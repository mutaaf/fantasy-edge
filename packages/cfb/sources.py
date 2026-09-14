"""Where a slate comes from: a recorded capture, test fixtures, or ESPN.

Every source answers the same two questions - the scoreboard, and one game's
summary - so handlers never know which one they are talking to.

# INTEGRATE: shared live source + replay harness from fantasy-edge
# scene/replay branch. `EspnSource` is a deliberately thin fetch (no cache
# tiers, no backoff ledger, no replay frames); fantasy-edge's LiveSource and
# replay-any-game harness replace it and `CaptureSource` at integration.
"""
from __future__ import annotations

import gzip
import json
import os
import pathlib
import urllib.parse
import urllib.request

from . import league

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0 Safari/537.36")


def _load(path: pathlib.Path) -> dict:
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return json.load(f)
    return json.loads(path.read_text())


class Source:
    label = "source"
    replay = False

    def scoreboard(self) -> dict:
        raise NotImplementedError

    def summary(self, event: str) -> dict | None:
        raise NotImplementedError


class CaptureSource(Source):
    """A recorded Saturday, frozen at `at` (a UTC stamp like 20260913T003400Z).

    Uses the newest scoreboard and the newest live summary at or before `at`;
    a game with no live snapshot by then falls back to its final only if the
    frozen scoreboard already calls it final, so a capture never shows a
    result from later in the night.
    """
    replay = True

    def __init__(self, root: str | pathlib.Path, at: str):
        self.root, self.at = pathlib.Path(root), at
        self.label = f"capture:{self.root.name}@{at}"

    def _newest(self, folder: pathlib.Path) -> pathlib.Path | None:
        files = [p for p in sorted(folder.glob("*.json.gz")) if p.name[:16] <= self.at[:16]]
        return files[-1] if files else None

    def scoreboard(self) -> dict:
        path = self._newest(self.root / "scoreboard")
        if not path:
            raise FileNotFoundError(f"no scoreboard at or before {self.at} in {self.root}")
        return _load(path)

    def summary(self, event: str) -> dict | None:
        live = self.root / "live" / event
        if live.is_dir() and (path := self._newest(live)):
            return _load(path)
        final = self.root / "final" / f"{event}.json.gz"
        state = next((ev["status"]["type"].get("completed") for ev in self.scoreboard().get("events", [])
                      if str(ev.get("id")) == event), False)
        return _load(final) if final.exists() and state else None


class FixtureSource(Source):
    """The trimmed fixtures in tests/fixtures, written by tools/make_fixtures.py."""
    replay = True

    def __init__(self, root: str | pathlib.Path):
        self.root = pathlib.Path(root)
        self.label = "fixtures"

    def scoreboard(self) -> dict:
        return _load(self.root / "slate.json")

    def summary(self, event: str) -> dict | None:
        path = self.root / f"summary_{event}.json"
        return _load(path) if path.exists() else None


class EspnSource(Source):
    label = "espn"

    def _get(self, url: str) -> dict:
        key = os.environ.get("ESPN_API_KEY")
        if key:
            url += "&apikey=" + urllib.parse.quote(key, safe="")
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json",
                                                   "Referer": "https://www.espn.com/"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.load(r)

    def scoreboard(self) -> dict:
        return self._get(league.scoreboard_url())

    def summary(self, event: str) -> dict | None:
        return self._get(league.summary_url(event))


def from_spec(spec: str, repo: pathlib.Path) -> Source:
    """`fixtures`, `espn`, or `capture:<dir>@<stamp>`."""
    if spec == "fixtures":
        return FixtureSource(repo / "tests/fixtures")
    if spec == "espn":
        return EspnSource()
    if spec.startswith("capture:"):
        body = spec.split(":", 1)[1]
        path, _, at = body.partition("@")
        return CaptureSource(repo / path if not os.path.isabs(path) else path, at or "99999999T999999Z")
    raise ValueError(f"unknown source {spec!r}: use fixtures, espn, or capture:<dir>@<UTC stamp>")
