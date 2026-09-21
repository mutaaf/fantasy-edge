"""A finished day, played back as if it were live.

`replay.py` replays one game. This replays a *slate*: every game of a Sunday
at once, so the red-zone channel can whip around them the way it did while
they were being played. The user who missed the games gets the day back.

THE TRICK, AND WHY IT WORKS. ESPN stamps every play with the instant it
happened (`wallclock`, present on all 2,546 plays of the 2026-09-20 slate), so
a finished game's summary is not only its final score - it is a timeline. Given
the day's board for the things a play does not carry (clubs, kickoff, network)
and every game's summary, the board can be rebuilt as it stood at any moment.

THE SHAPE, AND WHY THIS FILE IS SMALL. The rebuild emits an ESPN-shaped
scoreboard, and `DayDirector.fetch` stands in for `EspnLiveSource._fetch` on a
source instance of its own - the arrangement `ReplayDirector` already uses for
one game. So `live.EspnLiveSource.games()`, `whip.slate()`, `whip.rank()`,
`whip.choose()` and `/api/redzone` are untouched: a replayed day and a live
Sunday are not similar code paths, they are the same one. Nothing here knows
what a red zone is.

WHAT A REBUILT DAY IS BETTER AT. A play record carries `downDistanceText` and
`yardsToEndzone` for every play; the *live* scoreboard omits the second one
entirely outside the NFL and the first between plays. So the channel's captions
and its proximity term are better here than they were on the day.

WHAT IT CANNOT KNOW: see `CAVEATS`. A rebuild is not a recording and says so -
every board carries `dayProvenance`, and the payload and the page repeat it.
"""

from __future__ import annotations

import copy
import datetime as dt
import json
import pathlib
import threading
import time
from zoneinfo import ZoneInfo

from .live import scoreboard_url, summary_url

ET = ZoneInfo("America/New_York")

CAVEATS = [
    "A score ESPN corrected and then corrected back leaves no trace: only the version in the "
    "summary survives, so a tile that flickered up and down reads as one clean change.",
    "A delay that started and ended is not in a summary. It shows only as a gap between plays, "
    "and is not drawn as a delay.",
    "The status ESPN published minute by minute is gone. Halftime here is inferred from the gap "
    "between the last play of one period and the first of the next, not read from a board.",
    "Down, distance and possession between plays come from the next play's start. After the last "
    "play of a period there is no next play, so no ball is drawn.",
    "ESPN's play feed leads its own scoreboard, and a touchdown's play already carries the score "
    "after the extra point. A rebuild therefore never passes through the six-point moment between "
    "a touchdown and its conversion.",
    "A game begins at its first play and ends at its last, not when ESPN flipped the board.",
    "Wallclocks are ESPN's and a few are wrong. ESPN's play order is trusted over its stamps: the "
    "stamps that agree with the order are kept and the rest are spaced evenly between their "
    "neighbours, so a handful of plays sit a few seconds from where they really were.",
]

# Between the last play of a period and the first of the next the game is at a
# break; only the one after the second period is halftime.
HALFTIME_AFTER = 2

# A score's marker sits a beat before the play so that "skip to the next score"
# lands in time to watch it happen rather than on the aftermath. `replay.py`
# uses the same idea in game seconds; here it is wall seconds.
LEAD_SECONDS = 12.0


# ──────────────────────────── pulling a day ────────────────────────────

def day_url(date: str, league_path: str | None = None) -> str:
    """ESPN's board for one calendar day, `YYYY-MM-DD` or `YYYYMMDD`."""
    return scoreboard_url(f"?dates={_compact(date)}", league_path=league_path)


def _compact(date: str) -> str:
    text = str(date).strip().replace("-", "")
    if len(text) != 8 or not text.isdigit():
        raise ValueError(f"date must be YYYY-MM-DD, not {date!r}")
    return text


def day_dir(root: pathlib.Path, date: str) -> pathlib.Path:
    return pathlib.Path(root) / f"{_compact(date)[:4]}-{_compact(date)[4:6]}-{_compact(date)[6:]}"


