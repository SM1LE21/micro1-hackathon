"""cases x arms x seeds into runs, traces and failure diagnoses (docs/spec/05-eval-harness.md section 5).

One child `art30 scan` process per cell, so a wall-clock timeout is a kill and a failure is an exit
code rather than an exception in the parent (01-architecture.md section 1.2, decision 9). This module
never imports `loop.run` and never touches `results/metrics.json`, which is `report.py`'s file.

Over AGENTS.md's ~300 lines, as `trace_check.py` is and for the same reason: the plan, the two
pre-flight gates, the lock, the child, the failure capture and the timing file are the stages of one
sweep, and a reader chasing an exit code should not have to follow it across files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import statistics
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import yaml

from evals.harness import score as scoring
from evals.harness.trace_check import check_trace

REPO_ROOT = Path(__file__).resolve().parents[2]
SPLIT_FILE = REPO_ROOT / "evals" / "split.yaml"
MANIFESTS = REPO_ROOT / "evals" / "fixtures" / "manifests"
SPECS = REPO_ROOT / "evals" / "fixtures" / "specs"
SYNTHETIC = REPO_ROOT / "evals" / "fixtures" / "synthetic"
REAL = REPO_ROOT / "evals" / "fixtures" / "real"
TRACES = REPO_ROOT / "traces"
RESULTS = REPO_ROOT / "results"
ADR_DIR = REPO_ROOT / ".vault" / "adr"

TIMEOUTS = {"synthetic": 900, "real": 1800}  # section 5.3
ZERO_SHA = "0" * 64
ARMS = ("baseline", "advanced")
DEFAULT_OUT = "results/runs"  # the scored tree; any other --out takes its traces with it (section 9)
# CASES.md, Real cases: the vendored directory each real case reads. A hand-written real manifest
# may name its own with a `repo` key; none exists yet, so the mapping lives here.
REAL_DIRS = {"R01": "full-stack-fastapi-template", "R02": "flaskbb", "R03": "pinry",
             "R04": "microblog", "R05": "Django-Styleguide-Example"}
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


class Abort(Exception):
    """A harness refusal carrying one of section 5.5's exit codes."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Cell:
    """One (case, arm, seed) and everything the child needs. Picklable for the pool."""

    case: str
    arm: str
    seed: int
    repo: str
    out: str
    trace: str
    trace_dir: str
    mode: str
    approve: str
    timeout: int
    unlock: bool


# --- selection and the two pre-flight gates -------------------------------------------------


def _load_split() -> dict:
    try:
        return yaml.safe_load(SPLIT_FILE.read_text(encoding="utf-8")) or {}
    except OSError as exc:
        raise Abort(1, f"cannot read {SPLIT_FILE}: {exc}") from None


def cases_for(split_data: dict, name: str, include_reserve: bool = False) -> list[str]:
    """`--split all` is dev + test; reserve is never implied by a split (section 5)."""
    groups = ["dev", "test"] if name == "all" else [name]
    return [str(c) for g in groups + (["reserve"] if include_reserve else [])
            for c in split_data.get(g) or []]


def membership(split_data: dict) -> dict[str, str]:
    return {str(c): g for g in ("dev", "test", "reserve") for c in split_data.get(g) or []}


def select_cases(split_data: dict, split: str, cases: str | None,
                 include_reserve: bool = False) -> list[str]:
    """The one selection. `report.py` expands the same one, or it reports a plan nobody ran."""
    if cases:
        chosen = [c.strip() for c in cases.split(",") if c.strip()]
        chosen += cases_for(split_data, "reserve") if include_reserve else []
    else:
        chosen = cases_for(split_data, split, include_reserve)
    unknown = [c for c in chosen if c not in membership(split_data)]
    if unknown:
        raise Abort(1, f"cases not in {SPLIT_FILE}: {', '.join(unknown)}")
    return list(dict.fromkeys(chosen))  # an explicit list keeps its order, a split keeps the file's


