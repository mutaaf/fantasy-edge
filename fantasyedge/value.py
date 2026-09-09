"""Positional value: replacement level, value over replacement, and cliffs.

The single most useful idea in drafting is that a player's worth is not his
score, it is his score minus whatever you could have had at that position
anyway. Twelve quarterbacks start in a twelve-team league out of thirty-odd
who play, so QB12 is excellent and the elite ones are barely scarce. Twenty-
five running backs start once the flex is counted, so the drop to RB26 is a
cliff. That asymmetry is why the top running back outranks the top
quarterback despite scoring fewer points.

Everything here is computed from the league's own shape - team count and the
actual starting slots - because replacement level moves with both. A ten-team
league and a fourteen-team league are different games.

Two honesties the numbers depend on:

1. **Last season's points are not a projection.** Points by positional rank
   come from a completed season; the *shape* of those curves is what carries
   forward, not the individual names. Applying the curve to this year's ADP
   order says "if the market has the ordering right, this is what the pick is
   worth" - it does not predict anyone's season.
2. **Some positions barely persist.** First-half scoring predicts second-half
   scoring strongly at running back and receiver, weakly at tight end, and
   hardly at all at quarterback and kicker. A steep-looking curve at a
   position that does not persist is not an edge, so the persistence figure
   travels with the value figure everywhere it is shown.
"""

from __future__ import annotations

import collections
import csv
import io
import json
import pathlib
import time
import urllib.request

CACHE = pathlib.Path.home() / ".fantasy-edge" / "value_curves_{season}.json"
CACHE_TTL = 7 * 24 * 3600
WEEKLY = ("https://github.com/nflverse/nflverse-data/releases/download"
          "/stats_player/stats_player_week_{season}.csv")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/140.0"

SKILL = ("QB", "RB", "WR", "TE")
FLEX_OK = ("RB", "WR", "TE")


def _num(row: dict, key: str) -> float:
    v = row.get(key)
    if v in (None, "", "NA"):
        return 0.0
    try:
        return float(v)
    except ValueError:
        return 0.0


def _kicker_points(r: dict) -> float:
    """nflverse's PPR column excludes kicking, so rebuild it from the makes."""
    return (3 * _num(r, "fg_made_0_19") + 3 * _num(r, "fg_made_20_29")
            + 3 * _num(r, "fg_made_30_39") + 4 * _num(r, "fg_made_40_49")
            + 5 * _num(r, "fg_made_50_59") + 5 * _num(r, "fg_made_60_")
            + _num(r, "pat_made") - _num(r, "fg_missed"))


def _corr(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n < 3:
        return 0.0
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    den = (sum((a - mx) ** 2 for a in xs) * sum((b - my) ** 2 for b in ys)) ** 0.5
    return round(num / den, 2) if den else 0.0


def curves(season: int = 2025) -> dict:
    """Season points by positional rank, plus how well a half-season persists."""
    path = pathlib.Path(str(CACHE).format(season=season))
    if path.exists() and time.time() - path.stat().st_mtime < CACHE_TTL:
        try:
            return json.loads(path.read_text())
        except (OSError, ValueError):
            pass

    req = urllib.request.Request(WEEKLY.format(season=season),
                                 headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as fh:
        rows = [r for r in csv.DictReader(io.StringIO(fh.read().decode("utf-8", "replace")))
                if r.get("season_type") == "REG"]

    total: dict = collections.defaultdict(float)
    games: dict = collections.Counter()
    halves: dict = collections.defaultdict(lambda: [0.0, 0.0])
    pos_of: dict = {}
    for r in rows:
        pid, pos = r.get("player_id") or r.get("gsis_id"), r.get("position")
        if not pid or pos not in (*SKILL, "K"):
            continue
        pts = _kicker_points(r) if pos == "K" else _num(r, "fantasy_points_ppr")
        total[pid] += pts
        games[pid] += 1
        halves[pid][0 if int(r["week"]) <= 9 else 1] += pts
        pos_of[pid] = pos

    out = {"season": season, "byPos": {}, "persist": {}}
    for pos in (*SKILL, "K"):
        ids = [p for p in total if pos_of[p] == pos and games[p] >= 8]
        out["byPos"][pos] = sorted((round(total[p], 1) for p in ids), reverse=True)
        full = [p for p in ids if games[p] >= 14]
        out["persist"][pos] = _corr([halves[p][0] for p in full],
                                    [halves[p][1] for p in full]) if len(full) >= 8 else 0.0
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(out))
    except OSError:
        pass
    return out


def starters(teams: int, slots: list[str]) -> dict:
    """How many of each position actually start, flex allocated to the best pool."""
    base = collections.Counter(s for s in slots if s in SKILL)
    counts = {p: base.get(p, 0) * teams for p in SKILL}
    counts.setdefault("K", slots.count("K") * teams)
    counts["DEF"] = slots.count("DEF") * teams
    return counts


def replacement(cv: dict, teams: int, slots: list[str]) -> dict:
    """The first player at each position who does not start anywhere."""
    counts = starters(teams, slots)
    flex_spots = slots.count("FLEX") * teams

    # Hand each flex seat to whichever position has the best player left.
    cursor = {p: counts.get(p, 0) for p in FLEX_OK}
    for _ in range(flex_spots):
        best, best_pts = None, float("-inf")
        for p in FLEX_OK:
            pool = cv["byPos"].get(p, [])
            i = cursor[p]
            if i < len(pool) and pool[i] > best_pts:
                best, best_pts = p, pool[i]
        if best is None:
            break
        cursor[best] += 1

    out = {}
    for p in (*SKILL, "K"):
        n = cursor.get(p, counts.get(p, 0))
        pool = cv["byPos"].get(p, [])
        if not pool:
            continue
        out[p] = {"starts": n,
                  "replacement": pool[n] if n < len(pool) else pool[-1],
                  "persist": cv["persist"].get(p, 0.0)}
    return out


def build(adp_rows: list[dict], teams: int, slots: list[str],
          season: int = 2025) -> tuple[dict, dict]:
    """Value over replacement for every player on the board, by ADP order.

    A player's positional rank in ADP is read as the market's guess at where
    he will finish. That rank is priced against last season's curve. It is a
    statement about the market's ordering, not a forecast of any one player.
    """
    cv = curves(season)
    repl = replacement(cv, teams, slots)

    ranked = sorted((r for r in adp_rows if r.get("pos") in (*SKILL, "K")),
                    key=lambda r: float(r["rank"]))
    seen: dict = collections.Counter()
    vor: dict = {}
    for r in ranked:
        pos = r["pos"]
        info = repl.get(pos)
        if not info:
            continue
        i = seen[pos]
        seen[pos] += 1
        pool = cv["byPos"][pos]
        pts = pool[i] if i < len(pool) else pool[-1]
        vor[r["name"]] = {
            "pos": pos, "posRank": i + 1,
            "pts": round(pts, 1),
            "vor": round(pts - info["replacement"], 1),
            "starts": info["starts"],
            "startable": i < info["starts"],
        }

    # The biggest gap inside the startable range: where a position falls off.
    for pos, info in repl.items():
        pool = cv["byPos"][pos][: max(info["starts"], 2)]
        gaps = [(round(pool[i] - pool[i + 1], 1), i + 1) for i in range(len(pool) - 1)]
        drop, at = max(gaps, default=(0.0, 0))
        info["cliff"] = {"after": at, "drop": drop}
        info["best"] = round(cv["byPos"][pos][0] - info["replacement"], 1)
    return vor, repl
