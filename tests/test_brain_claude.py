"""`run_brain` end to end with a fake `claude` on PATH (ADR 0008 items 1-3).

No login, no network, no real CLI: `tests/fakes/fake_claude.py` prints the event
shapes the real one prints and calls the real MCP server for every submission, so
what is under test is our half -- the argv, the stream-to-trace conversion, the two
budgets, the gate, `_finalise`, and the four stop conditions a local brain can end
on. Every trace written here is handed to the shipped validator.

The fixture is copied first and everything is written under `tmp_path`: no result
and no trace lands in `results/` or `traces/` (ADR 0006 item 3).
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

import pytest

from advanced.arm import AdvancedArm
from art30 import cli
from art30.brains import claude as claude_brain
from art30.brains import pricing
from art30.brains import run_brain
from art30.config import Config
from art30.loop import CaseRef
from evals.harness.trace_check import check_trace
from tests.test_e2e_advanced import S10_LIE, record_of

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "evals" / "fixtures" / "synthetic"
WRAPPER = "import sys\nfrom tests.fakes.fake_claude import main\nsys.exit(main())\n"
READ_CALL = {"name": "Read", "input": {"file_path": "models.py"},
             "result": "1 class User:\n2     email = None\n"}


@pytest.fixture
def bench(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A copied S10, a fake `claude` first on PATH, and a place to write the script."""
    root = tmp_path / "repos" / "S10"
    shutil.copytree(FIXTURES / "S10", root)
    binaries = tmp_path / "bin"
    binaries.mkdir()
    fake = binaries / "claude"
    fake.write_text(f"#!{sys.executable}\n{WRAPPER}", encoding="utf-8")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{binaries}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("ART30_FAKE_CLAUDE_SCRIPT", str(tmp_path / "script.json"))
    monkeypatch.setenv("ART30_FAKE_CLAUDE_ARGV", str(tmp_path / "argv.json"))
    return root


def _record_file(tmp_path: Path, name: str, record: dict) -> str:
    path = tmp_path / f"{name}.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    return str(path)


def _submit(path: str) -> dict:
    return {"name": "mcp__art30__submit_record", "record_file": path}


def _script(tmp_path: Path, turns: list[dict], **extra) -> None:
    payload = {"model": "claude-opus-5", "total_cost_usd": 0.42, "turns": turns, **extra}
    (tmp_path / "script.json").write_text(json.dumps(payload), encoding="utf-8")


def _cfg(tmp_path: Path, **extra) -> Config:
    values = {"tool_budget": 20, "brain": "claude", "approve": "auto", **extra}
    return Config(out_dir=tmp_path / "out", trace_dir=tmp_path / "traces",
                  cache_dir=tmp_path / "cache", **values)


def _drive(tmp_path: Path, root: Path, cfg: Config):
    case = CaseRef(id="S10", name="S10", root=root)
    result = run_brain(cfg, case, AdvancedArm(), 1)
    trace = tmp_path / "traces" / "advanced" / "S10-s1.jsonl"
    lines = [json.loads(line) for line in trace.read_text(encoding="utf-8").splitlines()]
    return result, lines, trace


def _lie(tmp_path: Path) -> str:
    return _record_file(tmp_path, "lie", record_of("S10", edits={"uploads": S10_LIE},
                                                   drop=("nightly_backup",), retention=False))


def _good(tmp_path: Path) -> str:
    return _record_file(tmp_path, "good", record_of("S10"))


# ---------------------------------------------------------------------------
# the accepted run
# ---------------------------------------------------------------------------
def test_a_rejected_claim_then_an_accepted_record_ends_the_run(bench, tmp_path: Path) -> None:
    _script(tmp_path, [
        {"thinking": "reading the models", "text": "Let me read the model file.",
         "calls": [READ_CALL]},
        {"text": "Submitting the record.", "calls": [_submit(_lie(tmp_path))]},
        {"text": "Fixing uploads and adding the backup.", "calls": [_submit(_good(tmp_path))]},
    ])

    result, lines, trace = _drive(tmp_path, bench, _cfg(tmp_path))

    assert check_trace(trace) == []
    assert (result.stop_condition, result.steps) == ("accepted", 3)
    assert (result.tool_calls_total, result.submits, result.verify_rounds) == (3, 2, 1)
    start = lines[0]
    assert start["config"]["brain"] == "claude"
    assert start["config"]["cost_source"] == "cli_estimate"
    assert start["model"] == "claude-opus-5"   # the configured model, check 13
    steps = [line for line in lines if line["type"] == "step"]
    assert [step["phase"] for step in steps] == ["agent", "verify", "verify"]
    assert [step["request_hash"] for step in steps] == [None, None, None]
    assert steps[0]["reasoning"] == "reading the models"
    assert steps[0]["tool_calls"][0]["name"] == "Read"
    assert steps[1]["tool_calls"][0]["name"] == "submit_record"   # the prefix is ours to drop
    assert steps[1]["tool_results"][0]["is_error"] is True
    assert steps[2]["tool_results"][0]["output"] == '{"accepted":true}'
    assert result.cost_usd > 0 and steps[-1]["cost_cum_usd"] == result.cost_usd


