"""Compile the Field and Sideline Shader Graph packages.

    python3 tools/blender/field/shadergraph/build.py [xrsimulator|xros]

Each `<Actor>.rkassets` here holds one material, so `StadiumShaderGraph`,
which reads the first ShaderGraphMaterial off a compiled file, finds the
right one (docs/SHADERGRAPH.md). Outputs:

  assets/actors/field/shadergraph/Field.reality         FieldPaint
  assets/actors/sideline/shadergraph/Sideline.reality   NetFresnel
  assets/actors/field/shadergraph/Shells.reality        FieldShells
  assets/actors/field/shadergraph/Turf.reality          TurfSheen

realitytool does not validate node ids; grep the app log for [shadergraph]
and shoot after any change.
"""
from __future__ import annotations

import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[3]
PACKAGES = {"Field": ROOT / "assets/actors/field/shadergraph/Field.reality",
            "Sideline": ROOT / "assets/actors/sideline/shadergraph/Sideline.reality",
            "Shells": ROOT / "assets/actors/field/shadergraph/Shells.reality",
            "Turf": ROOT / "assets/actors/field/shadergraph/Turf.reality"}


def main() -> int:
    platform = sys.argv[1] if len(sys.argv) > 1 else "xrsimulator"
    for name, out in PACKAGES.items():
        out.parent.mkdir(parents=True, exist_ok=True)
        r = subprocess.run(["xcrun", "realitytool", "compile", str(HERE / f"{name}.rkassets"),
                            "--output-reality", str(out), "--platform", platform, "--deployment-target", "2.0"],
                           capture_output=True, text=True)
        if r.returncode != 0 or not out.exists():
            print(r.stdout, r.stderr)
            return r.returncode or 1
        print(f"wrote {out.relative_to(ROOT)} ({out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
