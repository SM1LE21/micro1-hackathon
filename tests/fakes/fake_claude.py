"""A fake `claude` binary: the real CLI's event stream, from a scripted conversation.

The shapes printed here were taken from a real
`claude -p --output-format stream-json --verbose` run against `evals/fixtures/
synthetic/D02` (saved beside this repository's scratch output as `shapes.jsonl`):
a `system`/`init` line, one `assistant` line per model message with `message.usage`,
a `user` line carrying the `tool_result` blocks of the message before it, and a
final `result` line with `total_cost_usd` and the run's usage.

What is real about this fake is the MCP half: every `submit_record` turn is a real
`tools/call` to `art30/brains/mcp_server.py`, spawned from the `--mcp-config` the
driver wrote, so the tool results in the stream are the arm's own answers.

The script is a JSON file named by `ART30_FAKE_CLAUDE_SCRIPT`:

    {"model": ..., "exit_code": 0, "stderr": "", "total_cost_usd": 0.4,
     "turns": [{"thinking": ..., "text": ..., "usage": {...},
                "calls": [{"name": "Read", "input": {...}, "result": "..."},
                          {"name": "mcp__art30__submit_record", "record_file": "..."}]}]}

`ART30_FAKE_CLAUDE_ARGV` names a file the fake writes its own argv to, which is how
`tests/test_brain_claude.py` checks the isolation flags without a real CLI.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path

from tests.fakes.mcp_client import McpClient

SCRIPT_VAR = "ART30_FAKE_CLAUDE_SCRIPT"
ARGV_VAR = "ART30_FAKE_CLAUDE_ARGV"
SUBMIT = "mcp__art30__submit_record"
# The real CLI's per-message usage: complete input and cache counts, a placeholder
# output count, and a cache write made at the one-hour TTL (see shapes.jsonl).
DEFAULT_USAGE = {"input_tokens": 2, "cache_creation_input_tokens": 1200,
                 "cache_read_input_tokens": 3400, "output_tokens": 1}
USAGE_KEYS = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens",
              "output_tokens")


def _emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def _flag(argv: list[str], name: str) -> str | None:
    return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else None


def _server(mcp_config: str | None) -> McpClient | None:
    if not mcp_config:
        return None
    spec = json.loads(Path(mcp_config).read_text(encoding="utf-8"))["mcpServers"]["art30"]
    client = McpClient([spec["command"], *spec["args"]])
    client.initialize()
    return client


def _record(call: dict) -> dict:
    if call.get("record_file"):
        return json.loads(Path(call["record_file"]).read_text(encoding="utf-8"))
    return call.get("record") or {}


def _groups(turn: dict, calls: list[dict]) -> list[list[dict]]:
    """The block groups of one message. The real CLI prints one line per group, all
    of them carrying the same `message.id` and the same usage (shapes.jsonl)."""
    groups: list[list[dict]] = []
    if turn.get("thinking"):
        groups.append([{"type": "thinking", "thinking": turn["thinking"], "signature": "fake"}])
    if turn.get("text"):
        groups.append([{"type": "text", "text": turn["text"]}])
    groups += [[{"type": "tool_use", "id": call["id"], "name": call["name"],
                 "input": call.get("input") or {"record": call.get("_record", {})}}]
               for call in calls]
    return groups or [[{"type": "text", "text": ""}]]


def _usage(turn: dict) -> dict:
    raw = {**DEFAULT_USAGE, **(turn.get("usage") or {})}
    written = raw["cache_creation_input_tokens"]
    return {**raw, "cache_creation": {"ephemeral_5m_input_tokens": 0,
                                      "ephemeral_1h_input_tokens": written},
            "service_tier": "standard"}


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if ARGV_VAR in os.environ:
        Path(os.environ[ARGV_VAR]).write_text(json.dumps(args, indent=1), encoding="utf-8")
    script = json.loads(Path(os.environ[SCRIPT_VAR]).read_text(encoding="utf-8"))
    model = script.get("model") or "claude-opus-5"
    session = str(uuid.uuid4())
    server = _server(_flag(args, "--mcp-config"))
    spent = {key: 0 for key in USAGE_KEYS}
    _emit({"type": "system", "subtype": "init", "cwd": os.getcwd(), "session_id": session,
           "tools": ["Read", "Grep", "Glob", SUBMIT], "model": model,
           "mcp_servers": [{"name": "art30", "status": "connected"}],
           # Null on a `--restricted` run and a dict of directories without it; the
           # driver refuses the second, so the script can ask for either.
           "memory_paths": script.get("memory_paths"),
           "permissionMode": "default", "apiKeySource": "none"})
    for turn in script.get("turns") or []:
        _turn(turn, model, session, server, spent)
    if server is not None:
        server.close()
    _emit({"type": "result", "subtype": script.get("subtype") or "success",
           "is_error": bool(script.get("is_error")), "duration_ms": 1200,
           "duration_api_ms": 900, "num_turns": len(script.get("turns") or []),
           "result": "done", "session_id": session,
           "total_cost_usd": script.get("total_cost_usd", 0.0),
           "usage": _totals(spent, script)})
    if script.get("stderr"):
        print(script["stderr"], file=sys.stderr, flush=True)
    return int(script.get("exit_code") or 0)


def _totals(spent: dict, script: dict) -> dict:
    """The run's own totals. The output count is the one the messages never carried."""
    written = spent["cache_creation_input_tokens"]
    return {**spent, "output_tokens": script.get("output_total", spent["output_tokens"]),
            "cache_creation": {"ephemeral_5m_input_tokens": 0,
                               "ephemeral_1h_input_tokens": written}}


def _turn(turn: dict, model: str, session: str, server: McpClient | None,
          spent: dict) -> None:
    calls = [dict(call, id=call.get("id") or f"toolu_{uuid.uuid4().hex[:12]}")
             for call in (turn.get("calls") or [])]
    for call in calls:
        if call["name"] == SUBMIT:
            call["_record"] = _record(call)
    usage = _usage(turn)
    for key in USAGE_KEYS:
        spent[key] += usage[key]
    message_id = f"msg_{uuid.uuid4().hex[:12]}"
    for group in _groups(turn, calls):
        _emit({"type": "assistant", "parent_tool_use_id": None, "session_id": session,
               "message": {"id": message_id, "type": "message", "role": "assistant",
                           "model": model, "content": group,
                           # The real CLI leaves this null on every assistant line.
                           "stop_reason": None, "stop_sequence": None, "usage": usage}})
    _emit({"type": "system", "subtype": "thinking_tokens", "estimated_tokens": 64,
           "estimated_tokens_delta": 64, "session_id": session})
    if not calls:
        return
    results = []
    for call in calls:
        if call["name"] == SUBMIT and server is not None:
            text, is_error = server.submit(call["_record"])
        else:
            text, is_error = str(call.get("result", "ok")), bool(call.get("is_error"))
        results.append({"type": "tool_result", "tool_use_id": call["id"],
                        "content": [{"type": "text", "text": text}], "is_error": is_error})
    _emit({"type": "user", "parent_tool_use_id": None, "session_id": session,
           "message": {"role": "user", "content": results}})


if __name__ == "__main__":   # pragma: no cover - the wrapper script calls main()
    sys.exit(main())
