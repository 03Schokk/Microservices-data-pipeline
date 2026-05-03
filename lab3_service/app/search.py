"""
lab3_service - search.py
Запрос: отчёт по группе - плановые и прослушанные часы по кафедральным дисциплинам
"""

import psycopg2
from neo4j import GraphDatabase
import redis
import pymongo
from db_config import POSTGRES_CONFIG, NEO4J_CONFIG, REDIS_CONFIG, MONGO_CONFIG

# ------- Подключения -------
def get_postgres_connection():
    return psycopg2.connect(**POSTGRES_CONFIG)

def get_neo4j_driver():
    driver = GraphDatabase.driver(NEO4J_CONFIG['uri'], auth=(NEO4J_CONFIG['user'], NEO4J_CONFIG['password']))
    driver.verify_connectivity()
    return driver

def get_redis_client():
    return redis.Redis(**REDIS_CONFIG)

def get_mongo_client():
    return pymongo.MongoClient(host=MONGO_CONFIG['host'], port=MONGO_CONFIG['port'],
                               username=MONGO_CONFIG['username'], password=MONGO_CONFIG['password'])

# ------- Основной отчёт -------
def generate_report(group_name: str):
    pg_conn = get_postgres_connection()
    neo4j_driver = get_neo4j_driver()
    redis_client = get_redis_client()
    mongo_client = get_mongo_client()

    try:
        # 1. ID группы (PostgreSQL)
        with pg_conn.cursor() as cur:
            cur.execute("SELECT id FROM student_group WHERE name = %s", (group_name,))
            row = cur.fetchone()
            if not row:
                return {"group_name": group_name, "students": []}
            group_id = row[0]

        # 2. Кафедральные курсы (PostgreSQL, is_primary = True)
        with pg_conn.cursor() as cur:
            cur.execute("""
                SELECT lc.id, lc.name, lc.lecture_hours, lc.semester
                FROM lecture_course lc
                JOIN department_specialties ds ON lc.specialty_id = ds.specialty_id
                WHERE ds.is_primary = TRUE
            """)
            courses = {
                str(row[0]): {
                    'name': row[1],
                    'planned_hours': row[2],
                    'semester': row[3]
                } for row in cur.fetchall()
            }
        if not courses:
            return {"group_name": group_name, "students": []}

        # 3. ID лекций кафедральных курсов (PostgreSQL)
        with pg_conn.cursor() as cur:
            cur.execute("SELECT id, course_id FROM lecture WHERE course_id = ANY(%s::uuid[])", (list(courses.keys()),))
            lecture_course = {str(row[0]): str(row[1]) for row in cur.fetchall()}

        student_card_map = {}         # список всех студентов (id: student_card_number) (для Redis и отчёта)
        student_schedule_lecture = [] # связь id студента с id расписания и id лекции (для подсчёта)

        # 4. Студенты и их расписание (Neo4j)
        with neo4j_driver.session() as session:
            # OPTIONAL MATCH - на случай, если у группы нет расписания по кафедральной дисциплине на определённом семестре
            result = session.run("""
                MATCH (g:StudentGroup {id: $group_id})-[:HAS_STUDENT]->(s:Student)
                OPTIONAL MATCH (g)-[:HAS_SCHEDULE]->(sch:Schedule)-[:PART_OF]->(l:Lecture)
                WHERE l.id IN $lecture_ids
                RETURN 
                    s.id AS student_id,
                    s.student_card_number AS student_card_number,
                    sch.id AS schedule_id,
                    l.id AS lecture_id
            """, group_id=str(group_id), lecture_ids=list(lecture_course.keys()))

            for row in result:
                student_id = row["student_id"]
                student_card_number = row["student_card_number"]

                if student_id not in student_card_map:
                    student_card_map[student_id] = student_card_number

                if row["schedule_id"] and row["lecture_id"]:
                    student_schedule_lecture.append((student_id, row["schedule_id"], row["lecture_id"]))

        if not student_card_map:
            return {"group_name": group_name, "students": []}

        # 5. Отметки о посещаемости (PostgreSQL)
        attendance = {}

        if student_schedule_lecture:
            students = [p[0] for p in student_schedule_lecture]
            schedules = [p[1] for p in student_schedule_lecture]
            
            with pg_conn.cursor() as cur:
                cur.execute("""
                    SELECT t.student_id, t.schedule_id, a.note
                    FROM unnest(%s::uuid[], %s::uuid[]) AS t(student_id, schedule_id)
                    LEFT JOIN attendance a ON a.student_id = t.student_id AND a.schedule_id = t.schedule_id
                """, (students, schedules))

                for row in cur.fetchall():
                    attendance[(str(row[0]), str(row[1]))] = row[2]

        # 6. Подсчёт прослушанных лекций по курсам для каждого студента
        student_course_hours = {}  # student_id: {course_id: lecture_count}
        
        for student_id, schedule_id, lecture_id in student_schedule_lecture:
            course_id = lecture_course.get(lecture_id)
            if not course_id:
                continue
            if attendance.get((student_id, schedule_id)) == 'Присутствовал':
                student_course_hours.setdefault(student_id, {}).setdefault(course_id, 0)
                student_course_hours[student_id][course_id] += 1

        # 7. Обогащение студентов группы из Redis
        pipe = redis_client.pipeline()
        for card in student_card_map.values():
            pipe.hgetall(f"student:{card}")
        redis_data = pipe.execute()

        # 8. Информация об университете (MongoDB)
        db = mongo_client[MONGO_CONFIG['database']]
        uni_doc = db.universities.find_one({}, {"name": 1, "address": 1, "website": 1})
        university_info = {
            "name": uni_doc.get("name", "N/D") if uni_doc else "N/D",
            "address": uni_doc.get("address", "N/D") if uni_doc else "N/D",
            "website": uni_doc.get("website", "N/D") if uni_doc else "N/D"
        }

        # 9. Сборка ответа
        students_out = []
        
        for idx, (student_id, card) in enumerate(student_card_map.items()):
            rd = redis_data[idx] or {}
            courses_list = []

            for course_id, count_hours in student_course_hours.get(student_id, {}).items():
                course = courses.get(course_id, {})
                courses_list.append({
                    "course_name": course.get('name', '?'),
                    "semester": course.get('semester', 0),
                    "planned_hours": course.get('planned_hours', 0),
                    "attended_hours": count_hours * 2   # 2 академ. часа на лекцию
                })

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