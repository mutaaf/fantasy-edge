# Replaying a day

`replay.py` replays one game. `dayreplay.py` replays a *slate*: every game of
a Sunday at once, so the red-zone channel whips around it the way it did while
the games were on.

```bash
# pull it once - one request for the board, one per finished game
python3 -m fantasyedge redzone-replay --date 2026-09-20 --pull

# serve, then open http://127.0.0.1:8790/redzone
python3 -m fantasyedge api --port 8790
curl -s localhost:8790/api/day -d '{"action":"load","date":"2026-09-20"}'
curl -s localhost:8790/api/day -d '{"action":"speed","speed":60}'
curl -s localhost:8790/api/day -d '{"action":"play"}'
```

Re-running `--pull` is free and offline: a day whose summaries are on disk is
skipped. 2026-09-20 cost **14 requests and 6.2 seconds** for 14 games and
2,546 plays.

## How it works

ESPN stamps every play with the instant it happened (`wallclock`), so a
finished game's summary is a timeline rather than only a final score. Given
the day's board and every summary, `board_at(when)` rebuilds the slate as it
stood at any moment.

That rebuild is an **ESPN-shaped scoreboard**, and `DayDirector.fetch` stands
in for `EspnLiveSource._fetch` on a source instance of its own - the
arrangement `ReplayDirector` already uses for a single game. So
`live.games()`, `whip.slate()`, `whip.rank()`, `whip.choose()`, `/api/redzone`
and the headset's Red Zone panel are untouched. **A replayed day and a live
Sunday are the same code path**, which is the property `tests/
test_dayreplay.py::TheChannelCannotTellItIsARebuild` exists to keep.

A rebuilt day is in some ways *richer* than the live feed: a play record
carries `downDistanceText` and `yardsToEndzone` on every play, where the live
`situation` block omits the first between plays and the second entirely
outside the NFL.

## Controls

`POST /api/day` (loopback only, like `/api/replay`):

| action | body | |
|---|---|---|
| `load` | `{date, from?, to?, slot?, at?}` | open a pulled day |
| `play` / `pause` | | |
| `seek` | `{at}` seconds, or `{time: "15:30"}` | |
| `speed` | `{speed}` | 0.25–3600× |
| `next` / `previous` | | the next scoring play *on the whole slate* |

`GET /api/day` is the state; `GET /api/day/markers` is every score as an
offset, for a scrub bar.

**Windows.** `--from`/`--to` take `13:00`, `1:00pm` or a full instant; a bare
time is Eastern, because that is the clock a football day is scheduled on.
`slot` takes a kickoff wave read off the day's own board rather than an hour
written into the source: `4pm` means both the 4:05 and 4:25 waves, `4:25pm`
means only its own.

## Verifying a rebuild

```bash
python3 tools/verify_day.py --date 2026-09-20
```

It rebuilds the board at the instant of every scoring play and compares it
against `scoringPlays` - a different block of the summary from the one the
rebuild walks - and each game's final against the header. **2026-09-20: 121 of
121 states identical**, and a sweep of the whole day every two minutes found
**no score going backwards**.

Differences are classified, not counted, and an unexplained one exits 1.

## What a rebuild cannot know

Carried in `dayProvenance.caveats` on every board, repeated in the payload,
shown on the page as a **REBUILT** chip that opens the list, and marked in the
headset panel. The claim travels with the data rather than being remembered by
whoever started the server.

- A score ESPN corrected and then corrected back reads as one clean change.
- A delay that started and ended is invisible; it shows only as a gap.
- Halftime is inferred from the gap between periods, not read from a board.
- Down and distance between plays come from the next play's start, so after
  the last play of a period no ball is drawn.
- ESPN's play feed leads its own scoreboard: a touchdown's play already
  carries the score after the extra point, so a rebuild never passes through
  the six-point moment.
- A game begins at its first play and ends at its last.

## Two faults in ESPN's own data, handled here

Both were on the 2026-09-20 slate, and both would make a tile flicker.

**A blank administrative row.** Cincinnati at Houston's "Two-Minute Warning"
play carries 0-0 while the game stood at 20-6. `running_scores` treats a 0-0
on a game that has already scored as unstated and carries the running score
through it.

**A touchdown counted before its try.** New Orleans at Baltimore's touchdown
carries 17 - the score it would have been had the two-point attempt worked -
and the failed attempt then restates 15. That is a real correction of a real
over-count and is **left alone**: it is what ESPN's feed published and what a
viewer saw.

The distinction: the first states a score nobody was ever on; the second
states one everybody saw.

## Another league

The league is read from the board (`leagues[0].slug`), never assumed, and
`live.scoreboard_url`/`summary_url` take a `league_path`. A college Saturday:

```bash
python3 -m fantasyedge redzone-replay --date 2026-09-19 --pull \
    --league-path football/college-football
```

Unproven: no college day has been pulled through this path yet. The rebuild
itself is league-agnostic - it reads plays, not rules - and
`_to_endzone_from_text` exists because ESPN omits `yardsToEndzone` from every
live college situation, but the end-to-end college pull has not been run.
