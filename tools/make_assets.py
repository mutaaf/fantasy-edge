"""Write the stadium's source assets: textures, a light probe, and sound.

Every file under assets/src is made here, from nothing but the standard
library, so the look has no licence to track and no download to go stale, and
a web or Android renderer loads exactly the same bytes the headset does:

  textures/*.png    8-bit RGBA or grey PNG, tileable where the name says so
  env/*.hdr         Radiance RGBE, the night light probe for image-based light
  audio/*.wav       16-bit mono PCM, 24 kHz

Deterministic: a second run writes identical files.

    python3 tools/make_assets.py            # all of it
    python3 tools/make_assets.py turf sky   # just those groups
"""

from __future__ import annotations

import math
import random
import struct
import sys
import wave
import zlib
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "src"


# ───────────────────────────── writers ─────────────────────────────

def write_png(path: pathlib.Path, width: int, height: int, rows: list[bytes], channels: int) -> None:
    """rows: one bytes object per scanline, `channels` bytes per pixel."""
    colour = {1: 0, 3: 2, 4: 6}[channels]
    raw = b"".join(b"\x00" + r for r in rows)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x89PNG\r\n\x1a\n"
                     + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, colour, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(raw, 9))
                     + chunk(b"IEND", b""))


def write_hdr(path: pathlib.Path, width: int, height: int, pixel) -> None:
    """Radiance .hdr, uncompressed RGBE scanlines. pixel(x, y) -> (r, g, b) linear."""
    out = bytearray(f"#?RADIANCE\nFORMAT=32-bit_rle_rgbe\n\n-Y {height} +X {width}\n".encode())
    for y in range(height):
        for x in range(width):
            r, g, b = pixel(x, y)
            v = max(r, g, b)
            if v < 1e-32:
                out += b"\x00\x00\x00\x00"
            else:
                m, e = math.frexp(v)
                s = m * 256.0 / v
                out += bytes((int(r * s), int(g * s), int(b * s), e + 128))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(out))


def write_wav(path: pathlib.Path, samples: list[float], rate: int = 24000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    peak = max(1e-9, max(abs(s) for s in samples))
    gain = 0.89 / peak
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"".join(struct.pack("<h", int(max(-1, min(1, s * gain)) * 32767)) for s in samples))


# ───────────────────────────── noise ─────────────────────────────

class Noise:
    """Tileable value noise on a lattice of `period` cells."""

    def __init__(self, seed: int, period: int):
        rng = random.Random(seed)
        self.p = period
        self.v = [rng.random() for _ in range(period * period)]

    def at(self, x: float, y: float) -> float:
        p = self.p
        xi, yi = int(math.floor(x)), int(math.floor(y))
        fx, fy = x - xi, y - yi
        sx, sy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)
        x0, x1, y0, y1 = xi % p, (xi + 1) % p, yi % p, (yi + 1) % p
        v = self.v
        a = v[y0 * p + x0] + (v[y0 * p + x1] - v[y0 * p + x0]) * sx
        b = v[y1 * p + x0] + (v[y1 * p + x1] - v[y1 * p + x0]) * sx
        return a + (b - a) * sy


def fbm(layers: list[Noise], u: float, v: float, weights: list[float]) -> float:
    total = 0.0
    for n, w in zip(layers, weights):
        total += n.at(u * n.p, v * n.p) * w
    return total / sum(weights)


def clamp8(x: float) -> int:
    return max(0, min(255, int(round(x * 255))))


def srgb(c: float) -> float:
    c = max(0.0, c)
    return c * 12.92 if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


# ───────────────────────────── turf ─────────────────────────────

