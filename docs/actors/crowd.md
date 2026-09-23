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

## Round 3 (MakeHuman bodies, and a dress in two seconds)

Before: `integration-10/s-crowd-closeup{,-clubLevel,-upper}.png`, `s-bowl-wide.png`, `s-td-moment-t*.png`, on `ab6d05a`.

### Pass 1: the dress, `crowd-r3-1` to `crowd-r3-3`

- **25 s to dress a crowd:** measured 24.8–26.0 s at integration-10, and 33–35 s on the perf branch. The detached task was
  not waiting on the main actor; `tint` itself was slow. Under the harness's -Onone build a per-texel loop of SIMD
  values, closures and `CGContext` draws cost that, and six `straightPadded` passes over the 6 MP card atlas were
  most of it.
- **Fix:**
  - Padding is not per matchup, so it moved offline: `tools/blender/crowd/pad_atlas.py` grows each figure's colour
    24 texels into the transparent albedo (12 in the mask), run by `build.py` after the impostors.
  - `CrowdKit.pixels` reads the decoded PNG's bytes in place, no copy. visionOS's ImageIO hands an alpha PNG over
    premultiplied (macOS hands the same file straight), so padding does not survive decode there: `tint` fills a
    card's transparent texels with that person's own tinted mean instead, which is what the mips need.
  - `tint` is scalar Float over raw buffers, the base copy is one `update(from:)` a row, and people are composed
    in parallel with `concurrentPerform`: each texel belongs to one person's rect or half-cell, so writes never overlap.
- **Measured:** `crowd dress composed in 1.97–2.42 s` (decode 0.01–0.30, tint 1.63–2.05, textures 0.07), in the
  Debug harness on the simulator. Release on device will be faster; the log line now splits the four stages.

### Pass 2: MakeHuman fans in the kit, `crowd-r3-4`

- **Integrated:** `build.py` builds MPFB bodies through `mh.assemble` (`--scripted` keeps the old procedural fans).
  The whole kit rebuilds in 17 min.
- **Heights:** MPFB's height macro is gender-dependent. The body is probed and scaled to the cast's height about the floor,
  rig included. A test holds every fan to the cast.
- **Hats:** `fan.hat` built at k = 1 and stretched per axis onto the measured cranium (temples, front and back of the
  skull, brows to scalp). Before, they floated a hand's width high and a size too big.
- **Scarves:** a new loop from the body's own cross-section under the neck, dipping to the breastbone and kept 8.5 cm
  under the chin; tails drape off whatever the fan wears. MakeHuman's neck bone sits 2 cm under the chin, and the old
  scarf covered faces.
- **Props:** turned from the kit's hanging-hand frame into the right wrist's, anchored at the fist, not the open fingertip.
- **Suits:** `female_sportsuit01` (crop top) and `female_casualsuit02` (dress) are gone; women wear
  `female_casualsuit01` and `male_casualsuit02/04`. A test fails if either returns.
- **Faces:** MakeHuman eyes and `teeth_base`, with jaw and finger posing. The scripted mouth disc is only for scripted fans.
- **Twins:** no fan repeats within four seats along a row or in the three seats directly ahead. Seated near-ring fans
  alternate `sit` and `sit_b`, so a row is not one posture copied.
- **Licences:** `assets/LICENSES.md` records the MakeHuman pack, its sha256 and every asset a fan wears; the manifest
  lists each fan's assets and a test matches them.
- **Budget:** 144.3k triangles, 36 draw parts, 0 shadow casters (LOD0 2,400, LOD1 650, LOD2 250; rings unchanged at 16/32/150).
  44,892 fans.
- **Gates:** `make test` 545 OK, `verify_scene` 15 scenes and 59,515 assertions OK, `contrast_check` OK, xcodebuild no new warnings.

| Shot | Worst thing left |
|---|---|
| `crowd-r3-4/s-crowd-closeup.png` | Bake smears: pale blotches on some faces and square patches on shirts where the LOD0 UV repack bled across islands. |
| `crowd-r3-4/s-crowd-closeup-clubLevel.png` | Signs and foam fingers still read as flat grey-brown boards at 3 m. |
| `crowd-r3-4/s-crowd-closeup-upper.png` | The nearest fan's hands float over the rail in front instead of resting on their thighs. |
| `crowd-r3-4/s-bowl-wide.png` | Unchanged from integration-10: far stands read, but the near celebrating row is still low-poly at the frame edge. |
| `crowd-r3-4/s-td-moment-t0.5.png`, `-t5.1.png` | Cheering arms read well; the raised foam fingers are cartoon-sized next to MakeHuman hands. |

## Round 4 (backwards, robotic, blocky)

From the user, on integration-11: "fans are backwards and robotic and blocky".
Before: `docs/lookdev/integration-11/s-redzone-trails.png`, `s-td-moment-t5.1.png`, `s-crowd-closeup-sideline.png`.

