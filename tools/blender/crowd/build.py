"""Build the crowd kit: 24 fans, LODs, atlases, clips, impostors, manifest.

    blender --background --python tools/blender/crowd/build.py [-- --stage meshes|impostors|all]

Writes to assets/actors/crowd/:
  fanNN.usdz / fanNN.glb     skinned LOD0 + LOD1, 20-joint skeleton, 10 clips
  lod1_poses.usdz / .glb      every fan's LOD1 frozen in each impostor pose,
                              static, for merging a mid-distance ring by pose
  fan_albedo.png, fan_mask.png          UV atlas for the meshes
  impostor_albedo.png, impostor_mask.png, impostor_normal.png
  variation.png               per-seat phase, fan, tint jitter, pose bias
  manifest.json               everything a renderer needs to read the above

The meshes are authored in metres, Z up, facing -Y, origin on the floor under
the pelvis. Both exports convert to +Y up with fans facing +Z, so the .usdz
and its .glb twin share one frame. Everything is deterministic: run it twice, get the same kit.
"""
from __future__ import annotations

import json
import math
import pathlib
import random
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import bpy
import bmesh
import numpy as np
from mathutils import Vector

import common
import fan as F
import poses as P
import rig as R
import specs

OUT = common.OUT
LOD0_TRIS, LOD1_TRIS, LOD2_TRIS = 2400, 650, 250
MESH_ATLAS = 2048                    # baked at 2x, shipped at this size
MESH_COLS, MESH_ROWS = 6, 4          # 24 cells, 341 x 512 px each
IMP_CELL = (64, 128)                 # px per impostor cell
IMP_WORLD = (1.2, 2.4)               # metres a cell covers, pivot at bottom centre
IMP_POSES = ["sit", "sit_b", "stand", "clap_b", "cheer_a", "groan"]
IMP_VIEWS = [0, 45, 90, 135, 180]    # yaw of the fan relative to the viewer; 225..315 mirror 135..45
IMP_ELEVATION = 12.0                 # degrees the camera looks down on a fan
# A far card is two neighbours, not one fan: seats are 0.55 yd (0.503 m) on
# centre, and one fan per card at that density would double the crowd's
# triangles. Cell p holds fan p on the left and pair_mate(p) on the right.
PAIR_OFFSET = 0.2515                 # metres from the cell centre to each fan
PAIR_STEP = 7                        # pair_mate(p) = (7p + 11) mod 24: a permutation with no fixed point


def pair_mate(p, n=24):
    return (PAIR_STEP * p + 11) % n
BAKE_SCALE = 2
AO_STRENGTH = 0.6
AO_WARM = (0.62, 0.42, 0.36)


def log(*a):
    print("[crowd]", *a, flush=True)


# ───────────────────────────── materials ─────────────────────────────

def image(name, w, h, colorspace="sRGB", alpha=False):
    img = bpy.data.images.new(name, w, h, alpha=alpha, float_buffer=False)
    img.colorspace_settings.name = colorspace
    img.generated_color = (0, 0, 0, 0)
    return img


def add_bake_target(mat, img):
    nt = mat.node_tree
    node = nt.nodes.new("ShaderNodeTexImage")
    node.image = img
    node.interpolation = "Closest"
    nt.nodes.active = node
    return node


def runtime_material(name, albedo):
    mat = bpy.data.materials.new(name)
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Roughness"].default_value = 0.85
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = albedo
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(bsdf.outputs[0], out.inputs["Surface"])
    return mat


def emission_material(name, img, colorspace_data=False, normal=False):
    mat = bpy.data.materials.new(name)
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    if normal:
        geo = nt.nodes.new("ShaderNodeNewGeometry")
        vt = nt.nodes.new("ShaderNodeVectorTransform")
        vt.vector_type = "NORMAL"; vt.convert_from = "WORLD"; vt.convert_to = "CAMERA"
        nt.links.new(geo.outputs["Normal"], vt.inputs[0])
        # Blender camera space looks down -Z; flip so +Z faces the viewer.
        flip = nt.nodes.new("ShaderNodeVectorMath"); flip.operation = "MULTIPLY"; flip.inputs[1].default_value = (1, 1, -1)
        nt.links.new(vt.outputs[0], flip.inputs[0])
        half = nt.nodes.new("ShaderNodeVectorMath"); half.operation = "MULTIPLY"; half.inputs[1].default_value = (0.5, 0.5, 0.5)
        nt.links.new(flip.outputs[0], half.inputs[0])
        add = nt.nodes.new("ShaderNodeVectorMath"); add.operation = "ADD"; add.inputs[1].default_value = (0.5, 0.5, 0.5)
        nt.links.new(half.outputs[0], add.inputs[0])
        nt.links.new(add.outputs[0], em.inputs["Color"])
    else:
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = img
        tex.interpolation = "Linear"
        nt.links.new(tex.outputs["Color"], em.inputs["Color"])
    nt.links.new(em.outputs[0], out.inputs["Surface"])
    return mat