def pull_day(date: str, root: pathlib.Path, http=None, log=None,
             refresh: bool = False, league_path: str | None = None) -> dict:
    """Fetch a day's board and every finished game on it, idempotently.

    One request for the board plus one per game, and free to re-run: `week.
    pull_week` already skips a game whose summary and slate are both on disk,
    so a day pulled once opens for ever after with no network at all.
    """
    from . import week as wk
    from .live import _get_json, with_key

    get = http or (lambda url: _get_json(with_key(url)))
    dest = day_dir(root, date)
    dest.mkdir(parents=True, exist_ok=True)
    board_file = dest / "board.json"

    if refresh or not board_file.exists():
        board = get(day_url(date, league_path))
        board_file.write_text(json.dumps(board))
        requests = 1
    else:
        board = json.loads(board_file.read_text())
        requests = 0

    out = wk.pull_week(board, dest, http=http, log=log, refresh=refresh)
    out["requests"] += requests
    out["date"] = date
    out["league"] = league_of(board)
    return out


def load_day(root: pathlib.Path, date: str) -> tuple[dict, dict[str, dict]]:
    """The day's board and every summary beside it, from disk."""
    dest = day_dir(root, date)
    board_file = dest / "board.json"
    if not board_file.exists():
        raise LookupError(f"{date} has not been pulled: no {board_file}")
    board = json.loads(board_file.read_text())
    summaries: dict[str, dict] = {}
    for ev in board.get("events") or []:
        path = dest / f"{str(ev.get('id'))}.json"
        if path.exists():
            summaries[str(ev["id"])] = json.loads(path.read_text())
    return board, summaries


def league_of(board: dict) -> str:
    """Which league a board is, stated by the feed rather than assumed."""
    return ((board.get("leagues") or [{}])[0].get("slug") or "")


# ──────────────────────── rebuilding from wallclocks ────────────────────────

def _when(play: dict) -> dt.datetime | None:
    raw = play.get("wallclock")
    if not raw:
        return None
    try:
        return dt.datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None


def ordered_times(times: list[dt.datetime | None]) -> list[dt.datetime | None]:
    """Stamps made non-decreasing, trusting ESPN's play order over its clocks.

    A few of ESPN's wallclocks are wrong - on a college Saturday one play was
    stamped two hours after its game ended. Sorting plays by them reorders a
    game around its worst stamp, which is far worse than the stamp itself. So
    the longest run of stamps that already agrees with the play order is kept
    and every disagreeing play is spaced evenly between its trusted
    neighbours. A play so placed is a few seconds out; a play re-ordered is in
    the wrong quarter.
    """
    known = [(i, t) for i, t in enumerate(times) if t is not None]
    if not known:
        return list(times)

    # Longest non-decreasing run over the known stamps (patience sorting).
    # `tails[k]` is the index into `known` ending the best run of length k+1.
    tails: list[int] = []
    prior: list[int | None] = [None] * len(known)
    for k, (_, t) in enumerate(known):
        lo, hi = 0, len(tails)
        while lo < hi:                       # first tail strictly later than t
            mid = (lo + hi) // 2
            if known[tails[mid]][1] <= t:
                lo = mid + 1
            else:
                hi = mid
        prior[k] = tails[lo - 1] if lo else None
        if lo == len(tails):
            tails.append(k)
        else:
            tails[lo] = k

    keep: list[int] = []
    cursor = tails[-1] if tails else None
    while cursor is not None:
        keep.append(cursor)
        cursor = prior[cursor]
    trusted = {known[k][0]: known[k][1] for k in reversed(keep)}

    out: list[dt.datetime | None] = [trusted.get(i) for i in range(len(times))]
    anchors = sorted(trusted)
    for left, right in zip([None] + anchors, anchors + [None]):
        lo = left + 1 if left is not None else 0
        hi = right if right is not None else len(times)
        if hi <= lo:
            continue
        if left is None:                     # before the first trusted stamp
            for i in range(lo, hi):
                out[i] = trusted[anchors[0]]
        elif right is None:                  # after the last
            for i in range(lo, hi):
                out[i] = trusted[anchors[-1]]
        else:
            a, b = trusted[left], trusted[right]
            step = (b - a) / (hi - lo + 1)
            for n, i in enumerate(range(lo, hi), start=1):
                out[i] = a + step * n
    return out


def timed_plays(summary: dict) -> list[tuple[dt.datetime, dict]]:
    """Every play with the instant it happened, in ESPN's own order.

    ESPN lists the drive in progress in both `previous` and `current`; keyed on
    play id each play appears once, which is the dedupe AGENTS.md calls for.
    """
    drives = summary.get("drives") or {}
    seen: dict[str, dict] = {}
    for drive in (drives.get("previous") or []) + ([drives["current"]] if drives.get("current") else []):
        for play in drive.get("plays") or []:
            seen[str(play.get("id") or len(seen))] = play
    plays = list(seen.values())
    return [(t, p) for t, p in zip(ordered_times([_when(p) for p in plays]), plays) if t]


