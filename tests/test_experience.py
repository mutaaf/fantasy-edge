"""Experience: the seats, the panel layout and the timings every client reads.

Placement is a comfort contract, not taste. A panel past 30 degrees to the side
is a sore neck by the fourth quarter, one past 33 degrees below the eye is in
the wearer's lap, and a web or Android port that lays out its own panels
would drift from the headset's. So the numbers live in tokens.json and the
seats in the scene, and this file holds them to the limits.
"""
import json
import math
import pathlib
import unittest

from fantasyedge import scene as sc

ROOT = pathlib.Path(__file__).resolve().parents[1]
TOKENS = json.loads((ROOT / "design" / "tokens.json").read_text())
EXPERIENCE = TOKENS["visual"]["experience"]


def below_degrees(slot: dict) -> float:
    return math.degrees(math.atan2(-slot["height"], slot["distance"]))


class Seats(unittest.TestCase):
    def setUp(self):
        self.stadium = sc.PRESENTATION["stadium"]
        self.seats = {s["id"]: s for s in self.stadium["seats"]}

    def test_every_preset_the_picker_offers_exists_once(self):
        ids = [s["id"] for s in self.stadium["seats"]]
        self.assertEqual(len(ids), len(set(ids)))
        for sid in ("club", "field", "endzone", "upper", "sideline", "clubLevel", "pressBox"):
            self.assertIn(sid, self.seats)
        self.assertIn(self.stadium["defaultSeat"], self.seats)

    def test_the_look_dev_shots_still_find_their_seats(self):
        src = (ROOT / "apple/FantasyEdge/Sources/Stadium/Actors/Experience/StadiumShots.swift").read_text()
        body = src.split("// SHOTS-BEGIN", 1)[1].split("// SHOTS-END", 1)[0]
        for used in set(__import__("re").findall(r'seat: "(\w+)"', body)):
            self.assertIn(used, self.seats, f"a shot sits in {used!r}, which the scene no longer offers")

    def test_a_seat_sits_on_a_row_and_faces_the_field(self):
        for s in self.stadium["seats"]:
            with self.subTest(seat=s["id"]):
                self.assertGreaterEqual(s["y"], 0.0)
                facing = (s["lookAt"]["x"] - s["x"], s["lookAt"]["z"] - s["z"])
                self.assertGreater(math.hypot(*facing), 10.0, "a seat must face somewhere on the field")
                outside = abs(s["z"]) > 80 / 3 or s["x"] < -10 or s["x"] > 110
                self.assertTrue(outside, "a seat on the playing surface")

    def test_every_seat_carries_the_preview_a_picker_shows(self):
        for s in self.stadium["seats"]:
            with self.subTest(seat=s["id"]):
                view = s["view"]
                self.assertIn(view["group"], ("sideline", "field", "endzone", "upper", "club", "press"))
                self.assertGreaterEqual(view["distanceYards"], 0.0)
                self.assertEqual(view["heightYards"], round(s["y"], 1))
        self.assertLess(self.seats["field"]["view"]["distanceYards"], self.seats["club"]["view"]["distanceYards"])
        self.assertGreater(self.seats["upper"]["view"]["heightYards"], self.seats["club"]["view"]["heightYards"])

    def test_the_press_box_seat_is_on_the_far_side_at_the_glass(self):
        box = sc.BOWL["pressBox"]
        seat = self.seats["pressBox"]
        self.assertLess(seat["z"], 0.0)
        self.assertEqual(seat["y"], box["rise"][0])
        self.assertGreaterEqual(seat["x"], box["fromX"])
        self.assertLessEqual(seat["x"], box["toX"])


