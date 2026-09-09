"""Provider port.

Adding a new source means writing one subclass and registering it. Nothing
else in the codebase changes. Ingestion, storage, analytics and reporting
all depend on this interface, never on a concrete provider.
"""

from __future__ import annotations

import abc
import json
import time
import urllib.error
import urllib.parse
import urllib.request

from ..models import LeagueRef, SeasonBundle

USER_AGENT = "fantasy-edge/1.0 (personal league analytics)"


class ProviderError(RuntimeError):
    """Anything that went wrong talking to a source."""


class AuthError(ProviderError):
    """Credentials are missing, wrong, or expired."""


class Http:
    """Tiny stdlib HTTP client.

    Deliberately not `requests`. This project has zero third-party
    dependencies so it runs on a bare Python install and cannot rot when
    an unrelated package upgrades.
    """

    def __init__(self, timeout: int = 20, retries: int = 3, backoff: float = 1.5):
        self.timeout = timeout
        self.retries = retries
        self.backoff = backoff

    def get_json(
        self,
        url: str,
        *,
        headers: dict | None = None,
        cookies: dict | None = None,
        params: dict | None = None,
    ):
        if params:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}{urllib.parse.urlencode(params)}"

        hdrs = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        hdrs.update(headers or {})
        if cookies:
            hdrs["Cookie"] = "; ".join(f"{k}={v}" for k, v in cookies.items())

        last: Exception | None = None
        for attempt in range(self.retries):
            try:
                req = urllib.request.Request(url, headers=hdrs)
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                if exc.code in (401, 403):
                    raise AuthError(
                        f"{exc.code} from {url}. Credentials are missing, wrong, "
                        f"or you were not in this league that season."
                    ) from exc
                if exc.code == 429 or 500 <= exc.code < 600:
                    last = exc
                    time.sleep(self.backoff ** attempt)
                    continue
                raise ProviderError(f"{exc.code} from {url}") from exc
            except urllib.error.URLError as exc:
                last = exc
                time.sleep(self.backoff ** attempt)
        raise ProviderError(f"giving up on {url}: {last}")


class Provider(abc.ABC):
    """One source of league data."""

    name: str = "base"

    @abc.abstractmethod
    def discover(self) -> list[LeagueRef]:
        """Leagues this credential can see, with the seasons available.

        Discovery matters more than it looks. Season identifiers drift
        (Yahoo's game key changes every year), and asking the API beats
        hardcoding a table that silently breaks each September.
        """

    @abc.abstractmethod
    def fetch_season(self, league_id: str, season: int) -> SeasonBundle:
        """Pull one league-season and return it normalized."""

    def fetch_many(self, league_id: str, seasons: list[int]) -> list[SeasonBundle]:
        out = []
        for s in seasons:
            try:
                out.append(self.fetch_season(league_id, s))
            except AuthError:
                raise
            except ProviderError as exc:
                # One bad season should not sink a ten-year backfill.
                print(f"  skip {season_label(s)}: {exc}")
        return out


def season_label(season: int) -> str:
    return f"{season}"


_REGISTRY: dict[str, type[Provider]] = {}


def register(cls: type[Provider]) -> type[Provider]:
    _REGISTRY[cls.name] = cls
    return cls


def get_provider(name: str, **kwargs) -> Provider:
    try:
        cls = _REGISTRY[name]
    except KeyError:
        raise ProviderError(
            f"unknown provider {name!r}. known: {', '.join(sorted(_REGISTRY))}"
        ) from None
    return cls(**kwargs)


def known_providers() -> list[str]:
    return sorted(_REGISTRY)