def running_scores(summary: dict) -> dict[str, tuple[int, int]]:
    """Each play's `(away, home)` score, with ESPN's blank rows carried over.

    A play record states the score after it, and most of them are right. Two
    kinds are not, and both were on the 2026-09-20 slate:

      * **A blank administrative row.** Cincinnati at Houston's "Two-Minute
        Warning" carries 0-0 while the game stood at 20-6. Reading it puts a
        tile back to nothing for one play, so a row reporting 0-0 once the
        game has scored is treated as unstated and the running score carries
        through it.
      * **A touchdown counted before its try.** New Orleans at Baltimore's
        touchdown carries 17 - the score it would have been had the two-point
        attempt worked - and the failed attempt then restates 15. That is a
        real correction of a real over-count, it is what ESPN's own feed
        published, and it is left alone rather than smoothed away.

    The distinction is that the first states a score nobody was ever on and
    the second states one everybody saw.
    """
    out: dict[str, tuple[int, int]] = {}
    away = home = 0
    for _, play in timed_plays(summary):
        saw_away, saw_home = _int(play.get("awayScore")), _int(play.get("homeScore"))
        if not (saw_away == 0 and saw_home == 0 and (away or home)):
            away, home = saw_away, saw_home
        out[str(play.get("id"))] = (away, home)
    return out


def covered_span(summaries: dict[str, dict]) -> tuple[dt.datetime, dt.datetime] | None:
    """First and last instant any play in any game happened."""
    times = [w for s in summaries.values() for w, _ in timed_plays(s)]
    return (min(times), max(times)) if times else None


def _int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _period(play: dict) -> int:
    return _int((play.get("period") or {}).get("number"))


def _clock(play: dict) -> str:
    return (play.get("clock") or {}).get("displayValue") or "0:00"


def period_label(period: int) -> str:
    if 0 < period < 5:
        return ("", "1st", "2nd", "3rd", "4th")[period]
    return f"OT{period - 4}" if period > 4 else ""


def _to_endzone_from_text(start: dict, clubs: dict[str, str]) -> int | None:
    """Yards to the end zone, read from the way football names a yard line.

    A spot is written as a club and a number - "PHI 17" - and the club is
    whose half of the field it is. So when the ball sits in the *other* side's
    half, the number is already the distance to the goal line; in your own
    half it is the distance from your own, and the ball is nowhere near
    scoring. `yardLine` cannot be used for this: it is absolute (83 for that
    same spot) and says nothing about which way the offence is facing.

    Only ever used when ESPN omits `yardsToEndzone`, which it does on every
    live college situation. A college play record carries one, so this is the
    belt to that brace - and it returns None rather than a guess when the text
    is not there, because a red zone claimed on a game that has not got one
    sends the channel to the wrong stadium.
    """
    text = (start.get("possessionText") or "").strip()
    if not text:
        text = (start.get("downDistanceText") or "").split(" at ")[-1].strip()
    parts = text.split()
    if len(parts) != 2 or not parts[1].isdigit():
        return None
    where, yards = parts[0].upper(), int(parts[1])
    holder = clubs.get(str((start.get("team") or {}).get("id")), "")
    if not holder or where not in clubs.values():
        return None
    return yards if where != holder else None


def situation_from(play: dict, last: dict, clubs: dict[str, str] | None = None) -> dict:
    """The situation the offence stood in, from the next play's own start.

    Everything the channel reads comes from here, and a play record carries
    more than a live scoreboard does: `downDistanceText` names the yard line,
    and `yardsToEndzone` is present on a play even in the college feed, where
    the live `situation` block never carries it. `isRedZone` is derived from
    the distance when there is one and from the yard line when there is not,
    rather than being absent - the channel keys off that flag.
    """
    clubs = clubs or {}
    start = play.get("start") or {}
    to_ez = start.get("yardsToEndzone")
    if to_ez is None:
        to_ez = _to_endzone_from_text(start, clubs)
    team = (start.get("team") or {}).get("id")
    return {
        "down": start.get("down"),
        "distance": start.get("distance"),
        "yardLine": start.get("yardLine"),
        "yardsToEndzone": start.get("yardsToEndzone"),
        "downDistanceText": start.get("downDistanceText"),
        "shortDownDistanceText": start.get("shortDownDistanceText"),
        "possession": str(team) if team is not None else None,
        "isRedZone": to_ez is not None and _int(to_ez, 99) <= 20,
        "lastPlay": {k: last[k] for k in
                     ("id", "text", "type", "scoreValue", "statYardage", "end", "team")
                     if k in last},
    }


