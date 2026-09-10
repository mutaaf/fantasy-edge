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

## Known gaps

- **The widget is source, not a target.** WidgetKit needs its own extension
  and an App Group, and hand-rolling an embedded appex into a generated
  `.pbxproj` is fragile enough that it is better added once through Xcode:
  *File → New → Target → Widget Extension*, then drag in `Widgets/`. The code
  is written and compiles.
- **Built against the xrOS 26.5 SDK with a 2.0 deployment target**, because
  the installed simulator runtime here is visionOS 2.1. Building for a real
  device needs the visionOS platform installed in Xcode → Settings → Components.
