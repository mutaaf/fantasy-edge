"""Replay a finished NFL game as though it were happening now.

Every game in the feed is either finished or has not kicked off, which means
possession, ball position, drives, play-by-play, win probability and a ramping
scoreline are all unexercisable: there is no Sunday afternoon to develop
against, and there will not be one until the next one. A simulator would fix
the schedule problem and break the more important one - it would be *our*
payload shapes being parsed, not ESPN's, so every bug the parsers actually
have would stay hidden.

So this replays a real game instead. It captures one finished event once, and
then rewrites the two files `live.EspnLiveSource._fetch` already reads -
`FANTASYEDGE_SCOREBOARD_FILE` and `FANTASYEDGE_SUMMARY_DIR/{event}.json` - to
show that game as of a moving point in its own clock. Nothing in the live tier
changes, and nothing is mocked at the API boundary, so a replay drives the
same scoring, the same D/ST pairing, the same gamecast shaping and the same
possession logic that a live Sunday would.

`frame()` is the whole idea and is a pure function: two ESPN payloads and a
game clock in, the same two payloads as they looked at that instant out. It is
pure so it can be tested at a play boundary rather than watched.

WHAT THIS CANNOT DO HONESTLY
----------------------------
The summary's `boxscore` is final-state only. ESPN publishes no per-play
player stat line on this endpoint, so there is no truthful way to say what a
receiver had after eleven minutes, and scaling the final line by elapsed
fraction would be inventing numbers that look exactly like data. So the box
score is served as captured - final - and every frame carries a `replay` block
saying so. Player fantasy points therefore do not ramp during a replay; game
state does. Everything in the gamecast, the scoreline and the situation is
real and time-correct; the per-player totals are the end of the game from the
first snap.

A per-play source does exist on ESPN's core API and is public: each play at
`/v2/.../events/{e}/competitions/{e}/plays/{p}` carries a `participants[]`
list, and each participant has a `statistics` reference holding that athlete's
line for that play. Accumulating it would ramp the box score truthfully. It is
not used here because it is roughly eight hundred requests to assemble one
game - a separate feature with a separate rate-limit risk - and because those
values are per-play rather than cumulative, so the summing would be ours
rather than ESPN's. README says the same, at more length.
"""

from __future__ import annotations

import copy
import json
import pathlib
import time

from .live import _get_json, scoreboard_url, summary_url, with_key

# A play's absolute game time is encoded against a fixed 900-second period,
# because that is the only encoding the payload itself supports: a play knows
# its period number and the clock showing at the snap, and nothing else. The
# inverse is exact for any instant that lands on a play, including overtime -
# an OT play at 8:00 round-trips to period 5, 8:00 - which is why there is no
# special case for a ten-minute overtime here.
PERIOD_SECONDS = 900

BOXSCORE_NOTE = (
    "Player stats in `boxscore` are the FINAL game totals, not the totals as of "
    "this clock. ESPN publishes no per-play player stat line on the summary "
    "endpoint, so ramping them would mean inventing numbers. Game state, score, "
    "drives, possession and win probability ARE time-correct."
)


def clock_seconds(display: str) -> int:
    """"7:00" -> 420 seconds still on the period clock."""
    parts = str(display or "0:00").split(":")
    try:
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        return int(float(parts[0]))
    except ValueError:
        return 0


def clock_display(remaining: int) -> str:
    remaining = max(0, int(remaining))
    return f"{remaining // 60}:{remaining % 60:02d}"


def play_seconds(play: dict) -> int:
    """Absolute seconds into the game at which this play was snapped."""
    period = int(((play.get("period") or {}).get("number")) or 1)
    left = clock_seconds((play.get("clock") or {}).get("displayValue"))
    return (period - 1) * PERIOD_SECONDS + (PERIOD_SECONDS - left)


def ordinal(period: int) -> str:
    if period >= 5:
        return "OT" if period == 5 else f"{period - 4}OT"
    return {1: "1st", 2: "2nd", 3: "3rd", 4: "4th"}.get(period, f"Q{period}")


def _drives(summary: dict) -> list[dict]:
    """Every drive in play order, whether the capture called it done or not."""
    raw = summary.get("drives") or {}
    out = list(raw.get("previous") or [])
    if raw.get("current"):
        out.append(raw["current"])
    return out


