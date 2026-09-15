"""Shoot the stadium's fixed look-dev shots in a visionOS simulator.

Serves the committed whole-game fixtures through the real API as a replay,
positions the replay for each shot, launches the app with `-shot <name>` and
saves a screenshot. No network, no capture. The shot names are the ones the
app's `StadiumShots` knows; a test keeps the two lists identical, and
docs/ART_BIBLE.md says which actor each one judges.

    python3 tools/lookdev.py --device <udid> --out .work/shots/iter5
    python3 tools/lookdev.py --device <udid> --out .work/shots/crowd --only crowd-closeup td-moment

Each shot writes `<name>.png` and a 1400-wide `s-<name>.png` for review, and
`stats.txt` gathers the per-actor draw counts the app logs with -stadiumStats.
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

# name -> where the replay sits: "redzone" (a red-zone snap with a drive on
# the field), "early" (a normal snap before it), or "touchdown" (the pick-six,
# played in at 1x so the moment fires while the camera watches).
SHOTS = {
    "tabletop": "redzone",
    "bowl-wide": "early",
    "field-level": "redzone",
    "crowd-closeup": "early",
    "lights-haze": "early",
    "sky-dome": "early",
    "td-moment": "touchdown",
    "redzone-trails": "redzone",
    "sideline-props": "early",
}


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
    summary = json.loads((FIX / f"replay_game_{PICK_SIX}.json").read_text())["summary"]
    lengths = rp.period_lengths(summary)
    play = next(p for p in rp._all_plays(summary) if "INTERCEPTED by N.Wright" in (p.get("text") or ""))
    return int(rp.play_seconds(play, lengths))


def red_zone_second(port: int) -> int:
    for at in range(300, 3600, 45):
        post(port, {"action": "seek", "at": at})
        s = get(port, "/api/replay/scene")
        if s["status"]["redZone"] and s.get("ball") and len(s["lasers"]) == 2 and s["currentDrive"] is not None \
                and len(s["drives"][s["currentDrive"]]["arcs"]) >= 5:
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
    ap.add_argument("--only", nargs="*", choices=sorted(SHOTS))
    ap.add_argument("--settle", type=float, default=9.0)
    ap.add_argument("--extra", default="", help="launch arguments after -shot, one quoted string: --extra=\"-stadiumPitch -40\"")
    ap.add_argument("--suffix", default="", help="appended to each shot's file name")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    source = stage_replays()
    env = {**os.environ, "FANTASYEDGE_REPLAY_DIR": str(source)}
    db = pathlib.Path(tempfile.mkdtemp()) / "lookdev.db"
    api = subprocess.Popen([sys.executable, "-m", "fantasyedge", "--db", str(db), "api", "--host", "127.0.0.1",
                            "--port", str(args.port)], cwd=ROOT, env=env,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    logs = []
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
        positions = {"touchdown": pick_six_second(), "redzone": red_zone_second(args.port)}
        positions["early"] = positions["redzone"] - 150
        started = time.strftime("%Y-%m-%d %H:%M:%S")
        for name, where in SHOTS.items():
            if args.only and name not in args.only:
                continue
            at = positions[where]
            simctl("terminate", args.device, BUNDLE, check=False)
            # The touchdown is held paused a few seconds before the snap until
            # the stadium has built, then played at 1x: the moment is only an
            # event if it arrives after the build, and it holds for
            # motion.momentSeconds, so the shot is taken inside that window.
            post(args.port, {"action": "seek", "at": at - 3 if where == "touchdown" else at})
            post(args.port, {"action": "pause"})
            simctl("launch", "--terminate-running-process", args.device, BUNDLE,
                   "-fe.host", f"127.0.0.1:{args.port}", "-stadiumStats", "-stadiumMute", "-shot", name, *args.extra.split(), check=False)
            time.sleep(args.settle)
            if where == "touchdown":
                post(args.port, {"action": "speed", "speed": 1})
                post(args.port, {"action": "play"})
                time.sleep(6.0)
            shot = args.out / f"{name}{args.suffix}.png"
            simctl("io", args.device, "screenshot", str(shot), check=False)
            subprocess.run(["sips", "-Z", "1400", str(shot), "--out", str(args.out / f"s-{name}{args.suffix}.png")],
                           capture_output=True)
            logs.append(f"{name}: replay at {at}s ({where}) -> {shot}")
            print(logs[-1], flush=True)
        stats = subprocess.run(["xcrun", "simctl", "spawn", args.device, "log", "show", "--start", started,
                                "--style", "compact", "--predicate", 'subsystem == "com.mutaaf.fantasyedge"'],
                               capture_output=True, text=True).stdout
        lines = sorted({line[line.index("[stadium"):] for line in stats.splitlines() if "[stadium" in line})
        (args.out / "stats.txt").write_text("\n".join(lines) + "\n")
        (args.out / "shots.txt").write_text("\n".join(logs) + "\n")
    finally:
        api.terminate()
        shutil.rmtree(source, ignore_errors=True)


if __name__ == "__main__":
    main()
