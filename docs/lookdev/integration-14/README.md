# integration-14 — the honest-timing checkpoint

What landed since integration-13: the status gate, so the drawn score, ribbon,
board score and red-zone flag wait for the ball (`director/score-timing`); the
video board narrating the newest *laid* play and the win-probability horizon
holding with it (`actor/broadcast-r6`); the drive log listing only landed plays
(`director/drive-log`); a visiting support with a ragged edge, staggered
brightening and empty seats in blocks (`actor/crowd-r6`); a goal net rewoven to
a 4-inch mesh and a press box whose furniture is furniture (`actor/sideline-r5`);
and panels that never touch the painted field, held whole by a view window
(`actor/experience-r5`).

Shot on the visionOS 26.5 simulator, clone `fe-i14`, own derived data
(`.work/dd-i14`), with the harness given `--app` so it could not install a stale
bundle. 41 review frames here; full-size originals in
`.work/shots/integration-14/`.

**The machine was not quiet when this run began.** Four simulators from earlier
agents were still booted and the load average was 224. They were shut down
first, and the timings below were taken after that. This matters: integration-13
read the crowd dress at 1.7–2.96 s and `actor/crowd-r6` read it at 6.9–8.7 s
under a load average above 340, which looked like a regression and was not.

## Gates

| Gate | Result |
|---|---|
| `make test` | 678 OK |
| `make verify-scene` | 15 scenes, 1,422 arcs, 495,078 assertions OK |
| `make verify-moment` | 284 checks OK |
| `make verify-crowd` | 346,120 checks OK |
| `contrast_check` | OK |
| `xcodebuild` | BUILD SUCCEEDED; one warning, the pre-existing AppIntents notice |

`generic/platform=visionOS Simulator` is the destination that builds; the shot
harness installs to a clone by id.

## Budget, measured with `-stadiumStats`

| Actor | Triangles | Parts | Target | |
|---|---:|---:|---|---|
| Field | 693 | 10 | 2k / 12 | |
| Sideline | 20,776 | 15 | 21k / 15 | at its ceiling, as it has been since integration-11 |
| Bowl | 53,732–55,044 | 18 | 62k / 20 | ↑ from 9–16: the press box's two new materials, two parts of headroom left |
| Crowd | 133,497 | 36 | 150k / 45 | ↓ from 135,626–136,338 |
| Lighting | 9,508 | 12 | 10k / 20 | 4 spots; beam overdraw 0.46–0.63 of a 1.2 cap |
| Sky | 4,800 | 3 | 5k / 3 | |
| Broadcast | 4,422 idle, 7,596 mid-kick | 6 idle, 22 mid-kick | 30k / 25 | back inside 25, from 27 at integration-12 |
| Moments | 0 | 0 | 2k / 10 | |
| Experience | 0 | 0 | 5k / 10 | attachments excluded |
| **Stadium** | **219,731–228,381**, 231,387 peak | **93–100**, 115 peak | 287k / 160 | ~67 MB textures |
| **Tabletop** | 23,778–23,855 | 67 | 80k / 110 | |

Crowd: 30,651 of 49,982 seats taken (61%), home 91% / visiting 4% / neutral 3%.
The kit logs `lod0/lod1/lod2 faces +Z`, measured off the probe triangle that
`actor/crowd-r5` added, so the backwards-fan bug cannot return unnoticed.

## Load, on the quiet machine

| | integration-13 | here |
|---|---|---|
| Assets ready after open | 3.0–3.4 s | **2.03–3.14 s** |
| First tick after open | 5.8–7.4 s | **5.93–6.72 s** |
| Crowd dress | 1.7–2.96 s | **2.39–3.67 s**, 2.4 s in the quietest runs |

So `actor/crowd-r6` cost roughly half a second of dress time for its third
(neutral) dress, which is what that actor predicted — not the four to six
seconds a loaded machine suggested. Tint is nearly all of it.

The simulator cannot measure frame time. Frame budget is still unverified on
device.

## Rubric, 1–5

| Actor | Read | Light | Material | Scale | Life | Clarity | Comfort | Cost |
|---|---|---|---|---|---|---|---|---|
| Field | 5 | 4 | 4 | 5 | – | 5 | – | 5 |
| Sideline | 4 | 4 | 4 | 4 | 3 | 4 | – | 5 |
| Bowl | 4 | 4 | 4 | 5 | – | 4 | – | 4 |
| Crowd | 4 | 4 | 4 | 4 | 4 | 4 | 5 | 5 |
| Lighting | 4 | 4 | 4 | 4 | 3 | 4 | 5 | 5 |
| Sky | 4 | 4 | 4 | – | 3 | 5 | 5 | 5 |
| Broadcast | 4 | 4 | 4 | 4 | 4 | 4 | 5 | 4 |
| Moments | 4 | 4 | – | – | 4 | 3 | 5 | 5 |
| Audio | – | – | – | – | – | – | – | – |
| Experience | 4 | – | – | 4 | 4 | 4 | 4 | 5 |

