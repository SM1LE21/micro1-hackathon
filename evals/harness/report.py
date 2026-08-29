"""results/runs into results/metrics.json and the Markdown tables (05-eval-harness.md sections 6 to 8).

Recomputes nothing: every number here is an aggregate of the per-run `metrics.json` the runner
already wrote, and `n` comes from the run plan rather than the results tree, so a planned run whose
process died is counted as a `crashed` failure instead of disappearing (01-architecture.md section 9).

Two refusals run before anything is written: the arms must carry the same `prompt_sha`, and their
recording windows must overlap (contract, Trace contract; 01-architecture.md section 4.2).

What is read from disk is here — the traces, the cache windows, the labelling sidecars, the timing
file — and what is computed from what was read is `stats.py` (the aggregates and the two statistics)
and `tables.py` (the Markdown and the changelog row), so no file passes AGENTS.md's ~300 lines.
Every public name a caller or a test reads on this module is still importable from it; three
constants no caller names moved with the code that uses them (`RNG_SEED` and `RESAMPLES` to
`stats.py`, `SECONDARY` to `tables.py`) rather than being re-exported as dead names.
"""

from __future__ import annotations

import argparse
import itertools
import json
import os
import sys
from pathlib import Path

import yaml

from evals.harness.run import ARMS, REPO_ROOT, Abort, git_sha7, membership, select_cases
# Imported to be re-exported: every one of these was a name on `report.py` before the split, and
# `report.mcnemar`, `report.bootstrap`, `report.markdown`, `report.diff_row` and the three "n/a"
# strings are read from this module by the harness tests and by `make report`'s callers.
from evals.harness.stats import (  # noqa: F401
    NO_GATE, NO_TIMING, PROTOCOL, aggregate, bootstrap, comparison, human_time, mcnemar,
)
from evals.harness.tables import NO_PREV, diff_row, markdown, print_summary  # noqa: F401

RESULTS = REPO_ROOT / "results"
TRACES = REPO_ROOT / "traces"
CACHE = REPO_ROOT / "evals" / "cache"
MANIFESTS = REPO_ROOT / "evals" / "fixtures" / "manifests"
SPLIT_FILE = REPO_ROOT / "evals" / "split.yaml"


class Refuse(Exception):
    """A refusal to write `metrics.json`; exit 1 either way."""


# --- reading the plan back --------------------------------------------------------------------


def _zero(case: str, arm: str, seed: int, split: str, stop: str) -> dict:
    """A planned run with no per-run metrics: f1 0.0, counted, never dropped (section 4.4)."""
    return {"case": case, "arm": arm, "seed": seed, "split": split, "f1": 0.0, "precision": 0.0,
            "recall": 0.0, "false_safe": 0, "unmatched_reaching_claims": 0, "pass": False,
            "unverified": 0, "invalid_verdict_for_kind": [], "draft": None,
            "citation_check": {"checked": 0, "bad": 0},
            "run": {"stop_condition": stop, "steps": 0, "tool_calls": 0, "cost_usd": 0.0}}


def _trace_facts(arm: str, case: str, seed: int) -> tuple[str | None, str | None, str]:
    """(prompt_sha, mode, stop condition) from the trace; no run_end line is `crashed` (01 section 9)."""
    path = TRACES / arm / f"{case}-s{seed}.jsonl"
    if not path.is_file():
        return None, None, "crashed"
    start: dict = {}
    ended = "crashed"
    for line in path.read_text(encoding="utf-8", errors="replace").split("\n"):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and obj.get("type") == "run_start" and not start:
            start = obj
        elif isinstance(obj, dict) and obj.get("type") == "run_end":
            ended = str(obj.get("stop_condition") or "crashed")
    return start.get("prompt_sha"), start.get("mode"), ended


