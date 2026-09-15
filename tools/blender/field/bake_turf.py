"""Bake tileable turf material sets from real blade geometry.

A 0.40 m square of turf is grown blade by blade - base position, height, width,
lean, bend, twist and colour all drawn from a seeded generator - and wrapped at
the edges so the square tiles without a seam. An orthographic camera looks
straight down and Cycles renders each map as a pass:

  albedo    blade colour, unlit                         sRGB   RGB
  normal    tangent-space normal, OpenGL (+Y up)        linear RGB
  orm       R ambient occlusion, G roughness, B height  linear RGB
  shells    8 coverage slices by height, for fin/shell  linear, one PNG per slice
            grass up close (shell_0 is the tallest cut)

Mowed stadium grass is combed: blades lean the way the mower travelled, and a
stripe is nothing but two lean directions under a floodlight. So the natural
set is baked twice, leaning +X ("with") and -X ("against"), from the same blade
layout; a renderer blends the pair by the stripe mask and gets a stripe that
changes with the view, as a real one does. A third natural set, "worn", is
thinned, flattened and browned for high-traffic ground.

    blender -b --factory-startup --python tools/blender/field/bake_turf.py -- natural
    blender -b --factory-startup --python tools/blender/field/bake_turf.py -- synthetic
"""
from __future__ import annotations

import math
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import common  # noqa: E402

import bpy  # noqa: E402
import numpy as np  # noqa: E402

PATCH = 0.40            # metres per tile
BAKE_RES = 2048
OUT_RES = 1024
SHELLS = 8
SHELL_RES = 512
WORN_RES = 512
MAX_H = 0.045           # height map full scale, metres


# ───────────────────────────── blades ─────────────────────────────

def blade_strip(base, height, width, lean_dir, bend, twist, segments=4):
    """Vertices for one tapered, bent blade: pairs up the length, a tip point."""
    verts = []
    ux, uy = math.cos(lean_dir), math.sin(lean_dir)           # lean direction on ground
    fx, fy = math.cos(lean_dir + math.pi / 2 + twist), math.sin(lean_dir + math.pi / 2 + twist)
    x, y, z = base
    seg = height / segments
    ang = 0.0
    for i in range(segments + 1):
        t = i / segments
        w = width * (1 - t) ** 0.8 * 0.5
        if i == segments:
            verts.append((x, y, z, t))
            break
        verts.append((x - fx * w, y - fy * w, z, t))
        verts.append((x + fx * w, y + fy * w, z, t))
        ang = bend * (t + 1 / segments) ** 1.6              # bends more toward the tip
        x += ux * seg * math.sin(ang)
        y += uy * seg * math.sin(ang)
        z += seg * math.cos(ang)
    faces = []
    for i in range(segments - 1):
        a, b, c, d = 2 * i, 2 * i + 1, 2 * i + 3, 2 * i + 2
        faces.append((a, b, c, d))
    faces.append((2 * (segments - 1), 2 * (segments - 1) + 1, 2 * segments))
    return verts, faces


