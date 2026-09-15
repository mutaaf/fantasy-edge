# Experience: arrival, seats, controls, the table

Owner: the Experience specialist (`actor/experience`). Files:
- `Actors/Experience/**`, plus `StadiumHost.swift` and `StadiumPassage.swift`
- `presentation` in `fantasyedge/scene.py`
- `visual.experience` in `design/tokens.json`
- `tests/test_experience.py`

## What it is meant to feel like

Walking into a night game, not loading one.

- **Arrival.** The table's "Enter stadium" raises a curtain of floodlight from the plinth's edge, with a bright lip, widening by `arrival.gateWiden` while the table dims to `arrival.tabletopDim`. The space then opens on the Crown dial.
- **Head never moved.** Nothing moves the wearer's head. The world turns about them, and only on their own action: a seat change, a pinch on the table.
- **Crown hint.** The first time the stadium opens on the dial, a hint names the Digital Crown for `crownHintSeconds`, once.
- **Field kept clear.** Every panel's place is a slot in `visual.experience.layout`, low and to the side.
  - **Rest.** Panels rest at `restOpacity` and come up to `hoverOpacity` when looked at (the system's hover state; the app never learns where you look).
  - **Folding.** The side panels fold to 60-point tabs. The controls fold to a pill after `controls.autoHideSeconds` untouched, and come back on a tap of the pill or a pinch out on the field.
  - **Moments.** A celebrated moment folds every panel and fades the tabs to `panels.momentOpacity` (reduce motion: folds, no fade), leaving the scorebug and Broadcast's world banner. `panels.momentReturnSeconds` after the banner goes, each panel returns as the wearer had it.
- **Seats.** Chosen on a map of the bowl drawn from `bowl.shape` and `presentation.stadium.seats`, each a 60-point target. The seat change fades through dark (reduce motion: a cut), and the last seat is remembered.
- **The table.**
  - **Plinth.** A bevelled stone plinth with a lit rim and a thin edge light in each club's colour, home along the home half, plus a grounding shadow.
  - **Pinch.** Pinch to scale (`tabletop.minScale`–`maxScale`, never past 1, or the volume clips the bowl) and turn about the vertical.
  - **Look closer.** Tips the model `closerTiltDegrees` toward you.

## Seat presets (`presentation.stadium.seats`)

| id | label | notes |
|---|---|---|
| `club` | 50-yard line, lower bowl | default; shots `crowd-closeup`, `lights-haze`, `sky-dome`, `td-moment`, `redzone-trails` |
| `field` | Field level, home sideline | shot `field-level` |
| `endzone` | Behind the home end zone | shot `sideline-props` |
| `upper` | Upper deck, midfield | shot `bowl-wide` |
| `sideline` | Lower bowl, home 30 | new |
| `clubLevel` | Club level, midfield | new: last rows of the lower bowl, under the overhang |
| `pressBox` | Press box, far side | new: floor level with the press box glass (`bowl.pressBox.rise[0]`) |

Each seat also carries `view: {group, distanceYards, heightYards}` for pickers.

## Hook contracts for other actors

### Moments & Audio: `ExperienceEvents`

Experience posts on `NotificationCenter.default`, name `ExperienceEvents.name` (`"fe.stadium.experience"`), with `userInfo["event"]` an `ExperienceEvent`. Audio scores these beats; Experience never plays a sound.

| Event | When | Suggested score |
|---|---|---|
| `.gateOpening(seconds:, swellLead:)` | the gate starts over the table; the space opens `seconds` later (0 with reduce motion) | start the crowd bed swelling `swellLead` before the space opens, quiet in the table mix |
| `.arrived(seat:, full:)` | the stadium's scene is first readable | settle the bed at the seat's position |
| `.seatChanging(to:, fadeSeconds:)` | a seat change starts; the world is dark at `fadeSeconds` | duck the bed through the dark, re-place emitters for the new seat |
| `.panelsYielded(Bool)` | a moment took the panels away (`true`) or gave them back | none required; lets Moments align its choreography with a clear view |
| `.leaving` | Leave stadium pressed | fade the bed out |

### Broadcast: panel footprints

`visual.experience.layout.panelSizes` is the contract, in points. Each panel is exactly `widthPoints` wide and at most `maxHeightPoints` tall, and the stadium clamps it (top-aligned, clipped).

| Panel | Width (pt) | Max height (pt) |
|---|---|---|
| drive | 460 | 400 |
| trailing | 420 | 450 |
| controls | 700 | 160 |
| folded tab | 180 | 64 |

Broadcast's drive log (5 rows, at most 360 pt) fits. Its test should read `panelSizes.drive.maxHeightPoints`.

### Broadcast: the glass scorebug yields to the video board

`layout.perSeat.<seat>.scorebugHidden` is true when `bowl.videoBoard` faces the wearer, sits within `scorebugYield.inViewDegrees` of straight ahead, and subtends at least `boardMinDegrees`. Today that is only the `endzone` seat.

## Panels per seat

`scene.py`'s `seat_panels()` works out each seat's drive, trailing and controls places.
- **Search:** from the default slot, it looks for the nearest spot inside the comfort limits (±30°, at most 33° below) whose angular box stays outside the field's projected silhouette (end zones included, plus `search.marginDegrees`).
- **Controls:** dead ahead, so they never climb above `search.controlsHighestBelowDegrees`.
- **No room:** a panel starts folded, and its tab is placed the same way.
- **Output:** the scene carries the result as `visual.experience.layout.perSeat`.
- **Swift:** moves the attachments when the seat changes and applies the folds.
- **Test:** `tests/test_experience.py` asserts no open panel overlaps the field from any of the seven presets.

| Seat | Drive / trailing below eye | Controls |
|---|---|---|
| club, endzone, sideline | about −1° to −4° (just above the eye, over the stands) | low, or folded |
| upper, clubLevel, pressBox | 1° to 11° | folded |
| field | 24–25° | 30° |

### Director: seat previews in `SceneSpec`

`SceneSpec.SeatOption` doesn't decode `view` yet. The picker shows the seat's label and its floor height (`y × metersPerYard`) until it does. Proposed: `public let view: SeatView?` with `SeatView { group: String; distanceYards: Double; heightYards: Double }`, lenient.

## Debug launch arguments (debug builds)

| Argument | Effect |
|---|---|
| `-arrivalAt <0…1>` | freezes the gate part-way open on the tabletop |
| `-stadiumPicker` | opens the seat picker on arrival |
| `-stadiumHint` | shows the Crown hint regardless of the once-only flag |
| `-stadiumUnfold` | starts with both side panels unfolded |
| `-stadiumControlsFolded` | starts with the controls folded to the pill |

Combine with `tools/lookdev.py --extra … --suffix …`.

## Needs a device

These can't be verified in the simulator:
- Pinch-to-scale and turn on the table.
- The pinch on the field that reveals the controls.
- The Crown dial.
- Hover brightening (the simulator's pointer hover is not gaze).
- Comfort of the lowered panels.
- The grounding shadow's look on a real table.

## Critique log

Before and after shots are under `.work/shots/experience-*` in the Experience worktree. The baseline is `docs/lookdev/integration-2/` and `integration-3/`.

**Before (integration 2 and 3):**
- `s-td-moment`: the Elsewhere panel floats in front of the play and the controls cover the lower-left of the field.
- `s-field-level`: the drive log and Elsewhere sit across the near sideline.
- `s-tabletop`: the model is a wide, low single deck; the ornament, centred on the volume's front edge, covers its front; the win-probability labels float above the model.

**Iteration 1 (`experience-it1`).** Invalid as evidence: I merged `a71facc` mid-shoot, so the API served merged tokens and assets to a pre-merge build. `td-moment` couldn't decode and the tabletop drew nothing. Lesson: never change tokens or merge while a shoot runs; the API reads `tokens.json` live.

**Iteration 2 (`experience-it2`, build `440ae1e`).**
- **`td-moment`:** the field is clear. Elsewhere starts folded, and during the touchdown every side panel yields. The scorebug and banner stay.
- **`tabletop`:** at 4 mm per yard on the 1.12 m volume, the model fills the table, with the bevel and club edge light visible.
- **`tabletop_gate`:** the disc read as frosted glass under room light, not as floodlight. Replaced with a curtain along the plinth edge in iteration 3.
- **`field-level_down` / `_left`:** the controls are too wide (seat label, 300-point segmented control), and the drive log at −30° crowds into them. Iteration 3 narrows the controls and moves the side panels to 1.25 m.
- **`bowl-wide_picker`:** the map is small, and four seats cluster on the home sideline. Iteration 3 adds a list beside the map.
- **`field-level*` render black:** the scene was still building when the screenshot fired (see "Look-dev under load").

**Iteration 3 (`experience-it3`, build `4ef314b`, stopped part-way).**
- **`crowd-closeup_picker`:** the picker lists all seven seats beside the map, each a 60-point row with its height. The panel stretched wider than its content, so it now has a fixed size.
- **`crowd-closeup_down` / `_ahead`:** the controls are one compact panel (Dial/Full toggle, Leave, fold), and the drive log at −30°, 1.25 m clears them.
- **Every stadium frame black at a 10 s settle:** re-shooting at 28 s.

**Iteration 4 (`experience-it4`, build `3ff272f`).**
- **`td-moment_yield`:** during the touchdown every panel folded and faded. Only the scorebug stays, with nothing between the wearer and the play.
- **`crowd-closeup_ahead`:** the drive log and Elsewhere rest translucent, low and to the sides; the controls have folded themselves away; the centre is clear.
- **`crowd-closeup_picker`:** the picker is compact, with the map and the seven seats side by side.
- **`field-level`:** renders at a 28 s settle.
- **Bug: the tabletop volume sat in the middle of the stadium in every frame.** visionOS restores the tabletop on relaunch with no value (the host shows it as the replay), so `dismissWindow(id:value:)` missed it. The passage now dismisses by id as well.
- **`bowl-wide_press`:** the press box seat looks into the back of the lower bowl. Its floor (19.8 yd) is level with the lower bowl's top rows (19.6 yd), so the heads in front and the box's own sill hide the field. See "Found for other actors".

**Iteration 5 (`experience-it5`, build `b3f1dc2`).**
- **Tabletop:** gone from the stadium in every frame.
- **`crowd-closeup_ahead`:** the drive log and Elsewhere rest low at ±30° and translucent. The controls folded to the `Controls` pill on their own. The field from sideline to sideline is clear.
- **`td-moment`:** only the scorebug is up; the play is unobstructed.
- **`field-level`:** a clean look down the field. The drive log sits in the lower-left corner and the Elsewhere tab in the lower right.
- **Budget:** stadium 0 draw parts. Tabletop 6 parts and 2.9k triangles, plus 3 parts for the gate while it opens. Budget is 5k triangles and 10 parts.

**Iteration 6 (`experience-it6`, build `cfe35ad`), `redzone-trails` from all seven presets.**
- **`pressBox`:** the drive log sits over the far stands and the controls pill above the field's far sideline; the field is clear.
- **`club` / `clubLevel` / `upper` / `sideline`:** the side panels sit over the stands, just above the field's far edge.
- **`field`:** panels over the near apron.
- **`endzone`:** the glass scorebug has yielded to the video board.

## Found for other actors

**Bowl: the press box sits too low to see the field from.** `bowl.pressBox.rise[0]` (19.8) is barely above the lower tier's top (19.6). A real press box looks over the last rows. Proposed: raise the box's floor about 3 yd above the lower bowl's top, or move it back over the concourse. The `pressBox` seat preset takes its floor from `pressBox.rise[0]`, so it follows automatically.

## Look-dev under load

A black stadium with panels showing is the renderer still preparing assets
(26 textures, the probe, 42 models) when the screenshot fires. It happened
at every seat in iterations 2 and 3 once several agents were building and
shooting at once; the shots that rendered were the ones with a longer wait
(`td-moment` holds 6 s more). Experience's shots now settle 28 s. An earlier
note here suspected the crowd at the `field` seat; that was this, not a bug.
