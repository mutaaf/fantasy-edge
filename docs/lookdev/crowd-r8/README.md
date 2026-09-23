# crowd-r8 — no flat fan stands among solid ones

Crowd round 8 on `actor/crowd-r8`, from `immersive/quality` at `f2f3e62`. Both sets were shot in
the same quiet window (load 4–8), `before/` from the integration tip and the rest from the fix, so
the numbers compare directly.

## The defect, and the rule that caused it

Experience found flat card fans standing among solid mesh fans at six to eight yards, with the
field showing through them (`docs/lookdev/experience-r7/crowd-cards-near-crop.png`). The cause was
an inversion in `CrowdActor`: **the count caps decided mesh against card, and the distance rule
only tidied up inside `minCardYards`.** A row seen end-on holds far more fans inside the mesh
radius than 14/24/130 allows, and every one of the overflow became a card wherever it stood.

Measured at this scene, fans within 13 yd of each seat preset:

| seat | 7 yd | 9 yd | 11 yd | 13 yd |
|---|---:|---:|---:|---:|
| club | 0 | 0 | 238 | 360 |
| sideline | 119 | 173 | 226 | 375 |
| endzone | 106 | 165 | 250 | 330 |
| clubLevel | 0 | 0 | 176 | 261 |

Covering a whole end-on row with meshes — 375 fans at the sideline seat — costs 94k triangles for
lod2 alone, six times the headroom. So the caps stay, and what changes is what they mean.

## The fix

Mesh against card is now decided by **rank in true distance**: the nearest `lod0Max + lod1Max +
lod2Max` fans are meshes and everyone beyond is a card, so the boundary is a circle and no card
can stand closer than a mesh fan. The dither still ragged-edges the seams *between* mesh rings; it
no longer decides whether a fan is flat. `lod2Max` rises 130 → 145, the most the budget allows at
250 triangles a lod2 fan, and the card material is explicitly `blending = .opaque`, so a card is
alpha-tested and can never read through. The app logs the radius it achieved:
`[stadium] crowd rings: meshes out to 7.6 yd, then cards`.

| | before | after |
|---|---|---|
| Crowd triangles | 136,412–136,419 | **140,132–140,145** (budget 150k) |
| Draw parts | 36 | **36** (budget 45) |
| Crowd dress | 2.03–2.71 s | **1.64–2.46 s** |
| Mesh fans | 168, wherever the caps ran out | **183, the nearest ones** |

## Frames

`near-cards-before.png` and `near-cards-after.png` are the same near rows of the sideline seat,
cropped from the 4K originals: in the before crop the field shows through the standing figures at
the left; in the after crop they are solid.

`s-crowd-closeup.png` and `-clubLevel`, `-upper`, `-endzone`, `-sideline`, `-field`, `-pressBox`,
`s-bowl-wide.png`, `s-td-moment-t0.5.png` and `-t5.1.png`, with `before/` alongside for each.
`stats-club.txt` and `stats-td.txt` carry the counts.
