"""Model every sideline and field prop, and export .usdz with a .glb twin.

Authored in metres, Blender Z-up, origin on the ground at the prop's base
centre. Local +X runs along the sideline (field length), local +Y points toward
the field of play. Both exporters convert to Y-up, where "toward the field"
becomes -Z; a renderer places a prop by its base and turns it to face the field.

Each prop is written at three levels of detail:

  assets/actors/sideline/<id>.usdz / .glb          LOD0, stadium seat and closer
  assets/actors/sideline/<id>_lod1.usdz / .glb     LOD1, the far side of the bowl
  assets/actors/sideline/<id>_lod2.usdz / .glb     LOD2, the tabletop

Dimensions come from tools/blender/field/rules.py (rulebook values) wherever a
rule sets one; everything else is measured from the real article and noted.
Materials are glTF/UsdPreviewSurface factors plus two generated textures (net,
pad fabric), and at most three materials per prop so a prop costs at most three
draw parts. Materials named `tint_*` are meant to be recoloured at runtime from
the scene's team chips.

    blender -b --factory-startup --python tools/blender/field/build.py            # all
    blender -b --factory-startup --python tools/blender/field/build.py -- pylon   # one
"""
from __future__ import annotations

import json
import math
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import common  # noqa: E402
import rules  # noqa: E402

import bpy  # noqa: E402
import bmesh  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Vector, Matrix  # noqa: E402

M_FT, M_IN, M_YD = common.FOOT, common.INCH, common.YARD
OUT = common.SIDELINE_OUT
TEX = OUT / "textures"
LODS = {0: 1.0, 1: 0.45, 2: 0.14}


# ───────────────────────────── materials ─────────────────────────────

_MATS: dict[str, bpy.types.Material] = {}

# One small library every prop draws from. The sideline actor merges every
# static prop into one mesh per material, so the number of materials here is
# the number of draw parts the whole team area costs.
PALETTE = {
    "prop_gold":   ("#F5B800", 0.35, 0.15),   # goal posts
    "prop_white":  ("#EDEDE8", 0.55, 0.0),    # chain rods, table tops, cup sleeves
    "prop_steel":  ("#A6ABB1", 0.35, 0.85),   # aluminium, scaffold, frames, poles
    "prop_dark":   ("#26292E", 0.5, 0.25),    # camera bodies, cases, heater shells
    "prop_black":  ("#0E1013", 0.6, 0.0),     # rubber, grills, lenses, screens, digits
    "prop_orange": ("#FF5A00", 0.62, 0.0),    # pylons, chain vanes, markers, ribbons, heater glow
    "prop_blue":   ("#1F5FB8", 0.45, 0.0),    # cooler lids, bins, bean bags
    "prop_yellow": ("#FFD100", 0.8, 0.0),     # penalty flags, cable ramps
    "tint_team_primary":   ("#26303C", 0.6, 0.0),   # pads, bench seats and backs
    "tint_team_secondary": ("#1C3E77", 0.8, 0.0),   # tents
}
ALIASES = {
    "prop_goalpost_gold": "prop_gold", "prop_goalpost_white": "prop_white",
    "prop_ribbon": "prop_orange", "prop_pylon": "prop_orange", "prop_pylon_lens": "prop_black",
    "prop_pylon_foot": "prop_black", "prop_chain_pole": "prop_white", "prop_chain_vane": "prop_orange",
    "prop_chain_steel": "prop_steel", "prop_down_digit": "prop_black", "prop_ground_marker": "prop_orange",
    "prop_bench_aluminium": "prop_steel", "tint_team_primary_bench": "tint_team_primary",
    "prop_heater_shell": "prop_dark", "prop_heater_grill": "prop_black", "prop_heater_glow": "prop_orange",
    "prop_table_top": "prop_white", "prop_table_legs": "prop_steel", "prop_cooler_lid": "prop_blue",
    "tint_team_secondary_tent": "tint_team_secondary", "prop_tent_frame": "prop_steel",
    "prop_tablet_case": "prop_dark", "prop_tablet_screen": "prop_black", "prop_camera_body": "prop_dark",
    "prop_camera_metal": "prop_steel", "prop_camera_glass": "prop_black", "prop_cable_rubber": "prop_black",
    "prop_cable_ramp": "prop_yellow", "prop_scaffold_steel": "prop_steel", "prop_scaffold_deck": "prop_dark",
    "prop_net_pole": "prop_steel", "prop_kicknet_frame": "prop_dark", "prop_football_leather": "prop_dark",
    "prop_beanbag": "prop_blue", "prop_penalty_flag": "prop_yellow", "review_mannequin": "prop_steel",
}


