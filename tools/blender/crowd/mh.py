"""Fans from MakeHuman (MPFB 2.0.17) bodies, CC0 assets only.

The cast in specs.py decides who each fan is; this module turns that into an
MPFB human: macros for sex, age, weight, muscle and height, a system skin for
age x ancestry x sex, a CC0 outfit, shoes, hair, and eyes. The body is baked
from its morph targets, clothing masks are applied (so skin hidden under a
shirt is really gone), and every part gets two flat emission materials the
kit's bake reads:

  <part>_base   the colour to bake into fan_albedo (alpha = cut-out coverage)
  <part>_tint   the club mask (R primary, G secondary, B face paint)

A club top never uses its source texture: MakeHuman's system garments carry
MakeHuman logos and a makehuman.org watermark. Its albedo is generated cloth
- a luminance, shaded by the garment's own normal map for folds and weave -
so no logo can reach the kit. tests/test_crowd_kit.py holds that.

Everything is posed through apply_pose below, which reads the same bone
direction dictionaries as poses.py and drives MPFB's 163-bone rig.

    (imported by build.py; run install_mpfb.sh and fetch_mh_assets.py first)
"""
from __future__ import annotations

import json
import math
import pathlib

import addon_utils
import bpy
from mathutils import Matrix, Quaternion, Vector

import fan as F

ROOT = pathlib.Path(__file__).resolve().parents[3]
MH = ROOT / ".work/crowd/mh"
SYS = MH / "makehuman_system_assets"
MPFB = "bl_ext.user_default.mpfb"

# ── curation (on top of the per-file licence filter) ──────────────────────────
# Suits are shirt-over-trousers in one mesh; the kit splits top from trousers by
# height on the body and generates the top's cloth, so logos never show.
SUITS = {
    "male": ["male_casualsuit01", "male_casualsuit02", "male_casualsuit03", "male_casualsuit04", "male_casualsuit05", "male_casualsuit06"],
    # female_sportsuit01 is a crop top over a bare midriff and female_casualsuit02 a
    # dress: neither is what a night crowd wears. MakeHuman fits any suit to any body.
    "female": ["female_casualsuit01", "male_casualsuit02", "male_casualsuit04"],
}
SHOES = ["shoes01", "shoes02", "shoes03", "shoes04", "shoes05", "shoes06"]
HAIR = {
    "male": {"short": "short02", "buzz": "short04", "curly": "afro01", "long": "long01", "ponytail": "ponytail01", "bald": None},
    "female": {"short": "bob02", "buzz": "short03", "curly": "afro01", "long": "long01", "ponytail": "ponytail01", "bald": "bob01"},
}
ANCESTRY = ["caucasian", "caucasian", "caucasian", "asian", "asian", "african", "african", "african"]   # by specs.SKIN index


def enable():
    addon_utils.enable(MPFB, default_set=True)
    from bl_ext.user_default.mpfb.services.humanservice import HumanService
    from bl_ext.user_default.mpfb.services.targetservice import TargetService
    return HumanService, TargetService


def identity(f: dict, index: int) -> dict:
    """Sex, age band, ancestry and macros for a cast member, deterministically."""
    import specs
    build = f["build"]
    female = build == "petite" or (build in ("slim", "average", "heavy", "teen") and (index * 7) % 5 in (1, 3))
    age = "young" if build == "teen" else ["young", "middleage", "middleage", "old"][(index * 3) % 4]
    ancestry = ANCESTRY[specs.SKIN.index(f["skin"])]
    weight = {"slim": 0.35, "average": 0.5, "broad": 0.6, "heavy": 0.85, "petite": 0.45, "teen": 0.4}[build]
    muscle = {"slim": 0.45, "average": 0.5, "broad": 0.75, "heavy": 0.45, "petite": 0.4, "teen": 0.4}[build]
    return {
        "female": female, "age": age, "ancestry": ancestry,
        "macros": {
            "gender": 0.0 if female else 1.0,
            "age": {"young": 0.5 if build != "teen" else 0.3, "middleage": 0.72, "old": 0.9}[age],
            "weight": weight, "muscle": muscle,
            "height": min(1.0, max(0.0, (f["height"] - 1.45) / 0.5)),
            "proportions": 0.5, "firmness": 0.5, "cupsize": 0.5,
            "race": {r: (0.8 if r == ancestry else 0.1) for r in ("african", "asian", "caucasian")},
        },
    }


# ── materials ──────────────────────────────────────────────────────────────

def _image_nodes(mat):
    if not mat or not mat.node_tree:
        return []
    return [n for n in mat.node_tree.nodes if n.type == "TEX_IMAGE" and n.image]


def _diffuse_image(mat):
    for n in _image_nodes(mat):
        name = (n.image.name + n.name + n.label).lower()
        if not any(k in name for k in ("normal", "bump", "rough", "spec", "_ao", "displace", "disp", "litsphere", "sss")):
            return n.image
    return None


def _normal_image(mat):
    for n in _image_nodes(mat):
        if "normal" in (n.image.name + n.name + n.label).lower():
            return n.image
    return None


