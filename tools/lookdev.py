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


def field_goal_second() -> int:
    summary = json.loads((FIX / f"replay_game_{PICK_SIX}.json").read_text())["summary"]
    lengths = rp.period_lengths(summary)
    play = next(p for p in rp._all_plays(summary) if "field goal is GOOD" in (p.get("text") or ""))
    return int(rp.play_seconds(play, lengths))


def wait_for_moment(port: int, kind: str, timeout: float = 20.0) -> float:
    """Poll the replay until the scene's active moment is `kind`; the time it
    appeared, or now if it never does."""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        m = get(port, "/api/replay/scene").get("activeMoment") or {}
        if m.get("kind") == kind:
            return time.monotonic()
        time.sleep(0.1)
    print(f"no {kind} moment within {timeout}s", flush=True)
    return time.monotonic()


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


def app_log(device: str, since: str) -> str:
    return subprocess.run(["xcrun", "simctl", "spawn", device, "log", "show", "--start", since, "--style", "compact",
                           "--predicate", 'subsystem == "com.mutaaf.fantasyedge"'],
                          capture_output=True, text=True).stdout


def wait_for_build(device: str, since: str, tabletop: bool, timeout: float) -> float:
    """Wait until the launched app says its stadium is built (the -stadiumStats
    totals line) and, in the stadium, that the crowd has dressed. A fixed delay
    rendered black worlds under load. Returns the seconds waited."""
    started = time.monotonic()
    built = "[stadium-stats] tabletop: models" if tabletop else "[stadium-stats] stadium: models"
    needs = [built] if tabletop else [built, "crowd dress composed"]
    while time.monotonic() - started < timeout:
        text = app_log(device, since)
        if all(n in text for n in needs):
            return time.monotonic() - started
        time.sleep(2.0)
    print(f"  not built after {timeout:.0f}s; shooting anyway", flush=True)
    return timeout


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", required=True)
    ap.add_argument("--out", required=True, type=pathlib.Path)
    ap.add_argument("--port", type=int, default=8795)
    ap.add_argument("--app", type=pathlib.Path,
                    default=ROOT / ".work/dd/Build/Products/Debug-xrsimulator/FantasyEdge.app")
    ap.add_argument("--only", nargs="*", choices=sorted(SHOTS))
    ap.add_argument("--settle", type=float, default=4.0, help="seconds to let the scene settle once the app says it is built")
    ap.add_argument("--build-timeout", type=float, default=60.0, help="longest wait for the built signal")
    ap.add_argument("--extra", default="", help="launch arguments after -shot, one quoted string: --extra=\"-stadiumPitch -40\"")
    ap.add_argument("--suffix", default="", help="appended to each shot's file name")
    ap.add_argument("--moment", default="touchdown", choices=["touchdown", "fieldGoal"],
                    help="which moment td-moment plays in: the pick-six, or the game's first made field goal")
    ap.add_argument("--times", default="",
                    help="comma-separated seconds after the moment appears, one screenshot each (td-moment-t<s>.png)")
    ap.add_argument("--seat", default="",
                    help="sit in this preset (any id in presentation.stadium.seats) instead of the shot's own seat")
    ap.add_argument("--during-moment", action="store_true",
                    help="play every selected shot through the --moment, not only td-moment")
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
        positions = {"touchdown": field_goal_second() if args.moment == "fieldGoal" else pick_six_second(),
                     "redzone": red_zone_second(args.port)}
        positions["early"] = positions["redzone"] - 150
        if args.seat:
            seats = [x["id"] for x in get(args.port, "/api/replay/scene")["presentation"]["stadium"].get("seats", [])]
            if args.seat not in seats:
                raise SystemExit(f"--seat {args.seat}: the scene's seats are {', '.join(seats)}")
        started = time.strftime("%Y-%m-%d %H:%M:%S")
        for name, where in SHOTS.items():
            if args.only and name not in args.only:
                continue
            if args.during_moment:
                where = "touchdown"
            at = positions[where]
            simctl("terminate", args.device, BUNDLE, check=False)
            # The touchdown is held paused a few seconds before the snap until
            # the stadium has built, then played at 1x: the moment is only an
            # event if it arrives after the build, and it holds for
            # motion.momentSeconds, so the shot is taken inside that window.
            post(args.port, {"action": "seek", "at": at - 3 if where == "touchdown" else at})
            post(args.port, {"action": "pause"})
            launched = time.strftime("%Y-%m-%d %H:%M:%S")
            simctl("launch", "--terminate-running-process", args.device, BUNDLE,
                   "-fe.host", f"127.0.0.1:{args.port}", "-stadiumStats", "-stadiumMute", "-shot", name, *(["-stadiumSeat", args.seat] if args.seat else []), *args.extra.split(), check=False)
            waited = wait_for_build(args.device, launched, name == "tabletop", args.build_timeout)
            time.sleep(args.settle)
            print(f"  {name}: built after {waited:.0f}s", flush=True)
            def shoot(tag: str, due: float = 0.0) -> None:
                if due:
                    time.sleep(max(0.0, due - time.monotonic()))
                shot = args.out / f"{name}{tag}{args.suffix}.png"
                simctl("io", args.device, "screenshot", str(shot), check=False)
                subprocess.run(["sips", "-Z", "1400", str(shot), "--out", str(args.out / f"s-{shot.name}")],
                               capture_output=True)
                logs.append(f"{name}{tag}: replay at {at}s ({where}) -> {shot}")
                print(logs[-1], flush=True)

            if where != "touchdown":
                shoot("")
                continue
            post(args.port, {"action": "speed", "speed": 1})
            post(args.port, {"action": "play"})
            played = time.monotonic()
            if not args.times:
                shoot("", played + 6.0)
                continue
            # "p1.5" is 1.5 s after play resumes (3 s before the snap): frames
            # in flight, before the moment exists. Plain numbers count from the
            # moment appearing in the scene.
            times = args.times.split(",")
            for t in sorted((t for t in times if t.startswith("p")), key=lambda t: float(t[1:])):
                shoot(f"-{t}", played + float(t[1:]))
            late = [t for t in times if not t.startswith("p")]
            if late:
                fired = wait_for_moment(args.port, args.moment)
                for t in late:
                    shoot(f"-t{t}", fired + float(t))
        stats = app_log(args.device, started)
        # Per-actor draw counts, and which path loaded each Shader Graph material.
        lines = sorted({line[line.index(tag):] for line in stats.splitlines()
                        for tag in ("[stadium", "[shadergraph") if tag in line})
        (args.out / "stats.txt").write_text("\n".join(lines) + "\n")
        (args.out / "shots.txt").write_text("\n".join(logs) + "\n")
    finally:
        api.terminate()
        shutil.rmtree(source, ignore_errors=True)


if __name__ == "__main__":
    main()
