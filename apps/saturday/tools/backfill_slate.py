"""Backfill a slate the recorder started too late for, and rebuild its timeline.

A finished or in-progress game's summary carries every play, and each play
carries a `wallclock` - the real instant it happened. So a night that was not
recorded minute by minute can still be reconstructed after the fact: where the
ball was, the score, the period and the clock, at any moment the plays cover.

What that cannot give back is anything that existed only in the moment. See
UNRECOVERABLE below and `cfb.reconstruct.CAVEATS`; a reconstructed board says
so in the payload, and never claims to be a recording.

It writes to its own folder and never touches the folder a running recorder
owns. `merge_capture.py` puts the two together afterwards.

    python3 tools/backfill_slate.py fetch --slate 2026-09-19        # summaries, idempotent
    python3 tools/backfill_slate.py frames --slate 2026-09-19       # boards from play wallclocks
    python3 tools/backfill_slate.py both --slate 2026-09-19

UNRECOVERABLE, and listed in the manifest rather than papered over:
  - a score corrected and then corrected back: only the final version survives;
  - a delay that came and went: ESPN keeps no history of it;
  - the moment-by-moment status ESPN itself published (halftime is inferred
    from the gap between the last play of one period and the first of the
    next, not read from a recorded board);
  - possession and down between plays where no next play exists yet;
  - anything about a game that never kicked off.

Stdlib only.
"""
from __future__ import annotations

import argparse
import datetime as dt
import gzip
import json
import pathlib
import sys
import time
import urllib.error

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "packages"))
sys.path.insert(0, str(REPO / "tools"))

from cfb import league, parse, reconstruct  # noqa: E402
from make_fixtures import trim_event  # noqa: E402
from record_slate import ET, fetch, load, save, slate_events, week_of  # noqa: E402

FRAME_SECONDS = 60.0


def newest_board(capture: pathlib.Path) -> tuple[str, dict] | tuple[None, None]:
    boards = sorted((capture / "scoreboard").glob("*.json.gz"))
    if not boards:
        return None, None
    return boards[0].name[:16], load(boards[-1])


def first_recorded_stamp(capture: pathlib.Path) -> str | None:
    boards = sorted(p.name[:16] for p in (capture / "scoreboard").glob("2*.json.gz"))
    return boards[0] if boards else None


def manifest_path(out: pathlib.Path) -> pathlib.Path:
    return out / "manifest.json"


def read_manifest(out: pathlib.Path) -> dict:
    try:
        return json.loads(manifest_path(out).read_text())
    except (OSError, ValueError):
        return {}


def write_manifest(out: pathlib.Path, body: dict) -> None:
    out.mkdir(parents=True, exist_ok=True)
    tmp = out / ".manifest.json.tmp"
    tmp.write_text(json.dumps(body, indent=1, sort_keys=True))
    tmp.replace(manifest_path(out))


def say(msg: str) -> None:
    print(f"{dt.datetime.now(ET):%H:%M:%S %Z} {msg}", flush=True)


