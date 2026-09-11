"""Intel: the strict-compute engine and the bring-your-own-key model client.

No network and no real keys. The AI providers are exercised against a local
`http.server` speaking each one's response shape, which is the only way to test
a 401, a 429 and a malformed body without either mocking away the transport
being tested or holding a credential in the repository.

The strict-compute half runs against the same recorded ESPN fixture the
analytics tests use, so every insight it produces can be checked by hand
against rows that are also on disk.
"""

from __future__ import annotations

import contextlib
import io
import json
import logging
import os
import pathlib
import re
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from fantasyedge import ai, analytics, injuries, intel, leverage   # noqa: E402
from fantasyedge.providers.base import Http                        # noqa: E402
from fantasyedge.providers.espn import EspnProvider                # noqa: E402
from fantasyedge.store import Store                                # noqa: E402

FIX = pathlib.Path(__file__).parent / "fixtures"

# Never a real key. Long enough that `redact` treats it as a secret, and shaped
# like one so the shape-based second pass is exercised too.
FAKE_KEY = "sk-test-000000000000000000000000deadbeef"


# ───────────────────────────── fixture plumbing ──────────────────────────────

class _StubHttp(Http):
    def __init__(self, payload):
        super().__init__()
        self.payload = payload

    def get_json(self, url, *, headers=None, cookies=None, params=None):
        if url.endswith("/ffl"):
            return {"currentSeasonId": 2026}
        return self.payload


def fixture_store(tmp: str) -> Store:
    payload = json.loads((FIX / "espn_2025.json").read_text())
    provider = EspnProvider(espn_s2="x", swid="{y}", league_id="99",
                            http=_StubHttp(payload))
    store = Store(pathlib.Path(tmp) / "intel.db")
    store.save(provider.fetch_season("99", 2025))
    return store


def mosaic_league(store: Store, team_id: str, week: int = 1, *,
                  league_id: str = "espn-99", name: str = "Fixture League",
                  season: int = 2025) -> dict:
    """One league in the shape `/api/mosaic` emits.

    Rebuilt here rather than imported from `api.py` on purpose: `intel.build`
    is specified against the *payload*, not against the method that happens to
    produce it today, and a test that reaches into the API would stop testing
    that contract the moment the API grew a credential or a cache.
    """
    from fantasyedge import live as livemod

    rows = livemod.roster_players(store, "espn", "99", season, week)
    names = {m["team_id"]: m["name"] for m in store.q(
        "SELECT team_id, name FROM manager WHERE provider='espn' "
        "AND league_id='99' AND season=?", (season,))}
    opp = next((r["opponent_id"] for r in store.q(
        "SELECT opponent_id FROM matchup WHERE provider='espn' AND league_id='99' "
        "AND season=? AND week=? AND team_id=?", (season, week, team_id))), None)

    def side(tid):
        return [{"id": str(r["player_id"]), "name": r["name"], "pos": r["pos"],
                 "team": r["team"], "slot": r["slot"],
                 "projected": round(float(r["projected"] or 0.0), 1)}
                for r in rows if r["team_id"] == tid and r["started"]]

    return {"id": league_id, "provider": "espn", "leagueId": "99",
            "league": name, "season": season, "week": week,
            "you": {"teamId": team_id, "name": names.get(team_id, team_id),
                    "starters": side(team_id)},
            "opp": {"teamId": opp, "name": names.get(opp, opp),
                    "starters": side(opp)},
            "roster": [], "priors": {}, "matchups": {}, "teams": []}


def snapshot(league: dict, *, you_played: float, opp_played: float,
             hero: str | None = None, hero_points: float = 0.0) -> dict:
    """A live snapshot for one league, made by hand so the maths is checkable.

    `you_played`/`opp_played` are the fraction of each side's games already
    gone, and every starter scores their projection times that fraction unless
    they are the hero, who is given an exact number.
    """
    players = {}
    for sidename, played in (("you", you_played), ("opp", opp_played)):
        for p in league[sidename]["starters"]:
            pts = (hero_points if str(p["id"]) == str(hero)
                   else round(p["projected"] * played, 2))
            players[str(p["id"])] = {
                "s": pts, "r": round(1.0 - played, 3),
                "g": "final" if played >= 1.0 else ("pre" if played <= 0 else "Q3")}
    return {"asOf": 120.0, "window": "late", "games": {},
            "players": players, "version": "test"}


def hand_league(you: list[tuple], opp: list[tuple], *, league_id: str = "espn-H",
                name: str = "Hand League") -> dict:
    """A matchup with numbers chosen rather than found.

    The fixture is the right thing to test the database-shaped generators
    against, but a fragile lead is a statement about a specific margin and a
    specific amount of football left, and pinning that to whatever the recorded
    season happens to contain makes the test assert a coincidence. These
    line-ups are small and the arithmetic in the assertions is done by hand.
    Each entry is (id, name, pos, projected).
    """
    def side(rows):
        return [{"id": i, "name": n, "pos": p, "team": "SF", "slot": p,
                 "projected": float(proj)} for i, n, p, proj in rows]

    return {"id": league_id, "provider": "espn", "leagueId": "H",
            "league": name, "season": 2025, "week": 3,
            "you": {"teamId": "1", "name": "You", "starters": side(you)},
            "opp": {"teamId": "2", "name": "Them", "starters": side(opp)},
            "roster": [], "priors": {}, "matchups": {}, "teams": []}


def hand_snapshot(scores: dict[str, tuple]) -> dict:
    """`{player id: (scored, fraction remaining, state)}`, exactly."""
    return {"asOf": 120.0, "window": "late", "games": {},
            "players": {k: {"s": s, "r": r, "g": g}
                        for k, (s, r, g) in scores.items()},
            "version": "test"}


# ───────────────────────────── strict compute ────────────────────────────────

