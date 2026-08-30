"""The settings layer: the five layers in order, the secret rule, and the two writers.

Every case builds its own project root and its own HOME under `tmp_path`, so no
test reads the author's `~/.config/art30/config.toml` or writes the repository's
own `.env` (ADR 0008 item 5).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from art30 import brains, cli, config, settings
from art30.loop import RunResult

KEY = settings.SECRET_ENV
EXAMPLE = Path(__file__).resolve().parents[1] / "art30.toml.example"
DOCS = Path(__file__).resolve().parents[1] / "docs" / "settings.md"


@pytest.fixture()
def home(tmp_path: Path) -> Path:
    return tmp_path / "home"


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    project.mkdir()
    return project


def _user_file(home: Path, text: str) -> Path:
    path = settings.user_file(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_the_layers_apply_in_order(root: Path, home: Path) -> None:
    """Defaults, the user file, the project file, `.env`, the environment: each one
    wins over the one before it and nothing else it did not name moves."""
    _user_file(home, "effort = 'low'\nmax_tokens = 8000\nconcurrency = 2\nbrain = 'codex'\n")
    (root / "art30.toml").write_text("effort = 'medium'\nmax_tokens = 12000\n", encoding="utf-8")
    (root / ".env").write_text(f"{KEY}=sk-not-a-real-key\nART30_MAX_TOKENS=16000\n", encoding="utf-8")

    resolved = settings.read(root, environ={"ART30_EFFORT": "max"}, home=home)

    assert resolved.value("effort") == "max" and resolved.sources["effort"] == "env"
    assert resolved.value("max_tokens") == 16_000 and resolved.sources["max_tokens"] == ".env"
    assert resolved.value("concurrency") == 2 and resolved.sources["concurrency"] == "user"
    assert resolved.value("brain") == "codex"
    assert resolved.value("model") == "claude-opus-5" and resolved.sources["model"] == "default"
    assert resolved.value("submit_budget") == 5 and resolved.value("max_usd") is None


def test_the_project_file_beats_the_user_file_and_the_environment_beats_both(
    root: Path, home: Path
) -> None:
    _user_file(home, "model = 'claude-haiku-4-5'\napprove = 'auto'\n")
    (root / "art30.toml").write_text("model = 'claude-sonnet-5'\n", encoding="utf-8")

    project = settings.read(root, environ={}, home=home)
    assert project.value("model") == "claude-sonnet-5" and project.sources["model"] == "project"
    assert project.value("approve") == "auto" and project.sources["approve"] == "user"

    over = settings.read(root, environ={"ART30_MODEL": "claude-opus-5"}, home=home)
    assert over.value("model") == "claude-opus-5" and over.sources["model"] == "env"


def test_an_empty_variable_is_not_a_value(root: Path, home: Path) -> None:
    """`.env.example` ships `ART30_MAX_USD=`; an empty line must not read as a ceiling."""
    resolved = settings.read(root, environ={"ART30_MAX_USD": "", "ART30_EFFORT": ""}, home=home)
    assert resolved.value("max_usd") is None and resolved.value("effort") == "high"

    # The file layer has the same rule. An emptied line used to be applied as None,
    # which put `{"model": null, "max_tokens": null}` in a request nothing can answer.
    (root / "art30.toml").write_text('model = ""\nmax_tokens = ""\ntool_budget = ""\n',
                                     encoding="utf-8")
    from_file = settings.read(root, environ={}, home=home)
    assert from_file.value("model") == "claude-opus-5" and from_file.sources["model"] == "default"
    assert from_file.value("max_tokens") == 32_000 and from_file.value("tool_budget") == 60


def test_the_run_switch_drops_both_files_for_one_process(root: Path, home: Path) -> None:
    """`ART30_IGNORE_SETTINGS_FILES` is a run switch, not a setting, and the harness pins
    it on every cell: `~/.config/art30/config.toml` is not a checkout artefact, so a clean
    checkout does not exclude it and only this does (ADR 0008 item 5)."""
    _user_file(home, "model = 'claude-haiku-9'\nconcurrency = 11\n")
    (root / "art30.toml").write_text("effort = 'low'\nbrain = 'codex'\n", encoding="utf-8")
    (root / ".env").write_text("ART30_SUBMIT_BUDGET=3\n", encoding="utf-8")

    resolved = settings.read(root, environ={settings.IGNORE_FILES_ENV: "1"}, home=home)

    assert resolved.value("model") == "claude-opus-5" and resolved.sources["model"] == "default"
    assert (resolved.value("effort"), resolved.value("brain")) == ("high", "api")
    assert resolved.value("concurrency") == 4
    # `.env` and the environment are the sweep's own seams and are not dropped.
    assert resolved.value("submit_budget") == 3 and resolved.sources["submit_budget"] == ".env"
    assert settings.read(root, environ={}, home=home).value("model") == "claude-haiku-9"


def test_the_key_is_a_presence_and_never_a_value(root: Path, home: Path) -> None:
    """`.env` is the only place the key lives, and `describe()` is what the CLI and
    the website print: neither may carry the secret itself."""
    secret = "sk-ant-not-a-real-key-0123456789"
    (root / ".env").write_text(f"{KEY}={secret}\n", encoding="utf-8")

    resolved = settings.read(root, environ={}, home=home)
    rows = settings.describe(resolved)
    row = next(r for r in rows if r["key"] == "anthropic_api_key")

    assert resolved.secret_present is True and resolved.secret_source == ".env"
    assert row["value"] == "present" and row["source"] == ".env"
    assert secret not in json.dumps(rows) and secret not in json.dumps(resolved.values)
    assert "anthropic_api_key" not in resolved.values

    elsewhere = root / "elsewhere"
    elsewhere.mkdir()
    away = settings.describe(settings.read(elsewhere, environ={}, home=home))
    assert next(r for r in away if r["key"] == "anthropic_api_key")["value"] == "absent"


def test_describe_carries_a_row_per_key_with_its_default_and_its_sentence() -> None:
    rows = settings.describe(settings.read(environ={}, home=Path("/nonexistent")))
    assert [r["key"] for r in rows] == [k.name for k in settings.KEYS]
    for row in rows:
        assert row["description"].endswith(".") and len(row["description"].split()) > 4
    brain = next(r for r in rows if r["key"] == "brain")
    assert brain["allowed"] == ["api", "claude", "codex"] and brain["default"] == "api"


def test_validation_names_the_key_and_the_allowed_values(root: Path, home: Path) -> None:
    (root / "art30.toml").write_text("brain = 'gpt'\n", encoding="utf-8")
    with pytest.raises(ValueError) as bad_brain:
        settings.read(root, environ={}, home=home)
    assert "brain must be one of api, claude, codex" in str(bad_brain.value)

    with pytest.raises(ValueError) as bad_int:
        settings.read(root.parent, environ={"ART30_MAX_TOKENS": "lots"}, home=home)
    assert "max_tokens must be a int, got 'lots'" in str(bad_int.value)

    with pytest.raises(ValueError) as unknown:
        settings.key_for("modle")
    assert "unknown setting 'modle'" in str(unknown.value)


def test_a_settings_file_may_not_hold_the_key_or_a_name_nobody_knows(
    root: Path, home: Path
) -> None:
    (root / "art30.toml").write_text(f"{settings.SECRET.name} = 'sk-nope'\n", encoding="utf-8")
    with pytest.raises(ValueError, match="belongs in .env"):
        settings.read(root, environ={}, home=home)

    (root / "art30.toml").write_text("modle = 'x'\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unknown setting"):
        settings.read(root, environ={}, home=home)


def test_write_and_unset_round_trip_and_keep_the_rest_of_the_file(
    root: Path, home: Path
) -> None:
    (root / "art30.toml").write_text("# hand written\nmodel = 'claude-sonnet-5'\n", encoding="utf-8")

    settings.write("effort", "low", project_root=root)
    path = settings.write("model", "claude-haiku-4-5", project_root=root)
    text = path.read_text(encoding="utf-8")
    assert path == root / "art30.toml" and "# hand written" in text
    assert text.count("model =") == 1 and 'model = "claude-haiku-4-5"' in text

    resolved = settings.read(root, environ={}, home=home)
    assert resolved.value("model") == "claude-haiku-4-5" and resolved.value("effort") == "low"

    settings.unset("model", project_root=root)
    after = settings.read(root, environ={}, home=home)
    assert after.value("model") == "claude-opus-5" and after.sources["model"] == "default"
    assert "# hand written" in path.read_text(encoding="utf-8")
    assert after.value("effort") == "low"


def test_the_user_scope_writes_the_user_file_and_the_project_file_wins(
    root: Path, home: Path
) -> None:
    path = settings.write("concurrency", "8", scope="user", project_root=root, home=home)
    assert path == settings.user_file(home) and path.is_file()
    assert settings.read(root, environ={}, home=home).value("concurrency") == 8

    settings.write("concurrency", "2", project_root=root)
    assert settings.read(root, environ={}, home=home).sources["concurrency"] == "project"
    with pytest.raises(ValueError, match="scope must be one of"):
        settings.write("concurrency", "2", scope="global", project_root=root)


def test_a_json_key_survives_a_write_and_a_read(root: Path, home: Path) -> None:
    settings.write("codex_prices", '{"gpt-5-codex": [1.25, 10.0]}', project_root=root)
    assert settings.read(root, environ={}, home=home).value("codex_prices") == {
        "gpt-5-codex": [1.25, 10.0]
    }
    with pytest.raises(ValueError, match="must be a JSON object"):
        settings.write("codex_prices", "1.25", project_root=root)


def test_both_surfaces_spell_codex_prices_the_way_the_code_reads_it() -> None:
    """The key's own description and `docs/settings.md` documented `[input, output]`
    while `pricing._triple` reads three numbers. A user who followed the documentation
    wrote two, cached input priced at the full input rate, and the cost-per-task row --
    a scored one -- came out several times too high with nothing saying so."""
    key = settings.key_for("codex_prices")
    row = next(line for line in DOCS.read_text(encoding="utf-8").splitlines()
               if line.startswith("| `codex_prices` |"))

    assert "cached_input" in key.description and "cached_input" in row
    assert "[input, output]" not in row


def test_the_secret_is_written_to_dotenv_at_0600_and_nowhere_else(root: Path) -> None:
    (root / ".env").write_text("# mine\nART30_EFFORT=low\nANTHROPIC_API_KEY=old\n", encoding="utf-8")

    path = settings.write_secret(KEY, "sk-ant-second", project_root=root)
    text = path.read_text(encoding="utf-8")

    assert path == root / ".env" and (path.stat().st_mode & 0o777) == 0o600
    assert text.count(f"{KEY}=") == 1 and f"{KEY}=sk-ant-second" in text
    assert "# mine" in text and "ART30_EFFORT=low" in text
    with pytest.raises(ValueError, match="is a secret"):
        settings.write("anthropic_api_key", "sk-nope", project_root=root)
    with pytest.raises(ValueError, match="is not a secret"):
        settings.write_secret("model", "claude-opus-5", project_root=root)


def test_unsetting_the_key_rewrites_dotenv_and_never_reports_a_false_success(root: Path) -> None:
    """`unset` used to succeed against `art30.toml`, print the key gone and leave it in
    `.env`. A person clearing a borrowed machine is the one reader that costs."""
    (root / ".env").write_text("# mine\nANTHROPIC_API_KEY=sk-ant-STILLHERE\nART30_EFFORT=low\n",
                               encoding="utf-8")

    path = settings.unset("anthropic_api_key", project_root=root)
    text = path.read_text(encoding="utf-8")

    assert path == root / ".env" and "STILLHERE" not in text
    assert "# mine" in text and "ART30_EFFORT=low" in text
    assert not (root / "art30.toml").exists()
    assert settings.read(root, environ={}, home=root / "home").secret_present is False


def test_unsetting_a_key_no_file_holds_leaves_no_file_behind(root: Path) -> None:
    assert settings.unset("model", project_root=root) == root / "art30.toml"
    assert not (root / "art30.toml").exists()


def test_a_new_dotenv_is_restricted_before_the_secret_reaches_it(root: Path, monkeypatch) -> None:
    """0600 is created, not repaired: a chmod after the write leaves the key readable
    for the width of that window, and keeps it there if the chmod raises."""
    modes: list[int | None] = []
    rewrite = settings._rewrite

    def spy(path: Path, name: str, line: str | None, header: str) -> Path:
        modes.append((path.stat().st_mode & 0o777) if path.is_file() else None)
        return rewrite(path, name, line, header)

    monkeypatch.setattr(settings, "_rewrite", spy)
    path = settings.write_secret(KEY, "sk-ant-not-a-real-key", project_root=root)

    assert modes == [0o600] and (path.stat().st_mode & 0o777) == 0o600
    assert "sk-ant-not-a-real-key" in path.read_text(encoding="utf-8")


def test_the_project_root_is_the_directory_holding_pyproject(tmp_path: Path, monkeypatch) -> None:
    """A checkout is found from any directory inside it; anywhere else is its own root."""
    project = tmp_path / "checkout"
    (project / "pkg" / "deep").mkdir(parents=True)
    (project / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    monkeypatch.chdir(project / "pkg" / "deep")
    assert settings.discover_root() == project.resolve()

    bare = tmp_path / "bare"
    bare.mkdir()
    monkeypatch.chdir(bare)
    assert settings.discover_root() == bare.resolve()


# --- what config.load() makes of it ------------------------------------------------------------


def test_the_api_brain_loads_exactly_what_it_loaded_before(tmp_path: Path, monkeypatch) -> None:
    """The three values that are hashed into a request, at their defaults, plus the
    fields ADR 0008 adds. A change here is a change to every recorded response."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    for name in ("ART30_MODEL", "ART30_EFFORT", "ART30_MAX_TOKENS", "ART30_TOOL_BUDGET"):
        monkeypatch.delenv(name, raising=False)

    cfg = config.load()

    assert (cfg.model, cfg.effort, cfg.max_tokens) == ("claude-opus-5", "high", 32_000)
    assert (cfg.tool_budget, cfg.max_submits, cfg.max_usd) == (60, 5, None)
    assert (cfg.brain, cfg.brain_model, cfg.max_turns) == ("api", None, 60)
    assert cfg.trace_config() == {"max_tokens": 32_000, "tool_budget": 60,
                                  "submit_budget": 5, "overridden": []}


