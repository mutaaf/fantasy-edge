"""Render the field and sideline under floodlights, for the critique log.

Builds a slice of a stadium floor in metres from the shipped assets alone - the
baked turf, the paint distance field, the mowing pattern, the wear and macro
maps - and re-imports every prop from its exported .glb, so what is judged is
what ships. A 1.85 m mannequin stands in for scale. Lit by the stadium's night
probe and four floodlight banks.

    blender -b --factory-startup --python tools/blender/field/review_render.py -- /tmp/shots nfl
    blender -b ... -- /tmp/shots nfl field-level        # one shot

Shots: field-level, sideline, row-16, goal-mouth, macro-turf, props-lineup.
"""
from __future__ import annotations

import json
import math
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import common  # noqa: E402

import bpy  # noqa: E402

YD = common.YARD
W = 160 / 3
ROOT = common.ROOT


def img(path, colour=True):
    im = bpy.data.images.load(str(path), check_existing=True)
    im.colorspace_settings.name = "sRGB" if colour else "Non-Color"
    return im


def turf_material(league: str, variant: str = "natural"):
    """The review stand-in for the engine's turf shader: tiled blades, a mowing
    pattern choosing between the two lean normals, wear toward the worn set,
    macro tone, and paint thresholded from the distance field."""
    F = common.FIELD_OUT
    m = bpy.data.materials.new("review_turf")
    m.use_nodes = True
    nt = m.node_tree
    N, L = nt.nodes, nt.links
    bsdf = N["Principled BSDF"]
    tc = N.new("ShaderNodeTexCoord")
    sep = N.new("ShaderNodeSeparateXYZ")
    L.new(tc.outputs["Object"], sep.inputs[0])

    # tiled UV: metres / 0.40
    tile = N.new("ShaderNodeVectorMath"); tile.operation = "DIVIDE"
    tile.inputs[1].default_value = (0.40, 0.40, 1)
    L.new(tc.outputs["Object"], tile.inputs[0])

    def tex(path, colour, vec, interp="Linear", ext="REPEAT"):
        t = N.new("ShaderNodeTexImage")
        t.image = img(path, colour)
        t.interpolation = interp
        t.extension = ext
        L.new(vec, t.inputs["Vector"])
        return t

    base = F / "turf" / variant
    if variant == "natural":
        alb = tex(base / "turf_natural_with_albedo.png", True, tile.outputs[0])
        nrm_w = tex(base / "turf_natural_with_normal.png", False, tile.outputs[0])
        nrm_a = tex(base / "turf_natural_against_normal.png", False, tile.outputs[0])
        orm = tex(base / "turf_natural_with_orm.png", False, tile.outputs[0])
        walb = tex(base / "turf_worn_any_albedo.png", True, tile.outputs[0])
    else:
        alb = tex(base / "turf_synthetic_any_albedo.png", True, tile.outputs[0])
        nrm_w = nrm_a = tex(base / "turf_synthetic_any_normal.png", False, tile.outputs[0])
        orm = tex(base / "turf_synthetic_any_orm.png", False, tile.outputs[0])
        walb = alb
    breakup = tex(base / "paint_breakup.png", False, tile.outputs[0])

    # field UV over the markings canvas: x yards from the left goal line = X / YD
    cx0, cx1, cy0, cy1 = -16.0, 116.0, -(81.375 - W) / 2, W + (81.375 - W) / 2
    fu = N.new("ShaderNodeMath"); fu.operation = "DIVIDE"; fu.inputs[1].default_value = YD
    L.new(sep.outputs["X"], fu.inputs[0])
    fv = N.new("ShaderNodeMath"); fv.operation = "DIVIDE"; fv.inputs[1].default_value = YD
    L.new(sep.outputs["Y"], fv.inputs[0])
    u = N.new("ShaderNodeMapRange"); u.inputs[1].default_value = cx0; u.inputs[2].default_value = cx1
    L.new(fu.outputs[0], u.inputs[0])
    v = N.new("ShaderNodeMapRange"); v.inputs[1].default_value = cy0; v.inputs[2].default_value = cy1
    L.new(fv.outputs[0], v.inputs[0])
    uv = N.new("ShaderNodeCombineXYZ")
    L.new(u.outputs[0], uv.inputs[0]); L.new(v.outputs[0], uv.inputs[1])

    sdf = tex(F / "markings" / league / "paint_sdf.png", False, uv.outputs[0], interp="Linear", ext="EXTEND")
    maps = tex(F / "maps" / league / "field_maps.png", False, uv.outputs[0], ext="EXTEND")
    mow = tex(F / "maps" / league / "mow_patterns.png", False, uv.outputs[0], ext="EXTEND")
    msep = N.new("ShaderNodeSeparateColor"); L.new(maps.outputs["Color"], msep.inputs[0])
    mowsep = N.new("ShaderNodeSeparateColor"); L.new(mow.outputs["Color"], mowsep.inputs[0])
    ssep = N.new("ShaderNodeSeparateColor"); L.new(sdf.outputs["Color"], ssep.inputs[0])

    # stripe: pick the five-yard pattern, blend the two lean normals by it
    nmix = N.new("ShaderNodeMix"); nmix.data_type = "RGBA"
    L.new(mowsep.outputs["Red"], nmix.inputs["Factor"])
    L.new(nrm_a.outputs["Color"], nmix.inputs[6]); L.new(nrm_w.outputs["Color"], nmix.inputs[7])

    # albedo: macro tone, a touch of stripe tint, wear toward the worn set
    wear = N.new("ShaderNodeMix"); wear.data_type = "RGBA"
    L.new(msep.outputs["Green"], wear.inputs["Factor"])
    L.new(alb.outputs["Color"], wear.inputs[6]); L.new(walb.outputs["Color"], wear.inputs[7])
    macro = N.new("ShaderNodeMath"); macro.operation = "MULTIPLY_ADD"
    macro.inputs[1].default_value = 0.6; macro.inputs[2].default_value = 0.7
    L.new(msep.outputs["Red"], macro.inputs[0])
    stripe_t = N.new("ShaderNodeMath"); stripe_t.operation = "MULTIPLY_ADD"
    stripe_t.inputs[1].default_value = 0.12; stripe_t.inputs[2].default_value = 0.9
    L.new(mowsep.outputs["Red"], stripe_t.inputs[0])
    tone = N.new("ShaderNodeMath"); tone.operation = "MULTIPLY"
    L.new(macro.outputs[0], tone.inputs[0]); L.new(stripe_t.outputs[0], tone.inputs[1])
    tinted = N.new("ShaderNodeMix"); tinted.data_type = "RGBA"; tinted.blend_type = "MULTIPLY"
    tinted.inputs["Factor"].default_value = 1.0
    L.new(wear.outputs[2], tinted.inputs[6])
    tcol = N.new("ShaderNodeCombineColor")
    for k in range(3):
        L.new(tone.outputs[0], tcol.inputs[k])
    L.new(tcol.outputs[0], tinted.inputs[7])

    # paint: threshold the SDF, eroded by the grass the paint sits in
    def paint_cov(channel):
        e = N.new("ShaderNodeMath"); e.operation = "MULTIPLY_ADD"
        e.inputs[1].default_value = 0.035; e.inputs[2].default_value = -0.0175
        L.new(breakup.outputs["Color"], e.inputs[0])
        s = N.new("ShaderNodeMath"); s.operation = "ADD"
        L.new(ssep.outputs[channel], s.inputs[0]); L.new(e.outputs[0], s.inputs[1])
        ss = N.new("ShaderNodeMapRange"); ss.interpolation_type = "SMOOTHSTEP"
        ss.inputs[1].default_value = 0.495; ss.inputs[2].default_value = 0.505
        L.new(s.outputs[0], ss.inputs[0])
        return ss.outputs[0]
    white = paint_cov("Red")
    yellow = paint_cov("Green")
    over_white = N.new("ShaderNodeMix"); over_white.data_type = "RGBA"
    L.new(white, over_white.inputs["Factor"])
    L.new(tinted.outputs[2], over_white.inputs[6])
    over_white.inputs[7].default_value = (0.82, 0.82, 0.80, 1)
    over_yel = N.new("ShaderNodeMix"); over_yel.data_type = "RGBA"
    L.new(yellow, over_yel.inputs["Factor"])
    L.new(over_white.outputs[2], over_yel.inputs[6])
    over_yel.inputs[7].default_value = (0.85, 0.62, 0.02, 1)
    L.new(over_yel.outputs[2], bsdf.inputs["Base Color"])

    osep = N.new("ShaderNodeSeparateColor"); L.new(orm.outputs["Color"], osep.inputs[0])
    rmix = N.new("ShaderNodeMix"); rmix.data_type = "FLOAT"
    L.new(white, rmix.inputs["Factor"])
    L.new(osep.outputs["Green"], rmix.inputs[2]); rmix.inputs[3].default_value = 0.78
    L.new(rmix.outputs[0], bsdf.inputs["Roughness"])
    nmap = N.new("ShaderNodeNormalMap"); nmap.inputs["Strength"].default_value = 1.0
    L.new(nmix.outputs[2], nmap.inputs["Color"])
    L.new(nmap.outputs[0], bsdf.inputs["Normal"])
    return m


