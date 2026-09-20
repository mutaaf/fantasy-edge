"""Read-only JSON API over the local database.

`serve` is a draft board: it holds an ESPN cookie, polls the provider, and is
bound to loopback for exactly that reason. This is the opposite thing. It
touches no provider, needs no credential, and answers only from rows already
in SQLite - which is what makes it safe to bind to the LAN so a TV, a headset
or a browser on another device can read it.

    python3 -m fantasyedge api --host 0.0.0.0

The split is deliberate. Anything needing a live cookie stays in `serve` on
loopback; anything a second device should render lives here. A client that
wants both talks to both, and only the machine running `serve` ever holds a
session credential.

Every response is JSON. Analyses are cached against the database file's mtime,
so a client may poll as fast as it likes and still pay for the SQL only after
a `pull` actually changes something.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote

from . import analytics, identity
from .store import Store

MOSAIC = pathlib.Path(__file__).parent / "templates" / "mosaic.html"
REDZONE = pathlib.Path(__file__).parent / "templates" / "redzone.html"

#: How wide a portrait is asked for when it is going in a list row rather than
#: a hero. The bare path returns the full original, which for a page of
#: twenty-three of them is several megabytes of image to draw at 44 points.
CARD_WIDTH = 200

def correct_finished() -> bool:
    """Whether a finished game's plays are corrected against nflverse.

    On by default, because a replayed game should be drawn from what happened
    rather than from what its text implied; off with
    FANTASYEDGE_CORRECT_PLAYS=0 for a run that must not touch the network.
    Read per call, not at import, so a test can turn it off after this module
    is loaded. A live game is never affected: nothing is published yet.
    """
    return os.environ.get("FANTASYEDGE_CORRECT_PLAYS", "1") != "0"

ROUTES = [
    ["GET", "/api", "this index"],
    ["GET", "/api/health", "database reachability and row counts"],
    ["GET", "/api/leagues", "every league in the database"],
    ["GET", "/api/leagues/{provider}/{id}", "one league: seasons, managers, your team"],
    ["GET", "/api/leagues/{provider}/{id}/analyses", "all nine analyses (?keys=a,b to filter)"],
    ["GET", "/api/leagues/{provider}/{id}/analyses/{key}", "one analysis"],
    ["GET", "/api/leagues/{provider}/{id}/managers", "manager dossiers, career scope"],
    ["GET", "/api/leagues/{provider}/{id}/standings", "standings (?season=, default latest)"],
    ["GET", "/api/leagues/{provider}/{id}/draft", "draft log (?season=, default latest)"],
    ["GET", "/api/mosaic", "every league at once - the parent board"],
    ["GET", "/api/mosaic/{provider}/{id}", "static half of one league's board"],
    ["GET", "/api/live", "shared game state - identical for every user"],
    ["GET", "/api/redzone", "every game ranked by urgency, and the one to watch"],
    ["GET", "/api/headlines", "NFL news, tagged with the players you roster"],
    ["GET", "/api/injuries", "which of your starters got hurt, and the damage"],
    ["GET", "/api/players", "every player you roster, across every league"],
    ["GET", "/api/universe", "every player known, filterable (?pos=&scope=&q=)"],
    ["GET", "/api/gamecast/{event}", "one game: drives, plays, ball position, win prob"],
    ["GET", "/api/player/{id}", "one player in depth: season log, ranks, draft history"],
    ["GET", "/api/rankings", "today's slate ranked, the way a pre-game show would"],
    ["GET", "/api/projections", "every source's number per player (?season=&week=&source=&pos=&q=&limit=)"],
    ["GET", "/api/projections/sources", "which sources are loaded, and what the rest are waiting on"],
    ["GET", "/api/context", "scoring plays, ESPN links, and ESPN's own injury report"],
    ["GET", "/api/prefs", "your team in each league, their order, and what is hidden"],
    ["POST", "/api/prefs", "update those - loopback only, see the handler"],
    ["GET", "/api/intel", "the computed brief: insights, caveats, provenance"],
    ["GET", "/api/intel/models", "which model providers are configured"],
    ["POST", "/api/intel/narrate", "narrate the brief - loopback only, costs money"],
    ["GET", "/api/scene/{event}", "one live game as renderable geometry: field, arcs, lasers, moments"],
    ["GET", "/api/lastweek", "last week's games and why each is worth replaying (?spoilers=&offline=)"],
    ["GET", "/api/replay", "the replay being driven, and every captured game"],
    ["POST", "/api/replay", "load, play, pause, seek, speed - loopback only, see the handler"],
    ["GET", "/api/replay/markers", "the loaded replay's scores and drives, in game seconds"],
    ["GET", "/api/replay/live", "the replay's own /api/live - labelled, never the real one"],
    ["GET", "/api/replay/gamecast", "the replayed game's gamecast, with the controls' state"],
    ["GET", "/api/replay/scene", "the replayed game as renderable geometry, paced to its speed"],
]

RASTER = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".heic")


def raster(url: str) -> bool:
    """Whether a plain image view can draw this without an SVG renderer.

    Thirty of thirty-two fantasy team badges in this install are SVG, which
    neither SwiftUI's AsyncImage nor an <img> used as a CSS background will
    rasterise reliably. Saying so here means every surface makes the same
    decision from the same fact, rather than each one discovering it by
    rendering nothing.
    """
    u = (url or "").lower().split("?")[0]
    if not u:
        return False
    if u.endswith(".svg"):
        return False
    # A path with no extension is usually a content-addressed upload, which
    # ESPN serves as a raster.
    return u.endswith(RASTER) or "." not in u.rsplit("/", 1)[-1]


COUNTED = ("league", "manager", "player", "draft_pick", "roster_slot",
           "matchup", "txn", "standing", "adp")

# Cache policy is a property of what the data *is*, not of the endpoint that
# serves it, so it is declared once here and attached per response.
#
# The live tier is the interesting one. `max-age=2` looks pointlessly short
# until you count: a shared CDN honouring it collapses every request in a two
# second window into a single origin fetch, so ten million viewers cost the
# origin half a fetch per second. The payload is identical for all of them,
# which is the only reason that works - see live.py.
IMMUTABLE = "public, max-age=31536000, immutable"
DERIVED = "public, max-age=60, stale-while-revalidate=86400"
CONFIG = "public, max-age=30, stale-while-revalidate=300"
LIVE = "public, max-age=2, stale-while-revalidate=8"
PRIVATE = "no-cache"
# A replay is shared bytes like the live tier, but it moves when someone
# presses a button, and a cache serving the frame from before a scrub for
# eight seconds of stale-while-revalidate is a remote control that ignores
# you. Nothing between here and the screen may keep it.
REPLAY = "no-store"

# ── model spend ──────────────────────────────────────────────────────────────
#
# Everything above this line is arithmetic over rows that are already on disk,
# so the only cost of a wrong cache decision is CPU. A narration is a paid API
# call, and the failure mode is not a slow page - it is a bill. Three rules,
# and the first is the one that matters:
#
#   1. No GET produces a narration. `/api/intel` returns the computed brief and
#      whatever prose has already been paid for; it never reaches a provider.
#      A board left open on a television polls this route for hours.
#   2. A narration is cached against the *shape* of the brief rather than its
#      exact numbers, so a point of win probability does not buy a new one.
#   3. Even a shape change cannot spend faster than MIN_INTERVAL. Rule 2 makes
#      the common case free; rule 3 is what bounds a client that got rule 1
#      wrong and posts in a loop.
NARRATION_TTL = 12 * 3600         # override with FANTASYEDGE_AI_TTL
NARRATION_MIN_INTERVAL = 120      # override with FANTASYEDGE_AI_MIN_INTERVAL


def _env_int(name: str, default: int) -> int:
    try:
        return max(0, int(os.environ.get(name) or default))
    except ValueError:
        return default


def _bucket(value: float, unit: str) -> str:
    """One numeric fact, coarsened to the granularity a sentence cares about.

    This is the whole cost model in one function. `Win probability 61%` and
    `Win probability 62%` are the same paragraph of English, so they must hash
    the same or a live Sunday re-buys the identical prose every few seconds.
    The step per unit is the smallest move that would actually change what a
    narrator wrote:

      %      10 points - the difference between "comfortable" and "a coin flip"
      pts     5 points - roughly a touchdown; less than that is drift
      counts  exact    - two line-ups and three line-ups are different claims,
                         and these never wobble on their own
    """
    if unit == "%":
        return str(int(round(value / 10.0)))
    if unit == "pts":
        return str(int(round(value / 5.0)))
    return f"{value:g}"


def narration_shape(brief) -> str:
    """What a narration is keyed on: which findings fired, about whom, roughly.

    Not `prompt_for(brief)`. That hash is exact, and exact is wrong here - it
    moves on every scoring play, so a client that re-asks after each one pays
    for a fresh paragraph that reads the same as the last. Not the insight keys
    alone either, because those would hold a stale sentence through a genuine
    collapse. So: the set of findings, the players they name, and every number
    rounded to the step at which the English changes.
    """
    parts = [f"{brief.season}/{brief.week}"]
    for i in brief.insights:
        who = ",".join(sorted(str(p.get("id") or p.get("name") or "")
                              for p in (i.players or [])))
        facts = []
        for f in i.facts:
            v = f.value
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                facts.append(f"{f.label}={v}")
            else:
                facts.append(f"{f.label}~{_bucket(float(v), f.unit)}")
        parts.append(f"{i.key}|{i.kind}|{i.league_id}|{who}|{'&'.join(facts)}")
    return hashlib.sha1("\n".join(parts).encode()).hexdigest()[:16]


class HttpError(Exception):
    """A response the client should see as a status code, not a traceback."""

    def __init__(self, code: int, message: str, fix: str = ""):
        super().__init__(message)
        self.code, self.message, self.fix = code, message, fix


def _result(r: analytics.Result) -> dict:
    """The same shape `analyze --json` emits, so clients learn one contract."""
    return {"key": r.key, "title": r.title, "headline": r.headline,
            "columns": r.columns, "rows": r.rows,
            "caveat": r.caveat, "note": r.note, "empty": r.empty}


class Api:
    """Query layer. One Store per thread, one analysis cache per database."""

    def __init__(self, db: str = "data/fantasy.db", allow_ai: bool = True):
        self.db = db
        self.allow_ai = allow_ai
        self._local = threading.local()
        self._lock = threading.Lock()
        self._cache: dict[tuple, tuple[float, object]] = {}
        self._stores: list[Store] = []
        # The brief is memoised in one slot rather than through `cached()`.
        # `cached()` keeps an entry per key forever, and this key contains the
        # live payload's content hash, which changes on every scoring play - a
        # Sunday would leave a few thousand whole briefs pinned in memory.
        # There is exactly one user of this endpoint, so one slot is the right
        # number.
        self._brief: tuple[tuple, object] | None = None
        # Narration state. Deliberately *not* the key: the key is read from the
        # environment at call time and never lands on this object, so a LAN
        # client reading the tier above can never be answered out of a
        # credential this process is holding.
        self._narrations: dict[str, dict] = {}
        self._last_call = 0.0
        self._calls = 0
        # The channel's memory: which game is on screen, since when, and when
        # each game last scored. One slot, because a channel shows one game.
        self._whip: dict = {"focus": "", "since": 0.0, "scored": {}, "totals": {}}

    # ---------- plumbing ----------

    def store(self) -> Store:
        """sqlite3 connections are single-thread by default and the server is
        threaded, so each thread keeps its own rather than sharing one."""
        st = getattr(self._local, "store", None)
        if st is None:
            st = self._local.store = Store(self.db)
            with self._lock:
                self._stores.append(st)      # so close() can reach every thread's
        return st

    def close(self) -> None:
        with self._lock:
            stores, self._stores = self._stores, []
        for st in stores:
            try:
                st.close()
            except Exception:
                pass

    def _stamp(self) -> float:
        """Database mtime. Cache keys hang off this so a `pull` invalidates
        everything and a poll storm invalidates nothing."""
        try:
            return self.store().path.stat().st_mtime
        except OSError:
            return 0.0

    def cached(self, key: tuple, build):
        stamp = self._stamp()
        with self._lock:
            hit = self._cache.get(key)
            if hit and hit[0] == stamp:
                return hit[1]
        value = build()
        with self._lock:
            self._cache[key] = (stamp, value)
        return value

    def _entry(self, provider: str, league: str) -> dict:
        """The followed-leagues record, which is where `also` ids live. A league
        recreated for a new season gets a fresh id on ESPN; without `also` its
        managers look like they have never played before."""
        from . import leagues as lg
        return next((e for e in lg.load()
                     if e.get("provider") == provider
                     and str(e.get("league_id")) == str(league)), {})

    def _seasons(self, provider: str, league: str) -> list[int]:
        rows = self.store().q(
            "SELECT season FROM league WHERE provider=? AND league_id=? "
            "ORDER BY season DESC", (provider, str(league)))
        return [int(r["season"]) for r in rows]

    def _require_league(self, provider: str, league: str) -> list[int]:
        seasons = self._seasons(provider, league)
        if not seasons:
            raise HttpError(404, f"No league {provider}/{league} in the database.",
                            f"python3 -m fantasyedge pull --provider {provider} "
                            f"--league {league} --seasons 2019-2026")
        return seasons

    def _season_arg(self, provider: str, league: str, qs: dict) -> int:
        seasons = self._require_league(provider, league)
        raw = (qs.get("season") or [""])[0]
        if not raw:
            return seasons[0]
        try:
            want = int(raw)
        except ValueError:
            raise HttpError(400, f"season must be a year, got {raw!r}")
        if want not in seasons:
            raise HttpError(404, f"Season {want} not loaded for {provider}/{league}.",
                            f"loaded: {', '.join(str(s) for s in seasons)}")
        return want

    # ---------- endpoints ----------

    def index(self) -> dict:
        return {"service": "fantasy-edge", "readonly": True, "routes": ROUTES}

    def health(self) -> dict:
        from . import __version__
        store = self.store()
        counts = {t: store.q(f"SELECT COUNT(*) c FROM {t}")[0]["c"] for t in COUNTED}
        seasons = [int(r["season"]) for r in
                   store.q("SELECT DISTINCT season FROM league ORDER BY season")]
        return {"ok": not store.is_empty(), "version": __version__,
                "db": str(store.path), "counts": counts, "seasons": seasons,
                "leagues": len({(r["provider"], r["league_id"])
                                for r in store.seasons()})}

    def leagues(self) -> dict:
        """Grouped by league, newest season first. The database is the source of
        truth; the followed list only annotates it."""
        from . import leagues as lg
        followed = {(e.get("provider"), str(e.get("league_id"))): e for e in lg.load()}
        out: dict[tuple, dict] = {}
        for r in self.store().seasons():
            key = (r["provider"], str(r["league_id"]))
            item = out.setdefault(key, {
                "provider": r["provider"], "league_id": str(r["league_id"]),
                "name": r["name"], "teams": r["team_count"], "seasons": [],
                "followed": key in followed,
                "also": [str(a) for a in (followed.get(key, {}).get("also") or [])],
            })
            item["seasons"].append(int(r["season"]))
            if int(r["season"]) >= max(item["seasons"]):
                item["name"], item["teams"] = r["name"], r["team_count"]
        return {"leagues": sorted(out.values(), key=lambda c: -max(c["seasons"]))}

    def league(self, provider: str, league: str) -> dict:
        from . import leagues as lg
        seasons = self._require_league(provider, league)
        entry = self._entry(provider, league)
        cfg = lg.config_from_db(self.store(), provider, league, seasons[0],
                                tuple(entry.get("also", [])), entry.get("label", ""))
        if cfg is None:
            raise HttpError(404, f"League {provider}/{league} has no managers stored "
                                 f"for {seasons[0]}.", "re-run `pull` for that season")
        cfg["seasons"] = seasons
        cfg["followed"] = bool(entry)
        return cfg

    def analyses(self, provider: str, league: str, keys: list[str] | None = None) -> dict:
        self._require_league(provider, league)
        wanted = keys or list(analytics.ANALYSES)
        for k in wanted:
            if k not in analytics.ANALYSES:
                raise HttpError(404, f"No analysis {k!r}.",
                                f"known: {', '.join(analytics.ANALYSES)}")
        results = self.cached(
            ("analyses", provider, league),
            lambda: [_result(r) for r in
                     analytics.run_all(self.store(), provider, str(league))])
        by_key = {r["key"]: r for r in results}
        return {"provider": provider, "league_id": str(league),
                "analyses": [by_key[k] for k in wanted if k in by_key]}

    def managers(self, provider: str, league: str) -> dict:
        self._require_league(provider, league)
        also = tuple(self._entry(provider, league).get("also", []))
        doss = self.cached(
            ("managers", provider, league, also),
            lambda: analytics.manager_dossier(self.store(), provider, str(league), also))
        return {"provider": provider, "league_id": str(league),
                "also": [str(a) for a in also], "managers": doss}

    def standings(self, provider: str, league: str, qs: dict) -> dict:
        season = self._season_arg(provider, league, qs)
        rows = self.store().q(
            """SELECT s.rank, s.team_id, m.name AS team, m.owner, m.logo,
                      s.wins, s.losses, s.ties, s.points_for, s.points_against
               FROM standing s
               LEFT JOIN manager m ON m.provider=s.provider AND m.league_id=s.league_id
                                  AND m.season=s.season AND m.team_id=s.team_id
               WHERE s.provider=? AND s.league_id=? AND s.season=?
               ORDER BY s.rank""",
            (provider, str(league), season))
        out = []
        for r in rows:
            d = dict(r)
            d["logo"] = d.get("logo") or ""
            d["logoRaster"] = raster(d["logo"])
            out.append(d)
        return {"provider": provider, "league_id": str(league), "season": season,
                "standings": out}

    def draft(self, provider: str, league: str, qs: dict) -> dict:
        from . import leagues as lg
        season = self._season_arg(provider, league, qs)
        log = lg.draft_log(self.store(), provider, str(league), season)
        return {"provider": provider, "league_id": str(league), "season": season,
                "columns": ["overall", "round", "team", "player", "pos", "adp"],
                "picks": log}


    # ---------- the live tier ----------

    def live_source(self):
        """One shared simulator for the whole process.

        Built from every player any followed league has rostered, because the
        live tier is global by definition: it must not vary by who is asking,
        or it stops being cacheable. Swapping this for the real feed is one
        subclass of `live.LiveSource` and changes nothing above it.
        """
        with self._lock:
            src = getattr(self, "_live", None)
        if src is None:
            from . import live as livemod

            players = self._live_players()
            # Real game state by default. It needs no credential - this is the
            # same public feed espn.com renders - so it belongs in this
            # credential-free process rather than in `serve`. The simulator
            # stays available for working on the board out of season, but it
            # is opt-in: a board that invents a Sunday is worse than one that
            # honestly says nothing has kicked off.
            if os.environ.get("FANTASYEDGE_SIMULATE") == "1":
                src = livemod.SimulatedSource(players, seed=7, speed=90.0,
                                              start=time.time() - 100.0)
            else:
                src = livemod.EspnLiveSource(players, scoring=self._scoring())
            with self._lock:
                self._live = src
        return src

    def _live_players(self) -> list[dict]:
        from . import live as livemod

        # Grouped by provider as well as id. A player id is only unique
        # within the provider that issued it, so grouping on the id alone
        # merges two different people the moment a second provider is
        # followed - ESPN's 4262921 and a Sleeper id are unrelated numbers
        # that collide as strings.
        rows = self.store().q(
            """SELECT r.provider, r.player_id, p.name, p.pos, p.nfl_team,
                      MAX(COALESCE(r.projected, r.points, 0)) AS proj
               FROM roster_slot r
               LEFT JOIN player p ON p.provider=r.provider
                                 AND p.player_id=r.player_id
               WHERE p.name IS NOT NULL
               GROUP BY r.provider, r.player_id""")
        return [{"player_id": r["player_id"], "name": r["name"],
                 "pos": r["pos"] or "", "team": livemod.team_abbr(r["nfl_team"]),
                 # Only ESPN's fantasy ids double as site athlete ids.
                 # Everyone else joins to a box score by name.
                 "espn_ids": r["provider"] == "espn",
                 "projected": r["proj"] or 0.0} for r in rows]

    def _scoring(self):
        # The league's own scoring, so a half-PPR board is not told it is
        # winning by a point it does not actually score.
        from .cli import load_config
        from .scoring import Scoring
        try:
            return Scoring.from_config(load_config())
        except Exception:
            return Scoring()

    # ---------- replay ----------

    def replay_director(self):
        """The one replay this process can be driven through.

        Captures live under `FANTASYEDGE_REPLAY_DIR`, `data/replay/source` by
        default - the same directory `replay --capture` fills, so a game
        captured on the command line is already in the app's picker.
        """
        with self._lock:
            director = getattr(self, "_replay", None)
            if director is None:
                from .replay import ReplayDirector
                root = os.environ.get("FANTASYEDGE_REPLAY_DIR", "data/replay/source")
                director = self._replay = ReplayDirector(pathlib.Path(root))
        return director

    def replay_source(self):
        """A live source of its own, reading the director instead of ESPN.

        Separate from `live_source()` on purpose. Routing a replay through the
        real source would be one environment variable away from a recorded
        game showing up on `/api/live` as though it were being played. Here
        the two cannot meet: the real routes never see this instance.

        No cache: the director already memoises frames by game second, and a
        scrub must show on the next poll, not twenty seconds later.
        """
        from . import live as livemod

        with self._lock:
            src = getattr(self, "_replay_src", None)
        if src is None:
            src = livemod.EspnLiveSource(self._live_players(), ttl=0.0, box_ttl=0.0,
                                         http=self.replay_director().fetch,
                                         scoring=self._scoring())
            with self._lock:
                self._replay_src = src
        return src

    def _replay_loaded(self):
        director = self.replay_director()
        if not director.event:
            raise HttpError(404, "No replay is loaded.",
                            'POST /api/replay {"action": "load", "event": "401772949"}')
        return director

    def replay_state(self) -> dict:
        director = self.replay_director()
        return {**director.state(), "games": director.catalog()}

    def last_week(self, qs: dict | None = None) -> dict:
        """Last week's slate as a picker reads it.

        Scores are withheld unless `?spoilers=1`, so the default answer can be
        put on screen beside a "watch it" button without ending the game for
        whoever presses it. `?offline=1` answers from the pulled slate alone.

        The week is *not* pulled here. A GET that spends sixteen requests on
        ESPN because somebody opened a screen is a GET that will be opened
        sixteen times; pulling stays an explicit act, on the command line or
        through POST /api/replay's own capture.
        """
        qs = qs or {}
        flag = lambda k: (qs.get(k) or ["0"])[0] not in ("0", "", "false")  # noqa: E731
        root = pathlib.Path(os.environ.get("FANTASYEDGE_REPLAY_DIR",
                                           "data/replay/source"))
        from . import week as wk

        try:
            out = wk.last_week(source=root, reveal=flag("spoilers"),
                               offline=flag("offline"))
        except SystemExit as exc:
            raise HttpError(503, str(exc),
                            "python3 -m fantasyedge last-week --pull") from exc
        out["open"] = {"method": "POST", "path": "/api/replay",
                       "body": {"action": "load", "event": "<event>"}}
        return out

    def replay_markers(self) -> dict:
        """Where the scores and drives are in the loaded game."""
        return self._replay_loaded().markers()

    def replay_live(self) -> dict:
        self._replay_loaded()
        snap = self.replay_source().snapshot()
        snap["source"] = "replay"
        return snap

    def replay_gamecast(self) -> dict:
        director = self._replay_loaded()
        out = self.gamecast(director.event, src=self.replay_source())
        out["replayControl"] = director.state()
        return out

    def live_league(self) -> str:
        """Which league the feed is serving, in the scene's own vocabulary.

        ESPN states it on the board it just answered with (`leagues[0].slug`),
        and its slugs are the names `scene.py` already branches on - `nfl` and
        `college-football` - so this is a read, not a translation.

        It is read rather than assumed because the difference reaches the
        grass: a college field's hash marks are far wider than the NFL's, so a
        Saturday drawn as a Sunday puts every play in the wrong place across
        the field. A constant here is invisible until the day it is wrong.
        """
        board = self.live_source().scoreboard()
        return ((board.get("leagues") or [{}])[0].get("slug") or "nfl")

    def scene(self, event: str) -> dict:
        from . import scene as sc
        return sc.build(self.gamecast(event), league=self.live_league(), speed=1.0)

    def replay_scene(self) -> dict:
        from . import scene as sc
        director = self._replay_loaded()
        out = sc.build(self.gamecast(director.event, src=self.replay_source()),
                       league="nfl", speed=director.speed)
        control = director.state()
        # Where "replay this drive" seeks to: the game second of the shown
        # drive's first snap. Only the replay knows game seconds, so it is
        # stated here rather than rebuilt from clock strings on each client.
        drive = (out["drives"][out["currentDrive"]] if out["currentDrive"] is not None
                 else (out["drives"][-1] if out["drives"] else None))
        control["driveStart"] = director.seconds_of(drive["arcs"][0]["id"]) \
            if drive and drive["arcs"] else None
        out["replayControl"] = control
        return out

    def replay_control(self, body: dict) -> dict:
        director = self.replay_director()
        try:
            state = director.control(body)
        except (ValueError, TypeError) as exc:
            raise HttpError(400, str(exc), 'actions: load {event, capture?, at?}, '
                                           'play, pause, seek {at}, speed {speed}')
        except LookupError as exc:
            raise HttpError(404, str(exc), 'load a game first: {"action": "load", "event": ...}')
        except SystemExit as exc:
            raise HttpError(404, str(exc), "capture it with `python3 -m fantasyedge "
                                           "replay --game EVENT --at 0`")
        return {**state, "games": director.catalog()}

    def live(self) -> dict:
        return self.live_source().snapshot()

    def redzone(self) -> dict:
        """Every game at once, ranked, with the one the channel is showing.

        Shared bytes like `/api/live`, and for the same reason: which game is
        most urgent is a fact about the slate, not about the viewer, so one
        answer serves everybody and a cache can hold it. Pinning is the
        viewer's own business and stays in the browser - the moment this
        response varied by who asked, the cost model in `live.py` would
        collapse.

        The focus is decided here rather than in the page so that two screens
        in the same room show the same game, and because the hysteresis needs
        to remember what was on screen a moment ago. That memory is this one
        slot: a channel has one current game by definition.
        """
        from . import live as livemod
        from . import whip

        with self._lock:
            state = self._whip
        now = time.time()
        rows = whip.slate(self.live_source().games(), colors=livemod.team_color)

        # When a score changed, so a touchdown can hold its own game on screen
        # for a few seconds. Kept here because it is the only place that sees
        # consecutive polls; the page is stateless between refreshes and a
        # score is the one thing it cannot work out from a single frame.
        scored = dict(state["scored"])
        for row in rows:
            key = row["event"]
            total = row["homeScore"] + row["awayScore"]
            if state["totals"].get(key) not in (None, total):
                scored[key] = now
            state["totals"][key] = total

        ranked = whip.rank(rows, scored=scored, now=now)
        held = now - state["since"] if state["focus"] else 0.0
        focus = whip.choose(ranked, state["focus"], held=held)
        if focus != state["focus"]:
            state["focus"], state["since"] = focus, now
        state["scored"] = {k: v for k, v in scored.items()
                           if now - v <= whip.SCORE_HOLD}

        live_now = [g for g in ranked if g["state"] == "in"]
        # The feed states which league it is (`leagues[0].slug`), so the page
        # is told rather than assuming. A constant here would be the thing
        # that breaks the day this serves a college Saturday.
        board = self.live_source().scoreboard()
        league = ((board.get("leagues") or [{}])[0].get("slug") or "")
        return {
            "league": league,
            "asOf": round(now, 3),
            "source": "espn",
            "error": self.live_source().last_error,
            "focus": focus,
            "counts": {"live": len(live_now), "total": len(ranked),
                       "final": sum(1 for g in ranked if g["state"] == "post"),
                       "redZone": sum(1 for g in live_now if g["redZone"])},
            "games": ranked,
        }

    def redzone_page(self) -> bytes:
        """The channel, served whole and static.

        Nothing is inlined, unlike the mosaic: this page needs no database and
        no league, so there is nothing personal to bake in. It asks
        `/api/redzone` for everything and is therefore the same bytes for
        every viewer, which is what lets a cache hold it.
        """
        if not REDZONE.exists():
            return b"<p>redzone.html is missing from fantasyedge/templates/</p>"
        return REDZONE.read_bytes()

    def mosaic_page(self) -> bytes:
        """The board, with every league's static half already inlined.

        Injecting it means the page paints real matchups on the first frame
        rather than flashing an empty grid while a fetch resolves.
        """
        if not MOSAIC.exists():
            return b"<p>mosaic.html is missing from fantasyedge/templates/</p>"
        try:
            data = self.mosaics()
            # Inlined so the page is whole on first paint and still whole when
            # published somewhere with no API behind it.
            data["prefs"] = self.prefs()
            for key, fn in (("players", self.players), ("headlines", self.headlines),
                            ("injuries", self.injuries), ("rankings", self.rankings),
                            ("context", self.context),
                            # Inlined whole, per-source numbers and all, so the
                            # source picker can switch the board's projections
                            # without a round trip - and so a published page
                            # with no API behind it still shows both sources
                            # rather than falling back to whichever one was
                            # baked into the roster rows.
                            ("projections", lambda: self.projections({}))):
                try:
                    data[key] = fn()
                except Exception:
                    data[key] = None

            # Profiles for everyone you roster, inlined. A published page has no
            # API behind it, and a card that can only go deep when a server
            # happens to be running is a card with two personalities.
            try:
                from . import profile as prof

                # The page is built once, so this is the moment to pay for the
                # live line: it is the only thing that can be restated across
                # scoring formats, and a card built without it silently drops
                # a whole section.
                raw = {}
                try:
                    src = self.live_source()
                    if hasattr(src, "raw_stats"):
                        raw = src.raw_stats()
                except Exception:
                    raw = {}
                # Every player a card can be opened on: both starting line-ups
                # in every league, today's ranked slate, anyone hurt, and your
                # own bench. A card that goes deep for your players and shallow
                # for the man across from you is half a feature.
                want: set[str] = set()
                for L in data["leagues"]:
                    for side in ("you", "opp"):
                        for pl in (L.get(side) or {}).get("starters") or []:
                            want.add(str(pl["id"]))
                for pl in (self.players().get("players") or []):
                    want.add(str(pl["id"]))
                for r in (data.get("rankings") or {}).get("players") or []:
                    want.add(str(r["id"]))
                for i in (data.get("injuries") or {}).get("injuries") or []:
                    want.add(str(i["id"]))
                data["profiles"] = {
                    pid: prof.build(self.store(), pid, raw.get(pid))
                    for pid in sorted(want)}
            except Exception:
                data["profiles"] = {}
            # The nine analyses, per league. They have existed since the first
            # commit and the console has never shown them, which is the widest
            # gap between what this project knows and what it says out loud.
            try:
                data["analyses"] = {
                    L["id"]: self.analyses(L["provider"], L["leagueId"])["analyses"]
                    for L in data["leagues"]}
            except Exception:
                data["analyses"] = {}

        except Exception as exc:
            data = {"leagues": [], "error": str(exc)}
        page = (MOSAIC.read_text(encoding="utf-8")
                .replace("__DATA__", json.dumps(data, separators=(",", ":"), default=str))
                # Served locally there is no CSP, so images load straight from
                # the CDN. The published build swaps in embedded data URIs.
                .replace("__IMAGES__", "{}"))
        return ("<!doctype html><html lang=en><head><meta charset=utf-8>"
                "<meta name=viewport content='width=device-width,initial-scale=1'>"
                "</head><body>" + page + "</body></html>").encode("utf-8")

    def mosaic(self, provider: str, league: str, qs: dict) -> dict:
        """The static half of the board: who is on which roster, plus priors.

        Deliberately carries no scores. Scores are live and shared; this is
        personal and slow-moving, so the two are cached on completely different
        clocks and joined on the client. That split is the whole cost model.
        """
        season = self._season_arg(provider, league, qs)
        from . import live as livemod

        store = self.store()
        rows = livemod.roster_players(store, provider, str(league), season)
        if not rows:
            raise HttpError(404, f"No rosters stored for {provider}/{league} {season}.",
                            "pull that season, then retry")
        week = rows[0]["week"]

        mgr_rows = store.q(
            "SELECT team_id, name, logo FROM manager WHERE provider=? AND league_id=? "
            "AND season=?", (provider, str(league), season))
        names = {m["team_id"]: m["name"] for m in mgr_rows}
        logos = {m["team_id"]: (m["logo"] or "") for m in mgr_rows}

        want = (qs.get("team") or [""])[0]
        if not want:
            cfg = self.league(provider, league)
            want = cfg.get("myTid") or (sorted(names) or [""])[0]
        want = str(want)
        if want not in names:
            raise HttpError(404, f"No team {want} in {provider}/{league} {season}.",
                            f"teams: {', '.join(sorted(names))}")

        opp = next((r["opponent_id"] for r in store.q(
            "SELECT opponent_id FROM matchup WHERE provider=? AND league_id=? "
            "AND season=? AND week=? AND team_id=?",
            (provider, str(league), season, week, want))), None)

        def side(team_id):
            return [{"id": r["player_id"], "name": r["name"], "pos": r["pos"],
                     "team": r["team"], "slot": r["slot"],
                     "projected": round(float(r["projected"] or 0.0), 1),
                     "color": livemod.team_color(r["team"]),
                     "img": livemod.headshot_url(r["player_id"], r["team"]),
                     "logo": livemod.logo_url(r["team"])}
                    for r in rows
                    if r["team_id"] == team_id and r["started"]]

        # Priors are what a history database buys you that a scoreboard cannot:
        # win probability that knows this opponent leaves points on the bench.
        # Team names arrive from the provider with stray whitespace, and the
        # payload trims them. Trim the prior keys to match or every join here
        # silently misses - which reads as "this manager has no history"
        # rather than as the bug it is.
        priors = {}
        for r in self.analyses(provider, league, ["bench", "luck"])["analyses"]:
            for row in r["rows"]:
                priors.setdefault(str(row[0]).strip(), {})[r["key"]] = row[-1]

        # Every rostered player, not just the two starting line-ups. The board
        # only needs your matchup, but the rankings answer a league-wide
        # question - who is actually winning the week, and who owns him - and
        # that cannot be answered from two rosters.
        roster = [{"id": r["player_id"], "name": r["name"], "pos": r["pos"],
                   "team": r["team"], "slot": r["slot"],
                   "projected": round(float(r["projected"] or 0.0), 1),
                   "teamId": r["team_id"], "owner": names.get(r["team_id"], r["team_id"]),
                   "started": bool(r["started"]),
                   "color": livemod.team_color(r["team"]),
                   "img": livemod.headshot_url(r["player_id"], r["team"]),
                   "logo": livemod.logo_url(r["team"])}
                  for r in rows]

        # Every pairing this week, not just yours. Without ESPN_SWID there is no
        # way to know which team is the user's, and guessing puts a stranger's
        # roster on the board under the word "you". Shipping the whole bracket
        # lets the client switch teams instantly and without asking again.
        pairs = {}
        for row in store.q(
                "SELECT team_id, opponent_id FROM matchup WHERE provider=? "
                "AND league_id=? AND season=? AND week=?",
                (provider, str(league), season, week)):
            if row["opponent_id"]:
                pairs[str(row["team_id"])] = str(row["opponent_id"])

        return {"provider": provider, "leagueId": str(league), "season": season,
                "week": week, "roster": roster, "matchups": pairs,
                "you": {"teamId": want, "name": names.get(want, want),
                        "starters": side(want)},
                "opp": ({"teamId": opp, "name": names.get(opp, opp),
                         "starters": side(opp)} if opp else None),
                "teams": [{"teamId": t, "name": n,
                       "logo": logos.get(t, ""),
                       "logoRaster": raster(logos.get(t, ""))}
                      for t, n in sorted(names.items())],
                "priors": priors}

    def mosaics(self) -> dict:
        """Every league at once - the parent level of the board.

        The same leverage model runs at both levels: a league whose matchup is
        a coin flip earns a bigger cell than one already decided, exactly as a
        player does inside a league. That is why this returns whole rosters
        rather than a summary - the client computes both levels from one
        payload and never asks twice.
        """
        # Before kickoff the board has no scores to show, so it shows judgement
        # instead: how well the projections it is sizing by have actually done.
        accuracy = None
        try:
            first = self.leagues()["leagues"][0]
            acc = self.analyses(first["provider"], first["league_id"],
                                ["projection_accuracy"])["analyses"][0]
            if not acc["empty"]:
                r = acc["rows"][0]
                accuracy = {"source": r[0], "weeks": r[1], "mae": r[3],
                            "bias": r[4], "hit": r[5]}
        except Exception:
            accuracy = None

        # Your saved team in each league, honoured here rather than left to
        # each client. This endpoint used to ask for no particular team, so
        # `mosaic` fell back to whoever ESPN_SWID named or, failing that, the
        # alphabetically first manager - and the whole board, win probability
        # included, was then about a stranger's roster. The web board papered
        # over it by re-asking per league; the headset had no way to.
        from . import prefs as pf
        saved = pf.load()
        picks = saved.get("teams") or {}
        hidden = set(saved.get("hidden") or [])
        order = saved.get("order") or []

        entries = [c for c in self.leagues()["leagues"]
                   if f'{c["provider"]}-{c["league_id"]}' not in hidden]
        if order:
            rank = {lid: i for i, lid in enumerate(order)}
            entries.sort(key=lambda c: rank.get(
                f'{c["provider"]}-{c["league_id"]}', len(rank)))

        out = []
        for c in entries:
            lid = f'{c["provider"]}-{c["league_id"]}'
            qs = {"team": [picks[lid]]} if picks.get(lid) else {}
            try:
                m = self.mosaic(c["provider"], c["league_id"], qs)
            except HttpError:
                continue                    # a league with nothing pulled yet
            if not m.get("opp"):
                continue                    # no opponent means no matchup to size
            out.append({
                "id": f'{c["provider"]}-{c["league_id"]}',
                "provider": c["provider"], "leagueId": c["league_id"],
                "league": c["name"], "season": m["season"], "week": m["week"],
                "you": {"teamId": m["you"]["teamId"],
                        "name": (m["you"]["name"] or "").strip(),
                        "starters": m["you"]["starters"]},
                "opp": {"teamId": m["opp"]["teamId"],
                        "name": (m["opp"]["name"] or "").strip(),
                        "starters": m["opp"]["starters"]},
                "roster": m["roster"], "priors": m["priors"],
                "matchups": m["matchups"], "teams": m["teams"],
                "record": self._record(c["provider"], c["league_id"],
                                       m["season"], m["you"]["teamId"]),
                "accuracy": accuracy,
            })
        if not out:
            raise HttpError(404, "No league has both rosters and a matchup stored.",
                            "pull a season with rosters, then retry")
        return {"leagues": out}

    def _record(self, provider: str, league: str, season: int,
                team_id: str) -> dict:
        """Your record and where it puts you, for the league rail.

        Read here rather than asked for per league by each client: four
        leagues on a headset is four extra round trips for two integers.
        """
        rows = self.store().q(
            "SELECT team_id, rank, wins, losses, ties, points_for FROM standing "
            "WHERE provider=? AND league_id=? AND season=?",
            (provider, str(league), season))
        if not rows:
            return {}
        mine = next((r for r in rows if str(r["team_id"]) == str(team_id)), None)
        if mine is None:
            return {"of": len(rows)}
        return {"wins": mine["wins"] or 0, "losses": mine["losses"] or 0,
                "ties": mine["ties"] or 0, "rank": mine["rank"],
                "of": len(rows), "pointsFor": mine["points_for"] or 0.0}

    def gamecast(self, event: str, src=None) -> dict:
        """One game, in the shape a field wants to draw.

        Everything here comes from the summary the live tier has already
        fetched for scoring, so opening a gamecast costs no extra request.
        The shaping happens here rather than on each client because a field
        is the same field on a television, a headset and a browser, and three
        implementations of "where is the ball" would be three chances to put
        it somewhere different.

        Shared, not personal: this is the same payload for every reader, which
        is what lets it cache like the rest of the live tier.

        `src` is the replay's own source when the replay routes ask; nothing
        else passes one, so the real routes can only ever read the real feed.
        """
        from .live import _num_score, headshot_url, logo_url
        from .scoring import boxscore_lines, score_boxscore

        src = src or self.live_source()
        if not hasattr(src, "summary"):
            raise HttpError(404, "This live source has no play data.",
                            "the simulated source cannot animate a real game")
        data = src.summary(event)
        if not data:
            raise HttpError(404, f"No play data for event {event}.",
                            "a game that has not kicked off is not fetched")

        head = data.get("header") or {}
        comp = ((head.get("competitions") or [{}])[0])
        status = comp.get("status") or {}
        sides = {}
        for c in (comp.get("competitors") or []):
            t = c.get("team") or {}
            sides[(c.get("homeAway") or "").lower()] = {
                "id": str(t.get("id") or ""),
                "abbr": (t.get("abbreviation") or "").upper(),
                "name": t.get("displayName") or t.get("name") or "",
                # The same name in its two parts, which the field letters its
                # end zones with (scene.club_lines). ESPN states both, so they
                # are passed through rather than split out of `displayName`.
                "location": t.get("location") or "",
                "nickname": t.get("name") or "",
                "logo": ((t.get("logos") or [{}])[0].get("href", "")
                         if t.get("logos") else logo_url(t.get("abbreviation") or "")),
                "color": "#" + (t.get("color") or "444444"),
                "altColor": "#" + t["alternateColor"] if t.get("alternateColor") else "",
                "score": _num_score(c.get("score")),
            }
        abbr_of = {s["id"]: s["abbr"] for s in sides.values()}

        # Drives, flattened to the fields a field animation actually uses.
        drives = []
        raw = data.get("drives") or {}
        # ESPN lists the drive in progress in `previous` as well as in
        # `current` (seen on college live snapshots, and nothing in the NFL
        # payload rules it out), so a live game drew that drive twice and
        # counted its score twice. `current` is the fresher copy and wins.
        current = raw.get("current")
        ordered = [d for d in (raw.get("previous") or [])
                   if not (current and str(d.get("id")) == str(current.get("id")))]
        for d in ordered + ([current] if current else []):
            plays = []
            for pl in (d.get("plays") or []):
                st, en = pl.get("start") or {}, pl.get("end") or {}
                plays.append({
                    "id": str(pl.get("id") or ""),
                    "type": (pl.get("type") or {}).get("text", ""),
                    # Who snapped it. A drive's team is not enough: a pick-six
                    # is in the offence's drive and scored by the defence.
                    "team": abbr_of.get(str((st.get("team") or {}).get("id") or ""), ""),
                    # Yards from the HOME goal line, which is what ESPN's
                    # `yardLine` is. Unlike `yardsToEndzone` it is fixed to
                    # the field: it does not flip with possession, and it is
                    # not the placeholder 0 a timeout carries or the punter's
                    # own yard line a punt carries.
                    "fromYard": st.get("yardLine"),
                    "toYard": en.get("yardLine"),
                    "text": pl.get("text") or "",
                    "clock": (pl.get("clock") or {}).get("displayValue", ""),
                    "period": (pl.get("period") or {}).get("number", 0),
                    "down": st.get("down"), "distance": st.get("distance"),
                    # Yards to the defending end zone: the one number a field
                    # needs to place the ball, and it is given rather than
                    # derived from a yard line whose direction is ambiguous.
                    "from": st.get("yardsToEndzone"),
                    "to": en.get("yardsToEndzone"),
                    "yards": pl.get("statYardage"),
                    "scoring": bool(pl.get("scoringPlay")),
                    "turnover": bool(pl.get("isTurnover")),
                    "penalty": bool(pl.get("isPenalty")),
                    "home": _num_score(pl.get("homeScore")),
                    "away": _num_score(pl.get("awayScore")),
                })
            team = (d.get("team") or {})
            drives.append({
                "id": str(d.get("id") or ""),
                "team": (team.get("abbreviation") or "").upper(),
                "description": d.get("description") or "",
                "result": d.get("displayResult") or d.get("result") or "",
                "scored": bool(d.get("isScore")),
                "yards": d.get("yards"), "plays": plays,
            })

        # Win probability, already one point per play.
        wp = [{"play": str(w.get("playId") or ""),
               "home": w.get("homeWinPercentage")}
              for w in (data.get("winprobability") or [])
              if w.get("homeWinPercentage") is not None]

        # Everyone this game has scored, whether or not anybody rosters them.
        #
        # A board is the twelve or so men in your line-ups. A game is
        # twenty-odd who put up a fantasy line, and until now the other
        # two-thirds were invisible: the Live tab could tell you your receiver
        # had eight catches and could not tell you the man opposite him had
        # nine. They come out of the summary the scoring already parsed, so
        # this costs no request.
        #
        # Shared, like everything else here. Which of these men are *yours* is
        # personal, is static between transactions, and is a set the client
        # already holds - so it is intersected there, on ids, and never
        # computed per reader on the server.
        lines = boxscore_lines(data)
        pts = score_boxscore(data, src.scoring)
        pos = self._positions(data, lines)
        players = sorted(
            ({**row,
              "points": round(pts.get(pid, 0.0), 2),
              "pos": pos.get(pid, ("", ""))[0],
              "posFrom": pos.get(pid, ("", ""))[1],
              "img": headshot_url(pid, row["team"], width=CARD_WIDTH)}
             for pid, row in lines.items()),
            key=lambda r: (-r["points"], r["name"]))

        # A finished game can be drawn from what happened rather than from
        # what the text implied. nflverse publishes the NFL's own row for
        # every play, including the one number ESPN never states - where the
        # ball was caught - so once a game is final its plays are corrected in
        # place and each carries which it is. A game still being played has no
        # published rows, and is left as the estimate it is.
        #
        # Never fatal, and never blocking a live Sunday: an unreachable or
        # unpublished source leaves every play exactly as ESPN shaped it.
        state = (status.get("type") or {}).get("state", "pre")
        truth_report = None
        if state == "post" and correct_finished():
            try:
                from . import truth
                # Corrected in one pass over the whole game, not per drive: the
                # match is a game-wide assignment, and a drive at a time would
                # let two drives claim the same row.
                flat = [p for d in drives for p in d["plays"]]
                fixed, truth_report = truth.correct_for_espn(flat, str(event))
                by_id = {str(p.get("id")): p for p in fixed}
                for d in drives:
                    d["plays"] = [by_id.get(str(p.get("id")), p) for p in d["plays"]]
            except Exception as exc:                   # noqa: BLE001
                truth_report = {"event": str(event), "covered": False,
                                "error": type(exc).__name__}

        last = drives[-1]["plays"][-1] if drives and drives[-1]["plays"] else None
        return {
            "event": str(event),
            # Whether this game's geometry is what happened or an estimate of
            # it, so a client can say so rather than implying the stronger one.
            "truth": truth_report,
            # Present only on a replay, and then always: a client must never
            # be able to mistake a recorded game for one being played.
            "replay": data.get("replay"),
            "state": (status.get("type") or {}).get("state", "pre"),
            "label": (status.get("type") or {}).get("shortDetail", ""),
            "clock": status.get("displayClock", ""),
            "period": (status.get("period") or 0),
            "home": sides.get("home", {}), "away": sides.get("away", {}),
            "possession": (comp.get("situation") or {}).get("possession", ""),
            "situation": comp.get("situation") or {},
            "lastPlay": last,
            "players": players,
            "drives": drives,
            "winProbability": wp,
            "scoringPlays": [{
                "text": sp.get("text") or "",
                "clock": (sp.get("clock") or {}).get("displayValue", ""),
                "period": (sp.get("period") or {}).get("number", 0),
                "team": ((sp.get("team") or {}).get("abbreviation") or "").upper(),
                "home": _num_score(sp.get("homeScore")),
                "away": _num_score(sp.get("awayScore")),
            } for sp in (data.get("scoringPlays") or [])],
        }

    def _positions(self, summary: dict, lines: dict) -> dict[str, tuple[str, str]]:
        """Athlete id -> (position, where the position came from).

        A box score has no position in it. It groups athletes by what they
        did, which is why `boxscore_lines` reports a role rather than a
        position - and a role is enough to sort a list but not enough to
        answer "show me the tight ends".

        Two sources, and the answer says which one it used, because a card
        that shows a position it guessed is worse than one that shows none.

          * ESPN's own `leaders` block, which carries a real position - for
            the handful of men per game it names.
          * The `player` table, which knows the position of everyone who has
            ever been on a roster in a league this install follows. An ESPN
            fantasy id is also a site athlete id, so those join directly; the
            other providers join through `identity`, on a folded name.

        Anybody neither source knows gets no position and keeps his role.
        """
        out: dict[str, tuple[str, str]] = {}
        for group in (summary.get("leaders") or []):
            for cat in (group.get("leaders") or []):
                for entry in (cat.get("leaders") or []):
                    a = entry.get("athlete") or {}
                    aid = str(a.get("id") or "")
                    ab = ((a.get("position") or {}).get("abbreviation") or "")
                    if aid and ab and aid not in out:
                        out[aid] = (ab.upper(), "espn")

        want = {pid for pid in lines if pid not in out}
        if not want:
            return out
        rows = self.store().q(
            "SELECT provider, player_id, name, pos FROM player WHERE pos IS NOT NULL")
        by_name: dict[str, str] = {}
        for r in rows:
            po = identity.position(r["pos"] or "")
            if not po:
                continue
            if r["provider"] == "espn" and str(r["player_id"]) in want:
                out[str(r["player_id"])] = (po, "roster")
            if r["name"]:
                k = identity.fold(r["name"])
                # A name two providers disagree about is left out rather than
                # decided by whichever row came back last.
                by_name[k] = po if by_name.get(k, po) == po else ""
        for pid in want - set(out):
            po = by_name.get(identity.fold(lines[pid]["name"]), "")
            if po:
                out[pid] = (po, "roster")
        return out

    def headlines(self) -> dict:
        """Recent NFL news, tagged with whoever you actually roster.

        Shared like the live tier - the same stories for everyone - so it caches
        the same way. The tagging is the useful part: a hamstring in a wire
        story matters to you only if he is in one of your line-ups, and this is
        the process that knows which.
        """
        from .providers.sleeper import normalise
        from . import serve as srv

        mine = {}
        for r in self.store().q(
                "SELECT DISTINCT p.name FROM roster_slot r "
                "JOIN player p ON p.provider=r.provider AND p.player_id=r.player_id "
                "WHERE r.started=1"):
            if r["name"]:
                mine[normalise(r["name"])] = r["name"]

        def build():
            try:
                news, as_of, count = srv.fetch_news(sorted(mine.values()), pages=1)
            except Exception:
                return {"stories": [], "asOf": "", "count": 0}
            from .live import headshot_url, team_abbr

            ident = {}
            for r in self.store().q(
                    "SELECT DISTINCT p.player_id, p.name, p.nfl_team, p.pos "
                    "FROM player p WHERE p.name IS NOT NULL"):
                ident[normalise(r["name"])] = r

            flat = []
            for name, items in news.items():
                who = ident.get(normalise(name))
                club = team_abbr(who["nfl_team"]) if who else ""
                for it in items:
                    flat.append({
                        "player": name, "headline": it["h"],
                        "detail": it["d"][:200], "published": it["p"],
                        "url": it["u"],
                        # carried so a story can draw a face without needing the
                        # player to be on the roster currently selected
                        "id": str(who["player_id"]) if who else "",
                        "pos": (who["pos"] if who else "") or "",
                        "team": club,
                        "img": headshot_url(who["player_id"], club) if who else "",
                    })
            flat.sort(key=lambda x: x["published"], reverse=True)
            return {"stories": flat[:60], "asOf": as_of, "count": count}

        return self.cached(("headlines",), build)

    def profile(self, player_id: str) -> dict:
        """One player in depth, for the card.

        Live raw stats are passed through where the slate has them, because
        they are the only line that can be restated across scoring formats -
        a stored season keeps points, not the plays behind them.
        """
        from . import profile as prof

        # Only borrow a live source that already exists. Opening a card should
        # never be the thing that triggers a slate fetch - the board owns that
        # clock, and a card that stampedes the feed to decorate itself is a bad
        # trade for one extra line of type.
        live = None
        with self._lock:
            src = getattr(self, "_live", None)
        if src is not None and hasattr(src, "raw_stats"):
            try:
                live = src.raw_stats().get(str(player_id))
            except Exception:
                live = None
        out = self.cached(("profile", str(player_id)),
                          lambda: prof.build(self.store(), player_id))
        if not out:
            raise HttpError(404, f"No player {player_id} in the database.",
                            "ids come from /api/players or a board tile")
        out = dict(out)
        out["formats"] = prof.format_lines(live) if live else []
        # Opportunity: what he is actually being given, rather than what it
        # came to. Cached on its own key because it is a season-scale fact and
        # does not move with the slate.
        out["opportunity"] = self.cached(
            ("opportunity", str(player_id)),
            lambda: prof.opportunity(player_id))
        return out

    def universe(self, qs: dict) -> dict:
        """Every player this install knows, with what is true of him.

        The board is organised around the men you already own. A players
        browser is the opposite question - everyone, filtered down - and it
        cannot be answered from the roster endpoints, which by construction
        only contain people somebody rostered.

        Ownership here is ownership *in your leagues*, counted from the same
        roster rows the board uses. It is not a league-wide percentage: no
        feed this reads publishes one, and a number labelled OWN% that quietly
        meant something else would be worse than no column.
        """
        def build():
            store = self.store()
            season = max((r["season"] for r in store.q(
                "SELECT DISTINCT season FROM roster_slot")), default=0)

            # Latest projection and club per player, one pass.
            rows = store.q(
                """SELECT p.player_id AS id, p.name, p.pos, p.nfl_team
                   FROM player p WHERE p.name IS NOT NULL""")

            owned: dict[str, list] = {}
            proj: dict[str, float] = {}
            for L in self.mosaics()["leagues"]:
                me = str(L["you"]["teamId"])
                for r in L["roster"]:
                    owned.setdefault(str(r["id"]), []).append({
                        "league": L["league"], "id": L["id"],
                        "team": r.get("owner") or "",
                        "mine": str(r.get("teamId")) == me,
                        "started": bool(r.get("started")),
                        "slot": r.get("slot") or ""})
                    if r.get("projected") is not None:
                        proj[str(r["id"])] = max(proj.get(str(r["id"]), 0.0),
                                                 float(r["projected"]))

            from .live import headshot_url, logo_url, team_abbr
            hurt = {}
            try:
                for i in (self.injuries().get("injuries") or []):
                    hurt[str(i["id"])] = i.get("label") or i.get("severity") or ""
            except Exception:
                hurt = {}

            out = []
            for r in rows:
                pid = str(r["id"])
                ab = team_abbr(r["nfl_team"])
                holders = owned.get(pid, [])
                out.append({
                    "id": pid, "name": r["name"], "pos": r["pos"] or "",
                    "team": ab,
                    "img": headshot_url(pid), "logo": logo_url(ab),
                    "projected": proj.get(pid),
                    "owned": len(holders), "mine": sum(1 for h in holders if h["mine"]),
                    "leagues": holders,
                    "status": hurt.get(pid, ""),
                })
            out.sort(key=lambda x: (-(x["projected"] or 0), x["name"]))
            return {"players": out, "count": len(out), "season": season,
                    "leagues": len(self.mosaics()["leagues"])}

        data = self.cached(("universe",), build)
        # Filtering is done here rather than on each client so a headset and a
        # television do not each ship the same predicate.
        pos = (qs.get("pos") or [""])[0].upper()
        scope = (qs.get("scope") or [""])[0].lower()
        q = (qs.get("q") or [""])[0].strip().lower()
        men = data["players"]
        if pos:
            men = [m for m in men if m["pos"].upper() == pos]
        if scope == "mine":
            men = [m for m in men if m["mine"]]
        elif scope == "free":
            men = [m for m in men if not m["owned"]]
        elif scope == "rostered":
            men = [m for m in men if m["owned"]]
        elif scope == "hurt":
            men = [m for m in men if m["status"]]
        if q:
            men = [m for m in men if q in m["name"].lower()
                   or q == m["team"].lower() or q == m["pos"].lower()]
        counts: dict[str, int] = {}
        for m in data["players"]:
            counts[m["pos"].upper()] = counts.get(m["pos"].upper(), 0) + 1
        return {"players": men, "count": len(men), "total": data["count"],
                "byPosition": counts, "leagues": data["leagues"],
                "season": data["season"]}

    def rankings(self) -> dict:
        """Today's slate, ranked - a companion to the shows that do this out loud.

        Everyone with a game in the current window, ordered by projection,
        annotated with what they did last season and whether you own them.
        Deliberately not limited to your rosters: half the value of a pre-game
        ranking is seeing the names you passed on.
        """
        from . import profile as prof

        def build():
            live = self.live()
            games = live.get("games") or {}
            today = {club for club, g in games.items()
                     if g.get("state") in ("in", "post")} or {
                     club for club, g in games.items() if g.get("state") == "pre"}

            owned: dict[str, list] = {}
            for L in self.mosaics()["leagues"]:
                me = str(L["you"]["teamId"])
                for r in L["roster"]:
                    if str(r["teamId"]) == me:
                        owned.setdefault(str(r["id"]), []).append(L["league"])

            store = self.store()
            rows = store.q(
                """SELECT r.player_id, p.name, p.pos, p.nfl_team,
                          MAX(COALESCE(r.projected, 0)) AS proj
                   FROM roster_slot r
                   JOIN player p ON p.provider=r.provider AND p.player_id=r.player_id
                   WHERE r.season=2026 AND p.name IS NOT NULL
                   GROUP BY r.player_id""")

            from .live import team_abbr
            out = []
            for r in rows:
                club = team_abbr(r["nfl_team"])
                if today and club not in today:
                    continue
                pid = str(r["player_id"])
                log = prof.season_log(store, pid, r["pos"] or "")
                played = [s for s in log if s["started"] and s["rank"]]
                last = played[-1] if played else None
                out.append({
                    "id": pid, "name": r["name"], "pos": r["pos"] or "",
                    "team": club, "projected": round(float(r["proj"] or 0), 1),
                    "scored": (live.get("players") or {}).get(pid, {}).get("s", 0.0),
                    "state": (live.get("players") or {}).get(pid, {}).get("g", ""),
                    "lastRank": last["rank"] if last else None,
                    "lastSeason": last["season"] if last else None,
                    "lastPpg": last["ppg"] if last else None,
                    "owned": owned.get(pid, []),
                })
            out.sort(key=lambda x: -x["projected"])
            for i, r in enumerate(out, start=1):
                r["rank"] = i
            return {"players": out[:120], "clubs": sorted(today),
                    "count": len(out)}

        return self.cached(("rankings",), build)

    # ---------- projections ----------

    def _proj_scope(self, qs: dict) -> tuple[int, int]:
        """Which season and week a projection question defaults to.

        `projections.current_week` owns the rule; see it for why the obvious
        `MAX(week)` is wrong twice over. Both the season and the week may be
        overridden by query string, which is the only way to reach a week the
        boards are not on.
        """
        store = self.store()
        rows = store.q("SELECT MAX(season) AS s FROM projection")
        season = int((rows[0]["s"] if rows else None) or 0)
        raw = (qs.get("season") or [""])[0]
        if raw:
            try:
                season = int(raw)
            except ValueError:
                raise HttpError(400, f"season must be a year, got {raw!r}")
        from . import projections as pj
        week = pj.current_week(store, season)
        if not week:
            rows = store.q("SELECT MIN(week) AS w FROM projection WHERE season=?",
                           (season,))
            week = int((rows[0]["w"] if rows else None) or 0)
        raw = (qs.get("week") or [""])[0]
        if raw:
            try:
                week = int(raw)
            except ValueError:
                raise HttpError(400, f"week must be a number, got {raw!r}")
        return season, week

    def projection_sources(self, qs: dict) -> dict:
        """Which sources exist, which are loaded, and what the rest need.

        Every surface builds its picker from this rather than from the distinct
        values in the table. The difference matters: a picker built from what
        is loaded silently drops CBS, FantasyPros and Yahoo, and a source that
        is simply absent reads as one that returned nothing - which is a claim
        about the players rather than about the licence.
        """
        from . import projections as pj

        season, week = self._proj_scope(qs)
        cat = self.cached(("projsrc", season, week),
                          lambda: pj.catalog(self.store(), season, week))
        live = [c for c in cat if c["loaded"]]
        return {"season": season, "week": week, "sources": cat,
                "loaded": [c["source"] for c in live],
                "n": len(live),
                "pending": [c["source"] for c in cat
                            if c["status"] == "pending" and not c["loaded"]],
                "route": pj.PENDING_ROUTE,
                # Spelled out because every client would otherwise phrase it
                # for itself, and one of them would phrase it as an average of
                # five.
                "consensus": ("mean of the " + str(len(live)) + " source(s) "
                              "actually loaded" if live else
                              "no source is loaded, so there is no consensus")}

    def projections(self, qs: dict) -> dict:
        """Every loaded source's number for each player, plus the consensus.

        `?source=` picks which source ranks the list and fills `points`; the
        per-source numbers travel with every row regardless, because the
        disagreement is the interesting part and averaging it away is the one
        thing this endpoint must not do.

        A source that is not loaded never appears in `by` and never
        contributes to `consensus`. It cannot produce a zero, an
        interpolation, or a share of a mean - see `projections.SOURCES`.
        """
        from . import projections as pj

        season, week = self._proj_scope(qs)
        data = self.cached(("projections", season, week),
                           lambda: pj.board(self.store(), season, week))
        cat = self.cached(("projsrc", season, week),
                          lambda: pj.catalog(self.store(), season, week))

        want = (qs.get("source") or [""])[0].lower()
        if want and want not in ("consensus",) and want not in data["sources"]:
            known = ", ".join(data["sources"]) or "none"
            meta = pj.SOURCES.get(want)
            raise HttpError(
                404, f"No projections loaded for source {want!r}.",
                (f"{meta['label']} needs {meta['needs']}." if meta and meta["needs"]
                 else f"loaded: {known}"))

        def value(m):
            if want and want != "consensus":
                return m["by"].get(want)
            return m["consensus"]

        men = [m for m in data["players"] if value(m) is not None]
        # Ranks are computed over the whole board before any filter, so a
        # position filter narrows what is shown without renumbering what is
        # ranked.
        men.sort(key=lambda m: -(value(m) or 0))
        pos_seen: dict[str, int] = {}
        rows = []
        for i, m in enumerate(men, start=1):
            pos_seen[m["pos"]] = pos_seen.get(m["pos"], 0) + 1
            rows.append({**m, "points": value(m), "rank": i,
                         "posRank": f'{m["pos"]}{pos_seen[m["pos"]]}' if m["pos"] else ""})

        pos = (qs.get("pos") or [""])[0].upper()
        q = (qs.get("q") or [""])[0].strip().lower()
        if pos and pos != "ALL":
            rows = [m for m in rows if m["pos"] == pos]
        if q:
            rows = [m for m in rows if q in m["name"].lower()
                    or q == m["team"].lower() or q == m["pos"].lower()]
        try:
            limit = int((qs.get("limit") or ["0"])[0])
        except ValueError:
            limit = 0
        shown = rows[:limit] if limit > 0 else rows

        disagree = sorted((m for m in data["players"] if m["spread"] is not None),
                          key=lambda m: -m["spread"])[:20]
        return {
            "season": season, "week": week,
            "source": want or "consensus",
            "sources": data["sources"], "n": data["n"],
            "catalog": cat,
            "pending": [{"source": c["source"], "label": c["label"],
                         "needs": c["needs"], "detail": c["detail"]}
                        for c in cat if c["status"] == "pending" and not c["loaded"]],
            "consensusOf": data["sources"],
            "players": shown, "count": len(shown), "total": len(rows),
            "disagreements": disagree,
        }

    def context(self) -> dict:
        """What just happened in the games your players are in."""
        def build():
            try:
                src = self.live_source()
                return src.context() if hasattr(src, "context") else {
                    "plays": [], "links": {}, "injuries": []}
            except Exception:
                return {"plays": [], "links": {}, "injuries": []}
        return self.cached(("context",), build)

    def prefs(self) -> dict:
        from . import prefs as pf
        return pf.load()

    def save_prefs(self, patch: dict) -> dict:
        from . import prefs as pf
        return pf.save(pf.merge(pf.load(), patch))

    def injuries(self) -> dict:
        """Injuries to players in one of your starting line-ups.

        Built on the same tagged wire the headlines view uses, so it costs no
        extra fetch: the expensive part is matching names, and that has already
        happened by the time this runs.
        """
        from . import injuries as inj

        def build():
            stories = self.headlines().get("stories") or []
            hurt = inj.detect(self.store(), stories)
            return {"injuries": hurt, "count": len(hurt),
                    "worst": hurt[0]["label"] if hurt else None}

        return self.cached(("injuries",), build)

    def players(self) -> dict:
        """Every player you roster, across every league you follow.

        The board is organised by league because a matchup is. This is the
        other question - "who do I actually own" - and it only has an answer
        once the leagues are collapsed. Exposure is the number that matters:
        a player in three of your line-ups is three times the Sunday.
        """
        agg: dict[str, dict] = {}
        for L in self.mosaics()["leagues"]:
            me = str(L["you"]["teamId"])
            for r in L["roster"]:
                if str(r["teamId"]) != me:
                    continue
                slot = agg.setdefault(str(r["id"]), {
                    "id": str(r["id"]), "name": r["name"], "pos": r["pos"],
                    "team": r["team"], "color": r["color"], "img": r["img"],
                    "logo": r["logo"], "projected": r["projected"],
                    "leagues": [], "starting": 0})
                slot["leagues"].append({"league": L["league"], "id": L["id"],
                                        "started": bool(r["started"])})
                slot["starting"] += 1 if r["started"] else 0
        out = sorted(agg.values(),
                     key=lambda x: (-len(x["leagues"]), -x["projected"]))
        return {"players": out, "count": len(out),
                "exposed": sum(1 for p in out if len(p["leagues"]) > 1)}

    # ---------- intel ----------

    def _safe(self, fn):
        """A payload the brief would like but can do without.

        `intel.build` is written to take `None` for live and for injuries and
        to say so in `notes`. A scoreboard that is briefly unreachable should
        cost the reader the two matchup insights that need it, not the ten that
        do not, so a failure here is a missing argument rather than a 500.
        """
        try:
            return fn()
        except Exception:
            return None

    def _prefs_sig(self) -> str:
        """Which team is yours, in what order, minus what you hid.

        In the brief's cache key because `mosaics()` honours all three and none
        of them touches the database file, so the mtime stamp `cached()` runs
        on cannot see them move. Picking a different team is the one edit most
        likely to be followed immediately by a look at this view.
        """
        try:
            from . import prefs as pf
            return hashlib.sha1(json.dumps(pf.load(), sort_keys=True)
                                .encode()).hexdigest()[:16]
        except Exception:
            return ""

    def _live_probe(self):
        """The live snapshot, re-read no more often than the tier promises.

        The brief's cache key contains the live payload's content hash, so
        validating the cache means producing that payload - and a snapshot
        costs about four tenths of a second, which a board polling every three
        seconds would pay forever just to be told nothing had changed. Two
        seconds is not a number invented here: it is `LIVE`'s own max-age, the
        staleness this project already tells every cache between here and the
        screen to accept.
        """
        now = time.time()
        with self._lock:
            hit = getattr(self, "_probe", None)
        if hit and now - hit[0] < 2.0:
            return hit[1]
        snap = self._safe(self.live)
        with self._lock:
            self._probe = (now, snap)
        return snap

    def _opportunity(self, season: int | None):
        """nflverse usage for the most recent season that has any.

        nflverse publishes weekly, so early in a new year the current season's
        release is a handful of players with one game each and every
        opportunity insight silently does not fire - the generator disappears
        from the brief with no note, which is the gap `UNAVAILABLE` exists to
        avoid leaving. Asking for last season instead is answerable and is
        what the caveat already describes; the season it actually used travels
        in the facts.

        The test is `intel.MIN_GAMES` rather than "is the release empty",
        because the 2026 release at week one is not empty: it is 47 players on
        one game apiece, which passes an emptiness check and then fails the
        generator's own floor a moment later.
        """
        from . import advanced, intel, profile

        year = int(season or 0)
        if year:
            try:
                rows = advanced.season_profiles(year)
                usable = sum(1 for r in rows.values()
                             if int(r.get("g") or 0) >= intel.MIN_GAMES)
            except Exception:
                usable = 0
            if not usable:
                year -= 1
        def opportunity(pid, _requested=None):
            # The season travels back with the row, so the Season fact names
            # the release the numbers came out of rather than the one the
            # brief happens to be about.
            o = profile.opportunity(pid, year or None)
            return dict(o, season=year) if o else o

        return opportunity, year

    def brief(self):
        """The computed brief as an `intel.Brief`, rebuilt only when it moved.

        Building one walks every followed league's mosaic, the live snapshot,
        the injury wire and up to nine analyses per league - a second or more
        of work that a board polling every few seconds would otherwise repeat
        forever. The three things that can change it are all cheap to read:
        the database mtime (already what `cached()` keys on, and what a `pull`
        moves), the live payload's own content hash, and your saved team picks.
        If none of them has moved, neither has the brief.
        """
        from . import intel

        live = self._live_probe()
        key = (self._stamp(), (live or {}).get("version") or "",
               self._prefs_sig())
        with self._lock:
            hit = self._brief
        if hit and hit[0] == key:
            return hit[1]

        mos = self._safe(self.mosaics) or {"leagues": []}
        analyses = {}
        for L in mos["leagues"]:
            got = self._safe(lambda L=L: self.analyses(L["provider"], L["leagueId"]))
            analyses[L["id"]] = (got or {}).get("analyses") or []
        season = (mos["leagues"][0].get("season") if mos["leagues"] else None)
        opp, used = self._opportunity(season)
        built = intel.build(
            mosaics=mos, live=live,
            injuries=(self._safe(self.injuries) or {}).get("injuries"),
            # `limit` is the brief's own, not the view's: this database
            # produces two dozen findings and the default twelve dropped every
            # history and opportunity insight behind ten roster conflicts.
            # The client decides what to show; the server should not decide
            # what exists.
            analyses=analyses, opportunity=opp, limit=64)
        if used and season and used != int(season):
            built.notes.append(
                f"nflverse has published no {season} usage yet, so opportunity "
                f"is computed from {used}. The season is named in each "
                f"insight's facts.")
        with self._lock:
            self._brief = (key, built)
        return built

    def _narration_block(self, brief) -> dict:
        """The narration slot of `/api/intel`, which never calls a model.

        It carries the prompt a client would send (so a Swift client running
        Apple Intelligence on device builds it from the findings and not from
        the raw payload), and any prose already paid for that still describes
        this brief. There is no field here that could trigger a request.
        """
        from . import ai

        shape = narration_shape(brief)
        with self._lock:
            entry = dict(self._narrations.get(shape) or {})
        # Budgeted, because the only client that builds its own request from
        # this block is a headset running Apple's on-device model, and that
        # model's window is smaller than a real brief. Twenty-eight findings
        # came to twenty-two thousand characters, so the request failed and the
        # view showed an apology instead of a summary. The server does the
        # trimming - a client trimming its own prompt is the one thing
        # docs/intel.md rules out, since then nobody knows what the model saw.
        full = ai.prompt_for(brief)
        capped = ai.prompt_for(brief, budget=ai.ON_DEVICE_BUDGET)
        out = {
            "prompt": {"system": ai.SYSTEM, "user": capped,
                       "budget": ai.ON_DEVICE_BUDGET,
                       "trimmed": len(capped) < len(full),
                       "fullLength": len(full)},
            "endpoint": "POST /api/intel/narrate",
            "shape": shape,
            "cached": None,
            "chat": {"available": False,
                     "note": "Conversational AI is out of scope here. "
                             "Coming soon."},
        }
        if entry and time.time() - entry["created"] <= _env_int(
                "FANTASYEDGE_AI_TTL", NARRATION_TTL):
            out["cached"] = self._served(entry, brief, cached=True)
        return out

    def _served(self, entry: dict, brief, cached: bool) -> dict:
        """One stored narration, re-checked against the brief on screen now.

        The verification is redone rather than replayed from the entry. A
        cached paragraph is served against a brief whose numbers may have
        drifted inside their bucket, and `trustworthy` has to be a statement
        about the figures the reader can see beneath the prose - otherwise the
        flag means "was true when written", which is not what the label says.
        """
        from . import ai, intel

        text = entry["text"]
        n = ai.Narration(
            text=text, provider=entry["provider"], model=entry["model"],
            grounded_in=[i.key for i in brief.insights],
            unverified=ai.verify_numbers(text, intel.allowed_numbers(brief)),
            flagged_metrics=intel.mentions_unavailable(text))
        out = n.as_dict()
        age = max(0, int(time.time() - entry["created"]))
        with self._lock:
            calls = self._calls
        out.update({
            "cached": cached, "ageSeconds": age, "createdAt": entry["created"],
            "briefShape": entry["shape"],
            # On every answer, not only a paid one, so a client can always
            # show what this session has actually spent.
            "calls": calls,
            # True when the brief has moved enough to be worth re-narrating.
            # Surfaced rather than acted on: spending is the client's call.
            "factsChanged": entry["shape"] != narration_shape(brief),
        })
        return out

    def intel_brief(self) -> dict:
        """The whole Intel view: computed findings first, prose only if bought."""
        brief = self.brief()
        out = brief.as_dict()
        out["narration"] = self._narration_block(brief)
        out["models"] = self.intel_models()["providers"]
        return out

    def intel_models(self) -> dict:
        """Which providers are configured. Booleans, never a key.

        `ai.available()` has no field that could carry a key, a prefix or a
        suffix, and this adds none. "Show me the key so I can check it" is how
        a key ends up in a screenshot; the only answerable question is whether
        one is present, and a wrong one answers itself on first use.
        """
        from . import ai

        providers = ai.available()
        if not self.allow_ai:
            # --no-ai. Reported as an explicit reason rather than by quietly
            # returning False everywhere, so a headset with nobody to type a
            # key shows "turned off here" instead of "you forgot to set it up".
            for p in providers:
                p["configured"] = False
                p["disabled"] = "This server was started with --no-ai."
        with self._lock:
            calls, last = self._calls, self._last_call
        return {"providers": providers,
                "narrate": "POST /api/intel/narrate",
                "enabled": self.allow_ai,
                # The number this whole design exists to keep at zero unless
                # somebody pressed something.
                "calls": calls,
                "nextEligibleIn": max(0, int(
                    _env_int("FANTASYEDGE_AI_MIN_INTERVAL",
                             NARRATION_MIN_INTERVAL) - (time.time() - last)))
                if last else 0,
                "keys": "Read from the environment or ~/.fantasy-edge/ai.json "
                        "at call time. Never stored by this process, never "
                        "returned by any route.",
                "chat": {"available": False, "note": "coming soon"}}

    def narrate(self, body: dict) -> dict:
        """Ask a model to write the brief up. The only paid call in this file.

        Never called by a GET. Reads the key at call time from the environment
        or `~/.fantasy-edge/ai.json` and lets it fall out of scope with the
        client, so the credential-free read tier stays credential-free even
        while this is running.
        """
        from . import ai

        if not self.allow_ai:
            raise HttpError(403, "This server was started with --no-ai.",
                            "restart without the flag; the computed brief "
                            "above needs no model and is already complete")
        provider = str(body.get("provider") or "anthropic").lower()
        supplied = str(body.get("text") or "")
        # Checked before the cache, not after. The cache is keyed on the brief
        # and not on the provider - prose about these findings is reusable
        # whoever wrote it, and the payload records which model did - but that
        # means an unrecognised name would otherwise be answered with somebody
        # else's paragraph and a 200, which reads as success to a client that
        # simply misspelled the provider.
        if provider != "apple" and not supplied and provider not in ai.CLIENTS:
            raise HttpError(404, f"No model provider named {provider!r}.",
                            f"one of: {', '.join(sorted(ai.CLIENTS))}, apple, "
                            f"or see GET /api/intel/models")
        brief = self.brief()
        shape = narration_shape(brief)
        floor = _env_int("FANTASYEDGE_AI_MIN_INTERVAL", NARRATION_MIN_INTERVAL)
        ttl = _env_int("FANTASYEDGE_AI_TTL", NARRATION_TTL)
        now = time.time()

        with self._lock:
            entry = self._narrations.get(shape)
            fresh = entry and now - entry["created"] <= ttl
            recent = max(self._narrations.values(),
                         key=lambda e: e["created"], default=None)
            waited = now - self._last_call

        # Text produced on somebody else's device costs this process nothing,
        # so it skips both the cache and the floor: an Apple Intelligence run
        # that already happened must not be thrown away to save a call that
        # was never going to be made.
        if provider == "apple" or supplied:
            client = ai.SuppliedClient(supplied)
            return self._store(ai.narrate(brief, client), brief, shape,
                               paid=False)

        if fresh and not body.get("refresh"):
            return self._served(entry, brief, cached=True)

        if self._last_call and waited < floor:
            # The brief moved, or a refresh was asked for, but not enough time
            # has passed to pay for it again.
            left = int(floor - waited)
            if recent and now - recent["created"] <= ttl:
                # Serving the last paragraph beats both an error and a charge:
                # it is still about these findings, and `factsChanged` tells
                # the reader it has drifted.
                out = self._served(recent, brief, cached=True)
                out["throttled"] = left
                out["note"] = (f"A new narration is available in {left}s. "
                               f"This one was written {out['ageSeconds']}s ago.")
                return out
            # Nothing to serve, and the clock still says no. This is the path a
            # failing provider takes: the call is what sets `_last_call`, and
            # a failure stores no prose, so without this a client retrying a
            # 500 in a loop would hit the provider every time and the floor
            # would never engage at all.
            n = ai.Narration("", provider, "", [i.key for i in brief.insights],
                             error=ai.ModelError(
                                 "throttled",
                                 f"The last request was {int(waited)}s ago.",
                                 f"Try again in {left}s. Everything below was "
                                 f"computed without a model and has not "
                                 f"changed.").as_dict())
            return dict(n.as_dict(), cached=False, ageSeconds=0,
                        briefShape=shape, factsChanged=False,
                        throttled=left, calls=self._calls)

        try:
            client = ai.client_for(provider)
        except ai.ModelError as exc:
            n = ai.Narration("", provider, "", [i.key for i in brief.insights],
                             error=exc.as_dict())
            return dict(n.as_dict(), cached=False, ageSeconds=0,
                        briefShape=shape, factsChanged=False)
        with self._lock:
            self._last_call = time.time()
        result = ai.narrate(brief, client)
        del client                      # the key goes out of scope with it
        return self._store(result, brief, shape, paid=True)

    def _store(self, narration, brief, shape: str, paid: bool) -> dict:
        """Keep prose worth reusing; count what it cost."""
        out = narration.as_dict()
        out.update({"cached": False, "ageSeconds": 0, "briefShape": shape,
                    "factsChanged": False, "createdAt": time.time()})
        if paid:
            with self._lock:
                self._calls += 1
        if narration.text and not narration.error:
            with self._lock:
                self._narrations[shape] = {
                    "text": narration.text, "provider": narration.provider,
                    "model": narration.model, "shape": shape,
                    "created": out["createdAt"]}
                # One shape per week is the realistic count; the cap is only
                # here so a long live Sunday cannot grow this without bound.
                if len(self._narrations) > 32:
                    oldest = min(self._narrations,
                                 key=lambda k: self._narrations[k]["created"])
                    del self._narrations[oldest]
        with self._lock:
            out["calls"] = self._calls
        return out

    # ---------- routing ----------

    def dispatch(self, path: str, qs: dict):
        """Route, and say how the answer may be cached.

        Policy is decided here rather than in each endpoint so that one table
        governs the whole surface: a client, a proxy and a CDN all read the
        same rules, and a new route cannot quietly ship without one.
        """
        parts = [unquote(p) for p in path.strip("/").split("/") if p]
        if not parts or parts[0] != "api":
            raise HttpError(404, f"No route {path}.", "GET /api lists every route")
        rest = parts[1:]
        if not rest:
            return self.index(), CONFIG
        if rest == ["health"]:
            return self.health(), PRIVATE
        if rest == ["live"]:
            return self.live(), LIVE
        if rest == ["redzone"]:
            # Shared bytes on the live clock, like /api/live: the ranking is a
            # fact about the slate, so every viewer may be handed the same one.
            return self.redzone(), LIVE
        if rest == ["headlines"]:
            return self.headlines(), DERIVED
        if rest == ["injuries"]:
            return self.injuries(), DERIVED
        if rest == ["players"]:
            return self.players(), CONFIG
        if rest == ["universe"]:
            return self.universe(qs), DERIVED
        if len(rest) == 2 and rest[0] == "gamecast":
            return self.gamecast(rest[1]), LIVE
        if len(rest) == 2 and rest[0] == "scene":
            return self.scene(rest[1]), LIVE
        if rest == ["lastweek"]:
            # A finished week never changes, but which week is last does,
            # and a pull swaps a row's reasons from quarter to play
            # resolution - so this is derived, not immutable.
            return self.last_week(qs), DERIVED
        if rest == ["replay"]:
            return self.replay_state(), REPLAY
        if rest == ["replay", "markers"]:
            return self.replay_markers(), REPLAY
        if rest == ["replay", "live"]:
            return self.replay_live(), REPLAY
        if rest == ["replay", "gamecast"]:
            return self.replay_gamecast(), REPLAY
        if rest == ["replay", "scene"]:
            return self.replay_scene(), REPLAY
        if len(rest) == 2 and rest[0] == "player":
            return self.profile(rest[1]), DERIVED
        if rest == ["context"]:
            return self.context(), LIVE
        if rest == ["rankings"]:
            return self.rankings(), DERIVED
        if rest == ["projections", "sources"]:
            # The catalogue moves only when someone runs a loader, so it is
            # config-shaped rather than derived - a client may hold it for the
            # length of a session without ever showing a stale picker.
            return self.projection_sources(qs), CONFIG
        if rest == ["projections"]:
            # A projection is derived: it is recomputed from stored rows, never
            # polled from a provider, so it belongs on the DERIVED clock beside
            # the analyses rather than on LIVE beside the scoreboard.
            return self.projections(qs), DERIVED
        if rest == ["prefs"]:
            return self.prefs(), PRIVATE
        if rest == ["intel", "models"]:
            return self.intel_models(), CONFIG
        if rest == ["intel"]:
            # CONFIG, not LIVE, and the distinction is the whole cost model.
            # This brief is built from `mosaics()`, which honours prefs.json,
            # so it is a different payload per person by construction. The live
            # tier's short max-age only works because every viewer gets
            # identical bytes there (see live.py); putting a personal payload
            # on it would hand one reader another reader's board out of a
            # shared cache.
            return self.intel_brief(), CONFIG
        if rest == ["leagues"]:
            return self.leagues(), CONFIG
        if rest == ["mosaic"]:
            return self.mosaics(), CONFIG
        if len(rest) == 3 and rest[0] == "mosaic":
            return self.mosaic(rest[1], rest[2], qs), CONFIG
        if rest and rest[0] == "leagues":
            if len(rest) < 3:
                raise HttpError(404, f"No route {path}.",
                                "GET /api/leagues/{provider}/{league_id}")
            provider, league, tail = rest[1], rest[2], rest[3:]
            if not tail:
                return self.league(provider, league), CONFIG
            if tail == ["analyses"]:
                raw = (qs.get("keys") or [""])[0]
                keys = [k for k in raw.split(",") if k] or None
                return self.analyses(provider, league, keys), DERIVED
            if len(tail) == 2 and tail[0] == "analyses":
                return self.analyses(provider, league, [tail[1]]), DERIVED
            if tail == ["managers"]:
                return self.managers(provider, league), DERIVED
            if tail in (["standings"], ["draft"]):
                fn = self.standings if tail == ["standings"] else self.draft
                out = fn(provider, league, qs)
                # A finished season can never change again, so it is worth a
                # year in every cache between here and the screen.
                latest = self._seasons(provider, league)[0]
                return out, (IMMUTABLE if out["season"] < latest else CONFIG)
        raise HttpError(404, f"No route {path}.", "GET /api lists every route")


def make_handler(app: Api):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "fantasy-edge"

        def _headers(self, body: bytes, code: int, etag: str = "",
                     policy: str = PRIVATE, ctype: str = "application/json") -> None:
            self.send_response(code)
            self.send_header("Content-Type", f"{ctype}; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            # Read-only, no credentials, no cookies: any origin may read it,
            # which is what lets a web client live somewhere other than here.
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, HEAD, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Cache-Control", policy)
            if etag:
                self.send_header("ETag", etag)
            self.end_headers()

        def _send(self, payload, code: int = 200, policy: str = PRIVATE) -> None:
            body = json.dumps(payload, separators=(",", ":"), default=str).encode()
            etag = '"%s"' % hashlib.sha1(body).hexdigest()[:16]
            # Content-addressed, so a poll that changed nothing costs a header
            # exchange rather than a payload. At a few seconds per tick across
            # millions of screens, that difference is the bandwidth bill.
            if self.headers.get("If-None-Match") == etag and code == 200:
                self.send_response(304)
                self.send_header("ETag", etag)
                self.send_header("Cache-Control", policy)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            self._headers(body, code, etag, policy)
            if self.command != "HEAD":
                self.wfile.write(body)

        def _stream(self, qs) -> None:
            """Server-sent events, delta encoded.

            SSE rather than WebSocket on purpose: this feed is one-way, and a
            unidirectional stream survives proxies, reconnects by itself, and
            costs far less to hold open. Every viewer receives byte-identical
            events, so the stream fans out at the edge from a single origin
            subscription instead of one per user.

            After the first frame only changed players are sent. Mid-afternoon
            that is a handful of entries rather than the whole table.
            """
            try:
                interval = max(1.0, float((qs.get("interval") or ["3"])[0]))
            except ValueError:
                interval = 3.0
            try:
                limit = float((qs.get("seconds") or ["900"])[0])
            except ValueError:
                limit = 900.0

            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Connection", "close")
            self.end_headers()

            src = app.live_source()
            started, prev = time.time(), {}
            try:
                while time.time() - started < limit:
                    snap = src.snapshot()
                    players = snap["players"]
                    if not prev:
                        frame, kind = snap, "full"
                    else:
                        changed = {k: v for k, v in players.items() if prev.get(k) != v}
                        frame = {"asOf": snap["asOf"], "window": snap["window"],
                                 "version": snap["version"], "players": changed}
                        kind = "delta"
                    prev = players
                    body = json.dumps(frame, separators=(",", ":"))
                    self.wfile.write(f"event: {kind}\ndata: {body}\n\n".encode())
                    self.wfile.flush()
                    time.sleep(interval)
            except (BrokenPipeError, ConnectionResetError):
                pass                      # the viewer closed the tab; not an error

        def _handle(self) -> None:
            raw = self.path.split("?", 1)
            path = raw[0]
            qs = parse_qs(raw[1]) if len(raw) > 1 else {}
            try:
                if path in ("/", "/index.html", "/mosaic"):
                    body = app.mosaic_page()
                    self._headers(body, 200, "", PRIVATE, "text/html")
                    if self.command != "HEAD":
                        self.wfile.write(body)
                    return
                if path in ("/redzone", "/redzone.html"):
                    # Static: the page holds no data, it fetches /api/redzone.
                    # That keeps it servable to a television or a phone on the
                    # LAN without this process rendering anything per viewer.
                    body = app.redzone_page()
                    self._headers(body, 200, "", CONFIG, "text/html")
                    if self.command != "HEAD":
                        self.wfile.write(body)
                    return
                if path == "/api/live/stream":
                    return self._stream(qs)
                payload, policy = app.dispatch(path, qs)
                self._send(payload, 200, policy)
            except HttpError as exc:
                self._send({"error": exc.message, "fix": exc.fix}, exc.code)
            except Exception as exc:                 # a client never sees a traceback
                self._send({"error": str(exc), "fix": "check the server log"}, 500)

        def _loopback(self) -> bool:
            return (self.client_address or ["?"])[0] in (
                "127.0.0.1", "::1", "localhost")

        def _body(self, limit: int) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            if n > limit:
                raise ValueError(f"payload over {limit} bytes")
            patch = json.loads(self.rfile.read(n) or b"{}")
            if not isinstance(patch, dict):
                raise ValueError("expected an object")
            return patch

        def do_POST(self):
            """The two writes in this process, and the only ones there should be.

            Everything else here is read-only on purpose, which is what makes
            it safe to bind to the LAN. Preferences are the exception because
            the console runs on several screens and they have to agree - but a
            write is still a write, so it is refused from anywhere but this
            machine unless FANTASYEDGE_ALLOW_REMOTE_PREFS is set. No credential
            is ever readable or writable through this endpoint.

            `/api/intel/narrate` carries the same loopback restriction for a
            second reason on top of the first: it is the one route here that
            reads an API key and spends money. Its escape hatch is a separate
            variable from the prefs one, because letting a housemate reorder
            your leagues from the television is not the same decision as
            letting them run up your model bill.
            """
            path = self.path.split("?", 1)[0]
            if path == "/api/prefs":
                if not self._loopback() and \
                        os.environ.get("FANTASYEDGE_ALLOW_REMOTE_PREFS") != "1":
                    return self._send(
                        {"error": "Preferences may only be changed from this machine.",
                         "fix": "set FANTASYEDGE_ALLOW_REMOTE_PREFS=1 to allow it"}, 403)
                try:
                    patch = self._body(64_000)
                except Exception as exc:
                    return self._send({"error": f"Bad JSON: {exc}",
                                       "fix": "send {teams, order, hidden}"}, 400)
                return self._send(app.save_prefs(patch), 200)

            if path == "/api/intel/narrate":
                if not self._loopback() and \
                        os.environ.get("FANTASYEDGE_ALLOW_REMOTE_AI") != "1":
                    return self._send(
                        {"error": "A narration may only be requested from this "
                                  "machine - it reads an API key and costs money.",
                         "fix": "set FANTASYEDGE_ALLOW_REMOTE_AI=1 to allow it. "
                                "The computed brief at GET /api/intel needs no "
                                "key and is already complete."}, 403)
                try:
                    # Bigger than prefs because an Apple Intelligence client
                    # posts finished prose here, and smaller than anything that
                    # could be mistaken for a roster: this endpoint takes a
                    # provider name and a paragraph, nothing else.
                    body = self._body(32_000)
                except Exception as exc:
                    return self._send({"error": f"Bad JSON: {exc}",
                                       "fix": 'send {"provider": "anthropic"} '
                                              'or {"provider": "apple", "text": "..."}'}, 400)
                try:
                    return self._send(app.narrate(body), 200, PRIVATE)
                except HttpError as exc:
                    return self._send({"error": exc.message, "fix": exc.fix},
                                      exc.code)

            if path == "/api/replay":
                # A third write, with the same loopback rule and its own escape
                # hatch. It spends nothing and holds no credential, but it can
                # make this machine fetch from ESPN (`capture`), and it moves
                # what every screen watching the replay sees. A headset on the
                # LAN needs FANTASYEDGE_ALLOW_REMOTE_REPLAY=1, which is a
                # separate decision from letting it edit your prefs.
                if not self._loopback() and \
                        os.environ.get("FANTASYEDGE_ALLOW_REMOTE_REPLAY") != "1":
                    return self._send(
                        {"error": "A replay may only be driven from this machine.",
                         "fix": "set FANTASYEDGE_ALLOW_REMOTE_REPLAY=1 to allow it"}, 403)
                try:
                    body = self._body(4_000)
                except Exception as exc:
                    return self._send({"error": f"Bad JSON: {exc}",
                                       "fix": '{"action": "play"}'}, 400)
                try:
                    return self._send(app.replay_control(body), 200, REPLAY)
                except HttpError as exc:
                    return self._send({"error": exc.message, "fix": exc.fix}, exc.code)

            return self._send({"error": f"No route {path}.",
                               "fix": "POST /api/prefs, /api/intel/narrate or /api/replay"},
                              404)

        do_GET = do_HEAD = _handle

        def do_OPTIONS(self):
            self._headers(b"", 204)

        def log_message(self, *a):                   # quiet by default
            pass
    return Handler


def run(db: str = "data/fantasy.db", host: str = "127.0.0.1", port: int = 8770,
        allow_ai: bool = True) -> None:
    app = Api(db, allow_ai=allow_ai)
    health = app.health()
    httpd = None
    for candidate in range(port, port + 10):         # something else may own the port
        try:
            httpd = ThreadingHTTPServer((host, candidate), make_handler(app))
            port = candidate
            break
        except OSError:
            continue
    if httpd is None:
        raise SystemExit(f"Ports {port}-{port + 9} are all busy. Pass --port with a free one.")

    print(f"\n  fantasy-edge mosaic   ->  http://{host}:{port}/")
    print(f"  read API              ->  http://{host}:{port}/api")
    print(f"  intel brief           ->  http://{host}:{port}/api/intel"
          f"{'' if allow_ai else '   (--no-ai: computed only)'}")
    print(f"  {health['leagues']} league(s), {len(health['seasons'])} season(s), "
          f"{health['counts']['roster_slot']} roster rows")
    if not health["ok"]:
        print("  database is empty - run `pull` first; every route will 404 until then")
    if host not in ("127.0.0.1", "localhost", "::1"):
        print(f"  bound to {host}: any device on this network can read your league "
              f"history.\n  No credentials are served - this process holds none.")
    print("  Ctrl-C to stop.\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  Stopped.")
    finally:
        httpd.server_close()
        app.close()
