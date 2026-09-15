# Asset licences

Every file under `assets/` is CC0 or original to this repository. Each actor
appends its own section.

## Crowd (`assets/actors/crowd/`)

**Original: no third-party inputs, no downloads.** Every file is produced by
`tools/blender/crowd/*.py` (Blender 5.2.1, procedural skin-modifier bodies,
primitive props, node-based face and fabric detail). There are no
third-party models, textures, scans or likenesses. Released with the
repository.

| Files | Made by |
|---|---|
| `fan*.{usdz,glb}`, `lod{0,1}_poses.{usdz,glb}` | `build.py` (skeleton and bodies in `fan.py`, `rig.py`; poses in `poses.py`) |
| `fan_albedo.png`, `fan_mask.png`, `impostor_{albedo,mask,normal}.png`, `variation.png`, `manifest.json` | `build.py` |
| `review/*.png` | `lineup.py`, `pose_review.py` (critique renders) |

## Lighting and sky (`assets/actors/lighting/`, `assets/actors/sky/`)

**Original: no third-party inputs, no downloads.** Every file is produced by
the committed Blender scripts in `tools/blender/lighting/` (`build.py` runs them
all) from procedural geometry, seeded numpy noise and Cycles renders of a proxy
bowl those scripts build. Released with the repository.

| Files | Made by |
|---|---|
| `light_bank_{hero,near,far}.{usdz,glb}`, `beam_{cone,quads}.{usdz,glb}` | `rigs.py` |
| `textures/emitter_lens.png`, `textures/lamp_bank_face.png` | `rigs.py` (face baked from the model) |
| `textures/glow_*`, `bloom_card`, `beam_*`, `haze_*`, `moth_atlas`, `shadow_multi`, `ao_riser` | `textures.py` |
| `env/stadium_{night,dusk}*`, `env/tabletop_room*` | `ibl.py` (Cycles, proxy stage in `stage.py`) |
| `sky/env/sky_{night,dusk}.exr`, `sky/textures/*` | `textures.py` |

No logos, marks or recognisable venues: the bowl is the scene's superellipse.
Blender itself (GPL) is a build tool only; its output is not covered by the GPL.