def test_the_record_carries_the_rejected_history_the_gate_and_the_brain(
    bench, tmp_path: Path
) -> None:
    _script(tmp_path, [
        {"calls": [_submit(_lie(tmp_path))]},
        {"calls": [_submit(_good(tmp_path))]},
    ])

    result, lines, _ = _drive(tmp_path, bench, _cfg(tmp_path))

    record = json.loads(Path(result.record_path).read_text(encoding="utf-8"))
    verification = record["verification"]
    assert verification["submits"] == 2 and verification["accepted_on_attempt"] == 2
    assert [item["store"] for item in verification["rejected_history"]] == ["uploads"]
    assert verification["rejected_history"][0]["revised_to"] == "not_erased"
    assert [item["store"] for item in verification["missing_stores_resolved"]] == ["nightly_backup"]
    assert verification["rule_set_sha"] == AdvancedArm().rule_set_sha
    provenance = record["provenance"]
    assert provenance["brain"] == "claude" and provenance["brain_model"] == "claude-opus-5"
    assert provenance["cost_source"] == "cli_estimate"
    assert provenance["cli_total_cost_usd"] == 0.42
    assert provenance["arm"] == "advanced" and provenance["gate"]["by"] == "simulated"
    point = next(line for line in lines if line["type"] == "checkpoint")
    assert (point["risk"], point["decision"], point["wait_s"]) == ("high", "approved", 0.0)
    assert result.gate == {"risk": "high", "decision": "approved", "by": "simulated",
                           "wait_s": 0.0, "at": provenance["gate"]["at"]}
    for name in ("record.json", "record.md", "record.html", "system-prompt.md", "mcp.json"):
        assert (tmp_path / "out" / name).is_file()
    spooled = (tmp_path / "out" / "brain" / "submissions.jsonl").read_text(encoding="utf-8")
    assert len(spooled.splitlines()) == 2


def test_one_message_split_across_lines_is_one_step_and_the_cost_matches_the_cli(
    bench, tmp_path: Path
) -> None:
    """The CLI prints a line per content group and an output count only for the run.

    Both shapes come from the real D02 stream (`shapes.jsonl`): the four lines of one
    message share a `message.id`, and their `output_tokens` is a placeholder the final
    `result` line settles. A trace that took either at face value would report twice
    as many steps and half the cost.
    """
    _script(tmp_path, [
        {"thinking": "which stores hold personal data", "text": "Reading the models.",
         "calls": [READ_CALL, dict(READ_CALL, input={"file_path": "cache.py"})]},
        {"text": "Submitting.", "calls": [_submit(_good(tmp_path))]},
    ], output_total=9000, total_cost_usd=0.75)

    result, lines, trace = _drive(tmp_path, bench, _cfg(tmp_path))

    assert check_trace(trace) == []
    steps = [line for line in lines if line["type"] == "step"]
    assert len(steps) == 2 and result.steps == 2
    assert steps[0]["reasoning"] == "which stores hold personal data"
    assert steps[0]["text"] == "Reading the models."
    assert [call["name"] for call in steps[0]["tool_calls"]] == ["Read", "Read"]
    spent = {key: sum(step["usage"][key] for step in steps)
             for key in ("input", "cache_read", "cache_write", "output")}
    assert spent["output"] == 9000   # the run's own count, settled on the last step
    assert result.cost_usd == pricing.estimate(spent, "claude-opus-5", spent["cache_write"])
    record = json.loads(Path(result.record_path).read_text(encoding="utf-8"))
    assert record["provenance"]["cli_total_cost_usd"] == 0.75


def test_a_second_scan_into_one_directory_does_not_inherit_the_first_ones_record(
    bench, tmp_path: Path
) -> None:
    """The spool is a run's, not a directory's: `--out` twice must not accept twice."""
    _script(tmp_path, [{"calls": [_submit(_good(tmp_path))]}])
    first, _, _ = _drive(tmp_path, bench, _cfg(tmp_path))

    _script(tmp_path, [{"text": "I could not read the repository."}])
    second, _, trace = _drive(tmp_path, bench, _cfg(tmp_path))

    assert first.stop_condition == "accepted"
    assert second.stop_condition == "no_submission"
    assert check_trace(trace) == []
    assert not (tmp_path / "out" / "brain" / "accepted.json").exists()


