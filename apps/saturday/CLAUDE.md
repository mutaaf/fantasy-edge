# saturday

College football for Apple Vision Pro, iPad and iPhone, with web and Android ports to follow. Read these first:
- `PLAN.md`: scope and phases
- `docs/ARCHITECTURE.md`: layout, monorepo target, integration plan, port matrix
- `docs/design-brief.md`: the look

## Operating procedure

```bash
make test                          # stdlib unittest, no network, under a second
PYTHONPATH=packages:apps/saturday python3 -m api doctor --json   # exit code + next_command
make replay                        # API on the recorded 2026-09-12 slate, port 8780
make serve                         # API on the test fixtures
make build-visionos build-ios build-ipad
```

`doctor` exit codes: 0 ready, 1 generic, 2 config, 3 credentials, 4 no data. A missing `CFBD_API_KEY` is a warning, not a failure.

Screenshots: launch the app with `-openGame <event id>` to open a game directly.

## Layout

```
packages/cfb/        college-only Python (league, parse, leverage, game, colors, sources, store)
apps/saturday/api/   pure handlers + dev server + doctor
apps/saturday/apple/ generated Xcode project; one multiplatform SwiftUI target
contracts/           JSON Schema every client builds to
tests/               fixtures come from tools/make_fixtures.py
```

## Rules

- **Clients hold no logic.** Spotlight, sections, flags, chip colours and completion are decided in Python and shipped in the payload. A client that needs a new fact gets it through a handler and a contract change, never by computing it.
- **Do not duplicate fantasy-edge.** The scene spec, 3D renderers, replay-any-game harness, gamecast shaping, chip normalisation, design tokens and API server belong to fantasy-edge's scene/replay branch. Code marked `INTEGRATE` is a stand-in to be deleted at the merge. Follow the plan in `docs/ARCHITECTURE.md`; don't extend a stand-in.
- **Change a contract before its payload.** Edit `contracts/*.schema.json` and the handler together. `tests/test_api.py` validates the fixture output against the schemas.
- **Stdlib only, Python 3.11+.** No third-party dependencies.
- **Never write credentials into the repo.** `CFBD_API_KEY` and `ESPN_API_KEY` live in the environment.
- **Raw captures in `data/capture/` are ESPN's bytes, gzipped, never edited.** Fixtures come from `tools/make_fixtures.py`. Never edit `tests/fixtures` by hand.
- **Scoreboard requests need `groups=80`.** Without it ESPN serves a curated subset of the FBS slate, with no error.
- **Completion comes from status, never from play text.** A college overtime game has no "End of Game" play: Wake Forest–Purdue (401858224, 2OT) ends on "Rushing Touchdown". A summary header also has no `period`, so the overtime count is read from "Final/2OT".
- **At halftime and in a delay the scoreboard keeps the last down and distance.** `parse.game_record` drops the situation, so no ball is drawn.
- **ESPN lists the drive in progress in both `previous` and `current`.** Dedupe on id.
- **An id is only unique inside its source.** Key on `(source, id)`, because ESPN and CFBD ids collide.
- **Every heuristic carries a non-empty caveat.** The leverage order is hand-weighted; report the caveat with it.
- **Never hand-edit `project.pbxproj`.** Run `make project`.
- **Text is system ink; colour goes on chips.** Every state has a glyph as well as a colour. Targets are ≥60 pt on visionOS and ≥44 pt on iOS.
