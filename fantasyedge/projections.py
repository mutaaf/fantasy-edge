"""Projections from more than one place, so they can be scored against reality.

Every network publishes a number before kickoff and nobody publishes how those
numbers did afterwards. The database already holds what actually happened, so
the only missing half is the predictions - and once several sources sit in one
table keyed the same way, "who was right" stops being an opinion.

Two ways in:

  * `seed_espn` lifts what is already there. ESPN's projection rides along on
    every roster row we pull, so that source needs no extra fetch at all.
  * `load_csv` takes anyone else. The contract is deliberately small because
    every site exports something different, and hand-normalising once beats
    writing a scraper that breaks in September.

    player,pos,points[,team]
    Ja'Marr Chase,WR,18.4,CIN

Names are matched the way the ADP join already does - normalised name plus
position - because player ids are not shared across networks and never will be.

There is deliberately no scraper here. NFL.com, CBS and FantasyPros each have
their own terms and their own auth, and inventing an endpoint that works today
and lies quietly in October is worse than an honest CSV.
"""

from __future__ import annotations

import csv
import pathlib
import re
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