def _manifest(case: str) -> tuple[dict, str]:
    path = MANIFESTS / f"{case}.yaml"
    try:
        raw = path.read_bytes()
        data = yaml.safe_load(raw.decode("utf-8")) or {}
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise Abort(1, f"cannot read manifest {path}: {exc}") from None
    return data, hashlib.sha256(raw).hexdigest()


def _fixture(case: str, manifest: dict) -> Path:
    if str(manifest.get("source") or "synthetic") == "real":
        root = REAL / str(manifest.get("repo") or REAL_DIRS.get(case) or case)
    else:
        root = SYNTHETIC / case
    if not root.is_dir():
        raise Abort(1, f"fixture for {case} not found at {root}")
    return root


def _check_freeze(cases: list[str], manifests: dict[str, dict], split_data: dict) -> None:
    """Section 5.1: the spec freeze and the split declaration, both before any model call."""
    member = membership(split_data)
    for case in cases:
        # Keyed on the manifest's source, not on truthiness: a real manifest carries
        # `spec_sha256: null` by construction, a synthetic one without it is unfrozen
        # (fixture-generator.md sections 6 and 8).
        if str(manifests[case].get("source") or "synthetic") != "real":
            expected = manifests[case].get("spec_sha256")
            if not expected:
                raise Abort(4, f"{case}: synthetic manifest carries no spec_sha256; the spec is not frozen")
            spec = SPECS / f"{case}.yaml"
            if not spec.is_file():
                raise Abort(1, f"spec for {case} not found at {spec}")
            actual = hashlib.sha256(spec.read_bytes()).hexdigest()
            if actual != expected:
                raise Abort(4, f"{case}: spec sha256 {actual} != manifest spec_sha256 {expected}")
        declared, group = str(manifests[case].get("split") or ""), member[case]
        # CASES.md calls R05 "reserve (test)", so a reserve manifest may declare either.
        if declared != group and not (group == "reserve" and declared == "test"):
            raise Abort(4, f"{case}: manifest split {declared!r} != split.yaml {group!r}")


# --- the test-split lock (section 5.4) ------------------------------------------------------


def _ledger_lines() -> list[str]:
    path = RESULTS / "test-runs.log"
    return [l for l in path.read_text(encoding="utf-8").split("\n") if l.strip()] if path.is_file() else []


