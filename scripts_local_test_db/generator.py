import os, uuid, random, json, time, shutil, subprocess
from datetime import datetime, timedelta, date
from faker import Faker
import psycopg2
from psycopg2.extras import execute_values
import redis
import pymongo
from neo4j import GraphDatabase
from elasticsearch import Elasticsearch, helpers

# Инициализация Faker для данных
fake = Faker('ru_RU')

# ==================== КОНФИГУРАЦИЯ ПОДКЛЮЧЕНИЙ ====================

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
    'port': 12000,
    'user': 'elastic',
    'password': 'elastic_pass123'
}

# ==================== ОЧИСТКА VOLUMES У КОНТЕЙНЕРОВ ====================

def clear_host_volumes():
    """Полное удаление и пересоздание папок на диске D, соответствующих volumes"""
    folders = (
        "D:/Docker/Containers/database/redis",
        "D:/Docker/Containers/database/logs/redis",
        "D:/Docker/Containers/database/mongodb",
        "D:/Docker/Containers/database/logs/mongodb",
        "D:/Docker/Containers/database/neo4j/data",
        "D:/Docker/Containers/database/neo4j/logs",
        "D:/Docker/Containers/database/neo4j/import",
        "D:/Docker/Containers/database/neo4j/plugins",
        "D:/Docker/Containers/database/elasticsearch/data",
        "D:/Docker/Containers/database/logs/elasticsearch",
        "D:/Docker/Containers/database/postgresql/data",
        "D:/Docker/Containers/database/logs/postgresql"
    )
    for folder in folders:
        if os.path.exists(folder):
            shutil.rmtree(folder)
        os.makedirs(folder, exist_ok=True)
        print(f"Очищена и создана папка: {folder}")

# ==================== ПРОВЕРКА СОСТОЯНИЙ КОНТЕЙНЕРОВ ПОСЛЕ ЗАПУСКА ====================

def wait_for_postgres():
    print("Ожидание PostgreSQL...")
    config = POSTGRES_CONFIG.copy()
    for attempt in range(60):
        try:
            conn = psycopg2.connect(**config)
            conn.close()
            print("PostgreSQL готов")
            return
        except Exception as e:
            print(f"Попытка {attempt+1}: {e}")
            time.sleep(2)
    print("\nPostgreSQL не запустился. Логи:")
    subprocess.run(["docker", "logs", "postgresql-server", "--tail", "50"])
    raise Exception("PostgreSQL не запустился")

def wait_for_redis():
    print("Ожидание Redis...")
    r = redis.Redis(**REDIS_CONFIG)
    for attempt in range(60):
        try:
            if r.ping():
                print("Redis готов")
                return
        except Exception as e:
            print(f"Попытка {attempt+1}: {e}")
        time.sleep(2)
    print("\nRedis не запустился. Логи:")
    subprocess.run(["docker", "logs", "redis-server", "--tail", "50"])
    raise Exception("Redis не запустился")

def wait_for_mongodb():
    print("Ожидание MongoDB...")
    for attempt in range(60):
        try:
            client = pymongo.MongoClient(
                host=MONGO_CONFIG['host'],
                port=MONGO_CONFIG['port'],
                username=MONGO_CONFIG['username'],
                password=MONGO_CONFIG['password'],
                authSource=MONGO_CONFIG.get('authSource', 'admin'),
                serverSelectionTimeoutMS=2000
            )
            client.admin.command('ping')
            client.close()
            print("MongoDB готова")
            return
        except Exception as e:
            print(f"Попытка {attempt+1}: {e}")
            time.sleep(2)
    print("\nMongoDB не запустилась. Последние логи контейнера:")
    subprocess.run(["docker", "logs", "mongodb-server", "--tail", "50"])
    raise Exception("MongoDB не запустилась")

