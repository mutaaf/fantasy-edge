"""Moments and Audio: the scene's beats, their choreography, and the sounds.

Fixture-driven like the rest of the scene suite: three whole 2025 games
replayed through the real API, no network. The contract every client builds
to is asserted here - which cues a game has, which one is playing, the
timeline a touchdown runs, and that every sound ships for every client at
the loudness it was designed.
"""

from __future__ import annotations

import json
import pathlib
import unittest

from fantasyedge import scene as sc
from tests import test_replay_scene as T

ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"


def setUpModule():
    T.setUpModule()


class _Final:
    _cache: dict = {}

    @classmethod
    def of(cls, event: str) -> dict:
        if event not in cls._cache:
            cls._cache[event] = T.SceneAt.at(event, 99999)
        return cls._cache[event]


class TestCues(unittest.TestCase):

    def kinds(self, s, kind):
        return [c for c in s["cues"] if c["kind"] == kind]

    def test_every_game_has_its_clock_beats_in_order(self):
        for ev in (T.REGULATION, T.PICK_SIX, T.OVERTIME):
            s = _Final.of(ev)
            self.assertEqual(len(self.kinds(s, "twoMinute")), 2, ev)
            self.assertEqual(len(self.kinds(s, "halfEnd")), 1, ev)
            self.assertEqual(len(self.kinds(s, "quarterEnd")), 2, ev)
            self.assertEqual(len(self.kinds(s, "final")), 1, ev)
            seq = [c["sequence"] for c in s["cues"]]
            self.assertEqual(seq, sorted(seq), "cues arrive in the order the game played them")
        self.assertEqual(len(self.kinds(_Final.of(T.OVERTIME), "regulationEnd")), 1)

    def test_the_final_says_who_won_and_is_the_cue_left_playing(self):
        expect = {T.REGULATION: ("home", "finalHomeWon"), T.PICK_SIX: ("away", "finalAwayWon"),
                  T.OVERTIME: ("home", "finalHomeWon")}
        for ev, (side, treatment) in expect.items():
            s = _Final.of(ev)
            final = self.kinds(s, "final")[0]
            h, a = s["teams"]["home"]["score"], s["teams"]["away"]["score"]
            self.assertEqual(side, "home" if h > a else "away")
            self.assertEqual((final["side"], final["treatment"]), (side, treatment))
            self.assertEqual(s["activeCue"]["id"], final["id"])

    def test_a_red_zone_cue_is_a_drawn_play_that_crosses_the_twenty_without_scoring(self):
        s = _Final.of(T.OVERTIME)
        arcs = {a["id"]: a for d in s["drives"] for a in d["arcs"]}
        crossings = self.kinds(s, "redZone")
        self.assertTrue(crossings)
        for c in crossings:
            a = arcs[c["playId"]]
            goal = s["field"]["length"] if c["side"] == "home" else 0.0
            self.assertGreater(abs(goal - a["fromX"]), sc.RED_ZONE)
            self.assertLessEqual(abs(goal - a["toX"]), sc.RED_ZONE)
            self.assertNotEqual(a["style"], "score")

    def test_third_down_is_a_home_crowd_cue_only_while_the_visitors_have_the_ball(self):
        seen = {"away": 0, "home": 0}
        for at in range(300, 3500, 40):
            s = T.SceneAt.at(T.REGULATION, at)
            st, cue = s["status"], s["activeCue"]
            if st["state"] != "in" or st["down"] != 3:
                continue
            seen[st["possession"]] += 1
            if st["possession"] == "away" and not (cue and cue["kind"] != "thirdDown"):
                self.assertEqual((cue["kind"], cue["side"]), ("thirdDown", "home"), at)
            if st["possession"] == "home":
                self.assertFalse(cue and cue["kind"] == "thirdDown", at)
            if seen["away"] >= 3 and seen["home"] >= 3:
                break
        self.assertGreater(seen["away"], 0)
        self.assertGreater(seen["home"], 0)

    def test_an_event_cue_holds_until_the_clock_moves(self):
        s = _Final.of(T.REGULATION)
        warning = self.kinds(s, "twoMinute")[0]
        summary = T.game(T.REGULATION)["summary"]
        second = T.play_second(summary, "Two-Minute Warning") if "Two-Minute" in json.dumps(summary) else None
        if second is None:
            self.skipTest("fixture text has no two-minute record to seek to")
        held = T.SceneAt.at(T.REGULATION, second)["activeCue"]
        self.assertIsNotNone(held)
        self.assertEqual(held["kind"], "twoMinute")
        self.assertEqual(held["period"], warning["period"])

    def test_every_cue_has_a_treatment_the_tokens_define(self):
        cues = sc.load_tokens()["visual"]["moments"]["cues"]
        for ev in (T.REGULATION, T.PICK_SIX, T.OVERTIME):
            for c in _Final.of(ev)["cues"]:
                self.assertIn(c["treatment"], cues, c)
                self.assertIn(c["source"], ("pa", "bowl", "standsHome", "standsAway"))
        self.assertIn("thirdDown", cues)


