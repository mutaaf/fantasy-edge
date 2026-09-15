"""A football game as geometry: the scene every renderer draws.

The headset is not the only surface. A web board, a phone and a tablet will
draw the same stadium, and the college app draws it too, so where a pass peaks,
which lane a run takes, when a touchdown lights a section and what colour a
club's chip is are decided here, once. Every client receives primitives - arcs,
lasers, a beacon, a horizon, bowl tiers, moments - and draws them. A client
that computed its own apex would be a second answer to a question with one.

This module knows nothing about fantasy football and imports nothing but the
standard library. Its only input is gamecast-shaped: two teams, a situation,
drives of plays with a type and a start and end yard line, win probability.
That is the seam that lets it move into a shared package later.

COORDINATES
-----------
Yards, right-handed, fixed to the field rather than to whoever has the ball:

  x  yards from the HOME goal line. 0 is the home goal line, 100 the away
     one; the end zones run -10..0 and 100..110. ESPN's `yardLine` is already
     this number - checked against every play of eighteen 2025 games, where
     `yardsToEndzone` is wrong on punts and a placeholder 0 on timeouts.
  z  yards across the field from its centre line, positive toward the home
     sideline.
  y  yards up.

The home team defends x = 0 and attacks toward 100.
"""

from __future__ import annotations

import colorsys
import json
import math
import os
import pathlib

SCENE_VERSION = "1.2"

TOKENS_PATH = pathlib.Path(
    os.environ.get("FANTASYEDGE_TOKENS")
    or pathlib.Path(__file__).resolve().parent.parent / "design" / "tokens.json")

# What differs between codes of football, and nothing else. College is stubbed:
# its field geometry is here because the stadium is shared, and everything the
# scene does not yet use for it is left out rather than guessed.
# ═══════════════════════ actor sections (docs/ART_BIBLE.md) ═══════════════════════
# Each block below is owned by one stadium actor. The spec's shape does not
# change with this layout; it only says whose numbers are whose.
#
#   field       RULES[league].field            -> scene.field
#   sideline    _props()                       -> scene.field.props
#   bowl        BOWL tiers/wall/ribbon/pressBox/tunnels -> scene.bowl
#   lighting    BOWL["rimLights"]              -> scene.bowl.rimLights
#   crowd       build(): crowd, sectionTint    -> scene.bowl.crowd, .sectionTint
#   broadcast   build(): drives, ball, lasers, winProbability, PRESENTATION horizon/beacon
#   moments     build(): moments, activeMoment
#   experience  SEATS, PRESENTATION            -> scene.presentation
#   every actor tokens.json visual.<actor>     -> scene.visual.<actor>

# ── sideline ──

def _props(bench_from: float, bench_to: float, upright_above: float) -> dict:
    """The sideline furniture, in yards. Both codes share its shape; where
    they differ - the team area and the upright height - is an argument.

    The goal post stands on the end line: a base two yards behind it, a
    gooseneck forward, a crossbar 10 ft up and uprights 18 ft 6 in apart
    (field.goalPostWidth). The NFL builds its uprights 35 ft above the bar
    (2026 Rule 1 §3 Art.2); NCAA 1-2-5-a only asks for tops 30 ft off the
    ground, and college posts are built 30 ft above the bar.

    The benches sit 3.8 yd off the sideline because the bowl's front wall is
    5.4 yd out. The NFL wants them at least 30 ft 4 in back (field diagram
    note 1): that needs a wider apron than this bowl has, and is the bowl's
    change to make, not the benches'."""
    return {
        "goalpost": {"baseBehind": 2.0, "crossbar": 3.333, "uprightAbove": upright_above,
                     "radius": {"base": 0.13, "crossbar": 0.09, "upright": 0.06},
                     "padHeight": 2.2, "padWidth": 0.7, "color": "prop.goalpost"},
        "pylon": {"size": 4 / 36, "height": 0.5, "color": "prop.pylon"},
        "benches": {"fromX": bench_from, "toX": bench_to, "offset": 3.8,
                    "height": 0.5, "depth": 0.7, "backHeight": 0.65, "color": "prop.bench"},
        # The chain crew works the visitors' sideline.
        "chains": {"length": 10.0, "offset": 2.5, "poleHeight": 2.0, "markerWidth": 0.5,
                   "side": "away", "color": "prop.chain"},
    }


# ── field ──

RULES = {
    "nfl": {
        "field": {"length": 100.0, "endZone": 10.0, "width": 160 / 3,
                  # 70 ft 9 in in from each sideline; 18 ft 6 in apart.
                  "hashFromSideline": 23.583, "goalPostWidth": 6.167},
        "overtimeSeconds": 600,
        # Benches between the 30-yard lines (field diagram note 8), uprights
        # 35 ft above the crossbar (Rule 1 §3 Art.2).
        "props": _props(30.0, 70.0, 35 / 3),
    },
    "college-football": {
        "field": {"length": 100.0, "endZone": 10.0, "width": 160 / 3,
                  # 60 ft in from each sideline; 40 ft apart.
                  "hashFromSideline": 20.0, "goalPostWidth": 6.167},
        "overtimeSeconds": None,
        # The team area runs between the 20-yard lines (NCAA 1-2-4-a); posts
        # are built 30 ft above the crossbar (1-2-5-a sets the 30 ft floor).
        "props": _props(20.0, 80.0, 10.0),
        "stub": True,
    },
}