def fetch_summaries(out: pathlib.Path, board: dict, saturday: dt.date, gap: float,
                    max_requests: int, refresh: bool, fetcher=fetch) -> dict:
    """One summary per game that has played, into <out>/summary/<event>.json.gz.

    Idempotent and resumable: a summary already on disk is skipped unless
    --refresh, so this can be run again after more games finish.
    """
    events = slate_events(board, saturday)
    records = {g["id"]: g for g in (parse.game_record(ev) for ev in events.values())}
    played = [e for e, g in records.items() if g["status"]["state"] in ("in", "post")]
    folder = out / "summary"
    folder.mkdir(parents=True, exist_ok=True)
    manifest = read_manifest(out)
    games = manifest.get("games", {})
    requests = 0
    for event in sorted(played):
        path = folder / f"{event}.json.gz"
        state = records[event]["status"]["state"]
        if path.exists() and not refresh and games.get(event, {}).get("state") == "post":
            continue                      # a final never changes again
        if requests >= max_requests:
            say(f"stopping at the {max_requests}-request cap; run again to continue")
            break
        time.sleep(gap)
        try:
            summary = fetcher(league.summary_url(event))
        except (urllib.error.URLError, TimeoutError, ConnectionError, ValueError) as exc:
            say(f"{event}: {type(exc).__name__}: {exc}")
            games.setdefault(event, {})["error"] = str(exc)
            continue
        requests += 1
        save(path, summary)
        plays = [p for d in (summary.get("drives") or {}).get("previous") or [] for p in d.get("plays") or []]
        clocks = [p["wallclock"] for p in plays if p.get("wallclock")]
        g = records[event]
        games[event] = {
            "state": state,
            "partial": state != "post",      # a live game's summary stops at the last snap
            "away": g["away"]["abbr"], "home": g["home"]["abbr"],
            "kickoff": g["kickoff"],
            "plays": len(plays), "withWallclock": len(clocks),
            "firstPlay": min(clocks) if clocks else None,
            "lastPlay": max(clocks) if clocks else None,
            "fetchedAt": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        say(f"{event} {g['away']['abbr']}-{g['home']['abbr']}: {len(plays)} plays, "
            f"{len(clocks)} timed{' (still live)' if state != 'post' else ''}")
    manifest.update({"slate": saturday.isoformat(), "games": games,
                     "unrecoverable": reconstruct.CAVEATS,
                     "fetchedRequests": manifest.get("fetchedRequests", 0) + requests})
    write_manifest(out, manifest)
    return manifest


def build_frames(out: pathlib.Path, board: dict, saturday: dt.date, until: str | None,
                 every: float = FRAME_SECONDS) -> dict:
    """Reconstructed boards, one per `every` seconds, from the plays on disk.

    Every frame says in the payload that it was reconstructed, and from what.
    Frames stop at `until` - the first board the live recorder wrote - because
    from there on the night is recorded and a reconstruction would be a worse
    copy of it.
    """
    summaries = {}
    for path in sorted((out / "summary").glob("*.json.gz")):
        summaries[path.name.removesuffix(".json.gz")] = load(path)
    if not summaries:
        say("no summaries on disk; run `fetch` first")
        return {}
    events = slate_events(board, saturday)
    span = reconstruct.covered_span(summaries)
    if not span:
        say("no play wallclocks; nothing to reconstruct")
        return {}
    start, end = span
    stop = reconstruct.stamp_to_dt(until) if until else None
    # The reference is trimmed to what a board is read for - a reconstructed
    # frame is not ESPN's bytes, and carrying odds and article links into a
    # thousand files would cost five times the disk for nothing.
    events = {k: trim_event(v) for k, v in events.items()}
    reference = {"events": [trim_event(ev) for ev in board.get("events") or []],
                 "week": board.get("week"), "season": board.get("season") or {},
                 "leagues": [{"calendar": (board.get("leagues") or [{}])[0].get("calendar") or []}]}
    folder = out / "scoreboard"
    folder.mkdir(parents=True, exist_ok=True)
    instants = reconstruct.frame_instants(summaries, every, stop)
    made, skipped, previous = 0, 0, None
    for when in instants:
        frame = reconstruct.board_at(reference, events, summaries, when)
        shape = json.dumps([[str(ev.get("id")), ev.get("status"), (ev.get("competitions") or [{}])[0].get("situation"),
                             [c.get("score") for c in (ev.get("competitions") or [{}])[0].get("competitors") or []]]
                            for ev in frame["events"]], sort_keys=True)
        if shape == previous:
            skipped += 1
            continue                       # nothing on the slate moved in that minute
        previous = shape
        save(folder / f"{reconstruct.dt_to_stamp(when)}.json.gz", frame)
        made += 1
    manifest = read_manifest(out)
    manifest["frames"] = {
        "count": made, "unchangedSkipped": skipped, "everySeconds": every,
        "from": instants[0].astimezone(ET).isoformat(timespec="seconds") if instants else None,
        "to": instants[-1].astimezone(ET).isoformat(timespec="seconds") if instants else None,
        "firstPlay": start.astimezone(ET).isoformat(timespec="seconds"),
        "lastPlay": end.astimezone(ET).isoformat(timespec="seconds"),
        "referenceTrimmed": True,
        "stopsAt": until, "provenance": "reconstructed",
        "builtAt": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    write_manifest(out, manifest)
    say(f"{made} reconstructed frames ({skipped} minutes unchanged) from "
        f"{instants[0].astimezone(ET):%a %H:%M} to {instants[-1].astimezone(ET):%a %H:%M}"
        + (" where the live recording takes over" if until else ""))
    return manifest


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("action", choices=("fetch", "frames", "both"))
    ap.add_argument("--slate", required=True, help="the Saturday, YYYY-MM-DD")
    ap.add_argument("--capture", type=pathlib.Path, help="the live recording, read only (default data/capture/<slate>)")
    ap.add_argument("--out", type=pathlib.Path, help="default data/capture/<slate>-backfill")
    ap.add_argument("--gap", type=float, default=3.0, help="seconds between requests, to stay off the recorder's toes")
    ap.add_argument("--max-requests", type=int, default=90)
    ap.add_argument("--every", type=float, default=FRAME_SECONDS, help="seconds between reconstructed frames")
    ap.add_argument("--refresh", action="store_true", help="re-fetch summaries already on disk")
    args = ap.parse_args(argv)

    saturday = dt.date.fromisoformat(args.slate)
    capture = args.capture or REPO / "data/capture" / saturday.isoformat()
    out = args.out or REPO / "data/capture" / f"{saturday.isoformat()}-backfill"

    # The live recording's own newest board is the reference for teams, venue,
    # network and rank, and reading it costs ESPN nothing.
    _, board = newest_board(capture)
    if board is None:
        say(f"no boards in {capture}; falling back to one request for the week board")
        base = fetch(league.scoreboard_url())
        week = week_of(base, saturday)
        board = fetch(league.scoreboard_url(week=week[1], seasontype=week[0])) if week else base
    save(out / "reference-board.json.gz", board)

    if args.action in ("fetch", "both"):
        fetch_summaries(out, board, saturday, args.gap, args.max_requests, args.refresh)
    if args.action in ("frames", "both"):
        build_frames(out, board, saturday, first_recorded_stamp(capture), args.every)
    say(f"manifest: {manifest_path(out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
