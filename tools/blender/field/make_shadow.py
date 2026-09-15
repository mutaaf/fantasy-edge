"""Write the sideline's stand-in prop shadow decal, in Lighting's format.

Lighting owns the real one (`visual.lighting.response.propShadowDecal`,
docs/actors/lighting-sky.md): 512 px, black RGB, alpha the shadow, four soft
lobes at 35/145/215/325 degrees, one per bank quadrant, plus a contact core,
alpha capped at 0.7. Until that branch merges, Sideline points at this file,
made to the same contract so the switch is a path change.

Grey single channel (the alpha), sRGB-encoded so a colour-decoding loader
reads back the linear value. u runs along +x, v along -z; lobe 0 points to
+x, -z.

    blender -b --factory-startup --python tools/blender/field/make_shadow.py
"""
from __future__ import annotations

import math
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import common  # noqa: E402
import numpy as np  # noqa: E402

N = 512
y, x = (np.mgrid[0:N, 0:N] + 0.5) / N * 2 - 1          # x: +u, y: rows top-down
v = -y                                                  # v up
r = np.hypot(x, v)
alpha = 0.7 * np.exp(-(r / 0.16) ** 2)                  # contact core
for deg in (35, 145, 215, 325):
    a = math.radians(deg)
    ux, uv = math.cos(a), math.sin(a)
    along = x * ux + v * uv
    across = -x * uv + v * ux
    lobe = np.exp(-((along - 0.42) / 0.36) ** 2 - (across / 0.17) ** 2) * (along > -0.05)
    alpha = np.maximum(alpha, 0.34 * lobe)
alpha *= np.clip((1 - r) / 0.12, 0, 1)                  # zero at the rim
alpha = np.clip(alpha, 0, 0.7)
srgb = np.where(alpha <= 0.0031308, alpha * 12.92, 1.055 * np.power(alpha, 1 / 2.4) - 0.055)
common.write_png(common.SIDELINE_OUT / "textures" / "shadow_props.png", srgb)
print("SHADOW", float(alpha.max()))
