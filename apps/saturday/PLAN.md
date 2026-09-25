# Saturday: plan

A college football app for Apple Vision Pro. It ports the proven pieces of `~/projects/fantasy-edge` and leaves the NFL-fantasy parts behind.

**Decisions:**
- **v1 scope:** live companion, analytics & history, recruiting & portal. College fantasy is out.
- **Audience:** personal use and TestFlight for friends, so unofficial ESPN data and team logos are acceptable.
- **Backend:** Python, stdlib only, SQLite. The headset talks only to our API.

## Data
| Lane | Source | Use |
|---|---|---|
| Live | ESPN `site.web.api.espn.com/.../football/college-football/{scoreboard?groups=80, summary?event=}`. Free and unofficial; cache and back off. | Scores, situation, drives, plays, win probability |
| History | CollegeFootballData REST. Free tier is 1,000 calls/month; Tier 3 is $10 for 75k. | Games, lines, SP+/EPA, recruiting, portal, venues, coaches |

Pull CFBD data by season and store it forever. Only play-by-play backfill might justify a paid tier.

**College differences:**
- About 60–90 FBS games a Saturday. Poll the scoreboard for all of them; fetch summaries only for games someone has open.
- 130+ teams: read ids, colours and logos from the payload.
- Overtime alternates possessions from the 25, with two-point shootouts from the third overtime on.
- Hash marks are wider than the NFL's.
- Check the current clock rules before simulating the clock.

## Porting from fantasy-edge
- **Backend:** `api.py` (server, cache tiers, ETag, SSE), the `LiveSource` fetch/backoff logic, the gamecast shaping, `replay.py` (frames and reconciliation), `doctor`, the Dockerfile.
- **visionOS app:**
  - `generate_project.py`, `contrast_check.py`, and `Theme` chips/`Mark`.
  - `Gridiron`, `Field`, `Gamecast`, `GameFieldView`, `Watch`, `Imagery`, `Spotlight`, `AppleIntelligence`.
  - The `ImmersiveBoard` placement math.
- **Rules:**
  - Every number carries a caveat.
  - Keys are `(source, id)`.
  - Regenerate fixtures by script, never by hand.
  - Don't rebuild RealityView attachments on update.
  - Size in points, never with scaleEffect.

## Scenes
| Scene | Type |
|---|---|
| Saturday Wall: every live game, ordered by leverage | Window, then an immersive arc |
| Game Volume: tabletop RealityKit field with drive arcs | Volumetric window |
| Stadium: sit at the 50, drawn in code | Progressive immersive space |
| Program Dossier: history, eras, analyses | Window |
| Rivalry Timeline | Volume |
| Recruiting & Portal Map: 3D US map with flows | Volume |

## Phases
0. **Spike.** *Done 2026-09-12.*
   - Scaffold, port generator/theme/field/gamecast, record fixtures.
   - *Exit:* a recorded CFB game plays in the simulator and `make test` passes.
1. **Live 2D.** *Done 2026-09-15.*
   - Saturday Wall, game detail, SSE, on-demand summaries, replay end-to-end tests including overtime.
   - Also shipped: frame-to-frame changes (score, correction, lead, possession, kickoff, final, upset, delay) with a flourish per change and a reduce-motion equivalent; the "Around the country" whip-around feed; a replay bar that scrubs the recorded night.
   - *Exit:* the full recorded slate replays across every tile within the request budget. Held by `tests/test_replay.py`: 60 frames, 86 tiles, three clients, one scoreboard per 20 s and one summary per open game per 15 s.
   - *Proven on 18-19 September 2026:* the API against live ESPN for a whole slate, the budget under three clients, and an unattended recording of 1,129 frames from Friday 19:36 to Sunday 02:46 ET. Write-up: `docs/LIVE_TEST_2026-09-19.md`.
   - *Still not proven, deferred to the next slate:* the LAN device passes - the iPhone and Vision Pro checklist in `docs/LIVE_TEST.md` - which need a live Saturday and cannot be run against a replay. Also unexercised: a delay that begins while the recorder is running.
2. **Real 3D.** *Blocked on fantasy-edge's scene branch landing* (`immersive/quality`; its `college-football` rules entry is still a stub).
   - Game Volume, then Stadium, plus a 3D placement harness. Test on a device.
   - Starts with integration steps 1-7 in `docs/ARCHITECTURE.md`, not with a renderer here: the scene spec and both renderers are built once, there.
   - *Exit:* on a device, drives render correctly for a whole replayed game.
3. **History.**
   - CFBD ingestion, `doctor` budget checks, Dossier and Rivalry, about six analyses with caveats.
   - *Exit:* 12 seasons offline.
4. **Recruiting and portal:** the Map volume.
5. **Social:** SharePlay, a widget target, narration, hosted API.

## Risks
- **ESPN blocks or changes endpoints.** Caching, the replay harness, and CFBD Tier 2 live data as a fallback.
- **3D cost with many games.** Tiles stay 2D; only the focused game renders in 3D.
- **OS version.** visionOS 27 is imminent: target 26 and adopt new APIs behind `#available`.
- **Hosting.** TestFlight friends need a hosted API.
