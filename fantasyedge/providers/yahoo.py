"""Yahoo Fantasy Sports adapter.

Harder than ESPN: three-legged OAuth2 against a registered app. Worth doing
once, because after the first authorization the refresh token keeps working
and you never touch a browser again.

The single most important decision here: game keys are discovered, never
hardcoded. Yahoo's NFL game key changes every season, and every integration
that ships a lookup table breaks silently the following September. Asking
`/users;use_login=1/games;game_keys=nfl/leagues` returns your real league
keys for every season you have played, in `{game_key}.l.{league_id}` form.

Setup, once:
    1. developer.yahoo.com/apps/create, Confidential Client, Fantasy Sports
       read permission. Yahoo's current form rejects the literal `oob`, so
       register an https URL you control and export it as YAHOO_REDIRECT_URI.
       The page never has to serve anything: after you approve, the code
       arrives as `?code=...` in the address bar and you copy it from there.
    2. export YAHOO_CLIENT_ID / YAHOO_CLIENT_SECRET
    3. python -m fantasyedge auth --provider yahoo, follow the prompt
    4. the refresh token lands in ~/.fantasy-edge/yahoo.json, chmod 600
"""

from __future__ import annotations

import base64
import json
import os
import pathlib
import time
import urllib.parse
import urllib.request

from ..models import (
    DraftPick, LeagueRef, Manager, Matchup, Player,
    RosterSlot, SeasonBundle, Standing, Transaction, dedupe_players,
)
from .base import AuthError, Http, Provider, ProviderError, register

API = "https://fantasysports.yahooapis.com/fantasy/v2"
AUTH = "https://api.login.yahoo.com/oauth2/request_auth"
TOKEN = "https://api.login.yahoo.com/oauth2/get_token"
TOKEN_PATH = pathlib.Path.home() / ".fantasy-edge" / "yahoo.json"
# Yahoo used to accept the out-of-band sentinel; new apps must register a real
# https URI. Whatever is registered must match on both legs of the exchange.
DEFAULT_REDIRECT = "oob"
BENCH_SLOTS = {"BN", "IR"}


class YahooAuth:
    """OAuth2 token lifecycle. Credentials live on disk, never in the repo."""

    def __init__(self, client_id: str | None = None, client_secret: str | None = None,
                 token_path: pathlib.Path = TOKEN_PATH,
                 redirect_uri: str | None = None):
        self.client_id = client_id or os.environ.get("YAHOO_CLIENT_ID", "")
        self.client_secret = client_secret or os.environ.get("YAHOO_CLIENT_SECRET", "")
        self.redirect_uri = redirect_uri or os.environ.get(
            "YAHOO_REDIRECT_URI", DEFAULT_REDIRECT)
        self.token_path = token_path
        self._tok: dict = {}
        if token_path.exists():
            self._tok = json.loads(token_path.read_text())

    def _basic(self) -> str:
        raw = f"{self.client_id}:{self.client_secret}".encode()
        return base64.b64encode(raw).decode()

    def authorize_url(self) -> str:
        # `scope` is not optional: without it Yahoo issues a token that refreshes
        # happily and then 401s `additional_authorization_required` on every
        # Fantasy call, because the consent screen was never asked to grant
        # Fantasy read. `fspt-r` is read-only; nothing here writes to a league.
        q = urllib.parse.urlencode({
            "client_id": self.client_id, "redirect_uri": self.redirect_uri,
            "response_type": "code", "language": "en-us", "scope": "fspt-r",
        })
        return f"{AUTH}?{q}"

    def _post(self, body: dict) -> dict:
        data = urllib.parse.urlencode(body).encode()
        req = urllib.request.Request(TOKEN, data=data, headers={
            "Authorization": f"Basic {self._basic()}",
            "Content-Type": "application/x-www-form-urlencoded",
        })
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                tok = json.loads(r.read().decode())
        except Exception as exc:
            raise AuthError(f"token exchange failed: {exc}") from exc
        tok["expires_at"] = time.time() + int(tok.get("expires_in", 3600)) - 60
        self._tok = tok
        self.token_path.parent.mkdir(parents=True, exist_ok=True)
        self.token_path.write_text(json.dumps(tok, indent=2))
        self.token_path.chmod(0o600)
        return tok

    def exchange(self, code: str) -> dict:
        return self._post({
            "client_id": self.client_id, "client_secret": self.client_secret,
            "redirect_uri": self.redirect_uri, "code": code,
            "grant_type": "authorization_code",
        })

    def access_token(self) -> str:
        if not self._tok:
            raise AuthError("no Yahoo token. run: python -m fantasyedge auth --provider yahoo")
        if self._tok.get("expires_at", 0) < time.time():
            self._post({
                "client_id": self.client_id, "client_secret": self.client_secret,
                "redirect_uri": self.redirect_uri, "grant_type": "refresh_token",
                "refresh_token": self._tok["refresh_token"],
            })
        return self._tok["access_token"]


def walk(node, key: str):
    """Yahoo's JSON is XML wearing a costume: numeric-keyed dicts, lists of
    single-key dicts, `count` sentinels. Rather than model that faithfully,
    walk it and yield every value stored under `key`."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k == key:
                yield v
            else:
                yield from walk(v, key)
    elif isinstance(node, list):
        for item in node:
            yield from walk(item, key)


def flatten(node) -> dict:
    """Collapse Yahoo's list-of-single-key-dicts into one flat dict."""
    out: dict = {}
    if isinstance(node, dict):
        for k, v in node.items():
            if isinstance(v, (dict, list)):
                out.update(flatten(v))
            else:
                out[k] = v
    elif isinstance(node, list):
        for item in node:
            if isinstance(item, (dict, list)):
                out.update(flatten(item))
    return out


