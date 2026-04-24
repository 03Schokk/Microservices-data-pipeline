"""
lab123_service - db_config.py
"""

import os

POSTGRES_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', 'postgresql'),
    'port': int(os.getenv('POSTGRES_PORT', 5432)),
    'database': os.getenv('POSTGRES_DB', 'testdb'),
    'user': os.getenv('POSTGRES_USER', 'admin'),
    'password': os.getenv('POSTGRES_PASSWORD', 'admin123')
}

REDIS_CONFIG = {
    'host': os.getenv('REDIS_HOST', 'redis'),
    'port': int(os.getenv('REDIS_PORT', 6379)),
    'db': 0,
    'decode_responses': True
}

MONGO_CONFIG = {
    'host': os.getenv('MONGO_HOST', 'mongodb'),
    'port': int(os.getenv('MONGO_PORT', 27017)),
    'username': os.getenv('MONGO_USER', 'admin'),
    'password': os.getenv('MONGO_PASSWORD', 'admin123'),
    'database': os.getenv('MONGO_DB', 'testdb'),
    'authSource': 'admin'
}

NEO4J_CONFIG = {
    'uri': f"bolt://{os.getenv('NEO4J_HOST', 'neo4j')}:{os.getenv('NEO4J_PORT', 7687)}",
    'user': os.getenv('NEO4J_USER', 'neo4j'),
    'password': os.getenv('NEO4J_PASSWORD', 'password123')
}

ELASTICSEARCH_CONFIG = {
    'host': os.getenv('ES_HOST', 'elasticsearch'),
    'port': int(os.getenv('ES_PORT', 9200)),
    'user': os.getenv('ES_USER', 'elastic'),
    'password': os.getenv('ES_PASSWORD', 'elastic_pass123')
}