### Backwards: the USD export axis

**Every near fan on the headset sat facing their own chair back, and had since the kit's first
frozen pose meshes.** `export_pose_meshes` wrote the USDZ with
`export_global_forward_selection="Z"`. For Blender's USD exporter that puts a fan's front
(Blender -Y) on **-Z**: the stage carries `xformOp:rotateXYZ = (90, 0, 180)`, and measuring a
marker vertex through it lands -Y at (0, 0, -1). The glTF twin uses `export_yup`, which puts it
on **+Z**, which is what the manifest promises and what `CrowdPoseMesh.placed` assumes when it
turns +Z onto a seat's facing. So the web and Android ports were right and the headset was
backwards. Measured on the shipped kit through pxr: `lod0_poses.usdz` faced -Z.

Round 3 gave the fans faces, which is why it became obvious then; the earlier scripted
mannequins hid it. Two of its logged "worst things" were this bug seen from the side: fans
perched above the pan with their legs over the row in front (a fan sat 180° round is sitting on
the front lip of their chair) and hands floating over the rail.

- **Fixed** at the export: `USD_FORWARD = "NEGATIVE_Z"` for the pose meshes and the skinned fans.
- **Measured, not assumed:** `build.py` reopens every exported file (USD through `pxr`, glTF
  through the stdlib reader in `glb.py`) and records the side its fans face in
  `manifest.json.forward`; the build fails if any file is not +Z. The cue is a seated fan's feet
  and shins against their torso, which survives LOD2's 250 triangles - standing toes do not, and
  reading those called 5 of 24 LOD2 fans backwards when they were not.
- **Held by three checks, at three levels:** `tests/test_crowd_kit.py` reads the glTF bytes for
  every fan on every LOD; it also holds the manifest's measured USD axis and the export setting.
  `apple/verify_scene.swift` places every seat through `CrowdFacing` - the one definition the
  actor also places with - and fails if a fan would look away from the field; with the kit's
  forward flipped it reports 163,950 failures. The app measures the kit it loaded and logs
  `[stadium] crowd kit lod0 faces +Z`, or an error naming the offsets.
- **Cards were never wrong:** the impostor atlas is rendered in Blender with view 0 facing the
  camera, and the runtime picks view 0 for a fan facing the wearer. Only the mesh rings flipped.

### Robotic

Everything stays group-level: a near group still swaps one merged mesh.

- **Per fan inside the slot.** Each slot a group can show is a merged mesh in which every fan
  wears a pose drawn by their own seat from `visual.crowd.nearMix`. Going between `sit` and
  `sit_b` draws from one stream, so about a third of a group changes and the rest hold: a row
  breathes instead of blinking.
- **Real postures.** `poses.py` grew seated and standing families - hands on thighs, a forearm on
  the armrest, elbows on knees leaning in, hands clasped in the lap, leaning back, weight on one
  hip, hands on hips, arms folded - reached with a two-bone solve (`mh.solve_arm`) onto targets
  measured off the posed body, not by hand-set angles. Fans holding something hold it up.
- **Heads follow the play.** New near-only stills `sit_look_l` / `sit_look_r` (chest, neck and
  head turned 38°, `mh.twist_upper_body`). A group turns when the ball is more than
  `lookYards` across it. Chatting pairs turn to each other at `chatShare`.
- **The rise is staggered and ripples.** A score reaches a group after
  `rippleSeconds x distance / rippleYards` from where the play was, then it goes through `rise_1`
  (the quickest 40% half up) and `rise_2` (the first cheering) before the celebration.
  `apple/verify_crowd.swift` sweeps it: 337,996 checks, and the scored-on side still never
  celebrates.

### Blocky

- **Shading, not silhouette, was most of it.** Every frozen pose mesh now takes custom split
  normals from the full-resolution body in the same pose (`transfer_normals`).
- **The square patches were the UV layout.** Smart-projecting a decimated 3,000-triangle body cut
  it into thousands of islands a few texels wide; at shipped size every texel sat by a seam, so
  mips mixed islands (salmon squares on jeans, pale blotches on faces). MakeHuman's parts already
  have clean layouts, so each part's own UVs now go into a fixed rectangle of the fan's cell
  (`PART_RECTS`), laid out before decimation so every LOD inherits it. Only the fitted hat, scarf
  and prop are projected. Bake margin is `EXTEND` at 80 px.
- **Hair.** MakeHuman hair is alpha cards and the stadium draws fans opaque, so clear texels now
  bake the shadowed depth of the hair instead of the texture under zero alpha (an orange lattice).
- **Props.** A foam finger is a rounded mitt the hand goes into with a raised finger, about 45 cm
  overall; a sign is 56 x 40 cm poster board, lettered in its own frame before it is placed.
