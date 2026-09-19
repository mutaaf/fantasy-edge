# The live test: Friday 18 and Saturday 19 September 2026

Everything so far has been proved against a recording. This is the first run
against a Saturday as it happens: ESPN live, the API in live mode, the app on
a phone and a headset on the LAN, and a recording of the whole weekend kept
for the next replay.

The slate (from `make record-plan`, ESPN's own week-3 board):

| | |
|---|---|
| Games | 74 FBS: 3 on Friday, 71 on Saturday |
| First kickoff | Fri 18 Sep, 7:30 PM ET |
| Last kickoff | Sat 19 Sep, 11:00 PM ET |
| Recording starts | Fri 18 Sep, 7:00 PM ET (30 min before the first kickoff) |
| Recording ends | when every slate game is final, or Sun 20 Sep 06:00 ET |
| Board | `scoreboard?groups=80&limit=300&week=3&seasontype=2` — one board, whole slate |

## Before Friday evening

1. `python3 -m unittest discover -s tests` — everything green.
2. `PYTHONPATH=packages:apps/saturday python3 -m api doctor --json` — exit 0.
   A missing `CFBD_API_KEY` is a warning, not a failure.
3. `make record-plan` — the window above. If the games or kickoff times have
   moved, the plan moves with them; it is read from ESPN each time.
4. Start the recorder (see **Recording** below) and check `heartbeat.json`
   says `waiting` with the right `startsAt`.
5. Start the API on the LAN: `make live` (or
   `PYTHONPATH=packages:apps/saturday python3 -m api serve --source espn --host 0.0.0.0`).
   Find the Mac's address with `ipconfig getifaddr en0`, then open
   `http://<address>:8780/api/health` from the phone's browser to prove the
   LAN reaches it. Set the same `<address>:8780` in the app's Settings.

## What to watch, and what right looks like

### The board
- **Scores** change within a minute of ESPN, and the tile flourishes once:
  a badge ("Touchdown · OSU"), the light bank, the number rolling.
- **Corrections.** A touchdown called back or overturned takes points off the
  board; the tile says "Off the board", never silently drops them. Six of
  these happened on 12 September, so expect one or two.
- **Lead changes** say "Takes lead" on the side that went ahead.
- **Finals** move the tile to "Tonight so far", upsets first, gold border.
- **Overtime** shows OT or 2OT and stays in the finals section afterwards.
- **Halftime and delays** show no ball on the field and no down-and-distance,
  even though ESPN leaves the last one on the board.
- **Kickoffs** move a game out of "Coming up" in kickoff order.
- **Around the country** fills with the last twenty minutes, newest first,
  each line keeping the score as it stood, all times in ET.

### The numbers behind it
- **Request budget**: `curl -s http://<address>:8780/api/health | python3 -m json.tool`.
  `budget.within` must stay `true` all night. It allows one scoreboard per
  20 s and one summary per open game per 15 s, however many people are
  watching. Check it at kickoff, mid-afternoon and late.
- **Stream**: with a game open, the app should show its detail updating
  without a visible reload. `curl -N "http://<address>:8780/api/stream?games=<id>"`
  prints `slate`, `game` and `budget` events; pull the Wi-Fi for ten seconds
  and watch the app fall back to polling and then reconnect (the header
  subtitle drops "live" while it is polling).
- **Recorder**: `cat data/capture/2026-09-19/heartbeat.json` — `phase` is
  `recording` (or `idle` overnight), `errors` is not climbing, `finalsSaved`
  rises through the evening. `tail -f data/capture/2026-09-19/record.log`.

### On the devices (LAN)

**iPhone**
- [ ] The wall fills, and "Coming up" is in kickoff order with ET labels.
- [ ] A score you can see on TV or espn.com appears within a minute, with one
      flourish, not a re-run of every earlier change.
- [ ] Open a game: drives, scoring, win probability and box score fill in, and
      keep updating while it is open.
- [ ] Leave the game and come back; no duplicate flourishes.
- [ ] Lock the phone for five minutes, unlock: the wall catches up.
- [ ] Reduce Motion on (Settings → Accessibility → Motion): flourishes become
      fades, nothing slides or strobes.

**Vision Pro**
- [ ] The wall reads at a comfortable distance; the ornament is reachable.
- [ ] A ranked game's tile, the spotlight and the whip-around all update.
- [ ] Open a detail, then the wall again: the poll keeps running (this was a
      bug in fantasy-edge; the store is reference-counted).
- [ ] "View in 3D" and "Enter stadium" still open the placeholder — the
      renderer is phase 2 and lands with fantasy-edge's scene branch.

### Known limits on the night
- No 3D: the volume and stadium are placeholders until the scene branch lands.
- Pre-game detail shows season averages, not a box score, and says so.
- The app polls when the stream cannot connect; that is the fallback working.

## Recording

Start it any time on Friday; it waits for the window by itself and keeps the
Mac awake while it runs:

```bash
tools/record_weekend.sh 2026-09-19            # or: make record-weekend
```

It ends by itself after the last final, or at 06:00 ET Sunday. To stop early,
`pkill -f record_slate.py` — the snapshots already written stay usable, and
starting it again resumes from what is on disk.

What lands in `data/capture/2026-09-19/`:

```
scoreboard/<stamp>.json.gz     one file per changed board
live/<event>/<stamp>.json.gz   the six highest-leverage live games, as they change
final/<event>.json.gz          one per game, a few minutes after it goes final
record.log, heartbeat.json     what it did, and that it is alive
```

## If the recorder starts late: backfill

It did, on 19 September: it began at 16:49 ET, after Friday's three games and
the whole early afternoon. A summary carries every play and every play carries
its own `wallclock`, so the missing hours can be rebuilt after the fact.

```bash
python3 tools/backfill_slate.py both --slate 2026-09-19     # summaries, then frames
python3 tools/verify_reconstruction.py --slate 2026-09-19   # against what was recorded
```

The backfill writes to `data/capture/<slate>-backfill` and never touches the
folder the running recorder owns. It is idempotent: run `fetch` again as more
games finish (`--refresh` re-fetches the ones that were still live), then
`frames` again.

**What a reconstruction cannot know** - in `manifest.json` and in every board
it writes, never papered over:

- a score corrected and then corrected back: only the surviving version is in
  the summary, so a tile that flickered reads as one clean change;
- a delay that started and ended: nothing in a summary records it, and it is
  not drawn as a delay. The two games sitting in a delay at 16:49 on
  19 September (UNC at Clemson, Mississippi State at South Carolina) have no
  delay in their rebuilt hours;
- the status ESPN published minute by minute. Halftime is inferred from the
  gap between the last play of one period and the first of the next;
- down, distance and possession where there is no next play yet;
- anything about a game that never kicked off: that tile stays the schedule.

### What a rebuilt day looks like in the app

- The wall carries a **REBUILT** chip beside the replay clock (its own line on
  a phone). Pressing it opens "Rebuilt from timestamps" with the API's own
  caveats, so the limits travel with the data rather than living in a doc.
- A rebuilt live tile loses the green live dot and takes the rebuilt glyph:
  nobody watched that minute, it was worked out afterwards.
- A recorded board shows none of this. `docs/screenshots/rebuilt` has both,
  side by side, on all three devices.

## Merging the backfill with the recording

Run it once the recorder has finished; it refuses while the recorder is still
alive. Re-fetch the games that were still live when they were first backfilled,
rebuild the frames, then merge:

```bash
python3 tools/backfill_slate.py fetch --slate 2026-09-19 --refresh
python3 tools/backfill_slate.py frames --slate 2026-09-19
python3 tools/merge_capture.py --slate 2026-09-19
```

The recording owns every moment it covers; the backfill only fills the hours
before it started, and each frame says which it is. The merged night lands in
`data/capture/2026-09-19-merged` with a `MERGE.json`, and replays as one:

```bash
PYTHONPATH=packages:apps/saturday python3 -m api serve \
  --source capture:data/capture/2026-09-19-merged --host 0.0.0.0
```

## Afterwards: comparing the recording to ESPN

0. **Finish the night in one go.** After the recorder exits:
   ```bash
   python3 tools/backfill_slate.py fetch --slate 2026-09-19 --refresh
   python3 tools/backfill_slate.py frames --slate 2026-09-19
   python3 tools/verify_reconstruction.py --slate 2026-09-19 --boards 40
   python3 tools/merge_capture.py --slate 2026-09-19
   ```
   The verify step compares the rebuilt hours against the recorded boards where
   they overlap and exits 1 if any game disagrees; it was 35 of 35 identical
   when the backfill was first built.

1. **Does the recording cover the night?**
   ```bash
   ls data/capture/2026-09-19/scoreboard | wc -l     # boards kept
   ls data/capture/2026-09-19/final | wc -l          # finals, should equal the slate
   python3 - <<'PY'
   import gzip, json, pathlib
   root = pathlib.Path("data/capture/2026-09-19")
   frames = sorted(p.name[:16] for p in (root/"scoreboard").glob("2026*.json.gz"))
   print(frames[0], "->", frames[-1], len(frames), "frames")
   PY
   ```
2. **Replay it and look**:
   ```bash
   PYTHONPATH=packages:apps/saturday python3 -m api serve \
     --source capture:data/capture/2026-09-19 --host 0.0.0.0
   ```
   The app, pointed at it, scrubs the whole night. `/api/replay` lists the
   frames, their marks and the gaps where the recorder lost the network.
3. **Check the story against ESPN.** Take three or four games — an upset, an
   overtime, a game with a score taken off the board — and compare the
   recorded finals and the change list with the box score on espn.com. Every
   score change should be in the feed, and every correction should be one.
4. **Make fixtures** from anything worth keeping:
   `python3 tools/make_fixtures.py` (never edit `tests/fixtures` by hand), then
   add the case to the tests.
5. **Write up** what broke, in the shape of the 12 September notes: what the
   real data did that the recording had not shown.