def build_floor(league: str, variant: str):
    mat = turf_material(league, variant)
    mesh = bpy.data.meshes.new("floor")
    x0, x1, y0, y1 = -16 * YD, 116 * YD, -14 * YD, (W + 14) * YD
    mesh.from_pydata([(x0, y0, 0), (x1, y0, 0), (x1, y1, 0), (x0, y1, 0)], [], [(0, 1, 2, 3)])
    obj = bpy.data.objects.new("floor", mesh)
    obj.data.materials.append(mat)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def import_prop(name, loc, rot_z=0.0, league="nfl"):
    path = common.SIDELINE_OUT / f"{name}.glb"
    before = set(bpy.context.scene.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    new = [o for o in bpy.context.scene.objects if o not in before]
    root = bpy.data.objects.new(f"place_{name}", None)
    bpy.context.scene.collection.objects.link(root)
    for o in new:
        if o.parent is None:
            o.parent = root
    root.location = loc
    root.rotation_euler = (0, 0, rot_z)
    return root


def mannequin(loc):
    grey = common.material("mannequin", (0.35, 0.36, 0.38), 0.6)
    parts = []
    for (r, d, z, r2) in ((0.16, 0.85, 0.425, 0.13), (0.2, 0.6, 1.2, 0.22)):
        bpy.ops.mesh.primitive_cone_add(vertices=16, radius1=r, radius2=r2, depth=d, location=(loc[0], loc[1], z))
        parts.append(bpy.context.active_object)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.115, location=(loc[0], loc[1], 1.735))
    parts.append(bpy.context.active_object)
    for p in parts:
        p.data.materials.append(grey)


