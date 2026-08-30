"""`art30 serve`: a stdlib server on 127.0.0.1 that drives the CLI (ADR 0007).

The routing table and the socket, and nothing else: every route hands off to
`api.py`, `runs.py` or `sse.py`. The page is one file served from the package.
The server binds a loopback address only, refuses anything else, and writes
under `results/web/<run_id>/` alone.
"""

from __future__ import annotations

import json
import socket
import sys
import traceback
import webbrowser
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from urllib.parse import parse_qs, urlparse

from art30.web import api, runs, sse

LOOPBACK = ("127.0.0.1", "localhost", "::1")
PAGE = "index.html"
MAX_BODY = 1 << 20
INTERNAL = "the server hit an unexpected error; its terminal has the details"
REFUSED = ("this server answers 127.0.0.1 only: reach it at the address it printed,"
           " and from a page it served")


def page_bytes() -> bytes:
    return resources.files("art30.web").joinpath(PAGE).read_bytes()


class Handler(BaseHTTPRequestHandler):
    server_version = "art30"
    sys_version = ""

    # --- plumbing ---------------------------------------------------------------------
    def log_message(self, fmt: str, *args) -> None:   # noqa: A002 - stdlib signature
        sys.stderr.write("  " + (fmt % args) + "\n")

    def _same_origin(self) -> bool:
        """Loopback is not a boundary a browser enforces: a name that resolves to
        127.0.0.1 (DNS rebinding) or a cross-origin form post both arrive on this
        socket. The `Host` a rebound name carries is not ours, and a cross-origin
        request carries an `Origin` that is not ours either."""
        port = self.server.server_address[1]
        allowed = {f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"}
        host = (self.headers.get("Host") or "").strip()
        if host not in allowed:
            return False
        origin = (self.headers.get("Origin") or "").strip()
        return not origin or origin == f"http://{host}"

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: dict) -> None:
        self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8") + b"\n",
                   "application/json; charset=utf-8")

    def _stream(self, run: runs.Run) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        # `closing`: a page that navigated away breaks the write, and the generator's
        # own `finally` (both file handles) then runs here rather than at collection.
        with closing(sse.events(run)) as stream:
            for chunk in stream:
                self.wfile.write(chunk)
                self.wfile.flush()

    # --- routing ----------------------------------------------------------------------
    def do_GET(self) -> None:                          # noqa: N802 - stdlib name
        if not self._same_origin():
            return self._safely(403, REFUSED)
        parsed = urlparse(self.path)
        parts = [p for p in parsed.path.split("/") if p]
        try:
            self._get(parts, parse_qs(parsed.query))
        except (BrokenPipeError, ConnectionResetError):
            return                                     # the page navigated away
        except Exception:                              # noqa: BLE001 - nothing leaks out
            traceback.print_exc()
            self._safely(500, INTERNAL)

    def do_POST(self) -> None:                         # noqa: N802 - stdlib name
        if not self._same_origin():
            return self._safely(403, REFUSED)
        parts = [p for p in urlparse(self.path).path.split("/") if p]
        try:
            self._post(parts)
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception:                              # noqa: BLE001
            traceback.print_exc()
            self._safely(500, INTERNAL)

    def _get(self, parts: list[str], query: dict) -> None:
        if parts in ([], [PAGE]):
            return self._send(200, page_bytes(), "text/html; charset=utf-8")
        if parts == ["favicon.ico"]:                     # the page carries its icon inline
            return self._send(204, b"", "image/x-icon")
        if parts == ["api", "cases"]:
            return self._json(*api.cases())
        if parts == ["api", "results"]:
            return self._json(*api.results())
        if parts == ["api", "runs"]:
            return self._json(*api.listing())
        if len(parts) >= 3 and parts[:2] == ["api", "runs"]:
            return self._run_get(parts[2], parts[3:], query)
        self._json(404, {"error": f"no route for GET {self.path}"})

    def _run_get(self, run_id: str, rest: list[str], query: dict) -> None:
        if rest == []:
            return self._json(*api.one(run_id))
        if rest == ["events"]:
            run = runs.get(run_id)
            if run is None:
                return self._json(404, {"error": f"no run called {run_id}"})
            return self._stream(run)
        if rest == ["source"]:
            return self._json(*api.source(run_id, query))
        if len(rest) == 1 and rest[0] in api.ARTIFACTS:
            status, body, content_type = api.artifact(run_id, rest[0])
            return self._send(status, body, content_type)
        self._json(404, {"error": f"no route for GET {self.path}"})

    def _post(self, parts: list[str]) -> None:
        body = self._body()
        if parts == ["api", "runs"]:
            return self._json(*api.start(body))
        if len(parts) == 4 and parts[:2] == ["api", "runs"]:
            if parts[3] == "gate":
                return self._json(*api.gate(parts[2], body))
            if parts[3] == "cancel":
                return self._json(*api.cancel(parts[2]))
        self._json(404, {"error": f"no route for POST {self.path}"})

    def _body(self) -> dict:
        try:
            length = min(int(self.headers.get("Content-Length") or 0), MAX_BODY)
        except ValueError:
            return {}
        if length <= 0:
            return {}
        try:
            found = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {}
        return found if isinstance(found, dict) else {}

    def _safely(self, status: int, message: str) -> None:
        try:
            self._json(status, {"error": message})
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class Server6(Server):
    """`::1` needs the family chosen before the socket is made, not after."""

    address_family = socket.AF_INET6


def build(host: str, port: int) -> Server:
    return (Server6 if ":" in host else Server)((host, port), Handler)


def serve(host: str = "127.0.0.1", port: int = 8734, open_browser: bool = False) -> int:
    """Print the URL, open the page if asked, serve until Ctrl-C."""
    if host not in LOOPBACK:
        print(f"art30 serve binds a loopback address only, not {host}", file=sys.stderr)
        return 2
    try:
        httpd = build(host, port)
    except OSError as exc:
        print(f"cannot listen on {host}:{port}: {exc.strerror or exc}", file=sys.stderr)
        return 2
    shown = f"[{host}]" if ":" in host else host
    url = f"http://{shown}:{httpd.server_address[1]}/"
    root = runs.runs_root()
    where = root.relative_to(runs.REPO_ROOT) if root.is_relative_to(runs.REPO_ROOT) else root
    print(f"art30 serve \u00b7 {url}", flush=True)
    print(f"runs are written under {where}/<run_id>/", flush=True)
    print("replay needs no API key. Ctrl-C stops the server.", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        httpd.server_close()
    return 0
