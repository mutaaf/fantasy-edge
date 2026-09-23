"""A tiny stdlib dev server that mounts the handlers.

# INTEGRATE: replace with shared api server from fantasy-edge (its
# ThreadingHTTPServer with ROUTES, five cache tiers, ETag/304 and SSE). This
# one keeps only what a client port needs to develop against: JSON, CORS, an
# ETag, a cache header per route, and a server-sent event transport for
# `handlers.stream`. It is read-only and holds no secrets. What each event
# says is decided in handlers; this file only carries the bytes.
"""
from __future__ import annotations

import hashlib
import json
import re
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import handlers
from cfb.sources import Budgeted, Source


def _q(query: dict, key: str) -> str | None:
    values = query.get(key)
    return values[0] if values else None


def _games(query: dict) -> tuple[str, ...]:
    return tuple(g for part in query.get("games", []) for g in part.split(",") if g.isdigit())


def _health(src: Source, m, q: dict) -> dict:
    out = {"ok": True, "source": src.label, "replay": bool(src.replay)}
    if isinstance(src, Budgeted):
        out["budget"] = src.report()
    return out


# Route table: pattern, handler, cache tier. A capture never changes, so a
# replayed slate could cache forever; live ESPN data must not.
ROUTES = [
    (re.compile(r"^/api/slate$"), lambda src, m, q: handlers.slate(src, _q(q, "at")), "live"),
    (re.compile(r"^/api/game/(\d+)$"), lambda src, m, q: handlers.game(src, m.group(1), _q(q, "at")), "live"),
    (re.compile(r"^/api/scene/(\d+)$"), lambda src, m, q: handlers.scene(src, m.group(1), _q(q, "at")), "live"),
    (re.compile(r"^/api/teams$"), lambda src, m, q: handlers.teams(src), "derived"),
    (re.compile(r"^/api/replay$"), lambda src, m, q: handlers.replay(src), "derived"),
    (re.compile(r"^/api/health$"), _health, "private"),
]
STREAM = re.compile(r"^/api/stream$")
CACHE = {"live": "public, max-age=2, stale-while-revalidate=8",
         "derived": "public, max-age=60",
         "private": "no-store"}


def make_handler(source: Source, sleep=None):
    class Handler(BaseHTTPRequestHandler):
        server_version = "saturday-dev/1"
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):
            pass

        def _send(self, code: int, payload: dict, cache: str = "no-store"):
            body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
            etag = '"' + hashlib.sha1(body).hexdigest()[:16] + '"'
            if code == 200 and self.headers.get("If-None-Match") == etag:
                self.send_response(304)
                self.send_header("ETag", etag)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", cache)
            self.send_header("ETag", etag)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _stream(self, q: dict):
            try:
                speed = float(_q(q, "speed") or 1)
            except ValueError:
                return self._send(400, {"error": "speed must be a number", "reason": "bad query"})
            kwargs = {"at": _q(q, "at"), "speed": speed, "games": _games(q)}
            if sleep:
                kwargs["sleep"] = sleep
            if isinstance(source, Budgeted):
                kwargs["budget"] = source.report
            events = handlers.stream(source, **kwargs)
            try:
                first = next(events)          # a bad ?at= fails before any header is sent
            except handlers.BadRequest as exc:
                return self._send(400, {"error": str(exc), "reason": "bad query"})
            except StopIteration:
                first = None
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True
            try:
                if first:
                    self._event(*first)
                for name, payload in events:
                    self._event(name, payload)
            except (BrokenPipeError, ConnectionResetError):
                pass                           # the client closed the stream; that is how it ends

        def _event(self, name: str, payload: dict):
            data = json.dumps(payload, separators=(",", ":"), sort_keys=True)
            self.wfile.write(f"event: {name}\ndata: {data}\n\n".encode())
            self.wfile.flush()

        def do_GET(self):
            url = urllib.parse.urlsplit(self.path)
            q = urllib.parse.parse_qs(url.query)
            if STREAM.match(url.path):
                return self._stream(q)
            for pattern, fn, tier in ROUTES:
                m = pattern.match(url.path)
                if not m:
                    continue
                try:
                    cache = CACHE[tier] if not source.replay else "public, max-age=30"
                    return self._send(200, fn(source, m, q), cache)
                except handlers.NotFound as exc:
                    return self._send(404, {"error": str(exc), "reason": exc.reason})
                except handlers.BadRequest as exc:
                    return self._send(400, {"error": str(exc), "reason": "bad query"})
                except Exception as exc:        # a dev server says what broke
                    traceback.print_exc()
                    return self._send(502, {"error": f"{type(exc).__name__}: {exc}", "reason": "source failed"})
            self._send(404, {"error": f"No route for {url.path}.",
                             "routes": [p.pattern for p, _, _ in ROUTES] + [STREAM.pattern]})

    return Handler


def serve(source: Source, host: str = "127.0.0.1", port: int = 8780) -> None:
    httpd = ThreadingHTTPServer((host, port), make_handler(source))
    httpd.daemon_threads = True
    print(f"saturday api on http://{host}:{port}  source={source.label}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
