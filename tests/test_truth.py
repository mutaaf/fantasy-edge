"""Correcting a play with what the NFL published about it.

ESPN says where a play started and ended. It never says where the ball was
*caught*, so a live scene guesses, and the guess is wrong by the yards after
the catch - on a Stafford completion in 401772949, by 27 yards of where the
ball came down. nflverse states it, so a finished game can be drawn from what
happened.

Stated against the three real games already captured as fixtures, and their
published play-by-play beside them, never a hand-made pair:

  401772510  DAL 20 @ PHI 24    2025_01_DAL_PHI
  401772810  MIN 24 @ CHI 27    2025_01_MIN_CHI
  401772949  LAR 37 @ SEA 38    2025_16_LA_SEA

No network: the rows are cut by `tools/make_replay_fixture.py --nflverse`.
"""

from __future__ import annotations

import json
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from fantasyedge import scene as sc                           # noqa: E402
from fantasyedge import truth                                 # noqa: E402

FIX = pathlib.Path(__file__).parent / "fixtures"
EVENTS = ("401772510", "401772810", "401772949")


def shaped(summary: dict) -> list[dict]:
    """The plays as `api.gamecast` shapes them, which is what a scene reads."""
    out = []
    for drive in (summary.get("drives") or {}).get("previous") or []:
        for p in (drive.get("plays") or []):
            st, en = p.get("start") or {}, p.get("end") or {}
            out.append({
                "id": str(p.get("id") or ""),
                "type": (p.get("type") or {}).get("text", ""),
                "text": p.get("text") or "",
                "yards": p.get("statYardage"),
                "period": (p.get("period") or {}).get("number", 0),
                "clock": (p.get("clock") or {}).get("displayValue", ""),
                "down": st.get("down"), "distance": st.get("distance"),
                "from": st.get("yardsToEndzone"), "to": en.get("yardsToEndzone"),
                "fromYard": st.get("yardLine"), "toYard": en.get("yardLine"),
                "scoring": bool(p.get("scoringPlay")),
                "turnover": bool(p.get("isTurnover")),
                "penalty": bool(p.get("isPenalty")),
            })
    return out


_CACHE: dict = {}


def game(event: str) -> tuple[list[dict], list[dict]]:
    """(the plays a scene draws, the published rows) for one event."""
    if event not in _CACHE:
        summary = json.loads((FIX / f"replay_game_{event}.json").read_text())["summary"]
        rows = json.loads((FIX / f"nflverse_pbp_{event}.json").read_text())["plays"]
        _CACHE[event] = ([p for p in shaped(summary) if sc.style_of(p)], rows)
    return _CACHE[event]


class TheGameBridge(unittest.TestCase):
    """nflverse publishes ESPN's id, so a game is joined rather than guessed."""

    def test_every_fixture_names_the_game_it_came_from(self):
        for event in EVENTS:
            blob = json.loads((FIX / f"nflverse_pbp_{event}.json").read_text())
            self.assertEqual(blob["event"], event)
            self.assertRegex(blob["gameId"], r"^\d{4}_\d{2}_[A-Z]{2,3}_[A-Z]{2,3}$")
            self.assertIn("play_by_play", blob["source"])


class TheIdentityRule(unittest.TestCase):
    """No play id is shared, so a play is matched on what it says about itself."""

    def test_nearly_every_drawn_play_finds_its_row(self):
        for event in EVENTS:
            plays, rows = game(event)
            paired = truth.match(plays, rows)
            rate = 100.0 * len(paired) / len(plays)
            self.assertGreater(rate, 97.0, f"{event}: only {rate:.1f}% matched")

    def test_a_row_is_never_used_twice(self):
        for event in EVENTS:
            plays, rows = game(event)
            paired = truth.match(plays, rows)
            ids = [str(r.get("play_id")) for r in paired.values()]
            self.assertEqual(len(ids), len(set(ids)), f"{event}: a row was matched twice")

    def test_an_exact_match_is_never_stolen_by_a_weaker_one(self):
        """The first-quarter touchdown in 401772510 has a row three seconds
        away that a single greedy sweep gave to an earlier play."""
        plays, rows = game("401772510")
        td = next(p for p in plays if "J.Williams left guard for 1 yard" in p["text"])
        row = truth.match(plays, rows).get(td["id"])
        self.assertIsNotNone(row, "the touchdown lost its row")
        self.assertEqual(truth._i(row["yardline_100"]), 1)
        self.assertEqual(truth._i(row["touchdown"]), 1)

    def test_a_drifted_clock_past_tolerance_is_refused(self):
        """A wrong correction draws one play's ball on another play's path,
        so a match that needs too much clock drift is not made at all."""
        plays, rows = game("401772810")
        one = [p for p in plays if p["down"] and "pass" in p["type"].lower()][3]
        far = dict(one, id="synthetic", period=1, clock="00:01")
        self.assertNotIn("synthetic", truth.match([far], rows, tolerance=2))

    def test_special_teams_are_matched_without_their_spot(self):
        """The two sources mean different things by a kickoff's spot: ESPN
        gives 65 yards to the end zone, nflverse the 35 it was kicked from."""
        plays, rows = game("401772810")
        paired = truth.match(plays, rows)
        kicks = [p for p in plays if p["type"] == "Kickoff"]
        self.assertTrue(kicks)
        for k in kicks:
            row = paired.get(k["id"])
            self.assertIsNotNone(row, "a kickoff went unmatched")
            self.assertEqual(truth._kind(row), "kickoff")


