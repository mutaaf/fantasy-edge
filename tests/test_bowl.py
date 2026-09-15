"""The bowl's seating and mounts: what the Bowl actor promises every client.

The scene carries every seat as runs along its row and every rim mount as a
headframe. The Blender kit builds its geometry from the same functions, so
these tests are the contract a web or Android renderer, and the Crowd actor,
can build to without reading the kit.
"""
from __future__ import annotations

import json
import math
import pathlib
import unittest

from fantasyedge import scene as sc

ROOT = pathlib.Path(__file__).resolve().parents[1]


def scene():
    return sc.build({"home": {"id": "1", "abbr": "CHI"}, "away": {"id": "2", "abbr": "MIN"}})


class BowlSeating(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = scene()
        cls.bowl = cls.s["bowl"]
        cls.plan = cls.bowl["seating"]
        cls.shape = cls.bowl["shape"]
        cls.tiers = {t["name"]: t for t in cls.bowl["tiers"]}
        cls.rows = cls.s["visual"]["bowl"]["rows"]

    def seats(self, tier_plan):
        for r, row in enumerate(tier_plan["rows"]):
            ring = sc.BowlRing(self.shape, row["feet"])
            for first, count in row["runs"]:
                for k in range(count):
                    yield r, row, ring, first + k * row["pitch"]

    def test_a_sold_out_bowl_has_a_believable_capacity(self):
        self.assertGreater(self.plan["total"], 45000)
        self.assertLess(self.plan["total"], 80000)
        for t in self.plan["tiers"]:
            self.assertEqual(len(t["rows"]), self.rows[t["tier"]])
            self.assertEqual(sum(r["seats"] for r in t["rows"]), sum(k for r in t["rows"] for _, k in r["runs"]))
        self.assertEqual(self.plan["total"], sum(r["seats"] for t in self.plan["tiers"] for r in t["rows"]))

    def test_every_seat_stands_on_its_row(self):
        """Feet on the tread SceneMath draws, between the row's front and back."""
        for t in self.plan["tiers"]:
            tier = self.tiers[t["tier"]]
            n = len(t["rows"])
            for r, row in enumerate(t["rows"]):
                want = sc.bowl_row(tier, r, n)
                self.assertAlmostEqual(row["floor"], want["tread"], places=3)
                self.assertTrue(want["front"] < row["feet"] < want["back"], row)
                self.assertAlmostEqual(row["length"], sc.BowlRing(self.shape, row["feet"]).length, places=2)

    def test_runs_are_seat_pitch_apart_and_never_overlap(self):
        pitch = self.plan["pitch"]
        for t in self.plan["tiers"]:
            for row in t["rows"]:
                self.assertAlmostEqual(row["pitch"], pitch, delta=0.02)
                ends = []
                for first, count in row["runs"]:
                    self.assertGreater(count, 0)
                    self.assertGreaterEqual(first, 0.0)
                    self.assertLessEqual(first + (count - 1) * row["pitch"], row["length"])
                    ends.append((first, first + (count - 1) * row["pitch"]))
                for (a0, a1), (b0, _) in zip(ends, ends[1:]):
                    self.assertLess(a1 + row["pitch"] * 0.5, b0)

    def test_nobody_sits_in_an_aisle_a_vomitory_or_a_tunnel(self):
        cfg = self.plan
        for t in cfg["tiers"]:
            tier = self.tiers[t["tier"]]
            n = len(t["rows"])
            secs = t["sections"]
            for r, row, ring, s in self.seats(t):
                gaps = sc.bowl_gaps(self.shape, tier, r, n, secs, ring, cfg, self.bowl["tunnels"])
                for a, b, kind in gaps:
                    for off in (-ring.length, 0.0, ring.length):
                        self.assertFalse(a + off < s < b + off, f"{t['tier']} row {r + 1} seat at {s} in {kind}")

    def test_every_seat_footprint_stands_on_tread(self):
        """From the row front to the feet line, across the seat's width, no
        point may fall in a hole the stands geometry cuts. Holes are cut in
        angle between the feet ring's arc ends (tools/blender/bowl/structure.py
        `spans`), so the footprint is tested in angle at its own depth."""
        cfg = self.plan
        for t in cfg["tiers"]:
            tier = self.tiers[t["tier"]]
            n = len(t["rows"])
            secs = t["sections"]
            for r, row in enumerate(t["rows"]):
                feet_ring = sc.BowlRing(self.shape, row["feet"])
                holes = [(feet_ring.angle(a % feet_ring.length), feet_ring.angle(b % feet_ring.length))
                         for a, b, k in sc.bowl_gaps(self.shape, tier, r, n, secs, feet_ring, cfg, self.bowl["tunnels"])
                         if k in ("vomitory", "tunnel")]
                if not holes:
                    continue
                front = sc.bowl_row(tier, r, n)["front"] + 0.02
                rings = [sc.BowlRing(self.shape, m) for m in (front, (front + row["feet"]) / 2, row["feet"])]
                half = row["pitch"] / 2
                for first, count in row["runs"]:
                    for k in range(count):
                        t_seat = feet_ring.angle(first + k * row["pitch"])
                        for ring in rings:
                            s = ring.arc_at(t_seat)
                            for lat in (-half, 0.0, half):
                                ang = ring.angle((s + lat) % ring.length)
                                for a0, a1 in holes:
                                    inside = a0 <= ang <= a1 if a0 <= a1 else (ang >= a0 or ang <= a1)
                                    self.assertFalse(inside, f"{t['tier']} row {r + 1}: seat at arc "
                                                             f"{first + k * row['pitch']:.2f} overhangs a hole")

    def test_aisles_line_up_and_sections_tile_the_ring(self):
        for t in self.plan["tiers"]:
            secs = t["sections"]
            self.assertGreaterEqual(len(secs), 8)
            ids = [s["id"] for s in secs]
            self.assertEqual(len(ids), len(set(ids)))
            width = secs[0]["to"] - secs[0]["from"]
            for s in secs:
                self.assertAlmostEqual(s["to"] - s["from"], width, places=5)
                self.assertIn(s["side"], {"home", "far", "east", "west"})
            self.assertTrue(any(s["vomitory"] for s in secs))

    def test_every_vomitory_has_an_accessible_platform_in_front(self):
        for t in self.plan["tiers"]:
            v = self.plan["vomitory"][t["tier"]]
            vom = [s for s in t["sections"] if s["vomitory"]]
            self.assertEqual(len(t["accessible"]), len(vom))
            for a in t["accessible"]:
                self.assertEqual(a["row"], v["rows"][0])          # row numbers are 1-based
                self.assertGreater(a["length"], v["width"])

    def test_team_tunnels_clear_the_front_rows_behind_each_end_zone(self):
        lower = next(t for t in self.plan["tiers"] if t["tier"] == "lower")
        tier = self.tiers["lower"]
        for tn in self.bowl["tunnels"]:
            t_end = 0.0 if tn["x"] > 50 else math.pi
            for r, row in enumerate(lower["rows"]):
                ring = sc.BowlRing(self.shape, row["feet"])
                s_end = ring.arc_at(t_end)
                near = [first + k * row["pitch"] for first, count in row["runs"] for k in range(count)
                        if abs(((first + k * row["pitch"]) - s_end + ring.length / 2) % ring.length - ring.length / 2)
                        < tn["width"] / 2]
                if sc.bowl_row(tier, r, len(lower["rows"]))["tread"] < tn["height"] + self.plan["tunnelClear"]:
                    self.assertEqual(near, [], f"row {r + 1} sits over the tunnel at x={tn['x']}")

    def test_every_seat_faces_into_the_bowl(self):
        lower = next(t for t in self.plan["tiers"] if t["tier"] == "lower")
        for r, row, ring, s in list(self.seats(lower))[::97]:
            t = ring.angle(s)
            x, z = sc.bowl_point(self.shape, row["feet"], t)
            nx, nz = sc.bowl_inward(self.shape, row["feet"], t)
            self.assertLess(nx * x + nz * z, 0.0)

    def test_the_layout_is_small_enough_to_ship_in_every_scene(self):
        self.assertLess(len(json.dumps(self.plan)), 80_000)
        self.assertEqual(json.dumps(sc.bowl_seating(self.shape, self.rows)), json.dumps(self.plan))


class BowlMounts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = scene()
        cls.bowl = cls.s["bowl"]
        cls.rim_tokens = cls.s["visual"]["lighting"]["rim"]

    def test_one_headframe_per_rim_bank_on_the_parapet_facing_the_field(self):
        rim = self.bowl["mounts"]["rim"]
        self.assertEqual(len(rim), self.bowl["rimLights"]["count"])
        upper = next(t for t in self.bowl["tiers"] if t["name"] == "upper")
        m = upper["outer"] + self.bowl["rimLights"]["beyondOuter"]
        for k, mount in enumerate(rim):
            x, y, z = mount["position"]
            t = k * math.pi / (len(rim) / 2) + self.rim_tokens["phase"]
            px, pz = sc.bowl_point(self.bowl["shape"], m, t)
            self.assertAlmostEqual(x, px, places=2)
            self.assertAlmostEqual(z, pz, places=2)
            self.assertAlmostEqual(y, upper["rise"][1] + self.rim_tokens["heightAbove"]["stadium"], places=2)
            fx, _, fz = mount["facing"]
            self.assertAlmostEqual(math.hypot(fx, fz), 1.0, places=3)
            self.assertLess(fx * x + fz * z, 0.0)
            self.assertLess(mount["pitch"], 0.0)
            self.assertEqual(mount["farSide"], z <= self.rim_tokens["farSideMaxZ"])
            self.assertGreaterEqual(y, mount["base"])


class BowlSightlines(unittest.TestCase):
    """Every seat preset sees the field over the structure the bowl builds in
    front of it. Heights here mirror tools/blender/bowl/structure.py."""

    EYE = 1.2 / 0.9144

    @classmethod
    def setUpClass(cls):
        cls.s = scene()
        cls.seats = {o["id"]: o for o in cls.s["presentation"]["stadium"]["seats"]}
        cls.tiers = {t["name"]: t for t in cls.s["bowl"]["tiers"]}
        cls.rows = cls.s["visual"]["bowl"]["rows"]

    def clears(self, seat, obstacle_offset, obstacle_top, target_offset, target_y=0.0):
        """Height of the eye-to-target line above the obstacle, along the
        radial profile (offsets outward from the field edge)."""
        half_w = self.s["field"]["width"] / 2
        eye_off = abs(seat["z"]) - half_w if abs(seat["x"] - 50) < 60 else abs(seat["x"] - 50) - 60
        eye_y = seat["y"] + self.EYE
        f = (obstacle_offset - target_offset) / (eye_off - target_offset)
        return target_y + (eye_y - target_y) * f - obstacle_top

    def test_the_upper_seat_sees_the_near_sideline_over_the_guard_wall(self):
        upper = self.tiers["upper"]
        walk = upper["rise"][0] + (upper["rise"][1] - upper["rise"][0]) / self.rows["upper"]
        cap = walk + 0.9                                     # GUARD.capAboveWalk
        c = self.clears(self.seats["upper"], 39.8 + 1.15, cap, 0.0)
        self.assertGreater(c, 0.06 / 0.9144, "C-value under 6 cm to the near sideline")

    def test_the_end_zone_seat_sees_the_goal_line_over_the_tunnel(self):
        lower = self.tiers["lower"]
        n = self.rows["lower"]
        tn = self.s["bowl"]["tunnels"][0]
        clear = self.s["bowl"]["seating"]["tunnelClear"]
        deck = max(sc.bowl_row(lower, r, n)["tread"] for r in range(n)
                   if sc.bowl_row(lower, r, n)["tread"] < tn["height"] + clear)
        rail = deck + 0.95
        wall = self.s["bowl"]["wall"]["offset"] + 0.3
        c = self.clears(self.seats["endzone"], wall, rail, -10.0)   # the goal line, 10 yd in from the end line
        self.assertGreater(c, 0.0, "the tunnel rail hides the goal line from the end-zone seat")

    def test_the_press_box_seat_sees_the_near_sideline_over_both_decks_and_their_fans(self):
        seat = self.seats["pressBox"]
        fans = 2.0                                                # a standing fan's head above the tread
        for tier in self.tiers.values():
            for off in (tier["inner"], (tier["inner"] + tier["outer"]) / 2, tier["outer"]):
                top = tier["rise"][0] + (tier["rise"][1] - tier["rise"][0]) * (off - tier["inner"]) / (tier["outer"] - tier["inner"])
                self.assertGreater(self.clears(seat, off, top + fans, 0.0), 0.0, f"{tier['name']} at {off}")
        parapet = self.s["bowl"]["parapet"]
        self.assertGreater(self.clears(seat, parapet["offset"], parapet["top"], 0.0), 0.0)

    def test_the_press_box_stands_clear_of_the_rim_rigs_and_the_upper_deck(self):
        pb = self.s["bowl"]["pressBox"]
        self.assertGreaterEqual(pb["offset"], self.tiers["upper"]["outer"])
        self.assertGreater(pb["rise"][0], self.s["bowl"]["parapet"]["top"])
        half = (pb["toX"] - pb["fromX"]) / 2
        for m in self.s["bowl"]["mounts"]["rim"]:
            x, _, z = m["position"]
            if z < 0:
                self.assertGreater(abs(x) - m["headframe"][0] / 2, half + 1.0, m["id"])

    def test_the_video_board_stands_above_the_stands_and_out_of_the_end_zone_view(self):
        vb = self.s["bowl"]["videoBoard"]
        cx, cy, cz = vb["centre"]
        w, h = vb["size"]
        top_row = self.tiers["upper"]["rise"][1]
        self.assertGreater(cy - h / 2, top_row)
        self.assertGreater(cx - 50, 60 + self.s["bowl"]["parapet"]["offset"])      # behind the east end
        self.assertAlmostEqual(math.hypot(*vb["facing"]), 1.0, places=3)
        self.assertLess(vb["facing"][0], 0.0)                                       # toward midfield
        # no rim headframe inside the board's width
        for m in self.s["bowl"]["mounts"]["rim"]:
            x, _, z = m["position"]
            if x > 100:
                self.assertGreater(abs(z) - m["headframe"][0] / 2, w / 2 + 0.5, m["id"])


class BowlModels(unittest.TestCase):
    def test_declared_bowl_models_exist_with_twins(self):
        tokens = sc.load_tokens()
        for name, rel in tokens["visual"]["bowl"].get("models", {}).items():
            usdz = ROOT / "assets" / rel
            self.assertTrue(usdz.is_file(), f"bowl.{name}: {rel}")
            self.assertTrue(usdz.with_suffix(".glb").is_file(), f"bowl.{name}: no .glb twin")


if __name__ == "__main__":
    unittest.main()
