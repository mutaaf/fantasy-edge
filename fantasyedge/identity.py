"""One player, three providers, one key.

ESPN, Yahoo and Sleeper each mint their own player ids, and none of them
agree. That was invisible while this project followed ESPN leagues only,
because ESPN's *fantasy* player id happens to equal ESPN's *site* athlete id,
so the live box score joined to a roster row for free. It is a coincidence,
not a design, and it holds for exactly one of the three providers.

So the join key here is derived from the player rather than issued by a
platform: a folded name plus a position group, and for a team defence the
club itself, because no two providers spell a defence the same way.

    ESPN     "Rams D/ST"            pos DEF   nfl_team 14
    Sleeper  "LAR"                  pos DEF
    Yahoo    "Los Angeles Rams"     pos DEF

All three land on `def:lar`.

This module is the single owner of that folding. Two copies of it already
existed - `projections.norm_name` and `providers.sleeper.normalise` - kept in
step by a test asserting they agree. Two implementations and a test is a
worse arrangement than one implementation, so both now call this.
"""

from __future__ import annotations

import re
import unicodedata

# Anywhere in the name, not only the end: "Robert Griffin III" and
# "Marvin Harrison Jr." both fold to the bare name.
SUFFIX = re.compile(r"\b(jr|sr|ii|iii|iv|v)\b")

#: Club nickname to the abbreviation this project uses everywhere else.
NICKNAME = {
    "texans": "HOU", "broncos": "DEN", "rams": "LAR", "seahawks": "SEA",
    "steelers": "PIT", "ravens": "BAL", "eagles": "PHI", "patriots": "NE",
    "lions": "DET", "browns": "CLE", "chargers": "LAC", "chiefs": "KC",
    "cowboys": "DAL", "jaguars": "JAX", "vikings": "MIN", "bills": "BUF",
    "49ers": "SF", "niners": "SF", "packers": "GB", "bears": "CHI",
    "dolphins": "MIA", "giants": "NYG", "bengals": "CIN", "commanders": "WAS",
    "raiders": "LV", "panthers": "CAR", "cardinals": "ARI", "titans": "TEN",
    "saints": "NO", "buccaneers": "TB", "bucs": "TB", "jets": "NYJ",
    "colts": "IND", "falcons": "ATL",
}

#: Abbreviations that mean the same club. Relocations and plain disagreement.
TEAM_ALIAS = {
    "WSH": "WAS", "WFT": "WAS", "JAC": "JAX", "OAK": "LV", "LVR": "LV",
    "SD": "LAC", "SDG": "LAC", "STL": "LAR", "LA": "LAR", "ARZ": "ARI",
    "GNB": "GB", "KAN": "KC", "NWE": "NE", "NOR": "NO", "SFO": "SF",
    "TAM": "TB", "NNY": "NYG", "CLV": "CLE", "HST": "HOU", "BLT": "BAL",
}

#: Position spellings that mean the same slot.
POS_ALIAS = {
    "PK": "K", "DST": "DEF", "D/ST": "DEF", "DEFENSE": "DEF", "D": "DEF",
    "WR/RB": "FLEX", "FB": "RB",
}

DEF_POS = {"DEF", "DST", "D/ST", "DEFENSE", "D"}


def fold(name: str) -> str:
    """A display name reduced to a join key.

    No accents, case, punctuation, spaces or generational suffix. Spaces go
    too, so "Ja'Marr" and "JaMarr" land together - an earlier version turned
    the apostrophe into a space and then failed to match precisely the players
    anybody cares about.
    """
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", SUFFIX.sub("", s.lower()))


def team(raw: str) -> str:
    """A club abbreviation, folded through the alias table."""
    ab = (raw or "").upper().strip()
    return TEAM_ALIAS.get(ab, ab)


def position(raw: str) -> str:
    p = (raw or "").upper().strip()
    return POS_ALIAS.get(p, p)


def club_of(name: str, nfl_team: str = "") -> str:
    """The club a defence belongs to, from however its name was spelled.

    Scans for a nickname anywhere in the string rather than taking the first
    word: ESPN says "Rams D/ST" but Yahoo says "Los Angeles Rams", and taking
    word one gives "Los".
    """
    for word in re.findall(r"[a-z0-9]+", (name or "").lower()):
        if word in NICKNAME:
            return NICKNAME[word]
    ab = team(nfl_team)
    if ab and ab != "FA":
        return ab
    # A bare abbreviation is how Sleeper names a defence: "LAR".
    bare = team(name)
    return bare if bare in set(NICKNAME.values()) else ""


