"""Last week's games: which week that was, what was on it, and what to watch.

`replay.py` can replay any finished game, given its event id. Getting that id
was the part a person could not do: `find_event` wants a season, a week and a
club, which is three things you have to know before you can watch the game you
half-remember hearing about. This is the other half - the slate itself.

THE WEEK IS READ, NEVER ASSUMED
-------------------------------
ESPN's own scoreboard says which week it is serving (`week.number`) and which
season (`leagues[].season`), so the boundary is read off the feed rather than
computed from today's date. That matters on the two days a naive calendar gets
wrong: a Tuesday, when last week's Monday night game finished six hours ago and
ESPN has already rolled to the next week, and a Thursday, when this week has
kicked off but only one game has been played.

`last_finished` therefore asks a different question than "what is today":
**the most recent week in which every game is final.** A week with a game still
to come is not finished, however many of its games are over, because a picker
that offered it would list games that have not happened. Walking back a week at
a time answers Thursday, Sunday night and the Tuesday after all the same way,
and crosses a season boundary by stepping into the previous postseason.

WHAT IS WORTH WATCHING, AND WHAT THAT COSTS
-------------------------------------------
A picker's whole job is the one line under the matchup. Two sources can answer
it and they cost different amounts:

  * **The slate, one request for sixteen games.** Final margin, overtime, and
    - from `linescores` - the biggest deficit the winner came back from, at
      quarter resolution. Enough to sort the week.
  * **The capture, one request per game.** The play-by-play: every lead change
    with its clock, and whether the winning score came in the last minute.

So a reason carries `precision`: "quarter" from the slate alone, "play" once
the game is pulled. The picker never pretends the cheap answer is the dear one,
and `week_games` upgrades a row in place the moment its capture exists.

SPOILERS
--------
Somebody replaying last week's game may not know how it ended, so a row's
`away.score`/`home.score` and its final-score label are withheld unless the
caller asks for them. The reasons are written to survive that: "3 lead changes"
and "won on a last-second field goal" say why the game is worth an hour without
saying who won. `reveal=True` adds the scores back for a caller who wants them.
"""

from __future__ import annotations

import json
import pathlib
import time

from .live import _get_json, scoreboard_url, with_key
from .replay import (_all_plays, _event, _num, capture, capture_is_complete,
                     clock_seconds, period_lengths, play_offsets, play_seconds,
                     scoreboard_path, total_seconds)

# ESPN's season types. 1 preseason, 2 regular season, 3 postseason.
PRESEASON, REGULAR, POSTSEASON = 1, 2, 3

# The last week number in each season type, used to step back over a boundary.
LAST_WEEK = {REGULAR: 18, POSTSEASON: 5, PRESEASON: 4}

# How many weeks back `last_finished` will walk before giving up. Three covers
# a bye-adjacent gap and the seasons' edges; more than that means the feed is
# not what we think it is, which should be said rather than searched around.
MAX_BACK = 4

QUARTER_NOTE = ("Read from quarter scores only: lead changes inside a quarter "
                "are invisible until the game is pulled.")
PLAY_NOTE = "Read from the game's own play-by-play."


def season_week(board: dict) -> dict:
    """`{season, seasontype, week}` as the board itself reports them."""
    league = (board.get("leagues") or [{}])[0]
    season = league.get("season") or board.get("season") or {}
    kind = season.get("type")
    if isinstance(kind, dict):
        seasontype = _num(kind.get("type"), REGULAR)
    else:
        seasontype = _num(kind, REGULAR)
    week = _num((board.get("week") or {}).get("number"), 0)
    if not week:
        week = _num((season.get("week") or {}).get("number"), 0)
    return {"season": _num(season.get("year"), 0),
            "seasontype": seasontype or REGULAR,
            "week": week}


def week_url(season: int, week: int, seasontype: int = REGULAR) -> str:
    return scoreboard_url(f"?dates={int(season)}&seasontype={int(seasontype)}"
                          f"&week={int(week)}")


def _fetch(http=None):
    return http or (lambda url: _get_json(with_key(url)))


def week_board(season: int, week: int, seasontype: int = REGULAR, http=None) -> dict:
    return _fetch(http)(week_url(season, week, seasontype))


