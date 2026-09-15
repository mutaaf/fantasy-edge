"""Review render: all 24 fans in rest pose, lit, with sample club colours.

    blender --background --python tools/blender/crowd/lineup.py
"""
import math
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import bpy
from mathutils import Vector

import common
import fan as F
import specs


def build_static(f, x_offset):
    J = F.joints(f)
    parts = []
    b = F.body(f, J); F.paint_body(b, f, J); parts.append((b, None))
    h, c = F.head(f, J); F.paint_head(h, f, c); parts.append((h, c))
    hr = F.hair(f, c)
    if hr:
        F.paint_flat(hr, F.hex_rgb(f["hair_colour"])); parts.append((hr, None))
    ht = F.hat(f, c)
    if ht:
        F.paint_flat(ht, F.TINTED, (0, 1, 0) if f["hat"] == "beanie" else (1, 0, 0)); parts.append((ht, None))
    pr = F.accessory(f, J)
    if pr:
        F.paint_prop(pr, f["accessory"]); parts.append((pr, None))
    for ob, centre in parts:
        mat = common.attr_material(f"{ob.name}_m", centre, f["paint"] if centre is not None else "none", mode="lit")
        ob.data.materials.append(mat)
        ob.location.x += x_offset
    return parts


def main():
    common.reset()
    fans = specs.cast()
    for i, f in enumerate(fans):
        build_static(f, (i - 11.5) * 0.75)
    sc = bpy.context.scene
    key = bpy.data.lights.new("key", "AREA"); key.energy = 9000; key.size = 12
    ko = bpy.data.objects.new("key", key); sc.collection.objects.link(ko)
    ko.location = (0, -10, 8); ko.rotation_euler = (math.radians(50), 0, 0)
    rim = bpy.data.lights.new("rim", "AREA"); rim.energy = 4000; rim.size = 10
    ro = bpy.data.objects.new("rim", rim); sc.collection.objects.link(ro)
    ro.location = (0, 8, 5); ro.rotation_euler = (math.radians(-120), 0, 0)
    out = common.REVIEW / "lineup_front.png"
    common.review_render(out, 3200, 560, (0, -30, 1.0), (math.radians(90), 0, 0), ortho=18.2, engine="CYCLES", samples=24)
    # A closer look at the first six, where faces and props are judged.
    sc.camera.data.ortho_scale = 4.6
    sc.camera.location = (-6.7, -30, 1.1)
    sc.render.resolution_x, sc.render.resolution_y = 2400, 1200
    sc.render.filepath = str(common.REVIEW / "lineup_close.png")
    bpy.ops.render.render(write_still=True)
    print("wrote", out)


main()
