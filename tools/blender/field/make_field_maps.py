"""Field-space maps that stop a 0.40 m turf tile reading as a tile.

Everything shares the markings canvas (x -16..116, y -14..67.33 yards, top row
= far edge), so one UV transform serves turf, paint and these maps.

  maps/field_maps.png      4 texels/yd, RGBA
      R  macro variation: grass health and tone, 0.5 neutral. Scales from 4 to
         30 yards, which is the size a stand's eye picks tiling out at.
      G  wear, 0..1: the strip between the hashes, the red zones, the kickoff
         and extra-point spots, the goal mouths and the team areas.
      B  mowing direction confidence: 1 where a pattern is freshly cut and
         crisp, lower where wear has flattened it.
      A  divot density, for scattering divot decals.
  maps/mow_patterns.png    4 texels/yd, RGBA, one mowing pattern per channel,
      1 = blades lean "with", 0 = "against", soft 0.25 yd turns
      R  five-yard bands        G  ten-yard bands
      B  checkerboard (5 yd x the hash spacing)  A  diagonal diamonds
  maps/divots.png          512 px RGBA atlas, 2x2 top-down divot scars
  maps/divots_normal.png   matching OpenGL normal map
  turf/<variant>/paint_breakup.png   tiles with the turf: how much paint a
      texel of grass carries (blade tips more than soil), used to erode the
      paint edge so lines sit in the grass rather than on it

    blender -b --factory-startup --python tools/blender/field/make_field_maps.py
"""
from __future__ import annotations

import math
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import common  # noqa: E402
import rules  # noqa: E402

import numpy as np  # noqa: E402

W = 160 / 3
CANVAS = {"x0": -16.0, "x1": 116.0, "y0": -(81.375 - W) / 2, "y1": W + (81.375 - W) / 2}


def grid(ppy):
    nx = int(round((CANVAS["x1"] - CANVAS["x0"]) * ppy))
    ny = int(round((CANVAS["y1"] - CANVAS["y0"]) * ppy))
    x = CANVAS["x0"] + (np.arange(nx) + 0.5) / ppy
    y = CANVAS["y0"] + (np.arange(ny) + 0.5) / ppy
    return np.meshgrid(x, y)


def value_noise(X, Y, scale, seed, period=512):
    """Smooth value noise on a lattice `scale` yards apart, repeating every
    `period` lattice cells (so it tiles when period * scale spans the tile)."""
    r = common.rng(seed)
    gx, gy = X / scale, Y / scale
    ix, iy = np.floor(gx).astype(int), np.floor(gy).astype(int)
    fx, fy = gx - ix, gy - iy
    ux, uy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)
    table = r.random((512, 512))

    def at(i, j):
        return table[j % period, i % period]
    a, b = at(ix, iy), at(ix + 1, iy)
    c, d = at(ix, iy + 1), at(ix + 1, iy + 1)
    return (a * (1 - ux) + b * ux) * (1 - uy) + (c * (1 - ux) + d * ux) * uy


def fbm(X, Y, scales, seed):
    total, weight = np.zeros_like(X), 0.0
    for k, s in enumerate(scales):
        w = s ** 0.6
        total += value_noise(X, Y, s, seed + k) * w
        weight += w
    return total / weight


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def gauss(x, mu, sigma):
    return np.exp(-0.5 * ((x - mu) / sigma) ** 2)