def flat_material(name, colour=None, image=None, image_multiply=(1, 1, 1), shade_from_normal=None, alpha_image=None):
    """An emission material a bake reads: colour or image (times a colour), optionally
    shaded by a tangent-space normal map, with alpha as a separate emission in `name`+'_alpha'."""
    mat = bpy.data.materials.new(name)
    nt = mat.node_tree
    nt.nodes.clear()
    N, L = nt.nodes, nt.links
    out = N.new("ShaderNodeOutputMaterial")
    em = N.new("ShaderNodeEmission")
    L.new(em.outputs[0], out.inputs["Surface"])
    if image is not None:
        tex = N.new("ShaderNodeTexImage"); tex.image = image
        mul = N.new("ShaderNodeMix"); mul.data_type = "RGBA"; mul.blend_type = "MULTIPLY"; mul.inputs["Factor"].default_value = 1
        mul.inputs[7].default_value = (*image_multiply, 1)
        L.new(tex.outputs["Color"], mul.inputs[6])
        if alpha_image is not None:
            # Hair is alpha cards and the stadium draws fans opaque: where a card is clear,
            # show the shadowed depth of the hair, not the texture's colour under zero alpha
            # (an orange lattice over the scalp in round 4's first bake).
            deep = N.new("ShaderNodeMix"); deep.data_type = "RGBA"; deep.clamp_factor = True
            deep.inputs[6].default_value = (*(c * 0.28 for c in image_multiply), 1)
            L.new(tex.outputs["Alpha"], deep.inputs["Factor"])
            L.new(mul.outputs[2], deep.inputs[7])
            L.new(deep.outputs[2], em.inputs["Color"])
        else:
            L.new(mul.outputs[2], em.inputs["Color"])
    else:
        em.inputs["Color"].default_value = (*colour, 1)
        if shade_from_normal is not None:
            # Cloth relief from the garment's normal map: light from above-front.
            nm = N.new("ShaderNodeTexImage"); nm.image = shade_from_normal
            shade_from_normal.colorspace_settings.name = "Non-Color"
            sep = N.new("ShaderNodeSeparateXYZ")
            vm = N.new("ShaderNodeVectorMath"); vm.operation = "MULTIPLY"; vm.inputs[1].default_value = (2, 2, 2)
            L.new(nm.outputs["Color"], vm.inputs[0])
            vs = N.new("ShaderNodeVectorMath"); vs.operation = "SUBTRACT"; vs.inputs[1].default_value = (1, 1, 1)
            L.new(vm.outputs[0], vs.inputs[0])
            dot = N.new("ShaderNodeVectorMath"); dot.operation = "DOT_PRODUCT"; dot.inputs[1].default_value = (0.25, 0.45, 0.86)
            L.new(vs.outputs[0], dot.inputs[0])
            rng = N.new("ShaderNodeMapRange"); rng.inputs["From Min"].default_value = 0.4; rng.inputs["From Max"].default_value = 1.0
            rng.inputs["To Min"].default_value = 0.62; rng.inputs["To Max"].default_value = 1.05
            L.new(dot.outputs["Value"], rng.inputs["Value"])
            mul = N.new("ShaderNodeMix"); mul.data_type = "RGBA"; mul.blend_type = "MULTIPLY"; mul.inputs["Factor"].default_value = 1
            mul.inputs[6].default_value = (*colour, 1)
            comb = N.new("ShaderNodeCombineColor")
            for k in range(3):
                L.new(rng.outputs["Result"], comb.inputs[k])
            L.new(comb.outputs[0], mul.inputs[7])
            L.new(mul.outputs[2], em.inputs["Color"])
    # alpha twin
    am = bpy.data.materials.new(name + "_alpha")
    ant = am.node_tree; ant.nodes.clear()
    ao = ant.nodes.new("ShaderNodeOutputMaterial"); ae = ant.nodes.new("ShaderNodeEmission")
    ant.links.new(ae.outputs[0], ao.inputs["Surface"])
    if alpha_image is not None:
        at = ant.nodes.new("ShaderNodeTexImage"); at.image = alpha_image
        ant.links.new(at.outputs["Alpha"], ae.inputs["Color"])
    else:
        ae.inputs["Color"].default_value = (1, 1, 1, 1)
    return mat


def mask_material(name, rgb):
    mat = bpy.data.materials.new(name)
    nt = mat.node_tree; nt.nodes.clear()
    o = nt.nodes.new("ShaderNodeOutputMaterial"); e = nt.nodes.new("ShaderNodeEmission")
    e.inputs["Color"].default_value = (*rgb, 1)
    nt.links.new(e.outputs[0], o.inputs["Surface"])
    return mat


