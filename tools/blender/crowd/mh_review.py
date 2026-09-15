"""Review: six MPFB fans, seated and cheering, lit and shot at 1.2 m.

    blender --background --python tools/blender/crowd/mh_review.py -- [indexes]
"""
import math, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import bpy
import common, mh, poses as P, specs

def lit(mat):
    nt = mat.node_tree
    for em in [n for n in nt.nodes if n.type == "EMISSION"]:
        bs = nt.nodes.new("ShaderNodeBsdfPrincipled"); bs.inputs["Roughness"].default_value = 0.7
        if em.inputs["Color"].links:
            nt.links.new(em.inputs["Color"].links[0].from_socket, bs.inputs["Base Color"])
        else:
            bs.inputs["Base Color"].default_value = em.inputs["Color"].default_value
        for l in list(em.outputs[0].links):
            nt.links.new(bs.outputs[0], l.to_socket)

def main():
    common.reset()
    cast = specs.cast()
    picks = [int(a) for a in common.args()] or [0, 3, 5, 9, 14, 22]
    for col, i in enumerate(picks):
        f = cast[i]
        for row, pose in enumerate(["sit", "cheer_a"]):
            mesh, rig, J, info = mh.assemble(f, i)
            print("fan", i, info["identity"]["female"], info["identity"]["age"], info["identity"]["ancestry"], info["suit"], info["hair"], round(info["height"], 2), len(mesh.data.polygons))
            for slot in mesh.material_slots:
                if slot.material and slot.material.name.endswith("_base"):
                    lit(slot.material)
            P.apply_pose(rig, pose, info["height"], i)
            rig.location = ((col - (len(picks) - 1) / 2) * 0.95, row * 1.6, 0)
    sc = bpy.context.scene
    for name, loc, rot, e in (("key", (2, -4, 5), (50, 0, 20), 900), ("fill", (-3, -3, 2), (70, 0, -50), 250), ("rim", (0, 5, 4), (-120, 0, 0), 500)):
        l = bpy.data.lights.new(name, "AREA"); l.energy = e; l.size = 3
        o = bpy.data.objects.new(name, l); sc.collection.objects.link(o); o.location = loc; o.rotation_euler = tuple(math.radians(a) for a in rot)
    common.review_render(common.REVIEW / "mh_lineup.png", 2800, 1400, (0, -6.5, 1.3), (math.radians(86), 0, 0), engine="BLENDER_EEVEE")
    cam = sc.camera
    cam.data.lens = 50; cam.location = (picks and (0 - (len(picks) - 1) / 2) * 0.95 or 0, -1.2, 0.95); cam.rotation_euler = (math.radians(88), 0, 0)
    sc.render.resolution_x, sc.render.resolution_y = 1400, 1400
    sc.render.filepath = str(common.REVIEW / "mh_closeup.png"); bpy.ops.render.render(write_still=True)
    print("done")

main()
