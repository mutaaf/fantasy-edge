"""The bowl as four models, inside the Bowl actor's budget (70k triangles,
20 draw parts, 50 MB; docs/ART_BIBLE.md).

  stands.usdz     one entity, six materials: every row's riser and tread,
                  painted aisle steps, vomitories, the padded wall, team
                  tunnels, the club and press box under the upper deck, the
                  ribbon fascia and the cantilevered lip over it, the parapet
                  and exterior fins. ~30k triangles.
  seats_far.usdz  `bands`: every row of seats as one slanted, textured band,
                  with the preset regions left out; `fill_<preset>`: those
                  regions as bands, shown for every preset but the one the
                  wearer sits in.
  near.usdz       `near_<preset>`: the foreground around each seat preset -
                  real aisle stairs, handrails, nosing strips, the seats in
                  front of you as modelled chairs, bands beyond. The actor
                  shows the one the wearer is in and hides the rest.
  table.usdz      the lower bowl stepped three rows at a time with the home
                  stands cut away, for the tabletop.

All geometry is built on the rows and seats `fantasyedge/scene.py` puts in
`bowl.seating`, so a modelled chair sits exactly where the Crowd actor seats a
fan. Faces are oriented by the normal they should have rather than by kept
winding, so nothing turns inside out on the far side of the bowl.
"""
from __future__ import annotations

import math

import bpy

import common as C
import kit
import seat as SEAT
from textures import TRIM, TRIM_U_YARDS

T = kit.TIERS
ROWS = kit.ROWS
HALF_L = kit.SHAPE["halfLength"]
RAIL_H = 1.04            # 0.95 m guard height, in yards
EYE = 1.26 / kit.YARD    # a seated eye above the tread
STEPS = {"lower": 2, "upper": 3}
LOD0_RADIUS, LOD1_RADIUS = 2.4, 7.0
CUTAWAY = kit.VISUAL["experience"]["tabletop"]["cutaway"]

# Interiors atlas regions, v: suites 0.5-1, press box 0.25-0.5, glow 0-0.25.
ATLAS = {"suites": (0.5, 1.0, 48.0), "press": (0.25, 0.5, 56.0), "glow": (0.0, 0.25, 32.0)}


def materials():
    return {
        "trim": C.material("bowl_trim", albedo="bowl_trim_albedo.jpg", normal="bowl_trim_normal.png",
                           orm="bowl_trim_orm.png", color=(1, 1, 1, 1)),
        "concrete": C.material("bowl_concrete", albedo="concrete_wall_albedo.jpg", normal="concrete_wall_normal.png",
                               orm="concrete_wall_orm.png", color=(1, 1, 1, 1)),
        "steel": C.material("bowl_steel", color=(0.05, 0.053, 0.058, 1), roughness=0.4, metallic=0.7),
        "glass": C.material("bowl_glass", color=(0.20, 0.24, 0.27, 1), roughness=0.05, metallic=0.1, alpha=0.32,
                            double_sided=True),
        "interiors": C.material("bowl_interiors", color=(0, 0, 0, 1), emission="interiors_emission.jpg",
                                emission_strength=3.5),
        # A slot: dark screens other actors light (ribbon, wall boards, tunnel header).
        "screens": C.material("bowl_screens", color=(0.012, 0.012, 0.014, 1), roughness=0.3,
                              emission_color=(0.02, 0.03, 0.05), emission_strength=1.0),
        # Double-sided: from any seat the rows in front are seen from behind,
        # and a culled band left the treads bare - a grey slab in the review
        # and the black ledge in the headset.
        "band": C.material("bowl_seat_band", color=(0.03, 0.05, 0.14, 1), albedo="seat_band_albedo.png", roughness=0.92,
                           double_sided=True),
        "stair": C.material("bowl_stair", albedo="stair_albedo.jpg", roughness=0.85, color=(1, 1, 1, 1)),
        "seat_plastic": SEAT.materials()["seat_plastic"],
        "seat_hardware": SEAT.materials()["seat_hardware"],
        "steplight": C.material("bowl_step_light", color=(0, 0, 0, 1), emission="interiors_emission.jpg",
                                emission_strength=6.0),
        "plaque": C.material("bowl_seat_plaque", albedo="seat_numbers.png", roughness=0.35, metallic=0.8,
                             color=(1, 1, 1, 1)),
        "table_trim": C.material("bowl_table_trim", albedo="table_trim_albedo.jpg", roughness=0.9, color=(1, 1, 1, 1)),
    }


# ───────────────────────────── primitives ─────────────────────────────

def pt(m, t, y):
    x, z = kit.bowl_point(m, t)
    return (x, y, z)


def band_uv(band, u0, u1, a=0.0, b=1.0):
    v0, v1 = TRIM[band]
    va, vb = v0 + (v1 - v0) * a, v0 + (v1 - v0) * b
    return ((u0, va), (u1, va), (u1, vb), (u0, vb))


def atlas_uv(region, u0, u1, a=0.0, b=1.0):
    v0, v1, per = ATLAS[region]
    va, vb = v0 + (v1 - v0) * a, v0 + (v1 - v0) * b
    return ((u0 / per, va), (u1 / per, va), (u1 / per, vb), (u0 / per, vb))


def oquad(b: C.Builder, pts, want, material, uv=((0, 0), (1, 0), (1, 1), (0, 1))):
    """A quad wound so its normal points along `want`."""
    p0, p1, _, p3 = pts
    n = C._cross(C._sub(p1, p0), C._sub(p3, p0))
    if C._dot(n, want) < 0:
        pts = (pts[1], pts[0], pts[3], pts[2])
        uv = (uv[1], uv[0], uv[3], uv[2])
    b.quad(*pts, material, uv=uv)


def inward3(m, t):
    nx, nz = kit.inward(m, t)
    return (nx, 0.0, nz)


def spans(cuts, ring):
    """Angle ranges of a ring left after removing arc-length cuts."""
    L = ring.length
    marks = []
    for a, b in cuts:
        length = b - a
        a %= L
        if a + length <= L:
            marks.append((a, a + length))
        else:
            marks.append((a, L))
            marks.append((0.0, a + length - L))
    marks.sort()
    keep, cur = [], 0.0
    for a, b in marks:
        if a > cur:
            keep.append((cur, a))
        cur = max(cur, b)
    if cur < L:
        keep.append((cur, L))
    return [(ring.angle(a), ring.angle(b) if b < L - 1e-9 else 2 * math.pi) for a, b in keep if b - a > 0.05]


def sample(base, t0, t1):
    return [t0] + [t for t in base if t0 < t < t1] + [t1]


def arclen(m, ts):
    out, acc = [0.0], 0.0
    for i in range(1, len(ts)):
        x0, z0 = kit.bowl_point(m, ts[i - 1])
        x1, z1 = kit.bowl_point(m, ts[i])
        acc += math.hypot(x1 - x0, z1 - z0)
        out.append(acc)
    return out


def cut_on_table(t0, t1):
    mid = ((t0 + t1) / 2) % (2 * math.pi)
    f = (mid if CUTAWAY["side"] == "home" else mid - math.pi) / math.pi
    return CUTAWAY["from"] < f < CUTAWAY["to"]


# ───────────────────────────── preset regions ─────────────────────────────

def presets():
    """The foreground around every seat preset that sits in a tier: its tier,
    angle, rows and lateral reach, and the wearer's eye."""
    out = []
    for s in kit.SC.SEATS:
        lx, lz = s["x"] - 50.0, s["z"]
        tier = None
        for name, tr in T.items():
            if tr["rise"][0] - 0.01 <= s["y"] <= tr["rise"][1] + 0.01 and s["y"] > 0.5:
                tier = name
        if tier is None:
            continue
        tr = T[tier]
        best = None
        for m10 in range(int(tr["inner"] * 10), int(tr["outer"] * 10) + 1, 2):
            m = m10 / 10
            for k in range(720):
                t = 2 * math.pi * k / 720
                x, z = kit.bowl_point(m, t)
                d = (x - lx) ** 2 + (z - lz) ** 2
                if best is None or d < best[0]:
                    best = (d, m, t)
        _, m, t = best
        n = ROWS[tier]
        r = min(n - 1, int((m - tr["inner"]) / ((tr["outer"] - tr["inner"]) / n)))
        rw = kit.row(tr, r, n)
        feet = kit.bowl_point(rw["front"] + (rw["back"] - rw["front"]) * kit.SEATING_CFG["feetDepth"], t)
        out.append({"id": s["id"], "tier": tier, "angle": t, "row": r,
                    "rows": (max(0, r - 13), min(n - 1, r + 2)), "reach": 30.0,
                    "eye": (feet[0], rw["tread"] + EYE, feet[1]), "feet": (feet[0], rw["tread"], feet[1])})
    return out


def in_region(region, tier_name, r, ring, s):
    if region["tier"] != tier_name or not (region["rows"][0] <= r <= region["rows"][1]):
        return False
    c = ring.arc_at(region["angle"])
    d = abs(((s - c) + ring.length / 2) % ring.length - ring.length / 2)
    return d <= region["reach"]


