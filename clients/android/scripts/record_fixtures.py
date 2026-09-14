"""Record the scene JSON the Android unit tests read, from the real API.

    python3 clients/android/scripts/record_fixtures.py

Runs tools/scene_samples.py, which replays the repo's committed whole-game
fixtures through fantasyedge.api at fixed instants (kickoff, mid-drive, the
Bears pick-six, overtime, the final whistle) and writes the scene the API
would serve at each. Also writes the replay remote's state for the same
director, so the control payload is tested against the real shape.

No network. Deterministic: run it twice and the bytes match. Never edit the
output by hand; change the API or the sample instants and run this again.
"""

from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUT = HERE.parent / "app" / "src" / "test" / "resources"


def main() -> None:
    scenes = OUT / "scenes"
    if scenes.exists():
        shutil.rmtree(scenes)
    scenes.mkdir(parents=True)
    subprocess.run([sys.executable, str(ROOT / "tools" / "scene_samples.py"), str(scenes)], check=True)
    for path in scenes.glob("*.json"):
        # Re-serialised with sorted keys so a re-run is byte-identical.
        path.write_text(json.dumps(json.loads(path.read_text()), indent=1, sort_keys=True) + "\n")

    sys.path.insert(0, str(ROOT))
    from fantasyedge import api, replay as rp                      # noqa: E402

    fix = ROOT / "tests" / "fixtures"
    source = pathlib.Path(tempfile.mkdtemp())
    for game in sorted(fix.glob("replay_game_*.json")):
        g = json.loads(game.read_text())
        event = game.stem.removeprefix("replay_game_")
        (source / f"{event}.json").write_text(json.dumps(g["summary"]))
        rp.scoreboard_path(source, event).write_text(json.dumps(g["scoreboard"]))
    app = api.Api(db=str(pathlib.Path(tempfile.mkdtemp()) / "r.db"))
    app._replay = rp.ReplayDirector(source)
    state = app.replay_control({"action": "load", "event": "401772810"})
    state = app.replay_control({"action": "seek", "at": 1929})
    state = app.replay_control({"action": "speed", "speed": 60})
    app.close()
    (OUT / "replay_state.json").write_text(json.dumps(state, indent=1, sort_keys=True) + "\n")
    print(f"wrote {len(list(scenes.glob('*.json')))} scenes and replay_state.json to {OUT}")


if __name__ == "__main__":
    main()
