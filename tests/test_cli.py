"""The command surface: the help text, the two locks, and the replay exit.

Every case here runs with no API key and no cache, which is the state a judge's
machine is in.
"""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

import pytest

from art30 import cli
from art30.loop import RunResult
from tests.conftest import mkrepo


def _result(condition: str, **overrides) -> RunResult:
    base = dict(
        run_id="base-S01-s1-9f3ac1e", stop_condition=condition, steps=3, tool_calls_total=4,
        submits=1, verify_rounds=0, wall_s=1.0, cost_usd=0.1, record_path=None,
    )
    return RunResult(**{**base, **overrides})


def _args(**overrides) -> argparse.Namespace:
    base = dict(arm="baseline", case="S01", seed=1, repo="fx", out=None)
    return argparse.Namespace(**{**base, **overrides})


def _repo(tmp_path: Path, name: str = "fx") -> Path:
    return mkrepo(tmp_path / name)


def test_scan_help_lists_the_contract_flags(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_code:
        cli.main(["scan", "--help"])
    assert exit_code.value.code == 0
    text = capsys.readouterr().out
    for flag in ("--arm", "--case", "--seed", "--mode", "--approve", "--out"):
        assert flag in text
    assert "--verbose" not in text and "--json" not in text


@pytest.mark.skipif(
    importlib.util.find_spec("advanced.arm") is not None,
    reason="the advanced arm exists; this lock is only for the phase before it",
)
def test_the_advanced_arm_says_it_is_not_built(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = cli.main(["scan", str(_repo(tmp_path)), "--arm", "advanced"])
    assert code == 2
    assert "not built yet" in capsys.readouterr().err


def test_a_test_case_needs_the_unlock_variable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("ART30_UNLOCK_TEST", raising=False)
    monkeypatch.chdir(tmp_path)
    _repo(tmp_path, "S10")
    assert "S10" in cli.test_cases()

    code = cli.main(["scan", "S10", "--arm", "baseline"])
    assert code == 2
    message = capsys.readouterr().err
    assert "test split" in message and "ART30_UNLOCK_TEST=1" in message


def test_the_unlock_variable_lets_the_same_case_through(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ART30_UNLOCK_TEST", "1")
    monkeypatch.chdir(tmp_path)
    _repo(tmp_path, "S10")

    # Replay with no cache: the lock is passed, the run then fails on the miss.
    assert cli.main(["scan", "S10", "--arm", "baseline", "--mode", "replay"]) == 4


def test_a_replay_with_an_empty_cache_exits_four(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    _repo(tmp_path)

    code = cli.main(["scan", "fx", "--arm", "baseline", "--mode", "replay", "--case", "S01"])
    assert code == 4
    out = capsys.readouterr().out
    assert "replay miss" in out
    # A call that raised inside `llm.call` writes no step line (01 section 9).
    assert "replay_miss · 0 steps" in out
    trace = tmp_path / "traces" / "baseline" / "S01-s1.jsonl"
    assert trace.is_file() and "run_end" in trace.read_text(encoding="utf-8")


def test_the_header_names_the_budget_and_the_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    _repo(tmp_path)

    cli.main(["scan", "fx", "--arm", "baseline", "--mode", "replay", "--case", "R01"])
    header = capsys.readouterr().out.splitlines()
    assert header[0].startswith("art30 ") and "arm baseline" in header[0]
    assert "model claude-opus-5 · effort high · max_tokens 32000" == header[1]
    # A real case runs at the 120-call budget (contract, Budgets).
    assert "budget 120 tool calls · 5 submit attempts" in header[2]


def test_out_is_used_verbatim_and_the_default_is_expanded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[Path] = []

    def fake_run(case, arm, seed, cfg, report=None) -> RunResult:
        seen.append(Path(cfg.out_dir))
        return _result("accepted")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "run", fake_run)
    _repo(tmp_path)
    chosen = tmp_path / "chosen"

    cli.main(["scan", "fx", "--arm", "baseline", "--case", "S01", "--out", str(chosen)])
    cli.main(["scan", "fx", "--arm", "baseline", "--case", "S01"])

    assert seen == [chosen, Path("results/runs/baseline/S01/s1")]


def test_the_tail_names_the_ceiling_the_record_and_the_gate(
    capsys: pytest.CaptureFixture[str]
) -> None:
    cfg = cli.config.load({}).__class__(max_usd=0.0001)
    ceiling = _result("budget_exhausted", steps=1, note="cost ceiling $0.0001 crossed at step 1")
    cli._tail(cfg, _args(), ceiling)
    cli._tail(
        cfg,
        _args(arm="advanced"),
        _result(
            "render_failed", note="citation storage.py:41 no longer contains cleanup_user_files.",
            record_path="out/record.json",
            gate={"risk": "high", "decision": "approved", "by": "simulated", "wait_s": 0.0},
        ),
    )
    printed = capsys.readouterr().out

    assert "[agent] cost ceiling $0.0001 crossed at step 1." in printed
    assert "budget exhausted at" not in printed
    assert "Nothing written. The record is kept at out/record.json." in printed
    assert "· 1 submit ·" in printed and "· no gate (baseline)" in printed
    assert "gate approved (simulated)" in printed


def test_a_missing_repository_is_a_usage_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["scan", str(tmp_path / "nowhere"), "--arm", "baseline"]) == 2
    assert "not a directory" in capsys.readouterr().err