def test_the_argv_carries_the_isolation_flags_and_the_key_is_stripped(
    bench, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR 0008 item 2, and the reason a local brain runs on the user's own login."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-not-a-real-key")
    _script(tmp_path, [{"calls": [_submit(_good(tmp_path))]}])

    _drive(tmp_path, bench, _cfg(tmp_path))

    argv = json.loads((tmp_path / "argv.json").read_text(encoding="utf-8"))
    assert argv[:1] == ["-p"] and "--strict-mcp-config" in argv
    # `--restricted` is the flag that does what a permission list cannot: it stops the
    # *scanned* repository's `.claude/settings.json` hooks from running, keeps the
    # user's own memory out, and confines Read/Grep/Glob to the working directory.
    assert "--restricted" in argv
    # `--tools` is the built-in tool set; `--allowedTools` is only a permission list,
    # so on its own it left ToolSearch and the Task* family callable (ADR 0008 item 2).
    assert argv[argv.index("--tools") + 1] == "Read,Grep,Glob"
    assert argv[argv.index("--allowedTools") + 1] == claude_brain.ALLOWED
    denied = argv[argv.index("--disallowedTools") + 1]
    assert "Bash" in denied and "TaskCreate" in denied and "ToolSearch" in denied
    assert argv[argv.index("--output-format") + 1] == "stream-json"
    assert argv[argv.index("--setting-sources") + 1] == ""
    assert argv[argv.index("--effort") + 1] == "high"   # the header's claim, made true
    assert "--disable-slash-commands" in argv and "--no-session-persistence" in argv
    assert argv[argv.index("--mcp-config") + 1] == str(tmp_path / "out" / "mcp.json")
    prompt = argv[argv.index("--append-system-prompt") + 1]
    assert "# What you are doing" in prompt and "Article 30" in prompt
    assert "mcp__art30__submit_record to submit" in argv[1]
    assert "ANTHROPIC_API_KEY" not in claude_brain.env()   # the login runs, not a key
    # Relocating it empties the memory directory but loses the login, so it is
    # dropped and `--restricted` carries the guarantee (see the module docstring).
    assert "CLAUDE_CONFIG_DIR" not in claude_brain.env()


# ---------------------------------------------------------------------------
# the four ways a run ends without a record
# ---------------------------------------------------------------------------
def test_the_tool_budget_stops_the_cli_and_the_trace_still_reconciles(
    bench, tmp_path: Path
) -> None:
    _script(tmp_path, [{"calls": [READ_CALL]}, {"calls": [READ_CALL]}, {"calls": [READ_CALL]},
                       {"calls": [_submit(_good(tmp_path))]}])

    result, lines, trace = _drive(tmp_path, bench, _cfg(tmp_path, tool_budget=2))

    assert check_trace(trace) == []
    assert result.stop_condition == "budget_exhausted"
    assert (result.tool_calls_total, result.submits) == (2, 0)
    assert "budget 2 exhausted" in (result.note or "")
    assert not (tmp_path / "out" / "record.json").exists()


def test_the_submit_budget_ends_the_run_at_max_submits(bench, tmp_path: Path) -> None:
    lie = _lie(tmp_path)
    _script(tmp_path, [{"calls": [_submit(lie)]}, {"calls": [_submit(lie)]},
                       {"calls": [_submit(_good(tmp_path))]}])

    result, _, trace = _drive(tmp_path, bench, _cfg(tmp_path, max_submits=2))

    assert check_trace(trace) == []
    assert (result.stop_condition, result.submits, result.verify_rounds) == ("max_submits", 2, 2)
    assert "last rejection: no path from entry point" in (result.note or "")
    assert (tmp_path / "out" / "brain" / "exhausted").is_file()


def test_a_cli_that_exits_non_zero_is_an_api_error_with_its_own_last_words(
    bench, tmp_path: Path
) -> None:
    _script(tmp_path, [{"text": "I cannot reach the model."}],
            exit_code=1, stderr="Invalid API key · Please run /login")

    result, _, trace = _drive(tmp_path, bench, _cfg(tmp_path))

    assert check_trace(trace) == []
    assert result.stop_condition == "api_error"
    assert "claude exited 1" in (result.note or "")
    assert "Please run /login" in (result.note or "")


def test_a_cli_that_submits_nothing_ends_the_run_with_no_submission(
    bench, tmp_path: Path
) -> None:
    _script(tmp_path, [{"text": "Here is what I found.", "calls": [READ_CALL]},
                       {"text": "I will submit the record next."}])

    result, lines, trace = _drive(tmp_path, bench, _cfg(tmp_path))

    assert check_trace(trace) == []
    assert (result.stop_condition, result.steps, result.submits) == ("no_submission", 2, 0)
    assert lines[-1]["note"] == "the CLI ended its turn with no submit_record call"


def test_the_turn_ceiling_is_ours_because_the_cli_has_no_flag_for_it(
    bench, tmp_path: Path
) -> None:
    """`claude --help` on 2.1.251 has no `--max-turns`, and it ignores unknown flags."""
    _script(tmp_path, [{"calls": [READ_CALL]}] * 5)

    result, _, trace = _drive(tmp_path, bench, _cfg(tmp_path, max_turns=2))

    assert check_trace(trace) == []
    assert result.stop_condition == "budget_exhausted"
    assert "max_turns 2" in (result.note or "")
    assert result.steps <= 3


def test_a_run_that_loaded_the_users_memory_is_stopped_before_it_is_scored(
    bench, tmp_path: Path
) -> None:
    """ADR 0008 item 2, checked against the CLI's own report rather than assumed.

    `--restricted` is what empties `memory_paths`; probed on 2.1.251 against
    `evals/fixtures/synthetic/D02`, a run without it loads
    `~/.claude/projects/<this repo>/memory/` -- the author's notes about building
    this tool -- into a model being scored on an eval case. A build that stopped
    doing that would contaminate every sweep silently, so the init line is read.
    """
    _script(tmp_path, [{"calls": [_submit(_good(tmp_path))]}],
            memory_paths={"auto": "/Users/someone/.claude/projects/art30/memory/"})

    result, _, trace = _drive(tmp_path, bench, _cfg(tmp_path))

    assert check_trace(trace) == []
    assert result.stop_condition == "api_error"
    assert "loaded memory from" in (result.note or "")
    assert not (tmp_path / "out" / "record.json").exists()


def test_a_model_with_no_list_price_reports_tokens_and_not_a_dollar_figure(
    bench, tmp_path: Path
) -> None:
    """ADR 0008 item 3: an unpriced run reads "n/a", never `$0.00`, which says free."""
    _script(tmp_path, [{"calls": [_submit(_good(tmp_path))]}], model="claude-sonnet-4-6")

    result, lines, trace = _drive(tmp_path, bench, _cfg(tmp_path, brain_model="claude-sonnet-4-6"))

    assert check_trace(trace) == []
    assert pricing.resolve("claude-sonnet-4-6") is None
    assert result.stop_condition == "accepted" and result.cost_usd == 0.0
    assert result.cost_source == "unpriced" and result.tokens > 0
    assert lines[0]["config"]["cost_source"] == "unpriced"
    record = json.loads(Path(result.record_path).read_text(encoding="utf-8"))
    assert record["provenance"]["cost_source"] == "unpriced"
    assert cli._money(_cfg(tmp_path), result).startswith("tokens ")
    assert "n/a" in cli._money(_cfg(tmp_path), result)


def test_the_context_window_suffix_the_init_line_reports_prices_as_its_family(
    bench, tmp_path: Path
) -> None:
    """`claude-opus-5[1m]` is `claude-opus-5` with a 1M window, and used to price as None."""
    _script(tmp_path, [{"calls": [_submit(_good(tmp_path))]}], model="claude-opus-5[1m]")

    result, lines, trace = _drive(tmp_path, bench, _cfg(tmp_path))

    assert check_trace(trace) == []
    assert result.cost_source == "cli_estimate" and result.cost_usd > 0
    assert lines[0]["config"]["usage_note"].startswith("per-step output tokens")


def test_a_gate_that_raises_still_leaves_a_run_end_line(
    bench, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`_outcome` runs the gate, `_finalise` and the renderer, and any of them can raise.

    `loop.run` guards that whole span; the driver used to guard only the subprocess,
    so a raise here left `run_start` plus step lines and no `run_end` -- check 2 red,
    `make smoke` red, and a sweep row with a truncated trace and no diagnosis.
    """
    def boom(self, record, ctx):
        raise RuntimeError("the approver went away")

    monkeypatch.setattr(AdvancedArm, "gate", boom)
    _script(tmp_path, [{"calls": [_submit(_good(tmp_path))]}])

    result, lines, trace = _drive(tmp_path, bench, _cfg(tmp_path))

    assert check_trace(trace) == []
    assert lines[-1]["type"] == "run_end"
    assert result.stop_condition == "api_error"
    assert result.note == "RuntimeError: the approver went away"
    assert sum(1 for line in lines if line["type"] == "run_end") == 1