def _all_plays(summary: dict) -> list[dict]:
    return [p for d in _drives(summary) for p in (d.get("plays") or [])]


def total_seconds(summary: dict) -> int:
    """When the last recorded play was snapped - the end of a replay."""
    plays = _all_plays(summary)
    return play_seconds(plays[-1]) if plays else 0


def _num(raw, default=0):
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _in_progress_drive(drive: dict, plays: list[dict]) -> dict:
    """A drive that has not finished, described only by what has happened.

    The captured drive carries its outcome - "5 plays, 25 yards, 3:18", a
    result of PUNT, `isScore` - and all of that is the future as far as this
    frame is concerned. Leaving it in is how a replay tells a client the drive
    ends in a punt while the drive is still being played, which is worse than a
    simulator, because it looks like real data.

    Nothing replaces those fields, because nothing honestly can. ESPN's own
    accounting is not a plain sum of the plays: `offensivePlays` is 5 on a
    drive holding 9 play records, since kickoffs, timeouts, punts and penalties
    do not count, and `yards` is measured to the last scrimmage spot rather
    than to the last record - a naive `yardsToEndzone` difference disagreed
    with ESPN on three of this game's nineteen drives and reported one
    possession as minus six yards. So a live drive here has no description, no
    yardage and no play count: absent, which is what a consumer already has to
    handle, rather than a number of our own invention wearing ESPN's shape.
    """
    d = dict(drive)
    d["plays"] = plays
    last = plays[-1] if plays else {}
    last_end = (last.get("end") or {})
    d["end"] = {
        "period": {"type": "quarter",
                   "number": _num((last.get("period") or {}).get("number"), 1)},
        "clock": {"displayValue": (last.get("clock") or {}).get("displayValue", "")},
        "yardLine": last_end.get("yardLine"),
        "text": last_end.get("possessionText") or "",
    }
    d["isScore"] = bool(last.get("scoringPlay"))
    for key in ("result", "displayResult", "shortDisplayResult", "timeElapsed",
                "description", "yards", "offensivePlays"):
        d.pop(key, None)
    return d


def _status_in(period: int, remaining: int) -> dict:
    clock = clock_display(remaining)
    return {
        "clock": float(remaining),
        "displayClock": clock,
        "period": period,
        "type": {
            "id": "2", "name": "STATUS_IN_PROGRESS", "state": "in",
            "completed": False, "description": "In Progress",
            "detail": f"{clock} - {ordinal(period)} Quarter"
                      if period <= 4 else f"{clock} - {ordinal(period)}",
            "shortDetail": f"{clock} - {ordinal(period)}",
        },
    }


def _status_pre(captured: dict) -> dict:
    """Kickoff has not happened.

    A capture of a finished game no longer carries what its pre-game status
    said, so this states the only thing that is certainly true - a full period
    on the clock, nothing played - and keeps the captured detail strings, which
    are the kickoff time rather than a score.
    """
    return {
        "clock": float(PERIOD_SECONDS), "displayClock": clock_display(PERIOD_SECONDS),
        "period": 0,
        "type": {"id": "1", "name": "STATUS_SCHEDULED", "state": "pre",
                 "completed": False, "description": "Scheduled",
                 "detail": (captured.get("type") or {}).get("detail", "Scheduled"),
                 "shortDetail": (captured.get("type") or {}).get("shortDetail", "Scheduled")},
    }


def _situation(play: dict) -> dict:
    """Where the ball is, from the end of the last play that has happened."""
    end = play.get("end") or {}
    team = str(((end.get("team") or {}).get("id")) or "")
    to_ez = end.get("yardsToEndzone")
    sit = {
        "down": end.get("down"),
        "distance": end.get("distance"),
        "yardLine": end.get("yardLine"),
        "yardsToEndzone": to_ez,
        "possession": team,
        "isRedZone": to_ez is not None and int(to_ez) <= 20,
    }
    for key in ("downDistanceText", "shortDownDistanceText", "possessionText"):
        if end.get(key):
            sit[key] = end[key]
    sit["lastPlay"] = {
        "id": str(play.get("id") or ""),
        "text": play.get("text") or "",
        "scoringPlay": bool(play.get("scoringPlay")),
        "team": {"id": str(((play.get("start") or {}).get("team") or {}).get("id") or "")},
    }
    return sit


