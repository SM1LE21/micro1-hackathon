"""What the two local brains need before they can run: is the CLI here, and is it logged in.

`detect()` runs `claude --version` / `codex --version` and each CLI's own login
command. It reads a version string and one boolean out of them and keeps nothing
else: no account, no email, no token. art30 never stores or asks for those
credentials (ADR 0008 item 6), so nothing here may put them in a page, a trace or
a log line.

Safe on a machine with neither CLI installed: a missing binary, a timeout or a
command that answers in a shape nobody expected all come back as "no".
"""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import Callable

TIMEOUT_S = 5
VERSION_CHARS = 80
# One entry per brain: the binary, its login command, and how that command answers.
BRAINS: dict[str, dict] = {
    "claude": {"login": ("auth", "status"), "format": "json",
               "label": "Claude (your login)"},
    "codex": {"login": ("login", "status"), "format": "text", "label": "Codex (your login)"},
}
LOGGED_IN_WORDS = ("logged in", "signed in")
NOT_WORDS = ("not logged in", "not signed in", "no credentials", "please run")

State = dict[str, object]


def _run(command: list[str], runner: Callable | None = None) -> tuple[int, str] | None:
    """(returncode, stdout+stderr), or None when the command could not be run at all."""
    call = runner or subprocess.run
    try:
        done = call(command, capture_output=True, text=True, timeout=TIMEOUT_S, check=False)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    out = f"{getattr(done, 'stdout', '') or ''}{getattr(done, 'stderr', '') or ''}"
    return int(getattr(done, "returncode", 1) or 0), out


def _version(binary: str, runner: Callable | None) -> str | None:
    answer = _run([binary, "--version"], runner)
    if answer is None or answer[0] != 0:
        return None
    line = answer[1].strip().splitlines()[0].strip() if answer[1].strip() else ""
    return line[:VERSION_CHARS] or None


def _logged_in_json(text: str) -> bool | None:
    """`claude auth status` as JSON. Only `loggedIn` is read; the rest is an account."""
    try:
        data = json.loads(text[text.index("{"): text.rindex("}") + 1])
    except (ValueError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    for holder in (data, data.get("account"), data.get("auth")):
        if isinstance(holder, dict):
            for name in ("loggedIn", "logged_in", "isLoggedIn"):
                if isinstance(holder.get(name), bool):
                    return bool(holder[name])
    return None


def _logged_in_text(text: str) -> bool | None:
    """`codex login status` in prose. The words, never the line: the line names an account."""
    lowered = text.lower()
    if any(word in lowered for word in NOT_WORDS):
        return False
    if any(word in lowered for word in LOGGED_IN_WORDS):
        return True
    return None


def _login(binary: str, spec: dict, runner: Callable | None) -> bool | None:
    """None when the CLI answered in a shape this code does not know: an unknown
    state is not a "no", and a brain that reports one is left to the CLI's own error."""
    answer = _run([binary, *spec["login"]], runner)
    if answer is None:
        return None
    return _logged_in_json(answer[1]) if spec["format"] == "json" else _logged_in_text(answer[1])


def detect(runner: Callable | None = None) -> dict[str, State]:
    """One entry per local brain: installed, where, which version, logged in.

    `logged_in` is `None` when the CLI is there but did not say either way, which
    is not the same as a "no" and is not printed as one. `runner` replaces
    `subprocess.run` in the tests; nothing else may inject a command.
    """
    found: dict[str, State] = {}
    for name, spec in BRAINS.items():
        path = shutil.which(name)
        if path is None:
            found[name] = {"name": name, "label": spec["label"], "installed": False,
                           "path": None, "version": None, "logged_in": None,
                           "detail": "not installed"}
            continue
        version = _version(name, runner)
        logged_in = _login(name, spec, runner)
        detail = {True: "logged in", False: "not logged in"}.get(
            logged_in, "installed; login state unknown")
        found[name] = {"name": name, "label": spec["label"], "installed": True, "path": path,
                       "version": version, "logged_in": logged_in, "detail": detail}
    return found
