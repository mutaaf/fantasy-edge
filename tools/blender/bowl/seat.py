"""One stadium seat, three levels of detail, folded and occupied.

Modelled in metres from a real bolt-down stadium chair: a moulded polymer
bucket on a hinged pan, a steel standard with an armrest and cupholder on
its left, and a numbered aluminium plaque on the back for the row behind.
Origin is the seat's feet on the tread, centred; it faces +z. A renderer
turns it by the yaw in seats.json: x' = x cos(yaw) + z sin(yaw),
z' = -x sin(yaw) + z cos(yaw).

Modules written:
  seat_lod0_up / seat_lod0_down   ~1.1k tris, for the rows around the wearer
  seat_lod1_up / seat_lod1_down   ~150 tris, for a section or two out
  seat_lod2                       12 tris, folded, for anything further
"""
from __future__ import annotations

import math

import common as C
import kit

M = 1 / kit.YARD           # metres to yards


def P(x, y, z):
    return (x * M, y * M, z * M)


def materials():
    return {
        # A venue colour multiplies the near-white shell; renderers replace the factor.
        "seat_plastic": C.material("seat_plastic", color=(0.035, 0.06, 0.16, 1.0), albedo="seat_plastic_albedo.png",
                                   normal="seat_plastic_normal.png", orm="seat_plastic_orm.png", normal_strength=0.12),
        # Powder-coated steel: smooth, satin, no scan - a diamond plate reads as bark at this size.
        "seat_hardware": C.material("seat_hardware", color=(0.045, 0.047, 0.052, 1.0), roughness=0.42, metallic=0.65),
        "seat_cup": C.material("seat_cup", color=(0.03, 0.03, 0.035, 1.0), roughness=0.5),
        "seat_plaque": C.material("seat_plaque", color=(0.78, 0.79, 0.80, 1.0), roughness=0.35, metallic=1.0),
    }


# ───────────────────────────── surfaces ─────────────────────────────

def back_surface(u, v):
    """The seat back: lumbar curve, wings coming forward, a rolled top lip."""
    x = u * (0.228 - 0.022 * v)
    y = 0.47 + 0.37 * v
    z = -0.205 - 0.065 * v - 0.014 * math.sin(math.pi * v) + 0.03 * u * u
    if v > 0.88:
        z -= (v - 0.88) * 0.22
        y -= (v - 0.88) * 0.05
    return x, y, z


def pan_surface(u, v, up: bool):
    """The hinged pan: dished, sides up, lip rolled down at the front."""
    x = u * 0.218
    z = -0.17 + v * 0.39
    y = 0.43 + v * 0.025 - 0.02 * math.sin(math.pi * v) * (1 - u * u) + 0.018 * u * u
    if v > 0.88:
        y -= (v - 0.88) * 0.35
    if up:
        # Fold about the hinge (y 0.44, z -0.17) until the pan stands against the back.
        ry, rz = y - 0.44, z + 0.17
        th = math.radians(-78)
        y = 0.44 + ry * math.cos(th) - rz * math.sin(th)
        z = -0.17 + ry * math.sin(th) + rz * math.cos(th)
    return x, y, z


def shell(b: C.Builder, surf, nu: int, nv: int, thickness: float, material: str, solid: bool, rim: bool = True) -> None:
    """A thin moulded shell from a parametric surface: front, back, and rim."""
    def grid(offset):
        pts = []
        for j in range(nv + 1):
            row = []
            for i in range(nu + 1):
                u = -1 + 2 * i / nu
                v = j / nv
                x, y, z = surf(u, v)
                if offset:
                    # push along the surface normal, estimated by differences
                    e = 1e-3
                    xu = surf(min(1, u + e), v); xu0 = surf(max(-1, u - e), v)
                    xv = surf(u, min(1, v + e)); xv0 = surf(u, max(0, v - e))
                    tu = C._sub(xu, xu0); tv = C._sub(xv, xv0)
                    n = C._norm(C._cross(tu, tv))
                    x, y, z = x - n[0] * offset, y - n[1] * offset, z - n[2] * offset
                row.append(P(x, y, z))
            pts.append(row)
        return pts

    front = grid(0.0)
    back = grid(thickness) if solid else None
    for j in range(nv):
        for i in range(nu):
            uv = ((i / nu, j / nv), ((i + 1) / nu, j / nv), ((i + 1) / nu, (j + 1) / nv), (i / nu, (j + 1) / nv))
            b.quad(front[j][i], front[j][i + 1], front[j + 1][i + 1], front[j + 1][i], material, uv)
            if solid:
                b.quad(back[j][i + 1], back[j][i], back[j + 1][i], back[j + 1][i + 1], material, uv)
            else:
                b.quad(front[j][i + 1], front[j][i], front[j + 1][i], front[j + 1][i + 1], material, uv)
    if solid and rim:
        # the rim: walk the boundary and stitch front to back
        edge = ([(0, i) for i in range(nu + 1)] + [(j, nu) for j in range(1, nv + 1)]
                + [(nv, i) for i in range(nu - 1, -1, -1)] + [(j, 0) for j in range(nv - 1, 0, -1)])
        for k in range(len(edge)):
            j0, i0 = edge[k]
            j1, i1 = edge[(k + 1) % len(edge)]
            b.quad(front[j0][i0], back[j0][i0], back[j1][i1], front[j1][i1], material,
                   uv=((0.0, 0.0), (0.0, 0.01), (0.01, 0.01), (0.01, 0.0)))


