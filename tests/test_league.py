"""Both codes over the same path.

The stadium was built against an NFL fixture and the Saturday app is college
only, so every league difference had exactly one side exercised. That is how
the pylons came to be wrong in both codes at once while a test that counted
them passed: the NFL was drawn with its four back corners missing and four
college hash pylons in their place, which is eight either way.

So these tests are parameterised over the leagues rather than written for one,
and they check where a thing is, not how many of it there are.
"""

import unittest

from fantasyedge import replay as rp
from fantasyedge import scene as sc

HOME = {"abbr": "MIN", "name": "Minnesota Vikings", "location": "Minnesota",
        "nickname": "Vikings", "color": "#4F2683", "id": "16"}
AWAY = {"abbr": "CHI", "name": "Chicago Bears", "location": "Chicago",
        "nickname": "Bears", "color": "#0B162A", "id": "3"}
LEAGUES = ("nfl", "college-football")


def built(league, game=None):
    return sc.build(dict(game or {"home": HOME, "away": AWAY}), league=league)


class TheLeagueComesFromTheGame(unittest.TestCase):
    """A college game drawn on an NFL field puts every play 3.58 yards off
    across, silently. The league is a property of the game, so it is read from
    the game."""

    def test_espn_says_which_league_in_its_header(self):
        for abbr, want in (("NFL", "nfl"), ("NCAAF", "college-football")):
            payload = {"header": {"league": {"abbreviation": abbr}}}
            self.assertEqual(sc.league_of(payload), want, abbr)

    def test_espn_says_which_league_in_a_uid_when_the_header_is_gone(self):
        """A gamecast keeps the uid long after it has dropped the header."""
        self.assertEqual(sc.league_of({"uid": "s:20~l:23~e:401858224"}), "college-football")
        self.assertEqual(sc.league_of({"uid": "s:20~l:28~e:401772949"}), "nfl")

    def test_a_league_stated_outright_is_taken(self):
        for league in LEAGUES:
            self.assertEqual(sc.league_of({"league": league}), league)

    def test_a_payload_that_says_nothing_falls_back_and_says_so(self):
        self.assertEqual(sc.league_of({}), "nfl")
        self.assertEqual(sc.league_of({}, default="college-football"), "college-football")
        self.assertEqual(sc.league_of(None), "nfl")

    def test_build_takes_the_league_from_the_game_when_no_one_insists(self):
        college = sc.build({"header": {"league": {"abbreviation": "NCAAF"}},
                            "home": HOME, "away": AWAY})
        self.assertEqual(college["league"], "college-football")
        self.assertEqual(college["field"]["hashFromSideline"], 20.0)

    def test_an_explicit_league_still_overrides_the_payload(self):
        """The override is what api.py uses today, and what it must stop
        using; it stays supported so a caller can force one deliberately."""
        forced = sc.build({"header": {"league": {"abbreviation": "NCAAF"}}}, league="nfl")
        self.assertEqual(forced["league"], "nfl")

    def test_an_unknown_league_is_refused_rather_than_guessed(self):
        with self.assertRaises(ValueError):
            sc.build({}, league="rugby")


class TheFieldIsTheLeaguesField(unittest.TestCase):

    def test_the_hashes_are_where_each_code_puts_them(self):
        """College hashes are 40 ft apart, the NFL's 18 ft 6 in, and both sit
        symmetrically in a 160 ft field. Every play's lateral place rides on
        this, so it is checked as a distance apart, not as a stored number."""
        for league, apart_feet in (("nfl", 18 + 6 / 12), ("college-football", 40.0)):
            f = built(league)["field"]
            apart = f["width"] - 2 * f["hashFromSideline"]
            self.assertAlmostEqual(apart, apart_feet / 3, places=2, msg=league)

    def test_the_two_codes_share_a_field_of_the_same_size(self):
        sizes = {lg: (built(lg)["field"]["length"], built(lg)["field"]["endZone"],
                      round(built(lg)["field"]["width"], 4)) for lg in LEAGUES}
        self.assertEqual(sizes["nfl"], sizes["college-football"])

    def test_the_goal_posts_are_the_same_width_and_different_heights(self):
        nfl, ncaa = (built(lg) for lg in LEAGUES)
        self.assertEqual(nfl["field"]["goalPostWidth"], ncaa["field"]["goalPostWidth"])
        self.assertAlmostEqual(nfl["field"]["props"]["goalpost"]["uprightAbove"], 35 / 3)
        self.assertAlmostEqual(ncaa["field"]["props"]["goalpost"]["uprightAbove"], 10.0)

    def test_each_league_draws_its_own_baked_markings(self):
        for league in LEAGUES:
            self.assertEqual(built(league)["field"]["markings"],
                             f"actors/field/markings/{league}")