class TestStrictMode(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.store = fixture_store(cls.tmp.name)
        cls.league = mosaic_league(cls.store, "1")
        cls.analyses = [
            {"key": r.key, "title": r.title, "headline": r.headline,
             "columns": r.columns, "rows": r.rows, "caveat": r.caveat,
             "empty": r.empty}
            for r in analytics.run_all(cls.store, "espn", "99")]

    @classmethod
    def tearDownClass(cls):
        cls.store.close()
        cls.tmp.cleanup()

    # --- the invariants that make an insight worth showing at all ---

    def _all_insights(self) -> list[intel.Insight]:
        live = snapshot(self.league, you_played=0.8, opp_played=0.4)
        brief = intel.build(mosaics={"leagues": [self.league]}, live=live,
                            injuries=self._injuries(),
                            analyses={"espn-99": self.analyses},
                            opportunity=_fake_opportunity, limit=50)
        return brief.insights

    def _injuries(self):
        name = self.league["you"]["starters"][0]["name"]
        return injuries.detect(self.store, [
            {"player": name, "headline": f"{name} ruled out with a knee injury",
             "detail": "He will miss the game.", "url": "", "published": ""}],
            season=2025)

    def test_produces_insights_from_the_fixture(self):
        got = self._all_insights()
        self.assertTrue(got, "strict mode produced nothing from the fixture")
        kinds = {i.kind for i in got}
        self.assertIn("history", kinds)
        self.assertIn("injury", kinds)
        self.assertIn("opportunity", kinds)

    def test_every_insight_carries_a_caveat(self):
        for i in self._all_insights():
            self.assertTrue(i.caveat.strip(), f"{i.key} has an empty caveat")

    def test_every_insight_carries_its_provenance(self):
        for i in self._all_insights():
            self.assertTrue(i.facts, f"{i.key} carries no facts")
            self.assertTrue(i.sources, f"{i.key} names no source")
            for f in i.facts:
                self.assertTrue(f.source, f"{i.key}/{f.label} has no source")

    def test_every_insight_is_labelled_computed(self):
        for i in self._all_insights():
            self.assertEqual(i.origin, "computed")
            self.assertEqual(i.as_dict()["origin"], "computed")

    def test_origin_cannot_be_forged(self):
        i = self._all_insights()[0]
        with self.assertRaises(AttributeError):
            i.origin = "model"                                # type: ignore[misc]

    def test_an_insight_without_a_caveat_will_not_construct(self):
        with self.assertRaises(ValueError):
            intel.Insight(key="k", kind="x", title="t", detail="d", caveat="",
                          facts=[intel.Fact("a", 1, "", "table")])

    def test_an_insight_without_facts_will_not_construct(self):
        with self.assertRaises(ValueError):
            intel.Insight(key="k", kind="x", title="t", detail="d",
                          caveat="c", facts=[])

    def test_a_fact_without_a_source_will_not_construct(self):
        with self.assertRaises(ValueError):
            intel.Fact("targets", 12)

    def test_never_names_a_metric_we_cannot_source(self):
        for i in self._all_insights():
            for text in (i.title, i.detail, i.caveat):
                self.assertEqual(intel.mentions_unavailable(text), [],
                                 f"{i.key} referred to an unsourceable metric")

    # --- the individual generators, against numbers that can be checked ---

    def test_carrying_names_the_top_scorer_and_the_share_adds_up(self):
        hero = self.league["you"]["starters"][0]
        live = snapshot(self.league, you_played=1.0, opp_played=1.0,
                        hero=hero["id"], hero_points=90.0)
        got = {i.kind: i for i in intel.matchup_insights(self.league, live)}
        self.assertIn("carrying", got)
        c = got["carrying"]
        self.assertIn(hero["name"], c.title)
        facts = {f.label: f.value for f in c.facts}
        self.assertEqual(facts[f"{hero['name']} scored"], 90.0)
        total = facts["Your line-up scored"]
        self.assertAlmostEqual(facts["Share"], round(100 * 90.0 / total, 1),
                               places=1)

    def test_a_fragile_lead_is_reported_only_while_it_is_fragile(self):
        # 80 on the board against 75 still to be played by three receivers:
        # five points ahead with roughly twelve points of spread against you.
        league = hand_league(
            [("y1", "Yours One", "WR", 30.0), ("y2", "Yours Two", "WR", 30.0),
             ("y3", "Yours Three", "WR", 20.0)],
            [("o1", "Theirs One", "WR", 25.0), ("o2", "Theirs Two", "WR", 25.0),
             ("o3", "Theirs Three", "WR", 25.0)])
        live = hand_snapshot({"y1": (30.0, 0.0, "final"),
                              "y2": (30.0, 0.0, "final"),
                              "y3": (20.0, 0.0, "final"),
                              "o1": (0.0, 1.0, "pre"), "o2": (0.0, 1.0, "pre"),
                              "o3": (0.0, 1.0, "pre")})
        got = {i.kind: i for i in intel.matchup_insights(league, live)}
        self.assertIn("fragility", got)
        facts = {f.label: f.value for f in got["fragility"].facts}
        self.assertEqual(facts["Expected margin"], 5.0)
        self.assertEqual(facts["Their starters yet to play"], 3)

        # The same lead once their afternoon is over is not fragile, and is not
        # reported. That is the case a naive "you are ahead" rule gets wrong.
        done = hand_snapshot({"y1": (30.0, 0.0, "final"),
                              "y2": (30.0, 0.0, "final"),
                              "y3": (20.0, 0.0, "final"),
                              "o1": (25.0, 0.0, "final"),
                              "o2": (25.0, 0.0, "final"),
                              "o3": (25.0, 0.0, "final")})
        self.assertNotIn("fragility",
                         {i.kind for i in intel.matchup_insights(league, done)})

    def test_fragility_matches_the_leverage_model_it_cites(self):
        league = hand_league(
            [("y1", "Yours One", "WR", 30.0), ("y2", "Yours Two", "WR", 30.0),
             ("y3", "Yours Three", "WR", 20.0)],
            [("o1", "Theirs One", "WR", 25.0), ("o2", "Theirs Two", "WR", 25.0),
             ("o3", "Theirs Three", "WR", 25.0)])
        live = hand_snapshot({"y1": (30.0, 0.0, "final"),
                              "y2": (30.0, 0.0, "final"),
                              "y3": (20.0, 0.0, "final"),
                              "o1": (0.0, 1.0, "pre"), "o2": (0.0, 1.0, "pre"),
                              "o3": (0.0, 1.0, "pre")})
        m = leverage.evaluate(intel.cells_for(league, live))
        got = next(i for i in intel.matchup_insights(league, live)
                   if i.kind == "fragility")
        facts = {f.label: f.value for f in got.facts}
        self.assertEqual(facts["Win probability"], round(100 * m.win_prob))
        self.assertEqual(facts["Expected margin"], round(m.margin, 1))
        self.assertLess(m.win_prob, 0.85)

    def test_the_last_man_playing_is_named_as_the_decider(self):
        """Falls out of the leverage model rather than a fourth-quarter rule."""
        league = hand_league(
            [("y1", "Yours One", "WR", 20.0), ("y2", "Yours Two", "WR", 20.0)],
            [("o1", "Theirs One", "WR", 20.0), ("o2", "Late Man", "WR", 38.0)])
        live = hand_snapshot({"y1": (20.0, 0.0, "final"),
                              "y2": (20.0, 0.0, "final"),
                              "o1": (0.0, 0.0, "final"),
                              "o2": (0.0, 1.0, "Q1")})
        got = {i.kind: i for i in intel.matchup_insights(league, live)}
        self.assertIn("decider", got)
        self.assertIn("Late Man", got["decider"].title)

    def test_before_kickoff_it_says_so_rather_than_inventing_a_read(self):
        got = intel.matchup_insights(self.league, None)
        kinds = {i.kind for i in got}
        self.assertEqual(kinds, {"pregame"})
        self.assertIn("uncertainty", got[0].caveat)

    def test_history_carries_the_analysis_caveat_verbatim(self):
        source = {a["key"]: a for a in self.analyses}
        got = intel.history_insights(self.analyses, you="Team 1",
                                     league="Fixture League",
                                     league_id="espn-99")
        self.assertTrue(got)
        for i in got:
            key = i.key.split(":")[1]
            self.assertEqual(i.caveat, source[key]["caveat"],
                             "the caveat was paraphrased instead of carried")

    def test_history_narrows_to_your_own_row(self):
        got = {i.key.split(":")[1]: i
               for i in intel.history_insights(self.analyses, you="Team 1",
                                               league_id="espn-99")}
        bench = got["bench"]
        facts = {f.label: f.value for f in bench.facts}
        self.assertEqual(facts["Owner"], "Team 1")

    def test_cross_league_conflict_is_found_and_priced(self):
        a = mosaic_league(self.store, "1", league_id="espn-A", name="League A")
        b = mosaic_league(self.store, "1", league_id="espn-B", name="League B")
        # In league B the same man you start is on the other side of the table.
        b["opp"]["starters"] = list(a["you"]["starters"])
        got = [i for i in intel.cross_league_insights([a, b])
               if i.kind == "conflict"]
        self.assertTrue(got)
        one = got[0]
        facts = {f.label: f.value for f in one.facts}
        self.assertEqual(facts["Starting for you in"], 2)
        self.assertEqual(facts["Starting against you in"], 1)
        self.assertIn("League A", one.detail)
        self.assertIn("League B", one.detail)

    def test_exposure_needs_three_leagues_not_two(self):
        a = mosaic_league(self.store, "1", league_id="espn-A", name="A")
        b = mosaic_league(self.store, "1", league_id="espn-B", name="B")
        two = {i.kind for i in intel.cross_league_insights([a, b])}
        self.assertNotIn("exposure", two)
        c = mosaic_league(self.store, "1", league_id="espn-C", name="C")
        three = [i for i in intel.cross_league_insights([a, b, c])
                 if i.kind == "exposure"]
        self.assertTrue(three)
        self.assertEqual({f.label: f.value
                          for f in three[0].facts}["Line-ups"], 3)

    def test_injury_insight_keeps_the_database_facts_with_the_roast(self):
        hurt = self._injuries()
        self.assertTrue(hurt, "the fixture produced no injury to build on")
        got = intel.injury_insights(hurt)
        self.assertTrue(got)
        one = got[0]
        labels = {f.label for f in one.facts}
        self.assertIn("Line-ups he starts in", labels)
        self.assertIn("Projected this week", labels)
        self.assertIn("classified", one.caveat)
        self.assertIn(hurt[0]["roast"], one.detail)

    def test_opportunity_reports_only_metrics_nflverse_publishes(self):
        allowed = {a["label"] for a in intel.AVAILABLE_OPPORTUNITY}
        # "Games" and "Season" are the denominator and the release these are
        # measured over, not claims about a metric nflverse does not publish.
        allowed |= {"Games", "Season", "Fantasy points a game"}
        got = intel.opportunity_insights(
            self.league["you"]["starters"], _fake_opportunity, 2025)
        self.assertTrue(got, "the injected profile produced no insight")
        for i in got:
            for f in i.facts:
                self.assertIn(f.label, allowed,
                              f"{f.label} is not a metric we can source")

    def test_opportunity_names_the_season_the_numbers_came_from(self):
        """The caveat promises "the season named in the facts", and in week one
        of a new year the caller falls back to last season's release. A Season
        fact reporting the request rather than the data would be a wrong
        number with a source attached."""
        def supplier(pid, _season=None):
            o = _fake_opportunity(pid, 2025)
            return dict(o, season=2025) if o else o

        got = intel.opportunity_insights(
            self.league["you"]["starters"], supplier, 2026)
        self.assertTrue(got, "the injected profile produced no insight")
        for i in got:
            seasons = [f.value for f in i.facts if f.label == "Season"]
            self.assertEqual(seasons, [2025],
                             "the fact must name the release, not the request")

    def test_opportunity_is_silent_when_nflverse_is_unreachable(self):
        def boom(_pid, _season=None):
            raise OSError("nflverse is down")

        got = intel.opportunity_insights(
            self.league["you"]["starters"], boom, 2025)
        self.assertEqual(got, [])

    def test_opportunity_ignores_a_player_with_no_profile(self):
        got = intel.opportunity_insights(
            self.league["you"]["starters"], lambda _p, _s=None: {}, 2025)
        self.assertEqual(got, [])

    # --- the brief itself ---

    def test_brief_states_what_it_cannot_source(self):
        brief = intel.build(mosaics={"leagues": [self.league]})
        named = {u["metric"] for u in brief.as_dict()["unavailable"]}
        self.assertIn("Yards Per Route Run", named)
        self.assertIn("Route Participation", named)
        for u in brief.as_dict()["unavailable"]:
            self.assertTrue(u["reason"].strip())

    def test_brief_with_no_leagues_is_empty_and_explains_itself(self):
        brief = intel.build(mosaics={"leagues": []})
        self.assertEqual(brief.insights, [])
        self.assertTrue(brief.notes)

    def test_brief_separates_computed_from_model_in_the_payload(self):
        d = intel.build(mosaics={"leagues": [self.league]}).as_dict()
        self.assertIn("insights", d)
        self.assertIn("narration", d)
        self.assertIsNone(d["narration"])
        self.assertEqual(d["counts"]["model"], 0)
        self.assertTrue(all(i["origin"] == "computed" for i in d["insights"]))

    def test_brief_is_json_serialisable(self):
        d = intel.build(mosaics={"leagues": [self.league]},
                        live=snapshot(self.league, you_played=0.5,
                                      opp_played=0.5)).as_dict()
        json.dumps(d)                          # must not raise

    def test_prompt_facts_carry_no_identifiers(self):
        brief = intel.build(mosaics={"leagues": [self.league]},
                            live=snapshot(self.league, you_played=0.6,
                                          opp_played=0.3), limit=50)
        blob = json.dumps(intel.as_prompt_facts(brief))
        for pid in [p["id"] for p in self.league["you"]["starters"]]:
            self.assertNotIn(f'"{pid}"', blob)
        for entry in intel.as_prompt_facts(brief):
            self.assertTrue(entry["caveat"], "a finding reached the model "
                                             "without its caveat")


def _fake_opportunity(_player_id, _season=None) -> dict:
    """A stand-in for `profile.opportunity`, which fetches nflverse over HTTPS.

    Injected rather than patched so the test says out loud that this engine
    does no I/O of its own. The shape is exactly what `advanced.season_profiles`
    emits, minus the metrics that release does not carry.
    """
    return {"games": 8, "targets": 76, "carries": 4, "targetShare": 27.5,
            "airYardsShare": 33.1, "wopr": 0.61, "adot": 9.4, "yac": 4.8,
            "ppg": 9.9}


# ────────────────────────────── the AI stub ──────────────────────────────────

class _Provider(BaseHTTPRequestHandler):
    """A local server that answers in each provider's real response shape.

    `mode` is set by the test on the server object, which is how one handler
    covers success, a rejected key, a rate limit and a body that is not JSON.
    """

    protocol_version = "HTTP/1.1"

    def log_message(self, *_args):            # keep the suite quiet
        pass

    def do_POST(self):                        # noqa: N802 - BaseHTTPRequestHandler
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n).decode("utf-8") if n else ""
        srv = self.server
        # Lower-cased keys: urllib title-cases what it sends, so a lookup for
        # "x-goog-api-key" would miss the header that is plainly there.
        srv.calls.append({"path": self.path, "body": body,
                          "headers": {k.lower(): v
                                      for k, v in self.headers.items()}})
        mode = srv.mode

        if mode == "401":
            # Deliberately echoes the key back, which some providers really do.
            # Nothing downstream may let that reach a message a person sees.
            return self._send(401, json.dumps(
                {"error": {"message": f"Incorrect API key provided: "
                                      f"{self.headers.get('x-api-key') or FAKE_KEY}"}}))
        if mode == "429":
            return self._send(429, json.dumps(
                {"error": {"message": "rate limit exceeded"}}))
        if mode == "500":
            return self._send(500, json.dumps({"error": "boom"}))
        if mode == "malformed":
            return self._send(200, "<html>captive portal</html>")
        if mode == "empty":
            return self._send(200, json.dumps({}))

        text = srv.reply
        if "/v1/chat/completions" in self.path:
            out = {"choices": [{"message": {"role": "assistant",
                                            "content": text}}]}
        elif "/v1/messages" in self.path:
            out = {"content": [{"type": "text", "text": text}]}
        elif "generateContent" in self.path:
            out = {"candidates": [{"content": {"parts": [{"text": text}]}}]}
        else:
            return self._send(404, json.dumps({"error": "no such path"}))
        return self._send(200, json.dumps(out))

    def _send(self, code: int, body: str) -> None:
        raw = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