def game_at(event: dict, summary: dict, when: dt.datetime) -> dict:
    """The board's event, rewritten to how that game stood at `when`.

    An ESPN-shaped event, so `live.games()` and everything above it read it
    exactly as they read a live one. It carries `dayProvenance` so nothing
    can mistake it for a recording.
    """
    plays = timed_plays(summary)
    out = copy.deepcopy(event)
    comp = (out.get("competitions") or [{}])[0]
    status = comp.setdefault("status", {})
    kind = status.setdefault("type", {})
    out["status"] = status                     # some readers look at either

    played = [(w, p) for w, p in plays if w <= when]
    if not played:
        out["dayProvenance"] = "schedule"      # it had not kicked off yet
        comp.pop("situation", None)
        for side in comp.get("competitors") or []:
            side["score"] = "0"
        kind.update({"name": "STATUS_SCHEDULED", "state": "pre", "completed": False,
                     "description": "Scheduled", "detail": "Scheduled",
                     "shortDetail": "Scheduled"})
        status.update({"period": 0, "clock": 0.0, "displayClock": "0:00"})
        return out

    out["dayProvenance"] = "reconstructed"
    last = played[-1][1]
    following = plays[len(played)][1] if len(plays) > len(played) else None
    period, clock = _period(last), _clock(last)

    header = (((summary.get("header") or {}).get("competitions") or [{}])[0].get("status") or {})
    header_kind = header.get("type") or {}
    ended = bool(header_kind.get("completed")) and following is None
    between = following is not None and _period(following) > period

    if ended:
        detail = header_kind.get("shortDetail") or "Final"
        kind.update({"name": header_kind.get("name") or "STATUS_FINAL", "state": "post",
                     "completed": True,
                     "description": header_kind.get("description") or "Final",
                     "detail": header_kind.get("detail") or detail, "shortDetail": detail})
        status.update({"period": period, "clock": 0.0, "displayClock": "0:00"})
    elif between and period == HALFTIME_AFTER:
        kind.update({"name": "STATUS_HALFTIME", "state": "in", "completed": False,
                     "description": "Halftime", "detail": "Halftime",
                     "shortDetail": "Halftime"})
        status.update({"period": period, "clock": 0.0, "displayClock": "0:00"})
    else:
        shown = f"{clock} - {period_label(period)}"
        kind.update({"name": "STATUS_IN_PROGRESS", "state": "in", "completed": False,
                     "description": "In Progress", "detail": shown, "shortDetail": shown})
        # `live.games()` reads `clock` as seconds remaining in the period to
        # work out how far through the game a club is; the string is what a
        # board prints. Both, or the channel's "one score, late" never fires.
        status.update({"period": period, "clock": _clock_seconds(clock),
                       "displayClock": clock})

    away, home = running_scores(summary).get(str(last.get("id")), (0, 0))
    for side in comp.get("competitors") or []:
        side["score"] = str(home if (side.get("homeAway") or "").lower() == "home" else away)

    comp.pop("situation", None)
    if following is not None and not between and not ended:
        comp["situation"] = situation_from(following, last, _clubs(summary))
    return out


def _clock_seconds(display: str) -> float:
    """"11:39" as seconds remaining, which is what `live.games()` divides by."""
    parts = str(display or "").split(":")
    try:
        if len(parts) == 2:
            return float(parts[0]) * 60.0 + float(parts[1])
        return float(parts[0])
    except (TypeError, ValueError):
        return 0.0


