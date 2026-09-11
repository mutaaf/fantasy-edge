"""Where refresh tokens live. One interface, two backends, one honest answer
about what protects the secret.

WHAT PROTECTS THE REFRESH TOKEN AT REST
---------------------------------------
`SupabaseTokenStore` seals every refresh token before it leaves this process,
with a construction built only from `hashlib`, `hmac` and `secrets` because
this project takes no third-party dependencies. It is spelled out here rather
than hidden behind a friendly function name, because a reader who cannot tell
what the cipher is cannot tell what it is worth.

    key material   scrypt(master, salt, n=2**14, r=8, p=1, dklen=64)
                   -> enc_key = dk[:32], mac_key = dk[32:]
                   fresh 16-byte random salt per record
    keystream      HMAC-SHA256(enc_key, nonce || counter_be32) for counter
                   0,1,2,... concatenated and truncated, XORed with the
                   plaintext. This is a PRF run in counter mode - the same
                   shape as NIST SP 800-108 counter-mode KDF - which is a
                   standard and analysable way to build a stream cipher out
                   of a PRF. It is not a home-made permutation.
    nonce          16 random bytes per record, never reused. Keystream reuse
                   under a fixed key is the failure mode that breaks stream
                   ciphers outright, and it is prevented here by the salt and
                   the nonce both being fresh per record, so no two records
                   share a derived key at all.
    integrity      encrypt-then-MAC: HMAC-SHA256(mac_key, version || key_id ||
                   salt || nonce || ciphertext || aad), compared with
                   `hmac.compare_digest`. The AAD binds the ciphertext to its
                   own row - user id, provider, family id - so a row swapped
                   for another row fails to open rather than opening as
                   somebody else's token.

That is authenticated encryption in the encrypt-then-MAC composition, and the
threat it actually defeats is the realistic one: a Supabase database dump, a
leaked read-only Postgres role, a backup on somebody's laptop, an over-broad
PostgREST policy. None of those yield a usable refresh token, because
`TOKEN_ENCRYPTION_KEY` is never sent to Supabase and exists only in the
application's environment.

WHAT DOES *NOT* PROTECT IT - PLAINLY
------------------------------------
  * This is not AES and not AES-GCM. There is no AES in the Python standard
    library. There is no hardware acceleration here, no constant-time
    implementation reviewed by anyone, and no formal analysis of this
    particular assembly of primitives. HMAC-SHA256-CTR plus HMAC-SHA256 is a
    conservative and conventional composition, but "conventional composition
    of good primitives" is a weaker claim than "AES-GCM from libsodium", and
    anyone who needs the stronger claim should reach for `cryptography` and
    accept the dependency.
  * It does not protect against a compromised application server. The master
    key is in that process's environment; anything that can read the process
    can decrypt every row. Encryption at rest is a control against *storage*
    disclosure, and nothing else.
  * It does not protect against a stolen `SUPABASE_SERVICE_KEY` combined with
    a stolen `TOKEN_ENCRYPTION_KEY`. They are separate secrets held in the same
    place, so in practice they leak together; the separation buys you the case
    where only the database leaks, which is the common case.
  * Rotating `TOKEN_ENCRYPTION_KEY` does not re-encrypt anything. Old rows stay
    sealed under the old key and only open while `TOKEN_ENCRYPTION_KEY_OLD` is
    still set. `deploy/README.md` has the procedure.
  * `FileTokenStore` does not encrypt at all. See its docstring; that is a
    deliberate compatibility decision, not an oversight.

The alternative considered was Postgres-side `pgcrypto`, and it was rejected
on a specific ground: everything here reaches Postgres through PostgREST with
the service key, so if the key that decrypts lived *in the database*, the
credential that reads the rows would also be the credential that decrypts them
and the encryption would buy nothing against the leak it is meant to survive.
Sealing in the application keeps the two apart. `deploy/schema.sql` stores the
sealed blob as `text` for that reason and does not enable pgcrypto.

NEVER RETURN A DECRYPTED TOKEN TO AN HTTP PATH
----------------------------------------------
`StoredConnection` carries the *sealed* blob and nothing else secret. The only
way to plaintext is `TokenStore.reveal_refresh_token`, which is called from
exactly one place in this codebase - `oauth.refresh` - and is named to be
greppable. Anything rendering a response calls `to_public()`, which cannot
return a secret because it does not have one to return. `dataclasses.asdict`
and `repr` are both redacted, so an accidental `json.dumps(connection)` leaks
a fingerprint at worst. A test asserts all of that, and asserts `api.py` does
not import this module.
"""

