"""A contact sheet for the sprites and skies, the way they will actually be seen:
additive white cards over a night-dark ground, and skies exposed for display.

    blender --background --factory-startup --python tools/blender/lighting/contact.py -- OUT.png

Review only; writes nothing under assets/.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import common as C  # noqa: E402
import numpy as np  # noqa: E402


def load_png(path):
    import bpy
    img = bpy.data.images.load(str(path))
    img.colorspace_settings.name = "Non-Color"
    w, h = img.size
    px = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    return np.flipud(px.reshape(h, w, 4))


def fit(a, w, h):
    ys = (np.arange(h) * a.shape[0] / h).astype(int)
    xs = (np.arange(w) * a.shape[1] / w).astype(int)
    return a[ys][:, xs]


def main():
    out = pathlib.Path(C.args()[0] if C.args() else C.SCRATCH / "contact.png")
    W, H = 1800, 1250
    sheet = np.zeros((H, W, 3))
    sheet[:] = (0.02, 0.022, 0.03)
    tex = C.OUT_LIGHT / "textures"
    tiles = [("glow_core.png", 1.0), ("glow_halo.png", 1.0), ("bloom_card.png", 1.0), ("beam_quad.png", 1.0),
             ("beam_cone.png", 1.0), ("haze_layer.png", 0.5), ("moth_atlas.png", 1.0), ("shadow_multi.png", -1.0)]
    cell = 300
    for i, (name, mode) in enumerate(tiles):
        a = load_png(tex / name)
        aspect = a.shape[1] / a.shape[0]
        w = cell if aspect >= 1 else int(cell * aspect)
        h = int(w / aspect)
        x0, y0 = 20 + (i % 4) * (cell + 140), 20 + (i // 4) * (cell + 40)
        f = fit(a, w, h)
        region = sheet[y0:y0 + h, x0:x0 + w]
        if mode < 0:
            region[:] = (0.25, 0.45, 0.2)
            region[:] = region * (1 - f[..., 3:4])
        else:
            region[:] = region + f[..., :3] * f[..., 3:4] * mode * np.array([1.0, 0.97, 0.9])
    sky_dir = C.OUT_SKY / "textures"
    for j, name in enumerate(("sky_night.png", "sky_dusk.png")):
        a = load_png(sky_dir / name)
        f = fit(a, 860, 280)
        x0 = 20 + j * 900
        sheet[700:980, x0:x0 + 860] = f[..., :3] ** 2.2
    a = load_png(tex / "ao_riser.png")
    sheet[1000:1240, 20:80] = fit(a, 60, 240)[..., :3] ** 2.2
    rgba = np.concatenate([np.clip(sheet, 0, 1), np.ones((H, W, 1))], axis=2)
    C.save_png(out, rgba, srgb_encode=True)
    print(f"[lighting] contact sheet {out}")


main()
