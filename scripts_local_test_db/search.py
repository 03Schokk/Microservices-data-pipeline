import sys
from datetime import datetime
from typing import List, Dict, Optional
import psycopg2
import redis
import pymongo
from neo4j import GraphDatabase
from elasticsearch import Elasticsearch

# ==================== КОНФИГУРАЦИЯ ====================
POSTGRES_CONFIG = {
    'host': 'localhost',
    'port': 5435,
    'database': 'testdb',
    'user': 'admin',
    'password': 'admin123'
}

REDIS_CONFIG = {
    'host': 'localhost',
    'port': 6379,
    'db': 0,
    'decode_responses': True
}

MONGO_CONFIG = {
    'host': 'localhost',
    'port': 27017,
    'username': 'admin',
    'password': 'admin123',
    'database': 'testdb',
    'authSource': 'admin'
}

NEO4J_CONFIG = {
    'uri': 'bolt://localhost:10001',
    'user': 'neo4j',
    'password': 'password123'
}

ELASTICSEARCH_CONFIG = {
    'host': 'localhost',
    'port': 20000,
    'user': 'elastic',
    'password': 'elastic_pass123'
}

# ==================== ПОДКЛЮЧЕНИЯ ====================

def get_elasticsearch_client():
    return Elasticsearch(
        hosts=[f'http://{ELASTICSEARCH_CONFIG["host"]}:{ELASTICSEARCH_CONFIG["port"]}'],
        basic_auth=(ELASTICSEARCH_CONFIG['user'], ELASTICSEARCH_CONFIG['password']),
        verify_certs=False,
        request_timeout=60
    )

def get_neo4j_driver():
    driver = GraphDatabase.driver(NEO4J_CONFIG['uri'], auth=(NEO4J_CONFIG['user'], NEO4J_CONFIG['password']))
    driver.verify_connectivity()
    return driver

def get_postgres_connection():
    return psycopg2.connect(**POSTGRES_CONFIG)

def get_redis_client():
    return redis.Redis(**REDIS_CONFIG)

def get_mongo_client():
    return pymongo.MongoClient(
        host=MONGO_CONFIG['host'],
        port=MONGO_CONFIG['port'],
        username=MONGO_CONFIG['username'],
        password=MONGO_CONFIG['password']
    )

# ==================== ПОИСК В ELASTICSEARCH ====================

def find_lecture_ids_by_term(es_client, term):
    """
    Нахождение лекций elasticsearch, у которых есть указанный темин/фраза
    """

    query_body = {
        "query": {
            "multi_match": {
                "query": term,
                "fields": ["title^2", "content_text"], # title с весом 2
                "type": "best_fields", # лучшее совпадение среди всех полей
                "operator": "and",     # совпадение всей фразы
                "fuzziness": "AUTO"    # автоматическая коррекция опечаток
            }
        },
        "size": 1000,                  # не более 1000 документов
        "_source": ["lecture_id"]      # только ID
    }

    response = es_client.search(index="materials", body=query_body)
    lecture_ids = set()
    for hit in response['hits']['hits']:
        lid = hit['_source'].get('lecture_id')
        if lid:
            lecture_ids.add(lid)

    return list(lecture_ids)

# ==================== ПОЛУЧЕНИЕ ДАННЫХ ИЗ NEO4J ====================

def get_students_and_schedules(neo4j_driver, lecture_ids, start_date, end_date):
    """
    Извлечение данных Neo4j по ID лекций elasticsearch:
    - ID занятий (schedule_id)
    - ID студентов (student_id)
    """
    if not lecture_ids:
        return []

    with neo4j_driver.session() as session:
        query = """
            MATCH (l:Lecture)-[:PART_OF]-(sch:Schedule)
            MATCH (g:StudentGroup)-[:HAS_SCHEDULE]->(sch)
            MATCH (g)-[:HAS_STUDENT]->(s:Student)
            WHERE l.id IN $lecture_ids 
              AND sch.date >= $start_date 
              AND sch.date <= $end_date
            RETURN DISTINCT 
                sch.id AS schedule_id, 
                g.id AS group_id, 
                s.id AS student_id,
                sch.date AS date
        """
        result = session.run(
            query,
            lecture_ids=lecture_ids,
            start_date=start_date,
            end_date=end_date
        )

        data = []
        for record in result:
            data.append({
                "schedule_id": record["schedule_id"],
                "student_id": record["student_id"]
            })
        return data

