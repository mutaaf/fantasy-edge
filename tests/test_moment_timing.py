"""A moment happens when the ball lands, not when the play arrives.

The scene announces a touchdown as the play arrives; Broadcast flies that play
for about five seconds. Integration-12 measured the banner, score, strobe and
surge 5.1 s early, and gone before the return finished. The composer now holds
the moment until Broadcast has flown it.

`apple/verify_moment.swift` sweeps MomentGate - the rule itself - over landing,
timeout, re-announcement, scrubbing and replay speed. The tests here also hold
the composer and the views to using it, because a gate nobody asks is no gate.
Swift parts are skipped where swiftc is unavailable.
"""
import json
import pathlib
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
STADIUM = ROOT / "apple/FantasyEdge/Sources/Stadium"
RENDERER = (STADIUM / "StadiumRenderer.swift").read_text()
VIEWS = (STADIUM / "Actors/Experience/StadiumViews.swift").read_text()


@unittest.skipUnless(shutil.which("swiftc"), "swiftc not available")
class MomentGateSweepTest(unittest.TestCase):
    def test_the_gate_holds_until_the_play_lands(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = pathlib.Path(tmp) / "verify-moment"
            # The same files `make verify-moment` compiles: the sweep covers
            # LaidPlay too, which needs SceneSpec and the look types it decodes.
            build = subprocess.run(
                ["swiftc", "-parse-as-library", "-o", str(exe),
                 str(STADIUM / "MomentGate.swift"),
                 str(STADIUM / "LaidPlay.swift"),
                 str(STADIUM / "SceneSpec.swift"),
                 str(STADIUM / "SceneLook.swift"),
                 *[str(p) for p in sorted((STADIUM / "Actors").glob("*/*Look.swift"))],
                 str(STADIUM / "Actors/Field/FieldArtSpec.swift"),
                 str(ROOT / "apple/verify_moment.swift")], capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stderr[-2000:])
            run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=120)
            self.assertEqual(run.returncode, 0, run.stdout[-3000:])
            self.assertIn("OK", run.stdout)


class ComposerTest(unittest.TestCase):
    """The composer is the only place a moment may be dispatched from."""

    def test_the_moment_waits_for_the_ball(self):
        self.assertIn("gate.arrive(", RENDERER)
        self.assertIn("gate.due(", RENDERER)
        self.assertIn("broadcast.hasTrail", RENDERER)

    def test_the_hold_is_released_on_the_frame_clock(self):
        tick = RENDERER.split("public func tick(")[1]
        self.assertIn("releaseMoment(c)", tick,
                      "a moment held on arrival is only ever released by the frame clock")

    def test_nothing_dispatches_a_moment_around_the_gate(self):
        for line in RENDERER.splitlines():
            if "actor.moment(.moment(" in line:
                self.assertIn("private func fire", RENDERER)
        body = RENDERER.split("private func fire(")[1]
        self.assertIn("actor.moment(.moment(m), c)", body.split("private func")[0])
        self.assertEqual(RENDERER.count("actor.moment(.moment("), 1,
                         "one place fires a moment, so one place can hold it")

    def test_the_stats_counts_are_timed_from_the_moment_not_the_arrival(self):
        fire = RENDERER.split("private func fire(")[1].split("private func")[0]
        self.assertIn("statsDue +=", fire,
                      "mid-moment budgets must be counted from when the moment fires")

    def test_a_moment_scrubbed_away_is_dropped(self):
        dispatch = RENDERER.split("private func dispatchEvents(")[1].split("private func")[0]
        self.assertIn("gate.clear()", dispatch)

    def test_the_views_follow_the_stadium_not_the_scene(self):
        self.assertIn("renderer.liveMoment", VIEWS)
        self.assertNotIn("of: feed.spec?.activeMoment", VIEWS,
                         "the panels would yield five seconds before the ball lands")


