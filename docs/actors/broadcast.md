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

## Round 4: plays that read like a broadcast (`actor/broadcast-r4`)

The user's word on integration-11: "plays dont look like the real thing". Every
play was one parabola from snap spot to finish spot, so a 3-yard run and a
3-yard pass both stood up as rainbows (`integration-11/s-redzone-trails.png`).
The user chose broadcast graphics with no players, so the no-players rule stands.

- **The path (`scene.play_path`, contract `arc.path`, additive):** every arc
  now carries timed segments - `hold`, `carry`, `air` - with a `phase`
  (presnap, snap, drop, mesh, run, throw, catch, yac, fall, kick, return,
  walk, sack, spike, settle). They're built from the type, the scene's spots
  and the text, with the numbers in `visual.broadcast.play`. `apex`,
  `seconds` and `duration` are unchanged for ports that have not moved.
  - **Snap:** every play starts on its spot for `presnapSeconds`; shotgun
    snaps fly 5 yd back.
  - **Runs:** carried at 1 yd, never flown. The mesh sits beside the
    quarterback, then the run goes to the hole the text names (end 11,
    tackle 5, guard 2.5, middle 0 yd off the lane, right = +z x attack), with
    a cut and a drift. "Pushed ob" ends on that sideline. Scrambles skip the
    mesh.
  - **Passes:** a drop (1.5 yd in the gun, 6 under centre, 1.9-2.3 s in the
    pocket), then a gravity parabola: hang 0.35 + 0.048 x throw length, rise
    g x hang^2 / 8 x 0.95. Air yards are bounded by short and deep (ESPN has
    no air yards), with the rest run after the catch. Incompletions fall to
    the grass at 9/24/12 yd; a catch pushed out is made 3 yd inside that
    sideline.
  - **Kicks:** punts from 14 yd back, hanging 3.2 + 0.025/yd s and landing
    on the spot the text names ("punts 51 yards to DAL 26"). Kickoffs
    hang about 4 s, and a touchback does not return. Field goals go from the
    hold at 7 yd, with the rise floored so a good kick clears the bar by the
    promised yard. Blocked kicks fall short. Every return runs to the spot
    in the text.
  - **Also:** sacks, interceptions (thrown to the "at" spot, then returned),
    kneels, spikes, penalties (flag, then walk).
  - **Reviews and conversions:** `play_body` reads the play after "REVERSED."
    and drops what follows a two-point try or a penalty. "M.Kneeland" is not
    a kneel.
- **Tempo:** real seconds. Runs of up to 10 yd take 2.4-5.5 s, short passes
  3-6.5 s, punts 7-12 s, all capped at 14 s. A replay faster than
  `referenceSpeed` divides them as before (`path.duration`). Plays keep a
  `beatSeconds` 0.9 rest between them when several are queued.
- **The headset:**
  - `SceneMath.ball/segmentPoint/trace/lowered/peak` fly and draw the path;
    `BallFlight.pose(arc, seconds:)` spirals throws, tumbles kicks, tucks and
    bobs runs, and lays the ball flat at rest.
  - Trails draw carried legs on the grass (`heights.trailLift` 0.12) and
    flights with ends easing to it. They grow behind the ball through the
    whole play, not just the air.
  - A ground marker rings the snap (`play.marker.pulse*`), then becomes
    the ball's shadow, fading with height, so depth reads. The ball's glow
    grows x1.7 while it's in the air.
  - The beacon hides while a play is on.
- **Edge fade:** now kicks only (`trail.edge.shapes`), judged on the
  airborne part of the line and weighted by length. A pass now crosses the
  field toward a sideline seat, and fading it hid the play being watched
  (from the club seat, a 16-yd out to the near sideline faded to 0).
- **Ribbon:** a whole number of tiles now fits the ring (the seam made
  "REDNE"), and a flash spaces whole words across its tile (it cut
  "TOUCHD TOUCHDOWN").
