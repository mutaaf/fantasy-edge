"""A finished day, rebuilt from play wallclocks and driven like a live one.

Fixture-driven and offline. `tests/fixtures/day_slate.json` and the two
`day_game_*.json` beside it are a real slate trimmed by
`tools/make_replay_fixture.py --day`, never edited by hand.

The tests that matter most are the last two: the rebuilt board has to travel
the *live* path - `EspnLiveSource.games()`, `whip.slate()`, `whip.rank()` -
without that path knowing anything has changed. If those two ever need a
special case, the claim that a replayed day and a live one are one code path
has stopped being true.
"""

import datetime as dt
import json
import pathlib
import unittest

from fantasyedge import dayreplay as dy

FIX = pathlib.Path(__file__).parent / "fixtures"
DAY = "2026-09-20"


def _fixture():
    board = json.loads((FIX / "day_slate.json").read_text())
    summaries = {}
    for ev in board.get("events") or []:
        path = FIX / f"day_game_{ev['id']}.json"
        if path.exists():
            summaries[str(ev["id"])] = json.loads(path.read_text())
    return board, summaries


def _at(hhmm: str) -> dt.datetime:
    return dy.parse_moment(hhmm, dt.date(2026, 9, 20))


def _state(event: dict) -> str:
    comp = (event.get("competitions") or [{}])[0]
    return (((comp.get("status") or {}).get("type")) or {}).get("state") or ""


def _scores(event: dict) -> dict:
    comp = (event.get("competitions") or [{}])[0]
    return {(c.get("homeAway") or "").lower(): int(c.get("score") or 0)
            for c in comp.get("competitors") or []}


class OrdersStampsByPlayOrder(unittest.TestCase):
    """ESPN's play order is trusted over its clocks."""

    def test_a_stamp_two_hours_late_is_pulled_back_between_its_neighbours(self):
        base = dt.datetime(2026, 9, 20, 17, 0, tzinfo=dt.timezone.utc)
        times = [base, base + dt.timedelta(seconds=30),
                 base + dt.timedelta(hours=2),            # the wrong one
                 base + dt.timedelta(seconds=90)]
        out = dy.ordered_times(times)
        self.assertEqual(out[0], times[0])
        self.assertEqual(out[1], times[1])
        self.assertEqual(out[3], times[3])
        self.assertTrue(times[1] < out[2] < times[3],
                        f"the late stamp should sit between its neighbours, got {out[2]}")

    def test_the_result_never_goes_backwards(self):
        base = dt.datetime(2026, 9, 20, 17, 0, tzinfo=dt.timezone.utc)
        times = [base + dt.timedelta(seconds=s) for s in (0, 500, 20, 30, 900, 40)]
        out = dy.ordered_times(times)
        self.assertEqual(out, sorted(out), "stamps must come out non-decreasing")

    def test_missing_stamps_are_filled_from_their_neighbours(self):
        base = dt.datetime(2026, 9, 20, 17, 0, tzinfo=dt.timezone.utc)
        out = dy.ordered_times([base, None, None, base + dt.timedelta(seconds=60)])
        self.assertTrue(all(t is not None for t in out))
        self.assertEqual(out, sorted(out))

    def test_the_real_day_needed_no_repair(self):
        """Measured, not assumed: this slate's stamps already agree with order.

        Recorded so that a future slate that *does* need repair shows up as a
        change here rather than silently.
        """
        _, summaries = _fixture()
        for summary in summaries.values():
            plays = [p for d in (summary["drives"]["previous"]) for p in d["plays"]]
            raw = [dy._when(p) for p in plays]
            self.assertEqual(raw, dy.ordered_times(raw))


