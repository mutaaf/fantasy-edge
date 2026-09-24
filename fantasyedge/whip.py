"""Which game deserves the screen right now, and when to leave it.

A red-zone channel answers a question a scoreboard never asks: of sixteen
games running at once, which one should a viewer be looking at *this second*?
That has to be a number, or the page cannot choose.

Urgency is built from what the scoreboard already knows - nothing here needs a
play-by-play call, because asking sixteen games for their drives every few
seconds is how an address gets blocked (see `live.EspnLiveSource`). Four
things move it:

  * **Proximity.** A first-and-goal at the four is the whole point of the
    channel. Urgency rises as the ball nears the goal line, and rises again
    inside the ten, because that is where a drive turns into points.
  * **Consequence.** A snap matters more when the game is close, and a close
    game matters more late. A three-score game in the first quarter is a
    highlight, not a destination.
  * **Down.** Fourth down is a decision; first and goal is an expectation.
    Third and long from the eighteen is more interesting than first and ten.
  * **Aftermath.** A score just happened is worth watching for a few seconds
    even though the ball is now on a kicking tee.

Deliberately pure: plain numbers in, plain numbers out, no I/O and no clock of
its own. The same arithmetic runs on the server to pick the shared focus and
in the browser to sort the grid, and the two agree because it is the same
twenty lines - the arrangement `leverage.py` already uses for tile size.

The hysteresis in `choose` is the difference between a channel and a strobe.
Two games in the red zone at once will trade the lead every poll if the rule
is "show the highest number", so a challenger has to be meaningfully better
*and* the incumbent has to have had its moment.
"""

from __future__ import annotations

# A challenger must beat the game on screen by this much before the view
# moves. Roughly "clearly more interesting", not "a rounding place better".
SWITCH_MARGIN = 12.0

# ...unless the game on screen has gone quiet, in which case a smaller
# difference is enough to leave. A team that just punted is not worth holding.
QUIET = 25.0

# The shortest a game may hold the screen, in seconds. A viewer needs long
# enough to read the score and see a snap; below about six seconds a channel
# reads as a slideshow rather than as coverage.
#
# This is the *page's* figure, and it is the default because the page is what
# `choose` was written for. A surface that costs more to leave passes its own:
# the stadium fades the whole world out and back to change games, and a wearer
# standing in a bowl cannot be moved at the rate a tile on a grid can.
MIN_DWELL = 6.0

# How long a score keeps its game on screen afterwards, in seconds. Long
# enough to see the celebration and the replay ESPN is showing, not so long
# that the channel sits on a kickoff while a drive stalls elsewhere.
SCORE_HOLD = 12.0


def scoring_play(points: float) -> str:
    """What a jump in a club's score must have been, named conservatively.

    Only the scoreboard is consulted, so this says what the arithmetic
    supports and nothing more. Seven is the trap: a touchdown and its extra
    point usually land in the same poll, and a channel that reads the total
    as an extra point announces the wrong thing on the biggest play of the
    drive - the same mistake the Saturday recorder made and had pinned by a
    test. Six through eight are therefore all touchdowns.

    Two is left ambiguous on purpose: a safety and a two-point conversion are
    both two, and the scoreboard cannot tell them apart.
    """
    p = int(round(points))
    if p >= 6:
        return "Touchdown"                      # 6, 7 with the kick, 8 with two
    if p == 3:
        return "Field goal"
    if p == 2:
        return "2 points"                       # safety or a conversion
    if p == 1:
        return "Extra point"
    if p > 0:
        return f"{p} points"
    return ""


def _num(value, default=0.0) -> float:
    """ESPN sends scores as strings and absent fields as null."""
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def ordinal(n: int) -> str:
    return {1: "1st", 2: "2nd", 3: "3rd", 4: "4th"}.get(int(n), f"{int(n)}th")


def has_down(game: dict) -> bool:
    """Whether a down is actually being played.

    ESPN uses 0 and -1 for "no down" - between plays, on a kickoff, at a
    change of possession - and both appear often: over one Saturday's boards
    they were a quarter of all live situations. Treating them as numbers puts
    "0th & 10" on screen; treating only 0 as absent still lets -1 through.
    """
    down = game.get("down")
    try:
        return down is not None and 1 <= int(down) <= 4
    except (TypeError, ValueError):
        return False


