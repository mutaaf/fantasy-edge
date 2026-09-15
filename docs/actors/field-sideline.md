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