# ==================== РАСЧЁТ ПОСЕЩАЕМОСТИ В POSTGRESQL ====================

def get_attendance_stats(postgres_conn, neo4j_data, min_lessons=5):
    """
    Счёт статистики по студентам в PostgreSQL по полученным данным Neo4j (schedule_id, student_id)
    """

    if not neo4j_data:
        return []

    # Формируем пары (schedule_id, student_id)
    pairs = [(item["schedule_id"], item["student_id"]) for item in neo4j_data]

    with postgres_conn.cursor() as cur:
        query = """
            WITH neo4j_pairs AS ( -- формирование таблицы из массивов индексов neo4j
                SELECT * FROM unnest(%s::uuid[], %s::uuid[]) AS t(schedule_id, student_id)
            ),
            student_info AS (    -- сбор минимальной информации по студентам 
                SELECT DISTINCT 
                    s.id AS student_id,
                    s.student_card_number,
                    sg.name AS group_name,
                    sp.name AS specialty_name
                FROM neo4j_pairs np
                JOIN student s ON s.id = np.student_id
                JOIN student_group sg ON s.group_id = sg.id
                JOIN specialty sp ON sg.specialty_id = sp.id
            ),
            attendance_data AS ( -- cбор отметок по посещениям
                SELECT 
                    np.student_id,
                    np.schedule_id,
                    a.note
                FROM neo4j_pairs np
                LEFT JOIN attendance a 
                    ON a.schedule_id = np.schedule_id 
                    AND a.student_id = np.student_id
            )
            SELECT
                si.student_id,
                si.student_card_number,
                si.group_name,
                si.specialty_name,
                COUNT(DISTINCT ad.schedule_id) AS total_scheduled, -- общее количество записей по посещениям
                ROUND(
                    COUNT(DISTINCT CASE WHEN ad.note = 'Присутствовал' THEN ad.schedule_id END) * 100.0 /
                    NULLIF(COUNT(DISTINCT ad.schedule_id), 0), 2   -- процент посещённых занятий по отношению ко всем
                ) AS attendance_percent
            FROM student_info si
            JOIN attendance_data ad ON si.student_id = ad.student_id
            GROUP BY si.student_id, si.student_card_number, si.group_name, si.specialty_name
            HAVING COUNT(DISTINCT ad.schedule_id) >= %s -- минимальное число записей по посещениям, чтобы были хоть какие-то данные
            ORDER BY attendance_percent ASC
            LIMIT 10
        """

        schedule_ids = [p[0] for p in pairs]
        student_ids = [p[1] for p in pairs]
        cur.execute(query, (schedule_ids, student_ids, min_lessons))
        rows = cur.fetchall()
        columns = ['student_id', 'student_card_number', 'group_name', 'specialty_name',
                   'total_scheduled', 'attendance_percent']

        return [dict(zip(columns, row)) for row in rows]

# ==================== ОБОГАЩЕНИЕ НАЙДЕННЫХ 10 СТУДЕНТОВ ИЗ REDIS ====================

