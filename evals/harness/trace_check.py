"""Trace validator: eighteen checks over a runtime trace (docs/spec/06-traces.md section 3).

Pure stdlib, no model. `make smoke` runs it over `traces/`, `run.py` after every run. One line per
violation on stdout, exit 1 when there is at least one; an empty directory is not a failure. A trace
line is data under validation, never a shape to trust: no input may raise out of `check_trace`, whose
only output contract is a list of violation strings.

Checks 1 and 2 (the parse and the line order) are here because they decide whether the rest can run
at all; checks 3 to 18 are `trace_checks.py`, so neither file passes AGENTS.md's ~300 lines. The
numbering is one responsibility and is unchanged: every violation still names its check. The
vocabulary the later checks read against (`STOP_CONDITIONS`, `ART30_VARS`, `RECIPIENT_KINDS`,
`HIGH_VERDICTS`, `HIGH_CATEGORIES`, `REACHES`, `USAGE_KEYS`, `MODEL`, `SUBMIT_BUDGET`, `EPS` and the
three patterns) moved with them and is `trace_checks.py`'s; nothing outside this package reads it,
so it is not re-exported here. The module's callable surface — `check_trace` and `main` — is
unchanged.

Three readings 06 section 3 leaves open:
- Check 10 also requires the one checkpoint on an advanced run that ended `gate_rejected`. The row
  names `accepted` only, but a run cannot be rejected by a gate that left no line.
- Check 11 stays silent when `run_end.record_path` does not resolve (06 and 05 both hedge it as
  "when the record exists"), because `results/runs/` is not committed and a violation there would
  turn `make smoke` red on a clean clone. `run.py` owns asserting the file exists before it calls
  this validator, and writes `record_path` repository-relative so the parent walk works from any cwd.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from evals.harness.trace_checks import (
    check_diagnosis, check_gate, check_run_end, check_start, check_steps,
)


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
    bad += check_start(trace, lines[0][0], start)
    bad += check_steps(trace, steps, end.get("stop_condition") == "accepted")
    bad += check_run_end(trace, lines[-1][0], end, steps, start)
    bad += check_gate(trace, points, start, end)
    if end.get("stop_condition") != "accepted":
        bad += check_diagnosis(trace, end)
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
