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
        """From every preset, a panel that starts open sits outside the field's
        projected silhouette and inside the comfort limits; one that cannot
        starts folded. The pressBox drive log used to sit over the play."""
        built = sc.build({})
        layout = built["visual"]["experience"]["layout"]
        eye = EXPERIENCE["camera"]["eyeMeters"]
        mpy = built["presentation"]["stadium"]["metersPerYard"]
        seats = built["presentation"]["stadium"]["seats"]
        self.assertEqual(set(layout["perSeat"]), {s["id"] for s in seats})
        for seat in seats:
            poly = sc.field_silhouette(seat, built["field"], eye, mpy)
            for name, slot in layout["perSeat"][seat["id"]].items():
                if name == "scorebugHidden":
                    continue
                with self.subTest(seat=seat["id"], panel=name):
                    self.assertLessEqual(abs(slot["yaw"]), layout["maxSideDegrees"])
                    self.assertLessEqual(below_degrees(slot), layout["maxBelowDegrees"] + 1e-6)
                    # Open, the whole panel; folded, its tab - the upper deck's
                    # controls pill once fell back onto the fifty.
                    size = layout["panelSizes"]["tab" if slot["folded"] else name]
                    box = sc.panel_box(slot, size, layout["pointsPerMeter"])
                    self.assertFalse(sc.box_overlaps(box, poly), f"{name} covers the field from {seat['id']}")
                    board = sc.video_board_points(seat, built["bowl"]["videoBoard"], eye, mpy)
                    self.assertFalse(sc.points_in_box(box, board), f"{name} covers the video board from {seat['id']}")

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
