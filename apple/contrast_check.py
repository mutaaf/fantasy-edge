#!/usr/bin/env python3
"""Measures every colour in `Theme.swift` instead of eyeballing it.

The palette this app started from is ESPN's, picked for a deep navy ground.
visionOS draws the whole console on `glassBackgroundEffect`, which is
translucent over whatever room the wearer happens to be in - and a colour that
is legible over a dark room is illegible over a bright one. So a token is
checked against *both* extremes here, never one:

  * a bright room seen through glass, sampled off a real headset screenshot
  * a dark room seen through the same glass

Three questions, and a token only passes the ones that apply to how it is
actually used:

  ink   - is this legible as text drawn straight onto glass?  (4.5:1 body,
          3:1 large.)  Every brand hue fails this on a bright room and always
          will, which is why the app no longer draws text in one.
  fill  - is this usable as an opaque chip: white text on it at 4.5:1, and the
          chip's own edge visible at 3:1 against both rooms?  That is a narrow
          band of luminance, and the `*Fill` tokens are computed to sit in it.
  hue   - do two colours that mean different things stay different for a
          reader with deuteranopia?  Simulated, then measured as CIE76 dE.

Run:  python3 apple/contrast_check.py            # report, exit 1 on a failure
      python3 apple/contrast_check.py --propose  # suggest fills for the hues

Standard library only, like everything else in this repository.
"""
from __future__ import annotations

import argparse
import colorsys
import math
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
THEME = HERE / "FantasyEdge" / "Sources" / "Theme.swift"

# Sampled from the user's own headset screenshot: a light room behind the
# glass. Not invented - #d8dad4 is what the panel body actually renders as
# over a bright wall.
LIGHT = (0xD8 / 255, 0xDA / 255, 0xD4 / 255)
# The other end of the same surface: the glass over an unlit room. A token has
# to survive both, because the app cannot see the room.
DARK = (0x1A / 255, 0x1C / 255, 0x20 / 255)
WHITE = (1.0, 1.0, 1.0)
# The one ground on this surface the app paints itself: the pitch in
# `Field.swift`, drawn as an opaque dark-green gradient. Colour is allowed to
# be ink there, because the backdrop is known - which is the whole distinction
# this file exists to make. Its lighter end, so the check is the harder one.
PITCH = (0x0E / 255, 0x3A / 255, 0x1F / 255)

# WCAG 2.1: 4.5:1 for body text, 3:1 for large text and for the boundary of a
# non-text control.
BODY, LARGE, COMPONENT = 4.5, 3.0, 3.0
# A chip is only readable if it is opaque, so its fill has to land where white
# text clears BODY *and* the chip clears COMPONENT against both rooms. That
# works out to a luminance window, computed rather than guessed:
FILL_MAX_L = 1.05 / BODY - 0.05                     # white text at 4.5:1
FILL_MIN_L = COMPONENT * (rel := 0.0) or None       # filled in below


def linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def luminance(rgb) -> float:
    r, g, b = (linear(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b) -> float:
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


FILL_MIN_L = COMPONENT * (luminance(DARK) + 0.05) - 0.05


# ---------------------------------------------------------------- colour blind

# Viénot, Brettel & Mollon (1999), the standard single-plane projection for a
# dichromat. Applied in linear light, which is where the projection is defined
# - running it on gamma-encoded values, as a lot of web snippets do, moves the
# result enough to change a verdict.
DEUTER = ((0.625, 0.375, 0.0),
          (0.700, 0.300, 0.0),
          (0.0, 0.300, 0.700))


def simulate(rgb, m=DEUTER):
    lin = [linear(c) for c in rgb]
    out = [sum(m[i][j] * lin[j] for j in range(3)) for i in range(3)]

    def encode(c):
        c = max(0.0, min(1.0, c))
        return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055

    return tuple(encode(c) for c in out)


def lab(rgb):
    r, g, b = (linear(c) for c in rgb)
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 1.00000
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def f(t):
        return t ** (1 / 3) if t > 216 / 24389 else (841 / 108) * t + 4 / 29

    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def delta_e(a, b):
    la, aa, ba = lab(a)
    lb, ab, bb = lab(b)
    return math.dist((la, aa, ba), (lb, ab, bb))


# ------------------------------------------------------------------- the theme

TOKEN = re.compile(
    r"static let (\w+)\s*=\s*Color\(red:\s*([\d.]+),\s*green:\s*([\d.]+),\s*blue:\s*([\d.]+)\)")
CASE = re.compile(
    r'case "([A-Z/]+)":\s*return Color\(red:\s*([\d.]+),\s*green:\s*([\d.]+),\s*blue:\s*([\d.]+)\)')
DEFAULT = re.compile(
    r'default:\s*return Color\(red:\s*([\d.]+),\s*green:\s*([\d.]+),\s*blue:\s*([\d.]+)\)')


def read_theme(path=THEME):
    """Read the palette out of the source rather than restating it here.

    Two functions in Theme.swift return position colours - the translucent
    identity hue and the opaque chip fill - and they are read separately. A
    single sweep of the file matched both and let the second silently
    overwrite the first, so the report claimed the old hues had been fixed
    when nothing about them had changed.
    """
    src = path.read_text()
    out = {}
    for name, r, g, b in TOKEN.findall(src):
        out[name] = (float(r), float(g), float(b))
    for fn, prefix in (("func position(", "pos."), ("func positionFill(", "posFill.")):
        i = src.find(fn)
        if i < 0:
            continue
        body = src[i:src.find("\n    }", i)]
        for pos, r, g, b in CASE.findall(body):
            out[prefix + pos] = (float(r), float(g), float(b))
        m = DEFAULT.search(body)
        if m:
            out[prefix + "DEF"] = tuple(float(x) for x in m.groups())
    return out


def hexof(rgb):
    return "#" + "".join(f"{round(c * 255):02x}" for c in rgb)


# ------------------------------------------------------------------- proposing

# Where in the legal band each fill sits, and why it sits there. The band is
# inset from its own edges by a few percent so a rounding of the literals in
# Theme.swift cannot push a token out of it.
BAND_LO, BAND_HI = FILL_MIN_L * 1.05, FILL_MAX_L * 0.97
# Ahead / caution / behind are the one triple whose members must not be
# confused, and hue alone cannot carry that for a deuteranope - so they are
# also spread across the band, darkest to lightest, and each carries a glyph
# in the interface on top of that. The position hues sit together in the
# middle: a position chip has the letters written on it, so its colour is
# identity rather than the thing being read.
TARGETS = {"green": BAND_LO, "red": (BAND_LO + BAND_HI) / 2, "gold": BAND_HI}


def propose(rgb, target=None):
    """The same hue, taken to the luminance an opaque chip needs.

    Hue is held exactly and saturation allowed to rise only a little, because
    the point is to keep the product's identity rather than to invent a new
    palette. The cap matters: pushing saturation to the maximum turns the
    near-neutral used for defences into a vivid blue, which would have given
    D/ST a colour it has never had and put it next to the one WR already uses.
    Only the lightness really moves, and it moves to a number the checks above
    demand rather than to one that looked right.
    """
    target = target if target is not None else (BAND_LO + BAND_HI) / 2
    h, s0, _ = colorsys.rgb_to_hsv(*rgb)
    best, err = None, 1e9
    for si in range(int(s0 * 100), int(min(1.0, s0 + 0.25) * 100) + 1):
        s = si / 100
        lo, hi = 0.0, 1.0
        for _ in range(48):
            v = (lo + hi) / 2
            cand = colorsys.hsv_to_rgb(h, s, v)
            if luminance(cand) < target:
                lo = v
            else:
                hi = v
        cand = colorsys.hsv_to_rgb(h, s, (lo + hi) / 2)
        e = abs(luminance(cand) - target)
        if e <= err + 1e-6:
            best, err = cand, min(err, e)
    return tuple(round(c, 3) for c in best)


# --------------------------------------------------------------------- tokens

TOKENS = HERE.parent / "design" / "tokens.json"


def check_tokens(path=TOKENS) -> list[str]:
    """The stadium's palette lives in design/tokens.json, not in Theme.swift.

    Two rules apply there. A `fill.*` token carries white text, so it is held
    to the chip rule above. Everything drawn on the turf - lasers, arcs, the
    beacon, yard lines - is a graphic on a ground this app paints, so it has to
    clear the component ratio against the lit turf it sits on, the lighter of
    the two stripes, which is the harder case.
    """
    import json

    if not path.exists():
        return []
    tokens = json.loads(path.read_text())["color"]

    def rgb(hexs):
        h = hexs.lstrip("#")[:6]
        return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))

    turf = max((rgb(tokens["turf.a"]), rgb(tokens["turf.b"])), key=luminance)
    fails = []
    print(f"\ndesign/tokens.json - fills as chips, turf graphics against {hexof(turf)}")
    for name, value in sorted(tokens.items()):
        if name.startswith("fill."):
            c = rgb(value)
            wo, cl, cd = contrast(WHITE, c), contrast(c, LIGHT), contrast(c, DARK)
            ok = wo >= BODY and cl >= COMPONENT and cd >= COMPONENT
            print(f"  {name:18s} {value:9s} white {wo:5.2f}  edge {cl:5.2f}/{cd:5.2f}  "
                  f"{'chip OK' if ok else 'CHIP FAILS'}")
            if not ok:
                fails.append(f"tokens {name}: white {wo:.2f}:1, edge {cl:.2f}/{cd:.2f}")
        elif name.split(".")[0] in ("laser", "arc", "beacon", "line"):
            on = contrast(rgb(value), turf)
            ok = on >= COMPONENT
            print(f"  {name:18s} {value:9s} on turf {on:5.2f}  {'OK' if ok else 'FAILS'}")
            if not ok:
                fails.append(f"tokens {name}: {on:.2f}:1 on the turf")
    return fails