def lights():
    world = bpy.data.worlds.new("night")
    bpy.context.scene.world = world
    world.use_nodes = True
    env = world.node_tree.nodes.new("ShaderNodeTexEnvironment")
    hdr = ROOT / "assets" / "generated" / "lighting" / "stadium_night.hdr"
    if hdr.exists():
        env.image = bpy.data.images.load(str(hdr))
        world.node_tree.links.new(env.outputs["Color"], world.node_tree.nodes["Background"].inputs["Color"])
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.08
    cx, cy = 50 * YD, W / 2 * YD
    for (dx, dy) in ((-70, -60), (70, -60), (-70, 60), (70, 60)):
        ld = bpy.data.lights.new("flood", "AREA")
        ld.energy = 6.5e4          # ~2000 lux on the field from four banks at 80 m
        ld.size = 14
        ld.color = (1.0, 0.97, 0.92)
        lo = bpy.data.objects.new("flood", ld)
        lo.location = (cx + dx, cy + dy, 48)
        direction = (lo.location - __import__("mathutils").Vector((cx, cy, 0))).normalized()
        lo.rotation_euler = direction.to_track_quat("Z", "Y").to_euler()
        bpy.context.scene.collection.objects.link(lo)


def camera(name, loc, target, lens=24):
    import mathutils
    cd = bpy.data.cameras.new(name)
    cd.lens = lens
    cd.clip_start = 0.02
    cd.clip_end = 800
    co = bpy.data.objects.new(name, cd)
    co.location = loc
    d = mathutils.Vector(target) - mathutils.Vector(loc)
    co.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.collection.objects.link(co)
    return co


