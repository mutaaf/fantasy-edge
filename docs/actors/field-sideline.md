# Field & Sideline: critique log

Owner: the Field & Sideline specialist. Shots are taken with `tools/blender/field/shoot.sh` (which takes a simulator slot, runs `tools/lookdev.py --only field-level sideline-props redzone-trails tabletop`, then frees the slot) into `.work/shots/field-*`. Blender review renders come from `tools/blender/field/review_render.py`.

## Sources of truth
- **NFL:** 2026 Official Playing Rules, Rule 1 and the field diagram notes.
- **NCAA:** 2026 Football Rules and Interpretations, Rule 1-2 (FR-19..21).
- **Paint values:** `tools/blender/field/rules.py` quotes each one against its rule.
- **Scene geometry:** `fantasyedge/scene.py` `RULES`. Team areas and upright heights were corrected to the books in `968ce92`.

## Baseline (`.work/shots/field-before`, before any Field or Sideline work)
- **Field (26 parts, 32k triangles):** each yard number was its own system-font text mesh. The paint was quads with a generic worn mask. The stripe was only a tint. There were no hashes at the NFL width, no arrows, no limit or coaching lines, and system-font end-zone lettering.
- **Sideline (8 parts, 0.9k triangles):** box benches, tube goal posts, box pylons. The chains belonged to Broadcast.

## Iteration 1 (`field-iter1b`)
**Done:**
- **Turf:** a baked blade tile, two stripe meshes wearing the with- and against-the-mower normals, and the league's wear map over the canvas.
- **Paint:** two half-canvas distance fields cut at 0.5.
- **Lettering:** the scene's art layout in Graduate.
- **Sideline:** 20 Blender props merged per material.

**Numbers:** field 10 parts, 1.1k triangles. Sideline 19 parts, 21k triangles.

**Critique:**
- **Paint:** reads right from the club seat. Numerals, arrows and hashes are crisp, and the far numerals read from their own sideline.
- **Stripe:** almost invisible from the stands; the normals alone are too subtle under this lighting.
- **Field-level seat:** it sat behind a bench. Chrome-bright bench legs filled the frame.
- **Field-goal net:** the poles showed but the net vanished. Cutout mips fall under the threshold.
- **Sideline parts:** 19, over the 15 budget. Pads, bench backs, tents and cooler lids were four team-tinted bins per club.
- **Shot timing:** the stadium was still loading at a 9 s settle, so the harness came back black. Stadium shots now settle 25 s.

## Iteration 2 (`field-iter2`)
**Changes:**
- Benches pair off either side of a 14 yd centre gap.
- Nets blend instead of cutting out.
- Stripe tint and roughness contrast go up.
- Steel is rougher.
- All team-tinted surfaces are one bin per club.
- Cable runs are dropped.
- Contact-shadow decals follow Lighting's contract (a stand-in texture at the same spec, `actors/sideline/textures/shadow_props.png`, to repoint at `visual.lighting.response.propShadowDecal` when that merges).

(critique appended below after the shots)

**Critique (`field-iter2`):**
- Field 10 parts. Sideline 15.
- The fifty-yard line drew as two lines, and a seam crossed the border at midfield. Cause: mip generation treats the half texture as wrapping. Fixed in iteration 3 with a yard of padding.
- The net now shows, but it read as chain-link.
- End-zone paint was flat and over-saturated.

## Iteration 3 (`field-iter3`, merged with Lighting at `26e632d`)
- **Changes:** half textures padded past midfield; wear drawn over the paint; nets at 0.55 opacity; end zones at 0.8 opacity; shadows now use Lighting's `shadow_multi.png` through base-colour alpha.
- **Critique:**
  - The fifty is a single line and the seam is gone.
  - Turf reads as floodlit grass under the merged lighting.
  - The wear over the paint was too strong: the white border and the numerals turned grey-beige.
  - Tabletop sideline showed only 2 parts. LOD2 meshes export as `bench__prop_steel_002`, and the `_002` suffix hid every palette key.

## Iteration 4 (`field-iter4`)
- **Changes:** Blender's numeric suffix is stripped from mesh names (the exporter now also frees mesh datablocks between LODs); wear scaled to 0.5.
- **Numbers:**
  - Stadium: field 10 parts / 1.1k triangles; sideline 15 parts / 20.6k triangles.
  - Tabletop: field 10 / 0.95k; sideline 15 / 2.9k.
  - Field textures as the headset loads them: 38.2 MB (RGBA with mips), budget 40.
- **Remaining gaps, ranked:**
  1. Paint is flat grey-white under the floodlights, with no grass breakup. The breakup texture needs a second UV set or a Shader Graph material; neither is authorable headlessly (Lighting hit the same wall).
  2. The baked shell slices are unused on the headset. Field-level grass is a normal map, not blades.
  3. The NFL's 6 ft white border fills the lower frame of `field-level` as a clean slab.
  4. Broadcast still owns its old chains entity, so there may be two chain sets. It needs a Wave 2 check.
  5. Gestures, reduce motion and frame time are unverified: simulator stills only.