- **Fewer, better near meshes,** inside the same 100k the crowd keeps for meshes beside its 50k of
  cards: LOD0 2400 -> 3000 triangles (14 of them, was 16), LOD1 650 -> 900 (24, was 32), LOD2 250
  (130, was 150). 96.1k, was 96.7k.
- **Measured and rejected:** protecting the face and hands with a decimate vertex group. Blender's
  group is all or nothing - protected vertices never collapse at any factor, and the rest
  collapsed so hard the head fell to 25 triangles. The head already keeps about half of LOD0.

**Cost:** `lod0_poses.usdz` is 29 MB (was 17): nine poses at 3,000 triangles rather than six at
2,400. LOD1 10 MB, LOD2 3.6 MB.

### Shot on the headset: `crowd-r4`

Built and shot after the Xcode 27 licence was accepted (the round-4 commit above was written
blind; `CrowdActor.swift` compiled first time, and the build carries no warning the
integration-11 baseline does not).

**Facing, the thing the user saw.** Rows in front show backs of heads from every seat:

| Shot | Verdict |
|---|---|
| `crowd-r4/s-crowd-closeup.png` (club) | backs and profiles, all turned to the field |
| `crowd-r4/s-crowd-closeup-clubLevel.png` | backs; the row below reads shoulders-and-cap |
| `crowd-r4/s-crowd-closeup-upper.png` | backs, legs under the chairs, nobody perched on the pan lip |
| `crowd-r4/s-crowd-closeup-endzone.png` | backs, turned in toward the goal line |
| `crowd-r4/s-crowd-closeup-sideline.png` | profiles to the field; this is the frame that showed a wall of faces at integration-11 |
| `crowd-r4/s-crowd-closeup-field.png` | no near fans at field level (correct: the seats are above and behind) |
| `crowd-r4/s-crowd-closeup-pressBox.png` | no near fans (behind glass) |
| `crowd-r4/s-redzone-trails.png` | backs; the integration-11 counterpart was the user's evidence |

The app measures the kit it loads and logs `[stadium] crowd kit lod0/lod1/lod2 faces +Z (24 fans)`.

**In motion.** `s-td-moment-t0.5.png` the near side is up, arms and props in a dozen different
gestures; `-t5.1.png` still celebrating, mixed cheering and clapping; `-t8.5.png` settled back
into the seats with a few still clapping. Idle rows read as people: leaning back, forearms on
armrests, elbows on knees, hands on thighs, heads turned to the play and to each other.

**A first run's `t5.1` caught the near rows seated.** Not a fault: the harness times its frames
from when the moment appears in the scene, that run drifted about 8 seconds of game clock later
(12:32 against 12:40 on the board), and it landed inside the settle, where each group sits at its
own point over `settleSeconds`. Re-shot with the slot decisions logged: `look_r` -> `rise_1` ->
`rise_2` -> `cheer_a` -> `clap_b` -> `cheer_a`, `scoring true` throughout, every group holding all
10 slot meshes.

**Budget** (`-stadiumStats`, stadium): crowd **143,728 triangles, 36 draw parts**, 0 shadow
casters, against 144,344 and 36 at integration-11. Stadium total 239,550 triangles, 97 parts,
~67 MB of textures. Crowd build 3.4-3.5 s (integration-11: 2.8-3.8 s); the dress composes in
1.35-1.42 s (integration-11: 1.5-2.3 s).

| Shot | Worst thing left |
|---|---|
| `crowd-r4/s-crowd-closeup.png` | The foam finger reads as a blue baton from behind: the mitt is a rounded block and the raised finger its handle. |
| `crowd-r4/s-crowd-closeup-upper.png` | Hair is still card-flat at 2-3 m now that the shading no longer hides it. |
| `crowd-r4/s-bowl-wide.png` | On a plain snap the fans along the bottom edge read as more raised arms than a first-quarter crowd would have. |
| `crowd-r4/s-td-moment-t8.5.png` | The settle drops a whole group within a second or two; it wants the same per-fan stagger the rise has. |

## Round 5 (whose crowd it is)

From the user: the fans should be "sooo accurate", and they should belong to the teams playing.
Before: `docs/lookdev/integration-12/` (crowd section). After: `docs/lookdev/crowd-r5/`.

### Whose crowd it is

Support is decided **per section, from the scene**, and the decision is clustered because that is
what a real away support looks like:

1. the scene's own `bowl.crowd.awaySection`;
2. behind the visiting bench - their sideline, between `field.props.benches` `fromX` and `toX`;
3. the upper corners on that side,

until `visual.crowd.support.visitingShare` (0.11) of the bowl's sections are the visitors'. Then
`neutralShare` (0.06) more, taken from the corners farthest from them, wear neither club: a third
dress composed from the scene's own `crowd.neutral` and `crowd.dark`, at quarter size because
those sections are the farthest seats in the building. Measured in the app: **home 85%, visiting
9%, neutral 5%** of the seats taken.

