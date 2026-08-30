"""Run configuration: one `Config` for a run, resolved through the settings layer.

The user-facing values (brain, model, effort, the budgets) come from
`art30.settings`, so the CLI, the harness and the website read one set of files
in one order (ADR 0008 item 5). The run switches that are not settings —
`ART30_MODE`, `ART30_RECORD`, `ART30_TRACE_DIR`, `ART30_CACHE_DIR`,
`ART30_UNLOCK_TEST`, `ART30_REPRODUCIBLE`, `ART30_IGNORE_SETTINGS_FILES` — stay
environment-only, because they are the seams the harness pins per cell and a
settings file must not reach them.

Never holds the API key: the client resolves `ANTHROPIC_API_KEY` from the
process environment, so nothing that gets serialised can carry it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal, Mapping

from art30 import settings

DEFAULT_MODEL = "claude-opus-5"
DEFAULT_EFFORT = "high"
DEFAULT_MAX_TOKENS = 32_000
DEFAULT_SUBMIT_BUDGET = 5
DEFAULT_BRAIN = "api"
DEFAULT_MAX_TURNS = 60
# The settings key each brain reads its own model from (ADR 0008 item 1).
BRAIN_MODEL_KEY = {"claude": "claude_model", "codex": "codex_model"}

# contract section Budgets: 60 tool calls on a synthetic case, 120 on a real one.
TOOL_BUDGET_BY_KIND: dict[str, int] = {"synthetic": 60, "real": 120}

# The five variables that change a request. `provenance.config.overridden`
# names the ones actually set (07-ui.md section 1); ART30_MAX_USD is not among them
# because a ceiling nobody hit changed nothing about the run.
REQUEST_VARS: tuple[str, ...] = (
    "ART30_EFFORT",
    "ART30_MAX_TOKENS",
    "ART30_MODEL",
    "ART30_SUBMIT_BUDGET",
    "ART30_TOOL_BUDGET",
)


class ConfigError(RuntimeError):
    """A configuration value is missing, unparseable or out of its enum."""


@dataclass(frozen=True)
class Config:
    model: str = DEFAULT_MODEL
    effort: str = DEFAULT_EFFORT
    max_tokens: int = DEFAULT_MAX_TOKENS
    mode: Literal["live", "replay"] = "live"
    record: bool = False
    tool_budget: int = TOOL_BUDGET_BY_KIND["synthetic"]
    max_submits: int = DEFAULT_SUBMIT_BUDGET
    max_usd: float | None = None
    approve: Literal["ask", "auto", "file"] = "ask"   # "file": the website's gate (ADR 0007)
    concurrency: int = 4
    cache_dir: Path = Path("evals/cache")
    out_dir: Path = Path("results/runs")
    trace_dir: Path = Path("traces")
    unlock_test: bool = False
    reproducible: bool = False
    overridden: tuple[str, ...] = ()
    # The request variables a layer named, whatever value it named. `overridden` is
    # by value and is what the trace prints; this is only what `for_case_kind` asks.
    explicit: tuple[str, ...] = ()
    brain: Literal["api", "claude", "codex"] = DEFAULT_BRAIN
    brain_model: str | None = None   # the local CLI's --model; the API brain uses `model`
    max_turns: int = DEFAULT_MAX_TURNS

    def trace_config(self) -> dict:
        """The `run_start` line's `config` object and `provenance.config`.

        `brain` appears only when the run was not the API one. Every recorded
        trace and the contract in `docs/spec/06-traces.md` describe an API run,
        and a key that always reads `api` would say nothing about it.
        """
        config = {
            "max_tokens": self.max_tokens,
            "tool_budget": self.tool_budget,
            "submit_budget": self.max_submits,
            "overridden": list(self.overridden),
        }
        if self.brain != DEFAULT_BRAIN:
            config["brain"] = self.brain
        return config

    def for_case_kind(self, kind: str) -> "Config":
        """Tool budget from the case kind, unless a layer named one."""
        if "ART30_TOOL_BUDGET" in self.explicit:
            return self
        return replace(self, tool_budget=budget_for_kind(kind))


def budget_for_kind(kind: str) -> int:
    try:
        return TOOL_BUDGET_BY_KIND[kind]
    except KeyError:
        raise ConfigError(f"no tool budget for case kind {kind!r}") from None


def read_dotenv(path: Path = Path(".env")) -> dict[str, str]:
    """`KEY=value` lines, `#` comments. No interpolation, no export syntax."""
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key:
            values[key] = value.strip()
    return values


def _choice(env: Mapping[str, str], name: str, default: str, allowed: tuple[str, ...]) -> str:
    value = env.get(name) or default
    if value not in allowed:
        raise ConfigError(f"{name} must be one of {', '.join(allowed)}, got {value!r}")
    return value


def load(overrides: Mapping[str, object] | None = None) -> Config:
    """The settings layer, then the run switches, then explicit overrides.

    `.env` is read from the project root the settings layer found, not from the
    working directory, so a command run inside a subdirectory of a checkout sees
    the same file `art30 config list` names. Its values are then pushed into
    `os.environ` with `setdefault`, so a variable already present always wins and
    the SDK can find the key without this module ever reading it.
    """
    dotenv = read_dotenv(settings.discover_root() / settings.DOTENV_NAME)
    env = os.environ
    try:
        resolved = settings.read(environ=env, dotenv=dotenv)
    except ValueError as exc:   # the settings layer's vocabulary, this module's exception type
        raise ConfigError(str(exc)) from None
    for key, value in dotenv.items():   # after the read, so `.env` keeps its own layer label
        env.setdefault(key, value)
    values = resolved.values
    brain = str(values["brain"])
    cfg = Config(
        model=values["model"],
        effort=values["effort"],
        max_tokens=values["max_tokens"],
        mode=_choice(env, "ART30_MODE", "live", ("live", "replay")),  # type: ignore[arg-type]
        record=env.get("ART30_RECORD") == "1",
        tool_budget=values["tool_budget"],
        max_submits=values["submit_budget"],
        max_usd=values["max_usd"],
        approve=values["approve"],
        concurrency=values["concurrency"],
        cache_dir=Path(env.get("ART30_CACHE_DIR") or "evals/cache"),
        trace_dir=Path(env.get("ART30_TRACE_DIR") or "traces"),   # the harness sets it per cell (01-architecture.md section 9)
        unlock_test=env.get("ART30_UNLOCK_TEST") == "1",
        reproducible=env.get("ART30_REPRODUCIBLE") == "1",
        overridden=_overridden(resolved),
        explicit=_explicit(resolved),
        brain=brain,   # type: ignore[arg-type]
        brain_model=values.get(BRAIN_MODEL_KEY.get(brain, "")),
        max_turns=values["max_turns"],
    )
    if overrides:
        cfg = replace(cfg, **dict(overrides))  # type: ignore[arg-type]
    return cfg


def _overridden(resolved: "settings.Settings") -> tuple[str, ...]:
    """The request variables whose value is not the default one, by env name.

    A value set in `art30.toml` counts: what the trace and `provenance.config`
    are for is that a run at non-default settings cannot be read as a reported
    one, and the file is as capable of moving a request as the variable is. The
    comparison is on the value, not on the layer, so copying the defaults
    `art30.toml.example` ships declares nothing: a run at the default settings is
    the default run whichever file spelled it out.
    """
    names = []
    for name in REQUEST_VARS:
        key = settings.key_for(name)
        if resolved.values.get(key.name, key.default) != key.default:
            names.append(name)
    return tuple(names)


def _explicit(resolved: "settings.Settings") -> tuple[str, ...]:
    """The request variables a layer named at all. `tool_budget = 60` on a real case
    is a choice of 60, and the case kind must not raise it to 120 behind the user."""
    return tuple(
        name for name in REQUEST_VARS
        if resolved.sources.get(settings.key_for(name).name, "default") != "default"
    )
