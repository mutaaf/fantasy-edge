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
from fantasyedge import whip
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
        # What this source can answer for that game. A capture that sampled its
        # snapshots says "afterFinal" rather than letting a tile look complete
        # and then fail when somebody opens it.
        g["detail"] = source.detail_for(g["id"], s["state"])
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
        state = next((g["status"]["state"] for g in _ranked_at(source, source.stamp(), source.scoreboard)
                      if g["id"] == event), None)
        reason = {"afterFinal": "this capture did not keep this game's snapshots; its play-by-play "
                                "arrives with the final",
                  "unavailable": "this capture kept nothing for this game"}.get(
            source.detail_for(event, state or "pre"),
            "a game that has not kicked off, or is not in this source, has no summary")
        raise NotFound(f"No play data for event {event}.", reason)
    # The board carries the live situation - where the ball is, the down and
    # the distance - which a summary's header does not.
    stamp = source.stamp()
    board = {g["id"]: g for g in _ranked_at(source, stamp, source.scoreboard)}
    raw_situation = {}
    for ev in (source.scoreboard().get("events") or []):
        if str(ev.get("id")) == event:
            raw_situation = ((ev.get("competitions") or [{}])[0].get("situation") or {})
            break
    out = game_from_summary(event, data, raw_situation)
    # Rank lives on the slate, not reliably in a summary header; take it from
    # the board so a tile and its detail never show two different ranks.
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


def scene(source: Source, event: str, at: str | None = None) -> dict:
    """One college game as renderable geometry, from the shared scene package.

    `fantasyedge.scene` owns the stadium: the field and its rules, the bowl,
    the drives as arcs, the moments. Nothing about geometry is decided here -
    this route hands it a gamecast and returns what it builds, so a college
    Saturday and an NFL Sunday are drawn by one renderer from one spec.
    """
    from fantasyedge import scene as shared

    return shared.build(game(source, event, at))


# ── the red zone in the bowl ──────────────────────────────────────────────
#
# The stadium can stand in one game or follow the Saturday. Following it is a
# ranking question Saturday already answers for the wall - `cfb.leverage` -
# and a *staying* question the wall never had to ask, because a wall changes
# nothing when its order changes and the bowl repaints the world.
#
# The staying question is `fantasyedge.whip.choose`, the same hysteresis the
# NFL red-zone channel uses. Only the numbers differ, and they differ for two
# reasons: leverage runs 0..112 where whip's urgency runs 0..100, and a wearer
# standing in a bowl is not a tile on a page.

# How long a game holds the bowl, in seconds. Measured against the recorded
# 19 September slate - 74 games, up to 31 live at once and 9 in the red zone
# together - taking whichever game ranked first each minute changed the bowl
# 94 times in seven and a half hours, 50 of those visits lasting a minute or
# two. At three minutes and five points, the same night changes 51 times, none
# of them shorter than three minutes, and the bowl is on a game 1.0 leverage
# points off the best available. That is the whole trade: a point of leverage
# buys every flicker.
BOWL_DWELL = 180.0
BOWL_MARGIN = 5.0
# Below this a game is dull enough that half the margin is enough to leave it.
BOWL_QUIET = 20.0

# How far back the focus is worked out from. The bowl's game depends on which
# game it was already on, so it is a walk, not a lookup - but it must not be a
# walk from a server's memory, or two headsets that joined at different times
# would be shown different games and a replay would not reproduce. It is a
# pure function of the moment instead, computed from the last half hour of
# frames. Held against a walk from the first frame of the recorded night, a
# thirty-minute look-back gives the same answer at all 450 sampled minutes.
FOCUS_SECONDS = 30 * 60


def _channel_side(team: dict, holder: str | None) -> dict:
    return {"abbr": team.get("abbr") or "", "score": team.get("score") or 0,
            "color": team.get("fill") or team.get("color") or "",
            "rank": team.get("rank"),
            "hasBall": bool(holder) and str(team.get("id")) == str(holder)}


