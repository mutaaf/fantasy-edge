"""Assemble a fan: parts, materials, one joined mesh, skeleton and weights.

Weights come from distance, not from Blender's bone-heat solver. Heat fails
silently on meshes made of separate shells (a hat, a phone), and a crowd
kit can't have one fan out of 24 that folds in half. Each body vertex takes
a Gaussian of its distance to every bone segment, keeps the strongest three,
and normalises. Head shells follow the head, props follow the right hand.
"""
from __future__ import annotations

import math

import bpy
from mathutils import Vector
from mathutils.geometry import intersect_point_line

import common
import fan as F

SIGMA = {"hips": 0.10, "spine": 0.09, "chest": 0.075, "neck": 0.05, "head": 0.08,
         "clavicle": 0.035, "upperarm": 0.06, "forearm": 0.05, "hand": 0.04,
         "thigh": 0.07, "shin": 0.055, "foot": 0.045}


def assemble(f: dict, mode: str = "lit"):
    """Build every part of fan `f`, joined into one mesh with a material per part."""
    J = F.joints(f)
    parts = []
    b = F.body(f, J); F.paint_body(b, f, J); parts.append((b, None, "body"))
    h, c = F.head(f, J); F.paint_head(h, f, c); parts.append((h, c, "head"))
    hr = F.hair(f, c)
    if hr:
        F.paint_flat(hr, F.hex_rgb(f["hair_colour"])); parts.append((hr, None, "head"))
    ht = F.hat(f, c)
    if ht:
        F.paint_flat(ht, F.TINTED, (0, 1, 0) if f["hat"] == "beanie" else (1, 0, 0)); parts.append((ht, None, "head"))
    sc = F.scarf(f, J)
    if sc:
        F.paint_scarf(sc, f); parts.append((sc, None, "chest"))
    pr = F.accessory(f, J)
    if pr:
        F.paint_prop(pr, f["accessory"]); parts.append((pr, None, "hand.R"))
    for ob, centre, owner in parts:
        ob["owner"] = owner
        mat = common.attr_material(f"{ob.name}_{mode}", centre, f["paint"] if centre is not None else "none", mode=mode)
        ob.data.materials.append(mat)
        # Record which bone owns each vertex before the parts are merged.
        grp = ob.data.attributes.new("owner_is_body", "INT", "POINT")
        for i in range(len(ob.data.vertices)):
            grp.data[i].value = 1 if owner == "body" else 0
        own = ob.data.attributes.new("owner_bone", "INT", "POINT")
        idx = [n for n, *_ in F.BONES].index(owner) if owner != "body" else -1
        for i in range(len(ob.data.vertices)):
            own.data[i].value = idx
    bpy.ops.object.select_all(action="DESELECT")
    for ob, *_ in parts:
        ob.select_set(True)
    bpy.context.view_layer.objects.active = parts[0][0]
    bpy.ops.object.join()
    mesh = parts[0][0]
    mesh.name = f"{f['id']}"
    mesh.data.name = f"{f['id']}"
    rig = F.make_armature(f, J)
    skin(mesh, rig)
    return mesh, rig, J


def skin(mesh, rig):
    bones = [(pb.name, pb.bone.head_local.copy(), pb.bone.tail_local.copy()) for pb in rig.pose.bones]
    names = [n for n, *_ in F.BONES]
    groups = {n: mesh.vertex_groups.new(name=n) for n in names if n != "root"}
    is_body = mesh.data.attributes["owner_is_body"].data
    owner = mesh.data.attributes["owner_bone"].data
    for v in mesh.data.vertices:
        if not is_body[v.index].value:
            groups[names[owner[v.index].value]].add([v.index], 1.0, "REPLACE")
            continue
        scores = []
        for name, hd, tl in bones:
            if name == "root":
                continue
            p, t = intersect_point_line(v.co, hd, tl)
            t = max(0.0, min(1.0, t))
            d = (v.co - (hd + (tl - hd) * t)).length
            s = SIGMA[name.split(".")[0]]
            scores.append((math.exp(-(d / s) ** 2), name))
        scores.sort(reverse=True)
        top = [x for x in scores[:3] if x[0] > 1e-4] or scores[:1]
        total = sum(w for w, _ in top)
        for w, name in top:
            groups[name].add([v.index], w / total, "REPLACE")
    mod = mesh.modifiers.new("rig", "ARMATURE")
    mod.object = rig
    mesh.parent = rig


def triangles(ob) -> int:
    return sum(len(p.vertices) - 2 for p in ob.data.polygons)
