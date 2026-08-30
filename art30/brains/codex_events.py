"""`codex exec --json` read as trace steps.

The stream is nothing like the `claude` one, so it gets its own reader rather than
a branch inside `convert.py`. What codex prints, captured from a real run on
2026-08-30 with codex-cli 0.148.0 (`shapes.jsonl` beside this repository's scratch
output):

    {"type":"thread.started","thread_id":"01a0..."}
    {"type":"turn.started"}
    {"type":"item.started","item":{"id":"item_0","type":"command_execution",...}}
    {"type":"item.completed","item":{"id":"item_0",...,"aggregated_output":"...",
                                     "exit_code":0,"status":"completed"}}
    {"type":"item.completed","item":{"id":"item_1","type":"mcp_tool_call",
                                     "server":"art30","tool":"submit_record",
                                     "arguments":{...},"result":{"content":[...]},
                                     "error":null,"status":"failed"}}
    {"type":"item.completed","item":{"id":"item_2","type":"agent_message","text":"..."}}
    {"type":"turn.completed","usage":{"input_tokens":44902,"cached_input_tokens":39168,
                                      "cache_write_input_tokens":0,"output_tokens":273,
                                      "reasoning_output_tokens":97}}

Three things are missing from it that the `claude` stream has, and each one shapes
this file:

- **No message boundaries.** There is no assistant line, so a step is rebuilt from
  the items: reasoning and text accumulate into the open step, a tool call closes
  it. One tool call per step is what the stream can support honestly, and it keeps
  every `tool_result` in the same step as its call (06-traces.md check 4).
- **No per-item usage.** `turn.completed` reports the run and nothing else, so
  every step's usage is zero and the last one carries the whole run -- the same
  settlement `driver.py` already does for the `claude` brain's placeholder output
  counts, through the same `Stepper.totals` seam.
- **No model name.** Nothing in the stream says which model answered, so
  `Stepper.model` stays whatever `codex_model` configured, which is also the only
  name `codex_prices` could be keyed by.

`file_change` is in the item table because it must be impossible to miss: the
sandbox is `read-only` and a write should never appear, so if one does it is
recorded as an error result rather than dropped.
"""

from __future__ import annotations

import json

from art30.brains import convert
from art30.brains.convert import Stepper, flatten, tool_name

SHELL = "shell"                 # what the trace calls codex's own exec tool
READ_ONLY = "read-only"         # `-s read-only`; recorded on every shell call
NO_WRITES = '{"accepted":false,"reason":"the read-only sandbox does not permit a file change"}'
USAGE_KEYS = ("input", "cache_read", "cache_write", "output")


# --- one event --------------------------------------------------------------------------------
def usage_of(raw: object) -> dict[str, int]:
    """`turn.completed.usage` under the trace's four names.

    Codex reports `input_tokens` as the whole input; `cached_input_tokens` and
    `cache_write_input_tokens` are both read here as *parts* of it, so the three
    trace keys partition what codex called input and `input + cache_read +
    cache_write == input_tokens`. Reporting the write beside the total instead would
    charge those tokens twice on a priced run, because `codex_estimate` prices
    `cache_write` at the input rate on top of an `input` count that already holds
    them. Both real runs reported `cache_write_input_tokens: 0`, so this reading is
    the safe one rather than the confirmed one; the first run with a non-zero write
    settles it.
    """
    usage = raw if isinstance(raw, dict) else {}
    total = _count(usage.get("input_tokens"))
    cached = min(_count(usage.get("cached_input_tokens")), total)
    written = min(_count(usage.get("cache_write_input_tokens")), max(0, total - cached))
    return {"input": total - cached - written, "cache_read": cached,
            "cache_write": written, "output": _count(usage.get("output_tokens"))}


def reasoning_tokens(raw: object) -> int:
    """Reasoning tokens, which the contract's four usage keys have no home for."""
    return _count((raw if isinstance(raw, dict) else {}).get("reasoning_output_tokens"))


