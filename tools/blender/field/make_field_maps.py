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

  turf/natural/paint_blades.png, paint_wear.png   the Shader Graph paint's
      blade-through and low-frequency wear (paint_wear_maps)

    blender -b --factory-startup --python tools/blender/field/make_field_maps.py
    ... --python tools/blender/field/make_field_maps.py -- paint_wear_maps
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
    X, Y = grid(4)
    # the sideline is where the chain crew, cameras and substitutes walk all night
    band = np.exp(-0.5 * (np.minimum(np.abs(Y + 2.0), np.abs(Y - W - 2.0)) / 3.0) ** 2)
    grime = band * (0.55 + 0.45 * fbm(X, Y, [0.8, 2.5, 6.0], 91))
    opacity = np.clip(0.62 * wear ** 0.9 + 0.55 * np.clip(0.5 - macro, 0, 1) + 0.22 * grime, 0, 0.8)
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


def grass_through():
    """Where blades stand up through paint: the low-carry texels of the turf's
    paint breakup, as coverage for a turf overlay drawn over the paint. 512 px,
    tiling with the turf, sRGB-encoded linear coverage."""
    src = common.FIELD_OUT / "turf" / "natural" / "paint_breakup.png"
    if not src.exists():
        return
    carry = common.read_image(src)[..., 0]
    carry = carry.reshape(512, 2, 512, 2).mean(axis=(1, 3)) if carry.shape[0] == 1024 else carry
    # the Shader Graph paint reads carry itself, raw, at the size it can afford
    common.write_png(common.FIELD_OUT / "turf" / "natural" / "paint_breakup_512.png", carry)
    cover = np.clip((0.62 - carry) / 0.3, 0, 1) ** 1.3
    common.write_png(common.FIELD_OUT / "turf" / "natural" / "paint_grassthrough.png", srgb(cover))


WEAR_YARDS = 6.0


def paint_wear_maps():
    """The two maps the Shader Graph paint wears itself with, both raw linear.

    turf/natural/paint_blades.png   512 px, tiles with the turf: how tall a
        blade stands at each texel, from the baked shell slices (the tallest
        slice counts most). Paint lets a blade through where it stands above a
        cut, so what shows is whole blades, evenly spread, not texel noise.
    turf/natural/paint_wear.png     512 px, tiles every WEAR_YARDS: low-frequency
        wear, 0 intact to 1 scuffed thin. Broad thin patches plus cleat scuffs,
        elongated along and across the field where players plant and turn. It
        lowers the blade cut and thins the paint colour in coherent patches, and
        it survives mipping where a blade texel does not.
    """
    base = common.FIELD_OUT / "turf" / "natural"
    slices = [base / f"turf_natural_shell_{k}.png" for k in range(8)]
    if all(q.exists() for q in slices[:6]):
        blades = np.zeros((512, 512))
        weights = [1.0, 0.9, 0.75, 0.55, 0.35, 0.2]
        for k, w in enumerate(weights):
            img = common.read_image(slices[k])[..., 0]
            if img.shape[0] != 512:
                img = img.reshape(512, img.shape[0] // 512, 512, img.shape[1] // 512).mean(axis=(1, 3))
            blades += w * img
        blades /= sum(weights)
        blades = np.clip(blades / max(1e-6, np.quantile(blades, 0.985)), 0, 1)
        common.write_png(base / "paint_blades.png", blades)

    n = 512
    t = (np.arange(n) + 0.5) * WEAR_YARDS / n
    X, Y = np.meshgrid(t, t)
    broad = np.zeros_like(X)
    total = 0.0
    for k, scale in enumerate((3.0, 1.5, 0.75, 0.375)):
        w = scale ** 0.8
        broad += w * value_noise(X, Y, scale, 301 + k, period=int(round(WEAR_YARDS / scale)))
        total += w
    broad /= total
    lo, hi = np.quantile(broad, 0.02), np.quantile(broad, 0.98)
    broad = (broad - lo) / (hi - lo)
    thin = smoothstep(0.3, 1.05, broad)

    r = common.rng(313)
    keep = np.ones_like(X)
    for _ in range(90):
        cx, cy = r.random() * WEAR_YARDS, r.random() * WEAR_YARDS
        angle = r.choice([0.0, np.pi / 2]) + r.normal(0, 0.35)
        length, width = r.uniform(0.04, 0.1), r.uniform(0.03, 0.06)
        dx = (X - cx + WEAR_YARDS / 2) % WEAR_YARDS - WEAR_YARDS / 2
        dy = (Y - cy + WEAR_YARDS / 2) % WEAR_YARDS - WEAR_YARDS / 2
        u = dx * np.cos(angle) + dy * np.sin(angle)
        v = -dx * np.sin(angle) + dy * np.cos(angle)
        keep *= 1 - r.uniform(0.35, 0.9) * np.exp(-0.5 * ((u / length) ** 2 + (v / width) ** 2))
    scuff = 1 - keep
    wear = np.clip(0.65 * thin + 0.7 * scuff, 0, 1)
    common.write_png(base / "paint_wear.png", wear)
    return {"bladesMean": round(float(blades.mean()), 3) if "blades" in locals() else None,
            "wearMean": round(float(wear.mean()), 3)}


def shell_atlas():
    """The eight natural shell slices at 256 px in a 4 x 2 atlas for the shell
    graph. Cell i (column i % 4, row i // 4, row 0 at the bottom of the image)
    holds the slice for layer i counted up from the ground, which is baked
    slice 7 - i. Raw linear coverage."""
    base = common.FIELD_OUT / "turf" / "natural"
    slices = [base / f"turf_natural_shell_{k}.png" for k in range(8)]
    if not all(p.exists() for p in slices):
        return
    atlas = np.zeros((512, 1024))
    for i in range(8):
        img = common.read_image(slices[7 - i])[..., 0]
        small = img.reshape(256, img.shape[0] // 256, 256, img.shape[1] // 256).mean(axis=(1, 3))
        col, row = i % 4, i // 4
        top = (1 - row) * 256                                  # row 0 in the lower half of the image
        atlas[top:top + 256, col * 256:(col + 1) * 256] = small
    common.write_png(base / "shell_atlas.png", atlas)


def main():
    only = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if only == ["paint_wear_maps"]:
        print("MAPS", paint_wear_maps())
        return
    out = {}
    for league in rules.LEAGUES:
        out[league] = field_maps(league)
        mow_patterns(league)
        engine_maps(league)
    split_orm()
    grass_through()
    shell_atlas()
    divots()
    paint_breakup()
    out["paintWear"] = paint_wear_maps()
    print("MAPS", out)


main()
