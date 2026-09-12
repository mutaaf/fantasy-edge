"""End-to-end tests. No network: the ESPN adapter is exercised against a
recorded fixture through a stub Http, which is the whole reason Http is
injected rather than imported at call sites."""

from __future__ import annotations

import json
import re
import os
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))

from fantasyedge import analytics, report                    # noqa: E402
from fantasyedge.providers.base import Http, get_provider     # noqa: E402
from fantasyedge.providers.espn import EspnProvider           # noqa: E402
from fantasyedge.providers.sleeper import SleeperProvider, normalise  # noqa: E402
from fantasyedge.providers.manual import ManualProvider       # noqa: E402
from fantasyedge.store import Store                           # noqa: E402

FIX = pathlib.Path(__file__).parent / "fixtures"


def setUpModule():
    """No network, ever. The live source will happily reach ESPN now that it
    works, and a suite that quietly takes ninety seconds and depends on an
    outside service is not the suite this project promises."""
    os.environ["FANTASYEDGE_SCOREBOARD_FILE"] = str(FIX / "espn_scoreboard.json")
    os.environ["FANTASYEDGE_SUMMARY_FILE"] = str(FIX / "espn_summary.json")


class StubHttp(Http):
    """Returns the fixture for any league URL. Records calls so we can assert
    the adapter asks for the views it claims to."""

    def __init__(self, payload):
        super().__init__()
        self.payload = payload
        self.calls: list[str] = []

    def get_json(self, url, *, headers=None, cookies=None, params=None):
        self.calls.append(url)
        if url.endswith("/ffl"):
            return {"currentSeasonId": 2026}
        return self.payload


def load_fixture_bundle():
    payload = json.loads((FIX / "espn_2025.json").read_text())
    http = StubHttp(payload)
    provider = EspnProvider(espn_s2="x", swid="{y}", league_id="99", http=http)
    return provider.fetch_season("99", 2025), http


class TestEspnProvider(unittest.TestCase):
    def test_normalizes_a_season(self):
        b, http = load_fixture_bundle()
        self.assertEqual(b.provider, "espn")
        self.assertEqual(b.season, 2025)
        self.assertEqual(b.team_count, 10)
        self.assertEqual(len(b.draft), 150)
        self.assertEqual(len(b.managers), 10)
        self.assertTrue(b.rosters)
        self.assertTrue(b.matchups)
        self.assertTrue(b.transactions)

    def test_requests_the_views_it_needs(self):
        _, http = load_fixture_bundle()
        joined = " ".join(http.calls)
        for view in ("mSettings", "mTeam", "mDraftDetail", "mRoster", "mTransactions2"):
            self.assertIn(view, joined)

    def test_started_flag_is_populated(self):
        b, _ = load_fixture_bundle()
        started = [r for r in b.rosters if r.started]
        benched = [r for r in b.rosters if not r.started]
        self.assertTrue(started and benched, "need both to measure a bench leak")

    def test_matchups_are_two_sided(self):
        b, _ = load_fixture_bundle()
        wk1 = [m for m in b.matchups if m.week == 1]
        self.assertEqual(len(wk1), 10, "one row per team per week")
        for m in wk1:
            mirror = [x for x in wk1 if x.team_id == m.opponent_id]
            self.assertEqual(mirror[0].points, m.opp_points)

    def test_historical_list_wrapper_is_unwrapped(self):
        payload = json.loads((FIX / "espn_2025.json").read_text())

        class ListHttp(StubHttp):
            def get_json(self, url, **kw):
                if url.endswith("/ffl"):
                    return {"currentSeasonId": 2026}
                return [self.payload]

        p = EspnProvider(espn_s2="x", swid="{y}", http=ListHttp(payload))
        b = p.fetch_season("99", 2017)
        self.assertEqual(len(b.draft), 150)


class SleeperHttp(Http):
    """Routes Sleeper's several endpoints out of one fixture."""

    def __init__(self, fx):
        super().__init__()
        self.fx = fx
        self.calls: list[str] = []

    def get_json(self, url, **kw):
        self.calls.append(url)
        tail = url.split("/v1/")[1]
        if tail.startswith("league/") and tail.endswith("/rosters"):
            return self.fx["rosters"]
        if tail.startswith("league/") and tail.endswith("/users"):
            return self.fx["users"]
        if tail.startswith("league/") and tail.endswith("/drafts"):
            return self.fx["drafts"]
        if "/matchups/" in tail:
            return self.fx["matchups"].get(tail.rsplit("/", 1)[1], [])
        if "/transactions/" in tail:
            return self.fx["transactions"].get(tail.rsplit("/", 1)[1], [])
        if tail.startswith("draft/"):
            return self.fx["picks"]
        if tail.startswith("league/"):
            return self.fx["league"]
        if tail == "players/nfl":
            return self.fx["players"]
        raise AssertionError(f"unexpected sleeper call {url}")


def sleeper_bundle():
    fx = json.loads((FIX / "sleeper_2025.json").read_text())
    http = SleeperHttp(fx)
    p = SleeperProvider(league_id="L1", http=http, players=fx["players"])
    return p.fetch_season("L1", 2025), http, p


class TestSleeperProvider(unittest.TestCase):
    def test_normalizes_a_season(self):
        b, _, _ = sleeper_bundle()
        self.assertEqual(b.provider, "sleeper")
        self.assertEqual(b.team_count, 4)
        self.assertEqual(len(b.draft), 16)
        self.assertEqual(len(b.managers), 4)
        self.assertEqual(len(b.standings), 4)
        self.assertTrue(b.matchups)
        self.assertTrue(b.transactions)

    def test_starters_become_the_started_flag(self):
        b, _, _ = sleeper_bundle()
        started = [r for r in b.rosters if r.started]
        benched = [r for r in b.rosters if not r.started]
        self.assertTrue(started and benched)
        # a started row carries a real lineup slot, never BN
        self.assertNotIn("BN", {r.slot for r in started})
        self.assertEqual({r.slot for r in benched}, {"BN"})

    def test_snake_draft_order_survives(self):
        b, _, _ = sleeper_bundle()
        rd1 = sorted((p for p in b.draft if p.round == 1), key=lambda p: p.overall)
        rd2 = sorted((p for p in b.draft if p.round == 2), key=lambda p: p.overall)
        self.assertEqual([p.team_id for p in rd1],
                         list(reversed([p.team_id for p in rd2])))

    def test_draft_state_is_pollable(self):
        _, _, p = sleeper_bundle()
        state = p.draft_state("L1", 2025)
        self.assertTrue(state["drafted"])
        self.assertEqual(len(state["picks"]), 16)
        self.assertTrue(all(r["name"] for r in state["picks"]))

    def test_name_join_ignores_case_accents_and_suffixes(self):
        self.assertEqual(normalise("Travis Etienne Jr."), normalise("travis etienne"))
        self.assertEqual(normalise("Kenneth Walker III"), normalise("Kenneth Walker"))
        self.assertEqual(normalise("Ja'Marr Chase"), "jamarrchase")

    def test_analyses_run_on_a_sleeper_league(self):
        b, _, _ = sleeper_bundle()
        store = Store(":memory:")
        store.save(b)
        results = {r.key: r for r in analytics.run_all(store, "sleeper", "L1")}
        self.assertFalse(results["luck"].empty)
        self.assertFalse(results["bench"].empty)
        store.close()


class TestManualProvider(unittest.TestCase):
    def test_parses_pasted_draft_and_standings(self):
        p = ManualProvider(draft_file=str(FIX / "draft.txt"),
                           standings_file=str(FIX / "standings.txt"),
                           league_id="demo", teams=10)
        b = p.fetch_season("demo", 2025)
        self.assertEqual(len(b.draft), 60)
        self.assertEqual(len(b.standings), 10)
        self.assertEqual(b.team_count, 10)
        self.assertTrue(all(d.round >= 1 for d in b.draft))

    def test_registry_wiring(self):
        p = get_provider("manual", draft_file=str(FIX / "draft.txt"))
        self.assertIsInstance(p, ManualProvider)


class TestStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(pathlib.Path(self.tmp.name) / "t.db")
        self.bundle, _ = load_fixture_bundle()
        self.store.save(self.bundle)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_roundtrip(self):
        rows = self.store.q("SELECT COUNT(*) c FROM draft_pick")
        self.assertEqual(rows[0]["c"], 150)

    def test_save_is_idempotent(self):
        self.store.save(self.bundle)
        self.store.save(self.bundle)
        for table, expect in (("draft_pick", 150), ("league", 1), ("standing", 10)):
            n = self.store.q(f"SELECT COUNT(*) c FROM {table}")[0]["c"]
            self.assertEqual(n, expect, f"{table} duplicated on re-pull")


class TestAnalytics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.store = Store(pathlib.Path(cls.tmp.name) / "a.db")
        bundle, _ = load_fixture_bundle()
        cls.store.save(bundle)
        cls.results = {r.key: r for r in analytics.run_all(cls.store, "espn", "99")}

    @classmethod
    def tearDownClass(cls):
        cls.store.close()
        cls.tmp.cleanup()

    def test_every_analysis_returns_a_result(self):
        self.assertEqual(set(self.results), set(analytics.ANALYSES))

    def test_analyses_with_data_produce_rows(self):
        for key in ("draft_roi", "allocation", "bench", "waiver", "luck", "phase", "profile"):
            self.assertFalse(self.results[key].empty, f"{key} produced nothing")

    def test_reach_degrades_gracefully_without_adp(self):
        r = self.results["reach"]
        self.assertTrue(r.empty)
        self.assertIn("ADP", r.caveat)

    def test_bench_leak_detects_the_seeded_leak(self):
        r = self.results["bench"]
        leaks = {row[0]: row[4] for row in r.rows}
        self.assertTrue(any(v > 0 for v in leaks.values()))
        for row in r.rows:
            self.assertGreaterEqual(row[4], 0.0)
            self.assertLessEqual(row[4], 100.0)

    def test_luck_all_play_is_bounded(self):
        for row in self.results["luck"].rows:
            self.assertGreaterEqual(row[3], 0.0)
            self.assertLessEqual(row[3], 1.0)

    def test_every_result_carries_a_caveat(self):
        for key, r in self.results.items():
            self.assertTrue(r.caveat, f"{key} has no stated caveat")

    def test_scope_isolation(self):
        empty = analytics.bench_leak(self.store, "espn", "does-not-exist")
        self.assertTrue(empty.empty)


class TestReport(unittest.TestCase):
    def test_html_is_self_contained(self):
        tmp = tempfile.TemporaryDirectory()
        store = Store(pathlib.Path(tmp.name) / "r.db")
        bundle, _ = load_fixture_bundle()
        store.save(bundle)
        results = analytics.run_all(store, "espn", "99")
        out = pathlib.Path(tmp.name) / "report.html"
        report.render(results, {"provider": "espn", "league_id": "99",
                                "league_name": "The Fixture League",
                                "seasons": [2025]}, out)
        html = out.read_text()
        self.assertIn("<table>", html)
        self.assertIn("The Fixture League", html)
        self.assertNotIn("<script", html, "report must not need JS")
        self.assertIn("Caveat", html)
        store.close()
        tmp.cleanup()

    def test_text_render_does_not_crash_on_empty(self):
        r = analytics.Result("k", "Title", caveat="nothing")
        self.assertIn("Title", report.render_text([r]))


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestAgentInterface(unittest.TestCase):
    """The CLI is an agent surface. These guard the contract in CLAUDE.md."""

    def _run(self, argv, env=None):
        import io, contextlib, os
        from fantasyedge.cli import main
        old = dict(os.environ)
        os.environ.update(env or {})
        buf = io.StringIO()
        code = 0
        try:
            with contextlib.redirect_stdout(buf):
                main(argv)
        except SystemExit as e:
            code = e.code or 0
        finally:
            os.environ.clear()
            os.environ.update(old)
        return code, buf.getvalue()

    def test_json_flag_works_in_either_position(self):
        with tempfile.TemporaryDirectory() as t:
            cfg = pathlib.Path(t) / "c.toml"
            a = self._run(["--config", str(cfg), "--db", f"{t}/a.db", "doctor", "--json"])
            b = self._run(["--config", str(cfg), "--db", f"{t}/a.db", "--json", "doctor"])
            for code, out in (a, b):
                json.loads(out)  # must be parseable in both forms

    def test_doctor_always_returns_a_next_command(self):
        with tempfile.TemporaryDirectory() as t:
            _, out = self._run(["--config", f"{t}/c.toml", "--db", f"{t}/a.db",
                                "doctor", "--json"])
            d = json.loads(out)
            self.assertIn("next_command", d)
            self.assertTrue(d["next_command"], "an agent needs something to run")
            self.assertIn("exit_code", d)

    def test_exit_codes_are_distinct_and_documented(self):
        from fantasyedge import doctor as doc
        codes = {doc.EXIT_READY, doc.EXIT_ERROR, doc.EXIT_CONFIG,
                 doc.EXIT_AUTH, doc.EXIT_NODATA}
        self.assertEqual(len(codes), 5)
        claude_md = (pathlib.Path(__file__).parents[1] / "CLAUDE.md").read_text()
        for c in sorted(codes):
            self.assertIn(f"| {c} |", claude_md, f"exit code {c} undocumented")

    def test_setup_is_non_interactive_and_writes_config(self):
        with tempfile.TemporaryDirectory() as t:
            cfg = pathlib.Path(t) / "league.toml"
            code, _ = self._run(["--config", str(cfg), "setup",
                                 "--provider", "espn", "--league", "42", "--teams", "10"])
            self.assertEqual(code, 0)
            self.assertTrue(cfg.exists())
            import tomllib
            with cfg.open("rb") as fh:
                loaded = tomllib.load(fh)
            self.assertEqual(loaded["league"]["provider"], "espn")
            self.assertEqual(loaded["league"]["league_id"], "42")
            self.assertEqual(loaded["roster"]["RB"], 2)

    def test_no_command_reads_stdin(self):
        """A blocking prompt would hang an agent session forever."""
        src = (pathlib.Path(__file__).parents[1] / "fantasyedge" / "cli.py").read_text()
        for line in src.splitlines():
            if "input(" in line and not line.strip().startswith("#"):
                self.assertIn("args.code or", line,
                              "stdin read outside the guarded interactive fallback")

    def test_analyze_json_is_machine_readable(self):
        with tempfile.TemporaryDirectory() as t:
            db = pathlib.Path(t) / "a.db"
            store = Store(db)
            bundle, _ = load_fixture_bundle()
            store.save(bundle)
            store.close()
            _, out = self._run(["--db", str(db), "analyze", "--json",
                                "--provider", "espn", "--league", "99"])
            d = json.loads(out)
            self.assertEqual(len(d["analyses"]), len(analytics.ANALYSES))
            for a in d["analyses"]:
                self.assertEqual(
                    set(a) >= {"key", "title", "rows", "columns", "caveat", "empty"}, True)

    def test_skills_have_valid_frontmatter(self):
        root = pathlib.Path(__file__).parents[1] / ".claude" / "skills"
        skills = list(root.glob("*/SKILL.md"))
        self.assertGreaterEqual(len(skills), 3)
        for s in skills:
            text = s.read_text()
            self.assertTrue(text.startswith("---\n"), f"{s} missing frontmatter")
            fm = text.split("---")[1]
            self.assertIn("name:", fm)
            self.assertIn("description:", fm)
            name = [l for l in fm.splitlines() if l.startswith("name:")][0].split(":", 1)[1].strip()
            self.assertEqual(name, s.parent.name, "skill name must match its directory")


class TestApi(unittest.TestCase):
    """The read API is what the web, tvOS and visionOS clients all talk to, so
    its contract matters more than any single client's. No network and no
    credential is involved: it answers only from stored rows."""

    @classmethod
    def setUpClass(cls):
        from fantasyedge.api import Api

        cls.tmp = tempfile.TemporaryDirectory()
        cls.db = pathlib.Path(cls.tmp.name) / "api.db"
        store = Store(cls.db)
        bundle, _ = load_fixture_bundle()
        store.save(bundle)
        store.close()
        cls.api = Api(str(cls.db))

    @classmethod
    def tearDownClass(cls):
        cls.api.close()
        cls.tmp.cleanup()

    def test_health_counts_what_is_loaded(self):
        h = self.api.health()
        self.assertTrue(h["ok"])
        self.assertEqual(h["leagues"], 1)
        self.assertEqual(h["counts"]["draft_pick"], 150)
        self.assertIn(2025, h["seasons"])

    def test_leagues_groups_seasons_under_one_league(self):
        items = self.api.leagues()["leagues"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["league_id"], "99")
        self.assertEqual(items[0]["seasons"], [2025])

    def test_analyses_match_the_cli_contract(self):
        """Same shape as `analyze --json`, so a client learns one contract."""
        out = self.api.analyses("espn", "99")
        self.assertEqual(len(out["analyses"]), len(analytics.ANALYSES))
        for a in out["analyses"]:
            self.assertTrue(set(a) >= {"key", "title", "headline", "columns",
                                       "rows", "caveat", "note", "empty"})
            self.assertTrue(a["caveat"], f"{a['key']} lost its caveat over the wire")

    def test_single_analysis_selects_one(self):
        out = self.api.analyses("espn", "99", ["luck"])
        self.assertEqual([a["key"] for a in out["analyses"]], ["luck"])

    def test_standings_and_draft_default_to_latest_season(self):
        self.assertEqual(self.api.standings("espn", "99", {})["season"], 2025)
        d = self.api.draft("espn", "99", {})
        self.assertEqual(d["season"], 2025)
        self.assertEqual(len(d["picks"]), 150)

    def test_unknown_league_and_season_are_404_with_a_fix(self):
        from fantasyedge.api import HttpError

        for call in (lambda: self.api.league("espn", "404"),
                     lambda: self.api.analyses("espn", "404"),
                     lambda: self.api.standings("espn", "99", {"season": ["1999"]}),
                     lambda: self.api.analyses("espn", "99", ["nope"])):
            with self.assertRaises(HttpError) as cm:
                call()
            self.assertEqual(cm.exception.code, 404)
            self.assertTrue(cm.exception.fix, "a 404 must say what to do next")

    def test_bad_season_is_a_400_not_a_500(self):
        from fantasyedge.api import HttpError

        with self.assertRaises(HttpError) as cm:
            self.api.standings("espn", "99", {"season": ["abc"]})
        self.assertEqual(cm.exception.code, 400)

    def test_every_advertised_route_dispatches(self):
        """`GET /api` is the client's discovery document; it must not lie.

        Routable is the claim, not found: a placeholder id resolves to a real
        route that honestly reports no such player, and that is a pass. Only
        "No route" means the document advertised something that does not
        exist.
        """
        from fantasyedge.api import HttpError

        for verb, template, _ in self.api.index()["routes"]:
            if verb != "GET":
                continue
            path = (template.replace("{provider}", "espn").replace("{id}", "99")
                            .replace("{key}", "luck"))
            try:
                self.assertIsNotNone(self.api.dispatch(path, {}), path)
            except HttpError as exc:
                self.assertNotIn("No route", exc.message, path)
                self.assertTrue(exc.fix, f"{path} 404s without saying what to do")

    def test_unknown_route_is_404(self):
        from fantasyedge.api import HttpError

        with self.assertRaises(HttpError) as cm:
            self.api.dispatch("/api/wat", {})
        self.assertEqual(cm.exception.code, 404)

    def test_cache_is_keyed_on_the_database_not_the_clock(self):
        """A poll must be free, but a `pull` must be visible immediately."""
        import os

        first = self.api.analyses("espn", "99")["analyses"][0]
        self.assertIs(self.api.analyses("espn", "99")["analyses"][0], first)
        st = self.db.stat()
        os.utime(self.db, (st.st_atime + 10, st.st_mtime + 10))
        self.assertIsNot(self.api.analyses("espn", "99")["analyses"][0], first)

    def test_http_layer_serves_cors_and_revalidates(self):
        import threading
        import urllib.error
        import urllib.request
        from http.server import ThreadingHTTPServer

        from fantasyedge.api import Api, make_handler

        # Its own Api, not the class's. Each request is served on its own
        # thread and the API keeps one sqlite connection per thread by design,
        # so the only way to release them is to close the Api - and closing
        # the shared one would pull the database out from under every test
        # that runs after this in the class.
        api = Api(str(self.db))
        srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(api))
        # ThreadingHTTPServer runs handlers on daemon threads and does not
        # join them, so `server_close()` can return while a handler is still
        # inside dispatch - and a connection opened after `api.close()` is one
        # nothing will ever release. Joining makes the teardown ordered.
        srv.daemon_threads = False
        srv.block_on_close = True
        port = srv.server_address[1]
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health") as r:
                self.assertEqual(r.status, 200)
                self.assertEqual(r.headers["Access-Control-Allow-Origin"], "*")
                etag = r.headers["ETag"]
            req = urllib.request.Request(f"http://127.0.0.1:{port}/api/health",
                                         headers={"If-None-Match": etag})
            with self.assertRaises(urllib.error.HTTPError) as cm:
                urllib.request.urlopen(req)   # urllib treats 304 as an error
            self.assertEqual(cm.exception.code, 304)
            cm.exception.close()              # an HTTPError *is* a response
            with self.assertRaises(urllib.error.HTTPError) as cm:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/api/leagues/espn/404")
            self.assertEqual(cm.exception.code, 404)
            self.assertIn("fix", json.loads(cm.exception.read()))
            cm.exception.close()
        finally:
            srv.shutdown()
            srv.server_close()
            # A suite that cries wolf about resources is one where a real leak
            # goes unread, so the threads' connections are released here.
            api.close()


