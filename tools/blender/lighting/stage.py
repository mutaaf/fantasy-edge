"""A proxy stadium to light: field, bowl, light banks, floods, sky.

Nothing here ships. It exists so the probe sees a stadium and the review
shots judge the lighting assets on something shaped like the real bowl.
Imported by ibl.py and shots.py.
"""
from __future__ import annotations

import math
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import common as C  # noqa: E402
import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

YD = C.YD

# Look numbers every actor consumes. Written into lighting-tokens.json by
# build.py; kept here so the probe, the shots and the tokens cannot disagree.
LOOK = {
    "colorTemperatureK": 5600,
    # Broadcast white balance is set to the lights, so LED white reads almost
    # neutral on camera; this is its linear tint under that balance.
    "floodTintLinear": [1.0, 0.985, 0.955],
    "floodWattsPerBank": 120000.0,       # Cycles watts for the proxy; the ratio is what matters
    "floodSpotDegrees": 62.0,
    "floodSpotBlend": 0.7,
    "floodRadiusM": 2.5,
    "skyStrength": 1.0,
    # An LED sports fixture's face is thousands of times brighter than the lit
    # turf; the glTF carries a modest emissive strength for real-time use,
    # and the proxy lifts it to something physical before the probe sees it.
    "lensEmissionProxy": 2500.0,
}


