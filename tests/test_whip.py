"""The red-zone channel: what it ranks first, and when it cuts away.

The fixtures here are the shapes ESPN actually sends, not the shapes the
feature would prefer. Two of them were found by measuring a whole Saturday's
captured boards and cost a rewrite: `yardsToEndzone` never appeared in a
single live situation, and `down` is 0 or -1 a quarter of the time.
"""

import unittest

from fantasyedge import whip


def game(**kw):
    """A live game, with the fields the scoreboard always sends."""
    base = {"event": "1", "state": "in", "label": "8:30 - 2nd", "played": 0.3,
            "homeScore": 7.0, "awayScore": 7.0, "redZone": False,
            "down": None, "distance": None, "toEndzone": None,
            "downDistanceText": None,
            "home": {"abbr": "HOM", "score": 7.0, "color": "", "hasBall": False},
            "away": {"abbr": "AWY", "score": 7.0, "color": "", "hasBall": False}}
    base.update(kw)
    return base


class Urgency(unittest.TestCase):
    def test_a_red_zone_game_outranks_a_close_one(self):
        """The flag is the whole point of the channel.

        The first version of this scored proximity from `yardsToEndzone` and
        ignored `isRedZone` entirely, so on a real board none of the six games
        in the red zone reached the top.
        """
        rz = whip.urgency(game(redZone=True))[0]
        close = whip.urgency(game(homeScore=20, awayScore=21, played=0.8))[0]
        self.assertGreater(rz, close)

    def test_the_flag_alone_is_enough(self):
        """ESPN's college feed sends no distance at all, so a channel that
        needs one to notice the red zone never fires."""
        value, reason = whip.urgency(game(redZone=True, toEndzone=None))
        self.assertGreater(value, 40.0)
        self.assertIn("red zone", reason)

    def test_nearer_the_line_ranks_higher(self):
        near = whip.urgency(game(redZone=True, toEndzone=2))[0]
        far = whip.urgency(game(redZone=True, toEndzone=19))[0]
        self.assertGreater(near, far)

    def test_a_finished_or_unstarted_game_is_never_urgent(self):
        self.assertEqual(whip.urgency(game(state="post"))[0], 0.0)
        self.assertEqual(whip.urgency(game(state="pre"))[0], 0.0)

    def test_a_blowout_fades_as_it_goes(self):
        early = whip.urgency(game(homeScore=35, awayScore=0, played=0.2))[0]
        late = whip.urgency(game(homeScore=35, awayScore=0, played=0.9))[0]
        self.assertGreater(early, late)

    def test_a_score_holds_its_game_for_a_moment(self):
        plain = whip.urgency(game())[0]
        just = whip.urgency(game(), scored_ago=1.0)[0]
        self.assertGreater(just, plain)
        self.assertEqual(whip.urgency(game(), scored_ago=1.0)[1], "just scored")
        # ...and lets go once the moment has passed.
        self.assertNotEqual(
            whip.urgency(game(), scored_ago=whip.SCORE_HOLD + 1)[1], "just scored")

    def test_a_reason_never_restates_the_clock(self):
        """The clock is already on screen beside the caption, so a reason that
        repeats it has said nothing - and the first version printed the down
        twice in the focus panel for exactly this reason."""
        for g in (game(), game(redZone=True, downDistanceText="4th & 7 at X 14"),
                  game(homeScore=20, awayScore=21, played=0.9)):
            reason = whip.urgency(g)[1]
            self.assertNotEqual(reason, g["label"])
            self.assertNotEqual(reason, whip.situation(g))


class ScoringPlay(unittest.TestCase):
    def test_seven_is_a_touchdown_not_an_extra_point(self):
        """The trap. A touchdown and its kick usually land in the same poll,
        and reading the total as the kick announces the wrong thing on the
        biggest play of the drive - the mistake the Saturday recorder made.
        Both were seen for real on 19 September: ARIZ 14 -> 21 in one frame,
        and PUR 7 -> 13 -> 14 across two."""
        self.assertEqual(whip.scoring_play(7), "Touchdown")
        self.assertEqual(whip.scoring_play(6), "Touchdown")
        self.assertEqual(whip.scoring_play(8), "Touchdown")
        self.assertEqual(whip.scoring_play(1), "Extra point")

    def test_the_ordinary_ones(self):
        self.assertEqual(whip.scoring_play(3), "Field goal")
        self.assertEqual(whip.scoring_play(2), "2 points")   # safety or a try

    def test_nothing_gained_is_not_a_score(self):
        self.assertEqual(whip.scoring_play(0), "")
        self.assertEqual(whip.scoring_play(-6), "")


