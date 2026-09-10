"""Spot an injury to somebody you actually roster, and say something about it.

There is no injury feed available here - ESPN's is behind the same edge that
rate-limits the scoreboard - so this reads the wire the board already carries
and works out which stories are about a body rather than a box score. That is a
classifier, not a lookup, so it is written to be wrong in the safe direction:
a story it cannot confidently call an injury is simply not one.

The roast is the point of the exercise, and the rule that keeps it from being
noise is that every clause has to be a fact from the database. Where you took
him, how far ahead of the market that was, how many of your line-ups he starts
in, what he was projected for tonight. A joke built on a real number lands; a
generated one about a player nobody drafted is just a machine being pleased
with itself.
"""

from __future__ import annotations

import re

from .providers.sleeper import normalise

# Ordered worst-first: a player named in several stories takes the worst one.
SEVERITY = [
    ("out", re.compile(
        r"\b(ruled out|out for the season|season[- ]ending|placed on (?:injured "
        r"reserve|IR)\b|to IR\b|will miss|expected to miss|set to miss|"
        r"miss(?:es)? (?:at least )?(?:the |his )?(?:opener|season|\d+))\b", re.I)),
    ("doubtful", re.compile(r"\bdoubtful\b", re.I)),
    ("questionable", re.compile(r"\b(questionable|game[- ]time decision)\b", re.I)),
    ("hurt", re.compile(
        r"\b(injur\w*|hurt|high ankle|ankle|knee|hamstring|shoulder|concussion|"
        r"acl|achilles|groin|calf|quad|hip|wrist|foot|carted|sidelined|strain|"
        r"sprain|surgery|MRI)\b", re.I)),
]

# Stories that merely mention a body part while being about football. Without
# this, "Seahawks pick off Drake Maye 3 times" reads as an injury because the
# recap happens to say somebody was banged up.
NOT_INJURY = re.compile(
    r"\b(pick(?:ed)? off|interception|touchdown pass|rushing title|"
    r"trade|contract|extension|holdout|suspend\w*|fined|arrest\w*|lawsuit|"
    r"prosecution|allege\w*)\b", re.I)

RANK = {name: i for i, (name, _) in enumerate(SEVERITY)}
LABEL = {"out": "OUT", "doubtful": "DOUBTFUL",
         "questionable": "QUESTIONABLE", "hurt": "INJURED"}


def classify(text: str) -> str | None:
    """Worst severity the text supports, or None if it is not about an injury."""
    if NOT_INJURY.search(text) and not re.search(r"\binjur\w*|carted|sprain|MRI\b",
                                                 text, re.I):
        return None
    for name, pattern in SEVERITY:
        if pattern.search(text):
            return name
    return None


def _facts(store, player_id: str, season: int) -> dict:
    """Everything the database knows that a roast could legitimately use."""
    picks = store.q(
        """SELECT d.league_id, d.round, d.overall, a.rank AS adp,
                  m.name AS team, l.name AS league
           FROM draft_pick d
           LEFT JOIN manager m ON m.provider=d.provider AND m.league_id=d.league_id
                              AND m.season=d.season AND m.team_id=d.team_id
           LEFT JOIN league  l ON l.provider=d.provider AND l.league_id=d.league_id
                              AND l.season=d.season
           LEFT JOIN adp a ON a.season=d.season AND a.provider=d.provider
                          AND a.player_id=d.player_id
           WHERE d.player_id=? AND d.season=?
           ORDER BY d.overall""", (str(player_id), season))
    # One line-up is one team in one league, not one row per week.
    # One line-up is one team in one league. Leaving `projected` inside the
    # DISTINCT made every weekly projection its own row, so a player started in
    # four leagues reported seventeen line-ups.
    starts = store.q(
        "SELECT COUNT(*) c FROM ("
        "  SELECT DISTINCT league_id, team_id FROM roster_slot "
        "  WHERE player_id=? AND season=? AND started=1)",
        (str(player_id), season))
    proj = store.q(
        "SELECT MAX(projected) p FROM roster_slot "
        "WHERE player_id=? AND season=? AND started=1", (str(player_id), season))
    return {
        "picks": [dict(r) for r in picks],
        "lineups": starts[0]["c"] if starts else 0,
        "projected": round(float(proj[0]["p"] or 0.0), 1) if proj else 0.0,
    }