def face_material(name, skin_image, eyes):
    """Skin with brows, a lip line and a soft cheek warmth painted at the eye bones:
    MakeHuman's brows are alpha cards, which cannot bake onto skin."""
    mat = flat_material(name, image=skin_image)
    nt = mat.node_tree
    N, L = nt.nodes, nt.links
    em = next(n for n in N if n.type == "EMISSION")
    colour = em.inputs["Color"].links[0].from_socket
    tc = N.new("ShaderNodeTexCoord")
    for side, eye in eyes.items():
        centre = eye + Vector((0.0, -0.004, 0.024))
        off = N.new("ShaderNodeVectorMath"); off.operation = "SUBTRACT"; off.inputs[1].default_value = tuple(centre)
        L.new(tc.outputs["Object"], off.inputs[0])
        sc = N.new("ShaderNodeVectorMath"); sc.operation = "DIVIDE"; sc.inputs[1].default_value = (0.024, 0.05, 0.0055)
        L.new(off.outputs[0], sc.inputs[0])
        ln = N.new("ShaderNodeVectorMath"); ln.operation = "LENGTH"
        L.new(sc.outputs[0], ln.inputs[0])
        rng = N.new("ShaderNodeMapRange"); rng.inputs["From Min"].default_value = 0.6; rng.inputs["From Max"].default_value = 1.0
        rng.inputs["To Min"].default_value = 0.55; rng.inputs["To Max"].default_value = 0.0
        L.new(ln.outputs["Value"], rng.inputs["Value"])
        mix = N.new("ShaderNodeMix"); mix.data_type = "RGBA"; mix.clamp_factor = True
        L.new(rng.outputs["Result"], mix.inputs["Factor"]); L.new(colour, mix.inputs[6])
        mix.inputs[7].default_value = (0.05, 0.035, 0.028, 1)
        colour = mix.outputs[2]
    L.new(colour, em.inputs["Color"])
    return mat


# ── assembly ───────────────────────────────────────────────────────────────

def hair_shell(ob, height):
    """Turn MakeHuman's hair cards into a solid head of hair.

    The cards are single-sided planes with an alpha texture. Drawn opaque, and
    decimated to a crowd's triangle budget, they read as a stack of flat slabs
    at 2-3 m - the oldest complaint against a near fan, and 6 mm of thickness
    in round 5 only made the slabs thicker. A voxel remesh closes the cards
    into one surface at the hair's own scale, so a fringe is a fringe and an
    afro is a dome, and the style each CC0 asset carries survives: nothing is
    invented, the shape is the one MakeHuman shipped.

    The shell has no UVs; build.py projects it into its own cell rectangle and
    bakes the cards' own colour onto it from the full-resolution copy.
    """
    k = height / 1.75
    thick = ob.modifiers.new("hairThickness", "SOLIDIFY")
    thick.thickness = 0.016 * k            # the shell closes around this; a voxel wider than it eats the hair
    thick.offset = 0.0
    remesh = ob.modifiers.new("hairShell", "REMESH")
    remesh.mode = "VOXEL"
    remesh.voxel_size = 0.006 * k          # half the thickness: coarser than that and an afro disappears
    remesh.adaptivity = 0.15
    smooth = ob.modifiers.new("hairSmooth", "SMOOTH")
    smooth.factor = 0.6
    smooth.iterations = 3
    bpy.context.view_layer.objects.active = ob
    for m in ("hairThickness", "hairShell", "hairSmooth"):
        bpy.ops.object.modifier_apply(modifier=m)
    # A shell of a few hundred triangles: the fan's own decimate takes it from here.
    tris = sum(len(poly.vertices) - 2 for poly in ob.data.polygons)
    if tris > 900:
        dec = ob.modifiers.new("hairTrim", "DECIMATE")
        dec.ratio = 900 / tris
        bpy.ops.object.modifier_apply(modifier="hairTrim")
    for poly in ob.data.polygons:
        poly.use_smooth = True
    # A remesh throws the fitted asset's weights away, and an unweighted part stays at the
    # rest pose while its fan sits down. Hair belongs to the head, so weight it there.
    for group in list(ob.vertex_groups):
        ob.vertex_groups.remove(group)
    ob.vertex_groups.new(name="head").add(list(range(len(ob.data.vertices))), 1.0, "REPLACE")


def _apply_modifiers(ob, keep=("ARMATURE",)):
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    if ob.data.shape_keys:
        bpy.ops.object.shape_key_remove(all=True, apply_mix=True)
    for m in list(ob.modifiers):
        if m.type in keep:
            ob.modifiers.remove(m)
            continue
        try:
            bpy.ops.object.modifier_apply(modifier=m.name)
        except RuntimeError:
            ob.modifiers.remove(m)


def _verts(obs):
    """World-space vertices of every object in `obs`."""
    out = []
    for ob in obs:
        W = ob.matrix_world
        out.extend(W @ v.co for v in ob.data.vertices)
    return out


def scale_to_height(rig, obs, height, target):
    """MPFB's height macro is gender-dependent (a female at 0.5 is 1.23-2.29 m
    across the range, a male 1.37-2.43 m), so the cast's height is met by
    probing the built body and scaling everything about the floor."""
    s = target / height
    for ob in obs:
        ob.data.transform(Matrix.Scale(s, 4))
    bpy.ops.object.select_all(action="DESELECT")
    rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode="EDIT")
    for eb in rig.data.edit_bones:
        eb.head *= s
        eb.tail *= s
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.context.view_layer.update()
    return s


