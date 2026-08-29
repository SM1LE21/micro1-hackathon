"""Scheduled job modules for the SQLAlchemy flavour (fixture-generator.md section 3.1).

A purge job carries its retention constant and the cutoff arithmetic; a backup job carries
the backup name, the dump columns every inherited field cites, and whatever schedule and
retention constants the knobs asked for.
"""

from __future__ import annotations

from emit import Doc, SpecError
from render_common import Rendered
from spec_model import model_named

def render_jobs(spec: dict, r: Rendered) -> None:
    if not spec["jobs"]:
        return
    r.files["jobs/__init__.py"] = ""
    positive = [m for m in spec["models"] if not m["negative"]]
    for job in spec["jobs"]:
        doc = Doc()
        store = next((s for s in spec["stores"] if s["module"] == job["module"]), None)
        if job["kind"] == "purge":
            target = model_named(spec, job["target"])
            doc.add(f'"""Scheduled purge of closed {target["table"]}."""')
            doc.blank()
            doc.add("from datetime import datetime, timedelta, timezone")
            doc.blank()
            if job["schedule"]:
                doc.add("from celery import shared_task")
                doc.blank()
            doc.add("from db import SessionLocal", f"from models import {target['name']}")
            doc.blank()
            doc.add(f"RETENTION_DAYS = {job['retention_days']}")
            doc.blank(2)
            if job["schedule"]:
                # The cadence itself lives once, in the beat registration config.py carries.
                doc.add("@shared_task")
            doc.add(f"def {job['name']}():")
            doc.add("    session = SessionLocal()")
            doc.add("    cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)")
            doc.add(
                f"    for row in session.query({target['name']})"
                f".filter({target['name']}.{job['filter_field']} < cutoff).all():"
            )
            doc.add("        session.delete(row)")
            doc.add("    session.commit()")
        elif job["kind"] == "backup":
            if store is None:
                raise SpecError(f"{spec['case']}: backup job {job['name']} has no store in {job['module']}")
            doc.add('"""Nightly database dump."""')
            doc.blank()
            doc.add("import json")
            doc.blank()
            doc.add("from db import SessionLocal")
            doc.add("from models import " + ", ".join(m["name"] for m in positive))
            doc.blank()
            identity = doc.add(f'BACKUP_NAME = "{store["name"]}"')
            columns = ", ".join(f'"{f["name"]}"' for f in store["fields"])
            dump = doc.add(f"DUMP_COLUMNS = [{columns}]")
            doc.add('DUMP_PATH = f"{BACKUP_NAME}.json"')
            if job["schedule"]:
                doc.add(f'SCHEDULE = "{job["schedule"]}"')
            if job["retention_days"]:
                doc.add(f"BACKUP_RETENTION_DAYS = {job['retention_days']}")
            doc.blank(2)
            doc.add(f"def {job['name']}():")
            doc.add("    session = SessionLocal()")
            doc.add("    rows = []")
            tables = ", ".join(m["name"] for m in positive)
            doc.add(f"    for table in ({tables}{',' if len(positive) == 1 else ''}):")
            doc.add("        for record in session.query(table).all():")
            doc.add("            rows.append({column: getattr(record, column, None) for column in DUMP_COLUMNS})")
            doc.add('    with open(DUMP_PATH, "w") as handle:')
            doc.add("        json.dump(rows, handle, default=str)")
            r.identity[store["name"]] = (job["module"], identity)
            r.subject_link[store["name"]] = (job["module"], dump)
            for field in store["fields"]:
                r.cite_field(store["name"], field["name"], job["module"], dump)
        else:
            raise SpecError(f"{spec['case']}: unknown job kind {job['kind']!r}")
        doc.blank(2)
        doc.add('if __name__ == "__main__":', f"    {job['name']}()")
        r.put(job["module"], doc)
