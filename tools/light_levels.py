"""What a frame's light actually measures: value structure, and pool edges.

The art bible asks for a value structure - "the field is the brightest thing
in the bowl. The stands sit a stop darker, the sky two" - and nobody had ever
measured it. It also lists a hard diagonal edge on the far turf that survived
three checkpoints, which is the kind of fault a scanline finds and an eye
argues about.

    python3 tools/light_levels.py shot.png --bands      # field / stands / sky
    python3 tools/light_levels.py shot.png --edges      # steps down the field

`--bands` reports mean relative luminance per band and the stops between them,
against the art bible's 1 stop and 2 stops. Bands are found by brightness and
position, the way tools/crowd_pixels.py finds its stands, not by hand-drawn
masks, so the same call works on any wide frame the harness shoots.

`--edges` walks columns down the field and reports the biggest row-to-row step
in each: a floodlight's terminator shows up as a step an order larger than the
mowing stripe's, at the same row across many columns. Stripes run along the
field, so a stripe boundary moves with the column and a light edge does not.

Stdlib only; the PNG reader is crowd_pixels.read_png.
"""
from __future__ import annotations

import argparse
import math
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from crowd_pixels import read_png                                    # noqa: E402


def luma(r: int, g: int, b: int) -> float:
    """Relative luminance, sRGB decoded. Rec.709 weights."""
    def lin(v: int) -> float:
        c = v / 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def rows_of(path: pathlib.Path) -> tuple[int, int, list[list[tuple[int, int, int]]]]:
    w, h, raw = read_png(path)
    rows = [[(row[i], row[i + 1], row[i + 2]) for i in range(0, w * 3, 3)] for row in raw]
    return w, h, rows


def green(px: tuple[int, int, int]) -> bool:
    """Turf: green dominant, not the painted white, not the dark fascia."""
    r, g, b = px
    return g > r + 8 and g > b + 8 and 25 < g < 235


def bands(path: pathlib.Path) -> None:
    w, h, rows = rows_of(path)
    field: list[float] = []
    stands: list[float] = []
    sky: list[float] = []
    # The sky is above the rim: the highest rows that hold no turf anywhere.
    first_green = h
    for y, row in enumerate(rows):
        if sum(1 for px in row if green(px)) > w * 0.02:
            first_green = min(first_green, y)
    for y, row in enumerate(rows):
        for x in range(0, w, 3):                       # every third column is plenty
            px = row[x]
            L = luma(*px)
            if green(px) and y > first_green:
                field.append(L)
            elif y < first_green * 0.45:
                sky.append(L)
            elif y < first_green:
                stands.append(L)
    def report(name: str, vals: list[float]) -> float:
        if not vals:
            print(f"{name:8} no pixels")
            return 0.0
        vals.sort()
        mean = sum(vals) / len(vals)
        print(f"{name:8} mean {mean:.4f}  median {vals[len(vals) // 2]:.4f}  "
              f"p10 {vals[len(vals) // 10]:.4f}  p90 {vals[len(vals) * 9 // 10]:.4f}  "
              f"n {len(vals)}")
        return mean
    f = report("field", field)
    s = report("stands", stands)
    k = report("sky", sky)
    print()
    for name, a, b, want in (("stands", f, s, 1.0), ("sky", f, k, 2.0)):
        if a > 0 and b > 0:
            stops = math.log2(a / b)
            verdict = "holds" if abs(stops - want) <= 0.6 else "OFF"
            print(f"field -> {name:7} {stops:+.2f} stops (art bible wants {want:.0f}) {verdict}")


def edges(path: pathlib.Path, columns: int = 24) -> None:
    """Row-to-row steps in turf luminance, per column, biggest first."""
    w, h, rows = rows_of(path)
    steps: dict[int, list[tuple[float, int]]] = {}
    for ci in range(columns):
        x = int(w * (ci + 0.5) / columns)
        col = [(y, luma(*rows[y][x])) for y in range(h) if green(rows[y][x])]
        if len(col) < 20:
            continue
        # Smooth over 3 rows so a mown stripe's dither does not read as a step.
        for i in range(3, len(col) - 3):
            y0, _ = col[i]
            before = sum(v for _, v in col[i - 3:i]) / 3
            after = sum(v for _, v in col[i:i + 3]) / 3
            if col[i + 3][0] - col[i - 3][0] > 12:       # a gap, not a neighbour
                continue
            steps.setdefault(y0, []).append((after - before, x))
    ranked = sorted(steps.items(), key=lambda kv: -abs(sum(d for d, _ in kv[1]) / len(kv[1])))
    print(f"{'row':>5}  {'mean step':>10}  {'columns':>7}   (negative = darker below)")
    for y, hits in ranked[:12]:
        mean = sum(d for d, _ in hits) / len(hits)
        print(f"{y:5d}  {mean:+10.4f}  {len(hits):7d}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("shot", type=pathlib.Path)
    ap.add_argument("--bands", action="store_true")
    ap.add_argument("--edges", action="store_true")
    ap.add_argument("--columns", type=int, default=24)
    args = ap.parse_args()
    if args.bands or not args.edges:
        bands(args.shot)
    if args.edges:
        print()
        edges(args.shot, args.columns)


if __name__ == "__main__":
    main()
