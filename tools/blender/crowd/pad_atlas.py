"""Grow each figure's colour out into the transparent texels around it.

A far card is a cut-out seen a hundred metres away through small mips. If
the texels around a figure are black, every mip averages the figure with
black and whole stands go dark. The runtime used to pad the dressed atlas
itself, six passes over 6 megapixels per matchup, and in the look-dev
harness's Debug build that was most of a 25-second dress. Padding is not
per matchup, so it happens here, once, and the runtime tints the padded
texels along with the figure (CrowdActor.swift, `CrowdKit.tint`).

Alpha is untouched: only the colour under alpha 0 changes. The mask is
padded the same way, so a padded texel takes its figure's club colour.

    blender --background --python tools/blender/crowd/pad_atlas.py
"""
from __future__ import annotations

import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

# Texels of padding, at each atlas's own size. The albedo's mip 5 is 80x72;
# 24 passes reach it from a figure's edge, and the half-size mask needs half.
ALBEDO_PASSES = 24
MASK_PASSES = 12


def pad(px: np.ndarray, passes: int) -> np.ndarray:
    """px: H x W x 4 float, straight alpha. Returns a copy with colour grown into alpha 0."""
    out = px.copy()
    known = out[..., 3] > 0
    rgb = out[..., :3]
    for _ in range(passes):
        if known.all():
            break
        k = known.astype(np.float32)[..., None]
        s = np.zeros_like(rgb)
        c = np.zeros_like(k)
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            s += np.roll(rgb * k, (dy, dx), axis=(0, 1))
            c += np.roll(k, (dy, dx), axis=(0, 1))
        # np.roll wraps; an atlas edge is a block edge, so a wrapped neighbour is another fan's border - drop it.
        edge = np.zeros(known.shape, dtype=bool)
        edge[0, :] = edge[-1, :] = edge[:, 0] = edge[:, -1] = True
        grow = (~known) & (c[..., 0] > 0) & ~edge
        rgb[grow] = s[grow] / c[grow]
        known = known | grow
    out[..., :3] = rgb
    return out


def pad_file(path: pathlib.Path, passes: int, colorspace: str) -> None:
    import bpy
    img = bpy.data.images.load(str(path), check_existing=False)
    img.colorspace_settings.name = colorspace
    img.alpha_mode = "STRAIGHT"
    W, H = img.size
    px = np.array(img.pixels[:], dtype=np.float32).reshape(H, W, 4)
    padded = pad(px, passes)
    img.pixels.foreach_set(padded.ravel())
    img.filepath_raw = str(path)
    img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img)
    print(f"[crowd] padded {path.name}: {W}x{H}, {passes} passes", flush=True)


def pad_kit(out: pathlib.Path) -> None:
    pad_file(out / "impostor_albedo.png", ALBEDO_PASSES, "sRGB")
    pad_file(out / "impostor_mask.png", MASK_PASSES, "Non-Color")


if __name__ == "__main__":
    import common
    pad_kit(common.OUT)
