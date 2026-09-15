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
- **Paint:** reads right from row 16. Numerals, arrows and hashes are crisp, and the far numerals read from their own sideline.
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
