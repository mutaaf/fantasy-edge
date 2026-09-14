"""Run the API on the repo's recorded games, for the Android emulator.

    python3 clients/android/scripts/serve_replay.py            # port 8794
    python3 clients/android/scripts/serve_replay.py --port 8794 --event 401772810 --at 1929

Lays the committed whole-game fixtures out as replay captures in a temporary
directory, starts `python3 -m fantasyedge api` on loopback with
FANTASYEDGE_REPLAY_DIR pointing at them, and optionally loads a game and seeks
to an instant (the Bears pick-six is 401772810 at 1929). The emulator reaches
it at http://10.0.2.2:<port>; its requests arrive on loopback, so the replay
remote's POST guard needs no override. No network.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from fantasyedge import replay as rp                                    # noqa: E402


def post(port: int, body: dict) -> dict:
    req = urllib.request.Request(f"http://127.0.0.1:{port}/api/replay", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", type=int, default=8794)
    ap.add_argument("--event")
    ap.add_argument("--at", type=int)
    ap.add_argument("--speed", type=float)
    ap.add_argument("--play", action="store_true")
    args = ap.parse_args()

    source = pathlib.Path(tempfile.mkdtemp(prefix="fe-replay-"))
    for game in sorted((ROOT / "tests" / "fixtures").glob("replay_game_*.json")):
        g = json.loads(game.read_text())
        event = game.stem.removeprefix("replay_game_")
        (source / f"{event}.json").write_text(json.dumps(g["summary"]))
        rp.scoreboard_path(source, event).write_text(json.dumps(g["scoreboard"]))
    env = {**os.environ, "FANTASYEDGE_REPLAY_DIR": str(source)}
    db = pathlib.Path(tempfile.mkdtemp(prefix="fe-db-")) / "api.db"
    server = subprocess.Popen([sys.executable, "-m", "fantasyedge", "--db", str(db), "api",
                               "--host", "127.0.0.1", "--port", str(args.port), "--no-ai"], cwd=ROOT, env=env)
    try:
        for _ in range(50):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{args.port}/api/replay", timeout=1).read()
                break
            except OSError:
                time.sleep(0.2)
        if args.event:
            post(args.port, {"action": "load", "event": args.event})
            if args.at is not None:
                post(args.port, {"action": "seek", "at": args.at})
            if args.speed:
                post(args.port, {"action": "speed", "speed": args.speed})
            if args.play:
                post(args.port, {"action": "play"})
        print(f"replay API on http://127.0.0.1:{args.port} (emulator: http://10.0.2.2:{args.port}); captures in {source}", flush=True)
        server.wait()
    finally:
        server.terminate()


if __name__ == "__main__":
    main()
