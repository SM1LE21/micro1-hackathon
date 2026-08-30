"""`reverify.py` over a synthetic results tree (ADR 0008 item 4).

Offline and model-free. The spool each test writes is built the way
`art30/brains/mcp_server.py` builds it -- the arm's own `handle_submit`, then
`loop._feedback_dict` -- and the `metrics.json` beside it the way `cells.finish_cell`
writes it, so what is compared here is what a local-brain run commits. Both halves of the
replay are covered: a tampered submission, and a tampered record or metrics file, which
are the two artefacts the reported table is actually built from.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from art30.arm import RunCtx
from art30.config import Config
from art30.loop import _feedback_dict
from art30.tools import ToolCtx
from evals.harness import reverify, score
from evals.harness.plan import manifest
from tests.test_e2e_advanced import S10_LIE, record_of

FIXTURES = Path(__file__).resolve().parents[1] / "evals" / "fixtures" / "synthetic"


def _feedback(arm_name: str, case: str, record: dict, attempt: int) -> dict:
    """What the MCP server spooled for this submission, produced by the same two calls."""
    arm = reverify.load_arm(arm_name)
    root = FIXTURES / case
    ctx = RunCtx(case=case, arm=arm_name, seed=1, root=root, tools=ToolCtx(root=root),
                 trace=reverify._NullTrace(), cfg=Config(approve="auto"))  # type: ignore[arg-type]
    ctx.submits = attempt
    answer = arm.handle_submit(record, ctx)
    return {"accepted": bool(answer.accepted), **_feedback_dict(answer)}


def _end(run_dir: Path) -> dict:
    return {"type": "run_end", "stop_condition": "accepted", "steps": 4, "tool_calls_total": 6,
            "submits": 1, "verify_rounds": 0, "cost_usd": 0.4,
            "record_path": str(run_dir / "record.json")}


def _spool(tree: Path, arm: str, case: str, submissions: list[dict], *, nested: bool = True,
           scored: bool = True) -> Path:
    """One run directory as `art30/brains/driver.py` and `cells.finish_cell` leave it:
    the spool, the record the run delivered, its trace and the metrics it was scored at."""
    run_dir = tree / "runs" / arm / case / "s1"
    target = (run_dir / "brain") if nested else run_dir
    target.mkdir(parents=True, exist_ok=True)
    (target / "submissions.jsonl").write_text(
        "".join(json.dumps(line) + "\n" for line in submissions), encoding="utf-8")
    if not scored:
        return run_dir
    record = submissions[-1]["record"]
    (run_dir / "record.json").write_text(json.dumps(record), encoding="utf-8")
    trace = tree / "runs" / "traces" / arm / f"{case}-s1.jsonl"
    trace.parent.mkdir(parents=True, exist_ok=True)
    trace.write_text(json.dumps(_end(run_dir)) + "\n", encoding="utf-8")
    data, sha = manifest(case, reverify.MANIFESTS)
    metrics = score.score_run(record, data, _end(run_dir), repo_root=FIXTURES / case,
                              arm=arm, seed=1, mode="live", manifest_sha256=sha)
    (run_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    return run_dir


def _lines(arm: str, case: str, records: list[dict]) -> list[dict]:
    return [{"attempt": i, "record": record, "feedback": _feedback(arm, case, record, i)}
            for i, record in enumerate(records, start=1)]


@pytest.fixture(scope="module")
def baseline_lines() -> list[dict]:
    """One schema-invalid attempt, then the valid record: the baseline's two answers."""
    return _lines("baseline", "D01", [{"schema_version": "1"}, record_of("D01")])


@pytest.fixture(scope="module")
def advanced_lines() -> list[dict]:
    """S10's dead-helper lie, rejected, then the record the verifier accepts."""
    return _lines("advanced", "S10", [record_of("S10", edits={"uploads": S10_LIE}),
                                      record_of("S10")])


def test_a_clean_tree_reverifies_every_submission_and_every_record(
    tmp_path: Path, baseline_lines, advanced_lines, capsys: pytest.CaptureFixture
) -> None:
    _spool(tmp_path, "baseline", "D01", baseline_lines)
    _spool(tmp_path, "advanced", "S10", advanced_lines)

    assert reverify.main(["--runs", str(tmp_path / "runs")]) == 0

    assert "reverified 4 submissions and 2 records in 2 runs, 0 mismatches" in capsys.readouterr().out


def test_a_tampered_record_is_a_failure_naming_the_run_and_the_attempt(
    tmp_path: Path, advanced_lines, capsys: pytest.CaptureFixture
) -> None:
    """The recorded feedback stays; the record it answered is edited to claim erasure."""
    tampered = json.loads(json.dumps(advanced_lines))
    tampered[1]["record"]["stores"] = [
        dict(store, erasure=S10_LIE) if store["name"] == "uploads" else store
        for store in tampered[1]["record"]["stores"]]
    _spool(tmp_path, "advanced", "S10", tampered)

    assert reverify.main(["--runs", str(tmp_path / "runs")]) == 1

    out = capsys.readouterr().out
    assert "advanced/S10-s1 attempt 2: the verifier no longer answers what was recorded" in out
    assert "reverified 2 submissions and 1 records in 1 runs, 1 mismatches" in out


