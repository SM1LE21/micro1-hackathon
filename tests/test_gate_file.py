"""`--approve file`: the request on disk, the decision waited for, the timeout.

ADR 0007 is the surface under test and `advanced/gate.py` is the whole implementation:
no server, no model, no repository. The decision is written by a thread, which is what
`art30 serve` does from its request handler, so the timing here is the real timing.

Every test names its own `out_dir` under `tmp_path`: a test that let the default
stand would be writing into `results/`.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

from advanced import gate as terminal
from tests.verify.test_check import USER_STORE, cite, erasure, field, record, store

VENDOR = store("stripe", "third_party", cite("app/models.py", 4, "User"),
               {"file": "app/models.py", "line": 4},
               [field("email", "contact", "app/models.py", 5)],
               erasure("external_manual"))


@pytest.fixture(autouse=True)
def _short_wait(monkeypatch):
    """No test may inherit the 1800 s default from the environment."""
    monkeypatch.setenv(terminal.TIMEOUT_VAR, "10")


@pytest.fixture
def printed():
    lines: list[str] = []
    return lines, lines.append


def write_after(path: Path, delay: float, payloads: list[str]) -> threading.Thread:
    """The website's side of the exchange: one write per payload, `delay` apart."""
    def run() -> None:
        for payload in payloads:
            time.sleep(delay)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(payload, encoding="utf-8")

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread


def decision_file(out_dir: Path) -> Path:
    return out_dir / terminal.GATE_DIR / terminal.DECISION_NAME


def submitted() -> dict:
    return record([USER_STORE, VENDOR])


def run_gate(out_dir: Path, say, rating: str = "high") -> object:
    found = submitted()
    return terminal.decide(found, rating, terminal.gate_summary(found, rating), "file",
                           say=say, out_dir=out_dir)


# ---------------------------------------------------------------------------
# the request
# ---------------------------------------------------------------------------
def test_the_request_carries_the_screen_in_fields(tmp_path, printed):
    """The documented shape, sorted keys, and the summary the terminal printed."""
    lines, say = printed
    thread = write_after(decision_file(tmp_path), 0.25, ['{"approved": true}'])
    decision = run_gate(tmp_path, say)
    thread.join(timeout=5)

    raw = (tmp_path / terminal.GATE_DIR / terminal.REQUEST_NAME).read_text(encoding="utf-8")
    request = json.loads(raw)
    assert sorted(request) == ["human_cells", "risk", "summary", "third_party", "written_at"]
    assert list(request) == sorted(request), "the file is written with sorted keys"
    assert request["risk"] == "high"
    assert request["summary"] == decision.summary == lines[2]
    assert request["third_party"] == [
        {"store": "stripe", "where": "app/models.py:4", "kinds": list(terminal.KINDS)}]
    assert request["human_cells"][0] == "controller identity and contact"
    assert request["human_cells"][-1] == "retention justification"
    assert len(request["human_cells"]) == 8
    assert request["written_at"].endswith("Z") and request["written_at"][4] == "-"


def test_the_terminal_still_prints_the_block_and_names_the_file(tmp_path, printed):
    """The server relays this stdout: the banner and the block print in file mode too."""
    lines, say = printed
    thread = write_after(decision_file(tmp_path), 0.25, ['{"approved": false}'])
    run_gate(tmp_path, say)
    thread.join(timeout=5)

    assert lines[0] == "\n[gate] human checkpoint · risk HIGH"
    assert "--approve auto" not in lines[0]
    assert "RECORD READY FOR REVIEW - app" in lines[2]
    assert lines[-1] == f"[gate] waiting for {decision_file(tmp_path)}"


def test_a_record_with_no_third_party_store_lists_none(tmp_path, printed):
    _, say = printed
    thread = write_after(decision_file(tmp_path), 0.25, ['{"approved": true}'])
    found = record([USER_STORE])
    terminal.decide(found, "low", terminal.gate_summary(found, "low"), "file",
                    say=say, out_dir=tmp_path)
    thread.join(timeout=5)

    request = json.loads((tmp_path / terminal.GATE_DIR / terminal.REQUEST_NAME).read_text())
    assert request["third_party"] == []


def test_the_human_cells_are_the_ones_the_terminal_prints():
    """One list, one wording: the page cannot drift from `HUMAN_CELLS`."""
    assert " ".join(terminal.HUMAN_CELLS.split()) == (
        ", ".join(terminal.human_cells()) + ".")