def turf() -> None:
    """Mowed natural grass, tileable over 4 yards. Albedo, normal, roughness.

    Blades are short streaks along v (the direction of the mowing), so the
    stripe a renderer tints reads as grass laid one way and then the other.
    """
    size = 1024
    cells = [Noise(11, 8), Noise(12, 32), Noise(13, 128)]
    blades = [Noise(21 + k, 256) for k in range(2)]
    height = [[0.0] * size for _ in range(size)]
    albedo_rows, rough_rows = [], []
    for y in range(size):
        row, rrow = bytearray(), bytearray()
        v = y / size
        for x in range(size):
            u = x / size
            patch = fbm(cells, u, v, [0.5, 0.3, 0.2])
            # Streaks: squash the blade lattice along v so each blade is taller than wide.
            b = blades[0].at(u * 256, v * 256 / 5) * 0.6 + blades[1].at(u * 256 * 1.7, v * 256 / 3) * 0.4
            blade = max(0.0, (b - 0.35) / 0.65) ** 1.4
            h = blade * 0.8 + patch * 0.2
            height[y][x] = h
            shade = 0.72 + 0.28 * blade
            tint = patch - 0.5
            r = (0.070 + 0.030 * tint) * shade
            g = (0.165 + 0.040 * tint + 0.030 * blade) * shade
            bl = (0.045 + 0.012 * tint) * shade
            # the odd dry tip
            if blade > 0.92:
                r, g, bl = r * 1.35 + 0.02, g * 1.1, bl
            row += bytes((clamp8(srgb(r)), clamp8(srgb(g)), clamp8(srgb(bl)), 255))
            rrow.append(clamp8(0.78 + 0.16 * (1 - blade) - 0.05 * patch))
        albedo_rows.append(bytes(row))
        rough_rows.append(bytes(rrow))
    normal_rows = []
    strength = 6.0
    for y in range(size):
        row = bytearray()
        for x in range(size):
            dx = (height[y][(x + 1) % size] - height[y][(x - 1) % size]) * strength
            dy = (height[(y + 1) % size][x] - height[(y - 1) % size][x]) * strength
            nx, ny, nz = -dx, -dy, 1.0
            ln = math.sqrt(nx * nx + ny * ny + nz * nz)
            row += bytes((clamp8(nx / ln * 0.5 + 0.5), clamp8(ny / ln * 0.5 + 0.5), clamp8(nz / ln * 0.5 + 0.5), 255))
        normal_rows.append(bytes(row))
    write_png(OUT / "textures/turf_albedo.png", size, size, albedo_rows, 4)
    write_png(OUT / "textures/turf_normal.png", size, size, normal_rows, 4)
    write_png(OUT / "textures/turf_roughness.png", size, size, rough_rows, 1)


def paint() -> None:
    """Field paint over grass: mostly opaque, with blades showing through and
    the edge a little ragged. Tileable along u. Alpha only matters."""
    w, h = 512, 64
    speck = Noise(31, 128)
    edge = Noise(32, 32)
    rows = []
    for y in range(h):
        row = bytearray()
        v = y / (h - 1)
        for x in range(w):
            u = x / w
            s = speck.at(u * 128, v * 128 * (h / w) * 8)
            e = edge.at(u * 32, 0.5)
            margin = 0.10 + 0.05 * e
            inside = min(v, 1 - v)
            soft = max(0.0, min(1.0, (inside - margin * 0.5) / (margin * 0.5)))
            holes = 1.0 if s > 0.23 else 0.35
            a = soft * holes * (0.92 - 0.1 * speck.at(u * 16, 0.3))
            row += bytes((255, 255, 255, clamp8(a)))
        rows.append(bytes(row))
    write_png(OUT / "textures/paint_mask.png", w, h, rows, 4)


# ───────────────────────────── light ─────────────────────────────

