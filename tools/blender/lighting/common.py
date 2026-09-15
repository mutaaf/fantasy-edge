"""Shared by every lighting and sky script: where things are, how files are written.

Runs inside Blender's own Python (it carries numpy); nothing here imports
outside bpy, numpy and the standard library.

Units. The scene spec works in yards with x along the field from the home goal
line (0..100, end zones beyond), y up and z across from the centre line, the
far side negative. Blender works in metres, Z up. One mapping, used everywhere:

    blender X = (x - 50) * YD      blender Y = -z * YD      blender Z = y * YD

glTF's exporter turns Blender Z-up into Y-up, so a .glb written here comes out
as (x - 50, y, z) in metres: the scene's own axes, centred on the fifty. A
renderer that works in yards divides by YD.
"""
from __future__ import annotations

import json
import math
import os
import pathlib
import sys

import bpy
import numpy as np

YD = 0.9144
HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUT_LIGHT = ROOT / "assets" / "actors" / "lighting"
OUT_SKY = ROOT / "assets" / "actors" / "sky"
SCRATCH = pathlib.Path(os.environ.get("FE_LIGHTING_SCRATCH", ROOT / ".work" / "lighting"))

# Mirrors fantasyedge/scene.py BOWL and look.light.rim. Read here rather than
# imported: Blender's Python has no path to the package, and this file is the
# one place a drift would be noticed (build.py checks it against scene.py).
HALF_LENGTH = 60.0          # half the field plus an end zone, yards
HALF_WIDTH = 160.0 / 6.0    # 26.67 yards
BOWL_EXPONENT = 4.0
TIERS = [
    {"name": "lower", "inner": 6.0, "outer": 36.0, "rise": (1.0, 19.6)},
    {"name": "upper", "inner": 42.0, "outer": 70.0, "rise": (24.0, 45.8)},
]
RIM = {"count": 16, "beyondOuter": 1.0, "phase": 0.3, "heightAbove": 9.0}


def to_blender(x, y, z):
    return ((x - 50.0) * YD, -z * YD, y * YD)


def bowl_xz(offset, t):
    """A point on the bowl's superellipse `offset` yards out, angle t, in scene yards
    relative to the fifty (so add 50 to x for scene coordinates)."""
    a, b = HALF_LENGTH + offset, HALF_WIDTH + offset
    c, s = math.cos(t), math.sin(t)
    e = 2.0 / BOWL_EXPONENT
    return a * math.copysign(abs(c) ** e, c), b * math.copysign(abs(s) ** e, s)


def placeholder_mounts():
    """Where light banks stand until Bowl publishes assets/actors/bowl/mounts.json.

    All the way round: a real stadium lights from every side, and the probe
    must see that even where a renderer only draws the far side. Each mount
    faces the centre of the field and is tilted down to it.
    """
    mounts_file = ROOT / "assets" / "actors" / "bowl" / "mounts.json"
    if mounts_file.exists():
        data = json.loads(mounts_file.read_text())
        rigs = [m for m in data.get("mounts", []) if m.get("kind", "light") in ("light", "lightBank")]
        if rigs:
            return rigs, "bowl/mounts.json"
    top = TIERS[-1]
    offset = top["outer"] + RIM["beyondOuter"]
    y = top["rise"][1] + RIM["heightAbove"]
    mounts = []
    for k in range(RIM["count"]):
        t = k * math.pi / (RIM["count"] / 2) + RIM["phase"]
        bx, bz = bowl_xz(offset, t)
        mounts.append({"id": f"rim{k}", "kind": "lightBank", "x": round(bx + 50.0, 3), "y": round(y, 3),
                       "z": round(bz, 3), "aim": [50.0, 0.0, 0.0], "side": "far" if bz < 0 else "near"})
    return mounts, "placeholder"


# ───────────────────────────── scene setup ─────────────────────────────

def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    prefs = bpy.context.preferences.addons["cycles"].preferences
    try:
        prefs.compute_device_type = "METAL"
        prefs.get_devices()
        for d in prefs.devices:
            d.use = True
        scene.cycles.device = "GPU"
    except Exception:
        scene.cycles.device = "CPU"
    scene.cycles.use_denoising = True
    scene.cycles.seed = 7
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.display_settings.display_device = "sRGB"
    return scene


