"""End-zone paint: the club's colour, and an ink chosen to read on it.

The paint used to be the club's *chip*. A chip is solved onto one luminance
band so that white text clears 4.5:1 inside a panel, which is right for a
panel and wrong for a thousand square yards: it painted Chicago's navy as a
mid-blue and both Las Vegas and Pittsburgh's black as a mid-grey.

Two properties have to hold together, and they pull against each other - a
paint far from the grass may be light enough that white letters vanish on it.
So both are measured here, over every club colour a fixture in this repository
states, in both codes.
"""

import json
import pathlib
import re
import unittest

from fantasyedge import scene as sc

ROOT = pathlib.Path(__file__).resolve().parents[1]
TOKENS = json.loads((ROOT / "design" / "tokens.json").read_text())
PAINT = TOKENS["visual"]["field"]["paint"]
TURF = TOKENS["color"]["turf.a"]
LEAGUES = ("nfl", "college-football")

# CIE76: below about 2.3 two colours are the same colour to an eye that is not
# holding them side by side. WCAG: 3:1 is the large-text floor, and end-zone
# lettering is as large as text gets.
JND = 2.3
LARGE_TEXT = 3.0


def _lab(hexs):
    def lin(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(c) for c in sc._rgb(hexs))
    x = (r * 0.4124 + g * 0.3576 + b * 0.1805) / 0.95047
    y = r * 0.2126 + g * 0.7152 + b * 0.0722
    z = (r * 0.0193 + g * 0.1192 + b * 0.9505) / 1.08883

    def f(t):
        return t ** (1 / 3) if t > 0.008856 else (7.787 * t) + 16 / 116
    fx, fy, fz = f(x), f(y), f(z)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def dE(a, b):
    (l1, a1, b1), (l2, a2, b2) = _lab(a), _lab(b)
    return ((l1 - l2) ** 2 + (a1 - a2) ** 2 + (b1 - b2) ** 2) ** 0.5


def club_colours():
    """Every club colour a fixture or capture here states, so the sweep is
    real clubs rather than a guess at what a club colour looks like."""
    found = {}
    pattern = re.compile(
        r'"(?:abbreviation)"\s*:\s*"([^"]+)"[^}]{0,400}?"color"\s*:\s*"([0-9a-fA-F]{6})"')
    for folder in ("tests/fixtures", "data/replay/source"):
        for p in (ROOT / folder).glob("*.json"):
            try:
                text = p.read_text()
            except OSError:
                continue
            for m in pattern.finditer(text):
                found.setdefault(m.group(1), "#" + m.group(2).upper())
    return found


def art_for(colour, league="nfl"):
    home = {"abbr": "HOM", "name": "Home Club", "location": "Home",
            "nickname": "Club", "color": colour, "id": "1"}
    away = {"abbr": "AWY", "name": "Away Club", "location": "Away",
            "nickname": "Rivals", "color": "#FFFFFF", "id": "2"}
    return sc.build({"home": home, "away": away}, league=league)["field"]["art"]


class ThePaintIsTheClubsColour(unittest.TestCase):

    def test_the_paint_is_the_colour_the_club_states_not_its_chip(self):
        for league in LEAGUES:
            for abbr, colour in club_colours().items():
                art = art_for(colour, league)
                for zone in art["endZones"]:
                    self.assertEqual(zone["paint"].upper(), colour.upper(),
                                     f"{abbr} in {league}")

    def test_black_stays_black(self):
        """Las Vegas and Pittsburgh state #000000. The chip band turned that
        into #6F6F6F - a grey end zone for two clubs whose colour is black."""
        art = art_for("#000000")
        self.assertEqual(art["endZones"][0]["paint"].upper(), "#000000")
        self.assertNotEqual(sc.chip("#000000", TOKENS["chip"]).upper(), "#000000")

    def test_the_midfield_ring_is_painted_the_same_colour(self):
        for league in LEAGUES:
            art = art_for("#0B1C3A", league)
            self.assertEqual(art["midfield"]["paint"].upper(), "#0B1C3A", league)


class TheLetteringReadsOnIt(unittest.TestCase):

    def test_every_club_letters_its_end_zone_legibly_in_both_codes(self):
        worst = (None, 99.0)
        for league in LEAGUES:
            for abbr, colour in club_colours().items():
                art = art_for(colour, league)
                zone = art["endZones"][0]
                seen = sc.paint_over(zone["paint"], TURF, PAINT["endZoneOpacity"])
                got = sc.contrast(zone["tint"], seen)
                if got < worst[1]:
                    worst = (f"{abbr} in {league}", got)
                self.assertGreaterEqual(
                    got, LARGE_TEXT,
                    f"{abbr} letters {zone['tint']} on {seen} at {got:.1f}:1 in {league}")
        self.assertIsNotNone(worst[0])

    def test_a_light_club_letters_dark_rather_than_white(self):
        """New Orleans' old gold is the case that breaks an assumed white:
        white measures 1.7:1 on it, which is unreadable at any size."""
        art = art_for("#D3BC8D")
        ink = art["endZones"][0]["tint"]
        self.assertEqual(ink.upper(), PAINT["ink"].upper())
        seen = sc.paint_over("#D3BC8D", TURF, PAINT["endZoneOpacity"])
        self.assertLess(sc.contrast(PAINT["white"], seen), LARGE_TEXT)
        self.assertGreaterEqual(sc.contrast(ink, seen), LARGE_TEXT)

    def test_a_dark_club_still_letters_white(self):
        for colour in ("#000000", "#0B1C3A", "#4F2683"):
            art = art_for(colour)
            self.assertEqual(art["endZones"][0]["tint"].upper(),
                             PAINT["white"].upper(), colour)

    def test_both_ends_and_midfield_letter_in_the_same_ink(self):
        """One field, one answer: a club does not letter one end white and the
        other dark, because both ends are painted the same colour."""
        for colour in ("#D3BC8D", "#0B1C3A"):
            art = art_for(colour)
            inks = {z["tint"] for z in art["endZones"]}
            inks.add(art["midfield"]["text"]["tint"])
            self.assertEqual(len(inks), 1, colour)


class ThePaintIsADifferentSurfaceFromTheGrass(unittest.TestCase):
    """Whether an end zone reads as painted is a colour question, not a
    luminance one: a WCAG ratio against the turf is near 1 by construction for
    a chip, and says nothing. CIE76 against the grass is the measure."""

    def test_every_club_separates_from_the_turf_in_both_codes(self):
        for league in LEAGUES:
            for abbr, colour in club_colours().items():
                art = art_for(colour, league)
                seen = sc.paint_over(art["endZones"][0]["paint"], TURF,
                                     PAINT["endZoneOpacity"])
                got = dE(seen, TURF)
                self.assertGreater(got, JND * 2,
                                   f"{abbr} paints dE {got:.1f} from the grass in {league}")

    def test_the_club_colour_separates_better_than_its_chip_did(self):
        """The chip band sits near the grass's own luminance, so solving a
        club onto it moved every club *toward* the turf. Measured over every
        club here: the worst separation rises from 7.8 to 15.3."""
        def worst(use_chip):
            out = 999.0
            for colour in club_colours().values():
                used = sc.chip(colour, TOKENS["chip"]) if use_chip else colour
                seen = sc.paint_over(used, TURF, PAINT["endZoneOpacity"])
                out = min(out, dE(seen, TURF))
            return out
        self.assertGreater(worst(False), worst(True))


if __name__ == "__main__":
    unittest.main()