# ───────────────────────────── stands ─────────────────────────────

def stands_rows(b: C.Builder, tier_name: str) -> None:
    """Riser and tread for every row, cut only where the stands are open
    (vomitories, tunnels), with a painted step front across each aisle."""
    tier = T[tier_name]
    n = ROWS[tier_name]
    secs = kit.sections(tier_name)
    base = kit.adaptive_angles((tier["inner"] + tier["outer"]) / 2, tolerance=0.15, max_step=12.0)
    rise_step = (tier["rise"][1] - tier["rise"][0]) / n
    for r in range(n):
        rw = kit.row(tier, r, n)
        ring = kit.Ring(rw["front"] + (rw["back"] - rw["front"]) * kit.SEATING_CFG["feetDepth"])
        gaps = kit.gaps_for_row(tier_name, r, secs, ring)
        cuts = [(a, bb) for a, bb, k in gaps if k in ("vomitory", "tunnel")]
        f, bk, tr, rf = rw["front"], rw["back"], rw["tread"], rw["riserFrom"]
        for t0, t1 in spans(cuts, ring):
            ts = sample(base, t0, t1)
            ul = arclen(f, ts)
            for i in range(len(ts) - 1):
                ta, tb = ts[i], ts[i + 1]
                nin = inward3(f, (ta + tb) / 2)
                ua, ub = ul[i] / TRIM_U_YARDS["riser"], ul[i + 1] / TRIM_U_YARDS["riser"]
                oquad(b, (pt(f, ta, rf), pt(f, tb, rf), pt(f, tb, tr), pt(f, ta, tr)), nin, "trim",
                      band_uv("riser", ua, ub, 0.0, min(1.0, (tr - rf) / 0.9)))
                oquad(b, (pt(f, ta, tr), pt(f, tb, tr), pt(bk, tb, tr), pt(bk, ta, tr)), (0, 1, 0), "trim",
                      band_uv("tread", ua, ub))
        # painted aisle steps: one riser face per intermediate step, no volume
        L = ring.length
        for sec in secs:
            s = sec["from"] * L
            if any(a - 0.6 <= s <= bb + 0.6 for a, bb in cuts):
                continue
            ta = ring.angle(s)
            nx, nz = kit.inward(ring.m, ta)
            tan = (nz, 0.0, -nx)
            half = kit.AISLE / 2
            for k in range(1, STEPS[tier_name]):
                d = f + (bk - f) * k / STEPS[tier_name]
                x, z = kit.bowl_point(d, ta)
                h = tr + rise_step * k / STEPS[tier_name]
                P = lambda lat, y: (x + tan[0] * lat, y, z + tan[2] * lat)
                # the dark anti-slip front only: the yellow edge read as a
                # bright stripe down every aisle from across the bowl
                oquad(b, (P(-half, tr), P(half, tr), P(half, h), P(-half, h)), (nx, 0, nz), "trim",
                      band_uv("nosing", 0, kit.AISLE / TRIM_U_YARDS["nosing"], 0.0, 0.5))


def vomitories(b: C.Builder, tier_name: str) -> None:
    tier = T[tier_name]
    n = ROWS[tier_name]
    v = kit.VOMITORY[tier_name]
    r0, r1 = v["rows"]
    half = v["width"] / 2
    landing = kit.row(tier, r0 - 1, n)["tread"]
    roof = landing + 2.84
    outer = tier["outer"] if tier_name == "lower" else kit.PARAPET["offset"] - 0.1
    mid = kit.Ring((tier["inner"] + tier["outer"]) / 2)
    for sec in kit.sections(tier_name):
        if not sec["vomitory"]:
            continue
        tc = mid.angle(((sec["from"] + sec["to"]) / 2) * mid.length)
        nx, nz = kit.inward(mid.m, tc)
        tan = (nz, 0.0, -nx)
        f0 = kit.row(tier, r0, n)["front"]
        b1 = kit.row(tier, r1, n)["back"]
        nxt = kit.row(tier, r1 + 1, n)

        def Q(m, lat, y):
            x, z = kit.bowl_point(m, tc)
            return (x + tan[0] * lat, y, z + tan[2] * lat)

        for r in range(r0, r1 + 1):
            rw = kit.row(tier, r, n)
            for side in (-1, 1):
                oquad(b, (Q(rw["front"], side * half, landing), Q(rw["back"], side * half, landing),
                          Q(rw["back"], side * half, rw["tread"]), Q(rw["front"], side * half, rw["tread"])),
                      (-tan[0] * side, 0, -tan[2] * side), "concrete",
                      ((0, 0), (0.35, 0), (0.35, (rw["tread"] - landing) / 3), (0, (rw["tread"] - landing) / 3)))
        oquad(b, (Q(nxt["front"], -half, roof), Q(nxt["front"], half, roof),
                  Q(nxt["front"], half, nxt["riserFrom"]), Q(nxt["front"], -half, nxt["riserFrom"])),
              (nx, 0, nz), "trim", band_uv("riser", 0, v["width"] / 4.4, 0, 0.6))
        oquad(b, (Q(f0, -half, landing), Q(f0, half, landing), Q(outer, half, landing), Q(outer, -half, landing)),
              (0, 1, 0), "trim", band_uv("tread", 0, v["width"] / 4.4))
        oquad(b, (Q(nxt["front"], -half, roof), Q(nxt["front"], half, roof), Q(outer, half, roof), Q(outer, -half, roof)),
              (0, -1, 0), "trim", band_uv("soffit", 0, 0.5, 0, 0.5))
        for side in (-1, 1):
            oquad(b, (Q(b1, side * half, landing), Q(outer, side * half, landing), Q(outer, side * half, roof),
                      Q(b1, side * half, roof)), (-tan[0] * side, 0, -tan[2] * side), "trim",
                  band_uv("padding", 0, 1.5, 0, 1))
        oquad(b, (Q(outer - 0.05, -half, landing), Q(outer - 0.05, half, landing), Q(outer - 0.05, half, roof),
                  Q(outer - 0.05, -half, roof)), (nx, 0, nz), "interiors", atlas_uv("glow", 0, v["width"] * 3))
        top = nxt["tread"]
        oquad(b, (Q(nxt["front"] + 0.12, -half, top), Q(nxt["front"] + 0.12, half, top),
                  Q(nxt["front"] + 0.12, half, top + RAIL_H), Q(nxt["front"] + 0.12, -half, top + RAIL_H)),
              (nx, 0, nz), "glass")


def field_wall(b: C.Builder) -> None:
    wall = kit.BOWL["wall"]
    m, top = wall["offset"], wall["height"]
    ring = kit.Ring(m)
    cuts = [(s0 + 0.7, s1 - 0.7) for s0, s1, _ in kit.tunnel_spans(ring)]
    base = kit.adaptive_angles(m, tolerance=0.06, max_step=10.0)
    inner = T["lower"]["inner"]
    for t0, t1 in spans(cuts, ring):
        ts = sample(base, t0, t1)
        ul = arclen(m, ts)
        for i in range(len(ts) - 1):
            ta, tb = ts[i], ts[i + 1]
            nin = inward3(m, (ta + tb) / 2)
            u0, u1 = ul[i], ul[i + 1]
            oquad(b, (pt(m, ta, 0.0), pt(m, tb, 0.0), pt(m, tb, 0.18), pt(m, ta, 0.18)), nin, "concrete",
                  ((u0 / 3, 0), (u1 / 3, 0), (u1 / 3, 0.06), (u0 / 3, 0.06)))
            oquad(b, (pt(m - 0.02, ta, 0.18), pt(m - 0.02, tb, 0.18), pt(m - 0.02, tb, 1.0), pt(m - 0.02, ta, 1.0)),
                  nin, "screens")
            pad = [(1.0, m - 0.02), (1.06, m - 0.13), (top - 0.07, m - 0.14), (top, m - 0.05)]
            for j in range(len(pad) - 1):
                (ya, ma), (yb, mb) = pad[j], pad[j + 1]
                oquad(b, (pt(ma, ta, ya), pt(ma, tb, ya), pt(mb, tb, yb), pt(mb, ta, yb)),
                      C._norm((nin[0], 0.4, nin[2])), "trim",
                      band_uv("padding", u0 / TRIM_U_YARDS["padding"], u1 / TRIM_U_YARDS["padding"], j / 3, (j + 1) / 3))
            oquad(b, (pt(m - 0.05, ta, top), pt(m - 0.05, tb, top), pt(inner, tb, top), pt(inner, ta, top)), (0, 1, 0),
                  "trim", band_uv("tread", u0 / 4.4, u1 / 4.4, 0.6, 0.9))
            oquad(b, (pt(m + 0.3, ta, top), pt(m + 0.3, tb, top), pt(m + 0.3, tb, top + 0.92), pt(m + 0.3, ta, top + 0.92)),
                  nin, "glass")
            oquad(b, (pt(m + 0.24, ta, top + 0.92), pt(m + 0.24, tb, top + 0.92), pt(m + 0.36, tb, top + 0.95),
                      pt(m + 0.36, ta, top + 0.95)), (0, 1, 0), "steel")