def grow(variant: str, lean: float, seed: int):
    """Return verts, faces and per-vertex colour, roughness for one tile."""
    r = common.rng(seed)
    V, F, C, R = [], [], [], []

    def add(base, h, w, d, bend, tw, colour, rough, segments=4):
        vs, fs = blade_strip(base, h, w, d, bend, tw, segments)
        extent = h * 1.05
        offsets = [(0.0, 0.0)]
        bx, by = base[0], base[1]
        for ox in (-PATCH, 0.0, PATCH):
            for oy in (-PATCH, 0.0, PATCH):
                if (ox, oy) == (0.0, 0.0):
                    continue
                nx, ny = bx + ox, by + oy
                if -extent <= nx <= PATCH + extent and -extent <= ny <= PATCH + extent:
                    offsets.append((ox, oy))
        for ox, oy in offsets:
            start = len(V)
            for (x, y, z, t) in vs:
                V.append((x + ox, y + oy, z))
                tip = t ** 1.5
                C.append(tuple(colour[k] * (0.55 + 0.45 * t) + tip * 0.06 * (k == 0) for k in range(3)))
                R.append(rough)
            F.extend(tuple(start + i for i in f) for f in fs)

    if variant in ("natural", "worn"):
        density = 260_000 if variant == "natural" else 95_000      # blades per m²; mown stadium turf is dense
        n = int(density * PATCH * PATCH)
        bases = r.random((n, 2)) * PATCH
        for i in range(n):
            worn = variant == "worn"
            h = max(0.010, r.normal(0.022 if not worn else 0.015, 0.004))
            w = r.uniform(0.0015, 0.0030)
            d = lean + r.normal(0, 0.45 if not worn else 1.3)
            bend = r.uniform(0.25, 0.80) if not worn else r.uniform(0.95, 1.5)
            tw = r.normal(0, 0.35)
            hue = r.normal(0.300, 0.010)
            sat = r.uniform(0.62, 0.86)
            val = r.uniform(0.20, 0.40)
            if r.random() < (0.03 if not worn else 0.25):          # dry and dead blades
                hue, sat, val = r.uniform(0.10, 0.16), r.uniform(0.35, 0.55), r.uniform(0.30, 0.48)
            colour = _hsv(hue, sat, val)
            add((bases[i, 0], bases[i, 1], 0.002), h, w, d, bend, tw, colour, r.uniform(0.48, 0.72))
    else:                                                             # synthetic turf
        gauge = 0.0095                                                # 3/8 in between tuft rows
        pitch = 0.0105
        rows = int(PATCH / gauge)
        cols = int(PATCH / pitch)
        for i in range(rows):
            for j in range(cols):
                cx = (j + 0.5) * pitch + r.normal(0, 0.0008)
                cy = (i + 0.5) * gauge + r.normal(0, 0.0005)
                tone = r.uniform(0.9, 1.1)
                tuft_dir = lean + r.normal(0, 0.5)                    # grooming brushes the pile one way
                for k in range(18):                                   # filaments per tuft
                    h = r.uniform(0.020, 0.032)                       # standing above the infill
                    d = tuft_dir + r.normal(0, 0.55)
                    colour = _hsv(r.normal(0.325, 0.006), r.uniform(0.62, 0.74), 0.36 * tone * r.uniform(0.9, 1.1))
                    add((cx, cy, 0.0), h, r.uniform(0.0018, 0.0028), d,
                        r.uniform(0.9, 1.5), r.normal(0, 0.25), colour, r.uniform(0.26, 0.38), segments=3)
    return np.array(V), F, np.array(C), np.array(R)


def _hsv(h, s, v):
    import colorsys
    return colorsys.hsv_to_rgb(h % 1.0, min(1, max(0, s)), min(1, max(0, v)))


