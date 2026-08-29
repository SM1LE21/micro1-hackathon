"""Nightly database dump."""

import json

from db import SessionLocal
from models import User

BACKUP_NAME = "nightly_backup"
DUMP_COLUMNS = ["email", "full_name"]
DUMP_PATH = f"{BACKUP_NAME}.json"
SCHEDULE = "0 3 * * *"
BACKUP_RETENTION_DAYS = 35


def dump_database():
    session = SessionLocal()
    rows = []
    for table in (User,):
        for record in session.query(table).all():
            rows.append({column: getattr(record, column, None) for column in DUMP_COLUMNS})
    with open(DUMP_PATH, "w") as handle:
        json.dump(rows, handle, default=str)


if __name__ == "__main__":
    dump_database()