# ── field: painted art and pylon spots ──
#
# The markings themselves - lines, hashes, numerals, arrows - are baked from
# the rulebooks into assets/actors/field/markings by tools/blender/field; the
# scene only says where the two things that change per game go: each club's
# name across its end zone and the home club's ring at midfield. Glyph shapes
# are an asset (fonts/glyphs.json), so a client applies the layout below to
# them and typesets nothing itself.

GLYPHS_PATH = pathlib.Path(__file__).resolve().parent.parent / "assets" / "actors" / "field" / "fonts" / "glyphs.json"
_GLYPHS: dict | None = None
_FT = 1 / 3


def _glyphs() -> dict | None:
    global _GLYPHS
    if _GLYPHS is None and GLYPHS_PATH.is_file():
        _GLYPHS = json.loads(GLYPHS_PATH.read_text())
    return _GLYPHS


def text_width(text: str, font: dict, tracking: float = 0.08) -> float:
    """Width of a line in em units (cap height 1), as a client lays it out:
    each glyph advances by its ink width plus `tracking`, a space by
    `font.space`, and unknown characters are skipped."""
    pen, drawn = 0.0, False
    for ch in text.upper():
        if ch == " ":
            pen += font["space"]
            continue
        g = font["glyphs"].get(ch)
        if not g:
            continue
        pen += g["width"] + tracking
        drawn = True
    return max(0.0, pen - tracking) if drawn else 0.0


def field_art(field: dict, league: str, home: dict, away: dict) -> dict | None:
    """Where each club's name and the midfield ring are painted.

    A text layout maps glyph space to the field: a glyph point (gx, gy) in
    em units lands at origin + (gx * along + gy * up) * capHeight, in (x, z)
    yards. Each name reads from the field of play with its letters' tops
    toward the end line; the midfield name reads from the home sideline.
    Clearance follows NCAA 1-2-1-d, four feet from any line, which never
    breaks the NFL's Commissioner-approved rule; midfield art stays inside
    the hashes for college (1-2-1-g-3) and inside the numbers for the NFL.
    """
    font = _glyphs()
    if not font:
        return None
    tracking = 0.08
    w = field["width"]
    clear = 4 * _FT
    goal_line = 8 / 36
    depth = field["endZone"] - goal_line - 2 * clear
    span = w - 2 * clear
    zones = []
    for side, team, x_mid, along, up in (
            ("home", home, -field["endZone"] / 2 - goal_line / 2, (0.0, -1.0), (-1.0, 0.0)),
            ("away", away, field["length"] + field["endZone"] / 2 + goal_line / 2, (0.0, 1.0), (1.0, 0.0))):
        name = (team.get("name") or team.get("abbr") or "").upper()
        width = text_width(name, font, tracking)
        if not width:
            continue
        cap = min(5.0, depth * 0.78, span * 0.92 / width)
        # centre: half the width back along `along`, half the cap back along `up`
        ox = x_mid - (width * cap / 2) * along[0] - (cap / 2) * up[0]
        oz = 0.0 - (width * cap / 2) * along[1] - (cap / 2) * up[1]
        zones.append({"side": side, "text": name, "capHeight": round(cap, 4),
                      "origin": [round(ox, 4), round(oz, 4)], "along": list(along), "up": list(up),
                      "tint": "white"})
    hash_in = field["hashFromSideline"]
    if league == "college-football":
        half_span = w / 2 - hash_in - 1 * _FT
    else:
        half_span = w / 2 - (12.0 + 2.0) - 1.0          # inside the numerals' tops
    radius = min(8.0, half_span)
    name = (home.get("name") or home.get("abbr") or "").upper()
    width = text_width(name, font, tracking)
    inner = radius * 0.86
    mid = {"center": [50.0, 0.0], "outer": round(radius, 4), "inner": round(inner, 4), "tint": "home"}
    if width:
        cap = min(inner * 0.55, (2 * inner * 0.8) / width)
        mid["text"] = {"text": name, "capHeight": round(cap, 4),
                       "origin": [round(50.0 - width * cap / 2, 4), round(cap / 2, 4)],
                       "along": [1.0, 0.0], "up": [0.0, -1.0], "tint": "white"}
    return {"glyphs": "actors/field/fonts/glyphs.json", "tracking": tracking,
            "endZones": zones, "midfield": mid}


def pylon_spots(field: dict, league: str, size: float) -> list[list[float]]:
    """Pylon centres in (x, z) yards, each standing just outside the line it
    marks, touching its inside edge (NFL Rule 1 §2 Art.3; NCAA 1-2-6)."""
    half = field["width"] / 2
    s = size / 2
    end = field["endZone"]
    spots = []
    for z in (-half - s, half + s):
        spots += [[-s, z], [field["length"] + s, z]]                      # goal line x sideline
        if league == "college-football":
            spots += [[-end - s, z], [field["length"] + end + s, z]]      # end line x sideline
    hash_z = half - field["hashFromSideline"]
    back = 1.0 if league == "college-football" else 0.0                   # three feet off (1-2-6)
    for z in (-hash_z, hash_z):
        spots += [[-end - s - back, z], [field["length"] + end + s + back, z]]
    return [[round(x, 4), round(z, 4)] for x, z in spots]


# Records that are clock rather than football. They are never drawn.
NOT_A_PLAY = {"timeout", "official timeout", "end period", "end of half",
              "end of game", "end of regulation", "two-minute warning",
              "coin toss", "end of quarter"}

# ── bowl (and lighting's rimLights) ──