Nothing names a club. Home and away chips, the away section and the bench range all come from the
scene, so the same code dresses any fixture, and a test fails if an abbreviation appears in it.

**What could not be done, and why.** Support is per section rather than per seat because a group
of fans shares one texture: a lone visitor in a home section would cost another draw part, and at
45 seats the budget has room for about nine. So there are no scattered strays, only clusters.

### What the scene knows about the score and the clock

It knows `status.homeScore`, `awayScore`, `period`, `clock` ("12:40", read as minutes and
seconds) and `state`, and the crowd uses all of them. It carries **no attendance**, so nothing is
inferred about how full the building should be beyond the tokens. A game decided by
`emptySeats.blowout.margin` (17) once the fourth quarter is inside ten minutes empties the upper
deck to 55% and the lower to 88%; the corners and the end zones thin out at every score. A test
holds the crowd to reading only fields `SceneSpec.Status` actually carries.

### Reactions, within what the feed knows

- **Third down**: the defending side rises (as before), and the side whose own offence is at the
  line now goes quiet - `hushOwnOffence`. Nothing idle outranks the hush; a moment and a cue still do.
- **A visiting score** is real but outnumbered: `visitorCelebration` 0.55 thins their celebration
  to standing and clapping between the cheers. The scored-on side still never celebrates.
- **A neutral section** watches both clubs' moments from its seats.
- **The wave** now needs a late or decided game: a 0-0 first quarter was full of raised arms.
- **The settle** comes down in stages (`settle_1`, `settle_2`), the way the rise goes up.

`apple/verify_crowd.swift` sweeps all of it: **346,120 checks**.

### Round 4's leftovers

- **Shoes over the tread edge** (clubLevel, endzone): seated legs are now a two-bone solve onto an
  ankle target `chair.ankleForwardMetres` (0.10 m) in front of the chair, which keeps the whole shoe
  inside Bowl's `seating.feetDepth` of tread. Before, only the ankle's height was solved and the
  shin was tipped forward whenever it could not reach.
- **Hair flat at 2-3 m**: MakeHuman's alpha cards get 6 mm of thickness.
- **The foam finger as a blue baton**: rebuilt as a hand - a 26 cm mitt with a thumb stuck out and a
  shorter, fatter finger offset from the middle.
- **More raised arms than a first quarter would have**: the wave gate above, and `idleStandShare`
  (0.06 early, 0.16 from the third quarter).
- **The settle dropping a group at once**: staged, as above.

**A LOD floor the props set.** Hair thickness and the rebuilt props are many small closed shells,
and a collapse decimate cannot take a shell under four triangles: LOD2 landed at 250-720 and the
ring left the budget. `weld_parts` welds hair, props, hats and scarves before each lower LOD is
decimated (1.5 cm at LOD1, 9 cm at LOD2, where the fan is 7-13 m away). Back to 3000/900/250.

**The forward probe.** Round 4 proved the export axis from anatomy; round 5's tucked feet broke
that cue, and at 250 triangles a shoe is a blob anyway. `build.py` now exports a one-triangle
marker beside the fans whose apex points where they face, measures it in every file, and fails the
build if it is not +Z. The app measures the same marker and logs
`[stadium] crowd kit lod0 faces +Z (probe apex z +0.053)`. Nothing looks it up as a pose, so it is
never drawn.

**Budget**: 135,998-136,330 triangles, 38 draw parts (integration-12: 143,728 and 36), against
150k and 45. The crowd dress takes 2.36-2.48 s, up from 1.44-1.52: the third dress costs about
0.9 s of tint even at a quarter size.

| Shot | Worst thing left |
|---|---|
| `crowd-r5/s-crowd-closeup-sideline.png` | Held up, the foam finger still reads as a blue bar end-on; the hand shape only tells from the side. |
| `crowd-r5/s-bowl-wide.png` | The empty seats are scattered evenly inside a section; real ones come in blocks and along the aisles. |
| `crowd-r5/s-td-moment-p7-visitors.png` | The visiting section brightens as a whole rectangle, because the tint is per group. |
| `crowd-r5/s-crowd-closeup-upper.png` | Hair has thickness now but still reads as cards rather than volume at 2-3 m. |
| Dress time | 2.4 s, up 0.9 s on round 4: a third dress is composed even when its sections are all cards. |

## Round 6 (the visiting wedge)

From the user, on integration-13: the visiting support reads as a painted purple wedge filling
one side of the bowl. Before: `docs/lookdev/integration-13/s-bowl-wide.png`. After:
`docs/lookdev/crowd-r6/`.

### Measured, not eyeballed

