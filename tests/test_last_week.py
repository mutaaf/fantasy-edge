"""Last week's slate: finding the week, pulling it, and what the picker says.

Two real 2026 boards, cut by `tools/make_replay_fixture.py --week` and never
edited by hand:

  week 1   sixteen games, every one final - the week to offer
  week 2   sixteen games, none kicked off - the week being served on the day
           these fixtures were cut, and the reason "this week" is the wrong
           answer to "what can I watch"

The three whole-game captures from `test_replay_scene` stand in for a pulled
week, because the reasons change when the play-by-play arrives and the point of
`precision` is that the picker says which answer it is giving.
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from fantasyedge import replay as rp                          # noqa: E402
from fantasyedge import week as wk                            # noqa: E402

FIX = pathlib.Path(__file__).parent / "fixtures"
FINISHED, TOCOME = "week_slate_2026_2_1.json", "week_slate_2026_2_2.json"
REGULATION, OVERTIME, PICK_SIX = "401772510", "401772949", "401772810"


def setUpModule():
    os.environ["FANTASYEDGE_SCOREBOARD_FILE"] = str(FIX / "espn_scoreboard.json")
    os.environ["FANTASYEDGE_SUMMARY_FILE"] = str(FIX / "espn_summary.json")


def board(name: str) -> dict:
    return json.loads((FIX / name).read_text())


def game(event: str) -> dict:
    return json.loads((FIX / f"replay_game_{event}.json").read_text())


class Feed:
    """ESPN, replaced by a dictionary of boards, counting every request."""

    def __init__(self, **by_url):
        self.by_url = by_url
        self.urls: list[str] = []

    def __call__(self, url: str) -> dict:
        self.urls.append(url)
        for fragment, payload in self.by_url.items():
            if fragment in url:
                return payload
        if "week=" not in url:                       # the undated "this week"
            return self.by_url.get("current", {"events": []})
        return {"events": []}


# ═══════════════════════════ finding the week ═══════════════════════════


class TestTheWeekIsReadFromTheFeed(unittest.TestCase):

    def test_a_board_reports_its_own_season_and_week(self):
        at = wk.season_week(board(FINISHED))
        self.assertEqual((at["season"], at["seasontype"], at["week"]), (2026, 2, 1))

    def test_a_week_is_finished_only_when_every_game_is(self):
        self.assertEqual(wk.week_state(board(FINISHED)), "final")
        self.assertEqual(wk.week_state(board(TOCOME)), "pre")
        self.assertEqual(wk.week_state({"events": []}), "empty")

    def test_one_game_still_to_come_leaves_the_week_unfinished(self):
        part = board(FINISHED)
        comp = part["events"][3]["competitions"][0]
        comp["status"] = {"type": {"state": "pre", "shortDetail": "Mon 8:15 PM"}}
        self.assertEqual(wk.week_state(part), "partial")

    def test_a_game_in_progress_makes_the_week_playing(self):
        live = board(FINISHED)
        live["events"][0]["competitions"][0]["status"] = {"type": {"state": "in"}}
        self.assertEqual(wk.week_state(live), "playing")

    def test_last_finished_walks_back_past_a_week_with_games_to_come(self):
        """The Thursday case: week 2 is being served, nothing has been played."""
        feed = Feed(current=board(TOCOME), **{"week=1": board(FINISHED)})
        found = wk.last_finished(http=feed)
        self.assertEqual((found["season"], found["week"]), (2026, 1))
        self.assertFalse(found["isCurrent"])
        self.assertEqual([t["state"] for t in found["tried"]], ["pre", "final"])
        self.assertEqual(len(feed.urls), 2)

    def test_a_finished_current_week_is_last_week_and_costs_one_request(self):
        """The Tuesday case: the week just ended and is still being served."""
        feed = Feed(current=board(FINISHED))
        found = wk.last_finished(http=feed)
        self.assertEqual(found["week"], 1)
        self.assertTrue(found["isCurrent"])
        self.assertEqual(len(feed.urls), 1)

    def test_walking_back_crosses_the_seams_of_a_season(self):
        self.assertEqual(wk.previous_week(2026, 3, wk.REGULAR), (2026, 2, wk.REGULAR))
        self.assertEqual(wk.previous_week(2026, 1, wk.POSTSEASON),
                         (2026, 18, wk.REGULAR))
        self.assertEqual(wk.previous_week(2026, 1, wk.REGULAR),
                         (2025, 5, wk.POSTSEASON))

    def test_a_feed_with_no_finished_week_says_so_rather_than_searching_on(self):
        feed = Feed(current=board(TOCOME))
        with self.assertRaises(SystemExit) as caught:
            wk.last_finished(http=feed, max_back=2)
        self.assertIn("No finished week", str(caught.exception))
        self.assertEqual(len(feed.urls), 3)          # the first, and two back


# ════════════════════════════ pulling a week ════════════════════════════


class TestPullingAWeek(unittest.TestCase):

    def setUp(self):
        self.dest = pathlib.Path(tempfile.mkdtemp())
        self.board = board(FINISHED)
        self.summaries = {ev["id"]: game(OVERTIME)["summary"]
                          for ev in self.board["events"]}

    def feed(self):
        def http(url):
            if "summary?event=" in url:
                event = url.split("summary?event=", 1)[1].split("&")[0]
                return self.summaries[event]
            return self.board
        calls = []
        return (lambda url: (calls.append(url), http(url))[1]), calls

    def test_a_week_costs_one_request_per_game(self):
        http, calls = self.feed()
        out = wk.pull_week(self.board, self.dest, http=http)
        self.assertEqual(len(out["pulled"]), 16)
        self.assertEqual(out["requests"], 16)
        self.assertEqual(len(calls), 16)
        self.assertTrue(all("summary?event=" in u for u in calls))

    def test_the_weeks_own_board_is_written_beside_every_game(self):
        http, _ = self.feed()
        wk.pull_week(self.board, self.dest, http=http)
        for ev in self.board["events"]:
            event = str(ev["id"])
            self.assertTrue((self.dest / f"{event}.json").exists())
            slate = rp.scoreboard_path(self.dest, event)
            self.assertTrue(slate.exists())
            # `replay.load` refuses a slate that does not carry its game.
            self.assertTrue(rp._event(json.loads(slate.read_text()), event))

    def test_pulling_twice_spends_nothing(self):
        http, calls = self.feed()
        wk.pull_week(self.board, self.dest, http=http)
        again = wk.pull_week(self.board, self.dest, http=http)
        self.assertEqual(again["requests"], 0)
        self.assertEqual(len(again["cached"]), 16)
        self.assertEqual(again["pulled"], [])
        self.assertEqual(len(calls), 16)             # not one more

    def test_refresh_pulls_again(self):
        http, _ = self.feed()
        wk.pull_week(self.board, self.dest, http=http)
        again = wk.pull_week(self.board, self.dest, http=http, refresh=True)
        self.assertEqual(len(again["pulled"]), 16)

    def test_only_pulls_the_game_asked_for(self):
        http, calls = self.feed()
        want = str(self.board["events"][2]["id"])
        out = wk.pull_week(self.board, self.dest, http=http, only=[want])
        self.assertEqual(out["pulled"], [want])
        self.assertEqual(len(calls), 1)

    def test_a_game_that_fails_is_reported_and_the_rest_still_pull(self):
        bad = str(self.board["events"][1]["id"])

        def http(url):
            if f"event={bad}" in url:
                raise OSError("ESPN said no")
            if "summary?event=" in url:
                event = url.split("summary?event=", 1)[1].split("&")[0]
                return self.summaries[event]
            return self.board

        out = wk.pull_week(self.board, self.dest, http=http)
        self.assertEqual(len(out["pulled"]), 15)
        self.assertEqual([f["event"] for f in out["failed"]], [bad])
        self.assertIn("ESPN said no", out["failed"][0]["error"])

    def test_a_game_with_no_plays_is_a_failure_not_an_empty_capture(self):
        self.summaries[str(self.board["events"][0]["id"])] = {"drives": {}}
        http, _ = self.feed()
        out = wk.pull_week(self.board, self.dest, http=http)
        self.assertEqual(len(out["failed"]), 1)
        self.assertFalse((self.dest / f"{self.board['events'][0]['id']}.json").exists())

    def test_a_week_still_being_played_pulls_only_its_finished_games(self):
        part = board(FINISHED)
        for ev in part["events"][:4]:
            ev["competitions"][0]["status"] = {"type": {"state": "pre"}}
        http, _ = self.feed()
        out = wk.pull_week(part, self.dest, http=http)
        self.assertEqual(out["games"], 12)
        self.assertEqual(len(out["pulled"]), 12)


# ══════════════════════════ why it is worth watching ══════════════════════


class TestTheReasonToWatch(unittest.TestCase):

    def row(self, event, pulled: bool):
        g = game(event)
        return wk.game_row(g["scoreboard"]["events"][0],
                           g["summary"] if pulled else None,
                           reveal=True, pulled=pulled)

    def test_overtime_leads_the_reasons(self):
        self.assertEqual(self.row(OVERTIME, False)["reasons"][0], "Went to overtime")

    def test_the_play_by_play_finds_lead_changes_the_quarters_hide(self):
        cheap = self.row(OVERTIME, False)
        dear = self.row(OVERTIME, True)
        self.assertEqual(cheap["precision"], "quarter")
        self.assertEqual(dear["precision"], "play")
        self.assertIn("2 lead changes", cheap["reasons"])
        self.assertIn("4 lead changes", dear["reasons"])
        self.assertIn("quarter", cheap["caveat"])

    def test_a_game_whose_quarters_look_flat_still_changed_hands(self):
        cheap, dear = self.row(REGULATION, False), self.row(REGULATION, True)
        self.assertNotIn("The lead changed hands", cheap["reasons"])
        self.assertIn("The lead changed hands", dear["reasons"])

    def test_lead_changes_are_counted_on_scoring_plays_only(self):
        """ESPN stamps a stale score on plays after the winning score.

        On 401772949 the two timeouts following the go-ahead touchdown carry
        37-36, the score before its two-point try. Counting every play sees the
        lead change twice more than it did; counting scoring plays does not.
        """
        summary = game(OVERTIME)["summary"]
        every = [p for p in rp._all_plays(summary)]
        stale = [p for p in every
                 if not p.get("scoringPlay")
                 and (p.get("type") or {}).get("text") == "Timeout"
                 and p.get("homeScore") == 36]
        self.assertTrue(stale, "the fixture no longer carries the stale-score plays")
        self.assertEqual(wk._play_swing(summary)["changes"], 4)

    def test_the_winning_score_is_a_score_not_the_end_of_the_game(self):
        winning = wk._play_swing(game(OVERTIME)["summary"])["winning"]
        self.assertIn("TOUCHDOWN", winning["text"].upper())
        self.assertNotIn("END GAME", winning["text"].upper())

    def test_a_late_winner_is_called_out_with_what_scored_it(self):
        swing = wk._play_swing(game(PICK_SIX)["summary"])
        self.assertEqual(swing["winning"]["period"], 4)
        board = game(PICK_SIX)["scoreboard"]["events"][0]
        # The same game, moved inside the last minute, must say so.
        summary = game(PICK_SIX)["summary"]
        for drive in rp._drives(summary):
            for play in drive.get("plays") or []:
                if play.get("id") == swing["winning"].get("id"):
                    play["clock"] = {"displayValue": "0:34"}
        lines = wk.reasons(board, summary)["lines"]
        self.assertTrue(any("lead change" in line.lower() or "Won on a" in line
                            for line in lines), lines)

    def test_a_comeback_is_measured_against_the_winner(self):
        row = self.row(PICK_SIX, True)
        self.assertIn("Won after trailing by 11", row["reasons"])

    def test_a_game_with_nothing_to_say_says_that_rather_than_nothing(self):
        flat = {"id": "1", "shortName": "AAA @ BBB", "competitions": [{
            "date": "2026-09-13T17:00Z",
            "status": {"type": {"state": "post", "shortDetail": "Final"}},
            "competitors": [
                {"homeAway": "home", "score": "31", "team": {"abbreviation": "BBB"},
                 "linescores": [{"value": 7}, {"value": 10}, {"value": 7}, {"value": 7}]},
                {"homeAway": "away", "score": "3", "team": {"abbreviation": "AAA"},
                 "linescores": [{"value": 0}, {"value": 3}, {"value": 0}, {"value": 0}]}]}]}
        out = wk.reasons(flat)
        self.assertIn("A rout", out["lines"])
        self.assertEqual(wk.game_row(flat)["reason"], "A rout")

    def test_the_best_game_sorts_first(self):
        rows = wk.week_games(board(FINISHED))
        self.assertGreaterEqual(rows[0]["watchability"], rows[-1]["watchability"])
        self.assertEqual(rows[0]["name"], "NO @ DET")      # the only overtime game


# ═════════════════════════════ spoilers ═════════════════════════════


class TestSkippingByScore(unittest.TestCase):
    """A replay is watched for the scores, so the skip is by score, not time."""

    def director(self, event=OVERTIME):
        root = pathlib.Path(tempfile.mkdtemp())
        g = game(event)
        (root / f"{event}.json").write_text(json.dumps(g["summary"]))
        rp.scoreboard_path(root, event).write_text(json.dumps(g["scoreboard"]))
        d = rp.ReplayDirector(root)
        d.load(event)
        return d

    def test_every_scoring_play_is_a_marker_and_every_drive_is_one(self):
        marks = self.director().markers()
        summary = game(OVERTIME)["summary"]
        scoring = [p for p in rp._all_plays(summary) if p.get("scoringPlay")]
        self.assertEqual(len(marks["scores"]), len(scoring))
        self.assertEqual(len(marks["drives"]), len(rp._drives(summary)))
        self.assertEqual(marks["length"], rp.total_seconds(summary))

    def test_a_score_marker_lands_before_the_play_not_on_it(self):
        for m in self.director().markers()["scores"]:
            self.assertLess(m["at"], m["playAt"])
            self.assertGreaterEqual(m["at"], 0)
            self.assertEqual(m["playAt"] - m["at"], min(rp.LEAD_SECONDS, m["playAt"]))

    def test_skipping_forward_walks_the_scores_in_order(self):
        d = self.director()
        marks = [m["at"] for m in d.markers()["scores"]]
        self.assertEqual(d.skip()["gameSeconds"], marks[0])
        self.assertEqual(d.skip()["gameSeconds"], marks[1])
        self.assertEqual(d.skip(forward=False)["gameSeconds"], marks[0])

    def test_skipping_back_from_the_first_score_reaches_the_kickoff(self):
        d = self.director()
        d.skip()
        self.assertEqual(d.skip(forward=False)["gameSeconds"], 0)

    def test_skipping_past_the_last_score_stops_at_the_end(self):
        d = self.director()
        d.seek(d.length)
        self.assertEqual(d.skip()["gameSeconds"], d.length)

    def test_the_controls_take_next_and_previous(self):
        d = self.director()
        self.assertEqual(d.control({"action": "next"})["gameSeconds"],
                         d.markers()["scores"][0]["at"])
        self.assertEqual(d.control({"action": "previous"})["gameSeconds"], 0)
        with self.assertRaises(ValueError) as caught:
            d.control({"action": "rewind"})
        self.assertIn("next", str(caught.exception))

    def test_markers_need_a_loaded_replay_and_say_so(self):
        from fantasyedge import api
        app = api.Api(db=str(pathlib.Path(tempfile.mkdtemp()) / "t.db"))
        app._replay = rp.ReplayDirector(pathlib.Path(tempfile.mkdtemp()))
        with self.assertRaises(api.HttpError) as caught:
            app.dispatch("/api/replay/markers", {})
        self.assertEqual(caught.exception.code, 404)


class TestSpoilers(unittest.TestCase):

    def test_a_default_row_carries_no_score_anywhere_in_it(self):
        """No score, and no number a score could be read out of.

        Checked against the board's own finals rather than by looking for the
        word: a reason may say "61 points between them", which is why the game
        is worth an hour and still does not say who scored them.
        """
        shown = {r["event"]: r for r in wk.week_games(board(FINISHED), reveal=True)}
        for row in wk.week_games(board(FINISHED)):
            self.assertNotIn("score", row["away"])
            self.assertNotIn("score", row["home"])
            self.assertNotIn("final", row)
            self.assertFalse(row["spoiler"])
            full = shown[row["event"]]
            for side in ("away", "home"):
                self.assertNotIn(str(full[side]["score"]), " ".join(row["reasons"]))

    def test_reasons_never_name_the_winner(self):
        for row in wk.week_games(board(FINISHED)):
            for line in row["reasons"]:
                self.assertNotIn(row["home"]["abbr"], line)
                self.assertNotIn(row["away"]["abbr"], line)

    def test_revealing_adds_the_scores_and_the_final_label(self):
        rows = wk.week_games(board(FINISHED), reveal=True)
        top = next(r for r in rows if r["name"] == "NO @ DET")
        self.assertEqual((top["away"]["score"], top["home"]["score"]), (30, 31))
        self.assertEqual(top["final"], "Final/OT")
        self.assertTrue(top["spoiler"])

    def test_the_shape_is_the_same_either_way(self):
        hidden = wk.week_games(board(FINISHED))[0]
        shown = wk.week_games(board(FINISHED), reveal=True)[0]
        self.assertEqual(set(shown) - set(hidden), {"final"})


# ═══════════════════════════ the contracts ═══════════════════════════


class TestTheJsonContract(unittest.TestCase):

    def setUp(self):
        self.source = pathlib.Path(tempfile.mkdtemp())
        for ev in (OVERTIME, PICK_SIX):
            g = game(ev)
            (self.source / f"{ev}.json").write_text(json.dumps(g["summary"]))
            rp.scoreboard_path(self.source, ev).write_text(json.dumps(g["scoreboard"]))
        # And a week as `pull_week` leaves it: the week's own board beside every
        # game, which is what the offline path reads.
        self.week = board(FINISHED)
        summary = game(OVERTIME)["summary"]
        wk.pull_week(self.week, self.source,
                     http=lambda url: (summary if "summary?event=" in url
                                       else self.week))

    def test_every_row_carries_what_a_picker_draws(self):
        for row in wk.week_games(board(FINISHED)):
            for key in ("event", "name", "kickoff", "away", "home", "reason",
                        "reasons", "precision", "caveat", "watchability",
                        "pulled", "spoiler"):
                self.assertIn(key, row)
            self.assertTrue(row["event"].isdigit())
            self.assertTrue(row["caveat"], "every row states which answer it gave")
            self.assertIn(row["precision"], ("quarter", "play"))

    def test_a_pulled_game_is_marked_and_carries_its_length(self):
        rows = wk.week_games(game(OVERTIME)["scoreboard"], source=self.source)
        self.assertTrue(rows[0]["pulled"])
        self.assertEqual(rows[0]["precision"], "play")
        self.assertEqual(rows[0]["length"], rp.total_seconds(game(OVERTIME)["summary"]))
        self.assertTrue(rows[0]["complete"])

    def test_a_pulled_week_needs_no_request_to_be_listed_again(self):
        def http(url):
            raise AssertionError(f"asked ESPN for {url}")

        out = wk.last_week(http=http, source=self.source, offline=True)
        self.assertTrue(out["offline"])
        self.assertEqual((out["season"], out["week"]), (2026, 1))
        self.assertEqual(out["total"], 16)
        self.assertEqual(out["pulled"], 16)

    def test_offline_with_nothing_pulled_says_what_to_run(self):
        with self.assertRaises(SystemExit) as caught:
            wk.last_week(source=pathlib.Path(tempfile.mkdtemp()), offline=True)
        self.assertIn("--pull", str(caught.exception))

    def test_the_newest_pulled_week_is_the_one_offered(self):
        """Pulling an older week does not make it last week.

        setUp has already pulled the 2026 week 1 board. A 2025 week beside it
        is older by kickoff, however recently its files were written, so the
        choice is made on the dates the board carries rather than on mtime.
        """
        old = json.loads(json.dumps(game(PICK_SIX)["scoreboard"]))
        old["events"].append(json.loads(json.dumps(old["events"][0])))
        old["events"][1]["id"] = "999"
        rp.scoreboard_path(self.source, "999").write_text(json.dumps(old))
        chosen = wk.cached_board(self.source)
        self.assertEqual(wk.season_week(chosen)["season"], 2026)
        self.assertFalse(any(ev.get("id") == "999" for ev in chosen["events"]))

        newer = json.loads(json.dumps(self.week))
        for ev in newer["events"]:
            ev["competitions"][0]["date"] = "2026-09-20T17:00Z"
            ev["id"] = f"55{ev['id'][-4:]}"
        rp.scoreboard_path(self.source, "550000").write_text(json.dumps(newer))
        self.assertEqual(
            max(wk._kickoff(ev) for ev in wk.cached_board(self.source)["events"]),
            "2026-09-20T17:00Z")

    def test_the_api_withholds_scores_by_default(self):
        import tempfile as tf

        from fantasyedge import api
        os.environ["FANTASYEDGE_REPLAY_DIR"] = str(self.source)
        app = api.Api(db=str(pathlib.Path(tf.mkdtemp()) / "t.db"))
        out, policy = app.dispatch("/api/lastweek", {"offline": ["1"]})
        self.assertEqual(policy, api.DERIVED)
        self.assertEqual(out["total"], 16)
        for row in out["games"]:
            self.assertNotIn("score", row["away"])
            self.assertNotIn("score", row["home"])
            self.assertNotIn("final", row)
        self.assertEqual(out["open"]["path"], "/api/replay")
        shown, _ = app.dispatch("/api/lastweek",
                                {"offline": ["1"], "spoilers": ["1"]})
        self.assertTrue(all("score" in r["home"] for r in shown["games"]))

    def test_the_command_line_names_the_week_it_is_showing(self):
        """`--offline` has no season or week flag to read, so it reads the board.

        The first version printed "None week None" over a correct sixteen-game
        list, because the header was built from the flags rather than from the
        slate it had just read off disk.
        """
        import argparse
        import contextlib
        import io
        import shutil

        from fantasyedge import cli

        out = pathlib.Path(tempfile.mkdtemp())
        shutil.copytree(self.source, out / "source")     # the CLI reads <out>/source
        args = argparse.Namespace(out=str(out), spoilers=False, offline=True,
                                  pull=False, open=None, refresh=False,
                                  season=None, week=None, seasontype=2, json=False)
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            cli.cmd_last_week(args, {})
        first = buffer.getvalue().splitlines()[0]
        self.assertIn("2026 week 1", first)
        self.assertNotIn("None", first)

    def test_the_route_is_listed(self):
        from fantasyedge import api
        self.assertTrue(any(r[1] == "/api/lastweek" for r in api.ROUTES))


if __name__ == "__main__":
    unittest.main()