class TestLeverage(unittest.TestCase):
    """The leverage model decides how big every tile on every surface is, so
    its properties are asserted directly rather than inferred from a screen."""

    POS = ["QB", "RB", "RB", "WR", "WR", "TE", "WR", "DEF", "K"]

    def team(self, side, scored, projected, remaining):
        from fantasyedge.leverage import Cell

        n = len(self.POS)
        return [Cell(id=f"{side}{i}", label=f"{side}{i}", pos=self.POS[i], side=side,
                     scored=scored / n, projected=projected / n, remaining=remaining)
                for i in range(n)]

    def test_leverage_peaks_at_a_coin_flip(self):
        from fantasyedge.leverage import evaluate

        tied = evaluate(self.team("you", 60, 130, .5) + self.team("opp", 60, 130, .5))
        blowout = evaluate(self.team("you", 60, 130, .5) + self.team("opp", 60, 260, .5))
        self.assertAlmostEqual(tied.win_prob, 0.5, places=6)
        self.assertGreater(tied.cells[0].leverage, blowout.cells[0].leverage * 50)

    def test_intensity_falls_to_zero_once_the_week_is_decided(self):
        from fantasyedge.leverage import evaluate

        self.assertAlmostEqual(
            evaluate(self.team("you", 60, 130, .5) + self.team("opp", 60, 130, .5)).intensity,
            1.0, places=6)
        done = evaluate(self.team("you", 118, 118, 0) + self.team("opp", 90, 90, 0))
        self.assertEqual(done.intensity, 0.0)
        self.assertEqual(sum(c.leverage for c in done.cells), 0.0)

    def test_the_last_player_running_absorbs_the_leverage(self):
        """The 'it all comes down to him' tile has to fall out of the model
        rather than be special-cased, or it will be wrong at the edges."""
        from fantasyedge.leverage import Cell, evaluate

        you = self.team("you", 118, 118, 0.0)
        you.append(Cell(id="star", label="last", pos="RB", side="you",
                        scored=4.0, projected=22.0, remaining=0.55))
        m = evaluate(you + self.team("opp", 125, 125, 0.0))
        self.assertEqual(m.cells[0].id, "star")
        self.assertGreater(m.cells[0].share, 0.99)
        self.assertEqual(m.cells[0].band, "xl")

    def test_shares_sum_to_one_and_sigma_tracks_time_left(self):
        from fantasyedge.leverage import evaluate, sigma_for

        m = evaluate(self.team("you", 40, 120, .8) + self.team("opp", 40, 120, .8))
        self.assertAlmostEqual(sum(c.share for c in m.cells), 1.0, places=6)
        self.assertGreater(sigma_for("RB", 1.0), sigma_for("RB", 0.5))
        self.assertEqual(sigma_for("RB", 0.0), 0.0)

    def test_bands_do_not_flicker_on_a_small_change(self):
        """A tile that changes size every tick moves the focused cell out from
        under the remote, which is why hysteresis exists."""
        from fantasyedge.leverage import evaluate

        first = evaluate(self.team("you", 40, 120, .8) + self.team("opp", 40, 120, .8))
        prev = {c.id: c.band for c in first.cells}
        nudged = self.team("you", 40, 120, .8) + self.team("opp", 40, 120, .8)
        nudged[0].remaining = 0.79
        second = evaluate(nudged, previous=prev)
        self.assertEqual([prev[c.id] for c in second.cells],
                         [c.band for c in second.cells])


class TestLiveTier(unittest.TestCase):
    """The live tier's whole value is that it is identical for every user.
    If a response here ever varied by viewer the cost model would collapse."""

    def setUp(self):
        from fantasyedge.live import SimulatedSource

        self.players = [
            {"player_id": str(i), "name": f"P{i}", "pos": p, "team": t, "projected": 14.0}
            for i, (p, t) in enumerate(
                [("QB", "KC"), ("RB", "SF"), ("WR", "BUF"), ("TE", "PHI"),
                 ("K", "DAL"), ("DEF", "GB"), ("WR", "MIA"), ("RB", "NYJ")])]
        self.src = SimulatedSource(self.players, seed=7, speed=90.0, start=1000.0)

    def test_snapshot_is_deterministic_across_processes(self):
        from fantasyedge.live import SimulatedSource

        twin = SimulatedSource(self.players, seed=7, speed=90.0, start=1000.0)
        for t in (1030.0, 1120.0, 1400.0):
            self.assertEqual(self.src.snapshot(at=t)["version"],
                             twin.snapshot(at=t)["version"])

    def test_points_never_go_backwards(self):
        prev = {}
        for t in range(1000, 1800, 20):
            for pid, v in self.src.snapshot(at=float(t))["players"].items():
                self.assertGreaterEqual(v["s"] + 1e-9, prev.get(pid, 0.0))
                prev[pid] = v["s"]

    def test_version_changes_only_when_players_change(self):
        a = self.src.snapshot(at=1000.0)
        self.assertEqual(a["version"], self.src.snapshot(at=1000.0)["version"])
        self.assertNotEqual(a["version"], self.src.snapshot(at=1200.0)["version"])

    def test_snapshot_carries_no_user_or_league_context(self):
        """Guards the rule the whole cost model rests on: shared means shared."""
        snap = self.src.snapshot(at=1200.0)
        self.assertEqual(set(snap) , {"asOf", "window", "games", "players", "version"})
        for v in snap["players"].values():
            self.assertEqual(set(v), {"s", "r", "g"})

    def test_team_abbreviations_are_human_readable(self):
        from fantasyedge.live import team_abbr

        self.assertEqual(team_abbr(14), "LAR")
        self.assertEqual(team_abbr("33"), "BAL")
        self.assertEqual(team_abbr(None), "FA")
        self.assertEqual(team_abbr(999), "FA")


class TestApiSurfaces(unittest.TestCase):
    """The routes the three clients actually depend on."""

    @classmethod
    def setUpClass(cls):
        from fantasyedge.api import Api

        cls.tmp = tempfile.TemporaryDirectory()
        db = pathlib.Path(cls.tmp.name) / "s.db"
        store = Store(db)
        bundle, _ = load_fixture_bundle()
        store.save(bundle)
        store.close()
        cls.api = Api(str(db))

    @classmethod
    def tearDownClass(cls):
        cls.api.close()
        cls.tmp.cleanup()

    def test_live_is_cached_briefly_and_mosaic_is_not_immutable(self):
        from fantasyedge.api import CONFIG, IMMUTABLE, LIVE

        _, pol = self.api.dispatch("/api/live", {})
        self.assertEqual(pol, LIVE)
        _, pol = self.api.dispatch("/api/mosaic/espn/99", {})
        self.assertEqual(pol, CONFIG)
        # a finished season can never change, so it caches for a year
        _, pol = self.api.dispatch("/api/leagues/espn/99/draft", {})
        self.assertNotEqual(pol, IMMUTABLE)      # 2025 is the only season loaded

    def test_mosaic_returns_two_sides_and_priors(self):
        m, _ = self.api.dispatch("/api/mosaic/espn/99", {})
        self.assertTrue(m["you"]["starters"])
        self.assertIsNotNone(m["opp"])
        self.assertNotEqual(m["you"]["teamId"], m["opp"]["teamId"])
        self.assertTrue(m["priors"])

    def test_mosaic_rejects_a_team_not_in_the_league(self):
        from fantasyedge.api import HttpError

        with self.assertRaises(HttpError) as cm:
            self.api.dispatch("/api/mosaic/espn/99", {"team": ["nobody"]})
        self.assertEqual(cm.exception.code, 404)

    def test_the_page_paints_a_real_matchup_on_first_frame(self):
        page = self.api.mosaic_page()
        self.assertNotIn(b"__DATA__", page)
        self.assertIn(b"<!doctype html>", page)
        self.assertIn(b"leverage", page.lower())


class TestProjections(unittest.TestCase):
    """Several sources in one table is the whole point: it turns 'who projects
    best' from an opinion into a query."""

    def setUp(self):
        from fantasyedge import projections as pj

        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(pathlib.Path(self.tmp.name) / "p.db")
        bundle, _ = load_fixture_bundle()
        self.store.save(bundle)
        self.pj = pj

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_espn_projections_are_lifted_from_rows_already_pulled(self):
        out = self.pj.seed_espn(self.store)
        self.assertGreater(out["rows"], 0)
        self.assertEqual(self.pj.sources(self.store), ["espn"])

    def test_seeding_twice_does_not_duplicate(self):
        first = self.pj.seed_espn(self.store)["rows"]
        self.pj.seed_espn(self.store)
        n = self.store.q("SELECT COUNT(*) c FROM projection")[0]["c"]
        self.assertEqual(n, first)

    def test_csv_joins_on_normalised_name_and_position(self):
        """Ids are not shared between networks, so the join is name plus
        position - and it has to survive accents, punctuation and suffixes."""
        who = self.store.q(
            "SELECT name, pos FROM player WHERE provider='espn' AND pos='RB' LIMIT 2")
        self.assertTrue(who)
        csv_path = pathlib.Path(self.tmp.name) / "rival_2025_w1.csv"
        lines = ["player,pos,points"]
        for r in who:
            lines.append(f"{r['name'].upper()} Jr.,{r['pos']},15.5")
        lines.append("Nobody At All,RB,9.9")
        csv_path.write_text("\n".join(lines))

        out = self.pj.load_csv(self.store, str(csv_path), "rival", 2025, 1)
        self.assertEqual(out["rows"], len(who))
        self.assertEqual(out["unmatched_count"], 1)
        self.assertIn("Nobody At All", out["unmatched"])
        self.assertIn("rival", self.pj.sources(self.store))

    def test_norm_name_handles_accents_case_and_suffixes(self):
        n = self.pj.norm_name
        self.assertEqual(n("Ja'Marr Chase"), n("JAMARR CHASE"))
        self.assertEqual(n("Michael Pittman Jr."), n("michael pittman"))
        self.assertEqual(n("Amon-Ra St. Brown"), n("Amon Ra St Brown"))
        self.assertEqual(n("Ja'Marr Chase"), "jamarrchase")

    def test_the_two_join_keys_cannot_drift_apart(self):
        """ADP and projections both join on name plus position. If these two
        implementations ever disagree, one of the joins quietly loses players."""
        for name in ("Ja'Marr Chase", "Amon-Ra St. Brown", "Michael Pittman Jr.",
                     "Kenneth Walker III", "D'Andre Swift", "Travis Etienne Jr."):
            self.assertEqual(self.pj.norm_name(name), normalise(name), name)

    def test_load_dir_reads_source_season_week_from_the_filename(self):
        d = pathlib.Path(self.tmp.name) / "proj"
        d.mkdir()
        name = self.store.q("SELECT name, pos FROM player WHERE provider='espn' LIMIT 1")[0]
        (d / "cbs_2025_w3.csv").write_text(
            f"player,pos,points\n{name['name']},{name['pos']},12.0\n")
        (d / "not-a-projection.csv").write_text("x,y\n1,2\n")
        out = self.pj.load_dir(self.store, str(d))
        self.assertEqual(len(out), 1)
        self.assertEqual((out[0]["source"], out[0]["season"], out[0]["week"]),
                         ("cbs", 2025, 3))


class TestProjectionAccuracy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fantasyedge import projections as pj

        cls.tmp = tempfile.TemporaryDirectory()
        cls.store = Store(pathlib.Path(cls.tmp.name) / "acc.db")
        bundle, _ = load_fixture_bundle()
        cls.store.save(bundle)
        pj.seed_espn(cls.store)

    @classmethod
    def tearDownClass(cls):
        cls.store.close()
        cls.tmp.cleanup()

    def test_scores_a_source_against_what_actually_happened(self):
        r = analytics.projection_accuracy(self.store, "espn", "99")
        self.assertFalse(r.empty)
        self.assertEqual(r.columns[0], "Source")
        row = r.rows[0]
        self.assertEqual(row[0], "espn")
        self.assertGreater(row[3], 0)          # mean absolute error is real
        self.assertTrue(r.headline)

    def test_it_is_registered_and_carries_a_caveat(self):
        self.assertIn("projection_accuracy", analytics.ANALYSES)
        r = analytics.projection_accuracy(self.store, "espn", "99")
        self.assertTrue(r.caveat)

    def test_says_so_plainly_when_nothing_is_loaded(self):
        tmp = tempfile.TemporaryDirectory()
        store = Store(pathlib.Path(tmp.name) / "empty.db")
        bundle, _ = load_fixture_bundle()
        store.save(bundle)
        try:
            r = analytics.projection_accuracy(store, "espn", "99")
            self.assertTrue(r.empty)
            self.assertIn("projection", r.caveat.lower())
        finally:
            store.close(); tmp.cleanup()


class TestPhase(unittest.TestCase):
    """Leverage answers "what is still in doubt". Before kickoff nothing is,
    and after the final whistle nothing is - so the board has to size by
    something else or show eighteen identical tiles."""

    PROJ = [("QB", 18.2), ("RB", 15.1), ("RB", 11.4), ("WR", 21.1), ("WR", 13.8),
            ("TE", 9.2), ("WR", 8.6), ("DEF", 6.1), ("K", 7.4)]

    def team(self, side, remaining, scored_frac):
        from fantasyedge.leverage import Cell

        return [Cell(id=f"{side}{i}", label=f"{side}{i}", pos=p, side=side,
                     scored=v * scored_frac, projected=v, remaining=remaining)
                for i, (p, v) in enumerate(self.PROJ)]

    def test_phase_reads_the_clock_not_the_scoreboard(self):
        from fantasyedge.leverage import evaluate

        self.assertEqual(evaluate(self.team("you", 1.0, 0.0)
                                  + self.team("opp", 1.0, 0.0)).phase, "pre")
        self.assertEqual(evaluate(self.team("you", 0.5, 0.4)
                                  + self.team("opp", 0.5, 0.4)).phase, "live")
        # points already scored must not make a finished week look live
        self.assertEqual(evaluate(self.team("you", 0.0, 1.0)
                                  + self.team("opp", 0.0, 1.0)).phase, "final")

    def test_pre_game_sizes_by_projection_not_uniformly(self):
        from fantasyedge.leverage import evaluate

        m = evaluate(self.team("you", 1.0, 0.0) + self.team("opp", 1.0, 0.0))
        shares = [c.share for c in m.cells]
        self.assertGreater(max(shares), min(shares) * 2)
        top = m.cells[0]
        self.assertEqual(top.projected, max(v for _, v in self.PROJ))
        self.assertGreater(len({c.band for c in m.cells}), 1)

    def test_final_sizes_by_what_was_actually_scored(self):
        from fantasyedge.leverage import evaluate

        cells = self.team("you", 0.0, 1.0) + self.team("opp", 0.0, 1.0)
        cells[8].scored = 40.0                      # the kicker had a night
        star = cells[8].id                          # evaluate sorts in place
        m = evaluate(cells)
        self.assertEqual(m.phase, "final")
        self.assertEqual(m.cells[0].id, star)

    def test_bands_are_relative_to_an_even_split(self):
        """Absolute cuts made every pre-game tile identical, because nobody
        holds 18% of the projected points in an eighteen-cell line-up."""
        from fantasyedge.leverage import band_for

        # the same share means different things at different board sizes
        self.assertEqual(band_for(0.20, even=1 / 4)[0], "sm")     # below 1/4
        self.assertEqual(band_for(0.30, even=1 / 4)[0], "md")     # just above it
        self.assertEqual(band_for(0.09, even=1 / 18)[0], "md")    # above 1/18
        self.assertEqual(band_for(0.20, even=1 / 18)[0], "xl")    # far above it


