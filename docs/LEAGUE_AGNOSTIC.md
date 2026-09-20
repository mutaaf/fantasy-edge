# The two codes

The stadium was built against an NFL fixture and the Saturday app is college
only, so every league difference had exactly one side exercised. This page is
the audit of where the two codes differ, where that difference lives, and
what is still owed.

The rule it is held to: **a league's rules live in one place and are read, not
decided.** `scene.RULES` states them, the scene carries them, and a renderer
reads the answer. An actor that compares a league's name has to be taught
every league; an actor that reads `props.chains.groundMarkers` does not.

## What differs, and whether it was right

| Thing | Where it lives | Was it right? |
|---|---|---|
| Hash marks | `RULES[league].field.hashFromSideline` | Yes. 40 ft apart in college, 18 ft 6 in in the NFL, both in a 160 ft field. |
| Field size, end zones | `RULES[league].field` | Yes, and identical: 100 × 53⅓ yd with 10 yd end zones. |
| Goal-post width | `RULES[league].field.goalPostWidth` | Yes, and identical: 18 ft 6 in. |
| Upright height | `RULES[league].props.goalpost.uprightAbove` | Yes. 35 ft above the crossbar (NFL Rule 1 §3 Art.2), 30 ft in college (NCAA 1-2-5-a). |
| Team areas | `RULES[league].props.benches` | Yes. Between the 30s in the NFL, the 20s in college (NCAA 1-2-4-a). |
| Painted border | `scene.PAINTED_BORDER` | Yes. 6 ft NFL, 4 in college. |
| Baked markings | `field.markings` → `assets/actors/field/markings/<league>` | Yes, and both are baked. |
| The ball | `broadcast.footballNFL` / `footballCollege` | Yes, and both assets exist. |
| Goal posts, pylons (models) | `SidelineActor`, chosen by league name | **Deferred.** See below. |
| **Pylon placement** | `scene.pylon_spots` | **No. Fixed.** |
| **Ground markers at the line to gain** | was `SidelineActor`, now `props.chains.groundMarkers` | **No. Fixed.** |
| **Which league a game is** | was the caller's argument, now `scene.league_of` | **No. Fixed.** |
| **Untimed overtime** | `replay.untimed_overtimes` | **No. Fixed.** |
| **Goal to go** | `scene.build`'s situation | **No. Fixed.** |
| Overtime length | `RULES[league].overtimeSeconds` | Declared and never read. Now used by the untimed-overtime rule's sibling in `replay`. |
| Ranks, conferences | ESPN's payload, carried through | Not a geometry difference; college teams carry a rank and NFL teams do not, and nothing assumes either. |

## The five that were wrong

### The league was the caller's opinion, not the game's

`api.scene` and `api.replay_scene` both passed `league="nfl"`, so **every
college game was drawn on an NFL field** — hash marks 3.58 yards off on each
side, NFL uprights, NFL pylons, NFL border paint and an NFL ball. Nothing
said so.

`scene.league_of` reads it from the payload instead: ESPN states it in
`header.league.abbreviation` and again in every `uid` (`s:20~l:23~…` is
college, `l:28` the NFL). `scene.build` uses it when the caller does not
insist, and the two call sites no longer insist.

### The pylons were wrong in both codes, and the count hid it

Both codes stand eight pylons at the sidelines: the four front corners of the
end zones where the goal lines meet them, and the four back corners where the
end lines do. College adds four more where the inbounds lines extended meet
the end lines, three feet beyond (NCAA 1-2-6); the NFL has none there (Rule 1
§2 Art.3).

What was drawn: the NFL had **no back corners at all** and four college hash
pylons standing in its end zones instead. That is eight either way, and the
only test was a count, so it passed. `tests/test_league.py` checks where each
pylon stands.

### A college overtime collapsed onto one instant

College overtime is alternating possessions with no clock (NCAA 3-1-3), so
ESPN reports the same clock on every play of it. Read literally, every play
of the period landed on the same absolute second: a replay could not scrub
through it, and "skip to the next score" landed back in the fourth quarter.

