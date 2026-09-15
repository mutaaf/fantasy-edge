"""Expose a scene-linear EXR or HDR to an 8-bit PNG for review.

    blender --background --factory-startup --python tools/blender/lighting/preview.py -- IN OUT [EV]

A filmic-ish shoulder (Reinhard on luminance, white point 16) so a probe's
lamps read as light rather than clipping flat. Review only.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import common as C  # noqa: E402
import numpy as np  # noqa: E402

a = C.args()
src, dst = pathlib.Path(a[0]), pathlib.Path(a[1])
ev = float(a[2]) if len(a) > 2 else 0.0
img = C.load_float(src) * (2.0 ** ev)
lum = img[..., 0] * 0.2126 + img[..., 1] * 0.7152 + img[..., 2] * 0.0722
white = 16.0
mapped = lum * (1 + lum / white ** 2) / (1 + lum)
img = img * (mapped / np.maximum(lum, 1e-8))[..., None]
rgba = np.concatenate([np.clip(img, 0, 1), np.ones(img.shape[:2] + (1,))], axis=2)
C.save_png(dst, rgba, srgb_encode=True)
print(f"[lighting] preview {dst}")
