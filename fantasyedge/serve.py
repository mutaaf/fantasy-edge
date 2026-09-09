"""Local draft board with real auto-sync.

A published web page cannot poll ESPN: it is sandboxed to an allowlist and has
no way to carry your session cookie. A process on your own machine has both, so
this serves the board from localhost and does the polling itself. The cookie
stays in this process and is never sent to the browser.

    python3 -m fantasyedge serve --league 289515778

Binds to 127.0.0.1 only. Stdlib only, like everything else here.
"""

from __future__ import annotations

import csv
import json
import pathlib
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TEMPLATE = pathlib.Path(__file__).parent / "templates" / "board.html"
NEWS_URL = ("https://now.core.api.espn.com/v1/sports/news"
            "?limit=100&offset={off}&sport=football&league=nfl")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/140.0"

SLOT_NAME = {0: "QB", 2: "RB", 4: "WR", 6: "TE", 16: "DEF", 17: "K", 23: "FLEX"}
DEFAULT_SLOTS = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "DEF", "K"]


def _get_json(url: str, timeout: int = 20):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


# ─────────────────────────────── payload ────────────────────────────────

def load_adp(path: str) -> list[list]:
    rows = []
    with open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r.get("pos") in ("QB", "RB", "WR", "TE", "K", "DEF"):
                rows.append([r["name"], r["pos"], round(float(r["rank"]), 1),
                             int(r["player_id"])])
    rows.sort(key=lambda x: x[2])
    return rows


def fetch_news(names: list[str], pages: int = 3) -> tuple[dict, str, int]:
    """Recent NFL stories, attached to players they actually name.

    Unauthenticated and best-effort: a draft is not worth failing over a news
    feed, so any error yields no news rather than an exception.
    """
    arts, seen = [], set()
    for off in range(0, pages * 100, 100):
        try:
            batch = _get_json(NEWS_URL.format(off=off)).get("headlines", [])
        except Exception:
            break
        for a in batch:
            hd = (a.get("headline") or "").strip()
            if not hd or hd in seen:
                continue
            seen.add(hd)
            link = ""
            try:
                link = ((a.get("links") or {}).get("web") or {}).get("href", "") or ""
            except Exception:
                pass
            arts.append({"h": hd, "d": (a.get("description") or "")[:240],
                         "p": (a.get("published") or "")[:10], "u": link.split("?")[0],
                         "k": " ".join(k for k in (a.get("keywords") or [])
                                       if isinstance(k, str)).lower()})
    arts.sort(key=lambda x: x["p"], reverse=True)
    news = {}
    for n in names[:220]:
        low = n.lower()
        hits = [a for a in arts if low in (a["h"] + " " + a["d"] + " " + a["k"]).lower()][:3]
        if hits:
            news[n] = [{"h": a["h"], "d": a["d"], "p": a["p"], "u": a["u"]} for a in hits]
    return news, (arts[0]["p"] if arts else ""), len(arts)


