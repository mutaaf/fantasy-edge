# The immersive red zone

The stadium following a live slate: the channel picks the game, the bowl
changes to it, and the wearer can take the wheel.

Shot with `python3 tools/shoot_redzone.py --device <udid> --app <path>`, which
loads one matchup, opens the stadium with the panel unfolded, then moves the
replay director to a second matchup and takes frames across the fade. The
fade is stretched ×10 for the capture (`-stadiumFadeScale 10`), because it is
over in a third of a second and a simulator screenshot costs about one.

| Shot | What it shows |
|---|---|
| `s-panel-before.png` | MIN @ CHI, the Red Zone panel open at the right hand: the slate, `Follow the ball`, and today's real NFL games read from `/api/redzone` |
| `s-changeover-0..4.png` | the move to DAL @ PHI, across the fade |
| `s-panel-after.png` | arrived: Eagles paint, Eagles crowd, DAL @ PHI on the scorebug |

## What the frames prove

**The bowl fades rather than cuts.** Mean luminance of a 120 px thumbnail
across the sequence, ×10 fade: `105 → 105 → 100 → 78 → 100 → 102 → 102`. The
dip is the dark middle, where the swap happens, and the app says so itself:

    [stadium] changeover: dark at 3.51 s, swapping

3.51 s is half of the stretched fade, as designed. At the shipped speed the
whole changeover is about 0.35 s.

**The livery really changes.** `s-panel-after` is Philadelphia throughout -
EAGLES and PHILADELPHIA painted in the end zones, the ring at midfield, the
crowd in teal, PHI on the scorebug and the win-probability horizon. Nothing
about the building moved.

## What they do not prove

**The scorebug leads the world through a changeover.** In `s-changeover-2`
the field still says BEARS while the scorebug already says DAL @ PHI: the
attachments read `feed.spec` directly and change the instant it arrives, while
the world waits for the dark. It is a window of about a third of a second, and
it is the same class of defect the composer's `StatusGate` exists to prevent -
something on screen ahead of what has been seen. The fix is to hand the
attachments `renderer.shownSpec` instead of `feed.spec`, which is 28 call
sites in `StadiumViews.swift` and belongs to whoever owns that file.

**None of this has been seen with a live game.** Every frame here is a
replayed fixture. The channel's own choosing was exercised against today's
real board (16 NFL games, correctly reporting `nfl`) but with nothing live on
it yet, so the whip-around has never actually been triggered by a real drive
reaching the red zone.