def _committed_ledger() -> list[str]:
    """The committed copy of the ledger, which the chain alone cannot stand in for (section 5.4).

    A forward chain proves each remaining line follows its predecessor, so an edit or a deletion in
    the middle is caught and a deletion at the end is not: drop the last two lines and every
    survivor still verifies. `results/test-runs.log` is committed precisely so there is a witness;
    this reads it. A ledger outside the working tree (a test sandbox) has none, and is skipped.
    """
    try:
        relative = (RESULTS / "test-runs.log").resolve().relative_to(REPO_ROOT)
    except ValueError:
        return []
    try:
        out = subprocess.run(["git", "show", f"HEAD:{relative.as_posix()}"], cwd=REPO_ROOT,
                             capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return []
    return [l for l in out.stdout.split("\n") if l.strip()] if out.returncode == 0 else []


def _check_lock(args: argparse.Namespace, cases: list[str], split_data: dict) -> tuple[bool, list[str]]:
    """Steps 1 to 4. Returns (the lock applied, the ledger as verified) for the append."""
    member = membership(split_data)
    locked = [c for c in cases if member[c] in ("test", "reserve")]
    if not locked:
        return False, []
    if not args.unlock_test:
        raise Abort(2, f"test-split cases selected: {','.join(locked)}; pass --unlock-test --reason \"...\"")
    if not args.reason:
        raise Abort(1, '--unlock-test requires --reason "..."')
    lines = _ledger_lines()
    committed = _committed_ledger()
    if lines[:len(committed)] != committed:  # append-only against the witness, not only forward
        raise Abort(1, f"results/test-runs.log does not begin with its committed copy: "
                       f"{len(committed)} committed lines, {len(lines)} on disk; lines were "
                       "removed or edited")
    for index, line in enumerate(lines):  # the chain, or an edit in the middle resets the budget
        want = ZERO_SHA if index == 0 else hashlib.sha256(lines[index - 1].encode("utf-8")).hexdigest()
        if line.rsplit("|", 1)[-1].strip() != want:
            raise Abort(1, f"results/test-runs.log:{index + 1}: chain broken; expected {want}")
    live = [l for l in lines if len(l.split("|")) > 5 and l.split("|")[5].strip() == "live"]
    if args.mode == "live" and len(live) >= 2:
        print("\n".join(live))
        if not args.adr:
            raise Abort(3, "two live test sweeps are on the record; a third needs --adr NNNN naming an ADR")
        adr = sorted(ADR_DIR.glob(f"{args.adr}-*.md"))
        if not adr:
            raise Abort(3, f"no ADR at {ADR_DIR}/{args.adr}-*.md")
        if "test sweep" not in adr[0].read_text(encoding="utf-8"):
            raise Abort(3, f"{adr[0]} does not contain the string 'test sweep'")
    return True, lines


def _append_ledger(args: argparse.Namespace, cases: list[str], lines: list[str]) -> None:
    """One line per sweep, written before the first model call; replay lines never count."""
    # The contract's clause is about a replay. Suppressing the ledger on a live sweep would let one
    # environment variable defeat the two-sweep ceiling with nothing left on the record.
    if args.mode == "replay" and os.environ.get("ART30_REPRODUCIBLE") == "1":
        return  # contract, Budgets: a replay rewrites neither the ledger nor the timing file
    reason = f"ADR {args.adr}: {args.reason}" if args.adr else str(args.reason)
    previous = hashlib.sha256(lines[-1].encode("utf-8")).hexdigest() if lines else ZERO_SHA
    fields = [datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), git_sha7(), args.arms,
              ",".join(cases), args.seeds, args.mode, reason.replace("|", "/"), previous]
    path = RESULTS / "test-runs.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(" | ".join(fields) + "\n")


def git_sha7() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--short=7", "HEAD"], cwd=REPO_ROOT,
                             capture_output=True, text=True, timeout=5, check=True)
    except (OSError, subprocess.SubprocessError):
        return "0000000"
    return out.stdout.strip() or "0000000"


# --- the plan and the child process ---------------------------------------------------------


def _seeds(raw: str) -> list[int]:
    try:
        return [int(s) for s in raw.split(",") if s.strip()]
    except ValueError:
        raise Abort(1, f"--seeds must be whole numbers, got {raw!r}") from None


def trace_root(out: str) -> Path:
    """Section 9: a sweep that writes outside the scored tree takes its traces with it.

    `make gate-timing` re-runs six advanced cells only to time the human at the gate; pointed at
    `traces/` those six runs overwrite six committed traces of the recorded sweep, which is the
    evidence the pass exists to leave alone.
    """
    return TRACES if Path(out).resolve() == (REPO_ROOT / DEFAULT_OUT).resolve() else Path(out) / "traces"


def _plan(args: argparse.Namespace, cases: list[str], manifests: dict[str, dict]) -> list[Cell]:
    """Order case -> seed -> arm, so a case's two arms are adjacent and share any drift (01 section 8)."""
    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    if [a for a in arms if a not in ARMS]:
        raise Abort(1, f"unknown arm in {args.arms!r}")
    traces = trace_root(args.out)
    cells: list[Cell] = []
    for case in cases:
        kind = "real" if str(manifests[case].get("source") or "") == "real" else "synthetic"
        repo = _fixture(case, manifests[case])
        for seed in _seeds(args.seeds):
            for arm in arms:
                cells.append(Cell(
                    case=case, arm=arm, seed=seed, repo=str(repo),
                    out=str(Path(args.out) / arm / case / f"s{seed}"),
                    trace=str(traces / arm / f"{case}-s{seed}.jsonl"), trace_dir=str(traces),
                    mode=args.mode, approve=args.approve,
                    timeout=args.timeout or TIMEOUTS[kind], unlock=bool(args.unlock_test)))
    return cells


