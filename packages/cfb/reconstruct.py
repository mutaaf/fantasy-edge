"""A night rebuilt from play wallclocks, and honest about being a rebuild.

ESPN stamps every play with the instant it happened, so a game's summary is
not only its final state: it is a timeline. Given the summaries and a
reference board for the things a play does not carry - teams, venue, network,
rank - this builds the board as it stood at any moment the plays cover.

A reconstruction is not a recording, and says so. Every board this module
writes carries `provenance: "reconstructed"`, every game it rebuilt carries
its own, and `CAVEATS` travels with it in the manifest. A game that had not
kicked off keeps the schedule's own words and is marked `"schedule"`.

WHAT A PLAY GIVES: the period, the game clock, both scores after it, where the
ball ended, and - from the next play's start - the down, distance and
possession while the offence stood over the ball.

WHAT IT CANNOT: see the module's CAVEATS.
"""
from __future__ import annotations

import copy
import datetime as dt

from . import parse

CAVEATS = [
    "A score ESPN corrected and then corrected back leaves no trace: only the version in the "
    "summary survives, so a tile that flickered up and down reads as one clean change.",
    "A weather or lightning delay that started and ended is not in a summary. Its effect shows "
    "only as a gap between plays, and it is not drawn as a delay.",
    "The status ESPN published minute by minute is gone. Halftime here is inferred from the gap "
    "between the last play of one period and the first of the next, not read from a board.",
    "Down, distance and possession between plays come from the next play's start. After the last "
    "play of a period, or at the moment a reconstruction ends, there is no next play and no ball "
    "is drawn.",
    "Win probability is ESPN's, keyed to plays, so it moves with them and not with the clock.",
    "A game that never kicked off has no plays, so its tile is the schedule, not a reconstruction.",
    "A rebuilt board carries the slate it rebuilt - the Saturday and its Friday - so a game from "
    "earlier in the week is absent rather than shown in a state nobody here recorded.",
    "Wallclocks are ESPN's and a few are wrong - one Buffalo-Penn State play is stamped two hours "
    "after the game ended. ESPN's play order is trusted over its stamps: the stamps that agree with "
    "the order are kept and the rest are placed evenly between their neighbours, so a handful of "
    "plays (mostly timeouts) sit a few seconds from where they really were.",
]

# Between the last play of a period and the first of the next, the game is at a
# break. Only the one after the second period is halftime.
HALFTIME_AFTER = 2


def stamp_to_dt(stamp: str) -> dt.datetime:
    return dt.datetime.strptime(stamp[:16], "%Y%m%dT%H%M%SZ").replace(tzinfo=dt.timezone.utc)


