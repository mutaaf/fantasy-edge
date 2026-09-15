"""Light that lives on cards, and the sky it hangs in: every sprite and sky image.

    blender --background --factory-startup --python tools/blender/lighting/textures.py -- [group ...]

Groups: sprites, decals, sky. Deterministic: seeded numpy, dithered 8-bit.

Conventions a renderer relies on:
  * Light sprites are white RGB with the shape in alpha. The renderer tints
    them from look tokens and draws them additively (colour * alpha), so a
    card's alpha must reach exactly 0 before its edge - a visible square
    border on a glow is the cheapest tell of a cheap stadium.
  * Beam textures run U across the beam, V along it, V=0 at the lamp.
  * Sky images are equirectangular, top row = zenith, centre column = -Z
    (the far side), +X to the right.
"""
from __future__ import annotations

import math
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import common as C  # noqa: E402

_save = C.save_png


def save_png(path, rgba, seed=0, srgb_encode=False):
    _save(path, rgba, seed=seed, srgb_encode=srgb_encode, dither_rgb=not isinstance(rgba, White))

import numpy as np  # noqa: E402


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def grid(w, h):
    y, x = np.mgrid[0:h, 0:w]
    return (x + 0.5) / w, (y + 0.5) / h


class White(np.ndarray):
    """Marks a sprite whose colour is flat white, so only its alpha is dithered."""


def white(alpha):
    h, w = alpha.shape
    out = np.ones((h, w, 4))
    out[..., 3] = np.clip(alpha, 0, 1)
    return out.view(White)


def value_noise(w, h, cells_x, cells_y, seed, tile=True):
    """Smooth tileable value noise, cells_x by cells_y lattice cells."""
    rng = np.random.default_rng(seed)
    lat = rng.random((cells_y, cells_x))
    u, v = grid(w, h)
    fx, fy = u * cells_x, v * cells_y
    x0, y0 = np.floor(fx).astype(int), np.floor(fy).astype(int)
    tx, ty = fx - x0, fy - y0
    tx, ty = tx * tx * (3 - 2 * tx), ty * ty * (3 - 2 * ty)
    x1, y1 = (x0 + 1) % cells_x, (y0 + 1) % cells_y
    x0, y0 = x0 % cells_x, y0 % cells_y
    a = lat[y0, x0] * (1 - tx) + lat[y0, x1] * tx
    b = lat[y1, x0] * (1 - tx) + lat[y1, x1] * tx
    return a * (1 - ty) + b * ty


def fbm(w, h, base_x, base_y, octaves, seed, gain=0.5):
    total, amp, norm = np.zeros((h, w)), 1.0, 0.0
    for o in range(octaves):
        total += amp * value_noise(w, h, base_x * 2 ** o, base_y * 2 ** o, seed + o)
        norm += amp
        amp *= gain
    return total / norm


# ───────────────────────────── sprites ─────────────────────────────

