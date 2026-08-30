"""`run_brain --brain codex` end to end with a fake `codex` on PATH (ADR 0008 items 1-3).

No login, no network, no real CLI: `tests/fakes/fake_codex.py` prints the event
shapes the real one prints and calls the real MCP server for every submission, so
what is under test is our half -- the argv and its isolation flags, the
item-stream-to-trace conversion, the two budgets, the gate, `_finalise`, the
pricing rule and the stop conditions. Every trace written here is handed to the
shipped validator.

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
from art30.brains import codex as codex_brain
from art30.brains import codex_events, pricing, run_brain
from art30.config import Config
from art30.loop import CaseRef
from evals.harness.trace_check import check_trace
from tests.test_e2e_advanced import S10_LIE, record_of

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "evals" / "fixtures" / "synthetic"
WRAPPER = "import sys\nfrom tests.fakes.fake_codex import main\nsys.exit(main())\n"
SHELL_ITEM = {"type": "command_execution", "command": "cat models.py",
              "output": "class User:\n    email = None\n", "exit_code": 0}
PRICE = '{"gpt-5-codex": [1.25, 0.125, 10.0]}'


@pytest.fixture
def bench(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A copied S10, a fake `codex` first on PATH, and a place to write the script."""
    root = tmp_path / "repos" / "S10"
    shutil.copytree(FIXTURES / "S10", root)
    binaries = tmp_path / "bin"
    binaries.mkdir()
    fake = binaries / "codex"
    fake.write_text(f"#!{sys.executable}\n{WRAPPER}", encoding="utf-8")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{binaries}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("ART30_FAKE_CODEX_SCRIPT", str(tmp_path / "script.json"))
    monkeypatch.setenv("ART30_FAKE_CODEX_ARGV", str(tmp_path / "argv.json"))
    return root


def _record_file(tmp_path: Path, name: str, record: dict) -> str:
    path = tmp_path / f"{name}.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    return str(path)


def _submit(path: str) -> dict:
    return {"type": "mcp_tool_call", "record_file": path}


def _script(tmp_path: Path, items: list[dict], **extra) -> None:
    (tmp_path / "script.json").write_text(json.dumps({"items": items, **extra}),
                                          encoding="utf-8")


def _cfg(tmp_path: Path, **extra) -> Config:
    values = {"tool_budget": 20, "brain": "codex", "approve": "auto", **extra}
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
def test_reasoning_a_shell_read_a_rejection_then_an_accepted_record(bench, tmp_path: Path) -> None:
    """The four item kinds a codex run produces, read as four trace steps."""
    _script(tmp_path, [
        {"type": "reasoning", "text": "which stores hold personal data"},
        {"type": "agent_message", "text": "Reading the model file."},
        SHELL_ITEM,
        _submit(_lie(tmp_path)),
        {"type": "agent_message", "text": "Fixing uploads and adding the backup."},
        _submit(_good(tmp_path)),
    ])

    result, lines, trace = _drive(tmp_path, bench, _cfg(tmp_path))

    assert check_trace(trace) == []
    assert (result.stop_condition, result.steps) == ("accepted", 3)
    assert (result.tool_calls_total, result.submits, result.verify_rounds) == (3, 2, 1)
    steps = [line for line in lines if line["type"] == "step"]
    assert [step["phase"] for step in steps] == ["agent", "verify", "verify"]
    assert [step["request_hash"] for step in steps] == [None, None, None]
    assert steps[0]["reasoning"] == "which stores hold personal data"
    assert steps[0]["text"] == "Reading the model file."
    # Codex's exec tool is recorded under one name, with the sandbox it ran in.
    assert steps[0]["tool_calls"][0]["name"] == "shell"
    assert steps[0]["tool_calls"][0]["input"]["sandbox"] == "read-only"
    assert "cat models.py" in steps[0]["tool_calls"][0]["input"]["command"]
    assert steps[0]["tool_results"][0]["output"].startswith("class User:")
    assert steps[1]["tool_calls"][0]["name"] == "submit_record"
    assert steps[1]["tool_results"][0]["is_error"] is True
    assert steps[2]["tool_results"][0]["output"] == '{"accepted":true}'


