"""Rebuilding a night from play wallclocks, and merging it with a recording.

The real fixture is Georgia at Arkansas from 19 September 2026: a noon
kickoff, wire to wire, 178 plays, 177 of them stamped. The ordering test uses
a play list built by hand, because the failure it guards against - a stamp two
hours out - is rare enough that no single game is a reliable example of it.
"""
from __future__ import annotations

import datetime as dt
import gzip
import json
import pathlib
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))

import merge_capture  # noqa: E402
import verify_reconstruction as verify  # noqa: E402
from api import handlers  # noqa: E402
from cfb import parse, reconstruct  # noqa: E402
from cfb.sources import CaptureSource  # noqa: E402
from schema_lite import Validator  # noqa: E402

FIX = REPO / "tests/fixtures"
CONTRACTS = Validator(REPO / "contracts")
UGA_ARK = "401856686"
HAVE = (FIX / f"summary_wallclock_{UGA_ARK}.json").exists()


def at(hhmm: str) -> dt.datetime:
    """A time on 19 September 2026, UTC."""
    return dt.datetime.fromisoformat(f"2026-09-19T{hhmm}:00+00:00")


def play(number: int, period: int, wallclock: str | None, away=0, home=0, text="Rush") -> dict:
    return {"id": str(number), "wallclock": wallclock, "period": {"number": period},
            "clock": {"displayValue": "10:00"}, "awayScore": away, "homeScore": home,
            "text": text, "type": {"text": text},
            "start": {"down": 1, "distance": 10, "yardLine": 30, "yardsToEndzone": 70,
                      "downDistanceText": "1st & 10 at UGA 30", "team": {"id": "61"}}}


class Ordering(unittest.TestCase):
    def test_a_stamp_from_two_hours_later_does_not_reorder_the_game(self):
        """Buffalo at Penn State carried a third-quarter play stamped after the
        game ended. Sorting by wallclock put that play last and the board read
        a two-touchdown-old score as the final."""
        plays = [play(1, 1, "2026-09-19T16:00:00Z"), play(2, 1, "2026-09-19T16:02:00Z"),
                 play(3, 3, "2026-09-19T20:30:00Z", away=6, home=48),      # wrong by two hours
                 play(4, 4, "2026-09-19T18:00:00Z", away=13, home=55)]
        summary = {"drives": {"previous": [{"plays": plays}]}}
        timed = reconstruct.timed_plays(summary)
        self.assertEqual([p["id"] for _, p in timed], ["1", "2", "3", "4"], "ESPN's order is the game's order")
        stamps = [w for w, _ in timed]
        self.assertEqual(stamps, sorted(stamps), "times are monotone")
        self.assertEqual(timed[-1][1]["homeScore"], 55, "the last play is the last play")

    def test_a_missing_stamp_is_placed_between_its_neighbours(self):
        plays = [play(1, 1, "2026-09-19T16:00:00Z"), play(2, 1, None), play(3, 1, "2026-09-19T16:04:00Z")]
        timed = reconstruct.timed_plays({"drives": {"previous": [{"plays": plays}]}})
        self.assertEqual(len(timed), 3)
        self.assertEqual(timed[1][0], at("16:02"))

    def test_the_drive_in_progress_is_not_counted_twice(self):
        current = {"id": "9", "plays": [play(5, 2, "2026-09-19T17:00:00Z")]}
        summary = {"drives": {"previous": [{"id": "9", "plays": [play(5, 2, "2026-09-19T17:00:00Z")]}],
                              "current": current}}
        self.assertEqual(len(reconstruct.timed_plays(summary)), 1)


