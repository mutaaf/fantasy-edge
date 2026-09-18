# score-timing: the board waits for the ball

Integration-13's first and second worst things. The moment gate already held
the banner, the fireworks, the strobe and the crowd until Broadcast had flown
a play; the **numbers** did not wait. `td-moment-t0.5` read CHI 17 with the
pick-six still running, and the down turned over before the ball got there.
The banner then outlived its play: at `t8.5` a TOUCHDOWN slab hung over a
board that had moved on to the next snap.

Both are fixed here. `StatusGate` (beside `MomentGate`, swept by
`apple/verify_moment.swift`) holds the arriving status behind the play it
describes, and the composer hands the actors the scene with the status the
stadium is **showing**. Everything else in the scene arrives untouched.

## What the frames show

Each `--times` frame is its own app launch, so the game clocks differ and the
frames are samples rather than a timeline. The log lines below are the
timeline.

| Frame | Board reads | Why it is right |
|---|---|---|
| `s-td-moment-t0.5.png` | MIN 6 · **CHI 10**, 3RD & 8 AT CHI 32, no banner | the pick-six is in the air; at integration-13 this frame read CHI 17 |
| `s-td-moment-t5.1.png` | MIN 6 · **CHI 17** | the ball has landed |
| `s-td-moment-t5.8-band.png` | CHI 17, fireworks, ribbon flashing TOUCHDOWN, near rows up | the score and the celebration arrive together |
| `s-td-moment-t6.png`, `-t8.5.png` | CHI 17, 2ND & 7 AT MIN 31, **no banner** | the next snap took the slab down; at integration-13 it was still up at t8.5 |
| `s-td-moment-t0.5-fg-club.png`, `-fg-sideline.png` | MIN 0 · CHI 7, 4TH & 8 AT CHI 14 · RED ZONE | the kick is still in flight, so the score has not moved |
| `s-bowl-wide-scrub.png`, `s-field-level-scrub.png` | MIN 0 · CHI 0, 2ND & 6 AT MIN 46 | a drive laid at rest flies nothing, so nothing is held: scorebug, ribbon and board agree at once |

## Measured (`stats-td.txt`, one launch)

```
[stadium] moment touchdown fired at t=253.75, held 5.24 s for its play to land
[stadium] score MIN 6 - CHI 17 drawn at t=253.75, held 5.24 s behind 4017728102188
```

The same frame, to the hundredth: the score now changes when the celebration
starts, which is when the ball arrives. Later plays in that run held the
board 3.0–15.7 s.

**The 15.7 s is the mechanism, not a fault.** A scene carries the state after
its *newest* play, and nothing in between, so when a drive arrives with
several plays queued the board can only catch up when the last of them lands.
Holding to the newest keeps the board behind the ball; adopting on the first
landing would put it ahead, which is the defect being fixed. The deadline -
the flight still owed by every play not yet laid, plus
`motion.momentHoldGraceSeconds` - means a play that never flies cannot freeze
the board.

## Still mistimed

- **The video board's last-play line is not held.** `s-td-moment-t0.5-fg-club.png`
  narrates "W.Reichard 31 yard field goal is GOOD" while the kick is in the
  air and the score correctly still reads 0-7. The board's words come from
  the drive's newest arc (`BroadcastVideoBoard.image`, `arcs.last`), not from
  the status, and holding them means feeding the board the newest *laid* play
  from `trails` and doing the same for the drive log beside it, so that the
  two never disagree. That is a Broadcast round, not a director's patch.
- **The win-probability horizon** moves with the play's result on arrival, for
  the same reason: it is a top-level field, not part of `status`.