def place_sideline(league: str):
    m = json.loads((common.SIDELINE_OUT / "manifest.json").read_text())["props"]
    gp = "goalpost_nfl" if league == "nfl" else "goalpost_college"
    py = "pylon_nfl" if league == "nfl" else "pylon_college"
    # goal post on the left end line, facing the field (+X)
    import_prop(gp, (-10 * YD, W / 2 * YD, 0), rot_z=-math.pi / 2)
    for x in (-10, 0):
        for y in (0, W):
            import_prop(py, (x * YD + (0.06 if x == 0 else -0.06), y * YD + (0.06 if y == 0 else -0.06), 0))
    side = -12 * YD                                           # the near team area
    for i, x in enumerate((32, 40, 48)):
        import_prop("bench", (x * YD, side - 1.5, 0), rot_z=0)
    import_prop("heater_fan", (36 * YD, side - 0.4, 0))
    import_prop("cooler_station", (27 * YD, side - 2.2, 0))
    import_prop("tablet_station", (44 * YD, side + 0.6, 0))
    import_prop("medical_tent", (58 * YD, side - 3.0, 0))
    import_prop("chain_set", (25 * YD, W * YD + 2.0, 0), rot_z=math.pi)
    import_prop("down_marker", (20 * YD, W * YD + 2.0, 0), rot_z=math.pi)
    import_prop("camera_cart", (10 * YD, -3.0, 0), rot_z=math.pi / 2)
    import_prop("cable_run", (14 * YD, -5.5, 0))
    import_prop("endzone_platform", (-15 * YD, W / 2 * YD + 12, 0), rot_z=-math.pi / 2)
    import_prop("fieldgoal_net", (-10 * YD - 3.5, W / 2 * YD, 0), rot_z=-math.pi / 2)
    import_prop("kicking_net", (20 * YD, side - 0.5, 0))
    import_prop("ball_bag", (22 * YD, side + 0.8, 0))
    import_prop("penalty_flag", (18 * YD, 18 * YD, 0))
    import_prop("bean_bag", (23 * YD, 26 * YD, 0))
    mannequin((30 * YD, side + 0.8, 0))
    mannequin((3 * YD, 20 * YD, 0))


SHOTS = {
    # name: (camera location m, target m, lens)
    "field-level": ((12 * YD, 17 * YD, 0.35), (-8 * YD, 26 * YD, 2.2), 20),
    "sideline": ((34 * YD, -14 * YD, 1.7), (15 * YD, 5 * YD, 1.0), 22),
    "row-16": ((50 * YD, -40 * YD, 16.0), (20 * YD, 25 * YD, 0.0), 28),
    "goal-mouth": ((6 * YD, 26.6 * YD, 1.2), (-5 * YD, 26.6 * YD, 1.0), 24),
    "macro-turf": ((30.15 * YD, 20 * YD, 0.12), (30.0 * YD, 20.35 * YD, 0.0), 35),
    "props-lineup": ((38 * YD, -2 * YD, 1.6), (38 * YD, -14 * YD, 0.8), 26),
}


def main():
    args = common.script_args()
    out = pathlib.Path(args[0] if args else "/private/tmp/fsrev/shots")
    league = args[1] if len(args) > 1 else "nfl"
    only = args[2].split(",") if len(args) > 2 else list(SHOTS)
    variant = "synthetic" if "synthetic" in args else "natural"
    scene = common.reset_scene(samples=96)
    scene.cycles.use_denoising = True
    scene.render.resolution_x, scene.render.resolution_y = 1600, 900
    scene.view_settings.view_transform = "AgX"
    build_floor(league, variant)
    lights()
    place_sideline(league)
    out.mkdir(parents=True, exist_ok=True)
    for name in only:
        loc, tgt, lens = SHOTS[name]
        scene.camera = camera(name, loc, tgt, lens)
        scene.render.image_settings.file_format = "JPEG"
        scene.render.image_settings.quality = 90
        scene.render.filepath = str(out / f"{league}-{variant}-{name}.jpg")
        bpy.ops.render.render(write_still=True)
        print("SHOT", scene.render.filepath)


main()
