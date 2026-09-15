"""Write assets/actors/field/manifest.json: every shipped file, what it is, and
what it costs on the GPU.

GPU cost is uncompressed with a full mip chain (x 4/3), the honest ceiling; a
renderer that compresses to ASTC 6x6 pays about a ninth of it. Stdlib only.

    python3 tools/blender/field/manifest.py
"""
from __future__ import annotations

import json
import pathlib
import struct
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import rules  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[3]
FIELD = ROOT / "assets" / "actors" / "field"

CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}

ROLES = {
    "turf/natural/turf_natural_with_albedo.png": "natural turf albedo (sRGB), tile 0.40 m",
    "turf/natural/turf_natural_with_normal.png": "natural turf normal, blades leaning with the mower (OpenGL)",
    "turf/natural/turf_natural_against_normal.png": "natural turf normal, blades leaning against the mower",
    "turf/natural/turf_natural_with_orm.png": "natural turf R occlusion G roughness B height",
    "turf/natural/turf_worn_any_albedo.png": "worn turf albedo, blended in by maps.G",
    "turf/natural/turf_worn_any_normal.png": "worn turf normal",
    "turf/natural/turf_worn_any_orm.png": "worn turf ORM",
    "turf/natural/paint_breakup.png": "paint carried per turf texel; perturbs the paint SDF edge",
    "turf/synthetic/turf_synthetic_any_albedo.png": "synthetic turf albedo with crumb-rubber infill",
    "turf/synthetic/turf_synthetic_any_normal.png": "synthetic turf normal",
    "turf/synthetic/turf_synthetic_any_orm.png": "synthetic turf ORM",
    "turf/synthetic/paint_breakup.png": "paint carried per synthetic texel",
    "maps/divots.png": "divot decal atlas 2x2, straight alpha",
    "maps/divots_normal.png": "divot decal normals",
    "fonts/glyphs.json": "Graduate glyph triangles for runtime team lettering",
}


def png_size(path: pathlib.Path):
    with path.open("rb") as f:
        head = f.read(26)
    w, h, bits, colour = struct.unpack(">IIBB", head[16:26])
    return w, h, CHANNELS.get(colour, 4) * max(1, bits // 8)


def entry(path: pathlib.Path) -> dict:
    rel = path.relative_to(FIELD).as_posix()
    rec = {"path": rel, "bytes": path.stat().st_size}
    if path.suffix == ".png":
        w, h, bpp = png_size(path)
        rec.update({"width": w, "height": h, "bytesPerTexel": bpp,
                    "gpuMB": round(w * h * bpp * 4 / 3 / 1e6, 2)})
    role = ROLES.get(rel)
    if role is None:
        if "/shell_" in rel or "_shell_" in rel:
            role = "shell coverage slice for field-level grass (shell_0 tallest)"
        elif rel.endswith("paint_sdf.png"):
            role = "painted markings, signed distance: R white G yellow, 0.5 = edge"
        elif rel.endswith("markings.json"):
            role = "every marking as polygons in field yards with its rule"
        elif rel.endswith("field_maps.png"):
            role = "R macro variation G wear B mow crispness A divot density"
        elif rel.endswith("mow_patterns.png"):
            role = "mowing patterns: R 5 yd G 10 yd B checker A diamond"
        elif rel.endswith("bake.json"):
            role = "bake parameters"
        elif rel.endswith(".ttf") or rel.startswith("fonts/OFL"):
            role = "font source and licence"
    rec["role"] = role or ""
    return rec


def main():
    files = sorted(p for p in FIELD.rglob("*") if p.is_file() and p.name != "manifest.json" and p.name != "README.md"
                   and not p.name.startswith("."))
    entries = [entry(p) for p in files]
    headset = {"turf/natural/turf_natural_with_albedo.png", "turf/natural/turf_natural_with_normal.png",
               "turf/natural/turf_natural_against_normal.png", "turf/natural/turf_natural_with_roughness.png",
               "markings/nfl/paint_white_half.png", "markings/nfl/paint_yellow_half.png",
               "maps/nfl/variation_opacity.png"}
    loaded = {  # what the visionOS field binds (design/tokens.json visual.field)
        "headset": [e for e in entries if e["path"] in headset],
        # the fuller set a shader-capable client (web, Android) may bind instead
        "fullShaderPath": [e for e in entries if e["path"].startswith(("turf/natural/", "markings/nfl/paint_sdf",
                                                                        "maps/nfl/field_maps", "maps/nfl/mow", "maps/divots"))
                           and "shell" not in e["path"]],
    }
    budget = {k: round(sum(e.get("gpuMB", 0) for e in v), 2) for k, v in loaded.items()}
    # RGBA with a full mip chain, the way StadiumAssets counts it
    budget["headsetAsLoaded"] = round(sum(e["width"] * e["height"] * 16 / 3 / 1e6 for e in loaded["headset"]), 2)
    manifest = {
        "actor": "field",
        "units": {"textures": "0.40 m turf tile; field-space maps in yards over the markings canvas"},
        "canvas": {"x0": -16.0, "x1": 116.0, "y0": -(81.375 - 160 / 3) / 2, "y1": 160 / 3 + (81.375 - 160 / 3) / 2,
                   "axes": "x yards from the left goal line, y yards from the near sideline, top row = far edge"},
        "leagues": list(rules.LEAGUES),
        "gpuBudgetMB": {"field": 40, "measuredUncompressed": budget},
        "discrepanciesWithScene": rules.DISCREPANCIES,
        "files": entries,
    }
    (FIELD / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps(budget))


if __name__ == "__main__":
    main()
