"""Trace validator: eighteen checks over a runtime trace (docs/spec/06-traces.md section 3).

Pure stdlib, no model. `make smoke` runs it over `traces/`, `run.py` after every run. One line per
violation on stdout, exit 1 when there is at least one; an empty directory is not a failure. A trace
line is data under validation, never a shape to trust: no input may raise out of `check_trace`, whose
only output contract is a list of violation strings.

Three readings 06 section 3 leaves open:
- Check 10 also requires the one checkpoint on an advanced run that ended `gate_rejected`. The row
  names `accepted` only, but a run cannot be rejected by a gate that left no line.
- Check 11 stays silent when `run_end.record_path` does not resolve (06 and 05 both hedge it as
  "when the record exists"), because `results/runs/` is not committed and a violation there would
  turn `make smoke` red on a clean clone. `run.py` owns asserting the file exists before it calls
  this validator, and writes `record_path` repository-relative so the parent walk works from any cwd.
- The file is over AGENTS.md's ~300 lines by design: the eighteen checks and their numbering are one
  responsibility, and splitting them hides which check a violation came from.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

STOP_CONDITIONS = frozenset(
    "accepted gate_rejected budget_exhausted max_submits max_tokens no_submission timeout crashed "
    "replay_miss render_failed api_error refusal".split()
)
ART30_VARS = frozenset(
    "ART30_MODEL ART30_EFFORT ART30_MODE ART30_RECORD ART30_MAX_TOKENS ART30_TOOL_BUDGET "
    "ART30_SUBMIT_BUDGET ART30_MAX_USD ART30_UNLOCK_TEST ART30_REPRODUCIBLE ART30_CONCURRENCY "
    "ART30_CACHE_DIR".split()
)
RECIPIENT_KINDS = frozenset({"unknown", "internal", "processor", "external_controller"})
HIGH_VERDICTS = frozenset(
    "not_erased pseudonymised external_manual no_entry_point no_schedule_evidenced unverified".split()
)
HIGH_CATEGORIES = frozenset({"identifier", "contact"})
REACHES = frozenset({"erased", "erased_after_timer", "anonymised"})
USAGE_KEYS = ("input", "cache_read", "cache_write", "output")

HEX64 = re.compile(r"\A[0-9a-f]{64}\Z")
FILENAME = re.compile(r"\A(?P<case>[A-Za-z0-9_]+)-s(?P<seed>\d+)\Z")
BYTE_COUNT = re.compile(r"\d+\s*bytes?", re.IGNORECASE)
MODEL = os.environ.get("ART30_MODEL", "claude-opus-5")
SUBMIT_BUDGET = 5
EPS = 1e-6


def _objects(value: Any) -> list[dict]:
    """The objects in a list field. Any other shape yields nothing to iterate over."""
    return [x for x in value if isinstance(x, dict)] if isinstance(value, list) else []


def _mapping(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _num(value: Any) -> float:
    """A cost field the trace got wrong is a check-6 mismatch, never a traceback."""
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0.0


def _parse(path: Path) -> tuple[list[tuple[int, dict]], list[str]]:
    """Check 1: UTF-8, LF, no trailing blank line, every line valid JSON."""
    bad: list[str] = []
    raw = path.read_bytes()
    if b"\r" in raw:
        bad.append(f"{path}:0: check 1: CR byte in the file; traces are LF only")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        return [], [f"{path}:0: check 1: not valid UTF-8 ({exc.reason})"]
    parts = text.split("\n")
    if parts and parts[-1] == "":
        parts.pop()
    if not parts:
        return [], [f"{path}:0: check 1: empty trace; expected one run_start and one run_end"]
    out: list[tuple[int, dict]] = []
    for i, line in enumerate(parts, start=1):
        try:  # a blank line lands here too: one JSON object per line, no exceptions
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            bad.append(f"{path}:{i}: check 1: line does not parse as JSON ({exc.msg})")
            continue
        if isinstance(obj, dict):
            out.append((i, obj))
        else:
            bad.append(f"{path}:{i}: check 1: line is not a JSON object")
    return out, bad


def _risk(record: dict) -> str:
    """Contract, Trace contract: the checkpoint's rating, recomputed from the record."""
    stores = _objects(record.get("stores"))
    for store in stores:
        verdict = _mapping(store.get("erasure")).get("verdict")
        categories = {f.get("category") for f in _objects(store.get("fields"))}
        if verdict in HIGH_VERDICTS and categories & HIGH_CATEGORIES:
            return "high"
    verdicts = [_mapping(s.get("erasure")).get("verdict") for s in stores]
    if verdicts and all(v in REACHES for v in verdicts):
        return "medium" if "erased_after_timer" in verdicts else "low"
    return "low"