def enrich_students_from_redis(redis_client, student_stats):
    """
    Обогащение найденных 10 студентов данными Redis
    """

    if not student_stats:
        return []

    pipe = redis_client.pipeline()

    for s in student_stats:
        key = f"student:{s['student_card_number']}"
        pipe.hgetall(key)

    redis_data_list = pipe.execute()

    enriched = []
    for i, student in enumerate(student_stats):
        redis_data = redis_data_list[i] or {}
        enriched.append({
            'last_name': redis_data.get('last_name', ''),
            'first_name': redis_data.get('first_name', ''),
            'patronymic': redis_data.get('patronymic', ''),
            'student_card_number': student['student_card_number'],
            'email': redis_data.get('email', ''),
            'phone': redis_data.get('phone', ''),
            'group_name': student['group_name'],
            'specialty_name': student['specialty_name'],
            'total_scheduled': student['total_scheduled'],
            'attendance_percent': student['attendance_percent']
        })
    return enriched

# ==================== ПОЛУЧЕНИЕ ДАННЫХ УНИВЕРСИТЕТА ИЗ MONGODB ====================

def get_university_info(mongo_client):
    """
    Нахожение данных по университету MongoDB
    """

    db = mongo_client[MONGO_CONFIG['database']]
    doc = db.universities.find_one({}, {"name": 1, "address": 1, "website": 1})

    if doc:
        return {"name": doc.get("name"), "address": doc.get("address"), "website": doc.get("website")}
    return {"name": "N/D", "address": "N/D", "website": "N/D"}

# ==================== ПОЛУЧЕНИЕ ГРАНИЦ ПЕРИОДА ====================

def get_min_max_schedule_dates(postgres_conn):
    """
    Нахожение минимальной и максимальной даты занятий PostgreSQL
    """

    with postgres_conn.cursor() as cur:
        cur.execute("SELECT MIN(scheduled_date), MAX(scheduled_date) FROM schedule")
        min_date, max_date = cur.fetchone()
        return min_date, max_date

# ==================== ОСНОВНАЯ ФУНКЦИЯ ====================

def generate_report(term, start_date, end_date, min_lessons=5):

    print("Поиск лекций по термину в Elasticsearch...")

    es_client = get_elasticsearch_client()
    lecture_ids = find_lecture_ids_by_term(es_client, term)
    if not lecture_ids:
        print("Предупреждение: лекции, содержащие указанный термин, не найдены.")
        return []

    print(f"Найдено лекций: {len(lecture_ids)}")

    print("Получение расписания, групп и студентов из Neo4j...")

    neo4j_driver = get_neo4j_driver()
    neo4j_data = get_students_and_schedules(neo4j_driver, lecture_ids, start_date, end_date)
    neo4j_driver.close()
    if not neo4j_data:
        print("Предупреждение: за указанный период нет расписания для найденных лекций.")
        return []

    print(f"Получено записей из Neo4j: {len(neo4j_data)}")

    print("Вычисление процента посещаемости в PostgreSQL...")

    pg_conn = get_postgres_connection()
    student_stats = get_attendance_stats(pg_conn, neo4j_data, min_lessons)
    pg_conn.close()
    if not student_stats:
        print("Предупреждение: нет данных о посещаемости или недостаточно занятий (минимум 5).")
        return []

    print(f"Получена статистика по {len(student_stats)} студентам.")

    print("Обогащение данных найденных студентов из Redis...")
    
    redis_client = get_redis_client()
    enriched_students = enrich_students_from_redis(redis_client, student_stats)
    redis_client.close()

    print("Получение данных по университету из MongoDB...")
    
    mongo_client = get_mongo_client()
    university_info = get_university_info(mongo_client)
    mongo_client.close()
    if enriched_students:
        enriched_students[0]['university'] = university_info

    return enriched_students

