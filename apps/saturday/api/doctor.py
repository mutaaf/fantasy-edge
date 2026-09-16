"""Diagnose the setup and name the exact next command, fantasy-edge style.

Exit codes: 0 ready, 1 generic, 2 config incomplete, 3 credentials missing,
4 no data. A warning never fails the run: CFBD history is a later phase, so a
missing key is reported with its fix but does not block the live slate.
"""
from __future__ import annotations

import json
import os
import pathlib
import urllib.error
import urllib.request

from cfb import league
from cfb.sources import UA

EXIT = {"ok": 0, "generic": 1, "config": 2, "credentials": 3, "data": 4}


def check(repo: pathlib.Path, offline: bool = False) -> dict:
    checks = []

    caps = sorted(p for p in (repo / "data/capture").glob("*") if (p / "scoreboard").is_dir())
    if caps:
        newest = caps[-1]
        finals = len(list((newest / "final").glob("*.json.gz")))
        boards = len(list((newest / "scoreboard").glob("*.json.gz")))
        beat = newest / "heartbeat.json"
        alive = ""
        if beat.exists():
            try:
                state = json.loads(beat.read_text())
                alive = f", recorder {state.get('phase')} at {state.get('at')}"
            except (OSError, ValueError):
                alive = ""
        checks.append({"name": "captures", "status": "ok",
                       "detail": f"{len(caps)} recorded slate(s); newest {newest.name} has {boards} boards "
                                 f"and {finals} finals{alive}",
                       "fix": None, "kind": "data"})
    else:
        checks.append({"name": "captures", "status": "fail", "detail": "no recorded slate under data/capture",
                       "fix": "python3 tools/record_slate.py --out data/capture/$(date +%F) --interval 60", "kind": "data"})

    fixtures = repo / "tests/fixtures/slate.json"
    checks.append({"name": "fixtures", "status": "ok" if fixtures.exists() else "fail",
                   "detail": "test fixtures present" if fixtures.exists() else "tests/fixtures is empty",
                   "fix": None if fixtures.exists() else "python3 tools/make_fixtures.py", "kind": "data"})

    if offline:
        checks.append({"name": "espn", "status": "warn", "detail": "skipped (--offline)", "fix": None, "kind": "generic"})
    else:
        try:
            req = urllib.request.Request(league.scoreboard_url(), headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=8) as r:
                n = len(json.load(r).get("events", []))
            checks.append({"name": "espn", "status": "ok", "detail": f"{league.HOST} reachable; {n} FBS events on the current board", "fix": None, "kind": "generic"})
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            checks.append({"name": "espn", "status": "fail", "detail": f"{league.HOST} unreachable: {exc}",
                           "fix": "check the network, or run offline with: python3 -m api serve --source fixtures", "kind": "generic"})

    if os.environ.get("CFBD_API_KEY"):
        checks.append({"name": "cfbd", "status": "ok", "detail": "CFBD_API_KEY is set", "fix": None, "kind": "credentials"})
    else:
        checks.append({"name": "cfbd", "status": "warn",
                       "detail": "CFBD_API_KEY not set; history, recruiting and portal stay off until it is",
                       "fix": "get a free key at https://collegefootballdata.com/key, then: export CFBD_API_KEY='...'",
                       "kind": "credentials"})

    failing = next((c for c in checks if c["status"] == "fail"), None)
    pending = failing or next((c for c in checks if c["status"] == "warn" and c["fix"]), None)
    code = EXIT[failing["kind"]] if failing else 0
    return {
        "ok": failing is None,
        "exit_code": code,
        "checks": checks,
        "next_action": f"{pending['name']}: {pending['detail']}" if pending else "ready",
        "next_command": pending["fix"] if pending else "python3 -m api serve --source capture:data/capture/2026-09-12@20260913T003400Z",
    }
