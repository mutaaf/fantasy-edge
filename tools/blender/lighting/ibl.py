"""Render the image-based light: what a ball on the fifty sees, lit for real.

    blender --background --factory-startup --python tools/blender/lighting/ibl.py -- [night dusk room] [--quick]

For each variant writes assets/actors/lighting/env/:
  <id>.exr                 2048x1024 scene-linear source (Three.js PMREM, Filament cmgen)
  <id>.hdr                 1024x512 Radiance, what RealityKit's EnvironmentResource loads
  <id>_irradiance.exr      64x32 cosine-convolved, as radiance (E / pi)
  <id>_specular_r40.exr    256x128 prefiltered at roughness 0.4, likewise r60, r80
and returns spherical harmonics (9 x RGB) for the manifest.

Exposure. The probe is scaled so the mean radiance of what lies below the
horizon - turf and stands, what actually lights a model - matches the probe
the stadium ships today (assets/src/env/stadium_night.hdr), so swapping it in
does not move the headset's exposure; the look changes, the level does not.
Lamps are clamped so a prefilter never turns eight hot pixels into sparkle.
"""
from __future__ import annotations

import math
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import common as C  # noqa: E402
import bpy  # noqa: E402
import numpy as np  # noqa: E402
import stage as S  # noqa: E402

OUT = C.OUT_LIGHT / "env"
CLAMP = 64.0
REFERENCE = C.ROOT / "assets" / "generated" / "lighting" / "stadium_night.hdr"


def luminance(img):
    return img[..., 0] * 0.2126 + img[..., 1] * 0.7152 + img[..., 2] * 0.0722


def solid_angles(w, h):
    _, th, _ = C.equirect_dirs(w, h)
    return (2 * np.pi / w) * (np.pi / h) * np.cos(th)


def below_mean(img):
    h, w, _ = img.shape
    _, th, _ = C.equirect_dirs(w, h)
    mask = th < math.radians(-5)
    wts = solid_angles(w, h) * mask
    return float((luminance(img) * wts).sum() / wts.sum())


def downsample(img, factor):
    h, w, c = img.shape
    return img[: h // factor * factor, : w // factor * factor].reshape(h // factor, factor, w // factor, factor, c).mean(axis=(1, 3))


def convolve(src, out_w, out_h, power=None):
    """power None: cosine (irradiance / pi). Otherwise a normalised cos^power lobe."""
    sh, sw, _ = src.shape
    sd, _, _ = C.equirect_dirs(sw, sh)
    sd = sd.reshape(-1, 3).astype(np.float32)
    dw = solid_angles(sw, sh).reshape(-1).astype(np.float32)
    L = src.reshape(-1, 3).astype(np.float32)
    od, _, _ = C.equirect_dirs(out_w, out_h)
    od = od.reshape(-1, 3).astype(np.float32)
    out = np.zeros((od.shape[0], 3), np.float32)
    for i in range(0, od.shape[0], 1024):
        cosm = np.clip(od[i:i + 1024] @ sd.T, 0.0, 1.0)
        if power is None:
            k = cosm * dw
            out[i:i + 1024] = (k @ L) / np.pi
        else:
            k = np.power(cosm, power) * dw
            k /= np.maximum(k.sum(axis=1, keepdims=True), 1e-12)
            out[i:i + 1024] = k @ L
    return out.reshape(out_h, out_w, 3)


def sh9(img):
    h, w, _ = img.shape
    d, _, _ = C.equirect_dirs(w, h)
    x, y, z = d[..., 0], d[..., 1], d[..., 2]
    basis = [0.282095 * np.ones_like(x), 0.488603 * y, 0.488603 * z, 0.488603 * x,
             1.092548 * x * y, 1.092548 * y * z, 0.315392 * (3 * z * z - 1), 1.092548 * x * z, 0.546274 * (x * x - y * y)]
    dw = solid_angles(w, h)
    return [[round(float((img[..., c] * b * dw).sum()), 6) for c in range(3)] for b in basis]


def probe_camera(scene, height, x=0.0, y=0.0):
    cd = bpy.data.cameras.new("probe")
    cd.type = "PANO"
    cd.panorama_type = "EQUIRECTANGULAR"
    cam = C.link(bpy.data.objects.new("probe", cd))
    cam.location = (x, y, height)
    cam.rotation_euler = (math.radians(90), 0, 0)
    scene.camera = cam
    return cam


def render(scene, name, w, samples):
    scene.render.resolution_x, scene.render.resolution_y = w, w // 2
    scene.render.resolution_percentage = 100
    scene.cycles.samples = samples
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.adaptive_threshold = 0.02
    scene.cycles.max_bounces = 4
    scene.cycles.use_denoising = True
    scene.render.image_settings.file_format = "OPEN_EXR"
    scene.render.image_settings.color_depth = "32"
    path = C.SCRATCH / f"probe_{name}.exr"
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    return C.load_float(path)


def room_stage():
    """A living room at night: warm lamp, cool window, a sofa, a rug. The
    tabletop variant, for clients with no environment estimate of their own."""
    scene = C.reset()
    wall = C.material("room_wall", color=(0.55, 0.50, 0.44), rough=0.9)
    floor = C.material("room_floor", color=(0.18, 0.11, 0.07), rough=0.45)
    ceiling = C.material("room_ceiling", color=(0.7, 0.68, 0.64), rough=0.95)
    sofa = C.material("room_sofa", color=(0.12, 0.13, 0.16), rough=0.95)
    rug = C.material("room_rug", color=(0.35, 0.22, 0.15), rough=1.0)
    hx, hy, hz = 2.8, 3.4, 2.6
    C.mesh_object("floor", [(-hx, -hy, 0), (hx, -hy, 0), (hx, hy, 0), (-hx, hy, 0)], [(0, 1, 2, 3)], floor)
    C.mesh_object("ceiling", [(-hx, -hy, hz), (hx, -hy, hz), (hx, hy, hz), (-hx, hy, hz)], [(0, 1, 2, 3)], ceiling)
    for name, pts in (("wall_n", [(-hx, hy, 0), (hx, hy, 0), (hx, hy, hz), (-hx, hy, hz)]),
                      ("wall_s", [(-hx, -hy, 0), (hx, -hy, 0), (hx, -hy, hz), (-hx, -hy, hz)]),
                      ("wall_e", [(hx, -hy, 0), (hx, hy, 0), (hx, hy, hz), (hx, -hy, hz)]),
                      ("wall_w", [(-hx, -hy, 0), (-hx, hy, 0), (-hx, hy, hz), (-hx, -hy, hz)])):
        C.mesh_object(name, pts, [(0, 1, 2, 3)], wall)
    C.mesh_object("rug", [(-1.4, -1.8, 0.01), (1.4, -1.8, 0.01), (1.4, 1.2, 0.01), (-1.4, 1.2, 0.01)], [(0, 1, 2, 3)], rug)
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, -2.4, 0.4))
    s = bpy.context.object
    s.scale = (2.2, 0.9, 0.8)
    s.data.materials.append(sofa)
    window = C.material("room_window", color=(0, 0, 0), emit=(0.10, 0.14, 0.24), emit_strength=0.6)
    C.mesh_object("window", [(hx - 0.01, -0.8, 0.9), (hx - 0.01, 1.4, 0.9), (hx - 0.01, 1.4, 2.1), (hx - 0.01, -0.8, 2.1)],
                  [(0, 1, 2, 3)], window)
    lamp = bpy.data.lights.new("lamp", "POINT")
    lamp.energy = 120.0
    lamp.shadow_soft_size = 0.2
    lamp.color = (1.0, 0.72, 0.45)                    # about 2700 K
    C.link(bpy.data.objects.new("lamp", lamp)).location = (-2.2, 2.6, 1.55)
    shade = C.material("lampshade", color=(0.9, 0.8, 0.6), rough=1.0, emit=(1.0, 0.75, 0.5), emit_strength=3.0)
    bpy.ops.mesh.primitive_cylinder_add(radius=0.22, depth=0.3, location=(-2.2, 2.6, 1.55))
    bpy.context.object.data.materials.append(shade)
    w = bpy.data.worlds.new("room_world")
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs["Color"].default_value = (0, 0, 0, 1)
    scene.world = w
    return scene