def sprites():
    out = C.OUT_LIGHT / "textures"
    # The core: what the eye reads as the lamp itself. Tight, with a short
    # shoulder so it does not look like a disc.
    s = 256
    u, v = grid(s, s)
    r = np.hypot(u - 0.5, v - 0.5) * 2
    core = np.exp(-(r / 0.16) ** 2) * 0.85 + np.exp(-(r / 0.42) ** 2) * 0.35
    core *= 1 - smoothstep(0.78, 1.0, r)
    save_png(out / "glow_core.png", white(core), seed=1)

    # The halo: the veil a lens and wet air put round a bright source. A
    # long 1/(1+kr^2) tail, windowed to zero well inside the card.
    s = 512
    u, v = grid(s, s)
    r = np.hypot(u - 0.5, v - 0.5) * 2
    halo = 1.0 / (1.0 + (r / 0.09) ** 2) - 1.0 / (1.0 + (1 / 0.09) ** 2)
    halo = np.clip(halo, 0, None) / halo.max()
    halo *= 1 - smoothstep(0.55, 0.98, r)
    save_png(out / "glow_halo.png", white(halo * 0.9), seed=2)

    # Bloom card: the faint, very wide lift over a whole light bank. It is
    # meant to be nearly invisible alone and to pool where banks overlap.
    s = 512
    u, v = grid(s, s)
    r = np.hypot((u - 0.5) * 2, (v - 0.5) * 2 * 1.6)
    bloom = np.exp(-(r / 0.5) ** 2) * (1 - smoothstep(0.7, 1.0, np.hypot(u - 0.5, v - 0.5) * 2))
    save_png(out / "bloom_card.png", white(bloom * 0.55), seed=3)

    # Beam, for a crossed-quad cone: across a soft Gaussian, along a bright
    # throat near the lamp decaying with distance, never a hard far edge.
    w, h = 256, 1024
    u, v = grid(w, h)
    across = np.exp(-((u - 0.5) / 0.22) ** 2) * (1 - smoothstep(0.38, 0.5, np.abs(u - 0.5)))
    along = (0.25 + 0.75 * np.exp(-v * 3.2)) * smoothstep(0.0, 0.035, v) * (1 - smoothstep(0.7, 1.0, v))
    save_png(out / "beam_quad.png", white(across * along), seed=4)

    # Beam, for a true cone mesh (U round the cone, V along): no across
    # falloff baked in - the renderer fades by view angle (fresnel) - only
    # the along profile and faint striations where individual LEDs overlap.
    w, h = 512, 1024
    u, v = grid(w, h)
    stri = 0.86 + 0.14 * value_noise(w, h, 48, 2, 41)
    cone = (0.2 + 0.8 * np.exp(-v * 2.6)) * smoothstep(0.0, 0.03, v) * (1 - smoothstep(0.72, 1.0, v)) * stri
    save_png(out / "beam_cone.png", white(cone), seed=5)

    # Scrolling dust in the beam: tileable, low contrast, multiplied in and
    # scrolled slowly along V so the air moves.
    n = fbm(256, 512, 6, 12, 4, 51)
    n = 0.55 + 0.45 * smoothstep(0.25, 0.8, n)
    img = np.ones((512, 256, 4))
    img[..., :3] = n[..., None]
    save_png(out / "beam_noise.png", img, seed=6)

    # Haze layer: a tileable sheet of thin air for large, faint cards laid
    # through the upper bowl, catching light near the banks.
    n = fbm(512, 512, 4, 4, 5, 61)
    haze = smoothstep(0.2, 0.9, n) * 0.55 + 0.35 * n
    save_png(out / "haze_layer.png", white(haze), seed=7)

    # Haze band: the same thin air laid round the bowl as a ring whose V runs
    # from its inner edge (0) to its outer edge (1). Both edges fade to zero,
    # so a sheet of it never shows a rim; U tiles round the bowl.
    n = fbm(1024, 256, 8, 2, 5, 71)
    band = np.sin(np.clip(grid(1024, 256)[1], 0, 1) * np.pi) ** 1.6
    wisps = smoothstep(0.25, 0.9, n) * 0.7 + 0.3 * n
    save_png(out / "haze_band.png", white(band * wisps), seed=14)

    # Spill: floodlight lying on the stands under a bank. Wide, flat-bottomed
    # (the light is strongest on the rows nearest the bank, at the card's
    # top) and fading to nothing at every edge.
    w, h = 512, 256
    u_, v_ = grid(w, h)
    across = np.exp(-((u_ - 0.5) / 0.26) ** 2)
    down = np.exp(-((v_ - 0.35) / 0.28) ** 2)
    edge = (1 - smoothstep(0.38, 0.5, np.abs(u_ - 0.5))) * (1 - smoothstep(0.38, 0.5, np.abs(v_ - 0.5)))
    save_png(out / "spill_card.png", white(across * down * edge), seed=15)

    # Beam dust: tiles along V (the beam's length), soft Gaussian across U so
    # the drifting motes stay inside the shaft. Streaky and sparse.
    w, h = 128, 512
    u_, v_ = grid(w, h)
    motes = value_noise(w, h, 24, 96, 81) ** 6 * 3.0
    drift = fbm(w, h, 4, 8, 4, 82)
    across = np.exp(-((u_ - 0.5) / 0.2) ** 2) * (1 - smoothstep(0.4, 0.5, np.abs(u_ - 0.5)))
    save_png(out / "beam_dust.png", white(np.clip((0.35 * drift + motes) * across, 0, 1)), seed=16)

    # Moths: eight frames of a wingbeat, lit from behind (bright edges,
    # dark body), 64 px each. A handful drift in the throat of a beam.
    fw, frames = 64, 8
    atlas = np.zeros((fw, fw * frames, 4))
    atlas[..., :3] = 1.0
    yy, xx = np.mgrid[0:fw, 0:fw]
    px, py = (xx + 0.5) / fw - 0.5, (yy + 0.5) / fw - 0.5
    for f in range(frames):
        beat = math.sin(2 * math.pi * f / frames)
        span = 0.30 * (0.55 + 0.45 * abs(beat))
        lift = 0.10 * beat
        body = np.exp(-((px / 0.035) ** 2 + (py / 0.14) ** 2))
        wings = np.zeros_like(px)
        for side in (-1, 1):
            wx = (px - side * span * 0.5) / (span * 0.55)
            wy = (py + lift * np.abs(px) * 3 + 0.02) / 0.13
            wing = np.exp(-(wx ** 2 + wy ** 2) * 1.6)
            wings = np.maximum(wings, wing)
        a = np.clip(np.maximum(wings * 0.75, body * 0.35), 0, 1)
        a *= 1 - smoothstep(0.40, 0.5, np.maximum(np.abs(px), np.abs(py)))
        atlas[:, f * fw:(f + 1) * fw, 3] = a
    save_png(out / "moth_atlas.png", atlas, seed=8)


