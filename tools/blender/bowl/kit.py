"""The bowl kit's plan: where every row, aisle, vomitory, seat and mast goes.

Pure standard library, so it runs under `python3` for the contract files and
under Blender's bundled Python for the geometry. It reads the bowl straight
from `fantasyedge/scene.py` and the row counts from `design/tokens.json`, and
reproduces `SceneMath.row`, `bowlPoint`, `inward` and `evenAngles` exactly, so
a seat in `seats.json` sits on the row a renderer draws rather than near it.

Coordinates are the renderer's local space in yards: midfield is the origin,
+x toward the east end zone, +y up, +z toward the home sideline (the far side,
where the press box is, is -z). Blender meshes are built in metres from the
same numbers; see `to_blender`.

    python3 tools/blender/bowl/kit.py      # writes seats.json and mounts.json
"""
from __future__ import annotations

import json
import math
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
OUT = ROOT / "assets" / "actors" / "bowl"
sys.path.insert(0, str(ROOT))

from fantasyedge import scene as SCENE  # noqa: E402  (stdlib-only module)

YARD = 0.9144
TOKENS = json.loads((ROOT / "design" / "tokens.json").read_text())
LOOK = TOKENS["look"]

FIELD = SCENE.RULES["nfl"]["field"]
BOWL = json.loads(json.dumps(SCENE.BOWL))
BOWL["shape"].update({"halfLength": FIELD["length"] / 2 + FIELD["endZone"],
                      "halfWidth": FIELD["width"] / 2})
SHAPE = BOWL["shape"]
TIERS = {t["name"]: t for t in BOWL["tiers"]}
ROWS = {name: LOOK["bowl"]["rows"][name] for name in TIERS}

# ── the kit's own dimensions, in yards unless named otherwise ──
# A stadium seat is 19-21 in on centre; 0.55 yd is 20 in. Aisles run 44 in.
SEAT_PITCH = 0.55
AISLE = 1.2
SEATS_PER_SECTION = {"lower": 24, "upper": 26}
VOMITORY = {  # every Nth section carries one, centred, through these rows
    "lower": {"every": 3, "phase": 1, "rows": (11, 16), "width": 3.0},
    "upper": {"every": 4, "phase": 2, "rows": (7, 11), "width": 3.0},
}
ACCESSIBLE_MARGIN = 1.1          # platform runs this far past each side of a vomitory
TUNNEL_CLEAR = 0.9               # yards of structure over a tunnel's opening
CLUB = {"slab": 37.2, "glass": 37.2, "ceiling": 23.0, "soffitTo": 41.6}
FASCIA = {"front": 41.6, "back": 42.2, "bottom": 21.0, "top": 24.9}
PARAPET = {"offset": 70.6, "top": 47.6}
WEDGES = 48                      # LOD2 and far bands are split by angle for the table cutaway


# ───────────────────────────── the curve ─────────────────────────────

def bowl_point(m: float, t: float) -> tuple[float, float]:
    a, b = SHAPE["halfLength"] + m, SHAPE["halfWidth"] + m
    e = 2 / SHAPE["exponent"]
    c, s = math.cos(t), math.sin(t)
    return (a * math.copysign(abs(c) ** e, c), b * math.copysign(abs(s) ** e, s))


def inward(m: float, t: float) -> tuple[float, float]:
    e = 1e-3
    ax, az = bowl_point(m, t - e)
    bx, bz = bowl_point(m, t + e)
    nx, nz = -(bz - az), bx - ax
    hx, hz = bowl_point(m, t)
    if nx * hx + nz * hz > 0:
        nx, nz = -nx, -nz
    n = math.hypot(nx, nz) or 1e-9
    return (nx / n, nz / n)


class Ring:
    """A superellipse at offset m, walked by arc length."""

    RES = 2880

    def __init__(self, m: float):
        self.m = m
        self.t = [2 * math.pi * i / self.RES for i in range(self.RES + 1)]
        self.cum = [0.0]
        px, pz = bowl_point(m, 0.0)
        for t in self.t[1:]:
            x, z = bowl_point(m, t)
            self.cum.append(self.cum[-1] + math.hypot(x - px, z - pz))
            px, pz = x, z
        self.length = self.cum[-1]

    def angle(self, s: float) -> float:
        """Curve parameter at arc length s (wraps)."""
        s %= self.length
        lo, hi = 0, self.RES
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if self.cum[mid] <= s:
                lo = mid
            else:
                hi = mid
        span = self.cum[hi] - self.cum[lo] or 1e-9
        return self.t[lo] + (self.t[hi] - self.t[lo]) * (s - self.cum[lo]) / span

    def at(self, s: float) -> tuple[float, float, float]:
        t = self.angle(s)
        x, z = bowl_point(self.m, t)
        return x, z, t

    def fraction(self, f: float) -> float:
        return f * self.length


