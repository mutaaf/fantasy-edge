"""OAuth flow, token sealing and Supabase storage, all against local stubs.

Yahoo is not reachable from here and its credentials are not ours to borrow, so
every provider interaction in this file runs against a `http.server` standing in
for one. That is not a compromise: the controls under test - PKCE binding, state
single-use, redirect allowlisting, refresh rotation, reuse detection - are ours,
not Yahoo's, and a fake provider that checks the verifier the way RFC 7636 says
to is a stricter counterparty than the real one.

What this therefore does NOT prove is that Yahoo accepts a PKCE authorize
request or rotates its refresh tokens. See the report in README.
"""

from __future__ import annotations

import base64
import hashlib
import http.server
import json
import pathlib
import os
import secrets
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request

from fantasyedge import oauth, tokens

REPO = pathlib.Path(__file__).resolve().parent.parent


def b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


# --------------------------------------------------------------------------
# a provider that behaves like an authorization server


class FakeProviderHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    @property
    def state(self):
        return self.server.state  # type: ignore[attr-defined]

    def _json(self, status: int, payload: dict) -> None:
        raw = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        self.state["seen_urls"].append(self.path)
        if parsed.path != "/authorize":
            self.send_error(404)
            return
        q = {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()}
        self.state["authorize_params"] = q
        code = "code-" + secrets.token_hex(8)
        self.state["codes"][code] = {
            "challenge": q.get("code_challenge", ""),
            "method": q.get("code_challenge_method", ""),
            "redirect_uri": q.get("redirect_uri", ""),
        }
        target = f"{q['redirect_uri']}?code={code}&state={urllib.parse.quote(q.get('state',''))}"
        self.send_response(302)
        self.send_header("Location", target)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_POST(self):  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        self.state["seen_urls"].append(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        form = {k: v[0] for k, v in
                urllib.parse.parse_qs(self.rfile.read(length).decode()).items()}
        self.state["last_form"] = form
        if parsed.path != "/token":
            self.send_error(404)
            return
        grant = form.get("grant_type")
        if grant == "authorization_code":
            self._authorization_code(form)
        elif grant == "refresh_token":
            self._refresh(form)
        else:
            self._json(400, {"error": "unsupported_grant_type"})

    def _authorization_code(self, form: dict) -> None:
        record = self.state["codes"].pop(form.get("code", ""), None)
        if record is None:
            self._json(400, {"error": "invalid_grant"})
            return
        if record["method"] != "S256":
            self._json(400, {"error": "invalid_request"})
            return
        verifier = form.get("code_verifier", "")
        expect = b64u(hashlib.sha256(verifier.encode()).digest())
        if expect != record["challenge"]:
            self.state["pkce_failures"] += 1
            self._json(400, {"error": "invalid_grant"})
            return
        if form.get("redirect_uri") != record["redirect_uri"]:
            self._json(400, {"error": "invalid_grant"})
            return
        self.state["pkce_verified"] += 1
        self._issue()

    def _refresh(self, form: dict) -> None:
        presented = form.get("refresh_token", "")
        if self.state.get("always_invalid_grant"):
            self._json(400, {"error": "invalid_grant"})
            return
        if presented in self.state["spent"] or presented != self.state["current_refresh"]:
            self._json(400, {"error": "invalid_grant"})
            return
        self.state["spent"].add(presented)
        self._issue()

    def _issue(self) -> None:
        access = "ACCESS-" + secrets.token_hex(6)
        refresh = "REFRESH-" + secrets.token_hex(6)
        self.state["current_refresh"] = refresh
        self.state["issued"].append((access, refresh))
        self._json(200, {"access_token": access, "refresh_token": refresh,
                         "expires_in": 3600, "token_type": "bearer",
                         "scope": "fspt-r"})

    def log_message(self, fmt, *args):
        pass


class FakeProvider:
    def __init__(self) -> None:
        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), FakeProviderHandler)
        self.httpd.state = {  # type: ignore[attr-defined]
            "codes": {}, "issued": [], "spent": set(), "current_refresh": "",
            "seen_urls": [], "authorize_params": {}, "last_form": {},
            "pkce_verified": 0, "pkce_failures": 0,
        }
        self.state = self.httpd.state  # type: ignore[attr-defined]
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever,
                                       kwargs={"poll_interval": 0.02}, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def config(self) -> oauth.ProviderConfig:
        return oauth.ProviderConfig(
            name="fake", authorize_url=f"{self.base}/authorize",
            token_url=f"{self.base}/token", scope="fspt-r",
            client_id_env="FAKE_ID", client_secret_env="FAKE_SECRET")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """The browser leg has to stop at the 302 so the test can read the code."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def follow_authorize(url: str) -> dict:
    opener = urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(url, timeout=5) as resp:
            location = resp.headers.get("Location", "")
    except urllib.error.HTTPError as exc:
        with exc:
            location = exc.headers.get("Location", "")
    return {k: v[0] for k, v in
            urllib.parse.parse_qs(urllib.parse.urlparse(location).query).items()}


CREDS = oauth.Credentials("fake-client-id", "fake-client-secret")
ALLOWED = "https://fantasy.digitalcraftai.com/oauth/callback"


# --------------------------------------------------------------------------
# PKCE


class TestPkce(unittest.TestCase):
    def test_verifier_is_within_rfc_bounds_and_unreserved(self):
        for _ in range(20):
            v = oauth.new_verifier()
            self.assertTrue(43 <= len(v) <= 128)
            self.assertTrue(all(c.isalnum() or c in "-._~" for c in v), v)

    def test_verifiers_are_not_repeated(self):
        self.assertEqual(50, len({oauth.new_verifier() for _ in range(50)}))

    def test_challenge_is_s256_of_the_verifier(self):
        v = oauth.new_verifier()
        self.assertEqual(b64u(hashlib.sha256(v.encode()).digest()), oauth.challenge_for(v))
        self.assertNotIn("=", oauth.challenge_for(v))

    def test_method_is_only_ever_s256(self):
        self.assertEqual("S256", oauth.CHALLENGE_METHOD)
        source = (REPO / "fantasyedge" / "oauth.py").read_text()
        # A downgrade to "plain" is a one-word change, so the absence of the
        # word is the thing worth asserting - a reviewer will not notice it
        # reappearing in a query-string literal.
        self.assertNotIn('"plain"', source)
        self.assertNotIn("'plain'", source)

    def test_out_of_range_verifier_is_refused(self):
        with self.assertRaises(oauth.OAuthError):
            oauth.challenge_for("tooshort")


# --------------------------------------------------------------------------
# leg one


class TestAuthorizeUrl(unittest.TestCase):
    def setUp(self):
        self.store = oauth.MemoryTransactionStore()

    def test_url_carries_state_and_s256_challenge_and_no_secret(self):
        cfg = oauth.PROVIDERS["yahoo"]
        auth = oauth.begin(cfg, CREDS, redirect_uri=ALLOWED, allowlist=[ALLOWED],
                           session_id="sess", store=self.store)
        q = {k: v[0] for k, v in
             urllib.parse.parse_qs(urllib.parse.urlparse(auth.url).query).items()}
        self.assertEqual("S256", q["code_challenge_method"])
        self.assertEqual(q["state"], auth.state)
        self.assertEqual("fspt-r", q["scope"])
        self.assertEqual(oauth.challenge_for(auth.transaction.verifier), q["code_challenge"])
        # The verifier and the client secret must never reach the address bar.
        self.assertNotIn(auth.transaction.verifier, auth.url)
        self.assertNotIn(CREDS.client_secret, auth.url)

    def test_read_only_scope(self):
        # fspt-w would be asking for roster-write permission this codebase has
        # no code to use. Requesting it is a consent-screen lie.
        self.assertEqual("fspt-r", oauth.PROVIDERS["yahoo"].scope)

    def test_yahoo_endpoints_match_the_working_provider(self):
        from fantasyedge.providers import yahoo as y
        self.assertEqual(y.AUTH, oauth.PROVIDERS["yahoo"].authorize_url)
        self.assertEqual(y.TOKEN, oauth.PROVIDERS["yahoo"].token_url)

    def test_the_provider_asks_for_the_same_scope(self):
        # It did not, and the two drifted in the one direction that cannot be
        # seen from here: the token refreshed forever and every Fantasy call
        # returned 401 additional_authorization_required, because the consent
        # screen was never asked for Fantasy read.
        import pathlib
        import urllib.parse
        from fantasyedge.providers import yahoo as y
        auth = y.YahooAuth(client_id="id", client_secret="secret",
                           token_path=pathlib.Path("/nonexistent/yahoo.json"),
                           redirect_uri=ALLOWED)
        asked = urllib.parse.parse_qs(
            urllib.parse.urlparse(auth.authorize_url()).query).get("scope", [""])[0]
        self.assertEqual(oauth.PROVIDERS["yahoo"].scope, asked)


class TestRedirectAllowlist(unittest.TestCase):
    def test_exact_match_only(self):
        self.assertEqual(ALLOWED, oauth.check_redirect(ALLOWED, [ALLOWED]))

    def test_near_misses_are_refused(self):
        for bad in [
            ALLOWED + "/",                                    # trailing slash
            ALLOWED + "?next=https://evil.example",           # appended query
            "https://fantasy.digitalcraftai.com.evil.example/oauth/callback",
            "https://fantasy.digitalcraftai.com:8443/oauth/callback",
            "http://fantasy.digitalcraftai.com/oauth/callback",  # scheme downgrade
            "https://fantasy.digitalcraftai.com/oauth/callback/../x",
        ]:
            with self.assertRaises(oauth.RedirectNotAllowed, msg=bad):
                oauth.check_redirect(bad, [ALLOWED])

    def test_empty_allowlist_passes_nothing(self):
        with self.assertRaises(oauth.RedirectNotAllowed):
            oauth.check_redirect(ALLOWED, [])

    def test_begin_refuses_before_minting_anything(self):
        store = oauth.MemoryTransactionStore()
        with self.assertRaises(oauth.RedirectNotAllowed):
            oauth.begin(oauth.PROVIDERS["yahoo"], CREDS,
                        redirect_uri="https://evil.example/cb", allowlist=[ALLOWED],
                        session_id="s", store=store)
        self.assertEqual({}, store._rows)

    def test_allowlist_from_env(self):
        env = {"OAUTH_REDIRECT_ALLOWLIST": f" {ALLOWED} , https://x.example/cb "}
        self.assertEqual((ALLOWED, "https://x.example/cb"), oauth.allowlist_from_env(env))
        self.assertEqual((), oauth.allowlist_from_env({}))


# --------------------------------------------------------------------------
# the whole flow against the fake provider


class TestFullFlow(unittest.TestCase):
    def test_authorize_exchange_refresh(self):
        with FakeProvider() as fp:
            cfg = fp.config()
            store = oauth.MemoryTransactionStore()
            auth = oauth.begin(cfg, CREDS, redirect_uri=ALLOWED, allowlist=[ALLOWED],
                               session_id="sess", store=store)
            cb = follow_authorize(auth.url)
            self.assertEqual(auth.state, cb["state"])

            tokset, tx = oauth.finish(cfg, CREDS, code=cb["code"], state=cb["state"],
                                      session_id="sess", store=store)
            self.assertEqual(1, fp.state["pkce_verified"])
            self.assertEqual(0, fp.state["pkce_failures"])
            self.assertTrue(tokset.access_token.startswith("ACCESS-"))
            self.assertTrue(tokset.refresh_token.startswith("REFRESH-"))
            self.assertEqual(ALLOWED, tx.redirect_uri)
            # The provider was given the verifier, not the challenge.
            self.assertEqual(tx.verifier, fp.state["last_form"]["code_verifier"])

    def test_a_wrong_verifier_is_rejected_by_the_counterparty(self):
        """Proof the fake provider actually checks PKCE, so the flow test means
        something. Without this, a broken challenge would still pass above."""
        with FakeProvider() as fp:
            cfg = fp.config()
            store = oauth.MemoryTransactionStore()
            auth = oauth.begin(cfg, CREDS, redirect_uri=ALLOWED, allowlist=[ALLOWED],
                               session_id="s", store=store)
            cb = follow_authorize(auth.url)
            auth.transaction.verifier = oauth.new_verifier()   # attacker's verifier
            store.put(auth.transaction)
            with self.assertRaises(oauth.OAuthError) as ctx:
                oauth.finish(cfg, CREDS, code=cb["code"], state=cb["state"],
                             session_id="s", store=store)
            self.assertEqual(1, fp.state["pkce_failures"])
            # A rejected code is not a disconnected account: there is no
            # connection yet to disconnect, and the two need different prompts.
            self.assertNotIsInstance(ctx.exception, oauth.Disconnected)

    def test_tokens_never_appear_in_a_url(self):
        with FakeProvider() as fp:
            cfg = fp.config()
            store = oauth.MemoryTransactionStore()
            auth = oauth.begin(cfg, CREDS, redirect_uri=ALLOWED, allowlist=[ALLOWED],
                               session_id="s", store=store)
            cb = follow_authorize(auth.url)
            tokset, _ = oauth.finish(cfg, CREDS, code=cb["code"], state=cb["state"],
                                     session_id="s", store=store)
            secrets_seen = [tokset.access_token, tokset.refresh_token,
                            auth.transaction.verifier, CREDS.client_secret]
            for url in fp.state["seen_urls"]:
                for value in secrets_seen:
                    self.assertNotIn(value, url)
            # The token exchange is a POST body, never a query string.
            self.assertEqual(["/token"], [u for u in fp.state["seen_urls"] if "token" in u])


class TestStateIsCsrfProtection(unittest.TestCase):
    def setUp(self):
        self.fp = FakeProvider().__enter__()
        self.cfg = self.fp.config()
        self.store = oauth.MemoryTransactionStore()
        self.auth = oauth.begin(self.cfg, CREDS, redirect_uri=ALLOWED, allowlist=[ALLOWED],
                                session_id="sess", store=self.store)
        self.cb = follow_authorize(self.auth.url)

    def tearDown(self):
        self.fp.__exit__(None, None, None)

    def test_mismatched_state_is_rejected(self):
        with self.assertRaises(oauth.StateMismatch):
            oauth.finish(self.cfg, CREDS, code=self.cb["code"], state="not-the-state",
                         session_id="sess", store=self.store)

    def test_missing_state_is_rejected(self):
        with self.assertRaises(oauth.StateMismatch):
            oauth.finish(self.cfg, CREDS, code=self.cb["code"], state="",
                         session_id="sess", store=self.store)

    def test_state_is_single_use(self):
        oauth.finish(self.cfg, CREDS, code=self.cb["code"], state=self.cb["state"],
                     session_id="sess", store=self.store)
        with self.assertRaises(oauth.StateMismatch):
            oauth.finish(self.cfg, CREDS, code=self.cb["code"], state=self.cb["state"],
                         session_id="sess", store=self.store)

    def test_state_is_bound_to_the_session(self):
        # The attack: attacker starts their own authorization, then feeds the
        # victim the callback URL. Same valid state, different browser session.
        with self.assertRaises(oauth.StateMismatch):
            oauth.finish(self.cfg, CREDS, code=self.cb["code"], state=self.cb["state"],
                         session_id="victims-session", store=self.store)

    def test_state_expires(self):
        later = self.auth.transaction.expires_at + 1
        with self.assertRaises(oauth.StateMismatch):
            oauth.finish(self.cfg, CREDS, code=self.cb["code"], state=self.cb["state"],
                         session_id="sess", store=self.store, now=later)

    def test_state_is_high_entropy_and_unique(self):
        self.assertGreaterEqual(len(self.auth.state), 32)
        self.assertEqual(50, len({oauth.new_state() for _ in range(50)}))

    def test_purge_expired_clears_the_table(self):
        self.assertEqual(1, self.store.purge_expired(self.auth.transaction.expires_at + 1))
        self.assertEqual(0, self.store.purge_expired())


# --------------------------------------------------------------------------
# rotation and reuse detection


class TestRotation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = tokens.FileTokenStore(pathlib.Path(self.tmp.name))
        self.fp = FakeProvider().__enter__()
        self.cfg = self.fp.config()

    def tearDown(self):
        self.fp.__exit__(None, None, None)
        self.tmp.cleanup()

    def _link(self) -> str:
        tx = oauth.MemoryTransactionStore()
        auth = oauth.begin(self.cfg, CREDS, redirect_uri=ALLOWED, allowlist=[ALLOWED],
                           session_id="s", store=tx)
        cb = follow_authorize(auth.url)
        tokset, _ = oauth.finish(self.cfg, CREDS, code=cb["code"], state=cb["state"],
                                 session_id="s", store=tx)
        self.store.link("u1", "fake", tokset.refresh_token, scopes=tokset.scope)
        return tokset.refresh_token

    def test_refresh_rotates_and_retires_the_old_token(self):
        first = self._link()
        fresh = oauth.refresh(self.cfg, CREDS, self.store, user_id="u1", provider="fake")
        self.assertNotEqual(first, fresh.refresh_token)
        conn = self.store.load("u1", "fake")
        self.assertEqual(oauth.token_fingerprint(fresh.refresh_token),
                         conn.refresh_fingerprint)
        self.assertTrue(self.store.is_spent(conn.family_id, oauth.token_fingerprint(first)))
        self.assertEqual(fresh.refresh_token, self.store.reveal_refresh_token(conn))

    def test_replaying_a_spent_refresh_token_kills_the_family(self):
        first = self._link()
        oauth.refresh(self.cfg, CREDS, self.store, user_id="u1", provider="fake")

        with self.assertRaises(oauth.FamilyCompromised):
            oauth.refresh(self.cfg, CREDS, self.store, user_id="u1", provider="fake",
                          presented=first)

        conn = self.store.load("u1", "fake")
        self.assertIsNone(conn, "a revoked family must not leave a usable token behind")
        raw = json.loads((pathlib.Path(self.tmp.name) / "fake.json").read_text())
        self.assertTrue(raw["revoked"])
        self.assertEqual("refresh token reuse", raw["revoked_reason"])
        self.assertEqual("", raw["refresh_token"])

    def test_a_token_we_never_issued_also_revokes(self):
        self._link()
        with self.assertRaises(oauth.FamilyCompromised):
            oauth.refresh(self.cfg, CREDS, self.store, user_id="u1", provider="fake",
                          presented="REFRESH-forged")
        raw = json.loads((pathlib.Path(self.tmp.name) / "fake.json").read_text())
        self.assertTrue(raw["revoked"])
        self.assertEqual("unrecognised refresh token", raw["revoked_reason"])

    def test_a_revoked_family_refuses_every_later_refresh(self):
        first = self._link()
        oauth.refresh(self.cfg, CREDS, self.store, user_id="u1", provider="fake")
        with self.assertRaises(oauth.FamilyCompromised):
            oauth.refresh(self.cfg, CREDS, self.store, user_id="u1", provider="fake",
                          presented=first)
        # Even the legitimate holder is locked out; that is the intended blast
        # radius, because we cannot tell the two parties apart.
        with self.assertRaises(oauth.OAuthError):
            oauth.refresh(self.cfg, CREDS, self.store, user_id="u1", provider="fake")

    def test_invalid_grant_is_a_relink_not_a_server_error(self):
        self._link()
        self.fp.state["always_invalid_grant"] = True
        with self.assertRaises(oauth.Disconnected):
            oauth.refresh(self.cfg, CREDS, self.store, user_id="u1", provider="fake")
        conn = self.store.load("u1", "fake")
        self.assertTrue(conn.disconnected_at > 0)
        self.assertFalse(conn.revoked, "invalid_grant is not a compromise")
        self.assertFalse(conn.to_public()["connected"])

    def test_refresh_without_a_connection_is_disconnected(self):
        with self.assertRaises(oauth.Disconnected):
            oauth.refresh(self.cfg, CREDS, self.store, user_id="nobody", provider="fake")

    def test_no_secret_reaches_the_exception_text(self):
        first = self._link()
        oauth.refresh(self.cfg, CREDS, self.store, user_id="u1", provider="fake")
        with self.assertRaises(oauth.FamilyCompromised) as ctx:
            oauth.refresh(self.cfg, CREDS, self.store, user_id="u1", provider="fake",
                          presented=first)
        self.assertNotIn(first, str(ctx.exception))


# --------------------------------------------------------------------------
# sealing


KEY = b"k" * 32
OTHER = b"o" * 32


class TestSealing(unittest.TestCase):
    def test_round_trip(self):
        blob = tokens.seal("REFRESH-abc", KEY, "u1|yahoo|fam")
        self.assertNotIn("REFRESH-abc", blob)
        self.assertEqual("REFRESH-abc", tokens.unseal(blob, KEY, "u1|yahoo|fam"))

    def test_two_seals_of_one_value_differ(self):
        a = tokens.seal("same", KEY, "aad")
        b = tokens.seal("same", KEY, "aad")
        self.assertNotEqual(a, b, "a fresh salt and nonce per record, or nothing")

    def test_tampering_with_the_ciphertext_fails_authentication(self):
        blob = tokens.seal("REFRESH-abc", KEY, "aad")
        parts = blob.split(".")
        raw = bytearray(tokens._unb64u(parts[4]))
        raw[0] ^= 0x01
        parts[4] = tokens._b64u(bytes(raw))
        with self.assertRaises(tokens.DecryptionFailed):
            tokens.unseal(".".join(parts), KEY, "aad")

    def test_a_row_moved_to_another_user_will_not_open(self):
        blob = tokens.seal("REFRESH-abc", KEY, "u1|yahoo|fam")
        with self.assertRaises(tokens.DecryptionFailed):
            tokens.unseal(blob, KEY, "u2|yahoo|fam")

    def test_the_wrong_key_is_named_not_guessed(self):
        blob = tokens.seal("x", KEY, "")
        with self.assertRaises(tokens.DecryptionFailed) as ctx:
            tokens.unseal(blob, OTHER, "")
        self.assertIn("key id", str(ctx.exception))

    def test_rotation_window_opens_old_rows(self):
        blob = tokens.seal("old-secret", OTHER, "")
        self.assertEqual("old-secret", tokens.unseal(blob, KEY, "", fallback=OTHER))

    def test_master_key_must_be_long_enough(self):
        with self.assertRaises(tokens.TokenStoreError):
            tokens.master_key({"TOKEN_ENCRYPTION_KEY": "changeme"})
        with self.assertRaises(tokens.TokenStoreError):
            tokens.master_key({})
        self.assertEqual(b"K" * 40, tokens.master_key({"TOKEN_ENCRYPTION_KEY": "K" * 40}))

    def test_base64_key_material_is_accepted(self):
        raw = secrets.token_bytes(32)
        env = {"TOKEN_ENCRYPTION_KEY": base64.urlsafe_b64encode(raw).decode().rstrip("=")}
        self.assertEqual(raw, tokens.master_key(env))

    def test_key_id_is_short_stable_and_not_the_key(self):
        kid = tokens.key_id(KEY)
        self.assertEqual(kid, tokens.key_id(KEY))
        self.assertNotEqual(kid, tokens.key_id(OTHER))
        self.assertEqual(12, len(kid))


# --------------------------------------------------------------------------
# a PostgREST stub


class PostgrestHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    @property
    def db(self):
        return self.server.db  # type: ignore[attr-defined]

    def _table_and_filters(self):
        parsed = urllib.parse.urlparse(self.path)
        table = parsed.path.rsplit("/", 1)[-1]
        filters = {}
        for k, v in urllib.parse.parse_qs(parsed.query).items():
            if k in ("select", "limit", "order"):
                continue
            op, _, value = v[0].partition(".")
            filters[k] = (op, value)
        return table, filters

    @staticmethod
    def _matches(row: dict, filters: dict) -> bool:
        for col, (op, value) in filters.items():
            actual = row.get(col)
            if op == "eq" and str(actual) != value:
                return False
            if op == "lt" and not (float(actual or 0) < float(value)):
                return False
        return True

    def _guard(self) -> bool:
        """The service key must arrive in headers. A stub that did not check
        would let a regression that puts it in the query string pass."""
        self.server.seen_urls.append(self.path)  # type: ignore[attr-defined]
        if self.headers.get("apikey") != "test-service-key":
            self._send(401, [{"message": "no apikey header"}])
            return False
        return True

    def _send(self, status: int, payload) -> None:
        raw = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _body(self):
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length).decode()) if length else None

    def do_GET(self):  # noqa: N802
        if not self._guard():
            return
        table, filters = self._table_and_filters()
        rows = [r for r in self.db.setdefault(table, []) if self._matches(r, filters)]
        self._send(200, rows)

    def do_POST(self):  # noqa: N802
        if not self._guard():
            return
        table, _ = self._table_and_filters()
        row = self._body()
        rows = self.db.setdefault(table, [])
        prefer = self.headers.get("Prefer", "")
        if "merge-duplicates" in prefer and table == tokens.CONNECTIONS:
            rows[:] = [r for r in rows
                       if not (r["user_id"] == row["user_id"]
                               and r["provider"] == row["provider"])]
        rows.append(row)
        self._send(201, [row] if "return=representation" in prefer else [])

    def do_PATCH(self):  # noqa: N802
        if not self._guard():
            return
        table, filters = self._table_and_filters()
        patch = self._body()
        hit = []
        for row in self.db.setdefault(table, []):
            if self._matches(row, filters):
                row.update(patch)
                hit.append(row)
        self._send(200, hit if "return=representation" in self.headers.get("Prefer", "") else [])

    def do_DELETE(self):  # noqa: N802
        if not self._guard():
            return
        table, filters = self._table_and_filters()
        rows = self.db.setdefault(table, [])
        gone = [r for r in rows if self._matches(r, filters)]
        rows[:] = [r for r in rows if r not in gone]
        self._send(200, gone if "return=representation" in self.headers.get("Prefer", "") else [])

    def log_message(self, fmt, *args):
        pass


class Postgrest:
    def __init__(self) -> None:
        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), PostgrestHandler)
        self.httpd.db = {}          # type: ignore[attr-defined]
        self.httpd.seen_urls = []   # type: ignore[attr-defined]
        self.db = self.httpd.db     # type: ignore[attr-defined]
        self.seen_urls = self.httpd.seen_urls  # type: ignore[attr-defined]
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever,
                                       kwargs={"poll_interval": 0.02}, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()

    def env(self) -> dict:
        return {"SUPABASE_URL": f"http://127.0.0.1:{self.port}",
                "SUPABASE_SERVICE_KEY": "test-service-key",
                "TOKEN_ENCRYPTION_KEY": "T" * 40}


class TestSupabaseTokenStore(unittest.TestCase):
    def setUp(self):
        self.pg = Postgrest().__enter__()
        self.store = tokens.SupabaseTokenStore(env=self.pg.env())

    def tearDown(self):
        self.pg.__exit__(None, None, None)

    def test_link_stores_ciphertext_and_load_returns_it_sealed(self):
        self.store.link("u1", "yahoo", "REFRESH-plain", scopes="fspt-r")
        row = self.pg.db[tokens.CONNECTIONS][0]
        self.assertNotIn("REFRESH-plain", json.dumps(row))
        self.assertTrue(row["refresh_sealed"].startswith("fe1."))
        conn = self.store.load("u1", "yahoo")
        self.assertEqual("REFRESH-plain", self.store.reveal_refresh_token(conn))

    def test_credentials_never_travel_in_a_url(self):
        self.store.link("u1", "yahoo", "REFRESH-plain")
        self.store.load("u1", "yahoo")
        for url in self.pg.seen_urls:
            self.assertNotIn("test-service-key", url)
            self.assertNotIn("REFRESH-plain", url)
            self.assertNotIn("TTTT", url)

    def test_rotation_records_the_spent_fingerprint(self):
        conn = self.store.link("u1", "yahoo", "R1")
        self.store.rotate(conn, "R2", spent_fingerprint=oauth.token_fingerprint("R1"))
        self.assertTrue(self.store.is_spent(conn.family_id, oauth.token_fingerprint("R1")))
        self.assertFalse(self.store.is_spent(conn.family_id, oauth.token_fingerprint("R2")))
        self.assertEqual("R2", self.store.reveal_refresh_token(self.store.load("u1", "yahoo")))

    def test_revoking_clears_the_ciphertext(self):
        conn = self.store.link("u1", "yahoo", "R1")
        self.store.revoke_family(conn.family_id, "refresh token reuse")
        after = self.store.load("u1", "yahoo")
        self.assertTrue(after.revoked)
        self.assertEqual("", after.sealed_refresh)
        with self.assertRaises(tokens.TokenStoreError):
            self.store.reveal_refresh_token(after)

    def test_relinking_replaces_the_row_and_starts_a_new_family(self):
        one = self.store.link("u1", "yahoo", "R1")
        two = self.store.link("u1", "yahoo", "R2")
        self.assertEqual(1, len(self.pg.db[tokens.CONNECTIONS]))
        self.assertNotEqual(one.family_id, two.family_id)

    def test_full_rotation_and_reuse_through_the_oauth_layer(self):
        with FakeProvider() as fp:
            cfg = fp.config()
            fp.state["current_refresh"] = "R1"
            self.store.link("u1", "fake", "R1", scopes="fspt-r")
            fresh = oauth.refresh(cfg, CREDS, self.store, user_id="u1", provider="fake")
            self.assertNotEqual("R1", fresh.refresh_token)
            with self.assertRaises(oauth.FamilyCompromised):
                oauth.refresh(cfg, CREDS, self.store, user_id="u1", provider="fake",
                              presented="R1")
            self.assertTrue(self.store.load("u1", "fake").revoked)

    def test_unlink_removes_the_row(self):
        self.store.link("u1", "yahoo", "R1")
        self.store.unlink("u1", "yahoo")
        self.assertIsNone(self.store.load("u1", "yahoo"))

    def test_missing_configuration_refuses_to_construct(self):
        with self.assertRaises(tokens.TokenStoreError):
            tokens.PostgREST(env={})

    def test_store_from_env_picks_the_file_store_without_supabase(self):
        self.assertIsInstance(tokens.store_from_env({}), tokens.FileTokenStore)
        self.assertIsInstance(tokens.store_from_env(self.pg.env()), tokens.SupabaseTokenStore)


class TestSupabaseTransactionStore(unittest.TestCase):
    def setUp(self):
        self.pg = Postgrest().__enter__()
        self.store = tokens.SupabaseTransactionStore(env=self.pg.env())

    def tearDown(self):
        self.pg.__exit__(None, None, None)

    def _tx(self, state="st-1"):
        return oauth.Transaction(state=state, verifier=oauth.new_verifier(),
                                 redirect_uri=ALLOWED, provider="yahoo",
                                 session_id="sess", created_at=100.0, expires_at=700.0)

    def test_verifier_is_sealed_at_rest_and_round_trips(self):
        tx = self._tx()
        self.store.put(tx)
        row = self.pg.db[tokens.TRANSACTIONS][0]
        self.assertNotIn(tx.verifier, json.dumps(row))
        got = self.store.take("st-1")
        self.assertEqual(tx.verifier, got.verifier)
        self.assertEqual("sess", got.session_id)

    def test_take_is_single_use(self):
        self.store.put(self._tx())
        self.assertIsNotNone(self.store.take("st-1"))
        self.assertIsNone(self.store.take("st-1"))

    def test_unknown_state_returns_none(self):
        self.assertIsNone(self.store.take("never-existed"))

    def test_purge_expired(self):
        self.store.put(self._tx("a"))
        self.assertEqual(1, self.store.purge_expired(now=10_000))
        self.assertEqual(0, self.store.purge_expired(now=10_000))

    def test_it_satisfies_the_flow_end_to_end(self):
        with FakeProvider() as fp:
            cfg = fp.config()
            auth = oauth.begin(cfg, CREDS, redirect_uri=ALLOWED, allowlist=[ALLOWED],
                               session_id="sess", store=self.store)
            cb = follow_authorize(auth.url)
            tokset, _ = oauth.finish(cfg, CREDS, code=cb["code"], state=cb["state"],
                                     session_id="sess", store=self.store)
            self.assertTrue(tokset.access_token)
            with self.assertRaises(oauth.StateMismatch):
                oauth.finish(cfg, CREDS, code=cb["code"], state=cb["state"],
                             session_id="sess", store=self.store)


# --------------------------------------------------------------------------
# nothing leaks


class TestNoLeaks(unittest.TestCase):
    def test_public_shapes_carry_no_secret(self):
        conn = tokens.StoredConnection(
            user_id="u1", provider="yahoo", family_id="fam",
            refresh_fingerprint="ff", sealed_refresh="fe1.secret.blob", scopes="fspt-r")
        self.assertNotIn("fe1.secret.blob", json.dumps(conn.to_public()))
        self.assertNotIn("fe1.secret.blob", repr(conn))
        self.assertNotIn("fe1.secret.blob", json.dumps(tokens.asdict_safe(conn)))
        self.assertIn("<redacted>", repr(conn))

    def test_tokenset_repr_is_redacted(self):
        ts = oauth.TokenSet(access_token="ACCESS-x", refresh_token="REFRESH-y")
        self.assertNotIn("ACCESS-x", repr(ts))
        self.assertNotIn("REFRESH-y", repr(ts))
        self.assertNotIn("REFRESH-y", json.dumps(ts.to_public()))

    def test_credentials_repr_is_redacted(self):
        self.assertNotIn("fake-client-secret", repr(CREDS))

    def test_only_the_refresh_routine_reads_plaintext(self):
        """`reveal_refresh_token` is the one door to a decrypted token. If it
        acquires a second caller, that caller wants review."""
        callers = []
        for path in sorted((REPO / "fantasyedge").rglob("*.py")):
            if path.name in ("tokens.py",):
                continue
            if "reveal_refresh_token" in path.read_text():
                callers.append(path.name)
        self.assertEqual(["oauth.py"], callers)

    def test_the_read_api_does_not_touch_token_storage(self):
        # api.py is the surface that binds to the LAN. It holds no credential
        # today and must not learn how to reach one.
        source = (REPO / "fantasyedge" / "api.py").read_text()
        self.assertNotIn("import tokens", source)
        self.assertNotIn("from .tokens", source)
        self.assertNotIn("from . import oauth", source)

    def test_no_logging_of_any_kind_in_the_oauth_modules(self):
        for name in ("oauth.py", "tokens.py"):
            source = (REPO / "fantasyedge" / name).read_text()
            self.assertNotIn("import logging", source)

    def test_a_completed_flow_writes_no_secret_into_the_repo(self):
        sentinel = "SENTINEL-" + secrets.token_hex(12)
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse(pathlib.Path(tmp).is_relative_to(REPO))
            store = tokens.FileTokenStore(pathlib.Path(tmp))
            store.link("u1", "fake", sentinel, scopes="fspt-r")
            self.assertEqual(sentinel, store.reveal_refresh_token(store.load("u1", "fake")))
            leaked = []
            for path in REPO.rglob("*"):
                parts = set(path.parts)
                if not path.is_file() or ".git" in parts or "__pycache__" in parts:
                    continue
                if path.stat().st_size > 2_000_000:
                    continue
                try:
                    if sentinel in path.read_text(errors="ignore"):
                        leaked.append(str(path))
                except OSError:
                    continue
            self.assertEqual([], leaked)

    def test_the_token_file_is_not_world_readable(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = tokens.FileTokenStore(pathlib.Path(tmp))
            store.link("u1", "yahoo", "R1")
            self.assertEqual(0o600, store.path("yahoo").stat().st_mode & 0o777)


# --------------------------------------------------------------------------
# the loopback listener


class TestLoopbackListener(unittest.TestCase):
    def test_it_catches_the_code_on_a_random_loopback_port(self):
        with oauth.LoopbackListener() as listener:
            self.assertTrue(listener.redirect_uri.startswith("http://127.0.0.1:"))
            self.assertNotEqual(0, listener.port)
            url = listener.redirect_uri + "?code=abc123&state=st"
            threading.Thread(target=lambda: urllib.request.urlopen(url, timeout=5).read(),
                             daemon=True).start()
            params = listener.wait(timeout=5)
        self.assertEqual({"code": "abc123", "state": "st"}, params)

    def test_the_browser_page_does_not_echo_the_code(self):
        with oauth.LoopbackListener() as listener:
            with urllib.request.urlopen(
                    listener.redirect_uri + "?code=abc123&state=st", timeout=5) as resp:
                body = resp.read().decode()
            listener.wait(timeout=5)
        self.assertNotIn("abc123", body)
        self.assertIn("Connected", body)

    def test_a_wrong_path_is_not_the_callback(self):
        with oauth.LoopbackListener() as listener:
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(f"http://127.0.0.1:{listener.port}/other", timeout=5)
            ctx.exception.close()

    def test_two_listeners_do_not_share_a_port(self):
        with oauth.LoopbackListener() as a, oauth.LoopbackListener() as b:
            self.assertNotEqual(a.port, b.port)

    def test_the_whole_loopback_flow(self):
        """Bind, authorize, catch the redirect, exchange - with a thread
        standing in for the browser. The listener is already serving by the
        time the URL is printed, which is what makes that safe."""
        done = threading.Event()

        def drive(authorize_url: str) -> None:
            query = urllib.parse.parse_qs(urllib.parse.urlparse(authorize_url).query)
            redirect_uri = query["redirect_uri"][0]
            self.assertTrue(redirect_uri.startswith("http://127.0.0.1:"))
            params = follow_authorize(authorize_url)
            urllib.request.urlopen(
                f"{redirect_uri}?code={params['code']}&state={params['state']}",
                timeout=5).read()
            done.set()

        def printer(message: str) -> None:
            url = message.split("visit:\n\n  ")[1].strip()
            threading.Thread(target=drive, args=(url,), daemon=True).start()

        with FakeProvider() as fp:
            tokset = oauth.run_loopback_flow(fp.config(), CREDS, open_browser=False,
                                             printer=printer, timeout=10)
        self.assertTrue(tokset.access_token.startswith("ACCESS-"))
        self.assertTrue(done.wait(5))


# --------------------------------------------------------------------------
# the deployment files carry no real values


class TestDeployArtifacts(unittest.TestCase):
    FILES = ["schema.sql", "Dockerfile", "vercel.json", "README.md"]

    def test_every_file_exists(self):
        for name in self.FILES:
            self.assertTrue((REPO / "deploy" / name).exists(), name)

    def test_row_level_security_is_on_for_every_table(self):
        sql = " ".join((REPO / "deploy" / "schema.sql").read_text().lower().split())
        for table in ("users", "provider_connections", "oauth_transactions",
                      "refresh_rotations"):
            self.assertIn(f"alter table {table} enable row level security", sql)
        # RLS with a permissive policy is RLS off with extra steps, so the
        # absence of a live `create policy` is the assertion that matters.
        for line in (REPO / "deploy" / "schema.sql").read_text().splitlines():
            self.assertFalse(line.strip().lower().startswith("create policy"), line)

    def test_the_schema_covers_what_the_store_writes(self):
        sql = (REPO / "deploy" / "schema.sql").read_text().lower()
        for column in ("family_id", "refresh_sealed", "refresh_fingerprint",
                       "rotated_at_epoch", "code_verifier_sealed", "expires_at_epoch",
                       "revoked", "scopes"):
            self.assertIn(column, sql)

    def test_no_real_secret_is_committed(self):
        """Placeholders only. A deploy file with a live key in it is the single
        most common way a service key ends up on GitHub."""
        for name in self.FILES:
            text = (REPO / "deploy" / name).read_text()
            for line in text.splitlines():
                stripped = line.strip()
                for var in ("SUPABASE_SERVICE_KEY", "TOKEN_ENCRYPTION_KEY",
                            "YAHOO_CLIENT_SECRET"):
                    if f"{var}=" in stripped and not stripped.startswith(("#", "//", "--")):
                        value = stripped.split(f"{var}=", 1)[1].strip().strip('",')
                        self.assertTrue(
                            value.startswith("<") or value in ("", "$" + var)
                            or "REPLACE" in value.upper(),
                            f"{name}: {var} must be a placeholder, got {value!r}")

    def test_the_dockerfile_installs_nothing(self):
        text = (REPO / "deploy" / "Dockerfile").read_text().lower()
        for forbidden in ("pip install", "requirements.txt", "poetry", "apt-get install"):
            self.assertNotIn(forbidden, text)



# --------------------------------------------------------------------------
# the single-user CLI is unchanged


class TestSingleUserPathStillWorks(unittest.TestCase):
    """The service path is additive. Everything below worked before this module
    existed and has to keep working exactly as well."""

    def test_a_token_written_the_new_way_is_read_by_the_old_provider(self):
        from fantasyedge.providers.yahoo import YahooAuth

        with tempfile.TemporaryDirectory() as tmp:
            store = tokens.FileTokenStore(pathlib.Path(tmp))
            tokset = oauth.TokenSet(access_token="ACCESS-1", refresh_token="REFRESH-1",
                                    expires_at=time.time() + 3000, scope="fspt-r")
            path = tokens.save_cli_tokens(tokset, "yahoo", store=store)
            auth = YahooAuth(client_id="id", client_secret="secret", token_path=path)
            # No network: the token is still fresh, so `access_token` returns it
            # from disk. If the file layout drifted, this raises or refreshes.
            self.assertEqual("ACCESS-1", auth.access_token())
            self.assertEqual("REFRESH-1", auth._tok["refresh_token"])

    def test_the_rotation_fields_do_not_disturb_the_old_reader(self):
        from fantasyedge.providers.yahoo import YahooAuth

        with tempfile.TemporaryDirectory() as tmp:
            store = tokens.FileTokenStore(pathlib.Path(tmp))
            store.link("local", "yahoo", "R1")
            doc = json.loads(store.path("yahoo").read_text())
            self.assertIn("family_id", doc)
            self.assertIn("spent", doc)
            YahooAuth(client_id="id", token_path=store.path("yahoo"))  # parses fine

    def test_a_pre_existing_file_with_no_rotation_state_still_loads(self):
        with tempfile.TemporaryDirectory() as tmp:
            legacy = pathlib.Path(tmp) / "yahoo.json"
            legacy.write_text(json.dumps({"access_token": "A", "refresh_token": "R",
                                          "expires_at": 1}))
            conn = tokens.FileTokenStore(pathlib.Path(tmp)).load("local", "yahoo")
            self.assertEqual(oauth.token_fingerprint("R"), conn.refresh_fingerprint)
            self.assertEqual("file:yahoo", conn.family_id)

    def test_auth_url_still_prints_and_exits_without_touching_stdin(self):
        with tempfile.TemporaryDirectory() as home:
            env = dict(os.environ, HOME=home, YAHOO_CLIENT_ID="test-id",
                       YAHOO_CLIENT_SECRET="test-secret")
            out = subprocess.run(
                [sys.executable, "-m", "fantasyedge", "auth", "--provider", "yahoo",
                 "--url", "--json"],
                cwd=REPO, env=env, capture_output=True, text=True, timeout=60,
                stdin=subprocess.DEVNULL)
            self.assertEqual(0, out.returncode, out.stderr)
            payload = json.loads(out.stdout)
            self.assertTrue(payload["authorize_url"].startswith(
                "https://api.login.yahoo.com/oauth2/request_auth?"))
            self.assertNotIn("test-secret", out.stdout)

    def test_the_new_flag_is_advertised_in_help(self):
        out = subprocess.run(
            [sys.executable, "-m", "fantasyedge", "auth", "--help"],
            cwd=REPO, capture_output=True, text=True, timeout=60)
        self.assertIn("--local", out.stdout)
        self.assertIn("--code", out.stdout)


if __name__ == "__main__":
    unittest.main()
