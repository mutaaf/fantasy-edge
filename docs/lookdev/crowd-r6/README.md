# crowd-r6 — the visiting wedge

Crowd round 6 on `actor/crowd-r6`, from integration-13 (`c4ba02b`). The user's note was that
the visiting support reads as a painted purple wedge filling one side of the bowl.

## The share, in seats and in pixels

`tools/crowd_pixels.py` measures a wide frame's stands: every pixel that is neither sky, field,
fascia nor panel is scored against the two crowd chips the scene carries, and pixels whose hue
sits between them are counted as neither.

| | seats | stand pixels (wide frame) |
|---|---|---|
| integration-12 | 9% | 35.0% |
| integration-13 | 9% | 26.1% |
| **crowd-r6** | **4%** | **20.1%** |

(The coordinator's own measure read integration-12 and -13 as 27.8% and 18.0%; the method here
differs — hue nearest, with an ambiguous band — so the trend matches and the absolute numbers do
not.) 10.7% of the stand pixels in the r6 frame belong to neither club by that measure.

## What broke the silhouette

Support is no longer a verdict per section. `CrowdSupport.supportBySection` returns a *pull* per
section, and `supportAt` draws every seat against it on a grain of 3 rows × 4 seats: dense in the
core (0.9), thin at the edge (0.28), thinning again as the block climbs its tier (`tailRows`).
So the boundary is ragged, home shirts sit inside the visiting block, and the whole thing is a
crowd rather than a rectangle — at no cost in draw parts, because the cost of a mixture is the
number of (slice, support, variant) groups, not the number of mixed seats.

## Frames

| Shot | What to look at |
|---|---|
| `s-bowl-wide.png` | The visitors: a core behind their bench, a broken tail into the far upper corner, mixed at its edges. |
| `s-bowl-wide-phi.png` | The close pairing: Philadelphia teal against Dallas blue. See the verdict in `docs/actors/crowd.md`. |
| `s-crowd-closeup.png` and `-clubLevel`, `-upper`, `-endzone`, `-sideline`, `-field`, `-pressBox` | Every seat preset; the rows a wearer looks along are the home crowd's. |
| `s-td-moment-p3-visitors.png`, `-p7-visitors.png` | The visitors score: their sections brighten a few blocks at a time, and the near home rows stay in their seats. |

`stats-club.txt` and `stats-visitors.txt` carry the `-stadiumStats` counts: crowd **133,138–133,481
triangles, 36 draw parts** (integration-13: 135,626–136,338 and 38), against 150k and 45.
