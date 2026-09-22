# What the Yahoo credential actually reaches

Reconnaissance, 22 September 2026, against the live APIs with the credential in
`~/.fantasy-edge/`. Reproduce with `tools/yahoo_probe.py` after
`source ~/.fantasy-edge/env`.

The short answer: **the credential is a Fantasy Sports credential and nothing
else, and today it does not even reach that.** Yahoo's authenticated
sports-data API no longer exists. There *is* a public, unauthenticated Yahoo
scores feed, it is genuinely interesting, and it has nothing to do with the
credential.

---

## 1. The Fantasy Sports API: reachable in principle, 401 today

The token in `~/.fantasy-edge/yahoo.json` had expired (12 September). It
refreshes cleanly, so the refresh token is alive and the client id and secret
are valid. Every Fantasy call then fails identically:

| Probe | Status |
|---|---|
| `users;use_login=1/games` | 401 |
| `users;use_login=1/games;game_keys=nfl/leagues` | 401 |
| `game/nfl` | 401 |
| `game/nfl/stat_categories` | 401 |
| `game/nfl/position_types` | 401 |

```
oauth_problem="additional_authorization_required", realm="yahooapis.com"
```

That is Yahoo's wording for *this token does not carry the permission*, and the
token itself says why: the stored response has **no `scope` field** and no
`xoauth_yahoo_guid`. A correctly scoped Yahoo Fantasy token carries both.

**Root cause, in our code.** `providers/yahoo.py::authorize_url()` builds the
consent URL from `client_id`, `redirect_uri`, `response_type` and `language` —
and no `scope`. So the consent screen never asked for Fantasy Sports read, and
the resulting grant cannot reach the Fantasy API. `oauth.py`, the newer
multi-user module, declares `scope="fspt-r"` correctly; the CLI path predates it
and was never brought in line.

This is a one-line fix plus a re-consent, but the re-consent needs a browser
and a human, so it is not something to do unattended:

1. add `"scope": "fspt-r"` to the `authorize_url()` parameters
2. `python3 -m fantasyedge auth --provider yahoo` and approve again

Until then the Yahoo *fantasy* provider cannot be exercised against the live
API at all — it has only ever run against fixtures here, and that remains true.
**Nothing about the provider's parsing is known to be broken**; it simply never
gets a payload to parse. A test that asserts the scope is present would have
caught this, and does not exist.

---

## 2. Authenticated sports data: the product is gone

| Host | Result |
|---|---|
| `sports.yahooapis.com` | **DNS does not resolve** |
| `query.yahooapis.com` (YQL) | **DNS does not resolve** |

Not 401, not 404 — no such host. Yahoo retired YQL in 2019 and the v1
`sports.yahooapis.com` API with it. There is no authenticated Yahoo sports-data
surface left to get access to, so no key, plan or scope unlocks one. If the
expectation was "Yahoo Sports API" as a data feed comparable to ESPN's, that
product does not exist.

---

## 3. The public feed, which needs no credential at all

`api-secure.sports.yahoo.com/v1/editorial/…` answers **unauthenticated**. I sent
no token; it returns 200. This is what Yahoo's own front end consumes.

```
GET /v1/editorial/s/scoreboard?leagues=nfl&date=2026-09-20   → JSON, 14 games
GET /v1/editorial/game/nfl.g.20260920034                     → XML, one game
```

The scoreboard carries 95 fields per game. Most of the interesting ones —
`drives`, `play_by_play`, `last_play`, `scoring_summary`, `teams` — are **not
inline**: they are pointers of the shape `["gamedrives", "nfl.g.20260920034"]`
into data islands the page fetches separately. The scoreboard alone is thin.

### The end-zone question

This is the one gap in the stadium: ESPN never sends distance to the end zone in
a **live** situation (0 of 887 NFL, 0 of 749 college), so a live game's ball is
estimated rather than known. Yahoo's schema has it:

```xml
<yards_to_endzone/>    <down/>    <distance/>
```

Present, emitted, and **empty for a finished game** — as are `start_yardline`
and `team_in_possession` in the JSON. They are situational fields, populated
during play.

**This is where the evidence stops.** There was no live game anywhere — NFL had
none on 22 September, and MLB, WNBA and NHL all returned zero live games at the
time of probing — so I could not observe a populated `yards_to_endzone`. The
schema is confirmed; **live population is unverified**. Do not build on it until
someone has seen it carry a number.

To settle it in one command during any live game:

```bash
python3 -c "
import json,urllib.request
u='https://api-secure.sports.yahoo.com/v1/editorial/s/scoreboard?leagues=nfl'
r=urllib.request.Request(u,headers={'User-Agent':'fantasy-edge/1.0'})
for g in json.load(urllib.request.urlopen(r))['service']['scoreboard']['games'].values():
    if 'progress' in str(g.get('status_type')):
        print(g['status_type'], 'ytez=', g.get('yards_to_endzone'),
              'down=', g.get('down'), 'dist=', g.get('distance'),
              'poss=', g.get('team_in_possession'))
"
```

---

## 4. Yahoo against ESPN, yesterday's real slate

14 NFL games, 20 September 2026. ESPN from the pull at
`.claude/worktrees/rz-replay`, Yahoo from the public scoreboard.

| | ESPN | Yahoo |
|---|---|---|
| Games | 14 | 14 |
| Final scores | — | **14/14 identical** |
| Play detail | full play-by-play inline, 161–213 plays per game | pointers only |
| Game id | `401872934` | `nfl.g.20260920034` |
| Team id | `CIN` | `nfl.t.34` |

No disagreement on any score. Two **abbreviation** mismatches, which is the
adoption cost in miniature:

| Team | ESPN | Yahoo |
|---|---|---|
| Jacksonville | `JAX` | `JAC` |
| Washington | `WSH` | `WAS` |

**There is no shared identifier of any kind** — not for games, not for teams.
Joining the two sources means matching on date plus both teams, with an alias
table for the abbreviations that disagree. That is precisely the trap CLAUDE.md
already names: *an id is only unique inside the source that issued it.*

---

## 5. Recommendation

**Fix the fantasy scope. Do not adopt Yahoo as a data source.**

**Worth doing** — the missing `scope="fspt-r"`, a one-line change plus a
re-consent. It is a real bug that makes the Yahoo fantasy provider dead on this
machine, and the user has a Yahoo league. Add a test asserting the authorize URL
requests a scope, so it cannot regress silently.

**Worth one experiment, not a project** — the live `yards_to_endzone`. If it is
populated during play, it closes the stadium's only genuine accuracy gap, and
that is worth knowing. Run the snippet above during any live game before
spending anything further. Note the cost even if it works: an undocumented
front-end endpoint with no stability contract, no shared ids with ESPN, and a
second live poller to keep inside a request budget. It would be a *correction*
to ESPN's live situation, in the same shape as the existing nflverse
correction — never a replacement.

**Not worth it** — Yahoo as a general second source. It agrees with ESPN on
every score, so it corroborates nothing we doubt; it carries less inline than
ESPN; its play detail is behind pointers we would have to reverse-engineer; and
for finished games ESPN's play records already carry field position (191/191),
with nflverse correcting the geometry exactly. A second source is complexity
that buys nothing except in the one live-only case above.

**Say no to** any plan that treats today's credential as sports-data access. It
is not, and no amount of configuration makes it so.
