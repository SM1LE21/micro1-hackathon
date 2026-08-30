"""One cell: the child process, the trace it leaves and the scoring that closes it out.

Split out of `run.py` so neither file passes AGENTS.md's ~300 lines. `launch` is still the one
subprocess seam (a test replaces `run._launch` and no test needs a child), and a broken child is
data here, never an exception: the parent repairs a partial line, writes the `run_end` the child
owed, scores what is on disk and files the failure. `run.py` keeps the sweep around it and passes
in every seam it owns — the launcher to `run_cells`, `repair` and `append_run_end` to `finish_cell`
— so a name replaced on `run.py` is the code a sweep runs, not merely an alias beside it.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from evals.harness import score as scoring
from evals.harness.plan import REPO_ROOT, Cell
from evals.harness.trace_check import check_trace

# 01-architecture.md section 9, one clause per stop condition, past tense, for the diagnosis line.
CLAUSE = {
    "gate_rejected": "the approver rejected the record at the gate",
    "budget_exhausted": "the run spent its tool-call budget without an accepted record",
    "max_submits": "every submit_record attempt was rejected",
    "max_tokens": "the model's output was cut off at max_tokens",
    "no_submission": "the model ended its turns without submitting a record",
    "timeout": "the child process was killed at the wall-clock limit",
    "crashed": "the process died before the loop could report",
    "replay_miss": "the cache held no response for the request",
    "render_failed": "a cited line no longer carried its symbol at render time",
    "api_error": "the run ended on an API or runtime error",
    "refusal": "the model refused the request",
}


# --- the child process -------------------------------------------------------------------------


def launch(cell: Cell) -> tuple[int, str, bool, float]:
    """The one subprocess seam: (returncode, stderr, timed_out, wall_s)."""
    command = [sys.executable, "-m", "art30.cli", "scan", cell.repo, "--arm", cell.arm,
               "--case", cell.case, "--seed", str(cell.seed), "--mode", cell.mode,
               "--approve", cell.approve, "--out", cell.out]
    env = dict(os.environ)
    env["ART30_TRACE_DIR"] = cell.trace_dir  # the child's half of the section 9 seam
    # ADR 0008 item 5: a sweep is run at art30's own defaults plus whatever the sweep
    # itself set. `~/.config/art30/config.toml` is not a checkout artefact, so a clean
    # checkout does not exclude it; this switch does, for every key at once.
    env["ART30_IGNORE_SETTINGS_FILES"] = "1"
    if cell.unlock:
        env["ART30_UNLOCK_TEST"] = "1"  # the CLI's own half of the lock (section 5.4)
    # `--approve ask` puts a person at the child's terminal: a pipe swallows the prompt and
    # art30/cli.py refuses a non-tty outright. Giving up stderr capture on those six cells (it
    # only feeds error.txt) is the cheaper half of the trade.
    capture = cell.approve != "ask"
    started = time.monotonic()
    try:
        done = subprocess.run(command, cwd=REPO_ROOT, env=env, capture_output=capture,
                              text=True, timeout=cell.timeout)
        return (done.returncode, (done.stderr or "") if capture else "", False,
                time.monotonic() - started)
    except subprocess.TimeoutExpired as exc:  # subprocess.run has already killed the child
        err = exc.stderr.decode("utf-8", "replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return -1, err, True, time.monotonic() - started


def clear_slot(cell: Cell) -> None:
    """01 section 4.2's rule for a cache slot, for a results slot: the directory is this run.

    Without it an earlier sweep's `record.json` is read as this run's output, and a run that
    produced no record inherits the F1 and the false-safe count of the one that did (section 4.4).
    """
    out = Path(cell.out)
    if out.is_dir():
        shutil.rmtree(out)


def run_cells(cells: list[Cell], jobs: int, finish, fail_fast: bool,
              launcher=launch) -> list[dict]:
    """Launch and score lazily, so `--fail-fast` stops the sweep rather than only its scoring.

    Cold-first: the head runs alone so the shared prefix is written once (01 section 8).
    `launcher` is named apart from the module-level `launch` it defaults to, so the loop body below
    says which one it calls; `run.py` passes `run._launch`, the seam a test replaces.
    """
    def _stop(recent: list[dict]) -> bool:
        return fail_fast and any(r["end"].get("stop_condition") != "accepted" for r in recent)

    rows: list[dict] = []
    if jobs <= 1 or len(cells) <= 1:
        for cell in cells:
            clear_slot(cell)
            rows.append(finish(cell, launcher(cell)))
            if _stop(rows[-1:]):
                break
        return rows
    clear_slot(cells[0])
    rows.append(finish(cells[0], launcher(cells[0])))
    if _stop(rows[-1:]):
        return rows
    rest = cells[1:]
    with ProcessPoolExecutor(max_workers=jobs) as pool:
        for start in range(0, len(rest), jobs):
            batch = rest[start:start + jobs]
            for cell in batch:
                clear_slot(cell)
            outcomes = list(pool.map(launcher, batch))
            rows += [finish(cell, outcome) for cell, outcome in zip(batch, outcomes)]
            if _stop(rows[-len(batch):]):
                break
    return rows


# --- closing a cell out ----------------------------------------------------------------------


def read_trace(path: Path) -> list[dict]:
    lines: list[dict] = []
    if not path.is_file():
        return lines
    for line in path.read_text(encoding="utf-8", errors="replace").split("\n"):
        try:
            obj = json.loads(line) if line.strip() else None
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            lines.append(obj)
    return lines


def repair(trace: Path) -> int:
    """A child killed mid-write leaves a partial line, which fails the validator's first check."""
    raw = trace.read_bytes()
    keep = offset = 0
    while offset < len(raw):
        newline = raw.find(b"\n", offset)
        if newline == -1:
            break
        try:
            json.loads(raw[offset:newline].decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            break
        keep = offset = newline + 1
    if keep < len(raw):
        with trace.open("rb+") as handle:
            handle.truncate(keep)
    return len(raw) - keep


def append_run_end(trace: Path, condition: str, note: str, wall_s: float) -> None:
    """The parent's own run_end, with every counter reconciled against the step lines."""
    steps = [o for o in read_trace(trace) if o.get("type") == "step"]
    calls = [c for s in steps for c in (s.get("tool_calls") or []) if isinstance(c, dict)]
    rejected = 0
    for step in steps:
        ids = {c.get("id") for c in (step.get("tool_calls") or [])
               if isinstance(c, dict) and c.get("name") == "submit_record"}
        for result in step.get("tool_results") or []:
            if isinstance(result, dict) and result.get("call_id") in ids:
                try:  # a handler error string, or a line the repair truncated: not a parent crash
                    payload = json.loads(result.get("output") or "{}")
                except (json.JSONDecodeError, TypeError):
                    continue
                rejected += 1 if isinstance(payload, dict) and payload.get("accepted") is False else 0
    end = {"type": "run_end", "stop_condition": condition, "steps": len(steps),
           "tool_calls_total": len(calls),
           "submits": sum(1 for c in calls if c.get("name") == "submit_record"),
           "verify_rounds": rejected, "wall_s": round(wall_s, 1),
           "cost_usd": steps[-1].get("cost_cum_usd", 0.0) if steps else 0.0,
           "record_path": None, "note": note}
    with trace.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(end, ensure_ascii=False) + "\n")


