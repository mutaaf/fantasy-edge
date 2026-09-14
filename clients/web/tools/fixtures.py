"""Stage replay captures for the web client, and record the scenes its tests read.

The web client's tests never talk to a server and never read a hand-written
scene: every JSON file under clients/web/test/fixtures is what the real API
code returned for a real replayed game, recorded here in-process with a fixed
clock so a second run writes the same bytes.

    python3 clients/web/tools/fixtures.py stage clients/web/.replay
    python3 clients/web/tools/fixtures.py record

`stage` writes a capture directory the API's replay director reads, for
`FANTASYEDGE_REPLAY_DIR=clients/web/.replay python3 -m fantasyedge api`.
"""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from fantasyedge import replay as rp  # noqa: E402

FIX = ROOT / "tests" / "fixtures"
OUT = ROOT / "clients" / "web" / "test" / "fixtures"
GAMES = ("401772510", "401772810", "401772949")
PICK_SIX = "401772810"          # MIN at CHI, 2025: a 74-yard interception return


def stage(dest: pathlib.Path) -> pathlib.Path:
    dest.mkdir(parents=True, exist_ok=True)
    for ev in GAMES:
        g = json.loads((FIX / f"replay_game_{ev}.json").read_text())
        (dest / f"{ev}.json").write_text(json.dumps(g["summary"]))
        rp.scoreboard_path(dest, ev).write_text(json.dumps(g["scoreboard"]))
    return dest


class Clock:
    now = 1000.0

    def __call__(self):
        return self.now


def second_of(summary: dict, text: str) -> int:
    lengths = rp.period_lengths(summary)
    p = next(p for p in rp._all_plays(summary) if text in (p.get("text") or ""))
    return rp.play_seconds(p, lengths)


def record() -> list[pathlib.Path]:
    from fantasyedge import api

    tmp = pathlib.Path(tempfile.mkdtemp())
    app = api.Api(db=str(tmp / "web.db"))
    app._replay = rp.ReplayDirector(stage(tmp / "captures"), clock=Clock())
    summary = json.loads((FIX / f"replay_game_{PICK_SIX}.json").read_text())["summary"]
    td = second_of(summary, "INTERCEPTED")
    moments = {
        "kickoff": 0,
        "midgame": td - 240,
        "pick-six": td,
        "final": rp.total_seconds(summary),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    written = []
    for name, at in moments.items():
        app.replay_control({"action": "load", "event": PICK_SIX, "at": at})
        app.replay_control({"action": "speed", "speed": 60})
        scene = app.replay_scene()
        path = OUT / f"scene-{name}.json"
        path.write_text(json.dumps(scene, indent=1, sort_keys=True) + "\n")
        written.append(path)
    state = app.replay_state()
    path = OUT / "replay-state.json"
    path.write_text(json.dumps(state, indent=1, sort_keys=True) + "\n")
    written.append(path)
    return written


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in ("stage", "record"):
        print(__doc__)
        return 2
    if argv[0] == "stage":
        dest = pathlib.Path(argv[1] if len(argv) > 1 else ROOT / "clients" / "web" / ".replay")
        print(stage(dest))
        return 0
    for p in record():
        print(p.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