BOWL = {
    "shape": {"type": "superellipse", "exponent": 4.0},
    "tiers": [
        {"name": "lower", "inner": 6.0, "outer": 36.0, "rise": [1.0, 19.6], "color": "bowl.lower"},
        {"name": "upper", "inner": 42.0, "outer": 70.0, "rise": [24.0, 45.8], "color": "bowl.upper"},
    ],
    "concourse": {"inner": 36.0, "outer": 42.0, "color": "bowl.concourse"},
    # Light banks just beyond the outermost tier a renderer draws - the upper
    # deck in the stadium, the lower on the tabletop - `beyondOuter` yards out.
    # How high above that tier's top they stand is visual.lighting.rim.heightAbove.
    # side "all": a real bowl is lit from every side, so banks stand all the
    # way round; the ones facing the seats (z <= farSideMaxZ) carry the
    # detailed model and the beams, the rest the cheap one. "far" draws only
    # the banks facing the seats.
    "rimLights": {"count": 16, "beyondOuter": 1.0, "side": "all", "color": "rim.light"},
    # The stands' front wall, lined with LED boards, short of the first row;
    # the ribbon board on the upper deck's fascia, all the way round; the
    # press box in the far concourse; tunnels under each end zone.
    "wall": {"offset": 5.4, "height": 1.4, "color": "board.base"},
    "ribbon": {"offset": 41.6, "rise": [21.0, 23.6], "color": "ribbon.base", "text": "ribbon.text"},
    # The club and the press box sit under the upper deck, behind the ribbon
    # fascia rather than in front of it, so the ribbon is never hidden; they
    # glow in the band between the concourse and the fascia's underside.
    "pressBox": {"side": "far", "fromX": 22.0, "toX": 78.0, "offset": 42.4, "depth": 4.1,
                 "rise": [19.6, 23.9], "mullionEvery": 3.0, "glass": "pressbox.glass",
                 "glassBrightness": 0.38},
    "tunnels": [{"x": -16.0, "width": 7.0, "height": 3.2},
                {"x": 116.0, "width": 7.0, "height": 3.2}],
    # How the stands are divided and seated. A seat is 20 in on centre, an
    # aisle 44 in; sections run radially so aisles line up row to row. Every
    # Nth section carries a vomitory through the rows named, with an accessible
    # platform on the row in front of it. Tunnel rows are cut where a row's
    # tread is lower than the tunnel's height plus `tunnelClear`.
    "seating": {"pitch": 0.55, "aisle": 1.2, "feetDepth": 0.38,
                "seatsPerSection": {"lower": 24, "upper": 26},
                "vomitory": {"lower": {"every": 3, "phase": 1, "rows": [11, 16], "width": 3.0},
                             "upper": {"every": 4, "phase": 2, "rows": [7, 11], "width": 3.0}},
                "accessibleMargin": 1.1, "tunnelClear": 0.9,
                "startAngle": 1.5707963267948966},
    # The rim the upper tier ends in: a parapet this far out and this high.
    # Light rigs stand on it (`mounts.rim`).
    "parapet": {"offset": 70.6, "top": 47.6},
}


# The bowl's curve, rows and seats. Pure arithmetic, reproduced exactly by
# SceneMath (bowlPoint, inward, row, evenAngles), so every client lands a seat
# on the same spot of the same row.

def bowl_point(shape: dict, m: float, t: float) -> tuple[float, float]:
    a, b = shape["halfLength"] + m, shape["halfWidth"] + m
    e = 2 / shape["exponent"]
    c, s = math.cos(t), math.sin(t)
    return (a * math.copysign(abs(c) ** e, c), b * math.copysign(abs(s) ** e, s))


def bowl_inward(shape: dict, m: float, t: float) -> tuple[float, float]:
    e = 1e-3
    ax, az = bowl_point(shape, m, t - e)
    bx, bz = bowl_point(shape, m, t + e)
    nx, nz = -(bz - az), bx - ax
    hx, hz = bowl_point(shape, m, t)
    if nx * hx + nz * hz > 0:
        nx, nz = -nx, -nz
    n = math.hypot(nx, nz) or 1e-9
    return (nx / n, nz / n)


class BowlRing:
    """A superellipse at offset m, walked by arc length from angle 0."""

    RES = 2880

    def __init__(self, shape: dict, m: float):
        self.shape, self.m = shape, m
        self.t = [2 * math.pi * i / self.RES for i in range(self.RES + 1)]
        self.cum = [0.0]
        px, pz = bowl_point(shape, m, 0.0)
        for t in self.t[1:]:
            x, z = bowl_point(shape, m, t)
            self.cum.append(self.cum[-1] + math.hypot(x - px, z - pz))
            px, pz = x, z
        self.length = self.cum[-1]

    def angle(self, s: float) -> float:
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

    def arc_at(self, t: float) -> float:
        i = min(self.RES, max(0, round((t % (2 * math.pi)) / (2 * math.pi) * self.RES)))
        return self.cum[i]


def bowl_row(tier: dict, r: int, rows: int) -> dict:
    """SceneMath.row, exactly."""
    n = max(1, rows)
    depth = (tier["outer"] - tier["inner"]) / n
    front = tier["inner"] + depth * r
    rise = tier["rise"][1] - tier["rise"][0]
    return {"front": front, "back": front + depth,
            "tread": tier["rise"][0] + rise * (r + 1) / n,
            "riserFrom": tier["rise"][0] + rise * r / n}


