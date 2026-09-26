# motion-1 — the motion pass

Shot on `Stadium 26.5` (visionOS 26.5 simulator) at the animation round. The
simulator cannot measure frame time honestly; the counts below are geometry and
the tick is the main thread's own, not a frame rate.

Five frames, all through motion rather than at rest, because that is what the
round changed.

| Frame | What it is for |
|---|---|
| `s-redzone-trails-p0.5.png` | half a second into a pass: the live trail is drawn behind the ball as far as it has flown, its head on the ball, and the scorebug still reads `MIN 0 CHI 0 · 2ND & 7 AT MIN 28` - the status has not got ahead of the ball |
| `s-redzone-trails-p1.0.png` | the same pass a second in: the arc complete, the ball down, the board still on the play before it until the frame it lands |
| `s-td-moment-t0.5.png` | half a second into the pick-six: the ball still lit in the air with its streak, the section up, the banks strobing |
| `s-td-moment-t3.png` | three seconds in |
| `s-td-moment-t6.png` | six seconds in, `motion.momentSeconds` |

## Budget

`stats.txt`, from the same run:

    [stadium-stats] stadium: models 89, draw parts 106, triangles 238812, texture memory ~67 MB
    [stadium-timing] stadium main-thread tick: 0.375 ms mean over 120 frames

Against the budget in `docs/ART_BIBLE.md` (287k triangles, 160 draw parts,
300 MB): inside all three. Nothing this round added geometry or per-frame work.
One thing took work away - `BroadcastActor.move` now returns when the entity is
already where it is being sent, and `settle` runs on every scene, which in a
replay is every 0.7 s and mostly moves nothing.

## The changeover, measured

`tools/measure_changeover.py`, six switches on the same simulator:

    [stadium] changeover: dark at 0.36 s, swapping
    [stadium-timing] stadium relivery: 0.215 s      # clubs seen before
    [stadium] changeover: back up over 0.35 s
    ...
    [stadium-timing] stadium relivery: 0.440 s      # clubs not seen before

The repaint is 0.215-0.440 s and the way back is 0.35 s. Before this round the
repaint's cost was charged to the way back, so there was no way back: see
`apps/saturday/docs/REDZONE.md`.
