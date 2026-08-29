"""Spec loading and defaults (fixture-generator.md section 2).

Every key gets its documented default here, so the renderers read a fully populated dict
and never guess. Knobs the ten frozen specs do not use are refused loudly rather than
rendered wrongly: section 9 lists them as having no fixture behind them, and a silent
half-implementation would put a wrong repository behind a declared verdict.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import yaml

from emit import SpecError

FIELD_TYPES = {"str", "int", "bool", "datetime", "json", "text", "image", "decimal"}
CATEGORIES = {"identifier", "contact", "financial", "behavioural", "free_text_may_contain", "technical"}
STORE_KINDS = {"object_storage", "cache", "search_index", "queue", "third_party", "log", "backup"}
CLIENTS = {"boto3", "redis", "elasticsearch", "pika", "stripe", "sendgrid", "mixpanel", "sentry", "logging", "file"}
ENTRY_KINDS = {"route", "view", "cli", "admin", "task", "signal"}
ACTIONS = {"hard_delete", "soft_delete", "anonymise", "none"}

# SQLAlchemy's own default cascade, and the two tokens that make a relationship a
# propagation edge (framework-behaviour.md section 6 R5).
CASCADE_DEFAULT = "save-update, merge"
DELETE_CASCADE_TOKENS = frozenset({"delete", "all"})

# Knob values with no template behind them (section 9). Rendering them wrongly would put a
# repository behind a declared verdict that does not match it.
UNSUPPORTED = {
    "versioning_declared": lambda v: v is True,
    "sdk_options": lambda v: bool(v),
}

_CLIENT_MODULE = {
    "boto3": "storage.py",
    "redis": "cache.py",
    "elasticsearch": "search.py",
    "pika": "queue.py",
    "stripe": "billing.py",
    "sendgrid": "mail.py",
    "mixpanel": "analytics.py",
    "sentry": "app.py",
    "logging": "middleware.py",
    "file": "jobs/backup.py",
}

# The SDK module each third-party client imports; the store identity is that module
# without its `_sdk` suffix (section 7 rule 1).
VENDOR_MODULE = {"stripe": "stripe", "sentry": "sentry_sdk", "mixpanel": "mixpanel", "sendgrid": "sendgrid"}


def _require(mapping: dict, key: str, where: str):
    if key not in mapping:
        raise SpecError(f"{where}: missing required key {key!r}")
    return mapping[key]


def _plural(name: str) -> str:
    lowered = name.lower()
    return lowered + "es" if lowered.endswith(("s", "x", "z", "ch", "sh")) else lowered + "s"


def _field(raw: dict, where: str) -> dict:
    field = {
        "name": _require(raw, "name", where),
        "type": raw.get("type", "str"),
        "category": raw.get("category"),
        "pk": raw.get("pk", False),
        "comment": raw.get("comment"),
        "nullable": raw.get("nullable", True),
        "store": raw.get("store"),
    }
    if field["type"] not in FIELD_TYPES:
        raise SpecError(f"{where}: unknown field type {field['type']!r}")
    if field["pk"]:
        field["category"] = None
    if field["category"] is not None and field["category"] not in CATEGORIES:
        raise SpecError(f"{where}: unknown category {field['category']!r}")
    return field


def _model(raw: dict, case: str) -> dict:
    name = _require(raw, "name", f"{case} models[]")
    where = f"{case} model {name}"
    table = raw.get("table") or _plural(name)
    model = {
        "name": name,
        "table": table,
        "store": raw.get("store", table),
        "negative": raw.get("negative", False),
        "parent": raw.get("parent"),
        "on_delete": raw.get("on_delete", "CASCADE"),
        "cascade": raw.get("cascade", CASCADE_DEFAULT),
        "ondelete": raw.get("ondelete"),
        "passive_deletes": raw.get("passive_deletes", False),
        "fields": [_field(f, where) for f in raw.get("fields", [])],
    }
    if model["passive_deletes"]:
        raise SpecError(f"{where}: passive_deletes has no template behind it (section 9)")
    return model


def _store(raw: dict, case: str) -> dict:
    name = _require(raw, "name", f"{case} stores[]")
    where = f"{case} store {name}"
    client = _require(raw, "client", where)
    if client not in CLIENTS:
        raise SpecError(f"{where}: unknown client {client!r}")
    store = {
        "name": name,
        "kind": _require(raw, "kind", where),
        "client": client,
        "module": raw.get("module") or _CLIENT_MODULE[client],
        "fields": [{"name": f["name"], "category": f.get("category")} for f in raw.get("fields", [])],
        "writes_from": raw.get("writes_from"),
        "write_called_by": raw.get("write_called_by", "module"),
        "delete_call": raw.get("delete_call"),
        "delete_called_by": raw.get("delete_called_by"),
        "key_template": raw.get("key_template"),
        "versioning_declared": raw.get("versioning_declared", False),
        "ttl_seconds": raw.get("ttl_seconds"),
        "sdk_options": raw.get("sdk_options") or {},
    }
    if store["kind"] not in STORE_KINDS:
        raise SpecError(f"{where}: unknown store kind {store['kind']!r}")
    if client == "file" and store["kind"] == "object_storage" and store["key_template"]:
        # A Django FileField's key is `upload_to`, derived from <model>.<field> so both halves
        # sit on the column line (section 7 rule 1). A declared template would be discarded.
        raise SpecError(f"{where}: key_template has no effect on a Django file store; remove it")
    for knob, refuse in UNSUPPORTED.items():
        if refuse(store[knob]):
            raise SpecError(f"{where}: {knob} has no template behind it (section 9)")
    return store


def _entry_point(raw: dict, case: str, flavour: str, apps: list[str]) -> dict:
    name = _require(raw, "name", f"{case} entry_points[]")
    where = f"{case} entry point {name}"
    default_module = "api/account.py" if flavour == "sqlalchemy" else f"{apps[0]}/views.py"
    default_via = "session_delete" if flavour == "sqlalchemy" else "model_delete"
    entry = {
        "name": name,
        "kind": raw.get("kind", "route"),
        "module": raw.get("module") or default_module,
        "action": _require(raw, "action", where),
        "deletes_via": raw.get("deletes_via", default_via),
        "calls": list(raw.get("calls", [])),
        "docstring": raw.get("docstring"),
    }
    if entry["kind"] not in ENTRY_KINDS:
        raise SpecError(f"{where}: unknown entry-point kind {entry['kind']!r}")
    if entry["action"] not in ACTIONS:
        raise SpecError(f"{where}: unknown action {entry['action']!r}")
    if entry["deletes_via"] not in {"session_delete", "model_delete"}:
        raise SpecError(f"{where}: deletes_via {entry['deletes_via']!r} has no template (section 9)")
    return entry


def _job(raw: dict, case: str) -> dict:
    name = _require(raw, "name", f"{case} jobs[]")
    job = {
        "name": name,
        "module": raw.get("module") or f"jobs/{name}.py",
        "kind": _require(raw, "kind", f"{case} job {name}"),
        "target": raw.get("target"),
        "method": raw.get("method", "orm_loop"),
        "retention_days": raw.get("retention_days"),
        "schedule": raw.get("schedule"),
        "filter_field": raw.get("filter_field", "deleted_at"),
    }
    if job["method"] != "orm_loop":
        raise SpecError(f"{case} job {name}: method {job['method']!r} has no template (section 9)")
    return job


def _receiver(raw: dict, case: str, apps: list[str]) -> dict:
    name = _require(raw, "name", f"{case} receivers[]")
    receiver = {
        "name": name,
        "signal": raw.get("signal", "post_delete"),
        "sender": raw.get("sender"),
        "module": raw.get("module") or f"{apps[0]}/signals.py",
        "weak": raw.get("weak", True),
        "registered_in": raw.get("registered_in", "apps_ready"),
        "body": raw.get("body", "delete_file"),
    }
    if receiver["registered_in"] != "apps_ready" or not receiver["weak"]:
        raise SpecError(f"{case} receiver {name}: only weak apps_ready receivers have a template (section 9)")
    return receiver


def load_spec(path: Path) -> dict:
    raw_bytes = path.read_bytes()
    raw = yaml.safe_load(raw_bytes.decode("utf-8"))
    case = _require(raw, "case", str(path))
    if case != path.stem:
        raise SpecError(f"{path}: case {case!r} does not equal the filename stem")
    flavour = _require(raw, "flavour", case)
    apps = list(raw.get("apps", []))
    if flavour == "django" and not apps:
        raise SpecError(f"{case}: django flavour needs apps[]")
    spec = {
        "case": case,
        "split": _require(raw, "split", case),
        "flavour": flavour,
        "package": _require(raw, "package", case),
        "apps": apps,
        "intent": _require(raw, "intent", case),
        "engine": raw.get("engine", "sqlite:///./app.db"),
        "enforce_sqlite_fk": raw.get("enforce_sqlite_fk", False),
        "models": [_model(m, case) for m in _require(raw, "models", case)],
        "stores": [_store(s, case) for s in raw.get("stores", [])],
        "entry_points": [_entry_point(e, case, flavour, apps) for e in raw.get("entry_points", [])],
        "jobs": [_job(j, case) for j in raw.get("jobs", [])],
        "routes": list(raw.get("routes", [])),
        "extra_files": list(raw.get("extra_files", [])),
        "receivers": [_receiver(r, case, apps) for r in raw.get("receivers", [])],
        "admin": list(raw.get("admin", [])),
        "retention": list(raw.get("retention", [])),
        "expect": _require(raw, "expect", case),
        "spec_sha256": hashlib.sha256(raw_bytes).hexdigest(),
    }
    if flavour not in {"sqlalchemy", "django"}:
        raise SpecError(f"{case}: unknown flavour {flavour!r}")
    return spec


def privacy_fields(spec: dict) -> tuple[str, str]:
    """(hashed, constant) for the anonymise template: the subject's first `contact` field and
    its first `identifier` field.

    Both the template and the implication table read this, so the anonymised/pseudonymised
    split is decided by the column the generator actually overwrote rather than by two
    hardcoded names (section 6.2, 03-verifier.md section 4.7).
    """
    subject = subject_model(spec)
    hashed = next((f["name"] for f in subject["fields"] if f["category"] == "contact"), None)
    constant = next((f["name"] for f in subject["fields"] if f["category"] == "identifier"), None)
    if not hashed or not constant:
        raise SpecError(
            f"{spec['case']}: anonymise needs a contact field to hash and an identifier field "
            f"to overwrite on {subject['name']}"
        )
    return hashed, constant


def cascade_tokens(cascade: str) -> frozenset[str]:
    return frozenset(token.strip() for token in cascade.split(",") if token.strip())


def is_delete_cascade(cascade: str) -> bool:
    """R5: exact tokens only. `delete-orphan` alone is not a delete cascade, and `all` is a
    documented synonym for a token list that contains `delete`."""
    return bool(cascade_tokens(cascade) & DELETE_CASCADE_TOKENS)


def subject_model(spec: dict) -> dict:
    for model in spec["models"]:
        if not model["negative"]:
            return model
    raise SpecError(f"{spec['case']}: no non-negative model to act as the data subject")


def children_of(spec: dict, model_name: str) -> list[dict]:
    return [m for m in spec["models"] if m["parent"] == model_name]


def model_named(spec: dict, name: str) -> dict:
    for model in spec["models"]:
        if model["name"] == name:
            return model
    raise SpecError(f"{spec['case']}: no model named {name!r}")


def snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def var_of(model: dict) -> str:
    return snake(model["name"])
