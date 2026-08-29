"""Manifest derivation and the implication check (fixture-generator.md section 6).

The inventory half is derived — the generator wrote those lines, so it knows where they
are. The verdict half is declared in `expect:` and cross-checked against the knob-to-verdict
table, so a generator bug fails the build instead of moving the ground truth.
"""

from __future__ import annotations

import yaml

from anchors import interpolate, resolve
from emit import SpecError
from render_common import Rendered
from spec_model import is_delete_cascade, privacy_fields, subject_model

GEN_VERSION = 1


def _entry_symbols(spec: dict) -> set[str]:
    names = {e["name"] for e in spec["entry_points"]}
    for entry in spec["entry_points"]:
        names.update(entry["calls"])
    return names


def _has_entry_point(spec: dict) -> bool:
    return bool(spec["entry_points"]) or bool(spec["admin"])


def _delete_cascade(spec: dict, model: dict) -> bool:
    """R1/R4/R5: does deleting the parent row delete this one?"""
    if spec["flavour"] == "django":
        return model["on_delete"] in {"CASCADE", "DB_CASCADE"}
    return is_delete_cascade(model["cascade"])


def _fk_enforced(spec: dict) -> bool:
    """R6: enforcement is a property of the engine the delete runs on, not of the DDL —
    a non-SQLite URL, or a PRAGMA foreign_keys listener on the SQLite one."""
    return not spec["engine"].startswith("sqlite") or spec["enforce_sqlite_fk"]


def _unenforced_fk(spec: dict, model: dict) -> bool:
    """DDL the database never applies: an ondelete cascade with nothing enforcing it."""
    return model["ondelete"] == "CASCADE" and not _fk_enforced(spec)


def _reached_by_row_delete(spec: dict, model: dict) -> bool:
    subject = subject_model(spec)
    if model["name"] == subject["name"]:
        return True
    if not model["parent"] or model["parent"] != subject["name"]:
        return False
    enforced_fk = model["ondelete"] == "CASCADE" and _fk_enforced(spec)
    return _delete_cascade(spec, model) or enforced_fk


def _purge_job(spec: dict, model: dict) -> dict | None:
    """03-verifier.md section 6.2: a retention constant is requirement 4 alone. Without a
    schedule registration nothing in the repository runs the job, and the verdict falls back
    to row 9 (test 37a)."""
    for job in spec["jobs"]:
        if (
            job["kind"] == "purge"
            and job["target"] == model["name"]
            and job["retention_days"]
            and job["schedule"]
        ):
            return job
    return None


def _file_store_owner(spec: dict, store: dict) -> dict:
    for model in spec["models"]:
        for field in model["fields"]:
            if field["store"] == store["name"]:
                return model
    raise SpecError(f"{spec['case']}: no model column declares the file store {store['name']}")


def _relational_verdict(spec: dict, model: dict, field_name: str | None = None) -> str:
    """03-verifier.md section 6.1 rows 3-9, in that precedence order."""
    if not _has_entry_point(spec):
        return "no_entry_point"
    actions = {e["action"] for e in spec["entry_points"]}
    if "hard_delete" in actions and _reached_by_row_delete(spec, model):
        return "erased"
    anonymise = "anonymise" in actions and model["name"] == subject_model(spec)["name"]
    hashed, constant = privacy_fields(spec) if anonymise else (None, None)
    # Row 5: the template overwrites one column with a module constant, so that column alone
    # is anonymised; the row and its primary key survive (section 4.7).
    if anonymise and field_name == constant:
        return "anonymised"
    # Row 6 before row 7: a soft delete followed by a real purge is not demoted by a hash.
    if "soft_delete" in actions and _purge_job(spec, model):
        return "erased_after_timer"
    if anonymise:
        return "pseudonymised" if field_name in (None, hashed) else "not_erased"
    if _unenforced_fk(spec, model):
        return "unverified"
    return "not_erased"


def _store_verdict(spec: dict, store: dict) -> str:
    if store["kind"] == "backup":
        job = next((j for j in spec["jobs"] if j["module"] == store["module"]), None)
        if job and (job["schedule"] or job["retention_days"]):
            return "governed_by_retention"
        return "no_schedule_evidenced"
    if store["kind"] == "third_party":
        return "external_manual"
    if not _has_entry_point(spec):
        return "no_entry_point"
    if store["client"] == "file" and store["kind"] == "object_storage":
        owner = _file_store_owner(spec, store)
        wired = any(
            rec["sender"] == owner["name"] and rec["body"] == "delete_file" for rec in spec["receivers"]
        )
        if wired and _relational_verdict(spec, owner) == "erased":
            return "erased"
        return "not_erased"
    if store["delete_call"] and store["delete_called_by"] in _entry_symbols(spec):
        return "erased"
    return "not_erased"


def _check_verdict(case: str, where: str, declared: dict, implied: str) -> None:
    if declared.get("verdict") != implied:
        raise SpecError(
            f"{case} {where}: expect says {declared.get('verdict')!r}, knobs imply {implied!r}"
        )


def _erasure(spec: dict, declared: dict, files: dict[str, str]) -> dict:
    block: dict = {"verdict": declared["verdict"]}
    if "timer_days" in declared:
        block["timer_days"] = declared["timer_days"]
    evidence = declared.get("evidence")
    if evidence:
        path, line = resolve(evidence, files)
        block["evidence"] = f"{path}:{line}"
    else:
        block["evidence"] = None
    if declared.get("note"):
        block["note"] = interpolate(declared["note"], files)
    return block