def test_the_run_start_line_names_the_brain_and_the_trace_says_what_is_unpriced(
    bench, tmp_path: Path
) -> None:
    _script(tmp_path, [_submit(_good(tmp_path))])

    result, lines, trace = _drive(tmp_path, bench, _cfg(tmp_path, brain_model="gpt-5-codex"))

    assert check_trace(trace) == []
    start = lines[0]
    assert start["config"]["brain"] == "codex"
    assert start["config"]["brain_model"] == "gpt-5-codex"
    assert start["config"]["cost_source"] == "unpriced"
    assert start["model"] == "claude-opus-5"      # the configured model, check 13
    assert not codex_brain.priced(None)           # codex never names a model to price
    assert "codex reports token counts once per turn" in start["config"]["usage_note"]
    assert result.cost_source == "unpriced" and result.cost_usd == 0.0
    assert cli._money(_cfg(tmp_path), result).startswith("tokens ")


def test_the_record_carries_the_rejected_history_the_gate_and_the_brain(
    bench, tmp_path: Path
) -> None:
    _script(tmp_path, [_submit(_lie(tmp_path)), _submit(_good(tmp_path))])

    result, lines, _ = _drive(tmp_path, bench, _cfg(tmp_path, brain_model="gpt-5-codex"))

    record = json.loads(Path(result.record_path).read_text(encoding="utf-8"))
    verification = record["verification"]
    assert verification["submits"] == 2 and verification["accepted_on_attempt"] == 2
    assert [item["store"] for item in verification["rejected_history"]] == ["uploads"]
    assert [item["store"] for item in verification["missing_stores_resolved"]] == ["nightly_backup"]
    provenance = record["provenance"]
    assert provenance["brain"] == "codex" and provenance["brain_model"] == "gpt-5-codex"
    assert provenance["brain_label"] == "Codex (your login)"
    assert provenance["cost_source"] == "unpriced"
    assert provenance["cli_total_cost_usd"] is None   # codex reports no cost of its own
    point = next(line for line in lines if line["type"] == "checkpoint")
    assert (point["risk"], point["decision"]) == ("high", "approved")
    for name in ("record.json", "record.md", "record.html", "system-prompt.md", "mcp.json"):
        assert (tmp_path / "out" / name).is_file()
    assert len((tmp_path / "out" / "brain" / "submissions.jsonl").read_text(
        encoding="utf-8").splitlines()) == 2


