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

## Audio (`assets/actors/audio/`)

**Original: no recordings, no samples, no downloads.** Every sound is
synthesised from seeded noise, oscillators and a synthetic stadium impulse
response by `tools/audio/build.py` (run on Blender's bundled Python for
numpy; nothing is pip-installed), then encoded with `afconvert` (Apple
Lossless `.caf`) and `ffmpeg` (Opus `.ogg`). No chants, songs, team
music, PA voices or brand sounds. Released with the repository.

| Sound | Files | Class |
|---|---|---|
| crowd_bed, clap_bed, murmur_bed, wind_bed | `<name>.{caf,ogg}` | looping beds |
| roar, cheer, groan, sting | `<name>.{caf,ogg}` | crowd reactions |
| whistle, chime, horn | `<name>.{caf,ogg}` | referee, PA, scoreboard |
| rumble, defense_swell, final_cheer, exodus, fireworks | `<name>.{caf,ogg}` | cues and moments |

`manifest.json` records each file's length, seed and measured RMS and peak.

## Moments (`assets/actors/moments/`)

No files: particles are RealityKit's default soft sprite, configured from
`visual.moments.bursts`.
