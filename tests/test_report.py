"""The report over a synthetic results tree (05-eval-harness.md sections 6 to 8).

Offline and model-free: the tree is per-run `metrics.json` files and traces written by hand, which
is exactly what `report.py` reads. No test writes into the repository's own `results/`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from evals.harness import report, run

SPLIT = {"dev": ["D1", "D2", "D3"], "test": ["T1", "T2"], "reserve": []}
SEEDS = [1, 2, 3]
PROMPT_SHA = "a" * 64


def _metrics(case: str, arm: str, seed: int, f1: float, passed: bool, *, false_safe: int = 0,
             stop: str = "accepted", cost: float = 0.4) -> dict:
    return {"case": case, "arm": arm, "seed": seed, "f1": f1, "precision": f1, "recall": f1,
            "false_safe": false_safe, "false_safe_tuples": [], "unmatched_reaching_claims": 0,
            "draft": None, "pass": passed, "unverified": 0, "invalid_verdict_for_kind": [],
            "citation_check": {"checked": 4, "bad": 0},
            "run": {"stop_condition": stop, "steps": 11, "tool_calls": 17, "submits": 1,
                    "verify_rounds": 0, "cost_usd": cost, "gate": None}}


def _write_run(root: Path, case: str, arm: str, seed: int, payload: dict, sha: str = PROMPT_SHA,
               brain: str = "api", started: str = "2026-08-30T10:00:00Z",
               tokens: tuple[int, ...] = (0, 0, 0, 0), runs: str = "results/runs",
               traces: str | None = None, prov: dict | None = None) -> None:
    out = root / runs / arm / case / f"s{seed}"
    out.mkdir(parents=True, exist_ok=True)
    (out / "metrics.json").write_text(json.dumps(payload), encoding="utf-8")
    if prov is not None:   # what art30/brains/driver.py writes into the delivered record
        (out / "record.json").write_text(json.dumps({"provenance": prov}), encoding="utf-8")
    trace = root / (traces or "traces") / arm / f"{case}-s{seed}.jsonl"
    trace.parent.mkdir(parents=True, exist_ok=True)
    config: dict = {"max_tokens": 32000, "tool_budget": 60, "submit_budget": 5, "overridden": []}
    if brain != "api":   # what art30/brains/driver.py writes on `run_start` (ADR 0008 item 1)
        config.update(brain=brain, brain_model=None, cost_source="cli_estimate")
    lines = [json.dumps({"type": "run_start", "arm": arm, "case": case, "seed": seed,
                         "mode": "replay", "prompt_sha": sha, "model": "claude-opus-5",
                         "config": config, "ts": started})]
    if any(tokens):
        cached = tuple(tokens) + (0, 0)
        lines.append(json.dumps({"type": "step", "step": 1, "request_hash": None,
                                 "usage": {"input": tokens[0], "output": tokens[1],
                                           "cache_read": cached[2], "cache_write": cached[3]}}))
    lines.append(json.dumps({"type": "run_end",
                             "stop_condition": payload["run"]["stop_condition"]}))
    trace.write_text("\n".join(lines) + "\n", encoding="utf-8")


@pytest.fixture()
def tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Advanced passes every dev and test case; baseline passes none and carries false safes."""
    monkeypatch.setattr(report, "TRACES", tmp_path / "traces")
    monkeypatch.setattr(report, "RESULTS", tmp_path / "results")
    monkeypatch.setattr(report, "CACHE", tmp_path / "cache")
    monkeypatch.setattr(report, "MANIFESTS", tmp_path / "manifests")
    monkeypatch.delenv("ART30_REPRODUCIBLE", raising=False)
    for case in SPLIT["dev"] + SPLIT["test"]:
        for seed in SEEDS:
            _write_run(tmp_path, case, "advanced", seed, _metrics(case, "advanced", seed, 0.9, True))
            _write_run(tmp_path, case, "baseline", seed,
                       _metrics(case, "baseline", seed, 0.6, False, false_safe=1, cost=0.3))
    return tmp_path


def _build(tree: Path, **kwargs) -> dict:
    """`traces` is passed rather than left to `_traces_root`: this tree is not the
    repository's own `results/runs`, so the default would be `<runs>/traces` (which is what
    `test_the_traces_root_follows_the_runs_tree` checks) and never the fixture's."""
    kwargs.setdefault("traces", tree / "traces")
    metrics, _ = report.build(tree / "results" / "runs", SPLIT, ["baseline", "advanced"], SEEDS,
                              **kwargs)
    return metrics