def turf_material():
    m = bpy.data.materials.new("proxy_turf")
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    coord = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(coord.outputs["Object"], sep.inputs[0])
    div = nt.nodes.new("ShaderNodeMath"); div.operation = "DIVIDE"; div.inputs[1].default_value = 5 * YD
    nt.links.new(sep.outputs["X"], div.inputs[0])
    flo = nt.nodes.new("ShaderNodeMath"); flo.operation = "FLOOR"
    nt.links.new(div.outputs[0], flo.inputs[0])
    mod = nt.nodes.new("ShaderNodeMath"); mod.operation = "FLOORED_MODULO"; mod.inputs[1].default_value = 2
    nt.links.new(flo.outputs[0], mod.inputs[0])
    mix = nt.nodes.new("ShaderNodeMix"); mix.data_type = "RGBA"
    mix.inputs["A"].default_value = (0.045, 0.125, 0.035, 1)
    mix.inputs["B"].default_value = (0.060, 0.155, 0.045, 1)
    nt.links.new(mod.outputs[0], mix.inputs["Factor"])
    noise = nt.nodes.new("ShaderNodeTexNoise"); noise.inputs["Scale"].default_value = 3.0
    mul = nt.nodes.new("ShaderNodeMix"); mul.data_type = "RGBA"; mul.blend_type = "MULTIPLY"
    mul.inputs["Factor"].default_value = 0.25
    nt.links.new(mix.outputs["Result"], mul.inputs["A"])
    nt.links.new(noise.outputs["Color"], mul.inputs["B"])
    nt.links.new(mul.outputs["Result"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.72
    bsdf.inputs["Specular IOR Level"].default_value = 0.35
    return m


def crowd_material(name, base):
    """Seats full of people: a speckle of jackets and faces over the concrete."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    # Object coordinates in metres, so a cell is about one person wide; the
    # mesh's generated 0..1 coordinates made cells the size of a section.
    coord = nt.nodes.new("ShaderNodeTexCoord")
    vor = nt.nodes.new("ShaderNodeTexVoronoi")
    vor.inputs["Scale"].default_value = 1.6
    nt.links.new(coord.outputs["Object"], vor.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    els = ramp.color_ramp.elements
    els[0].position, els[0].color = 0.0, (0.03, 0.03, 0.035, 1)
    els[1].position, els[1].color = 1.0, (0.55, 0.52, 0.48, 1)
    for pos, col in ((0.25, (0.30, 0.09, 0.03, 1)), (0.45, base + (1,)), (0.62, (0.10, 0.10, 0.12, 1)),
                     (0.8, (0.45, 0.30, 0.22, 1))):
        e = els.new(pos)
        e.color = col
    ramp.color_ramp.interpolation = "CONSTANT"
    nt.links.new(vor.outputs["Color"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.85
    return m


def tier_mesh(name, inner, outer, rise, mat, rows=14, seg=180):
    verts, faces = [], []
    for r in range(rows + 1):
        f = r / rows
        off = inner + (outer - inner) * f
        y = rise[0] + (rise[1] - rise[0]) * f
        for s in range(seg):
            t = 2 * math.pi * s / seg
            bx, bz = C.bowl_xz(off, t)
            verts.append(C.to_blender(bx + 50, y, bz))
    for r in range(rows):
        for s in range(seg):
            a, b = r * seg + s, r * seg + (s + 1) % seg
            faces.append((a, b, b + seg, a + seg))
    return C.mesh_object(name, verts, faces, mat)


def fascia(name, offset, y0, y1, mat, seg=180):
    verts, faces = [], []
    for s in range(seg):
        t = 2 * math.pi * s / seg
        bx, bz = C.bowl_xz(offset, t)
        verts.append(C.to_blender(bx + 50, y0, bz))
        verts.append(C.to_blender(bx + 50, y1, bz))
    for s in range(seg):
        a, b = 2 * s, 2 * ((s + 1) % seg)
        faces.append((a, b, b + 1, a + 1))
    return C.mesh_object(name, verts, faces, mat)


def field():
    turf = turf_material()
    w, l = C.HALF_WIDTH * YD, C.HALF_LENGTH * YD
    C.mesh_object("turf", [(-l - 8, -w - 8, 0), (l + 8, -w - 8, 0), (l + 8, w + 8, 0), (-l - 8, w + 8, 0)],
                  [(0, 1, 2, 3)], turf)
    paint = C.material("paint", color=(0.75, 0.75, 0.72), rough=0.6)
    for yd in range(0, 101, 5):
        x = (yd - 50) * YD
        hw = 0.1 * YD if yd % 10 else 0.12 * YD
        C.mesh_object(f"line{yd}", [(x - hw, -w, 0.01), (x + hw, -w, 0.01), (x + hw, w, 0.01), (x - hw, w, 0.01)],
                      [(0, 1, 2, 3)], paint)
    for side in (-1, 1):
        C.mesh_object(f"side{side}", [(-l, side * w - 0.1, 0.01), (l, side * w - 0.1, 0.01),
                                      (l, side * w + 0.1, 0.01), (-l, side * w + 0.1, 0.01)], [(0, 1, 2, 3)], paint)
    ez = C.material("endzone", color=(0.06, 0.09, 0.22), rough=0.7)
    for sgn in (-1, 1):
        x0, x1 = sgn * 50 * YD, sgn * 60 * YD
        C.mesh_object(f"ez{sgn}", [(min(x0, x1), -w, 0.005), (max(x0, x1), -w, 0.005),
                                   (max(x0, x1), w, 0.005), (min(x0, x1), w, 0.005)], [(0, 1, 2, 3)], ez)


def bowl():
    lower = crowd_material("crowd_lower", (0.55, 0.22, 0.05))
    upper = crowd_material("crowd_upper", (0.50, 0.20, 0.05))
    concrete = C.material("concrete", color=(0.22, 0.21, 0.2), rough=0.9)
    t_low, t_up = C.TIERS
    tier_mesh("tier_lower", t_low["inner"], t_low["outer"], t_low["rise"], lower)
    tier_mesh("tier_upper", t_up["inner"], t_up["outer"], t_up["rise"], upper)
    tier_mesh("concourse", t_low["outer"], t_up["inner"], (t_low["rise"][1], t_low["rise"][1]), concrete, rows=2)
    wall = C.material("wall", color=(0.03, 0.03, 0.035), rough=0.5, emit=(0.25, 0.35, 0.75), emit_strength=0.25)
    fascia("front_wall", 5.4, 0.0, 1.4, wall)
    ribbon = C.material("ribbon", color=(0.02, 0.02, 0.02), rough=0.4, emit=(1.0, 0.55, 0.15), emit_strength=0.6)
    fascia("ribbon", 41.6, 21.0, 23.6, ribbon)
    back = C.material("back_wall", color=(0.12, 0.115, 0.11), rough=0.9)
    fascia("upper_back", 70.0, 45.8, 47.5, back)


def rigs(lod="lod0"):
    mounts, source = C.placeholder_mounts()
    path = C.OUT_LIGHT / "rigs" / f"light_bank_{lod}.glb"
    placed = []
    for m in mounts:
        before = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=str(path))
        new = [o for o in bpy.data.objects if o not in before]
        loc = Vector(C.to_blender(m["x"], m["y"], m["z"]))
        aim = Vector(C.to_blender(*m["aim"]))
        flat = Vector((aim.x - loc.x, aim.y - loc.y, 0)).normalized()
        # The model faces -Y. Rotating (0, -1) by yaw gives (sin yaw, -cos yaw);
        # set that equal to the flat direction to the aim point.
        yaw = math.atan2(flat.x, -flat.y)
        for o in new:
            if o.parent is None:
                o.location = loc
                o.rotation_mode = "XYZ"
                o.rotation_euler = (0, 0, yaw)
        for o in new:
            for slot in getattr(o, "material_slots", []):
                mat = slot.material
                if mat and mat.use_nodes and ("lens" in mat.name or "face" in mat.name):
                    for node in mat.node_tree.nodes:
                        if node.type == "BSDF_PRINCIPLED":
                            node.inputs["Emission Strength"].default_value = LOOK["lensEmissionProxy"]
                        elif node.type == "EMISSION":
                            node.inputs["Strength"].default_value = LOOK["lensEmissionProxy"]
        placed.append((m, loc, aim, new))
    return placed, source


def floods(placed):
    lights = []
    for m, loc, aim, _ in placed:
        # The bank's lower rows reach the near field, its upper rows the far:
        # aim each flood a little past the centre, toward the opposite half.
        target = aim + (aim - loc).normalized() * 0.0
        target.z = 0
        data = bpy.data.lights.new(f"flood_{m['id']}", "SPOT")
        data.energy = LOOK["floodWattsPerBank"]
        data.spot_size = math.radians(LOOK["floodSpotDegrees"])
        data.spot_blend = LOOK["floodSpotBlend"]
        data.shadow_soft_size = LOOK["floodRadiusM"]
        data.color = LOOK["floodTintLinear"]
        obj = C.link(bpy.data.objects.new(f"flood_{m['id']}", data))
        front = (target - loc).normalized()
        obj.location = loc + front * 1.5
        obj.rotation_euler = C.aim_rotation(obj.location, target)
        lights.append(obj)
    return lights


def world(sky="night", strength=None):
    w = bpy.data.worlds.new(f"world_{sky}")
    w.use_nodes = True
    nt = w.node_tree
    bg = nt.nodes["Background"]
    env = nt.nodes.new("ShaderNodeTexEnvironment")
    env.image = bpy.data.images.load(str(C.OUT_SKY / "env" / f"sky_{sky}.exr"))
    env.image.colorspace_settings.name = "Non-Color"
    # Our equirect puts -Z (the scene's far side, Blender +Y) at the centre
    # column and +X a quarter turn right. Blender's lookup needs -90 degrees
    # about Z to agree - measured by orient.py, not reasoned: the half turn
    # that looks right on paper mirrors the sky.
    coord = nt.nodes.new("ShaderNodeTexCoord")
    mapping = nt.nodes.new("ShaderNodeMapping")
    mapping.inputs["Rotation"].default_value = (0, 0, -math.pi / 2)
    nt.links.new(coord.outputs["Generated"], mapping.inputs["Vector"])
    nt.links.new(mapping.outputs["Vector"], env.inputs["Vector"])
    nt.links.new(env.outputs["Color"], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = LOOK["skyStrength"] if strength is None else strength
    bpy.context.scene.world = w
    return w


def build(sky="night", lod="lod0"):
    scene = C.reset()
    field()
    bowl()
    placed, source = rigs(lod)
    floods(placed)
    world(sky)
    return scene, placed, source
