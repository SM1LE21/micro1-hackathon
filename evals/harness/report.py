"""results/runs into results/metrics.json and the Markdown tables (05-eval-harness.md sections 6 to 8).

Recomputes nothing: every number here is an aggregate of the per-run `metrics.json` the runner
already wrote, and `n` comes from the run plan rather than the results tree, so a planned run whose
process died is counted as a `crashed` failure instead of disappearing (01-architecture.md section 9).

Two refusals run before anything is written: the arms must carry the same `prompt_sha`, and their
recording windows must overlap (contract, Trace contract; 01-architecture.md section 4.2).
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import os
import random
import statistics
import sys
from pathlib import Path

import yaml

from evals.harness.run import ARMS, REPO_ROOT, Abort, git_sha7, membership, select_cases

RESULTS = REPO_ROOT / "results"
TRACES = REPO_ROOT / "traces"
CACHE = REPO_ROOT / "evals" / "cache"
MANIFESTS = REPO_ROOT / "evals" / "fixtures" / "manifests"
SPLIT_FILE = REPO_ROOT / "evals" / "split.yaml"

RNG_SEED = 20260830  # committed, controls the resampling only; the model takes no seed (ADR 0003)
RESAMPLES = 10000
PROTOCOL = "evals/CASES.md#labelling-protocol"
NO_TIMING = "n/a (no live sweep recorded)"
NO_GATE = "n/a (no gate-timing pass recorded)"
NO_PREV = "n/a (no previous metrics.json)"


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


# --- aggregation ------------------------------------------------------------------------------


def _by_case(rows: list[dict], key: str) -> dict[str, list[float]]:
    out: dict[str, list[float]] = {}
    for row in rows:
        out.setdefault(row["case"], []).append(float(row[key]))
    return out


def _majority(rows: list[dict]) -> dict[str, bool]:
    """Per case, the outcome is the majority of its seeds (section 7.3)."""
    passes: dict[str, list[bool]] = {}
    for row in rows:
        passes.setdefault(row["case"], []).append(bool(row["pass"]))
    return {case: sum(values) * 2 > len(values) for case, values in passes.items()}


def _mean(values: list[float]) -> float:
    return round(statistics.fmean(values), 6) if values else 0.0


def _aggregate(rows: list[dict], n_cases: int) -> dict:
    if not rows:
        return {"n_cases": n_cases, "n_runs": 0, "success": 0, "failure": 0}
    per_case_f1 = _by_case(rows, "f1")
    success = [r for r in rows if r["run"].get("stop_condition") == "accepted"]
    majority = _majority(rows)
    passes: dict[str, list[bool]] = {}
    for row in rows:
        passes.setdefault(row["case"], []).append(bool(row["pass"]))
    return {
        "n_cases": n_cases, "n_runs": len(rows), "success": len(success),
        "failure": len(rows) - len(success),
        "f1_mean": _mean([r["f1"] for r in rows]),
        "f1_std_seeds": round(statistics.fmean([statistics.pstdev(v) for v in per_case_f1.values()]), 6),
        "f1_std_cases": round(statistics.pstdev([statistics.fmean(v) for v in per_case_f1.values()]), 6),
        "f1_mean_success_only": _mean([r["f1"] for r in success]),
        "precision_mean": _mean([r["precision"] for r in rows]),
        "recall_mean": _mean([r["recall"] for r in rows]),
        "false_safe_total": sum(int(r["false_safe"]) for r in rows),
        "false_safe_cases": sorted({r["case"] for r in rows if r["false_safe"]}),
        "unmatched_reaching_total": sum(int(r["unmatched_reaching_claims"]) for r in rows),
        "false_safe_in_draft_total": sum(int((r.get("draft") or {}).get("false_safe_in_draft") or 0)
                                         for r in rows),
        "pass_runs": sum(1 for r in rows if r["pass"]),
        "pass_cases_majority": sum(1 for v in majority.values() if v),
        "pass3_cases": sum(1 for v in passes.values() if all(v)),
        "unverified_mean": _mean([float(r["unverified"]) for r in rows]),
        "invalid_verdict_for_kind_total": sum(len(r["invalid_verdict_for_kind"] or []) for r in rows),
        "citation_bad_total": sum(int((r["citation_check"] or {}).get("bad") or 0) for r in rows),
        "cost_usd_mean": _mean([float(r["run"].get("cost_usd") or 0.0) for r in rows]),
        "cost_usd_total": round(sum(float(r["run"].get("cost_usd") or 0.0) for r in rows), 6),
        "turns_mean": _mean([float(r["run"].get("steps") or 0) for r in rows]),
        "tool_calls_mean": _mean([float(r["run"].get("tool_calls") or 0) for r in rows]),
    }


# Section 7.2's rows, one format string per row against an arm's aggregate block.
SECONDARY = (
    ("Pass (runs)", "{pass_runs}/{n_runs}"),
    ("Pass (cases, majority of seeds)", "{pass_cases_majority}/{n_cases}"),
    ("pass^3", "{pass3_cases}/{n_cases}"),
    ("False safe (matched)", "{false_safe_total}"),
    ("Reaching claims on stores not in the manifest", "{unmatched_reaching_total}"),
    ("False safe in a gate-rejected draft", "{false_safe_in_draft_total}"),
    ("Unverified per run", "{unverified_mean:.2f}"),
    ("Invalid verdict for kind", "{invalid_verdict_for_kind_total}"),
    ("Bad citations", "{citation_bad_total}"),
    ("Cost per run", "${cost_usd_mean:.2f}"),
    ("Turns · tool calls", "{turns_mean:.1f} · {tool_calls_mean:.1f}"),
    ("success + failure = n", "{success} + {failure} = {n_runs}"),
)
_DEFAULTS = {key: 0 for key in (
    "pass_runs", "n_runs", "pass_cases_majority", "n_cases", "pass3_cases", "false_safe_total",
    "unmatched_reaching_total", "false_safe_in_draft_total", "unverified_mean",
    "invalid_verdict_for_kind_total", "citation_bad_total", "cost_usd_mean", "turns_mean",
    "tool_calls_mean", "success", "failure")}


# --- the two statistics (section 7.3) ----------------------------------------------------------


def mcnemar(advanced: dict[str, bool], baseline: dict[str, bool], *, seeds: int) -> dict:
    """Exact McNemar on the binary pass row, majority of the seeds, `math.comb` only."""
    cases = sorted(set(advanced) & set(baseline))
    b = sum(1 for c in cases if advanced[c] and not baseline[c])
    c_ = sum(1 for c in cases if baseline[c] and not advanced[c])
    n = b + c_
    p = 1.0 if n == 0 else min(1.0, 2 * sum(math.comb(n, k) for k in range(0, min(b, c_) + 1)) / 2 ** n)
    return {"b": b, "c": c_, "n_discordant": n, "p_exact": round(p, 6),
            "outcome_rule": f"majority of {seeds} seeds",  # section 6 pins the number, not the word
            "note": "no discordant pairs" if n == 0 else ""}


def _percentile(values: list[float], q: float) -> float:
    """Nearest-rank on the sorted resamples: one rule, no interpolation, same on every machine."""
    index = min(len(values) - 1, max(0, int(q * len(values))))
    return values[index]


def bootstrap(advanced: list[float], baseline: list[float], *, resamples: int = RESAMPLES,
              seed: int = RNG_SEED) -> dict:
    """Paired bootstrap over cases: the same resampled case indices for both arms."""
    n = len(advanced)
    if n == 0 or n != len(baseline):
        return {"delta_mean": 0.0, "ci95": [0.0, 0.0], "resamples": resamples, "rng_seed": seed}
    rng = random.Random(seed)
    diffs: list[float] = []
    for _ in range(resamples):
        picks = [rng.randrange(n) for _ in range(n)]
        diffs.append(statistics.fmean([advanced[i] for i in picks])
                     - statistics.fmean([baseline[i] for i in picks]))
    diffs.sort()
    return {"delta_mean": round(statistics.fmean(advanced) - statistics.fmean(baseline), 6),
            "ci95": [round(_percentile(diffs, 0.025), 6), round(_percentile(diffs, 0.975), 6)],
            "resamples": resamples, "rng_seed": seed}


def _comparison(rows: list[dict], cases: list[str], seeds: int) -> dict:
    by_arm = {arm: [r for r in rows if r["arm"] == arm] for arm in ARMS}
    if not all(by_arm.values()):
        return {}
    majority = {arm: _majority(by_arm[arm]) for arm in ARMS}
    means = {arm: _by_case(by_arm[arm], "f1") for arm in ARMS}
    paired = [c for c in cases if c in means["advanced"] and c in means["baseline"]]
    return {"mcnemar": mcnemar(majority["advanced"], majority["baseline"], seeds=seeds),
            "f1_bootstrap": bootstrap([statistics.fmean(means["advanced"][c]) for c in paired],
                                      [statistics.fmean(means["baseline"][c]) for c in paired])}


# --- human time (section 9) --------------------------------------------------------------------


def _yaml(path: Path) -> dict | None:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return None
    return value if isinstance(value, dict) else None


def _human_time(cases: list[str], timing: dict | None) -> dict:
    minutes: dict[str, float] = {}
    sources: dict[str, str] = {}
    for case in cases:
        sidecar = _yaml(MANIFESTS / f"{case}.labelling.yaml") or {}
        manifest = _yaml(MANIFESTS / f"{case}.yaml") or {}
        value = sidecar.get("labelling_minutes")
        source = "sidecar"
        if value is None:
            value, source = manifest.get("labelling_minutes"), "manifest"
        if value is not None:
            minutes[case], sources[case] = float(value), source
    manual = {"per_case": dict(sorted(minutes.items())),
              "mean": _mean(list(minutes.values())) if minutes else None,
              "n": len(minutes), "protocol": PROTOCOL, "sources": dict(sorted(sources.items()))}
    gate_file = _yaml(RESULTS / "gate-timing.yaml")
    if gate_file and gate_file.get("cases"):
        per_case = {str(e["case"]): round(float(e.get("wait_s") or 0.0) / 60.0, 6)
                    for e in gate_file["cases"] if isinstance(e, dict) and e.get("case")}
        gate: object = {"per_case": dict(sorted(per_case.items())),
                        "mean": _mean(list(per_case.values())), "n": len(per_case),
                        "source": "results/gate-timing.yaml", "measured_by": "make gate-timing",
                        "approve_mode": "ask", "mode": str(gate_file.get("mode") or "replay")}
    else:
        gate = NO_GATE
    machine: object = NO_TIMING
    if timing:
        machine = {"source": "results/timing.json"}
        for arm in ARMS:
            wall = ((timing.get("per_arm") or {}).get(arm) or {}).get("wall_s_mean")
            machine[arm] = round(float(wall) / 60.0, 6) if wall is not None else None
    return {"manual_minutes": manual, "gate_minutes": gate, "machine_minutes": machine}


# --- the metrics file and the tables -----------------------------------------------------------


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
             for c in select_cases(split_data, split, cases_arg, include_reserve)}
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
        arm: {name: _aggregate([r for r in rows if r["arm"] == arm and r["split"] == name],
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
        "comparison": {name: _comparison([r for r in rows if r["split"] == name], by_split[name],
                                         len(seeds)) for name in ("dev", "test")},
        "human_time": _human_time(sorted(cases), timing),
        # `n` is the plan's cardinality, computed without the row list, so a `_collect` that ever
        # dropped or duplicated a planned run fails the report instead of passing it (section 6).
        "identity_check": {"n": n_plan, "success": success, "failure": len(rows) - success,
                           "ok": len(rows) == n_plan and success + (len(rows) - success) == n_plan},
    }
    return _round(metrics), rows


def _f1_cell(block: dict) -> str:
    return f"{block.get('f1_mean', 0.0):.2f} ± {block.get('f1_std_seeds', 0.0):.2f}"


def markdown(metrics: dict, prev: dict | None = None) -> str:
    """Section 7.1's three rows and section 7.2's secondary table, dev and test separately."""
    human = metrics["human_time"]
    manual = human["manual_minutes"]["mean"]
    gate = human["gate_minutes"]["mean"] if isinstance(human["gate_minutes"], dict) else None
    out = ["# Evaluation report", "",
           "Both arms run the same prompt and the same tools; the gate approves by construction in "
           "every scored run, so the measured difference is the verifier's (05-eval-harness.md 7.1).", ""]
    for split in ("dev", "test"):
        base = metrics["arms"].get("baseline", {}).get(split, {})
        adv = metrics["arms"].get("advanced", {}).get(split, {})
        delta = adv.get("f1_mean", 0.0) - base.get("f1_mean", 0.0)
        out += [f"## {split}", "",
                "| Metric | Simple baseline | Agent solution | Change |", "|---|---|---|---|",
                f"| Erasure-inventory F1 ({split}, mean of seeds) | {_f1_cell(base)} | {_f1_cell(adv)} | {delta:+.2f} |",
                f"| Human time per task | {_minutes(manual)} | {_minutes(gate)} | {_delta_minutes(manual, gate)} |",
                f"| Cost per task | ${base.get('cost_usd_mean', 0.0):.2f} | ${adv.get('cost_usd_mean', 0.0):.2f} |"
                f" {_signed_usd(adv.get('cost_usd_mean', 0.0) - base.get('cost_usd_mean', 0.0))} |", "",
                f"Spread of the eval (std over cases): baseline {base.get('f1_std_cases', 0.0):.2f}, "
                f"advanced {adv.get('f1_std_cases', 0.0):.2f}. The ± above is the standard deviation "
                "over seeds, never over cases.", ""]
        out += _secondary(base, adv, metrics, split, prev)
    return "\n".join(out) + "\n"


def _signed_usd(delta: float) -> str:
    return f"{'+' if delta >= 0 else '-'}${abs(delta):.2f}"


def _minutes(value) -> str:
    return f"{value:.1f} min" if isinstance(value, (int, float)) else "n/a"


def _delta_minutes(manual, gate) -> str:
    if isinstance(manual, (int, float)) and isinstance(gate, (int, float)):
        return f"{gate - manual:+.1f}"
    return "n/a"


def _regressions(prev: dict | None, metrics: dict, arm: str, split: str) -> str:
    """Section 7.2's row: cases passing in the previous metrics.json and failing in this one.

    Same majority rule and same paired case set as `diff_row`, which is the other reader of it.
    """
    if not prev:
        return NO_PREV
    old, new = _case_pass(prev, arm, split), _case_pass(metrics, arm, split)
    cases = sorted(c for c in old if c in new and old[c] and not new[c])
    return f"{len(cases)}" + (f" ({', '.join(cases)})" if cases else "")


def _secondary(base: dict, adv: dict, metrics: dict, split: str, prev: dict | None = None) -> list[str]:
    machine = metrics["human_time"]["machine_minutes"]
    comparison = metrics["comparison"].get(split) or {}
    test = comparison.get("mcnemar") or {}
    boot = comparison.get("f1_bootstrap") or {}
    rows = [(label, template.format(**{**_DEFAULTS, **base}), template.format(**{**_DEFAULTS, **adv}))
            for label, template in SECONDARY]
    rows.insert(3, ("Regressions",  # section 7.2 puts it under pass^3
                    _regressions(prev, metrics, "baseline", split),
                    _regressions(prev, metrics, "advanced", split)))
    rows.insert(len(rows) - 1, ("Machine minutes per run",  # section 7.2 keeps the identity last
                                _minutes(machine.get("baseline") if isinstance(machine, dict) else None),
                                _minutes(machine.get("advanced") if isinstance(machine, dict) else None)))
    body = ["| Row | Baseline | Advanced |", "|---|---|---|"]
    body += [f"| {name} | {left} | {right} |" for name, left, right in rows]
    note = ("With 5 test cases the smallest attainable two-sided p is 0.0625, so this test cannot "
            "reach p < 0.05 on the test split." if split == "test" else "")
    body += ["",
             f"McNemar (pass, majority of seeds): b={test.get('b', 0)} c={test.get('c', 0)} "
             f"p={test.get('p_exact', 1.0):.4f}"
             + (" — no discordant pairs" if test.get("n_discordant") == 0 else "") + f" {note}".rstrip(),
             f"Paired bootstrap on F1: delta {boot.get('delta_mean', 0.0):+.3f}, 95% CI "
             f"[{(boot.get('ci95') or [0.0, 0.0])[0]:+.3f}, {(boot.get('ci95') or [0.0, 0.0])[1]:+.3f}] "
             f"over {boot.get('resamples', 0)} resamples, rng seed {boot.get('rng_seed', RNG_SEED)}.",
             "\"False safe\" counts matched tuples only; the unmatched half is the row above it.", ""]
    return body


# --- the changelog row (section 8) --------------------------------------------------------------


def _case_f1(metrics: dict, arm: str, split: str) -> dict[str, float]:
    rows = [r for r in metrics.get("per_case") or [] if r["arm"] == arm
            and r["case"] in (metrics.get("cases") or {}).get(split, [])]
    out: dict[str, list[float]] = {}
    for row in rows:
        out.setdefault(row["case"], []).append(float(row["f1"]))
    return {case: statistics.fmean(values) for case, values in out.items()}


def _case_pass(metrics: dict, arm: str, split: str) -> dict[str, bool]:
    rows = [r for r in metrics.get("per_case") or [] if r["arm"] == arm
            and r["case"] in (metrics.get("cases") or {}).get(split, [])]
    out: dict[str, list[bool]] = {}
    for row in rows:
        out.setdefault(row["case"], []).append(bool(row["pass"]))
    return {case: sum(v) * 2 > len(v) for case, v in out.items()}


def diff_row(old: dict, new: dict, stage: str, arm: str = "advanced", split: str = "dev") -> str:
    """One Markdown row in CHANGELOG_EVAL.md's four columns; two columns are typed by a human."""
    old_f1, new_f1 = _case_f1(old, arm, split), _case_f1(new, arm, split)
    cases = sorted(set(old_f1) & set(new_f1))
    boot = bootstrap([new_f1[c] for c in cases], [old_f1[c] for c in cases])
    old_block = (old.get("arms") or {}).get(arm, {}).get(split, {})
    new_block = (new.get("arms") or {}).get(arm, {}).get(split, {})
    old_pass, new_pass = _case_pass(old, arm, split), _case_pass(new, arm, split)
    regressions = sorted(c for c in cases if old_pass.get(c) and not new_pass.get(c))
    evidence = (
        f"{split} F1 {old_block.get('f1_mean', 0.0):.2f} → {new_block.get('f1_mean', 0.0):.2f} "
        f"(paired Δ {boot['delta_mean']:+.2f}, bootstrap 95% CI [{boot['ci95'][0]:+.2f}, {boot['ci95'][1]:+.2f}]); "
        f"false safe {old_block.get('false_safe_total', 0)} → {new_block.get('false_safe_total', 0)}; "
        f"cost/run ${old_block.get('cost_usd_mean', 0.0):.2f} → ${new_block.get('cost_usd_mean', 0.0):.2f}; "
        f"regressions {len(regressions)}" + (f" ({', '.join(regressions)})" if regressions else ""))
    return (f"| {stage} | (type: what you tried and why) | {evidence} "
            "| (type: decision / learning, after reading one trace) |")


