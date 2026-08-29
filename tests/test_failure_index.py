"""`traces/failures/INDEX.md` over a synthetic failures tree (tmp_path only).

Offline and model-free: the inputs are diagnosis files of the shape `cells.diagnosis` writes
(06-traces.md section 4). No test reads or writes the repository's own `traces/`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from evals.harness import failure_index

FIRST = ("advanced/S08-s2 · max_submits · the completeness guard kept re-adding the events queue "
         "· step 19, rejected_claims[0]")
SECOND = ("baseline/R02-s3 · budget_exhausted · read 41 files without reaching a delete path "
          "· steps 96-120")


def _diagnosis(traces: Path, arm: str, case: str, seed: int, first: str,
               *, trace: bool = True) -> Path:
    target = traces / "failures" / arm / f"{case}-s{seed}.diagnosis.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join([first, f"run_id: {arm[:3]}-{case}-s{seed}-9f3ac1e",
                                 "rule: 5 submits rejected", "last step: grep, submit_record",
                                 f"trace: traces/{arm}/{case}-s{seed}.jsonl"]) + "\n",
                      encoding="utf-8")
    if trace:
        target.with_suffix("").with_suffix(".jsonl").write_text("{}\n", encoding="utf-8")
    return target


def _run(traces: Path, *extra: str) -> int:
    return failure_index.main(["--traces", str(traces), *extra])


def _index(traces: Path) -> str:
    return (traces / "failures" / "INDEX.md").read_text(encoding="utf-8")


# --- the empty case ------------------------------------------------------------------------------


def test_no_failures_directory_is_an_empty_index(tmp_path: Path, capsys) -> None:
    assert _run(tmp_path / "traces") == 0
    text = _index(tmp_path / "traces")
    assert failure_index.EMPTY.strip() in text
    assert "| arm |" not in text
    assert "0 failure(s)" in capsys.readouterr().out


def test_empty_failures_directory_is_an_empty_index(tmp_path: Path) -> None:
    (tmp_path / "traces" / "failures").mkdir(parents=True)
    assert _run(tmp_path / "traces") == 0
    assert failure_index.EMPTY.strip() in _index(tmp_path / "traces")


# --- the rows ------------------------------------------------------------------------------------


def test_one_row_per_diagnosis_with_the_five_fields(tmp_path: Path, capsys) -> None:
    traces = tmp_path / "traces"
    _diagnosis(traces, "advanced", "S08", 2, FIRST)
    _diagnosis(traces, "baseline", "R02", 3, SECOND)
    assert _run(traces) == 0
    lines = [line for line in _index(traces).split("\n") if line.startswith("| ")]
    assert lines[0] == failure_index.HEADER[0]
    assert lines[1] == ("| advanced | S08 | 2 | max_submits | the completeness guard kept "
                        "re-adding the events queue · step 19, rejected_claims[0] |")
    assert lines[2].startswith("| baseline | R02 | 3 | budget_exhausted | read 41 files")
    assert "2 failure(s)" in capsys.readouterr().out


def test_rows_sort_by_arm_then_case_then_seed_numerically(tmp_path: Path) -> None:
    traces = tmp_path / "traces"
    for seed in (10, 2, 1):
        _diagnosis(traces, "advanced", "S08", seed, f"advanced/S08-s{seed} · timeout · killed · x")
    _diagnosis(traces, "advanced", "S01", 1, "advanced/S01-s1 · crashed · no run_end · x")
    seeds = [line.split(" | ")[2] for line in _index(traces).split("\n")
             if line.startswith("| advanced")] if _run(traces) == 0 else []
    assert seeds == ["1", "1", "2", "10"]


def test_a_malformed_first_line_still_yields_a_row(tmp_path: Path) -> None:
    traces = tmp_path / "traces"
    _diagnosis(traces, "advanced", "S03", 1, "hand-written nonsense with no separators")
    assert _run(traces) == 0
    row = [line for line in _index(traces).split("\n") if line.startswith("| advanced")][0]
    assert row == "| advanced | S03 | 1 |  |  |"


def test_pipes_in_a_diagnosis_cannot_close_the_column(tmp_path: Path) -> None:
    traces = tmp_path / "traces"
    _diagnosis(traces, "advanced", "S05", 1, "advanced/S05-s1 · api_error · a | b · step 3")
    assert _run(traces) == 0
    row = [line for line in _index(traces).split("\n") if line.startswith("| advanced")][0]
    assert row.count("|") - row.count("\\|") == 6 and "a \\| b" in row


def test_a_diagnosis_without_its_trace_is_still_indexed(tmp_path: Path) -> None:
    """The index reads the diagnosis files, so it disagrees with a trace-derived one on purpose."""
    traces = tmp_path / "traces"
    _diagnosis(traces, "advanced", "S09", 1, "advanced/S09-s1 · crashed · no run_end line · x",
               trace=False)
    assert _run(traces) == 0
    assert "| advanced | S09 | 1 | crashed |" in _index(traces)


def test_the_index_is_not_indexed_by_itself(tmp_path: Path) -> None:
    traces = tmp_path / "traces"
    _diagnosis(traces, "advanced", "S08", 2, FIRST)
    assert _run(traces) == 0
    first = _index(traces)
    assert _run(traces) == 0
    assert _index(traces) == first


# --- --check ---------------------------------------------------------------------------------


def test_check_is_one_on_an_absent_index(tmp_path: Path, capsys) -> None:
    traces = tmp_path / "traces"
    _diagnosis(traces, "advanced", "S08", 2, FIRST)
    assert _run(traces, "--check") == 1
    assert "stale" in capsys.readouterr().err
    assert not (traces / "failures" / "INDEX.md").exists()  # --check writes nothing


def test_check_is_zero_after_a_build_and_one_after_a_new_failure(tmp_path: Path) -> None:
    traces = tmp_path / "traces"
    _diagnosis(traces, "advanced", "S08", 2, FIRST)
    assert _run(traces) == 0
    assert _run(traces, "--check") == 0
    _diagnosis(traces, "baseline", "R02", 3, SECOND)
    assert _run(traces, "--check") == 1


def test_build_returns_the_count(tmp_path: Path) -> None:
    traces = tmp_path / "traces"
    _diagnosis(traces, "advanced", "S08", 2, FIRST)
    _diagnosis(traces, "advanced", "S08", 3, FIRST.replace("-s2", "-s3"))
    text, count = failure_index.build(traces)
    assert count == 2 and text.startswith("# Failure index")
