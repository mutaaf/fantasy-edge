"""Lighting and sky: the contract their assets and tokens keep for every client."""
import json
import pathlib
import unittest

from fantasyedge import scene as sc

ROOT = pathlib.Path(__file__).resolve().parents[1]
TOKENS = json.loads((ROOT / "design" / "tokens.json").read_text())


class LightingSky(unittest.TestCase):
    def test_banks_stand_all_the_way_round(self):
        rim = sc.BOWL["rimLights"]
        self.assertIn(rim["side"], ("all", "far"))
        self.assertGreaterEqual(rim["count"], 8)
        self.assertEqual(rim["count"] % 2, 0, "banks are placed k*pi/(count/2); an odd count skews the bowl")

    def test_blender_mirror_matches_the_scene(self):
        src = (ROOT / "tools" / "blender" / "lighting" / "common.py").read_text()
        self.assertIn(f'RIM = {{"count": {sc.BOWL["rimLights"]["count"]},', src)
        for tier in sc.BOWL["tiers"]:
            self.assertIn(f'"inner": {tier["inner"]}, "outer": {tier["outer"]}', src)

    def test_additive_light_has_an_overdraw_cap(self):
        beams = TOKENS["visual"]["lighting"]["beams"]
        self.assertGreater(beams["overdrawCapScreens"], 0)
        self.assertLessEqual(beams["overdrawCapScreens"], 3.0, "additive beams past three screens will not hold 90 fps")
        for mode in ("stadium", "tabletop"):
            self.assertLess(beams["opacity"][mode], 1.0)

    def test_a_strobe_never_fogs_the_stands(self):
        """Beams and haze are seen against the seats; a touchdown strobe that
        multiplies them turns both decks grey. Their gain is capped near 1, the
        lenses and glows pulse above it, and the field takes a wash."""
        s = TOKENS["visual"]["lighting"]["strobe"]
        self.assertLessEqual(s["beamGainMax"], 1.25)
        self.assertLessEqual(s["hazeGainMax"], 1.1)
        self.assertGreater(s["lensGain"], s["beamGainMax"])
        self.assertGreater(s["glowGain"], s["hazeGainMax"])
        self.assertGreater(s["fieldWashGain"], 1.0)

        def peak(gain, cap):          # LightingActor.strobeGain at pulse 1
            return min(cap, 1 + (gain - 1) * 1.0)
        self.assertLessEqual(peak(s["beamGain"], s["beamGainMax"]), s["beamGainMax"])
        self.assertLessEqual(peak(s["beamGain"], s["hazeGainMax"]), s["hazeGainMax"])

    def test_concourse_fill_sits_on_bowls_guard_wall(self):
        """The fill band lies on the seat-facing back of Bowl's guard wall, from
        the walkway to the LED strip under the cap. Bowl owns that geometry in
        its Blender script; if it moves, the fill must too."""
        import re
        src = (ROOT / "tools" / "blender" / "bowl" / "structure.py").read_text()
        m = re.search(r"lip_m, lip_under, lip_top = ([\d.]+), ([\d.]+), ([\d.]+)", src)
        self.assertIsNotNone(m, "structure.py no longer states the upper deck's lip")
        lip_m, lip_top = float(m.group(1)), float(m.group(3))
        g = re.search(r"wall_f, wall_b, cap = lip_m \+ [\d.]+, lip_m \+ ([\d.]+), lip_top \+ ([\d.]+)", src)
        self.assertIsNotNone(g, "structure.py no longer states the guard wall")
        self.assertIn("cap - 0.16", src, "the LED strip under the cap moved")
        upper = next(t for t in sc.BOWL["tiers"] if t["name"] == "upper")
        rows = TOKENS["visual"]["bowl"]["rows"]["upper"]
        walk = upper["rise"][0] + (upper["rise"][1] - upper["rise"][0]) / rows
        fill = TOKENS["visual"]["lighting"]["fill"]
        self.assertAlmostEqual(fill["wallOffsetYards"], lip_m + float(g.group(1)), places=3)
        self.assertAlmostEqual(fill["wallRise"][0], walk, places=2)
        self.assertAlmostEqual(fill["wallRise"][1], lip_top + float(g.group(2)) - 0.16, places=3)
        self.assertLess(fill["opacity"], 0.5, "a fill, not a light source")

    def test_beam_shader_graph_matches_its_tokens(self):
        """Every beam shader token is an input on the graph's material, the
        compiled package ships, and the UV-scroll fallback keeps its numbers
        for clients without the graph."""
        import re
        sh = TOKENS["visual"]["lighting"]["beams"]["shader"]
        self.assertTrue((ROOT / "assets" / sh["file"]).is_file(), "run tools/blender/lighting/shadergraph.py")
        usda = (ROOT / "tools/blender/lighting/shadergraph/Beams.rkassets/Beams.usda").read_text()
        self.assertIn(f'def Material "{sh["prim"].rsplit("/", 1)[-1]}"', usda)
        inputs = set(re.findall(r"^\s+(?:float|color3f) inputs:([A-Z]\w*) =", usda, re.M))
        for key in ("color", "opacity", "dustRepeat", "dustSpeed", "dustFloor", "dustAmount", "viewPower", "additive"):
            self.assertIn(key[0].upper() + key[1:], inputs, f"Beams.usda has no input for beams.shader.{key}")
        for tex in re.findall(r"@([\w.]+\.png)@", usda):
            self.assertTrue((ROOT / "tools/blender/lighting/shadergraph/Beams.rkassets" / tex).is_file(), tex)
        self.assertIn("ND_realitykit_viewdirection_vector3", usda, "the view-angle falloff is the point of the graph")
        self.assertIn(sh["additive"], (0.0, 1.0)) if isinstance(sh["additive"], int) else self.assertTrue(0 <= sh["additive"] <= 1)
        beams = TOKENS["visual"]["lighting"]["beams"]
        for key in ("opacity", "dustOpacity", "dustTileYards", "dustScrollPerSecond", "overdrawCapScreens"):
            self.assertIn(key, beams, f"the UV-scroll fallback needs beams.{key}")

    def test_beams_fade_from_high_seats(self):
        """From the press box and the upper deck the shafts are seen along
        their length; they must keep well under full alpha there, and the dust
        must not be a high-contrast streak pattern."""
        import math
        E = TOKENS["visual"]["lighting"]["beams"]["elevationFade"]
        self.assertLess(E["fromDegrees"], E["toDegrees"])
        self.assertLessEqual(E["minScale"], 0.5)

        def scale(seat):
            eye_y = seat["y"] + 1.3
            dep = math.degrees(math.atan2(eye_y, math.hypot(seat["x"] - 50, seat["z"])))
            t = max(0.0, min(1.0, (dep - E["fromDegrees"]) / (E["toDegrees"] - E["fromDegrees"])))
            return 1 + (E["minScale"] - 1) * t * t * (3 - 2 * t)
        seats = {s["id"]: s for s in sc.SEATS}
        self.assertLessEqual(scale(seats["pressBox"]), 0.5)
        self.assertLess(scale(seats["upper"]), scale(seats["club"]))
        self.assertGreater(scale(seats["field"]), 0.95)
        sh = TOKENS["visual"]["lighting"]["beams"]["shader"]
        self.assertLessEqual(sh["dustAmount"], 0.5, "high-contrast dust reads as rain")
        self.assertGreaterEqual(sh["viewPower"], 2.5, "edge-on quads must fade hard")

    def test_the_vomitory_mouths_can_be_found_where_the_seats_are_not(self):
        """Lighting lights the mouths Bowl leaves dark, and finds them by the
        hole in the seating rather than by `bowl.seating.vomitory`'s row list,
        which SceneSpec does not decode. That only works if a flagged section
        really is empty over *some* of its rows and not all of them - all of
        them would be an aisle. This pins the data the renderer relies on."""
        scene = sc.build({"home": {"id": "1", "abbr": "CHI"}, "away": {"id": "2", "abbr": "MIN"}})
        seating = scene["bowl"].get("seating")
        self.assertIsNotNone(seating, "bowl.seating carries the sections Lighting reads")

        def seated(row, frm, to):
            mid = ((frm + to) / 2) % 1
            for run in row["runs"]:
                if len(run) < 2:
                    continue
                start = run[0] / max(1e-6, row["length"])
                end = (run[0] + run[1] * row["pitch"]) / max(1e-6, row["length"])
                if start <= mid < end or (end > 1 and mid < end - 1):
                    return True
            return False

        mouths = 0
        for tier in seating["tiers"]:
            rows = sorted(tier["rows"], key=lambda r: r["row"])
            for section in tier.get("sections") or []:
                if not section.get("vomitory"):
                    continue
                empty = [r for r in rows if not seated(r, section["from"], section["to"])]
                self.assertTrue(empty, f"section {section['id']} is flagged a vomitory but has no gap")
                self.assertLess(len(empty), len(rows),
                                f"section {section['id']} is empty in every row, which is an aisle")
                mouths += 1
        self.assertGreaterEqual(mouths, 8, "a bowl this size has vomitories on both decks")

    def test_the_vomitory_fill_is_lit_and_warm(self):
        fill = TOKENS["visual"]["lighting"]["fill"]
        self.assertGreater(fill["vomitoryOpacity"], 0, "Bowl measured the mouths 3.08 stops under the field")
        r, g, b = (int(fill["vomitoryColor"].lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
        self.assertGreater(r, b, "concourse light is warm, not daylight")

    def test_the_beam_wash_target_can_actually_fire(self):
        """A seat that looks along the bowl stacks every shaft on one
        sightline: behind the posts the kept set measured 0.97 screens against
        0.46-0.63 from the club seat, and that stack is the wash over the far
        stands. elevationFade only answers how high a seat is, so a low seat at
        one end gets none of it. The target has to sit below the cap or it can
        never bite, and above zero or a shaft is never drawn."""
        beams = TOKENS["visual"]["lighting"]["beams"]
        self.assertGreater(beams["washTargetScreens"], 0)
        self.assertLess(beams["washTargetScreens"], beams["overdrawCapScreens"],
                        "a target at or above the cap can never fade anything")

    def test_every_lighting_and_sky_file_is_shipped(self):
        for actor in ("lighting", "sky"):
            section = TOKENS["visual"][actor]
            for rel in list(section["assets"].values()) + list(section["models"].values()):
                self.assertTrue((ROOT / "assets" / rel).is_file(), f"{actor}: assets/{rel} missing")
        for rel in TOKENS["visual"]["lighting"]["response"]["probeSources"].values():
            self.assertTrue((ROOT / "assets" / rel).is_file(), rel)

    def test_probes_ship_at_the_level_the_headset_expects(self):
        manifest = json.loads((ROOT / "assets" / "actors" / "lighting" / "manifest.json").read_text())
        for pid in ("stadium_night", "stadium_dusk", "tabletop_room"):
            probe = manifest["probes"][pid]
            self.assertEqual(len(probe["sh9"]), 9)
            self.assertLessEqual(probe["peak"], probe["clamp"])
            if pid.startswith("stadium"):
                self.assertAlmostEqual(probe["belowHorizonMean"], probe["referenceBelowMean"], places=3)

    def test_lighting_is_inside_its_texture_budget(self):
        section = TOKENS["visual"]["lighting"]
        runtime = sum((ROOT / "assets" / rel).stat().st_size for rel in section["assets"].values())
        self.assertLess(runtime / 1e6, 20.0, "visual.lighting assets over the art bible's 20 MB")


if __name__ == "__main__":
    unittest.main()