- **Budget:**
  - `trail.age.individual` 4 → 3 (-2 parts).
  - The beacon is off in flight (-1).
  - The marker costs one card (+1).
  - During a kick that is 27 → 25 by count; not measured (see below).
- **Audio:** the play whistle now waits for `arc.flightSeconds`, the path's
  duration, not the old 2.5 s-capped flight. That is a one-line change in
  Audio's file, flagged for its owner.
- **Tests:**
  - `tests/test_play_path.py` (10): the path joins and stays on the field,
    runs hug the grass and go the way the text says, pass rise follows hang
    and grows with length, deep throws go further, kicks hang like real ones,
    good field goals clear the bar, tempo and speed scaling, and text
    cleaning and spots.
  - `verify_scene.swift` flies every path in 15 scenes: 331,030 assertions,
    covering snap spot, never under the grass, no teleport, spiral along
    its flight, run trails on the grass, and lowered caps.
  - `sideOn`'s Python restatement follows the trail line
    (`scene.trail_points`).
- **Not verified:** the Xcode 27.0 update installed at 16:58 on 2026-09-15
  has not had its licence accepted.
  - `xcodebuild`, `simctl` and `/usr/bin/make` all refuse to run, so the app
    target (BroadcastActor, BroadcastTrails, BroadcastBoards, AudioActor) is
    unbuilt and no shots were taken.
  - `test_crowd_choreography.test_the_scored_on_side_never_celebrates`
    fails for the same reason; it compiles through `xcrun`.
  - `SceneSpec`, `SceneMath`, `BroadcastFlight` and the Look structs compile
    and pass under Command Line Tools swiftc.
- **Worst thing left (no shots this round):**
  - `redzone-trails`, `field-level`, `bowl-wide`, `td-moment`, `tabletop`:
    unshot until the licence is accepted; the new paths are proven only in
    the scene, `verify_scene` and tests.
  - `td-moment`: moments fire when the scene arrives, and a scoring play now
    takes about 5 s to play out, so the banner and fireworks lead the ball.
    The composer should hold a moment until Broadcast lands its play
    (`hasTrail(playId)` already exists). That is a director change.
  - Ports: web and Android still draw `apex` parabolas until they read `path`.

### Round 4 shot pass (`docs/lookdev/broadcast-r4/`, Xcode 27.0, visionOS 26.5 sim)

The licence being accepted, the branch built first time with no compile errors
and no new warnings (only the AppIntents metadata notice, which `6c57bc3`
raises too). What the frames showed, and what changed because of them:

- **The ball was not findable.** At the upper deck it was a dark blob with its
  own shadow under it and no glow to speak of. `ball.glow.yards.stadium`
  2.6 → 4.2 and `glow.opacity` 0.85 → 1.0; the marker's shadow softened
  (`shadowOpacity` 0.55 → 0.32, `shadowYards.stadium` 1.4 → 1.9) so it reads
  as a shadow rather than a hole. After: the ball reads as a lit point on the
  grass through a run (`bowl-wide-p4.5-run`, `-p5.5-run`).
- **Trails were thin at distance.** `trail.core.stadium` 0.2 → 0.34.
- **Budget, measured with `-stadiumStats` during the kick:** 26 draw parts at
  `fieldGoal+3.0s`, over the actor's 25. `trail.age.individual` 3 → 2 brings
  it to **24** (22 at +0.5 s and +6 s), 7.5k triangles of 30k. The stadium
  totals 98 parts idle, 115 mid-kick.

**Per play type, from the renders**

