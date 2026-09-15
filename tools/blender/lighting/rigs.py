"""Model the LED floodlight banks and the beam meshes, and bake the bank's face.

    blender --background --factory-startup --python tools/blender/lighting/rigs.py

Writes assets/actors/lighting/:
  rigs/light_bank_lod0.glb   every fixture modelled: housing, lens, fins, yoke,
                              pipes, truss, catwalk with rails, support legs
  rigs/light_bank_lod1.glb   a housing box with the baked face - the far side
  rigs/light_bank_lod2.glb   the face card alone, for the tabletop
  rigs/beam_cone.glb         unit cone, U round / V along, V=0 at the lamp
  rigs/beam_quads.glb        three crossed quads, the cheap beam
  textures/emitter_lens.png  one fixture's lens: 4x4 LEDs with reflector falloff
  textures/lamp_bank_face.png  the whole bank seen head-on, baked from LOD0

A bank's origin is its centre - the point look.light.rim places - with its
face toward +Z in glTF (the field, once a renderer turns it to its mount's
aim) and its legs reaching down to the tier below. Metres, like every glTF.
"""
from __future__ import annotations

import math
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import common as C  # noqa: E402
import bpy  # noqa: E402
import bmesh  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

YD = C.YD
BANK_W = 11.0 * YD            # look.light.rim.lampYards.stadium
BANK_H = 4.0 * YD
ROWS, COLS = 4, 14
LEG = 9.0 * YD                # look.light.rim.heightAbove.stadium: down to the tier top
OUT = C.OUT_LIGHT


# ───────────────────────────── primitives into one bmesh ─────────────────────────────

class Builder:
    """Accumulates boxes and tubes into per-material bmeshes, so a bank is one
    object with three materials: three draw calls, however many fixtures."""

    def __init__(self):
        self.parts: dict[str, bmesh.types.BMesh] = {}

    def bm(self, mat):
        if mat not in self.parts:
            b = bmesh.new()
            b.loops.layers.uv.new("UVMap")
            self.parts[mat] = b
        return self.parts[mat]

    def box(self, mat, size, matrix, uv_face=None):
        b = self.bm(mat)
        geom = bmesh.ops.create_cube(b, size=1.0)
        verts = geom["verts"]
        bmesh.ops.scale(b, vec=Vector(size), verts=verts)
        bmesh.ops.transform(b, matrix=matrix, verts=verts)
        uv = b.loops.layers.uv.active
        faces = {f for v in verts for f in v.link_faces}
        for f in faces:
            n = f.normal
            for loop in f.loops:
                co = matrix.inverted() @ loop.vert.co
                if abs(n.dot(matrix.to_3x3() @ Vector((0, 0, 1)))) > 0.9:
                    loop[uv].uv = (co.x / size[0] + 0.5, co.y / size[1] + 0.5)
                elif abs(n.dot(matrix.to_3x3() @ Vector((1, 0, 0)))) > 0.9:
                    loop[uv].uv = (co.y / size[1] + 0.5, co.z / size[2] + 0.5)
                else:
                    loop[uv].uv = (co.x / size[0] + 0.5, co.z / size[2] + 0.5)
        return faces

    def quad(self, mat, w, h, matrix, flip=False):
        b = self.bm(mat)
        uv = b.loops.layers.uv.active
        pts = [(-w / 2, 0, -h / 2), (w / 2, 0, -h / 2), (w / 2, 0, h / 2), (-w / 2, 0, h / 2)]
        vs = [b.verts.new(matrix @ Vector(p)) for p in pts]
        order = [0, 1, 2, 3] if not flip else [3, 2, 1, 0]
        f = b.faces.new([vs[i] for i in order])
        uvs = [(0, 0), (1, 0), (1, 1), (0, 1)]
        for loop, i in zip(f.loops, order):
            loop[uv].uv = uvs[i]
        return f

    def tube(self, mat, a, b_, radius, sides=8):
        a, b_ = Vector(a), Vector(b_)
        d = b_ - a
        length = d.length
        bm = self.bm(mat)
        geom = bmesh.ops.create_cone(bm, cap_ends=False, segments=sides, radius1=radius, radius2=radius, depth=length)
        rot = d.to_track_quat("Z", "Y").to_matrix().to_4x4()
        m = Matrix.Translation((a + b_) / 2) @ rot
        bmesh.ops.transform(bm, matrix=m, verts=geom["verts"])

    def objects(self, name, materials):
        objs = []
        for mat, b in self.parts.items():
            me = bpy.data.meshes.new(f"{name}_{mat}")
            b.normal_update()
            b.to_mesh(me)
            b.free()
            me.materials.append(materials[mat])
            obj = bpy.data.objects.new(f"{name}_{mat}", me)
            C.link(obj)
            objs.append(obj)
        self.parts = {}
        return objs


