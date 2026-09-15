"""The bowl's structure: every tier, stair, tunnel, wall, suite and fascia.

Built in local yards on the same rows `SceneMath.row` draws, so the kit
replaces the slab bowl without moving a seat. Faces are oriented by the
normal they should have rather than by hand-kept winding, so a surface
never turns inside out on the far side of the bowl.

Modules:
  bowl_lower_lod0   rows, nosings, aisle stairs, handrails, vomitories,
                    accessible platforms, the padded field wall, team tunnels
  bowl_club_lod0    concourse slab, suites behind glass, open end concourses,
                    soffit with its light cove, the ribbon fascia
  bowl_upper_lod0   rows, stairs, rails, vomitories, parapet, exterior fins
  bowl_seats_far    one slanted, textured band per row of seats, aisles cut
  bowl_lod2         a stepped bowl, three rows a step, for the table and the
                    distance - split into wedges so the table can cut the
                    near stands away

Every module is split into angular wedges (objects named *_wNN) so a renderer
can LOD or cull by direction.
"""
from __future__ import annotations

import math

import common as C
import kit
from textures import TRIM, TRIM_U_YARDS

T = kit.TIERS
ROWS = kit.ROWS
HALF_W, HALF_L = kit.SHAPE["halfWidth"], kit.SHAPE["halfLength"]
RAIL_H = 1.04            # 0.95 m guard height, in yards
STEPS = {"lower": 2, "upper": 3}
NOSE = 0.045
WEDGES_LOD0 = 16


def materials():
    return {
        "bowl_trim": C.material("bowl_trim", albedo="bowl_trim_albedo.jpg", normal="bowl_trim_normal.png",
                                orm="bowl_trim_orm.png", color=(1, 1, 1, 1)),
        "concrete_wall": C.material("concrete_wall", albedo="concrete_wall_albedo.jpg", normal="concrete_wall_normal.png",
                                    orm="concrete_wall_orm.png", color=(1, 1, 1, 1)),
        "steel_painted": C.material("steel_painted", color=(0.05, 0.053, 0.058, 1), roughness=0.4, metallic=0.7),
        "glass_rail": C.material("glass_rail", color=(0.55, 0.62, 0.66, 1), roughness=0.05, alpha=0.22, double_sided=True),
        "glass_suite": C.material("glass_suite", color=(0.08, 0.10, 0.12, 1), roughness=0.04, metallic=0.2, alpha=0.5,
                                  double_sided=True),
        "suite_interior": C.material("suite_interior", color=(0, 0, 0, 1), emission="suite_interior_emission.jpg",
                                     emission_strength=2.0),
        "concourse_glow": C.material("concourse_glow", color=(0, 0, 0, 1), emission="concourse_glow_emission.jpg",
                                     emission_strength=3.0),
        "tunnel_dark": C.material("tunnel_dark", color=(0.018, 0.018, 0.02, 1), roughness=0.9),
        # Slots other actors fill: they ship dark and self-lit just enough to read as screens.
        "wall_led": C.material("wall_led", color=(0.01, 0.01, 0.012, 1), roughness=0.3, emission_color=(0.02, 0.03, 0.05),
                               emission_strength=1.0),
        "ribbon_screen": C.material("ribbon_screen", color=(0.01, 0.01, 0.012, 1), roughness=0.3,
                                    emission_color=(0.02, 0.03, 0.05), emission_strength=1.0),
        "tunnel_header": C.material("tunnel_header", color=(0.02, 0.02, 0.025, 1), roughness=0.4,
                                    emission_color=(0.05, 0.05, 0.06), emission_strength=1.0),
        "seat_band": C.material("seat_band", color=(0.035, 0.06, 0.16, 1), albedo="seat_band_albedo.png",
                                normal="seat_band_normal.png", normal_strength=0.5),
    }


# ───────────────────────────── primitives ─────────────────────────────

def pt(m, t, y):
    x, z = kit.bowl_point(m, t)
    return (x, y, z)


def band_uv(band, u0, u1, a=0.0, b=1.0):
    """UVs for a quad in trim band `band`: u along, v from fraction a to b of the band."""
    v0, v1 = TRIM[band]
    va, vb = v0 + (v1 - v0) * a, v0 + (v1 - v0) * b
    return ((u0, va), (u1, va), (u1, vb), (u0, vb))


def oquad(b: C.Builder, pts, want, material, uv=((0, 0), (1, 0), (1, 1), (0, 1))):
    """A quad whose winding is chosen so its normal points along `want`."""
    p0, p1, _, p3 = pts
    n = C._cross(C._sub(p1, p0), C._sub(p3, p0))
    if C._dot(n, want) < 0:
        pts = (pts[1], pts[0], pts[3], pts[2])
        uv = (uv[1], uv[0], uv[3], uv[2])
    b.quad(*pts, material, uv=uv)


def inward3(m, t):
    nx, nz = kit.inward(m, t)
    return (nx, 0.0, nz)


