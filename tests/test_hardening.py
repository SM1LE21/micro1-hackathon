"""Adversarial passes over the jail, the loop and the harness. Offline, no key.

Every input here is one a hostile or broken model could produce: a path that
leaves the root, a tool call with the wrong keys, two submits in one turn, a
five-megabyte record, a child that never returns. The rule under test is the
one the runtime states about itself -- a tool never raises, a run always writes
a `run_end`, a pre-flight gate refuses before it spends a call -- and every
trace a run here produces is handed to the shipped validator, because a trace
that fails `check_trace` is a trace the sweep cannot publish.

Nothing in this file writes under `results/` or `traces/` (ADR 0006 item 3).
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
from pathlib import Path
from typing import Iterator

import pytest

from art30 import llm, tools
from art30.arm import Decision
from art30.config import Config
from art30.loop import CaseRef, run
from art30.tools import ToolCtx, ToolError, dispatch
from baseline.arm import BaselineArm
from conftest import mkrepo
from evals.harness import run as harness
from evals.harness.trace_check import check_trace
from test_loop import record_for
from test_run import _trace_lines, fake_launch

USAGE = {"input": 100, "cache_read": 0, "cache_write": 40, "output": 200}
MAX_FILE_BYTES = 2_000_000  # art30/tools.py; the 10 MB file below is five times it


# --- (a) the jail ------------------------------------------------------------------------


@pytest.fixture()
def hostile(tmp_path: Path) -> ToolCtx:
    """One repository carrying every shape a file is not supposed to have."""
    root = mkrepo(tmp_path / "fx", {"alpha.py": "ALPHA = 1\n", "crlf.py": "one\r\ntwo\r\n"})
    (tmp_path / "outside.py").write_text("SECRET = 1\n", encoding="utf-8")
    (tmp_path / "outside").mkdir()
    (tmp_path / "outside" / "secret.py").write_text("SECRET = 2\n", encoding="utf-8")
    (root / "link.py").symlink_to(tmp_path / "outside.py")
    (root / "linkdir").symlink_to(tmp_path / "outside", target_is_directory=True)
    (root / "adir.py").mkdir()  # a directory wearing a file's name
    (root / "binary.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00SECRET\x00")
    (root / "bad_utf8.py").write_bytes(b"import os\n\xff\xfe SECRET\n")
    with (root / "big.py").open("wb") as handle:
        handle.truncate(10 * 1024 * 1024)  # sparse: ten megabytes, written instantly
    return ToolCtx(root=root.resolve())


def _read(path: str) -> tuple[str, dict]:
    return "read_file", {"path": path, "start_line": 1, "end_line": None}


JAIL: tuple[tuple[str, dict, str], ...] = (
    (*_read("../outside.py"), "escapes the repository root"),
    (*_read("a/../../outside.py"), "escapes the repository root"),
    (*_read("/etc/passwd"), "must be relative"),
    (*_read("link.py"), "escapes the repository root"),
    (*_read("linkdir/secret.py"), "escapes the repository root"),
    (*_read("mo\x00dels.py"), "null"),
    (*_read("big.py"), "larger than"),
    (*_read("binary.png"), "not UTF-8 text"),
    (*_read("bad_utf8.py"), "not UTF-8 text"),
    (*_read("adir.py"), "not a file"),
    (*_read("nope.py"), "not a file"),
    ("list_tree", {"path": "alpha.py", "max_depth": 4}, "not a directory"),
    ("grep", {"pattern": "(unclosed", "path": ".", "glob": "*.py", "max_results": 5},
     "invalid regular expression"),
    ("grep", {"pattern": "x", "path": "../outside", "glob": "*.py", "max_results": 5},
     "escapes the repository root"),
)


@pytest.mark.parametrize("name,args,expected", JAIL, ids=[str(row[1]) for row in JAIL])
def test_a_hostile_tool_call_is_a_message_and_never_an_exception(
    hostile: ToolCtx, name: str, args: dict, expected: str
) -> None:
    output, is_error = dispatch(name, args, hostile)
    assert is_error, f"{name}{args} was accepted"
    assert expected in output.lower() or expected in output
    assert str(hostile.root) not in output  # no absolute path reaches the model


def test_the_jail_raises_for_a_direct_caller_rather_than_returning_a_path(
    hostile: ToolCtx
) -> None:
    for path in ("../outside.py", "/etc/passwd", "link.py", "linkdir/secret.py"):
        with pytest.raises(ToolError):
            tools.resolve(hostile.root, path)


def test_list_tree_names_a_symlinked_directory_without_descending_it(hostile: ToolCtx) -> None:
    tree = tools.list_tree(hostile, ".", 4)
    assert "linkdir" in tree and "secret.py" not in tree
    assert "adir.py/" in tree  # a directory is a directory whatever it is called


def test_grep_walks_past_every_file_it_cannot_read(hostile: ToolCtx) -> None:
    """The oversized, the binary and the invalid file are skipped, not fatal."""
    assert tools.grep(hostile, "SECRET", ".", "*", 100) == "no matches\n"
    assert tools.grep(hostile, "ALPHA", ".", "*.py", 100) == "alpha.py:1: ALPHA = 1\n"


def test_no_tool_output_carries_a_carriage_return(hostile: ToolCtx) -> None:
    """Trace check 1 refuses a CR byte, and tool output is copied into the trace."""
    assert tools.read_file(hostile, "crlf.py") == "1: one\n2: two\n"
    for name, args in (("list_tree", {"path": ".", "max_depth": 4}),
                       ("grep", {"pattern": "one", "path": ".", "glob": "*.py",
                                 "max_results": 100}),
                       _read("crlf.py")):
        output, is_error = dispatch(name, args, hostile)
        assert not is_error and "\r" not in output


# --- (b) the loop, driven by a scripted model ---------------------------------------------


def _response(blocks: list[dict], stop: str = "tool_use") -> llm.Response:
    return llm.Response(content=[{"type": "thinking", "thinking": "reading"}] + blocks,
                        stop_reason=stop, stop_details=None, usage=dict(USAGE),
                        request_id="req_test")


def _use(call_id: str, name: str, payload: dict) -> dict:
    return {"type": "tool_use", "id": call_id, "name": name, "input": payload}


def _submit(call_id: str, record: dict) -> dict:
    return _use(call_id, "submit_record", {"record": record})


QUIET = _response([{"type": "text", "text": "I will read the models next."}], stop="end_turn")


@pytest.fixture()
def script(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[llm.Response]]:
    """Responses served by step number; past the end, the last one repeats forever."""
    responses: list[llm.Response] = []

    def fake_call(req: dict, *, cfg: Config, slot: llm.Slot) -> llm.Response:
        assert "system" in req and "tools" in req
        return responses[min(slot.step, len(responses)) - 1]

    monkeypatch.setattr(llm, "call", fake_call)
    yield responses


def _cfg(tmp_path: Path, **over: object) -> Config:
    base = Config(trace_dir=tmp_path / "traces", out_dir=tmp_path / "out",
                  cache_dir=tmp_path / "cache", tool_budget=10)
    return Config(**{**base.__dict__, **over})


def _drive(repo: Path, tmp_path: Path, arm=None, **over: object):
    arm = arm or BaselineArm()
    result = run(CaseRef(id="S01", name=repo.name, root=repo), arm, 1, _cfg(tmp_path, **over))
    return result, tmp_path / "traces" / arm.name / "S01-s1.jsonl"


def _steps(trace: Path) -> list[dict]:
    lines = [json.loads(line) for line in trace.read_text(encoding="utf-8").splitlines()]
    return [line for line in lines if line["type"] == "step"]


def test_a_tool_call_with_a_required_key_missing_is_an_error_result(
    repo: Path, tmp_path: Path, script
) -> None:
    script += [_response([_use("t1", "read_file", {"start_line": 1})]),
               _response([_submit("t2", record_for(repo.name))])]
    result, trace = _drive(repo, tmp_path)

    assert result.stop_condition == "accepted"
    assert _steps(trace)[0]["tool_results"][0]["is_error"] is True
    assert check_trace(trace) == []


def test_an_unknown_tool_name_costs_a_call_and_does_not_stop_the_run(
    repo: Path, tmp_path: Path, script
) -> None:
    script += [_response([_use("t1", "rm_rf", {"path": "/"})]),
               _response([_submit("t2", record_for(repo.name))])]
    result, trace = _drive(repo, tmp_path)

    assert (result.stop_condition, result.tool_calls_total) == ("accepted", 2)
    assert "unknown tool: rm_rf" in _steps(trace)[0]["tool_results"][0]["output"]
    assert check_trace(trace) == []


def test_a_submit_whose_input_has_no_record_key_ends_the_run_rather_than_the_turn(
    repo: Path, tmp_path: Path, script
) -> None:
    """Defect: the loop indexes `input["record"]` (art30/loop.py:229). A model that
    breaks the tool schema kills the run instead of collecting an error result."""
    script.append(_response([_use("t1", "submit_record", {})]))
    result, trace = _drive(repo, tmp_path)

    assert (result.stop_condition, result.submits) == ("api_error", 1)
    assert "KeyError" in (result.note or "")
    assert check_trace(trace) == []  # the run_end still reconciles with the step lines


def test_two_submits_in_one_turn_buy_one_attempt(repo: Path, tmp_path: Path, script) -> None:
    """Invariant A holds in the loop. Checks 8 and 9 are filtered because the
    validator counts `submit_record` blocks and the loop counts attempts; they
    disagree on this trace (reported, not asserted, so a fix does not fail here)."""
    valid = record_for(repo.name)
    script += [_response([_submit("t1", {"schema_version": "1"}), _submit("t2", valid)]),
               _response([_submit("t3", valid)])]
    result, trace = _drive(repo, tmp_path)

    assert (result.stop_condition, result.submits, result.verify_rounds) == ("accepted", 2, 1)
    results = _steps(trace)[0]["tool_results"]
    assert json.loads(results[1]["output"])["reason"] == "one submit_record per turn"
    assert [v for v in check_trace(trace) if "check 8" not in v and "check 9" not in v] == []


def test_a_five_megabyte_record_is_rejected_and_echoed_back_whole(
    repo: Path, tmp_path: Path, script
) -> None:
    """Defect: the rejection quotes the instance, so a 5 MB submit becomes a 5 MB
    tool result in the trace and in the next request (art30/tools.py:289)."""
    script += [_response([_submit("t1", "x" * 5_000_000)]),
               _response([_submit("t2", record_for(repo.name))])]
    result, trace = _drive(repo, tmp_path)

    assert (result.stop_condition, result.verify_rounds) == ("accepted", 1)
    assert _steps(trace)[0]["tool_results"][0]["bytes"] > 5_000_000
    assert check_trace(trace) == []


def test_a_model_that_only_ever_writes_text_stops_after_three_quiet_turns(
    repo: Path, tmp_path: Path, script
) -> None:
    script.append(QUIET)  # the fixture repeats the last response forever
    result, trace = _drive(repo, tmp_path)

    assert (result.stop_condition, result.steps, result.tool_calls_total) == ("no_submission", 3, 0)
    assert check_trace(trace) == []


def test_a_tool_call_resets_the_nudge_count(repo: Path, tmp_path: Path, script) -> None:
    def call(call_id: str) -> llm.Response:
        return _response([_use(call_id, "list_tree", {"path": ".", "max_depth": 2})])

    script += [QUIET, QUIET, call("t1"), QUIET, QUIET, call("t2"), QUIET, QUIET, QUIET]
    result, trace = _drive(repo, tmp_path)

    assert (result.stop_condition, result.steps) == ("no_submission", 9)
    assert check_trace(trace) == []


def test_pause_turn_ends_the_run_and_says_why(repo: Path, tmp_path: Path, script) -> None:
    script.append(_response([], stop="pause_turn"))
    result, trace = _drive(repo, tmp_path)

    assert (result.stop_condition, result.steps) == ("api_error", 1)
    assert result.note == "pause_turn on a request with no server tools"
    assert check_trace(trace) == []


def test_a_tool_that_raises_an_oserror_is_an_error_result_and_the_run_continues(
    repo: Path, tmp_path: Path, script, monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode(ctx, path, start_line=1, end_line=None):
        raise OSError("device is on fire")

    monkeypatch.setattr(tools, "read_file", explode)
    script += [_response([_use("t1", "read_file", _read("models.py")[1])]),
               _response([_submit("t2", record_for(repo.name))])]
    result, trace = _drive(repo, tmp_path)

    assert result.stop_condition == "accepted"
    first = _steps(trace)[0]["tool_results"][0]
    assert first["is_error"] is True and "device is on fire" in first["output"]
    assert check_trace(trace) == []


def test_a_tool_that_raises_an_unexpected_exception_ends_the_run(
    repo: Path, tmp_path: Path, script, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`dispatch` catches ToolError, OSError, TypeError and ValueError only
    (art30/tools.py:270): any other bug in a tool is a run failure."""
    def explode(ctx, path, start_line=1, end_line=None):
        raise RuntimeError("tool bug")

    monkeypatch.setattr(tools, "read_file", explode)
    script.append(_response([_use("t1", "read_file", _read("models.py")[1])]))
    result, trace = _drive(repo, tmp_path)

    assert result.stop_condition == "api_error" and "RuntimeError" in (result.note or "")
    assert check_trace(trace) == []


