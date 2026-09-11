"""Draw the app icon, rather than storing it.

This repository keeps no binary assets, and an icon is the usual reason a
project starts. So it is generated: a script that draws it is reviewable in a
diff, regenerable at any size, and cannot drift from the palette the rest of
the product uses - which a PNG dropped in from a design tool always eventually
does.

PNG is written with `zlib` and `struct`, which is all a PNG is. No Pillow.

visionOS wants a *layered* icon - back, middle and front, each 1024x1024 -
which the system parallaxes as the wearer moves. That is a real constraint on
the design rather than a packaging detail: the layers have to mean something
in depth. Here the turf is behind, its lines sit in the middle, and the ball
stands in front, so the field recedes and the ball follows you. A flat badge
copied into three layers would look broken in exactly the way this format
exists to avoid.

    python3 tools/make_icon.py            # writes apple/FantasyEdge/Assets.xcassets
    python3 tools/make_icon.py --out DIR  # somewhere else, to inspect first
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import struct
import zlib

SIDE = 1024

# The product's own palette, not a new one. Green is the same grass green the
# board uses for anything you can act on; navy is the ground it sits on.
GREEN = (0x5B, 0xC2, 0x36)
TURF_DARK = (0x1E, 0x5B, 0x2A)
TURF_LIGHT = (0x27, 0x6E, 0x33)
NAVY = (0x0A, 0x1A, 0x5F)
CHALK = (0xF2, 0xF6, 0xF0)
LEATHER = (0x7A, 0x3B, 0x1D)
LEATHER_HI = (0x9A, 0x50, 0x28)


def _chunk(tag: bytes, data: bytes) -> bytes:
    return (struct.pack(">I", len(data)) + tag + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))


def write_png(path: pathlib.Path, pixels: list[bytearray]) -> None:
    """RGBA rows out to a file. Filter type 0 on every row - the images here
    are smooth gradients and flat fills, where a cleverer filter buys little
    and costs the ability to read this function."""
    raw = b"".join(b"\x00" + bytes(row) for row in pixels)
    png = (b"\x89PNG\r\n\x1a\n"
           + _chunk(b"IHDR", struct.pack(">IIBBBBB", SIDE, SIDE, 8, 6, 0, 0, 0))
           + _chunk(b"IDAT", zlib.compress(raw, 9))
           + _chunk(b"IEND", b""))
    path.write_bytes(png)


def blank(rgba=(0, 0, 0, 0)) -> list[bytearray]:
    row = bytearray(bytes(rgba) * SIDE)
    return [bytearray(row) for _ in range(SIDE)]


def put(rows, x: int, y: int, rgb, a: int = 255) -> None:
    if not (0 <= x < SIDE and 0 <= y < SIDE):
        return
    i = x * 4
    row = rows[y]
    if a >= 255:
        row[i:i + 4] = bytes((*rgb, 255))
        return
    # Source-over onto whatever is already there, so the ball's shading can be
    # laid down in passes instead of solved in one expression.
    inv = 255 - a
    for k in range(3):
        row[i + k] = (rgb[k] * a + row[i + k] * inv) // 255
    row[i + 3] = min(255, row[i + 3] + a)


def turf() -> list[bytearray]:
    """The ground: mown stripes, the way a groundsman cuts them."""
    rows = blank((*TURF_DARK, 255))
    band = SIDE // 8
    for y in range(SIDE):
        for x in range(SIDE):
            light = ((x // band) % 2) == 0
            base = TURF_LIGHT if light else TURF_DARK
            # A soft vignette so the layer reads as a surface under light
            # rather than as flat paper.
            dx, dy = (x - SIDE / 2) / (SIDE / 2), (y - SIDE / 2) / (SIDE / 2)
            fall = max(0.0, 1.0 - 0.35 * (dx * dx + dy * dy))
            put(rows, x, y, tuple(int(c * fall) for c in base))
    return rows


def lines() -> list[bytearray]:
    """Yard lines and hashes. Middle layer, so they float just off the turf."""
    rows = blank()
    for i in range(1, 8):
        x = SIDE * i // 8
        for dx in range(-3, 4):
            for y in range(SIDE):
                put(rows, x + dx, y, CHALK, 150 if abs(dx) < 2 else 60)
    # Hash marks, two rows of them, the short ticks between the yard lines.
    for i in range(1, 40):
        x = SIDE * i // 40
        if x % (SIDE // 8) == 0:
            continue
        for y0 in (SIDE * 3 // 8, SIDE * 5 // 8):
            for y in range(y0 - 12, y0 + 12):
                for dx in (-1, 0, 1):
                    put(rows, x + dx, y, CHALK, 90)
    return rows


def ball() -> list[bytearray]:
    """The front layer. A prolate spheroid with laces, drawn as an implicit
    shape and shaded by height, which keeps it smooth at any size."""
    rows = blank()
    cx, cy = SIDE / 2, SIDE / 2
    rx, ry = SIDE * 0.365, SIDE * 0.232
    tilt = math.radians(-22)
    cos_t, sin_t = math.cos(tilt), math.sin(tilt)
    for y in range(SIDE):
        for x in range(SIDE):
            px, py = x - cx, y - cy
            u = (px * cos_t + py * sin_t) / rx
            v = (-px * sin_t + py * cos_t) / ry
            d = u * u + v * v
            if d > 1.0:
                continue
            # Height above the silhouette, used both for shading and for the
            # rim, so the edge darkens the way a real ball's does.
            h = math.sqrt(max(0.0, 1.0 - d))
            lit = 0.55 + 0.55 * h - 0.30 * v
            base = LEATHER_HI if v < -0.25 else LEATHER
            col = tuple(min(255, int(c * lit)) for c in base)
            edge = 255 if d < 0.93 else int(255 * (1.0 - d) / 0.07)
            put(rows, x, y, col, max(0, min(255, edge)))
            # The white stripe near each end. It has to *bend*: a line of
            # constant u is a straight line in image space, which reads as a
            # bar laid across the ball rather than a band wrapped round it.
            # Bowing it outward with v^2 puts it on the surface, and fading it
            # as the surface turns away finishes the job.
            bow = 0.655 + 0.085 * v * v
            if abs(abs(u) - bow) < 0.032 and abs(v) < 0.80:
                put(rows, x, y, CHALK, int(235 * max(0.25, h)))
            if abs(v) < 0.055 and abs(u) < 0.34:
                put(rows, x, y, CHALK, 235)
            if abs(v) < 0.26 and abs(u) < 0.30:
                # cross-stitches: eight ticks along the seam
                if abs(math.sin(u * 26.0)) > 0.93:
                    put(rows, x, y, CHALK, 235)
    return rows


LAYERS = {"Back": turf, "Middle": lines, "Front": ball}


def contents(**extra) -> str:
    d = {"info": {"author": "fantasy-edge", "version": 1}}
    d.update(extra)
    return json.dumps(d, indent=2) + "\n"


def build(out: pathlib.Path) -> None:
    stack = out / "AppIcon.solidimagestack"
    stack.mkdir(parents=True, exist_ok=True)
    (out / "Contents.json").write_text(contents())
    (stack / "Contents.json").write_text(contents(
        layers=[{"filename": f"{n}.solidimagestacklayer"}
                for n in reversed(list(LAYERS))]))
    for name, draw in LAYERS.items():
        layer = stack / f"{name}.solidimagestacklayer"
        img = layer / "Content.imageset"
        img.mkdir(parents=True, exist_ok=True)
        (layer / "Contents.json").write_text(contents())
        (img / "Contents.json").write_text(contents(
            images=[{"filename": f"{name}.png", "idiom": "vision", "scale": "2x"}]))
        write_png(img / f"{name}.png", draw())
        print(f"  {name:7} {(img / f'{name}.png').stat().st_size // 1024:>4} KB")
    print(f"  wrote {stack}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="apple/FantasyEdge/Assets.xcassets")
    build(pathlib.Path(ap.parse_args().out))
