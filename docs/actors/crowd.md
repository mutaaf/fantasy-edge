# Crowd: critique log

The crowd's bar is in `docs/ART_BIBLE.md`. Shots are `crowd-closeup`,
`bowl-wide` and `td-moment`, taken with `tools/lookdev.py` on the
`fe-actor-crowd` simulator. Paths are under `.work/shots/`, which is not
committed.

## Baseline (the Art Director's split)

`crowd-before/s-crowd-closeup.png`, `crowd-before/s-bowl-wide.png`

- **Far:** cards from a 32×64 atlas read as coloured noise, not people, within
  10 m.
- **Near:** the front rows are black silhouette cut-outs with the backs of
  heads pasted on.
- **Motion:** a whole slice bobs up and down together. Nobody moves on their
  own.
- **Budget:** 129k triangles, over the crowd's 120k.

## Kit (Phase A, Blender)

Review renders: `assets/actors/crowd/review/lineup_*.png`, `poses_*.png`.

| Round | What was wrong | What changed |
|---|---|---|
| 1 | Tube mannequins. Face features too small to read. Collars and pockets painted as white flashes. Arms fused to the torso at the shoulders. | A denser skin graph (biceps, forearm, calf, ribcage, waist). Heads 8% larger, with a bigger nose and ears. |
| 2 | Hunched shoulders. Cloth flaps at the yoke. A jacket zip stripe down the face. White eyes read as masks. | Looser cloth kept off the shoulder joint. The zip stops at the collar. Eye whites shrunk to 45% opacity. |
| 3 | Visors sat over the eyes. | The band and brim moved up to the brow. |
| 4 | Atlas bake came out empty: the UV layer fetched before a mode switch writes nowhere. | Re-fetch after each switch. |
| 5 | Fan 14's glTF held 14 fans' clips. The ACTIONS export takes every action that fits the skeleton. | Clear actions per fan. |
| 6 | USD shipped Z-up while its glTF twin was Y-up. | Both export Y-up, fans facing +Z. |
| 7 | Decimating subdivision-2 bodies with 6 mm shells to 1.5k triangles left spikes near the seat. White beanies read as snow. A fifth of the cast held signs. | Author at runtime density (subsurf 1, 16×10 spheres, single-sided shells). Hats wear the primary. At most 2 signs. |

## In the stadium (Phase B)

### Iteration 1: `crowd-iter1b/`

- **Crash first:** composing the club dress read freed memory, because Swift
  released the mask context after its last named use. Fixed with
  `withExtendedLifetime`.
- **Close-up:** people now, with heads, builds, hats, scarves, arms up. A far
  improvement on the baseline.
- **Problems:**
  - 158k triangles, over budget.
  - Near fans spiky from decimation.
  - A bright sign in the front row pulls the eye.

### Iteration 2: `crowd-iter2/`

- **Budget:** rings capped (16 LOD0, 70 LOD1). Crowd **117k triangles, 17
  draw parts**, under budget.
- **Problem:** the dress now composes off the main actor, so for about 15 s
  every club region showed the kit's 0.86 grey. The stands read as snow and
  `bowl-wide` caught a frame still building.
- **Fix:** a quarter-size dress is composed synchronously for the first
  frame, and the full size swaps in when ready.

### Iteration 3: `crowd-iter3/`

- **Colour:** the quick dress works. Clubs show from the first frame.
- **Near:** fans read as people, but faceted, because decimation marked edges sharp.
- **Far:** a confetti of white and black flecks on two flat hues. Every club
  fan wears the chip.
- **Banding:** vertical stripes where a whole slice changes pose.
- **`bowl-wide`:** near-black, but the baseline is identical. The harness
  camera sits inside the upper-deck geometry at `7530d53`, so this isn't a
  crowd problem.

### Iteration 4: `crowd-iter4/`

- **Fixes:**
  - Sharp edges stripped and polygons smoothed.
  - A third of each side wears neutrals (grey, black, denim, stone).
  - Every club colour gets its own value (0.72–1.08) and saturation (0–35% toward grey).
  - Far cards softened toward each fan's mean (contrast 0.72).
  - Card groups split into two interleaved variants, with slice edges jittered.
- **Result:** sections read as a mass. 117k triangles, 34 parts.
- **Gap:** the upper deck reads as sparse stick figures. Fans were about
  1.1 yd apart; real seats are 0.55 yd. Doubling the cards would break the budget.

### Iteration 5: `crowd-iter5/`

- **Fixes:**
  - Paired impostors: each far card is two neighbours at 0.503 m, baked
    in Blender as two passes composited nearest-first. The halves of a cell
    are dressed as different people.
  - Seats at 0.55 yd pitch, from `bowl.seating` when the scene carries it
    (through `SceneMath.seat`), with pairs kept inside a run and group
    edges on section boundaries.
- **Result:** 52,039 fans, **108k triangles, 34 draw parts**. The full dress
  composes in 6.4 s. The far stands are a dense, mottled, textured crowd.