| Play | Verdict |
|---|---|
| Run | **Good.** Carried along the grass, never an arc, from the upper deck, the club seat and field level. The ball is findable and its shadow reads (`bowl-wide-p4.5-run`). |
| Short pass | **Reads,** but the 1.2 yd rise is invisible beyond about 40 yd, so from the upper deck it reads as a flat line (`bowl-wide-p5.5-short`). |
| Field goal | **The laid trail reads** as a thin arc over the end zone, and the ribbon says "4TH & 8 AT CHI 14 · RED ZONE" whole (`td-moment-p4-fg`). The kick itself was not caught in flight. |
| Deep pass | **Not verified.** Never caught mid-flight (see below). |
| Punt | **Never animates.** A punt is its drive's last play, and the scene moves to the receiving team's drive as the punt lands, so the shown drive changes and the punt is laid at rest instead of flying. Pre-existing, not from this change; the kickoff that follows does fly. |
| Kickoff | **Animates but was never seen.** `-trailTrace` puts the ball at 18 yd over the left of the field with a 46-point live trail, yet no ball and no trail appear in `bowl-wide-p6/p8-kick-deep`. Unresolved, and the most important thing left. |

**The touchdown banner leads the ball.** Timestamps from one run:
`fly 4017728102188 Interception Return Touchdown 5.112s` at 17:20:54.774, the
moment's first stats line at 17:20:55.269, `land` at 17:20:59.872. So the
banner, strobe, fireworks and the score all fire as the ball leaves, and the
ball is still in the air 5.1 s later - `td-moment-t0.5-td` shows CHI already
on 17 with the return still running.

**The hook I want** (a director change, not made here): the composer holds a
`.moment` until Broadcast says that play has landed - `hasTrail(m.playId)`
already answers it - with a timeout of the arc's `path.duration` + ~1 s so a
scrub or a reduce-motion jump never strands the moment. Failing that, a
`shared.landed(playId:)` on the blackboard the composer waits on.

**Look-dev:** `--play "<text>"` plays any shot through the first play whose
text contains it, with `--times p4,p5.5` for frames mid-play. It is flaky by
nature: a play only flies when its own drive is the one on screen, so plays
that end a drive (punts, field goals) and plays queued behind a long kickoff
often never animate. Shots here were taken with a burst of times and the ones
that caught the play kept.

**Worst thing left:** the kickoff's ball and trail are invisible in flight
though the trace has them placed; then the deep pass, never caught in a frame.

## Round 5: the ball at distance, kicks that stop at the posts, punts that play (`docs/lookdev/broadcast-r5/`)

Integration-12's five findings in Broadcast's area, four fixed and one
answered with a frame.

- **The ball lost its glow at distance (`ball.glow`).** The light was a fixed
  4.2 yd billboard *behind* the leather, and the child sits in the ball's own
  space - which spins with the spiral - so the offset r4 added swam behind the
  ball and back. At a hundred yards the leather is a third of a degree wide
  and the halo read as a dark dot in a ring.
  - The glow now holds `minArcMinutes` 46' at the wearer's eye, growing with
    distance to `maxYards` 11, and sits `coverYards` 0.5 toward them with the
    ball's rotation undone, so far off the light covers the leather.
  - Frames: `bowl-wide-p5-deep`, `-p5-short`, `-p8-kickoff` - a clean lit dot
    from the upper deck, no dark centre.
- **A lit ball over the far stands at t8.5 (`SceneMath.kickCut`).** It was the
  extra point. A goal kick's arc carries `goalKick.overshootYards` 10 past the
  posts so that it plainly crosses their plane, and the ball flew the whole
  way - out over the stands, with the trail behind it reading stick-straight
  end-on. The ball and the trail now stop `play.goalKick.netYards` 3 past the
  plane, where the kick leaves play, and the ball is hidden until the next
  snap gives it a spot. Measured: `land ... at y 3.7 cut=3.9`, just over the
  crossbar. `td-moment-t8.5-td` is clear.
- **A short pass read flat from the upper deck (`play.pass.minRiseYards`).**
  A 1.2 yd rise is nothing at 100 yd. Every throw now rises at least 2.6 yd
  over its chord; a deep ball still clears a short one by well over a yard and
  the longest are three times higher, which `test_play_path` holds.
