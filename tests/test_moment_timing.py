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
            build = subprocess.run(
                ["swiftc", "-parse-as-library", "-o", str(exe),
                 str(STADIUM / "MomentGate.swift"),
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


class TokensTest(unittest.TestCase):
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
