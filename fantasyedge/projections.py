"""Projections from more than one place, so they can be scored against reality.

Every network publishes a number before kickoff and nobody publishes how those
numbers did afterwards. The database already holds what actually happened, so
the only missing half is the predictions - and once several sources sit in one
table keyed the same way, "who was right" stops being an opinion.

Three ways in:

  * `seed_espn` lifts what is already there. ESPN's projection rides along on
    every roster row we pull, so that source needs no extra fetch at all.
  * `load_sleeper` calls Sleeper's public projections endpoint. No key, no
    cookie, no account - the only other source this install can obtain
    lawfully and for nothing.
  * `load_csv` takes anyone else. The contract is deliberately small because
    every site exports something different, and hand-normalising once beats
    writing a scraper that breaks in September.

    player,pos,points[,team]
    Ja'Marr Chase,WR,18.4,CIN

Names are matched the way the ADP join already does - by `identity`, which is
the same three-stage resolver the live box score uses - because player ids are
not shared across networks and never will be.

There is deliberately no scraper here. CBS and FantasyPros each sell an API
key, and Yahoo's Fantasy Sports API is still in their review queue. Scraping
those pages instead would breach their terms and would lie quietly in October,
which is worse than an honest CSV - so `SOURCES` names all three as pending
and no surface is permitted to draw a number for them. See `catalog`.
"""

from __future__ import annotations

import csv
import json
import pathlib
import re
import time
import unicodedata

from . import identity

#: Kept as a name because callers and tests use it; the implementation moved
#: to `identity`, which is now the single owner of this folding. Two copies of
#: it and a test asserting they agree was a worse arrangement than one copy.
norm_name = identity.fold


def seed_espn(store, season: int | None = None) -> dict:
    """Record ESPN's projection as a first-class source.

    It is already on every roster row; copying it into `projection` is what
    lets it be compared against anyone else on equal terms.
    """
    where, args = "provider='espn' AND projected IS NOT NULL AND projected > 0", ()
    if season:
        where += " AND season=?"
        args = (season,)
    rows = store.q(
        f"""SELECT season, week, player_id, MAX(projected) AS pts
            FROM roster_slot WHERE {where}
            GROUP BY season, week, player_id""", args)
    with store.tx() as c:
        c.executemany(
            "INSERT OR REPLACE INTO projection VALUES (?,?,?,?,?,?)",
            [(r["season"], r["week"], "espn", "espn", r["player_id"], r["pts"])
             for r in rows])
    return {"source": "espn", "rows": len(rows)}


def load_csv(store, path: str, source: str, season: int, week: int,
             provider: str = "espn") -> dict:
    """Load one source's numbers for one week, joined on name plus position.

    Reports what it could not match rather than dropping it silently - an
    unmatched star is the difference between a real answer and a flattering
    one.
    """
    known = {}
    for r in store.q("SELECT player_id, name, pos FROM player WHERE provider=?",
                     (provider,)):
        known[(norm_name(r["name"]), (r["pos"] or "").upper())] = r["player_id"]

    matched, missed = [], []
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            name = (row.get("player") or row.get("name") or "").strip()
            pos = (row.get("pos") or row.get("position") or "").strip().upper()
            raw = (row.get("points") or row.get("proj") or "").strip()
            if not (name and raw):
                continue
            try:
                pts = float(raw)
            except ValueError:
                continue
            pid = known.get((norm_name(name), pos))
            if pid is None:
                missed.append(name)
                continue
            matched.append((season, week, source, provider, pid, pts))

    with store.tx() as c:
        c.executemany("INSERT OR REPLACE INTO projection VALUES (?,?,?,?,?,?)", matched)
    return {"source": source, "season": season, "week": week,
            "rows": len(matched), "unmatched": missed[:20],
            "unmatched_count": len(missed)}


def sources(store) -> list[str]:
    return [r["source"] for r in
            store.q("SELECT DISTINCT source FROM projection ORDER BY source")]


def load_dir(store, directory: str, provider: str = "espn") -> list[dict]:
    """Every `<source>_<season>_w<week>.csv` in a directory, in one call."""
    out = []
    for f in sorted(pathlib.Path(directory).glob("*.csv")):
        m = re.match(r"([a-z0-9]+)_(\d{4})_w(\d{1,2})$", f.stem, re.I)
        if not m:
            continue
        src, season, week = m.group(1).lower(), int(m.group(2)), int(m.group(3))
        out.append(load_csv(store, str(f), src, season, week, provider))
    return out


# ---------------------------------------------------------------------------
# The catalogue
# ---------------------------------------------------------------------------

