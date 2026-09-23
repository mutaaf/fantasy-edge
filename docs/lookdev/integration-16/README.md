# integration-16 — the one-club checkpoint

integration-15 shot the refinement round and found that **a club wore two
different colours**: Field had moved the paint to the colour a club states,
while the crowd still dressed from `chip()`, which solves every club onto one
luminance band so white text reads on it *in a panel*. Philadelphia was
`#06424D` on the grass and `#0B798E` in the stands; Las Vegas `#000000` against
`#6F6F6F`.

`actor/crowd-r9` answered it: cloth is the club's own stated colour, moved in
HSV **value alone** — never hue, never saturation — with a floor of 0.26. This
checkpoint exists to judge that in a frame, together with everything else.

Shot on the visionOS 26.5 simulator (clone `fe-i16`), own derived data
(`.work/dd-i16`), the harness given `--app` so it could not install a stale
bundle. The simulator log was erased before the main run, because
`[stadium-stats]` lines persist across launches. 30 review frames here, plus
two full-resolution crops; originals in `.work/shots/integration-16/`.

## The verdict, in one frame

**Yes — paint and stands now read as the same club, and they remain different
materials.** `s-bowl-wide-phi.png` is the frame that answers it: midnight-green
end zones under a midnight-green crowd, where integration-15 had green paint
under a teal crowd. `s-bowl-wide.png` (Chicago navy) and
`s-bowl-wide-college.png` (Toledo navy) hold the same way.

**The cost is real and belongs in the record.** A dark club is now dark
everywhere. At the club seat (`s-crowd-closeup.png`) Chicago's navy reads as
black shirts; the club is carried by context rather than colour. In the
Philadelphia close-up the midnight green is just distinguishable from black at
two metres. That is what those clubs *are* at night, and crowd-r9 declined to
lift them further on exactly that ground — but it is the visible change since
integration-15, and the two crops below are the cleanest way to see it.

`club-near-i15.png` and `club-near-i16.png` are the same 1300×620 pixels of the
same seat, one commit apart: bright blue shirts against near-black ones.

**Las Vegas and Pittsburgh are still unshot.** No committed fixture has a
`#000000` club at home, and crowd-r9 deliberately deleted the throwaway it
built for its own sweep rather than leave a fake game in `tests/fixtures`. The
darkest clubs that can be *looked at* here are Chicago `#0B1C3A` and Toledo
`#0B2240`, both below the 0.26 floor and therefore lifted; Philadelphia
`#06424D` sits above it and is worn untouched. The black case remains covered
by tests and arithmetic alone.

## Gates

| Gate | Result |
|---|---|
| `make test` | 806 OK |
| `make verify-scene` | 15 scenes, 1,422 arcs, 495,232 assertions OK |
| `make verify-moment` | 284 checks OK |
| `make verify-crowd` | 346,120 checks OK |
| `contrast_check` | OK |
| `xcodebuild` | BUILD SUCCEEDED; one warning, the pre-existing AppIntents notice |

## Load, and the timings

The 1-minute load average was **2.88 at the start of the session and 9.87 when
the main run began** (the build is what raised it); no other agent was working.
integration-15's were taken at 4.1.

| | integration-15 | here (main run) | here (all 18 launches) |
|---|---|---|---|
| Crowd dress | 1.59–2.42 s | 1.93–2.60 s | 1.63–2.62 s |
| Assets ready after open | 2.03–2.47 s | 1.67–2.71 s | 1.67–2.71 s |
| Stadium first tick after open | 5.95–6.41 s | 5.57–6.70 s | 5.57–6.70 s |

Unchanged within the spread, which is what a colour change should cost. One
detail worth keeping: the dress splits into two profiles across launches —
either `tint 1.5 s + main-actor wait 0.8 s` or `tint 2.4 s + wait 0.0 s`. The
work is the same; what varies is whether the tint waits on the main actor or
overlaps it.

## Budget, measured with `-stadiumStats`

Parsed per launch from the main run's log, not read off the tail.

| Actor | Triangles | Parts | Target | |
|---|---:|---:|---|---|
| Field | 693 | 10 | 2k / 12 | |
| Sideline | 14,844–15,132 | 15 | 21k / 15 | |
| Bowl | 48,256–55,974 | 12–19 | 62k / 20 | 19 at the club seat |
| Crowd | 140,110–140,151 | 36 | 150k / 45 | |
| Lighting | 9,500–9,508 | 12 | 10k / 20 | |
| Sky | 4,800 | 3 | 5k / 3 | at its ceiling |
| Broadcast | 4,422 idle | 6 idle | 30k / 25 | 18 mid-kick, measured in r8 |
| Moments | 0 | 0 | 2k / 10 | idle |
| Experience | 0 | 0 | 5k / 10 | attachments excluded |
| **Stadium** | **222,674–230,661** | **94–101** | 287k / 160 | ~67 MB textures |
| **Tabletop** | 23,760–23,800 | 67 | 80k / 110 | |

**Identical to integration-15 in every line**, which is the expected result:
crowd-r9 changed a colour and moved no geometry. The stats are confirmed fresh
by the runtime lines around them — 17 dress lines against integration-15's 12,
and `crowd rings: meshes out to 7.6–10.6 yd` (the ring reaches further from
some seats than the 7.6 yd crowd-r8 reported from the sideline).

## The rubric, per actor

Scored on this checkpoint's frames. 1–5, the art bible's eight lines. Changes
from integration-15 are marked.

