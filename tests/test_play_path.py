"""How a play moves: `scene.play_path`, the broadcast replay graphic every
client flies the same way (`visual.broadcast.play`).

Stated against every play of three real replayed games, not a hand-made one:

  - the segments join end to end and stay on the field
  - a run hugs the grass: it never rises above carry height
  - a pass drops back, then flies a gravity parabola whose rise grows with
    the length of the throw, and lands where the text and spots say
  - kicks hang for as long as real ones do, and a good field goal clears
    the crossbar
  - plays take real time, and a fast replay divides it like any play
"""

from __future__ import annotations

import math
import unittest

from fantasyedge import scene as sc
from tests import test_replay_scene as T

EVENTS = (T.REGULATION, T.OVERTIME, T.PICK_SIX)


def setUpModule():
    T.setUpModule()


def end_of(seg: dict) -> list[float]:
    return {"hold": lambda s: s["at"], "carry": lambda s: s["points"][-1], "air": lambda s: s["to"]}[seg["kind"]](seg)


def start_of(seg: dict) -> list[float]:
    return {"hold": lambda s: s["at"], "carry": lambda s: s["points"][0], "air": lambda s: s["from"]}[seg["kind"]](seg)


def peak(seg: dict) -> float:
    if seg["kind"] == "air":
        return max(sc.air_point(seg, i / 40)[1] for i in range(41))
    if seg["kind"] == "carry":
        return max(p[1] for p in seg["points"])
    return seg["at"][1]


