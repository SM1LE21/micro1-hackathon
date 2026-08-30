"""The JSON API: validation, then a call into `runs.py` or a file off disk.

Every handler returns `(status, payload)` and raises nothing at the socket, so
`server.py` stays a routing table. Errors are `{"error": "..."}` with the status
that fits; the reason is the one a person can act on, never a traceback.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from art30 import settings, tools
from art30.web import catalog, runs, settings_api

RESULTS = catalog.REPO_ROOT / "results"
METRICS = RESULTS / "metrics.json"
REPORT = RESULTS / "report.md"
NO_RESULTS = ("No sweep has been scored yet. Run `make eval` for a live sweep, or"
              " `make eval-replay` to re-score the recorded one (docs/runbook-sweeps.md).")
GATE_KINDS = ("unknown", "internal", "processor", "external_controller")
ARTIFACTS = {"record": ("record.json", "application/json"),
             "record.md": ("record.md", "text/markdown; charset=utf-8"),
             "record.html": ("record.html", "text/html; charset=utf-8")}
CONTEXT_MAX = 40
# The case id names a directory under results/web/: it stays a plain label.
CASE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def _cache_label() -> str:
    root = catalog.cache_root()
    return str(root.relative_to(catalog.REPO_ROOT)) if root.is_relative_to(catalog.REPO_ROOT) \
        else str(root)


def error(status: int, message: str) -> tuple[int, dict]:
    return status, {"error": message}


def cases() -> tuple[int, dict]:
    payload = {"cases": catalog.cases(), "live_enabled": catalog.live_enabled()}
    hint = catalog.missing_split()
    if hint is not None:
        payload["hint"] = hint            # an empty list with a reason beats an empty table
    return 200, payload


# --- starting a run ---------------------------------------------------------------------


def _fixture_owner(known: dict[str, dict], path: Path) -> str | None:
    """The case id a directory belongs to, so a fixture cannot be relabelled: the
    split lock (`start`) and the CLI's own both key on the case id, and `case` is a
    separate field in the body."""
    for row in known.values():
        candidate = catalog.REPO_ROOT / row["path"]
        try:
            if candidate.resolve() == path:
                return str(row["id"])
        except OSError:
            continue
    return None


def _target(body: dict) -> tuple[Path | None, str, tuple[int, dict] | None]:
    """`repo` is a case id or a directory inside the project. The case id also names
    the trace, and for a known fixture it is the fixture's own id, never the body's."""
    raw = str(body.get("repo") or "").strip()
    if not raw:
        return None, "", error(400, "name a case id or a repository path in `repo`")
    known = catalog.by_id()
    if raw in known:
        row = known[raw]
        path = catalog.REPO_ROOT / row["path"]
        if not path.is_dir():
            return None, "", error(400, f"the fixture for {raw} is not on disk at {row['path']}")
        return path, raw, None
    root = catalog.project_root()
    path = Path(raw)
    if not path.is_absolute():
        path = root / path
    if not path.is_dir():
        return None, "", error(400, f"no case and no directory called {raw}")
    path = path.resolve()
    if path == root:
        # The project root holds `.env`, and a run rooted there would make the
        # secrets file readable through `source`. A scan of the whole checkout was
        # never a case anyway.
        return None, "", error(400, "name a case or a repository inside the project,"
                                    " not the project root")
    if not path.is_relative_to(root):
        return None, "", error(400, f"{raw} is outside {root}; the website runs cases and"
                                    " repositories inside the project")
    owner = _fixture_owner(known, path)
    if owner is not None:
        return path, owner, None
    return path, str(body.get("case") or path.name), None


def start(body: dict) -> tuple[int, dict]:
    if not isinstance(body, dict):
        return error(400, "the request body must be a JSON object")
    arm = str(body.get("arm") or "advanced")
    mode = str(body.get("mode") or "replay")
    brain = str(body.get("brain") or "api")
    model = str(body.get("model") or "").strip() or None
    if arm not in runs.ARMS:
        return error(400, f"arm must be one of {', '.join(runs.ARMS)}")
    if mode not in runs.MODES:
        return error(400, f"mode must be one of {', '.join(runs.MODES)}")
    if brain not in settings.BRAINS:
        return error(400, f"brain must be one of {', '.join(settings.BRAINS)}")
    try:
        seed = int(body.get("seed") or 1)
    except (TypeError, ValueError):
        return error(400, "seed must be a whole number")
    repo, case, refusal = _target(body)
    if refusal is not None:
        return refusal
    if not CASE_ID.fullmatch(case):
        return error(400, "a case id is letters, digits, dot, dash and underscore")
    if mode == "live" and case in catalog.test_cases():
        return error(400, f"{case} is in the test split (evals/split.yaml), which is swept"
                          " live at most twice and only through the harness ledger."
                          " Replay is allowed.")
    refused = _brain_refusal(brain, mode, case, arm)
    if refused is not None:
        return refused
    assert repo is not None
    run = runs.spawn(repo, arm, case, seed, mode, brain, model)
    return 201, {"run_id": run.run_id, "status": "running", "brain": brain}


def _brain_refusal(brain: str, mode: str, case: str, arm: str) -> tuple[int, dict] | None:
    """What each brain needs before it can run: a key and a recording, or a login.

    A local brain replays nothing: its run went through somebody's own CLI and no
    response was recorded, so the page plays the saved trace back (ADR 0008 item 4)."""
    if brain != "api":
        if mode != "live":
            return error(400, f"the {brain} brain has no recorded responses to replay."
                              " Play back a finished run of it instead.")
        why = settings_api.refusal(brain)
        return error(400, why) if why else None
    if mode == "live" and not catalog.live_enabled():
        return error(400, "live runs need ANTHROPIC_API_KEY in the environment or in .env;"
                          " replay a recorded case instead")
    if mode == "replay" and arm not in catalog.replay_arms(case):
        return error(400, f"no recorded responses for {case}/{arm} under"
                          f" {_cache_label()}/{case}/{arm}/s1")
    return None


def listing() -> tuple[int, dict]:
    """The children this process owns, plus every other run directory on disk.

    Read on each call rather than at startup only, so a run finished by another
    server -- or by the CLI writing into the same place -- is in the list too."""
    runs.reap()
    rows = [runs.state(run) for run in runs.listing()]
    known = {row["run_id"] for row in rows}
    rows += [row for row in from_disk() if row["run_id"] not in known]
    rows.sort(key=lambda row: (str(row.get("started_at") or ""), str(row["run_id"])))
    return 200, {"runs": rows}


def from_disk() -> list[dict]:
    """Every run directory under `results/web/` this process did not start, adopted
    and then read through the same `state` a live child gets. The directory is the
    record of what ran here, so a restarted server still lists it."""
    root = runs.runs_root()
    found = sorted(root.iterdir()) if root.is_dir() else []
    adopted = [runs.adopt(directory.name) for directory in found if directory.is_dir()]
    return [runs.state(run) for run in adopted if run is not None]


def one(run_id: str) -> tuple[int, dict]:
    run = runs.get(run_id)
    if run is None:
        return error(404, f"no run called {run_id}")
    return 200, runs.state(run)


# --- the gate ----------------------------------------------------------------------------


def gate(run_id: str, body: dict) -> tuple[int, dict]:
    run = runs.get(run_id)
    if run is None:
        return error(404, f"no run called {run_id}")
    if not isinstance(body, dict) or not isinstance(body.get("approved"), bool):
        return error(400, "the decision needs `approved` as true or false")
    request, decision = runs.gate_paths(run)
    if not request.is_file():
        return error(409, "this run has not reached the gate yet")
    if decision.is_file():
        return error(410, "this gate was already answered")
    raw = body.get("edits") or {}
    if not isinstance(raw, dict):
        return error(400, "`edits` maps a store name to a recipient kind")
    bad = [f"{k}: {v}" for k, v in raw.items() if v not in GATE_KINDS]
    if bad:
        return error(400, f"recipient kind must be one of {' | '.join(GATE_KINDS)}"
                          f" ({'; '.join(sorted(bad))})")
    runs.write_decision(run, bool(body["approved"]), {str(k): str(v) for k, v in raw.items()})
    return 200, {"run_id": run.run_id, "approved": bool(body["approved"]),
                 "edits": {str(k): str(v) for k, v in raw.items()}}


def cancel(run_id: str) -> tuple[int, dict]:
    run = runs.get(run_id)
    if run is None:
        return error(404, f"no run called {run_id}")
    if not runs.cancel(run):
        return error(409, "this run has already finished")
    return 200, {"run_id": run.run_id, "status": "cancelling"}


# --- what the run wrote -------------------------------------------------------------------


def artifact(run_id: str, name: str) -> tuple[int, bytes, str]:
    """The renderer's own three files, byte for byte. Nothing here renders anything."""
    run = runs.get(run_id)
    if run is None:
        return 404, _json_error(f"no run called {run_id}"), "application/json"
    filename, content_type = ARTIFACTS[name]
    path = run.dir / filename
    if not path.is_file():
        return 404, _json_error(f"{filename} has not been written yet"), "application/json"
    return 200, path.read_bytes(), content_type


