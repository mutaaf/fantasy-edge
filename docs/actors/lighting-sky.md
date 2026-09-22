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

**It 7–10: after the director's merge `50cb09b` (`lighting-it10-shared`).**
- **Eye-height fix:** the fix put the eyes 1.2 m above the seat floor. I removed the
  flood `aimZ` offset, which compensated for eyes sitting too low. The near
  turf is even without it (`lighting-it7/s-rim-far`).
- **Beam fog** (integration-1, `bowl-wide`): the beams washed the upper deck
  grey.
  - Each beam now starts where its ray comes inside the bowl at
    `beams.startInsideOffsetYards` (4 yd), so no additive light lies across
    the stands.
  - Beams stop at `endHeightYards` (9 yd) above the grass.
  - Beam opacity is 0.32, dust 0.16, spill 0.11.
  - The haze rings moved up to 58 and 66 yd, above the upper deck's eye line.
  - The upper deck now keeps its club colour. A faint veil remains over the
    far lower bowl, where the shafts cross it; that is the intended "barely
    visible".
- **Zenith pinch** (`sky-dome`): wind-streaked clouds converged at the dome's
  pole. They now fade out between 49° and 69° of elevation. The pinch is gone.

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

---

# Round 2 — the value structure, measured

`actor/lighting-r2`, off `immersive/quality` at `5fca925`. Shots in
`docs/lookdev/lighting-r2/{before,after}/`; `before/` are integration-14's own
frames, confirmed identical to a fresh baseline shot on this branch (the band
above the rim measured 0.0542 in both).

The brief carried two long-standing faults and one unmeasured rule. One fault
was not real, the other was not reproducible, and the rule was broken.

## The floodlight pool edge: there isn't one, and there cannot be

integration-12 logged "the far half of the turf still has the floodlight pool's
hard diagonal edge" on `s-bowl-wide`, and -13 and -14 carried it forward. It is
not a lighting fault.

**Geometry.** Each flood sits on a bank 116–150 yd from the field centre and
54.8 yd up, aimed at the centre, with a 50° outer cone and a 260 yd
attenuation radius. The cone's steeper edge meets the ground **118 yd from the
centre** — out in the stands behind the bank — and its shallower edge is 28°
*above* horizontal, so it never meets the ground at all. Laterally the cone is
175 yd wide where it crosses the field, against a 27 yd half-width. Both
boundaries miss the turf. The far end zone is 203 yd from the bank, inside the
260 yd radius, so the attenuation does not terminate on the field either.

**Measurement.** `tools/light_levels.py --edges` walks columns down the turf
and reports the biggest row-to-row step in each. On integration-12, -13 and -14
the largest steps are identical (0.041, 0.033, 0.031…) and their rows are
scattered over 172 rows with no slope: periodic boundaries aligned to the yard
lines, which is the mowing stripe. A single light terminator would put the same
row in every column. Magnified (`.work/crops/far-half-big.png`), the far half
shows evenly spaced stripes and no terminator.

The stripes *are* diagonal in frame — perspective turns cross-field mowing into
converging diagonals on the far half — which is what the note was seeing.

## The end-zone haze: not reproducible

integration-11 logged the haze as heavy from the end-zone seat. On this build
the end-zone frame shows no heaviness (`after/crowd-closeup-endzone.png`, and
the same seat in integration-14). The haze's measured contribution to the band
above the rim was **0.4%** — the opposite problem: from the club seat it was
too faint to read as anything, against a bar that asks for haze "visible
against the sky".

## The rule that was broken: the sky was as bright as the grass

The art bible: "The field is the brightest thing in the bowl… The stands sit a
stop darker, the sky two." Nobody had measured it. Measured
(`tools/light_levels.py --bands`, and clean patches on `s-bowl-wide`):

| | before | after | art bible |
|---|---:|---:|---|
| field, midfield | 0.0623 | 0.0623 | brightest |
| band above the rim | 0.0542 (**+0.20 st**) | 0.0355 (**+0.81 st**) | a glow, below the field |
| high sky | 0.0341 (**+0.87 st**) | 0.0140 (**+2.16 st**) | 2 stops |
| zenith (`sky-dome`) | 0.0162 | 0.0051 | dark, not a void |
| field → stands | +1.45 st | +1.45 st | 1 stop |

