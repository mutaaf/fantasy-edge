"""Measure what it costs to move the stadium from one game to another.

The red-zone channel leaves a game every few seconds, so the price of a
changeover is the whole feasibility question: a rebuild is three seconds of
blocked main thread and a repaint is a texture swap. This walks the app
between the committed fixture matchups and reads the app's own timing lines
back out of the simulator log, so the number is measured rather than reasoned
about.

    python3 tools/measure_changeover.py --device <udid> --app <path to .app>

It drives the replay director rather than the live feed because a changeover
is a changeover whichever target brings the scene - what the renderer sees is
a spec whose event id is not the one on screen - and two live games with
plays in them cannot be conjured on a Sunday morning.
"""

import argparse
import json
import pathlib
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fantasyedge import replay as rp                                  # noqa: E402

FIX = ROOT / "tests" / "fixtures"
BUNDLE = "com.mutaaf.fantasyedge"
# DAL@PHI, MIN@CHI, LAR@SEA: three different pairs of clubs, so every switch
# is a real change of livery rather than the same colours twice.
GAMES = ["401772510", "401772810", "401772949"]


def stage() -> pathlib.Path:
    source = pathlib.Path(tempfile.mkdtemp(prefix="changeover-"))
    for path in FIX.glob("replay_game_*.json"):
        event = path.stem.split("_")[-1]
        g = json.loads(path.read_text())
        (source / f"{event}.json").write_text(json.dumps(g["summary"]))
        rp.scoreboard_path(source, event).write_text(json.dumps(g["scoreboard"]))
    return source


def post(port: int, body: dict) -> dict:
    req = urllib.request.Request(f"http://127.0.0.1:{port}/api/replay",
                                 data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def simctl(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["xcrun", "simctl", *args], capture_output=True, text=True, check=check)


def log_since(device: str, since: str) -> str:
    return subprocess.run(
        ["xcrun", "simctl", "spawn", device, "log", "show", "--start", since,
         "--style", "compact", "--predicate", 'subsystem == "com.mutaaf.fantasyedge"'],
        capture_output=True, text=True).stdout


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", required=True)
    ap.add_argument("--app", required=True, type=pathlib.Path)
    ap.add_argument("--port", type=int, default=8793)
    ap.add_argument("--switches", type=int, default=6)
    ap.add_argument("--settle", type=float, default=6.0,
                    help="seconds to leave the app on each game before moving it")
    args = ap.parse_args()

    source = stage()
    db = pathlib.Path(tempfile.mkdtemp()) / "measure.db"
    api = subprocess.Popen(
        [sys.executable, "-m", "fantasyedge", "--db", str(db), "api", "--host", "127.0.0.1",
         "--port", str(args.port)], cwd=ROOT,
        env={**__import__("os").environ, "FANTASYEDGE_REPLAY_DIR": str(source)},
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{args.port}/api/health", timeout=2).read()
                break
            except Exception:
                time.sleep(1)

        post(args.port, {"action": "load", "event": GAMES[0]})
        post(args.port, {"action": "pause"})

        simctl("boot", args.device, check=False)
        simctl("install", args.device, str(args.app))
        simctl("terminate", args.device, BUNDLE, check=False)
        launched = time.strftime("%Y-%m-%d %H:%M:%S")
        started = time.time()
        # `-shot` is what the look-dev harness uses to open the stadium, and it
        # is the path that is known to work; -openStadium alone left the app in
        # its board window with nothing to measure.
        simctl("launch", args.device, BUNDLE,
               "-fe.host", f"127.0.0.1:{args.port}", "-stadiumStats", "-stadiumMute",
               "-shot", "bowl-wide")
        # Let it open, load its assets and build the first matchup.
        time.sleep(args.settle * 3)
        opened = time.time() - started

        for i in range(args.switches):
            post(args.port, {"action": "load", "event": GAMES[(i + 1) % len(GAMES)]})
            time.sleep(args.settle)

        out = log_since(args.device, launched)
    finally:
        simctl("terminate", args.device, BUNDLE, check=False)
        api.terminate()

    keep = [l for l in out.splitlines()
            if any(k in l for k in ("stadium-timing", "crowd dress", "crowd:", "changeover:"))]
    print("\n".join(keep))
    print(f"\n[measure] launch to settled: {opened:.1f}s wall clock, {args.switches} switches")


if __name__ == "__main__":
    main()
