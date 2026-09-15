"""Generate every painted marking of a football field, per league, from the rules.

Output, under assets/actors/field/:

  fonts/glyphs.json                 Graduate (OFL) as triangles, cap height 1
  markings/<league>/markings.json   every line, tick, numeral and arrow as
                                    polygons in field yards, with its source rule
  markings/<league>/paint_sdf.png   R white, G yellow: signed distance to paint,
                                    0.5 at the edge, +/- SDF_RANGE_IN inches over
                                    0..1, 16 texels per yard across the canvas

Why a distance field rather than a coverage mask: a 4-inch line is under two
texels at a size the headset budget allows, so a coverage mask is soft at field
level and aliased from the stands. A distance field thresholds to a hard,
correctly-wide edge at any distance, and the same texture gives the shader its
overspray halo (d just outside 0) and paint breakup (perturb d by the turf's
blade height before thresholding) for free.

Field coordinates are yards: x from the left goal line (end zones -10..0 and
100..110), y from the near sideline (0..53.33). The canvas spans x -16..116 and
y -14..67.33 so limit lines, coaching boxes and the NFL border are included.

    blender -b --factory-startup --python tools/blender/field/make_markings.py
"""
from __future__ import annotations

import math
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import common  # noqa: E402
import rules  # noqa: E402
import teamart  # noqa: E402

import bpy  # noqa: E402
import numpy as np  # noqa: E402

FT, IN = rules.FT, rules.IN
W = 160 / 3
# 132 x 81.375 yd: whole texels at 16 per yard (2112 x 1302) and centred on
# midfield, so a half turn maps texel centres exactly onto texel centres.
CANVAS = {"x0": -16.0, "x1": 116.0, "y0": -(81.375 - W) / 2, "y1": W + (81.375 - W) / 2}
HI_PPY = 32                  # texels per yard while rasterising
OUT_PPY = 16                 # texels per yard shipped
HALF_PAD_YARDS = 1.0         # the half textures run this far past midfield
SDF_RANGE_IN = 12.0          # inches of distance either side of an edge
FONT_FILE = common.FIELD_OUT / "fonts" / "Graduate-Regular.ttf"
GLYPHS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789&.'-?"


# ───────────────────────────── glyphs ─────────────────────────────

def extract_glyphs() -> dict:
    font = bpy.data.fonts.load(str(FONT_FILE))
    out = {}
    cap = None
    for ch in "H" + GLYPHS:
        cu = bpy.data.curves.new(f"g_{ord(ch)}", "FONT")
        cu.body = ch
        cu.font = font
        cu.resolution_u = 6
        obj = bpy.data.objects.new(cu.name, cu)
        bpy.context.scene.collection.objects.link(obj)
        dg = bpy.context.evaluated_depsgraph_get()
        mesh = obj.evaluated_get(dg).to_mesh()
        mesh.calc_loop_triangles()
        vs = [v.co for v in mesh.vertices]
        tris = [[(vs[i].x, vs[i].y) for i in t.vertices] for t in mesh.loop_triangles]
        xs = [v.x for v in vs] or [0.0]
        ys = [v.y for v in vs] or [0.0]
        if ch == "H" and cap is None:
            cap = max(ys) - min(ys)
            obj.evaluated_get(dg).to_mesh_clear()
            continue
        out[ch] = {"triangles": tris, "minX": min(xs), "maxX": max(xs), "minY": min(ys), "maxY": max(ys)}
        obj.evaluated_get(dg).to_mesh_clear()
    z = out.get("0")
    if z:
        cx, cy = (z["minX"] + z["maxX"]) / 2, (z["minY"] + z["maxY"]) / 2
        hw, hh = (z["maxX"] - z["minX"]) * 0.2, (z["maxY"] - z["minY"]) * 0.14
        z["triangles"] = [t for t in z["triangles"]
                          if not all(abs(x - cx) < hw and abs(y - cy) < hh for x, y in t)]
    glyphs = {}
    for ch, g in out.items():
        s = 1.0 / cap
        glyphs[ch] = {"triangles": [[(round(x * s, 5), round(y * s, 5)) for x, y in t] for t in g["triangles"]],
                      "minX": round(g["minX"] * s, 5), "width": round((g["maxX"] - g["minX"]) * s, 5),
                      "minY": round(g["minY"] * s, 5), "maxY": round(g["maxY"] * s, 5)}
    font_json = {"font": "Graduate Regular", "licence": "SIL OFL 1.1", "capHeight": 1.0,
                 "space": 0.32, "glyphs": glyphs}
    common.write_json(common.FIELD_OUT / "fonts" / "glyphs.json", font_json)
    return font_json


