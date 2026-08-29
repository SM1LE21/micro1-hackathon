"""Configuration for tidewharf."""

import os

from celery.schedules import crontab

DATABASE_URL = "sqlite:///./tidewharf.db"
PAGE_SIZE = 50
SESSION_COOKIE_NAME = "tidewharf_session"
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
AWS_REGION = "eu-central-1"
STRIPE_API_KEY = os.environ.get("STRIPE_API_KEY", "")

CELERYBEAT_SCHEDULE = {
    "purge-closed-accounts": {
        "task": "jobs.purge.purge_closed_accounts",
        "schedule": crontab(minute="0", hour="4"),
    },
}
