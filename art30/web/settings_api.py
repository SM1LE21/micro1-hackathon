"""`/api/settings`: the settings layer and the two local brains, over HTTP.

One loader answers the CLI, the harness and this page (ADR 0008 item 5), so this
module reads and writes through `art30.settings` and owns none of it. The API key
is the one value that goes in and never comes back: `POST` hands it to
`settings.write_secret`, and every read reports `present` or `absent`.

`detect()` shells out to two CLIs, so its answer is held for thirty seconds and
`?refresh=1` is how a person who has just logged in gets a new one.
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Any

from art30 import settings
from art30.brains import built, detect
from art30.web import catalog

# ADR 0008 item 6, verbatim. Shown wherever a local brain is selected; the page
# renders this string rather than a copy of it.
NOTE = ("Local brains run the `claude` / `codex` command already installed and logged in"
        " on this machine. art30 never stores or asks for those credentials; if the CLI is"
        " not logged in, the run fails with the CLI's own login error. Anthropic does not"
        " allow third parties to offer claude.ai login or rate limits inside their"
        " products; this tool does not — it runs your own CLI on your own machine.")

DETECT_TTL_S = 30.0
_detect_lock = threading.Lock()
_detected: tuple[float, dict] | None = None


def paths() -> tuple[Path, Path]:
    """The project root and the home directory every settings file is resolved against.

    The one seam: a test moves both under `tmp_path`, so no file belonging to the
    person running the suite is read, written or reported."""
    return catalog.project_root(), Path(os.environ.get("HOME") or Path.home())


def _error(status: int, message: str) -> tuple[int, dict]:
    return status, {"error": message}


# --- the brains -------------------------------------------------------------------------


def forget_brains() -> None:
    """Drop the cached detection. Called by `?refresh=1` and by the tests."""
    global _detected
    with _detect_lock:
        _detected = None


def brains(refresh: bool = False) -> dict:
    """`detect()`, at most once every thirty seconds.

    Under the lock rather than beside it: two requests arriving together would
    otherwise both shell out to two CLIs to learn the same thing. Each row is
    stamped with `built`: a CLI can be installed and logged in and still have no
    driver in `art30/brains/driver.py`, and that is a third way to be unable to
    run."""
    global _detected
    with _detect_lock:
        now = time.monotonic()
        if not refresh and _detected is not None and now - _detected[0] < DETECT_TTL_S:
            return _detected[1]
        ready = built()
        found = {name: (dict(row, built=name in ready) if isinstance(row, dict) else row)
                 for name, row in detect().items()}
        _detected = (now, found)
        return found


def logged_in(brain: str) -> bool:
    state = brains().get(brain) or {}
    return state.get("logged_in") is True


def refusal(brain: str) -> str | None:
    """Why a local brain cannot run, in the words the toggle shows, or None."""
    state = brains().get(brain)
    if state is None:
        return f"{brain} is not a local brain"
    label = str(state.get("label") or brain)
    if not state.get("installed"):
        return f"{label} is not installed on this machine, so it cannot run anything here."
    if state.get("logged_in") is not True:
        return (f"{label} is installed but {str(state.get('detail'))}."
                " Log the CLI in from a terminal, then press Refresh.")
    if not state.get("built"):
        return f"{label} is logged in, but art30 has no driver for it yet."
    return None


# --- reading ----------------------------------------------------------------------------


def read_settings() -> settings.Settings:
    root, home = paths()
    return settings.read(project_root=root, home=home)


def index(query: dict | None = None) -> tuple[int, dict]:
    """Every key with the layer it came from, both brains, the three files, the note."""
    refresh = ((query or {}).get("refresh") or ["0"])[0] == "1"
    try:
        resolved = read_settings()
    except ValueError as exc:      # a settings file with an unknown key names itself
        return _error(400, str(exc))
    return 200, {
        "keys": settings.describe(resolved),
        "brains": brains(refresh),
        "files": {"user": str(resolved.files["user"]),
                  "project": str(resolved.files["project"]),
                  "dotenv": str(resolved.files[settings.DOTENV_NAME])},
        "note": NOTE,
    }


def _scope(raw: Any) -> tuple[str, tuple[int, dict] | None]:
    scope = str(raw or "project")
    if scope not in settings.SCOPES:
        return scope, _error(400, f"scope must be one of {', '.join(settings.SCOPES)},"
                                  f" got {scope!r}")
    return scope, None


def _key(raw: Any) -> tuple[settings.Key | None, tuple[int, dict] | None]:
    name = str(raw or "").strip()
    if not name:
        return None, _error(400, "name the setting in `key`")
    try:
        return settings.key_for(name), None
    except ValueError as exc:
        return None, _error(400, str(exc))


# --- writing ----------------------------------------------------------------------------


def write(body: dict) -> tuple[int, dict]:
    """One key into one file. The answer names the file and never the value."""
    if not isinstance(body, dict):
        return _error(400, "the request body must be a JSON object")
    key, refusal_ = _key(body.get("key"))
    if refusal_ is not None:
        return refusal_
    scope, refusal_ = _scope(body.get("scope"))
    if refusal_ is not None:
        return refusal_
    assert key is not None
    root, home = paths()
    value = body.get("value")
    try:
        if key.secret:
            # The one value the answer never carries. Two shapes are refused here
            # rather than in the loader: anything but text, which would be written
            # as a Python repr; and more than one line by any of the separators
            # `str.splitlines` knows, which would put a second, unrelated
            # assignment into `.env` under the name of a write that shows nothing.
            if not isinstance(value, str):
                return _error(400, f"{key.env} is a single line of text")
            if len(value.splitlines()) > 1:
                return _error(400, f"{key.env} must be a single non-empty line")
            path = settings.write_secret(key.name, value, project_root=root)
        else:
            path = settings.write(key.name, value, scope=scope, project_root=root, home=home)
    except ValueError as exc:
        return _error(400, str(exc))
    except OSError as exc:
        return _error(500, f"cannot write the settings file: {exc.strerror or exc}")
    return 200, {"key": key.name, "written_to": str(path), "present": True}


def unset(name: str, query: dict | None = None) -> tuple[int, dict]:
    """Drop one key from the file that holds it; the layer below it takes over."""
    key, refusal_ = _key(name)
    if refusal_ is not None:
        return refusal_
    scope, refusal_ = _scope(((query or {}).get("scope") or ["project"])[0])
    if refusal_ is not None:
        return refusal_
    assert key is not None
    root, home = paths()
    try:
        path = settings.unset(key.name, scope=scope, project_root=root, home=home)
        resolved = read_settings()
    except ValueError as exc:
        return _error(400, str(exc))
    except OSError as exc:
        return _error(500, f"cannot write the settings file: {exc.strerror or exc}")
    present = resolved.secret_present if key.secret \
        else resolved.sources.get(key.name, "default") != "default"
    return 200, {"key": key.name, "removed_from": str(path), "present": present}
