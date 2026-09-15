"""The Broadcast actor's contract: what every renderer of `visual.broadcast`
must honour, stated as rules a port can check rather than as whatever the
headset happens to draw.

  - the ribbon board's letters are big enough to read from the default seat
  - every play the scene can emit maps to one way the ball moves
  - the win-probability horizon is one band with one label, not rails
  - the footballs exist for both codes and fit the actor's budget
"""

from __future__ import annotations

import json
import math
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fantasyedge import scene as sc                           # noqa: E402

MANNERS = {"spiral", "wobble", "tumble", "carry", "bounce"}


def manner(arc: dict, flight: dict) -> str:
    """The same lookup BallFlight.manner does: style, then type, then shape."""
    if arc["style"] in flight["byStyle"]:
        return flight["byStyle"][arc["style"]]
    kind = arc["type"].lower()
    for key in sorted(flight["byType"], key=len, reverse=True):
        if key in kind:
            return flight["byType"][key]
    return flight["byShape"].get(arc["shape"], "carry")


class TestBroadcastLook(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tokens = sc.load_tokens()
        cls.look = cls.tokens["visual"]["broadcast"]
        cls.scene = sc.build({"home": {"abbr": "CHI", "color": "#0B162A"},
                              "away": {"abbr": "MIN", "color": "#4F2683"}})

    def test_the_ribbon_reads_from_the_default_seat_to_the_far_side(self):
        """Capital letters are about 0.72 of the font size; the font is
        `textShare` of the ribbon's height. From the default stadium seat's
        eyes to the far side of the bowl - where the letters are smallest -
        they must subtend `legibility.minArcMinutes`."""
        ribbon = self.scene["bowl"]["ribbon"]
        shape = self.scene["bowl"]["shape"]
        stadium = self.scene["presentation"]["stadium"]
        seat = next(s for s in stadium["seats"] if s["id"] == stadium["defaultSeat"])
        eye = self.tokens["visual"]["experience"]["camera"]["eyeMeters"] / 0.9144
        rise = ribbon["rise"][1] - ribbon["rise"][0]
        cap = rise * self.look["ribbon"]["textShare"] * 0.72
        far_z = -(shape["halfWidth"] + ribbon["offset"])
        centre_y = (ribbon["rise"][0] + ribbon["rise"][1]) / 2
        distance = math.dist((seat["x"], seat["y"] + eye, seat["z"]), (seat["x"], centre_y, far_z))
        minutes = math.degrees(cap / distance) * 60
        self.assertGreaterEqual(minutes, self.look["ribbon"]["legibility"]["minArcMinutes"],
                                f"ribbon capitals subtend {minutes:.1f}' from {seat['id']} at {distance:.0f} yd")

    def test_every_play_moves_the_ball_one_known_way(self):
        flight = self.look["ball"]["flight"]
        for table in ("byStyle", "byType", "byShape"):
            self.assertLessEqual(set(flight[table].values()), MANNERS, table)
        # Every shape the scene can give an arc has a manner of its own.
        shapes = set(self.tokens["arc"]["shape"])
        self.assertLessEqual(shapes, set(flight["byShape"]), "a shape with no manner flies as a carry by accident")
        cases = [
            ({"style": "pass", "shape": "pass", "type": "Pass Reception"}, "spiral"),
            ({"style": "incomplete", "shape": "pass", "type": "Pass Incompletion"}, "wobble"),
            ({"style": "kick", "shape": "kick", "type": "Punt"}, "tumble"),
            ({"style": "score", "shape": "kick", "type": "Field Goal Good"}, "tumble"),
            ({"style": "run", "shape": "run", "type": "Rush"}, "carry"),
            ({"style": "turnover", "shape": "run", "type": "Fumble Recovery (Opponent)"}, "bounce"),
            # The pick-six: an interception return is a run along the ground.
            ({"style": "score", "shape": "run", "type": "Interception Return Touchdown"}, "carry"),
        ]
        for arc, expected in cases:
            self.assertEqual(manner(arc, flight), expected, arc["type"])
        self.assertTrue(0 < flight["bounceShare"] < 1)
        self.assertGreaterEqual(flight["bounces"], 1)

    def test_the_horizon_is_one_band_and_one_label(self):
        h = self.look["horizon"]
        for gone in ("railOpacity", "fillOpacity", "labelOpacity"):
            self.assertNotIn(gone, h, f"{gone}: the horizon has no rails, fills or floating words any more")
        self.assertGreater(h["thickness"]["stadium"], 0)
        self.assertTrue(0 < h["endFade"] < 0.5)
        self.assertTrue(0 <= h["inkMix"] <= 1)
        self.assertGreaterEqual(h["label"]["pixels"], 48, "a label drawn smaller than 48 px blurs at stadium distance")
        self.assertLess(h["haloOpacity"], h["opacity"])

    def test_the_banner_draws_to_the_moments_contract(self):
        """Broadcast draws the banner; Moments says what and when. Every kind
        the contract names has a word to put up and a timeline entry saying
        when, and Broadcast's own section carries no size or timing that
        would compete with it."""
        contract = self.tokens["visual"]["moments"]["banner"]
        words = self.look["ribbon"]["flash"]["words"]
        timeline = self.tokens["visual"]["moments"]["timeline"]
        for kind in contract["kinds"]:
            self.assertIn(kind, words, f"{kind}: no word for the banner")
            self.assertIn(kind, timeline, f"{kind}: no timeline entry says when its banner goes up")
            self.assertGreaterEqual(timeline[kind]["banner"], 0, f"{kind}: named for a banner but timed never")
        for gone in ("liftYards", "inSeconds", "outSeconds"):
            self.assertNotIn(gone, self.look["banner"], f"banner.{gone} belongs to visual.moments.banner")
        self.assertGreater(contract["widthDegrees"], contract["minHeightDegrees"])
        W, H = self.look["banner"]["pixels"]
        # The slab's own aspect must already reach the minimum height at the stated width.
        self.assertGreaterEqual(contract["widthDegrees"] * H / W, contract["minHeightDegrees"] * 0.9)

    def test_the_ribbon_stands_clear_of_bowls_screen(self):
        """Bowl tessellates its fascia screen to within 0.1 yd of the curve;
        the crawl must stand further off it than that or the two z-fight."""
        self.assertGreater(self.look["ribbon"]["offset"], 0.1)
        self.assertLess(self.look["ribbon"]["offset"], 0.5, "far enough off to see a gap from the lower bowl")

    def test_trails_ghost_with_age_and_never_vanish(self):
        age = self.look["trail"]["age"]
        self.assertTrue(0 < age["decay"] < 1 and 0 < age["thin"] <= 1)
        self.assertTrue(0 < age["minOpacity"] < 1 and 0 < age["minScale"] <= 1)
        tail = self.look["trail"]["tail"]
        self.assertTrue(0 <= tail["opacity"] < 1, "a trail is faint at the snap and full where the ball came down")
        self.assertEqual(len(self.look["trail"]["tabletopView"]), 3)

    def test_the_footballs_ship_for_both_codes_within_budget(self):
        manifest = json.loads((ROOT / "assets/actors/broadcast/manifest.json").read_text())
        self.assertEqual(set(manifest["models"]), {"nfl", "college"})
        for league, m in manifest["models"].items():
            self.assertLessEqual(m["triangles"], 5000, f"{league}: the ball is a speck at 50 yards")
            # NFL and NCAA: 11-11.25 in tip to tip, 21-21.25 in round the middle.
            self.assertAlmostEqual(m["lengthMeters"], 11.1 * 0.0254, delta=0.004)
            self.assertAlmostEqual(m["girthMeters"], 21.1 * 0.0254, delta=0.006)
        models = self.look["models"]
        self.assertEqual(models["footballNFL"], manifest["models"]["nfl"]["usdz"])
        self.assertEqual(models["footballCollege"], manifest["models"]["college"]["usdz"])
        # College stripes are a third material; the NFL ball has none.
        self.assertEqual(manifest["models"]["nfl"]["parts"] + 1, manifest["models"]["college"]["parts"])


if __name__ == "__main__":
    unittest.main()