from __future__ import annotations

import abc
import base64
import dataclasses
import hashlib
import hmac
import json
import os
import pathlib
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

from .oauth import token_fingerprint

SEAL_VERSION = "fe1"
SCRYPT_N = 2 ** 14
SCRYPT_R = 8
SCRYPT_P = 1
SALT_BYTES = 16
NONCE_BYTES = 16
# scrypt at n=2**14 needs 16 MiB and about 50 ms. Both are on purpose: it makes
# a stolen ciphertext expensive to attack offline, and a refresh happens once an
# hour per connection, so the cost is invisible where it lands.
SCRYPT_MAXMEM = 64 * 1024 * 1024

TOKEN_DIR = pathlib.Path.home() / ".fantasy-edge"


class TokenStoreError(RuntimeError):
    """Storage or sealing went wrong."""


class DecryptionFailed(TokenStoreError):
    """The blob did not authenticate: wrong key, wrong row, or tampering."""


# --------------------------------------------------------------------------
# sealing


def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64u(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def master_key(env: dict | None = None, var: str = "TOKEN_ENCRYPTION_KEY") -> bytes:
    """Read the master key from the environment. Never from a file in the repo.

    Accepts base64url or raw text and requires at least 32 bytes of it. The
    length check is the only thing standing between a deployment and someone
    setting this to "changeme" in a hurry, so it refuses rather than warns.
    """
    env = os.environ if env is None else env
    raw = env.get(var, "")
    if not raw:
        raise TokenStoreError(f"{var} is not set")
    try:
        decoded = _unb64u(raw)
    except Exception:
        decoded = b""
    key = decoded if len(decoded) >= 32 else raw.encode("utf-8")
    if len(key) < 32:
        raise TokenStoreError(f"{var} must be at least 32 bytes of key material")
    return key


def key_id(key: bytes) -> str:
    """A short public name for a key, so a row says which key sealed it.

    Rotation needs to know, per row, whether the current key or the previous
    one applies. Trying both works but doubles the scrypt cost on every read and
    makes a genuine tamper look like a key-generation mismatch.
    """
    return hashlib.sha256(b"fantasy-edge/key-id\x00" + key).hexdigest()[:12]


def _derive(key: bytes, salt: bytes) -> tuple[bytes, bytes]:
    dk = hashlib.scrypt(key, salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P,
                        dklen=64, maxmem=SCRYPT_MAXMEM)
    return dk[:32], dk[32:]


def _keystream(enc_key: bytes, nonce: bytes, length: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < length:
        block = hmac.new(enc_key, nonce + counter.to_bytes(4, "big"), hashlib.sha256)
        out.extend(block.digest())
        counter += 1
    return bytes(out[:length])


def seal(plaintext: str, key: bytes, aad: str = "") -> str:
    """Encrypt-then-MAC a secret into one opaque, storable string."""
    salt = secrets.token_bytes(SALT_BYTES)
    nonce = secrets.token_bytes(NONCE_BYTES)
    enc_key, mac_key = _derive(key, salt)
    raw = plaintext.encode("utf-8")
    ct = bytes(a ^ b for a, b in zip(raw, _keystream(enc_key, nonce, len(raw))))
    kid = key_id(key)
    tag = hmac.new(mac_key, _mac_input(kid, salt, nonce, ct, aad), hashlib.sha256).digest()
    return ".".join([SEAL_VERSION, kid, _b64u(salt), _b64u(nonce), _b64u(ct), _b64u(tag)])


def unseal(blob: str, key: bytes, aad: str = "", *, fallback: bytes | None = None) -> str:
    """Open a sealed secret, verifying the tag before touching the ciphertext.

    `fallback` is the previous master key during a rotation window. Which key a
    row used is read from its key id, so no row pays for two scrypt runs.
    """
    parts = blob.split(".")
    if len(parts) != 6 or parts[0] != SEAL_VERSION:
        raise DecryptionFailed("sealed value is not a recognised fe1 blob")
    _, kid, b_salt, b_nonce, b_ct, b_tag = parts
    chosen = key
    if kid != key_id(key):
        if fallback is not None and kid == key_id(fallback):
            chosen = fallback
        else:
            raise DecryptionFailed(
                f"no available key matches key id {kid}; "
                "set TOKEN_ENCRYPTION_KEY_OLD if you are mid-rotation")
    salt, nonce, ct, tag = _unb64u(b_salt), _unb64u(b_nonce), _unb64u(b_ct), _unb64u(b_tag)
    enc_key, mac_key = _derive(chosen, salt)
    expect = hmac.new(mac_key, _mac_input(kid, salt, nonce, ct, aad), hashlib.sha256).digest()
    # compare_digest, not ==. A byte-at-a-time comparison of a MAC is a forgery
    # oracle for anyone who can time it, and this one is reachable over HTTP.
    if not hmac.compare_digest(expect, tag):
        raise DecryptionFailed("sealed value failed authentication")
    return bytes(a ^ b for a, b in zip(ct, _keystream(enc_key, nonce, len(ct)))).decode("utf-8")


def _mac_input(kid: str, salt: bytes, nonce: bytes, ct: bytes, aad: str) -> bytes:
    return b"|".join([SEAL_VERSION.encode(), kid.encode(), salt, nonce, ct,
                      aad.encode("utf-8")])


# --------------------------------------------------------------------------
# the record


@dataclasses.dataclass
class StoredConnection:
    """One user's link to one provider. Holds no plaintext secret, ever."""

    user_id: str
    provider: str
    family_id: str
    refresh_fingerprint: str
    sealed_refresh: str = dataclasses.field(default="", repr=False)
    scopes: str = ""
    redirect_uri: str = ""
    revoked: bool = False
    revoked_reason: str = ""
    created_at: float = 0.0
    rotated_at: float = 0.0
    disconnected_at: float = 0.0

    def __repr__(self) -> str:
        return (f"StoredConnection(user_id={self.user_id!r}, provider={self.provider!r}, "
                f"family_id={self.family_id!r}, revoked={self.revoked!r}, "
                f"sealed_refresh=<redacted>)")

    def to_public(self) -> dict:
        """The shape an HTTP response may carry. No secret is reachable from it.

        Note what is absent: `sealed_refresh`. It is ciphertext and leaking it
        is not immediately fatal, but publishing ciphertext hands an attacker
        an offline target to grind scrypt against, and there is no reason a
        client needs it.
        """
        return {
            "provider": self.provider,
            "scopes": self.scopes,
            "connected": not self.revoked and not self.disconnected_at,
            "revoked": self.revoked,
            "revoked_reason": self.revoked_reason,
            "created_at": self.created_at,
            "rotated_at": self.rotated_at,
        }


def _redacting_dict_factory(pairs):
    """Used by `dataclasses.asdict` so a serialised connection cannot leak."""
    return {k: ("<redacted>" if k == "sealed_refresh" else v) for k, v in pairs}


def asdict_safe(conn: StoredConnection) -> dict:
    return dataclasses.asdict(conn, dict_factory=_redacting_dict_factory)


# --------------------------------------------------------------------------
# the interface


class TokenStore(abc.ABC):
    """What `oauth.refresh` needs from storage, and nothing more."""

    @abc.abstractmethod
    def load(self, user_id: str, provider: str) -> StoredConnection | None: ...

    @abc.abstractmethod
    def link(self, user_id: str, provider: str, refresh_token: str, *,
             scopes: str = "", redirect_uri: str = "",
             now: float | None = None) -> StoredConnection:
        """Record a brand new connection, starting a new rotation family."""

    @abc.abstractmethod
    def reveal_refresh_token(self, conn: StoredConnection) -> str:
        """The single door to plaintext. Called only by `oauth.refresh`."""

    @abc.abstractmethod
    def rotate(self, conn: StoredConnection, new_refresh_token: str, *,
               spent_fingerprint: str, now: float | None = None) -> StoredConnection: ...

    @abc.abstractmethod
    def is_spent(self, family_id: str, fingerprint: str) -> bool: ...

    @abc.abstractmethod
    def revoke_family(self, family_id: str, reason: str) -> None: ...

    @abc.abstractmethod
    def mark_disconnected(self, conn: StoredConnection) -> None:
        """The provider said `invalid_grant`. Not a fault; needs a re-link."""

    @abc.abstractmethod
    def unlink(self, user_id: str, provider: str) -> None: ...


# --------------------------------------------------------------------------
# backend one: the file the single-user CLI already uses


class FileTokenStore(TokenStore):
    """`~/.fantasy-edge/{provider}.json`, mode 600. What the CLI has today.

    The refresh token is stored in plaintext here and that is a decision, not a
    gap. `providers/yahoo.py` reads this exact file and this exact key layout,
    and the brief is that the single-user path keeps working exactly as well as
    it does now; sealing the file would either break that provider or require
    shipping the decryption key next to the ciphertext, which is not
    encryption, it is filing.

    So the protection on this file is the same as it was: it is in the user's
    home directory, mode 600, on a machine only they log into, and outside the
    working tree so no `git add .` can commit it. That is a reasonable posture
    for a personal tool and an unreasonable one for a server, which is why the
    server uses the other backend.

    Rotation state (`family_id`, the spent list) is added alongside the existing
    keys. `YahooAuth` ignores keys it does not know, so old files load and new
    files stay readable by it.
    """

    def __init__(self, base: pathlib.Path | None = None) -> None:
        self.base = pathlib.Path(base) if base else TOKEN_DIR

    def path(self, provider: str) -> pathlib.Path:
        return self.base / f"{provider}.json"

    def _read(self, provider: str) -> dict:
        p = self.path(provider)
        if not p.exists():
            return {}
        try:
            return json.loads(p.read_text())
        except ValueError:
            raise TokenStoreError(f"{p} is not valid JSON") from None

    def _write(self, provider: str, doc: dict) -> None:
        p = self.path(provider)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(doc, indent=2))
        p.chmod(0o600)

    def load(self, user_id: str, provider: str) -> StoredConnection | None:
        doc = self._read(provider)
        refresh = doc.get("refresh_token", "")
        if not refresh:
            return None
        return StoredConnection(
            user_id=user_id, provider=provider,
            # A file written before rotation existed has no family. Naming it
            # after the file keeps the id stable across loads, which matters
            # because the spent list is keyed on it.
            family_id=doc.get("family_id") or f"file:{provider}",
            refresh_fingerprint=doc.get("refresh_fingerprint") or token_fingerprint(refresh),
            sealed_refresh=refresh,
            scopes=doc.get("scopes", ""),
            redirect_uri=doc.get("redirect_uri", ""),
            revoked=bool(doc.get("revoked", False)),
            revoked_reason=doc.get("revoked_reason", ""),
            created_at=float(doc.get("created_at", 0) or 0),
            rotated_at=float(doc.get("rotated_at", 0) or 0),
            disconnected_at=float(doc.get("disconnected_at", 0) or 0),
        )

    def link(self, user_id: str, provider: str, refresh_token: str, *,
             scopes: str = "", redirect_uri: str = "",
             now: float | None = None) -> StoredConnection:
        now = time.time() if now is None else now
        doc = self._read(provider)
        doc.update({
            "refresh_token": refresh_token,
            "refresh_fingerprint": token_fingerprint(refresh_token),
            "family_id": str(uuid.uuid4()),
            "scopes": scopes, "redirect_uri": redirect_uri,
            "created_at": now, "rotated_at": now,
            "revoked": False, "revoked_reason": "", "disconnected_at": 0.0,
            "spent": [],
        })
        self._write(provider, doc)
        return self.load(user_id, provider)  # type: ignore[return-value]

    def reveal_refresh_token(self, conn: StoredConnection) -> str:
        return conn.sealed_refresh

    def rotate(self, conn: StoredConnection, new_refresh_token: str, *,
               spent_fingerprint: str, now: float | None = None) -> StoredConnection:
        now = time.time() if now is None else now
        doc = self._read(conn.provider)
        spent = list(doc.get("spent", []))
        if spent_fingerprint not in spent:
            spent.append(spent_fingerprint)
        doc.update({
            "refresh_token": new_refresh_token,
            "refresh_fingerprint": token_fingerprint(new_refresh_token),
            "family_id": conn.family_id, "rotated_at": now, "spent": spent,
        })
        self._write(conn.provider, doc)
        return self.load(conn.user_id, conn.provider)  # type: ignore[return-value]

    def is_spent(self, family_id: str, fingerprint: str) -> bool:
        provider = family_id.split(":", 1)[1] if family_id.startswith("file:") else ""
        doc = self._read(provider) if provider else {}
        if not doc:
            # A uuid family id gives no filename, so fall back to scanning the
            # directory. There are at most a handful of provider files.
            for p in sorted(self.base.glob("*.json")) if self.base.exists() else []:
                try:
                    candidate = json.loads(p.read_text())
                except ValueError:
                    continue
                if candidate.get("family_id") == family_id:
                    doc = candidate
                    break
        return fingerprint in set(doc.get("spent", []))

    def revoke_family(self, family_id: str, reason: str) -> None:
        for p in sorted(self.base.glob("*.json")) if self.base.exists() else []:
            try:
                doc = json.loads(p.read_text())
            except ValueError:
                continue
            if doc.get("family_id") != family_id and not family_id.startswith("file:"):
                continue
            if family_id.startswith("file:") and p.stem != family_id.split(":", 1)[1]:
                continue
            doc["revoked"] = True
            doc["revoked_reason"] = reason
            # The token itself goes. A revoked family must not leave a working
            # credential on disk for the next process that ignores the flag.
            doc["refresh_token"] = ""
            self._write(p.stem, doc)

    def mark_disconnected(self, conn: StoredConnection) -> None:
        doc = self._read(conn.provider)
        if doc:
            doc["disconnected_at"] = time.time()
            self._write(conn.provider, doc)

    def unlink(self, user_id: str, provider: str) -> None:
        self.path(provider).unlink(missing_ok=True)


# --------------------------------------------------------------------------
# backend two: Supabase over PostgREST


class PostgREST:
    """A Supabase client that is `urllib` and forty lines.

    Supabase publishes PostgREST over HTTPS, so a database client here is an
    HTTP client, which the standard library already has. That is what makes the
    zero-dependency rule survive the move to a hosted database - no psycopg, no
    supabase-py, no wheel that needs a compiler in the image.

    The service key bypasses row-level security by design, so it never leaves
    the server and never appears in a URL: it goes in `apikey` and
    `Authorization` headers, which is also where a proxy is most likely to
    redact it.
    """

    def __init__(self, url: str | None = None, service_key: str | None = None,
                 env: dict | None = None, timeout: int = 15) -> None:
        env = os.environ if env is None else env
        self.url = (url or env.get("SUPABASE_URL", "")).rstrip("/")
        self.service_key = service_key or env.get("SUPABASE_SERVICE_KEY", "")
        self.timeout = timeout
        if not self.url or not self.service_key:
            raise TokenStoreError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")

    def request(self, method: str, table: str, *, params: dict | None = None,
                body=None, prefer: str = "") -> list:
        url = f"{self.url}/rest/v1/{table}"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        headers = {
            "apikey": self.service_key,
            "Authorization": f"Bearer {self.service_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if prefer:
            headers["Prefer"] = prefer
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            with exc:
                detail = exc.read().decode("utf-8", "replace")[:200]
            raise TokenStoreError(f"postgrest {method} {table} -> {exc.code}: {detail}") from None
        except urllib.error.URLError as exc:
            raise TokenStoreError(f"supabase unreachable: {exc.reason}") from None
        if not raw.strip():
            return []
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, list) else [parsed]


CONNECTIONS = "provider_connections"
ROTATIONS = "refresh_rotations"
TRANSACTIONS = "oauth_transactions"


class SupabaseTokenStore(TokenStore):
    """Connections in Postgres, refresh tokens sealed before they get there.

    The AAD binds each sealed blob to `user_id|provider|family_id`. Moving a row
    to another user - the obvious attack once an attacker has write access but
    not the key - produces a blob that fails authentication instead of one that
    silently grants somebody else's Yahoo account.
    """

    def __init__(self, client: PostgREST | None = None, key: bytes | None = None,
                 old_key: bytes | None = None, env: dict | None = None) -> None:
        env = os.environ if env is None else env
        self.db = client or PostgREST(env=env)
        self.key = key if key is not None else master_key(env)
        if old_key is not None:
            self.old_key = old_key
        else:
            self.old_key = master_key(env, "TOKEN_ENCRYPTION_KEY_OLD") \
                if env.get("TOKEN_ENCRYPTION_KEY_OLD") else None

    @staticmethod
    def _aad(user_id: str, provider: str, family_id: str) -> str:
        return f"{user_id}|{provider}|{family_id}"

    @staticmethod
    def _row_to_conn(row: dict) -> StoredConnection:
        return StoredConnection(
            user_id=str(row["user_id"]), provider=str(row["provider"]),
            family_id=str(row["family_id"]),
            refresh_fingerprint=str(row.get("refresh_fingerprint") or ""),
            sealed_refresh=str(row.get("refresh_sealed") or ""),
            scopes=str(row.get("scopes") or ""),
            redirect_uri=str(row.get("redirect_uri") or ""),
            revoked=bool(row.get("revoked")),
            revoked_reason=str(row.get("revoked_reason") or ""),
            created_at=float(row.get("created_at_epoch") or 0),
            rotated_at=float(row.get("rotated_at_epoch") or 0),
            disconnected_at=float(row.get("disconnected_at_epoch") or 0),
        )

    def load(self, user_id: str, provider: str) -> StoredConnection | None:
        rows = self.db.request("GET", CONNECTIONS, params={
            "user_id": f"eq.{user_id}", "provider": f"eq.{provider}",
            "select": "*", "limit": "1"})
        return self._row_to_conn(rows[0]) if rows else None

    def link(self, user_id: str, provider: str, refresh_token: str, *,
             scopes: str = "", redirect_uri: str = "",
             now: float | None = None) -> StoredConnection:
        now = time.time() if now is None else now
        family_id = str(uuid.uuid4())
        sealed = seal(refresh_token, self.key, self._aad(user_id, provider, family_id))
        row = {
            "user_id": user_id, "provider": provider, "family_id": family_id,
            "refresh_sealed": sealed,
            "refresh_fingerprint": token_fingerprint(refresh_token),
            "scopes": scopes, "redirect_uri": redirect_uri,
            "revoked": False, "revoked_reason": "",
            "created_at_epoch": now, "rotated_at_epoch": now, "disconnected_at_epoch": 0,
            "key_id": key_id(self.key),
        }
        # merge-duplicates upserts on the (user_id, provider) unique constraint:
        # re-linking an existing connection replaces it and starts a new family
        # rather than colliding.
        out = self.db.request("POST", CONNECTIONS, body=row,
                              prefer="resolution=merge-duplicates,return=representation")
        return self._row_to_conn(out[0]) if out else self._row_to_conn(row)

    def reveal_refresh_token(self, conn: StoredConnection) -> str:
        if conn.revoked:
            raise TokenStoreError("refusing to unseal a revoked connection")
        return unseal(conn.sealed_refresh, self.key,
                      self._aad(conn.user_id, conn.provider, conn.family_id),
                      fallback=self.old_key)

    def rotate(self, conn: StoredConnection, new_refresh_token: str, *,
               spent_fingerprint: str, now: float | None = None) -> StoredConnection:
        now = time.time() if now is None else now
        # The retired fingerprint is recorded *before* the new token is stored.
        # If the process dies between the two writes, the worst case is a
        # connection that has to be re-linked; the other order would leave a
        # retired token that reuse detection cannot recognise, which is the
        # failure this whole mechanism exists to prevent.
        self.db.request("POST", ROTATIONS, body={
            "family_id": conn.family_id, "fingerprint": spent_fingerprint,
            "retired_at_epoch": now})
        sealed = seal(new_refresh_token, self.key,
                      self._aad(conn.user_id, conn.provider, conn.family_id))
        out = self.db.request("PATCH", CONNECTIONS, params={
            "user_id": f"eq.{conn.user_id}", "provider": f"eq.{conn.provider}"},
            body={"refresh_sealed": sealed,
                  "refresh_fingerprint": token_fingerprint(new_refresh_token),
                  "rotated_at_epoch": now, "key_id": key_id(self.key)},
            prefer="return=representation")
        return self._row_to_conn(out[0]) if out else conn

    def is_spent(self, family_id: str, fingerprint: str) -> bool:
        rows = self.db.request("GET", ROTATIONS, params={
            "family_id": f"eq.{family_id}", "fingerprint": f"eq.{fingerprint}",
            "select": "fingerprint", "limit": "1"})
        return bool(rows)

    def revoke_family(self, family_id: str, reason: str) -> None:
        # The sealed blob is cleared, not just flagged. A revoked family that
        # still holds recoverable ciphertext is one careless code path away from
        # being usable again, and there is nothing left to do with it.
        self.db.request("PATCH", CONNECTIONS,
                        params={"family_id": f"eq.{family_id}"},
                        body={"revoked": True, "revoked_reason": reason,
                              "refresh_sealed": "", "refresh_fingerprint": ""})

    def mark_disconnected(self, conn: StoredConnection) -> None:
        self.db.request("PATCH", CONNECTIONS, params={
            "user_id": f"eq.{conn.user_id}", "provider": f"eq.{conn.provider}"},
            body={"disconnected_at_epoch": time.time()})

    def unlink(self, user_id: str, provider: str) -> None:
        self.db.request("DELETE", CONNECTIONS, params={
            "user_id": f"eq.{user_id}", "provider": f"eq.{provider}"})


class SupabaseTransactionStore:
    """In-flight `state` in Postgres, so two server processes share one flow.

    `MemoryTransactionStore` is correct only while there is exactly one process.
    Put a second pod behind the same hostname and half the callbacks land on the
    instance that did not start the transaction, which looks precisely like a
    CSRF failure and would very reasonably get "fixed" by weakening the state
    check. So the shared deployment gets a shared store.

    The code verifier is sealed with the same construction as a refresh token.
    It is short-lived, but for its ten minutes it is the thing standing between
    an intercepted code and a token.
    """

    def __init__(self, client: PostgREST | None = None, key: bytes | None = None,
                 env: dict | None = None) -> None:
        env = os.environ if env is None else env
        self.db = client or PostgREST(env=env)
        self.key = key if key is not None else master_key(env)

    def put(self, tx) -> None:
        self.db.request("POST", TRANSACTIONS, body={
            "state": tx.state,
            "code_verifier_sealed": seal(tx.verifier, self.key, tx.state),
            "redirect_uri": tx.redirect_uri, "provider": tx.provider,
            "session_id": tx.session_id,
            "created_at_epoch": tx.created_at, "expires_at_epoch": tx.expires_at,
        })

    def take(self, state: str):
        from .oauth import Transaction

        # DELETE ... with `return=representation` is the single-use enforcement.
        # A SELECT followed by a DELETE has a window in which two concurrent
        # callbacks both read the same row and both succeed; deleting first
        # means the database decides who gets it, exactly once.
        rows = self.db.request("DELETE", TRANSACTIONS,
                               params={"state": f"eq.{state}"},
                               prefer="return=representation")
        if not rows:
            return None
        row = rows[0]
        try:
            verifier = unseal(str(row.get("code_verifier_sealed") or ""), self.key, state)
        except DecryptionFailed:
            return None
        return Transaction(
            state=str(row["state"]), verifier=verifier,
            redirect_uri=str(row.get("redirect_uri") or ""),
            provider=str(row.get("provider") or ""),
            session_id=str(row.get("session_id") or ""),
            created_at=float(row.get("created_at_epoch") or 0),
            expires_at=float(row.get("expires_at_epoch") or 0),
        )

    def purge_expired(self, now: float | None = None) -> int:
        now = time.time() if now is None else now
        rows = self.db.request("DELETE", TRANSACTIONS,
                               params={"expires_at_epoch": f"lt.{now}"},
                               prefer="return=representation")
        return len(rows)


def store_from_env(env: dict | None = None) -> TokenStore:
    """Supabase if it is configured, the home-directory file otherwise.

    This is what keeps the two worlds from needing two code paths: the CLI has
    no `SUPABASE_URL` and gets the file it has always used; the deployment sets
    the variables and gets the sealed database. Nothing else changes.
    """
    env = os.environ if env is None else env
    if env.get("SUPABASE_URL") and env.get("SUPABASE_SERVICE_KEY"):
        return SupabaseTokenStore(env=env)
    return FileTokenStore()


def save_cli_tokens(tokens, provider: str = "yahoo", store: FileTokenStore | None = None,
                    redirect_uri: str = "") -> pathlib.Path:
    """Write a fresh `TokenSet` in the layout `providers/yahoo.py` already reads.

    The loopback flow in `oauth.py` is provider-agnostic and knows nothing about
    that file. This is the one adapter between them, and it keeps the existing
    keys - `access_token`, `refresh_token`, `expires_at` - exactly where
    `YahooAuth` looks for them, so a token obtained the new way is
    indistinguishable from one obtained the old way.
    """
    store = store or FileTokenStore()
    store.link("local", provider, tokens.refresh_token,
               scopes=tokens.scope, redirect_uri=redirect_uri)
    doc = store._read(provider)
    doc["access_token"] = tokens.access_token
    doc["expires_at"] = tokens.expires_at
    doc["token_type"] = tokens.token_type
    store._write(provider, doc)
    return store.path(provider)