def _linescores(plays: list[dict], period: int) -> tuple[list[dict], list[dict]]:
    """Quarter-by-quarter, recomputed rather than carried over.

    The captured line score is the finished game's. Left alone it hands a
    client the fourth-quarter points during the first quarter, which is the
    single most obvious way a replay leaks the ending.
    """
    home, away = [], []
    prev_h = prev_a = 0
    for p in range(1, period + 1):
        upto = [x for x in plays if _num((x.get("period") or {}).get("number"), 1) <= p]
        h = _num((upto[-1] if upto else {}).get("homeScore"), 0)
        a = _num((upto[-1] if upto else {}).get("awayScore"), 0)
        home.append({"displayValue": str(h - prev_h)})
        away.append({"displayValue": str(a - prev_a)})
        prev_h, prev_a = h, a
    return home, away


def frame(scoreboard: dict, summary: dict, game_seconds: int) -> tuple[dict, dict]:
    """Both payloads as they looked `game_seconds` into the game.

    Pure: the inputs are not touched. Every number here is read off a play that
    had already been snapped at that instant - nothing is interpolated, and
    nothing that had not happened yet survives into the output.
    """
    sb = copy.deepcopy(scoreboard)
    sm = copy.deepcopy(summary)
    event = str((sm.get("header") or {}).get("id") or "")
    game_seconds = max(0, int(game_seconds))

    drives = _drives(sm)
    every = _all_plays(sm)
    included: list[list[dict]] = []
    for d in drives:
        included.append([p for p in (d.get("plays") or [])
                         if play_seconds(p) <= game_seconds])
    flat = [p for group in included for p in group]
    finished = bool(every) and len(flat) == len(every)

    head = (sm.get("header") or {})
    comps = (head.get("competitions") or [{}])
    comp = comps[0] if comps else {}
    sides = {(c.get("homeAway") or "").lower(): c for c in (comp.get("competitors") or [])}

    ev = _event(sb, event)
    ev_comp = ((ev.get("competitions") or [{}])[0]) if ev else {}

    note = {"event": event, "gameSeconds": game_seconds,
            "playsIncluded": len(flat), "playsTotal": len(every),
            "boxscore": BOXSCORE_NOTE}

    if not flat:
        # Nothing has been snapped, so there is nothing to report but "not yet".
        status = _status_pre(comp.get("status") or {})
        _set_status(comp, ev, ev_comp, status)
        _set_scores(sides, ev_comp, 0, 0)
        sm["drives"] = {"previous": []}
        sm["winprobability"] = []
        sm["scoringPlays"] = []
        comp.pop("situation", None)
        ev_comp.pop("situation", None)
        for c in (comp.get("competitors") or []):
            c["possession"] = False
            c.pop("linescores", None)
        note.update({"state": "pre", "clock": "", "period": 0})
        sm["replay"] = note
        sb["replay"] = dict(note)
        return sb, sm

    last = flat[-1]
    last_period = _num((last.get("period") or {}).get("number"), 1)

    if finished:
        # Every play is in, so the captured status is the true one - and it is
        # the only status here that was not derived. Deriving "post" would
        # discard ESPN's own final detail string for a worse copy of it.
        status = comp.get("status") or {}
        period_now = _num(status.get("period"), last_period)
    else:
        period_now = game_seconds // PERIOD_SECONDS + 1
        remaining = PERIOD_SECONDS - (game_seconds % PERIOD_SECONDS)
        if period_now != last_period:
            # Between the end of a period and the first snap of the next one
            # the derived period runs ahead of the game. The last play is the
            # last thing that actually happened, so it wins.
            period_now = last_period
            remaining = clock_seconds((last.get("clock") or {}).get("displayValue"))
        status = _status_in(period_now, remaining)
        _set_status(comp, ev, ev_comp, status)

    home_score = _num(last.get("homeScore"), 0)
    away_score = _num(last.get("awayScore"), 0)
    _set_scores(sides, ev_comp, home_score, away_score)

    ls_home, ls_away = _linescores(flat, period_now)
    if sides.get("home") is not None:
        sides["home"]["linescores"] = ls_home
    if sides.get("away") is not None:
        sides["away"]["linescores"] = ls_away

    sit = _situation(last)
    if finished:
        # Nobody has the ball after the whistle, and ESPN sends no situation.
        comp.pop("situation", None)
        ev_comp.pop("situation", None)
        for c in (comp.get("competitors") or []):
            c["possession"] = False
    else:
        comp["situation"] = sit
        if ev_comp:
            ev_comp["situation"] = dict(sit)
        for c in (comp.get("competitors") or []):
            c["possession"] = str(((c.get("team") or {}).get("id")) or "") == sit["possession"]

    # Rebuild the drive list. A drive with no included play has not begun, so it
    # is dropped entirely rather than shipped empty - an empty drive renders as
    # a real possession that gained nothing.
    previous, current = [], None
    for d, plays in zip(drives, included):
        if not plays:
            continue
        if len(plays) == len(d.get("plays") or []):
            previous.append({**d, "plays": plays})
        else:
            current = _in_progress_drive(d, plays)
    sm["drives"] = {"previous": previous}
    if current is not None:
        sm["drives"]["current"] = current

    ids = {str(p.get("id")) for p in flat}
    sm["scoringPlays"] = [sp for sp in (sm.get("scoringPlays") or [])
                          if str(sp.get("id")) in ids]

    # Win probability is one point per play plus a pre-game point whose playId
    # is the opening drive's, not a play's. Cutting on membership alone would
    # throw that first point away, so the cut is positional: keep everything up
    # to and including the last point that names a play which has happened.
    wp = sm.get("winprobability") or []
    keep = 0
    for i, w in enumerate(wp):
        if str(w.get("playId")) in ids:
            keep = i + 1
    sm["winprobability"] = wp[:keep]

    note.update({"state": (status.get("type") or {}).get("state", "in"),
                 "clock": status.get("displayClock", ""),
                 "period": period_now,
                 "homeScore": home_score, "awayScore": away_score})
    sm["replay"] = note
    sb["replay"] = dict(note)
    return sb, sm