def measure_head(base, bones):
    """The cranium a hat has to fit: above the brows, clear of the ears."""
    eye = (bones["eye.L"].head_local + bones["eye.R"].head_local) / 2
    vs = [v for v in _verts([base]) if v.z > eye.z - 0.01 and abs(v.x) < 0.2]
    top = max(v.z for v in vs)
    temple = [v for v in vs if eye.z + 0.03 < v.z < eye.z + 0.065] or vs
    cranium = [v for v in vs if v.z > eye.z + 0.02]
    return {
        "eye": eye, "brow": eye.z + 0.022, "top": top,
        "rx": max(abs(v.x) for v in temple),
        "front": min(v.y for v in cranium), "back": max(v.y for v in cranium),
    }


# Crown radii fan.hat builds at k = 1: 0.094, 0.108, 0.112 times HEAD_SCALE, on a centre 0.018 above c.
_CROWN = (0.094 * F.HEAD_SCALE, 0.108 * F.HEAD_SCALE, 0.112 * F.HEAD_SCALE)


def fitted_hat(f, head, hair):
    """fan.hat's cap, visor or beanie, stretched per axis onto this MPFB head.

    The kit's hats were drawn around the scripted head's centre and scale; on a
    measured MakeHuman head they floated a hand's width high and a size too
    big. Built at k = 1 around the origin, then scaled so the crown clears the
    temples and the back of the skull, and the rim sits at the brows."""
    ob = F.hat({**f, "height": 1.75}, Vector((0, 0, 0)))
    if ob is None:
        return None
    margin = 0.012 if hair else 0.007
    sx = (head["rx"] + margin) / _CROWN[0]
    sy = ((head["back"] - head["front"]) / 2 + margin) / _CROWN[1]
    # The crown's rim is ~0.020 above c and its top 0.139: rim at the brows, top just over the scalp.
    sz = (head["top"] + margin - head["brow"]) / (0.018 + _CROWN[2] - 0.020)
    c = Vector((0.0, (head["front"] + head["back"]) / 2, head["brow"] - 0.020 * sz))
    for v in ob.data.vertices:
        v.co = Vector((v.co.x * sx, v.co.y * sy, v.co.z * sz)) + c
    return ob


def fitted_scarf(f, base, suit, bones):
    """A knit club scarf on this body: a loop resting on the trapezius, dipping
    to the breastbone in front, and two tails that drape over whatever the fan
    wears.

    MakeHuman's neck is short: the chin hangs 2 cm above `neck01`'s head, so a
    loop at the neck bone met the mouth as soon as a pose tipped the head
    forward. The loop is measured from the body's cross-section just under the
    neck and kept a hand's width below the chin in front."""
    if not f.get("scarf"):
        return None
    import bmesh
    n0 = bones["neck01"].head_local
    chin = bones["jaw"].tail_local
    body = _verts([base])
    slab = [v for v in body if abs(v.z - (n0.z - 0.02)) < 0.008 and abs(v.x) < 0.11] or \
           [v for v in body if abs(v.z - n0.z) < 0.01 and abs(v.x) < 0.11]
    cy = (min(v.y for v in slab) + max(v.y for v in slab)) / 2
    rx = max(abs(v.x) for v in slab) + 0.02
    ry = (max(v.y for v in slab) - min(v.y for v in slab)) / 2 + 0.026
    back_z = n0.z - 0.004
    front_z = min(n0.z - 0.055, chin.z - 0.085)
    cloth = _verts([suit]) if suit else [v for v in body if v.z < front_z]
    bm = bmesh.new()
    seg = 18
    rings = []
    for h in (0.0, 0.03):
        ring = []
        for a in range(seg):
            t = 2 * math.pi * a / seg
            back = (math.cos(t) + 1) / 2            # t = 0 behind the neck (+Y), pi in front
            z = front_z + (back_z - front_z) * back
            ring.append(bm.verts.new((rx * math.sin(t), cy + ry * math.cos(t) - 0.01 * (1 - back) * (h > 0), z + h)))
        rings.append(ring)
    for a in range(seg):
        b = (a + 1) % seg
        bm.faces.new((rings[0][a], rings[0][b], rings[1][b], rings[1][a]))
    for x in (0.034, -0.046):
        near = [v for v in cloth if abs(v.x - x) < 0.035]
        column = []
        z = front_z + 0.02
        hang = cy - ry + 0.01
        while z > front_z - 0.32:
            band = [v.y for v in near if abs(v.z - z) < 0.02]
            # A tail drapes: it follows the chest out, then falls straight past anything below.
            if band:
                hang = min(hang, min(band) - 0.012)
            column.append((z, hang))
            z -= 0.03
        left = [bm.verts.new((x - 0.031, y, z)) for z, y in column]
        right = [bm.verts.new((x + 0.031, y, z)) for z, y in column]
        for k in range(len(column) - 1):
            bm.faces.new((left[k], right[k], right[k + 1], left[k + 1]))
    me = bpy.data.meshes.new(f"{f['id']}_scarf")
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(me.name, me)
    bpy.context.scene.collection.objects.link(ob)
    sol = ob.modifiers.new("thick", "SOLIDIFY")
    sol.thickness = 0.011
    _apply_modifiers(ob, keep=())
    ob["collar"] = front_z + 0.03
    return ob