def material(name, color=(0.5, 0.5, 0.5), rough=0.6, metal=0.0, emit=None, emit_strength=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1.0)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if emit is not None:
        b.inputs["Emission Color"].default_value = (*emit, 1.0)
        b.inputs["Emission Strength"].default_value = emit_strength
    return m


def link(obj, collection=None):
    (collection or bpy.context.scene.collection).objects.link(obj)
    return obj


def mesh_object(name, verts, faces, mat=None, uvs=None):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    if uvs is not None:
        layer = me.uv_layers.new(name="UVMap")
        for poly in me.polygons:
            for li in poly.loop_indices:
                layer.data[li].uv = uvs[me.loops[li].vertex_index]
    me.validate()
    me.update()
    obj = bpy.data.objects.new(name, me)
    if mat:
        obj.data.materials.append(mat)
    return link(obj)


def aim_rotation(src, dst):
    """Euler rotation turning an object's -Z (a light's axis) from src toward dst (Blender coords)."""
    from mathutils import Vector
    d = Vector(dst) - Vector(src)
    return d.to_track_quat("-Z", "Y").to_euler()


# ───────────────────────────── file writers ─────────────────────────────

def dither(shape, seed):
    """Triangular dither of ±1 code value, so an 8-bit glow ramp never bands."""
    rng = np.random.default_rng(seed)
    return (rng.random(shape) - rng.random(shape)) / 255.0


def save_png(path, rgba, seed=0, srgb_encode=False, dither_rgb=True):
    """rgba: float array (h, w, 4) top row first, 0..1. Written straight alpha, 8-bit.

    Dither goes on alpha always, and on colour unless the colour is a flat
    tint (a white light sprite): noise in a constant channel only costs bytes.
    """
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    a = np.asarray(rgba, dtype=np.float64)
    h, w, _ = a.shape
    if srgb_encode:
        c = a[..., :3]
        a = a.copy()
        a[..., :3] = np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(np.clip(c, 0, None), 1 / 2.4) - 0.055)
    noise = dither(a.shape, seed)
    if not dither_rgb:
        noise[..., :3] = 0.0
    a = np.clip(a + noise, 0.0, 1.0)
    a = np.round(a * 255.0) / 255.0
    img = bpy.data.images.new(path.stem, w, h, alpha=True, float_buffer=False)
    img.colorspace_settings.name = "Non-Color"
    img.alpha_mode = "STRAIGHT"
    img.pixels.foreach_set(np.flipud(a).astype(np.float32).ravel())
    img.filepath_raw = str(path)
    img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img)


def save_float(path, rgb, fmt="OPEN_EXR"):
    """rgb: float array (h, w, 3) top row first, scene-linear. EXR half/ZIP, or Radiance HDR."""
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rgb = np.asarray(rgb, dtype=np.float32)
    h, w, _ = rgb.shape
    rgba = np.concatenate([rgb, np.ones((h, w, 1), np.float32)], axis=2)
    img = bpy.data.images.new(path.stem, w, h, alpha=False, float_buffer=True)
    img.colorspace_settings.name = "Non-Color"
    img.pixels.foreach_set(np.flipud(rgba).ravel())
    scene = bpy.context.scene
    settings = scene.render.image_settings
    settings.file_format = fmt
    if fmt == "OPEN_EXR":
        settings.color_depth = "16"
        settings.exr_codec = "ZIP"
    settings.color_mode = "RGB"
    img.save_render(str(path), scene=scene)
    bpy.data.images.remove(img)


def load_float(path):
    img = bpy.data.images.load(str(path))
    img.colorspace_settings.name = "Non-Color"
    w, h = img.size
    px = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    return np.flipud(px.reshape(h, w, 4))[..., :3].copy()


def equirect_dirs(w, h):
    """Unit directions for an equirect image, top row first; +Y up, -Z at the centre column."""
    u = (np.arange(w) + 0.5) / w
    v = (np.arange(h) + 0.5) / h
    phi = (u - 0.5) * 2 * np.pi              # azimuth, 0 at the centre
    theta = (0.5 - v) * np.pi                # elevation, +pi/2 at the top
    ph, th = np.meshgrid(phi, theta)
    x = np.cos(th) * np.sin(ph)
    y = np.sin(th)
    z = -np.cos(th) * np.cos(ph)
    return np.stack([x, y, z], axis=-1), th, ph


def args():
    return sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def write_json(path, data):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
