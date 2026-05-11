import os, json, threading, time
from collections import defaultdict
import pymongo
from confluent_kafka import Consumer

MONGO_HOST = os.getenv('MONGO_HOST', 'mongodb')
MONGO_PORT = int(os.getenv('MONGO_PORT', 27017))
MONGO_USER = os.getenv('MONGO_USER', 'admin')
MONGO_PASSWORD = os.getenv('MONGO_PASSWORD', 'admin123')
MONGO_DB = os.getenv('MONGO_DB', 'testdb')

mongo = pymongo.MongoClient(
    host=MONGO_HOST, port=MONGO_PORT,
    username=MONGO_USER, password=MONGO_PASSWORD
)
db = mongo[MONGO_DB]

# Кеш последних состояний таблиц
state = {
    'university': {},
    'institute': {},
    'department': {},
    'specialty': {},
    'department_specialties': []
}

lock = threading.Lock()

def rebuild_mongo_doc():
    """Строит полный документ университета и сохраняет в коллекцию universities"""
    with lock:
        univ = list(state['university'].values())
        if not univ:
            return
        univ = univ[0]
        univ['_id'] = univ['id']
        # копируем данные
        institutes = []
        for inst in state['institute'].values():
            inst_doc = {**inst, '_id': inst['id']}
            depts = []
            for dept in state['department'].values():
                if dept.get('institute_id') == inst['id']:
                    dept_doc = {**dept, '_id': dept['id']}
                    specialties = []
                    for ds in state['department_specialties']:
                        if ds.get('department_id') == dept['id']:
                            spec = state['specialty'].get(ds['specialty_id'], {})
                            if spec:
                                specialties.append({
                                    'id': spec['id'],
                                    'name': spec['name'],
                                    'code': spec.get('code'),
                                    'degree_level': spec.get('degree_level')
                                })
                    dept_doc['specialties'] = specialties
                    depts.append(dept_doc)
            inst_doc['departments'] = depts
            institutes.append(inst_doc)
        univ['institutes'] = institutes
        db.universities.replace_one({'_id': univ['_id']}, univ, upsert=True)
        print("MongoDB document updated.")

def process_message(topic, payload):
    op = payload.get('op')
    after = payload.get('after', {})
    before = payload.get('before', {})
    table = topic.split('.')[-1]

    with lock:
        if op in ('c', 'r', 'u'):
            if table in ('university', 'institute', 'department', 'specialty'):
                state[table][after['id']] = after
            elif table == 'department_specialties':
                pass # полная пересборка списка
        elif op == 'd':
            if table in ('university', 'institute', 'department', 'specialty'):
                state[table].pop(before['id'], None)
    # перестраиваем при любом изменении
    rebuild_mongo_doc()

consumer = Consumer({
    'bootstrap.servers': os.getenv('KAFKA_BROKER', 'kafka:9092'),
    'group.id': 'mongo-sink',
    'auto.offset.reset': 'earliest'
})
consumer.subscribe([
    'dbserver.public.university',
    'dbserver.public.institute',
    'dbserver.public.department',
    'dbserver.public.specialty',
    'dbserver.public.department_specialties'
])

print("MongoDB sink started...")
while True:
    msg = consumer.poll(1.0)
    if msg is None:
        continue
    if msg.error():
        print(f"Consumer error: {msg.error()}")
        continue
    value = json.loads(msg.value().decode('utf-8'))
    process_message(msg.topic(), value.get('payload', {}))
    consumer.commit(msg)