class RejectingArm(BaselineArm):
    """The gate's other answer. The loop, not the arm, owns what follows it."""

    name = "advanced"

    def gate(self, record: dict, ctx) -> Decision:
        return Decision(risk="high", approved=False, by="simulated",
                        summary="users holds a contact field and does not reach erasure.\ndetail",
                        wait_s=0.0)


def test_a_rejected_gate_writes_the_draft_and_no_record(
    repo: Path, tmp_path: Path, script
) -> None:
    script.append(_response([_submit("t1", record_for(repo.name))]))
    result, trace = _drive(repo, tmp_path, arm=RejectingArm())

    assert result.stop_condition == "gate_rejected"
    assert result.record_path is None and result.gate["decision"] == "rejected"
    out = tmp_path / "out"
    draft = json.loads((out / "record.draft.json").read_text(encoding="utf-8"))
    assert draft["stores"][0]["name"] == "users"
    assert not (out / "record.json").exists() and not (out / "record.html").exists()
    assert "gate rejected at risk=high" in (result.note or "")
    assert check_trace(trace) == []


# --- (d) the harness ----------------------------------------------------------------------


@pytest.fixture()
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Traces, results and the ledger in a temporary tree; the fixtures stay committed."""
    monkeypatch.setattr(harness, "TRACES", tmp_path / "traces")
    monkeypatch.setattr(harness, "RESULTS", tmp_path / "results")
    monkeypatch.setattr(harness, "ADR_DIR", tmp_path / "adr")
    monkeypatch.delenv("ART30_REPRODUCIBLE", raising=False)
    return tmp_path


def _argv(root: Path, *extra: str, case: str = "S01") -> list[str]:
    return ["--cases", case, "--arms", "baseline,advanced", "--seeds", "1", "--mode", "replay",
            "--jobs", "1", "--out", str(root / "results" / "runs"), *extra]


def _spy(monkeypatch: pytest.MonkeyPatch, launcher=None) -> list[str]:
    """Counts children. A pre-flight refusal must spend none."""
    seen: list[str] = []
    inner = launcher or fake_launch()

    def _launch(cell):
        seen.append(f"{cell.arm}/{cell.case}-s{cell.seed}")
        return inner(cell)

    monkeypatch.setattr(harness, "_launch", _launch)
    return seen


def _ledger(root: Path) -> Path:
    return root / "results" / "test-runs.log"


def _seed_ledger(root: Path, count: int = 2) -> list[str]:
    lines: list[str] = []
    for index in range(count):
        previous = (hashlib.sha256(lines[-1].encode("utf-8")).hexdigest() if lines
                    else harness.ZERO_SHA)
        lines.append(f"2026-08-2{index}T10:00:00Z | 0000000 | baseline,advanced | S08 | 1 |"
                     f" replay | sweep {index} | {previous}")
    _ledger(root).parent.mkdir(parents=True, exist_ok=True)
    _ledger(root).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return lines


def test_one_unknown_case_id_aborts_the_whole_selection(
    sandbox: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    launched = _spy(monkeypatch)
    assert harness.main(_argv(sandbox, case="S01,S99,S02")) == 1
    message = capsys.readouterr().err
    assert "S99" in message and "S01" not in message
    assert launched == [] and not (sandbox / "results" / "runs").exists()


def test_a_stale_spec_sha_refuses_before_the_first_child(
    sandbox: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifests = sandbox / "manifests"
    manifests.mkdir()
    raw = (harness.MANIFESTS / "S01.yaml").read_text(encoding="utf-8")
    stale = raw.replace(raw.split("spec_sha256:")[1].split("\n")[0].strip(), "0" * 64)
    (manifests / "S01.yaml").write_text(stale, encoding="utf-8")
    monkeypatch.setattr(harness, "MANIFESTS", manifests)
    launched = _spy(monkeypatch)

    assert harness.main(_argv(sandbox)) == 4
    assert launched == []


def test_unlock_test_without_a_reason_spends_nothing(
    sandbox: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    launched = _spy(monkeypatch)
    assert harness.main(_argv(sandbox, "--unlock-test", case="S08")) == 1
    assert launched == [] and not _ledger(sandbox).exists()


def test_an_edited_ledger_line_breaks_the_chain_and_appends_nothing(
    sandbox: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The tamper is in the middle of a line, not in its chain field: the next
    line's back-pointer is what catches it."""
    lines = _seed_ledger(sandbox)
    launched = _spy(monkeypatch)
    _ledger(sandbox).write_text("\n".join(lines).replace("sweep 0", "sweep X") + "\n",
                                encoding="utf-8")

    assert harness.main(_argv(sandbox, "--unlock-test", "--reason", "third", case="S08")) == 1
    assert launched == []
    assert len(_ledger(sandbox).read_text(encoding="utf-8").strip().split("\n")) == len(lines)


