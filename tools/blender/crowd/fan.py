"""Build one fan in Blender: skeleton, skinned body, head, hair, hat, props.

Coordinates are metres, Z up, and every fan faces -Y with the origin on the
floor under the pelvis. Every fan shares one 20-joint skeleton - same names,
same hierarchy, proportions scaled per fan - so a pose written as bone
directions (see poses.py) fits all 24 without retargeting.

Colour is authored as two face-corner attributes. `base` is the albedo;
wherever a club colour will go it holds only a light luminance, so the runtime
multiplies it by a chip. `tint` is the mask: R primary chip, G secondary,
B face paint. Boundaries follow faces, so sleeves and collars stay crisp
after baking instead of smearing across a triangle.
"""
from __future__ import annotations

import math

import bmesh
import bpy
from mathutils import Matrix, Vector

TINTED = (0.86, 0.86, 0.86)          # luminance a club colour is multiplied into
HEAD_SCALE = 1.08                    # crowd heads read a touch large, as they do in any stand
SUBSURF = 1                          # body smoothing; 2 only for hero renders
SPHERE = (16, 10)                    # head and shell sphere segments at runtime density


def hex_rgb(h: str):
    h = h.lstrip("#")
    srgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in srgb)


# ───────────────────────────── skeleton ─────────────────────────────

BONES = [  # name, parent, head joint, tail joint
    ("root", None, "floor", "root_tip"),
    ("hips", "root", "pelvis", "spine"),
    ("spine", "hips", "spine", "chest"),
    ("chest", "spine", "chest", "neck"),
    ("neck", "chest", "neck", "head"),
    ("head", "neck", "head", "head_top"),
    ("clavicle.L", "chest", "clav.L", "shoulder.L"),
    ("upperarm.L", "clavicle.L", "shoulder.L", "elbow.L"),
    ("forearm.L", "upperarm.L", "elbow.L", "wrist.L"),
    ("hand.L", "forearm.L", "wrist.L", "hand_end.L"),
    ("clavicle.R", "chest", "clav.R", "shoulder.R"),
    ("upperarm.R", "clavicle.R", "shoulder.R", "elbow.R"),
    ("forearm.R", "upperarm.R", "elbow.R", "wrist.R"),
    ("hand.R", "forearm.R", "wrist.R", "hand_end.R"),
    ("thigh.L", "hips", "hip.L", "knee.L"),
    ("shin.L", "thigh.L", "knee.L", "ankle.L"),
    ("foot.L", "shin.L", "ankle.L", "toe.L"),
    ("thigh.R", "hips", "hip.R", "knee.R"),
    ("shin.R", "thigh.R", "knee.R", "ankle.R"),
    ("foot.R", "shin.R", "ankle.R", "toe.R"),
]


def joints(f: dict) -> dict[str, Vector]:
    """Joint positions for a fan, from a 1.75 m reference scaled by height."""
    k = f["height"] / 1.75
    sw, hw = f["sw"], f["hw"]
    j = {
        "floor": (0, 0, 0), "root_tip": (0, 0, 0.25),
        "pelvis": (0, 0, 0.97), "spine": (0, 0.005, 1.12), "chest": (0, 0.0, 1.30),
        "neck": (0, 0.005, 1.475), "head": (0, 0.0, 1.535), "head_top": (0, 0, 1.75),
    }
    for s, x in (("L", 1), ("R", -1)):
        j.update({
            f"clav.{s}": (x * 0.03, -0.01, 1.41),
            f"shoulder.{s}": (x * 0.185 * sw, 0.0, 1.425),
            f"elbow.{s}": (x * 0.33 * sw, 0.015, 1.20),
            f"wrist.{s}": (x * 0.45 * sw, -0.005, 1.00),
            f"hand_end.{s}": (x * 0.51 * sw, -0.02, 0.915),
            f"hip.{s}": (x * 0.092 * hw, 0.0, 0.93),
            f"knee.{s}": (x * 0.100 * hw, -0.012, 0.515),
            f"ankle.{s}": (x * 0.100 * hw, 0.018, 0.085),
            f"toe.{s}": (x * 0.105 * hw, -0.125, 0.025),
        })
    return {n: Vector(p) * k for n, p in j.items()}