def _count(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    return int(value) if value > 0 else 0


def piece(item: object) -> dict | None:
    """One completed item as a piece of a step, or None for an item the trace ignores.

    `{"kind": "reasoning"|"text", "text": str}`, or
    `{"kind": "call", "call": {...}, "result": {...}}` in the trace's own shapes.
    """
    if not isinstance(item, dict):
        return None
    kind, ident = item.get("type"), str(item.get("id") or "")
    if kind == "reasoning":
        return {"kind": "reasoning", "text": _text_of(item)}
    if kind == "agent_message":
        return {"kind": "text", "text": _text_of(item)}
    if kind == "command_execution":
        output = str(item.get("aggregated_output") or "")
        code = item.get("exit_code")
        # A negative code is a signal, not a success: anything that is not a plain
        # zero is an error, including the `None` a command that never finished leaves.
        failed = item.get("status") != "completed" or not (
            isinstance(code, int) and not isinstance(code, bool) and code == 0)
        return _call(ident, SHELL, {"command": str(item.get("command") or ""),
                                    "sandbox": READ_ONLY}, output, failed)
    if kind == "mcp_tool_call":
        return _mcp(item, ident)
    if kind == "file_change":
        return _call(ident, "file_change",
                     {k: v for k, v in item.items() if k not in ("id", "type")}, NO_WRITES, True)
    return None


def _mcp(item: dict, ident: str) -> dict:
    """One `mcp_tool_call` item, under the name the server serves.

    A transport-level failure is written in the verifier's vocabulary
    (`{"accepted": false, ...}`) only for the verifier's own tool. Codex probes other
    servers' tools too -- the real D02 run spent a call on `list_mcp_resources` -- and
    an `accepted:false` on one of those would put a rejected *submission* shape in the
    trace for a protocol error, which `convert._rejected` then counts as a rejection
    that `verify_rounds` never saw.
    """
    error = item.get("error")
    result = item.get("result") if isinstance(item.get("result"), dict) else {}
    output = flatten(result.get("content")) if result else ""
    name = tool_name(str(item.get("tool") or ""))
    if isinstance(error, dict) and error.get("message"):
        message = str(error["message"])
        output = output or (json.dumps({"accepted": False, "reason": message},
                                       ensure_ascii=False, separators=(",", ":"))
                            if name == convert.SUBMIT else message)
    # `status` reads "failed" on a rejected submission as well as on a broken call,
    # so the two are not distinguished here: both are an error result to the model.
    failed = (item.get("status") != "completed" or error is not None
              or convert._rejected(output))
    return _call(ident, name, _arguments(item.get("arguments")), output, failed)


def _arguments(raw: object) -> dict:
    """A tool call's arguments, whether the build sent an object or a JSON string.

    0.148.0 sends an object. A build that sent the string form would otherwise record
    `input: {}` for a `submit_record` call whose record is sitting in
    `submissions.jsonl` -- a silent hole in the deliverable trace.
    """
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return raw if isinstance(raw, dict) else {}


def _call(ident: str, name: str, arguments: dict, output: str, is_error: bool) -> dict:
    return {"kind": "call",
            "call": {"id": ident, "name": name, "input": arguments},
            "result": {"call_id": ident, "output": output, "is_error": bool(is_error),
                       "bytes": len(output.encode("utf-8"))}}


def _text_of(item: dict) -> str:
    """`text` on every shape seen so far. `summary` is read too, because a build with
    reasoning summaries turned on carries the reasoning item's text under that name."""
    for field in ("text", "summary", "content"):
        value = item.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, list):
            joined = "\n".join(str(v.get("text", "")) if isinstance(v, dict) else str(v)
                               for v in value).strip()
            if joined:
                return joined
    return ""


# --- the stream -------------------------------------------------------------------------------
class CodexStepper(Stepper):
    """The codex stream as steps. Budgets, halting and `close` come from `Stepper`.

    A step stays open until an item arrives that cannot join it, which is any item
    at all once it already carries a tool call. So reasoning and text accumulate,
    the call that follows them closes the exchange, and the run's last step is left
    open until EOF -- which is what makes it the one `driver._usage` settles the
    run's token totals on.
    """

    def __init__(self, tool_budget: int, submit_budget: int, max_turns: int) -> None:
        super().__init__(tool_budget, submit_budget, max_turns)
        self.thread_id: str | None = None
        self.reasoning_tokens = 0
        self.last_error: str | None = None

    def feed(self, event: dict | None) -> list[dict]:
        if not isinstance(event, dict):
            return []
        kind = event.get("type")
        if kind == "thread.started":
            self.thread_id = str(event.get("thread_id") or "") or None
            return []
        if kind == "turn.completed":
            # A turn's usage is that turn's, not the run's. `codex exec` emitted one
            # turn on every run seen so far, but a resumed thread or an auto-compaction
            # turn would make a replacing assignment throw away everything before it --
            # and the trace would still validate while understating the run.
            seen = (self.totals.get("usage") or {}) if self.totals else {}
            fresh = usage_of(event.get("usage"))
            self.totals = {"usage": {k: seen.get(k, 0) + fresh[k] for k in fresh},
                           "cache_1h": 0, "total_cost_usd": None}
            self.reasoning_tokens += reasoning_tokens(event.get("usage"))
            return []
        if kind == "turn.failed":
            self._halt("api_error", f"codex reported {_failure(event)}"[:300])
            return []
        if kind == "error":
            # Not a stop. Codex prints an `error` line for a retry too ("Reconnecting...
            # 2/5"), and a run that recovers from one is a run that finished. It is kept
            # so a run that does *not* recover ends with the CLI's own words in the note
            # rather than a bare `no_submission`.
            self.last_error = _failure(event)[:200]
            return []
        if kind != "item.completed":
            return []
        part = piece(event.get("item"))
        if part is None:
            return []
        done = self._begin()
        self._absorb(part)
        return done

    def _begin(self) -> list[dict]:
        """The finished step, if this item cannot go into the open one."""
        if self._open is not None and not self._open["tool_calls"]:
            return []
        done = self.close()
        self._open = {"id": f"step-{self.steps + 1}", "model": self.model, "reasoning": "",
                      "text": "", "stop_reason": "end_turn", "tool_calls": [],
                      "tool_results": [], "usage": {k: 0 for k in USAGE_KEYS}, "cache_1h": 0}
        self.steps += 1
        if self.steps > self.max_turns and self.stop is None:
            self.stop = ("budget_exhausted",
                         f"max_turns {self.max_turns} reached at step {self.steps}")
        return done

    def _absorb(self, part: dict) -> None:
        assert self._open is not None
        if part["kind"] in ("reasoning", "text"):
            field = "reasoning" if part["kind"] == "reasoning" else "text"
            self._open[field] = "\n".join(p for p in (self._open[field], part["text"]) if p)
            return
        call = part["call"]
        self._buy([call])
        # `_buy` drops a call neither budget could pay for; its result goes with it,
        # so `run_end.tool_calls_total` still equals what the step lines show.
        if any(bought["id"] == call["id"] for bought in self._open["tool_calls"]):
            self._open["tool_results"].append(part["result"])
            self._open["stop_reason"] = "tool_use"


def _failure(event: dict) -> str:
    error = event.get("error")
    if isinstance(error, dict):
        return str(error.get("message") or error)
    return str(error or event.get("message") or "a turn failure with no message")
