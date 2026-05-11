"""
generator - generator.py

Генерирует несколько семестров (осень 2024 - весна 2026)
"""

import uuid, random, json, time
from datetime import datetime, timedelta, date
from faker import Faker
import psycopg2
from psycopg2.extras import execute_values
import redis
import pymongo
from neo4j import GraphDatabase
from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk

from db_config import (
    POSTGRES_CONFIG, REDIS_CONFIG, MONGO_CONFIG,
    NEO4J_CONFIG, ELASTICSEARCH_CONFIG
)

fake = Faker('ru_RU')

POSTGRES_CONFIG = {
    'host': 'postgresql',
    'port': 5432,
    'database': 'testdb',
    'user': 'admin',
    'password': 'admin123'
}

# ------------------ Генерация данных ------------------
def generate_universities():
    return [{
        'id': uuid.uuid4(),
        'name': 'МИРЭА - Российский технологический университет',
        'short_name': 'РТУ МИРЭА',
        'address': 'просп. Вернадского, д. 78, Москва',
        'website': 'https://mirea.ru',
        'founded_year': 1947
    }]

def generate_institutes(university_id):
    institutes = [
        {'name': 'Институт информационных технологий', 'short_name': 'ИТУ', 'dean': fake.name()},
        {'name': 'Институт кибербезопасности и цифровых технологий', 'short_name': 'ИКБ', 'dean': fake.name()},
        {'name': 'Институт радиоэлектроники и информатики', 'short_name': 'ИРИ', 'dean': fake.name()},
    ]
    return [{
        'id': uuid.uuid4(),
        'university_id': university_id,
        'name': inst['name'],
        'short_name': inst['short_name'],
        'dean': inst['dean']
    } for inst in institutes]

def generate_departments(institute_ids):
    departments = []
    dept_names = [
        'Программной инженерии', 'Информационной безопасности', 'Вычислительной техники',
        'Автоматизации и управления', 'Системного анализа', 'Прикладной математики'
    ]
    for inst_id in institute_ids:
        for i in range(2):
            dept_name = random.choice(dept_names)
            departments.append({
                'id': uuid.uuid4(),
                'institute_id': inst_id,
                'name': f'Кафедра {dept_name}',
                'short_name': f'КФ-{random.randint(1, 20)}',
                'head': fake.name(),
                'room': f'{random.randint(100, 500)}'
            })
    return departments

def generate_specialties():
    specialties_data = [
        ('Информатика и вычислительная техника', '09.03.01', 'Бакалавриат', 4),
        ('Программная инженерия', '09.03.04', 'Бакалавриат', 4),
        ('Прикладная математика и информатика', '01.03.02', 'Бакалавриат', 4),
        ('Информационные системы и технологии', '09.03.02', 'Бакалавриат', 4),
        ('Бизнес-информатика', '38.03.05', 'Бакалавриат', 4),
    ]
    return [{
        'id': uuid.uuid4(),
        'name': name,
        'code': code,
        'degree_level': level,
        'duration_years': duration
    } for name, code, level, duration in specialties_data]

def generate_department_specialties(department_ids, specialty_ids):
    dept_spec = []
    for dept_id in department_ids:
        for spec_id in random.sample(specialty_ids, k=random.randint(1, 3)):
            dept_spec.append({
                'id': uuid.uuid4(),
                'department_id': dept_id,
                'specialty_id': spec_id,
                'is_primary': random.choice([True, False])
            })
    return dept_spec

def generate_lecture_courses(specialty_ids):
    """Генерирует курсы для семестров 1-6"""
    courses = []
    course_names = [
        'Базы данных', 'Алгоритмы и структуры данных', 'Операционные системы',
        'Сети ЭВМ', 'Объектно-ориентированное программирование',
        'Веб-технологии', 'Искусственный интеллект', 'Машинное обучение',
        'Криптография', 'Тестирование ПО', 'DevOps практики', 'Облачные вычисления',
        'Backend-разработка', 'Frontend-разработка', 'Разработка мобильных приложений'
    ]
    for spec_id in specialty_ids:
        for semester in range(1, 7):
            for course_name in random.sample(course_names, k=2):
                
                lecture_hours = random.randint(32, 64)
                practice_hours = random.randint(16, 32)
                lab_hours = random.randint(16, 32)
                total_hours = lecture_hours + practice_hours + lab_hours

                courses.append({
                    'id': uuid.uuid4(),
                    'specialty_id': spec_id,
                    'name': course_name,
                    'description': f'{fake.sentence(nb_words=5)}',
                    'semester': semester,
                    'total_hours': total_hours,
                    'lecture_hours': lecture_hours,
                    'practice_hours': practice_hours,
                    'lab_hours': lab_hours
                })
    return courses