`tools/crowd_pixels.py` (stdlib: a small PNG reader) scores a wide frame's stand pixels against
the two crowd chips the scene carries, counting pixels between them as neither club's.

| | seats | stand pixels |
|---|---|---|
| integration-12 | 9% | 35.0% |
| integration-13 | 9% | 26.1% |
| crowd-r6 | 4% | 20.1% |

### What broke the silhouette

The wedge was a granularity problem: support was decided per **section**, and a section is a
radial wedge from the front row to the back of its tier, so one verdict painted a rectangle.

`CrowdSupport.supportBySection` now returns a *pull* per section, and `supportAt` draws each seat
against it on a grain of `blockRows` x `blockSeats` (3 x 4): `coreProbability` 0.9 inside the
block, `edgeProbability` 0.28 at its edge, thinning as it climbs the tier (`tailRows` 0.62). Home
shirts therefore sit inside the visiting block and the boundary is ragged.

**This costs no draw parts.** A group of fans shares one texture, so the cost of a mixture is the
number of (slice, support, variant) groups it creates, not the number of mixed seats: seats of
different support inside one slice simply land in the group that already exists for that slice.
What does cost parts is a *new* slice carrying visitors, which is why a stray visitor in an
unpulled section is refused - the first pass allowed them and took the crowd to 45 parts, the
ceiling. At 36 parts now, against 38 at integration-13.

### A section that brightens as one rectangle

The tint each group takes now rises over `tintRiseSeconds` (0.9) after that group's own ripple
delay, and settles a little away from its neighbours' (`tintJitter` 0.06), so a support lights up
the way it rises: a few blocks first.

### Empty seats

Empties come in blocks of `blockRows` x `blockSeats` (4 x 6) at `blockEmptiness` (0.78), and the
last two seats of every run are emptier (`runEndFactor` 0.85) - both supports, everywhere, not
only in the visiting block. 30,651 of 49,982 seats taken (61%).

### The close club pairing: what the crowd can honestly do about it

At Philadelphia the chips are teal (`#0B798E`) and blue (`#116CD9`), about 0.08 apart in hue, and
integration-13 found them hard to tell apart at distance. **The crowd cannot honestly fix this.**
The chips come from the scene, they are already solved for legibility against white text, and a
colour that separated them would be a colour neither club wears - the same rule that forbids
inventing a club's colours forbids inventing a contrast between two.

Measured, with pixels whose hue sits within 0.06 of both chips counted as neither: **19.4%** of the
Philadelphia frame's stand pixels belong to neither club, against 10.7% for Chicago-Minnesota,
whose chips are 0.13 apart. The same measure calls 68.5% of Philadelphia's attributable stand
pixels "visiting", which is plainly wrong for a 4%-of-seats away support: a hue test cannot
separate those two clubs, and neither can an eye at that distance.

What the crowd does instead is positional, and it is what a real ground does: the visitors are one
block behind their own bench with a tail into the corner, so they read as *the other club* by
where they sit even when the hue will not carry it. Pairwise separation of two close chips would
have to happen where the chips are solved - `fantasyedge/scene.py`'s palette, which belongs to the
director and to `actor/field-identity` - and it is recorded here as their call, not taken here.

### Budget and cost

133,138-133,481 triangles, 36 draw parts, against 150k and 45. The dress measured 6.94-8.66 s in
these runs, against 1.7-2.96 s at integration-13 - but the machine was carrying a load average of
348-437 from the parallel agents while these shots were taken, and the dress does the same six
tints it did at round 5 (home, away and neutral, fan and card). It wants re-measuring on a quiet
machine before anyone reads a regression into it.

### The support decision is now pure and checked

It decides what the wide frame looks like, so it moved out of `CrowdActor` into `CrowdSupport.swift`
with no RealityKit, and `apple/verify_crowd_support.swift` runs it over every sample scene:
**98,715 checks** that every visiting seat is on the visitors' side, that neither club's colours sit
within 14 yd of a wearer's seat preset, that no section is unanimous, and that taken seats come in
runs rather than singly. It caught a real fault while it was being written: the unaligned were
ranked into upper *midfield* sections, which put a violet block a row in front of the wearer.

| Shot | Worst thing left |
|---|---|
| `crowd-r6/s-bowl-wide.png` | The visiting core sits in the lower bowl behind the bench, where the near rows hide it; what the wide frame shows is mostly the thin upper tail. |
| `crowd-r6/s-bowl-wide-phi.png` | Teal and blue still read as one crowd at distance, and nothing here can honestly change that. |
| `crowd-r6/s-td-moment-p7-visitors.png` | The blocks brighten in their own time, but every block still reaches the same final brightness. |
| Dress time | 6.9-8.7 s under load; needs a quiet-machine number. |
| `crowd-r6/s-crowd-closeup-pressBox.png` | Still Bowl's featureless beige desk, unchanged since integration-11. |