def wait_for_neo4j():
    print("Ожидание Neo4j...")
    for attempt in range(60):
        try:
            driver = GraphDatabase.driver(NEO4J_CONFIG['uri'], auth=(NEO4J_CONFIG['user'], NEO4J_CONFIG['password']))
            driver.verify_connectivity()
            driver.close()
            print("Neo4j готов")
            return
        except Exception as e:
            print(f"Попытка {attempt+1}: {e}")
        time.sleep(2)
    print("\nNeo4j не запустился. Логи:")
    subprocess.run(["docker", "logs", "neo4j-server", "--tail", "50"])
    raise Exception("Neo4j не запустился")

def wait_for_elasticsearch():
    print("Ожидание Elasticsearch...")
    es = Elasticsearch(
        hosts=[f'http://{ELASTICSEARCH_CONFIG["host"]}:{ELASTICSEARCH_CONFIG["port"]}'],
        basic_auth=(ELASTICSEARCH_CONFIG['user'], ELASTICSEARCH_CONFIG['password']),
        verify_certs=False,
        request_timeout=60
    )
    for attempt in range(60):
        try:
            if es.ping():
                print("Elasticsearch готов")
                return
        except Exception as e:
            print(f"Попытка {attempt+1}: {e}")
        time.sleep(2)
    print("\nElasticsearch не запустился. Логи:")
    subprocess.run(["docker", "logs", "elasticsearch-server", "--tail", "50"])
    raise Exception("Elasticsearch не запустился")

# ==================== ПЕРЕЗАПУСК КОНТЕЙНЕРОВ ПЕРЕД ЗАПОЛНЕНИЕМ ====================

def reset_containers():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    compose_file = os.path.join(script_dir, "..", "docker-compose.yaml")
    try:
        print("Останавливаем контейнеры и удаляем volumes...")
        subprocess.run(["docker-compose", "-f", compose_file, "down", "-v"], check=True)
        
        print("Очищаем физические папки на диске D:/...")
        clear_host_volumes()
        
        print("Запускаем контейнеры заново...")
        subprocess.run(["docker-compose", "-f", compose_file, "up", "-d"], check=True)

        print("Ожидаем 15 секунд, чтобы контейнеры настроились...")
        time.sleep(15)
        print("Ожидание завершено, проверяем подключения к контейнерам")

        # Ожидаем готовности всех сервисов
        wait_for_postgres()
        wait_for_redis()
        wait_for_mongodb()
        wait_for_neo4j()
        wait_for_elasticsearch()

        print("Контейнеры готовы к работе")
    except subprocess.CalledProcessError as e:
        print(f"Ошибка Docker Compose: {e}")
        raise

# ==================== ГЕНЕРАЦИЯ ТЕСТОВЫХ ДАННЫХ ====================

def generate_universities():
    """Генерация университетов"""
    return [{
        'id': uuid.uuid4(),
        'name': 'МИРЭА - Российский технологический университет',
        'short_name': 'РТУ МИРЭА',
        'address': 'просп. Вернадского, д. 78, Москва',
        'website': 'https://mirea.ru',
        'founded_year': 1947
    }]

def generate_institutes(university_id):
    """Генерация институтов"""
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
    """Генерация кафедр"""
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
    """Генерация специальностей"""
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
    """Связи кафедр со специальностями"""
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
    """Генерация курсов лекций"""
    courses = []
    course_names = [
        'Базы данных', 'Алгоритмы и структуры данных', 'Операционные системы',
        'Сети ЭВМ', 'Объектно-ориентированное программирование',
        'Веб-технологии', 'Искусственный интеллект', 'Машинное обучение',
        'Криптография', 'Тестирование ПО', 'DevOps практики', 'Облачные вычисления'
    ]
    for spec_id in specialty_ids:
        for semester in range(1, 8, 2): # потому что осенне-зимние семестры
            for course_name in random.sample(course_names, k=2):
                courses.append({
                    'id': uuid.uuid4(),
                    'specialty_id': spec_id,
                    'name': course_name,
                    'description': f'Курс "{course_name}"',
                    'semester': semester,
                    'total_hours': random.randint(72, 144),
                    'lecture_hours': random.randint(32, 64),
                    'practice_hours': random.randint(16, 32),
                    'lab_hours': random.randint(16, 32)
                })
    return courses

