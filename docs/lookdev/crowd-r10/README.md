# crowd-r10 — a fourth detail tier, so the mesh circle reaches the club seat

Crowd round 10 on `actor/crowd-r10`, from `immersive/quality` at `62c3f8d` (integration-16's
`016a7eb` changed no code — docs and shots only, so the two are the same build). `before/` is the
tip's app served the tip's tokens; the rest is the fix. Shot in the same session on one simulator.

## The defect

Round 8 made the mesh boundary a circle and left it at 7.6 yd. At the club seat every fan in view
sits beyond that, so the near rows were flat cards:

| | |
|---|---|
| `club-near-rows-before.png` | the sideline stripe runs straight **through** a raised arm and a torso, and the cut-outs have hard rectangular alpha edges |
| `club-near-rows-after.png` | the same rows, solid, with the stripe stopping where the figures begin |

`club-rows-wide-{before,after}.png` is the same pair at wider crop. Both are cut from the
full-resolution frames, not the 1400-wide review copies.

The crowd line also steps down between the two: a card is a billboard standing on the seat, a mesh
sits in Bowl's chair. Converting one to the other drops the fan into the seat, which is why the
after frame shows more field above the near rows. That is the meshes being right, not fans
disappearing.

## The tier

`LOD3_TRIS = 120`, from lod2 with the hair/hat/scarf/prop shells welded at 20 cm first. Every fan
lands at **119–120 triangles** (mean 119.6); nothing hit a decimation floor. Faces +Z off its own
probe triangle like every other tier.

The circle is bought in fans, and a fan used to cost 250. At 120 the same budget buys two, so
`lod2Max` 145 → 40 and `lod3Max` 286: **183 mesh fans → 364**.

| seat | circle before | circle after | | seat | before | after |
|---|---:|---:|---|---|---:|---:|
| club | 7.6 yd | **10.5 yd** | | endzone | 9.5 | 13.6 |
| upper | 8.0 | 10.9 | | field | 10.6 | 15.2 |
| sideline | 8.3 | 12.0 | | pressBox | 14.3 | 18.0 |
| clubLevel | 9.1 | 12.2 | | | | |

**+38% at the club seat, not the doubling estimated in round 8.** Doubling a radius is four times
the area and so four times the fans; 120 triangles buys +99% fans and about +40% radius.

## Cost

| | before | after |
|---|---:|---:|
| triangles (worst seat) | 140,151 | **147,982** of 150,000 |
| draw parts | 36 | **38** of 45 |
| dress | 2.39–2.66 s | 2.23–2.57 s |
| mesh fans / card fans | 183 / 33,663 | 364 / 33,482 |

The budget test's old model of the far crowd — 50,000 triangles, one card per two of a
50,000-seat bowl — was 10k over what the crowd measures (40,282 in round 9's stats). It is now the
measurement plus a 4% margin, reasoned in the test itself.

Gates: 807 tests, verify-scene 495,262 assertions, verify-moment 284 checks, verify-crowd 346,120
checks, contrast_check, and a build with no new warnings.
