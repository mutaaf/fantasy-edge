# Fantasy Edge for visionOS

A native SwiftUI app. Not a web wrapper: the leverage model is ported to Swift
and runs on the device, which is the whole reason it was kept to arithmetic
over plain numbers in the first place.

```bash
python3 apple/generate_project.py          # emits FantasyEdge.xcodeproj
open apple/FantasyEdge.xcodeproj           # then Run
```

## Running it on a real Vision Pro

The app reads a board; it never holds a credential. That lives on the Mac.

1. On the Mac with the database:
   ```bash
   python3 -m fantasyedge api --host 0.0.0.0
   ```
2. Find that Mac's address on your network (`ipconfig getifaddr en0`).
3. In the app: **gear → Where is the board?** → `192.168.x.x:8770`.
4. Headset and Mac must be on the same network. Signing needs your own Apple
   ID in Xcode's Signing & Capabilities - a free account is enough for a build
   that lasts seven days.

## What is where

| File | What it is |
|---|---|
| `Sources/Leverage.swift` | the model, ported from `fantasyedge/leverage.py` |
| `Sources/API.swift` | reads `/api/mosaic` and `/api/live` |
| `Sources/CellView.swift` | one cell, shared by the window and the volume |
| `Sources/BoardView.swift` | the windowed board |
| `Sources/ImmersiveBoard.swift` | the board placed around you |
| `Widgets/` | WidgetKit source, not yet a target - see below |

## The model is the same model

`Leverage.swift` is a hand port of `leverage.py`, and the two are checked
against each other rather than assumed to agree. Same fixtures, same output:

```
pre|pre|0.5000|1.0000|0.00|md,md,md,md
live|live|0.5000|1.0000|0.00|md,md,md,md
final|final|0.5000|1.0000|0.00|md,md,md,md
oneleft|live|0.9984|0.0033|star|1.0000
```

If you change one, change the other, and re-run the comparison.

## Immersive

The windowed board is a plane. The immersive space places the cells around you
and makes **importance depth** - a cell that can still change your week stands
forward, a decided one falls back. On a flat screen that has to be faked with
blur; here it is simply where the thing is.

## The player card is a hologram, not a card

ESPN's headshots are cut-out PNGs with a transparent surround, so on a headset
there is no reason to put one inside a rectangle - the head floats in the room,
lit from behind in the position colour, and the numbers sit around it. A border
here would only be drawing a box around something that already has an edge.

The detail is the default: season by season with positional finish, where he
went in each of your drafts against ADP, and this week restated across PPR,
half and standard. A card that opens shallow and asks for another tap wastes
the one gesture you gave it.

## Watching the game inside the board

The immersive space has two arrangements. Normally the cells sit on an arc in
front of you. Put a game on and they open into a ring around the screen, so you
are watching with your line-up around you rather than beside a list.

**Nothing is bundled and nothing is guessed at.** Point it at a stream or file
URL in the window's settings — anything `AVPlayer` can open — and it plays in
the middle.

## Reactions

The feed carries totals, not events, so the app knows a jump happened but not
that it was a touchdown. It says so honestly: a cell pulses and shows `+6.0`
when points land, and the panel at the edge of vision calls it a **big play**,
a **chunk**, or **moved** by size rather than claiming a play it cannot see.

Reactions are a moment, not a state — they clear after eight seconds so the
board settles.

## Whose board is this

Which team is yours in each league is saved on the server, in
`~/.fantasy-edge/prefs.json`, not on the device - so the choice you make in the
headset is the one the laptop and the television already see. Pick it from
**MY TEAM** in the ornament.

The parent board used to ask for no particular team, so it fell back to
whoever `ESPN_SWID` named or, failing that, the alphabetically first manager -
and the whole board, win probability included, was quietly about a stranger's
roster.

Saving is loopback-only unless the server is started with
`FANTASYEDGE_ALLOW_REMOTE_PREFS=1`. In the simulator that is loopback and just
works; a real Vision Pro on the house network is told plainly when the save
was refused, rather than appearing to save and forgetting.

## The command centre

Three rails on one surface. The left is **standing** - every league, your
record and place in each, and the cross-league totals that only exist once the
leagues are collapsed. The middle is **happening** - this week's matchups, the
live slate, your men ordered by what is at stake, and who is unrostered. The
right is **one player in depth**, because the question a board raises is
always about somebody in particular.

### Which numbers are which

The panels are deliberately unequal in how well founded they are, and say so:

- **Reported** - scores, projections, records, the slate, ownership. Straight
  from the read API.
- **Derived, and labelled** - floor and ceiling are that player's own 20th and
  80th percentile weeks across the games he actually played, not a model's
  opinion. The card says this on the card.
- **Opportunity** - targets, carries, target share, WOPR and aDOT from
  nflverse. `advanced.py` had cached these for months; nothing served them.
- **Absent** - pending waiver claims, trade offers and matchup grades have no
  source in anything this reads. They are missing rather than filled, because
  a dashboard that quietly invents a plausible number is worse than one with a
  hole in it: you cannot tell which half to trust.

## The league view

The command centre answers "how am I doing everywhere". The Leagues tab
answers "what is happening here", which needs the thing the other view
deliberately hides: every slot, bench included.

Four sub-tabs, each on data already in the payload - **Roster** (the line-up,
with each man's fixture, projection, actual and kickoff), **Matchups** (every
pairing in the league, totalled from the same roster rows, so no request per
team), **Standings**, and **Overview**. Trade Block, History and Settings are
absent: nothing this reads has them.

Starters and bench come from the provider's own `started` flag, never inferred
from the slot name - a FLEX and a BN look alike to anything that guesses.

## How it stays fast

Three caches, and one of them is load-bearing rather than an optimisation.

`Leverage.evaluate` is not cheap and is wanted constantly: the league rail and
the week header each want one per league, and SwiftUI re-runs a body whenever
anything observable moves. It is memoised on the live payload's `version` -
the server content-addresses that block, so it changes exactly when a number
changed and not on every poll that returned the same thing - plus which team
is yours, since picking a different team rebuilds the board.

Team totals and club fixtures are memoised the same way. Standings are fetched
once per league and kept: a standings table moves on Tuesdays, not on the
two-second live clock.

All three caches are `@ObservationIgnored`, and that is not a micro-
optimisation. They are written during a view's body evaluation; if observation
tracked them, writing one would invalidate the view that just read it and the
render would loop forever.

## Known gaps

- **The widget is source, not a target.** WidgetKit needs its own extension
  and an App Group, and hand-rolling an embedded appex into a generated
  `.pbxproj` is fragile enough that it is better added once through Xcode:
  *File → New → Target → Widget Extension*, then drag in `Widgets/`. The code
  is written and compiles.
- **Built against the xrOS 26.5 SDK with a 2.0 deployment target**, because
  the installed simulator runtime here is visionOS 2.1. Building for a real
  device needs the visionOS platform installed in Xcode → Settings → Components.
