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

from . import analytics
from .store import Store

MOSAIC = pathlib.Path(__file__).parent / "templates" / "mosaic.html"

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
    ["GET", "/api/headlines", "NFL news, tagged with the players you roster"],
    ["GET", "/api/players", "every player you roster, across every league"],
    ["GET", "/api/prefs", "your team in each league, their order, and what is hidden"],
    ["POST", "/api/prefs", "update those - loopback only, see the handler"],
]

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

    def __init__(self, db: str = "data/fantasy.db"):
        self.db = db
        self._local = threading.local()
        self._lock = threading.Lock()
        self._cache: dict[tuple, tuple[float, object]] = {}
        self._stores: list[Store] = []

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
            """SELECT s.rank, s.team_id, m.name AS team, m.owner,
                      s.wins, s.losses, s.ties, s.points_for, s.points_against
               FROM standing s
               LEFT JOIN manager m ON m.provider=s.provider AND m.league_id=s.league_id
                                  AND m.season=s.season AND m.team_id=s.team_id
               WHERE s.provider=? AND s.league_id=? AND s.season=?
               ORDER BY s.rank""",
            (provider, str(league), season))
        return {"provider": provider, "league_id": str(league), "season": season,
                "standings": [dict(r) for r in rows]}

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

            store = self.store()
            rows = store.q(
                """SELECT DISTINCT r.player_id, p.name, p.pos, p.nfl_team,
                          MAX(COALESCE(r.projected, r.points, 0)) AS proj
                   FROM roster_slot r
                   LEFT JOIN player p ON p.provider=r.provider
                                     AND p.player_id=r.player_id
                   WHERE p.name IS NOT NULL
                   GROUP BY r.player_id""")
            players = [{"player_id": r["player_id"], "name": r["name"],
                        "pos": r["pos"] or "", "team": livemod.team_abbr(r["nfl_team"]),
                        "projected": r["proj"] or 0.0} for r in rows]
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
                # The league's own scoring, so a half-PPR board is not told it
                # is winning by a point it does not actually score.
                from .cli import load_config
                from .scoring import Scoring
                try:
                    rules = Scoring.from_config(load_config())
                except Exception:
                    rules = Scoring()
                src = livemod.EspnLiveSource(players, scoring=rules)
            with self._lock:
                self._live = src
        return src

    def live(self) -> dict:
        return self.live_source().snapshot()

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
            for key, fn in (("players", self.players), ("headlines", self.headlines)):
                try:
                    data[key] = fn()
                except Exception:
                    data[key] = None
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

        names = {m["team_id"]: m["name"] for m in store.q(
            "SELECT team_id, name FROM manager WHERE provider=? AND league_id=? "
            "AND season=?", (provider, str(league), season))}

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
                "teams": [{"teamId": t, "name": n} for t, n in sorted(names.items())],
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

        out = []
        for c in self.leagues()["leagues"]:
            try:
                m = self.mosaic(c["provider"], c["league_id"], {})
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
                "accuracy": accuracy,
            })
        if not out:
            raise HttpError(404, "No league has both rosters and a matchup stored.",
                            "pull a season with rosters, then retry")
        return {"leagues": out}

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
            flat = []
            for name, items in news.items():
                for it in items:
                    flat.append({"player": name, "headline": it["h"],
                                 "detail": it["d"][:200], "published": it["p"],
                                 "url": it["u"]})
            flat.sort(key=lambda x: x["published"], reverse=True)
            return {"stories": flat[:60], "asOf": as_of, "count": count}

        return self.cached(("headlines",), build)

    def prefs(self) -> dict:
        from . import prefs as pf
        return pf.load()

    def save_prefs(self, patch: dict) -> dict:
        from . import prefs as pf
        return pf.save(pf.merge(pf.load(), patch))

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
        if rest == ["headlines"]:
            return self.headlines(), DERIVED
        if rest == ["players"]:
            return self.players(), CONFIG
        if rest == ["prefs"]:
            return self.prefs(), PRIVATE
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
                if path == "/api/live/stream":
                    return self._stream(qs)
                payload, policy = app.dispatch(path, qs)
                self._send(payload, 200, policy)
            except HttpError as exc:
                self._send({"error": exc.message, "fix": exc.fix}, exc.code)
            except Exception as exc:                 # a client never sees a traceback
                self._send({"error": str(exc), "fix": "check the server log"}, 500)

        def do_POST(self):
            """The only write in this process, and the only one there should be.

            Everything else here is read-only on purpose, which is what makes
            it safe to bind to the LAN. Preferences are the exception because
            the console runs on several screens and they have to agree - but a
            write is still a write, so it is refused from anywhere but this
            machine unless FANTASYEDGE_ALLOW_REMOTE_PREFS is set. No credential
            is ever readable or writable through this endpoint.
            """
            path = self.path.split("?", 1)[0]
            if path != "/api/prefs":
                return self._send({"error": f"No route {path}.",
                                   "fix": "POST /api/prefs is the only write"}, 404)
            host = (self.client_address or ["?"])[0]
            if host not in ("127.0.0.1", "::1", "localhost") and \
                    os.environ.get("FANTASYEDGE_ALLOW_REMOTE_PREFS") != "1":
                return self._send(
                    {"error": "Preferences may only be changed from this machine.",
                     "fix": "set FANTASYEDGE_ALLOW_REMOTE_PREFS=1 to allow it"}, 403)
            try:
                n = int(self.headers.get("Content-Length") or 0)
                if n > 64_000:
                    return self._send({"error": "Payload too large.",
                                       "fix": "prefs are small"}, 413)
                patch = json.loads(self.rfile.read(n) or b"{}")
                if not isinstance(patch, dict):
                    raise ValueError("expected an object")
            except Exception as exc:
                return self._send({"error": f"Bad JSON: {exc}",
                                   "fix": "send {teams, order, hidden}"}, 400)
            self._send(app.save_prefs(patch), 200)

        do_GET = do_HEAD = _handle

        def do_OPTIONS(self):
            self._headers(b"", 204)

        def log_message(self, *a):                   # quiet by default
            pass
    return Handler


def run(db: str = "data/fantasy.db", host: str = "127.0.0.1", port: int = 8770) -> None:
    app = Api(db)
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
