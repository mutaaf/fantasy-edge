"""Shoot the immersive look-dev shots in a visionOS simulator.

Serves the committed whole-game fixtures through the real API as a replay,
positions the replay for each shot, launches the app straight into the
tabletop or the stadium, and saves a screenshot. No network, no capture.

    python3 tools/lookdev.py --device <udid> --out .work/shots/iter1
    python3 tools/lookdev.py --device <udid> --out .work/shots/iter1 --only wide touchdown

Shots:
  tabletop   the pick-six game on the table, mid-drive
  wide       stadium, 50-yard line lower bowl, a normal snap
  sideline   stadium, field level on the home sideline
  touchdown  stadium, the Bears pick-six moment
  redzone    stadium, a red-zone snap with lines and trails
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fantasyedge import replay as rp          # noqa: E402

FIX = ROOT / "tests" / "fixtures"
PICK_SIX = "401772810"
BUNDLE = "com.mutaaf.fantasyedge"


def stage_replays() -> pathlib.Path:
    source = pathlib.Path(tempfile.mkdtemp(prefix="lookdev-replay-"))
    for path in FIX.glob("replay_game_*.json"):
        event = path.stem.split("_")[-1]
        g = json.loads(path.read_text())
        (source / f"{event}.json").write_text(json.dumps(g["summary"]))
        rp.scoreboard_path(source, event).write_text(json.dumps(g["scoreboard"]))
    return source


def post(port: int, body: dict) -> dict:
    req = urllib.request.Request(f"http://127.0.0.1:{port}/api/replay", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)


def get(port: int, path: str) -> dict:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=10) as r:
        return json.load(r)


def pick_six_second() -> int:
    g = json.loads((FIX / f"replay_game_{PICK_SIX}.json").read_text())
    summary = g["summary"]
    lengths = rp.period_lengths(summary)
    play = next(p for p in rp._all_plays(summary) if "INTERCEPTED by N.Wright" in (p.get("text") or ""))
    return int(rp.play_seconds(play, lengths))


def red_zone_second(port: int) -> int:
    for at in range(300, 3600, 45):
        post(port, {"action": "seek", "at": at})
        s = get(port, "/api/replay/scene")
        if s["status"]["redZone"] and s.get("ball") and len(s["lasers"]) == 2 and \
                s["shownDrive" if "shownDrive" in s else "drives"] and s["currentDrive"] is not None and \
                len(s["drives"][s["currentDrive"]]["arcs"]) >= 5:
            return at
    return 1800


def simctl(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["xcrun", "simctl", *args], capture_output=True, text=True, check=check)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", required=True)
    ap.add_argument("--out", required=True, type=pathlib.Path)
    ap.add_argument("--port", type=int, default=8795)
    ap.add_argument("--app", type=pathlib.Path,
                    default=ROOT / ".work/dd/Build/Products/Debug-xrsimulator/FantasyEdge.app")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--settle", type=float, default=9.0)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    source = stage_replays()
    env = {**os.environ, "FANTASYEDGE_REPLAY_DIR": str(source)}
    db = pathlib.Path(tempfile.mkdtemp()) / "lookdev.db"
    api = subprocess.Popen([sys.executable, "-m", "fantasyedge", "--db", str(db), "api", "--host", "127.0.0.1",
                            "--port", str(args.port)], cwd=ROOT, env=env,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try:
                get(args.port, "/api/health")
                break
            except Exception:
                time.sleep(0.2)
        simctl("boot", args.device, check=False)
        simctl("install", args.device, str(args.app))
        post(args.port, {"action": "load", "event": PICK_SIX})
        post(args.port, {"action": "pause"})
        td = pick_six_second()
        rz = red_zone_second(args.port)
        shots = {
            "tabletop": (rz, ["-openTabletop", "replay"]),
            "wide": (rz - 150, ["-openTabletop", "replay", "-openStadium", "-stadiumStyle", "full"]),
            "sideline": (rz, ["-openTabletop", "replay", "-openStadium", "-stadiumStyle", "full",
                              "-stadiumSeat", "field"]),
            "touchdown": (td, ["-openTabletop", "replay", "-openStadium", "-stadiumStyle", "full",
                               "-stadiumLook", "30"]),
            "redzone": (rz, ["-openTabletop", "replay", "-openStadium", "-stadiumStyle", "full"]),
        }
        logs = []
        for name, (at, launch) in shots.items():
            if args.only and name not in args.only:
                continue
            simctl("terminate", args.device, BUNDLE, check=False)
            if name == "touchdown":
                # Just before the snap at 1x, so the moment arrives while we watch.
                post(args.port, {"action": "seek", "at": at - 4})
                post(args.port, {"action": "speed", "speed": 1})
                post(args.port, {"action": "play"})
            else:
                post(args.port, {"action": "seek", "at": at})
                post(args.port, {"action": "pause"})
            r = simctl("launch", "--terminate-running-process", args.device, BUNDLE,
                       "-fe.host", f"127.0.0.1:{args.port}", "-stadiumStats", "-stadiumMute", *launch, check=False)
            time.sleep(args.settle)
            shot = args.out / f"{name}.png"
            simctl("io", args.device, "screenshot", str(shot), check=False)
            subprocess.run(["sips", "-Z", "1400", str(shot), "--out", str(args.out / f"s-{name}.png")],
                           capture_output=True)
            logs.append(f"{name}: at {at} -> {shot}")
            print(logs[-1], flush=True)
        (args.out / "shots.txt").write_text("\n".join(logs) + "\n")
    finally:
        api.terminate()
        shutil.rmtree(source, ignore_errors=True)


if __name__ == "__main__":
    main()
