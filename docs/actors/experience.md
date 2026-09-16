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
- **Field kept clear.** Every panel's place comes from the dock (see "Panels per seat"): tabs and the pill on one rail, opened panels in the gallery, never on the field, the boards or the lights.
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

## Panels per seat: the dock

`scene.py`'s `seat_panels()` lays every panel out as one anchored layer, by the same rule from every seat, rather than letting each panel hunt its own gap. The numbers are `visual.experience.layout.dock`.

- **The rail** holds what is always there: the Drive tab (left, `rail.sideYawDegrees`), the Controls pill (centre) and the right-hand tab, on one line at `rail.distance`. It sits in the lowest clear band inside the comfort window. That is under the field's near sideline where there is room (club, field, endzone, sideline, clubLevel), otherwise between the far sideline and the ribbon (upper, pressBox), at the height nearest `rail.preferredBelowDegrees` in that band.
- **The gallery** holds what the wearer opens. The side panels open as a mirrored pair at one height and one distance; the controls open centred, as near the pill's height as fits. A panel that needs more room than its band moves further out, where it subtends less, up to `gallery.maxDistance`.
- **Hard rules, never costs.** A place is refused if its box:
  - covers the field's silhouette (plus `fieldMarginDegrees`), the video board, the ribbon or a rim light bank (plus `hardMarginDegrees`);
  - has its centre outside ±30° or below 33°, or its top above `highestBelowDegrees`;
  - overlaps another dock element that can be on screen with it;
  - stands further out than a chair back, an aisle rail, the ground or the press box glass inside it. Such a place is brought in front of the obstacle (less `nearClearanceMeters`) and drawn smaller by `scale`, so it subtends the same angle; never nearer than `minDistance`.
- **Near geometry** is `near_occluders()`, from the scene's own seating plan and Bowl's kit numbers (`NEAR`, held to `tools/blender/bowl/` by a test).
- **Output.** `layout.perSeat.<seat>.<panel>` is the open place (`yaw`, `distance`, `height`, `scale`), `tab` (the same fields), `folded` (starts folded) and `clear` (it has an open place that obeys every rule), plus `rail` and `scorebugHidden`. A panel with no clear place would start folded and open over its tab only when asked; today every panel is clear from all seven presets, and a test holds that.
- **Swift** (`StadiumSpaceView.placeDock`) draws each attachment at its tab while folded and at its open place while open, with its scale, and moves it when the seat or the fold changes. Before this it placed each attachment once per seat, so a folded tab sat at the middle of the panel it folded from. That was the floating Elsewhere tab over the stands from the club seat and among the light banks from the upper deck and the press box.
- **Cost.** The layout solves once per field on a half-degree view grid and is cached. It adds about 1.5 s to the first scene built for a field; every later build reuses it.

| Seat | Rail (below eye, distance) | Side panels open (yaw, below, distance, scale) | Controls open |
|---|---|---|---|
| club | 31.5°, 1.25 m | ±30°, 2.5° below, 1.80 m | 0°, 32.5°, 1.50 m |
| field | 26.0°, 1.25 m | ±30°, 22.0°, 1.35 m | 0°, 26.0°, 0.90 m |
| endzone | 29.5°, 1.25 m | ±30°, 0.5°, 1.80 m | 0°, 32.0°, 0.95 m |
| upper | 13.0°, 1.25 m | ±30°, 9.0°, 1.80 m | 0°, 11.5°, 0.90 m |
| sideline | 29.0°, 1.25 m | left −30°, 1.0° above, 1.60 m; right 30°, 22.0°, 1.86 m ×0.93 | 0°, 31.0°, 0.90 m |
| clubLevel | 32.5°, 1.25 m | ±30°, 5.0°, 1.80 m | 0°, 7.5°, 0.90 m |
| pressBox | 17.5°, 0.92 m ×0.74 (inside the glass) | ±30°, 14.5°, 0.96 m ×0.48 | 0°, 16.5°, 0.86 m ×0.90 |

The sideline seat is the one without a mirrored pair: the ribbon dips on its right, so the right panel opens low over the rows in front, nearer than the chairs.

### Contract change for the ports and Broadcast