# --------------------------------------------------------------------- report

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--propose", action="store_true",
                    help="print chip fills for every hue that has none")
    args = ap.parse_args()

    theme = read_theme()
    if not theme:
        print(f"no colours found in {THEME}", file=sys.stderr)
        return 2

    print(f"backdrops: light {hexof(LIGHT)} (L={luminance(LIGHT):.4f})  "
          f"dark {hexof(DARK)} (L={luminance(DARK):.4f})")
    print(f"an opaque chip fill must sit in L {FILL_MIN_L:.4f}..{FILL_MAX_L:.4f} "
          f"for white text at {BODY}:1 and an edge at {COMPONENT}:1 on both\n")

    if args.propose:
        for name, rgb in sorted(theme.items()):
            if name.endswith("Fill") or name.startswith("posFill.") \
                    or name in ("navy", "navyUp"):
                continue
            p = propose(rgb, TARGETS.get(name))
            print(f"{name:14s} {hexof(rgb)} -> {hexof(p)}  "
                  f"Color(red: {p[0]}, green: {p[1]}, blue: {p[2]})")
        return 0

    fails = []
    print(f"{'token':16s} {'hex':9s} {'ink/light':>9s} {'ink/dark':>9s} "
          f"{'white on':>9s} {'chip/light':>10s} {'chip/dark':>9s}  verdict")
    for name, rgb in sorted(theme.items()):
        is_fill = name.endswith("Fill") or name.startswith("posFill.")
        il, id_ = contrast(rgb, LIGHT), contrast(rgb, DARK)
        wo = contrast(WHITE, rgb)
        cl, cd = il, id_
        if is_fill:
            ok = wo >= BODY and cl >= COMPONENT and cd >= COMPONENT
            verdict = "chip OK" if ok else "CHIP FAILS"
            if not ok:
                fails.append(f"{name}: white {wo:.2f}:1, edge {cl:.2f}/{cd:.2f}")
        else:
            ok = il >= LARGE and id_ >= LARGE
            verdict = "ink OK" if ok else "ink unusable (chip only)"
        print(f"{name:16s} {hexof(rgb):9s} {il:9.2f} {id_:9.2f} {wo:9.2f} "
              f"{cl:10.2f} {cd:9.2f}  {verdict}")

    print("\non the painted pitch - the one ground this app owns, so a hue may "
          "be ink there")
    for name in ("gold", "green", "red"):
        if name in theme:
            print(f"  {name:6s} on turf {hexof(PITCH)}: "
                  f"{contrast(theme[name], PITCH):5.2f}:1")

    print("\ndeuteranopia - CIE76 dE between pairs that carry different meanings")
    print("(dE under ~11 is a pair most people cannot tell apart)")
    pairs = [("green", "red"), ("green", "gold"), ("red", "gold"),
             ("greenFill", "redFill"), ("greenFill", "goldFill"),
             ("redFill", "goldFill"),
             ("posFill.QB", "posFill.RB"), ("posFill.RB", "posFill.WR"),
             ("posFill.WR", "posFill.TE"), ("posFill.TE", "posFill.K"),
             ("posFill.QB", "posFill.K"), ("posFill.RB", "posFill.DEF")]
    for a, b in pairs:
        if a not in theme or b not in theme:
            continue
        raw = delta_e(theme[a], theme[b])
        sim = delta_e(simulate(theme[a]), simulate(theme[b]))
        flag = "" if sim >= 11 else "   <- hue alone is not enough here"
        print(f"  {a:12s} vs {b:12s}  dE {raw:6.1f} -> {sim:6.1f} deuteranopic{flag}")

    fails += check_tokens()

    if fails:
        print("\nFAIL")
        for f in fails:
            print("  " + f)
        return 1
    print("\nOK - every chip fill clears white text at 4.5:1 and an edge at "
          "3:1 on both rooms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
