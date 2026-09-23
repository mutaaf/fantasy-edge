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
sys.path.insert(0, str(ROOT / "tools" / "blender" / "crowd"))   # specs.py and glb.py need no Blender


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
        self.assertEqual(C["nearPoses"], M["poseMeshes"]["poses"])
        self.assertEqual(C["nearPoses"][:len(C["poses"])], C["poses"], "near poses extend the impostor poses")
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

    def test_the_crowd_fills_bowls_seats_at_the_fill_token(self):
        """Fans come from bowl.seating, one per seat, kept with probability
        visual.crowd.fill (a sold-out bowl still has the odd empty seat), minus
        the clearance around the seats a wearer can take. 49,982 seats at 0.9
        is the 44,982 the stadium logs; the 52,039 before Bowl's seating were
        the crowd's own rows at seat pitch, with no aisles."""
        import random
        C = self.C
        self.assertGreater(C["fill"], 0.8, "a night game is near sold out")
        self.assertLessEqual(C["fill"], 1.0)
        rng = random.Random(1)
        seats = 49_982
        kept = sum(rng.random() < C["fill"] for _ in range(seats))
        self.assertAlmostEqual(kept / seats, C["fill"], delta=0.01)
        src = (ROOT / "apple/FantasyEdge/Sources/Stadium/Actors/Crowd/CrowdActor.swift").read_text()
        seated = src.index("if !c.tabletop, let seating = s.bowl.seating")
        # Round 5: the token is still what fills the bowl, now scaled per seat by where it is and
        # how the game is going (keepChance), so the corners and a decided upper deck thin out.
        block = src[seated:seated + 1800]
        self.assertIn("guard draw < C.fill * CrowdSupport.keepChance(", block, "fill applies to Bowl's seats")
        self.assertIn("let draw = rng.next()", block)

    def test_a_new_stadium_starts_with_no_cues(self):
        """Cues belong to one stadium's blackboard. A process-wide table kept
        them past a stadium's end, and a new stadium at a reused address
        inherited the last game's stand-until-forever. The blackboard starts
        empty, and Crowd keeps no static store of its own."""
        import re
        root = ROOT / "apple/FantasyEdge/Sources/Stadium"
        shared = "".join(f.read_text() for f in root.rglob("*.swift") if "class StadiumShared" in f.read_text())
        self.assertRegex(shared, r"var crowdCues\s*:\s*\[CrowdCue\]\s*=\s*\[\]")
        for f in (root / "Actors/Crowd").glob("*.swift"):
            src = f.read_text()
            self.assertIsNone(re.search(r"static var \w+\s*:\s*\[ObjectIdentifier", src), f"{f.name} keeps cues outside the stadium")
            self.assertNotIn("static var table", src, f.name)

    def test_seated_hips_meet_bowls_pan(self):
        """seat_fit.py measured the kit: at pelvis 0.52 m the lowest point under
        the hips sat 4.7 cm into Bowl's pan (0.442 m) on average. The chair's
        pelvis must stay within 2 cm of 4.5 cm above the kit's, which meets it."""
        self.assertAlmostEqual(self.C["chair"]["pelvisMetres"] - self.C["chair"]["kitPelvisMetres"], 0.045, delta=0.02)

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
        self.assertLessEqual(sum(f["accessory"] == "towel" for f in cast), 2, "a stand of towels reads as flags")

    def test_every_makehuman_asset_a_fan_wears_is_licensed(self):
        """A fan built from a MakeHuman asset the licence page does not list
        is an asset shipped without a record of its CC0 release."""
        licences = (ASSETS / "LICENSES.md").read_text()
        crowd = licences[licences.index("## Crowd"):]
        crowd = crowd[:crowd.index("\n## ", 5)]
        worn = {v for f in self.M["fans"] for k, v in f.get("makehuman", {}).items() if isinstance(v, str)}
        for asset in sorted(worn):
            kind, name = asset.split("/", 1)
            if kind == "skins":
                age, ancestry, sex = name.split("_")
                self.assertIn(age, crowd); self.assertIn(ancestry, crowd); self.assertIn(sex, crowd)
                continue
            listed = f"`{asset}`" in crowd or any(
                f"`{kind}/{stem}01` … `{kind}/{stem}06`" in crowd and name.startswith(stem)
                for stem in ("male_casualsuit", "shoes"))
            self.assertTrue(listed, f"{asset} is worn by a fan but not listed in assets/LICENSES.md")

    def test_no_makehuman_garment_texture_dresses_a_club_top(self):
        """MakeHuman's system garments carry logos and a makehuman.org
        watermark. A club top's albedo must be generated cloth: a colour
        shaded by the garment's normal map, never its diffuse image."""
        import re
        src = (ROOT / "tools/blender/crowd/mh.py").read_text()
        top = re.search(r"top = flat_material\((.*)\)\n", src)
        self.assertIsNotNone(top, "mh.py builds the top's material in one call")
        self.assertIn("colour=", top.group(1))
        self.assertNotIn("image=", top.group(1).replace("shade_from_normal", ""))
        suits = re.search(r"SUITS = \{(.*?)\n\}", src, re.S).group(1)
        for gone in ("female_sportsuit01", "female_casualsuit02"):
            self.assertNotIn(f'"{gone}"', suits, f"{gone} is not what a night crowd wears")
        for f in self.M["fans"]:
            if "makehuman" in f:
                self.assertNotIn(f["makehuman"]["suit"].split("/")[1], ("female_sportsuit01", "female_casualsuit02"))

    def test_fans_are_the_cast_height(self):
        """MPFB's height macro misses by up to 22 cm; the kit scales to the cast.
        The chair's lift assumes a fan's pelvis scales with their height."""
        import specs
        cast = {f["id"]: f for f in specs.cast()}
        for f in self.M["fans"]:
            self.assertAlmostEqual(f["height"], cast[f["id"]]["height"], places=3)

    def test_every_exported_fan_faces_plus_z_on_every_lod(self):
        """Round 4's backwards crowd, held by the marker build.py exports beside the fans.
        Which way a fan faces is a property of the export: at LOD2's 250 triangles a shoe is a
        blob, and round 5 tucks seated feet under the chair, so anatomy cannot answer it. The
        probe's apex points where the fans face, and must land on +Z in every pose file."""
        import glb
        src = (ROOT / "tools/blender/crowd/build.py").read_text()
        ns = {}
        exec(src[src.index("def probe_forward"):src.index("def transfer_normals")], ns)
        for lod in (0, 1, 2):
            probes = [(n, p) for n, p in glb.meshes(ASSETS / f"actors/crowd/lod{lod}_poses.glb", suffix="")
                      if n.startswith("forward_probe")]
            self.assertEqual([n for n, _ in probes], [f"forward_probe_lod{lod}"], f"lod{lod} carries its own probe")
            self.assertGreater(ns["probe_forward"](probes[0][1]), 0.01, f"lod{lod} faces -Z")
        # And it is never drawn: the renderer only ever asks for "<fan>_lod<k>_<pose>".
        actor = (ROOT / "apple/FantasyEdge/Sources/Stadium/Actors/Crowd/CrowdActor.swift").read_text()
        self.assertIn('String(format: "fan%02d_lod%d_%@"', actor)

    def test_the_usdz_forward_axis_is_measured_and_plus_z(self):
        """A USDZ cannot be read with the stdlib; build.py opens each one through pxr after
        export and records which way its fans face. Blender's USD exporter with forward "Z"
        put a fan's front on -Z, and that is exactly what the headset drew."""
        forward = {k: v for k, v in self.M.get("forward", {}).items() if k != "about"}
        self.assertEqual(sorted(forward), sorted(f"lod{l}.{e}" for l in (0, 1, 2) for e in ("usdz", "glb")))
        self.assertEqual(set(forward.values()), {"+Z"}, forward)
        src = (ROOT / "tools/blender/crowd/build.py").read_text()
        self.assertIn('USD_FORWARD = "NEGATIVE_Z"', src)
        self.assertNotIn('export_global_forward_selection="Z"', src)

    def test_near_mixes_are_shares_of_near_poses(self):
        """Every near slot draws only poses the kit froze, and its shares sum to 1."""
        import re
        C = self.C
        src = (ROOT / "apple/FantasyEdge/Sources/Stadium/Actors/Crowd/CrowdChoreography.swift").read_text()
        body = src[src.index("enum Slot"):src.index("public init(_ pose")]
        names = set()
        for line in re.findall(r"^\s*case (.+)$", body, re.M):
            for item in line.split(","):
                m = re.match(r'\s*(\w+)(?:\s*=\s*"([\w_]+)")?', item)
                names.add(m.group(2) or m.group(1))
        for slot, shares in C["nearMix"].items():
            self.assertIn(slot, names, f"nearMix.{slot} is not a slot")
            self.assertAlmostEqual(sum(s["share"] for s in shares), 1.0, places=6, msg=slot)
            for s in shares:
                self.assertIn(s["pose"], C["nearPoses"], f"nearMix.{slot} wears {s['pose']}")
        self.assertLessEqual(C["rings"]["lod0Max"] * 3000, 42_000)

    def test_the_crowd_belongs_to_the_teams_playing(self):
        """Whose crowd it is comes from the scene, never from an assumption: the home and away
        chips, the away section, and the bench range. The shares are the crowd's own tokens."""
        C = self.C
        self.assertGreater(C["support"]["visitingShare"], 0.02, "a real away support exists")
        self.assertLess(C["support"]["visitingShare"], 0.25, "a home game is overwhelmingly the home club's")
        self.assertLess(C["support"]["neutralShare"], C["support"]["visitingShare"])
        src = (ROOT / "apple/FantasyEdge/Sources/Stadium/Actors/Crowd/CrowdSupport.swift").read_text()
        support = src[src.index("static func supportBySection"):src.index("static func supportAt")]
        for reads in ("s.bowl.crowd.awaySection", "s.field.props?.benches", "C.support.visitingShare", "C.support.neutralShare"):
            self.assertIn(reads, support, f"the mix must come from {reads}")
        for invented in ('"CHI"', '"home team"', "abbr =="):
            self.assertNotIn(invented, support, "no club is named in the crowd's code")

    def test_empty_seats_use_only_what_the_scene_knows(self):
        """The scene carries the score, the period and the clock, and no attendance. The blowout
        rule may use the first three; nothing may invent the fourth."""
        C = self.C
        b = C["emptySeats"]["blowout"]
        self.assertGreaterEqual(b["margin"], 14, "a blowout is a blowout, not a one-score game")
        self.assertLess(b["upperFactor"], C["emptySeats"]["upperFactor"], "a decided game empties the upper deck further")
        import re
        src = (ROOT / "apple/FantasyEdge/Sources/Stadium/Actors/Crowd/CrowdSupport.swift").read_text()
        emptying = src[src.index("static func keepChance"):src.index("static func standingShare")]
        for reads in ("s.status.homeScore", "s.status.awayScore", "s.status.period", "s.status.clock"):
            self.assertIn(reads, emptying, reads)
        # Only fields SceneSpec.Status actually carries, so nothing is invented about the game.
        spec = (ROOT / "apple/FantasyEdge/Sources/Stadium/SceneSpec.swift").read_text()
        status = spec[spec.index("public struct Status"):]
        status = status[:status.index("\n    }")]
        known = set(re.findall(r"public let (\w+):", status))
        used = set(re.findall(r"s\.status\.(\w+)", emptying))
        self.assertTrue(used <= known, f"the crowd reads {used - known}, which the scene does not carry")

    def test_the_clock_is_read_as_the_broadcast_writes_it(self):
        """status.clock is "12:40", not seconds; a missing or odd clock must not decide a game."""
        import re
        src = (ROOT / "apple/FantasyEdge/Sources/Stadium/Actors/Crowd/CrowdSupport.swift").read_text()
        body = src[src.index("static func clockSeconds"):]
        body = body[:body.index("\n    }")]
        self.assertIn('split(separator: ":")', body)
        self.assertIn("return nil", body, "an unreadable clock decides nothing")

    def test_a_neutral_section_has_somewhere_to_get_its_colours(self):
        """The unaligned wear the scene's own crowd.neutral and crowd.dark, not an invented grey."""
        src = (ROOT / "apple/FantasyEdge/Sources/Stadium/Actors/Crowd/CrowdActor.swift").read_text()
        self.assertIn("s.palette[s.bowl.crowd.neutral]", src)
        self.assertIn("s.palette[s.bowl.crowd.dark]", src)

    def test_the_visiting_support_is_a_crowd_not_a_painted_block(self):
        """integration-13 read the visitors as a wedge: 9% of the seats but 18% of a wide
        frame's stand pixels, one flat rectangle. Support is drawn per seat on a block grain,
        so a section that carries visitors carries home shirts too."""
        C = self.C
        s = C["support"]
        self.assertLess(s["coreProbability"], 1.0, "even the core of a travelling support is not unanimous")
        self.assertGreater(s["coreProbability"], 0.6, "nor is it a sprinkle")
        self.assertLess(s["edgeProbability"], s["coreProbability"], "the edge is thinner than the core")
        self.assertGreaterEqual(s["blockRows"], 2, "a seat-by-seat dither is noise, not a crowd")
        self.assertGreaterEqual(s["blockSeats"], 2)
        self.assertLess(s["tailRows"], 1.0, "the block thins as it climbs its tier")
        src = (ROOT / "apple/FantasyEdge/Sources/Stadium/Actors/Crowd/CrowdSupport.swift").read_text()
        draw = src[src.index("static func supportAt"):src.index("static func keepChance")]
        for reads in ("coreProbability", "edgeProbability", "blockRows", "blockSeats", "tailRows"):
            self.assertIn(reads, draw, f"the per-seat draw must read {reads}")

    def test_empty_seats_come_in_blocks(self):
        """One empty seat here and one there reads as noise; a stand empties in blocks and at
        the ends of a run."""
        C = self.C["emptySeats"]
        self.assertGreaterEqual(C["blockRows"], 2)
        self.assertGreaterEqual(C["blockSeats"], 2)
        self.assertLess(C["blockEmptiness"], 1.0, "a block of empties is emptier than the bowl's average")
        self.assertGreater(C["blockEmptiness"], 0.4, "but a block is not a hole")
        self.assertLessEqual(C["runEndFactor"], 1.0)
        src = (ROOT / "apple/FantasyEdge/Sources/Stadium/Actors/Crowd/CrowdSupport.swift").read_text()
        keep = src[src.index("static func keepChance"):src.index("static func decided")]
        for reads in ("blockRows", "blockSeats", "blockEmptiness", "runEndSeats", "runEndFactor"):
            self.assertIn(reads, keep, f"keepChance must read {reads}")

    def test_a_scoring_section_brightens_in_its_own_time(self):
        """A support that lights up as one rectangle advertises itself as one."""
        C = self.C
        self.assertGreater(C["tintRiseSeconds"], 0.2)
        self.assertGreater(C["tintJitter"], 0.0)
        src = (ROOT / "apple/FantasyEdge/Sources/Stadium/Actors/Crowd/CrowdActor.swift").read_text()
        self.assertIn("C.tintRiseSeconds", src)
        self.assertIn("C.tintJitter", src)

    def test_the_support_decision_is_pure_and_checkable(self):
        """It decides what the wide frame looks like, so it is testable without RealityKit."""
        src = (ROOT / "apple/FantasyEdge/Sources/Stadium/Actors/Crowd/CrowdSupport.swift").read_text()
        self.assertNotIn("import RealityKit", src)
        self.assertTrue((ROOT / "apple/verify_crowd_support.swift").is_file())

    def test_no_card_stands_nearer_than_a_mesh_fan(self):
        """A row seen end-on holds more fans inside the mesh radius than the caps allow. When the
        caps decided mesh against card, that overflow stood among solid fans as flat billboards
        with the field showing through them (docs/lookdev/experience-r7/crowd-cards-near-crop.png).
        The nearest fans are meshes and the boundary is a circle; the caps only say how wide."""
        src = (ROOT / "apple/FantasyEdge/Sources/Stadium/Actors/Crowd/CrowdActor.swift").read_text()
        rings = src[src.index("// Rings: the nearest fans"):src.index("// Near rings: one merged mesh")]
        self.assertIn("let order = placed.indices.sorted { placed[$0].dist < placed[$1].dist }", rings)
        self.assertIn("where rank < meshes", rings, "mesh against card is decided by rank in distance, not by cap")
        # The dither may pick which mesh ring a fan lands in; it must not push one out to a card.
        loop = rings[rings.index("let d = Double(placed[i].dist)"):rings.index("#if DEBUG")]
        self.assertNotIn(".card", loop, "the dither must not decide mesh against card")

    def test_a_card_is_alpha_tested_and_never_blended(self):
        """Only the card material carries alpha. Blended, a fan reads as a window onto the field."""
        src = (ROOT / "apple/FantasyEdge/Sources/Stadium/Actors/Crowd/CrowdActor.swift").read_text()
        start = src.index("for (key, mb) in cards.sorted")
        cards = src[start:src.index("let e = ModelEntity(mesh: res", start)]
        self.assertIn("mat.opacityThreshold", cards)
        self.assertIn("mat.blending = .opaque", cards)

    def test_the_mesh_circle_is_as_wide_as_the_budget_allows(self):
        """lod2Max is what buys the circle's radius, so it should sit at the budget's edge."""
        C, M = self.C, self.M
        r = C["rings"]
        lod0 = max(f["lod0"]["triangles"] for f in M["fans"])
        lod1 = max(f["lod1"]["triangles"] for f in M["fans"])
        lod2 = max(f["lod2"]["triangles"] for f in M["fans"])
        used = r["lod0Max"] * lod0 + r["lod1Max"] * lod1 + r["lod2Max"] * lod2 + 50_000
        self.assertLessEqual(used, 150_000)
        # Within one more lod2 fan of the ceiling: anything less is budget left on the table.
        self.assertGreater(used + lod2, 150_000, "there is room for another lod2 fan")

    def test_a_stand_wears_its_own_clubs_stated_colour(self):
        """Round 9: the crowd dressed from `bowl.crowd`'s chips, which scene.py solves for
        white text on a panel - so a club that paints its field black had a #6F6F6F crowd and
        two clubs whose chips collided were pushed apart in hue. Cloth comes from
        `teams.*.color` and nothing else."""
        src = (ROOT / "apple/FantasyEdge/Sources/Stadium/Actors/Crowd/CrowdActor.swift").read_text()
        dress = src[src.index("func quickDress(for s: SceneSpec"):src.index("let tinted = Date()")]
        self.assertIn("clubCloth(s.teams.home.color", dress)
        self.assertIn("clubCloth(s.teams.away.color", dress)
        self.assertNotIn("s.bowl.crowd.home", dress, "a panel chip is not what a supporter wears")
        self.assertNotIn("s.bowl.crowd.away", dress)
        # The chips still key the dress cache in no way: a matchup is its two stated colours.
        key = src[src.index("private static func key(_ s: SceneSpec"):]
        key = key[:key.index("\n    }")]
        self.assertIn("s.teams.home.color", key)
        self.assertNotIn("s.bowl.crowd.home", key)

    def test_the_only_thing_a_crowd_moves_is_value(self):
        """Hue and saturation are the club's. The lift is one scale of r, g and b - which is
        what HSV value is - so it cannot move a hue, and it stops at the measured floor."""
        C = self.C["clubValue"]
        self.assertGreater(C["floor"], 0.0)
        self.assertLess(C["floor"], 0.5, "past here a club is not wearing its own colour any more")
        self.assertIn("measured", C["about"].lower())
        look = (ROOT / "apple/FantasyEdge/Sources/Stadium/Actors/Crowd/CrowdLook.swift").read_text()
        body = look[look.index("/// What a club's supporters wear"):]
        body = body[:body.index("\npublic enum CrowdFacing")]
        self.assertIn("let k = floor / v", body, "the lift must be one scale of all three channels")
        self.assertIn("guard v < floor else { return colour }", body, "a club above the floor is worn as stated")
        # The reasoning the ruling asked for, in the code: a stand is not a painted plane.
        for word in ("paint", "fabric", "value"):
            self.assertIn(word, body.lower(), f"the comment should say why a crowd lifts at all ({word})")

    def test_a_club_colour_mottles_around_its_floor(self):
        """The old band clamped every fan into [min, max] *after* the per-fan shade, so a dark
        club's fans all landed on the band's floor exactly: one paint chip, 24k times."""
        src = (ROOT / "apple/FantasyEdge/Sources/Stadium/Actors/Crowd/CrowdActor.swift").read_text()
        loop = src[src.index("for person in 0..<persons"):src.index("let sr = P.secondary.x")]
        self.assertNotIn("P.luma", loop, "the luma band is what flattened a dark club")
        self.assertIn("P.shade.0 + (P.shade.1 - P.shade.0)", loop, "each fan still gets its own shade")
        shade = self.C["shirtShade"]
        self.assertLess(shade[0], 1.0)
        self.assertGreater(shade[1], 1.0)


if __name__ == "__main__":
    unittest.main()
