---
name: fantasy-setup
description: Set up or repair the fantasy-edge league connection. Use when the user wants to connect their Yahoo or ESPN fantasy league, when any fantasyedge command fails, or when they ask why their league data will not load.
argument-hint: [espn|yahoo|manual]
allowed-tools: Bash, Read, Edit
---

Get fantasy-edge to a working state for provider: $ARGUMENTS (default: ask the user).

## Procedure

Run the diagnostic loop. Do not guess at what is broken.

```bash
python3 -m fantasyedge doctor --json
```

Read `exit_code` and `next_command`. Execute `next_command`. Repeat until
`exit_code` is 0. That loop resolves config and data issues on its own.

The one thing it cannot resolve is credentials, because only the user has them.

## When exit_code is 3 (credentials)

**ESPN.** Ask the user to sign into their ESPN league in a browser, open
Inspect Element, go to Application then Cookies then espn.com, and copy the
`espn_s2` and `SWID` values. The league id is the `leagueId=` value in the
league URL. Export all three, then rerun doctor.

**Yahoo.** Two steps, neither of which blocks.

```bash
python3 -m fantasyedge auth --provider yahoo --url --json
```

Give the user the `authorize_url`. When they paste back the code:

```bash
python3 -m fantasyedge auth --provider yahoo --code '<CODE>'
```

They need `YAHOO_CLIENT_ID` and `YAHOO_CLIENT_SECRET` exported first, from an
app created at developer.yahoo.com/apps/create with redirect URI `oob`.

**Manual.** No credentials needed. Ask the user to paste their draft results
page into `draft.txt` and standings into `standings.txt`, then pull with
`--provider manual`.

## Hard rules

Never write a credential into any file in the working tree. Use it in the
shell environment only. If the user pastes one into chat, do not echo it back
and do not persist it.

Never invent a league id, cookie value, or season range. Ask.

## Finish

When doctor returns 0, confirm what is connected and which seasons are
available, then stop. Do not pull unless asked.
