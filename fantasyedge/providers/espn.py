"""ESPN Fantasy Football adapter.

Auth is two session cookies, `espn_s2` and `SWID`, copied from a signed-in
browser. No app registration, no OAuth. That makes ESPN roughly a twenty
minute integration against Yahoo's weekend.

Two quirks this adapter absorbs so nothing downstream has to care:

1. The pre-2018 `leagueHistory` endpoint returns JSON wrapped in a list of
   length one; the modern endpoint returns a bare object.
2. Since August 2025 ESPN restricted historical access that used to be
   open, so the cookie is required even for older seasons. For a private
   league you must also have been a member in that season; there is no way
   around that except a cookie from someone who was.
"""

from __future__ import annotations

import os

from ..models import (
    Adp, DraftPick, LeagueRef, Manager, Matchup, Player,
    RosterSlot, SeasonBundle, Standing, Transaction, dedupe_players,
)
from .base import AuthError, Http, Provider, ProviderError, register

HOST = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl"

# ESPN encodes positions and lineup slots as integers.
POS = {1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K", 16: "DEF"}
SLOT = {
    0: "QB", 2: "RB", 4: "WR", 6: "TE", 16: "DEF", 17: "K",
    20: "BN", 21: "IR", 23: "FLEX",
}
BENCH_SLOTS = {"BN", "IR"}
TXN_KIND = {178: "add", 179: "drop", 180: "add", 181: "drop", 239: "drop", 244: "trade"}


@register
class EspnProvider(Provider):
    name = "espn"

    def __init__(self, espn_s2: str | None = None, swid: str | None = None,
                 league_id: str | None = None, http: Http | None = None):
        self.espn_s2 = espn_s2 or os.environ.get("ESPN_S2")
        self.swid = swid or os.environ.get("ESPN_SWID")
        self.league_id = league_id or os.environ.get("ESPN_LEAGUE_ID")
        self.http = http or Http()

    # ---------- plumbing ----------

    @property
    def _cookies(self) -> dict:
        if not (self.espn_s2 and self.swid):
            return {}
        swid = self.swid if self.swid.startswith("{") else "{%s}" % self.swid
        return {"espn_s2": self.espn_s2, "SWID": swid}

    def _url(self, league_id: str, season: int) -> str:
        if season >= 2018:
            return f"{HOST}/seasons/{season}/segments/0/leagues/{league_id}"
        return f"{HOST}/leagueHistory/{league_id}"

    def _get(self, league_id: str, season: int, views: list[str],
             scoring_period: int | None = None) -> dict:
        params = [("view", v) for v in views]
        if scoring_period is not None:
            params.append(("scoringPeriodId", str(scoring_period)))
        if season < 2018:
            params.append(("seasonId", str(season)))
        url = self._url(league_id, season)
        qs = "&".join(f"{k}={v}" for k, v in params)
        data = self.http.get_json(f"{url}?{qs}", cookies=self._cookies)
        # Historical endpoint wraps the payload in a single-element list.
        if isinstance(data, list):
            if not data:
                raise ProviderError(f"empty payload for {league_id} {season}")
            data = data[0]
        return data

    # ---------- interface ----------

    def discover(self) -> list[LeagueRef]:
        if not self.league_id:
            raise ProviderError(
                "set ESPN_LEAGUE_ID (the leagueId in your ESPN league URL)"
            )
        current = self.http.get_json(f"{HOST}")
        latest = int(current.get("currentSeasonId", 2026))
        seasons = []
        for yr in range(latest, latest - 12, -1):
            try:
                self._get(self.league_id, yr, ["mSettings"])
                seasons.append(yr)
            except (ProviderError, AuthError):
                continue
        return [LeagueRef("espn", self.league_id, seasons=tuple(sorted(seasons)))]

    def draft_state(self, league_id: str, season: int) -> dict:
        """Just the draft board, cheap enough to poll while a draft is running.

        `fetch_season` pulls every week of every roster; this is one request.
        Names come back too, because a pick id on its own tells you nothing.
        """
        data = self._get(league_id, season, ["mDraftDetail", "mTeam"])
        detail = data.get("draftDetail") or {}
        teams = {}
        for t in data.get("teams", []) or []:
            teams[t.get("id")] = t.get("name") or " ".join(
                filter(None, [t.get("location"), t.get("nickname")])
            ).strip() or f"Team {t.get('id')}"

        picks = []
        for pick in detail.get("picks", []) or []:
            overall = int(pick.get("overallPickNumber") or 0)
            # An unstarted draft returns a full slate of empty slots carrying
            # playerId -1. Negative ids in general are NOT empty: ESPN encodes
            # team defences that way, so -16014 is a real pick.
            pid = int(pick.get("playerId") or 0)
            if not overall or pid in (0, -1):
                continue
            picks.append({
                "overall": overall,
                "round": int(pick.get("roundId") or 0),
                "team_id": str(pick.get("teamId")),
                "team": teams.get(pick.get("teamId"), str(pick.get("teamId"))),
                "player_id": str(pick.get("playerId")),
                "keeper": bool(pick.get("keeper")),
            })
        picks.sort(key=lambda p: p["overall"])
        return {"drafted": bool(detail.get("drafted")),
                "in_progress": bool(detail.get("inProgress")),
                "picks": picks}

    def fetch_season(self, league_id: str, season: int) -> SeasonBundle:
        meta = self._get(league_id, season, ["mSettings", "mTeam", "mDraftDetail"])
        settings = meta.get("settings", {}) or {}

        bundle = SeasonBundle(
            provider="espn",
            league_id=str(league_id),
            season=season,
            league_name=settings.get("name", ""),
            team_count=len(meta.get("teams", []) or []),
            scoring=str((settings.get("scoringSettings") or {}).get("scoringType", "")),
        )

        id_to_team: dict[int, str] = {}
        for t in meta.get("teams", []) or []:
            tid = str(t.get("id"))
            id_to_team[t.get("id")] = tid
            name = t.get("name") or " ".join(
                filter(None, [t.get("location"), t.get("nickname")])
            ).strip()
            owners = t.get("owners") or []
            bundle.managers.append(Manager(tid, name or f"Team {tid}", str(owners[0]) if owners else ""))
            rec = ((t.get("record") or {}).get("overall") or {})
            bundle.standings.append(Standing(
                team_id=tid,
                rank=int(t.get("playoffSeed") or t.get("rankCalculatedFinal") or 0),
                wins=int(rec.get("wins") or 0),
                losses=int(rec.get("losses") or 0),
                ties=int(rec.get("ties") or 0),
                points_for=float(rec.get("pointsFor") or 0.0),
                points_against=float(rec.get("pointsAgainst") or 0.0),
            ))

        teams_n = max(bundle.team_count, 1)
        for pick in (meta.get("draftDetail") or {}).get("picks", []) or []:
            overall = int(pick.get("overallPickNumber") or 0)
            # An undrafted season still returns a full slate of empty slots
            # carrying playerId -1. Storing those invents a draft that never
            # happened. Negative ids in general are real: team defences.
            if not overall or int(pick.get("playerId") or 0) in (0, -1):
                continue
            bundle.draft.append(DraftPick(
                overall=overall,
                round=int(pick.get("roundId") or ((overall - 1) // teams_n + 1)),
                team_id=str(pick.get("teamId")),
                player_id=str(pick.get("playerId")),
                cost=float(pick["bidAmount"]) if pick.get("bidAmount") else None,
            ))

        self._load_weeks(league_id, season, bundle)
        bundle.players = dedupe_players(bundle.players)
        return bundle

    # ---------- detail loaders ----------

    def _weeks(self, data: dict) -> list[int]:
        """Scoring periods worth fetching.

        Prefers the league status; falls back to the periods the schedule
        actually mentions, which is what pre-2018 payloads carry.
        """
        status = data.get("status") or {}
        final = int(status.get("finalScoringPeriod") or 0)
        latest = int(status.get("latestScoringPeriod") or 0)
        if final:
            return list(range(1, max(min(final, latest or final), 1) + 1))
        weeks = {int(m.get("matchupPeriodId") or 0)
                 for m in data.get("schedule") or []}
        weeks.discard(0)
        return sorted(weeks) or [1]

    def _load_weeks(self, league_id: str, season: int, bundle: SeasonBundle) -> None:
        """Matchup results come season-wide; rosters do not.

        ESPN only fills `rosterForCurrentScoringPeriod` for the scoring
        period named in the query string. Ask without one and a finished
        season hands back every matchup with an empty roster - no error, no
        warning. That silently costs the started flag, and with it the
        bench-leak analysis, the player table, and every analysis that needs
        a position. So rosters are fetched one period at a time.
        """
        try:
            data = self._get(league_id, season, ["mMatchupScore", "mMatchup"])
        except ProviderError:
            return

        for m in data.get("schedule", []) or []:
            week = int(m.get("matchupPeriodId") or 0)
            home, away = m.get("home") or {}, m.get("away") or {}
            if not home or not away:
                continue
            h_id, a_id = str(home.get("teamId")), str(away.get("teamId"))
            h_pts = float(home.get("totalPoints") or 0.0)
            a_pts = float(away.get("totalPoints") or 0.0)
            bundle.matchups.append(Matchup(week, h_id, a_id, h_pts, a_pts))
            bundle.matchups.append(Matchup(week, a_id, h_id, a_pts, h_pts))

        for week in self._weeks(data):
            self._load_week(league_id, season, bundle, week)

    def _load_week(self, league_id: str, season: int,
                   bundle: SeasonBundle, week: int) -> None:
        """Rosters and transactions for one scoring period.

        Both views are period-scoped, so they ride along in one request.
        """
        try:
            data = self._get(
                league_id, season,
                ["mMatchupScore", "mRoster", "mMatchup", "mTransactions2"],
                scoring_period=week,
            )
        except ProviderError:
            return

        for m in data.get("schedule", []) or []:
            if int(m.get("matchupPeriodId") or 0) != week:
                continue
            for side in (m.get("home") or {}, m.get("away") or {}):
                if not side:
                    continue
                tid = str(side.get("teamId"))
                entries = ((side.get("rosterForCurrentScoringPeriod") or {})
                           .get("entries") or [])
                for e in entries:
                    self._roster_row(bundle, week, tid, e)

        for t in data.get("transactions", []) or []:
            # The live API already scopes these to the period. The filter
            # stops a whole-season payload from multiplying every
            # transaction by the number of weeks we ask for.
            if int(t.get("scoringPeriodId") or 0) != week:
                continue
            tid = str(t.get("teamId"))
            for item in t.get("items", []) or []:
                kind = TXN_KIND.get(item.get("type"), str(item.get("type", "")))
                bundle.transactions.append(Transaction(
                    week=week, team_id=tid,
                    player_id=str(item.get("playerId")),
                    kind=kind,
                    source=str(t.get("type", "")),
                ))

    def _roster_row(self, bundle: SeasonBundle, week: int, tid: str, entry: dict) -> None:
        pid = str(entry.get("playerId"))
        pool = (entry.get("playerPoolEntry") or {})
        p = pool.get("player") or {}
        slot = SLOT.get(entry.get("lineupSlotId"), "BN")
        pos = POS.get(p.get("defaultPositionId"), "")

        actual = projected = None
        for st in p.get("stats", []) or []:
            if int(st.get("scoringPeriodId") or -1) != week:
                continue
            if st.get("statSourceId") == 0:
                actual = float(st.get("appliedTotal") or 0.0)
            elif st.get("statSourceId") == 1:
                projected = float(st.get("appliedTotal") or 0.0)

        bundle.players.append(Player(pid, p.get("fullName", pid), pos,
                                     str(p.get("proTeamId", ""))))
        bundle.rosters.append(RosterSlot(
            week=week, team_id=tid, player_id=pid, slot=slot,
            points=float(actual if actual is not None else pool.get("appliedStatTotal") or 0.0),
            projected=projected,
            started=slot not in BENCH_SLOTS,
        ))
