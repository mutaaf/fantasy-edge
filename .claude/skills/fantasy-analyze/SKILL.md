---
name: fantasy-analyze
description: Run and interpret the fantasy league history analyses. Use when the user asks about their draft tendencies, bench decisions, waiver value, schedule luck, manager profiles, or wants a league report.
argument-hint: [optional analysis name]
allowed-tools: Bash, Read
---

Run the analyses and interpret them. Focus: $ARGUMENTS (default: all).

## Procedure

```bash
python3 -m fantasyedge analyze --json
```

If `exit_code` is 4, no data is loaded. Use the fantasy-pull skill first.

For a shareable artifact:

```bash
python3 -m fantasyedge report --out report.html
```

## The eight analyses

| key | Question it answers |
|---|---|
| `draft_roi` | Which rounds does each manager actually win and lose? |
| `allocation` | Does RB-heavy early actually win in *this* league? |
| `reach` | Does the user systematically pick ahead of market? |
| `bench` | How many points were left on the bench? |
| `waiver` | Do in-season adds beat drafted bench players? |
| `luck` | All-play record versus real record |
| `phase` | Different scoring in weeks 15 to 17? |
| `profile` | Who reaches for a QB, who never drafts a TE? |

## Interpreting honestly

**Every result carries a `caveat`. Carry it with the number.** These are not
boilerplate disclaimers. Each names a specific methodological limit:

- `bench` computes the optimum as the top N scorers, ignoring slot
  eligibility. The leak percentage is an upper bound, not a target.
- `allocation` is correlational on a tiny sample. A few seasons of a 10-team
  league is a few dozen data points split across three buckets.
- `phase` runs on roughly three games per season. Treat it as a prompt to
  investigate, never as a finding.
- `reach` only counts picks that matched an ADP row, so it measures early and
  middle rounds far better than late ones.

**`empty: true` is not an error.** It means the required data is not loaded,
and the `caveat` says which. Report that plainly and say what would fix it.
The `reach` analysis is empty until ADP is loaded via `adp-load`, which is
normal.

**Do not manufacture confidence.** If an analysis rests on three data points,
say so. The failure mode for this tool is not being wrong, it is being
confidently wrong at a glance.

## Where the real edge is

`bench` and `profile` are the most actionable. Bench leak is pure process and
improvable without knowing anything about football. Manager profiles are
directly exploitable in the next draft: if one manager always takes a
quarterback in round 4, the user can let the good ones slide past them.
