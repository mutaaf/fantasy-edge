"""A model, if you bring one, and nothing at all if you do not.

`intel.py` computes the findings. This narrates them. The split is the whole
design: a model here is a writer, never a source. It is handed the numbers
`intel` computed, told in the system prompt that it may not introduce any
others, and its output is checked against those numbers afterwards - because a
prompt is a request and a check is a guarantee. Anything it writes comes back
in a `Narration`, which is a different type from an `Insight`, lands under a
different key in the payload, and reports `origin == "model"` from a property
no caller can overwrite.

Three providers over stdlib HTTPS - OpenAI, Anthropic, Google - because every
one of them is a JSON POST and `urllib.request` is a sufficient client. Adding
`openai` and `anthropic` and `google-generativeai` to run three functions
would triple the install and buy nothing this file does not already do.

A fourth "provider" is `SuppliedClient`, which performs no I/O and simply
returns text produced elsewhere. That is the seam for Apple Intelligence: a
Swift client runs `FoundationModels` on-device, posts the resulting prose back
through the same call, and it flows through the same verification and the same
labelling as a cloud model's. See `docs/intel.md`.

**On keys.** They come from the environment or from `~/.fantasy-edge/ai.json`,
mode 600, outside the working tree, exactly like every other credential in
this project. They are never written into the repository, never put in a URL,
never logged, and never returned in a payload. Two specific precautions are
worth naming because they are the ones that get skipped:

  * Google's API accepts `?key=` in the query string, and that is how every
    example writes it. A `urllib.error.HTTPError` stringifies to include the
    URL, so one 429 would print the key into a traceback, a log line, and any
    error the API handed back to a browser. This module sends `x-goog-api-key`
    as a header instead, for that reason alone.
  * Every error string that leaves this module goes through `redact` with the
    key as a needle, so even a provider that echoes the credential back in its
    own error body cannot carry it out through an exception message.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from . import intel

KEY_DIR = pathlib.Path.home() / ".fantasy-edge"
KEY_FILE = KEY_DIR / "ai.json"

# Model identifiers move faster than this file will. These are defaults, not
# claims about what is current: every one is overridable per call, by
# `FANTASYEDGE_AI_MODEL`, or per provider by the env var in the table. A model
# id the provider no longer serves comes back as a `rejected` state naming the
# override, rather than as a stack trace.
PROVIDERS: dict[str, dict[str, str]] = {
    "openai": {
        "label": "OpenAI",
        "env": "OPENAI_API_KEY",
        "model_env": "OPENAI_MODEL",
        "model": "gpt-4o-mini",
        "base": "https://api.openai.com",
    },
    "anthropic": {
        "label": "Anthropic",
        "env": "ANTHROPIC_API_KEY",
        "model_env": "ANTHROPIC_MODEL",
        "model": "claude-sonnet-4-5",
        "base": "https://api.anthropic.com",
    },
    "google": {
        "label": "Google",
        "env": "GOOGLE_API_KEY",
        "model_env": "GOOGLE_MODEL",
        "model": "gemini-2.0-flash",
        "base": "https://generativelanguage.googleapis.com",
    },
}

# Google publishes this one under a second name and a good half of the world's
# shell profiles use it. Reading both costs nothing and saves a support round.
ALT_ENV = {"google": ("GEMINI_API_KEY",)}

ANTHROPIC_VERSION = "2023-06-01"
USER_AGENT = "fantasy-edge/1.0 (personal league analytics)"
MAX_TOKENS = 700
TIMEOUT = 30


# ─────────────────────────────── error states ────────────────────────────────

class ModelError(RuntimeError):
    """A model call that did not produce prose.

    Every one of these is an ordinary state of the Intel view, not a crash:
    the computed brief is still the whole product, and the view is expected to
    render it with this message beside the empty narration slot. `state` is
    what a client switches on; `remedy` is what a person reads.
    """

    def __init__(self, state: str, message: str, remedy: str = "") -> None:
        super().__init__(message)
        self.state = state
        self.remedy = remedy

    def as_dict(self) -> dict:
        return {"state": self.state, "message": str(self), "remedy": self.remedy}


def redact(text: str, *secrets: str) -> str:
    """Blank any secret that made it into a string, plus anything key-shaped.

    Two passes on purpose. The first removes the keys we know about. The second
    catches the ones we do not - a provider quoting a different credential back
    at us in an error body, or a user who put a second key in a prompt - by
    shape, because a long opaque token in an error message is never something
    a reader needs and is sometimes something they must not see.
    """
    out = str(text or "")
    for s in secrets:
        if s and len(s) >= 8:
            out = out.replace(s, "[redacted]")
    out = re.sub(r"\b(sk|sk-proj|sk-ant|sk-ant-api\d*|AIza|gsk|xai)"
                 r"[-_A-Za-z0-9]{12,}\b", "[redacted]", out)
    # Google's own docs put the key in the query string, so even though this
    # module never does, an error quoting a caller-built URL still might.
    out = re.sub(r"([?&](?:key|api_key|access_token)=)[^&\s\"']+",
                 r"\1[redacted]", out)
    return out


# ──────────────────────────────── key lookup ─────────────────────────────────

def _file_keys() -> dict[str, str]:
    try:
        data = json.loads(KEY_FILE.read_text())
    except (OSError, ValueError):
        return {}
    return {str(k).lower(): str(v) for k, v in data.items()
            if isinstance(v, str) and v.strip()}


def load_key(provider: str) -> str:
    """The key for one provider: environment first, then the home file.

    Environment first because that is where a key lives for one shell session
    and nowhere else, which is the safest place it can be.
    """
    spec = PROVIDERS.get(provider)
    if not spec:
        return ""
    for name in (spec["env"], *ALT_ENV.get(provider, ())):
        v = (os.environ.get(name) or "").strip()
        if v:
            return v
    return (_file_keys().get(provider) or "").strip()


def remember_key(provider: str, key: str) -> pathlib.Path:
    """Write a key to `~/.fantasy-edge/ai.json`, mode 600, outside the repo.

    Offered because the alternative a user reaches for is a `.env` in the
    working tree, which one `git add .` turns into a published credential.
    Nothing in the read path calls this; it exists so that when a key is
    persisted at all it is persisted somewhere survivable.
    """
    if provider not in PROVIDERS:
        raise ModelError("unknown_provider", f"No provider named {provider!r}.",
                         f"one of: {', '.join(sorted(PROVIDERS))}")
    doc = _file_keys()
    doc[provider] = key.strip()
    KEY_DIR.mkdir(parents=True, exist_ok=True)
    KEY_FILE.write_text(json.dumps(doc, indent=2))
    KEY_FILE.chmod(0o600)
    return KEY_FILE


def available() -> list[dict]:
    """Which providers are configured, said without echoing anything.

    `configured` is a boolean and there is no field that could carry the key
    itself. A "show me my key so I can check it" affordance is how keys end up
    in screenshots and support threads; the useful question is only ever
    whether one is present, and a rejected one answers itself on first use.
    """
    return [{"provider": name, "label": spec["label"],
             "configured": bool(load_key(name)),
             "env": spec["env"],
             "model": os.environ.get("FANTASYEDGE_AI_MODEL")
                      or os.environ.get(spec["model_env"]) or spec["model"]}
            for name, spec in sorted(PROVIDERS.items())] + [
        {"provider": "apple", "label": "Apple Intelligence",
         "configured": False, "env": "",
         "model": "on-device, supplied by the Swift client"}]


# ───────────────────────────────── transport ─────────────────────────────────

def _post(url: str, headers: dict, body: dict, key: str,
          timeout: int = TIMEOUT) -> dict:
    """One JSON POST, with every failure mapped to a state a person can read.

    No retry. A rate limit answered by an immediate second request is how a
    rate limit becomes a ban, and the caller here is a person pressing a
    button, not a backfill: telling them to wait is both more honest and more
    effective than hiding three attempts behind a spinner.
    """
    payload = json.dumps(body).encode("utf-8")
    hdrs = {"Content-Type": "application/json", "Accept": "application/json",
            "User-Agent": USER_AGENT, **headers}
    req = urllib.request.Request(url, data=payload, headers=hdrs, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", "replace")[:400]
        except Exception:
            detail = ""
        finally:
            # An HTTPError is an open response. Left to the garbage collector
            # it emits a ResourceWarning from wherever the collection happens,
            # which in a test suite means an unrelated file gets blamed.
            exc.close()
        detail = redact(detail, key)
        if exc.code in (401, 403):
            # The provider's own words are worth carrying - "expired" and
            # "no access to this model" need different fixes - but a 401 body
            # is exactly where a provider quotes the credential back at you,
            # so it only travels having been through `redact`.
            raise ModelError(
                "rejected",
                f"The provider rejected the key ({exc.code}). {detail}".strip(),
                "Check the key is current and has access to this model, then "
                "set it again in the environment.") from None
        if exc.code == 429:
            raise ModelError(
                "rate_limited",
                "The provider is rate limiting this key (429).",
                "Wait a minute and try again. The computed brief below needs "
                "no model and is already complete.") from None
        if exc.code == 404:
            raise ModelError(
                "rejected",
                f"The provider does not serve this model (404). {detail}",
                "Model names change. Override with FANTASYEDGE_AI_MODEL.") from None
        if 500 <= exc.code < 600:
            raise ModelError(
                "unavailable",
                f"The provider is having trouble ({exc.code}).",
                "Try again shortly.") from None
        raise ModelError("failed", f"{exc.code} from the provider. {detail}",
                         "") from None
    except urllib.error.URLError as exc:
        raise ModelError("unreachable",
                         f"Could not reach the provider: "
                         f"{redact(exc.reason, key)}",
                         "Check the network. Nothing else on this page needs "
                         "one.") from None
    try:
        data = json.loads(raw)
    except ValueError:
        raise ModelError("malformed",
                         "The provider returned something that is not JSON.",
                         "This is usually a proxy or a captive portal "
                         "answering instead of the API.") from None
    if not isinstance(data, dict):
        raise ModelError("malformed",
                         "The provider returned JSON that is not an object.",
                         "")
    return data


# ───────────────────────────────── clients ───────────────────────────────────

class Client:
    """One model, reachable. Subclasses differ only in URL, headers and shape."""

    provider = "base"

    def __init__(self, key: str = "", model: str = "", base: str = "") -> None:
        spec = PROVIDERS.get(self.provider, {})
        self.key = key or load_key(self.provider)
        self.model = (model or os.environ.get("FANTASYEDGE_AI_MODEL")
                      or os.environ.get(spec.get("model_env", "") or "_")
                      or spec.get("model", ""))
        # `base` is the injection point tests use to aim this at a local stub.
        # It is not a user-facing setting: pointing a key at an arbitrary host
        # is how a key ends up somewhere it was not meant to go.
        self.base = (base or spec.get("base", "")).rstrip("/")

    def require_key(self) -> str:
        if not self.key:
            spec = PROVIDERS.get(self.provider, {})
            raise ModelError(
                "no_key",
                f"No {spec.get('label', self.provider)} key is set.",
                f"export {spec.get('env', 'API_KEY')}=... , or put it in "
                f"{KEY_FILE} (mode 600). Everything above this line was "
                f"computed without one and does not need one.")
        return self.key

    def complete(self, system: str, user: str) -> str:
        raise NotImplementedError


class OpenAIClient(Client):
    provider = "openai"

    def complete(self, system: str, user: str) -> str:
        key = self.require_key()
        data = _post(
            f"{self.base}/v1/chat/completions",
            {"Authorization": f"Bearer {key}"},
            {"model": self.model,
             "messages": [{"role": "system", "content": system},
                          {"role": "user", "content": user}],
             "max_completion_tokens": MAX_TOKENS},
            key)
        try:
            return str(data["choices"][0]["message"]["content"] or "")
        except (KeyError, IndexError, TypeError):
            raise ModelError("malformed",
                             "The response had no message content in it.",
                             "") from None


class AnthropicClient(Client):
    provider = "anthropic"

    def complete(self, system: str, user: str) -> str:
        key = self.require_key()
        data = _post(
            f"{self.base}/v1/messages",
            {"x-api-key": key, "anthropic-version": ANTHROPIC_VERSION},
            {"model": self.model, "max_tokens": MAX_TOKENS, "system": system,
             "messages": [{"role": "user", "content": user}]},
            key)
        try:
            parts = [b.get("text", "") for b in data["content"]
                     if b.get("type") == "text"]
        except (KeyError, TypeError, AttributeError):
            raise ModelError("malformed",
                             "The response had no content blocks in it.",
                             "") from None
        if not any(parts):
            raise ModelError("malformed",
                             "The response carried no text.", "")
        return "".join(parts)


class GoogleClient(Client):
    provider = "google"

    def complete(self, system: str, user: str) -> str:
        key = self.require_key()
        # Header, not `?key=`. See the module docstring: an HTTPError prints
        # its URL, so a key in the query string is a key in the traceback.
        data = _post(
            f"{self.base}/v1beta/models/{self.model}:generateContent",
            {"x-goog-api-key": key},
            {"systemInstruction": {"parts": [{"text": system}]},
             "contents": [{"role": "user", "parts": [{"text": user}]}],
             "generationConfig": {"maxOutputTokens": MAX_TOKENS}},
            key)
        try:
            parts = data["candidates"][0]["content"]["parts"]
            text = "".join(str(p.get("text", "")) for p in parts)
        except (KeyError, IndexError, TypeError):
            raise ModelError("malformed",
                             "The response had no candidate text in it.",
                             "") from None
        if not text:
            raise ModelError("malformed", "The response carried no text.", "")
        return text


class SuppliedClient(Client):
    """Prose produced somewhere this process cannot call.

    Apple Intelligence runs on device through `FoundationModels`, which is
    Swift-only: there is no way to invoke it from here and no HTTP endpoint in
    front of it. Rather than pretend, this client accepts finished text and
    submits it to exactly the same verification, labelling and payload slot a
    cloud model's output goes through. The Swift side gets no privileged path
    and no way to have its output mistaken for a computed fact.
    """

    provider = "apple"

    def __init__(self, text: str, model: str = "apple-foundation-models") -> None:
        self.key = ""
        self.model = model
        self.base = ""
        self.text = text

    def require_key(self) -> str:
        return ""

    def complete(self, system: str, user: str) -> str:
        if not (self.text or "").strip():
            raise ModelError("no_text",
                             "The client supplied no text.",
                             "An on-device run that produced nothing is a "
                             "failed run; the computed brief stands alone.")
        return self.text


CLIENTS: dict[str, type[Client]] = {
    "openai": OpenAIClient,
    "anthropic": AnthropicClient,
    "google": GoogleClient,
}


def client_for(provider: str, *, key: str = "", model: str = "",
               base: str = "") -> Client:
    cls = CLIENTS.get((provider or "").lower())
    if cls is None:
        raise ModelError("unknown_provider",
                         f"No model provider named {provider!r}.",
                         f"one of: {', '.join(sorted(CLIENTS))}, or supply "
                         f"text from a Swift client")
    return cls(key=key, model=model, base=base)


# ─────────────────────────────── the narration ───────────────────────────────

SYSTEM = """You are writing the top-of-page summary for a fantasy football \
console. You will be given a list of findings that were already computed from \
the user's own league database. Your job is to order them by what matters most \
this week and write them as prose.

