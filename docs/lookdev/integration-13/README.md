# integration-13 — the accuracy checkpoint

What landed since integration-12: nflverse-corrected plays (`data/play-accuracy`),
the field given to the home club (`actor/field-identity`), last week's games as a
replay picker (`feature/last-week-replay`), the crowd given to the clubs playing
(`actor/crowd-r5`), and the director's restoration of `BroadcastActor.hasTrail`,
which an earlier merge dropped.

Shot on the visionOS 26.5 simulator, clone `fe-i13`, own derived data. 33 review
frames here; full-size originals in `.work/shots/integration-13/`.

## Gates

| Gate | Result |
|---|---|
| `make test` | 652 OK |
| `make verify-scene` | 15 scenes, 1,422 arcs, 495,078 assertions OK |
| `verify_crowd` | 346,120 checks OK |
| `verify_moment` | 86 checks OK |
| `contrast_check` | OK |
| `xcodebuild` | BUILD SUCCEEDED; one warning, the pre-existing AppIntents notice. Xcode 27 adds none. |

Use a destination *id* from `xcrun simctl list devices available`; a destination
by name now lists every simulator and builds nothing.

## Budget, measured with `-stadiumStats`

| Actor | Triangles | Parts | Target | |
|---|---:|---:|---|---|
| Field | 693 | 10 | 2k / 12 | ↓ from 1,114: BEARS and CHICAGO are fewer glyphs than CHICAGO BEARS twice |
| Sideline | 20,936 | 15 | 21k / 15 | |
| Bowl | 47,326–55,044 | 9–16 | 62k / 20 | |
| Crowd | 135,626–136,338 | 38 | 150k / 45 | ↓ from 143,728 |
| Lighting | 9,508 | 12 | 10k / 20 | 4 spots; beam overdraw 0.63 of a 1.2 cap |
| Sky | 4,800 | 3 | 5k / 3 | |
| Broadcast idle | 4,422 | 6 | 30k / 25 | |
| Moments | 0 | 0 | 2k / 10 | |
| Experience | 0 | 0 | 5k / 10 | attachments excluded |
| **Stadium** | **223,735–231,401** | **93–100** | 287k / 160 | ~67 MB textures |
| **Tabletop** | 23,760–23,800 | 67 | 80k / 110 | |

Crowd: 34,280 of 49,982 seats taken (69%), home 85% / visiting 9% / neutral 5%.
The kit logs `lod0/lod1/lod2 faces +Z`, measured off the probe triangle.

Load: assets ready 3.0–3.4 s, first tick 5.8–7.4 s, crowd dress 1.7–2.96 s
(tint 1.5–2.9 s of it), under a simulator running three shot sessions.

The simulator cannot measure frame time. Frame budget is still unverified on device.

## Rubric, 1–5

| Actor | Read | Light | Material | Scale | Life | Clarity | Comfort | Cost |
|---|---|---|---|---|---|---|---|---|
| Field | 5 | 4 | 4 | 5 | – | 5 | – | 5 |
| Sideline | 4 | 4 | 4 | 4 | 3 | 3 | – | 5 |
| Bowl | 4 | 4 | 4 | 5 | – | 4 | – | 5 |
| Crowd | 4 | 4 | 3 | 4 | 4 | 4 | 5 | 5 |
| Lighting | 4 | 4 | 4 | 4 | 3 | 4 | 5 | 5 |
| Sky | 4 | 4 | 4 | – | 3 | 5 | 5 | 5 |
| Broadcast | 4 | 4 | 4 | 4 | 4 | 4 | 5 | 4 |
| Moments | 4 | 4 | – | 4 | 4 | 3 | 5 | 5 |
| Audio | – | – | – | – | – | – | – | – |
| Experience | 3 | – | – | 4 | – | 3 | 4 | 5 |

Nothing scored below 3. Broadcast's Cost is 4 because the kick still runs at the
edge of its 25 parts. Experience's Read and Clarity are 3 because a resting panel
still reads as a floating label, and the field seat's tab lies over the border paint.
Audio is unscored: it cannot be screenshotted, and no listening pass was made here.

## Worst thing left, per shot

- `bowl-wide` — the visiting block is one contiguous wedge on the camera-facing
  side, so it reads bigger than it is: 18.0% of stand pixels against 9% of seats
  (integration-12 measured 27.8%).
- `field-level` — the border paint is clean but still lit a flat mid-grey, and the
  ribbon doubles where two segments meet when seen along its length.
- `tabletop` — the first launch after a cold simulator boot drew the room with no
  table model and "No board yet"; a retake with nothing changed is correct. Same
  miss as integration-12.
- `crowd-closeup` (club) — a few near fans hold arms up at 11:00 of the first
  quarter at 0–0, which is more than that moment earns.
- `crowd-closeup-clubLevel` — the far side is the visiting wedge, one flat rectangle
  of colour rather than a section with edges.
- `crowd-closeup-upper` — the fan at the aisle edge still shows shoes hanging past
  the tread.
- `crowd-closeup-endzone` — empty seats are scattered one by one inside a section;
  real ones come in blocks and along the aisles.
