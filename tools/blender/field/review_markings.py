"""Review sheet for the marking distance fields: threshold them the way a shader
would, upscaled, over flat turf, and crop the places that go wrong first - a
numeral and its arrow, the hash marks, the goal line and the team area.

    blender -b --factory-startup --python tools/blender/field/review_markings.py -- /tmp/out
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import common  # noqa: E402
import numpy as np  # noqa: E402

args = common.script_args()
out = pathlib.Path(args[0] if args else "/private/tmp/fsrev/markings")
out.mkdir(parents=True, exist_ok=True)

for league in ("nfl", "college-football"):
    meta = __import__("json").loads((common.FIELD_OUT / "markings" / league / "markings.json").read_text())
    c = meta["canvas"]
    sdf = common.read_image(common.FIELD_OUT / "markings" / league / "paint_sdf.png")
    ppy = c["texelsPerYard"]

    def crop(x0, x1, y0, y1, scale):
        # bilinear upsample of the region, then threshold: what a GPU does
        h, w = sdf.shape[:2]
        xs = np.linspace((x0 - c["x0"]) * ppy, (x1 - c["x0"]) * ppy, int((x1 - x0) * ppy * scale)) - 0.5
        ys = np.linspace((c["y1"] - y1) * ppy, (c["y1"] - y0) * ppy, int((y1 - y0) * ppy * scale)) - 0.5
        X, Y = np.meshgrid(xs, ys)
        x0i = np.clip(np.floor(X).astype(int), 0, w - 2); y0i = np.clip(np.floor(Y).astype(int), 0, h - 2)
        fx = (X - x0i)[..., None]; fy = (Y - y0i)[..., None]
        s = (sdf[y0i, x0i] * (1 - fx) * (1 - fy) + sdf[y0i, x0i + 1] * fx * (1 - fy)
             + sdf[y0i + 1, x0i] * (1 - fx) * fy + sdf[y0i + 1, x0i + 1] * fx * fy)
        texel = 1.0 / (2 * meta["sdf"]["rangeInches"] / 36 * ppy * scale)
        white = np.clip((s[..., 0] - 0.5) / texel + 0.5, 0, 1)[..., None]
        yellow = np.clip((s[..., 1] - 0.5) / texel + 0.5, 0, 1)[..., None]
        turf = np.array([0.08, 0.22, 0.07])
        img = turf * (1 - white) + np.array([0.95, 0.95, 0.93]) * white
        img = img * (1 - yellow) + np.array([0.95, 0.80, 0.10]) * yellow
        return img

    common.write_png(out / f"{league}_numeral_20.png", crop(14, 27, -3, 16, 12))
    common.write_png(out / f"{league}_goal_left.png", crop(-14, 8, -6, 18, 8))
    common.write_png(out / f"{league}_team_area.png", crop(16, 40, -15, 3, 8))
    common.write_png(out / f"{league}_overview.png", crop(-16, 116, -14, 160 / 3 + 14, 1))
    print("REVIEW", league)