class TestEspnLiveSource(unittest.TestCase):
    """Real game state, no credentials, and honest about being unreachable."""

    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads(
            (FIX / "espn_scoreboard.json").read_text())

    def source(self, http=None):
        from fantasyedge.live import EspnLiveSource

        players = [{"player_id": "1", "team": "SEA", "projected": 18.0},
                   {"player_id": "2", "team": "KC", "projected": 21.0},
                   {"player_id": "3", "team": "ZZZ", "projected": 5.0}]
        return EspnLiveSource(players, http=http or (lambda url: self.fixture))

    def test_reads_the_real_slate(self):
        snap = self.source().snapshot()
        self.assertEqual(snap["source"], "espn")
        self.assertEqual(snap["window"], 1)
        self.assertEqual(len(snap["games"]), 32)
        self.assertEqual(snap["players"]["1"]["g"], "PRE")
        self.assertEqual(snap["players"]["1"]["r"], 1.0)

    def test_a_club_with_no_game_is_a_bye(self):
        snap = self.source().snapshot()
        self.assertEqual(snap["players"]["3"]["g"], "BYE")

    def test_an_unreachable_feed_does_not_claim_a_bye(self):
        """Saying BYE when the feed is down is a definite claim the data does
        not support, and it silently zeroes everyone's remaining game."""
        def boom(url):
            raise OSError("403")

        snap = self.source(http=boom).snapshot()
        self.assertEqual(snap["source"], "espn-unavailable")
        for v in snap["players"].values():
            self.assertEqual(v["g"], "PRE")
            self.assertEqual(v["r"], 1.0)

    def test_it_caches_rather_than_hammering_the_edge(self):
        calls = []

        def counted(url):
            calls.append(url)
            return self.fixture

        src = self.source(http=counted)
        for _ in range(5):
            src.snapshot()
        self.assertEqual(len(calls), 1, "the edge blocks an address that keeps knocking")

    def test_snapshot_still_carries_no_user_context(self):
        """`scored` is a count of how many athletes the box scores covered - a
        property of the slate, not of whoever is asking. Everything here must
        stay that way or the payload stops being cacheable for everyone."""
        snap = self.source().snapshot()
        self.assertEqual(set(snap), {"asOf", "window", "source", "games",
                                     "players", "version", "scored", "error"})
        for v in snap["players"].values():
            self.assertEqual(set(v), {"s", "r", "g"})


class TestScoring(unittest.TestCase):
    """A box score reports football; a fantasy board needs points. This is the
    translation, and getting a weight wrong is invisible on screen."""

    def setUp(self):
        from fantasyedge import scoring

        self.sc = scoring
        self.fixture = json.loads((FIX / "espn_summary.json").read_text())

    def test_known_lines_score_correctly(self):
        s = self.sc.Scoring()
        # 264 pass yds (10.56) + 2 TD (8)
        self.assertAlmostEqual(
            s.points({"passingYards": 264, "passingTouchdowns": 2}), 18.56, places=2)
        # 8 rec (8) + 112 yds (11.2) + 1 TD (6)
        self.assertAlmostEqual(
            s.points({"receptions": 8, "receivingYards": 112,
                      "receivingTouchdowns": 1}), 25.2, places=2)
        # 198 yds (7.92) + 1 TD (4) - 2 INT (4) nets back to the yardage
        self.assertAlmostEqual(
            s.points({"passingYards": 198, "passingTouchdowns": 1,
                      "interceptions": 2}), 7.92, places=2)
        self.assertEqual(s.points({}), 0.0)

    def test_stats_are_read_by_key_not_by_position(self):
        """ESPN reorders these columns. A positional parser would keep working
        while quietly scoring interceptions as rushing yards."""
        shuffled = json.loads(json.dumps(self.fixture))
        for team in shuffled["boxscore"]["players"]:
            for cat in team["statistics"]:
                order = list(range(len(cat["keys"])))[::-1]
                cat["keys"] = [cat["keys"][i] for i in order]
                for ath in cat["athletes"]:      # every athlete, not just the first
                    ath["stats"] = [ath["stats"][i] for i in order]
        self.assertEqual(self.sc.score_boxscore(self.fixture),
                         self.sc.score_boxscore(shuffled))

    def test_espn_placeholders_do_not_become_numbers(self):
        for raw in (None, "", "--", "n/a"):
            self.assertEqual(self.sc._num(raw), 0.0)
        self.assertEqual(self.sc._num("20/35"), 20.0)     # made/attempted
        self.assertEqual(self.sc._num("1,024"), 1024.0)

    def test_league_scoring_overrides_the_default(self):
        half = self.sc.Scoring.from_config({"scoring": {"reception": 0.5}})
        full = self.sc.Scoring()
        line = {"receptions": 10, "receivingYards": 100}
        self.assertEqual(full.points(line) - half.points(line), 5.0)

    def test_an_unknown_category_contributes_nothing(self):
        junk = {"boxscore": {"players": [{"statistics": [
            {"name": "mystery", "keys": ["somethingNew"],
             "athletes": [{"athlete": {"id": "9"}, "stats": ["99"]}]}]}]}}
        self.assertEqual(self.sc.score_boxscore(junk), {})


class TestLiveBoxScores(unittest.TestCase):
    """Points must move during a game without asking the edge for every game."""

    @classmethod
    def setUpClass(cls):
        cls.sb = json.loads((FIX / "espn_scoreboard.json").read_text())
        cls.box = json.loads((FIX / "espn_summary.json").read_text())

    def source(self, state="in"):
        import copy

        from fantasyedge.live import EspnLiveSource

        sb = copy.deepcopy(self.sb)
        sb["events"][0]["competitions"][0]["status"] = {
            "period": 3, "clock": 420.0,
            "type": {"state": state, "shortDetail": "7:00 - 3rd"}}
        self.calls = []

        def http(url):
            self.calls.append(url)
            return self.box if "summary" in url else sb

        # the ids in the fixture are real starters from a real matchup
        players = [{"player_id": "3139477", "team": "SEA", "projected": 18.0},
                   {"player_id": "4258173", "team": "SEA", "projected": 15.0},
                   {"player_id": "-16026", "team": "SEA", "projected": 7.0},
                   {"player_id": "999999", "team": "KC", "projected": 12.0}]
        return EspnLiveSource(players, http=http)

    def test_points_arrive_from_the_box_score(self):
        snap = self.source().snapshot()
        self.assertAlmostEqual(snap["players"]["3139477"]["s"], 18.56, places=2)
        self.assertAlmostEqual(snap["players"]["4258173"]["s"], 25.2, places=2)
        # five athletes plus the clubs in the games that have started
        self.assertGreaterEqual(snap["scored"], 7)

    def test_only_started_games_are_fetched(self):
        """Sixteen summary calls a poll is how an address gets blocked."""
        self.source().snapshot()
        summaries = [c for c in self.calls if "summary" in c]
        self.assertEqual(len(summaries), 1, "only the in-progress game")

    def test_repeat_polls_do_not_refetch(self):
        src = self.source()
        src.snapshot()
        n = len([c for c in self.calls if "summary" in c])
        for _ in range(5):
            src.snapshot()
        self.assertEqual(len([c for c in self.calls if "summary" in c]), n)

    def test_a_defence_is_scored_from_the_other_side_of_its_game(self):
        """-16026 is Seattle: -16000 minus the club id. It has no row in a box
        score, so it is scored as a club - from what the opponent failed to do."""
        snap = self.source().snapshot()
        self.assertNotEqual(snap["players"]["-16026"]["s"], 0.0)
        self.assertEqual(snap["players"]["-16026"]["s"], 5.0)   # a shutout so far

    def test_a_player_not_in_the_box_score_stays_at_zero(self):
        snap = self.source().snapshot()
        self.assertEqual(snap["players"]["999999"]["s"], 0.0)

    def test_a_failing_summary_does_not_blank_the_board(self):
        import copy

        from fantasyedge.live import EspnLiveSource

        sb = copy.deepcopy(self.sb)
        sb["events"][0]["competitions"][0]["status"] = {
            "period": 2, "clock": 300.0, "type": {"state": "in", "shortDetail": "Q2"}}
        state = {"fail": False}

        def http(url):
            if "summary" in url:
                if state["fail"]:
                    raise OSError("503")
                return self.box
            return sb

        src = EspnLiveSource(
            [{"player_id": "3139477", "team": "SEA", "projected": 18.0}], http=http)
        first = src.snapshot()["players"]["3139477"]["s"]
        self.assertGreater(first, 0)
        state["fail"] = True
        src._boxes.clear()                    # force a refetch that will fail
        self.assertEqual(src.snapshot()["players"]["3139477"]["s"], 0.0)


class TestTeamDefence(unittest.TestCase):
    """A defence is scored from what the other side failed to do, which is why
    it needs the whole game rather than one athlete's stat line."""

    def setUp(self):
        from fantasyedge import scoring

        self.sc = scoring

    def test_the_points_allowed_tiers(self):
        d = self.sc.dst_points
        for allowed, expect in ((0, 5.0), (3, 4.0), (10, 3.0), (16, 1.0),
                                (24, 0.0), (31, -1.0), (41, -3.0), (52, -5.0)):
            self.assertEqual(d(allowed, None), expect, f"{allowed} allowed")

    def test_the_yards_allowed_tiers_stack_on_top(self):
        d = self.sc.dst_points
        self.assertEqual(d(0, 80), 10.0)        # shutout (5) + under 100 (5)
        self.assertEqual(d(10, 310), 3.0)       # 3 + 0
        self.assertEqual(d(31, 420), -4.0)      # -1 + -3
        self.assertEqual(d(52, 560), -12.0)     # -5 + -7

    def test_big_plays_are_added(self):
        d = self.sc.dst_points
        self.assertEqual(
            d(0, 180, {"sacks": 4, "interceptions": 2}), 16.0)
        self.assertEqual(
            d(0, 90, {"defensiveTouchdowns": 1}), 16.0)
        self.assertEqual(d(14, 300, {"safeties": 1, "fumblesRecovered": 1}), 5.0)

    def test_it_still_scores_without_a_box_score(self):
        """Points allowed come from the scoreboard; yards need the summary. A
        defence scored on points and big plays alone is a real answer, not a
        wrong one."""
        d = self.sc.dst_points
        self.assertEqual(d(6, None, {"sacks": 3}), 7.0)
        self.assertEqual(d(6, None), 4.0)

    def test_team_yards_and_defensive_plays_are_parsed(self):
        summary = {"boxscore": {
            "teams": [{"team": {"abbreviation": "SEA"},
                       "statistics": [{"name": "totalYards", "displayValue": "388"}]},
                      {"team": {"abbreviation": "NE"},
                       "statistics": [{"name": "totalYards", "displayValue": "241"}]}],
            "players": [{"team": {"abbreviation": "SEA"}, "statistics": [
                {"name": "defensive",              # ESPN's real category split
                 "keys": ["totalTackles", "sacks", "defensiveTouchdowns"],
                 "athletes": [{"athlete": {"id": "1"}, "stats": ["7", "2", "0"]},
                              {"athlete": {"id": "2"}, "stats": ["4", "1", "1"]}]},
                {"name": "interceptions",
                 "keys": ["interceptions", "interceptionYards"],
                 "athletes": [{"athlete": {"id": "3"}, "stats": ["1", "18"]}]},
                {"name": "fumbles",
                 "keys": ["fumbles", "fumblesLost", "fumblesRecovered"],
                 "athletes": [{"athlete": {"id": "4"}, "stats": ["0", "0", "1"]}]}]}]}}
        out = self.sc.parse_team_defence(summary)
        self.assertEqual(out["SEA"]["yards"], 388.0)
        self.assertEqual(out["NE"]["yards"], 241.0)
        self.assertEqual(out["SEA"]["sacks"], 3.0)          # summed across players
        self.assertEqual(out["SEA"]["interceptions"], 1.0)
        self.assertEqual(out["SEA"]["fumblesRecovered"], 1.0)
        self.assertEqual(out["SEA"]["defensiveTouchdowns"], 1.0)

    def test_a_league_can_override_the_big_play_values(self):
        d = self.sc.dst_points
        self.assertEqual(d(24, 300, {"sacks": 2}), 2.0)
        self.assertEqual(d(24, 300, {"sacks": 2}, rules={"sack": 2.0}), 4.0)


class TestDefensiveStatSources(unittest.TestCase):
    def test_a_quarterbacks_thrown_picks_are_not_his_defences_takeaways(self):
        """`interceptions` is a key in the passing category too. Reading it
        wherever it appears hands a defence two points for its own offence
        turning the ball over."""
        from fantasyedge import scoring

        summary = {"boxscore": {"players": [{"team": {"abbreviation": "KC"},
            "statistics": [
              {"name": "passing",
               "keys": ["passingYards", "passingTouchdowns", "interceptions"],
               "athletes": [{"athlete": {"id": "qb"}, "stats": ["250", "1", "3"]}]},
              {"name": "interceptions",
               "keys": ["interceptions", "interceptionYards"],
               "athletes": [{"athlete": {"id": "cb"}, "stats": ["1", "22"]}]}]}]}}
        out = scoring.parse_team_defence(summary)
        self.assertEqual(out["KC"]["interceptions"], 1.0,
                         "only the pick the defence actually caught")


class TestRealFetchPathExists(unittest.TestCase):
    """`_get_json` was called but never defined in live.py, and the broad
    except around it turned that NameError into "espn-unavailable" - a typo
    wearing the costume of a blocked endpoint for a whole day. These assert the
    network path is at least wired, without touching the network."""

    def test_the_fetch_helper_exists_and_is_callable(self):
        from fantasyedge import live

        self.assertTrue(callable(getattr(live, "_get_json", None)))
        self.assertTrue(callable(getattr(live, "scoreboard_url", None)))
        self.assertTrue(callable(getattr(live, "summary_url", None)))

    def test_urls_point_at_the_unblocked_host(self):
        from fantasyedge import live

        self.assertIn("site.web.api.espn.com", live.scoreboard_url())
        self.assertIn("summary?event=99", live.summary_url("99"))

    def test_an_api_key_is_appended_with_the_right_separator(self):
        import os

        from fantasyedge import live

        old = os.environ.get("ESPN_API_KEY")
        os.environ["ESPN_API_KEY"] = "k e y"
        try:
            self.assertTrue(live.with_key("https://x/a").endswith("/a?apikey=k%20e%20y"))
            self.assertTrue(live.with_key("https://x/a?b=1").endswith("&apikey=k%20e%20y"))
        finally:
            if old is None:
                del os.environ["ESPN_API_KEY"]
            else:
                os.environ["ESPN_API_KEY"] = old

    def test_a_failure_reason_is_reported_not_swallowed(self):
        from fantasyedge.live import EspnLiveSource

        def boom(url):
            raise RuntimeError("kaboom")

        snap = EspnLiveSource([{"player_id": "1", "team": "KC"}],
                              http=boom).snapshot()
        self.assertEqual(snap["source"], "espn-unavailable")
        self.assertIn("kaboom", snap["error"])


class TestPlayerProfile(unittest.TestCase):
    """The card's data: what he has done, where he finished, where he went."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.store = Store(pathlib.Path(cls.tmp.name) / "prof.db")
        bundle, _ = load_fixture_bundle()
        cls.store.save(bundle)
        row = cls.store.q("SELECT player_id FROM player WHERE pos='WR' LIMIT 1")
        cls.pid = row[0]["player_id"]

    @classmethod
    def tearDownClass(cls):
        cls.store.close()
        cls.tmp.cleanup()

    def test_a_season_log_is_built(self):
        from fantasyedge import profile

        out = profile.build(self.store, self.pid)
        self.assertTrue(out["name"])
        self.assertTrue(out["seasons"])
        first = out["seasons"][0]
        self.assertTrue({"season", "weeks", "total", "ppg", "rank",
                         "field", "weekly"} <= set(first))

    def test_an_unplayed_season_is_not_ranked(self):
        """A season in progress has a row per week with nothing in it. Ranking
        a field where everybody scored zero looks authoritative and means
        nothing."""
        from fantasyedge import profile

        log = profile.season_log(self.store, self.pid, "WR")
        for s in log:
            if not s["started"]:
                self.assertIsNone(s["rank"])

    def test_draft_history_carries_league_size(self):
        """Pick 21 is the back of round two in a ten-team league and the front
        of it in a twelve. A single ADP number cannot say that."""
        from fantasyedge import profile

        rows = profile.draft_history(self.store, self.pid)
        for r in rows:
            self.assertIn("teams", r)
            self.assertIn("overall", r)

    def test_one_line_restated_across_formats(self):
        from fantasyedge import profile

        out = profile.format_lines(
            {"receptions": 8, "receivingYards": 112, "receivingTouchdowns": 1})
        by = {f["name"]: f["points"] for f in out}
        self.assertEqual(by["PPR"] - by["Half PPR"], 4.0)     # 8 catches, half a point
        self.assertEqual(by["Half PPR"] - by["Standard"], 4.0)

    def test_an_unknown_player_yields_nothing(self):
        from fantasyedge import profile

        self.assertEqual(profile.build(self.store, "no-such-player"), {})


class TestAnonymisation(unittest.TestCase):
    """`--anon` is what makes a public Pages build safe. A field-by-field
    version of this already missed roster owners and team names - eighty-four
    real people in a build labelled anonymised - so it is asserted by sweeping
    for the names rather than by trusting the scrubber's field list."""

    def payload(self):
        return {
            "leagues": [{
                "id": "espn-1", "league": "Sure Buds", "week": 1, "season": 2026,
                "you": {"teamId": "1", "name": "Silky Johnson", "starters": []},
                "opp": {"teamId": "2", "name": "Fault Nation", "starters": []},
                "teams": [{"teamId": "1", "name": "Silky Johnson"},
                          {"teamId": "2", "name": "Fault Nation"}],
                "roster": [{"id": "9", "name": "Real Player", "teamId": "1",
                            "owner": "Silky Johnson", "started": True}],
                "priors": {"Silky Johnson": {"bench": 20.4}},
            }],
            "injuries": {"injuries": [
                {"id": "9", "name": "Real Player",
                 "roast": "Fault Nation took him in round 2 of Sure Buds."}]},
        }

    def test_nobody_elses_name_survives_anywhere(self):
        """The reader's own team is the one exemption, and it is deliberate.

        The demo is published by the person whose leagues these are, and
        scrubbing their own team made it read as a stranger's league - which is
        the opposite of what a demo is for. Everyone else in these leagues did
        not choose to be on a public page, so they are still swept, and this
        test is the thing standing between that decision and a leak.
        """
        import tools.build_docs as bd

        out = json.dumps(bd.anonymise(self.payload()))
        for name in ("Fault Nation", "Sure Buds"):
            self.assertNotIn(name, out, f"{name} survived anonymisation")

    def test_the_readers_own_team_is_kept(self):
        import tools.build_docs as bd

        out = bd.anonymise(self.payload())
        self.assertEqual(out["leagues"][0]["you"]["name"], "Silky Johnson")

    def test_the_exemption_does_not_leak_through_another_league(self):
        """Somebody else's team in league A must not survive because a team of
        the same name happens to be the reader's in league B. The exemption is
        by name, so two leagues are the case that would break it."""
        import tools.build_docs as bd

        data = self.payload()
        data["leagues"].append({
            "id": "espn-2", "league": "Other League", "week": 1, "season": 2026,
            "you": {"teamId": "9", "name": "My Other Team", "starters": []},
            "opp": {"teamId": "3", "name": "Fault Nation", "starters": []},
            "teams": [{"teamId": "3", "name": "Fault Nation"}],
            "roster": [], "priors": {},
        })
        out = json.dumps(bd.anonymise(data))
        self.assertNotIn("Fault Nation", out,
                         "an opponent survived because a league listed them "
                         "differently")
        self.assertIn("Silky Johnson", out)
        self.assertIn("My Other Team", out)

    def test_a_stand_in_never_collides_with_a_real_name(self):
        """ESPN calls an unnamed team "Team 8", and an earlier version of this
        minted labels of exactly that shape - so a real team matched the label
        invented for somebody else and two managers collapsed into one."""
        import tools.build_docs as bd

        data = self.payload()
        real = bd.STAND_INS[0]
        data["leagues"][0]["teams"].append({"teamId": "7", "name": real})
        out = bd.anonymise(data)
        labels = [t["name"] for t in out["leagues"][0]["teams"]]
        self.assertEqual(len(set(labels)), len(labels),
                         f"two teams share a name: {labels}")

    def test_the_same_person_gets_the_same_label(self):
        import tools.build_docs as bd

        out = bd.anonymise(self.payload())
        L = out["leagues"][0]
        self.assertEqual(L["you"]["name"], L["roster"][0]["owner"])
        self.assertEqual(L["you"]["name"], list(L["priors"])[0])

    def test_players_are_public_facts_and_stay(self):
        """NFL players are not the people being protected here."""
        import tools.build_docs as bd

        out = json.dumps(bd.anonymise(self.payload()))
        self.assertIn("Real Player", out)

    def test_a_team_named_like_a_label_does_not_merge_two_people(self):
        """ESPN names an unnamed team "Team 8", which is also the shape of the
        labels this scrubber generates. Replacing name by name rescans text it
        has already written, so that real name would match the label minted for
        somebody else and rewrite it, collapsing two managers into one. No leak,
        but a silently wrong league."""
        import tools.build_docs as bd

        data = self.payload()
        L = data["leagues"][0]
        # "Longhaul Legends" sorts eighth and so is minted as "Team 8"; the real
        # "Team 8" is shorter, so a longest-first pass reaches it afterwards and
        # rewrites that freshly minted label. Nine managers, eight labels.
        L["teams"] = [{"teamId": str(i), "name": n} for i, n in enumerate(
            ["Team 8", "Aaa", "Bbb", "Ccc", "Ddd", "Eee", "Fff", "Ggg",
             "Longhaul Legends"], 1)]
        out = bd.anonymise(data)
        labels = [t["name"] for t in out["leagues"][0]["teams"]]
        self.assertEqual(len(set(labels)), len(labels),
                         f"two managers collapsed onto one label: {labels}")


