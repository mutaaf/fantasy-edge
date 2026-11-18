# App Store readiness: Fantasy Edge (visionOS)

Checked 2026-11-18 against App Store Connect (app "Fantasy Edge: Game Day", id 6833213130, bundle
com.mutaaf.fantasyedge) and this repo. **Not submittable yet.** Nothing has been sent to App Review.

## What exists
- App record, visionOS version 1.0 (PREPARE_FOR_SUBMISSION).
- Two VALID builds of 1.0 on internal TestFlight: 202611110254 and 202611102316 (uploaded 2026-11-10).
- Privacy policy URL set: https://mutaaf.github.io/fantasy-edge/privacy.html (loads).

## Blockers in the app (owner decisions; no metadata fixes these)
1. **A reviewer can't use it.** The app reads its board from a Mac on the same network running
   `python3 -m fantasyedge api` (default host 127.0.0.1:8770, set under "Where is the board?"). On Apple's
   Vision Pro there is no such Mac, so every screen is empty: a 2.1 rejection. It needs either a hosted
   board API the app reaches over the internet, or a built-in demo league (recorded fixtures) a reviewer
   can open without a server.
2. **Third-party marks and images.** `CommandPanels.swift` loads player headshots from a.espncdn.com, and
   logos come from the feed. Public distribution needs those replaced or licensed (5.2.1, 5.2.2), the same
   reason Saturday is TestFlight-only.
3. **League accounts.** Real use needs an ESPN or Yahoo league connected on the Mac. The review notes must
   explain how to see it without one (see 1).

## Missing in App Store Connect (doable once the blockers are settled)
- Description, keywords, promotional text, support URL, marketing URL, subtitle (all empty).
- Primary category (draft: Sports; secondary Entertainment).
- Age rating questionnaire (every answer null).
- Content rights declaration (null; the honest answer is "uses third-party content").
- Price schedule and availability (none; a free app still needs one).
- App Review contact and notes (none).
- Screenshots: no visionOS set (Apple Vision Pro takes 3840x2160). Lobby has no visionOS spec yet
  (`lobby/specs/stores.json`), so this needs a Lobby target or hand captures from `apple/sim.sh`.
- App Privacy label (no API; set in App Store Connect).

## Draft listing (only once a reviewer can see real content)
- Subtitle: Every league on one board
- Promotional text: Every fantasy league you play, on one board around you, sized by what can still change your week.
- Keywords: fantasy football,fantasy,league,lineup,matchup,scores,live,sunday,vision pro,spatial,board,leverage
- Description, first paragraph: Fantasy Edge puts every fantasy football league you play on one board and sizes
  each player by how much they can still change your week. A running back in a close game with a half to play
  fills the view; a player in a blowout shrinks away. In the immersive view, what still matters stands forward
  and what's decided falls back.
- Review notes must disclose AI-assisted development the same way the other apps' notes do (written largely with
  Claude Code under the owner's direction), and must not overlap 17-0, which is a football history puzzle.
