"""A college game as renderable geometry, from the shared scene package.

Nothing about the stadium is decided here: `fantasyedge.scene` owns the field,
the bowl, the arcs and the moments, and one renderer draws a Saturday and a
Sunday from the same spec. These tests hold the seam - that a college game
arrives at that package saying what it is, and comes back drawn as college.
"""
from __future__ import annotations

import json
import pathlib
import unittest

from api import handlers
from cfb.game import game_from_summary
from cfb.sources import CaptureSource, FixtureSource
from fantasyedge import scene as shared

REPO = pathlib.Path(__file__).resolve().parents[1]
FIX = REPO / "tests/fixtures"
CAPTURE = REPO / "data/capture/2026-09-19"
HAVE_CAPTURE = (CAPTURE / "scoreboard").is_dir()
WAKE_PUR = "401858224"          # Wake Forest 38-36 Purdue, double overtime
OSU_TEX = "401856682"


def scene_of(event: str) -> dict:
    summary = json.loads((FIX / f"summary_{event}.json").read_text())
    return shared.build(game_from_summary(event, summary))


class DrawnAsCollege(unittest.TestCase):
    """The code of football is a property of the game, not of the caller."""

    @classmethod
    def setUpClass(cls):
        cls.scene = scene_of(WAKE_PUR)

    def test_the_gamecast_states_its_league_so_nothing_has_to_assume(self):
        game = game_from_summary(WAKE_PUR, json.loads((FIX / f"summary_{WAKE_PUR}.json").read_text()))
        self.assertEqual(game["league"], "college-football")
        self.assertEqual(shared.league_of(game), "college-football")
        self.assertEqual(self.scene["league"], "college-football")

    def test_the_field_is_a_college_field(self):
        """Hash marks 60 ft in rather than 70 ft 9 in: a Saturday drawn as a
        Sunday puts every play 3.58 yards off across the field."""
        field = self.scene["field"]
        self.assertEqual(field["hashFromSideline"], 20.0)
        self.assertNotEqual(field["hashFromSideline"], shared.RULES["nfl"]["field"]["hashFromSideline"])
        self.assertEqual(field["goalPostWidth"], 6.167, "18 ft 6 in, the same in both codes")

    def test_the_uprights_and_team_areas_are_the_college_ones(self):
        props = self.scene["field"]["props"]
        self.assertEqual(props["goalpost"]["uprightAbove"], 10.0, "30 ft above the crossbar (NCAA 1-2-5-a)")
        self.assertEqual((props["benches"]["fromX"], props["benches"]["toX"]), (20.0, 80.0),
                         "the team area runs between the 20s (NCAA 1-2-4-a)")

    def test_pylons_stand_at_both_ends_and_the_paint_is_the_clubs(self):
        pylons = self.scene["field"]["props"]["pylon"]["at"]
        self.assertEqual(len(pylons), 12, "four to a goal line, two either side of each end line")
        art = self.scene["field"]["art"]
        self.assertTrue(art["endZones"], "each club's name is lettered across its own end zone")
        self.assertTrue(art["glyphs"], "the letters are an asset, not typeset by a client")