class _Harness:
    """Server plus the base URL to point a client at."""

    def __init__(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _Provider)
        self.server.mode = "ok"
        self.server.reply = "Steady week."
        self.server.calls = []
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       daemon=True)
        self.thread.start()

    @property
    def base(self) -> str:
        host, port = self.server.server_address[:2]
        return f"http://{host}:{port}"

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


def tiny_brief() -> intel.Brief:
    """A one-finding brief with numbers a narration can be checked against."""
    return intel.Brief(season=2025, week=3, insights=[intel.Insight(
        key="carry:espn-99", kind="carrying", title="Somebody is carrying",
        detail="He has 31.4 of your 88.2 points, 36% of the line-up.",
        caveat="Share of points already scored, not of the final total.",
        facts=[intel.Fact("Scored", 31.4, "pts", "roster_slot"),
               intel.Fact("Line-up scored", 88.2, "pts", "roster_slot")],
        league="Fixture League", league_id="espn-99", weight=0.6)])


class TestModelTransport(unittest.TestCase):
    """The three cloud providers, against a stub that speaks their shapes."""

    @classmethod
    def setUpClass(cls):
        cls.h = _Harness()

    @classmethod
    def tearDownClass(cls):
        cls.h.stop()

    def setUp(self):
        self.h.server.mode = "ok"
        self.h.server.reply = "Steady week."
        self.h.server.calls.clear()
        # No provider key may be visible to these tests: a developer with a
        # real one in their shell must not have it picked up and sent anywhere.
        self._saved = {k: os.environ.pop(k, None) for k in (
            "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY",
            "GEMINI_API_KEY", "FANTASYEDGE_AI_MODEL")}

    def tearDown(self):
        for k, v in self._saved.items():
            if v is not None:
                os.environ[k] = v
            else:
                os.environ.pop(k, None)

    def _client(self, provider: str, key: str = FAKE_KEY) -> ai.Client:
        return ai.client_for(provider, key=key, model="test-model",
                             base=self.h.base)

    # --- a successful call, per provider ---

    def test_openai_success(self):
        got = self._client("openai").complete("sys", "user")
        self.assertEqual(got, "Steady week.")
        call = self.h.server.calls[-1]
        self.assertIn("/v1/chat/completions", call["path"])
        self.assertEqual(call["headers"]["authorization"], f"Bearer {FAKE_KEY}")

    def test_anthropic_success(self):
        got = self._client("anthropic").complete("sys", "user")
        self.assertEqual(got, "Steady week.")
        call = self.h.server.calls[-1]
        self.assertIn("/v1/messages", call["path"])
        self.assertEqual(call["headers"]["x-api-key"], FAKE_KEY)
        self.assertEqual(call["headers"]["anthropic-version"],
                         ai.ANTHROPIC_VERSION)

    def test_google_success(self):
        got = self._client("google").complete("sys", "user")
        self.assertEqual(got, "Steady week.")
        call = self.h.server.calls[-1]
        self.assertIn("generateContent", call["path"])
        self.assertEqual(call["headers"]["x-goog-api-key"], FAKE_KEY)

    def test_google_never_puts_the_key_in_the_url(self):
        """A key in the query string is a key in every traceback and log."""
        self.h.server.mode = "429"
        with self.assertRaises(ai.ModelError):
            self._client("google").complete("sys", "user")
        self.assertNotIn(FAKE_KEY, self.h.server.calls[-1]["path"])
        self.assertNotIn("key=", self.h.server.calls[-1]["path"])

    def test_the_key_is_never_in_the_request_body(self):
        for provider in ("openai", "anthropic", "google"):
            self._client(provider).complete("sys", "user")
            self.assertNotIn(FAKE_KEY, self.h.server.calls[-1]["body"],
                             f"{provider} put the key in the payload")

    # --- the four failure states, as states rather than stack traces ---

    def test_missing_key_never_reaches_the_network(self):
        for provider in ("openai", "anthropic", "google"):
            with self.subTest(provider=provider):
                with self.assertRaises(ai.ModelError) as cm:
                    ai.client_for(provider, key="", base=self.h.base).complete(
                        "sys", "user")
                self.assertEqual(cm.exception.state, "no_key")
                self.assertTrue(cm.exception.remedy)
        self.assertEqual(self.h.server.calls, [],
                         "a keyless client still made a request")

    def test_rejected_key(self):
        self.h.server.mode = "401"
        for provider in ("openai", "anthropic", "google"):
            with self.subTest(provider=provider):
                with self.assertRaises(ai.ModelError) as cm:
                    self._client(provider).complete("sys", "user")
                self.assertEqual(cm.exception.state, "rejected")
                self.assertNotIn(FAKE_KEY, str(cm.exception))

    def test_rate_limit(self):
        self.h.server.mode = "429"
        with self.assertRaises(ai.ModelError) as cm:
            self._client("openai").complete("sys", "user")
        self.assertEqual(cm.exception.state, "rate_limited")
        self.assertIn("Wait", cm.exception.remedy)

    def test_a_rate_limit_is_not_retried(self):
        """Retrying a 429 immediately is how a rate limit becomes a ban."""
        self.h.server.mode = "429"
        with self.assertRaises(ai.ModelError):
            self._client("anthropic").complete("sys", "user")
        self.assertEqual(len(self.h.server.calls), 1)

    def test_malformed_body(self):
        self.h.server.mode = "malformed"
        for provider in ("openai", "anthropic", "google"):
            with self.subTest(provider=provider):
                with self.assertRaises(ai.ModelError) as cm:
                    self._client(provider).complete("sys", "user")
                self.assertEqual(cm.exception.state, "malformed")

    def test_well_formed_json_with_nothing_in_it(self):
        self.h.server.mode = "empty"
        for provider in ("openai", "anthropic", "google"):
            with self.subTest(provider=provider):
                with self.assertRaises(ai.ModelError) as cm:
                    self._client(provider).complete("sys", "user")
                self.assertEqual(cm.exception.state, "malformed")

    def test_server_error(self):
        self.h.server.mode = "500"
        with self.assertRaises(ai.ModelError) as cm:
            self._client("openai").complete("sys", "user")
        self.assertEqual(cm.exception.state, "unavailable")

    def test_unreachable_provider(self):
        client = ai.client_for("openai", key=FAKE_KEY,
                               base="http://127.0.0.1:1")
        with self.assertRaises(ai.ModelError) as cm:
            client.complete("sys", "user")
        self.assertEqual(cm.exception.state, "unreachable")

    def test_unknown_provider(self):
        with self.assertRaises(ai.ModelError) as cm:
            ai.client_for("hal9000")
        self.assertEqual(cm.exception.state, "unknown_provider")

    # --- the key must not leak, anywhere ---

    def test_no_key_in_any_exception_log_line_or_payload(self):
        """The provider echoes the key back in its 401 body. Nothing may carry it out."""
        self.h.server.mode = "401"
        out, err = io.StringIO(), io.StringIO()
        log = io.StringIO()
        handler = logging.StreamHandler(log)
        logging.getLogger().addHandler(handler)
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                note = ai.narrate(tiny_brief(), self._client("anthropic"))
        finally:
            logging.getLogger().removeHandler(handler)

        payload = json.dumps(note.as_dict())
        for where, text in (("payload", payload), ("stdout", out.getvalue()),
                            ("stderr", err.getvalue()), ("log", log.getvalue()),
                            ("error message", note.error["message"]),
                            ("remedy", note.error["remedy"])):
            self.assertNotIn(FAKE_KEY, text, f"the key leaked into the {where}")
        self.assertIn("[redacted]", note.error["message"])

    def test_redact_scrubs_a_key_in_a_url_query(self):
        # Assembled rather than written out, because the last test in this file
        # scans the repository for anything key-shaped and a literal here would
        # trip it. That check is worth more than the convenience of a literal.
        fake = "AIza" + "Sy" + "F" * 20 + "1234"
        leaked = ("HTTP Error 429: https://generativelanguage.googleapis.com/"
                  f"v1beta/models/x:generateContent?key={fake}")
        got = ai.redact(leaked)
        self.assertNotIn(fake, got)
        self.assertIn("[redacted]", got)

    def test_redact_scrubs_a_key_it_was_never_told_about(self):
        fake = "sk-ant-" + "api03-" + "Z" * 20        # assembled, see above
        got = ai.redact(f"bad token {fake} here")
        self.assertNotIn(fake, got)
        self.assertIn("[redacted]", got)

    def test_available_reports_configuration_without_echoing_anything(self):
        os.environ["OPENAI_API_KEY"] = FAKE_KEY
        try:
            rows = ai.available()
        finally:
            os.environ.pop("OPENAI_API_KEY", None)
        blob = json.dumps(rows)
        self.assertNotIn(FAKE_KEY, blob)
        self.assertTrue(next(r for r in rows
                             if r["provider"] == "openai")["configured"])
        self.assertIn("apple", {r["provider"] for r in rows})