# --- entry point ----------------------------------------------------------------------------------


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
    _print_summary(metrics, out)
    return 0


def _print_summary(metrics: dict, out: Path) -> None:
    identity = metrics["identity_check"]
    print(f"{identity['n']} runs: {identity['success']} success, {identity['failure']} failure "
          f" (success + failure == n: {'ok' if identity['ok'] else 'FAILED'})")
    for split in ("dev", "test"):
        base = metrics["arms"].get("baseline", {}).get(split, {})
        adv = metrics["arms"].get("advanced", {}).get(split, {})
        print(f"{split:<5} baseline F1 {base.get('f1_mean', 0.0):.2f} ± {base.get('f1_std_seeds', 0.0):.2f}"
              f" | advanced F1 {adv.get('f1_mean', 0.0):.2f} ± {adv.get('f1_std_seeds', 0.0):.2f}"
              f" | false safe {base.get('false_safe_total', 0)} → {adv.get('false_safe_total', 0)}")
    parts = []
    for split in ("dev", "test"):
        test = (metrics["comparison"].get(split) or {}).get("mcnemar") or {}
        parts.append(f"{split} b={test.get('b', 0)} c={test.get('c', 0)} p={test.get('p_exact', 1.0):.4f}")
    print(f"McNemar (pass, majority of {len(metrics.get('seeds') or [])}): " + " | ".join(parts))
    print(f"wrote {out if not out.is_absolute() else out.name}")


if __name__ == "__main__":  # pragma: no cover - module entry point
    sys.exit(main())