| Actor | Read | Light | Material | Scale | Life | Clarity | Comfort | Cost |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| Field | 4 | 4 | 3 | 5 | 3 | 5 | 5 | 5 |
| Sideline | 4 | 4 | 4 | 5 | 4 | 4 | 5 | 5 |
| Bowl | 4 | 3 | 4 | 5 | 4 | 4 | 5 | 4 |
| Crowd | 4 | **3** ↓ | 4 ↑ | 4 | 4 | 4 | 5 | 4 |
| Lighting | 4 | **4** ↓ | 4 | 5 | 4 | 5 | 5 | 5 |
| Sky | 4 | 5 | 4 | 5 | 3 | 5 | 5 | 5 |
| Broadcast | 5 | 4 | 4 | 5 | 5 | 5 | 5 | 5 |
| Moments | 5 | 5 | 4 | 5 | 5 | 5 | 5 | 5 |
| Audio | – | – | – | – | – | – | – | 5 |
| Experience | 4 | 4 | 4 | 4 | 4 | 4 | 4 | 5 |

Crowd's **Material rises** — cloth is the club's own colour, mottled per fan
rather than every dark-club fan landing on one band value. Crowd's and
Lighting's **Light both fall one**, for the same measured reason: see below.

## Interactions judged

1. **The stands moved further from the art bible, not closer.** `light_levels
   --bands` on the same shot, one commit apart:

   | | integration-15 | here |
   |---|---:|---:|
   | field → stands | +1.43 stops | **+1.66 stops** |
   | far-stand mean luma | 29.5 | 24.5 |
   | far-stand detail | 5.09 levels | 4.08 levels |

   The bible asks for **1 stop**. `actor/lighting-r2` had already flagged 1.45
   as its own worst thing and named concourse spill as the lever; crowd-r9,
   correct in isolation, widened the gap by darkening most of what the band is
   made of. Neither actor is wrong and neither can fix it alone: the crowd
   cannot lift a club it does not own, and Lighting's spill is the only lever
   that raises a stand without touching a club's colour. **This is the
   director's to sequence, and it is now the stadium's biggest single miss
   against its own bar.**

2. **Saturation halved in the far stands** (0.29 → 0.12 mean), because `chip()`
   had been lifting *every* club, not only the dark ones — Minnesota's purple
   was lifted too. Hue separation between the two supports did not suffer:
   measured in the same windows it went 2° → 10°.

3. **Where clubs differ in hue, the system works.** `s-bowl-wide-college.png`
   shows Temple's crimson blocks unmistakable against Toledo's navy. Where they
   do not — two dark navies — the supports are told apart by position, which is
   round 6's verdict and unchanged.

4. **The timing chain still holds end to end**, and the log gives the exact
   reason a frame looks the way it does: `moment touchdown fired at t=20.14,
   held 5.21 s` and `score MIN 6 - CHI 17 drawn at t=20.14, held 5.21 s`. The
   `t5.1` frame is therefore **0.11 s before the landing** — the crowd standing
   in it is the third-down rise (Minnesota had 3rd & 8 at CHI 32, so the home
   defence was on the field), not an early celebration.

5. **The darker crowd did not cost the broadcast layer.** The trails, the lit
   ball and the painted lines all read against the darker stands in the
   mid-play frames; `actor/broadcast-r8` had already lifted trail opacity for
   the darker *sky*, and that change covers this too.

## Worst thing left, per shot

- `s-bowl-wide.png` — the far stands are a dark navy field with pale flecks;
  the club is legible but the bowl has lost the colour it had. This is
  interaction 1, and it is the frame that shows it.
- `s-bowl-wide-phi.png` — paint and stands agree; both are so dark that the
  lit ribbon and field carry the whole frame.
- `s-bowl-wide-college.png` — the best of the three: crimson against navy, and
  the dense college yard markings read as markings rather than crosshatch.
- `s-crowd-closeup.png` — **flat cards still read through at the club seat**;
  the grass shows through the figures in the row below. `club-near-i15.png`
  beside `club-near-i16.png` shows it identically in both, so it is *not* a
  regression — crowd-r8's fix reaches the sideline seat and not this one.
- `s-crowd-closeup-phi.png` — midnight green at two metres is a shade off
  black. Correct, and still the frame that costs the most.
- `s-field-level.png` — no blade reads as a blade; unchanged, awaiting a turf
  round.
- `s-td-moment-t5.1.png` — held, 0.11 s short of the landing. Right.
- `s-td-moment-t8.5.png` — ribbon, fireworks, score and win probability all
  together at 82%. Right.
- `s-td-moment-t4.2-fg-endzone.png` — the net's grid still crosses the frame
  from behind the posts; Sideline proved the wash itself is Lighting's haze.
- `s-tabletop.png` — stone plinth, field brightest on the table; the
  win-probability streak still floats behind the model.
- `s-bowl-wide-p*-*.png` — run, short, deep and kickoff all read mid-flight.

## Top 5 worst left

1. **Lighting (with Crowd) — the stands are 1.66 stops under the field** where
   the bible asks for 1, and this checkpoint widened it. Concourse and
   vomitory spill is the lever; Bowl has already measured that its own albedo
   is not the cause.
2. **Crowd — flat cards read through at the club seat.** Not a regression, and
   the structural fix is the lod3 tier at ~120 triangles crowd-r8 named, which
   would roughly double the mesh radius for the same budget.
3. **Field — no blade reads as a blade at field level.** A turf-authoring
   round, named and deliberately not half-tuned.
4. **Crowd — the black-club case has never been seen.** Las Vegas and
   Pittsburgh are covered by tests and arithmetic; a committed fixture with a
   `#000000` club at home is the cheapest way to close it.
5. **Bowl — the dark band under the ribbon and the vomitory mouths**, both
   occlusion rather than albedo, both wanting the same spill as item 1.
