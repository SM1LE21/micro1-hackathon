"""Configuration for tidepool."""

import os

DATABASE_URL = "sqlite:///./tidepool.db"
PAGE_SIZE = 50
SESSION_COOKIE_NAME = "tidepool_session"
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
AWS_REGION = "eu-central-1"
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
ELASTICSEARCH_URL = os.environ.get("ELASTICSEARCH_URL", "http://localhost:9200")
MIXPANEL_TOKEN = os.environ.get("MIXPANEL_TOKEN", "")