class TestCrowdCues(unittest.TestCase):

    def test_the_final_stands_the_winners_sections_and_sits_the_losers(self):
        for ev in (T.REGULATION, T.PICK_SIX, T.OVERTIME):
            s = _Final.of(ev)
            final = next(c for c in s["cues"] if c["kind"] == "final")
            fans = sc.fan_sections(s["bowl"])
            loser = "away" if final["side"] == "home" else "home"
            self.assertEqual(final["crowd"]["stand"], fans[final["side"]], ev)
            self.assertEqual(final["crowd"]["sit"], fans[loser], ev)

    def test_every_section_belongs_to_one_club_and_the_visitors_sit_where_the_scene_says(self):
        s = _Final.of(T.REGULATION)
        bowl = s["bowl"]
        fans = sc.fan_sections(bowl)
        every = [x["id"] for t in bowl["seating"]["tiers"] for x in t.get("sections", [])]
        self.assertEqual(sorted(fans["home"] + fans["away"]), sorted(every))
        self.assertTrue(fans["away"], "there is a visitors' section")
        self.assertGreater(len(fans["home"]), len(fans["away"]), "the home crowd outnumbers the visitors")
        self.assertEqual(bowl["crowd"]["awaySection"]["side"], "far")
        for tier in bowl["seating"]["tiers"]:
            for sec in tier.get("sections", []):
                if sec["id"] in fans["away"]:
                    self.assertNotEqual(sec["side"], "home", f"visitors sit across the field, not in {sec}")

    def test_crowd_durations_live_in_tokens(self):
        M = sc.load_tokens()["visual"]["moments"]
        t = M["timeline"]
        self.assertGreater(t["touchdown"]["standSeconds"], 0)
        self.assertGreater(t["fieldGoal"]["standSeconds"], 0)
        self.assertGreater(t["turnover"]["groanSeconds"], 0)
        self.assertGreater(t["turnover"]["standSeconds"], 0, "the side that took the ball jumps up")
        for kind, step in t.items():
            for key in ("standSeconds", "groanSeconds"):
                self.assertTrue(step[key] == -1 or 0 < step[key] <= sc.load_tokens()["motion"]["momentSeconds"] + 0.01,
                                (kind, key))
        self.assertEqual(M["cues"]["thirdDown"]["crowd"], "clap")
        self.assertEqual(M["cues"]["redZone"]["crowd"], "stand")
        for key in ("finalHomeWon", "finalAwayWon"):
            self.assertEqual(M["cues"][key]["crowd"], "final")
        for key, cue in M["cues"].items():
            self.assertIn(cue["crowd"], ("stand", "clap", "final", "none"), key)
            self.assertGreater(cue["seconds"], 0, key)


class TestMomentDetail(unittest.TestCase):

    def test_a_pick_six_says_interception_and_a_punt_return_says_so(self):
        pick = [m for m in _Final.of(T.PICK_SIX)["moments"] if m["kind"] == "touchdown"]
        self.assertIn("interception", [m["detail"] for m in pick])
        ot = _Final.of(T.OVERTIME)["moments"]
        self.assertIn("puntReturn", [m["detail"] for m in ot if m["kind"] == "touchdown"])

    def test_every_turnover_says_how_the_ball_changed_hands(self):
        for ev in (T.REGULATION, T.OVERTIME):
            for m in _Final.of(ev)["moments"]:
                if m["kind"] == "turnover":
                    self.assertIn(m["detail"], ("interception", "fumble"), m)


