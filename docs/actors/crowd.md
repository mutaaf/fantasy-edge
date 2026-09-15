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

In progress.