# ─────────────────────────── narration and labelling ─────────────────────────

class TestNarration(unittest.TestCase):
    def test_supplied_text_flows_through_the_same_path(self):
        note = ai.narrate(tiny_brief(),
                          ai.SuppliedClient("He has 31.4 of your 88.2. Steady."))
        self.assertEqual(note.origin, "model")
        self.assertEqual(note.provider, "apple")
        self.assertTrue(note.trustworthy)
        self.assertEqual(note.unverified, [])

    def test_a_narration_is_always_labelled_as_model_written(self):
        d = ai.narrate(tiny_brief(), ai.SuppliedClient("Fine.")).as_dict()
        self.assertEqual(d["origin"], "model")
        self.assertIn("Written by a model", d["label"])

    def test_narration_origin_cannot_be_forged(self):
        note = ai.narrate(tiny_brief(), ai.SuppliedClient("Fine."))
        with self.assertRaises(AttributeError):
            note.origin = "computed"                          # type: ignore[misc]

    def test_an_invented_number_is_caught_and_flagged(self):
        note = ai.narrate(tiny_brief(), ai.SuppliedClient(
            "He has 31.4 of your 88.2 points and ranks 312.7 in the league."))
        self.assertIn("312.7", note.unverified)
        self.assertFalse(note.trustworthy)

    def test_a_number_that_was_given_is_not_flagged(self):
        note = ai.narrate(tiny_brief(), ai.SuppliedClient(
            "31.4 of 88.2 came from one man."))
        self.assertEqual(note.unverified, [])

    def test_an_unsourceable_metric_in_the_prose_is_flagged(self):
        note = ai.narrate(tiny_brief(), ai.SuppliedClient(
            "His yards per route run is why."))
        self.assertIn("yards per route run", note.flagged_metrics)
        self.assertFalse(note.trustworthy)

    def test_the_system_prompt_forbids_inventing_numbers(self):
        self.assertIn("Do not introduce any number", ai.SYSTEM)
        self.assertIn("route", ai.SYSTEM.lower())

    def test_the_prompt_carries_the_caveats(self):
        text = ai.prompt_for(tiny_brief())
        self.assertIn("Share of points already scored", text)

    def test_narrate_never_raises(self):
        class Exploding:
            provider, model, key = "openai", "m", FAKE_KEY

            def complete(self, *_a):
                raise RuntimeError(f"boom with {FAKE_KEY} inside")

        note = ai.narrate(tiny_brief(), Exploding())
        self.assertEqual(note.text, "")
        self.assertEqual(note.error["state"], "failed")
        self.assertNotIn(FAKE_KEY, json.dumps(note.as_dict()))

    def test_no_key_is_an_ordinary_state_with_plain_language(self):
        saved = {k: os.environ.pop(k, None)
                 for k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY",
                           "GOOGLE_API_KEY", "GEMINI_API_KEY")}
        try:
            note = ai.narrate(tiny_brief(), ai.client_for("openai", key=""))
        finally:
            for k, v in saved.items():
                if v is not None:
                    os.environ[k] = v
        self.assertEqual(note.error["state"], "no_key")
        self.assertNotIn("Traceback", note.error["message"])
        self.assertIn("export", note.error["remedy"])

    def test_an_empty_brief_is_not_sent_to_a_model(self):
        class Counting:
            provider, model, key = "openai", "m", ""

            def __init__(self):
                self.n = 0

            def complete(self, *_a):
                self.n += 1
                return "text"

        c = Counting()
        note = ai.narrate(intel.Brief(), c)
        self.assertEqual(c.n, 0)
        self.assertEqual(note.error["state"], "nothing_to_say")

    def test_the_brief_keeps_the_two_kinds_apart(self):
        brief = tiny_brief()
        brief.narration = ai.narrate(brief, ai.SuppliedClient("Fine."))
        d = brief.as_dict()
        self.assertEqual(d["counts"], {"computed": 1, "model": 1})
        self.assertEqual(d["narration"]["origin"], "model")
        self.assertTrue(all(i["origin"] == "computed" for i in d["insights"]))
        # The prose lives nowhere inside the computed half of the payload.
        self.assertNotIn("Fine.", json.dumps(d["insights"]))


