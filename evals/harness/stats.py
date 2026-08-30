"""The aggregates, the two statistics and human time (05-eval-harness.md sections 6, 7.3 and 9).

Split out of `report.py` so neither file passes AGENTS.md's ~300 lines. Recomputes nothing from a
record: every number is an aggregate of the per-run `metrics.json` the runner already wrote. Both
statistics are deterministic — an exact McNemar over `math.comb`, and a paired bootstrap whose rng
seed is committed — so two machines reading the same tree print the same interval. `human_time` and
`recorded_windows` are the two readers of a file here, and every directory they read is passed in
by `report.py`, so a sandboxed report stays sandboxed.
"""

from __future__ import annotations

import json
import math
import random
import statistics
from pathlib import Path

import yaml

from evals.harness.plan import ARMS

API_BRAIN = "api"
MEASURED = "measured"          # the API brain: the cost the request was billed at
CLI_ESTIMATE = "cli_estimate"  # a local CLI's own token counts, priced at API list prices
UNPRICED = "unpriced"          # a model with no price entry: tokens only, never a dollar figure
RNG_SEED = 20260830  # committed, controls the resampling only; the model takes no seed (ADR 0003)
RESAMPLES = 10000
PROTOCOL = "evals/CASES.md#labelling-protocol"
NO_TIMING = "n/a (no live sweep recorded)"
NO_GATE = "n/a (no gate-timing pass recorded)"


def by_case(rows: list[dict], key: str) -> dict[str, list[float]]:
    out: dict[str, list[float]] = {}
    for row in rows:
        out.setdefault(row["case"], []).append(float(row[key]))
    return out


def majority(rows: list[dict]) -> dict[str, bool]:
    """Per case, the outcome is the majority of its seeds (section 7.3)."""
    passes: dict[str, list[bool]] = {}
    for row in rows:
        passes.setdefault(row["case"], []).append(bool(row["pass"]))
    return {case: sum(values) * 2 > len(values) for case, values in passes.items()}


def mean(values: list[float]) -> float:
    return round(statistics.fmean(values), 6) if values else 0.0


def aggregate(rows: list[dict], n_cases: int) -> dict:
    if not rows:
        return {"n_cases": n_cases, "n_runs": 0, "success": 0, "failure": 0}
    per_case_f1 = by_case(rows, "f1")
    success = [r for r in rows if r["run"].get("stop_condition") == "accepted"]
    outcomes = majority(rows)
    passes: dict[str, list[bool]] = {}
    for row in rows:
        passes.setdefault(row["case"], []).append(bool(row["pass"]))
    return {
        "n_cases": n_cases, "n_runs": len(rows), "success": len(success),
        "failure": len(rows) - len(success),
        "f1_mean": mean([r["f1"] for r in rows]),
        "f1_std_seeds": round(statistics.fmean([statistics.pstdev(v) for v in per_case_f1.values()]), 6),
        "f1_std_cases": round(statistics.pstdev([statistics.fmean(v) for v in per_case_f1.values()]), 6),
        "f1_mean_success_only": mean([r["f1"] for r in success]),
        "precision_mean": mean([r["precision"] for r in rows]),
        "recall_mean": mean([r["recall"] for r in rows]),
        "false_safe_total": sum(int(r["false_safe"]) for r in rows),
        "false_safe_cases": sorted({r["case"] for r in rows if r["false_safe"]}),
        "unmatched_reaching_total": sum(int(r["unmatched_reaching_claims"]) for r in rows),
        "false_safe_in_draft_total": sum(int((r.get("draft") or {}).get("false_safe_in_draft") or 0)
                                         for r in rows),
        "pass_runs": sum(1 for r in rows if r["pass"]),
        "pass_cases_majority": sum(1 for v in outcomes.values() if v),
        "pass3_cases": sum(1 for v in passes.values() if all(v)),
        "unverified_mean": mean([float(r["unverified"]) for r in rows]),
        "invalid_verdict_for_kind_total": sum(len(r["invalid_verdict_for_kind"] or []) for r in rows),
        "citation_bad_total": sum(int((r["citation_check"] or {}).get("bad") or 0) for r in rows),
        "cost_usd_mean": mean([float(r["run"].get("cost_usd") or 0.0) for r in rows]),
        "cost_usd_total": round(sum(float(r["run"].get("cost_usd") or 0.0) for r in rows), 6),
        "turns_mean": mean([float(r["run"].get("steps") or 0) for r in rows]),
        "tool_calls_mean": mean([float(r["run"].get("tool_calls") or 0) for r in rows]),
        **engine(rows),
    }


def engine(rows: list[dict]) -> dict:
    """Which brain and model produced these runs and what their cost column means (ADR 0008).

    A local brain adds the token means its estimate was computed from, so a reader can check
    the arithmetic against the price table without opening a trace. Cache reads and cache
    writes are separate means as well as a summed `cached`: a read is 0.1x input and a
    one-hour write is 2x it, so the folded number alone cannot reproduce the estimate.
    `brain_model` is the model that actually answered, off each run's record; on a local
    brain the configured model is usually null because the CLI chose.
    """
    named = {str(r.get("brain") or API_BRAIN) for r in rows} - {API_BRAIN}
    brain = sorted(named)[0] if named else API_BRAIN
    models = sorted({str(r["brain_model"]) for r in rows if r.get("brain_model")})
    block = {"brain": brain, "brain_model": models[0] if models else None,
             "cost_source": cost_source(rows, brain)}
    if brain != API_BRAIN:
        for key in ("input", "output", "cached", "cache_read", "cache_write"):
            block[f"tokens_{key}_mean"] = mean(
                [float((r.get("tokens") or {}).get(key) or 0) for r in rows])
    return block


