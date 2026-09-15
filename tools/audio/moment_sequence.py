"""Shoot a moment as a sequence of stills, so choreography can be judged.

A still proves a frame, not a schedule. This plays the pick-six at 1x into
the stadium and takes a screenshot at each offset after the snap - whistle,
surge, strobe, the fireworks opening, the chime, settle - on one launch.

    python3 tools/audio/moment_sequence.py --device <udid> --out .work/shots/moments-it1 \
        --offsets 3.2 3.8 4.4 5.2 6.5 8.5 --extra="-stadiumPitch 14"

Uses tools/lookdev.py's staging so the replay is exactly the look-dev one.
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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", required=True)
    ap.add_argument("--out", required=True, type=pathlib.Path)
    ap.add_argument("--port", type=int, default=8806)
    ap.add_argument("--app", type=pathlib.Path, default=ROOT / ".work/dd/Build/Products/Debug-xrsimulator/FantasyEdge.app")
    ap.add_argument("--shot", default="td-moment")
    ap.add_argument("--offsets", nargs="*", type=float, default=[3.2, 3.8, 4.4, 5.2, 6.5, 8.5])
    ap.add_argument("--settle", type=float, default=10.0)
    ap.add_argument("--extra", default="", help='launch arguments as one string, e.g. --extra="-stadiumPitch 14"')
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    source = ld.stage_replays()
    env = {**os.environ, "FANTASYEDGE_REPLAY_DIR": str(source)}
    db = pathlib.Path(tempfile.mkdtemp()) / "moments.db"
    api = subprocess.Popen([sys.executable, "-m", "fantasyedge", "--db", str(db), "api", "--host", "127.0.0.1",
                            "--port", str(args.port)], cwd=ROOT, env=env,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try:
                ld.get(args.port, "/api/health")
                break
            except Exception:
                time.sleep(0.2)
        ld.simctl("boot", args.device, check=False)
        ld.simctl("install", args.device, str(args.app))
        ld.post(args.port, {"action": "load", "event": ld.PICK_SIX})
        at = ld.pick_six_second()
        ld.post(args.port, {"action": "seek", "at": at - 3})
        ld.post(args.port, {"action": "pause"})
        ld.simctl("launch", "--terminate-running-process", args.device, ld.BUNDLE, "-fe.host",
                  f"127.0.0.1:{args.port}", "-stadiumStats", "-stadiumMute", "-shot", args.shot, *args.extra.split(), check=False)
        time.sleep(args.settle)
        ld.post(args.port, {"action": "speed", "speed": 1})
        ld.post(args.port, {"action": "play"})
        start = time.monotonic()
        for off in sorted(args.offsets):
            time.sleep(max(0.0, start + off - time.monotonic()))
            shot = args.out / f"t{off:04.1f}.png"
            ld.simctl("io", args.device, "screenshot", str(shot), check=False)
            print(f"t+{off:.1f}s after play -> {shot}", flush=True)
        for off in sorted(args.offsets):
            shot = args.out / f"t{off:04.1f}.png"
            subprocess.run(["sips", "-Z", "1000", str(shot), "--out", str(args.out / f"s-t{off:04.1f}.png")],
                           capture_output=True)
    finally:
        api.terminate()
        ld.simctl("terminate", args.device, ld.BUNDLE, check=False)


if __name__ == "__main__":
    main()
