"""Trace validator tests (docs/spec/06-traces.md section 3).

A hand-written valid trace in the shape of section 2's worked run, then one trace per violation
class. Every check the validator claims is exercised by a trace that breaks it.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from evals.harness.trace_check import check_trace, main

RECORD_PATH = "results/runs/advanced/S10/s1/record.json"
RECORD = {
    "schema_version": "1",
    "repository": "tidewharf",
    "stores": [
        {"name": "users", "kind": "relational",
         "fields": [{"name": "email", "category": "contact", "file": "models.py", "line": 15}],
         "erasure": {"verdict": "erased_after_timer", "timer_days": 30}},
        {"name": "uploads", "kind": "object_storage",
         "fields": [{"name": "avatar_key", "category": "identifier", "file": "storage.py", "line": 9}],
         "erasure": {"verdict": "not_erased", "timer_days": None}},
    ],
}
REJECTION = json.dumps({"accepted": False, "attempt": 1, "attempts_left": 4, "schema_errors": []})


def _step(step: int, calls: list, results: list, cost: float, cum: float, phase: str = "agent") -> dict:
    return {"type": "step", "step": step, "phase": phase, "ts": "2026-08-30T14:02:19.882Z",
            "request_id": "req_011CQx7", "request_hash": "a" * 64, "stop_reason": "tool_use",
            "reasoning": "", "text": "", "tool_calls": calls, "tool_results": results,
            "usage": {"input": 2314, "cache_read": 0, "cache_write": 4180, "output": 188},
            "cost_usd": cost, "cost_cum_usd": cum}


def valid_lines() -> list[dict]:
    """The section 2 run, shortened: one read, a rejected submit, an accepted submit, the gate."""
    return [
        {"type": "run_start", "run_id": "adv-S10-s1-9f3ac1e", "arm": "advanced", "case": "S10",
         "seed": 1, "model": "claude-opus-5", "effort": "high", "mode": "replay",
         "prompt_sha": "c" * 64,
         "config": {"max_tokens": 32000, "tool_budget": 60, "submit_budget": 5, "overridden": []},
         "ts": "2026-08-30T14:02:11.004Z"},
        _step(1, [{"id": "toolu_01A", "name": "list_tree", "input": {"path": "."}}],
              [{"call_id": "toolu_01A", "output": "models.py  (863 B)", "is_error": False, "bytes": 18}],
              0.04, 0.04),
        _step(2, [{"id": "toolu_01M", "name": "submit_record", "input": {"record": RECORD}}],
              [{"call_id": "toolu_01M", "output": REJECTION, "is_error": False, "bytes": len(REJECTION)}],
              0.03, 0.07, phase="verify"),
        _step(3, [{"id": "toolu_01N", "name": "submit_record", "input": {"record": RECORD}}],
              [{"call_id": "toolu_01N", "output": '{"accepted":true}', "is_error": False, "bytes": 17}],
              0.05, 0.12, phase="verify"),
        {"type": "checkpoint", "tool": "request_approval", "caller": "harness", "risk": "high",
         "summary": "2 stores. uploads NOT ERASED (identifier: avatar_key).",
         "decision": "approved", "by": "simulated", "wait_s": 0.0, "human_completions": None,
         "ts": "2026-08-30T14:05:40.004Z"},
        {"type": "run_end", "stop_condition": "accepted", "steps": 3, "tool_calls_total": 3,
         "submits": 2, "verify_rounds": 1, "wall_s": 209.0, "cost_usd": 0.12,
         "record_path": RECORD_PATH, "note": None},
    ]


def _write(tmp_path: Path, lines: list[dict] | None = None, *, arm: str = "advanced",
           name: str = "S10-s1.jsonl", failures: bool = False, record: dict | None = RECORD,
           text: str | None = None) -> Path:
    parts = ("traces", "failures", arm) if failures else ("traces", arm)
    directory = tmp_path.joinpath(*parts)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    body = text if text is not None else "\n".join(
        json.dumps(o) for o in (valid_lines() if lines is None else lines)) + "\n"
    path.write_text(body, encoding="utf-8")
    if record is not None:
        target = tmp_path / RECORD_PATH
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(record), encoding="utf-8")
    return path


def _mutate(**overrides: Any) -> list[dict]:
    lines = copy.deepcopy(valid_lines())
    for key, value in overrides.items():
        index = {"start": 0, "step1": 1, "step2": 2, "step3": 3, "gate": 4, "end": 5}[key]
        lines[index].update(value)
    return lines


def _codes(violations: list[str]) -> set[str]:
    return {v.split("check ", 1)[1].split(":")[0] for v in violations if "check " in v}


def test_valid_trace_has_no_violations(tmp_path: Path) -> None:
    assert check_trace(_write(tmp_path)) == []


def test_check_1_line_that_does_not_parse(tmp_path: Path) -> None:
    body = "\n".join(json.dumps(o) for o in valid_lines()[:-1]) + "\n{not json}\n"
    assert "1" in _codes(check_trace(_write(tmp_path, text=body)))


def test_check_1_trailing_blank_line(tmp_path: Path) -> None:
    body = "\n".join(json.dumps(o) for o in valid_lines()) + "\n\n"
    assert "1" in _codes(check_trace(_write(tmp_path, text=body)))


def test_check_2_missing_run_end(tmp_path: Path) -> None:
    assert "2" in _codes(check_trace(_write(tmp_path, valid_lines()[:-1])))


def test_check_2_two_run_starts(tmp_path: Path) -> None:
    lines = valid_lines()
    assert "2" in _codes(check_trace(_write(tmp_path, [lines[0]] + lines)))


def test_check_3_step_numbers_have_a_gap(tmp_path: Path) -> None:
    assert "3" in _codes(check_trace(_write(tmp_path, _mutate(step2={"step": 4}))))


def test_check_4_result_without_a_call_in_the_same_step(tmp_path: Path) -> None:
    lines = _mutate(step1={"tool_results": [{"call_id": "toolu_ZZ", "output": "x",
                                             "is_error": False, "bytes": 1}]})
    assert "4" in _codes(check_trace(_write(tmp_path, lines)))


def test_check_4_call_without_a_result_is_allowed_on_a_failed_run(tmp_path: Path) -> None:
    lines = _mutate(step3={"tool_results": []},
                    end={"stop_condition": "timeout", "submits": 2, "verify_rounds": 1,
                         "record_path": None, "note": "repaired: 143 bytes truncated"})
    del lines[4]  # no gate on a run that never reached acceptance
    path = _write(tmp_path, lines, failures=True)
    path.with_suffix(".diagnosis.txt").write_text(
        "advanced/S10-s1 · timeout · the run was killed on wall clock · steps 1-3\n", encoding="utf-8")
    assert check_trace(path) == []


def test_check_5_duplicate_tool_call_id(tmp_path: Path) -> None:
    lines = _mutate(step3={"tool_calls": [{"id": "toolu_01A", "name": "submit_record", "input": {}}],
                           "tool_results": [{"call_id": "toolu_01A", "output": '{"accepted":true}',
                                             "is_error": False, "bytes": 17}]})
    assert "5" in _codes(check_trace(_write(tmp_path, lines)))


def test_check_6_cost_sums_do_not_reconcile(tmp_path: Path) -> None:
    assert "6" in _codes(check_trace(_write(tmp_path, _mutate(step2={"cost_cum_usd": 0.9}))))


def test_check_7_run_end_step_count_is_wrong(tmp_path: Path) -> None:
    assert "7" in _codes(check_trace(_write(tmp_path, _mutate(end={"steps": 9}))))


def test_check_8_submits_do_not_match_the_calls(tmp_path: Path) -> None:
    assert "8" in _codes(check_trace(_write(tmp_path, _mutate(end={"submits": 1}))))


def test_check_9_verify_rounds_count_handled_submits(tmp_path: Path) -> None:
    assert "9" in _codes(check_trace(_write(tmp_path, _mutate(end={"verify_rounds": 2}))))


def test_check_10_baseline_carries_no_checkpoint(tmp_path: Path) -> None:
    lines = _mutate(start={"arm": "baseline", "run_id": "base-S10-s1-9f3ac1e"})
    assert "10" in _codes(check_trace(_write(tmp_path, lines, arm="baseline")))


def test_check_11_risk_rating_drifted_from_the_record(tmp_path: Path) -> None:
    assert "11" in _codes(check_trace(_write(tmp_path, _mutate(gate={"risk": "low"}))))


def test_check_11_medium_when_every_store_reaches_after_a_timer(tmp_path: Path) -> None:
    record = copy.deepcopy(RECORD)
    record["stores"][1]["erasure"] = {"verdict": "erased", "timer_days": None}
    path = _write(tmp_path, _mutate(gate={"risk": "medium"}), record=record)
    assert check_trace(path) == []


def test_check_12_usage_and_request_hash(tmp_path: Path) -> None:
    lines = _mutate(step1={"usage": {"input": -1, "cache_read": 0, "cache_write": 0, "output": 5},
                           "request_hash": "short"})
    assert _codes(check_trace(_write(tmp_path, lines))) == {"12"}


def test_check_13_arm_and_model_must_match(tmp_path: Path) -> None:
    lines = _mutate(start={"arm": "baseline", "model": "claude-3-haiku"})
    assert "13" in _codes(check_trace(_write(tmp_path, lines)))


def test_check_14_stop_condition_outside_the_enum(tmp_path: Path) -> None:
    assert "14" in _codes(check_trace(_write(tmp_path, _mutate(end={"stop_condition": "done"}))))


def test_check_15_failure_trace_without_a_diagnosis(tmp_path: Path) -> None:
    lines = _mutate(end={"stop_condition": "max_submits", "record_path": None})
    del lines[4]
    assert "15" in _codes(check_trace(_write(tmp_path, lines, failures=True)))


def test_check_16_truncation_recorded_on_a_run_that_did_not_time_out(tmp_path: Path) -> None:
    lines = _mutate(end={"note": "repaired: 143 bytes truncated"})
    assert "16" in _codes(check_trace(_write(tmp_path, lines)))


def test_check_17_human_completions_shape(tmp_path: Path) -> None:
    lines = _mutate(gate={"by": "human", "wait_s": 36.0,
                          "human_completions": {"recipient_kind": {"uploads": "processor"},
                                                "purposes": "billing"}})
    assert "17" in _codes(check_trace(_write(tmp_path, lines)))


def test_check_17_recipient_kind_names_a_store_in_the_record(tmp_path: Path) -> None:
    lines = _mutate(gate={"by": "human", "wait_s": 36.0,
                          "human_completions": {"recipient_kind": {"mailgun": "processor"}}})
    assert "17" in _codes(check_trace(_write(tmp_path, lines)))


def test_check_18_overridden_names_an_unknown_variable(tmp_path: Path) -> None:
    lines = _mutate(start={"config": {"max_tokens": 32000, "tool_budget": 60, "submit_budget": 5,
                                      "overridden": ["ART30_BUDGET"]}})
    assert "18" in _codes(check_trace(_write(tmp_path, lines)))


def test_main_exits_zero_on_a_directory_with_no_traces(tmp_path: Path) -> None:
    (tmp_path / "traces").mkdir()
    assert main([str(tmp_path / "traces")]) == 0


def test_main_exits_one_when_a_trace_is_invalid(tmp_path: Path, capsys: Any) -> None:
    _write(tmp_path, _mutate(end={"steps": 9}))
    assert main([str(tmp_path / "traces")]) == 1
    assert "check 7" in capsys.readouterr().out


def test_check_8_tool_budget_follows_a_declared_override(tmp_path: Path) -> None:
    over = _codes(check_trace(_write(tmp_path, _mutate(end={"tool_calls_total": 61}))))
    lifted = _mutate(end={"tool_calls_total": 61},
                     start={"config": {"max_tokens": 32000, "tool_budget": 200,
                                       "submit_budget": 5, "overridden": ["ART30_TOOL_BUDGET"]}})
    assert "8" in over
    assert "8" not in _codes(check_trace(_write(tmp_path, lifted, name="S10-s1.jsonl")))


# --- malformed input must produce violations, never a traceback ------------------------------


def test_check_11_record_that_does_not_parse_is_a_violation(tmp_path: Path) -> None:
    # A crashed or timed-out run is exactly what leaves a half-written record.json behind.
    path = _write(tmp_path)
    (tmp_path / RECORD_PATH).write_text("{not json", encoding="utf-8")
    assert "11" in _codes(check_trace(path))


def test_check_11_record_that_is_not_an_object_is_a_violation(tmp_path: Path) -> None:
    path = _write(tmp_path)
    (tmp_path / RECORD_PATH).write_text("[1, 2, 3]", encoding="utf-8")
    assert "11" in _codes(check_trace(path))


def test_check_4_tool_calls_that_are_not_objects(tmp_path: Path) -> None:
    for value in (["toolu_01A"], {"id": "toolu_01A"}):
        lines = _mutate(step1={"tool_calls": value, "tool_results": []})
        assert "4" in _codes(check_trace(_write(tmp_path, lines)))


def test_check_12_usage_that_is_not_an_object(tmp_path: Path) -> None:
    # A non-empty list survives `or {}`, which is how the guard used to be written.
    assert "12" in _codes(check_trace(_write(tmp_path, _mutate(step1={"usage": [1, 2, 3, 4]}))))


def test_check_10_gate_rejected_run_without_a_checkpoint(tmp_path: Path) -> None:
    lines = _mutate(end={"stop_condition": "gate_rejected", "record_path": None})
    del lines[4]
    assert "10" in _codes(check_trace(_write(tmp_path, lines)))


def test_check_16_a_byte_count_is_a_truncation_whatever_verb_it_uses(tmp_path: Path) -> None:
    lines = _mutate(end={"note": "parent discarded 143 bytes of a partial line"})
    assert "16" in _codes(check_trace(_write(tmp_path, lines)))


def test_check_17_human_completions_that_is_not_an_object(tmp_path: Path) -> None:
    lines = _mutate(gate={"by": "human", "wait_s": 36.0,
                          "human_completions": ["recipient_kind"]})
    violations = check_trace(_write(tmp_path, lines))
    assert "17" in _codes(violations)
    assert "expected an object or null" in violations[0]


def test_check_17_recipient_kind_that_is_not_a_mapping(tmp_path: Path) -> None:
    lines = _mutate(gate={"by": "human", "wait_s": 36.0,
                          "human_completions": {"recipient_kind": "processor"}})
    assert "17" in _codes(check_trace(_write(tmp_path, lines)))
