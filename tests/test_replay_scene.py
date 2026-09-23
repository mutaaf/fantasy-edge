"""Replay any finished game, and the scene every renderer draws from it.

Three real 2025 games, each a different shape, cut by
`tools/make_replay_fixture.py --game` and never edited by hand:

  401772510  DAL 20 @ PHI 24   a regulation game
  401772949  LAR 37 @ SEA 38   overtime, won by a touchdown and a two-point try
  401772810  MIN 24 @ CHI 27   a pick-six, scored by the side without the ball

The scene assertions are the contract a port has to match - RealityKit today,
a web or Android renderer later - so they are stated as the formulas and
facts of these games rather than as whatever the code currently returns.
"""

from __future__ import annotations

import ast
import io
import json
import math
import os
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from fantasyedge import replay as rp                          # noqa: E402
from fantasyedge import scene as sc                           # noqa: E402

FIX = pathlib.Path(__file__).parent / "fixtures"
REGULATION, OVERTIME, PICK_SIX = "401772510", "401772949", "401772810"


def _prop_ids(sideline: dict) -> set:
    """Every prop id SidelineActor can place, from the tokens it reads: the
    league-dependent posts and pylons, the benches, the team-area dressing,
    the end-line props and the chain crew."""
    ids = {"goalpost_nfl", "goalpost_college", "pylon_nfl", "pylon_college", "bench"}
    ids |= {d["model"] for d in sideline["dressing"]}
    ids |= {d["model"] for d in sideline["endLine"]}
    ids |= {sideline["chains"][k] for k in ("set", "box", "ground")}
    return ids


def setUpModule():
    # The same promise as the rest of the suite: no network. The replay routes
    # never touch the real source, but the real source is asserted on below.
    os.environ["FANTASYEDGE_SCOREBOARD_FILE"] = str(FIX / "espn_scoreboard.json")
    os.environ["FANTASYEDGE_SUMMARY_FILE"] = str(FIX / "espn_summary.json")
    # A finished game's plays are corrected against nflverse in the real
    # server (api.correct_finished), and that reads a release over HTTPS. The
    # correction has its own fixture-driven tests in test_truth.py; here it is
    # off so the suite holds its promise however it was launched, not only
    # through `make test`.
    os.environ["FANTASYEDGE_CORRECT_PLAYS"] = "0"


_GAMES: dict[str, dict] = {}


def game(event: str) -> dict:
    if event not in _GAMES:
        _GAMES[event] = json.loads((FIX / f"replay_game_{event}.json").read_text())
    return _GAMES[event]


def source_dir(*events: str) -> pathlib.Path:
    """A capture directory holding these games, as `capture` writes it."""
    root = pathlib.Path(tempfile.mkdtemp())
    for ev in events:
        g = game(ev)
        (root / f"{ev}.json").write_text(json.dumps(g["summary"]))
        rp.scoreboard_path(root, ev).write_text(json.dumps(g["scoreboard"]))
    return root


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def director(*events: str) -> tuple[rp.ReplayDirector, Clock]:
    clock = Clock()
    return rp.ReplayDirector(source_dir(*events), clock=clock), clock


def api_with(*events: str):
    from fantasyedge import api

    app = api.Api(db=str(pathlib.Path(tempfile.mkdtemp()) / "t.db"))
    d, clock = director(*events)
    app._replay = d
    return app, d, clock


def play_second(summary: dict, text: str) -> int:
    lengths = rp.period_lengths(summary)
    p = next(p for p in rp._all_plays(summary) if text in (p.get("text") or ""))
    return rp.play_seconds(p, lengths)


# ═════════════════════════════ the replay ═════════════════════════════

class TestOvertimeRunsOnItsOwnClock(unittest.TestCase):
    """A regular-season overtime is ten minutes. Encoded against fifteen, its
    first snap sat five minutes of game clock after regulation ended."""

    def test_overtime_is_six_hundred_seconds_and_regulation_is_untouched(self):
        self.assertEqual(rp.period_lengths(game(OVERTIME)["summary"]), {5: 600})
        self.assertEqual(rp.period_lengths(game(REGULATION)["summary"]), {})

    def test_the_first_overtime_snap_follows_regulation_directly(self):
        sm = game(OVERTIME)["summary"]
        lengths = rp.period_lengths(sm)
        first = next(p for p in rp._all_plays(sm) if p["period"]["number"] == 5)
        self.assertEqual(first["clock"]["displayValue"], "10:00")
        self.assertEqual(rp.play_seconds(first, lengths), 3600)
        # 3:13 left in a ten-minute overtime is 407 seconds in.
        self.assertEqual(rp.total_seconds(sm), 3600 + 407)

    def test_a_frame_in_overtime_reads_the_overtime_clock(self):
        g = game(OVERTIME)
        _, sm = rp.frame(g["scoreboard"], g["summary"], 3600 + 60)
        self.assertEqual(sm["replay"]["period"], 5)
        status = sm["header"]["competitions"][0]["status"]
        self.assertEqual(status["type"]["shortDetail"].split(" - ")[1], "OT")
        self.assertTrue(status["displayClock"].startswith("9:"))

    def test_clock_at_inverts_play_seconds_across_periods(self):
        lengths = {5: 600}
        self.assertEqual(rp.clock_at(0, lengths), (1, 900))
        self.assertEqual(rp.clock_at(2700 + 899, lengths), (4, 1))
        self.assertEqual(rp.clock_at(3600 + 407, lengths), (5, 600 - 407))


class TestAGameIsCompleteByItsHeaderAndItsLastPlay(unittest.TestCase):

    def test_every_whole_capture_is_complete(self):
        for ev in (REGULATION, OVERTIME, PICK_SIX):
            self.assertTrue(rp.capture_is_complete(game(ev)["summary"]), ev)

    def test_a_walk_off_with_no_closing_record_is_still_complete(self):
        """College overtime ends on the scoring play. Strip the NFL's closing
        records and the same game must still be judged whole."""
        sm = json.loads(json.dumps(game(OVERTIME)["summary"]))
        last = sm["drives"]["previous"][-1]
        while last["plays"][-1]["type"]["text"] in ("End of Game", "Timeout"):
            last["plays"].pop()
        self.assertEqual(last["plays"][-1]["type"]["text"], "Passing Touchdown")
        self.assertTrue(rp.capture_is_complete(sm))

    def test_a_trimmed_capture_of_a_final_game_is_not(self):
        """The header of a trimmed capture still says FINAL; the last play
        does not carry the final score, so it is partial."""
        sm = json.loads(json.dumps(game(REGULATION)["summary"]))
        sm["drives"]["previous"] = sm["drives"]["previous"][:6]
        self.assertFalse(rp.capture_is_complete(sm))


