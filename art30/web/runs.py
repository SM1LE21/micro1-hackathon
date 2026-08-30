"""One child process per run: the spawn, the directory it writes, the registry.

The command is the one `evals/harness/cells.py` builds -- same argv list, same
`ART30_TRACE_DIR` seam, same unlock for a replay of a test case -- with
`--approve file` and an `--out` under `results/web/`, which is git-ignored. No
shell string is ever built, and nothing here reads the model or the record: the
child owns the run and this module owns the process.
"""

from __future__ import annotations

import itertools
import json
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from art30.web import catalog

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNS_ROOT = REPO_ROOT / "results" / "web"
SPLIT_FILE = REPO_ROOT / "evals" / "split.yaml"     # the checkout, as opposed to a wheel
ARMS = ("baseline", "advanced")
MODES = ("live", "replay")
APPROVE = "file"                     # ADR 0007: the gate the website can answer
GATE_DIR, REQUEST_NAME, DECISION_NAME = "gate", "request.json", "decision.json"
KILL_AFTER_S = 5.0
LOG_NAME = "stdout.log"

_counter = itertools.count(1)
_lock = threading.Lock()
_runs: "dict[str, Run]" = {}


@dataclass
class Run:
    run_id: str
    case: str
    arm: str
    mode: str
    seed: int
    repo: Path
    dir: Path
    started_at: str
    proc: subprocess.Popen
    log: object
    cancelled: bool = False


def runs_root() -> Path:
    """`results/web/` inside the checkout. Installed as a wheel there is no checkout to
    write into, so `ART30_WEB_DIR` names the directory and the fallback is the one the
    person is standing in."""
    raw = os.environ.get("ART30_WEB_DIR")
    if raw:
        return Path(raw).expanduser()
    if SPLIT_FILE.is_file():
        return RUNS_ROOT
    return Path.cwd() / "art30-out" / "web"


