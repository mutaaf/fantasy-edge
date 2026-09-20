# Live snapshots: a sample, not the whole night

The recorder keeps a per-game summary snapshot for the six live games with the
highest leverage, re-chosen every cycle; across 19 September that touched 54 of
the 74 games and came to 92 MB. All of it is on disk here; 27.8 MB of it is in
git, and the rest is not.

**Which six, and why.** The same rule the recorder watches by, applied to the
whole night: every recorded board was ranked by `cfb.leverage`, and these are
the games that spent the most frames inside the live top six. Ties break on the
highest leverage each game reached. Nothing here was hand-picked.

| Game | Frames in the watched six | Peak leverage | Snapshots | Size | In git |
|---|---:|---:|---:|---:|---|
| LSU-MISS (401856688) | 195 | 81.3 | 153 | 4.8 MB | yes |
| FRES-SJSU (401860888) | 169 | 44.4 | 165 | 5.4 MB | yes |
| PUR-UCLA (401858458) | 158 | 47.3 | 152 | 5.2 MB | yes |
| SDAK-BOIS (401860885) | 149 | 61.2 | 132 | 4.4 MB | yes |
| FSU-ALA (401856685) | 145 | 58.3 | 125 | 3.7 MB | yes |
| SMU-LOU (401858230) | 141 | 70.9 | 117 | 4.2 MB | yes |
| NIU-ARIZ (401856793) | 135 | 21.3 | 85 | 1.1 MB | no |
| UK-TA&M (401856694) | 126 | 50.7 | 104 | 3.5 MB | no |
| MONT-ORST (401860886) | 118 | 26.2 | 107 | 3.7 MB | no |
| CLT-APP (401864574) | 112 | 55.0 | 105 | 3.9 MB | no |
| NEV-MTSU (401864443) | 104 | 61.4 | 85 | 3.0 MB | no |
| FIU-FAU (401862771) | 104 | 54.0 | 77 | 2.7 MB | no |
| ... and 42 more games | | | | | no |

**What dropping them costs.** A dropped game's play-by-play is still complete:
its final summary in `../final/` carries every play, and `cfb/reconstruct.py`
can rebuild any moment of it from the play wallclocks. What is gone is the
sequence of *in-flight* summaries - what ESPN was publishing about that game
minute by minute while it was still on.

**Nothing pretends otherwise.** `/api/slate` marks every tile with `detail`:
`available` when this capture can answer now, `afterFinal` when its play-by-play
only arrives with the final, `unavailable` when nothing was kept. Opening such a
game says which; it does not 404 as though the game never existed.