The night sat 0.2 stops under the floodlit grass. It read washed rather than
deep, and the field was not the brightest thing in the bowl.

**Which layer owned it, measured rather than guessed.** `-lightSkip
dome,haze,clouds,beams,glow,fill,floods,stars` (and `LIGHT_SKIP`) leaves a
layer out, the way `-bowlSkip` does; `SkyActor` reads the same set. Shooting
`bowl-wide` once per layer:

| layer skipped | band above the rim | its share |
|---|---:|---:|
| none | 0.0542 | – |
| dome | 0.0528 | **3%** |
| haze | 0.0540 | **0.4%** |
| dome + haze | 0.0526 | 3% |
| clouds | 0.0554 | *darkens by 2%* |

**97% of it was the sky texture itself** — its zenith-to-horizon gradient at the
6× display exposure baked into `sky_night.png`. My first hypothesis, that the
dome and the haze were stacking in the same band, was wrong by a factor of
thirty. The dome — the bible's signature "warm light dome over the rim" — was
contributing almost nothing, which is backwards.

**The change**, three numbers, no asset rebuild, so the web and Android ports
get it from the same tokens:

- `visual.sky.skyGain` 1.0 → **0.6**. `StadiumLook.emissive(scale:)` tints the
  sky texture, so this scales the *displayed* dome only. The probe is the EXR,
  untouched: image-based lighting on every other actor is exactly as it was.
- `visual.sky.domeOpacity` 0.2 → **0.4**, so the glow above the rim is drawn by
  the dome that exists for it rather than by the whole sky being bright.
- `visual.lighting.haze.opacity` 0.08 → **0.12**, so the lit air reads.

`skyGain` 0.45 was tried first and over-darkened: the zenith fell to 0.0025 and
began to read as a void, against "nothing reads as a void". 0.6 keeps the stars
on a navy that still has tone (`after/sky-dome.png`).

## Judged on the frames

- `after/bowl-wide.png` — the field is plainly the brightest thing; a warm band
  sits above the rim and fades into deep navy.
- `after/lights-haze.png` — the glow band above the stands now reads as lit air
  over the bowl; before, the whole sky was that value so there was no band.
- `after/sky-dome.png` — stars as points on navy, the veil visible, a glow
  rising from the rim. Not a void.
- `after/td-moment-t5.5.png` — the strobe is punchy against the darker sky, the
  ribbon flashing TOUCHDOWN.
- `after/crowd-closeup-endzone.png` — no heaviness, no fog on the field.

## Budget (`-stadiumStats`)

| Actor | Draw parts | Triangles | Budget |
|---|---:|---:|---|
| lighting | 12 | 9,500 | 20 parts, 10k tris, ≤4 spots, ≤1 shadow caster |
| sky | 3 | 4,800 | 3 parts, 5k tris |

4 spot lights, 0 shadow casters. Beam overdraw 0.97 of the 1.2 cap at the
end-zone seat, 18 of 20 beams kept. Nothing was spent: the change is three
token values.

## Worst thing left, per shot

- `bowl-wide` — the stands sit 1.45 stops under the field where the bible asks
  for 1. The spill and concourse fill are Lighting's own levers and were not
  touched this round; a round that raises them should re-measure this table.
- `field-level` — at this seat the stands read 1.93 stops under the field, the
  widest gap of any framing.
- `lights-haze` — the glow band's colour is warm in the middle and cool-grey at
  the sides, where the sky's own horizon tint shows through the dome.
- `sky-dome` — the cloud veil reads as soft grey blotches rather than
  wind-stretched cirrus.
- `td-moment-t5.5` — the strobe reads, but the frame is one sample; whether it
  is "brief" is a timing question a still cannot answer.
- `crowd-closeup-endzone` — nothing to fault in Lighting's own work here.
