"""
lab3_service - search.py

Запрос: отчёт по группе, в котором есть запланированные и прослушанные часы
по кафедральным дисциплинам
"""

import psycopg2
from neo4j import GraphDatabase
import redis
import pymongo
from db_config import POSTGRES_CONFIG, NEO4J_CONFIG, REDIS_CONFIG, MONGO_CONFIG

# ---------------------------- Подключения ----------------------------
def get_postgres_connection():
    return psycopg2.connect(**POSTGRES_CONFIG)

def get_neo4j_driver():
    driver = GraphDatabase.driver(
        NEO4J_CONFIG['uri'],
        auth=(NEO4J_CONFIG['user'],
        NEO4J_CONFIG['password'])
    )
    driver.verify_connectivity()
    return driver

def get_redis_client():
    return redis.Redis(**REDIS_CONFIG)

def get_mongo_client():
    return pymongo.MongoClient(
        host=MONGO_CONFIG['host'],
        port=MONGO_CONFIG['port'],
        username=MONGO_CONFIG['username'],
        password=MONGO_CONFIG['password']
    )

# ---------------------------- Основная функция ----------------------------
def generate_report(group_name: str):
    pg_conn = get_postgres_connection()
    neo4j_driver = get_neo4j_driver()
    redis_client = get_redis_client()
    mongo_client = get_mongo_client()

    try:
        # 1. Получаем группу и её специальность (PostgreSQL)
        with pg_conn.cursor() as cur:
            cur.execute(
                "SELECT id, specialty_id FROM student_group WHERE name = %s",
                (group_name,)
            )
            row = cur.fetchone()
            if not row:
                return {"group_name": group_name, "students": []}
            group_id, specialty_id = row

        # 2. Кафедральные курсы (привязанные к специальностям кафедр)
        with pg_conn.cursor() as cur:
            cur.execute("""
                SELECT lc.id, lc.name, lc.lecture_hours
                FROM lecture_course lc
                JOIN department_specialties ds ON lc.specialty_id = ds.specialty_id
                WHERE ds.is_primary = TRUE
            """)
            dept_courses = {}
            for row in cur.fetchall():
                dept_courses[str(row[0])] = {
                    'name': row[1],
                    'planned_hours': row[2]
                }
        if not dept_courses:
            return {"group_name": group_name, "students": []}

        # 3. Студенты группы (PostgreSQL)
        with pg_conn.cursor() as cur:
            cur.execute(
                "SELECT id, student_card_number FROM student WHERE group_id = %s",
                (group_id,)
            )
            students_pg = {str(row[0]): row[1] for row in cur.fetchall()}
        if not students_pg:
            return {"group_name": group_name, "students": []}

        # 4. Соответствие лекция -> курс (PostgreSQL)
        with pg_conn.cursor() as cur:
            cur.execute(
                "SELECT id, course_id FROM lecture WHERE course_id = ANY(%s::uuid[])",
                (list(dept_courses.keys()),)
            )
            rows = cur.fetchall()
            lecture_course_map = {str(row[0]): str(row[1]) for row in rows}
            lecture_ids_list = [str(row[0]) for row in rows]   # реальные ID лекций

        # 5. Расписание и посещения через Neo4j (пары student – lecture)
        student_lectures = {}
        if lecture_ids_list:
            with neo4j_driver.session() as session:
                query = """
                    MATCH (g:StudentGroup {id: $group_id})-[:HAS_STUDENT]->(s:Student)
                    MATCH (g)-[:HAS_SCHEDULE]->(sch:Schedule)-[:PART_OF]->(l:Lecture)
                    WHERE l.id IN $lecture_ids
                    RETURN s.id AS student_id, sch.id AS schedule_id, l.id AS lecture_id
                """
                result = session.run(query,
                                    group_id=str(group_id),
                                    lecture_ids=lecture_ids_list)
                for record in result:
                    sid = record["student_id"]
                    if sid not in student_lectures:
                        student_lectures[sid] = []
                    student_lectures[sid].append((record["schedule_id"], record["lecture_id"]))

        # 6. Получаем отметки о посещении (PostgreSQL)
        pairs = []
        for sid, lst in student_lectures.items():
            for sch_id, _ in lst:
                pairs.append((sch_id, sid))
        attendance_notes = {}
        if pairs:
            schedule_ids = [p[0] for p in pairs]
            student_ids = [p[1] for p in pairs]
            with pg_conn.cursor() as cur:
                query = """
                    SELECT t.schedule_id, t.student_id, a.note
                    FROM unnest(%s::uuid[], %s::uuid[]) AS t(schedule_id, student_id)
                    LEFT JOIN attendance a ON a.schedule_id = t.schedule_id AND a.student_id = t.student_id
                """
                cur.execute(query, (schedule_ids, student_ids))
                for row in cur.fetchall():
                    attendance_notes[(str(row[0]), str(row[1]))] = row[2]

        # 7. Подсчитываем прослушанные часы по курсам для каждого студента
        student_course_hours = {}  # student_id -> {course_id: attended_lectures_count}
        for sid, lst in student_lectures.items():
            course_counts = {}
            for sch_id, lec_id in lst:
                course_id = lecture_course_map.get(lec_id)
                if not course_id:
                    continue
                note = attendance_notes.get((sch_id, sid), None)
                if note == 'Присутствовал':
                    course_counts[course_id] = course_counts.get(course_id, 0) + 1
            student_course_hours[sid] = course_counts

        # 8. Обогащаем данные из Redis и формируем отчёт
        pipe = redis_client.pipeline()
        for card in students_pg.values():
            pipe.hgetall(f"student:{card}")
        redis_data = pipe.execute()

        # 9. Информация об университете (MongoDB) – опционально
        db = mongo_client[MONGO_CONFIG['database']]
        uni_doc = db.universities.find_one({}, {"name": 1, "address": 1, "website": 1})
        university_info = {
            "name": uni_doc.get("name", "N/D") if uni_doc else "N/D",
            "address": uni_doc.get("address", "N/D") if uni_doc else "N/D",
            "website": uni_doc.get("website", "N/D") if uni_doc else "N/D"
        }

        # 10. Сборка ответа
        students_out = []
        for idx, (student_id, card) in enumerate(students_pg.items()):
            rd = redis_data[idx] if redis_data[idx] else {}
            courses_list = []
            for course_id, attendance_count in student_course_hours.get(student_id, {}).items():
                course_info = dept_courses.get(course_id, {})
                courses_list.append({
                    "course_name": course_info.get('name', '?'),
                    "planned_hours": course_info.get('planned_hours', 0),
                    "attended_hours": attendance_count * 2  # каждая лекция = 2 академ. часа
                })
            # если студент не посещал ни одной лекции – всё равно включаем в отчёт
            students_out.append({
                "last_name": rd.get("last_name", ""),
                "first_name": rd.get("first_name", ""),
                "patronymic": rd.get("patronymic", ""),
                "student_card_number": card,
                "email": rd.get("email", ""),
                "phone": rd.get("phone", ""),
                "courses": courses_list
            })

        return {
            "group_name": group_name,
            "university": university_info,
            "students": students_out
        }

    except Exception as e:
        import traceback
        print("ERROR in generate_report (lab3):")
        traceback.print_exc()
        return {"group_name": group_name, "students": []}
    finally:
        pg_conn.close()
        neo4j_driver.close()
        redis_client.close()
        mongo_client.close()