# saturday

College football for Apple Vision Pro, iPad and iPhone, with web and Android ports to follow. Read these first:
- `PLAN.md`: scope and phases
- `docs/ARCHITECTURE.md`: layout, monorepo target, integration plan, port matrix
- `docs/design-brief.md`: the look

## Operating procedure

```bash
make test                          # stdlib unittest, no network; replays the whole recorded night in a few seconds
PYTHONPATH=packages:apps/saturday python3 -m api doctor --json   # exit code + next_command
make replay                        # API on the recorded 2026-09-12 slate, port 8780 (/api/replay, /api/stream)
make live                          # API against live ESPN, on the LAN (docs/LIVE_TEST.md)
make record-plan SLATE=2026-09-19  # the recording window, from the real schedule
make record-weekend SLATE=...      # wait for the window, record the weekend, keep the Mac awake
python3 tools/backfill_slate.py both --slate 2026-09-19    # rebuild hours the recorder missed
python3 tools/verify_reconstruction.py --slate 2026-09-19  # hold the rebuild against recorded boards
python3 tools/merge_capture.py --slate 2026-09-19          # one continuous night
make serve                         # API on the test fixtures
make build-visionos build-ios build-ipad
```

`doctor` exit codes: 0 ready, 1 generic, 2 config, 3 credentials, 4 no data. A missing `CFBD_API_KEY` is a warning, not a failure.

Screenshots: launch the app with `-openGame <event id>` to open a game directly, `-replayAt <stamp>` to park the replay on a frame, and `-replayPlay YES -replaySpeed 60` to play it.

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
- **A recording pins the week: `week=N&seasontype=2`.** ESPN answers a date range with 400 and one `dates=` day splits a Friday-Saturday slate over two boards. The week board carries Thursday too, so the recorder's slate is the Saturday and its Friday, by ET kickoff.
- **Before kickoff, ESPN's summary `boxscore` is season averages**, not this game. It ships as `seasonAverages` and `boxscore` is empty until the game starts; drawn as game totals it read 586 yards before kickoff.
- **A live source is shared by every client, so its cache needs a lock.** Three clients against live ESPN doubled the scoreboard budget on 2026-09-15: each thread saw the expired board and fetched its own. `sources.Budgeted` fetches under one lock per resource.
- **Scoreboard requests need `groups=80`.** Without it ESPN serves a curated subset of the FBS slate, with no error.
- **Completion comes from status, never from play text.** A college overtime game has no "End of Game" play: Wake Forest–Purdue (401858224, 2OT) ends on "Rushing Touchdown". A summary header also has no `period`, so the overtime count is read from "Final/2OT".
- **At halftime and in a delay the scoreboard keeps the last down and distance.** `parse.game_record` drops the situation, so no ball is drawn.
- **ESPN lists the drive in progress in both `previous` and `current`.** Dedupe on id.
- **An id is only unique inside its source.** Key on `(source, id)`, because ESPN and CFBD ids collide.
- **A play's `wallclock` turns a summary into a timeline.** Every play carries the instant it happened, so a day nobody recorded can be rebuilt from summaries afterwards (`cfb/reconstruct.py`). Checked against a real recorded board: 35 of 35 games identical.
- **Trust ESPN's play order over its wallclocks.** A few stamps are wrong by hours - a Buffalo-Penn State third-quarter play is stamped two hours after the final - so sorting by them reorders a game around its worst stamp. The order is the sequence; the stamps are made monotone and the disagreeing ones interpolated.
- **A reconstruction is never presented as a recording.** Every rebuilt board carries `saturdayProvenance`, every game carries `provenance` (`recorded` / `reconstructed` / `schedule`), the slate carries `reconstructed` with its caveats, and `reconstruct.CAVEATS` says what cannot be known. The recording wins wherever both cover a moment.
- **A capture's frames are its timestamped scoreboards only.** `20260912-closing-backfill` was fetched the next morning and sorts before every stamp by name; reading it by name put the night's finals on an 8 PM board.
- **Scores go down.** Six touchdowns came off the board on 2026-09-12 (penalties and reviews; Memphis-Boise State went 31, 37, 31, 38). A drop is a `correction` change, never ignored and never an error.
- **A change's `id` is its frame, game, kind and team.** Clients animate an id once; never re-derive whether something changed on a client.
- **Times a person reads are ET, from the server.** Every change carries `time` ("9:14 PM ET") and the replay clock carries `label`; a client that formats `at` in the device's zone shows a Central-time Mac an hour off.
- **History always includes the previous frame**, however old: the recorder's 25-minute gap is still a comparison.
- **ESPN text is cleaned on the server, once, in `cfb/text.py`.** Play, last-play and scoring text lose the clock prefix, formation, jersey numbers, parentheticals and ALL-CAPS tags ("(C. Hawkins KICK)" becomes "C. Hawkins kick"). The contracts forbid `#` and parentheses in those fields, and `tests/test_text.py` runs every string in the capture through it. A client never cleans or trims text.
- **Every team carries `shortName`, chosen on the server.** Clients draw `location` and fall back to `shortName` only when it does not fit (`TeamName`, by width). Never truncate a name when a shorter one was shipped.
- **Every heuristic carries a non-empty caveat.** The leverage order is hand-weighted; report the caveat with it.
- **Never hand-edit `project.pbxproj`.** Run `make project`.
- **Text is system ink; colour goes on chips.** Every state has a glyph as well as a colour. Targets are ≥60 pt on visionOS and ≥44 pt on iOS.