# ───────────────────────────── uv + bake ─────────────────────────────

def unwrap_into_cell(mesh, cell):
    """Smart-project, give the head more texels, pack, and move into the atlas cell."""
    bpy.ops.object.select_all(action="DESELECT")
    mesh.select_set(True)
    bpy.context.view_layer.objects.active = mesh
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(60), island_margin=0.004)
    bpy.ops.object.mode_set(mode="OBJECT")
    me = mesh.data
    uv = me.uv_layers.active.data
    head_slots = {i for i, m in enumerate(me.materials) if m and "_head" in m.name}
    # Faces are what people look at in a stand; they get nine times the area.
    if head_slots:
        loops = [li for p in me.polygons if p.material_index in head_slots for li in p.loop_indices]
        if loops:
            pts = np.array([uv[li].uv for li in loops])
            c = pts.mean(axis=0)
            for li in loops:
                uv[li].uv = tuple(c + (np.array(uv[li].uv) - c) * 3.0)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.pack_islands(margin=0.006, rotate=True)
    bpy.ops.object.mode_set(mode="OBJECT")
    # Mode switches rebuild mesh data; a layer fetched before them writes nowhere.
    uv = mesh.data.uv_layers.active.data
    x0, y0, w, h = cell
    for d in uv:
        u, v = d.uv
        d.uv = (x0 + u * w, y0 + v * h)


def bake(mesh, target):
    bpy.ops.object.select_all(action="DESELECT")
    mesh.select_set(True)
    bpy.context.view_layer.objects.active = mesh
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.samples = 4
    sc.render.bake.use_clear = False
    sc.render.bake.margin = 6 * BAKE_SCALE
    bpy.ops.object.bake(type="EMIT", use_clear=False, margin=6 * BAKE_SCALE)


def bake_from(source, target):
    """Bake the source's emission onto the target's UVs, a few millimetres apart."""
    bpy.ops.object.select_all(action="DESELECT")
    source.select_set(True)
    target.select_set(True)
    bpy.context.view_layer.objects.active = target
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.samples = 4
    bpy.ops.object.bake(type="EMIT", use_clear=False, margin=6 * BAKE_SCALE, use_selected_to_active=True,
                        cage_extrusion=0.03, max_ray_distance=0.1)  # decimation moves elbows and fists up to ~8 cm


def bake_ao(source, target, img):
    """Ambient occlusion from the full-resolution body, for the albedo to multiply in."""
    for slot in target.material_slots:
        add_bake_target(slot.material, img)
    bpy.ops.object.select_all(action="DESELECT")
    source.select_set(True)
    target.select_set(True)
    bpy.context.view_layer.objects.active = target
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.samples = 16
    sc.world = sc.world or bpy.data.worlds.new("w")
    sc.world.light_settings.distance = 0.25
    bpy.ops.object.bake(type="AO", use_clear=False, margin=6 * BAKE_SCALE, use_selected_to_active=True,
                        cage_extrusion=0.03, max_ray_distance=0.1)  # decimation moves elbows and fists up to ~8 cm


def soften(ob):
    """Smooth, area-weighted normals; hard only where two parts meet."""
    me = ob.data
    for p in me.polygons:
        p.use_smooth = True
    mod = ob.modifiers.new("wn", "WEIGHTED_NORMAL")
    mod.weight = 50
    mod.keep_sharp = True
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.modifier_apply(modifier="wn")


# The mouth samples a dark patch in the 0.002 gutter every cell keeps free of
# packed islands (see the cell inset in build_meshes), so it paints over nothing.
MOUTH_GUTTER = 0.0012