def _bowl_side(shape: dict, t: float) -> str:
    x, z = bowl_point(shape, 0.0, t)
    if abs(x) > shape["halfLength"] - 2 and abs(z) < shape["halfWidth"]:
        return "east" if x > 0 else "west"
    return "home" if z > 0 else "far"


def bowl_sections(shape: dict, tier: dict, cfg: dict) -> list[dict]:
    """Radial sections by arc-length fraction at the tier's middle row,
    numbered from the home 50-yard line (1xx lower, 3xx upper)."""
    name = tier["name"]
    mid = BowlRing(shape, (tier["inner"] + tier["outer"]) / 2)
    width = cfg["seatsPerSection"][name] * cfg["pitch"] + cfg["aisle"]
    count = max(8, round(mid.length / width))
    start = mid.arc_at(cfg["startAngle"]) / mid.length
    base = {"lower": 100, "upper": 300}.get(name, 500)
    v = cfg["vomitory"].get(name)
    out = []
    for k in range(count):
        f0 = (start + k / count) % 1.0
        t_mid = mid.angle((f0 + 0.5 / count) * mid.length)
        out.append({"id": str(base + k + 1), "from": round(f0, 6), "to": round(f0 + 1 / count, 6),
                    "side": _bowl_side(shape, t_mid),
                    "vomitory": bool(v and k % v["every"] == v["phase"])})
    return out


def bowl_gaps(shape: dict, tier: dict, r: int, rows: int, secs: list[dict], ring: BowlRing,
              cfg: dict, tunnels: list[dict]) -> list[tuple[float, float, str]]:
    """Arc-length stretches of a row with no seats: aisles, vomitories, the
    accessible platform in front of each, and team tunnels."""
    L = ring.length
    gaps = []
    v = cfg["vomitory"].get(tier["name"])
    for sec in secs:
        s = sec["from"] * L
        gaps.append((s - cfg["aisle"] / 2, s + cfg["aisle"] / 2, "aisle"))
        if v and sec["vomitory"]:
            c = (sec["from"] + sec["to"]) / 2 * L
            half = v["width"] / 2
            if v["rows"][0] <= r <= v["rows"][1]:
                gaps.append((c - half, c + half, "vomitory"))
            elif r == v["rows"][0] - 1:
                gaps.append((c - half - cfg["accessibleMargin"], c + half + cfg["accessibleMargin"], "accessible"))
    if tier["name"] == "lower":
        tread = bowl_row(tier, r, rows)["tread"]
        for tn in tunnels:
            if tread < tn["height"] + cfg["tunnelClear"]:
                s = ring.arc_at(0.0 if tn["x"] > 50 else math.pi)
                half = tn["width"] / 2 + 1.0
                gaps.append((s - half, s + half, "tunnel"))
    return gaps


def _covered(s: float, gaps, L: float) -> bool:
    for a, b, _ in gaps:
        for off in (-L, 0.0, L):
            if a + off <= s <= b + off:
                return True
    return False


_SEATING_CACHE: dict = {}


def bowl_seating(shape: dict, rows: dict) -> dict:
    """Every seat as runs along its row: `[firstArc, count]` in yards along the
    row's ring (offset `feet`, walked from angle 0), `pitch` apart. A client
    finds seat k of a run at arc firstArc + k * pitch, turns it into an angle
    by inverting arc length (SceneMath.evenAngles' walk), and faces it along
    SceneMath.inward. The same numbers build the Blender kit."""
    key = (shape["halfLength"], shape["halfWidth"], shape["exponent"], tuple(sorted(rows.items())))
    if key in _SEATING_CACHE:
        return _SEATING_CACHE[key]
    cfg = BOWL["seating"]
    tiers_out, total = [], 0
    for tier in BOWL["tiers"]:
        n = rows.get(tier["name"], 20)
        secs = bowl_sections(shape, tier, cfg)
        rows_out, accessible = [], []
        for r in range(n):
            rw = bowl_row(tier, r, n)
            ring = BowlRing(shape, rw["front"] + (rw["back"] - rw["front"]) * cfg["feetDepth"])
            gaps = bowl_gaps(shape, tier, r, n, secs, ring, cfg, BOWL["tunnels"])
            count = int(ring.length / cfg["pitch"])
            pitch = ring.length / count
            runs, run_start, run_len = [], None, 0
            for i in range(count):
                s = (i + 0.5) * pitch
                clear = not _covered(s, [(a - pitch * 0.45, b + pitch * 0.45, k) for a, b, k in gaps], ring.length)
                if clear:
                    if run_start is None:
                        run_start, run_len = s, 0
                    run_len += 1
                elif run_start is not None:
                    runs.append([round(run_start, 3), run_len])
                    run_start = None
            if run_start is not None:
                runs.append([round(run_start, 3), run_len])
            for a, b, kind in gaps:
                if kind == "accessible":
                    accessible.append({"row": r + 1, "arc": round(((a + b) / 2) % ring.length, 3),
                                       "length": round(b - a, 2)})
            seated = sum(k for _, k in runs)
            total += seated
            rows_out.append({"row": r + 1, "floor": round(rw["tread"], 3), "feet": round(ring.m, 3),
                             "length": round(ring.length, 3), "pitch": round(pitch, 5),
                             "seats": seated, "runs": runs})
        tiers_out.append({"tier": tier["name"], "sections": secs, "rows": rows_out,
                          "accessible": accessible})
    out = {**json.loads(json.dumps(cfg)), "total": total, "tiers": tiers_out}
    _SEATING_CACHE[key] = out
    return out