def board_at(board: dict, summaries: dict[str, dict], when: dt.datetime) -> dict:
    """The whole slate as it stood at `when`.

    Every game is rebuilt where it had played and left as scheduled where it
    had not, so a board at one o'clock is a board of kickoffs rather than a
    board of finals.
    """
    out = copy.deepcopy(board)
    events, rebuilt = [], 0
    for ev in board.get("events") or []:
        event_id = str(ev.get("id") or "")
        summary = summaries.get(event_id)
        if summary:
            fresh = game_at(ev, summary, when)
            rebuilt += fresh.get("dayProvenance") == "reconstructed"
        else:
            # Pulled days capture finished games; one that never finished has
            # no summary, and its schedule row is the honest thing to show.
            fresh = copy.deepcopy(ev)
            fresh["dayProvenance"] = "schedule"
        events.append(fresh)
    out["events"] = events
    out["dayProvenance"] = {
        "kind": "reconstructed",
        "at": when.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "from": "ESPN game summaries; each play's own wallclock",
        "gamesReconstructed": rebuilt,
        "caveats": CAVEATS,
    }
    return out


def summary_at(summary: dict, when: dt.datetime) -> dict:
    """A game's summary cut to what had happened by `when`.

    The board is what the channel reads, but a gamecast opens the summary, and
    serving the finished one would put the final score on screen hours before
    it happened. Drives are truncated play by play and the header is rewound
    with them.
    """
    out = copy.deepcopy(summary)
    cutoff = {str(p.get("id")) for w, p in timed_plays(summary) if w <= when}
    drives = out.get("drives") or {}
    kept_last: dict | None = None
    kept_drives = []
    for drive in (drives.get("previous") or []) + ([drives["current"]] if drives.get("current") else []):
        plays = [p for p in (drive.get("plays") or []) if str(p.get("id")) in cutoff]
        if not plays:
            continue
        fresh = copy.deepcopy(drive)
        fresh["plays"] = plays
        kept_drives.append(fresh)
        kept_last = plays[-1]
    out["drives"] = {"previous": kept_drives}
    out["scoringPlays"] = [sp for sp in (summary.get("scoringPlays") or [])
                           if str(sp.get("id")) in cutoff]
    out["winprobability"] = [w for w in (summary.get("winprobability") or [])
                             if str(w.get("playId")) in cutoff]

    header_comp = ((out.get("header") or {}).get("competitions") or [{}])[0]
    if kept_last is not None:
        away, home = running_scores(summary).get(str(kept_last.get("id")), (0, 0))
        period = _period(kept_last)
        status = header_comp.setdefault("status", {})
        kind = status.setdefault("type", {})
        ended = len(cutoff) >= len(timed_plays(summary))
        if not ended:
            shown = f"{_clock(kept_last)} - {period_label(period)}"
            kind.update({"name": "STATUS_IN_PROGRESS", "state": "in", "completed": False,
                         "description": "In Progress", "detail": shown, "shortDetail": shown})
            status.update({"period": period, "clock": _clock_seconds(_clock(kept_last)),
                           "displayClock": _clock(kept_last)})
        for side in header_comp.get("competitors") or []:
            side["score"] = str(home if (side.get("homeAway") or "").lower() == "home" else away)
    out["dayProvenance"] = "reconstructed"
    return out


def scoring_moments(summaries: dict[str, dict]) -> list[dict]:
    """Every scoring play on the slate, by the instant it happened.

    What "skip to the next score" is made of, and what a scrub bar draws its
    ticks from. A day's worth of these is a few hundred rows, computed once.
    """
    out = []
    for event_id, summary in summaries.items():
        clubs = _clubs(summary)
        for when, play in timed_plays(summary):
            if not play.get("scoringPlay"):
                continue
            team = str(((play.get("start") or {}).get("team") or {}).get("id") or "")
            out.append({
                "event": event_id,
                "at": when.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
                "epoch": when.timestamp(),
                "team": clubs.get(team, ""),
                "period": _period(play),
                "clock": _clock(play),
                "text": play.get("text") or "",
                "homeScore": _int(play.get("homeScore")),
                "awayScore": _int(play.get("awayScore")),
            })
    out.sort(key=lambda s: s["epoch"])
    return out


def _clubs(summary: dict) -> dict[str, str]:
    comp = (((summary.get("header") or {}).get("competitions") or [{}])[0])
    out = {}
    for side in comp.get("competitors") or []:
        team = side.get("team") or {}
        out[str(team.get("id"))] = (team.get("abbreviation") or "").upper()
    return out


# ───────────────────────────── the slots ─────────────────────────────