def key(name: str, pos: str = "", nfl_team: str = "") -> str:
    """The provider-neutral identity of one player.

    Returns "" when there is not enough to identify anybody, which callers
    must treat as unresolvable rather than as a key that groups every
    nameless row together.
    """
    p = position(pos)
    if p in DEF_POS or (not p and club_of(name, nfl_team) and not fold(name).strip()):
        club = club_of(name, nfl_team)
        return f"def:{club.lower()}" if club else ""
    n = fold(name)
    if not n:
        return ""
    return f"{n}:{p.lower()}" if p else n


def loose(name: str, nfl_team: str = "") -> str:
    """Name and club only, for joining against a source with no position.

    A box score groups athletes by statistical category, not by position, so
    the position half of `key` is not available on that side of the join.
    Name plus club is enough: duplicate full names inside one NFL club are
    vanishingly rare, and a collision costs one mismatched stat line rather
    than a wrong total for everybody.
    """
    n = fold(name)
    if not n:
        return ""
    ab = team(nfl_team)
    return f"{n}@{ab.lower()}" if ab and ab != "FA" else n


class Resolver:
    """Match a player from one provider onto players indexed from another.

    Three stages, each accepted only when it lands on exactly one candidate.
    Requiring uniqueness is what keeps a widening match from becoming a
    guess: an ambiguous fallback is reported as unresolved, because a
    confidently wrong stat line is worse than a blank one.

    The stages exist because real data breaks in three distinct ways, all of
    them observed against ESPN and Sleeper's own player files:

    1. **Exact** - folded name plus position. Resolves 98.8% of a real
       675-player pool on its own.
    2. **Name only** - the same person, filed at a different position.
       Travis Hunter is a WR to ESPN and a DB to Sleeper; N'Keal Harry moved
       from WR to TE. The position disagreeing is not evidence of a different
       human.
    3. **Surname, position and club** - the same person under another name.
       ESPN says "Hollywood Brown", Sleeper says "Marquise Brown"; "Bam
       Knight" is "Zonovan Knight". A shared surname alone would be reckless,
       so this stage additionally demands the same position and the same NFL
       club, and still only accepts a unique hit.

    What stays unresolved stays unresolved. A player who has left the league
    is absent from the other provider's file, and the honest answer is no
    match rather than the nearest surname.
    """

    def __init__(self):
        self.by_key: dict[str, list] = {}
        self.by_name: dict[str, list] = {}
        self.by_last: dict[tuple[str, str, str], list] = {}

    def add(self, ident, name: str, pos: str = "", nfl_team: str = "") -> None:
        entry = (str(ident), team(nfl_team))
        k = key(name, pos, nfl_team)
        if k:
            self.by_key.setdefault(k, []).append(entry)
        n = fold(name)
        if n:
            self.by_name.setdefault(n, []).append(entry)
        parts = re.findall(r"[A-Za-z']+", name or "")
        if len(parts) >= 2:
            self.by_last.setdefault(
                (fold(parts[-1]), position(pos), team(nfl_team)), []).append(entry)

    @staticmethod
    def _pick(cands, club: str):
        """One identity, or nothing.

        A single candidate is the answer. Several become one only when the
        club settles it - there are four Mike Williamses in the league's
        history and exactly one of them is the Charger. Several that the club
        cannot separate is a genuine ambiguity, and the answer is nothing.
        """
        if not cands:
            return None
        uniq = {c[0] for c in cands}
        if len(uniq) == 1:
            return cands[0][0]
        if club and club != "FA":
            same = {c[0] for c in cands if c[1] == club}
            if len(same) == 1:
                return next(iter(same))
        return None

    def resolve(self, name: str, pos: str = "", nfl_team: str = "") -> tuple:
        """Return (identity, how) or (None, "") when nothing is certain."""
        club = team(nfl_team)
        k = key(name, pos, nfl_team)
        for cands, how in ((self.by_key.get(k) if k else None, "exact"),
                           (self.by_name.get(fold(name)), "name")):
            got = self._pick(cands, club)
            if got is not None:
                return got, how
        parts = re.findall(r"[A-Za-z']+", name or "")
        if len(parts) >= 2 and club and club != "FA":
            got = self._pick(self.by_last.get((fold(parts[-1]), position(pos), club)), club)
            if got is not None:
                return got, "surname+club"
        return None, ""
