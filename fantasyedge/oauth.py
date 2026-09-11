"""Authorization Code + PKCE, provider-agnostic, for the multi-user service.

`providers/yahoo.py` already does three-legged OAuth and it is not wrong. It is
scoped to one person on their own laptop: there is one token, it lives in
`~/.fantasy-edge/yahoo.json` behind file permissions, and the only party who
can steal the authorization code is the person who just typed the password.
None of that survives contact with a server that does this for strangers, so
this module is the flow again with the controls that only matter once there is
more than one user and a public redirect endpoint:

  * **PKCE, S256 only.** The name of the weaker method appears nowhere in this
    module - a test greps for it - and `CHALLENGE_METHOD` is a constant rather
    than a parameter, so there is no downgrade to negotiate. A public redirect
    URL means an authorization code can be intercepted; without the verifier, a
    stolen code is not redeemable.
  * **`state`, single-use, TTL-bounded, bound to the session.** This is the
    CSRF control. Without it anyone can hand a victim a callback URL carrying
    *their* authorization code and silently graft their Yahoo account onto the
    victim's fantasy-edge login. The check is not "is this state well-formed",
    it is "did *this browser session* start this exact transaction, recently,
    and not already finish it".
  * **Exact redirect-URI matching against a server-side allowlist.** No
    wildcards, no prefix matching, no "starts with our domain". Prefix matching
    is how open redirects happen, and an open redirect on the callback turns
    the code into a token in the attacker's log.
  * **Refresh rotation with reuse detection.** See `refresh` - it is the one
    control that turns a stolen refresh token from permanent access into a
    detectable, self-limiting incident.

Two things this module will not do. It never puts a token in a URL: every
token request is a POST with a form body, and the only thing that ever travels
in a query string is the authorization code, which is single-use and useless
without the verifier. And it never logs a token - there is no logger here at
all, and error text carries the provider's error *code*, never its body, since
a token endpoint that echoes a request on failure would otherwise put a secret
in a log line.

Storage lives in `tokens.py`. This module is pure flow and holds nothing.
"""

from __future__ import annotations

import abc
import base64
import dataclasses
import hashlib
import http.server
import json
import os
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

USER_AGENT = "fantasy-edge/1.0 (oauth)"

# S256 is the only method this module can emit. RFC 7636 also defines a no-op
# method, which offers no protection at all against a code interceptor who can
# also see the authorize request - and an attacker positioned to steal a code
# from a redirect is very often exactly that. Making it a constant rather than
# an argument means no caller can accidentally negotiate it away.
CHALLENGE_METHOD = "S256"

# RFC 7636 fixes the verifier at 43-128 characters of unreserved alphabet.
# 64 characters of `secrets.token_urlsafe` is 384 bits, comfortably inside it.
VERIFIER_MIN = 43
VERIFIER_MAX = 128
VERIFIER_BYTES = 48

# How long an in-flight authorization may sit unfinished. Long enough for a
# human to read a consent screen and get through a password manager, short
# enough that a `state` scraped from a browser history or a proxy log is dead
# by the time anybody tries it.
TRANSACTION_TTL = 600.0


class OAuthError(RuntimeError):
    """Anything that went wrong in the flow."""


class StateMismatch(OAuthError):
    """The callback did not match an in-flight transaction for this session.

    Unknown, expired, already-consumed and wrong-session all land here on
    purpose: telling the caller which one it was tells an attacker probing the
    callback whether a given `state` ever existed.
    """


class RedirectNotAllowed(OAuthError):
    """The redirect URI is not an exact match for an allowlisted one."""


class Disconnected(OAuthError):
    """The provider says this grant is dead. The user must link again.

    `invalid_grant` is the provider telling us the user revoked access, changed
    their password, or the refresh token simply aged out. It is a normal end of
    life for a connection, not a fault of ours, and it must never surface as a
    500 - a server error gets retried and paged, whereas this needs a "reconnect
    your Yahoo account" link and nothing else.
    """


class FamilyCompromised(OAuthError):
    """A spent refresh token was presented. The whole family is revoked."""


# --------------------------------------------------------------------------
# provider configuration


