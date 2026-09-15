"""The crowd's tokens and the Blender kit they point at must agree.

visual.crowd describes the kit (fan count, poses, atlas layout) so every
renderer reads the same numbers; the kit's manifest is what Blender actually
wrote. A mismatch draws the wrong fan in a cell or a pose row that is not
there, silently, so it fails here instead. No Blender needed.
"""
import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
sys.path.insert(0, str(ROOT / "tools" / "blender" / "crowd"))


class CrowdKitTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.C = json.loads((ROOT / "design/tokens.json").read_text())["visual"]["crowd"]
        cls.M = json.loads((ASSETS / cls.C["kit"]["manifest"]).read_text())

    def test_every_kit_file_exists(self):
        for name, rel in self.C["kit"].items():
            self.assertTrue((ASSETS / rel).is_file(), f"visual.crowd.kit.{name}: assets/{rel} missing")

    def test_tokens_describe_the_kit_blender_wrote(self):
        C, M = self.C, self.M
        self.assertEqual(C["fans"], len(M["fans"]))
        self.assertEqual(C["poses"], M["impostor"]["poses"])
        self.assertEqual(C["poses"], M["poseMeshes"]["poses"])
        self.assertEqual(C["impostor"]["cellPixels"], M["impostor"]["cellPx"])
        self.assertEqual(C["impostor"]["viewsYaw"], M["impostor"]["viewsYawDeg"])
        self.assertEqual(C["impostor"]["worldMetres"], M["impostor"]["worldSize"])
        self.assertEqual(C["impostor"]["blocksPerRow"], M["impostor"]["layout"]["per_row"])
        block = [C["impostor"]["cellPixels"][0] * C["impostor"]["blockCells"][0],
                 C["impostor"]["cellPixels"][1] * C["impostor"]["blockCells"][1]]
        self.assertEqual(block, M["impostor"]["layout"]["block_px"])
        self.assertEqual(C["impostor"]["blockCells"], [len(C["impostor"]["viewsYaw"]), len(C["poses"])])
        self.assertEqual(C["fanGrid"][0] * C["fanGrid"][1], C["fans"])
        self.assertAlmostEqual(C["impostor"]["pairOffsetMetres"], M["impostor"]["pair"]["offsetMetres"])
        # Two neighbours at the scene's seat pitch: offset is half a seat.
        self.assertAlmostEqual(C["impostor"]["pairOffsetMetres"] * 2, C["seatPitchYards"]["stadium"] * C["metresPerYard"], places=2)

    def test_the_atlas_holds_every_fan(self):
        C, M = self.C, self.M
        rows = -(-C["fans"] // C["impostor"]["blocksPerRow"])
        w, h = M["textures"]["impostorAlbedo"]["size"]
        self.assertEqual(w, C["impostor"]["blocksPerRow"] * M["impostor"]["layout"]["block_px"][0])
        self.assertEqual(h, rows * M["impostor"]["layout"]["block_px"][1])

    def test_pose_models_are_declared_and_named_for_each_fan(self):
        models = self.C["models"]
        for lod in ("lod0", "lod1", "lod2"):
            rel = models[f"{lod}Poses"]
            self.assertEqual(rel, self.M["poseMeshes"][lod]["model"].join(["actors/crowd/", ""]))
            self.assertTrue((ASSETS / rel).with_suffix(".glb").is_file())

    def test_rings_fit_the_crowd_budget(self):
        """ART_BIBLE: crowd triangles (raised to 150k when Bowl seated 52k). Near meshes plus two per card must fit
        with a sold-out bowl: Bowl seats about 50k, and far cards hold two each."""
        C, M = self.C, self.M
        r = C["rings"]
        self.assertLess(r["lod0Yards"], r["lod1Yards"])
        lod0 = max(f["lod0"]["triangles"] for f in M["fans"])
        lod1 = max(f["lod1"]["triangles"] for f in M["fans"])
        lod2 = max(f.get("lod2", {"triangles": 250})["triangles"] for f in M["fans"])
        cards = (50_000 // 2) * 2
        self.assertLess(r["lod1Yards"], r["lod2Yards"])
        self.assertLessEqual(r["lod0Max"] * lod0 + r["lod1Max"] * lod1 + r["lod2Max"] * lod2 + cards, 150_000)

    def test_mesh_rings_are_stadium_only(self):
        """The tabletop's crowd budget did not rise with the stadium's: it draws
        cards only. The ring assignment must stay behind the tabletop guard."""
        src = (ROOT / "apple/FantasyEdge/Sources/Stadium/Actors/Crowd/CrowdActor.swift").read_text()
        guard = src.index("if !c.tabletop {\n            let order = placed.indices.sorted")
        rings = src.index("ringOf[i] = .lod2")
        self.assertLess(guard, rings)
        self.assertLess(rings - guard, 1500, "lod rings are assigned inside the stadium-only block")

    def test_the_cast_covers_every_variety_axis(self):
        import specs
        cast = specs.cast()
        self.assertEqual(len(cast), self.C["fans"])
        self.assertEqual(cast, specs.cast(), "the cast must be deterministic")
        for axis, pool in (("build", specs.BUILDS), ("skin", specs.SKIN), ("top", specs.TOPS)):
            self.assertEqual({f[axis] for f in cast}, set(pool), f"every {axis} appears")
        self.assertGreaterEqual(sum(f["scarf"] for f in cast), 3)
        self.assertLessEqual(sum(f["accessory"] == "sign" for f in cast), 2, "signs are rare in a real stand")


if __name__ == "__main__":
    unittest.main()
