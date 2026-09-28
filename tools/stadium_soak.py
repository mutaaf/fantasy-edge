#!/usr/bin/env python3
"""Open and close every stadium, over and over, in the simulator.

    python3 tools/stadium_soak.py                    # both apps, 6 cycles each
    python3 tools/stadium_soak.py --app saturday --cycles 10 --game 401856699
    python3 tools/stadium_soak.py --no-install       # the apps already on the rig

Launches each app with `-stadiumSoak`, which walks the table and the stadium
through the same `StadiumPassage` a tap uses (StadiumKit/StadiumSoak.swift),
and reads its `[stadium-soak]` lines back from the simulator's log. Exits 1 on
any of: a FAIL line, the app dying before it says `done`, no `done` inside the
time limit, or a closed footprint that keeps climbing - a stadium that is not
given back when it closes.

Both apps draw from their own API, and without one the passage is soaked but
no stadium is ever built. Saturday draws a live game: `make -C apps/saturday
live` (or `replay`). Fantasy Edge draws its loaded replay: `python3 -m
fantasyedge api --port 8770`, then load a game into it (`POST /api/replay`
with `{"action": "load", "event": ...}`).

Frame rate and memory the system would kill for are a headset's to say
(docs/DEVICE.md). What this proves is that nothing wedges and nothing is kept.
"""
from __future__ import annotations

import argparse
import json
import os
import queue
import threading
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIM = os.environ.get("FE_SIM", "Stadium 26.5")
APPS = {
    "saturday": {"bundle": "com.mutaaf.saturday",
                 "app": ROOT / ".work/dd-saturday/Build/Products/Debug-xrsimulator/Saturday.app",
                 "build": [str(ROOT / "apps/saturday/apple/sim.sh"), "build"]},
    "fantasyedge": {"bundle": "com.mutaaf.fantasyedge",
                    "app": ROOT / ".work/dd/Build/Products/Debug-xrsimulator/FantasyEdge.app",
                    "build": [str(ROOT / "apple/sim.sh"), "build"]},
}
# A stadium's first build in the simulator is the slow part; a cycle is two
# table waits, the walk, five seconds inside and the walk out.
SECONDS_PER_CYCLE = 120
# Growth in the closed footprint, per cycle after the first, that counts as a
# stadium kept. The first cycle fills caches that are meant to stay.
LEAK_MB_PER_CYCLE = 15.0

LINE = re.compile(r"\[stadium-soak\] (.*)$")
DONE = re.compile(r"done: (\d+) cycles, (\d+) failures, closed footprint (\d+) -> (\d+) MB, (-?[\d.]+) MB per cycle")


def sim_id() -> str:
    out = json.loads(subprocess.check_output(["xcrun", "simctl", "list", "devices", "available", "-j"]))
    for runtime, devices in out["devices"].items():
        if "xrOS" in runtime or "visionOS" in runtime:
            for d in devices:
                if d["name"] == SIM:
                    return d["udid"]
    sys.exit(f"no visionOS simulator named {SIM!r}; see apple/sim.sh doctor")


def pick_game() -> str | None:
    """A live game with a scene, else any game, from Saturday's own API."""
    try:
        with urllib.request.urlopen("http://127.0.0.1:8780/api/slate", timeout=30) as r:
            slate = json.load(r)
    except OSError:
        return None
    games = slate.get("games") or []
    live = [g["id"] for g in games if g["status"]["state"] == "in"]
    return slate.get("spotlight") or (live[0] if live else (games[0]["id"] if games else None))


def soak(name: str, device: str, cycles: int, game: str | None, install: bool, keep: bool = False,
         extra: list[str] = ()) -> bool:
    spec = APPS[name]
    print(f"\n== {name}: {cycles} cycles")
    if install:
        subprocess.run(spec["build"], check=True, stdout=subprocess.DEVNULL)
        subprocess.run(["xcrun", "simctl", "install", device, str(spec["app"])], check=True)
    args = ["-stadiumSoak", str(cycles), *extra]
    if name == "saturday":
        game = game or pick_game()
        if not game:
            print("  FAIL: Saturday's API is not answering on :8780; start it with make -C apps/saturday live")
            return False
    if game:
        args += ["-soakGame", game]
        print(f"  game {game}")

    subprocess.run(["xcrun", "simctl", "terminate", device, spec["bundle"]], stderr=subprocess.DEVNULL)
    stream = subprocess.Popen(
        ["xcrun", "simctl", "spawn", device, "log", "stream", "--style", "compact", "--level", "info",
         "--predicate", 'eventMessage CONTAINS "[stadium-soak]"'],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    time.sleep(2)                               # let the stream attach before anything is said
    out = subprocess.check_output(["xcrun", "simctl", "launch", device, spec["bundle"], *args], text=True)
    pid = int(out.strip().rsplit(":", 1)[1])

    said: queue.Queue[str] = queue.Queue()
    threading.Thread(target=lambda: [said.put(l) for l in stream.stdout], daemon=True).start()
    limit = 60 + cycles * SECONDS_PER_CYCLE
    deadline = time.time() + limit
    lines, done = [], None
    try:
        while time.time() < deadline and not done:
            try:
                raw = said.get(timeout=0.5)
            except queue.Empty:
                raw = ""
            m = LINE.search(raw.rstrip("\n"))
            if m:
                lines.append(m.group(1))
                print("  " + m.group(1), flush=True)
                done = DONE.search(m.group(1))
            if not done and subprocess.run(["kill", "-0", str(pid)], stderr=subprocess.DEVNULL).returncode:
                print(f"  FAIL: {name} (pid {pid}) died after {len(lines)} lines; see ~/Library/Logs/DiagnosticReports")
                return False
    finally:
        stream.terminate()
        if not keep:
            subprocess.run(["xcrun", "simctl", "terminate", device, spec["bundle"]], stderr=subprocess.DEVNULL)

    if not done:
        print(f"  FAIL: no 'done' inside {limit}s; the last line above is where it stuck")
        return False
    failures, growth = int(done.group(2)), float(done.group(5))
    leak = cycles >= 4 and growth > LEAK_MB_PER_CYCLE
    ok = failures == 0 and not leak
    verdict = "PASS" if ok else "FAIL"
    why = [f"{failures} failed checks"] if failures else []
    if leak:
        why.append(f"closed footprint climbs {growth:.1f} MB a cycle (limit {LEAK_MB_PER_CYCLE:.0f})")
    print(f"  {verdict}" + (": " + "; ".join(why) if why else ""))
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--app", choices=[*APPS, "all"], default="all")
    ap.add_argument("--cycles", type=int, default=6)
    ap.add_argument("--game", help="event id to soak (Saturday: defaults to the API's spotlight)")
    ap.add_argument("--no-install", dest="install", action="store_false")
    ap.add_argument("--extra", default="", help="more launch arguments, e.g. '-fe.host 127.0.0.1:9' for an API that is down")
    ap.add_argument("--keep", action="store_true", help="leave the app running afterwards, to see what is on screen")
    a = ap.parse_args()
    device = sim_id()
    subprocess.run(["xcrun", "simctl", "boot", device], stderr=subprocess.DEVNULL)
    subprocess.run(["xcrun", "simctl", "bootstatus", device, "-b"], stdout=subprocess.DEVNULL)
    names = list(APPS) if a.app == "all" else [a.app]
    results = {n: soak(n, device, a.cycles, a.game if n == "saturday" else None, a.install, a.keep, a.extra.split()) for n in names}
    print("\n" + ", ".join(f"{n} {'PASS' if ok else 'FAIL'}" for n, ok in results.items()))
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
