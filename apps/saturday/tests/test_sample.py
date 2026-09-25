"""A capture whose live snapshots were sampled must say so, not look complete.

19 September's per-game snapshots came to 92 MB across 54 games. Six games are
in git - the ones the recorder's own leverage rule watched most - and the rest
stay on disk. A fresh clone therefore has the boards, the finals and those six,
and everything has to keep working from exactly that.
"""
from __future__ import annotations

import datetime as dt
import gzip
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))

import backfill_slate  # noqa: E402
import merge_capture  # noqa: E402
from api import handlers  # noqa: E402
from cfb.sources import CaptureSource, FixtureSource  # noqa: E402
from schema_lite import Validator  # noqa: E402

CAPTURE = REPO / "data/capture/2026-09-19"
CONTRACTS = Validator(REPO / "contracts")
HAVE = (CAPTURE / "scoreboard").is_dir()


def tracked(path: pathlib.Path) -> list[str]:
    out = subprocess.run(["git", "ls-files", str(path.relative_to(REPO))],
                         cwd=REPO, capture_output=True, text=True, timeout=60)
    return [line for line in out.stdout.splitlines() if line]


class Declares(unittest.TestCase):
    """The three answers a source can give about one game's play-by-play."""

    def setUp(self):
        self.root = pathlib.Path(tempfile.mkdtemp())
        board = {"events": [], "capturedAt": "20260919T220000Z"}
        (self.root / "scoreboard").mkdir(parents=True)
        with gzip.open(self.root / "scoreboard" / "20260919T220000Z.json.gz", "wt") as f:
            json.dump(board, f)
        for kind, event in (("live", "1"), ("final", "2")):
            if kind == "live":
                (self.root / "live" / event).mkdir(parents=True)
                with gzip.open(self.root / "live" / event / "20260919T220000Z.json.gz", "wt") as f:
                    json.dump({"header": {}}, f)
            else:
                (self.root / "final").mkdir(parents=True, exist_ok=True)
                with gzip.open(self.root / "final" / f"{event}.json.gz", "wt") as f:
                    json.dump({"header": {}}, f)
        self.src = CaptureSource(self.root, "20260919T220000Z")

    def test_kept_game_answers_now(self):
        self.assertEqual(self.src.detail_for("1", "in"), "available")

    def test_dropped_game_with_a_final_answers_only_at_the_end(self):
        self.assertEqual(self.src.detail_for("2", "in"), "afterFinal")
        self.assertEqual(self.src.detail_for("2", "post"), "available")

    def test_a_game_with_nothing_kept_says_so(self):
        self.assertEqual(self.src.detail_for("3", "in"), "unavailable")

    def test_a_live_source_can_always_ask(self):
        self.assertEqual(FixtureSource(REPO / "tests/fixtures").detail_for("1", "in"), "available")