def kickoff_slots(board: dict) -> list[dict]:
    """The day's kickoff waves, from the board's own times.

    "The four o'clock games" is a real thing a viewer asks for, but the hours
    are not fixed - they drift by week and they are different in another
    league. So a slot is a cluster of kickoffs the day actually has rather
    than an hour written into this file.
    """
    times: dict[str, list[str]] = {}
    for ev in board.get("events") or []:
        raw = ev.get("date") or ""
        try:
            when = dt.datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(ET)
        except ValueError:
            continue
        times.setdefault(when.strftime("%H:%M"), []).append(str(ev.get("id")))

    out = []
    for hhmm in sorted(times):
        hour, minute = (int(p) for p in hhmm.split(":"))
        clock = dt.time(hour, minute)
        out.append({"at": hhmm, "games": len(times[hhmm]),
                    "label": _slot_label(clock, len(out)),
                    "events": times[hhmm]})
    return out


def _slot_label(clock: dt.time, index: int) -> str:
    hour = clock.hour % 12 or 12
    suffix = "am" if clock.hour < 12 else "pm"
    minute = f":{clock.minute:02d}" if clock.minute else ""
    return f"{hour}{minute}{suffix} ET"


def parse_moment(text: str, day: dt.date) -> dt.datetime:
    """"13:00", "1:00pm", "16:30 ET" or a full ISO instant, as an instant.

    A bare time is Eastern, because that is the clock a football day is
    scheduled on, and the alternative - the machine's own zone - would make
    the same command mean different things on two laptops.
    """
    raw = str(text or "").strip()
    if not raw:
        raise ValueError("a time is required")
    cleaned = raw.upper().replace("ET", "").replace("EST", "").replace("EDT", "").strip()
    try:                                        # a full instant, if given
        when = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return when if when.tzinfo else when.replace(tzinfo=ET)
    except ValueError:
        pass
    ampm = ""
    for tag in ("AM", "PM"):
        if cleaned.endswith(tag):
            ampm, cleaned = tag, cleaned[:-len(tag)].strip()
            break
    parts = cleaned.replace(".", ":").split(":")
    try:
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
    except (TypeError, ValueError):
        raise ValueError(f"cannot read {text!r} as a time") from None
    if ampm == "PM" and hour < 12:
        hour += 12
    if ampm == "AM" and hour == 12:
        hour = 0
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"{text!r} is not a time of day")
    return dt.datetime.combine(day, dt.time(hour, minute), tzinfo=ET)


# ───────────────────────────── the director ─────────────────────────────

