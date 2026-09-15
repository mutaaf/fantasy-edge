"""Prove the equirect convention end to end before any probe is trusted.

    blender --background --factory-startup --python tools/blender/lighting/orient.py

Two checks, both against the convention in textures.py (centre column = scene
-Z, +X a quarter turn right):
  1. the probe camera: a marker placed at scene -Z lands on the centre column
     and one at scene +X at u = 0.75;
  2. the sky lookup in stage.world: a marker painted at u = 0.5 / 0.75 of an
     equirect is seen by that camera at the same u.
Exits non-zero on a mismatch, so build.py stops before writing a mirrored probe.
"""
from __future__ import annotations

import math
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import common as C  # noqa: E402
import bpy  # noqa: E402
import numpy as np  # noqa: E402
import stage as S  # noqa: E402

W, H = 256, 128


def pano(scene, height=1.5):
    cd = bpy.data.cameras.new("probe")
    cd.type = "PANO"
    cd.panorama_type = "EQUIRECTANGULAR"
    cam = C.link(bpy.data.objects.new("probe", cd))
    cam.location = (0, 0, height)
    cam.rotation_euler = (math.radians(90), 0, 0)      # looks along Blender +Y = scene -Z
    scene.camera = cam
    return cam


def render(scene, name):
    scene.render.resolution_x, scene.render.resolution_y = W, H
    scene.cycles.samples = 2
    scene.cycles.use_denoising = False
    scene.render.image_settings.file_format = "OPEN_EXR"
    path = C.SCRATCH / f"{name}.exr"
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    return C.load_float(path)


def centre_u(img, ch):
    xs = np.nonzero(img[..., ch] > 1)[1]
    return (xs.mean() + 0.5) / W if len(xs) else -1.0


def main():
    failures = []
    scene = C.reset()
    w = bpy.data.worlds.new("black")
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs["Color"].default_value = (0, 0, 0, 1)
    scene.world = w
    for name, loc, col in (("red", C.to_blender(50, 1.5 / C.YD, -60), (1, 0, 0)),
                           ("green", C.to_blender(110, 1.5 / C.YD, 0), (0, 1, 0))):
        bpy.ops.mesh.primitive_cube_add(size=6, location=loc)
        bpy.context.object.data.materials.append(C.material(name, color=(0, 0, 0), emit=col, emit_strength=5))
    pano(scene)
    img = render(scene, "orient_camera")
    for ch, want in ((0, 0.5), (1, 0.75)):
        got = centre_u(img, ch)
        if abs(got - want) > 0.02:
            failures.append(f"camera channel {ch}: u {got:.3f}, want {want}")

    marker = np.zeros((H, W, 3), np.float32)
    marker[60:68, 126:130] = (5, 0, 0)
    marker[60:68, 190:194] = (0, 5, 0)
    sky_dir = C.SCRATCH / "orient_sky"
    C.save_float(sky_dir / "env" / "sky_marker.exr", marker)
    scene = C.reset()
    saved = C.OUT_SKY
    C.OUT_SKY = sky_dir
    try:
        S.world("marker")
    finally:
        C.OUT_SKY = saved
    pano(scene)
    img = render(scene, "orient_world")
    for ch, want in ((0, 0.5), (1, 0.75)):
        got = centre_u(img, ch)
        if abs(got - want) > 0.02:
            failures.append(f"sky lookup channel {ch}: u {got:.3f}, want {want}")

    if failures:
        print("[lighting] ORIENTATION FAILED: " + "; ".join(failures))
        sys.exit(1)
    print("[lighting] orientation ok: camera and sky lookup agree with the equirect convention")


main()