class TestKeyStorage(unittest.TestCase):
    """`remember_key` writes outside the repository, mode 600, never in git."""

    def test_key_file_is_owner_only_and_outside_the_working_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            saved_dir, saved_file = ai.KEY_DIR, ai.KEY_FILE
            ai.KEY_DIR = pathlib.Path(tmp) / ".fantasy-edge"
            ai.KEY_FILE = ai.KEY_DIR / "ai.json"
            try:
                path = ai.remember_key("openai", FAKE_KEY)
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                self.assertEqual(json.loads(path.read_text())["openai"],
                                 FAKE_KEY)
            finally:
                ai.KEY_DIR, ai.KEY_FILE = saved_dir, saved_file

    def test_no_key_is_committed_anywhere_in_the_repository(self):
        """The rule this project cannot break, asserted rather than trusted."""
        root = pathlib.Path(__file__).resolve().parents[1]
        shaped = re.compile(r"\b(sk-ant-api\d{2}-|sk-proj-|AIzaSy)[A-Za-z0-9_-]{16,}")
        for path in list(root.glob("fantasyedge/**/*.py")) + \
                list(root.glob("tests/*.py")) + list(root.glob("docs/*.md")):
            text = path.read_text(encoding="utf-8", errors="replace")
            self.assertIsNone(shaped.search(text),
                              f"something key-shaped is committed in {path}")