def test_a_project_file_reaches_config_and_is_declared_as_an_override(tmp_path: Path, monkeypatch, settings_files) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("ART30_TOOL_BUDGET", raising=False)
    (tmp_path / "art30.toml").write_text(
        "brain = 'claude'\nclaude_model = 'opus'\ntool_budget = 90\nmax_turns = 12\n",
        encoding="utf-8")

    cfg = config.load()

    assert cfg.brain == "claude" and cfg.brain_model == "opus" and cfg.max_turns == 12
    assert cfg.overridden == ("ART30_TOOL_BUDGET",)
    assert cfg.for_case_kind("real").tool_budget == 90   # the file wins over the case kind
    assert cfg.trace_config()["brain"] == "claude"


def test_copying_the_shipped_example_declares_no_override(tmp_path: Path, monkeypatch) -> None:
    """`art30.toml.example` says every line in it is the default. Declaring four
    overrides at default values fires 07-ui.md section 1's one signal on the run that
    is exactly the reported one, and diverges from every committed trace."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    for name in config.REQUEST_VARS:
        monkeypatch.delenv(name, raising=False)
    (tmp_path / "art30.toml").write_text(EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")

    cfg = config.load()

    assert cfg.overridden == ()
    assert cfg.trace_config() == {"max_tokens": 32_000, "tool_budget": 60,
                                  "submit_budget": 5, "overridden": []}


def test_a_budget_written_at_its_default_still_beats_the_case_kind(tmp_path: Path, monkeypatch, settings_files) -> None:
    """`tool_budget = 60` is a choice of 60. It is not an override, because 60 is the
    default value, and it still stops a real case being raised to 120 behind the user."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("ART30_TOOL_BUDGET", raising=False)
    (tmp_path / "art30.toml").write_text("tool_budget = 60\n", encoding="utf-8")

    cfg = config.load()

    assert cfg.overridden == () and cfg.explicit == ("ART30_TOOL_BUDGET",)
    assert cfg.for_case_kind("real").tool_budget == 60


