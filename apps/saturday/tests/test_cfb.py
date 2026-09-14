"""The college parsers and the wall ordering, against recorded fixtures."""
from __future__ import annotations

import json
import pathlib
import unittest

from cfb import colors, leverage, parse
from cfb.game import game_from_summary
from cfb.league import RULES, scoreboard_url

FIX = pathlib.Path(__file__).parent / "fixtures"
OSU_TEX, WAKE_PUR, OKST_ORE, CLEMSON = "401856682", "401858224", "401856782", "401858219"


def load(name):
    return json.loads((FIX / name).read_text())


class League(unittest.TestCase):
    def test_scoreboard_asks_for_fbs(self):
        self.assertIn("groups=80", scoreboard_url())
        self.assertIn("college-football", scoreboard_url())

    def test_college_rules_differ_from_the_nfl(self):
        self.assertEqual(RULES["hash_from_sideline_yd"], 20.0)
        self.assertEqual(RULES["ot_start_yards_to_goal"], 25)
        self.assertEqual(RULES["ot_two_point_only_from"], 3)


class Slate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.games = {g["id"]: g for g in parse.slate_records(load("slate.json"))}

    def test_every_fbs_event_is_read(self):
        self.assertEqual(len(self.games), 86)

    def test_spotlight_game_mid_drive_in_the_red_zone(self):
        g = self.games[OSU_TEX]
        self.assertEqual((g["away"]["abbr"], g["away"]["rank"], g["home"]["abbr"], g["home"]["rank"]), ("OSU", 1, "TEX", 4))
        self.assertEqual((g["away"]["score"], g["home"]["score"]), (10, 0))
        self.assertEqual(g["situation"]["text"], "3rd & 6 at TEX 17")
        self.assertEqual(g["situation"]["yardsToGoal"], 17)
        self.assertTrue(g["flags"]["redZone"])

    def test_yards_to_goal_counts_from_the_side_the_ball_is_on(self):
        self.assertEqual(parse.yards_to_goal("1st & 10 at OSU 19", "OSU"), 81)
        self.assertEqual(parse.yards_to_goal("2nd & Goal at FLA 1", "CAM"), 1)
        self.assertEqual(parse.yards_to_goal("1st & 10 at 50", "OSU"), 50)
        self.assertIsNone(parse.yards_to_goal(None, "OSU"))

    def test_overtime_final_is_complete_without_an_end_of_game_play(self):
        g = self.games[WAKE_PUR]
        self.assertTrue(g["status"]["completed"])
        self.assertEqual(g["status"]["overtimes"], 2)
        self.assertTrue(g["flags"]["overtime"])
        self.assertEqual((g["away"]["score"], g["home"]["score"]), (38, 36))

    def test_unranked_beating_ranked_is_an_upset(self):
        g = self.games[OKST_ORE]
        self.assertTrue(g["flags"]["upset"])
        self.assertEqual(g["away"]["rank"], 6)

    def test_ranked_beating_unranked_is_not(self):
        alabama = next(g for g in self.games.values() if g["away"]["abbr"] == "ALA")
        self.assertFalse(alabama["flags"]["upset"])

    def test_two_unranked_teams_cannot_upset_each_other(self):
        self.assertFalse(self.games[WAKE_PUR]["flags"]["upset"])

    def test_upset_alert_for_ranked_team_trailing(self):
        iowa = next(g for g in self.games.values() if g["home"]["abbr"] == "IOWA")
        self.assertTrue(iowa["flags"]["upsetAlert"])

    def test_halftime_draws_no_ball(self):
        half = [g for g in self.games.values() if g["status"]["halftime"]]
        self.assertTrue(half)
        self.assertTrue(all(g["situation"] is None for g in half))

    def test_pre_game_has_no_score(self):
        pre = [g for g in self.games.values() if g["status"]["state"] == "pre"]
        self.assertTrue(pre)
        self.assertTrue(all(g["away"]["score"] is None and g["home"]["score"] is None for g in pre))


class Delayed(unittest.TestCase):
    def test_delay_is_detected_and_draws_no_ball(self):
        g = parse.slate_records(load("slate_delayed.json"))[0]
        self.assertEqual(g["id"], CLEMSON)
        self.assertTrue(g["status"]["delayed"])
        self.assertFalse(g["flags"]["live"])
        self.assertIsNone(g["situation"])