def ground(variant: str, seed: int):
    """Soil and thatch under natural grass; rubber and sand infill under synthetic."""
    r = common.rng(seed + 1)
    mesh = bpy.data.meshes.new("ground")
    mesh.from_pydata([(-0.05, -0.05, 0), (PATCH + 0.05, -0.05, 0), (PATCH + 0.05, PATCH + 0.05, 0), (-0.05, PATCH + 0.05, 0)],
                     [], [(0, 1, 2, 3)])
    obj = bpy.data.objects.new("ground", mesh)
    bpy.context.scene.collection.objects.link(obj)
    specks = []
    if variant == "synthetic":
        n = int(12_000 * PATCH * PATCH * 10)                         # crumb rubber granules
        for _ in range(n):
            x, y = r.random() * PATCH, r.random() * PATCH
            s = r.uniform(0.0005, 0.0012)
            rubber = r.random() < 0.9
            col = (0.022, 0.022, 0.024) if rubber else (0.30, 0.26, 0.19)
            specks.append((x, y, s, col, 0.85 if rubber else 0.6))
    else:
        n = int(4_000 * PATCH * PATCH * 10)                          # thatch and soil crumbs
        for _ in range(n):
            x, y = r.random() * PATCH, r.random() * PATCH
            s = r.uniform(0.0004, 0.0012)
            col = _hsv(r.uniform(0.07, 0.11), r.uniform(0.3, 0.55), r.uniform(0.06, 0.16))
            specks.append((x, y, s, col, 0.9))
    V, F, C, R = [], [], [], []
    for (x, y, s, col, rough) in specks:
        for ox in (0.0, -PATCH, PATCH):
            for oy in (0.0, -PATCH, PATCH):
                px, py = x + ox, y + oy
                if not (-s <= px <= PATCH + s and -s <= py <= PATCH + s):
                    continue
                b = len(V)
                h = s * 0.3
                V += [(px - s, py - s, 0.0005), (px + s, py - s, 0.0005), (px + s, py + s, 0.0005), (px - s, py + s, 0.0005),
                      (px, py, 0.0005 + h)]
                F += [(b, b + 1, b + 4), (b + 1, b + 2, b + 4), (b + 2, b + 3, b + 4), (b + 3, b, b + 4)]
                C += [col] * 5
                R += [rough] * 5
    soil = {"natural": (0.030, 0.024, 0.014), "worn": (0.11, 0.078, 0.046)}.get(variant, (0.03, 0.03, 0.03))
    return mesh, obj, soil, (np.array(V), F, np.array(C), np.array(R))


def build_object(name, V, F, C, R):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([tuple(v) for v in V], [], F)
    col = mesh.color_attributes.new("col", "FLOAT_COLOR", "POINT")
    rgba = np.concatenate([C, np.ones((len(C), 1))], axis=1).astype(np.float32).ravel()
    col.data.foreach_set("color", rgba)
    rough = mesh.attributes.new("rough", "FLOAT", "POINT")
    rough.data.foreach_set("value", R.astype(np.float32))
    mesh.shade_smooth() if hasattr(mesh, "shade_smooth") else None
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


# ───────────────────────────── passes ─────────────────────────────

def pass_material(kind: str, soil, shell_min=None):
    """An emission shader that writes one map. Everything renders unlit."""
    m = bpy.data.materials.new(f"pass_{kind}")
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    emit = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(emit.outputs[0], out.inputs["Surface"])
    attr = nt.nodes.new("ShaderNodeAttribute")
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    if kind == "albedo":
        attr.attribute_name = "col"
        nt.links.new(attr.outputs["Color"], emit.inputs["Color"])
    elif kind == "normal":
        # world normal (z up) -> 0..1; the camera looks down -Z with +Y up, so
        # world X/Y are tangent X/Y: an OpenGL normal map.
        vm = nt.nodes.new("ShaderNodeVectorMath"); vm.operation = "MULTIPLY"
        vm.inputs[1].default_value = (0.5, 0.5, 0.5)
        va = nt.nodes.new("ShaderNodeVectorMath"); va.operation = "ADD"
        va.inputs[1].default_value = (0.5, 0.5, 0.5)
        nt.links.new(geo.outputs["Normal"], vm.inputs[0])
        nt.links.new(vm.outputs[0], va.inputs[0])
        nt.links.new(va.outputs[0], emit.inputs["Color"])
    elif kind == "rough":
        attr.attribute_name = "rough"
        nt.links.new(attr.outputs["Fac"], emit.inputs["Color"])
    elif kind == "height":
        sep = nt.nodes.new("ShaderNodeSeparateXYZ")
        mul = nt.nodes.new("ShaderNodeMath"); mul.operation = "DIVIDE"
        mul.inputs[1].default_value = MAX_H
        nt.links.new(geo.outputs["Position"], sep.inputs[0])
        nt.links.new(sep.outputs["Z"], mul.inputs[0])
        nt.links.new(mul.outputs[0], emit.inputs["Color"])
    elif kind == "ao":
        ao = nt.nodes.new("ShaderNodeAmbientOcclusion")
        ao.inputs["Distance"].default_value = 0.02
        ao.samples = 16
        nt.links.new(ao.outputs["AO"], emit.inputs["Color"])
    elif kind == "shell":
        # white where geometry stands above the slice, transparent below it
        sep = nt.nodes.new("ShaderNodeSeparateXYZ")
        cmp = nt.nodes.new("ShaderNodeMath"); cmp.operation = "GREATER_THAN"
        cmp.inputs[1].default_value = shell_min
        mix = nt.nodes.new("ShaderNodeMixShader")
        tr = nt.nodes.new("ShaderNodeBsdfTransparent")
        nt.links.new(geo.outputs["Position"], sep.inputs[0])
        nt.links.new(sep.outputs["Z"], cmp.inputs[0])
        nt.links.new(cmp.outputs[0], mix.inputs[0])
        nt.links.new(tr.outputs[0], mix.inputs[1])
        nt.links.new(emit.outputs[0], mix.inputs[2])
        nt.links.new(mix.outputs[0], out.inputs["Surface"])
    return m