class Wedges:
    """Builders keyed by direction, so a module splits into angular pieces."""

    def __init__(self, name, count):
        self.name, self.count = name, count
        self.parts: dict[int, C.Builder] = {}

    def at(self, t) -> C.Builder:
        k = int(((t % (2 * math.pi)) / (2 * math.pi)) * self.count) % self.count
        if k not in self.parts:
            self.parts[k] = C.Builder(f"{self.name}_w{k:02d}")
        return self.parts[k]

    def meta(self):
        return [{"object": f"{self.name}_w{k:02d}", "from": round(2 * math.pi * k / self.count, 5),
                 "to": round(2 * math.pi * (k + 1) / self.count, 5)} for k in sorted(self.parts)]

    def build(self, mats):
        objs = []
        for k in sorted(self.parts):
            b = self.parts[k]
            if b.faces:
                objs.append(b.build(mats))
        return objs

    @property
    def triangles(self):
        return sum(b.triangles for b in self.parts.values())


def spans(cuts, ring: kit.Ring):
    """Angle ranges of a ring left after removing arc-length cuts."""
    L = ring.length
    marks = []
    for a, b in cuts:
        a %= L
        b = a + (b - a) if b > a else b
        length = b - a if b >= a else (b % L) + L - a
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
    return [(ring.angle(a), ring.angle(b) if b < L else 2 * math.pi) for a, b in keep if b - a > 0.05]


def sample(base, t0, t1):
    inner = [t for t in base if t0 < t < t1]
    return [t0] + inner + [t1]


def arclen(m, ts):
    out, acc = [0.0], 0.0
    for i in range(1, len(ts)):
        x0, z0 = kit.bowl_point(m, ts[i - 1])
        x1, z1 = kit.bowl_point(m, ts[i])
        acc += math.hypot(x1 - x0, z1 - z0)
        out.append(acc)
    return out


# ───────────────────────────── tiers ─────────────────────────────