def team_tunnels(b: C.Builder) -> None:
    tier = T["lower"]
    n = ROWS["lower"]
    wall_m = kit.BOWL["wall"]["offset"]
    for tn in kit.BOWL["tunnels"]:
        tc = 0.0 if tn["x"] > 50 else math.pi
        half, h = tn["width"] / 2 + 0.3, tn["height"]
        nx, nz = kit.inward(wall_m, tc)
        tan = (nz, 0.0, -nx)
        cut_rows = [r for r in range(n) if kit.row(tier, r, n)["tread"] < h + kit.TUNNEL_CLEAR]
        last, nxt = kit.row(tier, cut_rows[-1], n), kit.row(tier, cut_rows[-1] + 1, n)
        deck, end, wide = last["tread"], 20.0, half + 1.0

        def Q(m, lat, y):
            x, z = kit.bowl_point(m, tc)
            return (x + tan[0] * lat, y, z + tan[2] * lat)

        for side in (-1, 1):
            oquad(b, (Q(wall_m, side * wide, 0), Q(nxt["front"], side * wide, 0), Q(nxt["front"], side * wide, deck),
                      Q(wall_m, side * wide, deck)), (-tan[0] * side, 0, -tan[2] * side), "concrete")
        oquad(b, (Q(wall_m, -wide, deck), Q(wall_m, wide, deck), Q(nxt["front"], wide, deck), Q(nxt["front"], -wide, deck)),
              (0, 1, 0), "concrete", ((0, 0), (2 * wide / 3, 0), (2 * wide / 3, 1.5), (0, 1.5)))
        oquad(b, (Q(nxt["front"], -wide, deck), Q(nxt["front"], wide, deck), Q(nxt["front"], wide, nxt["riserFrom"]),
                  Q(nxt["front"], -wide, nxt["riserFrom"])), (nx, 0, nz), "trim", band_uv("riser", 0, 2 * wide / 4.4, 0, 0.4))
        oquad(b, (Q(wall_m, -half, 0.01), Q(wall_m, half, 0.01), Q(end, half, 0.01), Q(end, -half, 0.01)), (0, 1, 0),
              "trim", band_uv("tread", 0, 1.5))
        oquad(b, (Q(wall_m, -half, h), Q(wall_m, half, h), Q(end, half, h), Q(end, -half, h)), (0, -1, 0), "trim",
              band_uv("soffit", 0, 1.2, 0, 1))
        # padded walls at the mouth, then the corridor's light coming on
        # toward the end, so the arch reads as a deep lit tunnel, not a box
        mid = wall_m + (end - wall_m) * 0.4
        for side in (-1, 1):
            oquad(b, (Q(wall_m, side * half, 0), Q(mid, side * half, 0), Q(mid, side * half, h), Q(wall_m, side * half, h)),
                  (-tan[0] * side, 0, -tan[2] * side), "trim", band_uv("padding", 0, 1.6, 0, 1))
            for k in range(4):
                ma, mb = mid + (end - mid) * k / 4, mid + (end - mid) * (k + 1) / 4
                oquad(b, (Q(ma, side * half, 0), Q(mb, side * half, 0), Q(mb, side * half, h), Q(ma, side * half, h)),
                      (-tan[0] * side, 0, -tan[2] * side), "interiors",
                      atlas_uv("glow", 0, 4, 0.05 + 0.2 * k, 0.05 + 0.2 * (k + 1)))
        oquad(b, (Q(end, -half, 0), Q(end, half, 0), Q(end, half, h), Q(end, -half, h)), (nx, 0, nz), "interiors",
              atlas_uv("glow", 0, 16))
        arch_m = wall_m - 0.5
        yaw = math.atan2(nx, nz)
        for side in (-1, 1):
            b.box(Q(arch_m, side * (half + 0.35), deck / 2), (0.7, deck, 1.1), "steel", yaw=yaw, skip=("bottom", "top"))
        oquad(b, (Q(arch_m - 0.56, -half, h), Q(arch_m - 0.56, half, h), Q(arch_m - 0.56, half, deck - 0.05),
                  Q(arch_m - 0.56, -half, deck - 0.05)), (nx, 0, nz), "screens")
        top = [Q(wall_m + 0.3, -wide, deck + 0.95), Q(wall_m + 0.3, wide, deck + 0.95)]
        b.tube(top, 0.04, "steel", sides=5)
        for lat in (-wide, 0.0, wide):
            b.tube([Q(wall_m + 0.3, lat, deck), Q(wall_m + 0.3, lat, deck + 0.95)], 0.035, "steel", sides=4)


