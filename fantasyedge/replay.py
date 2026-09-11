"""Replay a finished NFL game as though it were happening now.

Every game in the feed is either finished or has not kicked off, which means
possession, ball position, drives, play-by-play, win probability and a ramping
scoreline are all unexercisable: there is no Sunday afternoon to develop
against, and there will not be one until the next one. A simulator would fix
the schedule problem and break the more important one - it would be *our*
payload shapes being parsed, not ESPN's, so every bug the parsers actually
have would stay hidden.

So this replays a real game instead. It captures one finished event once, and
then rewrites the two files `live.EspnLiveSource._fetch` already reads -
`FANTASYEDGE_SCOREBOARD_FILE` and `FANTASYEDGE_SUMMARY_DIR/{event}.json` - to
show that game as of a moving point in its own clock. Nothing in the live tier
changes, and nothing is mocked at the API boundary, so a replay drives the
same scoring, the same D/ST pairing, the same gamecast shaping and the same
possession logic that a live Sunday would.

`frame()` is the whole idea and is a pure function: two ESPN payloads and a
game clock in, the same two payloads as they looked at that instant out. It is
pure so it can be tested at a play boundary rather than watched.

THE BOX SCORE
-------------
The summary's `boxscore` is final-state only, and serving it was this
harness's one dishonest number: every player carried his end-of-game total
from the opening kickoff, so the Seahawks defence read 16.0 before anybody had
touched the ball and the one thing this product is about - points arriving
during a game - was the one thing a replay could not show.

ESPN does publish the per-play stat lines, at `/v2/.../plays/{p}/participants`
on the core API, and that is still not used here: it is roughly eight hundred
requests to assemble one game. It does not need to be. `play.text` is a
machine-written grammar and every statistic that scores a fantasy point is
stated in it, so the box score is rebuilt from the text instead, in ESPN's own
shape, and `scoring.parse_boxscore` and `scoring.parse_team_defence` read a
replay through exactly the path they read a live Sunday through. There is no
second scoring path.

`reconcile()` is what keeps that honest. It accumulates the whole game and
diffs it against ESPN's published final cell by cell: 99.4% of 485 cells on
event 401872656 and 97.9% of 531 on 401872657, with every athlete finishing
within a tenth of a fantasy point of ESPN's own number. Every frame carries
that rate, the per-category breakdown and the names of the columns the text
cannot support, which are emitted as "--" rather than filled in from the
final. Nothing is ever backfilled from the final; that is the bug this
replaced.
"""

from __future__ import annotations

import copy
import json
import pathlib
import re
import time
from decimal import ROUND_HALF_UP, Decimal

from .live import _get_json, scoreboard_url, summary_url, with_key

# A play's absolute game time is encoded against a fixed 900-second period,
# because that is the only encoding the payload itself supports: a play knows
# its period number and the clock showing at the snap, and nothing else. The
# inverse is exact for any instant that lands on a play, including overtime -
# an OT play at 8:00 round-trips to period 5, 8:00 - which is why there is no
# special case for a ten-minute overtime here.
PERIOD_SECONDS = 900

BOXSCORE_NOTE = (
    "Player stats in `boxscore` are DERIVED from the play-by-play text as of "
    "this clock, not ESPN's published final. Each frame's `replay.boxscore` "
    "block carries the whole-game reconciliation against that final, per "
    "category, and names every column the text cannot support. Nothing is "
    "ever backfilled from the final."
)

# The same sentence, for a frame that could not derive anything.
CAPTURED_NOTE = (
    "This summary carries no box-score athlete list, so there was nothing to "
    "derive from and the captured FINAL box score is served unchanged. Player "
    "totals are the end of the game from the first snap."
)


def clock_seconds(display: str) -> int:
    """"7:00" -> 420 seconds still on the period clock."""
    parts = str(display or "0:00").split(":")
    try:
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        return int(float(parts[0]))
    except ValueError:
        return 0


def clock_display(remaining: int) -> str:
    remaining = max(0, int(remaining))
    return f"{remaining // 60}:{remaining % 60:02d}"


def play_seconds(play: dict) -> int:
    """Absolute seconds into the game at which this play was snapped."""
    period = int(((play.get("period") or {}).get("number")) or 1)
    left = clock_seconds((play.get("clock") or {}).get("displayValue"))
    return (period - 1) * PERIOD_SECONDS + (PERIOD_SECONDS - left)


def ordinal(period: int) -> str:
    if period >= 5:
        return "OT" if period == 5 else f"{period - 4}OT"
    return {1: "1st", 2: "2nd", 3: "3rd", 4: "4th"}.get(period, f"Q{period}")


def _drives(summary: dict) -> list[dict]:
    """Every drive in play order, whether the capture called it done or not."""
    raw = summary.get("drives") or {}
    out = list(raw.get("previous") or [])
    if raw.get("current"):
        out.append(raw["current"])
    return out


def _all_plays(summary: dict) -> list[dict]:
    return [p for d in _drives(summary) for p in (d.get("plays") or [])]


def total_seconds(summary: dict) -> int:
    """When the last recorded play was snapped - the end of a replay."""
    plays = _all_plays(summary)
    return play_seconds(plays[-1]) if plays else 0


def _num(raw, default=0):
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _in_progress_drive(drive: dict, plays: list[dict]) -> dict:
    """A drive that has not finished, described only by what has happened.

    The captured drive carries its outcome - "5 plays, 25 yards, 3:18", a
    result of PUNT, `isScore` - and all of that is the future as far as this
    frame is concerned. Leaving it in is how a replay tells a client the drive
    ends in a punt while the drive is still being played, which is worse than a
    simulator, because it looks like real data.

    Nothing replaces those fields, because nothing honestly can. ESPN's own
    accounting is not a plain sum of the plays: `offensivePlays` is 5 on a
    drive holding 9 play records, since kickoffs, timeouts, punts and penalties
    do not count, and `yards` is measured to the last scrimmage spot rather
    than to the last record - a naive `yardsToEndzone` difference disagreed
    with ESPN on three of this game's nineteen drives and reported one
    possession as minus six yards. So a live drive here has no description, no
    yardage and no play count: absent, which is what a consumer already has to
    handle, rather than a number of our own invention wearing ESPN's shape.
    """
    d = dict(drive)
    d["plays"] = plays
    last = plays[-1] if plays else {}
    last_end = (last.get("end") or {})
    d["end"] = {
        "period": {"type": "quarter",
                   "number": _num((last.get("period") or {}).get("number"), 1)},
        "clock": {"displayValue": (last.get("clock") or {}).get("displayValue", "")},
        "yardLine": last_end.get("yardLine"),
        "text": last_end.get("possessionText") or "",
    }
    d["isScore"] = bool(last.get("scoringPlay"))
    for key in ("result", "displayResult", "shortDisplayResult", "timeElapsed",
                "description", "yards", "offensivePlays"):
        d.pop(key, None)
    return d


def _status_in(period: int, remaining: int) -> dict:
    clock = clock_display(remaining)
    return {
        "clock": float(remaining),
        "displayClock": clock,
        "period": period,
        "type": {
            "id": "2", "name": "STATUS_IN_PROGRESS", "state": "in",
            "completed": False, "description": "In Progress",
            "detail": f"{clock} - {ordinal(period)} Quarter"
                      if period <= 4 else f"{clock} - {ordinal(period)}",
            "shortDetail": f"{clock} - {ordinal(period)}",
        },
    }


def _status_pre(captured: dict) -> dict:
    """Kickoff has not happened.

    A capture of a finished game no longer carries what its pre-game status
    said, so this states the only thing that is certainly true - a full period
    on the clock, nothing played - and keeps the captured detail strings, which
    are the kickoff time rather than a score.
    """
    return {
        "clock": float(PERIOD_SECONDS), "displayClock": clock_display(PERIOD_SECONDS),
        "period": 0,
        "type": {"id": "1", "name": "STATUS_SCHEDULED", "state": "pre",
                 "completed": False, "description": "Scheduled",
                 "detail": (captured.get("type") or {}).get("detail", "Scheduled"),
                 "shortDetail": (captured.get("type") or {}).get("shortDetail", "Scheduled")},
    }