## Round 7 (hair, and three refinements)

A refinement pass on my own list and the checkpoints'. Before:
`docs/lookdev/integration-14/`. After: `docs/lookdev/crowd-r7/`.

### 1. Hair, in order of what is most wrong with a near fan

MakeHuman's hair is single-sided alpha cards. Drawn opaque and decimated to a crowd's budget they
read as a stack of flat slabs at 2-3 m, which has been the oldest complaint against a near fan
since round 4; round 5's 6 mm of thickness only made the slabs thicker.

**The fix is to close the cards into a solid.** `mh.hair_shell` thickens each hairstyle to 16 mm,
voxel-remeshes it at 6 mm - half the thickness, because a voxel wider than the hair erases it, and
an 11 mm voxel deleted an afro outright - smooths the result and trims it to 900 triangles. The
style each CC0 asset carries survives: a fringe is a fringe, an afro is a dome. Nothing is
invented; the shape is the one MakeHuman shipped.

Three things the shell needs that the cards did not:

- **It has no UVs**, so `build.py` projects it into the cell like the fitted hat and scarf, and
  bakes the cards' own colour onto it from the full-resolution copy. The atlas rectangles were
  re-laid to give the projected parts room.
- **It must be built after the fit and the height scale are baked.** Remeshed before them it
  freezes at the asset's unfitted size and floats above the head, which is exactly what the first
  attempt did.
- **A remesh throws the fitted weights away**, and an unweighted part stays at the rest pose while
  its fan sits down - hair hovering where the standing head used to be. The shell is weighted to
  the head bone, as the hat already was.

**Cost:** 135,643-136,289 triangles against 133,497, so about 2.4k for the hair, inside the 150k
budget with 14k still spare. No draw parts (the shell is part of the same merged mesh), and no
dress time (it is geometry, not texture): 2.18-2.45 s against 2.39-3.67 s.

### 2. The blocks all reached the same brightness

The staggered rise arrived in turn and then levelled off, so the moment ended on the rectangle it
had avoided. Each group now also *takes its own time* (`tintRiseSpread` 0.7 of `tintRiseSeconds`)
and settles at its own brightness (`tintJitter` 0.14, was 0.06).

### 3. Empty seats scattered inside a block

Round 6 thinned whole blocks, but evenly inside them, which still read as scatter. A thinned block
now empties from its middle outwards (`aislePull`): the seats by a gangway are the last a stand
gives up, so what is left is a ragged edge along the aisle. Judged done at bowl-wide distance -
the stands carry patches and gangway bands where integration-14 carried even speckle.

### 4. The foam finger as a bar

Seen from the next seat along a real foam finger *is* a bar - that part was honest. What was not
was the silhouette: a plain rectangle. The mitt now tapers toward the wrist and deepens at the
knuckles, and the thumb stands out of the mitt's face as well as its side, so the edge-on shape
has a notch and a taper.

### Machine

Three actor agents were building in parallel throughout. Load averages ran 592-638 at times, and
two shoot attempts died in the harness's red-zone scan, whose client timeout is a fixed 10 s: the
API could not answer in time. The frames here were taken in a window where the one-minute average
was 11, with the simulator shut down between attempts.

| Shot | Worst thing left |
|---|---|
| `crowd-r7/s-crowd-closeup.png` | The hair shell reads as a single mass: a hairline parting and a few strands at the edge would sell it at 2 m, and it is now the head's flattest surface. |
| `crowd-r7/s-bowl-wide.png` | The empty patches are the right shape but the same shade as a shadowed seat, so they read as shadow at this distance rather than as empty. |
| `crowd-r7/s-td-moment-p7-visitors.png` | The visiting block brightens well, but the home sections around it do not dim, so the contrast comes entirely from one side. |
| `crowd-r7/s-crowd-closeup-pressBox.png` | Still Bowl's beige mass, identified at integration-14 and not the crowd's. |
| Dress time | 2.2-2.5 s is three quarters tint, and the tint is still a scalar loop at -Onone. |

## Round 8 (no flat fan among solid ones)

Experience found flat card fans standing among solid mesh fans at six to eight yards, the field
showing through them, and proved whose they were five ways rather than guessing
(`docs/lookdev/experience-r7/crowd-cards-near-crop.png`). Before and after:
`docs/lookdev/crowd-r8/`.

### The rule that was inverted

`visual.crowd.rings` says no card within `minCardYards` and caps meshes at 14/24/130. **The caps
decided mesh against card; the distance rule only tidied up inside 5.5 yd.** A row seen end-on
holds far more fans inside the mesh radius than the caps allow - 375 within 13 yd at the sideline
seat, 360 at the club seat - so the overflow became cards wherever it happened to stand, including
among solid fans a few yards away.