def _token() -> str:
    """Six hex from the clock and a counter. Two runs in the same microsecond
    still differ, and no randomness is needed to say so."""
    raw = (time.time_ns() // 1000) ^ (next(_counter) << 44)
    return f"{raw & 0xFFFFFF:06x}"


def new_run_id(arm: str, case: str, seed: int) -> str:
    return f"{arm}-{case}-s{seed}-{_token()}"


def command(repo: Path, arm: str, case: str, seed: int, mode: str, out: Path) -> list[str]:
    """The harness's own argv, one flag longer (`cells.launch`)."""
    return [sys.executable, "-m", "art30.cli", "scan", str(repo), "--arm", arm,
            "--case", case, "--seed", str(seed), "--mode", mode,
            "--approve", APPROVE, "--out", str(out)]


def environment(directory: Path, mode: str) -> dict[str, str]:
    env = dict(os.environ)
    env["ART30_TRACE_DIR"] = str(directory / "traces")
    # The server writes under its own run directory and nowhere else. Recording is the
    # one inherited variable that would break that: `art30/llm.py` clears the cache slot
    # before writing it, so a live run under `ART30_RECORD=1` would overwrite the corpus
    # the offline demo replays from (docs/runbook-sweeps.md).
    env["ART30_RECORD"] = "0"
    env["ART30_CACHE_DIR"] = str(catalog.cache_root())
    if mode == "replay":
        # A recorded test case replays without spending a live sweep: the same
        # reading of the lock evals/split.yaml records (policy, replay_counts…).
        env["ART30_UNLOCK_TEST"] = "1"
    return env


def spawn(repo: Path, arm: str, case: str, seed: int, mode: str) -> Run:
    run_id = new_run_id(arm, case, seed)
    directory = runs_root() / run_id
    directory.mkdir(parents=True, exist_ok=True)
    argv = command(repo, arm, case, seed, mode, directory)
    started = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    (directory / "run.json").write_text(json.dumps({
        "run_id": run_id, "case": case, "arm": arm, "mode": mode, "seed": seed,
        "repo": str(repo), "out": str(directory), "started_at": started,
        "command": argv,
    }, indent=2) + "\n", encoding="utf-8")
    log = (directory / LOG_NAME).open("wb")
    proc = subprocess.Popen(argv, cwd=REPO_ROOT, env=environment(directory, mode),
                            stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
    run = Run(run_id=run_id, case=case, arm=arm, mode=mode, seed=seed, repo=repo,
              dir=directory, started_at=started, proc=proc, log=log)
    with _lock:
        _runs[run_id] = run
    return run


def get(run_id: str) -> Run | None:
    with _lock:
        return _runs.get(run_id)


def listing() -> list[Run]:
    with _lock:
        return list(_runs.values())


def repo_root_of(run: Run) -> Path:
    """The jail for the source endpoint, read back from what the spawn recorded."""
    try:
        data = json.loads((run.dir / "run.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return run.repo
    return Path(str(data.get("repo") or run.repo))


# --- the trace, the gate, the outcome --------------------------------------------------


def trace_path(run: Run) -> Path | None:
    """The single `*.jsonl` the child writes under its own trace directory."""
    traces = run.dir / "traces"
    if not traces.is_dir():
        return None
    found = sorted(traces.rglob("*.jsonl"))
    return found[0] if found else None


def run_end(run: Run) -> dict | None:
    path = trace_path(run)
    if path is None:
        return None
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    for line in reversed(text.splitlines()):
        if '"run_end"' not in line:
            continue
        try:
            found = json.loads(line)
        except json.JSONDecodeError:
            return None
        if isinstance(found, dict) and found.get("type") == "run_end":
            return found
    return None


def gate_paths(run: Run) -> tuple[Path, Path]:
    folder = run.dir / GATE_DIR
    return folder / REQUEST_NAME, folder / DECISION_NAME


def gate_waiting(run: Run) -> bool:
    request, decision = gate_paths(run)
    return request.is_file() and not decision.is_file()


def stop_condition(run: Run) -> str:
    """What ended the run, including the two the trace cannot carry itself."""
    end = run_end(run)
    if end and end.get("stop_condition"):
        return str(end["stop_condition"])
    return "cancelled" if run.cancelled else "crashed"


def status(run: Run) -> str:
    if run.proc.poll() is None:
        return "gate_waiting" if gate_waiting(run) else "running"
    condition = stop_condition(run)
    return "accepted" if condition == "accepted" else f"failed:{condition}"


def state(run: Run) -> dict:
    return {"run_id": run.run_id, "case": run.case, "arm": run.arm, "mode": run.mode,
            "seed": run.seed, "started_at": run.started_at, "status": status(run),
            "exit_code": run.proc.poll()}


def write_decision(run: Run, approved: bool, edits: dict[str, str]) -> None:
    """The gate's documented shape: `approved`, and one `stores.<name>.recipient_kind`
    per edit (advanced/gate.py, ADR 0007). The child validates the keys again."""
    request, decision = gate_paths(run)
    payload = {"approved": bool(approved),
               "edits": {f"stores.{name}.recipient_kind": kind
                         for name, kind in sorted((edits or {}).items())}}
    decision.parent.mkdir(parents=True, exist_ok=True)
    scratch = decision.with_suffix(".part")
    scratch.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    scratch.replace(decision)          # the child polls: it never reads half a file


def tail(run: Run, lines: int = 3) -> str:
    try:
        text = (run.dir / LOG_NAME).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return "\n".join(text.splitlines()[-lines:]).strip()


def cancel(run: Run) -> bool:
    """SIGTERM now, SIGKILL five seconds later, from a thread so the request returns."""
    if run.proc.poll() is not None:
        return False
    run.cancelled = True
    run.proc.terminate()

    def _kill() -> None:
        try:
            run.proc.wait(KILL_AFTER_S)
        except subprocess.TimeoutExpired:
            run.proc.kill()
        _close(run)

    threading.Thread(target=_kill, daemon=True).start()
    return True


def _close(run: Run) -> None:
    try:
        run.log.close()           # type: ignore[union-attr]
    except OSError:
        pass


def reap() -> None:
    """Close the log of every child that has exited. Called on each listing."""
    for run in listing():
        if run.proc.poll() is not None:
            _close(run)
