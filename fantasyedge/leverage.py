"""How much a cell of the mosaic can still change your week.

A scoreboard shows what happened. A mosaic has to decide what *matters*, and
that decision has to be a number or the layout cannot use it. That number is
leverage.

The model. Your remaining points and your opponent's are sums of independent
per-player unknowns, so the final margin is approximately normal:

    m = (your_score + R_you) - (opp_score + R_opp)    expected final margin
    s = sqrt(V_you + V_opp)                           its standard deviation
    P(win) = Phi(m / s)

Leverage of one player is the sensitivity of P(win) to that player's own
remaining uncertainty:

    leverage_i = phi(m / s) * sigma_i / s

which falls out of differentiating Phi(m/s) and weighting by how much
uncertainty the player actually carries. Every property you want is a
consequence rather than a special case:

  * a blowout drives m/s far from zero, phi collapses, every tile shrinks
  * a tied game sits at the peak of phi, so everything is big
  * a player whose game is over has sigma_i = 0 and vanishes
  * late in a close game s is small, so the last player still running has
    enormous sigma_i / s - the "it all comes down to him" tile, arrived at
    honestly instead of by special-casing the fourth quarter

Variance accumulates like independent increments over game time, so a player
with fraction f of their game left carries sigma_full * sqrt(f).

Pure functions over plain numbers, deliberately. The same twenty lines run in
Swift on a TV and in JavaScript in a browser, so no surface has to wait for a
server to tell it how big to draw a box.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from statistics import NormalDist

_N = NormalDist()

# Full-game standard deviation of fantasy points, by position. Kickers are
# nearly deterministic; skill positions are not. These are the spread of a
# week's outcomes, not of a projection error, which is why they look large.
SIGMA_FULL = {"QB": 7.0, "RB": 6.5, "WR": 7.0, "TE": 5.0, "K": 3.0, "DEF": 6.0}
DEFAULT_SIGMA = 6.0

# Tile size bands. Area is roughly proportional to leverage share; these are
# the quantised sizes a grid can actually pack, largest first.
BANDS = [("xl", 4), ("lg", 3), ("md", 2), ("sm", 1)]
BAND_ORDER = {name: i for i, (name, _) in enumerate(BANDS)}


@dataclass
class Cell:
    """One tile's inputs. `side` is "you", "opp", or "league" for a cell that
    belongs to somebody else's matchup and so carries no leverage for you."""

    id: str
    label: str
    pos: str = ""
    team: str = ""
    side: str = "you"
    scored: float = 0.0
    projected: float = 0.0          # full-game projection
    remaining: float = 1.0          # fraction of their game still to play, 0..1
    state: str = ""                 # "RZ", "final", "pre", "bye", ...
    # filled in by evaluate()
    sigma: float = 0.0
    leverage: float = 0.0
    share: float = 0.0
    band: str = "sm"
    weight: int = 1


@dataclass
class Mosaic:
    win_prob: float
    margin: float
    sigma: float
    intensity: float
    phase: str
    your_score: float
    opp_score: float
    your_projected: float
    opp_projected: float
    cells: list[Cell] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "winProb": round(self.win_prob, 4),
            "intensity": round(self.intensity, 4),
            "phase": self.phase,
            "margin": round(self.margin, 2),
            "sigma": round(self.sigma, 2),
            "yourScore": round(self.your_score, 2),
            "oppScore": round(self.opp_score, 2),
            "yourProjected": round(self.your_projected, 2),
            "oppProjected": round(self.opp_projected, 2),
            "cells": [
                {"id": c.id, "label": c.label, "pos": c.pos, "team": c.team,
                 "side": c.side, "scored": round(c.scored, 2),
                 "projected": round(c.projected, 2), "remaining": round(c.remaining, 3),
                 "state": c.state, "sigma": round(c.sigma, 2),
                 "leverage": round(c.leverage, 5), "share": round(c.share, 4),
                 "band": c.band, "weight": c.weight}
                for c in self.cells
            ],
        }


def sigma_for(pos: str, remaining: float) -> float:
    """Standard deviation of the points a player has *left* to score."""
    full = SIGMA_FULL.get((pos or "").upper(), DEFAULT_SIGMA)
    return full * math.sqrt(max(0.0, min(1.0, remaining)))