- `crowd-closeup-sideline` — the frame that was a wall of faces at integration-11
  now reads correctly; nothing worse than the wedge behind it.
- `crowd-closeup-field` — the Elsewhere tab sits over the painted border and reads
  as lying on the grass.
- `crowd-closeup-pressBox` — the desk and floor fill the right half of the frame,
  unchanged from integration-12.
- `lights-haze` — unchanged from integration-12: the haze reads, the banks burn.
- `sky-dome` — unchanged.
- `redzone-trails` — the drive panel clips at the frame edge; the trails themselves
  now lie on the grass, which is the integration-12 fix holding.
- `sideline-props` — the goal net still reads as a grid across the whole view from
  behind the posts.
- `td-moment-t0.5` — the gate holds: no banner, no ribbon flash, the crowd seated.
  But the *score* already reads CHI 17 while the ball is in the air, because the
  scorebug and board redraw from the spec, not from the moment.
- `td-moment-t5.1` — the near side is up and the ribbon flashes TOUCHDOWN whole.
  Fireworks are already gone by this frame.
- `td-moment-t8.5` — the banner is still up while the board has moved on to the
  next play ("J.Mason left end to MIN 31"), so the celebration outlives its play.
- `td-moment-p4-fg-club` — the visiting section brightens as one hard-edged
  rectangle on their kick.
- `td-moment-p6.5-fg-sideline` — FIELD GOAL flashes whole in the kicking club's
  purple and the scored-on side stays seated; the drive panel is clear of the
  ribbon, which integration-12's was not.
- `bowl-wide-p5-run` / `field-level-p5-run` — the carry hugs the grass and the ball
  is findable; the arcs behind it are earlier plays, correctly ghosted.
- `field-level-p4-short` — the ball's glow reads as a large bloom this close.
- `bowl-wide-p4-deep` — the arc and the lit ball both read from the upper deck, and
  RED ZONE flashes whole ("REDNE" is gone).
- `bowl-wide-p4-kickoff` — the kickoff arc draws; at this time the flight is already
  complete, so no ball is in the air. Broadcast's "invisible kickoff" was a shot
  timing artefact, not a defect.
- `bowl-wide-phi` / `field-level-phi` — the rule generalises: EAGLES and
  PHILADELPHIA in Eagles paint, Dallas nowhere on the grass. But Eagles midnight
  green sits close to Dallas navy at distance, so the two supports are hard to tell
  apart in a wide frame; the near rows read clearly teal.
- `lastweek-picker` — on screen for the first time (see below). Every row carries a
  reason and no score, and the Scores toggle is off by default.

## The picker, and why nobody had seen it

`feature/last-week-replay` reported the visionOS simulator could not reach the Mac's
API. It could. Two things were in the way, neither of them the network:

1. **An empty board hides the whole Live tab.** `CommandView` draws
   `ContentUnavailableView` "No board yet" when the board has no leagues, and that
   message says "Start the API on your Mac" only when `board.lastError` is nil — that
   is, when the API answered and had nothing to give. A look-dev database has no
   league, so the tab never drew, and the panel read like a connection failure.
   Seeding a board from the committed ESPN fixture (`tests/fixtures/espn_2025.json`,
   the way `test_end_to_end` builds one) fixes it: 2,550 roster rows, 170 matchups.
2. **`-openLastWeek` landed in the wrong mode.** It set `tab = .live`, but `LiveView`
   opens on My Team, and the picker is `GameFieldView`'s sheet. The flag exists only
   so the picker can be screenshotted, so it now selects Game mode.

Fixed here, minimally, in `LiveView.swift`. Also fixed: the header read "2,026 · Week 1",
because `Text` interpolates an `Int` with grouping — `Text(verbatim:)` now.

Serving `/api/lastweek?offline=1` needs a multi-event board on disk;
`week_slate_2026_2_1.json` staged as `scoreboard-week1.json` beside the replay
fixtures answers all 16 games with no network at all.

## Top 5 worst things left

1. **Moments / Broadcast — the score still leads the ball.** The gate holds the
   banner, fireworks, strobe and crowd until the play lands, but the scorebug and
   video board redraw from `c.spec` on arrival, so `td-moment-t0.5` shows CHI 17 with
   the return still running. `director/moment-timing` recorded where the change
   belongs; it is Broadcast's key/image. The red-zone flag has the same shape.
2. **Moments — the celebration outlives its play.** At `t8.5` the TOUCHDOWN banner is
   still up while the board has moved to the next snap. Holding the moment shifted
   its window without shortening it.
3. **Crowd — the visiting support reads as a painted wedge.** 18% of stand pixels for
   9% of seats, one contiguous block that brightens as a single rectangle on a
   visiting score, with empty seats scattered evenly inside it rather than in blocks.
4. **Experience — panels still touch the field at two seats.** The Elsewhere tab lies
   over the border paint from the field seat, and the drive panel clips at the frame
   edge in `redzone-trails`.
5. **Sideline — the goal net covers the view from behind the posts.** Unchanged since
   integration-11, and the one thing that still looks wrong in `sideline-props`.
