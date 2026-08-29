"""Configuration for civicbeam."""

import os

DATABASE_URL = "sqlite:///./civicbeam.db"
PAGE_SIZE = 50
SESSION_COOKIE_NAME = "civicbeam_session"
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
AWS_REGION = "eu-central-1"
ELASTICSEARCH_URL = os.environ.get("ELASTICSEARCH_URL", "http://localhost:9200")
RABBITMQ_URL = os.environ.get("RABBITMQ_URL", "amqp://localhost")