# ---------------------------------------------------------------------------
# the decision
# ---------------------------------------------------------------------------
def test_a_decision_written_half_a_second_later_is_honoured(tmp_path, printed):
    """The wait is measured, not assumed: `wait_s` is what the trace carries."""
    _, say = printed
    thread = write_after(decision_file(tmp_path), 0.5, [json.dumps(
        {"approved": True, "edits": {"stores.stripe.recipient_kind": "processor"}})])
    decision = run_gate(tmp_path, say)
    thread.join(timeout=5)

    assert (decision.approved, decision.by) == (True, "human")
    assert decision.edits == {"stores.stripe.recipient_kind": "processor"}
    assert decision.human_completions() == {"recipient_kind": {"stripe": "processor"}}
    assert 0.5 <= decision.wait_s < 3.0
    assert decision.risk == "high"


def test_a_rejection_is_a_human_rejection(tmp_path, printed):
    _, say = printed
    thread = write_after(decision_file(tmp_path), 0.25, ['{"approved": false}'])
    decision = run_gate(tmp_path, say)
    thread.join(timeout=5)

    assert (decision.approved, decision.by, decision.edits) == (False, "human", {})
    assert decision.summary.startswith("RECORD READY FOR REVIEW"), (
        "a rejection by a person quotes the record, not the timeout")


def test_a_malformed_file_is_waited_through_and_the_next_one_decides(tmp_path, printed):
    """A writer mid-flush is not a decision; the gate keeps waiting."""
    _, say = printed
    thread = write_after(decision_file(tmp_path), 0.3,
                         ['{"approved": tr', '{"approved": true}'])
    decision = run_gate(tmp_path, say)
    thread.join(timeout=5)

    assert (decision.approved, decision.by) == (True, "human")
    assert decision.wait_s >= 0.6


def test_a_json_object_without_a_boolean_approved_is_not_a_decision(tmp_path, printed):
    _, say = printed
    thread = write_after(decision_file(tmp_path), 0.3,
                         ['{"edits": {}}', '{"approved": "yes"}', '{"approved": true}'])
    decision = run_gate(tmp_path, say)
    thread.join(timeout=5)

    assert decision.approved is True and decision.wait_s >= 0.9


def test_the_gate_deletes_nothing(tmp_path, printed):
    """Both files survive the run: the exchange is the audit trail of the checkpoint."""
    _, say = printed
    thread = write_after(decision_file(tmp_path), 0.25, ['{"approved": true}'])
    run_gate(tmp_path, say)
    thread.join(timeout=5)

    assert (tmp_path / terminal.GATE_DIR / terminal.REQUEST_NAME).is_file()
    assert decision_file(tmp_path).is_file()


def test_a_decision_left_by_an_earlier_gate_is_moved_aside(tmp_path, printed, monkeypatch):
    """Two runs of one case share `--out`, so run two would inherit run one's answer.

    Honoured, it would reach the checkpoint line as `by: "human"` with `wait_s` 0.0:
    a record signed off by a person who never saw this run.
    """
    lines, say = printed
    monkeypatch.setenv(terminal.TIMEOUT_VAR, "0.4")
    decision_file(tmp_path).parent.mkdir(parents=True)
    decision_file(tmp_path).write_text('{"approved": true}', encoding="utf-8")
    decision = run_gate(tmp_path, say)

    assert decision.approved is False and decision.wait_s >= 0.4
    assert not decision_file(tmp_path).exists()
    kept = sorted((tmp_path / terminal.GATE_DIR).glob(f"{terminal.DECISION_NAME}.*.stale"))
    assert len(kept) == 1, "the old decision is stamped and kept, not deleted"
    assert json.loads(kept[0].read_text(encoding="utf-8")) == {"approved": True}
    assert [line for line in lines if line.startswith("  a decision was already here")]


# ---------------------------------------------------------------------------
# the edits
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("edits, note", [
    ({"stores.mailgun.recipient_kind": "processor"},
     "no third-party store named mailgun in this record"),
    ({"stores.stripe.recipient_kind": "vendor"},
     "vendor is not one of unknown | internal | processor | external_controller"),
    ({"stores.stripe.kind": "processor"},
     "the gate sets stores.<name>.recipient_kind and nothing else"),
    ({"stores.user.recipient_kind": "internal"},
     "no third-party store named user in this record"),
    ({"stores.s3.avatars.recipient_kind": "processor"},
     "a store name with a dot cannot be addressed at the gate"),
])
def test_an_edit_this_record_cannot_carry_is_ignored_with_a_note(tmp_path, printed,
                                                                 edits, note):
    lines, say = printed
    thread = write_after(decision_file(tmp_path), 0.25,
                         [json.dumps({"approved": True, "edits": edits})])
    decision = run_gate(tmp_path, say)
    thread.join(timeout=5)

    assert decision.approved is True and decision.edits == {}
    assert decision.human_completions() is None
    notes = [line for line in lines if line.strip().startswith("ignored")]
    assert notes == [f"  ignored {list(edits)[0]}: {note}"]


