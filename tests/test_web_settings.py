"""`/api/settings`, the brain detection behind it, and the registry read off disk.

Everything here runs against the real loopback server with the settings layer
pointed at `tmp_path`: `settings_api.paths` is the one seam, so no file belonging
to the person running the suite is read, written or reported. `detect()` is
replaced by a counter, because a test must not depend on which CLIs happen to be
installed on the machine it runs on.

The property this file exists for is the API key: it goes in and never comes
back. Two assertions hold it -- the write's own answer, and the whole settings
document, are scanned for the characters that were sent.
"""

from __future__ import annotations

import json
import os
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from art30 import settings
from art30.brains import built
from art30.web import runs
from art30.web import server as server_mod
from art30.web import settings_api
from test_web_server import call, raw

SECRET = "sk-ant-not-a-real-key-0123456789"
NOTE_OPENING = "Local brains run the `claude` / `codex` command already installed"
LOGGED_IN = {
    "claude": {"name": "claude", "label": "Claude (your login)", "installed": True,
               "path": "/usr/local/bin/claude", "version": "claude 2.0.1",
               "logged_in": True, "detail": "logged in"},
    "codex": {"name": "codex", "label": "Codex (your login)", "installed": False,
              "path": None, "version": None, "logged_in": None, "detail": "not installed"},
}
LOGGED_OUT = {
    "claude": dict(LOGGED_IN["claude"], logged_in=False, detail="not logged in"),
    "codex": LOGGED_IN["codex"],
}
# Both CLIs here and answering "logged in": the state the build machine is in, and
# the one that says nothing about whether art30 can drive either of them.
BOTH_LOGGED_IN = {
    "claude": LOGGED_IN["claude"],
    "codex": {"name": "codex", "label": "Codex (your login)", "installed": True,
              "path": "/usr/local/bin/codex", "version": "codex-cli 0.148.0",
              "logged_in": True, "detail": "logged in"},
}
TRACE = [
    {"type": "run_start", "case": "D01", "arm": "advanced", "cost_source": "cli_estimate",
     "config": {"tool_budget": 60, "submit_budget": 5, "max_turns": 40, "brain": "claude"}},
    {"type": "step", "step": 1},
    {"type": "run_end", "stop_condition": "accepted", "steps": 1, "cost_usd": 0.0},
]
# An API run that never wrote an end line: killed, or still going somewhere else.
UNFINISHED = [{"type": "run_start", "case": "D01", "arm": "advanced",
               "config": {"tool_budget": 60, "submit_budget": 5}},
              {"type": "step", "step": 1}]