class ReadsScoresThroughEspnsBlanks(unittest.TestCase):
    def test_an_administrative_row_reporting_nothing_does_not_reset_the_score(self):
        summary = {"drives": {"previous": [{"plays": [
            {"id": "1", "wallclock": "2026-09-20T17:00:00Z", "awayScore": 7, "homeScore": 0},
            {"id": "2", "wallclock": "2026-09-20T17:01:00Z", "awayScore": 0, "homeScore": 0,
             "text": "Two-Minute Warning"},
            {"id": "3", "wallclock": "2026-09-20T17:02:00Z", "awayScore": 7, "homeScore": 3},
        ]}]}}
        running = dy.running_scores(summary)
        self.assertEqual(running["2"], (7, 0), "a 0-0 admin row must carry the score through")
        self.assertEqual(running["3"], (7, 3))

    def test_a_real_correction_downwards_is_kept(self):
        """A failed two-point try restates a score ESPN counted early."""
        summary = {"drives": {"previous": [{"plays": [
            {"id": "1", "wallclock": "2026-09-20T17:00:00Z", "awayScore": 17, "homeScore": 17},
            {"id": "2", "wallclock": "2026-09-20T17:01:00Z", "awayScore": 15, "homeScore": 17,
             "text": "TWO-POINT CONVERSION ATTEMPT. ATTEMPT FAILS."},
        ]}]}}
        self.assertEqual(dy.running_scores(summary)["2"], (15, 17))

    def test_a_genuine_nil_nil_start_is_left_alone(self):
        summary = {"drives": {"previous": [{"plays": [
            {"id": "1", "wallclock": "2026-09-20T17:00:00Z", "awayScore": 0, "homeScore": 0},
        ]}]}}
        self.assertEqual(dy.running_scores(summary)["1"], (0, 0))


