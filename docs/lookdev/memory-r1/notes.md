# memory-r1 — what the stadium holds, and what it was holding for no reason

A memory pass, not a look pass. Nothing here changes what is drawn; the shots
were re-taken only to prove that. `bowl-wide` and `crowd-closeup` are
unchanged from `field-identity`, and the near rings are in club colours rather
than the kit's grey, which is the thing that would have broken.

## Measured

visionOS 27 simulator (`Stadium 27`), `tools/lookdev.py`, one stadium, MIN at
CHI. **Simulator numbers**: the load order, the counts and the texture bytes
transfer to the headset; the frame time does not, and none of this was taken
on a device.

`stats-before-standin-release.txt` is the same harness on the same tree with
only `CrowdKit.dropStandIn` missing.

| | before | after |
|---|---:|---:|
| texture, at build | 185 MB | 185 MB |
| texture, dress landed | 252 MB | **194 MB** |
| — declared (`StadiumAssets`) | 67 MB | 67 MB |
| — crowd kit source atlases | 60 MB | 60 MB |
| — crowd dresses | 125 MB | **67 MB** |
| draw parts | 106 | 106 |
| triangles | 238,812 | 238,812 |
| main-thread tick, 120-frame mean | 0.417 ms | 0.380 – 0.401 ms |

The tick difference is inside the 0.30 – 0.43 ms band `integration-11-perf`
already recorded as simulator noise. Three per-frame allocations were removed
in this round and **none of them is visible above that noise** — treat the
tick as unchanged, not improved.

## The number the stats line used to print was wrong

It said `texture memory ~67 MB`. That was `StadiumAssets.bytes`, which is the
declared textures only. The crowd's four atlases are loaded by `CrowdKit`
directly and its dresses are composed at runtime, so **none of the largest
consumer in the bowl was in the number** the 300 MB budget in
`docs/ART_BIBLE.md` is checked against. The real figure was 252 MB — out by a
factor of 3.8. It is now printed in three parts.

At 194 MB, one stadium spends about two thirds of the whole 300 MB stadium
texture budget. That is worth knowing before a second one is opened.

## What one more concurrent stadium costs

Shared between renderers (`StadiumAssets.shared`, `CrowdKit.cache`, the dress
LRU): the 67 MB of declared textures and the 60 MB of source atlases. Paid
again per additional view showing a *different* matchup: about 71 MB of dress,
plus that renderer's own entity tree and generated meshes.

The dress LRU is `visual.crowd.dressCache`, default 2 — which is also how many
stadiums can be on screen before one evicts another's dress. Raise it to the
number of stadiums intended and budget ~71 MB each.

## The crowd's resident geometry is 12x what it draws

Measured from `stats.txt`: 33,846 fans — lod0 14, lod1 24, lod2 40, lod3 286,
cards 33,482, 38 groups — and every near group reports `slots 12/12`.

The rings demote correctly and the caps bind exactly (each ring sits on its
`visual.crowd.rings` maximum), and the far rings really are cheaper: 3,000
triangles a fan at lod0 down to about 1.2 a fan for a paired card, a range of
2,500:1. 98.9% of the crowd is cards.

But each near group holds a merged mesh for **every one of the twelve
choreography slots**, so the near rings' 107,920 drawn triangles are about
1.3M triangles of resident vertex and index buffers — **reasoned** at roughly
44 MB, not measured. That is deliberate: it is what makes a pose change a
single property write, which `docs/ART_BIBLE.md` requires ("fans animate by
group, never per fan on the CPU"). Dropping the rarely-reached slots for lod2
and lod3 would give most of it back and is a fidelity call for the Crowd
specialist, not a memory fix.

## Left alone on purpose

`StadiumRenderer.optOutOfShadows` walks the whole world every frame. At 89
models it is small, and the obvious dirty flag — an entity count — is unsound:
`BroadcastTrails.grow` unparents the live trail and adds its replacement in
the same frame, so the count is unchanged while three entities that must not
cast are new.