def _find_record(trace: Path, record_path: Any) -> Path | None:
    if not isinstance(record_path, str) or not record_path:
        return None
    direct = Path(record_path)
    if direct.is_file():
        return direct
    for parent in trace.resolve().parents:
        candidate = parent / record_path
        if candidate.is_file():
            return candidate
    return None


def _check_steps(path: Path, steps: list[tuple[int, dict]], accepted: bool) -> list[str]:
    """Checks 3, 4, 5, 12 and the cost half of check 6."""
    bad: list[str] = []
    seen_ids: dict[str, int] = {}
    cum = 0.0
    for index, (lineno, step) in enumerate(steps):
        if step.get("step") != index + 1:
            bad.append(f"{path}:{lineno}: check 3: step is {step.get('step')!r}, expected {index + 1}")
        calls, results = _objects(step.get("tool_calls")), _objects(step.get("tool_results"))
        for key, kept in (("tool_calls", calls), ("tool_results", results)):
            raw = step.get(key) or []
            if not isinstance(raw, list) or len(raw) != len(kept):
                bad.append(f"{path}:{lineno}: check 4: {key} is not a list of objects")
        call_ids = [c.get("id") for c in calls]
        # A run that did not end accepted may lose the result of its last step's calls.
        pending_ok = index == len(steps) - 1 and not accepted
        for result in results:
            if result.get("call_id") not in call_ids:
                bad.append(f"{path}:{lineno}: check 4: call_id {result.get('call_id')!r} has no call in this step")
        for call_id in call_ids:
            if call_id in seen_ids:
                bad.append(f"{path}:{lineno}: check 5: call id {call_id!r} also used on line {seen_ids[call_id]}")
            seen_ids[call_id] = lineno
            n = sum(1 for r in results if r.get("call_id") == call_id)
            if n != 1 and not (n == 0 and pending_ok):
                bad.append(f"{path}:{lineno}: check 4: call {call_id!r} has {n} results, expected exactly 1")
        usage = step.get("usage")
        if not isinstance(usage, dict):
            bad.append(f"{path}:{lineno}: check 12: usage is {usage!r}, expected an object")
            usage = {}
        for key in USAGE_KEYS:
            value = usage.get(key)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                bad.append(f"{path}:{lineno}: check 12: usage.{key} is {value!r}, expected an integer >= 0")
        if not HEX64.match(str(step.get("request_hash", ""))):
            bad.append(f"{path}:{lineno}: check 12: request_hash is not 64 hex characters")
        if not step.get("stop_reason"):
            bad.append(f"{path}:{lineno}: check 12: stop_reason is missing")
        cost = _num(step.get("cost_usd"))
        reported = _num(step.get("cost_cum_usd"))
        if reported + EPS < cum:
            bad.append(f"{path}:{lineno}: check 6: cost_cum_usd {reported} is below the previous {cum}")
        if abs(reported - (cum + cost)) > EPS:
            bad.append(f"{path}:{lineno}: check 6: cost_cum_usd {reported} != {cum} + cost_usd {cost}")
        cum = reported
    return bad


def _budgets(start: dict) -> tuple[int, int]:
    """Contract, Budgets: both budgets are overridable per run and the override is declared."""
    config = start.get("config") or {}
    overridden = config.get("overridden") or []
    case = str(start.get("case") or "")
    tools = config.get("tool_budget") if "ART30_TOOL_BUDGET" in overridden else None
    submits = config.get("submit_budget") if "ART30_SUBMIT_BUDGET" in overridden else None
    default_tools = 120 if case.upper().startswith("R") else 60
    return (tools if isinstance(tools, int) else default_tools,
            submits if isinstance(submits, int) else SUBMIT_BUDGET)


