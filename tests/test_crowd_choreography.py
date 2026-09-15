"""The side that was scored on never celebrates (integration-9).

Runs apple/verify_crowd.swift, which sweeps CrowdChoreography - the crowd's
pure pose decision - over both scorers, touchdown and field goal, every cue
Moments can send, surge, ring, wave, third-down stand and reduce motion.
Skipped where swiftc is unavailable.
"""
import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("swiftc"), "swiftc not available")
class CrowdChoreographyTest(unittest.TestCase):
    def test_the_scored_on_side_never_celebrates(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = pathlib.Path(tmp) / "verify-crowd"
            build = subprocess.run(
                ["swiftc", "-parse-as-library", "-o", str(exe),
                 str(ROOT / "apple/FantasyEdge/Sources/Stadium/Actors/Crowd/CrowdChoreography.swift"),
                 str(ROOT / "apple/verify_crowd.swift")], capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stderr[-2000:])
            run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=120)
            self.assertEqual(run.returncode, 0, run.stdout[-3000:])
            self.assertIn("OK", run.stdout)

    def test_the_actor_decides_through_the_choreography(self):
        src = (ROOT / "apple/FantasyEdge/Sources/Stadium/Actors/Crowd/CrowdActor.swift").read_text()
        self.assertIn("CrowdChoreography.pose(", src)
        self.assertNotIn("case .groan: pose = groan", src, "a standing groan reads as cheering")


if __name__ == "__main__":
    unittest.main()
