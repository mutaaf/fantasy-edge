# Lighting & Sky: critique log

Shots from `tools/blender/lighting/shoot.py` (lighting's no-tilt framings) and
`tools/lookdev.py`. Paths are under the specialist worktree's `.work/shots/`.

## Note on the shared shots

`lights-haze`, `sky-dome` and `bowl-wide` open inside the stands (a grey or
black frame) on the director's split build `7530d53` as well as on this
branch: the debug pivot tilts the world about a point that is not the eye.
Evidence: `lighting-baseline/s-lights-haze.png`, `s-bowl-wide.png`. Reported to
the director. Until that's fixed, lighting is judged on `shoot.py`'s framings,
which keep pitch 0, plus `td-moment`, which renders.

## Iterations

**Baseline (`lighting-baseline`, `lighting-it1/s-td-moment.png`).** Rim banks are
four grey slabs with a stuck-on glow on only the far side. There are no beams,
and the "haze" is invisible. The sky is a flat grey-brown gradient washed by the
light dome, so it reads as dusk fog, not night. The probe is procedural.

**It 1: models in, first read.** The near and far bank models are merged per
material: 9 draw parts, 5.9k triangles. The fixtures and lit lenses read as real
LED banks. Two problems: the merged glow billboards were visible only on the far
side, and the sky sphere at 8k triangles was over budget.

**It 2: sky dome.** A custom inward-facing dome at 48×24 (4.8k tris for sky, 3
parts, in budget). Stars are crisp. Critique:
- The far upper deck is still mostly a dark wall, and banks behind the wearer are not in shot.
- Beams are invisible at 0.05 opacity.
- The light dome is too bright; the sky above the rim is grey.

**It 3: count and scale.** 16 banks all the way round, lamps 14×5.1 yd, and a
larger halo and bloom. Beam opacity 0.13, 3 per bank, overdraw capped at 2.0
screens (13–24 of 24 kept depending on seat). The sky gain is down to 0.6.
`rim-far` now reads as a floodlit night, and `endzone` shows the rigs raking
round the rim. The beams are still too faint to register.

**It 4: probing visibility.** Beams at 0.45 finally read as shafts from
`rim-left`, but the haze sheets at 0.3 showed a hard **elliptical rim** in the
sky. That's a cheap tell: rejected. Tabletop glows cut to the halo only
(21 → 13 parts).

**It 5: soft haze band.** `haze_band.png` fades to zero at both inner and outer
edges, with UVs mapped inner→outer. The rim is gone, and the air over the stands
now has a faint lit veil. Beams are at 0.34.
- `rim-left`: shafts falling from the banks toward the field.
- `rim-far`: banks glowing, sky dark blue-black with stars.

Remaining critique, ranked:
1. The veil still shows a large, faint grey shape in the upper sky from some seats. Height or opacity needs one more pass.
2. The lens emissive clips white. Fine at distance, but the LED grid pattern is lost close up (press box view).
3. Beams are uniform shafts; they want the scrolling dust (`beam_noise.png`), which a Shader Graph material would allow. UnlitMaterial can't scroll.
4. There are no field shadows from the goal posts beyond the single shadow caster. The multi-shadow decal exists for Sideline to use.

## Budget, measured (stadium, `-stadiumStats`)

| Actor | Draw parts | Triangles | Lights | Budget |
|---|---:|---:|---:|---|
| lighting | 9 | 9.2k | 4 spot, 1 shadow | 20 parts, 10k tris |
| sky | 3 | 4.8k | – | 3 parts, 5k tris |
| lighting (tabletop) | 13 | 8.8k | 4 spot | |

The additive beam overdraw is estimated per seat and capped at 2.0 screens, and
logged at build: `[stadium] lighting beams k/n, overdraw ≈ x screens`.
