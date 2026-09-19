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
    print(f"compared {len(rows)} game-moments across {len({r['stamp'] for r in rows})} recorded boards: "
          f"{len(rows) - len(bad)} identical, {len(bad)} different")
    for r in bad:
        print(f"  {r['stamp']} {r['event']} {r['teams']}: recorded {r['recorded']} ({r['recordedDetail']}) "
              f"!= rebuilt {r['rebuilt']} ({r['rebuiltDetail']})")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