def _state(ev: dict) -> str:
    comp = (ev.get("competitions") or [{}])[0]
    return ((comp.get("status") or {}).get("type") or {}).get("state") or ""


def week_state(board: dict) -> str:
    """"final" only when every game on the board is over.

    A board with nothing on it is "empty", which is a different thing from a
    week whose games are all still to come: an out-of-range week number returns
    the former, and a pre-season gap the latter.
    """
    states = [_state(ev) for ev in (board.get("events") or [])]
    if not states:
        return "empty"
    if all(s == "post" for s in states):
        return "final"
    if any(s == "in" for s in states):
        return "playing"
    return "pre" if all(s == "pre" for s in states) else "partial"


def previous_week(season: int, week: int, seasontype: int) -> tuple[int, int, int]:
    """The week before this one, stepping across a season's seams."""
    if week > 1:
        return season, week - 1, seasontype
    if seasontype == POSTSEASON:
        return season, LAST_WEEK[REGULAR], REGULAR
    if seasontype == REGULAR:
        # Week 1 of a regular season follows the previous season's playoffs.
        return season - 1, LAST_WEEK[POSTSEASON], POSTSEASON
    return season, LAST_WEEK[PRESEASON], PRESEASON


def last_finished(http=None, board: dict | None = None,
                  max_back: int = MAX_BACK) -> dict:
    """The most recent week whose every game is final, and its board.

    Starts at whatever week the feed is currently serving - which on a Tuesday
    is already the week that just ended - and walks back until a week is whole.
    """
    get = _fetch(http)
    board = board if board is not None else get(scoreboard_url())
    at = season_week(board)
    season, week, kind = at["season"], at["week"], at["seasontype"]
    tried = []
    for step in range(max_back + 1):
        if step:
            season, week, kind = previous_week(season, week, kind)
            board = get(week_url(season, week, kind))
        state = week_state(board)
        tried.append({"season": season, "week": week, "seasontype": kind,
                      "state": state, "games": len(board.get("events") or [])})
        if state == "final":
            return {"season": season, "week": week, "seasontype": kind,
                    "board": board, "current": at, "tried": tried,
                    "isCurrent": step == 0}
    raise SystemExit(
        "No finished week in the last "
        f"{max_back + 1} tried: {json.dumps(tried)}")


# ───────────────────────── what is worth watching ─────────────────────────


def _sides(ev: dict) -> tuple[dict, dict]:
    comp = (ev.get("competitions") or [{}])[0]
    by = {(c.get("homeAway") or "").lower(): c for c in (comp.get("competitors") or [])}
    return by.get("away") or {}, by.get("home") or {}


def _club(c: dict) -> dict:
    team = c.get("team") or {}
    return {"abbr": (team.get("abbreviation") or "").upper(),
            "name": team.get("shortDisplayName") or team.get("displayName") or "",
            "color": team.get("color") or "", "alt": team.get("alternateColor") or ""}


def _periods(c: dict) -> list[int]:
    return [_num(p.get("value"), 0) for p in (c.get("linescores") or [])]


def _overtimes(ev: dict) -> int:
    away, home = _sides(ev)
    return max(0, max(len(_periods(away)), len(_periods(home))) - 4)


def _quarter_swing(ev: dict) -> tuple[int, int]:
    """(lead changes, biggest deficit the winner erased) at quarter ends.

    Both are lower bounds. A team that went ahead and fell behind inside one
    quarter shows up as nothing here, which is why every row built from this
    carries `precision: "quarter"`.
    """
    away, home = _sides(ev)
    a_q, h_q = _periods(away), _periods(home)
    a = h = 0
    lead = 0                        # -1 away ahead, +1 home ahead, 0 level
    changes, worst = 0, 0
    final_a, final_h = _num(away.get("score"), 0), _num(home.get("score"), 0)
    winner = 1 if final_h > final_a else (-1 if final_a > final_h else 0)
    for i in range(max(len(a_q), len(h_q))):
        a += a_q[i] if i < len(a_q) else 0
        h += h_q[i] if i < len(h_q) else 0
        now = 1 if h > a else (-1 if a > h else 0)
        if now and lead and now != lead:
            changes += 1
        if now:
            lead = now
        if winner:
            behind = (a - h) if winner > 0 else (h - a)
            worst = max(worst, behind)
    return changes, worst