- **Punts never animated (`play.holdSwitchSeconds`).** Not the punt's fault:
  the scene moves to the receiving team's drive about six seconds after the
  snap, while the ball is still up, and the switch cleared the trails and
  cancelled the flight. A new drive now waits for the field to go quiet, up to
  8 s. Trace: `fly ... Punt 7.575s`, `hold drive=... for ...`, `land`. The
  punt reads as a proper hanging parabola (`bowl-wide-p6-punt`).
- **The deep pass, never caught in a frame at r4:** `bowl-wide-p3.5-deep`
  has the ball lit in flight, and `-p4.5-deep` the finished arc from the
  quarterback, over the 30, down to the catch at the 40 with the run after it.

**Gates:** `make test` 560, `verify_scene` (which now checks every kick's cut
lies inside its flight, past the posts, with the ball still up), `verify_crowd`
337,996 checks, `contrast_check`, and a build with no new warnings (the
AppIntents notice only, as at `e173952`).

**Budget:** 24 draw parts at `touchdown+3.0s`, 6 idle, 6.2k triangles - inside
the actor's 25 and 30k.

**Worst thing left:**
- No frame catches the ball *mid-kick* on a field goal: the kick is over in
  3.9 s and the shot times either side of it missed. Everything else about
  that kick is verified.
- A play only animates while its own drive is the one on screen, so plays
  queued behind a long kickoff can still be laid down without flying.
- The moment still leads the ball; the hook is the director's
  (`director/moment-timing`).

## Round 6 (the director's fix for integration-13's #1 and #2)

- **The drawn score waited for nothing.** The moment gate held the banner, the
  fireworks, the strobe and the crowd until a play landed, but the ribbon, the
  video board and the glass scorebug all redrew from the scene on arrival:
  `td-moment-t0.5` read CHI 17 with the pick-six still running. `StatusGate`
  now holds the arriving status behind the play it describes, and the composer
  hands every actor the scene with the status the stadium is *showing*. The
  score, the down and distance and the red-zone flag follow the ball;
  everything else in a scene arrives untouched. Measured: the score is drawn at
  t=253.75 having been held 5.24 s, the same hundredth of a second the moment
  fires.
- **A banner outlived its play.** At `t8.5` a TOUCHDOWN slab hung over a board
  that had moved to the next snap. `BroadcastBanner.snapping` is called when
  Broadcast starts the next flight: the slab wipes out over `exitSeconds`, and
  is never cut shorter than `visual.moments.banner.minSeconds` (2.5), so a
  quick snap or a fast replay shortens it rather than flashing it.
- **Shots:** `docs/lookdev/score-timing/`, with what each frame proves and the
  two log lines in its README.
- **Worst thing left, and it is yours:** the board still *narrates* a play
  while the ball is in the air - `s-td-moment-t0.5-fg-club.png` says the kick
  "is GOOD" under a score that correctly has not moved. The words come from
  the drive's newest arc in `BroadcastVideoBoard.image` (`arcs.last`) rather
  than from the status. Feeding the board the newest *laid* play from `trails`
  would fix it, and the drive log beside it has to follow in the same change
  or the two disagree.

## Round 6: the board narrates what has landed (`docs/lookdev/broadcast-r6/`)

`director/score-timing` made the score wait for the ball. Two things in
Broadcast were still ahead of it, both the same shape, and both are now tied
to the same landing.