def print_report(students, term, start_date, end_date):
    print("\n" + "=" * 165)
    print("ОТЧЁТ: 10 студентов с минимальным процентом посещения лекций, содержащих заданный термин")
    print("=" * 165)
    print(f"Параметры отчёта:")
    print(f"  Термин (искомый):            '{term}'")
    print(f"  Период обучения:              {start_date} – {end_date}")
    if students and 'university' in students[0]:
        uni = students[0]['university']
        print(f"  Университет (MongoDB):        {uni.get('name')}")
        print(f"  Адрес:                        {uni.get('address')}")
    print("\nРезультаты:")
    print("-" * 165)

    if not students:
        print("Нет данных для формирования отчёта.")
        return

    print(f"{'Студент':<35} {'Номер карты':<18} {'Email':<17} {'Телефон':<18} {'Группа':<15} {'Специальность':<30} {'% посещ.':<12} {'Всего занятий':<12}")
    print("-" * 165)

    for s in students:
        full_name = f"{s['last_name']} {s['first_name']} {s['patronymic']}".strip()
        if len(full_name) > 39:
            full_name = full_name[:36] + "..."
        
        spec_name = s['specialty_name']
        if len(spec_name) > 34:
            spec_name = spec_name[:31] + "..."
        
        percent_str = f"{s['attendance_percent']:.2f} %" if s['attendance_percent'] is not None else "0.00 %"
        
        print(f"{full_name:<35} "
              f"{s['student_card_number']:<12} "
              f"{s['email']:<20} "
              f"{s['phone']:<20} "
              f"{s['group_name']:<12} "
              f"{spec_name:<35} "
              f"{percent_str:<12} "
              f"{s['total_scheduled']:<12}")

    print("-" * 165)
    print("\n" + "=" * 165)
    print("Отчёт сформирован с использованием всех пяти БД:")
    print("  - Elasticsearch для поиска лекций по тексту")
    print("  - Neo4j для получения расписания, групп и студентов (граф связей)")
    print("  - PostgreSQL для расчёта посещаемости (только статистика)")
    print("  - Redis для персональных данных студентов")
    print("  - MongoDB для информации об университете")
    print("=" * 165)

def parse_date(s):
    s = s.strip()
    if not s:
        return None

    try:
        datetime.strptime(s, "%Y-%m-%d")
        return s
    except ValueError:
        raise ValueError("Неверный формат даты. Используйте ГГГГ-ММ-ДД")

def main():
    term = input("Введите слово или фразу для поиска в лекциях: ").strip()
    if not term:
        print("Ошибка: термин не может быть пустым.")
        return

    print("\nВведите период обучения (формат ГГГГ-ММ-ДД). Если дата не будет указана, будет использовано значение по умолчанию.")
    start_date_str = input("Начало периода (по умолчанию самый минимальный - 2024-09-01): ").strip()
    end_date_str = input("Конец периода (по умолчанию самый максимальный - 2024-12-24): ").strip()
    print()

    try:
        start_date = parse_date(start_date_str)
        end_date = parse_date(end_date_str)

        pg_conn = get_postgres_connection()
        min_date_db, max_date_db = get_min_max_schedule_dates(pg_conn)
        pg_conn.close()

        if start_date is None:
            start_date = min_date_db.isoformat()
        else:
            if start_date < min_date_str:
                print(f"Предупреждение: дата начала {start_date} раньше минимальной даты в расписании {min_date_str}")
                print(f"Взята минималная дата расписания {min_date_str}")
                start_date = min_date_str
                
        if end_date is None:
            end_date = max_date_db.isoformat()
        else:
            print(f"Предупреждение: дата окончания {end_date} позже максимальной даты в расписании {max_date_str}")
            print(f"Взята максимальная дата расписания {max_date_str}")
            end_date = max_date_str

        if start_date is None or end_date is None:
            print("Ошибка: не удалось определить границы периода (нет данных в расписании).")
            return

        if start_date > end_date:
            print("Ошибка: дата начала периода не может быть позже даты окончания.")
            return

    except ValueError as e:
        print(f"Ошибка: {e}")
        return

    try:
        report_data = generate_report(term, start_date, end_date)
        print_report(report_data, term, start_date, end_date)
    except Exception as e:
        print(f"\nОшибка при формировании отчёта: {e}")
        from traceback import print_exc
        print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()