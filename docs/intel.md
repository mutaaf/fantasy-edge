# Intel

Three ways to produce an insight, in strict order of how much you should
trust them.

1. **Strict compute.** Arithmetic over rows already in SQLite. No model, no
   key, no network. This is the default and the whole product.
2. **Bring-your-own-key AI.** A model you pay for, given the strict-mode
   findings and told to write them up. It narrates; it never sources.
3. **Apple Intelligence.** The same narration, produced on device by a Swift
   client, submitted through the same seam.

Two files: `fantasyedge/intel.py` computes, `fantasyedge/ai.py` narrates.
They never merge their outputs.

---

## 1. Strict compute

`intel.build()` does no I/O. Everything it needs is a payload the API has
already built and cached, passed in as a keyword argument:

```python
from fantasyedge import intel

brief = intel.build(
    mosaics=app.mosaics(),                     # /api/mosaic
    live=app.live(),                           # /api/live, or None before kickoff
    injuries=app.injuries()["injuries"],       # /api/injuries
    analyses={L["id"]: app.analyses(L["provider"], L["leagueId"])["analyses"]
              for L in app.mosaics()["leagues"]},
    opportunity=profile.opportunity,           # optional; hits nflverse
    limit=12,
)
brief.as_dict()
```

Purity is the point. The same call runs against a fixture in `test_intel.py`
and against a real Sunday in production; neither path can reach the network
from inside, and no credential ever enters the module.

### What it can actually say, and from what

| Insight | Computed from | Fires when |
|---|---|---|
| `carrying` | live snapshot joined to `roster_slot` | one starter has ≥25% of the points your line-up has scored |
| `fragility` | `leverage.evaluate` over the same cells the mosaic sizes | live, expected margin positive, win probability under 85% |
| `decider` | `leverage.sigma_for`, `leverage.evaluate` | exactly one starter on either side still playing, and the week is not decided |
| `pregame` | `roster_slot.projected` | nothing has kicked off — says so rather than inventing a read |
| `conflict` | `roster_slot.started` across every followed league | a player starts for you in one league and against you in another |
| `exposure` | same | a player starts in three or more of your line-ups |
| `injury` | `injuries.detect` + `draft_pick` + `adp` + `roster_slot` | the wire names one of your starters in an injury headline |
| `opportunity` | nflverse via `advanced.season_profiles` | WR/TE ≥20% target share, or RB ≥14 touches a game, on under 12 points a game |
| `history` | `analytics.bench`, `analytics.luck`, `analytics.projection_accuracy` | that analysis is not empty; narrowed to your own row |

Three of these exist only because this project holds several leagues in one
database. `conflict` is the clearest: a single-league view structurally cannot
tell you that the man you are starting in one league is playing against you in
another, and that is a real number, because his projection appears on both
sides of your Sunday.

### The three rules that hold it up

**Provenance travels with the number.** An `Insight` is not a string. It is a
string plus a list of `Fact`s, each naming the table or function it came from
(`roster_slot.projected`, `leverage.evaluate`, `nflverse via
advanced.season_profiles`). `Fact.__post_init__` refuses a fact with no
source, and `Insight.__post_init__` refuses an insight with no facts. A
plausible sentence nobody can check is the failure this guards against, so it
is a construction error rather than a lint.

**The caveat travels with it too.** `analytics.py` already makes every result
carry its own weakness and a test asserts none is empty. A layer that reads
nine caveated analyses and emits one confident headline would silently undo
that, so `Insight.caveat` is required and non-empty, and `history_insights`
copies the analysis's caveat **verbatim** — a paraphrase is a second chance to
lose the qualification. A test asserts the string equality.

**Computed and model-written are different types.** See below.

### Metrics deliberately not produced

The design this view is modelled on shows five things no feed within reach
publishes. They are named in `intel.UNAVAILABLE` with the reason, and shipped
in every brief so the UI can say so out loud rather than leave a gap the
reader fills in with an assumption:

- **First Read Rate** — needs per-snap coverage charting.
- **Yards Per Route Run** — needs routes run, charted by PFF, not in nflverse.
- **Route Participation** — same missing denominator.
- **Route tree** — needs per-route classification from tracking data.
- **Target heatmap** — needs per-target field coordinates.

What we do have is in `intel.AVAILABLE_OPPORTUNITY`: targets, carries, target
share, air yards share, WOPR, aDOT, YAC. Estimating YPRR from targets would
put a number on the screen that looks like the others and is not one, which is
the worst single thing this view could do.

---

## 2. Bring-your-own-key AI

```python
from fantasyedge import ai

client = ai.client_for("anthropic")            # or "openai", "google"
brief.narration = ai.narrate(brief, client)
```