def field_maps(league: str):
    L = rules.league(league)
    hash_in = L["scene"]["field"]["hashFromSideline"]
    ba = L["paint"]["benchArea"]
    X, Y = grid(4)
    inside = (X > -10) & (X < 110) & (Y > 0) & (Y < W)

    macro = 0.5 + 0.5 * (fbm(X, Y, [4, 9, 18, 30], 11) - 0.5) * 1.6
    # a sprinkler grid shows as faint greener circles on natural grass
    for sx in np.arange(-5, 106, 21.0):
        for sy in (hash_in / 2, W / 2, W - hash_in / 2):
            macro += 0.035 * gauss(np.hypot(X - sx, Y - sy), 0, 6.0)
    macro = np.clip(macro, 0, 1)

    # wear: concentrated between the hashes, where every snap happens
    between = gauss(Y, W / 2, (W / 2 - hash_in) * 1.25 + 2.0)
    along = 0.55 + 0.45 * gauss(X, 50, 22) + 0.35 * (gauss(X, 5, 4) + gauss(X, 95, 4))
    wear = between * along * 0.75
    for kx in (35.0, 65.0):                                   # kickoff spots
        wear += 0.55 * gauss(np.hypot(X - kx, Y - W / 2), 0, 1.4)
    for gx, d in ((0.0, 1), (100.0, -1)):
        wear += 0.6 * gauss(np.hypot(X - (gx + d * 7.5), Y - W / 2), 0, 1.8)   # PAT and field goal holds
        wear += 0.35 * gauss(X, gx + d * 1.5, 1.6) * gauss(Y, W / 2, 9)        # goal-line stands
    for sgn, ys in ((1, 0.0), (-1, W)):                          # team areas, just off the field
        team = smoothstep(ba["fromYard"] - 3, ba["fromYard"] + 2, X) * (1 - smoothstep(ba["toYard"] - 2, ba["toYard"] + 3, X))
        wear += 0.8 * team * gauss(Y, ys - sgn * 4.5, 3.0)
    wear *= 0.65 + 0.7 * fbm(X, Y, [1.5, 3, 6], 23)
    wear = np.clip(wear, 0, 1)

    crisp = np.clip(1.0 - wear * 1.2, 0.15, 1.0)

    r = common.rng(31)
    divot = np.zeros_like(X)
    for _ in range(420):
        cx = r.normal(50, 26)
        cy = r.normal(W / 2, (W / 2 - hash_in) + 3)
        divot += gauss(np.hypot(X - cx, Y - cy), 0, 0.35)
    divot = np.clip(divot * wear * 1.5, 0, 1) * inside

    img = np.stack([macro, wear, crisp, divot], axis=2)[::-1]
    common.write_png(common.FIELD_OUT / "maps" / league / "field_maps.png", img)
    return {"macroMean": round(float(macro[inside].mean()), 3), "wearMean": round(float(wear[inside].mean()), 3)}


def mow_patterns(league: str):
    L = rules.league(league)
    hash_in = L["scene"]["field"]["hashFromSideline"]
    X, Y = grid(4)
    turn = 0.25

    def bands(coord, width):
        return _square(np.mod(coord, 2 * width), width, turn)

    five = bands(X, 5.0)
    ten = bands(X, 10.0)
    cells_y = W / 2 - hash_in                                   # checker rows follow the hash spacing
    checker = np.abs(bands(X, 5.0) - bands(Y - W / 2, max(cells_y, 3.0)))
    diag = np.abs(bands((X + Y) / math.sqrt(2), 5.0) - bands((X - Y) / math.sqrt(2), 5.0))
    img = np.stack([five, ten, checker, diag], axis=2)[::-1]
    common.write_png(common.FIELD_OUT / "maps" / league / "mow_patterns.png", img)


def _square(phase, width, turn):
    # distance to the nearest band edge, signed positive inside even bands
    in_even = phase < width
    local = np.where(in_even, phase, phase - width)
    edge = np.minimum(local, width - local)
    signed = np.where(in_even, edge, -edge)
    return smoothstep(-turn, turn, signed)