def make_armature(f: dict, J: dict[str, Vector]):
    arm = bpy.data.armatures.new(f"{f['id']}_rig")
    ob = bpy.data.objects.new(f"{f['id']}_rig", arm)
    bpy.context.scene.collection.objects.link(ob)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode="EDIT")
    eb = {}
    for name, parent, h, t in BONES:
        b = arm.edit_bones.new(name)
        b.head, b.tail = J[h], J[t]
        # Z toward the fan's front, so X is the flexion axis on every bone.
        b.align_roll(Vector((0, -1, 0)) if abs((J[t] - J[h]).normalized().y) < 0.9 else Vector((0, 0, 1)))
        if parent:
            b.parent = eb[parent]
            b.use_connect = False
        eb[name] = b
    bpy.ops.object.mode_set(mode="OBJECT")
    for pb in ob.pose.bones:
        pb.rotation_mode = "QUATERNION"
    return ob


# ───────────────────────────── body ─────────────────────────────

def _skin_mesh(name, verts, edges, radii, root=0):
    me = bpy.data.meshes.new(name)
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    bm = bmesh.new()
    vs = [bm.verts.new(v) for v in verts]
    for a, b in edges:
        bm.edges.new((vs[a], vs[b]))
    bm.to_mesh(me)
    bm.free()
    mod = ob.modifiers.new("skin", "SKIN")
    mod.branch_smoothing = 1.0
    mod.use_smooth_shade = True
    for i, v in enumerate(me.skin_vertices[0].data):
        v.radius = radii[i]
    me.skin_vertices[0].data[root].use_root = True
    sub = ob.modifiers.new("sub", "SUBSURF")
    sub.levels = SUBSURF
    sub.render_levels = SUBSURF
    _apply_all(ob)
    return ob


def _apply_all(ob):
    bpy.context.view_layer.objects.active = ob
    for o in bpy.context.selected_objects:
        o.select_set(False)
    ob.select_set(True)
    for m in list(ob.modifiers):
        bpy.ops.object.modifier_apply(modifier=m.name)


