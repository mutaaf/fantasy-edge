# Saturday architecture

Saturday is laid out so it moves into the shared monorepo as a plain move, and so every client is a thin renderer of one API.

## The rule: clients hold no logic

All of these are decided on the server, once:
- which game is the spotlight;
- which section a game sits in;
- whether a result is an upset;
- where the ball is;
- what colour a team chip is;
- whether a game is over;
- what changed since the last scoreboard: a score and its kind, points taken off the board, a lead change, a possession flip, a kickoff, a final, an upset, a delay;
- which of those make the whip-around feed;
- where a replay stands, and which frames a scrubber can land on.

A client decodes the payload, lays it out for its screen and draws it. Filtering by flags the server already set ("Top 25", "My teams") is view state and allowed. Computing a new fact about a game is not. If a client needs something, add it to the handler and to `contracts/`, and let every client get it.

## Layout today

```
packages/cfb/            college-football-only Python, stdlib
  league.py              ESPN host, groups=80, RULES (OT from the 25, 2-pt from 3OT, 20-yd hashes)
  parse.py               scoreboard -> game records: status, flags, situation
  leverage.py            wall ordering, sections, spotlight, CAVEAT
  changes.py             frame-to-frame changes and the whip-around feed, CAVEAT
  game.py                summary -> gamecast-shaped detail            (INTEGRATE)
  colors.py              chip normalisation stand-in                  (INTEGRATE)
  sources.py             capture / fixtures / ESPN, Budgeted          (INTEGRATE)
  store.py               CFBD history schema, keyed (source, id)
apps/saturday/api/       handlers.py (pure), server.py (dev, INTEGRATE), doctor.py, __main__.py
apps/saturday/apple/     generate_project.py (INTEGRATE), Saturday/ (SwiftUI: visionOS, iPadOS, iOS)
contracts/               JSON Schema for /api/slate, /api/game/{id}, /api/teams, /api/replay, /api/stream (+ common)
tests/                   stdlib unittest + schema_lite validator; fixtures from tools/make_fixtures.py
tools/                   record_slate.py, make_fixtures.py
design/                  mockup generators (reference for every client's look)
data/capture/            raw ESPN recordings, never edited
```

Run it with `PYTHONPATH=packages:apps/saturday:tests`; the Makefile sets this.

## Live and replay

| Route | What it is |
|---|---|
| `GET /api/slate[?at=<stamp>]` | the wall; `clock` is non-null on a replay, `changes` and `feed` always present |
| `GET /api/game/{id}[?at=<stamp>]` | one game's detail at that moment |
| `GET /api/replay` | the recorded night as frames with marks and a headline each; 404 when live |
| `GET /api/stream?games=<id,id>[&at=<stamp>&speed=<x>]` | server-sent events: `slate`, `game` (open games only), `clock` and `end` on a replay, `budget` or `ping` when live |

- **Replay position is the client's, not the server's.** Every read names its frame with `?at=`, so two people scrubbing one API never fight over a shared cursor, and a frame's response can be cached forever.
- **Summaries are fetched only for open games.** The stream's `games=` is the list of games a client has on screen. `sources.Budgeted` holds ESPN to `league.BUDGET` (one scoreboard per 20 s, one summary per game per 15 s) however many clients watch, and counts every request; `/api/health` reports it and `tests/test_replay.py` holds a whole recorded night to it.
- **The seam a shared source must keep:** `scoreboard()`, `summary(event)`, `stamp()`, `history(seconds)` returning `(stamp, loader)` pairs that always include the previous frame, and on a replay `frames()` and `at(stamp)`. `handlers.stream` is a pure generator of `(event, payload)` pairs, so the shared server only has to write them out.

## Target monorepo

```
packages/
  core/                  from fantasy-edge: api server, cache tiers, ETag/SSE, doctor base, Http
  live/                  from fantasy-edge: LiveSource, replay-any-game harness, gamecast shaping
  scene/                 from fantasy-edge: /api/scene/{event}, league rules table (nfl, college-football)
  tokens/                design/tokens.json + generated Swift/CSS/Kotlin readers
  cfb/                   this repo's packages/cfb, minus the INTEGRATE stand-ins
  fantasy/               fantasy-edge's providers, analytics, intel, scoring
  tooling/               generate_project.py (one generator, per-app settings)
  swift/StadiumKit/      RealityKit Stadium + Tabletop renderers of the scene spec
apps/
  fantasy-edge/          api routes + apple app
  saturday/              api routes + apple app (this repo's apps/saturday)
  web/                   TypeScript clients (one per product, shared renderer package)
  android/               Compose clients (phone + tablet)
contracts/               every product's schemas, including scene.schema.json
```

