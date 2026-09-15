"""Blender-side helpers for the bowl kit: meshes, materials, export.

Every mesh is accumulated in plain lists by `Builder` and turned into one
Blender object at the end, so a 50,000-seat bowl is a handful of objects
rather than 50,000 - which is also what the renderers want to draw.

Units: builders take local yards (kit.py's space) and store Blender metres,
with Blender's Z up. The glTF exporter's +Y-up conversion then gives glTF
(x, y, z) = local (x, y, z) x 0.9144, so a module drops into a renderer's
local space with one uniform scale of 1/0.9144.
"""
from __future__ import annotations

import json
import math
import pathlib

import bpy
import bmesh  # noqa: F401  (kept for scripts that import common)

import kit

OUT = kit.OUT
TEX = OUT / "textures"
MOD = OUT / "modules"
Y = kit.YARD


def reset() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0


def bl(x: float, y: float, z: float) -> tuple[float, float, float]:
    """Local yards to Blender metres (Z up)."""
    return (x * Y, -z * Y, y * Y)


# ───────────────────────────── geometry ─────────────────────────────

class Builder:
    """Triangles in, one object out. Positions are local yards; UVs are
    whatever the caller says (trim-sheet v, tiling u)."""

    def __init__(self, name: str):
        self.name = name
        self.verts: list[tuple[float, float, float]] = []
        self.faces: list[tuple[int, ...]] = []
        self.uvs: list[tuple[tuple[float, float], ...]] = []
        self.mats: list[int] = []
        self.slots: list[str] = []

    def slot(self, material: str) -> int:
        if material not in self.slots:
            self.slots.append(material)
        return self.slots.index(material)

    def face(self, pts, uvs, material: str) -> None:
        base = len(self.verts)
        self.verts.extend(bl(*p) for p in pts)
        self.faces.append(tuple(range(base, base + len(pts))))
        self.uvs.append(tuple(uvs))
        self.mats.append(self.slot(material))

    def quad(self, a, b, c, d, material: str, uv=((0, 0), (1, 0), (1, 1), (0, 1))) -> None:
        self.face((a, b, c, d), uv, material)

    def tri(self, a, b, c, material: str, uv=((0, 0), (1, 0), (0.5, 1))) -> None:
        self.face((a, b, c), uv, material)

    def tube(self, pts, radius: float, material: str, sides: int = 6, caps: bool = False,
             v0: float = 0.0, v1: float = 1.0) -> None:
        """A pipe through points (local yards). Frames are parallel-transported
        so a rail round a corner does not twist."""
        if len(pts) < 2:
            return
        rings = []
        prev_n = None
        for i, p in enumerate(pts):
            a = pts[max(0, i - 1)]
            b = pts[min(len(pts) - 1, i + 1)]
            t = _norm((b[0] - a[0], b[1] - a[1], b[2] - a[2]))
            if prev_n is None:
                up = (0.0, 1.0, 0.0) if abs(t[1]) < 0.9 else (1.0, 0.0, 0.0)
                n = _norm(_cross(t, up))
            else:
                n = _norm(_sub(prev_n, _scale(t, _dot(prev_n, t))))
            bnorm = _cross(t, n)
            prev_n = n
            ring = []
            for k in range(sides):
                ang = 2 * math.pi * k / sides
                off = _add(_scale(n, math.cos(ang) * radius), _scale(bnorm, math.sin(ang) * radius))
                ring.append(_add(p, off))
            rings.append(ring)
        length = 0.0
        for i in range(len(pts) - 1):
            seg = math.dist(pts[i], pts[i + 1])
            for k in range(sides):
                k2 = (k + 1) % sides
                u0, u1 = k / sides, (k + 1) / sides
                self.quad(rings[i][k], rings[i][k2], rings[i + 1][k2], rings[i + 1][k], material,
                          uv=((length, v0 + (v1 - v0) * u0), (length, v0 + (v1 - v0) * u1),
                              (length + seg, v0 + (v1 - v0) * u1), (length + seg, v0 + (v1 - v0) * u0)))
            length += seg
        if caps:
            for ring, flip in ((rings[0], True), (rings[-1], False)):
                pts_ = list(reversed(ring)) if flip else ring
                self.face(pts_, [(0.5 + 0.5 * math.cos(2 * math.pi * k / sides),
                                  0.5 + 0.5 * math.sin(2 * math.pi * k / sides)) for k in range(sides)], material)

    def box(self, centre, size, material: str, yaw: float = 0.0, uv_scale: float = 1.0,
            skip=()) -> None:
        """An axis box (local yards) turned by yaw about +y. `skip` names faces to leave off."""
        cx, cy, cz = centre
        sx, sy, sz = (s / 2 for s in size)
        c, s = math.cos(yaw), math.sin(yaw)

        def P(x, y, z):
            return (cx + x * c + z * s, cy + y, cz - x * s + z * c)
        v = {n: P(*xyz) for n, xyz in {
            "a": (-sx, -sy, -sz), "b": (sx, -sy, -sz), "c": (sx, sy, -sz), "d": (-sx, sy, -sz),
            "e": (-sx, -sy, sz), "f": (sx, -sy, sz), "g": (sx, sy, sz), "h": (-sx, sy, sz)}.items()}
        W, H, D = size[0] * uv_scale, size[1] * uv_scale, size[2] * uv_scale
        faces = {"back": ("b", "a", "d", "c", W, H), "front": ("e", "f", "g", "h", W, H),
                 "left": ("a", "e", "h", "d", D, H), "right": ("f", "b", "c", "g", D, H),
                 "top": ("h", "g", "c", "d", W, D), "bottom": ("a", "b", "f", "e", W, D)}
        for name, (p0, p1, p2, p3, uw, vh) in faces.items():
            if name in skip:
                continue
            self.quad(v[p0], v[p1], v[p2], v[p3], material, uv=((0, 0), (uw, 0), (uw, vh), (0, vh)))

    def extend(self, other: "Builder") -> None:
        base = len(self.verts)
        self.verts.extend(other.verts)
        remap = [self.slot(m) for m in other.slots]
        for f, u, mi in zip(other.faces, other.uvs, other.mats):
            self.faces.append(tuple(i + base for i in f))
            self.uvs.append(u)
            self.mats.append(remap[mi])

    @property
    def triangles(self) -> int:
        return sum(len(f) - 2 for f in self.faces)

    def build(self, materials: dict[str, "bpy.types.Material"], collection=None, smooth_angle=None):
        me = bpy.data.meshes.new(self.name)
        me.from_pydata(self.verts, [], self.faces)
        uv = me.uv_layers.new(name="UVMap")
        loop = 0
        for poly_uvs in self.uvs:
            for u in poly_uvs:
                uv.data[loop].uv = u
                loop += 1
        for name in self.slots:
            me.materials.append(materials[name])
        me.polygons.foreach_set("material_index", self.mats)
        me.validate(clean_customdata=False)
        me.update()
        obj = bpy.data.objects.new(self.name, me)
        (collection or bpy.context.scene.collection).objects.link(obj)
        if smooth_angle is not None:
            me.shade_smooth()
            me.set_sharp_from_angle(angle=math.radians(smooth_angle))
        obj["triangles"] = self.triangles
        return obj


