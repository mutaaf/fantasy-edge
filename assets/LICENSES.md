# Asset licences

Every file under `assets/` is CC0 or original to this repository. Each actor
appends its own section.

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