def _launch(cell: Cell) -> tuple[int, str, bool, float]:
    """The one subprocess seam: (returncode, stderr, timed_out, wall_s)."""
    command = [sys.executable, "-m", "art30.cli", "scan", cell.repo, "--arm", cell.arm,
               "--case", cell.case, "--seed", str(cell.seed), "--mode", cell.mode,
               "--approve", cell.approve, "--out", cell.out]
    env = dict(os.environ)
    env["ART30_TRACE_DIR"] = cell.trace_dir  # the child's half of the section 9 seam
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


def _clear_slot(cell: Cell) -> None:
    """01 section 4.2's rule for a cache slot, for a results slot: the directory is this run.

    Without it an earlier sweep's `record.json` is read as this run's output, and a run that
    produced no record inherits the F1 and the false-safe count of the one that did (section 4.4).
    """
    out = Path(cell.out)
    if out.is_dir():
        shutil.rmtree(out)


def _run_cells(cells: list[Cell], jobs: int, finish, fail_fast: bool) -> list[dict]:
    """Launch and score lazily, so `--fail-fast` stops the sweep rather than only its scoring.

    Cold-first: the head runs alone so the shared prefix is written once (01 section 8).
    """
    def _stop(recent: list[dict]) -> bool:
        return fail_fast and any(r["end"].get("stop_condition") != "accepted" for r in recent)

    rows: list[dict] = []
    if jobs <= 1 or len(cells) <= 1:
        for cell in cells:
            _clear_slot(cell)
            rows.append(finish(cell, _launch(cell)))
            if _stop(rows[-1:]):
                break
        return rows
    _clear_slot(cells[0])
    rows.append(finish(cells[0], _launch(cells[0])))
    if _stop(rows[-1:]):
        return rows
    rest = cells[1:]
    with ProcessPoolExecutor(max_workers=jobs) as pool:
        for start in range(0, len(rest), jobs):
            batch = rest[start:start + jobs]
            for cell in batch:
                _clear_slot(cell)
            outcomes = list(pool.map(_launch, batch))
            rows += [finish(cell, outcome) for cell, outcome in zip(batch, outcomes)]
            if _stop(rows[-len(batch):]):
                break
    return rows


# --- closing a cell out ----------------------------------------------------------------------


def _read_trace(path: Path) -> list[dict]:
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


def _repair(trace: Path) -> int:
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


def _append_run_end(trace: Path, condition: str, note: str, wall_s: float) -> None:
    """The parent's own run_end, with every counter reconciled against the step lines."""
    steps = [o for o in _read_trace(trace) if o.get("type") == "step"]
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


def _relative(path: Path) -> str:
    """Repository-relative where possible: no absolute path reaches a written artefact."""
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return path.name


def _diagnosis(cell: Cell, lines: list[dict], end: dict) -> str:
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
        f"trace: {_relative(Path(cell.trace))}",
    ]) + "\n"