class ThePylonsStandWhereTheBookPutsThem(unittest.TestCase):
    """Both codes put eight at the sidelines - the four front corners of the
    end zones and the four back corners. College adds four more on the end
    lines where the inbounds lines extended meet them, three feet beyond
    (NCAA 1-2-6); the NFL has none there (Rule 1 §2 Art.3).

    Counting pylons cannot see the difference: before the league audit the NFL
    had its back corners missing and college's hash pylons in the end zone
    instead, and that is eight either way.
    """

    def places(self, league):
        f = built(league)["field"]
        half, end, length = f["width"] / 2, f["endZone"], f["length"]
        hash_z = half - f["hashFromSideline"]
        out = []
        for x, z in f["props"]["pylon"]["at"]:
            line = "goal" if min(abs(x), abs(x - length)) < 0.5 else (
                "endline" if min(abs(x + end), abs(x - length - end)) < 1.5 else "?")
            across = "sideline" if abs(abs(z) - half) < 0.5 else (
                "hash" if abs(abs(z) - hash_z) < 0.5 else "?")
            out.append(f"{line} x {across}")
        return sorted(out)

    def test_both_codes_stand_one_at_every_corner_of_both_end_zones(self):
        for league in LEAGUES:
            got = self.places(league)
            self.assertEqual(got.count("goal x sideline"), 4, f"{league}: front corners")
            self.assertEqual(got.count("endline x sideline"), 4, f"{league}: back corners")
            self.assertNotIn("? x ?", got, f"{league}: a pylon on no line at all")

    def test_only_college_stands_them_on_the_hashes(self):
        self.assertEqual(self.places("college-football").count("endline x hash"), 4)
        self.assertEqual(self.places("nfl").count("endline x hash"), 0)

    def test_the_counts_are_eight_and_twelve(self):
        self.assertEqual(len(built("nfl")["field"]["props"]["pylon"]["at"]), 8)
        self.assertEqual(len(built("college-football")["field"]["props"]["pylon"]["at"]), 12)

    def test_college_stands_its_hash_pylons_three_feet_back(self):
        f = built("college-football")["field"]
        end, length = f["endZone"], f["length"]
        half_z = f["width"] / 2 - f["hashFromSideline"]
        hashes = [x for x, z in f["props"]["pylon"]["at"] if abs(abs(z) - half_z) < 0.5]
        for x in hashes:
            beyond = min(abs(x + end), abs(x - length - end))
            self.assertAlmostEqual(beyond, 1.0 + f["props"]["pylon"]["size"] / 2, places=3)

    def test_no_pylon_ever_stands_inside_the_field_of_play(self):
        for league in LEAGUES:
            f = built(league)["field"]
            for x, z in f["props"]["pylon"]["at"]:
                inside_length = 0 < x < f["length"]
                inside_width = abs(z) < f["width"] / 2
                self.assertFalse(inside_length and inside_width, f"{league}: ({x}, {z})")


class TheSidelineFurnitureFollowsTheCode(unittest.TestCase):

    def test_the_team_areas_are_each_codes_own(self):
        """NFL between the 30s (field diagram note 8), college between the 20s
        (NCAA 1-2-4-a)."""
        nfl = built("nfl")["field"]["props"]["benches"]
        ncaa = built("college-football")["field"]["props"]["benches"]
        self.assertEqual((nfl["fromX"], nfl["toX"]), (30.0, 70.0))
        self.assertEqual((ncaa["fromX"], ncaa["toX"]), (20.0, 80.0))

    def test_the_scene_says_which_code_marks_the_ground_not_the_renderer(self):
        """College lays markers on the line to gain on both sidelines and the
        NFL does not. An actor that decided this by comparing the league's
        name would have to be taught every league; it reads the answer."""
        self.assertIs(built("college-football")["field"]["props"]["chains"]["groundMarkers"], True)
        self.assertIs(built("nfl")["field"]["props"]["chains"]["groundMarkers"], False)

    def test_the_chain_crew_works_the_visitors_side_in_both(self):
        for league in LEAGUES:
            self.assertEqual(built(league)["field"]["props"]["chains"]["side"], "away")


