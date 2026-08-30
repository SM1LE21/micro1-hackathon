"""The CLI's event stream, read as trace steps.

`claude -p --output-format stream-json --verbose` prints one JSON object per line:
a `system`/`init` line, an `assistant` line per model message, a `user` line
carrying the tool results of the message before it, and a final `result` line with
the run's totals. This module turns those into the fields
`docs/spec/00-contract.md` §Trace contract names, and nothing else: the driver
owns the step numbering, the budgets and the writer.

Two shapes the reader must survive. A message may arrive split across several
`assistant` lines that share one `message.id` (the CLI emits a line per content
group), so steps are merged by that id. And a `tool_result` block carries either a
string or a list of content blocks, so both are flattened to the text the trace
stores in full.

`request_hash` is null for a local brain: the request was assembled inside the
CLI and this process never saw the bytes it would hash (ADR 0008 item 1).

The `init` line is also read for what it says the CLI loaded. ADR 0008 item 2
requires the user's own memory to stay out of a measured run, and `--restricted`
is what keeps it out; `memory_paths` on that line is the CLI's own report of
whether it did. A run that starts with a memory path is stopped there rather than
scored, because a model carrying the author's notes about building this tool is
not measuring the same thing as one that is not.
"""

from __future__ import annotations

import json
from typing import Any

from art30 import llm

MCP_PREFIX = "mcp__art30__"
SUBMIT = "submit_record"


def parse(line: str) -> dict | None:
    """One stream line as an object, or None for a blank or non-JSON line."""
    text = line.strip()
    if not text:
        return None
    try:
        event = json.loads(text)
    except json.JSONDecodeError:
        return None
    return event if isinstance(event, dict) else None


def tool_name(name: str) -> str:
    """`mcp__art30__submit_record` is our tool: the trace records the name we serve."""
    return name[len(MCP_PREFIX):] if name.startswith(MCP_PREFIX) else name


def _blocks(content: Any) -> list[dict]:
    return [b for b in content if isinstance(b, dict)] if isinstance(content, list) else []


def _joined(blocks: list[dict], kind: str, field: str) -> str:
    return "\n".join(str(b.get(field, "")) for b in blocks if b.get("type") == kind).strip()


def flatten(content: Any) -> str:
    """A tool result's payload as text: a string, or the text of its blocks."""
    if isinstance(content, str):
        return content
    parts = []
    for block in _blocks(content):
        if block.get("type") == "text":
            parts.append(str(block.get("text", "")))
        else:
            parts.append(json.dumps(block, ensure_ascii=False, separators=(",", ":")))
    return "\n".join(parts)


def assistant_step(event: dict) -> dict:
    """One model message: its id, its blocks by kind, its stop reason and its usage."""
    message = event.get("message") if isinstance(event.get("message"), dict) else {}
    blocks = _blocks(message.get("content"))
    calls = [
        {"id": str(b.get("id") or ""), "name": tool_name(str(b.get("name") or "")),
         "input": b.get("input") if isinstance(b.get("input"), dict) else {}}
        for b in blocks if b.get("type") == "tool_use"
    ]
    return {
        "id": str(message.get("id") or event.get("uuid") or ""),
        "model": message.get("model") or event.get("model"),
        "reasoning": _joined(blocks, "thinking", "thinking"),
        "text": _joined(blocks, "text", "text"),
        # A message that is still waiting for tool results carries no stop_reason on
        # some CLI builds; check 12 requires one, and `tool_use` is what it was.
        "stop_reason": str(message.get("stop_reason") or ("tool_use" if calls else "end_turn")),
        "tool_calls": calls,
        "usage": llm.usage_of(message.get("usage") or {}),
        "cache_1h": cache_1h(message.get("usage") or {}),
    }


def cache_1h(usage: Any) -> int:
    """The part of the cache write made at the one-hour TTL, which prices differently."""
    block = usage.get("cache_creation") if isinstance(usage, dict) else None
    value = block.get("ephemeral_1h_input_tokens") if isinstance(block, dict) else 0
    return int(value) if isinstance(value, int) and value > 0 else 0


def tool_results(event: dict) -> list[dict]:
    """The `tool_result` blocks of a user line, in the trace's shape."""
    message = event.get("message") if isinstance(event.get("message"), dict) else {}
    out = []
    for block in _blocks(message.get("content")):
        if block.get("type") != "tool_result":
            continue
        output = flatten(block.get("content"))
        out.append({
            "call_id": str(block.get("tool_use_id") or ""),
            "output": output,
            "is_error": bool(block.get("is_error")) or _rejected(output),
            "bytes": len(output.encode("utf-8")),
        })
    return out


def _rejected(output: str) -> bool:
    """A verifier rejection is an error result whether or not the CLI said so."""
    try:
        payload = json.loads(output)
    except (json.JSONDecodeError, TypeError):
        return False
    return isinstance(payload, dict) and payload.get("accepted") is False


def result_totals(event: dict) -> dict:
    """The final `result` line: what the CLI says the run cost and why it ended."""
    usage = event.get("usage") if isinstance(event.get("usage"), dict) else {}
    cost = event.get("total_cost_usd")
    return {
        "subtype": str(event.get("subtype") or ""),
        "is_error": bool(event.get("is_error")),
        "num_turns": event.get("num_turns"),
        "total_cost_usd": float(cost) if isinstance(cost, (int, float)) else None,
        "usage": llm.usage_of(usage),
        "cache_1h": cache_1h(usage),
        "text": str(event.get("result") or "")[:500],
    }