def _situation(play: dict) -> dict:
    """Where the ball is, from the end of the last play that has happened."""
    end = play.get("end") or {}
    team = str(((end.get("team") or {}).get("id")) or "")
    to_ez = end.get("yardsToEndzone")
    sit = {
        "down": end.get("down"),
        "distance": end.get("distance"),
        "yardLine": end.get("yardLine"),
        "yardsToEndzone": to_ez,
        "possession": team,
        "isRedZone": to_ez is not None and int(to_ez) <= 20,
    }
    for key in ("downDistanceText", "shortDownDistanceText", "possessionText"):
        if end.get(key):
            sit[key] = end[key]
    sit["lastPlay"] = {
        "id": str(play.get("id") or ""),
        "text": play.get("text") or "",
        "scoringPlay": bool(play.get("scoringPlay")),
        "team": {"id": str(((play.get("start") or {}).get("team") or {}).get("id") or "")},
    }
    return sit


def _linescores(plays: list[dict], period: int) -> tuple[list[dict], list[dict]]:
    """Quarter-by-quarter, recomputed rather than carried over.

    The captured line score is the finished game's. Left alone it hands a
    client the fourth-quarter points during the first quarter, which is the
    single most obvious way a replay leaks the ending.
    """
    home, away = [], []
    prev_h = prev_a = 0
    for p in range(1, period + 1):
        upto = [x for x in plays if _num((x.get("period") or {}).get("number"), 1) <= p]
        h = _num((upto[-1] if upto else {}).get("homeScore"), 0)
        a = _num((upto[-1] if upto else {}).get("awayScore"), 0)
        home.append({"displayValue": str(h - prev_h)})
        away.append({"displayValue": str(a - prev_a)})
        prev_h, prev_a = h, a
    return home, away


# ══════════════════════ the box score, derived from the play text ══════════
#
# The summary's `boxscore` is final-state only: ESPN publishes no per-play
# player line on this endpoint, so a replay that shipped it served every
# player's end-of-game total from the opening kickoff. A defence read 16.0
# before anybody had touched the ball, which made the one thing this product
# is about - points arriving during a game - the one thing a replay could not
# demonstrate.
#
# The per-play numbers do exist on ESPN's core API, at
# `/v2/.../plays/{p}/participants`, and they are not used here: assembling one
# game costs roughly eight hundred requests. What is used instead is already
# in the payload we have. `play.text` is a strict, machine-written grammar -
# "R.Stevenson up the middle to NE 11 for 3 yards (D.Lawrence; D.Thomas)." -
# and every stat that scores fantasy points is stated in it. So the box score
# is rebuilt from the text, in ESPN's own shape, and `scoring.py` consumes it
# through exactly the same `parse_boxscore` / `parse_team_defence` path it
# uses on a live Sunday. There is no second scoring path.
#
# Two rules keep this honest rather than approximately right:
#
#   * `reconcile()` accumulates the whole game and diffs it against ESPN's
#     published final, cell by cell. Anything that does not match is named in
#     the frame, not smoothed over.
#   * A column the text cannot support - passer rating, QBR - is emitted as
#     "--", which is ESPN's own marker for a value it is not stating. It is
#     never backfilled from the final, because backfilling from the final is
#     the exact bug this code exists to remove.

_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}

# Surname particles that ESPN's play-by-play keeps and the display name splits
# on a space: "G.Van Roten" is one man whose last token is "Roten". Matching on
# the last token alone would look for a "Roten" who is not in the box score.
_PARTICLES = {"st", "van", "von", "de", "del", "della", "da", "di", "le", "la",
              "mac", "mc", "ter", "vander"}

# A name as the play-by-play writes it: one initial, a dot, a surname that may
# carry a hyphen, an apostrophe or a particle. Three details are load-bearing.
# The initial is a single letter and must not be preceded by one, or
# "TOUCHDOWN. A.Borregales extra point is GOOD" parses as a man whose initial
# is "N" and every extra point in both games goes unattributed. The
# continuation is `[A-Z][a-z]` rather than `[A-Z]` so that "R.Shaheed to SEA
# 24" does not swallow the club abbreviation into the surname and "for 2
# yards, TOUCHDOWN" does not swallow the TOUCHDOWN.
_NM = (r"(?<![A-Za-z])[A-Z]\.\s?[A-Z][A-Za-z'.\-]*"
       r"(?:\s[A-Z][a-z][A-Za-z'.\-]*)*")
_PLAY_NAME = re.compile(r"([A-Z])\.\s?([A-Z][A-Za-z'.\-]*"
                        r"(?:\s[A-Z][a-z][A-Za-z'.\-]*)*)")

_SPOT = r"(?:[A-Z][A-Za-z]{1,3}\s)?-?\d+"
_ADV = (r"(?:\s+(?:pushed\s+ob|ran\s+ob|pushed\s+out\s+of\s+bounds|ob))?"
        rf"(?:\s+(?:at|to)\s+(?:{_SPOT}|end\s+zone))?")
_GAIN = r"\s+for\s+(?:(?P<y>-?\d+)\s+yards?|(?P<ng>no\s+gain))"

_RE_PASS_INT = re.compile(
    rf"(?P<passer>{_NM})\s+pass(?:\s+(?:short|deep)\s+(?:left|middle|right))?"
    rf"\s+intended\s+for\s+(?P<rec>{_NM})\s+INTERCEPTED\s+by\s+(?P<who>{_NM})")
_RE_PASS_COMP = re.compile(
    rf"(?P<passer>{_NM})\s+pass(?:\s+(?:short|deep)\s+(?:left|middle|right))?"
    rf"\s+to\s+(?P<rec>{_NM}){_ADV}{_GAIN}")
_RE_PASS_INC = re.compile(
    rf"(?P<passer>{_NM})\s+pass\s+incomplete"
    rf"(?:\s+(?:short|deep)\s+(?:left|middle|right))?(?:\s+to\s+(?P<rec>{_NM}))?")
_RE_SACK = re.compile(
    rf"(?P<passer>{_NM})\s+sacked(?:\s+ob)?(?:\s+at\s+{_SPOT})?{_GAIN}")
_RE_RUSH = re.compile(
    rf"(?P<who>{_NM})(?:\s+(?:scrambles|kneels))?"
    rf"(?:\s+(?:up\s+the\s+middle|(?:left|right)\s+(?:end|tackle|guard)|middle))?"
    rf"{_ADV}{_GAIN}")
_RE_KICKOFF = re.compile(
    rf"(?P<who>{_NM})\s+kicks\s+(?P<dist>\d+)\s+yards?\s+from\s+{_SPOT}"
    rf"\s+to\s+(?:end\s+zone|{_SPOT})")
_RE_PUNT = re.compile(
    rf"(?P<who>{_NM})\s+punts\s+(?P<dist>\d+)\s+yards?"
    rf"\s+to\s+(?:(?P<ez>end\s+zone)|(?P<club>[A-Z]{{2,4}})\s+(?P<yl>-?\d+))")
_RE_RETURN = re.compile(rf"(?P<who>{_NM}){_ADV}{_GAIN}")
_RE_FG = re.compile(
    rf"(?P<who>{_NM})\s+(?P<dist>\d+)\s+yard\s+field\s+goal\s+is\s+"
    r"(?P<res>GOOD|No\s+Good)")
_RE_XP = re.compile(rf"(?P<who>{_NM})\s+extra\s+point\s+is\s+(?P<res>GOOD|No\s+Good)")
_RE_FUMBLE = re.compile(r"FUMBLES(?:\s*\((?P<forced>[^)]*)\))?")
_RE_RECOVERED = re.compile(
    rf"RECOVERED\s+by\s+(?P<club>[A-Z]{{2,4}})-(?P<who>{_NM})")
_RE_TACKLERS = re.compile(r"\s*\((?P<names>[^)]*)\)")
_RE_BRACKET = re.compile(r"\[(?P<names>[^\]]*)\]")