def _channel_row(g: dict, source: Source) -> dict:
    """One game as the channel states it: the same shape the NFL channel
    sends, so one panel reads both."""
    from fantasyedge import scene as shared

    st, sit = g["status"], (g.get("situation") or {})
    return {
        "event": g["id"],
        # Whether the bowl can actually be stood in for this game. A sampled
        # capture kept six games' live snapshots and not the other sixty-eight,
        # and a panel that offers one of those opens onto a black stadium - the
        # same rule the wall's tiles already keep.
        "detail": source.detail_for(g["id"], st["state"]),
        "state": st["state"],
        "label": shared.status_label({"status": st, "period": st.get("period"), "clock": st.get("clock")},
                                     st["state"], "college-football"),
        "kickoff": g.get("kickoff") or "",
        "league": "college-football",
        "situation": sit.get("text") or "",
        "redZone": bool((g.get("flags") or {}).get("redZone")),
        "urgency": g["leverage"]["score"],
        "reason": ", ".join(g["leverage"]["reasons"]),
        "lastPlay": (g.get("lastPlay") or {}).get("text") or "",
        "home": _channel_side(g["home"], sit.get("possession")),
        "away": _channel_side(g["away"], sit.get("possession")),
    }


def _focus(history: list[tuple[str, list[dict]]], source: Source) -> str:
    """Which game the bowl should be in, walked forward over the frames.

    Nothing is remembered between requests: the walk starts cold at the oldest
    frame in the window and arrives at the same answer for every caller asking
    about the same moment.

    A game this source cannot draw is not a candidate, however much it deserves
    the screen. On a live Saturday that excludes nothing; on a sampled capture
    it is the difference between the bowl following the night and the bowl
    going black.
    """
    pick, since = "", ""
    for stamp, ranked in history:
        rows = [{"event": g["id"], "state": g["status"]["state"], "urgency": g["leverage"]["score"]}
                for g in ranked
                if source.detail_for(g["id"], g["status"]["state"]) == "available"]
        held = seconds_between(since, stamp) if since else 0.0
        nxt = whip.choose(rows, pick, held=held, dwell=BOWL_DWELL,
                          margin=BOWL_MARGIN, quiet=BOWL_QUIET)
        if nxt != pick:
            pick, since = nxt, stamp
    return pick


def redzone(source: Source, at: str | None = None) -> dict:
    """Every live game ranked, and the one the bowl should be standing in.

    The client holds no ranking and no dwell - a test asserts the Swift side
    does not reimplement them - so that a headset, a second headset and a
    browser are looking at the same game.
    """
    source = positioned(source, at)
    history = source.history(FOCUS_SECONDS)
    if not history:
        raise NotFound(f"{source.label} has no scoreboard at that moment.",
                       "the recording had not started at that moment")
    now, load = history[-1]
    games = _ranked_at(source, now, load)
    walked = [(s, _ranked_at(source, s, b)) for s, b in history[:-1]] + [(now, games)]

    rows = [_channel_row(g, source) for g in games]
    rows.sort(key=lambda r: (0 if r["state"] == "in" else 1 if r["state"] == "pre" else 2,
                             -r["urgency"], r["event"]))
    live = [r for r in rows if r["state"] == "in"]
    return {
        "version": VERSION,
        "league": "college-football",
        "asOf": _iso(now) if now else _iso(_now_stamp()),
        "source": source.label,
        "replay": bool(source.replay),
        "clock": clock(source),
        "focus": _focus(walked, source),
        "counts": {"total": len(rows), "live": len(live),
                   "redZone": sum(1 for r in live if r["redZone"]),
                   "final": sum(1 for r in rows if r["state"] == "post")},
        "dwellSeconds": BOWL_DWELL,
        "caveat": leverage.CAVEAT,
        "games": rows,
    }


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