- **Gaps:**
  - Too much cream: the neutral stone, a near-white secondary and khaki trousers.
  - Near fans show white wedges and sawtooth sleeve edges. The tint mask
    shipped at 1024² against a 2048² albedo.
  - LOD1 arms are faceted at 420 triangles.

### Iteration 6: `crowd-iter6/`

- **Changes:** full-size mask, LOD1 at 650 triangles (ring capped at 55),
  cream dropped from the neutrals, secondary darkened to `#CFCBC2`.
- **Result:** 114k triangles, 34 parts. The palette settles.
- **Gap:** the white wedges survived the full-size mask. They follow
  decimated triangles, so the real cause is baking colour after decimation.
- **`td-moment`:** black. The stadium hadn't built before capture; the
  director has since fixed the harness.

### Iteration 7: `crowd-iter7/`

- **Fixes:**
  - Albedo and mask bake from a full-resolution copy onto the low-poly UVs
    (selected to active). `kit_review.py` renders the shipped glTF with the
    runtime's tint, so a leak shows without a simulator.
  - The scoring side celebrates for as long as `bowl.sectionTint` names it:
    peak poses while Moments surges, then a half-pace stand/cheer/clap
    cycle. The other side sinks into its seats, and a few groan.
- **Result:** wedges gone, and `td-moment` reads as a stand on its feet.
- **Gap:** the blocky near fans are cards drawn close. About 400 seats sit
  within 12 yd of a club seat, and the mesh caps ran out at about 5 yd.

### Iteration 8: `crowd-iter8/`

- **Budget:** raised to 150k with the director's approval, since Bowl seats
  52k where the old budget assumed 32k.
- **Fixes:**
  - LOD2 pose meshes at 250 triangles for the 7–13 yd ring.
  - Rings dithered ±1.6 yd per fan, so a ring edge is a ragged band.
  - Towels wear the secondary and shrink.
- **Measured, club seat:** 151.1k triangles, 36 parts (16 LOD0, 40 LOD1, 190
  LOD2, 51,793 cards). Over by 1k, so `lod2Max` drops to 180. Tabletop: 734
  triangles, 22 parts, cards only.
- **Result:** every fan within reach of a club seat is a lit mesh.
- **Gap:** five towels raised at once read as rigid flags, so towels are
  capped at two fans.
- **Upper-deck and ring-boundary shots:** these moved to iteration 9.

### Iteration 9: `crowd-iter9/` (on Bowl's served seating)

- **Seating:** every stadium fan comes from `bowl.seating` through
  `SceneMath.Ring` and `SceneMath.seat`: Bowl's seats, each seat's facing,
  and its row's floor.
- **Chair fit:** Bowl's chair origin is the feet, with the pan at 0.43 m and
  the back at z −0.22.
  - Seated poses move forward and lift shorter fans so every pelvis rests
    at 0.52 m.
  - Standing poses step 0.12 m forward of the folded pan.
  - All of it is in `visual.crowd.chair`.
- **Hooks for Moments:** `shared.stand(target, until:, clap:)`,
  `shared.sit(target, until:)` and `shared.groan(side, until:)`, aimed at a side
  or at seating sections, in `CrowdCues.swift`. Debug builds take
  `-crowdCue kind:side`.
- **Measured** (44,982 fans, 16 LOD0, 40 LOD1, 180 LOD2, 44,746 cards, 36 draw parts):

  | Seat | Crowd triangles | Stadium triangles |
  |---|---|---|
  | Club (`crowd-closeup`, `td-moment`, `bowl-wide`) | 142.2k | 239.7k |
  | Upper deck (`crowd-closeup_upper`, `td-moment_upper`, `bowl-wide_upper`) | 142.3k | 237.4k |
  | Tabletop | 734 (22 parts, cards only) | |

- **Shots:**
  - `s-crowd-closeup.png`: rows seated in the modelled chairs.
  - `s-bowl-wide_upper.png`: the far deck full, the deck in front seated row by row.
  - `s-crowd-closeup_boundary.png`: pitched down across LOD0 → LOD2 → cards. No seam; the dithered band is not visible.
  - `s-crowd-closeup_cue-{clap,groan,sit}-home.png`, `s-crowd-closeup_cue-stand-away.png`: each hook.
  - `s-td-moment.png`: the scoring side standing and cheering.
- **Gap:** in the steep upper deck, shins came out in front of the
  chair backs one row down. A 0.20 m forward shift put knees past the tread
  edge. It is now 0.10 m, and cards 0.11 m. Verified in `crowd-iter10/s-crowd-closeup_upper.png`: fans sit back in their chairs. One fan at the deck-edge aisle still shows shoes below the pans.

## Round 2 (the art director's critique of `crowd-iter9`)

Before: `crowd-iter9/s-crowd-closeup.png`, `s-td-moment.png`, `crowd-iter10/s-crowd-closeup_upper.png`.

### Pass 1: `crowd-r2-1/` and `crowd-r2-2/`