def dt_to_stamp(when: dt.datetime) -> str:
    return when.astimezone(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _when(play: dict) -> dt.datetime | None:
    raw = play.get("wallclock")
    if not raw:
        return None
    try:
        return dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _monotone(times: list[dt.datetime | None]) -> list[dt.datetime | None]:
    """Keep the longest non-decreasing run of stamps and interpolate the rest.

    ESPN's play order is the real sequence; its wallclocks are per play and a
    few are simply wrong - Buffalo at Penn State carries a third-quarter play
    stamped two hours after the game ended. Sorting by them reorders a game
    around its worst stamp, so instead the stamps that agree with the order
    are kept (a longest non-decreasing subsequence) and each disagreeing play
    is placed evenly between its neighbours.
    """
    known = [(i, t) for i, t in enumerate(times) if t]
    if not known:
        return list(times)
    # longest non-decreasing subsequence over the known stamps, by patience
    tails: list[int] = []            # positions in `known` of each tail
    back: list[int | None] = [None] * len(known)
    for k, (_, t) in enumerate(known):
        lo, hi = 0, len(tails)
        while lo < hi:                 # first tail strictly greater than t
            mid = (lo + hi) // 2
            if known[tails[mid]][1] <= t:
                lo = mid + 1
            else:
                hi = mid
        back[k] = tails[lo - 1] if lo else None
        if lo == len(tails):
            tails.append(k)
        else:
            tails[lo] = k
    keep: list[int] = []
    cursor: int | None = tails[-1] if tails else None
    while cursor is not None:
        keep.append(cursor)
        cursor = back[cursor]
    trusted = {known[k][0]: known[k][1] for k in reversed(keep)}

    out: list[dt.datetime | None] = [trusted.get(i) for i in range(len(times))]
    anchors = sorted(trusted)
    for gap_start, gap_end in zip([None] + anchors, anchors + [None]):
        lo = gap_start + 1 if gap_start is not None else 0
        hi = gap_end if gap_end is not None else len(times)
        span = hi - lo
        if span <= 0:
            continue
        if gap_start is None:                       # before the first trusted stamp
            for i in range(lo, hi):
                out[i] = trusted[anchors[0]]
        elif gap_end is None:                       # after the last
            for i in range(lo, hi):
                out[i] = trusted[anchors[-1]]
        else:
            a, b = trusted[gap_start], trusted[gap_end]
            step = (b - a) / (span + 1)
            for n, i in enumerate(range(lo, hi), start=1):
                out[i] = a + step * n
    return out


def timed_plays(summary: dict) -> list[tuple[dt.datetime, dict]]:
    """Every play with the instant it happened, in ESPN's own order.

    ESPN lists the drive in progress in both `previous` and `current`; keyed on
    play id each play appears once. The order is ESPN's; the times are made
    non-decreasing by `_monotone`, which is where the bad stamps are handled.
    """
    drives = (summary.get("drives") or {})
    seen: dict[str, dict] = {}
    for drive in (drives.get("previous") or []) + ([drives["current"]] if drives.get("current") else []):
        for play in drive.get("plays") or []:
            seen[str(play.get("id") or len(seen))] = play
    plays = list(seen.values())
    stamps = _monotone([_when(p) for p in plays])
    return [(t, p) for t, p in zip(stamps, plays) if t]


def covered_span(summaries: dict[str, dict]) -> tuple[dt.datetime, dt.datetime] | None:
    """First and last instant any play in any summary happened."""
    times = [w for summary in summaries.values() for w, _ in timed_plays(summary)]
    return (min(times), max(times)) if times else None


def _score(play: dict, side: str) -> int:
    value = play.get(f"{side}Score")
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _period(play: dict) -> int:
    return int((play.get("period") or {}).get("number") or 0)


def game_at(event: dict, summary: dict, when: dt.datetime) -> dict:
    """The reference event, rewritten to how that game stood at `when`.

    Returns an ESPN-shaped event, so everything downstream - parse, the
    handlers, the contracts, the app - reads it exactly as it reads a recorded
    board. It carries `saturdayProvenance` so nothing can mistake it for one.
    """
    plays = timed_plays(summary)
    out = copy.deepcopy(event)
    comp = (out.get("competitions") or [{}])[0]
    status = out.setdefault("status", {})
    kind = status.setdefault("type", {})

    played = [(w, p) for w, p in plays if w <= when]
    if not played:
        out["saturdayProvenance"] = "schedule"        # it had not kicked off yet
        comp.pop("situation", None)
        for side in comp.get("competitors") or []:
            side["score"] = "0"
        kind.update({"name": "STATUS_SCHEDULED", "state": "pre", "completed": False,
                     "description": "Scheduled"})
        status.update({"period": 0, "clock": 0.0, "displayClock": "0:00"})
        return out

    out["saturdayProvenance"] = "reconstructed"
    last_when, last = played[-1]
    following = plays[len(played)] if len(plays) > len(played) else None
    home, away = _score(last, "home"), _score(last, "away")
    period = _period(last)
    clock = (last.get("clock") or {}).get("displayValue") or "0:00"

    header_status = (((summary.get("header") or {}).get("competitions") or [{}])[0].get("status") or {})
    header_kind = header_status.get("type") or {}
    ended = bool(header_kind.get("completed")) and following is None
    between = following is not None and _period(following[1]) > period

    if ended:
        detail = header_kind.get("shortDetail") or "Final"
        kind.update({"name": header_kind.get("name") or "STATUS_FINAL", "state": "post", "completed": True,
                     "description": header_kind.get("description") or "Final",
                     "detail": header_kind.get("detail") or detail, "shortDetail": detail})
        status.update({"period": period, "clock": 0.0, "displayClock": "0:00"})
    elif between and period == HALFTIME_AFTER:
        kind.update({"name": "STATUS_HALFTIME", "state": "in", "completed": False,
                     "description": "Halftime", "detail": "Halftime", "shortDetail": "Halftime"})
        status.update({"period": period, "clock": 0.0, "displayClock": "0:00"})
    else:
        shown = f"{clock} - {['', '1st', '2nd', '3rd', '4th'][period] if 0 < period < 5 else f'OT{period - 4}'}"
        kind.update({"name": "STATUS_IN_PROGRESS", "state": "in", "completed": False,
                     "description": "In Progress", "detail": shown, "shortDetail": shown})
        status.update({"period": period, "displayClock": clock})

    for side in comp.get("competitors") or []:
        side["score"] = str(home if (side.get("homeAway") or "").lower() == "home" else away)

    # The situation is where the next snap would be taken from: that is the
    # next play's own start. Without one - a period break, or the end of what
    # has been played - no ball is drawn.
    comp.pop("situation", None)
    if following and not between and not ended:
        start = (following[1].get("start") or {})
        team = (start.get("team") or {}).get("id")
        if start.get("downDistanceText"):
            comp["situation"] = {
                "down": start.get("down"), "distance": start.get("distance"),
                "yardLine": start.get("yardLine"),
                "downDistanceText": start.get("downDistanceText"),
                "shortDownDistanceText": start.get("shortDownDistanceText"),
                "possession": str(team) if team is not None else None,
                "isRedZone": bool(start.get("yardsToEndzone") is not None and start["yardsToEndzone"] <= 20),
                "lastPlay": {k: last[k] for k in ("id", "text", "type", "scoreValue", "statYardage", "end", "team")
                             if k in last},
            }
    return out


def board_at(reference: dict, events: dict[str, dict], summaries: dict[str, dict],
             when: dt.datetime) -> dict:
    """The whole board as it stood at `when`: every slate game, rebuilt where
    it had played and left as scheduled where it had not."""
    out = copy.deepcopy(reference)
    rebuilt = []
    by_id = {}
    for event_id, event in events.items():
        summary = summaries.get(event_id)
        if summary:
            by_id[event_id] = game_at(event, summary, when)
            if by_id[event_id].get("saturdayProvenance") == "reconstructed":
                rebuilt.append(event_id)
        else:
            fresh = copy.deepcopy(event)
            fresh["saturdayProvenance"] = "schedule"
            by_id[event_id] = fresh
    # A reconstructed board carries the slate it rebuilt and nothing else. A
    # game outside it - the Thursday game on a week board - was neither
    # recorded nor rebuilt here, and passing its current state through would
    # label somebody else's recording as ours.
    out["events"] = [by_id[str(ev.get("id"))] for ev in reference.get("events") or []
                     if str(ev.get("id")) in by_id]
    out["capturedAt"] = dt_to_stamp(when)
    out["saturdayProvenance"] = {
        "kind": "reconstructed",
        "at": when.isoformat().replace("+00:00", "Z"),
        "from": "ESPN game summaries; each play's own wallclock",
        "gamesReconstructed": len(rebuilt),
        "caveats": CAVEATS,
    }
    return out


def frame_instants(summaries: dict[str, dict], every: float, until: dt.datetime | None = None) -> list[dt.datetime]:
    """The minutes worth a frame: those in which a play happened somewhere on
    the slate, rounded up to the frame grid, plus one frame a step after the
    last play so the closing state is on the board.

    A flat sweep would spend a thousand files on an empty Friday night; a
    Saturday's gaps are real gaps, and the replay already draws them as gaps.
    """
    step = dt.timedelta(seconds=every)
    marks = set()
    for summary in summaries.values():
        for when, _ in timed_plays(summary):
            ticks = int(when.timestamp() // every) * every + every
            marks.add(dt.datetime.fromtimestamp(ticks, dt.timezone.utc))
    if marks:
        marks.add(max(marks) + step)
    return sorted(m for m in marks if until is None or m <= until)


def provenance_of(event: dict) -> str:
    """What a board's event is: recorded live, reconstructed, or the schedule."""
    value = event.get("saturdayProvenance")
    return value if value in ("reconstructed", "schedule") else "recorded"
