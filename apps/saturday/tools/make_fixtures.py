"""Trim the recorded 2026-09-12 capture into small, deterministic test fixtures.

Never edit tests/fixtures by hand: change this script and re-run it. It only
removes fields nothing reads (links, articles, broadcast maps, per-athlete
detail); it never changes a value, so a fixture is ESPN's bytes, less.

    python3 tools/make_fixtures.py
"""
from __future__ import annotations

import gzip
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
CAP = ROOT / "data/capture/2026-09-12"
OUT = ROOT / "tests/fixtures"

PREGAME = ROOT / "data/capture/2026-09-19-pregame"   # a Tuesday snapshot of the week-3 board
PRE_EVENT = "401856688"                              # LSU at Ole Miss, days before kickoff

AT = "20260913T003400Z"          # OSU-Texas, 3rd & 6 at the TEX 17, early 2nd quarter
DELAYED_AT = "20260913T002000Z"  # Georgia Southern at Clemson, sitting in a delay

OSU_TEX, WAKE_PUR, OKST_ORE, CLEMSON = "401856682", "401858224", "401856782", "401858219"

EVENT_DROP = {"links", "weather", "uid"}
COMP_DROP = {"geoBroadcasts", "highlights", "headlines", "leaders", "odds", "notes", "uid", "tickets", "format", "recent", "startDate", "timeValid", "dateValid", "playByPlayAvailable", "type"}
TEAM_DROP = {"links", "venue", "uid", "isActive"}
SUMMARY_DROP = {"article", "news", "videos", "standings", "broadcasts", "againstTheSpread", "meta", "odds", "pickcenter", "leaders", "format", "wallclockAvailable"}
PLAY_DROP = {"wallclock", "modified", "teamParticipants", "athletesInvolved", "participants", "probability", "priority", "sequenceNumber"}


def load(path):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def newest(folder, at):
    files = [p for p in sorted(folder.glob("*.json.gz")) if p.name[:16] <= at[:16]]
    return files[-1]


def trim_event(ev):
    ev = {k: v for k, v in ev.items() if k not in EVENT_DROP}
    comps = []
    for c in ev.get("competitions", []):
        c = {k: v for k, v in c.items() if k not in COMP_DROP}
        c["competitors"] = [{**{k: v for k, v in x.items() if k not in ("statistics", "uid", "leaders", "linescores")},
                             "team": {k: v for k, v in x["team"].items() if k not in TEAM_DROP}}
                            for x in c.get("competitors", [])]
        if c.get("situation", {}).get("lastPlay"):
            lp = c["situation"]["lastPlay"]
            c["situation"] = {**c["situation"], "lastPlay": {k: lp[k] for k in ("id", "text", "type", "scoreValue", "statYardage", "end", "team") if k in lp}}
        comps.append(c)
    ev["competitions"] = comps
    return ev


def trim_summary(sm):
    sm = {k: v for k, v in sm.items() if k not in SUMMARY_DROP}
    drives = sm.get("drives") or {}
    for d in (drives.get("previous") or []) + ([drives["current"]] if drives.get("current") else []):
        d["plays"] = [{k: v for k, v in p.items() if k not in PLAY_DROP} for p in d.get("plays", [])]
    box = sm.get("boxscore") or {}
    for p in box.get("players") or []:
        p["statistics"] = [{**cat, "athletes": cat.get("athletes", [])[:1]} for cat in p.get("statistics", [])[:3]]
        p["team"] = {k: v for k, v in p["team"].items() if k not in TEAM_DROP}
    for t in box.get("teams") or []:
        t["team"] = {k: v for k, v in t["team"].items() if k not in TEAM_DROP}
    head = sm.get("header") or {}
    head.pop("links", None)
    for c in head.get("competitions") or []:
        for x in c.get("competitors") or []:
            x["team"] = {k: v for k, v in x["team"].items() if k not in TEAM_DROP}
    if sm.get("gameInfo", {}).get("venue"):
        sm["gameInfo"]["venue"].pop("images", None)
    if sm.get("gameInfo", {}).get("weather"):
        sm["gameInfo"]["weather"].pop("link", None)
    return sm


def write(name, payload):
    (OUT / name).write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")


def pregame():
    """A real board on which every game is scheduled, and one scheduled game's
    summary: the state a Saturday starts in, which a recorded night never
    contains. Skipped when that capture is not present."""
    boards = sorted((PREGAME / "scoreboard").glob("*.json.gz"))
    summaries = sorted((PREGAME / "live" / PRE_EVENT).glob("*.json.gz"))
    if not boards or not summaries:
        return
    board = load(boards[0])
    write("slate_pregame.json", {"events": [trim_event(ev) for ev in board["events"]],
                                 "capturedAt": boards[0].name[:16],
                                 "week": board.get("week"), "season": board.get("season") or {},
                                 "leagues": [{"calendar": (board.get("leagues") or [{}])[0].get("calendar") or []}]})
    write(f"summary_pregame_{PRE_EVENT}.json", trim_summary(load(summaries[0])))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    board = load(newest(CAP / "scoreboard", AT))
    write("slate.json", {"events": [trim_event(ev) for ev in board["events"]],
                         "capturedAt": AT, "week": board.get("week"), "season": (board.get("season") or {})})
    early = load(newest(CAP / "scoreboard", DELAYED_AT))
    write("slate_delayed.json", {"events": [trim_event(ev) for ev in early["events"] if ev["id"] == CLEMSON],
                                 "capturedAt": DELAYED_AT})
    write(f"summary_{OSU_TEX}.json", trim_summary(load(newest(CAP / "live" / OSU_TEX, AT))))
    for event in (WAKE_PUR, OKST_ORE):
        write(f"summary_{event}.json", trim_summary(load(CAP / "final" / f"{event}.json.gz")))
    pregame()
    for p in sorted(OUT.glob("*.json")):
        print(f"{p.name}: {p.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