def body(f: dict, J: dict[str, Vector]):
    """Torso, arms and legs as one skin-modifier mesh, clothing thickness included.

    The skin graph is denser than the skeleton: a thigh has a mid point, an
    arm a biceps and a forearm swell, the torso a ribcage and a waist. Those
    in-between radii are what turn a mannequin of tubes into a body.
    """
    k = f["height"] / 1.75
    top = f["top"]
    loose = {"jersey": 0.014, "tee": 0.006, "hoodie": 0.024, "jacket": 0.028, "pullover": 0.016}[top]
    b, bl, sw, hw = f["bulk"], f["belly"], f["sw"], f["hw"]
    sl = loose if top in ("hoodie", "jacket", "pullover") else loose * 0.5
    pl = 0.012                                                    # trousers are not skin-tight
    pts, rad, edges = [], [], []

    def add(p, r):
        pts.append(Vector(p)); rad.append((r[0] * k, r[1] * k)); return len(pts) - 1

    def lerp(a, c, t):
        return J[a].lerp(J[c], t)

    z = lambda zz: Vector((0, 0, zz * k))
    crotch = add(z(0.905), (0.150 * hw * b + pl, 0.110 * b + pl))
    hips = add(z(0.985), (0.168 * hw * b + pl, 0.118 * b * bl ** 0.4 + pl))
    waist = add(z(1.090), (0.148 * b * bl + loose, 0.112 * b * bl ** 1.5 + loose))
    ribs = add(z(1.225) + Vector((0, -0.004, 0)), (0.163 * sw * b + loose, 0.120 * b * bl ** 0.7 + loose))
    chest = add(z(1.330) + Vector((0, -0.006, 0)), (0.172 * sw * b + loose, 0.112 * b + loose))
    yoke = add(z(1.405), (0.145 * sw * b + loose * 0.4, 0.092 * b + loose * 0.4))
    neck0 = add(z(1.450), (0.068 * b ** 0.5 + loose * 0.4, 0.066 * b ** 0.5 + loose * 0.4))
    neck1 = add(z(1.515), (0.060 * b ** 0.4, 0.062 * b ** 0.4))
    for a, c in ((crotch, hips), (hips, waist), (waist, ribs), (ribs, chest), (chest, yoke), (yoke, neck0), (neck0, neck1)):
        edges.append((a, c))
    for s, x in (("L", 1), ("R", -1)):
        sh = add(J[f"shoulder.{s}"] / k, (0.066 * b + sl * 0.6, 0.068 * b + sl * 0.6))
        bic = add(lerp(f"shoulder.{s}", f"elbow.{s}", 0.45) / k, (0.056 * b + sl, 0.058 * b + sl))
        el = add(J[f"elbow.{s}"] / k, (0.044 * b + sl, 0.046 * b + sl))
        fa = add(lerp(f"elbow.{s}", f"wrist.{s}", 0.32) / k, (0.045 * b + sl * 0.8, 0.043 * b + sl * 0.8))
        cuff = sl if top in ("hoodie", "jacket") else 0.0
        wr = add(J[f"wrist.{s}"] / k, (0.031 * b ** 0.5 + cuff, 0.026 + cuff))
        palm = add(lerp(f"wrist.{s}", f"hand_end.{s}", 0.45) / k, (0.043, 0.020))
        tip = add(J[f"hand_end.{s}"] / k, (0.036, 0.015))
        edges += [(yoke, sh), (sh, bic), (bic, el), (el, fa), (fa, wr), (wr, palm), (palm, tip)]
        hip = add(J[f"hip.{s}"] / k + Vector((0, 0.004, -0.02)), (0.098 * hw * b + pl, 0.100 * b + pl))
        th = add(lerp(f"hip.{s}", f"knee.{s}", 0.45) / k, (0.084 * b + pl, 0.088 * b + pl))
        kn = add(J[f"knee.{s}"] / k, (0.060 * b + pl, 0.062 * b + pl))
        calf = add(lerp(f"knee.{s}", f"ankle.{s}", 0.30) / k + Vector((0, 0.012, 0)), (0.058 * b + pl, 0.064 * b + pl))
        an = add(J[f"ankle.{s}"] / k + Vector((0, 0, 0.03)), (0.046 + pl * 0.6, 0.048 + pl * 0.6))
        heel = add(J[f"ankle.{s}"] / k + Vector((0, 0.02, -0.035)), (0.048, 0.050))
        ball = add(lerp(f"ankle.{s}", f"toe.{s}", 0.62) / k + Vector((0, 0, -0.02)), (0.050, 0.040))
        toe = add(J[f"toe.{s}"] / k + Vector((0, -0.012, -0.005)), (0.044, 0.030))
        edges += [(hips, hip), (hip, th), (th, kn), (kn, calf), (calf, an), (an, heel), (heel, ball), (ball, toe)]
    ob = _skin_mesh(f"{f['id']}_body", [p * k for p in pts], edges, rad, root=crotch)
    return ob