- **Faceted mannequins:** weighted smooth normals, LOD0 at about 2,400
  triangles, and warm AO baked from the full body (strength 0.6, cavities
  toward red-brown). The review render (`review/kit_tinted_sit.png`) reads
  soft. In the headset shots silhouettes still facet within about 1.5 m.
- **Stiff T-arms:** the cheer and clap slots are filled per fan from
  families of real gestures: V with bent elbows, fists pumping, clapping
  overhead, a high-five lean, leaning over the row, one arm punching.
  `crowd-r2-2/s-td-moment.png` shows a section celebrating in different
  ways (`review/kit_tinted_cheer_a.png`).
- **Blank faces:** 9× the head texels, brow sockets, a nose shadow, heavier
  brows, and a mouth disc. The cheer pose drops it open (2.6×), clapping
  opens it slightly, and at rest it is a slit.
- **Props:** towels drape and swing three ways, and signs are 22 mm boards
  with block lettering. Beanies no longer cover the eyes.
- **Dark sections:** the crowd's own albedo. Chips are solved to about 0.16
  relative luminance for white text; times 0.86 cloth and the shade, that
  came to about 0.12 linear. Club colours now lift into `clubLuma` (sRGB
  luma 0.5–0.7) before tinting. Lighting unchanged.
- **Shoes below the pans:** the tread in front of those seats is cut
  (vomitory or accessible). The fans are at the right height, so this was
  routed to Bowl.
- **Budget:** rings rebalanced (16 LOD0, 32 LOD1, 150 LOD2, and never a card
  within 5.5 yd). Measured 141.3k triangles, 36 parts.
- **Gap:** white blotches on some shirts and pale fingertips. Decimation moves
  elbows and fists further than the 4 cm bake reach, so those texels were
  never baked. Reach widened to 10 cm in pass 2.

### Pass 2: `crowd-r2-4/`, on `aba0503` (Bowl's tread fix, the cues on the blackboard)

- **Near fans went black under the field goal's purple strobe:** the
  crowd's fault, not Lighting's. The non-scoring side's lit meshes were
  multiplied by the cards' 0.3 dim. Now meshes dim to 0.75
  (`tint.meshDim`) and cards to 0.55. `s-td-moment-t4-fg.png` reads.
- **Khaki-grey far crowd:** the club luma lift turns near fans and cards
  club blue (`s-crowd-closeup.png`). The far stands still read tan at t0.5,
  from khaki trousers on 1 fan in 5 and warm AO. Trousers move to denim and
  black, neutralShare drops to 0.24 and desaturation to 0–0.2 (pass 3).
- **Seats on stilts over a void:** with Bowl's `2daced9` merged, the
  club-seat close-up shows tread under the seats.
- **Touchdown stands then sits:** two causes.
  - The scene's section tint ends with the moment (`momentSeconds` 6). The
    scoring side now keeps celebrating, and each group sits at its own
    point over `settleSeconds` 2.5–5 s.
  - At t0.5 and t8.5 the side stood with arms down. Moments now calls
    `shared.stand` on a touchdown, and that cue replaced the celebration.
    Stand and clap cues no longer override a side that is already
    celebrating.
- **Cues:** on `StadiumShared.crowdCues` (the director's move). A test holds
  them to the stadium's own blackboard.

### Passes 3-6: `crowd-r2-6` to `crowd-r2-11`, on `e16a834`

- **Far stands dark khaki:**
  - The dressed impostor atlas was premultiplied, so every transparent texel
    was black and far mips averaged figures with it. Colour now pads six
    texels out, as straight alpha.
  - Cards 100 m from the lamps sat about four stops under the field, so they
    now emit a chip-coloured flood spill (`impostor.floodFill` 0.06). A
    textured emissive read grey, and 0.45 went white.
  - Result: `s-bowl-wide.png` reads Chicago blue and Minnesota purple.
- **Fan shadows:** off (`castShadows` false), as a cost fix. The black
  treads were Bowl's geometry facing away from the floods.
- **Floating near fans:** measured with `tools/blender/crowd/seat_fit.py`
  against Bowl's pan.
  - The lift was `pelvisMetres * (1 - scale)`, which only equals the target
    when the token is 0.52, so hips sank 4.7 cm into the pan and thighs rode
    over the armrests.
  - The lift is now `pelvisMetres - kitPelvisMetres * scale`. At 0.565, hips
    meet the pan within ±3 cm for every build.
  - Shots: `s-crowd-closeup-{club,clubLevel,upper}.png`.
- **Touchdown:** the celebration holds at 0.5, 5.1 and 8.5 s
  (`s-td-moment-t*.png`), then settles over 2.5–5 s.
- **Budget:** 141.7k triangles, 36 draw parts, 0 shadow casters. 44,855 fans:
  16 LOD0, 32 LOD1, 150 LOD2, 44,657 cards.
- **Gates:** `make test` 530, `verify_scene`, `contrast_check`.
