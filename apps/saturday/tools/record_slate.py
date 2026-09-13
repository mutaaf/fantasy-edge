"""Record a college football Saturday from ESPN, raw, for replay fixtures.

Two things are worth keeping from a live slate and only one of them can be
fetched later. A finished game's summary stays on ESPN for years; the sequence
of scoreboards a live night produces - situation, possession, down and
distance changing minute by minute - exists only while it is happening. So
this records both: a scoreboard snapshot every interval, a summary snapshot
for each watched game whenever it changes, and one final summary for every
game on the slate once it goes final.

Payloads are stored exactly as ESPN sent them, gzipped. Trimming them into
test fixtures is a separate, deterministic step; nothing here is edited.

    python3 tools/record_slate.py --out data/capture/2026-09-12 \
        --watch 401856682 401856681 --interval 60 --until 04:30

Stdlib only. Stops by itself when every game is final or at --until.
"""
from __future__ import annotations

import argparse
import datetime as dt
import gzip
import hashlib
import json
import os
import pathlib
import time
import urllib.error
import urllib.parse
import urllib.request

HOST = os.environ.get("ESPN_API_HOST", "site.web.api.espn.com")
BASE = f"https://{HOST}/apis/site/v2/sports/football/college-football"
# groups=80 is FBS. Without it ESPN serves a curated subset, not the slate.
SCOREBOARD = BASE + "/scoreboard?groups=80&limit=300"
SUMMARY = BASE + "/summary?event={event}"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0 Safari/537.36")


def fetch(url: str) -> dict:
    key = os.environ.get("ESPN_API_KEY")
    if key:
        url += "&apikey=" + urllib.parse.quote(key, safe="")
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9", "Referer": "https://www.espn.com/"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.load(r)


def save(path: pathlib.Path, payload: dict) -> None:
    """Atomic, so a crash mid-write never leaves a fixture that half-parses."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("." + path.name + ".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8") as f:
        json.dump(payload, f, separators=(",", ":"))
    tmp.replace(path)


def digest(payload: dict, drop: tuple[str, ...] = ()) -> str:
    """Hash of the parts that change with the game, not with the request.

    ESPN stamps volatile metadata onto every response; hashing it would make
    every poll look new and store hundreds of identical snapshots.
    """
    body = {k: v for k, v in payload.items() if k not in drop}
    return hashlib.sha1(json.dumps(body, sort_keys=True).encode()).hexdigest()


def stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def states(board: dict) -> dict[str, str]:
    return {e["id"]: e["status"]["type"]["state"] for e in board.get("events", [])}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True, type=pathlib.Path)
    ap.add_argument("--watch", nargs="*", default=[],
                    help="event ids to snapshot live, not just at the final")
    ap.add_argument("--interval", type=float, default=60.0)
    ap.add_argument("--until", default="04:30", help="local HH:MM to stop at")
    ap.add_argument("--gap", type=float, default=2.5,
                    help="seconds between consecutive requests")
    args = ap.parse_args()

    out: pathlib.Path = args.out
    log = (out / "record.log")
    out.mkdir(parents=True, exist_ok=True)

    def say(msg: str) -> None:
        line = f"{dt.datetime.now():%H:%M:%S} {msg}"
        print(line, flush=True)
        with log.open("a") as f:
            f.write(line + "\n")

    hh, mm = map(int, args.until.split(":"))
    now = dt.datetime.now()
    deadline = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if deadline <= now:
        deadline += dt.timedelta(days=1)

    last: dict[str, str] = {}
    finals_done = {p.name.removesuffix(".json.gz")
                   for p in (out / "final").glob("*.json.gz")}
    backoff = 0.0
    say(f"recording to {out} until {deadline:%a %H:%M}; watching {args.watch or 'none'}")

    while dt.datetime.now() < deadline:
        cycle = time.monotonic()
        try:
            board = fetch(SCOREBOARD)
            h = digest(board)
            if h != last.get("board"):
                save(out / "scoreboard" / f"{stamp()}.json.gz", board)
                last["board"] = h
            st = states(board)

            for event in args.watch:
                if st.get(event) != "in":
                    continue
                time.sleep(args.gap)
                sm = fetch(SUMMARY.format(event=event))
                h = digest(sm, drop=("meta",))
                if h != last.get(event):
                    save(out / "live" / event / f"{stamp()}.json.gz", sm)
                    last[event] = h

            # A final is fetched once, a little after it goes final, because
            # ESPN keeps amending stat corrections for the first few minutes.
            for event, state in sorted(st.items()):
                if state != "post" or event in finals_done:
                    continue
                time.sleep(args.gap)
                sm = fetch(SUMMARY.format(event=event))
                save(out / "final" / f"{event}.json.gz", sm)
                finals_done.add(event)
                say(f"final {event}: {len(sm.get('drives', {}).get('previous', []))} drives")

            live = sum(1 for s in st.values() if s == "in")
            pre = sum(1 for s in st.values() if s == "pre")
            say(f"{len(st)} games: {live} live, {pre} pre, {len(finals_done)} finals saved")
            backoff = 0.0
            if st and live == 0 and pre == 0 and finals_done >= set(st):
                # Take one last board, so the slate's closing state is on disk.
                save(out / "scoreboard" / f"{stamp()}-closing.json.gz", board)
                say("every game final and saved; done")
                return 0
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            # A 403 from the edge means slow down, not retry harder.
            backoff = min(600.0, max(120.0, backoff * 2))
            say(f"fetch failed ({exc}); backing off {backoff:.0f}s")
            time.sleep(backoff)
            continue
        time.sleep(max(5.0, args.interval - (time.monotonic() - cycle)))

    say("deadline reached")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
