# drive-log: the log lists what has landed

The last consumer that ran ahead of the ball. The score, the ribbon, the board
and the red-zone flag already waited (`StatusGate`, score-timing); the drive
log still named the play in the air, and the drive's result with it.

The composer publishes `shownDrive` beside `shownStatus`, cut at the play the
gate is holding, and `DriveLog` reads that. The rule itself is `LaidPlay`, a
Foundation-only file the sweeps can compile: the board asks it which play has
landed, the composer asks it which plays may be listed.

## What the frames show

Each `--times` frame is its own launch, so these are four samples, not a
timeline. `log.txt` is the timeline: the app says what the log lists, what it
is waiting for, and when the score caught up.

| Frame | The ball | The log ends on | Header |
|---|---|---|---|
| `s-in-flight-pass.png` | a deep pass in the air, 3rd & 5 on the grass | the rush before it | "CHI drive" |
| `s-landed-pass.png` | trail on the grass, 1st & 10 at MIN 13 | that pass, +17 | "CHI drive" |
| `s-in-flight-fieldgoal.png` | the kick climbing toward the posts, 4th & 8 | the incompletion before it | "MIN drive" |
| `s-landed-fieldgoal.png` | the kick down, MIN 3 on the bug and the ribbon | - | - |

The pass pair is the evidence for the log; the kick pair is the evidence for
the hold. In the landed kick the panels have yielded to the celebration, so
there is no log in that frame to read - `log.txt` carries what it listed.

From `log.txt`, one play, both halves of the rule moving together:

```
drive log lists 7 of 8 plays, newest 401772810938, waiting on 401772810961
score MIN 3 - CHI 7 drawn at t=25.97, held 4.12 s behind 401772810961
drive log lists 8 of 8 plays, newest 401772810961, waiting on -
```

A drive laid at rest - a scrub, a seat change, reduce motion - holds nothing
and lists everything at once: `lists 7 of 7 plays, waiting on -`.

## Worst thing left

`held 18.68 s behind …`: a drive that arrives with several plays already
queued holds the board for the whole queue, because a scene carries only the
state after its newest play. The alternative - adopting on the first landing -
puts the board ahead of the ball again, which is the defect being fixed.
Recorded at score-timing; unchanged here.
