"""Phase 1's exit: the whole recorded night replays across every tile, inside
the request budget, overtime included.

These run against data/capture/2026-09-12 - the recording itself, not a
fixture - because the claim is about the night as it was recorded. They skip
when the capture is absent.
"""
from __future__ import annotations

import copy
import gzip
import itertools
import json
import pathlib
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from api import handlers, server
from cfb import changes, league, parse
from cfb.sources import Budgeted, CaptureSource, FixtureSource, Source, seconds_between
from schema_lite import Validator

REPO = pathlib.Path(__file__).resolve().parents[1]
ROOT = REPO / "data/capture/2026-09-12"
CONTRACTS = Validator(REPO / "contracts")
HAVE = (ROOT / "scoreboard").is_dir()

OSU_TEX, WAKE_PUR, CAM_FLA, USM_AUB, TOW_SC = "401856682", "401858224", "401856672", "401856671", "401856680"
TEXAS = "251"


def capture(at="99999999T999999Z"):
    return CaptureSource(ROOT, at)


@unittest.skipUnless(HAVE, "capture not present")
class Timeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = capture()
        cls.timeline = handlers.replay(cls.src)

    def test_matches_contract(self):
        self.assertEqual(CONTRACTS.validate(self.timeline, "replay.schema.json"), [])

    def test_frames_are_the_timestamped_boards_only(self):
        frames = self.timeline["frames"]
        self.assertEqual(len(frames), 60)
        self.assertEqual(frames[0]["stamp"], "20260913T001906Z")
        self.assertEqual(frames[-1]["stamp"], "20260913T014409Z")
        self.assertEqual(frames[0]["label"], "8:19 PM ET")
        self.assertEqual([f["index"] for f in frames], list(range(60)))
        self.assertIsNone(frames[0]["headline"], "the first frame has nothing to compare against")

    def test_the_recorder_gap_is_reported_not_papered_over(self):
        self.assertEqual(self.timeline["gaps"], [{"from": "2026-09-13T01:17:43Z", "to": "2026-09-13T01:43:11Z", "minutes": 25.5}])

    def test_the_backfill_never_answers_for_a_moment_before_the_recording(self):
        early = capture("20260913T000000Z")
        self.assertIsNone(early.stamp())
        with self.assertRaises(handlers.NotFound):
            handlers.slate(early)
        self.assertIsNone(early.summary(WAKE_PUR), "a final fetched next morning is not on the board at 8 PM")

    def test_the_closing_board_of_a_finished_night_replays(self):
        """The recorder writes its last board as `<stamp>-closing.json.gz`, so
        a frame is not always `<stamp>.json.gz`. Reading the last frame of the
        finished 19 September night looked for a file nobody had written."""
        root = pathlib.Path(tempfile.mkdtemp())
        (root / "scoreboard").mkdir(parents=True)
        for name in ("20260919T204914Z.json.gz", "20260920T064612Z-closing.json.gz"):
            with gzip.open(root / "scoreboard" / name, "wt") as f:
                json.dump({"events": []}, f)
        src = CaptureSource(root, "99999999T999999Z")
        self.assertEqual(src.frames(), ["20260919T204914Z", "20260920T064612Z"])
        self.assertEqual(src.stamp(), "20260920T064612Z")
        self.assertEqual(len(src.at("20260920T064612Z").history(1200)), 2)
        self.assertEqual(handlers.slate(src.at("20260920T064612Z"))["clock"]["index"], 1)

    def test_marks_find_the_night(self):
        by_stamp = {f["stamp"]: f for f in self.timeline["frames"]}
        texas_fg = by_stamp["20260913T004843Z"]
        self.assertGreaterEqual(texas_fg["marks"]["scores"], 1)
        self.assertEqual(by_stamp["20260913T005043Z"]["marks"]["finals"], 1)
        self.assertEqual(by_stamp["20260913T010643Z"]["marks"]["kickoffs"], 2)
        self.assertEqual(sum(f["marks"]["finals"] for f in self.timeline["frames"]), 3)


