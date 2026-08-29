"""Scheduled purge of closed users."""

from datetime import datetime, timedelta, timezone

from celery import shared_task

from db import SessionLocal
from models import User

RETENTION_DAYS = 30


@shared_task
def purge_closed_accounts():
    session = SessionLocal()
    cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)
    for row in session.query(User).filter(User.deleted_at < cutoff).all():
        session.delete(row)
    session.commit()


if __name__ == "__main__":
    purge_closed_accounts()