def league_config(provider, league: str, season: int) -> dict:
    """League shape, draft order and your own team, read live from ESPN."""
    data = provider._get(league, season, ["mSettings", "mTeam", "mDraftDetail"])
    s = data.get("settings", {}) or {}
    counts = (s.get("rosterSettings") or {}).get("lineupSlotCounts") or {}
    slots, bench = [], 0
    for k, v in counts.items():
        if not v:
            continue
        name = SLOT_NAME.get(int(k))
        if name:
            slots.extend([name] * int(v))
        elif int(k) == 20:
            bench = int(v)

    def team_name(t):
        return (t.get("name") or " ".join(
            filter(None, [t.get("location"), t.get("nickname")])).strip()
            or f"Team {t.get('id')}")

    swid = (provider.swid or "").upper().strip("{}")
    me = next((t for t in data.get("teams", []) or []
               if any((o or "").upper().strip("{}") == swid for o in (t.get("owners") or []))),
              None)
    picks = [p for p in (data.get("draftDetail") or {}).get("picks", []) or []
             if p.get("overallPickNumber")]
    slot_of = {p["teamId"]: p["roundPickNumber"]
               for p in sorted((p for p in picks if p.get("roundId") == 1),
                               key=lambda p: p.get("roundPickNumber") or 0)}
    teams = data.get("teams", []) or []
    size = int(s.get("size") or len(teams) or 10)
    order = [str(t["id"]) for t in sorted(teams, key=lambda t: slot_of.get(t["id"], 99))]
    return {
        "id": "live", "leagueId": str(league), "name": s.get("name") or f"League {league}",
        "teams": size, "rounds": (len(picks) // size) or 16, "bench": bench or 6,
        "slots": slots or DEFAULT_SLOTS,
        "slot": (slot_of.get(me["id"]) if me else None) or 1,
        "myTid": str(me["id"]) if me else "",
        "scoring": "Full PPR" if ((s.get("scoringSettings") or {}).get("scoringItems") and any(
            i.get("statId") == 53 and i.get("points") == 1
            for i in s["scoringSettings"]["scoringItems"])) else "",
        "drafted": bool((data.get("draftDetail") or {}).get("drafted")),
        "order": order,
        "mgrs": [[(f"You ({team_name(t)})" if me and t["id"] == me["id"] else team_name(t)),
                  slot_of.get(t["id"], 0), None, None,
                  ("you" if me and t["id"] == me["id"] else ""),
                  "Live league read. Draft-value history is not computed here — "
                  "run `analyze` for that."]
                 for t in sorted(teams, key=lambda t: slot_of.get(t["id"], 99))],
    }


# ─────────────────────────────── the server ─────────────────────────────

class DraftServer:
    def __init__(self, provider, league: str, season: int, adp_csv: str,
                 poll: int = 30, skip_news: bool = False, manual: str | None = None,
                 db: str = "data/fantasy.db"):
        self.provider, self.league, self.season = provider, str(league), season
        self.db = db
        self.poll = max(poll, 5)
        self.adp_csv = adp_csv
        self.players = load_adp(adp_csv)
        self.cfg = league_config(provider, self.league, season)
        try:
            from . import advanced
            with open(adp_csv, newline="", encoding="utf-8") as fh:
                self.adv = advanced.build(list(csv.DictReader(fh)))
        except Exception:
            self.adv = {}          # a stats outage must not stop a draft
        if skip_news:
            self.news, self.as_of, self.n_art = {}, "", 0
        else:
            self.news, self.as_of, self.n_art = fetch_news([p[0] for p in self.players])
        self._lock = threading.Lock()
        self._cache, self._at = None, 0.0
        # ESPN publishes nothing over REST while a draft is actually running -
        # picks appear only once it completes. This file is the stand-in: one
        # player name per line, in pick order, re-read on every poll.
        self.manual = pathlib.Path(manual) if manual else None
        self._by_name = {p[0].lower(): p for p in self.players}

    def _manual_picks(self) -> list:
        """Names typed into the manual file, resolved and attributed by snake order."""
        if not self.manual or not self.manual.exists():
            return []
        order = self.cfg.get("order") or []
        n = self.cfg["teams"]
        rows, unresolved = [], []
        for i, line in enumerate(
                [l.strip() for l in self.manual.read_text().splitlines() if l.strip()]):
            if line.startswith("#"):
                continue
            hit = self._by_name.get(line.lower())
            if not hit:                        # forgiving on partial names
                cand = [p for k, p in self._by_name.items() if line.lower() in k]
                hit = cand[0] if len(cand) == 1 else None
            if not hit:
                unresolved.append(line)
                continue
            overall = len(rows) + 1
            rnd, idx = (overall - 1) // n, (overall - 1) % n
            seat = idx if rnd % 2 == 0 else n - 1 - idx
            rows.append([overall, order[seat] if seat < len(order) else "", str(hit[3])])
        if unresolved:
            print(f"  manual feed: could not resolve {unresolved}", flush=True)
        return rows

    def picks(self) -> dict:
        """Current board, cached briefly so a fast poll cannot hammer ESPN."""
        with self._lock:
            if self._cache and time.time() - self._at < max(self.poll / 3, 5):
                return self._cache
        state = self.provider.draft_state(self.league, self.season)
        live = [[p["overall"], p["team_id"], p["player_id"]] for p in state["picks"]]
        # The API wins the moment it has anything; the manual feed only stands in
        # for the window where ESPN reports an in-progress draft as empty.
        picks = live or self._manual_picks()
        out = {"leagueId": self.league, "drafted": state["drafted"], "picks": picks,
               "source": "espn" if live else ("manual" if picks else "none")}
        with self._lock:
            self._cache, self._at = out, time.time()
        return out

    def stored(self) -> tuple[list, dict, dict]:
        """Every followed league, drawn from the local database.

        No provider call: a league already pulled should render with the
        network unplugged, and nothing should ever need re-adding by hand.
        """
        from . import leagues as lg
        from .analytics import manager_dossier
        from .store import Store

        entries = lg.load()
        if not entries:
            return [self.cfg], {}, {}
        store = Store(self.db)
        cfgs, doss, logs = [], {}, {}
        try:
            for e in entries:
                lid, also = e["league_id"], tuple(e.get("also", []))
                season = lg.latest_season(store, e["provider"], lid)
                if not season:
                    continue
                cfg = lg.config_from_db(store, e["provider"], lid, season,
                                        also, e.get("label", ""))
                if not cfg:
                    continue
                if str(lid) == self.league:
                    cfg["scoring"] = self.cfg.get("scoring", "")
                d = {n: m for n, m in
                     manager_dossier(store, e["provider"], lid, also).items()
                     if m.get("active")}
                for n, m in d.items():
                    m["you"] = (n == cfg.get("myTeam"))
                cfg["mgrs"] = [
                    [n, i + 1, m["early"], m["late"],
                     "you" if m["you"] else ("danger" if m["allplay"] >= .545
                                             else ("soft" if m["allplay"] <= .46 else "")),
                     f"{m['record']} on a {m['allplay']} all-play, "
                     f"{m['luck']:+} points of luck over {m['seasons']} seasons."]
                    for i, (n, m) in enumerate(
                        sorted(d.items(), key=lambda x: -x[1]["allplay"]))]
                cfgs.append(cfg)
                doss[cfg["id"]] = d
                logs[cfg["id"]] = lg.draft_log(store, e["provider"], lid, season)
        finally:
            store.close()
        # the league this process can poll live goes first
        cfgs.sort(key=lambda c: c["leagueId"] != self.league)
        return (cfgs or [self.cfg]), doss, logs

    def value_maps(self, cfgs: list[dict]) -> tuple[dict, dict]:
        """Replacement level moves with league size, so price each one separately."""
        from . import value
        vor, repl = {}, {}
        try:
            with open(self.adp_csv, newline="", encoding="utf-8") as fh:
                rows = list(csv.DictReader(fh))
        except OSError:
            return {}, {}
        for c in cfgs:
            try:
                v, r = value.build(rows, c["teams"], c.get("slots") or [])
                vor[c["id"]], repl[c["id"]] = v, r
            except Exception:
                continue        # a missing curve must not stop the board
        return vor, repl

    def html(self) -> bytes:
        cfgs, doss, logs = self.stored()
        vor, repl = self.value_maps(cfgs)
        payload = {"players": self.players, "news": self.news, "adv": self.adv,
                   "vorByLeague": vor, "replByLeague": repl,
                   "leagues": cfgs, "dossiers": doss, "draftLog": logs,
                   "liveLeague": self.league,
                   "newsAsOf": self.as_of, "articleCount": self.n_art,
                   "live": True, "pollSeconds": self.poll}
        page = TEMPLATE.read_text(encoding="utf-8").replace(
            "__DATA__", json.dumps(payload, separators=(",", ":")))
        return ("<!doctype html><html><head><meta charset=utf-8>"
                "<meta name=viewport content='width=device-width,initial-scale=1'>"
                "</head><body>" + page + "</body></html>").encode("utf-8")


def make_handler(app: DraftServer):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _send(self, body: bytes, ctype: str, code: int = 200):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = self.path.split("?")[0]
            try:
                if path in ("/", "/index.html"):
                    return self._send(app.html(), "text/html; charset=utf-8")
                if path == "/api/picks":
                    want = ""
                    if "?" in self.path:
                        from urllib.parse import parse_qs
                        want = (parse_qs(self.path.split("?", 1)[1]).get("league") or [""])[0]
                    if want and want != app.league:
                        # Another league is on screen; this process holds no
                        # live feed for it, so say so rather than answer wrong.
                        return self._send(json.dumps(
                            {"leagueId": want, "picks": [], "drafted": False,
                             "source": "not-live"}).encode(), "application/json")
                    return self._send(json.dumps(app.picks()).encode(), "application/json")
                self._send(b"not found", "text/plain", 404)
            except Exception as exc:                       # never kill the draft
                self._send(json.dumps({"error": str(exc)}).encode(),
                           "application/json", 502)

        def log_message(self, *a):                          # quiet by default
            pass
    return Handler


def run(provider, league: str, season: int, adp_csv: str,
        port: int = 8765, poll: int = 30, skip_news: bool = False,
        manual: str | None = None, db: str = "data/fantasy.db") -> None:
    app = DraftServer(provider, league, season, adp_csv, poll, skip_news, manual, db)
    handler = make_handler(app)
    httpd = None
    for candidate in range(port, port + 10):          # something else may own the port
        try:
            httpd = ThreadingHTTPServer(("127.0.0.1", candidate), handler)
            port = candidate
            break
        except OSError:
            continue
    if httpd is None:
        raise SystemExit(f"Ports {port}-{port + 9} are all busy. Pass --port with a free one.")
    cfgs, _, _ = app.stored()
    print(f"\n  {len(cfgs)} league(s) loaded from the database:")
    for c in cfgs:
        live = "  <- live feed" if c["leagueId"] == app.league else ""
        print(f"    {c['name'][:34]:<35} {c['teams']}t {c['rounds']}r"
              f"{'  slot ' + str(c['slot']) if c.get('myTid') else ''}{live}")
    cfg = app.cfg
    print(f"\n  {cfg['name']} — {cfg['teams']} teams, {cfg['rounds']} rounds"
          f"{', you are slot ' + str(cfg['slot']) if cfg['myTid'] else ''}")
    print(f"  {len(app.players)} players, {len(app.adv)} with 2025 usage, "
          f"{len(app.news)} with recent news"
          f"{f' (to {app.as_of})' if app.as_of else ''}")
    print(f"\n  Open  ->  http://127.0.0.1:{port}")
    print(f"  Auto-syncing every {app.poll}s. Ctrl-C to stop.\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  Stopped.")
    finally:
        httpd.server_close()