def head(f: dict, J: dict[str, Vector]):
    k = f["height"] / 1.75
    c = (J["head"] + J["head_top"]) / 2 + Vector((0, -0.010, -0.030)) * k
    hs = HEAD_SCALE
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=SPHERE[0], v_segments=SPHERE[1], radius=1.0)
    for v in bm.verts:
        x, y, z = v.co
        sx = 0.083 if z > -0.1 else 0.083 * (0.78 + 0.22 * (1 + z))     # jaw narrows
        sy = 0.098 - (0.012 if (y < 0 and z < -0.2) else 0)              # face flatter than skull
        v.co = Vector((x * sx, y * sy - (0.006 if z < -0.35 else 0), z * 0.112)) * k * hs + c
    # Nose and ears: small, but they are what makes a head read as facing you.
    nose = bmesh.ops.create_cone(bm, cap_ends=True, segments=6, radius1=0.016 * k, radius2=0.005 * k, depth=0.036 * k)
    for v in nose["verts"]:
        v.co = Matrix.Rotation(math.radians(90), 4, "X") @ v.co
        v.co += c + Vector((0, -0.110, -0.014)) * k
    for s in (1, -1):
        ear = bmesh.ops.create_uvsphere(bm, u_segments=6, v_segments=4, radius=1.0)
        for v in ear["verts"]:
            v.co = Vector((v.co.x * 0.010, v.co.y * 0.020, v.co.z * 0.030)) * k + c + Vector((s * 0.090, 0.006, -0.004)) * k
    me = bpy.data.meshes.new(f"{f['id']}_head")
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(me.name, me)
    bpy.context.scene.collection.objects.link(ob)
    for p in me.polygons:
        p.use_smooth = True
    ob["head_centre"] = list(c)
    return ob, c


def _shell(name, centre, k, scale, keep, deform=None, segments=None, rings=None):
    segments = segments or SPHERE[0]
    rings = rings or SPHERE[1]
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=segments, v_segments=rings, radius=1.0)
    kill = [v for v in bm.verts if not keep(v.co)]
    bmesh.ops.delete(bm, geom=kill, context="VERTS")
    for v in bm.verts:
        p = Vector((v.co.x * scale[0], v.co.y * scale[1], v.co.z * scale[2]))
        if deform:
            p = deform(p, v.co)
        v.co = p * k * HEAD_SCALE + centre
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    for p in me.polygons:
        p.use_smooth = True
    return ob


def hair(f: dict, c: Vector):
    k = f["height"] / 1.75
    style = f["hair"]
    if style in ("bald", "buzz"):
        return None
    # Hairline: high at the forehead, low at the nape.
    def line(co):
        return co.z > (0.28 if co.y < -0.3 else -0.1 if co.y < 0.2 else -0.55)
    if style == "short":
        return _shell(f"{f['id']}_hair", c, k, (0.090, 0.106, 0.120), line)
    if style == "curly":
        import random as _r
        rnd = _r.Random(hash(f["id"]) & 0xFFFF)
        def puff(p, co):
            return p * (1.0 + 0.10 * rnd.random())
        return _shell(f"{f['id']}_hair", c, k, (0.112, 0.126, 0.134), line, puff)
    if style == "long":
        def drape(p, co):
            if co.y > -0.1 and co.z < 0.1:
                p = Vector((p.x * 1.05, p.y + 0.012, p.z - (0.1 - co.z) * 0.16))
            return p
        return _shell(f"{f['id']}_hair", c, k, (0.093, 0.110, 0.122),
                      lambda co: co.z > (0.28 if co.y < -0.3 else -0.95), drape)
    if style == "ponytail":
        ob = _shell(f"{f['id']}_hair", c, k, (0.091, 0.107, 0.121), line)
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        tail = bmesh.ops.create_cone(bm, cap_ends=True, segments=8, radius1=0.022 * k, radius2=0.008 * k, depth=0.16 * k)
        for v in tail["verts"]:
            v.co = Matrix.Rotation(math.radians(-25), 4, "X") @ v.co
            v.co += c + Vector((0, 0.11, -0.09)) * k
        bm.to_mesh(ob.data)
        bm.free()
        return ob
    return None


