#!/usr/bin/env python3
"""Score the scene's play geometry against nflverse, game by game.

"More accurate" is a claim until somebody measures it, so this is the
measurement. It takes the games already captured as replay fixtures, matches
every play to nflverse's published row, and reports the error in the numbers a
path is actually drawn from.

    python3 tools/measure_play_accuracy.py            # every captured game
    python3 tools/measure_play_accuracy.py --event 401772810 --json

The number that matters is `airYards`: where the ball was caught. ESPN never
states it, so a live scene estimates it from the depth word and the gain, and
the error is the yards after the catch. Start and end spots are reported for
scrimmage plays only - on a kickoff or a punt the two sources mean different
things by a spot, which `truth.POSSESSION_CHANGES` explains.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from fantasyedge import nflverse, scene as sc, truth   # noqa: E402

FIX = pathlib.Path(__file__).resolve().parents[1] / "tests" / "fixtures"


def shaped(summary: dict) -> list[dict]:
    """The plays as `api.gamecast` shapes them, which is what a scene reads."""
    out = []
    for drive in (summary.get("drives") or {}).get("previous") or []:
        for p in (drive.get("plays") or []):
            st, en = p.get("start") or {}, p.get("end") or {}
            out.append({
                "id": str(p.get("id") or ""),
                "type": (p.get("type") or {}).get("text", ""),
                "text": p.get("text") or "",
                "yards": p.get("statYardage"),
                "period": (p.get("period") or {}).get("number", 0),
                "clock": (p.get("clock") or {}).get("displayValue", ""),
                "down": st.get("down"), "distance": st.get("distance"),
                "from": st.get("yardsToEndzone"), "to": en.get("yardsToEndzone"),
                "fromYard": st.get("yardLine"), "toYard": en.get("yardLine"),
                "scoring": bool(p.get("scoringPlay")),
                "turnover": bool(p.get("isTurnover")),
                "penalty": bool(p.get("isPenalty")),
            })
    return out


def events() -> list[str]:
    return sorted(p.name[len("replay_game_"):-len(".json")]
                  for p in FIX.glob("replay_game_*.json"))


def report(event: str) -> dict:
    summary = json.loads((FIX / f"replay_game_{event}.json").read_text())["summary"]
    plays = [p for p in shaped(summary) if sc.style_of(p)]
    rows, sched = nflverse.plays_for_espn(event)
    if not rows:
        return {"event": event, "covered": False, "plays": len(plays)}
    out = truth.compare(plays, rows, estimate_air=lambda p: sc.air_yards(p))
    # The same measurement over corrected plays. `scene.air_yards` returns
    # what nflverse stated when it is there, so this is the error that is
    # left once a game is corrected, not a second estimate of it.
    fixed = truth.correct(plays, rows, event=event)
    after = truth.compare(fixed, rows, estimate_air=lambda p: sc.air_yards(p))
    out["afterAirYards"] = after["airYards"]
    out["corrected"] = sum(1 for p in fixed
                           if (p.get("truth") or {}).get("source") == "corrected")
    out["event"] = event
    out["gameId"] = (sched or {}).get("game_id")
    out["covered"] = True
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--event", action="append", help="ESPN event id; repeatable")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    out = [report(e) for e in (args.event or events())]
    if args.json:
        print(json.dumps(out, indent=1))
        return 0

    for r in out:
        if not r.get("covered"):
            print(f"\n{r['event']}: not published by nflverse yet ({r['plays']} plays)")
            continue
        print(f"\n{r['event']}  {r['gameId']}")
        print(f"  matched {r['matched']}/{r['plays']} plays ({r['matchRate']}%), "
              f"{r['scrimmage']} from scrimmage")
        for key, label in (("startSpot", "start spot "), ("endSpot", "end spot   "),
                           ("yardsGained", "yards      "), ("airYards", "air yards  ")):
            s = r[key]
            if not s.get("n"):
                continue
            print(f"  {label} n={s['n']:3d}  mean {s['mean']:5.2f} yd   "
                  f"worst {s['worst']:5.1f} yd   within 0.5 yd: {s['exact']}/{s['n']}")
        a = r["afterAirYards"]
        if a.get("n"):
            print(f"  air yards, corrected: mean {a['mean']:5.2f} yd   worst {a['worst']:5.1f} yd   "
                  f"within 0.5 yd: {a['exact']}/{a['n']}")
        k = r["playType"]
        print(f"  play type   {k['same']} agree, {k['differ']} differ")
        print(f"  corrected   {r['corrected']}/{r['plays']} plays")
        if r["airYards"].get("worstPlay"):
            print(f"  worst air:  {r['airYards']['worstPlay']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
