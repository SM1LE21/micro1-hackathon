"""cases x arms x seeds into runs, traces and failure diagnoses (docs/spec/05-eval-harness.md section 5).

One child `art30 scan` process per cell, so a wall-clock timeout is a kill and a failure is an exit
code rather than an exception in the parent (01-architecture.md section 1.2, decision 9). This module
never imports `loop.run` and never touches `results/metrics.json`, which is `report.py`'s file.

The sweep's own stages are here — the two pre-flight gates, the lock, the plan, the launch, the
timing file — and the detail of each is a sibling module, so no file passes AGENTS.md's ~300 lines:
`plan.py` selects and plans, `ledger.py` is the test-split ledger, `cells.py` is the child and the
scoring that closes it out. Every path a sandboxed sweep redirects (`SPLIT_FILE`, `SPECS`,
`SYNTHETIC`, `REAL`, `MANIFESTS`, `TRACES`, `RESULTS`, `ADR_DIR`) is a constant on this module and
is passed to the sibling that reads it, so rebinding one here is what the sweep then reads; the
siblings carry no path default that could shadow it. Every public name `report.py` or a test reads
on this module is still on it; the split moved pure data and helpers no caller names outside the
harness (`TIMEOUTS`, `REAL_DIRS` to `plan.py`; `CLAUSE`, `check_trace` to `cells.py`).
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess  # noqa: F401 - kept for one seam: `run.subprocess` and `cells.subprocess` are
#   the same module object, so a test that patches `subprocess.run` through this name patches the
#   child launch in `cells.launch`. Deleting the import as unused silently disarms that spy.
import sys
from datetime import datetime, timezone
from pathlib import Path

from evals.harness import ledger
from evals.harness.cells import append_run_end, failure_index, finish_cell, launch, relative, repair
from evals.harness.cells import run_cells as _cells_run
# `ZERO_SHA`, `ARMS`, `Cell`, `cases_for`, `git_sha7`, `membership`, `select_cases` and `Abort` are
# names this module has always carried: `report.py` imports several from here and the harness tests
# read the rest off it, so they are imported to be re-exported.
from evals.harness.ledger import ZERO_SHA, git_sha7  # noqa: F401
from evals.harness.plan import (  # noqa: F401
    ARMS, REPO_ROOT, Abort, Cell, build_cells, cases_for, check_freeze, load_split,
    membership, select_cases, timing_scope,
)
from evals.harness.plan import manifest as _manifest_of

# The paths a sandboxed sweep redirects. They live here and nowhere else: each is passed to the
# sibling that reads it, so `monkeypatch.setattr(run, "<name>", ...)` redirects the sweep itself.
SPLIT_FILE = REPO_ROOT / "evals" / "split.yaml"
MANIFESTS = REPO_ROOT / "evals" / "fixtures" / "manifests"
SPECS = REPO_ROOT / "evals" / "fixtures" / "specs"
SYNTHETIC = REPO_ROOT / "evals" / "fixtures" / "synthetic"
REAL = REPO_ROOT / "evals" / "fixtures" / "real"
TRACES = REPO_ROOT / "traces"
RESULTS = REPO_ROOT / "results"
ADR_DIR = REPO_ROOT / ".vault" / "adr"

DEFAULT_OUT = "results/runs"  # the scored tree; any other --out takes its traces with it (section 9)
LEDGER = "test-runs.log"

# The three seams the tests and section 5.3 know by name: the child launcher a test replaces, and
# the two halves of the timeout repair. All three are handed to `cells.py` at call time — `_launch`
# to `run_cells`, the repair pair to `finish_cell` — so replacing a name on this module replaces
# what a sweep actually runs, not only what a direct call to it does.
_launch = launch
_repair = repair
_append_run_end = append_run_end


# --- the test-split lock (section 5.4) ------------------------------------------------------


def _ledger_lines() -> list[str]:
    return ledger.read_lines(RESULTS / LEDGER)


def _committed_ledger() -> list[str]:
    return ledger.committed_lines(RESULTS / LEDGER, REPO_ROOT)


def _check_lock(args: argparse.Namespace, cases: list[str], split_data: dict) -> tuple[bool, list[str]]:
    """Steps 1 to 4. Returns (the lock applied, the ledger as verified) for the append."""
    member = membership(split_data)
    locked = [c for c in cases if member[c] in ("test", "reserve")]
    if not locked:
        return False, []
    if not args.unlock_test:
        raise Abort(2, f"test-split cases selected: {','.join(locked)}; pass --unlock-test --reason \"...\"")
    if not args.reason:
        raise Abort(1, '--unlock-test requires --reason "..."')
    lines = _ledger_lines()
    ledger.check_chain(lines, _committed_ledger())
    ledger.check_live_budget(lines, args.mode, args.adr, ADR_DIR)
    return True, lines


def _append_ledger(args: argparse.Namespace, cases: list[str], lines: list[str]) -> None:
    """One line per sweep, written before the first model call; replay lines never count."""
    # The contract's clause is about a replay. Suppressing the ledger on a live sweep would let one
    # environment variable defeat the two-sweep ceiling with nothing left on the record.
    if args.mode == "replay" and os.environ.get("ART30_REPRODUCIBLE") == "1":
        return  # contract, Budgets: a replay rewrites neither the ledger nor the timing file
    ledger.append(RESULTS / LEDGER, args, cases, lines)


# --- the plan and the child process ---------------------------------------------------------


def _manifest(case: str) -> tuple[dict, str]:
    """The manifest as bytes and their sha256; `MANIFESTS` is read here so a test may redirect it."""
    return _manifest_of(case, MANIFESTS)


def trace_root(out: str) -> Path:
    """Section 9: a sweep that writes outside the scored tree takes its traces with it.

    `make gate-timing` re-runs six advanced cells only to time the human at the gate; pointed at
    `traces/` those six runs overwrite six committed traces of the recorded sweep, which is the
    evidence the pass exists to leave alone.
    """
    return TRACES if Path(out).resolve() == (REPO_ROOT / DEFAULT_OUT).resolve() else Path(out) / "traces"


def _run_cells(cells: list[Cell], jobs: int, finish, fail_fast: bool) -> list[dict]:
    """`_launch` is read here, at call time, so a test that replaces it is the child that runs."""
    return _cells_run(cells, jobs, finish, fail_fast, _launch)


# --- what the sweep leaves behind -------------------------------------------------------------


def _identity_check(rows: list[dict]) -> None:
    """01 decision 8: the arms' step-1 request hashes match per case, or the comparison is invalid."""
    by_case: dict[str, dict[str, str]] = {}
    for row in rows:
        if row["step1"]:
            by_case.setdefault(row["cell"].case, {})[row["cell"].arm] = row["step1"]
    for case in sorted(by_case):
        if len(set(by_case[case].values())) > 1:
            detail = ", ".join(f"{a}={h[:12]}" for a, h in sorted(by_case[case].items()))
            raise Abort(1, f"{case}: step-1 request hashes differ between arms ({detail})")


