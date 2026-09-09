# Backlog

Ordered by what unblocks the most. Each item says what "done" means, because
an item without that is a wish.

---

## Now

### 1. Real live feed behind `LiveSource`
`live.py` ships `SimulatedSource`, a deterministic Sunday. The whole point of
the ABC is that the real feed is one subclass and nothing above it moves.

**Done when:** an `EspnLiveSource` returns the same `{s, r, g}` shape from real
scoring-period data, the simulator still backs the tests, and `--simulate`
selects between them.
**Watch for:** roster and scoring views are per `scoringPeriodId`. Asking
without one returns empty rosters with no error. See AGENTS.md.

### 2. Choose a licence
The repo is currently all-rights-reserved by default, which blocks any fork —
including an internal one. This is the cheapest unblock on the list.

**Done when:** a `LICENSE` file exists and the README's closing note is
replaced with it.

### 3. `git`-based provenance for `docs/`
`make docs` is run by hand. A stale Pages build silently misrepresents the
project.

**Done when:** the build stamps its source commit into the page and a check
fails if `docs/index.html` is older than `templates/mosaic.html`.

---

## Next

### 4. tvOS client
Native SwiftUI — tvOS has no web view, so the mosaic cannot be wrapped. The
data layer is done: `/api/mosaic` plus `/api/live/stream`, and `leverage.py`
ports to Swift almost line for line.

**Done when:** an Apple TV on the LAN renders the parent board, the focus
engine moves between league cells, and the ceiling of ~8 tiles is respected.
**Watch for:** 10-foot legibility roughly doubles every type size, and safe-area
insets are real. No text input exists — every control must be reachable by
directional focus.

### 5. visionOS client
Safari on Vision Pro already runs the board today, and the **Spatial** surface
is a preview of the treatment. A native client earns its keep only through
genuine depth.

**Done when:** low-leverage cells recede in real Z rather than in CSS
`perspective`, and the matchup holds a comfortable focal distance.

### 6. Player-specific variance
`SIGMA_FULL` is a flat per-position constant. A workhorse RB and a boom-bust
deep threat plainly do not carry the same uncertainty, and the model currently
says they do.

**Done when:** σ is derived per player from that player's own week-to-week
history in `roster_slot`, falling back to the position constant below some
minimum sample. Carry the sample size in the caveat.

### 7. Correlation between stacked players
The model assumes per-player outcomes are independent. A QB and his own WR1
are strongly correlated, so a stack is overweighted today. This is stated in
the board's caveat, which is honest but not a fix.

**Done when:** same-team offensive players share a covariance term and
`s = √(1ᵀΣ1)` rather than `√Σσᵢ²`. The properties in `TestLeverage` must
still hold.

---

## Open questions

### 8. Leverage versus attention
**Pre-game players outrank Q4 players**, because all of their uncertainty is
still ahead of them. The model is right; it is not obviously what a *live*
board wants, since attention belongs on what is actionable now.

Deliberately unresolved. Options: blend a liveness term into tile size; keep
size pure and encode liveness in colour or motion; offer both and let the
viewer choose. Picking one silently would be the wrong move — it is a product
decision, not a maths one.

### 9. Multi-tenancy
Everything today assumes one household: credentials in one environment, one
SQLite file, no accounts. Serving leaguemates means per-user credential
handling and auth, and that is a materially different security surface — other
people's session cookies at rest.

**Not started deliberately.** Decide whether it is wanted before building it.

---

## Later

- **Historical replay.** The database already holds every week ever played.
  Feeding `LiveSource` from `roster_slot` instead of a simulator would let you
  re-watch a 2023 championship as a live board, and would test the whole live
  path against real data.
- **Injury and news on the card.** `serve.py` already fetches and attaches ESPN
  news by player name; the player card is the natural home for it.
- **Draft board convergence.** `board.html` and `mosaic.html` are two front
  ends over one data model. They should probably be one.
- **Yahoo and Sleeper on the mosaic.** The API is provider-agnostic; only ESPN
  has been exercised end to end through the board.
- **Season-long leverage.** The same maths applied to a playoff race rather
  than a single week: which remaining games can still change your seed.
- **Accessibility pass.** Focus order, reduced-motion (partly done), and a
  screen-reader account of a layout whose meaning is carried by *area*.