# ─────────────────────── the wiring into the read API ────────────────────────

class _CountingClient(ai.Client):
    """A provider that never leaves the process and counts what it was asked.

    The counter is on the class because `client_for` builds a fresh instance
    per call, which is itself the property under test: the key is read at call
    time and goes out of scope with the client rather than living on the app.
    """

    provider = "stub"
    calls = 0
    text = "Your lead is real but thin, and the bench figure is an upper bound."

    def __init__(self, key: str = "", model: str = "", base: str = "") -> None:
        self.key, self.model, self.base = "", "stub-1", ""

    def complete(self, system: str, user: str) -> str:
        type(self).calls += 1
        return type(self).text


def brief_with(margin: float, win_prob: float) -> intel.Brief:
    """One fragility insight with the two numbers a live Sunday moves."""
    return intel.Brief(season=2025, week=3, insights=[intel.Insight(
        key="fragile:espn-99", kind="fragility",
        title="Your lead is not safe",
        detail=f"You are {margin} ahead but the model gives you {win_prob}%.",
        caveat="Win probability assumes independent, normally distributed "
               "outcomes, which is an approximation.",
        facts=[intel.Fact("Expected margin", margin, "pts", "leverage.evaluate"),
               intel.Fact("Win probability", win_prob, "%", "leverage.evaluate")],
        league="Fixture League", league_id="espn-99", weight=0.8)])


class FakeBriefApi:
    """`Api` with the compute half replaced, so the spend half can be tested.

    Subclassed rather than mocked: every cache decision, the loopback guard and
    the throttle are the real ones. Only `brief()` is swapped, because what a
    narration costs must not depend on what the database happens to contain.
    """

    @staticmethod
    def make(margin: float = 7.1, win_prob: float = 62.0):
        from fantasyedge.api import Api

        class Wired(Api):
            fake = brief_with(margin, win_prob)

            def brief(self):
                return self.fake

        return Wired(":memory:")


