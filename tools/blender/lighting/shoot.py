"""Lighting's own review shots in the visionOS simulator, framed without a
world tilt.

    python3 tools/blender/lighting/shoot.py --device <udid> --out .work/shots/lighting-itN [--port 8803] [--app PATH]

Why not only tools/lookdev.py: its `lights-haze`, `sky-dome` and `bowl-wide`
presets tilt the world about a pivot that is not the eye, and at the time of
writing all three open inside the stands (a grey or black frame) on the
director's own build as well as this one. These framings keep pitch at 0 and
turn instead, which the td-moment preset proves renders. Uses lookdev.py's
replay staging and API, so the stadium is the same one.
"""
from __future__ import annotations

import argparse
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
import lookdev as L  # noqa: E402

# name -> (seat, yaw, pitch, replay position)
SHOTS = {
    "rim-far": ("club", 0, 0, "early"),          # the far stands and their banks, head on
    "rim-left": ("club", -45, 0, "early"),        # banks raking across the upper deck
    "rim-behind": ("club", 180, 0, "early"),      # the banks behind the wearer, the far model
    "field-up": ("field", 0, 0, "early"),          # from the grass: the bowl rising into light
    "endzone": ("endzone", 0, 0, "early"),         # down the field, beams crossing
    "strobe": ("club", 30, 0, "touchdown"),        # the moment: strobe and wash
    "tabletop": (None, 0, 0, "redzone"),
    "bowl-wide-club": ("club", 0, -8, "early"),     # bowl-wide's framing from the club seat
    "bowl-wide-upper": ("upper", 0, -8, "early"),   # the shared preset's seat
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", required=True)
    ap.add_argument("--out", required=True, type=pathlib.Path)
    ap.add_argument("--port", type=int, default=8803)
    ap.add_argument("--app", type=pathlib.Path, default=ROOT / ".work/dd/Build/Products/Debug-xrsimulator/FantasyEdge.app")
    ap.add_argument("--only", nargs="*", choices=sorted(SHOTS))
    ap.add_argument("--settle", type=float, default=14.0)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    source = L.stage_replays()
    env = {**os.environ, "FANTASYEDGE_REPLAY_DIR": str(source)}
    db = pathlib.Path(tempfile.mkdtemp()) / "shoot.db"
    api = subprocess.Popen([sys.executable, "-m", "fantasyedge", "--db", str(db), "api", "--host", "127.0.0.1",
                            "--port", str(args.port)], cwd=ROOT, env=env,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try:
                L.get(args.port, "/api/health")
                break
            except Exception:
                time.sleep(0.2)
        L.simctl("boot", args.device, check=False)
        L.simctl("install", args.device, str(args.app))
        L.post(args.port, {"action": "load", "event": L.PICK_SIX})
        L.post(args.port, {"action": "pause"})
        positions = {"touchdown": L.pick_six_second(), "redzone": L.red_zone_second(args.port)}
        positions["early"] = positions["redzone"] - 150
        started = time.strftime("%Y-%m-%d %H:%M:%S")
        for name, (seat, yaw, pitch, where) in SHOTS.items():
            if args.only and name not in args.only:
                continue
            at = positions[where]
            L.simctl("terminate", args.device, L.BUNDLE, check=False)
            if where == "touchdown":
                L.post(args.port, {"action": "seek", "at": at - 4})
                L.post(args.port, {"action": "speed", "speed": 1})
                L.post(args.port, {"action": "play"})
            else:
                L.post(args.port, {"action": "seek", "at": at})
                L.post(args.port, {"action": "pause"})
            launch = ["launch", "--terminate-running-process", args.device, L.BUNDLE,
                      "-fe.host", f"127.0.0.1:{args.port}", "-stadiumStats", "-stadiumMute"]
            if seat is None:
                launch += ["-shot", "tabletop"]
            else:
                launch += ["-shot", "td-moment", "-stadiumSeat", seat, "-stadiumLook", str(yaw), "-stadiumPitch", str(pitch)]
            L.simctl(*launch, check=False)
            time.sleep(args.settle + (3 if where == "touchdown" else 0))
            shot = args.out / f"{name}.png"
            L.simctl("io", args.device, "screenshot", str(shot), check=False)
            subprocess.run(["sips", "-Z", "1400", str(shot), "--out", str(args.out / f"s-{name}.png")], capture_output=True)
            print(f"{name}: {seat} yaw {yaw} pitch {pitch} at {at}s -> {shot}", flush=True)
        log = subprocess.run(["xcrun", "simctl", "spawn", args.device, "log", "show", "--start", started, "--style", "compact",
                              "--predicate", 'subsystem == "com.mutaaf.fantasyedge"'], capture_output=True, text=True).stdout
        lines = sorted({ln[ln.index("[stadium"):] for ln in log.splitlines() if "[stadium" in ln})
        (args.out / "stats.txt").write_text("\n".join(lines) + "\n")
    finally:
        api.terminate()
        shutil.rmtree(source, ignore_errors=True)


if __name__ == "__main__":
    main()
