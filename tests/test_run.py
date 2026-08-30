"""The runner's planning, its two pre-flight gates and the test-split lock (05-eval-harness.md section 5).

Offline: `run._launch` is the one subprocess seam and every test replaces it with a function that
writes a canned trace and record, so no test needs an API key, a model or a child process.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml

from evals.harness import run

PROMPT_SHA = "a" * 64
STEP_HASH = {"baseline": "b" * 64, "advanced": "b" * 64}
RECORD = {
    "repository": "S01",
    "stores": [{"name": "users", "kind": "relational",
                "fields": [{"name": "email", "category": "contact", "file": "models.py", "line": 15}],
                "erasure": {"verdict": "erased", "evidence": "api/account.py:13"}}],
}


def _trace_lines(cell: run.Cell, stop: str, step_hash: str) -> list[dict]:
    lines = [
        {"type": "run_start", "run_id": f"{cell.arm[:3]}-{cell.case}-s{cell.seed}-0000000",
         "arm": cell.arm, "case": cell.case, "seed": cell.seed, "model": "claude-opus-5",
         "effort": "high", "mode": cell.mode, "prompt_sha": PROMPT_SHA,
         "config": {"max_tokens": 32000, "tool_budget": 60, "submit_budget": 5, "overridden": []},
         "ts": "2026-08-30T09:00:00Z"},
        {"type": "step", "step": 1, "phase": "verify", "ts": "2026-08-30T09:00:10Z",
         "request_id": "req_1", "request_hash": step_hash, "stop_reason": "tool_use",
         "reasoning": "", "text": "", "tool_calls": [{"id": "c1", "name": "submit_record", "input": {}}],
         "tool_results": [{"call_id": "c1", "output": '{"accepted": true}', "is_error": False, "bytes": 18}],
         "usage": {"input": 10, "cache_read": 0, "cache_write": 0, "output": 5},
         "cost_usd": 0.01, "cost_cum_usd": 0.01},
    ]
    if cell.arm == "advanced":
        lines.append({"type": "checkpoint", "tool": "request_approval", "caller": "harness",
                      "risk": "low", "summary": "one store", "decision": "approved",
                      "by": "simulated", "wait_s": 0.0, "human_completions": None,
                      "ts": "2026-08-30T09:00:20Z"})
    lines.append({"type": "run_end", "stop_condition": stop, "steps": 1, "tool_calls_total": 1,
                  "submits": 1, "verify_rounds": 0, "wall_s": 12.5, "cost_usd": 0.01,
                  "record_path": str(Path(cell.out) / "record.json"), "note": None})
    return lines


def fake_launch(stop: str = "accepted", hashes: dict[str, str] | None = None):
    """A child that writes what `art30 scan` writes, without running one."""
    step_hashes = hashes or STEP_HASH

    def _fake(cell: run.Cell) -> tuple[int, str, bool, float]:
        trace = Path(cell.trace)
        trace.parent.mkdir(parents=True, exist_ok=True)
        body = _trace_lines(cell, stop, step_hashes[cell.arm])
        trace.write_text("\n".join(json.dumps(line) for line in body) + "\n", encoding="utf-8")
        out = Path(cell.out)
        out.mkdir(parents=True, exist_ok=True)
        if stop == "accepted":
            (out / "record.json").write_text(json.dumps(RECORD), encoding="utf-8")
        return 0, "", False, 12.5
    return _fake


@pytest.fixture()
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Traces, results and the ledger go to a temporary tree; fixtures stay the committed ones."""
    monkeypatch.setattr(run, "TRACES", tmp_path / "traces")
    monkeypatch.setattr(run, "RESULTS", tmp_path / "results")
    monkeypatch.setattr(run, "ADR_DIR", tmp_path / "adr")
    monkeypatch.delenv("ART30_REPRODUCIBLE", raising=False)
    return tmp_path


def _argv(tmp_path: Path, *extra: str, case: str = "S01") -> list[str]:
    return ["--cases", case, "--arms", "baseline,advanced", "--seeds", "1", "--mode", "replay",
            "--jobs", "1", "--out", str(tmp_path / "results" / "runs"), *extra]