@unittest.skipUnless(HAVE, "capture not present")
class Changes(unittest.TestCase):
    def changes_at(self, stamp):
        return handlers.slate(capture(stamp))["changes"]

    def test_a_field_goal_is_read_as_one(self):
        found = [c for c in self.changes_at("20260913T004843Z") if c["game"] == OSU_TEX]
        score = next(c for c in found if c["kind"] == "score")
        self.assertEqual((score["team"], score["points"], score["label"]), (TEXAS, 3, "Field goal"))
        self.assertEqual(score["time"], "8:48 PM ET", "the slate's clock, not the device's")

    def test_kickoff_final_and_delay(self):
        at_0050 = self.changes_at("20260913T005043Z")
        self.assertIn(("final", CAM_FLA), {(c["kind"], c["game"]) for c in at_0050})
        self.assertIn(("kickoff", USM_AUB), {(c["kind"], c["game"]) for c in at_0050})
        self.assertIn(("delay", TOW_SC), {(c["kind"], c["game"]) for c in self.changes_at("20260913T014311Z")})

    def test_a_delay_that_lifts_before_kickoff_is_not_play_resuming(self):
        found = self.changes_at("20260913T002443Z")
        self.assertFalse([c for c in found if c["game"] == USM_AUB])

    def test_ids_are_stable_so_a_client_animates_once(self):
        a, b = self.changes_at("20260913T011443Z"), self.changes_at("20260913T011443Z")
        self.assertEqual([c["id"] for c in a], [c["id"] for c in b])
        self.assertEqual(len({c["id"] for c in a}), len(a))

    def test_the_feed_is_newest_first_and_keeps_the_score_as_it_was(self):
        out = handlers.slate(capture("20260913T011643Z"))
        self.assertTrue(out["feed"])
        self.assertEqual([f["at"] for f in out["feed"]], sorted((f["at"] for f in out["feed"]), reverse=True))
        osu = [f for f in out["feed"] if f["game"] == OSU_TEX and f["kind"] == "score"]
        self.assertTrue(osu)
        scores = [(f["away"]["score"], f["home"]["score"]) for f in osu]
        self.assertEqual(scores, sorted(scores, key=sum, reverse=True), "older feed lines keep older scores")
        self.assertNotIn("possession", {f["kind"] for f in out["feed"]})


class ChangeRules(unittest.TestCase):
    """The detector against fixture records nudged into each case."""

    @classmethod
    def setUpClass(cls):
        board = json.loads((REPO / "tests/fixtures/slate.json").read_text())
        cls.games = {g["id"]: g for g in parse.slate_records(board)}

    def nudge(self, event, **edits):
        before = self.games[event]
        after = copy.deepcopy(before)
        for path, value in edits.items():
            node = after
            *parents, leaf = path.split("__")
            for key in parents:
                node = node[key]
            node[leaf] = value
        return before, after

    def test_a_score_labelled_from_the_scoring_play(self):
        before, after = self.nudge(OSU_TEX, away__score=17, lastPlay={"text": "x", "type": "Passing Touchdown", "scoring": True})
        (c,) = [c for c in changes.between(before, after, "20260913T003500Z") if c["kind"] == "score"]
        self.assertEqual((c["points"], c["label"]), (7, "Touchdown"))

    def test_a_touchdown_and_its_extra_point_in_one_frame_is_a_touchdown(self):
        before, after = self.nudge(OSU_TEX, away__score=17, lastPlay={"text": "x", "type": "Extra Point Good", "scoring": True})
        (c,) = [c for c in changes.between(before, after, "s") if c["kind"] == "score"]
        self.assertEqual((c["points"], c["label"]), (7, "Touchdown"))

    def test_two_points_asks_the_play(self):
        before, after = self.nudge(OSU_TEX, home__score=2, lastPlay={"text": "x", "type": "Safety", "scoring": True})
        (c,) = [c for c in changes.between(before, after, "s") if c["kind"] == "score"]
        self.assertEqual(c["label"], "Safety")

    def test_without_a_scoring_play_the_points_decide(self):
        before, after = self.nudge(OSU_TEX, away__score=13, lastPlay={"text": "Kickoff", "type": "Kickoff", "scoring": False})
        (c,) = [c for c in changes.between(before, after, "s") if c["kind"] == "score"]
        self.assertEqual(c["label"], "Field goal")

    def test_a_correction_downward_is_not_a_score(self):
        before, after = self.nudge(OSU_TEX, away__score=7)
        self.assertFalse([c for c in changes.between(before, after, "s") if c["kind"] == "score"])

    def test_lead_change_and_possession(self):
        before, after = self.nudge(OSU_TEX, home__score=14, situation__possession=self.games[OSU_TEX]["home"]["id"])
        kinds = {c["kind"]: c for c in changes.between(before, after, "s")}
        self.assertEqual(kinds["lead"]["team"], self.games[OSU_TEX]["home"]["id"])
        self.assertIn("possession", kinds)
        self.assertLess(list(kinds).index("score"), list(kinds).index("possession"))

    def test_the_first_frame_has_no_changes(self):
        self.assertEqual(changes.diff(None, list(self.games.values()), "s"), [])
        self.assertEqual(handlers.slate(FixtureSource(REPO / "tests/fixtures"))["changes"], [])

    def test_caveat_travels(self):
        self.assertTrue(handlers.slate(FixtureSource(REPO / "tests/fixtures"))["changesCaveat"])


