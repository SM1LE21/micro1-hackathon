"""The shipped record schema, the spec copy, and what they accept.

The two copies must hash equal: the schema is embedded in `submit_record`'s
input schema, so an edit to either moves step 1's request hash in every run.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from jsonschema import Draft202012Validator

from art30.tools import SCHEMA_PATH, format_schema_errors, record_schema

# Derived from the module under test, never from the process cwd: run from
# elsewhere this would fail with FileNotFoundError rather than a hash mismatch.
SPEC_COPY = SCHEMA_PATH.parents[2] / "docs" / "spec" / "record.schema.json"

CITATION = {"file": "storage.py", "line": 47, "symbol": "delete_object"}

MINIMAL_RECORD: dict = {
    "schema_version": "1",
    "repository": "tidewharf",
    "unscanned": [],
    "data_subjects": [
        {"label": "account holders", "basis": "model_name", "file": "models.py", "line": 12}
    ],
    "entry_points": [
        {
            "name": "close_account",
            "kind": "route",
            "file": "api/account.py",
            "line": 12,
            "admin_only": False,
            "note": None,
        }
    ],
    "stores": [
        {
            "name": "uploads",
            "kind": "object_storage",
            "declared_at": {"file": "storage.py", "line": 8, "symbol": "BUCKET"},
            "subject_link": {"file": "storage.py", "line": 20},
            "fields": [
                {
                    "name": "avatar_key",
                    "category": "identifier",
                    "file": "storage.py",
                    "line": 20,
                    "note": None,
                    "erasure": None,
                }
            ],
            "erasure": {
                "verdict": "erased",
                "evidence": [CITATION],
                "timer_days": None,
                "note": None,
            },
            "recipient_kind": None,
            "note": None,
        }
    ],
    "retention": [],
    "activities": [],
    "hints": {
        "observed_module_names": [],
        "observed_region_hints": [],
        "security_evidence": [],
    },
    "human": {
        "controller": {"name": None, "contact": None},
        "joint_controller": {"name": None, "contact": None},
        "representative": {"name": None, "contact": None},
        "dpo": {"name": None, "contact": None},
        "purposes": None,
        "legal_basis": None,
        "data_subject_categories_confirmed": None,
        "data_categories_outside_code": None,
        "special_categories": None,
        "transfers": {"occurs": None, "countries": None, "safeguards": None},
        "retention_justification": None,
        "security_organisational": None,
    },
}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_shipped_schema_and_spec_copy_hash_equal() -> None:
    assert _sha(SCHEMA_PATH) == _sha(SPEC_COPY)


def test_schema_is_a_valid_2020_12_schema() -> None:
    Draft202012Validator.check_schema(record_schema())


def test_minimal_record_validates() -> None:
    errors = format_schema_errors(Draft202012Validator(record_schema()).iter_errors(MINIMAL_RECORD))
    assert errors == []


def test_a_human_cell_the_agent_filled_is_rejected() -> None:
    record = {**MINIMAL_RECORD, "human": {**MINIMAL_RECORD["human"], "purposes": "marketing"}}
    errors = format_schema_errors(Draft202012Validator(record_schema()).iter_errors(record))
    assert any(error.startswith("/human/purposes:") for error in errors)


def test_recipient_kind_cannot_be_set_by_the_agent() -> None:
    store = {**MINIMAL_RECORD["stores"][0], "recipient_kind": "processor"}
    record = {**MINIMAL_RECORD, "stores": [store]}
    errors = format_schema_errors(Draft202012Validator(record_schema()).iter_errors(record))
    assert any(error.startswith("/stores/0/recipient_kind:") for error in errors)


def test_an_unknown_verdict_names_the_allowed_values() -> None:
    store = {**MINIMAL_RECORD["stores"][0]}
    store["erasure"] = {**store["erasure"], "verdict": "deleted"}
    record = {**MINIMAL_RECORD, "stores": [store]}
    errors = format_schema_errors(Draft202012Validator(record_schema()).iter_errors(record))
    verdict = [error for error in errors if error.startswith("/stores/0/erasure/verdict:")]
    assert verdict and "allowed: anonymised, erased," in verdict[0]