def _play_swing(summary: dict) -> dict:
    """Lead changes, the last one's clock, and the winning score's timing.

    Read from the scoring plays alone, which is not a shortcut - it is the only
    reliable order. ESPN stamps every play with the score, but not always the
    score *at* that play: on event 401772949 the two timeouts that follow the
    winning touchdown are stamped 37-36, the score before its two-point try,
    and the game's own last record is stamped 37-38. Walking every play in
    order therefore shows the lead changing hands twice more than it did and
    puts the winning score on "END GAME". A lead can only change on a play that
    scores, so only those are counted.
    """
    plays = _all_plays(summary)
    if not plays:
        return {}
    lengths, offsets = period_lengths(summary), play_offsets(summary)
    scoring = [p for p in plays if p.get("scoringPlay")]
    lead, changes, last_change = 0, 0, None
    winning_at = None
    for p in scoring:
        a, h = _num(p.get("awayScore"), 0), _num(p.get("homeScore"), 0)
        now = 1 if h > a else (-1 if a > h else 0)
        if now and lead and now != lead:
            changes += 1
            last_change = p
        if now:
            lead = now
    # The final score is the game's, not a play's: the last record carries it
    # even when the last scoring play does not (a defensive two-point try, a
    # correction applied after the whistle).
    final_a = _num(plays[-1].get("awayScore"), 0)
    final_h = _num(plays[-1].get("homeScore"), 0)
    winner = 1 if final_h > final_a else (-1 if final_a > final_h else 0)
    # The winning score: the scoring play after which the winner was never
    # caught again.
    ahead_since = None
    for p in scoring:
        a, h = _num(p.get("awayScore"), 0), _num(p.get("homeScore"), 0)
        now = 1 if h > a else (-1 if a > h else 0)
        if winner and now == winner and ahead_since is None:
            ahead_since = p
        elif winner and now != winner:
            ahead_since = None
    if ahead_since is not None:
        winning_at = {
            "period": _num((ahead_since.get("period") or {}).get("number"), 0),
            "clock": ((ahead_since.get("clock") or {}).get("displayValue") or ""),
            "text": (ahead_since.get("text") or "")[:120],
            "seconds": play_seconds(ahead_since, lengths, offsets)}
    return {"changes": changes, "winning": winning_at,
            "lastChange": ({"period": _num((last_change.get("period") or {}).get("number"), 0),
                            "clock": ((last_change.get("clock") or {}).get("displayValue") or "")}
                           if last_change is not None else None),
            "length": total_seconds(summary)}


def _kind(text: str) -> str:
    low = (text or "").lower()
    if "field goal" in low and "no good" not in low:
        return "field goal"
    if "touchdown" in low or " td" in low:
        return "touchdown"
    if "safety" in low:
        return "safety"
    return "score"


def reasons(ev: dict, summary: dict | None = None) -> dict:
    """Why this game is worth an hour, without saying who won.

    Returns `{lines, precision, note, score}`. `lines` is ordered best first
    and every line is spoiler-safe: it may say a game was close, went to
    overtime or turned over five times, and may never say which side came out
    of it ahead.
    """
    away, home = _sides(ev)
    a, h = _num(away.get("score"), 0), _num(home.get("score"), 0)
    margin, total = abs(a - h), a + h
    overtimes = _overtimes(ev)
    q_changes, comeback = _quarter_swing(ev)

    swing = _play_swing(summary) if summary else {}
    exact = bool(swing)
    changes = swing.get("changes", q_changes) if exact else q_changes

    lines: list[str] = []
    score = 0.0
    if overtimes >= 2:
        lines.append(f"{overtimes} overtimes")
        score += 55 + 10 * overtimes
    elif overtimes == 1:
        lines.append("Went to overtime")
        score += 45

    won_late = False
    if exact and swing.get("winning"):
        w = swing["winning"]
        left = clock_seconds(w.get("clock"))
        if w.get("period", 0) >= 4 and left <= 120:
            when = "the final minute" if left <= 60 else "the last two minutes"
            lines.append(f"Won on a {_kind(w.get('text'))} in {when}")
            score += 35 if left <= 60 else 22
            won_late = True

    if changes >= 2:
        lines.append(f"{changes} lead changes")
        score += 7 * min(changes, 8)
    elif changes == 1:
        lines.append("The lead changed hands")
        score += 7

    if not won_late and margin <= 3 and not overtimes:
        lines.append("Decided by a field goal or less")
        score += 30
    elif not won_late and margin <= 8 and not overtimes:
        lines.append("A one-score game")
        score += 20

    if comeback >= 14:
        lines.append(f"A {comeback}-point comeback")
        score += comeback
    elif comeback >= 10:
        lines.append(f"Won after trailing by {comeback}")
        score += comeback * 0.8

    if total >= 60:
        lines.append(f"{total} points between them")
        score += 12
    if margin >= 25:
        lines.append("A rout")
        score -= 8

    if not lines:
        lines.append("A straight-ahead game")
    return {"lines": lines[:3], "precision": "play" if exact else "quarter",
            "note": PLAY_NOTE if exact else QUARTER_NOTE, "score": round(score, 1)}