# ───────────────────────────── materials ─────────────────────────────

def materials():
    housing = C.material("bank_housing", color=(0.030, 0.032, 0.036), rough=0.42, metal=0.85)
    steel = C.material("bank_steel", color=(0.42, 0.43, 0.44), rough=0.55, metal=0.9)
    lens = bpy.data.materials.new("bank_lens")
    lens.use_nodes = True
    nt = lens.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.02, 0.02, 0.02, 1)
    bsdf.inputs["Roughness"].default_value = 0.08
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(str(OUT / "textures" / "emitter_lens.png"))
    tex.image.colorspace_settings.name = "sRGB"
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Emission Color"])
    bsdf.inputs["Emission Strength"].default_value = 40.0
    face = bpy.data.materials.new("bank_face")
    face.use_nodes = True
    nt = face.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.02, 0.02, 0.02, 1)
    tex = nt.nodes.new("ShaderNodeTexImage")
    face_png = OUT / "textures" / "lamp_bank_face.png"
    if face_png.exists():
        tex.image = bpy.data.images.load(str(face_png))
        tex.image.colorspace_settings.name = "sRGB"
        nt.links.new(tex.outputs["Color"], bsdf.inputs["Emission Color"])
        nt.links.new(tex.outputs["Alpha"], bsdf.inputs["Alpha"])
    bsdf.inputs["Emission Strength"].default_value = 40.0
    return {"housing": housing, "steel": steel, "lens": lens, "face": face}


# ───────────────────────────── the lens texture ─────────────────────────────

def emitter_lens():
    """Sixteen LEDs behind a diffusing lens. Lit, a sports fixture reads as a
    blazing panel with the LED pattern only just visible in it - so the lens
    carries a high floor of scattered light, hot cores and faceted cups on top,
    and only a thin dark frame at its edge."""
    s = 256
    y, x = np.mgrid[0:s, 0:s]
    u, v = (x + 0.5) / s, (y + 0.5) / s
    n = 4
    cu, cv = (u * n) % 1 - 0.5, (v * n) % 1 - 0.5
    r = np.hypot(cu, cv) * 2
    core = np.exp(-(r / 0.34) ** 2)
    cup = np.clip(1 - r, 0, 1) ** 1.2 * 0.35
    facets = 0.8 + 0.2 * np.cos(np.arctan2(cv, cu) * 12) ** 2
    diffuse = 0.62 + 0.08 * np.cos(u * np.pi * 2) * np.cos(v * np.pi * 2)
    val = np.clip(diffuse + 0.5 * core + cup * facets, 0, 1.0)
    edge = np.minimum(np.minimum(u, 1 - u), np.minimum(v, 1 - v))
    val *= np.clip(edge / 0.03, 0, 1)
    rgba = np.ones((s, s, 4))
    rgba[..., 0] = val
    rgba[..., 1] = val * 0.985
    rgba[..., 2] = val * 0.96
    C.save_png(OUT / "textures" / "emitter_lens.png", rgba, seed=21)


# ───────────────────────────── the bank ─────────────────────────────

