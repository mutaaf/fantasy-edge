"""Review render: four fans in every impostor pose, plus the prop poses.

    blender --background --python tools/blender/crowd/pose_review.py
"""
import math
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import bpy

import common
import poses as P
import rig as R
import specs

SHOW = P.IMPOSTOR_POSES + ["pump_a", "towel_1", "phone", "semi"]


def lights():
    sc = bpy.context.scene
    for name, loc, rot, e, s in (("key", (4, -9, 8), (50, 0, 20), 9000, 10), ("rim", (-3, 8, 5), (-120, 0, 0), 3500, 10)):
        l = bpy.data.lights.new(name, "AREA"); l.energy = e; l.size = s
        o = bpy.data.objects.new(name, l); sc.collection.objects.link(o)
        o.location = loc; o.rotation_euler = tuple(math.radians(a) for a in rot)


def main():
    common.reset()
    cast = specs.cast()
    picks = [cast[i] for i in (0, 5, 9, 16)]
    for col, pose in enumerate(SHOW):
        for row, f in enumerate(picks):
            mesh, rig, _ = R.assemble(f)
            rig.location = ((col - (len(SHOW) - 1) / 2) * 1.05, 0.3 * (col % 2), (len(picks) - 1 - row) * 2.35)
            P.apply_pose(rig, pose, f["height"], cast.index(f))
    lights()
    sc = bpy.context.scene
    common.review_render(common.REVIEW / "poses_front.png", 3000, 2250, (0, -40, 4.6), (math.radians(90), 0, 0),
                         ortho=13.4, engine="CYCLES", samples=20)
    cam = sc.camera
    cam.location = (26, -30, 12); cam.rotation_euler = (math.radians(78), 0, math.radians(40)); cam.data.ortho_scale = 15
    sc.render.filepath = str(common.REVIEW / "poses_three_quarter.png")
    bpy.ops.render.render(write_still=True)
    print("tris", {f["id"]: R.triangles(bpy.data.objects[f["id"]]) for f in picks})


main()