class Situation(unittest.TestCase):
    def test_espns_own_words_win(self):
        """ESPN names the yard line; composing from down and distance cannot,
        because the distance to the end zone is not in the payload."""
        self.assertEqual(
            whip.situation(game(downDistanceText="1st & Goal at COLO 9",
                                down=1, distance=9)),
            "1st & Goal at COLO 9")

    def test_no_down_is_no_situation(self):
        """0 and -1 both mean "between plays" and were a quarter of all live
        situations across one Saturday. Either one reaching a caption puts
        "0th & 10" on screen."""
        for down in (0, -1, None):
            self.assertEqual(whip.situation(game(down=down, distance=10)), "")
            self.assertFalse(whip.has_down(game(down=down)))

    def test_composed_when_espn_is_silent(self):
        self.assertEqual(whip.situation(game(down=3, distance=7)), "3rd & 7")
        self.assertEqual(whip.situation(game(down=1, distance=5, toEndzone=5)),
                         "1st & goal at the 5")


class Choosing(unittest.TestCase):
    def rank(self, *games):
        return whip.rank(list(games), now=0.0)

    def test_it_opens_on_the_most_urgent_live_game(self):
        ranked = self.rank(game(event="a"), game(event="b", redZone=True))
        self.assertEqual(whip.choose(ranked), "b")

    def test_it_never_opens_on_a_game_that_is_not_running(self):
        """Everything is zero before kickoff, so something has to sort first -
        and a channel opening on Thursday's final is worse than one that says
        nothing is running."""
        ranked = self.rank(game(event="a", state="post"),
                           game(event="b", state="pre"))
        self.assertEqual(whip.choose(ranked), "")

    def test_it_holds_a_game_for_its_minimum(self):
        """Two red-zone drives at once would otherwise trade the screen every
        poll and show neither."""
        ranked = self.rank(game(event="a"), game(event="b", redZone=True))
        self.assertEqual(whip.choose(ranked, "a", held=1.0), "a")

    def test_a_clearly_better_game_wins_once_the_hold_expires(self):
        ranked = self.rank(game(event="a"), game(event="b", redZone=True))
        self.assertEqual(whip.choose(ranked, "a", held=whip.MIN_DWELL + 1), "b")

    def test_a_marginally_better_game_does_not(self):
        ranked = self.rank(game(event="a", redZone=True, toEndzone=9),
                           game(event="b", redZone=True, toEndzone=8))
        self.assertEqual(whip.choose(ranked, "a", held=60.0), "a")

    def test_it_leaves_a_game_that_ended(self):
        ranked = self.rank(game(event="a", state="post"), game(event="b"))
        self.assertEqual(whip.choose(ranked, "a", held=1.0), "b")


class Slate(unittest.TestCase):
    def per_club(self, **over):
        """`games()` is keyed by club, which is what the channel regroups."""
        common = {"event": "9", "state": "in", "label": "Q1", "played": 0.1,
                  "kickoff": "2026-09-20T17:00", "redZone": True,
                  "down": 1, "distance": 10, "toEndzone": None,
                  "downDistanceText": "1st & 10 at HOM 15", "possession": "AWY"}
        common.update(over)
        return {"HOM": {**common, "score": "10", "home": True},
                "AWY": {**common, "score": "13", "home": False}}

    def test_two_clubs_become_one_game(self):
        rows = whip.slate(self.per_club())
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["home"]["abbr"], "HOM")
        self.assertEqual(row["away"]["abbr"], "AWY")
        self.assertEqual(row["homeScore"], 10.0)
        self.assertTrue(row["away"]["hasBall"])
        self.assertEqual(row["situation"], "1st & 10 at HOM 15")

    def test_a_club_without_an_opponent_is_not_a_game(self):
        """A bye club carries no event, and a half-parsed one would otherwise
        reach the page as a tile with a single team in it."""
        half = {"HOM": {**self.per_club()["HOM"]}}
        self.assertEqual(whip.slate(half), [])
        self.assertEqual(whip.slate({"BYE": {"event": "", "state": "pre"}}), [])

    def test_the_league_is_carried_not_assumed(self):
        rows = whip.slate(self.per_club(league="college-football"))
        self.assertEqual(rows[0]["league"], "college-football")


if __name__ == "__main__":
    unittest.main()