def _json(path: Path) -> dict | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _finish(cell: Cell, outcome: tuple[int, str, bool, float], manifest: dict, sha: str) -> dict:
    """Repair, close, score and file one cell. A broken child is data here, never an exception."""
    code, stderr, timed_out, wall_s = outcome
    trace, out = Path(cell.trace), Path(cell.out)
    if timed_out and trace.is_file():
        lost = _repair(trace)
        _append_run_end(trace, "timeout",
                        f"killed at {round(wall_s)}s; {lost} bytes of a partial line discarded", wall_s)
    lines = _read_trace(trace)
    ended = [o for o in lines if o.get("type") == "run_end"]
    if not ended and stderr.strip():
        out.mkdir(parents=True, exist_ok=True)
        (out / "error.txt").write_text(stderr, encoding="utf-8")
    if not ended and lines:  # a trace with no run_end: the parent writes the one the child owed
        tail = stderr.strip().splitlines()[-1][:120] if stderr.strip() else str(code)
        _append_run_end(trace, "api_error", f"child exited {code}: {tail}", wall_s)
        lines = _read_trace(trace)
        ended = [o for o in lines if o.get("type") == "run_end"]
    # No trace at all is `crashed`, which report.py counts from the plan (01 section 9).
    end = ended[-1] if ended else {"stop_condition": "crashed", "wall_s": round(wall_s, 1)}
    checkpoints = [o for o in lines if o.get("type") == "checkpoint"]
    metrics = scoring.score_run(
        _json(out / "record.json"), manifest, end, draft=_json(out / "record.draft.json"),
        repo_root=Path(cell.repo), checkpoint=checkpoints[-1] if checkpoints else None,
        arm=cell.arm, seed=cell.seed, mode=cell.mode, manifest_sha256=sha)
    out.mkdir(parents=True, exist_ok=True)
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    if end.get("stop_condition") != "accepted" and trace.is_file():
        target = Path(cell.trace_dir) / "failures" / cell.arm / f"{cell.case}-s{cell.seed}.jsonl"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(trace.read_bytes())
        target.with_suffix(".diagnosis.txt").write_text(_diagnosis(cell, lines, end), encoding="utf-8")
    for violation in (check_trace(trace) if trace.is_file() else []):
        print(f"  trace: {violation}")
    return {"cell": cell, "metrics": metrics, "end": end,
            "wall_s": float(end.get("wall_s") or round(wall_s, 1)),
            "step1": next((o.get("request_hash") for o in lines if o.get("type") == "step"), None)}


# --- what the sweep leaves behind -------------------------------------------------------------


def _identity_check(rows: list[dict]) -> None:
    """01 decision 8: the arms' step-1 request hashes match per case, or the comparison is invalid."""
    by_case: dict[str, dict[str, str]] = {}
    for row in rows:
        if row["step1"]:
            by_case.setdefault(row["cell"].case, {})[row["cell"].arm] = row["step1"]
    for case in sorted(by_case):
        if len(set(by_case[case].values())) > 1:
            detail = ", ".join(f"{a}={h[:12]}" for a, h in sorted(by_case[case].items()))
            raise Abort(1, f"{case}: step-1 request hashes differ between arms ({detail})")


def _stat(values: list[float]) -> dict:
    return {"wall_s_mean": round(statistics.fmean(values), 1),
            "wall_s_std": round(statistics.pstdev(values), 1), "n": len(values)}


def _write_timing(mode: str, rows: list[dict], full: bool, tag: str) -> Path | None:
    """Section 6: the live sweep's clock, and never a replay's or a subset's over it.

    `results/timing.json` is the recorded 84-run sweep, which section 9 reads for the README's
    machine minutes. A dev-iteration subset is a live sweep too and would replace it with a
    nine-run advanced-only clock, so only a sweep of both arms over `--split all` claims the name.
    """
    if os.environ.get("ART30_REPRODUCIBLE") == "1" or not rows:
        return None
    per_case: dict[str, dict[str, list[float]]] = {}
    per_arm: dict[str, list[float]] = {}
    for row in rows:
        cell = row["cell"]
        per_case.setdefault(cell.case, {}).setdefault(cell.arm, []).append(row["wall_s"])
        per_arm.setdefault(cell.arm, []).append(row["wall_s"])
    payload = {"recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
               "git_sha": git_sha7(),
               "per_case": {c: {a: _stat(v) for a, v in sorted(arms.items())}
                            for c, arms in sorted(per_case.items())},
               "per_arm": {a: _stat(v) for a, v in sorted(per_arm.items())}}
    if mode != "live":
        name = "timing.replay.json"
    else:
        name = "timing.json" if full else f"timing.{tag}.json"
    path = RESULTS / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _failure_index(traces: Path) -> None:
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="evals.harness.run", description="Run cases x arms x seeds.")
    parser.add_argument("--cases", default=None, help="explicit list, e.g. S01,S03; the lock applies")
    parser.add_argument("--split", default="dev", choices=("dev", "test", "all"))
    parser.add_argument("--include-reserve", action="store_true", help="adds R05; needs --unlock-test")
    parser.add_argument("--arms", default="baseline,advanced")
    parser.add_argument("--seeds", default="1,2,3")
    parser.add_argument("--mode", default="live", choices=("live", "replay"))
    parser.add_argument("--approve", default="auto", choices=("auto", "ask"))
    parser.add_argument("--jobs", type=int, default=None, help="default 4 live, 1 replay")
    parser.add_argument("--timeout", type=int, default=None, help="seconds; default 900 / 1800 real")
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--unlock-test", action="store_true")
    parser.add_argument("--reason", default=None, help="required with --unlock-test; goes in the ledger")
    parser.add_argument("--adr", default=None, help="ADR number authorising a third live test sweep")
    parser.add_argument("--fail-fast", action="store_true")
    return parser


