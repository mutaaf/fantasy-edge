"""ESPN college payloads into normalised records.

Two readers: `game_record` turns one scoreboard event into the record a tile
draws, and `status_of` reads any status block, scoreboard or summary header. Both decide whether a
game is over from the status ESPN states, never from the text of the last
play: a college overtime game ends on the scoring play, so Wake Forest-Purdue
(401858224, 2OT) has no "End of Game" play at all.
"""
from __future__ import annotations

import re

from . import colors, reconstruct, text as words
from .league import LOGO, RULES

DELAYED = {"STATUS_DELAYED", "STATUS_RAIN_DELAY"}
STOPPED = {"STATUS_POSTPONED", "STATUS_CANCELED", "STATUS_SUSPENDED", "STATUS_FORFEIT"}


def _int(v, default=None):
    try:
        return int(float(str(v).strip()))
    except (TypeError, ValueError):
        return default


def status_of(status: dict) -> dict:
    """What state a game is in, from ESPN's status block alone."""
    t = status.get("type") or {}
    name = t.get("name") or ""
    period = _int(status.get("period"), 0) or 0
    completed = bool(t.get("completed")) and name.startswith("STATUS_FINAL")
    overtimes = max(0, period - RULES["periods"])
    if not overtimes:
        # A summary's header status carries no period, only "Final/2OT"; read
        # the count from the detail so a summary and a scoreboard agree.
        m = re.search(r"(?:^|/|\s)(\d*)OT\b", t.get("altDetail") or t.get("shortDetail") or t.get("detail") or "")
        if m:
            overtimes = int(m.group(1) or 1)
            period = max(period, RULES["periods"] + overtimes)
    return {
        "state": "post" if completed else ("pre" if t.get("state") == "pre" else "in" if t.get("state") == "in" else t.get("state") or "pre"),
        "name": name,
        "detail": t.get("shortDetail") or t.get("detail") or "",
        "period": period,
        "clock": status.get("displayClock") or "",
        "clockSeconds": float(status.get("clock") or 0.0),
        "completed": completed,
        "delayed": name in DELAYED,
        "stopped": name in STOPPED,
        "overtimes": overtimes,
        "halftime": name == "STATUS_HALFTIME",
    }


def yards_to_goal(text: str | None, offense_abbr: str | None) -> int | None:
    """From "3rd & 6 at TEX 17": the ball is on a side, count from that side.

    The scoreboard's own `yardLine` does not say whose half it is in, so it
    is not used; the text does.
    """
    if not text or not offense_abbr:
        return None
    if text.rstrip().endswith("at 50"):
        return 50
    m = re.search(r"at ([A-Z&\-]+) (\d+)", text)
    if not m:
        return None
    side, n = m.group(1), int(m.group(2))
    return 100 - n if side == offense_abbr else n


def team_record(comp: dict) -> dict:
    t = comp.get("team") or {}
    rank = (comp.get("curatedRank") or {}).get("current")
    if rank is None:
        rank = comp.get("rank")
    rank = _int(rank)
    tid = str(t.get("id") or "")
    return {
        "id": tid,
        "abbr": (t.get("abbreviation") or "").upper(),
        "name": t.get("displayName") or t.get("name") or "",
        "location": t.get("location") or t.get("shortDisplayName") or "",
        "shortName": words.short_name(t.get("location") or t.get("shortDisplayName") or "",
                                      t.get("shortDisplayName"), (t.get("abbreviation") or "").upper()),
        "color": "#" + (t.get("color") or "666666").upper(),
        "alternateColor": "#" + (t.get("alternateColor") or "666666").upper(),
        # The shared scene's names for the same two things: the club's second
        # colour, and the half of its name the end zone is lettered with.
        "altColor": "#" + (t.get("alternateColor") or "666666").upper(),
        "nickname": t.get("name") or "",
        "logo": t.get("logo") or ((t.get("logos") or [{}])[0].get("href")) or LOGO.format(id=tid),
        "conferenceId": str(t.get("conferenceId")) if t.get("conferenceId") is not None else None,
        "rank": rank if rank and rank <= 25 else None,
        "record": ((comp.get("records") or comp.get("record") or [{}])[0] or {}).get("summary", ""),
        "score": _int(comp.get("score")),
    }


