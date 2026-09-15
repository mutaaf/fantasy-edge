"""Build the bowl kit. Run inside Blender:

    blender --background --factory-startup --python tools/blender/bowl/build.py -- [steps...]

Steps: contracts textures seat structure architecture review (default: all
but review). Each writes into assets/actors/bowl/ and records itself in
manifest.json. Deterministic: same repo, same bytes (renders aside).
"""
from __future__ import annotations

import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import kit  # noqa: E402

ALL = ["contracts", "textures", "seat", "structure", "architecture"]


def main(argv: list[str]) -> None:
    steps = argv or ALL
    for step in steps:
        t0 = time.time()
        if step == "contracts":
            kit.main()
        elif step == "textures":
            import textures
            import common
            common.reset()
            credits = textures.build()
            common.write_manifest_part("sources", credits)
        elif step == "seat":
            import seat
            seat.build()
        elif step == "structure":
            import structure
            structure.build()
        elif step == "architecture":
            import architecture
            architecture.build()
        elif step == "review":
            import review
            review.build(argv[argv.index("review") + 1:] if len(argv) > argv.index("review") + 1 else [])
            break
        else:
            raise SystemExit(f"unknown step {step}")
        print(f"[bowl] {step} done in {time.time() - t0:.1f}s", flush=True)


if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    main(args)