@unittest.skipUnless(HAVE, "capture not present")
class WholeNight(unittest.TestCase):
    """Stream the recording end to end with two games open, as a client would."""

    @classmethod
    def setUpClass(cls):
        cls.slept = []
        cls.events = list(handlers.stream(capture(), speed=60, games=(OSU_TEX, WAKE_PUR), sleep=cls.slept.append))

    def named(self, name):
        return [p for n, p in self.events if n == name]

    def test_every_frame_arrives_and_matches_its_contract(self):
        slates = self.named("slate")
        self.assertEqual(len(slates), 60)
        for s in slates:
            self.assertEqual(CONTRACTS.validate(s, "slate.schema.json"), [], s["asOf"])
        for g in self.named("game"):
            self.assertEqual(CONTRACTS.validate(g, "game.schema.json"), [], (g["event"], g["asOf"]))
        for c in self.named("clock"):
            self.assertEqual(CONTRACTS.validate(c, "stream.schema.json"), [])
        self.assertEqual(self.events[-1][0], "end")

    def test_every_display_name_has_a_short_form_on_every_frame(self):
        for s in self.named("slate"):
            for g in s["games"]:
                for side in (g["away"], g["home"]):
                    short = side["shortName"]
                    self.assertTrue(short, (side["location"], s["asOf"]))
                    self.assertLessEqual(len(short), len(side["location"]), side["location"])
                    if side["location"].upper() != side["abbr"].upper():
                        self.assertNotEqual(short.upper(), side["abbr"].upper(), side["location"])
        for d in self.named("game"):
            for side in (d["away"], d["home"]):
                self.assertTrue(side["shortName"])

    def test_no_raw_espn_text_reaches_a_payload_all_night(self):
        raw = r"[#()]|clock \d|^(Shotgun|No Huddle)|\b(1ST DOWN|TOUCHDOWN|NO GOOD|GOOD|KICK|PENALTY|NO PLAY)\b"
        for s in self.named("slate"):
            for g in s["games"]:
                if g["lastPlay"]:
                    self.assertNotRegex(g["lastPlay"]["text"], raw)
        for d in self.named("game"):
            for drive in d["drives"]:
                self.assertNotRegex(drive["result"], raw)
                for p in drive["plays"]:
                    self.assertNotRegex(p["text"], raw)
            for sp in d["scoringPlays"]:
                self.assertNotRegex(sp["text"], raw)

    def test_every_tile_is_drawn_exactly_once_on_every_frame(self):
        for s in self.named("slate"):
            placed = [g for sec in s["sections"] for g in sec["games"]] + ([s["spotlight"]] if s["spotlight"] else [])
            self.assertEqual(sorted(placed), sorted(g["id"] for g in s["games"]), s["asOf"])

    def test_the_clock_paces_the_recording(self):
        ticks = self.named("clock")
        self.assertEqual([t["index"] for t in ticks], list(range(60)))
        self.assertAlmostEqual(sum(self.slept), ticks[-1]["durationSeconds"] / 60, places=3)

    def test_nothing_goes_backwards_unannounced(self):
        seen_final, scores, drops = set(), {}, 0
        for s in self.named("slate"):
            corrections = {(c["game"], c["team"]) for c in s["changes"] if c["kind"] == "correction"}
            for g in s["games"]:
                if g["id"] in seen_final:
                    self.assertEqual(g["status"]["state"], "post", (g["id"], s["asOf"]))
                if g["status"]["state"] == "post":
                    seen_final.add(g["id"])
                for i, side in enumerate(("away", "home")):
                    now, was = g[side]["score"] or 0, scores.get((g["id"], side), 0)
                    if now < was:
                        drops += 1
                        self.assertIn((g["id"], g[side]["id"]), corrections, (g["id"], s["asOf"], was, now))
                    scores[(g["id"], side)] = now
        # Six scores came off the board that night - touchdowns called back for
        # a penalty or overturned on review (Memphis-Boise State, Jacksonville
        # State-Ohio, Southern Miss-Auburn, Cal Poly-San Jose State, Bowling
        # Green-Nebraska, Charlotte-Ole Miss) - and every one was announced.
        self.assertEqual(drops, 6)

    def test_a_reviewed_touchdown_reads_as_scored_taken_off_and_scored(self):
        boise = [(c["kind"], c["points"]) for s in self.named("slate") for c in s["changes"]
                 if c["game"] == "401860881" and "20260913T0054" <= c["id"][:13] <= "20260913T0059"
                 and c["kind"] in ("score", "correction")]
        self.assertEqual(boise, [("score", 6), ("correction", -6), ("score", 7)])

    def test_a_change_is_announced_once_across_the_night(self):
        ids = [c["id"] for s in self.named("slate") for c in s["changes"]]
        self.assertEqual(len(ids), len(set(ids)))
        texas = [c for s in self.named("slate") for c in s["changes"] if c["game"] == OSU_TEX and c["kind"] == "score"]
        self.assertEqual(len(texas), 4, "OSU-Texas scored four times while it was being recorded")

    def test_overtime_final_holds_on_every_frame(self):
        details = [g for g in self.named("game") if g["event"] == WAKE_PUR]
        self.assertEqual(len(details), 60)
        for d in details:
            self.assertTrue(d["status"]["completed"])
            self.assertEqual(d["status"]["overtimes"], 2)
            self.assertIsNone(d["possession"])
        last = details[-1]["drives"][-1]["plays"][-1]
        self.assertIn("Touchdown", last["type"], "a 2OT game ends on its scoring play, with no End of Game")
        for s in self.named("slate"):
            tile = next(g for g in s["games"] if g["id"] == WAKE_PUR)
            self.assertIn(WAKE_PUR, next(sec for sec in s["sections"] if sec["id"] == "finals")["games"])
            self.assertIn("overtime", tile["leverage"]["reasons"])

    def test_an_open_live_game_follows_the_board(self):
        frame, pairs = None, 0
        for name, payload in self.events:
            if name == "clock":
                frame = payload
            elif name == "game" and payload["event"] == OSU_TEX:
                self.assertEqual(payload["asOf"], frame["at"])
                pairs += 1
        self.assertGreater(pairs, 50)

    def test_starting_mid_night(self):
        events = list(handlers.stream(capture(), at="20260913T011443Z", speed=10, sleep=lambda s: None))
        self.assertEqual(events[0][1]["stamp"], "20260913T011443Z")
        with self.assertRaises(handlers.BadRequest):
            next(handlers.stream(capture(), at="eight pm"))