@unittest.skipUnless(HAVE, "capture not present")
class FromTheCommittedTreeAlone(unittest.TestCase):
    """Build a tree of only what git tracks, and use it."""

    @classmethod
    def setUpClass(cls):
        cls.root = pathlib.Path(tempfile.mkdtemp()) / "2026-09-19"
        files = tracked(CAPTURE)
        if not files:
            raise unittest.SkipTest("capture is not committed yet")
        for name in files:
            src = REPO / name
            dst = cls.root / pathlib.Path(name).relative_to("data/capture/2026-09-19")
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        cls.kept = sorted(p.name for p in (cls.root / "live").glob("*") if p.is_dir())

    def test_a_fresh_clone_gets_the_boards_the_finals_and_six_games(self):
        self.assertGreater(len(list((self.root / "scoreboard").glob("*.json.gz"))), 500)
        self.assertEqual(len(list((self.root / "final").glob("*.json.gz"))), 74)
        self.assertEqual(len(self.kept), 6, self.kept)
        self.assertTrue((self.root / "live" / "README.md").exists(), "the sample explains itself")

    def test_the_night_still_replays(self):
        src = CaptureSource(self.root, "99999999T999999Z")
        self.assertGreater(len(src.frames()), 500)
        out = handlers.slate(src)
        self.assertEqual(CONTRACTS.validate(out, "slate.schema.json"), [])
        self.assertEqual(out["counts"]["post"], 75)

    def test_a_kept_game_opens_mid_game(self):
        src = CaptureSource(self.root, "20260919T230000Z")
        kept = self.kept[0]
        out = handlers.game(src, kept)
        self.assertEqual(CONTRACTS.validate(out, "game.schema.json"), [])
        self.assertTrue(out["drives"], "the snapshots that were kept still carry the game")

    def test_a_dropped_game_says_why_rather_than_looking_complete(self):
        """The failure a sample must not have: a tile that looks live and then
        opens onto nothing, with no way to tell a sampled capture from a bug."""
        at = "20260919T230000Z"
        src = CaptureSource(self.root, at)
        slate = handlers.slate(src)
        live = [g for g in slate["games"] if g["status"]["state"] == "in"]
        dropped = [g for g in live if g["detail"] == "afterFinal"]
        self.assertTrue(dropped, "at 7 PM some live game's snapshots were not kept")
        self.assertTrue(all(g["id"] not in self.kept for g in dropped))
        with self.assertRaises(handlers.NotFound) as caught:
            handlers.game(src, dropped[0]["id"])
        self.assertIn("did not keep this game's snapshots", caught.exception.reason)
        self.assertIn("final", caught.exception.reason)

    def test_a_dropped_game_is_whole_again_once_it_is_final(self):
        """Nothing is actually lost: the final carries every play, and the
        rebuild can put any moment of it back."""
        src = CaptureSource(self.root, "99999999T999999Z")
        slate = handlers.slate(src)
        dropped = next(g for g in slate["games"]
                       if g["id"] not in self.kept and g["status"]["state"] == "post")
        self.assertEqual(dropped["detail"], "available")
        out = handlers.game(src, dropped["id"])
        self.assertTrue(out["drives"])
        self.assertTrue(out["status"]["completed"])

    def test_every_kept_game_is_one_the_recorder_watched_most(self):
        """The sample is the recorder's own rule, not a hand-picked six."""
        readme = (self.root / "live" / "README.md").read_text()
        for event in self.kept:
            self.assertIn(event, readme)
            self.assertIn(f"({event}) |", readme)


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(HAVE, "capture not present")
class RebuildsWhatIsNotStored(unittest.TestCase):
    """The backfill's frames are derived, so they are not in git. A clone has
    the summaries they are built from, and has to be able to build them."""

    @classmethod
    def setUpClass(cls):
        cls.root = pathlib.Path(tempfile.mkdtemp())
        for folder in (CAPTURE, REPO / "data/capture/2026-09-19-backfill"):
            names = tracked(folder)
            if not names:
                raise unittest.SkipTest(f"{folder.name} is not committed yet")
            for name in names:
                src, dst = REPO / name, cls.root / name
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
        cls.capture = cls.root / "data/capture/2026-09-19"
        cls.backfill = cls.root / "data/capture/2026-09-19-backfill"

    def test_a_clone_has_the_summaries_but_not_the_frames(self):
        self.assertFalse((self.backfill / "scoreboard").exists(), "frames are derived, not stored")
        self.assertEqual(len(list((self.backfill / "summary").glob("*.json.gz"))), 74)
        self.assertTrue((self.backfill / "reference-board.json.gz").exists())

    def test_the_frames_rebuild_and_the_night_replays_from_them(self):
        """One command's worth of work, then the merged night end to end. A
        coarser grid than the committed build: the point is that it rebuilds,
        not that a test spends a minute reproducing 572 frames."""
        board = backfill_slate.load(self.backfill / "reference-board.json.gz")
        backfill_slate.build_frames(self.backfill, board, dt.date(2026, 9, 19),
                                    backfill_slate.first_recorded_stamp(self.capture), every=600)
        self.assertGreater(len(list((self.backfill / "scoreboard").glob("*.json.gz"))), 20)

        merged = self.root / "merged"
        report = merge_capture.merge(self.capture, self.backfill, merged)
        self.assertEqual(report["frames"]["recorded"], 557)
        self.assertEqual(report["frames"]["reconstructedDropped"], 0)

        src = CaptureSource(merged, "99999999T999999Z")
        stamps = src.frames()
        self.assertEqual(stamps[0][:8], "20260918", "the night still starts on the Friday")
        self.assertEqual(stamps[-1], "20260920T064612Z", "and ends on the closing board")
        first = handlers.slate(src.at(stamps[0]))
        self.assertEqual(CONTRACTS.validate(first, "slate.schema.json"), [])
        self.assertIsNotNone(first["reconstructed"], "the rebuilt hours still say they were rebuilt")
        last = handlers.slate(src.at(stamps[-1]))
        self.assertIsNone(last["reconstructed"], "the recorded hours still say they were recorded")
        self.assertEqual(last["counts"]["post"], 75)
