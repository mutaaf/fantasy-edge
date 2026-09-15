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
    "female": ["female_casualsuit01", "female_casualsuit02", "female_sportsuit01"],
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


def assemble(f: dict, index: int):
    """One MPFB fan. Returns (mesh, rig, J, info) like rig.assemble."""
    HS, TS = enable()
    ident = identity(f, index)
    sex = "female" if ident["female"] else "male"
    base = HS.create_human(macro_detail_dict=json.loads(json.dumps(ident["macros"])), scale=0.1)
    rig = HS.add_builtin_rig(base, "default")
    rig["mpfb"] = True
    skin_dir = SYS / f"skins/{ident['age']}_{ident['ancestry']}_{sex}"
    HS.set_character_skin(str(next(skin_dir.glob("*.mhmat"))), base, skin_type="MAKESKIN")
    suit = SUITS[sex][(index * 5 + 1) % len(SUITS[sex])]
    parts = {"suit": HS.add_mhclo_asset(str(SYS / f"clothes/{suit}/{suit}.mhclo"), base, asset_type="Clothes", subdiv_levels=0)}
    shoes = SHOES[(index * 7 + 2) % len(SHOES)]
    parts["shoes"] = HS.add_mhclo_asset(str(SYS / f"clothes/{shoes}/{shoes}.mhclo"), base, asset_type="Clothes", subdiv_levels=0)
    hair = HAIR[sex].get(f["hair"]) if f["hat"] in ("none", "visor") or f["hair"] in ("long", "ponytail") else HAIR[sex].get("buzz")
    if hair:
        parts["hair"] = HS.add_mhclo_asset(str(SYS / f"hair/{hair}/{hair}.mhclo"), base, asset_type="Hair", subdiv_levels=0)
    parts["eyes"] = HS.add_mhclo_asset(str(SYS / "eyes/low-poly/low-poly.mhclo"), base, asset_type="Eyes", subdiv_levels=0)

    bones = rig.data.bones
    height = base.dimensions.z
    k = height / 1.75
    eyes = {s: rig.matrix_world @ bones[f"eye.{s}"].head_local for s in ("L", "R")}
    # Joints in the kit's names, for fan.py's hats, scarves and props.
    W = rig.matrix_world
    J = {
        "head": W @ bones["head"].head_local,
        "neck": W @ bones["neck01"].head_local, "pelvis": W @ bones["root"].head_local,
        "hand_end.R": W @ bones["finger3-3.R"].tail_local, "hand_end.L": W @ bones["finger3-3.L"].tail_local,
        "ankle.L": W @ bones["foot.L"].head_local, "ankle.R": W @ bones["foot.R"].head_local,
    }

    # Bake morphs and masks, so the geometry is what the kit ships.
    TS.bake_targets(base)
    for ob in [base, *[p for p in parts.values() if p]]:
        _apply_modifiers(ob)

    head_verts = [base.matrix_world @ v.co for v in base.data.vertices if (base.matrix_world @ v.co).z > (W @ bones["neck03"].tail_local).z]
    lo = Vector((min(p.x for p in head_verts), min(p.y for p in head_verts), min(p.z for p in head_verts)))
    hi = Vector((max(p.x for p in head_verts), max(p.y for p in head_verts), max(p.z for p in head_verts)))
    head_centre = (lo + hi) / 2
    J["head_top"] = Vector((head_centre.x, head_centre.y, hi.z))
    height = hi.z
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

    # Hats, scarves and props from the kit's own builders, fitted to this head and neck.
    extras = []
    c = head_centre + Vector((0, 0, -0.01))
    ht = F.hat(f, c)
    if ht:
        extras.append((ht, "head", F.TINTED, (1, 0, 0)))
    sc = F.scarf(f, F.joints(f))
    if sc:
        sc.location += Vector((0, J["neck"].y - 0.004 * k, J["neck"].z + 0.03 - 1.455 * k))
        extras.append((sc, "neck01", None, None))
    pr = F.accessory(f, {**F.joints(f), "hand_end.R": J["hand_end.R"]})
    if pr:
        extras.append((pr, "wrist.R", None, None))
    for ob, bone, rgb, mask in extras:
        _apply_modifiers(ob)
        role = ob.name.split("_")[-1]
        if rgb is not None:
            F.paint_flat(ob, rgb, mask)
        elif role == "scarf":
            F.paint_scarf(ob, f)
        else:
            F.paint_prop(ob, ob.get("prop", ""))
        import common
        ob.data.materials.append(common.attr_material(f"{ob.name}_base", None, "none", mode="base"))
        ob.data.materials.append(common.attr_material(f"{ob.name}_tint", None, "none", mode="tint"))
        g = ob.vertex_groups.new(name=bone)
        g.add(list(range(len(ob.data.vertices))), 1.0, "REPLACE")

    # One mesh; two slots per part (base, tint), faces on the base slot.
    objs = [base, *[p for p in parts.values() if p], *[e[0] for e in extras]]
    bpy.ops.object.select_all(action="DESELECT")
    for ob in objs:
        ob.select_set(True)
    bpy.context.view_layer.objects.active = base
    bpy.ops.object.join()
    mesh = base
    mesh.name = f["id"]
    mesh.data.name = f["id"]
    for m in list(mesh.modifiers):
        mesh.modifiers.remove(m)
    mod = mesh.modifiers.new("rig", "ARMATURE")
    mod.object = rig
    mesh.parent = rig
    mesh.matrix_parent_inverse = rig.matrix_world.inverted()
    info = {"height": height, "identity": ident, "suit": suit, "shoes": shoes, "hair": hair,
            "skin": skin_dir.name}
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
    """Thigh and shin directions that put a seated fan's ankles on the tread.

    The runtime lifts a seated fan by pelvisMetres - kitPelvisMetres * height/1.75,
    so the ankle must sit at tread (0.085 m) minus that lift in the kit's frame.
    Shins tuck back under the chair before they ever reach forward into the row
    in front; if a shin is too short to reach, the thigh tips down instead.
    """
    ch = _chair_tokens()
    k = height / 1.75
    lift = ch["pelvisMetres"] - ch["kitPelvisMetres"] * k
    target = 0.085 - lift
    b = rig.data.bones
    Lt = (b["upperleg01.L"].head_local - b["lowerleg01.L"].head_local).length
    Ls = (b["lowerleg01.L"].head_local - b["foot.L"].head_local).length
    hip = sitting_hips_z - 0.01 * k
    a = math.radians(4)                          # thigh a little down from level
    knee = hip - Lt * math.sin(a)
    need = knee - target
    if need > Ls:                                # shin cannot reach: tip the thigh down
        a = math.asin(min(1.0, max(-1.0, (hip - target - Ls * 0.99) / Lt)))
        knee = hip - Lt * math.sin(a)
        need = knee - target
    cosb = max(-1.0, min(1.0, need / Ls))
    tilt = math.acos(cosb)                       # 0 = shin vertical
    back = min(tilt, math.radians(28))
    thigh = (0.08, -math.cos(a), -math.sin(a))
    shin = (0.03, math.sin(back), -math.cos(back)) if tilt <= math.radians(28) else (0.03, -math.sin(tilt), -math.cos(tilt))
    return thigh, shin


def apply_pose(rig, dirs: dict, hips, height: float, pose_name: str = ""):
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
    # Hands: relaxed curl, fists on a cheer. Mouth open on a cheer. Eyes on the field.
    curl = math.radians(62 if pose_name in FIST_POSES else 22)
    for pb in rig.pose.bones:
        if pb.name.startswith("finger") and not pb.name.startswith("finger1"):
            pb.rotation_mode = "XYZ"; pb.rotation_euler = (curl, 0, 0)
        elif pb.name.startswith("finger1"):
            pb.rotation_mode = "XYZ"; pb.rotation_euler = (curl * 0.5, 0, 0)
    if "jaw" in rig.pose.bones:
        jaw = rig.pose.bones["jaw"]
        jaw.rotation_mode = "XYZ"; jaw.rotation_euler = (math.radians(OPEN_MOUTH.get(pose_name, 2)), 0, 0)
    bpy.context.view_layer.update()
