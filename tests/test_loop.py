"""The loop's seven stop paths, driven by a scripted `llm.call`.

Offline: no API key, no socket. Every run's trace is handed to the shipped
validator, so a loop change that breaks a trace fails here rather than in the
sweep that recorded 84 of them.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterator

import pytest

from art30 import llm, loop
from art30.config import Config
from art30.loop import CaseRef, run
from baseline.arm import BaselineArm
from evals.harness.trace_check import check_trace

USAGE = {"input": 100, "cache_read": 0, "cache_write": 40, "output": 200}
REPO_ROOT = Path(__file__).resolve().parent.parent
# The six keys a baseline tool result may never carry (01-architecture.md section 1.3).
VERIFIER_KEYS = (
    "rejected_claims", "missing_stores", "missing_entry_points",
    "bad_citations", "unverified", "conservative_divergences",
)


def _response(blocks: list[dict], stop: str = "tool_use") -> llm.Response:
    return llm.Response(
        content=[{"type": "thinking", "thinking": "reading the models"}] + blocks,
        stop_reason=stop,
        stop_details=None,
        usage=dict(USAGE),
        request_id="req_test",
    )


def _use(call_id: str, name: str, payload: dict) -> dict:
    return {"type": "tool_use", "id": call_id, "name": name, "input": payload}


def _read(call_id: str, path: str) -> dict:
    return _use(call_id, "read_file", {"path": path, "start_line": 1, "end_line": None})


def _submit(call_id: str, record: dict) -> dict:
    return _use(call_id, "submit_record", {"record": record})


def _citation(path: str, line: int, symbol: str) -> dict:
    return {"file": path, "line": line, "symbol": symbol}


def record_for(repo_name: str) -> dict:
    """A record that validates and whose every symbol is on its cited line."""
    return {
        "schema_version": "1",
        "repository": repo_name,
        "unscanned": [{"path": "README.md", "reason": "not_python"}],
        "data_subjects": [
            {"label": "account holders", "basis": "model_name", "file": "models.py", "line": 1}
        ],
        "entry_points": [
            {
                "name": "close_account",
                "kind": "route",
                "file": "api/account.py",
                "line": 1,
                "admin_only": False,
                "note": None,
            }
        ],
        "stores": [
            {
                "name": "users",
                "kind": "relational",
                "declared_at": _citation("models.py", 1, "User"),
                "subject_link": {"file": "models.py", "line": 1},
                "fields": [
                    {
                        "name": "email",
                        "category": "contact",
                        "file": "models.py",
                        "line": 2,
                        "note": None,
                        "erasure": None,
                    }
                ],
                "erasure": {
                    "verdict": "not_erased",
                    "evidence": [_citation("storage.py", 4, "cleanup_user_files")],
                    "timer_days": None,
                    "note": "cleanup_user_files is defined at storage.py:4 and has no caller",
                },
                "recipient_kind": None,
                "note": None,
            }
        ],
        "retention": [],
        "activities": [],
        "hints": {
            "observed_module_names": [],
            "observed_region_hints": [],
            "security_evidence": [],
        },
        "human": {
            "controller": {"name": None, "contact": None},
            "joint_controller": {"name": None, "contact": None},
            "representative": {"name": None, "contact": None},
            "dpo": {"name": None, "contact": None},
            "purposes": None,
            "legal_basis": None,
            "data_subject_categories_confirmed": None,
            "data_categories_outside_code": None,
            "special_categories": None,
            "transfers": {"occurs": None, "countries": None, "safeguards": None},
            "retention_justification": None,
            "security_organisational": None,
        },
    }


@pytest.fixture()
def script(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[llm.Response]]:
    """Scripted responses, served by step number. No client is constructed."""
    responses: list[llm.Response] = []

    def fake_call(req: dict, *, cfg: Config, slot: llm.Slot) -> llm.Response:
        assert "system" in req and "tools" in req  # the request is still assembled
        return responses[slot.step - 1]

    monkeypatch.setattr(llm, "call", fake_call)
    yield responses


def _config(tmp_path: Path, **overrides: object) -> Config:
    base = Config(
        trace_dir=tmp_path / "traces",
        out_dir=tmp_path / "out",
        cache_dir=tmp_path / "cache",
        tool_budget=10,
    )
    return Config(**{**base.__dict__, **overrides})


def _case(repo: Path) -> CaseRef:
    return CaseRef(id="S01", name=repo.name, root=repo, kind="synthetic")


def _trace(tmp_path: Path) -> Path:
    return tmp_path / "traces" / "baseline" / "S01-s1.jsonl"


def _lines(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_two_calls_then_a_valid_submit_is_accepted(repo: Path, tmp_path: Path, script) -> None:
    script += [
        _response([_read("t1", "models.py"), _read("t2", "storage.py")]),
        _response([_submit("t3", record_for(repo.name))]),
    ]
    cfg = _config(tmp_path)
    result = run(_case(repo), BaselineArm(), 1, cfg)

    assert result.stop_condition == "accepted"
    assert (result.submits, result.verify_rounds, result.tool_calls_total) == (1, 0, 3)
    out = tmp_path / "out"  # the loop writes to cfg.out_dir verbatim (07-ui.md section 1)
    assert (out / "record.json").is_file()
    assert (out / "record.md").is_file()
    assert (out / "record.html").is_file()
    written = json.loads((out / "record.json").read_text(encoding="utf-8"))
    assert written["provenance"]["arm"] == "baseline"
    assert written["verification"]["accepted_on_attempt"] == 1
    assert check_trace(_trace(tmp_path)) == []


def test_a_rejected_submit_is_an_error_result_and_counts_one_round(
    repo: Path, tmp_path: Path, script
) -> None:
    script += [
        _response([_submit("t1", {"schema_version": "1"})]),
        _response([_submit("t2", record_for(repo.name))]),
    ]
    result = run(_case(repo), BaselineArm(), 1, _config(tmp_path))

    assert result.stop_condition == "accepted"
    assert (result.submits, result.verify_rounds) == (2, 1)
    steps = [line for line in _lines(_trace(tmp_path)) if line["type"] == "step"]
    first = steps[0]["tool_results"][0]
    assert first["is_error"] is True
    payload = json.loads(first["output"])
    assert payload["accepted"] is False and payload["attempt"] == 1
    assert set(payload) == {"accepted", "attempt", "attempts_left", "schema_errors"}
    assert json.loads(steps[1]["tool_results"][0]["output"]) == {"accepted": True}
    assert check_trace(_trace(tmp_path)) == []


def test_five_rejected_submits_end_the_run(repo: Path, tmp_path: Path, script) -> None:
    script += [_response([_submit(f"t{n}", {"schema_version": "1"})]) for n in range(5)]
    result = run(_case(repo), BaselineArm(), 1, _config(tmp_path))

    assert result.stop_condition == "max_submits"
    assert (result.submits, result.verify_rounds, result.steps) == (5, 5, 5)
    assert check_trace(_trace(tmp_path)) == []


def test_the_budget_stops_a_batch_half_way(repo: Path, tmp_path: Path, script) -> None:
    script += [
        _response([_read("t1", "models.py"), _read("t2", "storage.py"), _read("t3", "alpha.py")])
    ]
    result = run(_case(repo), BaselineArm(), 1, _config(tmp_path, tool_budget=2))

    assert result.stop_condition == "budget_exhausted"
    assert result.tool_calls_total == 2
    step = [line for line in _lines(_trace(tmp_path)) if line["type"] == "step"][0]
    assert len(step["tool_calls"]) == 2 and len(step["tool_results"]) == 2
    assert check_trace(_trace(tmp_path)) == []


def test_the_cost_ceiling_names_itself_in_the_note(repo: Path, tmp_path: Path, script) -> None:
    """Two triggers, one stop condition: the note is what tells them apart (02 section 1)."""
    script.append(_response([_read("t1", "models.py")]))
    result = run(_case(repo), BaselineArm(), 1, _config(tmp_path, max_usd=0.0001))

    assert (result.stop_condition, result.tool_calls_total) == ("budget_exhausted", 0)
    assert result.note == "cost ceiling $0.0001 crossed at step 1"
    assert check_trace(_trace(tmp_path)) == []


def test_a_refusal_ends_the_run_before_content_is_read(repo: Path, tmp_path: Path, script) -> None:
    script.append(_response([], stop="refusal"))
    result = run(_case(repo), BaselineArm(), 1, _config(tmp_path))

    assert result.stop_condition == "refusal"
    assert result.tool_calls_total == 0
    assert check_trace(_trace(tmp_path)) == []


def test_three_quiet_turns_end_the_run(repo: Path, tmp_path: Path, script) -> None:
    script += [
        _response([{"type": "text", "text": "I will read the models next."}], stop="end_turn")
        for _ in range(3)
    ]
    result = run(_case(repo), BaselineArm(), 1, _config(tmp_path))

    assert result.stop_condition == "no_submission"
    assert result.steps == 3
    assert check_trace(_trace(tmp_path)) == []


def test_a_truncated_response_is_its_own_stop_condition(
    repo: Path, tmp_path: Path, script
) -> None:
    script.append(_response([], stop="max_tokens"))
    result = run(_case(repo), BaselineArm(), 1, _config(tmp_path))

    assert result.stop_condition == "max_tokens"
    assert "max_tokens=32000" in (result.note or "")
    assert "on step 1" in (result.note or "")
    assert check_trace(_trace(tmp_path)) == []


def test_the_three_quiet_turns_have_to_be_consecutive(
    repo: Path, tmp_path: Path, script
) -> None:
    """01-architecture.md section 9: three *consecutive* turns, not three in a run."""
    quiet = _response([{"type": "text", "text": "I will read the models next."}], stop="end_turn")
    script += [quiet, _response([_read("t1", "models.py")]), quiet, quiet, quiet]
    result = run(_case(repo), BaselineArm(), 1, _config(tmp_path))

    assert result.stop_condition == "no_submission"
    assert result.steps == 5
    assert check_trace(_trace(tmp_path)) == []


def test_a_replay_miss_writes_a_run_end_and_no_step_line(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No step line exists for a call that raised inside `llm.call` (01 section 9)."""
    cfg = _config(tmp_path, mode="replay")

    def miss(req: dict, *, cfg: Config, slot: llm.Slot) -> llm.Response:
        raise llm.ReplayMiss(slot, None, "0" * 64, cfg)

    monkeypatch.setattr(llm, "call", miss)
    result = run(_case(repo), BaselineArm(), 1, cfg)

    assert (result.stop_condition, result.steps) == ("replay_miss", 0)
    assert [line["type"] for line in _lines(_trace(tmp_path))] == ["run_start", "run_end"]
    assert check_trace(_trace(tmp_path)) == []


