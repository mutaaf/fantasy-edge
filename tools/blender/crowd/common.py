"""Scene plumbing shared by the crowd scripts: reset, materials, render setup."""
from __future__ import annotations

import pathlib
import sys

import bpy

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUT = ROOT / "assets" / "actors" / "crowd"
REVIEW = OUT / "review"


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    import addon_utils
    addon_utils.enable("cycles", default_set=True)
    for m in ("io_scene_gltf2",):
        try:
            addon_utils.enable(m, default_set=True)
        except Exception:
            pass


def args() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def attr_material(name: str, head_centre=None, paint: str = "none", mode: str = "base"):
    """Material that shows a fan's colour attributes.

    mode "base" renders albedo, "tint" the mask, "lit" albedo previewed with
    the club colours applied so a review render reads like the stadium will.
    A head gets its face drawn procedurally in object space.
    """
    mat = bpy.data.materials.new(name)
    nt = mat.node_tree
    nt.nodes.clear()
    N, L = nt.nodes, nt.links
    out = N.new("ShaderNodeOutputMaterial")
    base = N.new("ShaderNodeAttribute"); base.attribute_name = "base"; base.attribute_type = "GEOMETRY"
    tint = N.new("ShaderNodeAttribute"); tint.attribute_name = "tint"; tint.attribute_type = "GEOMETRY"
    colour = base.outputs["Color"]
    mask = tint.outputs["Color"]
    # Fabric grain: a faint high-frequency noise so flat cloth is not plastic.
    noise = N.new("ShaderNodeTexNoise"); noise.inputs["Scale"].default_value = 420.0; noise.inputs["Detail"].default_value = 2.0
    grain = N.new("ShaderNodeMapRange"); grain.inputs["To Min"].default_value = 0.93; grain.inputs["To Max"].default_value = 1.05
    L.new(noise.outputs["Fac"], grain.inputs["Value"])
    mul = N.new("ShaderNodeMix"); mul.data_type = "RGBA"; mul.blend_type = "MULTIPLY"; mul.inputs["Factor"].default_value = 1.0
    L.new(colour, mul.inputs[6]); L.new(grain.outputs["Result"], mul.inputs[7])
    colour = mul.outputs[2]

    if head_centre is not None:
        colour, mask = _face(nt, colour, mask, head_centre, paint)

    if mode == "lit":
        sep = N.new("ShaderNodeSeparateColor"); L.new(mask, sep.inputs[0])
        prim = N.new("ShaderNodeMix"); prim.data_type = "RGBA"; prim.blend_type = "MULTIPLY"
        prim.inputs[7].default_value = (0.55, 0.06, 0.07, 1)
        L.new(sep.outputs[0], prim.inputs["Factor"]); L.new(colour, prim.inputs[6])
        sec = N.new("ShaderNodeMix"); sec.data_type = "RGBA"; sec.blend_type = "MULTIPLY"
        sec.inputs[7].default_value = (0.95, 0.95, 0.95, 1)
        L.new(sep.outputs[1], sec.inputs["Factor"]); L.new(prim.outputs[2], sec.inputs[6])
        pnt = N.new("ShaderNodeMix"); pnt.data_type = "RGBA"; pnt.blend_type = "MIX"
        pnt.inputs[7].default_value = (0.55, 0.06, 0.07, 1)
        L.new(sep.outputs[2], pnt.inputs["Factor"]); L.new(sec.outputs[2], pnt.inputs[6])
        bsdf = N.new("ShaderNodeBsdfPrincipled")
        bsdf.inputs["Roughness"].default_value = 0.8
        L.new(pnt.outputs[2], bsdf.inputs["Base Color"])
        L.new(bsdf.outputs[0], out.inputs["Surface"])
    else:
        em = N.new("ShaderNodeEmission")
        L.new(colour if mode == "base" else mask, em.inputs["Color"])
        L.new(em.outputs[0], out.inputs["Surface"])
    return mat