class TestPlayPath(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tokens = sc.load_tokens()
        cls.rule = cls.tokens["visual"]["broadcast"]["play"]
        cls.scenes = {e: T.SceneAt.at(e, 99999, speed=1.0) for e in EVENTS}
        cls.arcs = [a for s in cls.scenes.values() for d in s["drives"] for a in d["arcs"]]

    def of(self, *types: str) -> list[dict]:
        return [a for a in self.arcs if a["type"] in types]

    def test_every_play_has_a_path_that_joins_end_to_end_and_stays_on_the_field(self):
        self.assertGreater(len(self.arcs), 400)
        for a in self.arcs:
            p = a["path"]
            segs = p["segments"]
            self.assertTrue(segs, a["text"])
            self.assertEqual(segs[0]["phase"], "presnap", f"{a['id']}: a play starts on its spot")
            self.assertAlmostEqual(segs[0]["at"][0], a["fromX"], places=2, msg=a["text"])
            self.assertEqual(p["snap"], [round(a["fromX"], 3), round(a["lane"], 3)])
            for prev, seg in zip(segs, segs[1:]):
                a0, b0 = end_of(prev), start_of(seg)
                self.assertLess(math.dist(a0[::2], b0[::2]), 0.01, f"{a['id']} {seg['phase']}: a gap in the path")
            for seg in segs:
                for q in ([start_of(seg), end_of(seg)] + seg.get("points", [])):
                    # A good kick carries on past the end line into the net.
                    over = self.tokens["arc"]["goalKick"]["overshootYards"] + 0.5
                    self.assertTrue(-10 - over <= q[0] <= 110 + over, f"{a['id']}: x {q[0]} off the field")
                    self.assertLessEqual(abs(q[2]), 26.67 + 2.0, f"{a['id']}: z {q[2]} past the sideline")
                    self.assertGreaterEqual(q[1], 0.0, f"{a['id']}: under the grass")
            self.assertAlmostEqual(p["seconds"], sum(s["seconds"] for s in segs), places=2)
            self.assertLessEqual(p["seconds"], self.rule["maxSeconds"] + 0.01)

    def test_a_run_hugs_the_grass(self):
        """A run is carried, never flown: nothing on its path rises above
        carry height, and it finishes on the scene's spot."""
        runs = self.of("Rush", "Rushing Touchdown")
        self.assertGreater(len(runs), 150)
        carry = self.rule["heights"]["carry"]
        for a in runs:
            segs = a["path"]["segments"]
            self.assertFalse([s for s in segs if s["kind"] == "air" and s["phase"] != "snap"], a["text"])
            for s in segs:
                self.assertLessEqual(peak(s), carry + 0.01, f"{a['id']}: a run rose to {peak(s):.2f} yd")
            self.assertAlmostEqual(end_of(segs[-1])[0], a["toX"], places=2, msg=a["text"])

    def test_a_run_goes_the_way_the_text_says(self):
        """Facing the attack, right is +z x attack: "right end" ends on the
        runner's right of the lane, "left end" on his left."""
        checked = 0
        for a in self.of("Rush", "Rushing Touchdown"):
            text = a["text"].lower()
            if "kneels" in text or a["side"] is None:
                continue
            attack = 1.0 if a["side"] == "home" else -1.0
            run = [s for s in a["path"]["segments"] if s["phase"] == "run"][0]
            off = (run["points"][-1][2] - a["lane"]) * attack
            if "right end" in text:
                self.assertGreater(off, 3.0, a["text"])
                checked += 1
            elif "left end" in text:
                self.assertLess(off, -3.0, a["text"])
                checked += 1
            elif "up the middle" in text:
                self.assertLess(abs(off), 0.01, a["text"])
                checked += 1
        self.assertGreater(checked, 40)

    def test_a_pass_drops_back_then_flies_higher_the_longer_it_is_thrown(self):
        g = self.rule["gravity"]
        ps = self.rule["pass"]
        throws = []
        for a in self.of("Pass Reception", "Passing Touchdown", "Pass Incompletion"):
            segs = a["path"]["segments"]
            phases = [s["phase"] for s in segs]
            if "spike" in phases:
                continue
            self.assertIn("drop", phases, a["text"])
            drop = segs[phases.index("drop")]
            attack = 1.0 if a["side"] == "home" else -1.0
            self.assertLess((drop["points"][-1][0] - a["fromX"]) * attack, 0, f"{a['id']}: the drop goes backward")
            throw = segs[phases.index("throw")]
            length = math.dist(throw["from"][::2], throw["to"][::2])
            hang = ps["hangBase"] + ps["hangPerYard"] * length
            self.assertAlmostEqual(throw["seconds"], hang, delta=0.01)
            self.assertAlmostEqual(throw["rise"], g * hang * hang / 8 * ps["drag"], delta=0.01)
            self.assertTrue(0.4 <= throw["seconds"] <= 3.5, f"{a['id']}: hang {throw['seconds']}")
            throws.append((length, throw["rise"]))
            if a["type"] != "Pass Incompletion":
                self.assertAlmostEqual(end_of(segs[-1])[0], a["toX"], places=2, msg=a["text"])
            else:
                self.assertEqual(throw["to"][1], 0.0, f"{a['id']}: an incompletion falls to the grass")
        throws.sort()
        self.assertGreater(len(throws), 150)
        for (l0, r0), (l1, r1) in zip(throws, throws[1:]):
            if l1 > l0 + 1e-6:
                self.assertGreaterEqual(r1, r0 - 1e-6, "a longer throw never flies lower")
        short = [r for l, r in throws if l < 12]
        deep = [r for l, r in throws if l > 30]
        self.assertTrue(short and deep)
        self.assertGreater(min(deep), 2.5 * max(short) / 2, "a deep ball hangs visibly higher than a quick one")
        self.assertLess(max(short), 3.0, "a quick throw is a line, not a rainbow")

    def test_deep_passes_throw_further_than_short_ones(self):
        deep, short = [], []
        for a in self.of("Pass Reception", "Passing Touchdown"):
            throw = [s for s in a["path"]["segments"] if s["phase"] == "throw"][0]
            air = abs(throw["to"][0] - a["fromX"])
            (deep if " deep " in a["text"] else short if " short " in a["text"] else []).append(air)
        self.assertTrue(deep and short)
        self.assertGreater(sum(deep) / len(deep), 2 * sum(short) / len(short))

    def test_kicks_hang_like_real_ones(self):
        """Punts about four seconds, kickoffs about four, field goals two to
        three and a half; a punt's `to` spot is where the text lands it."""
        ranges = {"Punt": (3.5, 5.0), "Kickoff": (3.4, 4.6), "Field Goal Good": (1.5, 3.6),
                  "Field Goal Missed": (1.5, 3.6)}
        for a in self.of(*ranges):
            kick = [s for s in a["path"]["segments"] if s["phase"] == "kick"][0]
            lo, hi = ranges[a["type"]]
            self.assertTrue(lo <= kick["seconds"] <= hi, f"{a['type']} {a['id']}: hang {kick['seconds']}")
        punts = [a for a in self.of("Punt") if "punts 51 yards to DAL 26" in a["text"]]
        self.assertTrue(punts)
        kick = [s for s in punts[0]["path"]["segments"] if s["phase"] == "kick"][0]
        home = self.scenes[T.REGULATION]["teams"]["home"]["abbr"]
        self.assertEqual(home, "PHI")
        self.assertAlmostEqual(kick["to"][0], 100 - 26, places=2)
        self.assertGreater(peak(kick), 12.0, "a punt hangs high")

    def test_a_good_field_goal_clears_the_crossbar_on_its_path(self):
        clearance = self.tokens["arc"]["goalKick"]["minClearanceYards"]
        seen = 0
        for s in self.scenes.values():
            f = s["field"]
            for a in (x for d in s["drives"] for x in d["arcs"]):
                text = a["text"].lower()
                if "field goal" not in a["type"].lower() or "good" not in text or "no good" in text:
                    continue
                kick = [x for x in a["path"]["segments"] if x["phase"] == "kick"][0]
                attack = 1.0 if kick["to"][0] > kick["from"][0] else -1.0
                plane = f["length"] + f["endZone"] if attack > 0 else -f["endZone"]
                u = (plane - kick["from"][0]) / (kick["to"][0] - kick["from"][0])
                self.assertTrue(0 < u < 1, a["id"])
                height = sc.air_point(kick, u)[1]
                self.assertGreaterEqual(height, sc.CROSSBAR_YARDS + clearance, f"{a['id']}: {height:.2f} yd at the posts")
                seen += 1
        self.assertGreater(seen, 3)

    def test_plays_take_real_time_and_a_fast_replay_divides_it(self):
        # A run to the sideline crosses the field first, so it is timed on its own.
        rush = [a for a in self.of("Rush") if 0 < abs(a["toX"] - a["fromX"]) <= 10
                and "kneels" not in a["text"] and " ob " not in a["text"]]
        self.assertGreater(len(rush), 80)
        self.assertTrue(all(2.4 <= a["path"]["seconds"] <= 5.5 for a in rush),
                        sorted(a["path"]["seconds"] for a in rush)[:3] + sorted(a["path"]["seconds"] for a in rush)[-3:])
        wide = [a for a in self.of("Rush") if " ob " in a["text"] and abs(a["toX"] - a["fromX"]) <= 10]
        self.assertTrue(wide and all(a["path"]["seconds"] <= 7.0 for a in wide),
                        sorted(a["path"]["seconds"] for a in wide)[-3:])
        short = [a for a in self.of("Pass Reception") if abs(a["toX"] - a["fromX"]) <= 15]
        self.assertTrue(all(3.0 <= a["path"]["seconds"] <= 6.5 for a in short))
        motion = self.tokens["motion"]
        fast = T.SceneAt.at(T.REGULATION, 99999, speed=60.0)
        slow = self.scenes[T.REGULATION]
        for d0, d1 in zip(slow["drives"], fast["drives"]):
            for a0, a1 in zip(d0["arcs"], d1["arcs"]):
                self.assertEqual(a0["path"]["duration"], a0["path"]["seconds"])
                want = max(motion["floorSeconds"], a0["path"]["seconds"] / (60 / motion["referenceSpeed"]))
                self.assertAlmostEqual(a1["path"]["duration"], want, places=2)

    def test_the_text_that_describes_the_ball_is_the_play_as_it_stands(self):
        reversed_ = ("(Shotgun) M.Stafford pass short middle intended for B.Corum INTERCEPTED by E.Jones at SEA 44. "
                     "The Replay Official reviewed the interception ruling, and the play was REVERSED."
                     "(Shotgun) M.Stafford pass incomplete short middle to B.Corum.")
        self.assertEqual(sc.play_body(reversed_), "(Shotgun) M.Stafford pass incomplete short middle to B.Corum.")
        two = "S.Darnold pass deep right to A.Barner for 26 yards, TOUCHDOWN. TWO-POINT CONVERSION ATTEMPT. S.Darnold pass to Z.Charbonnet is incomplete."
        self.assertNotIn("incomplete", sc.play_body(two))
        # A tackler named Kneeland is not a kneel.
        sack = [a for a in self.of("Sack") if "Kneeland" in a["text"]]
        self.assertTrue(sack)
        self.assertIn("sack", [s["phase"] for s in sack[0]["path"]["segments"]])

    def test_spots_read_both_clubs_and_shortened_abbreviations(self):
        home, away = {"abbr": "SEA"}, {"abbr": "LAR"}
        self.assertEqual(sc._club_x("SEA", 35, home, away), 35.0)
        self.assertEqual(sc._club_x("LA", 1, home, away), 99.0)
        self.assertIsNone(sc._club_x("DAL", 20, home, away))
        self.assertEqual(sc._spot_after("pass short left to K.Walker to 50 for 8 yards", ("to",), home, away), 50.0)


if __name__ == "__main__":
    unittest.main()