def test_a_second_submit_in_one_turn_does_not_spend_an_attempt(
    repo: Path, tmp_path: Path, script
) -> None:
    valid = record_for(repo.name)
    script.append(_response([_submit("t1", valid), _submit("t2", valid)]))
    result = run(_case(repo), BaselineArm(), 1, _config(tmp_path))

    assert result.submits == 1 and result.tool_calls_total == 2
    step = [line for line in _lines(_trace(tmp_path)) if line["type"] == "step"][0]
    assert json.loads(step["tool_results"][1]["output"])["reason"] == "one submit_record per turn"


def test_an_arm_that_raises_still_writes_a_run_end_line(repo: Path, tmp_path: Path, script) -> None:
    class Exploding(BaselineArm):
        def handle_submit(self, record: dict, ctx) -> None:  # type: ignore[override]
            raise RuntimeError("verifier bug")

    script.append(_response([_submit("t1", record_for(repo.name))]))
    result = run(_case(repo), Exploding(), 1, _config(tmp_path))

    assert result.stop_condition == "api_error"
    assert "RuntimeError" in (result.note or "")
    assert _lines(_trace(tmp_path))[-1]["type"] == "run_end"
    # The counters on that run_end still describe step lines that exist.
    assert check_trace(_trace(tmp_path)) == []


