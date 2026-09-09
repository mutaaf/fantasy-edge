"""Opportunity metrics from nflverse, joined to the draft board.

Fantasy points tell you what happened. Target share, aDOT and touch volume
tell you *why*, and they carry to next season far better than points do. The
league APIs expose none of it, so this pulls the free nflverse weekly release
and folds it in.

Two rules make the output honest rather than impressive:

1. **Opportunity is only ever compared within a position.** A running back's
   touches and a receiver's target share are different units. Ranking them on
   one scale produces a sleeper list made entirely of running backs, which is
   an artifact of the arithmetic, not a finding.
2. **A player with no prior season has no profile, and says so.** Rookies are
   absent from last year's data. Silence is reported as silence rather than
   scored as zero, which would rank every rookie as the worst player alive.

No API key, no account. Two CSVs over HTTPS, cached for a day.
"""

from __future__ import annotations

import collections
import csv
import io
import json
import pathlib
import time
import urllib.request

BASE = "https://github.com/nflverse/nflverse-data/releases/download"
WEEKLY = BASE + "/stats_player/stats_player_week_{season}.csv"
ROSTER = BASE + "/players/players.csv"
CACHE_DIR = pathlib.Path.home() / ".fantasy-edge"
CACHE_TTL = 24 * 3600
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/140.0"

SKILL = ("QB", "RB", "WR", "TE")


def _csv(url: str) -> list[dict]:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as r:
        return list(csv.DictReader(io.StringIO(r.read().decode("utf-8", "replace"))))


def _num(row: dict, key: str) -> float:
    v = row.get(key)
    if v in (None, "", "NA"):
        return 0.0
    try:
        return float(v)
    except ValueError:
        return 0.0


def _cached(name: str, build):
    path = CACHE_DIR / name
    if path.exists() and time.time() - path.stat().st_mtime < CACHE_TTL:
        try:
            return json.loads(path.read_text())
        except (OSError, ValueError):
            pass
    data = build()
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data))
    except OSError:
        pass                                  # a cold cache is not a failure
    return data


def season_profiles(season: int) -> dict:
    """Per-player regular-season opportunity, keyed by nflverse player id."""

    def build():
        rows = [r for r in _csv(WEEKLY.format(season=season))
                if r.get("season_type") == "REG"]
        agg: dict = collections.defaultdict(lambda: collections.defaultdict(float))
        meta: dict = {}
        for r in rows:
            pid = r.get("player_id") or r.get("gsis_id")
            if not pid:
                continue
            a = agg[pid]
            a["g"] += 1
            for k in ("targets", "receptions", "receiving_air_yards",
                      "receiving_yards_after_catch", "carries", "fantasy_points_ppr"):
                a[k] += _num(r, k)
            a["ts"] += _num(r, "target_share")
            a["ays"] += _num(r, "air_yards_share")
            a["wopr"] += _num(r, "wopr")
            meta[pid] = {"name": r.get("player_display_name"),
                         "pos": r.get("position"),
                         "team": r.get("recent_team") or r.get("team")}
        out = {}
        for pid, a in agg.items():
            m = meta[pid]
            if m["pos"] not in SKILL:
                continue
            g = a["g"] or 1
            out[pid] = {
                "name": m["name"], "pos": m["pos"], "team": m["team"], "g": int(g),
                "tgt": int(a["targets"]), "car": int(a["carries"]),
                "ts": round(100 * a["ts"] / g, 1),
                "ays": round(100 * a["ays"] / g, 1),
                "wopr": round(a["wopr"] / g, 2),
                "adot": round(a["receiving_air_yards"] / a["targets"], 1) if a["targets"] else 0.0,
                "yac": round(a["receiving_yards_after_catch"] / a["receptions"], 1) if a["receptions"] else 0.0,
                "ppg": round(a["fantasy_points_ppr"] / g, 1),
            }
        return out

    return _cached(f"nflverse_profiles_{season}.json", build)


def espn_bridge() -> dict:
    """ESPN player id -> nflverse id. nflverse publishes the crosswalk."""
    def build():
        out = {}
        for r in _csv(ROSTER):
            e, g = (r.get("espn_id") or "").strip(), (r.get("gsis_id") or "").strip()
            if e and g:
                out[e] = g
        return out
    return _cached("nflverse_espn_bridge.json", build)


def _percentile(sorted_vals: list[float], v: float) -> float:
    return 100 * sum(1 for x in sorted_vals if x < v) / max(len(sorted_vals) - 1, 1)


def opportunity(p: dict) -> float:
    """One number per position, never compared across them."""
    g = max(p["g"], 1)
    if p["pos"] in ("WR", "TE"):
        return p["ts"]                        # share of the team's targets
    if p["pos"] == "RB":
        return (p["car"] + p["tgt"]) / g      # touches a game
    return p["tgt"] / g


def build(adp_rows: list[dict], season: int = 2025, min_games: int = 6,
          adp_floor: float = 165.0) -> dict:
    """Attach last season's profile to this season's ADP board.

    `adp_rows` are the ADP CSV dicts: player_id, name, pos, rank.
    Returns {player name: profile}, where a profile may be absent entirely,
    and where `gap` is present only for players the market actually prices.
    """
    profiles, bridge = season_profiles(season), espn_bridge()
    joined: dict[str, dict] = {}
    for r in adp_rows:
        if r.get("pos") not in SKILL:
            continue
        try:
            gsis = bridge.get(str(int(r["player_id"])))
        except (TypeError, ValueError):
            continue
        prof = profiles.get(gsis or "")
        if prof:
            joined[r["name"]] = {**prof, "adp": float(r["rank"])}

    # Depth-chart role, derived from who actually saw the targets.
    by_team: dict = collections.defaultdict(list)
    for name, p in joined.items():
        if p["pos"] in ("WR", "TE"):
            by_team[(p["team"], p["pos"])].append((p["ts"], name))
    for (team, pos), members in by_team.items():
        for i, (_, name) in enumerate(sorted(members, reverse=True), start=1):
            joined[name]["role"] = f"{pos}{i}"

    # Usage against price, ranked inside each position.
    #
    # Anything at or past `adp_floor` is excluded from the comparison. ESPN
    # parks every unranked player on one placeholder value near 170, so those
    # rows carry no price information at all. Scored, they would take over the
    # whole sleeper list: zero apparent cost against any usage is a maximal
    # gap, and the result would be a ranking of the ADP floor, not of value.
    for pos in ("WR", "TE", "RB"):
        grp = {n: p for n, p in joined.items()
               if p["pos"] == pos and p["g"] >= min_games and p["adp"] < adp_floor}
        if len(grp) < 8:
            continue
        opps = sorted(opportunity(p) for p in grp.values())
        adps = sorted(p["adp"] for p in grp.values())
        for n, p in grp.items():
            use = _percentile(opps, opportunity(p))
            cost = 100 - _percentile(adps, p["adp"])
            p["use"] = round(use)
            p["cost"] = round(cost)
            p["gap"] = round(use - cost)
    return joined