class TestCaptureKeepsEveryGamesSlate(unittest.TestCase):

    def fake_espn(self, event: str, filed_under: str):
        g = game(event)
        asked = []

        def http(url):
            asked.append(url)
            if "summary?event=" in url:
                return g["summary"]
            if f"dates={filed_under}" in url:
                return g["scoreboard"]
            return {"events": []}
        return http, asked

    def test_a_night_game_is_found_on_the_eastern_date(self):
        """401772810 kicked off 2025-09-09T00:20Z, Monday night the 8th."""
        http, asked = self.fake_espn(PICK_SIX, "20250908")
        dest = pathlib.Path(tempfile.mkdtemp())
        info = rp.capture(PICK_SIX, dest, http=http)
        self.assertEqual(info["plays"], 185)
        boards = [u for u in asked if "scoreboard" in u]
        self.assertIn("dates=20250909", boards[0])
        self.assertIn("dates=20250908", boards[1])
        self.assertTrue(rp.scoreboard_path(dest, PICK_SIX).exists())

    def test_a_second_capture_does_not_break_the_first(self):
        dest = pathlib.Path(tempfile.mkdtemp())
        for ev, day in ((REGULATION, "20250904"), (OVERTIME, "20251218")):
            http, _ = self.fake_espn(ev, day)
            rp.capture(ev, dest, http=http)
        for ev in (REGULATION, OVERTIME):
            board, summary = rp.load(dest, ev)
            self.assertTrue(rp._event(board, ev), ev)

    def test_a_legacy_shared_scoreboard_is_read_only_if_it_carries_the_game(self):
        dest = pathlib.Path(tempfile.mkdtemp())
        (dest / f"{OVERTIME}.json").write_text(json.dumps(game(OVERTIME)["summary"]))
        (dest / "scoreboard.json").write_text(json.dumps(game(REGULATION)["scoreboard"]))
        with self.assertRaises(SystemExit):
            rp.load(dest, OVERTIME)

    def test_find_event_by_week_and_club(self):
        board = game(PICK_SIX)["scoreboard"]
        asked = []

        def http(url):
            asked.append(url)
            return board
        self.assertEqual(rp.find_event(2025, 1, "chi", http=http), PICK_SIX)
        self.assertIn("seasontype=2&week=1", asked[0])
        with self.assertRaises(SystemExit):
            rp.find_event(2025, 1, "SEA", http=http)


class TestTheDirector(unittest.TestCase):

    def test_play_pause_seek_and_speed_move_an_anchor_not_a_ticker(self):
        d, clock = director(REGULATION)
        d.load(REGULATION)
        self.assertEqual(d.game_seconds(), 0)
        d.set_speed(60)
        d.play()
        clock.now += 10
        self.assertEqual(d.game_seconds(), 600)
        d.pause()
        clock.now += 100
        self.assertEqual(d.game_seconds(), 600)
        d.seek(1800)
        self.assertEqual(d.state()["period"], 3)
        d.set_speed(5)
        d.play()
        clock.now += 4
        self.assertEqual(d.game_seconds(), 1820)

    def test_the_tape_stops_at_the_end_and_play_rewinds_it(self):
        d, clock = director(OVERTIME)
        d.load(OVERTIME, at=4000)
        d.play()
        clock.now += 60
        state = d.state()
        self.assertEqual(state["gameSeconds"], 4007)
        self.assertFalse(state["playing"])
        self.assertEqual((state["homeScore"], state["awayScore"]), (38, 37))
        d.play()
        self.assertEqual(d.game_seconds(), 0)

    def test_the_board_carries_only_the_replayed_game(self):
        """The rest of that week's slate would show its finals beside a game
        still in its first quarter."""
        d, _ = director(REGULATION)
        d.load(REGULATION, at=900)
        board = d.fetch("https://x/scoreboard")
        self.assertEqual([e["id"] for e in board["events"]], [REGULATION])
        self.assertEqual(board["replay"]["event"], REGULATION)
        with self.assertRaises(LookupError):
            d.fetch("https://x/summary?event=401772949")

    def test_every_state_says_replay(self):
        d, _ = director(REGULATION)
        self.assertTrue(d.state()["replay"])
        d.load(REGULATION)
        self.assertTrue(d.state()["replay"])
        self.assertEqual(d.catalog()[0]["event"], REGULATION)

    def test_bad_controls_are_refused(self):
        d, _ = director(REGULATION)
        with self.assertRaises(LookupError):
            d.play()
        d.load(REGULATION)
        with self.assertRaises(ValueError):
            d.control({"action": "rewind"})
        with self.assertRaises(ValueError):
            d.set_speed(10_000)
        with self.assertRaises(ValueError):
            d.load("../../etc/passwd")


class TestReplayRoutes(unittest.TestCase):

    def test_routes_are_listed_and_cached_as_replays(self):
        from fantasyedge import api

        listed = {(m, p) for m, p, _ in api.ROUTES}
        for route in (("GET", "/api/replay"), ("POST", "/api/replay"),
                      ("GET", "/api/replay/live"), ("GET", "/api/replay/gamecast"),
                      ("GET", "/api/replay/scene"), ("GET", "/api/scene/{event}")):
            self.assertIn(route, listed)
        app, d, _ = api_with(OVERTIME)
        self.addCleanup(app.close)
        d.load(OVERTIME, at=3700)
        for path in ("/api/replay", "/api/replay/live", "/api/replay/gamecast",
                     "/api/replay/scene"):
            _, policy = app.dispatch(path, {})
            self.assertEqual(policy, api.REPLAY, path)

    def test_a_replay_never_reaches_the_real_live_tier(self):
        app, d, _ = api_with(OVERTIME)
        self.addCleanup(app.close)
        d.load(OVERTIME, at=3700)
        self.assertIsNot(app.replay_source(), app.live_source())
        self.assertEqual(app.replay_live()["source"], "replay")
        self.assertNotEqual(app.live()["source"], "replay")

    def test_the_gamecast_and_scene_are_labelled(self):
        app, d, _ = api_with(OVERTIME)
        self.addCleanup(app.close)
        d.load(OVERTIME, at=3700)
        gc = app.replay_gamecast()
        self.assertEqual(gc["replay"]["event"], OVERTIME)
        self.assertTrue(gc["replayControl"]["replay"])
        scene = app.replay_scene()
        self.assertEqual(scene["source"], "replay")
        self.assertEqual(scene["status"]["period"], 5)

    def test_nothing_loaded_is_a_404_with_a_fix(self):
        from fantasyedge.api import HttpError

        app, _, _ = api_with(OVERTIME)
        self.addCleanup(app.close)
        with self.assertRaises(HttpError) as ctx:
            app.dispatch("/api/replay/scene", {})
        self.assertEqual(ctx.exception.code, 404)
        self.assertIn("load", ctx.exception.fix)

    def _post(self, host: str, body: dict):
        from fantasyedge.api import make_handler

        app, _, _ = api_with(REGULATION)
        self.addCleanup(app.close)
        raw = json.dumps(body).encode()
        handler = object.__new__(make_handler(app))
        handler.client_address = (host, 5000)
        handler.path = "/api/replay"
        handler.headers = {"Content-Length": str(len(raw))}
        handler.rfile = io.BytesIO(raw)
        sent = {}
        handler._send = lambda payload, code=200, policy=None: sent.update(
            payload=payload, code=code, policy=policy)
        handler.do_POST()
        return sent

    def test_the_controls_are_loopback_only(self):
        os.environ.pop("FANTASYEDGE_ALLOW_REMOTE_REPLAY", None)
        refused = self._post("192.168.1.40", {"action": "load", "event": REGULATION})
        self.assertEqual(refused["code"], 403)
        self.assertIn("FANTASYEDGE_ALLOW_REMOTE_REPLAY", refused["payload"]["fix"])
        ok = self._post("127.0.0.1", {"action": "load", "event": REGULATION})
        self.assertEqual(ok["code"], 200)
        self.assertTrue(ok["payload"]["loaded"])

    def test_the_escape_hatch_is_its_own(self):
        os.environ["FANTASYEDGE_ALLOW_REMOTE_PREFS"] = "1"
        try:
            self.assertEqual(self._post("192.168.1.40", {"action": "play"})["code"], 403)
        finally:
            os.environ.pop("FANTASYEDGE_ALLOW_REMOTE_PREFS", None)
        os.environ["FANTASYEDGE_ALLOW_REMOTE_REPLAY"] = "1"
        try:
            sent = self._post("192.168.1.40", {"action": "load", "event": REGULATION})
            self.assertEqual(sent["code"], 200)
        finally:
            os.environ.pop("FANTASYEDGE_ALLOW_REMOTE_REPLAY", None)

    def test_a_bad_action_is_a_400(self):
        sent = self._post("127.0.0.1", {"action": "rewind"})
        self.assertEqual(sent["code"], 400)
        self.assertIn("seek", sent["payload"]["fix"])