### What I chose, and why

Covering a whole end-on row needs 94k triangles of lod2 alone, six times the headroom, so raising
the caps far enough was never affordable. Instead **the distance beats the count**: the nearest
`lod0Max + lod1Max + lod2Max` fans are meshes and everyone beyond is a card, so the boundary is a
circle and no card can stand nearer than a mesh fan. The dither still ragged-edges the seams
between mesh rings, where it costs nothing; it no longer decides whether a fan is flat.

`lod2Max` goes 130 → 145, which is exactly what the budget allows at 250 triangles a lod2 fan
(14 x 3000 + 24 x 900 + 145 x 250 + 50,000 of cards = 150,000). Measured cost: **140,132-140,145
triangles against 136,412-136,419**, 36 draw parts unchanged, and the dress *fell* to 1.64-2.46 s
from 2.03-2.71 s (no texture changed; that is the machine being quiet). The app logs what the
circle reached: `meshes out to 7.6 yd, then cards`.

### And the second half of it

A card that blends is a fan you can see the field through. The card material was alpha-tested but
never told not to blend, so `mat.blending = .opaque` is now explicit. That costs nothing and is
what actually removes the transparency; the ordering fix is what removes the interleaving. Both
are held by tests: one reads the ring loop and fails if the dither can decide mesh against card,
one fails if the card material loses either line.

### What I did not take from my round-7 list

- **The hair shell still reads as one mass.** A parting and a few edge strands need a kit rebuild
  and a reshoot; the card defect had evidence and a user behind it, and I spent the quiet window
  on measuring and fixing that properly instead.
- **Empty patches still read as shadow** at bowl-wide distance: right shape, wrong value. The
  value is Bowl's seat colour showing through, so it wants a conversation with that actor rather
  than a crowd-side fudge.
- **The home sections do dim on a visiting score** (`tint.dim` 0.55 for cards): integration-14
  rated that frame a 4 and I had no evidence the number is wrong, so I left it rather than fiddle.

| Shot | Worst thing left |
|---|---|
| `crowd-r8/s-crowd-closeup-sideline.png` | The mesh circle reaches 7.6 yd, so cards begin closer than they should on a row seen end-on. A cheaper lod3 tier at about 120 triangles would roughly double the radius for the same budget; that is the next real move. |
| `crowd-r8/s-crowd-closeup.png` | Hair is volume now but one mass: no parting, no edge strands. |
| `crowd-r8/s-bowl-wide.png` | Empty patches read as shadow rather than as empty. |
| `crowd-r8/s-crowd-closeup-pressBox.png` | Bowl's beige mass, identified at integration-14 and not the crowd's. |

## Round 9 (a club's own colour, on the people who wear it)

A club wore two colours: the field painted its **stated** colour (`teams.*.color`) and the crowd
dressed from `bowl.crowd`'s chip, which `scene.py` solves so white text clears 4.5:1 on a panel.
Same club, two colours in one frame. The director's ruling is that the crowd's lift is legitimate
but must come from the club's own colour, not from a panel chip. Before and after:
`docs/lookdev/crowd-r9/`.

What the chips actually did to three clubs, measured off the served scene:

| club | states | chip it wore | now wears |
|---|---|---|---|
| Philadelphia | `#06424D` midnight green | `#0B798E` bright teal | `#06424D`, unchanged |
| Pittsburgh | `#101820` black | `#4C7399` mid blue | `#213242` |
| Las Vegas | `#000000` black | `#6F6F6F` mid grey | `#424242` charcoal |

### What the crowd is allowed to move

One thing: HSV value, which is r, g and b scaled together. That cannot shift a hue and cannot
touch saturation, so a club's colour stays the club's. `CrowdCloth.of` is the whole of it, and it
lives in `CrowdLook.swift` so `verify_scene` can sweep it on every sample scene: every club is
worn at its own value or at the floor, never lighter than both, and each channel keeps its ratio
to the colour's value within 2e-3.

Why a lift at all is physical, not cosmetic, and the code says so: paint on grass is one flat
plane and returns one radiance under the floods, so it reads as dark as the ink. A stand is
thousands of separate fabric surfaces at every angle, threaded with hats, sleeves, forearms,
faces and the gaps between people, so the same dye returns a spread of radiances. Black fabric
under stadium light reads charcoal; black paint on wet grass reads black. Both are true at once.

### The floor, measured

Sweeping `visual.crowd.clubValue.floor` needs no rebuild - `FANTASYEDGE_TOKENS` points the API at
another token file and the app dresses from the scene it is served. The subject is a bowl-wide
frame of two black clubs, with `neutralShare` set to 0 for the sweep so the club's own cloth is
the only thing carrying the stand, which is what "a full stand" means. The window is a fixed
rectangle on the far upper deck (frame fractions 0.20-0.80 x 0.285-0.383), read by
`tools/crowd_pixels.py --structure`: `detail` is the mean absolute difference between
neighbouring pixels along a row, `mean` is the window's mean luma, both in 8-bit levels.

