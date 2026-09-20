"""Shoot the immersive red-zone channel: the panel, and a changeover in flight.

The look-dev harness shoots one scene at a time; a changeover only exists
between two, so this drives the replay director from one matchup to the next
and takes frames across the fade. The panel is shot with `-stadiumUnfold`,
which is how every other panel is captured.

    python3 tools/shoot_redzone.py --device <udid> --app <path> --out docs/lookdev/redzone
"""

import argparse
import json
import os
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
FROM, TO = "401772810", "401772510"          # MIN@CHI, then DAL@PHI


def stage() -> pathlib.Path:
    source = pathlib.Path(tempfile.mkdtemp(prefix="redzone-shot-"))
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


def built(device: str, since: str) -> bool:
    out = subprocess.run(
        ["xcrun", "simctl", "spawn", device, "log", "show", "--start", since, "--style", "compact",
         "--predicate", 'subsystem == "com.mutaaf.fantasyedge"'],
        capture_output=True, text=True).stdout
    return "[stadium-stats] stadium: models" in out and "crowd dress composed" in out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", required=True)
    ap.add_argument("--app", required=True, type=pathlib.Path)
    ap.add_argument("--out", type=pathlib.Path, default=ROOT / "docs" / "lookdev" / "redzone")
    ap.add_argument("--port", type=int, default=8794)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    source = stage()
    db = pathlib.Path(tempfile.mkdtemp()) / "shoot.db"
    api = subprocess.Popen(
        [sys.executable, "-m", "fantasyedge", "--db", str(db), "api", "--host", "127.0.0.1",
         "--port", str(args.port)], cwd=ROOT,
        env={**os.environ, "FANTASYEDGE_REPLAY_DIR": str(source)},
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{args.port}/api/health", timeout=2).read()
                break
            except Exception:
                time.sleep(1)
        post(args.port, {"action": "load", "event": FROM})
        post(args.port, {"action": "pause"})

        simctl("boot", args.device, check=False)
        simctl("install", args.device, str(args.app))
        simctl("terminate", args.device, BUNDLE, check=False)
        since = time.strftime("%Y-%m-%d %H:%M:%S")
        simctl("launch", args.device, BUNDLE,
               "-fe.host", f"127.0.0.1:{args.port}", "-stadiumStats", "-stadiumMute",
               "-stadiumUnfold", "-stadiumFadeScale", "10", "-shot", "bowl-wide")
        for _ in range(90):
            if built(args.device, since):
                break
            time.sleep(1)
        time.sleep(3)

        shot = lambda name: simctl("io", args.device, "screenshot", str(args.out / f"{name}.png"), check=False)
        shot("s-panel-before")                       # MIN@CHI, panel open

        # The changeover: the fade is two halves of seatFadeSeconds, so frames
        # a fifth of a second apart straddle it.
        post(args.port, {"action": "load", "event": TO})
        for i, wait in enumerate([0.1, 0.9, 0.9, 0.9, 1.2]):
            time.sleep(wait)
            shot(f"s-changeover-{i}")
        time.sleep(4)
        shot("s-panel-after")                        # DAL@PHI, arrived
    finally:
        simctl("terminate", args.device, BUNDLE, check=False)
        api.terminate()
    print(f"shots in {args.out}")


if __name__ == "__main__":
    main()
