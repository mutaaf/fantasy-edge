# crowd-r7 — hair, and three refinements

Crowd round 7 on `actor/crowd-r7`, from `immersive/quality` at `5fca925`. Before frames are
`docs/lookdev/integration-14/`.

| | integration-14 | crowd-r7 |
|---|---|---|
| Crowd triangles | 133,497 | **135,643–136,289** |
| Draw parts | 36 | **36** (budget 45) |
| Crowd dress | 2.39–3.67 s | **2.18–2.45 s** |

## What to look at

| Shot | What changed |
|---|---|
| `s-crowd-closeup.png` | **Hair.** MakeHuman's cards are closed into a solid shell per style, so hair is volume rather than a stack of slabs. This is the round's point; compare with integration-14's frame at the same seat. |
| `s-bowl-wide.png` | Empty seats cluster into patches and run along the gangways instead of scattering inside a block. |
| `s-td-moment-p3-visitors.png`, `-p7-visitors.png` | The visiting sections brighten at their own pace *and* settle at their own brightness, so the block never squares up. |
| `s-crowd-closeup-clubLevel.png`, `-sideline.png` | The foam finger's mitt tapers to the wrist and its thumb stands proud of the face, so the edge-on silhouette is a hand rather than a bar. |
| `-upper`, `-endzone`, `-field`, `-pressBox` | The rest of the seat presets, unchanged in intent. |
| `s-td-moment-t0.5.png`, `-t5.1.png` | The home celebration, for comparison with the visiting one. |

`stats-club.txt`, `stats-td.txt` and `stats-visitors.txt` carry the `-stadiumStats` counts.