class WhatTheCorrectionSays(unittest.TestCase):

    def test_a_corrected_play_carries_its_provenance(self):
        plays, rows = game("401772949")
        fixed = truth.correct(plays, rows, event="401772949")
        self.assertEqual(len(fixed), len(plays))
        for p in fixed:
            t = p["truth"]
            self.assertIn(t["source"], ("live", "corrected"))
            self.assertEqual(t["event"], "401772949")
            # Lateral placement is nobody's measurement, on either source.
            self.assertIn("lane", t["estimated"])
            if t["source"] == "corrected":
                self.assertTrue(t["fields"])
                self.assertTrue(t["gameId"])

    def test_an_uncovered_game_is_a_live_estimate_not_an_error(self):
        plays, _ = game("401772510")
        fixed = truth.correct(plays, [], event="401772510")
        self.assertEqual(len(fixed), len(plays))
        self.assertTrue(all(p["truth"]["source"] == "live" for p in fixed))

    def test_correcting_does_not_touch_the_plays_it_was_given(self):
        plays, rows = game("401772810")
        before = json.dumps(plays, sort_keys=True)
        truth.correct(plays, rows, event="401772810")
        self.assertEqual(before, json.dumps(plays, sort_keys=True))

    def test_provenance_survives_into_the_scene(self):
        """A client is told which plays are drawn from what happened."""
        plays, rows = game("401772810")
        fixed = truth.correct(plays, rows, event="401772810")
        by_id = {p["id"]: p for p in fixed}
        game_blob = json.loads((FIX / "replay_game_401772810.json").read_text())
        spec = sc.build({**_gamecast(game_blob), "drives": _corrected_drives(game_blob, by_id)})
        arcs = [a for d in spec["drives"] for a in d["arcs"]]
        self.assertTrue(arcs)
        self.assertTrue(any(a["source"] == "corrected" for a in arcs))
        for a in arcs:
            self.assertIn(a["source"], ("live", "corrected"))
            if a["source"] == "corrected":
                self.assertTrue(a["corrected"])


