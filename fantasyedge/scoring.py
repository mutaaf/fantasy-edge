"""Turn a box score into fantasy points.

ESPN's summary endpoint reports football statistics, not fantasy ones. This is
the translation, and it is deliberately its own module because it is the one
place where a league's own rules matter: `config/league.toml` carries the
scoring, and a league that pays half a point per reception should not be told
it is winning by a point it does not score.

Stats arrive as a `keys` list plus a parallel `stats` list per athlete, so
everything here reads by key name rather than by position. ESPN reorders those
columns from time to time, and a positional parser would keep working while
quietly attributing rushing yards to interceptions.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Sensible defaults for a full-PPR league. Anything present in league.toml wins.
DEFAULTS = {
    "reception": 1.0,
    "pass_yard": 0.04,
    "rush_yard": 0.1,
    "rec_yard": 0.1,
    "return_yard": 0.04,
    "pass_touchdown": 4.0,
    "touchdown": 6.0,          # rushing and receiving
    "interception": -2.0,
    "fumble_lost": -2.0,
    "two_point": 2.0,
    "field_goal": 3.0,
    "extra_point": 1.0,
}

# Which box-score keys carry the numbers we care about. A key we do not know
# is ignored rather than guessed at.
WANTED = {
    "passingYards", "passingTouchdowns", "interceptions",
    "rushingYards", "rushingTouchdowns",
    "receptions", "receivingYards", "receivingTouchdowns",
    "fumblesLost", "fieldGoalsMade", "extraPointsMade",
    "kickReturnYards", "puntReturnYards",
}


@dataclass
class Scoring:
    rules: dict = field(default_factory=lambda: dict(DEFAULTS))

    @classmethod
    def from_config(cls, cfg: dict | None) -> "Scoring":
        rules = dict(DEFAULTS)
        for k, v in ((cfg or {}).get("scoring") or {}).items():
            try:
                rules[k] = float(v)
            except (TypeError, ValueError):
                continue
        return cls(rules)

    def points(self, stat: dict) -> float:
        r, g = self.rules, stat.get
        total = (
            g("passingYards", 0.0) * r["pass_yard"]
            + g("passingTouchdowns", 0.0) * r["pass_touchdown"]
            + g("interceptions", 0.0) * r["interception"]
            + g("rushingYards", 0.0) * r["rush_yard"]
            + g("rushingTouchdowns", 0.0) * r["touchdown"]
            + g("receptions", 0.0) * r["reception"]
            + g("receivingYards", 0.0) * r["rec_yard"]
            + g("receivingTouchdowns", 0.0) * r["touchdown"]
            + g("fumblesLost", 0.0) * r["fumble_lost"]
            + g("fieldGoalsMade", 0.0) * r["field_goal"]
            + g("extraPointsMade", 0.0) * r["extra_point"]
            + (g("kickReturnYards", 0.0) + g("puntReturnYards", 0.0)) * r["return_yard"]
        )
        return round(total, 2)


def _num(raw) -> float:
    """ESPN reports "20/30" for made/attempted and "--" for nothing."""
    if raw in (None, "", "--"):
        return 0.0
    s = str(raw).split("/")[0].replace(",", "")
    try:
        return float(s)
    except ValueError:
        return 0.0


def parse_boxscore(summary: dict) -> dict[str, dict]:
    """Athlete id -> the stats we know how to score.

    Reads by key name. A category we do not recognise contributes nothing
    rather than being folded in at the wrong weight.
    """
    out: dict[str, dict] = {}
    for team in ((summary.get("boxscore") or {}).get("players") or []):
        for cat in (team.get("statistics") or []):
            keys = cat.get("keys") or []
            idx = {k: i for i, k in enumerate(keys) if k in WANTED}
            if not idx:
                continue
            for ath in (cat.get("athletes") or []):
                pid = str(((ath.get("athlete") or {}).get("id")) or "")
                if not pid:
                    continue
                stats = ath.get("stats") or []
                bucket = out.setdefault(pid, {})
                for key, i in idx.items():
                    if i < len(stats):
                        bucket[key] = bucket.get(key, 0.0) + _num(stats[i])
    return out


def score_boxscore(summary: dict, scoring: Scoring | None = None) -> dict[str, float]:
    sc = scoring or Scoring()
    return {pid: sc.points(stat) for pid, stat in parse_boxscore(summary).items()}