# Noise ESPN staples onto a play that has nothing to do with the play.
_NOISE = [
    re.compile(r"\*\*\s*Injury Update:.*$", re.S),
    re.compile(r"\s*[A-Z]{2,4}-[A-Z][A-Za-z']*\.[^.]*? was injured during the play\.?"),
    re.compile(r"\s*The Replay Official reviewed.*$", re.S),
    re.compile(r"\s*The ruling on the field.*$", re.S),
    re.compile(r"\s*The [a-z ]+ was assisted by replay\.?"),
    re.compile(r",\s*(?:Center|Holder)-[A-Z]\.[A-Za-z'\-]+"
               r"(?:\s[A-Z][a-z][A-Za-z'\-]*)*"),
    re.compile(r"^\s*\((?:Shotgun|No Huddle|Wildcat|Punt formation|"
               r"Field Goal formation)[^)]*\)\s*"),
    re.compile(r"^\s*[A-Z][A-Za-z']*\.[A-Za-z'.\- ]+? reported in as eligible\.\s*"),
    re.compile(r"^\s*Direct snap to [A-Z][A-Za-z']*\.[A-Za-z'.\-]+\.\s*"),
]


def _fold(text: str) -> str:
    return re.sub(r"[^a-z]", "", (text or "").lower())


def _name_keys(display: str) -> tuple[str, set[str]]:
    """First initial and every surname the play-by-play might write for him."""
    parts = [p for p in re.split(r"\s+", (display or "").strip()) if p]
    if len(parts) < 2:
        return "", set()
    tail = parts[1:]
    while len(tail) > 1 and _fold(tail[-1]) in _SUFFIXES:
        tail = tail[:-1]
    keys = {_fold(tail[-1])}
    if len(tail) >= 2 and _fold(tail[-2]) in _PARTICLES:
        keys.add(_fold(tail[-2] + tail[-1]))
    return parts[0][0].upper(), {k for k in keys if k}


class Roster:
    """Resolve `R.Stevenson` to an ESPN athlete id, or refuse.

    The box score's own athlete list is the only roster available, and it is
    the right one: a name in the play text that is not in the box score has no
    stat line to land in anyway. Matching is surname plus first initial plus
    club. The club is what makes it safe - two `D.Jones` in one game are
    ordinary - and an unresolved or ambiguous name is counted and dropped
    rather than guessed at, because guessing puts a touchdown on the wrong
    player and nothing downstream can tell.
    """

    def __init__(self, summary: dict):
        from .scoring import boxscore_names

        self.info = boxscore_names(summary)
        self.by_club: dict[tuple, set] = {}
        self.anywhere: dict[tuple, set] = {}
        for pid, who in self.info.items():
            initial, keys = _name_keys(who.get("name") or "")
            for key in keys:
                self.by_club.setdefault((who.get("team"), initial, key), set()).add(pid)
                self.anywhere.setdefault((initial, key), set()).add(pid)
        self.misses: dict[str, int] = {}

    def club(self, pid: str | None) -> str | None:
        return (self.info.get(pid) or {}).get("team") if pid else None

    def find(self, token: str | None, club: str | None = None) -> str | None:
        m = _PLAY_NAME.fullmatch((token or "").strip())
        if not m:
            if token:
                self._miss(token.strip())
            return None
        initial, key = m.group(1)[0].upper(), _fold(m.group(2))
        scoped = self.by_club.get((club, initial, key)) if club else None
        if scoped:
            if len(scoped) == 1:
                return next(iter(scoped))
            self._miss(f"{token} (ambiguous in {club})")
            return None
        loose = self.anywhere.get((initial, key)) or set()
        if len(loose) == 1:
            return next(iter(loose))
        self._miss(token.strip() + (" (ambiguous)" if loose else ""))
        return None

    def _miss(self, label: str) -> None:
        self.misses[label] = self.misses.get(label, 0) + 1


# Play records that carry no football in them at all. Everything else is put
# through the grammar, because dispatching on `type.text` and trusting it is
# how a "Fumble Recovery (Opponent)" whose text is a 5-yard completion loses
# the completion.
_CLOCK_ONLY = {"Official Timeout", "Timeout", "End Period", "End of Half",
               "End of Game", "End of Regulation", "Two-minute warning",
               "Coin Toss", "Kickoff Return (Offense)"}


def _clean(text: str) -> str | None:
    """The play, minus everything ESPN staples on. None if it never happened.

    A "No Play" is a penalty that wiped the down: the run, the catch, even a
    touchdown in the text before it are all rescinded, and ESPN's box score
    does not carry them. Play 60 of event 401872656 reads as a one-yard A.Barner
    rush and A.Barner has no rushing line in the game, which is exactly this.
    """
    t = (text or "").strip()
    for _ in range(3):
        before = t
        for rx in _NOISE:
            t = rx.sub(" ", t).strip()
        if t == before:
            break
    if re.search(r"(?i)\bno play\b", t):
        return None
    # A penalty stated after the result - "for 1 yard (B.Murphy).PENALTY on
    # SEA-D.Hall" - leaves the result standing, so the clause is cut rather
    # than the play. The lower-case "Penalty on ... declined" form is the same
    # thing said differently.
    return re.split(r"(?i)\.?\s*penalty on\b", t)[0].strip()


def _yards(m: re.Match) -> int:
    return 0 if m.group("ng") else int(m.group("y"))


def _names(blob: str) -> list[str]:
    return [n.strip() for n in (blob or "").split(";") if n.strip()]


class _Tally:
    """Cumulative per-athlete football statistics, keyed by ESPN athlete id."""

    def __init__(self, roster: "Roster", clubs: dict, pair: tuple):
        self.roster, self.clubs, self.pair = roster, clubs, pair
        self.by_athlete: dict[str, dict[str, float]] = {}
        self.orphans: dict[str, int] = {}

    def add(self, pid: str | None, key: str, value: float = 1.0) -> None:
        if not pid:
            return
        line = self.by_athlete.setdefault(pid, {})
        line[key] = line.get(key, 0.0) + value

    def peak(self, pid: str | None, key: str, value: float) -> None:
        if not pid:
            return
        cur = self.by_athlete.setdefault(pid, {}).get(key, 0.0)
        self.by_athlete[pid][key] = max(cur, value, 0.0)

    def other(self, club: str | None) -> str | None:
        a, b = self.pair
        return b if club == a else (a if club == b else None)

    def club_of(self, abbrev: str) -> str | None:
        """"SF" and "LA" both name a club whose ESPN abbreviation may be longer."""
        up = (abbrev or "").upper()
        for ab in self.pair:
            if ab == up or ab.startswith(up) or up.startswith(ab):
                return ab
        return None

    def tacklers(self, rest: str, club: str | None, for_loss: bool) -> None:
        m = _RE_TACKLERS.match(rest or "")
        if not m:
            return
        names = _names(m.group("names"))
        solo = len(names) == 1
        for name in names:
            pid = self.roster.find(name, club)
            self.add(pid, "totalTackles")
            if solo:
                self.add(pid, "soloTackles")
            if for_loss:
                self.add(pid, "tacklesForLoss")

    def defended(self, rest: str, club: str | None) -> str:
        m = _RE_TACKLERS.match(rest or "")
        if not m:
            return rest or ""
        for name in _names(m.group("names")):
            self.add(self.roster.find(name, club), "passesDefended")
        return rest[m.end():]


def _touchdown(rest: str) -> bool:
    return bool(re.match(r"\s*,\s*TOUCHDOWN\b", rest or ""))


