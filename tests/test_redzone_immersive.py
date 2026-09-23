"""The immersive red-zone channel: the rules the Swift side has to keep.

The ranking is `whip.py`'s and is tested in `test_whip.py`. What is tested
here is the half that only exists in the headset - that moving the stadium
from one game to another repaints rather than rebuilds, that it fades rather
than cuts, and that the league still comes from the feed - which is checked by
reading the sources, the way `test_moment_timing.py` already holds the
composer's timing rules. A rendered check for the same thing lives in
`apple/verify_scene.swift` (`a venue is the building`) and in
`tools/measure_changeover.py`, which times it on a simulator.
"""

import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
STADIUM = ROOT / "packages" / "swift" / "StadiumKit" / "Sources" / "StadiumKit"
SOURCES = ROOT / "apple" / "FantasyEdge" / "Sources"

VENUE = (STADIUM / "StadiumVenue.swift").read_text()
RENDERER = (STADIUM / "StadiumRenderer.swift").read_text()
CROWD = (STADIUM / "Actors" / "Crowd" / "CrowdActor.swift").read_text()
EXPERIENCE = (STADIUM / "Actors" / "Experience" / "ExperienceActor.swift").read_text()
FEED = (STADIUM / "SceneFeed.swift").read_text()
CHANNEL = (SOURCES / "RedZoneChannel.swift").read_text()
API = (ROOT / "fantasyedge" / "api.py").read_text()


class VenueTest(unittest.TestCase):
    """A venue is the building; a livery is whose colours it wears."""

    def test_the_venue_holds_no_club_colour(self):
        """The four crowd colours, the section tint and the painted club names
        change on every switch and move no geometry. If one reaches the venue,
        every switch rebuilds the stand and the channel becomes a slideshow."""
        body = VENUE.split("init(_ s: SceneSpec)")[1].split("static func livery(")[0]
        # Whole names: `crowd.awaySection` is where the visiting block sits,
        # which is the building, while `crowd.away` is the colour in it.
        for club in ("s.bowl.crowd.home", "s.bowl.crowd.away", "s.bowl.crowd.neutral",
                     "s.bowl.crowd.dark", "s.bowl.sectionTint", "s.field.art",
                     "s.teams"):
            self.assertIsNone(re.search(re.escape(club) + r"\b", body),
                              f"{club} is livery, not building")

    def test_the_livery_holds_no_geometry(self):
        body = VENUE.split("static func livery(")[1]
        for geometry in ("length", "hashFromSideline", "seating", "tiers", "seats"):
            self.assertNotIn(f"s.field.{geometry}", body)
            self.assertNotIn(f"s.bowl.{geometry}", body)

    def test_the_league_is_part_of_the_building(self):
        """College hash marks are far wider than the NFL's, so the same bowl
        under a different league is a different building and must rebuild."""
        self.assertIn("league = s.league", VENUE)

    def test_the_renderer_rebuilds_on_venue_and_repaints_on_livery(self):
        body = RENDERER.split("private func apply(")[1].split("\n    private func")[0]
        self.assertIn("StadiumVenue(next)", body)
        self.assertIn("StadiumVenue.livery(next)", body)
        self.assertIn("actor.relivery(c)", body,
                      "a livery change must repaint rather than build")
        self.assertRegex(body, r"if venue != builtVenue \{\s*\n\s*build\(c\)",
                         "a venue change must still rebuild")


class RepaintTest(unittest.TestCase):
    """The crowd is the reason any of this matters: placing forty thousand
    fans is three seconds and none of it depends on who is playing."""

    def test_the_crowd_repaints_without_replacing_its_fans(self):
        body = CROWD.split("func relivery(")[1].split("\n    private func redress")[0]
        self.assertIn("redress(", body, "a new matchup is a texture swap")
        self.assertNotIn("placed.append", body, "relivery must not place fans again")

    def test_the_crowd_still_rebuilds_when_the_seat_moves(self):
        """Rings are measured from the wearer and every card turns to face
        them, so a different seat really is different geometry."""
        body = CROWD.split("func relivery(")[1].split("\n    private func redress")[0]
        self.assertIn("build(c); return", body)
        self.assertIn("simd_distance(seat, key)", body)

    def test_an_actor_that_says_nothing_rebuilds(self):
        """The default is correct-but-slow rather than fast-but-wrong: an
        actor gains nothing by staying silent, and loses nothing either."""
        protocol = (STADIUM / "Actors" / "StadiumActor.swift").read_text()
        self.assertIn("func relivery(_ c: StadiumContext) { build(c) }", protocol)