- **The video board (`BroadcastVideoBoard`).** It took `arcs.last` - the
  newest play to *arrive* - so it read "W.Reichard 31 yard field goal is GOOD"
  with the kick still in the air, beside a score correctly waiting for it.
  `apply(_:laid:)` now takes the newest play the viewer has seen land, from
  the same `trails.has` the score's gate uses, and the board's drive diagram
  draws only the plays up to it. The board is redrawn when a play lands, so it
  catches up on the frame the ball does.
  - `td-moment-p4.2-fg-club`, `-p4.4-fg-sideline`, `-p5.0-fg-endzone`: mid-kick,
    the board says "J.McCarthy pass incomplete short right to..." - the third
    down before it - and the ribbon still reads MIN 0.
  - `td-moment-t0.5-td`: the pick-six is still running; the board says
    "A.Jones right end to CHI 32 for 2 yards" and the score is CHI 10.
  - `td-moment-t5.1-td`: both have caught up - CHI 17, and the board has moved
    on to the kickoff.
- **The win-probability horizon (`BroadcastHorizon`).** Win probability is a
  top-level field, not part of the gated status, so the band swung to the
  outcome of a play still in the air. `update(_:hold:)` keeps the drawn band
  while the newest play is airborne. Measured across the touchdown: 58% at
  t0.5 with the return still running, 82% at t5.1 once it had landed.
- **The drive log is not Broadcast's to change.** `DriveLog` lives in
  Experience's `StadiumViews.swift` and reads `spec.shownDrive` from the spec
  the renderer hands the views. **The hook:** have the renderer hand views a
  spec whose `shownDrive.arcs` stop at the newest laid play - it already knows,
  through `broadcast.hasTrail` - or pass `DriveLog` a `laidThrough: String?`.
  Either fixes the log, the scrubber and anything else reading the drive, in
  one place. Broadcast's board and diagram already obey it.
- **A play queued behind a long kickoff was laid down without flying.** The
  drive-switch hold from r5 counted total time, and an eleven-second kickoff
  out-waited its eight seconds, so the switch took the stage and the queued
  play never flew. The hold now measures the field being *idle*: while the ball
  is moving it keeps its patience. Trace from the field-goal shoot:
  `fly Kickoff 11.613s`, `land`, then `fly Pass Reception 5.969s`.
- **The ball mid-kick, never caught before.** The kick lasts 3.9 s and the
  strike is 2 s into the path, so the window is p5-p7 after the resume, and
  each screenshot costs over a second - closely spaced times slip past it.
  Shot one frame per launch and checked the file's own timestamp against the
  `fly`/`land` pair in the log. `td-moment-p5.0-fg-endzone` catches it:
  the lit ball climbing from the left, the posts ahead of it, the board and
  ribbon still on the previous play.

**Gates:** `make test` 566, `verify_scene` 495,078 assertions, `verify_crowd`
346,120 checks, `verify_moment` 117 checks, `contrast_check`, and a build with
no new warnings. `xcodebuild` takes `-destination "generic/platform=visionOS
Simulator"`; the harness installs to a cloned device by id.

**Budget:** 22 draw parts at the touchdown's peak (6 idle, 8.4k triangles), of
the actor's 25 and 30k.

**Worst thing left:**
- The drive log still narrates a play in the air, pending the hook above.
- From the club and sideline seats the near crowd hides a kick struck in that
  corner; the end-zone seat is the one that sees it.
- Nothing in the suite holds the board to the laid play: it is a UIKit drawing
  path, so `verify_scene` cannot reach it. A test needs `newestLaid` split out
  into a file that does not import UIKit.

## Round 7: a scoring play is announced when it counts (`docs/lookdev/broadcast-r7/`)

Integration-14's first worst thing: "a made field goal is announced about two
seconds before it counts", root cause recorded as "the kick's own scene never
carries its points". **Measured, that root cause is wrong, and so is the two
seconds.**

- **The scene does carry the points with the kick.** Sampling the replayed
  pick-six four times a second from 1028 s to 1040 s, there is no instant at
  which the kick's arc is in the scene under the pre-kick score: at 1032.00 s
  the Field Goal Good arc and `3-7` arrive together, in one scene. Nothing to
  fix in `scene.py`, and no contract change is needed.
