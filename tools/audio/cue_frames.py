"""Shoot real cues end to end: red zone, third down, a turnover, the final.

For each, the replay is parked a few seconds before the play the server's
cue (or turnover moment) comes from, the app is launched into the crowd
close-up and built, then the game plays at 1x until the scene's own
`activeCue` / `activeMoment` shows it, and the frame is taken
`--after` seconds later. Nothing is forced with -crowdCue: what shows is
what the composer dispatched from the scene.

    python3 tools/audio/cue_frames.py --device <udid> --out .work/shots/cues
"""

from __future__ import annotations

import argparse
import os
import pathlib
import subprocess
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT))

import lookdev as ld  # noqa: E402

REGULATION, OVERTIME = "401772510", "401772949"


def find(port: int, event: str, test, lo: int, hi: int, step: int = 15) -> int | None:
    ld.post(port, {"action": "load", "event": event})
    ld.post(port, {"action": "pause"})
    for at in range(lo, hi, step):
        ld.post(port, {"action": "seek", "at": at})
        if test(ld.get(port, "/api/replay/scene")):
            return at
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", required=True)
    ap.add_argument("--out", required=True, type=pathlib.Path)
    ap.add_argument("--port", type=int, default=8806)
    ap.add_argument("--app", type=pathlib.Path, default=ROOT / ".work/dd/Build/Products/Debug-xrsimulator/FantasyEdge.app")
    ap.add_argument("--after", type=float, default=1.6)
    ap.add_argument("--only", nargs="*")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    source = ld.stage_replays()
    env = {**os.environ, "FANTASYEDGE_REPLAY_DIR": str(source)}
    db = pathlib.Path(tempfile.mkdtemp()) / "cues.db"
    api = subprocess.Popen([sys.executable, "-m", "fantasyedge", "--db", str(db), "api", "--host", "127.0.0.1",
                            "--port", str(args.port)], cwd=ROOT, env=env,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    cue = lambda kind: (lambda s: (s.get("activeCue") or {}).get("kind") == kind)
    turnover = lambda s: (s.get("activeMoment") or {}).get("kind") == "turnover"
    plan = [
        ("redzone", REGULATION, cue("redZone"), 200, 3600),
        ("thirddown", REGULATION, cue("thirdDown"), 200, 3600),
        ("turnover", OVERTIME, turnover, 200, 4000),
        ("final", REGULATION, cue("final"), 3500, 3700),
    ]
    try:
        for _ in range(50):
            try:
                ld.get(args.port, "/api/health")
                break
            except Exception:
                time.sleep(0.2)
        ld.simctl("boot", args.device, check=False)
        ld.simctl("install", args.device, str(args.app))
        for name, event, test, lo, hi in plan:
            if args.only and name not in args.only:
                continue
            at = find(args.port, event, test, lo, hi)
            if at is None:
                print(f"{name}: no such cue in {event}", flush=True)
                continue
            ld.simctl("terminate", args.device, ld.BUNDLE, check=False)
            ld.post(args.port, {"action": "seek", "at": max(0, at - 20)})
            ld.post(args.port, {"action": "pause"})
            launched = time.strftime("%Y-%m-%d %H:%M:%S")
            ld.simctl("launch", "--terminate-running-process", args.device, ld.BUNDLE, "-fe.host",
                      f"127.0.0.1:{args.port}", "-stadiumMute", "-shot", "crowd-closeup", check=False)
            ld.wait_for_build(args.device, launched, False, 60.0)
            time.sleep(3.0)
            ld.post(args.port, {"action": "speed", "speed": 1})
            ld.post(args.port, {"action": "play"})
            deadline = time.monotonic() + 40
            seen = None
            while time.monotonic() < deadline:
                s = ld.get(args.port, "/api/replay/scene")
                if test(s):
                    seen = (s.get("activeCue") or s.get("activeMoment") or {})
                    break
                time.sleep(0.25)
            if not seen:
                print(f"{name}: cue did not arrive while playing", flush=True)
                continue
            time.sleep(args.after)
            png = args.out / f"{name}.png"
            ld.simctl("io", args.device, "screenshot", str(png), check=False)
            subprocess.run(["sips", "-Z", "1000", "-s", "format", "jpeg", "-s", "formatOptions", "75", str(png),
                            "--out", str(args.out / f"{name}.jpg")], capture_output=True)
            print(f"{name}: {event} at {at}s, cue {seen.get('kind')} {seen.get('treatment', seen.get('detail'))} "
                  f"-> {png}", flush=True)
    finally:
        api.terminate()
        ld.simctl("terminate", args.device, ld.BUNDLE, check=False)
        ld.simctl("shutdown", args.device, check=False)


if __name__ == "__main__":
    main()
