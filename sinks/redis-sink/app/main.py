import os
import json
import redis
from confluent_kafka import Consumer

r = redis.Redis(
    host=os.getenv('REDIS_HOST', 'redis'),
    port=int(os.getenv('REDIS_PORT', 6379)),
    decode_responses=True
)

consumer = Consumer({
    'bootstrap.servers': os.getenv('KAFKA_BROKER', 'kafka:9092'),
    'group.id': 'redis-sink',
    'auto.offset.reset': 'earliest'
})
consumer.subscribe(['dbserver.public.student'])

print("Redis sink started, waiting for messages...")
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
    before = payload.get('before', {})

    card = after.get('student_card_number') or before.get('student_card_number')
    if not card:
        continue

    if op in ('c', 'r', 'u'):
        r.hset(f"student:{card}", mapping=after)
        print(f"Redis updated: student:{card}")
    elif op == 'd':
        r.delete(f"student:{card}")
        print(f"Redis deleted: student:{card}")

    consumer.commit(msg)