def paint_scarf(ob, collar):
    """Primary on the loop, bars of primary and secondary down the tails."""
    me = ob.data
    base, tint = F._corner_attrs(ob)
    for p in me.polygons:
        z = (ob.matrix_world @ p.center).z
        band = int((collar - z) / 0.045)
        mask = (1, 0, 0) if z > collar - 0.01 or band % 2 == 0 else (0, 1, 0)
        F._set_face(me, base, tint, p, F.TINTED, mask)


def fitted_prop(f, bones):
    """fan.accessory's prop, held in the right hand's own frame.

    The kit authors a prop around a fingertip with the hand hanging straight
    down and the fan facing -Y. MakeHuman's rest hand angles forward and out,
    so the prop is turned from that frame into the wrist's before it is
    weighted to the wrist, and follows the hand into every pose."""
    ob = F.accessory({**f, "height": 1.75}, {**F.joints({**f, "height": 1.75}), "hand_end.R": Vector((0, 0, 0))})
    if ob is None:
        return None
    F.paint_prop(ob, ob.get("prop", ""))                 # in the prop's own frame, before it moves
    tip = bones["finger3-3.R"].tail_local
    wrist = bones["wrist.R"].head_local
    d = (tip - wrist).normalized()
    # Anchored where the kit's fingertip is, but a fist is a palm shorter than an
    # open hand: anchoring at the open fingertip left a phone floating past the fist.
    grip = wrist + (tip - wrist) * 0.55
    front = Vector((0, -1, 0))
    front = (front - d * front.dot(d)).normalized()
    x = front.cross(d)
    M = Matrix((x, -front, -d)).transposed()          # columns: kit x, kit y, kit z
    for v in ob.data.vertices:
        v.co = grip + M @ v.co
    return ob