def bank(builder: Builder, detail=True):
    """Blender coords: bank centre at the origin, face toward -Y, up +Z."""
    col_pitch = BANK_W / COLS
    row_pitch = BANK_H / ROWS
    fw, fh, fd = col_pitch * 0.88, row_pitch * 0.62, 0.20
    for r in range(ROWS):
        z = BANK_H / 2 - row_pitch * (r + 0.5)
        tilt = math.radians(18 + 5 * r)            # lower rows reach further down the field
        # the pipe this row hangs from
        builder.tube("steel", (-BANK_W / 2 - 0.2, 0.22, z + fh * 0.62), (BANK_W / 2 + 0.2, 0.22, z + fh * 0.62), 0.045)
        for c in range(COLS):
            xcol = -BANK_W / 2 + col_pitch * (c + 0.5)
            yaw = math.radians((c - (COLS - 1) / 2) * -1.2)   # a slight fan across the bank
            m = Matrix.Translation((xcol, 0.0, z)) @ Matrix.Rotation(yaw, 4, "Z") @ Matrix.Rotation(-tilt, 4, "X")
            builder.box("housing", (fw, fd, fh), m)
            lens_m = m @ Matrix.Translation((0, -fd / 2 - 0.004, 0))
            builder.quad("lens", fw * 0.9, fh * 0.86, lens_m)
            if detail:
                for k in range(6):                                   # heat-sink fins
                    fx = -fw / 2 + fw * (k + 0.5) / 6
                    builder.box("housing", (0.012, 0.10, fh * 0.9), m @ Matrix.Translation((fx, fd / 2 + 0.05, 0)))
                for side in (-1, 1):                                 # yoke plates
                    builder.box("steel", (0.02, 0.16, fh * 0.9), m @ Matrix.Translation((side * (fw / 2 + 0.02), 0.04, 0)))
                builder.box("steel", (0.06, 0.06, 0.26), Matrix.Translation((xcol, 0.2, z + fh * 0.42)))
    for side in (-1, 1):                                             # frame posts
        builder.tube("steel", (side * (BANK_W / 2 + 0.2), 0.22, -BANK_H / 2 - 0.3),
                     (side * (BANK_W / 2 + 0.2), 0.22, BANK_H / 2 + 0.2), 0.07)
    if not detail:
        return
    # A triangular truss under the bank, then the catwalk the crew walks.
    tz = -BANK_H / 2 - 0.55
    chords = [(0.0, 0.1, tz + 0.35), (0.0, -0.25, tz - 0.2), (0.0, 0.45, tz - 0.2)]
    for cy, cyy, cz in chords:
        builder.tube("steel", (-BANK_W / 2 - 0.3, cyy, cz), (BANK_W / 2 + 0.3, cyy, cz), 0.04, sides=6)
    bays = 12
    for i in range(bays + 1):
        x0 = -BANK_W / 2 - 0.3 + (BANK_W + 0.6) * i / bays
        x1 = -BANK_W / 2 - 0.3 + (BANK_W + 0.6) * (i + 0.5) / bays
        a, b_, c_ = chords
        builder.tube("steel", (x0, a[1], a[2]), (x1, b_[1], b_[2]), 0.018, sides=4)
        builder.tube("steel", (x0, a[1], a[2]), (x1, c_[1], c_[2]), 0.018, sides=4)
        builder.tube("steel", (x0, b_[1], b_[2]), (x0, c_[1], c_[2]), 0.018, sides=4)
    deck_z = tz - 0.25
    slats = 36
    for i in range(slats):
        x = -BANK_W / 2 - 0.3 + (BANK_W + 0.6) * (i + 0.5) / slats
        builder.box("steel", ((BANK_W + 0.6) / slats * 0.8, 0.95, 0.03), Matrix.Translation((x, -0.6, deck_z)))
    for yy in (-1.05, -0.15):
        builder.box("steel", (BANK_W + 0.6, 0.02, 0.12), Matrix.Translation((0, yy, deck_z + 0.06)))
    rail_y = -1.05
    for hgt in (0.55, 1.05):
        builder.tube("steel", (-BANK_W / 2 - 0.3, rail_y, deck_z + hgt), (BANK_W / 2 + 0.3, rail_y, deck_z + hgt), 0.022, sides=6)
    posts = 8
    for i in range(posts + 1):
        x = -BANK_W / 2 - 0.3 + (BANK_W + 0.6) * i / posts
        builder.tube("steel", (x, rail_y, deck_z), (x, rail_y, deck_z + 1.05), 0.022, sides=6)
    for i in range(5):                                               # driver cabinets
        x = -BANK_W / 2 + BANK_W * (i + 0.5) / 5
        builder.box("housing", (0.5, 0.28, 0.42), Matrix.Translation((x, -0.35, deck_z + 0.24)))
    # Legs down to the tier top, with a cross brace.
    for side in (-1, 1):
        x = side * BANK_W * 0.32
        builder.tube("steel", (x, 0.2, deck_z), (x, 0.2, -LEG), 0.14, sides=10)
        builder.tube("steel", (x, 0.2, deck_z - 1.0), (-x * 0.35, 0.2, -LEG + 1.5), 0.05, sides=6)


def export(path, objs):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.gltf(filepath=str(path), export_format="GLB", use_selection=True,
                              export_apply=True, export_yup=True, export_texcoords=True,
                              export_normals=True, export_materials="EXPORT", export_image_format="AUTO")
    tris = sum(sum(len(p.vertices) - 2 for p in o.data.polygons) for o in objs)
    for o in objs:
        bpy.data.objects.remove(o, do_unlink=True)
    return tris


