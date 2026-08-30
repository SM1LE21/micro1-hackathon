"""results/runs into results/metrics.json and the Markdown tables (05-eval-harness.md sections 6 to 8).

Recomputes nothing: every number here is an aggregate of the per-run `metrics.json` the runner
already wrote, and `n` comes from the run plan rather than the results tree, so a planned run whose
process died is counted as a `crashed` failure instead of disappearing (01-architecture.md section 9).

Five refusals run before anything is written: every scored run must have a trace under the root
this tree's traces live in (`--traces`, or the mirror of `run.trace_root`), the arms must carry the
same `prompt_sha`, one results tree is one brain and one `brain_model` — measured dollars and a
list-price estimate are not one column, and two CLI defaults are not one comparison (ADR 0008
items 4 and 5) — and the arms' recording windows must overlap (contract, Trace contract;
01-architecture.md section 4.2).

What is read off one run is `facts.py` (its trace, the record it delivered, the metrics it was
scored at) and what is computed from what was read is `stats.py` (the aggregates, the two
statistics, the recording windows, which are read there because `CACHE` is passed in from here)
and `tables.py` (the Markdown and the changelog row), so no file passes AGENTS.md's ~300 lines.
What stays here is the plan expansion, the five refusals, the two files this module reads by name
— the timing file and the labelling sidecars — and every path a sandboxed report redirects.
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

# The reading half of this module, split out for the line rule; `report.py` still owns every
# path it reads and passes each one in.
from evals.harness.facts import collect as _collect
from evals.harness.run import ARMS, REPO_ROOT, Abort, git_sha7, membership, select_cases
# Imported to be re-exported: every one of these was a name on `report.py` before the split, and
# `report.mcnemar`, `report.bootstrap`, `report.markdown`, `report.diff_row` and the three "n/a"
# strings are read from this module by the harness tests and by `make report`'s callers.
from evals.harness.stats import (  # noqa: F401
    NO_GATE, NO_TIMING, PROTOCOL, aggregate, bootstrap, comparison, cost_source, human_time,
    mcnemar, recorded_windows,
)
from evals.harness.tables import NO_PREV, diff_row, markdown, print_summary  # noqa: F401

RESULTS = REPO_ROOT / "results"
TRACES = REPO_ROOT / "traces"
CACHE = REPO_ROOT / "evals" / "cache"
MANIFESTS = REPO_ROOT / "evals" / "fixtures" / "manifests"
SPLIT_FILE = REPO_ROOT / "evals" / "split.yaml"

API_BRAIN = "api"
MEASURED = "measured"          # the API brain: the cost the request was billed at
CLI_ESTIMATE = "cli_estimate"  # a local CLI's own token counts, priced at API list prices
UNPRICED = "unpriced"          # a model with no price entry: tokens only, never a dollar figure


class Refuse(Exception):
    """A refusal to write `metrics.json`; exit 1 either way."""


# --- where a tree's traces are, and the five refusals ------------------------------------------


def _traces_root(runs: Path) -> Path:
    """Where this results tree's traces are, mirroring `run.trace_root` (05 section 9).

    A sweep writes `traces/` only for the scored tree; any other `--out` takes its traces
    with it, into `<out>/traces`. Reading the module constant for every tree is how a
    local-brain sweep reported at a different `--out` silently became `brain: api` with
    `cost_source: measured` — a subscription estimate printed as billed dollars — because
    no trace was found and every refusal that keys off a trace passed vacuously.

    The condition is anchored on `REPO_ROOT`, not on this module's rebindable `RESULTS`,
    because `run.trace_root` anchors it there: a sandboxed sweep writing to its own
    `<scratch>/results/runs` still puts its traces under that tree, and a report that
    followed a rebound `RESULTS` would look somewhere the sweep never wrote. `--traces`
    is the override for a tree whose traces were moved after the fact.
    """
    return TRACES if runs.resolve() == (REPO_ROOT / "results" / "runs").resolve() else runs / "traces"


def _check_traces(blind: list[str], traces: Path) -> None:
    """A scored run with no trace is refused, not read as an API run (ADR 0008 item 4).

    Every brain and cost fact hangs off the trace lookup, and every refusal that reads one
    — the prompt_sha check, the mixed-brain check, the recording windows — passes vacuously
    when the file is not there. Silence would relabel a subscription sweep `api`/`measured`
    and fold its list-price estimate into a column of billed dollars.
    """
    if blind:
        listed = ", ".join(sorted(blind)[:6]) + (" ..." if len(blind) > 6 else "")
        raise Refuse(f"{len(blind)} scored runs with no trace under {traces}: {listed};"
                     " pass --traces if this tree's traces are elsewhere")


def _check_brain_models(facts: dict) -> str | None:
    """The model that actually answered, and one of it per results tree (ADR 0008 item 5).

    On a local brain the configured model is usually null — the CLI's own default answered
    — and only the run's record names what that was. `prompt_sha` cannot see this drift:
    the instruction text is a constant of the checkout, so two arms swept at two different
    CLI defaults would pass the arm-equality check and still not be one comparison.
    """
    by_arm: dict[str, set[str]] = {}
    for (arm, _case, _seed), fact in facts.items():
        if fact.get("brain_model"):
            by_arm.setdefault(arm, set()).add(str(fact["brain_model"]))
    seen = {model for models in by_arm.values() for model in models}
    if len(seen) > 1:
        detail = "; ".join(f"{arm}: {', '.join(sorted(m))}" for arm, m in sorted(by_arm.items()))
        raise Refuse(f"the runs do not share one brain_model ({detail});"
                     " the comparison is not model-equal")
    return sorted(seen)[0] if seen else None


def _check_brains(facts: dict) -> str:
    """One metrics.json describes one brain (ADR 0008 item 4): two of them in one file would
    put an API run's measured dollars in the same column as a subscription run's list-price
    estimate and label the pair a comparison. The README names one brain beside the table."""
    seen = sorted({str(f["brain"]) for f in facts.values() if f["prompt_sha"] or f["tokens"]})
    if len(seen) > 1:
        raise Refuse(f"runs from more than one brain in one results tree: {', '.join(seen)};"
                     " report each brain separately")
    return seen[0] if seen else API_BRAIN


def _check_prompt_sha(prompt_shas: dict[str, set[str]]) -> None:
    values = {arm: shas for arm, shas in prompt_shas.items() if shas}
    flat = {sha for shas in values.values() for sha in shas}
    if len(flat) > 1:
        detail = "; ".join(f"{arm}: {', '.join(sorted(s)[:2])}" for arm, s in sorted(values.items()))
        raise Refuse(f"the arms do not share one prompt_sha ({detail}); the comparison is not arm-equal")


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
          include_reserve: bool = False, split: str = "all", cases_arg: str | None = None,
          traces: Path | None = None) -> tuple[dict, list[dict]]:
    member = membership(split_data)
    # The same expansion `run.py` planned, or the report books cases the sweep never ran as
    # crashed and prints an F1 for a comparison nobody made (01-architecture.md section 9).
    cases = {c: ("test" if member[c] == "reserve" else member[c])
             for c in select_cases(split_data, split, cases_arg, include_reserve,
                                   split_file=SPLIT_FILE)}
    trace_root = Path(traces) if traces is not None else _traces_root(runs)
    rows, prompt_shas, modes, facts, blind = _collect(runs, cases, arms, seeds, trace_root)
    _check_traces(blind, trace_root)
    _check_prompt_sha(prompt_shas)
    brain = _check_brains(facts)
    brain_model = _check_brain_models(facts)
    _check_windows(recorded_windows(list(cases), arms, seeds, facts, brain, CACHE))
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
        # On the API brain the pinned request model is the model. On a local brain the CLI
        # chose, and the only place that choice is recorded is `record.json`'s provenance
        # (ADR 0008 item 5); asserting the pin there would name a model that never answered.
        "model": (brain_model if brain != API_BRAIN
                  else os.environ.get("ART30_MODEL", "claude-opus-5")),
        # ADR 0008 item 4: which engine produced these runs, and what the cost column means
        # (`measured`, `cli_estimate` at list prices, or `unpriced` — tokens and "n/a").
        "brain": brain,
        "brain_model": brain_model,
        "cost_source": cost_source(rows, brain),
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
    parser.add_argument("--traces", default=None,
                        help="trace root; default `traces/` for the scored tree and"
                             " <runs>/traces for any other, mirroring the sweep (section 9)")
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
                           args.split, args.cases,
                           Path(args.traces) if args.traces else None)
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
