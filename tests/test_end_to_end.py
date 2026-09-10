"""End-to-end tests. No network: the ESPN adapter is exercised against a
recorded fixture through a stub Http, which is the whole reason Http is
injected rather than imported at call sites."""

from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from fantasyedge import analytics, report                    # noqa: E402
from fantasyedge.providers.base import Http, get_provider     # noqa: E402
from fantasyedge.providers.espn import EspnProvider           # noqa: E402
from fantasyedge.providers.sleeper import SleeperProvider, normalise  # noqa: E402
from fantasyedge.providers.manual import ManualProvider       # noqa: E402
from fantasyedge.store import Store                           # noqa: E402

FIX = pathlib.Path(__file__).parent / "fixtures"


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
        """`GET /api` is the client's discovery document; it must not lie."""
        for _, template, _ in self.api.index()["routes"]:
            path = (template.replace("{provider}", "espn").replace("{id}", "99")
                            .replace("{key}", "luck"))
            self.assertIsNotNone(self.api.dispatch(path, {}), path)

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

        from fantasyedge.api import make_handler

        srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.api))
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
            with self.assertRaises(urllib.error.HTTPError) as cm:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/api/leagues/espn/404")
            self.assertEqual(cm.exception.code, 404)
            self.assertIn("fix", json.loads(cm.exception.read()))
        finally:
            srv.shutdown()
            srv.server_close()


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