@unittest.skipUnless(HAVE, "wallclock capture not present")
class RealGame(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.summary = json.loads((FIX / f"summary_wallclock_{UGA_ARK}.json").read_text())
        cls.event = json.loads((FIX / "board_reference.json").read_text())["events"][0]
        cls.timed = reconstruct.timed_plays(cls.summary)

    def test_the_night_is_a_timeline_not_just_a_result(self):
        self.assertGreater(len(self.timed), 150)
        stamps = [w for w, _ in self.timed]
        self.assertEqual(stamps, sorted(stamps))
        span = reconstruct.covered_span({UGA_ARK: self.summary})
        self.assertEqual(span[0].strftime("%H:%M"), "16:05", "a noon kickoff in ET")
        self.assertGreater((span[1] - span[0]).total_seconds(), 3 * 3600)

    def test_before_the_first_play_it_is_the_schedule_not_a_rebuild(self):
        out = reconstruct.game_at(self.event, self.summary, at("15:00"))
        self.assertEqual(reconstruct.provenance_of(out), "schedule")
        record = parse.game_record(out)
        self.assertEqual(record["status"]["state"], "pre")
        self.assertIsNone(record["away"]["score"])
        self.assertIsNone(record["situation"])

    def test_mid_game_it_is_the_score_and_the_ball_at_that_moment(self):
        out = reconstruct.game_at(self.event, self.summary, at("17:00"))
        self.assertEqual(reconstruct.provenance_of(out), "reconstructed")
        record = parse.game_record(out)
        self.assertEqual(record["status"]["state"], "in")
        self.assertIn(record["status"]["period"], (1, 2))
        played = [p for w, p in self.timed if w <= at("17:00")]
        self.assertEqual(record["home"]["score"], int(played[-1]["homeScore"]))
        self.assertEqual(record["away"]["score"], int(played[-1]["awayScore"]))

    def test_the_break_between_halves_draws_no_ball(self):
        """Halftime is the gap between the last play of the second period and
        the first of the third - inferred, and only where ESPN's periods say."""
        second = [w for w, p in self.timed if (p["period"] or {}).get("number") == 2]
        third = [w for w, p in self.timed if (p["period"] or {}).get("number") == 3]
        middle = second[-1] + (third[0] - second[-1]) / 2
        record = parse.game_record(reconstruct.game_at(self.event, self.summary, middle))
        self.assertTrue(record["status"]["halftime"])
        self.assertIsNone(record["situation"], "no ball on the field during the band")

    def test_after_the_last_play_it_is_final_with_the_final_score(self):
        record = parse.game_record(reconstruct.game_at(self.event, self.summary, at("23:00")))
        self.assertEqual(record["status"]["state"], "post")
        self.assertTrue(record["status"]["completed"])
        self.assertEqual((record["away"]["score"], record["home"]["score"]), (45, 17))

    def test_a_score_lands_in_the_minute_it_happened(self):
        scoring = [(w, p) for w, p in self.timed if p.get("scoringPlay")]
        if not scoring:
            self.skipTest("no scoring play flagged in this summary")
        when, first = scoring[0]
        before = parse.game_record(reconstruct.game_at(self.event, self.summary, when - dt.timedelta(seconds=30)))
        after = parse.game_record(reconstruct.game_at(self.event, self.summary, when + dt.timedelta(seconds=1)))
        self.assertLess(before["away"]["score"] + before["home"]["score"],
                        after["away"]["score"] + after["home"]["score"])


@unittest.skipUnless(HAVE, "wallclock capture not present")
class Boards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reference = json.loads((FIX / "board_reference.json").read_text())
        cls.events = {str(ev["id"]): ev for ev in cls.reference["events"]}
        cls.summaries = {UGA_ARK: json.loads((FIX / f"summary_wallclock_{UGA_ARK}.json").read_text())}

    def board(self, when):
        return reconstruct.board_at(self.reference, self.events, self.summaries, when)

    def test_a_rebuilt_board_says_so_in_its_own_payload(self):
        board = self.board(at("17:00"))
        self.assertEqual(board["saturdayProvenance"]["kind"], "reconstructed")
        self.assertTrue(board["saturdayProvenance"]["caveats"])
        self.assertEqual(board["capturedAt"], "20260919T170000Z")
        self.assertEqual([reconstruct.provenance_of(ev) for ev in board["events"]], ["reconstructed"])

    def test_the_slate_carries_the_provenance_and_the_caveats(self):
        class Board(CaptureSource):
            replay = True
            label = "rebuilt"

            def __init__(self, board):
                self.board = board

            def scoreboard(self):
                return self.board

            def stamp(self):
                return self.board["capturedAt"]

            def frames(self):
                return []

            def history(self, seconds):
                return [(self.stamp(), lambda: self.board)]

            def summary(self, event):
                return None

        out = handlers.slate(Board(self.board(at("17:00"))))
        self.assertEqual(CONTRACTS.validate(out, "slate.schema.json"), [])
        self.assertEqual(out["games"][0]["provenance"], "reconstructed")
        self.assertEqual(out["reconstructed"]["games"], 1)
        self.assertTrue(out["reconstructed"]["caveats"])

    def test_a_recorded_board_is_never_marked_reconstructed(self):
        recorded = json.loads((FIX / "slate.json").read_text())
        for record in parse.slate_records(recorded):
            self.assertEqual(record["provenance"], "recorded")
        out = handlers.slate(__import__("cfb.sources", fromlist=["FixtureSource"]).FixtureSource(FIX))
        self.assertIsNone(out["reconstructed"])

    def test_frames_are_only_minutes_in_which_something_was_played(self):
        instants = reconstruct.frame_instants(self.summaries, 60.0)
        self.assertGreater(len(instants), 100)
        self.assertLess(len(instants), 250, "one game's frames, not a sweep of the whole day")
        self.assertEqual(instants, sorted(instants))
        stop = at("17:00")
        self.assertTrue(all(i <= stop for i in reconstruct.frame_instants(self.summaries, 60.0, stop)))


class KnownLimits(unittest.TestCase):
    """The rebuild differs from the board in three understood ways, all of them
    the same thing: ESPN's play feed leads its own scoreboard."""

    def row(self, recorded, rebuilt):
        return {"recorded": recorded, "rebuilt": rebuilt}

    def test_a_touchdown_carries_its_extra_point(self):
        # WKU at Indiana, 20:51:14Z: the board said 6, the play already said 7.
        self.assertEqual(verify.classify(self.row(("in", 0, 6), ("in", 0, 7))), "playFeedAheadOfBoard")
        self.assertEqual(verify.classify(self.row(("in", 24, 14), ("in", 24, 21))), "playFeedAheadOfBoard")

    def test_a_game_starts_at_its_first_play(self):
        self.assertEqual(verify.classify(self.row(("pre", None, None), ("in", 0, 0))), "startsAtItsFirstPlay")

    def test_a_game_ends_at_its_last_play(self):
        self.assertEqual(verify.classify(self.row(("in", 16, 22), ("post", 16, 22))), "endsAtItsLastPlay")

    def test_anything_else_is_unexplained(self):
        self.assertEqual(verify.classify(self.row(("in", 21, 7), ("in", 14, 7))), "unexplained",
                         "a rebuild behind the board is not a known limit")
        self.assertEqual(verify.classify(self.row(("in", 0, 6), ("in", 0, 20))), "unexplained",
                         "two scores adrift is not a conversion")
        self.assertEqual(verify.classify(self.row(("post", 16, 22), ("in", 16, 22))), "unexplained")


class Merge(unittest.TestCase):
    """The recording owns every moment it covers."""

    def setUp(self):
        self.root = pathlib.Path(tempfile.mkdtemp())
        self.capture = self.root / "live"
        self.backfill = self.root / "backfill"
        self.out = self.root / "merged"

    def write(self, path: pathlib.Path, body: dict):
        path.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(path, "wt") as f:
            json.dump(body, f)

    def build(self):
        for stamp in ("20260919T160000Z", "20260919T170000Z", "20260919T204914Z"):
            self.write(self.backfill / "scoreboard" / f"{stamp}.json.gz", {"events": [], "capturedAt": stamp})
        for stamp in ("20260919T204914Z", "20260919T205014Z"):
            self.write(self.capture / "scoreboard" / f"{stamp}.json.gz", {"events": [], "capturedAt": stamp})
        self.write(self.capture / "final" / "1.json.gz", {"header": {}})
        self.write(self.capture / "live" / "1" / "20260919T205014Z.json.gz", {"header": {}})
        self.write(self.backfill / "summary" / "1.json.gz", {"header": {}})
        self.write(self.backfill / "summary" / "2.json.gz", {"header": {}})   # finished before the recorder
        self.write(self.backfill / "summary" / "3.json.gz", {"header": {}})   # still live when fetched
        (self.backfill / "manifest.json").write_text(json.dumps(
            {"games": {"1": {"state": "post"}, "2": {"state": "post"}, "3": {"state": "in", "partial": True}}}))

    def test_the_recording_wins_where_both_cover_a_moment(self):
        self.build()
        report = merge_capture.merge(self.capture, self.backfill, self.out)
        self.assertEqual(report["frames"], {"reconstructed": 2, "recorded": 2, "reconstructedDropped": 1,
                                            "firstRecorded": "20260919T204914Z",
                                            "first": "20260919T160000Z", "last": "20260919T205014Z"})
        names = sorted(p.name for p in (self.out / "scoreboard").glob("*.json.gz"))
        self.assertEqual(names, ["20260919T160000Z.json.gz", "20260919T170000Z.json.gz",
                                 "20260919T204914Z.json.gz", "20260919T205014Z.json.gz"])
        kept = json.loads(gzip.open(self.out / "scoreboard" / "20260919T204914Z.json.gz", "rt").read())
        self.assertEqual(kept["capturedAt"], "20260919T204914Z")

    def test_a_partial_summary_is_never_filed_as_a_final(self):
        self.build()
        report = merge_capture.merge(self.capture, self.backfill, self.out)
        self.assertEqual(sorted(p.name for p in (self.out / "final").glob("*.json.gz")),
                         ["1.json.gz", "2.json.gz"])
        self.assertEqual(report["finals"], {"fromRecording": 1, "onlyFromBackfill": 1,
                                            "backfillPartialsNotUsedAsFinals": 1})

    def test_the_merged_night_replays_as_one(self):
        self.build()
        merge_capture.merge(self.capture, self.backfill, self.out)
        src = CaptureSource(self.out, "99999999T999999Z")
        self.assertEqual(src.frames(), ["20260919T160000Z", "20260919T170000Z",
                                        "20260919T204914Z", "20260919T205014Z"])
        self.assertTrue((self.out / "MERGE.json").exists())

    def test_it_refuses_while_the_recorder_is_still_going(self):
        self.build()
        (self.capture / "heartbeat.json").write_text(json.dumps({"phase": "recording", "pid": 1, "at": "now"}))
        self.assertIsNotNone(merge_capture.recorder_running(self.capture))
        (self.capture / "heartbeat.json").write_text(json.dumps({"phase": "stopped", "pid": 1, "at": "now"}))
        self.assertIsNone(merge_capture.recorder_running(self.capture))
        # a heartbeat left behind by a process that is gone does not block it
        (self.capture / "heartbeat.json").write_text(json.dumps({"phase": "recording", "pid": 999999, "at": "old"}))
        self.assertIsNone(merge_capture.recorder_running(self.capture))


if __name__ == "__main__":
    unittest.main()
