"""Review renders for the bowl kit. They load the exported modules - the
same files a renderer gets - rather than Blender's working meshes, so a
review shows what ships.

    blender --background --factory-startup --python tools/blender/bowl/build.py -- review [shots...]

Shots: seat, pressbox, wide, row16, upper, fieldlevel, tunnel, exterior, tabletop.
Renders go to assets/actors/bowl/review/. Lighting here is a neutral review
rig - the Lighting actor owns the real one.
"""
from __future__ import annotations

import json
import math

import bpy
from mathutils import Vector

import common as C
import kit

REVIEW = kit.ROOT / "docs" / "actors" / "bowl" / "review"


def cycles(samples: int = 64, w: int = 1600, h: int = 900) -> None:
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    prefs = bpy.context.preferences.addons["cycles"].preferences
    try:
        prefs.compute_device_type = "METAL"
        prefs.get_devices()
        for d in prefs.devices:
            d.use = True
        scene.cycles.device = "GPU"
    except Exception:
        scene.cycles.device = "CPU"
    scene.cycles.samples = samples
    scene.cycles.use_denoising = True
    scene.cycles.max_bounces = 4
    scene.render.resolution_x, scene.render.resolution_y = w, h
    scene.render.image_settings.file_format = "PNG"
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium High Contrast"


def world_studio() -> None:
    w = bpy.data.worlds.new("studio")
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.26, 0.27, 0.29, 1)
    bg.inputs["Strength"].default_value = 0.8
    bpy.context.scene.world = w


def world_night(strength: float = 0.35) -> None:
    w = bpy.data.worlds.new("night")
    w.use_nodes = True
    nt = w.node_tree
    env = nt.nodes.new("ShaderNodeTexEnvironment")
    env.image = bpy.data.images.load(str(kit.ROOT / "assets" / "generated" / "lighting" / "stadium_night.hdr"))
    nt.links.new(env.outputs["Color"], nt.nodes["Background"].inputs["Color"])
    nt.nodes["Background"].inputs["Strength"].default_value = strength
    bpy.context.scene.world = w


def area(name, loc_local_yards, target_local_yards, size_m, watts, color=(1.0, 0.95, 0.88)):
    light = bpy.data.lights.new(name, "AREA")
    light.size = size_m
    light.energy = watts
    light.color = color
    obj = bpy.data.objects.new(name, light)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = C.bl(*loc_local_yards)
    obj.visible_camera = False
    look(obj, C.bl(*target_local_yards))
    return obj


def look(obj, target) -> None:
    d = Vector(target) - obj.location
    obj.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()


def camera(loc_local_yards, target_local_yards, lens: float = 24.0):
    cam = bpy.data.cameras.new("cam")
    cam.lens = lens
    cam.clip_end = 2000
    obj = bpy.data.objects.new("cam", cam)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = C.bl(*loc_local_yards)
    look(obj, C.bl(*target_local_yards))
    bpy.context.scene.camera = obj
    return obj


def render(name: str) -> None:
    REVIEW.mkdir(parents=True, exist_ok=True)
    scene = bpy.context.scene
    scene.render.image_settings.file_format = "JPEG"
    scene.render.image_settings.quality = 85
    scene.render.filepath = str(REVIEW / f"{name}.jpg")
    bpy.ops.render.render(write_still=True)
    print(f"[review] {name}.jpg", flush=True)


def import_module(name: str):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(kit.OUT / f"{name}.glb"))
    return [o for o in bpy.data.objects if o not in before]


def ground(size_m=400, color=(0.05, 0.16, 0.07, 1)):
    bpy.ops.mesh.primitive_plane_add(size=size_m)
    g = bpy.context.active_object
    mat = C.material("review_turf", color=color, roughness=0.9)
    g.data.materials.append(mat)
    return g


# ───────────────────────────── instancing seats ─────────────────────────────

def seat_points(module: str, predicate=None, name="seats"):
    """A point cloud of seats.json with a Geometry Nodes instancer, so tens of
    thousands of chairs render as instances of one imported module."""
    data = json.loads((kit.OUT / "seats.json").read_text())
    verts, yaws = [], []
    for tier in data["tiers"]:
        for row in tier["rows"]:
            for sec_id, seats in row["sections"].items():
                for x, z, yaw in seats:
                    if predicate and not predicate(tier["tier"], row["row"], sec_id, x, z):
                        continue
                    verts.append(C.bl(x, row["floorY"], z))
                    yaws.append(yaw)
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], [])
    attr = me.attributes.new("yaw", "FLOAT", "POINT")
    attr.data.foreach_set("value", yaws)
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)

    src = import_module(module)
    proto = src[0]
    proto.hide_render = True
    proto.location = (0, 0, 0)

    ng = bpy.data.node_groups.new(f"{name}_instancer", "GeometryNodeTree")
    ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    n = ng.nodes
    gin, gout = n.new("NodeGroupInput"), n.new("NodeGroupOutput")
    inst = n.new("GeometryNodeInstanceOnPoints")
    info = n.new("GeometryNodeObjectInfo")
    info.inputs["As Instance"].default_value = True
    info.inputs["Object"].default_value = proto
    info.transform_space = "ORIGINAL"
    attr_node = n.new("GeometryNodeInputNamedAttribute")
    attr_node.data_type = "FLOAT"
    attr_node.inputs["Name"].default_value = "yaw"
    combine = n.new("ShaderNodeCombineXYZ")
    to_rot = n.new("FunctionNodeEulerToRotation")
    ng.links.new(gin.outputs[0], inst.inputs["Points"])
    ng.links.new(info.outputs["Geometry"], inst.inputs["Instance"])
    # glTF import already turned the module Z-up; the chair faces local +z,
    # which in Blender is -Y, and a yaw about local +y is a turn about +Z.
    ng.links.new(attr_node.outputs["Attribute"], combine.inputs["Z"])
    ng.links.new(combine.outputs["Vector"], to_rot.inputs["Euler"])
    ng.links.new(to_rot.outputs["Rotation"], inst.inputs["Rotation"])
    ng.links.new(inst.outputs["Instances"], gout.inputs[0])
    mod = obj.modifiers.new("instancer", "NODES")
    mod.node_group = ng
    return obj