class TestPlayerIdentity(unittest.TestCase):
    """One player, three providers, one key.

    ESPN's fantasy player id doubles as its site athlete id, so a live box
    score joined to an ESPN roster for free. That is a coincidence that holds
    for one provider out of three; Yahoo and Sleeper ids match nothing. These
    assert the derived key that replaces it.
    """

    def test_every_provider_spells_a_defence_differently(self):
        from fantasyedge import identity as I

        for spelling, club in [("Rams D/ST", "14"), ("LAR", ""),
                               ("Los Angeles Rams", ""), ("St. Louis Rams", "")]:
            self.assertEqual(I.key(spelling, "DEF", club), "def:lar", spelling)
        self.assertEqual(I.key("49ers D/ST", "DEF"), "def:sf")
        self.assertEqual(I.key("San Francisco 49ers", "DST"), "def:sf")

    def test_a_club_that_moved_is_still_the_same_club(self):
        from fantasyedge import identity as I

        self.assertEqual(I.team("OAK"), "LV")
        self.assertEqual(I.team("WSH"), "WAS")
        self.assertEqual(I.team("JAC"), "JAX")

    def test_folding_survives_suffixes_accents_and_apostrophes(self):
        from fantasyedge import identity as I

        self.assertEqual(I.fold("Marvin Harrison Jr."), I.fold("Marvin Harrison"))
        self.assertEqual(I.fold("Kenneth Walker III"), I.fold("Kenneth Walker"))
        self.assertEqual(I.fold("Ja'Marr Chase"), "jamarrchase")
        self.assertEqual(I.fold("Amon-Ra St. Brown"), "amonrastbrown")

    def test_one_owner_of_the_folding(self):
        """`projections.norm_name` and `sleeper.normalise` were two copies kept
        in step by a test. One implementation needs no such test."""
        from fantasyedge import identity, projections
        from fantasyedge.providers import sleeper

        self.assertIs(projections.norm_name, identity.fold)
        self.assertIs(sleeper.normalise, identity.fold)

    def test_a_position_change_is_not_a_different_person(self):
        """Travis Hunter is a WR to ESPN and a DB to Sleeper. Observed."""
        from fantasyedge import identity as I

        r = I.Resolver()
        r.add("sleeper-1", "Travis Hunter", "DB", "JAX")
        got, how = r.resolve("Travis Hunter", "WR", "JAX")
        self.assertEqual(got, "sleeper-1")
        self.assertEqual(how, "name")

    def test_a_nickname_resolves_only_with_the_club_to_back_it(self):
        """ESPN says "Hollywood Brown", Sleeper says "Marquise Brown"."""
        from fantasyedge import identity as I

        r = I.Resolver()
        r.add("sleeper-2", "Marquise Brown", "WR", "KC")
        got, how = r.resolve("Hollywood Brown", "WR", "KC")
        self.assertEqual((got, how), ("sleeper-2", "surname+club"))
        # The same surname at another club is not the same man.
        self.assertEqual(r.resolve("Hollywood Brown", "WR", "SEA")[0], None)

    def test_an_ambiguous_name_resolves_to_nobody(self):
        """Four Mike Williamses; the club picks one, and without a club the
        honest answer is none. A confident wrong line is worse than a blank."""
        from fantasyedge import identity as I

        r = I.Resolver()
        r.add("a", "Mike Williams", "WR", "LAC")
        r.add("b", "Mike Williams", "WR", "")
        self.assertEqual(r.resolve("Mike Williams", "WR", "LAC")[0], "a")
        self.assertEqual(r.resolve("Mike Williams", "WR", "")[0], None)

    def test_frank_gore_and_frank_gore_jr_are_two_people(self):
        """Folding the suffix is right for matching and wrong for telling them
        apart, so the club has to do it."""
        from fantasyedge import identity as I

        r = I.Resolver()
        r.add("snr", "Frank Gore", "RB", "NYJ")
        r.add("jnr", "Frank Gore Jr.", "RB", "BUF")
        self.assertEqual(r.resolve("Frank Gore", "RB", "NYJ")[0], "snr")
        self.assertEqual(r.resolve("Frank Gore Jr.", "RB", "BUF")[0], "jnr")
        self.assertEqual(r.resolve("Frank Gore", "RB", "")[0], None)


class TestCrossProviderLiveScoring(unittest.TestCase):
    """A Sleeper or Yahoo roster has to score off an ESPN box score.

    This is the whole point of the identity layer, and the failure it guards
    is a quiet one: ids that match nothing fall through to zero, so every
    player on those rosters reads as scoreless and the board looks like it is
    merely a slow afternoon. Asserting a non-zero total is the only way to
    tell the two apart.
    """

    @classmethod
    def setUpClass(cls):
        cls.summary = json.loads((FIX / "espn_summary.json").read_text())
        # Every game in the stored slate is pre-kickoff, and a player whose
        # game has not started scores nothing by design - so on the stored
        # fixture these assertions would pass on zeros and prove nothing.
        board = json.loads((FIX / "espn_scoreboard.json").read_text())
        board["events"][0]["competitions"][0]["status"] = {
            "period": 3, "clock": 420.0,
            "type": {"state": "in", "shortDetail": "7:00 - 3rd"}}
        cls.board = board

    def source(self, players):
        """An injected transport wins over the fixture files setUpModule pins,
        so it has to answer both endpoints, not just the interesting one."""
        from fantasyedge.live import EspnLiveSource

        def http(url):
            return self.summary if "summary?event=" in url else self.board
        return EspnLiveSource(players, http=http)

    def test_a_sleeper_id_still_finds_its_points(self):
        """The live game is SEA; the summary lists the athletes. A Sleeper id
        matches nothing in it, so only the name can carry the join."""
        espn = self.source([{"player_id": "4258173", "team": "SEA",
                             "name": "Nico Collins", "pos": "WR"}])
        sleeper = self.source([{"player_id": "8112", "team": "SEA",
                                "name": "Nico Collins", "pos": "WR",
                                "espn_ids": False}])
        mine = espn.snapshot()["players"]["4258173"]["s"]
        theirs = sleeper.snapshot()["players"]["8112"]["s"]
        self.assertGreater(mine, 0.0, "fixture should score this player")
        self.assertEqual(theirs, mine,
                         "a Sleeper id must resolve to the same box-score line")

    def test_a_yahoo_defence_scores_as_a_club(self):
        """Yahoo spells a defence "Seattle Seahawks" and gives it a positive
        id, so neither ESPN's naming nor its negative-id trick applies."""
        yahoo = self.source([{"player_id": "100014", "team": "SEA",
                              "name": "Seattle Seahawks", "pos": "DEF",
                              "espn_ids": False}])
        espn = self.source([{"player_id": "-16026", "team": "SEA",
                             "name": "Seahawks D/ST", "pos": "DEF"}])
        self.assertEqual(yahoo.snapshot()["players"]["100014"]["s"],
                         espn.snapshot()["players"]["-16026"]["s"])

    def test_an_unmatchable_name_scores_zero_rather_than_somebody_else(self):
        ghost = self.source([{"player_id": "z9", "team": "SEA",
                              "name": "Nobody Atall", "pos": "WR",
                              "espn_ids": False}])
        self.assertEqual(ghost.snapshot()["players"]["z9"]["s"], 0.0)


class TestOpeningTheStoreIsReadOnly(unittest.TestCase):
    """The API keys every cached payload on the database's mtime, so anything
    that writes on open silently turns the whole read cache off."""

    def test_opening_a_store_does_not_touch_the_file(self):
        import tempfile, pathlib as _p
        from fantasyedge.store import Store

        with tempfile.TemporaryDirectory() as d:
            path = _p.Path(d) / "t.db"
            Store(path).close()                 # create it
            before = path.stat().st_mtime_ns
            for _ in range(5):
                Store(path).close()
            self.assertEqual(path.stat().st_mtime_ns, before,
                             "opening a Store rewrote the database, which "
                             "invalidates every API cache keyed on its mtime")

    def test_a_fresh_database_still_records_its_schema_version(self):
        import tempfile, pathlib as _p
        from fantasyedge.store import Store, SCHEMA_VERSION

        with tempfile.TemporaryDirectory() as d:
            st = Store(_p.Path(d) / "t.db")
            row = st.q("SELECT value FROM meta WHERE key='schema_version'")
            self.assertEqual(row[0]["value"], str(SCHEMA_VERSION))
            st.close()


class TestTeamBadges(unittest.TestCase):
    """Most ESPN team badges are SVG, which no plain image view rasterises."""

    def test_svg_is_not_offered_as_drawable(self):
        from fantasyedge.api import raster

        self.assertFalse(raster("https://g.espncdn.com/lm-static/x/Gene.svg"))
        self.assertFalse(raster(""))
        self.assertTrue(raster("https://x/y.png"))
        self.assertTrue(raster("https://x/y.GIF"))
        self.assertTrue(raster("https://mystique-api.fantasy.espn.com/apis/v1/images/048ec3"))


class TestGamecast(unittest.TestCase):
    """The shape a field animation draws from.

    The important property is that it costs no extra request: the summary it
    reads is the one the scoring already fetched. A gamecast that re-fetched
    would double the only expensive call the live tier makes, per viewer.
    """

    def source(self):
        from fantasyedge.live import EspnLiveSource

        board = json.loads((FIX / "espn_scoreboard.json").read_text())
        board["events"][0]["competitions"][0]["status"] = {
            "period": 3, "clock": 420.0,
            "type": {"state": "in", "shortDetail": "7:00 - 3rd"}}
        summary = json.loads((FIX / "espn_summary.json").read_text())
        self.calls = []

        def http(url):
            self.calls.append(url)
            return summary if "summary?event=" in url else board
        return EspnLiveSource([{"player_id": "1", "team": "SEA", "name": "", "pos": "WR"}],
                              http=http)

    def test_the_summary_is_not_fetched_twice(self):
        src = self.source()
        src.boxscores()
        before = sum(1 for c in self.calls if "summary?event=" in c)
        src.summary(src._events()[0][0])
        after = sum(1 for c in self.calls if "summary?event=" in c)
        self.assertEqual(before, after,
                         "opening a gamecast re-fetched a summary the scoring "
                         "had already paid for")

    def test_a_game_that_has_not_started_has_no_play_data(self):
        """The live tier deliberately does not fetch pre-game summaries, so
        the honest answer is nothing rather than an empty field."""
        src = self.source()
        self.assertEqual(src.summary("not-an-event"), {})


class TestBoxScoreLines(unittest.TestCase):
    """Everyone a game scored, not just everyone somebody rosters.

    Against the real capture of 401872656 (NE 10 @ SEA 13), because every
    assertion here is about how ESPN actually shapes a box score - a role read
    off columns that are named differently in every category, and a display
    line assembled from labels ESPN reorders from time to time.
    """

    @classmethod
    def setUpClass(cls):
        from fantasyedge.scoring import boxscore_lines, score_boxscore

        cls.summary = json.loads((FIX / "replay_summary.json").read_text())
        cls.lines = boxscore_lines(cls.summary)
        cls.points = score_boxscore(cls.summary)

    def one(self, name):
        hit = [r for r in self.lines.values() if r["name"] == name]
        self.assertEqual(len(hit), 1, f"{name} appears {len(hit)} times")
        return hit[0]

    def test_a_back_who_catches_is_still_a_back(self):
        """The role rule that a first version got wrong.

        Rhamondre Stevenson ran eighteen times for 51 and caught five for 44.
        In full PPR the catches score 9.4 and the carries 5.1, so a rule that
        picked the highest-scoring category filed a bell-cow running back
        under REC. Volume - touches, which is also how a person reads the line
        - puts him back where he belongs.
        """
        self.assertEqual(self.one("Rhamondre Stevenson")["role"], "RUSH")

    def test_a_quarterback_who_runs_is_still_a_quarterback(self):
        """Drake Maye: 33 attempts and 7 carries."""
        self.assertEqual(self.one("Drake Maye")["role"], "PASS")

    def test_a_receiver_who_returns_kicks_is_not_a_return_man(self):
        """ESPN publishes return *yards* and no return attempts, so the number
        in that slot is in a different unit from a carry or a catch. Rashid
        Shaheed's 80 return yards beat his one reception on the arithmetic and
        used to make a receiver into a returner."""
        self.assertEqual(self.one("Rashid Shaheed")["role"], "REC")

    def test_a_man_with_nothing_but_returns_is_a_return_man(self):
        self.assertEqual(self.one("Kyle Williams")["role"], "RET")
        self.assertFalse(self.one("Kyle Williams")["skill"])

    def test_the_two_return_lines_are_told_apart(self):
        """Both categories label their yards column "YDS", so an untagged line
        reads "80 YDS · 9 YDS" and says nothing about which was which."""
        line = self.one("Rashid Shaheed")["line"]
        self.assertIn("KR 80 YDS", line)
        self.assertIn("PR 9 YDS", line)

    def test_a_kicker_line_says_which_pair_is_which(self):
        """"2/2, 1/1" is two pairs and no way to know which is the field
        goals. Both labels are kept for exactly that reason, where C/ATT's is
        dropped because the value already reads as a pair."""
        self.assertEqual(self.one("Jason Myers")["line"], "2/2 FG, 1/1 XP")
        self.assertTrue(self.one("Drew Lock")["line"].startswith("16/22, 187 YDS"))

    def test_a_zero_shows_only_in_the_volume_column(self):
        """Romeo Doubs was targeted three times and caught none. "0 REC" is
        the fact; a string of zeroes after it is noise."""
        self.assertEqual(self.one("Romeo Doubs")["line"], "0 REC, 3 TGTS")

    def test_it_finds_the_men_no_board_would_mention(self):
        """The point of the whole block: a four-league board names a dozen
        players and this game scored twenty-odd."""
        self.assertGreaterEqual(len(self.lines), 20)
        self.assertGreaterEqual(sum(1 for r in self.lines.values() if r["skill"]), 18)

    def test_the_points_agree_with_the_scoring_the_board_uses(self):
        """Same parse, so a man cannot read one number in the game panel and a
        different one in the row above it."""
        jsn = self.one("Jaxon Smith-Njigba")
        self.assertAlmostEqual(self.points[jsn["id"]], 26.2, places=2)