# ---------------------------------------------------------------------------
# the command line
# ---------------------------------------------------------------------------
def test_the_argv_carries_the_isolation_flags_and_the_key_is_stripped(
    bench, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR 0008 item 2, and the reason a local brain runs on the user's own login."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-not-a-real-key")
    _script(tmp_path, [_submit(_good(tmp_path))])

    _drive(tmp_path, bench, _cfg(tmp_path, brain_model="gpt-5-codex"))

    argv = json.loads((tmp_path / "argv.json").read_text(encoding="utf-8"))
    assert argv[:3] == ["exec", "--json", "-s"] and argv[3] == "read-only"
    assert "--skip-git-repo-check" in argv
    # The user's own `~/.codex/config.toml`, execpolicy rules and session files stay
    # out of a measured run; the login in the same directory still works.
    assert "--ignore-user-config" in argv and "--ignore-rules" in argv
    assert "--ephemeral" in argv
    assert argv[argv.index("-C") + 1] == str(bench)
    assert argv[argv.index("-m") + 1] == "gpt-5-codex"
    overrides = dict(argv[index + 1].split("=", 1)
                     for index, flag in enumerate(argv) if flag == "-c")
    # Without this one, every MCP call answers "requires approval, but approval
    # policy is never" and the model never reaches the verifier.
    assert overrides["mcp_servers.art30.default_tools_approval_mode"] == '"approve"'
    assert json.loads(overrides["mcp_servers.art30.command"]) == sys.executable
    assert json.loads(overrides["mcp_servers.art30.args"])[:2] == ["-m", "art30.brains.mcp_server"]
    assert "PYTHONPATH" in overrides["mcp_servers.art30.env"]
    assert overrides["project_doc_max_bytes"] == "0"        # the scanned AGENTS.md is not read
    assert overrides["memories.use_memories"] == "false"
    assert overrides["tools.web_search"] == "false"
    assert overrides["model_reasoning_effort"] == '"high"'   # the header's claim, made true
    # Without it the stream carries no `reasoning` item at all, probed both ways.
    assert overrides["model_reasoning_summary"] == '"detailed"'
    # Without it every shell command runs through a login shell, so the operator's
    # `~/.zprofile` decides which `rg`, `python` and `grep` the model gets.
    assert overrides["allow_login_shell"] == "false"
    assert argv[argv.index("allow_login_shell=false") - 1] == "-c"
    assert "OPENAI_API_KEY" not in codex_brain.env()         # the login runs, not a key


def test_the_instruction_text_is_the_prompt_because_codex_has_no_system_flag(
    bench, tmp_path: Path
) -> None:
    _script(tmp_path, [_submit(_good(tmp_path))])

    _drive(tmp_path, bench, _cfg(tmp_path))

    prompt = json.loads((tmp_path / "argv.json").read_text(encoding="utf-8"))[-1]
    assert "# What you are doing" in prompt and "Article 30" in prompt
    assert "Scan target: S10" in prompt
    # The sandbox blocks writes and network but not executing the repository, so the
    # prompt is what forbids it (ADR 0008 item 2; docs/brains.md says it is a limit).
    assert "Never execute the repository's own code" in prompt
    # The frozen instruction text says "use `grep` to locate and `read_file` to
    # decide"; `read_file` is not a tool this brain serves, so the first turn names
    # the shell equivalents rather than leaving the model to work it out.
    assert "read_file" in prompt and "on this run both are shell commands" in prompt
    assert "sed -n" in prompt
    assert prompt == (tmp_path / "out" / "system-prompt.md").read_text(encoding="utf-8").rstrip("\n")


# ---------------------------------------------------------------------------
# the deliverable
# ---------------------------------------------------------------------------
def test_the_signed_record_names_the_brain_that_answered_not_the_api_model(
    bench, tmp_path: Path
) -> None:
    """`provenance.model` is the configured API model on every run. A codex record
    that printed it in the Model row would name a model that never read the
    repository, in the one row a reader uses to judge provenance (ADR 0008 item 1)."""
    _script(tmp_path, [_submit(_good(tmp_path))])

    result, _, _ = _drive(tmp_path, bench, _cfg(tmp_path))

    markdown = (tmp_path / "out" / "record.md").read_text(encoding="utf-8")
    page = (tmp_path / "out" / "record.html").read_text(encoding="utf-8")
    assert "claude-opus-5" not in markdown and "claude-opus-5" not in page
    assert "| Model | Codex (your login) — the CLI default model, effort high |" in markdown
    assert "Codex (your login)" in page
    assert result.stop_condition == "accepted"


def test_the_record_says_n_a_where_the_cost_is_unknown_rather_than_usd_zero(
    bench, tmp_path: Path
) -> None:
    """ADR 0008 item 3 on the surface a person signs: `USD 0.0` reads as free."""
    _script(tmp_path, [_submit(_good(tmp_path))])

    _drive(tmp_path, bench, _cfg(tmp_path))

    markdown = (tmp_path / "out" / "record.md").read_text(encoding="utf-8")
    assert "| Cost | n/a (no list price for this model), 1 tool calls |" in markdown
    assert "USD 0.0" not in markdown


def test_a_priced_codex_record_labels_its_dollars_as_an_estimate(
    bench, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _script(tmp_path, [_submit(_good(tmp_path))])
    monkeypatch.setenv("ART30_CODEX_PRICES", PRICE)

    _drive(tmp_path, bench, _cfg(tmp_path, brain_model="gpt-5-codex"))

    markdown = (tmp_path / "out" / "record.md").read_text(encoding="utf-8")
    assert "| Model | Codex (your login) — gpt-5-codex, effort high |" in markdown
    assert "(estimate at list prices)" in markdown


# ---------------------------------------------------------------------------
# cost
# ---------------------------------------------------------------------------
def test_a_codex_run_is_unpriced_until_a_price_is_configured(
    bench, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR 0008 item 3: tokens and "n/a", never `$0.00`, which would say free."""
    _script(tmp_path, [_submit(_good(tmp_path))],
            usage={"input_tokens": 10_000, "cached_input_tokens": 4_000,
                   "cache_write_input_tokens": 0, "output_tokens": 2_000,
                   "reasoning_output_tokens": 500})
    cfg = _cfg(tmp_path, brain_model="gpt-5-codex")

    monkeypatch.setenv("ART30_CODEX_PRICES", PRICE)
    result, lines, trace = _drive(tmp_path, bench, cfg)

    assert check_trace(trace) == []
    assert pricing.codex_prices() == {"gpt-5-codex": (1.25, 0.125, 10.0)}
    # 6,000 uncached input at 1.25, 4,000 cached at 0.125, 2,000 output at 10.
    assert result.cost_usd == pytest.approx(0.0075 + 0.0005 + 0.02)
    assert result.cost_source == "cli_estimate"
    assert lines[0]["config"]["cost_source"] == "cli_estimate"
    assert cli._money(cfg, result).endswith("est")


def test_a_run_that_wrote_no_step_line_still_reports_unpriced_and_its_tokens(
    bench, tmp_path: Path
) -> None:
    """The shape of `codex` not being logged in: a turn with no items and a non-zero
    exit. `cost_source` is set inside `_write`, which never ran, so the end of the run
    used to disagree with its own `run_start` and print `$0.00 est` -- the zero that
    reads as free. `tokens` came off the same empty ledger while `run_end.note` was
    already printing the CLI's totals."""
    _script(tmp_path, [], exit_code=1, stderr="Not logged in. Run codex login.")

    result, lines, trace = _drive(tmp_path, bench, _cfg(tmp_path))

    assert check_trace(trace) == []
    assert result.steps == 0 and result.stop_condition == "api_error"
    assert lines[0]["config"]["cost_source"] == "unpriced"
    assert result.cost_source == "unpriced"
    assert cli._money(_cfg(tmp_path), result).startswith("tokens 45175 · n/a")
    # 5,734 + 39,168 + 0 + 273, the counts the note on the same run reports.
    assert "tokens: 5734/39168/273/97" in (result.note or "")


def test_the_run_end_note_carries_the_four_token_counts_codex_reports(
    bench, tmp_path: Path
) -> None:
    """The contract's `usage` has four keys and no room for reasoning tokens."""
    _script(tmp_path, [_submit(_good(tmp_path))],
            usage={"input_tokens": 10_000, "cached_input_tokens": 4_000,
                   "cache_write_input_tokens": 0, "output_tokens": 2_000,
                   "reasoning_output_tokens": 500})

    result, lines, trace = _drive(tmp_path, bench, _cfg(tmp_path))

    assert check_trace(trace) == []
    assert lines[-1]["note"] == "tokens: 6000/4000/2000/500 (input/cached/output/reasoning)"
    steps = [line for line in lines if line["type"] == "step"]
    # Codex reports the turn and never the item, so the run settles on the last step.
    assert steps[-1]["usage"] == {"input": 6000, "cache_read": 4000,
                                  "cache_write": 0, "output": 2000}
    assert result.tokens == 12_000


# ---------------------------------------------------------------------------
# the ways a run ends without a record
# ---------------------------------------------------------------------------
def test_a_file_change_under_a_read_only_sandbox_is_recorded_as_an_error(
    bench, tmp_path: Path
) -> None:
    """`-s read-only` should make this impossible; if it happens it must be legible."""
    _script(tmp_path, [{"type": "file_change", "changes": [{"path": "models.py", "kind": "edit"}]},
                       _submit(_good(tmp_path))])

    result, lines, trace = _drive(tmp_path, bench, _cfg(tmp_path))

    assert check_trace(trace) == []
    steps = [line for line in lines if line["type"] == "step"]
    assert steps[0]["tool_calls"][0]["name"] == "file_change"
    assert steps[0]["tool_results"][0]["is_error"] is True
    assert "read-only sandbox does not permit" in steps[0]["tool_results"][0]["output"]
    assert result.stop_condition == "accepted"


def test_the_tool_budget_stops_the_cli_and_the_trace_still_reconciles(
    bench, tmp_path: Path
) -> None:
    _script(tmp_path, [SHELL_ITEM, SHELL_ITEM, SHELL_ITEM, _submit(_good(tmp_path))])

    result, _, trace = _drive(tmp_path, bench, _cfg(tmp_path, tool_budget=2))

    assert check_trace(trace) == []
    assert result.stop_condition == "budget_exhausted"
    assert (result.tool_calls_total, result.submits) == (2, 0)
    assert "budget 2 exhausted" in (result.note or "")
    assert not (tmp_path / "out" / "record.json").exists()


def test_the_submit_budget_ends_the_run_at_max_submits(bench, tmp_path: Path) -> None:
    lie = _lie(tmp_path)
    _script(tmp_path, [_submit(lie), _submit(lie), _submit(_good(tmp_path))])

    result, _, trace = _drive(tmp_path, bench, _cfg(tmp_path, max_submits=2))

    assert check_trace(trace) == []
    assert (result.stop_condition, result.submits, result.verify_rounds) == ("max_submits", 2, 2)
    assert "last rejection: no path from entry point" in (result.note or "")
    assert (tmp_path / "out" / "brain" / "exhausted").is_file()


def test_the_turn_ceiling_is_ours_because_codex_has_no_flag_for_it(
    bench, tmp_path: Path
) -> None:
    _script(tmp_path, [SHELL_ITEM] * 5)

    result, _, trace = _drive(tmp_path, bench, _cfg(tmp_path, max_turns=2))

    assert check_trace(trace) == []
    assert result.stop_condition == "budget_exhausted"
    assert "max_turns 2" in (result.note or "")
    assert result.steps <= 3


def test_a_cli_that_exits_non_zero_is_an_api_error_with_its_own_last_words(
    bench, tmp_path: Path
) -> None:
    _script(tmp_path, [{"type": "agent_message", "text": "I cannot reach the model."}],
            exit_code=1, stderr="Not logged in. Run codex login.")

    result, _, trace = _drive(tmp_path, bench, _cfg(tmp_path))

    assert check_trace(trace) == []
    assert result.stop_condition == "api_error"
    assert "codex exited 1" in (result.note or "")
    assert "Run codex login" in (result.note or "")


def test_a_cli_that_submits_nothing_ends_the_run_with_no_submission(
    bench, tmp_path: Path
) -> None:
    _script(tmp_path, [SHELL_ITEM, {"type": "agent_message", "text": "I will submit next."}])

    result, _, trace = _drive(tmp_path, bench, _cfg(tmp_path))

    assert check_trace(trace) == []
    assert (result.stop_condition, result.steps, result.submits) == ("no_submission", 2, 0)
    assert (result.note or "").startswith("the CLI ended its turn with no submit_record call")


def test_a_failed_turn_is_read_off_the_stream_rather_than_the_exit_code(
    bench, tmp_path: Path
) -> None:
    """`turn.failed` is how codex reports a model-side failure; the exit code can be 0."""
    _script(tmp_path, [SHELL_ITEM], turn_failed="stream disconnected before completion")

    result, _, trace = _drive(tmp_path, bench, _cfg(tmp_path))

    assert check_trace(trace) == []
    assert result.stop_condition == "api_error"
    assert "stream disconnected" in (result.note or "")


def test_an_error_line_the_run_recovered_from_does_not_end_it(bench, tmp_path: Path) -> None:
    """Codex prints `error` for a retry too ("Reconnecting... 2/5"), which was observed
    on a real invocation whose HOME had been moved away from the login. A run that
    goes on to submit a record has recovered, and the line is not its stop condition."""
    _script(tmp_path, [_submit(_good(tmp_path))],
            stream_error="Reconnecting... 2/5 (unexpected status 401 Unauthorized)")

    result, lines, trace = _drive(tmp_path, bench, _cfg(tmp_path))

    assert check_trace(trace) == []
    assert result.stop_condition == "accepted"
    assert "Reconnecting" not in (result.note or "")


def test_an_error_line_a_run_never_recovered_from_is_the_note_it_ends_with(
    bench, tmp_path: Path
) -> None:
    _script(tmp_path, [{"type": "agent_message", "text": "I could not read the repository."}],
            stream_error="unexpected status 401 Unauthorized")

    result, _, trace = _drive(tmp_path, bench, _cfg(tmp_path))

    assert check_trace(trace) == []
    assert result.stop_condition == "no_submission"
    assert "codex reported unexpected status 401" in (result.note or "")


# ---------------------------------------------------------------------------
# the reader, on the shapes the real CLI printed
# ---------------------------------------------------------------------------
def test_the_usage_reader_splits_codexs_input_into_cached_and_uncached() -> None:
    """Codex's `input_tokens` is the whole input; the contract's `input` is the rest."""
    usage = codex_events.usage_of({"input_tokens": 44902, "cached_input_tokens": 39168,
                                   "cache_write_input_tokens": 0, "output_tokens": 273,
                                   "reasoning_output_tokens": 97})

    assert usage == {"input": 5734, "cache_read": 39168, "cache_write": 0, "output": 273}
    assert usage["input"] + usage["cache_read"] == 44902
    assert codex_events.reasoning_tokens({"reasoning_output_tokens": 97}) == 97


def test_an_mcp_item_that_never_reached_the_server_is_an_error_with_its_reason() -> None:
    """The shape a run without `default_tools_approval_mode` produces, kept as a test
    so the flag's absence would fail loudly rather than score an empty run."""
    piece = codex_events.piece({
        "id": "item_1", "type": "mcp_tool_call", "server": "art30", "tool": "submit_record",
        "arguments": {"record": {}}, "result": None, "status": "failed",
        "error": {"message": "MCP tool call requires approval, but approval policy is never"},
    })

    assert piece is not None and piece["kind"] == "call"
    assert piece["call"]["name"] == "submit_record"
    assert piece["result"]["is_error"] is True
    assert "approval policy is never" in piece["result"]["output"]


def test_a_shell_command_that_did_not_exit_zero_is_an_error_result() -> None:
    for code, is_error in ((0, False), (1, True), (-9, True), (None, True)):
        piece = codex_events.piece({"id": "item_0", "type": "command_execution",
                                    "command": "/bin/zsh -lc 'cat missing.py'",
                                    "aggregated_output": "no such file", "exit_code": code,
                                    "status": "completed"})
        assert piece is not None and piece["result"]["is_error"] is is_error


def test_an_item_kind_the_trace_has_no_shape_for_is_ignored_rather_than_guessed() -> None:
    assert codex_events.piece({"id": "item_9", "type": "todo_list", "items": []}) is None
    assert codex_events.piece("not an item") is None



def test_a_second_turn_adds_to_the_runs_totals_rather_than_replacing_them() -> None:
    """`codex exec` emitted one turn on every run seen so far. A resumed thread or an
    auto-compaction turn would otherwise drop everything before the last one, silently,
    into `run_end.cost_usd` and the trace's last step."""
    stepper = codex_events.CodexStepper(tool_budget=10, submit_budget=5, max_turns=10)

    for usage in ({"input_tokens": 100, "cached_input_tokens": 0, "output_tokens": 10,
                   "reasoning_output_tokens": 2},
                  {"input_tokens": 50, "cached_input_tokens": 20, "output_tokens": 5,
                   "reasoning_output_tokens": 3}):
        stepper.feed({"type": "turn.completed", "usage": usage})

    assert stepper.totals["usage"] == {"input": 130, "cache_read": 20,
                                       "cache_write": 0, "output": 15}
    assert stepper.reasoning_tokens == 5


def test_a_cache_write_is_part_of_the_input_codex_reported_not_extra() -> None:
    """`cache_write` priced beside a full `input_tokens` would bill those tokens twice."""
    usage = codex_events.usage_of({"input_tokens": 1000, "cached_input_tokens": 400,
                                   "cache_write_input_tokens": 300, "output_tokens": 10})

    assert usage == {"input": 300, "cache_read": 400, "cache_write": 300, "output": 10}
    assert usage["input"] + usage["cache_read"] + usage["cache_write"] == 1000


def test_a_transport_error_on_another_servers_tool_is_not_a_rejected_submission() -> None:
    """`accepted:false` is the verifier's vocabulary. Speaking it for a protocol error
    on `list_mcp_resources` puts a rejection in the trace that `verify_rounds` never
    saw, and a reader counting rejections off the step lines gets the wrong number."""
    piece = codex_events.piece({
        "id": "item_3", "type": "mcp_tool_call", "tool": "list_mcp_resources",
        "arguments": {}, "result": None, "status": "failed",
        "error": {"message": "resources/list failed: unknown method resources/list"},
    })

    assert piece is not None and piece["call"]["name"] == "list_mcp_resources"
    assert piece["result"]["output"].startswith("resources/list failed")
    assert piece["result"]["is_error"] is True
    assert "accepted" not in piece["result"]["output"]


def test_arguments_sent_as_a_json_string_still_reach_the_trace() -> None:
    """0.148.0 sends an object. A build that sent the string form would record a
    `submit_record` call with no record while `submissions.jsonl` held the real one."""
    piece = codex_events.piece({
        "id": "item_1", "type": "mcp_tool_call", "tool": "submit_record",
        "arguments": '{"record":{"repository":"S10"}}', "status": "completed",
        "result": {"content": [{"type": "text", "text": '{"accepted":true}'}]}, "error": None,
    })

    assert piece is not None
    assert piece["call"]["input"] == {"record": {"repository": "S10"}}
    assert codex_events.piece({"id": "x", "type": "mcp_tool_call", "tool": "submit_record",
                               "arguments": "not json", "status": "completed",
                               "result": None, "error": None})["call"]["input"] == {}