class TestIntelRoutes(unittest.TestCase):
    """The three routes, their policies, and what they may not carry."""

    def setUp(self):
        from fantasyedge import api as apimod

        self.api = FakeBriefApi.make()
        self.mod = apimod
        _CountingClient.calls = 0
        ai.CLIENTS["stub"] = _CountingClient
        self.saved_key_file = ai.KEY_FILE
        self.tmp = tempfile.TemporaryDirectory()
        ai.KEY_FILE = pathlib.Path(self.tmp.name) / "ai.json"
        self.saved_env = {k: os.environ.pop(k, None) for k in
                          ("OPENAI_API_KEY", "ANTHROPIC_API_KEY",
                           "GOOGLE_API_KEY", "GEMINI_API_KEY")}

    def tearDown(self):
        ai.CLIENTS.pop("stub", None)
        ai.KEY_FILE = self.saved_key_file
        for k, v in self.saved_env.items():
            if v is not None:
                os.environ[k] = v
        self.tmp.cleanup()
        self.api.close()

    def test_every_intel_route_is_advertised(self):
        advertised = {(r[0], r[1]) for r in self.mod.ROUTES}
        for row in (("GET", "/api/intel"), ("GET", "/api/intel/models"),
                    ("POST", "/api/intel/narrate")):
            self.assertIn(row, advertised, f"{row} is not in ROUTES")

    def test_the_brief_is_personal_and_so_is_not_on_the_live_tier(self):
        """`/api/intel` is built from `mosaics()`, which honours prefs.json, so
        it differs per person. The live tier's two-second max-age only works
        because every viewer gets identical bytes there - see live.py."""
        _, policy = self.api.dispatch("/api/intel", {})
        self.assertEqual(policy, self.mod.CONFIG)
        self.assertNotEqual(policy, self.mod.LIVE)

    def test_models_route_is_config(self):
        _, policy = self.api.dispatch("/api/intel/models", {})
        self.assertEqual(policy, self.mod.CONFIG)

    def test_models_answers_in_booleans_and_never_in_a_key(self):
        ai.KEY_FILE.write_text(json.dumps({"openai": FAKE_KEY}))
        payload = self.api.intel_models()
        for p in payload["providers"]:
            self.assertIsInstance(p["configured"], bool)
        self.assertTrue(
            next(p for p in payload["providers"]
                 if p["provider"] == "openai")["configured"],
            "a configured provider must still report True")
        blob = json.dumps(payload)
        self.assertNotIn(FAKE_KEY, blob)
        # Not a prefix and not a suffix either: eight characters of a key is
        # still eight characters of a key in a screenshot.
        self.assertNotIn(FAKE_KEY[:8], blob)
        self.assertNotIn(FAKE_KEY[-8:], blob)

    def test_the_brief_carries_the_unsourceable_metrics_with_reasons(self):
        """Five metrics the design asks for and no feed here can supply. They
        ship in every brief so the view can say so, rather than leaving a gap
        the reader fills in with an assumption."""
        out = self.api.intel_brief()
        self.assertEqual(len(out["unavailable"]), 5)
        for u in out["unavailable"]:
            self.assertTrue(u.get("reason", "").strip(),
                            f"{u} is missing its reason")

    def test_the_brief_offers_a_prompt_but_no_prose(self):
        out = self.api.intel_brief()
        self.assertIsNone(out["narration"]["cached"])
        self.assertIn("system", out["narration"]["prompt"])
        self.assertTrue(out["narration"]["prompt"]["user"])
        self.assertFalse(out["narration"]["chat"]["available"],
                         "AI chat is out of scope and must not advertise itself")


class TestNarrationSpend(unittest.TestCase):
    """The half of this that costs money, and what stops it."""

    def setUp(self):
        _CountingClient.calls = 0
        ai.CLIENTS["stub"] = _CountingClient
        self.saved = {k: os.environ.get(k) for k in
                      ("FANTASYEDGE_AI_MIN_INTERVAL", "FANTASYEDGE_AI_TTL")}
        os.environ["FANTASYEDGE_AI_MIN_INTERVAL"] = "0"

    def tearDown(self):
        ai.CLIENTS.pop("stub", None)
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_a_poll_of_the_brief_never_reaches_a_provider(self):
        """The rule the whole design exists for. A board left open on a
        television polls this route for hours; not one of those requests may
        produce a paid call."""
        api = FakeBriefApi.make()
        try:
            for _ in range(40):
                api.intel_brief()
                api.intel_models()
                api.dispatch("/api/intel", {})
        finally:
            api.close()
        self.assertEqual(_CountingClient.calls, 0)

    def test_many_explicit_requests_cost_one_call(self):
        api = FakeBriefApi.make()
        try:
            first = api.narrate({"provider": "stub"})
            self.assertFalse(first["cached"])
            self.assertEqual(first["origin"], "model")
            for _ in range(30):
                again = api.narrate({"provider": "stub"})
                self.assertTrue(again["cached"])
                self.assertIsInstance(again["ageSeconds"], int)
        finally:
            api.close()
        self.assertEqual(_CountingClient.calls, 1)

    def test_drift_inside_a_bucket_does_not_buy_a_second_paragraph(self):
        """A point of win probability is the same paragraph of English. Keying
        on the exact brief would re-buy it on every scoring play."""
        api = FakeBriefApi.make(margin=7.1, win_prob=62.0)
        try:
            api.narrate({"provider": "stub"})
            api.fake = brief_with(margin=7.4, win_prob=64.0)
            out = api.narrate({"provider": "stub"})
            self.assertTrue(out["cached"])
        finally:
            api.close()
        self.assertEqual(_CountingClient.calls, 1)

    def test_a_real_change_in_the_facts_does_buy_one(self):
        api = FakeBriefApi.make(margin=7.1, win_prob=62.0)
        try:
            api.narrate({"provider": "stub"})
            api.fake = brief_with(margin=25.3, win_prob=84.0)
            out = api.narrate({"provider": "stub"})
            self.assertFalse(out["cached"])
        finally:
            api.close()
        self.assertEqual(_CountingClient.calls, 2)

    def test_the_floor_bounds_a_client_that_posts_in_a_loop(self):
        """Rule two makes the common case free. This is what bounds the case
        where the shape really is moving and the client really is looping."""
        os.environ["FANTASYEDGE_AI_MIN_INTERVAL"] = "600"
        api = FakeBriefApi.make(margin=7.1, win_prob=62.0)
        try:
            api.narrate({"provider": "stub"})
            for i in range(20):
                api.fake = brief_with(margin=7.1 + 6 * (i + 1), win_prob=62.0)
                out = api.narrate({"provider": "stub"})
                self.assertTrue(out["cached"])
                self.assertGreater(out["throttled"], 0)
                self.assertTrue(out["factsChanged"],
                                "a throttled answer must admit it has drifted")
        finally:
            api.close()
        self.assertEqual(_CountingClient.calls, 1)

    def test_a_refresh_still_cannot_beat_the_floor(self):
        os.environ["FANTASYEDGE_AI_MIN_INTERVAL"] = "600"
        api = FakeBriefApi.make()
        try:
            api.narrate({"provider": "stub"})
            for _ in range(10):
                api.narrate({"provider": "stub", "refresh": True})
        finally:
            api.close()
        self.assertEqual(_CountingClient.calls, 1)

    def test_a_failing_provider_is_not_retried_in_a_loop(self):
        """The call is what sets the clock and a failure stores no prose, so
        without a floor on the empty case a client retrying a 500 would reach
        the provider every single time."""
        class Broken(_CountingClient):
            def complete(self, system, user):
                _CountingClient.calls += 1
                raise ai.ModelError("unavailable", "The provider is down.", "")

        ai.CLIENTS["stub"] = Broken
        os.environ["FANTASYEDGE_AI_MIN_INTERVAL"] = "600"
        api = FakeBriefApi.make()
        try:
            first = api.narrate({"provider": "stub"})
            self.assertEqual(first["error"]["state"], "unavailable")
            for _ in range(20):
                again = api.narrate({"provider": "stub"})
                self.assertEqual(again["error"]["state"], "throttled")
                self.assertGreater(again["throttled"], 0)
                self.assertTrue(again["error"]["remedy"])
        finally:
            api.close()
            ai.CLIENTS["stub"] = _CountingClient
        self.assertEqual(_CountingClient.calls, 1)

    def test_supplied_text_costs_no_call_and_is_kept(self):
        """Apple Intelligence runs on the user's own device, so the text is
        already paid for. Throwing it away to save a call that was never going
        to be made would be the wrong economy."""
        api = FakeBriefApi.make()
        try:
            out = api.narrate({"provider": "apple",
                               "text": "Nothing here is settled."})
            self.assertEqual(out["provider"], "apple")
            self.assertEqual(out["origin"], "model")
            held = api.intel_brief()["narration"]["cached"]
            self.assertIsNotNone(held)
            self.assertEqual(held["text"], "Nothing here is settled.")
        finally:
            api.close()
        self.assertEqual(_CountingClient.calls, 0)

    def test_a_cached_paragraph_is_re_checked_against_the_brief_on_screen(self):
        """`trustworthy` has to describe the figures the reader can see now,
        not the ones that were there when the prose was written."""
        _CountingClient.text = "You are 41.5 points clear."
        try:
            api = FakeBriefApi.make(margin=41.5, win_prob=62.0)
            out = api.narrate({"provider": "stub"})
            self.assertEqual(out["unverified"], [])
            # Same bucket, so no new call - but 41.5 is no longer a number
            # anybody computed, and the served copy must say so.
            api.fake = brief_with(margin=42.0, win_prob=62.0)
            again = api.narrate({"provider": "stub"})
            self.assertTrue(again["cached"])
            self.assertIn("41.5", again["unverified"])
            self.assertFalse(again["trustworthy"])
            api.close()
        finally:
            _CountingClient.text = ("Your lead is real but thin, and the bench "
                                    "figure is an upper bound.")
        self.assertEqual(_CountingClient.calls, 1)

    def test_an_unknown_provider_is_an_error_not_somebody_elses_paragraph(self):
        """The cache is keyed on the brief, not the provider, so a misspelled
        name would otherwise be answered with a 200 and the last model's
        prose."""
        from fantasyedge.api import HttpError

        api = FakeBriefApi.make()
        try:
            api.narrate({"provider": "stub"})
            with self.assertRaises(HttpError) as caught:
                api.narrate({"provider": "stbu"})
            self.assertEqual(caught.exception.code, 404)
            self.assertIn("stub", caught.exception.fix)
        finally:
            api.close()
        self.assertEqual(_CountingClient.calls, 1)

    def test_no_ai_refuses_and_says_why(self):
        from fantasyedge.api import Api, HttpError

        class Wired(Api):
            fake = brief_with(7.1, 62.0)

            def brief(self):
                return self.fake

        api = Wired(":memory:", allow_ai=False)
        try:
            with self.assertRaises(HttpError) as caught:
                api.narrate({"provider": "stub"})
            self.assertEqual(caught.exception.code, 403)
            self.assertTrue(caught.exception.fix)
            models = api.intel_models()
            self.assertFalse(models["enabled"])
            for p in models["providers"]:
                self.assertFalse(p["configured"])
                self.assertIn("--no-ai", p["disabled"])
        finally:
            api.close()
        self.assertEqual(_CountingClient.calls, 0)


