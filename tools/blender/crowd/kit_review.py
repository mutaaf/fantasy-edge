"""Review render of the shipped kit, tinted exactly as the runtime tints it.

Imports lod0_poses.glb, applies fan_albedo x mix(1, chip, mask) with a sample
club, and renders a seated row close up. What this shows is what the app gets:
if a collar or a sleeve leaks, it leaks here first, without a simulator.

    blender --background --python tools/blender/crowd/kit_review.py
"""
import math
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import bpy

import common

CHIP = (0.10, 0.25, 0.75, 1)          # a strong club blue, linear
SECONDARY = (0.62, 0.60, 0.55, 1)


def main():
    common.reset()
    kit = common.OUT
    bpy.ops.import_scene.gltf(filepath=str(kit / "lod0_poses.glb"))
    albedo = bpy.data.images.load(str(kit / "fan_albedo.png"))
    mask = bpy.data.images.load(str(kit / "fan_mask.png"))
    mask.colorspace_settings.name = "Non-Color"
    mat = bpy.data.materials.new("kit")
    nt = mat.node_tree
    nt.nodes.clear()
    N, L = nt.nodes, nt.links
    out = N.new("ShaderNodeOutputMaterial")
    bsdf = N.new("ShaderNodeBsdfPrincipled"); bsdf.inputs["Roughness"].default_value = 0.85
    ta = N.new("ShaderNodeTexImage"); ta.image = albedo
    tm = N.new("ShaderNodeTexImage"); tm.image = mask
    sep = N.new("ShaderNodeSeparateColor"); L.new(tm.outputs["Color"], sep.inputs[0])
    prim = N.new("ShaderNodeMix"); prim.data_type = "RGBA"; prim.blend_type = "MULTIPLY"; prim.inputs[7].default_value = CHIP
    L.new(sep.outputs[0], prim.inputs["Factor"]); L.new(ta.outputs["Color"], prim.inputs[6])
    sec = N.new("ShaderNodeMix"); sec.data_type = "RGBA"; sec.blend_type = "MULTIPLY"; sec.inputs[7].default_value = SECONDARY
    L.new(sep.outputs[1], sec.inputs["Factor"]); L.new(prim.outputs[2], sec.inputs[6])
    L.new(sec.outputs[2], bsdf.inputs["Base Color"])
    L.new(bsdf.outputs[0], out.inputs["Surface"])
    poses = [o for o in bpy.context.scene.objects if o.type == "MESH" and o.name.endswith("_sit")]
    poses.sort(key=lambda o: o.name)
    for o in bpy.context.scene.objects:
        if o.type == "MESH" and o not in poses[:12]:
            o.hide_render = True
    for i, o in enumerate(poses[:12]):
        o.data.materials.clear(); o.data.materials.append(mat)
        col, row = i % 6, i // 6
        o.location = ((col - 2.5) * 0.9, row * 1.1, row * 0.55)
        o.rotation_euler = (math.radians(90), 0, 0)      # glTF Y-up back to Blender Z-up
    sc = bpy.context.scene
    for name, loc, rot, e in (("key", (3, -6, 5), (55, 0, 25), 1500), ("fill", (-4, -3, 3), (60, 0, -50), 500)):
        l = bpy.data.lights.new(name, "AREA"); l.energy = e; l.size = 5
        ob = bpy.data.objects.new(name, l); sc.collection.objects.link(ob)
        ob.location = loc; ob.rotation_euler = tuple(math.radians(a) for a in rot)
    common.review_render(common.REVIEW / "kit_tinted.png", 2400, 1300, (0, -6.2, 2.2), (math.radians(78), 0, 0),
                         engine="BLENDER_EEVEE")
    print("wrote kit_tinted.png")


main()
