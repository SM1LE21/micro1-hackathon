"""`submit_record` as an MCP stdio server, so a local CLI submits to the arm itself.

    python -m art30.brains.mcp_server --arm advanced --repo <root> --spool <dir>
                                      --tool-budget N --submit-budget N

JSON-RPC 2.0, one message per line on stdin and stdout, stdout reserved for
protocol traffic and every log line on stderr. The tool served is
`art30.tools.SPEC[3]` verbatim -- the same name, the same description and the same
input schema the API brain sends -- and the handler behind it is
`baseline/arm.py` or `advanced/arm.py`, so a claim the verifier rejects comes back
to the model as the same JSON it would see through the Messages API (ADR 0008
item 1).

Three things this server owns because the CLI cannot be trusted with them:
the submit budget (a call past it is an error, not a sixth attempt), the record of
every attempt (`spool.py`), and the fact that acceptance happens once. The
tool-call budget belongs to the driver, which is the process that can see the
CLI's other tools; `--tool-budget` is accepted here so the arm's `RunCtx` carries
the same number the model was told about.

The gate does not run here. `handle_submit` is a pure verification step; the human
checkpoint runs in the driver after the CLI exits, where a terminal exists.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from art30 import __version__, tools
from art30.arm import RunCtx
from art30.brains.spool import Spool
from art30.config import Config
from art30.loop import _feedback_dict
from art30.tools import ToolCtx

PROTOCOL_VERSION = "2025-06-18"
SERVER_NAME = "art30"
TOOL = tools.SPEC[3]
METHOD_NOT_FOUND = -32601
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
NO_ATTEMPTS = '{"accepted":false,"reason":"no attempts left"}'
ALREADY = '{"accepted":false,"reason":"already accepted"}'
NO_RECORD = '{"accepted":false,"reason":"arguments must carry a record object"}'


class _NullTrace:
    """`RunCtx` carries a trace; the arm never writes to it and this process owns none.

    The run's trace is the driver's: it is built from the CLI's event stream, and a
    second writer here would put step lines in it that no step produced.
    """

    def __getattr__(self, name: str):   # pragma: no cover - never called by an arm
        def _ignore(*args: Any, **kwargs: Any) -> None:
            return None
        return _ignore


def load_arm(name: str):
    """The arms live outside the `art30` package; an import failure is a usage error."""
    if name == "baseline":
        from baseline.arm import BaselineArm

        return BaselineArm()
    from advanced.arm import AdvancedArm

    return AdvancedArm()


class Server:
    """One MCP session. Nothing here reads stdin; `serve` does the reading."""

    def __init__(self, arm, ctx: RunCtx, spool: Spool, submit_budget: int) -> None:
        self.arm = arm
        self.ctx = ctx
        self.spool = spool
        self.submit_budget = submit_budget

    # --- the tool -------------------------------------------------------------
    def submit(self, arguments: dict) -> tuple[str, bool]:
        record = arguments.get("record") if isinstance(arguments, dict) else None
        if not isinstance(record, dict):
            return NO_RECORD, True
        if self.spool.accepted_record() is not None:
            return ALREADY, True
        if self.ctx.submits >= self.submit_budget:
            self.spool.mark_exhausted(f"{self.submit_budget} submit_record attempts used")
            return NO_ATTEMPTS, True
        self.ctx.submits += 1   # before the handler: a raise cannot buy an attempt
        feedback = self.arm.handle_submit(record, self.ctx)
        payload = {"accepted": bool(feedback.accepted), **_feedback_dict(feedback)}
        self.spool.append(self.ctx.submits, record, payload)
        if feedback.accepted:
            self.spool.write_accepted(record)
        elif self.ctx.submits >= self.submit_budget:
            self.spool.mark_exhausted(f"{self.submit_budget} submit_record attempts used")
        return feedback.to_tool_result(), not feedback.accepted

    # --- the protocol ---------------------------------------------------------
    def handle(self, message: dict) -> dict | None:
        """A response object, or None for a notification and for anything unaddressed."""
        method = message.get("method")
        ident = message.get("id")
        if not isinstance(method, str):
            return _error(ident, INVALID_REQUEST, "message carries no method")
        if ident is None:   # a notification is answered with silence, by the spec
            return None
        if method == "initialize":
            return _ok(ident, self._initialize(message.get("params") or {}))
        if method == "tools/list":
            return _ok(ident, {"tools": [{"name": TOOL["name"],
                                          "description": TOOL["description"],
                                          "inputSchema": TOOL["input_schema"]}]})
        if method == "tools/call":
            return _ok(ident, self._call(message.get("params") or {}))
        if method == "ping":
            return _ok(ident, {})
        # Codex probes both on connect even though this server advertises neither
        # capability. Left unanswered, the real D02 run logged `resources/list failed`
        # to stderr and the model then spent one of its 60 tool calls on
        # `list_mcp_resources` trying to recover -- a call charged to the budget and to
        # the eval by a gap here. An empty list costs nothing and closes both.
        if method == "resources/list":
            return _ok(ident, {"resources": []})
        if method == "resources/templates/list":
            # `resourceTemplates`, not `resources`: the wrong key is not a shape error
            # codex reports as a bad response, it is `Unexpected response type` on its
            # stderr and the same wasted tool call the empty list exists to prevent.
            return _ok(ident, {"resourceTemplates": []})
        if method == "prompts/list":
            return _ok(ident, {"prompts": []})
        return _error(ident, METHOD_NOT_FOUND, f"unknown method {method}")

    def _initialize(self, params: dict) -> dict:
        asked = params.get("protocolVersion") if isinstance(params, dict) else None
        return {
            "protocolVersion": asked if isinstance(asked, str) and asked else PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": SERVER_NAME, "version": __version__},
        }

    def _call(self, params: dict) -> dict:
        name = params.get("name") if isinstance(params, dict) else None
        arguments = params.get("arguments") if isinstance(params, dict) else None
        if name != TOOL["name"]:
            return _content(f"unknown tool {name!r}; this server serves {TOOL['name']}", True)
        try:
            text, is_error = self.submit(arguments if isinstance(arguments, dict) else {})
        except Exception as exc:   # a bad record must not take the server down
            _log(f"submit_record raised: {type(exc).__name__}: {exc}")
            return _content(f'{{"accepted":false,"reason":"{type(exc).__name__}"}}', True)
        return _content(text, is_error)


def _ok(ident: Any, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": ident, "result": result}


def _error(ident: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": ident, "error": {"code": code, "message": message}}


def _content(text: str, is_error: bool) -> dict:
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


def _log(text: str) -> None:
    print(f"[art30-mcp] {text}", file=sys.stderr, flush=True)


def serve(server: Server, stdin=None, stdout=None) -> int:
    """Read lines until EOF. A malformed line is answered, never fatal.

    "Never fatal" has to hold for a hostile line as well as a garbled one: the
    stream comes from a process reading an untrusted repository, and if this server
    dies the CLI loses `submit_record` for the rest of the run -- which then ends
    `no_submission` with nothing saying why. Two ways an unguarded loop dies.
    `json.loads` raises `RecursionError`, not `JSONDecodeError`, on a deeply nested
    line: a 100k-deep array kills it, where 2,000 deep is answered normally. And a
    `BrokenPipeError` on the way out is the driver having terminated the CLI, so
    there is nobody left to answer and the loop ends quietly instead of raising.

    Bytes that are not UTF-8 are handled before they get here: `main` reconfigures
    the stream to substitute them, so they arrive as replacement characters and are
    answered as the parse error they are.
    """
    source = stdin or sys.stdin
    sink = stdout or sys.stdout
    for raw in source:
        line = raw.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except (json.JSONDecodeError, RecursionError, ValueError) as exc:
            _log(f"unparseable line ({type(exc).__name__})")
            if not _write(sink, _error(None, PARSE_ERROR, "line is not valid JSON")):
                return 0
            continue
        if not isinstance(message, dict):
            if not _write(sink, _error(None, INVALID_REQUEST, "message is not an object")):
                return 0
            continue
        response = server.handle(message)
        if response is not None and not _write(sink, response):
            return 0
    return 0


def _write(sink, payload: dict) -> bool:
    """False when the other end has gone: the caller stops reading rather than raising."""
    try:
        sink.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
        sink.flush()
    except (BrokenPipeError, ValueError):
        return False
    return True


def build(args: argparse.Namespace) -> Server:
    root = Path(args.repo).resolve()
    spool = Spool(Path(args.spool)).prepare()
    cfg = Config(tool_budget=args.tool_budget, max_submits=args.submit_budget, approve="auto")
    ctx = RunCtx(case=args.case, arm=args.arm, seed=args.seed, root=root,
                 tools=ToolCtx(root=root), trace=_NullTrace(), cfg=cfg)  # type: ignore[arg-type]
    return Server(load_arm(args.arm), ctx, spool, args.submit_budget)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="art30-mcp", description=__doc__.splitlines()[0])
    parser.add_argument("--arm", required=True, choices=("advanced", "baseline"))
    parser.add_argument("--repo", required=True, help="the repository being scanned")
    parser.add_argument("--spool", required=True, help="where submissions are recorded")
    parser.add_argument("--tool-budget", type=int, default=60)
    parser.add_argument("--submit-budget", type=int, default=5)
    parser.add_argument("--case", default="adhoc")
    parser.add_argument("--seed", type=int, default=1)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdin, sys.stdout):
        # A byte sequence that is not UTF-8 must be a parse error, not a dead server.
        getattr(stream, "reconfigure", lambda **_: None)(errors="replace")
    args = parse_args(argv)
    server = build(args)
    _log(f"serving {TOOL['name']} for the {args.arm} arm on {args.repo}")
    return serve(server)


if __name__ == "__main__":   # pragma: no cover - the CLI spawns this module
    sys.exit(main())
