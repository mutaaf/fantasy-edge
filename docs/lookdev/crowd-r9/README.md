# crowd-r9 — a club's own colour, on the people who wear it

Crowd round 9 on `actor/crowd-r9`, from the integration tip `9b16788`. Every frame here was shot
in the same session on the same simulator, `-before` from a build of the tip and `-after` from the
fix, so the numbers compare directly.

## What was wrong

A club wore two colours at once. The field painted `teams.*.color`, the club's stated colour; the
crowd dressed from `bowl.crowd.{home,away}`, which `scene.py` solves so white text clears 4.5:1 on
a panel. Read off the served scene:

| club | states | chip it wore | now wears |
|---|---|---|---|
| Philadelphia | `#06424D` midnight green | `#0B798E` bright teal | `#06424D`, unchanged |
| Pittsburgh | `#101820` black | `#4C7399` mid blue | `#213242` |
| Las Vegas | `#000000` black | `#6F6F6F` mid grey | `#424242` charcoal |

The crowd now derives its cloth from the stated colour and moves exactly one thing about it: HSV
value, which is r, g and b scaled together and so cannot shift a hue or a saturation. It is lifted
no further than `visual.crowd.clubValue.floor`, and a club already above the floor is worn as
stated.

## The floor, measured

`FANTASYEDGE_TOKENS` points the API at another token file, so the floor sweeps with no rebuild.
Subject: a bowl-wide frame of two black clubs, `neutralShare` set to 0 for the sweep so the club's
own cloth is the only thing carrying the stand. Window: a fixed rectangle on the far upper deck
(0.20–0.80 × 0.285–0.383 of the frame), read by `tools/crowd_pixels.py --structure`.

| cloth value | 0.00 | 0.15 | 0.20 | 0.25 | 0.30 | 0.35 | 0.50 | 1.00 | *no fans* |
|---|---|---|---|---|---|---|---|---|---|
| mean luma | 16.8 | 17.0 | 17.6 | 17.8 | 18.4 | 18.9 | 21.2 | 32.9 | 12.9 |
| what the cloth adds | – | +0.2 | +0.8 | +1.0 | +1.6 | +2.1 | +4.4 | +16.1 | – |
| p10 | 2.9 | 3.0 | 3.8 | 4.0 | 4.2 | 5.6 | 5.9 | 5.9 | 2.2 |
| detail | 4.28 | 4.31 | 4.30 | 4.33 | 4.35 | 4.40 | 4.71 | 7.45 | 0.99 |

A stand in pure black cloth still measures 4.28 levels of detail against an empty stand's 0.99 —
faces, hands, hair and pale trim carry it — so **there is no value at which a full stand collapses
into one shape in this bowl**. What disappears is the club: under 0.15 its cloth adds less than
half an 8-bit level to its own stand, which is under what an eye can find in a dark field. It
reaches a full level at 0.25. **The floor is 0.26**, just above that, and sRGB 0.26 is 5.5% linear
reflectance — what black fabric actually measures.

## The frames

| file | what to look at |
|---|---|
| `s-bowl-wide-phi-{before,after}.png` | the paint and the stands in one frame: teal stands over a midnight-green field, then both the same colour |
| `s-crowd-closeup-phi-{before,after}.png` | bright teal shirts at two metres, then midnight green |
| `s-bowl-wide-black-{before,after}.png` | two black clubs in a blue-grey bowl, then a dark one |
| `s-crowd-closeup-black-{before,after}.png` | `#6F6F6F` and `#4C7399` at two metres, then charcoal |
| `s-bowl-wide-chi-after.png` | the visiting block reads 14.6° of hue from a home block in the same stand |

Budget across all of them: 140,132–140,145 triangles of 150,000, 36 draw parts of 45, both
unchanged. Dress 2.35–2.43 s against 2.28–2.43 s before.

The black pairing is a throwaway fixture, not a committed one: `replay_game_401772510.json` with
the two clubs' colours, names and event id replaced. A fake game does not belong in
`tests/fixtures`, so it was deleted after the shoot.
