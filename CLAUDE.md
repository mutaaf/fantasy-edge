# fantasy-edge

Pulls a fantasy football league's full history from Yahoo or ESPN, normalizes
it into SQLite, and runs nine analyses on it.

## Contract for Claude Code

**Always start with `doctor`.** It diagnoses the whole setup and returns the
exact next command. Never guess what's wrong; run it and read `next_command`.

```bash
python3 -m fantasyedge doctor --json
```

```json
{
  "ok": false,
  "exit_code": 3,
  "checks": [{"name": "credentials", "status": "fail", "detail": "...", "fix": "..."}],
  "next_action": "credentials: missing env: ESPN_S2, ESPN_SWID",
  "next_command": "export ESPN_S2=... ESPN_SWID='{...}' ESPN_LEAGUE_ID=..."
}
```

Loop until `exit_code` is 0: run `doctor --json`, execute `next_command`,
repeat. That is the whole operating procedure.

### Exit codes

| Code | Meaning | What to do |
|---|---|---|
| 0 | Ready | Proceed |
| 1 | Generic error | Read stderr |
| 2 | Config incomplete | `setup` |
| 3 | Credentials missing or invalid | Ask the user for them; see below |
| 4 | No data loaded | `pull` |

### Every command accepts `--json`

It works before or after the subcommand. `analyze --json` returns each
analysis as `{key, title, headline, columns, rows, caveat, empty}`. Parse
that rather than scraping terminal output.

### Nothing blocks on stdin

`auth --url` prints the authorization URL and exits. `auth --code <CODE>`
completes the exchange. There is no interactive prompt in any code path an
agent will hit, so no command can hang a session.

## Standard flows

**ESPN, the easy one:**
```bash
python3 -m fantasyedge setup --provider espn --league <LEAGUE_ID> --teams 10
export ESPN_S2='...' ESPN_SWID='{...}' ESPN_LEAGUE_ID='<LEAGUE_ID>'
python3 -m fantasyedge discover --provider espn --json
python3 -m fantasyedge pull --provider espn --seasons 2019-2026 --json
python3 -m fantasyedge report --out report.html
```

**Yahoo, two-step auth:**
```bash
python3 -m fantasyedge setup --provider yahoo --league <LEAGUE_ID> --teams 10
export YAHOO_CLIENT_ID='...' YAHOO_CLIENT_SECRET='...'
python3 -m fantasyedge auth --provider yahoo --url --json   # give URL to user
python3 -m fantasyedge auth --provider yahoo --code '<CODE>' # after they paste it back
python3 -m fantasyedge pull --provider yahoo --seasons 2019-2026 --json
```

**Draft day:**
```bash
python3 -m fantasyedge draft-watch --provider espn --league <ID>          # poll every 30s
python3 -m fantasyedge draft-watch --provider espn --league <ID> --once --json
python3 -m fantasyedge adp-load --season 2026 --provider espn --csv adp.csv
python3 -m fantasyedge draft-report --provider espn --league <ID> --out draft.html
```

```bash
python3 -m fantasyedge serve --provider espn --league <ID>    # auto-syncing board
```

`draft-watch` prints only picks it has not seen yet and stops when the draft
completes. `draft-report` renders a standalone page for any league in the
database and auto-detects which team is the user's from `ESPN_SWID`. `serve`
runs the live board on 127.0.0.1 and polls ESPN itself, which a published page
cannot do: it is sandboxed to an allowlist and holds no session cookie.

**Sleeper, no credentials:**
```bash
python3 -m fantasyedge pull --provider sleeper --league <LEAGUE_ID> --seasons 2021-2025
```

A Sleeper league id is one season; prior years hang off `previous_league_id`
and the adapter walks that chain. Its player ids are its own, and `espn_id` is
null for most stars, so ADP joins on normalised name plus position instead.

**No credentials at all:**
```bash
python3 -m fantasyedge pull --provider manual \
  --draft draft.txt --standings standings.txt --league mine --season 2025
```

**Last week, replayed:**
```bash
python3 -m fantasyedge last-week --json            # the week, best game first
python3 -m fantasyedge last-week --pull            # all of it, one request per game
python3 -m fantasyedge last-week --open 401872660  # how to open that one
python3 -m fantasyedge last-week --offline         # from disk, no requests
```

Needs no credential and no database. The week is read off ESPN's own board -
the most recent one whose every game is final, so a Thursday with one game
played offers the week before it rather than a half-played one. `--pull` costs
one request per game and is free to re-run; a pulled week then lists and opens
with no network at all.

**Final scores are hidden unless `--spoilers` is passed**, on the command line
and at `/api/lastweek`, because a picker for games you have not seen must not
be a results page. Each row carries a reason to watch that survives that
rule - "3 lead changes", "won on a touchdown in the last minute" - and a
`precision` saying which answer it is: `quarter` from the slate alone, `play`
once the game is pulled and its play-by-play can be read.

## Rules

**Never write credentials into a file in this repo.** `ESPN_S2`, `ESPN_SWID`,
`YAHOO_CLIENT_SECRET` and the Yahoo token are live session credentials. They
belong in the environment or `~/.fantasy-edge/`. If the user pastes one into
chat, use it in the shell and do not persist it anywhere in the working tree.

**Never invent a league id, cookie, or season range.** If `doctor` says a
credential is missing, ask the user for it. Do not try to derive it.