class DrawnScoreTest(unittest.TestCase):
    """The score, the down and the red-zone flag lag the scene by one play.

    A scene carries the state after its newest play, and Broadcast then flies
    that play for seconds: integration-13 read CHI 17 on the board with the
    return still running. `StatusGate` holds the arriving status behind that
    play, and `apple/verify_moment.swift` sweeps the rule itself.
    """

    BANNER = (STADIUM / "Actors/Broadcast/BroadcastBanner.swift").read_text()
    BROADCAST = (STADIUM / "Actors/Broadcast/BroadcastActor.swift").read_text()

    def test_the_composer_holds_the_status_behind_the_ball(self):
        self.assertIn("StatusGate<SceneSpec.Status>", RENDERER)
        self.assertIn("status.hold(", RENDERER)
        self.assertIn("status.due(", RENDERER)

    def test_the_status_catches_up_on_the_frame_clock(self):
        tick = RENDERER.split("public func tick(")[1]
        self.assertIn("releaseStatus(c)", tick,
                      "the score must be able to change with no new scene, the frame the ball lands")
        self.assertLess(tick.index("releaseStatus(c)"), tick.index("releaseMoment(c)"),
                        "the banner carries the score, so the score catches up first")

    def test_catching_up_redraws_the_boards(self):
        body = RENDERER.split("private func releaseStatus(")[1].split("\n    private func")[0]
        self.assertIn("actor.apply(c", body,
                      "the boards draw in apply, so a score that changes between scenes must re-apply")

    def test_the_actors_are_handed_the_shown_status(self):
        # The apply that does the work, not the one-line public wrapper in
        # front of it: the wrapper exists so a changeover can re-enter this
        # with `swapping: true` once the world is dark.
        apply = RENDERER.split("private func apply(")[1].split("\n    private func")[0]
        self.assertIn("showing(next", apply)
        self.assertIn("spec: shown", apply,
                      "actors draw the stadium's status, never the scene's")

    def test_only_the_status_lags_the_scene(self):
        body = RENDERER.split("private func showing(")[1].split("\n    private func")[0]
        self.assertIn("s.status = status.shown", body)
        written = set(re.findall(r"^\s*s\.(\w+)\s*=", body, re.M))
        self.assertEqual(written, {"status"},
                         "a scene is held back by its status alone; its plays arrive as they are")

    def test_the_glass_agrees_with_the_board(self):
        self.assertEqual(VIEWS.count("SceneScorebug(spec:"), 2)
        for line in VIEWS.splitlines():
            if "SceneScorebug(spec:" in line:
                self.assertIn("status: renderer.shownStatus", line,
                              "the glass scorebug and the video board must show one score")

    def test_the_banner_comes_down_before_the_next_snap(self):
        self.assertIn("banner.snapping(c)", self.BROADCAST,
                      "a TOUCHDOWN slab still up over the kickoff belongs to a play the board has left")
        self.assertIn("func snapping(", self.BANNER)

    def test_a_quick_snap_shortens_the_banner_rather_than_flashing_it(self):
        body = self.BANNER.split("func snapping(")[1].split("\n    private func")[0]
        self.assertIn("minSeconds", body)
        self.assertIn("max(floor", body)


class DriveLogTest(unittest.TestCase):
    """The drive log lists plays the viewer has seen land.

    The last consumer to run ahead of the ball: the log named the play in the
    air, and the drive's result with it, beside a score correctly waiting for
    it. The composer publishes `shownDrive` beside `shownStatus`, and the log
    reads that.
    """

    BOARD = (STADIUM / "Actors/Broadcast/BroadcastVideoBoard.swift").read_text()
    LAID = (STADIUM / "LaidPlay.swift").read_text()

    def test_the_composer_publishes_the_drive_the_views_may_list(self):
        self.assertIn("public private(set) var shownDrive", RENDERER)
        self.assertIn("LaidPlay.through(", RENDERER)

    def test_the_log_reads_the_composers_answer(self):
        code = [l for l in VIEWS.splitlines() if not l.lstrip().startswith("//")]
        self.assertNotIn("spec.shownDrive", "\n".join(code),
                         "the log would list a play still in the air")
        for line in VIEWS.splitlines():
            if "DriveLog(spec:" in line:
                self.assertIn("drive: renderer.shownDrive", line,
                              "every caller names where the drive came from")

    def test_the_actors_still_see_the_play_that_has_not_landed(self):
        """Broadcast learns of a play from the spec it is handed, and flies it.

        Truncating the drive for the actors would mean the newest play never
        arrived, so it would never fly, so it would never land: the log would
        be right and the field empty. The holding is for the views alone.
        """
        body = RENDERER.split("private func showing(")[1].split("\n    private func")[0]
        written = set(re.findall(r"^\s*s\.(\w+)\s*=", body, re.M))
        self.assertEqual(written, {"status"})

    def test_one_rule_for_the_board_and_the_log(self):
        self.assertIn("LaidPlay.newest(", self.BOARD,
                      "the board and the log must not each carry their own idea of newest")
        self.assertNotIn("import UIKit", self.LAID,
                         "the rule lives where the sweeps can compile it")

    def test_a_held_play_takes_its_result_with_it(self):
        body = self.LAID.split("public static func through(")[1]
        self.assertIn('result: ""', body,
                      'a header reading "Touchdown" over a ball in flight is the same defect')


class TokensTest(unittest.TestCase):
    def test_the_banner_floor_is_a_token(self):
        tokens = json.loads((ROOT / "design/tokens.json").read_text())
        floor = tokens["visual"]["moments"]["banner"]["minSeconds"]
        dwell = tokens["visual"]["moments"]["banner"]["dwellSeconds"]
        self.assertGreater(floor, 0)
        self.assertLess(floor, dwell, "a floor above the dwell would keep every banner up longer")
        self.assertIn("minSeconds", (STADIUM / "Actors/Moments/MomentsLook.swift").read_text())

    def test_the_grace_is_a_token_not_a_constant(self):
        tokens = json.loads((ROOT / "design/tokens.json").read_text())
        grace = tokens["motion"]["momentHoldGraceSeconds"]
        self.assertGreater(grace, 0)
        self.assertLessEqual(grace, 3, "a long grace is a long wrong celebration")
        self.assertIn("momentHoldGraceSeconds", (STADIUM / "SceneSpec.swift").read_text())

    def test_the_scene_carries_the_grace_to_every_client(self):
        import sys
        sys.path.insert(0, str(ROOT))
        from fantasyedge import scene as sc
        motion = sc.load_tokens()["motion"]
        self.assertIn("momentHoldGraceSeconds", motion)


if __name__ == "__main__":
    unittest.main()