class _Moving(Source):
    """A recorded night played back against a fake clock, so it looks live:
    frames() is empty, and the board is whichever frame the clock has reached."""
    label = "moving-capture"

    def __init__(self, clock):
        self.base, self.clock = capture(), clock
        self.frames_ = self.base.frames()
        self.start = self.frames_[0]

    def _now(self) -> CaptureSource:
        reached = [f for f in self.frames_ if seconds_between(self.start, f) <= self.clock()]
        return self.base.at(reached[-1])

    def scoreboard(self):
        return self._now().scoreboard()

    def summary(self, event):
        return self._now().summary(event)

    def stamp(self):
        return self._now().stamp()

    def history(self, seconds):
        return self._now().history(seconds)


@unittest.skipUnless(HAVE, "capture not present")
class Budget(unittest.TestCase):
    """The night as if live: every tile from one scoreboard per window, and a
    summary only for the game somebody has open."""

    def test_the_whole_night_stays_inside_the_budget_with_several_clients(self):
        t = [0.0]
        clock = lambda: t[0]
        moving = _Moving(clock)
        duration = seconds_between(moving.frames_[0], moving.frames_[-1])
        src = Budgeted(moving, clock=clock)

        # Three clients: two watching the wall with OSU-Texas open, one the wall alone.
        def client(games):
            return handlers.stream(src, games=games, sleep=lambda s: None, budget=src.report)

        streams = [client((OSU_TEX,)), client((OSU_TEX,)), client(())]
        tiles_seen, slates = set(), 0
        while t[0] <= duration:
            for s in streams:
                for name, payload in itertools.takewhile(lambda e: e[0] not in ("ping", "budget"), s):
                    if name == "slate":
                        slates += 1
                        tiles_seen |= {g["id"] for g in payload["games"]}
            t[0] += 10                                    # clients wake every 10 s of the night

        report = src.report()
        self.assertTrue(report["within"], report)
        self.assertEqual(set(report["requests"]["summary"]), {OSU_TEX}, "no summary for a game nobody opened")
        self.assertLessEqual(report["requests"]["scoreboard"], duration // league.BUDGET["scoreboardSeconds"] + 1)
        self.assertLessEqual(report["requests"]["summary"][OSU_TEX], duration // league.BUDGET["summarySeconds"] + 1)
        self.assertEqual(len(tiles_seen), 86)
        self.assertGreater(slates, 3)

    def test_concurrent_clients_share_one_fetch(self):
        """Live ESPN takes a second or more to answer; the threaded server must
        not let every request that arrives meanwhile fetch its own board."""
        calls = []

        class Slow(Source):
            label = "slow"

            def scoreboard(self):
                calls.append("board")
                time.sleep(0.2)
                return {"events": []}

            def summary(self, event):
                calls.append(event)
                time.sleep(0.2)
                return None

        src = Budgeted(Slow(), clock=lambda: 0.0)
        threads = [threading.Thread(target=src.scoreboard) for _ in range(8)]
        threads += [threading.Thread(target=src.summary, args=(OSU_TEX,)) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(sorted(calls), sorted(["board", OSU_TEX]))
        self.assertEqual(src.report()["requests"]["total"], 2)

    def test_a_cache_hit_is_not_a_request(self):
        t = [0.0]
        src = Budgeted(_Moving(lambda: t[0]), clock=lambda: t[0])
        for _ in range(10):
            src.scoreboard()
            src.summary(OSU_TEX)
        self.assertEqual(src.report()["requests"]["total"], 2)
        t[0] = league.BUDGET["scoreboardSeconds"]
        src.scoreboard()
        self.assertEqual(src.report()["requests"]["scoreboard"], 2)


@unittest.skipUnless(HAVE, "capture not present")
class StreamOverHttp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(capture(), sleep=lambda s: None))
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def get(self, path):
        try:
            with urllib.request.urlopen(self.base + path, timeout=30) as r:
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as exc:
            with exc:
                return exc.code, dict(exc.headers), exc.read()

    def test_server_sent_events_from_a_moment(self):
        code, headers, body = self.get(f"/api/stream?at=20260913T011443Z&speed=100&games={OSU_TEX}")
        self.assertEqual(code, 200)
        self.assertEqual(headers["Content-Type"], "text/event-stream")
        events = []
        for block in body.decode().strip().split("\n\n"):
            lines = dict(line.split(": ", 1) for line in block.split("\n"))
            events.append((lines["event"], json.loads(lines["data"])))
        self.assertEqual([n for n, _ in events[:3]], ["clock", "slate", "game"])
        self.assertEqual(events[-1][0], "end")
        self.assertEqual(events[1][1]["clock"]["stamp"], "20260913T011443Z")

    def test_slate_and_game_at_a_moment(self):
        code, _, body = self.get("/api/slate?at=2026-09-13T00:48:43Z")
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(body)["clock"]["stamp"], "20260913T004843Z")
        code, _, body = self.get(f"/api/game/{OSU_TEX}?at=20260913T004843Z")
        self.assertEqual(json.loads(body)["asOf"], "2026-09-13T00:48:43Z")

    def test_bad_moments_and_the_timeline(self):
        self.assertEqual(self.get("/api/slate?at=soon")[0], 400)
        self.assertEqual(self.get("/api/stream?at=soon")[0], 400)
        self.assertEqual(self.get("/api/slate?at=20260913T000000Z")[0], 404)
        code, _, body = self.get("/api/replay")
        self.assertEqual(code, 200)
        self.assertEqual(len(json.loads(body)["frames"]), 60)

    def test_fixtures_have_no_timeline(self):
        with self.assertRaises(handlers.NotFound):
            handlers.replay(FixtureSource(REPO / "tests/fixtures"))


if __name__ == "__main__":
    unittest.main()