class TestNamesThePlayTextActuallyWrites(unittest.TestCase):
    """Two ways the 2025 text broke name resolution, both found by reconciling
    these captures against ESPN's own box scores."""

    def roster(self):
        def ath(pid, name, cat):
            return {"name": cat, "athletes": [{"athlete": {"id": pid, "displayName": name}}]}
        summary = {"boxscore": {"players": [{
            "team": {"abbreviation": "CHI"},
            "statistics": [ath("1", "Caleb Williams", "passing"),
                           ath("2", "Chris Williams", "defensive"),
                           ath("3", "Jaquan Brisker", "defensive"),
                           ath("4", "Tremaine Edmunds", "defensive")]}]}}
        return rp.Roster(summary)

    def test_two_men_with_one_initial_are_told_apart_by_the_slot(self):
        roster = self.roster()
        self.assertIsNone(roster.find("C.Williams", "CHI"))
        self.assertEqual(roster.find("C.Williams", "CHI", "passing"), "1")
        self.assertEqual(roster.find("C.Williams", "CHI", "defensive"), "2")
        self.assertEqual(roster.find("Ch.Williams", "CHI"), "2")

    def test_tacklers_split_on_a_comma_as_well_as_a_semicolon(self):
        self.assertEqual(rp._names("J.Brisker, T.Edmunds"), ["J.Brisker", "T.Edmunds"])
        self.assertEqual(rp._names("J.Brisker; T.Edmunds"), ["J.Brisker", "T.Edmunds"])


# ═════════════════════════════ the scene ═════════════════════════════

class SceneAt:
    """A scene for one fixture game at one game second, through the API."""
    _apps: dict = {}

    @classmethod
    def at(cls, event: str, seconds: int, speed: float = 1.0) -> dict:
        app, d, _ = api_with(event)
        d.load(event, at=seconds)
        if speed != 60.0:
            d.set_speed(speed)
        out = app.replay_scene()
        app.close()
        return out