def generate_lectures(course_ids):
    """Генерация лекций"""
    lectures = []
    for course_id in course_ids:
        for i in range(1, random.randint(8, 16)):
            lecture_type = random.choice(['Лекция', 'Практика', 'Лабораторная'])
            lectures.append({
                'id': uuid.uuid4(),
                'course_id': course_id,
                'title': f'Занятие {i}: {fake.sentence(nb_words=5)}',
                'annotation': fake.paragraph(),
                'lecture_type': lecture_type,
                'computer_type': random.choice(['Требуется проектор', 'Дополнительная техника не требуется']) if lecture_type == 'Лекция' else random.choice(['Требуется компьютерный класс с ОС Windows', 'Требуется компьютерный класс с ОС Linux', 'Требуется проектор', 'Дополнительная техника не требуется']),
                'order_number': i,
                'duration_minutes': 90
            })
    return lectures

def generate_lecture_materials(lecture_ids):
    """Генерация материалов лекций"""
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
    """Генерация студенческих групп"""
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
    """Генерация 1000 студентов"""
    students = []
    for i in range(1000):
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
            'enrollment_date': fake.date_between(start_date='-3y', end_date='today'),
            'status': random.choice(['Активный', 'Академ'])
        })
    return students

def generate_schedules(lecture_ids, group_ids):
    """Генерация расписания"""
    schedules = []
    
    start_date = date(2024, 9, 1)
    end_date = date(2024, 12, 24)

    current_date = start_date
    while current_date <= end_date:
        for lecture_id in random.sample(lecture_ids, k=min(20, len(lecture_ids))):
            for group_id in random.sample(group_ids, k=min(5, len(group_ids))):
                if random.random() > 0.3:
                    start_time = datetime.strptime(f"{random.randint(9, 17)}:{random.choice(['00', '30'])}", "%H:%M").time()
                    end_time = datetime.strptime(f"{start_time.hour + 1}:{start_time.minute}", "%H:%M").time()
                    schedules.append({
                        'id': uuid.uuid4(),
                        'lecture_id': lecture_id,
                        'group_id': group_id,
                        'scheduled_date': current_date,
                        'week_start_date': current_date,
                        'start_time': start_time,
                        'end_time': end_time,
                        'classroom': f'{random.choice(["А", "Б", "В", "Г", "Д"])}-{random.randint(100, 500)}',
                        'teacher_name': fake.name(),
                        'status': random.choice(['Отменено', 'Завершено'])
                    })
        current_date += timedelta(days=7)
    
    return schedules

def generate_attendance(schedules, students):
    """Генерация посещаемости: для каждого студента из группы и каждого занятия создаётся запись."""
    attendance = []

    # Группируем студентов по группам для быстрого доступа
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

# ==================== ЗАПОЛНЕНИЕ POSTGRESQL ====================

