"""Lay out end-zone lettering and midfield art from team names, in field yards.

Stdlib only, so this can move into fantasyedge/scene.py as it stands: every
renderer then receives the same triangles and tints them with the scene's chip
colours, rather than each client typesetting names its own way.

Coordinates: x is yards from the left goal line (end zones run -10..0 and
100..110), y is yards from the near sideline (0..53.33). Glyphs come from
assets/actors/field/fonts/glyphs.json, which make_markings.py extracts from
Graduate (SIL OFL 1.1) as triangles with cap height 1.

The only rule the lettering must obey is clearance: NCAA 1-2-1-d keeps
decorative end-zone markings at least four feet from any line, and 1-2-1-g-3
keeps midfield art off the hash marks and numbers. The NFL leaves both to the
Commissioner; the same clearances are used for it, which never breaks a rule.
"""
from __future__ import annotations

import json
import math
import pathlib

FONT = pathlib.Path(__file__).resolve().parents[3] / "assets" / "actors" / "field" / "fonts" / "glyphs.json"
FT = 1 / 3


def load_font(path: pathlib.Path = FONT) -> dict:
    return json.loads(path.read_text())


def _typeset(text: str, font: dict, tracking: float = 0.08):
    """Triangles for a line of text in em units (cap height 1), and its width."""
    tris, pen = [], 0.0
    for ch in text.upper():
        g = font["glyphs"].get(ch) or font["glyphs"].get("?")
        if ch == " ":
            pen += font["space"]
            continue
        for t in g["triangles"]:
            tris.append([(pen + x - g["minX"], y) for x, y in t])
        pen += g["width"] + tracking
    return tris, max(0.0, pen - tracking)


def _place(tris, origin, u, v, scale):
    ox, oy = origin
    return [[(ox + (x * u[0] + y * v[0]) * scale, oy + (x * u[1] + y * v[1]) * scale) for x, y in t]
            for t in tris]


def end_zone_regions(league_paint: dict, width: float = 160 / 3) -> list[dict]:
    """The paintable box of each end zone after the four-foot clearance.

    The goal line's full width sits in the end zone, so the clearance is taken
    from its end-zone edge, not from the goal line itself.
    """
    clear = 4 * FT
    gl = league_paint["goalLine"]
    return [
        {"end": "left", "x0": -10 + clear, "x1": -gl - clear, "y0": clear, "y1": width - clear, "up": (-1.0, 0.0)},
        {"end": "right", "x0": 100 + gl + clear, "x1": 110 - clear, "y0": clear, "y1": width - clear, "up": (1.0, 0.0)},
    ]


def end_zone_text(name: str, league_paint: dict, end: str, font: dict | None = None,
                  height: float | None = None) -> dict:
    """A team name set across one end zone, letter tops toward the end line.

    Sized to the largest cap height that fits both the depth and the width,
    capped at 5 yd so a short name does not become a wall of paint.
    """
    font = font or load_font()
    region = next(r for r in end_zone_regions(league_paint) if r["end"] == end)
    depth = region["x1"] - region["x0"]
    span = region["y1"] - region["y0"]
    tris, w = _typeset(name, font)
    cap = height or min(5.0, depth * 0.78, span * 0.92 / max(w, 1e-6))
    # Letter "up" points to the end line; reading left-to-right runs along y
    # so the text reads from the field of play looking into the end zone.
    if end == "left":
        u, v = (0.0, -1.0), (-1.0, 0.0)
        cx = (region["x0"] + region["x1"]) / 2
        origin = (cx + cap / 2, (region["y0"] + region["y1"]) / 2 + w * cap / 2)
    else:
        u, v = (0.0, 1.0), (1.0, 0.0)
        cx = (region["x0"] + region["x1"]) / 2
        origin = (cx - cap / 2, (region["y0"] + region["y1"]) / 2 - w * cap / 2)
    return {"kind": "endZoneText", "end": end, "text": name.upper(), "capHeight": round(cap, 4),
            "tint": "team.primary", "triangles": _place(tris, origin, u, v, cap)}


def midfield_region(league: str, league_paint: dict, hash_from_sideline: float, width: float = 160 / 3) -> dict:
    """Where midfield art may go. College keeps it between the hash marks;
    the NFL allows over them, so its box runs from number top to number top."""
    margin = 1 * FT
    if league == "college-football":
        y0 = hash_from_sideline + margin
        return {"x0": 42.0, "x1": 58.0, "y0": y0, "y1": width - y0, "mayCoverHashes": False, "shadowLines": True}
    nums = league_paint["numbers"]
    top = nums["bottomFromSideline"] + nums["height"] if "bottomFromSideline" in nums else nums["topFromSideline"]
    return {"x0": 41.0, "x1": 59.0, "y0": top + 1.0, "y1": width - top - 1.0, "mayCoverHashes": True, "shadowLines": True}


def midfield_art(name: str, league: str, league_paint: dict, hash_from_sideline: float,
                 font: dict | None = None, segments: int = 96) -> dict:
    """A ring and the team's name inside it, centred on the 50.

    Generic on purpose: no club marks. The ring is two tints (team.primary
    outer, team.secondary inner) and the name reads from the near sideline.
    """
    font = font or load_font()
    box = midfield_region(league, league_paint, hash_from_sideline)
    cx, cy = (box["x0"] + box["x1"]) / 2, (box["y0"] + box["y1"]) / 2
    r_out = min(box["x1"] - box["x0"], box["y1"] - box["y0"]) / 2
    r_in = r_out * 0.86
    ring = []
    for i in range(segments):
        a0, a1 = 2 * math.pi * i / segments, 2 * math.pi * (i + 1) / segments
        p0o = (cx + r_out * math.cos(a0), cy + r_out * math.sin(a0))
        p1o = (cx + r_out * math.cos(a1), cy + r_out * math.sin(a1))
        p0i = (cx + r_in * math.cos(a0), cy + r_in * math.sin(a0))
        p1i = (cx + r_in * math.cos(a1), cy + r_in * math.sin(a1))
        ring += [[p0o, p1o, p1i], [p0o, p1i, p0i]]
    disc = [[(cx, cy), (cx + r_in * math.cos(2 * math.pi * i / segments), cy + r_in * math.sin(2 * math.pi * i / segments)),
             (cx + r_in * math.cos(2 * math.pi * (i + 1) / segments), cy + r_in * math.sin(2 * math.pi * (i + 1) / segments))]
            for i in range(segments)]
    tris, w = _typeset(name, font)
    cap = min(r_in * 0.55, (2 * r_in * 0.80) / max(w, 1e-6))
    text = _place(tris, (cx - w * cap / 2, cy - cap / 2), (1.0, 0.0), (0.0, 1.0), cap)
    return {"kind": "midfieldArt", "region": box, "capHeight": round(cap, 4),
            "layers": [{"tint": "team.secondary", "opacity": 0.55, "triangles": disc},
                       {"tint": "team.primary", "triangles": ring},
                       {"tint": "paint.white", "triangles": text}]}