def hat(f: dict, c: Vector):
    k = f["height"] / 1.75
    kind = f["hat"]
    if kind == "none":
        return None
    if kind == "beanie":
        ob = _shell(f"{f['id']}_hat", c + Vector((0, 0, 0.01)) * k, k, (0.098, 0.112, 0.128), lambda co: co.z > -0.05)
        bm = bmesh.new(); bm.from_mesh(ob.data)
        pom = bmesh.ops.create_uvsphere(bm, u_segments=8, v_segments=6, radius=0.024 * k)
        for v in pom["verts"]:
            v.co += c + Vector((0, 0, 0.14)) * k
        bm.to_mesh(ob.data); bm.free()
        return ob
    crown = (0.094, 0.108, 0.112)
    ob = _shell(f"{f['id']}_hat", c + Vector((0, 0, 0.018)) * k, k, crown, lambda co: co.z > 0.02)
    if kind in ("cap", "cap_back", "visor"):
        bm = bmesh.new(); bm.from_mesh(ob.data)
        if kind == "visor":
            bm.clear()
            band = bmesh.ops.create_circle(bm, cap_ends=False, segments=20, radius=1.0)
            ring = bmesh.ops.extrude_edge_only(bm, edges=bm.edges[:])
            for v in bm.verts:
                up = v in [e for e in ring["geom"] if isinstance(e, bmesh.types.BMVert)]
                v.co = Vector((v.co.x * 0.101, v.co.y * 0.119, 0.022 if up else -0.008)) * k + c + Vector((0, 0, 0.058)) * k
        brim = bmesh.ops.create_circle(bm, cap_ends=True, segments=12, radius=1.0)
        back = kind == "cap_back"
        for v in brim["verts"]:
            y = v.co.y
            keep_front = (y < 0.0) if not back else (y > 0.0)
            lift = 0.032 if kind == "visor" else 0.0
            v.co = Vector((v.co.x * 0.085, (y * 0.07 if keep_front else y * 0.02) + (-0.10 if not back else 0.10),
                           0.034 + lift - (0.010 if keep_front else 0))) * k * HEAD_SCALE + c
        bm.to_mesh(ob.data); bm.free()
    return ob


def accessory(f: dict, J: dict[str, Vector]):
    kind = f["accessory"]
    if kind == "none":
        return None
    k = f["height"] / 1.75
    hand = J["hand_end.R"]
    bm = bmesh.new()
    if kind == "foam_finger":
        mitt = bmesh.ops.create_cube(bm, size=1.0)
        for v in mitt["verts"]:
            v.co = Vector((v.co.x * 0.085, v.co.y * 0.04, v.co.z * 0.13)) + Vector((0, 0, -0.02))
        finger = bmesh.ops.create_cone(bm, cap_ends=True, segments=8, radius1=0.028, radius2=0.022, depth=0.2)
        for v in finger["verts"]:
            v.co += Vector((0.015, 0, -0.17))
        origin = hand + Vector((-0.02, -0.01, -0.06)) * k
    elif kind == "towel":
        grid = bmesh.ops.create_grid(bm, x_segments=6, y_segments=3, size=1.0)
        for v in grid["verts"]:
            u, w = v.co.x, v.co.y
            v.co = Vector((w * 0.10, 0.025 * math.sin(u * 3), -0.17 * (u + 1)))
        origin = hand + Vector((0, -0.01, 0.01)) * k
    elif kind == "sign":
        board = bmesh.ops.create_cube(bm, size=1.0)
        for v in board["verts"]:
            v.co = Vector((v.co.x * 0.46, v.co.y * 0.008, v.co.z * 0.32)) + Vector((0, 0, 0.36))
        stick = bmesh.ops.create_cone(bm, cap_ends=True, segments=6, radius1=0.008, radius2=0.008, depth=0.4)
        for v in stick["verts"]:
            v.co += Vector((0, 0.012, 0.12))
        origin = hand + Vector((0, -0.02, -0.08)) * k
    elif kind == "phone":
        phone = bmesh.ops.create_cube(bm, size=1.0)
        for v in phone["verts"]:
            v.co = Vector((v.co.x * 0.036, v.co.y * 0.004, v.co.z * 0.075)) + Vector((0, -0.01, 0.0))
        origin = hand + Vector((0, -0.02, 0.0)) * k
    for v in bm.verts:
        v.co = v.co * k + origin
    me = bpy.data.meshes.new(f"{f['id']}_prop")
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(me.name, me)
    bpy.context.scene.collection.objects.link(ob)
    ob["prop"] = kind
    return ob


