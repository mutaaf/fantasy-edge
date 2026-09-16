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

## Afterwards: comparing the recording to ESPN

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
