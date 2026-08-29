"""SQLAlchemy flavour (fixture-generator.md section 3.1).

Modules sit at the repository root, as CASES.md's example manifest and the demo script
expect. The file list is fixed; the knobs decide the contents.
"""

from __future__ import annotations

from emit import Doc, SpecError
from render_common import Rendered, helpers, readme, requirements
from render_jobs import render_jobs
from render_routes import render_module
from render_stores import has_module, render_store
from spec_model import CASCADE_DEFAULT, cascade_tokens, children_of, model_named, privacy_fields, var_of

COLUMN_TYPES = {
    "str": "String(255)",
    "int": "Integer",
    "bool": "Boolean",
    "datetime": "DateTime",
    "json": "JSON",
    "text": "Text",
    "decimal": "Numeric(10, 2)",
}

ENV_CONSTANTS = {
    "redis": 'REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")',
    "stripe": 'STRIPE_API_KEY = os.environ.get("STRIPE_API_KEY", "")',
    "mixpanel": 'MIXPANEL_TOKEN = os.environ.get("MIXPANEL_TOKEN", "")',
    "sendgrid": 'SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY", "")',
    "sentry": 'SENTRY_DSN = os.environ.get("SENTRY_DSN", "")',
    "elasticsearch": 'ELASTICSEARCH_URL = os.environ.get("ELASTICSEARCH_URL", "http://localhost:9200")',
    "pika": 'RABBITMQ_URL = os.environ.get("RABBITMQ_URL", "amqp://localhost")',
}


CRON_FIELDS = ("minute", "hour", "day_of_month", "month_of_year", "day_of_week")


def _crontab(schedule: str) -> str:
    """A five-field cron string as the `crontab(...)` call celery beat takes."""
    fields = schedule.split()
    if len(fields) != len(CRON_FIELDS):
        raise SpecError(f"schedule {schedule!r} is not a five-field cron expression")
    args = ", ".join(f'{name}="{value}"' for name, value in zip(CRON_FIELDS, fields) if value != "*")
    return f"crontab({args})"


def _scheduled_purges(spec: dict) -> list[dict]:
    return [job for job in spec["jobs"] if job["kind"] == "purge" and job["schedule"]]


def _config(spec: dict, r: Rendered) -> None:
    doc = Doc()
    doc.add(f'"""Configuration for {spec["package"]}."""')
    doc.blank()
    env: list[str] = []
    for store in spec["stores"]:
        constant = ENV_CONSTANTS.get(store["client"])
        if constant and constant not in env:
            env.append(constant)
    purges = _scheduled_purges(spec)
    if env:  # stdlib group, only where a constant below needs it
        doc.add("import os")
        doc.blank()
    if purges:
        doc.add("from celery.schedules import crontab")
        doc.blank()
    doc.add(f'DATABASE_URL = "{spec["engine"]}"')
    doc.add("PAGE_SIZE = 50")
    doc.add(f'SESSION_COOKIE_NAME = "{spec["package"]}_session"')
    doc.add("MAX_UPLOAD_BYTES = 5 * 1024 * 1024")
    doc.add('AWS_REGION = "eu-central-1"')
    if env:
        doc.add(*env)
    if purges:
        # The registration a scheduled purge needs to count as erasure after a timer: the
        # decorator alone never says anything runs the job (03-verifier.md section 6.2 req 3).
        doc.blank()
        doc.add("CELERYBEAT_SCHEDULE = {")
        for job in purges:
            module = job["module"][:-3].replace("/", ".")
            doc.add(f'    "{job["name"].replace("_", "-")}": {{')
            doc.add(f'        "task": "{module}.{job["name"]}",')
            doc.add(f'        "schedule": {_crontab(job["schedule"])},')
            doc.add("    },")
        doc.add("}")
    r.put("config.py", doc)


def _db(spec: dict, r: Rendered) -> None:
    doc = Doc()
    doc.add('"""Database engine, session factory and declarative base."""')
    doc.blank()
    imports = ["from sqlalchemy import create_engine"]
    if spec["enforce_sqlite_fk"]:
        imports = ["from sqlalchemy import create_engine, event", "from sqlalchemy.engine import Engine"]
    doc.add(*imports, "from sqlalchemy.orm import declarative_base, sessionmaker")
    doc.blank()
    doc.add("from config import DATABASE_URL")
    doc.blank()
    doc.add(
        "engine = create_engine(DATABASE_URL)",
        "SessionLocal = sessionmaker(bind=engine, autoflush=False)",
        "Base = declarative_base()",
    )
    if spec["enforce_sqlite_fk"]:
        doc.blank(2)
        doc.add(
            '@event.listens_for(Engine, "connect")',
            "def _set_sqlite_pragma(dbapi_connection, connection_record):",
            '    dbapi_connection.execute("PRAGMA foreign_keys=ON")',
        )
    r.put("db.py", doc)


def _column(field: dict) -> str:
    if field["pk"]:
        body = "Integer, primary_key=True"
    else:
        body = COLUMN_TYPES[field["type"]]
        if not field["nullable"]:
            body += ", nullable=False"
    line = f"    {field['name']} = Column({body})"
    return line + (f"  # {field['comment']}" if field["comment"] else "")


def _fk_column(spec: dict, model: dict) -> tuple[str, str]:
    parent = model_named(spec, model["parent"])
    name = f"{var_of(parent)}_id"
    inner = f'"{parent["table"]}.id"'
    if model["ondelete"]:
        inner += f', ondelete="{model["ondelete"]}"'
    return name, f"    {name} = Column(Integer, ForeignKey({inner}))"