class TestSceneGeometry(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tokens = sc.load_tokens()
        cls.final = SceneAt.at(REGULATION, 99999, speed=1.0)

    def arcs(self, scene):
        return [a for d in scene["drives"] for a in d["arcs"]]

    def test_version_axes_and_field(self):
        s = self.final
        self.assertEqual(s["version"], sc.SCENE_VERSION)
        self.assertEqual(s["kind"], "football-scene")
        self.assertAlmostEqual(s["field"]["width"], 53.333, places=2)
        self.assertEqual(s["field"]["homeEndZone"], [-10.0, 0.0])
        self.assertEqual(s["field"]["awayEndZone"], [100.0, 110.0])
        self.assertEqual(set(s["palette"]), set(self.tokens["color"]))

    def test_apex_is_the_stated_formula_for_every_arc(self):
        """Pass 3 + 0.35d, run 0.8 + 0.12d, kick 8 + 0.25d, flat 0."""
        formula = {"pass": (3.0, 0.35), "run": (0.8, 0.12), "kick": (8.0, 0.25),
                   "flat": (0.0, 0.0)}
        arcs = self.arcs(self.final)
        self.assertGreater(len(arcs), 140)
        for a in arcs:
            base, per = formula[a["shape"]]
            self.assertAlmostEqual(a["apex"], base + per * abs(a["toX"] - a["fromX"]),
                                   places=2, msg=a["text"])
        ten = [a for a in arcs if a["shape"] == "pass" and abs(a["toX"] - a["fromX"]) == 10]
        self.assertTrue(ten)
        self.assertAlmostEqual(ten[0]["apex"], 6.5)

    def test_lanes_fan_each_drive_symmetrically(self):
        spread = self.final["field"]["width"] * self.tokens["arc"]["laneSpread"]
        for d in self.final["drives"]:
            # A field goal or extra point aims at the posts, not a lane
            # (TestGoalKicks); the rest of the drive fans.
            lanes = [a["lane"] for a in d["arcs"]
                     if not any(k in a["type"].lower() for k in ("field goal", "extra point"))]
            if len(lanes) == 1:
                self.assertEqual(lanes, [0.0])
            elif len(lanes) > 1:
                # Rounded to a thousandth of a yard on the wire.
                self.assertTrue(all(abs(z) <= spread + 0.001 for z in lanes), lanes)
                self.assertEqual(lanes, sorted(lanes))
                self.assertAlmostEqual(lanes[0], -spread, places=2)

    def test_goal_kicks_cross_the_plane_of_the_uprights_as_the_text_says(self):
        """Every field goal in the three games, at the end line it attacks:
        a good one between the uprights and over the crossbar with room to
        spare; a wide one outside the upright on the side the text names,
        right being the kicker's right."""
        props = self.final["field"]["props"]["goalpost"]
        clearance = self.tokens["arc"]["goalKick"].get("minClearanceYards", 1.0)
        seen = {"good": 0, "wide": 0}
        for event in (REGULATION, OVERTIME, PICK_SIX):
            s = SceneAt.at(event, 99999, speed=1.0)
            f = s["field"]
            half = f["goalPostWidth"] / 2
            for a in self.arcs(s):
                kind, text = a["type"].lower(), a["text"].lower()
                if "field goal" not in kind or "blocked" in text:
                    continue
                attack = 1.0 if a["toX"] > a["fromX"] else -1.0
                plane = f["length"] + f["endZone"] if attack > 0 else -f["endZone"]
                self.assertEqual(attack > 0, a["side"] == "home", f"{a['id']}: kicked at the wrong posts")
                u = (plane - a["fromX"]) / (a["toX"] - a["fromX"])
                self.assertTrue(0 < u < 1, f"{a['id']}: the arc never reaches the posts")
                height = a["apex"] * 4 * u * (1 - u)
                if "good" in text and "no good" not in text:
                    seen["good"] += 1
                    self.assertLess(abs(a["lane"]), half, f"{a['id']}: a good kick outside the uprights")
                    self.assertGreaterEqual(height, props["crossbar"] + clearance,
                                            f"{a['id']}: a good kick {height:.1f} yd at the posts, under the bar")
                elif "wide right" in text or "wide left" in text:
                    seen["wide"] += 1
                    self.assertGreater(abs(a["lane"]), half, f"{a['id']}: a wide kick between the uprights")
                    right = 1.0 if "wide right" in text else -1.0
                    self.assertGreater(a["lane"] * right * attack, 0, f"{a['id']}: wide on the wrong side")
        self.assertGreater(seen["good"], 3)
        self.assertGreaterEqual(seen["wide"], 2)

    def test_trails_fade_end_on_and_stay_whole_side_on(self):
        """BroadcastTrails.sideOn, restated: field goals seen from behind the
        end zone fade toward their subtle core; from the club seat every field
        goal and every play of the game stays whole."""
        look = self.tokens["visual"]["broadcast"]["trail"]
        edge, kick = look["edge"], look["kick"]
        eye = self.tokens["visual"]["experience"]["camera"]["eyeMeters"] / 0.9144
        self.assertTrue(0 < edge["minOpacity"] < 1 and 0 < edge["minScale"] < 1)
        self.assertTrue(0 <= kick["restOpacity"] < 1 and kick["fadeSeconds"] > 0)

        lift = self.tokens["visual"]["broadcast"]["play"]["heights"]["trailLift"]

        def side_on(a, seat):
            # Along the line the trail draws (scene.trail_points), weighted by length.
            e, total, weight = (seat["x"], seat["y"] + eye, seat["z"]), 0.0, 0.0
            line = sc.trail_points(a, 96, lift)
            ground = min(pt[1] for pt in line)
            for p, q in zip(line, line[1:]):
                if max(p[1], q[1]) <= ground + 0.05:
                    continue
                t = [q[k] - p[k] for k in range(3)]
                d = [e[k] - (p[k] + q[k]) / 2 for k in range(3)]
                tl, dl = math.sqrt(sum(c * c for c in t)), math.sqrt(sum(c * c for c in d))
                if tl < 1e-5 or dl < 1e-5:
                    continue
                total += tl * math.degrees(math.acos(min(1, abs(sum(t[k] * d[k] for k in range(3))) / (tl * dl))))
                weight += tl
            deg = total / weight if weight else 90
            rule = kick if a["shape"] == "kick" else edge
            return max(0.0, min(1.0, (deg - rule["goneDegrees"]) / (rule["fullDegrees"] - rule["goneDegrees"])))

        faded = 0
        for event in (REGULATION, OVERTIME, PICK_SIX):
            s = SceneAt.at(event, 99999, speed=1.0)
            seats = {x["id"]: x for x in s["presentation"]["stadium"]["seats"]}
            for a in self.arcs(s):
                if a["shape"] not in edge["shapes"]:
                    continue
                self.assertEqual(side_on(a, seats["club"]), 1.0, f"{a['id']} {a['type']}: dimmed from the club seat")
                if "field goal" in a["type"].lower() and (a["toX"] < a["fromX"]):
                    # Kicked into the home end, toward the end-zone seat.
                    self.assertLess(side_on(a, seats["endzone"]), 0.75, f"{a['id']}: a streak from behind the posts")
                    faded += 1
        self.assertGreater(faded, 3)

    def test_goal_kick_rules_for_short_blocked_and_the_away_end(self):
        field = dict(sc.RULES["college-football"]["field"])
        t = self.tokens
        short = sc.goal_kick({"type": "Field Goal Missed", "text": "45 yard field goal is No Good, Short"}, 30.0, "home", field, t)
        self.assertEqual(short["result"], "short")
        self.assertLess(short["toX"], field["length"] + field["endZone"])
        self.assertIsNone(sc.goal_kick({"type": "Blocked Field Goal", "text": "BLOCKED"}, 30.0, "home", field, t))
        self.assertIsNone(sc.goal_kick({"type": "Punt", "text": ""}, 30.0, "home", field, t))
        away = sc.goal_kick({"type": "Field Goal Missed", "text": "No Good, Wide Right"}, 70.0, "away", field, t)
        # The away side attacks -x; facing -x the kicker's right is -z.
        self.assertLess(away["toX"], -field["endZone"])
        self.assertLess(away["lane"], -field["goalPostWidth"] / 2)
        xp = sc.goal_kick({"type": "Extra Point Good", "text": "extra point is GOOD"}, 85.0, "home", field, t)
        self.assertEqual((xp["lane"], xp["result"]), (0.0, "good"))

    def test_clock_records_are_never_drawn(self):
        for a in self.arcs(self.final):
            self.assertNotIn(a["type"].lower(), sc.NOT_A_PLAY)

    def test_styles_follow_the_play(self):
        by_type = {}
        for a in self.arcs(self.final):
            by_type.setdefault(a["type"], set()).add(a["style"])
        self.assertLessEqual(by_type["Pass Incompletion"], {"incomplete", "turnover"})
        self.assertIn("kick", by_type["Punt"])
        self.assertIn("score", by_type.get("Passing Touchdown", set())
                      | by_type.get("Rushing Touchdown", set()))
        self.assertEqual(by_type["Sack"], {"loss"})

    def test_durations_scale_with_speed_and_stay_in_bounds(self):
        motion = self.tokens["motion"]
        fast = SceneAt.at(REGULATION, 99999, speed=60.0)
        for slow_arc, fast_arc in zip(self.arcs(self.final), self.arcs(fast)):
            self.assertGreaterEqual(slow_arc["seconds"], motion["minSeconds"])
            self.assertLessEqual(slow_arc["seconds"], motion["maxSeconds"])
            self.assertEqual(slow_arc["duration"], slow_arc["seconds"])
            want = max(motion["floorSeconds"], slow_arc["seconds"] / (60 / motion["referenceSpeed"]))
            self.assertAlmostEqual(fast_arc["duration"], want, places=2)

    def test_x_is_fixed_to_the_field_not_to_possession(self):
        """Home attacks toward 100 whoever has the ball; an away drive's
        gains run toward 0."""
        s = self.final
        for d in s["drives"]:
            gains = [a for a in d["arcs"] if a["style"] in ("run", "pass")
                     and a["toX"] != a["fromX"] and a["side"] == d["side"]]
            for a in gains[:3]:
                forward = a["toX"] > a["fromX"]
                self.assertEqual(forward, d["side"] == "home", a["text"])

    def test_chips_are_in_the_band_and_carry_white_text(self):
        band = self.tokens["chip"]
        for ev in (REGULATION, OVERTIME, PICK_SIX):
            s = SceneAt.at(ev, 0)
            for side in ("home", "away"):
                team = s["teams"][side]
                self.assertAlmostEqual(sc.luminance(team["chip"]), band["luminance"],
                                       delta=0.006, msg=team)
                self.assertGreaterEqual(sc.contrast(team["chip"], "#FFFFFF"), 4.5)

    def test_navy_against_blue_gives_the_away_side_its_alternate(self):
        s = SceneAt.at(OVERTIME, 0)
        self.assertEqual((s["teams"]["home"]["abbr"], s["teams"]["away"]["abbr"]), ("SEA", "LAR"))
        self.assertFalse(sc.clash(s["teams"]["home"]["chip"], s["teams"]["away"]["chip"],
                                  self.tokens["chip"]))

    def test_league_rules(self):
        self.assertAlmostEqual(sc.RULES["nfl"]["field"]["hashFromSideline"], 23.583)
        self.assertEqual(sc.RULES["college-football"]["field"]["hashFromSideline"], 20.0)
        with self.assertRaises(ValueError):
            sc.build({}, league="rugby")

    def test_seats_sit_on_a_row_of_the_bowl_and_face_the_field(self):
        """1.1: every seat is on its tier's surface or on the field, looks at
        midfield, and the 1.0 `seat` is the default of them."""
        st = self.final["presentation"]["stadium"]
        seats = {s["id"]: s for s in st["seats"]}
        self.assertEqual(st["defaultSeat"], "club")
        self.assertEqual({k: st["seat"][k] for k in "xyz"}, {k: seats["club"][k] for k in "xyz"})
        # The look-dev shots sit in the first four; Experience adds presets
        # (tests/test_experience.py holds the rest of the list).
        self.assertLessEqual({"club", "field", "endzone", "upper"}, set(seats))
        tiers = {t["name"]: t for t in self.final["bowl"]["tiers"]}
        half_w, half_l = self.final["field"]["width"] / 2, 60.0
        for s in seats.values():
            # A seat in the bowl looks at midfield. A seat close in names its
            # own point instead - the camera well looks at the goal line it
            # sits behind - and the one look-dev preset looks out at the wall
            # it exists to shoot. Nothing may look into the stands.
            look = (s["lookAt"]["x"], s["lookAt"]["z"])
            if s.get("lookdev"):
                # A look-dev preset faces the thing it was added to judge - the
                # wall behind it, the goal line the ball crosses - rather than
                # midfield, and that thing is far enough away to be a view.
                far = math.hypot(look[0] - s["x"], look[1] - s["z"])
                self.assertGreater(far, 10.0, f"{s['id']} faces something a stride away")
                self.assertNotEqual(look, (50.0, 0.0), f"{s['id']} may as well be a bowl seat")
            elif s["view"]["distanceYards"] > 6:
                self.assertEqual(look, (50.0, 0.0))
            else:
                self.assertLessEqual(abs(look[1]), half_w, f"{s['id']} looks into the stands")
                self.assertTrue(-10.0 <= look[0] <= 110.0, f"{s['id']} looks off the field")
            if s["id"] == "pressBox":
                # Not on a tier: level with the press box glass.
                self.assertEqual(s["y"], self.final["bowl"]["pressBox"]["rise"][0])
                continue
            off = max(abs(s["z"]) - half_w, abs(s["x"] - 50) - half_l)
            tier = next((t for t in tiers.values() if t["inner"] <= off <= t["outer"]), None)
            if tier is None:
                self.assertEqual(s["y"], 0.0, s)
                self.assertLess(off, tiers["lower"]["inner"], s)
            else:
                f = (off - tier["inner"]) / (tier["outer"] - tier["inner"])
                want = tier["rise"][0] + (tier["rise"][1] - tier["rise"][0]) * f
                self.assertAlmostEqual(s["y"], want, places=2, msg=s)

    def test_a_celebration_is_held_for_the_scenes_own_seconds(self):
        """Clients hold a moment for motion.momentSeconds, not for a poll: at
        60x the server's moment is gone before the next frame."""
        held = self.final["motion"]["momentSeconds"]
        self.assertEqual(held, self.tokens["motion"]["momentSeconds"])
        self.assertGreaterEqual(held, 3.0)
        self.assertLessEqual(held, 10.0)

    def test_props_follow_the_league_and_look_names_real_assets(self):
        nfl = self.final["field"]["props"]
        self.assertEqual(nfl["benches"]["fromX"], 30.0)
        self.assertEqual(sc.RULES["college-football"]["props"]["benches"]["fromX"], 20.0)
        self.assertAlmostEqual(nfl["goalpost"]["crossbar"] * 3, 10.0, places=2)
        for key in ("goalpost", "pylon", "benches", "chains"):
            self.assertIn(nfl[key]["color"], self.final["palette"])
        for key in ("wall", "ribbon", "pressBox"):
            self.assertIn(key, self.final["bowl"])
        root = pathlib.Path(__file__).resolve().parents[1] / "assets"
        actors = {"experience", "field", "sideline", "bowl", "crowd", "lighting", "sky",
                  "broadcast", "moments", "audio"}
        self.assertEqual(set(self.final["visual"]) - {"about"}, actors,
                         "visual has one section per stadium actor (docs/ART_BIBLE.md)")
        for actor, section in self.final["visual"].items():
            if not isinstance(section, dict):
                continue
            for name, rel in section.get("assets", {}).items():
                self.assertTrue((root / rel).is_file(),
                                f"{actor}.{name}: assets/{rel} is missing; run tools/make_assets.py")
                self.assertTrue(rel.startswith(("actors/", "generated/")),
                                f"{actor}.{name}: assets live under assets/actors/ or assets/generated/")

    def test_the_sideline_follows_each_rulebook(self):
        """Team areas and upright heights come from the 2026 books, not from
        what looked right: NFL benches between the 30s and uprights 35 ft
        above the bar; college team areas between the 20s and 30 ft uprights.
        Both books put the bar 10 ft up and the uprights 18 ft 6 in apart."""
        nfl, ncaa = sc.RULES["nfl"], sc.RULES["college-football"]
        self.assertEqual((nfl["props"]["benches"]["fromX"], nfl["props"]["benches"]["toX"]), (30.0, 70.0))
        self.assertEqual((ncaa["props"]["benches"]["fromX"], ncaa["props"]["benches"]["toX"]), (20.0, 80.0))
        self.assertAlmostEqual(nfl["props"]["goalpost"]["uprightAbove"] * 3, 35.0, places=3)
        self.assertAlmostEqual(ncaa["props"]["goalpost"]["uprightAbove"] * 3, 30.0, places=3)
        for rules in (nfl, ncaa):
            self.assertAlmostEqual(rules["props"]["goalpost"]["crossbar"] * 3, 10.0, places=2)
            self.assertAlmostEqual(rules["field"]["goalPostWidth"] * 36, 222.0, delta=0.1)
            # symmetric about midfield, which the half-canvas paint relies on
            b = rules["props"]["benches"]
            self.assertAlmostEqual(b["fromX"] + b["toX"], 100.0)

    def test_end_zone_names_fit_their_clearance_and_read_the_right_way(self):
        """Each club's name sits inside its end zone four feet clear of every
        line (NCAA 1-2-1-d), and reads un-mirrored from the field of play with
        its tops toward the end line. The glyph layout a client applies is
        checked here, corner by corner, so no client has to trust it."""
        import json as _json
        art = self.final["field"]["art"]
        self.assertIsNotNone(art, "assets/actors/field/fonts/glyphs.json is missing")
        font = _json.loads((pathlib.Path(sc.__file__).resolve().parent.parent / "assets" / art["glyphs"]).read_text())
        f = self.final["field"]
        clear, gl = 4 / 3, 8 / 36
        for z in art["endZones"]:
            width = sc.text_width(z["text"], font, art["tracking"])
            (ox, oz), (ax, az), (ux, uz), cap = z["origin"], z["along"], z["up"], z["capHeight"]
            corners = [(ox + (a * ax + b * ux) * cap, oz + (a * az + b * uz) * cap)
                       for a in (0, width) for b in (0, 1)]
            if z["side"] == "home":
                lo, hi = -f["endZone"] + clear, -gl - clear
            else:
                lo, hi = f["length"] + gl + clear, f["length"] + f["endZone"] - clear
            for x, zz in corners:
                self.assertGreaterEqual(x, lo - 1e-6)
                self.assertLessEqual(x, hi + 1e-6)
                self.assertLessEqual(abs(zz), f["width"] / 2 - clear + 1e-6)
            # un-mirrored seen from above: along x up has the orientation of
            # the viewer's right x forward, which is -1 in (x, z)
            self.assertAlmostEqual(ax * uz - az * ux, -1.0)
            # tops toward the end line
            self.assertEqual(ux, -1.0 if z["side"] == "home" else 1.0)
        mid = art["midfield"]
        self.assertEqual(mid["center"], [50.0, 0.0])
        self.assertLess(mid["inner"], mid["outer"])
        self.assertLessEqual(mid["outer"], f["width"] / 2 - 15.0 + 1e-6, "NFL midfield art stays inside the numerals")

    def test_field_and_sideline_shader_graphs_are_wired_to_their_tokens(self):
        """The paint and net graphs are named from visual.field and
        visual.sideline, compiled, and every scalar or colour input a graph
        declares is a parameter the tokens set - so a port reimplementing the
        graph has every number the headset used. Texture inputs are set at
        runtime from assets the actor names."""
        import re
        root = pathlib.Path(sc.__file__).resolve().parent.parent
        mats = self.final["shaderGraph"]["materials"]
        for actor, key, usda in (("field", "paintMaterial", "Field.rkassets/FieldPaint.usda"),
                                 ("sideline", "netMaterial", "Sideline.rkassets/NetFresnel.usda"),
                                 ("field", "shells.material", "Shells.rkassets/FieldShells.usda"),
                                 ("field", "turfMaterial", "Turf.rkassets/TurfSheen.usda")):
            section = self.final["visual"][actor]
            for part in key.split(".")[:-1]:
                section = section[part]
            entry = mats[section[key.split(".")[-1]]]
            self.assertTrue((root / "assets" / entry["file"]).is_file(), f"{entry['file']}: run tools/blender/field/shadergraph/build.py")
            for k in ("blend", "color", "opacity"):
                self.assertIn(k, entry["fallback"])
            src = (root / "tools/blender/field/shadergraph" / usda).read_text()
            # the material's own inputs sit at eight spaces; node inputs are deeper
            declared = set(re.findall(r"^ {8}(?:float|color3f) inputs:(\w+) =", src, re.M))
            runtime = ({"Color", "UseMask", "Roughness", "BorderColor", "BorderRoughness", "BorderGrassCut",
                        "HalfWidth", "HalfLength"} if key == "paintMaterial" else
                       {"PatchX0", "PatchX1", "PatchZ0", "PatchZ1", "PatchFade"} if key == "shells.material" else
                       {"Tint", "Roughness", "Sheen"} if key == "turfMaterial" else
                       {"FaceOpacity", "GrazingOpacity"})
            self.assertEqual(declared - set(entry["parameters"]) - runtime, set(), f"{usda} inputs the tokens do not set")
            self.assertTrue(entry["prim"].endswith("/" + usda.split("/")[-1][:-5]))
        shells = self.final["visual"]["field"]["shells"]
        self.assertTrue((root / "assets" / shells["atlas"]).is_file())
        self.assertTrue(0 <= shells["firstLayer"] <= shells["lastLayer"] <= 7, "the atlas holds eight layers")
        for name, rel in self.final["visual"]["field"]["shaderTextures"].items():
            tex = root / "assets" / rel
            self.assertTrue(tex.is_file(), name)
            self.assertLess(tex.stat().st_size, 4_000_000, name)
        turf = self.final["visual"]["field"]["turf"]
        self.assertEqual(len(turf["stripeSheen"]), len(turf["stripeTint"]), "a sheen per stripe")

    def test_the_boundary_is_as_wide_as_each_book_says(self):
        """NFL: a solid white border six feet (two yards) wide outside the
        sidelines and end lines (2026 Rule 1 §1 Art.2). NCAA: a 4-inch
        sideline (1-2-1-a). Measured off the baked markings, not the table."""
        import json as _json
        root = pathlib.Path(sc.__file__).resolve().parent.parent / "assets" / "actors" / "field" / "markings"
        for league, kind, width in (("nfl", "border", 2.0), ("college-football", "sideline", 4 / 36)):
            prims = _json.loads((root / league / "markings.json").read_text())["primitives"]
            near = [q for q in prims if q["kind"] == kind and max(y for _, y in q["poly"]) <= 1e-6]
            self.assertTrue(near, f"{league}: no near {kind}")
            ys = [y for q in near for _, y in q["poly"]]
            self.assertAlmostEqual(max(ys) - min(ys), width, places=3, msg=league)

    def test_a_net_is_visible_face_on(self):
        """Behind the goal a net faces the eye, and a real one reads there as
        a mesh of cords: it keeps a face-on minimum and only fades edge-on."""
        net = self.final["visual"]["sideline"]["net"]
        self.assertGreaterEqual(net["minOpacity"], 0.35)
        self.assertLess(net["grazingOpacity"], net["minOpacity"])

    def test_a_net_is_cord_and_air_not_a_sheet(self):
        """From behind the posts you watch the game *through* the net, so what
        keeps it visible must be the cord, not the sheet.

        A cord is near-opaque and thin; the air between cords is most of the
        net. So the face-on opacity is the *cord's*, and the veil the net lays
        over the field is that times the mask's own coverage - which is what
        a mip converges to at the far posts. Gaining the mask to keep a distant
        net alive instead fattens every near cord into a band, which is how
        this read as a grid across the whole field through integration-13.
        """
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))
        from crowd_pixels import read_png

        net = self.final["visual"]["sideline"]["net"]
        gain = self.final["shaderGraph"]["materials"]["netFresnel"]["parameters"]["CordGain"]
        mask = (pathlib.Path(__file__).resolve().parents[1]
                / "assets" / "actors" / "sideline" / "textures" / "net_mask.png")
        w, h, rows = read_png(mask)
        coverage = sum(r[i] for r in rows for i in range(0, len(r), 3)) / (w * h) / 255

        # real netting: a few per cent of cord, the rest air
        self.assertLess(coverage, 0.12, "the mask itself is more cord than net")
        # a cord reads as cord, not as a translucent band
        self.assertGreaterEqual(net["minOpacity"], 0.6)
        # and is never smeared wider than it was authored
        self.assertLessEqual(gain, 1.0, "CordGain fattens near cords into a grid")
        # so the veil over the field stays a haze at any distance
        self.assertLessEqual(coverage * gain * net["minOpacity"], 0.10)

    def test_every_prop_mesh_the_stadium_can_ask_for_is_declared(self):
        """A model id the tokens do not declare loads as nothing, and a prop
        that loads as nothing is simply absent - no error, no warning.

        This round moved the team-area dressing to LOD1 in the stadium and
        every one of those props vanished, because `models` declared each
        prop's full mesh and its `_lod2` and never its `_lod1`. It showed up
        as the sideline shedding half its triangles, which is the only reason
        anyone looked. Declare what can be asked for.
        """
        S = self.final["visual"]["sideline"]
        models, lod = S["models"], S["lodSuffix"]
        wanted = {p + lod["stadium"] for p in _prop_ids(S)}
        wanted |= {p + lod["tabletop"] for p in _prop_ids(S)}
        wanted |= {p + suffix for p, suffix in (lod.get("stadiumByModel") or {}).items()}
        missing = sorted(w for w in wanted if w not in models)
        self.assertEqual([], missing, f"asked for but never declared: {missing}")

        root = pathlib.Path(__file__).resolve().parents[1] / "assets"
        absent = sorted(k for k, v in models.items() if not (root / v).exists())
        self.assertEqual([], absent, f"declared but not on disk: {absent}")

    def test_field_paint_is_paint_not_white(self):
        """Pure white albedo blows out under the floods, and grey paint reads
        as concrete. Lines sit at chalky field-paint albedo (0.80-0.88 sRGB)
        and the border a touch below them, still off-white (0.75-0.85). The
        border is duller than any grass so it never catches a specular
        highlight, and lets more grass through."""
        def srgb(h):
            h = h.lstrip("#")
            return [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
        p = self.final["visual"]["field"]["paint"]
        for key, lo, hi in (("white", 0.80, 0.88), ("border", 0.75, 0.85)):
            for ch in srgb(p[key]):
                self.assertGreaterEqual(ch, lo, key)
                self.assertLessEqual(ch, hi, key)
        self.assertLessEqual(max(srgb(p["border"])), max(srgb(p["white"])))
        turf = self.final["visual"]["field"]["turf"]
        self.assertGreaterEqual(p["borderRoughness"], max(turf["stripeRoughness"]))
        # a blade shows where it stands above the cut, so a lower cut lets more through
        self.assertLess(p["borderGrassCut"], self.final["shaderGraph"]["materials"]["fieldPaint"]["parameters"]["GrassCut"])

    def test_pylons_stand_where_each_book_puts_them(self):
        """NFL: the four goal-line corners and two on each end line at the
        hashes. College adds the end-line corners and sets the hash pylons
        three feet off the end line (1-2-6)."""
        for league, count in (("nfl", 8), ("college-football", 12)):
            rules = sc.RULES[league]
            spots = sc.pylon_spots(rules["field"], league, rules["props"]["pylon"]["size"])
            self.assertEqual(len(spots), count, league)
            self.assertEqual(len({tuple(s) for s in spots}), count)
            # symmetric under a half turn about midfield
            turned = {(round(100 - x, 3), round(-z, 3)) for x, z in spots}
            self.assertEqual(turned, {(round(x, 3), round(z, 3)) for x, z in spots})
        self.assertEqual(len(self.final["field"]["props"]["pylon"]["at"]), 8)

    def test_every_look_field_the_renderer_reads_is_in_the_tokens(self):
        """The visionOS renderer may only read appearance through SceneLook.swift.
        Every `let` there must be a key the tokens carry under `look`, so no
        renderer-facing number lives only in Swift and every port can reach it."""
        import re

        root = pathlib.Path(__file__).resolve().parents[1]
        stadium = root / "apple/FantasyEdge/Sources/Stadium"
        files = [stadium / "SceneLook.swift"] + sorted(stadium.glob("Actors/*/*Look.swift"))
        self.assertEqual(len(files), 11, "SceneLook.swift plus one <Actor>Look.swift per actor")
        swift = set()
        for f in files:
            block = f.read_text().split("// LOOK-BEGIN", 1)[1].split("// LOOK-END", 1)[0]
            swift |= set(re.findall(r"public let (\w+):", block))
        swift -= {"stadium", "tabletop"}

        def keys(node):
            out = set()
            if isinstance(node, dict):
                for k, v in node.items():
                    out.add(k)
                    out |= keys(v)
            elif isinstance(node, list):
                for v in node:
                    out |= keys(v)
            return out

        carried = keys(self.final["visual"])
        self.assertTrue(swift, "no fields parsed from SceneLook.swift")
        self.assertEqual(swift - carried, set(),
                         "SceneLook.swift reads these but tokens.json visual does not carry them")

    def test_every_model_ships_for_every_client(self):
        """A model is authored once and exported twice: `.usdz` for the headset
        and a `.glb` beside it for the web and Android. Neither without the
        other, and every model a section names exists."""
        root = pathlib.Path(__file__).resolve().parents[1] / "assets"
        for f in list(root.rglob("*.usdz")) + list(root.rglob("*.glb")):
            twin = f.with_suffix(".glb" if f.suffix == ".usdz" else ".usdz")
            self.assertTrue(twin.is_file(), f"{f.relative_to(root)} has no {twin.suffix} twin")
        for actor, section in self.final["visual"].items():
            if isinstance(section, dict):
                for name, rel in section.get("models", {}).items():
                    self.assertTrue((root / rel).is_file(), f"{actor}.{name}: assets/{rel} is missing")
                    self.assertTrue(rel.endswith(".usdz"), f"{actor}.{name}: name the .usdz; the .glb rides beside it")

    def test_the_look_dev_shots_are_one_list(self):
        """The app's `-shot` names and the harness's must be the same set, so
        every specialist shoots exactly what the art bible lists."""
        import re
        import importlib.util

        root = pathlib.Path(__file__).resolve().parents[1]
        src = (root / "apple/FantasyEdge/Sources/Stadium/Actors/Experience/StadiumShots.swift").read_text()
        block = src.split("// SHOTS-BEGIN", 1)[1].split("// SHOTS-END", 1)[0]
        swift = set(re.findall(r'"([a-z-]+)": Shot\(', block))
        spec = importlib.util.spec_from_file_location("lookdev", root / "tools" / "lookdev.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.assertEqual(swift, set(mod.SHOTS))
        bible = (root / "docs" / "ART_BIBLE.md").read_text()
        for name in swift:
            self.assertIn(f"`{name}`", bible, f"docs/ART_BIBLE.md does not list the {name} shot")

    def test_the_module_imports_nothing_but_the_standard_library(self):
        tree = ast.parse(pathlib.Path(sc.__file__).read_text())
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                self.assertEqual(node.level, 0, "no relative imports: it must lift out whole")
                names.add((node.module or "").split(".")[0])
        self.assertLessEqual(names, set(sys.stdlib_module_names))


class TestTheFieldBelongsToTheHomeClub(unittest.TestCase):
    """A visiting club is not painted on someone else's field.

    Before this, the end zone the visitors defended was lettered with their
    name and painted in their colour, so a home game showed two clubs' fields
    stitched together. Both ends are the home club's now; the away side wears
    its colour in the stands, and on its own bench.
    """

    HOME = {"abbr": "MIN", "name": "Minnesota Vikings", "location": "Minnesota",
            "nickname": "Vikings", "color": "#4F2683", "id": "16"}
    AWAY = {"abbr": "CHI", "name": "Chicago Bears", "location": "Chicago",
            "nickname": "Bears", "color": "#0B162A", "id": "3"}

    def art(self, home=None, away=None, league="nfl"):
        built = sc.build({"home": home or self.HOME, "away": away or self.AWAY}, league=league)
        return built, built["field"]["art"]

    def test_both_end_zones_carry_the_home_club_and_never_the_visitors(self):
        built, art = self.art()
        self.assertEqual({z["side"] for z in art["endZones"]}, {"home", "away"},
                         "both ends are still drawn; `side` says which end, not whose it is")
        for z in art["endZones"]:
            self.assertEqual(z["fill"], "home", "the home club's paint at both ends")
        painted = " ".join(z["text"] for z in art["endZones"]) + " " + art["midfield"]["text"]["text"]
        for word in ("CHICAGO", "BEARS", "CHI"):
            self.assertNotIn(word, painted, f"the visiting club is painted on the grass: {painted!r}")
        for word in ("VIKINGS", "MINNESOTA"):
            self.assertIn(word, painted)
        self.assertEqual(art["midfield"]["tint"], "home")

    def test_swapping_home_and_away_swaps_the_whole_field(self):
        _, art = self.art(home=self.AWAY, away=self.HOME)
        painted = " ".join(z["text"] for z in art["endZones"])
        self.assertIn("BEARS", painted)
        self.assertNotIn("VIKINGS", painted)

    def test_one_cap_height_serves_both_ends(self):
        """A long word at one end must not letter it smaller than the other:
        the two ends of a real field match."""
        _, art = self.art()
        caps = {z["capHeight"] for z in art["endZones"]}
        self.assertEqual(len(caps), 1, f"end zones lettered at different sizes: {caps}")

    def test_a_club_that_states_only_one_name_letters_it_at_both_ends(self):
        """Lambeau paints PACKERS twice. Splitting a display name on its last
        word would invent "NOTRE DAME FIGHTING" and "IRISH", so it is not done."""
        _, art = self.art(home={"abbr": "ND", "name": "Notre Dame Fighting Irish", "color": "#0C2340"})
        texts = [z["text"] for z in art["endZones"]]
        self.assertEqual(texts, ["NOTRE DAME FIGHTING IRISH"] * 2)

    def test_the_longest_names_still_fit_their_end_zone(self):
        """The fit is checked at the lengths that break it, not at a short one."""
        font = sc._glyphs()
        self.assertIsNotNone(font)
        for name in ("Jacksonville Jaguars", "New England Patriots", "Tampa Bay Buccaneers",
                     "Washington Commanders", "Notre Dame Fighting Irish",
                     "Southern Mississippi Golden Eagles"):
            built, art = self.art(home={"abbr": "XX", "name": name, "color": "#4F2683"})
            f = built["field"]
            clear, gl = 4 / 3, 8 / 36
            for z in art["endZones"]:
                width = sc.text_width(z["text"], font, art["tracking"])
                self.assertGreater(width, 0, name)
                (ox, oz), (ax, az), (ux, uz), cap = z["origin"], z["along"], z["up"], z["capHeight"]
                self.assertGreater(cap, 0.5, f"{name} lettered too small to read: {cap}")
                for a in (0, width):
                    for b in (0, 1):
                        x = ox + (a * ax + b * ux) * cap
                        zz = oz + (a * az + b * uz) * cap
                        lo, hi = ((-f["endZone"] + clear, -gl - clear) if z["side"] == "home"
                                  else (f["length"] + gl + clear, f["length"] + f["endZone"] - clear))
                        self.assertGreaterEqual(x, lo - 1e-6, name)
                        self.assertLessEqual(x, hi + 1e-6, name)
                        self.assertLessEqual(abs(zz), f["width"] / 2 - clear + 1e-6, name)

    def test_white_lettering_reads_on_every_club_colour(self):
        """End-zone paint is the club's chip, which is solved to a luminance
        band, so white letters clear WCAG *body* text on any hue - not merely
        the 3:1 they would need as large text. Swept at 18 cubed samples the
        worst any hue reaches is 4.96:1, so 4.5 is the bar. Tested by sweeping
        rather than by club, because the club list is ESPN's and is not in
        this repository."""
        band = sc.load_tokens()["chip"]
        hexes = [f"#{r:02X}{g:02X}{b:02X}" for r, g, b in
                 [(255, 0, 0), (255, 255, 0), (0, 255, 0), (0, 255, 255), (0, 0, 255),
                  (255, 0, 255), (255, 255, 255), (0, 0, 0), (128, 128, 128),
                  (11, 22, 42), (79, 38, 131), (0, 53, 148), (200, 16, 46)]]
        worst = min(((sc.contrast("#FFFFFF", sc.chip(h, band)), h) for h in hexes))
        self.assertGreaterEqual(worst[0], 4.5, f"white letters fail on {worst[1]} at {worst[0]:.2f}:1")

    def test_the_end_zone_reads_against_the_grass_it_is_painted_on(self):
        """A chip laid over turf at the paint's opacity has to be seen as a
        different surface from the field of play.

        Measured as colour distance, not luminance contrast: the chip band
        solves every club to one luminance, so a WCAG ratio is near 1 by
        construction and says nothing. CIE76 dE 2.3 is one just-noticeable
        difference; the hardest real case is a green club on green grass, and
        a swept sample bottoms out at dE 12 (a Jets green at 12.2), so 10 is
        the floor here - comfortably above a JND, just under the worst case
        the palette actually produces.
        """
        import importlib.util

        root = pathlib.Path(__file__).resolve().parents[1]
        spec = importlib.util.spec_from_file_location("contrast_check", root / "apple" / "contrast_check.py")
        cc = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cc)
        tokens = sc.load_tokens()
        band, paint = tokens["chip"], tokens["visual"]["field"]["paint"]
        turf = sc._rgb(tokens["color"]["turf.a"])
        opacity = paint["endZoneOpacity"]
        for hexs in ("#4F2683", "#0B162A", "#125740", "#203731", "#69BE28",
                     "#004C54", "#FFFFFF", "#F0BE00", "#000000"):
            over = tuple(opacity * c + (1 - opacity) * t
                         for c, t in zip(sc._rgb(sc.chip(hexs, band)), turf))
            self.assertGreaterEqual(cc.delta_e(over, turf), 10.0,
                                    f"a {hexs} end zone vanishes into the grass")


class TestTokensHaveOneSource(unittest.TestCase):

    def test_the_css_is_a_current_rendering_of_the_json(self):
        import importlib.util

        root = pathlib.Path(__file__).resolve().parents[1]
        spec = importlib.util.spec_from_file_location("make_tokens", root / "tools" / "make_tokens.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.assertEqual(mod.CSS.read_text(), mod.render(sc.load_tokens()),
                         "run python3 tools/make_tokens.py")

    def test_every_token_on_the_turf_or_under_text_passes_contrast(self):
        import contextlib
        import importlib.util

        root = pathlib.Path(__file__).resolve().parents[1]
        spec = importlib.util.spec_from_file_location("contrast_check", root / "apple" / "contrast_check.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(mod.check_tokens(), [])


class TestSceneMoments(unittest.TestCase):

    def test_the_overtime_winner_is_the_last_moment_and_no_phantom_follows(self):
        """ESPN's records after the touchdown dip back to the pre-conversion
        score and climb again at End of Game; that is not a second score."""
        s = SceneAt.at(OVERTIME, 4007)
        last = s["moments"][-1]
        self.assertEqual((last["kind"], last["side"], last["team"]), ("touchdown", "home", "SEA"))
        self.assertEqual((last["period"], last["clock"], last["points"]), (5, "3:13", 8.0))
        self.assertEqual(s["activeMoment"]["playId"], last["playId"])
        self.assertEqual(s["bowl"]["sectionTint"]["side"], "home")
        self.assertIsNone(s["ball"], "nobody has the ball after the whistle")

    def test_a_pick_six_lights_the_defence_not_the_offence(self):
        summary = game(PICK_SIX)["summary"]
        snap = play_second(summary, "INTERCEPTED by N.Wright")
        s = SceneAt.at(PICK_SIX, snap)
        m = s["activeMoment"]
        self.assertEqual((m["kind"], m["side"], m["team"]), ("touchdown", "home", "CHI"))
        arc = next(a for d in s["drives"] for a in d["arcs"] if a["id"] == m["playId"])
        shown = s["drives"][s["currentDrive"]]
        self.assertIn(m["playId"], [a["id"] for a in shown["arcs"]],
                      "under a TOUCHDOWN banner the scoring drive is shown, not the kickoff after it")
        self.assertEqual(arc["style"], "score")
        self.assertEqual(arc["side"], "away", "Minnesota snapped it")
        self.assertEqual((arc["fromX"], arc["toX"]), (32.0, 100.0))
        self.assertEqual(s["bowl"]["sectionTint"], {"side": "home",
                                                    "color": s["teams"]["home"]["chip"],
                                                    "dim": 0.28})
        self.assertEqual(s["ball"]["beacon"]["color"], "beacon.score")
        # 1.1: the moment says it celebrates and where: Chicago is home, and
        # home attacks x = 100, so the effects anchor in the 100..110 end zone
        # the pick-six was returned into.
        self.assertTrue(m["celebrates"])
        self.assertEqual(m["anchor"], {"x": 105.0, "y": 0.0, "z": 0.0})
        self.assertTrue(all(x["celebrates"] == (x["kind"] != "turnover") for x in s["moments"]
                            if x["kind"] in ("touchdown", "turnover")))

    def test_a_moment_holds_until_the_clock_moves(self):
        summary = game(PICK_SIX)["summary"]
        snap = play_second(summary, "INTERCEPTED by N.Wright")
        self.assertIsNotNone(SceneAt.at(PICK_SIX, snap + 5)["activeMoment"])
        later = SceneAt.at(PICK_SIX, snap + 30)
        self.assertIsNone(later["activeMoment"])
        self.assertIsNone(later["bowl"]["sectionTint"]["side"])

    def test_a_turnover_is_a_moment_for_the_side_that_took_it(self):
        s = SceneAt.at(OVERTIME, 4007)
        turnovers = [m for m in s["moments"] if m["kind"] == "turnover"]
        self.assertTrue(turnovers)
        for m in turnovers:
            self.assertIn(m["side"], ("home", "away"))
            self.assertEqual(m["points"], 0)

    def test_lasers_point_the_way_the_offence_is_going(self):
        for ev in (REGULATION, OVERTIME):
            for at in range(300, 3500, 400):
                s = SceneAt.at(ev, at)
                lasers = {l["kind"]: l["x"] for l in s["lasers"]}
                if "lineToGain" not in lasers:
                    continue
                step = lasers["lineToGain"] - lasers["scrimmage"]
                self.assertAlmostEqual(abs(step), s["status"]["distance"])
                self.assertEqual(step > 0, s["status"]["possession"] == "home", (ev, at))


if __name__ == "__main__":
    unittest.main()