def glows() -> None:
    """Soft sprites for things that should read as light: a lamp's bloom, a
    beam, a trail, a haze cone. White with alpha; the renderer tints."""
    s = 256
    rows = []
    for y in range(s):
        row = bytearray()
        for x in range(s):
            dx, dy = (x + 0.5) / s * 2 - 1, (y + 0.5) / s * 2 - 1
            r2 = dx * dx + dy * dy
            a = math.exp(-r2 * 5.5) * 0.85 + math.exp(-r2 * 42) * 0.15
            a *= max(0.0, 1 - r2)
            row += bytes((255, 255, 255, clamp8(a)))
        rows.append(bytes(row))
    write_png(OUT / "textures/glow.png", s, s, rows, 4)

    w, h = 64, 512
    rows = []
    for y in range(h):
        row = bytearray()
        t = y / (h - 1)                      # 0 at the top of the image
        along = (1 - t) ** 0.0 * (t ** 1.6)  # brightest at the bottom, gone at the top
        for x in range(w):
            c = (x + 0.5) / w * 2 - 1
            across = math.exp(-c * c * 9)
            row += bytes((255, 255, 255, clamp8(along * across)))
        rows.append(bytes(row))
    write_png(OUT / "textures/beam.png", w, h, rows, 4)

    w, h = 512, 16
    rows = []
    for y in range(h):
        row = bytearray()
        for x in range(w):
            t = x / (w - 1)                  # 0 at the snap, 1 where the play ended
            a = 0.18 + 0.82 * t ** 1.8
            row += bytes((255, 255, 255, clamp8(a)))
        rows.append(bytes(row))
    write_png(OUT / "textures/trail.png", w, h, rows, 4)

    w, h = 128, 512
    rows = []
    for y in range(h):
        row = bytearray()
        t = y / (h - 1)                      # 0 at the lamp, 1 at the far end
        for x in range(w):
            a = (1 - t) ** 2.2 * 0.55
            row += bytes((255, 255, 255, clamp8(a)))
        rows.append(bytes(row))
    write_png(OUT / "textures/haze.png", w, h, rows, 4)


def lamp_face() -> None:
    """A light bank seen from the stands: a grid of lamps in a dark frame."""
    w, h = 512, 192
    rows = []
    cols, lines = 12, 4
    for y in range(h):
        row = bytearray()
        for x in range(w):
            cx = (x % (w / cols)) / (w / cols) * 2 - 1
            cy = (y % (h / lines)) / (h / lines) * 2 - 1
            r2 = cx * cx + cy * cy
            lamp = math.exp(-r2 * 3.2)
            frame = 0.06
            v = frame + (1 - frame) * lamp
            row += bytes((clamp8(v), clamp8(v * 0.97), clamp8(v * 0.9), 255))
        rows.append(bytes(row))
    write_png(OUT / "textures/lamp_face.png", w, h, rows, 4)


# ───────────────────────────── the bowl ─────────────────────────────

def seats() -> None:
    """One yard of stepped seating, tileable both ways: a concrete tread with a
    row of seat backs along its rear edge. u runs around the bowl, v up a row."""
    w, h = 256, 128
    grit = Noise(41, 64)
    rows = []
    for y in range(h):
        row = bytearray()
        v = y / h
        for x in range(w):
            u = x / w
            g = grit.at(u * 64, v * 32)
            base = 0.20 + 0.06 * g
            r, gg, b = base, base * 0.98, base * 0.95
            seat_phase = (u * 8) % 1.0
            if v > 0.55 and 0.12 < seat_phase < 0.88:
                back = 0.10 + 0.03 * g
                r, gg, b = back, back, back * 1.05
                if v > 0.9:
                    r, gg, b = r * 0.6, gg * 0.6, b * 0.6
            if v < 0.04:
                r, gg, b = r * 1.4, gg * 1.4, b * 1.4
            row += bytes((clamp8(srgb(r * 0.5)), clamp8(srgb(gg * 0.5)), clamp8(srgb(b * 0.5)), 255))
        rows.append(bytes(row))
    write_png(OUT / "textures/seats.png", w, h, rows, 4)

    s = 512
    rows = []
    stain = [Noise(51, 16), Noise(52, 64), Noise(53, 256)]
    for y in range(s):
        row = bytearray()
        for x in range(s):
            n = fbm(stain, x / s, y / s, [0.5, 0.3, 0.2])
            c = 0.30 + 0.12 * (n - 0.5)
            row += bytes((clamp8(srgb(c * 0.55)), clamp8(srgb(c * 0.54)), clamp8(srgb(c * 0.52)), 255))
        rows.append(bytes(row))
    write_png(OUT / "textures/concrete.png", s, s, rows, 4)