def club(b: C.Builder) -> None:
    """The concourse at the top of the lower bowl; the club and press box
    under the upper deck behind glass; the ribbon fascia; and the upper deck's
    cantilevered lip, whose underside is what you see from the lower rows."""
    y0 = T["lower"]["rise"][1]
    fas = kit.FASCIA
    glass_m, ceil, back = 42.4, 23.9, 46.5
    lip_m, lip_under, lip_top = 39.8, 25.0, 25.3
    pb = kit.BOWL["pressBox"]
    rib = kit.BOWL["ribbon"]["rise"]
    base = kit.adaptive_angles(40.0, tolerance=0.1, max_step=8.0)
    ul = arclen(glass_m, base)
    next_mull, next_col = 0.0, 0.0
    for i in range(len(base) - 1):
        ta, tb = base[i], base[i + 1]
        tm = (ta + tb) / 2
        nin = inward3(40.0, tm)
        x, z = kit.bowl_point(40.0, tm)
        u0, u1 = ul[i], ul[i + 1]
        end = abs(x) > HALF_L + 2
        press = False            # the press box moved to the parapet (press_box below)
        region = "press" if press else "glow" if end else "suites"
        # concourse floor, running back under the deck to the glass
        oquad(b, (pt(T["lower"]["outer"], ta, y0), pt(T["lower"]["outer"], tb, y0), pt(glass_m, tb, y0), pt(glass_m, ta, y0)),
              (0, 1, 0), "trim", band_uv("tread", u0 / 4.4, u1 / 4.4))
        # the glass wall and the lit room behind it
        if press:
            press_face(b, ta, tb, u0, u1, nin, y0)
        else:
            oquad(b, (pt(glass_m, ta, y0), pt(glass_m, tb, y0), pt(glass_m, tb, ceil), pt(glass_m, ta, ceil)), nin, "glass")
        oquad(b, (pt(back, ta, y0), pt(back, tb, y0), pt(back, tb, ceil), pt(back, ta, ceil)), nin, "interiors",
              atlas_uv(region, u0, u1))
        oquad(b, (pt(glass_m, ta, ceil), pt(glass_m, tb, ceil), pt(back, tb, ceil), pt(back, ta, ceil)), (0, -1, 0), "trim",
              band_uv("soffit", u0 / 6, u1 / 6, 0, 0.6))
        # the ribbon fascia: steel trim, the screen, concrete, and its underside
        fm, fb = fas["front"], glass_m
        for ya, yb, mat, uv in ((fas["bottom"], rib[0] + 0.12, "trim", band_uv("steel", u0 / 3, u1 / 3, 0, 0.3)),
                                (rib[0] + 0.12, rib[1] - 0.12, "screens", ((0, 0), (1, 0), (1, 1), (0, 1))),
                                (rib[1] - 0.12, rib[1], "trim", band_uv("steel", u0 / 3, u1 / 3, 0.3, 0.6)),
                                (rib[1], lip_under, "concrete", ((u0 / 3, rib[1] / 3), (u1 / 3, rib[1] / 3),
                                                                 (u1 / 3, lip_under / 3), (u0 / 3, lip_under / 3)))):
            oquad(b, (pt(fm, ta, ya), pt(fm, tb, ya), pt(fm, tb, yb), pt(fm, ta, yb)), nin, mat, uv)
        oquad(b, (pt(fm, ta, fas["bottom"]), pt(fm, tb, fas["bottom"]), pt(fb, tb, fas["bottom"]), pt(fb, ta, fas["bottom"])),
              (0, -1, 0), "concrete")
        # the lip: underside with a light cove, a thin front, glass on top
        oquad(b, (pt(lip_m, ta, lip_under), pt(lip_m, tb, lip_under), pt(fm, tb, lip_under), pt(fm, ta, lip_under)),
              (0, -1, 0), "trim", band_uv("soffit", u0 / 6, u1 / 6))
        oquad(b, (pt(lip_m + 0.35, ta, lip_under - 0.02), pt(lip_m + 0.35, tb, lip_under - 0.02),
                  pt(lip_m + 0.6, tb, lip_under - 0.02), pt(lip_m + 0.6, ta, lip_under - 0.02)), (0, -1, 0), "interiors",
              atlas_uv("glow", u0, u1, 0.6, 0.9))
        oquad(b, (pt(lip_m, ta, lip_under), pt(lip_m, tb, lip_under), pt(lip_m, tb, lip_top), pt(lip_m, ta, lip_top)), nin,
              "trim", band_uv("steel", u0 / 3, u1 / 3))
        # The deck's front: a narrow guard wall with a cap, then a walkway at
        # the first row's tread. It was a 2.2 yd slab standing proud of row 1,
        # and from every upper seat it read as a bare grey ledge.
        walk = T["upper"]["rise"][0] + (T["upper"]["rise"][1] - T["upper"]["rise"][0]) / ROWS["upper"]
        # cap = walk + GUARD["capAboveWalk"] (24.838 + 0.9), stated from the lip so
        # Lighting's concourse fill can read it (tests/test_lighting_sky.py)
        wall_f, wall_b, cap = lip_m + 0.9, lip_m + 1.15, lip_top + 0.438
        oquad(b, (pt(lip_m, ta, lip_top), pt(lip_m, tb, lip_top), pt(wall_f, tb, lip_top), pt(wall_f, ta, lip_top)),
              (0, 1, 0), "trim", band_uv("steel", u0 / 3, u1 / 3, 0.6, 1.0))
        oquad(b, (pt(wall_f, ta, lip_top), pt(wall_f, tb, lip_top), pt(wall_f, tb, cap), pt(wall_f, ta, cap)), nin,
              "concrete", ((u0 / 3, 0), (u1 / 3, 0), (u1 / 3, 0.33), (u0 / 3, 0.33)))
        oquad(b, (pt(wall_f - 0.04, ta, cap), pt(wall_f - 0.04, tb, cap), pt(wall_b + 0.04, tb, cap),
                  pt(wall_b + 0.04, ta, cap)), (0, 1, 0), "trim", band_uv("steel", u0 / 3, u1 / 3, 0.0, 0.3))
        oquad(b, (pt(wall_b, ta, walk), pt(wall_b, tb, walk), pt(wall_b, tb, cap), pt(wall_b, ta, cap)),
              (-nin[0], 0, -nin[2]), "concrete", ((u0 / 3, 0), (u1 / 3, 0), (u1 / 3, 0.4), (u0 / 3, 0.4)))
        oquad(b, (pt(wall_b + 0.01, ta, cap - 0.16), pt(wall_b + 0.01, tb, cap - 0.16), pt(wall_b + 0.01, tb, cap - 0.08),
                  pt(wall_b + 0.01, ta, cap - 0.08)), (-nin[0], 0, -nin[2]), "interiors",
              atlas_uv("glow", u0, u1, 0.75, 0.8))
        oquad(b, (pt(wall_f + 0.12, ta, cap), pt(wall_f + 0.12, tb, cap), pt(wall_f + 0.12, tb, cap + GUARD["glass"]),
                  pt(wall_f + 0.12, ta, cap + GUARD["glass"])), nin, "glass")
        oquad(b, (pt(wall_b, ta, walk), pt(wall_b, tb, walk), pt(T["upper"]["inner"], tb, walk),
                  pt(T["upper"]["inner"], ta, walk)), (0, 1, 0), "trim", band_uv("tread", u0 / 4.4, u1 / 4.4, 0.1, 0.9))
        # mullions behind the glass, columns in the open end concourses
        while next_mull <= u1:
            if next_mull >= u0:
                t = ta + (tb - ta) * (next_mull - u0) / max(1e-6, u1 - u0)
                nx, nz = kit.inward(glass_m, t)
                if not end:
                    tx, tz = nz * 0.05, -nx * 0.05
                    px, pz = kit.bowl_point(glass_m - 0.03, t)
                    oquad(b, ((px - tx, y0, pz - tz), (px + tx, y0, pz + tz), (px + tx, ceil, pz + tz), (px - tx, ceil, pz - tz)),
                          (nx, 0, nz), "steel")
            next_mull += pb["mullionEvery"] * (1 if press else 2)
        while next_col <= u1:
            if next_col >= u0 and end:
                t = ta + (tb - ta) * (next_col - u0) / max(1e-6, u1 - u0)
                nx, nz = kit.inward(40.0, t)
                b.box(pt(41.0, t, (y0 + fas["bottom"]) / 2), (0.8, fas["bottom"] - y0, 0.8), "concrete",
                      yaw=math.atan2(nx, nz), skip=("top", "bottom"), uv_scale=0.33)
            next_col += 9.0
    # the press box's broadcast bay: a glazed box pushed forward under the lip
    x0, x1 = pb["fromX"] - 50, pb["toX"] - 50
    bay_half = 6.0
    for tt in (math.pi * 1.5,):
        nx, nz = kit.inward(40.0, tt)
        tan = (nz, 0.0, -nx)

        def Q(m, lat, y):
            x, z = kit.bowl_point(m, tt)
            return (x + tan[0] * lat, y, z + tan[2] * lat)
        front, top = 39.6, fas["bottom"] - 0.05
        oquad(b, (Q(front, -bay_half, y0), Q(front, bay_half, y0), Q(front, bay_half, top), Q(front, -bay_half, top)),
              (nx, 0, nz), "glass")
        oquad(b, (Q(front + 0.8, -bay_half, y0), Q(front + 0.8, bay_half, y0), Q(front + 0.8, bay_half, top),
                  Q(front + 0.8, -bay_half, top)), (nx, 0, nz), "interiors", atlas_uv("press", 0, 2 * bay_half))
        oquad(b, (Q(front, -bay_half, top), Q(front, bay_half, top), Q(glass_m, bay_half, top), Q(glass_m, -bay_half, top)),
              (0, 1, 0), "trim", band_uv("steel", 0, 4))
        for side in (-1, 1):
            oquad(b, (Q(front, side * bay_half, y0), Q(glass_m, side * bay_half, y0), Q(glass_m, side * bay_half, top),
                      Q(front, side * bay_half, top)), (tan[0] * side, 0, tan[2] * side), "glass")
    del x0, x1


# The upper deck's guard wall: its cap above the first row's tread, and clear
# glass above that to a 1.1 m guard. Checked by tests/test_bowl.py against the
# upper preset's sightline to the near sideline.
GUARD = {"capAboveWalk": 0.9, "glass": 0.3}

PRESS = {"upstand": 37.6, "sill": 20.25, "glassTop": 38.9, "head": 20.95, "desk": 40.6}


def press_face(b: C.Builder, ta, tb, u0, u1, nin, y0) -> None:
    """The press box's face. The fascia above leaves only its bottom edge
    (bowl.ribbon.rise[0]) for a room above the concourse, so depth comes from
    projecting forward: a concrete upstand at the concourse edge, glazing
    canted out toward the field, a steel head tucked under the fascia, and a
    lit desk line inside."""
    P = PRESS
    fb = kit.FASCIA["bottom"]
    # upstand: front face, top
    oquad(b, (pt(P["upstand"], ta, y0), pt(P["upstand"], tb, y0), pt(P["upstand"], tb, P["sill"]),
              pt(P["upstand"], ta, P["sill"])), nin, "concrete",
          ((u0 / 3, 0), (u1 / 3, 0), (u1 / 3, 0.2), (u0 / 3, 0.2)))
    oquad(b, (pt(P["upstand"], ta, P["sill"]), pt(P["upstand"], tb, P["sill"]), pt(P["upstand"] + 0.45, tb, P["sill"]),
              pt(P["upstand"] + 0.45, ta, P["sill"])), (0, 1, 0), "trim", band_uv("steel", u0 / 3, u1 / 3, 0, 0.3))
    # canted glazing from the sill back up to the head under the fascia
    oquad(b, (pt(P["upstand"] + 0.3, ta, P["sill"]), pt(P["upstand"] + 0.3, tb, P["sill"]),
              pt(P["glassTop"], tb, P["head"]), pt(P["glassTop"], ta, P["head"])),
          C._norm((nin[0], 0.45, nin[2])), "glass")
    # steel head and a soffit back to the fascia's underside
    oquad(b, (pt(P["glassTop"] - 0.1, ta, P["head"]), pt(P["glassTop"] - 0.1, tb, P["head"]),
              pt(P["glassTop"] - 0.1, tb, fb), pt(P["glassTop"] - 0.1, ta, fb)), nin, "trim",
          band_uv("steel", u0 / 3, u1 / 3, 0.3, 0.6))
    oquad(b, (pt(P["glassTop"] - 0.1, ta, fb), pt(P["glassTop"] - 0.1, tb, fb), pt(kit.FASCIA["front"], tb, fb),
              pt(kit.FASCIA["front"], ta, fb)), (0, -1, 0), "trim", band_uv("soffit", u0 / 6, u1 / 6))
    # inside: a floor, and the desk line lit by its monitors
    oquad(b, (pt(P["upstand"] + 0.45, ta, P["sill"] - 0.4), pt(P["upstand"] + 0.45, tb, P["sill"] - 0.4),
              pt(P["desk"], tb, P["sill"] - 0.4), pt(P["desk"], ta, P["sill"] - 0.4)), (0, 1, 0), "trim",
          band_uv("tread", u0 / 4.4, u1 / 4.4, 0.2, 0.6))
    oquad(b, (pt(P["desk"], ta, P["sill"] - 0.4), pt(P["desk"], tb, P["sill"] - 0.4), pt(P["desk"], tb, P["sill"] + 0.35),
              pt(P["desk"], ta, P["sill"] + 0.35)), nin, "interiors", atlas_uv("press", u0, u1, 0.3, 0.55))


