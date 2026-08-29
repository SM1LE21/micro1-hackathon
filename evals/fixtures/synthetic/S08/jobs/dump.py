"""Nightly database dump."""

import json

from db import SessionLocal
from models import User, Document

BACKUP_NAME = "nightly_dump"
DUMP_COLUMNS = ["email", "full_name", "phone"]
DUMP_PATH = f"{BACKUP_NAME}.json"


def write_dump():
    session = SessionLocal()
    rows = []
    for table in (User, Document):
        for record in session.query(table).all():
            rows.append({column: getattr(record, column, None) for column in DUMP_COLUMNS})
    with open(DUMP_PATH, "w") as handle:
        json.dump(rows, handle, default=str)


if __name__ == "__main__":
    write_dump()