def _kickoff(ev: dict) -> str:
    return ((ev.get("competitions") or [{}])[0]).get("date") or ev.get("date") or ""


def _final_label(ev: dict) -> str:
    comp = (ev.get("competitions") or [{}])[0]
    return ((comp.get("status") or {}).get("type") or {}).get("shortDetail") or ""


def game_row(ev: dict, summary: dict | None = None, reveal: bool = False,
             pulled: bool = False) -> dict:
    """One line in the picker.

    Scores and the "Final/OT" label are only present when `reveal` is set; the
    shape is the same either way, so a client never has to branch on which kind
    of row it received.
    """
    away, home = _sides(ev)
    row = {"event": str(ev.get("id") or ""),
           "name": ev.get("shortName") or "",
           "kickoff": _kickoff(ev),
           "away": _club(away), "home": _club(home),
           "pulled": bool(pulled),
           "complete": capture_is_complete(summary) if summary else None,
           "spoiler": bool(reveal)}
    info = reasons(ev, summary)
    row["reasons"] = info["lines"]
    row["reason"] = info["lines"][0] if info["lines"] else ""
    row["precision"] = info["precision"]
    row["caveat"] = info["note"]
    row["watchability"] = info["score"]
    if summary:
        row["length"] = total_seconds(summary)
        row["plays"] = len(_all_plays(summary))
    if reveal:
        row["away"] = {**row["away"], "score": _num(away.get("score"), 0)}
        row["home"] = {**row["home"], "score": _num(home.get("score"), 0)}
        row["final"] = _final_label(ev)
    return row


def _summary_for(source: pathlib.Path | None, event: str) -> dict | None:
    if not source:
        return None
    path = pathlib.Path(source) / f"{event}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def week_games(board: dict, source: pathlib.Path | None = None,
               reveal: bool = False) -> list[dict]:
    """Every game on a board as picker rows, best first.

    A game already captured under `source` is read for its play-by-play, which
    upgrades its reasons from quarter resolution to play resolution without a
    request. Everything else is answered from the board alone.
    """
    rows = []
    for ev in (board.get("events") or []):
        event = str(ev.get("id") or "")
        summary = _summary_for(source, event)
        rows.append(game_row(ev, summary, reveal=reveal, pulled=summary is not None))
    rows.sort(key=lambda r: (-r["watchability"], r["kickoff"]))
    return rows


# ───────────────────────────── pulling a week ─────────────────────────────