def bowl_mounts(shape: dict, rim_tokens: dict) -> dict:
    """Where the bowl offers a place to hang things. `rim`: one headframe per
    rim light bank at angle k*pi/(count/2) + phase, on the parapet, facing
    midfield. Lighting hangs its lamps on these."""
    rim = BOWL["rimLights"]
    count = rim["count"]
    upper = next(t for t in BOWL["tiers"] if t["name"] == "upper")
    m = upper["outer"] + rim["beyondOuter"]
    y = upper["rise"][1] + rim_tokens["heightAbove"]["stadium"]
    lamp = rim_tokens["lampYards"]["stadium"]
    out = []
    for k in range(count):
        t = k * math.pi / (count / 2) + rim_tokens["phase"]
        x, z = bowl_point(shape, m, t)
        nx, nz = bowl_inward(shape, m, t)
        out.append({"id": f"rim-{k:02d}", "angle": round(t, 5),
                    "position": [round(x, 3), round(y, 3), round(z, 3)],
                    "facing": [round(nx, 4), 0.0, round(nz, 4)],
                    "pitch": round(-math.degrees(math.atan2(y, math.hypot(x, z))), 2),
                    "headframe": [round(lamp[0] + 1.0, 2), round(lamp[1] + 1.0, 2)],
                    "base": BOWL["parapet"]["top"],
                    "farSide": z <= rim_tokens["farSideMaxZ"]})
    return {"rim": out}


def _tier_height(name: str, offset: float) -> float:
    tier = next(t for t in BOWL["tiers"] if t["name"] == name)
    f = max(0.0, min(1.0, (offset - tier["inner"]) / (tier["outer"] - tier["inner"])))
    return round(tier["rise"][0] + (tier["rise"][1] - tier["rise"][0]) * f, 3)


def _seat(sid: str, label: str, x: float, z: float, tier: str | None, offset: float,
          look_at=(50.0, 0.0, 0.0), floor: float | None = None, group: str = "sideline") -> dict:
    """A place to sit: the floor under the wearer, in field yards, and the
    point the seat faces. Heights come from the bowl, so a seat is always on a
    row rather than floating in front of one; `floor` is for the one seat that
    is not on a tier, the press box.

    `view` is what a seat picker shows before you move: how far the nearest
    edge of the playing surface (end zones included) is, how high the floor is,
    and which part of the ground it is in. Worked out here so every client says
    the same thing about the same seat."""
    y = floor if floor is not None else (_tier_height(tier, offset) if tier else 0.0)
    dx = max(-10.0 - x, 0.0, x - 110.0)
    dz = max(abs(z) - 80 / 3, 0.0)
    return {"id": sid, "label": label, "x": x, "y": y, "z": round(z, 3),
            "lookAt": {"x": look_at[0], "y": look_at[1], "z": look_at[2]},
            "view": {"group": group, "distanceYards": round((dx * dx + dz * dz) ** 0.5, 1),
                     "heightYards": round(y, 1)}}


# ── experience ──

HALF_WIDTH = 80 / 3
SEATS = [
    # The first four ids are the look-dev shots' seats; keep them.
    _seat("club", "50-yard line, lower bowl", 50.0, HALF_WIDTH + 24.0, "lower", 24.0),
    _seat("field", "Field level, home sideline", 50.0, HALF_WIDTH + 4.5, None, 0.0, group="field"),
    _seat("endzone", "Behind the home end zone", -24.0, 0.0, "lower", 14.0, group="endzone"),
    _seat("upper", "Upper deck, midfield", 50.0, HALF_WIDTH + 50.0, "upper", 50.0, group="upper"),
    _seat("sideline", "Lower bowl, home 30", 30.0, HALF_WIDTH + 12.0, "lower", 12.0),
    # The last rows of the lower bowl, under the upper deck's overhang: the
    # club seats of a real ground.
    _seat("clubLevel", "Club level, midfield", 50.0, HALF_WIDTH + 34.0, "lower", 34.0, group="club"),
    # On the far side, level with the press box glass, looking across.
    _seat("pressBox", "Press box, far side", 50.0, -(HALF_WIDTH + BOWL["pressBox"]["offset"] + 1.0), None, 0.0,
          floor=BOWL["pressBox"]["rise"][0], group="press"),
]

PRESENTATION = {
    # The table model is sized for the whole two-deck bowl on its plinth, not
    # the lower bowl alone, which read as a shallow dish: the plinth reaches
    # (70 + 3) * 1.03 + a 2.4 yard bevel = 77.6 yards past the field, so the
    # model is 275 yards long and 209 deep. At 4 mm a yard that is
    # 1.10 x 0.83 m on a 1.12 x 0.45 x 0.86 m volume, and the field is 0.48 m.
    # Shrinking to fit 0.9 m instead (3.3 mm) left a 0.40 m field; keeping
    # 4.5 mm needed a 1.25 m volume, wider than the table it sits on.
    # bowlTiers stays lower-only until Bowl's table model carries the upper
    # deck; tests/test_experience.py already holds both decks to the volume.
    "tabletop": {"metersPerYard": 0.004, "volume": [1.12, 0.45, 0.86],
                 "floor": -0.2, "bowlTiers": ["lower"]},
    # `seat` is the default of `seats`, kept so a 1.0 renderer still sits down.
    "stadium": {"metersPerYard": 0.9144,
                "seat": {k: SEATS[0][k] for k in ("x", "y", "z")},
                "seats": SEATS, "defaultSeat": SEATS[0]["id"],
                "bowlTiers": ["lower", "upper"]},
    "horizon": {"z": -58.0, "y0": 52.0, "y1": 76.0},
    "beaconHeight": 22.0,
}