def test_the_loader_reads_the_projects_dotenv_from_a_subdirectory(
    tmp_path: Path, monkeypatch
) -> None:
    """`config.load` read `.env` relative to the working directory while `settings.read`
    walked up to `pyproject.toml`: from a subdirectory `art30 config list` reported the
    key present and `art30 scan --mode live` refused for want of it."""
    project = tmp_path / "checkout"
    (project / "pkg").mkdir(parents=True)
    (project / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (project / ".env").write_text(f"{KEY}=sk-ant-not-a-real-key\nART30_EFFORT=low\n",
                                  encoding="utf-8")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("ART30_EFFORT", raising=False)
    monkeypatch.delenv(KEY, raising=False)
    monkeypatch.chdir(project / "pkg")

    listed = settings.read(home=tmp_path / "home")   # what `art30 config list` prints
    cfg = config.load()                              # what a scan resolves

    assert listed.sources["effort"] == ".env" and listed.secret_present is True
    assert cfg.effort == "low"
    # art30/cli.py checks the environment before `llm` builds a client (docs/cli.md).
    assert os.environ[KEY] == "sk-ant-not-a-real-key"


def test_a_bad_settings_file_is_a_config_error_not_a_traceback(tmp_path: Path, monkeypatch, settings_files) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "art30.toml").write_text("effort = 'enormous'\n", encoding="utf-8")
    with pytest.raises(config.ConfigError, match="effort must be one of"):
        config.load()


