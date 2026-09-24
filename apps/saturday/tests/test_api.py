"""Handlers, the dev server, doctor, and the contracts every client builds to."""
from __future__ import annotations

import json
import os
import pathlib
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest import mock

from api import doctor, handlers, server
from cfb import store
from cfb.sources import CaptureSource, FixtureSource, from_spec
from schema_lite import Validator

REPO = pathlib.Path(__file__).resolve().parents[1]
FIX = REPO / "tests/fixtures"
CONTRACTS = Validator(REPO / "contracts")
OSU_TEX, WAKE_PUR, OKST_ORE = "401856682", "401858224", "401856782"


class Handlers(unittest.TestCase):
    src = FixtureSource(FIX)

    def test_slate_matches_contract(self):
        out = handlers.slate(self.src)
        self.assertEqual(CONTRACTS.validate(out, "slate.schema.json"), [])
        self.assertEqual(out["spotlight"], OSU_TEX)
        self.assertTrue(out["replay"])
        self.assertEqual(sum(out["counts"].values()), len(out["games"]))
        by_state = {k: sum(1 for g in out["games"] if g["status"]["state"] == k and not g["status"]["delayed"]) for k in ("in", "pre", "post")}
        self.assertEqual((out["counts"]["live"], out["counts"]["pre"], out["counts"]["post"]), (by_state["in"], by_state["pre"], by_state["post"]))
        self.assertGreater(out["counts"]["live"], 20)
        self.assertEqual(out["asOf"], "2026-09-13T00:34:00Z")

    def test_game_matches_contract(self):
        for event in (OSU_TEX, WAKE_PUR, OKST_ORE):
            out = handlers.game(self.src, event)
            self.assertEqual(CONTRACTS.validate(out, "game.schema.json"), [], event)
            self.assertTrue(out["winProbabilityCaveat"])

    def test_game_takes_rank_from_the_board(self):
        out = handlers.game(self.src, OKST_ORE)
        self.assertEqual(out["away"]["rank"], 6)

    def test_teams_matches_contract(self):
        out = handlers.teams(self.src)
        self.assertEqual(CONTRACTS.validate(out, "team.schema.json"), [])
        self.assertEqual(len({t["id"] for t in out["teams"]}), len(out["teams"]))

    def test_unknown_game_is_not_found(self):
        with self.assertRaises(handlers.NotFound):
            handlers.game(self.src, "1")

    def test_contract_catches_a_broken_payload(self):
        out = handlers.slate(self.src)
        out["games"][0]["status"]["state"] = "halftime"
        del out["games"][0]["away"]["fill"]
        errs = CONTRACTS.validate(out, "slate.schema.json")
        self.assertTrue(any("halftime" in e for e in errs))
        self.assertTrue(any("missing fill" in e for e in errs))


class Capture(unittest.TestCase):
    root = REPO / "data/capture/2026-09-12"

    @unittest.skipUnless((REPO / "data/capture/2026-09-12/scoreboard").is_dir(), "capture not present")
    def test_capture_never_shows_a_later_result(self):
        src = CaptureSource(self.root, "20260913T003400Z")
        out = handlers.game(src, OSU_TEX)
        self.assertFalse(out["status"]["completed"])
        # Utah-Arkansas had not kicked off at this moment; its final exists on disk.
        self.assertIsNone(src.summary("401856670"))

    def test_source_spec(self):
        self.assertEqual(from_spec("fixtures", REPO).label, "fixtures")
        cap = from_spec("capture:data/capture/2026-09-12@20260913T003400Z", REPO)
        self.assertEqual(cap.moment, "20260913T003400Z")
        with self.assertRaises(ValueError):
            from_spec("nope", REPO)


class Server(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(FixtureSource(FIX)))
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def get(self, path, headers=None):
        req = urllib.request.Request(self.base + path, headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as exc:
            with exc:
                return exc.code, dict(exc.headers), exc.read()

    def test_slate_over_http_with_etag(self):
        code, headers, body = self.get("/api/slate")
        self.assertEqual(code, 200)
        self.assertEqual(headers["Access-Control-Allow-Origin"], "*")
        self.assertEqual(json.loads(body)["spotlight"], OSU_TEX)
        code, _, _ = self.get("/api/slate", {"If-None-Match": headers["ETag"]})
        self.assertEqual(code, 304)

    def test_game_and_404s(self):
        self.assertEqual(self.get(f"/api/game/{WAKE_PUR}")[0], 200)
        code, _, body = self.get("/api/game/1")
        self.assertEqual(code, 404)
        self.assertIn("reason", json.loads(body))
        self.assertEqual(self.get("/api/nothing")[0], 404)

    def test_health(self):
        code, _, body = self.get("/api/health")
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(body)["source"], "fixtures")