def _collect(runs: Path, cases: dict[str, str], arms: list[str], seeds: list[int]) -> tuple[list[dict], dict, set]:
    rows: list[dict] = []
    prompt_shas: dict[str, set[str]] = {arm: set() for arm in arms}
    modes: set[str] = set()
    for case, split in cases.items():
        for seed in seeds:
            for arm in arms:
                sha, mode, stop = _trace_facts(arm, case, seed)
                if sha:
                    prompt_shas[arm].add(sha)
                if mode:
                    modes.add(mode)
                path = runs / arm / case / f"s{seed}" / "metrics.json"
                row = None
                if path.is_file():
                    try:
                        row = json.loads(path.read_text(encoding="utf-8"))
                    except json.JSONDecodeError:
                        row = None
                if not isinstance(row, dict):
                    row = _zero(case, arm, seed, split, stop)
                row["case"], row["arm"], row["seed"], row["split"] = case, arm, seed, split
                rows.append(row)
    return rows, prompt_shas, modes


def _check_prompt_sha(prompt_shas: dict[str, set[str]]) -> None:
    values = {arm: shas for arm, shas in prompt_shas.items() if shas}
    flat = {sha for shas in values.values() for sha in shas}
    if len(flat) > 1:
        detail = "; ".join(f"{arm}: {', '.join(sorted(s)[:2])}" for arm, s in sorted(values.items()))
        raise Refuse(f"the arms do not share one prompt_sha ({detail}); the comparison is not arm-equal")


def _recorded_windows(cases: list[str], arms: list[str], seeds: list[int]) -> dict[str, tuple[str, str]]:
    spans: dict[str, list[str]] = {}
    for arm in arms:
        for case in cases:
            for seed in seeds:
                for entry in sorted((CACHE / case / arm / f"s{seed}").glob("*.json")):
                    try:
                        stamp = json.loads(entry.read_text(encoding="utf-8")).get("recorded_at")
                    except (OSError, json.JSONDecodeError):
                        continue
                    if isinstance(stamp, str):
                        spans.setdefault(arm, []).append(stamp)
    return {arm: (min(values), max(values)) for arm, values in spans.items() if values}


def _check_windows(windows: dict[str, tuple[str, str]]) -> None:
    """01 section 4.2: two arms recorded in disjoint windows carry any drift on one arm alone."""
    for (arm_a, a), (arm_b, b) in itertools.combinations(sorted(windows.items()), 2):
        if a[1] < b[0] or b[1] < a[0]:
            raise Refuse(
                f"recording windows do not overlap: {arm_a} {a[0]}..{a[1]}, {arm_b} {b[0]}..{b[1]}")


# --- the metrics file ---------------------------------------------------------------------------


