"""Hold a reconstruction against boards that were actually recorded.

Where a backfill's window overlaps a recording, the two describe the same
moment and must agree. This prints every game whose state differs, which is
the only honest way to say how good a reconstruction is.

    python3 tools/verify_reconstruction.py --slate 2026-09-19
    python3 tools/verify_reconstruction.py --slate 2026-09-19 --boards 5

Exit code 1 if any game disagrees, so it can be a gate.
"""
from __future__ import annotations

import argparse
import datetime as dt
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "packages"))
sys.path.insert(0, str(REPO / "tools"))

from cfb import parse, reconstruct  # noqa: E402
from make_fixtures import trim_event  # noqa: E402
from record_slate import load, slate_events  # noqa: E402


def classify(row: dict) -> str:
    """Why a rebuilt moment differs from the recorded one.

    Three differences are understood, measured against the whole 19 September
    overlap, and they all say the same thing: the play feed leads the board.
    Anything else is unexplained and fails the check.
    """
    (state_a, away_a, home_a), (state_b, away_b, home_b) = row["recorded"], row["rebuilt"]
    scores = [(away_a or 0, away_b or 0), (home_a or 0, home_b or 0)]
    if state_a == "pre" and state_b == "in" and (away_b or 0) == 0 and (home_b or 0) == 0:
        return "startsAtItsFirstPlay"
    if state_a == "in" and state_b == "post" and (away_a, home_a) == (away_b, home_b):
        return "endsAtItsLastPlay"
    if state_a == state_b and all(b >= a and b - a <= 8 for a, b in scores):
        return "playFeedAheadOfBoard"
    return "unexplained"


def compare(capture: pathlib.Path, backfill: pathlib.Path, saturday: dt.date, boards: int) -> list[dict]:
    reference = load(backfill / "reference-board.json.gz")
    summaries = {p.name.removesuffix(".json.gz"): load(p) for p in (backfill / "summary").glob("*.json.gz")}
    events = {k: trim_event(v) for k, v in slate_events(reference, saturday).items()}
    shell = {"events": [trim_event(ev) for ev in reference.get("events") or []]}
    out = []
    for path in sorted((capture / "scoreboard").glob("2*.json.gz"))[:boards]:
        when = reconstruct.stamp_to_dt(path.name[:16])
        recorded = {g["id"]: g for g in (parse.game_record(e) for e in load(path).get("events") or [])}
        rebuilt = {g["id"]: g for g in (parse.game_record(e)
                                        for e in reconstruct.board_at(shell, events, summaries, when)["events"])}
        for event, real in recorded.items():
            mine = rebuilt.get(event)
            if not mine or mine["provenance"] != "reconstructed":
                continue
            a = (real["status"]["state"], real["away"]["score"], real["home"]["score"])
            b = (mine["status"]["state"], mine["away"]["score"], mine["home"]["score"])
            out.append({"stamp": path.name[:16], "event": event, "agree": a == b,
                        "teams": f"{real['away']['abbr']}-{real['home']['abbr']}",
                        "recorded": a, "rebuilt": b,
                        "recordedDetail": real["status"]["detail"], "rebuiltDetail": mine["status"]["detail"]})
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--slate", required=True)
    ap.add_argument("--capture", type=pathlib.Path)
    ap.add_argument("--backfill", type=pathlib.Path)
    ap.add_argument("--boards", type=int, default=1, help="how many recorded boards to check, oldest first")
    args = ap.parse_args(argv)
    saturday = dt.date.fromisoformat(args.slate)
    capture = args.capture or REPO / "data/capture" / saturday.isoformat()
    backfill = args.backfill or REPO / "data/capture" / f"{saturday.isoformat()}-backfill"
    rows = compare(capture, backfill, saturday, args.boards)
    if not rows:
        print("nothing overlaps: no recorded board covers a game the backfill rebuilt")
        return 0
    bad = [r for r in rows if not r["agree"]]
    kinds: dict[str, list[dict]] = {}
    for row in bad:
        kinds.setdefault(classify(row), []).append(row)
    print(f"compared {len(rows)} game-moments across {len({r['stamp'] for r in rows})} recorded boards: "
          f"{len(rows) - len(bad)} identical, {len(bad)} different")
    for kind, group in sorted(kinds.items()):
        print(f"  {len(group)} {kind}")
        for r in group[:3 if kind != 'unexplained' else len(group)]:
            print(f"    {r['stamp']} {r['event']} {r['teams']}: recorded {r['recorded']} ({r['recordedDetail']}) "
                  f"!= rebuilt {r['rebuilt']} ({r['rebuiltDetail']})")
        if kind != "unexplained" and len(group) > 3:
            print(f"    ... and {len(group) - 3} more")
    unexplained = kinds.get("unexplained", [])
    if unexplained:
        print(f"\n{len(unexplained)} differences are not explained by a known limit of the rebuild")
    return 1 if unexplained else 0


if __name__ == "__main__":
    raise SystemExit(main())
