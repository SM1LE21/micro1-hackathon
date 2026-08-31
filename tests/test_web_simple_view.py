"""The simple view, read as text. The page's script runs in Node against a small DOM
stub (tests/web_dom_stub.js); a synthetic run is fed through `apply()` the way the
event stream would; the Now line, the status chip and the findings card are asserted.
No browser is on the build machine, so this is how the view's wording and plumbing
are checked. Skipped where node is not on PATH, as test_web_page does."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PAGE = REPO_ROOT / "art30" / "web" / "index.html"
STUB = Path(__file__).with_name("web_dom_stub.js")

RUN = {"run_id": "advanced-T01-s1-test", "case": "T01", "arm": "advanced", "mode": "live",
       "seed": 1, "repo": "/repo", "brain": "claude", "status": "running"}

RECORD = {
    "schema_version": "1", "repository": "t01", "unscanned": [], "data_subjects": [],
    "entry_points": [{"name": "delete_account", "kind": "view", "file": "app/views.py", "line": 9,
                      "admin_only": False, "note": None}],
    "stores": [
        {"name": "members", "kind": "relational", "note": "The member table.",
         "declared_at": {"file": "app/models.py", "line": 8, "symbol": "members"},
         "subject_link": {"file": "app/models.py", "line": 8},
         "fields": [{"name": "email", "category": "contact", "file": "app/models.py", "line": 9,
                     "note": None, "erasure": None}],
         "erasure": {"verdict": "erased", "note": "The view calls delete().", "timer_days": None,
                     "evidence": [{"file": "app/views.py", "line": 12, "symbol": "delete"}]},
         "recipient_kind": None},
        {"name": "avatar.files", "kind": "object_storage", "note": "Avatar images.",
         "declared_at": {"file": "app/models.py", "line": 14, "symbol": "ImageField"},
         "subject_link": {"file": "app/models.py", "line": 14},
         "fields": [{"name": "avatar", "category": "identifier", "file": "app/models.py", "line": 14,
                     "note": None, "erasure": None}],
         "erasure": {"verdict": "not_erased", "timer_days": None,
                     "note": "No receiver removes the file when the row goes.",
                     "evidence": [{"file": "app/models.py", "line": 14, "symbol": "ImageField"}]},
         "recipient_kind": None},
    ],
    "retention": [], "hints": {}, "human": {}, "activities": [],
    "provenance": {"arm": "advanced", "case": "T01", "brain": "claude", "cost_usd": 0.02},
    "verification": {"submissions": 1, "accepted_on_attempt": 1, "rule_set_sha": "abc"},
}

STEP_READ = {"type": "step", "step": 1, "phase": "agent", "reasoning": "", "text": "",
             "tool_calls": [{"id": "c1", "name": "Read", "input": {"file_path": "/repo/app/models.py"}},
                            {"id": "c2", "name": "Read", "input": {"file_path": "/repo/app/views.py"}}],
             "tool_results": [{"call_id": "c1", "output": "x", "is_error": False, "bytes": 1},
                              {"call_id": "c2", "output": "y", "is_error": False, "bytes": 1}],
             "cost_usd": 0.01, "cost_cum_usd": 0.01}
STEP_SUBMIT = {"type": "step", "step": 2, "phase": "verify", "reasoning": "", "text": "",
               "tool_calls": [{"id": "c3", "name": "submit_record", "input": {"record": RECORD}}],
               "tool_results": [{"call_id": "c3", "output": json.dumps({"accepted": True}),
                                 "is_error": False, "bytes": 20}],
               "cost_usd": 0.01, "cost_cum_usd": 0.02}
GATE = {"risk": "high", "third_party": [], "human_cells": ["purposes"],
        "summary": "RECORD READY FOR REVIEW - t01\nRisk: HIGH. avatar.files does not reach erasure.\n\nbody"}
END = {"type": "run_end", "stop_condition": "accepted", "steps": 2, "tool_calls_total": 3, "submits": 1,
       "verify_rounds": 0, "wall_s": 3.2, "cost_usd": 0.02, "record_path": "/out/record.json", "note": None}

CHECK = """
var out = {};
openRun(RUN, false);
out.start = byId("now-line").textContent;
out.simpleHidden = byId("simple").hidden;
apply({ kind: "trace", data: JSON.stringify(STEP_READ) });
out.reading = byId("now-line").textContent;
out.progress = byId("now-progress").textContent;
out.files = byId("now-files").textContent;
apply({ kind: "trace", data: JSON.stringify(STEP_SUBMIT) });
out.submitted = byId("now-line").textContent;
out.findingsBeforeGate = byId("findings-card").hidden;
apply({ kind: "gate", data: JSON.stringify(GATE) });
out.gate = byId("now-line").textContent;
out.status = byId("run-status").textContent;
out.columns = byId("run-columns").className;
out.findings = byId("findings-card").textContent;
apply({ kind: "trace", data: JSON.stringify(END) });
apply({ kind: "done", data: JSON.stringify({ status: "accepted" }) });
drawRecord(RECORD);
out.finished = byId("now-line").textContent;
out.statusEnd = byId("run-status").textContent;
out.findingsAfter = byId("findings-card").textContent;
out.endCard = byId("steps")._children.filter(function (c) { return c.className.indexOf("end-card") >= 0; })[0].textContent;
setView("details");
out.detailsHidesSimple = byId("simple").hidden;
out.detailsColumns = byId("run-columns").className;
console.log(JSON.stringify(out));
process.exit(0);
"""


@pytest.fixture(scope="module")
def view(tmp_path_factory: pytest.TempPathFactory) -> dict:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not on PATH, so the page's script cannot run here")
    page = PAGE.read_text(encoding="utf-8")
    script = re.search(r"<script>(.*)</script>", page, re.S)
    assert script is not None, "the page has no script block"
    consts = "".join(f"var {name} = {json.dumps(value)};\n" for name, value in [
        ("RUN", RUN), ("RECORD", RECORD), ("STEP_READ", STEP_READ), ("STEP_SUBMIT", STEP_SUBMIT),
        ("GATE", GATE), ("END", END)])
    target = tmp_path_factory.mktemp("page") / "simple.js"
    target.write_text(STUB.read_text(encoding="utf-8") + script.group(1) + consts + CHECK, encoding="utf-8")
    done = subprocess.run([node, str(target)], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])


def test_the_now_line_reads_the_tool_calls_back_as_a_sentence(view: dict) -> None:
    assert view["start"] == "Starting the scan."
    assert view["simpleHidden"] is False
    assert view["reading"] == "Reading app/models.py, app/views.py."
    assert view["progress"] == "Step 1 · 2 tool calls · 2 files read"
    assert "app/models.py" in view["files"] and "app/views.py" in view["files"]
    assert view["submitted"].startswith("The verifier accepted the record on attempt 1")


def test_the_findings_card_opens_with_the_gate_and_names_the_store_the_line_and_the_reason(view: dict) -> None:
    assert view["findingsBeforeGate"] is True
    assert view["gate"].startswith("Scan complete.")
    assert view["status"] == "waiting for your approval"
    assert "simple" in view["columns"].split() and "gate-open" in view["columns"].split()
    text = view["findings"]
    assert "1 of 2 stores is not proven erased." in text
    assert "delete_account (app/views.py:9)" in text
    assert "avatar.files" in text and "NOT ERASED" in text and "app/models.py:14" in text
    assert "No receiver removes the file when the row goes." in text
    assert "Reaching erasure: members." in text
    assert "members" in text and "ERASED" in text
    assert "Approve at the checkpoint below" in text
    assert "requires human completion" in text


def test_the_finished_run_says_so_in_plain_words_and_links_the_record(view: dict) -> None:
    assert view["finished"] == "Finished. The record is written."
    assert view["statusEnd"] == "finished"
    assert "Open the full record" in view["findingsAfter"] and "record.md" in view["findingsAfter"]
    assert "Approve at the checkpoint" not in view["findingsAfter"]
    assert "record written" in view["endCard"]


def test_details_is_the_page_as_it_was(view: dict) -> None:
    assert view["detailsHidesSimple"] is True
    assert "simple" not in view["detailsColumns"].split()