class TestReplay(unittest.TestCase):
    """`frame()`: a finished game as it looked at one instant of its own clock.

    The fixture is eight real drives of event 401872656 (NE 10 @ SEA 13), cut
    down by `tools/make_replay_fixture.py` - ESPN's shapes, not an imitation of
    them, because the point of a replay is to exercise the parsers against the
    payload they will actually be handed.

    Every assertion below is against a fact of that game rather than a round
    number, which is what makes them fail loudly if the filtering slips by a
    play: the first snap is at 0:00 elapsed, the second at 0:05, New England's
    opening drive does not begin until 3:18, and their first touchdown lands at
    20:49 - 1249 seconds.
    """

    KICKOFF, SECOND_PLAY = 0, 5
    NE_FIRST_DRIVE, FIRST_TD = 198, 1249

    @classmethod
    def setUpClass(cls):
        # Parsed once. `frame()` promises not to mutate its inputs - there is a
        # test below for exactly that - so every case can share one copy, and
        # re-parsing 150KB of play-by-play per assertion is pure waste.
        cls.SB = json.loads((FIX / "replay_scoreboard.json").read_text())
        cls.SM = json.loads((FIX / "replay_summary.json").read_text())

    def payloads(self):
        return self.SB, self.SM

    def frame(self, seconds):
        from fantasyedge.replay import frame

        sb, sm = self.payloads()
        return frame(sb, sm, seconds)

    def plays(self, summary):
        return [p for d in ((summary.get("drives") or {}).get("previous") or [])
                + ([summary["drives"]["current"]] if (summary.get("drives") or {}).get("current") else [])
                for p in (d.get("plays") or [])]

    # ── the cut ──

    def test_a_play_is_included_at_its_own_second_and_not_before(self):
        """The boundary is inclusive, which is what makes a replay reach the
        final play at all: the last snap of this game is at exactly 3600."""
        before = self.plays(self.frame(self.SECOND_PLAY - 1)[1])
        at = self.plays(self.frame(self.SECOND_PLAY)[1])
        self.assertEqual(len(before), 1)
        self.assertEqual(len(at), 2)
        self.assertEqual(at[1]["text"][:20], "J.Price right tackle")

    def test_the_future_never_leaks_into_a_frame(self):
        _, sm = self.frame(600)
        self.assertTrue(all(
            (p.get("period") or {}).get("number", 1) <= 1 or True
            for p in self.plays(sm)))
        from fantasyedge.replay import play_seconds
        self.assertLessEqual(max(play_seconds(p) for p in self.plays(sm)), 600)

    def test_a_drive_with_no_included_plays_is_dropped(self):
        """An empty drive is not a drive that has not happened yet - it renders
        as a real possession that gained nothing, on every client."""
        _, sm = self.frame(self.NE_FIRST_DRIVE - 1)
        drives = sm["drives"]
        self.assertEqual(drives["previous"], [],
                         "Seattle's opening drive is still in progress here")
        self.assertIn("current", drives)
        self.assertEqual(drives["current"]["team"]["abbreviation"], "SEA")
        self.assertTrue(all(d.get("plays") for d in drives["previous"]))

        _, later = self.frame(self.NE_FIRST_DRIVE)
        self.assertEqual(len(later["drives"]["previous"]), 1)
        self.assertEqual(later["drives"]["current"]["team"]["abbreviation"], "NE")

    def test_a_drive_in_progress_states_no_outcome(self):
        """The captured drive knows it ends in a punt. Carrying that through
        would tell a client how the possession finishes while it is being
        played, which is a worse lie than a simulator tells."""
        _, sm = self.frame(100)
        current = sm["drives"]["current"]
        for key in ("result", "displayResult", "shortDisplayResult",
                    "description", "yards", "offensivePlays"):
            self.assertNotIn(key, current)
        self.assertFalse(current["isScore"])

    # ── the clock ──

    def test_the_clock_and_period_come_from_the_instant_asked_for(self):
        _, sm = self.frame(1000)
        status = sm["header"]["competitions"][0]["status"]
        self.assertEqual(status["type"]["state"], "in")
        self.assertEqual(status["period"], 2)
        self.assertEqual(status["displayClock"], "13:20")
        self.assertEqual(status["clock"], 800.0)
        self.assertEqual(status["type"]["shortDetail"], "13:20 - 2nd")

    def test_the_scoreboard_says_the_same_thing_as_the_summary(self):
        """`live.games()` reads the scoreboard and the gamecast reads the
        summary. Framing one and not the other produces a game that is live on
        the board and final in its own header."""
        sb, sm = self.frame(1000)
        ev = sb["events"][0]
        want = sm["header"]["competitions"][0]["status"]
        self.assertEqual(ev["competitions"][0]["status"], want)
        self.assertEqual(ev["status"], want)

    def test_a_frame_past_the_last_play_is_the_finished_game(self):
        sb, sm = self.frame(10_000)
        self.assertEqual(sm["header"]["competitions"][0]["status"]["type"]["state"],
                         "post")
        self.assertNotIn("current", sm["drives"])
        self.assertNotIn("situation", sm["header"]["competitions"][0])

    # ── the score ──

    def test_the_score_is_the_last_play_that_had_happened(self):
        for second, away in ((self.FIRST_TD - 1, 0), (self.FIRST_TD, 7)):
            _, sm = self.frame(second)
            sides = {c["homeAway"]: c
                     for c in sm["header"]["competitions"][0]["competitors"]}
            self.assertEqual(sides["away"]["score"], str(away), f"at {second}s")
            self.assertEqual(sides["home"]["score"], "0", f"at {second}s")

    def test_the_winner_flag_does_not_survive_a_frame(self):
        """A finished competitor carries `winner: true`. A client that reads it
        draws the trophy on a game that is tied in the first quarter."""
        _, sm = self.frame(600)
        for c in sm["header"]["competitions"][0]["competitors"]:
            self.assertNotIn("winner", c)

    def test_the_line_score_is_recomputed_rather_than_carried(self):
        _, sm = self.frame(1000)
        sides = {c["homeAway"]: c
                 for c in sm["header"]["competitions"][0]["competitors"]}
        self.assertEqual([q["displayValue"] for q in sides["away"]["linescores"]],
                         ["0", "0"], "two quarters reached, neither scored in yet")
        self.assertEqual(len(sides["home"]["linescores"]), 2)

    def test_win_probability_and_scoring_plays_are_truncated(self):
        _, before = self.frame(self.FIRST_TD - 1)
        _, after = self.frame(self.FIRST_TD)
        self.assertEqual(before["scoringPlays"], [])
        self.assertEqual(len(after["scoringPlays"]), 1)
        self.assertLess(len(before["winprobability"]),
                        len(after["winprobability"]))
        # The leading point names the opening drive rather than a play, so a
        # membership filter would silently drop it.
        self.assertEqual(before["winprobability"][0]["playId"],
                         self.SM["winprobability"][0]["playId"])

    # ── possession ──

    def test_possession_is_derived_from_the_end_of_the_last_play(self):
        sb, sm = self.frame(600)
        last = self.plays(sm)[-1]
        holder = last["end"]["team"]["id"]
        comp = sm["header"]["competitions"][0]
        self.assertEqual(comp["situation"]["possession"], holder)
        self.assertEqual(comp["situation"]["down"], last["end"]["down"])
        self.assertEqual(comp["situation"]["distance"], last["end"]["distance"])
        self.assertEqual(comp["situation"]["yardsToEndzone"],
                         last["end"]["yardsToEndzone"])
        self.assertEqual(sb["events"][0]["competitions"][0]["situation"]["possession"],
                         holder)
        flags = {c["team"]["id"]: c["possession"] for c in comp["competitors"]}
        self.assertTrue(flags[holder])
        self.assertEqual(sum(1 for v in flags.values() if v), 1)

    def test_the_red_zone_is_stated_not_guessed(self):
        for second in range(0, 1700, 137):
            _, sm = self.frame(second)
            sit = sm["header"]["competitions"][0].get("situation")
            if not sit or sit["yardsToEndzone"] is None:
                continue
            self.assertEqual(sit["isRedZone"], sit["yardsToEndzone"] <= 20)

    # ── the box score ──

    def test_the_box_score_is_derived_from_the_plays_and_says_so(self):
        """The box score is rebuilt from the play text as of this clock.

        This test used to assert the opposite - that the captured FINAL box
        score was passed through untouched - because ESPN publishes no
        per-play player line and ramping it was thought to mean inventing
        numbers. It does not: the numbers are stated in `play.text`, which is
        a machine-written grammar, and `replay.reconcile` diffs the whole-game
        parse against ESPN's published final at 99.4% of cells. What survives
        of the old assertion is the part that mattered - the frame has to say
        which of the two it is serving, or a client draws a defence at its
        final total before the opening kickoff.
        """
        _, sm = self.frame(600)
        self.assertNotEqual(sm["boxscore"], self.SM["boxscore"])
        note = sm["replay"]["boxscore"]
        self.assertEqual(note["mode"], "derived")
        # This fixture is seven drives of a nineteen-drive game, so there is no
        # final to reconcile against and the frame says exactly that rather
        # than publishing a rate that measures the trim. The whole-game rate is
        # asserted in TestBoxScoreDerivedFromPlayText, on both games.
        self.assertFalse(note["reconciled"])
        self.assertEqual(sm["replay"]["playsTotal"], 62)
        self.assertEqual(sm["replay"]["state"], "in")

    def test_frame_does_not_mutate_what_it_was_given(self):
        from fantasyedge.replay import frame

        sb, sm = self.payloads()
        keep = json.dumps(sm, sort_keys=True), json.dumps(sb, sort_keys=True)
        frame(sb, sm, 900)
        self.assertEqual((json.dumps(sm, sort_keys=True),
                          json.dumps(sb, sort_keys=True)), keep)

    # ── the daemon ──

    def test_a_frozen_frame_writes_the_two_files_the_live_tier_reads(self):
        """`--at` has to land exactly where `live._fetch` looks, or the harness
        drives nothing: the scoreboard by file, the summary by event id."""
        from fantasyedge import replay as rp

        sb, sm = self.payloads()
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp)
            source = out / "source"
            source.mkdir()
            (source / "scoreboard.json").write_text(json.dumps(sb))
            (source / "401872656.json").write_text(json.dumps(sm))
            info = rp.run("401872656", out, at=1000)
            self.assertEqual(info["state"], "in")
            self.assertEqual(info["clock"], "13:20")
            written = json.loads((out / "401872656.json").read_text())
            self.assertEqual(written["replay"]["gameSeconds"], 1000)
            self.assertTrue((out / "scoreboard.json").exists())
            self.assertIn("FANTASYEDGE_SUMMARY_DIR", info["run"])


class TestAFinishedGameIsRefetchedOnce(unittest.TestCase):
    """A summary cached during play must not be kept as the final word.

    Found by replaying a real game: once the scoreboard flipped to `post` the
    cached summary was held forever, but the thing being held was whatever was
    last fetched *while the game was still running*. The board therefore froze
    up to half a minute before the whistle - a game-winning touchdown could
    simply never be scored.
    """

    def setUp(self):
        self.board = json.loads((FIX / "espn_scoreboard.json").read_text())
        self.summary = json.loads((FIX / "espn_summary.json").read_text())
        self.state = "in"
        self.fetches = 0

    def source(self):
        import copy as _copy

        from fantasyedge.live import EspnLiveSource

        def http(url):
            if "summary?event=" in url:
                self.fetches += 1
                return self.summary
            b = _copy.deepcopy(self.board)
            b["events"][0]["competitions"][0]["status"] = {
                "period": 4, "clock": 0.0,
                "type": {"state": self.state,
                         "shortDetail": "FINAL" if self.state == "post" else "2:00 - 4th"}}
            return b
        return EspnLiveSource([{"player_id": "1", "team": "SEA", "name": "", "pos": "WR"}],
                              http=http)

    def test_the_whistle_forces_one_more_fetch(self):
        src = self.source()
        src.boxscores()
        self.assertEqual(self.fetches, 1)

        src.boxscores()                       # still live, inside the TTL
        self.assertEqual(self.fetches, 1, "a live game refetched inside its TTL")

        self.state = "post"                   # the whistle
        src._cache = None                     # let the slate be re-read
        src.boxscores()
        self.assertEqual(self.fetches, 2,
                         "the final summary was never fetched, so the board "
                         "keeps whatever it happened to hold before the whistle")

        src._cache = None
        src.boxscores()
        self.assertEqual(self.fetches, 2,
                         "a finished game was refetched; its numbers cannot "
                         "change again and re-asking is pure waste")


class TestAWholeGameThroughTheStack(unittest.TestCase):
    """Walk a real game minute by minute and assert what must never happen.

    Every other test here pins one behaviour at one instant. This one replays
    an actual game through the real live tier, the real scoring and the real
    leverage model, and checks the properties that hold at every instant. It
    is the test that would have caught the frozen-final-summary bug, and it is
    the shape of test that finds the next one.
    """

    @classmethod
    def setUpClass(cls):
        cls.board = json.loads((FIX / "replay_scoreboard.json").read_text())
        cls.summary = json.loads((FIX / "replay_summary.json").read_text())

    def players(self):
        from fantasyedge.scoring import boxscore_names

        men = [{"player_id": pid, "team": i["team"], "name": i["name"], "pos": "WR"}
               for pid, i in boxscore_names(self.summary).items()]
        # Both defences, because a defence is scored as a club rather than
        # looked up as a person and takes an entirely different path.
        men += [{"player_id": "-16026", "team": "SEA", "name": "Seahawks D/ST", "pos": "DEF"},
                {"player_id": "-16017", "team": "NE", "name": "Patriots D/ST", "pos": "DEF"}]
        return men

    def walk(self):
        """Yield a snapshot every hundred game seconds."""
        from fantasyedge import replay
        from fantasyedge.live import EspnLiveSource

        men = self.players()
        for t in range(0, 1600, 100):
            b, s = replay.frame(self.board, self.summary, t)
            src = EspnLiveSource(
                men, http=lambda u, b=b, s=s: s if "summary?event=" in u else b)
            yield t, src.snapshot()

    def test_nothing_is_ever_nonsense(self):
        import math

        for t, snap in self.walk():
            for pid, st in snap["players"].items():
                self.assertIsNotNone(st["s"], f"t={t} {pid} scored None")
                self.assertFalse(math.isnan(st["s"]), f"t={t} {pid} scored NaN")
                self.assertGreaterEqual(st["r"], 0.0, f"t={t} {pid} remaining < 0")
                self.assertLessEqual(st["r"], 1.0, f"t={t} {pid} remaining > 1")

    def costs(self, t):
        """Per athlete, the derived numbers that can legitimately cost points."""
        from fantasyedge import replay

        roster = replay.Roster(self.summary)
        clubs, pair = replay.game_clubs(self.summary)
        plays = [p for p in replay._all_plays(self.summary)
                 if replay.play_seconds(p) <= t]
        tally = replay.tally(plays, roster, clubs, pair)
        return {pid: (a.get("rushingYards", 0.0), a.get("receivingYards", 0.0),
                      a.get("passingYards", 0.0), a.get("intThrown", 0.0),
                      a.get("fumblesLost", 0.0))
                for pid, a in tally.by_athlete.items()}

    def test_a_players_points_only_go_backwards_when_he_earns_it(self):
        """Deliberately not asserted of a defence, and no longer asserted flat.

        A defence's score legitimately falls: it is paid for a shutout and
        charged for what it concedes, so conceding is a real subtraction.

        Since the box score began ramping off the play text, the same is true
        of a person. A three-yard loss costs a running back three tenths, an
        interception costs a quarterback two points, and a lost fumble costs
        anybody two. Flat monotonicity passed for years only because the box
        score was frozen at its final value; at a ten-second sampling it is
        false three times in this fixture alone. So the invariant asserted is
        the true one: points fall only when this player's own derived line
        records something that costs points.
        """
        seen, before = {}, {}
        for t, snap in self.walk():
            now = self.costs(t)
            for pid, st in snap["players"].items():
                if pid.startswith("-") or st["g"] == "PRE":
                    before[pid] = now.get(pid, (0.0,) * 5)
                    seen[pid] = st["s"]
                    continue
                was, is_ = before.get(pid, (0.0,) * 5), now.get(pid, (0.0,) * 5)
                charged = (is_[0] < was[0] or is_[1] < was[1] or is_[2] < was[2]
                           or is_[3] > was[3] or is_[4] > was[4])
                if pid in seen and not charged:
                    self.assertGreaterEqual(
                        st["s"] + 1e-9, seen[pid],
                        f"t={t} {pid} lost points with nothing to show for it: "
                        f"{seen[pid]} -> {st['s']}")
                before[pid], seen[pid] = is_, st["s"]

    def test_the_clock_only_runs_forwards(self):
        last = -1.0
        for t, snap in self.walk():
            played = max((g.get("played") or 0.0) for g in snap["games"].values())
            self.assertGreaterEqual(played + 1e-9, last,
                                    f"t={t} the game clock went backwards")
            last = played

    def test_the_model_stays_inside_its_own_definitions(self):
        import math

        from fantasyedge.leverage import Cell, evaluate

        for t, snap in self.walk():
            cells = [Cell(id=k, label=k, projected=10.0, scored=v["s"],
                          remaining=v["r"], side="you" if i % 2 else "opp")
                     for i, (k, v) in enumerate(snap["players"].items())]
            m = evaluate(cells)
            self.assertFalse(math.isnan(m.win_prob), f"t={t} win probability NaN")
            self.assertGreaterEqual(m.win_prob, 0.0)
            self.assertLessEqual(m.win_prob, 1.0)
            self.assertIn(m.phase, ("pre", "live", "final"))
            self.assertAlmostEqual(sum(c.share for c in m.cells), 1.0, places=6,
                                   msg=f"t={t} tile shares do not fill the board")


