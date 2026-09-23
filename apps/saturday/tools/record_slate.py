"""Record a college football weekend from ESPN, raw, unattended.

Two things are worth keeping from a live slate and only one of them can be
fetched later. A finished game's summary stays on ESPN for years; the sequence
of scoreboards a live night produces - situation, possession, down and
distance changing minute by minute - exists only while it is happening. So
this records both: a scoreboard snapshot whenever it changes, a summary
snapshot for the games that matter most while they are live, and one final
summary for every game on the slate a few minutes after it goes final.

Payloads are stored as ESPN sent them, gzipped, one file per snapshot, never
edited. Trimming them into test fixtures is tools/make_fixtures.py's job.

THE WINDOW comes from the real schedule. The slate is a Saturday plus that
Friday's FBS games (ET). Recording starts 30 minutes before the first kickoff
and ends when every slate game is final (or postponed or cancelled) and its
final summary is saved, or at 06:00 ET on Sunday, whichever is first.

Between Friday night and Saturday's first kickoff nothing is live for hours;
when no game is live, delayed or waiting on its final summary and the next
kickoff is more than 45 minutes away, it sleeps until 30 minutes before it.

UNATTENDED means: it waits for the window by itself; a network drop backs off
and resumes; a Mac that slept is noticed and logged; a restart resumes from
what is on disk (finals already saved are not fetched again, the newest
snapshot is not written twice); record.log rotates at 5 MB; heartbeat.json is
rewritten every cycle so anyone can see it is alive. Keeping the Mac awake is
the wrapper's job (tools/record_weekend.sh runs this under caffeinate).

    python3 tools/record_slate.py --slate 2026-09-19 --plan           # print the window, exit
    python3 tools/record_slate.py --slate 2026-09-19                  # wait, record, stop
    python3 tools/record_slate.py --slate 2026-09-19 --dry-run 3 \\
        --out /tmp/dry                                                # record now for 3 minutes

Exit codes: 0 done (all final, hard stop, or dry run finished), 2 bad
arguments, 3 the slate has no games.

Stdlib only.
"""
from __future__ import annotations

import argparse
import datetime as dt
import gzip
import hashlib
import json
import os
import pathlib
import signal
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "packages"))

from cfb import league, leverage, parse  # noqa: E402

try:
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
except Exception:                          # no tz database: a football weekend is EDT
    ET = dt.timezone(dt.timedelta(hours=-4), "ET")

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0 Safari/537.36")

LEAD = dt.timedelta(minutes=30)             # start before the first kickoff
HARD_STOP_HOUR = 6                          # 06:00 ET Sunday
FINAL_SETTLE = 300.0                        # ESPN amends stats for a few minutes after a final
LOG_ROTATE_BYTES = 5 * 1024 * 1024
IDLE_MIN = dt.timedelta(minutes=45)         # a lull at least this long is slept through
DONE_STATES = {"STATUS_POSTPONED", "STATUS_CANCELED", "STATUS_FORFEIT"}


# ---- plumbing ------------------------------------------------------------------

def fetch(url: str) -> dict:
    key = os.environ.get("ESPN_API_KEY")
    if key:
        url += ("&" if "?" in url else "?") + "apikey=" + urllib.parse.quote(key, safe="")
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9", "Referer": "https://www.espn.com/"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.load(r)