def mullions_press(b: C.Builder) -> None:
    """Mullions on the canted press glazing, every pressBox.mullionEvery yards."""
    pb, P = kit.BOWL["pressBox"], PRESS
    ring = kit.Ring(P["upstand"])
    s0 = ring.arc_at(math.pi * 1.5)
    half = (pb["toX"] - pb["fromX"]) / 2
    s = s0 - half
    while s <= s0 + half:
        t = ring.angle(s)
        nx, nz = kit.inward(P["upstand"], t)
        tx, tz = nz * 0.06, -nx * 0.06
        a = kit.bowl_point(P["upstand"] + 0.3, t)
        c = kit.bowl_point(P["glassTop"], t)
        oquad(b, ((a[0] - tx, P["sill"], a[1] - tz), (a[0] + tx, P["sill"], a[1] + tz),
                  (c[0] + tx, P["head"], c[1] + tz), (c[0] - tx, P["head"], c[1] - tz)),
              (nx, 0.45, nz), "steel")
        s += pb["mullionEvery"]


def press_box(b: C.Builder) -> None:
    """The press box on the far parapet (`bowl.pressBox`): a glazed room
    canted toward the field, a lit interior with a desk line, a flat roof with
    an overhang, mullions, and a back wall and ends in concrete."""
    pb = kit.BOWL["pressBox"]
    front, back = pb["offset"], pb["offset"] + pb["depth"]
    y0, y1 = pb["rise"]
    ring = kit.Ring(front)
    c = ring.arc_at(math.pi * 1.5)
    half = (pb["toX"] - pb["fromX"]) / 2
    ts = [ring.angle(c - half + 2 * half * k / 16) for k in range(17)]
    ul = arclen(front, ts)
    cant = 0.7                                 # the glass leans out at the top
    for i in range(len(ts) - 1):
        ta, tb = ts[i], ts[i + 1]
        nin = inward3(front, (ta + tb) / 2)
        u0, u1 = ul[i], ul[i + 1]
        # floor slab edge and sill
        oquad(b, (pt(front - 0.2, ta, y0 - 0.5), pt(front - 0.2, tb, y0 - 0.5), pt(front - 0.2, tb, y0 + 0.6),
                  pt(front - 0.2, ta, y0 + 0.6)), nin, "concrete", ((u0 / 3, 0), (u1 / 3, 0), (u1 / 3, 0.35), (u0 / 3, 0.35)))
        oquad(b, (pt(front - 0.2, ta, y0 - 0.5), pt(front - 0.2, tb, y0 - 0.5), pt(back, tb, y0 - 0.5),
                  pt(back, ta, y0 - 0.5)), (0, -1, 0), "trim", band_uv("soffit", u0 / 6, u1 / 6))
        # canted glazing
        oquad(b, (pt(front, ta, y0 + 0.6), pt(front, tb, y0 + 0.6), pt(front - cant, tb, y1), pt(front - cant, ta, y1)),
              C._norm((nin[0], 0.2, nin[2])), "glass")
        # the room: floor, lit back wall, desk line
        oquad(b, (pt(front, ta, y0 + 0.02), pt(front, tb, y0 + 0.02), pt(back, tb, y0 + 0.02), pt(back, ta, y0 + 0.02)),
              (0, 1, 0), "trim", band_uv("tread", u0 / 4.4, u1 / 4.4, 0.2, 0.6))
        oquad(b, (pt(back, ta, y0), pt(back, tb, y0), pt(back, tb, y1), pt(back, ta, y1)), nin, "interiors",
              atlas_uv("press", u0, u1))
        oquad(b, (pt(front + 1.2, ta, y0 + 0.9), pt(front + 1.2, tb, y0 + 0.9), pt(front + 1.2, tb, y0 + 1.5),
                  pt(front + 1.2, ta, y0 + 1.5)), nin, "interiors", atlas_uv("press", u0, u1, 0.3, 0.55))
        # roof with an overhang, and its fascia edge
        oquad(b, (pt(front - cant - 0.9, ta, y1 + 0.35), pt(front - cant - 0.9, tb, y1 + 0.35), pt(back + 0.2, tb, y1 + 0.35),
                  pt(back + 0.2, ta, y1 + 0.35)), (0, 1, 0), "trim", band_uv("steel", u0 / 3, u1 / 3, 0.6, 1.0))
        oquad(b, (pt(front - cant - 0.9, ta, y1), pt(front - cant - 0.9, tb, y1), pt(back, tb, y1), pt(back, ta, y1)),
              (0, -1, 0), "trim", band_uv("soffit", u0 / 6, u1 / 6))
        oquad(b, (pt(front - cant - 0.9, ta, y1), pt(front - cant - 0.9, tb, y1), pt(front - cant - 0.9, tb, y1 + 0.35),
                  pt(front - cant - 0.9, ta, y1 + 0.35)), nin, "steel")
        # back wall outside
        oquad(b, (pt(back + 0.2, ta, y0 - 0.5), pt(back + 0.2, tb, y0 - 0.5), pt(back + 0.2, tb, y1 + 0.35),
                  pt(back + 0.2, ta, y1 + 0.35)), (-nin[0], 0, -nin[2]), "concrete",
              ((u0 / 3, 0), (u1 / 3, 0), (u1 / 3, 1.4), (u0 / 3, 1.4)))
        # mullion at the segment start
        nx, nz = kit.inward(front, ta)
        tx, tz = nz * 0.07, -nx * 0.07
        a = kit.bowl_point(front, ta)
        cc = kit.bowl_point(front - cant, ta)
        oquad(b, ((a[0] - tx, y0 + 0.6, a[1] - tz), (a[0] + tx, y0 + 0.6, a[1] + tz), (cc[0] + tx, y1, cc[1] + tz),
                  (cc[0] - tx, y1, cc[1] - tz)), (nx, 0.2, nz), "steel")
    # end walls
    for t in (ts[0], ts[-1]):
        nx, nz = kit.inward(front, t)
        side = (nz, 0.0, -nx) if t == ts[0] else (-nz, 0.0, nx)
        oquad(b, (pt(front - cant, t, y0 - 0.5), pt(back + 0.2, t, y0 - 0.5), pt(back + 0.2, t, y1 + 0.35),
                  pt(front - cant, t, y1 + 0.35)), side, "concrete", ((0, 0), (1.7, 0), (1.7, 1.4), (0, 1.4)))
    # the slab reaches back to the parapet on two stub walls
    for t in (ts[2], ts[8], ts[14]):
        nx, nz = kit.inward(front, t)
        yaw = math.atan2(nx, nz)
        b.box(pt(front + pb["depth"] / 2, t, (kit.PARAPET["top"] + y0 - 0.5) / 2),
              (0.5, y0 - 0.5 - kit.PARAPET["top"], pb["depth"]), "concrete", yaw=yaw, skip=("top", "bottom"), uv_scale=0.3)


def rigs(b: C.Builder) -> None:
    """A structure for every rim light bank in `bowl.mounts.rim`: a lattice
    headframe behind the lamp face, a catwalk with a guard rail along its foot,
    twin masts down to the parapet and a raking back stay. The Lighting actor
    hangs the lamps on the mount's position and facing; this is what they hang
    on."""
    for mount in kit.mounts()["rim"]:
        px, py, pz = mount["position"]
        fx, _, fz = mount["facing"]
        pitch = math.radians(mount["pitch"])
        n = (fx * math.cos(pitch), math.sin(pitch), fz * math.cos(pitch))       # the face looks along n
        r = C._norm((-fz, 0.0, fx))
        u = C._norm(C._cross(r, n))
        if u[1] < 0:
            u = C._scale(u, -1)
        w, h = mount["headframe"]
        back = C._scale(n, -0.9)                                                 # frame sits behind the lamps

        def F(a, c, d=0.0):
            return C._add(C._add(C._add((px, py, pz), back), C._scale(r, a * w / 2)),
                          C._add(C._scale(u, c * h / 2), C._scale(n, d)))
        R = 0.09
        corners = [F(-1, -1), F(1, -1), F(1, 1), F(-1, 1)]
        b.tube(corners + [corners[0]], R, "steel", sides=4)
        # lattice: verticals and alternating diagonals across the back
        bays = 6
        for k in range(bays + 1):
            a = -1 + 2 * k / bays
            b.tube([F(a, -1, -0.6), F(a, 1, -0.6)], R * 0.7, "steel", sides=4)
            if k < bays:
                a2 = -1 + 2 * (k + 1) / bays
                lo, hi = (-1, 1) if k % 2 == 0 else (1, -1)
                b.tube([F(a, lo, -0.6), F(a2, hi, -0.6)], R * 0.55, "steel", sides=4)
        b.tube([F(-1, -1, -0.6), F(1, -1, -0.6)], R * 0.7, "steel", sides=4)
        b.tube([F(-1, 1, -0.6), F(1, 1, -0.6)], R * 0.7, "steel", sides=4)
        # catwalk at the frame's foot: grating plank and a guard rail
        g0, g1 = F(-1, -1, 0.1), F(1, -1, 0.1)
        g2, g3 = F(1, -1, 1.0), F(-1, -1, 1.0)
        oquad(b, (g0, g1, g2, g3), u, "trim", band_uv("steel", 0, w / 3, 0.6, 1.0))
        b.tube([F(-1, -1, 1.0), F(1, -1, 1.0)], 0.03, "steel", sides=4)
        rail = [C._add(p, C._scale(u, 1.05)) for p in (F(-1, -1, 1.0), F(1, -1, 1.0))]
        b.tube(rail, 0.03, "steel", sides=4)
        for a in (-1.0, 0.0, 1.0):
            b.tube([F(a, -1, 1.0), C._add(F(a, -1, 1.0), C._scale(u, 1.05))], 0.025, "steel", sides=4)
        # masts: from the frame's lower corners down to the parapet top, and a stay
        base = mount["base"]
        for a in (-0.7, 0.7):
            top = F(a, -1, -0.6)
            foot = (top[0] - fx * 1.5, base, top[2] - fz * 1.5)
            b.tube([top, foot], 0.16, "steel", sides=5)
        stay_top = F(0.0, 1, -0.6)
        stay_foot = (px - fx * 5.0, base, pz - fz * 5.0)
        b.tube([stay_top, stay_foot], 0.11, "steel", sides=4)