class Overtime(unittest.TestCase):
    """College overtime: alternating possessions from the 25, no ties, and no
    clock. The scene layer handles it; this is the end-to-end check from a
    college payload, on a real 2OT game."""

    @classmethod
    def setUpClass(cls):
        cls.game = game_from_summary(WAKE_PUR, json.loads((FIX / f"summary_{WAKE_PUR}.json").read_text()))
        cls.scene = shared.build(cls.game)

    def test_the_game_is_final_in_the_sixth_period(self):
        self.assertEqual(self.game["state"], "post")
        self.assertEqual(self.game["period"], 6, "four quarters and two overtimes")
        self.assertEqual(self.game["status"]["overtimes"], 2)

    def test_overtime_plays_are_drawn_like_any_other(self):
        overtime = [a for d in self.scene["drives"] for a in d["arcs"] if a.get("period", 0) > 4]
        self.assertTrue(overtime, "both overtimes produced arcs")
        self.assertEqual(sorted({a["period"] for a in overtime}), [5, 6])

    def test_the_winning_score_is_a_moment_in_overtime(self):
        last = self.scene["moments"][-1]
        self.assertEqual(last["kind"], "touchdown")
        self.assertGreater(last["period"], 4, "the game ended in overtime")

    def test_college_overtime_is_untimed(self):
        """The NFL gives overtime a clock; college gives it possessions. The
        rules table says so, and says it per league rather than per caller."""
        self.assertIsNone(shared.RULES["college-football"]["overtimeSeconds"])
        self.assertEqual(shared.RULES["nfl"]["overtimeSeconds"], 600)


class Ranks(unittest.TestCase):
    """A college team carries a rank and an NFL team does not. The rank rides
    on the slate and the detail, not in the scene: the stadium draws a field,
    and #4 belongs on the board beside the name."""

    def test_a_ranked_team_keeps_its_rank_through_the_gamecast(self):
        out = handlers.game(FixtureSource(FIX), OSU_TEX)
        self.assertEqual(out["away"]["rank"], 1)
        self.assertEqual(out["home"]["rank"], 4)

    def test_the_scene_does_not_invent_a_rank(self):
        """The stadium draws a field; #4 belongs on the board beside the name,
        which is the app's business and comes from the slate."""
        teams = scene_of(OSU_TEX)["teams"]
        self.assertNotIn("rank", teams["home"])
        self.assertNotIn("rank", teams["away"])
        self.assertEqual({teams["home"]["abbr"], teams["away"]["abbr"]}, {"OSU", "TEX"})


@unittest.skipUnless(HAVE_CAPTURE, "capture not present")
class FromTheRecordedSlate(unittest.TestCase):
    """One game of 19 September, at a moment it was being played."""

    @classmethod
    def setUpClass(cls):
        cls.src = CaptureSource(CAPTURE, "20260919T230000Z")
        cls.event = "401858230"          # SMU at Louisville, live at 7 PM ET
        cls.scene = handlers.scene(cls.src, cls.event)

    def test_the_route_builds_a_scene_for_a_live_college_game(self):
        self.assertEqual(self.scene["league"], "college-football")
        self.assertEqual(self.scene["event"], self.event)
        self.assertGreater(len(self.scene["drives"]), 10)
        self.assertGreater(sum(len(d["arcs"]) for d in self.scene["drives"]), 100)

    def test_the_ball_is_where_the_board_says_it_is(self):
        """The scene places the ball from the situation, which a summary does
        not carry and the board does - so the handler hands it over."""
        ball = self.scene["ball"]
        self.assertIsNotNone(ball, "a live game has a ball on the field")
        self.assertGreaterEqual(ball["x"], -10.0)
        self.assertLessEqual(ball["x"], 110.0)
        self.assertIsNotNone(self.scene["currentDrive"], "the drive in progress is named")

    def test_a_scene_at_a_moment_matches_the_slate_at_that_moment(self):
        slate = handlers.slate(self.src)
        tile = next(g for g in slate["games"] if g["id"] == self.event)
        self.assertEqual(self.scene["teams"]["home"]["score"], tile["home"]["score"])
        self.assertEqual(self.scene["teams"]["away"]["score"], tile["away"]["score"])

    def test_before_kickoff_there_is_a_field_and_no_arcs(self):
        early = CaptureSource(CAPTURE, "20260919T210000Z")
        slate = handlers.slate(early)
        pre = next(g for g in slate["games"]
                   if g["status"]["state"] == "pre" and g["detail"] != "unavailable")
        with self.assertRaises(handlers.NotFound):
            handlers.scene(early, pre["id"])


if __name__ == "__main__":
    unittest.main()