`replay.untimed_overtimes` recognises a period whose football plays show one
clock, and `replay.play_offsets` spaces them by `UNTIMED_SNAP_SECONDS`.
Timeouts are excluded before the clocks are compared, because they carry
their own: Toledo at Temple (401862774), a real overtime and now a committed
fixture, shows 0:14 on a Temple timeout and 0:00 on all six football plays
around it. Counting that timeout made the period look timed and left five
plays on one instant.

### A line to gain was painted inside the end zone

Goal-to-go was decided by comparing the distance with `yardsToEndzone`.
**ESPN sends that field for the NFL and never for college**: 0 of 749 live
college situations in a Saturday's boards carried one, while `yardLine`,
`down`, `distance` and `isRedZone` were in all 749. So on college it was
always absent, always read as "not goal to go", and a line to gain was drawn
on every goal-to-go snap — on the goal line itself for 1st and goal from the
5, and **five yards inside the end zone** for 2nd and 8 from the 3.

It is now decided by where the line would fall, which both codes state.
ESPN's own answer is still honoured where it exists.

### The renderer decided a rule of the game

`SidelineActor` compared `s.league == "college-football"` to decide whether to
lay markers on the line to gain. Which props a code puts on the field is a
rule of that code, so the scene says it (`props.chains.groundMarkers`) and the
actor reads it. The web and Android ports get the same answer for free.

## Checked, and not a defect

- **College play records do carry `yardsToEndzone`** — 191 of 191 in the
  fixture — so the replay's red-zone derivation (`replay._situation`) is
  sound. The omission is specific to the live scoreboard's `situation` block.
  Do not "fix" the replay path.
- **`possession` is absent from 47% of live college situations**, and that is
  ESPN being right rather than wrong: 94% of them are moments with no offence
  set — a timeout (29%), the end of a period (27%), an extra point (21%), a
  made field goal (8%) or a kickoff (4%). The scene draws no line to gain at
  those moments, which is correct. The remaining ~6% are ESPN briefly stale
  after a reception.

## Still owed

- **`live.BASE` hardcodes `/football/nfl`**, so the live tier can only ever
  fetch NFL games however well everything above it reads the league. The fix
  is a league in the base URL and a caller that states which — the red-zone
  agent found this independently, and it is sequenced behind that work.
- **`Gridiron.place` (`apple/.../Gridiron.swift`) guards on `toEndzone`** and
  returns no position along the field when it is nil, so a live **college**
  game cannot place its ball on the 2D field strip. `yardLine` is present in
  100% of live college situations and is the field to use.
- **The red-zone list sorts by `toEndzone`** (`mosaic.html`), which is
  undefined for every college game, so the ordering is meaningless there —
  every college game ties at the fallback. Same fix: `yardLine`.
- **Goal-post and pylon models are chosen by league name in `SidelineActor`**
  (`college ? "goalpost_college" : "goalpost_nfl"`). It is the same class of
  problem as the ground markers, but the model ids belong to
  `visual.sideline.models` and carry an LOD naming convention, so moving them
  into the scene is a bigger change than it looks. Left as it is, deliberately.
- **Clock rules are not modelled at all**: college stops the clock on a first
  down, and neither code's timing rules are anywhere in this repository. The
  replay reads the clock ESPN reports rather than running one, so nothing is
  wrong today; it would matter the day anything simulates a clock.

## The fixture

`tests/fixtures/replay_game_401862774.json` is Toledo at Temple, 19 September
2026, a real college game with a real overtime — 191 plays, 25 drives, 144 KB.
It is the first college fixture in this repository, and it exists because a
test that only ever loads an NFL game is how all of the above survived.

Regenerate it the way everything else is regenerated, never by hand:

```bash
python3 tools/make_replay_fixture.py --game --event 401862774 \
    --from-capture ~/Desktop/projects/saturday/data/capture/2026-09-19
```