def video_board(b: C.Builder) -> None:
    """The video board, from `bowl.videoBoard`: a dark LED face in a steel
    frame, a lattice truss behind, and two legs down to the parapet. Broadcast
    draws on the face; the bowl only builds what holds it up."""
    vb = kit.SC.BOWL["videoBoard"]
    cx, cy, cz = vb["centre"]
    cx -= 50.0                                   # field x to local
    fx, fy, fz = vb["facing"]
    w, h = vb["size"]
    r = C._norm((-fz, 0.0, fx))
    u = C._norm(C._cross(r, (fx, fy, fz)))
    if u[1] < 0:
        u = C._scale(u, -1)
    n = (fx, fy, fz)

    def F(a, c, d=0.0):
        return C._add((cx, cy, cz), C._add(C._scale(r, a), C._add(C._scale(u, c), C._scale(n, d))))
    # face (slot for Broadcast) and a 0.5 yd frame around it, 0.6 deep
    oquad(b, (F(-w / 2, -h / 2, 0.02), F(w / 2, -h / 2, 0.02), F(w / 2, h / 2, 0.02), F(-w / 2, h / 2, 0.02)), n, "screens")
    m, d = 0.5, 0.6
    for (a0, c0, a1, c1) in ((-w / 2 - m, h / 2, w / 2 + m, h / 2 + m), (-w / 2 - m, -h / 2 - m, w / 2 + m, -h / 2),
                              (-w / 2 - m, -h / 2, -w / 2, h / 2), (w / 2, -h / 2, w / 2 + m, h / 2)):
        oquad(b, (F(a0, c0, 0.05), F(a1, c0, 0.05), F(a1, c1, 0.05), F(a0, c1, 0.05)), n, "steel")
    oquad(b, (F(-w / 2 - m, -h / 2 - m, -d), F(w / 2 + m, -h / 2 - m, -d), F(w / 2 + m, h / 2 + m, -d),
              F(-w / 2 - m, h / 2 + m, -d)), C._scale(n, -1), "trim", band_uv("steel", 0, w / 3, 0, 0.6))
    for (a0, c0, a1, c1) in ((-w / 2 - m, h / 2 + m, w / 2 + m, h / 2 + m), (-w / 2 - m, -h / 2 - m, w / 2 + m, -h / 2 - m)):
        oquad(b, (F(a0, c0, 0.05), F(a1, c1, 0.05), F(a1, c1, -d), F(a0, c0, -d)), u if c0 > 0 else C._scale(u, -1), "steel")
    for a in (-w / 2 - m, w / 2 + m):
        oquad(b, (F(a, -h / 2 - m, 0.05), F(a, h / 2 + m, 0.05), F(a, h / 2 + m, -d), F(a, -h / 2 - m, -d)),
              r if a > 0 else C._scale(r, -1), "steel")
    # truss behind: chords and diagonals
    R = 0.12
    for c in (-h / 2, 0.0, h / 2):
        b.tube([F(-w / 2, c, -1.6), F(w / 2, c, -1.6)], R, "steel", sides=4)
    bays = 8
    for k in range(bays + 1):
        a = -w / 2 + w * k / bays
        b.tube([F(a, -h / 2, -1.6), F(a, h / 2, -1.6)], R * 0.8, "steel", sides=4)
        b.tube([F(a, -h / 2, -d), F(a, -h / 2, -1.6)], R * 0.6, "steel", sides=4)
        if k < bays:
            a2 = -w / 2 + w * (k + 1) / bays
            lo, hi = (-h / 2, h / 2) if k % 2 == 0 else (h / 2, -h / 2)
            b.tube([F(a, lo, -1.6), F(a2, hi, -1.6)], R * 0.6, "steel", sides=4)
    # legs to the parapet top
    base = kit.PARAPET["top"]
    for a in (-w * 0.3, w * 0.3):
        top = F(a, -h / 2, -1.6)
        b.tube([top, (top[0] - fx * 2.0, base, top[2] - fz * 2.0)], 0.35, "steel", sides=6)


def parapet(b: C.Builder) -> None:
    m0, m1 = T["upper"]["outer"], kit.PARAPET["offset"]
    y0, y1 = T["upper"]["rise"][1], kit.PARAPET["top"]
    base = kit.adaptive_angles(m1, tolerance=0.15, max_step=12.0)
    ul = arclen(m1, base)
    next_fin = 0.0
    for i in range(len(base) - 1):
        ta, tb = base[i], base[i + 1]
        nin = inward3(m1, (ta + tb) / 2)
        u0, u1 = ul[i], ul[i + 1]
        oquad(b, (pt(m0, ta, y0), pt(m0, tb, y0), pt(m0, tb, y1), pt(m0, ta, y1)), nin, "concrete",
              ((u0 / 3, 0), (u1 / 3, 0), (u1 / 3, 0.6), (u0 / 3, 0.6)))
        oquad(b, (pt(m0, ta, y1), pt(m0, tb, y1), pt(m1 + 0.2, tb, y1), pt(m1 + 0.2, ta, y1)), (0, 1, 0), "trim",
              band_uv("steel", u0 / 3, u1 / 3))
        oquad(b, (pt(m1 + 0.2, ta, 30.0), pt(m1 + 0.2, tb, 30.0), pt(m1 + 0.2, tb, y1), pt(m1 + 0.2, ta, y1)),
              (-nin[0], 0, -nin[2]), "concrete", ((u0 / 4, 0), (u1 / 4, 0), (u1 / 4, 4.4), (u0 / 4, 4.4)))
        while next_fin <= u1:
            if next_fin >= u0:
                t = ta + (tb - ta) * (next_fin - u0) / max(1e-6, u1 - u0)
                nx, nz = kit.inward(m1, t)
                b.box(pt(m1 + 0.95, t, (30.0 + y1 + 0.6) / 2), (0.45, y1 + 0.6 - 30.0, 1.5), "concrete",
                      yaw=math.atan2(nx, nz), uv_scale=0.3, skip=("bottom", "back"))
            next_fin += 8.0


# ───────────────────────────── seats ─────────────────────────────

LIP, BAND_TOP = 0.24, 0.93


def band_quads(b: C.Builder, row_floor: float, m_feet: float, ts, material="band") -> None:
    ul = arclen(m_feet, ts)
    for i in range(len(ts) - 1):
        ta, tb = ts[i], ts[i + 1]
        nin = inward3(m_feet, ta)
        # Each row slides its texture by a different fraction of a tile, so
        # seat columns do not line up row over row into a sawtooth.
        off = (row_floor * 1.618) % 1.0
        u0, u1 = ul[i] / (8 * kit.SEAT_PITCH) + off, ul[i + 1] / (8 * kit.SEAT_PITCH) + off
        oquad(b, (pt(m_feet - LIP, ta, row_floor + 0.05), pt(m_feet - LIP, tb, row_floor + 0.05),
                  pt(m_feet + 0.3, tb, row_floor + BAND_TOP), pt(m_feet + 0.3, ta, row_floor + BAND_TOP)),
              C._norm((nin[0], 0.6, nin[2])), material, ((u0, 0), (u1, 0), (u1, 1), (u0, 1)))


def seat_runs(tier_name: str):
    """Row by row, the seated stretches as (r, row, ring, [(s0, s1)]) in arc
    length, split wherever the scene's runs break."""
    plan = next(t for t in kit.seating()["tiers"] if t["tier"] == tier_name)
    tier = T[tier_name]
    n = ROWS[tier_name]
    for r, rp in enumerate(plan["rows"]):
        ring = kit.Ring(rp["feet"])
        stretches = [(first - rp["pitch"] / 2, first + (count - 0.5) * rp["pitch"]) for first, count in rp["runs"]]
        yield r, kit.row(tier, r, n), ring, rp, stretches