def test_the_loop_holds_no_conditional_on_the_arm_name() -> None:
    """The claim of 01-architecture.md section 3, enforced rather than restated."""
    source = Path(loop.__file__).read_text(encoding="utf-8")
    branching = [
        line.strip()
        for line in source.splitlines()
        if "arm.name" in line and re.search(r"\bif\b|\belif\b|==|!=", line)
    ]
    assert branching == []


def test_no_baseline_tool_result_carries_verifier_vocabulary(
    repo: Path, tmp_path: Path, script
) -> None:
    """The baseline's only model-visible channel names no verifier key (01 section 1.3)."""
    script += [
        _response([_submit("t1", {"schema_version": "1"})]),
        _response([_submit("t2", record_for(repo.name))]),
    ]
    run(_case(repo), BaselineArm(), 1, _config(tmp_path))

    traces = [_trace(tmp_path)] + sorted((REPO_ROOT / "traces" / "baseline").glob("*.jsonl"))
    for path in traces:
        for line in _lines(path):
            for result in line.get("tool_results") or []:
                for key in VERIFIER_KEYS:
                    assert key not in result["output"], f"{path.name} names {key}"


def test_first_turn_template_carries_no_absolute_path() -> None:
    """02-agent-loop.md section 2 (deviation D-04): the first user turn is rendered from the case
    name and the two budgets only, so nothing machine-specific can enter the hashed request."""
    rendered = loop.FIRST_TURN.format(repo_name="S01", tool_call_budget=60, submit_budget=5)
    assert not re.search(r"(^|\s)/[A-Za-z]", rendered), rendered
    assert "S01" in rendered and "60 tool calls" in rendered and "5 submit_record" in rendered
    placeholders = set(re.findall(r"{(\w+)}", loop.FIRST_TURN))
    assert placeholders == {"repo_name", "tool_call_budget", "submit_budget"}


def test_trace_dir_env_is_honoured(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """01-architecture.md section 9 seam: the harness hands each cell its own trace directory
    through ART30_TRACE_DIR; a child that ignored it would overwrite the committed traces."""
    from art30 import config as config_mod
    monkeypatch.setattr(config_mod, "read_dotenv", lambda *a, **k: {})
    monkeypatch.setenv("ART30_TRACE_DIR", str(tmp_path / "elsewhere"))
    cfg = config_mod.load()
    assert cfg.trace_dir == tmp_path / "elsewhere"
    monkeypatch.delenv("ART30_TRACE_DIR")
    assert config_mod.load().trace_dir == Path("traces")
