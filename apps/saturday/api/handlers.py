"""Route handlers: a source in, a JSON-ready dict out. No HTTP.

Clients render these payloads and hold no logic of their own - which game is
the spotlight, whether a result is an upset, where the ball is, what colour a
chip is, what just changed: all of it is decided here, once, so a headset, a
phone and a browser cannot disagree. The shapes are pinned by
contracts/*.schema.json.

The only module state is a cache of recorded frames, which never change.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import time

from cfb import changes, colors, leverage, parse, reconstruct
from cfb.game import game_from_summary
from cfb.sources import BadStamp, Source, seconds_between, stamp_of

VERSION = 1

# How far back the whip-around feed reaches, in seconds of the source's clock.
FEED_SECONDS = 20 * 60

class NotFound(Exception):
    def __init__(self, message: str, reason: str):
        super().__init__(message)
        self.reason = reason


class BadRequest(Exception):
    pass


def _iso(stamp: str) -> str:
    """20260913T003400Z -> 2026-09-13T00:34:00Z"""
    return dt.datetime.strptime(stamp[:15], "%Y%m%dT%H%M%S").strftime("%Y-%m-%dT%H:%M:%SZ")


def _now_stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


_eastern = changes.eastern


def positioned(source: Source, at: str | None) -> Source:
    """The source read at a replay moment, or unchanged when no moment is asked."""
    if not at:
        return source
    try:
        return source.at(stamp_of(at))
    except BadStamp as exc:
        raise BadRequest(str(exc)) from None


def _ranked(board: dict) -> list[dict]:
    return leverage.rank(parse.slate_records(board))


_FRAMES: dict[tuple[str, str], list[dict]] = {}


def _ranked_at(source: Source, stamp: str | None, load, copy: bool = False) -> list[dict]:
    """A board already read at a stamp never changes - a recorded frame, or a
    live board fetched at that second - so its ranked records are worked out
    once and the board is not read again. History frames are only read; the
    current frame is copied because it goes out in a payload."""
    if not stamp:
        return _ranked(load())
    key = (source.label.split("@")[0], stamp)
    if key not in _FRAMES:
        if len(_FRAMES) > 512:
            _FRAMES.clear()
        _FRAMES[key] = _ranked(load())
    return json.loads(json.dumps(_FRAMES[key])) if copy else _FRAMES[key]


def clock(source: Source) -> dict | None:
    frames = source.frames()
    now = source.stamp()
    if not frames or not now or now not in frames:
        return None
    return {"stamp": now, "at": _iso(now), "label": _eastern(now), "index": frames.index(now), "frames": len(frames),
            "offsetSeconds": seconds_between(frames[0], now), "durationSeconds": seconds_between(frames[0], frames[-1])}


def slate(source: Source, at: str | None = None) -> dict:
    source = positioned(source, at)
    history = source.history(FEED_SECONDS)
    if not history:
        raise NotFound(f"{source.label} has no scoreboard at that moment.", "the recording had not started at that moment")
    now, load = history[-1]
    games = _ranked_at(source, now, load, copy=True)
    ranked_history = [(s, _ranked_at(source, s, b)) for s, b in history[:-1]] + [(now, games)]
    previous = ranked_history[-2][1] if len(ranked_history) > 1 else None

    counts = {"live": 0, "pre": 0, "post": 0, "delayed": 0}
    for g in games:
        s = g["status"]
        counts["delayed" if s["delayed"] else {"in": "live", "post": "post"}.get(s["state"], "pre")] += 1
    return {
        "version": VERSION,
        "league": "college-football",
        "asOf": _iso(now) if now else _iso(_now_stamp()),
        "source": source.label,
        "replay": bool(source.replay),
        "clock": clock(source),
        "counts": counts,
        "spotlight": leverage.spotlight(games),
        "sections": leverage.sections(games),
        "leverageCaveat": leverage.CAVEAT,
        "reconstructed": _reconstructed(games),
        "changes": changes.diff(previous, games, ranked_history[-1][0]),
        "feed": changes.feed(ranked_history),
        "changesCaveat": changes.CAVEAT,
        "games": games,
    }


def _reconstructed(games: list[dict]) -> dict | None:
    """Say it on the board when any tile was rebuilt rather than recorded."""
    rebuilt = sum(1 for g in games if g.get("provenance") == "reconstructed")
    return {"games": rebuilt, "caveats": reconstruct.CAVEATS} if rebuilt else None


def game(source: Source, event: str, at: str | None = None) -> dict:
    source = positioned(source, at)
    data = source.summary(event)
    if not data:
        raise NotFound(f"No play data for event {event}.", "a game that has not kicked off, or is not in this source, has no summary")
    # INTEGRATE: shared gamecast shaping from fantasy-edge scene/replay branch
    out = game_from_summary(event, data)
    # Rank lives on the slate, not reliably in a summary header; take it from
    # the board so a tile and its detail never show two different ranks.
    stamp = source.stamp()
    board = {g["id"]: g for g in _ranked_at(source, stamp, source.scoreboard)}
    if event in board:
        for side in ("away", "home"):
            if out.get(side) and out[side].get("rank") is None:
                out[side]["rank"] = board[event][side]["rank"]
            if out.get(side):
                out[side]["fill"] = board[event][side]["fill"]
                out[side]["hatch"] = board[event][side]["hatch"]
    return {"version": VERSION, "source": source.label, "replay": bool(source.replay),
            "asOf": _iso(stamp) if stamp else _iso(_now_stamp()),
            "winProbabilityCaveat": "ESPN's model, reproduced as published; not computed here.", **out}


def teams(source: Source) -> dict:
    seen: dict[str, dict] = {}
    for g in parse.slate_records(source.scoreboard()):
        for side in ("away", "home"):
            t = g[side]
            seen.setdefault(t["id"], {k: t[k] for k in ("id", "abbr", "name", "location", "shortName", "color",
                                                          "alternateColor", "logo", "conferenceId", "rank", "record")}
                            # a directory chip is the team's own colour; the away-gives-way
                            # swap only applies inside one matchup
                            | {"fill": colors.chip(t["color"])})
    return {"version": VERSION, "source": source.label,
            "teams": sorted(seen.values(), key=lambda t: (t["location"], t["id"])),
            "caveat": "Teams on this slate only; the full FBS directory arrives with CFBD history."}


def replay(source: Source) -> dict:
    """The recorded night as a timeline a scrubber can draw."""
    frames = source.frames()
    if not frames:
        raise NotFound(f"{source.label} is not a replay.", "only a recorded capture has a timeline")
    return _timeline(source.label, tuple(frames), source)


_TIMELINES: dict[tuple[str, tuple[str, ...]], dict] = {}


def _timeline(label: str, frames: tuple[str, ...], source: Source) -> dict:
    key = (label.split("@")[0], frames)
    if key in _TIMELINES:
        return _TIMELINES[key]
    out_frames, previous = [], None
    for i, stamp in enumerate(frames):
        at_frame = source.at(stamp)
        games = _ranked_at(at_frame, stamp, at_frame.scoreboard)
        found = changes.diff(previous, games, stamp)
        marks = {"scores": sum(c["kind"] == "score" for c in found), "finals": sum(c["kind"] == "final" for c in found),
                 "kickoffs": sum(c["kind"] == "kickoff" for c in found), "upsets": sum(c["kind"] == "upset" for c in found)}
        headline = next((c for c in found if c["kind"] in ("upset", "final", "score")), None)
        out_frames.append({"stamp": stamp, "at": _iso(stamp), "label": _eastern(stamp), "index": i, "frames": len(frames),
                           "offsetSeconds": seconds_between(frames[0], stamp),
                           "durationSeconds": seconds_between(frames[0], frames[-1]),
                           "marks": marks, "headline": headline})
        previous = games
    gaps = [{"from": _iso(a), "to": _iso(b), "minutes": round(seconds_between(a, b) / 60, 1)}
            for a, b in zip(frames, frames[1:]) if seconds_between(a, b) > 180]
    out = {"version": VERSION, "source": label, "start": _iso(frames[0]), "end": _iso(frames[-1]),
           "frames": out_frames, "gaps": gaps,
           "caveat": ("A recording, one scoreboard about a minute. Where the recorder lost the network the timeline "
                      "has a gap, and the board jumps across it rather than inventing what happened in between.")}
    _TIMELINES[key] = out
    return out


def _digest(payload: dict) -> str:
    return hashlib.sha1(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def stream(source: Source, *, at: str | None = None, speed: float = 1.0, games: tuple[str, ...] = (),
           poll: float | None = None, sleep=time.sleep, budget=None):
    """The events of `/api/stream`, as (name, payload) pairs, pacing itself.

    Live: every `poll` seconds, the slate when it changed and each open game's
    detail when it changed. Summaries are asked for only for `games`, and a
    budgeted source decides whether that is a request or a cached answer.

    Replay: from `at` (or the first frame) through the last, one frame at a
    time, sleeping the recorded gap between frames divided by `speed`. A
    `clock` event leads every frame so a scrubber can follow it, and `end`
    closes the night.
    """
    games = tuple(dict.fromkeys(g for g in games if g))
    frames = source.frames()
    if frames:
        try:
            start = stamp_of(at) if at else frames[0]
        except BadStamp as exc:
            raise BadRequest(str(exc)) from None
        run = [f for f in frames if f >= start] or frames[-1:]
        speed = max(0.1, float(speed))
        for i, stamp in enumerate(run):
            here = source.at(stamp)
            tick = clock(here)
            yield "clock", {**tick, "speed": speed}
            yield "slate", slate(here)
            for event in games:
                try:
                    yield "game", game(here, event)
                except NotFound:
                    pass
            if i + 1 < len(run):
                sleep(seconds_between(stamp, run[i + 1]) / speed)
        yield "end", {"stamp": run[-1], "reason": "the recording ends here"}
        return

    if at:
        raise BadRequest(f"{source.label} is live; only a replay can be streamed from a moment")
    from cfb.league import BUDGET
    poll = poll or BUDGET["scoreboardSeconds"]
    sent: dict[str, str] = {}
    while True:
        payload = slate(source)
        digest = _digest({k: v for k, v in payload.items() if k != "asOf"})
        if sent.get("slate") != digest:
            sent["slate"] = digest
            yield "slate", payload
        for event in games:
            try:
                detail = game(source, event)
            except NotFound:
                continue
            digest = _digest({k: v for k, v in detail.items() if k != "asOf"})
            if sent.get(event) != digest:
                sent[event] = digest
                yield "game", detail
        if budget is not None:
            yield "budget", budget()
        else:
            yield "ping", {}
        sleep(poll)
