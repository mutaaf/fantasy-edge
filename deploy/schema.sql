-- fantasy-edge, Supabase schema.
--
-- Run once against a fresh project:  supabase db execute --file deploy/schema.sql
-- (or paste it into the SQL editor). It is idempotent, so re-running is safe.
--
-- NOTE ON ENCRYPTION. pgcrypto is deliberately NOT enabled here and the sealed
-- refresh token is a plain `text` column. The application seals it before it
-- ever reaches Postgres - scrypt-derived key, HMAC-SHA256 keystream,
-- encrypt-then-MAC, key from TOKEN_ENCRYPTION_KEY in the app's environment.
-- See the module docstring in fantasyedge/tokens.py, which is explicit about
-- what that does and does not protect.
--
-- The reason not to use pgcrypto: every application read reaches these tables
-- through PostgREST holding the service key. If the decryption key also lived
-- in the database, that one credential would both read the row and open it,
-- and encryption at rest would buy nothing against a database compromise -
-- which is the only thing encryption at rest is for. Keeping the key in the
-- application environment means a leaked dump, a leaked backup or an
-- over-broad policy yields ciphertext and nothing else.

create extension if not exists "pgcrypto" with schema extensions;  -- gen_random_uuid only

-- --------------------------------------------------------------------------
-- users

create table if not exists users (
    id          uuid primary key default gen_random_uuid(),
    -- Supabase Auth's user id, when the deployment uses Supabase Auth. Kept
    -- separate from `id` so the table survives swapping the identity provider.
    auth_uid    uuid unique,
    email       text,
    created_at  timestamptz not null default now()
);

-- --------------------------------------------------------------------------
-- provider connections: one row per (user, provider)

create table if not exists provider_connections (
    id                    uuid primary key default gen_random_uuid(),
    user_id               text not null,
    provider              text not null,
    scopes                text not null default '',
    redirect_uri          text not null default '',

    -- The sealed refresh token. Ciphertext only: "fe1.<key id>.<salt>.<nonce>.
    -- <ciphertext>.<tag>", all base64url. Never a plaintext token, and never
    -- selected by any read path except the refresh routine.
    refresh_sealed        text not null default '',
    -- SHA-256 of the current refresh token. Reuse detection compares
    -- fingerprints so retired tokens need not be kept in any form.
    refresh_fingerprint   text not null default '',
    -- Which TOKEN_ENCRYPTION_KEY sealed this row, so a rotation window knows
    -- which key to use without trying both.
    key_id                text not null default '',

    -- The rotation family. Every refresh token descended from one
    -- authorization shares it, and a reuse detection revokes the family, not
    -- just the token that was replayed.
    family_id             uuid not null,

    revoked               boolean not null default false,
    revoked_reason        text not null default '',

    -- Epoch seconds rather than timestamptz: PostgREST hands these straight to
    -- Python, and float seconds compare and sort without a timezone question
    -- on either side. `created_at` below stays a real timestamp for humans.
    created_at_epoch      double precision not null default 0,
    rotated_at_epoch      double precision not null default 0,
    disconnected_at_epoch double precision not null default 0,

    created_at            timestamptz not null default now(),
    unique (user_id, provider)
);

create index if not exists provider_connections_family
    on provider_connections (family_id);

-- --------------------------------------------------------------------------
-- retired refresh tokens: the spent list that makes reuse detectable

create table if not exists refresh_rotations (
    id               bigserial primary key,
    family_id        uuid not null,
    -- SHA-256 hex of a refresh token we have already retired. Presenting one
    -- of these means two parties hold tokens from this family, and we cannot
    -- tell which is the user - so the family is revoked.
    fingerprint      text not null,
    retired_at_epoch double precision not null default 0,
    unique (family_id, fingerprint)
);

create index if not exists refresh_rotations_lookup
    on refresh_rotations (family_id, fingerprint);

-- --------------------------------------------------------------------------
-- OAuth transactions: state and PKCE verifier, in flight

create table if not exists oauth_transactions (
    state                text primary key,
    provider             text not null,
    -- Sealed with the same construction as a refresh token, AAD-bound to the
    -- state. It lives about ten minutes, and for those ten minutes it is the
    -- only thing between an intercepted authorization code and a token.
    code_verifier_sealed text not null,
    redirect_uri         text not null,
    -- Binds the callback to the browser session that started it. A state that
    -- validates in a different session is the CSRF case, not a retry.
    session_id           text not null default '',
    created_at_epoch     double precision not null default 0,
    expires_at_epoch     double precision not null default 0
);

create index if not exists oauth_transactions_expiry
    on oauth_transactions (expires_at_epoch);

-- --------------------------------------------------------------------------
-- Row-level security
--
-- THE POLICY, AND WHY IT LOOKS LIKE THIS.
--
-- RLS is enabled on every table and NO policy grants the `anon` or
-- `authenticated` roles anything. That is not an omission - it is the whole
-- design. Supabase exposes every table in the `public` schema through
-- PostgREST at a URL anyone can reach with the publishable anon key. A table
-- holding OAuth material with RLS off, or with a permissive policy, is a
-- public endpoint serving refresh tokens. Enabling RLS with no policy means
-- the anon and authenticated roles see zero rows, always.
--
-- The application reaches these tables with the service key, which bypasses
-- RLS by design. So the access rule is enforced in one place - the server -
-- and the database's job is to make sure there is no second way in.
--
-- Consequence to keep in mind: never expose these tables to a browser client,
-- and never "fix" a 401 from the anon key by adding a policy here. If a
-- browser needs to know whether a user is connected, the server answers that
-- from `StoredConnection.to_public()`, which cannot carry a secret.

alter table users                enable row level security;
alter table provider_connections enable row level security;
alter table refresh_rotations    enable row level security;
alter table oauth_transactions   enable row level security;

-- Belt and braces: revoke the table grants too, so a future policy added by
-- accident still does not hand out rows.
revoke all on users, provider_connections, refresh_rotations, oauth_transactions
    from anon, authenticated;

-- The one policy in the file, and it reads nothing sensitive: a user may see
-- that their own account row exists. Uncomment only if the browser needs it.
-- create policy users_read_self on users
--     for select to authenticated
--     using (auth_uid = auth.uid());

-- --------------------------------------------------------------------------
-- Housekeeping
--
-- Expired transactions are dead weight and every one of them holds a sealed
-- verifier. The application purges them, but a scheduled job means an
-- application that stops running does not leave them lying there. With
-- pg_cron enabled:
--
--   select cron.schedule('purge-oauth-transactions', '*/15 * * * *',
--     $$delete from oauth_transactions
--        where expires_at_epoch < extract(epoch from now())$$);
