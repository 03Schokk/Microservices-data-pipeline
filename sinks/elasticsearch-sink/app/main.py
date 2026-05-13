from confluent_kafka import Consumer
from elasticsearch import Elasticsearch
import os, json

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

print("Elasticsearch sink started...")
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
    before = payload.get('before', {})
    after = payload.get('after', {})

    # Обновление кэша лекций
    if topic == 'dbserver.public.lecture':
        if op in ('c', 'r', 'u'):
            lectures[after['id']] = after
        elif op == 'd':
            lectures.pop(before['id'], None)
        continue # только кэширование, индексация позже
    
    # Обновление кэша курсов
    elif topic == 'dbserver.public.lecture_course':
        if op in ('c', 'r', 'u'):
            courses[after['id']] = after
        elif op == 'd':
            courses.pop(before['id'], None)
        continue
    
    # Обновление кэша специальностей
    elif topic == 'dbserver.public.specialty':
        if op in ('c', 'r', 'u'):
            specialties[after['id']] = after
        elif op == 'd':
            specialties.pop(before['id'], None)
        continue
    
    # Индексация материала
    if topic == 'dbserver.public.lecture_material':
        material_id = after.get('id') or before.get('id')
        if not material_id:
            continue

        if op == 'd':
            es.delete(index=INDEX, id=material_id, ignore=[404])
            print(f"ElasticSearch deleted: {material_id}")
            consumer.commit(msg)
            continue

        lecture = lectures.get(after.get('lecture_id'))
        if not lecture:
            continue # лекция ещё не пришла - пропуск

        course = courses.get(lecture.get('course_id'))
        if not course:
            continue # курс ещё не пришёл - пропуск

        specialty_name = specialties.get(course.get('specialty_id'), {}).get('name', '')

        metadata_raw = after.get('metadata', {})
        if isinstance(metadata_raw, str):
            try:
                metadata = json.loads(metadata_raw) # из JSONB в string
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
        print(f"ElasticSearch indexed: {after['id']}")

    consumer.commit(msg)