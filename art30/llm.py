"""Request assembly, canonical hashing, the record/replay cache, usage to cost.

In replay mode no client is constructed and no socket is opened: `make
eval-replay` needs no API key, which is the property REPRODUCE.md sells.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

from art30.config import Config, ConfigError

CANON: dict[str, Any] = {"sort_keys": True, "separators": (",", ":"), "ensure_ascii": False}
CACHE_CONTROL = {"type": "ephemeral"}
THINKING = {"type": "adaptive", "display": "summarized"}
HASH_PREFIX = "sha256:"

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
INCLUDE_MARKER = "<!-- include: taxonomy.md -->"

# Keyed by model id: ART30_MODEL is overridable for cost experiments, and an
# unkeyed table would report Opus 5 dollars for a Sonnet 5 run, silently.
_IO_USD_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-opus-5": (5.0, 25.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-haiku-4-5": (1.0, 5.0),
}


class LlmError(RuntimeError):
    """A call failed. `kind` is the `stop_condition` the loop should write."""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind


class ReplayMiss(RuntimeError):
    """The slot, both hashes, and the values that most often moved one.

    01-architecture.md section 4.5 wants the model, the effort and both budgets
    by value: two bare 64-hex strings leave the reader a bisect.
    """

    def __init__(
        self,
        slot: "Slot",
        expected: str | None,
        got: str,
        cfg: Config,
        entry: Mapping[str, Any] | None = None,
    ) -> None:
        where = f"{slot.case}/{slot.arm}/s{slot.seed}/{slot.step:02d}"
        detail = "no cache entry" if expected is None else f"expected {expected}"
        drift = [
            f"{key}={entry[key]}"
            for key in ("model", "effort")
            if entry and entry.get(key) and str(entry[key]) != getattr(cfg, key)
        ]
        super().__init__(
            f"replay miss at {where}: {detail}, computed {got}"
            f"; configured model={cfg.model} effort={cfg.effort}"
            f" tool_budget={cfg.tool_budget} submit_budget={cfg.max_submits}"
            + (f"; recorded with {' '.join(drift)}" if drift else "")
        )
        self.slot = slot
        self.expected = expected
        self.got = got


@dataclass(frozen=True)
class Response:
    content: list[dict]
    stop_reason: str
    stop_details: dict | None
    usage: dict[str, int]
    request_id: str | None


@dataclass(frozen=True)
class Slot:
    case: str
    arm: str
    seed: int
    step: int


@lru_cache(maxsize=1)
def system_prompt() -> str:
    """`system.md` with `taxonomy.md` spliced in at the include marker."""
    system = (PROMPTS_DIR / "system.md").read_text(encoding="utf-8")
    taxonomy = (PROMPTS_DIR / "taxonomy.md").read_text(encoding="utf-8")
    if INCLUDE_MARKER not in system:
        raise ConfigError(f"system.md carries no {INCLUDE_MARKER!r} marker")
    return system.replace(INCLUDE_MARKER, taxonomy.rstrip("\n"))


def prompt_sha(text: str | None = None) -> str:
    """SHA-256 of the spliced instruction text: the trace's `prompt_sha`."""
    return hashlib.sha256((system_prompt() if text is None else text).encode("utf-8")).hexdigest()


def system_blocks() -> list[dict]:
    return [{"type": "text", "text": system_prompt()}]


def build_request(
    cfg: Config, system: list[dict], tools: tuple[dict, ...], messages: list[dict]
) -> dict:
    request = {
        "model": cfg.model,
        "max_tokens": cfg.max_tokens,
        "thinking": dict(THINKING),
        "output_config": {"effort": cfg.effort},
        "system": _marked(system),
        "tools": list(tools),
        "messages": messages,
    }
    _reject_floats(request, "")
    return request


def _marked(system: list[dict]) -> list[dict]:
    """Cache breakpoint A: the last system block, always. Returns a copy."""
    blocks = [dict(block) for block in system]
    if not blocks:
        raise ConfigError("the system prompt is empty")
    blocks[-1]["cache_control"] = dict(CACHE_CONTROL)
    return blocks


def _reject_floats(node: object, path: str) -> None:
    """No float may reach the wire: repr stability is not a thing to depend on."""
    if isinstance(node, float):
        raise ConfigError(f"float in the request body at {path or '/'}: {node!r}")
    if isinstance(node, dict):
        for key, value in node.items():
            _reject_floats(value, f"{path}/{key}")
    elif isinstance(node, (list, tuple)):
        for index, value in enumerate(node):
            _reject_floats(value, f"{path}/{index}")


def canonical(request: dict) -> str:
    return json.dumps(request, **CANON)


def request_hash(request: dict) -> str:
    return hashlib.sha256(canonical(request).encode("utf-8")).hexdigest()


def prices(model: str) -> dict[str, float]:
    if model not in _IO_USD_PER_MTOK:
        raise ConfigError(f"no price table for {model}")
    inp, out = _IO_USD_PER_MTOK[model]
    return {"input": inp, "cache_write": inp * 1.25, "cache_read": inp * 0.10, "output": out}


