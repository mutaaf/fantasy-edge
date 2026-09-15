"""The bowl kit's textures: CC0 scans where a real surface matters, numpy
where the pattern is ours.

Sources are fetched once into .work/bowl-sources and
every committed map is derived from them here, deterministically. The trim
sheet is the kit's main material: one 2048 map, banded, that every riser,
tread, nosing, pad, steel edge and soffit panel in the bowl samples by v,
tiling along u - no unique UVs anywhere in the stands.

    blender --background --factory-startup --python tools/blender/bowl/build.py -- textures
"""
from __future__ import annotations

import json
import pathlib
import urllib.request

import bpy
import numpy as np

import kit

OUT = kit.OUT
# Working files live in .work/ (ignored, never bundled): the app bundles
# assets/ whole, and every texture already rides inside its .usdz and .glb.
TEX = kit.ROOT / ".work" / "bowl-textures"
CACHE = kit.ROOT / ".work" / "bowl-sources"

SOURCES = {
    "concrete_floor_worn_001": ("diff", "nor_gl", "arm"),
    "painted_concrete": ("diff", "nor_gl", "arm"),
    "metal_plate": ("diff", "nor_gl", "arm"),
    "leather_white": ("diff", "nor_gl", "arm"),
}

# Trim bands, v from 0 at the bottom of the image to 1 at the top.
TRIM = {
    "tread": (0.75, 1.0),
    "nosing": (0.6875, 0.75),
    "riser": (0.4375, 0.6875),
    "padding": (0.3125, 0.4375),
    "steel": (0.1875, 0.3125),
    "soffit": (0.0, 0.1875),
}
# How many yards one full u of each band covers, so a surface textures at
# real-world scale whatever its length.
TRIM_U_YARDS = {"tread": 4.4, "nosing": 4.4, "riser": 4.4, "padding": 3.0, "steel": 3.0, "soffit": 6.0}


def fetch() -> dict:
    """Download the CC0 sources once; return their credits for LICENSES.md."""
    CACHE.mkdir(parents=True, exist_ok=True)
    credits = {}
    for asset, maps in SOURCES.items():
        info_path = CACHE / f"{asset}.info.json"
        if not info_path.exists():
            info_path.write_bytes(_get(f"https://api.polyhaven.com/info/{asset}"))
        info = json.loads(info_path.read_text())
        credits[asset] = {"name": info.get("name", asset), "authors": sorted(info.get("authors", {})),
                          "url": f"https://polyhaven.com/a/{asset}", "license": "CC0 1.0"}
        for m in maps:
            dest = CACHE / f"{asset}_{m}_1k.png"
            if dest.exists():
                continue
            dest.write_bytes(_get(f"https://dl.polyhaven.org/file/ph-assets/Textures/png/1k/{asset}/{asset}_{m}_1k.png"))
    return credits


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "fantasy-edge-bowl-kit/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


# ───────────────────────────── image io ─────────────────────────────

def load(path: pathlib.Path, size: int | None = None) -> np.ndarray:
    img = bpy.data.images.load(str(path))
    img.colorspace_settings.name = "Non-Color"
    if size and (img.size[0] != size or img.size[1] != size):
        img.scale(size, size)
    w, h = img.size
    px = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    return px.reshape(h, w, 4)[:, :, :3].copy()


def save(arr: np.ndarray, name: str, jpeg: bool = False) -> None:
    TEX.mkdir(parents=True, exist_ok=True)
    arr = np.clip(arr, 0.0, 1.0).astype(np.float32)
    h, w = arr.shape[:2]
    rgba = np.ones((h, w, 4), dtype=np.float32)
    rgba[:, :, :3] = arr[:, :, :3] if arr.ndim == 3 else arr[:, :, None]
    img = bpy.data.images.new(name, w, h, alpha=False, float_buffer=False)
    img.colorspace_settings.name = "Non-Color"
    img.pixels.foreach_set(rgba.ravel())
    img.filepath_raw = str(TEX / name)
    img.file_format = "JPEG" if jpeg else "PNG"
    scene = bpy.context.scene
    if jpeg:
        scene.render.image_settings.quality = 88
    img.save()
    bpy.data.images.remove(img)


