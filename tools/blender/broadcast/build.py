"""Build the Broadcast actor's footballs: one to NFL rules, one to college rules.

    nice -n 10 blender --background -t 4 --factory-startup \
        --python tools/blender/broadcast/build.py [-- --review]

Writes, for each ball, assets/actors/broadcast/football_<league>.usdz for the
headset and a .glb beside it for Three.js and Filament, plus manifest.json.
With --review it also renders docs/actors/broadcast/review/football.png.

Everything is made here from nothing: the pebble grain, the panel seams and
the lace are numpy and geometry, so there is no download to licence.

Axes. The ball's long axis is local +x and its laces face local +y (up). In
Blender that is +X and +Z; the exporters' Y-up conversion hands a renderer
exactly local axes in metres, so a client scales by 1/0.9144 into yards.

Rules the geometry follows:
  NFL (Wilson "The Duke" spec): 11-11.25 in long, 21-21.25 in round the
  middle, 28 in round the tips; four panels, one lace of eight crossings;
  no stripes.
  College (NCAA rule 1-3-1): the same size range, with a 1 in white stripe
  3-3.25 in from each tip on the two panels adjacent to the lace panel.
"""
from __future__ import annotations

import json
import math
import pathlib
import sys

import bpy
import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[3]
OUT = ROOT / "assets" / "actors" / "broadcast"
TEX = ROOT / ".work" / "broadcast-textures"
REVIEW = ROOT / "docs" / "actors" / "broadcast" / "review"
INCH = 0.0254

# ───────────────────────────── spec ─────────────────────────────

LENGTH = 11.1 * INCH                      # tip to tip
GIRTH = 21.1 * INCH                       # round the middle
RADIUS = GIRTH / (2 * math.pi)            # 0.0852 m
HALF = LENGTH / 2
RINGS = 34                                # along the long axis
SIDES = 36                                # round it

LACE = {"length": 0.62,                   # of the ball's length, centred
        "crossings": 8, "width": 0.34 * INCH, "cross": 1.25 * INCH,
        "lift": 0.10 * INCH, "thick": 0.07 * INCH}
STRIPE = {"from_tip": 3.1 * INCH, "width": 1.0 * INCH,
          "arc": math.radians(180)}      # the lace half of the ball

LEAGUES = {"nfl": {"stripes": False}, "college": {"stripes": True}}


def profile(x: float) -> float:
    """Radius at x along the axis. A prolate spheroid sharpened toward the
    tips - a football is more pointed than an ellipse - with a small round
    at each tip so the mesh closes cleanly."""
    t = min(1.0, abs(x) / HALF)
    return RADIUS * max(0.0, 1.0 - t ** 2.15) ** 0.78 + 0.0015 * (1 - t)


# ───────────────────────────── textures ─────────────────────────────

def _blur(a: np.ndarray, sigma: float) -> np.ndarray:
    """Gaussian blur on a torus, via FFT, so the texture tiles round the ball."""
    h, w = a.shape
    fy = np.fft.fftfreq(h)[:, None]
    fx = np.fft.fftfreq(w)[None, :]
    g = np.exp(-2 * (math.pi ** 2) * (sigma ** 2) * (fx ** 2 + fy ** 2))
    return np.real(np.fft.ifft2(np.fft.fft2(a) * g))