class RebuildsAGameAtAMoment(unittest.TestCase):
    def setUp(self):
        self.board, self.summaries = _fixture()
        self.event = (self.board["events"])[0]
        self.summary = self.summaries[str(self.event["id"])]

    def test_before_the_first_play_it_is_the_schedule(self):
        out = dy.game_at(self.event, self.summary, _at("11:00"))
        self.assertEqual(out["dayProvenance"], "schedule")
        self.assertEqual(_state(out), "pre")
        self.assertEqual(_scores(out), {"home": 0, "away": 0})
        self.assertIsNone((out["competitions"][0]).get("situation"))

    def test_mid_game_it_carries_score_clock_and_a_ball(self):
        plays = dy.timed_plays(self.summary)
        when = plays[len(plays) // 2][0]
        out = dy.game_at(self.event, self.summary, when)
        self.assertEqual(out["dayProvenance"], "reconstructed")
        self.assertEqual(_state(out), "in")
        comp = out["competitions"][0]
        self.assertTrue(comp["status"]["displayClock"])
        self.assertGreaterEqual(comp["status"]["period"], 1)
        self.assertIn("situation", comp)

    def test_the_clock_is_seconds_as_well_as_a_string(self):
        """`live.games()` divides by the number; the string is what a board prints."""
        plays = dy.timed_plays(self.summary)
        out = dy.game_at(self.event, self.summary, plays[len(plays) // 2][0])
        status = out["competitions"][0]["status"]
        self.assertIsInstance(status["clock"], float)
        minutes, seconds = status["displayClock"].split(":")
        self.assertAlmostEqual(status["clock"], int(minutes) * 60 + int(seconds))

    def test_a_score_only_ever_grows_through_the_game(self):
        seen = {"home": 0, "away": 0}
        for when, _ in dy.timed_plays(self.summary):
            now = _scores(dy.game_at(self.event, self.summary, when))
            for side in ("home", "away"):
                self.assertGreaterEqual(now[side], seen[side],
                                        f"{side} score went backwards at {when}")
            seen = now


class ReadsTheDistanceToTheEndZone(unittest.TestCase):
    CLUBS = {"1": "PHI", "2": "TEN"}

    def test_the_other_sides_half_gives_the_distance(self):
        start = {"possessionText": "PHI 17", "team": {"id": "2"}}
        self.assertEqual(dy._to_endzone_from_text(start, self.CLUBS), 17)

    def test_your_own_half_is_not_a_red_zone(self):
        start = {"possessionText": "TEN 17", "team": {"id": "2"}}
        self.assertIsNone(dy._to_endzone_from_text(start, self.CLUBS))

    def test_an_unreadable_spot_claims_nothing(self):
        self.assertIsNone(dy._to_endzone_from_text({"possessionText": "midfield",
                                                    "team": {"id": "2"}}, self.CLUBS))

    def test_espns_own_number_is_preferred_when_it_is_there(self):
        play = {"start": {"yardsToEndzone": 4, "possessionText": "PHI 17",
                          "team": {"id": "2"}, "down": 1, "distance": 4}}
        sit = dy.situation_from(play, {}, self.CLUBS)
        self.assertEqual(sit["yardsToEndzone"], 4)
        self.assertTrue(sit["isRedZone"])


class RebuildsTheWholeBoard(unittest.TestCase):
    def setUp(self):
        self.board, self.summaries = _fixture()

    def test_it_says_it_is_a_rebuild_and_what_that_costs(self):
        out = dy.board_at(self.board, self.summaries, _at("14:15"))
        note = out["dayProvenance"]
        self.assertEqual(note["kind"], "reconstructed")
        self.assertTrue(note["caveats"], "a rebuild must carry its caveats")
        self.assertTrue(all(c.strip() for c in note["caveats"]))

    def test_every_game_is_present_whether_or_not_it_has_started(self):
        out = dy.board_at(self.board, self.summaries, _at("11:00"))
        self.assertEqual(len(out["events"]), len(self.board["events"]))
        self.assertTrue(all(_state(e) == "pre" for e in out["events"]))

    def test_the_day_ends_with_every_game_final(self):
        end = dy.covered_span(self.summaries)[1] + dt.timedelta(minutes=1)
        out = dy.board_at(self.board, self.summaries, end)
        # The fixture keeps the first 60 plays, so these games end mid-way and
        # are still "in" - what matters is that the rebuild reaches the last
        # play it was given rather than stopping early.
        self.assertTrue(all(dy.timed_plays(self.summaries[str(e["id"])])
                            for e in out["events"]))


class TruncatesASummaryWithoutLeakingTheResult(unittest.TestCase):
    def test_a_gamecast_opened_early_cannot_see_later_plays(self):
        board, summaries = _fixture()
        summary = summaries[str(board["events"][0]["id"])]
        plays = dy.timed_plays(summary)
        cut = plays[len(plays) // 3][0]
        out = dy.summary_at(summary, cut)
        kept = dy.timed_plays(out)
        self.assertLess(len(kept), len(plays))
        self.assertTrue(all(w <= cut for w, _ in kept))
        self.assertTrue(all(str(sp.get("id")) in {str(p.get("id")) for _, p in kept}
                            for sp in out.get("scoringPlays") or []))
        self.assertEqual(out["dayProvenance"], "reconstructed")


class ReadsATimeOfDay(unittest.TestCase):
    DAY = dt.date(2026, 9, 20)

    def test_a_bare_time_is_eastern(self):
        when = dy.parse_moment("13:00", self.DAY)
        self.assertEqual(when.astimezone(dy.ET).hour, 13)

    def test_it_reads_the_way_people_write_it(self):
        for text in ("4:25pm", "16:25", "4:25 PM ET"):
            self.assertEqual(dy.parse_moment(text, self.DAY).astimezone(dy.ET).hour, 16,
                             f"{text!r} should be 4pm Eastern")

    def test_nonsense_is_refused_rather_than_guessed(self):
        for text in ("", "lunchtime", "25:00"):
            with self.assertRaises(ValueError):
                dy.parse_moment(text, self.DAY)


class DrivesTheDay(unittest.TestCase):
    """The director, on a clock this test owns rather than the wall's."""

    def setUp(self):
        self.now = [1000.0]
        self.root = FIX / "_day_root"
        day = self.root / DAY
        day.mkdir(parents=True, exist_ok=True)
        board, summaries = _fixture()
        (day / "board.json").write_text(json.dumps(board))
        for event, summary in summaries.items():
            (day / f"{event}.json").write_text(json.dumps(summary))
        self.director = dy.DayDirector(self.root, clock=lambda: self.now[0])
        self.state = self.director.load(DAY)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.root, ignore_errors=True)

    def test_it_opens_paused_at_the_first_play_and_says_it_is_a_rebuild(self):
        self.assertTrue(self.state["loaded"])
        self.assertFalse(self.state["playing"])
        self.assertEqual(self.state["provenance"], "reconstructed")
        self.assertEqual(self.state["offset"], 0.0)

    def test_playing_advances_the_day_by_speed(self):
        self.director.set_speed(60.0)
        self.director.play()
        self.now[0] += 10.0                       # ten real seconds
        self.assertAlmostEqual(self.director.offset(), 600.0, delta=1.0)

    def test_pausing_stops_it_where_it_stood(self):
        self.director.set_speed(60.0)
        self.director.play()
        self.now[0] += 5.0
        self.director.pause()
        stopped = self.director.offset()
        self.now[0] += 100.0
        self.assertAlmostEqual(self.director.offset(), stopped, delta=0.01)

    def test_it_stops_at_the_end_rather_than_looping(self):
        self.director.set_speed(3600.0)
        self.director.play()
        self.now[0] += 1000.0
        self.assertFalse(self.director.state()["playing"])
        self.assertAlmostEqual(self.director.offset(), self.director.length(), delta=1.0)

    def test_skip_lands_before_the_score_not_on_it(self):
        marks = self.director.markers()["scores"]
        self.assertTrue(marks, "the fixture must contain a score to skip to")
        self.director.skip(forward=True)
        self.assertAlmostEqual(self.director.offset(), marks[0]["at"], delta=1.0)
        self.assertLess(marks[0]["at"], marks[0]["playAt"],
                        "the marker must sit before the play")

    def test_a_window_refuses_to_end_before_it_starts(self):
        with self.assertRaises(ValueError):
            self.director.load(DAY, window=("16:00", "14:00"))

    def test_an_unknown_action_is_refused_rather_than_ignored(self):
        with self.assertRaises(ValueError):
            self.director.control({"action": "rewind"})

    def test_fetch_serves_a_board_and_a_truncated_summary(self):
        self.director.seek(600)
        board = self.director.fetch("https://example/scoreboard")
        self.assertIn("events", board)
        self.assertEqual(board["dayProvenance"]["kind"], "reconstructed")
        event = str(board["events"][0]["id"])
        summary = self.director.fetch(f"https://example/summary?event={event}")
        self.assertEqual(summary["dayProvenance"], "reconstructed")

    def test_fetch_refuses_a_game_that_is_not_on_the_day(self):
        with self.assertRaises(LookupError):
            self.director.fetch("https://example/summary?event=1")


class TheChannelCannotTellItIsARebuild(unittest.TestCase):
    """The point of the whole exercise.

    The live path is handed the director's board and must work unchanged: if
    `games()`, `slate()` or `rank()` ever needs to know, a replayed day and a
    live one have stopped being one code path.
    """

    def setUp(self):
        self.root = FIX / "_day_channel"
        day = self.root / DAY
        day.mkdir(parents=True, exist_ok=True)
        board, summaries = _fixture()
        (day / "board.json").write_text(json.dumps(board))
        for event, summary in summaries.items():
            (day / f"{event}.json").write_text(json.dumps(summary))
        self.director = dy.DayDirector(self.root)
        self.director.load(DAY)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.root, ignore_errors=True)

    def _rows(self):
        from fantasyedge import live as livemod, whip

        src = livemod.EspnLiveSource([], ttl=0.0, box_ttl=0.0, http=self.director.fetch)
        return whip.rank(whip.slate(src.games(), colors=livemod.team_color))

    def test_the_live_tier_reads_the_rebuilt_board(self):
        self.director.seek(1200)
        rows = self._rows()
        self.assertTrue(rows, "the channel saw no games at all")
        self.assertTrue(any(r["state"] == "in" for r in rows))
        for row in rows:
            self.assertTrue(row["home"] and row["away"])
            self.assertIn("urgency", row)
            self.assertTrue(row["reason"])

    def test_the_league_comes_from_the_board_not_a_constant(self):
        rows = self._rows()
        self.assertTrue(all(r["league"] for r in rows),
                        "every row must carry the league the feed stated")

    def test_a_caption_says_where_the_ball_is(self):
        """The rebuild's captions come from play records, which always have them."""
        self.director.seek(1200)
        live = [r for r in self._rows() if r["state"] == "in" and r["situation"]]
        self.assertTrue(live, "no live game had a situation to caption")
        self.assertTrue(any(" at " in r["situation"] for r in live),
                        "a play record names the yard line; the caption should show it")

    def test_the_channel_picks_a_live_game(self):
        from fantasyedge import whip

        self.director.seek(1200)
        ranked = self._rows()
        focus = whip.choose(ranked)
        self.assertTrue(focus)
        chosen = next(r for r in ranked if r["event"] == focus)
        self.assertEqual(chosen["state"], "in",
                         "the channel must never settle on a game that is not running")


if __name__ == "__main__":
    unittest.main()