def mat(name, base=None, rough=0.5, metal=0.0, emission=None):
    """A library material by role. The colour arguments of older call sites
    are ignored on purpose: a prop does not get a material of its own."""
    key = ALIASES.get(name, name)
    if key not in PALETTE:
        raise KeyError(f"{name!r} is not in the prop palette")
    if key in _MATS:
        return _MATS[key]
    hexs, r, mtl = PALETTE[key]
    m = common.material(key, base=common.hex_linear(hexs), rough=r, metal=mtl)
    _MATS[key] = m
    return m


def textured_mat(name, image_path, rough=0.8, alpha=False, tint="#FFFFFF"):
    if name in _MATS:
        return _MATS[name]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    img = nt.nodes.new("ShaderNodeTexImage")
    img.image = bpy.data.images.load(str(image_path))
    bsdf.inputs["Base Color"].default_value = (*common.hex_linear(tint), 1)
    nt.links.new(img.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = rough
    if alpha:
        nt.links.new(img.outputs["Alpha"], bsdf.inputs["Alpha"])
        m.surface_render_method = "DITHERED"
    _MATS[name] = m
    return m


def make_textures():
    """The net and pad textures, generated so the models carry no downloads."""
    TEX.mkdir(parents=True, exist_ok=True)
    # knotted netting: 2 inch square mesh seen at 256 px for a 0.6 m repeat
    n = 256
    y, x = np.mgrid[0:n, 0:n] / n * 12.0                 # 12 cells per repeat
    fx, fy = np.abs(np.mod(x, 1) - 0.5), np.abs(np.mod(y, 1) - 0.5)
    strand = np.clip(1 - np.minimum(fx, fy) / 0.06, 0, 1) ** 1.5
    knots = np.clip(1 - np.hypot(fx - 0.5, fy - 0.5) / 0.12, 0, 1)
    a = np.clip(strand + knots, 0, 1)
    common.write_png(TEX / "net.png", np.stack([np.full_like(a, 0.92), np.full_like(a, 0.92), np.full_like(a, 0.9), a], axis=2))
    # quilted pad vinyl: stitched panels with a soft sheen
    n = 256
    y, x = np.mgrid[0:n, 0:n] / n
    seam = np.clip(1 - np.abs(np.mod(y * 4, 1) - 0.5) / 0.03, 0, 1)
    grain = common.rng(9).random((n, n)) * 0.04
    v = 0.85 - 0.25 * seam + grain
    navy = np.array([0.16, 0.20, 0.27])            # sRGB; a runtime tint replaces it
    common.write_png(TEX / "pad.png", v[..., None] * navy)


# ───────────────────────────── geometry helpers ─────────────────────────────

def _link(obj, material):
    bpy.context.scene.collection.objects.link(obj)
    obj.data.materials.append(material)
    return obj


def box(size, loc, material, bevel=0.0, rot=(0, 0, 0)):
    mesh = bpy.data.meshes.new("box")
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=Vector(size), verts=bm.verts)
    if bevel > 0:
        bmesh.ops.bevel(bm, geom=list(bm.edges) + list(bm.verts), offset=bevel, segments=1 if min(size) < 0.08 else 2, affect="EDGES")
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new("box", mesh)
    obj.location = loc
    obj.rotation_euler = rot
    return _link(obj, material)


def cylinder(radius, depth, loc, material, verts=12, rot=(0, 0, 0), cap=True, radius2=None):
    mesh = bpy.data.meshes.new("cyl")
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=cap, cap_tris=False, segments=verts, radius1=radius,
                          radius2=radius if radius2 is None else radius2, depth=depth)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new("cyl", mesh)
    obj.location = loc
    obj.rotation_euler = rot
    return _link(obj, material)


def sphere(radius, loc, material, segs=10, rings=6, scale=(1, 1, 1)):
    mesh = bpy.data.meshes.new("sph")
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=segs, v_segments=rings, radius=radius)
    bmesh.ops.scale(bm, vec=Vector(scale), verts=bm.verts)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new("sph", mesh)
    obj.location = loc
    return _link(obj, material)