def textures() -> dict[str, pathlib.Path]:
    """Leather albedo, pebble normal and ORM (R occlusion, G roughness, B metal).

    u runs round the ball, v along it; the image is 2:1 because the ball is
    about 2.4x as long round as it is along a meridian from tip to tip... then
    squashed so pebbles stay round on the surface."""
    TEX.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(1869)       # Rutgers v Princeton
    W, H = 1024, 512
    v_axis = np.arange(H)[:, None] / H

    # Pebbles: sparse impulses blurred to bumps, then clipped so the tops
    # flatten the way a pebbled leather's do.
    imp = (rng.random((H, W)) > 0.93).astype(np.float64)
    bumps = _blur(imp, 1.15)
    bumps = np.clip(bumps / (bumps.max() + 1e-9) * 1.6, 0, 1) ** 0.8
    fine = _blur(rng.random((H, W)), 0.8)
    fine = (fine - fine.min()) / (fine.max() - fine.min() + 1e-9)
    # The grain wears smooth toward each tip, where a hand never grips.
    tipfade = np.clip(np.minimum(v_axis, 1 - v_axis) / 0.16, 0, 1) ** 1.5
    height = (0.75 * bumps + 0.25 * fine) * (0.25 + 0.75 * tipfade)

    # Panel seams: four meridians round the ball, a groove pressed into the grain.
    u = np.arange(W)[None, :] / W
    seam = np.zeros((H, W))
    for k in range(4):
        d = np.abs(((u - k / 4) + 0.5) % 1.0 - 0.5) * W
        seam = np.maximum(seam, np.exp(-(d / 2.2) ** 2))
    height = height * (1 - 0.9 * seam) - 0.35 * seam

    # Normal from the height field.
    strength = 1.5
    dx = (np.roll(height, -1, axis=1) - np.roll(height, 1, axis=1)) * strength
    dy = (np.roll(height, -1, axis=0) - np.roll(height, 1, axis=0)) * strength
    n = np.stack([-dx, -dy, np.ones_like(height)], axis=-1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    normal = (n * 0.5 + 0.5)

    # Albedo: a tanned brown, darker in the pebble valleys and along the
    # seams, with a broad worn sheen along the middle of each panel.
    base = np.array([0.30, 0.135, 0.058])
    tone = 0.86 + 0.2 * height[..., None] - 0.45 * seam[..., None]
    v = np.arange(H)[:, None] / H
    wear = 1 + 0.08 * np.exp(-((v - 0.5) / 0.22) ** 2)
    albedo = np.clip(base[None, None, :] * tone * wear[..., None], 0, 1)

    rough = np.clip(0.62 - 0.18 * bumps + 0.12 * seam, 0.3, 0.9)
    occ = np.clip(1 - 0.45 * seam - 0.15 * (1 - bumps), 0, 1)
    orm = np.stack([occ, rough, np.zeros_like(rough)], axis=-1)

    out = {}
    for name, arr, colour in (("leather_albedo", albedo, True), ("leather_normal", normal, False),
                              ("leather_orm", orm, False)):
        path = TEX / f"{name}.png"
        img = bpy.data.images.new(name, W, H, alpha=False, float_buffer=False)
        img.colorspace_settings.name = "sRGB" if colour else "Non-Color"
        rgba = np.concatenate([arr, np.ones((H, W, 1))], axis=-1)
        img.pixels.foreach_set(rgba.astype(np.float32).ravel())
        img.filepath_raw = str(path)
        img.file_format = "PNG"
        img.save()
        out[name] = path
    return out


# ───────────────────────────── materials ─────────────────────────────

def material(name: str, color=(0.8, 0.8, 0.8, 1), roughness=0.6, maps: dict | None = None):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = roughness
    if maps:
        uv = nt.nodes.new("ShaderNodeUVMap")
        uv.uv_map = "UVMap"

        def tex(path, data):
            node = nt.nodes.new("ShaderNodeTexImage")
            node.image = bpy.data.images.load(str(path), check_existing=True)
            node.image.colorspace_settings.name = "Non-Color" if data else "sRGB"
            nt.links.new(uv.outputs["UV"], node.inputs["Vector"])
            return node
        nt.links.new(tex(maps["leather_albedo"], False).outputs["Color"], bsdf.inputs["Base Color"])
        nm = nt.nodes.new("ShaderNodeNormalMap")
        nt.links.new(tex(maps["leather_normal"], True).outputs["Color"], nm.inputs["Color"])
        nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
        sep = nt.nodes.new("ShaderNodeSeparateColor")
        nt.links.new(tex(maps["leather_orm"], True).outputs["Color"], sep.inputs["Color"])
        nt.links.new(sep.outputs["Green"], bsdf.inputs["Roughness"])
    return mat


# ───────────────────────────── geometry ─────────────────────────────

class Mesh:
    def __init__(self, name: str):
        self.name, self.verts, self.faces, self.uvs, self.mats, self.slots = name, [], [], [], [], []

    def slot(self, m: str) -> int:
        if m not in self.slots:
            self.slots.append(m)
        return self.slots.index(m)

    def face(self, idx, uvs, m):
        self.faces.append(tuple(idx))
        self.uvs.append(tuple(uvs))
        self.mats.append(self.slot(m))

    def add(self, p) -> int:
        self.verts.append(tuple(p))
        return len(self.verts) - 1

    @property
    def triangles(self) -> int:
        return sum(len(f) - 2 for f in self.faces)

    def build(self, materials):
        me = bpy.data.meshes.new(self.name)
        me.from_pydata(self.verts, [], self.faces)
        layer = me.uv_layers.new(name="UVMap")
        layer.data.foreach_set("uv", [c for f in self.uvs for uv in f for c in uv])
        for s in self.slots:
            me.materials.append(materials[s])
        me.polygons.foreach_set("material_index", self.mats)
        me.validate(clean_customdata=False)
        me.update()
        import bmesh
        bm = bmesh.new()
        bm.from_mesh(me)
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(me)
        bm.free()
        me.shade_smooth()
        me.set_sharp_from_angle(angle=math.radians(50))
        obj = bpy.data.objects.new(self.name, me)
        bpy.context.scene.collection.objects.link(obj)
        obj["triangles"] = self.triangles
        return obj


def point(x: float, angle: float, lift: float = 0.0):
    """On the leather at x along the axis, `angle` round it from the laces
    (+Z), `lift` metres off the surface."""
    r = profile(x) + lift
    return (x, -math.sin(angle) * r, math.cos(angle) * r)


def shell(m: Mesh) -> None:
    xs = [-HALF + LENGTH * i / RINGS for i in range(RINGS + 1)]
    grid = [[m.add(point(x, 2 * math.pi * k / SIDES)) for k in range(SIDES + 1)] for x in xs]
    for i in range(RINGS):
        for k in range(SIDES):
            a, b, c, d = grid[i][k], grid[i][k + 1], grid[i + 1][k + 1], grid[i + 1][k]
            # u round the ball starting at the laces, v along it.
            m.face((a, d, c, b), ((k / SIDES, i / RINGS), (k / SIDES, (i + 1) / RINGS),
                                  ((k + 1) / SIDES, (i + 1) / RINGS), ((k + 1) / SIDES, i / RINGS)), "leather")


def band(m: Mesh, x0: float, x1: float, a0: float, a1: float, lift: float, material: str,
         steps: int = 12, along: int = 2) -> None:
    """A strip lying on the leather between two stations and two angles, as
    one shared-vertex grid so it shades as a single smooth surface."""
    grid = [[m.add(point(x0 + (x1 - x0) * i / along, a0 + (a1 - a0) * j / steps, lift))
             for j in range(steps + 1)] for i in range(along + 1)]
    for i in range(along):
        for j in range(steps):
            m.face((grid[i][j], grid[i + 1][j], grid[i + 1][j + 1], grid[i][j + 1]),
                   ((i / along, j / steps), ((i + 1) / along, j / steps),
                    ((i + 1) / along, (j + 1) / steps), (i / along, (j + 1) / steps)), material)


def tube(m: Mesh, pts, radius: float, material: str, sides: int = 6) -> None:
    """A closed pipe through points; used for the lace, so it sits on the
    leather as a rounded cord rather than a paper strip."""
    rings = []
    for i, p in enumerate(pts):
        a, b = pts[max(0, i - 1)], pts[min(len(pts) - 1, i + 1)]
        t = [b[k] - a[k] for k in range(3)]
        tl = math.sqrt(sum(c * c for c in t)) or 1e-9
        t = [c / tl for c in t]
        # Radial direction from the ball's axis is the cord's "up".
        up = [0.0, p[1], p[2]]
        ul = math.sqrt(sum(c * c for c in up)) or 1e-9
        up = [c / ul for c in up]
        side = [t[1] * up[2] - t[2] * up[1], t[2] * up[0] - t[0] * up[2], t[0] * up[1] - t[1] * up[0]]
        ring = []
        for k in range(sides):
            ang = 2 * math.pi * k / sides
            off = [math.cos(ang) * up[c] * radius + math.sin(ang) * side[c] * radius for c in range(3)]
            ring.append(m.add((p[0] + off[0], p[1] + off[1], p[2] + off[2])))
        rings.append(ring)
    for i in range(len(rings) - 1):
        for k in range(sides):
            k2 = (k + 1) % sides
            m.face((rings[i][k], rings[i + 1][k], rings[i + 1][k2], rings[i][k2]),
                   ((i, k / sides), (i + 1, k / sides), (i + 1, (k + 1) / sides), (i, (k + 1) / sides)), material)
    for ring, flip in ((rings[0], True), (rings[-1], False)):
        idx = list(reversed(ring)) if flip else ring
        m.face(idx, [(0.5, 0.5)] * len(idx), material)


def lace(m: Mesh) -> None:
    """The spine along the top seam and eight crossings over it, as cords
    lying on the leather."""
    half = HALF * LACE["length"]
    r = LACE["thick"]
    spine = [point(-half + 2 * half * i / 20, 0.0, r * 0.9) for i in range(21)]
    tube(m, spine, r * 1.1, "lace", sides=6)
    n = LACE["crossings"]
    span = LACE["cross"] / RADIUS / 2
    for i in range(n):
        xc = -half * 0.9 + (2 * half * 0.9) * i / (n - 1)
        cross = [point(xc, -span + 2 * span * j / 8, r * (1.0 + 0.8 * math.sin(math.pi * j / 8))) for j in range(9)]
        tube(m, cross, r, "lace", sides=6)


def stripes(m: Mesh) -> None:
    a = STRIPE["arc"] / 2
    for sign in (-1, 1):
        x_mid = sign * (HALF - STRIPE["from_tip"] - STRIPE["width"] / 2)
        band(m, x_mid - STRIPE["width"] / 2, x_mid + STRIPE["width"] / 2, -a, a, 0.0007, "stripe", steps=40, along=2)


# ───────────────────────────── export ─────────────────────────────

def export(obj, name: str) -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    glb, usdz = OUT / f"{name}.glb", OUT / f"{name}.usdz"
    bpy.ops.export_scene.gltf(filepath=str(glb), export_format="GLB", use_selection=True, export_yup=True,
                              export_apply=True, export_image_format="WEBP", export_image_quality=85,
                              export_cameras=False, export_lights=False)
    bpy.ops.wm.usd_export(filepath=str(usdz), selected_objects_only=True, export_materials=True,
                          generate_preview_surface=True, export_textures_mode="NEW", overwrite_textures=True,
                          relative_paths=True, convert_orientation=True,
                          export_global_forward_selection="NEGATIVE_Z", export_global_up_selection="Y",
                          meters_per_unit=1.0, export_animation=False, usdz_downscale_size="512")
    return {"usdz": f"actors/broadcast/{name}.usdz", "glb": f"actors/broadcast/{name}.glb",
            "triangles": obj["triangles"], "parts": len(obj.material_slots),
            "bytes": {"usdz": usdz.stat().st_size, "glb": glb.stat().st_size},
            "lengthMeters": round(LENGTH, 4), "girthMeters": round(GIRTH, 4)}


def review(objs) -> None:
    """Each ball three ways - side, three-quarter from above, end-on - under a
    floodlight-like key, for the art-director pass."""
    REVIEW.mkdir(parents=True, exist_ok=True)
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x, scene.render.resolution_y = 1500, 900
    world = bpy.data.worlds.new("review")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.02, 0.025, 0.04, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.5
    scene.world = world
    poses = [(0, 0, 0), (math.radians(-35), 0, math.radians(35)), (0, 0, math.radians(90))]
    copies = []
    for row, o in enumerate(objs):
        for col, rot in enumerate(poses):
            c = o if col == 0 else o.copy()
            if col:
                scene.collection.objects.link(c)
            c.location = ((col - 1) * 0.36, 0, (0.5 - row) * 0.26)
            c.rotation_euler = rot
            copies.append(c)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    scene.collection.objects.link(cam)
    cam.location = (0, -1.9, 0.12)
    cam.rotation_euler = (math.radians(87), 0, 0)
    cam.data.lens = 70
    scene.camera = cam
    for loc, energy in (((0.9, -1.2, 1.5), 260), ((-1.2, -0.6, 0.2), 60), ((0, 1.0, 0.8), 90)):
        light = bpy.data.objects.new("key", bpy.data.lights.new("key", "AREA"))
        light.data.energy, light.data.size = energy, 0.8
        light.location = loc
        direction = -__import__("mathutils").Vector(loc)
        light.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
        scene.collection.objects.link(light)
    scene.render.filepath = str(REVIEW / "football.png")
    bpy.ops.render.render(write_still=True)


def main() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    maps = textures()
    mats = {"leather": material("leather", maps=maps),
            "lace": material("lace", color=(0.93, 0.92, 0.88, 1), roughness=0.7),
            "stripe": material("stripe", color=(0.95, 0.95, 0.93, 1), roughness=0.55)}
    manifest = {"about": "Footballs for the Broadcast actor; see tools/blender/broadcast/build.py.",
                "axes": "long axis +x, laces +y, metres; scale by 1/0.9144 into scene yards",
                "models": {}}
    objs = []
    for league, rule in LEAGUES.items():
        m = Mesh(f"football_{league}")
        shell(m)
        lace(m)
        if rule["stripes"]:
            stripes(m)
        obj = m.build(mats)
        manifest["models"][league] = export(obj, f"football_{league}")
        objs.append(obj)
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    print("BROADCAST", json.dumps(manifest["models"]))
    if "--review" in sys.argv:
        review(objs)


main()
