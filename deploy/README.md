# Deploying fantasy-edge at `fantasy.digitalcraftai.com`

Every value in this directory is a placeholder. Nothing here is a real key, a
real project ref or a real client secret, and a test in `tests/test_oauth.py`
fails the build if one appears. Secrets come from the environment of whatever
runs the container, and from nowhere else.

## What the pieces are

| File | Does what |
|---|---|
| `Dockerfile` | Runs `python3 -m fantasyedge api`. No `pip install`, because there is nothing to install. |
| `vercel.json` | Puts `fantasy.digitalcraftai.com` in front of that container: static pages from `docs/`, `/api/*` and `/oauth/*` rewritten to the origin. |
| `schema.sql` | Supabase tables, indexes and row-level security. Run once. |

Two processes, and only one of them is deployable. `fantasyedge api` holds no
credential and calls no provider, which is what makes it safe to face the
internet. `fantasyedge serve` holds an ESPN cookie and polls ESPN, so it stays
on loopback on the user's own machine. Do not containerise `serve`.

## Environment variables

Required by the service:

| Variable | What it is |
|---|---|
| `SUPABASE_URL` | `https://<YOUR-PROJECT-REF>.supabase.co`. Not a secret. |
| `SUPABASE_SERVICE_KEY` | The **service role** key. Bypasses RLS by design. Server only - putting this in a browser publishes every table. |
| `TOKEN_ENCRYPTION_KEY` | At least 32 bytes, base64url or raw. Seals refresh tokens before they reach Supabase. Never sent to Supabase. |
| `YAHOO_CLIENT_ID` | From your Yahoo app. |
| `YAHOO_CLIENT_SECRET` | From your Yahoo app. Confidential client. |
| `OAUTH_REDIRECT_ALLOWLIST` | Comma-separated, exact URIs. `https://fantasy.digitalcraftai.com/oauth/callback` |

Optional:

| Variable | What it is |
|---|---|
| `TOKEN_ENCRYPTION_KEY_OLD` | The previous encryption key. Set only during a rotation window; see below. |
| `FANTASYEDGE_DB` | Path to the SQLite file the read API answers from. Defaults to `/app/data/fantasy.db` in the image. |
| `PORT` | Listen port. Defaults to 8080. |

Generate an encryption key with the standard library and nothing else:

```bash
python3 -c "import base64,secrets;print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip('='))"
```

Never put any of these in a file inside the repository. `.gitignore` already
covers `*.env`, but the rule is that they live in your host's secret store -
Fly secrets, Railway variables, Vercel environment variables, a Kubernetes
secret - and are injected at run time.

## 1. Supabase

1. Create a project. Note the project ref and the service role key.
2. Run the schema:
   ```bash
   psql "$SUPABASE_DB_URL" -f deploy/schema.sql     # or paste into the SQL editor
   ```
3. Confirm RLS: in the table editor every one of `users`,
   `provider_connections`, `refresh_rotations` and `oauth_transactions` must
   show **RLS enabled** with **no policies**. That combination means the anon
   key sees zero rows, which is the intended state. A permissive policy on
   `provider_connections` publishes OAuth material at a URL anyone can guess.

## 2. The container

```bash
docker build -f deploy/Dockerfile -t fantasy-edge .
docker run --rm -p 8080:8080 \
  -e SUPABASE_URL="https://<YOUR-PROJECT-REF>.supabase.co" \
  -e SUPABASE_SERVICE_KEY="<PASTE-AT-RUN-TIME>" \
  -e TOKEN_ENCRYPTION_KEY="<PASTE-AT-RUN-TIME>" \
  -e YAHOO_CLIENT_ID="<PASTE-AT-RUN-TIME>" \
  -e YAHOO_CLIENT_SECRET="<PASTE-AT-RUN-TIME>" \
  -e OAUTH_REDIRECT_ALLOWLIST="https://fantasy.digitalcraftai.com/oauth/callback" \
  fantasy-edge
```

