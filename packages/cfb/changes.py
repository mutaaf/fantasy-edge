"""What changed on the board between two scoreboard frames.

The design's motion spec spends its animation on a score change, a possession
flip and an upset reveal. Whether one of those happened is a fact about the
game, so it is decided here from two consecutive frames and shipped in the
slate; a client only has to animate a change it has not animated before, which
is what the stable `id` is for.

Two frames are about a minute apart on a recorded night and one budget window
apart live, so a touchdown and its extra point arrive together as seven
points, and a quick score-and-answer can arrive as two changes in one frame.
That is the caveat, and it travels with the payload.
"""
from __future__ import annotations

import datetime as dt

CAVEAT = ("Changes are read by comparing two scoreboard snapshots, about a minute apart on a recording. "
          "Two scores inside one snapshot arrive together, and a score's kind comes from its points, "
          "with ESPN's last play deciding only whether two points were a safety or a conversion. Points taken off the board may be a review "
          "or ESPN correcting its own data; the board does not say which.")

# The order a single game's changes are listed in, most important first.
ORDER = ("final", "upset", "score", "correction", "lead", "kickoff", "resume", "delay", "redZone", "possession")

# Changes worth a line in the whip-around feed; possession and red zone belong
# to the tile, and a kickoff only to a ranked game.
FEED_KINDS = {"score", "correction", "lead", "final", "upset", "kickoff", "delay"}

POINTS_LABEL = {6: "Touchdown", 7: "Touchdown", 8: "Touchdown", 3: "Field goal", 2: "Safety or two-point try",
                1: "Extra point"}


try:
    from zoneinfo import ZoneInfo
    EASTERN = ZoneInfo("America/New_York")
except Exception:                     # no tz database: a September Saturday is EDT
    EASTERN = dt.timezone(dt.timedelta(hours=-4), "ET")


def eastern(stamp: str | None) -> str:
    """A college Saturday is scheduled on the East Coast clock, so every time
    a client shows reads in it, whatever time zone the device is in."""
    try:
        when = dt.datetime.strptime((stamp or "")[:16], "%Y%m%dT%H%M%SZ").replace(tzinfo=dt.timezone.utc)
    except ValueError:
        return ""
    return when.astimezone(EASTERN).strftime("%-I:%M %p ET")


def _iso(stamp: str | None) -> str:
    if not stamp:
        return ""
    try:
        return dt.datetime.strptime(stamp[:16], "%Y%m%dT%H%M%SZ").strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return stamp


def _score_label(points: int, last: dict | None) -> str:
    """Six to eight points in one frame is a touchdown, whatever ESPN's last
    play says: OSU-Texas went 13 to 20 in one frame whose last play was the
    extra point. The play decides only what the points cannot - whether two
    points were a safety or a conversion."""
    if 6 <= points <= 8:
        return "Touchdown"
    if points == 3:
        return "Field goal"
    kind = (last or {}).get("type", "").lower() if (last or {}).get("scoring") else ""
    if points == 2:
        return "Safety" if "safety" in kind else "Two-point try" if "two" in kind else POINTS_LABEL[2]
    return POINTS_LABEL.get(points, f"{points} points")


def _leader(g: dict) -> str | None:
    a, h = g["away"]["score"], g["home"]["score"]
    if a is None or h is None or a == h:
        return None
    return g["away"]["id"] if a > h else g["home"]["id"]


def between(before: dict, after: dict, stamp: str | None) -> list[dict]:
    """Every change to one game from its record in the previous frame to this one."""
    out: list[dict] = []
    at = _iso(stamp)
    sa, sb = before["status"], after["status"]

    def add(kind, label, team=None, points=None):
        out.append({"id": f"{stamp or 'now'}:{after['id']}:{kind}:{team or '-'}", "game": after["id"], "kind": kind,
                    "team": team, "points": points, "label": label, "at": at, "time": eastern(stamp)})

    if sb["state"] == "in" and sa["state"] == "pre" and not sb["delayed"]:
        add("kickoff", "Kickoff")
    if sb["state"] == "post" and sa["state"] != "post":
        add("final", sb["detail"] or "Final", _leader(after))
    if sb["state"] == "in":
        if sb["delayed"] and not sa["delayed"]:
            add("delay", "Delayed")
        elif sa["delayed"] and not sb["delayed"] and sa["state"] == "in":
            add("resume", "Play resumes")

    if sb["state"] != "pre":
        for side in ("away", "home"):
            was, now = before[side]["score"] or 0, after[side]["score"] or 0
            if now > was:
                add("score", _score_label(now - was, after.get("lastPlay")), after[side]["id"], now - was)
            elif now < was:
                # Memphis-Boise State, 00:54-00:58Z: 31, then 37 on a touchdown,
                # 31 again while it was reviewed, then 38 with the extra point.
                # Points leaving the board are news, and never a flourish.
                add("correction", "Points taken off the board", after[side]["id"], now - was)
        old_lead, new_lead = _leader(before), _leader(after)
        if new_lead and old_lead and new_lead != old_lead:
            add("lead", "Takes lead", new_lead)

    if after["flags"]["upset"] and not before["flags"]["upset"]:
        add("upset", "Upset", _leader(after))

    sit_a, sit_b = before.get("situation"), after.get("situation")
    if sit_a and sit_b:
        if sit_b["redZone"] and not sit_a["redZone"]:
            add("redZone", "Red zone", sit_b["possession"])
        if sit_a["possession"] and sit_b["possession"] and sit_a["possession"] != sit_b["possession"]:
            add("possession", "Change of possession", sit_b["possession"])

    out.sort(key=lambda c: ORDER.index(c["kind"]))
    return out


def diff(before: list[dict] | None, after: list[dict], stamp: str | None) -> list[dict]:
    """Changes across a slate, in the order of `after` (wall order when ranked)."""
    if not before:
        return []
    prior = {g["id"]: g for g in before}
    out: list[dict] = []
    for g in after:
        if g["id"] in prior:
            out += between(prior[g["id"]], g, stamp)
    return out


def _snapshot(side: dict) -> dict:
    return {k: side[k] for k in ("id", "abbr", "rank", "score", "fill", "hatch")}


def feed(frames: list[tuple[str | None, list[dict]]], limit: int = 12) -> list[dict]:
    """The whip-around: feed-worthy changes across consecutive frames, newest
    first, each carrying both sides as they stood at that frame."""
    per_frame: list[list[dict]] = []
    for (_, before), (stamp, after) in zip(frames, frames[1:]):
        by_id = {g["id"]: g for g in after}
        items = []
        for c in diff(before, after, stamp):
            g = by_id[c["game"]]
            if c["kind"] not in FEED_KINDS:
                continue
            if c["kind"] == "kickoff" and not g["flags"]["ranked"]:
                continue
            items.append({**c, "away": _snapshot(g["away"]), "home": _snapshot(g["home"])})
        per_frame.append(items)
    # Newest frame first; inside one frame, wall order.
    return [c for items in reversed(per_frame) for c in items][:limit]
