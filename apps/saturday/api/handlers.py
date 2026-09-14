"""Route handlers: a source in, a JSON-ready dict out. No HTTP, no globals.

Clients render these payloads and hold no logic of their own - which game is
the spotlight, whether a result is an upset, where the ball is, what colour a
chip is: all of it is decided here, once, so a headset, a phone and a browser
cannot disagree. The shapes are pinned by contracts/*.schema.json.
"""
from __future__ import annotations

import datetime as dt

from cfb import colors, leverage, parse
from cfb.game import game_from_summary
from cfb.sources import Source

VERSION = 1


class NotFound(Exception):
    def __init__(self, message: str, reason: str):
        super().__init__(message)
        self.reason = reason


def _iso(stamp: str) -> str:
    """20260913T003400Z -> 2026-09-13T00:34:00Z"""
    return dt.datetime.strptime(stamp[:15], "%Y%m%dT%H%M%S").strftime("%Y-%m-%dT%H:%M:%SZ")


def _board_stamp(board: dict, source: Source) -> str:
    stamp = board.get("capturedAt") or getattr(source, "at", None)
    if stamp:
        return _iso(stamp)
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def slate(source: Source) -> dict:
    board = source.scoreboard()
    games = leverage.rank(parse.slate_records(board))
    counts = {"live": 0, "pre": 0, "post": 0, "delayed": 0}
    for g in games:
        s = g["status"]
        counts["delayed" if s["delayed"] else {"in": "live", "post": "post"}.get(s["state"], "pre")] += 1
    return {
        "version": VERSION,
        "league": "college-football",
        "asOf": _board_stamp(board, source),
        "source": source.label,
        "replay": bool(source.replay),
        "counts": counts,
        "spotlight": leverage.spotlight(games),
        "sections": leverage.sections(games),
        "leverageCaveat": leverage.CAVEAT,
        "games": games,
    }


def game(source: Source, event: str) -> dict:
    data = source.summary(event)
    if not data:
        raise NotFound(f"No play data for event {event}.", "a game that has not kicked off, or is not in this source, has no summary")
    # INTEGRATE: shared gamecast shaping from fantasy-edge scene/replay branch
    out = game_from_summary(event, data)
    # Rank lives on the slate, not reliably in a summary header; take it from
    # the board so a tile and its detail never show two different ranks.
    board = {g["id"]: g for g in parse.slate_records(source.scoreboard())}
    if event in board:
        for side in ("away", "home"):
            if out.get(side) and out[side].get("rank") is None:
                out[side]["rank"] = board[event][side]["rank"]
            if out.get(side):
                out[side]["fill"] = board[event][side]["fill"]
                out[side]["hatch"] = board[event][side]["hatch"]
    return {"version": VERSION, "source": source.label, "replay": bool(source.replay),
            "winProbabilityCaveat": "ESPN's model, reproduced as published; not computed here.", **out}


def teams(source: Source) -> dict:
    seen: dict[str, dict] = {}
    for g in parse.slate_records(source.scoreboard()):
        for side in ("away", "home"):
            t = g[side]
            seen.setdefault(t["id"], {k: t[k] for k in ("id", "abbr", "name", "location", "color",
                                                          "alternateColor", "logo", "conferenceId", "rank", "record")}
                            # a directory chip is the team's own colour; the away-gives-way
                            # swap only applies inside one matchup
                            | {"fill": colors.chip(t["color"])})
    return {"version": VERSION, "source": source.label,
            "teams": sorted(seen.values(), key=lambda t: (t["location"], t["id"])),
            "caveat": "Teams on this slate only; the full FBS directory arrives with CFBD history."}