def variant(name, quick, reuse=False):
    t0 = time.time()
    if reuse:
        vid = "tabletop_room" if name == "room" else f"stadium_{name}"
        img = C.load_float(C.SCRATCH / f"probe_{vid}.exr")
        return finish(name, vid, img, img.shape[1], 0, t0)
    if name == "room":
        scene = room_stage()
        probe_camera(scene, 0.45)
        w, samples, vid = (1024 if quick else 2048), (48 if quick else 256), "tabletop_room"
    else:
        scene, placed, source = S.build(sky=name, lod="hero")
        # Between the 50 and the 45, a stride off the centre line: sat exactly
        # on a painted line, the line fills the probe's whole nadir and every
        # model is lit white from below.
        probe_camera(scene, 1.5, x=2.5 * C.YD, y=1.2)
        w, samples, vid = (1024 if quick else 2048), (64 if quick else 384), f"stadium_{name}"
    img = render(scene, vid, w, samples)
    return finish(name, vid, img, w, samples, t0)


def finish(name, vid, img, w, samples, t0):
    raw_below = below_mean(img)
    if not REFERENCE.exists():
        raise SystemExit(f"[lighting] reference probe missing at {REFERENCE}; refusing to guess an exposure")
    target = below_mean(C.load_float(REFERENCE))
    if name == "room":
        target *= 0.6          # a lamp-lit room is dimmer than a floodlit bowl
    scale = target / max(raw_below, 1e-9)
    img = np.minimum(img * scale, CLAMP)
    src = img if img.shape[1] == 2048 else np.repeat(np.repeat(img, 2, axis=0), 2, axis=1)
    C.save_float(OUT / f"{vid}.exr", src)
    rt = downsample(src, 2)
    C.save_float(OUT / f"{vid}.hdr", rt, fmt="HDR")
    small = downsample(src, 8)                                    # 256 x 128
    C.save_float(OUT / f"{vid}_irradiance.exr", convolve(small, 64, 32))
    for rough, power in ((40, 3050.0), (60, 117.0), (80, 10.0)):
        C.save_float(OUT / f"{vid}_specular_r{rough}.exr", convolve(small, 256, 128, power))
    stats = {
        "id": vid,
        "seconds": round(time.time() - t0, 1),
        "renderWidth": w,
        "samples": samples,
        "exposureScale": round(scale, 6),
        "belowHorizonMean": round(below_mean(img), 5),
        "referenceBelowMean": round(target, 5),
        "peak": round(float(img.max()), 3),
        "clamp": CLAMP,
        "sh9": sh9(small),
    }
    C.write_json(C.SCRATCH / f"ibl_{vid}.json", stats)
    print(f"[lighting] probe {vid}: {stats['seconds']} s, scale {scale:.4g}, below {stats['belowHorizonMean']}, peak {stats['peak']}")
    return stats


def main():
    a = C.args()
    quick = "--quick" in a
    reuse = "--reuse" in a          # reprocess the last raw renders in .work without rendering
    names = [x for x in a if not x.startswith("--")] or ["night", "dusk", "room"]
    for n in names:
        variant(n, quick, reuse)


main()