class DayDirector:
    """One day a process can be driven through: play, pause, scrub, skip.

    The position is an instant in that day, never a number that ticks. It is
    an anchor - a moment and the monotonic instant it was true - plus a speed,
    and the current moment is computed from those when asked. Pausing,
    seeking and changing speed each only move the anchor, so nothing drifts
    and no thread has to run. `ReplayDirector` keeps its position the same
    way, in game seconds rather than wall time.

    `fetch` stands in for `EspnLiveSource._fetch` on a source instance of its
    own, exactly as one game's replay does. That is what makes the channel
    above it unaware that the day is over.
    """

    SPEEDS = (1.0, 5.0, 15.0, 30.0, 60.0, 120.0, 300.0, 600.0)

    def __init__(self, root: pathlib.Path, clock=time.monotonic):
        self.root = pathlib.Path(root)
        self.clock = clock
        self._lock = threading.RLock()
        self.date = ""
        self.board: dict = {}
        self.summaries: dict[str, dict] = {}
        self.league = ""
        self.start: dt.datetime | None = None
        self.end: dt.datetime | None = None
        self.speed = 60.0
        self.playing = False
        self._anchor_at: dt.datetime | None = None
        self._anchor_wall = 0.0
        self._scores: list[dict] = []
        self._boards: dict[int, dict] = {}

    # ── loading ──

    def load(self, date: str, *, window: tuple[str, str] | None = None,
             slot: str = "", at: str = "") -> dict:
        """Open a pulled day, optionally windowed to part of it."""
        board, summaries = load_day(self.root, date)
        if not summaries:
            raise LookupError(f"{date} has a board but no games: pull it first")
        span = covered_span(summaries)
        if not span:
            raise LookupError(f"{date} has no plays to replay")

        day = dt.datetime.fromisoformat(_compact(date)[:4] + "-" + _compact(date)[4:6]
                                        + "-" + _compact(date)[6:]).date()
        start, end = span
        if slot:
            start, end = self._slot_window(board, summaries, slot, span)
        if window:
            if window[0]:
                start = max(start, parse_moment(window[0], day))
            if window[1]:
                end = min(end, parse_moment(window[1], day))
        if end <= start:
            raise ValueError("the window ends before it starts")

        with self._lock:
            self.date, self.board, self.summaries = date, board, summaries
            self.league = league_of(board)
            self.start, self.end = start, end
            self._scores = [s for s in scoring_moments(summaries)
                            if start <= _from_epoch(s["epoch"]) <= end]
            self._boards = {}
            self.playing = False
            self._set(parse_moment(at, day) if at else start)
        return self.state()

    def _slot_window(self, board: dict, summaries: dict[str, dict], slot: str,
                     span: tuple[dt.datetime, dt.datetime]):
        """The window covering one kickoff wave - "the four o'clock games".

        Matched against the day's own kickoff times rather than an hour
        written down here: a slate's waves move by week and by league.
        """
        wanted = str(slot).strip().lower()
        slots = kickoff_slots(board)
        if not slots:
            raise ValueError("this day has no kickoff times to pick a slot from")
        names = ", ".join(s["label"] for s in slots)

        # An exact wave first - "4:25pm" means that one and not its neighbour.
        hits = [s for s in slots
                if wanted in (s["label"].lower(), s["at"],
                              s["label"].lower().replace(" et", ""))]
        if not hits:
            # Then the hour, which is what a viewer says: "the four o'clock
            # games" is both the 4:05 wave and the 4:25 one, and answering
            # with two of the five games would be answering a question nobody
            # asked. An NFL Sunday splits its afternoon into waves minutes
            # apart and calls the whole thing one slot.
            hour = wanted.rstrip("apm. ").split(":")[0]
            if hour.isdigit():
                want12 = int(hour) % 12
                for s in slots:
                    at_hour = int(s["at"].split(":")[0])
                    if at_hour % 12 == want12 and ("am" in s["label"]) == ("am" in wanted
                                                                          or at_hour < 12):
                        hits.append(s)
        if not hits:
            raise ValueError(f"no kickoff slot like {slot!r}; this day has {names}")
        events = {e for s in hits for e in s["events"]}
        times = [w for eid, s in summaries.items() if eid in events
                 for w, _ in timed_plays(s)]
        return (min(times), max(times)) if times else span

    # ── the controls ──

    def play(self) -> dict:
        with self._lock:
            self._need()
            now = self._now()
            self._set(self.start if now >= self.end else now)
            self.playing = True
        return self.state()

    def pause(self) -> dict:
        with self._lock:
            self._need()
            self._set(self._now())
            self.playing = False
        return self.state()

    def seek(self, offset: float) -> dict:
        """Seek to `offset` seconds after the window's start."""
        with self._lock:
            self._need()
            self._set(self.start + dt.timedelta(seconds=max(0.0, float(offset))))
        return self.state()

    def seek_at(self, text: str) -> dict:
        """Seek to a time of day - "15:30", "3:30pm"."""
        with self._lock:
            self._need()
            day = self.start.astimezone(ET).date()
            self._set(parse_moment(text, day))
        return self.state()

    def set_speed(self, speed: float) -> dict:
        speed = float(speed)
        if not (0.25 <= speed <= 3600):
            raise ValueError("speed must be between 0.25 and 3600 seconds per second")
        with self._lock:
            self._need()
            now = self._now()
            self.speed = speed
            self._set(now)
        return self.state()

    def skip(self, forward: bool = True) -> dict:
        """Seek to the next scoring play on the whole slate, or the previous.

        A day's version of `replay.skip`: the channel's own reason to move.
        The marker sits `LEAD_SECONDS` before the play so the score is watched
        rather than discovered.
        """
        with self._lock:
            self._need()
            now = self._now()
            marks = [_from_epoch(s["epoch"]) - dt.timedelta(seconds=LEAD_SECONDS)
                     for s in self._scores]
            if forward:
                nxt = next((m for m in marks if m > now + dt.timedelta(seconds=1)), self.end)
            else:
                nxt = next((m for m in reversed(marks)
                            if m < now - dt.timedelta(seconds=1)), self.start)
            self._set(nxt)
        return self.state()

    def control(self, body: dict) -> dict:
        """One POST body, one action. Unknown actions are refused."""
        action = str(body.get("action") or "")
        if action == "load":
            return self.load(body.get("date") or "",
                             window=(str(body.get("from") or ""), str(body.get("to") or "")),
                             slot=str(body.get("slot") or ""),
                             at=str(body.get("at") or ""))
        if action == "play":
            return self.play()
        if action == "pause":
            return self.pause()
        if action == "seek":
            if body.get("time"):
                return self.seek_at(str(body["time"]))
            return self.seek(float(body.get("at") or 0))
        if action == "speed":
            return self.set_speed(body.get("speed") or 60)
        if action in ("next", "previous"):
            return self.skip(forward=action == "next")
        raise ValueError(f"unknown action {action!r}: load, play, pause, seek, speed, "
                         "next or previous")

    # ── position ──

    def _need(self) -> None:
        if not self.date:
            raise LookupError("no day loaded")

    def _set(self, when: dt.datetime) -> None:
        self._anchor_at = min(max(when, self.start), self.end)
        self._anchor_wall = self.clock()

    def _now(self) -> dt.datetime:
        if not self.playing or self._anchor_at is None:
            return self._anchor_at or self.start
        gone = (self.clock() - self._anchor_wall) * self.speed
        return min(self._anchor_at + dt.timedelta(seconds=gone), self.end)

    def moment(self) -> dt.datetime:
        """Where the day is now, stopping the tape at the end rather than looping."""
        with self._lock:
            self._need()
            now = self._now()
            if self.playing and now >= self.end:
                self._set(self.end)
                self.playing = False
            return now

    def offset(self) -> float:
        return (self.moment() - self.start).total_seconds()

    def length(self) -> float:
        return (self.end - self.start).total_seconds() if self.start else 0.0

    # ── what it serves ──

    def board_now(self) -> dict:
        """The slate as of now, memoised by whole second.

        A poll every three seconds at 60x steps three minutes through the day,
        so the cache is small and exists to stop two viewers in the same
        second paying for the same fourteen rebuilds.
        """
        with self._lock:
            self._need()
            key = int(self.moment().timestamp())
            hit = self._boards.get(key)
            if hit is None:
                if len(self._boards) > 16:
                    self._boards.clear()
                hit = self._boards[key] = board_at(self.board, self.summaries,
                                                   _from_epoch(key))
            return hit

    def fetch(self, url: str) -> dict:
        """`EspnLiveSource._fetch` for the day's own source instance."""
        if "summary?event=" in url:
            event = url.split("summary?event=", 1)[1].split("&")[0]
            summary = self.summaries.get(event)
            if summary is None:
                raise LookupError(f"event {event} is not on the day being replayed")
            return summary_at(summary, self.moment())
        return self.board_now()

    def state(self) -> dict:
        """What a remote control shows. Always labelled as a rebuild."""
        with self._lock:
            if not self.date:
                return {"day": True, "loaded": False, "playing": False,
                        "speed": self.speed, "speeds": list(self.SPEEDS)}
            now = self.moment()
            live = sum(1 for ev in self.board_now().get("events") or []
                       if (((ev.get("competitions") or [{}])[0].get("status") or {})
                           .get("type") or {}).get("state") == "in")
            return {
                "day": True, "loaded": True, "date": self.date, "league": self.league,
                "playing": self.playing, "speed": self.speed, "speeds": list(self.SPEEDS),
                "at": now.astimezone(ET).isoformat(),
                "label": now.astimezone(ET).strftime("%-I:%M:%S %p ET"),
                "offset": round(self.offset(), 1), "length": round(self.length(), 1),
                "progress": round(self.offset() / self.length(), 4) if self.length() else 0.0,
                "window": {"from": self.start.astimezone(ET).strftime("%-I:%M %p ET"),
                           "to": self.end.astimezone(ET).strftime("%-I:%M %p ET")},
                "games": len(self.summaries), "live": live,
                "scores": len(self._scores),
                "provenance": "reconstructed",
                "caveats": CAVEATS,
            }

    def markers(self) -> dict:
        """Where the scores are, as offsets into the window, for a scrub bar."""
        with self._lock:
            self._need()
            out = []
            for s in self._scores:
                at = (_from_epoch(s["epoch"]) - self.start).total_seconds()
                out.append({**{k: s[k] for k in
                               ("event", "team", "period", "clock", "text")},
                            "at": round(max(0.0, at - LEAD_SECONDS), 1),
                            "playAt": round(at, 1)})
            return {"scores": out, "length": round(self.length(), 1),
                    "slots": kickoff_slots(self.board)}


def _from_epoch(epoch: float) -> dt.datetime:
    return dt.datetime.fromtimestamp(epoch, dt.timezone.utc)
