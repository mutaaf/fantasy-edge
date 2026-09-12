"""Turn a box score into fantasy points.

ESPN's summary endpoint reports football statistics, not fantasy ones. This is
the translation, and it is deliberately its own module because it is the one
place where a league's own rules matter: `config/league.toml` carries the
scoring, and a league that pays half a point per reception should not be told
it is winning by a point it does not score.

Stats arrive as a `keys` list plus a parallel `stats` list per athlete, so
everything here reads by key name rather than by position. ESPN reorders those
columns from time to time, and a positional parser would keep working while
quietly attributing rushing yards to interceptions.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Sensible defaults for a full-PPR league. Anything present in league.toml wins.
DEFAULTS = {
    "reception": 1.0,
    "pass_yard": 0.04,
    "rush_yard": 0.1,
    "rec_yard": 0.1,
    "return_yard": 0.04,
    "pass_touchdown": 4.0,
    "touchdown": 6.0,          # rushing and receiving
    "interception": -2.0,
    "fumble_lost": -2.0,
    "two_point": 2.0,
    "field_goal": 3.0,
    "extra_point": 1.0,
}

# Which box-score keys carry the numbers we care about. A key we do not know
# is ignored rather than guessed at.
#: ESPN reports some columns as a made-and-attempted pair under one key -
#: "fieldGoalsMade/fieldGoalAttempts", whose value is "2/2". The value side was
#: always handled (`_num` takes the part before the slash), but the *key* was
#: not: nothing named `fieldGoalsMade` is ever sent, so the column was skipped
#: and every kicker on every board scored exactly zero, always. Jason Myers
#: kicked two field goals and an extra point in the game this was found in and
#: read 0.0. Mapping the pair onto the name the scoring rules already use fixes
#: it everywhere at once.
ALIAS = {
    "fieldGoalsMade/fieldGoalAttempts": "fieldGoalsMade",
    "extraPointsMade/extraPointAttempts": "extraPointsMade",
}

WANTED = {
    "passingYards", "passingTouchdowns", "interceptions",
    "rushingYards", "rushingTouchdowns",
    "receptions", "receivingYards", "receivingTouchdowns",
    "fumblesLost", "fieldGoalsMade", "extraPointsMade",
    "kickReturnYards", "puntReturnYards",
}


@dataclass
class Scoring:
    rules: dict = field(default_factory=lambda: dict(DEFAULTS))

    @classmethod
    def from_config(cls, cfg: dict | None) -> "Scoring":
        rules = dict(DEFAULTS)
        for k, v in ((cfg or {}).get("scoring") or {}).items():
            try:
                rules[k] = float(v)
            except (TypeError, ValueError):
                continue
        return cls(rules)

    def points(self, stat: dict) -> float:
        r, g = self.rules, stat.get
        total = (
            g("passingYards", 0.0) * r["pass_yard"]
            + g("passingTouchdowns", 0.0) * r["pass_touchdown"]
            + g("interceptions", 0.0) * r["interception"]
            + g("rushingYards", 0.0) * r["rush_yard"]
            + g("rushingTouchdowns", 0.0) * r["touchdown"]
            + g("receptions", 0.0) * r["reception"]
            + g("receivingYards", 0.0) * r["rec_yard"]
            + g("receivingTouchdowns", 0.0) * r["touchdown"]
            + g("fumblesLost", 0.0) * r["fumble_lost"]
            + g("fieldGoalsMade", 0.0) * r["field_goal"]
            + g("extraPointsMade", 0.0) * r["extra_point"]
            + (g("kickReturnYards", 0.0) + g("puntReturnYards", 0.0)) * r["return_yard"]
        )
        return round(total, 2)


def _num(raw) -> float:
    """ESPN reports "20/30" for made/attempted and "--" for nothing."""
    if raw in (None, "", "--"):
        return 0.0
    s = str(raw).split("/")[0].replace(",", "")
    try:
        return float(s)
    except ValueError:
        return 0.0


def parse_boxscore(summary: dict) -> dict[str, dict]:
    """Athlete id -> the stats we know how to score.

    Reads by key name. A category we do not recognise contributes nothing
    rather than being folded in at the wrong weight.
    """
    out: dict[str, dict] = {}
    for team in ((summary.get("boxscore") or {}).get("players") or []):
        for cat in (team.get("statistics") or []):
            keys = cat.get("keys") or []
            idx = {ALIAS.get(k, k): i for i, k in enumerate(keys)
                   if ALIAS.get(k, k) in WANTED}
            if not idx:
                continue
            for ath in (cat.get("athletes") or []):
                pid = str(((ath.get("athlete") or {}).get("id")) or "")
                if not pid:
                    continue
                stats = ath.get("stats") or []
                bucket = out.setdefault(pid, {})
                for key, i in idx.items():
                    if i < len(stats):
                        bucket[key] = bucket.get(key, 0.0) + _num(stats[i])
    return out


def boxscore_names(summary: dict) -> dict[str, dict]:
    """Athlete id -> the name and club the box score used.

    `parse_boxscore` throws these away because scoring never needs them. A
    provider whose player ids are not ESPN's does need them: it is the only
    bridge from a Sleeper or Yahoo roster row to a line in this box score.
    """
    out: dict[str, dict] = {}
    for team in ((summary.get("boxscore") or {}).get("players") or []):
        ab = ((team.get("team") or {}).get("abbreviation") or "").upper()
        for cat in (team.get("statistics") or []):
            for ath in (cat.get("athletes") or []):
                a = ath.get("athlete") or {}
                pid = str(a.get("id") or "")
                if pid and pid not in out:
                    out[pid] = {"name": a.get("displayName") or "", "team": ab}
    return out


def score_boxscore(summary: dict, scoring: Scoring | None = None) -> dict[str, float]:
    sc = scoring or Scoring()
    return {pid: sc.points(stat) for pid, stat in parse_boxscore(summary).items()}


# ── team defence ────────────────────────────────────────────────────────
#
# A defence is not scored from its own stat line but from what the other side
# failed to do, which is why it needs the whole game rather than one athlete's
# row. Both tiers below are ESPN's defaults; a league that runs different bands
# overrides them the same way it overrides any other rule.
#
# Read the tables as "up to this many, score that": the first threshold a value
# falls under wins.
POINTS_ALLOWED = [(0, 5.0), (6, 4.0), (13, 3.0), (17, 1.0), (27, 0.0),
                  (34, -1.0), (45, -3.0), (10**6, -5.0)]
YARDS_ALLOWED = [(99, 5.0), (199, 3.0), (299, 2.0), (349, 0.0), (399, -1.0),
                 (449, -3.0), (499, -5.0), (549, -6.0), (10**6, -7.0)]

DST_DEFAULTS = {
    "sack": 1.0, "def_interception": 2.0, "fumble_recovery": 2.0,
    "safety": 2.0, "def_touchdown": 6.0, "blocked_kick": 2.0,
}


def _tier(value: float, table) -> float:
    for ceiling, points in table:
        if value <= ceiling:
            return points
    return table[-1][1]


def dst_points(points_allowed: float, yards_allowed: float | None = None,
               stats: dict | None = None, rules: dict | None = None,
               count_yards: bool = True) -> float:
    """Score one team defence.

    `yards_allowed` is optional because it is the half that needs a box score;
    points allowed alone is available from the scoreboard. Passing None scores
    the defence on points and big plays only, which is a real answer rather
    than a wrong one.
    """
    r = dict(DST_DEFAULTS)
    r.update(rules or {})
    st = stats or {}
    total = _tier(points_allowed, POINTS_ALLOWED)
    if count_yards and yards_allowed is not None:
        total += _tier(yards_allowed, YARDS_ALLOWED)
    total += (st.get("sacks", 0.0) * r["sack"]
              + st.get("interceptions", 0.0) * r["def_interception"]
              + st.get("fumblesRecovered", 0.0) * r["fumble_recovery"]
              + st.get("safeties", 0.0) * r["safety"]
              + st.get("defensiveTouchdowns", 0.0) * r["def_touchdown"]
              + st.get("blockedKicks", 0.0) * r["blocked_kick"])
    return round(total, 2)


# Team totals we know how to read out of a summary.
TEAM_YARDS_KEYS = ("totalYards", "netTotalYards")

# Which category a defensive number is allowed to come from.
#
# `interceptions` is the trap: it is a key in the *passing* category too, where
# it means picks a quarterback threw. Reading it wherever it appears credits a
# defence for its own quarterback's mistakes - the defence of the team that
# just turned the ball over gets two points for it. So every defensive stat is
# bound to the category it legitimately comes from.
DEF_SOURCES = {
    "defensive": {"sacks", "defensiveTouchdowns", "safeties", "blockedKicks"},
    "interceptions": {"interceptions"},
    "fumbles": {"fumblesRecovered"},
}


def parse_team_defence(summary: dict) -> dict[str, dict]:
    """Club abbreviation -> yards it gained and the big plays its defence made.

    Yards *gained* here; the caller flips it into yards *allowed* by looking at
    the other side of the same game, which is the only place that pairing is
    known.
    """
    out: dict[str, dict] = {}
    box = summary.get("boxscore") or {}
    for team in (box.get("teams") or []):
        ab = ((team.get("team") or {}).get("abbreviation") or "").upper()
        if not ab:
            continue
        bucket = out.setdefault(ab, {})
        for stat in (team.get("statistics") or []):
            name = stat.get("name")
            if name in TEAM_YARDS_KEYS:
                bucket["yards"] = _num(stat.get("displayValue")
                                       if stat.get("displayValue") is not None
                                       else stat.get("value"))
    for team in (box.get("players") or []):
        ab = ((team.get("team") or {}).get("abbreviation") or "").upper()
        if not ab:
            continue
        bucket = out.setdefault(ab, {})
        for cat in (team.get("statistics") or []):
            allowed = DEF_SOURCES.get((cat.get("name") or "").lower())
            if not allowed:
                continue
            keys = cat.get("keys") or []
            idx = {k: i for i, k in enumerate(keys) if k in allowed}
            if not idx:
                continue
            for ath in (cat.get("athletes") or []):
                stats = ath.get("stats") or []
                for key, i in idx.items():
                    if i < len(stats):
                        bucket[key] = bucket.get(key, 0.0) + _num(stats[i])
    return out


# ── the whole line, not just the points ─────────────────────────────────
#
# The board needs a number. A card needs the line that produced it, and the
# Live tab needs both for men who are on nobody's roster - the twenty-six
# athletes a game scores that a four-league board never mentions. That is the
# same parse either way, so it happens once, here, rather than three times in
# three clients.

#: Which columns of each category a fantasy reader wants back, in reading
#: order. Everything else ESPN sends - QBR, air yards, long gains, the whole
#: defensive block - is either not scored or not a skill line, and a card that
#: showed it would be showing noise beside the number that matters.
LINE = {
    "passing": ["completions/passingAttempts", "passingYards",
                "passingTouchdowns", "interceptions"],
    "rushing": ["rushingAttempts", "rushingYards", "rushingTouchdowns"],
    "receiving": ["receptions", "receivingYards", "receivingTouchdowns",
                  "receivingTargets"],
    "kicking": ["fieldGoalsMade/fieldGoalAttempts",
                "extraPointsMade/extraPointAttempts"],
    "kickReturns": ["kickReturnYards"],
    "puntReturns": ["puntReturnYards"],
    "fumbles": ["fumblesLost"],
}

#: What a man was doing, decided by volume: the column that carries how many
#: times the ball came to him this way. Whichever is biggest is the job.
#:
#: Deliberately not a position. A box score groups by what happened, not by
#: who somebody is, so this can say a back ran and cannot say he is an RB -
#: a position, where this ships one, comes from a source that knows it.
#:
#: Volume rather than points, which was the first rule and was wrong in a way
#: worth keeping a note about: in a full-PPR league Rhamondre Stevenson's five
#: catches for 44 outscored his eighteen carries for 51, so scoring by
#: production filed a bell-cow running back under REC. Touches do not have
#: that problem, and touches are also how a person reads the line.
VOLUME = {"passing": ("completions/passingAttempts", "PASS"),
          "rushing": ("rushingAttempts", "RUSH"),
          "receiving": ("receptions", "REC"),
          "kicking": ("fieldGoalsMade/fieldGoalAttempts", "KICK"),
          "kickReturns": ("kickReturnYards", "RET"),
          "puntReturns": ("puntReturnYards", "RET")}

#: Ties break down this list.
RANK = ["PASS", "RUSH", "REC", "KICK"]

#: A return line is not comparable with the others and is never allowed to
#: win on volume. ESPN publishes return *yards* and no attempt column, so the
#: number sitting in that slot is measured in a different unit from a carry or
#: a catch: eighty return yards beat one reception on the arithmetic and made
#: Rashid Smith - a receiver who happens to return kicks - into a return man.
#: So a return decides the role only when it is the only line there is.
LAST = "RET"

#: Which of those roles is fantasy-relevant at all. `fumbles` is in LINE
#: because a lost fumble belongs on the card; it is not here because nobody is
#: a fumbler by trade.
SKILL = {"PASS", "RUSH", "REC", "KICK"}

#: Categories whose own labels do not say which category they are. ESPN calls
#: both return columns "YDS", so a man who returned a kick and a punt reads as
#: "80 YDS · 9 YDS" with nothing to tell them apart.
TAG = {"kickReturns": "KR", "puntReturns": "PR", "fumbles": "LOST"}


def boxscore_lines(summary: dict) -> dict[str, dict]:
    """Athlete id -> everything a card wants: who, what he did, and his role.

    Sibling of `parse_boxscore`, which stays as it is because scoring is on
    its critical path and wants nothing but numbers. This one carries the
    name, club, jersey and headshot ESPN already sent, a rendered line per
    category, and the role that line implies.

    The role is the category he was given the ball in most often - see
    `VOLUME`. A quarterback who takes a carry is still a quarterback and a
    back who throws one pass is not one, which precedence by order would get
    wrong in both directions.
    """
    out: dict[str, dict] = {}
    for team in ((summary.get("boxscore") or {}).get("players") or []):
        ab = ((team.get("team") or {}).get("abbreviation") or "").upper()
        for cat in (team.get("statistics") or []):
            name = cat.get("name") or ""
            want = LINE.get(name)
            if not want:
                continue
            keys = cat.get("keys") or []
            labels = cat.get("labels") or []
            cols = [(i, k, labels[i] if i < len(labels) else "")
                    for i, k in enumerate(keys) if k in want]
            if not cols:
                continue
            for ath in (cat.get("athletes") or []):
                a = ath.get("athlete") or {}
                pid = str(a.get("id") or "")
                if not pid:
                    continue
                stats = ath.get("stats") or []
                seg = []
                for n, (i, k, label) in enumerate(cols):
                    if i >= len(stats):
                        continue
                    raw = stats[i]
                    # The volume column always shows, even at zero - "0 CAR"
                    # is information. A zero in any other column is not.
                    if _num(raw) or n == 0:
                        # A column whose own label is a pair - C/ATT - reads
                        # as "23/33" and naming it again adds nothing. FG and
                        # XP are pairs whose label is the only thing telling
                        # them apart, so those keep theirs.
                        seg.append(str(raw) if "/" in str(label)
                                   else f"{raw} {label}".strip())
                if not seg:
                    continue
                row = out.setdefault(pid, {
                    "id": pid,
                    "name": a.get("displayName") or "",
                    "team": ab,
                    "jersey": str(a.get("jersey") or ""),
                    "headshot": ((a.get("headshot") or {}).get("href") or ""),
                    "lines": [], "role": "", "_vol": {},
                })
                row["lines"].append({"kind": name, "text": ", ".join(seg)})
                col = VOLUME.get(name)
                if col:
                    key, role = col
                    i = keys.index(key) if key in keys else -1
                    if 0 <= i < len(stats):
                        row["_vol"][role] = max(row["_vol"].get(role, 0.0),
                                                _num(stats[i]))
    for row in out.values():
        vol = row.pop("_vol", {})
        real = {r: v for r, v in vol.items() if r != LAST}
        if real:
            row["role"] = max(real, key=lambda r: (real[r], -RANK.index(r)))
        elif vol:
            row["role"] = LAST
        row["line"] = " · ".join(
            f"{TAG[l['kind']]} {l['text']}" if l["kind"] in TAG else l["text"]
            for l in row["lines"])
        row["skill"] = row["role"] in SKILL
    return out