def load_tokens(path: pathlib.Path | str | None = None) -> dict:
    return json.loads(pathlib.Path(path or TOKENS_PATH).read_text())


# ───────────────────────────── colour ─────────────────────────────

def _rgb(hexs: str) -> tuple[float, float, float]:
    h = (hexs or "#666666").lstrip("#")
    if len(h) < 6:
        h = "666666"
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _hex(rgb) -> str:
    return "#" + "".join(f"{round(max(0.0, min(1.0, c)) * 255):02X}" for c in rgb)


def _lin(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def luminance(hexs: str) -> float:
    r, g, b = (_lin(c) for c in _rgb(hexs))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def chip(hexs: str, band: dict) -> str:
    """A club colour with its hue kept and its value solved into the band.

    Saturation gives way first when a hue cannot reach the band at any value -
    a pure blue is darker than the band even at full brightness - and a colour
    that was near-grey to begin with stays grey rather than acquiring a hue.
    """
    target = band["luminance"]
    h, s, _ = colorsys.rgb_to_hsv(*_rgb(hexs))
    s = 0.0 if s < band["neutralBelow"] else min(s, band["maxSaturation"])
    while s > 0 and luminance(_hex(colorsys.hsv_to_rgb(h, s, 1.0))) < target:
        s = max(0.0, s - 0.02)
    lo, hi = 0.0, 1.0
    for _ in range(32):
        mid = (lo + hi) / 2
        if luminance(_hex(colorsys.hsv_to_rgb(h, s, mid))) < target:
            lo = mid
        else:
            hi = mid
    return _hex(colorsys.hsv_to_rgb(h, s, (lo + hi) / 2))


def clash(a: str, b: str, band: dict) -> bool:
    (ha, sa, _), (hb, sb, _) = (colorsys.rgb_to_hsv(*_rgb(x)) for x in (a, b))
    if sa < band["neutralBelow"] and sb < band["neutralBelow"]:
        return True
    d = abs(ha - hb) * 360
    return (min(d, 360 - d) < band["clashDegrees"]
            and sa >= band["neutralBelow"] and sb >= band["neutralBelow"])


def team_chips(home: dict, away: dict, band: dict) -> tuple[dict, dict]:
    """Both chips, with the away side giving way when the two would read alike.

    Away takes its alternate colour if that is a real, different colour, and
    otherwise keeps its own and is marked `hatch` - a grey chip reads as "no
    team", not as the other team.
    """
    def one(t):
        return {"abbr": t.get("abbr", ""), "name": t.get("name", ""),
                "id": str(t.get("id", "")), "color": t.get("color", ""),
                "chip": chip(t.get("color", ""), band), "chipText": band["text"],
                "hatch": False, "score": t.get("score", 0)}
    h, a = one(home), one(away)
    if clash(h["chip"], a["chip"], band):
        alt = chip(away.get("altColor") or "", band)
        if away.get("altColor") and colorsys.rgb_to_hsv(*_rgb(alt))[1] >= band["neutralBelow"] \
                and not clash(alt, h["chip"], band):
            a["chip"] = alt
        else:
            a["hatch"] = True
    return h, a


# ───────────────────────────── plays ─────────────────────────────

def style_of(play: dict) -> tuple[str, str] | None:
    """(style, shape) for a play, or None for a clock record.

    Style decides colour and emphasis; shape decides the curve. They differ on
    purpose: a touchdown pass is styled `score` and still flies like a pass.
    """
    kind = (play.get("type") or "").strip().lower()
    if not kind or kind in NOT_A_PLAY:
        return None
    yards = play.get("yards") or 0
    if "kickoff" in kind or "punt" in kind or "field goal" in kind or "extra point" in kind:
        shape = "kick"
    elif "interception" in kind or "fumble" in kind:
        # The yards on a turnover are the return, run along the ground. Flown
        # as a pass, the 68-yard pick-six in 401772810 peaked 27 yards up.
        shape = "run"
    elif "incompletion" in kind or "pass" in kind or "reception" in kind:
        shape = "pass"
    elif "penalty" in kind:
        shape = "flat"
    else:
        shape = "run"
    if play.get("scoring"):
        return "score", shape
    if play.get("turnover"):
        return "turnover", shape
    if "penalty" in kind:
        return "penalty", "flat"
    if shape == "kick":
        return "kick", shape
    if "incompletion" in kind:
        return "incomplete", shape
    if "sack" in kind or (yards < 0 and shape in ("run", "pass")):
        return "loss", "run" if "sack" in kind else shape
    return shape, shape


def apex(shape: str, distance: float, tokens: dict) -> float:
    rule = tokens["arc"]["shape"][shape]
    return round(rule["apexBase"] + rule["apexPerYard"] * abs(distance), 3)


def seconds(style: str, distance: float, tokens: dict) -> float:
    """Roughly how long the play took in real time, clamped for animation."""
    rule = tokens["arc"]["seconds"].get(style) or tokens["arc"]["seconds"]["run"]
    motion = tokens["motion"]
    raw = rule["base"] + rule["perYard"] * abs(distance)
    return round(min(motion["maxSeconds"], max(motion["minSeconds"], raw)), 3)


def duration(real: float, speed: float, tokens: dict) -> float:
    """The animation length at a replay speed. Live is speed 1."""
    motion = tokens["motion"]
    factor = max(1.0, float(speed or 1.0) / motion["referenceSpeed"])
    return round(max(motion["floorSeconds"], real / factor), 3)


def lane(index: int, count: int, width: float, tokens: dict) -> float:
    """Where across the field a play is drawn. ESPN does not say where a play
    went laterally, so the drive is fanned across the middle only to keep its
    arcs from overlapping - a lane is a layout, not a claim."""
    spread = width * tokens["arc"]["laneSpread"]
    if count <= 1:
        return 0.0
    return round(-spread + 2 * spread * index / (count - 1), 3)


def _side(team_abbr: str, home: dict, away: dict) -> str | None:
    if team_abbr and team_abbr == home.get("abbr"):
        return "home"
    if team_abbr and team_abbr == away.get("abbr"):
        return "away"
    return None


def _num(v, default=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def moment_kind(play: dict, points: float) -> str:
    kind = (play.get("type") or "").lower()
    text = (play.get("text") or "").upper()
    if "touchdown" in kind or "TOUCHDOWN" in text:
        return "touchdown"
    if "safety" in kind or "SAFETY" in text:
        return "safety"
    if "field goal" in kind or points == 3:
        return "fieldGoal"
    return "score"


# ───────────────────────────── the scene ─────────────────────────────

def build(game: dict, league: str = "nfl", speed: float = 1.0,
          tokens: dict | None = None) -> dict:
    """The scene for one game at one instant. Pure: `game` is not touched."""
    tokens = tokens or load_tokens()
    rules = RULES.get(league)
    if rules is None:
        raise ValueError(f"no field rules for {league!r}; known: {', '.join(RULES)}")
    field = dict(rules["field"])
    width = field["width"]
    band = tokens["chip"]
    home, away = team_chips(game.get("home") or {}, game.get("away") or {}, band)
    sit = game.get("situation") or {}

    drives_out, moments = [], []
    prev_home = prev_away = 0.0
    last_ref = None
    raw_drives = game.get("drives") or []
    for di, drive in enumerate(raw_drives):
        plays = [p for p in (drive.get("plays") or []) if style_of(p)]
        arcs = []
        for pi, play in enumerate(plays):
            style, shape = style_of(play)
            x0, x1 = play.get("fromYard"), play.get("toYard")
            if x0 is None or x1 is None:
                continue
            dist = abs(_num(x1) - _num(x0))
            real = seconds(style, dist, tokens)
            arcs.append({
                "id": str(play.get("id", "")),
                "style": style, "shape": shape,
                "type": play.get("type", ""),
                "fromX": _num(x0), "toX": _num(x1),
                "lane": lane(pi, len(plays), width, tokens),
                "apex": apex(shape, dist, tokens),
                "color": f"arc.{style}",
                "dash": tokens["arc"]["dash"].get(style),
                "seconds": real,
                "duration": duration(real, speed, tokens),
                "side": _side(play.get("team") or drive.get("team", ""), home, away),
                "text": play.get("text", ""),
                "period": play.get("period"), "clock": play.get("clock", ""),
                "down": play.get("down"), "distance": play.get("distance"),
            })
            last_ref = (len(drives_out), len(arcs) - 1)
        for play in (drive.get("plays") or []):
            h, a = _num(play.get("home"), prev_home), _num(play.get("away"), prev_away)
            if h > prev_home or a > prev_away:
                scorer = "home" if h - prev_home >= a - prev_away else "away"
                points = max(h - prev_home, a - prev_away)
                moments.append({"kind": moment_kind(play, points), "side": scorer,
                                "team": (home if scorer == "home" else away)["abbr"],
                                "points": points, "playId": str(play.get("id", "")),
                                "text": play.get("text", ""),
                                "period": play.get("period"), "clock": play.get("clock", "")})
            elif play.get("turnover") and style_of(play):
                offense = _side(play.get("team") or drive.get("team", ""), home, away)
                taker = {"home": "away", "away": "home"}.get(offense)
                if taker:
                    moments.append({"kind": "turnover", "side": taker,
                                    "team": (home if taker == "home" else away)["abbr"],
                                    "points": 0, "playId": str(play.get("id", "")),
                                    "text": play.get("text", ""),
                                    "period": play.get("period"),
                                    "clock": play.get("clock", "")})
            # A running maximum, not the last record's score. After a
            # touchdown ESPN's timeout records can carry the score from before
            # the conversion - 38, then 36, 36, then 38 again at "End of Game"
            # in 401772949 - and trusting the dip invents a second score.
            prev_home, prev_away = max(prev_home, h), max(prev_away, a)
        drives_out.append({"id": str(drive.get("id", "")), "team": drive.get("team", ""),
                           "side": _side(drive.get("team", ""), home, away),
                           "result": drive.get("result", ""), "arcs": arcs})

    # 1.1: whether a moment stops the stadium, and where its banner, light and
    # sound go - the middle of the end zone the scoring side attacks. Home
    # attacks x = 100, so a home score lands in 100..110.
    celebrate = set(tokens["visual"]["moments"]["celebrate"])
    for m in moments:
        m["celebrates"] = m["kind"] in celebrate
        ez = field["endZone"]
        m["anchor"] = {"x": field["length"] + ez / 2 if m["side"] == "home" else -ez / 2,
                       "y": 0.0, "z": 0.0}

    state = game.get("state", "pre")
    current = len(drives_out) - 1 if drives_out and state == "in" else None

    # The instant's moment: the newest one, but only while its play is still
    # the last thing that happened. A touchdown from the first quarter is not
    # lighting a section in the third.
    # A moment holds until the game clock moves. The try, a timeout and the
    # kickoff that follow a touchdown all carry its clock - 12:51 for the
    # pick-six in 401772810 - so they arrive in the same poll, and "until the
    # next drawn play" cleared the touchdown before a single frame showed it.
    active = None
    if moments:
        newest = moments[-1]
        drawn = [(a["id"], a["period"], a["clock"]) for d in drives_out for a in d["arcs"]]
        ids = [x[0] for x in drawn]
        if newest["playId"] in ids:
            after = drawn[ids.index(newest["playId"]) + 1:]
            if all((p, c) == (newest["period"], newest["clock"]) for _, p, c in after):
                active = newest
        elif drawn and (drawn[-1][1], drawn[-1][2]) == (newest["period"], newest["clock"]):
            active = newest
    # While a moment holds, the drive to show is the one it happened in. The
    # kickoff after a touchdown starts the next drive on the same clock, and
    # showing that drive put a kick arc in the air under a TOUCHDOWN banner
    # while the scoring play itself was nowhere to be seen.
    if active and state == "in":
        for i, d in enumerate(drives_out):
            if any(a["id"] == active["playId"] for a in d["arcs"]):
                current = i
                break

    possession = sit.get("possession")
    holder = "home" if possession and str(possession) == home["id"] else \
        "away" if possession and str(possession) == away["id"] else None
    ball, lasers = None, []
    yard_line = sit.get("yardLine")
    if state == "in" and yard_line is not None:
        x = _num(yard_line)
        scoring = bool(active and active["kind"] in ("touchdown", "fieldGoal", "safety"))
        ball = {"x": x, "y": 0.0, "z": 0.0,
                "beacon": {"height": PRESENTATION["beaconHeight"],
                           "color": "beacon.score" if scoring else "beacon"}}
        lasers.append({"kind": "scrimmage", "x": x, "color": "laser.scrimmage"})
        dist, to_goal = sit.get("distance"), sit.get("yardsToEndzone")
        if holder and dist and (to_goal is None or _num(dist) < _num(to_goal)):
            step = 1.0 if holder == "home" else -1.0
            lasers.append({"kind": "lineToGain", "x": x + step * _num(dist),
                           "color": "laser.lineToGain"})

    props = json.loads(json.dumps(rules["props"]))
    props["pylon"]["at"] = pylon_spots(field, league, props["pylon"]["size"])
    wp = [w.get("home") for w in (game.get("winProbability") or [])
          if w.get("home") is not None]
    tint_side = active["side"] if active and active["kind"] != "turnover" else None
    bowl = json.loads(json.dumps(BOWL))
    bowl["shape"].update({"halfLength": field["length"] / 2 + field["endZone"],
                          "halfWidth": width / 2})
    bowl["seating"] = bowl_seating(bowl["shape"], tokens["visual"]["bowl"]["rows"])
    bowl["mounts"] = bowl_mounts(bowl["shape"], tokens["visual"]["lighting"]["rim"])
    # Shirts wear the chip, not the raw club colour: at night a navy or a
    # black shirt is indistinguishable from an empty seat, and the chip is
    # the same hue solved into a band that reads.
    bowl["crowd"] = {"home": home["chip"], "away": away["chip"],
                     "neutral": "crowd.neutral", "dark": "crowd.dark",
                     "awaySection": {"side": "far", "fromX": 90.0}}
    bowl["sectionTint"] = {"side": tint_side,
                           "color": (home if tint_side == "home" else away)["chip"]
                           if tint_side else None,
                           "dim": tokens["motion"]["sectionDim"]}

    return {
        "version": SCENE_VERSION,
        "kind": "football-scene",
        "league": league,
        "event": str(game.get("event", "")),
        "source": "replay" if game.get("replay") else "live",
        "replay": game.get("replay"),
        "speed": float(speed or 1.0),
        "units": {"length": "yard", "time": "second"},
        "axes": {"x": "yards from the home goal line; end zones -10..0 and 100..110",
                 "z": "yards from the centre line, positive toward the home sideline",
                 "y": "yards up"},
        "field": {**field, "league": league, "stripeEvery": 5, "numbersEvery": 10,
                  "props": props,
                  "art": field_art(field, league, home, away),
                  "markings": f"actors/field/markings/{league}",
                  "homeEndZone": [-field["endZone"], 0.0],
                  "awayEndZone": [field["length"], field["length"] + field["endZone"]]},
        "teams": {"home": home, "away": away},
        "status": {"state": state, "label": game.get("label", ""),
                   "clock": game.get("clock", ""), "period": game.get("period", 0),
                   "homeScore": home["score"], "awayScore": away["score"],
                   "possession": holder, "down": sit.get("down"),
                   "distance": sit.get("distance"),
                   "downDistance": sit.get("downDistanceText") or "",
                   "redZone": bool(sit.get("isRedZone"))},
        "ball": ball,
        "lasers": lasers,
        "drives": drives_out,
        "currentDrive": current,
        "winProbability": {"side": "home", "series": wp,
                           "horizon": {**PRESENTATION["horizon"],
                                       "x0": -field["endZone"],
                                       "x1": field["length"] + field["endZone"]}},
        "moments": moments,
        "activeMoment": active,
        "bowl": bowl,
        "presentation": PRESENTATION,
        "palette": tokens["color"],
        "motion": tokens["motion"],
        "visual": tokens["visual"],
    }
