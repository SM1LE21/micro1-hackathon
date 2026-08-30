"""One child process per run: the spawn, the directory it writes, the registry.

The command is the one `evals/harness/cells.py` builds -- same argv list, same
`ART30_TRACE_DIR` seam, same unlock for a replay of a test case -- with
`--approve file`, an `--out` under `results/web/`, which is git-ignored, and the
brain the person picked. No shell string is ever built: the child owns the run and
this module owns the process. The registry is a `Run` per child started here plus
every `results/web/<run_id>/` on disk, which `adopt` opens, so a restart keeps it.
"""

from __future__ import annotations

import itertools
import json
import os
import re
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
RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")   # a directory name, never a path

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
    brain: str = "api"
    model: str | None = None


def runs_root() -> Path:
    """`results/web/` inside a checkout. Installed as a wheel there is none to write
    into, so `ART30_WEB_DIR` names it and the fallback is where the person stands."""
    raw = os.environ.get("ART30_WEB_DIR")
    if raw:
        return Path(raw).expanduser()
    if SPLIT_FILE.is_file():
        return RUNS_ROOT
    return Path.cwd() / "art30-out" / "web"


def new_run_id(arm: str, case: str, seed: int) -> str:
    """`<arm>-<case>-s<seed>-` and six hex of clock and counter: two runs started in
    the same microsecond differ, with no randomness needed to say so."""
    raw = (time.time_ns() // 1000) ^ (next(_counter) << 44)
    return f"{arm}-{case}-s{seed}-{raw & 0xFFFFFF:06x}"


def command(repo: Path, arm: str, case: str, seed: int, mode: str, out: Path,
            brain: str = "api", model: str | None = None) -> list[str]:
    """The harness's own argv, two flags longer (`cells.launch`). `--brain` always, so
    what the page showed is what the child is told rather than whatever `art30.toml`
    says; `--model` only when a person typed one, because empty means the brain's own
    default and the CLI routes that flag by the brain it resolved (ADR 0008 item 1)."""
    argv = [sys.executable, "-m", "art30.cli", "scan", str(repo), "--arm", arm,
            "--case", case, "--seed", str(seed), "--mode", mode,
            "--approve", APPROVE, "--out", str(out), "--brain", brain]
    return argv + (["--model", model] if model else [])


def environment(directory: Path, mode: str) -> dict[str, str]:
    env = dict(os.environ)
    env["ART30_TRACE_DIR"] = str(directory / "traces")
    # The server writes under its own run directory and nowhere else. Recording is the
    # one inherited variable that would break that: `art30/llm.py` clears the cache slot
    # before writing it, so `ART30_RECORD=1` overwrites the corpus the demo replays.
    env["ART30_RECORD"] = "0"
    env["ART30_CACHE_DIR"] = str(catalog.cache_root())
    if mode == "replay":
        # A recorded test case replays without spending a live sweep: the same
        # reading of the lock evals/split.yaml records (policy, replay_counts…).
        env["ART30_UNLOCK_TEST"] = "1"
        # and it replays at the recorded settings, not the user's files (ADR 0008 item 5)
        env["ART30_IGNORE_SETTINGS_FILES"] = "1"
    return env


def spawn(repo: Path, arm: str, case: str, seed: int, mode: str, brain: str = "api",
          model: str | None = None) -> Run:
    run_id = new_run_id(arm, case, seed)
    directory = runs_root() / run_id
    directory.mkdir(parents=True, exist_ok=True)
    argv = command(repo, arm, case, seed, mode, directory, brain, model)
    started = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    (directory / "run.json").write_text(json.dumps({
        "run_id": run_id, "case": case, "arm": arm, "mode": mode, "seed": seed,
        "repo": str(repo), "out": str(directory), "started_at": started,
        "brain": brain, "model": model, "command": argv,
    }, indent=2) + "\n", encoding="utf-8")
    log = (directory / LOG_NAME).open("wb")
    proc = subprocess.Popen(argv, cwd=REPO_ROOT, env=environment(directory, mode),
                            stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
    run = Run(run_id=run_id, case=case, arm=arm, mode=mode, seed=seed, repo=repo,
              dir=directory, started_at=started, proc=proc, log=log, brain=brain,
              model=model)
    with _lock:
        _runs[run_id] = run
    return run


def get(run_id: str) -> Run | None:
    with _lock:
        found = _runs.get(run_id)
    return found if found is not None else adopt(run_id)


class Exited:
    """Where the child process would be, for a run this server did not start."""
    def poll(self) -> int:
        return 0


def adopt(run_id: str) -> Run | None:
    """A finished run under `results/web/`, wrapped as a `Run` so the stream, the record
    and the source routes read it as a live one. Nothing is spawned (ADR 0008 item 4)."""
    if not RUN_ID.fullmatch(run_id):
        return None
    directory = runs_root() / run_id
    try:
        data = json.loads((directory / "run.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    run = Run(run_id=run_id, case=str(data.get("case") or ""),
              arm=str(data.get("arm") or ""), mode=str(data.get("mode") or ""),
              seed=int(data.get("seed") or 1), repo=Path(str(data.get("repo") or directory)),
              dir=directory, started_at=str(data.get("started_at") or ""),
              proc=Exited(), log=None, brain=str(data.get("brain") or "api"),
              model=data.get("model"))
    with _lock:
        return _runs.setdefault(run_id, run)


def listing() -> list[Run]:
    with _lock:
        return list(_runs.values())


def repo_root_of(run: Run) -> Path:
    """The jail for the source endpoint: the root `run.json` recorded at the spawn."""
    return run.repo


# --- the trace, the gate, the outcome --------------------------------------------------


def trace_in(directory: Path) -> Path | None:
    """The single `*.jsonl` the child writes under its own trace directory."""
    traces = directory / "traces"
    if not traces.is_dir():
        return None
    found = sorted(traces.rglob("*.jsonl"))
    return found[0] if found else None


def trace_path(run: Run) -> Path | None:
    return trace_in(run.dir)


def trace_line(path: Path | None, kind: str, last: bool = False) -> dict | None:
    """The first, or the last, line of one type in a trace."""
    if path is None:
        return None
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    lines = text.splitlines()
    for line in (reversed(lines) if last else lines):
        if f'"{kind}"' not in line:
            continue
        try:
            found = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(found, dict) and found.get("type") == kind:
            return found
    return None


def cost_source(brain: str, start: dict | None) -> str:
    """What the cost figure is: the API brain's measured dollars, or a local brain's
    estimate from the tokens its CLI reported (ADR 0008 item 3). A trace wins."""
    named = str((start or {}).get("cost_source") or "")
    return named or ("measured" if brain == "api" else "cli_estimate")


def gate_paths(run: Run) -> tuple[Path, Path]:
    folder = run.dir / GATE_DIR
    return folder / REQUEST_NAME, folder / DECISION_NAME


def gate_waiting(run: Run) -> bool:
    request, decision = gate_paths(run)
    return request.is_file() and not decision.is_file()


def stop_condition(run: Run) -> str:
    """What ended the run, including the two the trace cannot carry itself."""
    end = trace_line(trace_path(run), "run_end", last=True)
    if end and end.get("stop_condition"):
        return str(end["stop_condition"])
    return "cancelled" if run.cancelled else "crashed"


def status(run: Run) -> str:
    if run.proc.poll() is None:
        return "gate_waiting" if gate_waiting(run) else "running"
    condition = stop_condition(run)
    return "accepted" if condition == "accepted" else f"failed:{condition}"


def state(run: Run) -> dict:
    start = trace_line(trace_path(run), "run_start")
    return {"run_id": run.run_id, "case": run.case, "arm": run.arm, "mode": run.mode,
            "seed": run.seed, "started_at": run.started_at, "status": status(run),
            "exit_code": run.proc.poll(), "brain": run.brain,
            "cost_source": cost_source(run.brain, start)}


def write_decision(run: Run, approved: bool, edits: dict[str, str]) -> None:
    """The gate's shape: `approved`, and one `stores.<name>.recipient_kind` per edit
    (advanced/gate.py). The child validates the keys again."""
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
    if run.log is None:            # an adopted run has no handle of ours to close
        return
    try:
        run.log.close()           # type: ignore[union-attr]
    except OSError:
        pass


def reap() -> None:
    """Close the log of every child that has exited. Called on each listing."""
    for run in listing():
        if run.proc.poll() is not None:
            _close(run)