def relative(path: Path) -> str:
    """Repository-relative where possible: no absolute path reaches a written artefact."""
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return path.name


def diagnosis(cell: Cell, lines: list[dict], end: dict) -> str:
    """Five generated lines, first line four fields (06-traces.md section 4, check 15)."""
    start = lines[0] if lines and lines[0].get("type") == "run_start" else {}
    steps = [o for o in lines if o.get("type") == "step"]
    condition = str(end.get("stop_condition") or "crashed")
    calls = [c.get("name") for c in (steps[-1].get("tool_calls") or []) if isinstance(c, dict)] if steps else []
    head = " · ".join([f"{cell.arm}/{cell.case}-s{cell.seed}", condition,
                       CLAUSE.get(condition, "the run did not end accepted"),
                       f"step {len(steps)}" if steps else "no step line"])
    return "\n".join([
        head[:160],
        f"run_id: {start.get('run_id') or f'{cell.arm}-{cell.case}-s{cell.seed}'}",
        f"rule: {end.get('note') or CLAUSE.get(condition, condition)}",
        f"last step: {', '.join(calls) or 'none'}",
        f"trace: {relative(Path(cell.trace))}",
    ]) + "\n"


def read_json(path: Path) -> dict | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def finish_cell(cell: Cell, outcome: tuple[int, str, bool, float], manifest: dict, sha: str,
                repair_trace=repair, append_end=append_run_end) -> dict:
    """Repair, close, score and file one cell. A broken child is data here, never an exception.

    The two halves of the timeout repair arrive as arguments, defaulting to this module's own, so
    that replacing `run._repair` or `run._append_run_end` changes what a sweep does on a timeout
    and not only what a direct call to the alias does.
    """
    code, stderr, timed_out, wall_s = outcome
    trace, out = Path(cell.trace), Path(cell.out)
    if timed_out and trace.is_file():
        lost = repair_trace(trace)
        append_end(trace, "timeout",
                   f"killed at {round(wall_s)}s; {lost} bytes of a partial line discarded", wall_s)
    lines = read_trace(trace)
    ended = [o for o in lines if o.get("type") == "run_end"]
    if not ended and stderr.strip():
        out.mkdir(parents=True, exist_ok=True)
        (out / "error.txt").write_text(stderr, encoding="utf-8")
    if not ended and lines:  # a trace with no run_end: the parent writes the one the child owed
        tail = stderr.strip().splitlines()[-1][:120] if stderr.strip() else str(code)
        append_end(trace, "api_error", f"child exited {code}: {tail}", wall_s)
        lines = read_trace(trace)
        ended = [o for o in lines if o.get("type") == "run_end"]
    # No trace at all is `crashed`, which report.py counts from the plan (01 section 9).
    end = ended[-1] if ended else {"stop_condition": "crashed", "wall_s": round(wall_s, 1)}
    checkpoints = [o for o in lines if o.get("type") == "checkpoint"]
    metrics = scoring.score_run(
        read_json(out / "record.json"), manifest, end, draft=read_json(out / "record.draft.json"),
        repo_root=Path(cell.repo), checkpoint=checkpoints[-1] if checkpoints else None,
        arm=cell.arm, seed=cell.seed, mode=cell.mode, manifest_sha256=sha)
    out.mkdir(parents=True, exist_ok=True)
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    if end.get("stop_condition") != "accepted" and trace.is_file():
        target = Path(cell.trace_dir) / "failures" / cell.arm / f"{cell.case}-s{cell.seed}.jsonl"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(trace.read_bytes())
        target.with_suffix(".diagnosis.txt").write_text(diagnosis(cell, lines, end), encoding="utf-8")
    for violation in (check_trace(trace) if trace.is_file() else []):
        print(f"  trace: {violation}")
    return {"cell": cell, "metrics": metrics, "end": end,
            "wall_s": float(end.get("wall_s") or round(wall_s, 1)),
            "step1": next((o.get("request_hash") for o in lines if o.get("type") == "step"), None)}


# --- the failure index (06-traces.md section 4) ------------------------------------------------


def failure_index(traces: Path) -> None:
    """06-traces.md section 4: the index cannot fall behind the directory because it is regenerated."""
    root = traces / "failures"
    if not root.is_dir():
        return
    rows = ["| file | arm | case | seed | stop condition | what happened |", "|---|---|---|---|---|---|"]
    for trace in sorted(root.rglob("*.jsonl")):
        case, _, seed = trace.stem.rpartition("-s")
        note = trace.with_suffix(".diagnosis.txt")
        fields = (note.read_text(encoding="utf-8").split("\n")[0].split(" · ") if note.is_file() else [])
        rows.append(f"| {trace.relative_to(root)} | {trace.parent.name} | {case} | {seed} | "
                    f"{fields[1] if len(fields) > 1 else ''} | {fields[2] if len(fields) > 2 else ''} |")
    (root / "README.md").write_text(
        "# Failure traces\n\nGenerated by `evals/harness/run.py`: every run whose stop condition is "
        "not `accepted` is copied here with a one-line diagnosis beside it.\n\n" + "\n".join(rows) + "\n",
        encoding="utf-8")