class TestNarrationShape(unittest.TestCase):
    """What the narration cache is keyed on, asserted directly."""

    def test_a_point_of_win_probability_is_the_same_shape(self):
        from fantasyedge.api import narration_shape

        self.assertEqual(narration_shape(brief_with(7.1, 62.0)),
                         narration_shape(brief_with(7.4, 64.0)))

    def test_a_collapse_is_not(self):
        from fantasyedge.api import narration_shape

        self.assertNotEqual(narration_shape(brief_with(7.1, 62.0)),
                            narration_shape(brief_with(-9.0, 31.0)))

    def test_a_different_player_is_not(self):
        """The insight key alone would hold a stale sentence about the wrong
        man: `carry:espn-99` does not say who is carrying."""
        from fantasyedge.api import narration_shape

        a = brief_with(7.1, 62.0)
        b = brief_with(7.1, 62.0)
        a.insights[0].players = [{"id": "1", "name": "A"}]
        b.insights[0].players = [{"id": "2", "name": "B"}]
        self.assertNotEqual(narration_shape(a), narration_shape(b))

    def test_a_finding_that_stops_firing_is_not(self):
        from fantasyedge.api import narration_shape

        empty = intel.Brief(season=2025, week=3, insights=[])
        self.assertNotEqual(narration_shape(brief_with(7.1, 62.0)),
                            narration_shape(empty))


class TestNarrateIsLoopbackOnly(unittest.TestCase):
    """The same restriction `POST /api/prefs` carries, for a second reason on
    top of the first: this route reads a key and spends money."""

    def _handler(self, host: str, body: dict):
        from fantasyedge.api import make_handler

        app = FakeBriefApi.make()
        self.addCleanup(app.close)
        raw = json.dumps(body).encode()
        handler = object.__new__(make_handler(app))
        handler.client_address = (host, 5000)
        handler.path = "/api/intel/narrate"
        handler.headers = {"Content-Length": str(len(raw))}
        handler.rfile = io.BytesIO(raw)
        sent = {}
        handler._send = lambda payload, code=200, policy=None: sent.update(
            payload=payload, code=code)
        handler.do_POST()
        return sent

    def setUp(self):
        _CountingClient.calls = 0
        ai.CLIENTS["stub"] = _CountingClient
        os.environ.pop("FANTASYEDGE_ALLOW_REMOTE_AI", None)
        os.environ["FANTASYEDGE_AI_MIN_INTERVAL"] = "0"

    def tearDown(self):
        ai.CLIENTS.pop("stub", None)
        os.environ.pop("FANTASYEDGE_AI_MIN_INTERVAL", None)

    def test_a_remote_client_is_refused(self):
        sent = self._handler("192.168.1.40", {"provider": "stub"})
        self.assertEqual(sent["code"], 403)
        self.assertTrue(sent["payload"]["fix"])
        self.assertEqual(_CountingClient.calls, 0,
                         "a refused request must not have spent anything")

    def test_this_machine_is_allowed(self):
        sent = self._handler("127.0.0.1", {"provider": "stub"})
        self.assertEqual(sent["code"], 200)
        self.assertEqual(sent["payload"]["origin"], "model")
        self.assertEqual(_CountingClient.calls, 1)

    def test_the_escape_hatch_is_not_the_prefs_one(self):
        """Letting a housemate reorder your leagues from the television is not
        the same decision as letting them run up your model bill."""
        os.environ["FANTASYEDGE_ALLOW_REMOTE_PREFS"] = "1"
        try:
            sent = self._handler("192.168.1.40", {"provider": "stub"})
            self.assertEqual(sent["code"], 403)
        finally:
            os.environ.pop("FANTASYEDGE_ALLOW_REMOTE_PREFS", None)



if __name__ == "__main__":
    unittest.main()