def game_record(event: dict) -> dict:
    comp = (event.get("competitions") or [{}])[0]
    st = status_of(event.get("status") or comp.get("status") or {})
    sides = {(c.get("homeAway") or "").lower(): team_record(c) for c in comp.get("competitors") or []}
    away, home = sides.get("away", team_record({})), sides.get("home", team_record({}))
    colors.pair(away, home)
    if st["state"] == "pre":
        away["score"] = home["score"] = None

    sit_raw = comp.get("situation") or {}
    situation = None
    # At halftime and in a delay ESPN leaves the last down-and-distance on the
    # board; drawing it would put a ball on the field during the band show.
    if st["state"] == "in" and sit_raw and not st["halftime"] and not st["delayed"]:
        pos_id = str(sit_raw.get("possession") or "")
        offense = next((s for s in (away, home) if s["id"] == pos_id), None)
        text = sit_raw.get("downDistanceText")
        ytg = yards_to_goal(text, offense["abbr"] if offense else None)
        situation = {
            "possession": pos_id or None,
            "down": _int(sit_raw.get("down")),
            "distance": _int(sit_raw.get("distance")),
            "text": text or None,
            "yardsToGoal": ytg,
            "redZone": bool(sit_raw.get("isRedZone")) or (ytg is not None and ytg <= RULES["red_zone_yards_to_goal"]),
        }

    last = sit_raw.get("lastPlay") or {}
    last_play = None
    # The last play is shown only while the game is on: at halftime or in a
    # delay it is stale, and after the final the result says more.
    readable = words.play(last.get("text"))
    # A last play that is only a clock or a tackler cleans to nothing: no line.
    if situation and readable:
        last_play = {"text": readable, "type": (last.get("type") or {}).get("text") or "",
                     "scoring": bool(_int(last.get("scoreValue"), 0))}

    broadcasts = [n for b in comp.get("broadcasts") or [] for n in b.get("names") or []]
    venue = comp.get("venue") or {}
    addr = venue.get("address") or {}
    return {
        "id": str(event.get("id") or ""),
        # Recorded live, rebuilt from play wallclocks, or still just the
        # schedule. A replay of a backfilled day must never pass one off as
        # another; see cfb/reconstruct.py.
        "provenance": reconstruct.provenance_of(event),
        "kickoff": event.get("date") or comp.get("date") or "",
        "kickoffLabel": words.kickoff_label(event.get("date") or comp.get("date") or "", comp.get("timeValid", True)),
        "status": st,
        "away": away,
        "home": home,
        "situation": situation,
        "lastPlay": last_play,
        "tv": broadcasts[0] if broadcasts else None,
        "venue": {"name": venue.get("fullName") or "", "city": addr.get("city") or "", "state": addr.get("state") or ""},
        "neutralSite": bool(comp.get("neutralSite")),
        "conferenceGame": bool(comp.get("conferenceCompetition")),
        "flags": flags(st, away, home, situation),
    }


def _effective_rank(t: dict) -> int:
    return t["rank"] or 99


def flags(st: dict, away: dict, home: dict, situation: dict | None) -> dict:
    a, h = away.get("score"), home.get("score")
    scored = a is not None and h is not None
    margin = abs(a - h) if scored else None
    upset = upset_alert = False
    if scored and a != h:
        win, lose = (away, home) if a > h else (home, away)
        # An upset: a ranked team loses to an unranked one, or to a team
        # ranked below it. Two unranked teams cannot upset each other.
        underdog_won = lose["rank"] is not None and _effective_rank(win) > _effective_rank(lose)
        upset = st["state"] == "post" and underdog_won
        upset_alert = st["state"] == "in" and underdog_won
    return {
        "live": st["state"] == "in" and not st["delayed"],
        "redZone": bool(situation and situation["redZone"]),
        "overtime": st["overtimes"] > 0,
        "delayed": st["delayed"],
        "upset": upset,
        "upsetAlert": upset_alert,
        "oneScore": margin is not None and margin <= 8,
        "ranked": bool(away["rank"] or home["rank"]),
    }


def slate_records(board: dict) -> list[dict]:
    return [game_record(ev) for ev in board.get("events") or []]