def cone():
    """A unit cone along -Y (glTF +Z): apex ring radius 0.04 at the lamp, radius 1 at length 1."""
    b = bmesh.new()
    uv = b.loops.layers.uv.new("UVMap")
    seg, rings = 24, 8
    verts = []
    for r in range(rings + 1):
        t = r / rings
        rad = 0.04 + 0.96 * t
        row = []
        for s in range(seg + 1):
            a = 2 * math.pi * s / seg
            row.append(b.verts.new((rad * math.cos(a), -t, rad * math.sin(a))))
        verts.append(row)
    for r in range(rings):
        for s in range(seg):
            f = b.faces.new((verts[r][s], verts[r][s + 1], verts[r + 1][s + 1], verts[r + 1][s]))
            coords = [(s / seg, r / rings), ((s + 1) / seg, r / rings), ((s + 1) / seg, (r + 1) / rings), (s / seg, (r + 1) / rings)]
            for loop, c in zip(f.loops, coords):
                loop[uv].uv = (c[0], 1 - c[1])
    me = bpy.data.meshes.new("beam_cone")
    b.to_mesh(me)
    b.free()
    mat = C.material("beam", color=(0, 0, 0), emit=(1, 1, 1), emit_strength=1.0)
    me.materials.append(mat)
    obj = C.link(bpy.data.objects.new("beam_cone", me))
    return [obj]


def quads():
    b = Builder()
    for k in range(3):
        m = Matrix.Rotation(math.radians(60 * k), 4, "Y") @ Matrix.Translation((0, -0.5, 0)) @ Matrix.Rotation(math.radians(90), 4, "X")
        b.quad("beam", 1.2, 1.0, m)
    mat = C.material("beam", color=(0, 0, 0), emit=(1, 1, 1), emit_strength=1.0)
    return b.objects("beam_quads", {"beam": mat})


def bake_face(mats):
    """Render LOD0 head-on, orthographic, lenses lit and housings faintly
    visible, into the texture the far-side LOD shows."""
    scene = bpy.context.scene
    b = Builder()
    bank(b, detail=False)
    objs = b.objects("bank_bake", mats)
    cam_data = bpy.data.cameras.new("face_cam")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = BANK_W + 0.5
    cam = C.link(bpy.data.objects.new("face_cam", cam_data))
    cam.location = (0, -20, 0)
    cam.rotation_euler = (math.radians(90), 0, 0)
    scene.camera = cam
    scene.render.resolution_x = 1024
    scene.render.resolution_y = int(1024 * (BANK_H + 0.9) / (BANK_W + 0.5))
    scene.render.film_transparent = True
    scene.cycles.samples = 64
    world = bpy.data.worlds.new("face_world")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.02, 0.022, 0.03, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 1.0
    scene.world = world
    # Bake hot: the lens should clip to white across most of its area, the
    # LED structure surviving only as a faint pattern, the frame dark.
    mats["lens"].node_tree.nodes["Principled BSDF"].inputs["Emission Strength"].default_value = 1.35
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.color_depth = "8"
    path = OUT / "textures" / "lamp_bank_face.png"
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    mats["lens"].node_tree.nodes["Principled BSDF"].inputs["Emission Strength"].default_value = 40.0
    for o in objs:
        bpy.data.objects.remove(o, do_unlink=True)
    bpy.data.objects.remove(cam, do_unlink=True)
    return scene.render.resolution_x, scene.render.resolution_y


def main():
    C.reset()
    emitter_lens()
    mats = materials()
    size = bake_face(mats)
    mats = materials()      # reload so the face material picks up the fresh bake

    b = Builder()
    bank(b, detail=True)
    t0 = export(OUT / "rigs" / "light_bank_lod0.glb", b.objects("light_bank_lod0", mats))

    b = Builder()
    depth = 0.35
    b.box("housing", (BANK_W, depth, BANK_H), Matrix.Translation((0, depth / 2 + 0.01, 0)))
    b.quad("face", BANK_W + 0.5, BANK_H + 0.9, Matrix.Translation((0, -0.01, -0.2)))
    for side in (-1, 1):
        b.tube("steel", (side * BANK_W * 0.32, 0.2, -BANK_H / 2), (side * BANK_W * 0.32, 0.2, -LEG), 0.14, sides=6)
    t1 = export(OUT / "rigs" / "light_bank_lod1.glb", b.objects("light_bank_lod1", mats))

    b = Builder()
    b.quad("face", BANK_W + 0.5, BANK_H + 0.9, Matrix.Translation((0, 0, -0.2)))
    t2 = export(OUT / "rigs" / "light_bank_lod2.glb", b.objects("light_bank_lod2", mats))

    t3 = export(OUT / "rigs" / "beam_cone.glb", cone())
    t4 = export(OUT / "rigs" / "beam_quads.glb", quads())
    C.write_json(C.SCRATCH / "rig_stats.json", {"lod0": t0, "lod1": t1, "lod2": t2, "cone": t3, "quads": t4,
                                               "faceTexture": list(size)})
    print(f"[lighting] rigs: lod0 {t0} tris, lod1 {t1}, lod2 {t2}, cone {t3}, quads {t4}; face {size}")


main()
