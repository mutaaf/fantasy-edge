"""Team chip colours: a tiny stand-in so tiles can be tested today.

# INTEGRATE: shared team chip colour normalisation from fantasy-edge
# scene/replay branch. That branch owns the one implementation (tokens +
# luminance band). This stand-in is the same rule as design/build.py's
# chip(), kept to the minimum the slate contract needs, and is deleted at
# integration.
"""
from __future__ import annotations

import colorsys

BAND = 0.159            # relative luminance where white text clears 4.5:1


def _lin(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _lum(rgb) -> float:
    r, g, b = (_lin(x) for x in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _rgb(hexs: str):
    h = (hexs or "666666").lstrip("#")
    if len(h) != 6:
        h = "666666"
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def chip(hexs: str) -> str:
    h, s, _ = colorsys.rgb_to_hsv(*_rgb(hexs))
    s = 0.0 if s < 0.12 else min(s, 0.92)
    while s > 0 and _lum(colorsys.hsv_to_rgb(h, s, 1.0)) < BAND:
        s -= 0.02
    s = max(s, 0.0)
    lo, hi = 0.0, 1.0
    for _ in range(30):
        m = (lo + hi) / 2
        lo, hi = (m, hi) if _lum(colorsys.hsv_to_rgb(h, s, m)) < BAND else (lo, m)
    return "#" + "".join(f"{round(x * 255):02X}" for x in colorsys.hsv_to_rgb(h, s, (lo + hi) / 2))


def clash(a: str, b: str) -> bool:
    (ha, sa, _), (hb, sb, _) = (colorsys.rgb_to_hsv(*_rgb(x)) for x in (a, b))
    if sa < 0.12 and sb < 0.12:
        return True
    d = abs(ha - hb) * 360
    return min(d, 360 - d) < 16 and sa >= 0.12 and sb >= 0.12


def pair(away: dict, home: dict) -> None:
    """Fill both sides' `fill` and `hatch`; the away side gives way on a clash."""
    away["fill"], home["fill"] = chip(away["color"]), chip(home["color"])
    away["hatch"] = home["hatch"] = False
    if clash(away["fill"], home["fill"]):
        alt = chip(away.get("alternateColor") or "#666666")
        if colorsys.rgb_to_hsv(*_rgb(alt))[1] >= 0.12 and not clash(alt, home["fill"]):
            away["fill"] = alt
        else:
            away["hatch"] = True