def render_pass(scene, objs, kind, tmp: pathlib.Path, soil, shell_min=None):
    m = pass_material(kind, soil, shell_min)
    for o in objs:
        o.data.materials.clear()
        o.data.materials.append(m)
    ground_obj = objs[-1]
    if kind == "albedo":
        gm = bpy.data.materials.new("soil")
        gm.use_nodes = True
        e = gm.node_tree.nodes.new("ShaderNodeEmission")
        e.inputs["Color"].default_value = (*soil, 1)
        gm.node_tree.links.new(e.outputs[0], gm.node_tree.nodes["Material Output"].inputs["Surface"])
        ground_obj.data.materials.clear(); ground_obj.data.materials.append(gm)
    scene.render.film_transparent = kind == "shell"
    scene.world.color = (0, 0, 0)
    scene.render.image_settings.file_format = "OPEN_EXR"
    scene.render.image_settings.color_depth = "32"
    scene.render.image_settings.color_mode = "RGBA"
    path = tmp / f"{kind}{'' if shell_min is None else f'_{shell_min:.4f}'}.exr"
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    return common.read_image(path)


def downsample(a, factor):
    h, w = a.shape[:2]
    return a.reshape(h // factor, factor, w // factor, factor, -1).mean(axis=(1, 3))


def linear_to_srgb(x):
    x = np.clip(x, 0, 1)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055)


