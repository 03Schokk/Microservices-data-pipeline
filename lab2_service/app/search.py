"""
lab2_service - search.py

Запрос: для заданного семестра и года обучения получить список лекций
с указанием количества слушателей и требований к оборудованию
"""

import psycopg2
from neo4j import GraphDatabase
from db_config import POSTGRES_CONFIG, NEO4J_CONFIG

# ---------------------------- PostgreSQL ----------------------------
def get_postgres_connection():
    return psycopg2.connect(**POSTGRES_CONFIG)

def get_group_ids_by_year(pg_conn, enrollment_year):
    """Возвращает список UUID групп с заданным годом набора."""
    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM student_group WHERE enrollment_year = %s",
            (enrollment_year,)
        )
        return [row[0] for row in cur.fetchall()]

def get_lectures_by_semester(pg_conn, semester):
    """Возвращает список лекций"""
    with pg_conn.cursor() as cur:
        cur.execute("""
            SELECT l.id, l.title, l.lecture_type, l.computer_type,
                   c.id AS course_id, c.name AS course_name,
                   c.description AS course_description,
                   s.name AS specialty_name
            FROM lecture l
            JOIN lecture_course c ON l.course_id = c.id
            LEFT JOIN specialty s ON c.specialty_id = s.id
            WHERE c.semester = %s
        """, (semester,))
        lectures = {}
        for row in cur.fetchall():
            lectures[str(row[0])] = {
                'title': row[1],
                'lecture_type': row[2],
                'computer_type': row[3],
                'course_id': str(row[4]),
                'course_name': row[5],
                'course_description': row[6],
                'specialty_name': row[7] if row[7] else 'Не указана'
            }
        return lectures

# ---------------------------- Neo4j ----------------------------
def get_neo4j_driver():
    driver = GraphDatabase.driver(
        NEO4J_CONFIG['uri'],
        auth=(NEO4J_CONFIG['user'],
        NEO4J_CONFIG['password'])
    )
    driver.verify_connectivity()
    return driver

def get_lecture_student_counts(neo4j_driver, group_ids, lecture_ids):
    """
    Для каждой лекции подсчитывает количество уникальных студентов,
    которые присутствуют в расписании через свои группы.
    group_ids и lecture_ids - списки строковых UUID.
    Возвращает dict: lecture_id -> student_count
    """
    if not group_ids or not lecture_ids:
        return {}

    with neo4j_driver.session() as session:
        query = """
            MATCH (g:StudentGroup)-[:HAS_SCHEDULE]->(sch:Schedule)-[:PART_OF]->(l:Lecture)
            MATCH (g)-[:HAS_STUDENT]->(s:Student)
            WHERE g.id IN $group_ids AND l.id IN $lecture_ids
            RETURN l.id AS lecture_id, COUNT(DISTINCT s.id) AS student_count
        """
        result = session.run(query, group_ids=group_ids, lecture_ids=lecture_ids)
        counts = {}
        for record in result:
            counts[record["lecture_id"]] = record["student_count"]
        return counts

# ---------------------------- Главный отчёт ----------------------------
def generate_report(semester: int, year: int):
    pg_conn = get_postgres_connection()
    neo4j_driver = get_neo4j_driver()

    try:
        # 1. Группы нужного года обучения
        group_ids = [str(g) for g in get_group_ids_by_year(pg_conn, year)]
        if not group_ids:
            return []

        # 2. Лекции курсов заданного семестра
        lectures_dict = get_lectures_by_semester(pg_conn, semester)
        if not lectures_dict:
            return []

        lecture_ids = list(lectures_dict.keys())

        # 3. Количество студентов на каждую лекцию (Neo4j)
        student_counts = get_lecture_student_counts(neo4j_driver, group_ids, lecture_ids)

        # 4. Собираем результат
        report = []
        for lec_id, lec_info in lectures_dict.items():
            report.append({
                "specialty_name": lec_info["specialty_name"],
                "course_name": lec_info["course_name"],
                "course_description": lec_info["course_description"],
                "semester": semester,
                "lecture_title": lec_info["title"],
                "lecture_type": lec_info["lecture_type"],
                "computer_type": lec_info["computer_type"],
                "student_count": student_counts.get(lec_id, 0)
            })

        return report

    except Exception as e:
        import traceback
        print("ERROR in generate_report (lab2):")
        traceback.print_exc()
        return []
    finally:
        pg_conn.close()
        neo4j_driver.close()