def _traces(tmp_path: Path) -> Path:
    """An --out other than the default takes its traces with it (05 section 9)."""
    return tmp_path / "results" / "runs" / "traces"


# --- selection -------------------------------------------------------------------------------


def test_split_selection_all_is_dev_plus_test_and_never_reserve() -> None:
    data = yaml.safe_load(run.SPLIT_FILE.read_text(encoding="utf-8"))
    dev, test = run.cases_for(data, "dev"), run.cases_for(data, "test")
    assert run.cases_for(data, "all") == dev + test
    assert "R05" not in run.cases_for(data, "all")
    assert run.cases_for(data, "all", include_reserve=True)[-1] == "R05"
    assert len(run.cases_for(data, "all")) == 14  # 84 runs at three seeds and two arms


def test_unknown_case_is_a_harness_error(sandbox: Path) -> None:
    assert run.main(_argv(sandbox, case="S99")) == 1


# --- the lock (section 5.4) -------------------------------------------------------------------


def test_test_split_without_unlock_exits_2(sandbox: Path) -> None:
    assert run.main(_argv(sandbox, case="S08")) == 2


def test_unlock_without_reason_is_a_harness_error(sandbox: Path) -> None:
    assert run.main(_argv(sandbox, "--unlock-test", case="S08")) == 1