**Run `make test` before and after any code change.** 25 tests, no network,
under a second. A green suite is the definition of not-broken here.

**ESPN roster and transaction views are per scoring period.** Ask without a
`scoringPeriodId` and a finished season returns every matchup with an empty
roster - no error, no warning. That silently costs the started flag and every
analysis that needs a position. `_load_week` fetches one period at a time for
exactly this reason; do not "optimize" it back into a single call.

**A negative ESPN `playerId` is a real pick, not an empty slot.** Team defences
are encoded that way, so `-16014` is the Rams D/ST. Only `-1` and `0` mean an
unfilled draft slot. Filtering on `playerId <= 0` silently drops every defence
in the league.

**An undrafted ESPN season still returns a full slate of empty pick slots.**
Every one carries `playerId` -1. Both `fetch_season` and `draft_state` filter
them; dropping that filter invents a 192-pick draft that never happened and
silently poisons the draft log and every draft analysis.

**A player id is only unique inside the provider that issued it.** ESPN,
Yahoo and Sleeper all mint their own, and they collide as strings. Group or
key on `(provider, player_id)`, never on the id alone. The one place this is
tempting is the shared live tier, where it silently merges two different
people the moment a second provider is followed.

**ESPN's fantasy player id doubling as its site athlete id is a coincidence,
not a design.** It is why a live box score joins to an ESPN roster for free,
and it holds for exactly one of the three providers. Everything else joins
through `identity.py`, which is the single owner of name folding - do not add
a fourth copy of it. A roster whose ids resolve to nothing does not raise; it
reports every player as scoreless, which looks like a quiet Sunday.

**ESPN stamps a stale score on the plays after a score.** On event 401772949
the two timeouts following the winning touchdown carry 37-36, the score before
its two-point try, and the game's own last record carries 37-38. Walking every
play in order therefore counts two lead changes that never happened and puts
the winning score on "END GAME". A lead can only change on a play that scores,
so `week._play_swing` reads `scoringPlay` plays alone.

**Do not add third-party dependencies.** Zero-dependency is a deliberate
constraint: stdlib only, Python 3.11+. If something seems to need `requests`
or `pandas`, it doesn't. nflverse publishes parquet beside its CSV, and
parquet is the one that would need pandas: read the `.csv.gz` releases.

**ESPN never says where a pass was caught, so a live scene estimates it.**
The estimate is wrong by the yards after the catch - 4.4 yards on average and
31 at worst, measured over three games. `truth.py` corrects a finished game
from nflverse's published rows, and every play and arc carries whether it is a
`live` estimate or `corrected`. Never present one as the other, and never
present lateral placement as measured: nobody publishes it. See
`docs/PLAY_ACCURACY.md`.

**ESPN and nflverse mean different things by a spot on a change of
possession.** On a kickoff from a team's own 35, ESPN says 65 (the distance to
the end zone) and nflverse says 35 (the marker); on one punt ESPN reported 16
where nflverse reported 84. Both are self-consistent statements, not bugs. So
special-teams plays are matched on kind and clock rather than on their spot,
and a correction only ever supplies a *relative* yardage, which carries no
convention. The scene draws from ESPN's `yardLine`, which is fixed to the
ground and right in both cases.

**Regenerate fixtures with the script, never by hand.**
`python3 tests/fixtures/make_fixtures.py` is deterministic. Hand-edited
fixtures caused a real bug during development where duplicate players
collided on a primary key and silently dropped 74% of the roster rows.

## Layout

```
config/league.toml       league settings; nothing is hardcoded in source
fantasyedge/
  models.py              normalized records every provider emits
  providers/base.py      Provider ABC + registry + stdlib HTTP with retry
  providers/{espn,yahoo,sleeper,manual}.py
  store.py               SQLite schema, idempotent upserts
  analytics.py           nine pure functions: store in, Result out
  doctor.py              self-diagnosis, agent-facing
  report.py              HTML and text rendering
  serve.py               localhost draft board, polls ESPN itself
  leagues.py             followed leagues + board config read from the db
  advanced.py            nflverse opportunity metrics
  nflverse.py            the one owner of talking to nflverse: releases, cache
  truth.py               ESPN's live estimate, corrected by what was published
  templates/             draft_report.html, board.html
  cli.py                 argparse wiring
tests/                   25 tests, fixture-driven, no network
```

Adding a provider means one subclass of `Provider` plus `@register`. Nothing
else changes. Analytics never imports a provider; it reads normalized tables,
which is why the same nine analyses work across all three sources.

## Interpreting results

Every analysis returns a `caveat` and a test asserts none is empty. When
reporting findings to the user, carry the caveat with the number. The bench
optimum ignores slot eligibility and is an upper bound. The allocation
analysis is correlational on a small sample. The phase split runs on three
games a season. Reporting any of those as settled fact is wrong.

Two conventions in the draft analyses are easy to get backwards. **Reach is
`adp - overall`, so positive means the pick came before the market had him.**
And **kickers and defences are excluded from the storylines and from every
reach aggregate**, because their ADP is a placeholder near the bottom of the
board; leaving them in makes every manager look like a wild reacher. The
reach analysis proper still counts them, which is why its own numbers run
higher than the storylines'.

An analysis that returns `empty: true` is not a failure. It means the data it
needs isn't loaded, and its `caveat` says which. Read it and act on it rather
than treating it as an error.