def add_mouth(mesh, rig, f, J, cell):
    """A dark mouth disc just inside the lips, skinned to the head. Poses open it (see open_mouth)."""
    k = f["height"] / 1.75
    hs = F.HEAD_SCALE
    c = (J["head"] + J["head_top"]) / 2 + Vector((0, -0.010, -0.030)) * k
    centre = c + Vector((0, -0.081, -0.050)) * k * hs
    bm = bmesh.new()
    ring = bmesh.ops.create_circle(bm, cap_ends=True, segments=10, radius=1.0)
    for v in bm.verts:
        v.co = Vector((v.co.x * 0.021, 0.0, v.co.y * 0.006)) * k * hs + centre
    me = bpy.data.meshes.new(f"{f['id']}_mouth")
    bm.to_mesh(me)
    bm.free()
    uv = me.uv_layers.new(name=mesh.data.uv_layers.active.name)
    x0, y0, w, h = cell
    for d in uv.data:
        d.uv = (x0 - MOUTH_GUTTER, y0 - MOUTH_GUTTER)
    ob = bpy.data.objects.new(me.name, me)
    bpy.context.scene.collection.objects.link(ob)
    ob.data.materials.append(mesh.data.materials[0])
    g = ob.vertex_groups.new(name="head")
    g.add(list(range(len(me.vertices))), 1.0, "REPLACE")
    ob["mouth_centre"] = list(centre)
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    mesh.select_set(True)
    bpy.context.view_layer.objects.active = mesh
    bpy.ops.object.join()


def paint_mouth_patch(img, cell):
    """The texels every mouth disc samples: a dark, warm cavity."""
    import numpy as _np
    W, H = img.size
    px = _np.array(img.pixels[:], dtype=_np.float32).reshape(H, W, 4)
    x0, y0 = int((cell[0] - MOUTH_GUTTER) * W), int((cell[1] - MOUTH_GUTTER) * H)
    px[y0 - 3:y0 + 4, x0 - 3:x0 + 4, :3] = (0.07, 0.025, 0.02)
    px[y0 - 3:y0 + 4, x0 - 3:x0 + 4, 3] = 1.0
    img.pixels.foreach_set(px.ravel())


OPEN_POSES = {"cheer_a": 2.6, "clap_b": 1.4}


def open_mouth(ob, pose, height):
    """Frozen pose meshes: find the mouth by its UV and open it (or keep it a slit)."""
    me = ob.data
    uv = me.uv_layers.active.data
    ids = set()
    want = 0.002 - MOUTH_GUTTER
    for p in me.polygons:
        for li in p.loop_indices:
            u, v = uv[li].uv
            if abs((u % (1 / MESH_COLS)) - want) < 2e-4 and abs((v % (1 / MESH_ROWS)) - want) < 2e-4:
                ids.add(me.loops[li].vertex_index)
    if len(ids) < 3:
        return
    pts = [me.vertices[i].co.copy() for i in ids]
    centre = sum(pts, Vector()) / len(pts)
    # The disc is wide and short; its short axis is the face's up, whatever the pose.
    wide = max((q - centre for q in pts), key=lambda e: e.length).normalized()
    normal = (pts[0] - centre).cross(pts[1] - centre)
    if normal.length < 1e-9:
        return
    up = normal.normalized().cross(wide).normalized()
    if up.z < 0:
        up = -up
    open_by = OPEN_POSES.get(pose, 0.55)
    for i in ids:
        co = me.vertices[i].co
        along = (co - centre).dot(up)
        # A jaw drops: the lower lip moves, the upper barely does.
        factor = open_by if along < 0 else min(1.0, 0.6 + 0.4 * open_by)
        me.vertices[i].co = co + up * along * (factor - 1)


def swap_materials(mesh, mode):
    for i, slot in enumerate(mesh.material_slots):
        name = slot.material.name.rsplit("_", 1)[0]
        slot.material = bpy.data.materials[f"{name}_{mode}"]


def decimate(ob, tris):
    now = R.triangles(ob)
    if now <= tris:
        return
    mod = ob.modifiers.new("dec", "DECIMATE")
    mod.ratio = tris / now
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.modifier_move_to_index(modifier="dec", index=0)
    bpy.ops.object.modifier_apply(modifier="dec")


