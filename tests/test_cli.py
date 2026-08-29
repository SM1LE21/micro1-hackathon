"""The command surface: the help text, the three locks, the paths, the replay exit.

Every case here runs with no API key and no cache, which is the state a judge's
machine is in. The one case that needs a run drives the loop with a scripted
model, the way tests/test_loop.py does; no client is ever constructed.
"""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

import pytest

from art30 import cli, llm
from art30.loop import RunResult
from tests.conftest import mkrepo
from tests.test_loop import _response, _submit, record_for

D02 = cli.REPO_ROOT / "evals" / "fixtures" / "synthetic" / "D02"


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


def test_an_arm_that_cannot_be_imported_is_a_usage_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`baseline/` and `advanced/` live outside the `art30` package, so a wheel
    built without them has neither. Either way the run ends in one sentence and
    exit 2, not the `ModuleNotFoundError` traceback an installed copy used to
    print (ADR 0007 item 2). Replay keeps the no-key check out of the way, so the
    arm check is the one that fires."""
    monkeypatch.setattr(cli, "load_arm", lambda name: None)
    repo = str(_repo(tmp_path))

    for arm in ("baseline", "advanced"):
        assert cli.main(["scan", repo, "--arm", arm, "--mode", "replay"]) == 2
        message = capsys.readouterr().err
        assert f"no {arm} arm: {arm}/arm.py could not be imported" in message
        assert "packages baseline/ and advanced/" in message


def test_the_arms_import_in_this_checkout() -> None:
    """The other half of the case above: inside the repository both arms load."""
    assert importlib.util.find_spec("advanced.arm") is not None
    assert cli.load_arm("baseline") is not None and cli.load_arm("advanced") is not None


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
    trace = tmp_path / "art30-out" / "fx" / "baseline" / "s1" / "baseline" / "S01-s1.jsonl"
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


def _spy(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Path, Path]]:
    """Every run's (out_dir, trace_dir), with the loop replaced by a stub."""
    seen: list[tuple[Path, Path]] = []

    def fake_run(case, arm, seed, cfg, report=None) -> RunResult:
        seen.append((Path(cfg.out_dir), Path(cfg.trace_dir)))
        return _result("accepted")

    monkeypatch.setattr(cli, "run", fake_run)
    return seen


def test_out_is_used_verbatim_and_the_fixture_default_is_expanded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An evaluation fixture keeps the results/runs layout and the traces/ tree:
    the harness's own paths are what `make eval` reports from."""
    monkeypatch.chdir(tmp_path)
    seen = _spy(monkeypatch)
    chosen = tmp_path / "chosen"

    replay = ["--mode", "replay"]   # the stub stands in for the loop; no key, no cache
    cli.main(["scan", str(D02), "--arm", "baseline", "--case", "D02", "--out", str(chosen), *replay])
    cli.main(["scan", str(D02), "--arm", "baseline", "--case", "D02", *replay])

    assert seen == [
        (chosen, Path("traces")),
        (Path("results/runs/baseline/D02/s1"), Path("traces")),
    ]


def test_a_repository_of_your_own_gets_its_own_output_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR 0007 item 2: a scan of somebody's repository writes nothing into the
    eval's trees. Record and trace land together under ./art30-out/<slug>/."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ART30_TRACE_DIR", raising=False)
    seen = _spy(monkeypatch)
    _repo(tmp_path)

    cli.main(["scan", "fx", "--arm", "baseline", "--case", "S01", "--seed", "3", "--mode", "replay"])
    own = Path("art30-out/fx/baseline/s3")
    assert seen == [(own, own)]

    # --out moves both, and ART30_TRACE_DIR still wins for the harness.
    monkeypatch.setenv("ART30_TRACE_DIR", str(tmp_path / "elsewhere"))
    cli.main(["scan", "fx", "--arm", "baseline", "--case", "S01", "--out", "here",
              "--mode", "replay"])
    assert seen[1] == (Path("here"), tmp_path / "elsewhere")


def test_the_case_defaults_to_a_slug_of_the_directory_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    mkrepo(tmp_path / "My Repo (copy)")

    assert cli.main(["scan", "My Repo (copy)", "--arm", "baseline", "--mode", "replay"]) == 4
    printed = capsys.readouterr().out
    assert "case My_Repo_copy " in printed.splitlines()[0]
    assert (tmp_path / "art30-out/My_Repo_copy/baseline/s1/baseline"
            / "My_Repo_copy-s1.jsonl").is_file()
    # An evaluation id is already a slug; lowering it would miss its cache slot.
    assert cli.slug("D02") == "D02" and cli.slug("...") == "repo"