def crowd_atlas() -> None:
    """Fans, as masks: 16 x 8 figures in 64 x 128 cells.

    R is shirt, G is skin, B is hair or a cap, A is coverage. A renderer mixes
    its own colours per channel, so one atlas dresses any two clubs. Row 0-3
    sit or stand; rows 4-7 have their arms up, which is what a surge swaps to.
    """
    cw, ch, cols, rws = 64, 128, 16, 8
    W, H = cw * cols, ch * rws
    img = [[(0, 0, 0, 0)] * W for _ in range(H)]
    rng = random.Random(61)

    def put(px, py, r, g, b):
        if 0 <= px < W and 0 <= py < H:
            img[py][px] = (r, g, b, 255)

    for ry in range(rws):
        for cx in range(cols):
            ox, oy = cx * cw, ry * ch
            arms_up = ry >= 4
            head_r = rng.uniform(7.5, 9.5)
            hx = cw / 2 + rng.uniform(-3, 3)
            hy = 30 + rng.uniform(-3, 4)
            shoulders = rng.uniform(19, 25)
            waist = shoulders * rng.uniform(0.78, 0.95)
            torso_top, torso_bot = hy + head_r + 3, 124
            cap = rng.random() < 0.3
            hair = rng.random() < 0.7
            for py in range(ch):
                for px in range(cw):
                    X, Y = px + 0.5, py + 0.5
                    # head
                    if (X - hx) ** 2 + (Y - hy) ** 2 <= head_r ** 2:
                        top = Y < hy - head_r * 0.25
                        if cap and Y < hy - head_r * 0.1:
                            put(ox + px, oy + py, 0, 0, 255)
                        elif hair and top:
                            put(ox + px, oy + py, 0, 0, 255)
                        else:
                            put(ox + px, oy + py, 0, 255, 0)
                        continue
                    # neck
                    if abs(X - hx) < 3.5 and hy + head_r - 2 <= Y <= torso_top + 1:
                        put(ox + px, oy + py, 0, 255, 0)
                        continue
                    # torso, a rounded trapezoid
                    if torso_top <= Y <= torso_bot:
                        t = (Y - torso_top) / (torso_bot - torso_top)
                        half = shoulders + (waist - shoulders) * t
                        if t < 0.12:
                            half *= 0.75 + 0.25 * (t / 0.12)
                        if abs(X - cw / 2) <= half:
                            put(ox + px, oy + py, 255, 0, 0)
                            continue
                    # arms raised: two slanted bars with hands
                    if arms_up:
                        for side in (-1, 1):
                            sx = cw / 2 + side * (shoulders - 3)
                            ex = sx + side * rng.uniform(4, 7) if False else sx + side * 6
                            if torso_top - 44 <= Y <= torso_top + 6:
                                f = (torso_top + 6 - Y) / 50
                                axx = sx + (ex - sx) * f
                                if abs(X - axx) < 4.2:
                                    colour = (0, 255, 0) if Y < torso_top - 36 else (255, 0, 0)
                                    put(ox + px, oy + py, *colour)
    rows = [bytes(v for p in line for v in p) for line in img]
    write_png(OUT / "textures/crowd_atlas.png", W, H, rows, 4)


# ───────────────────────────── sky and probe ─────────────────────────────

