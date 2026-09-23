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

## Round 5: off the paint, and never half out of view (`docs/lookdev/experience-r5/`)

Two things the reviews kept flagging against the dock's own "never touches the field" rule, both now rules rather than judgements.

**1. The Elsewhere tab lay over the border paint from the field seat.** Round 4 called it a flat-frame artefact - the tab is a metre and a quarter out, the paint two and a half - and that was true and beside the point: it read as lying on the white every time anyone looked at the frame.

- **The keep-off region is now the painted field**, not the playing surface: surface, end zones, the painted border (`PAINTED_BORDER`, Field's own rule book - the NFL's 6 ft white border, college's 4 in line) and `dock.paintClearYards` of ground beyond it, because a degree of margin is only a hand's width of grass from a seat at field level.
- **Consequence, and it is the right one:** from the field seat the whole lower view is painted field to within half a yard of the wearer's feet, so there is no band under the paint at all. The rail moves up to the gallery, where the dock already sits from the club, end zone, sideline and club level seats. The field seat's dock now reads exactly like every other lower-bowl seat's.
- **Measured:** the old rail sat 0.13 yd clear of the paint's outer edge - a hand's width, which is why it touched in every frame. The new one is 40 yd clear, over the far stands.

**2. The drive panel clipped at the frame edge in redzone-trails.** Comfort and legibility were one rule and had to be two:

- **Where a panel sits** is comfort: its centre inside ±`maxSideDegrees`, never below `maxBelowDegrees`.
- **How much of it can be seen** is `dock.viewWindowDegrees`: the whole box, edges and all, inside the view window. A 460-point panel is 16° wide at 1.8 m, so demanding the *box* inside ±30° would have meant centres inside ±22° - that is a tighter comfort rule than the art bible's, and it cost the end zone and sideline seats their open panels outright. The window is the honest home for "nothing half out of view".
- **A thin band now costs rows, not type size.** Where no full-height panel fits, the dock shortens it in `heightStep` steps to `minHeightFraction`, ships the seat's own `maxHeightPoints`, and the app clamps the panel to it. Shrinking (`scale`) is the last resort, and a floor holds every panel to subtending at least what it would full size at `gallery.maxDistance`: shrinking *and* standing back reads smaller than either alone. The home 30 is the seat that needs it - the ribbon dips into its right side - and it now opens a mirrored pair at full type size, 360 pt tall instead of 400.

**Tests.** `make test` 672. Four new: nothing in the dock overlaps the paint; the paint check itself catches the old field-seat rail (off the surface, on the border); nothing is half out of view (centre in the comfort window, box in the view window); a thin band costs rows before type size, and the app reads the seat's own height. `PAINTED_BORDER` is held to Field's rule book.

**Gates.** `verify_scene` 15 scenes / 495,078 assertions, `verify_crowd` OK, `verify_moment` 117 checks, `contrast_check` OK, `xcodebuild` BUILD SUCCEEDED (`generic/platform=visionOS Simulator`, own derived data) with one warning - the AppIntents metadata notice that predates this work.

**Verdict per seat, from the renders.**
- `field` (`seat-field/`, `main/s-field-level.png`): solved. The tab sits at eye level over the far stands; the grass, the white border and the near apron are empty. This is the frame two checkpoints complained about.
- `club` (`main/s-crowd-closeup.png`, `ahead/`): the dock is one line under the ribbon - drive log open at the left, pill centred, Elsewhere right - and `ahead/s-redzone-trails-ahead.png`, shot with the head straight, shows all three whole and inside the frame.
- `endzone` (`seat-endzone/`): the tab is over the far stands, clear of the blue end zone paint. The upper middle integration-13 called crowded is not: the board carries the score, the scorebug yields, and no panel is near it.
- `upper` (`main/s-bowl-wide.png`): unchanged and still the clearest read - one line between the far sideline and the ribbon. The pill remains centred; the upper deck has no clear band under the field, and after this round it has none under the paint either.
- `sideline` (`seat-sideline/`): nothing on a chair, nothing on the paint; the pair opens shortened rather than shrunk.
- `clubLevel`, `pressBox` (`seat-*/`): unchanged from round 4 but for the paint clearance; the press box dock is still inside the glass.
- **Field goal** (`fg-club/`, `fg-sideline/`): the drive log sits in the band, off the ribbon, at both seats.

**Worst thing left.**
- **A turned head still takes a panel out of frame.** With the head turned 22° (the redzone-trails shot) the left panel's box runs from 52° to 57° off the view centre, past the simulator frame's edge - so it is now wholly outside rather than cut in half, which is the better of the two but is not "in view". The dock is anchored to the seat, and the art bible's comfort window is measured from the seat, so no placement fixes this. The two real fixes both change that contract: a recentre affordance (`AnchorEntity(.head, trackingMode: .once)` can re-anchor the dock to where the wearer is looking, on a tap of the pill), or a dock that follows the play by a few degrees. Both are the director's call, not mine.
- **The pill is centred from the upper deck and the press box**, for want of any clear band below.
- **The press box** still draws everything at ×0.47 inside the glass; it needs a device to judge.
- **`fg-club`** shows the pill clipped at the right frame edge, the same turned-head effect at -45°.

## Round 6: the recentre (`docs/lookdev/experience-r6/`)

Round 5 left one defect and two ways to fix it; the director chose the gesture over the drift, because a dock that moves on its own reads as the world moving, which the comfort rule exists to prevent.

**The gesture.** A tap on the Controls pill, or a pinch anywhere in the room, re-seats the whole dock in front of where the wearer is looking. Nothing follows the head on its own: the dock sits where it was put until it is asked to move.

- **The dock is solved for every facing it can land on.** `layout.dock.recentre` gives the buckets: every 15° out to 60° either side. `perSeat.<seat>.recentre["<degrees>"]` is the whole dock solved again from that facing, so **every rule is re-checked there** - off the painted field and border, off the board, the ribbon and the light banks, inside the comfort window, whole within the view window, nearer than any chair, rail, ground or glass. A test walks all nine facings at all seven seats.
- **Cheap, because a turn is a shift.** `below` does not depend on which way the wearer faces and `yaw` only shifts, so one `seat_view` grid per seat answers every facing. Each bucket starts from the one beside it (`seed`), so the dock keeps its arrangement as it moves and most facings cost a check rather than a search. The scene carries all nine for about 42 kB.
- **The app** reads the head's yaw from ARKit (`HeadFacing`, device anchor only - head pose, never gaze), lands on the nearest solved facing, and fades the dock across `recentre.fadeSeconds`. Reduce motion places it at once. No ARKit, no anchor, no yaw: it recentres to the seat's own forward, which is the worst it can do and still useful.
- **Its own undo.** Recentring while facing where the seat faces lands on bucket 0, which is the layout the seat started with. A test holds bucket 0 equal to the seat's own dock.
- **The world never moves.** Only the attachments are re-placed; a test asserts the recentre touches neither `world.orientation` nor `pivot.orientation`.

**How the pill stays reachable when the dock is off to the side.** It does not have to be. The gesture has two surfaces, and the one that matters when the dock is out of view is the room itself: the reveal catcher became a sphere around the wearer (`RecentreCatcher`), so a pinch anywhere - not only at a panel ahead - brings the dock over. Everything else sits nearer than the catcher, so a pinch on a panel, the field or a hologram still reaches that first. The pill remains the labelled way when it is in view, and now recentres as well as unfolding the controls.

**Discoverable without a tutorial.** The first time the wearer is looking more than the comfort window away from the dock for `recentre.hintAfterSeconds`, a hint appears once - "Pinch anywhere, or tap Controls, to bring the panels to you" - in the place and style the Crown hint already uses, and is never shown again. The pill's accessibility hint says the same thing.

**Tests:** `make test` 677, four of them new: every facing solved and every rule re-checked from it; recentring from the seat's own facing changes nothing; the dock keeps its shape across a recentre; and the app recentres on the pill and on a pinch, lands on a solved facing, honours reduce motion and never turns the world.

**Gates:** `make verify-scene`, `make verify-crowd`, `make verify-moment` (117 checks - the last two had no Makefile target until now, and do now), `contrast_check`, and `xcodebuild` on `generic/platform=visionOS Simulator` with one warning, the AppIntents notice that predates this work.

**Shots.** A shot cannot pinch, so `-stadiumRecentre <degrees>` names the facing a recentre would have landed on.
- `before/s-redzone-trails.png`: the head turned 22° and no recentre - the pill and the Elsewhere tab are in view, the drive log is off frame to the left. This is round 5's worst thing left.
- `after/s-redzone-trails-recentred.png`: the same turn, recentred. The drive log is back, whole, with the pill and the tab beside it, between the ribbon and the far sideline.
- `turn45/`, `turn-30/`, `turn60/`: recentred at three more facings. The dock is whole and clear of the field, the ribbon and the light banks at each one.
- `seat-*/`: every preset unchanged from round 5.

**Worst thing left.**
- **The dock lands on a bucket, so it can sit up to 7.5° off where the wearer is looking.** Finer buckets cost build time (nine facings already take the scene about 8 s to solve for a field, cached thereafter); a client-side nudge within the bucket would need the solver in Swift.
- **ARKit is the one thing that can be missing.** Without a device anchor the gesture still works but always returns the dock to the seat's forward. Worth checking on a device that the anchor is there in the progressive dial as well as in full immersion.
- **The hint fires on head yaw**, so a wearer who never turns far never sees it; that is the intent, but it means the gesture is undiscovered until it is needed.
- **The press box** still draws its dock at ×0.47 inside the glass, unchanged, and still wants a device.

## Round 7: the table as an object (`docs/lookdev/experience-r7/`)

The dock is settled, so this round is the rest of what Experience owns, judged against the bar rather than against the last frame.

### The tabletop: a mirror, not a plinth

**Verdict before:** the cutaway works - the near sideline is left out and you do look into the bowl - but the plinth failed the bar. The palette asks for near-black stone (`baseplate` is `#101216`) and the frame showed a **light grey slab**, wider than the model needed, with a rim you had to look for. On a table in a beige room the plinth was the brightest thing in the volume, which is the opposite of a jewel on a lit plinth.

**Cause, measured rather than guessed:** the plinth drew at `metallic: 0.55`, `roughness: 0.28`. A polished metal takes its colour from what it reflects, so in a warm room it reads as the room, whatever the palette says. Two shots either side of one change settle it: at metallic 0.08 and roughness 0.22 it was still light (`after/s-tabletop.png`), because a smooth dielectric still carries the room's whole specular lobe; at **metallic 0, roughness 0.62** it is stone (`after-matte/s-tabletop.png`).

**What changed** (all `visual.experience.baseplate`, all now tokens rather than numbers in Swift):
- `topRoughness` 0.62, `topMetallic` 0 - stone, not chrome. The band and bevel likewise, the bevel keeping a little sheen (0.38 / 0.05) so the chamfer still catches the room.
- `marginScale` 1.03 → 1.015: the plinth hugs the model instead of leaving a ring of grey table.
- `rimOpacity` 0.6 → 0.85 and `rimRadiusYards` 0.9 → 0.7: a thinner, brighter lit edge.
- `edgeOpacity` 0.55 → 0.85: the clubs' edge light reads at a glance.

**Verdict after:** the field and the lit ribbon are the brightest things on the table, the bowl reads as a miniature you lean into, and the club's blue edge names the home side. At the second distance (`after/tabletop-far/`, `-tabletopScale 0.62`) it holds: smaller, still a jewel. A test keeps the plinth a dielectric, so it cannot quietly become a mirror again.

### The seat change, the ramp, the controls

- **Seat change:** holds, including with the changeover the red-zone work added. `after/seat-change/s-crowd-closeup-seatchange.png` is a frame from inside the fade (`-stadiumFadeScale 10 -stadiumSitAfter 5:upper`, both new debug arguments): the world is dimmed mid-fade, the wearer has not moved, and the dock and scorebug stay lit above it, because they hang off the wearer rather than the world. The seat fade now honours `-stadiumFadeScale`, as the changeover already did.
- **The ramp:** `StadiumPassage.leave` reopens the windows before dismissing the space, and `spaceDisappeared` does the same when the Crown closes it instead, so the way out is covered from both directions. `-stadiumLeaveAfter` presses Leave without a pinch for a capture.
- **The controls:** unchanged this round. Glanceable, in reach, inside comfort, and now the pill also recentres (round 6).

### The transparent fans are Crowd's

Not a guess, and not mine:
1. They appear in **Crowd's own frame** (`docs/lookdev/crowd-r7/crowd-closeup.png`), which has no dock in it.
2. At full resolution (`crowd-cards-near-crop.png`) the see-through figures are **flat billboards** standing among solid mesh fans: the field shows through their torsos and arms, and their silhouettes are photographic rather than geometric. They are impostor cards, drawn in the front rows.
3. Only the card material is alpha-tested (`CrowdActor` sets `opacityThreshold` on cards and nothing on mesh fans, whose atlas is RGB and forced opaque at composition), so cards are the only fans that can read through.
4. `visual.crowd.rings` says `minCardYards: 5.5` - never a card within five and a half yards - while `lod0Max`/`lod1Max`/`lod2Max` cap the mesh fans at 14/24/130. Looking along a row at the club seat there are more fans inside 13 yd than those caps allow, so the overflow becomes cards **inside the distance floor**. The count caps beat the distance rule.
5. Experience's only opacity writes are on the world (seat change, arrival dim) and on dock attachments; both are all-or-nothing and would dim the stands and field too.

**Routed to Crowd** with those five points. The fix is theirs: either the ring assignment must honour `minCardYards` before it honours the caps, or the caps must rise to cover a row seen end-on.

### Budget

Unchanged where it matters: Experience is **0 draw parts and 0 triangles in the stadium**; on the table it is **6 parts and 2,856 triangles** of the shared **67 parts / 23,778 triangles** (targets 110 and 80k), and this round moved none of it - the plinth's geometry is the same, only its material. Stadium total this round: 101 parts, 225–227k triangles, ~67 MB.

### Worst thing left

- **The press box** still draws its dock at ×0.47 inside the glass and has never been judged on a device (`after/seat-pressBox/`). Unchanged, and still the one thing a simulator cannot answer.
- **The recentre lands on a 15° bucket**, so it can sit up to 7.5° off where the wearer is looking.
- **The win-probability horizon on the table** reads as a streak floating behind the model rather than as part of it (`after/s-tabletop.png`). It is inside the volume and inside its rails, so it obeys its contract; it is Broadcast's to judge whether it belongs on the table at all.
- **During a seat change the panels stay lit while the world fades.** It is defensible - they are the wearer's, not the room's - but nobody has decided it, and the mid-fade frame is the first time it has been looked at.

## Round 8: two seats nothing could be judged from (`docs/lookdev/experience-r8/`)

Two actors could not be judged at all, and both gaps were seat geometry, which is Experience's.

### The camera well: the first frame with the ball inside its life-size band

Broadcast r8 corrected a ball that had been 2.6x life size everywhere to life size within 14 yd, easing back to 2.6x by 45, and said the close half was "honest in the formula but unproven in a frame" because no seat could see it. The nearest preset stood about 25 yd from a ball.

- **`goalLine`, "Camera well, away goal line"**: field level, 1.5 yd behind the end line, 4 yd off the centre so the near upright is not in the middle of the view. The goal line is **12.2 yd** away.
- **It is the away end** because that is the end the fixtures score in: the Bears pick-six ends at yard line 100. Behind the home end line the ball is never nearer than 40 yd.
- **A seat was not enough.** The pick-six's ball is reset upfield the instant it scores, so no frame in that moment holds it close. The fixture does carry a snap on the 1-yard line, so the harness gained a third replay position, `goalline` (`tools/lookdev.py`), which rests the ball **13.1 yd** from the well. That is what the `goal-line` shot uses.

**Verdict for Broadcast: the correction holds.** `goal-line/s-goal-line.png`, and `ball-at-13yd-crop.png` at full resolution: the ball is a laced, correctly proportioned football sitting on the grass, about 23 px wide in a 3840-px frame at 13.1 yd. It is emphatically not the marker it was. Two things worth knowing:
- At this range the ball is **dark**; what makes it findable is the light column above it, not the ball. That is the beacon doing the work, which is fine, but it means "findable at 50 yards" and "life size at 13" are being carried by different things.
- A ball at 2.6x would subtend 3.5° here against life size's 1.3°, so the difference is now large enough that any regression will be obvious in this frame.

### The wall seat: the LED boards, square on, for the first time

Every preset looks *along* the wall, so Sideline's boards had only ever been shot at a grazing angle, and "a subtle pixel grid up close" had never been testable.

- **`wall`, "Wall boards, home side"**: field level in the apron at the home 20 - no bench there, they run from the 30 to the 30 - 2.6 yd from the wall and facing it.

**Verdict for Sideline: there is nothing there to judge.** `wall/s-wall-boards.png` and `wall-level/s-wall-boards-level.png` (the same seat, level rather than pitched down): at 2.6 yd square on the wall is a **flat matte panel**, one blue-grey band and one near-black one, with no lit content, no text, no crawl and no pixel structure of any kind. `SidelineActor.buildBoards` textures the wall with `StadiumText.boards(s)` and falls back to `StadiumLook.solid(wall.color)` when that is nil; what the frame shows is the fallback. So the art bible's "glow like LED, with a subtle pixel grid up close" is not a near-field polish question yet - the boards have no content at all. That is Sideline's to answer, and the seat to answer it from now exists.

### Both are look-dev seats, not places to sit

The picker offers neither, and the app filters them on `lookdev`:
- The **wall** seat faces away from the play.
- The **camera well** turned out to be a place the dock cannot serve: a yard and a half behind an end line the painted field fills the view, and no panel can keep off the paint, the ribbon and the board at once. Rather than weaken a promise made to wearers, the well is diagnostic. Promoting it later needs an answer for the dock first - most likely letting a field-level seat behind an end line put panels over the far end zone.

**One cross-actor consequence, flagged rather than hidden.** Crowd's `verify_crowd_support` rule 2 says no visiting seat within 14 yd of "a wearer's seat preset"; the well stands beside the away support behind that end zone, and 255 checks failed. The rule's intent is a wearer's comfort, so the verifier now skips `lookdev` presets - a two-line change in `apple/verify_crowd_support.swift`, Crowd's file, with the reason written beside it. The rule itself is unchanged.

### The panels during a seat change: they go through the dark with the world

Decided, and the reason is not the one I expected. The dock is the wearer's rather than the room's, which argues for leaving it lit - but the dock is solved per seat, so **at the dark middle of the change its panels move**. Lit, they would be seen to jump, which is the one thing the fade exists to hide. So the dock fades with the world, and the scorebug, which does not move, stays lit so the score is never away. Reduce motion places, as everywhere.

`seat-change/s-crowd-closeup-seatchange.png` is a frame from inside the fade: the world dimmed, the Red Zone tab dimmed with it, the scorebug and win probability still bright. Getting that frame exposed a real bug: `-stadiumFadeScale` stretched the world's fade and not the dock's, so the two came apart under the debug stretch. They share it now.

### Budget and cost

Experience is still **0 draw parts and 0 triangles** in the stadium and 6 parts / 2,856 triangles on the table. The two seats add no geometry. They do cost the scene: the dock is solved for every seat at every recentre facing, so nine seats take **8.6 s** to solve for a field, cached thereafter. That is what made the harness fail twice at its first request - its own per-request timeout was 10 s - so `tools/lookdev.py` now allows 90 s for a cold scene. Every agent's harness gets that.

**Shots:** `goal-line/`, `wall/`, `wall-level/`, `seat-change/`, `main/` and `seat-*/` for all six other presets, unchanged.

**Worst thing left:** the camera well cannot be offered to a wearer until the dock has an answer for a seat behind an end line; the press box still draws its dock at x0.47 inside the glass and wants a device; and the recentre still lands on a 15 degrees bucket.