@pytest.fixture()
def web(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, settings_files):
    """The server, with both settings files and the runs directory under `tmp_path`."""
    for name in [key for key in os.environ if key.startswith("ART30_")]:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    root = tmp_path / "project"
    home = tmp_path / "home"
    root.mkdir()
    home.mkdir()
    monkeypatch.setattr(settings_api, "paths", lambda: (root, home))
    monkeypatch.setattr(settings_api, "detect", lambda *a, **k: LOGGED_IN)
    monkeypatch.setattr(runs, "RUNS_ROOT", tmp_path / "web")
    monkeypatch.setattr(runs, "_runs", {})
    settings_api.forget_brains()
    httpd = server_mod.build("127.0.0.1", 0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", root, home
    settings_api.forget_brains()
    httpd.shutdown()
    httpd.server_close()
    thread.join(timeout=5)


def delete(url: str) -> tuple[int, dict]:
    request = urllib.request.Request(url, method="DELETE")
    try:
        with urllib.request.urlopen(request, timeout=30) as answer:
            return answer.status, json.loads(answer.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def rows(payload: dict) -> dict[str, dict]:
    return {row["key"]: row for row in payload["keys"]}


# --- reading ------------------------------------------------------------------------------


def test_every_key_is_listed_with_its_layer_and_the_three_files_are_named(web) -> None:
    url, root, home = web
    status, payload = call(url + "/api/settings")
    assert status == 200
    assert [row["key"] for row in payload["keys"]] == [key.name for key in settings.KEYS]
    assert payload["files"] == {"user": str(home / ".config" / "art30" / "config.toml"),
                                "project": str(root / "art30.toml"),
                                "dotenv": str(root / ".env")}
    assert payload["note"].startswith(NOTE_OPENING)
    assert payload["brains"]["claude"]["label"] == "Claude (your login)"
    assert rows(payload)["brain"] == {
        "key": "brain", "value": "api", "source": "default", "default": "api",
        "allowed": ["api", "claude", "codex"],
        "description": rows(payload)["brain"]["description"],
    }


def test_the_note_on_the_page_is_the_one_the_adr_wrote(web) -> None:
    """ADR 0008 item 6, verbatim: the page renders this string and never a copy."""
    adr = (Path(__file__).resolve().parents[1] / ".vault" / "adr"
           / "0008-brains-and-settings.md").read_text(encoding="utf-8")
    _, payload = call(web[0] + "/api/settings")
    for sentence in payload["note"].split(". "):
        assert sentence.strip(" .") in adr


# --- writing ------------------------------------------------------------------------------


def test_a_value_round_trips_through_the_project_file_and_unset_gives_it_back(web) -> None:
    url, root, _ = web
    status, written = call(url + "/api/settings", {"key": "effort", "value": "low"})
    assert (status, written) == (200, {"key": "effort", "written_to": str(root / "art30.toml"),
                                       "present": True})
    assert 'effort = "low"' in (root / "art30.toml").read_text(encoding="utf-8")
    after = rows(call(url + "/api/settings")[1])["effort"]
    assert (after["value"], after["source"]) == ("low", "project")

    status, removed = call(url + "/api/settings", {"key": "max_turns", "value": "40"})
    assert status == 200 and rows(call(url + "/api/settings")[1])["max_turns"]["value"] == 40

    status, removed = delete(url + "/api/settings/effort?scope=project")
    assert (status, removed["present"]) == (200, False)
    back = rows(call(url + "/api/settings")[1])["effort"]
    assert (back["value"], back["source"]) == ("high", "default")
    assert "effort" not in (root / "art30.toml").read_text(encoding="utf-8")


def test_the_user_scope_writes_the_file_in_the_home_directory(web) -> None:
    url, root, home = web
    status, written = call(url + "/api/settings",
                           {"key": "concurrency", "value": 2, "scope": "user"})
    user_file = home / ".config" / "art30" / "config.toml"
    assert (status, written["written_to"]) == (200, str(user_file))
    assert "concurrency = 2" in user_file.read_text(encoding="utf-8")
    assert not (root / "art30.toml").exists(), "the project file was not the one asked for"
    assert rows(call(url + "/api/settings")[1])["concurrency"]["source"] == "user"


def test_a_value_outside_the_key_s_list_is_refused_with_the_reason(web) -> None:
    url, root, _ = web
    status, payload = call(url + "/api/settings", {"key": "effort", "value": "enormous"})
    assert status == 400
    assert payload["error"] == "effort must be one of low, medium, high, xhigh, max," \
                               " got 'enormous'"
    status, payload = call(url + "/api/settings", {"key": "max_turns", "value": "many"})
    assert status == 400 and payload["error"] == "max_turns must be a int, got 'many'"
    status, payload = call(url + "/api/settings", {"key": "nonsense", "value": "1"})
    assert status == 400 and payload["error"].startswith("unknown setting 'nonsense'")
    status, payload = call(url + "/api/settings", {"key": "effort", "value": "low",
                                                   "scope": "elsewhere"})
    assert status == 400 and payload["error"].startswith("scope must be one of")
    status, payload = call(url + "/api/settings", {"value": "low"})
    assert status == 400 and payload["error"] == "name the setting in `key`"
    assert not (root / "art30.toml").exists(), "a refused write wrote nothing"


# --- the one value that never comes back ----------------------------------------------------


def test_the_key_is_written_to_dotenv_and_never_read_back(web) -> None:
    url, root, _ = web
    status, written = call(url + "/api/settings",
                           {"key": "ANTHROPIC_API_KEY", "value": SECRET})
    assert (status, written) == (200, {"key": "anthropic_api_key",
                                       "written_to": str(root / ".env"), "present": True})
    assert SECRET not in json.dumps(written)
    dotenv = root / ".env"
    assert f"ANTHROPIC_API_KEY={SECRET}" in dotenv.read_text(encoding="utf-8")
    assert oct(dotenv.stat().st_mode)[-3:] == "600"

    status, content_type, body = raw(url + "/api/settings")
    assert status == 200 and SECRET not in body, "the key's own characters left the server"
    row = rows(json.loads(body))["anthropic_api_key"]
    assert (row["value"], row["source"], row["default"]) == ("present", ".env", "absent")

    status, removed = delete(url + "/api/settings/anthropic_api_key")
    assert (status, removed) == (200, {"key": "anthropic_api_key",
                                       "removed_from": str(dotenv), "present": False})
    assert SECRET not in dotenv.read_text(encoding="utf-8")
    assert rows(call(url + "/api/settings")[1])["anthropic_api_key"]["value"] == "absent"


def test_the_key_may_not_be_written_into_a_settings_file(web) -> None:
    """`settings.write` refuses it; the API answers with that sentence and not a 500."""
    url, root, _ = web
    status, payload = call(url + "/api/settings",
                           {"key": "anthropic_api_key", "value": "", "scope": "project"})
    assert status == 400 and "single non-empty line" in payload["error"]
    assert not (root / "art30.toml").exists()


def test_the_key_is_one_line_of_text_and_nothing_else(web) -> None:
    """The endpoint whose whole contract is "the value never comes back" is also the
    one place a second `.env` line could be smuggled in unseen: `.env` is read with
    `str.splitlines`, which splits on more than the newline, and a structured value is
    written as a Python repr and then reported as a real key."""
    url, root, _ = web
    call(url + "/api/settings", {"key": "anthropic_api_key", "value": SECRET})
    dotenv = root / ".env"
    before = dotenv.read_text(encoding="utf-8")

    for value in (SECRET + "\rART30_MAX_USD=999", SECRET + "\u2028ART30_MAX_USD=999",
                  SECRET + "\x0bART30_MAX_USD=999"):
        status, payload = call(url + "/api/settings",
                               {"key": "anthropic_api_key", "value": value})
        assert status == 400, value.encode("unicode_escape")
        assert payload["error"] == "ANTHROPIC_API_KEY must be a single non-empty line"
    for value in ({"a": SECRET}, ["k"], 7, None):
        status, payload = call(url + "/api/settings",
                               {"key": "anthropic_api_key", "value": value})
        assert status == 400, value
        assert payload["error"] == "ANTHROPIC_API_KEY is a single line of text"

    assert dotenv.read_text(encoding="utf-8") == before, "a refused write wrote nothing"
    assert len([line for line in before.splitlines() if "=" in line]) == 1
    assert rows(call(url + "/api/settings")[1])["max_usd"]["source"] == "default"


# --- the detection behind the brains panel ---------------------------------------------------


def test_detect_is_shelled_out_once_and_refresh_is_how_you_ask_again(
    web, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`detect()` runs four subprocesses; a page that polls must not run them all."""
    calls: list[int] = []

    def counted(*a, **k) -> dict:
        calls.append(1)
        return LOGGED_IN

    monkeypatch.setattr(settings_api, "detect", counted)
    settings_api.forget_brains()
    url = web[0]
    assert call(url + "/api/settings")[1]["brains"]["claude"]["logged_in"] is True
    call(url + "/api/settings")
    call(url + "/api/settings")
    assert len(calls) == 1, "the answer is held for thirty seconds"
    call(url + "/api/settings?refresh=1")
    assert len(calls) == 2, "a person who has just logged in presses Refresh"


def test_a_local_brain_that_is_not_logged_in_refuses_the_run_with_the_reason(
    web, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = web[0]
    monkeypatch.setattr(settings_api, "detect", lambda *a, **k: LOGGED_OUT)
    settings_api.forget_brains()
    status, payload = call(url + "/api/runs", {"repo": "D01", "arm": "advanced",
                                               "mode": "live", "brain": "claude"})
    assert status == 400
    assert payload["error"] == ("Claude (your login) is installed but not logged in."
                                " Log the CLI in from a terminal, then press Refresh.")
    status, payload = call(url + "/api/runs", {"repo": "D01", "arm": "advanced",
                                               "mode": "live", "brain": "codex"})
    assert status == 400 and payload["error"].startswith("Codex (your login) is not installed")
    status, payload = call(url + "/api/runs", {"repo": "D01", "arm": "advanced",
                                               "mode": "replay", "brain": "claude"})
    assert status == 400 and "no recorded responses to replay" in payload["error"]
    status, payload = call(url + "/api/runs", {"repo": "D01", "arm": "advanced",
                                               "mode": "live", "brain": "cortex"})
    assert status == 400 and payload["error"] == "brain must be one of api, claude, codex"


def test_a_brain_with_no_driver_is_refused_before_it_can_start(
    web, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A CLI can be installed and logged in and still have no driver on this side
    (`art30/brains/driver.py::BRAINS`). Readiness asks that too, so the toggle goes
    dead with a sentence instead of the run crashing at `exit 2` with the reason in
    a log file."""
    url = web[0]
    monkeypatch.setattr(settings_api, "detect", lambda *a, **k: BOTH_LOGGED_IN)
    monkeypatch.setattr(settings_api, "built", lambda: ("claude",))
    settings_api.forget_brains()
    payload = call(url + "/api/settings")[1]
    assert payload["brains"]["claude"]["built"] is True
    assert payload["brains"]["codex"]["built"] is False
    assert settings_api.refusal("claude") is None, "a brain with a driver is not refused"
    status, refused = call(url + "/api/runs", {"repo": "D01", "arm": "advanced",
                                               "mode": "live", "brain": "codex"})
    assert status == 400
    assert refused["error"] == ("Codex (your login) is logged in, but art30 has no driver"
                                " for it yet.")


def test_the_built_flag_is_the_driver_table_and_not_a_second_list(web) -> None:
    """One source for what art30 can drive: `art30.brains.built()`, stamped onto the
    row the page reads. A brain that gains a driver needs no change here."""
    payload = call(web[0] + "/api/settings")[1]
    assert payload["brains"]
    for name, row in payload["brains"].items():
        assert row["built"] is (name in built()), name


def test_the_child_is_told_which_brain_and_which_model(web) -> None:
    """The page's pick reaches the CLI as flags, never as a settings file the child
    might read differently (`art30/cli.py`, ADR 0008 item 1)."""
    argv = runs.command(Path("/repo"), "advanced", "D01", 1, "live", Path("/out"),
                        "claude", "opus-4.5")
    assert argv[-4:] == ["--brain", "claude", "--model", "opus-4.5"]
    assert runs.command(Path("/repo"), "advanced", "D01", 1, "live", Path("/out"))[-2:] \
        == ["--brain", "api"], "the API brain is named too, so nothing is left implied"
    assert "--model" not in runs.command(Path("/repo"), "advanced", "D01", 1, "live",
                                         Path("/out"), "codex", None)


# --- the registry a restart keeps -------------------------------------------------------------


def canned(root: Path, run_id: str, lines: list[dict], **extra) -> Path:
    """One `results/web/<run_id>/` as the server would have left it behind."""
    directory = root / run_id
    (directory / "traces" / "advanced").mkdir(parents=True)
    body = {"run_id": run_id, "case": "D01", "arm": "advanced", "mode": "live", "seed": 1,
            "repo": "evals/fixtures/synthetic/D01", "started_at": "2026-08-30T09:00:00Z"}
    body.update(extra)
    (directory / "run.json").write_text(json.dumps(body), encoding="utf-8")
    (directory / "traces" / "advanced" / "D01-s1.jsonl").write_text(
        "".join(json.dumps(line) + "\n" for line in lines), encoding="utf-8")
    return directory


def test_a_restarted_server_lists_the_runs_it_finds_on_disk(web, tmp_path: Path) -> None:
    """Nothing is in memory here: every row comes from a directory (ADR 0008 item 4)."""
    root = tmp_path / "web"
    canned(root, "advanced-D01-s1-aaaaaa", TRACE, brain="claude")
    canned(root, "advanced-D01-s1-bbbbbb", UNFINISHED, started_at="2026-08-30T10:00:00Z")
    (root / "not-a-run").mkdir()

    status, payload = call(web[0] + "/api/runs")
    assert status == 200
    listed = {row["run_id"]: row for row in payload["runs"]}
    assert list(listed) == ["advanced-D01-s1-aaaaaa", "advanced-D01-s1-bbbbbb"], \
        "oldest first, and a directory with no run.json is not a run"
    first = listed["advanced-D01-s1-aaaaaa"]
    assert (first["status"], first["brain"], first["case"]) == ("accepted", "claude", "D01")
    assert first["cost_source"] == "cli_estimate", "a local brain's cost is an estimate"
    second = listed["advanced-D01-s1-bbbbbb"]
    assert (second["status"], second["brain"]) == ("failed:crashed", "api")
    assert second["cost_source"] == "measured", "the API brain's dollars are measured"

    status, one = call(web[0] + "/api/runs/advanced-D01-s1-aaaaaa")
    assert (status, one["status"], one["brain"]) == (200, "accepted", "claude")
    status, payload = call(web[0] + "/api/runs/advanced-D01-s1-aaaaaa/cancel", {})
    assert status == 409, "a run this process never started cannot be killed by it"


def test_a_run_id_that_is_a_path_reaches_no_directory(web, tmp_path: Path) -> None:
    canned(tmp_path / "web", "advanced-D01-s1-aaaaaa", TRACE)
    assert runs.adopt("../../etc") is None
    assert runs.adopt("..") is None
    assert runs.adopt("nothing-here") is None
    status, payload = call(web[0] + "/api/runs/..%2F..%2Fetc")
    assert status == 404
