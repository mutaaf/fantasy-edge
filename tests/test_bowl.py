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


class BowlModels(unittest.TestCase):
    def test_declared_bowl_models_exist_with_twins(self):
        tokens = sc.load_tokens()
        for name, rel in tokens["visual"]["bowl"].get("models", {}).items():
            usdz = ROOT / "assets" / rel
            self.assertTrue(usdz.is_file(), f"bowl.{name}: {rel}")
            self.assertTrue(usdz.with_suffix(".glb").is_file(), f"bowl.{name}: no .glb twin")


if __name__ == "__main__":
    unittest.main()
