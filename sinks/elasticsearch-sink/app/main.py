import os, json
from elasticsearch import Elasticsearch
from confluent_kafka import Consumer

es = Elasticsearch(
    hosts=[f"http://{os.getenv('ES_HOST', 'elasticsearch')}:{os.getenv('ES_PORT', '9200')}"],
    basic_auth=(os.getenv('ES_USER', 'elastic'), os.getenv('ES_PASSWORD', 'elastic_pass123')),
    verify_certs=False
)

INDEX = os.getenv('ES_INDEX', 'materials')

# создание индекса с маппингом, если его нет
if not es.indices.exists(index=INDEX):
    with open('mapping.json', 'r') as f:
        es.indices.create(index=INDEX, body=json.load(f))

# подписки на топики
topics = [
    'dbserver.public.lecture_material',
    'dbserver.public.lecture',
    'dbserver.public.lecture_course',
    'dbserver.public.specialty'
]

consumer = Consumer({
    'bootstrap.servers': os.getenv('KAFKA_BROKER', 'kafka:9092'),
    'group.id': 'elasticsearch-sink',
    'auto.offset.reset': 'earliest'
})
consumer.subscribe(topics)

# Кэш состояний
lectures = {}        # lecture_id -> { course_id, ... }
courses = {}         # course_id   -> { name, specialty_id }
specialties = {}     # specialty_id -> { name }

print("Elasticsearch sink started (multi-topic join)...")
while True:
    msg = consumer.poll(1.0)
    if msg is None:
        continue
    if msg.error():
        print(f"Consumer error: {msg.error()}")
        continue

    topic = msg.topic()
    value = json.loads(msg.value().decode('utf-8'))
    payload = value.get('payload', {})
    op = payload.get('op')
    after = payload.get('after', {}) or {}
    before = payload.get('before', {}) or {}

    # ── Обновление кэша ──
    if topic == 'dbserver.public.lecture':
        if op in ('c', 'r', 'u'):
            lectures[after['id']] = after
        elif op == 'd':
            lectures.pop(before['id'], None)
        # При любом изменении лекции пересчитываем все связанные материалы
        # (для простоты переиндексируем все материалы этой лекции)
        continue   # индексация триггерится при получении материала

    elif topic == 'dbserver.public.lecture_course':
        if op in ('c', 'r', 'u'):
            courses[after['id']] = after
        elif op == 'd':
            courses.pop(before['id'], None)
        # При изменении курса тоже пересчитаем связанные материалы,
        # которые придут позже или перезапросим (см. ниже)
        continue

    elif topic == 'dbserver.public.specialty':
        if op in ('c', 'r', 'u'):
            specialties[after['id']] = after
        elif op == 'd':
            specialties.pop(before['id'], None)
        continue

    # ── Обработка lecture_material ──
    if topic == 'dbserver.public.lecture_material':
        material_id = after.get('id') or before.get('id')
        if not material_id:
            continue

        if op == 'd':
            # Удаление из ES
            es.delete(index=INDEX, id=material_id, ignore=[404])
            print(f"ES deleted: {material_id}")
            consumer.commit(msg)
            continue

        # Сборка полного документа
        lecture = lectures.get(after.get('lecture_id'))
        if not lecture:
            # Если лекция ещё не пришла, отложим (или пропустим)
            # В рабочем варианте можно запросить из PG или повторить позже
            continue

        course = courses.get(lecture.get('course_id'))
        if not course:
            continue

        specialty_name = specialties.get(course.get('specialty_id'), {}).get('name', '')

        metadata_raw = after.get('metadata', {})
        if isinstance(metadata_raw, str):
            try:
                metadata = json.loads(metadata_raw)
            except json.JSONDecodeError:
                metadata = {}
        else:
            metadata = metadata_raw

        doc = {
            'id': after['id'],
            'lecture_id': after['lecture_id'],
            'title': after.get('title', ''),
            'content_text': after.get('content_text', ''),
            'content_type': after.get('content_type', ''),
            'file_url': after.get('file_url', ''),
            'course_name': course.get('name', ''),
            'specialty_name': specialty_name,
            'metadata': metadata,
            'created_at': after.get('created_at', '')
        }

        es.index(index=INDEX, id=after['id'], body=doc)
        print(f"ES indexed: {after['id']}")

    consumer.commit(msg)