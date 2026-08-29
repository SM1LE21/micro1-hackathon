"""Configuration for atlaslane."""

from celery.schedules import crontab

DATABASE_URL = "sqlite:///./atlaslane.db"
PAGE_SIZE = 50
SESSION_COOKIE_NAME = "atlaslane_session"
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
AWS_REGION = "eu-central-1"

CELERYBEAT_SCHEDULE = {
    "purge-closed-accounts": {
        "task": "jobs.purge.purge_closed_accounts",
        "schedule": crontab(minute="0", hour="4"),
    },
}
