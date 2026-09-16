# The moment waits for the ball

Integration-12's worst thing: a touchdown's banner, score flash, strobe,
fireworks and section surge all fired as the play *arrived*, and the ball
landed about five seconds later. `s-td-moment-t0.5.png` at integration-12
showed CHI already on 17 with the return still running, and the banner gone
by `t5.1`.

The composer now holds a moment until Broadcast has flown its play
(`MomentGate`, `apple/verify_moment.swift`). Measured here, from the app's own
log:

| Moment | Held | Released by |
|---|---:|---|
| touchdown (the pick-six) | **5.14 s** | the play landing |
| fieldGoal, club seat | **4.38 s** | the play landing |
| fieldGoal, sideline seat | **4.40 s** | the play landing |

Every one was released by the landing, not by the deadline, which is the
play's own flight plus `motion.momentHoldGraceSeconds` (1.0 s).

## Frames

`--times` counts from when the moment appears in the scene, so it is also the
lead the celebration used to have. Each frame is its own launch of the app, so
the game clock differs between them; read them as separate samples, not a
timeline.

- `s-td-moment-t0.5.png` — **nothing is celebrating**. The near rows are
  seated, no banner, no fireworks. Integration-12's frame at this instant had
  the banner up. The score on the boards already reads 17 (see below).
- `s-td-moment-t5.5.png` — **the celebration, at the landing**: the TOUCHDOWN
  banner, fireworks over the rim, the strobe, and the near rows up with arms
  and props raised.
- `s-td-moment-t4.png`, `-t7.png`, `-t9.png`, `-t11.png` — other launches,
  each drifting a little differently; the crowd is up and settling.
- `s-td-moment-t4.5-fg-club.png` — the kick: the ribbon flashing FIELD GOAL
  whole-word in Minnesota purple, the banks strobing purple, and the near
  (Chicago) rows correctly *not* celebrating.
- `s-td-moment-t{0.5,3,4.5,6}-fg-{club,sideline}.png` — the same kick from
  both seats.

## What is still early: the score

The scorebug and the video board are not driven by the moment. They redraw
from the scene in `apply`, so the score changes the instant the play arrives -
about five seconds before the ball lands, as `s-td-moment-t0.5.png` still
shows. That is a separate path and was left alone rather than changed
silently. Fixing it means holding the *displayed* score behind the same gate
(the scene's score, and `BroadcastVideoBoard.key`/`image`), which is Broadcast's
code, not the composer's.

The red-zone crossing has the same shape of mismatch: `status.redZone` fires
on arrival, while the ball crosses the twenty seconds later. It predates this
change and is not in this branch.

## Budgets

Unchanged by this branch: crowd 143,728 triangles / 36 parts, stadium 241k at
touchdown +0.5 s and 242–247k at fieldGoal +0.5 s, ~67 MB textures.