# ───────────────────────────── decals ─────────────────────────────

def decals():
    out = C.OUT_LIGHT / "textures"
    # Four soft shadows round a prop, one per light bank quadrant: the
    # cheap multi-shadow a floodlit object throws. Black RGB, alpha = shadow.
    s = 512
    u, v = grid(s, s)
    x, y = (u - 0.5) * 2, (v - 0.5) * 2
    a = np.zeros((s, s))
    for ang in (math.radians(35), math.radians(145), math.radians(215), math.radians(325)):
        dx, dy = math.cos(ang), math.sin(ang)
        along = x * dx + y * dy
        across = -x * dy + y * dx
        lobe = np.exp(-(across / (0.10 + 0.12 * np.clip(along, 0, 1))) ** 2) * np.clip(along, 0, 1) ** 0.3
        lobe *= 1 - smoothstep(0.55, 0.95, along)
        a += lobe * 0.28
    a += np.exp(-(np.hypot(x, y) / 0.12) ** 2) * 0.45
    a *= 1 - smoothstep(0.85, 1.0, np.hypot(x, y))
    img = np.zeros((s, s, 4))
    img[..., 3] = np.clip(a, 0, 0.7)
    save_png(out / "shadow_multi.png", img, seed=9)

    # Concourse fill: warm light spilling out of the concourse and the
    # vomitories onto a wall face. V = 0 at the foot of the face, where the
    # walkway throws light up it, fading toward the top; U tiles round the bowl
    # with soft pools where the openings are.
    w, h = 512, 128
    u, v = grid(w, h)
    rise = np.exp(-(1 - v) * 2.4)
    pools = 0.55 + 0.45 * np.cos(u * 2 * np.pi * 3) ** 2
    img = np.ones((h, w, 4))
    img[..., 3] = np.clip(rise * pools, 0, 1)
    save_png(out / "fill_band.png", img.view(White), seed=17)

    # Contact AO for a seating riser: dark in the corner where the tread
    # meets the next riser, fading up the riser and out across the tread.
    # V=0 is the tread's back edge (the corner), tiles along U.
    w, h = 64, 256
    u, v = grid(w, h)
    ao = 1 - 0.55 * np.exp(-v / 0.08) - 0.18 * np.exp(-(1 - v) / 0.05)
    img = np.ones((h, w, 4))
    img[..., :3] = ao[..., None]
    save_png(out / "ao_riser.png", img, seed=10)


# ───────────────────────────── sky ─────────────────────────────

