"""The unattended recorder: the window it computes, and what a day does to it.

The schedule tests read the real week-3 board captured on the Tuesday before.
The behaviour tests drive `Recorder` with a fake clock and a fake ESPN, so a
network drop, a Mac that slept, a restart and a final that settles all happen
in milliseconds.
"""
from __future__ import annotations

import datetime as dt
import gzip
import json
import pathlib
import sys
import tempfile
import unittest
import urllib.error

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))

import record_slate as rec  # noqa: E402

FIX = REPO / "tests/fixtures"
HAVE = (FIX / "slate_pregame.json").exists()
SATURDAY = dt.date(2026, 9, 19)


def board_from_fixture() -> dict:
    return json.loads((FIX / "slate_pregame.json").read_text())


def game(event: str, iso: str, state: str, name: str = "STATUS_SCHEDULED") -> dict:
    return {"id": event, "date": iso, "shortName": f"A{event} at B{event}",
            "status": {"period": 0, "displayClock": "0:00", "type": {"name": name, "state": state, "completed": state == "post"}},
            "competitions": [{"date": iso, "competitors": [
                {"homeAway": "away", "score": "0", "team": {"id": "1", "abbreviation": "AAA", "location": "Aaa", "displayName": "Aaa"}},
                {"homeAway": "home", "score": "0", "team": {"id": "2", "abbreviation": "BBB", "location": "Bbb", "displayName": "Bbb"}}]}]}


