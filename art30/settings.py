"""One layered settings loader for the CLI, the eval harness and the website.

Precedence, lowest first: the defaults in `KEYS`, `~/.config/art30/config.toml`,
`<project>/art30.toml`, `.env`, the process environment. A CLI flag is the last
word and is applied by the caller. Every resolved value carries the layer it came
from, which is what `art30 config list` and the website's settings view print
(ADR 0008 item 5).

`ART30_IGNORE_SETTINGS_FILES=1` drops the two file layers for one process: a run
switch the harness pins per cell, so a user's files never move a sweep.

The API key is the one secret: read by name from `.env` or the environment, kept
as a yes or no. This module never returns or logs the value.
"""

from __future__ import annotations

import json
import os
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Mapping

ENV_PREFIX = "ART30_"
SECRET_ENV = "ANTHROPIC_API_KEY"
USER_PATH = Path(".config") / "art30" / "config.toml"
PROJECT_NAME = "art30.toml"
DOTENV_NAME = ".env"
MARKER = "pyproject.toml"
IGNORE_FILES_ENV = "ART30_IGNORE_SETTINGS_FILES"   # a run switch; see the module docstring
BRAINS = ("api", "claude", "codex")
EFFORTS = ("low", "medium", "high", "xhigh", "max")
APPROVALS = ("ask", "auto", "file")
SCOPES = ("project", "user")
NEW_FILE_HEADER = "# art30 settings. One flat `key = value` per line; see docs/settings.md.\n"
NEW_DOTENV_HEADER = "# art30 secrets. Never commit this file.\n"


@dataclass(frozen=True)
class Key:
    """One setting: how it is spelled everywhere, what it accepts, what it means."""

    name: str
    type: str                      # str | int | float | bool | json
    default: Any
    description: str
    allowed: tuple[str, ...] = ()
    secret: bool = False

    @property
    def env(self) -> str:
        return SECRET_ENV if self.secret else ENV_PREFIX + self.name.upper()


KEYS: tuple[Key, ...] = (
    Key("brain", "str", "api", allowed=BRAINS,
        description="Which engine runs the loop: the Anthropic API, your own `claude` CLI, or your own `codex` CLI."),
    Key("model", "str", "claude-opus-5",
        description="The model id the `api` brain sends; it is hashed into every request, so changing it invalidates recorded responses."),
    Key("claude_model", "str", None,
        description="The model the `claude` brain passes to `claude --model`; unset leaves the CLI its own default."),
    Key("codex_model", "str", None,
        description="The model the `codex` brain passes to `codex exec -m`; unset leaves the CLI its own default."),
    Key("effort", "str", "high", allowed=EFFORTS,
        description="Reasoning effort on the `api` brain, from `low` to `max`."),
    Key("max_tokens", "int", 32_000,
        description="Output-token ceiling for one API response."),
    Key("max_turns", "int", 60,
        description="Turn ceiling for a local brain, which has no dollar ceiling to stop it."),
    Key("tool_budget", "int", 60,
        description="Tool calls one run may spend; unset, the case kind picks 60 for a synthetic repository and 120 for a real one."),
    Key("submit_budget", "int", 5,
        description="How many `submit_record` attempts the verifier accepts before the run stops."),
    Key("max_usd", "float", None,
        description="Cumulative dollar ceiling for one `api` run; local brains bill no dollars and ignore it."),
    Key("gate_timeout", "int", 1800,
        description="Seconds `--approve file` waits for a decision before it records a rejection."),
    Key("approve", "str", "ask", allowed=APPROVALS,
        description="How the human gate is answered: a terminal prompt, an automatic approval, or a decision file."),
    Key("concurrency", "int", 4,
        description="How many evaluation cells the harness runs at once."),
    Key("codex_prices", "json", {},
        description="Per-model `[input, output]` dollars per million tokens for pricing a `codex` run; a model with no entry is reported as tokens only."),
    Key("anthropic_api_key", "str", None, secret=True,
        description="The key the SDK reads for the `api` brain; it lives in `.env`, and art30 reports only whether it is there."),
)

_BY_NAME: dict[str, Key] = {n: k for k in KEYS for n in (k.name, k.env.lower())}
PUBLIC: tuple[Key, ...] = tuple(k for k in KEYS if not k.secret)
SECRET: Key = next(k for k in KEYS if k.secret)


@dataclass(frozen=True)
class Settings:
    """Resolved values, the layer each came from, and the files that were read."""

    values: dict[str, Any]
    sources: dict[str, str]
    secret_present: bool
    secret_source: str
    root: Path
    files: dict[str, Path]

    def value(self, name: str) -> Any:
        """`brain`, `ART30_BRAIN` or `BRAIN`: one lookup for every surface's spelling."""
        return self.values[key_for(name).name]