def _stat(values: list[float]) -> dict:
    return {"wall_s_mean": round(statistics.fmean(values), 1),
            "wall_s_std": round(statistics.pstdev(values), 1), "n": len(values)}


def _write_timing(mode: str, rows: list[dict], full: bool, tag: str) -> Path | None:
    """Section 6: the live sweep's clock, and never a replay's or a subset's over it.

    `results/timing.json` is the recorded 84-run sweep, which section 9 reads for the README's
    machine minutes. A dev-iteration subset is a live sweep too and would replace it with a
    nine-run advanced-only clock, so only a sweep of both arms over `--split all` claims the name.
    """
    if os.environ.get("ART30_REPRODUCIBLE") == "1" or not rows:
        return None
    per_case: dict[str, dict[str, list[float]]] = {}
    per_arm: dict[str, list[float]] = {}
    for row in rows:
        cell = row["cell"]
        per_case.setdefault(cell.case, {}).setdefault(cell.arm, []).append(row["wall_s"])
        per_arm.setdefault(cell.arm, []).append(row["wall_s"])
    payload = {"recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
               "git_sha": git_sha7(),
               "per_case": {c: {a: _stat(v) for a, v in sorted(arms.items())}
                            for c, arms in sorted(per_case.items())},
               "per_arm": {a: _stat(v) for a, v in sorted(per_arm.items())}}
    if mode != "live":
        name = "timing.replay.json"
    else:
        name = "timing.json" if full else f"timing.{tag}.json"
    path = RESULTS / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="evals.harness.run", description="Run cases x arms x seeds.")
    parser.add_argument("--cases", default=None, help="explicit list, e.g. S01,S03; the lock applies")
    parser.add_argument("--split", default="dev", choices=("dev", "test", "all"))
    parser.add_argument("--include-reserve", action="store_true", help="adds R05; needs --unlock-test")
    parser.add_argument("--arms", default="baseline,advanced")
    parser.add_argument("--seeds", default="1,2,3")
    parser.add_argument("--mode", default="live", choices=("live", "replay"))
    parser.add_argument("--approve", default="auto", choices=("auto", "ask"))
    parser.add_argument("--jobs", type=int, default=None, help="default 4 live, 1 replay")
    parser.add_argument("--timeout", type=int, default=None, help="seconds; default 900 / 1800 real")
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--unlock-test", action="store_true")
    parser.add_argument("--reason", default=None, help="required with --unlock-test; goes in the ledger")
    parser.add_argument("--adr", default=None, help="ADR number authorising a third live test sweep")
    parser.add_argument("--fail-fast", action="store_true")
    return parser