def _models(spec: dict, r: Rendered) -> None:
    doc = Doc()
    positive = [m for m in spec["models"] if not m["negative"]]
    types = {COLUMN_TYPES[f["type"]].split("(")[0] for m in positive for f in m["fields"] if not f["pk"]}
    names = sorted({"Column", "Integer"} | types | ({"ForeignKey"} if any(m["parent"] for m in positive) else set()))
    doc.add(f'"""Data models for {spec["package"]}.')
    doc.blank()
    doc.add("One class per table. The schema is created from these definitions by db.py.")
    doc.add('"""')
    doc.blank()
    doc.add("from sqlalchemy import " + ", ".join(names))
    if any(children_of(spec, m["name"]) for m in positive):
        doc.add("from sqlalchemy.orm import relationship")
    doc.blank()
    doc.add("from db import Base")
    for model in positive:
        doc.blank(2)
        declared = doc.add(f"class {model['name']}(Base):")
        doc.add(f'    __tablename__ = "{model["table"]}"')
        for field in model["fields"]:
            line = doc.add(_column(field))
            if field["category"]:
                r.cite_field(field["store"] or model["store"], field["name"], "models.py", line)
        if model["parent"]:
            _, text = _fk_column(spec, model)
            r.subject_link[model["store"]] = ("models.py", doc.add(text))
        else:
            r.subject_link[model["store"]] = ("models.py", declared)
        r.identity[model["store"]] = ("models.py", declared + 1)
        for child in children_of(spec, model["name"]):
            departs = cascade_tokens(child["cascade"]) != cascade_tokens(CASCADE_DEFAULT)
            arg = f', cascade="{child["cascade"]}"' if departs else ""
            doc.add(f'    {child["table"]} = relationship("{child["name"]}"{arg})')
    r.put("models.py", doc)


def _catalog(spec: dict, r: Rendered) -> None:
    negatives = [m for m in spec["models"] if m["negative"]]
    if not negatives:
        return
    doc = Doc()
    doc.add('"""Catalogue tables. No personal data is held here."""')
    doc.blank()
    types = {COLUMN_TYPES[f["type"]].split("(")[0] for m in negatives for f in m["fields"] if not f["pk"]}
    doc.add("from sqlalchemy import " + ", ".join(sorted({"Column", "Integer"} | types)))
    doc.blank()
    doc.add("from db import Base")
    for model in negatives:
        doc.blank(2)
        doc.add(f"class {model['name']}(Base):")
        doc.add(f'    __tablename__ = "{model["table"]}"')
        for field in model["fields"]:
            doc.add(_column(field))
    r.put("catalog.py", doc)


def _app(spec: dict, r: Rendered) -> None:
    doc = Doc()
    sentry = next((s for s in spec["stores"] if s["client"] == "sentry"), None)
    log = next((s for s in spec["stores"] if s["client"] == "logging"), None)
    doc.add(f'"""Application object for {spec["package"]}."""')
    doc.blank()
    if sentry:
        doc.add("import sentry_sdk")
        doc.blank()
    modules = sorted({m.split("/")[-1][:-3] for m in _route_modules(spec)})
    doc.add(f"from api import {', '.join(modules)}")
    if sentry:
        doc.add("from config import SENTRY_DSN")
    if log:
        doc.add(f"from middleware import {log['writes_from']}")
    doc.blank()
    if sentry:
        doc.add("SENTRY_DEFAULT_FIELDS = [")
        for field in sentry["fields"]:
            line = doc.add(f'    "{field["name"]}",')
            r.cite_field(sentry["name"], field["name"], "app.py", line)
        doc.add("]")
    doc.add(f"ROUTES = [{', '.join(modules)}]")
    if log:
        doc.add(f"MIDDLEWARE = [{log['writes_from']}]")
    if sentry:
        doc.blank(2)
        doc.add(f"def {sentry['writes_from']}():")
        init = doc.add("    sentry_sdk.init(dsn=SENTRY_DSN)")
        doc.blank(2)
        doc.add(f"{sentry['writes_from']}()")
        r.identity[sentry["name"]] = ("app.py", init)
        r.subject_link[sentry["name"]] = ("app.py", init)
    r.put("app.py", doc)


def _route_modules(spec: dict) -> list[str]:
    modules = ["api/account.py"]
    for item in spec["entry_points"] + spec["routes"]:
        module = item["module"]
        if module not in modules:
            modules.append(module)
    return modules


def _privacy(spec: dict, r: Rendered) -> None:
    if not any(e["action"] == "anonymise" for e in spec["entry_points"]):
        return
    doc = Doc()
    doc.add('"""Profile anonymisation."""')
    doc.blank()
    doc.add("import hashlib")
    doc.blank()
    hashed, constant = privacy_fields(spec)
    doc.add('ANONYMISED_NAME = "removed"')
    doc.blank(2)
    doc.add("def anonymize_user(user):")
    doc.add(f"    user.{hashed} = hashlib.sha256(user.{hashed}.encode()).hexdigest()")
    doc.add(f"    user.{constant} = ANONYMISED_NAME")
    r.put("privacy.py", doc)


def render(spec: dict) -> Rendered:
    r = Rendered()
    r.files["README.md"] = readme(spec)
    r.files["requirements.txt"] = requirements(spec)
    _config(spec, r)
    _db(spec, r)
    _models(spec, r)
    _catalog(spec, r)
    for store in spec["stores"]:
        if has_module(store):
            render_store(spec, store, r)
    _privacy(spec, r)
    r.files["api/__init__.py"] = ""
    for module in _route_modules(spec):
        render_module(spec, r, module)
    _app(spec, r)
    render_jobs(spec, r)
    for extra in spec["extra_files"]:
        if extra.get("kind") != "helpers":
            raise SpecError(f"{spec['case']}: extra_files kind {extra.get('kind')!r} has no template")
        r.files[extra["path"]] = helpers(spec)
    return r