# --- the metrics.json shape (section 6) --------------------------------------------------------


def test_metrics_shape(tree: Path) -> None:
    metrics = _build(tree)
    assert metrics["schema"] == 1 and metrics["generated_at"] is None
    assert metrics["seeds"] == SEEDS
    assert metrics["cases"] == {"dev": SPLIT["dev"], "test": SPLIT["test"]}
    dev = metrics["arms"]["baseline"]["dev"]
    assert dev["n_cases"] == 3 and dev["n_runs"] == 9 and dev["success"] == 9 and dev["failure"] == 0
    assert dev["f1_mean"] == 0.6 and dev["f1_std_seeds"] == 0.0 and dev["f1_std_cases"] == 0.0
    assert dev["false_safe_total"] == 9 and dev["false_safe_cases"] == SPLIT["dev"]
    assert dev["pass_runs"] == 0 and dev["pass_cases_majority"] == 0 and dev["pass3_cases"] == 0
    advanced = metrics["arms"]["advanced"]["test"]
    assert advanced["pass_cases_majority"] == 2 and advanced["pass3_cases"] == 2
    assert advanced["cost_usd_mean"] == 0.4 and advanced["turns_mean"] == 11.0
    assert metrics["identity_check"] == {"n": 30, "success": 30, "failure": 0, "ok": True}
    assert metrics["git_sha"] is None  # section 10: never the sha of the commit that carries it
    assert metrics["per_case"] == sorted(metrics["per_case"], key=lambda r: (r["arm"], r["case"], r["seed"]))


def test_a_missing_run_is_counted_as_crashed_with_f1_zero(tree: Path) -> None:
    """01 section 9: `n` comes from the plan, so a run with no trace is a crashed failure."""
    (tree / "results" / "runs" / "advanced" / "D1" / "s1" / "metrics.json").unlink()
    (tree / "traces" / "advanced" / "D1-s1.jsonl").unlink()
    metrics = _build(tree)
    assert metrics["identity_check"] == {"n": 30, "success": 29, "failure": 1, "ok": True}
    assert metrics["arms"]["advanced"]["dev"]["failure"] == 1
    row = [r for r in metrics["per_case"] if r["arm"] == "advanced" and r["case"] == "D1" and r["seed"] == 1]
    assert row[0]["stop_condition"] == "crashed" and row[0]["f1"] == 0.0


def test_a_failed_run_still_counts_in_f1_mean(tree: Path) -> None:
    _write_run(tree, "D1", "advanced", 1,
               _metrics("D1", "advanced", 1, 0.0, False, stop="budget_exhausted"))
    metrics = _build(tree)
    dev = metrics["arms"]["advanced"]["dev"]
    assert dev["f1_mean"] == round((0.9 * 8) / 9, 6)
    assert dev["f1_mean_success_only"] == 0.9
    assert dev["success"] + dev["failure"] == dev["n_runs"]


# --- the two statistics (section 7.3) ------------------------------------------------------------


def test_mcnemar_on_a_known_two_by_two() -> None:
    advanced = {"D1": True, "D2": True, "D3": True}
    baseline = {"D1": False, "D2": False, "D3": False}
    result = report.mcnemar(advanced, baseline, seeds=3)
    assert (result["b"], result["c"], result["n_discordant"]) == (3, 0, 3)
    assert result["p_exact"] == 0.25  # 2 * comb(3, 0) / 2**3
    assert result["outcome_rule"] == "majority of 3 seeds"  # section 6 pins the number


def test_mcnemar_with_no_discordant_pairs_says_so() -> None:
    result = report.mcnemar({"D1": True}, {"D1": True}, seeds=3)
    assert result["p_exact"] == 1.0 and result["note"] == "no discordant pairs"


def test_mcnemar_reaches_its_dev_floor_with_nine_cases() -> None:
    cases = [f"D{i}" for i in range(9)]
    result = report.mcnemar({c: True for c in cases}, {c: False for c in cases}, seeds=3)
    assert result["p_exact"] == round(2 / 2 ** 9, 6)  # 0.003906, the dev floor of section 7.3