class TestChoreographyTokens(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tokens = sc.load_tokens()
        cls.M = cls.tokens["visual"]["moments"]

    def test_every_moment_that_celebrates_or_turns_over_has_a_timeline(self):
        for kind in self.M["celebrate"] + ["turnover"]:
            self.assertIn(kind, self.M["timeline"])
            self.assertIn(kind, self.M["burstFor"])

    def test_a_touchdown_runs_whistle_surge_strobe_particles_then_chime_inside_the_hold(self):
        t = self.M["timeline"]["touchdown"]
        order = [t["whistle"], t["surge"], t["strobe"], t["particles"], t["chime"], t["settle"]]
        self.assertTrue(all(x >= 0 for x in order))
        self.assertEqual(order, sorted(order))
        self.assertLessEqual(t["settle"], self.tokens["motion"]["momentSeconds"])
        self.assertLessEqual(t["strobe"] + t["strobeSeconds"], t["settle"])

    def test_steps_a_kind_skips_are_minus_one_and_the_rest_end_by_settle(self):
        for kind, t in self.M["timeline"].items():
            for step in ("whistle", "surge", "strobe", "particles", "banner", "chime"):
                self.assertTrue(t[step] == -1 or 0 <= t[step] < t["settle"], (kind, step))

    def test_bursts_named_anywhere_exist(self):
        names = set(self.M["bursts"]) | {"none"}
        for kind, burst in self.M["burstFor"].items():
            self.assertIn(burst, names, kind)
        for key, cue in self.M["cues"].items():
            self.assertIn(cue["burst"], names, key)
        for b in self.M["bursts"].values():
            self.assertGreater(b["shells"], 0)
            self.assertLessEqual(b["shells"] * b["birthRate"] * b["burstSeconds"], 12000,
                                 "a burst stays inside the 4k-live-particle budget at its lifespan")

    def test_the_banner_contract_dominates_and_leaves_before_the_hold_ends(self):
        b = self.M["banner"]
        self.assertGreaterEqual(b["widthDegrees"], 25, "the TOUCHDOWN should dominate, not be a chip")
        self.assertLessEqual(b["enterSeconds"] + b["dwellSeconds"] + b["exitSeconds"],
                             self.tokens["motion"]["momentSeconds"] + 0.01)
        self.assertEqual(set(b["kinds"]), set(self.M["celebrate"]))

    def test_reduce_motion_never_flashes_or_bursts(self):
        rm = self.M["reduceMotion"]
        self.assertFalse(rm["strobe"])
        self.assertFalse(rm["particles"])
        self.assertLess(rm["swellDb"], 0)


class TestSounds(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.A = sc.load_tokens()["visual"]["audio"]
        cls.manifest = json.loads((ASSETS / "actors/audio/manifest.json").read_text())

    def test_every_sound_ships_for_the_headset_and_for_every_other_client(self):
        for key, rel in self.A["assets"].items():
            caf = ASSETS / rel
            self.assertTrue(caf.is_file(), f"{rel}: run tools/audio/build.py")
            self.assertEqual(caf.suffix, ".caf")
            self.assertTrue(caf.with_suffix(".ogg").is_file(), f"{rel} has no .ogg twin for web/Android")
            self.assertIn(key, self.A["gains"], f"{key} has no level in the mix")

    def test_every_cue_and_moment_names_a_sound_that_exists(self):
        M = sc.load_tokens()["visual"]["moments"]
        for key, cue in M["cues"].items():
            self.assertTrue(cue["audio"] == "none" or cue["audio"] in self.A["assets"], key)
        for sound in ("whistle", "roar", "cheer", "sting", "groan", "chime", "fireworks"):
            self.assertIn(sound, self.A["assets"])

    def test_loudness_was_normalised_when_the_files_were_made(self):
        loud = self.A["loudness"]
        for name, s in self.manifest["sounds"].items():
            self.assertLessEqual(s["peak"], loud["peak"] + 0.05, name)
            target = loud["bedRms"] if s["class"] == "bed" else loud["effectRms"]
            self.assertAlmostEqual(s["rms"], target, delta=1.5, msg=name)
            self.assertEqual(s["loop"], s["class"] == "bed", name)

    def test_beds_loop_by_their_id_and_the_mix_has_headroom(self):
        beds = [k for k in self.A["assets"] if k.endswith("Bed")]
        for k in beds:
            self.assertTrue(self.manifest["sounds"][pathlib.Path(self.A["assets"][k]).stem]["loop"], k)
        stadium_beds = self.A["bedEmitters"] + (len(beds) - 1)
        self.assertLessEqual(stadium_beds + 4, self.A["maxSources"],
                             "beds leave room for a whistle, a roar, fireworks and a chime at once")
        self.assertLessEqual(max(self.A["gains"].values()) + self.A["masterGain"], 0.0)
        self.assertLess(self.A["tabletop"]["gain"], -12, "the tabletop is a miniature, not the stadium in the room")

    def test_audio_fits_its_budget(self):
        total = sum(f.stat().st_size for f in (ASSETS / "actors/audio").iterdir() if f.suffix in (".caf", ".ogg"))
        self.assertLess(total, 30 * 1024 * 1024)

    def test_every_sound_is_logged_as_original(self):
        text = (ASSETS / "LICENSES.md").read_text()
        self.assertIn("tools/audio/build.py", text)
        for name in self.manifest["sounds"]:
            self.assertIn(name, text)


if __name__ == "__main__":
    unittest.main()
