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
        self.assertEqual(cap.at, "20260913T003400Z")
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