def save(path: pathlib.Path, payload: dict) -> None:
    """Atomic, so a crash mid-write never leaves a file that half-parses."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("." + path.name + ".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8") as f:
        json.dump(payload, f, separators=(",", ":"))
    tmp.replace(path)


def load(path: pathlib.Path) -> dict:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def digest(payload: dict, drop: tuple[str, ...] = ()) -> str:
    """Hash of the parts that change with the game, not with the request.

    ESPN stamps volatile metadata onto every response; hashing it would make
    every poll look new and store hundreds of identical snapshots.
    """
    body = {k: v for k, v in payload.items() if k not in drop}
    return hashlib.sha1(json.dumps(body, sort_keys=True).encode()).hexdigest()


def stamp(now: dt.datetime | None = None) -> str:
    return (now or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc(iso: str) -> dt.datetime:
    return dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))


# ---- the schedule ---------------------------------------------------------------

def week_of(board: dict, saturday: dt.date) -> tuple[int, int] | None:
    """(season type, week number) whose calendar entry contains the Saturday."""
    noon = dt.datetime.combine(saturday, dt.time(12), ET).astimezone(dt.timezone.utc)
    for league_ in board.get("leagues") or []:
        for block in league_.get("calendar") or []:
            kind = int(block["value"]) if str(block.get("value", "")).isdigit() else 2   # 2 regular, 3 post
            for entry in block.get("entries") or []:
                try:
                    if utc(entry["startDate"]) <= noon <= utc(entry["endDate"]):
                        return kind, int(entry["value"])
                except (KeyError, ValueError):
                    continue
    return None


def slate_events(board: dict, saturday: dt.date) -> dict[str, dict]:
    """The slate: games whose ET kickoff falls on the Friday or the Saturday."""
    days = {saturday - dt.timedelta(days=1), saturday}
    out = {}
    for ev in board.get("events") or []:
        try:
            day = utc(ev["date"]).astimezone(ET).date()
        except (KeyError, ValueError):
            continue
        if day in days:
            out[str(ev["id"])] = ev
    return out


def plan(board: dict, saturday: dt.date, url: str) -> dict:
    events = slate_events(board, saturday)
    kickoffs = sorted(utc(ev["date"]) for ev in events.values())
    sunday = saturday + dt.timedelta(days=1)
    hard_stop = dt.datetime.combine(sunday, dt.time(HARD_STOP_HOUR), ET)
    return {
        "slate": saturday.isoformat(),
        "scoreboard": url,
        "games": len(events),
        "byDay": {d: sum(1 for ev in events.values() if utc(ev["date"]).astimezone(ET).strftime("%a") == d)
                  for d in ("Fri", "Sat")},
        "firstKickoff": kickoffs[0].astimezone(ET).isoformat() if kickoffs else None,
        "lastKickoff": kickoffs[-1].astimezone(ET).isoformat() if kickoffs else None,
        "start": (kickoffs[0] - LEAD).astimezone(ET).isoformat() if kickoffs else None,
        "hardStop": hard_stop.isoformat(),
    }


# ---- the recorder ---------------------------------------------------------------

class Recorder:
    def __init__(self, out: pathlib.Path, saturday: dt.date, url: str, interval: float, gap: float,
                 watch_top: int, watch: list[str], clock=time.time, sleep=time.sleep, fetcher=fetch,
                 watch_any_state: bool = False, echo: bool = True):
        self.out, self.saturday, self.url = out, saturday, url
        self.interval, self.gap, self.watch_top, self.watch = interval, gap, watch_top, watch
        self.clock, self.sleep, self.fetch = clock, sleep, fetcher
        self.watch_any_state = watch_any_state          # a dry run snapshots --watch before kickoff too
        self.echo = echo                                # the log always; the terminal only when asked
        self.log_path = out / "record.log"
        self.last: dict[str, str] = {}
        self.post_seen: dict[str, float] = {}
        self.requests = 0
        self.errors = 0
        self.last_error: str | None = None
        self.stopping = False
        out.mkdir(parents=True, exist_ok=True)
        self.finals = {p.name.removesuffix(".json.gz") for p in (out / "final").glob("*.json.gz")}
        self._resume_digests()

    # -- resume --

    def _resume_digests(self) -> None:
        """After a restart, don't write the newest snapshot a second time."""
        boards = sorted((self.out / "scoreboard").glob("*.json.gz"))
        if boards:
            try:
                self.last["board"] = digest(load(boards[-1]))
            except (OSError, ValueError, EOFError):
                pass
        for folder in sorted((self.out / "live").glob("*")):
            snaps = sorted(folder.glob("*.json.gz"))
            if snaps:
                try:
                    self.last[folder.name] = digest(load(snaps[-1]), drop=("meta",))
                except (OSError, ValueError, EOFError):
                    pass

    # -- output --

    def say(self, msg: str) -> None:
        line = f"{dt.datetime.now(ET):%Y-%m-%d %H:%M:%S %Z} {msg}"
        if self.echo:
            print(line, flush=True)
        try:
            if self.log_path.exists() and self.log_path.stat().st_size > LOG_ROTATE_BYTES:
                rotated = sorted(self.out.glob("record.log.*"))
                self.log_path.replace(self.out / f"record.log.{len(rotated) + 1}")
            with self.log_path.open("a") as f:
                f.write(line + "\n")
        except OSError:
            pass                              # a full disk must not stop the recording

    def heartbeat(self, **state) -> None:
        body = {"at": dt.datetime.now(ET).isoformat(timespec="seconds"), "pid": os.getpid(),
                "slate": self.saturday.isoformat(), "requests": self.requests, "errors": self.errors,
                "lastError": self.last_error, "finalsSaved": len(self.finals), **state}
        tmp = self.out / ".heartbeat.json.tmp"
        tmp.write_text(json.dumps(body, indent=1))
        tmp.replace(self.out / "heartbeat.json")

    def get(self, url: str) -> dict:
        self.requests += 1
        return self.fetch(url)

    # -- one cycle --

    def cycle(self) -> tuple[bool, dict]:
        board = self.get(self.url)
        if digest(board) != self.last.get("board"):
            save(self.out / "scoreboard" / f"{stamp()}.json.gz", board)
            self.last["board"] = digest(board)
        events = slate_events(board, self.saturday)
        records = leverage.rank([parse.game_record(ev) for ev in events.values()])
        by_id = {g["id"]: g for g in records}

        live = [g for g in records if g["status"]["state"] == "in" and not g["status"]["delayed"]]
        watched = list(dict.fromkeys([g["id"] for g in live[: self.watch_top]]
                                     + [e for e in self.watch if e in by_id
                                        and (self.watch_any_state or by_id[e]["status"]["state"] == "in")]))
        for event in watched:
            self.sleep(self.gap)
            sm = self.get(league.summary_url(event))
            h = digest(sm, drop=("meta",))
            if h != self.last.get(event):
                save(self.out / "live" / event / f"{stamp()}.json.gz", sm)
                self.last[event] = h

        now = self.clock()
        done = set()
        for event, g in by_id.items():
            name = g["status"]["name"]
            if name in DONE_STATES:
                done.add(event)
                continue
            if g["status"]["state"] != "post":
                continue
            if event in self.finals:
                done.add(event)
                continue
            first = self.post_seen.setdefault(event, now)
            if now - first < FINAL_SETTLE and not self.stopping:
                continue
            self.sleep(self.gap)
            sm = self.get(league.summary_url(event))
            save(self.out / "final" / f"{event}.json.gz", sm)
            self.finals.add(event)
            done.add(event)
            self.say(f"final {g['away']['abbr']} {g['away']['score']} at {g['home']['abbr']} {g['home']['score']} "
                     f"({event}): {len((sm.get('drives') or {}).get('previous') or [])} drives")

        counts = {"games": len(by_id), "live": len(live),
                  "pre": sum(1 for g in records if g["status"]["state"] == "pre"),
                  "delayed": sum(1 for g in records if g["status"]["delayed"]),
                  "final": sum(1 for g in records if g["status"]["state"] == "post"),
                  "done": len(done), "watching": watched}
        pending = [e for e, g in by_id.items() if g["status"]["state"] == "post" and e not in done]
        upcoming = sorted(g["kickoff"] for g in records if g["status"]["state"] == "pre" and g["kickoff"])
        counts["nextKickoff"] = upcoming[0] if upcoming else None
        counts["idle"] = not live and not counts["delayed"] and not pending
        finished = bool(by_id) and done >= set(by_id)
        if finished:
            save(self.out / "scoreboard" / f"{stamp()}-closing.json.gz", board)
        return finished, counts

    # -- the run --

    def run(self, start: dt.datetime | None, stop: dt.datetime, ends_when_final: bool = True) -> int:
        signal.signal(signal.SIGTERM, lambda *_: setattr(self, "stopping", True))
        if start:
            while dt.datetime.now(dt.timezone.utc) < start and not self.stopping:
                left = (start - dt.datetime.now(dt.timezone.utc)).total_seconds()
                self.heartbeat(phase="waiting", startsAt=start.astimezone(ET).isoformat())
                if int(left) % 1800 < 60:
                    self.say(f"waiting {left / 3600:.1f} h for the window at {start.astimezone(ET):%a %H:%M %Z}")
                self.sleep(min(60.0, max(1.0, left)))
        self.say(f"recording {self.url} to {self.out} until every slate game is final or "
                 f"{stop.astimezone(ET):%a %H:%M %Z}")
        backoff, last_tick = 0.0, self.clock()
        while not self.stopping:
            if dt.datetime.now(dt.timezone.utc) >= stop:
                self.say("hard stop reached")
                self.heartbeat(phase="stopped", reason="hard stop")
                return 0
            began = self.clock()
            if began - last_tick > max(180.0, self.interval * 3):
                # Wall-clock time moved far more than we slept: the Mac slept or
                # the process was suspended. Say so, then carry on.
                self.say(f"resumed after a {began - last_tick:.0f}s gap (sleep or suspend)")
            last_tick = began
            try:
                finished, counts = self.cycle()
                backoff = 0.0
                self.last_error = None
                self.say(f"{counts['games']} slate games: {counts['live']} live, {counts['pre']} pre, "
                         f"{counts['delayed']} delayed, {counts['final']} final, {len(self.finals)} finals saved"
                         + (f"; watching {','.join(counts['watching'])}" if counts["watching"] else ""))
                self.heartbeat(phase="recording", **counts)
                if finished and ends_when_final:
                    self.say("every slate game is final and saved; done")
                    self.heartbeat(phase="stopped", reason="all final", **counts)
                    return 0
                if counts["idle"] and counts["nextKickoff"] and ends_when_final:
                    wake = utc(counts["nextKickoff"]).astimezone(dt.timezone.utc) - LEAD
                    if wake - dt.datetime.now(dt.timezone.utc) > IDLE_MIN - LEAD:
                        self.say(f"nothing live until {utc(counts['nextKickoff']).astimezone(ET):%a %H:%M %Z}; "
                                 f"sleeping until {wake.astimezone(ET):%H:%M}")
                        while dt.datetime.now(dt.timezone.utc) < min(wake, stop) and not self.stopping:
                            self.heartbeat(phase="idle", wakesAt=wake.astimezone(ET).isoformat(), **counts)
                            self.sleep(60.0)
                        last_tick = self.clock()
                        continue
            except (urllib.error.URLError, TimeoutError, ConnectionError, json.JSONDecodeError, OSError) as exc:
                self.errors += 1
                self.last_error = f"{type(exc).__name__}: {exc}"
                # Network gone (Wi-Fi drop, sleep) or the edge pushing back: wait
                # longer each time, but never so long that a quarter goes unseen.
                backoff = min(120.0, max(15.0, backoff * 2))
                self.say(f"fetch failed ({self.last_error}); retrying in {backoff:.0f}s")
                self.heartbeat(phase="backing off", retryIn=backoff)
                self.sleep(backoff)
                last_tick = self.clock()
                continue
            self.sleep(max(5.0, self.interval - (self.clock() - began)))
        self.say("stopped by signal")
        self.heartbeat(phase="stopped", reason="signal")
        return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--slate", required=True, help="the Saturday, YYYY-MM-DD (its Friday is included)")
    ap.add_argument("--out", type=pathlib.Path, help="default data/capture/<slate>")
    ap.add_argument("--interval", type=float, default=60.0, help="seconds between scoreboards")
    ap.add_argument("--gap", type=float, default=2.5, help="seconds between consecutive requests")
    ap.add_argument("--watch-top", type=int, default=6, help="snapshot the N highest-leverage live games")
    ap.add_argument("--watch", nargs="*", default=[], help="event ids to snapshot live as well")
    ap.add_argument("--plan", action="store_true", help="print the window from the real schedule and exit")
    ap.add_argument("--dry-run", type=float, metavar="MINUTES",
                    help="skip the wait and record now for MINUTES, to prove the setup works")
    args = ap.parse_args(argv)

    try:
        saturday = dt.date.fromisoformat(args.slate)
    except ValueError:
        print(f"--slate {args.slate!r} is not YYYY-MM-DD", file=sys.stderr)
        return 2
    if saturday.weekday() != 5:
        print(f"--slate {saturday} is a {saturday:%A}, not a Saturday", file=sys.stderr)
        return 2

    base = fetch(league.scoreboard_url())
    week = week_of(base, saturday)
    url = league.scoreboard_url(week=week[1], seasontype=week[0]) if week else league.scoreboard_url()
    board = fetch(url) if week else base
    window = plan(board, saturday, url)
    if args.plan:
        print(json.dumps(window, indent=2))
        return 0 if window["games"] else 3
    if not window["games"]:
        print(f"no FBS games on the Friday or Saturday of {saturday}", file=sys.stderr)
        return 3

    out = args.out or REPO / "data/capture" / saturday.isoformat()
    rec = Recorder(out, saturday, url, args.interval, args.gap, args.watch_top, args.watch,
                   watch_any_state=bool(args.dry_run))
    rec.say(f"plan: {json.dumps(window)}")
    if args.dry_run:
        stop = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=args.dry_run)
        code = rec.run(None, stop, ends_when_final=False)
        rec.say(f"dry run done: {rec.requests} requests, {rec.errors} errors")
        return code
    start = utc(window["start"]).astimezone(dt.timezone.utc)
    return rec.run(start, utc(window["hardStop"]).astimezone(dt.timezone.utc))


if __name__ == "__main__":
    raise SystemExit(main())
