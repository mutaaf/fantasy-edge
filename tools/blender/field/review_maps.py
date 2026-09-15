"""Split the field maps into one grey image per channel for review.

    blender -b --factory-startup --python tools/blender/field/review_maps.py -- /tmp/out
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import common  # noqa: E402
import numpy as np  # noqa: E402

args = common.script_args()
out = pathlib.Path(args[0] if args else "/private/tmp/fsrev/maps")
out.mkdir(parents=True, exist_ok=True)
for league in ("nfl", "college-football"):
    for name, labels in (("field_maps", ("macro", "wear", "crisp", "divot")),
                         ("mow_patterns", ("five", "ten", "checker", "diamond"))):
        img = common.read_image(common.FIELD_OUT / "maps" / league / f"{name}.png")
        for k, lab in enumerate(labels):
            common.write_png(out / f"{league}_{name}_{lab}.png", img[..., k])
print("SPLIT")
