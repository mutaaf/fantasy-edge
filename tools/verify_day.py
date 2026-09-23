"""Check a rebuilt day against a record it was not built from.

The rebuild walks `drives[].plays[]`. A summary also carries `scoringPlays`,
a separate block listing every score with the totals after it, and the header
carries the final. Neither is consulted when rebuilding, so both are
independent witnesses: rebuild the board at the instant of each scoring play
and ask whether the score on the tile is the score that play says it produced.

A difference is classified rather than counted. The known and explainable one
is ESPN's own: a touchdown's play record already carries the score *after* the
extra point, so a rebuild never passes through the six-point moment. An
unexplained difference exits 1.

    python3 tools/verify_day.py --date 2026-09-20 [--root data/replay/day]
"""

from __future__ import annotations

import argparse
import datetime as dt
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from fantasyedge import dayreplay as dr          # noqa: E402


def _int(value, default=0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def check(board: dict, summaries: dict[str, dict]) -> dict:
    events = {str(e.get("id")): e for e in board.get("events") or []}
    out = {"checked": 0, "same": 0, "differences": [], "games": len(summaries)}

    for event_id, summary in summaries.items():
        event = events.get(event_id)
        if not event:
            continue
        # The independent witness: ESPN's own scoring list, with the totals it
        # says each score produced.
        witnesses = []
        by_id = {str(p.get("id")): (w, p) for w, p in dr.timed_plays(summary)}
        for sp in summary.get("scoringPlays") or []:
            hit = by_id.get(str(sp.get("id")))
            if hit:
                witnesses.append((hit[0], sp))

        for when, sp in witnesses:
            rebuilt = dr.game_at(event, summary, when)
            comp = (rebuilt.get("competitions") or [{}])[0]
            got = {}
            for side in comp.get("competitors") or []:
                got[(side.get("homeAway") or "").lower()] = _int(side.get("score"))
            want = {"home": _int(sp.get("homeScore")), "away": _int(sp.get("awayScore"))}
            out["checked"] += 1
            if got.get("home") == want["home"] and got.get("away") == want["away"]:
                out["same"] += 1
            else:
                out["differences"].append({
                    "event": event_id, "name": event.get("shortName"),
                    "at": when.astimezone(dr.ET).strftime("%H:%M:%S"),
                    "got": got, "want": want,
                    "text": (sp.get("text") or "")[:70],
                    "why": _explain(got, want),
                })

        # And the final, from the header rather than from any play.
        span = dr.timed_plays(summary)
        if span:
            end = span[-1][0] + dt.timedelta(seconds=1)
            rebuilt = dr.game_at(event, summary, end)
            comp = (rebuilt.get("competitions") or [{}])[0]
            got = {(s.get("homeAway") or "").lower(): _int(s.get("score"))
                   for s in comp.get("competitors") or []}
            header = (((summary.get("header") or {}).get("competitions") or [{}])[0])
            want = {(s.get("homeAway") or "").lower(): _int(s.get("score"))
                    for s in header.get("competitors") or []}
            out["checked"] += 1
            if got == want:
                out["same"] += 1
            else:
                out["differences"].append({
                    "event": event_id, "name": event.get("shortName"), "at": "final",
                    "got": got, "want": want, "text": "final score",
                    "why": "finalDiffers"})
    return out


def _explain(got: dict, want: dict) -> str:
    """Name a difference, or call it unexplained.

    The one ESPN causes: a touchdown's play carries the score after the try,
    so the rebuild is ahead by the extra point rather than behind.
    """
    ahead = (got.get("home", 0) - want.get("home", 0),
             got.get("away", 0) - want.get("away", 0))
    if ahead in ((1, 0), (0, 1), (2, 0), (0, 2)):
        return "playFeedAheadOfScoringList"
    return "unexplained"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--root", default="data/replay/day")
    args = ap.parse_args()

    board, summaries = dr.load_day(pathlib.Path(args.root), args.date)
    result = check(board, summaries)
    total, same = result["checked"], result["same"]
    pct = 100.0 * same / total if total else 0.0
    print(f"{args.date}: {same}/{total} rebuilt states identical ({pct:.1f}%) "
          f"across {result['games']} games")

    kinds: dict[str, int] = {}
    for diff in result["differences"]:
        kinds[diff["why"]] = kinds.get(diff["why"], 0) + 1
    for why, n in sorted(kinds.items()):
        print(f"  {n:>4}  {why}")
    for diff in result["differences"][:8]:
        print(f"        {diff['name']} {diff['at']} got {diff['got']} "
              f"want {diff['want']}  {diff['text']}")

    unexplained = kinds.get("unexplained", 0) + kinds.get("finalDiffers", 0)
    if unexplained:
        print(f"FAIL: {unexplained} unexplained")
        raise SystemExit(1)
    print("OK: every difference is explained")


if __name__ == "__main__":
    main()
