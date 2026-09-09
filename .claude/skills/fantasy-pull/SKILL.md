---
name: fantasy-pull
description: Ingest fantasy league history into the local database. Use when the user wants to load, refresh, backfill, or re-sync their league seasons from Yahoo or ESPN.
argument-hint: [season range like 2019-2026]
allowed-tools: Bash, Read
---

Load league-seasons into the local store. Requested range: $ARGUMENTS

## Procedure

1. Confirm the setup is healthy before spending a long network round trip:

```bash
python3 -m fantasyedge doctor --json
```

If `exit_code` is 2 or 3, stop and use the fantasy-setup skill instead.

2. Find out what actually exists before choosing a range:

```bash
python3 -m fantasyedge discover --provider <p> --json
```

Discovery returns real seasons. Never assume a range. For Yahoo especially,
game keys change every year and discovery is the only correct way to resolve
them; a hardcoded table breaks silently each September.

3. Pull:

```bash
python3 -m fantasyedge pull --provider <p> --seasons <range> --json
```

## What to watch for

`pull` is idempotent. It replaces a league-season atomically and never
duplicates, so a partial failure is always safe to retry.

The store reports rows offered versus rows landed and warns on any gap. **A
gap is a real problem, not noise.** It means primary-key collisions swallowed
data, which silently corrupts every downstream analysis. If you see something
like `warn: roster_slot 2550 offered, 680 stored`, surface it to the user
instead of continuing as if the pull succeeded.

Yahoo's roster endpoint is one call per team per week. A ten-year backfill of
a 10-team league is roughly 1,700 requests and will take a long time. Warn
the user before starting one, and pull a single season first to confirm the
pipeline works end to end.

Seasons that fail individually are skipped rather than fatal. For a private
league the user must have been a member that season; there is no workaround.

## Finish

Report which seasons landed and their row counts. Offer to run the analyses,
but do not run them unprompted.