def tube(points, radius, material, sides=10, resolution=6):
    """A pipe along a polyline, smoothed as a Bezier."""
    cu = bpy.data.curves.new("tube", "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = radius
    cu.bevel_resolution = max(1, sides // 4 - 1)
    cu.resolution_u = resolution
    cu.use_fill_caps = True
    sp = cu.splines.new("BEZIER")
    sp.bezier_points.add(len(points) - 1)
    for bp, p in zip(sp.bezier_points, points):
        bp.co = p
        bp.handle_left_type = bp.handle_right_type = "AUTO"
    obj = bpy.data.objects.new("tube", cu)
    bpy.context.scene.collection.objects.link(obj)
    obj.data.materials.append(material)
    return to_mesh(obj)


def plane(size, loc, material, rot=(0, 0, 0), uv_repeat=(1, 1)):
    mesh = bpy.data.meshes.new("plane")
    w, h = size
    mesh.from_pydata([(-w / 2, 0, 0), (w / 2, 0, 0), (w / 2, 0, h), (-w / 2, 0, h)], [], [(0, 1, 2, 3)])
    uv = mesh.uv_layers.new(name="UVMap")
    for li, (u, v) in zip(range(4), [(0, 0), (uv_repeat[0], 0), (uv_repeat[0], uv_repeat[1]), (0, uv_repeat[1])]):
        uv.data[li].uv = (u, v)
    obj = bpy.data.objects.new("plane", mesh)
    obj.location = loc
    obj.rotation_euler = rot
    return _link(obj, material)


def text_mesh(body, height, loc, material, rot=(0, 0, 0), extrude=0.004):
    font = bpy.data.fonts.load(str(common.FIELD_OUT / "fonts" / "Graduate-Regular.ttf"), check_existing=True)
    cu = bpy.data.curves.new("txt", "FONT")
    cu.body = body
    cu.font = font
    cu.size = height / 0.7
    cu.extrude = extrude
    cu.align_x = "CENTER"
    cu.align_y = "CENTER"
    cu.resolution_u = 3
    obj = bpy.data.objects.new("txt", cu)
    obj.location = loc
    obj.rotation_euler = rot
    bpy.context.scene.collection.objects.link(obj)
    obj.data.materials.append(material)
    return to_mesh(obj)


def to_mesh(obj):
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(obj.evaluated_get(dg))
    new = bpy.data.objects.new(obj.name + "_m", me)
    new.matrix_world = obj.matrix_world
    bpy.context.scene.collection.objects.link(new)
    bpy.data.objects.remove(obj)
    return new


def join(objs, name):
    for o in bpy.context.scene.objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.join()
    out = bpy.context.view_layer.objects.active
    out.name = name
    out.data.name = name
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    # merge material slots that share a material, so parts == unique materials
    bpy.ops.object.material_slot_remove_unused()
    for poly in out.data.polygons:
        poly.use_smooth = True
    return out


# ───────────────────────────── props ─────────────────────────────
# Each builder returns a list of objects; the exporter joins them.

def goalpost(league: str):
    """Single-standard slingshot goal. Base behind the end line, gooseneck up
    and forward, crossbar in the plane of the end line."""
    P = rules.PAINT[league]["goal"]
    scene_props = rules.RULES[league]["props"]["goalpost"]
    gold = mat("prop_gold" if P["color"] == "gold" else "prop_white")
    pad = mat("tint_team_primary")
    ribbon = mat("prop_ribbon", "#FF6A13", 0.8)
    back = scene_props["baseBehind"] * M_YD                   # base this far behind the end line
    crossbar_h = P["crossbar"] * M_YD
    width = P["width"] * M_YD
    above = P["uprightAbove"] * M_YD
    up_r = P["uprightDiameter"] * M_YD / 2 if "uprightDiameter" in P else 0.05
    objs = []
    base_r, neck_r = 0.115, 0.095
    base_top = crossbar_h - 0.95
    objs.append(cylinder(base_r, base_top, (0, -back, base_top / 2), gold, verts=16))
    objs.append(tube([(0, -back, base_top - 0.05), (0, -back, crossbar_h - 0.25), (0, -back * 0.45, crossbar_h + 0.05),
                      (0, 0, crossbar_h - 0.02)], neck_r, gold, sides=12, resolution=8))
    objs.append(cylinder(0.08, width, (0, 0, crossbar_h), gold, verts=14, rot=(0, math.pi / 2, 0)))
    for sx in (-1, 1):
        x = sx * width / 2
        objs.append(cylinder(up_r, above, (x, 0, crossbar_h + above / 2), gold, verts=10))
        objs.append(sphere(0.085, (x, 0, crossbar_h), gold, segs=10, rings=6))       # elbow sleeve
        rb = plane((0.1016, 1.0668), (x + 0.02, 0, crossbar_h + above - 1.02), ribbon, rot=(0.12, 0, 0.3 * sx))
        objs.append(rb)
    pad_h = max(P.get("padHeightMin", 6 * rules.FT), 6 * rules.FT) * M_YD
    objs.append(box((0.46, 0.46, pad_h), (0, -back, pad_h / 2), pad, bevel=0.06))
    return objs


def pylon(league: str):
    """4 x 4 x 18 in, orange, soft; camera ports as dark insets, no marks."""
    P = rules.PAINT[league]["pylons"]
    orange = mat("prop_pylon", "#FF5A00", 0.62)
    lens = mat("prop_pylon_lens", "#101216", 0.15, 0.0)
    s = P["size"] * M_YD
    gap = P.get("gapUnder", 0.0) * M_YD
    h = P["height"] * M_YD - gap
    objs = [box((s, s, h), (0, 0, gap + h / 2), orange, bevel=0.009)]
    if gap:
        foot = mat("prop_pylon_foot", "#202226", 0.9)
        objs.append(box((s * 0.9, s * 0.9, gap), (0, 0, gap / 2), foot, bevel=0.004))
    for k in range(4):
        a = k * math.pi / 2
        objs.append(box((0.034, 0.004, 0.022), (math.sin(a) * (s / 2 + 0.001), math.cos(a) * (s / 2 + 0.001), gap + h * 0.78),
                        lens, rot=(0, 0, -a)))
    return objs


def chain_set(league: str):
    """Two rods ten yards apart joined by the chain; the rods' inside edges
    are exactly 10 yd apart when the chain is taut (NCAA 1-2-7-a)."""
    P = rules.PAINT[league]["chains"]
    rod_h = max(P["rodHeightMin"] * M_YD, 2.1)
    pole = mat("prop_chain_pole", "#F4F4F0", 0.5)
    vane = mat("prop_chain_vane", "#FF5A00", 0.6)
    steel = mat("prop_chain_steel", "#8A8E94", 0.35, 0.9)
    half = 10 * M_YD / 2 + 0.025
    objs = []
    for sx in (-1, 1):
        objs.append(cylinder(0.025, rod_h, (sx * half, 0, rod_h / 2), pole, verts=10))
        objs.append(box((0.30, 0.02, 0.22), (sx * half, 0, rod_h - 0.12), vane, bevel=0.01))
        objs.append(cylinder(0.035, 0.05, (sx * half, 0, 0.025), steel, verts=10))   # flat end (1-2-7-e)
    # the chain sags between hands at about waist height
    pts = []
    links = 14
    for i in range(links + 1):
        t = i / links
        x = -half + t * 2 * half
        z = 0.95 - 0.28 * (1 - (2 * t - 1) ** 2)
        pts.append((x, 0, z))
    objs.append(tube(pts, 0.008, steel, sides=6, resolution=2))
    return objs


def down_marker(league: str):
    """The box: a rod with a four-sided flip card on top. The four digits are
    separate children named down_1..down_4; a renderer shows one."""
    P = rules.PAINT[league]["chains"]
    rod_h = max(P["rodHeightMin"] * M_YD, 2.1)
    pole = mat("prop_chain_pole", "#F4F4F0", 0.5)
    card = mat("prop_chain_vane", "#FF5A00", 0.6)
    digit = mat("prop_down_digit", "#101216", 0.6)
    objs = [cylinder(0.025, rod_h, (0, 0, rod_h / 2), pole, verts=10),
            box((0.36, 0.36, 0.34), (0, 0, rod_h + 0.17), card, bevel=0.015)]
    digits = []
    for d in range(1, 5):
        faces = []
        for k in range(4):
            a = k * math.pi / 2
            t = text_mesh(str(d), 0.26, (math.sin(a) * 0.184, -math.cos(a) * 0.184, rod_h + 0.17), digit,
                          rot=(math.pi / 2, 0, a), extrude=0.003)
            faces.append(t)
        dj = join(faces, f"down_{d}")
        digits.append(dj)
    return objs, digits


def ground_marker(league: str):
    """NCAA 1-2-7-d unofficial line-to-gain ground marker: 10 x 32 in with a
    5 in triangle toward the sideline."""
    G = rules.PAINT["college-football"]["chains"]["groundMarker"]
    orange = mat("prop_ground_marker", "#FF5A00", 0.75)
    w, l, tri = G["width"] * M_YD, G["length"] * M_YD, G["triangle"] * M_YD
    mesh = bpy.data.meshes.new("gm")
    hw = w / 2
    verts = [(-hw, 0, 0.012), (hw, 0, 0.012), (hw, l, 0.012), (0, l + tri, 0.012), (-hw, l, 0.012),
             (-hw, 0, 0), (hw, 0, 0), (hw, l, 0), (0, l + tri, 0), (-hw, l, 0)]
    faces = [(0, 1, 2, 3, 4), (9, 8, 7, 6, 5), (0, 5, 6, 1), (1, 6, 7, 2), (2, 7, 8, 3), (3, 8, 9, 4), (4, 9, 5, 0)]
    mesh.from_pydata(verts, [], faces)
    obj = bpy.data.objects.new("gm", mesh)
    obj.location = (0, -l / 2, 0)
    return [_link(obj, orange)]


def bench():
    """One 24 ft aluminium team bench with a backrest."""
    alu = mat("prop_bench_aluminium", "#B9BDC2", 0.35, 0.85)
    seat = mat("tint_team_primary_bench", "#27303C", 0.55)
    L = 7.3
    objs = [box((L, 0.30, 0.05), (0, 0, 0.46), seat, bevel=0.012),
            box((L, 0.05, 0.22), (0, -0.17, 0.72), seat, bevel=0.01),
            box((L, 0.12, 0.03), (0, 0.1, 0.18), alu, bevel=0.006)]
    for x in np.linspace(-L / 2 + 0.25, L / 2 - 0.25, 5):
        objs.append(box((0.05, 0.36, 0.04), (x, 0, 0.02), alu, bevel=0.006))
        objs.append(box((0.04, 0.04, 0.46), (x, 0.08, 0.23), alu, bevel=0.006))
        objs.append(box((0.04, 0.04, 0.84), (x, -0.17, 0.42), alu, bevel=0.006))
    return objs


def heater_fan():
    """A sideline forced-air heater on casters, a ducted hood toward the bench."""
    shell = mat("prop_heater_shell", "#2B2F35", 0.45, 0.4)
    grill = mat("prop_heater_grill", "#0D0F12", 0.7)
    glow = mat("prop_heater_glow", "#FF6A1A", 0.9, emission=common.hex_linear("#FF4A0A"))
    objs = [cylinder(0.30, 0.62, (0, 0, 0.48), shell, verts=20, rot=(math.pi / 2, 0, 0)),
            cylinder(0.26, 0.02, (0, 0.32, 0.48), grill, verts=20, rot=(math.pi / 2, 0, 0)),
            cylinder(0.20, 0.01, (0, 0.335, 0.48), glow, verts=16, rot=(math.pi / 2, 0, 0)),
            box((0.52, 0.42, 0.06), (0, 0, 0.13), shell, bevel=0.01)]
    for sx in (-1, 1):
        for sy in (-1, 1):
            objs.append(cylinder(0.04, 0.03, (sx * 0.2, sy * 0.15, 0.04), grill, verts=10, rot=(0, math.pi / 2, 0)))
    return objs


def cooler_station():
    """A folding table with two round drink coolers, cup sleeves and a bin.
    Generic: white bodies, blue lids, no marks."""
    top = mat("prop_table_top", "#E7E6E1", 0.7)
    legs = mat("prop_table_legs", "#6D7177", 0.4, 0.8)
    lid = mat("prop_cooler_lid", "#1F5FB8", 0.4)
    objs = [box((1.83, 0.76, 0.04), (0, 0, 0.74), top, bevel=0.01)]
    for sx in (-1, 1):
        objs.append(tube([(sx * 0.8, -0.3, 0.0), (sx * 0.8, -0.3, 0.72)], 0.014, legs, sides=6, resolution=1))
        objs.append(tube([(sx * 0.8, 0.3, 0.0), (sx * 0.8, 0.3, 0.72)], 0.014, legs, sides=6, resolution=1))
    for x in (-0.45, 0.25):
        objs.append(cylinder(0.19, 0.46, (x, 0, 0.99), top, verts=18))
        objs.append(cylinder(0.2, 0.06, (x, 0, 1.25), lid, verts=18))
        objs.append(box((0.05, 0.04, 0.04), (x, 0.2, 0.84), lid, bevel=0.008))                # spigot
    for i in range(3):
        objs.append(cylinder(0.04, 0.35, (0.72, -0.2 + i * 0.1, 0.94), top, verts=10, radius2=0.035))  # cup sleeves
    objs.append(cylinder(0.24, 0.8, (1.25, 0.1, 0.4), lid, verts=16, radius2=0.28))                     # bin
    return objs


def medical_tent():
    """A pop-up sideline medical tent, 3 x 2 m, sides down, blue."""
    canvas = mat("tint_team_secondary_tent", "#1C3E77", 0.8)
    frame = mat("prop_tent_frame", "#A8ADB3", 0.35, 0.8)
    w, d, h = 3.0, 2.0, 2.0
    objs = [box((w, 0.02, h), (0, -d / 2, h / 2), canvas), box((w, 0.02, h), (0, d / 2, h / 2), canvas),
            box((0.02, d, h), (-w / 2, 0, h / 2), canvas), box((0.02, d, h), (w / 2, 0, h / 2), canvas)]
    # a shallow pyramid roof
    mesh = bpy.data.meshes.new("roof")
    mesh.from_pydata([(-w / 2, -d / 2, h), (w / 2, -d / 2, h), (w / 2, d / 2, h), (-w / 2, d / 2, h), (0, 0, h + 0.55)],
                     [], [(0, 1, 4), (1, 2, 4), (2, 3, 4), (3, 0, 4), (3, 2, 1, 0)])
    roof = bpy.data.objects.new("roof", mesh)
    objs.append(_link(roof, canvas))
    for sx in (-1, 1):
        for sy in (-1, 1):
            objs.append(cylinder(0.022, h + 0.05, (sx * w / 2, sy * d / 2, h / 2), frame, verts=8))
    return objs


def tablet_station():
    """A rolling hard case on a stand, two tablets docked on top."""
    case = mat("prop_tablet_case", "#1D2025", 0.5, 0.2)
    screen = mat("prop_tablet_screen", "#0A0D12", 0.08, 0.0, emission=(0.02, 0.05, 0.09))
    objs = [box((0.62, 0.40, 0.92), (0, 0, 0.5), case, bevel=0.02)]
    for x in (-0.15, 0.15):
        objs.append(box((0.25, 0.018, 0.18), (x, 0.06, 1.05), case, bevel=0.006, rot=(-0.5, 0, 0)))
        objs.append(box((0.22, 0.004, 0.15), (x, 0.07, 1.056), screen, rot=(-0.5, 0, 0)))
    for sx in (-1, 1):
        objs.append(cylinder(0.04, 0.04, (sx * 0.24, -0.12, 0.04), case, verts=10, rot=(0, math.pi / 2, 0)))
    return objs


def camera_cart():
    """A sideline broadcast camera on a wheeled pedestal, lens toward the field."""
    body = mat("prop_camera_body", "#23262B", 0.45, 0.3)
    metal = mat("prop_camera_metal", "#9CA1A7", 0.3, 0.9)
    glass = mat("prop_camera_glass", "#0B1016", 0.05, 0.0)
    objs = [cylinder(0.07, 1.1, (0, 0, 0.75), metal, verts=12),
            box((0.26, 0.55, 0.28), (0, 0.05, 1.42), body, bevel=0.02),
            cylinder(0.075, 0.42, (0, 0.52, 1.44), body, verts=14, rot=(math.pi / 2, 0, 0)),
            cylinder(0.068, 0.01, (0, 0.735, 1.44), glass, verts=14, rot=(math.pi / 2, 0, 0)),
            box((0.18, 0.12, 0.14), (0, -0.25, 1.58), body, bevel=0.01)]                 # viewfinder
    for k in range(3):
        a = k * 2 * math.pi / 3
        objs.append(tube([(0, 0, 0.26), (math.cos(a) * 0.5, math.sin(a) * 0.5, 0.08)], 0.02, metal, sides=6, resolution=1))
        objs.append(cylinder(0.05, 0.035, (math.cos(a) * 0.52, math.sin(a) * 0.52, 0.05), body, verts=10, rot=(0, math.pi / 2, a)))
    return objs


def cable_run():
    """Ten metres of cable bundle along the ground and a rubber ramp over it."""
    rubber = mat("prop_cable_rubber", "#111214", 0.85)
    ramp = mat("prop_cable_ramp", "#F2C200", 0.7)
    objs = []
    for k, off in enumerate((-0.03, 0.0, 0.028)):
        pts = [(x, off + 0.04 * math.sin(x * 0.9 + k), 0.012) for x in np.linspace(-5, 5, 7)]
        objs.append(tube(pts, 0.011, rubber, sides=6, resolution=2))
    mesh = bpy.data.meshes.new("ramp")
    w, d, h = 0.9, 0.5, 0.05
    mesh.from_pydata([(-w / 2, -d / 2, 0), (w / 2, -d / 2, 0), (w / 2, d / 2, 0), (-w / 2, d / 2, 0),
                      (-w / 2, -0.08, h), (w / 2, -0.08, h), (w / 2, 0.08, h), (-w / 2, 0.08, h)], [],
                     [(0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7), (4, 5, 6, 7)])
    r = bpy.data.objects.new("ramp", mesh)
    r.rotation_euler = (0, 0, math.pi / 2)
    objs.append(_link(r, ramp))
    return objs


def endzone_platform():
    """A 3 m scaffold camera tower behind the end line, rails and a ladder."""
    steel = mat("prop_scaffold_steel", "#B2B6BB", 0.35, 0.85)
    deck = mat("prop_scaffold_deck", "#3A3D42", 0.8)
    body = mat("prop_camera_body", "#23262B", 0.45, 0.3)
    s, h = 2.0, 3.0
    objs = [box((s, s, 0.06), (0, 0, h), deck, bevel=0.01)]
    for sx in (-1, 1):
        for sy in (-1, 1):
            objs.append(cylinder(0.024, h + 1.0, (sx * s / 2, sy * s / 2, (h + 1.0) / 2), steel, verts=8))
    for z in (0.9, 1.9, h + 0.5, h + 1.0):
        for (a, b) in (((-1, -1), (1, -1)), ((1, -1), (1, 1)), ((1, 1), (-1, 1)), ((-1, 1), (-1, -1))):
            if z < h and a == (1, 1):
                continue
            objs.append(tube([(a[0] * s / 2, a[1] * s / 2, z), (b[0] * s / 2, b[1] * s / 2, z)], 0.018, steel, sides=6, resolution=1))
    for z in np.arange(0.3, h, 0.3):                                                   # ladder rungs
        objs.append(cylinder(0.012, 0.45, (s / 2 + 0.02, 0, z), steel, verts=6, rot=(math.pi / 2, 0, 0)))
    objs.append(box((0.26, 0.5, 0.28), (0, 0.3, h + 0.5), body, bevel=0.02))
    objs.append(cylinder(0.07, 0.6, (0, 0.8, h + 0.5), body, verts=12, rot=(math.pi / 2, 0, 0)))
    return objs


def fieldgoal_net():
    """The net raised behind the goal on two poles for kicks: 12 x 9 m."""
    pole = mat("prop_net_pole", "#DADCDF", 0.35, 0.8)
    net = textured_mat("prop_net", TEX / "net.png", rough=0.9, alpha=True)
    w, h, lift = 12.0, 9.0, 4.2
    objs = [plane((w, h), (0, 0, lift), net, uv_repeat=(w / 0.6, h / 0.6))]
    for sx in (-1, 1):
        objs.append(cylinder(0.06, lift + h + 0.4, (sx * (w / 2 + 0.1), 0, (lift + h + 0.4) / 2), pole, verts=10))
    objs.append(tube([(-w / 2, 0, lift + h), (w / 2, 0, lift + h)], 0.012, pole, sides=6, resolution=1))
    return objs


def kicking_net():
    """The practice net a kicker warms up into on the sideline: 2.4 m square."""
    frame = mat("prop_kicknet_frame", "#1C1E22", 0.5, 0.3)
    net = textured_mat("prop_net", TEX / "net.png", rough=0.9, alpha=True)
    s = 2.4
    objs = [plane((s, s), (0, 0.5, 0.05), net, rot=(-0.25, 0, 0), uv_repeat=(4, 4))]
    for a, b_ in (((-s / 2, 0.5, 0.05), (-s / 2, 0.2, s)), ((-s / 2, 0.2, s), (s / 2, 0.2, s)), ((s / 2, 0.2, s), (s / 2, 0.5, 0.05))):
        objs.append(cylinder(0.025, math.dist(a, b_), tuple((x + y) / 2 for x, y in zip(a, b_)), frame, verts=8,
                             rot=_aim(a, b_)))
    for sx in (-1, 1):
        objs.append(tube([(sx * s / 2, 0.5, 0.05), (sx * s / 2, 1.4, 0.05)], 0.025, frame, sides=8, resolution=1))
    objs.append(plane((s, 0.9), (0, 0.95, 0.03), net, rot=(-math.pi / 2, 0, 0), uv_repeat=(4, 1.5)))
    return objs


def _aim(a, b):
    """Euler rotation that turns a Z-aligned cylinder to run from a to b."""
    d = Vector(b) - Vector(a)
    return d.to_track_quat("Z", "Y").to_euler()


def _football(loc, material, rot=(0, 0, 0), laces=None):
    b = sphere(0.085, loc, material, segs=9, rings=6, scale=(1.0, 1.0, 1.65))
    b.rotation_euler = rot
    return b


def ball_bag():
    """A drawstring mesh bag with footballs showing through, on the ground."""
    leather = mat("prop_football_leather", "#6B3A1F", 0.55)
    netm = textured_mat("prop_net", TEX / "net.png", rough=0.9, alpha=True)
    objs = []
    r = common.rng(12)
    for i in range(6):
        objs.append(_football((r.normal(0, 0.12), r.normal(0, 0.12), 0.09 + 0.12 * (i // 3)), leather,
                              rot=(r.uniform(1.2, 1.9), 0, r.uniform(0, math.pi))))
    bag = sphere(0.3, (0, 0, 0.26), netm, segs=12, rings=7, scale=(1.0, 0.9, 0.9))
    objs.append(bag)
    return objs


def bean_bag():
    """The official's bean bag, dropped to mark a spot."""
    cloth = mat("prop_beanbag", "#1D4FA8", 0.9)
    return [sphere(0.06, (0, 0, 0.025), cloth, segs=10, rings=6, scale=(1.0, 0.8, 0.4))]


def penalty_flag():
    """A thrown penalty flag lying on the grass, knotted around its weight."""
    cloth = mat("prop_penalty_flag", "#FFD100", 0.85)
    mesh = bpy.data.meshes.new("flag")
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=6, y_segments=6, size=0.2)
    r = common.rng(5)
    for v in bm.verts:
        d = math.hypot(v.co.x, v.co.y)
        v.co.z = 0.012 * math.exp(-d * 12) + 0.004 * r.random() + 0.006 * math.sin(v.co.x * 20) * (d > 0.08)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new("flag", mesh)
    obj.location = (0, 0, 0.005)
    obj.rotation_euler = (0, 0, 0.4)
    knot = sphere(0.022, (0, 0, 0.02), cloth, segs=8, rings=5)
    return [_link(obj, cloth), knot]


def human_reference():
    """A 1.85 m mannequin for scale in review renders; never exported."""
    grey = mat("review_mannequin", "#8C8F94", 0.6)
    objs = [cylinder(0.17, 0.85, (0, 0, 0.425), grey, verts=12, radius2=0.14),
            cylinder(0.2, 0.62, (0, 0, 1.2), grey, verts=12, radius2=0.22),
            sphere(0.115, (0, 0, 1.735), grey, segs=12, rings=8)]
    return join(objs, "human_1p85m")


PROPS = {
    "goalpost_nfl": lambda: goalpost("nfl"),
    "goalpost_college": lambda: goalpost("college-football"),
    "pylon_nfl": lambda: pylon("nfl"),
    "pylon_college": lambda: pylon("college-football"),
    "chain_set": lambda: chain_set("nfl"),
    "down_marker": lambda: down_marker("nfl"),
    "ground_marker": lambda: ground_marker("college-football"),
    "bench": bench,
    "heater_fan": heater_fan,
    "cooler_station": cooler_station,
    "medical_tent": medical_tent,
    "tablet_station": tablet_station,
    "camera_cart": camera_cart,
    "cable_run": cable_run,
    "endzone_platform": endzone_platform,
    "fieldgoal_net": fieldgoal_net,
    "kicking_net": kicking_net,
    "ball_bag": ball_bag,
    "bean_bag": bean_bag,
    "penalty_flag": penalty_flag,
}


# ───────────────────────────── export ─────────────────────────────

def triangles(obj) -> int:
    obj.data.calc_loop_triangles()
    return len(obj.data.loop_triangles)


def lod_copy(obj, ratio, name):
    new = obj.copy()
    new.data = obj.data.copy()
    new.name = name
    bpy.context.scene.collection.objects.link(new)
    if ratio < 1.0:
        mod = new.modifiers.new("dec", "DECIMATE")
        mod.ratio = ratio
        mod.use_collapse_triangulate = True
        for o in bpy.context.scene.objects:
            o.select_set(False)
        new.select_set(True)
        bpy.context.view_layer.objects.active = new
        bpy.ops.object.modifier_apply(modifier="dec")
    return new


def export(objs, path_stem: pathlib.Path):
    for o in bpy.context.scene.objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    path_stem.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.gltf(filepath=str(path_stem.with_suffix(".glb")), export_format="GLB",
                              use_selection=True, export_apply=True, export_yup=True)
    bpy.ops.wm.usd_export(filepath=str(path_stem.with_suffix(".usdz")), selected_objects_only=True,
                          export_materials=True, triangulate_meshes=True, convert_orientation=True,
                          export_global_up_selection="Y", export_global_forward_selection="NEGATIVE_Z",
                          meters_per_unit=1.0)


def build(name: str) -> dict:
    common.reset_scene(engine="BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items] else "CYCLES")
    _MATS.clear()
    result = PROPS[name]()
    children = []
    if isinstance(result, tuple):
        result, children = result
    root = join(result, name)
    record = {"id": name, "lods": {}, "materials": [s.material.name for s in root.material_slots if s.material],
              "dimensionsMetres": [round(d, 3) for d in root.dimensions]}
    for lod, ratio in LODS.items():
        lod_root = lod_copy(root, ratio, f"{name}_lod{lod}" if lod else name)
        extra = [lod_copy(c, ratio, f"{c.name}" if lod == 0 else f"{c.name}_lod{lod}") for c in children]
        for c in extra:
            c.parent = lod_root
        stem = OUT / (name if lod == 0 else f"{name}_lod{lod}")
        export([lod_root] + extra, stem)
        record["lods"][lod] = {"triangles": triangles(lod_root) + sum(triangles(c) for c in extra),
                               "parts": len(record["materials"]) + (1 if extra else 0),
                               "files": [stem.with_suffix(".usdz").name, stem.with_suffix(".glb").name]}
        if extra:
            record["lods"][lod]["children"] = [c.name for c in extra]
    return record


def main():
    args = common.script_args()
    common.reset_scene()
    make_textures()
    names = args or list(PROPS)
    manifest_path = OUT / "manifest.json"
    existing = json.loads(manifest_path.read_text())["props"] if manifest_path.exists() else {}
    for name in names:
        existing[name] = build(name)
        print("PROP", name, existing[name]["lods"][0]["triangles"], existing[name]["dimensionsMetres"])
    common.write_json(manifest_path, {
        "actor": "sideline",
        "axes": "metres; exported Y-up; origin at the base on the ground; -Z faces the field of play",
        "lodUse": {"0": "stadium and field level", "1": "far side of the bowl", "2": "tabletop"},
        "tints": "materials named tint_* take the scene's team chip colours at runtime",
        "budget": {"triangles": 25000, "parts": 15, "textureMB": 20},
        "props": existing,
    })


if __name__ == "__main__" or True:
    main()
