"""`make verify-docs` over a synthetic metrics file and a synthetic README (tmp_path only).

Offline and model-free: the inputs are a hand-written `metrics.json` of the shape `report.py`
writes and a README carrying the markers. No test reads or writes the repository's own README.md,
`results/` or `traces/`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evals.harness import verify_docs
from evals.harness.tables import markdown

DEV = ["S01", "S02", "S03"]
TEST = ["S08", "S09"]


def _arm(f1: float, cost: float, false_safe: int = 0) -> dict:
    return {"n_cases": 2, "n_runs": 6, "success": 6, "failure": 0,
            "f1_mean": f1, "f1_std_seeds": 0.02, "f1_std_cases": 0.05,
            "f1_mean_success_only": f1, "precision_mean": f1, "recall_mean": f1,
            "false_safe_total": false_safe, "false_safe_cases": [],
            "unmatched_reaching_total": 0, "false_safe_in_draft_total": 0,
            "pass_runs": 4, "pass_cases_majority": 2, "pass3_cases": 1,
            "unverified_mean": 0.5, "invalid_verdict_for_kind_total": 0, "citation_bad_total": 0,
            "cost_usd_mean": cost, "cost_usd_total": cost * 6,
            "turns_mean": 11.0, "tool_calls_mean": 17.0}


def _comparison() -> dict:
    return {"mcnemar": {"b": 2, "c": 0, "n_discordant": 2, "p_exact": 0.5, "note": ""},
            "f1_bootstrap": {"delta_mean": 0.3, "ci95": [0.1, 0.5], "resamples": 10000,
                             "rng_seed": 20260830}}


def metrics_object() -> dict:
    return {
        "schema": 1, "generated_at": None, "git_sha": None, "model": "claude-opus-5",
        "mode": "replay", "seeds": [1, 2, 3], "cases": {"dev": DEV, "test": TEST},
        "arms": {"baseline": {"dev": _arm(0.55, 0.31, 4), "test": _arm(0.60, 0.30, 3)},
                 "advanced": {"dev": _arm(0.88, 0.52, 1), "test": _arm(0.90, 0.51, 0)}},
        "per_case": [],
        "comparison": {"dev": _comparison(), "test": _comparison()},
        "human_time": {"manual_minutes": {"mean": 42.0, "n": 5},
                       "gate_minutes": {"mean": 3.5, "n": 5},
                       "machine_minutes": {"baseline": 2.0, "advanced": 4.0}},
        "identity_check": {"n": 12, "success": 12, "failure": 0, "ok": True},
    }


@pytest.fixture()
def metrics_file(tmp_path: Path) -> Path:
    path = tmp_path / "metrics.json"
    path.write_text(json.dumps(metrics_object(), indent=2) + "\n", encoding="utf-8")
    return path


def _readme(tmp_path: Path, block: str, *, markers: bool = True) -> Path:
    path = tmp_path / "README.md"
    body = (f"{verify_docs.BEGIN}\n{block}\n{verify_docs.END}" if markers else block)
    path.write_text(f"# art30\n\nPreamble.\n\n## Results\n\n{body}\n\nProse after.\n",
                    encoding="utf-8")
    return path


def _run(metrics: Path, readme: Path, *extra: str) -> int:
    return verify_docs.main(["--metrics", str(metrics), "--readme", str(readme), *extra])


# --- what the block is -------------------------------------------------------------------------


def test_block_is_the_two_tables_report_generates() -> None:
    block = verify_docs.generate(metrics_object(), "test")
    tables = verify_docs.tables_for(markdown(metrics_object()), "test")
    assert block == verify_docs.normalise(tables[0] + "\n\n" + tables[1])
    assert block.count("| Metric | Simple baseline | Agent solution | Change |") == 1
    assert "| Row | Baseline | Advanced |" in block
    # Section 7.1's table is three rows plus its two header lines.
    assert len(tables[0].split("\n")) == 5


def test_dev_and_test_blocks_are_different() -> None:
    assert verify_docs.generate(metrics_object(), "dev") != verify_docs.generate(metrics_object(), "test")


def test_unknown_split_is_blocked() -> None:
    with pytest.raises(verify_docs.Blocked):
        verify_docs.generate(metrics_object(), "reserve")


# --- exit 0 ------------------------------------------------------------------------------------


def test_matching_readme_exits_zero(metrics_file: Path, tmp_path: Path, capsys) -> None:
    readme = _readme(tmp_path, verify_docs.generate(metrics_object(), "test"))
    assert _run(metrics_file, readme) == 0
    assert "verify-docs OK" in capsys.readouterr().out


def test_trailing_whitespace_and_blank_lines_are_ignored(metrics_file: Path, tmp_path: Path) -> None:
    block = verify_docs.generate(metrics_object(), "test")
    noisy = "\n\n" + "\n".join(line + "   " for line in block.split("\n")) + "\n\n"
    assert _run(metrics_file, _readme(tmp_path, noisy)) == 0


def test_dev_split_is_selectable(metrics_file: Path, tmp_path: Path) -> None:
    readme = _readme(tmp_path, verify_docs.generate(metrics_object(), "dev"))
    assert _run(metrics_file, readme, "--split", "dev") == 0
    assert _run(metrics_file, readme, "--split", "test") == 1


# --- exit 1 ------------------------------------------------------------------------------------


def test_stale_number_exits_one_with_a_unified_diff(metrics_file: Path, tmp_path: Path, capsys) -> None:
    stale = verify_docs.generate(metrics_object(), "test").replace("0.90", "0.99")
    readme = _readme(tmp_path, stale)
    before = readme.read_text(encoding="utf-8")
    assert _run(metrics_file, readme) == 1
    captured = capsys.readouterr()
    assert captured.out.startswith("---")
    assert "+++" in captured.out and "@@" in captured.out
    assert any(line.startswith("+") and "0.99" in line for line in captured.out.split("\n"))
    assert "differ" in captured.err
    assert readme.read_text(encoding="utf-8") == before  # the checker never edits the README


def test_a_missing_secondary_table_exits_one(metrics_file: Path, tmp_path: Path) -> None:
    block = verify_docs.generate(metrics_object(), "test")
    readme = _readme(tmp_path, block.split("\n\n")[0])
    assert _run(metrics_file, readme) == 1


# --- exit 2 ------------------------------------------------------------------------------------


def test_absent_metrics_exits_two(tmp_path: Path, capsys) -> None:
    readme = _readme(tmp_path, "anything")
    code = _run(tmp_path / "results" / "metrics.json", readme)
    assert code == 2
    err = capsys.readouterr().err
    assert "metrics.json" in err and "make eval-replay" in err


def test_readme_without_markers_exits_two(metrics_file: Path, tmp_path: Path, capsys) -> None:
    readme = _readme(tmp_path, verify_docs.generate(metrics_object(), "test"), markers=False)
    assert _run(metrics_file, readme) == 2
    err = capsys.readouterr().err
    assert verify_docs.BEGIN in err and verify_docs.END in err


def test_absent_readme_exits_two(metrics_file: Path, tmp_path: Path) -> None:
    assert _run(metrics_file, tmp_path / "nope.md") == 2


def test_metrics_that_is_not_a_report_exits_two(tmp_path: Path, capsys) -> None:
    path = tmp_path / "metrics.json"
    path.write_text(json.dumps({"schema": 1}), encoding="utf-8")
    assert _run(path, _readme(tmp_path, "x")) == 2
    assert "not a report" in capsys.readouterr().err


def test_unparsable_metrics_exits_two(tmp_path: Path) -> None:
    path = tmp_path / "metrics.json"
    path.write_text("{not json", encoding="utf-8")
    assert _run(path, _readme(tmp_path, "x")) == 2


def test_json_list_is_not_a_metrics_object(tmp_path: Path) -> None:
    path = tmp_path / "metrics.json"
    path.write_text("[]", encoding="utf-8")
    assert _run(path, _readme(tmp_path, "x")) == 2


# --- --emit ------------------------------------------------------------------------------------


def test_emit_prints_a_pasteable_block(metrics_file: Path, tmp_path: Path, capsys) -> None:
    readme = _readme(tmp_path, "stale")
    assert _run(metrics_file, readme, "--emit") == 0
    printed = capsys.readouterr().out.strip("\n")
    assert printed.startswith(verify_docs.BEGIN) and printed.endswith(verify_docs.END)
    pasted = _readme(tmp_path, "\n".join(printed.split("\n")[1:-1]))
    assert _run(metrics_file, pasted) == 0
