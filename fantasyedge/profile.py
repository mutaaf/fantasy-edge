"""Everything the database knows about one player, assembled for a card.

The board answers "how is he doing right now". This answers the questions you
ask before you trust him: what has he done in the seasons you have on file,
where he finished among his position each year, and where he actually went in
your drafts.

Two honest limits, stated here because they shape what the card can show.

Historical points are whatever each league's own scoring produced, because
that is what is stored - there are no raw box-score lines behind past weeks,
so a season cannot be re-scored into half-PPR after the fact. Only the current
week has raw stats, and only that week can be shown across formats.

And the only ADP on file is ESPN's, one source and one format. Rather than
invent the others, the card shows something better for this purpose: where he
was actually taken in *your* leagues, split by league size, which is a real
draft position from a real room rather than a national average.
"""

from __future__ import annotations

# A season needs this many scored weeks before its rank means anything.
MIN_WEEKS = 4


def _weekly(store, player_id: str) -> list[dict]:
    return [dict(r) for r in store.q(
        "SELECT DISTINCT season, week, points FROM roster_slot "
        "WHERE player_id=? AND points IS NOT NULL ORDER BY season, week",
        (str(player_id),))]


def _position_ranks(store, pos: str, seasons: list[int]) -> dict[int, list]:
    """Every player at this position, by season total. The rank falls out of it."""
    if not pos or not seasons:
        return {}
    marks = ",".join("?" * len(seasons))
    rows = store.q(
        f"""SELECT d.season, d.player_id, SUM(d.points) AS total,
                   COUNT(*) AS weeks
            FROM (SELECT DISTINCT season, week, player_id, points
                  FROM roster_slot WHERE points IS NOT NULL) d
            JOIN player p ON p.player_id = d.player_id
            WHERE p.pos = ? AND d.season IN ({marks})
            GROUP BY d.season, d.player_id""",
        (pos, *seasons))
    by_season: dict[int, list] = {}
    for r in rows:
        by_season.setdefault(r["season"], []).append(
            (r["player_id"], r["total"] or 0.0, r["weeks"]))
    for season in by_season:
        by_season[season].sort(key=lambda x: -x[1])
    return by_season


def season_log(store, player_id: str, pos: str) -> list[dict]:
    weeks = _weekly(store, player_id)
    if not weeks:
        return []
    seasons = sorted({w["season"] for w in weeks})
    ranks = _position_ranks(store, pos, seasons)

    out = []
    for season in seasons:
        wk = [w for w in weeks if w["season"] == season]
        played = [w["points"] for w in wk if w["points"] is not None]
        total = sum(played)
        rank = None
        field = ranks.get(season) or []
        for i, (pid, _t, _w) in enumerate(field, start=1):
            if str(pid) == str(player_id):
                rank = i
                break
        out.append({
            "season": season,
            "weeks": len(played),
            "total": round(total, 1),
            "ppg": round(total / len(played), 2) if played else 0.0,
            "best": round(max(played), 1) if played else 0.0,
            "worst": round(min(played), 1) if played else 0.0,
            # A season in progress has a row per week with nothing in it yet.
            # Ranking a field where everybody has scored zero produces a number
            # that looks authoritative and means nothing, so it stays None until
            # somebody has actually played.
            "rank": rank if (len(played) >= MIN_WEEKS and total > 0) else None,
            "started": total > 0,
            "field": sum(1 for _p, t, _w in field if t > 0),
            "weekly": [round(w["points"] or 0.0, 1) for w in wk],
        })
    return out