@dataclasses.dataclass(frozen=True)
class ProviderConfig:
    """Everything that differs between one OAuth provider and the next."""

    name: str
    authorize_url: str
    token_url: str
    scope: str = ""
    client_id_env: str = ""
    client_secret_env: str = ""
    # Yahoo wants HTTP Basic on the token endpoint; plenty of providers want the
    # client id and secret in the form body instead. RFC 6749 permits both and
    # providers disagree, so it is configuration rather than a guess.
    auth_style: str = "basic"
    extra_authorize_params: tuple[tuple[str, str], ...] = ()


PROVIDERS: dict[str, ProviderConfig] = {
    # URLs and scope lifted from providers/yahoo.py so the two cannot drift.
    # `fspt-r` is read-only Fantasy Sports. Nothing in this codebase writes to
    # a league, so asking for `fspt-w` would be requesting a permission we have
    # no use for - and the consent screen would be asking the user to trust us
    # with roster moves we will never make.
    "yahoo": ProviderConfig(
        name="yahoo",
        authorize_url="https://api.login.yahoo.com/oauth2/request_auth",
        token_url="https://api.login.yahoo.com/oauth2/get_token",
        scope="fspt-r",
        client_id_env="YAHOO_CLIENT_ID",
        client_secret_env="YAHOO_CLIENT_SECRET",
        auth_style="basic",
        extra_authorize_params=(("language", "en-us"),),
    ),
}


@dataclasses.dataclass(frozen=True)
class Credentials:
    """Client credentials. `repr` is redacted so a traceback cannot leak one."""

    client_id: str
    client_secret: str = ""

    def __repr__(self) -> str:
        return f"Credentials(client_id={self.client_id!r}, client_secret=<redacted>)"


def credentials_from_env(config: ProviderConfig, env: dict | None = None) -> Credentials:
    env = os.environ if env is None else env
    cid = env.get(config.client_id_env, "")
    if not cid:
        raise OAuthError(f"missing {config.client_id_env}")
    return Credentials(cid, env.get(config.client_secret_env, ""))


def get_provider_config(name: str) -> ProviderConfig:
    try:
        return PROVIDERS[name]
    except KeyError:
        raise OAuthError(f"unknown oauth provider: {name}") from None


# --------------------------------------------------------------------------
# PKCE


def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def new_verifier() -> str:
    """A fresh PKCE code verifier, 43-128 chars of the unreserved alphabet."""
    v = secrets.token_urlsafe(VERIFIER_BYTES)
    if not VERIFIER_MIN <= len(v) <= VERIFIER_MAX:  # pragma: no cover - arithmetic
        raise OAuthError(f"verifier length {len(v)} outside RFC 7636 bounds")
    return v


def challenge_for(verifier: str) -> str:
    """S256: base64url(sha256(verifier)), unpadded, per RFC 7636 §4.2."""
    if not VERIFIER_MIN <= len(verifier) <= VERIFIER_MAX:
        raise OAuthError("code verifier outside the 43-128 character bound")
    return _b64u(hashlib.sha256(verifier.encode("ascii")).digest())


def new_state() -> str:
    return secrets.token_urlsafe(32)


