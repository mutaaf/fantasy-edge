# Where the ball actually was

The scene draws a play from what the feed says about it. ESPN's public feed
says where a play started and where it ended, and not one word about where the
ball was **caught**. So the catch point was guessed - a share of the gain,
bounded by the depth word - and the guess is wrong by exactly the yards after
the catch.

Measured over three real games, it was wrong on 94% of throws, by 4.4 yards on
average and 31 yards at worst.

nflverse republishes the NFL's own play-by-play, and it states the number. So
a finished game is now drawn from what happened, and a live one says it is an
estimate.

## The two sources

| | ESPN | nflverse |
|---|---|---|
| When | during the game | after it |
| Says where a play started and ended | yes | yes |
| Says where the ball was caught | **no** | yes (`air_yards`) |
| Says the gap a run went through | in prose, sometimes | yes (`run_gap`) |
| Says how far a kick travelled | in prose, usually | yes (`kick_distance`) |
| Says where across the field anything went | no | no |

Neither tracks players. Nothing here says where across the field a ball went,
and every play carries `lane` in its `estimated` list so no client can present
that as measured.

## The rule

```
live       ESPN's text and spots; the catch point and the rest estimated
corrected  every field nflverse states, replaced in place
```

A live game has no published rows, so it is an estimate and says so. A
finished game is corrected in `api.gamecast`, in one pass over the whole game.
Turn it off with `FANTASYEDGE_CORRECT_PLAYS=0`; the test suite does, because
correcting reads a release over HTTPS and the suite promises no network.

Each play carries its provenance, and so does each arc in the scene:

```json
{"source": "corrected",
 "corrected": ["airYards", "yacYards", "passLength", "passLocation", "yards"]}
```

In Swift, read `arc.provenance` and `arc.isCorrected`. Both fields are
optional on the wire: a synthesized `Decodable` ignores a default value and
throws on a missing key, so a scene built before this existed still decodes.

## The identity rule

The two sources share no play id, so a play is matched on what it says about
itself.

**The game** is exact. nflverse's schedules release carries an `espn` column
holding ESPN's event id, so the bridge is published, not inferred.

**The play** is matched on `(quarter, down, distance, yards to the defending
end zone)`, and among rows agreeing on all four, the one whose game clock is
nearest. Matching runs in passes, strongest evidence first, and each pass
assigns its candidates closest-clock-first rather than in play order. A single
greedy sweep let a penalty four seconds away take the row belonging to a
touchdown three seconds away, and the touchdown went uncorrected.

A match needing more than `TOLERANCE_SECONDS` (8) of clock drift is refused
rather than forced: a wrong correction draws one play's ball along another
play's path, which is worse than an honest estimate.

**Penalties** are matched separately. ESPN keeps a nullified play; nflverse
files it as `no_play`. They match each other and never compete for a real row.

### Two spot conventions that are not bugs

On a change of possession the two sources mean different things by a spot, so
special-teams plays are matched on kind and clock, never on their spot:

- **Kickoff.** Chicago kicks from its own 35. ESPN says `65` yards to the end
  zone, which is the distance. nflverse says `35`, which is the marker.
- **Punt.** Chicago punts from its own 16 on 4th & 19. nflverse says `84`, the
  distance; ESPN says `16`, having not flipped for the home side.

Neither reaches the field. The scene draws from ESPN's `yardLine`, which is
fixed to the ground and independently right in both cases, and a correction
only ever supplies a **relative** yardage - how far the ball was thrown, how
far it was kicked - which carries no convention at all.

## Measured

`python3 tools/measure_play_accuracy.py`, over the three captured games and
their published rows. "Air yards" is the error in where the ball came down.

| Game | Matched | Start spot | Air yards, live | Air yards, corrected |
|---|---|---|---|---|
| 2025_01_DAL_PHI | 141/142 (99.3%) | 0.00 yd | mean 3.42, worst 15.0 | 0.00, all 57 exact |
| 2025_01_MIN_CHI | 154/156 (98.7%) | 0.02 yd | mean 4.45, worst 14.0 | 0.00, all 53 exact |
| 2025_16_LA_SEA | 185/188 (98.4%) | 0.00 yd | mean 5.22, worst 31.3 | 0.00, all 82 exact |

Read that as three separate findings:

1. **The spots were already right.** On scrimmage plays the two sources agree
   to within a hundredth of a yard, so correcting buys nothing there and
   nothing is claimed for it.
2. **The catch point was wrong nearly every time.** 4 of 57, 3 of 53 and 8 of
   82 throws landed within half a yard of where the ball actually came down.
3. **Play types agree**, on 480 of 481 matched plays.

One play, to show the shape of it - Stafford to Nacua, 54 yards, in
2025_16_LA_SEA:

| | thrown | after the catch | ball lands at | arc height |
|---|---|---|---|---|
| estimated | 45.9 yd | 8 yd | x = 42.1 | 10.3 yd |
| what happened | 19.0 yd | 35.0 yd | x = 69.0 | 3.1 yd |

The ball came down 27 yards from where it was drawn, on an arc three times too
high.

## What is published, and when

`fantasyedge.nflverse.coverage(season)` answers this from nflverse's own
statement rather than an assumed cadence. Measured on 2026-09-17:

- Every one of the 16 finished 2026 games is in the play-by-play release.
- The release was rebuilt at `2026-09-17 10:17:33 EDT`, its own
  `timestamp.json`, three days after the last game it covers (Monday
  2026-09-14). The file is rewritten on a schedule, so that is an upper bound
  on staleness, not the publication lag of any one game.

**What this does not establish:** how soon after a Sunday game its rows first
appear. That needs watching a game land, which no single run can measure. Until
then, a game corrects when `coverage()` reports it, and does not before.

## Layout

```
fantasyedge/nflverse.py   the single owner of talking to nflverse: releases,
                          the disk cache, the published game bridge
fantasyedge/truth.py      the identity rule, the correction, the measurement
tools/measure_play_accuracy.py   the table above
tests/test_truth.py       17 tests, fixture-driven, no network
tests/fixtures/nflverse_pbp_*.json
                          cut by tools/make_replay_fixture.py --nflverse
```

The cache lives in `~/.fantasy-edge/nflverse/`: the release as published, a
per-game shard beside it, and a `meta.json` recording each release's URL,
`Last-Modified` and nflverse's own rebuild time. A download lands in a `.part`
file and is renamed only on completion, so an interrupted fetch never leaves a
truncated file that a later read would trust.