`narrate` never raises. A missing key, a rejected key, a rate limit, an
unreachable host and a body that is not JSON are all ordinary states of this
view — the computed brief above the fold is already complete — so each comes
back as `Narration.error = {"state", "message", "remedy"}` in plain language.
The states are `no_key`, `rejected`, `rate_limited`, `unavailable`,
`unreachable`, `malformed`, `failed`, `nothing_to_say`, `unknown_provider`.

### Keeping model prose distinguishable from computed fact

Styling can be got wrong by a client. A type cannot. Four things, in order of
strength:

1. **Different types, different keys.** `Insight` and `Narration` are separate
   classes and land under `brief.insights` and `brief.narration`. A client
   that renders only `insights` is correct and complete.
2. **`origin` is a read-only property.** `Insight.origin` returns `"computed"`,
   `Narration.origin` returns `"model"`, and neither can be assigned — not by
   a caller, not by a round-trip through a dict. Tests assert the
   `AttributeError`.
3. **The model is given only findings.** `intel.as_prompt_facts` flattens the
   brief to findings, their numbers and their caveats — no ids, no rosters, no
   raw payload. A narrator with only the facts can get the emphasis wrong,
   which is recoverable. A narrator with the raw payload can find a number
   nobody computed.
4. **What it wrote is checked.** A prompt is a request; `verify_numbers` is a
   guarantee. Every numeric token in the prose is matched against
   `intel.allowed_numbers(brief)`; anything else lands in
   `Narration.unverified`. `intel.mentions_unavailable` separately catches a
   model reaching for yards per route run because that is what scouting
   reports say. `Narration.trustworthy` is false if either fires, and
   `as_dict()` always carries the label *"Written by a model from the computed
   findings below. Not itself a source."*

Small integers 0–10 are allowed through unflagged: flagging "one of your
starters" as an invented statistic is the false positive that teaches a reader
to ignore the flag.

### Keys

