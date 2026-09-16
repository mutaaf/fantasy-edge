"""Read mesh positions straight out of a .glb, stdlib only.

Shared by build.py (measuring which way the exported fans face) and
tests/test_crowd_kit.py (holding them to it), so both read the bytes a
renderer reads. Node transforms are applied (translation, rotation, scale);
the result is in glTF's own frame, +Y up.
"""
from __future__ import annotations

import json
import math
import pathlib
import struct


def _quat_rotate(q, v):
    x, y, z, w = q
    vx, vy, vz = v
    # v + 2w(q x v) + 2 q x (q x v)
    cx, cy, cz = y * vz - z * vy, z * vx - x * vz, x * vy - y * vx
    cx2, cy2, cz2 = y * cz - z * cy, z * cx - x * cz, x * cy - y * cx
    return (vx + 2 * (w * cx + cx2), vy + 2 * (w * cy + cy2), vz + 2 * (w * cz + cz2))


def load(path: pathlib.Path):
    b = pathlib.Path(path).read_bytes()
    n = struct.unpack("<I", b[12:16])[0]
    doc = json.loads(b[20:20 + n])
    off = 20 + n
    size = struct.unpack("<I", b[off:off + 4])[0]
    return doc, b[off + 8:off + 8 + size]


def meshes(path, suffix: str = ""):
    """(mesh name, [(x, y, z), ...]) for every node whose mesh name ends with `suffix`."""
    doc, blob = load(path)
    out = []
    for node in doc.get("nodes", []):
        if "mesh" not in node:
            continue
        mesh = doc["meshes"][node["mesh"]]
        name = mesh.get("name", node.get("name", ""))
        if suffix and not name.endswith(suffix):
            continue
        t = node.get("translation", (0, 0, 0)); r = node.get("rotation", (0, 0, 0, 1)); sc = node.get("scale", (1, 1, 1))
        pts = []
        for prim in mesh["primitives"]:
            acc = doc["accessors"][prim["attributes"]["POSITION"]]
            view = doc["bufferViews"][acc["bufferView"]]
            start = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
            stride = view.get("byteStride", 12)
            for i in range(acc["count"]):
                v = struct.unpack_from("<3f", blob, start + stride * i)
                v = _quat_rotate(r, (v[0] * sc[0], v[1] * sc[1], v[2] * sc[2]))
                pts.append((v[0] + t[0], v[1] + t[1], v[2] + t[2]))
        out.append((name, pts))
    return out
