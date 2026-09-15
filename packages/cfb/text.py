"""ESPN's words, made readable once, on the server.

Play text arrives as a scorer's shorthand: "(05:01) #41 R.Culkin field goal
attempt from 27 yards GOOD (H: #19 L.Droegemueller, LS: #45 B.Bergfeld),
clock 04:59". A screen wants "R. Culkin field goal attempt from 27 yards
good". Every string a client draws from a play, a scoring summary or a drive
result goes through here, so no client ever cleans text, and none can do it
differently.

What is removed: the leading clock, formation tokens, jersey numbers,
tackler and holder parentheticals, a review's "(Original Play: ...)", the
trailing ", clock 04:59" and "End Of Play". What is rewritten: ALL-CAPS tags
("1ST DOWN", "TOUCHDOWN", "NO GOOD", "KICK") into lower case, "14 Yd Run"
into "14-yd run", a conversion parenthetical into a clause, and "K.Jackson"
into "K. Jackson". Names, numbers and yard lines are never changed.
"""
from __future__ import annotations

import re

# Words ESPN writes in capitals as tags, never as names or places.
CAPS_TAGS = [
    ("CALL OVERTURNED", "call overturned"), ("CALL CONFIRMED", "call confirmed"),
    ("RULING UPHELD", "ruling upheld"), ("NO GOOD", "no good"), ("NO PLAY", "no play"),
    ("1ST DOWN", "first down"), ("TOUCHDOWN", "touchdown"), ("SAFETY", "safety"),
    ("FUMBLES", "fumbles"), ("FUMBLE", "fumble"), ("PENALTY", "penalty"), ("BLOCKED", "blocked"),
    ("GOOD", "good"), ("KICK", "kick"), ("TOUCHBACK", "touchback"), ("DECLINED", "declined"),
    ("OFFSETTING", "offsetting"), ("INTERCEPTED", "intercepted"), ("RECOVERED", "recovered"),
    ("MISSED", "missed"),
]
_CAPS = re.compile(r"\b(" + "|".join(re.escape(k) for k, _ in CAPS_TAGS) + r")\b")
_CAPS_MAP = dict(CAPS_TAGS)

FORMATION = re.compile(r"^(?:No Huddle-)?(?:Shotgun|Pistol|Under Center|No Huddle)\s+")
CLOCK_PREFIX = re.compile(r"^\(\d{1,2}:\d{2}\)\s*")
JERSEY = re.compile(r"#\d+\s*")
CLOCK_SUFFIX = re.compile(r",?\s*clock \d{1,2}:\d{2},?")
END_OF_PLAY = re.compile(r",?\s*End Of Play\.?", re.I)
ORIGINAL = re.compile(r"\(Original Play:.*$")
INITIAL = re.compile(r"\b([A-Z])\.(?=[A-Z][a-z'])")
YARDS = re.compile(r"\b(\d+) Yd\b")
# "(Dillon Curtis Kick)", "(C. Hawkins KICK)"
KICK = re.compile(r"\(([^()]*?)\s+(?:KICK|Kick)\)")
# "(O. Carey PAT MISSED)"
PAT = re.compile(r"\(([^()]*?)\s+PAT\s+(MISSED|BLOCKED|GOOD|Missed|Blocked|Good)\)")
# "(Mana Carvalho Run for Two-Point Conversion)", "(Two-Point Pass Conversion Failed)"
CONVERSION = re.compile(r"\(([^()]*Two-Point[^()]*)\)")
PAREN = re.compile(r"\s*\([^()]*\)")
SCORING_TYPES = ("Run", "Pass", "Field Goal", "Interception Return", "Fumble Return", "Punt Return",
                 "Kickoff Return", "Blocked Punt Return", "Blocked Field Goal Return", "Fumble Recovery")


def _sentence_case(fragment: str) -> str:
    """"Mana Carvalho Run for Two-Point Conversion" -> "Mana Carvalho run for two-point conversion".
    Only the known football words lose their capitals; names keep theirs."""
    for word in ("Run", "Pass", "Conversion", "Failed", "Two-Point", "Kick", "Good", "Attempt"):
        fragment = re.sub(rf"\b{word}\b", word.lower(), fragment)
    return fragment