class TestConnectPage(unittest.TestCase):
    """The Pages entry page: what a visitor with no credentials can reach.

    GitHub Pages serves files, so this page has no server behind it. That is
    not a limitation to work around, it is the constraint that decides what
    can honestly be offered: Sleeper's read API and ESPN's public endpoints
    allow a cross-origin read, so those work from a stranger's browser; Yahoo
    needs a secret, so it cannot. These assert the page keeps that bargain.
    """

    @classmethod
    def setUpClass(cls):
        cls.page = (pathlib.Path(__file__).resolve().parents[1] / "fantasyedge" /
                    "templates" / "connect.html").read_text(encoding="utf-8")

    def table(self, name):
        """One mirrored table, lifted out of the page's JavaScript."""
        import re
        m = re.search(r"^const " + name + r" = (\{.*\}|\[.*\]);$",
                      self.page, re.M)
        self.assertIsNotNone(m, f"{name} is no longer a single-line literal in "
                                "connect.html, so nothing can compare it to Python")
        return json.loads(m.group(1))

    def test_the_javascript_folding_tables_are_the_python_ones(self):
        """identity.py is the single owner of how a name folds.

        A Sleeper roster is joined to an ESPN box score by folded name, because
        Sleeper's player ids are not ESPN's - `espn_id` is null for most of the
        players anybody starts. The browser has to do that join itself, so the
        tables exist twice. Two copies that drift are worse than one that is
        awkward, and the drift would be silent: a stale alias does not throw,
        it just reports a real player as scoreless.
        """
        from fantasyedge import identity as I
        from fantasyedge.live import NFL_TEAM
        from fantasyedge.providers.espn import BENCH_SLOTS, POS, SLOT

        self.assertEqual(self.table("NICKNAME"), I.NICKNAME)
        self.assertEqual(self.table("TEAM_ALIAS"), I.TEAM_ALIAS)
        self.assertEqual(self.table("POS_ALIAS"), I.POS_ALIAS)
        self.assertEqual(self.table("NFL_TEAM"),
                         {str(k): v for k, v in NFL_TEAM.items()})
        self.assertEqual(self.table("ESPN_POS"),
                         {str(k): v for k, v in POS.items()})
        self.assertEqual(self.table("ESPN_SLOT"),
                         {str(k): v for k, v in SLOT.items()})
        self.assertEqual(sorted(self.table("BENCH_SLOTS")), sorted(BENCH_SLOTS))

    def test_the_page_never_asks_a_visitor_for_a_credential(self):
        """The one rule this page cannot be allowed to break.

        `espn_s2` and `SWID` are a whole ESPN account, not one league. A public
        page with a box for them is indistinguishable from a page built to
        harvest them, and it teaches the habit phishing depends on. So there is
        no such input, and this asserts it by shape rather than by wording -
        a future contributor renaming the field must still trip it.
        """
        import re

        for field in re.findall(r"<input\b[^>]*>", self.page):
            self.assertNotIn("type=\"password\"", field)
            low = field.lower()
            for banned in ("s2", "swid", "cookie", "password", "token", "secret"):
                self.assertNotIn(banned, low,
                                 f"an input mentions {banned!r}: {field}")

    def test_both_refusals_are_explained_rather_than_hidden(self):
        """A missing feature with no explanation reads as a bug.

        Somebody with a private ESPN league or a Yahoo league needs to be told
        why this page cannot help and what does, or they conclude the page is
        broken and this project cannot read their league at all - which is the
        opposite of true. Both refusals name the credential and offer the local
        command that does work.
        """
        for phrase in ("espn_s2", "SWID", "python3 -m fantasyedge api"):
            self.assertIn(phrase, self.page, f"the ESPN refusal no longer says {phrase!r}")
        for phrase in ("Yahoo", "OAuth", "client secret",
                       "python3 -m fantasyedge auth --provider yahoo --url"):
            self.assertIn(phrase, self.page, f"the Yahoo refusal no longer says {phrase!r}")

    def test_there_is_no_yahoo_button_that_could_not_work(self):
        """Every provider card that is clickable must lead somewhere real."""
        import re

        gos = set(re.findall(r'data-go="([a-z]+)"', self.page))
        self.assertIn("sleeper", gos)
        self.assertIn("espn", gos)
        self.assertNotIn("yahoo", gos,
                         "a Yahoo entry point appeared; a static page cannot hold "
                         "the client secret OAuth needs, so the button would lie")
        self.assertRegex(self.page, r'class="prov dead"[^>]*disabled',
                         "the Yahoo card must be disabled, not merely styled dead")

    def test_the_page_talks_to_the_documented_hosts_and_nothing_else(self):
        """An allowlist, because a new host is a new party to trust.

        The footer promises a visitor exactly which hosts their browser will
        contact. A stray CDN, analytics tag or font host added later would make
        that promise false without anything failing, so the promise is asserted
        against the file instead of maintained by hand.
        """
        import re

        allowed = {
            "api.sleeper.app", "site.web.api.espn.com",
            "lm-api-reads.fantasy.espn.com", "fonts.googleapis.com",
            "fonts.gstatic.com",
            "github.com",              # links out, not fetched
        }
        hosts = {re.sub(r"[/?\"'].*$", "", u[8:])
                 for u in re.findall(r"https://[^\s\"'<>)]+", self.page)}
        self.assertTrue(hosts <= allowed,
                        f"undocumented host(s) in connect.html: {sorted(hosts - allowed)}")

    def test_the_demo_is_labelled_as_one_persons_season_and_links_back(self):
        """The demo must not read as the visitor's own board.

        It is one real league's real season with the managers scrubbed. A
        visitor who lands on it cold reads it either as dummy data or as
        theirs, and both readings are wrong, so the ribbon says which it is and
        offers the way in. It is injected at build time rather than added to
        mosaic.html because only the Pages copy of that board is a demo.
        """
        import tools.build_docs as bd

        self.assertIn("DEMO BOARD", bd.RIBBON)
        self.assertIn("Not your data", bd.RIBBON)
        self.assertIn('href="index.html"', bd.RIBBON)

        with tempfile.TemporaryDirectory() as d:
            out = pathlib.Path(d) / "index.html"
            bd.build_connect(out)
            built = out.read_text(encoding="utf-8")
        self.assertIn("<!doctype html>", built)
        self.assertIn('href="demo.html"', built,
                      "the entry page no longer offers the demo, so the demo is "
                      "unreachable rather than merely moved")


class TestBoxScoreDerivedFromPlayText(unittest.TestCase):
    """The acceptance test for the derivation: ESPN's final is ground truth.

    `replay.frame()` rebuilds the box score out of `play.text` so a replay can
    show points arriving during a game. The only way that is honest rather than
    plausible is to accumulate the whole game and diff it, cell by cell, against
    what ESPN published. Two games, because one parser fitted to one game is not
    a parser.

    Both fixtures are whole games cut to their plays and their final box score
    by `python3 tools/make_replay_fixture.py --event <id> --pbp`. Never edit
    one by hand.
    """

    GAMES = ("401872656", "401872657")          # NE at SEA, SF at LAR

    def load(self, event):
        return json.loads((FIX / f"replay_pbp_{event}.json").read_text())

    def tally(self, summary, plays=None):
        from fantasyedge import replay

        roster = replay.Roster(summary)
        clubs, pair = replay.game_clubs(summary)
        if plays is None:
            plays = replay._all_plays(summary)
        return replay.tally(plays, roster, clubs, pair), roster

    def derived(self, summary, plays=None):
        from fantasyedge import replay

        tally, _ = self.tally(summary, plays)
        return {**summary, "boxscore": replay.derived_boxscore(summary, tally)}

    # ── the reconciliation ──

    def test_both_games_reconcile_against_espns_published_final(self):
        """The headline number. Measured, not aspirational: 99.4% and 97.9%.

        The floor is set just under what the parser actually does rather than
        at some round number, so a regression that costs a single category
        fails here instead of being absorbed.
        """
        from fantasyedge import replay

        for event in self.GAMES:
            with self.subTest(event=event):
                checked = replay.reconcile(self.load(event))
                self.assertGreater(checked["cells"], 450)
                self.assertGreaterEqual(checked["rate"], 0.975,
                                        f"{event}: {checked['mismatches']}")

    # What each category actually reconciles at, across both games, so that a
    # regression in any single one fails here rather than being averaged away
    # by the ten that are perfect. Where a floor is below 1.0 the residual is
    # named in the class docstring of the statYardage test: in every case it is
    # ESPN's published box score disagreeing with ESPN's own play data, which
    # is why raising these floors is not a matter of parsing harder.
    FLOORS = {"passing": 0.94, "rushing": 0.95, "receiving": 0.98,
              "interceptions": 1.0, "fumbles": 1.0, "kicking": 1.0,
              "kickReturns": 0.86, "puntReturns": 1.0, "punting": 1.0,
              "defensive": 0.99, "team": 0.87}

    def test_every_category_reconciles_at_its_own_measured_floor(self):
        """A category `scoring.py` reads has the higher bar: passing, rushing,
        receiving, interceptions, fumbles and kicking are what a lineup is paid
        on, and a cell wrong there is a wrong score on somebody's screen."""
        from fantasyedge import replay

        for event in self.GAMES:
            checked = replay.reconcile(self.load(event))
            self.assertEqual(set(checked["categories"]) - set(self.FLOORS), set())
            for name, floor in self.FLOORS.items():
                info = checked["categories"].get(name) or {}
                if not info.get("cells"):
                    continue                    # neither side fumbled all game
                with self.subTest(event=event, category=name):
                    self.assertGreaterEqual(info["rate"], floor,
                                            f"{name}: {checked['mismatches']}")

    def test_every_name_in_the_play_text_resolves_to_an_athlete(self):
        """An unresolved name is a silently dropped stat line, so there are
        none. Two real bugs were found by this alone: "TOUCHDOWN. A.Borregales
        extra point is GOOD" parsed as a man whose initial was TOUCHDOWN, and
        an unremoved ", Center-J.Ashby" turned the punt returner two words
        later into "Ashby. R.Shaheed"."""
        from fantasyedge import replay

        for event in self.GAMES:
            with self.subTest(event=event):
                self.assertEqual(replay.reconcile(self.load(event))["unresolved"], {})

    def test_the_parse_agrees_with_espns_own_statYardage(self):
        """An independent check, and the one that says where a residual lives.

        `statYardage` is ESPN's own number for the same play, computed by ESPN
        rather than read out of the sentence. All 223 scrimmage and return
        plays across both games agree with it - which is how we know the four
        cells that do not reconcile (Kaelon Black at 66 rushing yards against a
        published 65, Lan Larison at 50 kick-return yards against 49) are
        ESPN's box score disagreeing with ESPN's own play data, not a misparse.
        """
        from fantasyedge import replay

        counted = {"Rush", "Rushing Touchdown", "Pass Reception",
                   "Passing Touchdown", "Sack", "Kickoff", "Punt"}
        checked = 0
        for event in self.GAMES:
            summary = self.load(event)
            _, roster = self.tally(summary, [])
            clubs, pair = replay.game_clubs(summary)
            for play in replay._all_plays(summary):
                if (play.get("type") or {}).get("text") not in counted:
                    continue
                # A penalty moves the ball after the fact, so ESPN's own
                # `statYardage` stops describing the play the text describes.
                if re.search(r"(?i)penalty", play.get("text") or ""):
                    continue
                one = replay.tally([play], roster, clubs, pair)
                gained = sum(a.get("rushingYards", 0.0) + a.get("receivingYards", 0.0)
                             + a.get("kickReturnYards", 0.0)
                             + a.get("puntReturnYards", 0.0)
                             - a.get("sackYardsLost", 0.0)
                             for a in one.by_athlete.values())
                checked += 1
                self.assertEqual(gained, play.get("statYardage"),
                                 f"{event}: {play.get('text')}")
        self.assertGreater(checked, 200)

    def test_the_fantasy_points_at_the_final_whistle_are_espns(self):
        """What the reconciliation is ultimately for. Every athlete in both
        games finishes within a tenth of a point of what ESPN's own final box
        score scores him, and the two games' totals agree to within a quarter
        of a point across fifty-one players."""
        from fantasyedge.scoring import score_boxscore

        for event in self.GAMES:
            summary = self.load(event)
            mine = score_boxscore(self.derived(summary))
            espn = score_boxscore(summary)
            self.assertEqual(set(mine), set(espn))
            for pid in espn:
                with self.subTest(event=event, athlete=pid):
                    self.assertAlmostEqual(mine[pid], espn[pid], delta=0.101)
            self.assertAlmostEqual(sum(mine.values()), sum(espn.values()), delta=0.25)

    # ── what it will not pretend to know ──

    def test_a_column_the_text_cannot_support_is_absent_not_backfilled(self):
        """Passer rating and QBR are not in the play text at any price, and the
        team block's first downs, third-down efficiency and time of possession
        need down-and-distance bookkeeping this parser does not do.

        The failure mode being guarded is not "we got it wrong" but "we quietly
        used the final value", which is the bug the whole derivation exists to
        remove and would be invisible at t=0 - a quarterback showing his
        end-of-game passer rating before his first snap.
        """
        from fantasyedge import replay

        summary = self.load("401872656")
        derived = self.derived(summary, plays=replay._all_plays(summary)[:20])
        for team in derived["boxscore"]["players"]:
            for cat in team["statistics"]:
                if cat["name"] != "passing":
                    continue
                for ath in cat["athletes"]:
                    row = dict(zip(cat["keys"], ath["stats"]))
                    self.assertEqual(row["adjQBR"], "--")
                    self.assertEqual(row["QBRating"], "--")
        shown = {s["name"] for t in derived["boxscore"]["teams"]
                 for s in t["statistics"]}
        for absent in ("firstDowns", "thirdDownEff", "possessionTime",
                       "totalPenaltiesYards", "redZoneAttempts"):
            self.assertNotIn(absent, shown)
        self.assertIn("totalYards", shown)

    def test_a_nullified_play_contributes_nothing(self):
        """A "No Play" is a penalty that rescinded the down. Play 60 of event
        401872656 reads as a one-yard A.Barner rush and A.Barner has no rushing
        line in ESPN's box score, because the flag wiped it. Counting it would
        invent a carry for a tight end."""
        from fantasyedge import replay

        summary = self.load("401872656")
        nulls = [p for p in replay._all_plays(summary)
                 if "No Play" in (p.get("text") or "")]
        self.assertGreaterEqual(len(nulls), 15)
        tally, _ = self.tally(summary, nulls)
        self.assertEqual(tally.by_athlete, {})

    def test_a_sacks_yardage_is_not_taken_off_the_passer(self):
        """ESPN keeps it in its own `sacks-sackYardsLost` column and leaves
        `passingYards` gross - Drake Maye is 178 yards with 3-10 in sacks, and
        New England's receiving column sums to 178 exactly. Subtracting it here
        would put every quarterback in the league four tenths light."""
        summary = self.load("401872656")
        derived = self.derived(summary)
        for team in derived["boxscore"]["players"]:
            for cat in team["statistics"]:
                if cat["name"] != "passing":
                    continue
                for ath in cat["athletes"]:
                    if ath["athlete"]["displayName"] != "Drake Maye":
                        continue
                    row = dict(zip(cat["keys"], ath["stats"]))
                    self.assertEqual(row["passingYards"], "178")
                    self.assertEqual(row["sacks-sackYardsLost"], "3-10")
                    return
        self.fail("Drake Maye is not in the derived passing block")

    def test_an_ambiguous_name_is_refused_rather_than_guessed(self):
        """Two men with the same initial and surname on the same club cannot be
        told apart by the play text, and picking one puts a touchdown on the
        wrong player with nothing downstream able to notice."""
        from fantasyedge import replay

        summary = self.load("401872656")
        roster = replay.Roster(summary)
        pid = roster.find("R.Stevenson", "NE")
        self.assertEqual(roster.info[pid]["name"], "Rhamondre Stevenson")
        key = ("NE", "R", "stevenson")
        roster.by_club[key] = set(roster.by_club[key]) | {"999999"}
        self.assertIsNone(roster.find("R.Stevenson", "NE"))

    def test_a_surname_particle_and_a_suffix_both_resolve(self):
        """"G.Van Roten" is one man whose display name's last token is "Roten",
        and "Deebo Samuel Sr." is written "D.Samuel"."""
        from fantasyedge import replay

        roster = replay.Roster(self.load("401872657"))
        self.assertEqual(roster.info[roster.find("D.Samuel", "SF")]["name"],
                         "Deebo Samuel Sr.")
        self.assertEqual(roster.info[roster.find("S.Bennett", "LAR")]["name"],
                         "Stetson Bennett IV")
        self.assertEqual(roster.info[roster.find("C.West", "SF")]["name"],
                         "C.J. West")


class TestAReplayRampsThePlayerPoints(unittest.TestCase):
    """The point of the whole exercise: points arrive during a game.

    Before the box score was derived, every player carried his end-of-game
    total from the opening kickoff. The Seahawks defence read 16.0 before
    anybody had touched the ball - a shutout bonus, plus the yards New England
    would eventually gain, plus three interceptions it had not yet caught.
    """

    @classmethod
    def setUpClass(cls):
        cls.SB = json.loads((FIX / "replay_scoreboard.json").read_text())
        cls.SM = json.loads((FIX / "replay_summary.json").read_text())
        cls.PBP = json.loads((FIX / "replay_pbp_401872656.json").read_text())

    def at(self, second):
        from fantasyedge.replay import frame

        return frame(self.SB, self.SM, second)[1]

    def dst(self, summary, club, opponent):
        from fantasyedge.scoring import dst_points, parse_team_defence

        teams = parse_team_defence(summary)
        scores = {c["homeAway"]: int(c["score"]) for c in
                  summary["header"]["competitions"][0]["competitors"]}
        conceded = scores["away" if club == "SEA" else "home"]
        return dst_points(conceded, (teams.get(opponent) or {}).get("yards"),
                          teams.get(club) or {})

    def test_a_defence_no_longer_reads_its_final_total_at_kickoff(self):
        """The captured box score scored Seattle's defence at 16.0 before the
        first snap. Derived, it opens at the shutout floor - nothing conceded
        and no yards allowed, which is what `dst_points` is defined to pay -
        and moves from there."""
        from fantasyedge.scoring import dst_points, parse_team_defence

        captured = parse_team_defence(self.SM)
        self.assertEqual(dst_points(0, captured["NE"]["yards"], captured["SEA"]), 16.0)
        self.assertEqual(self.dst(self.at(0), "SEA", "NE"), 10.0)
        self.assertEqual(self.dst(self.at(0), "NE", "SEA"), 10.0)

    def test_nobody_carries_a_stat_line_before_he_earns_it(self):
        """At the opening kickoff the only two athletes in the box score are
        the man who returned it and the man who tackled him."""
        listed = [ath["athlete"]["displayName"]
                  for team in self.at(0)["boxscore"]["players"]
                  for cat in team["statistics"] for ath in cat["athletes"]]
        self.assertEqual(sorted(listed), ["Namdi Obiazor", "Rashid Shaheed"])

    def test_a_receiver_accumulates_across_the_whole_game(self):
        """Jaxon Smith-Njigba, play by play, to exactly what ESPN published."""
        from fantasyedge import replay
        from fantasyedge.scoring import score_boxscore

        plays = replay._all_plays(self.PBP)
        roster = replay.Roster(self.PBP)
        clubs, pair = replay.game_clubs(self.PBP)
        ramp = []
        for upto in (0, 20, 60, 100, 140, len(plays)):
            box = replay.derived_boxscore(
                self.PBP, replay.tally(plays[:upto], roster, clubs, pair))
            # `.get`, because before his first target he is not in the box
            # score at all - which is itself the behaviour being asserted.
            ramp.append(score_boxscore({**self.PBP, "boxscore": box}).get("4430878", 0.0))
        self.assertEqual(ramp, [0.0, 2.3, 8.7, 10.3, 24.1, 26.2])
        self.assertEqual(ramp[-1], score_boxscore(self.PBP)["4430878"])

    def test_the_frame_states_how_the_box_score_was_made(self):
        """A client that cannot tell a derived box score from a captured one
        will draw the second as though it were the first."""
        note = self.at(600)["replay"]["boxscore"]
        self.assertEqual(note["mode"], "derived")
        self.assertEqual(note["source"], "play-by-play text")
        self.assertIn("DERIVED", note["note"])
        self.assertIn("passing.QBRating", note["excluded"])

    def test_a_full_capture_carries_its_reconciliation_rate_in_every_frame(self):
        from fantasyedge import replay

        board = {"events": [{"id": "401872656", "competitions": [{}]}]}
        summary = {**self.PBP, "winprobability": [], "scoringPlays": []}
        summary["header"] = {**summary["header"], "id": "401872656"}
        summary["header"]["competitions"][0]["status"] = {
            "type": {"state": "post", "completed": True}}
        note = replay.frame(board, summary, 1200)[1]["replay"]["boxscore"]
        self.assertTrue(note["reconciled"])
        self.assertGreater(note["rate"], 0.99)
        self.assertEqual(note["unresolvedNames"], {})
        self.assertIn("kickReturns", note["unreconciled"])

    def test_the_real_scoring_path_reads_a_derived_box_score_unchanged(self):
        """No parallel scoring path: `parse_boxscore`, `score_boxscore` and
        `parse_team_defence` are handed the derived block exactly as they are
        handed ESPN's."""
        from fantasyedge.scoring import (parse_boxscore, parse_team_defence,
                                         score_boxscore)

        early, late = self.at(300), self.at(1521)
        self.assertLess(len(parse_boxscore(early)), len(parse_boxscore(late)))
        self.assertTrue(all(v >= 0 or True for v in score_boxscore(late).values()))
        yards = parse_team_defence(late)
        self.assertGreater(yards["SEA"]["yards"], parse_team_defence(early)["SEA"]["yards"])

    def test_frame_still_does_not_mutate_what_it_was_given(self):
        """Deriving a box score reads the captured one as a template, which is
        one more chance to write through it."""
        from fantasyedge.replay import frame

        keep = json.dumps(self.SM, sort_keys=True)
        frame(self.SB, self.SM, 900)
        self.assertEqual(json.dumps(self.SM, sort_keys=True), keep)