def draft_history(store, player_id: str) -> list[dict]:
    """Where he actually went, in your rooms, with the league size attached.

    Size is the part that matters: pick 21 in a ten-team league is the back of
    round two, and in a twelve it is the front. A single ADP number cannot say
    that, and these are real picks rather than an average of strangers.
    """
    rows = store.q(
        """SELECT d.season, d.league_id, d.overall, d.round, d.cost,
                  l.name AS league, l.team_count AS teams,
                  m.name AS team, a.rank AS adp
           FROM draft_pick d
           LEFT JOIN league  l ON l.provider=d.provider AND l.league_id=d.league_id
                              AND l.season=d.season
           LEFT JOIN manager m ON m.provider=d.provider AND m.league_id=d.league_id
                              AND m.season=d.season AND m.team_id=d.team_id
           LEFT JOIN adp a ON a.season=d.season AND a.provider=d.provider
                          AND a.player_id=d.player_id
           WHERE d.player_id=? ORDER BY d.season DESC, d.overall""",
        (str(player_id),))
    out = []
    for r in rows:
        adp = r["adp"]
        out.append({
            "season": r["season"], "league": r["league"], "teams": r["teams"],
            "team": r["team"], "round": r["round"], "overall": r["overall"],
            "adp": round(adp, 1) if adp is not None else None,
            "reach": round(adp - r["overall"], 1) if adp is not None else None,
            "cost": r["cost"],
        })
    return out


def format_lines(stats: dict) -> list[dict]:
    """The same raw stat line under the three common scoring systems.

    Only possible where raw stats exist, which means the current week. A past
    season stores points, not the plays behind them, so it cannot be restated.
    """
    from .scoring import Scoring

    formats = [
        ("PPR", {"reception": 1.0}),
        ("Half PPR", {"reception": 0.5}),
        ("Standard", {"reception": 0.0}),
    ]
    return [{"name": name,
             "points": Scoring.from_config({"scoring": rules}).points(stats)}
            for name, rules in formats]


def build(store, player_id: str, live_stats: dict | None = None) -> dict:
    row = store.q("SELECT name, pos, nfl_team FROM player WHERE player_id=? LIMIT 1",
                  (str(player_id),))
    if not row:
        return {}
    from .live import headshot_url, logo_url, team_abbr

    pos = row[0]["pos"] or ""
    club = team_abbr(row[0]["nfl_team"])
    log = season_log(store, player_id, pos)
    scored = [s for s in log if s["rank"]]
    return {
        "id": str(player_id), "name": row[0]["name"], "pos": pos, "team": club,
        "img": headshot_url(player_id, club), "logo": logo_url(club),
        "seasons": log,
        "recentRanks": [{"season": s["season"], "rank": s["rank"],
                         "field": s["field"], "label": f"{pos}{s['rank']}"}
                        for s in scored[-2:]],
        "career": {
            "seasons": len(log),
            "best": max((s["ppg"] for s in log), default=0.0),
            "totalWeeks": sum(s["weeks"] for s in log),
        },
        "draft": draft_history(store, player_id),
        "formats": format_lines(live_stats) if live_stats else [],
    }


def opportunity(player_id: str, season: int | None = None) -> dict:
    """What this player is actually being given, from nflverse.

    Fantasy points are an outcome; targets, carries and target share are the
    opportunity behind them, and a card that shows only the outcome cannot say
    whether a quiet week was bad luck or a bad role. nflverse publishes this
    free and `advanced.py` already caches it - it was simply never served.

    Returns {} when the player is not in the release, which is the honest
    answer for a rookie or a player who has not taken a snap.
    """
    from . import advanced

    try:
        bridge = advanced.espn_bridge()
        nid = bridge.get(str(player_id))
        if not nid:
            return {}
        prof = advanced.season_profiles(season or 2025)
        row = prof.get(str(nid))
    except Exception:
        return {}
    if not row:
        return {}
    out = {"games": row.get("g"), "targets": row.get("tgt"),
           "carries": row.get("car"), "targetShare": row.get("ts"),
           "airYardsShare": row.get("ays"), "wopr": row.get("wopr"),
           "adot": row.get("adot"), "yac": row.get("yac"),
           "ppg": row.get("ppg")}
    return {k: v for k, v in out.items() if v is not None}