def _sub(a, b): return (a[0] - b[0], a[1] - b[1], a[2] - b[2])
def _add(a, b): return (a[0] + b[0], a[1] + b[1], a[2] + b[2])
def _scale(a, k): return (a[0] * k, a[1] * k, a[2] * k)
def _dot(a, b): return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
def _cross(a, b): return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(a):
    n = math.sqrt(_dot(a, a)) or 1e-9
    return (a[0] / n, a[1] / n, a[2] / n)


# ───────────────────────────── materials ─────────────────────────────

def _image(path: pathlib.Path, data: bool):
    img = bpy.data.images.load(str(path), check_existing=True)
    img.colorspace_settings.name = "Non-Color" if data else "sRGB"
    return img


def _gltf_output_group():
    """The node group the glTF exporter reads ambient occlusion from."""
    name = "glTF Material Output"
    if name in bpy.data.node_groups:
        return bpy.data.node_groups[name]
    ng = bpy.data.node_groups.new(name, "ShaderNodeTree")
    ng.interface.new_socket("Occlusion", in_out="INPUT", socket_type="NodeSocketFloat")
    return ng


def material(name: str, *, color=(0.8, 0.8, 0.8, 1.0), albedo: str | None = None,
             normal: str | None = None, orm: str | None = None, roughness: float = 0.6,
             metallic: float = 0.0, emission: str | None = None, emission_color=(0, 0, 0),
             emission_strength: float = 0.0, alpha: float = 1.0, transmission: float = 0.0,
             normal_strength: float = 1.0, double_sided: bool = False):
    """A Principled material built only from inputs glTF and UsdPreviewSurface
    both understand: base colour (texture x factor), normal, ORM packed as
    glTF expects (R occlusion, G roughness, B metallic), emission, alpha."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    uvmap = nt.nodes.new("ShaderNodeUVMap")
    uvmap.uv_map = "UVMap"

    def tex(file: str, data: bool):
        node = nt.nodes.new("ShaderNodeTexImage")
        node.image = _image(TEX / file, data)
        nt.links.new(uvmap.outputs["UV"], node.inputs["Vector"])
        return node

    if albedo:
        t = tex(albedo, False)
        if tuple(color[:3]) != (1.0, 1.0, 1.0) and tuple(color[:3]) != (0.8, 0.8, 0.8):
            mix = nt.nodes.new("ShaderNodeMix")
            mix.data_type = "RGBA"
            mix.blend_type = "MULTIPLY"
            mix.inputs["Factor"].default_value = 1.0
            nt.links.new(t.outputs["Color"], mix.inputs[6])
            mix.inputs[7].default_value = color
            nt.links.new(mix.outputs[2], bsdf.inputs["Base Color"])
        else:
            nt.links.new(t.outputs["Color"], bsdf.inputs["Base Color"])
    if normal:
        t = tex(normal, True)
        nm = nt.nodes.new("ShaderNodeNormalMap")
        nm.inputs["Strength"].default_value = normal_strength
        nt.links.new(t.outputs["Color"], nm.inputs["Color"])
        nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    if orm:
        t = tex(orm, True)
        sep = nt.nodes.new("ShaderNodeSeparateColor")
        nt.links.new(t.outputs["Color"], sep.inputs["Color"])
        nt.links.new(sep.outputs["Green"], bsdf.inputs["Roughness"])
        nt.links.new(sep.outputs["Blue"], bsdf.inputs["Metallic"])
        grp = nt.nodes.new("ShaderNodeGroup")
        grp.node_tree = _gltf_output_group()
        nt.links.new(sep.outputs["Red"], grp.inputs["Occlusion"])
    if emission:
        t = tex(emission, False)
        nt.links.new(t.outputs["Color"], bsdf.inputs["Emission Color"])
        bsdf.inputs["Emission Strength"].default_value = emission_strength or 1.0
    elif emission_strength:
        bsdf.inputs["Emission Color"].default_value = (*emission_color, 1.0)
        bsdf.inputs["Emission Strength"].default_value = emission_strength
    if transmission:
        bsdf.inputs["Transmission Weight"].default_value = transmission
    if alpha < 1.0:
        bsdf.inputs["Alpha"].default_value = alpha
        try:
            mat.surface_render_method = "BLENDED"
        except Exception:
            mat.blend_method = "BLEND"
    mat.use_backface_culling = not double_sided
    return mat


# ───────────────────────────── export ─────────────────────────────

def export(objects, name: str) -> dict:
    """Write modules/<name>.gltf (+ .bin, textures shared in ../textures) and
    modules/<name>.usdc. Returns the manifest entry."""
    MOD.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    for o in objects:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.export_scene.gltf(filepath=str(MOD / f"{name}.gltf"), export_format="GLTF_SEPARATE",
                              export_texture_dir="../textures", use_selection=True, export_yup=True,
                              export_apply=True, export_image_format="AUTO",
                              export_keep_originals=True, export_tangents=False,
                              export_cameras=False, export_lights=False, export_extras=True)
    bpy.ops.wm.usd_export(filepath=str(MOD / f"{name}.usdc"), selected_objects_only=True,
                          export_materials=True, generate_preview_surface=True,
                          export_textures_mode="KEEP", relative_paths=True,
                          convert_orientation=True, export_global_forward_selection="NEGATIVE_Z",
                          export_global_up_selection="Y", meters_per_unit=1.0,
                          triangulate_meshes=False, export_animation=False)
    tris = sum(int(o.get("triangles", 0)) for o in objects)
    mats = sorted({s.material.name for o in objects for s in o.material_slots if s.material})
    return {"name": name, "gltf": f"modules/{name}.gltf", "usd": f"modules/{name}.usdc",
            "objects": [o.name for o in objects], "triangles": tris, "materials": mats}


def write_manifest_part(key: str, entries) -> None:
    path = OUT / "manifest.json"
    data = json.loads(path.read_text()) if path.exists() else {}
    data[key] = entries
    path.write_text(json.dumps(data, indent=1))