#: Every source this product names, and the honest status of each.
#:
#: This table exists so that "which sources are there" has exactly one answer,
#: shared by the CLI, the API and every client. The alternative - each surface
#: keeping its own list - is how a picker ends up offering a source that
#: produces nothing, and an empty column reads as "he is projected for zero"
#: rather than as "nobody asked anybody". A source is `live` only when this
#: install can actually obtain its numbers without the user buying anything.
SOURCES = {
    "espn": {
        "label": "ESPN", "status": "live", "needs": "",
        "detail": "Rides along on every roster row already pulled, so it "
                  "costs no extra request.",
        "attribution": "ESPN's own weekly projection",
    },
    "sleeper": {
        "label": "Sleeper", "status": "live", "needs": "",
        "detail": "Sleeper's public projections endpoint. No key, no cookie, "
                  "no account.",
        "attribution": "Rotowire, published through Sleeper",
    },
    "cbs": {
        "label": "CBS", "status": "pending", "needs": "an API key",
        "detail": "CBS publishes projections only behind a developer key this "
                  "install does not have.",
        "attribution": "",
    },
    "fantasypros": {
        "label": "FantasyPros", "status": "pending", "needs": "a paid API key",
        "detail": "The consensus everyone quotes is a paid API. Scraping the "
                  "site instead would breach their terms and break in "
                  "September, so it waits for a key.",
        "attribution": "",
    },
    "yahoo": {
        "label": "Yahoo", "status": "pending",
        "needs": "Yahoo's Fantasy Sports API approval",
        "detail": "The application is in Yahoo's manual review queue. Until it "
                  "clears there is no endpoint to call.",
        "attribution": "",
    },
}

#: What a pending source needs in order to start producing numbers. Every one
#: of them arrives through `load_csv`, which already takes an arbitrary source
#: name - so the architecture is finished even where the licence is not.
PENDING_ROUTE = ("python3 -m fantasyedge projections load --source <name> "
                 "--csv <file> --season <year> --week <n>")


def catalog(store, season: int | None = None, week: int | None = None) -> list[dict]:
    """Every named source with what it has actually got in this database.

    Deliberately lists the pending three as well as the two that work. A
    picker built from only the loaded sources cannot tell a user *why* CBS is
    absent, and "absent without explanation" is the state that gets read as
    "broken".
    """
    where, args = "", []
    if season is not None:
        where, args = " WHERE season=?", [season]
        if week is not None:
            where, args = " WHERE season=? AND week=?", [season, week]
    counts = {r["source"]: (r["n"], r["weeks"]) for r in store.q(
        f"SELECT source, COUNT(*) AS n, COUNT(DISTINCT week) AS weeks "
        f"FROM projection{where} GROUP BY source", tuple(args))}

    out = []
    for key, meta in SOURCES.items():
        rows, weeks = counts.get(key, (0, 0))
        out.append({"source": key, "label": meta["label"],
                    "status": meta["status"], "needs": meta["needs"],
                    "detail": meta["detail"],
                    "attribution": meta["attribution"],
                    "loaded": rows > 0, "rows": rows, "weeks": weeks})
    # Anything loaded from a CSV under a name this table does not know is still
    # real data and must not vanish from the picker just because it is not on
    # the shortlist.
    for key, (rows, weeks) in sorted(counts.items()):
        if key not in SOURCES:
            out.append({"source": key, "label": key.title(), "status": "live",
                        "needs": "", "detail": "Loaded from a CSV.",
                        "attribution": "", "loaded": True,
                        "rows": rows, "weeks": weeks})
    return out


# ---------------------------------------------------------------------------
# Sleeper
# ---------------------------------------------------------------------------

SLEEPER_API = "https://api.sleeper.app/projections/nfl"
SLEEPER_CACHE = pathlib.Path.home() / ".fantasy-edge" / "cache"
SLEEPER_TTL = 6 * 3600
POSITIONS = ("QB", "RB", "WR", "TE", "K", "DEF")

#: Sleeper publishes each row in all three scoring formats at once. Which one
#: is right is a property of the league, not of the fetch, so it is chosen at
#: load time from `config/league.toml` rather than baked in here. Loading the
#: PPR column into a half-PPR league would make Sleeper look wrong by about a
#: point a receiver, which is a slander produced entirely by the reader.
SLEEPER_FORMAT = {"ppr": "pts_ppr", "half_ppr": "pts_half_ppr", "std": "pts_std"}