def assemble(f: dict, index: int):
    """One MPFB fan at the cast's height. Returns (mesh, rig, J, info) like rig.assemble."""
    HS, TS = enable()
    ident = identity(f, index)
    sex = "female" if ident["female"] else "male"
    base = HS.create_human(macro_detail_dict=json.loads(json.dumps(ident["macros"])), scale=0.1)
    rig = HS.add_builtin_rig(base, "default")
    rig["mpfb"] = True
    rig["prop"] = f.get("accessory", "none")
    skin_dir = SYS / f"skins/{ident['age']}_{ident['ancestry']}_{sex}"
    HS.set_character_skin(str(next(skin_dir.glob("*.mhmat"))), base, skin_type="MAKESKIN")
    suit = SUITS[sex][(index * 5 + 1) % len(SUITS[sex])]
    parts = {"suit": HS.add_mhclo_asset(str(SYS / f"clothes/{suit}/{suit}.mhclo"), base, asset_type="Clothes", subdiv_levels=0)}
    shoes = SHOES[(index * 7 + 2) % len(SHOES)]
    parts["shoes"] = HS.add_mhclo_asset(str(SYS / f"clothes/{shoes}/{shoes}.mhclo"), base, asset_type="Clothes", subdiv_levels=0)
    hair = HAIR[sex].get(f["hair"]) if f["hat"] in ("none", "visor") or f["hair"] in ("long", "ponytail") else HAIR[sex].get("buzz")
    if hair:
        parts["hair"] = HS.add_mhclo_asset(str(SYS / f"hair/{hair}/{hair}.mhclo"), base, asset_type="Hair", subdiv_levels=0)
        # The shell is built after the fit and the height scale are baked (below): remeshed
        # here it would freeze at the asset's unfitted size and float above the head.
    parts["eyes"] = HS.add_mhclo_asset(str(SYS / "eyes/low-poly/low-poly.mhclo"), base, asset_type="Eyes", subdiv_levels=0)
    teeth = SYS / "teeth/teeth_base/teeth_base.mhclo"
    if teeth.exists():
        try:
            parts["teeth"] = HS.add_mhclo_asset(str(teeth), base, asset_type="Teeth", subdiv_levels=0)
        except Exception as e:                        # an MPFB without a teeth type still builds a fan
            print("[crowd] no teeth:", e)

    # Bake morphs and masks, so the geometry is what the kit ships.
    TS.bake_targets(base)
    for ob in [base, *[p for p in parts.values() if p]]:
        _apply_modifiers(ob)
    for ob in [base, *[p for p in parts.values() if p]]:
        ob.parent = None
        ob.matrix_world = Matrix.Identity(4)

    # Probe, then scale to the cast's height.
    built = max(v.z for v in _verts([base]))
    scale = scale_to_height(rig, [base, *[p for p in parts.values() if p]], built, f["height"])
    height = f["height"]
    if parts.get("hair"):
        hair_shell(parts["hair"], f["height"])
    bones = rig.data.bones
    W = rig.matrix_world
    eyes = {s: W @ bones[f"eye.{s}"].head_local for s in ("L", "R")}
    J = {
        "head": W @ bones["head"].head_local,
        "neck": W @ bones["neck01"].head_local, "pelvis": W @ bones["root"].head_local,
        "hand_end.R": W @ bones["finger3-3.R"].tail_local, "hand_end.L": W @ bones["finger3-3.L"].tail_local,
        "ankle.L": W @ bones["foot.L"].head_local, "ankle.R": W @ bones["foot.R"].head_local,
    }
    head = measure_head(base, bones)
    J["head_top"] = Vector((0.0, (head["front"] + head["back"]) / 2, head["top"]))
    k = height / 1.75
    skin_img = _diffuse_image(base.active_material)
    waist = J["pelvis"].z + 0.03 * k
    club = f["club"]
    neutral = F.hex_rgb(f["top_neutral"])
    # Base (albedo) materials, tint (mask) materials, and the part each face belongs to.
    for ob, role in [(base, "skin"), *[(p, r) for r, p in parts.items() if p]]:
        src = ob.active_material
        name = f"{f['id']}_{role}"
        ob.data.materials.clear()
        if role == "skin":
            ob.data.materials.append(face_material(f"{name}_base", skin_img, eyes))
            ob.data.materials.append(mask_material(f"{name}_tint", (0, 0, 0)))
        elif role == "suit":
            # Slot 0: trousers keep their texture. Slot 1: the top, generated cloth.
            pants = flat_material(f"{f['id']}_pants_base", image=_diffuse_image(src))
            top = flat_material(f"{f['id']}_top_base", colour=F.TINTED if club else neutral, shade_from_normal=_normal_image(src))
            ob.data.materials.append(pants); ob.data.materials.append(top)
            ob.data.materials.append(mask_material(f"{f['id']}_pants_tint", (0, 0, 0)))
            ob.data.materials.append(mask_material(f"{f['id']}_top_tint", (1, 0, 0) if club else (0, 0, 0)))
            for p in ob.data.polygons:
                p.material_index = 1 if (ob.matrix_world @ p.center).z > waist else 0
            continue
        elif role == "hair":
            img = _diffuse_image(src)
            ob.data.materials.append(flat_material(f"{name}_base", image=img, image_multiply=tuple(min(1, c * 2.4) for c in F.hex_rgb(f["hair_colour"])), alpha_image=img))
            ob.data.materials.append(mask_material(f"{name}_tint", (0, 0, 0)))
        else:
            img = _diffuse_image(src)
            ob.data.materials.append(flat_material(f"{name}_base", image=img) if img else flat_material(f"{name}_base", colour=(0.2, 0.2, 0.2)))
            ob.data.materials.append(mask_material(f"{name}_tint", (0, 0, 0)))
        for p in ob.data.polygons:
            p.material_index = 0

    # Hats, scarves and props: fitted to this head, this neck and chest, this hand.
    import common
    extras = []
    ht = fitted_hat(f, head, bool(hair))
    if ht:
        F.paint_flat(ht, F.TINTED, (1, 0, 0))
        extras.append((ht, "head"))
    sc = fitted_scarf(f, base, parts.get("suit"), bones)
    if sc:
        paint_scarf(sc, sc["collar"])
        extras.append((sc, "spine01"))
    pr = fitted_prop(f, bones)
    if pr:
        extras.append((pr, "wrist.R"))
    for ob, bone in extras:
        ob.data.materials.append(common.attr_material(f"{ob.name}_base", None, "none", mode="base"))
        ob.data.materials.append(common.attr_material(f"{ob.name}_tint", None, "none", mode="tint"))

    # Every part's vertices follow the rig: MPFB parts by their own weights, extras rigidly.
    mesh = base
    for ob, bone in extras:
        g = ob.vertex_groups.new(name=bone)
        g.add(list(range(len(ob.data.vertices))), 1.0, "REPLACE")
    objs = [base, *[p for p in parts.values() if p], *[e[0] for e in extras]]
    bpy.ops.object.select_all(action="DESELECT")
    for ob in objs:
        ob.select_set(True)
    bpy.context.view_layer.objects.active = base
    bpy.ops.object.join()
    mesh.name = f["id"]
    mesh.data.name = f["id"]
    for m in list(mesh.modifiers):
        mesh.modifiers.remove(m)
    mod = mesh.modifiers.new("rig", "ARMATURE")
    mod.object = rig
    mesh.parent = rig
    mesh.matrix_parent_inverse = rig.matrix_world.inverted()
    info = {"height": height, "built": built, "scale": scale, "identity": ident, "suit": suit, "shoes": shoes,
            "hair": hair, "skin": skin_dir.name, "head": {k2: (list(v) if isinstance(v, Vector) else v) for k2, v in head.items()}}
    return mesh, rig, J, info


# ── posing ─────────────────────────────────────────────────────────────────