def situation(game: dict) -> str:
    """The down and distance as a human would say it, or "" when there is none.

    Prefers ESPN's own wording, which names the yard line - "1st & 10 at
    OU 25" - and is the only form that says *where* the ball is, because
    `yardsToEndzone` was absent from every live situation across a full
    Saturday. Composing from down and distance is the fallback, and it can
    only say "1st & 10", never where.
    """
    text = (game.get("downDistanceText") or "").strip()
    if text:
        return text
    if not has_down(game):
        return ""
    down, dist = game.get("down"), game.get("distance")
    to_ez = game.get("toEndzone")
    goal_to_go = to_ez is not None and dist is not None and _num(dist) >= _num(to_ez)
    where = f" at the {int(_num(to_ez))}" if to_ez is not None else ""
    if goal_to_go:
        return f"{ordinal(down)} & goal{where}"
    if dist is None:
        return f"{ordinal(down)} down{where}"
    return f"{ordinal(down)} & {int(_num(dist))}{where}"


def urgency(game: dict, *, scored_ago: float | None = None) -> tuple[float, str]:
    """How much this game deserves the screen, 0..100, and why.

    The reason is returned beside the number because a channel that cuts
    without saying why reads as random. It is the same string a caption shows.
    """
    state = game.get("state") or "pre"
    if state == "pre":
        return 0.0, "not started"
    if state == "post":
        return 0.0, "final"

    to_ez = game.get("toEndzone")
    down = game.get("down")
    home = _num(game.get("homeScore"))
    away = _num(game.get("awayScore"))
    margin = abs(home - away)
    played = _num(game.get("played"))          # 0..1 through the game

    score = 10.0
    # A category rather than the clock: the clock is already on screen beside
    # this, and a channel whose caption restates it has said nothing.
    reason = "in progress"

    # Proximity. Nothing else on this list moves the number as much, because
    # nothing else is as likely to become points in the next thirty seconds.
    #
    # `isRedZone` is the signal, not a distance we derive: ESPN sends the flag
    # on every live situation and `yardsToEndzone` on none of them in the
    # college feed, so a channel built on the distance alone never fires. The
    # distance refines the number when it happens to be there.
    if game.get("redZone"):
        score += 40.0
        # A category, not the down: the caption beside this already prints
        # "4th & 7 at MOST 14", and a panel that says it twice reads as a bug.
        reason = "in the red zone"
        if to_ez is not None:
            # Inside the flag, nearer is better: the goal line adds a further
            # 15, the twenty adds nothing, and the curve between is steep,
            # because the difference between the 18 and the 4 is not four
            # fifths of anything - it is most of the drama.
            yards = max(0.0, min(20.0, _num(to_ez)))
            score += 15.0 * ((20.0 - yards) / 20.0) ** 1.6
    elif to_ez is not None and _num(to_ez) <= 35:
        score += 8.0                            # knocking on the door
        reason = "closing in"

    # Down. A fourth down is a decision being made on camera.
    if has_down(game):
        d = int(_num(down))
        if d == 4:
            score += 12.0
            if game.get("redZone") or (to_ez is not None and _num(to_ez) <= 40):
                score += 6.0                    # fourth down in range
            if not game.get("redZone"):
                reason = "fourth down"
        elif d == 3:
            score += 6.0

    # Consequence: close games, and lateness multiplying closeness. A tie in
    # the fourth is the most interesting ordinary snap in football.
    if margin <= 8:
        score += 10.0 * (1.0 - margin / 8.0) * (0.4 + 0.6 * played)
    elif margin >= 21:
        score -= 8.0 * played                   # a blowout empties out late

    if played >= 0.75 and margin <= 8:
        score += 8.0
        if reason == "in progress":
            reason = "one score, late"

    # Aftermath. Something just happened here; stay a moment.
    if scored_ago is not None and scored_ago <= SCORE_HOLD:
        score += 30.0 * (1.0 - scored_ago / SCORE_HOLD)
        reason = "just scored"

    return max(0.0, min(100.0, score)), reason


