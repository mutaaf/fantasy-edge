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