class TheFieldIsPaintedForTheHomeClubInBothCodes(unittest.TestCase):
    """The home-club rule was written and tested against the NFL alone; it has
    to hold for a college field, whose midfield ring is bounded by the hashes
    rather than the numerals."""

    def test_both_end_zones_carry_the_home_club_in_both_codes(self):
        for league in LEAGUES:
            art = built(league)["field"]["art"]
            painted = " ".join(z["text"] for z in art["endZones"])
            self.assertIn("VIKINGS", painted, league)
            self.assertNotIn("BEARS", painted, league)
            for zone in art["endZones"]:
                self.assertEqual(zone["fill"], "home", league)

    def test_one_cap_height_serves_both_ends_in_both_codes(self):
        for league in LEAGUES:
            caps = {z["capHeight"] for z in built(league)["field"]["art"]["endZones"]}
            self.assertEqual(len(caps), 1, league)

    def test_the_midfield_ring_stays_inside_the_hashes_for_college(self):
        """NCAA 1-2-1-g-3. The NFL's is bounded by the numerals instead, so it
        is the larger of the two."""
        f = built("college-football")["field"]
        ring = f["art"]["midfield"]["outer"]
        hash_z = f["width"] / 2 - f["hashFromSideline"]
        self.assertLess(ring, hash_z, "the college ring crosses its hash marks")
        self.assertGreater(built("nfl")["field"]["art"]["midfield"]["outer"], ring)

    def test_the_longest_college_names_still_fit_a_college_end_zone(self):
        """College names run longer than the NFL's, and the end zone is the
        same ten yards deep."""
        for name in ("Southern Mississippi Golden Eagles", "Notre Dame Fighting Irish",
                     "Texas A&M Aggies", "Middle Tennessee Blue Raiders"):
            art = built("college-football",
                        {"home": {"abbr": "XX", "name": name, "color": "#4F2683"},
                         "away": AWAY})["field"]["art"]
            for zone in art["endZones"]:
                self.assertGreater(zone["capHeight"], 0.5, f"{name} lettered too small")


class TheLineToGainIsDecidedByGeometryNotByAFieldEspnOmits(unittest.TestCase):
    """ESPN sends `yardsToEndzone` on an NFL situation and never on a college
    one - 0 of 887 live college situations in a Saturday's boards carried it.
    The goal-to-go test used to read that field, so on college it was always
    absent, always "not goal to go", and a line to gain was painted on every
    goal-to-go: on the goal line itself for 1st and goal from the 5, and five
    yards inside the end zone for 2nd and 8 from the 3.

    Where the line would fall is the same question and is answerable in both
    codes, so that is what decides it now.
    """

    GAME = {"home": {"abbr": "AA", "id": "1", "color": "#123456"},
            "away": {"abbr": "BB", "id": "2", "color": "#654321"}, "state": "in"}

    def gain(self, league, situation, possession="1"):
        built = sc.build({**self.GAME, "situation": {**situation, "possession": possession}},
                         league=league)
        return [round(laser["x"], 2) for laser in built["lasers"]
                if laser["kind"] == "lineToGain"]

    def test_goal_to_go_draws_no_line_to_gain_in_either_code(self):
        for league in LEAGUES:
            for yard_line, distance in ((95, 5), (97, 8), (99, 10), (92, 20)):
                self.assertEqual(self.gain(league, {"yardLine": yard_line, "distance": distance}),
                                 [], f"{league}: {distance} to go from {yard_line}")

    def test_a_line_to_gain_is_never_painted_inside_an_end_zone(self):
        """The failure this replaces put one five yards into the end zone."""
        for league in LEAGUES:
            length = sc.RULES[league]["field"]["length"]
            for yard_line in range(1, 100):
                for distance in (1, 5, 8, 10, 15):
                    for who, side in (("1", "home"), ("2", "away")):
                        for x in self.gain(league, {"yardLine": yard_line, "distance": distance}, who):
                            self.assertGreater(x, 0.0, f"{league} {side}: line at {x}")
                            self.assertLess(x, length, f"{league} {side}: line at {x}")

    def test_an_ordinary_down_still_draws_its_line_in_either_code(self):
        for league in LEAGUES:
            self.assertEqual(self.gain(league, {"yardLine": 50, "distance": 10}), [60.0], league)
            self.assertEqual(self.gain(league, {"yardLine": 40, "distance": 2}), [42.0], league)

    def test_the_visiting_side_attacks_the_other_way(self):
        for league in LEAGUES:
            self.assertEqual(self.gain(league, {"yardLine": 50, "distance": 10}, "2"), [40.0], league)
            self.assertEqual(self.gain(league, {"yardLine": 5, "distance": 5}, "2"), [], league)

    def test_espns_own_answer_is_still_honoured_when_it_sends_one(self):
        """`yardsToEndzone` is the more direct statement where it exists, and
        it can call goal-to-go a yard before the geometry does."""
        self.assertEqual(self.gain("nfl", {"yardLine": 95, "distance": 5, "yardsToEndzone": 5}), [])
        self.assertEqual(self.gain("nfl", {"yardLine": 50, "distance": 10, "yardsToEndzone": 50}),
                         [60.0])