def scoring_format(cfg: dict | None) -> str:
    """Which of Sleeper's three columns matches this league's reception rule."""
    try:
        rec = float(((cfg or {}).get("scoring") or {}).get("reception", 1.0))
    except (TypeError, ValueError):
        rec = 1.0
    if rec >= 0.75:
        return "ppr"
    return "half_ppr" if rec >= 0.25 else "std"


def sleeper_url(season: int, week: int | None = None,
                positions=POSITIONS, order_by: str = "pts_ppr") -> str:
    """Sleeper wants the positions as repeated `position[]` pairs.

    Built by hand rather than through `Http(params=...)`, which takes a dict
    and would therefore keep only the last position - one call returning
    kickers alone, silently, with no error to notice.
    """
    import urllib.parse
    path = f"{SLEEPER_API}/{int(season)}" + (f"/{int(week)}" if week else "")
    pairs = [("season_type", "regular")]
    pairs += [("position[]", p) for p in positions]
    pairs.append(("order_by", order_by))
    return f"{path}?{urllib.parse.urlencode(pairs)}"


def fetch_sleeper(season: int, week: int | None = None, *, http=None,
                  refresh: bool = False, cache_dir=None) -> list[dict]:
    """One slate of Sleeper projections, cached on disk.

    Two megabytes a week and it moves a few times between Tuesday and Sunday,
    so a file cache with a short life is the whole story. It lives beside the
    player file in `~/.fantasy-edge/`, never in the working tree, and never in
    the API process - `api` calls no provider, by design, so this is reached
    from the CLI and the rows it writes are what the API serves.
    """
    from .providers.base import Http, ProviderError

    cache = pathlib.Path(cache_dir or SLEEPER_CACHE)
    path = cache / f"sleeper_proj_{int(season)}_w{int(week or 0)}.json"
    if not refresh and path.exists() and time.time() - path.stat().st_mtime < SLEEPER_TTL:
        try:
            return json.loads(path.read_text())
        except ValueError:
            pass                      # a truncated cache is not worth failing on

    rows = (http or Http()).get_json(sleeper_url(season, week))
    if not isinstance(rows, list):
        raise ProviderError(f"sleeper projections {season} w{week}: "
                            f"expected a list, got {type(rows).__name__}")
    try:
        cache.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(rows))
    except OSError:
        pass
    return rows


def sleeper_rows(raw: list[dict], fmt: str = "ppr") -> list[dict]:
    """The projected players in a Sleeper payload, flattened.

    Most of the payload is not a projection. Of 3,304 rows in a real week 1,
    2,855 carry only an ADP placeholder and no points at all: they are players
    in the file, not players anybody projected. Keeping them and reading a
    missing `pts_ppr` as 0.0 would put a hard zero next to several thousand
    names, which is a claim nobody made.
    """
    col = SLEEPER_FORMAT.get(fmt, "pts_ppr")
    out = []
    for r in raw:
        stats = r.get("stats") or {}
        pts = stats.get(col)
        if pts is None:
            continue
        p = r.get("player") or {}
        name = (" ".join(x for x in (p.get("first_name"), p.get("last_name")) if x)
                or "").strip()
        pos = (p.get("position") or "").upper()
        club = (r.get("team") or p.get("team") or p.get("team_abbr") or "")
        if pos == "DEF" and not club:
            # A Sleeper defence is filed under the club code as its player id,
            # which is the only place the club survives when `team` is null.
            club = str(r.get("player_id") or "")
        out.append({"name": name, "pos": pos, "team": club,
                    "points": float(pts), "sleeper_id": str(r.get("player_id") or ""),
                    "opponent": r.get("opponent") or "",
                    "company": r.get("company") or ""})
    return out


