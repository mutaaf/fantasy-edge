"""Server-side text: ESPN's play shorthand made readable, and team short names.

Every input below is a real string from data/capture/2026-09-12; the first
test proves they are there, so a case cannot be invented to suit the cleaner.
"""
from __future__ import annotations

import pathlib
import re
import unittest

from cfb import text
from cfb.sources import _load

REPO = pathlib.Path(__file__).resolve().parents[1]
CAP = REPO / "data/capture/2026-09-12"
HAVE = (CAP / "final").is_dir()

RAW = re.compile(r"[#()]|clock \d|^(Shotgun|No Huddle|Pistol)|\b(1ST DOWN|TOUCHDOWN|NO GOOD|GOOD|KICK|PENALTY|NO PLAY|MISSED)\b")

CASES = [
    # the one the screenshot showed under the Big Game
    ("(C. Hawkins KICK)", "C. Hawkins kick"),
    ("(O. Carey PAT MISSED)", "O. Carey extra point missed"),
    ("(06:15) #5 K.Henderson pass complete short right to #2 K.Young caught at SU00, for 7 yards to the SU00 TOUCHDOWN, clock 06:10",
     "K. Henderson pass complete short right to K. Young caught at SU00, for 7 yards to the SU00 touchdown"),
    ("No Huddle-Shotgun #9 M.Vezza rush middle for 12 yards gain to the JAX11 (#7 M.Woods), 1ST DOWN",
     "M. Vezza rush middle for 12 yards gain to the JAX11, first down"),
    ("(05:01) #41 R.Culkin field goal attempt from 27 yards GOOD (H: #19 L.Droegemueller, LS: #45 B.Bergfeld), clock 04:59",
     "R. Culkin field goal attempt from 27 yards good"),
    ("(03:42) #41 C.Rogers field goal attempt from 54 yards NO GOOD (H: #91 R.Chandley, LS: #54 W.Adkinson), clock 03:37, End Of Play",
     "C. Rogers field goal attempt from 54 yards no good"),
    ("(11:27) #30 B.Bowman punt 42 yards to the FLA30 #1 V.Brown III return 70 yards to the CU00 TOUCHDOWN, clock 11:13 #91 P.Durkin kick attempt good (H: #38 A.Clark, LS: #54 L.Anderson)",
     "B. Bowman punt 42 yards to the FLA30 V. Brown III return 70 yards to the CU00 touchdown, P. Durkin kick attempt good"),
    ("Devon Dampier 7 Yd Run (Mana Carvalho Run for Two-Point Conversion)",
     "Devon Dampier 7-yd run, Mana Carvalho run for two-point conversion"),
    ("Andre Jordan Jr. 29 Yd Interception Return (Alex McPherson Kick)",
     "Andre Jordan Jr. 29-yd interception return, Alex McPherson kick"),
    ("Max Gilbert 29 Yd Field Goal  ", "Max Gilbert 29-yd field goal"),
    ("Timeout Texas, clock 01:38", "Timeout Texas"),
    ("End of 1st quarter.", "End of 1st quarter."),
]


class PlayText(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.seen: set[str] = set()
        if not HAVE:
            return
        files = sorted((CAP / "final").glob("*.json.gz")) + sorted((CAP / "scoreboard").glob("*.json.gz"))
        files += sorted((CAP / "live").glob("*/*.json.gz"))[::4]
        for f in files:
            if True:
                d = _load(f)
                for sp in d.get("scoringPlays") or []:
                    cls.seen.add((sp.get("text") or "").strip())
                for dr in (d.get("drives") or {}).get("previous") or []:
                    cls.seen.update((p.get("text") or "").strip() for p in dr.get("plays") or [])
                for ev in d.get("events") or []:
                    last = ((ev["competitions"][0].get("situation") or {}).get("lastPlay") or {}).get("text")
                    if last:
                        cls.seen.add(last.strip())

    @unittest.skipUnless(HAVE, "capture not present")
    def test_every_case_is_a_real_string(self):
        for raw, _ in CASES:
            self.assertIn(raw.strip(), self.seen, raw[:80])

    def test_cases(self):
        for raw, clean in CASES:
            self.assertEqual(text.play(raw), clean, raw)

    def test_idempotent(self):
        for raw, _ in CASES:
            once = text.play(raw)
            self.assertEqual(text.play(once), once)

    @unittest.skipUnless(HAVE, "capture not present")
    def test_nothing_raw_survives_anywhere_in_the_recording(self):
        leaks = [(s, text.play(s)) for s in self.seen if RAW.search(text.play(s))]
        self.assertFalse(leaks, f"{len(leaks)} of {len(self.seen)} strings still raw, e.g. {leaks[:3]}")
        self.assertGreater(len(self.seen), 5000)

    def test_drive_results(self):
        self.assertEqual(text.result("End Of Half"), "End of half")
        self.assertEqual(text.result("Missed FG"), "Missed FG")
        self.assertEqual(text.result("Touchdown"), "Touchdown")


class ShortNames(unittest.TestCase):
    def test_short_names(self):
        for location, espn, abbr, short in [
            ("Ohio State", "Ohio State", "OSU", "Ohio St"),
            ("Southern", "Southern", "SOU", "Southern"),
            ("Jacksonville State", "Jax State", "JVST", "Jax State"),
            ("Louisiana Tech", "Louisiana Tech", "LT", "La Tech"),
            ("Oklahoma State", "Oklahoma St", "OKST", "Oklahoma St"),
            ("Tennessee", "Tennessee", "TENN", "Tennessee"),
            ("Central Connecticut", "C Connecticut", "CCSU", "C Connecticut"),
            ("Florida International", "FIU", "FIU", "Florida Intl"),
            ("Middle Tennessee", "MTSU", "MTSU", "Middle Tenn"),
            ("Florida Atlantic", "FAU", "FAU", "Florida Atl"),
        ]:
            self.assertEqual(text.short_name(location, espn, abbr), short, location)

    @unittest.skipUnless(HAVE, "capture not present")
    def test_every_team_on_the_night_gets_one_that_fits(self):
        board = _load(sorted((CAP / "scoreboard").glob("2026*T*.json.gz"))[-1])
        long = []
        for ev in board["events"]:
            for c in ev["competitions"][0]["competitors"]:
                t = c["team"]
                short = text.short_name(t["location"], t.get("shortDisplayName"), t["abbreviation"])
                self.assertTrue(short)
                self.assertLessEqual(len(short), len(t["location"]))
                if t["location"].upper() != t["abbreviation"].upper():      # Ohio is OHIO
                    self.assertNotEqual(short.upper(), t["abbreviation"].upper(), t["location"])
                if len(short) > text.SHORT_MAX:
                    long.append(short)
        self.assertEqual(long, [])


if __name__ == "__main__":
    unittest.main()