class WhereTheBallWasCaught(unittest.TestCase):
    """The number ESPN never states, and the whole point of correcting."""

    def test_the_estimate_is_wrong_by_the_yards_after_the_catch(self):
        for event in EVENTS:
            plays, rows = game(event)
            before = truth.compare(plays, rows, estimate_air=sc.air_yards)
            self.assertGreater(before["airYards"]["n"], 40)
            self.assertGreater(before["airYards"]["mean"], 3.0,
                               f"{event}: the estimate was better than expected")

    def test_a_corrected_play_flies_to_where_the_ball_was_caught(self):
        for event in EVENTS:
            plays, rows = game(event)
            fixed = truth.correct(plays, rows, event=event)
            after = truth.compare(fixed, rows, estimate_air=sc.air_yards)
            self.assertEqual(after["airYards"]["worst"], 0.0,
                             f"{event}: a corrected play still guessed the catch")

    def test_the_catch_moves_and_the_throw_flattens(self):
        """Stafford to Nacua, 54 yards: 19 of them thrown, 35 run after it.
        The estimate threw it 45.9 and arced three times as high."""
        plays, rows = game("401772949")
        fixed = truth.correct(plays, rows, event="401772949")
        text = "M.Stafford pass deep middle to P.Nacua"
        live = next(p for p in plays if text in p["text"])
        done = next(p for p in fixed if text in p["text"])
        self.assertAlmostEqual(done["airYards"], 19.0, places=1)
        self.assertAlmostEqual(done["yacYards"], 35.0, places=1)
        self.assertGreater(sc.air_yards(live) - sc.air_yards(done), 20.0)

        def thrown(play):
            style, shape = sc.style_of(play)
            path = sc.play_path(play, style, shape, float(play["fromYard"]),
                                float(play["toYard"]), 0.0, "away", None,
                                dict(sc.RULES["nfl"]["field"]), {"abbr": "SEA"},
                                {"abbr": "LA"}, sc.load_tokens())
            air = [s for s in path["segments"] if s["kind"] == "air"][-1]
            return air["to"][0], air["rise"]

        live_x, live_rise = thrown(live)
        done_x, done_rise = thrown(done)
        self.assertGreater(abs(done_x - live_x), 20.0)
        self.assertLess(done_rise, live_rise / 2)

    def test_an_incompletion_is_thrown_where_it_was_aimed(self):
        """It ends the down back at the line, and the ball did not go there."""
        plays, rows = game("401772510")
        fixed = truth.correct(plays, rows, event="401772510")
        deep = [p for p in fixed
                if p["truth"]["source"] == "corrected" and "incomplete deep" in p["text"]
                and p.get("airYards") is not None]
        self.assertTrue(deep)
        for p in deep:
            self.assertAlmostEqual(sc.air_yards(p), p["airYards"], places=1)


class WhatIsStillEstimated(unittest.TestCase):

    def test_the_spots_already_agreed_so_nothing_is_claimed_for_them(self):
        """Correcting is worth it for the catch point, not the snap: on
        scrimmage plays the two sources already state the same yard line."""
        for event in EVENTS:
            plays, rows = game(event)
            rep = truth.compare(plays, rows, estimate_air=sc.air_yards)
            self.assertLess(rep["startSpot"]["mean"], 0.2, f"{event}: spots disagree")

    def test_the_two_sources_agree_on_what_kind_of_play_it_was(self):
        for event in EVENTS:
            plays, rows = game(event)
            rep = truth.compare(plays, rows, estimate_air=sc.air_yards)
            k = rep["playType"]
            rate = 100.0 * k["same"] / max(1, k["same"] + k["differ"])
            self.assertGreater(rate, 97.0, f"{event}: {k}")

    def test_lateral_placement_is_never_presented_as_measured(self):
        """Neither source tracks players, so where across the field a ball
        went is a layout on every play, corrected or not."""
        plays, rows = game("401772949")
        for p in truth.correct(plays, rows, event="401772949"):
            self.assertIn("lane", p["truth"]["estimated"])
            self.assertNotIn("lane", p["truth"]["fields"])


def _gamecast(blob: dict) -> dict:
    comp = blob["summary"]["header"]["competitions"][0]
    sides = {}
    for c in comp["competitors"]:
        t = c["team"]
        sides[c["homeAway"]] = {"id": str(t["id"]), "abbr": t["abbreviation"],
                               "name": t.get("displayName", ""),
                               "color": "#" + t.get("color", "444444"),
                               "altColor": "#" + t.get("alternateColor", "888888"),
                               "score": 0, "logo": ""}
    return {"home": sides["home"], "away": sides["away"], "situation": {}}


def _corrected_drives(blob: dict, by_id: dict) -> list[dict]:
    """The fixture's drives, with each play replaced by its corrected twin."""
    out = []
    ids = {str(c["team"]["id"]): c["team"]["abbreviation"]
           for c in blob["summary"]["header"]["competitions"][0]["competitors"]}
    for d in blob["summary"]["drives"]["previous"]:
        plays = []
        for p in (d.get("plays") or []):
            fixed = by_id.get(str(p.get("id")))
            if not fixed:
                continue
            st = p.get("start") or {}
            plays.append({**fixed,
                          "team": ids.get(str((st.get("team") or {}).get("id")), ""),
                          "home": p.get("homeScore"), "away": p.get("awayScore")})
        out.append({"id": str(d.get("id") or ""),
                    "team": (d.get("team") or {}).get("abbreviation", ""),
                    "result": d.get("displayResult") or "", "plays": plays})
    return out


if __name__ == "__main__":
    unittest.main()
