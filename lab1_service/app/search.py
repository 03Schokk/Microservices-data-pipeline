"""
lab1_service - search.py

Запрос: для термина и периода обучения найти лекции с данным термином,
после чего найти занятия по этим лекциям, по ним вычислить 10 студентов,
которые хуже всего посещали данные лекции
"""

import sys
from datetime import datetime
import psycopg2
import redis
import pymongo
from neo4j import GraphDatabase
from elasticsearch import Elasticsearch
from db_config import (
    POSTGRES_CONFIG, REDIS_CONFIG, MONGO_CONFIG,
    NEO4J_CONFIG, ELASTICSEARCH_CONFIG
)

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
    query_body = {
        "query": {
            "multi_match": {
                "query": term,
                # Добавили annotation из твоей ER-диаграммы
                "fields": ["title^3", "annotation^2", "content_text"], 
                "type": "best_fields",
                "fuzziness": "AUTO"
            }
        },
        "size": 100,
        "_source": ["lecture_id"]
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
def get_attendance_stats(postgres_conn, neo4j_data):
    if not neo4j_data: return []
    
    # Чтобы работало партиционирование, нам нужно вычислить начало недели
    # (в PostgreSQL это date_trunc('week', scheduled_date))
    with postgres_conn.cursor() as cur:
        query = """
            WITH student_info AS (
                SELECT s.id, s.student_card_number, sg.name as group_name
                FROM student s JOIN student_group sg ON s.id = sg.id
            ),
            absent_counts AS (
                SELECT 
                    a.student_id, 
                    COUNT(*) as missed_count
                FROM attendance a
                -- Используем партиционирование: фильтруем по дате начала недели
                WHERE a.note = 'Отсутствовал'
                AND a.schedule_id IN %s 
                GROUP BY a.student_id
            )
            SELECT 
                si.student_card_number, 
                si.group_name, 
                ac.missed_count
            FROM student_info si
            JOIN absent_counts ac ON si.id = ac.student_id
            ORDER BY ac.missed_count DESC
            LIMIT 10
        """
        schedule_ids = [p[0] for p in pairs]
        student_ids = [p[1] for p in pairs]
        cur.execute(query, (schedule_ids, student_ids))
        rows = cur.fetchall()
        columns = ['student_id', 'student_card_number', 'group_name', 'specialty_name',
                   'total_scheduled', 'attendance_percent']
        return [dict(zip(columns, row)) for row in rows]

# ==================== ОБОГАЩЕНИЕ ИЗ REDIS ====================
def enrich_students_from_redis(redis_client, student_stats):
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

# ==================== MONGODB ====================
def get_university_info(mongo_client):
    db = mongo_client[MONGO_CONFIG['database']]
    doc = db.universities.find_one({}, {"name": 1, "address": 1, "website": 1})
    if doc:
        return {"name": doc.get("name"), "address": doc.get("address"), "website": doc.get("website")}
    return {"name": "N/D", "address": "N/D", "website": "N/D"}

def get_min_max_schedule_dates(postgres_conn):
    with postgres_conn.cursor() as cur:
        cur.execute("SELECT MIN(scheduled_date), MAX(scheduled_date) FROM schedule")
        min_date, max_date = cur.fetchone()
        return min_date, max_date

# ==================== ОСНОВНАЯ ФУНКЦИЯ ====================
def generate_report(term, start_date, end_date):
    try:
        es_client = get_elasticsearch_client()
        lecture_ids = find_lecture_ids_by_term(es_client, term)
        if not lecture_ids:
            print(f"Лекции с термином '{term}' не найдены")
            return []

        neo4j_driver = get_neo4j_driver()
        neo4j_data = get_students_and_schedules(neo4j_driver, lecture_ids, start_date, end_date)
        neo4j_driver.close()
        if not neo4j_data:
            print("Нет расписания для найденных лекций в указанном периоде")
            return []

        pg_conn = get_postgres_connection()
        student_stats = get_attendance_stats(pg_conn, neo4j_data)
        pg_conn.close()
        if not student_stats:
            print("Нет данных о посещаемости или недостаточно занятий")
            return []

        redis_client = get_redis_client()
        enriched_students = enrich_students_from_redis(redis_client, student_stats)
        redis_client.close()

        mongo_client = get_mongo_client()
        university_info = get_university_info(mongo_client)
        mongo_client.close()

        for student in enriched_students:
            student['university'] = university_info

        return enriched_students
    except Exception as e:
        import traceback
        print("ERROR in generate_report:")
        traceback.print_exc()
        return []