def _event(scoreboard: dict, event: str) -> dict:
    for ev in (scoreboard.get("events") or []):
        if str(ev.get("id")) == event:
            return ev
    return {}


def _set_status(comp: dict, ev: dict, ev_comp: dict, status: dict) -> None:
    """The same status in all three places ESPN states it.

    The scoreboard repeats it at `event.status` and at `event.competitions[0]
    .status`, and `live.games()` reads the second while other clients read the
    first. Setting one and not the other produces a game that is live on the
    board and final in the header.
    """
    comp["status"] = copy.deepcopy(status)
    if ev:
        ev["status"] = copy.deepcopy(status)
    if ev_comp:
        ev_comp["status"] = copy.deepcopy(status)


def _set_scores(sides: dict, ev_comp: dict, home: int, away: int) -> None:
    """The running score, in both payloads.

    `winner` goes with it. A finished game is flagged on the competitor that
    won, and a client that reads it will draw the trophy on a game that is
    tied in the third - which is the ending leaking out through a field nobody
    thinks to truncate.
    """
    by_side = {"home": home, "away": away}
    for c in list(sides.values()) + list(ev_comp.get("competitors") or []):
        side = (c.get("homeAway") or "").lower()
        if side in by_side:
            c["score"] = str(by_side[side])
        c.pop("winner", None)


# ──────────────────────────── capture ────────────────────────────