CHAINS = {
    "spine": ["spine05", "spine04", "spine03"], "chest": ["spine02", "spine01"],
    "neck": ["neck01", "neck02", "neck03"], "head": ["head"],
    "upperarm.L": ["upperarm01.L", "upperarm02.L"], "forearm.L": ["lowerarm01.L", "lowerarm02.L"], "hand.L": ["wrist.L"],
    "upperarm.R": ["upperarm01.R", "upperarm02.R"], "forearm.R": ["lowerarm01.R", "lowerarm02.R"], "hand.R": ["wrist.R"],
    "thigh.L": ["upperleg01.L", "upperleg02.L"], "shin.L": ["lowerleg01.L", "lowerleg02.L"], "foot.L": ["foot.L"],
    "thigh.R": ["upperleg01.R", "upperleg02.R"], "shin.R": ["lowerleg01.R", "lowerleg02.R"], "foot.R": ["foot.R"],
}
FIST_POSES = {"cheer_a", "cheer_b", "pump_a", "pump_b"}
OPEN_MOUTH = {"cheer_a": 16, "cheer_b": 12, "clap_b": 7, "pump_a": 14, "pump_b": 10}


def _chair_tokens():
    C = json.loads((ROOT / "design/tokens.json").read_text())["visual"]["crowd"]["chair"]
    return C


def solve_legs(rig, height, sitting_hips_z):
    """Thigh and shin directions that sit a fan's feet on the tread and keep them there.

    Bowl gives each row `seating.feetDepth` of tread in front of the chair
    (0.38 yd, 0.35 m). Aiming only at the tread's height let the ankle fall
    where it liked, and at integration-12 the shoes of the nearest fan hung
    over the edge above the row below. So both the height and the distance are
    solved: the ankle goes `ankleForwardMetres` in front of the chair's origin,
    which leaves the whole shoe inside the tread, and the knee bends forward
    from a two-bone solve rather than the shin being tipped until it reaches.
    """
    ch = _chair_tokens()
    k = height / 1.75
    lift = ch["pelvisMetres"] - ch["kitPelvisMetres"] * k
    b = rig.data.bones
    Lt = (b["upperleg01.L"].head_local - b["lowerleg01.L"].head_local).length
    Ls = (b["lowerleg01.L"].head_local - b["foot.L"].head_local).length
    hip = Vector((0.0, 0.0, sitting_hips_z - 0.01 * k))
    # In the kit's frame the fan faces -Y, so forward of the chair is -Y.
    ankle = Vector((0.0, -ch.get("ankleForwardMetres", 0.10) * k, 0.085 - lift))
    to = ankle - hip
    d = min(to.length, (Lt + Ls) * 0.985)
    if d < 1e-4:
        return (0.08, -1.0, 0.05), (0.03, 0.2, -1.0)
    u = to.normalized()
    cos_a = max(-1.0, min(1.0, (Lt * Lt + d * d - Ls * Ls) / (2 * Lt * d)))
    a = math.acos(cos_a)
    # The knee bends forward, in the plane of the hip and the ankle.
    forward = Vector((0.0, -1.0, 0.0))
    bend = (forward - u * forward.dot(u))
    bend = bend.normalized() if bend.length > 1e-6 else Vector((0.0, -1.0, 0.0))
    knee = hip + (u * math.cos(a) + bend * math.sin(a)) * Lt
    thigh = (knee - hip).normalized()
    shin = (ankle - knee).normalized()
    return (0.08, thigh.y, thigh.z), (0.03, shin.y, shin.z)


def _head(rig, name):
    return rig.pose.bones[name].head.copy()


def _reach_target(rig, kind, t, side, k):
    """Where a hand rests, in armature space, read off the posed body."""
    sx = 1 if side == "L" else -1
    hip = _head(rig, f"upperleg01.{side}")
    knee = _head(rig, f"lowerleg01.{side}")
    root = _head(rig, "root")
    if kind == "thigh":
        # On top of the thigh: the bone runs through its middle, the hand sits on the cloth.
        return hip.lerp(knee, t) + Vector((sx * 0.012, 0.0, 0.075 * k))
    if kind == "knee":
        return knee + Vector((-sx * 0.02, 0.02, 0.07 * k))
    if kind == "lap":
        other = "R" if side == "L" else "L"
        mid = hip.lerp(knee, t).lerp(_head(rig, f"upperleg01.{other}").lerp(_head(rig, f"lowerleg01.{other}"), t), 0.5)
        return mid + Vector((sx * 0.03, 0.0, 0.085 * k))
    if kind == "armrest":
        # Bowl's armrests sit half a seat pitch out (0.25 m), about 0.19 m over the pan, forward of the hips.
        return Vector((sx * 0.235, root.y - 0.13, root.z + 0.17 * k))
    if kind == "hip":
        return Vector((sx * 0.19 * k, root.y + 0.01, root.z + 0.09 * k))
    if kind == "fold":
        chest = _head(rig, "spine01")
        return Vector((-sx * 0.12 * k, chest.y - 0.16 * k, chest.z - 0.02 * k))
    return None


def _aim(rig, names, direction):
    d = Vector(direction).normalized()
    for name in names:
        pb = rig.pose.bones[name]
        rest = pb.bone.matrix_local
        rest_dir = (pb.bone.tail_local - pb.bone.head_local).normalized()
        q = rest_dir.rotation_difference(d)
        m = q.to_matrix().to_4x4() @ rest.to_3x3().to_4x4()
        m.translation = pb.head.copy()
        pb.matrix = m
        bpy.context.view_layer.update()