Rules, in order of importance:
1. Do not introduce any number that is not in the findings you were given. Not \
a rank, not a percentage, not a projection, not a score, not a week number. If \
you want to say something that needs a number you do not have, say it without \
the number or leave it out.
2. Do not name a statistic that is not in the findings. In particular you do \
not have routes run, yards per route run, route participation, first read \
rate, or any route or target chart, and must not refer to them.
3. Do not contradict a caveat. If a finding says its number is an upper bound \
or a small sample, your sentence must not state it as settled.
4. No preamble, no sign-off, no headings, no lists. Three to five short \
sentences of continuous prose.
5. You are a narrator, not an analyst. Nothing you write is evidence."""


@dataclass
class Narration:
    """Model-written prose about findings somebody else computed.

    Deliberately not a subclass of, or a field on, `Insight`. The two are
    different kinds of claim and the payload should make that impossible to
    confuse - `origin` is a property here for the same reason it is one there.
    """

    text: str
    provider: str
    model: str
    grounded_in: list[str] = field(default_factory=list)
    unverified: list[str] = field(default_factory=list)
    flagged_metrics: list[str] = field(default_factory=list)
    error: dict | None = None

    @property
    def origin(self) -> str:
        return "model"

    @property
    def trustworthy(self) -> bool:
        """Whether the prose stayed inside the numbers it was given.

        False does not mean the text is wrong. It means at least one figure in
        it did not come from the brief, so the sentence containing it is not
        backed by anything on this page and the view should say so.
        """
        return not self.unverified and not self.flagged_metrics

    def as_dict(self) -> dict:
        return {
            "origin": self.origin, "text": self.text,
            "provider": self.provider, "model": self.model,
            "groundedIn": self.grounded_in,
            "unverified": self.unverified,
            "flaggedMetrics": self.flagged_metrics,
            "trustworthy": self.trustworthy,
            "label": "Written by a model from the computed findings below. "
                     "Not itself a source.",
            "error": self.error,
        }


NUMBER = re.compile(r"(?<![\w.])\d+(?:\.\d+)?")

# Numbers a sentence can carry without having been given one: ordinals and
# small counts a narrator uses as English rather than as data. Flagging "one of
# your starters" as an invented statistic is the kind of false positive that
# teaches a reader to ignore the flag entirely.
BENIGN = {"0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10"}


def verify_numbers(text: str, allowed: set[str]) -> list[str]:
    """Figures in the prose that were not in the brief.

    A prompt asking a model not to invent numbers is a request. This is the
    part that holds, and it is why `Narration.trustworthy` can be a boolean
    rather than a hope.
    """
    bad: list[str] = []
    for tok in NUMBER.findall(text or ""):
        norm = f"{float(tok):g}"
        if norm in allowed or tok in allowed or norm in BENIGN:
            continue
        if norm not in bad:
            bad.append(norm)
    return bad


#: How much prompt an on-device model can actually read. Apple's small model
#: has a few thousand tokens for the input and the output together, and a real
#: brief here is twenty-eight findings and twenty-two thousand characters -
#: past the window, so the request fails and the headset shows an apology
#: instead of a summary. A cloud model has room for all of it, so the cap is
#: opt-in rather than the default: `budget=None` keeps the whole brief.
ON_DEVICE_BUDGET = 8000


def prompt_for(brief: intel.Brief, *, budget: int | None = None) -> str:
    """The findings, as the only numbers a model is allowed to use.

    With a budget, findings are taken in the order the brief ranked them until
    the budget is spent, and the prompt says how many of how many it holds -
    so a model that can only read the first eight does not write as though it
    had seen all twenty-eight. Truncating silently would produce prose that
    reads complete and is not, which is worse than saying so.
    """
    facts = intel.as_prompt_facts(brief)
    if not facts:
        return ""
    head = ("Findings computed from the league database. Every number you may "
            "use is in here.")
    if budget is None:
        return head + "\n\n" + json.dumps(facts, indent=1)

    # Compact separators, because indentation is pure cost when the window is
    # the constraint - it is about a fifth of the payload and carries nothing.
    kept: list[dict] = []
    for fact in facts:
        trial = kept + [fact]
        body = json.dumps(trial, separators=(",", ":"))
        if kept and len(body) + len(head) > budget:
            break
        kept.append(fact)
    note = ""
    if len(kept) < len(facts):
        note = (f"\n\nThese are the {len(kept)} most important of "
                f"{len(facts)} findings; the rest are on screen beneath your "
                "summary. Do not imply this is all of them.")
    return head + note + "\n\n" + json.dumps(kept, separators=(",", ":"))


def narrate(brief: intel.Brief, client: Client | Any) -> Narration:
    """Ask a model to write the brief up, then check what it wrote.

    Never raises. A missing key, a rejected key and a rate limit are states of
    this view, not exceptions from it: the computed brief is already complete
    and the correct behaviour is to render it with a sentence explaining why
    there is no prose above it.
    """
    provider = getattr(client, "provider", "unknown")
    model = getattr(client, "model", "")
    grounded = [i.key for i in brief.insights]
    user = prompt_for(brief)
    if not user:
        return Narration(
            "", provider, model, grounded,
            error=ModelError("nothing_to_say",
                             "There are no computed findings to narrate.",
                             "Pull a season with rosters and a matchup.").as_dict())
    try:
        text = (client.complete(SYSTEM, user) or "").strip()
    except ModelError as exc:
        return Narration("", provider, model, grounded, error=exc.as_dict())
    except Exception as exc:                  # noqa: BLE001 - see redact below
        # A model call must not be able to take the page down, and whatever
        # went wrong may be carrying the key in its message.
        key = getattr(client, "key", "")
        return Narration("", provider, model, grounded,
                         error=ModelError("failed",
                                          redact(str(exc), key), "").as_dict())
    if not text:
        return Narration("", provider, model, grounded,
                         error=ModelError("malformed",
                                          "The model returned empty text.",
                                          "").as_dict())
    key = getattr(client, "key", "")
    return Narration(
        # Belt and braces: a model that was somehow shown a key must not be
        # able to hand it back through this field.
        text=redact(text, key),
        provider=provider, model=model, grounded_in=grounded,
        unverified=verify_numbers(text, intel.allowed_numbers(brief)),
        flagged_metrics=intel.mentions_unavailable(text),
    )