def recorded_windows(cases: list[str], arms: list[str], seeds: list[int],
                     facts: dict, brain: str, cache: Path) -> dict[str, tuple[str, str]]:
    """When each arm was run: `recorded_at` off the response cache for the API brain, and
    `run_start.ts` for a local brain, which records no response (ADR 0008 item 4). The
    question 01 section 4.2 asks is the same either way — do the two arms' windows overlap,
    or does any drift between them sit on one arm alone."""
    spans: dict[str, list[str]] = {}
    if brain != API_BRAIN:
        for (arm, case, _seed), fact in facts.items():
            if arm in arms and case in cases and isinstance(fact.get("started"), str):
                spans.setdefault(arm, []).append(fact["started"])
        return {arm: (min(v), max(v)) for arm, v in spans.items() if v}
    for arm in arms:
        for case in cases:
            for seed in seeds:
                for entry in sorted((cache / case / arm / f"s{seed}").glob("*.json")):
                    try:
                        stamp = json.loads(entry.read_text(encoding="utf-8")).get("recorded_at")
                    except (OSError, json.JSONDecodeError):
                        continue
                    if isinstance(stamp, str):
                        spans.setdefault(arm, []).append(stamp)
    return {arm: (min(values), max(values)) for arm, values in spans.items() if values}


def cost_source(rows: list[dict], brain: str) -> str:
    """The weakest source among the runs: one unpriced model makes the column unpriceable."""
    if brain == API_BRAIN:
        return MEASURED
    sources = {str(r.get("cost_source") or CLI_ESTIMATE) for r in rows if r.get("cost_source")}
    return UNPRICED if UNPRICED in sources else CLI_ESTIMATE


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


def comparison(rows: list[dict], cases: list[str], seeds: int) -> dict:
    by_arm = {arm: [r for r in rows if r["arm"] == arm] for arm in ARMS}
    if not all(by_arm.values()):
        return {}
    outcomes = {arm: majority(by_arm[arm]) for arm in ARMS}
    means = {arm: by_case(by_arm[arm], "f1") for arm in ARMS}
    paired = [c for c in cases if c in means["advanced"] and c in means["baseline"]]
    return {"mcnemar": mcnemar(outcomes["advanced"], outcomes["baseline"], seeds=seeds),
            "f1_bootstrap": bootstrap([statistics.fmean(means["advanced"][c]) for c in paired],
                                      [statistics.fmean(means["baseline"][c]) for c in paired])}


# --- the per-case rows the tables and the changelog row read (section 8) -----------------------


def case_f1(metrics: dict, arm: str, split: str) -> dict[str, float]:
    rows = [r for r in metrics.get("per_case") or [] if r["arm"] == arm
            and r["case"] in (metrics.get("cases") or {}).get(split, [])]
    out: dict[str, list[float]] = {}
    for row in rows:
        out.setdefault(row["case"], []).append(float(row["f1"]))
    return {case: statistics.fmean(values) for case, values in out.items()}


def case_pass(metrics: dict, arm: str, split: str) -> dict[str, bool]:
    rows = [r for r in metrics.get("per_case") or [] if r["arm"] == arm
            and r["case"] in (metrics.get("cases") or {}).get(split, [])]
    out: dict[str, list[bool]] = {}
    for row in rows:
        out.setdefault(row["case"], []).append(bool(row["pass"]))
    return {case: sum(v) * 2 > len(v) for case, v in out.items()}


# --- human time (section 9) --------------------------------------------------------------------


def _yaml(path: Path) -> dict | None:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return None
    return value if isinstance(value, dict) else None


def human_time(cases: list[str], timing: dict | None, manifests: Path,
               results: Path) -> dict:
    minutes: dict[str, float] = {}
    sources: dict[str, str] = {}
    for case in cases:
        sidecar = _yaml(manifests / f"{case}.labelling.yaml") or {}
        manifest = _yaml(manifests / f"{case}.yaml") or {}
        value = sidecar.get("labelling_minutes")
        source = "sidecar"
        if value is None:
            value, source = manifest.get("labelling_minutes"), "manifest"
        if value is not None:
            minutes[case], sources[case] = float(value), source
    manual = {"per_case": dict(sorted(minutes.items())),
              "mean": mean(list(minutes.values())) if minutes else None,
              "n": len(minutes), "protocol": PROTOCOL, "sources": dict(sorted(sources.items()))}
    gate_file = _yaml(results / "gate-timing.yaml")
    if gate_file and gate_file.get("cases"):
        per_case = {str(e["case"]): round(float(e.get("wait_s") or 0.0) / 60.0, 6)
                    for e in gate_file["cases"] if isinstance(e, dict) and e.get("case")}
        gate: object = {"per_case": dict(sorted(per_case.items())),
                        "mean": mean(list(per_case.values())), "n": len(per_case),
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
