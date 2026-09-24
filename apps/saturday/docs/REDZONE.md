# The red zone in the bowl, on a Saturday

The stadium can stand in one college game or follow the night. Following it
is `/api/redzone`: every game ranked for attention, and the one the bowl
should be standing in.

```bash
# a recorded Saturday, served at a moment
PYTHONPATH=packages:apps/saturday:. python3 -m api serve \
  --source "capture:$PWD/apps/saturday/data/capture/2026-09-19-merged@20260920T000000Z" --port 8780

# walk in and let it follow
apps/saturday/apple/sim.sh run -saturday.host 127.0.0.1:8780 \
  -openStadium 401856685 -replayAt 20260920T000000Z -followBall YES
```

## What is shared, and what is not

The channel client (`RedZoneChannel`) and the panel (`RedZonePanel`) live in
`StadiumKit`: both products poll one route, draw one panel and read one
payload shape. `tests/test_redzone_immersive.py` walks both apps' sources and
fails if either grows a copy.

The **staying** question is shared too. `fantasyedge.whip.choose` holds a
channel steady, and its `dwell`, `margin` and `quiet` are the caller's
because they belong to the surface and to the scale of the numbers.

The **urgency** number is not shared, and should not be. College leverage
weighs the AP poll, an upset in the making and an untimed overtime, none of
which a Sunday has; `whip.urgency` weighs yards to the end zone, which ESPN
never sends on a college situation (0 of 749 over a full Saturday).

## The numbers, and where they come from

Measured over the recorded 19 September slate: 74 games, up to 31 live at
once, 9 in the red zone together.

| dwell | margin | changes in 7½ h | median hold | visits of 1–2 min | leverage given up | red-zone minutes shown |
|---:|---:|---:|---:|---:|---:|---:|
| greedy | 0 | 94 | 2 min | 50 | 0.0 | 52 % |
| 2 min | 3 | 63 | 4 min | 18 | 0.3 | 52 % |
| **3 min** | **5** | **51** | **5 min** | **0** | **1.0** | **50 %** |
| 4 min | 8 | 39 | 7 min | 0 | 1.2 | 44 % |
| 4 min | 12 | 27 | 10 min | 1 | 1.3 | 38 % |

Three minutes and five points is the chosen pair: every sub-three-minute
visit is gone for one leverage point and two points of red-zone coverage.

An explicit red-zone pre-empt was tried and dropped. Allowing a game in the
red zone to cut the dwell short bought 5 points of coverage and put 12–16
short visits back. The ranking already weighs the red zone, so the dwell does
not need to.

A residual remains and is not a bug: when two games sit within five leverage
points and trade the lead — LSU–Ole Miss against Florida State–Alabama
between 00:42 and 00:56 — the bowl alternates every three or four minutes.
That is the dwell doing exactly what it was set to do.

## The focus is a function of the moment

Not of server memory. The walk starts cold at the oldest frame of a
half-hour window and arrives at the same answer for every caller asking about
the same moment, so two headsets that joined at different times are in the
same game and a replay reproduces exactly.

Held against a walk from the first frame of the night, a thirty-minute
look-back agrees at all 450 sampled minutes. Twenty minutes agrees at 449.

## A changeover is a repaint, measured

Eight changeovers between three college games (FSU–Alabama, LSU–Ole Miss,
SMU–Louisville) on `Stadium 26.5`, read out of the app's own timing lines:

    [stadium] changeover: dark at 0.36 s, swapping
    [stadium-timing] stadium relivery: 0.363 s     # clubs not seen before
    [stadium-timing] stadium relivery: 0.365 s
    [stadium-timing] stadium relivery: 0.197 s     # clubs seen before
    [stadium-timing] stadium relivery: 0.184 s
    [stadium-timing] stadium relivery: 0.195 s
    [stadium-timing] stadium relivery: 0.179 s

Every one a relivery; not one a rebuild. The building costs **3.58 s** to
raise, and a whip-around that rebuilt would pay that on every switch. The
same figures the NFL side reports — 0.36 s for new clubs, about 0.19 s for
clubs seen before — now measured for college rather than assumed from it.

Why it holds: `StadiumVenue` is the building and the livery is the paint, and
`league` is part of the building. Two college matchups share a venue and
differ in livery. `apple/verify_scene.swift` asserts this over every sampled
scene, grouped by league, with three college scenes in the set.

Reproduce:

```bash
apps/saturday/apple/sim.sh build
xcrun simctl launch <udid> com.mutaaf.saturday -saturday.host 127.0.0.1:8780 \
  -openStadium 401856685 -replayAt 20260920T000000Z -stadiumStats \
  -stadiumWhip 401856685,401856688,401858230 -stadiumWhipEvery 14
xcrun simctl spawn <udid> log show --last 3m --style compact \
  --predicate 'subsystem == "com.mutaaf.fantasyedge"' | grep -E "changeover|relivery"
```

## The frames

Shot at commit `ed001f8`, on the merged 19 September capture.

| Shot | What it shows |
|---|---|
| `screenshots/phase-2/visionpro-redzone-panel.png` | LSU at Ole Miss, the panel at the right hand: 31 live, 1 in the red zone, `Follow the ball` on, "Here because: ranked, upset alert", and the slate with its ranks — `#7 LSU @ #8 MISS`, `UTSA @ #1 TEX`, `MSU @ #3 ND` |
| `screenshots/phase-2/visionpro-redzone-changeover.png` | a changeover caught coming back up: the world still dim, the new livery already in place, REBELS at midfield and `#7 LSU 0 · #8 MISS 10 · 2:00 1ST` on the ribbon |
| `screenshots/phase-2/visionpro-redzone-fsu-alabama.png` | the same session, the other game: crimson crowd, CRIMSON TIDE at midfield, `FSU 28 · #10 ALA 40 · 12:50 4TH` |

The fade is stretched ×10 for the capture (`-stadiumFadeScale 10`), because
it is over in about a third of a second and a simulator screenshot costs
roughly one.

## The bowl is never sent where it cannot be drawn

19 September kept the live snapshots of six games by the sampling rule. ECU
at Old Dominion ranked first at half past midnight, and the stadium opened on
a black field: the ranking was asked which game deserved the bowl and never
asked whether it could be shown.

Every row now carries `detail`, the focus only considers what is drawable,
and the panel dims a row it cannot open rather than offering it. The wall's
tiles already kept that rule; the bowl does now too. On a live Saturday this
excludes nothing.

## Follow the ball is off by default

The same default as the NFL side, and for the same reason: a wearer who
walked in from one game's table came to watch that game, and moving them off
it unasked is a theft rather than a feature. A college Saturday does not
argue otherwise — it argues harder for it, because there are 74 games and the
one you chose is the one you chose.

The switch is in the panel. `-followBall YES` turns it on for a screenshot.