def _scrimmage(text: str, t: _Tally, off: str | None) -> str | None:
    """One snap from scrimmage. Returns whoever finished the play with the ball.

    The order is not arbitrary: an interception and a sack both contain the
    word "pass" or a name followed by yardage, and the rushing pattern is the
    loosest of the five, so it is tried last or it eats the others.
    """
    find = t.roster.find

    m = _RE_PASS_INT.search(text)
    if m:
        passer = find(m.group("passer"), off)
        oc = t.roster.club(passer) or off
        dc = t.other(oc)
        t.add(passer, "passingAttempts")
        t.add(passer, "intThrown")
        t.add(find(m.group("rec"), oc), "receivingTargets")
        who = find(m.group("who"), dc)
        t.add(who, "defInterceptions")
        # ESPN credits the interceptor with a pass defended as well as the
        # interception: N.Pritchett's two in event 401872656 are one deflected
        # incompletion and his own pick.
        t.add(who, "passesDefended")
        rest = t.defended(text[m.end():], dc)
        r = _RE_RETURN.search(rest)
        if r and find(r.group("who"), dc) == who:
            t.add(who, "interceptionYards", _yards(r))
            if _touchdown(rest[r.end():]):
                t.add(who, "interceptionTouchdowns")
                t.add(who, "defensiveTouchdowns")
            t.tacklers(rest[r.end():], oc, False)
        return who

    m = _RE_SACK.search(text)
    if m:
        passer = find(m.group("passer"), off)
        oc = t.roster.club(passer) or off
        dc = t.other(oc)
        lost = -_yards(m)
        t.add(passer, "sacksTaken")
        t.add(passer, "sackYardsLost", lost)
        # A sack's yardage is charged to the team, not to the passer's line:
        # ESPN keeps it in the passing row's own `sacks-sackYardsLost` column
        # and leaves `passingYards` gross. Drake Maye is 178 passing yards with
        # 3-10 in sacks in event 401872656, and the receiving column sums to
        # 178 exactly. Subtracting it here would put every quarterback in the
        # league four tenths of a point light.
        rest = text[m.end():]
        tk = _RE_TACKLERS.match(rest)
        names = _names(tk.group("names")) if tk else []
        share = 1.0 / len(names) if names else 0.0
        for name in names:
            pid = find(name, dc)
            t.add(pid, "defSacks", share)
            t.add(pid, "totalTackles")
            if len(names) == 1:
                t.add(pid, "soloTackles")
            t.add(pid, "tacklesForLoss")
            t.add(pid, "QBHits")
        return passer

    m = _RE_PASS_COMP.search(text)
    if m:
        passer = find(m.group("passer"), off)
        oc = t.roster.club(passer) or off
        dc = t.other(oc)
        rec = find(m.group("rec"), oc)
        gain = _yards(m)
        t.add(passer, "passingAttempts")
        t.add(passer, "completions")
        t.add(passer, "passingYards", gain)
        t.add(rec, "receptions")
        t.add(rec, "receivingYards", gain)
        t.add(rec, "receivingTargets")
        t.peak(rec, "longReception", gain)
        rest = text[m.end():]
        if _touchdown(rest):
            t.add(passer, "passingTouchdowns")
            t.add(rec, "receivingTouchdowns")
        t.tacklers(rest, dc, gain < 0)
        return rec

    m = _RE_PASS_INC.search(text)
    if m:
        passer = find(m.group("passer"), off)
        oc = t.roster.club(passer) or off
        t.add(passer, "passingAttempts")
        t.add(find(m.group("rec"), oc) if m.group("rec") else None, "receivingTargets")
        t.defended(text[m.end():], t.other(oc))
        return None

    m = _RE_RUSH.search(text)
    if m:
        who = find(m.group("who"), off)
        oc = t.roster.club(who) or off
        gain = _yards(m)
        t.add(who, "rushingAttempts")
        t.add(who, "rushingYards", gain)
        t.peak(who, "longRushing", gain)
        rest = text[m.end():]
        if _touchdown(rest):
            t.add(who, "rushingTouchdowns")
        t.tacklers(rest, t.other(oc), gain < 0)
        return who
    return None


def _special(text: str, t: _Tally, off: str | None) -> tuple[bool, str | None]:
    """A kickoff, a punt or a place kick. Returns (handled, ball carrier)."""
    find = t.roster.find

    m = _RE_KICKOFF.search(text)
    if m:
        kicker = find(m.group("who"), off)
        kc = t.roster.club(kicker) or off
        rest = text[m.end():]
        if re.search(r"(?i)touchback", rest):
            return True, None
        r = _RE_RETURN.search(rest)
        if not r:
            return True, None
        ret = find(r.group("who"), t.other(kc))
        gain = _yards(r)
        t.add(ret, "kickReturns")
        t.add(ret, "kickReturnYards", gain)
        t.peak(ret, "longKickReturn", gain)
        if _touchdown(rest[r.end():]):
            t.add(ret, "kickReturnTouchdowns")
        t.tacklers(rest[r.end():], kc, False)
        return True, ret

    m = _RE_PUNT.search(text)
    if m:
        punter = find(m.group("who"), off)
        pc = t.roster.club(punter) or off
        dist = int(m.group("dist"))
        t.add(punter, "punts")
        t.add(punter, "puntYards", dist)
        t.peak(punter, "longPunt", dist)
        rest = text[m.end():]
        if m.group("ez") or re.search(r"(?i)touchback", rest):
            t.add(punter, "touchbacks")
        elif m.group("yl") is not None and 0 < int(m.group("yl")) < 20:
            t.add(punter, "puntsInside20")
        r = _RE_RETURN.search(rest)
        if not r:
            return True, None
        ret = find(r.group("who"), t.other(pc))
        gain = _yards(r)
        t.add(ret, "puntReturns")
        t.add(ret, "puntReturnYards", gain)
        t.peak(ret, "longPuntReturn", gain)
        if _touchdown(rest[r.end():]):
            t.add(ret, "puntReturnTouchdowns")
        t.tacklers(rest[r.end():], pc, False)
        return True, ret

    m = _RE_FG.search(text)
    if m:
        who = find(m.group("who"), off)
        t.add(who, "fieldGoalAttempts")
        if m.group("res").upper() == "GOOD":
            t.add(who, "fieldGoalsMade")
            t.peak(who, "longFieldGoalMade", int(m.group("dist")))
        return True, None
    return False, None


def tally(plays: list[dict], roster: Roster, clubs: dict, pair: tuple) -> _Tally:
    """Accumulate every play's stat line, in order."""
    t = _Tally(roster, clubs, pair)
    for play in plays:
        kind = ((play.get("type") or {}).get("text") or "")
        if kind in _CLOCK_ONLY:
            continue
        text = _clean(play.get("text"))
        if not text:
            continue
        off = clubs.get(str(((play.get("start") or {}).get("team") or {}).get("id") or ""))
        handled, carrier = _special(text, t, off)
        if not handled:
            carrier = _scrimmage(text, t, off)
            # A quarterback hit is written in square brackets and a sack is
            # already one, which is why the sack branch credits it itself.
            for br in _RE_BRACKET.finditer(text):
                for name in _names(br.group("names")):
                    t.add(roster.find(name, t.other(off)), "QBHits")
        xp = _RE_XP.search(text)
        if xp:
            kicker = roster.find(xp.group("who"), off)
            t.add(kicker, "extraPointAttempts")
            if xp.group("res").upper() == "GOOD":
                t.add(kicker, "extraPointsMade")
        fum = _RE_FUMBLE.search(text)
        if fum and carrier:
            t.add(carrier, "fumbles")
            rec = _RE_RECOVERED.search(text)
            if rec:
                pid = roster.find(rec.group("who"), t.club_of(rec.group("club")))
                t.add(pid, "fumblesRecovered")
                if pid and roster.club(pid) != roster.club(carrier):
                    t.add(carrier, "fumblesLost")
            elif re.search(r"(?i)and recover(?:s|ed)\b", text):
                t.add(carrier, "fumblesRecovered")
    return t


def _n(value: float) -> str:
    value = float(value or 0.0)
    return str(int(round(value))) if abs(value - round(value)) < 1e-9 else f"{value:.1f}"


