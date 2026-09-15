# Broadcast — critique log

Owner: the Broadcast specialist. Actor: `Actors/Broadcast/`, `visual.broadcast`,
the scene's drives, ball, lasers and win probability. Shots judged:
`redzone-trails`, `td-moment`, `bowl-wide`, `field-level`, `tabletop`.

Machine rule for every shoot: one simulator slot, `fe-actor-broadcast`, API on
8805, shut down after the run.

## Baseline — integration 1 (`docs/lookdev/integration-1/`)

- **td-moment:** the win-probability horizon is a scribbled white polyline in
  the sky with three floating words ("CHI / WIN PROBABILITY / MIN") beside it.
  It reads as a glitch, not a graphic.
- **redzone-trails:** the drive is three disconnected white wires; no ball to
  be found; the scrimmage and line-to-gain lines are neon tubes that vanish
  into the turf's stripes at distance.
- **tabletop:** the same three floating words hover above the model like a
  debug overlay.
- The ball is a lathed spheroid with a flat brown texture.

## Iteration 1

What changed:
- **Football:** modelled in Blender to NFL and college rules
  (`tools/blender/broadcast/build.py`, review render
  `docs/actors/broadcast/review/football.png`), loaded as `.usdz`.
- **Ball motion:** a manner per play from `visual.broadcast.ball.flight`
  (spiral, wobble, tumble, carry, bounce), pure math in `BroadcastFlight.swift`.
- **Trails:** camera-facing filaments with a soft halo instead of tubes;
  faint at the snap, full at the catch; older plays ghost and thin by age.
- **Lines:** painted in light with feathered edges and grass through them;
  a down-and-distance tag on the far half of the field.
- **Horizon:** one band, tinted toward the favoured side, faded at the ends,
  a marker at now and one label. Rails, fills and the three words are gone.
- **Ribbon:** larger capitals (legibility rule tested), a slow drift, and
  flashes for moments, first downs and red-zone entry.

Critique (`.work/shots/b1`):
- `bowl-wide`: the horizon finally reads as a graphic, but it is too thin
  and nearly white; its label is a speck. Lines read as TV lines.
- `redzone-trails`: a dark hole on the turf where the ball rests — the
  grounding shadow of a lifted ball. Removed.
- `td-moment`, `tabletop`: harness timing (black world, API not reachable
  yet); reshoot with a longer settle.

## Iteration 2 (`.work/shots/b2`)

- `bowl-wide`: the horizon band reads as a graphic now, with its label
  legible; but it runs almost white, and from the upper deck it crosses the
  glass scorebug. Raised to y 62-86 over z -62 and tinted harder
  (`tintGain`, lower `inkMix`).
- `tabletop`: band and percentage read cleanly at table scale.
- `td-moment`: harness caught the table mid-transition; the director's
  timing fix (617c4de) merged.

## Iteration 3 (`.work/shots/b3`)

- **TOUCHDOWN is a moment graphic, not a chip.** `BroadcastBanner` hangs a
  44-yard slab in the scoring side's colour over the end zone it names,
  wipes it open, holds it for `motion.momentSeconds`, wipes it shut; the
  ribbon floods with TOUCHDOWN in the same colour. The glass chip in
  StadiumViews is retired so the two never show together.
- Found: the slab and the horizon label's chip were invisible - only white
  survived. A transparent RealityKit material reads opacity from the
  texture's colour, not its alpha. Every composited graphic now carries a
  separate alpha mask (`BroadcastGraphics.overlay` / `.light`).
- Found: a football half-sunk at the fifty. It was the ball, never placed:
  `move(to:)` on an entity not yet in a scene does nothing, and a paused
  replay sends one scene before the stadium is on stage. Placed outright
  until there is a scene.

## Iteration 4-5 (`.work/shots/b4`, `b5`)

- `td-moment` (b4): TOUCHDOWN is a Bears-blue slab with the scoreline, owning
  the end zone; the gold pick-six trail sweeps the field. The horizon label
  finally shows its CHI chip.
- The horizon still read as a streak where the series spiked: smoothed
  (`smoothing` 0.035 of the series, now pinned to the model's value) and
  its thickness swells with the smoothed value, not the raw one.
- The tag sat on the 40's numeral: moved inside the numbers (15 yd from
  the sideline) and made taller.
- Scorebug and drive log (b5): club-washed side panels, the down on its own
  plate that turns red in the red zone; the drive log dims older plays the
  way their trails do and prints each gain.
- `verify_scene.swift` now flies the ball down all 1,422 arcs of the
  fifteen replayed scenes (spiral nose on the tangent, wobble within its
  angle, carry tucked, never under the grass).

## Iteration 6-8

- Budget: two draw parts per trail would spend a fifteen-play drive at 30.
  The newest four plays draw individually; older ones merge into one ghost
  (2 parts). Beacon cards merged; the lines' invisible glow strip dropped.
