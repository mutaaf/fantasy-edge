"""Compile Lighting's Shader Graph package: the beam material.

    python3 tools/blender/lighting/shadergraph.py [xrsimulator|xros]

`tools/blender/lighting/shadergraph/Beams.rkassets/Beams.usda` is hand-written
MaterialX (docs/SHADERGRAPH.md). Its two grey textures are derived here from
the portable beam textures textures.py writes, so the graph and the UV-scroll
fallback draw from the same images. Output: assets/actors/lighting/Beams.reality.

Lighting keeps its own package rather than adding to the shared
Materials.reality: StadiumShaderGraph's fallback loader returns the first
ShaderGraphMaterial it finds in a file, so one material per file is what makes
the prim unambiguous.
"""
from __future__ import annotations

import pathlib
import struct
import subprocess
import sys
import zlib

ROOT = pathlib.Path(__file__).resolve().parents[3]
PKG = ROOT / "tools" / "blender" / "lighting" / "shadergraph" / "Beams.rkassets"
TEX = ROOT / "assets" / "actors" / "lighting" / "textures"
OUT = ROOT / "assets" / "actors" / "lighting" / "Beams.reality"


def read_png_alpha(path: pathlib.Path) -> tuple[int, int, bytes]:
    """8-bit RGBA, non-interlaced PNG (what textures.py writes) -> its alpha channel."""
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    pos, idat = 8, b""
    w = h = 0
    while pos < len(data):
        n = struct.unpack(">I", data[pos:pos + 4])[0]
        tag = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + n]
        if tag == b"IHDR":
            w, h, depth, colour = struct.unpack(">IIBB", body[:10])
            assert depth == 8 and colour == 6, f"{path.name}: expected 8-bit RGBA"
        elif tag == b"IDAT":
            idat += body
        pos += 12 + n
    raw = zlib.decompress(idat)
    bpp, stride = 4, w * 4
    out = bytearray()
    prev = bytearray(stride)
    i = 0
    for _ in range(h):
        f = raw[i]
        line = bytearray(raw[i + 1:i + 1 + stride])
        i += 1 + stride
        for x in range(stride):
            a = line[x - bpp] if x >= bpp else 0
            b = prev[x]
            c = prev[x - bpp] if x >= bpp else 0
            if f == 1:
                line[x] = (line[x] + a) & 255
            elif f == 2:
                line[x] = (line[x] + b) & 255
            elif f == 3:
                line[x] = (line[x] + (a + b) // 2) & 255
            elif f == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[x] = (line[x] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        out += line[3::4]
        prev = line
    return w, h, bytes(out)


def write_grey(path: pathlib.Path, w: int, h: int, grey: bytes) -> None:
    rows = b"".join(b"\x00" + grey[y * w:(y + 1) * w] for y in range(h))

    def chunk(tag, body):
        return struct.pack(">I", len(body)) + tag + body + struct.pack(">I", zlib.crc32(tag + body) & 0xFFFFFFFF)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b""))


def main() -> int:
    for src, dst in (("beam_quad.png", "beam_profile_sg.png"), ("beam_dust.png", "beam_dust_sg.png")):
        w, h, a = read_png_alpha(TEX / src)
        write_grey(PKG / dst, w, h, a)
    cmd = ["xcrun", "realitytool", "compile", str(PKG), "--output-reality", str(OUT),
           "--platform", sys.argv[1] if len(sys.argv) > 1 else "xrsimulator", "--deployment-target", "2.0"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not OUT.exists():
        print(r.stdout, r.stderr)
        return r.returncode or 1
    print(f"[lighting] wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