| cloth value | 0.00 | 0.15 | 0.20 | 0.25 | 0.30 | 0.35 | 0.50 | 1.00 | *no fans* |
|---|---|---|---|---|---|---|---|---|---|
| mean luma | 16.8 | 17.0 | 17.6 | 17.8 | 18.4 | 18.9 | 21.2 | 32.9 | 12.9 |
| what the cloth adds | - | +0.2 | +0.8 | +1.0 | +1.6 | +2.1 | +4.4 | +16.1 | - |
| p10 | 2.9 | 3.0 | 3.8 | 4.0 | 4.2 | 5.6 | 5.9 | 5.9 | 2.2 |
| detail | 4.28 | 4.31 | 4.30 | 4.33 | 4.35 | 4.40 | 4.71 | 7.45 | 0.99 |

**The first thing the sweep says is that the question's premise does not hold here.** A stand
dressed entirely in pure black still measures 4.28 levels of detail against an empty stand's
0.99: faces, hands, hair and the kit's pale trim carry it, so this bowl has no value at which a
full stand collapses into one shape. Reporting a floor derived from a collapse that does not
happen would have been inventing one.

What does disappear is the club. Below 0.15 the cloth adds under half an 8-bit level to its own
stand - less than the smallest step an eye finds in a dark field, so the stand is *entirely*
faces and street clothes and says nothing about who is in it. It reaches a full level at 0.25,
and the darkest tenth of the stand comes off the empty-seat floor (2.2) between 0.15 and 0.20.
**The floor is 0.26**, just above where a club's own colour first makes a difference that can be
found in the frame.

It lands where the physics says it should, which is the check on the number rather than the
reason for it: sRGB 0.26 is 5.5% linear reflectance, and black fabric measures 4-6%. A black club
is worn as charcoal because charcoal is what black cloth returns, not because a panel needed it.

### What each club does with it

Only a near-black club moves at all. Philadelphia (0.302), Dallas (0.361), Minnesota (0.514),
Temple's crimson (0.643) and New Orleans' old gold (0.827) are all worn exactly as stated.
Chicago (0.227) and Toledo (0.251) lift a hair; Pittsburgh (0.125) doubles; Las Vegas (0.000),
which has no hue or saturation to keep, lifts to neutral charcoal.

**Philadelphia is the honest constraint.** At 0.302 it is above the floor, so the crowd wears
midnight green exactly, and at night, next to a lit field, midnight green reads nearly black
(`s-crowd-closeup-phi-after.png`). That is the club. Lifting it would be the chip's mistake
again, in the crowd's own code.

### Whether the two supports stay tellable apart

Where the colours allow. Moving off the chips does not change this either way - `chip()` keeps
hue too - so the gaps are the clubs': Chicago/Minnesota 48.2 deg, Toledo/Temple 135.7 deg,
Philadelphia/Dallas 23.3 deg, Seattle/LA Rams 5.9 deg. Measured in the frame, the Minnesota
block on the far side reads 14.6 deg of hue from a Chicago block in the same stand
(`bowl-wide-chi-after.png`): a third of the clubs' own separation, because both blocks hold the
same neutrals, skin and navy seats. It is visible, and it is the most that distance allows.
Seattle/LA Rams at 5.9 deg cannot be told apart by anyone, and neither can two black clubs; that
was recorded in round 6 for Philadelphia/Dallas and nothing here changes it.

### Cost

None. 140,132-140,145 triangles of 150,000 and 36 draw parts of 45, both unchanged. The dress is
2.35-2.43 s against 2.28-2.43 s on the same machine in the same session - the per-fan loop lost a
branch and gained a clamp, and the difference is inside the run-to-run spread.

### Reproducing the black-club frames

The sweep and the black pairing ran against a throwaway fixture, not a committed one: a copy of
`replay_game_401772510.json` with the two clubs' colours and names replaced and its event id
changed, staged like any other. Two lines rebuild it when it is next wanted; a fake game does not
belong in `tests/fixtures`.

| Shot | Worst thing left |
|---|---|
| `crowd-r9/s-bowl-wide-black-after.png` | With two black clubs the far stands read navy, because the brightest thing left in them is `crowd.neutral`'s `#3B4B68` street clothes. Correct in principle - a black-clad stand shows its coats - but the neutral pool leans blue enough to look like a decision. |
| `crowd-r9/s-crowd-closeup-phi-after.png` | Midnight green at night reads black at two metres. The club's, not the crowd's, but it is what the frame shows. |
| `crowd-r9/s-crowd-closeup-black-after.png` | Hair is still one mass; unchanged since round 7. |
