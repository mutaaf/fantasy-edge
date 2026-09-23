#!/usr/bin/env python3
"""What the end-zone paint and its lettering actually measure, per club.

Two questions the field has to answer for every club, and they pull against
each other:

  1. Does the painted end zone read as a *different surface* from the grass?
     That is a colour-difference question, not a luminance one, so it is
     measured as CIE76 dE against `color.turf.a`. Below about 2.3 two colours
     are indistinguishable to an eye that is not comparing them side by side.

  2. Do the club's letters read on that paint? That is a luminance question,
     measured as a WCAG contrast ratio. End-zone lettering is enormous, so 3:1
     (large text) is the floor and 4.5:1 is comfortable.

`chip()` solves every club onto one luminance band so that white text clears
4.5:1 in a *panel*. That is the right answer for a chip and the wrong one for
a thousand square yards of paint: it lightens a club past what it is. Run this
with `--chip` to see the difference it makes.

Standard library only, like everything else here.

    python3 tools/field_paint.py                # true colours, the rule now
    python3 tools/field_paint.py --chip         # what chips measured instead
    python3 tools/field_paint.py --worst        # only the clubs that bind
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from fantasyedge import scene as sc                                # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
TOKENS = json.loads((ROOT / "design" / "tokens.json").read_text())


def rgb(h: str) -> tuple[float, float, float]:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def hexs(c: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{max(0, min(255, round(x * 255))):02X}" for x in c)


def linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def luminance(h: str) -> float:
    r, g, b = (linear(x) for x in rgb(h))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def ratio(a: str, b: str) -> float:
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _xyz(h: str) -> tuple[float, float, float]:
    r, g, b = (linear(x) for x in rgb(h))
    return (r * 0.4124 + g * 0.3576 + b * 0.1805,
            r * 0.2126 + g * 0.7152 + b * 0.0722,
            r * 0.0193 + g * 0.1192 + b * 0.9505)


def _lab(h: str) -> tuple[float, float, float]:
    x, y, z = _xyz(h)
    x, y, z = x / 0.95047, y / 1.0, z / 1.08883
    f = lambda t: t ** (1 / 3) if t > 0.008856 else (7.787 * t) + 16 / 116   # noqa: E731
    fx, fy, fz = f(x), f(y), f(z)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def dE(a: str, b: str) -> float:
    (l1, a1, b1), (l2, a2, b2) = _lab(a), _lab(b)
    return ((l1 - l2) ** 2 + (a1 - a2) ** 2 + (b1 - b2) ** 2) ** 0.5


def over(paint: str, ground: str, opacity: float) -> str:
    """Paint composited over the grass, which is what an eye actually sees.

    An approximation of one alpha blend: the renderer also lays blades back
    over the paint, and the floods are not modelled at all. It is the same
    approximation on both sides of a before/after, which is what makes the
    comparison worth anything.
    """
    p, g = rgb(paint), rgb(ground)
    return hexs(tuple(opacity * p[i] + (1 - opacity) * g[i] for i in range(3)))


def clubs() -> dict[str, str]:
    """Every club colour a fixture or capture in this repo states."""
    found: dict[str, str] = {}
    pattern = re.compile(
        r'"(?:abbreviation)"\s*:\s*"([^"]+)"[^}]{0,400}?"color"\s*:\s*"([0-9a-fA-F]{6})"')
    for folder in ("tests/fixtures", "data/replay/source"):
        for p in (ROOT / folder).glob("*.json"):
            try:
                text = p.read_text()
            except OSError:
                continue
            for m in pattern.finditer(text):
                found.setdefault(m.group(1), "#" + m.group(2).upper())
    return found


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--chip", action="store_true",
                    help="measure the solved chip instead of the club's colour")
    ap.add_argument("--worst", action="store_true", help="only the binding clubs")
    args = ap.parse_args()

    paintTok = TOKENS["visual"]["field"]["paint"]
    turf = TOKENS["color"]["turf.a"]
    opacity = paintTok["endZoneOpacity"]
    inks = {"white": paintTok["white"], "dark": paintTok.get("ink", "#12140F")}

    rows = []
    for abbr, colour in sorted(clubs().items()):
        used = sc.chip(colour, TOKENS["chip"]) if args.chip else colour
        seen = over(used, turf, opacity)
        best = max(inks, key=lambda k: ratio(inks[k], seen))
        rows.append((abbr, colour, used, seen, dE(seen, turf),
                     best, ratio(inks[best], seen), ratio(inks["white"], seen)))

    rows.sort(key=lambda r: (r[4], r[6]))
    shown = rows[:6] if args.worst else rows
    what = "chip" if args.chip else "club colour"
    print(f"{'club':5} {'colour':8} {what:9} {'over grass':10} "
          f"{'dE turf':>8} {'ink':5} {'ratio':>6} {'white':>6}")
    for abbr, colour, used, seen, d, ink, r, rw in shown:
        flag = "" if d >= 2.3 and r >= 3.0 else "  <-- fails"
        print(f"{abbr:5} {colour:8} {used:9} {seen:10} {d:8.1f} {ink:5} "
              f"{r:6.1f} {rw:6.1f}{flag}")

    worstDE = min(r[4] for r in rows)
    worstInk = min(r[6] for r in rows)
    worstWhite = min(r[7] for r in rows)
    print(f"\n{len(rows)} clubs. worst dE against turf {worstDE:.1f} (JND 2.3); "
          f"worst lettering {worstInk:.1f}:1 with the ink chosen, "
          f"{worstWhite:.1f}:1 if white were assumed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
