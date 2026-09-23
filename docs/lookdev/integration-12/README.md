# integration-12 — the round-4 checkpoint

`immersive/quality` with three merges on top of integration-11: crowd round 4
(the facing fix, per-fan poses, a clean bake), `experience-r4` (the dock) and
`broadcast-r4` (per-play paths, a lit ball). Shot on a cloned visionOS 26.5
simulator from a Debug build against the visionOS 27.0 SDK.

**The headline: the crowd faces the field.** Every seat preset shows the rows
in front from behind or in profile. integration-11's `crowd-closeup-sideline`
was a wall of faces; it is now shoulders and backs of heads. The app measures
the kit it loaded and logs it: `crowd kit lod0/lod1/lod2 faces +Z (24 fans)`.

## Gates

| Gate | Result |
|---|---|
| `make test` | 569 OK |
| `make verify-scene` | 15 scenes, 1,422 arcs, 495,085 assertions OK |
| `verify_crowd` | 337,996 checks OK |
| `contrast_check` | OK |
| `xcodebuild` (clean, own derived data) | BUILD SUCCEEDED, 1 warning — the pre-existing AppIntents metadata notice. Xcode 27 adds none. |

**The tokens merge is intact.** `design/tokens.json` was resolved by value
rather than by line, because crowd round 4 reformatted the whole file. All
1,166 keys parse, and each branch's own section is present:
`visual.experience.layout.dock` (21 keys, and `layout.search` is gone as
intended), `visual.broadcast.play` (87), `visual.crowd.nearMix` (11),
`arc.goalKick` and `visual.broadcast.play.goalKick`. `verify_scene` reads the
file through `SceneLook` and passes, which is the test the art bible names.

## Budget, measured with `-stadiumStats`

| Actor | Triangles | Draw parts | Target |
|---|---:|---:|---|
| Field | 1,114 | 10 | 2k / 12 |
| Sideline | 20,936 | 15 | 21k / 15 |
| Bowl | 59,672 | 16 | 62k / 20 |
| Crowd | 143,763 | 36 | 150k / 45 |
| Lighting | 9,508 | 12 | 10k / 20, ≤4 spots (4), beams ≤1.2 screens (0.46–0.97) |
| Sky | 4,800 | 3 | 5k / 3 |
| Broadcast, idle | 4,422 | 6 | 30k / 25 |
| Broadcast, mid-kick | 7,462 | 24 | **back under 25** (27 at integration-11) |
| Moments | 0 | 0 | 2k / 10, ≤4 emitters (4 measured) |
| Experience, Audio | 0 | 0 | — |
| **Stadium, idle** | 184–240k | 88–98 | 287k / 160 |
| **Stadium, peak (fieldGoal +6 s)** | 247,045 | 115 | 287k / 160 |
| **Tabletop** | 24,221 | 73 | 80k / 110 |
| Texture memory | ~67 MB | | 300 MB |

Load, in the simulator: assets ready 1.86–2.35 s after open, first tick
5.79–6.44 s, crowd dress 1.44–1.52 s (tint is 1.3–1.4 s of it). Frame time is
still unverified; only a device can answer it.

## Rubric, 1–5

| Actor | Read | Light | Material | Scale | Life | Clarity | Comfort | Cost |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| Field | 4 | 4 | 4 | 5 | — | 5 | 5 | 5 |
| Sideline | 4 | 4 | 3 | 5 | 3 | 3 | 5 | 5 |
| Bowl | 4 | 4 | 4 | 5 | — | 5 | 5 | 5 |
| Crowd | 4 | 4 | 3 | 4 | 4 | 4 | 5 | 4 |
| Lighting | 4 | 4 | 4 | 5 | 4 | 4 | 5 | 5 |
| Sky | 4 | 4 | 4 | 5 | 3 | 5 | 5 | 5 |
| Broadcast | 4 | 4 | 4 | 4 | 4 | 3 | 5 | 4 |
| Moments | 3 | 4 | 4 | 4 | 4 | 3 | 4 | 5 |
| Experience | 4 | — | 4 | 4 | 3 | 4 | 4 | 5 |
| Audio | — | — | — | — | — | — | — | — |

