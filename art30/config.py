"""Run configuration: defaults, environment overrides, `.env` reading.

Never holds the API key: the client resolves `ANTHROPIC_API_KEY` from the
process environment, so nothing that gets serialised can carry it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal, Mapping

DEFAULT_MODEL = "claude-opus-5"
DEFAULT_EFFORT = "high"
DEFAULT_MAX_TOKENS = 32_000
DEFAULT_SUBMIT_BUDGET = 5

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

    def trace_config(self) -> dict:
        """The `run_start` line's `config` object and `provenance.config`."""
        return {
            "max_tokens": self.max_tokens,
            "tool_budget": self.tool_budget,
            "submit_budget": self.max_submits,
            "overridden": list(self.overridden),
        }

    def for_case_kind(self, kind: str) -> "Config":
        """Tool budget from the case kind, unless the environment set it."""
        if "ART30_TOOL_BUDGET" in self.overridden:
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


def _int(env: Mapping[str, str], name: str, default: int) -> int:
    raw = env.get(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        raise ConfigError(f"{name} must be a whole number, got {raw!r}") from None


def _float(env: Mapping[str, str], name: str) -> float | None:
    raw = env.get(name)
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        raise ConfigError(f"{name} must be a number, got {raw!r}") from None


def _choice(env: Mapping[str, str], name: str, default: str, allowed: tuple[str, ...]) -> str:
    value = env.get(name) or default
    if value not in allowed:
        raise ConfigError(f"{name} must be one of {', '.join(allowed)}, got {value!r}")
    return value


def load(overrides: Mapping[str, object] | None = None) -> Config:
    """Defaults, then `.env`, then the environment, then explicit overrides.

    `.env` values are pushed into `os.environ` with `setdefault` so a variable
    already present always wins and the SDK can find the key without this
    module ever reading it.
    """
    for key, value in read_dotenv().items():
        os.environ.setdefault(key, value)
    env = os.environ

    cfg = Config(
        model=env.get("ART30_MODEL") or DEFAULT_MODEL,
        effort=env.get("ART30_EFFORT") or DEFAULT_EFFORT,
        max_tokens=_int(env, "ART30_MAX_TOKENS", DEFAULT_MAX_TOKENS),
        mode=_choice(env, "ART30_MODE", "live", ("live", "replay")),  # type: ignore[arg-type]
        record=env.get("ART30_RECORD") == "1",
        tool_budget=_int(env, "ART30_TOOL_BUDGET", TOOL_BUDGET_BY_KIND["synthetic"]),
        max_submits=_int(env, "ART30_SUBMIT_BUDGET", DEFAULT_SUBMIT_BUDGET),
        max_usd=_float(env, "ART30_MAX_USD"),
        concurrency=_int(env, "ART30_CONCURRENCY", 4),
        cache_dir=Path(env.get("ART30_CACHE_DIR") or "evals/cache"),
        trace_dir=Path(env.get("ART30_TRACE_DIR") or "traces"),   # the harness sets it per cell (01-architecture.md section 9)
        unlock_test=env.get("ART30_UNLOCK_TEST") == "1",
        reproducible=env.get("ART30_REPRODUCIBLE") == "1",
        overridden=tuple(name for name in REQUEST_VARS if env.get(name)),
    )
    if overrides:
        cfg = replace(cfg, **dict(overrides))  # type: ignore[arg-type]
    return cfg