def generate_lectures(course_ids):
    lectures = []
    for course_id in course_ids:
        for i in range(1, random.randint(8, 16)):
            lecture_type = random.choice(['Лекция', 'Практика', 'Лабораторная'])
            computer_type = ['Требуется проектор', 'Дополнительная техника не требуется']

            if lecture_type == 'Лекция':
                computer_type.extend(['Требуется компьютерный класс с ОС Windows', 'Требуется компьютерный класс с ОС Linux'])

            lectures.append({
                'id': uuid.uuid4(),
                'course_id': course_id,
                'title': f'Занятие {i}: {fake.sentence(nb_words=5)}',
                'annotation': fake.paragraph(),
                'lecture_type': lecture_type,
                'computer_type': random.choice(computer_type),
                'order_number': i,
                'duration_minutes': 90  # 2 академических часа (90 минут)
            })
    return lectures

def generate_lecture_materials(lecture_ids):
    materials = []
    for lecture_id in lecture_ids:
        for _ in range(random.randint(1, 3)):
            content_type = random.choice(['text', 'pdf', 'video', 'presentation'])
            materials.append({
                'id': uuid.uuid4(),
                'lecture_id': lecture_id,
                'content_type': content_type,
                'title': f'Материал: {fake.sentence(nb_words=4)}',
                'content_text': fake.text(max_nb_chars=500),
                'file_url': f'https://storage.example.com/{uuid.uuid4()}.{content_type}',
                'metadata': {'size': random.randint(1024, 10485760), 'pages': random.randint(1, 50)}
            })
    return materials

def generate_student_groups(specialty_ids):
    groups = []
    years = [2022, 2023, 2024]
    prefixes = ['БСБО', 'БИСО', 'БББО', 'БАСО', 'ББСО']
    for idx, spec_id in enumerate(specialty_ids):
        prefix = prefixes[idx % len(prefixes)]
        for year in years:
            for i in range(1, 6):
                groups.append({
                    'id': uuid.uuid4(),
                    'specialty_id': spec_id,
                    'name': f'{prefix}-{i:02d}-{year % 100:02d}',
                    'enrollment_year': year,
                    'curator': fake.name()
                })
    return groups

def generate_students(group_ids):
    students = []
    for i in range(1500):
        name = fake.name().split()
        students.append({
            'id': uuid.uuid4(),
            'group_id': random.choice(group_ids),
            'first_name': name[0],
            'last_name': name[1],
            'patronymic': name[2],
            'email': f'student{i}@edu.mirea.ru',
            'phone': fake.phone_number(),
            'student_card_number': f'НСБ-{i+1:06d}',
            'enrollment_date': fake.date_between(start_date='-4y', end_date='-2y'),
            'status': random.choice(['Активный', 'Академ'])
        })
    return students

def generate_schedules_for_semester(start_date, end_date, lecture_ids, group_ids):
    schedules = []
    current_date = start_date
    while current_date <= end_date:
        # праздники не учитываются
        for lecture_id in random.sample(lecture_ids, k=min(40, len(lecture_ids))):
            for group_id in random.sample(group_ids, k=min(10, len(group_ids))):
                if random.random() > 0.2:
                    start_time = datetime.strptime(f"{random.randint(9, 17)}:{random.choice(['00', '30'])}", "%H:%M").time()
                    end_time = (datetime.combine(current_date, start_time) + timedelta(minutes=90)).time()
                    schedules.append({
                        'id': uuid.uuid4(),
                        'lecture_id': lecture_id,
                        'group_id': group_id,
                        'scheduled_date': current_date,
                        'week_start_date': current_date, # упрощённо - начало недели совпадает с датой
                        'start_time': start_time,
                        'end_time': end_time,
                        'classroom': f'{random.choice(["А", "Б", "В", "Г", "Д"])}-{random.randint(100, 400)}',
                        'teacher_name': fake.name(),
                        'status': random.choice(['Отменено', 'Завершено'])
                    })
        current_date += timedelta(days=7)
    return schedules