# --- the CLI surface ---------------------------------------------------------------------------


def _run(argv: list[str], capsys) -> tuple[int, str, str]:
    code = cli.main(argv)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_config_list_get_and_path_print_the_layer_each_value_came_from(tmp_path: Path, monkeypatch, capsys, settings_files) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("ART30_EFFORT", "low")
    (tmp_path / "art30.toml").write_text("model = 'claude-sonnet-5'\n", encoding="utf-8")

    code, out, _ = _run(["config", "list"], capsys)
    lines = {line.split()[0]: line for line in out.splitlines()}

    assert code == 0 and len(lines) == len(settings.KEYS)
    assert "claude-sonnet-5" in lines["model"] and lines["model"].endswith("project")
    assert lines["effort"].endswith("env") and "low" in lines["effort"]
    assert lines["claude_model"].split()[1:] == ["(unset)", "default"]
    assert lines["anthropic_api_key"].split()[1] == "absent"

    assert _run(["config", "get", "model"], capsys)[1] == "claude-sonnet-5\n"
    assert _run(["config", "get", "ART30_EFFORT"], capsys)[1] == "low\n"
    code, out, _ = _run(["config", "path"], capsys)
    assert code == 0 and str(tmp_path / "art30.toml") in out and ".env" in out


def test_config_set_and_unset_write_the_file_the_scope_names(tmp_path: Path, monkeypatch, capsys, settings_files) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))

    assert _run(["config", "set", "brain", "codex"], capsys)[0] == 0
    assert (tmp_path / "art30.toml").read_text(encoding="utf-8").count("brain") == 1
    assert _run(["config", "get", "brain"], capsys)[1] == "codex\n"

    assert _run(["config", "set", "concurrency", "6", "--user"], capsys)[0] == 0
    assert settings.user_file(tmp_path / "home").is_file()

    assert _run(["config", "unset", "brain"], capsys)[0] == 0
    assert _run(["config", "get", "brain"], capsys)[1] == "api\n"

    code, _, err = _run(["config", "set", "effort", "enormous"], capsys)
    assert code == 2 and "effort must be one of low, medium, high, xhigh, max" in err


