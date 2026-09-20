"""Where a slate comes from: a recorded capture, test fixtures, or ESPN.

Every source answers the same questions - the scoreboard, one game's summary,
and the recent boards before this one - so handlers never know which one they
are talking to.

# INTEGRATE: shared live source + replay harness from fantasy-edge
# scene/replay branch. `EspnSource` is a deliberately thin fetch (no cache
# tiers, no backoff ledger, no replay frames); fantasy-edge's LiveSource and
# replay-any-game harness replace it and `CaptureSource` at integration. The
# seam they must keep is the one below: `scoreboard`, `summary`, `history`,
# and on a replay `frames` plus `at`.
"""
from __future__ import annotations

import collections
import datetime as dt
import gzip
import json
import os
import pathlib
import re
import threading
import time
import urllib.parse
import urllib.request
from typing import Callable

from . import league

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0 Safari/537.36")

STAMP = re.compile(r"^\d{8}T\d{6}Z$")


class BadStamp(ValueError):
    pass


def _load(path: pathlib.Path) -> dict:
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return json.load(f)
    return json.loads(path.read_text())


def stamp_of(value: str) -> str:
    """Accept a capture stamp or an ISO instant; return the stamp form."""
    value = (value or "").strip()
    if STAMP.match(value):
        return value
    try:
        when = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise BadStamp(f"{value!r} is not a stamp like 20260913T003400Z or an ISO instant") from None
    if when.tzinfo is None:
        when = when.replace(tzinfo=dt.timezone.utc)
    return when.astimezone(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def seconds_between(a: str, b: str) -> float:
    fmt = "%Y%m%dT%H%M%SZ"
    return (dt.datetime.strptime(b, fmt) - dt.datetime.strptime(a, fmt)).total_seconds()


class Source:
    label = "source"
    replay = False

    def scoreboard(self) -> dict:
        raise NotImplementedError

    def summary(self, event: str) -> dict | None:
        raise NotImplementedError

    def stamp(self) -> str | None:
        """The capture stamp of the board `scoreboard()` returns, if it has one."""
        return None

    def history(self, seconds: float) -> list[tuple[str | None, Callable[[], dict]]]:
        """Boards from the last `seconds`, oldest first, ending with the current
        one, each as a loader: a board whose records are already worked out
        need not be read again, and a night's boards are 1.3 MB apiece."""
        board = self.scoreboard()
        return [(self.stamp(), lambda: board)]

    def frames(self) -> list[str]:
        """Every frame stamp a replay can be positioned at; empty when live."""
        return []

    def at(self, stamp: str) -> "Source":
        raise BadStamp(f"{self.label} is live; only a replay can be read at a moment")


class CaptureSource(Source):
    """A recorded Saturday, frozen at `at` (a UTC stamp like 20260913T003400Z).

    Uses the newest scoreboard and the newest live summary at or before `at`;
    a game with no live snapshot by then falls back to its final only if the
    frozen scoreboard already calls it final, so a capture never shows a
    result from later in the night.

    Only timestamped scoreboards are frames. The closing backfill
    (`20260912-closing-backfill`) was fetched the next morning; it sorts
    before every stamp by name, so reading it by name would put the night's
    finals on a board asked for at 8 PM.
    """
    replay = True

    def __init__(self, root: str | pathlib.Path, at: str):
        self.root, self._at = pathlib.Path(root), at
        self.label = f"capture:{self.root.name}@{at}"

    # `at` is both the frozen moment and the method that moves it.
    def at(self, stamp: str) -> "CaptureSource":
        return CaptureSource(self.root, stamp_of(stamp))

    @property
    def moment(self) -> str:
        return self._at

    def _stamped(self, folder: pathlib.Path) -> list[pathlib.Path]:
        return [p for p in sorted(folder.glob("*.json.gz")) if STAMP.match(p.name[:16])]

    def _by_stamp(self, folder: pathlib.Path) -> dict[str, pathlib.Path]:
        """Stamp to file. A frame is not always `<stamp>.json.gz`: the recorder
        writes its last board as `<stamp>-closing.json.gz`, and a night that
        ended crashed a replay that assumed the plain name."""
        return {p.name[:16]: p for p in self._stamped(folder)}

    def _newest(self, folder: pathlib.Path) -> pathlib.Path | None:
        files = [p for p in self._stamped(folder) if p.name[:16] <= self._at[:16]]
        return files[-1] if files else None

    def frames(self) -> list[str]:
        return [p.name[:16] for p in self._stamped(self.root / "scoreboard")]

    def stamp(self) -> str | None:
        path = self._newest(self.root / "scoreboard")
        return path.name[:16] if path else None

    def scoreboard(self) -> dict:
        path = self._newest(self.root / "scoreboard")
        if not path:
            raise FileNotFoundError(f"no scoreboard at or before {self._at} in {self.root}")
        return _load(path)

    def history(self, seconds: float):
        now = self.stamp()
        if not now:
            return []
        before = [s for s in self.frames() if s <= now]
        # Always the frame before this one, however long ago: across the
        # recorder's gap a change is still a change.
        keep = [s for i, s in enumerate(before) if i >= len(before) - 2 or seconds_between(s, now) <= seconds]
        paths = self._by_stamp(self.root / "scoreboard")
        return [(s, lambda p=paths[s]: _load(p)) for s in keep if s in paths]

    def summary(self, event: str) -> dict | None:
        live = self.root / "live" / event
        if live.is_dir() and (path := self._newest(live)):
            return _load(path)
        final = self.root / "final" / f"{event}.json.gz"
        if not final.exists() or not self.stamp():
            return None
        state = next((ev["status"]["type"].get("completed") for ev in self.scoreboard().get("events", [])
                      if str(ev.get("id")) == event), False)
        return _load(final) if state else None


class FixtureSource(Source):
    """The trimmed fixtures in tests/fixtures, written by tools/make_fixtures.py."""
    replay = True

    def __init__(self, root: str | pathlib.Path):
        self.root = pathlib.Path(root)
        self.label = "fixtures"

    def scoreboard(self) -> dict:
        return _load(self.root / "slate.json")

    def stamp(self) -> str | None:
        return self.scoreboard().get("capturedAt")

    def summary(self, event: str) -> dict | None:
        path = self.root / f"summary_{event}.json"
        return _load(path) if path.exists() else None


class EspnSource(Source):
    """ESPN, fetched on demand. It keeps the boards it has already fetched for
    an hour so a change can be read against the one before it."""
    label = "espn"

    def __init__(self):
        self._boards: collections.deque[tuple[str, dict]] = collections.deque(maxlen=64)   # 1.3 MB each; 21 min at one per window

    def _get(self, url: str) -> dict:
        key = os.environ.get("ESPN_API_KEY")
        if key:
            url += "&apikey=" + urllib.parse.quote(key, safe="")
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json",
                                                   "Referer": "https://www.espn.com/"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.load(r)

    def scoreboard(self) -> dict:
        board = self._get(league.scoreboard_url())
        now = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self._boards.append((now, board))
        return board

    def stamp(self) -> str | None:
        return self._boards[-1][0] if self._boards else None

    def history(self, seconds: float):
        if not self._boards:
            self.scoreboard()
        now, n = self._boards[-1][0], len(self._boards)
        return [(s, lambda b=b: b) for i, (s, b) in enumerate(self._boards)
                if i >= n - 2 or seconds_between(s, now) <= seconds]

    def summary(self, event: str) -> dict | None:
        return self._get(league.summary_url(event))


class Budgeted(Source):
    """A live source held to the request budget in `league.BUDGET`.

    However many clients are watching, the scoreboard is fetched at most once
    per `scoreboardSeconds` and a game's summary at most once per
    `summarySeconds`, and a summary is fetched only when somebody asks for
    that game. Every upstream request is counted, so a test and `/api/health`
    can say whether the night stayed inside the budget.

    The server is threaded and an ESPN fetch takes a second or more, so the
    check and the fetch happen under one lock per resource: when a cached
    board expires, the first request fetches and every request that arrives
    meanwhile waits for that answer. Without the lock, three clients doubled
    the scoreboard budget against live ESPN on 2026-09-15.
    """

    def __init__(self, inner: Source, clock=time.monotonic, budget: dict | None = None):
        self.inner, self.clock = inner, clock
        self.budget = dict(budget or league.BUDGET)
        self.label, self.replay = inner.label, inner.replay
        self.started = clock()
        self._board: tuple[float, dict] | None = None
        self._summaries: dict[str, tuple[float, dict | None]] = {}
        self.requests = {"scoreboard": 0, "summary": collections.Counter()}
        self._board_lock = threading.Lock()
        self._locks_lock = threading.Lock()
        self._summary_locks: dict[str, threading.Lock] = {}

    def scoreboard(self) -> dict:
        with self._board_lock:
            now = self.clock()
            if self._board is None or now - self._board[0] >= self.budget["scoreboardSeconds"]:
                self.requests["scoreboard"] += 1          # counted even if the fetch fails
                self._board = (now, self.inner.scoreboard())
            return self._board[1]

    def summary(self, event: str) -> dict | None:
        with self._locks_lock:
            lock = self._summary_locks.setdefault(event, threading.Lock())
        with lock:
            now = self.clock()
            hit = self._summaries.get(event)
            if hit is None or now - hit[0] >= self.budget["summarySeconds"]:
                self.requests["summary"][event] += 1
                hit = (now, self.inner.summary(event))
                self._summaries[event] = hit
            return hit[1]

    def stamp(self) -> str | None:
        return self.inner.stamp()

    def history(self, seconds: float):
        self.scoreboard()
        with self._board_lock:
            return self.inner.history(seconds)

    def report(self) -> dict:
        elapsed = max(0.0, self.clock() - self.started)
        limit_board = int(elapsed // self.budget["scoreboardSeconds"]) + 1
        limit_game = int(elapsed // self.budget["summarySeconds"]) + 1
        games = dict(self.requests["summary"])
        return {
            "requests": {"scoreboard": self.requests["scoreboard"], "summary": games,
                         "total": self.requests["scoreboard"] + sum(games.values())},
            "limits": {"elapsedSeconds": round(elapsed, 1), "scoreboard": limit_board, "summaryPerGame": limit_game,
                       **self.budget},
            "within": self.requests["scoreboard"] <= limit_board and all(n <= limit_game for n in games.values()),
        }


def from_spec(spec: str, repo: pathlib.Path) -> Source:
    """`fixtures`, `espn`, or `capture:<dir>@<stamp>`."""
    if spec == "fixtures":
        return FixtureSource(repo / "tests/fixtures")
    if spec == "espn":
        return Budgeted(EspnSource())
    if spec.startswith("capture:"):
        body = spec.split(":", 1)[1]
        path, _, at = body.partition("@")
        return CaptureSource(repo / path if not os.path.isabs(path) else path, at or "99999999T999999Z")
    raise ValueError(f"unknown source {spec!r}: use fixtures, espn, or capture:<dir>@<UTC stamp>")
