"""Join a backfill and a live recording into one continuous night.

The recording is the truth wherever it exists. The backfill only fills the
hours before the recorder started, and every frame it contributes says in its
own payload that it was reconstructed. Where both cover a moment, the
recording wins and the reconstruction is dropped.

Nothing is edited and nothing is deleted: the merged folder is built from
copies (hard links where the filesystem allows, so a 13 MB backfill and a
recording do not become a third copy on disk).

    python3 tools/merge_capture.py --slate 2026-09-19                # into <slate>-merged
    python3 tools/merge_capture.py --slate 2026-09-19 --dry-run

Run it after the recorder has finished. It refuses while the recording's own
heartbeat says it is still going, unless --force.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import shutil
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "packages"))
sys.path.insert(0, str(REPO / "tools"))

from record_slate import ET  # noqa: E402

LIVE_PHASES = {"recording", "waiting", "idle", "backing off"}


def recorder_running(capture: pathlib.Path) -> str | None:
    """The recorder's own phase, if its heartbeat says it is still going."""
    try:
        beat = json.loads((capture / "heartbeat.json").read_text())
    except (OSError, ValueError):
        return None
    phase = beat.get("phase")
    if phase not in LIVE_PHASES:
        return None
    try:
        os.kill(int(beat.get("pid")), 0)
    except ProcessLookupError:
        return None                 # the heartbeat is stale; the process is gone
    except PermissionError:
        pass                        # it exists and belongs to somebody else
    except (TypeError, ValueError, OSError):
        return None
    pid = beat.get("pid")
    return f"{phase} (pid {pid}, last beat {beat.get('at')})"


def link_or_copy(src: pathlib.Path, dst: pathlib.Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        return
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def merge(capture: pathlib.Path, backfill: pathlib.Path, out: pathlib.Path, dry_run: bool = False) -> dict:
    recorded = sorted(p for p in (capture / "scoreboard").glob("2*.json.gz"))
    first_recorded = recorded[0].name[:16] if recorded else None
    rebuilt = sorted(p for p in (backfill / "scoreboard").glob("2*.json.gz"))
    # The recording owns every moment it covers.
    kept = [p for p in rebuilt if not first_recorded or p.name[:16] < first_recorded]
    dropped = len(rebuilt) - len(kept)

    finals_live = {p.name: p for p in (capture / "final").glob("*.json.gz")}
    # A backfill summary counts as a final only if the game had finished when
    # it was fetched. A live game's summary stops at the last snap, and a
    # partial one in final/ would read as a finished game that ended early.
    try:
        states = json.loads((backfill / "manifest.json").read_text()).get("games", {})
    except (OSError, ValueError):
        states = {}
    finals_backfill = {p.name: p for p in (backfill / "summary").glob("*.json.gz")
                       if states.get(p.name.removesuffix(".json.gz"), {}).get("state") == "post"}
    partial = sum(1 for p in (backfill / "summary").glob("*.json.gz")
                  if states.get(p.name.removesuffix(".json.gz"), {}).get("state") != "post")
    only_backfill = sorted(set(finals_backfill) - set(finals_live))

    live_snaps = sorted((capture / "live").glob("*/*.json.gz"))

    report = {
        "slate": capture.name,
        "out": str(out),
        "frames": {"reconstructed": len(kept), "recorded": len(recorded),
                   "reconstructedDropped": dropped, "firstRecorded": first_recorded,
                   "first": (kept or recorded)[0].name[:16] if (kept or recorded) else None,
                   "last": recorded[-1].name[:16] if recorded else (kept[-1].name[:16] if kept else None)},
        "finals": {"fromRecording": len(finals_live), "onlyFromBackfill": len(only_backfill),
                   "backfillPartialsNotUsedAsFinals": partial},
        "liveSnapshots": len(live_snaps),
        "mergedAt": dt.datetime.now(ET).isoformat(timespec="seconds"),
    }
    if dry_run:
        return report

    for path in kept:
        link_or_copy(path, out / "scoreboard" / path.name)
    for path in recorded:
        link_or_copy(path, out / "scoreboard" / path.name)
    for path in (capture / "scoreboard").glob("*-closing.json.gz"):
        link_or_copy(path, out / "scoreboard" / path.name)
    for name, path in finals_live.items():
        link_or_copy(path, out / "final" / name)
    for name in only_backfill:
        # A game whose final the recorder never fetched: the backfill's summary
        # is the only copy, and for a finished game it is the same document.
        link_or_copy(finals_backfill[name], out / "final" / name)
    for path in live_snaps:
        link_or_copy(path, out / "live" / path.parent.name / path.name)
    for extra in ("record.log", "heartbeat.json"):
        if (capture / extra).exists():
            link_or_copy(capture / extra, out / f"recording-{extra}")
    if (backfill / "manifest.json").exists():
        link_or_copy(backfill / "manifest.json", out / "backfill-manifest.json")

    (out / "MERGE.json").write_text(json.dumps({
        **report,
        "rule": "the recording owns every moment it covers; the backfill only fills the hours before it",
        "provenance": "every frame says in its own payload whether it was recorded or reconstructed; "
                      "see backfill-manifest.json for what a reconstruction cannot know",
    }, indent=1))
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--slate", required=True)
    ap.add_argument("--capture", type=pathlib.Path)
    ap.add_argument("--backfill", type=pathlib.Path)
    ap.add_argument("--out", type=pathlib.Path)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="merge even while the recorder is running")
    args = ap.parse_args(argv)

    saturday = dt.date.fromisoformat(args.slate)
    capture = args.capture or REPO / "data/capture" / saturday.isoformat()
    backfill = args.backfill or REPO / "data/capture" / f"{saturday.isoformat()}-backfill"
    out = args.out or REPO / "data/capture" / f"{saturday.isoformat()}-merged"

    running = recorder_running(capture)
    if running and not (args.force or args.dry_run):
        print(f"the recorder is still {running}; wait for it to finish, or pass --force", file=sys.stderr)
        return 2
    report = merge(capture, backfill, out, args.dry_run)
    print(json.dumps(report, indent=1))
    if not args.dry_run:
        where = out.relative_to(REPO) if out.is_relative_to(REPO) else out
        print(f"\nreplay it with:\n  PYTHONPATH=packages:apps/saturday python3 -m api serve "
              f"--source capture:{where} --host 0.0.0.0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