def sky_image(w, h, kind, seed):
    """Scene-linear equirect sky. kind: night | dusk."""
    d, th, ph = C.equirect_dirs(w, h)
    el = th
    up = np.clip(el, 0, None)
    rng = np.random.default_rng(seed)

    if kind == "night":
        zenith = np.array([0.0016, 0.0032, 0.0135])   # navy at 6x display exposure
        horizon = np.array([0.0080, 0.0105, 0.0200])
        pollute = np.array([0.040, 0.028, 0.017])     # sodium and LED mix, kept to the horizon
    else:
        zenith = np.array([0.012, 0.024, 0.075])
        horizon = np.array([0.30, 0.16, 0.10])
        pollute = np.array([0.20, 0.07, 0.03])

    t = np.power(1 - np.clip(up / (np.pi / 2), 0, 1), 3.2)[..., None]
    img = zenith * (1 - t) + horizon * t

    # Light pollution: a city glow that is stronger in two directions, so
    # the horizon is not a uniform ring.
    city = 0.55 + 0.45 * np.cos(ph - 0.9) ** 8 + 0.25 * np.cos(ph + 2.2) ** 16
    img += pollute * (np.exp(-up * 14.0) * city)[..., None]

    if kind == "dusk":
        sun_az = 2.4
        glow = np.exp(-((ph - sun_az + np.pi) % (2 * np.pi) - np.pi) ** 2 / 0.6) * np.exp(-up * 4.5)
        img += np.array([0.9, 0.34, 0.10]) * glow[..., None] * 0.9
        band = np.exp(-((up - 0.22) / 0.12) ** 2) * 0.05
        img += np.array([0.35, 0.10, 0.25]) * band[..., None]

    # Stars: magnitude-weighted, dimmed by extinction near the horizon and
    # drowned by light pollution; very few at dusk.
    count = 1800 if kind == "night" else 200
    su = rng.random(count)
    sv = np.arcsin(rng.random(count))                  # uniform over the upper hemisphere
    mag = rng.random(count) ** 7
    temp = rng.random(count)
    stars = np.zeros((h, w, 3))
    for i in range(count):
        cx = su[i] * w
        cy = (0.5 - sv[i] / np.pi) * h
        if cy < 1 or cy > h * 0.5 - 2:
            continue
        ext = math.sin(sv[i]) ** 0.8
        b = (0.05 + 5.0 * mag[i]) * ext * 0.12
        col = np.array([1.0, 0.95, 0.9]) if temp[i] < 0.6 else np.array([0.85, 0.9, 1.0])
        x0, y0 = int(cx), int(cy)
        for oy in (-1, 0, 1):
            for ox in (-1, 0, 1):
                xx, yy = (x0 + ox) % w, y0 + oy
                if 0 <= yy < h:
                    wgt = math.exp(-((xx + 0.5 - cx) ** 2 + (yy + 0.5 - cy) ** 2) / 0.12)
                    stars[yy, xx] += col * b * wgt
    haze_mask = np.exp(-up * 5)[..., None]
    img += stars * (1 - 0.85 * haze_mask)

    # Clouds: thin, wind-stretched cirrostratus rather than cotton wool. At
    # night they are barely there - a slight veil that eats stars and
    # catches a cool-grey lift from the city, warmed only directly over the
    # stadium, where the floodlights reach them.
    n = fbm(w, h // 2, 14, 3, 6, seed + 100, gain=0.55)
    streak = fbm(w, h // 2, 40, 2, 3, seed + 200)
    cover = smoothstep(0.50, 0.80, n) * (0.55 + 0.45 * streak)
    cloud = np.zeros((h, w))
    cloud[: h // 2] = cover
    cloud *= smoothstep(0.03, 0.22, up) * (1 - smoothstep(0.85, 1.2, up))
    if kind == "night":
        cloud *= 0.55
        under = np.array([0.009, 0.010, 0.015])
        overhead = np.exp(-((np.pi / 2 - up) / 0.45) ** 2)[..., None] * np.array([0.020, 0.017, 0.013])
    else:
        under = np.array([0.30, 0.15, 0.11])
        overhead = np.zeros((h, w, 1))
    city_lift = (np.exp(-up * 3.0) * city)[..., None] * (pollute * 0.6)
    cloud_col = under + city_lift + overhead
    img = img * (1 - cloud[..., None] * 0.7) + cloud_col * cloud[..., None]

    # Below the horizon: the dark ground outside the stadium, never seen
    # past the bowl but kept dark so a probe made from this sky is honest.
    below = el < 0
    img[below] = np.array([0.006, 0.006, 0.007])
    return img, cloud


def sky():
    out = C.OUT_SKY
    for kind, seed in (("night", 301), ("dusk", 302)):
        img, cloud = sky_image(2048, 1024, kind, seed)
        C.save_float(out / "env" / f"sky_{kind}.exr", img)
        # An 8-bit sRGB dome texture for a renderer that cannot sample float:
        # exposed so the brightest horizon glow sits below 1.
        expose = 6.0 if kind == "night" else 1.6
        disp = np.clip(img * expose, 0, 1)
        rgba = np.concatenate([disp, np.ones(disp.shape[:2] + (1,))], axis=2)
        save_png(out / "textures" / f"sky_{kind}.png", rgba, seed=11, srgb_encode=True)
        if kind == "night":
            cl = np.ones(cloud.shape + (4,))
            cl[..., :3] = 1.0
            cl[..., 3] = cloud
            save_png(out / "textures" / "sky_clouds.png", cl, seed=12)


def dome():
    """The light a floodlit bowl throws into the air above its rim, for a
    band of quads standing on the rim: bright at the rim (top row, which a
    renderer maps to v = 1), gone well before the band's top, tiling round
    the bowl with soft pools where banks would be."""
    w, h = 1024, 256
    u, v = grid(w, h)
    rise = np.exp(-v * 3.6) * (1 - smoothstep(0.7, 1.0, v))
    pools = 0.75 + 0.25 * np.cos(u * 2 * np.pi * 2.5) ** 2
    n = fbm(w, h, 8, 2, 4, 401)
    a = rise * pools * (0.8 + 0.2 * n)
    save_png(C.OUT_SKY / "textures" / "light_dome.png", white(a), seed=13)


GROUPS = {"sprites": sprites, "decals": decals, "sky": sky, "dome": dome}

if __name__ == "__main__":
    wanted = C.args() or list(GROUPS)
    for g in wanted:
        GROUPS[g]()
        print(f"[lighting] wrote {g}")