def test_ledger_is_appended_and_chained(sandbox: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(run, "_launch", fake_launch())
    for reason in ("first sweep", "second sweep"):
        assert run.main(_argv(sandbox, "--unlock-test", "--reason", reason, case="S08")) == 0
    lines = (sandbox / "results" / "test-runs.log").read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2
    assert lines[0].rsplit("|", 1)[-1].strip() == run.ZERO_SHA
    assert lines[1].rsplit("|", 1)[-1].strip() == hashlib.sha256(lines[0].encode("utf-8")).hexdigest()
    assert lines[0].split("|")[3].strip() == "S08" and lines[0].split("|")[5].strip() == "replay"


def test_broken_chain_exits_1(sandbox: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(run, "_launch", fake_launch())
    assert run.main(_argv(sandbox, "--unlock-test", "--reason", "first", case="S08")) == 0
    ledger = sandbox / "results" / "test-runs.log"
    ledger.write_text(ledger.read_text(encoding="utf-8").replace(run.ZERO_SHA, "f" * 64), encoding="utf-8")
    assert run.main(_argv(sandbox, "--unlock-test", "--reason", "second", case="S08")) == 1


def _seed_live_ledger(sandbox: Path) -> None:
    lines: list[str] = []
    for index in range(2):
        previous = hashlib.sha256(lines[-1].encode("utf-8")).hexdigest() if lines else run.ZERO_SHA
        lines.append(f"2026-08-3{index}T10:00:00Z | 0000000 | baseline,advanced | S08 | 1 | live"
                     f" | sweep {index} | {previous}")
    (sandbox / "results").mkdir(parents=True, exist_ok=True)
    (sandbox / "results" / "test-runs.log").write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_third_live_sweep_exits_3_without_an_adr(sandbox: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(run, "_launch", fake_launch())
    _seed_live_ledger(sandbox)
    argv = _argv(sandbox, "--unlock-test", "--reason", "third", case="S08")
    argv[argv.index("replay")] = "live"
    assert run.main(argv) == 3
    assert run.main(argv + ["--adr", "0099"]) == 3  # the ADR file does not exist


def test_third_live_sweep_runs_with_an_adr_that_names_a_test_sweep(
    sandbox: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(run, "_launch", fake_launch())
    _seed_live_ledger(sandbox)
    (sandbox / "adr").mkdir(parents=True, exist_ok=True)
    (sandbox / "adr" / "0099-third-sweep.md").write_text(
        "status: accepted\n\nA third live test sweep is authorised.\n", encoding="utf-8")
    argv = _argv(sandbox, "--unlock-test", "--reason", "third", "--adr", "0099", case="S08")
    argv[argv.index("replay")] = "live"
    assert run.main(argv) == 0
    assert "ADR 0099" in (sandbox / "results" / "test-runs.log").read_text(encoding="utf-8")


def test_replay_sweeps_do_not_consume_the_live_budget(sandbox: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(run, "_launch", fake_launch())
    _seed_live_ledger(sandbox)
    assert run.main(_argv(sandbox, "--unlock-test", "--reason", "replay of the sweep", case="S08")) == 0


# --- the freeze gate (section 5.1) --------------------------------------------------------------


def test_spec_freeze_mismatch_exits_4(sandbox: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifests = sandbox / "manifests"
    manifests.mkdir()
    data = yaml.safe_load((run.MANIFESTS / "S01.yaml").read_text(encoding="utf-8"))
    data["spec_sha256"] = "0" * 64
    (manifests / "S01.yaml").write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    monkeypatch.setattr(run, "MANIFESTS", manifests)
    monkeypatch.setattr(run, "_launch", fake_launch())
    assert run.main(_argv(sandbox)) == 4


def test_split_mismatch_exits_4(sandbox: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifests = sandbox / "manifests"
    manifests.mkdir()
    data = yaml.safe_load((run.MANIFESTS / "S01.yaml").read_text(encoding="utf-8"))
    data["split"] = "test"
    (manifests / "S01.yaml").write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    monkeypatch.setattr(run, "MANIFESTS", manifests)
    monkeypatch.setattr(run, "_launch", fake_launch())
    assert run.main(_argv(sandbox)) == 4


# --- a completed cell ----------------------------------------------------------------------------


def test_a_run_writes_metrics_and_leaves_no_failure(sandbox: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(run, "_launch", fake_launch())
    assert run.main(_argv(sandbox)) == 0
    metrics = json.loads((sandbox / "results" / "runs" / "advanced" / "S01" / "s1" / "metrics.json")
                         .read_text(encoding="utf-8"))
    assert metrics["case"] == "S01" and metrics["arm"] == "advanced" and metrics["seed"] == 1
    assert metrics["run"]["stop_condition"] == "accepted"
    assert metrics["run"]["gate"] == {"risk": "low", "decision": "approved", "by": "simulated"}
    assert not list(_traces(sandbox).glob("failures/*/*.jsonl"))


def test_a_failed_run_is_copied_with_a_generated_diagnosis(sandbox: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(run, "_launch", fake_launch(stop="max_submits"))
    assert run.main(_argv(sandbox)) == 0
    diagnosis = _traces(sandbox) / "failures" / "baseline" / "S01-s1.diagnosis.txt"
    first = diagnosis.read_text(encoding="utf-8").split("\n")[0]
    assert first.split(" · ")[0] == "baseline/S01-s1"
    assert first.split(" · ")[1] == "max_submits"
    assert len(first.split(" · ")) == 4 and len(first) <= 160
    index = (_traces(sandbox) / "failures" / "README.md").read_text(encoding="utf-8")
    assert "max_submits" in index and "S01" in index


# --- the identity check (01 decision 8) -----------------------------------------------------------


def test_step1_hash_mismatch_between_arms_fails_the_plan(sandbox: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(run, "_launch", fake_launch(hashes={"baseline": "b" * 64, "advanced": "c" * 64}))
    assert run.main(_argv(sandbox)) == 1


def test_matching_step1_hashes_pass(sandbox: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(run, "_launch", fake_launch())
    assert run.main(_argv(sandbox)) == 0


# --- timing (section 6) ----------------------------------------------------------------------------


def test_a_live_subset_never_claims_the_recorded_sweeps_timing_file(
    sandbox: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Section 9 reads results/timing.json as the 84-run sweep; a dev subset is not it."""
    monkeypatch.setattr(run, "_launch", fake_launch())
    argv = _argv(sandbox)
    argv[argv.index("replay")] = "live"
    assert run.main(argv) == 0
    assert not (sandbox / "results" / "timing.json").exists()
    scratch = sorted((sandbox / "results").glob("timing.cases-*.json"))
    timing = json.loads(scratch[0].read_text(encoding="utf-8"))
    assert timing["per_arm"]["advanced"] == {"wall_s_mean": 12.5, "wall_s_std": 0.0, "n": 1}
    assert timing["per_case"]["S01"]["baseline"]["n"] == 1


def test_a_full_live_sweep_writes_timing_json(sandbox: Path) -> None:
    cell = run.Cell(case="S01", arm="advanced", seed=1, repo="r", out="o", trace="t",
                    trace_dir="t", mode="live", approve="auto", timeout=900, unlock=False)
    path = run._write_timing("live", [{"cell": cell, "wall_s": 12.5}], full=True, tag="all")
    assert path == sandbox / "results" / "timing.json" and path.is_file()


def test_replay_writes_the_replay_clock_and_reproducible_writes_neither(
    sandbox: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(run, "_launch", fake_launch())
    assert run.main(_argv(sandbox)) == 0
    assert (sandbox / "results" / "timing.replay.json").is_file()
    (sandbox / "results" / "timing.replay.json").unlink()
    monkeypatch.setenv("ART30_REPRODUCIBLE", "1")
    assert run.main(_argv(sandbox)) == 0
    assert not (sandbox / "results" / "timing.replay.json").exists()
    assert not (sandbox / "results" / "timing.json").exists()


def test_reproducible_does_not_append_to_the_ledger(sandbox: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(run, "_launch", fake_launch())
    monkeypatch.setenv("ART30_REPRODUCIBLE", "1")
    assert run.main(_argv(sandbox, "--unlock-test", "--reason", "replay", case="S08")) == 0
    assert not (sandbox / "results" / "test-runs.log").exists()


# --- the slot, the flags and the seams ---------------------------------------------------------------


def test_a_second_run_of_a_cell_does_not_inherit_the_first_ones_record(
    sandbox: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Section 4.4: a run that produced no record scores zero, whatever an earlier sweep left."""
    monkeypatch.setattr(run, "_launch", fake_launch())
    assert run.main(_argv(sandbox)) == 0
    slot = sandbox / "results" / "runs" / "advanced" / "S01" / "s1"
    assert json.loads((slot / "metrics.json").read_text(encoding="utf-8"))["f1"] > 0.0
    monkeypatch.setattr(run, "_launch", fake_launch(stop="max_submits"))
    assert run.main(_argv(sandbox)) == 0
    metrics = json.loads((slot / "metrics.json").read_text(encoding="utf-8"))
    assert metrics["run"]["stop_condition"] == "max_submits"
    assert (metrics["f1"], metrics["tp"], metrics["fp"], metrics["false_safe"]) == (0.0, 0, 0, 0)
    assert not (slot / "record.json").exists()


def test_fail_fast_stops_launching_not_only_scoring(sandbox: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    launched: list[str] = []
    failing = fake_launch(stop="max_submits")

    def _count(cell: run.Cell) -> tuple[int, str, bool, float]:
        launched.append(f"{cell.arm}/{cell.case}")
        return failing(cell)

    monkeypatch.setattr(run, "_launch", _count)
    assert run.main(_argv(sandbox, "--fail-fast", case="S01,S02")) == 0
    assert len(launched) == 1
    assert len(list((sandbox / "results" / "runs").rglob("metrics.json"))) == 1


def test_the_live_ledger_is_written_even_under_the_replay_flag(
    sandbox: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Section 5.4: one environment variable may not empty the record of a live test sweep."""
    monkeypatch.setenv("ART30_REPRODUCIBLE", "1")
    args = run.build_parser().parse_args(_argv(sandbox, "--unlock-test", "--reason", "live", case="S08"))
    args.mode = "live"
    run._append_ledger(args, ["S08"], [])
    assert "| live |" in (sandbox / "results" / "test-runs.log").read_text(encoding="utf-8")


def test_a_live_sweep_under_the_replay_flag_is_refused(sandbox: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(run, "_launch", fake_launch())
    monkeypatch.setenv("ART30_REPRODUCIBLE", "1")
    argv = _argv(sandbox)
    argv[argv.index("replay")] = "live"
    assert run.main(argv) == 1


def test_truncating_the_ledger_is_detected_against_the_committed_copy(
    sandbox: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The forward chain cannot see a deletion at the end; the committed copy can."""
    monkeypatch.setattr(run, "_launch", fake_launch())
    _seed_live_ledger(sandbox)
    committed = run._ledger_lines()
    monkeypatch.setattr(run, "_committed_ledger", lambda: committed)
    (sandbox / "results" / "test-runs.log").unlink()
    argv = _argv(sandbox, "--unlock-test", "--reason", "third", case="S08")
    argv[argv.index("replay")] = "live"
    assert run.main(argv) == 1


def test_a_synthetic_manifest_without_a_spec_sha_exits_4(
    sandbox: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifests = sandbox / "manifests"
    manifests.mkdir()
    data = yaml.safe_load((run.MANIFESTS / "S01.yaml").read_text(encoding="utf-8"))
    data["spec_sha256"] = None
    (manifests / "S01.yaml").write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    monkeypatch.setattr(run, "MANIFESTS", manifests)
    monkeypatch.setattr(run, "_launch", fake_launch())
    assert run.main(_argv(sandbox)) == 4


def _spy_subprocess(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    calls: list[dict] = []

    class _Done:
        returncode, stdout, stderr = 0, "", ""

    def _run(command, **kwargs):
        calls.append({"command": command, **kwargs})
        return _Done()

    monkeypatch.setattr(run.subprocess, "run", _run)
    return calls


def _cell(**over) -> run.Cell:
    fields = {"case": "S03", "arm": "advanced", "seed": 1, "repo": "repo", "out": "out",
              "trace": "t/advanced/S03-s1.jsonl", "trace_dir": "t", "mode": "replay",
              "approve": "auto", "timeout": 900, "unlock": False}
    return run.Cell(**{**fields, **over})


def test_approve_ask_leaves_the_childs_terminal_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    """art30/cli.py refuses `--approve ask` without a tty, and a pipe swallows the prompt."""
    calls = _spy_subprocess(monkeypatch)
    run._launch(_cell(approve="ask"))
    assert calls[0]["capture_output"] is False
    calls.clear()
    run._launch(_cell(approve="auto"))
    assert calls[0]["capture_output"] is True


def test_the_child_is_told_where_to_write_its_trace(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _spy_subprocess(monkeypatch)
    run._launch(_cell(trace_dir="results/.gate-timing/traces"))
    assert calls[0]["env"]["ART30_TRACE_DIR"] == "results/.gate-timing/traces"


def test_no_settings_file_of_the_users_reaches_a_cell(monkeypatch: pytest.MonkeyPatch) -> None:
    """ADR 0008 item 5: the sweep runs at art30's defaults plus what the sweep itself set.
    `~/.config/art30/config.toml` is not a checkout artefact, so `make eval-replay` from a
    clean checkout does not exclude it; the switch the child is handed does."""
    calls = _spy_subprocess(monkeypatch)
    run._launch(_cell())
    assert calls[0]["env"]["ART30_IGNORE_SETTINGS_FILES"] == "1"


def test_the_trace_root_follows_out(sandbox: Path) -> None:
    assert run.trace_root(run.DEFAULT_OUT) == run.TRACES
    assert run.trace_root("results/.gate-timing") == Path("results/.gate-timing") / "traces"


# --- the timeout path (section 5.3) -----------------------------------------------------------------


def test_partial_line_is_repaired_and_the_note_carries_one_byte_count(tmp_path: Path) -> None:
    trace = tmp_path / "S01-s1.jsonl"
    good = json.dumps({"type": "run_start", "case": "S01"})
    trace.write_text(good + "\n" + '{"type": "step", "ste', encoding="utf-8")
    discarded = run._repair(trace)
    assert discarded == len('{"type": "step", "ste')
    run._append_run_end(trace, "timeout", f"killed at 900s; {discarded} bytes of a partial line discarded", 900.0)
    lines = [json.loads(line) for line in trace.read_text(encoding="utf-8").strip().split("\n")]
    assert lines[-1]["stop_condition"] == "timeout" and lines[-1]["steps"] == 0
    assert lines[-1]["note"].count("bytes") == 1


def test_an_unparseable_submit_result_does_not_kill_the_parent(tmp_path: Path) -> None:
    """The repair path is where malformed traces live; the parent has to file them, not die."""
    trace = tmp_path / "S01-s1.jsonl"
    trace.write_text(json.dumps({
        "type": "step", "step": 1, "tool_calls": [{"id": "c1", "name": "submit_record", "input": {}}],
        "tool_results": [{"call_id": "c1", "output": "handler error: not json", "is_error": True}],
        "cost_cum_usd": 0.02}) + "\n", encoding="utf-8")
    run._append_run_end(trace, "timeout", "killed at 900s; 0 bytes discarded", 900.0)
    end = json.loads(trace.read_text(encoding="utf-8").strip().split("\n")[-1])
    assert end["stop_condition"] == "timeout" and end["verify_rounds"] == 0 and end["submits"] == 1


# --- the brain (ADR 0008 items 4 and 5) --------------------------------------------------------


def test_the_brain_reaches_the_child_and_the_cell_pins_every_request_setting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ADR 0008 item 5: a cell is the same request on any machine, said out loud."""
    calls = _spy_subprocess(monkeypatch)
    run._launch(_cell(brain="claude", tool_budget=120))
    command, env = calls[0]["command"], calls[0]["env"]
    assert command[command.index("--brain") + 1] == "claude"
    pinned = {"ART30_MODEL": "claude-opus-5", "ART30_EFFORT": "high", "ART30_MAX_TOKENS": "32000",
              "ART30_TOOL_BUDGET": "120", "ART30_SUBMIT_BUDGET": "5", "ART30_MAX_TURNS": "60",
              "ART30_IGNORE_SETTINGS_FILES": "1"}
    assert {key: env[key] for key in pinned} == pinned


def test_a_local_brain_cell_carries_no_dollar_ceiling(monkeypatch: pytest.MonkeyPatch) -> None:
    """ADR 0008 item 3: nothing enforces ART30_MAX_USD on a local brain, so it is not passed
    on as a limit that is not there. The API brain keeps it."""
    monkeypatch.setenv("ART30_MAX_USD", "6")
    calls = _spy_subprocess(monkeypatch)
    run._launch(_cell(brain="claude"))
    assert "ART30_MAX_USD" not in calls[0]["env"]
    calls.clear()
    run._launch(_cell(brain="api"))
    assert calls[0]["env"]["ART30_MAX_USD"] == "6"
    assert calls[0]["command"][calls[0]["command"].index("--brain") + 1] == "api"


def test_the_default_brain_is_the_api_one(sandbox: Path) -> None:
    args = run.build_parser().parse_args(_argv(sandbox))
    assert args.brain == "api"


def test_the_identity_check_falls_back_to_prompt_sha_on_a_local_brain() -> None:
    """A local brain hashes no request (ADR 0008 item 1), so `step1` is null on every row and
    the API brain's check would pass two arms that ran different instructions."""
    rows = [{"cell": _cell(arm=arm), "step1": None, "prompt_sha": sha}
            for arm, sha in (("baseline", "a" * 64), ("advanced", "b" * 64))]
    run._identity_check(rows, "api")   # nothing to compare: the hole the fallback closes
    with pytest.raises(run.Abort) as caught:
        run._identity_check(rows, "claude")
    assert "prompt_sha differ between arms" in str(caught.value)
    same = [{**row, "prompt_sha": "a" * 64} for row in rows]
    run._identity_check(same, "claude")


def test_the_ledger_line_records_the_brain(sandbox: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(run, "_launch", fake_launch())
    assert run.main(_argv(sandbox, "--brain", "claude", "--unlock-test",
                          "--reason", "acceptance run", case="S08")) == 0
    line = (sandbox / "results" / "test-runs.log").read_text(encoding="utf-8")
    assert "brain claude; acceptance run" in line
