"""What one results tree holds, read off disk (05-eval-harness.md sections 6 and 9).

Split out of `report.py` so neither file passes AGENTS.md's ~300 lines. This is the reading
half — one run's trace, the record it delivered and the metrics it was scored at, turned into
the rows and facts `report.py` refuses on and `stats.py` aggregates. Nothing here decides
where the traces are: the root is `report.py`'s, computed by its `_traces_root` and passed in,
for the same reason every other path a sandboxed report redirects stays a constant there.

Two lines of one run can disagree about that run. `run_start` is written before the CLI has
named its model, so `brain_model` is the configured value (null when the CLI chose) and
`cost_source` is a guess `pricing.priced(None)` answers optimistically; `record.json`'s
provenance carries the verdict the run settled on. `settle` is where the end state wins.
"""

from __future__ import annotations

import json
from pathlib import Path

API_BRAIN = "api"
MEASURED = "measured"          # the API brain: the cost the request was billed at
CLI_ESTIMATE = "cli_estimate"  # a local CLI's own token counts, priced at API list prices


def zero(case: str, arm: str, seed: int, split: str, stop: str) -> dict:
    """A planned run with no per-run metrics: f1 0.0, counted, never dropped (section 4.4)."""
    return {"case": case, "arm": arm, "seed": seed, "split": split, "f1": 0.0, "precision": 0.0,
            "recall": 0.0, "false_safe": 0, "unmatched_reaching_claims": 0, "pass": False,
            "unverified": 0, "invalid_verdict_for_kind": [], "draft": None,
            "citation_check": {"checked": 0, "bad": 0},
            "run": {"stop_condition": stop, "steps": 0, "tool_calls": 0, "cost_usd": 0.0}}


def trace_facts(arm: str, case: str, seed: int, traces: Path) -> dict:
    """One trace: the arm-equality fields, the stop condition, the brain that ran it and, for
    a local brain, the tokens it spent (ADR 0008 items 3 and 4). No `run_end` line is
    `crashed` (01 section 9); `brain` and `cost_source` ride in `run_start.config`, where
    `art30/brains/driver.py` puts them, and a trace with neither is the API brain.

    `cache_read` and `cache_write` are kept apart as well as summed: a cache read is 0.1x
    input and a one-hour cache write is 2x it, so one folded "cached" number cannot be
    multiplied back against the price table (ADR 0008 item 3).
    """
    path = traces / arm / f"{case}-s{seed}.jsonl"
    facts = {"prompt_sha": None, "mode": None, "stop": "crashed", "brain": API_BRAIN,
             "cost_source": None, "brain_model": None, "started": None, "tokens": None,
             "trace": False}
    if not path.is_file():
        return facts
    facts["trace"] = True
    tokens = {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}
    for line in path.read_text(encoding="utf-8", errors="replace").split("\n"):
        try:
            obj = json.loads(line) if line.strip() else None
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        if obj.get("type") == "run_start" and facts["prompt_sha"] is None:
            config = obj.get("config") or {}
            facts.update(prompt_sha=obj.get("prompt_sha"), mode=obj.get("mode"),
                         brain=str(config.get("brain") or API_BRAIN), started=obj.get("ts"),
                         cost_source=str(config.get("cost_source") or "") or None,
                         brain_model=config.get("brain_model") or None)
        elif obj.get("type") == "step":
            usage = obj.get("usage") if isinstance(obj.get("usage"), dict) else {}
            for key in tokens:
                value = usage.get(key)
                tokens[key] += value if isinstance(value, int) and not isinstance(value, bool) else 0
        elif obj.get("type") == "run_end":
            facts["stop"] = str(obj.get("stop_condition") or "crashed")
    facts["tokens"] = {**tokens, "cached": tokens["cache_read"] + tokens["cache_write"]}
    return facts


def provenance(path: Path) -> dict:
    """`provenance` off a run's delivered `record.json`, or an empty mapping."""
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    block = record.get("provenance") if isinstance(record, dict) else None
    return block if isinstance(block, dict) else {}


def settle(fact: dict, prov: dict) -> dict:
    """The run's own end state wins over what `run_start` guessed (ADR 0008 item 3).

    `run_start.config.cost_source` is decided before the CLI has named its model, and
    `pricing.priced(None)` is optimistic there by construction, so a `claude` run whose
    default model has no price entry starts out saying `cli_estimate` and prices every
    step at 0.0. The verdict is settled afterwards by `driver._cost_source()` and written
    to `record.json`; reading only the first line is what turned an unpriceable run into
    "$0.00" in the cost row instead of "n/a". `brain_model` is the same story: the
    configured value is null when the CLI chose, and only the record names what answered.
    """
    fact["brain"] = str(prov.get("brain") or fact["brain"] or API_BRAIN)
    fact["brain_model"] = prov.get("brain_model") or fact["brain_model"]
    source = str(prov.get("cost_source") or fact["cost_source"] or "")
    if fact["brain"] == API_BRAIN:
        fact["cost_source"], fact["tokens"] = MEASURED, None
    else:
        fact["cost_source"] = source or CLI_ESTIMATE
    return fact


def collect(runs: Path, cases: dict[str, str], arms: list[str], seeds: list[int],
             traces: Path) -> tuple[list[dict], dict, set, dict, list[str]]:
    """The rows, the two arm-equality sets, the facts and the scored runs that had no trace."""
    rows: list[dict] = []
    prompt_shas: dict[str, set[str]] = {arm: set() for arm in arms}
    modes: set[str] = set()
    facts: dict[tuple[str, str, int], dict] = {}
    blind: list[str] = []
    for case, split in cases.items():
        for seed in seeds:
            for arm in arms:
                slot = runs / arm / case / f"s{seed}"
                fact = settle(trace_facts(arm, case, seed, traces),
                               provenance(slot / "record.json"))
                facts[(arm, case, seed)] = fact
                if fact["prompt_sha"]:
                    prompt_shas[arm].add(str(fact["prompt_sha"]))
                if fact["mode"]:
                    modes.add(str(fact["mode"]))
                path = slot / "metrics.json"
                row = None
                if path.is_file():
                    if not fact["trace"]:
                        blind.append(f"{arm}/{case}-s{seed}")
                    try:
                        row = json.loads(path.read_text(encoding="utf-8"))
                    except json.JSONDecodeError:
                        row = None
                if not isinstance(row, dict):
                    row = zero(case, arm, seed, split, str(fact["stop"]))
                row["case"], row["arm"], row["seed"], row["split"] = case, arm, seed, split
                row["brain"], row["cost_source"] = fact["brain"], fact["cost_source"]
                row["brain_model"], row["tokens"] = fact["brain_model"], fact["tokens"]
                rows.append(row)
    return rows, prompt_shas, modes, facts, blind