- **Ribbon dropout (integration 4):** Bowl's kit hangs a dark screen at
  exactly `bowl.ribbon.offset`, tessellated to 0.1 yd; the crawl on the
  same surface z-fought it into patches. The crawl now stands 0.2 yd toward
  the field along the fascia normal, cut into 480 segments. Proof:
  `.work/shots/b8/s-bowl-wide.png`, `s-field-level.png` - continuous all
  round, against `docs/lookdev/integration-4/s-bowl-wide.png`.
- Banner drawn to `visual.moments.banner` (Moments' contract): 34° wide at
  the seat's eye, ≥ 8° tall, 24 yd over the scoring end zone, timeline
  offset, 4.2 s dwell, 0.35/0.6 s wipe, 1.4° scoreline. No turnover banner:
  the contract times it never.

## Budget (stadium, a fifteen-play drive, during a moment)

| Part | Draw parts | Triangles |
|---|---|---|
| Trails: 4 newest + 1 merged history (core + halo) | 10 | ~4,300 |
| Horizon: halo, band, marker, label | 4 | ~600 |
| Football (NFL model: leather + lace) + glow | 3 | ~3,500 |
| Beacon | 1 | 4 |
| Lines (scrimmage, line to gain) + tag | 3 | 6 |
| Ribbon crawl | 1 | 960 |
| Banner: slab + glow (only during a moment) | 2 | 4 |
| **Total** | **24 / 25** | **~9.4k / 30k** |

Textures ~9 MB of 20: football 3 x 512² packed, trail/line/marker PNGs,
the banner 2048x560 plus its mask while a moment shows, the ribbon crawl,
the horizon band and label. Counted from the build, not measured in the
simulator: `-stadiumStats` reports at build time, before a drive arrives
(4 parts, 3.7k triangles then).

## Integration-11 polish (`docs/lookdev/integration-11-polish/`, before in `before/`)
- **Trails from low seats (`trail.lowSeat`):** from the field seat a drive's passes stood over the far stands as five grey wire arches (`before/s-field-level.png`).
  - **Rule:** a play already done now flies no higher than `apexOverEye` 0.8 of the eye's height (never under `minApexYards` 1.5), in `BroadcastTrails.lowered`. The newest play and the live flight keep the scene's apex, and a lowered history ghost draws at `historyOpacity` 0.2.
  - **Where it applies:** from the club (eye 13.5 yd) and every seat above, a 20-yard pass (10 yd apex) is untouched, which `test_done_plays_lie_down_under_a_low_eye_and_stand_from_the_stands` holds. From the field seat the wall is gone.
- **Ribbon clipping:** the crawl ran past its 36 yd segment, so every repeat cut the down to "2ND & 6 A".
  - **Fix:** `segmentYards` 36 → 60, and the crawl now measures itself, narrowing the clock and down toward `fitFloor` 0.72 before dropping RED ZONE. `test_the_ribbon_segment_holds_its_crawl` checks a long down fits at full size.
  - **Shots:** the red-zone crawl reads whole in `s-redzone-trails.png` and `s-field-level.png`.
- **Video board:** now a scoreboard first.
  - **Score:** each club is a `sideShare` 0.3 block, its abbreviation on a darker third and the score filling the rest at 0.86 of a `scorebugShare` 0.42 band. The clock is 0.56 of the band high, with the quarter under it.
  - **Down strip:** full width, `downShare` 0.15; it turns red with "RED ZONE" inside the 20.
  - **Last play and drive:** the last play is two lines behind a bar in its trail colour (the "LAST PLAY" header cost a line). The drive diagram stays at the right.
  - **Legibility:** smallest text unchanged at 0.12 of the height, 18′ from the end-zone seat.
- **Geometry not changed:** the face is Bowl's 36×13.5 yd, baked into Bowl's model. From the club seat it subtends about 14° and sits 69° off the seat's forward, so it is a glance, not a view. A larger board is a Bowl and director change: about 54×20 yd on the same parapet, `centre.y` about 60.
- **Scorebug yield:** verified unchanged. `scorebugHidden` is true only at `endzone`, where the board is dead ahead. From every other preset the board is more than 35° off forward, so the glass scorebug and the board are never both straight ahead.
- **Budget:** `-stadiumStats` counts at build time: 5 parts / 4.4k triangles (tabletop 4 / 4.4k). The drive trails are unchanged in count, per the table above: 24 of 25 parts during a moment.
- **Worst thing left:**
  - `crowd-closeup`: the board is legible but small in frame; its size is the limit now, not its layout.
  - `field-level`: the newest pass still stands full height at the right edge, alone, which is the intent. The ribbon is too oblique from field level to read at all.
  - `redzone-trails`: the three newest passes from the club seat are thin and bright, but the ghosted one is hard to tell from the stands behind it.
