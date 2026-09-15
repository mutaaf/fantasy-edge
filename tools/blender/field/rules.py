"""Field-marking rules per league, layered over the scene's RULES table.

The scene (fantasyedge/scene.py) owns what the renderers already use: field
size, hash distance, goal-post width and the team area. This module reads
those and adds the paint the scene does not carry yet, each value quoted from
the rulebook it came from, so the masks can be checked against a source rather
than against memory.

Sources, both fetched 2026-09-14:
  NFL  - 2026 Official Playing Rules, Rule 1 and the field diagram notes.
  NCAA - 2026 NCAA Football Rules and Interpretations, Rule 1-2 (FR-19..21).

Where the scene and the rulebook disagree, the rulebook value is used here and
the disagreement is listed in DISCREPANCIES, so Phase B can correct the scene
rather than paint around it.

Stdlib only: this also runs outside Blender (manifest checks, tests).
"""
from __future__ import annotations

import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fantasyedge.scene import RULES  # noqa: E402

FT = 1 / 3          # yards per foot
IN = 1 / 36         # yards per inch

# Everything in yards. "Sideline distance" is measured from the inside edge of
# the sideline, the convention both books use.
PAINT = {
    "nfl": {
        "source": "NFL 2026 Rule 1 §1-2, §2 Art.1-4, §3; field diagram notes 1-10",
        "line": 4 * IN,                         # notes 2: all lines 4 in
        "goalLine": 8 * IN,                     # §2 Art.3: each goal line 8 in
        "boundary": {"kind": "border", "width": 6 * FT},   # §1 Art.2: solid white border 6 ft
        "yardLineStopShort": 8 * IN,            # §2 Art.1: stop 8 in short of the border
        "yardLineIntoBorder": 4 * IN,           # §2 Art.1: extended 4 in beyond the border (outer)
        "hash": {"fromSideline": 70.75 * FT, "length": 2 * FT, "width": 4 * IN,
                 "measuredTo": "inbound edge"},  # notes 10
        "sideTicks": {"fromBorder": 8 * IN, "length": 2 * FT},  # §2 Art.2 Item 2
        "numbers": {"bottomFromSideline": 12.0, "height": 2.0, "width": 4 * FT,
                    "rule": "bottoms 12 yd in from each sideline, 2 yd long"},  # §2 Art.4 Item 1
        "arrows": {"longSide": 36 * IN, "base": 18 * IN, "belowTop": 15 * IN,
                   "fromNumberEdge": 6 * IN},    # notes 9
        "tryMark": {"distance": 2.0, "length": 1.0},   # §2 Art.4 Item 2: 1 yd line, 2 yd out
        "limitLine": {"style": "broken", "color": "yellow", "width": 8 * IN,
                      "dash": 2 * FT, "gap": 1 * FT,
                      "beyondBorderNonBench": (9 + 4 / 12) * FT,
                      "beyondBorderEndZone": 6 * FT},       # notes 1
        "coachesLine": {"style": "solid", "color": "yellow", "width": 8 * IN,
                        "behindBorder": 6 * FT},            # notes 1
        "benchArea": {"fromYard": 30.0, "toYard": 70.0, "angleFromYard": 25.0,
                      "benchesBack": (30 + 4 / 12) * FT},   # notes 1, 7, 8
        "pylons": {"size": 4 * IN, "height": 18 * IN,
                   "at": ["goal line x sideline", "end line x hash extended"]},  # §2 Art.3
        "goal": {"crossbar": 10 * FT, "width": 18.5 * FT, "uprightAbove": 35 * FT,
                 "uprightDiameter": 4 * IN, "style": "slingshot", "color": "gold",
                 "ribbon": {"width": 4 * IN, "length": 42 * IN, "color": "orange"},
                 "offsetFromEndLine": "in plane of end line; standard offset behind"},  # §3
        "chains": {"rodHeightMin": 5 * FT, "side": "visitors", "offsetFromSideline": 6 * FT},
    },
    "college-football": {
        "source": "NCAA 2026 Rule 1-2-1 .. 1-2-7 (FR-19..21)",
        "line": 4 * IN,                         # 1-2-1-a
        "goalLine": 8 * IN,                     # 1-2-1-a: 4 or 8 in; 8 chosen, stated
        "boundary": {"kind": "line", "width": 4 * IN,
                     "note": "sidelines may exceed 4 in; solid white area to the coaching line is mandatory (1-2-1-c)"},
        "yardLineStopShort": 4 * IN,            # 1-2-1-b: yard lines four inches from the sidelines
        "yardLineIntoBorder": 0.0,
        "hash": {"fromSideline": 60 * FT, "length": 24 * IN, "width": 4 * IN},  # 1-2-1-j
        "sideTicks": {"fromBorder": 4 * IN, "length": 24 * IN},  # 1-2-1-b
        "numbers": {"topFromSideline": 9.0, "height": 6 * FT, "width": 4 * FT,
                    "rule": "not larger than 6x4 ft, tops 9 yd from the sidelines (recommended)"},  # 1-2-1-h
        "arrows": {"longSide": 36 * IN, "base": 18 * IN, "belowTop": 15 * IN,
                   "fromNumberEdge": 6 * IN},    # 1-2-1-i; placement borrowed from NFL note 9
        "nineYardMarks": {"length": 12 * IN, "every": 10, "requiredIfNoNumbers": True},  # 1-2-1-k
        "tryMark": {"distance": 3.0, "length": 1.0,
                    "note": "not required by rule; the try snaps from the 3 (FR-8-3) and most fields mark it"},
        "limitLine": {"style": "broken", "color": "yellow", "width": 4 * IN,
                      "dash": 12 * IN, "gap": 24 * IN, "beyondSideline": 12 * FT},  # 1-2-3-a
        "coachesLine": {"style": "solid", "color": "white", "width": 4 * IN,
                        "beyondSideline": 6 * FT, "fromYard": 20.0, "toYard": 80.0,
                        "coachingBox": "white diagonal lines between coaching and limit lines"},  # 1-2-4-a
        "fiveYardRefMarks": {"size": 4 * IN, "on": "coaching line extended, each 5-yd line"},  # 1-2-4-a
        "benchArea": {"fromYard": 20.0, "toYard": 80.0},   # 1-2-4-a: between the 20-yard lines
        "pylons": {"size": 4 * IN, "height": 18 * IN, "gapUnder": 2 * IN,
                   "endLineHashOffset": 3 * FT,
                   "at": ["goal line x sideline", "end line x sideline", "end line x hash extended"]},  # 1-2-6
        # the rule only sets a floor (tops at least 30 ft up, 1-2-5-a); posts are
        # built 30 ft above the bar in practice, and a 20 ft upright looks stunted
        "goal": {"crossbar": 10 * FT, "width": 18.5 * FT, "uprightAbove": 30 * FT,
                 "uprightTopMinAboveGround": 30 * FT, "style": "slingshot", "color": "gold",
                 "padHeightMin": 6 * FT,
                 "ribbon": {"width": 4 * IN, "length": 42 * IN, "color": "orange"}},   # 1-2-5
        "chains": {"rodHeightMin": 5 * FT, "side": "opposite press box", "offsetFromSideline": 6 * FT,
                   "groundMarker": {"width": 10 * IN, "length": 32 * IN, "triangle": 5 * IN}},  # 1-2-7
    },
}

DISCREPANCIES = [
    {"league": "college-football", "key": "props.benches.fromX/toX",
     "scene": [25.0, 75.0], "rule": [20.0, 80.0], "source": "NCAA 1-2-4-a: team area between the 20-yard lines"},
    {"league": "nfl", "key": "props.benches.fromX/toX",
     "scene": [32.0, 68.0], "rule": [30.0, 70.0], "source": "NFL diagram note 8: benches between the 30-yard lines"},
    {"league": "nfl", "key": "props.goalpost.uprightAbove",
     "scene": 10.0, "rule": 35 * FT, "source": "NFL §3 Art.2: uprights extend 35 ft above the crossbar"},
    {"league": "college-football", "key": "props.goalpost.uprightAbove",
     "scene": 10.0, "rule": 30 * FT, "source": "NCAA 1-2-5-a sets tops at least 30 ft up; 30 ft above the bar is standard build"},
]


def league(name: str) -> dict:
    """Scene geometry plus rulebook paint for one league."""
    if name not in RULES:
        raise KeyError(f"no rules for {name!r}; known: {', '.join(RULES)}")
    return {"name": name, "scene": RULES[name], "paint": PAINT[name]}


LEAGUES = tuple(PAINT)