def init_model(event: dict) -> str | None:
    """The model the `system`/`init` line names, when it names one."""
    model = event.get("model")
    return str(model) if isinstance(model, str) and model else None


def init_memory(event: dict) -> list[str]:
    """The memory directories the `init` line says it loaded. Empty is the only pass."""
    paths = event.get("memory_paths")
    if isinstance(paths, dict):
        return sorted(str(v) for v in paths.values() if v)
    if isinstance(paths, list):
        return sorted(str(v) for v in paths if v)
    return [str(paths)] if isinstance(paths, str) and paths else []


class Stepper:
    """The stream as a sequence of finished steps, with the two budgets applied.

    A step closes when the next model message opens or when the stream ends, which
    is the point at which its tool results have all arrived: the API cannot send a
    second assistant message before the first one's results are back. A call that
    neither budget can buy is dropped from the step it appeared in as well as
    stopping the run, so `run_end.tool_calls_total` and `submits` stay equal to what
    the step lines show (06-traces.md checks 7 and 8).
    """

    def __init__(self, tool_budget: int, submit_budget: int, max_turns: int) -> None:
        self.tool_budget, self.submit_budget, self.max_turns = tool_budget, submit_budget, max_turns
        self.tool_calls = 0
        self.submits = 0
        self.steps = 0
        self.model: str | None = None
        self.memory: list[str] = []
        self.totals: dict = {}
        self.stop: tuple[str, str] | None = None
        self._open: dict | None = None

    def feed(self, event: dict | None) -> list[dict]:
        """The steps this event finished. Usually none, sometimes the one before it."""
        if not isinstance(event, dict):
            return []
        kind = event.get("type")
        if kind == "system":
            self.model = init_model(event) or self.model
            self.memory = init_memory(event) or self.memory
            if self.memory and self.stop is None:
                # Not a measurement any more: see the module docstring.
                self.stop = ("api_error", "the CLI loaded memory from "
                             f"{', '.join(self.memory)}; a measured run loads none")
            return []
        if kind == "result":
            self.totals = result_totals(event)
            return []
        if kind == "user":
            self._attach(tool_results(event))
            return []
        if kind != "assistant":
            return []
        step = assistant_step(event)
        self.model = step.get("model") or self.model
        done: list[dict] = []
        if self._open is not None and step["id"] and step["id"] == self._open["id"]:
            self._merge(step)
        else:
            done = self.close()
            self._open = {**step, "tool_calls": [], "tool_results": []}
            self.steps += 1
            if self.steps > self.max_turns and self.stop is None:
                self.stop = ("budget_exhausted",
                             f"max_turns {self.max_turns} reached at step {self.steps}")
        self._buy(step["tool_calls"])
        return done

    def close(self) -> list[dict]:
        """The open step, if there is one. Called once when the stream ends."""
        step, self._open = self._open, None
        return [step] if step is not None else []

    def _merge(self, step: dict) -> None:
        assert self._open is not None
        for field in ("reasoning", "text"):
            self._open[field] = "\n".join(p for p in (self._open[field], step[field]) if p)
        self._open["stop_reason"] = step["stop_reason"]
        if any(step["usage"].values()):
            self._open["usage"] = step["usage"]
            self._open["cache_1h"] = step["cache_1h"]

    def _buy(self, calls: list[dict]) -> None:
        assert self._open is not None
        for index, call in enumerate(calls):
            if self.tool_calls >= self.tool_budget:
                self._halt("budget_exhausted", _budget_note(self, calls[: index + 1]))
                return
            if call["name"] == SUBMIT and self.submits >= self.submit_budget:
                self._halt("max_submits", f"{self.submit_budget} submit_record attempts used")
                return
            self.tool_calls += 1
            self.submits += 1 if call["name"] == SUBMIT else 0
            self._open["tool_calls"].append(call)

    def _halt(self, condition: str, note: str) -> None:
        if self.stop is None:
            self.stop = (condition, note)

    def _attach(self, results: list[dict]) -> None:
        if self._open is None:
            return
        known = {call["id"] for call in self._open["tool_calls"]}
        self._open["tool_results"] += [r for r in results if r["call_id"] in known]


def _budget_note(stepper: Stepper, calls: list[dict]) -> str:
    names = ", ".join(c["name"] for c in calls[-3:])
    return (f"budget {stepper.tool_budget} exhausted at step {stepper.steps};"
            f" last 3 calls: {names}; submits={stepper.submits}")


# --- the codex branch -------------------------------------------------------------------------
# `codex exec --json` prints a different stream and `art30/brains/codex_events.py`
# reads it. Only the seam the driver needs from both brains lives here.
CODEX_TOOL_ITEMS = ("mcp_tool_call", "command_execution", "file_change")


def is_tool_result(event: object) -> bool:
    """True for the stream event that hands a tool's result back to the model.

    The driver reads the spool after one of these, which is where a submission the
    arm has already answered becomes visible to this process. `claude` carries them
    on its `user` lines; `codex` carries each one on the item that completed.
    """
    if not isinstance(event, dict):
        return False
    if event.get("type") == "user":
        return True
    item = event.get("item") if event.get("type") == "item.completed" else None
    return isinstance(item, dict) and item.get("type") in CODEX_TOOL_ITEMS
