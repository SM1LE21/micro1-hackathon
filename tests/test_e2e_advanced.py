"""Four scripted advanced runs, end to end, offline (ADR 0006 item 3).

No API key, no socket, no result and no trace outside `tmp_path`: the model is a list
of canned responses served by step number, exactly as `tests/test_loop.py` drives the
baseline, and every fixture is copied before it is read.

The records the fake model submits are built from the case manifests, so a test that
passes says the tool accepts the ground truth and rejects one deliberate lie per case
-- S10's dead helper, S09's wrong-sender receiver, D01's file field behind a cascade
-- while S08, where nothing deletes a user at all, is accepted first time at risk
`high`. Manifests are read here as test data; nothing under `art30/` can see them.

Every run's trace is handed to the shipped validator, which recomputes the checkpoint
rating from the accepted record (check 11) and requires exactly one checkpoint on an
advanced run (check 10).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Iterator

import pytest
import yaml

from advanced.arm import AdvancedArm
from art30 import llm
from art30.config import Config
from art30.loop import CaseRef, run
from evals.harness.trace_check import check_trace

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "evals" / "fixtures" / "synthetic"
MANIFESTS = REPO_ROOT / "evals" / "fixtures" / "manifests"
USAGE = {"input": 100, "cache_read": 0, "cache_write": 40, "output": 200}

# 03-verifier.md 2.2 discovers these two from `admin.site.register`; they are not
# symbols and a record cannot cite them, so they arrive as `missing_entry_points`.
SYNTHETIC_ENTRIES = ("admin_delete_model", "admin_delete_selected")

# The symbol on each manifest evidence line, per case. The manifest carries
# `file:line` and the citation check (7.2) reads the symbol off the line.
SYMBOLS: dict[str, dict[str, str]] = {
    "S10": {"users": "delete", "nightly_backup": "BACKUP_RETENTION_DAYS"},
    "S09": {"gallery_account": "delete", "gallery_photo": "ForeignKey",
            "gallery_comment": "ForeignKey"},
    "S08": {},
    "D01": {"members_member": "delete", "members_note": "ForeignKey",
            "members_order": "ForeignKey"},
}
HUMAN: dict = {
    "controller": {"name": None, "contact": None},
    "joint_controller": {"name": None, "contact": None},
    "representative": {"name": None, "contact": None},
    "dpo": {"name": None, "contact": None},
    "purposes": None, "legal_basis": None, "data_subject_categories_confirmed": None,
    "data_categories_outside_code": None, "special_categories": None,
    "transfers": {"occurs": None, "countries": None, "safeguards": None},
    "retention_justification": None, "security_organisational": None,
}


# ---------------------------------------------------------------------------
# the fixture copy and the record the fake model submits
# ---------------------------------------------------------------------------
@pytest.fixture
def copy_case(tmp_path: Path):
    """ADR 0006 item 3: fixture copies, and nothing written under results/ or traces/."""
    def _copy(case: str) -> Path:
        target = tmp_path / "repos" / case
        shutil.copytree(FIXTURES / case, target)
        return target
    return _copy


def manifest(case: str) -> dict:
    return yaml.safe_load((MANIFESTS / f"{case}.yaml").read_text(encoding="utf-8"))


def _cite(text: str, symbol: str) -> dict:
    file, _, line = str(text).rpartition(":")
    return {"file": file, "line": int(line), "symbol": symbol}


def _erasure(case: str, item: dict) -> dict:
    block = item.get("erasure") or {}
    evidence = block.get("evidence")
    symbol = SYMBOLS[case].get(item["name"], item["name"])
    return {"verdict": block.get("verdict"),
            "evidence": [_cite(evidence, symbol)] if evidence else [],
            "timer_days": block.get("timer_days"), "note": block.get("note")}


def _store(case: str, item: dict) -> dict:
    declared = item.get("declared_at")
    return {
        "name": item["name"], "kind": item["kind"],
        "declared_at": (dict(declared, symbol=item["name"].split(".")[-1])
                        if declared else None),
        "subject_link": item.get("subject_link"),
        "fields": [{"name": f["name"], "category": f["category"], "file": f["file"],
                    "line": f["line"], "note": None, "erasure": None}
                   for f in item["fields"]],
        "erasure": _erasure(case, item), "recipient_kind": None, "note": None,
    }


def record_of(case: str, edits: dict[str, dict] | None = None,
              drop: tuple[str, ...] = (), retention: bool = True) -> dict:
    """The manifest as a submitted record, with `edits` replacing erasure blocks."""
    data = manifest(case)
    stores = [_store(case, item) for item in data["stores"] if item["name"] not in drop]
    for item in stores:
        if edits and item["name"] in edits:
            item["erasure"] = edits[item["name"]]
    names = {item["name"] for item in stores}
    items = [{"store": r["store"], "category": r.get("category"), "days": r.get("days"),
              "criteria": None, "file": r["file"], "line": r["line"],
              "justification": None}
             for r in (data.get("retention") or []) if retention and r["store"] in names]
    return {
        "schema_version": "1", "repository": case.lower(), "unscanned": [],
        "data_subjects": [], "activities": [], "retention": items, "stores": stores,
        "entry_points": [{"name": e["name"], "kind": e["kind"], "file": e["file"],
                          "line": e["line"], "admin_only": bool(e.get("admin_only")),
                          "note": None}
                         for e in data["entry_points"]
                         if e["name"] not in SYNTHETIC_ENTRIES],
        "hints": {"observed_module_names": [], "observed_region_hints": [],
                  "security_evidence": []},
        "human": json.loads(json.dumps(HUMAN)),
    }


# ---------------------------------------------------------------------------
# the scripted model
# ---------------------------------------------------------------------------
def _response(blocks: list[dict], stop: str = "tool_use") -> llm.Response:
    return llm.Response(content=[{"type": "thinking", "thinking": "reading the models"}]
                        + blocks, stop_reason=stop, stop_details=None,
                        usage=dict(USAGE), request_id="req_test")


def _use(call_id: str, name: str, payload: dict) -> dict:
    return {"type": "tool_use", "id": call_id, "name": name, "input": payload}


def _submit(call_id: str, record: dict) -> dict:
    return _use(call_id, "submit_record", {"record": record})


@pytest.fixture
def script(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[llm.Response]]:
    responses: list[llm.Response] = []

    def fake_call(req: dict, *, cfg: Config, slot: llm.Slot) -> llm.Response:
        assert "system" in req and "tools" in req
        return responses[slot.step - 1]

    monkeypatch.setattr(llm, "call", fake_call)
    yield responses


def _cfg(tmp_path: Path) -> Config:
    return Config(trace_dir=tmp_path / "traces", out_dir=tmp_path / "out",
                  cache_dir=tmp_path / "cache", approve="auto", tool_budget=20)


def _drive(case: str, root: Path, tmp_path: Path, script: list) -> tuple:
    cfg = _cfg(tmp_path)
    result = run(CaseRef(id=case, name=root.name, root=root), AdvancedArm(), 1, cfg, None)
    trace = tmp_path / "traces" / "advanced" / f"{case}-s1.jsonl"
    lines = [json.loads(line) for line in trace.read_text(encoding="utf-8").splitlines()]
    return result, lines, trace


def _feedback(lines: list[dict], step: int) -> dict:
    """The submit result of one step, as the model saw it."""
    steps = [line for line in lines if line["type"] == "step"]
    return json.loads(steps[step - 1]["tool_results"][-1]["output"])


def _checkpoint(lines: list[dict]) -> dict:
    return next(line for line in lines if line["type"] == "checkpoint")


# ---------------------------------------------------------------------------
# S10: the dead helper
# ---------------------------------------------------------------------------
S10_LIE = {"verdict": "erased",
           "evidence": [{"file": "storage.py", "line": 30, "symbol": "delete_object"}],
           "timer_days": None, "note": "cleanup_user_files removes the avatar"}
S10_REASON = ("no path from entry point close_account (api/account.py:12) to any"
              " object-storage deletion primitive; cleanup_user_files (storage.py:29)"
              " is defined but has no callers")


def test_s10_the_dead_helper_is_rejected_then_the_record_is_accepted(
    copy_case, tmp_path: Path, script, capsys
) -> None:
    """The contract's own example sentence, rendered from the fixture's own lines."""
    root = copy_case("S10")
    script += [
        _response([_submit("t1", record_of("S10", edits={"uploads": S10_LIE},
                                           drop=("nightly_backup",), retention=False))]),
        _response([_submit("t2", record_of("S10"))]),
    ]
    result, lines, trace = _drive("S10", root, tmp_path, script)

    first = _feedback(lines, 1)
    assert first["accepted"] is False
    assert len(first["rejected_claims"]) == 1
    entry = first["rejected_claims"][0]
    assert (entry["store"], entry["claim"]) == ("uploads", "erasure.verdict=erased")
    assert entry["reason"] == S10_REASON
    assert entry["path"] == []
    assert entry["expected"] == "verdict not_erased, or cite the path"
    assert [m["store"] for m in first["missing_stores"]] == ["nightly_backup"]

    assert _feedback(lines, 2) == {"accepted": True}
    assert (result.stop_condition, result.submits, result.verify_rounds) == ("accepted", 2, 1)
    point = _checkpoint(lines)
    assert (point["risk"], point["by"], point["wait_s"]) == ("high", "simulated", 0.0)
    assert (point["decision"], point["caller"]) == ("approved", "harness")
    assert point["human_completions"] is None
    written = json.loads(Path(result.record_path).read_text(encoding="utf-8"))
    assert written["verification"]["accepted_on_attempt"] == 2
    assert written["provenance"]["arm"] == "advanced"
    assert written["provenance"]["gate"]["risk"] == "high"
    assert check_trace(trace) == []
    assert "RECORD READY FOR REVIEW" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# S09: the decoy receiver
# ---------------------------------------------------------------------------
S09_LIE = {"verdict": "erased",
           "evidence": [{"file": "gallery/signals.py", "line": 11, "symbol": "delete"}],
           "timer_days": None, "note": "the post_delete receiver deletes the file"}


def test_s09_a_receiver_registered_for_the_wrong_sender_is_rejected(
    copy_case, tmp_path: Path, script, capsys
) -> None:
    """R9 [S6]: a receiver with a different `sender=` does not count. The S09 decoy."""
    root = copy_case("S09")
    script += [
        _response([_submit("t1", record_of("S09", edits={"photo.image": S09_LIE}))]),
        _response([_submit("t2", record_of("S09"))]),
    ]
    result, lines, trace = _drive("S09", root, tmp_path, script)

    first = _feedback(lines, 1)
    assert [e["store"] for e in first["rejected_claims"]] == ["photo.image"]
    assert "has sender=Comment, not Photo" in first["rejected_claims"][0]["reason"]
    assert _feedback(lines, 2) == {"accepted": True}
    assert (result.stop_condition, result.verify_rounds) == ("accepted", 1)
    assert _checkpoint(lines)["risk"] == "high"
    assert check_trace(trace) == []
    capsys.readouterr()


def test_s09_reports_the_admin_entry_points_without_blocking(
    copy_case, tmp_path: Path, script, capsys
) -> None:
    """4.2a: the two admin entry points the record cannot cite cost no attempt."""
    root = copy_case("S09")
    script.append(_response([_submit("t1", record_of("S09"))]))
    result, lines, trace = _drive("S09", root, tmp_path, script)

    assert (result.stop_condition, result.verify_rounds) == ("accepted", 0)
    assert check_trace(trace) == []
    capsys.readouterr()


# ---------------------------------------------------------------------------
# S08: no way to delete a user
# ---------------------------------------------------------------------------
def test_s08_every_store_is_no_entry_point_and_the_gate_says_high(
    copy_case, tmp_path: Path, script, capsys
) -> None:
    """ADR 0004 P-09: the case built to test whether the tool can say there is no way."""
    root = copy_case("S08")
    submitted = record_of("S08")
    script.append(_response([_submit("t1", submitted)]))
    result, lines, trace = _drive("S08", root, tmp_path, script)

    verdicts = {s["name"]: s["erasure"]["verdict"] for s in submitted["stores"]}
    assert submitted["entry_points"] == []
    assert set(verdicts.values()) == {"no_entry_point", "no_schedule_evidenced"}
    assert _feedback(lines, 1) == {"accepted": True}
    assert (result.stop_condition, result.verify_rounds) == ("accepted", 0)
    point = _checkpoint(lines)
    assert (point["risk"], point["by"]) == ("high", "simulated")
    assert ("no deletion entry point was found; no store in this record reaches erasure"
            in point["summary"])
    assert check_trace(trace) == []
    capsys.readouterr()


# ---------------------------------------------------------------------------
# D01: the demo case
# ---------------------------------------------------------------------------
D01_LIE = {"verdict": "erased",
           "evidence": [{"file": "members/models.py", "line": 14, "symbol": "avatar"}],
           "timer_days": None, "note": "the row cascade removes the avatar"}


def test_d01_the_file_survives_the_cascade_and_the_db_cascade_rows_do_not(
    copy_case, tmp_path: Path, script, capsys
) -> None:
    """R8 and R4: the avatar claim is rejected, the DB_CASCADE order rows are accepted."""
    root = copy_case("D01")
    script += [
        _response([_submit("t1", record_of("D01", edits={"member.avatar": D01_LIE}))]),
        _response([_submit("t2", record_of("D01"))]),
    ]
    result, lines, trace = _drive("D01", root, tmp_path, script)

    first = _feedback(lines, 1)
    assert [e["store"] for e in first["rejected_claims"]] == ["member.avatar"]
    assert ("member.avatar (members/models.py:14) is a file field; a row cascade does"
            " not delete the file" in first["rejected_claims"][0]["reason"])
    assert _feedback(lines, 2) == {"accepted": True}
    assert (result.stop_condition, result.verify_rounds) == ("accepted", 1)
    assert check_trace(trace) == []
    capsys.readouterr()


def test_nothing_is_written_outside_the_temporary_directory(
    copy_case, tmp_path: Path, script, capsys
) -> None:
    """ADR 0006 item 3: an offline test produces no result and no trace in the repo."""
    root = copy_case("D01")
    script.append(_response([_submit("t1", record_of("D01"))]))
    before = {p for p in (REPO_ROOT / "traces").rglob("*") if p.is_file()}
    result, _, _ = _drive("D01", root, tmp_path, script)

    assert result.stop_condition == "accepted"
    assert Path(result.record_path).is_relative_to(tmp_path)
    assert {p for p in (REPO_ROOT / "traces").rglob("*") if p.is_file()} == before
    capsys.readouterr()


def test_the_advanced_record_says_the_verifier_ran(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """04-output-schema.md section 5: an advanced record names its rule set and carries the
    rejected claim with what replaced it; a reader must never see "Verification: none" on
    a record the verifier accepted."""
    import json
    import shutil
    import subprocess
    import sys
    repo = tmp_path / "S10"
    shutil.copytree(Path("evals/fixtures/synthetic/S10"), repo)
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_e2e_advanced.py", "-q", "-k", "dead_helper",
         "--basetemp", str(tmp_path / "bt")], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout[-800:]
    records = list((tmp_path / "bt").rglob("record.json"))
    assert records, "the scripted S10 run wrote no record.json"
    ver = json.loads(records[0].read_text())["verification"]
    assert ver["rule_set_sha"] and len(ver["rule_set_sha"]) == 12
    assert ver["rejected_history"] and ver["rejected_history"][0]["store"] == "uploads"
    assert ver["rejected_history"][0]["revised_to"] == "not_erased"
    md = records[0].with_name("record.md").read_text()
    assert "Verification: none" not in md and "rule set " in md
