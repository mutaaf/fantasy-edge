"""Manual adapter: paste-and-parse.

The escape hatch. If OAuth is broken, cookies expired, or you simply want
one season loaded in ninety seconds, paste the draft results page and the
standings page into text files and this reads them.

Deliberately forgiving about format. Yahoo, ESPN and Sleeper all copy out
slightly differently, so the parser works on regex shapes rather than
column positions.

Draft lines it accepts:
    1. (1.01) Jahmyr Gibbs RB DET - Team Name
    1  Jahmyr Gibbs  RB  DET  Team Name
    Round 1 Pick 1  Jahmyr Gibbs (DET - RB)  Team Name

Standings lines it accepts:
    1  Team Name  11-3-0  1543.２2
    1. Team Name (11-3) 1543.22
"""

from __future__ import annotations

import pathlib
import re

from ..models import (
    DraftPick, LeagueRef, Manager, Player, SeasonBundle, Standing, dedupe_players,
)
from .base import Provider, ProviderError, register

POSITIONS = r"QB|RB|WR|TE|K|DEF|DST|D/ST|PK"

DRAFT_PATTERNS = [
    # 1. (1.01) Jahmyr Gibbs RB DET - Team Name
    re.compile(
        rf"^\s*(?P<overall>\d+)[.)]?\s*(?:\((?P<r>\d+)\.(?P<p>\d+)\))?\s*"
        rf"(?P<name>[A-Za-z'.\-\s]+?)\s+(?P<pos>{POSITIONS})\b\s*[-–,]?\s*"
        rf"(?P<team>[A-Z]{{2,3}})?\s*[-–|]\s*(?P<mgr>.+?)\s*$"
    ),
    # Round 1 Pick 1  Jahmyr Gibbs (DET - RB)  Team Name
    re.compile(
        rf"^\s*Round\s+(?P<r>\d+)\s+Pick\s+(?P<p>\d+)\s+"
        rf"(?P<name>[A-Za-z'.\-\s]+?)\s*\((?P<team>[A-Z]{{2,3}})\s*[-–]\s*(?P<pos>{POSITIONS})\)\s*"
        rf"(?P<mgr>.+?)\s*$"
    ),
    # tab or multi-space separated columns
    re.compile(
        rf"^\s*(?P<overall>\d+)[\t ]{{1,}}(?P<name>[A-Za-z'.\-\s]+?)[\t ]{{2,}}"
        rf"(?P<pos>{POSITIONS})[\t ]{{1,}}(?P<team>[A-Z]{{2,3}})[\t ]{{2,}}(?P<mgr>.+?)\s*$"
    ),
]

STANDING_PATTERN = re.compile(
    r"^\s*(?P<rank>\d+)[.)]?\s+(?P<name>.+?)\s+\(?(?P<w>\d+)\s*[-–]\s*(?P<l>\d+)"
    r"(?:\s*[-–]\s*(?P<t>\d+))?\)?\s+(?P<pf>[\d,]+\.?\d*)\s*$"
)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.strip().lower()).strip("-")


@register
class ManualProvider(Provider):
    name = "manual"

    def __init__(self, draft_file: str | None = None, standings_file: str | None = None,
                 league_id: str = "manual", teams: int = 10):
        self.draft_file = pathlib.Path(draft_file) if draft_file else None
        self.standings_file = pathlib.Path(standings_file) if standings_file else None
        self.league_id = league_id
        self.teams = teams

    def discover(self) -> list[LeagueRef]:
        return [LeagueRef("manual", self.league_id, "pasted league")]

    def fetch_season(self, league_id: str, season: int) -> SeasonBundle:
        bundle = SeasonBundle(provider="manual", league_id=str(league_id),
                              season=season, team_count=self.teams)
        if self.draft_file:
            self._parse_draft(bundle)
        if self.standings_file:
            self._parse_standings(bundle)
        if not bundle.draft and not bundle.standings:
            raise ProviderError("nothing parsed. check the file format in manual.py docstring")
        bundle.players = dedupe_players(bundle.players)
        return bundle

    # ---------- parsers ----------

    def _parse_draft(self, bundle: SeasonBundle) -> None:
        managers: dict[str, Manager] = {}
        rows: list[tuple[int, int, str, str, str, str]] = []

        for raw in self.draft_file.read_text(encoding="utf-8").splitlines():
            line = raw.rstrip()
            if not line.strip():
                continue
            for pat in DRAFT_PATTERNS:
                m = pat.match(line)
                if not m:
                    continue
                g = m.groupdict()
                rnd = int(g["r"]) if g.get("r") else 0
                if g.get("overall"):
                    overall = int(g["overall"])
                elif g.get("r") and g.get("p"):
                    overall = (int(g["r"]) - 1) * self.teams + int(g["p"])
                else:
                    overall = len(rows) + 1
                if not rnd:
                    rnd = (overall - 1) // max(self.teams, 1) + 1
                pos = (g.get("pos") or "").upper().replace("D/ST", "DEF").replace("DST", "DEF")
                rows.append((overall, rnd, g["name"].strip(), pos,
                             (g.get("team") or "").upper(), g["mgr"].strip()))
                break

        if not rows:
            return

        # Team count is inferable from the data itself when the paste is complete.
        distinct_mgrs = {r[5] for r in rows}
        if len(distinct_mgrs) > 1:
            self.teams = len(distinct_mgrs)
            bundle.team_count = self.teams

        for overall, rnd, name, pos, nfl, mgr in rows:
            tid = _slug(mgr)
            if tid not in managers:
                managers[tid] = Manager(tid, mgr, mgr)
            pid = _slug(name)
            bundle.players.append(Player(pid, name, pos, nfl))
            bundle.draft.append(DraftPick(
                overall=overall,
                round=(overall - 1) // max(self.teams, 1) + 1,
                team_id=tid, player_id=pid,
            ))
        bundle.managers.extend(managers.values())

    def _parse_standings(self, bundle: SeasonBundle) -> None:
        known = {m.name: m.team_id for m in bundle.managers}
        for raw in self.standings_file.read_text(encoding="utf-8").splitlines():
            m = STANDING_PATTERN.match(raw.rstrip())
            if not m:
                continue
            g = m.groupdict()
            name = g["name"].strip()
            tid = known.get(name) or _slug(name)
            if tid not in {mm.team_id for mm in bundle.managers}:
                bundle.managers.append(Manager(tid, name, name))
            bundle.standings.append(Standing(
                team_id=tid, rank=int(g["rank"]),
                wins=int(g["w"]), losses=int(g["l"]), ties=int(g.get("t") or 0),
                points_for=float(g["pf"].replace(",", "")),
            ))