# ───────────────────────────── noise ─────────────────────────────

def noise(h: int, w: int, cells: int, seed: int) -> np.ndarray:
    """Tileable value noise in 0..1, `cells` lattice cells across the width."""
    rng = np.random.default_rng(seed)
    ch = max(1, round(cells * h / w))
    grid = rng.random((ch, cells)).astype(np.float32)
    y = np.arange(h, dtype=np.float32) / h * ch
    x = np.arange(w, dtype=np.float32) / w * cells
    y0 = np.floor(y).astype(int)
    x0 = np.floor(x).astype(int)
    fy = (y - y0)[:, None]
    fx = (x - x0)[None, :]
    fy = fy * fy * (3 - 2 * fy)
    fx = fx * fx * (3 - 2 * fx)
    y1, x1 = (y0 + 1) % ch, (x0 + 1) % cells
    y0, x0 = y0 % ch, x0 % cells
    a = grid[y0][:, x0]
    b = grid[y0][:, x1]
    c = grid[y1][:, x0]
    d = grid[y1][:, x1]
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


def fbm(h: int, w: int, cells: int, seed: int, octaves: int = 4) -> np.ndarray:
    out = np.zeros((h, w), dtype=np.float32)
    amp, total = 1.0, 0.0
    for o in range(octaves):
        out += noise(h, w, cells * (2 ** o), seed + o * 101) * amp
        total += amp
        amp *= 0.5
    return out / total


