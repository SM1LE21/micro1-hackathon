"""The Markdown tables, the changelog row and the terminal summary (05-eval-harness.md 7.1, 7.2, 8).

Split out of `report.py` so neither file passes AGENTS.md's ~300 lines. Nothing here reads the
results tree: every function takes a finished `metrics.json` object (and, for the regressions row
and the changelog row, a previous one) and returns text. Section 7.2's rows are one format string
each, applied to both arms' aggregate blocks, so a row cannot say one thing for one arm and
another for the other.
"""

from __future__ import annotations

from pathlib import Path

from evals.harness.stats import RNG_SEED, bootstrap, case_f1, case_pass

NO_PREV = "n/a (no previous metrics.json)"
# Section 7.1's cost row, named for what the number is (ADR 0008 item 3). The API brain's
# figure is the billed arithmetic; a local brain's is its own token counts priced at API list
# prices, which is an estimate and says so; a model with no price entry has no dollar figure
# at all and prints tokens and "n/a" rather than a zero that reads as free.
COST_LABEL = {"measured": "Cost per task (measured)",
              "cli_estimate": "Cost per task (estimate at list prices)",
              "unpriced": "Cost per task (unpriced model)"}
UNPRICED = "unpriced"
# Four numbers, not three: a cache read prices at 0.1x input and `art30/brains/pricing.py`
# charges a one-hour cache write at 2x input, so a single folded "cached" column cannot be
# multiplied back against the price table and the row would promise a check it cannot support.
TOKENS_ROW = ("Tokens per run (input · output · cache read · cache write)",
              "{tokens_input_mean:,.0f} · {tokens_output_mean:,.0f} · "
              "{tokens_cache_read_mean:,.0f} · {tokens_cache_write_mean:,.0f}")

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
    "tool_calls_mean", "success", "failure", "tokens_input_mean", "tokens_output_mean",
    "tokens_cached_mean", "tokens_cache_read_mean", "tokens_cache_write_mean")}


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
                _cost_row(metrics, base, adv), "",
                f"Spread of the eval (std over cases): baseline {base.get('f1_std_cases', 0.0):.2f}, "
                f"advanced {adv.get('f1_std_cases', 0.0):.2f}. The ± above is the standard deviation "
                "over seeds, never over cases.", ""]
        out += _secondary(base, adv, metrics, split, prev)
    return "\n".join(out) + "\n"


def _cost_row(metrics: dict, base: dict, adv: dict) -> str:
    """Section 7.1's third row, labelled by where its number came from (ADR 0008 item 3)."""
    source = str(metrics.get("cost_source") or "measured")
    label = COST_LABEL.get(source, COST_LABEL["measured"])
    if source == UNPRICED:
        return f"| {label} | n/a | n/a | n/a |"
    left, right = base.get("cost_usd_mean", 0.0), adv.get("cost_usd_mean", 0.0)
    return f"| {label} | ${left:.2f} | ${right:.2f} | {_signed_usd(right - left)} |"


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
    old, new = case_pass(prev, arm, split), case_pass(metrics, arm, split)
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
    if "tokens_input_mean" in adv or "tokens_input_mean" in base:
        # A local brain reports tokens beside the estimate they were priced from, so the
        # cost row can be checked against the price table (ADR 0008 item 3).
        label, template = TOKENS_ROW
        rows.insert(len(rows) - 2, (label, template.format(**{**_DEFAULTS, **base}),
                                    template.format(**{**_DEFAULTS, **adv})))
    if str(metrics.get("cost_source") or "") == UNPRICED:
        rows = [(name, "n/a", "n/a") if name == "Cost per run" else (name, left, right)
                for name, left, right in rows]
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


def diff_row(old: dict, new: dict, stage: str, arm: str = "advanced", split: str = "dev") -> str:
    """One Markdown row in CHANGELOG_EVAL.md's four columns; two columns are typed by a human."""
    old_f1, new_f1 = case_f1(old, arm, split), case_f1(new, arm, split)
    cases = sorted(set(old_f1) & set(new_f1))
    boot = bootstrap([new_f1[c] for c in cases], [old_f1[c] for c in cases])
    old_block = (old.get("arms") or {}).get(arm, {}).get(split, {})
    new_block = (new.get("arms") or {}).get(arm, {}).get(split, {})
    old_pass, new_pass = case_pass(old, arm, split), case_pass(new, arm, split)
    regressions = sorted(c for c in cases if old_pass.get(c) and not new_pass.get(c))
    evidence = (
        f"{split} F1 {old_block.get('f1_mean', 0.0):.2f} → {new_block.get('f1_mean', 0.0):.2f} "
        f"(paired Δ {boot['delta_mean']:+.2f}, bootstrap 95% CI [{boot['ci95'][0]:+.2f}, {boot['ci95'][1]:+.2f}]); "
        f"false safe {old_block.get('false_safe_total', 0)} → {new_block.get('false_safe_total', 0)}; "
        f"cost/run ${old_block.get('cost_usd_mean', 0.0):.2f} → ${new_block.get('cost_usd_mean', 0.0):.2f}; "
        f"regressions {len(regressions)}" + (f" ({', '.join(regressions)})" if regressions else ""))
    return (f"| {stage} | (type: what you tried and why) | {evidence} "
            "| (type: decision / learning, after reading one trace) |")


# --- the terminal summary -----------------------------------------------------------------------


def print_summary(metrics: dict, out: Path) -> None:
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