def _round(value):
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, dict):
        return {k: _round(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_round(v) for v in value]
    return value


def build(runs: Path, split_data: dict, arms: list[str], seeds: list[int],
          include_reserve: bool = False, split: str = "all",
          cases_arg: str | None = None) -> tuple[dict, list[dict]]:
    member = membership(split_data)
    # The same expansion `run.py` planned, or the report books cases the sweep never ran as
    # crashed and prints an F1 for a comparison nobody made (01-architecture.md section 9).
    cases = {c: ("test" if member[c] == "reserve" else member[c])
             for c in select_cases(split_data, split, cases_arg, include_reserve,
                                   split_file=SPLIT_FILE)}
    rows, prompt_shas, modes = _collect(runs, cases, arms, seeds)
    _check_prompt_sha(prompt_shas)
    _check_windows(_recorded_windows(list(cases), arms, seeds))
    timing = None
    path = RESULTS / "timing.json"
    if path.is_file():
        try:
            timing = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            timing = None
    by_split = {name: [c for c, s in cases.items() if s == name] for name in ("dev", "test")}
    arms_block = {
        arm: {name: aggregate([r for r in rows if r["arm"] == arm and r["split"] == name],
                               len(by_split[name])) for name in ("dev", "test")}
        for arm in arms}
    success = sum(1 for r in rows if r["run"].get("stop_condition") == "accepted")
    n_plan = len(cases) * len(arms) * len(seeds)
    metrics = {
        "schema": 1,
        "generated_at": None,
        # Section 10: a file cannot contain the sha of the commit that contains it. Unconditional,
        # or a plain `make report` writes a sha that `make eval-replay`'s diff then fails on.
        # The real sha reaches the reader through results/timing.json, which is never diffed.
        "git_sha": None,
        "model": os.environ.get("ART30_MODEL", "claude-opus-5"),
        "mode": sorted(modes)[0] if len(modes) == 1 else ("mixed" if modes else "replay"),
        "seeds": seeds,
        "cases": by_split,
        "arms": arms_block,
        "per_case": sorted(
            [{"case": r["case"], "arm": r["arm"], "seed": r["seed"], "f1": r["f1"],
              "false_safe": r["false_safe"], "unmatched_reaching_claims": r["unmatched_reaching_claims"],
              "pass": bool(r["pass"]), "stop_condition": r["run"].get("stop_condition"),
              "cost_usd": r["run"].get("cost_usd"), "tool_calls": r["run"].get("tool_calls")}
             for r in rows], key=lambda r: (r["arm"], r["case"], r["seed"])),
        "comparison": {name: comparison([r for r in rows if r["split"] == name], by_split[name],
                                         len(seeds)) for name in ("dev", "test")},
        "human_time": human_time(sorted(cases), timing, MANIFESTS, RESULTS),
        # `n` is the plan's cardinality, computed without the row list, so a `_collect` that ever
        # dropped or duplicated a planned run fails the report instead of passing it (section 6).
        "identity_check": {"n": n_plan, "success": success, "failure": len(rows) - success,
                           "ok": len(rows) == n_plan and success + (len(rows) - success) == n_plan},
    }
    return _round(metrics), rows


# --- entry point --------------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="evals.harness.report", description="runs -> metrics.json")
    parser.add_argument("--runs", default="results/runs")
    parser.add_argument("--out", default="results/metrics.json")
    parser.add_argument("--md", default=None, help="Markdown tables; implies --markdown")
    parser.add_argument("--markdown", action="store_true", help="write results/report.md too")
    parser.add_argument("--arms", default="baseline,advanced")
    parser.add_argument("--seeds", default="1,2,3")
    parser.add_argument("--split", default="all", choices=("dev", "test", "all"),
                        help="expand the same plan the sweep ran; `all` is the recorded sweep")
    parser.add_argument("--cases", default=None, help="explicit list, mirroring run.py's --cases")
    parser.add_argument("--include-reserve", action="store_true")
    parser.add_argument("--prev", default=None, help="previous metrics.json, for the regressions row")
    parser.add_argument("--diff", nargs=2, metavar=("OLD", "NEW"), default=None)
    parser.add_argument("--stage", default="", help="the Stage column of the changelog row")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.diff:
        old, new = (json.loads(Path(p).read_text(encoding="utf-8")) for p in args.diff)
        print(diff_row(old, new, args.stage or "(stage)"))
        return 0
    split_data = yaml.safe_load(SPLIT_FILE.read_text(encoding="utf-8")) or {}
    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    unknown = [a for a in arms if a not in ARMS]
    if unknown:
        print(f"unknown arm in {args.arms!r}: {', '.join(unknown)}", file=sys.stderr)
        return 1
    seeds = [int(s) for s in args.seeds.split(",") if s.strip()]
    prev = json.loads(Path(args.prev).read_text(encoding="utf-8")) if args.prev else None
    try:
        metrics, _ = build(Path(args.runs), split_data, arms, seeds, args.include_reserve,
                           args.split, args.cases)
    except (Refuse, Abort) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    identity = metrics["identity_check"]
    if not identity["ok"]:
        print(f"identity check failed: {identity}", file=sys.stderr)
        return 1
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(metrics, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    if args.markdown or args.md:
        target = Path(args.md or "results/report.md")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(markdown(metrics, prev), encoding="utf-8")
    print_summary(metrics, out)
    return 0


if __name__ == "__main__":  # pragma: no cover - module entry point
    sys.exit(main())