def _entry_points(spec: dict, r: Rendered) -> list[dict]:
    rows = []
    for entry in spec["entry_points"]:
        path, line = r.entry_lines[entry["name"]]
        rows.append({"name": entry["name"], "file": path, "line": line, "kind": entry["kind"]})
    if spec["admin"]:
        if r.admin_line is None:
            raise SpecError(f"{spec['case']}: admin[] declared but no registration was rendered")
        path, line = r.admin_line
        for name in ("admin_delete_model", "admin_delete_selected"):
            rows.append({"name": name, "file": path, "line": line, "kind": "admin", "admin_only": True})
    declared = list(spec["expect"].get("entry_points", []))
    if [row["name"] for row in rows] != declared:
        raise SpecError(
            f"{spec['case']}: expect.entry_points {declared} does not match the rendered "
            f"{[row['name'] for row in rows]}"
        )
    return rows


def _field_rows(spec: dict, r: Rendered, store_name: str, fields: list[dict], model: dict | None) -> list[dict]:
    rows = []
    expect_fields = spec["expect"].get("fields") or {}
    for field in fields:
        if field.get("store") and field["store"] != store_name:
            if field["category"]:
                raise SpecError(
                    f"{spec['case']} {store_name}.{field['name']}: a redirected field with a "
                    "category has no template behind it"
                )
            continue
        if not field["category"]:
            continue
        path, line = r.field_cite[(store_name, field["name"])]
        row = {"name": field["name"], "category": field["category"], "file": path, "line": line}
        key = f"{store_name}.{field['name']}"
        if key in expect_fields:
            declared = expect_fields[key]
            implied = (
                _relational_verdict(spec, model, field["name"])
                if model is not None
                else _store_verdict(spec, next(s for s in spec["stores"] if s["name"] == store_name))
            )
            _check_verdict(spec["case"], f"field {key}", declared, implied)
            row["erasure"] = _erasure(spec, declared, r.files)
        rows.append(row)
    return rows


def _stores(spec: dict, r: Rendered) -> list[dict]:
    expect_stores = spec["expect"]["stores"]
    rows = []
    for model in spec["models"]:
        if model["negative"]:
            continue
        name = model["store"]
        declared = expect_stores.get(name)
        if declared is None:
            raise SpecError(f"{spec['case']}: expect.stores has no entry for {name}")
        _check_verdict(spec["case"], f"store {name}", declared, _relational_verdict(spec, model))
        path, line = r.subject_link[name]
        rows.append(
            {
                "name": name,
                "kind": "relational",
                "subject_link": {"file": path, "line": line},
                "fields": _field_rows(spec, r, name, model["fields"], model),
                "erasure": _erasure(spec, declared, r.files),
            }
        )
    for store in spec["stores"]:
        name = store["name"]
        declared = expect_stores.get(name)
        if declared is None:
            raise SpecError(f"{spec['case']}: expect.stores has no entry for {name}")
        _check_verdict(spec["case"], f"store {name}", declared, _store_verdict(spec, store))
        path, line = r.subject_link[name]
        row = {"name": name, "kind": store["kind"]}
        if name in r.declared_at:
            cite = r.declared_at[name]
            row["declared_at"] = {"file": cite[0], "line": cite[1]}
        if store["kind"] == "third_party":
            row["recipient_kind"] = "unknown"
        row["subject_link"] = {"file": path, "line": line}
        row["fields"] = _field_rows(spec, r, name, [dict(f, store=None, pk=False) for f in store["fields"]], None)
        row["erasure"] = _erasure(spec, declared, r.files)
        rows.append(row)
    unknown = set(expect_stores) - {row["name"] for row in rows}
    if unknown:
        raise SpecError(f"{spec['case']}: expect.stores names no store: {sorted(unknown)}")
    return rows


def _retention(spec: dict, r: Rendered) -> list[dict]:
    rows = []
    for item in spec["retention"]:
        if not item.get("anchor"):
            raise SpecError(f"{spec['case']}: retention row for {item.get('store')} has no anchor")
        path, line = resolve(item["anchor"], r.files)
        row = {"store": item["store"], "category": item["category"]}
        if ("days" in item) == ("criteria" in item):
            raise SpecError(f"{spec['case']}: retention row for {item['store']} needs days or criteria")
        if "days" in item:
            row["days"] = item["days"]
        else:
            row["criteria"] = item["criteria"]
        row["file"] = path
        row["line"] = line
        rows.append(row)
    return rows


def build(spec: dict, r: Rendered) -> dict:
    return {
        "case": spec["case"],
        "split": spec["split"],
        "source": "synthetic",
        "intent": spec["intent"],
        "spec_sha256": spec["spec_sha256"],
        "gen_version": GEN_VERSION,
        "normalisation": {"prefixes": list(spec["apps"])},
        "labelling_minutes": None,
        "entry_points": _entry_points(spec, r),
        "stores": _stores(spec, r),
        "retention": _retention(spec, r),
        "negatives": [m["store"] for m in spec["models"] if m["negative"]],
    }


def dump(manifest: dict) -> str:
    return yaml.safe_dump(
        manifest, sort_keys=False, default_flow_style=False, allow_unicode=True, width=100
    )