def _avg(top: float, bottom: float) -> str:
    if not bottom:
        return "0.0"
    return str(Decimal(top / bottom).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def _g(a: dict, key: str) -> float:
    return float(a.get(key, 0.0) or 0.0)


# ESPN's own column key -> how to state it from an accumulator, per category.
# Keyed by category as well as by column because `interceptions` means two
# opposite things: picks thrown in the passing block, picks caught in the
# interceptions block. scoring.py already guards that distinction on the way
# in; this is the same guard on the way out.
#
# "--" is ESPN's marker for a value it is not stating, and it is what a column
# gets when the play text cannot support it. Passer rating and QBR are not in
# the text at any price. Emitting a plausible number there would be inventing
# data; emitting the final one would be the very bug this module removes.
_EMIT = {
    "passing": {
        "completions/passingAttempts":
            lambda a: f"{_n(_g(a, 'completions'))}/{_n(_g(a, 'passingAttempts'))}",
        "passingYards": lambda a: _n(_g(a, "passingYards")),
        "yardsPerPassAttempt":
            lambda a: _avg(_g(a, "passingYards"), _g(a, "passingAttempts")),
        "passingTouchdowns": lambda a: _n(_g(a, "passingTouchdowns")),
        "interceptions": lambda a: _n(_g(a, "intThrown")),
        "sacks-sackYardsLost":
            lambda a: f"{_n(_g(a, 'sacksTaken'))}-{_n(_g(a, 'sackYardsLost'))}",
        "adjQBR": lambda a: "--",
        "QBRating": lambda a: "--",
    },
    "rushing": {
        "rushingAttempts": lambda a: _n(_g(a, "rushingAttempts")),
        "rushingYards": lambda a: _n(_g(a, "rushingYards")),
        "yardsPerRushAttempt":
            lambda a: _avg(_g(a, "rushingYards"), _g(a, "rushingAttempts")),
        "rushingTouchdowns": lambda a: _n(_g(a, "rushingTouchdowns")),
        "longRushing": lambda a: _n(_g(a, "longRushing")),
    },
    "receiving": {
        "receptions": lambda a: _n(_g(a, "receptions")),
        "receivingYards": lambda a: _n(_g(a, "receivingYards")),
        "yardsPerReception":
            lambda a: _avg(_g(a, "receivingYards"), _g(a, "receptions")),
        "receivingTouchdowns": lambda a: _n(_g(a, "receivingTouchdowns")),
        "longReception": lambda a: _n(_g(a, "longReception")),
        "receivingTargets": lambda a: _n(_g(a, "receivingTargets")),
    },
    "fumbles": {
        "fumbles": lambda a: _n(_g(a, "fumbles")),
        "fumblesLost": lambda a: _n(_g(a, "fumblesLost")),
        "fumblesRecovered": lambda a: _n(_g(a, "fumblesRecovered")),
    },
    "defensive": {
        "totalTackles": lambda a: _n(_g(a, "totalTackles")),
        "soloTackles": lambda a: _n(_g(a, "soloTackles")),
        "sacks": lambda a: _n(_g(a, "defSacks")),
        "tacklesForLoss": lambda a: _n(_g(a, "tacklesForLoss")),
        "passesDefended": lambda a: _n(_g(a, "passesDefended")),
        "QBHits": lambda a: _n(_g(a, "QBHits")),
        "defensiveTouchdowns": lambda a: _n(_g(a, "defensiveTouchdowns")),
    },
    "interceptions": {
        "interceptions": lambda a: _n(_g(a, "defInterceptions")),
        "interceptionYards": lambda a: _n(_g(a, "interceptionYards")),
        "interceptionTouchdowns": lambda a: _n(_g(a, "interceptionTouchdowns")),
    },
    "kickReturns": {
        "kickReturns": lambda a: _n(_g(a, "kickReturns")),
        "kickReturnYards": lambda a: _n(_g(a, "kickReturnYards")),
        "yardsPerKickReturn":
            lambda a: _avg(_g(a, "kickReturnYards"), _g(a, "kickReturns")),
        "longKickReturn": lambda a: _n(_g(a, "longKickReturn")),
        "kickReturnTouchdowns": lambda a: _n(_g(a, "kickReturnTouchdowns")),
    },
    "puntReturns": {
        "puntReturns": lambda a: _n(_g(a, "puntReturns")),
        "puntReturnYards": lambda a: _n(_g(a, "puntReturnYards")),
        "yardsPerPuntReturn":
            lambda a: _avg(_g(a, "puntReturnYards"), _g(a, "puntReturns")),
        "longPuntReturn": lambda a: _n(_g(a, "longPuntReturn")),
        "puntReturnTouchdowns": lambda a: _n(_g(a, "puntReturnTouchdowns")),
    },
    "kicking": {
        "fieldGoalsMade/fieldGoalAttempts":
            lambda a: f"{_n(_g(a, 'fieldGoalsMade'))}/{_n(_g(a, 'fieldGoalAttempts'))}",
        "fieldGoalPct": lambda a: _avg(100.0 * _g(a, "fieldGoalsMade"),
                                       _g(a, "fieldGoalAttempts")),
        "longFieldGoalMade": lambda a: _n(_g(a, "longFieldGoalMade")),
        "extraPointsMade/extraPointAttempts":
            lambda a: f"{_n(_g(a, 'extraPointsMade'))}/{_n(_g(a, 'extraPointAttempts'))}",
        "totalKickingPoints":
            lambda a: _n(3 * _g(a, "fieldGoalsMade") + _g(a, "extraPointsMade")),
    },
    "punting": {
        "punts": lambda a: _n(_g(a, "punts")),
        "puntYards": lambda a: _n(_g(a, "puntYards")),
        "grossAvgPuntYards": lambda a: _avg(_g(a, "puntYards"), _g(a, "punts")),
        "touchbacks": lambda a: _n(_g(a, "touchbacks")),
        "puntsInside20": lambda a: _n(_g(a, "puntsInside20")),
        "longPunt": lambda a: _n(_g(a, "longPunt")),
    },
}

# What has to be non-zero for an athlete to appear in a category at all. ESPN
# lists a man from the moment he does something, which is why a receiver with
# a target and no catch is in the receiving block and a receiver who has not
# been thrown at is not. Listing everybody at zero would be harmless
# arithmetic and a lie about who is on the field.
_PRESENT = {
    "passing": ("passingAttempts", "sacksTaken"),
    "rushing": ("rushingAttempts",),
    "receiving": ("receptions", "receivingTargets"),
    "fumbles": ("fumbles", "fumblesLost", "fumblesRecovered"),
    "defensive": ("totalTackles", "defSacks", "passesDefended", "QBHits",
                  "defensiveTouchdowns"),
    "interceptions": ("defInterceptions",),
    "kickReturns": ("kickReturns",),
    "puntReturns": ("puntReturns",),
    "kicking": ("fieldGoalAttempts", "extraPointAttempts"),
    "punting": ("punts",),
}

_ORDER = {
    "passing": ("passingYards", "completions"),
    "rushing": ("rushingYards", "rushingAttempts"),
    "receiving": ("receivingYards", "receptions"),
    "fumbles": ("fumbles", "fumblesRecovered"),
    "defensive": ("totalTackles", "soloTackles"),
    "interceptions": ("defInterceptions", "interceptionYards"),
    "kickReturns": ("kickReturnYards", "kickReturns"),
    "puntReturns": ("puntReturnYards", "puntReturns"),
    "kicking": ("fieldGoalsMade", "extraPointsMade"),
    "punting": ("puntYards", "punts"),
}

# Team totals the play text states. Everything ESPN ships alongside them -
# first downs, third-down efficiency, red-zone trips, penalties, time of
# possession - needs down-and-distance bookkeeping this parser does not do, so
# those rows are dropped from a derived box score rather than carried over
# from the final. Carrying them over is how a first-quarter frame reports a
# 34:17 time of possession.
TEAM_DERIVED = ("totalOffensivePlays", "totalYards", "yardsPerPlay", "totalDrives",
                "netPassingYards", "completionAttempts", "yardsPerPass",
                "interceptions", "sacksYardsLost", "rushingYards",
                "rushingAttempts", "yardsPerRushAttempt", "turnovers",
                "fumblesLost", "defensiveTouchdowns")


def _team_value(name: str, a: dict, drives: int) -> str | None:
    net = _g(a, "passingYards") - _g(a, "sackYardsLost")
    rush = _g(a, "rushingYards")
    dropbacks = _g(a, "passingAttempts") + _g(a, "sacksTaken")
    snaps = dropbacks + _g(a, "rushingAttempts")
    return {
        "totalOffensivePlays": lambda: _n(snaps),
        "totalYards": lambda: _n(net + rush),
        "yardsPerPlay": lambda: _avg(net + rush, snaps),
        "totalDrives": lambda: _n(drives),
        "netPassingYards": lambda: _n(net),
        "completionAttempts":
            lambda: f"{_n(_g(a, 'completions'))}/{_n(_g(a, 'passingAttempts'))}",
        "yardsPerPass": lambda: _avg(net, dropbacks),
        "interceptions": lambda: _n(_g(a, "intThrown")),
        "sacksYardsLost":
            lambda: f"{_n(_g(a, 'sacksTaken'))}-{_n(_g(a, 'sackYardsLost'))}",
        "rushingYards": lambda: _n(rush),
        "rushingAttempts": lambda: _n(_g(a, "rushingAttempts")),
        "yardsPerRushAttempt": lambda: _avg(rush, _g(a, "rushingAttempts")),
        "turnovers": lambda: _n(_g(a, "intThrown") + _g(a, "fumblesLost")),
        "fumblesLost": lambda: _n(_g(a, "fumblesLost")),
        "defensiveTouchdowns": lambda: _n(_g(a, "defensiveTouchdowns")),
    }[name]()


def _club_totals(tally: _Tally) -> dict[str, dict]:
    out: dict[str, dict] = {ab: {} for ab in tally.pair}
    for pid, stats in tally.by_athlete.items():
        club = tally.roster.club(pid)
        if club not in out:
            continue
        for key, value in stats.items():
            if key.startswith("long"):
                out[club][key] = max(out[club].get(key, 0.0), value)
            else:
                out[club][key] = out[club].get(key, 0.0) + value
    return out


def derived_boxscore(summary: dict, tally: _Tally,
                     drives: dict[str, int] | None = None) -> dict:
    """A box score in ESPN's exact shape, holding only what has been played.

    Templated off the captured one deliberately. The final box score is a
    superset of every prefix of itself - a man who caught a pass in the first
    quarter is in the final receiving block - so its athlete list, its column
    keys and its labels are all correct for any instant, and reusing them is
    what lets `parse_boxscore` and `parse_team_defence` read this without
    knowing a replay happened. What is NOT reused is a single number.
    """
    box = summary.get("boxscore") or {}
    clubs = _club_totals(tally)
    drives = drives or {}
    players = []
    for team in (box.get("players") or []):
        ab = ((team.get("team") or {}).get("abbreviation") or "").upper()
        cats = []
        for cat in (team.get("statistics") or []):
            name = (cat.get("name") or "")
            emit, keys = _EMIT.get(name), (cat.get("keys") or [])
            if emit is None:
                continue
            rows = []
            for ath in (cat.get("athletes") or []):
                pid = str(((ath.get("athlete") or {}).get("id")) or "")
                a = tally.by_athlete.get(pid) or {}
                if not any(_g(a, k) for k in _PRESENT.get(name, ())):
                    continue
                rows.append(({**ath, "stats": [emit[k](a) if k in emit else "--"
                                               for k in keys]}, a))
            first, second = _ORDER.get(name, ("", ""))
            rows.sort(key=lambda r: (-_g(r[1], first), -_g(r[1], second)))
            club = dict(clubs.get(ab) or {})
            if name == "passing":
                # ESPN's passing totals row is net of sacks even though the
                # athlete rows above it are not. Matching that is the whole
                # point of templating off the real thing.
                club["passingYards"] = _g(club, "passingYards") - _g(club, "sackYardsLost")
            cats.append({**cat, "athletes": [r[0] for r in rows],
                         "totals": [emit[k](club) if k in emit else "--"
                                    for k in keys]})
        players.append({**team, "statistics": cats})

    teams = []
    for team in (box.get("teams") or []):
        ab = ((team.get("team") or {}).get("abbreviation") or "").upper()
        a = clubs.get(ab) or {}
        stats = []
        for stat in (team.get("statistics") or []):
            name = stat.get("name")
            if name not in TEAM_DERIVED:
                continue
            shown = _team_value(name, a, drives.get(ab, 0))
            try:
                value = float(shown)
            except ValueError:
                value = None
            stats.append({"name": name, "displayValue": shown, "value": value,
                          "label": stat.get("label")})
        teams.append({**team, "statistics": stats})
    return {**box, "players": players, "teams": teams}


# The last play of a game says so. A capture that stops before it - the test
# fixture is seven drives of a nineteen-drive game - has no final to be
# reconciled against: the published box score describes plays the capture does
# not contain, so diffing the two measures the trim, not the parser. Saying
# 50.7% there would be worse than saying nothing.
_GAME_OVER = {"End of Game", "End of Regulation"}


def capture_is_complete(summary: dict) -> bool:
    plays = _all_plays(summary)
    return bool(plays) and ((plays[-1].get("type") or {}).get("text") in _GAME_OVER)


def _boxscore_note(checked: dict | None) -> dict:
    """How this frame's box score was produced, stated so it cannot be mistaken.

    `mode` is the field that matters: "derived" means every number was read off
    a play that had already been snapped, "captured" means the frame is serving
    ESPN's final and the player totals are the end of the game. A client that
    cannot tell those apart will draw a defence at sixteen points before the
    opening kickoff, which is the whole reason this block exists.
    """
    if checked == "partial":
        return {"mode": "derived", "source": "play-by-play text",
                "note": BOXSCORE_NOTE, "reconciled": False,
                "reason": "this capture stops before the end of the game, so "
                          "the published box score covers plays it does not "
                          "contain and there is nothing to diff against",
                "excluded": sorted(EXCLUDED_COLUMNS)}
    if not checked:
        return {"mode": "captured", "note": CAPTURED_NOTE}
    weak = {cat: info for cat, info in checked["categories"].items()
            if info["cells"] and info["rate"] < 1.0}
    return {
        "mode": "derived",
        "source": "play-by-play text",
        "note": BOXSCORE_NOTE,
        "reconciled": True,
        "reconciledCells": checked["matched"],
        "totalCells": checked["cells"],
        "rate": checked["rate"],
        # A category with no cells in this game - neither side fumbled - is
        # left out rather than reported at zero, which reads as a failure.
        "categories": {c: i["rate"] for c, i in checked["categories"].items()
                       if i["cells"]},
        # Named rather than smoothed over. A category that does not reconcile
        # is still the derived ramp - substituting the final value for it at
        # t=0 is the bug this module exists to remove - but a consumer is told
        # which ones ESPN would argue with, and by how much.
        "unreconciled": {c: {"rate": i["rate"], "cells": i["cells"],
                             "matched": i["matched"]}
                         for c, i in weak.items()},
        "excluded": sorted(EXCLUDED_COLUMNS),
        "mismatches": checked["mismatches"][:12],
        "unresolvedNames": checked["unresolved"],
    }


# Columns a derived box score states as "--" because the play text does not
# carry them at any price, and team rows it drops for the same reason. Both
# lists travel in every frame: an absent number a consumer can handle, and a
# fabricated one it cannot.
EXCLUDED_COLUMNS = ("passing.adjQBR", "passing.QBRating") + tuple(
    f"team.{name}" for name in
    ("firstDowns", "firstDownsPassing", "firstDownsRushing", "firstDownsPenalty",
     "thirdDownEff", "fourthDownEff", "redZoneAttempts", "totalPenaltiesYards",
     "possessionTime"))


def game_clubs(summary: dict) -> tuple[dict[str, str], tuple]:
    """ESPN team id -> club abbreviation, and the two clubs of this game.

    Read off the box score rather than the header, because the box score is
    also what `boxscore_names` labels athletes with, and a club spelled one way
    in one place and another way in the other resolves nobody.
    """
    by_id: dict[str, str] = {}
    pair: list[str] = []
    for team in ((summary.get("boxscore") or {}).get("players") or []):
        club = (team.get("team") or {})
        ab = (club.get("abbreviation") or "").upper()
        if not ab:
            continue
        by_id[str(club.get("id") or "")] = ab
        pair.append(ab)
    comp = ((summary.get("header") or {}).get("competitions") or [{}])[0]
    for c in (comp.get("competitors") or []):
        team = c.get("team") or {}
        ab = (team.get("abbreviation") or "").upper()
        tid = str(team.get("id") or "")
        if tid and tid not in by_id and ab:
            by_id[tid] = ab
            if ab not in pair:
                pair.append(ab)
    return by_id, tuple(pair[:2])


def _drive_counts(drives: list[dict]) -> dict[str, int]:
    out: dict[str, int] = {}
    for d in drives:
        ab = ((d.get("team") or {}).get("abbreviation") or "").upper()
        if ab:
            out[ab] = out.get(ab, 0) + 1
    return out


def _norm(shown: str) -> tuple:
    return tuple(float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", shown or ""))


def reconcile(summary: dict, limit: int = 40) -> dict:
    """Diff the whole-game derived box score against ESPN's published final.

    This is the acceptance test for the parser and it lives in the module
    rather than only in the test suite, because every frame reports its own
    rate. A client that is handed a derived box score is entitled to know how
    much of it ESPN would agree with, and a category that does not reconcile
    has to say so in the payload rather than be quietly replaced by the final
    value - substituting the final value at t=0 is the bug this exists to
    remove, and doing it only for the columns that are hard would be the same
    bug wearing a smaller hat.
    """
    roster = Roster(summary)
    clubs, pair = game_clubs(summary)
    every = _all_plays(summary)
    t = tally(every, roster, clubs, pair)
    box = summary.get("boxscore") or {}
    cats: dict[str, dict] = {}
    misses: list[str] = []

    def cell(cat: str, ok: bool, note: str = "") -> None:
        c = cats.setdefault(cat, {"matched": 0, "total": 0, "excluded": 0})
        c["total"] += 1
        if ok:
            c["matched"] += 1
        elif len(misses) < limit:
            misses.append(note)

    for team in (box.get("players") or []):
        ab = ((team.get("team") or {}).get("abbreviation") or "").upper()
        for cat in (team.get("statistics") or []):
            name = cat.get("name") or ""
            emit = _EMIT.get(name)
            if not emit:
                continue
            keys = cat.get("keys") or []
            slot = cats.setdefault(name, {"matched": 0, "total": 0, "excluded": 0})
            for ath in (cat.get("athletes") or []):
                who = ath.get("athlete") or {}
                pid = str(who.get("id") or "")
                a = t.by_athlete.get(pid) or {}
                stats = ath.get("stats") or []
                for i, key in enumerate(keys):
                    want = stats[i] if i < len(stats) else ""
                    if key not in emit:
                        slot["excluded"] += 1
                        continue
                    got = emit[key](a)
                    if got == "--":
                        slot["excluded"] += 1
                        continue
                    cell(name, _norm(got) == _norm(want),
                         f"{ab} {name} {who.get('displayName')} {key}: "
                         f"derived {got}, ESPN {want}")

    drives = _drive_counts(_drives(summary))
    aggregate = _club_totals(t)
    for team in (box.get("teams") or []):
        ab = ((team.get("team") or {}).get("abbreviation") or "").upper()
        a = aggregate.get(ab) or {}
        for stat in (team.get("statistics") or []):
            name = stat.get("name")
            if name not in TEAM_DERIVED:
                cats.setdefault("team", {"matched": 0, "total": 0, "excluded": 0})
                cats["team"]["excluded"] += 1
                continue
            got = _team_value(name, a, drives.get(ab, 0))
            cell("team", _norm(got) == _norm(stat.get("displayValue")),
                 f"{ab} team {name}: derived {got}, ESPN {stat.get('displayValue')}")

    matched = sum(c["matched"] for c in cats.values())
    total = sum(c["total"] for c in cats.values())
    return {
        "cells": total,
        "matched": matched,
        "rate": round(matched / total, 4) if total else 0.0,
        "categories": {k: {"matched": v["matched"], "cells": v["total"],
                           "excluded": v["excluded"],
                           "rate": round(v["matched"] / v["total"], 4)
                                   if v["total"] else 0.0}
                       for k, v in sorted(cats.items())},
        "mismatches": misses,
        "unresolved": dict(sorted(roster.misses.items())),
    }

def frame(scoreboard: dict, summary: dict, game_seconds: int) -> tuple[dict, dict]:
    """Both payloads as they looked `game_seconds` into the game.

    Pure: the inputs are not touched. Every number here is read off a play that
    had already been snapped at that instant - nothing is interpolated, and
    nothing that had not happened yet survives into the output.
    """
    sb = copy.deepcopy(scoreboard)
    sm = copy.deepcopy(summary)
    event = str((sm.get("header") or {}).get("id") or "")
    game_seconds = max(0, int(game_seconds))

    drives = _drives(sm)
    every = _all_plays(sm)
    included: list[list[dict]] = []
    for d in drives:
        included.append([p for p in (d.get("plays") or [])
                         if play_seconds(p) <= game_seconds])
    flat = [p for group in included for p in group]
    finished = bool(every) and len(flat) == len(every)

    head = (sm.get("header") or {})
    comps = (head.get("competitions") or [{}])
    comp = comps[0] if comps else {}
    sides = {(c.get("homeAway") or "").lower(): c for c in (comp.get("competitors") or [])}

    ev = _event(sb, event)
    ev_comp = ((ev.get("competitions") or [{}])[0]) if ev else {}

    # The box score is rebuilt from the plays that have been snapped, in
    # ESPN's own shape, so `scoring.parse_boxscore` and `parse_team_defence`
    # read a replay exactly as they read a Sunday. `reconcile` runs the same
    # parser over the whole game and diffs it against ESPN's published final,
    # and that rate travels with every frame: a client is entitled to know how
    # much of a derived number ESPN would agree with.
    roster = Roster(sm)
    clubs, pair = game_clubs(sm)
    derivable = bool(roster.info) and bool(every)
    checked = None
    if derivable:
        checked = reconcile(summary) if capture_is_complete(sm) else "partial"

    note = {"event": event, "gameSeconds": game_seconds,
            "playsIncluded": len(flat), "playsTotal": len(every),
            "boxscore": _boxscore_note(checked)}

    if not flat:
        # Nothing has been snapped, so there is nothing to report but "not yet".
        status = _status_pre(comp.get("status") or {})
        _set_status(comp, ev, ev_comp, status)
        _set_scores(sides, ev_comp, 0, 0)
        sm["drives"] = {"previous": []}
        sm["winprobability"] = []
        sm["scoringPlays"] = []
        if derivable:
            # Nobody has touched the ball, so every line is empty. This is the
            # frame the captured box score got most wrong: it read a defence
            # at its final total before the opening kickoff.
            sm["boxscore"] = derived_boxscore(sm, tally([], roster, clubs, pair))
        comp.pop("situation", None)
        ev_comp.pop("situation", None)
        for c in (comp.get("competitors") or []):
            c["possession"] = False
            c.pop("linescores", None)
        note.update({"state": "pre", "clock": "", "period": 0})
        sm["replay"] = note
        sb["replay"] = dict(note)
        return sb, sm

    last = flat[-1]
    last_period = _num((last.get("period") or {}).get("number"), 1)

    if finished:
        # Every play is in, so the captured status is the true one - and it is
        # the only status here that was not derived. Deriving "post" would
        # discard ESPN's own final detail string for a worse copy of it.
        status = comp.get("status") or {}
        period_now = _num(status.get("period"), last_period)
    else:
        period_now = game_seconds // PERIOD_SECONDS + 1
        remaining = PERIOD_SECONDS - (game_seconds % PERIOD_SECONDS)
        if period_now != last_period:
            # Between the end of a period and the first snap of the next one
            # the derived period runs ahead of the game. The last play is the
            # last thing that actually happened, so it wins.
            period_now = last_period
            remaining = clock_seconds((last.get("clock") or {}).get("displayValue"))
        status = _status_in(period_now, remaining)
        _set_status(comp, ev, ev_comp, status)

    home_score = _num(last.get("homeScore"), 0)
    away_score = _num(last.get("awayScore"), 0)
    _set_scores(sides, ev_comp, home_score, away_score)

    ls_home, ls_away = _linescores(flat, period_now)
    if sides.get("home") is not None:
        sides["home"]["linescores"] = ls_home
    if sides.get("away") is not None:
        sides["away"]["linescores"] = ls_away

    sit = _situation(last)
    if finished:
        # Nobody has the ball after the whistle, and ESPN sends no situation.
        comp.pop("situation", None)
        ev_comp.pop("situation", None)
        for c in (comp.get("competitors") or []):
            c["possession"] = False
    else:
        comp["situation"] = sit
        if ev_comp:
            ev_comp["situation"] = dict(sit)
        for c in (comp.get("competitors") or []):
            c["possession"] = str(((c.get("team") or {}).get("id")) or "") == sit["possession"]

    # Rebuild the drive list. A drive with no included play has not begun, so it
    # is dropped entirely rather than shipped empty - an empty drive renders as
    # a real possession that gained nothing.
    previous, current = [], None
    for d, plays in zip(drives, included):
        if not plays:
            continue
        if len(plays) == len(d.get("plays") or []):
            previous.append({**d, "plays": plays})
        else:
            current = _in_progress_drive(d, plays)
    sm["drives"] = {"previous": previous}
    if current is not None:
        sm["drives"]["current"] = current

    if derivable:
        played = previous + ([current] if current is not None else [])
        sm["boxscore"] = derived_boxscore(sm, tally(flat, roster, clubs, pair),
                                          _drive_counts(played))

    ids = {str(p.get("id")) for p in flat}
    sm["scoringPlays"] = [sp for sp in (sm.get("scoringPlays") or [])
                          if str(sp.get("id")) in ids]

    # Win probability is one point per play plus a pre-game point whose playId
    # is the opening drive's, not a play's. Cutting on membership alone would
    # throw that first point away, so the cut is positional: keep everything up
    # to and including the last point that names a play which has happened.
    wp = sm.get("winprobability") or []
    keep = 0
    for i, w in enumerate(wp):
        if str(w.get("playId")) in ids:
            keep = i + 1
    sm["winprobability"] = wp[:keep]

    note.update({"state": (status.get("type") or {}).get("state", "in"),
                 "clock": status.get("displayClock", ""),
                 "period": period_now,
                 "homeScore": home_score, "awayScore": away_score})
    sm["replay"] = note
    sb["replay"] = dict(note)
    return sb, sm


def _event(scoreboard: dict, event: str) -> dict:
    for ev in (scoreboard.get("events") or []):
        if str(ev.get("id")) == event:
            return ev
    return {}


def _set_status(comp: dict, ev: dict, ev_comp: dict, status: dict) -> None:
    """The same status in all three places ESPN states it.

    The scoreboard repeats it at `event.status` and at `event.competitions[0]
    .status`, and `live.games()` reads the second while other clients read the
    first. Setting one and not the other produces a game that is live on the
    board and final in the header.
    """
    comp["status"] = copy.deepcopy(status)
    if ev:
        ev["status"] = copy.deepcopy(status)
    if ev_comp:
        ev_comp["status"] = copy.deepcopy(status)


def _set_scores(sides: dict, ev_comp: dict, home: int, away: int) -> None:
    """The running score, in both payloads.

    `winner` goes with it. A finished game is flagged on the competitor that
    won, and a client that reads it will draw the trophy on a game that is
    tied in the third - which is the ending leaking out through a field nobody
    thinks to truncate.
    """
    by_side = {"home": home, "away": away}
    for c in list(sides.values()) + list(ev_comp.get("competitors") or []):
        side = (c.get("homeAway") or "").lower()
        if side in by_side:
            c["score"] = str(by_side[side])
        c.pop("winner", None)


# ──────────────────────────── capture ────────────────────────────

def capture(event: str, dest: pathlib.Path) -> dict:
    """Download one finished game and the slate it sits on, once.

    The slate is fetched first because it is what decides whether the event is
    even on this week's board: a replay whose event is missing from the
    scoreboard drives nothing, since the live tier walks the slate and never
    asks for a game it cannot see. If the current week does not carry it, the
    single-date board for the game's own kickoff does.
    """
    dest.mkdir(parents=True, exist_ok=True)
    summary = _get_json(with_key(summary_url(event)))
    if not _all_plays(summary):
        raise SystemExit(f"Event {event} has no play-by-play to replay.")
    board = _get_json(with_key(scoreboard_url()))
    if not _event(board, event):
        date = ((summary.get("header") or {}).get("competitions") or [{}])[0].get("date", "")
        day = date[:10].replace("-", "")
        if not day:
            raise SystemExit(f"Event {event} is not on this week's scoreboard "
                             "and carries no date to look it up by.")
        board = _get_json(with_key(scoreboard_url(f"?dates={day}")))
        if not _event(board, event):
            raise SystemExit(f"Event {event} is not on the scoreboard for {day}.")
    (dest / "scoreboard.json").write_text(json.dumps(board))
    (dest / f"{event}.json").write_text(json.dumps(summary))
    return {"event": event, "plays": len(_all_plays(summary)),
            "drives": len(_drives(summary)), "seconds": total_seconds(summary),
            "dir": str(dest)}


def load(source: pathlib.Path, event: str) -> tuple[dict, dict]:
    board = source / "scoreboard.json"
    game = source / f"{event}.json"
    if not (board.exists() and game.exists()):
        raise SystemExit(f"No capture in {source}. Run with --capture first.")
    return json.loads(board.read_text()), json.loads(game.read_text())


def write_frame(out: pathlib.Path, event: str, sb: dict, sm: dict) -> None:
    """Write both files atomically.

    A reader polling every twenty seconds will eventually read while this
    writes, and a half-written scoreboard raises inside `_fetch`, which the
    live tier reads as ESPN blocking us and backs off from for two minutes.
    A rename is the cheap way to never let that happen.
    """
    out.mkdir(parents=True, exist_ok=True)
    for name, payload in ((f"{event}.json", sm), ("scoreboard.json", sb)):
        tmp = out / f".{name}.tmp"
        tmp.write_text(json.dumps(payload))
        tmp.replace(out / name)


def run_hint(out: pathlib.Path) -> str:
    return (f"FANTASYEDGE_SCOREBOARD_FILE={out}/scoreboard.json "
            f"FANTASYEDGE_SUMMARY_DIR={out} "
            "python3 -m fantasyedge api --host 0.0.0.0")


def run(event: str, out: pathlib.Path, speed: float = 60.0, at: int | None = None,
        do_capture: bool = False, start: int = 0, interval: float = 1.0,
        source: pathlib.Path | None = None, log=print) -> dict:
    """Write frames until the game runs out, or one frozen frame with `at`."""
    out = pathlib.Path(out)
    source = pathlib.Path(source) if source else out / "source"
    if do_capture or not (source / f"{event}.json").exists():
        log(f"Capturing event {event} from ESPN ...")
        info = capture(event, source)
        log(f"  {info['plays']} plays, {info['drives']} drives, "
            f"{info['seconds']}s of game clock")
    board, summary = load(source, event)
    length = total_seconds(summary)

    if at is not None:
        sb, sm = frame(board, summary, at)
        write_frame(out, event, sb, sm)
        return {"event": event, "at": at, "length": length,
                "frames": 1, "state": sm["replay"]["state"],
                "clock": sm["replay"]["clock"], "period": sm["replay"]["period"],
                "out": str(out), "run": run_hint(out), "boxscore": BOXSCORE_NOTE,
                "reconciliation": sm["replay"]["boxscore"]}

    began = time.monotonic()
    frames = 0
    last_state = "pre"
    while True:
        game_at = int(start + (time.monotonic() - began) * speed)
        sb, sm = frame(board, summary, game_at)
        write_frame(out, event, sb, sm)
        frames += 1
        last_state = sm["replay"]["state"]
        if game_at >= length:
            log(f"Replay complete: {frames} frames, final "
                f"{sm['replay'].get('awayScore')}-{sm['replay'].get('homeScore')}")
            break
        if frames == 1 or frames % 15 == 0:
            log(f"  {sm['replay']['clock']} {ordinal(sm['replay']['period'])}  "
                f"{sm['replay'].get('awayScore')}-{sm['replay'].get('homeScore')}  "
                f"{sm['replay']['playsIncluded']}/{sm['replay']['playsTotal']} plays")
        time.sleep(max(0.1, interval))
    return {"event": event, "frames": frames, "length": length, "state": last_state,
            "out": str(out), "run": run_hint(out), "boxscore": BOXSCORE_NOTE,
            "reconciliation": sm["replay"]["boxscore"]}