- **The gap was 0.11 s, not 2 s.** On the tip, `land 401772810961 ... cut=3.9`
  at t=23.91 and `score MIN 3 - CHI 7 drawn at t=24.02, held 4.06 s`. The
  board flipped on the landing frame and the score on the release frame after
  it. Integration-14 sampled t4 and t6 and read the distance between its own
  two samples as the defect; its t4 frame caught that 0.11 s window.
- **The layer is Broadcast's.** The score is gated correctly and must not move
  before the ball lands; the board simply must not announce an outcome the
  drawn score has not acknowledged. Both now hinge on the same release.
  - When a play whose `style` is `score` lands, `BroadcastActor` records the
    drawn score at that instant. The board's `laid` predicate holds that play
    back while the drawn score still reads the same, so the words and the
    number appear on one frame. `momentHoldGraceSeconds` is the backstop: a
    scene whose points never arrive cannot silence the board for ever.
  - This costs nothing on a play that does not score, and it is the same
    landing the score, the moment and the win-probability band already use.

**The ribbon "double-draw" is the review image, not the ribbon.** Shot
`field-level` and cropped the band 1:1 out of the 3840x2160 original: one
crawl, one gold trim line, "8:30 - 1ST · 1ST & 10 AT MIN 13 · RED ZONE" read
once. The same band in the committed 1400-wide `s-` copy shows the ghost
integration-14 describes - the downscale aliases a band a few pixels tall.
Nothing to fix; shoot the original when judging the ribbon edge-on.

**Frames** (board and ribbon read off each):