No line is below 3, and none is lower than it was at integration-11.
Moments' Read and Clarity stay at 3 for the timing defect below; Sideline's
Clarity stays at 3 for the net.

## Worst thing left, per shot

- `s-crowd-closeup.png` — the Elsewhere tab sits among the heads of the near row.
- `s-crowd-closeup-clubLevel.png` — the nearest fan's shoes hang over the tread edge, above the row below.
- `s-crowd-closeup-upper.png` — clean; the Elsewhere tab is the only thing dead ahead.
- `s-crowd-closeup-endzone.png` — the right-hand near fan's feet hang in the air over the row below.
- `s-crowd-closeup-sideline.png` — fixed; nothing on the chair in front. Hair still reads card-flat at 2–3 m.
- `s-crowd-closeup-field.png` — the Elsewhere tab lies on the white sideline stripe.
- `s-crowd-closeup-pressBox.png` — the desk and wall are one featureless beige plane (unchanged from integration-11, Bowl's).
- `s-bowl-wide.png` — the far half of the turf still has the floodlight pool's hard diagonal edge.
- `s-field-level.png` — the ribbon double-draws seen along its length: two overlapping copies of the crawl at different brightness.
- `s-redzone-trails.png` — done plays now lie on the grass; the remaining trail is so faint it barely reads as a drive.
- `s-sideline-props.png` — the goal net's grid covers the whole view from behind the posts.
- `s-lights-haze.png`, `s-sky-dome.png` — unchanged from integration-11.
- `s-tabletop.png` — the bowl's rim reads as a dark band; the crowd is a texture at this size.
- `s-td-moment-t0.5.png` — the banner, the score (CHI 17) and the ribbon flash are all up while the ball is still in flight.
- `s-td-moment-t5.1.png` — the banner has gone before the play lands; the crowd is still celebrating, which is right.
- `s-td-moment-t8.5.png` — a lit ball sits over the far stands with a stick-straight trail; probably the extra point, but from this seat it reads as off the field.
- `s-td-moment-p6.5-fg-club.png`, `-fg-sideline.png` — "FIELD GOAL" flashes whole words and the drive panel is clear of the ribbon; the ball is nowhere to be found mid-kick.
- `s-field-level-p*-run.png` — the run reads: the ball is carried along the grass with a visible glow and shadow. Nothing wrong.
- `s-bowl-wide-p*-short.png` — "FIRST DOWN" flashes whole; the ball is a dark speck from the upper deck.
- `s-bowl-wide-p*-deep.png` — the open Controls panel sits across the middle of the field.
- `s-bowl-wide-p*-kickoff.png` — the kick arc and the return read; the ball itself is hard to find.

## Interactions the merge could have created

- **Fans against the dock:** no conflict. The rail's pills sit low among the near rows; nothing is planted on a fan.
- **The lit ball against the new trails:** they read together at field level. At upper-deck distance the ball loses its glow before the trail loses its line.
- **The ribbon:** `broadcast-r4`'s fixes hold in the merged build. `RED ZONE`, `FIRST DOWN`, `FIELD GOAL` and `TOUCHDOWN` all flash whole words; integration-11's `REDNE` and `TOUCHD TOUCHDOWN` are gone.
- **Moment timing (the director's, recorded not fixed):** the banner, strobe, score and ribbon flash fire when the play arrives, and the ball lands about 5 s later. `t0.5` shows CHI already on 17 with the return still running. The hook Broadcast wants: the composer holds a `.moment` until `hasTrail(m.playId)`, with a timeout of the arc's duration plus about a second.

## Regressions found and fixed

None. Nothing in the merge needed a fix, and no gate failed.

One harness note, not a code change: each `lookdev.py` run rewrites
`stats.txt` for its own launches only, so this checkpoint's `stats.txt` was
gathered once across every run from the simulator's log.