def far_bands(regions) -> dict[str, C.Builder]:
    """`bands` for the whole bowl minus the preset regions; `fill_<id>` for each region."""
    out = {"bands": C.Builder("bands")}
    for reg in regions:
        out[reg["id"]] = C.Builder(f"fill_{reg['id']}")
    for tier_name in ("lower", "upper"):
        tier = T[tier_name]
        base = kit.adaptive_angles((tier["inner"] + tier["outer"]) / 2, tolerance=0.2, max_step=12.0)
        for r, rw, ring, rp, stretches in seat_runs(tier_name):
            for s0, s1 in stretches:
                # split the stretch where it enters and leaves any region
                cuts = [s0, s1]
                for reg in regions:
                    if reg["tier"] == tier_name and reg["rows"][0] <= r <= reg["rows"][1]:
                        c = ring.arc_at(reg["angle"])
                        for edge in (c - reg["reach"], c + reg["reach"]):
                            for off in (-ring.length, 0.0, ring.length):
                                if s0 < edge + off < s1:
                                    cuts.append(edge + off)
                cuts.sort()
                for a, bb in zip(cuts, cuts[1:]):
                    if bb - a < 0.05:
                        continue
                    mid = (a + bb) / 2
                    owner = next((reg["id"] for reg in regions if in_region(reg, tier_name, r, ring, mid)), "bands")
                    ta, tb = ring.angle(a), ring.angle(bb)
                    if tb < ta:
                        tb += 2 * math.pi
                    ts = sample(base, ta, tb)
                    band_quads(out[owner], rw["tread"], rp["feet"], ts)
    return out


def seat_number(rp, s) -> int:
    """A seat's number within its run, 1-based, as its plaque shows it."""
    for first, count in rp["runs"]:
        k = round((s - first) / rp["pitch"])
        if 0 <= k < count:
            return k + 1
    return 1


def plaque(b: C.Builder, x, y, z, yaw, number: int) -> None:
    """The aluminium plate on the back of a chair, numbered for the row
    behind: 8 x 3.5 cm, 0.79 m up, on the back face of the shell."""
    Y = kit.YARD
    fx, fz = math.sin(yaw), math.cos(yaw)
    rx, rz = fz, -fx
    back = -0.296 / Y
    cx, cz = x + fx * back, z + fz * back
    cy = y + 0.79 / Y
    hw, hh = 0.04 / Y, 0.0175 / Y
    n = max(0, min(99, number))
    cu, cv = n % 10, n // 10
    u0, u1 = cu / 10, (cu + 1) / 10
    v0, v1 = 1 - (cv + 1) / 10, 1 - cv / 10

    def P(lat, up):
        return (cx + rx * lat, cy + up, cz + rz * lat)
    oquad(b, (P(hw, -hh), P(-hw, -hh), P(-hw, hh), P(hw, hh)), (-fx, 0, -fz), "plaque",
          ((u0, v0), (u1, v0), (u1, v1), (u0, v1)))


def near_patch(reg) -> C.Builder:
    """The foreground around one preset: nosing strips, aisle stairs,
    handrails, modelled chairs in front of the wearer, bands beyond."""
    b = C.Builder(f"near_{reg['id']}")
    tier_name = reg["tier"]
    tier = T[tier_name]
    n = ROWS[tier_name]
    secs = kit.sections(tier_name)
    rise_step = (tier["rise"][1] - tier["rise"][0]) / n
    base = kit.adaptive_angles((tier["inner"] + tier["outer"]) / 2, tolerance=0.04, max_step=4.0)
    ex, ey, ez = reg["eye"]
    fx, _, fz = reg["feet"]
    lod0 = SEAT.seat(0, False)
    lod1 = SEAT.seat(1, False)
    rails: dict[str, list] = {}
    for r, rw, ring, rp, stretches in seat_runs(tier_name):
        if not (reg["rows"][0] <= r <= reg["rows"][1]):
            continue
        f, bk, tr = rw["front"], rw["back"], rw["tread"]
        c = ring.arc_at(reg["angle"])
        s_lo, s_hi = c - reg["reach"], c + reg["reach"]
        # a rubber nosing strip proud of the riser along the whole region
        gaps = kit.gaps_for_row(tier_name, r, secs, ring)
        cuts = [(a, bb) for a, bb, k in gaps if k in ("vomitory", "tunnel")]
        for t0, t1 in spans(cuts, ring):
            a0, a1 = ring.arc_at(t0), ring.arc_at(t1) if t1 < 2 * math.pi - 1e-9 else ring.length
            lo, hi = max(a0, s_lo), min(a1, s_hi)
            if hi - lo < 0.1:
                continue
            ts = sample(base, ring.angle(lo), ring.angle(hi))
            ul = arclen(f, ts)
            for i in range(len(ts) - 1):
                ta, tb = ts[i], ts[i + 1]
                nin = inward3(f, (ta + tb) / 2)
                u0, u1 = ul[i] / 2.2, ul[i + 1] / 2.2
                oquad(b, (pt(f - 0.02, ta, tr - 0.06), pt(f - 0.02, tb, tr - 0.06), pt(f - 0.02, tb, tr + 0.012),
                          pt(f - 0.02, ta, tr + 0.012)), nin, "stair", ((u0, 0.02), (u1, 0.02), (u1, 0.16), (u0, 0.16)))
                oquad(b, (pt(f - 0.02, ta, tr + 0.012), pt(f - 0.02, tb, tr + 0.012), pt(f + 0.07, tb, tr + 0.012),
                          pt(f + 0.07, ta, tr + 0.012)), (0, 1, 0), "stair", ((u0, 0.05), (u1, 0.05), (u1, 0.15), (u0, 0.15)))
        # seats: chairs near the wearer, bands beyond
        for s0, s1 in stretches:
            lo, hi = max(s0, s_lo), min(s1, s_hi)
            if hi - lo < 0.05:
                continue
            band_from = None
            k0 = math.ceil((lo - rp["runs"][0][0]) / rp["pitch"] - 1e-6) if rp["runs"] else 0
            s = rp["runs"][0][0] + k0 * rp["pitch"] if rp["runs"] else lo
            while s <= hi + 1e-6:
                if s >= lo - 1e-6:
                    t = ring.angle(s)
                    x, z = kit.bowl_point(ring.m, t)
                    d = math.dist((x, tr, z), (ex, ey, ez))
                    own = math.dist((x, z), (fx, fz)) < rp["pitch"] * 0.6 and abs(tr - reg["feet"][1]) < 0.1
                    nx, nz = kit.inward(ring.m, t)
                    yaw = math.atan2(nx, nz)
                    if own:
                        pass
                    elif d <= LOD1_RADIUS:
                        if band_from is not None:
                            band_quads(b, tr, rp["feet"], sample(base, ring.angle(band_from), ring.angle(s - rp["pitch"] / 2)))
                            band_from = None
                        b.extend_placed(lod0 if d <= LOD0_RADIUS else lod1, yaw, (x, tr, z))
                        plaque(b, x, tr, z, yaw, seat_number(rp, s))
                    elif band_from is None:
                        band_from = s - rp["pitch"] / 2
                s += rp["pitch"]
            if band_from is not None and hi - band_from > 0.05:
                band_quads(b, tr, rp["feet"], sample(base, ring.angle(band_from), ring.angle(hi)))
        # aisle stairs as real blocks, and their handrail points
        L = ring.length
        for sec in secs:
            s = sec["from"] * L
            if not (s_lo <= s <= s_hi) or any(a - 0.6 <= s <= bb + 0.6 for a, bb in cuts):
                rails.setdefault(sec["id"], []).append(None)
                continue
            ta = ring.angle(s)
            nx, nz = kit.inward(ring.m, ta)
            tan = (nz, 0.0, -nx)
            half = kit.AISLE / 2 - 0.02

            def P(depth, lat, y):
                x, z = kit.bowl_point(f + (bk - f) * depth, ta)
                return (x + tan[0] * lat, y, z + tan[2] * lat)

            steps = STEPS[tier_name]
            for side in (-1, 1):
                for k in range(steps):
                    d = max(0.02, k / steps) - 0.014
                    h0 = rw["tread"] + rise_step * k / steps
                    c = P(d, side * (half - 0.12), h0 + 0.09)
                    oquad(b, (C._add(c, C._scale(tan, -0.07)), C._add(c, C._scale(tan, 0.07)),
                              C._add(C._add(c, C._scale(tan, 0.07)), (0, 0.05, 0)),
                              C._add(C._add(c, C._scale(tan, -0.07)), (0, 0.05, 0))),
                          (nx, 0, nz), "steplight", ((0.1, 0.02), (0.4, 0.02), (0.4, 0.2), (0.1, 0.2)))
            for k in range(1, steps):
                d0, d1 = k / steps, 1.0
                h = tr + rise_step * k / steps
                front_d = d0 - 0.012
                oquad(b, (P(front_d, -half, tr), P(front_d, half, tr), P(front_d, half, h), P(front_d, -half, h)), (nx, 0, nz),
                      "stair", ((0, 0), (1, 0), (1, 0.4), (0, 0.4)))
                oquad(b, (P(front_d, -half, h), P(front_d, half, h), P(d1, half, h), P(d1, -half, h)), (0, 1, 0), "stair",
                      ((0, 0.4), (1, 0.4), (1, 1), (0, 1)))
                for side in (-1, 1):
                    oquad(b, (P(front_d, side * half, tr), P(d1, side * half, tr), P(d1, side * half, h),
                              P(front_d, side * half, h)), (tan[0] * side, 0, tan[2] * side), "stair",
                          ((0, 0.45), (0.3, 0.45), (0.3, 0.6), (0, 0.6)))
            rails.setdefault(sec["id"], []).append((P(0.06, 0, rw["riserFrom"] + RAIL_H), P(0.06, 0, rw["riserFrom"])))
    for pts in rails.values():
        run = []
        for item in pts + [None]:
            if item is None:
                if len(run) >= 2:
                    b.tube([p[0] for p in run], 0.026, "seat_hardware", sides=5)
                    for j, (top, foot) in enumerate(run):
                        if j % 3 == 0:
                            b.tube([foot, top], 0.03, "seat_hardware", sides=4)
                run = []
            else:
                run.append(item)
    return b


