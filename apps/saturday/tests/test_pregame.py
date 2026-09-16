"""The state a Saturday starts in: every game scheduled, nothing played yet.

A recorded night never contains it, so these run against a real week-3 board
captured on the Tuesday before (tools/make_fixtures.py, `pregame`).
"""
from __future__ import annotations

import json
import pathlib
import unittest

from api import handlers
from cfb import parse, text
from cfb.sources import FixtureSource
from schema_lite import Validator

REPO = pathlib.Path(__file__).resolve().parents[1]
FIX = REPO / "tests/fixtures"
CONTRACTS = Validator(REPO / "contracts")
LSU_MISS = "401856688"
HAVE = (FIX / "slate_pregame.json").exists()


class PregameSource(FixtureSource):
    label = "fixtures-pregame"

    def __init__(self):
        self.root = FIX

    def scoreboard(self):
        return json.loads((self.root / "slate_pregame.json").read_text())

    def summary(self, event):
        path = self.root / f"summary_pregame_{event}.json"
        return json.loads(path.read_text()) if path.exists() else None


@unittest.skipUnless(HAVE, "pregame capture not present")
class Pregame(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = PregameSource()
        cls.slate = handlers.slate(cls.src)

    def test_slate_matches_contract_with_nothing_played(self):
        self.assertEqual(CONTRACTS.validate(self.slate, "slate.schema.json"), [])
        self.assertEqual(self.slate["counts"]["live"], 0)
        self.assertEqual(self.slate["counts"]["post"], 0)
        self.assertGreater(self.slate["counts"]["pre"], 60)
        self.assertIsNone(self.slate["spotlight"], "no game is live, so nothing is the big game")
        self.assertEqual(self.slate["changes"], [])
        self.assertEqual(self.slate["feed"], [])

    def test_every_game_is_in_coming_up_and_nowhere_else(self):
        sections = {s["id"]: s["games"] for s in self.slate["sections"]}
        self.assertEqual(sorted(sections["upcoming"]), sorted(g["id"] for g in self.slate["games"]))
        self.assertEqual(sum(len(v) for k, v in sections.items() if k != "upcoming"), 0)

    def test_coming_up_is_in_kickoff_order(self):
        """A schedule reads by time. Ranked-first would put the 8 PM marquee
        game above the noon kickoff people are about to watch."""
        kickoffs = [g["kickoff"] for g in self.slate["games"]]
        self.assertEqual(kickoffs, sorted(kickoffs))

    def test_kickoff_labels_are_eastern_and_carry_the_day(self):
        labels = [g["kickoffLabel"] for g in self.slate["games"]]
        self.assertTrue(all(l.endswith(" ET") or l.endswith("TBA") for l in labels), labels[:3])
        self.assertTrue(all(l[:3] in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun") for l in labels))
        self.assertEqual(text.kickoff_label("2026-09-19T23:30Z"), "Sat 7:30 PM ET")
        self.assertEqual(text.kickoff_label("2026-09-19T16:00Z"), "Sat 12:00 PM ET")
        self.assertEqual(text.kickoff_label("2026-09-19T16:00Z", False), "Sat TBA",
                         "a time ESPN has not fixed is never drawn as a real kickoff")

    def test_tiles_have_what_a_pre_game_tile_draws(self):
        for g in self.slate["games"]:
            self.assertIsNone(g["away"]["score"])
            self.assertIsNone(g["situation"], "no ball on the field before kickoff")
            self.assertIsNone(g["lastPlay"])
            self.assertTrue(g["venue"]["name"])
            self.assertTrue(g["away"]["record"] and g["home"]["record"])
        self.assertTrue(all(g["tv"] for g in self.slate["games"]), "every week-3 game had a network")

    def test_a_scheduled_game_has_no_box_score_only_season_averages(self):
        """ESPN's pre-game boxscore is each team's season per-game averages.
        Drawn as this game's totals it reads 586 yards before kickoff."""
        out = handlers.game(self.src, LSU_MISS)
        self.assertEqual(CONTRACTS.validate(out, "game.schema.json"), [])
        self.assertEqual(out["status"]["state"], "pre")
        self.assertEqual(out["boxscore"], [])
        self.assertEqual(len(out["seasonAverages"]), 2)
        self.assertIn("Points Per Game", [s["label"] for s in out["seasonAverages"][0]["stats"]])
        self.assertEqual((out["drives"], out["scoringPlays"], out["winProbability"]), ([], [], []))
        self.assertIsNone(out["lastPlay"])
        self.assertIsNone(out["possession"])

    def test_ranks_survive_the_board(self):
        ranked = [g for g in self.slate["games"] if g["flags"]["ranked"]]
        self.assertGreater(len(ranked), 15)
        ranks = {r for g in self.slate["games"] for r in (g["away"]["rank"], g["home"]["rank"]) if r}
        self.assertEqual(ranks, set(range(1, 26)), "all 25 ranked teams are on a week's board")

    def test_short_names_and_chips_are_there_before_kickoff(self):
        for g in self.slate["games"]:
            for side in (g["away"], g["home"]):
                self.assertTrue(side["shortName"])
                self.assertRegex(side["fill"], r"^#[0-9A-F]{6}$")


@unittest.skipUnless(HAVE, "pregame capture not present")
class PregameRecords(unittest.TestCase):
    def test_a_scheduled_game_scores_zero_not_none_on_espn(self):
        board = json.loads((FIX / "slate_pregame.json").read_text())
        raw = [c.get("score") for ev in board["events"] for c in ev["competitions"][0]["competitors"]]
        self.assertEqual(set(raw), {"0"}, "ESPN sends 0, and a tile must not show it as a score")
        for g in parse.slate_records(board):
            self.assertIsNone(g["away"]["score"])


if __name__ == "__main__":
    unittest.main()