def pull_week(board: dict, dest: pathlib.Path, http=None, log=None,
              refresh: bool = False, only: list[str] | None = None) -> dict:
    """Capture every finished game on a board, skipping what is already there.

    One board serves the whole week, so it is written once per event rather
    than re-fetched per game: `capture()` spends one to three requests finding
    the slate a single game sits on, which is right for one game and wasteful
    sixteen times over. That makes a week cost one request per game plus the
    board already in hand.

    Re-running is free and offline: a game whose summary and slate are both on
    disk is skipped, so a week pulled once opens instantly for ever after.
    """
    get = _fetch(http)
    dest = pathlib.Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    say = log or (lambda *_: None)
    events = [ev for ev in (board.get("events") or [])
              if _state(ev) == "post" and (not only or str(ev.get("id")) in set(only))]
    out = {"pulled": [], "cached": [], "failed": [], "requests": 0,
           "dir": str(dest), "games": len(events)}
    began = time.monotonic()
    from .live import summary_url

    for i, ev in enumerate(events, 1):
        event = str(ev.get("id") or "")
        game, slate = dest / f"{event}.json", scoreboard_path(dest, event)
        if not refresh and game.exists() and slate.exists():
            out["cached"].append(event)
            say(f"  [{i}/{len(events)}] {ev.get('shortName', event)}  already pulled")
            continue
        try:
            summary = get(summary_url(event))
            out["requests"] += 1
            plays = len(_all_plays(summary))
            if not plays:
                raise ValueError("no play-by-play")
            if _event(board, event):
                slate.write_text(json.dumps(board))
                game.write_text(json.dumps(summary))
            else:
                # The week board does not carry it; let capture find its own.
                capture(event, dest, http=http)
                out["requests"] += 2
            out["pulled"].append(event)
            say(f"  [{i}/{len(events)}] {ev.get('shortName', event)}  "
                f"{plays} plays, {total_seconds(summary)}s")
        except Exception as exc:                       # noqa: BLE001 - reported, not raised
            out["failed"].append({"event": event, "error": str(exc)})
            say(f"  [{i}/{len(events)}] {ev.get('shortName', event)}  FAILED: {exc}")
    out["seconds"] = round(time.monotonic() - began, 1)
    return out


def cached_board(source: pathlib.Path | None) -> dict | None:
    """The newest week slate already on disk, or None.

    `pull_week` writes the week's own board beside every game it captures, so a
    week that has been pulled carries its own slate and needs no request to be
    listed again. The newest is chosen by the kickoff dates on the board rather
    than by file time, so re-pulling an old week does not make it "last week".
    """
    if not source:
        return None
    best, best_key = None, ""
    for path in sorted(pathlib.Path(source).glob("scoreboard-*.json")):
        try:
            board = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        events = board.get("events") or []
        if len(events) < 2:            # a single-game slate is a capture, not a week
            continue
        key = max((_kickoff(ev) for ev in events), default="")
        if key > best_key:
            best, best_key = board, key
    return best


def last_week(http=None, source: pathlib.Path | None = None, reveal: bool = False,
              board: dict | None = None, offline: bool = False) -> dict:
    """The whole answer: which week, its games, and how much of it is local.

    A pulled week answers without a request: `offline` reads the slate the pull
    left behind, and a network failure falls back to it rather than to nothing,
    so the picker still opens on a plane.
    """
    from_disk = False
    if board is None and offline:
        board = cached_board(source)
        from_disk = True
        if board is None:
            raise SystemExit("Nothing pulled yet, so there is no offline week. "
                             "Run `last-week --pull` once while online.")
    if board is None:
        try:
            found = last_finished(http=http)
        except Exception:                          # noqa: BLE001 - fall back, then report
            board = cached_board(source)
            if board is None:
                raise
            found = None
        if board is not None and found is None:
            return _answer(board, source, reveal, offline=True)
        return _answer(found["board"], source, reveal, found=found)
    return _answer(board, source, reveal, offline=from_disk)


def _answer(board: dict, source, reveal: bool, found: dict | None = None,
            offline: bool = False) -> dict:
    at = season_week(board)
    found = found or {"season": at["season"], "week": at["week"],
                      "seasontype": at["seasontype"], "isCurrent": False,
                      "tried": [{**at, "state": week_state(board),
                                 "games": len(board.get("events") or [])}]}
    rows = week_games(board, source=source, reveal=reveal)
    return {"season": found["season"], "week": found["week"],
            "seasontype": found["seasontype"],
            "isCurrentWeek": found.get("isCurrent", False),
            "games": rows,
            "pulled": sum(1 for r in rows if r["pulled"]),
            "total": len(rows),
            "spoilers": bool(reveal),
            "offline": bool(offline),
            "source": str(source) if source else "",
            "tried": found.get("tried", [])}