def _json_error(message: str) -> bytes:
    return json.dumps({"error": message}).encode("utf-8")


def source(run_id: str, query: dict) -> tuple[int, dict]:
    """A cited line and its neighbours, jailed to the repository the run read."""
    run = runs.get(run_id)
    if run is None:
        return error(404, f"no run called {run_id}")
    rel = str((query.get("path") or [""])[0])
    if not rel:
        return error(400, "name the file in `path`, relative to the repository root")
    try:
        line = int((query.get("line") or ["1"])[0])
        context = int((query.get("context") or ["3"])[0])
    except ValueError:
        return error(400, "`line` and `context` are whole numbers")
    root = runs.repo_root_of(run)
    try:
        path = tools.resolve(root, rel)
    except (tools.ToolError, ValueError) as exc:
        # ValueError: a NUL byte never reaches `realpath`, so the jail never rules on it.
        return error(403, str(exc))
    # The belt to `_target`'s braces: the key goes into `.env` through POST
    # /api/settings and is never read back, and this endpoint is not the way out.
    if path.name == settings.DOTENV_NAME:
        return error(403, "the secrets file is not source")
    if not path.is_file():
        return error(404, f"no file at {rel}")
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return error(404, f"cannot read {rel}: {exc.strerror or 'unreadable'}")
    context = max(0, min(context, CONTEXT_MAX))
    lines = text.splitlines()
    if not 1 <= line <= len(lines):
        return error(404, f"{rel} has {len(lines)} lines; there is no line {line}")
    start = max(1, line - context)
    end = min(len(lines), line + context)
    return 200, {"path": rel, "line": line, "start": start,
                 "lines": [[n, lines[n - 1]] for n in range(start, end + 1)]}


def results() -> tuple[int, dict]:
    if not METRICS.is_file():
        return 200, {"available": False, "hint": NO_RESULTS}
    try:
        metrics = json.loads(METRICS.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 200, {"available": False, "hint": f"{METRICS.name} is unreadable. {NO_RESULTS}"}
    report = REPORT.read_text(encoding="utf-8") if REPORT.is_file() else None
    return 200, {"available": True, "metrics": metrics, "report": report}