Push it to whatever runs containers with a TLS-terminating hostname. That
hostname is the **origin**; write it down, it goes into `vercel.json`.

Never pass a secret with `--build-arg`. Build args are stored in the image
history and travel with the image into every registry it reaches.

## 3. DNS for `fantasy.digitalcraftai.com`

At the DNS provider for `digitalcraftai.com`:

| Record | Name | Value |
|---|---|---|
| `CNAME` | `fantasy` | `cname.vercel-dns.com` |

Then in Vercel: **Project → Settings → Domains → Add** `fantasy.digitalcraftai.com`,
and wait for the certificate to issue. If you are skipping Vercel and pointing
straight at the container host, use that host's CNAME target instead and let it
terminate TLS; the only hard requirement is that the callback is reachable over
**https** at exactly the URI you allowlisted.

Edit `vercel.json` and replace `REPLACE-ME-origin.example.com` in both rewrites
with the container origin, then deploy. The rewrites are what let one hostname
serve the static pages and the API without a CORS conversation. The
`Referrer-Policy: no-referrer` header on `/oauth/*` is not decoration: the
callback URL contains an authorization code, and a default referrer policy
leaks it to every third-party asset the page loads.

## 4. Register the Yahoo redirect URI

At [developer.yahoo.com/apps](https://developer.yahoo.com/apps/):

1. Your app → **Update**.
2. **Redirect URI(s)**: `https://fantasy.digitalcraftai.com/oauth/callback`
   — exactly this string. Yahoo compares it byte for byte on both legs of the
   exchange, and so does `oauth.check_redirect`. A trailing slash is a
   different URI.
3. **API Permissions**: Fantasy Sports → **Read**. Not Read/Write. Nothing in
   this codebase writes to a league, and asking for write on the consent
   screen is asking the user to trust you with roster moves you will never
   make. The scope requested in code is `fspt-r`.
4. Client type: **Confidential Client**.
5. Put the same string in `OAUTH_REDIRECT_ALLOWLIST`. Two places, one value,
   and they must match.

Yahoo's form currently rejects `oob` and rejects loopback URIs, so
`fantasyedge auth --local` (the RFC 8252 loopback flow) is available for
providers that allow a variable-port `http://127.0.0.1` redirect, and the
copy-the-code path stays the supported one for Yahoo.

## 5. Rotating `TOKEN_ENCRYPTION_KEY`

Rotation does not re-encrypt anything by itself. Each sealed value records the
id of the key that sealed it, so old and new coexist for as long as you let
them.

1. Generate a new key (command above).
2. Set **both**: `TOKEN_ENCRYPTION_KEY` = the new key,
   `TOKEN_ENCRYPTION_KEY_OLD` = the outgoing one. Deploy. Nothing breaks:
   rows sealed with either key open, and every write from now on uses the new
   one.
3. Re-seal the existing rows. A refresh re-seals a connection as a side effect,
   so most rows migrate on their own within an hour; force the rest with a
   one-off that loads each connection and calls `rotate` on it.
4. When `select count(*) from provider_connections where key_id <> '<NEW KEY ID>'`
   returns zero, unset `TOKEN_ENCRYPTION_KEY_OLD` and deploy again.

Do not skip step 4 and leave the old key set forever. The point of rotation is
that the old key stops being able to open anything.

If the key is **lost** rather than rotated, no refresh token is recoverable and
every user must re-link. That is the correct outcome and it is the price of the
key not living in the database.

## What this deployment does not do

* It does not verify anything against Yahoo. As of writing, the Yahoo app in
  question returns `additional_authorization_required`, which is a setting on
  the app registration and not something this code can work around.
* `fantasyedge api` currently serves league history from SQLite. Wiring the
  OAuth routes (`/oauth/start`, `/oauth/callback`) into it is the next step;
  `oauth.begin` and `oauth.finish` are the two calls it needs, and the session
  id they take must be the server's own session cookie, not anything the client
  can choose.
