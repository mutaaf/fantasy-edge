"""The "What's new" notes: present for the version the app builds as, shaped
for the sheet, and clean of anything this repo must never ship.

The once-per-version rule and the launch-flag suppression are Swift and are
tested in `packages/swift/WhatsNewKit` (`make whats-new-test`). This half needs
no Xcode, so it runs in `make test` and a version bump without notes fails here
first.
"""

from __future__ import annotations

import json
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
NOTES = ROOT / "apple" / "FantasyEdge" / "WhatsNew.json"
GENERATOR = ROOT / "apple" / "generate_project.py"
LOBBY = ROOT / "store" / "lobby.json"
APP_SIDE = ROOT / "apple" / "FantasyEdge" / "Sources" / "WhatsNew.swift"

# Real leagues, broadcasters, platforms and clubs. The older "saturday" app was
# paused over a broadcaster's marks; the notes name none of them, ever. The
# store manifest's own `avoid` list is added at test time.
BANNED = {
    "ESPN", "Yahoo", "Sleeper", "NFL", "NCAA", "RedZone", "Red Zone Channel",
    "Super Bowl", "Pro Bowl", "Monday Night", "Thursday Night", "Sunday Ticket",
    "Heisman", "Big Ten", "SEC", "ACC", "Big 12", "Pac-12", "nflverse",
    # every pro club's nickname
    "Cardinals", "Falcons", "Ravens", "Bills", "Panthers", "Bears", "Bengals",
    "Browns", "Cowboys", "Broncos", "Lions", "Packers", "Texans", "Colts",
    "Jaguars", "Chiefs", "Raiders", "Chargers", "Rams", "Dolphins", "Vikings",
    "Patriots", "Saints", "Giants", "Jets", "Eagles", "Steelers", "49ers",
    "Niners", "Seahawks", "Buccaneers", "Titans", "Commanders",
}


def marketing_version() -> str:
    m = re.search(r'^VERSION = "([^"]+)"', GENERATOR.read_text(), re.M)
    assert m, "apple/generate_project.py has no VERSION"
    return m.group(1)


def routed_destinations() -> set[str]:
    """The cases of `WhatsNewDestination`, which is what the app can open."""
    src = APP_SIDE.read_text()
    m = re.search(r"enum WhatsNewDestination\b[^{]*\{(.*?)\n\}", src, re.S)
    assert m, "WhatsNew.swift has no WhatsNewDestination enum"
    return set(re.findall(r"^\s*case (\w+)", m.group(1), re.M))


def copy_of(release: dict) -> list[str]:
    """Every string a reader sees. Icons are SF Symbol names, not copy."""
    out = [release["kicker"], release["headline"], release["subhead"], release["store"]]
    out += release["notes"]
    for card in release["cards"]:
        out += [card["title"], card["line"]]
    return out


class WhatsNewNotes(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.notes = json.loads(NOTES.read_text())
        cls.version = marketing_version()

    def release(self) -> dict:
        found = [r for r in self.notes["releases"] if r["version"] == self.version]
        self.assertEqual(len(found), 1, f"WhatsNew.json needs exactly one entry for {self.version}")
        return found[0]

    def test_current_version_has_notes(self) -> None:
        r = self.release()
        for key in ("kicker", "headline", "subhead", "store"):
            self.assertTrue(r[key].strip(), key)
        self.assertTrue(r["notes"])

    def test_two_to_four_short_cards(self) -> None:
        cards = self.release()["cards"]
        self.assertTrue(2 <= len(cards) <= 4, len(cards))
        for c in cards:
            self.assertLessEqual(len(c["title"].split()), 6, c["title"])
            self.assertLessEqual(len(c["line"]), 120, c["line"])
            self.assertIn(c["tint"], {"green", "gold", "red", "blue"})
            self.assertRegex(c["icon"], r"^[a-z0-9.]+$")

    def test_destinations_are_ones_the_app_routes(self) -> None:
        # The sheet draws a card with an unknown destination plain, so a typo
        # here would quietly lose the callout rather than break anything.
        known = routed_destinations()
        self.assertTrue(known)
        for release in self.notes["releases"]:
            for c in release["cards"]:
                if "destination" in c:
                    self.assertIn(c["destination"], known, c["title"])

    def test_current_version_takes_you_somewhere(self) -> None:
        # The owner's rule: the callouts go to the feature. At least one card
        # in the shipping entry has to be one.
        self.assertTrue(any(c.get("destination") for c in self.release()["cards"]))

    def test_the_force_flags_are_documented_beside_the_notes(self) -> None:
        about = self.notes["about"]
        for flag in ("-whatsNewPreview", "-whatsNewTap"):
            self.assertIn(flag, about)

    def test_versions_are_unique(self) -> None:
        versions = [r["version"] for r in self.notes["releases"]]
        self.assertEqual(len(versions), len(set(versions)))

    def test_no_real_names_or_marks(self) -> None:
        banned = BANNED | set(json.loads(LOBBY.read_text()).get("avoid", []))
        for release in self.notes["releases"]:
            for text in copy_of(release):
                for word in banned:
                    self.assertIsNone(
                        re.search(rf"(?<![A-Za-z]){re.escape(word)}(?![A-Za-z])", text, re.I),
                        f"{word!r} in {release['version']}: {text!r}")

    def test_the_app_bundles_the_notes(self) -> None:
        src = GENERATOR.read_text()
        self.assertIn("WhatsNew.json", src)
        self.assertIn("MARKETING_VERSION = {VERSION}", src)
        self.assertTrue((ROOT / "apple/FantasyEdge/Assets.xcassets/WhatsNewBall.imageset/Ball.png").exists())


if __name__ == "__main__":
    unittest.main()
