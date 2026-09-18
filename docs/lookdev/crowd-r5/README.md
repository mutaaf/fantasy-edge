# crowd-r5 — whose crowd it is

Crowd round 5 on `actor/crowd-r5`, branched from integration `99a0cb2`. Shot with the
harness at 1400 px, on a private simulator clone and derived data.

**The mix, from the scene and nothing else.** `[stadium] crowd support: home 85%, visiting 9%,
neutral 5% of 34,280 seats taken`. Home and away colours, the away section and the bench range
all come from the scene; no club is named anywhere in the crowd's code.

| Shot | What to look at |
|---|---|
| `s-bowl-wide.png` | The visitors as one block in the far upper corner, home blue everywhere else, corners visibly thinner than midfield. |
| `s-crowd-closeup.png` | Club seat: the near rows watching, not waving, in a 0-0 first quarter. |
| `s-crowd-closeup-clubLevel.png`, `-endzone.png` | Shoes on the tread: integration-12's overhang above the row below is gone. |
| `s-crowd-closeup-upper.png`, `-sideline.png`, `-field.png`, `-pressBox.png` | Every other seat preset; fans face the field from all of them. |
| `s-td-moment-t0.5.png`, `-t5.1.png` | The home side scores: up in stages, still celebrating at 5 s. |
| `s-td-moment-p3-visitors.png`, `-p7-visitors.png` | The visitors score (MIN 12, CHI 17, 4th): their section lifts and brightens across the bowl while the near home rows stay in their seats. |

`stats-club.txt`, `stats-td.txt` and `stats-visitors.txt` carry the `-stadiumStats` counts.
Crowd: **135,998–136,330 triangles, 38 draw parts**, against 143,728 and 36 at integration-12,
inside the 150k / 45 the art bible allows.
