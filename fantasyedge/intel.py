"""Insight, computed rather than generated.

The Intel view answers "what should I actually look at this week". There are
two ways to answer that and only one of them can be checked. This module is
the one that can: every sentence it emits is assembled from numbers already in
the database or already produced by `leverage`, `analytics`, `profile` and
`injuries`, and every sentence ships the numbers it was built from alongside
it. A model may later narrate these findings - see `ai.py` - but it never
produces one, and the two never share a container.

Three rules hold the thing up.

**Provenance travels with the number.** An `Insight` is not a string; it is a
string plus the `Fact`s behind it, each naming the table or function it came
from. A reader who disbelieves a line can follow it back. An insight built
without facts is rejected at construction, because the failure mode this
guards against is the one that matters: a plausible sentence nobody can check.

**The caveat travels with the number too.** That convention is already
load-bearing in `analytics.py`, where a test asserts no result hides its own
weakness, and it would be silently undone by a layer that reads nine caveated
analyses and emits one confident headline. So `Insight.caveat` is required and
non-empty, and where an insight is derived from an analysis it carries that
analysis's caveat verbatim rather than a summary of it.

**Computed and model-written are different types.** `Insight.origin` is a
read-only property that returns "computed" and cannot be assigned;
`ai.Narration.origin` returns "model" the same way. They live under different
keys in the payload. Styling can be got wrong by a client; a type cannot.

What this module deliberately does not do: any I/O of its own. It is handed
the mosaic payload, the live snapshot, the injury list and the analyses, all
of which the API has already built and cached. That keeps it testable without
a network, keeps credentials out of it entirely, and means the same functions
run against a fixture in a test and a real Sunday in production.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from . import leverage

# ─────────────────────────── what we cannot source ───────────────────────────

# The design this view is modelled on shows five metrics no free feed in this
# project's reach publishes. Charting a route tree or a first read requires
# per-snap participation data that PFF and Next Gen Stats sell and nflverse
# does not carry. Producing them anyway - by estimating routes from targets,
# say - would put a number on the screen that looks like the others and is not
# one, which is the single worst thing this view could do. So they are named
# here, with the reason, and the UI is expected to say so out loud rather than
# leave a gap the reader fills in with an assumption.
UNAVAILABLE: list[dict[str, str]] = [
    {"metric": "First Read Rate",
     "reason": "Requires per-snap coverage charting. No free feed publishes "
               "which receiver the quarterback looked at first."},
    {"metric": "Yards Per Route Run",
     "reason": "Needs routes run, which is charted by hand by PFF and is not "
               "in the nflverse release. Targets are not a substitute: they "
               "are the numerator of a different fraction."},
    {"metric": "Route Participation",
     "reason": "Needs routes run against team dropbacks. Same missing "
               "denominator as YPRR."},
    {"metric": "Route tree",
     "reason": "Needs per-route classification from tracking data."},
    {"metric": "Target heatmap",
     "reason": "Needs per-target field coordinates. nflverse publishes air "
               "yards in aggregate, not the x/y of each throw."},
]

# What we do have, from nflverse via `advanced.season_profiles`. Listed so a
# client can render the opportunity panel from the source of truth instead of
# a hardcoded list that drifts.
AVAILABLE_OPPORTUNITY: list[dict[str, str]] = [
    {"key": "targets", "label": "Targets", "unit": ""},
    {"key": "carries", "label": "Carries", "unit": ""},
    {"key": "targetShare", "label": "Target share", "unit": "%"},
    {"key": "airYardsShare", "label": "Air yards share", "unit": "%"},
    {"key": "wopr", "label": "WOPR", "unit": ""},
    {"key": "adot", "label": "aDOT", "unit": "yd"},
    {"key": "yac", "label": "YAC", "unit": "yd"},
]

_UNAVAILABLE_WORDS = re.compile(
    r"\b(first read|yards per route run|yprr|route participation|route tree|"
    r"target heatmap|routes run)\b", re.I)


# ────────────────────────────── the structures ───────────────────────────────

@dataclass(frozen=True)
class Fact:
    """One number and where it came from.

    `source` is a location, not a description: a table name, or a module
    function. It is what makes an insight arguable rather than merely
    assertive, so it is required.
    """

    label: str
    value: Any
    unit: str = ""
    source: str = ""

    def __post_init__(self) -> None:
        if not self.source:
            raise ValueError(f"fact {self.label!r} has no source")

    def as_dict(self) -> dict:
        return {"label": self.label, "value": self.value,
                "unit": self.unit, "source": self.source}


@dataclass
class Insight:
    """One computed finding.

    `weight` is a priority in 0..1 used only for ordering; it is not a
    confidence and clients should not render it as one.
    """

    key: str
    kind: str
    title: str
    detail: str
    caveat: str
    facts: list[Fact] = field(default_factory=list)
    league: str = ""
    league_id: str = ""
    weight: float = 0.0
    players: list[dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        # Both of these have been the shape of a real regression elsewhere in
        # this project: an analysis that returned rows with an empty caveat,
        # and a headline assembled from numbers that were no longer in the
        # payload beneath it. Refusing to construct is cheaper than a test
        # that only catches it on the paths the test happens to walk.
        if not self.caveat:
            raise ValueError(f"insight {self.key!r} has no caveat")
        if not self.facts:
            raise ValueError(f"insight {self.key!r} carries no facts")

    @property
    def origin(self) -> str:
        """Always "computed". A property rather than a field so that no caller,
        and no round-trip through a dict, can dress model prose as arithmetic."""
        return "computed"

    @property
    def sources(self) -> list[str]:
        return sorted({f.source for f in self.facts})

    def as_dict(self) -> dict:
        return {
            "key": self.key, "kind": self.kind, "title": self.title,
            "detail": self.detail, "caveat": self.caveat,
            "origin": self.origin, "sources": self.sources,
            "facts": [f.as_dict() for f in self.facts],
            "league": self.league, "leagueId": self.league_id,
            "weight": round(self.weight, 4), "players": self.players,
        }


@dataclass
class Brief:
    """Everything the Intel view shows, with the model kept in its own box.

    `narration` is deliberately a sibling of `insights` rather than a field on
    each one. A client that renders only `insights` is correct and complete; a
    client that renders `narration` has to reach for a different key to get it,
    which is the point.
    """

    season: int = 0
    week: int = 0
    insights: list[Insight] = field(default_factory=list)
    narration: Any = None                     # ai.Narration | None
    unavailable: list[dict] = field(default_factory=lambda: list(UNAVAILABLE))
    available: list[dict] = field(default_factory=lambda: list(AVAILABLE_OPPORTUNITY))
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "season": self.season, "week": self.week,
            "insights": [i.as_dict() for i in self.insights],
            "narration": self.narration.as_dict() if self.narration else None,
            "unavailable": self.unavailable,
            "available": self.available,
            "notes": self.notes,
            "counts": {"computed": len(self.insights),
                       "model": 1 if self.narration else 0},
        }


# ─────────────────────────────── small helpers ───────────────────────────────

def _num(v, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _starters(league: dict, side: str) -> list[dict]:
    return list((league.get(side) or {}).get("starters") or [])


def cells_for(league: dict, live: dict | None) -> list[leverage.Cell]:
    """Turn one mosaic league plus the shared live snapshot into leverage cells.

    The mosaic payload deliberately carries no scores - it is the personal,
    slow-moving half and caches on a different clock - so the scored total and
    the fraction of each game remaining have to come from the live snapshot and
    be joined here. A player the snapshot has never heard of is treated as
    not yet kicked off rather than as zero-and-finished, because the opposite
    default silently declares the week over the moment a feed is unavailable.
    """
    players = (live or {}).get("players") or {}
    cells: list[leverage.Cell] = []
    for side in ("you", "opp"):
        for p in _starters(league, side):
            st = players.get(str(p.get("id"))) or {}
            cells.append(leverage.Cell(
                id=f'{side}:{p.get("id")}',
                label=p.get("name") or "?",
                pos=(p.get("pos") or "").upper(),
                team=p.get("team") or "",
                side=side,
                scored=_num(st.get("s")),
                projected=_num(p.get("projected")),
                remaining=_num(st.get("r"), 1.0),
                state=st.get("g") or "",
            ))
    return cells


def _player_ref(p: dict) -> dict:
    return {"id": str(p.get("id")), "name": p.get("name") or "?",
            "pos": p.get("pos") or "", "team": p.get("team") or ""}


LEVERAGE_CAVEAT = (
    "Win probability comes from the leverage model in leverage.py, which "
    "treats each player's remaining points as independent and draws their "
    "spread from a fixed per-position table rather than from this player's own "
    "history. It is a well-calibrated way to size what still matters, not a "
    "forecast of the final score."
)


# ───────────────────────────── matchup insights ──────────────────────────────

def matchup_insights(league: dict, live: dict | None) -> list[Insight]:
    """Who is carrying this week, and whether the lead survives the night."""
    cells = cells_for(league, live)
    if not cells:
        return []
    m = leverage.evaluate(cells)
    lid = str(league.get("id") or "")
    lname = str(league.get("league") or lid)
    you = [c for c in cells if c.side == "you"]
    opp = [c for c in cells if c.side == "opp"]
    out: list[Insight] = []

    scored_you = sum(c.scored for c in you)

    # 1. Carrying the matchup. Only meaningful once somebody has scored:
    # before kickoff every share is a share of zero, and the top "carrier"
    # would be whoever happens to sort first.
    if m.phase != "pre" and scored_you > 0:
        top = max(you, key=lambda c: c.scored)
        share = 100.0 * top.scored / scored_you
        if share >= 25.0:
            out.append(Insight(
                key=f"carry:{lid}",
                kind="carrying",
                title=f"{top.label} is carrying {lname}",
                detail=(f"{top.label} has {top.scored:.1f} of your "
                        f"{scored_you:.1f} points, {share:.0f}% of everything "
                        f"your line-up has scored this week."),
                caveat="Share of points already scored, not of the final total. "
                       "A team-mate whose game has not kicked off contributes "
                       "nothing to this denominator yet, so an early share "
                       "overstates how lopsided the week will finish.",
                facts=[
                    Fact(f"{top.label} scored", round(top.scored, 1), "pts",
                         "live snapshot joined to roster_slot"),
                    Fact("Your line-up scored", round(scored_you, 1), "pts",
                         "live snapshot joined to roster_slot"),
                    Fact("Share", round(share, 1), "%", "intel.matchup_insights"),
                    Fact("Game state", top.state or "pre", "", "live snapshot"),
                ],
                league=lname, league_id=lid,
                weight=min(1.0, share / 100.0 + 0.2),
                players=[{"id": top.id.split(":", 1)[-1], "name": top.label,
                          "pos": top.pos, "team": top.team}],
            ))

    # 2. A lead that is not safe. Ahead on expected final margin but the win
    # probability says the opponent still has the innings to take it back.
    # Both halves are needed: a big margin with nothing left to play is not
    # fragile, and a coin flip you are losing is not a lead.
    if m.phase == "live" and m.margin > 0 and m.win_prob < 0.85:
        opp_left = sum(c.sigma for c in opp)
        you_left = sum(c.sigma for c in you)
        yet = [c for c in opp if c.remaining > 0.999]
        out.append(Insight(
            key=f"fragile:{lid}",
            kind="fragility",
            title=f"Your lead in {lname} is not safe",
            detail=(f"You are {m.margin:.1f} ahead on expected final score but "
                    f"the model gives you {100 * m.win_prob:.0f}%. Your "
                    f"opponent still carries {opp_left:.1f} points of "
                    f"uncertainty against your {you_left:.1f}"
                    + (f", and {len(yet)} of their starters have not kicked off."
                       if yet else ".")),
            caveat=LEVERAGE_CAVEAT,
            facts=[
                Fact("Expected margin", round(m.margin, 1), "pts",
                     "leverage.evaluate"),
                Fact("Win probability", round(100 * m.win_prob), "%",
                     "leverage.evaluate"),
                Fact("Your remaining sigma", round(you_left, 1), "pts",
                     "leverage.sigma_for"),
                Fact("Opponent remaining sigma", round(opp_left, 1), "pts",
                     "leverage.sigma_for"),
                Fact("Their starters yet to play", len(yet), "",
                     "live snapshot"),
            ],
            league=lname, league_id=lid,
            weight=0.6 + 0.4 * m.intensity,
            players=[{"id": c.id.split(":", 1)[-1], "name": c.label,
                      "pos": c.pos, "team": c.team} for c in yet[:4]],
        ))

    # 3. One man left. The leverage model produces this honestly rather than by
    # special-casing the fourth quarter: late in a close game the total spread
    # is small, so whoever is still running owns most of the sensitivity.
    if m.phase == "live" and m.cells:
        live_cells = [c for c in m.cells if c.remaining > 0 and c.side in ("you", "opp")]
        if len(live_cells) == 1 and m.intensity > 0.3:
            c = live_cells[0]
            whose = "yours" if c.side == "you" else "your opponent's"
            out.append(Insight(
                key=f"last:{lid}",
                kind="decider",
                title=f"{c.label} decides {lname}",
                detail=(f"{c.label} is the only starter still playing and he is "
                        f"{whose}. Expected margin {m.margin:+.1f} with "
                        f"{c.sigma:.1f} points of spread left on the board."),
                caveat=LEVERAGE_CAVEAT,
                facts=[
                    Fact("Expected margin", round(m.margin, 1), "pts",
                         "leverage.evaluate"),
                    Fact("Win probability", round(100 * m.win_prob), "%",
                         "leverage.evaluate"),
                    Fact("His remaining spread", round(c.sigma, 1), "pts",
                         "leverage.sigma_for"),
                    Fact("He has scored", round(c.scored, 1), "pts",
                         "live snapshot"),
                ],
                league=lname, league_id=lid, weight=1.0,
                players=[{"id": c.id.split(":", 1)[-1], "name": c.label,
                          "pos": c.pos, "team": c.team}],
            ))

    # 4. Before kickoff there is no leverage to report - every player carries
    # identical uncertainty - so the honest pre-game line is about the priors
    # the database holds and the projected gap, not about a win probability
    # dressed up as news.
    if m.phase == "pre":
        gap = m.your_projected - m.opp_projected
        out.append(Insight(
            key=f"pregame:{lid}",
            kind="pregame",
            title=f"{lname}: projected {gap:+.1f}",
            detail=(f"Nothing has kicked off. Your starters project "
                    f"{m.your_projected:.1f} against {m.opp_projected:.1f}, a "
                    f"gap of {gap:+.1f} points."),
            caveat="Projections are the provider's own, stored with the roster "
                   "row. Before kickoff every player carries identical "
                   "uncertainty, so there is no leverage to rank by and this is "
                   "an expectation rather than a read on the week.",
            facts=[
                Fact("Your projected", round(m.your_projected, 1), "pts",
                     "roster_slot.projected"),
                Fact("Opponent projected", round(m.opp_projected, 1), "pts",
                     "roster_slot.projected"),
                Fact("Gap", round(gap, 1), "pts", "intel.matchup_insights"),
            ],
            league=lname, league_id=lid, weight=0.3,
        ))
    return out


# ────────────────────────── cross-league insights ────────────────────────────

def cross_league_insights(leagues: list[dict]) -> list[Insight]:
    """Where two of your leagues want opposite things from the same player.

    This is the one question a single-league view structurally cannot answer,
    and it is the reason the mosaic ships every league in one payload. A player
    you start in one league and face in another is not a rooting conflict in
    the abstract: it is a number, because his projection appears on both sides
    of your Sunday.
    """
    if len(leagues) < 2:
        return []

    mine: dict[str, list[tuple[dict, dict]]] = {}
    theirs: dict[str, list[tuple[dict, dict]]] = {}
    for L in leagues:
        for p in _starters(L, "you"):
            mine.setdefault(str(p.get("id")), []).append((L, p))
        for p in _starters(L, "opp"):
            theirs.setdefault(str(p.get("id")), []).append((L, p))

    out: list[Insight] = []
    for pid, for_you in sorted(mine.items()):
        against = theirs.get(pid)
        if not against:
            continue
        p = for_you[0][1]
        for_names = [str(L.get("league") or L.get("id")) for L, _ in for_you]
        vs_names = [str(L.get("league") or L.get("id")) for L, _ in against]
        for_pts = sum(_num(q.get("projected")) for _, q in for_you)
        vs_pts = sum(_num(q.get("projected")) for _, q in against)
        net = for_pts - vs_pts
        want = ("want him" if net > 0 else
                "want him quiet" if net < 0 else "are perfectly hedged on him")
        out.append(Insight(
            key=f"conflict:{pid}",
            kind="conflict",
            title=f"{p.get('name')} is on both sides of your Sunday",
            detail=(f"{p.get('name')} starts for you in "
                    f"{', '.join(for_names)} and against you in "
                    f"{', '.join(vs_names)}. That is {for_pts:.1f} projected "
                    f"points for you and {vs_pts:.1f} against, so on net you "
                    f"{want} by {abs(net):.1f}."),
            caveat="Projected points, not scored, and the two leagues may use "
                   "different scoring rules - the projection stored with each "
                   "roster row is that league's own. The net is a rough "
                   "direction of interest, not a transferable quantity.",
            facts=[
                Fact("Starting for you in", len(for_you), "leagues",
                     "roster_slot.started"),
                Fact("Starting against you in", len(against), "leagues",
                     "roster_slot.started"),
                Fact("Projected for you", round(for_pts, 1), "pts",
                     "roster_slot.projected"),
                Fact("Projected against you", round(vs_pts, 1), "pts",
                     "roster_slot.projected"),
            ],
            weight=min(1.0, 0.5 + abs(net) / 40.0),
            players=[_player_ref(p)],
        ))

    # Exposure: the same man in several of your line-ups is several times the
    # Sunday, in both directions. Worth saying only above two, since one league
    # is not exposure and everybody has a few doubles.
    for pid, entries in sorted(mine.items()):
        if len(entries) < 3 or pid in theirs:
            continue
        p = entries[0][1]
        names = [str(L.get("league") or L.get("id")) for L, _ in entries]
        total = sum(_num(q.get("projected")) for _, q in entries)
        out.append(Insight(
            key=f"exposure:{pid}",
            kind="exposure",
            title=f"{p.get('name')} starts in {len(entries)} of your line-ups",
            detail=(f"{p.get('name')} is in your starting line-up in "
                    f"{', '.join(names)}, {total:.1f} projected points of your "
                    f"Sunday riding on one player."),
            caveat="Projected points summed across leagues with possibly "
                   "different scoring rules. It measures how correlated your "
                   "week is, not how many points you will score.",
            facts=[
                Fact("Line-ups", len(entries), "", "roster_slot.started"),
                Fact("Total projected", round(total, 1), "pts",
                     "roster_slot.projected"),
            ],
            weight=min(1.0, 0.4 + 0.15 * len(entries)),
            players=[_player_ref(p)],
        ))
    return out


# ───────────────────────────── injury insights ───────────────────────────────

def injury_insights(injuries: Iterable[dict] | None) -> list[Insight]:
    """What the wire says about your men, priced in points you were counting on.

    `injuries.detect` has already done the hard part - classifying a story as
    being about a body rather than a box score, and attributing it only when
    the headline itself names the player - and has already attached the draft
    and line-up facts. This turns each one into the same shape as every other
    insight so the view does not need a special case for it, and so the roast
    it wrote travels with the numbers it was built from rather than alone.
    """
    out: list[Insight] = []
    order = {"out": 1.0, "doubtful": 0.85, "questionable": 0.65, "hurt": 0.5}
    for e in (injuries or []):
        pid = str(e.get("id"))
        proj = _num(e.get("projected"))
        lineups = int(e.get("lineups") or 0)
        facts = [
            Fact("Severity", e.get("label") or "", "",
                 "injuries.classify over the tagged news wire"),
            Fact("Line-ups he starts in", lineups, "",
                 "roster_slot.started"),
            Fact("Projected this week", round(proj, 1), "pts",
                 "roster_slot.projected"),
        ]
        picks = e.get("picks") or []
        if picks:
            facts.append(Fact("Drafted in your leagues", len(picks), "times",
                              "draft_pick"))
            reaches = [p["adp"] - p["overall"] for p in picks
                       if p.get("adp") is not None]
            if reaches:
                facts.append(Fact("Biggest reach on him", round(max(reaches)),
                                  "picks", "draft_pick joined to adp"))
        detail = (f"{e.get('name')} ({e.get('pos')}) is "
                  f"{(e.get('label') or '').lower()}"
                  + (f", and he is in {lineups} of your line-ups"
                     if lineups else "")
                  + (f" for {proj:.1f} projected points" if proj else "")
                  + ".")
        roast = (e.get("roast") or "").strip()
        if roast:
            detail = f"{detail} {roast}"
        out.append(Insight(
            key=f"injury:{pid}",
            kind="injury",
            title=f"{e.get('label')}: {e.get('name')}",
            detail=detail,
            caveat="Severity is classified from the wording of a news "
                   "headline, not read from an injury report - there is no "
                   "injury feed available here. It is written to be wrong in "
                   "the safe direction, so a story it cannot confidently call "
                   "an injury is not reported at all, which means this list "
                   "under-reports rather than over-reports.",
            facts=facts,
            weight=order.get(str(e.get("severity")), 0.4)
                   + min(0.3, proj / 100.0),
            players=[{"id": pid, "name": e.get("name") or "?",
                      "pos": e.get("pos") or "", "team": e.get("team") or ""}],
        ))
    return out


# ─────────────────────────── opportunity insights ────────────────────────────

# Above this many targets a game, or touches a game, a role is real rather than
# a small-sample accident. Below it the ratio swings wildly week to week and an
# "underused" finding is noise.
MIN_GAMES = 3
TARGET_SHARE_FLOOR = 20.0
TOUCHES_FLOOR = 14.0


def opportunity_insights(players: Iterable[dict],
                         opportunity: Callable[[str], dict] | None,
                         season: int | None = None) -> list[Insight]:
    """Men being given the ball more than their points suggest.

    Opportunity is the leading half of the pair: targets, carries and target
    share carry to next week far better than points do, so a quiet game on a
    heavy workload reads differently from a quiet game on three touches. This
    only reports the metrics nflverse actually publishes; see `UNAVAILABLE`
    for the ones the design asked for and no feed here can supply.

    `opportunity` is injected rather than imported so this runs without a
    network. It takes `(player_id, season)`. In production it is
    `profile.opportunity`, which returns {} for anyone not in the release - a
    rookie, or a player who has not taken a snap - and {} is treated as
    silence rather than as a zero.
    """
    if opportunity is None:
        return []
    out: list[Insight] = []
    for p in players:
        pid = str(p.get("id"))
        try:
            o = opportunity(pid, season)
        except Exception:
            # nflverse is a cached HTTP fetch. Its being unreachable is a
            # missing panel, never a failed brief. Catching broadly rather
            # than by type because the failure can arrive as a URLError, a
            # JSON error from a half-written cache file, or an OSError from
            # the cache directory, and the response to all three is the same.
            continue
        if not o:
            continue
        games = int(o.get("games") or 0)
        if games < MIN_GAMES:
            continue
        pos = (p.get("pos") or "").upper()
        ppg = _num(o.get("ppg"))
        share = _num(o.get("targetShare"))
        touches = (_num(o.get("targets")) + _num(o.get("carries"))) / max(games, 1)

        facts = [Fact("Games", games, "", "nflverse via advanced.season_profiles")]
        for key, label, unit in (("targets", "Targets", ""),
                                 ("carries", "Carries", ""),
                                 ("targetShare", "Target share", "%"),
                                 ("airYardsShare", "Air yards share", "%"),
                                 ("wopr", "WOPR", ""),
                                 ("adot", "aDOT", "yd"),
                                 ("yac", "YAC", "yd"),
                                 ("ppg", "Fantasy points a game", "")):
            if o.get(key) is not None:
                facts.append(Fact(label, o[key], unit,
                                  "nflverse via advanced.season_profiles"))

        if pos in ("WR", "TE") and share >= TARGET_SHARE_FLOOR and ppg < 12.0:
            body = (f"{p.get('name')} is seeing {share:.1f}% of his team's "
                    f"targets over {games} games and returning {ppg:.1f} points "
                    f"a game. The role is there; the production has not "
                    f"followed it yet.")
        elif pos == "RB" and touches >= TOUCHES_FLOOR and ppg < 12.0:
            body = (f"{p.get('name')} is getting {touches:.1f} touches a game "
                    f"over {games} games for {ppg:.1f} points a game. That is "
                    f"volume without the finish.")
        else:
            continue

        adot = o.get("adot")
        if adot is not None and pos in ("WR", "TE"):
            body += f" His average target is {_num(adot):.1f} yards downfield."
        out.append(Insight(
            key=f"opportunity:{pid}",
            kind="opportunity",
            title=f"{p.get('name')}: role ahead of production",
            detail=body,
            caveat="nflverse opportunity metrics for the season named in the "
                   "facts, which is not necessarily the current week and is "
                   "league-neutral - it does not know your scoring rules. "
                   "Volume predicts points better than points predict points, "
                   "but it is a tendency across a population, not a promise "
                   "about this player.",
            facts=facts,
            weight=min(1.0, 0.35 + share / 100.0 + touches / 60.0),
            players=[_player_ref(p)],
        ))
    return out


# ──────────────────────────── history insights ───────────────────────────────

# The analyses worth surfacing next to a live week. The rest are draft-season
# questions and belong on a different screen; carrying all nine here would bury
# the three that bear on Sunday.
HISTORY_KEYS = ("bench", "luck", "projection_accuracy")


def history_insights(analyses: Iterable[Any], you: str = "",
                     league: str = "", league_id: str = "") -> list[Insight]:
    """The standing analyses, narrowed to your row, caveat intact.

    The caveat is copied verbatim from the analysis rather than restated. A
    paraphrase is a second chance to lose the qualification, and the whole
    reason `analytics.Result` carries one is that the number is not safe
    without it.
    """
    out: list[Insight] = []
    target = (you or "").strip().casefold()
    for a in (analyses or []):
        d = a if isinstance(a, dict) else {
            "key": a.key, "title": a.title, "headline": a.headline,
            "columns": a.columns, "rows": a.rows, "caveat": a.caveat,
            "empty": a.empty}
        if d.get("key") not in HISTORY_KEYS or d.get("empty"):
            continue
        cols = d.get("columns") or []
        rows = d.get("rows") or []
        mine = next((r for r in rows
                     if target and str(r[0]).strip().casefold() == target), None)
        row = mine if mine is not None else (rows[0] if rows else None)
        if row is None:
            continue
        facts = [Fact(str(c), v, "", f"analytics.{d['key']}")
                 for c, v in zip(cols, row)]
        if not facts:
            continue
        whose = "You" if mine is not None else str(row[0])
        detail = d.get("headline") or ""
        if mine is not None and d["key"] == "bench":
            detail = (f"{whose} have left {row[-1]}% of available points on the "
                      f"bench across {row[1]} team-weeks.")
        elif mine is not None and d["key"] == "luck":
            detail = (f"{whose} are {row[1]} against an all-play win rate of "
                      f"{row[3]}, which is {row[-1]:+} points of win "
                      f"percentage of schedule luck.")
        if not detail:
            continue
        out.append(Insight(
            key=f"history:{d['key']}:{league_id}",
            kind="history",
            title=d.get("title") or d["key"],
            detail=detail,
            caveat=d.get("caveat") or "",
            facts=facts,
            league=league, league_id=league_id,
            weight=0.35 if mine is not None else 0.2,
        ))
    return out


# ──────────────────────────────── assembly ───────────────────────────────────

def build(*, mosaics: dict | None = None,
          live: dict | None = None,
          injuries: Iterable[dict] | None = None,
          analyses: dict[str, Any] | None = None,
          opportunity: Callable[..., dict] | None = None,
          season: int | None = None,
          limit: int = 12) -> Brief:
    """The whole strict-compute brief. No I/O, no credentials, no model.

    Every argument is a payload the API has already built and cached, which is
    what keeps this function pure: the same call runs against a fixture in a
    test and against a live Sunday in production, and neither path can reach
    the network from in here.

    `analyses` maps a league id (`"espn-12345"`) to that league's list of
    analysis dicts, exactly as `/api/leagues/{p}/{id}/analyses` returns them.
    """
    leagues = list((mosaics or {}).get("leagues") or [])
    insights: list[Insight] = []
    notes: list[str] = []

    for L in leagues:
        insights.extend(matchup_insights(L, live))
        lid = str(L.get("id") or "")
        insights.extend(history_insights(
            (analyses or {}).get(lid) or [],
            you=(L.get("you") or {}).get("name") or "",
            league=str(L.get("league") or lid), league_id=lid))

    insights.extend(cross_league_insights(leagues))
    insights.extend(injury_insights(injuries))

    if opportunity is not None:
        # Your own starters only. Running this over every rostered player in
        # four leagues is a few hundred lookups for insights about men you are
        # not playing.
        seen: dict[str, dict] = {}
        for L in leagues:
            for p in _starters(L, "you"):
                seen.setdefault(str(p.get("id")), p)
        insights.extend(opportunity_insights(
            seen.values(), opportunity,
            season if season is not None else (leagues[0].get("season")
                                               if leagues else None)))
    else:
        notes.append("Opportunity metrics were not requested, so no usage "
                     "insight was computed.")

    if not leagues:
        notes.append("No league has both rosters and a matchup stored, so "
                     "there is nothing to compute a brief from.")
    if live is None:
        notes.append("No live snapshot was supplied, so every game is treated "
                     "as not yet kicked off.")

    insights.sort(key=lambda i: (-i.weight, i.key))
    week = int(leagues[0].get("week") or 0) if leagues else 0
    yr = int(season if season is not None
             else (leagues[0].get("season") if leagues else 0) or 0)
    return Brief(season=yr, week=week, insights=insights[:limit], notes=notes)


# ───────────────────────── the handoff to a model ────────────────────────────

def as_prompt_facts(brief: Brief) -> list[dict]:
    """The brief flattened to exactly what a model is allowed to see.

    Only the computed findings, their facts and their caveats: no roster, no
    ids, no league identifiers beyond a display name. A narrator that is given
    only the facts can only get the emphasis wrong, which is a recoverable
    failure. A narrator handed the raw payload can find a number nobody
    computed and put it in a sentence, which is not.
    """
    return [{
        "id": i.key, "kind": i.kind, "league": i.league,
        "finding": i.detail, "caveat": i.caveat,
        "numbers": {f.label: f"{f.value}{(' ' + f.unit) if f.unit else ''}"
                    for f in i.facts},
    } for i in brief.insights]


def allowed_numbers(brief: Brief) -> set[str]:
    """Every numeric token a narrator could legitimately repeat.

    Used by `ai.verify_numbers` to flag prose that introduced a figure nobody
    computed. Deliberately generous - it includes the rounded and unrounded
    forms and any number already appearing in a finding or a caveat - because
    the check is meant to catch invention, and a false alarm on a number that
    was in fact supplied would train a reader to ignore the flag.
    """
    tokens: set[str] = set()

    def add(v) -> None:
        if isinstance(v, bool) or v is None:
            return
        if isinstance(v, (int, float)):
            if isinstance(v, float) and not math.isfinite(v):
                return
            tokens.add(f"{v:g}")
            tokens.add(f"{round(v):g}")
            tokens.add(f"{abs(v):g}")
            tokens.add(f"{round(abs(v)):g}")
            tokens.add(f"{v:.1f}".lstrip("+"))
            tokens.add(f"{abs(v):.1f}")
        else:
            for tok in re.findall(r"\d+(?:\.\d+)?", str(v)):
                tokens.add(f"{float(tok):g}")

    for i in brief.insights:
        for f in i.facts:
            add(f.value)
        for text in (i.detail, i.caveat, i.title):
            for tok in re.findall(r"\d+(?:\.\d+)?", text):
                add(float(tok))
    return tokens


def mentions_unavailable(text: str) -> list[str]:
    """Metrics from the design that no feed here can source, if prose used one.

    A model asked to sound like a scouting report will reach for yards per
    route run whether or not it was given one, because that is what scouting
    reports say. Naming the offence is cheaper than hoping.
    """
    return sorted({m.lower() for m in _UNAVAILABLE_WORDS.findall(text or "")})