Environment first (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`,
also `GEMINI_API_KEY`), then `~/.fantasy-edge/ai.json`, mode 600, outside the
working tree — the same posture as every other credential here. Never in the
repository, never in a URL, never logged, never in a returned payload.

Two precautions worth naming because they are the ones that get skipped:

- **Google's key goes in a header, not `?key=`.** Every example puts it in the
  query string. `urllib.error.HTTPError` stringifies to include the URL, so
  one 429 would print the key into a traceback, a log line, and any error
  handed back to a browser. `GoogleClient` sends `x-goog-api-key`.
- **Every error string goes through `redact`.** Providers really do echo the
  credential back in a 401 body. `redact` blanks keys it was told about and,
  by shape, ones it was not. A test drives a stub that echoes the key in its
  401 and asserts it appears in no exception, payload, log line, stdout or
  stderr.

`ai.available()` reports which providers are configured as a boolean. There is
no field that could carry a key back out; "show me my key to check it" is how
keys end up in screenshots.

No retry on a 429. The caller is a person pressing a button, not a backfill,
and an immediate second request is how a rate limit becomes a ban.

### Model ids

`PROVIDERS` carries a default per provider. Model names move faster than this
file will, so every one is overridable per call, by `FANTASYEDGE_AI_MODEL`, or
per provider by `OPENAI_MODEL` / `ANTHROPIC_MODEL` / `GOOGLE_MODEL`. A 404
comes back as `rejected` with a remedy naming the override rather than as a
stack trace. **This is the field most likely to be stale — check it before
blaming the transport.**

---

## 3. Apple Intelligence — what the Swift side must implement

`FoundationModels.framework` is present in the visionOS 26.5 SDK on this
machine, so on-device inference is genuinely available. It is Swift-only:
there is no way to invoke it from Python and no HTTP endpoint in front of it.
Rather than pretend, `ai.SuppliedClient` accepts finished text and submits it
to exactly the same verification, labelling and payload slot a cloud model's
output goes through. The Swift side gets no privileged path and no way to have
its output mistaken for a computed fact.

```python
brief.narration = ai.narrate(brief, ai.SuppliedClient(text_from_swift))
# -> provider "apple", model "apple-foundation-models", origin "model"
```

The Swift client must:

1. **Fetch the brief.** `GET /api/intel` (see wiring below) and render
   `insights` — that is the complete product and needs no model.
2. **Build the prompt from the brief, not from the raw payload.** Use the
   `narration.prompt` block the endpoint returns, which is
   `ai.SYSTEM` plus `ai.prompt_for(brief)`. Do not assemble your own from
   rosters or scores; the guarantee in point 4 of the previous section depends
   on the model having seen only findings.
3. **Run `SystemLanguageModel` / `LanguageModelSession`** with that system
   instruction and that user content, and check availability first —
   `SystemLanguageModel.default.availability` reports device support, Apple
   Intelligence being switched off, and model assets still downloading as
   distinct cases. Each is a plain-language state beside an empty narration
   slot, exactly like `no_key`; none is an error dialog.
4. **Post the finished text back** to `POST /api/intel/narrate` with
   `{"provider": "apple", "text": "..."}`. The server runs `verify_numbers`
   and `mentions_unavailable` over it and returns the `Narration`. Render the
   result, not the text you sent — the server's copy carries `unverified`,
   `flaggedMetrics` and `trustworthy`.
5. **Label it.** Show `narration.label` with the prose, and keep the computed
   insights visible beneath it. If `trustworthy` is false, say which figures
   were not computed; do not quietly drop them.
6. **Send nothing else.** No roster, no ids, no key. There is no key.

A Swift client that would rather verify locally can port `verify_numbers` —
it is a regex over the prose against a set of tokens — but the server-side
check must still run, because it is the one the payload's `trustworthy` flag
comes from.

---

## Wiring into `api.py`

Done. Three routes, and the cache policies are the point.

```python
["GET",  "/api/intel",         "the computed brief: insights, caveats, provenance"],
["GET",  "/api/intel/models",  "which model providers are configured"],
["POST", "/api/intel/narrate", "narrate the brief - loopback only, costs money"],
```

`Api.brief()` returns the `intel.Brief`; `Api.intel_brief()` wraps it as the
payload, with `narration` carrying the prompt block a Swift client needs plus
any prose already paid for. `--no-ai` on `fantasyedge api` makes
`client_for` unreachable and reports every provider as unconfigured with a
reason, for the headset build where there is nobody to type a key.

### `/api/intel` - `CONFIG`, and not `LIVE`

It is built from `mosaics()`, which honours `prefs.json`, so it is a different
payload per person by construction. The live tier's two-second `max-age` only
works because every viewer gets identical bytes there; putting a personal
payload on that tier would hand one reader another reader's board out of a
shared cache. See `live.py`'s docstring. A test asserts the policy is `CONFIG`
and is not `LIVE`.

### The compute cache: what actually changes a brief

Building one walks every followed league's mosaic, the live snapshot, the
injury wire and up to nine analyses per league - about four seconds against
the real database. Three things can change it, and all three are cheap to
read, so the brief is memoised against the tuple of them:

| Input | Key component | Moved by |
|---|---|---|
| stored rows | the database mtime, the same stamp `cached()` uses | `pull` |
| live game state | the live payload's own `version` content hash | a scoring play |
| whose board this is | a hash of `prefs.json` | changing your team pick |

Two details worth naming because both were measured:

- **One slot, not `cached()`.** `cached()` keeps an entry per key forever, and
  this key contains a content hash that changes on every scoring play. A
  Sunday would leave a few thousand whole briefs pinned in memory. There is
  one user, so one slot is the right number.
- **The live probe is itself rate-limited to two seconds.** Producing the key
  means producing the live snapshot, which costs about four tenths of a
  second - so validating the cache cost more than the cache saved, forever, on
  every poll. Two seconds is `LIVE`'s own `max-age`: the staleness this
  project already tells every cache between here and the screen to accept.
  With it, a repeat request is about half a millisecond.

### The model cache: what a narration is keyed on

This is the half that costs money, and the rules are ordered by how much they
matter.

**1. No GET produces a narration.** `/api/intel` returns the computed brief and
whatever prose has already been paid for. It reaches no provider, ever. A
board left open on a television polls it for hours. Measured: sixty polls,
zero calls.

**2. The key is the brief's *shape*, not its numbers.** `api.narration_shape`
hashes, per insight: its key, kind, league, the ids of the players it names,
and every numeric fact **bucketed** - percentages to ten points, fantasy
points to five, counts exactly. `Win probability 61%` and `62%` are the same
paragraph of English, so they must hash the same or a live Sunday re-buys
identical prose every few seconds. Hashing `prompt_for(brief)` instead would be
exact and wrong for that reason; hashing the insight keys alone would be coarse
and wrong the other way, holding a stale sentence through a genuine collapse.
Player ids are in the key because `carry:espn-99` does not say who is carrying.

**3. A shape change still cannot spend faster than the floor.**
`FANTASYEDGE_AI_MIN_INTERVAL`, 120 seconds by default. Inside it, a moved brief
is answered with the last paragraph, `cached: true`, `throttled` counting down
and `factsChanged: true` telling the reader it has drifted. Rule 2 makes the
common case free; rule 3 bounds a client that got rule 1 wrong.
`{"refresh": true}` skips the cache but not the floor.

Every narration response carries `cached`, `ageSeconds`, `createdAt`,
`factsChanged`, `briefShape` and `calls` - the last being the count this
process has actually spent, also on `/api/intel/models`, so a client can show
it.

**A cached paragraph is re-verified, not replayed.** `verify_numbers` and
`mentions_unavailable` run again against the brief on screen *now*, because
`trustworthy` has to describe the figures the reader can see beneath the prose.
Replaying the stored flags would make it mean "was true when written", which is
not what the label says.

Supplied text - Apple Intelligence - skips both the cache and the floor. It
was produced on the user's own device and costs this process nothing; throwing
it away to save a call that was never going to be made is the wrong economy.

### `/api/intel/narrate` - loopback only

The same restriction `POST /api/prefs` carries, for a second reason on top of
the first: it is the one route in `api.py` that reads an API key and spends
money. Its escape hatch is `FANTASYEDGE_ALLOW_REMOTE_AI`, deliberately a
different variable from the prefs one - letting a housemate reorder your
leagues from the television is not the same decision as letting them run up
your model bill. The key is read from the environment or
`~/.fantasy-edge/ai.json` at call time and goes out of scope with the client;
it never becomes an attribute of the app, so the LAN-safe read tier stays
credential-free even while a narration is in flight.

`/api/intel/models` is `CONFIG` and returns booleans. There is no field on it
that could carry a key, a prefix or a suffix, and a test asserts none of the
three appears in the payload.

### The nflverse season, and why the brief says so

`intel.build` asks `profile.opportunity` for the season the mosaic is about.
In week one of a new year nflverse has published 47 players on one game
apiece, which is not empty - it passes an emptiness check and then fails
`MIN_GAMES` a moment later, so every opportunity insight silently does not
fire and a whole generator vanishes from the brief with no note. `Api`
resolves the season by `MIN_GAMES` instead and falls back to the last one that
has any, and the brief carries a note saying so. The season the numbers came
out of travels in each insight's facts, which is what the caveat had been
promising all along without a fact to back it.

**AI chat is out of scope.** There is no conversational endpoint and none
should be added here; `/api/intel/models` reports `chat.available: false` and
the web view says "coming soon".

### The Intel view in the web console

`templates/mosaic.html`, a tab beside Analysis. Computed findings first and
unaided: one card per insight, each showing its facts with the table or
function each came from, the sources it was computed from, and its caveat.
Model prose, if asked for, sits in a hatched amber panel above them - never
instead of them - carrying `narration.label`, the provider and model, whether
it is cached and how old, and a red block naming any figure that was not
computed here. The five metrics in `intel.UNAVAILABLE` are printed with their
reasons rather than omitted, beside what nflverse does publish.

There is deliberately **no key field on the page**. A key pasted into a browser
lives in the DOM, in the form history and in any screenshot; the loopback API
can already read one from the environment, so the safe version of that
affordance is its absence. The page says where a key is read from instead.

One client-side trap worth recording: the tab polls `/api/intel`, whose
`Cache-Control` is `max-age=30`. That is right for a proxy and wrong for the
tab that just bought a narration - the poll ten seconds later was answered from
the browser's own cache with a body written before the prose existed, and wiped
it off the screen. The poll uses `cache: "no-cache"` to revalidate, which the
handler answers with a 304 and no payload.

---

## Tests

`tests/test_intel.py`, 82 tests, no network and no real key.

The three cloud providers run against a local `http.server` speaking each
one's real response shape, with a `mode` switch for success, 401, 429, 500, a
body that is not JSON, and well-formed JSON with nothing in it. It asserts the
key reaches the right header, never the URL and never the body; that a keyless
client makes no request at all; that a 429 is not retried; and that a key
echoed back in a 401 body escapes into no exception, payload, log line,
stdout or stderr.

The strict half runs against `tests/fixtures/espn_2025.json`. Matchup insights
whose thresholds are statements about a specific margin are tested against
hand-built line-ups instead, so the assertion is arithmetic rather than a
coincidence of the recorded season. `profile.opportunity` is injected rather
than patched, which is the test saying out loud that the engine does no I/O.

The wiring half asserts the money. A counting stub is registered in
`ai.CLIENTS` and the real `Api` is subclassed with only `brief()` swapped, so
every cache decision, the loopback guard and the throttle under test are the
shipped ones. It asserts that forty polls of `/api/intel` reach no provider;
that thirty explicit requests cost one call; that a point of win probability
does not buy a second paragraph and a collapse does; that twenty posts against
a moving brief still cost one call under the floor, and that `refresh` cannot
beat it; that supplied Apple text costs nothing and is kept; that a cached
paragraph is re-verified against the brief on screen; and that a POST from a
LAN address is refused without spending anything, under its own escape hatch
rather than the prefs one.
