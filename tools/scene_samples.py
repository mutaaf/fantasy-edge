"""Write replayed scenes to disk for apple/verify_scene.swift.

    python3 tools/scene_samples.py /tmp/scenes

Uses the committed whole-game fixtures, so it needs no network and no
capture: each game is replayed through the real API at a handful of instants
- kickoff, mid-drive, a red-zone snap, the pick-six, overtime, the final
whistle - and the scene the API would serve at that moment is written out.
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
GAMES = {
    "401772510": [0, 700, 1500, 2400, 3300, 3600],
    "401772949": [900, 2000, 3600, 3900, 4007],
    "401772810": [600, 1800, None, 3600],
}


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
            (out / f"{event}-{at}.json").write_text(json.dumps(app.replay_scene()))
            written += 1
    app.close()
    print(f"wrote {written} scenes to {out}")


if __name__ == "__main__":
    main()