def capture(event: str, dest: pathlib.Path) -> dict:
    """Download one finished game and the slate it sits on, once.

    The slate is fetched first because it is what decides whether the event is
    even on this week's board: a replay whose event is missing from the
    scoreboard drives nothing, since the live tier walks the slate and never
    asks for a game it cannot see. If the current week does not carry it, the
    single-date board for the game's own kickoff does.
    """
    dest.mkdir(parents=True, exist_ok=True)
    summary = _get_json(with_key(summary_url(event)))
    if not _all_plays(summary):
        raise SystemExit(f"Event {event} has no play-by-play to replay.")
    board = _get_json(with_key(scoreboard_url()))
    if not _event(board, event):
        date = ((summary.get("header") or {}).get("competitions") or [{}])[0].get("date", "")
        day = date[:10].replace("-", "")
        if not day:
            raise SystemExit(f"Event {event} is not on this week's scoreboard "
                             "and carries no date to look it up by.")
        board = _get_json(with_key(scoreboard_url(f"?dates={day}")))
        if not _event(board, event):
            raise SystemExit(f"Event {event} is not on the scoreboard for {day}.")
    (dest / "scoreboard.json").write_text(json.dumps(board))
    (dest / f"{event}.json").write_text(json.dumps(summary))
    return {"event": event, "plays": len(_all_plays(summary)),
            "drives": len(_drives(summary)), "seconds": total_seconds(summary),
            "dir": str(dest)}


def load(source: pathlib.Path, event: str) -> tuple[dict, dict]:
    board = source / "scoreboard.json"
    game = source / f"{event}.json"
    if not (board.exists() and game.exists()):
        raise SystemExit(f"No capture in {source}. Run with --capture first.")
    return json.loads(board.read_text()), json.loads(game.read_text())


def write_frame(out: pathlib.Path, event: str, sb: dict, sm: dict) -> None:
    """Write both files atomically.

    A reader polling every twenty seconds will eventually read while this
    writes, and a half-written scoreboard raises inside `_fetch`, which the
    live tier reads as ESPN blocking us and backs off from for two minutes.
    A rename is the cheap way to never let that happen.
    """
    out.mkdir(parents=True, exist_ok=True)
    for name, payload in ((f"{event}.json", sm), ("scoreboard.json", sb)):
        tmp = out / f".{name}.tmp"
        tmp.write_text(json.dumps(payload))
        tmp.replace(out / name)


def run_hint(out: pathlib.Path) -> str:
    return (f"FANTASYEDGE_SCOREBOARD_FILE={out}/scoreboard.json "
            f"FANTASYEDGE_SUMMARY_DIR={out} "
            "python3 -m fantasyedge api --host 0.0.0.0")


def run(event: str, out: pathlib.Path, speed: float = 60.0, at: int | None = None,
        do_capture: bool = False, start: int = 0, interval: float = 1.0,
        source: pathlib.Path | None = None, log=print) -> dict:
    """Write frames until the game runs out, or one frozen frame with `at`."""
    out = pathlib.Path(out)
    source = pathlib.Path(source) if source else out / "source"
    if do_capture or not (source / f"{event}.json").exists():
        log(f"Capturing event {event} from ESPN ...")
        info = capture(event, source)
        log(f"  {info['plays']} plays, {info['drives']} drives, "
            f"{info['seconds']}s of game clock")
    board, summary = load(source, event)
    length = total_seconds(summary)

    if at is not None:
        sb, sm = frame(board, summary, at)
        write_frame(out, event, sb, sm)
        return {"event": event, "at": at, "length": length,
                "frames": 1, "state": sm["replay"]["state"],
                "clock": sm["replay"]["clock"], "period": sm["replay"]["period"],
                "out": str(out), "run": run_hint(out), "boxscore": BOXSCORE_NOTE}

    began = time.monotonic()
    frames = 0
    last_state = "pre"
    while True:
        game_at = int(start + (time.monotonic() - began) * speed)
        sb, sm = frame(board, summary, game_at)
        write_frame(out, event, sb, sm)
        frames += 1
        last_state = sm["replay"]["state"]
        if game_at >= length:
            log(f"Replay complete: {frames} frames, final "
                f"{sm['replay'].get('awayScore')}-{sm['replay'].get('homeScore')}")
            break
        if frames == 1 or frames % 15 == 0:
            log(f"  {sm['replay']['clock']} {ordinal(sm['replay']['period'])}  "
                f"{sm['replay'].get('awayScore')}-{sm['replay'].get('homeScore')}  "
                f"{sm['replay']['playsIncluded']}/{sm['replay']['playsTotal']} plays")
        time.sleep(max(0.1, interval))
    return {"event": event, "frames": frames, "length": length, "state": last_state,
            "out": str(out), "run": run_hint(out), "boxscore": BOXSCORE_NOTE}