def test_bootstrap_is_reproducible_and_paired() -> None:
    advanced = [0.9, 0.8, 1.0, 0.7, 0.95]
    baseline = [0.6, 0.5, 0.7, 0.4, 0.65]
    first = report.bootstrap(advanced, baseline)
    assert first == report.bootstrap(advanced, baseline)
    assert first["rng_seed"] == 20260830 and first["resamples"] == 10000
    assert first["ci95"][0] <= first["delta_mean"] <= first["ci95"][1]
    assert report.bootstrap(advanced, baseline, seed=1) != first


def test_comparison_lands_in_metrics(tree: Path) -> None:
    metrics = _build(tree)
    assert metrics["comparison"]["dev"]["mcnemar"]["b"] == 3
    assert metrics["comparison"]["test"]["mcnemar"]["p_exact"] == 0.5  # 2 cases: 2 * 1 / 4
    assert metrics["comparison"]["dev"]["f1_bootstrap"]["delta_mean"] == round(0.9 - 0.6, 6)


# --- the refusals ---------------------------------------------------------------------------------


def test_prompt_sha_mismatch_exits_1(tree: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_run(tree, "D1", "baseline", 1, _metrics("D1", "baseline", 1, 0.6, False), sha="c" * 64)
    split_file = tree / "split.yaml"
    split_file.write_text(yaml.safe_dump(SPLIT), encoding="utf-8")
    monkeypatch.setattr(report, "SPLIT_FILE", split_file)
    code = report.main(["--runs", str(tree / "results" / "runs"),
                        "--traces", str(tree / "traces"),
                        "--out", str(tree / "results" / "metrics.json")])
    assert code == 1
    assert not (tree / "results" / "metrics.json").exists()


def test_disjoint_recording_windows_are_refused(tree: Path) -> None:
    for arm, day in (("baseline", "29"), ("advanced", "31")):
        slot = tree / "cache" / "D1" / arm / "s1"
        slot.mkdir(parents=True, exist_ok=True)
        (slot / "01.json").write_text(json.dumps({"recorded_at": f"2026-08-{day}T10:00:00Z"}),
                                      encoding="utf-8")
    with pytest.raises(report.Refuse):
        _build(tree)


def test_overlapping_windows_are_accepted(tree: Path) -> None:
    for arm in ("baseline", "advanced"):
        slot = tree / "cache" / "D1" / arm / "s1"
        slot.mkdir(parents=True, exist_ok=True)
        (slot / "01.json").write_text(json.dumps({"recorded_at": "2026-08-30T10:00:00Z"}),
                                      encoding="utf-8")
    assert _build(tree)["identity_check"]["ok"]


# --- human time and the tables ---------------------------------------------------------------------


def test_human_time_says_n_a_when_nothing_was_measured(tree: Path) -> None:
    human = _build(tree)["human_time"]
    assert human["gate_minutes"] == report.NO_GATE
    assert human["machine_minutes"] == report.NO_TIMING
    assert human["manual_minutes"]["n"] == 0 and human["manual_minutes"]["mean"] is None


def test_human_time_reads_the_sidecar_the_manifest_and_the_two_duration_files(tree: Path) -> None:
    (tree / "manifests").mkdir(exist_ok=True)
    (tree / "manifests" / "D1.labelling.yaml").write_text("labelling_minutes: 34\n", encoding="utf-8")
    (tree / "manifests" / "T1.yaml").write_text("case: T1\nlabelling_minutes: 62\n", encoding="utf-8")
    (tree / "results" / "gate-timing.yaml").write_text(
        "mode: replay\ncases:\n  - {case: D1, wait_s: 36.0}\n  - {case: T1, wait_s: 72.0}\n",
        encoding="utf-8")
    (tree / "results" / "timing.json").write_text(json.dumps(
        {"per_arm": {"baseline": {"wall_s_mean": 84.0}, "advanced": {"wall_s_mean": 96.0}}}),
        encoding="utf-8")
    human = _build(tree)["human_time"]
    assert human["manual_minutes"]["per_case"] == {"D1": 34.0, "T1": 62.0}
    assert human["manual_minutes"]["sources"] == {"D1": "sidecar", "T1": "manifest"}
    assert human["manual_minutes"]["mean"] == 48.0
    assert human["gate_minutes"]["mean"] == 0.9 and human["gate_minutes"]["approve_mode"] == "ask"
    assert human["machine_minutes"] == {"source": "results/timing.json", "baseline": 1.4, "advanced": 1.6}


def test_the_report_expands_the_plan_the_sweep_ran(tree: Path) -> None:
    """01 section 9: a dev-only sweep must not book the test cases as planned and crashed."""
    for case in SPLIT["test"]:
        for seed in SEEDS:
            for arm in ("baseline", "advanced"):
                (tree / "results" / "runs" / arm / case / f"s{seed}" / "metrics.json").unlink()
                (tree / "traces" / arm / f"{case}-s{seed}.jsonl").unlink()
    metrics = _build(tree, split="dev")
    assert metrics["identity_check"] == {"n": 18, "success": 18, "failure": 0, "ok": True}
    assert metrics["cases"] == {"dev": SPLIT["dev"], "test": []}
    assert metrics["arms"]["advanced"]["test"]["n_runs"] == 0


def test_an_explicit_case_list_is_expanded_like_run_pys(tree: Path) -> None:
    metrics = _build(tree, cases_arg="D1,T1")
    assert metrics["identity_check"]["n"] == 12
    assert metrics["cases"] == {"dev": ["D1"], "test": ["T1"]}


def test_regressions_is_a_row_of_the_secondary_table(tree: Path) -> None:
    old = _build(tree)
    for seed in SEEDS:
        _write_run(tree, "D3", "advanced", seed, _metrics("D3", "advanced", seed, 0.2, False))
    text = report.markdown(_build(tree), old)
    assert "| Regressions | 0 | 1 (D3) |" in text
    assert f"| Regressions | {report.NO_PREV} | {report.NO_PREV} |" in report.markdown(_build(tree))


def test_an_unknown_arm_is_an_argument_error(tree: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    split_file = tree / "split.yaml"
    split_file.write_text(yaml.safe_dump(SPLIT), encoding="utf-8")
    monkeypatch.setattr(report, "SPLIT_FILE", split_file)
    assert report.main(["--runs", str(tree / "results" / "runs"), "--traces",
                        str(tree / "traces"), "--arms", "baseline,advnaced"]) == 1


def test_a_third_arm_with_a_cache_slot_is_compared_pairwise() -> None:
    windows = {"baseline": ("2026-08-30T09:00:00Z", "2026-08-30T12:00:00Z"),
               "advanced": ("2026-08-30T10:00:00Z", "2026-08-30T13:00:00Z"),
               "probe": ("2026-08-31T10:00:00Z", "2026-08-31T13:00:00Z")}
    with pytest.raises(report.Refuse) as caught:
        report._check_windows(windows)
    assert "probe" in str(caught.value)


def test_markdown_carries_the_three_rows_and_the_secondary_table(tree: Path) -> None:
    text = report.markdown(_build(tree))
    assert "| Metric | Simple baseline | Agent solution | Change |" in text
    assert "Erasure-inventory F1 (dev, mean of seeds) | 0.60 ± 0.00 | 0.90 ± 0.00 | +0.30" in text
    assert "Human time per task" in text and "Cost per task" in text
    assert "pass^3" in text and "False safe (matched)" in text and "success + failure = n" in text
    assert "cannot reach p < 0.05 on the test split" in text


def test_main_writes_metrics_and_markdown(tree: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    split_file = tree / "split.yaml"
    split_file.write_text(yaml.safe_dump(SPLIT), encoding="utf-8")
    monkeypatch.setattr(report, "SPLIT_FILE", split_file)
    out = tree / "results" / "metrics.json"
    code = report.main(["--runs", str(tree / "results" / "runs"), "--out", str(out),
                        "--traces", str(tree / "traces"),
                        "--md", str(tree / "results" / "report.md")])
    assert code == 0
    assert json.loads(out.read_text(encoding="utf-8"))["identity_check"]["ok"] is True
    assert (tree / "results" / "report.md").is_file()


# --- the changelog row (section 8) --------------------------------------------------------------------


def test_diff_row_reports_the_delta_its_interval_and_the_regressions(tree: Path) -> None:
    old = _build(tree)
    for case in SPLIT["dev"]:
        for seed in SEEDS:
            _write_run(tree, case, "advanced", seed,
                       _metrics(case, "advanced", seed, 1.0 if case != "D3" else 0.2,
                                case != "D3", cost=0.5))
    new = _build(tree)
    row = report.diff_row(old, new, "verifier: sender check")
    assert row.startswith("| verifier: sender check |")
    assert "dev F1 0.90 → 0.73" in row
    assert "regressions 1 (D3)" in row
    assert "cost/run $0.40 → $0.50" in row
    assert "bootstrap 95% CI" in row


# --- the brain (ADR 0008 items 3 and 4) ------------------------------------------------------


def _local(tree: Path, brain: str = "claude", **kwargs) -> None:
    """Rewrite the whole tree as a local-brain sweep: same runs, traces from a CLI."""
    for case in SPLIT["dev"] + SPLIT["test"]:
        for seed in SEEDS:
            _write_run(tree, case, "advanced", seed, _metrics(case, "advanced", seed, 0.9, True),
                       brain=brain, tokens=(12000, 900, 4000, 2000), **kwargs)
            _write_run(tree, case, "baseline", seed,
                       _metrics(case, "baseline", seed, 0.6, False, false_safe=1, cost=0.3),
                       brain=brain, tokens=(8000, 500, 3000, 1500), **kwargs)


def test_the_api_brain_is_named_and_its_cost_is_measured(tree: Path) -> None:
    metrics = _build(tree)
    assert metrics["brain"] == "api" and metrics["cost_source"] == "measured"
    assert metrics["arms"]["advanced"]["dev"]["brain"] == "api"
    assert metrics["arms"]["advanced"]["dev"]["cost_source"] == "measured"
    assert "tokens_input_mean" not in metrics["arms"]["advanced"]["dev"]
    assert "| Cost per task (measured) | $0.30 | $0.40 | +$0.10 |" in report.markdown(metrics)


def test_a_local_brain_is_named_and_its_cost_is_an_estimate_with_tokens_beside_it(
    tree: Path,
) -> None:
    _local(tree)
    metrics = _build(tree)
    assert metrics["brain"] == "claude" and metrics["cost_source"] == "cli_estimate"
    block = metrics["arms"]["advanced"]["dev"]
    assert block["brain"] == "claude" and block["cost_source"] == "cli_estimate"
    assert (block["tokens_input_mean"], block["tokens_output_mean"],
            block["tokens_cached_mean"]) == (12000.0, 900.0, 6000.0)
    # A cache read prices at 0.1x input and a one-hour cache write at 2x it, so the two
    # halves are reported apart or the row cannot be checked against the price table.
    assert (block["tokens_cache_read_mean"], block["tokens_cache_write_mean"]) == (4000.0, 2000.0)
    text = report.markdown(metrics)
    assert "| Cost per task (estimate at list prices) | $0.30 | $0.40 | +$0.10 |" in text
    assert ("| Tokens per run (input · output · cache read · cache write) "
            "| 8,000 · 500 · 3,000 · 1,500 | 12,000 · 900 · 4,000 · 2,000 |") in text


def test_two_brains_in_one_results_tree_are_refused(tree: Path) -> None:
    """ADR 0008 item 4: measured dollars and a list-price estimate are not one column."""
    _write_run(tree, "D1", "advanced", 1, _metrics("D1", "advanced", 1, 0.9, True), brain="claude",
               tokens=(10, 10, 10, 10))
    with pytest.raises(report.Refuse) as caught:
        _build(tree)
    assert "more than one brain" in str(caught.value)


def test_a_local_brains_recording_window_comes_from_the_traces(tree: Path) -> None:
    """No response cache exists for a local brain, so `run_start.ts` is the window."""
    _local(tree)
    for seed in SEEDS:
        for case in SPLIT["dev"] + SPLIT["test"]:
            _write_run(tree, case, "baseline", seed,
                       _metrics(case, "baseline", seed, 0.6, False, false_safe=1, cost=0.3),
                       brain="claude", tokens=(8000, 500, 3000), started="2026-08-25T10:00:00Z")
    with pytest.raises(report.Refuse) as caught:
        _build(tree)
    assert "recording windows do not overlap" in str(caught.value)


# --- the traces root, the record's own verdict and the model that answered --------------------


def test_a_scored_run_with_no_trace_is_refused(tree: Path) -> None:
    """Every brain and cost fact hangs off the trace; silence relabels the tree `api`."""
    _local(tree)
    (tree / "traces" / "advanced" / "D1-s1.jsonl").unlink()

    with pytest.raises(report.Refuse) as caught:
        _build(tree)

    assert "scored runs with no trace" in str(caught.value)
    assert "advanced/D1-s1" in str(caught.value)


def test_the_traces_root_follows_the_runs_tree(tree: Path) -> None:
    """05 section 9: a sweep outside `results/runs` took its traces to `<out>/traces`.

    Reading the module constant instead is how the runbook's own API-check tree came back
    labelled `brain: api`, `cost_source: measured` — a subscription estimate rendered as
    billed dollars — with every trace-keyed refusal passing vacuously.
    """
    for case in SPLIT["dev"]:
        for seed in SEEDS:
            for arm, f1 in (("advanced", 0.9), ("baseline", 0.6)):
                _write_run(tree, case, arm, seed, _metrics(case, arm, seed, f1, f1 > 0.8),
                           brain="claude", tokens=(10, 10, 10, 10),
                           runs="results/.api-check", traces="results/.api-check/traces")
    runs = tree / "results" / ".api-check"

    metrics, _ = report.build(runs, SPLIT, ["baseline", "advanced"], SEEDS, split="dev")

    assert metrics["brain"] == "claude" and metrics["cost_source"] == "cli_estimate"


def test_the_report_and_the_sweep_agree_on_where_traces_are() -> None:
    """One rule, spelled twice: `run.trace_root` writes them, `_traces_root` reads them."""
    for out in ("results/runs", "results/.api-check", "/tmp/sweep"):
        assert report._traces_root(Path(out)) == run.trace_root(out)
    assert report._traces_root(report.REPO_ROOT / "results" / "runs") == report.TRACES


def test_the_traces_flag_overrides_the_root(tree: Path) -> None:
    _local(tree)
    moved = tree / "elsewhere"
    (tree / "traces").rename(moved)

    with pytest.raises(report.Refuse):
        _build(tree, traces=tree / "traces")

    assert report.build(tree / "results" / "runs", SPLIT, ["baseline", "advanced"], SEEDS,
                        traces=moved)[0]["brain"] == "claude"


def test_the_records_cost_source_wins_over_the_one_run_start_guessed(tree: Path) -> None:
    """ADR 0008 item 3: `run_start` is written before the CLI names its model, and
    `pricing.priced(None)` is optimistic there, so an unpriceable run starts out saying
    `cli_estimate` and prices every step at 0.0. `record.json` carries the verdict."""
    _local(tree, prov={"brain": "claude", "brain_model": "claude-sonnet-4-6",
                       "cost_source": "unpriced"})

    metrics = _build(tree)

    assert metrics["cost_source"] == "unpriced"
    text = report.markdown(metrics)
    assert "| Cost per task (unpriced model) | n/a | n/a | n/a |" in text
    assert "| Cost per run | n/a | n/a |" in text


def test_the_model_that_answered_is_the_records_and_not_the_pin(tree: Path) -> None:
    """`metrics.json` asserted the API brain's pinned model on a sweep the CLI chose for."""
    _local(tree, prov={"brain": "claude", "brain_model": "claude-sonnet-4-6",
                       "cost_source": "cli_estimate"})

    metrics = _build(tree)

    assert metrics["brain_model"] == "claude-sonnet-4-6"
    assert metrics["model"] == "claude-sonnet-4-6"
    assert metrics["arms"]["advanced"]["dev"]["brain_model"] == "claude-sonnet-4-6"


def test_two_brain_models_in_one_results_tree_are_refused(tree: Path) -> None:
    """The drift `prompt_sha` cannot see: the instruction text is a constant of the checkout."""
    _local(tree, prov={"brain": "claude", "brain_model": "claude-opus-5",
                       "cost_source": "cli_estimate"})
    for seed in SEEDS:
        _write_run(tree, "D1", "baseline", seed,
                   _metrics("D1", "baseline", seed, 0.6, False, false_safe=1, cost=0.3),
                   brain="claude", tokens=(8000, 500, 3000, 1500),
                   prov={"brain": "claude", "brain_model": "claude-sonnet-4-6",
                         "cost_source": "cli_estimate"})

    with pytest.raises(report.Refuse) as caught:
        _build(tree)

    assert "do not share one brain_model" in str(caught.value)