def play(text: str | None) -> str:
    """One play or scoring summary, readable. Idempotent: cleaning a cleaned
    string changes nothing."""
    t = (text or "").strip()
    t = CLOCK_PREFIX.sub("", t)
    t = FORMATION.sub("", t)
    t = ORIGINAL.sub("", t)
    t = JERSEY.sub("", t)
    t = CLOCK_SUFFIX.sub(", ", t)
    t = END_OF_PLAY.sub("", t)
    t = PAT.sub(lambda m: f", {m.group(1).strip()} extra point {m.group(2).lower()}", t)
    t = KICK.sub(lambda m: f", {m.group(1).strip()} kick", t)
    t = CONVERSION.sub(lambda m: ", " + _sentence_case(m.group(1).strip()), t)
    # Whatever parenthetical is left names tacklers, a holder and snapper, or
    # a scorer's note; none of it is the play.
    t = PAREN.sub("", t)
    t = re.sub(r"\s*\([^()]*$", "", t)          # ESPN cuts some texts off inside a parenthesis
    t = _CAPS.sub(lambda m: _CAPS_MAP[m.group(1)], t)
    t = YARDS.sub(r"\1-yd", t)
    for kind in SCORING_TYPES:
        t = re.sub(rf"(\d+-yd) {kind}\b", lambda m: f"{m.group(1)} {kind.lower()}", t)
    t = INITIAL.sub(r"\1. ", t)
    t = re.sub(r"\s+([,.;])", r"\1", t)
    t = re.sub(r"\s{2,}", " ", t)
    t = re.sub(r"^[,;.\s]+|[,;\s]+$", "", t)
    # A new sentence starts with a capital; "Jr." and an initial do not end one.
    t = re.sub(r"(?<![A-Z])(?<!Jr)(?<!Sr)(?<!St)([.!?]\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), t)
    return t[:1].upper() + t[1:] if t else t


def result(text: str | None) -> str:
    """A drive result: "End Of Half" -> "End of half", "Missed FG" unchanged."""
    t = (text or "").strip()
    if not t:
        return t
    words = t.split()
    return " ".join([words[0]] + [w if (w.isupper() and len(w) <= 3) else w.lower() for w in words[1:]])


# ---- team names -------------------------------------------------------------

SHORT_WORDS = [("International", "Intl"), ("State", "St"), ("Northern", "N"), ("Southern", "So"),
               ("Western", "W"), ("Eastern", "E"), ("Central", "C"), ("Tennessee", "Tenn"),
               ("Carolina", "Car"), ("Connecticut", "Conn"), ("Mississippi", "Miss"), ("Louisiana", "La"),
               ("Georgia", "Ga"), ("Atlantic", "Atl"), ("Kentucky", "KY"), ("Michigan", "Mich"), ("Illinois", "Ill")]
SHORT_MAX = 14


def short_name(location: str, espn_short: str | None, abbr: str) -> str:
    """The name to draw when `location` does not fit: ESPN's shortDisplayName
    when it is shorter and is not just the abbreviation the chip beside it
    already shows ("Oklahoma St", "Jax State"); otherwise the location with its
    long words shortened one at a time until it is at most SHORT_MAX
    ("Florida Intl", "La Tech"); otherwise the location itself. Never longer
    than the location."""
    location = (location or abbr or "").strip()
    espn_short = (espn_short or "").strip()
    if espn_short and espn_short.upper() != abbr.upper() and len(espn_short) < len(location) \
            and len(espn_short) <= SHORT_MAX:
        return espn_short
    name = location
    if " " not in location:           # "Southern" is a school, not a direction to shorten
        return location
    for long, short in SHORT_WORDS:
        if len(name) <= SHORT_MAX and name != location:
            break
        name = re.sub(rf"\b{long}\b", short, name)
    return name if len(name) < len(location) else location