def roast(name: str, pos: str, severity: str, facts: dict) -> str:
    """One line, and every clause in it is a number from the database."""
    picks = facts.get("picks") or []
    worst = None
    for p in picks:
        if p.get("adp") is not None:
            reach = p["adp"] - p["overall"]
            if worst is None or reach > worst[0]:
                worst = (reach, p)

    bits = []
    if worst and worst[0] >= 3:
        reach, p = worst
        bits.append(
            f"{p['team']} took {name} {reach:.0f} picks ahead of the market in "
            f"round {p['round']} of {p['league']}")
    elif picks:
        p = picks[0]
        bits.append(f"{name} went in round {p['round']} of {p['league']}")
    else:
        bits.append(f"{name} was not drafted anywhere")

    if facts.get("lineups"):
        n = facts["lineups"]
        bits.append(f"and he is starting in {n} line-up{'s' if n != 1 else ''} "
                    f"this week")
    if facts.get("projected"):
        bits.append(f"projected for {facts['projected']}")

    tail = {
        "out": "Those are the points he will not be scoring.",
        "doubtful": "Start thinking about the bench now, not at one o'clock.",
        "questionable": "Enjoy refreshing the inactives list all morning.",
        "hurt": "Hold that thought until the MRI.",
    }[severity]
    return ", ".join(bits) + ". " + tail


def detect(store, stories: list[dict], season: int = 2026) -> list[dict]:
    """Injury stories that name somebody in one of your starting line-ups.

    `stories` are the already-tagged items from the news feed, so the expensive
    name matching has happened once upstream.
    """
    rostered = {}
    for r in store.q(
            "SELECT DISTINCT p.player_id, p.name, p.pos FROM roster_slot r "
            "JOIN player p ON p.provider=r.provider AND p.player_id=r.player_id "
            "WHERE r.started=1 AND r.season=?", (season,)):
        if r["name"]:
            rostered[normalise(r["name"])] = r

    found: dict[str, dict] = {}
    for st in stories:
        headline = st.get("headline", "")
        text = f"{headline} {st.get('detail','')}"
        sev = classify(text)
        if not sev:
            continue
        who = rostered.get(normalise(st.get("player") or ""))
        if not who:
            continue
        # The wire tagger matches a name anywhere in an article, which is right
        # for "stories about my players" and badly wrong here: one "Fantasy
        # buzz" round-up mentioning a dozen names would report a dozen injuries.
        # An injury is only attributed when the headline itself names the man.
        if normalise(who["name"]) not in normalise(headline):
            continue
        pid = str(who["player_id"])
        prev = found.get(pid)
        if prev and RANK[prev["severity"]] <= RANK[sev]:
            prev["stories"].append(st.get("headline", ""))
            continue
        entry = found.get(pid) or {"stories": []}
        entry.update({
            "id": pid, "name": who["name"], "pos": who["pos"],
            "severity": sev, "label": LABEL[sev],
            "headline": st.get("headline", ""), "url": st.get("url", ""),
            "published": st.get("published", ""),
            "stories": entry["stories"] + [st.get("headline", "")],
        })
        found[pid] = entry

    from .live import headshot_url, logo_url, team_abbr

    clubs = {r["player_id"]: r["nfl_team"] for r in store.q(
        "SELECT player_id, nfl_team FROM player WHERE provider='espn'")}

    out = []
    for entry in found.values():
        facts = _facts(store, entry["id"], season)
        entry.update(facts)
        # Carry the portrait here rather than leaving the page to find it. An
        # injured player is often not on the team the viewer has selected, so
        # the cross-league roster it would otherwise look him up in does not
        # contain him - and he renders as a grey disc at the loudest moment on
        # the board.
        club = team_abbr(clubs.get(entry["id"]))
        entry["team"] = club
        entry["img"] = headshot_url(entry["id"], club)
        entry["logo"] = logo_url(club)
        entry["roast"] = roast(entry["name"], entry["pos"],
                               entry["severity"], facts)
        out.append(entry)
    out.sort(key=lambda e: (RANK[e["severity"]], -e.get("projected", 0)))
    return out