def token_fingerprint(token: str) -> str:
    """A stable, non-reversible name for a refresh token.

    Reuse detection needs to recognise a token it has already retired, and
    keeping a list of retired *tokens* would mean storing extra live secrets
    for exactly as long as they are dangerous. A SHA-256 of a high-entropy
    provider token is not brute-forceable in any useful sense, so the spent
    list holds fingerprints and the plaintext is discarded at rotation.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# redirect allowlist


def check_redirect(uri: str, allowlist) -> str:
    """Exact string match against a server-side allowlist. No wildcards.

    Deliberately dumber than it could be. Anything cleverer - suffix matching
    on the domain, ignoring the port, normalising the path - is a way to say
    yes to a URI the operator never wrote down, and the callback is where the
    authorization code lands. The CLI's loopback listener gets its concrete
    `http://127.0.0.1:<port>/callback` added to the allowlist at bind time,
    which is how a random port stays compatible with exact matching.
    """
    allowed = tuple(allowlist or ())
    if uri in allowed:
        return uri
    raise RedirectNotAllowed(f"redirect_uri is not allowlisted: {uri!r}")


def allowlist_from_env(env: dict | None = None) -> tuple[str, ...]:
    """`OAUTH_REDIRECT_ALLOWLIST`, comma-separated. Empty means nothing passes."""
    env = os.environ if env is None else env
    raw = env.get("OAUTH_REDIRECT_ALLOWLIST", "")
    return tuple(x.strip() for x in raw.split(",") if x.strip())


# --------------------------------------------------------------------------
# in-flight transactions


@dataclasses.dataclass
class Transaction:
    """One authorization in flight. Holds the verifier, so it holds a secret."""

    state: str
    verifier: str = dataclasses.field(repr=False)
    redirect_uri: str = ""
    provider: str = ""
    session_id: str = ""
    created_at: float = 0.0
    expires_at: float = 0.0

    def expired(self, now: float) -> bool:
        return now >= self.expires_at


class TransactionStore(abc.ABC):
    """Where in-flight `state` lives between the two legs.

    `take` is destructive by contract: a `state` is single-use, and the way you
    enforce single-use is to make reading it consume it. A store that offers a
    non-destructive `get` will eventually be used by someone in a retry path,
    and then a replayed callback works twice.
    """

    @abc.abstractmethod
    def put(self, tx: Transaction) -> None: ...

    @abc.abstractmethod
    def take(self, state: str) -> Transaction | None: ...

    def purge_expired(self, now: float | None = None) -> int:
        return 0


class MemoryTransactionStore(TransactionStore):
    """Single-process store. Fine for the CLI and for tests; not for two pods."""

    def __init__(self) -> None:
        self._rows: dict[str, Transaction] = {}
        self._lock = threading.Lock()

    def put(self, tx: Transaction) -> None:
        with self._lock:
            self._rows[tx.state] = tx

    def take(self, state: str) -> Transaction | None:
        with self._lock:
            return self._rows.pop(state, None)

    def purge_expired(self, now: float | None = None) -> int:
        now = time.time() if now is None else now
        with self._lock:
            dead = [s for s, tx in self._rows.items() if tx.expired(now)]
            for s in dead:
                del self._rows[s]
        return len(dead)


# --------------------------------------------------------------------------
# tokens in flight


@dataclasses.dataclass
class TokenSet:
    """A token response. Never serialise this into an HTTP response body."""

    access_token: str = dataclasses.field(repr=False, default="")
    refresh_token: str = dataclasses.field(repr=False, default="")
    expires_at: float = 0.0
    scope: str = ""
    token_type: str = "bearer"
    raw_expires_in: int = 0

    def __repr__(self) -> str:
        return (f"TokenSet(access_token=<redacted>, refresh_token=<redacted>, "
                f"expires_at={self.expires_at!r}, scope={self.scope!r})")

    def to_public(self) -> dict:
        """The only shape safe to hand to a template or an HTTP response."""
        return {"scope": self.scope, "expires_at": self.expires_at,
                "token_type": self.token_type}


def _parse_token_response(payload: dict, now: float) -> TokenSet:
    expires_in = int(payload.get("expires_in", 3600) or 3600)
    return TokenSet(
        access_token=str(payload.get("access_token", "")),
        refresh_token=str(payload.get("refresh_token", "")),
        # The 60 second haircut matches providers/yahoo.py: a token that expires
        # while a request is in flight fails the request, and the retry costs
        # more than a minute of unused life.
        expires_at=now + expires_in - 60,
        scope=str(payload.get("scope", "")),
        token_type=str(payload.get("token_type", "bearer")),
        raw_expires_in=expires_in,
    )


def post_form(url: str, form: dict, headers: dict | None = None, timeout: int = 20) -> dict:
    """POST an application/x-www-form-urlencoded body and parse the JSON reply.

    A separate function from `providers.base.Http` because that one is a GET
    client with retry, and retrying a token exchange is wrong: an authorization
    code is single-use, so a retry after a timeout burns the code and the second
    attempt fails with `invalid_grant` that the caller then misreads as "the
    user revoked us".
    """
    data = urllib.parse.urlencode(form).encode()
    hdrs = {"Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json", "User-Agent": USER_AGENT}
    hdrs.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=hdrs, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        with exc:
            body = exc.read().decode("utf-8", "replace")
        raise _error_from_body(exc.code, body) from None
    except urllib.error.URLError as exc:
        raise OAuthError(f"token endpoint unreachable: {exc.reason}") from None
    try:
        payload = json.loads(body)
    except ValueError:
        raise OAuthError("token endpoint returned a non-JSON body") from None
    if isinstance(payload, dict) and payload.get("error"):
        raise _error_from_code(str(payload["error"]))
    return payload


def _error_from_body(status: int, body: str) -> OAuthError:
    """Turn a failed token call into an exception without quoting the body.

    The body is parsed for the OAuth error *code* and then dropped. It is not
    put in the message and not logged, because a provider that echoes the
    submitted form back on error - and some do - would otherwise write the
    refresh token straight into a traceback and from there into a log
    aggregator that nobody thinks of as holding credentials.
    """
    code = ""
    try:
        parsed = json.loads(body)
        if isinstance(parsed, dict):
            code = str(parsed.get("error", ""))
    except ValueError:
        pass
    if code:
        return _error_from_code(code)
    return OAuthError(f"token endpoint returned HTTP {status}")


def _error_from_code(code: str) -> OAuthError:
    if code == "invalid_grant":
        return Disconnected("the provider rejected this grant; the user must link again")
    return OAuthError(f"token endpoint error: {code}")


# --------------------------------------------------------------------------
# leg one: authorize


@dataclasses.dataclass
class Authorization:
    url: str
    state: str
    transaction: Transaction = dataclasses.field(repr=False)


def begin(
    config: ProviderConfig,
    credentials: Credentials,
    *,
    redirect_uri: str,
    allowlist,
    session_id: str,
    store: TransactionStore,
    scope: str | None = None,
    now: float | None = None,
    ttl: float = TRANSACTION_TTL,
) -> Authorization:
    """Mint state + PKCE, record the transaction, return the authorize URL."""
    now = time.time() if now is None else now
    check_redirect(redirect_uri, allowlist)

    verifier = new_verifier()
    state = new_state()
    tx = Transaction(
        state=state, verifier=verifier, redirect_uri=redirect_uri,
        provider=config.name, session_id=session_id,
        created_at=now, expires_at=now + ttl,
    )
    store.put(tx)

    params = {
        "client_id": credentials.client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "state": state,
        "code_challenge": challenge_for(verifier),
        "code_challenge_method": CHALLENGE_METHOD,
    }
    chosen_scope = config.scope if scope is None else scope
    if chosen_scope:
        params["scope"] = chosen_scope
    params.update(dict(config.extra_authorize_params))
    url = f"{config.authorize_url}?{urllib.parse.urlencode(params)}"
    return Authorization(url=url, state=state, transaction=tx)


# --------------------------------------------------------------------------
# leg two: exchange


def finish(
    config: ProviderConfig,
    credentials: Credentials,
    *,
    code: str,
    state: str,
    session_id: str,
    store: TransactionStore,
    now: float | None = None,
    poster=post_form,
) -> tuple[TokenSet, Transaction]:
    """Validate the callback and exchange the code. Raises on any mismatch."""
    now = time.time() if now is None else now
    tx = store.take(state)
    # One message for four different failures, on purpose - see StateMismatch.
    if tx is None or tx.expired(now) or tx.session_id != session_id \
            or tx.provider != config.name:
        raise StateMismatch("no in-flight authorization matches this callback")

    form = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": tx.redirect_uri,
        "client_id": credentials.client_id,
        "code_verifier": tx.verifier,
    }
    try:
        payload = poster(config.token_url, form, _auth_headers(config, credentials, form))
    except Disconnected:
        # `invalid_grant` means something different on each leg. Here it is a
        # bad, expired or already-redeemed authorization code - the user is not
        # disconnected, they never got connected - so it must not surface as a
        # "reconnect your account" prompt for a connection that has no row yet.
        raise OAuthError("the authorization code was rejected; start again") from None
    return _parse_token_response(payload, now), tx


def _auth_headers(config: ProviderConfig, credentials: Credentials, form: dict) -> dict:
    """Attach client credentials the way this provider wants them.

    `form` is mutated for the body style. The Basic style is preferred where a
    provider supports it: a secret in an `Authorization` header is at least
    conventionally scrubbed by proxies and log formatters, whereas one in a
    form body is just bytes nobody has taught anything to redact.
    """
    if config.auth_style == "basic":
        raw = f"{credentials.client_id}:{credentials.client_secret}".encode()
        return {"Authorization": "Basic " + base64.b64encode(raw).decode()}
    form["client_id"] = credentials.client_id
    if credentials.client_secret:
        form["client_secret"] = credentials.client_secret
    return {}


# --------------------------------------------------------------------------
# refresh, rotation, reuse detection


def refresh(
    config: ProviderConfig,
    credentials: Credentials,
    store,
    *,
    user_id: str,
    provider: str | None = None,
    presented: str | None = None,
    now: float | None = None,
    poster=post_form,
) -> TokenSet:
    """Refresh an access token, rotating the refresh token and catching reuse.

    Rotation on its own is only half a control. If the provider hands back a new
    refresh token each time and we simply overwrite ours, a stolen copy still
    works exactly once - and after it does, the legitimate client's next refresh
    fails, which looks like a bug and gets "fixed" by asking the user to
    reconnect. The theft is never noticed.

    So every retired token's fingerprint is kept. Presenting one is not a
    recoverable error and is not retried: exactly one of two parties holds a
    token we already retired, we cannot tell which, and the honest conclusion is
    that the family is compromised. The whole family is revoked, both parties
    lose access, and the real user re-links. That is the intended blast radius -
    an attacker gets one refresh cycle and a forced, visible disconnection,
    instead of silent permanent access.

    `presented` exists for the case where a token arrives from outside - a
    replay, a stale copy from another process - rather than being read from our
    own row. Omitted, the stored current token is used.
    """
    now = time.time() if now is None else now
    provider = provider or config.name

    conn = store.load(user_id, provider)
    if conn is None:
        raise Disconnected(f"no {provider} connection for this user")
    if conn.revoked:
        raise FamilyCompromised(
            f"{provider} connection was revoked ({conn.revoked_reason or 'unknown'}); "
            "the user must link again")

    token = presented if presented is not None else store.reveal_refresh_token(conn)
    fp = token_fingerprint(token)

    if fp != conn.refresh_fingerprint:
        # Either a fingerprint we retired (a genuine replay) or one we have
        # never seen (a forgery, or a row from a restored backup). Both mean
        # somebody holds a token for this family that is not the current one.
        reason = "refresh token reuse" if store.is_spent(conn.family_id, fp) \
            else "unrecognised refresh token"
        store.revoke_family(conn.family_id, reason)
        raise FamilyCompromised(
            f"{reason} detected for {provider}; the connection has been revoked "
            "and the user must link again")

    form = {"grant_type": "refresh_token", "refresh_token": token,
            "redirect_uri": conn.redirect_uri or "", "client_id": credentials.client_id}
    if not form["redirect_uri"]:
        del form["redirect_uri"]
    try:
        payload = poster(config.token_url, form, _auth_headers(config, credentials, form))
    except Disconnected:
        # invalid_grant. The user revoked us, or the token aged out. Mark it and
        # re-raise: this is a re-link prompt, never a 500. See Disconnected.
        store.mark_disconnected(conn)
        raise

    tokens = _parse_token_response(payload, now)
    if tokens.refresh_token and tokens.refresh_token != token:
        store.rotate(conn, tokens.refresh_token, spent_fingerprint=fp, now=now)
    return tokens


# --------------------------------------------------------------------------
# RFC 8252 loopback listener, for the CLI


CALLBACK_PAGE = (
    "<!doctype html><meta charset=utf-8><title>fantasy-edge</title>"
    "<style>body{font:16px/1.6 system-ui;margin:4rem auto;max-width:32rem;"
    "color:#111}</style><h1>{heading}</h1><p>{body}</p>"
)


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    server_version = "fantasy-edge"

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler's spelling
        parsed = urllib.parse.urlparse(self.path)
        listener: LoopbackListener = self.server.listener  # type: ignore[attr-defined]
        if parsed.path != listener.path:
            self.send_error(404)
            return
        q = urllib.parse.parse_qs(parsed.query)
        listener._deliver({k: v[0] for k, v in q.items()})
        ok = "code" in q and "error" not in q
        heading = "Connected." if ok else "Authorization failed."
        body = ("You can close this tab and return to the terminal."
                if ok else "Nothing was saved. Return to the terminal and try again.")
        # The page never echoes the code or the state. A browser renders this
        # from a URL that is already in history and possibly in a screen
        # recording; repeating the code in the body would put it somewhere else
        # again for no benefit.
        page = CALLBACK_PAGE.replace("{heading}", heading).replace("{body}", body)
        raw = page.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, fmt, *args) -> None:
        """Silence. The default handler logs the request line, and the request
        line is the callback URL, which carries the authorization code."""


class LoopbackListener:
    """Catch the redirect on `http://127.0.0.1:<random>/callback` (RFC 8252).

    The alternative, which is what this repo does today, is to register an
    https URL that serves nothing and have the user copy the code out of the
    address bar. That works and stays as the headless fallback, but it puts a
    live authorization code on a clipboard and usually into a chat window.

    Port zero, chosen by the kernel, is deliberate: a fixed port is squattable
    by any other process on the machine, which would let it receive the code.
    RFC 8252 §7.3 requires authorization servers to allow a variable port for
    loopback for exactly this reason. Note that not every provider honours it -
    Yahoo's app registration currently insists on an https redirect URI - so
    this is opt-in rather than the default.
    """

    def __init__(self, path: str = "/callback", host: str = "127.0.0.1") -> None:
        self.path = path
        self.host = host
        self._result: dict | None = None
        self._got = threading.Event()
        self._httpd = http.server.HTTPServer((host, 0), _CallbackHandler)
        self._httpd.listener = self  # type: ignore[attr-defined]
        self.port = self._httpd.server_address[1]
        self._thread = threading.Thread(target=self._httpd.serve_forever,
                                        kwargs={"poll_interval": 0.05}, daemon=True)

    @property
    def redirect_uri(self) -> str:
        return f"http://{self.host}:{self.port}{self.path}"

    def __enter__(self) -> LoopbackListener:
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _deliver(self, params: dict) -> None:
        if self._result is None:
            self._result = params
            self._got.set()

    def wait(self, timeout: float = 300.0) -> dict:
        if not self._got.wait(timeout):
            raise OAuthError(f"no callback on {self.redirect_uri} within {timeout:.0f}s")
        return dict(self._result or {})

    def close(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()


def run_loopback_flow(
    config: ProviderConfig,
    credentials: Credentials,
    *,
    store: TransactionStore | None = None,
    session_id: str = "cli",
    timeout: float = 300.0,
    open_browser: bool = True,
    poster=post_form,
    printer=print,
) -> TokenSet:
    """Whole flow in one call, for an interactive terminal.

    Binds the listener first so the concrete random-port redirect URI can go
    into the allowlist *and* the authorize request as the same exact string;
    the provider will compare them byte for byte and so do we.
    """
    store = store or MemoryTransactionStore()
    with LoopbackListener() as listener:
        redirect_uri = listener.redirect_uri
        auth = begin(config, credentials, redirect_uri=redirect_uri,
                     allowlist=(redirect_uri,), session_id=session_id, store=store)
        printer(f"Opening your browser to approve {config.name}.\n"
                f"If it does not open, visit:\n\n  {auth.url}\n")
        if open_browser:
            try:
                webbrowser.open(auth.url)
            except Exception:  # pragma: no cover - platform dependent
                pass
        params = listener.wait(timeout)

    if params.get("error"):
        raise OAuthError(f"authorization denied: {params['error']}")
    if "code" not in params:
        raise OAuthError("callback carried no authorization code")
    tokens, _tx = finish(config, credentials, code=params["code"],
                         state=params.get("state", ""), session_id=session_id,
                         store=store, poster=poster)
    return tokens
