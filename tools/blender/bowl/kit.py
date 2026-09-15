"""The bowl kit's plan, read from the scene.

Every row, section, aisle, vomitory, tunnel cut and seat comes from
`fantasyedge/scene.py` - the same functions that put `bowl.seating` and
`bowl.mounts` in the scene every client receives - so the geometry this kit
exports and the seats a renderer places can never disagree. This module only
adapts those functions to the kit's shorthand and adds what exists purely as
architecture (the club band, fascia depth), which no client needs to know.

Coordinates are the renderer's local space in yards: midfield is the origin,
+x toward the east end zone, +y up, +z toward the home sideline (the far side,
where the press box is, is -z). Stdlib only, so it runs under Blender's Python
and plain python3 alike.

    python3 tools/blender/bowl/kit.py      # prints the plan's totals
"""
from __future__ import annotations

import json
import math
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
OUT = ROOT / "assets" / "actors" / "bowl"
sys.path.insert(0, str(ROOT))

from fantasyedge import scene as SC  # noqa: E402  (stdlib-only module)

YARD = 0.9144
TOKENS = SC.load_tokens()
VISUAL = TOKENS["visual"]

FIELD = SC.RULES["nfl"]["field"]
BOWL = json.loads(json.dumps(SC.BOWL))
BOWL["shape"].update({"halfLength": FIELD["length"] / 2 + FIELD["endZone"],
                      "halfWidth": FIELD["width"] / 2})
SHAPE = BOWL["shape"]
TIERS = {t["name"]: t for t in BOWL["tiers"]}
ROWS = dict(VISUAL["bowl"]["rows"])
SEATING_CFG = BOWL["seating"]
SEAT_PITCH = SEATING_CFG["pitch"]
AISLE = SEATING_CFG["aisle"]
VOMITORY = {k: {**v, "rows": tuple(v["rows"])} for k, v in SEATING_CFG["vomitory"].items()}
ACCESSIBLE_MARGIN = SEATING_CFG["accessibleMargin"]
TUNNEL_CLEAR = SEATING_CFG["tunnelClear"]
PARAPET = BOWL["parapet"]

# Architecture only the kit needs.
CLUB = {"glass": 37.2, "ceiling": 23.0, "back": 41.0}
FASCIA = {"front": BOWL["ribbon"]["offset"], "back": BOWL["ribbon"]["offset"] + 0.6,
          "bottom": BOWL["ribbon"]["rise"][0], "top": 24.9}
WEDGES = 48


def bowl_point(m: float, t: float) -> tuple[float, float]:
    return SC.bowl_point(SHAPE, m, t)


def inward(m: float, t: float) -> tuple[float, float]:
    return SC.bowl_inward(SHAPE, m, t)


def Ring(m: float) -> SC.BowlRing:
    return SC.BowlRing(SHAPE, m)


def row(tier: dict, r: int, rows: int) -> dict:
    return SC.bowl_row(tier, r, rows)


def sections(tier_name: str) -> list[dict]:
    return SC.bowl_sections(SHAPE, TIERS[tier_name], SEATING_CFG)


def gaps_for_row(tier_name: str, r: int, secs: list[dict], ring) -> list[tuple[float, float, str]]:
    return SC.bowl_gaps(SHAPE, TIERS[tier_name], r, ROWS[tier_name], secs, ring, SEATING_CFG, BOWL["tunnels"])


def tunnel_spans(ring) -> list[tuple[float, float, dict]]:
    out = []
    for tn in BOWL["tunnels"]:
        s = ring.arc_at(0.0 if tn["x"] > 50 else math.pi)
        half = tn["width"] / 2 + 1.0
        out.append((s - half, s + half, tn))
    return out


def seating() -> dict:
    return SC.bowl_seating(SHAPE, ROWS)


def mounts() -> dict:
    return SC.bowl_mounts(SHAPE, VISUAL["lighting"]["rim"])


def seat_rows(tier_name: str):
    """Row by row: (r, row, ring, [(arc, x, z, yaw)], gaps, sections), from the
    scene's runs. yaw is about +y with 0 facing +z: facing (sin yaw, cos yaw)."""
    plan = next(t for t in seating()["tiers"] if t["tier"] == tier_name)
    tier = TIERS[tier_name]
    n = ROWS[tier_name]
    secs = plan["sections"]
    for r, rw_plan in enumerate(plan["rows"]):
        rw = row(tier, r, n)
        ring = Ring(rw_plan["feet"])
        seats = []
        for first, count in rw_plan["runs"]:
            for k in range(count):
                s = first + k * rw_plan["pitch"]
                t = ring.angle(s)
                x, z = bowl_point(ring.m, t)
                nx, nz = inward(ring.m, t)
                seats.append((s, x, z, math.atan2(nx, nz)))
        yield r, rw, ring, seats, gaps_for_row(tier_name, r, secs, ring), secs


def adaptive_angles(m: float, tolerance: float = 0.04, max_step: float = 6.0) -> list[float]:
    """Angles around the ring, dense in the corners and sparse on the straights."""
    ring = Ring(m)
    out = [0.0]
    s = 0.0
    step = 0.5
    while s < ring.length - 1e-6:
        nxt = min(ring.length, s + max_step)
        while nxt - s > step:
            t0, t1, tm = ring.angle(s), ring.angle(nxt), ring.angle((s + nxt) / 2)
            x0, z0 = bowl_point(m, t0)
            x1, z1 = bowl_point(m, t1)
            xm, zm = bowl_point(m, tm)
            dev = abs((x1 - x0) * (z0 - zm) - (x0 - xm) * (z1 - z0)) / (math.hypot(x1 - x0, z1 - z0) or 1e-9)
            if dev <= tolerance:
                break
            nxt = s + (nxt - s) * 0.6
        s = nxt
        out.append(ring.angle(s) if s < ring.length - 1e-6 else 2 * math.pi)
    return out


def main() -> None:
    plan = seating()
    print("seats:", plan["total"], {t["tier"]: (len(t["sections"]), sum(r["seats"] for r in t["rows"]))
                                    for t in plan["tiers"]}, "mounts:", len(mounts()["rim"]))


if __name__ == "__main__":
    main()