def band_for(share: float, previous: str = "", hysteresis: float = 0.15,
             even: float = 1 / 18) -> tuple[str, int]:
    """Quantise a share of the board to a tile size.

    Cuts are multiples of an even split rather than absolute numbers, because
    the metric behind `share` changes with the phase of the week. One player
    can carry most of the leverage in a close game, but nobody carries 18% of
    the projected points in an eighteen-cell line-up - absolute cuts made every
    pre-game tile identical. Measuring against `1/n` asks the question that
    actually matters: how far above its fair share is this cell?

    Hysteresis is not a nicety. Shares are recomputed every few seconds, and a
    cell sitting exactly on a boundary would flip size on every tick - which on
    a television reads as a broken screen, and worse, moves the focused tile out
    from under the remote. A cell must beat the next threshold by a margin
    before it is allowed to grow or shrink.
    """
    cuts = [("xl", even * 3.0), ("lg", even * 1.9), ("md", even * 1.05), ("sm", 0.0)]
    target = next(name for name, cut in cuts if share >= cut)
    if previous and previous in BAND_ORDER and previous != target:
        # Only move if the change is decisive; otherwise hold the old size.
        pi, ti = BAND_ORDER[previous], BAND_ORDER[target]
        cut_for = dict(cuts)
        if ti < pi:                       # growing: must clear the bar by margin
            if share < cut_for[target] * (1.0 + hysteresis):
                target = previous
        else:                             # shrinking: must fall well below it
            if share > cut_for[previous] * (1.0 - hysteresis):
                target = previous
    return target, dict(BANDS)[target]


def evaluate(cells: list[Cell], previous: dict[str, str] | None = None) -> Mosaic:
    """Score every cell and the matchup it belongs to.

    `previous` maps cell id to the band it had last tick, which is what makes
    the hysteresis above work across updates.
    """
    previous = previous or {}
    you = [c for c in cells if c.side == "you"]
    opp = [c for c in cells if c.side == "opp"]

    def side_totals(group: list[Cell]) -> tuple[float, float, float]:
        scored = sum(c.scored for c in group)
        rest = sum(max(0.0, c.projected - c.scored) * c.remaining for c in group)
        var = 0.0
        for c in group:
            c.sigma = sigma_for(c.pos, c.remaining)
            var += c.sigma ** 2
        return scored, rest, var

    ys, yr, yv = side_totals(you)
    os_, orr, ov = side_totals(opp)
    for c in cells:                        # league cells still need a sigma
        if c.side not in ("you", "opp"):
            c.sigma = sigma_for(c.pos, c.remaining)

    margin = (ys + yr) - (os_ + orr)
    s = math.sqrt(yv + ov)

    if s <= 1e-9:
        # Nothing left to play: the week is decided, so nothing has leverage.
        win_prob = 1.0 if margin > 0 else (0.0 if margin < 0 else 0.5)
        sensitivity = 0.0
    else:
        z = margin / s
        win_prob = _N.cdf(z)
        sensitivity = _N.pdf(z) / s

    for c in cells:
        c.leverage = (sensitivity * c.sigma) if c.side in ("you", "opp") else 0.0

    # Which question the board can actually answer right now.
    #
    # Before kickoff every player carries identical uncertainty, so leverage is
    # uniform and sizing by it says nothing - eighteen tiles of exactly the
    # same size. Once the week is over there is no uncertainty left at all. In
    # both cases leverage is the wrong metric, not a broken one, so the board
    # falls back to the metric that does carry information: what is expected
    # beforehand, what was actually scored afterwards.
    # Read the clock, not the scoreboard: points already scored do not make a
    # week live, and an early kickoff does not make it over.
    if all(c.remaining >= 1.0 for c in cells):
        phase = "pre"
    elif all(c.remaining <= 0.0 for c in cells):
        phase = "final"
    else:
        phase = "live"

    total = sum(c.leverage for c in cells)
    if phase == "pre":
        basis = {c.id: max(0.0, c.projected) for c in cells}
    elif phase == "final":
        basis = {c.id: max(0.0, c.scored) for c in cells}
    else:
        basis = {c.id: c.leverage for c in cells}
    btot = sum(basis.values())

    even = 1.0 / max(1, len(cells))
    for c in cells:
        c.share = (basis[c.id] / btot) if btot > 1e-12 else 0.0
        c.band, c.weight = band_for(c.share, previous.get(c.id, ""), even=even)

    # `share` is normalised, so it says who matters most *within* this matchup
    # but says nothing about whether the matchup itself is still alive. A 40
    # point blowout keeps the same relative sizes as a coin flip, which would
    # leave the screen shouting through a game nobody can lose. Intensity is
    # the absolute dimension: 1.0 at a true toss-up, 0 once the week is decided.
    # The client spends it on how much room the matchup takes and how hot the
    # accent runs, so a dead week calms down and yields space to the league.
    intensity = 2.0 * min(win_prob, 1.0 - win_prob)

    cells.sort(key=lambda c: (-c.share, -c.leverage, c.id))
    return Mosaic(win_prob=win_prob, margin=margin, sigma=s, intensity=intensity,
                  phase=phase,
                  your_score=ys, opp_score=os_,
                  your_projected=ys + yr, opp_projected=os_ + orr,
                  cells=cells)