def test_an_edited_metrics_file_is_a_mismatch(tmp_path: Path, advanced_lines,
                                              capsys: pytest.CaptureFixture) -> None:
    """The scored table is built from `metrics.json`; nothing else re-reads it."""
    run_dir = _spool(tmp_path, "advanced", "S10", advanced_lines)
    metrics = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))
    metrics.update(f1=0.5, precision=0.5, recall=0.5)
    (run_dir / "metrics.json").write_text(json.dumps(metrics), encoding="utf-8")

    assert reverify.main(["--runs", str(tmp_path / "runs")]) == 1

    out = capsys.readouterr().out
    assert "advanced/S10-s1: f1 was 0.5, re-scores 1.0" in out
    assert "reverified 2 submissions and 1 records in 1 runs, 3 mismatches" in out


def test_a_record_with_stores_deleted_is_a_mismatch(tmp_path: Path, advanced_lines,
                                                    capsys: pytest.CaptureFixture) -> None:
    """The other artefact the table is built from: the record the run delivered."""
    run_dir = _spool(tmp_path, "advanced", "S10", advanced_lines)
    record = json.loads((run_dir / "record.json").read_text(encoding="utf-8"))
    record["stores"] = record["stores"][:1]
    (run_dir / "record.json").write_text(json.dumps(record), encoding="utf-8")

    assert reverify.main(["--runs", str(tmp_path / "runs")]) == 1

    out = capsys.readouterr().out
    assert "advanced/S10-s1: recall was 1.0, re-scores" in out
    assert "advanced/S10-s1: pass was True, re-scores False" in out


def test_a_run_that_recorded_submissions_and_no_metrics_cannot_be_re_scored(
    tmp_path: Path, baseline_lines, capsys: pytest.CaptureFixture
) -> None:
    _spool(tmp_path, "baseline", "D01", baseline_lines, scored=False)

    assert reverify.main(["--runs", str(tmp_path / "runs")]) == 1

    assert "baseline/D01-s1: recorded submissions but no metrics.json" in capsys.readouterr().out


def test_a_spool_written_beside_the_record_is_found_too(tmp_path: Path, baseline_lines) -> None:
    """`<run>/submissions.jsonl` and `<run>/brain/submissions.jsonl` are the same run."""
    _spool(tmp_path, "baseline", "D01", baseline_lines, nested=False)

    assert reverify.main(["--runs", str(tmp_path / "runs")]) == 0


def test_the_trace_root_follows_the_runs_tree_and_a_flag_overrides_it(
    tmp_path: Path, advanced_lines
) -> None:
    """Section 9: a sweep outside `results/runs` took its traces with it, and the run's
    stop condition decides `pass`, so reading the wrong root re-scores every run crashed."""
    run_dir = _spool(tmp_path, "advanced", "S10", advanced_lines)
    moved = tmp_path / "elsewhere"
    (tmp_path / "runs" / "traces").rename(moved)

    assert reverify.main(["--runs", str(tmp_path / "runs")]) == 1
    assert reverify.main(["--runs", str(tmp_path / "runs"), "--traces", str(moved)]) == 0
    assert json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))["pass"] is True


def test_a_tree_with_no_local_brain_run_is_not_a_failure(tmp_path: Path,
                                                         capsys: pytest.CaptureFixture) -> None:
    """An `api` sweep commits no submissions; `make eval-replay` still runs this target."""
    (tmp_path / "runs").mkdir()

    assert reverify.main(["--runs", str(tmp_path / "runs")]) == 0

    assert "reverified 0 submissions and 0 records in 0 runs, 0 mismatches" in capsys.readouterr().out


def test_a_run_directory_outside_the_arm_case_seed_layout_is_a_harness_error(
    tmp_path: Path, baseline_lines
) -> None:
    (tmp_path / "runs" / "loose").mkdir(parents=True)
    (tmp_path / "runs" / "loose" / "submissions.jsonl").write_text(
        json.dumps(baseline_lines[0]) + "\n", encoding="utf-8")

    assert reverify.main(["--runs", str(tmp_path / "runs")]) == 1


def test_a_half_written_submission_line_is_a_failure_not_an_exception(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "baseline" / "D01" / "s1" / "brain"
    run_dir.mkdir(parents=True)
    (run_dir / "submissions.jsonl").write_text('{"attempt": 1, "record": {"sch', encoding="utf-8")

    assert reverify.main(["--runs", str(tmp_path / "runs")]) == 1
