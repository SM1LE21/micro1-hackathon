"""A fake `codex` binary: the real CLI's event stream, from a scripted conversation.

The shapes printed here were taken from real `codex exec --json` runs against
`evals/fixtures/synthetic` on 2026-08-30 with codex-cli 0.148.0 (saved beside this
repository's scratch output as `shapes.jsonl`): a `thread.started` line, a
`turn.started` line, an `item.started`/`item.completed` pair per thing the model
did, and a final `turn.completed` carrying the run's five token counts.

What is real about this fake is the MCP half. The `-c mcp_servers.art30.command`
and `-c mcp_servers.art30.args` overrides the driver put on the command line are
parsed back out of argv and used to spawn `art30/brains/mcp_server.py`, so every
`submit_record` item in the stream carries the arm's own answer.

The script is a JSON file named by `ART30_FAKE_CODEX_SCRIPT`:

    {"exit_code": 0, "stderr": "",
     "usage": {"input_tokens": 44902, "cached_input_tokens": 39168,
               "cache_write_input_tokens": 0, "output_tokens": 273,
               "reasoning_output_tokens": 97},
     "items": [{"type": "reasoning", "text": "..."},
               {"type": "agent_message", "text": "..."},
               {"type": "command_execution", "command": "cat models.py",
                "output": "...", "exit_code": 0},
               {"type": "mcp_tool_call", "record_file": "..."},
               {"type": "file_change", "changes": [...]}]}

`ART30_FAKE_CODEX_ARGV` names a file the fake writes its own argv to, which is how
`tests/test_brain_codex.py` checks the isolation flags without a real CLI.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path

from tests.fakes.mcp_client import McpClient

SCRIPT_VAR = "ART30_FAKE_CODEX_SCRIPT"
ARGV_VAR = "ART30_FAKE_CODEX_ARGV"
SERVER = "art30"
SUBMIT = "submit_record"
DEFAULT_USAGE = {"input_tokens": 44902, "cached_input_tokens": 39168,
                 "cache_write_input_tokens": 0, "output_tokens": 273,
                 "reasoning_output_tokens": 97}
TOOL_ITEMS = ("command_execution", "mcp_tool_call", "file_change")


def _emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def _overrides(argv: list[str]) -> dict[str, str]:
    """Every `-c key=value` on the command line, values left as the CLI would see them."""
    found: dict[str, str] = {}
    for index, item in enumerate(argv):
        if item == "-c" and index + 1 < len(argv) and "=" in argv[index + 1]:
            key, _, value = argv[index + 1].partition("=")
            found[key.strip()] = value
    return found


def _server(argv: list[str]) -> McpClient | None:
    """The MCP server the `-c mcp_servers.art30.*` overrides describe, started for real."""
    config = _overrides(argv)
    command = config.get(f"mcp_servers.{SERVER}.command")
    args = config.get(f"mcp_servers.{SERVER}.args")
    if not command or not args:
        return None
    client = McpClient([json.loads(command), *json.loads(args)])
    client.initialize()
    return client


def _record(item: dict) -> dict:
    if item.get("record_file"):
        return json.loads(Path(item["record_file"]).read_text(encoding="utf-8"))
    return item.get("record") or {}


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if ARGV_VAR in os.environ:
        Path(os.environ[ARGV_VAR]).write_text(json.dumps(args, indent=1), encoding="utf-8")
    script = json.loads(Path(os.environ[SCRIPT_VAR]).read_text(encoding="utf-8"))
    server = _server(args)
    _emit({"type": "thread.started", "thread_id": str(uuid.uuid4())})
    _emit({"type": "turn.started"})
    if script.get("stream_error"):
        # A top-level `error` line, which the real CLI prints for a retry as well as
        # for a failure: "Reconnecting... 2/5 (unexpected status 401 ...)".
        _emit({"type": "error", "message": script["stream_error"]})
    for index, item in enumerate(script.get("items") or []):
        _item(dict(item), f"item_{index}", server)
    if server is not None:
        server.close()
    if script.get("turn_failed"):
        _emit({"type": "turn.failed", "error": {"message": script["turn_failed"]}})
    else:
        _emit({"type": "turn.completed",
               "usage": {**DEFAULT_USAGE, **(script.get("usage") or {})}})
    if script.get("stderr"):
        print(script["stderr"], file=sys.stderr, flush=True)
    return int(script.get("exit_code") or 0)


def _item(item: dict, ident: str, server: McpClient | None) -> None:
    kind = item.get("type")
    if kind not in TOOL_ITEMS:
        _emit({"type": "item.completed",
               "item": {"id": ident, "type": kind, "text": item.get("text", "")}})
        return
    _emit({"type": "item.started", "item": _started(item, ident)})
    _emit({"type": "item.completed", "item": _completed(item, ident, server)})


def _started(item: dict, ident: str) -> dict:
    if item["type"] == "command_execution":
        return {"id": ident, "type": "command_execution",
                "command": _shell(item), "aggregated_output": "",
                "exit_code": None, "status": "in_progress"}
    if item["type"] == "mcp_tool_call":
        return {"id": ident, "type": "mcp_tool_call", "server": SERVER, "tool": SUBMIT,
                "arguments": {"record": _record(item)}, "result": None, "error": None,
                "status": "in_progress"}
    return {"id": ident, "type": "file_change", "status": "in_progress",
            "changes": item.get("changes") or []}


def _completed(item: dict, ident: str, server: McpClient | None) -> dict:
    if item["type"] == "command_execution":
        code = int(item.get("exit_code") or 0)
        return {"id": ident, "type": "command_execution", "command": _shell(item),
                "aggregated_output": str(item.get("output", "")), "exit_code": code,
                "status": "completed" if code == 0 else "failed"}
    if item["type"] == "file_change":
        return {"id": ident, "type": "file_change", "status": "completed",
                "changes": item.get("changes") or []}
    record = _record(item)
    text, is_error = server.submit(record) if server is not None else ('{"accepted":false}', True)
    return {"id": ident, "type": "mcp_tool_call", "server": SERVER, "tool": SUBMIT,
            "arguments": {"record": record},
            "result": {"content": [{"type": "text", "text": text}], "structured_content": None},
            "error": None, "status": "failed" if is_error else "completed"}


def _shell(item: dict) -> str:
    """The real CLI wraps every command in the login shell before it reports it."""
    return f"/bin/zsh -lc '{item.get('command', 'true')}'"


if __name__ == "__main__":   # pragma: no cover - the wrapper script calls main()
    sys.exit(main())