def row(tier: dict, r: int, rows: int) -> dict:
    """SceneMath.row, exactly."""
    n = max(1, rows)
    depth = (tier["outer"] - tier["inner"]) / n
    front = tier["inner"] + depth * r
    rise = tier["rise"][1] - tier["rise"][0]
    return {"front": front, "back": front + depth,
            "tread": tier["rise"][0] + rise * (r + 1) / n,
            "riserFrom": tier["rise"][0] + rise * r / n}


def adaptive_angles(m: float, tolerance: float = 0.04, max_step: float = 6.0) -> list[float]:
    """Angles around the ring, dense in the corners and sparse on the straights,
    so a row strip keeps its curve without spending triangles on a flat side."""
    ring = Ring(m)
    out = [0.0]
    s = 0.0
    step = 0.5
    while s < ring.length - 1e-6:
        nxt = min(ring.length, s + max_step)
        # shrink until the chord's midpoint stays within tolerance of the curve
        while nxt - s > step:
            x0, z0, _ = ring.at(s)
            x1, z1, _ = ring.at(nxt)
            xm, zm, _ = ring.at((s + nxt) / 2)
            dev = abs((x1 - x0) * (z0 - zm) - (x0 - xm) * (z1 - z0)) / (math.hypot(x1 - x0, z1 - z0) or 1e-9)
            if dev <= tolerance:
                break
            nxt = s + (nxt - s) * 0.6
        s = nxt
        out.append(ring.angle(s) if s < ring.length - 1e-6 else 2 * math.pi)
    return out


# ───────────────────────────── the plan ─────────────────────────────

def side_of(t: float) -> str:
    x, z = bowl_point(0.0, t)
    if abs(x) > SHAPE["halfLength"] - 2 and abs(z) < SHAPE["halfWidth"]:
        return "east" if x > 0 else "west"
    return "home" if z > 0 else "far"


def sections(tier_name: str) -> list[dict]:
    """Radial sections laid out by arc-length fraction at the tier's middle
    row, so aisles line up row to row. Numbered from the home 50-yard line,
    clockwise seen from above."""
    tier = TIERS[tier_name]
    mid = Ring((tier["inner"] + tier["outer"]) / 2)
    width = SEATS_PER_SECTION[tier_name] * SEAT_PITCH + AISLE
    count = max(8, round(mid.length / width))
    # start at the home midfield (t = pi/2) and run toward +x... then round.
    start = Ring((tier["inner"] + tier["outer"]) / 2)
    s0 = _arc_at_angle(start, math.pi / 2)
    base = {"lower": 100, "upper": 300}[tier_name]
    out = []
    for k in range(count):
        f0 = ((s0 / mid.length) + k / count) % 1.0
        f1 = f0 + 1 / count
        t_mid = mid.angle((f0 + 0.5 / count) * mid.length)
        cx, cz = bowl_point(mid.m, t_mid)
        v = VOMITORY[tier_name]
        out.append({"id": f"{base + k + 1}", "tier": tier_name, "index": k,
                    "from": round(f0, 6), "to": round(f1, 6),
                    "side": side_of(t_mid), "centre": [round(cx, 2), round(cz, 2)],
                    "vomitory": k % v["every"] == v["phase"]})
    return out


def _arc_at_angle(ring: Ring, t: float) -> float:
    i = min(ring.RES, max(0, round(t / (2 * math.pi) * ring.RES)))
    return ring.cum[i]


def tunnel_spans(ring: Ring) -> list[tuple[float, float, dict]]:
    spans = []
    for tn in BOWL["tunnels"]:
        x = tn["x"] - 50
        t = 0.0 if x > 0 else math.pi
        s = _arc_at_angle(ring, t)
        half = tn["width"] / 2 + 1.0
        spans.append((s - half, s + half, tn))
    return spans


