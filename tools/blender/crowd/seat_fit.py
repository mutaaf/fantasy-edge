"""Measure every seated fan, placed as the app places them, against Bowl's chair.

Takes each fan's frozen LOD0 sit pose from the kit (glTF), applies
visual.crowd.chair exactly as CrowdActor does, and reports the gap between
the lowest point under the hips and Bowl's pan (tools/blender/bowl/seat.py:
pan at 0.43-0.455 m over z -0.17..0.22, back at z -0.22, feet origin, +z
front), plus how far the feet are off the tread.

    blender --background --python tools/blender/crowd/seat_fit.py
"""
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))

import bpy
from mathutils import Vector

import common

PAN = 0.442          # mid-pan height, metres


def main():
    common.reset()
    C = json.loads((ROOT / "design/tokens.json").read_text())["visual"]["crowd"]
    ch = C["chair"]
    manifest = json.loads((ROOT / "assets/actors/crowd/manifest.json").read_text())
    heights = {f["id"]: f["height"] for f in manifest["fans"]}
    bpy.ops.import_scene.gltf(filepath=str(ROOT / "assets/actors/crowd/lod0_poses.glb"))
    rows = []
    for fid in sorted(heights):
        ob = bpy.data.objects.get(f"{fid}_lod0_sit")
        if ob is None:
            continue
        k = heights[fid] / ch["referenceHeightMetres"]
        lift = ch["pelvisMetres"] - ch["kitPelvisMetres"] * k
        fwd = ch["sitForwardMetres"]
        wm = ob.matrix_world
        # Imported glTF: Blender Z up, the fan's front is -Y. App frame: up, and +forward.
        pts = [(p.x, -p.y + fwd, p.z + lift) for p in (wm @ v.co for v in ob.data.vertices)]
        # Under the hips only: behind the knees and above the shins.
        seat = [p for p in pts if abs(p[0]) < 0.14 and -0.26 < p[1] < 0.05 and 0.25 < p[2] < 0.75]
        low = min(p[2] for p in seat) if seat else float("nan")
        feet = min(p[2] for p in pts)
        front = max(p[1] for p in pts if p[2] < 0.12)
        rows.append((fid, heights[fid], low - PAN, feet, front))
    print("fan height  seat-gap(m)  feet(m)  toe-forward(m)")
    for fid, h, gap, feet, front in rows:
        print(f"{fid} {h:.2f}  {gap:+.3f}  {feet:+.3f}  {front:+.3f}")
    gaps = [r[2] for r in rows]
    print(f"seat gap range {min(gaps):+.3f} .. {max(gaps):+.3f}, mean {sum(gaps)/len(gaps):+.3f}")
    feet = [r[3] for r in rows]
    print(f"feet range {min(feet):+.3f} .. {max(feet):+.3f}")


main()
