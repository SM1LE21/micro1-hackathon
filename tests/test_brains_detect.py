"""`art30.brains.detect()` against fake `claude` and `codex` executables on a temp PATH.

The real CLIs are not called here, and the two things this code must never do —
crash on a machine that has neither, keep anything out of a login answer beyond
the boolean — are the cases below (ADR 0008 item 6).
"""

from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from art30 import brains

EMAIL = "someone@example.com"
CLAUDE_STATUS = {"loggedIn": True, "authMethod": "claude.ai", "email": EMAIL,
                 "orgName": "Someone's Organization", "subscriptionType": "max"}


def fake(directory: Path, name: str, version: str, status: str, status_code: int = 0) -> Path:
    """A binary that answers `--version` and its own login command, and nothing else."""
    path = directory / name
    path.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = "--version" ]; then printf %s\\\\n ' + repr(version).replace("'", '"') + "; exit 0; fi\n"
        "printf %s\\\\n " + json.dumps(status) + f"; exit {status_code}\n",
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


@pytest.fixture()
def bindir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    directory = tmp_path / "bin"
    directory.mkdir()
    monkeypatch.setenv("PATH", str(directory))
    return directory


def test_neither_cli_installed_is_two_negative_answers(bindir: Path) -> None:
    found = brains.detect()
    assert set(found) == {"claude", "codex"}
    for name, state in found.items():
        assert state == {"name": name, "label": brains.BRAINS[name]["label"], "installed": False,
                         "path": None, "version": None, "logged_in": None,
                         "detail": "not installed"}


def test_both_clis_report_a_version_and_a_login_state(bindir: Path) -> None:
    fake(bindir, "claude", "2.1.251 (Claude Code)", json.dumps(CLAUDE_STATUS))
    fake(bindir, "codex", "codex-cli 0.148.0", f"Logged in using ChatGPT ({EMAIL})")

    found = brains.detect()

    assert found["claude"]["installed"] and found["claude"]["path"] == str(bindir / "claude")
    assert found["claude"]["version"] == "2.1.251 (Claude Code)"
    assert found["claude"]["logged_in"] is True and found["claude"]["detail"] == "logged in"
    assert found["codex"]["version"] == "codex-cli 0.148.0"
    assert found["codex"]["logged_in"] is True
    assert found["claude"]["label"] == "Claude (your login)"   # never "Claude Code"


def test_nothing_of_the_account_survives_the_detection(bindir: Path) -> None:
    """The login answers carry an email, an organisation and a plan. Only the boolean
    may come out: this is the dictionary the CLI and the website print."""
    fake(bindir, "claude", "2.1.251", json.dumps(CLAUDE_STATUS))
    fake(bindir, "codex", "codex-cli 0.148.0", f"Logged in using ChatGPT ({EMAIL})")

    serialised = json.dumps(brains.detect())

    assert EMAIL not in serialised and "Organization" not in serialised
    assert "max" not in serialised and "ChatGPT" not in serialised


def test_a_logged_out_cli_says_so_and_an_unreadable_answer_says_nothing(bindir: Path) -> None:
    fake(bindir, "claude", "2.1.251", "not JSON at all")
    fake(bindir, "codex", "codex-cli 0.148.0", "Not logged in. Run codex login.", status_code=1)

    found = brains.detect()

    assert found["codex"]["logged_in"] is False and found["codex"]["detail"] == "not logged in"
    assert found["claude"]["logged_in"] is None
    assert found["claude"]["detail"] == "installed; login state unknown"


def test_a_cli_that_hangs_or_fails_is_not_an_exception(bindir: Path) -> None:
    """A `--version` that never returns must not hold a page or a scan open."""
    (bindir / "claude").write_text("#!/bin/sh\nsleep 30\n", encoding="utf-8")
    (bindir / "claude").chmod(0o755)
    (bindir / "codex").write_text("#!/bin/sh\nexit 9\n", encoding="utf-8")
    (bindir / "codex").chmod(0o755)

    calls: list[list[str]] = []

    def runner(command, **kwargs):
        calls.append(list(command))
        assert kwargs["timeout"] == brains.TIMEOUT_S
        raise TimeoutError("would have hung")

    found = brains.detect(runner)

    assert [c[1] for c in calls] == ["--version", "auth", "--version", "login"]
    assert found["claude"]["installed"] and found["claude"]["version"] is None
    assert found["claude"]["logged_in"] is None
    (bindir / "claude").unlink()                        # the sleeping one, out of the way
    assert brains.detect()["codex"]["version"] is None   # exit 9 is not a version