def generate_attendance(schedules, students):
    attendance = []
    students_by_group = {}
    for s in students:
        students_by_group.setdefault(s['group_id'], []).append(s)
    for schedule in schedules:
        group_students = students_by_group.get(schedule['group_id'], [])
        for student in group_students:
            attendance.append({
                'id': uuid.uuid4(),
                'week_start_date': schedule['week_start_date'],
                'schedule_id': schedule['id'],
                'student_id': student['id'],
                'marked_at': datetime.combine(schedule['scheduled_date'], schedule['start_time']),
                'marked_by': schedule['teacher_name'],
                'note': 'Присутствовал' if random.random() > 0.20 else 'Отсутствовал'
            })
    return attendance

# ------------------ Очистка PostgreSQL ------------------
def clear_database():
    # PostgreSQL
    conn = psycopg2.connect(**POSTGRES_CONFIG)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    cur.close()
    conn.close()

# ------------------ Заполнение PostgreSQL ------------------
def create_tables():
    conn = psycopg2.connect(**POSTGRES_CONFIG)
    conn.autocommit = True
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS university (
            id UUID PRIMARY KEY,
            name VARCHAR(500) NOT NULL,
            short_name VARCHAR(100),
            address TEXT,
            website VARCHAR(255),
            founded_year INT,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS institute (
            id UUID PRIMARY KEY,
            university_id UUID REFERENCES university(id) ON DELETE CASCADE,
            name VARCHAR(500) NOT NULL,
            short_name VARCHAR(100),
            dean VARCHAR(300),
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS department (
            id UUID PRIMARY KEY,
            institute_id UUID REFERENCES institute(id) ON DELETE CASCADE,
            name VARCHAR(500) NOT NULL,
            short_name VARCHAR(100),
            head VARCHAR(300),
            room VARCHAR(50),
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS specialty (
            id UUID PRIMARY KEY,
            name VARCHAR(500) NOT NULL,
            code VARCHAR(20) NOT NULL,
            degree_level VARCHAR(20),
            duration_years INT,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS department_specialties (
            id UUID PRIMARY KEY,
            department_id UUID REFERENCES department(id) ON DELETE CASCADE,
            specialty_id UUID REFERENCES specialty(id) ON DELETE CASCADE,
            is_primary BOOLEAN,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS lecture_course (
            id UUID PRIMARY KEY,
            specialty_id UUID REFERENCES specialty(id) ON DELETE CASCADE,
            name VARCHAR(500) NOT NULL,
            description TEXT,
            semester INT,
            total_hours INT,
            lecture_hours INT,
            practice_hours INT,
            lab_hours INT,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS lecture (
            id UUID PRIMARY KEY,
            course_id UUID REFERENCES lecture_course(id) ON DELETE CASCADE,
            title VARCHAR(500) NOT NULL,
            annotation TEXT,
            lecture_type VARCHAR(50),
            computer_type VARCHAR(100),
            order_number INT,
            duration_minutes INT,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS lecture_material (
            id UUID PRIMARY KEY,
            lecture_id UUID REFERENCES lecture(id) ON DELETE CASCADE,
            content_type VARCHAR(50),
            title VARCHAR(500),
            content_text TEXT,
            file_url VARCHAR(1000),
            metadata JSONB,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS student_group (
            id UUID PRIMARY KEY,
            specialty_id UUID REFERENCES specialty(id) ON DELETE CASCADE,
            name VARCHAR(50) NOT NULL,
            enrollment_year INT,
            curator VARCHAR(300),
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS student (
            id UUID PRIMARY KEY,
            group_id UUID REFERENCES student_group(id) ON DELETE CASCADE,
            first_name VARCHAR(100) NOT NULL,
            last_name VARCHAR(100) NOT NULL,
            patronymic VARCHAR(100),
            email VARCHAR(255),
            phone VARCHAR(20),
            student_card_number VARCHAR(20),
            enrollment_date DATE,
            status VARCHAR(20),
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS schedule (
            id UUID PRIMARY KEY,
            lecture_id UUID REFERENCES lecture(id) ON DELETE CASCADE,
            group_id UUID REFERENCES student_group(id) ON DELETE CASCADE,
            scheduled_date DATE,
            week_start_date DATE,
            start_time TIME,
            end_time TIME,
            classroom VARCHAR(50),
            teacher_name VARCHAR(300),
            status VARCHAR(20),
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id UUID NOT NULL,
            week_start_date DATE NOT NULL,
            schedule_id UUID NOT NULL,
            student_id UUID NOT NULL,
            marked_at TIMESTAMP,
            marked_by VARCHAR(300),
            note VARCHAR(500),
            created_at TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY (id, week_start_date),
            FOREIGN KEY (schedule_id) REFERENCES schedule(id) ON DELETE CASCADE,
            FOREIGN KEY (student_id) REFERENCES student(id) ON DELETE CASCADE
        ) PARTITION BY RANGE (week_start_date)
    """)

    # все даты начала учебных недель
    week_starts = set()
    semesters_config = [
        (date(2024, 9, 1), date(2024, 12, 24)),
        (date(2025, 2, 9), date(2025, 6, 5)),
        (date(2025, 9, 1), date(2025, 12, 24)),
        (date(2026, 2, 9), date(2026, 6, 5)),
    ]
    for start_d, end_d in semesters_config:
        current = start_d
        while current <= end_d:
            week_starts.add(current)
            current += timedelta(days=7)

    # партиции для каждой недели
    for week_start in sorted(week_starts):
        week_end = week_start + timedelta(days=7)   # интервал ровно 7 дней
        iso_year, iso_week, _ = week_start.isocalendar()
        partition_name = f"attendance_{iso_year}_w{iso_week:02d}"
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {partition_name} PARTITION OF attendance
            FOR VALUES FROM ('{week_start.isoformat()}') TO ('{week_end.isoformat()}')
        """)

    # создание слота репликации, если не существует
    cur.execute("SELECT slot_name FROM pg_replication_slots WHERE slot_name = 'debezium'")
    if cur.fetchone() is None:
        cur.execute("SELECT pg_create_logical_replication_slot('debezium', 'wal2json')")
    
    # создание публикации, если не существует
    cur.execute("SELECT pubname FROM pg_publication WHERE pubname = 'pub'")
    if cur.fetchone() is None:
        cur.execute("CREATE PUBLICATION pub FOR ALL TABLES")

    cur.close()
    conn.close()

def fill_tables(data):
    conn = psycopg2.connect(**POSTGRES_CONFIG)
    conn.autocommit = True
    cur = conn.cursor()
    now = datetime.now()

    execute_values(cur,
        """INSERT INTO university (id, name, short_name, address, website, founded_year, created_at, updated_at) VALUES %s""",
        [(str(u['id']), u['name'], u['short_name'], u['address'], u['website'], u['founded_year'], now, now) for u in data['universities']]
    )

    execute_values(cur,
        """INSERT INTO institute (id, university_id, name, short_name, dean, created_at, updated_at) VALUES %s""",
        [(str(i['id']), str(i['university_id']), i['name'], i['short_name'], i['dean'], now, now) for i in data['institutes']]
    )

    execute_values(cur,
        """INSERT INTO department (id, institute_id, name, short_name, head, room, created_at, updated_at) VALUES %s""",
        [(str(d['id']), str(d['institute_id']), d['name'], d['short_name'], d['head'], d['room'], now, now) for d in data['departments']]
    )

    execute_values(cur,
        """INSERT INTO specialty (id, name, code, degree_level, duration_years, created_at, updated_at) VALUES %s""",
        [(str(s['id']), s['name'], s['code'], s['degree_level'], s['duration_years'], now, now) for s in data['specialties']]
    )

    execute_values(cur,
        """INSERT INTO department_specialties (id, department_id, specialty_id, is_primary, created_at) VALUES %s""",
        [(str(ds['id']), str(ds['department_id']), str(ds['specialty_id']), ds['is_primary'], now) for ds in data['department_specialties']]
    )

    execute_values(cur,
        """INSERT INTO lecture_course (id, specialty_id, name, description, semester, total_hours, lecture_hours, practice_hours, lab_hours, created_at, updated_at) VALUES %s""",
        [(str(lc['id']), str(lc['specialty_id']), lc['name'], lc['description'], lc['semester'], lc['total_hours'], lc['lecture_hours'], lc['practice_hours'], lc['lab_hours'], now, now) for lc in data['lecture_courses']]
    )

    execute_values(cur,
        """INSERT INTO lecture (id, course_id, title, annotation, lecture_type, computer_type, order_number, duration_minutes, created_at, updated_at) VALUES %s""",
        [(str(l['id']), str(l['course_id']), l['title'], l['annotation'], l['lecture_type'], l['computer_type'], l['order_number'], l['duration_minutes'], now, now) for l in data['lectures']]
    )

    execute_values(cur,
        """INSERT INTO lecture_material (id, lecture_id, content_type, title, content_text, file_url, metadata, created_at, updated_at) VALUES %s""",
        [(str(m['id']), str(m['lecture_id']), m['content_type'], m['title'], m['content_text'], m['file_url'], json.dumps(m['metadata']), now, now) for m in data['lecture_materials']]
    )

    execute_values(cur,
        """INSERT INTO student_group (id, specialty_id, name, enrollment_year, curator, created_at, updated_at) VALUES %s""",
        [(str(g['id']), str(g['specialty_id']), g['name'], g['enrollment_year'], g['curator'], now, now) for g in data['student_groups']]
    )

    execute_values(cur,
        """INSERT INTO student (id, group_id, first_name, last_name, patronymic, email, phone, student_card_number, enrollment_date, status, created_at, updated_at) VALUES %s""",
        [(str(s['id']), str(s['group_id']), s['first_name'], s['last_name'], s['patronymic'], s['email'], s['phone'], s['student_card_number'], s['enrollment_date'], s['status'], now, now) for s in data['students']]
    )

    execute_values(cur,
        """INSERT INTO schedule (id, lecture_id, group_id, scheduled_date, week_start_date, start_time, end_time, classroom, teacher_name, status, created_at, updated_at) VALUES %s""",
        [(str(sch['id']), str(sch['lecture_id']), str(sch['group_id']), sch['scheduled_date'], sch['week_start_date'], sch['start_time'], sch['end_time'], sch['classroom'], sch['teacher_name'], sch['status'], now, now) for sch in data['schedules']]
    )

    execute_values(cur,
        """INSERT INTO attendance (id, week_start_date, schedule_id, student_id, marked_at, marked_by, note, created_at) VALUES %s""",
        [(str(a['id']), a['week_start_date'], str(a['schedule_id']), str(a['student_id']), a['marked_at'], a['marked_by'], a['note'], now) for a in data['attendance']]
    )

    cur.close()
    conn.close()


def run_generation():

    clear_database()
    create_tables()

    # Генерация базовых сущностей
    data = {}

    data['universities'] = generate_universities()

    data['institutes'] = generate_institutes(data['universities'][0]['id'])

    institute_ids = [i['id'] for i in data['institutes']]
    data['departments'] = generate_departments(institute_ids)

    department_ids = [d['id'] for d in data['departments']]
    data['specialties'] = generate_specialties()

    specialty_ids = [s['id'] for s in data['specialties']]
    data['department_specialties'] = generate_department_specialties(department_ids, specialty_ids)

    data['lecture_courses'] = generate_lecture_courses(specialty_ids)

    course_ids = [c['id'] for c in data['lecture_courses']]
    data['lectures'] = generate_lectures(course_ids)
    
    lecture_ids = [l['id'] for l in data['lectures']]
    data['lecture_materials'] = generate_lecture_materials(lecture_ids)

    data['student_groups'] = generate_student_groups(specialty_ids)

    group_ids = [g['id'] for g in data['student_groups']]
    data['students'] = generate_students(group_ids)

    # Настройка семестров: периоды и соответствующие номера семестров
    semesters_config = [
        ("Осень 2024", date(2024, 9, 1), date(2024, 12, 24), [1, 3, 5]),
        ("Весна 2025", date(2025, 2, 9), date(2025, 6, 5),  [2, 4, 6]),
        ("Осень 2025", date(2025, 9, 1), date(2025, 12, 24), [1, 3, 5]),
        ("Весна 2026", date(2026, 2, 9), date(2026, 6, 5),  [2, 4, 6]),
    ]

    all_schedules = []
    all_attendance = []

    lecture_by_course = {}
    for lec in data['lectures']:
        lecture_by_course.setdefault(str(lec['course_id']), []).append(lec['id'])

    for semester_name, start_d, end_d, active_semesters in semesters_config:
        print(f"Генерация расписания для {semester_name} ({start_d} – {end_d})")

        # отбираем лекции, чьи курсы принадлежат одному из активных семестров
        active_lecture_ids = []
        for course in data['lecture_courses']:
            if course['semester'] in active_semesters:
                active_lecture_ids.extend(lecture_by_course.get(str(course['id']), []))

        if not active_lecture_ids:
            continue
        
        sched = generate_schedules_for_semester(start_d, end_d, active_lecture_ids, group_ids)
        att = generate_attendance(sched, data['students'])
        all_schedules.extend(sched)
        all_attendance.extend(att)

    data['schedules'] = all_schedules
    data['attendance'] = all_attendance

    fill_postgresql(data)

    print("Данные сгенерированы и загружены в PostgreSQL.")