def scarf(f: dict, J: dict[str, Vector]):
    """A knit club scarf: a loop at the collar and two tails down the chest."""
    if not f.get("scarf"):
        return None
    k = f["height"] / 1.75
    b = f["bulk"]
    neck = Vector((0, 0.004, 1.455)) * k
    bm = bmesh.new()
    ring = bmesh.ops.create_cone(bm, cap_ends=False, segments=16, radius1=0.078 * k * b ** 0.5,
                                 radius2=0.070 * k * b ** 0.5, depth=0.05 * k)
    for v in ring["verts"]:
        v.co += neck
    for side, x in ((1, 0.035), (-1, -0.045)):
        tail = bmesh.ops.create_cube(bm, size=1.0)
        for v in tail["verts"]:
            v.co = Vector((v.co.x * 0.062, v.co.y * 0.014, v.co.z * 0.30)) * k
            v.co += Vector((x, -0.105 * b - 0.012, 1.30)) * k
            v.co.y -= (1.42 * k - v.co.z) * 0.10          # hangs off the chest, not through it
    me = bpy.data.meshes.new(f"{f['id']}_scarf")
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(me.name, me)
    bpy.context.scene.collection.objects.link(ob)
    sol = ob.modifiers.new("thick", "SOLIDIFY")
    sol.thickness = 0.012 * k
    _apply_all(ob)
    return ob


def paint_scarf(ob, f: dict):
    """Bars of primary and secondary down the tails, primary on the loop."""
    me = ob.data
    base, tint = _corner_attrs(ob)
    k = f["height"] / 1.75
    for p in me.polygons:
        c = ob.matrix_world @ p.center
        if c.z > 1.42 * k:
            mask = (1, 0, 0)
        else:
            band = int((1.42 * k - c.z) / (0.045 * k))
            mask = (1, 0, 0) if band % 2 == 0 else (0, 1, 0)
        _set_face(me, base, tint, p, TINTED, mask)


# ───────────────────────────── colour ─────────────────────────────

def _corner_attrs(ob):
    me = ob.data
    base = me.color_attributes.new("base", "FLOAT_COLOR", "CORNER")
    tint = me.color_attributes.new("tint", "FLOAT_COLOR", "CORNER")
    return base, tint


def _set_face(me, base, tint, poly, rgb, mask):
    for li in poly.loop_indices:
        base.data[li].color = (*rgb, 1.0)
        tint.data[li].color = (*mask, 1.0)