def rank(games: list[dict], *, scored: dict | None = None,
         now: float = 0.0) -> list[dict]:
    """Every game with its urgency and reason, most urgent first.

    `scored` maps event id to the timestamp of its last scoring change, so a
    touchdown can hold its game on screen. Sorting is stable on event id so
    two equal games do not swap places between polls for no reason.
    """
    scored = scored or {}
    out = []
    for g in games:
        ago = None
        when = scored.get(g.get("event"))
        if when:
            ago = max(0.0, now - when)
        value, why = urgency(g, scored_ago=ago)
        out.append({**g, "urgency": round(value, 2), "reason": why})
    out.sort(key=lambda g: (-g["urgency"], g.get("event") or ""))
    return out


def choose(ranked: list[dict], current: str = "", *, held: float = 0.0,
           dwell: float = MIN_DWELL, margin: float = SWITCH_MARGIN,
           quiet: float = QUIET) -> str:
    """Which game the channel should be on, given the one it is already on.

    Hysteresis rather than "highest wins", because two red-zone drives at once
    would otherwise swap the screen every poll and show neither. The incumbent
    keeps the screen until it has had `dwell` seconds *and* a challenger is
    clearly better - or until it has gone quiet enough that anything beats it.

    `dwell`, `margin` and `quiet` are the caller's, because they belong to the surface
    and to the scale of the numbers, not to this arithmetic. A page changing a
    tile and a stadium fading the whole world out are not the same act, and an
    urgency out of `urgency` and one out of `cfb.leverage` are not the same
    units. The defaults are the red-zone page's, which is what this was
    written for.
    """
    # Only a game in progress may hold the screen. Ranking alone would put a
    # final on it before kickoff, since everything is zero and something has
    # to sort first - and a channel opening on a game that finished on
    # Thursday is worse than one that says nothing is running yet.
    live_games = [g for g in ranked if (g.get("state") or "") == "in"]
    if not live_games:
        return ""
    best = live_games[0]
    if not current:
        return best.get("event") or ""

    incumbent = next((g for g in live_games if g.get("event") == current), None)
    # The game on screen ended or vanished from the slate: move immediately.
    if incumbent is None:
        return best.get("event") or ""
    if best.get("event") == current:
        return current
    if held < dwell:
        return current

    gap = best["urgency"] - incumbent["urgency"]
    need = margin if incumbent["urgency"] >= quiet else margin / 2
    return best.get("event") if gap >= need else current


def slate(games: dict, *, colors=None) -> list[dict]:
    """Per-event rows from `live.EspnLiveSource.games()`, which is per club.

    The live tier keys game state by club abbreviation because a fantasy
    roster asks "what is my running back's game doing". A channel asks the
    opposite question - "what are the games doing" - so this regroups without
    refetching anything.

    `league` rides along on each row rather than being assumed here: the same
    page has to work for a Sunday and for a college Saturday, and a constant
    written into this module is exactly how that breaks.
    """
    colors = colors or (lambda ab: "")
    by_event: dict[str, dict] = {}
    for abbr, info in (games or {}).items():
        event = info.get("event") or ""
        if not event:
            continue
        row = by_event.setdefault(event, {
            "event": event, "state": info.get("state") or "pre",
            "label": info.get("label") or "", "kickoff": info.get("kickoff") or "",
            "played": info.get("played") or 0.0,
            "league": info.get("league") or "",
            "possession": info.get("possession") or "",
            "down": info.get("down"), "distance": info.get("distance"),
            "toEndzone": info.get("toEndzone"),
            "downDistanceText": info.get("downDistanceText"),
            "redZone": bool(info.get("redZone")),
            "home": None, "away": None,
        })
        side = {"abbr": abbr, "score": _num(info.get("score")),
                "color": colors(abbr),
                "hasBall": info.get("possession") == abbr}
        row["home" if info.get("home") else "away"] = side

    out = []
    for row in by_event.values():
        # A club whose opponent is missing from the slate is not a game. This
        # is defensive rather than theoretical: a club on a bye appears in the
        # per-club map with no event at all, and a half-parsed event would
        # otherwise reach the page as a tile with one team in it.
        if not row["home"] or not row["away"]:
            continue
        row["homeScore"] = row["home"]["score"]
        row["awayScore"] = row["away"]["score"]
        row["situation"] = situation(row)
        out.append(row)
    out.sort(key=lambda r: (r.get("kickoff") or "", r["event"]))
    return out