def _check_run_end(path: Path, lineno: int, end: dict, steps: list[tuple[int, dict]], start: dict) -> list[str]:
    """Checks 7, 8, 9, 14, 16."""
    bad: list[str] = []
    budget, submit_budget = _budgets(start)
    stop = end.get("stop_condition")
    if stop not in STOP_CONDITIONS:
        bad.append(f"{path}:{lineno}: check 14: stop_condition {stop!r} is not one of the twelve contract values")
    cum = _num(steps[-1][1].get("cost_cum_usd")) if steps else 0.0
    if abs(_num(end.get("cost_usd")) - cum) > EPS:
        bad.append(f"{path}:{lineno}: check 7: run_end.cost_usd {end.get('cost_usd')} != last cost_cum_usd {cum}")
    if end.get("steps") != len(steps):
        bad.append(f"{path}:{lineno}: check 7: run_end.steps {end.get('steps')!r} != {len(steps)} step lines")
    total = sum(len(_objects(s.get("tool_calls"))) for _, s in steps)
    if end.get("tool_calls_total") != total:
        bad.append(f"{path}:{lineno}: check 7: tool_calls_total {end.get('tool_calls_total')!r} != {total}")
    submits = sum(1 for _, s in steps for c in _objects(s.get("tool_calls")) if c.get("name") == "submit_record")
    if end.get("submits") != submits:
        bad.append(f"{path}:{lineno}: check 8: submits {end.get('submits')!r} != {submits} submit_record calls")
    if submits > submit_budget:
        bad.append(f"{path}:{lineno}: check 8: {submits} submits exceeds the budget of {submit_budget}")
    reported = end.get("tool_calls_total")  # check 7 has already tied this to the step lines
    calls = reported if isinstance(reported, int) else total
    if calls > budget:
        bad.append(f"{path}:{lineno}: check 8: {calls} tool calls exceeds the budget of {budget}")
    rejections = _rejections(steps)
    if end.get("verify_rounds") != rejections:
        bad.append(f"{path}:{lineno}: check 9: verify_rounds {end.get('verify_rounds')!r} != {rejections} rejections")
    note = end.get("note")
    if isinstance(note, str) and ("truncat" in note.lower() or BYTE_COUNT.search(note)):
        counted = len(BYTE_COUNT.findall(note))
        if stop != "timeout":
            bad.append(f"{path}:{lineno}: check 16: note records a truncation on a run that ended {stop!r}")
        elif counted != 1:
            bad.append(f"{path}:{lineno}: check 16: note carries {counted} byte counts, expected exactly one")
    return bad


def _rejections(steps: list[tuple[int, dict]]) -> int:
    rounds = 0
    for _, step in steps:
        submitted = {c.get("id") for c in _objects(step.get("tool_calls")) if c.get("name") == "submit_record"}
        for result in _objects(step.get("tool_results")):
            if result.get("call_id") not in submitted:
                continue
            try:
                payload = json.loads(result.get("output") or "{}")
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(payload, dict) and payload.get("accepted") is False:
                rounds += 1
    return rounds


def _check_start(path: Path, lineno: int, start: dict) -> list[str]:
    """Checks 13 and 18."""
    bad: list[str] = []
    match = FILENAME.match(path.stem)
    if not match:
        bad.append(f"{path}:{lineno}: check 13: filename is not <case>-s<seed>.jsonl")
    else:
        if start.get("case") != match.group("case"):
            bad.append(f"{path}:{lineno}: check 13: case {start.get('case')!r} != {match.group('case')!r}")
        if str(start.get("seed")) != match.group("seed"):
            bad.append(f"{path}:{lineno}: check 13: seed {start.get('seed')!r} != {match.group('seed')!r}")
    if start.get("arm") != path.parent.name:
        bad.append(f"{path}:{lineno}: check 13: arm {start.get('arm')!r} != directory {path.parent.name!r}")
    if start.get("mode") not in ("live", "replay"):
        bad.append(f"{path}:{lineno}: check 13: mode {start.get('mode')!r} is not live or replay")
    if start.get("model") != MODEL:
        bad.append(f"{path}:{lineno}: check 13: model {start.get('model')!r} != configured {MODEL!r}")
    overridden = (start.get("config") or {}).get("overridden")
    if not isinstance(overridden, list):
        bad.append(f"{path}:{lineno}: check 18: config.overridden is {overridden!r}, expected a list of strings")
    else:
        for name in overridden:
            if name not in ART30_VARS:
                bad.append(f"{path}:{lineno}: check 18: config.overridden names {name!r}, not an ART30_* variable")
    return bad


