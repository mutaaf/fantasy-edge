"""Sleeper adapter.

The easy one. Sleeper's read API is public: no cookie, no OAuth, no developer
app. A league id is the whole credential, which makes this the only provider a
non-technical user can set up in one step.

Three quirks this absorbs so nothing downstream has to care:

1. A Sleeper league is one season. Prior years hang off `previous_league_id`,
   so history means walking that chain rather than passing a season number.
2. Weekly rosters arrive as a `starters` list plus a `players` list, which is
   exactly the started flag the bench analysis needs, for free.
3. Player ids are Sleeper's own. `espn_id` is present for barely half the
   active pool and null for most stars, so joining ADP by id does not work.
   Matching on a normalised name plus position resolves 98% of a top-300
   board; see `PlayerBook`.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import time
import unicodedata

from .. import identity

from ..models import (
    DraftPick, LeagueRef, Manager, Matchup, Player, RosterSlot,
    SeasonBundle, Standing, Transaction, dedupe_players,
)
from .base import Http, Provider, ProviderError, register

API = "https://api.sleeper.app/v1"
CACHE = pathlib.Path.home() / ".fantasy-edge" / "sleeper_players.json"
CACHE_TTL = 24 * 3600          # the player file is 14MB and changes slowly

# Sleeper writes a defence as the team code; ESPN writes "Texans D/ST".
TEAM_CODE = {
    "Texans": "HOU", "Broncos": "DEN", "Rams": "LAR", "Seahawks": "SEA",
    "Steelers": "PIT", "Ravens": "BAL", "Eagles": "PHI", "Patriots": "NE",
    "Lions": "DET", "Browns": "CLE", "Chargers": "LAC", "Chiefs": "KC",
    "Cowboys": "DAL", "Jaguars": "JAX", "Vikings": "MIN", "Bills": "BUF",
    "49ers": "SF", "Packers": "GB", "Bears": "CHI", "Dolphins": "MIA",
    "Giants": "NYG", "Bengals": "CIN", "Commanders": "WAS", "Raiders": "LV",
    "Panthers": "CAR", "Cardinals": "ARI", "Titans": "TEN", "Saints": "NO",
    "Buccaneers": "TB", "Jets": "NYJ", "Colts": "IND", "Falcons": "ATL",
}
#: See `identity.fold`. This name is kept because the provider and its tests
#: use it; there is only one implementation now.
normalise = identity.fold


class PlayerBook:
    """The Sleeper player file, indexed for the joins this project needs."""

    def __init__(self, raw: dict):
        self.raw = raw
        self.by_name: dict[tuple[str, str], list[dict]] = {}
        self.by_name_only: dict[str, list[dict]] = {}
        for pid, p in raw.items():
            pos = p.get("position")
            if not pos:
                continue
            p = {**p, "player_id": pid}
            key = p.get("search_full_name") or normalise(
                p.get("full_name") or f"{p.get('first_name','')}{p.get('last_name','')}")
            if not key:
                continue
            self.by_name.setdefault((key, pos), []).append(p)
            self.by_name_only.setdefault(key, []).append(p)

    def lookup(self, name: str, pos: str) -> dict | None:
        """Resolve an outside name to a Sleeper player. Position breaks ties."""
        if pos == "DEF":
            code = TEAM_CODE.get((name or "").split()[0] if name else "")
            return {**self.raw[code], "player_id": code} if code in self.raw else None
        key = normalise(name)
        for cand in (self.by_name.get((key, pos)), self.by_name_only.get(key)):
            if cand:
                return cand[0]
        return None

    def name_of(self, pid: str) -> tuple[str, str, str]:
        p = self.raw.get(str(pid))
        if not p:
            return str(pid), "", ""
        if p.get("position") == "DEF" or not p.get("full_name"):
            team = p.get("team") or str(pid)
            return f"{team} D/ST", "DEF", team
        return p["full_name"], p.get("position", ""), p.get("team") or ""


@register
class SleeperProvider(Provider):
    name = "sleeper"

    def __init__(self, league_id: str | None = None, username: str | None = None,
                 http: Http | None = None, players: dict | None = None):
        self.league_id = league_id or os.environ.get("SLEEPER_LEAGUE_ID")
        self.username = username or os.environ.get("SLEEPER_USERNAME")
        self.http = http or Http()
        self._players = players
        self._book: PlayerBook | None = None

    # ---------- plumbing ----------

    def _get(self, path: str):
        try:
            return self.http.get_json(f"{API}/{path}")
        except Exception as exc:
            raise ProviderError(f"sleeper {path}: {exc}") from exc

    @property
    def players(self) -> dict:
        """The 14MB player file, cached on disk because it moves slowly."""
        if self._players is None:
            if CACHE.exists() and time.time() - CACHE.stat().st_mtime < CACHE_TTL:
                self._players = json.loads(CACHE.read_text())
            else:
                self._players = self._get("players/nfl")
                try:
                    CACHE.parent.mkdir(parents=True, exist_ok=True)
                    CACHE.write_text(json.dumps(self._players))
                except OSError:
                    pass                      # a cache miss is not worth failing on
        return self._players

    @property
    def book(self) -> PlayerBook:
        if self._book is None:
            self._book = PlayerBook(self.players)
        return self._book

    def _chain(self, league_id: str) -> list[dict]:
        """This league and every prior season it points back to."""
        out, seen, cur = [], set(), str(league_id)
        while cur and cur not in seen and cur != "0":
            seen.add(cur)
            lg = self._get(f"league/{cur}")
            if not lg:
                break
            out.append(lg)
            cur = str(lg.get("previous_league_id") or "")
        return out

    # ---------- interface ----------

    def discover(self) -> list[LeagueRef]:
        if self.username:
            user = self._get(f"user/{self.username}")
            if not user or not user.get("user_id"):
                raise ProviderError(f"no Sleeper user named {self.username!r}")
            season = self._get("state/nfl").get("season") or "2026"
            leagues = self._get(f"user/{user['user_id']}/leagues/nfl/{season}") or []
            return [LeagueRef("sleeper", str(l["league_id"]), l.get("name", ""),
                              tuple(sorted(int(x["season"]) for x in self._chain(l["league_id"]))))
                    for l in leagues]
        if not self.league_id:
            raise ProviderError(
                "set SLEEPER_LEAGUE_ID (the id in your league URL) or SLEEPER_USERNAME")
        chain = self._chain(self.league_id)
        return [LeagueRef("sleeper", str(self.league_id), chain[0].get("name", "") if chain else "",
                          tuple(sorted(int(l["season"]) for l in chain)))]

    def fetch_season(self, league_id: str, season: int) -> SeasonBundle:
        # A Sleeper league id is one season, so find the link for the year asked for.
        target = next((l for l in self._chain(league_id) if int(l["season"]) == int(season)), None)
        if target is None:
            raise ProviderError(f"season {season} is not in this league's history")
        lid = str(target["league_id"])

        rosters = self._get(f"league/{lid}/rosters") or []
        users = {u["user_id"]: u for u in (self._get(f"league/{lid}/users") or [])}
        slots = [s for s in (target.get("roster_positions") or []) if s != "BN"]

        bundle = SeasonBundle(
            provider="sleeper", league_id=str(league_id), season=int(season),
            league_name=target.get("name", ""), team_count=len(rosters),
            scoring=str((target.get("scoring_settings") or {}).get("rec", "")),
        )

        by_roster = {}
        for r in rosters:
            tid = str(r["roster_id"])
            by_roster[r["roster_id"]] = tid
            u = users.get(r.get("owner_id")) or {}
            team = ((u.get("metadata") or {}).get("team_name")
                    or u.get("display_name") or f"Team {tid}")
            bundle.managers.append(Manager(tid, team, str(r.get("owner_id") or "")))
            st = r.get("settings") or {}
            bundle.standings.append(Standing(
                team_id=tid, rank=int(st.get("rank") or 0),
                wins=int(st.get("wins") or 0), losses=int(st.get("losses") or 0),
                ties=int(st.get("ties") or 0),
                points_for=float(st.get("fpts") or 0) + float(st.get("fpts_decimal") or 0) / 100,
                points_against=float(st.get("fpts_against") or 0)
                + float(st.get("fpts_against_decimal") or 0) / 100,
            ))

        self._load_draft(lid, bundle, by_roster)
        self._load_weeks(lid, target, bundle, by_roster, slots)
        bundle.players = dedupe_players(bundle.players)
        return bundle

    def draft_state(self, league_id: str, season: int) -> dict:
        """Live board, for `serve` and `draft-watch`. One or two calls."""
        target = next((l for l in self._chain(league_id) if int(l["season"]) == int(season)), None)
        if target is None:
            raise ProviderError(f"season {season} is not in this league's history")
        drafts = self._get(f"league/{target['league_id']}/drafts") or []
        if not drafts:
            return {"drafted": False, "in_progress": False, "picks": []}
        draft = drafts[0]
        picks = self._get(f"draft/{draft['draft_id']}/picks") or []
        rows = []
        for p in picks:
            if not p.get("player_id"):
                continue
            name, pos, _ = self.book.name_of(p["player_id"])
            rows.append({
                "overall": int(p.get("pick_no") or 0),
                "round": int(p.get("round") or 0),
                "team_id": str(p.get("roster_id") or p.get("draft_slot") or ""),
                "team": "", "player_id": str(p["player_id"]), "name": name,
                "keeper": bool(p.get("is_keeper")),
            })
        rows.sort(key=lambda r: r["overall"])
        return {"drafted": draft.get("status") == "complete",
                "in_progress": draft.get("status") == "drafting", "picks": rows}

    # ---------- detail loaders ----------

    def _load_draft(self, lid: str, bundle: SeasonBundle, by_roster: dict) -> None:
        drafts = self._get(f"league/{lid}/drafts") or []
        if not drafts:
            return
        for p in self._get(f"draft/{drafts[0]['draft_id']}/picks") or []:
            if not p.get("player_id") or not p.get("pick_no"):
                continue
            bundle.draft.append(DraftPick(
                overall=int(p["pick_no"]), round=int(p.get("round") or 0),
                team_id=by_roster.get(p.get("roster_id"), str(p.get("draft_slot") or "")),
                player_id=str(p["player_id"]),
                cost=float(p["metadata"]["amount"])
                if (p.get("metadata") or {}).get("amount") else None,
            ))

    def _load_weeks(self, lid: str, league: dict, bundle: SeasonBundle,
                    by_roster: dict, slots: list[str]) -> None:
        """Matchups carry the starters list, which is the started flag for free."""
        settings = league.get("settings") or {}
        last = int(settings.get("playoff_week_start") or 15) + 3
        for week in range(1, min(last, 19)):
            try:
                rows = self._get(f"league/{lid}/matchups/{week}") or []
            except ProviderError:
                continue
            if not rows:
                continue

            pairs: dict[int, list[dict]] = {}
            for m in rows:
                if m.get("matchup_id") is not None:
                    pairs.setdefault(m["matchup_id"], []).append(m)
                self._roster_rows(bundle, week, m, by_roster, slots)
            for side in pairs.values():
                if len(side) != 2:
                    continue
                a, b = side
                ta, tb = by_roster.get(a["roster_id"]), by_roster.get(b["roster_id"])
                pa, pb = float(a.get("points") or 0), float(b.get("points") or 0)
                if ta and tb:
                    bundle.matchups.append(Matchup(week, ta, tb, pa, pb))
                    bundle.matchups.append(Matchup(week, tb, ta, pb, pa))

            self._load_transactions(lid, week, bundle, by_roster)

    def _roster_rows(self, bundle: SeasonBundle, week: int, m: dict,
                     by_roster: dict, slots: list[str]) -> None:
        tid = by_roster.get(m.get("roster_id"))
        if not tid:
            return
        starters = list(m.get("starters") or [])
        pts = m.get("players_points") or {}
        for pid in (m.get("players") or []):
            if not pid:
                continue
            name, pos, team = self.book.name_of(pid)
            bundle.players.append(Player(str(pid), name, pos, team))
            started = pid in starters
            slot = pos or "BN"
            if started:
                # Sleeper's starters list is positional: index i is slot i.
                i = starters.index(pid)
                slot = slots[i] if i < len(slots) else (pos or "FLEX")
            bundle.rosters.append(RosterSlot(
                week=week, team_id=tid, player_id=str(pid),
                slot=slot if started else "BN",
                points=float(pts.get(pid) or 0.0), projected=None, started=started,
            ))

    def _load_transactions(self, lid: str, week: int, bundle: SeasonBundle,
                           by_roster: dict) -> None:
        try:
            txns = self._get(f"league/{lid}/transactions/{week}") or []
        except ProviderError:
            return
        for t in txns:
            if t.get("status") != "complete":
                continue
            kind_src = t.get("type") or ""
            for pid, rid in (t.get("adds") or {}).items():
                tid = by_roster.get(rid)
                if tid:
                    bundle.transactions.append(
                        Transaction(week, tid, str(pid), "add", kind_src))
            for pid, rid in (t.get("drops") or {}).items():
                tid = by_roster.get(rid)
                if tid:
                    bundle.transactions.append(
                        Transaction(week, tid, str(pid), "drop", kind_src))