## Contract: the chains and the down box belong to Field & Sideline
- **The sideline actor draws the chain crew.** That is the chain set with its forward rod on `scene.lasers[kind=lineToGain]`, the down box at the scrimmage laser showing `status.down`, and the college ground markers. It rebuilds them when the line to gain, the scrimmage spot or the down changes (`SidelineActor.buildCrew`), on `field.props.chains.side`.
- **Broadcast must not draw physical chains, down markers or ground markers.** Its old `chains` entity in `BroadcastActor.swift` is to be removed in Wave 2.
- **Broadcast still owns the light:** the scrimmage and line-to-gain lasers, the beacon and the trails.
- **Needing the crew's position:** read it from the scene, the same way the sideline actor does. Actors never call each other.

## Iteration 5 (the coordinator's list)
- **Gates:**
  - `tools/blender/field/gates.sh` runs `verify_scene.swift` (15 scenes, 23,376 assertions) and `contrast_check.py`. Both pass.
  - The field-art types moved to `Actors/Field/FieldArtSpec.swift`, with no RealityKit, so the verifier compiles `SceneSpec.swift`.
- **NFL border slab:**
  - The paint distance field now bakes in a ragged edge of about 1 in and graded scuffs, which thin a line lightly or punch through the middle of the border.
  - Scuffs weight to the sidelines, the border, the end lines and between the hashes, averaged with their half turn so the field stays symmetric.
  - The variation map adds grime along both sidelines.
- **Lettering and paint:** a turf overlay (`paint.grass`) lies over all paint and the end-zone names, showing blades only where the turf's paint breakup is low. The lettering now draws under the wear layer. Field: 11 parts; textures as loaded 39.6 MB of 40.