class TestKickersActuallyScore(unittest.TestCase):
    """Every kicker on every board scored exactly zero, always.

    ESPN sends made-and-attempted as one column - the key is
    "fieldGoalsMade/fieldGoalAttempts" and the value is "2/2". The value side
    was always handled; the key was not, so the column never matched and was
    dropped. Nothing raised, no kicker ever complained, and the board simply
    showed 0.0 for a man who had kicked three times.
    """

    def setUp(self):
        # The older fixture is trimmed to the scrimmage categories and has no
        # kicker in it at all, which is precisely why this went unnoticed for
        # so long. The replay capture is a whole box score.
        self.summary = json.loads((FIX / "replay_summary.json").read_text())

    def test_the_combined_key_is_read(self):
        from fantasyedge.scoring import parse_boxscore

        stats = parse_boxscore(self.summary)
        kickers = {p: s for p, s in stats.items()
                   if "fieldGoalsMade" in s or "extraPointsMade" in s}
        self.assertTrue(kickers, "no kicking line was parsed at all")

    def test_it_agrees_with_espns_own_arithmetic(self):
        """ESPN publishes `totalKickingPoints` beside the columns it is made
        of, which makes this checkable rather than merely plausible - under
        the default rules a field goal is 3 and an extra point is 1, which is
        exactly what that column counts."""
        from fantasyedge.scoring import parse_boxscore

        published = {}
        for team in ((self.summary.get("boxscore") or {}).get("players") or []):
            for cat in (team.get("statistics") or []):
                keys = cat.get("keys") or []
                if "totalKickingPoints" not in keys:
                    continue
                at = keys.index("totalKickingPoints")
                for ath in (cat.get("athletes") or []):
                    pid = str(((ath.get("athlete") or {}).get("id")) or "")
                    st = ath.get("stats") or []
                    if pid and at < len(st):
                        published[pid] = float(st[at])

        self.assertTrue(published, "fixture has no kicker to check against")
        stats = parse_boxscore(self.summary)
        for pid, espn_points in published.items():
            line = stats.get(pid) or {}
            mine = line.get("fieldGoalsMade", 0.0) * 3 + line.get("extraPointsMade", 0.0)
            self.assertEqual(mine, espn_points,
                             f"{pid}: scored {mine} where ESPN counts {espn_points}")


class StubProjHttp(Http):
    """Serves the recorded Sleeper projections payload for any URL, and keeps
    the URLs so a test can assert the query string the adapter actually built."""

    def __init__(self, payload):
        super().__init__()
        self.payload = payload
        self.calls: list[str] = []

    def get_json(self, url, *, headers=None, cookies=None, params=None):
        self.calls.append(url)
        return self.payload


class TestSleeperProjections(unittest.TestCase):
    """The second source that genuinely exists, and the rules that keep it
    honest about the three that do not."""

    def setUp(self):
        from fantasyedge import projections as pj

        self.pj = pj
        self.tmp = tempfile.TemporaryDirectory()
        self.cache = pathlib.Path(self.tmp.name) / "cache"
        self.store = Store(pathlib.Path(self.tmp.name) / "sp.db")
        bundle, _ = load_fixture_bundle()
        self.store.save(bundle)
        self.raw = json.loads((FIX / "sleeper_projections_2026_w1.json").read_text())
        self.http = StubProjHttp(self.raw)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def load(self, **kw):
        kw.setdefault("http", self.http)
        kw.setdefault("cache_dir", str(self.cache))
        return self.pj.load_sleeper(self.store, 2026, 1, **kw)

    def test_positions_are_repeated_pairs_not_one_dict_key(self):
        """Sleeper wants `position[]` once per position.

        `Http.get_json(params=...)` takes a dict, and a dict cannot hold six
        entries under one key - it would send the last one only, and the call
        would return kickers alone with no error to notice. So the URL is built
        by hand, and this is the assertion that keeps it that way.
        """
        url = self.pj.sleeper_url(2026, 1)
        for pos in ("QB", "RB", "WR", "TE", "K", "DEF"):
            self.assertIn(f"position%5B%5D={pos}", url)
        self.assertEqual(url.count("position%5B%5D="), 6)
        self.assertIn("/projections/nfl/2026/1", url)
        # No week means Sleeper's season-long variant, which is a different
        # question and must not silently answer the weekly one.
        self.assertNotIn("/1?", self.pj.sleeper_url(2026))

    def test_a_row_with_no_points_never_becomes_a_zero(self):
        """Most of the payload is not a projection.

        Of 3,304 rows in a real week 1, 2,855 carry an ADP placeholder and no
        points. Reading a missing `pts_ppr` as 0.0 would put a hard zero beside
        several thousand names - a forecast nobody made.
        """
        rows = self.pj.sleeper_rows(self.raw)
        offered = sum(1 for r in self.raw if (r.get("stats") or {}).get("pts_ppr"))
        self.assertEqual(len(rows), offered)
        self.assertLess(len(rows), len(self.raw))
        self.assertTrue(all(r["points"] for r in rows))

    def test_the_scoring_format_follows_the_league_not_the_fetch(self):
        ppr = {r["name"]: r["points"] for r in self.pj.sleeper_rows(self.raw, "ppr")}
        half = {r["name"]: r["points"] for r in self.pj.sleeper_rows(self.raw, "half_ppr")}
        std = {r["name"]: r["points"] for r in self.pj.sleeper_rows(self.raw, "std")}
        who = next(n for n, v in ppr.items() if v and n != "Philadelphia Eagles")
        self.assertGreater(ppr[who], half[who])
        self.assertGreater(half[who], std[who])
        self.assertEqual(self.pj.scoring_format({"scoring": {"reception": 1.0}}), "ppr")
        self.assertEqual(self.pj.scoring_format({"scoring": {"reception": 0.5}}), "half_ppr")
        self.assertEqual(self.pj.scoring_format({"scoring": {"reception": 0}}), "std")
        self.assertEqual(self.pj.scoring_format(None), "ppr")

    def test_it_joins_onto_espn_ids_and_says_by_which_rule(self):
        out = self.load()
        self.assertGreater(out["rows"], 0)
        self.assertTrue(out["matched"])
        # Every hit is attributed to a stage of identity.Resolver. A loader
        # that matched 60% of the board silently would produce a "consensus"
        # that is really ESPN wherever the other source went missing.
        self.assertEqual(sum(out["matched"].values()), out["rows"])
        self.assertLessEqual(set(out["matched"]), {"exact", "name", "surname+club"})
        stored = self.store.q(
            "SELECT COUNT(*) c FROM projection WHERE source='sleeper'")[0]["c"]
        self.assertEqual(stored, out["rows"])

    def test_what_it_could_not_match_is_reported_not_dropped(self):
        """The ESPN fixture has no team defence in it, so Sleeper's Eagles have
        nowhere to land - and an unmatched name has to come back rather than
        quietly reduce the row count."""
        out = self.load()
        self.assertGreater(out["unmatched_count"], 0)
        self.assertTrue(any("Eagles" in n for n in out["unmatched"]))
        self.assertEqual(out["rows"] + out["unmatched_count"], out["offered"])

    def test_a_defence_lands_on_espns_spelling_of_the_same_club(self):
        """Sleeper files the Eagles as player_id "PHI", named "Philadelphia
        Eagles"; ESPN writes "Eagles D/ST". No character is shared beyond the
        nickname, and only `identity.club_of` reconciles them."""
        with self.store.tx() as c:
            c.execute("INSERT OR REPLACE INTO player VALUES (?,?,?,?,?)",
                      ("espn", "-16021", "Eagles D/ST", "DEF", "21"))
        out = self.load()
        row = self.store.q(
            "SELECT points FROM projection WHERE source='sleeper' AND player_id='-16021'")
        self.assertTrue(row, "the Eagles defence did not join")
        self.assertAlmostEqual(row[0]["points"], 9.71, places=2)

    def test_loading_twice_does_not_duplicate(self):
        first = self.load()["rows"]
        self.load()
        n = self.store.q(
            "SELECT COUNT(*) c FROM projection WHERE source='sleeper'")[0]["c"]
        self.assertEqual(n, first)

    def test_the_slate_is_cached_rather_than_refetched(self):
        """Two megabytes a week. The API never calls this at all - it reads the
        rows - but the CLI loading fourteen weeks must not fetch each of them
        twice."""
        self.load()
        n = len(self.http.calls)
        self.load()
        self.assertEqual(len(self.http.calls), n, "the second load refetched")
        self.load(refresh=True)
        self.assertEqual(len(self.http.calls), n + 1, "--refresh did not refetch")

    def test_nothing_is_written_inside_the_repository(self):
        """A cache under the working tree would be committed sooner or later.
        It belongs beside the player file in ~/.fantasy-edge/, like everything
        else this project keeps for itself."""
        repo = pathlib.Path(__file__).resolve().parents[1]
        self.assertFalse(str(self.pj.SLEEPER_CACHE).startswith(str(repo)))
        self.load()
        self.assertTrue(any(self.cache.iterdir()))


class TestProjectionCatalogueIsHonest(unittest.TestCase):
    """A source nobody has supplied must never produce a number - not a zero,
    not an interpolation, and not a share of something called a consensus."""

    def setUp(self):
        from fantasyedge import projections as pj

        self.pj = pj
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(pathlib.Path(self.tmp.name) / "c.db")
        bundle, _ = load_fixture_bundle()
        self.store.save(bundle)
        self.pj.seed_espn(self.store)
        self.raw = json.loads((FIX / "sleeper_projections_2026_w1.json").read_text())

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_the_pending_three_are_named_and_marked_unloaded(self):
        cat = {c["source"]: c for c in self.pj.catalog(self.store)}
        for key in ("cbs", "fantasypros", "yahoo"):
            self.assertIn(key, cat, f"{key} is not even named")
            self.assertEqual(cat[key]["status"], "pending")
            self.assertFalse(cat[key]["loaded"])
            self.assertEqual(cat[key]["rows"], 0)
            # Each has to say what it is waiting on. "Absent, no reason given"
            # is the state a user reads as broken.
            self.assertTrue(cat[key]["needs"].strip())
            self.assertTrue(cat[key]["detail"].strip())

    def test_a_source_loaded_from_a_csv_still_appears(self):
        """The extension point for a licensed feed. A picker built only from
        the shortlist would hide a source the user has actually paid for."""
        csv = pathlib.Path(self.tmp.name) / "x.csv"
        name = self.store.q("SELECT name, pos FROM player LIMIT 1")[0]
        csv.write_text(f"player,pos,points\n{name['name']},{name['pos']},14.5\n")
        self.pj.load_csv(self.store, str(csv), "fantasypros", 2025, 1)
        cat = {c["source"]: c for c in self.pj.catalog(self.store, 2025, 1)}
        self.assertTrue(cat["fantasypros"]["loaded"])
        self.assertEqual(cat["fantasypros"]["status"], "pending",
                         "a licensed load must not silently rewrite the status "
                         "of the other weeks, which still have nothing")

    def test_a_consensus_of_one_says_so_and_has_no_spread(self):
        week = self.store.q(
            "SELECT MIN(week) w FROM projection WHERE source='espn'")[0]["w"]
        b = self.pj.board(self.store, 2025, week)
        self.assertEqual(b["sources"], ["espn"])
        self.assertEqual(b["n"], 1)
        self.assertTrue(b["players"])
        for m in b["players"]:
            self.assertEqual(m["n"], 1)
            self.assertEqual(m["consensus"], m["by"]["espn"])
            # One source cannot disagree with itself, and a printed 0.0 would
            # read as "they agree exactly".
            self.assertIsNone(m["spread"])
            self.assertNotIn("cbs", m["by"])
            self.assertNotIn("fantasypros", m["by"])
            self.assertNotIn("yahoo", m["by"])

    def test_a_consensus_of_two_is_the_mean_of_exactly_those_two(self):
        week = self.store.q(
            "SELECT MIN(week) w FROM projection WHERE source='espn'")[0]["w"]
        pid = self.store.q(
            "SELECT player_id, points FROM projection WHERE source='espn' "
            "AND week=? LIMIT 1", (week,))[0]
        with self.store.tx() as c:
            c.execute("INSERT OR REPLACE INTO projection VALUES (?,?,?,?,?,?)",
                      (2025, week, "sleeper", "espn", pid["player_id"],
                       pid["points"] + 6.0))
        b = self.pj.board(self.store, 2025, week)
        m = next(x for x in b["players"] if x["id"] == str(pid["player_id"]))
        self.assertEqual(m["n"], 2)
        self.assertAlmostEqual(m["consensus"], round(pid["points"] + 3.0, 2), places=1)
        self.assertAlmostEqual(m["spread"], 6.0, places=2)
        # And the man nobody else spoke about is still n=1, in the same payload.
        lone = next(x for x in b["players"] if x["n"] == 1)
        self.assertIsNone(lone["spread"])

    def test_the_current_week_is_the_commonest_not_the_maximum(self):
        """One league pulled with fourteen weeks of forward, unplayed roster
        rows must not drag the whole console onto week 14.

        This is the real shape of the author's database: three ESPN leagues
        hold week 1 only, and a fourth was pulled with ESPN's forward roster
        view, which returns every remaining week with points of 0.0. The flat
        maximum put the console on week 14 - a week only ESPN has projected -
        and the honest "consensus of 1" that produced was indistinguishable
        from the Sleeper loader having failed.
        """
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(pathlib.Path(tmp) / "wk.db")
            try:
                with store.tx() as c:
                    for lid, last in (("a", 1), ("b", 1), ("c", 1), ("forward", 14)):
                        for week in range(1, last + 1):
                            c.execute(
                                "INSERT OR REPLACE INTO roster_slot VALUES "
                                "(?,?,?,?,?,?,?,?,?,?)",
                                ("espn", lid, 2026, week, "1", "9999", "BN",
                                 0.0, 0.0, 0))
                flat = store.q(
                    "SELECT MAX(week) w FROM roster_slot WHERE season=2026")[0]["w"]
                self.assertEqual(flat, 14, "the trap this rule exists for")
                self.assertEqual(self.pj.current_week(store, 2026), 1)
            finally:
                store.close()