def save(img, path, size=None):
    if size and (img.size[0] != size[0]):
        img.scale(*size)
    img.filepath_raw = str(path)
    img.file_format = "PNG"
    img.save()


# ───────────────────────────── meshes ─────────────────────────────

def build_meshes(cast):
    albedo = image("fan_albedo", MESH_ATLAS * BAKE_SCALE, MESH_ATLAS * BAKE_SCALE, "sRGB")
    mask = image("fan_mask", MESH_ATLAS * BAKE_SCALE, MESH_ATLAS * BAKE_SCALE, "Non-Color")
    ao = image("fan_ao", MESH_ATLAS * BAKE_SCALE, MESH_ATLAS * BAKE_SCALE, "Non-Color")
    ao.generated_color = (1, 1, 1, 1)
    cw, ch = 1 / MESH_COLS, 1 / MESH_ROWS
    built = []
    for i, f in enumerate(cast):
        col, row = i % MESH_COLS, i // MESH_COLS
        cell = (col * cw + 0.002, 1 - (row + 1) * ch + 0.002, cw - 0.004, ch - 0.004)
        # Two material variants per part: base albedo and tint mask. The head
        # draws its face procedurally, so both of its variants need the centre.
        mesh, rig, J = R.assemble(f, mode="base")
        hc = (J["head"] + J["head_top"]) / 2 + Vector((0, -0.010, -0.030)) * (f["height"] / 1.75)
        for slot in mesh.material_slots:
            base_name = slot.material.name.rsplit("_", 1)[0]
            is_head = base_name == f"{f['id']}_head"
            common.attr_material(f"{base_name}_tint", hc if is_head else None,
                                 f["paint"] if is_head else "none", mode="tint")
        # Colour lives on the full-resolution body's faces. Baked after
        # decimation, collars and sleeve stripes smeared across collapsed
        # triangles into white wedges; baked from a full copy they stay crisp.
        hi = mesh.copy(); hi.data = mesh.data.copy(); hi.name = f"{f['id']}_hi"
        bpy.context.scene.collection.objects.link(hi)
        decimate(mesh, LOD0_TRIS)
        unwrap_into_cell(mesh, cell)
        for mode, img in (("base", albedo), ("tint", mask)):
            swap_materials(mesh, mode)
            swap_materials(hi, mode)
            for slot in mesh.material_slots:
                add_bake_target(slot.material, img)
            bake_from(hi, mesh)
        swap_materials(mesh, "base")
        bake_ao(hi, mesh, ao)
        bpy.data.objects.remove(hi)
        paint_mouth_patch(albedo, cell)
        soften(mesh)
        add_mouth(mesh, rig, f, J, cell)
        lod1 = mesh.copy(); lod1.data = mesh.data.copy(); lod1.name = f"{f['id']}_lod1"; lod1.data.name = lod1.name
        bpy.context.scene.collection.objects.link(lod1)
        lod1.parent = rig
        decimate(lod1, LOD1_TRIS)
        soften(lod1)
        lod2 = lod1.copy(); lod2.data = lod1.data.copy(); lod2.name = f"{f['id']}_lod2"; lod2.data.name = lod2.name
        bpy.context.scene.collection.objects.link(lod2)
        lod2.parent = rig
        decimate(lod2, LOD2_TRIS)
        soften(lod2)
        built.append({"f": f, "mesh": mesh, "lod1": lod1, "lod2": lod2, "rig": rig, "cell": cell})
        log(f"{f['id']}: lod0 {R.triangles(mesh)} tris, lod1 {R.triangles(lod1)} tris, lod2 {R.triangles(lod2)} tris")
    # Warm occlusion: cavities go a little red-brown, which reads as skin on
    # skin and as fold shadow on cloth, rather than grey dirt.
    W, H = albedo.size
    a = np.array(albedo.pixels[:], dtype=np.float32).reshape(H, W, 4)
    o = np.array(ao.pixels[:], dtype=np.float32).reshape(H, W, 4)[..., :1]
    o = 1 - (1 - o) * AO_STRENGTH
    warm = np.array(AO_WARM, dtype=np.float32)
    a[..., :3] *= o + (1 - o) * warm
    albedo.pixels.foreach_set(a.ravel())
    save(albedo, OUT / "fan_albedo.png", (MESH_ATLAS, MESH_ATLAS))
    # Full size: a half-size mask upscaled on load missed edge texels, and near
    # fans came out with white wedges and sawtooth sleeves.
    save(mask, OUT / "fan_mask.png", (MESH_ATLAS, MESH_ATLAS))
    return built, albedo, mask


