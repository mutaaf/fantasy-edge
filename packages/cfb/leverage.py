"""Which game matters most right now: the Saturday Wall's ordering.

A heuristic, and labelled as one. It is not a win-probability model and not
a measure of excitement; it is a hand-weighted blend of what a fan checks
first. The weights are constants so the ordering is deterministic and
a test can pin it.

Live games (0 to 112, the sum of the weights):

    closeness = max(0, 1 - margin / 24)            three scores apart is 0
    lateness  = elapsed / 3600, 1.0 in overtime     0 at kickoff, 1 at the end
    rankness  = (sum over ranked sides of (26 - rank)) / 50
    score     = 40 * closeness * (0.4 + 0.6 * lateness)
              + 25 * rankness
              + 12 * red zone
              + 15 * overtime
              +  8 * a ranked team trailing an underdog
              + 12 * close and late (one score, 3/4 of regulation gone)

Finals are ordered by what is worth hearing about - upset 30, overtime 20,
one-score 15, rankness 10 - and upcoming games by rankness then kickoff.
Ties break on event id, so the order never depends on dict iteration.
"""
from __future__ import annotations

from .league import RULES

CAVEAT = ("Hand-weighted ordering from score margin, game clock, AP rank and field position. "
          "Not a win-probability or excitement model; the weights are constants, not fitted.")

W_CLOSE, W_RANK, W_REDZONE, W_OT, W_ALERT, W_LATE = 40, 25, 12, 15, 8, 12


def rankness(g: dict) -> float:
    return sum(26 - t["rank"] for t in (g["away"], g["home"]) if t["rank"]) / 50


def elapsed_seconds(st: dict) -> float:
    per, n = RULES["period_seconds"], RULES["periods"]
    if st["overtimes"]:
        return per * n
    if st["period"] <= 0:
        return 0.0
    return min(per * n, (st["period"] - 1) * per + (per - st["clockSeconds"]))


def live_score(g: dict) -> tuple[float, list[str]]:
    st, f = g["status"], g["flags"]
    margin = abs((g["away"]["score"] or 0) - (g["home"]["score"] or 0))
    closeness = max(0.0, 1 - margin / 24)
    lateness = 1.0 if st["overtimes"] else elapsed_seconds(st) / (RULES["period_seconds"] * RULES["periods"])
    parts = [
        (W_CLOSE * closeness * (0.4 + 0.6 * lateness), "close" if f["oneScore"] else None),
        (W_RANK * rankness(g), "ranked" if f["ranked"] else None),
        (W_REDZONE * f["redZone"], "red zone" if f["redZone"] else None),
        (W_OT * f["overtime"], "overtime" if f["overtime"] else None),
        (W_ALERT * f["upsetAlert"], "upset alert" if f["upsetAlert"] else None),
    ]
    late = lateness >= 0.75 and f["oneScore"]
    parts.append((W_LATE * late, "late" if late else None))
    return round(sum(p for p, _ in parts), 3), [r for _, r in parts if r]


def final_score(g: dict) -> tuple[float, list[str]]:
    f = g["flags"]
    parts = [(30 * f["upset"], "upset"), (20 * f["overtime"], "overtime"),
             (15 * f["oneScore"], "one score"), (10 * rankness(g), "ranked" if f["ranked"] else None)]
    return round(sum(p for p, _ in parts), 3), [r for p, r in parts if r and p]


def rank(games: list[dict]) -> list[dict]:
    """Annotate every game with `leverage` and return them in wall order:
    live (and delayed) by score, then upcoming, then finals."""
    def band(g):
        s = g["status"]
        return 0 if s["state"] == "in" else 1 if s["state"] == "pre" else 2

    for g in games:
        s = g["status"]
        if s["state"] == "in" and not s["delayed"]:
            score, reasons = live_score(g)
        elif s["state"] == "post":
            score, reasons = final_score(g)
        else:
            score, reasons = round(10 * rankness(g), 3), (["ranked"] if g["flags"]["ranked"] else [])
            if s["delayed"]:
                reasons = reasons + ["delayed"]
        g["leverage"] = {"score": score, "reasons": reasons}
    ordered = sorted(games, key=lambda g: (band(g), -g["leverage"]["score"],
                                           g["kickoff"] if band(g) == 1 else "", g["id"]))
    for i, g in enumerate(ordered):
        g["leverage"]["rank"] = i + 1
    return ordered


def spotlight(ordered: list[dict]) -> str | None:
    live = [g for g in ordered if g["status"]["state"] == "in" and not g["status"]["delayed"]]
    return live[0]["id"] if live else None