def test_an_explicit_unknown_is_no_edit_at_all(tmp_path, printed):
    """`unknown` is the default the loop writes anyway; the ask path drops it too."""
    _, say = printed
    thread = write_after(decision_file(tmp_path), 0.25, [json.dumps(
        {"approved": True, "edits": {"stores.stripe.recipient_kind": "unknown"}})])
    decision = run_gate(tmp_path, say)
    thread.join(timeout=5)

    assert decision.edits == {} and decision.human_completions() is None


def test_edits_that_are_not_an_object_are_ignored_whole(tmp_path, printed):
    lines, say = printed
    thread = write_after(decision_file(tmp_path), 0.25,
                         ['{"approved": true, "edits": ["stripe"]}'])
    decision = run_gate(tmp_path, say)
    thread.join(timeout=5)

    assert decision.edits == {}
    assert "  ignored edits: expected an object of stores.<name>.recipient_kind, got list" in lines


# ---------------------------------------------------------------------------
# the timeout
# ---------------------------------------------------------------------------
def test_a_decision_that_never_arrives_is_a_rejection(tmp_path, printed, monkeypatch):
    """The note the loop turns into `gate_rejected` says nobody answered."""
    lines, say = printed
    monkeypatch.setenv(terminal.TIMEOUT_VAR, "0.4")
    decision = run_gate(tmp_path, say)

    assert (decision.approved, decision.by) == (False, "human")
    assert 0.4 <= decision.wait_s < 3.0, "the trace carries the wait, not the ceiling"
    assert decision.risk == "high" and decision.edits == {}
    first = decision.summary.splitlines()[0]
    assert first == (f"No decision arrived within 0.4 s;"
                     f" {decision_file(tmp_path)} was never written.")
    assert f"  {first}" in lines
    assert "RECORD READY FOR REVIEW - app" in decision.summary
    assert not decision_file(tmp_path).exists()


@pytest.mark.parametrize("raw", ["soon", "nan", "inf", "1e400", "0", "-5"])
def test_a_wait_the_gate_cannot_reach_falls_back_to_the_default(tmp_path, printed,
                                                                monkeypatch, raw):
    """`nan` fails every deadline and `inf` passes none: either polls until killed.

    Zero and below go the other way and return before anyone can answer, writing a
    wait into the trace that nobody waited. All four parse; none is a wait.
    """
    lines, say = printed
    monkeypatch.setenv(terminal.TIMEOUT_VAR, raw)
    thread = write_after(decision_file(tmp_path), 0.25, ['{"approved": true}'])
    decision = run_gate(tmp_path, say)
    thread.join(timeout=5)

    assert decision.approved is True and decision.wait_s >= 0.25
    assert (f"  ART30_GATE_TIMEOUT must be a positive number of seconds ({raw});"
            " waiting 1800 s") in lines


def test_the_default_timeout_is_the_one_adr_0007_names(monkeypatch):
    monkeypatch.delenv(terminal.TIMEOUT_VAR, raising=False)
    assert terminal._timeout(lambda line: None) == 1800.0
    assert terminal.POLL_S == 0.25


# --------------------------- the modes it did not change -------------------
def test_auto_writes_no_gate_files(tmp_path, printed):
    """`file` split the auto branch off `approve != "ask"`; auto still writes nothing.
    The rest of the auto and ask paths is `tests/test_advanced_arm.py`."""
    _, say = printed
    found = submitted()
    decision = terminal.decide(found, "high", terminal.gate_summary(found, "high"),
                               "auto", say=say, out_dir=tmp_path)

    assert (decision.by, decision.wait_s) == ("simulated", 0.0)
    assert not (tmp_path / terminal.GATE_DIR).exists()


def test_ask_writes_no_gate_files(monkeypatch, tmp_path, printed):
    _, say = printed
    answers = iter(["processor", "y"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    found = submitted()
    decision = terminal.decide(found, "high", terminal.gate_summary(found, "high"),
                               "ask", say=say, out_dir=tmp_path)

    assert (decision.approved, decision.by) == (True, "human")
    assert decision.edits == {"stores.stripe.recipient_kind": "processor"}
    assert not (tmp_path / terminal.GATE_DIR).exists()


def test_the_default_out_dir_is_outside_the_eval_s_results(tmp_path):
    """A gate nobody routed writes beside the website's runs, never into a result."""
    assert terminal.UNROUTED == Path("results/web/unrouted")
    assert "runs" not in terminal.UNROUTED.parts
