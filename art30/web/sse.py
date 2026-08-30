"""The event stream: the trace as the child flushes it, its stdout beside it.

One generator, four event names. `trace` carries a raw JSONL line unchanged --
the page parses the same bytes a judge reads in `traces/` -- `stdout` carries a
line the CLI printed, `gate` the request the run is blocked on, `done` the exit.
A reconnect replays from the start of both files; there is no Last-Event-ID.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Callable, Iterator

from art30.web import runs

POLL_S = 0.2
KEEPALIVE_S = 5.0        # a write is how a closed socket is noticed; a quiet run
                         # otherwise keeps a dead stream's thread and handles alive
KEEPALIVE = b": keepalive\n\n"
RETRY = b"retry: 2000\n\n"


def frame(name: str, data: str) -> bytes:
    """One event. `data` is a single line by construction: JSONL lines and
    printed lines both are, and a stray newline would split the event."""
    return f"event: {name}\ndata: {data.replace(chr(10), ' ')}\n\n".encode("utf-8")


class Tail:
    """A file that may not exist yet, read forward in whole lines.

    Bytes, not text: a poll can land between the two halves of a `\u00b7`, which the
    CLI prints in every header and gate line, and decoding a half is a replacement
    character no later poll can undo. Whole lines are decoded, partial ones wait.
    """

    def __init__(self, locate: Callable[[], Path | None]) -> None:
        self._locate = locate
        self._handle = None
        self._buffer = b""

    def lines(self) -> list[str]:
        if self._handle is None:
            path = self._locate()
            if path is None or not path.is_file():
                return []
            self._handle = path.open("rb")
        chunk = self._handle.read()
        if not chunk:
            return []
        self._buffer += chunk
        parts = self._buffer.split(b"\n")
        self._buffer = parts.pop()
        return [part.decode("utf-8", "replace") for part in parts]

    def close(self) -> None:
        if self._handle is not None:
            self._handle.close()
            self._handle = None


def _gate_payload(run: runs.Run) -> str | None:
    request, _ = runs.gate_paths(run)
    try:
        found = json.loads(request.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return json.dumps(found, ensure_ascii=False)


def _done(run: runs.Run) -> bytes:
    condition = runs.stop_condition(run)
    payload = {"exit_code": run.proc.poll(), "stop_condition": condition,
               "status": runs.status(run)}
    if condition in ("crashed", "cancelled"):
        payload["note"] = runs.tail(run)
    return frame("done", json.dumps(payload, ensure_ascii=False))


def events(run: runs.Run, poll_s: float = POLL_S,
           keepalive_s: float = KEEPALIVE_S) -> Iterator[bytes]:
    trace = Tail(lambda: runs.trace_path(run))
    stdout = Tail(lambda: run.dir / runs.LOG_NAME)
    gate_sent = False
    last = time.monotonic()
    yield RETRY
    try:
        while True:
            # The exit is read before the files, so the drain after an exit sees
            # everything the child wrote: a dead child has no unflushed bytes.
            exited = run.proc.poll() is not None
            spoke = False
            for line in stdout.lines():
                yield frame("stdout", line)
                spoke = True
            for line in trace.lines():
                if line.strip():
                    yield frame("trace", line)
                    spoke = True
            if not gate_sent and runs.gate_waiting(run):
                payload = _gate_payload(run)
                if payload is not None:
                    yield frame("gate", payload)
                    gate_sent = spoke = True
            if exited:
                yield _done(run)
                return
            if spoke:
                last = time.monotonic()
            elif time.monotonic() - last >= keepalive_s:
                yield KEEPALIVE
                last = time.monotonic()
            time.sleep(poll_s)
    finally:
        trace.close()
        stdout.close()