@unittest.skipUnless(HAVE, "pregame capture not present")
class Schedule(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.board = board_from_fixture()

    def test_the_week_is_resolved_from_espns_own_calendar(self):
        self.assertEqual(rec.week_of(self.board, SATURDAY), (2, 3))
        self.assertIsNone(rec.week_of({"leagues": [{"calendar": []}]}, SATURDAY))

    def test_the_slate_is_the_saturday_and_its_friday(self):
        """The week board carries Thursday too; a Saturday recording is not
        waiting on a Thursday game that finished two days earlier."""
        events = rec.slate_events(self.board, SATURDAY)
        days = {rec.utc(ev["date"]).astimezone(rec.ET).strftime("%a") for ev in events.values()}
        self.assertEqual(days, {"Fri", "Sat"})
        self.assertEqual(len(events), len(self.board["events"]) - 1)

    def test_the_window_starts_before_the_first_kickoff_and_stops_sunday_morning(self):
        plan = rec.plan(self.board, SATURDAY, "url")
        self.assertEqual(plan["games"], 74)
        self.assertEqual(plan["byDay"], {"Fri": 3, "Sat": 71})
        first = rec.utc("2026-09-18T23:30Z")
        self.assertEqual(rec.utc(plan["start"]), first - rec.LEAD)
        self.assertEqual(plan["hardStop"][:16], "2026-09-20T06:00")


class Fake:
    """A scripted ESPN: a queue of boards, and summaries on demand."""

    def __init__(self, boards, fail_first=0):
        self.boards, self.fail_first, self.calls = list(boards), fail_first, []

    def __call__(self, url: str) -> dict:
        self.calls.append(url)
        if self.fail_first > 0:
            self.fail_first -= 1
            raise urllib.error.URLError("no route to host")
        if "summary" in url:
            return {"header": {}, "drives": {"previous": []}, "meta": {"fetched": len(self.calls)}}
        return self.boards[min(len(self.boards) - 1, sum(1 for c in self.calls if "summary" not in c) - 1)]


class Recording(unittest.TestCase):
    def setUp(self):
        self.dir = pathlib.Path(tempfile.mkdtemp())
        self.now = [1000.0]

    def recorder(self, fake, **kw):
        return rec.Recorder(self.dir, SATURDAY, "http://espn/scoreboard", interval=60, gap=0,
                            watch_top=kw.pop("watch_top", 1), watch=kw.pop("watch", []),
                            clock=lambda: self.now[0], sleep=lambda s: self.now.__setitem__(0, self.now[0] + s),
                            fetcher=fake, echo=False, **kw)

    def files(self, kind):
        return sorted(p.name for p in (self.dir / kind).glob("**/*.json.gz"))

    def test_an_unchanged_board_is_not_stored_twice(self):
        board = {"events": [game("1", "2026-09-19T16:00Z", "pre")]}
        r = self.recorder(Fake([board]))
        r.cycle()
        r.cycle()
        self.assertEqual(len(self.files("scoreboard")), 1)

    def test_a_live_game_is_snapshotted_and_a_final_waits_to_settle(self):
        live = {"events": [game("1", "2026-09-19T16:00Z", "in", "STATUS_IN_PROGRESS")]}
        final = {"events": [game("1", "2026-09-19T16:00Z", "post", "STATUS_FINAL")]}
        fake = Fake([live, final, final])
        r = self.recorder(fake)
        r.cycle()
        self.assertEqual(len(self.files("live")), 1, "a live game's summary is kept as it changes")
        done, _ = r.cycle()
        self.assertFalse(done, "ESPN amends a final for a few minutes; it is not fetched at once")
        self.assertEqual(self.files("final"), [])
        self.now[0] += rec.FINAL_SETTLE + 1
        done, counts = r.cycle()
        self.assertTrue(done)
        self.assertEqual(self.files("final"), ["1.json.gz"])
        self.assertTrue(any(p.name.endswith("-closing.json.gz") for p in (self.dir / "scoreboard").glob("*")))

    def test_a_postponed_game_never_blocks_the_end(self):
        off = {"events": [game("1", "2026-09-19T16:00Z", "post", "STATUS_POSTPONED")]}
        done, counts = self.recorder(Fake([off])).cycle()
        self.assertTrue(done)
        self.assertEqual(self.files("final"), [], "a game that was not played has no summary to fetch")

    def test_a_restart_resumes_from_disk(self):
        board = {"events": [game("1", "2026-09-19T16:00Z", "in", "STATUS_IN_PROGRESS")]}
        first = self.recorder(Fake([board]))
        first.cycle()
        again = self.recorder(Fake([board]))
        again.cycle()
        self.assertEqual(len(self.files("scoreboard")), 1, "the same board is not written again after a restart")
        self.assertEqual(len(self.files("live")), 1)

    def test_a_saved_final_is_never_fetched_twice(self):
        (self.dir / "final").mkdir(parents=True)
        with gzip.open(self.dir / "final" / "1.json.gz", "wt") as f:
            json.dump({"header": {}}, f)
        fake = Fake([{"events": [game("1", "2026-09-19T16:00Z", "post", "STATUS_FINAL")]}])
        done, _ = self.recorder(fake).cycle()
        self.assertTrue(done)
        self.assertEqual([c for c in fake.calls if "summary" in c], [])

    def test_a_network_drop_backs_off_and_carries_on(self):
        board = {"events": [game("1", "2026-09-19T16:00Z", "pre")]}
        fake = Fake([board], fail_first=3)
        r = self.recorder(fake)
        stop = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=30)
        r.run(None, stop, ends_when_final=False)
        log = (self.dir / "record.log").read_text()
        self.assertIn("retrying in", log)
        self.assertGreaterEqual(r.errors, 3)
        self.assertEqual(len(self.files("scoreboard")), 1, "it kept recording once the network came back")
        beat = json.loads((self.dir / "heartbeat.json").read_text())
        self.assertEqual(beat["slate"], "2026-09-19")
        self.assertIn(beat["phase"], ("recording", "stopped", "idle"))

    def test_a_gap_in_wall_clock_time_is_reported(self):
        board = {"events": [game("1", "2026-09-19T16:00Z", "pre")]}
        r = self.recorder(Fake([board]))
        r.sleep = lambda s: self.now.__setitem__(0, self.now[0] + s + 3600)   # the Mac slept an hour
        stop = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=0.5)
        r.run(None, stop, ends_when_final=False)
        self.assertIn("resumed after a", (self.dir / "record.log").read_text())

    def test_the_log_rotates(self):
        r = self.recorder(Fake([{"events": []}]))
        (self.dir / "record.log").write_bytes(b"x" * (rec.LOG_ROTATE_BYTES + 1))
        r.say("after the rotation")
        self.assertTrue((self.dir / "record.log.1").exists())
        self.assertLess((self.dir / "record.log").stat().st_size, 1000)

    def test_a_lull_is_reported_so_the_run_can_sleep_through_it(self):
        soon = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=6)).strftime("%Y-%m-%dT%H:%MZ")
        board = {"events": [game("1", soon, "pre")]}
        # slate_events keys on the ET day, so ask about the day that kickoff lands on
        day = rec.utc(soon).astimezone(rec.ET).date()
        r = rec.Recorder(self.dir, day, "u", 60, 0, 1, [], clock=lambda: self.now[0],
                         sleep=lambda s: None, fetcher=Fake([board]), echo=False)
        _, counts = r.cycle()
        self.assertTrue(counts["idle"])
        self.assertEqual(counts["nextKickoff"], board["events"][0]["date"])


if __name__ == "__main__":
    unittest.main()