def paint_body(ob, f: dict, J: dict[str, Vector]):
    """Assign clothing per face from where the face sits on the skeleton."""
    me = ob.data
    base, tint = _corner_attrs(ob)
    k = f["height"] / 1.75
    skin = hex_rgb(f["skin"])
    top = f["top"]
    club = f["club"]
    top_rgb = TINTED if club else hex_rgb(f["top_neutral"])
    top_mask = (1, 0, 0) if club else (0, 0, 0)
    pants = hex_rgb(f["pants"])
    shoes = hex_rgb(f["shoes"])
    sleeve_to = {"jersey": 0.45, "tee": 0.30, "hoodie": 1.02, "jacket": 1.02, "pullover": 1.0}[top]
    waist = J["pelvis"].z - 0.055 * k        # tops hang over the belt
    for p in me.polygons:
        c = ob.matrix_world @ p.center
        side = "L" if c.x > 0 else "R"
        sh, el, wr = J[f"shoulder.{side}"], J[f"elbow.{side}"], J[f"wrist.{side}"]
        arm_axis = (wr - sh)
        t = (c - sh).dot(arm_axis) / arm_axis.length_squared      # 0 at shoulder, 1 at wrist
        dist_arm = (c - (sh + arm_axis * max(0.0, min(1.0, t)))).length
        on_arm = abs(c.x) > abs(sh.x) * 0.80 and dist_arm < 0.125 * k and c.z > waist - 0.05 * k
        rgb, mask = top_rgb, top_mask
        if c.z < J["ankle.L"].z + 0.03 * k:
            rgb, mask = shoes, (0, 0, 0)
        elif c.z < waist:
            rgb, mask = pants, (0, 0, 0)
        elif on_arm:
            arm_len = max(0.0, t) * 0.5 + (0.5 if t > 0.5 else 0)
            if t > sleeve_to:
                rgb, mask = skin, (0, 0, 0)
            elif f.get("sleeve_stripes") and sleeve_to - 0.14 < t < sleeve_to - 0.05:
                rgb, mask = TINTED, (0, 1, 0)
            elif top in ("hoodie", "jacket") and t > sleeve_to - 0.07:
                rgb, mask = (hex_rgb(f["top_neutral"]), (0, 0, 0)) if club else (top_rgb, top_mask)
        elif c.z > J["neck"].z - 0.02 * k and math.hypot(c.x, c.y) < 0.075 * k:
            rgb, mask = skin, (0, 0, 0)
        else:
            near_neck = math.hypot(c.x, c.y) < 0.085 * k
            if top == "jersey" and c.z > J["neck"].z - 0.05 * k and near_neck and c.y < 0.02 * k:
                rgb, mask = TINTED, (0, 1, 0)                      # collar
            if top == "jacket" and abs(c.x) < 0.012 * k and c.y < 0 and c.z < J["neck"].z - 0.03 * k:
                rgb, mask = (0.12, 0.12, 0.12), (0, 0, 0)          # zip
            if top == "hoodie" and c.y < -0.06 * k and J["pelvis"].z + 0.03 * k < c.z < J["pelvis"].z + 0.15 * k and abs(c.x) < 0.10 * k:
                # kangaroo pocket: the same cloth, a shade darker, never a flash of white
                shade = tuple(ch * 0.72 for ch in rgb)
                rgb = shade
        _set_face(me, base, tint, p, rgb, mask)


def paint_flat(ob, rgb, mask=(0, 0, 0)):
    me = ob.data
    base, tint = _corner_attrs(ob)
    for p in me.polygons:
        _set_face(me, base, tint, p, rgb, mask)


def paint_head(ob, f: dict, c: Vector):
    """Skin, with a buzz cut painted onto the scalp rather than modelled."""
    me = ob.data
    base, tint = _corner_attrs(ob)
    skin = hex_rgb(f["skin"])
    hair = hex_rgb(f["hair_colour"])
    buzz = tuple(0.7 * h + 0.3 * s for h, s in zip(hair, skin))
    k = f["height"] / 1.75
    for p in me.polygons:
        rel = (ob.matrix_world @ p.center - c) / (k * HEAD_SCALE)
        rgb = skin
        if f["hair"] == "buzz" and rel.z > (0.035 if rel.y < -0.05 else -0.03 if rel.y < 0.05 else -0.07):
            rgb = buzz
        _set_face(me, base, tint, p, rgb, (0, 0, 0))


def paint_prop(ob, kind):
    me = ob.data
    base, tint = _corner_attrs(ob)
    for p in me.polygons:
        if kind == "phone":
            rgb, mask = ((0.05, 0.05, 0.06), (0, 0, 0)) if p.normal.y > -0.9 else ((0.35, 0.55, 0.9), (0, 0, 0))
        elif kind == "sign":
            rgb, mask = ((0.93, 0.92, 0.88), (0, 0, 0)) if abs(p.normal.y) > 0.9 else ((0.55, 0.42, 0.28), (0, 0, 0))
        elif kind == "towel":
            rgb, mask = TINTED, (0, 1, 0)
        else:
            rgb, mask = TINTED, (1, 0, 0)
        _set_face(me, base, tint, p, rgb, mask)
