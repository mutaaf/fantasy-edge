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
    """A college team carries a rank and an NFL team does not. The board beside
    the name is the stadium's board, so the rank has to reach the scene to be
    drawn on it - but only ever as the payload stated it. A team outside the 25
    says nothing, which is not the same as claiming to be 26th."""

    def test_a_ranked_team_keeps_its_rank_through_the_gamecast(self):
        out = handlers.game(FixtureSource(FIX), OSU_TEX)
        self.assertEqual(out["away"]["rank"], 1)
        self.assertEqual(out["home"]["rank"], 4)

    def test_the_rank_reaches_the_board_the_stadium_draws(self):
        teams = scene_of(OSU_TEX)["teams"]
        self.assertEqual(teams["away"]["rank"], 1)
        self.assertEqual(teams["home"]["rank"], 4)
        self.assertEqual({teams["home"]["abbr"], teams["away"]["abbr"]}, {"OSU", "TEX"})

    def test_the_scene_does_not_invent_a_rank(self):
        """An unranked team and an NFL club are the same case: the key is
        absent, and the renderer draws the chip without a number."""
        teams = scene_of(WAKE_PUR)["teams"]
        self.assertNotIn("rank", teams["home"])
        self.assertNotIn("rank", teams["away"])

    def test_a_rank_outside_the_poll_is_not_carried(self):
        """Some feeds put 99 in the field to mean unranked. 99 is not a rank."""
        game = game_from_summary(OSU_TEX, json.loads((FIX / f"summary_{OSU_TEX}.json").read_text()))
        game["home"]["rank"], game["away"]["rank"] = 99, 0
        teams = shared.build(game)["teams"]
        self.assertNotIn("rank", teams["home"])
        self.assertNotIn("rank", teams["away"])


class DrawnFromCollegeText(unittest.TestCase):
    """The scene package reads a play's text to draw it, and the two codes do
    not write the same sentence. These are the places where reading it the NFL
    way drew a college play wrong."""

    @classmethod
    def setUpClass(cls):
        cls.arcs = {}
        for event in ("401856782", "401858224"):
            scene = scene_of(event)
            cls.arcs[event] = {a["id"]: a for d in scene["drives"] for a in d["arcs"]}
        cls.field = scene["field"]

    def phases(self, event: str, arc: str) -> list[str]:
        return [s["phase"] for s in self.arcs[event][arc]["path"]["segments"]]

    def test_the_kick_clause_is_found_in_either_code(self):
        """The NFL conjugates the verb, college names it. Splitting on "kicks"
        left every college kick with an empty clause and no landing spot."""
        self.assertEqual(shared._kick_clause("J.Moody kicks 65 yards from DET 35").strip(),
                         "65 yards from DET 35")
        self.assertEqual(shared._kick_clause("P. Woodring kickoff 65 yards to the ARK00").strip(),
                         "65 yards to the ARK00")
        self.assertEqual(shared._kick_clause("G. Rush punt 37 yards to the UGA31").strip(),
                         "37 yards to the UGA31")

    def test_a_spot_is_read_with_or_without_the_space(self):
        """"to DAL 32" and "to the PUR36" are the same fact, written twice."""
        home, away = {"abbr": "PUR"}, {"abbr": "WAKE"}
        self.assertEqual(shared._spot_after("to PUR 36", ("to",), home, away), 36.0)
        self.assertEqual(shared._spot_after("to the PUR36", ("to",), home, away), 36.0)
        self.assertEqual(shared._spot_after("to the ARK00", ("to",), {"abbr": "ARK"}, away), 0.0)

    def test_a_kickoff_out_of_bounds_is_not_returned(self):
        """It was drawn caught in midfield and carried to the sideline at 105
        yards a second, because the runback's clock only counted the yards up
        the field and the ball also had to cross to the touchline."""
        arc = self.arcs["401858224"]["401858224122"]
        self.assertIn("out of bounds", arc["text"])
        self.assertEqual(self.phases("401858224", "401858224122")[-1], "catch")
        self.assertNotIn("return", self.phases("401858224", "401858224122"))
        landing = arc["path"]["segments"][2]["to"]
        self.assertGreater(abs(landing[2]), self.field["width"] / 2 - 1,
                           "the ball came down past the touchline, not in the middle of the field")

    def test_a_punt_return_ends_where_the_text_says_it_ended(self):
        arc = self.arcs["401858224"]["401858224683"]
        self.assertIn("return", arc["text"])
        self.assertIn("return", self.phases("401858224", "401858224683"))
        self.assertAlmostEqual(arc["path"]["segments"][3]["to"][0], 36.0, places=3,
                               msg="the punt came down at PUR36, where the text says")

    def test_a_run_is_not_thrown_because_the_conversion_was_a_pass(self):
        """"3-yd run, two-point pass conversion failed" is a run. The
        conversion is a different play, appended to this one; reading it as
        this one put the ball 2.6 yards in the air on a rushing touchdown."""
        arc = self.arcs["401858224"]["401858224837"]
        self.assertEqual(arc["shape"], "run")
        self.assertIn("pass", arc["text"])
        self.assertEqual([s["kind"] for s in arc["path"]["segments"] if s["kind"] == "air"], [],
                         "a run never leaves the ground")


class TheLineOnTheBoard(unittest.TestCase):
    """The stadium's boards say the period and the clock, and they say it from
    `status.label`. The NFL gamecast writes that line itself; the college one
    does not, and a blank board is not an acceptable answer to a payload that
    states the period, the clock and the overtimes plainly."""

    def label(self, **over) -> str:
        game = game_from_summary(WAKE_PUR, json.loads((FIX / f"summary_{WAKE_PUR}.json").read_text()))
        game["status"] = dict(game["status"], **over.pop("status", {}))
        return shared.build(dict(game, **over))["status"]["label"]

    def test_a_live_college_game_says_the_clock_and_the_quarter(self):
        self.assertEqual(self.label(state="in", period=4, clock="2:43",
                                    status={"completed": False}), "2:43 4th")

    def test_a_double_overtime_final_says_so(self):
        self.assertEqual(self.label(), "Final/2OT")

    def test_college_overtime_shows_no_clock_because_it_has_none(self):
        """An untimed period with "0:00" on the board is a lie the rules table
        already knows the answer to."""
        self.assertEqual(self.label(state="in", period=6, clock="0:00",
                                    status={"completed": False}), "2OT")
        self.assertEqual(self.label(league="nfl", state="in", period=5, clock="2:43",
                                    status={"completed": False}), "2:43 OT")

    def test_a_stated_label_wins(self):
        """A gamecast that has decided this has decided it; the fallback is for
        a payload that says nothing, not a second opinion."""
        self.assertEqual(self.label(label="Delayed"), "Delayed")

    def test_halftime_is_not_a_quarter(self):
        self.assertEqual(self.label(state="in", period=2, clock="0:00",
                                    status={"completed": False, "halftime": True}), "Halftime")


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
