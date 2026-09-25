"""Write replayed scenes to disk for apple/verify_scene.swift.

    python3 tools/scene_samples.py /tmp/scenes

Uses the committed whole-game fixtures, so it needs no network and no
capture: each game is replayed through the real API at a handful of instants
- kickoff, mid-drive, a red-zone snap, the pick-six, overtime, the final
whistle - and the scene the API would serve at that moment is written out.

Both codes are in the set. A Saturday's whip-around moves the bowl between
college games, and whether that repaints or rebuilds is decided by whether
two college scenes share a `StadiumVenue` - so there have to be college
scenes here for anything to check it.
"""

from __future__ import annotations

import json
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fantasyedge import api, replay as rp          # noqa: E402

FIX = ROOT / "tests" / "fixtures"
CFB_FIX = ROOT / "apps" / "saturday" / "tests" / "fixtures"
GAMES = {
    "401772510": [0, 700, 1500, 2400, 3300, 3600],
    "401772949": [900, 2000, 3600, 3900, 4007],
    "401772810": [600, 1800, None, 3600],
}
# College, from Saturday's committed summaries. A summary is one moment - the
# final - which is all the venue check needs: three different college bowls,
# with three different sets of clubs in them.
CFB_GAMES = ["401856682", "401856782", "401858224"]


def write_seat_samples(path: pathlib.Path, scene: dict) -> None:
    """Where scene.py itself puts a handful of seats, so verify_scene.swift can
    check SceneMath.seat against it. Nothing is written for a scene without
    `bowl.seating`."""
    from fantasyedge import scene as sc

    seating = (scene.get("bowl") or {}).get("seating")
    if not seating or not hasattr(sc, "BowlRing"):
        return
    shape = scene["bowl"]["shape"]
    samples = []
    for ti, tier in enumerate(seating["tiers"]):
        rows = tier["rows"]
        for ri in sorted({0, len(rows) // 2, len(rows) - 1}):
            row = rows[ri]
            if not row["runs"]:
                continue
            ring = sc.BowlRing(shape, row["feet"])
            for run in sorted({0, len(row["runs"]) - 1}):
                first, count = row["runs"][run]
                for k in sorted({0, int(count) - 1}):
                    t = ring.angle(first + k * row["pitch"])
                    x, z = sc.bowl_point(shape, row["feet"], t)
                    nx, nz = sc.bowl_inward(shape, row["feet"], t)
                    samples.append({"tier": ti, "row": ri, "run": run, "k": k, "x": x, "y": row["floor"],
                                    "z": z, "nx": nx, "nz": nz})
    path.write_text(json.dumps(samples))


def main() -> None:
    out = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/scenes")
    out.mkdir(parents=True, exist_ok=True)
    source = pathlib.Path(tempfile.mkdtemp())
    for event in GAMES:
        g = json.loads((FIX / f"replay_game_{event}.json").read_text())
        (source / f"{event}.json").write_text(json.dumps(g["summary"]))
        rp.scoreboard_path(source, event).write_text(json.dumps(g["scoreboard"]))
    app = api.Api(db=str(pathlib.Path(tempfile.mkdtemp()) / "s.db"))
    app._replay = rp.ReplayDirector(source)
    written = 0
    for event, instants in GAMES.items():
        app.replay_director().load(event)
        summary = app.replay_director().summary
        for at in instants:
            if at is None:
                # The pick-six itself, so a celebrating scene is in the set.
                lengths = rp.period_lengths(summary)
                play = next(p for p in rp._all_plays(summary)
                            if "INTERCEPTED by N.Wright" in (p.get("text") or ""))
                at = rp.play_seconds(play, lengths)
            app.replay_director().seek(at)
            app.replay_director().set_speed(60)
            scene = app.replay_scene()
            (out / f"{event}-{at}.json").write_text(json.dumps(scene))
            write_seat_samples(out / f"{event}-{at}.seats", scene)
            written += 1
    app.close()
    written += write_college(out)
    print(f"wrote {written} scenes to {out}")


def write_college(out: pathlib.Path) -> int:
    """College scenes, built straight through the shared scene package: there
    is no replay director in the path, because a college summary is already a
    whole game."""
    sys.path.insert(0, str(ROOT / "packages"))
    from cfb.game import game_from_summary
    from fantasyedge import scene as sc

    written = 0
    for event in CFB_GAMES:
        path = CFB_FIX / f"summary_{event}.json"
        if not path.is_file():          # Saturday's fixtures are not required here
            continue
        scene = sc.build(game_from_summary(event, json.loads(path.read_text())))
        (out / f"cfb-{event}.json").write_text(json.dumps(scene))
        write_seat_samples(out / f"cfb-{event}.seats", scene)
        written += 1
    return written


if __name__ == "__main__":
    main()