- **Ports:** `perSeat` panels gain `scale`, `clear` and `tab`, and `rail`. The web and Android ports should draw a folded panel at `tab`, not at the open place, and apply `scale`. `layout.search` is gone; `layout.dock` replaces it.
- **Broadcast:** `panelSizes.trailing.maxHeightPoints` is now 400, the same as the drive log's, so the side pair opens at one height. The Elsewhere list measures about 394 pt at six rows. `panelSizes.drive` is unchanged.

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

## Integration-11 polish (`docs/lookdev/integration-11-polish/`, before in `before/`)
- **Panels avoid the boards, not only the field** (`scene.py` `seat_panels`):
  - **Video board:** a panel may never cover it. `video_board_points` samples its face (only when it faces the wearer) and the search skips any box holding one.
  - **Ribbon:** `ribbon_points` samples it all the way round, and a box over it costs `search.ribbonCost` (20°) of movement. It moves off when a nearby place is free and stays when the only alternative is folding.
  - **Result:** the upper, clubLevel and pressBox side panels rise above the ribbon, where before they sat across it (`before/s-bowl-wide.png`). Club, field, sideline and endzone are unchanged.
- **Folded tabs no longer fall back onto the field.** A tab with no room in its panel's own search took its default slot, which from the upper deck put the Controls pill on the fifty (`before/s-bowl-wide.png`). A tab now searches the whole comfort window (±30°, 33° below to 12° above). `test_no_open_panel_covers_the_field_from_any_seat` now checks folded tabs, and the board, too; `test_the_board_test_sees_a_panel_over_the_board` checks the check.
- **Budget:** stadium 0 parts; tabletop 6 parts / 2.9k triangles. Unchanged.
- **Worst thing left:**
  - `bowl-wide`: the Controls pill is now off the field but dead ahead over the far lower stands, and the drive log sits up by the rim light banks. Both are inside the limits, but the drive log crosses a bank. From the upper deck the only place off the field and the ribbon is high.
  - `crowd-closeup`: the Elsewhere tab still floats over the far stands. It is inside the limits and off the field; it is just the only place a tab fits from the club seat.
  - `tabletop`: unchanged.

## Round 4: the dock (`docs/lookdev/experience-r4/`)

**Asked for:** panels that read as a deliberate, anchored layer from every seat, after integration-11 found:
- pills on the grass (field seat), on a chair in the row in front (sideline) and at the wearer's feet (redzone-trails);
- the drive panel across the ribbon in both field-goal shots;
- the controls pill dead ahead and the drive log across a light bank (upper);
- the Elsewhere tab floating over the stands (club).

**What was wrong:**
1. **Tabs at the open panel's centre.** The app placed each attachment once per seat, so a folded tab was drawn at the middle of its open place. The Elsewhere panel starts folded, which put its tab above the eye over the stands (club) and among the rim light banks (upper, press box).
2. **The ribbon was a cost, not a rule.** A panel could pay 20° to stay on it.
3. **No near geometry.** From the press box the glass is 0.91 m out, and every panel stood outside the window.

**What changed:** the dock above. Tabs have their own places, the ribbon and the light banks are hard rules, and near geometry is modelled and respected.

**Evidence:** placement plots, not renders. `placement/before-<seat>.png` and `placement/after-<seat>.png` draw each seat's view in angle space (yaw across, degrees below the eye down):
- the field in green, the ribbon in orange, the video board in purple, the rim light banks in yellow, and near geometry in grey;
- the comfort window dashed;
- each panel's box as the app draws it: integration-11 with tabs at their panel's slot, then the dock with open panels solid and the rail outlined.

**Gates.** Xcode.app was updated to 27.0 mid-round and its licence was accepted before this pass:
- **`make test`:** 556 tests OK.
- **`verify_scene`:** 15 scenes, 1,422 arcs, 59,515 assertions OK.
- **`contrast_check`:** OK.
- **`xcodebuild`** (visionOS 27.0 simulator SDK, own derived data `.work/dd-exp`): BUILD SUCCEEDED, one warning - the AppIntents metadata notice integration-11 already recorded. No warning from this change, and none new from Xcode 27 in this target.
- **Budget:** Experience 0 draw parts, 0 triangles, as before. Stadium 87-97 parts, 183-245k triangles across the run.