# ───────────────────────────── shots ─────────────────────────────

def shot_seat() -> None:
    C.reset()
    cycles(128, 1600, 900)
    world_studio()
    ground(20, (0.3, 0.3, 0.3, 1))
    import seat as SEAT
    mats = SEAT.materials()
    for k, (detail, up) in enumerate(((0, False), (0, True), (1, False), (2, True))):
        b = SEAT.seat(detail, up)
        o = b.build(mats, smooth_angle=50 if detail < 2 else None)
        o.location.x += 0.55 * k
    area("key", (1.5, 2.2, 1.8), (0.3, 0.5, 0), 1.5, 400)
    area("rim", (-1.5, 1.8, -1.5), (0.3, 0.5, 0), 1.0, 200, (0.7, 0.8, 1.0))
    camera((2.4, 1.35, 2.9), (0.55, 0.45, 0.0), 50)
    render("seat_front")
    camera((-1.3, 1.5, -2.6), (0.55, 0.5, 0.0), 50)
    render("seat_back")


def stadium_scene(preset="club"):
    """The kit as the actor assembles it for a preset: stands, every band but
    this preset's fill, and this preset's near patch. A neutral review rig:
    floods on the rim all round, the night probe."""
    C.reset()
    cycles(96, 1920, 1080)
    world_night(0.25)
    import_module("stands")
    for o in import_module("seats_far"):
        if o.name.startswith(f"fill_{preset}"):
            o.hide_render = True
    for o in import_module("near"):
        if not o.name.startswith(f"near_{preset}"):
            o.hide_render = True
    ground(700)
    for k in range(8):
        t = 0.3 + k * math.pi / 4
        x, z = kit.bowl_point(74, t)
        area(f"flood{k}", (x, 58, z), (0, 0, 0), 12, 9e4)


def eye_of(preset):
    import structure
    reg = next(r for r in structure.presets() if r["id"] == preset)
    return reg["eye"]


def shot_club():
    stadium_scene("club")
    ex, ey, ez = eye_of("club")
    camera((ex, ey, ez), (ex, 1.0, 0.0), 20)
    render("bowl_club_seat")


def shot_foreground():
    stadium_scene("club")
    ex, ey, ez = eye_of("club")
    camera((ex + 0.6, ey + 0.2, ez + 0.3), (ex - 1.5, ey - 3.0, ez - 6.0), 24)
    render("bowl_club_foreground")


def shot_crowd_closeup():
    stadium_scene("club")
    ex, ey, ez = eye_of("club")
    a = math.radians(62)
    camera((ex, ey, ez), (ex + math.sin(a) * 30, ey - 6, ez - math.cos(a) * 30), 22)
    render("bowl_crowd_closeup")


def shot_wide():
    stadium_scene("upper")
    ex, ey, ez = eye_of("upper")
    camera((ex, ey, ez), (0, 2, -8), 18)
    render("bowl_wide")


def shot_fieldlevel():
    stadium_scene("club")
    camera((0, 1.9, kit.SHAPE["halfWidth"] + 2.0), (-40, 8, -10), 18)
    render("bowl_field_level")


def shot_endzone():
    stadium_scene("endzone")
    ex, ey, ez = eye_of("endzone")
    camera((ex, ey, ez), (0, 2, 0), 20)
    render("bowl_endzone_seat")


def shot_tabletop():
    C.reset()
    cycles(96, 1600, 1000)
    world_night(0.4)
    import_module("table")
    ground(400)
    area("key", (0, 90, 120), (0, 0, 0), 40, 2e5)
    camera((0, 110, 190), (0, 0, -10), 32)
    render("bowl_tabletop")


SHOTS = {"seat": shot_seat, "club": shot_club, "foreground": shot_foreground, "closeup": shot_crowd_closeup, "wide": shot_wide,
         "fieldlevel": shot_fieldlevel, "endzone": shot_endzone, "tabletop": shot_tabletop}


def build(names: list[str]) -> None:
    for name in names or list(SHOTS):
        SHOTS[name]()