def normal_from_height(height: np.ndarray, strength: float) -> np.ndarray:
    """OpenGL-convention (+Y up) tangent normals from a tileable height field."""
    dx = (np.roll(height, -1, axis=1) - np.roll(height, 1, axis=1)) * strength
    dy = (np.roll(height, -1, axis=0) - np.roll(height, 1, axis=0)) * strength
    n = np.stack([-dx, -dy, np.ones_like(height)], axis=-1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    return n * 0.5 + 0.5


def down(arr: np.ndarray, factor: int) -> np.ndarray:
    """Box-filter an image down by an integer factor."""
    h, w = arr.shape[0] // factor, arr.shape[1] // factor
    a = arr[:h * factor, :w * factor]
    return a.reshape(h, factor, w, factor, -1).mean(axis=(1, 3))


def tile_band(src: np.ndarray, width: int, height: int, row_offset: int = 0) -> np.ndarray:
    """Tile a square tileable source across `width`, crop `height` rows."""
    reps = int(np.ceil(width / src.shape[1]))
    wide = np.tile(src, (1, reps, 1))[:, :width]
    rows = np.arange(height) + row_offset
    return wide[rows % src.shape[0]]


# ───────────────────────────── maps ─────────────────────────────

def srgb_to_lin(c):
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def lin_to_srgb(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)


def tint(albedo_srgb: np.ndarray, rgb_srgb, keep: float = 0.0) -> np.ndarray:
    """Multiply in linear light: a scan's detail under a chosen paint colour."""
    lum = srgb_to_lin(albedo_srgb).mean(axis=-1, keepdims=True)
    lum = lum / max(1e-6, float(lum.mean()))
    col = srgb_to_lin(np.array(rgb_srgb, dtype=np.float32))[None, None, :]
    lin = col * (0.55 + 0.45 * lum) * (1 - keep) + srgb_to_lin(albedo_srgb) * keep
    return lin_to_srgb(lin)


def trim_sheet(S: int = 2048) -> None:
    src = {a: {m: load(CACHE / f"{a}_{m}_1k.png", 1024) for m in maps} for a, maps in SOURCES.items()}
    albedo = np.zeros((S, S, 3), np.float32)
    normal = np.zeros((S, S, 3), np.float32)
    orm = np.zeros((S, S, 3), np.float32)

    def band(name):
        v0, v1 = TRIM[name]
        return int(round(v0 * S)), int(round(v1 * S))

    # Tread: worn floor concrete, a touch warmer, with a darker scuffed line
    # where feet go, a third of the way back from the nosing.
    r0, r1 = band("tread")
    h = r1 - r0
    a = tile_band(src["concrete_floor_worn_001"]["diff"], S, h)
    wear = np.exp(-((np.linspace(0, 1, h) - 0.3) / 0.12) ** 2)[:, None, None]
    grime = fbm(h, S, 12, 7)[:, :, None]
    albedo[r0:r1] = a * (0.92 - 0.10 * wear * (0.6 + 0.4 * grime))
    normal[r0:r1] = tile_band(src["concrete_floor_worn_001"]["nor_gl"], S, h)
    o = tile_band(src["concrete_floor_worn_001"]["arm"], S, h)
    o[:, :, 1] = np.clip(o[:, :, 1] - 0.08 * wear[:, :, 0], 0.3, 1.0)
    o[:, :, 2] = 0.0
    orm[r0:r1] = o

    # Nosing: an anti-slip insert, dark and gritty, with a painted safety
    # line along the top edge that is chipped where the tread meets it.
    r0, r1 = band("nosing")
    h = r1 - r0
    grit = fbm(h, S, 180, 11, 2)
    chips = fbm(h, S, 40, 13, 3) > 0.62
    base = np.full((h, S, 3), 0.085, np.float32) + (grit[:, :, None] - 0.5) * 0.05
    top = (np.arange(h) >= int(h * 0.62))[:, None]
    line = np.array([0.74, 0.60, 0.16], np.float32)
    base = np.where((top & ~chips)[:, :, None], line * (0.85 + 0.15 * grit[:, :, None]), base)
    albedo[r0:r1] = base
    normal[r0:r1] = normal_from_height(grit * 0.6 + top * 0.4, 6.0)
    orm[r0:r1] = np.stack([np.full((h, S), 0.95), np.where(top & ~chips, 0.55, 0.9), np.zeros((h, S))], -1)

    # Riser: painted concrete face, rain-streaked darker toward the foot.
    r0, r1 = band("riser")
    h = r1 - r0
    a = tile_band(src["painted_concrete"]["diff"], S, h, 200)
    a = tint(a, (0.47, 0.45, 0.42), keep=0.0)
    streak = fbm(h, S, 90, 21, 2)
    streak = np.clip((streak - 0.35) * 1.8, 0, 1) * np.linspace(0.55, 0.0, h)[:, None]
    foot = np.linspace(0.78, 1.0, h)[:, None, None]
    albedo[r0:r1] = a * foot * (1 - 0.35 * streak[:, :, None])
    normal[r0:r1] = tile_band(src["painted_concrete"]["nor_gl"], S, h, 200)
    o = tile_band(src["painted_concrete"]["arm"], S, h, 200)
    o[:, :, 2] = 0.0
    orm[r0:r1] = o

    # Padding: vinyl-wrapped foam over the wall, dark, panelled every half u.
    r0, r1 = band("padding")
    h = r1 - r0
    a = tile_band(src["leather_white"]["diff"], S, h)
    a = tint(a, (0.07, 0.08, 0.10), keep=0.0)
    seams = np.zeros((h, S), np.float32)
    for k in range(0, S, S // 4):
        seams[:, max(0, k - 3):k + 3] = 1.0
    puff = np.sin(np.linspace(0, np.pi, h))[:, None] * 0.6
    albedo[r0:r1] = a * (1 - 0.5 * seams[:, :, None])
    leather_n = tile_band(src["leather_white"]["nor_gl"], S, h)
    seam_n = normal_from_height(puff - seams * 0.8, 3.0)
    normal[r0:r1] = np.clip((leather_n - 0.5) + (seam_n - 0.5), -0.5, 0.5) + 0.5
    o = tile_band(src["leather_white"]["arm"], S, h)
    o[:, :, 1] = np.clip(o[:, :, 1] * 0.7, 0.25, 0.7)
    o[:, :, 2] = 0.0
    orm[r0:r1] = o

    # Steel: painted structural steel, a cool dark grey over the plate scan.
    r0, r1 = band("steel")
    h = r1 - r0
    a = tile_band(src["metal_plate"]["diff"], S, h)
    albedo[r0:r1] = tint(a, (0.20, 0.22, 0.25), keep=0.15)
    normal[r0:r1] = tile_band(src["metal_plate"]["nor_gl"], S, h)
    o = tile_band(src["metal_plate"]["arm"], S, h)
    o[:, :, 1] = np.clip(o[:, :, 1] * 0.8 + 0.1, 0.3, 0.8)
    o[:, :, 2] = 0.35
    orm[r0:r1] = o

    # Soffit: acoustic ceiling panels on a grid, water-stained here and there.
    r0, r1 = band("soffit")
    h = r1 - r0
    u = np.arange(S)[None, :] % (S // 6)
    v = np.arange(h)[:, None] % (h // 2)
    joint = ((u < 6) | (v < 6)).astype(np.float32)
    stain = np.clip((fbm(h, S, 10, 31) - 0.6) * 2.5, 0, 1)
    speck = fbm(h, S, 400, 33, 1)
    base = 0.50 + 0.04 * speck - 0.12 * stain
    col = np.stack([base, base * 0.98, base * 0.95], -1)
    albedo[r0:r1] = col * (1 - 0.55 * joint[:, :, None])
    normal[r0:r1] = normal_from_height(-joint * 0.7 + speck * 0.1, 4.0)
    orm[r0:r1] = np.stack([1 - 0.3 * joint, np.full((h, S), 0.85), np.zeros((h, S))], -1)

    # Colour carries the detail at 2K; normal and ORM are soft signals and ship
    # at 1K, which is what keeps the bowl inside its 50 MB.
    save(albedo, "bowl_trim_albedo.jpg", jpeg=True)
    n = down(normal, 2) - 0.5
    n /= np.maximum(1e-6, np.linalg.norm(n, axis=-1, keepdims=True))
    save(n * 0.5 + 0.5, "bowl_trim_normal.png")
    save(down(orm, 2), "bowl_trim_orm.png")
    save(down(albedo, 4), "table_trim_albedo.jpg", jpeg=True)


def tileables() -> None:
    # Fascia, walls, vomitory cheeks, exterior: painted concrete, pale, at 512.
    s = {m: load(CACHE / f"painted_concrete_{m}_1k.png", 1024) for m in ("diff", "nor_gl", "arm")}
    save(down(tint(s["diff"], (0.60, 0.59, 0.56), keep=0.0), 2), "concrete_wall_albedo.jpg", jpeg=True)
    save(down(s["nor_gl"], 2), "concrete_wall_normal.png")
    o = down(s["arm"], 2)
    o[:, :, 2] = 0.0
    save(o, "concrete_wall_orm.png")


def stair_sheet() -> None:
    """Aisle stairs up close: tread concrete above, a riser with its anti-slip
    nosing and yellow safety edge below. v 0.4-1.0 is the tread, 0-0.4 the front."""
    W, H = 512, 256
    src = load(CACHE / "concrete_floor_worn_001_diff_1k.png", 1024)
    tread = down(src[:512, :1024], 2)[:int(H * 0.6)]
    grit = fbm(int(H * 0.4), W, 90, 61, 2)
    front = np.full((int(H * 0.4), W, 3), 0.09, np.float32) + (grit[:, :, None] - 0.5) * 0.04
    edge = (np.arange(int(H * 0.4)) >= int(H * 0.4 * 0.72))[:, None]
    chips = fbm(int(H * 0.4), W, 30, 63, 3) > 0.66
    front = np.where((edge & ~chips)[:, :, None], np.array([0.74, 0.60, 0.16]) * (0.85 + 0.15 * grit[:, :, None]), front)
    img = np.concatenate([front, tread * 0.9], axis=0)
    save(img, "stair_albedo.jpg", jpeg=True)


def seat_maps(S: int = 256) -> None:
    """Moulded seat plastic: near-white so a venue colour multiplies cleanly,
    with orange-peel texture and grime pooled at the bottom of the bucket."""
    peel = fbm(S, S, 96, 41, 2)
    grime = np.clip(fbm(S, S, 6, 43) * 1.4 - 0.4, 0, 1)
    v = np.linspace(0, 1, S)[:, None]
    pooled = np.clip(1 - v * 3, 0, 1) * 0.35 + grime * 0.12
    base = 0.93 - pooled
    save(np.stack([base, base, base * 0.99], -1), "seat_plastic_albedo.png")
    save(normal_from_height(peel, 0.6), "seat_plastic_normal.png")
    save(np.stack([1 - pooled * 0.6, 0.66 + 0.08 * peel + pooled * 0.2, np.zeros_like(peel)], -1), "seat_plastic_orm.png")


    # The far-row band: a row of seat backs seen from the field, eight to a
    # tile, grey so the venue colour multiplies, with the dark gap beneath.
    W, H = 1024, 256
    x = (np.arange(W) % (W // 8)) / (W // 8)
    y = np.linspace(0, 1, H)[:, None]
    back = ((x > 0.08) & (x < 0.92))[None, :] & (y > 0.30)
    rounded = np.clip(1 - np.abs(x - 0.5)[None, :] * 2.2, 0, 1) ** 0.3
    pan = (y > 0.18) & (y <= 0.30)
    col = np.where(back, 0.78 * (0.85 + 0.15 * rounded), np.where(pan, 0.55, 0.05))
    save(np.stack([col, col, col], -1), "seat_band_albedo.png")



def interiors() -> None:
    """Emissive interiors glimpsed through glass: suites warm, the press box
    cool with monitors, the concourse a sodium glow. Blocky on purpose - they
    are read through tinted glass from 60 yards."""
    rng = np.random.default_rng(51)
    W, H = 1024, 512
    y = np.linspace(0, 1, H)[:, None]
    warm = np.array([1.0, 0.72, 0.42], np.float32)
    img = (0.10 + 0.55 * np.exp(-((y - 0.85) / 0.25) ** 2))[:, :, None] * warm * np.ones((1, W, 1), np.float32)
    for k in range(0, W, W // 8):                                   # a suite every 128 px
        img[:, k:k + 5] *= 0.25                                     # divider
        tv = slice(int(H * 0.55), int(H * 0.70)), slice(k + 44, k + 84)
        img[tv] = np.array([0.35, 0.55, 0.95]) * (0.7 + 0.3 * rng.random())
        img[int(H * 0.08):int(H * 0.32), k + 12:k + 116] *= 0.35    # counter and chairs
        img[int(H * 0.88):int(H * 0.93), k + 20:k + 108] = warm * 1.0  # cove light
    suites = img

    cool = np.array([0.72, 0.84, 1.0], np.float32)
    img = (0.12 + 0.45 * np.exp(-((y - 0.9) / 0.3) ** 2))[:, :, None] * cool * np.ones((1, W, 1), np.float32)
    for k in range(10, W, 64):
        img[int(H * 0.30):int(H * 0.46), k:k + 40] = np.array([0.2, 0.9, 0.6]) * (0.4 + 0.6 * rng.random())
        img[int(H * 0.10):int(H * 0.28), k - 6:k + 50] *= 0.3
    press = img

    W, H = 512, 256
    x = np.linspace(0, 1, W)[None, :]
    img = (0.25 + 0.75 * np.exp(-((np.linspace(0, 1, H)[:, None] - 0.8) / 0.35) ** 2)
           * (0.7 + 0.3 * np.cos(x * np.pi * 6) ** 2))[:, :, None] * np.array([1.0, 0.68, 0.36])
    glow = img
    # One atlas, one material: suites in the top half (v 0.5-1), the press box
    # below that (v 0.25-0.5), the concourse glow in the bottom quarter.
    atlas = np.zeros((1024, 1024, 3), np.float32)
    atlas[512:1024] = suites
    atlas[256:512] = down(press, 2).repeat(2, axis=1)
    atlas[0:256] = np.tile(glow, (1, 2, 1))[:256, :1024]
    save(atlas, "interiors_emission.jpg", jpeg=True)


def build() -> dict:
    credits = fetch()
    trim_sheet()
    tileables()
    stair_sheet()
    seat_maps()
    interiors()
    return credits