@register
class YahooProvider(Provider):
    name = "yahoo"

    def __init__(self, auth: YahooAuth | None = None, http: Http | None = None):
        self.auth = auth or YahooAuth()
        self.http = http or Http()

    def _get(self, path: str) -> dict:
        return self.http.get_json(
            f"{API}/{path}",
            params={"format": "json"},
            headers={"Authorization": f"Bearer {self.auth.access_token()}"},
        )

    def discover(self) -> list[LeagueRef]:
        """Ask Yahoo which leagues exist rather than guessing game keys."""
        data = self._get("users;use_login=1/games;game_keys=nfl/leagues")
        refs: dict[str, LeagueRef] = {}
        seen: dict[str, set] = {}
        for lg in walk(data, "league"):
            f = flatten(lg)
            key = f.get("league_key")
            if not key or "league_id" not in f:
                continue
            lid = str(f["league_id"])
            season = int(f.get("season", 0) or 0)
            seen.setdefault(lid, set()).add(season)
            refs[lid] = LeagueRef("yahoo", lid, f.get("name", ""))
        return [
            LeagueRef("yahoo", lid, r.name, tuple(sorted(s for s in seen[lid] if s)))
            for lid, r in refs.items()
        ]

    def _league_key(self, league_id: str, season: int) -> str:
        for lg in walk(self._get("users;use_login=1/games;game_keys=nfl/leagues"), "league"):
            f = flatten(lg)
            if str(f.get("league_id")) == str(league_id) and int(f.get("season", 0)) == season:
                return f["league_key"]
        raise ProviderError(f"no Yahoo league {league_id} in {season}")

    def fetch_season(self, league_id: str, season: int) -> SeasonBundle:
        key = self._league_key(league_id, season)
        meta = flatten(self._get(f"league/{key}/settings"))

        bundle = SeasonBundle(
            provider="yahoo", league_id=str(league_id), season=season,
            league_name=meta.get("name", ""),
            team_count=int(meta.get("num_teams", 0) or 0),
            scoring=str(meta.get("scoring_type", "")),
        )

        for team in walk(self._get(f"league/{key}/standings"), "team"):
            f = flatten(team)
            tid = str(f.get("team_id", ""))
            if not tid:
                continue
            bundle.managers.append(Manager(tid, f.get("name", f"Team {tid}"),
                                           f.get("nickname", "")))
            bundle.standings.append(Standing(
                team_id=tid, rank=int(f.get("rank", 0) or 0),
                wins=int(f.get("wins", 0) or 0), losses=int(f.get("losses", 0) or 0),
                ties=int(f.get("ties", 0) or 0),
                points_for=float(f.get("points_for", 0) or 0),
                points_against=float(f.get("points_against", 0) or 0),
            ))

        teams_n = max(bundle.team_count, 1)
        for pick in walk(self._get(f"league/{key}/draftresults"), "draft_result"):
            f = flatten(pick)
            if "pick" not in f:
                continue
            overall = int(f["pick"])
            bundle.draft.append(DraftPick(
                overall=overall,
                round=int(f.get("round", (overall - 1) // teams_n + 1)),
                team_id=str(f.get("team_key", "")).split(".t.")[-1],
                player_id=str(f.get("player_key", "")).split(".p.")[-1],
                cost=float(f["cost"]) if f.get("cost") else None,
            ))

        weeks = int(meta.get("end_week", 17) or 17)
        for wk in range(1, weeks + 1):
            self._load_week(key, wk, bundle)
        self._load_transactions(key, bundle)
        bundle.players = dedupe_players(bundle.players)
        return bundle

    def _load_week(self, key: str, week: int, bundle: SeasonBundle) -> None:
        try:
            data = self._get(f"league/{key}/scoreboard;week={week}")
        except ProviderError:
            return
        for mu in walk(data, "matchup"):
            sides = []
            for team in walk(mu, "team"):
                f = flatten(team)
                tid = str(f.get("team_id", ""))
                pts = float(f.get("total", 0) or 0)
                if tid:
                    sides.append((tid, pts))
            if len(sides) == 2:
                (a, ap), (b, bp) = sides[0], sides[1]
                bundle.matchups.append(Matchup(week, a, b, ap, bp))
                bundle.matchups.append(Matchup(week, b, a, bp, ap))

        for tid in {m.team_id for m in bundle.matchups if m.week == week}:
            try:
                roster = self._get(f"team/{key}.t.{tid}/roster;week={week}/players/stats")
            except ProviderError:
                continue
            for pl in walk(roster, "player"):
                f = flatten(pl)
                pid = str(f.get("player_key", "")).split(".p.")[-1]
                if not pid:
                    continue
                slot = f.get("selected_position") or f.get("position") or "BN"
                bundle.players.append(Player(pid, f.get("full", f.get("name", pid)),
                                             f.get("position_type", ""), f.get("editorial_team_abbr", "")))
                bundle.rosters.append(RosterSlot(
                    week=week, team_id=tid, player_id=pid, slot=str(slot),
                    points=float(f.get("total", 0) or 0),
                    started=str(slot) not in BENCH_SLOTS,
                ))

    def _load_transactions(self, key: str, bundle: SeasonBundle) -> None:
        try:
            data = self._get(f"league/{key}/transactions")
        except ProviderError:
            return
        for t in walk(data, "transaction"):
            f = flatten(t)
            bundle.transactions.append(Transaction(
                week=0, team_id=str(f.get("destination_team_key", "")).split(".t.")[-1],
                player_id=str(f.get("player_key", "")).split(".p.")[-1],
                kind=str(f.get("transaction_type", f.get("type", ""))),
                source=str(f.get("source_type", "")),
            ))