def bake(variant: str, lean_name: str, lean: float, out_dir: pathlib.Path, seed: int, shells: bool,
         out_res: int | None = None):
    scene = common.reset_scene(samples=24, seed=seed)
    scene.world = bpy.data.worlds.new("w")
    scene.render.resolution_x = scene.render.resolution_y = BAKE_RES
    scene.render.pixel_aspect_x = scene.render.pixel_aspect_y = 1
    scene.render.filter_size = 1.2
    scene.view_settings.view_transform = "Raw" if "Raw" in [i.identifier for i in scene.view_settings.bl_rna.properties["view_transform"].enum_items] else "Standard"
    cam_data = bpy.data.cameras.new("cam")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = PATCH
    cam = bpy.data.objects.new("cam", cam_data)
    cam.location = (PATCH / 2, PATCH / 2, 1.0)
    scene.collection.objects.link(cam)
    scene.camera = cam

    V, F, C, R = grow(variant, lean, seed)
    blades = build_object("blades", V, F, C, R)
    gmesh, gobj, soil, specks = ground(variant, seed)
    speck_obj = build_object("specks", *specks)
    objs = [blades, speck_obj, gobj]
    tmp = pathlib.Path(bpy.app.tempdir) / f"turf_{variant}_{lean_name}"
    tmp.mkdir(parents=True, exist_ok=True)

    f = BAKE_RES // (out_res or OUT_RES)
    albedo = downsample(render_pass(scene, objs, "albedo", tmp, soil)[..., :3], f)
    normal = downsample(render_pass(scene, objs, "normal", tmp, soil)[..., :3], f)
    n = normal * 2 - 1
    n *= np.where(n[..., 2:3] < 0, -1.0, 1.0)
    n /= np.linalg.norm(n, axis=2, keepdims=True) + 1e-8
    normal = n * 0.5 + 0.5
    rough = downsample(render_pass(scene, objs, "rough", tmp, soil)[..., 0:1], f)[..., 0]
    height = downsample(render_pass(scene, objs, "height", tmp, soil)[..., 0:1], f)[..., 0]
    ao = downsample(render_pass(scene, objs, "ao", tmp, soil)[..., 0:1], f)[..., 0]
    ao = np.clip(0.25 + 0.75 * ao, 0, 1)
    # soil has no roughness attribute; where the ground shows, it is matte
    rough = np.where(rough < 0.05, 0.92, rough)

    prefix = out_dir / f"turf_{variant}_{lean_name}"
    common.write_png(prefix.with_name(prefix.name + "_normal.png"), normal)
    if lean_name != "against":
        # Leaning the other way changes only the normals: the stripe comes from
        # how light meets the blades, so "against" shares albedo and ORM.
        common.write_png(prefix.with_name(prefix.name + "_albedo.png"), linear_to_srgb(albedo))
        common.write_png(prefix.with_name(prefix.name + "_orm.png"), np.stack([ao, rough, np.clip(height, 0, 1)], axis=2))
    stats = {"blades": int(len(F)), "albedoMean": [round(float(x), 4) for x in albedo.reshape(-1, 3).mean(0)]}
    if shells:
        for i in range(SHELLS):
            hmin = MAX_H * 0.62 * (1 - (i + 0.5) / SHELLS)
            # shells only draw within a few metres of the eye: half resolution
            cov = downsample(render_pass(scene, objs, "shell", tmp, soil, hmin)[..., 3:4], BAKE_RES // SHELL_RES)[..., 0]
            common.write_png(out_dir / f"turf_{variant}_shell_{i}.png", cov)
        stats["shellHeights"] = [round(MAX_H * 0.62 * (1 - (i + 0.5) / SHELLS), 4) for i in range(SHELLS)]
    return stats


def main():
    args = common.script_args() or ["natural"]
    variant = args[0]
    out_dir = common.FIELD_OUT / "turf" / variant
    out_dir.mkdir(parents=True, exist_ok=True)
    report = {}
    if "preview" in args:
        global BAKE_RES, OUT_RES
        BAKE_RES = OUT_RES = 512
        out_dir = pathlib.Path("/private/tmp/fsrev/preview")
        out_dir.mkdir(parents=True, exist_ok=True)
        report["with"] = bake(variant, "with", 0.0, out_dir, 101, shells=False)
        print("PREVIEW", out_dir)
    elif variant == "natural":
        report["with"] = bake("natural", "with", 0.0, out_dir, 101, shells=True)
        report["against"] = bake("natural", "against", math.pi, out_dir, 101, shells=False)
        report["worn"] = bake("worn", "any", 0.0, out_dir, 202, shells=False, out_res=WORN_RES)
    elif variant == "synthetic":
        report["any"] = bake("synthetic", "any", 0.0, out_dir, 303, shells=True)
    if "preview" in args:
        return
    common.write_json(out_dir / "bake.json", {"patchMetres": PATCH, "resolution": OUT_RES,
                                             "shellResolution": SHELL_RES, "wornResolution": WORN_RES,
                                             "heightScaleMetres": MAX_H, **report})
    print("BAKED", variant, report)


main()
