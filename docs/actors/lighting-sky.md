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

**It 6: art director's round (`lighting-it6`).** Each fix, and the shot that shows it:
- **Sky:** navy toward the zenith, city glow pulled down to the horizon
  (falloff 14 per radian of elevation, was 7), and fewer stars that are
  smaller and sharper. The warm light dome is down from 0.32 to 0.2 opacity.
  The night no longer reads grey-brown (`s-rim-far`).
- **Grey veil:** the haze sheets left the open sky. They are now rings at
  bank height (40 and 52 yd up) over the rim, 38 to 78 yd out. Gone in every
  shot.
- **Spill:** a new seat-facing glow layer (78×40 yd card, 16 yd below and
  10 yd in front of each bank) lies over the upper seats. The rows under the
  banks now read as floodlit (`s-rim-far`, `s-strobe`).
- **Lens:** a lower diffuse floor so only the LED cores reach full value, with
  gains set to 1.0. The grid survives at distance and the face bake shows it.
- **Beam dust:** a second quad set tiles `beam_dust.png` along each beam and
  scrolls it with `UnlitMaterial.textureCoordinateTransform.offset`, updated
  every 0.1 s and held still under reduce motion. **This is the fallback:**
  visionOS has no CustomMaterial, and a Shader Graph `.usda` needs a Reality
  Composer Pro package that a headless build can't author or verify. Beam
  opacity is now 0.42 and dust 0.22; the beams read as shafts in haze
  (`s-rim-left`). The motion is unverified; the shots are stills.
- **Near turf:** the four floods alternate their aim between z +14 and −4
  yards instead of the centre line. The near half evens up with the far half
  (`s-rim-far`).
- **Budget:** lighting is 11 parts and 9.3k triangles; overdraw is still
  capped at 2.0 screens.

## Contract for Sideline: prop shadows

Only one spot light casts real shadows (the budget allows one), so goal posts,
benches, pylons and chains need faked floodlight shadows. Lighting provides the
decal; Sideline places and owns it.

- **Texture:** `visual.lighting.response.propShadowDecal`
  (`actors/lighting/textures/shadow_multi.png`, 512²). RGB is black and alpha
  is the shadow: four soft lobes at 35°/145°/215°/325°, one per light-bank
  quadrant, plus a contact core. Its alpha is already capped at 0.7.
- **Placement:** a quad lying on the turf, centred on the prop's footprint,
  about 3× the footprint across (goal-post base: 3 yd; pylon: 0.5 yd). Put it
  at `field.lines.lift / 2` so it sits under the paint, in `StadiumLook.groundSort`.
- **Material:** a PBR or unlit transparent material with black tint and the
  decal as opacity. Don't write depth. Don't use additive blending; shadows
  subtract light.
- **Orientation:** lobe 0 (35°) points toward scene +x, −z; yaw the quad so
  the lobes line up with the rim banks' quadrants. Banks stand all round, so any
  yaw works, but keep one yaw for every prop.
- **Strength:** multiply alpha by `visual.lighting.response.bowlContactAO`
  (0.55) so props and seats share one level of occlusion.
- **Seat risers:** `response.riserAO` (`ao_riser.png`) is for Bowl, not
  Sideline. V runs from the tread's back corner (0) to the next riser (1) and
  tiles along U.

Lighting won't draw these itself: a decal Lighting placed could not follow a
prop Sideline moves.

## Out of scope, noted for other actors

- **Crowd:** the foreground fans in the rows directly in front of the seat
  render pixelated and blocky (`s-rim-far`, `s-strobe`, `s-endzone`).
- **Broadcast (Wave 2):** the win-probability labels
  ("WIN PROBABILITY", "MIN", "CHI") float in the open sky with no panel behind
  them, so they read as stray text over the stars.

## Budget, measured (stadium, `-stadiumStats`)

| Actor | Draw parts | Triangles | Lights | Budget |
|---|---:|---:|---:|---|
| lighting | 9 | 9.2k | 4 spot, 1 shadow | 20 parts, 10k tris |
| sky | 3 | 4.8k | – | 3 parts, 5k tris |
| lighting (tabletop) | 13 | 8.8k | 4 spot | |

The additive beam overdraw is estimated per seat and capped at 2.0 screens, and
logged at build: `[stadium] lighting beams k/n, overdraw ≈ x screens`.
