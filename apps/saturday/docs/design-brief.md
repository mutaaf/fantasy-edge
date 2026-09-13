# Design brief: Saturday, initial views

Design three views for **Saturday**, a college football app for Apple Vision Pro (visionOS 26, SwiftUI + RealityKit). It follows every FBS game live, then goes deep on programs, rivalries and recruiting. It's a personal/TestFlight app, so ESPN team logos and colours are allowed.

## Direction
Pick a bold, specific look and commit to it. Our starting point is **stadium lights at night**: broadcast-chyron precision, the ink texture of a printed game-day program, and turf underneath everything. It should feel like college football (marching bands, school colours, rivalries), not a generic sports dashboard. Avoid purple gradients, default system-card layouts, and fonts like Inter or Space Grotesk.

## Views

**1. Saturday Wall** (window, 1680×940 pt)
- Every live game on one surface. A typical Saturday has 60–90 FBS games.
- The games that matter most right now are larger and further forward. Importance means: close score, 4th quarter, top-25, overtime.
- Design a **game tile** in these states: `pre` (kickoff time, TV network), `live`, `red zone`, `overtime`, `delayed`, `final`, and `upset` (unranked beats ranked).
- Each tile shows rank, abbreviation, score, possession, down & distance, and clock/period.
- Include the filter/ornament bar: Top 25, conference, close games, my teams.

**2. Game Volume** (volumetric window, about 0.9 × 0.4 × 0.6 m)
- A tabletop 3D field for one game: team-coloured end zones, the ball on its real yard line, and the current drive drawn as an arc of play segments (run/pass/penalty/turnover/score look distinct).
- A floating scorebug and win-probability ribbon, plus a drive scrubber (pinch to step through plays).
- Show it at kickoff, mid-drive in the red zone, and on a scoring play.

**3. Game Detail** (window, 1280×860 pt)
- The 2D companion to the volume: play-by-play grouped by drive, a box score, the win-probability chart, and a "watch in 3D" / "enter stadium" action.

## Hard constraints (learned on-device, not negotiable)
- **Legibility on glass:** text is system ink. Colour goes on an opaque chip *beside* text, never as the text colour.
  - Body contrast must be ≥4.5:1 and large text ≥3:1, against both a bright room (#d8dad4) and a dark one (#1a1c20). Gold measured 1.02:1 on glass.
  - Nothing below 12 pt.
- **Team colours are hostile.** With 130+ teams, many primaries fail on glass. Place every team colour on a chip normalised into one luminance band (about 0.135–0.18 relative luminance). Show how a clashing pair looks, e.g. Texas vs Tennessee.
- **Colour is never the only signal.** Every state carries a glyph as well: live, red zone, possession, upset, OT, injury.
- **Targets:** hit areas of 60 pt or more. Hover shape matches the visible shape.
- **Placement** (for later immersive versions):
  - Keep content within ±46° horizontally and no more than 33° below eye level.
  - Detail opens dead ahead.
  - In immersive space, size in points, not by scaling.
- **Motion:** use restraint in the tiles and spend it on scoring plays. Every animation needs a reduce-motion equivalent.

## Deliverables
- Frames for each view and every tile state, in light and dark rooms.
- Type scale and colour tokens (including the chip-normalisation rule).
- A glyph set.
- A short motion spec: score change, possession flip, upset reveal.
- For the volume: a side view with dimensions in metres and the drive-arc construction.

**Sample data:** a real slate recorded on 2026-09-12. It includes #1 Ohio State vs #4 Texas, Wake Forest 38–36 Purdue in double overtime, Oklahoma State over #6 Oregon, and a game in a weather delay.
