"""The Broadcast actor's light textures: trails, broadcast lines, the horizon marker.

    python3 tools/blender/broadcast/textures.py

Standard library only (it needs no Blender), deterministic, and driven by
design/tokens.json `visual.broadcast`, so the shape of a trail's fade lives in
the tokens and every client loads the same PNGs from assets/actors/broadcast/.

  trail_core.png   the bright filament of a flight trail: u along the play
                   (0 at the snap, 1 where it ended), v across its width
  trail_halo.png   the soft glow round it, same axes, a wide gaussian
  line.png         a TV first-down line on grass: u tiles along the line,
                   v crosses it with a feathered edge and grass breaking it up
  marker.png       the glowing "now" point on the win-probability horizon
"""
from __future__ import annotations

import json
import math
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))

from make_assets import write_png  # noqa: E402

OUT = ROOT / "assets" / "actors" / "broadcast"


def clamp8(v: float) -> int:
    return max(0, min(255, int(round(v * 255))))


def hash01(x: int, y: int, seed: int) -> float:
    """A repeatable value in 0..1 per integer lattice point."""
    n = (x * 374761393 + y * 668265263 + seed * 1442695041) & 0xFFFFFFFF
    n = (n ^ (n >> 13)) * 1274126177 & 0xFFFFFFFF
    return ((n ^ (n >> 16)) & 0xFFFF) / 0xFFFF


def along(u: float, tail: dict) -> float:
    """How bright a trail is at u: faint at the snap, full where the ball is."""
    return tail["opacity"] + (1 - tail["opacity"]) * u ** tail["power"]


def trail(path: pathlib.Path, w: int, h: int, tail: dict, sharpness: float, gauss: bool) -> None:
    rows = []
    for y in range(h):
        c = (y + 0.5) / h * 2 - 1           # -1..1 across
        if gauss:
            across = math.exp(-c * c * sharpness)
        else:
            # A filament: flat-topped with an anti-aliased shoulder.
            across = max(0.0, 1 - abs(c) ** sharpness)
        row = bytearray()
        for x in range(w):
            u = x / (w - 1)
            # The last few percent round off, so the head is not a hard cut.
            head = min(1.0, (1 - u) / 0.03 + 0.35)
            row += bytes((255, 255, 255, clamp8(along(u, tail) * across * head)))
        rows.append(bytes(row))
    write_png(path, w, h, rows, 4)


def line(path: pathlib.Path, rule: dict) -> None:
    """Opaque in the middle, a soft shoulder at each edge, and blades of grass
    standing through it, so it sits in the turf rather than on a sheet above."""
    w, h = 256, 64
    feather = rule["feather"]
    grass = rule["grass"]
    rows = []
    for y in range(h):
        v = (y + 0.5) / h
        edge = min(v, 1 - v) / max(1e-6, feather)
        body = min(1.0, edge) ** 1.3
        row = bytearray()
        for x in range(w):
            # Blades: thin vertical streaks of varying strength, tiling in u.
            blade = hash01(x, y // 6, 7) * 0.6 + hash01(x, 0, 11) * 0.4
            occl = grass * max(0.0, blade - 0.55) / 0.45
            row += bytes((255, 255, 255, clamp8(body * (1 - occl))))
        rows.append(bytes(row))
    write_png(path, w, h, rows, 4)


def marker(path: pathlib.Path) -> None:
    n = 128
    rows = []
    for y in range(n):
        row = bytearray()
        for x in range(n):
            dx, dy = (x + 0.5) / n * 2 - 1, (y + 0.5) / n * 2 - 1
            r = math.hypot(dx, dy)
            core = max(0.0, 1 - r / 0.16) ** 1.5
            halo = math.exp(-r * r * 7.5) * 0.55
            row += bytes((255, 255, 255, clamp8(min(1.0, core + halo) * (1 if r < 1 else 0))))
        rows.append(bytes(row))
    write_png(path, n, n, rows, 4)


def main() -> None:
    tokens = json.loads((ROOT / "design" / "tokens.json").read_text())
    b = tokens["visual"]["broadcast"]
    tail = b["trail"]["tail"]
    trail(OUT / "trail_core.png", 512, 32, tail, sharpness=4.0, gauss=False)
    trail(OUT / "trail_halo.png", 512, 64, tail, sharpness=4.5, gauss=True)
    line(OUT / "line.png", b["laser"]["texture"])
    marker(OUT / "marker.png")
    print("wrote", ", ".join(p.name for p in sorted(OUT.glob("*.png"))))


if __name__ == "__main__":
    main()
