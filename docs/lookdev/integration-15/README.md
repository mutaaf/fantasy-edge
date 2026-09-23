# integration-15 — the refinement checkpoint

Every one of the ten actors was refined between integration-14 and here, so
this checkpoint is mostly about *interactions*: each actor was judged good by
its own owner, in its own frames, against the build it started from. What
follows is what they look like together.

Shot on the visionOS 26.5 simulator (clone `fe-i15`), own derived data
(`.work/dd-i15`), the harness given `--app` so it could not install a stale
bundle. 35 review frames here; full-size originals in
`.work/shots/integration-15/`.

**The machine was genuinely quiet for the first time this session.** One stray
simulator was shut down before measuring; the 1-minute load average was 4.1 at
the start of the run and no other agent was working. Every earlier timing in
this repository was taken with parallel work in flight, which is why the
ranges below are so much tighter than integration-14's rather than faster.

## Gates

| Gate | Result |
|---|---|
| `make test` | 803 OK |
| `make verify-scene` | 15 scenes, 1,422 arcs, 495,082 assertions OK |
| `make verify-moment` | 284 checks OK |
| `make verify-crowd` | 346,120 checks OK |
| `contrast_check` | OK |
| `xcodebuild` | BUILD SUCCEEDED; one warning, the pre-existing AppIntents notice |

`generic/platform=visionOS Simulator` is the destination that builds; the shot
harness installs to a clone by id. A first attempt cloned the *visionOS 1.2*
device and the install failed with "Requires a Newer Version of visionOS" —
clone a 26.5 device, and note that `xcrun simctl install` can fail while a
shell `&&` chain still prints success.

## Load, on the quiet machine

| | integration-14 | here |
|---|---|---|
| Crowd dress | 2.39–3.67 s | **1.59–2.42 s** |
| Assets ready after open | 2.03–3.14 s | **2.03–2.47 s** |
| Stadium first tick after open | 5.93–6.72 s | **5.95–6.41 s** |
| All actors' build | — | 3.41–3.57 s |

First tick is unchanged; what changed is the spread. The crowd dress gain is
partly crowd-r8's work and partly the quiet machine, and those two cannot be
separated from this run alone.

## Budget, measured with `-stadiumStats`

`[stadium-stats]` lines persist in the simulator log across launches, and the
harness writes every launch of a run into one file. The ranges below are across
the nine launches of the main run, parsed per line, not read off the tail.

| Actor | Triangles | Parts | Target | |
|---|---:|---:|---|---|
| Field | 693 | 10 | 2k / 12 | |
| Sideline | 14,844–15,132 | 15 | 21k / 15 | **↓ from 20,776**: the LOD1 tier nothing was drawing |
| Bowl | 48,256–55,974 | 12–19 | 62k / 20 | 19 at the club seat, after the soffit material |
| Crowd | 140,110–140,151 | 36 | 150k / 45 | ↑ from 133,497: solid hair and the mesh circle |
| Lighting | 9,500–9,508 | 12 | 10k / 20 | |
| Sky | 4,800 | 3 | 5k / 3 | at its ceiling |
| Broadcast | 4,422 idle | 6 idle | 30k / 25 | 18 parts mid-kick, measured in r8 |
| Moments | 0 | 0 | 2k / 10 | idle |
| Audio | – | – | 40 MB | 4.3 MB measured, 16 sounds |
| Experience | 0 | 0 | 5k / 10 | attachments excluded |
| **Stadium** | **222,674–230,661** | **94–101** | 287k / 160 | ~67 MB textures |
| **Tabletop** | 23,760–23,800 | 67 | 80k / 110 | |

Every actor is inside its ceiling, and for the first time so is college: the
Sideline round found it had been 648 triangles **over** at 21,648, undetected
because every measurement ever taken here had been an NFL one.

## The rubric, per actor

Scored on this checkpoint's frames. 1–5, the art bible's eight lines.

| Actor | Read | Light | Material | Scale | Life | Clarity | Comfort | Cost |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| Field | 4 | 4 | 3 | 5 | 3 | 5 | 5 | 5 |
| Sideline | 4 | 4 | 4 | **5** | 4 | 4 | 5 | 5 |
| Bowl | 4 | 3 | 4 | 5 | 4 | 4 | 5 | 4 |
| Crowd | 4 | 4 | 3 | 4 | 4 | 4 | 5 | 4 |
| Lighting | 4 | **5** | 4 | 5 | 4 | 5 | 5 | 5 |
| Sky | 4 | 5 | 4 | 5 | 3 | 5 | 5 | 5 |
| Broadcast | 5 | 4 | 4 | **5** | 5 | 5 | 5 | 5 |
| Moments | 5 | 5 | 4 | 5 | 5 | 5 | 5 | 5 |
| Audio | – | – | – | – | – | – | – | 5 |
| Experience | 4 | 4 | 4 | 4 | 4 | 4 | 4 | 5 |

Field's Material is a 3 only because of the blades, below. Audio cannot be
scored from a frame, and every shot run is launched with `-stadiumMute`, which
is why nobody has heard it; its rules are now checked from the trace instead.

