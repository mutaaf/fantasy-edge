# integration-11: the load checkpoint

`immersive/quality` at `c071896` with three merges on top of integration-10:

- **`perf/integration-11` @ `a44822a`:**
  - assets load concurrently
  - beams are single quads facing the seat, under an overdraw cap of 1.2
  - the bowl's idle fills draw as one mesh
- **`actor/crowd` @ `5500b59`:**
  - MakeHuman fans
  - the crowd dresses in about 2 s instead of 25 s
- **`polish/integration-11` @ `fc990c8`:**
  - a smooth border
  - trails that stay low once played
  - a video board that leads with the score
  - panels kept off the board

Shot with `.work/shoot11.sh`, which uses the same recipe as integration-10 plus lights-haze, sky-dome, redzone-trails and sideline-props. `stats.txt` holds every `-stadiumStats` and `-stadiumTiming` line from the run.

## Gates

| Gate | Result |
|---|---|
| `make test` | 548 tests OK |
| `verify_scene` (swiftc per its header) | 15 scenes, 1,422 arcs, 59,515 assertions OK |
| `contrast_check` | OK |
| `xcodebuild` (visionOS simulator) | BUILD SUCCEEDED. The only warning is the existing AppIntents metadata notice, plus stale-file notices from a derived-data folder first built under the old clone path |

## What the merge broke, and the fix

- **The field seat drew no field paint on the first pass.**
  - **Symptom:** the border, hashes and team-area line were all missing, with none of the Shader Graph lines logged.
  - **Cause:** the harness waited only for `crowd dress composed`. At 25 s that wait had hidden every slower load behind it. At 2 s, a shot under load can beat the field's Shader Graph paint, which draws nothing until it swaps in. One load in this run took 10.4 s.
  - **Fix:** `tools/lookdev.py` now also waits for `[shadergraph] field paint on` or its fallback. The field seat was re-shot with the fix and its paint is back.
  - **On device:** the same race means paint can pop in late on a slow first open. That belongs to Field, and needs checking on device.
- **The first tabletop shot showed "No board yet".** The first launch after a cold simulator boot didn't reach the API. A retake with nothing changed is correct, so this is not a regression. The harness should warm the app once before its first shot.

No other shot is worse than integration-10.

## Budget, measured against the art bible

Figures come from the club seat unless a range is given. Ranges cover every seat and moment in this run.

| Actor | Triangles | Target | Draw parts | Target | Notes |
|---|---:|---:|---:|---:|---|
| Field | 1.1k | 2k | 10 | 12 | |
| Sideline | 20.6–20.9k | 21k | 15 | 15 | 1 shadow caster (decal, intended) |
| Bowl | 47.3–59.7k | 62k | 9–16 | 20 | 16 was 20 before the perf merge; 9 in the press box |
| Crowd | 144.3–144.4k | 150k | 36 | 45 | 44,892 fans: 16 LOD0, 32 LOD1, 150 LOD2, 44,694 cards; 0 casters |
| Lighting | 9.5k | 10k | 12 | 20 | 4 spot lights; beam overdraw 0.00–0.97 against a cap of 1.2 |
| Sky | 4.8k | 5k | 3 | 3 | |
| Broadcast | 4.4k idle, 6.8k peak in the kick | 30k | 5 idle, 27 peak in the kick | 25 | **27 at fieldGoal+0.5 s is 2 over its line**, the same as integration-10; 0 casters |
| Moments | 0 | 2k | 0 | 10 | ≤ 4 emitters at touchdown+3 s |
| Experience | 0 | 5k | 0 | 10 | |
| **Stadium** | **232–240k idle, 242k peak** | **287k** | **90–97 idle, 118 peak** | **160** | ~67 MB textures (target 300) |
| **Tabletop** | **24.2k** | **80k** | **72** | **110** | |

