"""A minimal stdio JSON-RPC client: what the CLI does to our MCP server.

One request per line, one response per line, in order. No batching, no
concurrency, no reconnect: the server under test answers one message at a time and
a test that hangs here has found a real bug rather than a client limitation.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

PROTOCOL_VERSION = "2025-06-18"
REPO_ROOT = Path(__file__).resolve().parents[2]


def server_argv(arm: str, repo: Path, spool: Path, *, tool_budget: int = 60,
                submit_budget: int = 5, case: str = "S10", seed: int = 1) -> list[str]:
    return [sys.executable, "-m", "art30.brains.mcp_server", "--arm", arm,
            "--repo", str(repo), "--spool", str(spool), "--tool-budget", str(tool_budget),
            "--submit-budget", str(submit_budget), "--case", case, "--seed", str(seed)]


class McpClient:
    """Spawn a stdio MCP server and talk to it. Use as a context manager."""

    def __init__(self, argv: list[str], cwd: Path | None = None) -> None:
        env = dict(os.environ, PYTHONPATH=str(REPO_ROOT))
        self.proc = subprocess.Popen(
            argv, cwd=str(cwd) if cwd else None, env=env, text=True, bufsize=1,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        self._id = 0

    def __enter__(self) -> "McpClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # --- the wire -------------------------------------------------------------
    def send_raw(self, text: str) -> None:
        self.proc.stdin.write(text if text.endswith("\n") else text + "\n")  # type: ignore[union-attr]
        self.proc.stdin.flush()   # type: ignore[union-attr]

    def send_bytes(self, payload: bytes) -> None:
        """Raw bytes, the way a hostile or garbled stream arrives: not always UTF-8."""
        self.proc.stdin.flush()   # type: ignore[union-attr]
        buffer = self.proc.stdin.buffer   # type: ignore[union-attr]
        buffer.write(payload if payload.endswith(b"\n") else payload + b"\n")
        buffer.flush()

    def read(self) -> dict:
        line = self.proc.stdout.readline()   # type: ignore[union-attr]
        if not line:
            raise EOFError(f"the server closed its stdout; stderr: {self.stderr()}")
        return json.loads(line)

    def request(self, method: str, params: dict | None = None) -> dict:
        self._id += 1
        self.send_raw(json.dumps({"jsonrpc": "2.0", "id": self._id, "method": method,
                                  "params": params or {}}))
        return self.read()

    def notify(self, method: str, params: dict | None = None) -> None:
        self.send_raw(json.dumps({"jsonrpc": "2.0", "method": method, "params": params or {}}))

    # --- the protocol ---------------------------------------------------------
    def initialize(self, version: str = PROTOCOL_VERSION) -> dict:
        answer = self.request("initialize", {
            "protocolVersion": version, "capabilities": {},
            "clientInfo": {"name": "art30-tests", "version": "0"},
        })
        self.notify("notifications/initialized")
        return answer

    def tools(self) -> list[dict]:
        return self.request("tools/list")["result"]["tools"]

    def call(self, name: str, arguments: dict) -> dict:
        return self.request("tools/call", {"name": name, "arguments": arguments})["result"]

    def submit(self, record: dict) -> tuple[str, bool]:
        """`(text, isError)` -- what the model would see for one `submit_record` call."""
        result = self.call("submit_record", {"record": record})
        return result["content"][0]["text"], bool(result["isError"])

    def stderr(self) -> str:
        self.proc.stdin.close()   # type: ignore[union-attr]
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        return (self.proc.stderr.read() or "")[-2000:]   # type: ignore[union-attr]

    def close(self) -> None:
        if self.proc.poll() is None:
            try:
                self.proc.stdin.close()   # type: ignore[union-attr]
                self.proc.wait(timeout=5)
            except (subprocess.TimeoutExpired, OSError):
                self.proc.kill()
        for stream in (self.proc.stdout, self.proc.stderr):
            if stream is not None and not stream.closed:
                stream.close()