def gaps_for_row(tier_name: str, r: int, secs: list[dict], ring: Ring) -> list[tuple[float, float, str]]:
    """Stretches of this row's arc with no seats: aisles, vomitories, the
    accessible platform in front of each, and tunnels. In arc length (yards)."""
    L = ring.length
    gaps = []
    v = VOMITORY[tier_name]
    for sec in secs:
        s = sec["from"] * L
        gaps.append((s - AISLE / 2, s + AISLE / 2, "aisle"))
        if sec["vomitory"]:
            c = (sec["from"] + sec["to"]) / 2 * L
            half = v["width"] / 2
            if v["rows"][0] <= r <= v["rows"][1]:
                gaps.append((c - half, c + half, "vomitory"))
            elif r == v["rows"][0] - 1:
                gaps.append((c - half - ACCESSIBLE_MARGIN, c + half + ACCESSIBLE_MARGIN, "accessible"))
    if tier_name == "lower":
        rw = row(TIERS["lower"], r, ROWS["lower"])
        for s0, s1, tn in tunnel_spans(ring):
            if rw["tread"] < tn["height"] + TUNNEL_CLEAR:
                gaps.append((s0, s1, "tunnel"))
    return gaps


def _inside(s: float, gaps, L) -> str | None:
    for a, b, kind in gaps:
        for off in (-L, 0.0, L):
            if a + off <= s <= b + off:
                return kind
    return None


def seat_rows(tier_name: str):
    """Every seat, row by row: (row index, row dict, ring, [(s, x, z, yaw)], gaps)."""
    tier = TIERS[tier_name]
    n = ROWS[tier_name]
    secs = sections(tier_name)
    for r in range(n):
        rw = row(tier, r, n)
        # A seat's feet are a third of the way back on its tread.
        ring = Ring(rw["front"] + (rw["back"] - rw["front"]) * 0.38)
        gaps = gaps_for_row(tier_name, r, secs, ring)
        seats = []
        count = int(ring.length / SEAT_PITCH)
        pitch = ring.length / count
        for i in range(count):
            s = (i + 0.5) * pitch
            # keep a seat clear of a gap by half a pitch
            if _inside(s, [(a - pitch * 0.45, b + pitch * 0.45, k) for a, b, k in gaps], ring.length):
                continue
            x, z, t = ring.at(s)
            nx, nz = inward(ring.m, t)
            seats.append((s, x, z, math.atan2(nx, nz)))
        yield r, rw, ring, seats, gaps, secs


def section_of(s: float, L: float, secs: list[dict]) -> dict:
    f = (s / L) % 1.0
    for sec in secs:
        a, b = sec["from"], sec["to"]
        if a <= f < b or a <= f + 1.0 < b:
            return sec
    return secs[-1]


def rim_mounts() -> list[dict]:
    """Light-rig mounting points on the rim, one per rim bank the tokens
    describe (angle k*pi/(count/2) + phase), with the far-side flag the scene
    uses. The Lighting actor hangs its lamps on these headframes."""
    rim = BOWL["rimLights"]
    tok = LOOK["light"]["rim"]
    count = rim["count"]
    m = TIERS["upper"]["outer"] + rim["beyondOuter"]
    y = TIERS["upper"]["rise"][1] + tok["heightAbove"]["stadium"]
    lamp = tok["lampYards"]["stadium"]
    out = []
    for k in range(count):
        t = k * math.pi / (count / 2) + tok["phase"]
        x, z = bowl_point(m, t)
        nx, nz = inward(m, t)
        # aim at midfield, dropping toward the far hash from the rim's height
        dist = math.hypot(x, z)
        pitch = -math.degrees(math.atan2(y, dist))
        out.append({"id": f"rim-{k:02d}", "angle": round(t, 5),
                    "position": [round(x, 3), round(y, 3), round(z, 3)],
                    "facing": [round(nx, 4), 0.0, round(nz, 4)],
                    "yawDegrees": round(math.degrees(math.atan2(nx, nz)), 2),
                    "pitchDegrees": round(pitch, 2),
                    "headframeYards": [round(lamp[0] + 1.0, 2), round(lamp[1] + 1.0, 2)],
                    "farSide": z <= tok["farSideMaxZ"],
                    "baseY": PARAPET["top"]})
    return out