class Layout(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.built = sc.build({})
        cls.layout = cls.built["visual"]["experience"]["layout"]
        cls.seats = cls.built["presentation"]["stadium"]["seats"]
        cls.by_id = {s["id"]: s for s in cls.seats}
        cls._views = {}

    def view(self, seat):
        """What the dock is solved against, recomputed here from the scene."""
        if seat["id"] not in self._views:
            eye = EXPERIENCE["camera"]["eyeMeters"]
            mpy = self.built["presentation"]["stadium"]["metersPerYard"]
            bowl, field = self.built["bowl"], self.built["field"]
            self._views[seat["id"]] = {
                "field": sc.field_silhouette(seat, field, eye, mpy),
                "painted": sc.field_silhouette(seat, field, eye, mpy, grow=sc.painted_border(field)),
                "board": sc.video_board_points(seat, bowl["videoBoard"], eye, mpy),
                "ribbon": sc.ribbon_points(seat, field, bowl["ribbon"], eye, mpy),
                "rim": sc.rim_points(seat, bowl["mounts"], eye, mpy),
                "near": sc.near_occluders(seat, bowl["shape"], bowl["seating"], eye, mpy),
            }
        return self._views[seat["id"]]

    def dock_places(self):
        """Every (seat, panel, folded, slot, size) the app can draw."""
        sizes = self.layout["panelSizes"]
        for seat in self.seats:
            per = self.layout["perSeat"][seat["id"]]
            self.assertEqual(set(per) - {"scorebugHidden", "rail"}, {"drive", "trailing", "controls"})
            for name in ("drive", "trailing", "controls"):
                if per[name]["clear"]:
                    yield seat, name, False, per[name], sizes[name]
                yield seat, name, True, per[name]["tab"], sizes["tab"]

    def test_every_panel_is_inside_the_comfort_limits(self):
        layout = EXPERIENCE["layout"]
        for name, slot in layout["slots"].items():
            with self.subTest(slot=name):
                self.assertLessEqual(abs(slot["yaw"]), layout["maxSideDegrees"])
                self.assertLessEqual(below_degrees(slot), layout["maxBelowDegrees"])
                self.assertGreater(slot["distance"], 0.5, "closer than half a metre is inside the arm")

    def test_the_side_panels_sit_below_the_scorebug_and_clear_the_centre(self):
        slots = EXPERIENCE["layout"]["slots"]
        self.assertEqual(slots["drive"]["yaw"], -slots["trailing"]["yaw"], "the two side panels mirror")
        self.assertGreater(abs(slots["drive"]["yaw"]), 20.0, "a side panel near the centre covers the play")
        # Below the near sideline's sightline from the default seat: about 20
        # degrees down from row 24, 11 m up, 22 m back.
        self.assertGreater(below_degrees(slots["drive"]), 20.0)
        self.assertGreater(below_degrees(slots["controls"]), below_degrees(slots["drive"]))
        self.assertGreater(slots["scorebug"]["height"], 0.0)

    def test_targets_and_timings_are_ones_a_wearer_can_use(self):
        self.assertGreaterEqual(EXPERIENCE["controls"]["targetPoints"], 60.0)
        self.assertGreaterEqual(EXPERIENCE["seatPicker"]["dotPoints"], 60.0)
        self.assertGreaterEqual(EXPERIENCE["controls"]["autoHideSeconds"], 4.0, "controls that vanish mid-reach")
        panels = EXPERIENCE["panels"]
        self.assertLessEqual(panels["momentFadeSeconds"], 1.0)
        self.assertGreaterEqual(panels["momentReturnSeconds"], 0.0)
        self.assertGreater(panels["elsewhereRows"], 0)
        arrival = EXPERIENCE["arrival"]
        self.assertLessEqual(arrival["gateSeconds"], 2.5, "a gate longer than that is a loading screen")
        self.assertLess(arrival["tabletopDim"], 1.0)
        layout = EXPERIENCE["layout"]
        self.assertLess(layout["restOpacity"], layout["hoverOpacity"])

    def test_the_tabletop_scales_inside_its_volume(self):
        t = EXPERIENCE["tabletop"]
        self.assertLess(t["minScale"], t["maxScale"])
        self.assertLessEqual(t["maxScale"], 1.0, "scaled past 1 the bowl is clipped by the volume")
        self.assertLessEqual(t["closerTiltDegrees"], 30.0)

    def test_the_whole_two_deck_bowl_fits_the_table_volume(self):
        """The table is sized for both decks on their plinth, whichever tiers
        it draws today, so turning the upper deck on never clips the model."""
        t = sc.PRESENTATION["tabletop"]
        base = EXPERIENCE["baseplate"]
        outer = (max(tier["outer"] for tier in sc.BOWL["tiers"]) + 3) * base["marginScale"] + base["bevelYards"]
        length = 2 * (60 + outer) * t["metersPerYard"]
        depth = 2 * (80 / 3 + outer) * t["metersPerYard"]
        self.assertLessEqual(length, t["volume"][0], "the plinth is wider than the volume")
        self.assertLessEqual(depth, t["volume"][2], "the plinth is deeper than the volume")
        top = max(tier["rise"][1] for tier in sc.BOWL["tiers"]) * t["metersPerYard"] + t["floor"]
        self.assertLessEqual(top, t["volume"][1] / 2, "the upper deck pokes out of the top of the volume")
        self.assertGreaterEqual(t["floor"] - base["thicknessMeters"], -t["volume"][1] / 2)
        self.assertGreaterEqual(120 * t["metersPerYard"], 0.45, "a field under 45 cm is too small to read a drive on")

    def test_the_win_probability_horizon_stays_inside_the_table(self):
        """Placement contract for Broadcast's horizon: on the table it sits
        inside the volume, behind the far stands and no higher than the
        volume's top, never floating over the room."""
        t = sc.PRESENTATION["tabletop"]
        h = sc.PRESENTATION["horizon"]
        self.assertLessEqual(abs(h["z"]) * t["metersPerYard"], t["volume"][2] / 2)
        self.assertLessEqual(h["y1"] * t["metersPerYard"] + t["floor"], t["volume"][1] / 2)

    def test_no_open_panel_covers_the_field_from_any_seat(self):
        """From every preset, every place a panel can be drawn - open, and
        folded to its tab or pill - sits inside the comfort limits and off the
        field's projected silhouette and the video board. The pressBox drive
        log used to sit over the play, and the upper deck's pill on the fifty."""
        for seat, name, folded, slot, size in self.dock_places():
            with self.subTest(seat=seat["id"], panel=name, folded=folded):
                self.assertLessEqual(abs(slot["yaw"]), self.layout["maxSideDegrees"])
                self.assertLessEqual(below_degrees(slot), self.layout["maxBelowDegrees"] + 1e-6)
                box = sc.panel_box(slot, size, self.layout["pointsPerMeter"])
                self.assertFalse(sc.box_overlaps(box, self.view(seat)["field"]), f"covers the field from {seat['id']}")
                self.assertFalse(sc.points_in_box(box, self.view(seat)["board"]), f"covers the video board from {seat['id']}")

    def test_nothing_in_the_dock_overlaps_the_paint(self):
        """The painted field is the keep-off region, not the playing surface:
        from the field seat the Elsewhere tab sat low over the 6 ft white
        border, and read as lying on it through integration-12 and -13,
        however much nearer than the paint it really was."""
        for seat, name, folded, slot, size in self.dock_places():
            with self.subTest(seat=seat["id"], panel=name, folded=folded):
                box = sc.panel_box(slot, size, self.layout["pointsPerMeter"])
                self.assertFalse(sc.box_overlaps(box, self.view(seat)["painted"]),
                                 f"{name} overlaps the paint from {seat['id']}")

    def test_the_paint_test_sees_a_panel_on_the_border(self):
        """The check itself: from the field seat the old rail height is over
        the border but off the playing surface, so only the painted outline
        catches it."""
        seat = self.by_id["field"]
        size = self.layout["panelSizes"]["tab"]
        ppm = self.layout["pointsPerMeter"]
        old = {"yaw": 24.0, "distance": 1.25, "height": -1.25 * math.tan(math.radians(26.0))}
        box = sc.panel_box(old, size, ppm)
        self.assertFalse(sc.box_overlaps(box, self.view(seat)["field"]))
        self.assertTrue(sc.box_overlaps(box, self.view(seat)["painted"]))

    def test_no_panel_is_half_out_of_view(self):
        """Two rules, not one. Where a panel sits is comfort: its centre inside
        ±maxSideDegrees, never lower than maxBelowDegrees. How much of it can
        be seen is the second: the whole box, edges and all, inside
        viewWindowDegrees and under the window's top. integration-13 caught the
        drive log cut in two by the frame edge in redzone-trails."""
        layout = self.layout
        window = layout["dock"]["viewWindowDegrees"]
        self.assertGreater(window, layout["maxSideDegrees"], "a view window inside the comfort window clips every panel")
        for seat, name, folded, slot, size in self.dock_places():
            with self.subTest(seat=seat["id"], panel=name, folded=folded):
                y0, y1, b0, b1 = sc.panel_box(slot, size, layout["pointsPerMeter"])
                self.assertLessEqual(abs(slot["yaw"]), layout["maxSideDegrees"] + 1e-6, "sits outside the comfort window")
                self.assertGreaterEqual(y0, -window - 1e-6, "half out of view on the left")
                self.assertLessEqual(y1, window + 1e-6, "half out of view on the right")
                self.assertLessEqual(b1, layout["maxBelowDegrees"] + 1e-6, "hangs below the window")
                self.assertGreaterEqual(b0, layout["dock"]["highestBelowDegrees"] - 1e-6, "climbs above the window")

    def test_a_thin_band_costs_rows_before_it_costs_type_size(self):
        """Where a band is too thin for the full panel the dock shortens it -
        the home 30's pair, whose right side the ribbon dips into - and the app
        clamps the panel to the seat's own height. Type size is the last thing
        to go."""
        short = {(seat["id"], name): per
                 for seat in self.seats
                 for name, per in self.layout["perSeat"][seat["id"]].items()
                 if name in ("drive", "trailing") and "maxHeightPoints" in per}
        self.assertTrue(short, "no seat needs a shortened panel; the case is untested")
        for (sid, name), per in short.items():
            with self.subTest(seat=sid, panel=name):
                full = self.layout["panelSizes"][name]["maxHeightPoints"]
                self.assertLess(per["maxHeightPoints"], full)
                self.assertGreaterEqual(per["maxHeightPoints"],
                                        full * self.layout["dock"]["gallery"]["minHeightFraction"] - 1e-6)
                self.assertEqual(per.get("scale", 1.0), 1.0, "shortened and shrunk; rows come first")
        src = (ROOT / "apple/FantasyEdge/Sources/Stadium/Actors/Experience/StadiumViews.swift").read_text()
        self.assertIn("slot?.maxHeightPoints", src, "the app ignores the seat's own panel height")

    def test_a_panel_drawn_smaller_is_still_legible(self):
        """A panel with nowhere its own size fits may shrink, but only to
        gallery.minScale: past that the list it carries stops being readable
        from the seat."""
        for seat in self.seats:
            per = self.layout["perSeat"][seat["id"]]
            for name in ("drive", "trailing", "controls"):
                with self.subTest(seat=seat["id"], panel=name):
                    scale = per[name].get("scale", 1.0)
                    near_capped = per[name]["distance"] < self.layout["dock"]["gallery"]["minDistance"] - 1e-6
                    if not near_capped:
                        self.assertGreaterEqual(scale, self.layout["dock"]["gallery"]["minScale"] - 1e-6)
                    # However it was scaled, it subtends no less than it would
                    # full size at the gallery's furthest.
                    subtends = scale / per[name]["distance"]
                    self.assertGreaterEqual(subtends, 1.0 / self.layout["dock"]["gallery"]["maxDistance"] - 1e-6)

    def test_the_painted_border_matches_fields_rule_book(self):
        """PAINTED_BORDER is Field's, read from its rule book."""
        import re
        rules = (ROOT / "tools/blender/field/rules.py").read_text()
        nfl = re.search(r'"boundary": \{"kind": "border", "width": (\d+) \* FT\}', rules)
        self.assertTrue(nfl, "the NFL boundary is no longer a border of whole feet")
        self.assertAlmostEqual(sc.PAINTED_BORDER["nfl"], int(nfl.group(1)) / 3)
        college = re.search(r'"boundary": \{"kind": "line", "width": (\d+) \* IN', rules)
        self.assertTrue(college, "the college boundary is no longer a line of whole inches")
        self.assertAlmostEqual(sc.PAINTED_BORDER["college-football"], int(college.group(1)) / 36)

    def test_nothing_in_the_dock_covers_the_ribbon_or_a_light_bank(self):
        """The ribbon used to be a cost a panel could pay: from the club seat the
        drive log sat across it through a field goal, and from the upper deck
        and the press box the Elsewhere tab hung among the rim light banks.
        Both are hard rules now, open and folded."""
        for seat, name, folded, slot, size in self.dock_places():
            with self.subTest(seat=seat["id"], panel=name, folded=folded):
                box = sc.panel_box(slot, size, self.layout["pointsPerMeter"])
                self.assertFalse(sc.points_in_box(box, self.view(seat)["ribbon"]), f"covers the ribbon from {seat['id']}")
                self.assertFalse(sc.points_in_box(box, self.view(seat)["rim"]), f"covers a light bank from {seat['id']}")

    def test_nothing_in_the_dock_stands_past_something_near_it(self):
        """A panel further out than a chair back, an aisle rail, the ground or
        the press box glass it overlaps is drawn through it: the sideline
        seat's Elsewhere tab read as lying on the chair in front. Every place
        is nearer than whatever solid thing shares its box."""
        for seat, name, folded, slot, size in self.dock_places():
            with self.subTest(seat=seat["id"], panel=name, folded=folded):
                box = sc.panel_box(slot, size, self.layout["pointsPerMeter"])
                inside = [d for y, b, d in self.view(seat)["near"] if box[0] <= y <= box[1] and box[2] <= b <= box[3]]
                if inside:
                    self.assertLess(slot["distance"], min(inside), f"stands past something near from {seat['id']}")
                self.assertGreaterEqual(slot["distance"], self.layout["dock"]["minDistance"] - 1e-6)
                self.assertLessEqual(slot.get("scale", 1.0), 1.0)

    def test_every_panel_has_a_clear_place_from_every_seat(self):
        """The dock finds room for every panel, open, from all seven presets -
        none has to start folded for want of a place. Guards the search's
        reach as well as its rules."""
        for seat in self.seats:
            for name in ("drive", "trailing", "controls"):
                with self.subTest(seat=seat["id"], panel=name):
                    self.assertTrue(self.layout["perSeat"][seat["id"]][name]["clear"])

    def test_the_rail_is_one_line_under_its_panels(self):
        """The tabs and the pill stand on one line at one height, the pill in
        the middle and each side tab on its own panel's side, so what is
        always there reads as one anchored thing rather than three strays."""
        rail = self.layout["dock"]["rail"]
        for seat in self.seats:
            per = self.layout["perSeat"][seat["id"]]
            with self.subTest(seat=seat["id"]):
                self.assertTrue(per["rail"]["clear"], "no one line holds the rail")
                tabs = [per[n]["tab"] for n in ("drive", "controls", "trailing")]
                belows = [below_degrees(t) for t in tabs]
                self.assertLess(max(belows) - min(belows), 0.05, "the rail is not one line")
                self.assertEqual([t["yaw"] for t in tabs], [-rail["sideYawDegrees"], 0.0, rail["sideYawDegrees"]])
                self.assertLess(per["drive"]["yaw"], 0.0)
                self.assertGreater(per["trailing"]["yaw"], 0.0)

    def test_a_folded_panel_is_drawn_at_its_tab_not_at_its_open_place(self):
        """The bug behind the floating tabs: the app placed each attachment once
        per seat, so a folded panel's tab sat at the middle of where the panel
        would open. The scene now carries both, and the app draws the one that
        matches the fold."""
        per = self.layout["perSeat"]["upper"]
        self.assertNotEqual((per["trailing"]["tab"]["yaw"], per["trailing"]["tab"]["height"]),
                            (per["trailing"]["yaw"], per["trailing"]["height"]))
        src = (ROOT / "apple/FantasyEdge/Sources/Stadium/Actors/Experience/StadiumViews.swift").read_text()
        body = src.split("private func placeDock", 1)[1].split("\n    }\n", 1)[0]
        for folded in ("driveFolded", "trailingFolded", "controlsFolded"):
            self.assertIn(folded, body, f"the dock ignores {folded}")
        self.assertIn("place(folded:", body)
        self.assertIn("e.scale", body)

    def test_open_panels_and_the_rail_never_overlap_each_other(self):
        """What can be on screen at once never overlaps: an open side panel and
        the pill or the other tab, the open controls and either side, open
        or folded."""
        ppm = self.layout["pointsPerMeter"]
        sizes = self.layout["panelSizes"]
        for seat in self.seats:
            per = self.layout["perSeat"][seat["id"]]
            box = lambda slot, size: sc.panel_box(slot, size, ppm)
            tabs = {n: box(per[n]["tab"], sizes["tab"]) for n in ("drive", "trailing", "controls")}
            opened = {n: box(per[n], sizes[n]) for n in ("drive", "trailing", "controls")}
            pairs = [("drive", opened["drive"], tabs["controls"]), ("drive", opened["drive"], tabs["trailing"]),
                     ("trailing", opened["trailing"], tabs["controls"]), ("trailing", opened["trailing"], tabs["drive"]),
                     ("controls", opened["controls"], tabs["drive"]), ("controls", opened["controls"], tabs["trailing"]),
                     ("controls", opened["controls"], opened["drive"]), ("controls", opened["controls"], opened["trailing"]),
                     ("drive", opened["drive"], opened["trailing"])]
            for name, a, b in pairs:
                with self.subTest(seat=seat["id"], panel=name):
                    self.assertFalse(sc._boxes_overlap(a, b), f"{name} overlaps another dock element from {seat['id']}")

    def test_near_geometry_sees_the_press_box_glass_and_the_rows_in_front(self):
        """The near check itself: from the press box the glass is under a metre
        ahead, so a panel at the old 1.25 m stood outside the window; from the
        club seat the chair backs in front are there, low."""
        glass = [d for y, b, d in self.view(self.by_id["pressBox"])["near"] if abs(y) < 5 and 0 < b < 20]
        self.assertTrue(glass)
        self.assertLess(max(glass), 1.2)
        self.assertGreater(min(glass), 0.8)
        chairs = self.view(self.by_id["club"])["near"]
        self.assertTrue(any(abs(y) < 30 and b > 30 and d < 2.5 for y, b, d in chairs), "no chair backs ahead of the club seat")
        ground = self.view(self.by_id["field"])["near"]
        self.assertTrue(ground and all(b > 0 for _, b, _ in ground))

    def test_near_numbers_match_the_bowl_kit(self):
        """NEAR's chair, rail and press box numbers are Bowl's, read from its kit."""
        import re
        structure = (ROOT / "tools/blender/bowl/structure.py").read_text()
        seat = (ROOT / "tools/blender/bowl/seat.py").read_text()
        self.assertAlmostEqual(float(re.search(r"RAIL_H = ([\d.]+)", structure).group(1)), sc.NEAR["railYards"])
        self.assertIn("cant = 0.7", structure)
        self.assertAlmostEqual(sc.NEAR["pressCantYards"], 0.7)
        room = re.search(r"PRESS_ROOM = \{([^}]*)\}", structure).group(1)
        self.assertIn(f'"deskFront": {sc.NEAR["pressDeskFrontYards"]}', room)
        self.assertIn(f'"deskDepth": {sc.NEAR["pressDeskDepthYards"]}', room)
        self.assertIn(f'"deskTop": {sc.NEAR["pressSillYards"]}', room)
        self.assertIn("y0 + 0.6", structure)
        # The seat back rises from 0.47 m by 0.37 m (seat.py back surface).
        self.assertIn("y = 0.47 + 0.37 * v", seat)
        self.assertAlmostEqual(sc.NEAR["chairBackYards"] * 0.9144, 0.84)

    def test_the_board_test_sees_a_panel_over_the_board(self):
        """From behind the home end zone the board is dead ahead a little
        above the eye: a panel there covers it, and one low at the side does not."""
        built = sc.build({})
        seat = next(s for s in built["presentation"]["stadium"]["seats"] if s["id"] == "endzone")
        eye = EXPERIENCE["camera"]["eyeMeters"]
        board = sc.video_board_points(seat, built["bowl"]["videoBoard"], eye, 0.9144)
        self.assertTrue(board, "the board faces the end-zone seat")
        yaws, belows = [p[0] for p in board], [p[1] for p in board]
        size = EXPERIENCE["layout"]["panelSizes"]["drive"]
        ppm = EXPERIENCE["layout"]["pointsPerMeter"]
        mid = (min(belows) + max(belows)) / 2
        on = {"yaw": (min(yaws) + max(yaws)) / 2, "distance": 1.25, "height": -1.25 * math.tan(math.radians(mid))}
        off = {"yaw": -30.0, "distance": 1.25, "height": -0.5}
        self.assertTrue(sc.points_in_box(sc.panel_box(on, size, ppm), board))
        self.assertFalse(sc.points_in_box(sc.panel_box(off, size, ppm), board))
        behind = {"x": 200.0, "y": 20.0, "z": 0.0, "lookAt": {"x": 50.0, "y": 0.0, "z": 0.0}}
        self.assertEqual(sc.video_board_points(behind, built["bowl"]["videoBoard"], eye, 0.9144), [])

    def test_the_silhouette_test_sees_a_panel_over_the_field(self):
        """The overlap check itself: the old fixed drive slot from the press box
        is over the field, and a panel high above the eye is not."""
        seat = next(s for s in sc.PRESENTATION["stadium"]["seats"] if s["id"] == "pressBox")
        field = sc.RULES["nfl"]["field"]
        eye = EXPERIENCE["camera"]["eyeMeters"]
        poly = sc.field_silhouette(seat, field, eye, 0.9144)
        size = EXPERIENCE["layout"]["panelSizes"]["drive"]
        low = {"yaw": -20.0, "distance": 1.25, "height": -0.5}
        high = {"yaw": -30.0, "distance": 1.25, "height": 0.6}
        ppm = EXPERIENCE["layout"]["pointsPerMeter"]
        self.assertTrue(sc.box_overlaps(sc.panel_box(low, size, ppm), poly))
        self.assertFalse(sc.box_overlaps(sc.panel_box(high, size, ppm), poly))

    def test_the_glass_scorebug_yields_where_the_video_board_carries_the_score(self):
        """Behind the home end zone the board faces the wearer, dead ahead and
        wide: the glass scorebug would sit on it. From the sidelines it is off
        to the side, and from behind the board it is not in view at all."""
        per = sc.build({})["visual"]["experience"]["layout"]["perSeat"]
        self.assertTrue(per["endzone"]["scorebugHidden"])
        for sid in ("club", "field", "upper", "sideline", "clubLevel", "pressBox"):
            self.assertFalse(per[sid]["scorebugHidden"], sid)
        board = sc.BOWL["videoBoard"]
        behind = {"x": 200.0, "y": 20.0, "z": 0.0, "lookAt": {"x": 50.0, "y": 0.0, "z": 0.0}}
        self.assertFalse(sc.board_carries_score(behind, board, EXPERIENCE["layout"]["scorebugYield"]))

    def test_panel_heights_are_a_contract_a_renderer_can_read(self):
        sizes = EXPERIENCE["layout"]["panelSizes"]
        for name in ("drive", "trailing", "controls", "tab"):
            self.assertGreater(sizes[name]["maxHeightPoints"], 0)
            self.assertGreater(sizes[name]["widthPoints"], 0)
        self.assertGreaterEqual(sizes["tab"]["maxHeightPoints"], 60.0, "a folded tab is a 60-point target")

    def test_the_scene_carries_the_experience_tokens(self):
        built = sc.build({})
        carried = {k: v for k, v in built["visual"]["experience"]["layout"].items() if k != "perSeat"}
        self.assertEqual(carried, EXPERIENCE["layout"])
        self.assertEqual([s["id"] for s in built["presentation"]["stadium"]["seats"]],
                         [s["id"] for s in sc.PRESENTATION["stadium"]["seats"]])


if __name__ == "__main__":
    unittest.main()