def create_tables_postgresql():
    """Создание таблиц PostgreSQL с партиционированием attendance"""
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
    
    # Таблица attendance с партиционированием
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
    
    # Создание партиций для attendance на каждый месяц 2024 года
    start_date = date(2024, 1, 1)
    end_date = date(2024, 12, 24)
    current = start_date

    while current <= end_date:
        # меняем день месяца на 28 -> + 4 дня для перехода в следующий месяц -> меняем в нём день на первый
        next_month = (current.replace(day=28) + timedelta(days=4)).replace(day=1)
        partition_name = f"attendance_{current.year}_{current.month:02d}"

        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {partition_name} PARTITION OF attendance
            FOR VALUES FROM ('{current.isoformat()}') TO ('{next_month.isoformat()}')
        """)

        current = next_month

    cur.close()
    conn.close()
    print("Таблицы PostgreSQL созданы")

def fill_postgresql(data):
    conn = psycopg2.connect(**POSTGRES_CONFIG)
    conn.autocommit = True
    cur = conn.cursor()

    now = datetime.now()
    
    # university
    execute_values(
        cur,
        """INSERT INTO university (id, name, short_name, address, website, founded_year, created_at, updated_at) VALUES %s""",
        [(str(u['id']), u['name'], u['short_name'], u['address'], u['website'], u['founded_year'], now, now) for u in data['universities']]
    )
    print(f"Заполнено university: {len(data['universities'])}")
    
    # institute
    execute_values(
        cur, 
        """INSERT INTO institute (id, university_id, name, short_name, dean, created_at, updated_at) VALUES %s""",
        [(str(i['id']), str(i['university_id']), i['name'], i['short_name'], i['dean'], now, now) for i in data['institutes']]
    )
    print(f"Заполнено institute: {len(data['institutes'])}")
    
    # department
    execute_values(
        cur,
        """INSERT INTO department (id, institute_id, name, short_name, head, room, created_at, updated_at) VALUES %s""", 
        [(str(d['id']), str(d['institute_id']), d['name'], d['short_name'], d['head'], d['room'], now, now) for d in data['departments']]
    )
    print(f"Заполнено department: {len(data['departments'])}")
    
    # specialty
    execute_values(
        cur,
        """INSERT INTO specialty (id, name, code, degree_level, duration_years, created_at, updated_at) VALUES %s""",
        [(str(s['id']), s['name'], s['code'], s['degree_level'], s['duration_years'], now, now) for s in data['specialties']]
    )
    print(f"Заполнено specialty: {len(data['specialties'])}")
    
    # department_specialties
    execute_values(
        cur,
        """INSERT INTO department_specialties (id, department_id, specialty_id, is_primary, created_at) VALUES %s""",
        [(str(ds['id']), str(ds['department_id']), str(ds['specialty_id']), ds['is_primary'], now) for ds in data['department_specialties']]
    )
    print(f"Заполнено department_specialties: {len(data['department_specialties'])}")
    
    # lecture_course
    execute_values(
        cur,
        """INSERT INTO lecture_course (id, specialty_id, name, description, semester, total_hours, lecture_hours, practice_hours, lab_hours, created_at, updated_at) VALUES %s""",
        [(str(lc['id']), str(lc['specialty_id']), lc['name'], lc['description'], lc['semester'], lc['total_hours'], lc['lecture_hours'], lc['practice_hours'], lc['lab_hours'], now, now) for lc in data['lecture_courses']]
    )
    print(f"Заполнено lecture_course: {len(data['lecture_courses'])}")
    
    # lecture
    execute_values(
        cur,
        """INSERT INTO lecture (id, course_id, title, annotation, lecture_type, computer_type, order_number, duration_minutes, created_at, updated_at) VALUES %s""",
        [(str(l['id']), str(l['course_id']), l['title'], l['annotation'], l['lecture_type'], l['computer_type'], l['order_number'], l['duration_minutes'], now, now) for l in data['lectures']]
    )
    print(f"Заполнено lecture: {len(data['lectures'])}")
    
    # lecture_material
    execute_values(
        cur,
        """INSERT INTO lecture_material (id, lecture_id, content_type, title, content_text, file_url, metadata, created_at, updated_at) VALUES %s""", 
        [(str(m['id']), str(m['lecture_id']), m['content_type'], m['title'], m['content_text'], m['file_url'], json.dumps(m['metadata']), now, now) for m in data['lecture_materials']]
    )
    print(f"Заполнено lecture_material: {len(data['lecture_materials'])}")
    
    # student_group
    execute_values(
        cur,
        """INSERT INTO student_group (id, specialty_id, name, enrollment_year, curator, created_at, updated_at) VALUES %s""",
        [(str(g['id']), str(g['specialty_id']), g['name'], g['enrollment_year'], g['curator'], now, now) for g in data['student_groups']]
    )
    print(f"Заполнено student_group: {len(data['student_groups'])}")
    
    # student
    execute_values(
        cur,
        """INSERT INTO student (id, group_id, first_name, last_name, patronymic, email, phone, student_card_number, enrollment_date, status, created_at, updated_at) VALUES %s""",
        [(str(s['id']), str(s['group_id']), s['first_name'], s['last_name'], s['patronymic'], s['email'], s['phone'], s['student_card_number'], s['enrollment_date'], s['status'], now, now) for s in data['students']]
    )
    print(f"Заполнено student: {len(data['students'])}")
    
    # schedule
    execute_values(
        cur,
        """INSERT INTO schedule (id, lecture_id, group_id, scheduled_date, week_start_date, start_time, end_time, classroom, teacher_name, status, created_at, updated_at) VALUES %s""",
        [(str(sch['id']), str(sch['lecture_id']), str(sch['group_id']), sch['scheduled_date'], sch['week_start_date'], sch['start_time'], sch['end_time'], sch['classroom'], sch['teacher_name'], sch['status'], now, now) for sch in data['schedules']]
    )
    print(f"Заполнено schedule: {len(data['schedules'])}")
    
    # attendance
    execute_values(
        cur,
        """INSERT INTO attendance (id, week_start_date, schedule_id, student_id, marked_at, marked_by, note, created_at) VALUES %s""",
        [(str(a['id']), a['week_start_date'], str(a['schedule_id']), str(a['student_id']), a['marked_at'], a['marked_by'], a['note'], now) for a in data['attendance']]
    )
    print(f"Заполнено attendance: {len(data['attendance'])}")
    
    cur.close()
    conn.close()

# ==================== ЗАПОЛНЕНИЕ REDIS ====================

def fill_redis(students):
    try:
        r = redis.Redis(**REDIS_CONFIG)
        pipe = r.pipeline()
        for student in students:
            key = f"student:{student['student_card_number']}"
            value = {
                'id': str(student['id']),
                'first_name': student['first_name'],
                'last_name': student['last_name'],
                'patronymic': student['patronymic'],
                'email': student['email'],
                'phone': student['phone'],
                'student_card_number': student['student_card_number'],
                'group_id': str(student['group_id']),
                'enrollment_date': student['enrollment_date'].isoformat(),
                'status': student['status']
            }
            pipe.hset(key, mapping=value)
            pipe.expire(key, 7200)
            if len(pipe) >= 100:
                pipe.execute()
                pipe = r.pipeline()
        pipe.execute()
        print(f"Заполнено Redis: {len(students)} студентов")
    except Exception as e:
        print(f"Ошибка заполнения Redis: {e}")

# ==================== ЗАПОЛНЕНИЕ MONGODB ====================

def fill_mongodb(data):
    try:
        client = pymongo.MongoClient(
            host=MONGO_CONFIG['host'],
            port=MONGO_CONFIG['port'],
            username=MONGO_CONFIG['username'],
            password=MONGO_CONFIG['password']
        )
        db = client[MONGO_CONFIG['database']]
        
        # Создаём денормализованную структуру
        university = data['universities'][0]
        institutes = []
        
        for inst in data['institutes']:
            departments = [d for d in data['departments'] if d['institute_id'] == inst['id']]
            departments_list = []

            for dept in departments:
                dept_specs = [ds for ds in data['department_specialties'] if ds['department_id'] == dept['id']]
                specialties_for_dept = []

                for ds in dept_specs:
                    specialty = next((s for s in data['specialties'] if s['id'] == ds['specialty_id']), None)

                    if specialty:
                        specialties_for_dept.append({
                            'id': str(specialty['id']),
                            'name': specialty['name'],
                            'code': specialty['code'],
                            'degree_level': specialty['degree_level']
                        })
                
                departments_list.append({
                    '_id': str(dept['id']),
                    'institute_id': str(inst['id']),
                    'name': dept['name'],
                    'short_name': dept['short_name'],
                    'head': dept['head'],
                    'room': dept['room'],
                    'specialties': specialties_for_dept
                })
            
            institutes.append({
                '_id': str(inst['id']),
                'university_id': str(university['id']),
                'name': inst['name'],
                'short_name': inst['short_name'],
                'dean': inst['dean'],
                'departments': departments_list
            })
        
        mongo_doc = {
            '_id': str(university['id']),
            'name': university['name'],
            'short_name': university['short_name'],
            'address': university['address'],
            'website': university['website'],
            'founded_year': university['founded_year'],
            'institutes': institutes
        }
        
        db.universities.insert_one(mongo_doc)
        
        print(f"Заполнено MongoDB: 1 документ университета")
        client.close()
    except Exception as e:
        print(f"Ошибка заполнения MongoDB: {e}")

# ==================== ЗАПОЛНЕНИЕ NEO4J ====================

def fill_neo4j(data):
    """Заполнение Neo4j графом посещений"""
    try:
        driver = GraphDatabase.driver(NEO4J_CONFIG['uri'], auth=(NEO4J_CONFIG['user'], NEO4J_CONFIG['password']))
        
        with driver.session() as session:
            for group in data['student_groups']:
                session.run(
                    "CREATE (g:StudentGroup {id: $id, name: $name})",
                    id=str(group['id']), name=group['name']
                )
            
            for student in data['students']:
                session.run(
                    "MATCH (g:StudentGroup {id: $group_id}) "
                    "CREATE (s:Student {id: $id, student_card_number: $card}) "
                    "CREATE (g)-[:HAS_STUDENT]->(s)",
                    group_id=str(student['group_id']),
                    id=str(student['id']),
                    card=student['student_card_number']
                )
            
            for lecture in data['lectures']:
                session.run(
                    "CREATE (l:Lecture {id: $id, type: $type, title: $title})",
                    id=str(lecture['id']),
                    type=lecture['lecture_type'],
                    title=lecture['title']
                )
            
            for schedule in data['schedules']:
                lecture = next((l for l in data['lectures'] if l['id'] == schedule['lecture_id']), None)
                if lecture:
                    session.run(
                        "MATCH (g:StudentGroup {id: $group_id}) "
                        "MATCH (l:Lecture {id: $lecture_id}) "
                        "CREATE (sch:Schedule {id: $id, date: $date, classroom: $classroom, time: $time}) "
                        "CREATE (g)-[:HAS_SCHEDULE]->(sch) "
                        "CREATE (sch)-[:PART_OF]->(l)",
                        group_id=str(schedule['group_id']),
                        lecture_id=str(schedule['lecture_id']),
                        id=str(schedule['id']),
                        date=schedule['scheduled_date'].isoformat(),
                        classroom=schedule['classroom'],
                        time=schedule['start_time'].isoformat()
                    )
        
        driver.close()
        print(f"Заполнено Neo4j: {len(data['student_groups'])} групп, {len(data['students'])} студентов, {len(data['lectures'])} лекций")
    except Exception as e:
        print(f"Ошибка заполнения Neo4j: {e}")

# ==================== ЗАПОЛНЕНИЕ ELASTICSEARCH ====================

def setup_elasticsearch():
    """Создание индекса materials в Elasticsearch"""
    es = Elasticsearch(
        hosts=[f'http://{ELASTICSEARCH_CONFIG["host"]}:{ELASTICSEARCH_CONFIG["port"]}'],
        basic_auth=(ELASTICSEARCH_CONFIG['user'], ELASTICSEARCH_CONFIG['password']),
        verify_certs=False,
        request_timeout=60
    )

    index_body = {
        'settings': {
            'number_of_shards': 1,    # фрагменты индекса
            'number_of_replicas': 0,  # копии фрагментов
            'analysis': {
                'analyzer': {
                    'russian_custom': {
                        'type': 'custom',
                        'tokenizer': 'standard',
                        'filter': ['lowercase', 'russian_stop', 'russian_stemmer'] # разбиение предложения на слова
                    }
                },
                'filter': {
                    'russian_stop': {'type': 'stop', 'stopwords': '_russian_'},   # стоп слова для удаления (частицы, союзы)
                    'russian_stemmer': {'type': 'stemmer', 'language': 'russian'} # корни слов
                }
            }
        },
        'mappings': {
            'properties': {
                'id':            {'type': 'keyword'},
                'lecture_id':    {'type': 'keyword'},
                'title':         {'type': 'text', 'analyzer': 'russian_custom'},
                'content_text':  {'type': 'text', 'analyzer': 'russian_custom'},
                'content_type':  {'type': 'keyword'},
                'file_url':      {'type': 'text', 'index': False},
                'course_name':   {'type': 'text', 'analyzer': 'russian_custom'},
                'specialty_name':{'type': 'text', 'analyzer': 'russian_custom'},
                'metadata':      {'type': 'object', 'enabled': True},
                'created_at':    {'type': 'date'}
            }
        }
    }
    es.indices.create(index='materials', body=index_body)
    print("Elasticsearch индекс materials создан")

def fill_elasticsearch(data):
    """Заполнение Elasticsearch материалами лекций"""
    try:
        es = Elasticsearch(
            hosts=[f'http://{ELASTICSEARCH_CONFIG["host"]}:{ELASTICSEARCH_CONFIG["port"]}'],
            basic_auth=(ELASTICSEARCH_CONFIG['user'], ELASTICSEARCH_CONFIG['password']),
            verify_certs=False,
            request_timeout=60
        )
        if not es.ping():
            print("Не удалось подключиться к Elasticsearch")
            return

        lectures_dict = {str(l['id']): l for l in data['lectures']}
        courses_dict = {str(c['id']): c for c in data['lecture_courses']}
        specialties_dict = {str(s['id']): s for s in data['specialties']}

        count = 0
        for material in data['lecture_materials']:
            lecture = lectures_dict.get(str(material['lecture_id']))
            if not lecture:
                continue

            course = courses_dict.get(str(lecture['course_id']))
            if not course:
                continue

            doc = {
                'id': str(material['id']),
                'lecture_id': str(material['lecture_id']),
                'title': material['title'],
                'content_text': material['content_text'],
                'content_type': material['content_type'],
                'file_url': material['file_url'],
                'course_name': course['name'],
                'specialty_name': specialties_dict.get(str(course['specialty_id']), {}).get('name', ''),
                'metadata': material['metadata'],
                'created_at': datetime.now().isoformat()
            }
            es.index(index='materials', id=str(material['id']), document=doc)
            count += 1

        es.indices.refresh(index='materials')
        print(f"Загружено в Elasticsearch: {count} материалов лекций")
    except Exception as e:
        print(f"Ошибка при заполнении Elasticsearch: {e}")

# ==================== ГЛАВНАЯ ФУНКЦИЯ ====================

def main():
    print("=" * 60)
    print("НАЧАЛО ГЕНЕРАЦИИ ТЕСТОВЫХ ДАННЫХ")
    print("=" * 60)

    print("\n--- ПЕРЕЗАПУСК КОНТЕЙНЕРОВ ДЛЯ ОЧИСТКИ VOLUMES ---")
    reset_containers()

    print("\n--- СОЗДАНИЕ ТАБЛИЦ POSTGRESQL ---")
    create_tables_postgresql()
    
    print("\n--- СОЗДАНИЕ ИНДЕКСА В ELASTICSEARCH ---")
    setup_elasticsearch()

    print("\n--- ГЕНЕРАЦИЯ ТЕСТОВЫХ ДАННЫХ ---")
    
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
    
    data['schedules'] = generate_schedules(lecture_ids, group_ids)
    
    data['attendance'] = generate_attendance(data['schedules'], data['students'])
    
    print(f"Сгенерировано: {len(data['students'])} студентов, {len(data['lectures'])} лекций, {len(data['schedules'])} занятий, {len(data['attendance'])} записей посещаемости")
    
    print("\n--- ЗАПОЛНЕНИЕ POSTGRESQL ---")
    fill_postgresql(data)
    
    print("\n--- ЗАПОЛНЕНИЕ REDIS ---")
    fill_redis(data['students'])
    
    print("\n--- ЗАПОЛНЕНИЕ MONGODB ---")
    fill_mongodb(data)
    
    print("\n--- ЗАПОЛНЕНИЕ NEO4J ---")
    fill_neo4j(data)
    
    print("\n--- ЗАПОЛНЕНИЕ ELASTICSEARCH ---")
    fill_elasticsearch(data)
    
    print("\n" + "=" * 60)
    print("ГЕНЕРАЦИЯ ДАННЫХ ЗАВЕРШЕНА")
    print("=" * 60)

if __name__ == "__main__":
    main()