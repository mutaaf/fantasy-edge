"""How much of a wide frame's stands each support owns, in pixels.

The crowd's share of *seats* is a number the app logs. What the eye judges is
the share of the *frame*: at integration-12 the visitors held 9% of the seats
and 27.8% of the stand pixels, which read as a painted wedge. This measures
the second, so the two can be reported together.

    python3 tools/crowd_pixels.py docs/lookdev/crowd-r6/bowl-wide.png \
        --home '#0B798E' --away '#116CD9'

Stdlib only: a small PNG reader (zlib plus the five filters), then every pixel
in the stands band is scored against the two chips and the neutral grey. Sky,
field, the black fascia and the overlay panels are excluded by brightness and
by where they are, not by hand-drawn masks, so the same call works on any
wide frame the harness shoots.
"""
from __future__ import annotations

import argparse
import pathlib
import struct
import zlib


def read_png(path: pathlib.Path) -> tuple[int, int, list[bytes]]:
    """(width, height, rows of RGB bytes). 8-bit grey, RGB or RGBA, no
    interlace. Grey is expanded to RGB, so every caller reads three bytes a
    pixel whatever the file held (the net mask is grey; the crowd's is RGB)."""
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise SystemExit(f"{path}: not a PNG")
    pos, idat, w, h, depth, colour = 8, bytearray(), 0, 0, 8, 6
    while pos < len(data):
        length, kind = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + length]
        if kind == b"IHDR":
            w, h, depth, colour, _, _, interlace = struct.unpack(">IIBBBBB", body)
            if depth != 8 or colour not in (0, 2, 6) or interlace:
                raise SystemExit(f"{path}: need an 8-bit grey, RGB or RGBA PNG, got depth {depth} colour {colour}")
        elif kind == b"IDAT":
            idat += body
        elif kind == b"IEND":
            break
        pos += 12 + length
    raw = zlib.decompress(bytes(idat))
    step = {0: 1, 2: 3, 6: 4}[colour]
    stride = w * step
    out, prev, at = [], bytearray(stride), 0
    for _ in range(h):
        filt = raw[at]; at += 1
        line = bytearray(raw[at:at + stride]); at += stride
        for i in range(stride):
            a = line[i - step] if i >= step else 0
            b = prev[i]
            c = prev[i - step] if i >= step else 0
            if filt == 1: line[i] = (line[i] + a) & 255
            elif filt == 2: line[i] = (line[i] + b) & 255
            elif filt == 3: line[i] = (line[i] + (a + b) // 2) & 255
            elif filt == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        prev = line
        if step == 1:
            out.append(bytes(v for g in line for v in (g, g, g)))
        else:
            out.append(bytes(line[i] for i in range(stride) if step == 3 or i % 4 != 3))
    return w, h, out


def chip(text: str) -> tuple[float, float, float]:
    t = text.lstrip("#")
    return tuple(int(t[i:i + 2], 16) / 255 for i in (0, 2, 4))


def hue_of(r: float, g: float, b: float) -> tuple[float, float, float]:
    """(hue 0-1, saturation, value), the usual conversion."""
    hi, lo = max(r, g, b), min(r, g, b)
    v, d = hi, hi - lo
    s = 0.0 if hi <= 0 else d / hi
    if d <= 1e-6:
        return 0.0, s, v
    if hi == r: h = ((g - b) / d) % 6
    elif hi == g: h = (b - r) / d + 2
    else: h = (r - g) / d + 4
    return h / 6, s, v


def hue_gap(a: float, b: float) -> float:
    d = abs(a - b) % 1.0
    return min(d, 1 - d)


def shares(path: pathlib.Path, home: str, away: str, top: float, bottom: float, gap: float = 0.02) -> dict:
    w, h, rows = read_png(path)
    hz = hue_of(*chip(home))
    az = hue_of(*chip(away))
    counts = {"home": 0, "away": 0, "other": 0, "ambiguous": 0}
    y0, y1 = int(h * top), int(h * bottom)
    for y in range(y0, y1):
        row = rows[y]
        for x in range(0, w, 2):                       # every other pixel: the answer is a share
            r, g, b = row[x * 3] / 255, row[x * 3 + 1] / 255, row[x * 3 + 2] / 255
            hue, sat, val = hue_of(r, g, b)
            # Stands only: the sky and the black fascia are dark, the field and the
            # overlay panels are brighter or greener than a lit crowd at this distance.
            if val < 0.055 or val > 0.72 or sat < 0.12:
                counts["other"] += 1
                continue
            if 0.2 < hue < 0.42 and sat > 0.25:        # the field's green
                counts["other"] += 1
                continue
            dh, da = hue_gap(hue, hz[0]), hue_gap(hue, az[0])
            # Two clubs whose chips sit a hair apart in hue cannot be told apart in a stand:
            # count those pixels rather than pretending the nearer one wins.
            if abs(dh - da) < gap:
                counts["ambiguous"] += 1
            else:
                counts["home" if dh < da else "away"] += 1
    stands = counts["home"] + counts["away"]
    total = stands + counts["ambiguous"]
    return {"file": path.name, "stand_pixels": total,
            "home": counts["home"] / stands if stands else 0.0,
            "away": counts["away"] / stands if stands else 0.0,
            "ambiguous": counts["ambiguous"] / total if total else 0.0}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("frames", nargs="+", type=pathlib.Path)
    ap.add_argument("--home", required=True, help="the home crowd chip, #rrggbb (scene bowl.crowd.home)")
    ap.add_argument("--away", required=True, help="the away crowd chip, #rrggbb")
    ap.add_argument("--top", type=float, default=0.12, help="ignore above this fraction of the frame (sky)")
    ap.add_argument("--bottom", type=float, default=0.72, help="ignore below this (field, near rows, controls)")
    ap.add_argument("--gap", type=float, default=0.02, help="hue gap under which a pixel belongs to neither club")
    args = ap.parse_args()
    for frame in args.frames:
        s = shares(frame, args.home, args.away, args.top, args.bottom, args.gap)
        print(f"{s['file']}: visiting {s['away'] * 100:.1f}% of attributable stand pixels "
              f"(home {s['home'] * 100:.1f}%, {s['ambiguous'] * 100:.1f}% of {s['stand_pixels']} too close to call)")


if __name__ == "__main__":
    main()