def _face(nt, colour, mask, c, paint):
    """Eyes, brows, mouth, cheeks: soft ellipses in the head's object space."""
    N, L = nt.nodes, nt.links
    tc = N.new("ShaderNodeTexCoord")
    off = N.new("ShaderNodeVectorMath"); off.operation = "SUBTRACT"
    off.inputs[1].default_value = tuple(c)
    L.new(tc.outputs["Object"], off.inputs[0])
    sep = N.new("ShaderNodeSeparateXYZ"); L.new(off.outputs[0], sep.inputs[0])

    def blob(cx, cz, rx, rz, front=True, sharp=6.0):
        # exp(-((x-cx)/rx)^2 - ((z-cz)/rz)^2) on the front of the face only
        dx = N.new("ShaderNodeMath"); dx.operation = "SUBTRACT"; L.new(sep.outputs[0], dx.inputs[0]); dx.inputs[1].default_value = cx
        qx = N.new("ShaderNodeMath"); qx.operation = "DIVIDE"; L.new(dx.outputs[0], qx.inputs[0]); qx.inputs[1].default_value = rx
        px = N.new("ShaderNodeMath"); px.operation = "POWER"; L.new(qx.outputs[0], px.inputs[0]); px.inputs[1].default_value = 2
        dz = N.new("ShaderNodeMath"); dz.operation = "SUBTRACT"; L.new(sep.outputs[2], dz.inputs[0]); dz.inputs[1].default_value = cz
        qz = N.new("ShaderNodeMath"); qz.operation = "DIVIDE"; L.new(dz.outputs[0], qz.inputs[0]); qz.inputs[1].default_value = rz
        pz = N.new("ShaderNodeMath"); pz.operation = "POWER"; L.new(qz.outputs[0], pz.inputs[0]); pz.inputs[1].default_value = 2
        s = N.new("ShaderNodeMath"); s.operation = "ADD"; L.new(px.outputs[0], s.inputs[0]); L.new(pz.outputs[0], s.inputs[1])
        g = N.new("ShaderNodeMath"); g.operation = "MULTIPLY"; L.new(s.outputs[0], g.inputs[0]); g.inputs[1].default_value = -sharp
        e = N.new("ShaderNodeMath"); e.operation = "EXPONENT"; L.new(g.outputs[0], e.inputs[0])
        if not front:
            return e.outputs[0]
        fr = N.new("ShaderNodeMath"); fr.operation = "LESS_THAN"; L.new(sep.outputs[1], fr.inputs[0]); fr.inputs[1].default_value = -0.05
        m = N.new("ShaderNodeMath"); m.operation = "MULTIPLY"; L.new(e.outputs[0], m.inputs[0]); L.new(fr.outputs[0], m.inputs[1])
        return m.outputs[0]

    def mix(col, fac, rgb, strength=1.0):
        f = N.new("ShaderNodeMath"); f.operation = "MULTIPLY"; L.new(fac, f.inputs[0]); f.inputs[1].default_value = strength
        m = N.new("ShaderNodeMix"); m.data_type = "RGBA"; m.clamp_factor = True
        L.new(f.outputs[0], m.inputs["Factor"]); L.new(col, m.inputs[6]); m.inputs[7].default_value = (*rgb, 1)
        return m.outputs[2]

    add = lambda a, b: _add(nt, a, b)
    eyes = add(blob(0.031, 0.010, 0.0085, 0.0085, sharp=4), blob(-0.031, 0.010, 0.0085, 0.0085, sharp=4))
    whites = add(blob(0.031, 0.010, 0.013, 0.007, sharp=4), blob(-0.031, 0.010, 0.013, 0.007, sharp=4))
    brows = add(blob(0.033, 0.034, 0.021, 0.0065, sharp=3), blob(-0.033, 0.034, 0.021, 0.0065, sharp=3))
    mouth = blob(0.0, -0.050, 0.024, 0.0060, sharp=3)
    cheeks = add(blob(0.042, -0.018, 0.020, 0.016, sharp=3), blob(-0.042, -0.018, 0.020, 0.016, sharp=3))
    colour = mix(colour, whites, (0.78, 0.76, 0.72), 0.45)
    colour = mix(colour, eyes, (0.05, 0.04, 0.035), 1.0)
    colour = mix(colour, brows, (0.07, 0.055, 0.045), 1.0)
    colour = mix(colour, mouth, (0.26, 0.08, 0.07), 0.85)
    colour = mix(colour, cheeks, (0.55, 0.18, 0.16), 0.10)
    if paint != "none":
        if paint == "stripes":
            p = add(add(blob(0.042, -0.010, 0.018, 0.004, sharp=5), blob(0.042, -0.022, 0.018, 0.004, sharp=5)),
                    add(blob(-0.042, -0.010, 0.018, 0.004, sharp=5), blob(-0.042, -0.022, 0.018, 0.004, sharp=5)))
        elif paint == "cheek":
            p = blob(0.045, -0.018, 0.016, 0.013, sharp=4)
        else:  # half: one side of the face
            gt = N.new("ShaderNodeMath"); gt.operation = "GREATER_THAN"; L.new(sep.outputs[0], gt.inputs[0]); gt.inputs[1].default_value = 0.0
            fr = N.new("ShaderNodeMath"); fr.operation = "LESS_THAN"; L.new(sep.outputs[1], fr.inputs[0]); fr.inputs[1].default_value = -0.02
            lo = N.new("ShaderNodeMath"); lo.operation = "LESS_THAN"; L.new(sep.outputs[2], lo.inputs[0]); lo.inputs[1].default_value = 0.05
            p1 = N.new("ShaderNodeMath"); p1.operation = "MULTIPLY"; L.new(gt.outputs[0], p1.inputs[0]); L.new(fr.outputs[0], p1.inputs[1])
            p2 = N.new("ShaderNodeMath"); p2.operation = "MULTIPLY"; L.new(p1.outputs[0], p2.inputs[0]); L.new(lo.outputs[0], p2.inputs[1])
            p = p2.outputs[0]
        # Paint is a mask (B), drawn over a light base so the chip reads true.
        colour = mix(colour, p, (0.86, 0.86, 0.86), 1.0)
        comb = N.new("ShaderNodeSeparateColor"); L.new(mask, comb.inputs[0])
        mx = N.new("ShaderNodeMath"); mx.operation = "MAXIMUM"; L.new(comb.outputs[2], mx.inputs[0]); L.new(p, mx.inputs[1])
        cc = N.new("ShaderNodeCombineColor"); L.new(comb.outputs[0], cc.inputs[0]); L.new(comb.outputs[1], cc.inputs[1]); L.new(mx.outputs[0], cc.inputs[2])
        mask = cc.outputs[0]
    return colour, mask


def _add(nt, a, b):
    m = nt.nodes.new("ShaderNodeMath"); m.operation = "ADD"; m.use_clamp = True
    nt.links.new(a, m.inputs[0]); nt.links.new(b, m.inputs[1])
    return m.outputs[0]


def review_render(path, width, height, camera_loc, camera_rot, ortho=None, engine="BLENDER_EEVEE", samples=32,
                  transparent=False, world=(0.18, 0.18, 0.2)):
    sc = bpy.context.scene
    sc.render.engine = engine
    if engine == "CYCLES":
        sc.cycles.samples = samples
        sc.cycles.use_denoising = True
    sc.render.resolution_x, sc.render.resolution_y = width, height
    sc.render.film_transparent = transparent
    sc.view_settings.view_transform = "AgX"
    if sc.world is None:
        sc.world = bpy.data.worlds.new("w")
    sc.world.color = world
    cam_data = bpy.data.cameras.new("cam")
    if ortho:
        cam_data.type = "ORTHO"; cam_data.ortho_scale = ortho
    cam = bpy.data.objects.new("cam", cam_data)
    sc.collection.objects.link(cam)
    cam.location, cam.rotation_euler = camera_loc, camera_rot
    sc.camera = cam
    sc.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    return cam
