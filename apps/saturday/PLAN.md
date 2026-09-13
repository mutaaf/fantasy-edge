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
0. **Spike.**
   - Scaffold, port generator/theme/field/gamecast, record fixtures (done 2026-09-12).
   - *Exit:* a recorded CFB game plays in the simulator and `make test` passes.
1. **Live 2D.**
   - Saturday Wall, game detail, SSE, on-demand summaries, replay end-to-end tests including overtime.
   - *Exit:* the full recorded slate replays across every tile within the request budget.
2. **Real 3D.**
   - Game Volume, then Stadium, plus a 3D placement harness. Test on a device.
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