# ───────────────────────────── primitives ─────────────────────────────

class Paint:
    def __init__(self):
        self.items = []

    def rect(self, x0, y0, x1, y1, kind, colour="white", rule=""):
        x0, x1 = sorted((x0, x1))
        y0, y1 = sorted((y0, y1))
        self.items.append({"kind": kind, "colour": colour, "rule": rule,
                           "poly": [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]})

    def tris(self, triangles, kind, colour="white", rule=""):
        self.items.append({"kind": kind, "colour": colour, "rule": rule, "triangles": triangles})

    def dashed_x(self, x0, x1, yc, width, dash, gap, kind, colour, rule):
        x = x0
        while x < x1 - 1e-6:
            self.rect(x, yc - width / 2, min(x + dash, x1), yc + width / 2, kind, colour, rule)
            x += dash + gap

    def dashed_y(self, xc, y0, y1, width, dash, gap, kind, colour, rule):
        y = y0
        while y < y1 - 1e-6:
            self.rect(xc - width / 2, y, xc + width / 2, min(y + dash, y1), kind, colour, rule)
            y += dash + gap

    def dashed_segment(self, a, b, width, dash, gap, kind, colour, rule):
        """Dashes centred on the segment, so a segment and its half-turn image
        dash identically."""
        (ax, ay), (bx, by) = a, b
        length = math.hypot(bx - ax, by - ay)
        ux, uy = (bx - ax) / length, (by - ay) / length
        nx, ny = -uy * width / 2, ux * width / 2
        count = max(1, int((length + gap) // (dash + gap)))
        t = (length - (count * dash + (count - 1) * gap)) / 2
        while t < length - 1e-6:
            t1 = min(t + dash, length)
            p0 = (ax + ux * t, ay + uy * t)
            p1 = (ax + ux * t1, ay + uy * t1)
            quad = [(p0[0] - nx, p0[1] - ny), (p1[0] - nx, p1[1] - ny), (p1[0] + nx, p1[1] + ny), (p0[0] + nx, p0[1] + ny)]
            self.items.append({"kind": kind, "colour": colour, "rule": rule, "poly": quad})
            t += dash + gap


def numeral_triangles(digit: str, font: dict, box_x0: float, base_y: float, height: float,
                      box_w: float, flip: bool):
    """One digit, cap height `height`, centred in a box `box_w` wide.

    Unflipped reads from the near sideline (up = +y). Flipped reads from the
    far sideline: rotated 180 degrees about the box centre.
    """
    g = font["glyphs"][digit]
    s = height
    w = g["width"] * s
    if w > box_w:                           # never wider than the rule allows
        s = box_w / g["width"]
        w = box_w
    dx = box_x0 + (box_w - w) / 2 - g["minX"] * s
    cx, cy = box_x0 + box_w / 2, base_y + height / 2
    out = []
    for t in g["triangles"]:
        pts = []
        for x, y in t:
            px, py = dx + x * s, base_y + y * s
            if flip:
                px, py = 2 * cx - px, 2 * cy - py
            pts.append((px, py))
        out.append(pts)
    return out


# Marks that cross midfield but are not their own half-turn image. A coaching
# box hatch is a slash on both sidelines, so the one that happens to straddle
# the fifty would print twice; it is dropped and its neighbours carry the box.
NOT_SELF_SYMMETRIC = {"coachingBoxHatch"}


def symmetrize(p: Paint) -> Paint:
    """Keep the left half, add its half-turn image, keep self-symmetric marks
    that cross midfield. The field is then symmetric by construction, which is
    what lets a renderer ship half the texture."""
    def pts(it):
        return it["poly"] if "poly" in it else [q for t in it["triangles"] for q in t]

    def turned(it):
        rec = dict(it)
        if "poly" in it:
            rec["poly"] = [(100 - x, W - y) for x, y in it["poly"]]
        else:
            rec["triangles"] = [[(100 - x, W - y) for x, y in t] for t in it["triangles"]]
        return rec
    out = Paint()
    eps = 1e-6
    for it in p.items:
        xs = [q[0] for q in pts(it)]
        if max(xs) <= 50 + eps:
            out.items += [it, turned(it)]
        elif min(xs) >= 50 - eps:
            continue
        elif it["kind"] not in NOT_SELF_SYMMETRIC:
            out.items.append(it)
    return out


def build(league_name: str, font: dict) -> Paint:
    L = rules.league(league_name)
    P = L["paint"]
    geo = L["scene"]["field"]
    nfl = league_name == "nfl"
    p = Paint()
    lw = P["line"]
    src = P["source"]

    # Boundaries sit outside the field: measurements are to their inside edges.
    if P["boundary"]["kind"] == "border":
        b = P["boundary"]["width"]
        p.rect(-10 - b, -b, 110 + b, 0, "border", rule=src + " §1 Art.2")
        p.rect(-10 - b, W, 110 + b, W + b, "border", rule=src + " §1 Art.2")
        p.rect(-10 - b, 0, -10, W, "border", rule=src + " §1 Art.2")
        p.rect(110, 0, 110 + b, W, "border", rule=src + " §1 Art.2")
    else:
        b = P["boundary"]["width"]
        p.rect(-10 - b, -b, 110 + b, 0, "sideline", rule=src + " 1-2-1-a")
        p.rect(-10 - b, W, 110 + b, W + b, "sideline", rule=src + " 1-2-1-a")
        p.rect(-10 - b, 0, -10, W, "endLine", rule=src + " 1-2-1-a")
        p.rect(110, 0, 110 + b, W, "endLine", rule=src + " 1-2-1-a")

    # Goal lines: the whole width of the line is in the end zone.
    gl = P["goalLine"]
    p.rect(-gl, 0, 0, W, "goalLine", rule=src)
    p.rect(100, 0, 100 + gl, W, "goalLine", rule=src)

    # Yard lines every five, stopping short of the boundary.
    stop = P["yardLineStopShort"]
    for x in range(5, 100, 5):
        p.rect(x - lw / 2, stop, x + lw / 2, W - stop, "yardLine", rule=src)
        if P["yardLineIntoBorder"]:
            e = P["yardLineIntoBorder"]
            bw = P["boundary"]["width"]
            p.rect(x - lw / 2, -bw - e, x + lw / 2, -bw, "yardLineExtension", rule=src)
            p.rect(x - lw / 2, W + bw, x + lw / 2, W + bw + e, "yardLineExtension", rule=src)

    # Hash marks: inbound edge at the rule distance, running toward the sideline.
    h = P["hash"]
    assert abs(h["fromSideline"] - geo["hashFromSideline"]) < 1e-3, "rules and scene disagree on hashes"
    ticks = P["sideTicks"]
    for x in range(1, 100):
        if x % 5 == 0:
            continue
        p.rect(x - h["width"] / 2, h["fromSideline"] - h["length"], x + h["width"] / 2, h["fromSideline"], "hash", rule=src)
        p.rect(x - h["width"] / 2, W - h["fromSideline"], x + h["width"] / 2, W - h["fromSideline"] + h["length"], "hash", rule=src)
        t0 = ticks["fromBorder"]
        p.rect(x - lw / 2, t0, x + lw / 2, t0 + ticks["length"], "sideTick", rule=src)
        p.rect(x - lw / 2, W - t0 - ticks["length"], x + lw / 2, W - t0, "sideTick", rule=src)

    # Numerals and arrows, both sidelines.
    n = P["numbers"]
    if "bottomFromSideline" in n:
        bottom = n["bottomFromSideline"]
    else:
        bottom = n["topFromSideline"] - n["height"]
    height, box_w = n["height"], n["width"]
    half_gap = 2.25 * FT if nfl else 1.5 * FT       # NFL diagram: 6'-3" yard line to number edge
    ar = P["arrows"]
    alt = math.sqrt(ar["longSide"] ** 2 - (ar["base"] / 2) ** 2)
    for x in range(10, 100, 10):
        label = str(x if x <= 50 else 100 - x)
        tens, ones = label[0], label[1]
        for side in ("near", "far"):
            flip = side == "far"
            base = bottom if not flip else W - bottom - height
            left_digit, right_digit = (tens, ones) if not flip else (ones, tens)
            p.tris(numeral_triangles(left_digit, font, x - half_gap - box_w, base, height, box_w, flip),
                   "numeral", rule=n["rule"])
            p.tris(numeral_triangles(right_digit, font, x + half_gap, base, height, box_w, flip),
                   "numeral", rule=n["rule"])
            if x == 50:
                continue
            goalward = -1 if x < 50 else 1
            outer_edge = x + goalward * (half_gap + box_w)
            top = base + height if not flip else base
            down = -1 if not flip else 1                 # "below the top" is toward the sideline
            yb0 = top + down * ar["belowTop"]
            yb1 = yb0 + down * ar["base"]
            xb = outer_edge + goalward * ar["fromNumberEdge"]
            apex = (xb + goalward * alt, (yb0 + yb1) / 2)
            p.tris([[(xb, yb0), (xb, yb1), apex]], "arrow", rule=src + " arrows")

    # The try mark.
    tm = P["tryMark"]
    for gx, d in ((0, 1), (100, -1)):
        xc = gx + d * tm["distance"]
        p.rect(xc - lw / 2, W / 2 - tm["length"] / 2, xc + lw / 2, W / 2 + tm["length"] / 2, "tryMark", rule=tm.get("note", src))

    # Team areas, limit lines and coaching lines.
    lim = P["limitLine"]
    ba = P["benchArea"]
    if nfl:
        bw = P["boundary"]["width"]
        y_lim = bw + lim["beyondBorderNonBench"]
        bench_back = ba["benchesBack"] + 6 * FT
        for sgn, y_side in ((-1, 0.0), (1, W)):
            def Y(d): return y_side + sgn * d
            a, bpt = (-10, Y(y_lim)), (ba["angleFromYard"], Y(y_lim))
            p.dashed_segment(a, bpt, lim["width"], lim["dash"], lim["gap"], "limitLine", "yellow", src + " notes 1")
            p.dashed_segment((ba["angleFromYard"], Y(y_lim)), (ba["fromYard"], Y(bench_back)), lim["width"], lim["dash"], lim["gap"], "limitLine", "yellow", src + " notes 1")
            p.dashed_segment((ba["fromYard"], Y(bench_back)), (ba["toYard"], Y(bench_back)), lim["width"], lim["dash"], lim["gap"], "limitLine", "yellow", src + " notes 1")
            p.dashed_segment((ba["toYard"], Y(bench_back)), (100 - ba["angleFromYard"], Y(y_lim)), lim["width"], lim["dash"], lim["gap"], "limitLine", "yellow", src + " notes 1")
            p.dashed_segment((100 - ba["angleFromYard"], Y(y_lim)), (110, Y(y_lim)), lim["width"], lim["dash"], lim["gap"], "limitLine", "yellow", src + " notes 1")
            co = P["coachesLine"]
            yc = bw + co["behindBorder"]
            p.rect(ba["fromYard"], Y(yc) - co["width"] / 2, ba["toYard"], Y(yc) + co["width"] / 2, "coachesLine", "yellow", src + " notes 1")
            wb = y_lim - 3 * FT
            for (x0, x1) in ((-10, ba["angleFromYard"]), (100 - ba["angleFromYard"], 110)):
                p.dashed_segment((x0, Y(wb)), (x1, Y(wb)), 4 * IN, 4 * FT, 2 * FT, "whiteBrokenBorder", "white", src + " notes 1")
        ez = bw + lim["beyondBorderEndZone"]
        for x_end, sgn in ((-10, -1), (110, 1)):
            xc = x_end + sgn * ez
            p.dashed_segment((xc, -y_lim), (xc, W + y_lim), lim["width"], lim["dash"], lim["gap"], "limitLine", "yellow", src + " notes 1")
    else:
        y_lim = lim["beyondSideline"]
        gap = lim["gap"]
        for sgn, y_side in ((-1, 0.0), (1, W)):
            def Y(d): return y_side + sgn * d
            # broken outside the team area, solid along it (1-2-3-a)
            p.dashed_segment((-10 - y_lim, Y(y_lim)), (ba["fromYard"], Y(y_lim)), lim["width"], lim["dash"], gap, "limitLine", "yellow", src + " 1-2-3-a")
            p.rect(ba["fromYard"], Y(y_lim) - lim["width"] / 2, ba["toYard"], Y(y_lim) + lim["width"] / 2, "teamAreaLimitLine", "yellow", src + " 1-2-3-a")
            p.dashed_segment((ba["toYard"], Y(y_lim)), (110 + y_lim, Y(y_lim)), lim["width"], lim["dash"], gap, "limitLine", "yellow", src + " 1-2-3-a")
            co = P["coachesLine"]
            yc = co["beyondSideline"]
            p.rect(co["fromYard"], Y(yc) - co["width"] / 2, co["toYard"], Y(yc) + co["width"] / 2, "coachingLine", "white", src + " 1-2-4-a")
            p.rect(co["fromYard"], min(Y(0), Y(yc)), co["toYard"], max(Y(0), Y(yc)), "coachingArea", "white", src + " 1-2-1-c")
            # diagonal hatching in the coaching box, 45 degrees, one line a yard
            x = co["fromYard"]
            while x < co["toYard"] - 1e-6:
                a = (x, Y(yc))
                bb = (min(x + (y_lim - yc), co["toYard"]), Y(yc + min(y_lim - yc, co["toYard"] - x)))
                p.dashed_segment(a, bb, 4 * IN, 100.0, 0.0, "coachingBoxHatch", "white", src + " 1-2-4-a")
                x += 1.0
            rm = P["fiveYardRefMarks"]["size"]
            for xm in range(0, 101, 5):
                if co["fromYard"] <= xm <= co["toYard"]:
                    continue
                p.rect(xm - rm / 2, Y(yc) - rm / 2, xm + rm / 2, Y(yc) + rm / 2, "referenceMark", "white", src + " 1-2-4-a")
        for x_end, sgn in ((-10, -1), (110, 1)):
            xc = x_end + sgn * y_lim
            p.dashed_segment((xc, -y_lim), (xc, W + y_lim), lim["width"], lim["dash"], gap, "limitLine", "yellow", src + " 1-2-3-a")
    return symmetrize(p)


# ───────────────────────────── distance field ─────────────────────────────

def _convex_sdf(poly, X, Y):
    """Exact signed distance to a convex polygon, positive inside, in yards."""
    pts = poly
    n = len(pts)
    area = sum(pts[k][0] * pts[(k + 1) % n][1] - pts[(k + 1) % n][0] * pts[k][1] for k in range(n))
    sgn = 1.0 if area >= 0 else -1.0
    inside_d = np.full(X.shape, np.inf)
    outside_d = np.full(X.shape, np.inf)
    all_in = np.ones(X.shape, dtype=bool)
    for k in range(n):
        ax, ay = pts[k]
        bx, by = pts[(k + 1) % n]
        ex, ey = bx - ax, by - ay
        L = math.hypot(ex, ey)
        if L < 1e-12:
            continue
        # signed perpendicular distance, positive on the inner side
        perp = sgn * (ex * (Y - ay) - ey * (X - ax)) / L
        all_in &= perp >= 0
        inside_d = np.minimum(inside_d, perp)
        t = np.clip(((X - ax) * ex + (Y - ay) * ey) / (L * L), 0, 1)
        seg = np.hypot(X - (ax + t * ex), Y - (ay + t * ey))
        outside_d = np.minimum(outside_d, seg)
    return np.where(all_in, inside_d, -outside_d)


def distance_fields(p: Paint):
    """Per colour, the signed distance in yards at every shipped texel centre.

    Union of shapes is the maximum of their fields. Each shape's own field is
    exact: convex pieces analytically, glyphs by distance to their outline, so
    no triangulation edge can dent a numeral.
    """
    nx = int(round((CANVAS["x1"] - CANVAS["x0"]) * OUT_PPY))
    ny = int(round((CANVAS["y1"] - CANVAS["y0"]) * OUT_PPY))
    rng_yd = SDF_RANGE_IN * IN
    fields = {c: np.full((ny, nx), -rng_yd, dtype=np.float64) for c in ("white", "yellow")}
    xs = CANVAS["x0"] + (np.arange(nx) + 0.5) / OUT_PPY
    ys = CANVAS["y0"] + (np.arange(ny) + 0.5) / OUT_PPY

    def splat(poly, field):
        px = [q[0] for q in poly]
        py = [q[1] for q in poly]
        i0 = max(0, int(math.floor((min(px) - rng_yd - CANVAS["x0"]) * OUT_PPY)))
        i1 = min(nx, int(math.ceil((max(px) + rng_yd - CANVAS["x0"]) * OUT_PPY)) + 1)
        j0 = max(0, int(math.floor((min(py) - rng_yd - CANVAS["y0"]) * OUT_PPY)))
        j1 = min(ny, int(math.ceil((max(py) + rng_yd - CANVAS["y0"]) * OUT_PPY)) + 1)
        if i0 >= i1 or j0 >= j1:
            return
        X, Y = np.meshgrid(xs[i0:i1], ys[j0:j1])
        d = _convex_sdf(poly, X, Y)
        field[j0:j1, i0:i1] = np.maximum(field[j0:j1, i0:i1], d)

    def splat_mesh(tris, field):
        """Exact signed distance to a triangulated shape: distance to its outline
        (edges used by one triangle only), sign from whether any triangle holds
        the point. Internal edges never enter, so they cannot dent the edge."""
        count = {}
        for t in tris:
            for k in range(3):
                a = (round(t[k][0], 6), round(t[k][1], 6))
                b = (round(t[(k + 1) % 3][0], 6), round(t[(k + 1) % 3][1], 6))
                key = (a, b) if a <= b else (b, a)
                count[key] = count.get(key, 0) + 1
        outline = [e for e, c in count.items() if c == 1]
        px = [q[0] for t in tris for q in t]
        py = [q[1] for t in tris for q in t]
        i0 = max(0, int(math.floor((min(px) - rng_yd - CANVAS["x0"]) * OUT_PPY)))
        i1 = min(nx, int(math.ceil((max(px) + rng_yd - CANVAS["x0"]) * OUT_PPY)) + 1)
        j0 = max(0, int(math.floor((min(py) - rng_yd - CANVAS["y0"]) * OUT_PPY)))
        j1 = min(ny, int(math.ceil((max(py) + rng_yd - CANVAS["y0"]) * OUT_PPY)) + 1)
        X, Y = np.meshgrid(xs[i0:i1], ys[j0:j1])
        dist = np.full(X.shape, np.inf)
        for (ax, ay), (bx, by) in outline:
            ex, ey = bx - ax, by - ay
            L2 = ex * ex + ey * ey
            if L2 < 1e-14:
                continue
            t_ = np.clip(((X - ax) * ex + (Y - ay) * ey) / L2, 0, 1)
            dist = np.minimum(dist, np.hypot(X - (ax + t_ * ex), Y - (ay + t_ * ey)))
        inside = np.zeros(X.shape, dtype=bool)
        for t in tris:
            (ax, ay), (bx, by), (cx_, cy_) = t
            d1 = (bx - ax) * (Y - ay) - (by - ay) * (X - ax)
            d2 = (cx_ - bx) * (Y - by) - (cy_ - by) * (X - bx)
            d3 = (ax - cx_) * (Y - cy_) - (ay - cy_) * (X - cx_)
            inside |= ((d1 >= 0) & (d2 >= 0) & (d3 >= 0)) | ((d1 <= 0) & (d2 <= 0) & (d3 <= 0))
        d = np.where(inside, dist, -dist)
        field[j0:j1, i0:i1] = np.maximum(field[j0:j1, i0:i1], d)

    for it in p.items:
        field = fields[it["colour"]]
        if "poly" in it:
            splat(it["poly"], field)
        else:
            splat_mesh(it["triangles"], field)

    for c in fields:
        fields[c] = np.clip(fields[c], -rng_yd, rng_yd)
    return fields


def encode(p: Paint, league: str):
    """Write the full RG field, and the half the headset loads.

    A football field is symmetric under a half turn about midfield: every
    line, numeral, arrow and team-area mark maps onto itself (the "5" left of
    the fifty on one side is the "5" right of it on the other, upside down).
    So a renderer needs only x -16..50 and draws the other half rotated,
    which halves the memory. The half-canvas files are single-channel and
    sRGB-encoded, so a loader that treats them as colour decodes them straight
    back to the linear distance and a 0.5 threshold is exact.
    """
    rng_yd = SDF_RANGE_IN * IN
    fields = distance_fields(p)
    chans = [0.5 + fields[c] / (2 * rng_yd) for c in ("white", "yellow")]
    rg = np.stack(chans + [np.zeros_like(chans[0])], axis=2)[::-1]   # top row = far edge
    out = common.FIELD_OUT / "markings" / league
    common.write_png(out / "paint_sdf.png", rg)
    half = int(round((50.0 - CANVAS["x0"]) * OUT_PPY))
    # One yard of overlap past midfield: a GPU builds mips as if the texture
    # wrapped, so the last columns of a texture that stopped at x = 50 would
    # average with its first and cut a gap down the fifty at any distance.
    pad = int(round(HALF_PAD_YARDS * OUT_PPY))
    asym = {}
    for k, c in enumerate(("white", "yellow")):
        full = rg[..., k]
        left, right = full[:, :half], full[:, half:]
        asym[c] = float(np.abs(left - right[::-1, ::-1]).max())
        assert asym[c] < 0.02, f"{league} {c} paint is not half-turn symmetric ({asym[c]:.3f})"
        left = full[:, :half + pad]
        srgb = np.where(left <= 0.0031308, left * 12.92, 1.055 * np.power(np.clip(left, 0, 1), 1 / 2.4) - 0.055)
        common.write_png(out / f"paint_{c}_half.png", srgb)
    return rg, asym, half


def main():
    font = extract_glyphs()
    summary = {}
    for league in rules.LEAGUES:
        p = build(league, font)
        rg, asym, half = encode(p, league)
        prims = []
        for it in p.items:
            rec = {"kind": it["kind"], "colour": it["colour"], "rule": it["rule"]}
            if "poly" in it:
                rec["poly"] = [[round(x, 4), round(y, 4)] for x, y in it["poly"]]
            else:
                rec["triangles"] = [[[round(x, 4), round(y, 4)] for x, y in t] for t in it["triangles"]]
            prims.append(rec)
        L = rules.league(league)
        regions = {"endZones": teamart.end_zone_regions(L["paint"]),
                   "midfield": teamart.midfield_region(league, L["paint"], L["scene"]["field"]["hashFromSideline"])}
        common.write_json(common.FIELD_OUT / "markings" / league / "markings.json", {
            "league": league, "units": "yards",
            "axes": {"x": "yards from the left goal line; end zones -10..0 and 100..110",
                     "y": "yards from the near sideline, 0..53.333"},
            "canvas": {**CANVAS, "texelsPerYard": OUT_PPY, "width": rg.shape[1], "height": rg.shape[0],
                       "rowOrder": "top row is the far edge (y1)"},
            "half": {"x0": CANVAS["x0"], "x1": 50.0 + HALF_PAD_YARDS, "drawnTo": 50.0,
                     "width": half + int(round(HALF_PAD_YARDS * OUT_PPY)), "height": rg.shape[0],
                     "encoding": "sRGB-encoded linear distance; decode as colour, threshold 0.5",
                     "otherHalf": "rotate 180 degrees about (50, 26.667): u' = 1 - u, v' = 1 - v",
                     "maxAsymmetry": asym},
            "sdf": {"channels": {"r": "white", "g": "yellow"}, "edge": 0.5, "rangeInches": SDF_RANGE_IN,
                    "insideIs": "greater than 0.5"},
            "source": L["paint"]["source"], "discrepancies": [d for d in rules.DISCREPANCIES if d["league"] in (league, "both")],
            "regions": regions, "primitives": prims})
        counts = {}
        for it in p.items:
            counts[it["kind"]] = counts.get(it["kind"], 0) + 1
        summary[league] = {"primitives": len(p.items), "texture": list(rg.shape[:2]), "asymmetry": asym, "byKind": counts}
    print("MARKINGS", summary)


main()