def _check_gate(path: Path, points: list[tuple[int, dict]], start: dict, end: dict) -> list[str]:
    """Checks 10, 11, 17."""
    bad: list[str] = []
    arm, stop = start.get("arm"), end.get("stop_condition")
    if arm == "baseline" and points:
        bad.append(f"{path}:{points[0][0]}: check 10: the baseline arm must carry no checkpoint")
    if arm == "advanced" and stop in ("accepted", "gate_rejected") and len(points) != 1:
        bad.append(f"{path}:0: check 10: an advanced run that ended {stop} needs one checkpoint, "
                   f"found {len(points)}")
    cited = end.get("record_path")
    record_path = _find_record(path, cited)
    record = None
    if record_path is not None:
        try:
            record = json.loads(record_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
            bad.append(f"{path}:0: check 11: {cited} does not parse as JSON ({exc})")
        if not isinstance(record, dict):
            if record is not None:
                bad.append(f"{path}:0: check 11: {cited} is not a JSON object")
            record = None
    for lineno, point in points:
        if point.get("caller") != "harness":
            bad.append(f"{path}:{lineno}: check 10: checkpoint.caller {point.get('caller')!r} != 'harness'")
        if record is not None and point.get("risk") != _risk(record):
            bad.append(f"{path}:{lineno}: check 11: risk {point.get('risk')!r} != {_risk(record)!r} from the record")
        bad.extend(_check_completions(path, lineno, point, record))
    return bad


def _check_completions(path: Path, lineno: int, point: dict, record: dict | None) -> list[str]:
    completions = point.get("human_completions")
    if completions is None:
        return []
    if point.get("by") == "simulated":
        return [f"{path}:{lineno}: check 17: human_completions must be null when by is 'simulated'"]
    if not isinstance(completions, dict):
        return [f"{path}:{lineno}: check 17: human_completions is {type(completions).__name__}, "
                f"expected an object or null"]
    if set(completions) != {"recipient_kind"}:
        return [f"{path}:{lineno}: check 17: human_completions keys {sorted(completions)} != ['recipient_kind']"]
    raw = completions.get("recipient_kind")
    if not isinstance(raw, dict):
        return [f"{path}:{lineno}: check 17: recipient_kind is {raw!r}, expected a store -> kind object"]
    bad: list[str] = []
    names = {s.get("name") for s in _objects((record or {}).get("stores"))}
    for store, kind in raw.items():
        if kind not in RECIPIENT_KINDS:
            bad.append(f"{path}:{lineno}: check 17: recipient_kind {kind!r} for {store!r} is outside the enum")
        if record is not None and store not in names:
            bad.append(f"{path}:{lineno}: check 17: recipient_kind names store {store!r}, which is not in the record")
    return bad


def _check_diagnosis(path: Path, end: dict) -> list[str]:
    """Check 15, over traces/failures/ only."""
    if "failures" not in path.parts:
        return []
    diagnosis = path.with_suffix(".diagnosis.txt")
    if not diagnosis.is_file():
        return [f"{path}:0: check 15: no {diagnosis.name} beside the failure trace"]
    first = diagnosis.read_text(encoding="utf-8").split("\n", 1)[0]
    fields = first.split(" · ")
    if len(fields) != 4 or len(first) > 160:
        return [f"{diagnosis}:1: check 15: first line is not four fields separated by ' · ' within 160 characters"]
    expected = f"{path.parent.name}/{path.stem}"
    bad: list[str] = []
    if fields[0] != expected:
        bad.append(f"{diagnosis}:1: check 15: first field {fields[0]!r} != {expected!r}")
    if fields[1] != end.get("stop_condition"):
        bad.append(f"{diagnosis}:1: check 15: field 2 {fields[1]!r} != stop_condition {end.get('stop_condition')!r}")
    return bad


def check_trace(path: str | Path) -> list[str]:
    """Every violation in one trace, one string each. Empty means the trace is valid."""
    trace = Path(path)
    lines, bad = _parse(trace)
    if bad or not lines:
        return bad or [f"{trace}:0: check 2: no trace lines"]
    kinds = [obj.get("type") for _, obj in lines]
    if [kinds[0], kinds[-1]] != ["run_start", "run_end"] or kinds.count("run_start") + kinds.count("run_end") != 2:
        return [f"{trace}:0: check 2: expected exactly one run_start first and one run_end last"]
    start, end = lines[0][1], lines[-1][1]
    steps = [(n, o) for n, o in lines if o.get("type") == "step"]
    points = [(n, o) for n, o in lines if o.get("type") == "checkpoint"]
    for lineno, obj in lines[1:-1]:
        if obj.get("type") not in ("step", "checkpoint"):
            bad.append(f"{trace}:{lineno}: check 2: line type {obj.get('type')!r} between run_start and run_end")
    if points and steps and points[0][0] < steps[-1][0]:
        bad.append(f"{trace}:{points[0][0]}: check 2: the checkpoint precedes the last step line")
    bad += _check_start(trace, lines[0][0], start)
    bad += _check_steps(trace, steps, end.get("stop_condition") == "accepted")
    bad += _check_run_end(trace, lines[-1][0], end, steps, start)
    bad += _check_gate(trace, points, start, end)
    if end.get("stop_condition") != "accepted":
        bad += _check_diagnosis(trace, end)
    return bad


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: python -m evals.harness.trace_check <dir-or-file>...", file=sys.stderr)
        return 2
    traces: list[Path] = []
    for arg in argv:
        target = Path(arg)
        if target.is_dir():
            traces.extend(sorted(target.rglob("*.jsonl")))
        elif target.is_file():
            traces.append(target)
        else:
            print(f"{target}:0: not a file or a directory")
            return 1
    violations = [v for trace in traces for v in check_trace(trace)]
    for violation in violations:
        print(violation)
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