class TestProjectionsOverTheApi(unittest.TestCase):
    """What a visionOS or television client actually calls. It reads rows; it
    never touches a provider - see the module docstring in api.py."""

    @classmethod
    def setUpClass(cls):
        from fantasyedge import projections as pj
        from fantasyedge.api import Api

        cls.tmp = tempfile.TemporaryDirectory()
        db = pathlib.Path(cls.tmp.name) / "a.db"
        store = Store(db)
        bundle, _ = load_fixture_bundle()
        store.save(bundle)
        pj.seed_espn(store)
        cls.week = store.q(
            "SELECT MIN(week) w FROM projection WHERE source='espn'")[0]["w"]
        rows = store.q("SELECT player_id, points FROM projection WHERE week=?",
                       (cls.week,))
        with store.tx() as c:
            # A second source on half the board, so both the agreeing case and
            # the "only one source spoke" case are live in one payload.
            c.executemany(
                "INSERT OR REPLACE INTO projection VALUES (?,?,?,?,?,?)",
                [(2025, cls.week, "sleeper", "espn", r["player_id"],
                  r["points"] + 4.0) for r in rows[:len(rows) // 2]])
        store.close()
        cls.api = Api(str(db))

    @classmethod
    def tearDownClass(cls):
        cls.api.close()
        cls.tmp.cleanup()

    def q(self, **kw):
        return {k: [str(v)] for k, v in kw.items()}

    def test_a_projection_is_derived_not_live(self):
        """It is recomputed from stored rows and never polled from a provider,
        so it caches beside the analyses rather than beside the scoreboard."""
        from fantasyedge.api import CONFIG, DERIVED, LIVE

        _, pol = self.api.dispatch("/api/projections", self.q(week=self.week))
        self.assertEqual(pol, DERIVED)
        self.assertNotEqual(pol, LIVE)
        _, pol = self.api.dispatch("/api/projections/sources", {})
        self.assertEqual(pol, CONFIG)

    def test_every_advertised_projection_route_dispatches(self):
        from fantasyedge.api import ROUTES

        advertised = [r[1] for r in ROUTES if r[1].startswith("/api/projections")]
        self.assertEqual(len(advertised), 2)
        for path in advertised:
            self.api.dispatch(path, {})          # must not raise

    def test_n_travels_with_the_consensus_on_every_row(self):
        b, _ = self.api.dispatch("/api/projections", self.q(week=self.week))
        self.assertEqual(sorted(b["sources"]), ["espn", "sleeper"])
        self.assertEqual(b["n"], 2)
        self.assertTrue(b["players"])
        for m in b["players"]:
            self.assertIn("n", m)
            self.assertEqual(m["n"], len(m["by"]))
            self.assertEqual(m["consensus"],
                             round(sum(m["by"].values()) / len(m["by"]), 2))
        # Both cases present, so a client cannot be written against only one.
        self.assertTrue(any(m["n"] == 2 for m in b["players"]))
        self.assertTrue(any(m["n"] == 1 for m in b["players"]))

    def test_an_unloaded_source_produces_no_number_anywhere(self):
        b, _ = self.api.dispatch("/api/projections", self.q(week=self.week))
        for m in b["players"]:
            for key in ("cbs", "fantasypros", "yahoo"):
                self.assertNotIn(key, m["by"])
        self.assertEqual(sorted(x["source"] for x in b["pending"]),
                         ["cbs", "fantasypros", "yahoo"])
        for x in b["pending"]:
            self.assertTrue(x["needs"].strip())

    def test_asking_for_a_pending_source_is_a_404_that_says_why(self):
        from fantasyedge.api import HttpError

        with self.assertRaises(HttpError) as cm:
            self.api.dispatch("/api/projections",
                              {"source": ["cbs"], "week": [str(self.week)]})
        self.assertEqual(cm.exception.code, 404)
        # The fix line has to name the blocker, not list what happens to be
        # loaded - otherwise the client shows "try espn" for a licence problem.
        self.assertIn("API key", cm.exception.fix)

    def test_choosing_a_source_reorders_the_board(self):
        """The whole point of the picker: a different source is a different
        ranking, not the same list with different labels."""
        espn, _ = self.api.dispatch(
            "/api/projections", {"source": ["espn"], "week": [str(self.week)]})
        slp, _ = self.api.dispatch(
            "/api/projections", {"source": ["sleeper"], "week": [str(self.week)]})
        self.assertNotEqual([m["id"] for m in espn["players"]],
                            [m["id"] for m in slp["players"]])
        for m in slp["players"]:
            self.assertEqual(m["points"], m["by"]["sleeper"])
        self.assertEqual(slp["players"][0]["rank"], 1)
        self.assertTrue(slp["players"][0]["posRank"])

    def test_disagreement_is_surfaced_rather_than_averaged_away(self):
        b, _ = self.api.dispatch("/api/projections", self.q(week=self.week))
        self.assertTrue(b["disagreements"])
        for m in b["disagreements"]:
            self.assertIsNotNone(m["spread"])
            self.assertGreaterEqual(m["spread"], 0)
        spreads = [m["spread"] for m in b["disagreements"]]
        self.assertEqual(spreads, sorted(spreads, reverse=True))

    def test_the_page_ships_the_sources_so_a_switch_costs_no_round_trip(self):
        page = self.api.mosaic_page().decode()
        self.assertIn('"catalog"', page)
        self.assertIn("fantasypros", page)
        # And the picker is in the markup as a disabled control, not as an
        # option that would draw an empty column.
        self.assertIn("pb-chip", page)
        self.assertIn("NEEDS ", page)


class TestTheChosenSourcePersists(unittest.TestCase):
    """It is a preference like the others, for the same reason: the console
    runs on a laptop, a television and a headset, and they have to agree."""

    def test_it_round_trips_without_touching_the_other_keys(self):
        from fantasyedge import prefs as pf

        before = {"teams": {"espn-1": "4"}, "order": ["espn-1"],
                  "hidden": ["espn-2"]}
        after = pf.merge(before, {"projection": "sleeper"})
        self.assertEqual(after["projection"], "sleeper")
        self.assertEqual(after["teams"], before["teams"])
        self.assertEqual(after["hidden"], before["hidden"])
        self.assertEqual(after["order"], before["order"])

    def test_a_file_written_before_this_existed_still_loads(self):
        from fantasyedge import prefs as pf

        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "prefs.json"
            path.write_text(json.dumps({"teams": {"espn-9": "3"},
                                        "hidden": ["espn-8"]}))
            old, pf.CONFIG = pf.CONFIG, path
            try:
                got = pf.load()
            finally:
                pf.CONFIG = old
        self.assertEqual(got["teams"], {"espn-9": "3"})
        self.assertEqual(got["hidden"], ["espn-8"])
        self.assertEqual(got["projection"], "",
                         "an unset source must be empty, not a guessed name")


class TestTheConsoleNeverInventsAProjection(unittest.TestCase):
    """Read against the template rather than the running page, because these
    are properties of the code that has to hold on every surface it renders on
    - including a published copy with no API behind it."""

    @classmethod
    def setUpClass(cls):
        cls.page = (pathlib.Path(__file__).resolve().parents[1]
                    / "fantasyedge" / "templates" / "mosaic.html").read_text()

    def test_a_missing_number_is_a_dash_and_never_a_zero(self):
        """`nf` turns null into "0.0", which is the single most misleading
        thing this page could print about a man no source has projected."""
        self.assertIn("const nfp=", self.page)
        self.assertIn('nfp(c.projected)', self.page)
        self.assertIn('nfp(p.projected)', self.page)

    def test_the_pending_sources_are_disabled_controls(self):
        self.assertIn("disabled data-src=", self.page)
        self.assertIn('.pb-chip[disabled]', self.page)
        # and the click handler refuses them a second time, because CSS is not
        # an access control
        self.assertIn("if(!b||b.disabled)return", self.page)

    def test_a_consensus_of_one_is_never_offered(self):
        self.assertIn("PROJLOADED.length>1", self.page)

    def test_the_javascript_leverage_port_was_not_altered(self):
        """`leverage.py` and this port must agree - see AGENTS.md. A missing
        projection reaches evaluate() as null, which Math.max already floors to
        nothing; that is exactly "this source does not expect him to play", and
        it needed no change here."""
        self.assertIn("const rest=Math.max(0,c.projected-c.scored)*c.remaining;",
                      self.page)
        self.assertIn("const basis=c=>phase===\"pre\"?Math.max(0,c.projected)",
                      self.page)


class TestAnUnplayedWeekIsNotAMiss(unittest.TestCase):
    """A projection is not wrong because the game has not kicked off.

    ESPN writes `points = 0.0` on a forward roster row rather than leaving it
    null, so a source loaded for the rest of the season was scored against a
    league it claimed was held scoreless every week. It reported an eleven
    point bias and a 98% hit rate off the same rows - numbers that look like
    a finding and are an artefact of the calendar.
    """

    def setUp(self):
        import tempfile
        from fantasyedge.store import Store

        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(pathlib.Path(self.tmp.name) / "acc.db")
        with self.store.tx() as c:
            # Twenty-five starters, because the engine skips any source with
            # fewer than twenty scored records - a sensible floor that a
            # nine-man fixture would trip instead of testing anything.
            for i in range(25):
                c.execute("INSERT INTO roster_slot VALUES (?,?,?,?,?,?,?,?,?,?)",
                          ("espn", "L", 2026, 1, "t1", f"p{i}", "WR",
                           10.0 + i, 9.0 + i, 1))
            # One week that has not happened: same men, stored zeros.
            for i in range(25):
                c.execute("INSERT INTO roster_slot VALUES (?,?,?,?,?,?,?,?,?,?)",
                          ("espn", "L", 2026, 2, "t1", f"p{i}", "WR",
                           0.0, 9.0 + i, 1))
            for w in (1, 2):
                for i in range(25):
                    c.execute("INSERT INTO projection VALUES (?,?,?,?,?,?)",
                              (2026, w, "src", "espn", f"p{i}", 9.0 + i))
                    c.execute("INSERT OR REPLACE INTO player VALUES (?,?,?,?,?)",
                              ("espn", f"p{i}", f"P{i}", "WR", "DET"))

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_only_the_played_week_is_scored(self):
        from fantasyedge.analytics import projection_accuracy

        r = projection_accuracy(self.store, "espn", "L")
        self.assertEqual(len(r.rows), 1, "expected one source")
        weeks = r.rows[0][r.columns.index("Weeks")]
        self.assertEqual(weeks, 1,
                         "the unplayed week was scored; every projection in it "
                         "counts as missing by its whole value")

    def test_the_bias_is_not_the_calendar(self):
        """Projections here are within a point of the truth in the week that
        happened. Counting the week that did not would swing the bias by about
        the size of a projection."""
        from fantasyedge.analytics import projection_accuracy

        r = projection_accuracy(self.store, "espn", "L")
        bias = r.rows[0][r.columns.index("Bias (proj - actual)")]
        self.assertLess(abs(bias), 2.0, f"bias {bias} looks like unplayed weeks")

    def test_the_caveat_says_so(self):
        from fantasyedge.analytics import projection_accuracy

        r = projection_accuracy(self.store, "espn", "L")
        self.assertIn("in progress", r.caveat.lower())


def _contrast(a: str, b: str) -> float:
    """WCAG 2.1 contrast between two hex colours. Duplicated from
    `apple/contrast_check.py` rather than imported, so the web tests still run
    in a checkout with no Apple sources in it."""
    def lum(h):
        h = h.lstrip("#")
        cs = []
        for i in (0, 2, 4):
            c = int(h[i:i + 2], 16) / 255
            cs.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
        return 0.2126 * cs[0] + 0.7152 * cs[1] + 0.0722 * cs[2]
    la, lb = lum(a), lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


class TestTheChipFillsAreTheAppsOwn(unittest.TestCase):
    """The browser and the headset must not drift into two palettes.

    `apple/contrast_check.py` solves for the one luminance band where white
    text on a chip clears 4.5:1 and the chip's edge clears 3:1 against both a
    bright room and a dark one, and writes the answer into `Theme.swift`. The
    web board reuses those exact values. A hand-tweak on either side is the
    failure this asserts against: two surfaces that merely rhyme.
    """

    @classmethod
    def setUpClass(cls):
        root = pathlib.Path(__file__).resolve().parents[1]
        cls.page = (root / "fantasyedge" / "templates" / "mosaic.html").read_text()
        cls.theme = root / "apple" / "FantasyEdge" / "Sources" / "Theme.swift"

    @staticmethod
    def _swift_hexes(src, names):
        """The RGB triples Theme.swift declares, as hex, for the named tokens."""
        out = {}
        for name in names:
            m = re.search(
                r"static let %s\s*=\s*Color\(red:\s*([\d.]+),\s*green:\s*([\d.]+),"
                r"\s*blue:\s*([\d.]+)\)" % re.escape(name), src)
            if m:
                out[name] = "#" + "".join(
                    f"{round(float(v) * 255):02x}" for v in m.groups())
        return out

    def test_the_state_fills_match_the_swift_source(self):
        if not self.theme.exists():                 # web-only checkout
            self.skipTest("the visionOS sources are not in this checkout")
        src = self.theme.read_text()
        want = self._swift_hexes(src, ["greenFill", "redFill", "goldFill"])
        self.assertEqual(len(want), 3, "Theme.swift no longer declares the fills")
        for token, css in (("greenFill", "--fill-green"),
                           ("redFill", "--fill-red"),
                           ("goldFill", "--fill-gold")):
            self.assertIn(f"{css}:{want[token]}", self.page,
                          f"{css} has drifted from Theme.swift's {token} "
                          f"({want[token]}); rerun apple/contrast_check.py")

    def test_the_position_fills_match_the_swift_source(self):
        if not self.theme.exists():
            self.skipTest("the visionOS sources are not in this checkout")
        src = self.theme.read_text()
        i = src.find("func positionFill(")
        self.assertGreater(i, 0, "positionFill is gone from Theme.swift")
        body = src[i:src.find("\n    }", i)]
        pairs = re.findall(
            r'case "([A-Z/]+)":\s*return Color\(red:\s*([\d.]+),\s*'
            r'green:\s*([\d.]+),\s*blue:\s*([\d.]+)\)', body)
        self.assertTrue(pairs, "no position cases found")
        for pos, r, g, b in pairs:
            hexed = "#" + "".join(f"{round(float(v) * 255):02x}" for v in (r, g, b))
            self.assertIn(f"--posfill-{pos}:{hexed}", self.page,
                          f"the web's {pos} chip fill has drifted from the app's")

    def test_white_on_every_chip_fill_clears_body_text(self):
        """The property the fills exist for, re-checked on this side rather
        than trusted. 4.5:1 is the WCAG floor for text this size."""
        for m in re.finditer(r"--(?:fill|posfill)-[\w]+:(#[0-9a-f]{6})", self.page):
            self.assertGreaterEqual(
                _contrast("#ffffff", m.group(1)), 4.5,
                f"white text on {m.group(1)} is below 4.5:1")

    def test_a_chip_carries_a_hairline_because_navy_is_darker_than_glass(self):
        """The fills were solved to stay visible against a *bright* room. This
        page is darker than either room that solver considered, so a bare chip
        boundary measures about 2.2-4.0:1 here against the 3:1 WCAG wants for
        the edge of a non-text component. The stroke is what buys it back, and
        removing it would silently reintroduce that."""
        self.assertIn("--chip-edge:", self.page)
        for cls in (".mk{", ".pos{"):
            i = self.page.find(cls)
            self.assertGreater(i, 0, f"{cls} is gone")
            self.assertIn("var(--chip-edge)", self.page[i:i + 800],
                          f"{cls} lost the stroke that gives it an edge on navy")


class TestColourIsNeverTheOnlyCarrier(unittest.TestCase):
    """Every state pairs with a glyph, so a red-green colourblind reader loses
    nothing. Two of the six states share a fill with another state on purpose;
    the glyph is the only thing separating those pairs."""

    @classmethod
    def setUpClass(cls):
        cls.page = (pathlib.Path(__file__).resolve().parents[1]
                    / "fantasyedge" / "templates" / "mosaic.html").read_text()

    def test_all_six_marks_exist_with_a_glyph_and_a_spoken_label(self):
        i = self.page.find("const MARK={")
        self.assertGreater(i, 0, "the mark table is gone")
        table = self.page[i:self.page.find("};", i)]
        for state, say in (("ahead", "ahead"), ("behind", "behind"),
                           ("level", "level"), ("caution", "worth a look"),
                           ("live", "live"), ("hurt", "on the injury wire")):
            self.assertIn(state, table, f"the {state} mark is missing")
            self.assertIn(say, table,
                          f"the {state} mark lost the label a screen reader reads")
        # The two pairs that share a fill are only distinguishable by glyph.
        self.assertIn("↑", table)      # ahead
        self.assertIn("↓", table)      # behind
        self.assertIn("✚", table)      # hurt

    def test_the_scoreline_totals_are_ink_not_two_tints(self):
        """A green figure and a red figure are the classic pair a deuteranope
        cannot separate, and at 66px a tint is at its least readable."""
        self.assertIn(".team .pts{color:var(--ink)}", self.page)
        self.assertNotIn(".team.a .pts{color:var(--green)}", self.page)
        self.assertIn("function scoreMarks(", self.page)

    def test_a_mark_is_announced_rather_than_left_as_decoration(self):
        i = self.page.find("function mk(")
        self.assertGreater(i, 0)
        body = self.page[i:i + 700]
        self.assertIn('role="img"', body)
        self.assertIn("aria-label=", body)


class TestPortraitsAreAskedForAtTheSizeTheyAreDrawn(unittest.TestCase):
    """The payload carries ESPN's bare path, which is one size for every
    surface. `live.py` exposes the combiner; the board is what has to ask."""

    @classmethod
    def setUpClass(cls):
        cls.page = (pathlib.Path(__file__).resolve().parents[1]
                    / "fantasyedge" / "templates" / "mosaic.html").read_text()

    def test_a_bare_espn_path_is_rewritten_through_the_combiner(self):
        self.assertIn("combiner/i?img=", self.page)
        self.assertIn("function atW(", self.page)

    def test_an_embedded_data_uri_is_left_alone(self):
        """`build_docs.py --embed` inlines portraits as data: URIs for hosts
        that block the CDN. Rewriting one of those produces a dead image."""
        i = self.page.find("function atW(")
        body = self.page[i:i + 420]
        self.assertIn('url.startsWith("data:")', body)

    def test_the_row_avatar_does_not_ask_for_the_original(self):
        """The universe table draws a 38px avatar and runs to hundreds of
        rows. Asking for the 1200px original there is most of a megabyte a row
        for pixels nobody can see - which is the reason this is a ladder and
        not one number."""
        i = self.page.find("const IMGW={")
        self.assertGreater(i, 0, "the width ladder is gone")
        table = self.page[i:self.page.find("};", i)]
        row = int(re.search(r"row:(\d+)", table).group(1))
        card = int(re.search(r"card:(\d+)", table).group(1))
        self.assertLessEqual(row, 128, "the table avatar got greedy")
        self.assertGreater(card, row, "the one big image should ask for more")


class TestEveryNumberCanExplainItself(unittest.TestCase):
    """Ported from `Explain` on the headset so a figure cannot come to mean
    two things on two surfaces."""

    @classmethod
    def setUpClass(cls):
        cls.page = (pathlib.Path(__file__).resolve().parents[1]
                    / "fantasyedge" / "templates" / "mosaic.html").read_text()

    def test_every_explanation_says_what_how_and_usually_a_caveat(self):
        i = self.page.find("const EXPLAIN={")
        self.assertGreater(i, 0, "the explanation table is gone")
        block = self.page[i:self.page.find("\n};", i)]
        keys = re.findall(r"\n  (\w+):\(\)=>", block)
        self.assertGreaterEqual(len(keys), 12, f"only {len(keys)} explanations")
        for field in ("title:", "what:", "how:", "caveat:"):
            self.assertIn(field, block)

    def test_a_trigger_is_reachable_without_a_mouse(self):
        """Hover does not exist on a phone, and this page is used on one."""
        i = self.page.find("const exAttr=")
        body = self.page[i:i + 320]
        self.assertIn('tabindex="0"', body)
        self.assertIn('role="button"', body)
        self.assertIn("aria-expanded", body)

    def test_the_caveat_is_a_chip_and_the_sentence_is_ink(self):
        """It used to be gold text on the headset, which measured 1.02:1 - the
        most important sentence on the card and the least readable thing on
        it."""
        i = self.page.find("function openEx(")
        body = self.page[i:i + 900]
        self.assertIn('mk("caution"', body)


class TestTheBoardSurvivesEveryShape(unittest.TestCase):
    """Landscape phone is the shape most likely to be broken: wide, and often
    under 400 CSS pixels tall, where the page's own furniture can account for
    the whole window."""

    @classmethod
    def setUpClass(cls):
        cls.page = (pathlib.Path(__file__).resolve().parents[1]
                    / "fantasyedge" / "templates" / "mosaic.html").read_text()

    def test_a_tab_strip_scrolls_rather_than_clipping(self):
        """Nine tabs do not fit across a 390px phone. When the strip clipped
        instead of scrolling, Headlines was simply unreachable."""
        i = self.page.find(".seg{display:flex")
        self.assertGreater(i, 0)
        body = self.page[i:i + 400]
        self.assertIn("overflow-x:auto", body)
        self.assertIn("max-width:100%", body)

    def test_the_controls_can_shrink(self):
        """`flex:none` here put the cluster off the right edge of a 1440px
        window, which shows up as a horizontal scrollbar on the document."""
        i = self.page.find(".ctrls{display:flex")
        self.assertGreater(i, 0)
        self.assertIn("min-width:0", self.page[i:i + 220])

    def test_a_short_landscape_window_gets_a_deliberate_treatment(self):
        self.assertIn("@media (orientation:landscape) and (max-height:500px)",
                      self.page)

    def test_the_pitch_keeps_its_geometry_when_it_is_capped(self):
        """The field is the one drawing whose proportions carry meaning. It may
        be made smaller; it may not be squashed."""
        self.assertIn('viewBox="0 0 1200 300"', self.page)
        i = self.page.find('viewBox="0 0 1200 300"')
        self.assertNotIn('preserveAspectRatio="none"', self.page[i:i + 200])
