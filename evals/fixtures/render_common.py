"""Pieces both flavours render, and the record of what was written where.

`Rendered` is the generator's memory: every citation is recorded as the token that names
it is emitted (fixture-generator.md section 6.1), never searched for afterwards.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from emit import Doc, SpecError
from spec_model import VENDOR_MODULE, subject_model, var_of

# Pinned as in docs/research/framework-behaviour.md "Versions studied" where that document
# names a version; the remaining SDKs are pinned to a plausible current release so the file
# looks like a real requirements.txt rather than an unpinned one.
VERSIONS = {
    "sqlalchemy": "SQLAlchemy==2.0.52",
    "django": "Django==6.1",
    "boto3": "boto3==1.43.82",
    "sentry": "sentry-sdk==2.68.1",
    "redis": "redis==5.2.1",
    "stripe": "stripe==11.4.1",
    "mixpanel": "mixpanel==4.10.1",
    "sendgrid": "sendgrid==6.11.0",
    "elasticsearch": "elasticsearch==8.17.0",
    "pika": "pika==1.3.2",
    "celery": "celery==5.4.0",
}

_PLACEHOLDER = re.compile(r"\{([a-z_][a-z0-9_]*)\}")


@dataclass
class Rendered:
    """Files plus every line number the manifest needs."""

    files: dict[str, str] = field(default_factory=dict)
    field_cite: dict[tuple[str, str], tuple[str, int]] = field(default_factory=dict)
    subject_link: dict[str, tuple[str, int]] = field(default_factory=dict)
    identity: dict[str, tuple[str, int]] = field(default_factory=dict)
    declared_at: dict[str, tuple[str, int]] = field(default_factory=dict)
    entry_lines: dict[str, tuple[str, int]] = field(default_factory=dict)
    admin_line: tuple[str, int] | None = None

    def put(self, path: str, doc: Doc) -> None:
        self.files[path] = doc.text()

    def cite_field(self, store: str, name: str, path: str, line: int) -> None:
        self.field_cite[(store, name)] = (path, line)


def placeholders(key_template: str | None) -> list[str]:
    return _PLACEHOLDER.findall(key_template or "")


def readme(spec: dict) -> str:
    doc = Doc()
    doc.add(f"# {spec['package']}")
    doc.blank()
    doc.add("A small Python service. The data model, the HTTP routes and the background jobs live here.")
    return doc.text()


def requirements(spec: dict) -> str:
    lines = [VERSIONS["django" if spec["flavour"] == "django" else "sqlalchemy"]]
    if any(job["kind"] == "purge" and job["schedule"] for job in spec["jobs"]):
        lines.append(VERSIONS["celery"])
    for store in spec["stores"]:
        pin = VERSIONS.get(store["client"])
        if pin and pin not in lines:
            lines.append(pin)
    doc = Doc()
    doc.add(*lines)
    return doc.text()


def helpers(spec: dict) -> str:
    doc = Doc()
    doc.add('"""Small string helpers. No personal data passes through this module."""')
    doc.blank(2)
    doc.add(
        "def slugify(value):",
        '    return "-".join(part for part in value.lower().split() if part)',
    )
    doc.blank(2)
    doc.add(
        "def truncate(value, limit=80):",
        "    if len(value) <= limit:",
        "        return value",
        '    return value[: limit - 3] + "..."',
    )
    doc.blank(2)
    doc.add(
        "def humanise_bytes(count):",
        '    for unit in ("B", "KB", "MB"):',
        "        if count < 1024:",
        '            return f"{count} {unit}"',
        "        count //= 1024",
        '    return f"{count} GB"',
    )
    return doc.text()


def value_expr(spec: dict, name: str) -> str:
    """The expression a payload-style store writes for one declared field.

    The line must carry the field's own name, which the dict key does; the value names the
    attribute the data actually comes from.
    """
    subject = subject_model(spec)
    for model in spec["models"]:
        if model["negative"]:
            continue
        if any(f["name"] == name for f in model["fields"]):
            return f"{var_of(model)}.{name}"
    if name.endswith("email"):
        return f"{var_of(subject)}.email"
    if name.endswith("name") and any(f["name"] == "full_name" for f in subject["fields"]):
        return f"{var_of(subject)}.full_name"
    return f"{var_of(subject)}.id"


def value_models(spec: dict, names: list[str]) -> list[dict]:
    """Which model objects a writer needs as parameters, in spec order."""
    wanted = {value_expr(spec, n).split(".", 1)[0] for n in names}
    return [m for m in spec["models"] if not m["negative"] and var_of(m) in wanted]


def vendor_key(store: dict) -> str:
    module = VENDOR_MODULE.get(store["client"])
    if module is None:
        raise SpecError(f"store {store['name']}: client {store['client']} is not a third-party SDK")
    return module[: -len("_sdk")] if module.endswith("_sdk") else module