def key_for(name: str) -> Key:
    """A key by any spelling a person uses: `model`, `MODEL`, `ART30_MODEL`."""
    key = _BY_NAME.get(str(name).strip().lower())
    if key is None:
        raise ValueError(f"unknown setting {name!r}; known: {', '.join(k.name for k in KEYS)}")
    return key


def discover_root(start: Path | None = None) -> Path:
    """The directory holding `pyproject.toml`, walking up from `start`, else `start`."""
    here = (Path(start) if start else Path.cwd()).resolve()
    for candidate in (here, *here.parents):
        if (candidate / MARKER).is_file():
            return candidate
    return here


def user_file(home: Path | str | None = None, environ: Mapping[str, str] | None = None) -> Path:
    env = os.environ if environ is None else environ
    base = Path(home) if home is not None else Path(env.get("HOME") or Path.home())
    return base / USER_PATH


def scope_file(scope: str, root: Path, home: Path | str | None = None,
               environ: Mapping[str, str] | None = None) -> Path:
    if scope not in SCOPES:
        raise ValueError(f"scope must be one of {', '.join(SCOPES)}, got {scope!r}")
    return root / PROJECT_NAME if scope == "project" else user_file(home, environ)


# --- reading ---------------------------------------------------------------------------------


def _coerce(key: Key, raw: Any) -> Any:
    if raw is None or raw == "":
        return None
    if key.type == "json":
        value = raw if isinstance(raw, dict) else _json(key, raw)
    elif key.type == "bool":
        value = raw if isinstance(raw, bool) else str(raw).strip().lower() in ("1", "true", "yes")
    elif key.type == "int":
        value = _number(key, raw, int)
    elif key.type == "float":
        value = _number(key, raw, float)
    else:
        value = str(raw)
    if key.allowed and value not in key.allowed:
        raise ValueError(f"{key.name} must be one of {', '.join(key.allowed)}, got {value!r}")
    return value


def _number(key: Key, raw: Any, cast: type) -> Any:
    try:
        if isinstance(raw, bool):
            raise TypeError
        return cast(raw)
    except (TypeError, ValueError):
        raise ValueError(f"{key.name} must be a {cast.__name__}, got {raw!r}") from None


def _json(key: Key, raw: Any) -> dict:
    try:
        value = json.loads(str(raw))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{key.name} must be a JSON object, got {raw!r} ({exc.msg})") from None
    if not isinstance(value, dict):
        raise ValueError(f"{key.name} must be a JSON object, got {raw!r}")
    return value


def read_toml(path: Path) -> dict[str, Any]:
    """A flat settings file. An unknown key is an error rather than a silent no-op."""
    if not path.is_file():
        return {}
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ValueError(f"{path}: {exc}") from None
    if SECRET.name in data:
        raise ValueError(f"{path}: {SECRET.name} belongs in {DOTENV_NAME}, never in a settings file")
    unknown = sorted(n for n in data if n.lower() not in _BY_NAME)
    if unknown:
        raise ValueError(f"{path}: unknown setting(s) {', '.join(unknown)}"
                         f"; known: {', '.join(k.name for k in PUBLIC)}")
    return data


def _env_layer(mapping: Mapping[str, str]) -> Iterator[tuple[Key, str]]:
    """`ART30_*` names in a mapping, ignoring the run switches that are not settings."""
    for key in PUBLIC:
        raw = mapping.get(key.env)
        if raw:
            yield key, raw


def _dotenv(path: Path) -> dict[str, str]:
    """`.env` through `config.read_dotenv`, imported late: `config` imports this module.

    Late is also what keeps the seam: `tests/test_cli.py` replaces
    `config.read_dotenv` so a judge's own `.env` cannot answer a test.
    """
    from art30 import config

    return config.read_dotenv(path)


def read(project_root: Path | str | None = None, environ: Mapping[str, str] | None = None,
         home: Path | str | None = None, dotenv: Mapping[str, str] | None = None) -> Settings:
    """Defaults, the user file, the project file, `.env`, then the process environment.

    `dotenv` is the caller's already-parsed `.env`, so `config.load` and this
    function never disagree about which file that is."""
    env = os.environ if environ is None else environ
    root = Path(project_root).resolve() if project_root else discover_root()
    files = {"user": user_file(home, env), "project": root / PROJECT_NAME,
             DOTENV_NAME: root / DOTENV_NAME}
    values: dict[str, Any] = {k.name: k.default for k in PUBLIC}
    sources: dict[str, str] = {k.name: "default" for k in PUBLIC}
    # The harness pins the switch on every cell, so no file of the user's moves a sweep.
    labels = () if env.get(IGNORE_FILES_ENV) == "1" else ("user", "project")
    for label in labels:
        for name, raw in read_toml(files[label]).items():
            key = key_for(name)
            value = _coerce(key, raw)
            if value is None:   # an empty value is not a value: the layer below keeps the key
                continue
            values[key.name], sources[key.name] = value, label
    dotenv = _dotenv(files[DOTENV_NAME]) if dotenv is None else dict(dotenv)
    for label, mapping in ((DOTENV_NAME, dotenv), ("env", env)):
        for key, raw in _env_layer(mapping):
            values[key.name], sources[key.name] = _coerce(key, raw), label
    secret_source = "env" if env.get(SECRET_ENV) else (DOTENV_NAME if dotenv.get(SECRET_ENV) else "")
    return Settings(values=values, sources=sources, secret_present=bool(secret_source),
                    secret_source=secret_source, root=root, files=files)