def cost_of(usage: Mapping[str, int], model: str) -> float:
    price = prices(model)
    return (
        usage.get("input", 0) * price["input"]
        + usage.get("cache_write", 0) * price["cache_write"]
        + usage.get("cache_read", 0) * price["cache_read"]
        + usage.get("output", 0) * price["output"]
    ) / 1_000_000


def usage_of(raw: Mapping[str, Any]) -> dict[str, int]:
    """The API's four token counts under the trace's names."""
    return {
        "input": int(raw.get("input_tokens") or 0),
        "cache_read": int(raw.get("cache_read_input_tokens") or 0),
        "cache_write": int(raw.get("cache_creation_input_tokens") or 0),
        "output": int(raw.get("output_tokens") or 0),
    }


class Cache:
    """Path-addressed at `<case>/<arm>/s<seed>/<NN>.json`, hash-verified."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self._cleared: set[Path] = set()

    def slot_dir(self, slot: Slot) -> Path:
        return self.root / slot.case / slot.arm / f"s{slot.seed}"

    def path(self, slot: Slot) -> Path:
        return self.slot_dir(slot) / f"{slot.step:02d}.json"

    def read(
        self, slot: Slot, req_hash: str, cfg: Config
    ) -> tuple[dict, dict[str, int], str | None]:
        entry_path = self.path(slot)
        if not entry_path.is_file():
            raise ReplayMiss(slot, None, req_hash, cfg)
        entry = json.loads(entry_path.read_text(encoding="utf-8"))
        stored = str(entry.get("request_hash", ""))
        if stored.startswith(HASH_PREFIX):
            stored = stored[len(HASH_PREFIX) :]
        if stored != req_hash:
            raise ReplayMiss(slot, stored or None, req_hash, cfg, entry)
        message = entry.get("response") or {}
        usage = entry.get("usage") or usage_of(message.get("usage") or {})
        return message, {k: int(v) for k, v in usage.items()}, entry.get("request_id")

    def write(
        self,
        slot: Slot,
        req_hash: str,
        *,
        model: str,
        effort: str,
        request_id: str | None,
        message: dict,
        usage: dict[str, int],
    ) -> None:
        directory = self.slot_dir(slot)
        # The slot is exactly the run it recorded: a longer earlier recording
        # would otherwise leave higher-numbered files behind.
        if directory not in self._cleared:
            shutil.rmtree(directory, ignore_errors=True)
            self._cleared.add(directory)
        directory.mkdir(parents=True, exist_ok=True)
        entry = {
            "request_hash": HASH_PREFIX + req_hash,
            "model": model,
            "effort": effort,
            "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "request_id": request_id,
            "usage": usage,
            "response": message,
        }
        self.path(slot).write_text(json.dumps(entry, indent=1, sort_keys=True) + "\n", "utf-8")


_CACHES: dict[Path, Cache] = {}


def cache_for(root: Path) -> Cache:
    """One Cache per root per process, so the slot is cleared once per run."""
    key = Path(root).resolve()
    if key not in _CACHES:
        _CACHES[key] = Cache(root)
    return _CACHES[key]


@lru_cache(maxsize=1)
def _client(max_retries: int) -> Any:
    import anthropic  # imported here so replay never touches the SDK

    return anthropic.Anthropic(max_retries=max_retries)


def call(req: dict, *, cfg: Config, slot: Slot) -> Response:
    req_hash = request_hash(req)
    cache = cache_for(cfg.cache_dir)
    if cfg.mode == "replay":
        message, usage, request_id = cache.read(slot, req_hash, cfg)
        return _response(message, usage, request_id)
    message, usage, request_id = _live(req)
    if cfg.record:
        cache.write(
            slot,
            req_hash,
            model=cfg.model,
            effort=cfg.effort,
            request_id=request_id,
            message=message,
            usage=usage,
        )
    return _response(message, usage, request_id)


def _live(req: dict) -> tuple[dict, dict[str, int], str | None]:
    import anthropic

    try:
        with _client(4).messages.stream(**req) as stream:
            message = stream.get_final_message()
            # `_request_id` is set on a parsed top-level response only; the
            # stream's final message is accumulated from events and never
            # passes through that assignment. The header is on the stream.
            request_id = stream.request_id
    except anthropic.AnthropicError as exc:
        raise LlmError("api_error", f"{type(exc).__name__}: {exc}") from exc
    data = message.to_dict()
    return data, usage_of(data.get("usage") or {}), request_id


def _response(message: dict, usage: dict[str, int], request_id: str | None) -> Response:
    # stop_reason before content: a refusal returns 200 with an empty-shaped
    # content list, and code that indexes content[0] breaks on it. The three
    # stop_reason exits (refusal, max_tokens, pause_turn) belong to the loop,
    # which traces the step and its usage before it stops (02-agent-loop.md
    # section 1); raising here would lose both.
    return Response(
        content=list(message.get("content") or []),
        stop_reason=str(message.get("stop_reason") or ""),
        stop_details=message.get("stop_details"),
        usage=usage,
        request_id=request_id,
    )
