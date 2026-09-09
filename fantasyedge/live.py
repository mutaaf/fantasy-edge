"""The live tier: game state that is identical for every user on earth.

This module exists to enforce one architectural rule, which is the only reason
a fantasy dashboard can serve millions of people without a fleet behind it.

    Live data is shared. Personal data is static. Never compute their product
    on the server.

There are about sixteen games and seventeen hundred relevant players on a
Sunday. That snapshot is a few tens of kilobytes and it is *the same bytes for
every viewer* - so it is fetched once from the provider, cached once, and
fanned out at the edge. Cost is O(games), not O(users).

What is personal - your roster, your opponent's roster, your league - changes
a handful of times a week, so it is separately cacheable for minutes at a time.

Your live score is the product of the two, and that product is where the
trouble would be: computing it server-side means a unique response per user
every few seconds, which is O(users) work, uncacheable by definition, and the
thing that turns a dashboard into a datacentre. So it is never computed here.
The client joins the shared snapshot against its own static roster and runs
`leverage.evaluate` locally, which is a few hundred floating point operations
and costs the server exactly nothing.

`SimulatedSource` stands in until the real feed is wired. It is deterministic
given a seed, which is what lets tests assert on a live system at all.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import pathlib
import random
import time
from abc import ABC, abstractmethod

# A compressed Sunday: kickoff offsets and length, in simulated minutes.
WINDOWS = [("1pm", 0), ("4pm", 180), ("SNF", 420)]

# ESPN stores an NFL club as a numeric id. Nobody wants to read "14" on a
# television, so the mapping lives here rather than in each client.
NFL_TEAM = {
    1: "ATL", 2: "BUF", 3: "CHI", 4: "CIN", 5: "CLE", 6: "DAL", 7: "DEN",
    8: "DET", 9: "GB", 10: "TEN", 11: "IND", 12: "KC", 13: "LV", 14: "LAR",
    15: "MIA", 16: "MIN", 17: "NE", 18: "NO", 19: "NYG", 20: "NYJ", 21: "PHI",
    22: "ARI", 23: "PIT", 24: "LAC", 25: "SF", 26: "SEA", 27: "TB", 28: "WSH",
    29: "CAR", 30: "JAX", 33: "BAL", 34: "HOU",
}


# Club colour, picked for a dark surface rather than for the style guide. A
# handful of clubs are officially near-black (LV, JAX, CHI, CLE); their primary
# would vanish against this ground, so the vivid secondary stands in.
NFL_COLOR = {
    "ARI": "#E64A6B", "ATL": "#E8262F", "BAL": "#7B68EE", "BUF": "#3B7DE0",
    "CAR": "#0FA5E9", "CHI": "#F26522", "CIN": "#FB4F14", "CLE": "#FF6A1F",
    "DAL": "#7FA5D8", "DEN": "#FB6516", "DET": "#3FA9E8", "GB": "#7BC043",
    "HOU": "#4A9FD4", "IND": "#3E8FD6", "JAX": "#D7A22A", "KC": "#F5344E",
    "LV": "#C8CDD0", "LAC": "#28B4E8", "LAR": "#4C7FE0", "MIA": "#00C4CF",
    "MIN": "#8B5CD6", "NE": "#E8455F", "NO": "#D3BC8D", "NYG": "#4A7BD4",
    "NYJ": "#3FBE6E", "PHI": "#22B5A8", "PIT": "#FFC833", "SF": "#E8434B",
    "SEA": "#69BE28", "TB": "#F03A3A", "TEN": "#5BA3E0", "WSH": "#C9803F",
    "FA": "#7d8998",
}


def team_color(abbr: str) -> str:
    return NFL_COLOR.get((abbr or "").upper(), NFL_COLOR["FA"])


def headshot_url(player_id: str, team: str = "") -> str:
    """A player's portrait, or their club's mark for a team defence.

    A negative ESPN id is a D/ST rather than a person - see the note in
    CLAUDE.md - and there is no headshot for a defence, so the club logo
    stands in.
    """
    pid = str(player_id or "")
    if pid.startswith("-"):
        return logo_url(team)
    return f"https://a.espncdn.com/i/headshots/nfl/players/full/{pid}.png"


def logo_url(team: str) -> str:
    ab = (team or "").lower()
    return f"https://a.espncdn.com/i/teamlogos/nfl/500/{ab}.png" if ab and ab != "fa" else ""


def _num_score(raw) -> float:
    try:
        return float(str(raw).strip() or 0)
    except (TypeError, ValueError):
        return 0.0


def team_abbr(raw) -> str:
    """A club id, an abbreviation, or nothing, rendered as an abbreviation."""
    if raw in (None, ""):
        return "FA"
    try:
        return NFL_TEAM.get(int(raw), "FA")
    except (TypeError, ValueError):
        return str(raw).upper()[:4]
GAME_MINUTES = 190          # about three hours of wall clock per game


class LiveSource(ABC):
    """A source of shared, user-independent game state.

    One method on purpose. Anything that needs to know *who is asking* does not
    belong in this tier, because the moment a response varies by user it stops
    being cacheable and the whole cost model collapses.
    """

    @abstractmethod
    def snapshot(self, at: float | None = None) -> dict:
        """Global game and player state. Same answer for every caller."""


class SimulatedSource(LiveSource):
    """A deterministic Sunday, for building against before the feed exists.

    Scoring events are drawn once at construction from a seeded generator, so
    points accumulate monotonically and any two processes with the same seed
    agree exactly. That reproducibility is what makes the live path testable.
    """

    def __init__(self, players: list[dict], seed: int = 7,
                 speed: float = 90.0, start: float | None = None):
        self.speed = speed                      # simulated minutes per real second
        self.start = start if start is not None else time.time()
        rng = random.Random(seed)
        self.games: dict[str, dict] = {}
        self.players: list[dict] = []

        teams = sorted({p.get("team") or "FA" for p in players})
        for i, t in enumerate(teams):
            window, offset = WINDOWS[i % len(WINDOWS)]
            self.games[t] = {"team": t, "window": window, "kickoff": offset}

        for p in players:
            proj = float(p.get("projected") or 0.0) or 8.0
            # Points arrive in lumps, not a smooth ramp: a touchdown is six
            # points in one second. Event count scales with the projection.
            n_events = max(1, int(rng.gauss(proj / 3.5, 1.2)))
            events = []
            remaining = proj * rng.uniform(0.55, 1.45)   # real outcomes miss projections
            for _ in range(n_events):
                events.append([rng.random(), remaining / n_events])
            events.sort()
            self.players.append({
                "id": str(p["player_id"]), "name": p.get("name") or "?",
                "pos": (p.get("pos") or "").upper(), "team": p.get("team") or "FA",
                "projected": round(proj, 1), "events": events,
            })

    # ---------- clock ----------

    def _minute(self, at: float | None) -> float:
        return ((at if at is not None else time.time()) - self.start) * self.speed / 60.0

    def _game_progress(self, team: str, minute: float) -> tuple[float, str]:
        """Fraction of a team's game already played, and a display state."""
        g = self.games.get(team)
        if not g:
            return 1.0, "bye"
        elapsed = minute - g["kickoff"]
        if elapsed <= 0:
            return 0.0, "pre"
        if elapsed >= GAME_MINUTES:
            return 1.0, "final"
        f = elapsed / GAME_MINUTES
        return f, f"Q{min(4, int(f * 4) + 1)}"

    # ---------- the snapshot ----------

    def snapshot(self, at: float | None = None) -> dict:
        minute = self._minute(at)
        out = {}
        for p in self.players:
            played, state = self._game_progress(p["team"], minute)
            scored = sum(pts for t, pts in p["events"] if t <= played)
            # A near-term scoring event is what "in the red zone" actually means
            # to a fantasy viewer: points are about to land.
            hot = any(played < t <= played + 0.06 for t, _ in p["events"])
            out[p["id"]] = {
                "s": round(scored, 2),                  # scored so far
                "r": round(max(0.0, 1.0 - played), 3),  # fraction of game remaining
                "g": "RZ" if (hot and state not in ("pre", "final")) else state,
            }
        payload = {
            "asOf": round(minute, 1),
            "window": next((w for w, o in reversed(WINDOWS) if minute >= o), "pre"),
            "games": {t: dict(zip(("played", "state"),
                                  self._game_progress(t, minute)))
                      for t in self.games},
            "players": out,
        }
        # Content-addressed: the version *is* the hash, so any cache layer can
        # answer "has this changed" without understanding the payload.
        payload["version"] = hashlib.sha1(
            json.dumps(payload["players"], sort_keys=True,
                       separators=(",", ":")).encode()).hexdigest()[:16]
        return payload