def profile_plate(b: C.Builder, outline, x: float, thickness: float, material: str) -> None:
    """An extruded side plate: outline in (z, y) metres at lateral x."""
    n = len(outline)
    l = [P(x - thickness / 2, y, z) for z, y in outline]
    r = [P(x + thickness / 2, y, z) for z, y in outline]
    b.face(list(reversed(l)), [(0, 0)] * n, material)
    b.face(r, [(0, 0)] * n, material)
    for k in range(n):
        k2 = (k + 1) % n
        b.quad(l[k], l[k2], r[k2], r[k], material)


def cylinder(b: C.Builder, centre, radius, y0, y1, sides, material, inner=None):
    cx, cz = centre
    ring = lambda r, y: [P(cx + r * math.cos(2 * math.pi * k / sides), y, cz + r * math.sin(2 * math.pi * k / sides))
                         for k in range(sides)]
    o0, o1 = ring(radius, y0), ring(radius, y1)
    for k in range(sides):
        k2 = (k + 1) % sides
        b.quad(o0[k], o0[k2], o1[k2], o1[k], material)
    if inner:
        i0, i1 = ring(inner, y0 + 0.008), ring(inner, y1)
        for k in range(sides):
            k2 = (k + 1) % sides
            b.quad(i1[k], i1[k2], i0[k2], i0[k], material)
            b.quad(o1[k], o1[k2], i1[k2], i1[k], material)
        b.face(list(reversed(i0)), [(0, 0)] * sides, material)
    b.face(list(reversed(o0)), [(0, 0)] * sides, material)


# ───────────────────────────── the chair ─────────────────────────────

HALF_PITCH = kit.SEAT_PITCH * kit.YARD / 2


def standard(b: C.Builder, detail: int) -> None:
    """The steel standard on the seat's left, with armrest and cupholder."""
    x = -HALF_PITCH + 0.012
    if detail == 0:
        outline = [(-0.30, 0.0), (0.03, 0.0), (0.03, 0.014), (-0.035, 0.03), (-0.055, 0.22),
                   (-0.07, 0.42), (-0.09, 0.60), (-0.16, 0.61), (-0.15, 0.44), (-0.17, 0.26),
                   (-0.21, 0.05), (-0.30, 0.014)]
        profile_plate(b, outline, x, 0.014, "seat_hardware")
        # armrest: a moulded bar with a rounded front, cupholder under the tip
        arm = [(-0.20, 0.61), (0.10, 0.61)]
        pts = [P(x, 0.625, z) for z in (-0.20, -0.05, 0.08, 0.11)]
        b.tube([(p[0], p[1], p[2]) for p in pts], 0.022 * M, "seat_cup", sides=8, caps=True)
        cylinder(b, (x, 0.145), 0.042, 0.555, 0.628, 14, "seat_cup", inner=0.035)
        # foot bolts
        for z in (-0.26, -0.02):
            cylinder(b, (x, z), 0.012, 0.0, 0.02, 6, "seat_hardware")
        del arm
    else:
        b.box(P(x, 0.30, -0.10), (0.014 * M, 0.60 * M, 0.06 * M), "seat_hardware", skip=("bottom",))
        b.box(P(x, 0.02, -0.12), (0.03 * M, 0.04 * M, 0.30 * M), "seat_hardware", skip=("bottom",))
        b.box(P(x, 0.625, -0.04), (0.04 * M, 0.035 * M, 0.30 * M), "seat_cup", skip=("bottom",))


def plaque(b: C.Builder) -> None:
    b.box(P(0.0, 0.79, -0.292), (0.08 * M, 0.035 * M, 0.004 * M), "seat_plaque")


def seat(detail: int, up: bool) -> C.Builder:
    b = C.Builder(f"seat_lod{detail}_{'up' if up else 'down'}")
    if detail == 0:
        shell(b, back_surface, 10, 12, 0.013, "seat_plastic", solid=True)
        shell(b, lambda u, v: pan_surface(u, v, up), 10, 10, 0.013, "seat_plastic", solid=True)
        # the pan's hinge bar and the back's mounting tube
        b.tube([P(-0.22, 0.44, -0.17), P(0.22, 0.44, -0.17)], 0.011 * M, "seat_hardware", sides=8, caps=True)
        b.tube([P(-0.2415, 0.50, -0.235), P(0.2415, 0.50, -0.235)], 0.013 * M, "seat_hardware", sides=8, caps=True)
        standard(b, 0)
        plaque(b)
    elif detail == 1:
        shell(b, back_surface, 4, 4, 0.01, "seat_plastic", solid=True, rim=False)
        shell(b, lambda u, v: pan_surface(u, v, up), 3, 3, 0.01, "seat_plastic", solid=True, rim=False)
        standard(b, 1)
    else:
        shell(b, back_surface, 1, 2, 0.01, "seat_plastic", solid=True, rim=False)
        shell(b, lambda u, v: pan_surface(u, v, True), 1, 1, 0.01, "seat_plastic", solid=True, rim=False)
    return b


def build() -> list[dict]:
    C.reset()
    mats = materials()
    entries = []
    for detail, up in ((0, True), (0, False), (1, True), (1, False), (2, True)):
        b = seat(detail, up)
        obj = b.build(mats, smooth_angle=50 if detail < 2 else None)
        name = "seat_lod2" if detail == 2 else b.name
        obj.name = name
        e = C.export([obj], name)
        e.update({"kind": "seat", "lod": detail, "folded": up,
                  "about": "Origin at the feet, facing +z; turn by seats.json yaw. Tint via seat_plastic base colour."})
        entries.append(e)
        print(f"[seat] {name}: {b.triangles} tris", flush=True)
    C.write_manifest_part("seat", entries)
    return entries
