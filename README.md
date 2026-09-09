<h1 align="center">fantasy-edge</h1>

<p align="center">
  <em>Your league's entire history, normalized into SQLite — and a live board that
  resizes itself around whatever can still change your week.</em>
</p>

<p align="center">
  <a href="#the-leverage-model"><strong>The model</strong></a> ·
  <a href="#quickstart"><strong>Quickstart</strong></a> ·
  <a href="#three-surfaces-one-api"><strong>Surfaces</strong></a> ·
  <a href="AGENTS.md"><strong>For agents</strong></a> ·
  <a href="BACKLOG.md"><strong>Backlog</strong></a>
</p>

---

Every fantasy app shows you a scoreboard. None of them tell you **where to look.**

At 3:47pm you have nine players running across six games. Two of them still
matter. The rest are either finished, buried in a blowout, or on a bench that
cannot change anything. A scoreboard gives all of them the same row height.

This gives them different sizes.

```
┌───────────────────────────────┬───────────────┐
│                               │  Nico Collins │   tile area = how much
│      BIJAN ROBINSON           │  6.2      Q4  │   this cell can still
│      18.4              RZ     ├───────┬───────┤   change your week
│                               │ K 7.1 │ D 4.0 │
└───────────────────────────────┴───────┴───────┘
```

Zero third-party dependencies. Python 3.11+ and the standard library. No pip
install, no virtualenv, no supply chain to rot.

```bash
make test      # 56 tests, no network, under two seconds
make doctor    # diagnoses the setup and prints the exact next command
make board     # the live mosaic at http://127.0.0.1:8770
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
  templates/        board.html, draft_report.html, mosaic.html
tools/build_docs.py static build for GitHub Pages
tests/              56 tests, fixture-driven, no network
```

Adding a provider is one subclass of `Provider` plus `@register`. Analytics
never imports a provider — it reads normalized tables, which is why the same
nine analyses work across every source, and why swapping in an official API
touches exactly one file.

## Live demo

`make docs` renders a self-contained board into `docs/`, which GitHub Pages
serves as-is. It runs a deterministic simulated Sunday so the page is alive
without a server. **`--anon` is the default** in the Makefile: NFL players are
public facts and stay, but the people in your league become "Team 3".

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