Sideline's Clarity rises from 3: the net no longer curtains the field.
Bowl's Cost falls from 5: the press box spent two draw parts.
Moments' Clarity is 3 for the field-goal score lag below.

## Worst thing left, per shot

- `bowl-wide` — the visiting support reads as people in patches rather than a
  painted wedge, and the home identity is unambiguous. Nothing to fault beyond
  the far crowd's flatness at this distance.
- `field-level` — the ribbon double-draws when seen along its length: two
  crawls overlap and neither reads. Unchanged since integration-13.
- `sideline-props` — the net is a veil now, not a curtain, but its grid still
  crosses the whole view; a 12 × 9 m net a few metres away does that in life,
  and at review resolution its cords can only mip to a wash. Judge on device.
- `crowd-closeup` (club) — fans face the field, sit in their chairs and vary.
  Hair still reads as cards at 2–3 m.
- `-clubLevel`, `-upper`, `-endzone`, `-sideline` — feet are on the treads at
  every seat; the shoes-over-the-edge fault is gone.
- `-field` — turf reads as grass with blades and a stripe; the surround is
  clean. No fault found.
- `-pressBox` — the room reads as a room: dark chairs, monitors, a lit ceiling.
  A large flat beige mass still fills the lower middle. See below.
- `td-moment` — the whole rule in one frame: ball in flight, score still 10,
  board narrating the *previous* play, win probability 58%, no celebration.
- `td-moment-t5.1` / `-t8.5` — the celebration begins when the ball lands and
  the banner is gone by 8.5 s. Both integration-13 defects are fixed.
- `td-moment-t0.5-fg-club` / `-t4-fg-club` / `fg-late/-t6` — the field-goal lag
  below.
- `bowl-wide-p*-run` / `-short` / `-deep` / `-kickoff` — runs hug the grass,
  passes arc by distance, the kickoff draws its arc and return. The ball holds
  its light at upper-deck distance.
- `bowl-wide-phi` / `field-level-phi` — EAGLES and PHILADELPHIA in Eagles teal,
  Dallas nowhere on the grass: the home rule is a rule. The two supports are
  still hard to tell apart at distance.
- `lastweek-picker` — 16 games, a reason each, no scores, Scores off, and the
  header reads `2026 · Week 1`.
- `crowd-closeup-skip-stands` — the bisect frame, not a look-dev shot.

## The beige mass at the press-box seat, identified as far as skipping can

`actor/sideline-r5` reported a large flat beige mass in the middle of that
seat's view that never moved when the room's floor, chairs or dado changed, and
guessed it was bowl structure outside the glass. Bisected here with `-bowlSkip`:

| Skipped | The mass |
|---|---|
| `near` | still there |
| `fills` | still there |
| `stands` | **gone** — and the whole press-box enclosure with it |

So it is inside the `stands` mesh, which is where the press box is built. It is
not the room's furniture: `press_desk` is a dark brown (0.23, 0.15, 0.09),
`press_chair` near black, `press_floor` darker still, and the dado was moved off
desk-beige in `actor/sideline-r5` for exactly this reason. The beige-capable
materials left in that section of `tools/blender/bowl/structure.py` (the press
box, about lines 590–620) are `concrete` (the floor-slab edge and sill at the
front) and `trim` (the soffit under the slab, and the roof). Settling which
needs a material-level skip — `-bowlSkip` is per piece, not per material — and
that is one small debug flag away.

## Top 5 worst things left

1. **Broadcast / Moments — a made field goal is announced before it is
   scored.** `td-moment-t4-fg-club` has the board reading "W.Reichard 31 yard
   field goal is GOOD" over MIN 0 and a situation still on 4TH & 8;
   `fg-late/td-moment-t6-fg-club` has MIN 3 and the ribbon flashing FIELD GOAL.
   About two seconds where the kick is good and the score is not. The board
   follows the newest laid play, the score follows the status of the scene that
   play arrived in, and that scene carries the pre-kick score — the points come
   with the next scene. This is the queued-scene limitation `director/score-timing`
   recorded, and it is more visible on a kick than a touchdown because the kick's
   own scene never carries its points.
2. **Experience — a turned head still takes a panel out of frame.** In
   `redzone-trails` the drive log is absent rather than clipped, which is better
   and still not in view. No placement fixes it while the dock is anchored to the
   seat; the two real answers are a recentre affordance on the pill or a dock
   that follows the play by a few degrees. Director's call.
3. **Bowl — the beige mass at the press-box seat**, narrowed above to the
   `stands` mesh and to `concrete` or `trim` in the press-box build.
4. **Crowd — two clubs whose colours are close read as one crowd at distance.**
   `bowl-wide-phi`: Eagles teal against Dallas navy. The crowd separates them by
   where they sit, not by colour, and cannot honestly do more; pairwise chip
   separation belongs to the palette. Hair also still reads as cards at 2–3 m.
5. **Sideline / Field — the ribbon double-draws along its length** at field
   level, and the net's grid still crosses `sideline-props`. Both are
   resolution-bound in a still frame and want a device before more is spent.