def finalise_materials(built, albedo):
    mat = runtime_material("crowd_fan", albedo)
    for b in built:
        for ob in (b["mesh"], b["lod1"], b["lod2"]):
            ob.data.materials.clear()
            ob.data.materials.append(mat)
            for p in ob.data.polygons:
                p.material_index = 0
            # Decimation leaves collapsed edges marked sharp, and in the stadium
            # every fan came out faceted. At crowd scale soft beats crisp.
            for name in [a.name for a in ob.data.color_attributes] + ["owner_is_body", "owner_bone", "sharp_face", "sharp_edge"]:
                if name in ob.data.attributes:
                    ob.data.attributes.remove(ob.data.attributes[name])
            for p in ob.data.polygons:
                p.use_smooth = True
    return mat


def export_fans(built):
    clips = {}
    for b in built:
        f, rig = b["f"], b["rig"]
        # glTF's ACTIONS mode exports every action that fits the skeleton, and
        # all 24 fans share bone names: clear the last fan's clips first.
        for act in list(bpy.data.actions):
            bpy.data.actions.remove(act)
        ranges = P.build_actions(rig, f["height"], f"{f['id']}|")
        clips = ranges
        only = [rig, b["mesh"], b["lod1"]]
        bpy.ops.object.select_all(action="DESELECT")
        for ob in only:
            ob.select_set(True)
        bpy.context.view_layer.objects.active = rig
        bpy.ops.export_scene.gltf(filepath=str(OUT / f"{f['id']}.glb"), export_format="GLB", use_selection=True,
                                  export_animation_mode="ACTIONS", export_skins=True, export_image_format="NONE",
                                  export_yup=True, export_apply=False)
        # USD has one timeline, so the clips are laid end to end.
        timeline = bpy.data.actions.new(f"{f['id']}|timeline")
        rig.animation_data.action = timeline
        start, usd_ranges = 0, {}
        for clip, spec in P.CLIPS.items():
            for fr, pose in spec["keys"]:
                P.apply_pose(rig, pose, f["height"], built.index(b))
                P.key_pose(rig, start + fr)
            end = start + spec["keys"][-1][0]
            usd_ranges[clip] = [start, end]
            start = end + 2
        bpy.context.scene.frame_start, bpy.context.scene.frame_end = 0, start
        bpy.ops.wm.usd_export(filepath=str(OUT / f"{f['id']}.usdz"), selected_objects_only=True,
                              export_animation=True, export_armatures=True, export_materials=False,
                              convert_orientation=True, export_global_forward_selection="Z", export_global_up_selection="Y")

        rig.animation_data.action = None
        b["usd_ranges"] = usd_ranges
        log(f"exported {f['id']}")
    return clips


def export_pose_meshes(built, lod):
    """Freeze each fan's LOD in every impostor pose into static meshes.

    The art bible animates fans by group, never per fan on the CPU: a group
    swaps which frozen pose it shows, the way the far crowd flips cells.
    """
    frozen = []
    dg = bpy.context.evaluated_depsgraph_get()
    for b in built:
        f, rig = b["f"], b["rig"]
        lod1 = {0: b["mesh"], 1: b["lod1"], 2: b["lod2"]}[lod]
        rig.animation_data.action = None
        for pose in IMP_POSES:
            P.apply_pose(rig, pose, f["height"], built.index(b))
            dg = bpy.context.evaluated_depsgraph_get()
            ev = lod1.evaluated_get(dg)
            me = bpy.data.meshes.new_from_object(ev, depsgraph=dg)
            me.name = f"{f['id']}_lod{lod}_{pose}"
            open_mouth(type("O", (), {"data": me})(), pose, f["height"])
            ob = bpy.data.objects.new(me.name, me)
            bpy.context.scene.collection.objects.link(ob)
            ob.matrix_world = lod1.matrix_world
            frozen.append(ob)
        P.apply_pose(rig, "stand", f["height"])
    bpy.ops.object.select_all(action="DESELECT")
    for ob in frozen:
        ob.select_set(True)
    bpy.context.view_layer.objects.active = frozen[0]
    bpy.ops.export_scene.gltf(filepath=str(OUT / f"lod{lod}_poses.glb"), export_format="GLB", use_selection=True,
                              export_animations=False, export_image_format="NONE", export_yup=True)
    bpy.ops.wm.usd_export(filepath=str(OUT / f"lod{lod}_poses.usdz"), selected_objects_only=True,
                          export_animation=False, export_materials=False,
                          convert_orientation=True, export_global_forward_selection="Z", export_global_up_selection="Y")
    tris = R.triangles(frozen[0])
    for ob in frozen:
        bpy.data.objects.remove(ob)
    return tris


