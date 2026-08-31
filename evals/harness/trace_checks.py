"""The eighteen numbered checks (docs/spec/06-traces.md section 3).

Split out of `trace_check.py` so each file stays inside AGENTS.md's ~300 lines; the numbering is
unchanged and every violation string still names its check, so a reader still sees which check a
line came from. `trace_check.py` owns check 1 (the parse) and check 2 (the line order) and calls
the five entry points here: `check_start`, `check_steps`, `check_run_end`, `check_gate`,
`check_diagnosis`. Nothing here reads a manifest or a model; a trace line is data under
validation, never a shape to trust, so no input may raise out of a check.
"""

from __future__ import annotations

import json
import os
import re
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
API_BRAIN = "api"
# Which brain wrote the trace under validation, keyed by path. `check_start` is the
# only check that sees `run_start`, `check_steps` is the only one that sees the step
# lines, and `trace_check.check_trace` calls them in that order over one file, so this is
# how the request_hash rule below gets its other half without changing either entry point's
# shape for `trace_check.py` (ADR 0008). It is a fallback only: `check_steps` takes the
# brain as an argument and pops the entry on the way out.
_BRAIN: dict[str, str] = {}
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
    """A relative `record_path` is anchored to the run's own tree (the trace's
    parents), never to the checker's working directory: once a sweep has written
    `results/...` into the repository, a CWD-relative hit would shadow the run's
    own record and check 11 would read the wrong document. An absolute path is
    unaffected either way (`parent / "/abs"` is `/abs`)."""
    if not isinstance(record_path, str) or not record_path:
        return None
    for parent in trace.resolve().parents:
        candidate = parent / record_path
        if candidate.is_file():
            return candidate
    direct = Path(record_path)
    if direct.is_file():
        return direct
    return None


def check_steps(path: Path, steps: list[tuple[int, dict]], accepted: bool,
                brain: str | None = None) -> list[str]:
    """Checks 3, 4, 5, 12 and the cost half of check 6.

    `brain` is check 12's one input that is not on a step line (ADR 0008 item 1): it comes
    off `run_start`, which only `check_start` sees. A caller that is not `check_trace` — a
    test, the website's validator — passes it rather than being stuck with the API brain's
    strict rule; unpassed, the `_BRAIN` map `check_start` filled is the fallback, and the
    entry is dropped on the way out so no verdict depends on it outliving this call.
    """
    bad: list[str] = []
    seen_ids: dict[str, int] = {}
    cum = 0.0
    wrote = brain if brain is not None else _BRAIN.get(str(path), API_BRAIN)
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
        bad += _request_hash(path, lineno, step, wrote)
        if not step.get("stop_reason"):
            bad.append(f"{path}:{lineno}: check 12: stop_reason is missing")
        cost = _num(step.get("cost_usd"))
        reported = _num(step.get("cost_cum_usd"))
        if reported + EPS < cum:
            bad.append(f"{path}:{lineno}: check 6: cost_cum_usd {reported} is below the previous {cum}")
        if abs(reported - (cum + cost)) > EPS:
            bad.append(f"{path}:{lineno}: check 6: cost_cum_usd {reported} != {cum} + cost_usd {cost}")
        cum = reported
    _BRAIN.pop(str(path), None)
    return bad


def _request_hash(path: Path, lineno: int, step: dict, brain: str) -> list[str]:
    """Check 12, with ADR 0008 item 1's one exception.

    The API brain hashes the request it assembled, and that hash is what makes a
    recorded run replayable. A local brain assembles its request inside the `claude`
    or `codex` process, so there are no bytes for art30 to hash and the field is null
    rather than a number nobody could recompute. Null is accepted only there: on an
    `api` run a missing hash is a lost replay and stays a violation.
    """
    raw = step.get("request_hash")
    if raw is None and brain != API_BRAIN:
        return []
    if HEX64.match(str(raw or "")):
        return []
    if raw is None:
        return [f"{path}:{lineno}: check 12: request_hash is null on a brain {brain!r} run"]
    return [f"{path}:{lineno}: check 12: request_hash is not 64 hex characters"]


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


def check_run_end(path: Path, lineno: int, end: dict, steps: list[tuple[int, dict]], start: dict) -> list[str]:
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


def check_start(path: Path, lineno: int, start: dict) -> list[str]:
    """Checks 13 and 18."""
    bad: list[str] = []
    _BRAIN[str(path)] = str((start.get("config") or {}).get("brain") or API_BRAIN)
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


def check_gate(path: Path, points: list[tuple[int, dict]], start: dict, end: dict) -> list[str]:
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


def check_diagnosis(path: Path, end: dict) -> list[str]:
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