def sky() -> None:
    """The night over an open bowl, as an equirectangular image.

    Deep blue at the zenith, a warm sodium dome near the horizon where the
    stadium's own light hangs in the air, and stars that thin out into it.
    """
    W, H = 2048, 1024
    rng = random.Random(71)
    haze = Noise(72, 16)
    stars = {}
    for _ in range(2600):
        x, y = rng.randrange(W), rng.randrange(H // 2)
        elevation = (0.5 - y / H) * math.pi
        if rng.random() > math.sin(max(0.0, elevation)) ** 0.6:
            continue
        stars[(x, y)] = rng.uniform(0.25, 1.0) ** 2.5
    rows = []
    for y in range(H):
        row = bytearray()
        el = (0.5 - (y + 0.5) / H) * math.pi          # +pi/2 zenith, -pi/2 nadir
        for x in range(W):
            if el < -0.05:
                r, g, b = 0.006, 0.006, 0.008
            else:
                t = min(1.0, el / (math.pi / 2))
                zen = (0.004, 0.008, 0.022)
                hor = (0.050, 0.046, 0.050)
                k = (1 - t) ** 3.5
                r = zen[0] + (hor[0] - zen[0]) * k
                g = zen[1] + (hor[1] - zen[1]) * k
                b = zen[2] + (hor[2] - zen[2]) * k
                glow = math.exp(-el * 9) * (0.6 + 0.4 * haze.at(x / W * 16, 3.3))
                r += 0.075 * glow
                g += 0.052 * glow
                b += 0.030 * glow
                s = stars.get((x, y))
                if s:
                    r, g, b = r + 0.8 * s, g + 0.8 * s, b + 0.9 * s
            row += bytes((clamp8(srgb(r)), clamp8(srgb(g)), clamp8(srgb(b)), 255))
        rows.append(bytes(row))
    write_png(OUT / "textures/sky_night.png", W, H, rows, 4)


def probe() -> None:
    """Image-based light for a floodlit bowl at night, in linear radiance.

    What a football sitting on the fifty would see: a dark sky, a ring of
    very bright light banks around the rim, the warm glow of lit stands below
    them and green bounce off the field. Specular highlights on a helmet-gloss
    ball and the bench roofs come from those banks.
    """
    W, H = 512, 256
    banks = 10

    def pixel(x, y):
        az = (x + 0.5) / W * 2 * math.pi
        el = (0.5 - (y + 0.5) / H) * math.pi
        if el > 0.62:                                   # open sky
            k = (el - 0.62) / (math.pi / 2 - 0.62)
            return (0.010 * (1 - k) + 0.004 * k, 0.012 * (1 - k) + 0.006 * k, 0.020)
        if el > 0.28:                                   # the rim and its lights
            ring = 0.012
            d_el = (el - 0.45) / 0.07
            phase = (az / (2 * math.pi) * banks) % 1.0
            d_az = (phase - 0.5) / 0.12
            lamp = math.exp(-(d_el * d_el + d_az * d_az)) * 55.0
            return (ring + lamp, ring + lamp * 0.95, ring * 1.2 + lamp * 0.82)
        if el > -0.35:                                  # stands, lit
            return (0.085, 0.066, 0.052)
        return (0.030, 0.070, 0.030)                    # the field

    write_hdr(OUT / "env/stadium_night.hdr", W, H, pixel)


def football() -> None:
    """Pebbled leather with laces and seams, wrapped u around the ball's long
    axis, v from tip to tip."""
    w, h = 512, 256
    pebble = Noise(81, 128)
    rows = []
    for y in range(h):
        row = bytearray()
        v = y / h
        for x in range(w):
            u = x / w
            p = pebble.at(u * 128, v * 64)
            c = 0.62 + 0.25 * p
            r, g, b = 0.36 * c, 0.15 * c, 0.07 * c
            # the two seams
            if min(abs(u - 0.25), abs(u - 0.75)) < 0.004:
                r, g, b = r * 0.5, g * 0.5, b * 0.5
            # laces on one panel, the middle third of its length
            if abs(u - 0.5) < 0.035 and 0.33 < v < 0.67:
                if abs(u - 0.5) < 0.006 or ((v * 60) % 1.0) < 0.35:
                    r, g, b = 0.92, 0.90, 0.86
            row += bytes((clamp8(srgb(r)), clamp8(srgb(g)), clamp8(srgb(b)), 255))
        rows.append(bytes(row))
    write_png(OUT / "textures/football.png", w, h, rows, 4)


# ───────────────────────────── sound ─────────────────────────────

RATE = 24000


class Filter:
    def __init__(self, cutoff: float):
        self.a = math.exp(-2 * math.pi * cutoff / RATE)
        self.y = 0.0

    def __call__(self, x: float) -> float:
        self.y = (1 - self.a) * x + self.a * self.y
        return self.y


def crowd_bed() -> None:
    """Twelve seconds of a full stadium between plays, loopable.

    Many voices are close to noise, band-limited: a low rumble, a mid murmur
    that swells and ebbs, and scattered claps and shouts. The last second is
    crossfaded into the first so the loop has no seam.
    """
    rng = random.Random(91)
    n = RATE * 12
    rumble, murmur, hiss = Filter(160), Filter(900), Filter(3200)
    out = []
    for i in range(n):
        t = i / RATE
        noise = rng.uniform(-1, 1)
        swell = 0.75 + 0.25 * math.sin(2 * math.pi * t / 6.0) + 0.1 * math.sin(2 * math.pi * t / 1.7)
        s = rumble(noise) * 1.8 + (murmur(noise) - rumble.y) * 1.1 * swell + (hiss(noise) - murmur.y) * 0.12
        out.append(s)
    for _ in range(60):                                  # claps and shouts
        start = rng.randrange(n - RATE // 2)
        length = rng.randrange(RATE // 60, RATE // 12)
        amp = rng.uniform(0.2, 0.6)
        band = Filter(rng.uniform(800, 2400))
        for k in range(length):
            env = (1 - k / length) ** 2
            out[start + k] += band(rng.uniform(-1, 1)) * amp * env
    fade = RATE
    for k in range(fade):
        w = k / fade
        out[k] = out[k] * w + out[n - fade + k] * (1 - w)
    write_wav(OUT / "audio/crowd_bed.wav", out[: n - fade], RATE)


def roar() -> None:
    """A touchdown: the whole section at once, rising in a third of a second
    and tailing off over four."""
    rng = random.Random(92)
    n = RATE * 5
    low, mid = Filter(220), Filter(1400)
    out = []
    for i in range(n):
        t = i / RATE
        env = min(1.0, t / 0.35) * math.exp(-max(0.0, t - 0.6) / 1.6)
        noise = rng.uniform(-1, 1)
        s = (low(noise) * 2.2 + (mid(noise) - low.y) * 1.4) * env
        s += 0.08 * math.sin(2 * math.pi * 92 * t) * env
        out.append(s)
    write_wav(OUT / "audio/roar.wav", out, RATE)


def groan() -> None:
    """A turnover from the other side's point of view: a falling, muffled sigh."""
    rng = random.Random(93)
    n = int(RATE * 2.6)
    out = []
    f = Filter(700)
    for i in range(n):
        t = i / RATE
        f.a = math.exp(-2 * math.pi * (900 - 600 * t / 2.6) / RATE)
        env = min(1.0, t / 0.25) * math.exp(-t / 1.2)
        out.append(f(rng.uniform(-1, 1)) * env * 1.8)
    write_wav(OUT / "audio/groan.wav", out, RATE)


def chime() -> None:
    """The stadium's PA chime: two soft bell tones."""
    n = int(RATE * 2.2)
    out = [0.0] * n
    for start, freq in ((0.0, 659.25), (0.28, 987.77)):
        s0 = int(start * RATE)
        for i in range(s0, n):
            t = (i - s0) / RATE
            env = math.exp(-t * 2.4) * min(1.0, t / 0.01)
            out[i] += (math.sin(2 * math.pi * freq * t) + 0.3 * math.sin(2 * math.pi * freq * 2.01 * t)) * env * 0.5
    write_wav(OUT / "audio/chime.wav", out, RATE)


GROUPS = {
    "turf": [turf, paint],
    "light": [glows, lamp_face],
    "bowl": [seats, crowd_atlas],
    "sky": [sky, probe],
    "ball": [football],
    "audio": [crowd_bed, roar, groan, chime],
}


def main(argv: list[str]) -> None:
    wanted = argv or list(GROUPS)
    for name in wanted:
        for fn in GROUPS[name]:
            fn()
            print(f"  {name}: {fn.__name__}")
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main(sys.argv[1:])
