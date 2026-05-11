import os, json
from neo4j import GraphDatabase
from confluent_kafka import Consumer
from datetime import datetime, timedelta, timezone

uri = os.getenv('NEO4J_URI', 'bolt://neo4j:7687')
driver = GraphDatabase.driver(uri, auth=(
    os.getenv('NEO4J_USER', 'neo4j'),
    os.getenv('NEO4J_PASSWORD', 'password123')
))

def process_student_group(after, op):
    with driver.session() as s:
        if op in ('c', 'r', 'u'):
            s.run("MERGE (g:StudentGroup {id: $id}) SET g.name = $name",
                  id=after['id'], name=after['name'])
        elif op == 'd':
            s.run("MATCH (g:StudentGroup {id: $id}) DETACH DELETE g", id=after['id'])

def process_student(after, op):
    with driver.session() as s:
        if op in ('c', 'r', 'u'):
            s.run("MERGE (s:Student {id: $id}) SET s.student_card_number = $card "
                  "WITH s MATCH (g:StudentGroup {id: $gid}) MERGE (g)-[:HAS_STUDENT]->(s)",
                  id=after['id'], card=after['student_card_number'], gid=after['group_id'])
        elif op == 'd':
            s.run("MATCH (s:Student {id: $id}) DETACH DELETE s", id=after['id'])

def process_lecture(after, op):
    with driver.session() as s:
        if op in ('c', 'r', 'u'):
            s.run("MERGE (l:Lecture {id: $id}) SET l.type = $type, l.title = $title",
                  id=after['id'], type=after['lecture_type'], title=after['title'])
        elif op == 'd':
            s.run("MATCH (l:Lecture {id: $id}) DETACH DELETE l", id=after['id'])

def days_to_date_str(days):
    """Преобразует целое число дней от 1970-01-01 в строку YYYY-MM-DD"""
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    return (epoch + timedelta(days=days)).strftime('%Y-%m-%d')

def nano_to_time_str(nano):
    """Преобразует наносекунды от начала дня в строку HH:MM"""
    total_seconds = nano / 1_000_000_000
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    return f"{hours:02d}:{minutes:02d}"

def process_schedule(after, op):
    with driver.session() as s:
        if op in ('c', 'r', 'u'):
            # Конвертируем числовые поля в строки
            date_val = after.get('scheduled_date')
            time_val = after.get('start_time')
            date_str = days_to_date_str(date_val) if isinstance(date_val, int) else date_val
            time_str = nano_to_time_str(time_val) if isinstance(time_val, int) else time_val

            s.run("MERGE (sch:Schedule {id: $id}) "
                  "SET sch.date = $date, sch.classroom = $classroom, sch.time = $time "
                  "WITH sch "
                  "MATCH (g:StudentGroup {id: $gid}) "
                  "MATCH (l:Lecture {id: $lid}) "
                  "MERGE (g)-[:HAS_SCHEDULE]->(sch) "
                  "MERGE (sch)-[:PART_OF]->(l)",
                  id=after['id'], date=date_str, classroom=after['classroom'],
                  time=time_str, gid=after['group_id'], lid=after['lecture_id'])
        elif op == 'd':
            s.run("MATCH (sch:Schedule {id: $id}) DETACH DELETE sch", id=after['id'])

handlers = {
    'dbserver.public.student_group': process_student_group,
    'dbserver.public.student': process_student,
    'dbserver.public.lecture': process_lecture,
    'dbserver.public.schedule': process_schedule
}

consumer = Consumer({
    'bootstrap.servers': os.getenv('KAFKA_BROKER', 'kafka:9092'),
    'group.id': 'neo4j-sink',
    'auto.offset.reset': 'earliest'
})
consumer.subscribe(list(handlers.keys()))

print("Neo4j sink started...")
while True:
    msg = consumer.poll(1.0)
    if msg is None:
        continue
    if msg.error():
        print(f"Consumer error: {msg.error()}")
        continue
    value = json.loads(msg.value().decode('utf-8'))
    payload = value.get('payload', {})
    op = payload.get('op')
    after = payload.get('after', {})
    handler = handlers.get(msg.topic())
    if handler:
        handler(after or payload.get('before', {}), op)
    consumer.commit(msg)