def solve_arm(rig, side, target, k):
    """Two-bone reach: upper arm and forearm lengths from the rig, the elbow
    out to the side and a little back, the hand laid along the forearm."""
    sx = 1 if side == "L" else -1
    b = rig.data.bones
    s0 = _head(rig, f"upperarm01.{side}")
    Lu = (b[f"lowerarm01.{side}"].head_local - b[f"upperarm01.{side}"].head_local).length
    Lf = (b[f"wrist.{side}"].head_local - b[f"lowerarm01.{side}"].head_local).length
    to = target - s0
    dist = min(to.length, (Lu + Lf) * 0.985)
    to = to.normalized()
    # Law of cosines: the elbow's angle off the shoulder-to-hand line.
    cos_a = max(-1.0, min(1.0, (Lu * Lu + dist * dist - Lf * Lf) / (2 * Lu * dist)))
    a = math.acos(cos_a)
    hint = Vector((sx * 0.8, 0.35, -0.5))
    bend = (hint - to * hint.dot(to)).normalized()
    elbow = s0 + (to * math.cos(a) + bend * math.sin(a)) * Lu
    hand = s0 + to * dist
    _aim(rig, [f"upperarm01.{side}", f"upperarm02.{side}"], elbow - s0)
    _aim(rig, [f"lowerarm01.{side}", f"lowerarm02.{side}"], hand - elbow)
    fore = (hand - elbow).normalized()
    _aim(rig, [f"wrist.{side}"], (fore + Vector((0, 0, -0.55))).normalized())


def twist_upper_body(rig, degrees):
    """Turn chest, neck and head about the vertical, parents first, so the
    head ends up `degrees` round: positive to the fan's left."""
    if not degrees:
        return
    for name, share in (("spine01", 0.2), ("neck01", 0.35), ("head", 0.45)):
        pb = rig.pose.bones[name]
        h = pb.head.copy()
        R = Matrix.Translation(h) @ Matrix.Rotation(math.radians(degrees * share), 4, "Z") @ Matrix.Translation(-h)
        pb.matrix = R @ pb.matrix
        bpy.context.view_layer.update()


def apply_pose(rig, dirs: dict, hips, height: float, pose_name: str = "", reach=None, twist=0):
    """Aim MPFB's chains along the kit's bone directions (armature space, -Y front)."""
    k = height / 1.75
    for pb in rig.pose.bones:
        pb.matrix_basis = Matrix.Identity(4)
    bpy.context.view_layer.update()
    sitting = hips is not None and hips[2] < 0.7
    if hips is not None:
        root = rig.pose.bones["root"]
        rest = root.bone.matrix_local.copy()
        # keep the root's rest rotation; move only its head
        root.matrix = Matrix.Translation(Vector(hips) * k - rest.translation) @ rest
        bpy.context.view_layer.update()
    if sitting:
        thigh, shin = solve_legs(rig, height, hips[2] * k)
        dirs = {**dirs, "thigh.L": thigh, "shin.L": shin, "thigh.R": (-thigh[0], thigh[1], thigh[2]), "shin.R": (-shin[0], shin[1], shin[2])}
    order = [pb for pb in rig.pose.bones]            # parents before children
    targets = {}
    for key, chain in CHAINS.items():
        if key in dirs:
            for name in chain:
                targets[name] = Vector(dirs[key]).normalized()
    for pb in order:
        if pb.name not in targets:
            continue
        rest = pb.bone.matrix_local
        rest_dir = (pb.bone.tail_local - pb.bone.head_local).normalized()
        q = rest_dir.rotation_difference(targets[pb.name])
        m = q.to_matrix().to_4x4() @ rest.to_3x3().to_4x4()
        m.translation = pb.head.copy()
        pb.matrix = m
        bpy.context.view_layer.update()
    for key, (kind, t) in (reach or {}).items():
        side = key[-1]
        target = _reach_target(rig, kind, t, side, k)
        if target is not None:
            solve_arm(rig, side, target, k)
    twist_upper_body(rig, twist)
    # Hands: relaxed curl, fists on a cheer, flatter where they rest on something. Mouth open on a cheer.
    resting = bool(reach)
    curl = math.radians(62 if pose_name in FIST_POSES else (12 if resting else 22))
    for pb in rig.pose.bones:
        if pb.name.startswith("finger") and not pb.name.startswith("finger1"):
            pb.rotation_mode = "XYZ"; pb.rotation_euler = (curl, 0, 0)
        elif pb.name.startswith("finger1"):
            pb.rotation_mode = "XYZ"; pb.rotation_euler = (curl * 0.5, 0, 0)
    if "jaw" in rig.pose.bones:
        jaw = rig.pose.bones["jaw"]
        jaw.rotation_mode = "XYZ"; jaw.rotation_euler = (math.radians(OPEN_MOUTH.get(pose_name, 2)), 0, 0)
    bpy.context.view_layer.update()