# ───────────────────────────── contract files ─────────────────────────────

def seats_contract() -> dict:
    tiers_out = []
    total = 0
    for name in ("lower", "upper"):
        rows_out = []
        accessible = []
        secs = None
        for r, rw, ring, seats, gaps, secs in seat_rows(name):
            by_section: dict[str, list] = {}
            for s, x, z, yaw in seats:
                sec = section_of(s, ring.length, secs)
                by_section.setdefault(sec["id"], []).append([round(x, 3), round(z, 3), round(yaw, 4)])
            for a, b, kind in gaps:
                if kind == "accessible":
                    mid = (a + b) / 2
                    x, z, t = ring.at(mid)
                    nx, nz = inward(ring.m, t)
                    accessible.append({"row": r + 1, "section": section_of(mid, ring.length, secs)["id"],
                                       "centre": [round(x, 3), round(rw["tread"], 3), round(z, 3)],
                                       "yaw": round(math.atan2(nx, nz), 4), "lengthYards": round(b - a, 2)})
            count = sum(len(v) for v in by_section.values())
            total += count
            rows_out.append({"row": r + 1, "floorY": round(rw["tread"], 3),
                             "front": round(rw["front"], 3), "back": round(rw["back"], 3),
                             "feetOffset": round(ring.m, 3), "count": count,
                             "sections": by_section})
        tiers_out.append({"tier": name, "rows": rows_out, "accessible": accessible,
                          "sections": secs})
    return {
        "version": "1.0",
        "about": ("Every seat in the bowl kit. Local yards: midfield origin, +x east, +y up, "
                  "+z home sideline, -z far side (press box). A seat is [x, z, yaw]: its feet "
                  "on the row's floorY, yaw in radians about +y with 0 facing +z, so the "
                  "facing vector is (sin yaw, 0, cos yaw) and always points into the bowl. "
                  "Section ids: 1xx lower, 3xx upper, numbered from home midfield."),
        "units": "yards", "seatPitch": SEAT_PITCH, "aisle": AISLE,
        "seatHeights": {"panYards": round(0.44 / YARD, 3), "backTopYards": round(0.84 / YARD, 3),
                        "eyeSeatedYards": round(1.15 / YARD, 3)},
        "shape": SHAPE, "totalSeats": total, "tiers": tiers_out,
    }


def mounts_contract() -> dict:
    board = video_board()
    return {
        "version": "1.0",
        "about": ("Mounting points the bowl kit provides for other actors, in local yards "
                  "(see seats.json). Rim mounts are one per rim light bank; a headframe's "
                  "centre is `position`, its face looks along `facing` tipped by pitchDegrees."),
        "rim": rim_mounts(),
        "videoBoard": board,
        "ribbon": {"offset": BOWL["ribbon"]["offset"], "rise": BOWL["ribbon"]["rise"],
                   "about": "The LED ribbon's screen face on the upper fascia, all the way round; material slot ribbon_screen."},
        "wallBoards": {"offset": BOWL["wall"]["offset"], "rise": [0.22, 1.0],
                       "about": "The field wall's LED band; material slot wall_led."},
        "pressBox": BOWL["pressBox"],
        "tunnels": BOWL["tunnels"],
    }


def video_board() -> dict:
    """The end-zone video board: on the west rim, facing the field."""
    m = PARAPET["offset"] + 1.5
    x, z = bowl_point(m, math.pi)
    return {"id": "board-west", "centre": [round(x, 3), 58.0, 0.0], "facing": [1.0, 0.0, 0.0],
            "screenYards": [46.0, 16.0], "tiltDegrees": 6.0,
            "about": "Screen slot video_board_screen; content comes from the Broadcast actor."}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    seats = seats_contract()
    (OUT / "seats.json").write_text(json.dumps(seats, separators=(",", ":")))
    (OUT / "mounts.json").write_text(json.dumps(mounts_contract(), indent=1))
    per = {t["tier"]: sum(r["count"] for r in t["rows"]) for t in seats["tiers"]}
    print(f"seats: {seats['totalSeats']} {per}; sections:",
          {t["tier"]: len(t["sections"]) for t in seats["tiers"]})


if __name__ == "__main__":
    main()