class AnUntimedOvertimeIsPlacedByItsPlays(unittest.TestCase):
    """College overtime is alternating possessions with no clock (NCAA 3-1-3),
    so ESPN reports the same clock on every play of it. Read literally that put
    every play of an overtime at one instant: a replay could not scrub through
    it, and "skip to the next score" landed in the fourth quarter."""

    def plays(self, period, clocks):
        return [{"period": {"number": period}, "clock": {"displayValue": c},
                 "id": f"{period}-{i}"} for i, c in enumerate(clocks)]

    def summary(self, plays):
        return {"drives": {"previous": [{"plays": plays}]}}

    def test_a_college_overtime_is_recognised_as_untimed(self):
        sm = self.summary(self.plays(5, ["0:00"] * 6))
        self.assertEqual(rp.untimed_overtimes(sm), {5})

    def test_an_nfl_overtime_runs_a_clock_and_is_left_alone(self):
        sm = self.summary(self.plays(5, ["10:00", "9:12", "8:30"]))
        self.assertEqual(rp.untimed_overtimes(sm), set())
        self.assertEqual(rp.play_offsets(sm), {})
        self.assertEqual(rp.period_lengths(sm), {5: rp.OVERTIME_SECONDS})

    def test_every_play_of_an_untimed_overtime_lands_at_its_own_second(self):
        sm = self.summary(self.plays(5, ["0:00"] * 6))
        lengths, offsets = rp.period_lengths(sm), rp.play_offsets(sm)
        secs = [rp.play_seconds(p, lengths, offsets) for p in rp._all_plays(sm)]
        self.assertEqual(len(set(secs)), 6, f"plays collapsed onto one instant: {secs}")
        self.assertEqual(secs, sorted(secs), "plays run backwards")

    def test_a_second_overtime_starts_after_the_first(self):
        sm = self.summary(self.plays(5, ["0:00"] * 6) + self.plays(6, ["0:00"] * 4))
        lengths, offsets = rp.period_lengths(sm), rp.play_offsets(sm)
        secs = [rp.play_seconds(p, lengths, offsets) for p in rp._all_plays(sm)]
        self.assertEqual(len(set(secs)), 10)
        self.assertLess(max(secs[:6]), min(secs[6:]), "the second overtime overlaps the first")

    def test_skipping_to_a_score_lands_before_it_not_in_regulation(self):
        """LEAD_SECONDS back from a scoring play has to stay inside the
        overtime; the collapse put it in the fourth quarter."""
        sm = self.summary(self.plays(5, ["0:00"] * 6))
        lengths, offsets = rp.period_lengths(sm), rp.play_offsets(sm)
        scoring = rp._all_plays(sm)[-1]
        at = rp.play_seconds(scoring, lengths, offsets) - rp.LEAD_SECONDS
        regulation = rp.PERIOD_SECONDS * rp.REGULATION_PERIODS
        self.assertGreater(at, regulation, "skip-to-score left the overtime")

    def test_regulation_is_untouched_by_any_of_it(self):
        sm = self.summary(self.plays(1, ["15:00", "14:02"]))
        self.assertEqual(rp.period_lengths(sm), {})
        self.assertEqual(rp.play_offsets(sm), {})
        self.assertEqual([rp.play_seconds(p, {}, {}) for p in rp._all_plays(sm)], [0, 58])

    def test_a_single_play_overtime_is_not_called_untimed(self):
        """One play shows one clock whatever the code, so it says nothing."""
        self.assertEqual(rp.untimed_overtimes(self.summary(self.plays(5, ["0:00"]))), set())


if __name__ == "__main__":
    unittest.main()