def test_the_reproducible_flag_suppresses_every_timing_file(
    sandbox: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _spy(monkeypatch)
    monkeypatch.setenv("ART30_REPRODUCIBLE", "1")
    assert harness.main(_argv(sandbox)) == 0
    assert sorted((sandbox / "results").glob("timing*.json")) == []
    cell = harness.Cell(case="S01", arm="advanced", seed=1, repo="r", out="o", trace="t",
                        trace_dir="t", mode="live", approve="auto", timeout=900, unlock=False)
    assert harness._write_timing("live", [{"cell": cell, "wall_s": 1.0}], True, "all") is None
    assert sorted((sandbox / "results").glob("timing*.json")) == []


def _sleeping_launch(seconds: float = 0.05):
    """A child that never returns: it writes a run_start, starts a step line and is killed."""
    def _fake(cell) -> tuple[int, str, bool, float]:
        trace = Path(cell.trace)
        trace.parent.mkdir(parents=True, exist_ok=True)
        head = json.dumps(_trace_lines(cell, "accepted", "b" * 64)[0])
        trace.write_text(head + "\n" + '{"type": "step", "step": 1, "phase": "ag',
                         encoding="utf-8")
        time.sleep(seconds)
        return -1, "", True, seconds
    return _fake


def test_a_timed_out_cell_is_repaired_filed_and_still_validates(
    sandbox: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _spy(monkeypatch, _sleeping_launch())
    assert harness.main(_argv(sandbox, "--arms", "baseline")) == 0

    traces = sandbox / "results" / "runs" / "traces"
    failure = traces / "failures" / "baseline" / "S01-s1.jsonl"
    end = json.loads(failure.read_text(encoding="utf-8").strip().split("\n")[-1])
    assert end["stop_condition"] == "timeout" and end["steps"] == 0
    assert "bytes of a partial line discarded" in end["note"]
    diagnosis = failure.with_suffix(".diagnosis.txt").read_text(encoding="utf-8")
    assert diagnosis.split("\n")[0].split(" · ")[1] == "timeout"
    assert check_trace(failure) == []
    metrics = json.loads((sandbox / "results" / "runs" / "baseline" / "S01" / "s1" /
                          "metrics.json").read_text(encoding="utf-8"))
    assert metrics["run"]["stop_condition"] == "timeout" and metrics["f1"] == 0.0


def test_the_launcher_reports_a_kill_rather_than_raising(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"], stderr=b"half a line \xff")

    monkeypatch.setattr(harness.subprocess, "run", _raise)
    cell = harness.Cell(case="S01", arm="baseline", seed=1, repo="r", out="o", trace="t",
                        trace_dir="t", mode="replay", approve="auto", timeout=1, unlock=False)
    code, stderr, timed_out, wall_s = harness._launch(cell)
    assert (code, timed_out) == (-1, True)
    assert stderr.startswith("half a line ") and wall_s >= 0.0
