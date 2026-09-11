<h1 align="center">fantasy-edge</h1>

<p align="center">
  <strong>The fantasy football command center — every league you play, on every
  screen you own.</strong>
</p>

<p align="center">
  <a href="https://mutaaf.github.io/fantasy-edge/">Connect your leagues</a> ·
  <a href="#the-leverage-model">The model</a> ·
  <a href="#quickstart">Quickstart</a> ·
  <a href="apple/">visionOS app</a> ·
  <a href="AGENTS.md">For agents</a> ·
  <a href="BACKLOG.md">Backlog</a>
</p>

---

## What this is for

Fantasy apps are built one league at a time. If you play in four, you have four
tabs, four sets of push notifications, and no way to answer the only question
that actually matters on a Sunday afternoon: **out of everything happening right
now, what should I be looking at?**

This answers that. One console, every league you play, ranked by what can still
change your week — and the same console on a laptop, a television, a phone and a
Vision Pro, because a fantasy Sunday does not happen on one device.

### The three things nobody else does

**It sizes itself around what matters.** Every cell on the board is as big as its
ability to still change your result. A running back in a tight game with a half
to play fills the screen; a player in a blowout shrinks away on his own. That is
one number, computed, not a layout somebody chose — see [the model](#the-leverage-model).

**It collapses your leagues.** Who do you actually own, across all of them?
Which one deserves your attention in the next ten minutes? Which of your teams
is about to lose because a starter is on a bye? A per-league app cannot ask
those questions, let alone answer them.

**It knows your history and says what it means.** Seven seasons in SQLite means
your opponent's bench habits, your own schedule luck, and how accurate the
projections you are staring at have actually been — carried next to the number
rather than left in a spreadsheet.

### It runs everywhere the same way

| Surface | What it is | State |
|---|---|---|
| **Web** | the full console — board, rankings, analysis, headlines | shipping |
| **Phone** | the same console, laid out for a thumb | shipping |
| **TV** | a ten-foot board driven by the focus engine | shipping |
| **visionOS** | a native SwiftUI app; the board placed around you | [built](apple/) |
| **Spatial (web)** | a preview of the above, in any browser | shipping |

One model, one API, four front ends. The leverage maths is
[~200 lines of pure arithmetic](fantasyedge/leverage.py), ported by hand into
[Swift](apple/FantasyEdge/Sources/Leverage.swift) and JavaScript and checked
against each other, so no screen ever waits on a server to be told how big to
draw a cell.

### From one league to ten

A rookie with one team should see a board, not a dashboard about a board. A
veteran in ten needs triage, not ten cards to scroll. *(This is the current
frontier — see [BACKLOG.md](BACKLOG.md).)*

---

Zero third-party dependencies. Python 3.11+ and the standard library. No pip
install, no virtualenv, no supply chain to rot.

```bash
make test      # 104 tests, no network, under four seconds
make doctor    # diagnoses the setup and prints the exact next command
make board     # the live console at http://127.0.0.1:8770
```

## The leverage model

Leverage is the one idea here. It is the sensitivity of your win probability to
a single player's *remaining uncertainty*:

$$\text{leverage}_i = \varphi\!\left(\frac{m}{s}\right)\cdot\frac{\sigma_i}{s}$$

where `m` is your expected final margin, `s` is the standard deviation of that
margin, and `σᵢ` is the uncertainty this player still carries. Variance
accumulates like independent increments over game time, so a player with
fraction `f` of his game left carries `σ_full · √f`.

Every behaviour you want falls out of the arithmetic instead of being
special-cased:

| Situation | What the model does | Why |
|---|---|---|
| Tied game | Every tile is big | `φ` peaks at `m/s = 0` |
| 40-point blowout | The board goes quiet | `φ` collapses far from zero |
| Player's game ends | His tile vanishes | `σᵢ → 0` |
| One man left, one score in it | He fills the screen | `s` is tiny, so `σᵢ/s` is huge |

That last row is the good one. The "it all comes down to him" tile is arrived
at honestly, not by special-casing the fourth quarter — and there is a test
asserting exactly that.

A second dial, **intensity** (`2·min(p, 1−p)`), says whether the matchup
deserves the screen at all. It is 1.0 at a true toss-up and 0 once the week is
decided, and the board literally desaturates as it falls.

The same model runs at both levels: it sizes a **league** on the parent board
exactly as it sizes a **player** inside one. The mosaic is fractal.

`fantasyedge/leverage.py` is ~200 lines of pure functions over plain numbers,
which is what lets the identical model run in Swift on a TV and in JavaScript
in a browser.

## Quickstart

**ESPN** — the easy one:

```bash
python3 -m fantasyedge setup --provider espn --league <LEAGUE_ID> --teams 10
export ESPN_S2='...' ESPN_SWID='{...}' ESPN_LEAGUE_ID='<LEAGUE_ID>'
python3 -m fantasyedge pull --provider espn --seasons 2019-2026 --json
make board
```

**Sleeper** — no credentials at all:

```bash
python3 -m fantasyedge pull --provider sleeper --league <LEAGUE_ID> --seasons 2021-2025
```

**No credentials, no league** — the bundled fixture:

```bash
make demo
```

Stuck? `python3 -m fantasyedge doctor --json` returns a `next_command` field.
Run it, repeat until `exit_code` is 0. That is the entire operating procedure.

## Three surfaces, one API

The board runs on the web today and is built so a tvOS and a visionOS client
are view layers rather than rewrites. Two constraints shaped everything:

1. **tvOS has no web view.** You cannot wrap the web app for an Apple TV. That
   client must be native SwiftUI driven by the focus engine.
2. **Credentials cannot live on the TV.** `ESPN_S2`/`ESPN_SWID` are browser
   session cookies. Nobody is typing one on a Siri Remote.

So the split is strict:

```
Mac / Pi  ──  fantasyedge serve   holds the cookie, polls ESPN, loopback only
          └─  fantasyedge api     holds nothing, reads SQLite, safe on the LAN
                    ├── Web       the mosaic in this repo
                    ├── visionOS  Safari today; native volumetric later
                    └── tvOS      native SwiftUI, read-only client
```

| | tvOS | visionOS | Web |
|---|---|---|---|
| **Role** | Ambient Sunday companion | Command centre | Analysis surface |
| **Tiles visible** | 6–9, hard ceiling | 12–20 across depth | 30+ |
| **Leverage shown as** | Tile size | **Z-depth** — dead cells recede | Size + density |
| **Input** | Focus engine, directional | Gaze + pinch | Pointer, deep links |

Press **TV** or **Spatial** in the board's header to see each treatment. In TV
mode the arrow keys drive the focus engine and `Enter` opens a card.

## Why this scales

The architecture rests on one rule, enforced in `fantasyedge/live.py`:

> **Live data is shared. Personal data is static. Never compute their product
> on the server.**

There are ~16 games and ~1,700 relevant players on a Sunday. That snapshot is
a few tens of kilobytes and it is **byte-identical for every viewer on earth**,
so it is fetched once and fanned out at the edge. Your personal score is the
*product* of that shared table and your own static roster — and computing that
server-side would mean a unique, uncacheable response per user every few
seconds. So the client joins them and runs `leverage.evaluate` locally, a few
hundred floating-point operations that cost the server nothing.

Cache policy is a property of what the data *is*, declared once in `api.py`:

| Tier | Example | `Cache-Control` |
|---|---|---|
| Immutable | a finished season's draft | `max-age=31536000, immutable` |
| Derived | the nine analyses | `max-age=60, stale-while-revalidate=86400` |
| Live shared | all game state | `max-age=2, stale-while-revalidate=8` |
| Live personal | your leverage | never sent — computed on the client |

`max-age=2` looks pointless until you count: a CDN honouring it collapses every
request in a two-second window into a single origin fetch. Ten million viewers
cost the origin half a fetch per second. ETags are content-addressed, so a poll
that changed nothing costs a header exchange rather than a payload.

## The analyses

Nine pure functions in `analytics.py`, each returning the same `Result` shape
and each carrying a **caveat that a test asserts is non-empty**. Carry the
caveat with the number when you report it — the bench optimum ignores slot
eligibility and is an upper bound, the allocation analysis is correlational on
a small sample, and the phase split runs on three games a season.

| Key | Answers |
|---|---|
| `draft_roi` | Which rounds each manager actually wins |
| `allocation` | Whether a roster shape correlates with finish |
| `reach` | Who drafts ahead of the market (`adp − overall`) |
| `bench` | Points left on the bench, as a share of available |
| `waiver` | How much of a season came from undrafted players |
| `luck` | Real record versus all-play record |
| `phase` | Regular season versus championship weeks |
| `profile` | When each manager takes each position |
| `storylines` | The bargains and reaches of one draft night |

## Layout

```
fantasyedge/
  models.py         normalized records every provider emits — the seam
  providers/        espn, yahoo, sleeper, manual + the Provider ABC
  store.py          SQLite schema, idempotent upserts
  analytics.py      nine pure functions: store in, Result out
  leverage.py       the model above; pure, portable, no I/O
  live.py           the shared tier — game state, identical for every user
  api.py            credential-free read API + SSE delta stream
  serve.py          the draft board; holds the cookie, loopback only
  templates/        board.html, draft_report.html, mosaic.html, connect.html
tools/build_docs.py static build for GitHub Pages: connect page + demo board
tests/              56 tests, fixture-driven, no network
```

Adding a provider is one subclass of `Provider` plus `@register`. Analytics
never imports a provider — it reads normalized tables, which is why the same
nine analyses work across every source, and why swapping in an official API
touches exactly one file.

## Replaying a real Sunday

Every NFL game is either finished or has not kicked off. So possession, ball
position, drives, play-by-play, win probability and a ramping scoreline — every
part of the live tier worth looking at — are unexercisable on any ordinary day,
and no amount of care in the parsers can be checked against anything.

`replay` fixes that by rewinding one real game. It downloads a finished event
once, then rewrites the two files `live.py` already reads — `FANTASYEDGE_
SCOREBOARD_FILE` and `FANTASYEDGE_SUMMARY_DIR/{event}.json` — to show that game
as of a moving point in its own clock. Nothing in the live tier changes and
nothing is mocked at the API boundary, so a replay drives the real scoring, the
real D/ST pairing, the real gamecast shaping and the real possession logic
against ESPN's own payload shapes.

```bash
# Capture once and replay at 60x: a full game in a minute.
python3 -m fantasyedge replay --game 401872656 --out data/replay --speed 60

# In another shell, point any reader at the frames it is writing.
FANTASYEDGE_SCOREBOARD_FILE=data/replay/scoreboard.json \
FANTASYEDGE_SUMMARY_DIR=data/replay \
python3 -m fantasyedge api --host 0.0.0.0
```

`--at 1800` writes a single frozen frame instead — halftime, every time, which
is what a screenshot or a test wants. `--capture` re-downloads.

`frame(scoreboard, summary, game_seconds)` is a pure function and is where the
work happens: it cuts the plays at that instant, rebuilds the drive list with
the one in progress as `current`, recomputes the status, score, line score and
`situation` from the last play that had actually been snapped, and truncates
win probability and scoring plays to match. Anything that had not happened is
gone — including `winner`, which a finished competitor carries and which would
otherwise draw a trophy on a game tied in the first quarter.

### The box score ramps too, and says how far it can be trusted

The summary's `boxscore` is final-state only, and serving it was this
harness's one dishonest number. Every player carried his end-of-game total
from the opening kickoff: the Seahawks defence read **16.0 before anybody had
touched the ball** — a shutout bonus, plus all the yards New England would
eventually gain, plus three interceptions it had not yet caught. Which made
the one thing the product is about, points arriving during a game, the one
thing a replay could not show.

ESPN does publish per-play stat lines, at `.../plays/{p}/participants` on the
core API. That is still not used, because it is roughly 800 requests to
assemble one game. It does not need to be. `play.text` is a machine-written
grammar and every statistic that scores a fantasy point is stated in it:

```
R.Stevenson up the middle to NE 11 for 3 yards (D.Lawrence; D.Thomas).
D.Lock pass short left to J.Smith-Njigba for 45 yards, TOUCHDOWN. J.Myers extra point is GOOD, ...
(Shotgun) S.Darnold sacked at SEA 49 for -5 yards (D.Jones).
```

So the box score is **rebuilt from the text**, in ESPN's own shape, and
`scoring.parse_boxscore` and `scoring.parse_team_defence` consume a replay
through exactly the path they consume a live Sunday through. There is no
second scoring path. Names are resolved against the box score's own athlete
list on surname plus first initial plus club; an ambiguous name is refused
rather than guessed at, because guessing puts a touchdown on the wrong player
and nothing downstream can tell.

**The reconciliation.** ESPN's published final is ground truth, so the parser
is run over the whole game and diffed against it cell by cell:

| | NE at SEA (401872656) | SF at LAR (401872657) |
|---|---|---|
| Cells reconciled | **482 / 485 — 99.4%** | **520 / 531 — 97.9%** |
| passing, rushing, receiving | 100 / 100 / 100% | 94 / 96 / 98% |
| interceptions, fumbles, kicking | 100% | 100% |
| kick / punt returns, punting | 87 / 100 / 100% | 100 / 100 / 100% |
| defensive | 99.6% | 99.3% |
| team totals | 100% | 88% |
| Unresolved names | 0 | 0 |
| Worst athlete, in fantasy points | **0.04** | **0.10** |

Every one of the fourteen residual cells is ESPN's box score disagreeing with
ESPN's own play data, not a misparse — all 223 scrimmage and return plays
across both games agree exactly with ESPN's per-play `statYardage`, and where
`statYardage` says Kaelon Black gained 66 rushing yards the published box score
says 65.

**What is not derived is absent, never backfilled.** Passer rating and QBR are
not in the play text at any price, so they are emitted as `--`, which is
ESPN's own marker for a value it is not stating. First downs, third-down
efficiency, red-zone trips, penalties and time of possession need
down-and-distance bookkeeping this parser does not do, so those team rows are
dropped from a derived box score rather than carried over from the final.
Substituting the final value for a column that is hard is the same bug as
substituting it for all of them, in a smaller hat.

Every frame says which it is serving:

```json
"replay": {"gameSeconds": 1320, "playsIncluded": 54, "playsTotal": 179,
           "boxscore": {"mode": "derived", "source": "play-by-play text",
                        "reconciled": true, "rate": 0.9938,
                        "reconciledCells": 482, "totalCells": 485,
                        "categories": {"passing": 1.0, "kickReturns": 0.8667, ...},
                        "unreconciled": {"kickReturns": {...}},
                        "excluded": ["passing.QBRating", "team.possessionTime", ...],
                        "mismatches": ["NE kickReturns Lan Larison kickReturnYards: derived 50, ESPN 49"]}}
```

`mode` is `"captured"` only when the summary carries no athlete list to derive
against, and `reconciled` is `false` when the capture stops before the end of
the game — a seven-drive test fixture has no final to be diffed against, and
publishing a rate there would measure the trim rather than the parser.

So a defence now opens at the shutout floor and moves with the game, and a
receiver climbs from nothing to what ESPN published:

```
   clock   Smith-Njigba   Stevenson   Maye   |  NE D/ST   SEA D/ST
   15:00           0.00        0.00   0.00   |     10.0       10.0
   10:00 Q1        2.30        0.50   1.00   |     11.0       10.0
   15:00 Q2        4.10        1.20   2.04   |     11.0       10.0
   15:00 Q3       10.30        3.30  10.24   |     10.0        6.0
   10:00 Q4       24.10       12.50  10.68   |      7.0        7.0
   FINAL          26.20       14.50   9.82   |      7.0       14.0
```

Drake Maye peaks at 11.24 and finishes at 9.82, because he throws three
interceptions in the fourth quarter. That is football, and it is why the live
tier's monotonicity assertion is now "points fall only when this player's own
line records something that costs points" rather than "points never fall".

Regenerate the fixtures — never edit one by hand:

```bash
python3 tools/make_replay_fixture.py --event 401872656            # frame() fixture
python3 tools/make_replay_fixture.py --event 401872656 --pbp      # reconciliation fixture
python3 tools/make_replay_fixture.py --event 401872657 --pbp
```

## On the web: connect your own leagues

**[mutaaf.github.io/fantasy-edge](https://mutaaf.github.io/fantasy-edge/)** —
GitHub Pages, so there is no server behind it and never will be. Which decides,
exactly, what a visitor can be offered:

| Provider | On the web | Why |
|---|---|---|
| **Sleeper** | Works. Type a username. | `api.sleeper.app` sends `access-control-allow-origin: *` and needs no auth at all. Username → user id → leagues → rosters, matchups and live per-player points. |
| **ESPN, public league** | Works. Type a league id. | `lm-api-reads.fantasy.espn.com` reflects the `Origin` header, and only 401s when the league is private. |
| **ESPN, private league** | **Refused, deliberately.** | It would need your `espn_s2` and `SWID`. Those are your whole ESPN account, not one league. A public page with a box for them is indistinguishable from a page built to harvest them. Run `python3 -m fantasyedge api` locally instead, where the cookie stays in your own environment. |
| **Yahoo** | **Impossible here.** | OAuth needs a client secret, and a static page has nowhere to keep one. It would take a deployed backend. There is no button, because a button that could not work is a lie about what the page is. |

Live NFL game state works for every visitor whatever their provider, because
ESPN's public slate is CORS-open too. It is joined to a roster by folded name
plus position — never by player id, since Sleeper's ids are not ESPN's and
`espn_id` is null for most of the players anybody starts. The browser runs the
same folding rules as [`identity.py`](fantasyedge/identity.py), and a test
asserts the two tables have not drifted.

The connection lives in that browser's `localStorage` and is sent nowhere;
there is nowhere to send it.

### The demo board

**[/demo.html](https://mutaaf.github.io/fantasy-edge/demo.html)** — one real
league's real season with the people scrubbed out: NFL players are public
figures and keep their names, the managers become "Team 7". It is labelled as
a demo on the page itself, because a visitor landing on somebody else's
anonymised season reads it as either dummy data or their own, and both
readings are wrong.

`make docs` builds both pages into `docs/`, which GitHub Pages serves as-is:
the entry page needs no build input at all, and the demo runs a deterministic
simulated Sunday so it is alive without a server. **`--anon` is the default**
in the Makefile.

## Documentation

- **[AGENTS.md](AGENTS.md)** — the contract for coding agents
- **[CLAUDE.md](CLAUDE.md)** — the long-form rules, gotchas and hard-won bugs
- **[CONTRIBUTING.md](CONTRIBUTING.md)** — how to change this safely
- **[BACKLOG.md](BACKLOG.md)** — what is next and what is deliberately not

## A note on ESPN

ESPN's fantasy endpoints are undocumented and unofficial, and NFL club marks
are licensed. That is fine for your own league; it is a wall if you ever want
this in an app store. The `Provider` seam exists partly so an official API can
replace the unofficial one without touching anything above it.

**No licence has been chosen yet** — see the backlog. Until one is, assume all
rights reserved.

## Deploying it: `fantasy.digitalcraftai.com`

The table above says Yahoo on the web is impossible, and on GitHub Pages it is:
OAuth needs a client secret and a static page has nowhere to keep one. This is
the deployed backend that changes that answer, and everything in it is additive
— the single-user CLI still keeps its token in `~/.fantasy-edge/yahoo.json` and
still works exactly as it did.

Three new pieces:

| File | What it is |
|---|---|
| [`fantasyedge/oauth.py`](fantasyedge/oauth.py) | Authorization Code + PKCE, provider-agnostic. `state`, redirect allowlisting, refresh rotation, reuse detection, and an RFC 8252 loopback listener for the terminal. |
| [`fantasyedge/tokens.py`](fantasyedge/tokens.py) | `TokenStore` with two backends: the home-directory file the CLI already uses, and Supabase over PostgREST with the refresh token sealed before it leaves the process. |
| [`deploy/`](deploy/) | `Dockerfile`, `vercel.json`, `schema.sql`, and a README with the DNS, the env vars, the Yahoo redirect registration and the key-rotation procedure. |

Supabase is reached over PostgREST, which is HTTPS, which means `urllib` is a
sufficient database client. No psycopg, no supabase-py, no wheel that needs a
compiler in an image that holds OAuth refresh tokens. The zero-dependency rule
survives the move to a hosted database, and it stops being a slogan at exactly
the point where a dependency would have to be trusted with a credential.

### The four controls, and why each one is there

**PKCE, S256 only.** A public callback URL means an authorization code can be
intercepted. With PKCE, an intercepted code is not redeemable without the
verifier, which never leaves the server. The weaker method is not a parameter
anywhere in the module, so there is nothing to downgrade — a test greps for it.

**`state`, single-use, ten-minute TTL, bound to the session.** Without it,
anyone can hand a victim a callback URL carrying *their* authorization code and
quietly graft their Yahoo account onto the victim's login. Reading a state
consumes it, because that is how single-use is enforced rather than intended.

**Exact redirect-URI matching against a server-side allowlist.** No wildcards
and no prefix matching. Prefix matching is how open redirects happen, and an
open redirect on the callback puts the code in somebody else's log. The CLI's
loopback listener adds its own concrete `http://127.0.0.1:<port>/callback` to
the allowlist at bind time, so a kernel-chosen port stays compatible with exact
matching.

**Refresh rotation with reuse detection.** This is the one everybody skips.
Rotation alone means a stolen refresh token still works once, and the theft then
looks like a bug: the real user's next refresh fails, they are asked to
reconnect, and nobody investigates. So every retired token's fingerprint is
kept, and presenting one revokes the whole family — both parties lose access and
the user re-links. That is the intended blast radius. An attacker gets one
cycle and a visible disconnection instead of silent permanent access.

`invalid_grant` on refresh is treated as *disconnected, please re-link*, never
as a server error. A 500 gets retried and paged; a revoked grant needs a button.

### What protects the refresh token at rest, and what does not

Sealed in the application before it reaches Supabase: `scrypt` for key
derivation, an HMAC-SHA256 keystream in counter mode, encrypt-then-MAC with a
second HMAC, fresh salt and nonce per record, and the row's own identity as
associated data so a row moved to another user fails to open. The key comes from
`TOKEN_ENCRYPTION_KEY` in the environment and is never sent to Supabase, so a
database dump, a leaked backup or an over-broad RLS policy yields ciphertext.

What it is not: AES-GCM. The standard library has no AES, and this composition —
conventional as it is — has not been analysed by anyone. It does nothing against
a compromised application server, since the key is in that process's
environment. `pgcrypto` was considered and rejected on the ground that every
read here arrives holding the service key, so a key living in the database would
be reachable by the same credential that reads the rows, and the encryption
would buy nothing against the only thing it is for. The module docstring in
[`tokens.py`](fantasyedge/tokens.py) says all of this at length, on purpose.

### Connecting from a terminal

```bash
python3 -m fantasyedge auth --provider yahoo --local   # browser + loopback catch
python3 -m fantasyedge auth --provider yahoo --url     # print URL, copy the code
python3 -m fantasyedge auth --provider yahoo --code '<CODE>'
```

`--local` opens a browser and catches the redirect on a random loopback port, so
a live authorization code never goes onto a clipboard. It is opt-in because it
only works where the provider permits a loopback redirect, and Yahoo's app form
currently insists on https — for Yahoo, `--url` and `--code` remain the path.

**Not verified end to end against Yahoo.** The app registration in question
returns `additional_authorization_required`, which is a setting on the app and
not something this code can work around. Every provider interaction in
[`tests/test_oauth.py`](tests/test_oauth.py) runs against a local `http.server`
that checks the PKCE verifier the way RFC 7636 says to — a stricter counterparty
than the real one, but not the real one.