# ───────────────────────────── table ─────────────────────────────

def table() -> C.Builder:
    """Both decks at LOD2 - the lower three rows a step, the upper four - with
    the ribbon fascia, the back walls and the field wall, and the home stands
    cut away so the wearer looks in. The Experience actor draws
    presentation.tabletop.bowlTiers; with only "lower" listed the upper deck
    is still in the model but outside what the table volume promised."""
    b = C.Builder("table")
    tier = T["lower"]
    n = ROWS["lower"]
    base = kit.adaptive_angles((tier["inner"] + tier["outer"]) / 2, tolerance=0.35, max_step=12.0)
    for g0 in range(0, n, 3):
        g1 = min(n, g0 + 3) - 1
        first, last = kit.row(tier, g0, n), kit.row(tier, g1, n)
        f, bk, tr, rf = first["front"], last["back"], last["tread"], first["riserFrom"]
        ul = arclen(f, base)
        for i in range(len(base) - 1):
            ta, tb = base[i], base[i + 1]
            if cut_on_table(ta, tb):
                continue
            nin = inward3(f, (ta + tb) / 2)
            oquad(b, (pt(f, ta, rf), pt(f, tb, rf), pt(f, tb, tr), pt(f, ta, tr)), nin, "table_trim",
                  band_uv("riser", ul[i] / 4.4, ul[i + 1] / 4.4))
            su0, su1 = ul[i] / (8 * kit.SEAT_PITCH), ul[i + 1] / (8 * kit.SEAT_PITCH)
            oquad(b, (pt(f, ta, tr), pt(f, tb, tr), pt(bk, tb, tr), pt(bk, ta, tr)), (0, 1, 0), "band",
                  ((su0, 0), (su1, 0), (su1, g1 - g0 + 1), (su0, g1 - g0 + 1)))
    upper = T["upper"]
    nu = ROWS["upper"]
    base = kit.adaptive_angles((upper["inner"] + upper["outer"]) / 2, tolerance=0.5, max_step=14.0)
    for g0 in range(0, nu, 4):
        g1 = min(nu, g0 + 4) - 1
        first, last = kit.row(upper, g0, nu), kit.row(upper, g1, nu)
        f, bk, tr, rf = first["front"], last["back"], last["tread"], first["riserFrom"]
        ul = arclen(f, base)
        for i in range(len(base) - 1):
            ta, tb = base[i], base[i + 1]
            if cut_on_table(ta, tb):
                continue
            nin = inward3(f, (ta + tb) / 2)
            oquad(b, (pt(f, ta, rf), pt(f, tb, rf), pt(f, tb, tr), pt(f, ta, tr)), nin, "table_trim",
                  band_uv("riser", ul[i] / 4.4, ul[i + 1] / 4.4))
            su0, su1 = ul[i] / (8 * kit.SEAT_PITCH), ul[i + 1] / (8 * kit.SEAT_PITCH)
            oquad(b, (pt(f, ta, tr), pt(f, tb, tr), pt(bk, tb, tr), pt(bk, ta, tr)), (0, 1, 0), "band",
                  ((su0, 0), (su1, 0), (su1, g1 - g0 + 1), (su0, g1 - g0 + 1)))
    for i in range(len(base) - 1):
        ta, tb = base[i], base[i + 1]
        if cut_on_table(ta, tb):
            continue
        nin = inward3(upper["inner"], (ta + tb) / 2)
        rib = kit.BOWL["ribbon"]
        # the ribbon fascia and the deck's front, then the back of the top row down to the ground
        oquad(b, (pt(rib["offset"], ta, T["lower"]["rise"][1]), pt(rib["offset"], tb, T["lower"]["rise"][1]),
                  pt(rib["offset"], tb, upper["rise"][0]), pt(rib["offset"], ta, upper["rise"][0])), nin, "screens")
        oquad(b, (pt(rib["offset"], ta, upper["rise"][0]), pt(rib["offset"], tb, upper["rise"][0]),
                  pt(upper["inner"], tb, upper["rise"][0]), pt(upper["inner"], ta, upper["rise"][0])), (0, 1, 0),
              "table_trim", band_uv("steel", 0, 1))
        o, yt = upper["outer"], upper["rise"][1]
        oquad(b, (pt(o, ta, yt), pt(o, tb, yt), pt(o, tb, yt + 1.8), pt(o, ta, yt + 1.8)), nin, "table_trim",
              band_uv("steel", 0, 1))
        oquad(b, (pt(o + 0.6, ta, 0), pt(o + 0.6, tb, 0), pt(o + 0.6, tb, yt + 1.8), pt(o + 0.6, ta, yt + 1.8)),
              (-nin[0], 0, -nin[2]), "table_trim", band_uv("riser", 0, 1))
    wm, top = kit.BOWL["wall"]["offset"], kit.BOWL["wall"]["height"]
    base = kit.adaptive_angles(20.0, tolerance=0.35, max_step=12.0)
    for i in range(len(base) - 1):
        ta, tb = base[i], base[i + 1]
        if cut_on_table(ta, tb):
            continue
        nin = inward3(wm, (ta + tb) / 2)
        oquad(b, (pt(wm, ta, 0), pt(wm, tb, 0), pt(wm, tb, top), pt(wm, ta, top)), nin, "screens")
        oquad(b, (pt(wm, ta, top), pt(wm, tb, top), pt(tier["inner"], tb, top), pt(tier["inner"], ta, top)), (0, 1, 0),
              "table_trim", band_uv("tread", 0, 1, 0.5, 0.8))
        o, yt = tier["outer"], tier["rise"][1]
        oquad(b, (pt(o, ta, yt), pt(o, tb, yt), pt(o, tb, yt + 1.6), pt(o, ta, yt + 1.6)), nin, "table_trim",
              band_uv("steel", 0, 1))
        oquad(b, (pt(o + 0.4, ta, 0), pt(o + 0.4, tb, 0), pt(o + 0.4, tb, yt + 1.6), pt(o + 0.4, ta, yt + 1.6)),
              (-nin[0], 0, -nin[2]), "table_trim", band_uv("riser", 0, 1))
    return b


# ───────────────────────────── build ─────────────────────────────

def build() -> list[dict]:
    C.reset()
    mats = materials()
    entries = []

    def emit(name, builders, about, **extra):
        objs = [bd.build(mats) for bd in builders if bd.faces]
        e = C.export(objs, name)
        e.update({"about": about, **extra})
        entries.append(e)
        print(f"[structure] {name}: {e['triangles']} tris, parts {e['parts']}, "
              f"{e['bytes']['usdz'] / 1e6:.1f} MB usdz / {e['bytes']['glb'] / 1e6:.1f} MB glb", flush=True)
        for o in objs:
            bpy.data.objects.remove(o)

    regions = presets()
    stands = C.Builder("stands")
    for tier_name in ("lower", "upper"):
        stands_rows(stands, tier_name)
        vomitories(stands, tier_name)
    field_wall(stands)
    team_tunnels(stands)
    club(stands)
    parapet(stands)
    press_box(stands)
    rigs(stands)
    video_board(stands)
    emit("stands", [stands], "The whole bowl's structure in one entity.")

    bands = far_bands(regions)
    emit("seats_far", list(bands.values()),
         "Seat bands: `bands` everywhere but the preset regions; `fill_<preset>` for each region. Show every fill "
         "except the preset the wearer sits in.", regions=[{k: r[k] for k in ("id", "tier", "angle", "rows", "reach")}
                                                         for r in regions])
    emit("near", [near_patch(r) for r in regions],
         "Foreground detail per preset (`near_<preset>`): show only the wearer's.")
    emit("table", [table()], "The tabletop bowl: lower tier, stepped, home stands cut away.")
    C.write_manifest_part("structure", entries)
    return entries