## Integration plan, for when the fantasy-edge scene/replay branch lands

1. **Move, then test.** Move this repo into `apps/saturday` and `packages/cfb` in the monorepo with history (`git filter-repo` or subtree), then run `make test`. Nothing changes behaviour at this step.
2. **Rules.** `packages/cfb/league.py` RULES becomes the `college-football` entry of the shared rules table in `packages/scene`. Fill in the stub that branch left, using these values (20-yd hashes, OT from the 25, 2-pt only from 3OT). Delete RULES here and keep only the ESPN host details.
3. **Chip colours.** Replace `packages/cfb/colors.py` with the shared normaliser. Keep `pair()` semantics (the away side gives way: its alternate colour, else a hatch) if the shared one lacks them. Otherwise delete the file. The test `Colours.test_identical_golds_resolve_with_a_hatch` must stay green.
4. **Gamecast.** Replace `packages/cfb/game.py` with the shared gamecast shaping. Its field names were mirrored on purpose. Keep only the college additions: rank, `status.overtimes`, completion from status, box score and leaders. Update `contracts/game.schema.json` to `$ref` the shared gamecast schema plus those fields.
5. **Sources.** Replace `packages/cfb/sources.py`: `EspnSource` becomes the shared LiveSource pointed at `college-football` with `groups=80`, and `CaptureSource` becomes the shared replay-any-game harness. Keep the seam in "Live and replay" above, and keep the capture rules that a frozen moment never shows a later result (`Capture.test_capture_never_shows_a_later_result`, `Timeline.test_the_backfill_never_answers_for_a_moment_before_the_recording`). `Budgeted` goes if the shared cache tiers enforce the same budget and count requests; `Budget.test_the_whole_night_stays_inside_the_budget_with_several_clients` must stay green either way.
6. **Server.** Mount `apps/saturday/api/handlers.py` on the shared server as routes, and `handlers.stream` on its SSE transport. Delete `server.py`. Give each route a cache tier: slate and game are LIVE, teams and replay are DERIVED; any response with `?at=` on a capture is immutable.
7. **3D.** Add `/api/scene/{event}` for college games; it comes from the shared scene package with the college rules. In the Apple app, `SharedRendererPlaceholder` routes become StadiumKit's Tabletop volume and Stadium immersive space. Delete the placeholder.
8. **Tokens.** `Tokens.swift` reads the generated reader from `packages/tokens`. Delete the literals.
9. **Tooling.** Both apps call `packages/tooling/generate_project.py` with their own settings. Delete this copy.

After step 9 there should be no `INTEGRATE` markers left: `grep -rn INTEGRATE packages apps` returns nothing.

## Client port matrix

Every client consumes the same contracts. Only the renderer differs.

| Platform | UI | Contracts | 3D renderer (draws `scene.schema.json`) | Notes |
|---|---|---|---|---|
| visionOS | SwiftUI | slate, game, team, scene | RealityKit: Tabletop volume + Stadium ImmersiveSpace (`.progressive`/`.full`) | Ornament filters; ≥60 pt targets; panels within ±46° and ≤33° below eye |
| iPadOS | SwiftUI (same target) | slate, game, team, scene | RealityKit on iOS 18+ (`RealityView`), SceneKit fallback | Two-column wall; ≥44 pt targets |
| iOS | SwiftUI (same target) | slate, game, team, scene | RealityKit / SceneKit, AR tabletop optional | One-column wall, spotlight on top |
| Android phone | Jetpack Compose | slate, game, team, scene | Filament (SceneView) | Same breakpoints as iOS compact |
| Android tablet | Jetpack Compose | slate, game, team, scene | Filament (SceneView) | Same breakpoints as iPad |
| Web | TypeScript (framework-free or React) | slate, game, team, scene | Three.js | Also the reference client for contract changes |

Each port generates its models from `contracts/*.schema.json`. The Swift models in `Models.swift` are hand-written today; generating them is a tooling task at the move. A port is done when it renders the fixture slate identically to the SwiftUI screenshots: same spotlight, same sections, same badges.