class ChangeoverTest(unittest.TestCase):
    """Comfort: the world fades, the wearer never moves."""

    def test_a_new_game_fades_rather_than_cuts(self):
        body = RENDERER.split("private func apply(")[1].split("\n    private func")[0]
        self.assertIn("next.event != shown.event", body)
        self.assertIn("beginChangeover", body)

    def test_reduce_motion_and_the_tabletop_are_not_faded(self):
        body = EXPERIENCE.split("func beginChangeover(")[1].split("\n    var changingOver")[0]
        self.assertIn("!c.tabletop, !c.reduceMotion", body)
        self.assertIn("return false", body, "the caller swaps at once instead")

    def test_the_swap_happens_where_nothing_can_be_seen(self):
        body = EXPERIENCE.split("private func updateChangeover(")[1].split("\n    ///")[0]
        self.assertIn("ch.swap()", body)
        self.assertIn("if ch.elapsed < half", body,
                      "the swap belongs at the dark middle, not at either end")

    def test_the_wearer_is_never_moved(self):
        """A changeover writes opacity and nothing else. Moving the world
        about somebody's head is what makes people ill."""
        body = EXPERIENCE.split("private func updateChangeover(")[1].split("\n    ///")[0]
        written = set(re.findall(r"c\.world\.(\w+)", body))
        self.assertEqual(written - {"components"}, set(),
                         "a changeover may fade the world, never move it")

    def test_a_live_switch_keeps_the_old_scene_until_the_new_one_lands(self):
        """Blanking the spec tears the stadium down and rebuilds it in view."""
        body = FEED.split("public var target: Target?")[1].split("@ObservationIgnored")[0]
        self.assertIn("if case .live = target, case .live = oldValue {} else { spec = nil }", body)

    def test_a_poll_in_flight_cannot_overwrite_the_game_it_was_left_for(self):
        body = FEED.split("public func refresh()")[1].split("\n    // MARK")[0]
        self.assertIn("let asked = target", body)
        self.assertIn("guard asked == self.target else { return }", body)


class ChannelTest(unittest.TestCase):
    def test_the_ranking_is_not_reimplemented_in_swift(self):
        """`whip.py` owns it: one copy, in the language the recording harness
        can test, and one answer for every screen in the room."""
        self.assertIn("/api/redzone", CHANNEL)
        for ported in ("SWITCH_MARGIN", "MIN_DWELL", "urgency", "hysteresis "):
            self.assertNotIn(ported, CHANNEL.split("public func refresh")[0].split("///")[0])

    def test_a_pin_outranks_the_channel_but_not_a_final(self):
        body = CHANNEL.split("public var wanted: String {")[1].split("\n    public func")[0]
        self.assertIn("live == true", body,
                      "a pinned game that ended must not strand the wearer on a final")

    def test_the_scene_takes_its_league_from_the_feed(self):
        """A constant here draws a college Saturday with NFL hash marks.

        This asserted on `league=self.live_league()` until the league audit
        landed a better answer for the same bug: the league is a fact about
        the *game*, so `scene.build` reads it from the payload and a mixed
        slate cannot be wrong about one of its games. What must never come
        back is the constant, so that is what is pinned - by behaviour rather
        than by the spelling of a call, which is what made this brittle.
        """
        body = API.split("def scene(self, event: str)")[1].split("def ")[0]
        self.assertNotIn('league="nfl"', body)

        from fantasyedge import scene as sc
        college = {"header": {"league": {"abbreviation": "NCAAF"}}}
        self.assertEqual(sc.league_of(college), "college-football",
                         "the game's own payload must decide its league")


if __name__ == "__main__":
    unittest.main()