**Shots** (`docs/lookdev/experience-r4/`, own simulator clone `fe-exp-r4`): `main/` (tabletop, bowl-wide, field-level, crowd-closeup, redzone-trails, sideline-props), `seat-<id>/` (crowd-closeup from the other six presets), `td/` (touchdown at 0.5, 5.1 and 8.5 s) and `fg-club/`, `fg-sideline/` (the field goal). Review-sized `s-*.png` as usual; full frames are not committed.

**Verdict per seat, from the renders.**
- `club` (`main/s-crowd-closeup.png`, `main/s-redzone-trails.png`): the rail reads as a pair of small pills tucked low among the near rows, not as UI dropped at the wearer's feet. The risk I flagged from the plot does not appear in the render. The drive log opens between the ribbon and the far sideline and no longer crosses the ribbon.
- `field` (`seat-field/s-crowd-closeup-field.png`): the Elsewhere tab sits low over the painted border, a metre and a quarter in front of a wearer whose turf is two and a half metres out. It keeps off the playing surface, and in stereo it is plainly nearer than the paint, but a flat frame still reads it as lying on the white. Worth a look on device before anything is changed for it.
- `endzone` (`main/s-sideline-props.png`): not crowded. The glass scorebug yields to the video board, the drive log sits well left over the stands, and the pill and tab are low and central-bottom. The board, the ribbon and the goal posts share the upper middle without a panel among them.
- `upper` (`main/s-bowl-wide.png`): the clearest improvement. The drive log, the pill and the Elsewhere tab sit on one line between the far sideline and the ribbon, where in integration-11 the tab was among the rim light banks and the pill had fallen onto the fifty. The pill is dead ahead, which is the cost of the upper deck having no clear band under the field; it is small, translucent, and over the far stands rather than the play.
- `sideline` (`seat-sideline/s-crowd-closeup-sideline.png`): nothing on the chair in front any more. Turned 55° for this shot the dock is off frame to the left, which is correct - the rail is anchored to the seat's own forward, not to where the head is turned.
- `clubLevel` (`seat-clubLevel/s-crowd-closeup-clubLevel.png`): the tab is low over the near rows, clear of the video board and the ribbon above it.
- `pressBox` (`seat-pressBox/s-crowd-closeup-pressBox.png`): the tab is inside the glass at 0.92 m, drawn at ×0.74. It subtends what the club seat's tab does, and in the frame it reads as a small label over the bowl. Stereo depth and legibility here are the one judgement a simulator frame cannot make.
- **Moments** (`td/s-td-moment-t5.1.png`, `fg-club/`, `fg-sideline/`): the panels yield as they should - at 5.1 s into the touchdown nothing is up but the scorebug and the win-probability horizon. Through the field goal the drive log sits in the gap between ribbon and field instead of across the ribbon, which was integration-11's fault at both seats.

**Nothing was changed after the renders.** Every risk I listed from the plots either did not appear (club, endzone) or is inherent to the seat and within the rules (upper's centred pill, the press box's near panels), and the one that half-appeared - the field seat's tab over the border paint - is a flat-frame artefact of a panel that is genuinely nearer than the paint. Changing the layout for it would trade a real comfort win for a screenshot.

**Worst thing left:**
- `field`: the tab over the border paint, above.
- `upper`: the pill dead ahead. Only a band under the field would fix it, and the upper deck has none.
- `pressBox`: everything inside the glass at ×0.48-0.74. Needs a device.
- All seats: a panel resting at `restOpacity` over a busy crowd reads as a floating label in a still frame; hover brightening, which the simulator cannot show, is what separates it in use.

**Found for the director:** the renderer's wearer eye is not Bowl's near-patch eye. `presentation.stadium.seats[].y` is the tier height at the seat's offset, which from the club seat is the tread of the row in front (12.16 yd). Bowl's `structure.presets()` puts the eye on the seat's own row tread plus 1.26 m (14.16 yd against the renderer's 13.47 yd). The near check uses the renderer's eye, since that is where the wearer is, but the modelled "own seat" gap and the chairs around it were cut for Bowl's.