def divots():
    size, cells = 512, 2
    cell = size // cells
    rgba = np.zeros((size, size, 4))
    height = np.zeros((size, size))
    r = common.rng(41)
    yy, xx = np.mgrid[0:cell, 0:cell]
    for i in range(cells):
        for j in range(cells):
            cx, cy = cell / 2 + r.normal(0, 8), cell / 2 + r.normal(0, 8)
            ang = r.uniform(0, math.pi)
            a, b = r.uniform(58, 80), r.uniform(26, 36)
            u = ((xx - cx) * math.cos(ang) + (yy - cy) * math.sin(ang)) / a
            v = (-(xx - cx) * math.sin(ang) + (yy - cy) * math.cos(ang)) / b
            edge_noise = 0.18 * (value_noise(xx.astype(float), yy.astype(float), 9.0, 50 + i * 2 + j) - 0.5)
            rr = np.sqrt(u * u + v * v) + edge_noise
            scar = 1 - smoothstep(0.85, 1.0, rr)
            # torn sod flipped at the far end of the scar
            su, sv = u - 1.25, v
            sod = 1 - smoothstep(0.35, 0.5, np.sqrt((su / 0.55) ** 2 + (sv / 1.0) ** 2) + edge_noise)
            soil = np.array([0.20, 0.14, 0.09]) * (0.75 + 0.5 * value_noise(xx.astype(float), yy.astype(float), 3.0, 60 + i + j))[..., None]
            grass = np.array([0.10, 0.20, 0.06])
            col = soil * scar[..., None]
            col = col * (1 - sod[..., None]) + grass * sod[..., None]
            alpha = np.clip(scar + sod, 0, 1)
            h = -0.6 * scar + 0.8 * sod
            y0, x0 = i * cell, j * cell
            rgba[y0:y0 + cell, x0:x0 + cell, :3] = col
            rgba[y0:y0 + cell, x0:x0 + cell, 3] = alpha
            height[y0:y0 + cell, x0:x0 + cell] = h
    srgb = np.where(rgba[..., :3] <= 0.0031308, rgba[..., :3] * 12.92, 1.055 * np.power(np.clip(rgba[..., :3], 0, 1), 1 / 2.4) - 0.055)
    common.write_png(common.FIELD_OUT / "maps" / "divots.png", np.concatenate([srgb, rgba[..., 3:4]], axis=2))
    gy, gx = np.gradient(height)
    n = np.stack([-gx * 2.0, gy * 2.0, np.ones_like(height)], axis=2)
    n /= np.linalg.norm(n, axis=2, keepdims=True)
    common.write_png(common.FIELD_OUT / "maps" / "divots_normal.png", n * 0.5 + 0.5)


def paint_breakup():
    for variant, name in (("natural", "turf_natural_with_orm.png"), ("synthetic", "turf_synthetic_any_orm.png")):
        src = common.FIELD_OUT / "turf" / variant / name
        if not src.exists():
            print("SKIP breakup, missing", src)
            continue
        orm = common.read_image(src)
        height = orm[..., 2]
        h = (height - height.min()) / max(1e-6, height.max() - height.min())
        ny, nx = h.shape
        Xp, Yp = np.meshgrid(np.arange(nx, dtype=float), np.arange(ny, dtype=float))
        # tile-safe noise: lattice period divides the tile
        speck = value_noise(Xp, Yp, nx / 64, 71, period=64)
        carry = np.clip(0.25 + 0.95 * smoothstep(0.15, 0.75, h) + 0.25 * (speck - 0.5), 0, 1)
        common.write_png(common.FIELD_OUT / "turf" / variant / "paint_breakup.png", carry)


def srgb(x):
    x = np.clip(x, 0, 1)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055)


def engine_maps(league: str):
    """Single-channel maps a stock PBR material can bind without a shader.

    variation_opacity.png: how much a dark, worn-olive overlay covers the turf,
    from wear and the macro map. sRGB-encoded, so a colour-decoding loader gets
    the linear opacity back.
    """
    img = common.read_image(common.FIELD_OUT / "maps" / league / "field_maps.png")
    macro, wear = img[..., 0], img[..., 1]
    opacity = np.clip(0.62 * wear ** 0.9 + 0.55 * np.clip(0.5 - macro, 0, 1), 0, 0.8)
    common.write_png(common.FIELD_OUT / "maps" / league / "variation_opacity.png", srgb(opacity))


def split_orm():
    """Roughness and occlusion as their own grey images: a PBR material reads
    one channel per property, and not the green of a packed ORM."""
    for variant, stem in (("natural", "turf_natural_with"), ("synthetic", "turf_synthetic_any")):
        src = common.FIELD_OUT / "turf" / variant / f"{stem}_orm.png"
        if not src.exists():
            continue
        orm = common.read_image(src)
        common.write_png(common.FIELD_OUT / "turf" / variant / f"{stem}_roughness.png", orm[..., 1])
        common.write_png(common.FIELD_OUT / "turf" / variant / f"{stem}_occlusion.png", orm[..., 0])


def main():
    out = {}
    for league in rules.LEAGUES:
        out[league] = field_maps(league)
        mow_patterns(league)
        engine_maps(league)
    split_orm()
    divots()
    paint_breakup()
    print("MAPS", out)


main()