SCOREBOARD = ("https://site.api.espn.com/apis/site/v2/sports/football/nfl"
              "/scoreboard{q}")
SUMMARY = ("https://site.api.espn.com/apis/site/v2/sports/football/nfl"
           "/summary?event={event}")
GAME_LENGTH_MIN = 60.0          # four quarters of game clock


class EspnLiveSource(LiveSource):
    """Real game state from ESPN's public scoreboard.

    No credentials: this is the same feed espn.com itself renders, so it needs
    no cookie and is safe to call from the credential-free API. It is behind
    Akamai and will start returning 403 if hammered - the cache here is not an
    optimisation, it is the thing that keeps the feed working.

    Game state is the honest part. Per-player scoring is not in this payload;
    it lives behind a per-game summary call, and asking for sixteen of those on
    every poll is exactly how you get blocked. So this reports what the
    scoreboard actually knows - which games are running and how far through
    they are - and leaves each player's points at whatever the caller already
    had. That is enough to drive the phase and the clock, which is what the
    board needs before kickoff and between plays.
    """

    def __init__(self, players: list[dict], ttl: float = 20.0, http=None,
                 scoring=None, box_ttl: float = 25.0):
        self.players = [{"id": str(p["player_id"]), "team": p.get("team") or "FA",
                         "projected": float(p.get("projected") or 0.0)}
                        for p in players]
        self.ttl = ttl
        self.box_ttl = box_ttl
        self._http = http
        self._cache: dict | None = None
        self._at = 0.0
        self._fail_until = 0.0
        self._boxes: dict[str, tuple[float, dict]] = {}
        if scoring is None:
            from .scoring import Scoring
            scoring = Scoring()
        self.scoring = scoring

    def _fetch(self, url: str) -> dict:
        """One way in, so a captured payload stands in for every endpoint.

        ESPN's edge rate-limits an address that polls too eagerly, and being
        able to point at real recorded data is the difference between
        developing against the truth and developing against a simulator. The
        override covers box scores too - a slate that moves but never scores is
        exactly as misleading as a simulator.
        """
        if self._http is not None:                 # injected for tests
            return self._http(url)
        if "summary?event=" in url:
            event = url.split("summary?event=", 1)[1].split("&")[0]
            d = os.environ.get("FANTASYEDGE_SUMMARY_DIR")
            if d:
                f = pathlib.Path(d) / f"{event}.json"
                if f.exists():
                    return json.loads(f.read_text())
            one = os.environ.get("FANTASYEDGE_SUMMARY_FILE")
            if one:
                return json.loads(pathlib.Path(one).read_text())
        else:
            path = os.environ.get("FANTASYEDGE_SCOREBOARD_FILE")
            if path:
                return json.loads(pathlib.Path(path).read_text())
        return _get_json(url)

    def scoreboard(self) -> dict:
        """The raw slate, cached. A 403 backs off rather than retrying hot."""
        now = time.time()
        if self._cache is not None and now - self._at < self.ttl:
            return self._cache
        if now < self._fail_until:
            return self._cache or {"events": []}
        try:
            data = self._fetch(SCOREBOARD.format(q=""))
            self._cache, self._at, self._fail_until = data, now, 0.0
        except Exception:
            # Back off hard: the edge blocks an IP that keeps knocking.
            self._fail_until = now + 120.0
            if self._cache is None:
                self._cache, self._at = {"events": []}, now
        return self._cache

    def _events(self) -> list[tuple[str, str, list[str]]]:
        """(event id, state, club abbreviations) for this week's slate."""
        out = []
        for ev in (self.scoreboard().get("events") or []):
            comp = (ev.get("competitions") or [{}])[0]
            state = ((comp.get("status") or {}).get("type") or {}).get("state") or "pre"
            clubs = []
            for c in (comp.get("competitors") or []):
                ab = ((c.get("team") or {}).get("abbreviation") or "").upper()
                if ab:
                    clubs.append((ab, _num_score(c.get("score"))))
            if ev.get("id"):
                out.append((str(ev["id"]), state, clubs))
        return out

    def boxscores(self) -> tuple[dict[str, float], dict[str, float]]:
        """Fantasy points per athlete, for games that have actually started.

        Only in-progress and finished games are fetched, and each is cached on
        its own clock, because this is the expensive half of the feed: one call
        per game rather than one for the slate. On a Sunday afternoon that is a
        dozen or so requests a minute at worst, which the edge tolerates; asking
        for all sixteen every poll is how an address gets blocked.

        A finished game is fetched once and then held - its numbers cannot
        change again, so re-asking is pure waste.
        """
        from .scoring import dst_points, parse_team_defence, score_boxscore

        now = time.time()
        points: dict[str, float] = {}
        dst: dict[str, float] = {}
        for event, state, clubs in self._events():
            if state == "pre":
                continue                       # nothing to score yet
            hit = self._boxes.get(event)
            fresh = hit and (state == "post" or now - hit[0] < self.box_ttl)
            if not fresh:
                try:
                    data = self._fetch(SUMMARY.format(event=event))
                    hit = (now, score_boxscore(data, self.scoring),
                           parse_team_defence(data))
                except Exception:
                    # keep whatever we had; a single bad game must not blank a board
                    hit = hit or (now, {}, {})
                    hit = (now, hit[1], hit[2] if len(hit) > 2 else {})
                self._boxes[event] = hit
            points.update(hit[1])

            # A defence is scored from the other side of its own game, which is
            # the only place points and yards allowed are paired up. Yards need
            # the box score; points do not, so a defence still scores if the
            # summary is unavailable - on points and big plays alone.
            teams = hit[2] if len(hit) > 2 else {}
            if len(clubs) == 2:
                for me, other in ((0, 1), (1, 0)):
                    ab, _ = clubs[me]
                    opp_ab, opp_score = clubs[other]
                    allowed_yards = (teams.get(opp_ab) or {}).get("yards")
                    dst[ab] = dst_points(opp_score, allowed_yards,
                                         teams.get(ab) or {})
        return points, dst

    def games(self) -> dict:
        """Per club: how far through its game it is, and what to call that."""
        out: dict[str, dict] = {}
        for ev in (self.scoreboard().get("events") or []):
            comp = (ev.get("competitions") or [{}])[0]
            status = comp.get("status") or {}
            st = (status.get("type") or {})
            state = st.get("state") or "pre"
            period = int(status.get("period") or 0)
            clock = float(status.get("clock") or 0.0)
            if state == "post":
                played, label = 1.0, "FINAL"
            elif state == "in":
                # elapsed = whole quarters done, plus the part of this one gone
                done = max(0, period - 1) * 15.0
                played = min(0.99, (done + (15.0 - clock / 60.0)) / GAME_LENGTH_MIN)
                label = st.get("shortDetail") or f"Q{period}"
            else:
                played, label = 0.0, "PRE"
            for c in (comp.get("competitors") or []):
                ab = ((c.get("team") or {}).get("abbreviation") or "").upper()
                if ab:
                    out[ab] = {"played": round(played, 4), "state": state,
                               "label": label[:18],
                               "kickoff": (ev.get("date") or "")[:16],
                               "score": c.get("score")}
        return out

    def snapshot(self, at: float | None = None) -> dict:
        g = self.games()
        # Fantasy ids and site athlete ids are the same numbers for real people.
        # Team defences are negative in fantasy and absent from a box score, so
        # they stay unscored rather than being invented.
        started = any(v["state"] != "pre" for v in g.values())
        pts, dst = self.boxscores() if started else ({}, {})
        # No slate means the feed is unreachable, not that the league is on bye.
        # Saying "BYE" would be a definite claim the data does not support, so
        # an unavailable feed degrades to "not started" and says so out loud.
        ok = bool(g)
        players = {}
        for p in self.players:
            info = g.get(p["team"]) if ok else None
            if not ok:
                players[p["id"]] = {"s": 0.0, "r": 1.0, "g": "PRE"}
            elif info is None:                     # club genuinely has no game
                players[p["id"]] = {"s": 0.0, "r": 0.0, "g": "BYE"}
            else:
                # Points only count once that player's own game has started.
                # A real box score cannot report otherwise, but a stale or
                # hand-made one can, and "12.4 points, PRE" is incoherent on a
                # board - it reads as a bug in the scoring, not in the feed.
                live_now = info["state"] != "pre"
                if p["id"].startswith("-"):
                    # A fantasy defence is -16000 minus its club id, so it is
                    # scored as a club rather than looked up as a person.
                    val = dst.get(p["team"], 0.0)
                else:
                    val = pts.get(p["id"], 0.0)
                players[p["id"]] = {
                    "s": float(val) if live_now else 0.0,
                    "r": round(1.0 - info["played"], 4),
                    "g": info["label"]}
        sb = self.scoreboard()
        payload = {
            "asOf": 0.0,
            "window": (sb.get("week") or {}).get("number", 0),
            "source": "espn" if ok else "espn-unavailable",
            "scored": len(pts) + len(dst),
            "games": g,
            "players": players,
        }
        payload["version"] = hashlib.sha1(
            json.dumps(players, sort_keys=True,
                       separators=(",", ":")).encode()).hexdigest()[:16]
        return payload


def roster_players(store, provider: str, league: str, season: int,
                   week: int | None = None) -> list[dict]:
    """The starters this league actually fielded, as live-feed candidates.

    Reads the normalized tables, so it is provider-agnostic by construction.
    """
    if week is None:
        rows = store.q(
            "SELECT MAX(week) w FROM roster_slot WHERE provider=? AND league_id=? "
            "AND season=?", (provider, str(league), season))
        week = (rows[0]["w"] if rows and rows[0]["w"] else 1)
    rows = store.q(
        """SELECT r.team_id, r.player_id, r.slot, r.started, r.points, r.projected,
                  p.name, p.pos, p.nfl_team
           FROM roster_slot r
           LEFT JOIN player p ON p.provider=r.provider AND p.player_id=r.player_id
           WHERE r.provider=? AND r.league_id=? AND r.season=? AND r.week=?""",
        (provider, str(league), season, week))
    return [{"player_id": r["player_id"], "name": r["name"] or "?",
             "pos": r["pos"] or "", "team": team_abbr(r["nfl_team"]),
             "team_id": r["team_id"], "slot": r["slot"],
             "started": bool(r["started"]),
             "projected": r["projected"] or r["points"] or 0.0,
             "week": week}
            for r in rows]
