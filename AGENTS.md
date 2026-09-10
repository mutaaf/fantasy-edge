# AGENTS.md

The contract for coding agents working in this repository. `CLAUDE.md` carries
the same rules in longer form with the reasoning; read it when a rule here
seems arbitrary, because each one is a bug that already happened.

## Start here, every time

```bash
python3 -m fantasyedge doctor --json
```

It diagnoses the whole setup and returns `next_command`. Loop — run
`doctor --json`, execute `next_command`, repeat — until `exit_code` is 0.
Never guess what is wrong.

| Exit | Meaning | Do |
|---|---|---|
| 0 | Ready | Proceed |
| 1 | Generic error | Read stderr |
| 2 | Config incomplete | `setup` |
| 3 | Credentials missing | **Ask the user.** Never derive one. |
| 4 | No data loaded | `pull` |

Every command accepts `--json`, before or after the subcommand. Nothing reads
stdin, so no command can hang a session. `auth --url` prints a URL and exits;
`auth --code <CODE>` completes it.

## Non-negotiable rules

**Never write credentials into this repo.** `ESPN_S2`, `ESPN_SWID`,
`YAHOO_CLIENT_SECRET` and the Yahoo token are live session credentials. They
belong in the environment or `~/.fantasy-edge/`. If a user pastes one into
chat, use it in the shell and persist it nowhere in the working tree.

**Never invent a league id, cookie, or season range.** Ask.

**`~/.fantasy-edge/prefs.json` is the user's, not yours.** It holds which team
is theirs in each league, the order they arranged, and what they hid. Deleting
it to get a clean screenshot silently undoes work they did by hand, and it
looks to them like the app forgot. Point `HOME` elsewhere if you need a blank
slate.

**Run `make test` before and after any change.** 56 tests, no network, under
two seconds. A green suite is the definition of not-broken here.

**Do not add third-party dependencies.** Standard library only, Python 3.11+.
If something seems to need `requests` or `pandas`, it does not.

**Regenerate fixtures with the script**, never by hand:
`python3 tests/fixtures/make_fixtures.py`. Hand-edited fixtures once caused
duplicate players to collide on a primary key and silently drop 74% of the
roster rows.

## Data gotchas that will bite you

**ESPN roster and transaction views are per scoring period.** Ask without a
`scoringPeriodId` and a finished season returns every matchup with an empty
roster — no error, no warning. `_load_week` fetches one period at a time for
exactly this reason. Do not "optimize" it into a single call.

**A negative ESPN `playerId` is a real pick, not an empty slot.** Team defences
are encoded that way, so `-16014` is the Rams D/ST. Only `-1` and `0` mean an
unfilled slot. Filtering on `playerId <= 0` silently drops every defence.

**An undrafted season still returns a full slate of empty pick slots**, all
carrying `playerId` -1. Both `fetch_season` and `draft_state` filter them.

**Reach is `adp - overall`**, so positive means the pick came *before* the
market had him. Kickers and defences are excluded from the storylines and from
every reach aggregate, because their ADP is a placeholder near the bottom of
the board.

## Reporting results

Every analysis returns a `caveat` and a test asserts none is empty. **Carry the
caveat with the number.** The bench optimum ignores slot eligibility and is an
upper bound. The allocation analysis is correlational on a small sample. The
phase split runs on three games a season. Reporting any of those as settled
fact is wrong.

An analysis returning `empty: true` is not a failure. Its caveat says which
data it needs.

## The surfaces

Two processes, and the split is deliberate:

- **`fantasyedge serve`** holds the ESPN cookie, polls the provider, and binds
  to loopback *because* it holds a secret. Draft board only.
- **`fantasyedge api`** holds no credential and calls no provider. It answers
  from rows already in SQLite, which is what makes it safe on the LAN for a TV
  or a headset.

Never move a credential into `api.py`, and never make a `/api/live` response
vary by user. The moment it varies by viewer it stops being cacheable and the
whole cost model collapses — see the module docstring in `live.py`.

`leverage.py` is pure functions over plain numbers with no I/O, so it can be
ported to Swift and JavaScript verbatim. Keep it that way; the JS port lives in
`templates/mosaic.html` and the two must agree.

## Conventions

- Docstrings explain **why**, not what. Match the surrounding density.
- Comments earn their place by recording a decision or a trap, not by narrating
  the next line.
- New API routes need a cache policy in `api.py`'s dispatch table and an entry
  in `ROUTES`; a test asserts every advertised route dispatches.
- British-ish spelling appears in some docstrings. Match the file you are in.

## Skills

`.claude/skills/` ships `/fantasy-setup`, `/fantasy-pull` and
`/fantasy-analyze`. A test asserts their frontmatter `name` matches the
directory name.
