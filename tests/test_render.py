"""The rendered record: section order, verdict words, the empty cells.

The record below is the shape `docs/spec/example-record-S10.md` describes,
against a repository small enough to read in one screen but carrying every
cited symbol on its cited line.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from art30.render import RenderError, render_all
from art30.render.html import render_html
from art30.render.markdown import render_markdown
from tests.conftest import mkrepo

SOURCE = {
    "models.py": "class User(Base):\n    email = Column(String)\n    deleted_at = Column(DateTime)\n",
    "storage.py": (
        'AVATAR_PREFIX = "avatars/"\n'
        'avatar_key = f"{AVATAR_PREFIX}{user_id}"\n'
        "\n"
        "def cleanup_user_files(user_id):\n"
        "    s3.delete_object(Bucket=BUCKET, Key=avatar_key)\n"
    ),
    "jobs/backup.py": "def dump(): email, full_name = read_users()\nRETENTION_DAYS = 35\n",
    "jobs/purge.py": "def purge_closed_accounts():\n    session.delete(user)\n",
    "billing.py": "Customer.create(email=user.email)\nname = user.full_name\n",
    "api/account.py": "def close_account(user_id):\n    user.deleted_at = now()\n",
    "config.py": 'REGION = "eu-central-1"\nDSN = "postgres://db?sslmode=require"\n',
}


def cite(path: str, line: int, symbol: str) -> dict:
    return {"file": path, "line": line, "symbol": symbol}


def store(name: str, kind: str, declared, link, fields: list, erasure: dict, note=None) -> dict:
    return {
        "name": name,
        "kind": kind,
        "declared_at": declared,
        "subject_link": link,
        "fields": fields,
        "erasure": erasure,
        "recipient_kind": "unknown" if kind == "third_party" else None,
        "note": note,
    }


def field(name: str, category: str, path: str, line: int, note=None) -> dict:
    return {"name": name, "category": category, "file": path, "line": line, "note": note, "erasure": None}


def erasure(verdict: str, evidence: list, timer=None, note=None) -> dict:
    return {"verdict": verdict, "evidence": evidence, "timer_days": timer, "note": note}


def record(rule_set: str | None = None) -> dict:
    return {
        "schema_version": "1",
        "repository": "tidewharf",
        "unscanned": [{"path": "README.md", "reason": "not_python"}],
        "data_subjects": [
            {"label": "account holders", "basis": "model_name", "file": "models.py", "line": 1}
        ],
        "entry_points": [
            {
                "name": "close_account",
                "kind": "route",
                "file": "api/account.py",
                "line": 1,
                "admin_only": False,
                "note": "the only deletion surface in the repository",
            }
        ],
        "stores": [
            store(
                "users", "relational", cite("models.py", 1, "User"), {"file": "models.py", "line": 1},
                [field("email", "contact", "models.py", 2), field("deleted_at", "technical", "models.py", 3)],
                erasure("erased_after_timer", [cite("jobs/purge.py", 2, "delete")], 30,
                        "close_account writes deleted_at; purge_closed_accounts removes the row"),
            ),
            store(
                "uploads", "object_storage", None, {"file": "storage.py", "line": 1},
                [field("avatar_key", "identifier", "storage.py", 2)],
                erasure("not_erased", [cite("storage.py", 4, "cleanup_user_files")], None,
                        "cleanup_user_files is defined at storage.py:4 and has no caller"),
            ),
            store(
                "nightly_backup", "backup", cite("jobs/backup.py", 1, "dump"),
                {"file": "jobs/backup.py", "line": 1},
                [field("email", "contact", "jobs/backup.py", 1)],
                erasure("governed_by_retention", [cite("jobs/backup.py", 2, "RETENTION_DAYS")], 35),
            ),
            store(
                "stripe", "third_party", cite("billing.py", 1, "Customer"),
                {"file": "billing.py", "line": 1},
                [field("email", "contact", "billing.py", 1), field("name", "identifier", "billing.py", 2)],
                erasure("external_manual", [], None, "no Customer.delete call in the repository"),
            ),
        ],
        "retention": [
            {
                "store": "users",
                "category": "contact",
                "days": 30,
                "criteria": "after `deleted_at`",
                "file": "jobs/purge.py",
                "line": 2,
                "justification": None,
            }
        ],
        "activities": [],
        "hints": {
            "observed_module_names": [{"name": "billing", "file": "billing.py"}],
            "observed_region_hints": [cite("config.py", 1, "eu-central-1")],
            "security_evidence": [
                {
                    "measure": "encryption_in_transit",
                    "file": "config.py",
                    "line": 2,
                    "symbol": "sslmode=require",
                }
            ],
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
        "verification": {
            "submits": 2,
            "accepted_on_attempt": 2,
            "rejected_history": [
                {
                    "attempt": 1,
                    "store": "uploads",
                    "claim": "erasure.verdict=erased",
                    "reason": "no path from close_account to any object-storage deletion primitive",
                    "expected": "verdict not_erased, or cite the path",
                    "revised_to": "not_erased",
                }
            ],
            "missing_stores_resolved": [],
            "bad_citations_resolved": [],
            "unverified": [],
            "rule_set_sha": rule_set,
        },
        "provenance": {
            "arm": "advanced" if rule_set else "baseline",
            "model": "claude-opus-5",
            "effort": "high",
            "config": {"max_tokens": 32000, "tool_budget": 60, "submit_budget": 5, "overridden": []},
            "run_id": "adv-S10-s1-9f3ac1e",
            "case": "S10",
            "seed": 1,
            "mode": "replay",
            "fixture": {"id": "S10", "path": "evals/fixtures/synthetic/S10", "sha256": "9f3c41ab7e02"},
            "instruction_sha256": "c4d81f60a92b",
            "started_at": "2026-08-30T14:02:11Z",
            "finished_at": "2026-08-30T14:05:41Z",
            "trace": "traces/advanced/S10-s1.jsonl",
            "cost_usd": 0.41,
            "tool_calls": 21,
            "gate": None,
        },
    }


@pytest.fixture()
def source(tmp_path: Path) -> Path:
    return mkrepo(tmp_path / "fx", SOURCE)


def test_the_sections_run_a_to_h_in_order() -> None:
    text = render_markdown(record())
    assert re.findall(r"^## ([A-H])\. ", text, re.MULTILINE) == list("ABCDEFGH")
    assert text.startswith("# Record of processing — tidewharf")


def test_verdicts_are_words_in_capitals() -> None:
    text = render_markdown(record())
    assert "| uploads | NOT ERASED |" in text
    assert "ERASED AFTER TIMER (30 days)" in text
    assert "GOVERNED BY RETENTION (35 days)" in text
    # The verdicts that do not reach erasure come first (04 section 6 D).
    erasure = text.split("## D. Erasure")[1].split("## E.")[0]
    names = [line.split(" | ")[0][2:] for line in erasure.splitlines() if line.startswith("| ")][1:]
    assert names == ["uploads", "stripe", "nightly_backup", "users"]


def test_human_cells_say_what_is_missing() -> None:
    text = render_markdown(record())
    assert f"UNKNOWN — requires human completion" in text
    assert text.count("requires human completion") >= 15
    assert "| stripe |" in text and "Recipient kind — stripe" in text


def test_the_document_states_no_legal_conclusion() -> None:
    text = render_markdown(record()).lower()
    assert "complian" not in text
    assert "legal basis | — | requires human completion" in text


def test_a_store_with_no_retention_item_renders_no_timer_evidenced() -> None:
    text = render_markdown(record())
    assert "| uploads | — | NO TIMER EVIDENCED | — | requires human completion |" in text
    assert "| users | contact | 30 days after `deleted_at` |" in text


def test_the_baseline_replaces_the_verification_appendix_with_one_line() -> None:
    assert "accepted on schema validity alone" in render_markdown(record())
    assert "Claims rejected and what replaced them" in render_markdown(record("3f9ac1d2"))


def test_the_evidence_index_lists_every_cited_line_once() -> None:
    text = render_markdown(record())
    index = text.split("## H. Evidence index")[1]
    assert index.count("`models.py:1`") == 1
    assert "`storage.py:4`" in index and "| D |" in index
    assert "`config.py:1`" in index and "`eu-central-1`" in index


def test_the_page_carries_no_javascript_and_one_tooltip_per_citation(source: Path) -> None:
    page = render_html(record(), source)
    assert "<script" not in page.lower()
    assert "http://" not in page and "https://" not in page.replace("http://www.w3.org", "")
    assert '<section id="a-inventory">' in page and '<section id="h-evidence">' in page
    assert '<code class="cite" title="class User(Base):">models.py:1</code>' in page
    assert '<span class="verdict not-reaching">NOT ERASED</span>' in page
    assert '<span class="empty">requires human completion</span>' in page


def test_a_citation_that_lost_its_symbol_stops_the_render(source: Path, tmp_path: Path) -> None:
    kept = SOURCE["storage.py"].replace("def cleanup_user_files", "def renamed")
    (source / "storage.py").write_text(kept, encoding="utf-8")
    with pytest.raises(RenderError) as caught:
        render_html(record(), source)
    assert "cleanup_user_files" in str(caught.value)

    with pytest.raises(RenderError) as through:
        render_all(record(), tmp_path / "out", source)
    # record.json is written before the Markdown and the HTML, so it survives.
    assert (tmp_path / "out" / "record.json").is_file()
    assert through.value.record_path.endswith("record.json")


def test_a_citation_inside_a_multi_line_statement_renders(source: Path) -> None:
    """7.2 rule 3 reads the statement whose span contains the cited line, so the
    verifier accepts such a citation; the render check must not be stricter than
    the verifier that vouched for the record (DEVIATIONS D-22 — the R01 demo run
    died on exactly this, after the human had approved)."""
    (source / "notify.py").write_text(
        "send_email(\n    to=user.email,\n    password=password,\n)\n", encoding="utf-8")
    rec = record()
    rec["stores"][0]["fields"].append(field("password", "technical", "notify.py", 2))
    render_html(rec, source)


def test_two_renders_of_one_record_are_the_same_bytes(source: Path) -> None:
    assert render_markdown(record()) == render_markdown(record())
    assert render_html(record(), source) == render_html(record(), source)