class Leverage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ordered = leverage.rank(parse.slate_records(load("slate.json")))

    def test_spotlight_is_the_ranked_red_zone_game(self):
        self.assertEqual(leverage.spotlight(self.ordered), OSU_TEX)

    def test_close_and_late_beats_scoreless_at_the_half(self):
        ids = [g["id"] for g in self.ordered]
        jvst = next(g["id"] for g in self.ordered if g["away"]["abbr"] == "JVST")
        sdsu = next(g["id"] for g in self.ordered if g["away"]["abbr"] == "SDSU")
        self.assertLess(ids.index(jvst), ids.index(sdsu))

    def test_bands_live_then_upcoming_then_final(self):
        bands = [0 if g["status"]["state"] == "in" else 1 if g["status"]["state"] == "pre" else 2 for g in self.ordered]
        self.assertEqual(bands, sorted(bands))

    def test_deterministic(self):
        again = leverage.rank(parse.slate_records(load("slate.json")))
        self.assertEqual([g["id"] for g in again], [g["id"] for g in self.ordered])
        self.assertEqual([g["leverage"]["rank"] for g in again], list(range(1, 87)))

    def test_notable_finals_lead_the_finals(self):
        finals = [g for g in self.ordered if g["status"]["state"] == "post"]
        top = {g["id"] for g in finals[:3]}
        self.assertIn(OKST_ORE, top)

    def test_sections_partition_every_game_but_the_spotlight(self):
        secs = leverage.sections(self.ordered)
        ids = [i for sec in secs for i in sec["games"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(set(ids) | {OSU_TEX}, {g["id"] for g in self.ordered})
        by = {sec["id"]: sec["games"] for sec in secs}
        jvst = next(g["id"] for g in self.ordered if g["away"]["abbr"] == "JVST")
        self.assertIn(jvst, by["closeLate"])
        self.assertEqual(by["finals"][0], OKST_ORE)

    def test_caveat_is_not_empty(self):
        self.assertTrue(leverage.CAVEAT.strip())


class Colours(unittest.TestCase):
    def test_chip_clears_white_text_contrast(self):
        for hexs in ("#CEB888", "#FFD200", "#003087", "#000000", "#FFFFFF"):
            rgb = colors._rgb(colors.chip(hexs))
            self.assertGreaterEqual(1.05 / (colors._lum(rgb) + 0.05), 4.5, hexs)

    def test_identical_golds_resolve_with_a_hatch(self):
        wake = parse.slate_records(load("slate.json"))
        g = next(x for x in wake if x["id"] == WAKE_PUR)
        self.assertTrue(g["away"]["hatch"])
        self.assertFalse(g["home"]["hatch"])


class Summary(unittest.TestCase):
    def test_live_summary(self):
        g = game_from_summary(OSU_TEX, load(f"summary_{OSU_TEX}.json"))
        self.assertFalse(g["status"]["completed"])
        self.assertEqual(g["possession"], "194")
        self.assertEqual(sum(d["current"] for d in g["drives"]), 1)
        ids = [d["id"] for d in g["drives"]]
        self.assertEqual(len(ids), len(set(ids)), "the drive in progress must not be listed twice")
        self.assertGreater(len(g["winProbability"]), 10)
        self.assertTrue(all(0 <= w["home"] <= 1 for w in g["winProbability"]))

    def test_two_overtime_final_from_its_header(self):
        g = game_from_summary(WAKE_PUR, load(f"summary_{WAKE_PUR}.json"))
        self.assertTrue(g["status"]["completed"])
        self.assertEqual(g["status"]["overtimes"], 2)
        self.assertEqual(g["lastPlay"]["type"], "Rushing Touchdown")     # no End of Game play
        self.assertIsNone(g["possession"])
        self.assertFalse(any(d["current"] for d in g["drives"]))
        last = g["scoringPlays"][-1]
        self.assertEqual((last["away"], last["home"]), (38, 36))

    def test_play_positions_are_yards_to_goal(self):
        g = game_from_summary(OKST_ORE, load(f"summary_{OKST_ORE}.json"))
        plays = [p for d in g["drives"] for p in d["plays"] if p["from"] is not None]
        self.assertTrue(plays)
        self.assertTrue(all(0 <= p["from"] <= 100 for p in plays))
        self.assertFalse(any(p["text"].startswith("(") for p in plays))


if __name__ == "__main__":
    unittest.main()
