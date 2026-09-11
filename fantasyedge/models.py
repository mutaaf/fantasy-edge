"""Normalized domain model.

Every provider adapts its own wire format into these records. Nothing
downstream of ingestion knows or cares whether the data came from Yahoo,
ESPN, or a copy-paste. That boundary is the whole point: analytics is
written once and works against any source.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Iterable


@dataclass(frozen=True)
class LeagueRef:
    """Identifies one league on one provider."""

    provider: str
    league_id: str
    name: str = ""
    seasons: tuple[int, ...] = ()


@dataclass(frozen=True)
class Manager:
    team_id: str
    name: str          # team name, which people rename constantly
    owner: str = ""    # human, which is the stable key across seasons
    logo: str = ""     # the team's own badge, where the provider has one


@dataclass(frozen=True)
class Player:
    player_id: str
    name: str
    pos: str
    nfl_team: str = ""


@dataclass(frozen=True)
class DraftPick:
    overall: int
    round: int
    team_id: str
    player_id: str
    cost: float | None = None   # auction only; None in a snake draft


@dataclass(frozen=True)
class RosterSlot:
    """One player on one roster in one week.

    `started` is what makes the bench-leak analysis possible, and `points`
    must be actual scored points, not projections.
    """

    week: int
    team_id: str
    player_id: str
    slot: str            # QB, RB, WR, TE, FLEX, K, DEF, BN, IR
    points: float = 0.0
    projected: float | None = None
    started: bool = False


@dataclass(frozen=True)
class Matchup:
    week: int
    team_id: str
    opponent_id: str
    points: float
    opp_points: float

    @property
    def won(self) -> bool:
        return self.points > self.opp_points


@dataclass(frozen=True)
class Transaction:
    week: int
    team_id: str
    player_id: str
    kind: str            # add, drop, trade
    source: str = ""     # waivers, freeagent, trade


@dataclass(frozen=True)
class Standing:
    team_id: str
    rank: int
    wins: int = 0
    losses: int = 0
    ties: int = 0
    points_for: float = 0.0
    points_against: float = 0.0


@dataclass(frozen=True)
class Adp:
    """External draft-market rank, used for the reach analysis.

    Optional. Without it every other analysis still runs; you just lose
    the "am I systematically reaching" answer.
    """

    player_id: str
    source: str
    rank: float


@dataclass
class SeasonBundle:
    """Everything one provider knows about one league-season."""

    provider: str
    league_id: str
    season: int
    league_name: str = ""
    team_count: int = 0
    scoring: str = ""
    managers: list[Manager] = field(default_factory=list)
    players: list[Player] = field(default_factory=list)
    draft: list[DraftPick] = field(default_factory=list)
    rosters: list[RosterSlot] = field(default_factory=list)
    matchups: list[Matchup] = field(default_factory=list)
    transactions: list[Transaction] = field(default_factory=list)
    standings: list[Standing] = field(default_factory=list)
    adp: list[Adp] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"{self.provider}:{self.league_id} {self.season} "
            f"{len(self.managers)} teams, {len(self.draft)} picks, "
            f"{len(self.rosters)} roster rows, {len(self.matchups)} matchups, "
            f"{len(self.transactions)} transactions"
        )


def dedupe_players(players: Iterable[Player]) -> list[Player]:
    """Providers repeat players across weeks. Keep the richest record."""
    best: dict[str, Player] = {}
    for p in players:
        prior = best.get(p.player_id)
        if prior is None or (not prior.nfl_team and p.nfl_team):
            best[p.player_id] = p
    return list(best.values())


def to_dict(obj) -> dict:
    return asdict(obj)
