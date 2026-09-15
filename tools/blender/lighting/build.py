"""Build every lighting and sky asset, in order, and write the manifest.

    blender --background --python tools/blender/lighting/build.py [-- --quick] [-- --skip-probes]

  1. orient.py      prove the equirect convention; stop on a mismatch
  2. textures.py    sprites, decals, sky, light dome
  3. rigs.py        light banks (hero / near / far) and beams, .usdz + .glb
  4. ibl.py         night, dusk and tabletop probes with irradiance, specular, SH
  5. manifest.json  every file with its size, the budget, the SH, the tokens

Each stage runs in its own Blender process, so one stage's scene never leaks
into the next. Also checks that the bowl numbers common.py mirrors still match
fantasyedge/scene.py.
"""
from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys

import bpy

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUT_LIGHT = ROOT / "assets" / "actors" / "lighting"
OUT_SKY = ROOT / "assets" / "actors" / "sky"
SCRATCH = ROOT / ".work" / "lighting"


def run(script, *args):
    cmd = [bpy.app.binary_path, "--background", "--factory-startup", "--python", str(HERE / script), "--", *args]
    p = subprocess.run(cmd, capture_output=True, text=True)
    lines = [ln for ln in p.stdout.splitlines() if ln.startswith("[lighting]")]
    for ln in lines:
        print(ln)
    if p.returncode != 0 or any("FAILED" in ln for ln in lines) or "Traceback" in p.stderr + p.stdout:
        print(p.stdout[-3000:], p.stderr[-3000:])
        raise SystemExit(f"[lighting] {script} failed")
    return lines


def check_scene_mirror():
    src = (ROOT / "fantasyedge" / "scene.py").read_text()
    sys.path.insert(0, str(HERE))
    import common as C
    for tier in C.TIERS:
        pattern = r'"name": "%s", "inner": ([\d.]+), "outer": ([\d.]+), "rise": \[([\d.]+), ([\d.]+)\]' % tier["name"]
        m = re.search(pattern, src)
        if not m:
            raise SystemExit(f"[lighting] scene.py no longer states the {tier['name']} tier the way common.py reads it")
        got = tuple(float(x) for x in m.groups())
        want = (tier["inner"], tier["outer"], *tier["rise"])
        if got != want:
            raise SystemExit(f"[lighting] common.py mirrors {tier['name']} as {want}, scene.py says {got}")
    m = re.search(r'"rimLights": \{"count": (\d+), "beyondOuter": ([\d.]+)', src)
    if not m or (int(m.group(1)), float(m.group(2))) != (C.RIM["count"], C.RIM["beyondOuter"]):
        raise SystemExit("[lighting] common.py RIM no longer matches scene.py rimLights")
    print("[lighting] common.py mirrors scene.py's bowl")


def manifest():
    files = []
    for base in (OUT_LIGHT, OUT_SKY):
        for f in sorted(base.rglob("*")):
            if f.is_file() and f.name not in ("manifest.json",):
                files.append({"path": str(f.relative_to(ROOT / "assets")), "bytes": f.stat().st_size})
    stats = {}
    for f in sorted(SCRATCH.glob("ibl_*.json")):
        d = json.loads(f.read_text())
        stats[d["id"]] = d
    rigs = json.loads((SCRATCH / "rig_stats.json").read_text()) if (SCRATCH / "rig_stats.json").exists() else {}
    data = {
        "about": "Lighting and sky assets for every client. Models are metres, Y-up, face +Z; see README.md.",
        "units": "metres for models; scene yards divide by 0.9144",
        "equirect": "top row zenith, centre column -Z (the far side), +X a quarter turn right; verified by orient.py",
        "triangles": rigs,
        "probes": {k: {kk: v[kk] for kk in ("exposureScale", "belowHorizonMean", "referenceBelowMean", "peak", "clamp", "sh9", "renderWidth", "samples")}
                   for k, v in stats.items()},
        "budget": {
            "lighting": {"triangles": 10000, "drawParts": 20, "textureMB": 20, "spotLights": 4, "shadowCasters": 1},
            "sky": {"triangles": 5000, "drawParts": 3, "textureMB": 30},
            "additiveOverdrawCapScreens": 2.0,
        },
        "files": files,
    }
    path = OUT_LIGHT / "manifest.json"
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    print(f"[lighting] manifest {path.relative_to(ROOT)}: {len(files)} files")


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    quick = "--quick" in argv
    check_scene_mirror()
    run("orient.py")
    run("textures.py")
    run("rigs.py")
    if "--skip-probes" not in argv:
        run("ibl.py", *(["--quick"] if quick else []))
    manifest()


main()