def test_config_set_of_the_key_writes_dotenv_without_echoing_it(tmp_path: Path, monkeypatch, capsys, settings_files) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    secret = "sk-ant-not-a-real-key"

    code, out, _ = _run(["config", "set", KEY, secret], capsys)

    assert code == 0 and out == "written to .env (not echoed)\n"
    assert secret in (tmp_path / ".env").read_text(encoding="utf-8")
    assert secret not in _run(["config", "list"], capsys)[1]
    monkeypatch.delenv(KEY, raising=False)
    assert "present" in [line for line in _run(["config", "list"], capsys)[1].splitlines()
                         if line.startswith("anthropic_api_key")][0]


def _stub(seen: list, pick):
    """A `run_brain` that spawns nothing: the dispatch is what these tests are about."""
    def _run(cfg, case, arm, seed, report=None):
        seen.append(pick(cfg, arm))
        return RunResult(run_id="base-fx-s1-0000000", stop_condition="no_submission", steps=0,
                         tool_calls_total=0, submits=0, verify_rounds=0, wall_s=0.0,
                         cost_usd=0.0, record_path=None, note="stub")
    return _run


def test_the_model_flag_follows_the_brain_the_loader_resolved(tmp_path: Path, monkeypatch, capsys, settings_files) -> None:
    """`--model` used to be routed by the `--brain` flag, so a brain that came from
    `art30.toml` moved the API model and left the CLI that would run with nothing."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "fx").mkdir()
    (tmp_path / "fx" / "a.py").write_text("A = 1\n", encoding="utf-8")
    seen: list[dict] = []
    loader = config.load
    monkeypatch.setattr(cli.config, "load",
                        lambda over=None: (seen.append(dict(over or {})), loader(over))[1])

    (tmp_path / "art30.toml").write_text("brain = 'claude'\n", encoding="utf-8")
    ran: list = []
    monkeypatch.setattr("art30.brains.run_brain", _stub(ran, lambda cfg, arm: cfg))
    cli.main(["scan", "fx", "--arm", "baseline", "--model", "opus-x"])
    capsys.readouterr()
    assert seen[-1] == {}   # the API model is not what a `claude` run's --model names
    assert (ran[-1].brain, ran[-1].brain_model) == ("claude", "opus-x")
    assert ran[-1].model == config.DEFAULT_MODEL   # the API model did not move

    (tmp_path / "art30.toml").unlink()
    code, out, _ = _run(["scan", "fx", "--arm", "baseline", "--mode", "replay",
                         "--model", "opus-x"], capsys)
    assert code == 4 and out.splitlines()[1].startswith("model opus-x ")
    assert "overridden: ART30_MODEL" in out


def test_every_brain_the_flag_offers_reaches_the_driver(tmp_path: Path, monkeypatch,
                                                       capsys) -> None:
    """Both local brains are built now (ADR 0008 item 1), so `--brain` reaches the
    driver rather than the "not built yet" exit the flag used to take.

    The exit is still in `art30/cli.py`: it is what a brain named in the settings
    but missing from `art30/brains/driver.py` would take, and the assertion below is
    that neither of the two is in that state. Nothing is spawned here -- the driver
    is stubbed -- so no test on this machine starts a real CLI."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "fx").mkdir()
    (tmp_path / "fx" / "a.py").write_text("A = 1\n", encoding="utf-8")
    assert set(brains.built()) == {"claude", "codex"} == set(settings.BRAINS) - {"api"}

    ran: list = []
    monkeypatch.setattr("art30.brains.run_brain", _stub(ran, lambda cfg, arm: arm.name))
    for brain in ("claude", "codex"):
        assert cli.main(["scan", "fx", "--arm", "baseline", "--brain", brain]) == 1
        capsys.readouterr()
    assert ran == ["baseline", "baseline"]