| Shot | Board | Ribbon | Ball |
|---|---|---|---|
| `td-moment-t3.5-fg-endzone` | MIN 0 · 4TH & 8 · "J.McCarthy pass incomplete short right to..." | MIN 0 CHI 7, 4TH & 8 | lit, climbing at the posts |
| `td-moment-t4-fg-endzone` (integration-14's time) | MIN 0 · 4TH & 8 · the same incompletion | MIN 0 CHI 7 | down |
| `td-moment-t4.5-fg-endzone` | **MIN 3** · 1ST & 10 AT CHI 39 · "W.Reichard 31 yard field goal is GOOD" | FIELD GOAL flashing | out of play |
| `td-moment-t0.5-td` | MIN 6 · CHI 10 · "A.Jones right end to CHI 32 for 2 yards" | 3RD & 8 AT CHI 32 | pick-six running |
| `td-moment-t4-td`, `-t8-td` | the score and the words together, then the kickoff | | |

**Gates:** `make test` 566, `make verify-scene` 495,078 assertions,
`contrast_check`, build clean with no new warnings
(`-destination "generic/platform=visionOS Simulator"`). `verify_moment` (117
checks) and `verify_crowd` pass, run by the `swiftc` lines in their own
headers: **neither is a Makefile target** on this tip, whatever the round's
brief says. Adding them is a one-line change each and belongs to the director.

**Worst thing left:**
- The drive log still narrates a play in the air (r6's hook, Experience's
  file, unchanged).
- The board's rule has no test: it is a UIKit drawing path, so `verify_scene`
  cannot reach it. `newestLaid` and the new score-acknowledgement rule want a
  file that does not import UIKit.

## Round 8: the objects, judged at the distance they are seen (`docs/lookdev/broadcast-r8/`)

Shot `before/` and `after/` with one binary: the app takes its look from the
scene the API serves, so a token edit between runs changes the render without
a rebuild. The night is two stops darker and the paint is the clubs' own now,
which is what these objects are judged against.

**The uprights re-check (Sideline widened them to 18 ft 6 in inside-to-inside,
6.167 yd).** Every kick in the three replayed games, at the plane of the posts:
good kicks cross **4.83-5.53 yd** up, i.e. 1.5-2.2 yd clear of the 3.333 yd
crossbar, all on the centre line (lane 0.00, inside the 3.083 yd half-width);
the two wide misses sit at **±5.58 yd**, outside the posts, as their text says.
The widening does not touch clearance, and `goal_kick`'s wide offset is
`half + wideYards`, so it follows the rule width automatically.

| Object | Before | After |
|---|---|---|
| **The ball** | **2.6x life size everywhere** - 0.8 yd long, about a yard in the hands of a close seat. A cartoon at any seat that can see it is a ball. | Life size (0.31 yd) within `nearYards` 14, easing to 2.6x by `farYards` 45, so it stays findable where it would be a speck. Its **light** does the finding (r5), not its size. `before/field-level-p6-ball` vs `after/`. |
| **Trails** | The newest play reads; the drive behind it had faded under the darker grass - a drive read as one arc. | `age.minOpacity` 0.30 → 0.42 and `historyOpacity` 0.32 → 0.46: the older plays read as a drive again without competing with the live one. `before/redzone-trails` vs `after/`. |
| **Lines in light** | — | Pass. Feathered, on the grass, no z-fighting, and they hold against the clubs' real paint: the blue scrimmage line and yellow line to gain both read over navy end-zone paint and over the mowing stripe (`after/field-level`). |
| **Ribbon** | — | Pass. Whole words from the club seat and from field level: "MIN 0 CHI 0 · 8:30 - 1ST · 1ST & 10 AT MIN 13 · RED ZONE", no clipping, no seam. |
| **Video board** | — | Pass as a screen: score leads, down strip red in the red zone, the newest **laid** play in words (r6/r7), drive diagram at the right. Legible from the end-zone seat across the field. |
| **Win-probability horizon** | — | Pass: one band, labelled with the club chip and a percentage, and it tells you who is ahead at a glance. |
| **Beacon and tag** | — | Pass. The beacon reads as a column of light on the ball's spot; "1ST & 10" is painted on the far half and legible from the club seat. |

**Budget, from an erased simulator log** (the stale-line trap): Broadcast is
**6 draw parts / 4,422 triangles idle** and **18 / 7,428 mid-kick**, against
25 and 30k. The ball's scale change spends nothing; the trail lift spends
nothing.

**The double whistle is real, and it is Audio's to fix.** Two paths fire on a
scoring play:
- `AudioActor.apply` schedules a per-play whistle at `arc.flightSeconds +
  playWhistle.afterFlight` (0.15 s), at the play's end spot, gain -24 dB.
- `AudioActor.choreograph` plays the moment's whistle at `timeline.whistle`
  (0.0 for touchdown, field goal, safety and turnover), at the field anchor,
  gain -14 dB.
Since score-timing, the moment fires when the play lands, so the two land
about 0.15 s apart, from two positions, at two gains - "twice at one instant
from slightly different positions". The fix belongs in Audio: skip the
per-play whistle when that play carries a moment that will whistle (its
`playId` is the moment's), or set `timeline.whistle` to -1 for kinds whose
play already whistles. Broadcast supplies the landing both of them key off,
and needs no change.

**The wall LED boards still have no seat that judges them.** They are
Sideline's object on the wall below the stands; the nearest preset is the
field seat, which looks *along* the wall, so they sit at a grazing angle in
every frame we have. A seat facing the wall square-on would settle it - a
`wall` preset behind the bench, or `sideline-props` re-aimed at the wall.
That is a `presentation.stadium.seats` change, so it belongs to Experience or
the director; Broadcast only notes that no existing shot can answer it.

**Worst thing left:**
- No seat preset stands within 10 yd of the ball: the closest is the field
  seat at about 25 yd, so "the ball at 10 yd" is still unjudged. The formula
  is honest there (life size under 14 yd), but no frame proves it.
- The drive log still narrates a play in the air (r6's hook, Experience's).
- `verify_moment`'s header compile line is stale - it now needs `SceneSpec`
  and `LaidPlay` too, and neither it nor `verify_crowd` is a Makefile target.