- **Crowd dress:** 1.5–7.3 s, down from 24.8–26.0 s. The top of the range is under simulator load.
- **Stadium first tick after open:** 5.1–9.2 s. Simulator timings are not frame time, so these need verifying on device.

## Rubric, 1–5

Order: read · light · material · scale · life · clarity · comfort · cost.

| Actor | Scores | Change against integration-10 |
|---|---|---|
| Field | 4 · 4 · 3 · 4 · – · 4 · 5 · 5 | material holds: the border is smooth, but flat grey from the field seat |
| Sideline | 4 · 3 · 3 · 4 · 3 · 4 · 4 · 5 | the net still grids the view from behind the posts |
| Bowl | 4 · 3 · 3 · 4 · – · 4 · 5 · 5 | cost improves: 16 parts |
| Crowd | 4 · 3 · 3 · 4 · 4 · 4 · 5 · 4 | read, scale and life all +1: people rather than mannequins |
| Lighting | 4 · 4 · 4 · 4 · 3 · 4 · 4 · 5 | cost improves: overdraw 0.97 at worst |
| Sky | 4 · 4 · 4 · 4 · 3 · 5 · 5 · 5 | unchanged |
| Broadcast | 4 · 4 · 4 · 4 · 4 · 4 · 5 · 4 | clarity +1: the board and trails; cost is 2 parts over in the kick |
| Moments | 4 · 4 · 4 · 4 · 4 · 4 · 4 · 5 | unchanged |
| Experience | 3 · – · – · 4 · – · 3 · 3 · 5 | panels are off the board, but pills still land on seats and grass |

## Worst thing left, per shot

- **`s-bowl-wide.png`:** the near-right fan's shirt shows square bake patches, and the near-left fan is visibly low-poly next to the MakeHuman rows.
- **`s-field-level.png`:** the border is clean, but it's a flat mid-grey slab with no light from the stands behind.
- **`s-crowd-closeup.png`:** the top edge crops the taller score-led board, so the clock is cut off.
- **`s-crowd-closeup-upper.png`:** the nearest fan sits high on the seat pan with their shoes off the tread, and the Elsewhere pill overlaps a light bank.
- **`s-crowd-closeup-clubLevel.png`:** the props in raised hands read as flat grey-brown boards.
- **`s-crowd-closeup-field.png`:** the Elsewhere pill lies on the grass at the wearer's feet.
- **`s-crowd-closeup-sideline.png`:** the Elsewhere pill sits on a chair seat in the row in front.
- **`s-crowd-closeup-endzone.png`:** the goal net grids the upper-left view, and the nearest fan on the right sits high with their legs hanging.
- **`s-crowd-closeup-pressBox.png`:** the Elsewhere pill sits on top of the rim between two light banks.
- **`s-td-moment-t0.5.png`:** the ribbon's TOUCHDOWN flash still clips ("TOUCHD TOUCHDOWN"), as "TC" did in integration-10, and the scorebug and video board both sit in frame.
- **`s-td-moment-t5.1.png`:** raised foam fingers are cartoon-sized next to the new hands.
- **`s-td-moment-t8.5.png`:** the far celebrating rows at the frame edge are still low-poly LOD2.
- **`s-td-moment-p6.5-fg-club.png`:** the drive panel sits across the ribbon and hides the score crawl behind its glass.
- **`s-td-moment-p6.5-fg-sideline.png`:** the drive panel covers the ribbon over the far stands, and the ball in flight is a thin, hard-to-find spike.
- **`s-redzone-trails.png`:** the ribbon clips "RED ZONE" to "REDNE" at the right, and Controls lies at the wearer's feet.
- **`s-sideline-props.png`:** the net's 0.35 floor grids the entire view, and the haze at top left is heavy.
- **`s-lights-haze.png`:** the drive panel is cut off at the left edge over the ribbon.
- **`s-sky-dome.png`:** the clouds low on the left read as smudges, not cloud.
- **`s-tabletop.png`:** the ribbon and board are unreadable at table scale. This is expected, but nothing replaces them there.