def _timing_scope(args: argparse.Namespace, cases: list[str], split_data: dict) -> tuple[bool, str]:
    """Whether this sweep is the one that may claim `results/timing.json`, and a scratch name."""
    arms = {a.strip() for a in args.arms.split(",") if a.strip()}
    full = arms == set(ARMS) and set(cases) >= set(cases_for(split_data, "all"))
    if not args.cases:
        return full, args.split
    digest = hashlib.sha256(",".join(sorted(cases)).encode("utf-8")).hexdigest()[:7]
    return full, f"cases-{digest}"


def sweep(args: argparse.Namespace) -> int:
    split_data = _load_split()
    cases = select_cases(split_data, args.split, args.cases, args.include_reserve)
    if not cases:
        raise Abort(1, "no cases selected")
    if args.mode == "live" and os.environ.get("ART30_REPRODUCIBLE") == "1":
        raise Abort(1, "ART30_REPRODUCIBLE=1 is the replay flag; it cannot be set on a live sweep")
    locked, ledger = _check_lock(args, cases, split_data)
    loaded = {case: _manifest(case) for case in cases}
    manifests = {case: value[0] for case, value in loaded.items()}
    _check_freeze(cases, manifests, split_data)
    cells = _plan(args, cases, manifests)
    if locked:
        _append_ledger(args, cases, ledger)
    jobs = args.jobs if args.jobs else (1 if args.mode == "replay" else 4)
    print(f"{len(cells)} runs · {len(cases)} cases · mode {args.mode} · jobs {jobs}")

    def finish(cell: Cell, outcome: tuple[int, str, bool, float]) -> dict:
        row = _finish(cell, outcome, manifests[cell.case], loaded[cell.case][1])
        metrics = row["metrics"]
        print(f"{cell.arm:<9}{cell.case:<5}s{cell.seed}  {str(row['end'].get('stop_condition')):<17}"
              f"f1 {metrics['f1']:.3f}  fs {metrics['false_safe']}"
              f"  ${float(metrics['run']['cost_usd'] or 0):.2f}  {row['wall_s']}s")
        return row

    rows = _run_cells(cells, jobs, finish, bool(args.fail_fast))
    _failure_index(trace_root(args.out))
    _identity_check(rows)
    full, tag = _timing_scope(args, cases, split_data)
    timing = _write_timing(args.mode, rows, full, tag)
    accepted = sum(1 for r in rows if r["end"].get("stop_condition") == "accepted")
    print(f"{len(rows)} runs · {accepted} accepted · {len(rows) - accepted} failed")
    if timing:
        print(f"wrote {_relative(timing)}")
    # ADR 0003 item 6: replay fails loudly on a miss, which is its own exit code (section 5.5).
    return 5 if any(r["end"].get("stop_condition") == "replay_miss" for r in rows) else 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return sweep(args)
    except Abort as exc:
        print(str(exc), file=sys.stderr)
        return exc.code


if __name__ == "__main__":  # pragma: no cover - module entry point
    sys.exit(main())
