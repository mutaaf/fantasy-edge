"""The crowd kit's cast: 24 fans, decided from a fixed seed.

Nothing here touches bpy, so the cast can be read (and tested) without
Blender. Every choice a fan carries - build, skin, hair, top, what they hold -
comes from one seeded generator plus a coverage pass, so the kit is the same
on every run and no variety axis silently collapses.

Colours are sRGB hex. Anything a club owns is not a colour here but a tint
channel: R is the club's primary chip, G its secondary, B face paint. The
runtime supplies both chips, so one kit dresses every fixture.
"""
from __future__ import annotations

import random

SEED = 20260914
COUNT = 24

# Skin runs light to deep in even steps; every tone appears at least twice.
SKIN = ["#F2C9AC", "#E3B08F", "#CD966F", "#B27A55", "#955F3E", "#784A30", "#5B3825", "#43291C"]
HAIR = {"black": "#1B1714", "dark_brown": "#35261D", "brown": "#634630", "auburn": "#77391F",
        "blonde": "#B7985F", "grey": "#8E8A84", "white": "#D6D2CA"}
PANTS = {"jeans": "#3B4B68", "dark_jeans": "#262F45", "khaki": "#9A896A", "black": "#232427", "grey": "#5D6065"}
SHOES = {"white": "#E4E4E0", "black": "#1D1D1F", "grey": "#85888C"}
NEUTRAL_TOP = {"navy": "#1F2A3E", "black": "#1E1F22", "heather": "#8C8F94", "olive": "#4E5238", "cream": "#D9D2C1"}

# Body archetypes: shoulder width, hip width, bulk (girth), belly, height in metres.
BUILDS = {
    "slim":    dict(sw=0.92, hw=0.95, bulk=0.88, belly=0.95, height=(1.70, 1.84)),
    "average": dict(sw=1.00, hw=1.00, bulk=1.00, belly=1.00, height=(1.66, 1.82)),
    "broad":   dict(sw=1.14, hw=1.02, bulk=1.10, belly=1.04, height=(1.76, 1.92)),
    "heavy":   dict(sw=1.08, hw=1.12, bulk=1.22, belly=1.32, height=(1.68, 1.84)),
    "petite":  dict(sw=0.86, hw=1.04, bulk=0.90, belly=0.96, height=(1.52, 1.64)),
    "teen":    dict(sw=0.84, hw=0.90, bulk=0.84, belly=0.92, height=(1.45, 1.58)),
}

TOPS = ["jersey", "tee", "hoodie", "jacket", "pullover"]
HAIR_STYLES = ["short", "buzz", "long", "ponytail", "curly", "bald"]
HATS = ["none", "cap", "cap_back", "beanie", "visor"]
ACCESSORIES = ["none", "foam_finger", "towel", "sign", "phone"]
PAINT = ["none", "stripes", "half", "cheek"]


def _pick(rng: random.Random, pool, counts, cap):
    """Pick from pool, preferring options that are under their fair share."""
    under = [p for p in pool if counts.get(p, 0) < cap]
    choice = rng.choice(under or pool)
    counts[choice] = counts.get(choice, 0) + 1
    return choice


def cast(seed: int = SEED, count: int = COUNT) -> list[dict]:
    rng = random.Random(seed)
    counts: dict[str, dict] = {k: {} for k in ("build", "skin", "top", "hair", "hat", "acc", "paint")}
    fans = []
    for i in range(count):
        build = _pick(rng, list(BUILDS), counts["build"], count // len(BUILDS) + 1)
        b = BUILDS[build]
        skin = _pick(rng, SKIN, counts["skin"], count // len(SKIN) + 1)
        top = _pick(rng, TOPS, counts["top"], count // len(TOPS) + 2)
        hat = _pick(rng, HATS, counts["hat"], count // len(HATS) + 2)
        hair = _pick(rng, HAIR_STYLES, counts["hair"], count // len(HAIR_STYLES) + 1)
        if hat != "none" and hair in ("long", "curly") and rng.random() < 0.5:
            hair = "short"
        hair_colour = rng.choice(list(HAIR) if build != "teen" else ["black", "dark_brown", "brown", "auburn", "blonde"])
        if hair_colour in ("grey", "white") and build == "teen":
            hair_colour = "brown"
        acc = _pick(rng, ACCESSORIES, counts["acc"], count // len(ACCESSORIES) + 1)
        paint = "none"
        if top in ("jersey", "tee") or rng.random() < 0.25:
            paint = _pick(rng, PAINT, counts["paint"], count // 2)
        # About a quarter of fans wear no club colour on the body at all; a
        # section of nothing but jerseys reads as a uniform, not a crowd.
        club = top in ("jersey", "tee") or (top in ("hoodie", "pullover") and rng.random() < 0.6)
        fans.append({
            "id": f"fan{i:02d}",
            "build": build,
            "height": round(rng.uniform(*b["height"]), 3),
            "sw": round(b["sw"] * rng.uniform(0.96, 1.04), 3),
            "hw": round(b["hw"] * rng.uniform(0.96, 1.04), 3),
            "bulk": round(b["bulk"] * rng.uniform(0.97, 1.03), 3),
            "belly": round(b["belly"] * rng.uniform(0.97, 1.05), 3),
            "skin": skin,
            "hair": hair,
            "hair_colour": HAIR[hair_colour],
            "hat": hat,
            "top": top,
            "club": club,
            "top_neutral": rng.choice(list(NEUTRAL_TOP.values())),
            "sleeve_stripes": top == "jersey" and rng.random() < 0.7,
            "pants": rng.choice(list(PANTS.values())),
            "shoes": rng.choice(list(SHOES.values())),
            "paint": paint,
            "accessory": acc,
            "phase": round(rng.random(), 4),
            # Drawn from its own stream so adding scarves did not reshuffle the cast.
            "scarf": random.Random(seed + 7919 * i).random() < (0.45 if top in ("jacket", "hoodie", "pullover") else 0.2),
        })
    return fans


if __name__ == "__main__":
    import json
    print(json.dumps(cast(), indent=1))