def tier_rows(tier_name: str, W: Wedges, rails: Wedges, dark: Wedges) -> None:
    tier = T[tier_name]
    n = ROWS[tier_name]
    secs = kit.sections(tier_name)
    base = kit.adaptive_angles((tier["inner"] + tier["outer"]) / 2, tolerance=0.05)
    v = kit.VOMITORY[tier_name]
    rise_step = (tier["rise"][1] - tier["rise"][0]) / n
    rails_by_aisle: dict[str, list] = {}

    for r in range(n):
        rw = kit.row(tier, r, n)
        ring = kit.Ring(rw["front"] + (rw["back"] - rw["front"]) * 0.38)
        gaps = kit.gaps_for_row(tier_name, r, secs, ring)
        cuts = [(a, b) for a, b, k in gaps if k in ("vomitory", "tunnel")]
        f, bk, tr, rf = rw["front"], rw["back"], rw["tread"], rw["riserFrom"]
        for t0, t1 in spans(cuts, ring):
            ts = sample(base, t0, t1)
            ul = arclen(f, ts)
            for i in range(len(ts) - 1):
                ta, tb = ts[i], ts[i + 1]
                bld = W.at((ta + tb) / 2)
                nin = inward3(f, (ta + tb) / 2)
                ua, ub = ul[i] / TRIM_U_YARDS["riser"], ul[i + 1] / TRIM_U_YARDS["riser"]
                oquad(bld, (pt(f, ta, rf), pt(f, tb, rf), pt(f, tb, tr - NOSE), pt(f, ta, tr - NOSE)), nin,
                      "bowl_trim", band_uv("riser", ua, ub, 0.0, min(1.0, (tr - rf) / 0.9)))
                up_in = C._norm((nin[0], 1.0, nin[2]))
                oquad(bld, (pt(f, ta, tr - NOSE), pt(f, tb, tr - NOSE), pt(f + NOSE, tb, tr), pt(f + NOSE, ta, tr)), up_in,
                      "bowl_trim", band_uv("nosing", ua, ub))
                oquad(bld, (pt(f + NOSE, ta, tr), pt(f + NOSE, tb, tr), pt(bk, tb, tr), pt(bk, ta, tr)), (0, 1, 0),
                      "bowl_trim", band_uv("tread", ua, ub))

        # Aisle stairs and their centre handrail.
        steps = STEPS[tier_name]
        L = ring.length
        for sec in secs:
            s = sec["from"] * L
            if any(a - 0.5 <= s <= b + 0.5 for a, b in cuts):
                rails_by_aisle.setdefault(sec["id"], []).append(None)
                continue
            ta = ring.angle(s)
            nx, nz = kit.inward(ring.m, ta)
            tan = (nz, 0.0, -nx)
            half = kit.AISLE / 2
            bld = W.at(ta)

            def P(depth, lat, y):
                x, z = kit.bowl_point(f + (bk - f) * depth, ta)
                return (x + tan[0] * lat, y, z + tan[2] * lat)

            for k in range(1, steps):
                d0, d1 = k / steps, (k + 1) / steps
                h = tr + rise_step * k / steps
                hp = tr + rise_step * (k - 1) / steps
                oquad(bld, (P(d0, -half, hp), P(d0, half, hp), P(d0, half, h), P(d0, -half, h)), (nx, 0, nz),
                      "bowl_trim", band_uv("nosing", 0, kit.AISLE / TRIM_U_YARDS["nosing"], 0.2, 1.0))
                oquad(bld, (P(d0, -half, h), P(d0, half, h), P(d1, half, h), P(d1, -half, h)), (0, 1, 0),
                      "bowl_trim", band_uv("tread", 0, kit.AISLE / TRIM_U_YARDS["tread"], 0.0, (d1 - d0) * 0.9))
                for side in (-1, 1):
                    oquad(bld, (P(d0, side * half, tr), P(d1, side * half, tr), P(d1, side * half, h), P(d0, side * half, h)),
                          (tan[0] * side, 0, tan[2] * side), "bowl_trim",
                          band_uv("riser", 0, (d1 - d0) / TRIM_U_YARDS["riser"], 0, 0.3))
            rails_by_aisle.setdefault(sec["id"], []).append((P(0.06, 0, rf + RAIL_H), P(0.06, 0, rf), ta))

    # Handrails: one polyline per aisle, broken wherever a row was cut.
    for sec_id, pts in rails_by_aisle.items():
        run = []
        for i, item in enumerate(pts + [None]):
            if item is None:
                if len(run) >= 2:
                    rb = rails.at(run[len(run) // 2][2])
                    rb.tube([p[0] for p in run], 0.026, "steel_painted", sides=5)
                    for j, (top, foot, _) in enumerate(run):
                        if j % 3 == 0:
                            rb.tube([foot, top], 0.03, "steel_painted", sides=5)
                run = []
            else:
                run.append(item)

    vomitories(tier_name, secs, W, rails, dark)


def vomitories(tier_name: str, secs, W: Wedges, rails: Wedges, dark: Wedges) -> None:
    tier = T[tier_name]
    n = ROWS[tier_name]
    v = kit.VOMITORY[tier_name]
    r0, r1 = v["rows"]
    half = v["width"] / 2
    landing = kit.row(tier, r0 - 1, n)["tread"]
    roof = landing + 2.84
    outer = tier["outer"] if tier_name == "lower" else kit.PARAPET["offset"] - 0.1
    mid_ring = kit.Ring((tier["inner"] + tier["outer"]) / 2)
    for sec in secs:
        if not sec["vomitory"]:
            continue
        frac = (sec["from"] + sec["to"]) / 2
        tc = mid_ring.angle(frac * mid_ring.length)
        nx, nz = kit.inward(mid_ring.m, tc)
        tan = (nz, 0.0, -nx)
        out = (-nx, 0.0, -nz)
        bld = W.at(tc)
        dk = dark.at(tc)
        f0 = kit.row(tier, r0, n)["front"]
        b1 = kit.row(tier, r1, n)["back"]

        def Q(m, lat, y):
            x, z = kit.bowl_point(m, tc)
            return (x + tan[0] * lat, y, z + tan[2] * lat)

        # stepped cheek walls through the cut rows
        for r in range(r0, r1 + 1):
            rw = kit.row(tier, r, n)
            for side in (-1, 1):
                oquad(bld, (Q(rw["front"], side * half, landing), Q(rw["back"], side * half, landing),
                            Q(rw["back"], side * half, rw["tread"]), Q(rw["front"], side * half, rw["tread"])),
                      (-tan[0] * side, 0, -tan[2] * side), "concrete_wall",
                      ((0, 0), ((rw["back"] - rw["front"]) / 3, 0), ((rw["back"] - rw["front"]) / 3, (rw["tread"] - landing) / 3),
                       (0, (rw["tread"] - landing) / 3)))
        # the lintel: from the tunnel's roof up to the first uncut row's riser
        nxt = kit.row(tier, r1 + 1, n)
        oquad(bld, (Q(nxt["front"], -half, roof), Q(nxt["front"], half, roof),
                    Q(nxt["front"], half, nxt["riserFrom"]), Q(nxt["front"], -half, nxt["riserFrom"])),
              (nx, 0, nz), "bowl_trim", band_uv("riser", 0, v["width"] / TRIM_U_YARDS["riser"], 0, 0.6))
        # the tunnel under the rows behind: floor, roof, walls, and the glow at its end
        oquad(dk, (Q(f0, -half, landing), Q(f0, half, landing), Q(outer, half, landing), Q(outer, -half, landing)),
              (0, 1, 0), "bowl_trim", band_uv("tread", 0, v["width"] / TRIM_U_YARDS["tread"], 0, 1))
        oquad(dk, (Q(nxt["front"], -half, roof), Q(nxt["front"], half, roof), Q(outer, half, roof), Q(outer, -half, roof)),
              (0, -1, 0), "bowl_trim", band_uv("soffit", 0, v["width"] / TRIM_U_YARDS["soffit"], 0, 0.5))
        for side in (-1, 1):
            oquad(dk, (Q(b1, side * half, landing), Q(outer, side * half, landing), Q(outer, side * half, roof),
                       Q(b1, side * half, roof)), (-tan[0] * side, 0, -tan[2] * side), "tunnel_dark")
        oquad(dk, (Q(outer - 0.05, -half, landing), Q(outer - 0.05, half, landing), Q(outer - 0.05, half, roof),
                   Q(outer - 0.05, -half, roof)), (nx, 0, nz), "concourse_glow")
        # guard rails: along each cheek's stepped top and a glass panel across the lintel
        rb = rails.at(tc)
        for side in (-1, 1):
            line = []
            for r in range(r0, r1 + 1):
                rw = kit.row(tier, r, n)
                line.append(Q(rw["front"] + 0.1, side * (half + 0.1), rw["tread"] + RAIL_H))
            line.append(Q(b1, side * (half + 0.1), kit.row(tier, r1, n)["tread"] + RAIL_H))
            rb.tube(line, 0.026, "steel_painted", sides=5)
        top = nxt["tread"]
        rb.tube([Q(nxt["front"] + 0.12, -half, top + RAIL_H), Q(nxt["front"] + 0.12, half, top + RAIL_H)], 0.03,
                "steel_painted", sides=6)
        oquad(rb, (Q(nxt["front"] + 0.12, -half, top), Q(nxt["front"] + 0.12, half, top),
                   Q(nxt["front"] + 0.12, half, top + RAIL_H - 0.05), Q(nxt["front"] + 0.12, -half, top + RAIL_H - 0.05)),
              (nx, 0, nz), "glass_rail")
        # the accessible platform's front rail
        acc = kit.row(tier, r0 - 1, n)
        wide = half + kit.ACCESSIBLE_MARGIN
        rb.tube([Q(acc["front"] + 0.1, -wide, acc["tread"] + RAIL_H * 0.8), Q(acc["front"] + 0.1, wide, acc["tread"] + RAIL_H * 0.8)],
                0.026, "steel_painted", sides=5)
        for lat in (-wide, 0.0, wide):
            rb.tube([Q(acc["front"] + 0.1, lat, acc["tread"]), Q(acc["front"] + 0.1, lat, acc["tread"] + RAIL_H * 0.8)],
                    0.028, "steel_painted", sides=5)
        del out


# ───────────────────────────── field level ─────────────────────────────

def field_wall(W: Wedges, rails: Wedges) -> None:
    wall = kit.BOWL["wall"]
    m = wall["offset"]
    top = wall["height"]
    ring = kit.Ring(m)
    cuts = [(s0 + 0.7, s1 - 0.7) for s0, s1, _ in kit.tunnel_spans(ring)]
    base = kit.adaptive_angles(m, tolerance=0.03)
    inner = T["lower"]["inner"]
    for t0, t1 in spans(cuts, ring):
        ts = sample(base, t0, t1)
        ul = arclen(m, ts)
        for i in range(len(ts) - 1):
            ta, tb = ts[i], ts[i + 1]
            bld = W.at((ta + tb) / 2)
            nin = inward3(m, (ta + tb) / 2)
            u = (ul[i] / 3.0, ul[i + 1] / 3.0)
            layers = [(0.0, 0.16, m, "concrete_wall", None), (0.16, 0.2, m - 0.02, "steel_painted", None),
                      (0.2, 1.0, m - 0.02, "wall_led", None), (1.0, 1.03, m - 0.02, "steel_painted", None)]
            for y0, y1, mm, mat, _ in layers:
                uv = ((u[0], y0), (u[1], y0), (u[1], y1), (u[0], y1))
                oquad(bld, (pt(mm, ta, y0), pt(mm, tb, y0), pt(mm, tb, y1), pt(mm, ta, y1)), nin, mat, uv)
            # the pad: a rounded roll of vinyl proud of the wall
            pad = [(1.03, m - 0.02), (1.08, m - 0.12), (top - 0.08, m - 0.14), (top, m - 0.06)]
            for j in range(len(pad) - 1):
                (ya, ma), (yb, mb) = pad[j], pad[j + 1]
                oquad(bld, (pt(ma, ta, ya), pt(ma, tb, ya), pt(mb, tb, yb), pt(mb, ta, yb)),
                      C._norm((nin[0], 0.4, nin[2])), "bowl_trim",
                      band_uv("padding", ul[i] / TRIM_U_YARDS["padding"], ul[i + 1] / TRIM_U_YARDS["padding"],
                              j / 3, (j + 1) / 3))
            oquad(bld, (pt(m - 0.06, ta, top), pt(m - 0.06, tb, top), pt(inner, tb, top), pt(inner, ta, top)), (0, 1, 0),
                  "bowl_trim", band_uv("tread", ul[i] / 4.4, ul[i + 1] / 4.4, 0.6, 0.9))
            oquad(bld, (pt(inner, ta, T["lower"]["rise"][0]), pt(inner, tb, T["lower"]["rise"][0]),
                        pt(inner, tb, top), pt(inner, ta, top)), (-nin[0], 0, -nin[2]), "concrete_wall")
        # glass along the wall's cap, steel top rail
        rb = rails.at((t0 + t1) / 2)
        gl = [pt(m + 0.25, t, top + 0.95) for t in ts]
        rb.tube(gl, 0.03, "steel_painted", sides=5)
        for i in range(len(ts) - 1):
            ta, tb = ts[i], ts[i + 1]
            oquad(rb, (pt(m + 0.25, ta, top), pt(m + 0.25, tb, top), pt(m + 0.25, tb, top + 0.93), pt(m + 0.25, ta, top + 0.93)),
                  inward3(m, ta), "glass_rail")


def team_tunnels(W: Wedges, rails: Wedges, dark: Wedges) -> None:
    tier = T["lower"]
    n = ROWS["lower"]
    for tn in kit.BOWL["tunnels"]:
        x = tn["x"] - 50
        tc = 0.0 if x > 0 else math.pi
        half = tn["width"] / 2 + 0.3
        h = tn["height"]
        nx, nz = kit.inward(5.4, tc)
        tan = (nz, 0.0, -nx)
        bld = W.at(tc)
        dk = dark.at(tc)
        wall_m = kit.BOWL["wall"]["offset"]
        cut_rows = [r for r in range(n) if kit.row(tier, r, n)["tread"] < h + kit.TUNNEL_CLEAR]
        last = kit.row(tier, cut_rows[-1], n)
        nxt = kit.row(tier, cut_rows[-1] + 1, n)
        deck = last["tread"]
        end = 20.0

        def Q(m, lat, y):
            xx, zz = kit.bowl_point(m, tc)
            return (xx + tan[0] * lat, y, zz + tan[2] * lat)

        wide = half + 1.0
        # cheek walls rising under the removed rows, then the deck over the mouth
        for r in cut_rows:
            rw = kit.row(tier, r, n)
            for side in (-1, 1):
                oquad(bld, (Q(rw["front"], side * wide, 0), Q(rw["back"], side * wide, 0),
                            Q(rw["back"], side * wide, rw["tread"]), Q(rw["front"], side * wide, rw["tread"])),
                      (-tan[0] * side, 0, -tan[2] * side), "concrete_wall")
        for side in (-1, 1):
            oquad(bld, (Q(wall_m, side * wide, 0), Q(tier["inner"], side * wide, 0), Q(tier["inner"], side * wide, deck),
                        Q(wall_m, side * wide, deck)), (-tan[0] * side, 0, -tan[2] * side), "concrete_wall")
        oquad(bld, (Q(wall_m, -wide, deck), Q(wall_m, wide, deck), Q(nxt["front"], wide, deck), Q(nxt["front"], -wide, deck)),
              (0, 1, 0), "bowl_trim", band_uv("tread", 0, 2 * wide / 4.4, 0, 1))
        oquad(bld, (Q(nxt["front"], -wide, deck), Q(nxt["front"], wide, deck), Q(nxt["front"], wide, nxt["riserFrom"]),
                    Q(nxt["front"], -wide, nxt["riserFrom"])), (nx, 0, nz), "bowl_trim",
              band_uv("riser", 0, 2 * wide / 4.4, 0, 0.4))
        # the tunnel: floor, ceiling, walls, glow at the end
        oquad(dk, (Q(wall_m, -half, 0.01), Q(wall_m, half, 0.01), Q(end, half, 0.01), Q(end, -half, 0.01)), (0, 1, 0), "tunnel_dark")
        oquad(dk, (Q(wall_m, -half, h), Q(wall_m, half, h), Q(end, half, h), Q(end, -half, h)), (0, -1, 0), "tunnel_dark")
        for side in (-1, 1):
            oquad(dk, (Q(wall_m, side * half, 0), Q(end, side * half, 0), Q(end, side * half, h), Q(wall_m, side * half, h)),
                  (-tan[0] * side, 0, -tan[2] * side), "tunnel_dark")
        oquad(dk, (Q(end, -half, 0), Q(end, half, 0), Q(end, half, h), Q(end, -half, h)), (nx, 0, nz), "concourse_glow")
        # the entry arch: posts, a header screen, the deck's front face
        arch_m = wall_m - 0.5
        for side in (-1, 1):
            c = Q(arch_m, side * (half + 0.35), (deck + 1.3) / 2)
            yaw = math.atan2(nx, nz)
            bld.box(c, (0.7, deck + 1.3, 1.1), "steel_painted", yaw=yaw)
        c = Q(arch_m, 0, deck + 0.65)
        bld.box(c, (2 * half + 1.4, 1.3, 1.1), "steel_painted", yaw=math.atan2(nx, nz), skip=("front",))
        oquad(bld, (Q(arch_m - 0.56, -half - 0.6, deck + 0.05), Q(arch_m - 0.56, half + 0.6, deck + 0.05),
                    Q(arch_m - 0.56, half + 0.6, deck + 1.25), Q(arch_m - 0.56, -half - 0.6, deck + 1.25)), (nx, 0, nz),
              "tunnel_header")
        oquad(bld, (Q(arch_m - 0.56, -half, h), Q(arch_m - 0.56, half, h), Q(arch_m - 0.56, half, deck), Q(arch_m - 0.56, -half, deck)),
              (nx, 0, nz), "bowl_trim", band_uv("padding", 0, 2 * half / 3.0, 0, 1))
        rb = rails.at(tc)
        rb.tube([Q(wall_m + 0.3, -wide, deck + 1.35), Q(wall_m + 0.3, wide, deck + 1.35)], 0.03, "steel_painted", sides=6)
        oquad(rb, (Q(wall_m + 0.3, -wide, deck + 1.3), Q(wall_m + 0.3, wide, deck + 1.3), Q(wall_m + 0.3, wide, deck + 2.3),
                   Q(wall_m + 0.3, -wide, deck + 2.3)), (nx, 0, nz), "glass_rail")


# ───────────────────────────── club level ─────────────────────────────

def club(W: Wedges, rails: Wedges) -> None:
    lower_top = T["lower"]["rise"][1]
    ceil = kit.CLUB["ceiling"]
    glass_m = kit.CLUB["glass"]
    back_m = 41.0
    fas = kit.FASCIA
    pb = kit.BOWL["pressBox"]
    base = kit.adaptive_angles(39.0, tolerance=0.04, max_step=3.0)
    ring = kit.Ring(39.0)
    ul = arclen(glass_m, base)
    mull_every = 3.0
    next_mull = 0.0
    for i in range(len(base) - 1):
        ta, tb = base[i], base[i + 1]
        tm = (ta + tb) / 2
        bld = W.at(tm)
        nin = inward3(39.0, tm)
        x, z = kit.bowl_point(39.0, tm)
        u0, u1 = ul[i], ul[i + 1]
        end = abs(x) > HALF_L + 2
        press = (pb["side"] == "far" and z < 0 and (pb["fromX"] - 50) <= x <= (pb["toX"] - 50))
        # slab and balcony edge
        oquad(bld, (pt(T["lower"]["outer"], ta, lower_top), pt(T["lower"]["outer"], tb, lower_top),
                    pt(back_m, tb, lower_top), pt(back_m, ta, lower_top)), (0, 1, 0), "bowl_trim",
              band_uv("tread", u0 / 4.4, u1 / 4.4))
        # soffit with a light cove
        oquad(bld, (pt(T["lower"]["outer"], ta, ceil), pt(T["lower"]["outer"], tb, ceil), pt(fas["front"], tb, ceil),
                    pt(fas["front"], ta, ceil)), (0, -1, 0), "bowl_trim", band_uv("soffit", u0 / 6.0, u1 / 6.0))
        oquad(bld, (pt(36.35, ta, ceil - 0.02), pt(36.35, tb, ceil - 0.02), pt(36.55, tb, ceil - 0.02), pt(36.55, ta, ceil - 0.02)),
              (0, -1, 0), "concourse_glow")
        if press:
            pass                                  # architecture.py builds the press box here
        elif end:
            oquad(bld, (pt(back_m, ta, lower_top), pt(back_m, tb, lower_top), pt(back_m, tb, ceil), pt(back_m, ta, ceil)),
                  nin, "concourse_glow", ((u0 / 32, 0), (u1 / 32, 0), (u1 / 32, 1), (u0 / 32, 1)))
        else:
            oquad(bld, (pt(back_m, ta, lower_top), pt(back_m, tb, lower_top), pt(back_m, tb, ceil), pt(back_m, ta, ceil)),
                  nin, "suite_interior", ((u0 / 48, 0), (u1 / 48, 0), (u1 / 48, 1), (u0 / 48, 1)))
            oquad(bld, (pt(glass_m, ta, lower_top), pt(glass_m, tb, lower_top), pt(glass_m, tb, ceil), pt(glass_m, ta, ceil)),
                  nin, "glass_suite")
            # balcony glass rail in front of the suites
            oquad(rails.at(tm), (pt(36.25, ta, lower_top), pt(36.25, tb, lower_top), pt(36.25, tb, lower_top + 0.95),
                                 pt(36.25, ta, lower_top + 0.95)), nin, "glass_rail")
        # fascia: trim, the ribbon screen in its frame, concrete above, cap, underside, back
        rib = kit.BOWL["ribbon"]["rise"]
        fm = fas["front"]
        layers = [(fas["bottom"], rib[0] + 0.15, "steel_painted"), (rib[0] + 0.15, rib[1] - 0.15, "ribbon_screen"),
                  (rib[1] - 0.15, rib[1], "steel_painted"), (rib[1], fas["top"], "concrete_wall")]
        for y0, y1, mat in layers:
            oquad(bld, (pt(fm, ta, y0), pt(fm, tb, y0), pt(fm, tb, y1), pt(fm, ta, y1)), nin, mat,
                  ((u0 / 3, y0 / 3), (u1 / 3, y0 / 3), (u1 / 3, y1 / 3), (u0 / 3, y1 / 3)))
        oquad(bld, (pt(fm, ta, fas["top"]), pt(fm, tb, fas["top"]), pt(fas["back"], tb, fas["top"]), pt(fas["back"], ta, fas["top"])),
              (0, 1, 0), "bowl_trim", band_uv("steel", u0 / 3, u1 / 3))
        oquad(bld, (pt(fm, ta, fas["bottom"]), pt(fm, tb, fas["bottom"]), pt(fas["back"], tb, fas["bottom"]),
                    pt(fas["back"], ta, fas["bottom"])), (0, -1, 0), "concrete_wall")
        oquad(bld, (pt(fas["back"], ta, fas["bottom"]), pt(fas["back"], tb, fas["bottom"]), pt(fas["back"], tb, ceil),
                    pt(fas["back"], ta, ceil)), (-nin[0], 0, -nin[2]), "concrete_wall")
        # glass rail on the fascia
        oquad(rails.at(tm), (pt(41.9, ta, fas["top"]), pt(41.9, tb, fas["top"]), pt(41.9, tb, fas["top"] + 0.95),
                             pt(41.9, ta, fas["top"] + 0.95)), nin, "glass_rail")
        # mullions and end-concourse columns, spaced along the curve
        while next_mull <= u1:
            if next_mull >= u0:
                f = (next_mull - u0) / max(1e-6, u1 - u0)
                t = ta + (tb - ta) * f
                nx, nz = kit.inward(glass_m, t)
                yaw = math.atan2(nx, nz)
                if end:
                    if int(next_mull / mull_every) % 3 == 0:
                        bld.box(pt(38.6, t, (lower_top + ceil) / 2), (0.7, ceil - lower_top, 0.7), "concrete_wall", yaw=yaw)
                elif not press:
                    bld.box(pt(glass_m, t, (lower_top + ceil) / 2), (0.09, ceil - lower_top, 0.12), "steel_painted", yaw=yaw)
            next_mull += mull_every
        # the rail on top of the fascia glass
    top_line = [pt(41.9, t, fas["top"] + 0.97) for t in base]
    for k in range(0, len(top_line) - 1, 12):
        chunk = top_line[k:k + 13]
        rails.at(base[k]).tube(chunk, 0.03, "steel_painted", sides=5)
    del ring


# ───────────────────────────── the top ─────────────────────────────

def parapet(W: Wedges) -> None:
    m0 = T["upper"]["outer"]
    m1 = kit.PARAPET["offset"]
    y0, y1 = T["upper"]["rise"][1], kit.PARAPET["top"]
    base = kit.adaptive_angles(m1, tolerance=0.06)
    ul = arclen(m1, base)
    fin_every, next_fin = 5.0, 0.0
    for i in range(len(base) - 1):
        ta, tb = base[i], base[i + 1]
        tm = (ta + tb) / 2
        bld = W.at(tm)
        nin = inward3(m1, tm)
        u0, u1 = ul[i], ul[i + 1]
        oquad(bld, (pt(m0, ta, y0), pt(m0, tb, y0), pt(m0, tb, y1), pt(m0, ta, y1)), nin, "concrete_wall",
              ((u0 / 3, 0), (u1 / 3, 0), (u1 / 3, 0.6), (u0 / 3, 0.6)))
        oquad(bld, (pt(m0, ta, y1), pt(m0, tb, y1), pt(m1 + 0.2, tb, y1), pt(m1 + 0.2, ta, y1)), (0, 1, 0), "bowl_trim",
              band_uv("steel", u0 / 3, u1 / 3))
        oquad(bld, (pt(m1 + 0.2, ta, 26.0), pt(m1 + 0.2, tb, 26.0), pt(m1 + 0.2, tb, y1), pt(m1 + 0.2, ta, y1)),
              (-nin[0], 0, -nin[2]), "concrete_wall", ((u0 / 4, 0), (u1 / 4, 0), (u1 / 4, 5.4), (u0 / 4, 5.4)))
        while next_fin <= u1:
            if next_fin >= u0:
                f = (next_fin - u0) / max(1e-6, u1 - u0)
                t = ta + (tb - ta) * f
                nx, nz = kit.inward(m1, t)
                c = pt(m1 + 0.95, t, (26.0 + y1 + 0.6) / 2)
                bld.box(c, (0.45, y1 + 0.6 - 26.0, 1.5), "concrete_wall", yaw=math.atan2(nx, nz), uv_scale=0.3)
            next_fin += fin_every


# ───────────────────────────── far seats ─────────────────────────────

def far_seats(W: Wedges) -> None:
    """Each row of seats as one slanted band - pan edge to back top - with the
    seat texture, and every gap in it that seats.json has."""
    lip, top = 0.24, 0.93
    for tier_name in ("lower", "upper"):
        tier = T[tier_name]
        n = ROWS[tier_name]
        base = kit.adaptive_angles((tier["inner"] + tier["outer"]) / 2, tolerance=0.12)
        for r, rw, ring, seats, gaps, secs in kit.seat_rows(tier_name):
            cuts = [(a, b) for a, b, _ in gaps]
            m_feet = ring.m
            for t0, t1 in spans(cuts, ring):
                ts = sample(base, t0, t1)
                ul = arclen(m_feet, ts)
                for i in range(len(ts) - 1):
                    ta, tb = ts[i], ts[i + 1]
                    bld = W.at((ta + tb) / 2)
                    nin = inward3(m_feet, ta)
                    u0, u1 = ul[i] / (8 * kit.SEAT_PITCH), ul[i + 1] / (8 * kit.SEAT_PITCH)
                    oquad(bld, (pt(m_feet - lip, ta, rw["tread"] + 0.05), pt(m_feet - lip, tb, rw["tread"] + 0.05),
                                pt(m_feet + 0.3, tb, rw["tread"] + top), pt(m_feet + 0.3, ta, rw["tread"] + top)),
                          C._norm((nin[0], 0.6, nin[2])), "seat_band", ((u0, 0), (u1, 0), (u1, 1), (u0, 1)))


# ───────────────────────────── LOD2 ─────────────────────────────

def lod2(W: Wedges) -> None:
    group = 3
    for tier_name in ("lower", "upper"):
        tier = T[tier_name]
        n = ROWS[tier_name]
        base = kit.adaptive_angles((tier["inner"] + tier["outer"]) / 2, tolerance=0.35, max_step=10.0)
        for g0 in range(0, n, group):
            g1 = min(n, g0 + group) - 1
            first, last = kit.row(tier, g0, n), kit.row(tier, g1, n)
            f, bk, tr, rf = first["front"], last["back"], last["tread"], first["riserFrom"]
            ul = arclen(f, base)
            for i in range(len(base) - 1):
                ta, tb = base[i], base[i + 1]
                bld = W.at((ta + tb) / 2)
                nin = inward3(f, (ta + tb) / 2)
                ua, ub = ul[i] / 4.4, ul[i + 1] / 4.4
                oquad(bld, (pt(f, ta, rf), pt(f, tb, rf), pt(f, tb, tr), pt(f, ta, tr)), nin, "bowl_trim",
                      band_uv("riser", ua, ub, 0, 1))
                su0, su1 = ul[i] / (8 * kit.SEAT_PITCH), ul[i + 1] / (8 * kit.SEAT_PITCH)
                oquad(bld, (pt(f, ta, tr), pt(f, tb, tr), pt(bk, tb, tr), pt(bk, ta, tr)), (0, 1, 0), "seat_band",
                      ((su0, 0), (su1, 0), (su1, g1 - g0 + 1), (su0, g1 - g0 + 1)))
    # wall, club band, fascia and parapet as single faces
    fas = kit.FASCIA
    lower_top, ceil = T["lower"]["rise"][1], kit.CLUB["ceiling"]
    base = kit.adaptive_angles(40.0, tolerance=0.35, max_step=10.0)
    ul = arclen(40.0, base)
    for i in range(len(base) - 1):
        ta, tb = base[i], base[i + 1]
        bld = W.at((ta + tb) / 2)
        nin = inward3(40.0, (ta + tb) / 2)
        u0, u1 = ul[i], ul[i + 1]
        wm = kit.BOWL["wall"]["offset"]
        oquad(bld, (pt(wm, ta, 0), pt(wm, tb, 0), pt(wm, tb, 1.0), pt(wm, ta, 1.0)), nin, "wall_led")
        oquad(bld, (pt(wm, ta, 1.0), pt(wm, tb, 1.0), pt(wm, tb, 1.4), pt(wm, ta, 1.4)), nin, "bowl_trim",
              band_uv("padding", u0 / 3, u1 / 3))
        oquad(bld, (pt(T["lower"]["outer"], ta, lower_top), pt(T["lower"]["outer"], tb, lower_top),
                    pt(40.5, tb, lower_top), pt(40.5, ta, lower_top)), (0, 1, 0), "bowl_trim", band_uv("tread", u0 / 4.4, u1 / 4.4))
        oquad(bld, (pt(40.5, ta, lower_top), pt(40.5, tb, lower_top), pt(40.5, tb, ceil), pt(40.5, ta, ceil)), nin,
              "suite_interior", ((u0 / 48, 0), (u1 / 48, 0), (u1 / 48, 1), (u0 / 48, 1)))
        oquad(bld, (pt(T["lower"]["outer"], ta, ceil), pt(T["lower"]["outer"], tb, ceil), pt(fas["front"], tb, ceil),
                    pt(fas["front"], ta, ceil)), (0, -1, 0), "bowl_trim", band_uv("soffit", u0 / 6, u1 / 6))
        oquad(bld, (pt(fas["front"], ta, fas["bottom"]), pt(fas["front"], tb, fas["bottom"]), pt(fas["front"], tb, kit.BOWL["ribbon"]["rise"][1]),
                    pt(fas["front"], ta, kit.BOWL["ribbon"]["rise"][1])), nin, "ribbon_screen")
        oquad(bld, (pt(fas["front"], ta, kit.BOWL["ribbon"]["rise"][1]), pt(fas["front"], tb, kit.BOWL["ribbon"]["rise"][1]),
                    pt(fas["front"], tb, fas["top"]), pt(fas["front"], ta, fas["top"])), nin, "concrete_wall")
        oquad(bld, (pt(fas["front"], ta, fas["top"]), pt(fas["front"], tb, fas["top"]), pt(T["upper"]["inner"], tb, fas["top"]),
                    pt(T["upper"]["inner"], ta, fas["top"])), (0, 1, 0), "bowl_trim", band_uv("steel", u0 / 3, u1 / 3))
        pm = T["upper"]["outer"]
        oquad(bld, (pt(pm, ta, T["upper"]["rise"][1]), pt(pm, tb, T["upper"]["rise"][1]), pt(pm, tb, kit.PARAPET["top"]),
                    pt(pm, ta, kit.PARAPET["top"])), nin, "concrete_wall")


# ───────────────────────────── build ─────────────────────────────

def build() -> list[dict]:
    C.reset()
    mats = materials()
    entries = []

    def emit(name, groups, about, **extra):
        objs = []
        tris = 0
        meta = []
        for g in groups:
            objs += g.build(mats)
            tris += g.triangles
            meta += g.meta()
        e = C.export(objs, name)
        e.update({"kind": "structure", "about": about, "wedges": meta, "triangles": tris, **extra})
        entries.append(e)
        print(f"[structure] {name}: {tris} tris in {len(objs)} objects", flush=True)
        for o in objs:
            import bpy
            bpy.data.objects.remove(o)

    W, R, D = Wedges("lower", WEDGES_LOD0), Wedges("lower_rails", WEDGES_LOD0), Wedges("lower_tunnels", WEDGES_LOD0)
    tier_rows("lower", W, R, D)
    field_wall(W, R)
    team_tunnels(W, R, D)
    emit("bowl_lower_lod0", (W, R, D), "Lower tier at full detail: rows, stairs, rails, vomitories, wall, team tunnels.", lod=0)

    W, R = Wedges("club", WEDGES_LOD0), Wedges("club_rails", WEDGES_LOD0)
    club(W, R)
    emit("bowl_club_lod0", (W, R), "Club level: concourse slab, suites behind glass, end concourses, soffit, ribbon fascia.", lod=0)

    W, R, D = Wedges("upper", WEDGES_LOD0), Wedges("upper_rails", WEDGES_LOD0), Wedges("upper_tunnels", WEDGES_LOD0)
    tier_rows("upper", W, R, D)
    parapet(W)
    emit("bowl_upper_lod0", (W, R, D), "Upper tier at full detail: rows, stairs, rails, vomitories, parapet, exterior.", lod=0)

    W = Wedges("seats_far", kit.WEDGES)
    far_seats(W)
    emit("bowl_seats_far", (W,), "Every row of seats as one textured band, for seats beyond instancing range. Tint: seat_band base colour.",
         lod=2)

    W = Wedges("lod2", kit.WEDGES)
    lod2(W)
    emit("bowl_lod2", (W,), "The whole bowl stepped three rows at a time, for the tabletop (hide wedges inside the cutaway) and distance.",
         lod=2)
    C.write_manifest_part("structure", entries)
    return entries