def test_an_evaluation_id_keeps_its_kind_and_any_other_repository_is_sized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """R01 is real however few files it has; a repository nobody named is real
    above the file threshold and synthetic below it (docs/cli.md)."""
    assert cli.eval_cases() >= {"S01", "S10", "D01", "D02", "R01", "R05"}
    assert cli.case_kind("R01", 3) == "real" and cli.case_kind("S01", 4000) == "synthetic"
    assert cli.case_kind("wagtail", cli.REAL_REPO_FILES) == "synthetic"
    assert cli.case_kind("wagtail", cli.REAL_REPO_FILES + 1) == "real"

    monkeypatch.chdir(tmp_path)
    big = tmp_path / "big"
    mkrepo(big, {f"mod{n}.py": "x = 1\n" for n in range(cli.REAL_REPO_FILES + 1)})
    cli.main(["scan", "big", "--arm", "baseline", "--mode", "replay"])

    header = capsys.readouterr().out.splitlines()[2]
    assert "budget 120 tool calls" in header and f"({cli.REAL_REPO_FILES + 1} files)" in header


def test_the_file_count_ignores_where_the_repository_is_checked_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`_files` excludes `.git`, `media` and their siblings *inside* the repository
    (docs/cli.md, The budget of a repository nobody named). An ancestor directory of
    that name used to zero the count, and the count now picks the tool budget, which
    is a hashed request byte: the same repository has to size the same from anywhere."""
    monkeypatch.chdir(tmp_path)
    files = {f"mod{n}.py": "x = 1\n" for n in range(cli.REAL_REPO_FILES + 1)}
    mkrepo(tmp_path / "plain" / "bigrepo", files)
    mkrepo(tmp_path / "media" / "bigrepo", files)

    headers = []
    for parent in ("plain", "media"):
        cli.main(["scan", f"{parent}/bigrepo", "--arm", "baseline", "--mode", "replay"])
        headers.append(capsys.readouterr().out.splitlines()[2])

    assert f"({cli.REAL_REPO_FILES + 1} files)" in headers[0]
    assert "budget 120 tool calls" in headers[0]
    assert headers[0].split(" · repo ")[0] == headers[1].split(" · repo ")[0]
    assert cli._files(tmp_path / "media" / "bigrepo") == cli.REAL_REPO_FILES + 1


def test_a_real_fixture_is_locked_under_its_case_id_not_its_directory_name(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """R03 and R04 are vendored under their upstream names, so the directory carries
    no case id. The lock resolves the path first (evals/split.yaml, comment 4) and
    holds even when --case names something else."""
    monkeypatch.delenv("ART30_UNLOCK_TEST", raising=False)
    pinry = cli.FIXTURES / "real" / "pinry"
    assert pinry.is_dir() and cli.fixture_case(pinry) == "R03"
    assert cli.fixture_case(D02) == "D02" and cli.fixture_case(cli.REPO_ROOT) is None

    for extra in ([], ["--case", "anything"]):
        assert cli.main(["scan", str(pinry), "--arm", "baseline", *extra]) == 2
        message = capsys.readouterr().err
        assert message.startswith("R03 is in the test split")
        assert "ART30_UNLOCK_TEST=1" in message


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


def test_a_live_run_without_a_key_stops_before_the_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The message a judge with no key sees, printed before anything is spent."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli.config, "read_dotenv", lambda *a, **k: {})   # a judge may have one
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    seen = _spy(monkeypatch)
    _repo(tmp_path)

    assert cli.main(["scan", "fx", "--arm", "baseline", "--case", "S01"]) == 2
    assert capsys.readouterr().err.strip() == (
        "no ANTHROPIC_API_KEY: put it in .env (see .env.example) or export it;"
        " --mode replay needs no key"
    )
    assert seen == []
    # Replay needs no key, which is what the message says.
    assert cli.main(["scan", "fx", "--arm", "baseline", "--case", "S01", "--mode", "replay"]) == 0


def test_the_last_line_names_the_three_files_and_the_trace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """One scripted run, start to finish: the last line is the whole address of
    what it produced (07-ui.md section 2 rule 5)."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "not-a-key-the-scripted-model-never-calls-out")
    repo = _repo(tmp_path)
    scripted = [_response([_submit("t1", record_for(repo.name))])]
    monkeypatch.setattr(llm, "call", lambda req, *, cfg, slot: scripted[slot.step - 1])

    assert cli.main(["scan", "fx", "--arm", "baseline", "--case", "S01"]) == 0
    out = Path("art30-out/fx/baseline/s1")   # printed as written: relative to the cwd
    last = capsys.readouterr().out.splitlines()[-1]

    assert f"{out / 'record.json'} · record.md · record.html · " in last
    assert last.endswith(str(out / "baseline" / "S01-s1.jsonl"))
    for name in ("record.json", "record.md", "record.html"):
        assert (tmp_path / out / name).is_file()
