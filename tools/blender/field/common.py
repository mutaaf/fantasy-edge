"""Shared plumbing for the field and sideline asset scripts.

Every script here runs inside Blender (`blender -b --factory-startup --python
<script> -- <args>`), imports this module by path, and writes under
assets/actors/field or assets/actors/sideline. Nothing here is hand-authored in
a DCC: a second run from the same inputs writes the same geometry and masks,
and the Cycles bakes match to within sampling noise (seeded, fixed samples).

Blender's bundled numpy is allowed in these tools. It never reaches the app or
the Python package, which stay stdlib only.
"""
from __future__ import annotations

import json
import math
import pathlib
import struct
import sys
import zlib

ROOT = pathlib.Path(__file__).resolve().parents[3]
FIELD_OUT = ROOT / "assets" / "actors" / "field"
SIDELINE_OUT = ROOT / "assets" / "actors" / "sideline"

YARD = 0.9144       # metres
FOOT = 0.3048
INCH = 0.0254

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def script_args() -> list[str]:
    argv = sys.argv
    return argv[argv.index("--") + 1:] if "--" in argv else []


# ───────────────────────────── images ─────────────────────────────

def write_png(path: pathlib.Path, arr, bits: int = 8) -> None:
    """Write a float array in 0..1 (H, W) or (H, W, C) as PNG, top row first.

    Hand-rolled so the bytes do not depend on Blender's image writer settings,
    which change between releases and would make regeneration noisy.
    """
    import numpy as np
    a = np.asarray(arr, dtype=np.float64)
    if a.ndim == 2:
        a = a[:, :, None]
    h, w, c = a.shape
    colour = {1: 0, 2: 4, 3: 2, 4: 6}[c]
    a = np.clip(a, 0.0, 1.0)
    if bits == 16:
        data = np.round(a * 65535).astype(">u2")
    else:
        data = np.round(a * 255).astype(np.uint8)
    raw = np.concatenate([np.zeros((h, 1), dtype=np.uint8),
                          data.reshape(h, -1).view(np.uint8).reshape(h, -1)], axis=1).tobytes()

    def chunk(tag: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + tag + body + struct.pack(">I", zlib.crc32(tag + body) & 0xFFFFFFFF)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x89PNG\r\n\x1a\n"
                     + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, bits, colour, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(raw, 9))
                     + chunk(b"IEND", b""))


def read_image(path: pathlib.Path):
    """Load any image Blender can read as float RGBA (H, W, 4), top row first."""
    import bpy
    import numpy as np
    img = bpy.data.images.load(str(path), check_existing=False)
    w, h = img.size
    px = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    return px.reshape(h, w, 4)[::-1].copy()


def write_json(path: pathlib.Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


# ───────────────────────────── scene ─────────────────────────────

def reset_scene(engine: str = "CYCLES", samples: int = 64, seed: int = 7):
    import bpy
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.engine = engine
    if engine == "CYCLES":
        prefs = bpy.context.preferences.addons["cycles"].preferences
        try:
            prefs.compute_device_type = "METAL"
            prefs.get_devices()
            for d in prefs.devices:
                d.use = True
            scene.cycles.device = "GPU"
        except Exception:
            scene.cycles.device = "CPU"
        scene.cycles.samples = samples
        scene.cycles.seed = seed
        scene.cycles.use_denoising = False
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    return scene


def material(name: str, base=(0.8, 0.8, 0.8), rough: float = 0.5, metal: float = 0.0,
             emission=None, alpha: float = 1.0):
    """A glTF-exportable Principled material: factors only, no procedural nodes."""
    import bpy
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*base, 1.0)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if emission is not None:
        b.inputs["Emission Color"].default_value = (*emission, 1.0)
        b.inputs["Emission Strength"].default_value = 1.0
    if alpha < 1.0:
        b.inputs["Alpha"].default_value = alpha
        m.surface_render_method = "BLENDED"
    return m


def srgb_to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def hex_linear(h: str):
    h = h.lstrip("#")
    return tuple(srgb_to_linear(int(h[i:i + 2], 16) / 255) for i in (0, 2, 4))


def rng(seed: int):
    import numpy as np
    return np.random.default_rng(seed)