def sweep(args: argparse.Namespace) -> int:
    split_data = load_split(SPLIT_FILE)
    cases = select_cases(split_data, args.split, args.cases, args.include_reserve,
                         split_file=SPLIT_FILE)
    if not cases:
        raise Abort(1, "no cases selected")
    if args.mode == "live" and os.environ.get("ART30_REPRODUCIBLE") == "1":
        raise Abort(1, "ART30_REPRODUCIBLE=1 is the replay flag; it cannot be set on a live sweep")
    locked, ledger_lines = _check_lock(args, cases, split_data)
    loaded = {case: _manifest(case) for case in cases}
    manifests = {case: value[0] for case, value in loaded.items()}
    check_freeze(cases, manifests, split_data, SPECS)
    cells = build_cells(args, cases, manifests, trace_root(args.out), SYNTHETIC, REAL)
    if locked:
        _append_ledger(args, cases, ledger_lines)
    jobs = args.jobs if args.jobs else (1 if args.mode == "replay" else 4)
    print(f"{len(cells)} runs · {len(cases)} cases · mode {args.mode} · jobs {jobs}")

    def finish(cell: Cell, outcome: tuple[int, str, bool, float]) -> dict:
        # `_repair` and `_append_run_end` are read here, at call time, for the reason `_launch` is:
        # a test that replaces one on this module replaces what the sweep does on a timeout.
        row = finish_cell(cell, outcome, manifests[cell.case], loaded[cell.case][1],
                          _repair, _append_run_end)
        metrics = row["metrics"]
        print(f"{cell.arm:<9}{cell.case:<5}s{cell.seed}  {str(row['end'].get('stop_condition')):<17}"
              f"f1 {metrics['f1']:.3f}  fs {metrics['false_safe']}"
              f"  ${float(metrics['run']['cost_usd'] or 0):.2f}  {row['wall_s']}s")
        return row

    rows = _run_cells(cells, jobs, finish, bool(args.fail_fast))
    failure_index(trace_root(args.out))
    _identity_check(rows)
    full, tag = timing_scope(args, cases, split_data)
    timing = _write_timing(args.mode, rows, full, tag)
    accepted = sum(1 for r in rows if r["end"].get("stop_condition") == "accepted")
    print(f"{len(rows)} runs · {accepted} accepted · {len(rows) - accepted} failed")
    if timing:
        print(f"wrote {relative(timing)}")
    # ADR 0003 item 6: replay fails loudly on a miss, which is its own exit code (section 5.5).
    return 5 if any(r["end"].get("stop_condition") == "replay_miss" for r in rows) else 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return sweep(args)
    except Abort as exc:
        print(str(exc), file=sys.stderr)
        return exc.code


if __name__ == "__main__":  # pragma: no cover - module entry point
    sys.exit(main())