# ───────────────────────────── impostors ─────────────────────────────

def render_impostors(built, albedo, mask):
    """Render every fan in every pose from every view, three passes, into atlases."""
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE"
    try:
        sc.eevee.taa_render_samples = 16
    except Exception:
        pass
    n = len(built)
    cw_px, ch_px = IMP_CELL
    sc.render.resolution_x, sc.render.resolution_y = n * cw_px, ch_px
    sc.render.film_transparent = True
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    cam_data = bpy.data.cameras.new("imp_cam")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = n * IMP_WORLD[0]
    cam = bpy.data.objects.new("imp_cam", cam_data)
    sc.collection.objects.link(cam)
    sc.camera = cam
    p = math.radians(IMP_ELEVATION)
    zc = (IMP_WORLD[1] / 2) / math.cos(p)
    d = Vector((0, math.cos(p), -math.sin(p)))
    cam.location = Vector((0, 0, zc)) - d * 50
    cam.rotation_euler = (math.radians(90) - p, 0, 0)
    mats = {
        "albedo": emission_material("imp_albedo", albedo),
        "mask": emission_material("imp_mask", mask),
        "normal": emission_material("imp_normal", None, normal=True),
    }
    rows = len(IMP_POSES)
    cols = len(IMP_VIEWS)
    block = (cols * cw_px, rows * ch_px)
    per_row = 8
    atlas_w = per_row * block[0]
    atlas_h = math.ceil(n / per_row) * block[1]
    atlas = {k: np.zeros((atlas_h, atlas_w, 4), dtype=np.float32) for k in mats}
    tmp = pathlib.Path(bpy.app.tempdir or "/tmp") / "crowd_imp.png"
    inverse = {pair_mate(c, n): c for c in range(n)}
    centre = lambda c: (c - (n - 1) / 2) * IMP_WORLD[0]

    def shoot(key):
        sc.render.filepath = str(tmp)
        bpy.ops.render.render(write_still=True)
        img = bpy.data.images.load(str(tmp), check_existing=False)
        px = np.array(img.pixels[:], dtype=np.float32).reshape(ch_px, n * cw_px, 4)
        bpy.data.images.remove(img)
        return px

    for pi, pose in enumerate(IMP_POSES):
        for b in built:
            P.apply_pose(b["rig"], pose, b["f"]["height"], built.index(b))
        for vi, yaw in enumerate(IMP_VIEWS):
            th = math.radians(yaw)
            for b in built:
                b["rig"].rotation_euler = (0, 0, th)
                b["lod1"].hide_render = True
                b["mesh"].hide_render = False
            layers = {}
            # Each fan is rendered twice a view: as the left member of its own
            # cell, then as the right member of its mate's cell, and the two
            # passes are laid over each other nearest-first.
            for side in (-1, 1):
                for i, b in enumerate(built):
                    c = i if side < 0 else inverse[i]
                    b["rig"].location = (centre(c) + side * PAIR_OFFSET * math.cos(th),
                                         side * PAIR_OFFSET * math.sin(th), 0)
                bpy.context.view_layer.update()
                for key, mat in mats.items():
                    sc.view_settings.view_transform = "Standard" if key == "albedo" else "Raw"
                    for b in built:
                        b["mesh"].material_slots[0].material = mat
                    layers[(side, key)] = shoot(key)
            # Smaller y is nearer the camera: that side goes on top.
            near_side = -1 if (-1 * math.sin(th)) < (1 * math.sin(th)) else 1
            if abs(math.sin(th)) < 1e-6:
                near_side = -1
            far_side = -near_side
            for key in mats:
                top, bottom = layers[(near_side, key)], layers[(far_side, key)]
                a = top[..., 3:4]
                comp = np.empty_like(top)
                comp[..., :3] = top[..., :3] * a + bottom[..., :3] * (1 - a)
                comp[..., 3:4] = a + bottom[..., 3:4] * (1 - a)
                for i in range(n):
                    bx, by = (i % per_row) * block[0], (i // per_row) * block[1]
                    cell = comp[:, i * cw_px:(i + 1) * cw_px]
                    y0 = atlas_h - (by + (pi + 1) * ch_px)
                    atlas[key][y0:y0 + ch_px, bx + vi * cw_px:bx + (vi + 1) * cw_px] = cell
            log(f"impostor {pose} yaw {yaw}")
    out = {}
    for key, arr in atlas.items():
        img = bpy.data.images.new(f"impostor_{key}", atlas_w, atlas_h, alpha=True)
        img.colorspace_settings.name = "sRGB" if key == "albedo" else "Non-Color"
        img.pixels.foreach_set(arr.ravel())
        path = OUT / f"impostor_{key}.png"
        if key == "albedo":
            save(img, path)
        else:
            save(img, path, (atlas_w // 2, atlas_h // 2))
        out[key] = {"file": path.name, "size": list(img.size), "colorspace": "srgb" if key == "albedo" else "linear"}
    for b in built:
        b["mesh"].material_slots[0].material = bpy.data.materials["crowd_fan"]
        b["rig"].location = (0, 0, 0)
        b["rig"].rotation_euler = (0, 0, 0)
    return out, {"per_row": per_row, "block_px": list(block), "atlas_px": [atlas_w, atlas_h]}


def variation_map(n_fans, size=256, seed=specs.SEED):
    """R phase, G fan index, B tint jitter, A pose bias; no two 4-neighbours share a fan."""
    rng = random.Random(seed)
    grid = np.zeros((size, size, 4), dtype=np.float32)
    fans = np.zeros((size, size), dtype=np.int32)
    for y in range(size):
        for x in range(size):
            banned = set()
            if x: banned.add(fans[y, x - 1])
            if y: banned.add(fans[y - 1, x])
            if x and y: banned.add(fans[y - 1, x - 1])
            choice = rng.randrange(n_fans)
            while choice in banned and len(banned) < n_fans:
                choice = rng.randrange(n_fans)
            fans[y, x] = choice
            grid[y, x] = (rng.random(), (choice + 0.5) / n_fans, rng.random(), rng.random())
    img = bpy.data.images.new("variation", size, size, alpha=True)
    img.colorspace_settings.name = "Non-Color"
    img.pixels.foreach_set(grid.ravel())
    save(img, OUT / "variation.png")


# ───────────────────────────── manifest ─────────────────────────────

def write_manifest(built, clips, lod1_tris, impostor, layout, cast):
    joints = [{"name": n, "parent": p} for n, p, *_ in F.BONES]
    fans = []
    for i, b in enumerate(built):
        f = b["f"]
        x0, y0, w, h = b["cell"]
        fans.append({
            "id": f["id"], "build": f["build"], "height": f["height"], "top": f["top"], "club": f["club"],
            "hat": f["hat"], "hair": f["hair"], "accessory": f["accessory"], "paint": f["paint"],
            "model": f"{f['id']}.usdz", "gltf": f"{f['id']}.glb",
            "lod0": {"mesh": f["id"], "triangles": R.triangles(b["mesh"])},
            "lod1": {"mesh": f"{f['id']}_lod1", "triangles": R.triangles(b["lod1"])},
            "lod2": {"mesh": f"{f['id']}_lod2", "triangles": R.triangles(b["lod2"])},
            "uvCell": [round(x0, 5), round(y0, 5), round(w, 5), round(h, 5)],
            "impostorBlock": [(i % layout["per_row"]) * layout["block_px"][0], (i // layout["per_row"]) * layout["block_px"][1]],
            "impostorMate": built[pair_mate(i, len(built))]["f"]["id"],
            "usdClips": b.get("usd_ranges", {}),
        })
    k = 1.0
    manifest = {
        "version": 1,
        "generator": "tools/blender/crowd/build.py",
        "units": "metres",
        "axes": {"gltf": "+Y up, fans face +Z", "usd": "+Y up, fans face +Z (converted on export, same frame as glTF)"},
        "origin": "floor under the pelvis in the standing pose",
        "seat": {"about": "In the sitting clips the pelvis moves back and down onto the seat pan; feet stay near the origin.",
                 "pelvisAt175m": list(P.SIT_HIPS)},
        "skeleton": joints,
        "fans": fans,
        "animations": [{"name": c, "frames": [spec["keys"][0][0], spec["keys"][-1][0]], "fps": P.FPS, "loop": spec["loop"]}
                       for c, spec in P.CLIPS.items()],
        "tint": {
            "formula": "albedo.rgb * mix(1, chip, mask) per channel: rgb = albedo * lerp(1, primary, m.r) * lerp(1, secondary, m.g); paint = lerp(rgb, primary*0.86, m.b)",
            "R": "club primary chip", "G": "club secondary chip", "B": "face paint (primary)",
            "note": "Tinted regions carry a 0.86 luminance in albedo so the chip reads at its own value.",
        },
        "textures": {
            "fanAlbedo": {"file": "fan_albedo.png", "size": [MESH_ATLAS, MESH_ATLAS], "colorspace": "srgb"},
            "fanMask": {"file": "fan_mask.png", "size": [MESH_ATLAS, MESH_ATLAS], "colorspace": "linear"},
            "impostorAlbedo": impostor["albedo"], "impostorMask": impostor["mask"], "impostorNormal": impostor["normal"],
            "variation": {"file": "variation.png", "size": [256, 256], "colorspace": "linear",
                          "channels": {"r": "animation phase 0..1", "g": "fan index (i+0.5)/24", "b": "tint jitter", "a": "pose bias"}},
        },
        "impostor": {
            "cellPx": list(IMP_CELL), "worldSize": list(IMP_WORLD), "pivot": "bottom centre",
            "pair": {"about": "Each cell holds two neighbours: the block's fan left of centre, its mate right, each offsetMetres from the centre along the seat row (rotated with the view). Tint the left half of a cell as one fan and the right half as the other.",
                     "offsetMetres": PAIR_OFFSET, "mate": f"({PAIR_STEP} * index + 11) mod 24"},
            "poses": IMP_POSES, "viewsYawDeg": IMP_VIEWS, "mirror": {"225": 135, "270": 90, "315": 45},
            "elevationDeg": IMP_ELEVATION,
            "layout": {**layout, "cell": "column = view index, row = pose index, both from the block's top-left"},
            "normal": "view space, +X right, +Y up, +Z toward the viewer, encoded n*0.5+0.5",
        },
        "poseMeshes": {
        "about": "Static meshes of every fan frozen in each impostor pose, for animating near and mid rings by group.",
        "lod0": {"model": "lod0_poses.usdz", "gltf": "lod0_poses.glb", "meshName": "<fanId>_lod0_<pose>"},
        "lod1": {"model": "lod1_poses.usdz", "gltf": "lod1_poses.glb", "meshName": "<fanId>_lod1_<pose>"},
        "lod2": {"model": "lod2_poses.usdz", "gltf": "lod2_poses.glb", "meshName": "<fanId>_lod2_<pose>"},
        "poses": IMP_POSES},
        "lod": {"lod0Triangles": LOD0_TRIS, "lod1Triangles": LOD1_TRIS,
                "suggestedRings": {"lod0MaxMetres": 7, "lod1MaxMetres": 16, "impostorBeyondMetres": 16}},
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=1))
    return manifest


def main():
    stage = "all"
    a = common.args()
    if "--stage" in a:
        stage = a[a.index("--stage") + 1]
    OUT.mkdir(parents=True, exist_ok=True)
    common.reset()
    cast = specs.cast()
    only = None
    if "--only" in a:
        only = int(a[a.index("--only") + 1])
        cast = cast[:only]
    built, albedo, mask = build_meshes(cast)
    finalise_materials(built, albedo)
    clips = export_fans(built)
    lod1_tris = export_pose_meshes(built, 1)
    lod0_tris = export_pose_meshes(built, 0)
    export_pose_meshes(built, 2)
    impostor, layout = ({}, {"per_row": 8, "block_px": [0, 0], "atlas_px": [0, 0]})
    if stage in ("all", "impostors"):
        impostor, layout = render_impostors(built, albedo, mask)
    variation_map(len(cast))
    write_manifest(built, clips, lod1_tris, impostor, layout, cast)
    log("done")


main()