## Worst thing left, per shot

- `s-bowl-wide.png` — the two end zones read as different colours: the near one
  navy, the far one washed grey-blue. That is the haze over a sightline
  crossing the whole bowl, the same wash the goal net was blamed for.
- `s-bowl-wide-phi.png` — **the club wears two colours**: midnight green on the
  grass, bright teal in the stands. See the interactions below.
- `s-crowd-closeup.png` — flat cards still read through at the club seat: the
  grass and the yellow line show through the figures in the row below. Compare
  `club-seat-cards-i15.png` with `club-seat-cards-i14.png`; it is not a
  regression, but crowd-r8's fix does not reach this seat.
- `s-crowd-closeup-*.png` (sideline, endzone) — solid, as crowd-r8 verified.
- `s-field-level.png` — the grass is a flat olive tint with grain; no blade
  reads as a blade. Field named this and left it for a turf-authoring round.
- `s-td-moment-t5.1.png` — the moment is still held; the crowd is up for third
  down, which is the crowd's own reaction rule, not an early celebration.
- `s-td-moment-t8.5.png` — score, ribbon, fireworks and win probability all
  land together, and the banner is already down because the next play snapped.
- `s-td-moment-p5.0-fg-endzone.png` — the net's grid crosses the whole frame
  from behind the posts. Geometrically right; still the least legible seat.
- `s-tabletop.png` — the plinth is stone now and the field is the brightest
  thing on the table; the win-probability streak floats behind the model,
  which Experience flagged as Broadcast's call.
- `s-sideline-props.png` — the base pads read as pads; a gold strip still
  crosses the near pad, which Sideline named and could not finish.

## Interactions judged

Nine of the ten actors changed, so these are what only a checkpoint can see.

1. **A club now wears two different colours.** Field moved the paint to the
   colour a club *states*; the crowd still dresses from the chip, which is
   solved onto a luminance band. For Philadelphia that is `#004C54` on the
   grass against `#0B7B86` in the stands; Chicago `#0B162A` against `#366CCD`;
   Las Vegas `#000000` against `#6F6F6F`. In the Philadelphia frame the
   difference is plain. This is not a bug in either actor — the crowd's lift
   exists because dark clubs made the far stands read as a black mass — but
   one club reading as two colours in one frame is a question only the
   director can settle.
2. **The darker night against the new paint.** They compound: a two-stop
   darker sky plus a club's true dark colour makes the end zones read as
   near-black slabs at bowl-wide distance. The lettering still clears its
   contrast floor and the grass is clearly the brightest thing, so this is
   within the bible — but it is the largest visual change since
   integration-14 and worth a human eye.
3. **The smaller ball against its glow.** Broadcast took the ball from 2.6×
   life size to life size within 14 yd. At bowl-wide distance it is now found
   entirely by its light, which is what r5 built. It works; there is no frame
   of it inside 10 yd because no seat stands that close.
4. **Solid hair and the mesh circle** hold together at the sideline and
   end-zone seats; the club seat is where cards still intrude (above).
5. **The corrected uprights** change nothing about clearance, as r8 measured:
   good kicks cross well above the crossbar and the wide misses stay outside.
6. **The lit soffits** read as concrete rather than void in `bowl-wide`, and
   they do not lift the dark band under the ribbon, which is occlusion.

## Two shot-list gaps, recorded not closed

Both need a new entry in `presentation.stadium.seats`, which is a contract
change and the director's, so this checkpoint records rather than adds them:

- **No seat stands within 10 yd of the ball** (nearest is ~25 yd), so
  Broadcast's life-size claim is honest in the formula and unproven in a frame.
  A seat on the bench at the near hash, looking down the line of scrimmage,
  would settle it.
- **The wall LED boards are at a grazing angle in every preset**, so the bar's
  "subtle pixel grid up close" has never been testable. A seat behind the home
  bench facing the wall square-on would settle it.

## Top 5 worst things left, across the stadium

1. **Crowd — flat cards read through at the club seat.** The defect the user
   reported is fixed at the sideline seat and not at this one; the evidence is
   the two crops here. The structural fix crowd-r8 named is a cheaper fourth
   detail tier, which roughly doubles the mesh radius for the same budget.
2. **Field — no blade reads as a blade at field level.** Five of six grass
   criteria pass; this one needs a turf-authoring round, not a tuning pass.
3. **Director — a club wears two colours.** Paint states the truth, the crowd
   states the chip. Whoever owns club identity has to choose.
4. **Lighting — the haze wash across a long sightline**, which makes the far
   end zone a different colour from the near one and was blamed on the goal
   net for three checkpoints. Now correctly routed.
5. **Bowl — the band under the ribbon at 1.40 stops and the vomitory mouths at
   3.08** read as a dark band and as holes cut in the crowd. Bowl measured
   these as occlusion, wanting concourse spill from Lighting.

Everything above is a simulator frame. Frame time, the press box dock at ×0.47
inside the glass, and whether any of this reads at true scale still need the
device.
