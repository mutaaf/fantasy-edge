"""Compile the text-authored Shader Graph materials into the app's assets.

    python3 tools/shadergraph/build.py

`tools/shadergraph/Materials.rkassets/*.usda` are MaterialX node networks
written by hand (see docs/SHADERGRAPH.md). `xcrun realitytool compile` turns
the package into `assets/generated/shadergraph/Materials.reality`, which the
app bundles with the rest of `assets/` and loads with `StadiumShaderGraph`.

realitytool is part of Xcode, not a Python dependency. It compiles silently
and does not validate node ids: an unknown `info:id` compiles and then fails
to load at runtime, so check the app log for `[shadergraph]` after a change.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC = ROOT / "tools" / "shadergraph" / "Materials.rkassets"
OUT = ROOT / "assets" / "generated" / "shadergraph" / "Materials.reality"


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["xcrun", "realitytool", "compile", str(SRC), "--output-reality", str(OUT),
           "--platform", sys.argv[1] if len(sys.argv) > 1 else "xrsimulator", "--deployment-target", "2.0"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not OUT.exists():
        print(r.stdout, r.stderr)
        return r.returncode or 1
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
