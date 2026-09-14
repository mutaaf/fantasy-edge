"""A tiny stdlib dev server that mounts the handlers.

# INTEGRATE: replace with shared api server from fantasy-edge (its
# ThreadingHTTPServer with ROUTES, five cache tiers, ETag/304 and SSE). This
# one keeps only what a client port needs to develop against: JSON, CORS, an
# ETag, and a cache header per route. It is read-only and holds no secrets.
"""
from __future__ import annotations

import hashlib
import json
import re
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import handlers
from cfb.sources import Source

# Route table: pattern, handler, Cache-Control. A capture never changes, so a
# replayed slate could cache forever; live ESPN data must not.
ROUTES = [
    (re.compile(r"^/api/slate$"), lambda src, m: handlers.slate(src), "live"),
    (re.compile(r"^/api/game/(\d+)$"), lambda src, m: handlers.game(src, m.group(1)), "live"),
    (re.compile(r"^/api/teams$"), lambda src, m: handlers.teams(src), "derived"),
    (re.compile(r"^/api/health$"), lambda src, m: {"ok": True, "source": src.label}, "private"),
]
CACHE = {"live": "public, max-age=2, stale-while-revalidate=8",
         "derived": "public, max-age=60",
         "private": "no-store"}


def make_handler(source: Source):
    class Handler(BaseHTTPRequestHandler):
        server_version = "saturday-dev/1"

        def log_message(self, fmt, *args):
            pass

        def _send(self, code: int, payload: dict, cache: str = "no-store"):
            body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
            etag = '"' + hashlib.sha1(body).hexdigest()[:16] + '"'
            if code == 200 and self.headers.get("If-None-Match") == etag:
                self.send_response(304)
                self.send_header("ETag", etag)
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

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            for pattern, fn, tier in ROUTES:
                m = pattern.match(path)
                if not m:
                    continue
                try:
                    return self._send(200, fn(source, m), CACHE[tier] if not source.replay else "public, max-age=30")
                except handlers.NotFound as exc:
                    return self._send(404, {"error": str(exc), "reason": exc.reason})
                except Exception as exc:        # a dev server says what broke
                    traceback.print_exc()
                    return self._send(502, {"error": f"{type(exc).__name__}: {exc}", "reason": "source failed"})
            self._send(404, {"error": f"No route for {path}.", "routes": [p.pattern for p, _, _ in ROUTES]})

    return Handler


def serve(source: Source, host: str = "127.0.0.1", port: int = 8780) -> None:
    httpd = ThreadingHTTPServer((host, port), make_handler(source))
    print(f"saturday api on http://{host}:{port}  source={source.label}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