class Doctor(unittest.TestCase):
    def test_offline_ready_warns_about_cfbd_without_failing(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CFBD_API_KEY", None)
            report = doctor.check(REPO, offline=True)
        self.assertEqual(report["exit_code"], 0)
        cfbd = next(c for c in report["checks"] if c["name"] == "cfbd")
        self.assertEqual(cfbd["status"], "warn")
        self.assertIn("CFBD_API_KEY", report["next_command"])

    def test_missing_data_exits_4(self):
        report = doctor.check(pathlib.Path("/nonexistent"), offline=True)
        self.assertEqual(report["exit_code"], 4)
        self.assertTrue(report["next_command"])


class History(unittest.TestCase):
    def test_schema_keys_on_source_and_id(self):
        con = store.connect(":memory:")
        cols = {r[1]: r[5] for r in con.execute("PRAGMA table_info(team)")}
        self.assertEqual((cols["source"], cols["id"]), (1, 2))
        con.execute("INSERT INTO team (source, id, school) VALUES ('espn', '194', 'Ohio State')")
        con.execute("INSERT INTO team (source, id, school) VALUES ('cfbd', '194', 'Somewhere Else')")
        self.assertEqual(con.execute("SELECT COUNT(*) FROM team").fetchone()[0], 2)
        con.close()


if __name__ == "__main__":
    unittest.main()


MERGED = REPO / "data/capture/2026-09-19-merged"


class RedZoneChannel(unittest.TestCase):
    """Which game the stadium stands in, over a real Saturday."""

    def test_the_channel_matches_its_contract(self):
        out = handlers.redzone(FixtureSource(FIX))
        self.assertEqual(CONTRACTS.validate(out, "redzone.schema.json"), [])

    def test_the_caveat_rides_with_the_ranking(self):
        self.assertTrue(handlers.redzone(FixtureSource(FIX))["caveat"].strip())

    def test_only_a_live_game_may_hold_the_bowl(self):
        """A channel that opens on a game that finished at lunchtime is worse
        than one that says nothing is running."""
        out = handlers.redzone(FixtureSource(FIX))
        if out["focus"]:
            game = next(g for g in out["games"] if g["event"] == out["focus"])
            self.assertEqual(game["state"], "in")

    @unittest.skipUnless((MERGED / "scoreboard").is_dir(), "merged capture not present")
    def test_the_focus_is_a_function_of_the_moment_not_of_who_asked(self):
        """Two headsets that joined the night at different times must be in the
        same game. Nothing is remembered between requests, so the only way that
        holds is if the same moment always walks to the same answer."""
        src = CaptureSource(MERGED, "20260920T013000Z")
        first = handlers.redzone(src)["focus"]
        for _ in range(3):
            self.assertEqual(handlers.redzone(CaptureSource(MERGED, "20260920T013000Z"))["focus"], first)
        self.assertTrue(first)

    @unittest.skipUnless((MERGED / "scoreboard").is_dir(), "merged capture not present")
    def test_the_bowl_does_not_thrash_over_seventy_four_games(self):
        """The night of 19 September, an hour of it, minute by minute: 74 games
        on the slate, up to 31 of them live at once and 9 in the red zone
        together. Taking whichever game ranks first each minute changed the
        bowl 94 times in seven and a half hours, half of those visits lasting a
        minute or two - a fade of the whole world, twice a minute.

        This is the guard on that. An hour is 20 changes if the bowl is picking
        greedily and about 7 if the dwell is holding."""
        src = CaptureSource(MERGED, "20260920T013000Z")
        frames = [f for f in src.frames() if "20260920T0030" <= f <= "20260920T0130"]
        self.assertGreater(len(frames), 30, "an hour of frames to walk")

        focus, changes_seen = "", 0
        for stamp in frames:
            now = handlers.redzone(CaptureSource(MERGED, stamp))["focus"]
            if now != focus:
                changes_seen += 1
            focus = now
        self.assertLessEqual(changes_seen, 12,
                             f"the bowl changed game {changes_seen} times in an hour")
        self.assertGreater(changes_seen, 0, "and it did follow the Saturday")

    @unittest.skipUnless((MERGED / "scoreboard").is_dir(), "merged capture not present")
    def test_the_bowl_is_never_sent_to_a_game_this_source_cannot_draw(self):
        """19 September kept the live snapshots of six games and not the other
        sixty-eight, by the sampling rule. ECU at Old Dominion ranked first at
        half past midnight and the stadium opened on a black field, because the
        ranking was asked which game deserved the bowl and never asked whether
        it could be drawn."""
        for stamp in ("20260920T003000Z", "20260920T013000Z", "20260920T020000Z"):
            out = handlers.redzone(CaptureSource(MERGED, stamp))
            focus = next((g for g in out["games"] if g["event"] == out["focus"]), None)
            self.assertIsNotNone(focus, f"{stamp}: the focus is on the slate")
            self.assertEqual(focus["detail"], "available",
                             f"{stamp}: the bowl was sent to {focus['event']}, which has no plays here")

    @unittest.skipUnless((MERGED / "scoreboard").is_dir(), "merged capture not present")
    def test_a_game_that_cannot_be_drawn_is_still_listed_and_still_says_so(self):
        """It is not hidden - it is part of the night, and its score belongs on
        the panel. It is marked, so the client can refuse to open it."""
        out = handlers.redzone(CaptureSource(MERGED, "20260920T013000Z"))
        shut = [g for g in out["games"] if g["detail"] != "available"]
        self.assertTrue(shut, "a sampled capture has games it cannot draw")
        self.assertTrue(all(g["detail"] in ("afterFinal", "unavailable") for g in shut))

    @unittest.skipUnless((MERGED / "scoreboard").is_dir(), "merged capture not present")
    def test_every_live_game_is_ranked_and_the_ball_is_placed(self):
        out = handlers.redzone(CaptureSource(MERGED, "20260920T013000Z"))
        live = [g for g in out["games"] if g["state"] == "in"]
        self.assertGreater(len(live), 20, "a Saturday night has plenty running")
        self.assertEqual(out["counts"]["live"], len(live))
        self.assertEqual([g["urgency"] for g in live], sorted((g["urgency"] for g in live), reverse=True))
        with_ball = [g for g in live if g["home"]["hasBall"] or g["away"]["hasBall"]]
        self.assertTrue(with_ball, "somebody has the ball in a live game")
        for g in with_ball:
            self.assertFalse(g["home"]["hasBall"] and g["away"]["hasBall"],
                             "both sides cannot have the ball")