## Iteration 6 (`field-iter6`, director's integration-3 notes)
- **Border wear:** scuffs cut to 12 in (below half the NFL border's 36 in) and rarer, and the sideline grime halved. `field-level` now shows a ragged edge and grass through the border, with no tearing.
- **Purple blob:** it was the pop-up medical tent, a 3 m box tinted in the away club's colour. It is dropped from the dressing (medical areas live in the tunnel), so the sideline keeps its 15 parts.
- **Goal-post net:** thinner cord (6% of each cell) and 0.2 opacity. A cutout can't survive mips at the stands' distance, so the net stays blended; in `td-moment` it now reads as a faint haze behind the far posts, not a sheet.

## Iteration 7
- **Medical tent restored.**
  - The canvas and roof are neutral white (`prop_white`) and the frame is `prop_steel`.
  - Only a 0.22 m valance and a cross on the field-facing wall wear the club's colour (`tint_team_primary`).
  - All three bins already exist, so the sideline stays at 15 parts.
- **Net: no view-dependent fade.**
  - A distance- or Fresnel-driven fade needs the view vector per fragment, which only Shader Graph provides on visionOS.
  - A baked texture or vertex colour can't depend on the view: PhysicallyBasedMaterial ignores vertex colour, and RealityKit generates the mips, so a mip-aware mask isn't possible either.
  - Left blended at 0.2 opacity with thin cord.

## Hook for Moments: the field-goal net sways
- **Writing it (Moments):** on a kick through, set `c.shared.netSway = (endX: m.anchorX, strength: 0...1, until: c.shared.time + seconds)`.
- **Reading it (Sideline):** `update` swings the net behind the end nearest `endX` about its top bar (13.2 m up), a decaying sine: `visual.sideline.sway` has `maxDegrees` 7, `frequency` 0.85 Hz and `decaySeconds` 1.2. When `until` passes, the net returns level and the hook clears itself.
- **Reduce motion:** the net holds still.
- **Geometry:** each end's net mesh is its own entity on that pivot; the poles stay in the static merge.
- **Parts:** the two nets add two. That is paid for by drawing `prop_black` with `prop_dark` (palette `alias`) and the chain crew's steel in its rods' white, so Sideline stays at 15.
- **`StadiumActor.swift`:** gains the one blackboard field `netSway`. That's a director file, so it's noted for approval.
- **Verification:** the swing hasn't been shot yet; it needs Moments' field-goal timeline to fire it.

## Shader Graph (merged `3e67602`)
- **Paint (`FieldPaint.usda`, `shaderGraph.materials.fieldPaint`):**
  - Cuts each distance field at `Edge`, pushed in and out by the turf's paint breakup (512 px, raw), sampled on the turf tile from object position.
  - Shows the turf's own colour where blades stand up through the paint.
  - Covers every marking and the end-zone lettering (`UseMask` 0).
  - The texture materials stay as the fallback, and they are what the web and Android draw.
- **Nets (`NetFresnel.usda`):** the cord mask times a view-angle falloff (`Floor`, `Power`). They're gone from `td-moment` and `sideline-props`, where they face the eye.
- **Shells (`FieldShells.usda`):**
  - Six layers of the eight baked slices in a 4×2 atlas. The layer index is read back from each fragment's height, and blades take the paint.
  - The patch fades at its edge and costs one part and 24 triangles.
  - It renders (log: "shell grass on 6 layers"), but from the field-level seat the 24×10 yd patch still reads as a darker rectangle.
  - It ships disabled (`visual.field.shells.enabled` false) until that's solved.
- **Loads:** all three load via `Entity(contentsOf:)`, each from its own `.reality`, because `StadiumShaderGraph` takes the first material in a file.
- **Parts:** Field 10 (11 with shells), Sideline 15.

## Paint albedo (`6a5640e`)
- **Albedo:** lines at 0.80 sRGB (`#CDCDC6`), border and end lines `#C4C4BA`. Border roughness is 0.98, above any grass, and its grass cut is 0.44 against 0.37 on the lines. The graph finds the border from object position (`HalfWidth`, `HalfLength`).
- **Result:** at field level (`field-sg6`) the border reads as worn off-white over grass rather than a grey slab. From the club seat (`field-sg5` `redzone-trails`) the lines sit in the turf.
- **Load path:** all three materials load via `Entity(contentsOf:)`, one material per `.reality` (Field, Shells, Sideline). They're not consolidated yet; that works unchanged under the director's by-name loader.

## Worn paint and grazing turf (integration-9 verdict)
- **Border read as speckled gravel.** The old breakup was the turf height map (0.8 mm texels, soil included) plus a speck term, sampled again 7× coarser: salt and pepper at every scale, with soil black showing through white.
- **Paint now wears in two bands** (`FieldPaint.usda`):
  - `paint_blades.png` (turf tile): blade height from the baked shell slices. A blade shows where it stands above the cut, coloured by the turf, so what comes through is whole blades, evenly spread. Border cut 0.38, lines 0.55 (lower lets more through).
  - `paint_wear.png` (6 yd tile, `make_field_maps.py -- paint_wear_maps`): broad thin patches plus cleat scuffs. It lowers the cut (`WearDepth`), thins the colour toward `ThinColor`, and pulls the edge in a little. It is what still varies at a graze, after the blade texels mip away.
  - The salt-and-pepper speck and the coarse resample are gone. The baked mask's scuffs drop from 12 in to 5 in and its edge noise to about half an inch, so edges are crisp and slightly soft.
- **Turf picked from shots: grazing sheen, not shells** (`Turf.rkassets/TurfSheen.usda`, `shaderGraph.materials.turfSheen`):
  - As the view flattens, soil gaps (low in the ORM height) fill toward `SideColor` and blades take `SheenColor`, per-stripe `visual.field.turf.stripeSheen`. The stripe tint goes on last, so mowing stripes still read at a graze. Normals and baked occlusion as before.
  - Covers the surround and both stripes, so parts are unchanged (Field 10). Tabletop keeps the PBR turf. Shells stay disabled: they cover only the near patch, and the sheen reads from every seat.
- **Shots:** `.work/shots/field-turf4` from the field, sideline and club seats.

## Paint coats the grass (border read as concrete with moss)
- **Coat, don't replace:** paint colour × `mix(1, turf luma / TurfLuma, CoatDetail)`, and the paint surface takes the turf's blade normals (`Normal`, `NormalScale`). Every blade keeps its relief in white; roughness stays above the grass.
- **Value:** lines `#DADAD3`, border `#D2D3CB` (test bands 0.80-0.88 and 0.75-0.85 sRGB). At the field seat the border measures ~5× the turf's luma (it was 2×) without clipping. The fallback colour and texture paint read the same tokens.
- **Wear:** green blade tips, not blobs. The blade mask is read on a 1.3 yd tile (`BladeYards`), so a tip survives the mips at a graze. The wear map only lowers the cut (`WearDepth` 0.3), which changes tip density in clusters; nothing goes solid green.
- **Shots:** `.work/shots/field-coat3`.

## Edge, near blades, quieter wear (integration-10a verdict: stucco)
- **Edge:** the baked mask's edge noise is down to about 0.2 in, and its scuffs to 1.5 in, and the graph's blade and wear pushes to 0.004 and 0.006. The seam is straight. Because the paint is a cutout, the soft falloff is in colour: over `EdgeFeather` inside the edge, paint runs from 55% to full over the turf.
- **Near blades:** `Detail` is the blade map loaded without mips on the turf tile. It lightens tips and darkens bases about its mean (`DetailGain`), and the blade normals strengthen to `NearNormalScale`. Both fade by |n·v| (`NearStart`..`NearEnd`), which from a field-level eye is eye height over distance, so it is a distance fade using only nodes already proven. Far away the layer is weighted to zero before missing mips could shimmer.
- **Wear:** 90 small scuffs instead of 150; `WearDepth` 0.2 and `TipStrength` 0.6, so a tip is part grass, part paint.
- **Shots:** `.work/shots/field-edge2`: field, sideline and a 1 m close-up (`round.sh … closeup`, field seat at pitch −38). The close-up shows single white blades. At 3-5 m from the field seat the border still reads as fine grain rather than blades: that is the limit of one texture sample at a graze without anisotropic filtering.

## Integration-11 polish (`docs/lookdev/integration-11-polish/`, before in `before/`)
- **The field seat's "gravel" was the NFL border, not the surround.** The seat is 4.5 yd off the sideline, so the 2 yd border fills the bottom of `field-level` and the surround is out of frame. At a graze the grain came from the paint graph's per-texel terms, not the turf-through overlay: `grassThrough` 0.85 → 0.3 changed nothing measurable, so it stays at 0.85.
  - **Changed (`shaderGraph.materials.fieldPaint`):** `NormalScale` 1.0 → 0.3, `NearNormalScale` 2.0 → 0.3, `CoatDetail` 0.5 → 0.06, `DetailGain` 1.2 → 0.15, `TipStrength` 0.6 → 0.4. Border `#D2D3CB` → `#D8D8D0`, the top of its 0.75–0.85 test band.
  - **Result:** a 1000×500 crop of the border (field seat, 4K) goes from salt-and-pepper granite to a smooth, worn off-white band.
- **Net (`visual.sideline.net`, `netFresnel.Color`):** from the end-zone seat the net was a white grid across the whole view. Cord colour `#D2D2CC` → `#A9ACA4`. `minOpacity` stays at the 0.35 floor `test_a_net_is_visible_face_on` holds; at 0.22 it read as a haze, so the floor is the next lever if the director agrees.
- **Budget:** field 10 parts / 1.1k triangles; sideline 15 / 20.8k. Tabletop field 10 / 954; sideline 15 / 2.9k. Unchanged.
- **Worst thing left:**
  - `field-level`: the border is now clean but lit a flat mid-grey from this seat. It reads as a smooth painted slab rather than bright paint on grass. The value is the floods behind the wearer, so this needs Lighting's near-field fill, not more albedo.
  - `sideline-props`: the net grid still reads over the whole field from behind the posts at its 0.35 face-on floor.
  - `redzone-trails`: the far half's turf carries a hard diagonal light-pool edge. That is Lighting's floods, not the stripe.

## The field belongs to the home club (`docs/lookdev/field-identity/`)

The user, on integration-12's `s-bowl-wide.png`: "lets make it so the endzones
and logos on the field and stuff and fans are in the teams relevant". That
frame is a Bears home game with `CHICAGO BEARS` in one end zone and
`MINNESOTA VIKINGS` in the other, painted in each club's own colour - two
clubs' fields stitched together, which no stadium has ever looked like.

**What was wrong.** `field_art` walked `(("home", home), ("away", away))` and
lettered each end with that club's name, and `FieldActor` painted each end
with that club's chip. So the visiting club owned the end zone it defended,
in its own colour, on someone else's field. The midfield ring was already the
home club's and is unchanged.

**The rule now.** Both end zones are the home club's, in its paint, and so is
the ring. `side` on an end zone still says *which end* (the side that defends
it, which the geometry needs); the new `fill` says *whose colour* it is, and
is `home` at both ends. The visiting club appears where a real stadium shows
it: in the stands (`bowl.crowd.away` and its away section), and on its own
bench, where `tint_team_primary` props are already tinted per side.

**Two ends, two words.** A club that states its name in parts letters the
nickname at the end it defends and the location at the other, the way a split
field reads - Soldier Field paints `BEARS` and `CHICAGO`. `location` and
`nickname` come from ESPN through `api.py`, which already had both and threw
them away into one `displayName`. A club that gives only one name letters it
at both ends, which is equally real (Lambeau paints `PACKERS` twice) and is
the only honest answer: splitting a display name on its last word invents
`NOTRE DAME FIGHTING` and `IRISH`. The midfield ring takes the nickname when
it is known, which is what made `BEARS` legible at midfield where
`CHICAGO BEARS` had been set small enough to fill the ring.

**One cap for both ends.** The cap was solved per name, so `MINNESOTA VIKINGS`
lettered its end at 3.72 yd while `CHICAGO BEARS` lettered the other at 5.0.
Both ends now take the smaller of the two fits, because the two ends of a real
field match.

**The mark at midfield is not anyone's.** It is a ring struck from the club's
own chip with the club's name set inside it in Graduate. No club's device is
copied, approximated or referenced, here or anywhere else on the field; the
art bible's rule holds and nothing in the repository holds a club logo.

**Contrast.** End-zone paint is the club's chip, which `chip()` solves onto a
luminance band, so white lettering clears WCAG large text on every hue - swept
round the wheel at 18³ samples, the worst is 4.96:1, which clears body text. Whether the end zone reads as a different
surface from the grass is a colour question, not a luminance one: the band
puts every club at one luminance, so a WCAG ratio is near 1 by construction
and says nothing. Measured as CIE76 dE against `turf.a` at the paint's 0.8
opacity, the hardest real case is a green club on green grass and it bottoms
out at dE 12.2 (a Jets green), against a just-noticeable difference of 2.3.

**Shots.** `s-bowl-wide.png`, `s-field-level.png`, `s-redzone-trails.png`,
`s-sideline-props.png`, `s-tabletop.png` (MIN at CHI), and `-phi` on the
second pairing (DAL at PHI) to prove it is a rule and not two clubs' luck.
`tools/lookdev.py --event` selects the fixture for that.

**Budget (`-stadiumStats`).** Field 10 parts / 770 triangles (2k, 12);
sideline 15 / 20.8k (21k, 15). Tabletop field 10 / 610, sideline 15 / 2.9k.
The field's count *fell* from integration-12's 1,114: `BEARS` and `CHICAGO`
are fewer glyphs than `CHICAGO BEARS` and `MINNESOTA VIKINGS`, and glyphs are
triangles.

**Worst thing left:**
- **The club's paint is its chip, not its colour.** A chip is solved to a
  luminance band so white text reads on it in a panel; on 1,000 square yards
  of end zone it lightens a club past what it is. Bears navy `#0B162A` paints
  `#366CCD`, and Eagles midnight green `#004C54` paints a teal `#0B7B86`.
  Accuracy wants the club's own colour, with the lettering picked for contrast
  against it rather than assumed white - a change to how the paint is chosen,
  not a tweak to a number.
- **`s-sideline-props.png`:** the goal-post net still reads as a grid across
  the whole field from behind the posts, at its 0.35 face-on floor. Unchanged
  and already on the director's list.
- **`s-bowl-wide.png`:** the away support fills most of one side of the bowl.
  That is `bowl.crowd.awaySection` (`fromX` 90, far side), and it reads as a
  larger travelling support than a home game has. Crowd's, not Field's.

## Round 5: the net was woven twice as tight as a real one

Before: `docs/lookdev/integration-13/s-sideline-props.png`. After:
`docs/lookdev/sideline-r5/s-sideline-props.png`.

**The 0.35 floor was never the lever.** `test_a_net_is_visible_face_on` holds
two things - a face-on minimum, and a fade only edge-on - and both survive this
round untouched: `minOpacity` went *up*, to 0.85. What it was guarding against
is older than the blend: "the poles showed but the net vanished. Cutout mips
fall under the threshold." That was an **alpha-tested** net, whose mips fell
under the cutout and disappeared. The net has been blended since, and a blended
net cannot vanish - it converges on its own coverage. So the floor was holding
a sheet opaque to prevent a failure the blend had already fixed, and the sheet
is exactly what read as a curtain.

**What the curtain actually was: coverage.** The veil a net lays over the field
is `coverage x CordGain x FaceOpacity`, and at any honest distance a 2.5 mm cord
is **sub-pixel**, so that is all it can be - the mip cannot resolve cord and air,
it averages them. Measured on the shipped mask:

| | coverage | CordGain | FaceOpacity | veil |
|---|---:|---:|---:|---:|
| integration-13 | 0.0550 | 2.5 | 0.35 | 0.048 |
| the same weave, cord-true | 0.0550 | 1.0 | 0.85 | 0.047 |
| **round 5** | **0.0236** | **1.0** | **0.85** | **0.020** |

The middle row is the point: making the cord true and dropping the gain changed
the veil by 0.001, because near *and* far are both mip-dominated. Only the weave
moves it. The mask was authored at a **2 inch** mesh - fishing net - where what
hangs behind an NFL goal is **4 inch** of 2.5 mm cord. Halving the weave halves
the veil, and the numbers above are why this round's fix is in
`tools/blender/field/build.py`, not in the tokens.

- **Changes:** mask 12 cells per 0.6 m repeat -> 6, cord half-width 0.03 -> 0.0125
  cell, knots 0.06 -> 0.030; `CordGain` 2.5 -> 1.0; `net.minOpacity` 0.35 -> 0.85
  (a cord is near-opaque, and it is the cord that is visible now, not the sheet);
  `net.grazingOpacity` 0.12 -> 0.35; the portable `fallback.opacity` 0.35 -> 0.08,
  which is the veil a flat material can honestly stand in for. Ports cannot draw
  cords from a flat colour, and should say so rather than draw a 35% sheet.
- **Test:** `test_a_net_is_cord_and_air_not_a_sheet` pins the real invariant -
  coverage is a few per cent, a cord reads as cord (`minOpacity >= 0.6`), it is
  never smeared (`CordGain <= 1`), and the veil stays under 0.10. It reads the
  shipped `net_mask.png`, so a re-woven mask is checked, not a copied constant.
  On integration-13's values it fails.
- **Budget:** sideline unchanged at 15 parts, 20,648-20,776 triangles.
- **Worst thing left, `s-sideline-props.png`:** the grid still crosses the view.
  It is finer and half the veil, but a 12 x 9 m net a few metres in front of you
  spans that view in life too, and at review-image resolution its cords can only
  ever mip to a wash. Judge this one on the headset before spending more on it.

## Field round 2: the paint is the club's colour, and the ink is chosen

Before: `docs/lookdev/field-r2/before/`. After: `docs/lookdev/field-r2/after/`.
Both leagues, five shots each; the before frames are the league audit's own
(`docs/lookdev/league/`), shot at the same seats one commit earlier, so the
only difference across the pair is this round.

**The defect.** End-zone paint, the midfield ring and the lettering all took
the club's *chip*. `chip()` solves a club onto one luminance band so that white
text clears 4.5:1 inside a panel. That is right for a panel and wrong for a
thousand square yards: it lightened every club past what it is. Chicago's navy
`#0B1C3A` painted `#366CCD`; Las Vegas and Pittsburgh both state `#000000` and
painted `#6F6F6F`, a grey end zone for two clubs whose colour is black.

**The rule now.** The paint is the colour the club states. The lettering ink is
*chosen* - the better of the field's own white `#DADAD3` and a new dark
`#12140F` - against the paint as it is actually seen, which is one alpha blend
over `color.turf.a` at `endZoneOpacity`. `scene.letter_ink` decides it, so the
web and Android get the same answer, and both ends and midfield share it: a
club does not letter one end white and the other dark.

**Measured over all 34 club colours a fixture here states** (`tools/field_paint.py`):

| | chip, before | club colour, after |
|---|---:|---:|
| worst separation from the grass (CIE76 dE) | 7.8 | **15.3** |
| worst lettering, ink chosen | 3.8:1 | 3.8:1 |
| worst lettering, white assumed | 3.8:1 | **1.7:1** |

The first row is the surprise and the reason this is not a trade: the chip band
sits near the grass's own luminance, so solving a club onto it moved every club
*toward* the turf. Green Bay's forest green is further from the grass as itself
than as a lightened chip. The third row is why the ink cannot be assumed - New
Orleans' old gold takes white lettering to 1.7:1, unreadable at any size. Six
clubs letter dark: Miami, New Orleans, Tennessee, Carolina, the Chargers and
Cincinnati. The binding club for lettering is Detroit at 3.8:1, which clears the
3:1 large-text floor and is not comfortable; end-zone type is as large as type
gets, so it stands.

**Cost:** one draw part per *distinct* ink. A field needing one ink costs what
it did; only a club whose midfield and end zones disagreed would cost two, and
the rule forbids that. Field measures 693 triangles / 10 parts against 2k / 12.

### The grass, judged against the bar

Item by item, on `after/nfl-field-level.png` and `after/nfl-redzone-trails.png`:

- **Reads as floodlit grass rather than a green plane, from the club seat** -
  passes. The mowing bands carry it at that distance.
- **The stripe changes with viewing angle as well as colour** - passes; the
  bands invert across the halfway line in `bowl-wide`.
- **No tiling visible from any seat** - passes. Nothing repeats visibly at
  0.4374 yd per tile.
- **Numbers' weight and scale** - passes against a real field; Graduate at the
  NFL's 6 ft cap.
- **Paint worn, with blades through it** - partial. The wear and the ragged
  hash edges are there; blades through the paint are not resolvable at review
  size.
- **Up close at field level, blades rather than a blurred photo** - **fails.**
  A 1200 x 700 crop of the near field of play at full resolution
  (`after/nfl-field-level.png`, near the bottom of frame) is a flat olive tint
  carrying a fine grain, with no blade reading as a blade. The albedo, both
  normals and the roughness map all load, and `TurfSheen` is bound on 3 meshes,
  so this is not a missing asset: at 0.4374 yd per tile the blade frequency mips
  to an average at anything past a couple of yards, and what survives is the
  stripe. Fixing it is a turf-authoring round - a coarser near-field detail
  layer, or a distance-blended second tile - and it is too large to do safely
  behind a colour change, so it is left named rather than half-tuned.

**Worst thing left, per shot:**

- `after/nfl-field-level.png`: the near grass is flat; no blades survive (above).
  The border is clean but still lit a flat mid-grey, which is Lighting's near
  field fill, not Field's albedo - unchanged from round 1 and now being worked
  in parallel.
- `after/nfl-bowl-wide.png`, `after/college-bowl-wide.png`: nothing in Field's
  hands. The college frame's crosshatch is its own dense yard markings and is
  present in the before frame too.
- `after/nfl-redzone-trails.png`: the midfield ring reads well in navy, but a
  club whose colour is close to the grass would put the ring near the turf -
  untested on a frame, because no fixture here has such a club at home.
- `after/*-tabletop.png`: no regression; the paint reads at table scale.
- **Untested on a frame in either league: the dark-ink case.** No fixture here
  has a light-coloured club at home, so New Orleans' gold and Miami's aqua are
  covered by `tests/test_field_paint.py` and by nothing you can look at. A
  fixture for one of them is the cheapest way to close that.

## Sideline round 6: the objects round

Before: `docs/lookdev/sideline-r6/before/`. After: `.../after/`. Both leagues.
Numbers in `.../stats.txt`.

**The net was not the problem, and has not been since round 5.** Three
checkpoints have carried "the grid still crosses the view" as this actor's
worst thing. `-sidelineSkip fieldgoal_net` (new, below) shoots the same frame
without it: the net raises everything behind it by **1.1 of 255** and does not
move the variance at all. The wash that makes the far stands milky from behind
the posts is still there with the net gone - it is Lighting's haze on a
sightline that crosses the whole bowl, not the net's veil. Round 5's re-weave
worked; the note outlived it. **Routed to Lighting**, whose own round measured
haze at 0.4% of the *sky* from the club seat, which is a different path
entirely.

**College was 648 triangles over its ceiling and nobody had measured it.** The
league audit correctly gave college its four extra hash pylons (1-2-6); that
put the actor at 21,648 against 21,000, while the NFL sat at 20,776 under it.
Every sideline measurement in this repo had been an NFL one.

**Where the budget went, and where it came from.** `bench` x8 is 6,336
triangles - 30% of the actor - and the team-area dressing another 5,800. An
LOD1 tier has been exported for every prop since the actor was built and used
by *nothing*: `lodSuffix` had `stadium` and `tabletop` only. The dressing (a
cooler 40+ yd from every seat) now draws LOD1 through a new
`lodSuffix.stadiumByModel`, which is a token because which props a viewer gets
near is a judgement about this stadium, not a renderer's business. The posts,
pylons, chain crew and benches keep their full mesh.

  NFL 20,776 -> 14,972; college 21,648 -> 15,844. Both leagues now sit ~5k
  under, where the actor has had no headroom since integration-11.

Judged on frames, not assumed: the dressing crop before and after is
indistinguishable (`before/sideline-props-nfl.png` against
`after/sideline-props-nfl.png`, the far team area).

**A bug the saving exposed.** The first measurement came back at 11,092 - half
the actor - and 13 draw parts instead of 15. `models` declared every prop's
full mesh and its `_lod2` and **never its `_lod1`**, so `assets.model` returned
nil, `add` returned early, and the entire team-area dressing was *absent*. No
error: a model that does not load simply is not drawn. Only the implausible
size of the saving gave it away. `test_every_prop_mesh_the_stadium_can_ask_for_is_declared`
now walks every id the actor can place against `models` and against the disk,
and fails on a missing declaration.

**Goal posts: 4 inches too narrow, on the one object a kick is judged
against.** 18 ft 6 in is measured inside-to-inside; the uprights were placed
with their *centres* on it, so the gap a ball must pass was 18 ft 2 in.
Measured off the exported .glb: 18.167 -> 18.517 ft (the rule is 18.500; the
0.2 in over is the 10-sided cylinder's facets). The crossbar now runs out to
the uprights' new centres so it does not end short of them. No kick call
changes - a good kick is drawn on the centre line and a miss at half the post
width plus 2.5 yd - so this was accuracy, not judging.

**The base pad was a crate.** From behind the posts it read as two blue slabs
with the gold pole standing between them. It is now a cylinder wrapping the
base, which is what padding on a goal post actually is: 12 -> 60 triangles for
the pair, and it reads as a wrap.

**New: `-sidelineSkip`,** DEBUG only, matching Bowl's `-bowlSkip` and
Lighting's `-lightSkip`: `-sidelineSkip fieldgoal_net,bench` leaves props out
and `mat:prop_net` hides a palette entry. Every claim above about what
something contributes was measured with it.

**Worst thing left, per shot:**

- `after/sideline-props-nfl.png` and `after/pad-nfl.png`: a gold strip still
  crosses the new pad. The pad is a 0.23 m cylinder and the base pole it wraps
  is 0.115 m, so the pole cannot be outside it; the strip is most likely the
  gooseneck projecting down across the pad from a camera above the pad's top,
  or the team chip drawing without depth against it. `-sidelineSkip
  mat:prop_gold` settles which in one shot - I ran out of run budget before it
  and am not guessing in the log.
- `after/sideline-props-*.png`: the view from behind the posts is washed by
  haze. Lighting's, measured above.
- `after/field-level-college.png`: the visitors' benches read as one purple
  rail at 50 yd. Right colour, right place, no bench detail at that distance;
  LOD is not the cause (benches keep their full mesh).
- `after/bowl-wide-nfl.png`: the LED boards along the wall were not judged
  this round - they never fall close enough to any shot's seat to read their
  pixel grid, which is itself the finding: the bar asks for a grid "up close"
  and no shot gets up close.

## Field round 3: blades at field level, as geometry

The one Field criterion still failing after r2: *up close at field level, the
grass has blades, not a blurred photo.*

**Measured first, because the obvious fix was the wrong one.** r2 blamed mip
averaging and proposed either a coarser near-field detail layer or a
distance-blended second tile. Both are more texture, and more texture does not
survive. Measuring the rendered near turf against its own source settles it:

| | horizontal high-frequency (0-255 luminance, mean step between neighbouring pixels) |
|---|---:|
| turf albedo, native 1024 px | 10.61 |
| the same albedo at mip 3 (128 px) | 12.12 |
| the same albedo at mip 5 (32 px) | 4.69 |
| **rendered near turf, field seat** | **0.60** |

The texture still carries 8x the delivered detail even at mip 5, so the tile is
not what is failing and a finer or coarser tile would not have helped.
Simulating `TurfSheen`'s own arithmetic over the real albedo and ORM at the
seat's angles accounts for part of it and not the rest:

| view distance from the field seat | grazing term | high-frequency left |
|---|---:|---:|
| 4.5 yd (the nearest field of play) | 0.374 | 7.65 (72% of raw) |
| 20 yd | 0.816 | 4.76 (45% of raw) |

So the sheen costs 28-55% by design, and the remaining ~85% is the graze
itself: at 16 degrees the sampler averages along the depth axis over many
texels whatever the tile holds. **That is why this round puts the blades in
geometry rather than in a texture** - the two candidate approaches from r2
were both texture, and both were measured out before any of them was built.

**The blades already existed, switched off.** `visual.field.shells` is six
alpha-tested layers of the eight baked coverage slices, one draw part and 24
triangles, built two rounds ago and shipped `enabled: false` because "from the
field-level seat the 24x10 yd patch still reads as a darker rectangle".

**Why it was a darker rectangle, read out of the graph rather than guessed.**
`FieldShells.usda` ended at `Base = mix(PaintColor, TurfSample x GrassTint)`
and bound that straight to the surface. `TurfSheen.usda` lifts the flat turf
toward `SheenColor` as the view flattens. So the field around the patch was
lifted and the blades inside it were not: the patch read as a hole in a
brighter field, and no tint tuned at one distance could fix it, because the
lift varies with angle across the patch.

**The fix.** The shells take the same sheen, by the same arithmetic, from the
same tokens: `Geometric . View -> abs -> 1-x -> ^SheenPower -> x Sheen ->
mix toward SheenColor`, and the surface binds `Sheened` instead of `Base`.
Only the sheen term is copied; the gap fill belongs to the ground plane, whose
soil the shells alpha-test away rather than paint. The two surfaces now agree
at every angle by construction.

**And the patch was too small to hide its own edges.** At 24 yd wide it ended
inside the frame: the field seat is 4.5 yd outside the near sideline, so at the
patch's far edge the eye is `depth + 4.5` yd away and a 90 degree view spans
that either side of centre. 32-68 yd (36 wide) against a 16.5 yd half-view
clears it, with `depth` 12 yd and `fade` 4 yd so the far edge dissolves where
blades stop resolving anyway. Enlarging the patch adds no triangles - the same
six quads, larger - only fill.

**Cost.** One draw part and 24 triangles, as before. The shell atlas is the only
new texture: 1024x512 RGBA = 2.10 MB, 2.80 MB with mips, against a stadium
sitting at ~67 MB of 300. The turf albedo and the paint mask were already
resident. Field's own budget is 2k triangles and 12 parts.

**Tests.** `tests/test_turf_shells.py` pins the bug rather than the numbers:
both surfaces take the same `SheenColor` and `SheenPower`; the shells' single
`Sheen` lies between the turf's per-stripe pair; the surface actually binds
through the sheen mix (a parameter the tokens set and the graph ignores is the
same bug with a passing test); the patch reaches past the frustum; and the far
edge fade is a real fraction of the depth. One of them caught a reversed
assertion of mine before the first build.