def describe(settings: Settings | None = None) -> list[dict]:
    """One row per key for `art30 config list` and the website. The secret is a state."""
    st = settings if settings is not None else read()
    rows = []
    for key in KEYS:
        secret = key.secret
        rows.append({
            "key": key.name,
            "value": ("present" if st.secret_present else "absent") if secret else st.values[key.name],
            "source": (st.secret_source or "default") if secret else st.sources[key.name],
            "default": "absent" if secret else key.default,
            "allowed": list(key.allowed),
            "description": key.description,
        })
    return rows


# --- writing ---------------------------------------------------------------------------------


def render(key: Key, value: Any) -> str:
    """One TOML line. The settings files are flat, so this is the whole serialiser."""
    if key.type == "json" or isinstance(value, dict):
        payload = json.dumps(value, sort_keys=True, separators=(",", ": "))
        body = f"'{payload}'" if "'" not in payload else json.dumps(payload)
    elif isinstance(value, bool):
        body = "true" if value else "false"
    elif isinstance(value, (int, float)):
        body = repr(value)
    else:
        body = json.dumps(str(value))   # JSON's escapes are a subset of TOML's
    return f"{key.name} = {body}"


def _rewrite(path: Path, name: str, line: str | None, header: str) -> Path:
    """Replace the one line that assigns `name`, or append it. Other lines survive."""
    if line is None and not path.is_file():
        return path   # nothing to remove: an unset must not leave an empty file behind
    existing = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    pattern = re.compile(rf"^\s*{re.escape(name)}\s*=")
    kept: list[str] = []
    replaced = False
    for raw in existing:
        if pattern.match(raw):
            if line is not None and not replaced:
                kept.append(line)
                replaced = True
            continue
        kept.append(raw)
    if line is not None and not replaced:
        kept.append(line)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(kept)
    if not existing and body:
        body = header + body
    path.write_text(body + "\n" if body else "", encoding="utf-8")
    return path


def _root(given: Path | str | None) -> Path:
    return Path(given).resolve() if given else discover_root()


def write(key: str, value: Any, scope: str = "project", project_root: Path | str | None = None,
          home: Path | str | None = None, environ: Mapping[str, str] | None = None) -> Path:
    """Set one key in one file, creating the file when it is not there yet."""
    target = key_for(key)
    if target.secret:
        raise ValueError(f"{target.name} is a secret; write it to {DOTENV_NAME} with write_secret()")
    coerced = _coerce(target, value)
    if coerced is None:
        raise ValueError(f"{target.name} needs a value; use unset to remove it")
    path = scope_file(scope, _root(project_root), home, environ)
    return _rewrite(path, target.name, render(target, coerced), NEW_FILE_HEADER)


def unset(key: str, scope: str = "project", project_root: Path | str | None = None,
          home: Path | str | None = None, environ: Mapping[str, str] | None = None) -> Path:
    """Drop one key from the file that holds it. The secret is never in a settings
    file, so an unset of it rewrites `.env`: the one false success here that costs."""
    target = key_for(key)
    root = _root(project_root)
    if target.secret:
        return _rewrite(root / DOTENV_NAME, target.env, None, NEW_DOTENV_HEADER)
    return _rewrite(scope_file(scope, root, home, environ), target.name, None, NEW_FILE_HEADER)


def write_secret(name: str, value: str, project_root: Path | str | None = None) -> Path:
    """The API key into `<project>/.env`, mode 0600. The value is never logged."""
    key = key_for(name)
    if not key.secret:
        raise ValueError(f"{key.name} is not a secret; write it with write()")
    text = str(value).strip()
    if not text or "\n" in text:
        raise ValueError(f"{key.env} must be a single non-empty line")
    path = _root(project_root) / DOTENV_NAME
    if not path.is_file():   # 0600 before any content, not after: no world-readable window
        path.parent.mkdir(parents=True, exist_ok=True)
        os.close(os.open(path, os.O_CREAT | os.O_WRONLY, 0o600))
    _rewrite(path, key.env, f"{key.env}={text}", NEW_DOTENV_HEADER)
    path.chmod(0o600)
    return path