def load_sleeper(store, season: int, week: int, *, fmt: str = "ppr",
                 provider: str = "espn", http=None, refresh: bool = False,
                 cache_dir=None) -> dict:
    """Sleeper's numbers, joined onto the ids this database already uses.

    The join is `identity.Resolver`, the same three-stage match the live box
    score uses, and it reports which stage each hit came from. That matters
    here more than anywhere: a projection source that silently matched 60% of
    the board would produce a "consensus" that is really ESPN wherever Sleeper
    went missing, and the missing half would be invisible.
    """
    from . import identity

    res = identity.Resolver()
    known = store.q("SELECT player_id, name, pos, nfl_team FROM player WHERE provider=?",
                    (provider,))
    if not known:
        return {"source": "sleeper", "season": season, "week": week, "rows": 0,
                "matched": {}, "unmatched": [], "unmatched_count": 0,
                "note": f"no {provider} players stored yet - run `pull` first"}
    from .live import team_abbr
    for r in known:
        res.add(r["player_id"], r["name"], r["pos"] or "", team_abbr(r["nfl_team"]))

    rows = sleeper_rows(fetch_sleeper(season, week, http=http, refresh=refresh,
                                      cache_dir=cache_dir), fmt)
    how: dict[str, int] = {}
    seen: dict[str, tuple] = {}
    unmatched = []
    for row in rows:
        pid, rule = res.resolve(row["name"], row["pos"], row["team"])
        if pid is None:
            unmatched.append(f'{row["name"]} ({row["pos"]})')
            continue
        # Two Sleeper rows can land on one ESPN id - a player filed at two
        # positions - and the primary key would keep whichever wrote last.
        # Keeping the higher is at least a stated rule rather than a race.
        if pid in seen and seen[pid][0] >= row["points"]:
            continue
        seen[pid] = (row["points"], rule)
        how[rule] = how.get(rule, 0) + 1

    with store.tx() as c:
        c.executemany(
            "INSERT OR REPLACE INTO projection VALUES (?,?,?,?,?,?)",
            [(int(season), int(week), "sleeper", provider, pid, pts)
             for pid, (pts, _) in seen.items()])
    return {"source": "sleeper", "season": int(season), "week": int(week),
            "format": fmt, "rows": len(seen), "offered": len(rows),
            "pool": len(known), "matched": how,
            "unmatched": unmatched[:20], "unmatched_count": len(unmatched)}


# ---------------------------------------------------------------------------
# Reading them back
# ---------------------------------------------------------------------------

def current_week(store, season: int) -> int:
    """The week the boards are on: each league's newest, then the commonest.

    One definition, called by the API and by `daily`, because two of them
    would drift and the console would then be picking a source for one week
    while drawing tiles for another.

    Both halves fix a real reading of a real database. Each league's own
    newest week is the rule `live.roster_players` already uses. Taking the
    commonest of those rather than the flat maximum is what stops a single
    league pulled with fourteen weeks of forward, unplayed roster rows from
    dragging the whole console to week 14 - a week only ESPN has projected,
    where the honest "consensus of 1" is indistinguishable from a broken
    loader. Ties break toward the earlier week: a league carrying
    forward-dated rows is the outlier, not the clock.
    """
    rows = store.q(
        """SELECT week, COUNT(*) AS leagues FROM (
               SELECT provider, league_id, MAX(week) AS week
               FROM roster_slot WHERE season=? GROUP BY provider, league_id)
           GROUP BY week ORDER BY leagues DESC, week ASC LIMIT 1""",
        (int(season),))
    return int((rows[0]["week"] if rows else None) or 0)


def board(store, season: int, week: int, provider: str = "espn",
          player_ids=None) -> dict:
    """Every loaded source's number for each player, side by side.

    The consensus is the mean of *what is actually here*, and `n` travels with
    it everywhere. A mean of one source is that source wearing a different
    hat, and calling it a consensus without saying so is the single most
    misleading thing this endpoint could do - so `n` is not optional, and a
    player only carries a `spread` when at least two sources spoke.
    """
    want = {str(p) for p in player_ids} if player_ids else None
    rows = store.q(
        """SELECT j.player_id AS id, j.source, j.points, p.name, p.pos, p.nfl_team
           FROM projection j
           LEFT JOIN player p ON p.provider=j.provider AND p.player_id=j.player_id
           WHERE j.season=? AND j.week=? AND j.provider=?""",
        (int(season), int(week), provider))

    from .live import team_abbr
    men: dict[str, dict] = {}
    for r in rows:
        pid = str(r["id"])
        if want is not None and pid not in want:
            continue
        m = men.setdefault(pid, {"id": pid, "name": r["name"] or pid,
                                 "pos": (r["pos"] or "").upper(),
                                 "team": team_abbr(r["nfl_team"]), "by": {}})
        m["by"][r["source"]] = round(float(r["points"]), 2)

    loaded = sorted({s for m in men.values() for s in m["by"]})
    for m in men.values():
        vals = [m["by"][s] for s in sorted(m["by"])]
        m["n"] = len(vals)
        m["consensus"] = round(sum(vals) / len(vals), 2) if vals else None
        # Spread is the disagreement, and it is the interesting column. One
        # source cannot disagree with itself, so it is None rather than 0.0 -
        # a printed zero would read as "they agree exactly".
        m["spread"] = round(max(vals) - min(vals), 2) if len(vals) > 1 else None
    out = sorted(men.values(), key=lambda m: -(m["consensus"] or 0))
    return {"season": int(season), "week": int(week), "provider": provider,
            "sources": loaded, "n": len(loaded), "players": out,
            "count": len(out)}
