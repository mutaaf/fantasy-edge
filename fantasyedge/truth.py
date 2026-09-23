"""Two sources, one play: ESPN's live estimate, corrected by nflverse.

ESPN's public feed says where a play started and where it ended. It does not
say where the ball was *caught*, so the scene has had to guess: a share of the
gain, clamped to a band per depth word. On a screen pass that ran sixty yards
the guess put the catch thirty yards downfield and flew the ball there. The
play is drawn in the right place at its ends and wrong in the middle, which is
the part you watch.

nflverse republishes the NFL's own play-by-play, and it states `air_yards` and
`yards_after_catch` for every throw, the gap a run went through, and how far a
kick travelled. So a finished game can be drawn from what happened rather than
from what could be inferred.

WHICH SOURCE WINS, AND WHEN
---------------------------
A live game has no nflverse rows: they are published after the fact. So the
rule is not "prefer nflverse", it is:

    live       ESPN's text and spots, and a stated estimate for the rest
    corrected  every field nflverse states, in place, with the rest left alone

A play carries which it is, per field, in `truth`. A replay of a finished game
is corrected throughout; a Sunday afternoon is an estimate and says so.

THE IDENTITY RULE
-----------------
The two sources share no play id, so a play is matched on what it says about
itself. Game first, which is exact: nflverse's schedules release carries ESPN's
event id in an `espn` column, so the game bridge is published, not guessed.

Within a game, a play is identified by

    (quarter, down, distance, yards to the defending end zone)

and, among rows that agree on all four, the one whose game clock is nearest.
Those four pin a play to a situation, and a game almost never repeats a
situation in the same quarter - when it does, after an offsetting penalty, the
clock separates the repeats. A match past `TOLERANCE_SECONDS` of clock drift is
refused rather than forced: a wrong correction is worse than none, because it
would draw one play's ball on another play's path.

Kickoffs and extra points have no down. They are matched on quarter, kind and
clock, in order, which is enough because a quarter holds few of them.

WHAT IS STILL ESTIMATED
-----------------------
Neither source tracks players, so nothing here says where across the field a
ball went. `pass_location` and `run_location` name a third of the field
(left, middle, right) and that is all anybody publishes; the lateral yardage
in a path remains a layout choice. It is called out in `estimated` on every
play so a client can never present it as measured.
"""

from __future__ import annotations

from . import nflverse

# How far apart two clocks may be and still be the same play. nflverse stamps
# a play at the snap and ESPN at its own moment, and they differ by a second
# or two; past this the situation match is more likely a coincidence.
TOLERANCE_SECONDS = 8

# nflverse rows that are not a play: the game marker, timeouts, and the
# no-play rows an offsetting penalty leaves behind.
NOT_A_PLAY = {"", "NA", "no_play"}

# What a corrected play carries, and where it comes from.
CORRECTABLE = (
    "airYards", "yacYards", "passLength", "passLocation",
    "runLocation", "runGap", "kickDistance", "returnYards",
    "penaltyYards", "shotgun", "noHuddle", "scramble", "yards",
)

# Lateral placement is a layout everywhere: nobody publishes it.
ESTIMATED_ALWAYS = ("lane", "lateral")

# Kinds whose spot is not comparable between the two sources, because each
# reports a change of possession its own way. Measured on 2025_01_MIN_CHI:
#
#   kickoff  CHI kicks from its own 35. ESPN says 65 yards to the end zone,
#            which is the distance; nflverse says 35, which is the marker.
#   punt     CHI punts from its own 16 at 4th & 19. nflverse says 84, the
#            distance; ESPN says 16, having not flipped for the home side.
#
# Neither is a bug to route around: they are different statements. So a
# special-teams play is matched on its kind and its clock, never on its spot,
# and the spot comparison below reports scrimmage plays separately from it.
# None of this reaches the field: the scene draws from ESPN's `yardLine`,
# which is fixed to the ground and independently right in both cases, and a
# correction only ever supplies a *relative* yardage - how far the ball was
# thrown, how far it was kicked - which carries no convention at all.
POSSESSION_CHANGES = ("kickoff", "punt", "extra_point", "field_goal")


def _f(v):
    """A number, or None. nflverse writes an absent value as "NA"."""
    if v in (None, "", "NA"):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _i(v):
    f = _f(v)
    return None if f is None else int(f)


def _secs(clock) -> int | None:
    """A game clock as seconds remaining in its quarter."""
    s = (clock or "").strip()
    if ":" not in s:
        return None
    m, _, rest = s.partition(":")
    try:
        return int(m) * 60 + int(float(rest))
    except ValueError:
        return None


def _kind(row: dict) -> str:
    """The family a row belongs to, for matching a play with no down."""
    t = (row.get("play_type") or "").lower()
    if "kickoff" in t:
        return "kickoff"
    if "extra_point" in t:
        return "extra_point"
    if "field_goal" in t:
        return "field_goal"
    if "punt" in t:
        return "punt"
    return t


def _espn_kind(play: dict) -> str:
    t = (play.get("type") or "").lower()
    if "kickoff" in t:
        return "kickoff"
    if "extra point" in t or "pat" in t:
        return "extra_point"
    if "field goal" in t:
        return "field_goal"
    if "punt" in t:
        return "punt"
    if "pass" in t or "reception" in t or "incompletion" in t or "interception" in t:
        return "pass"
    if "sack" in t:
        return "sack"
    if "penalty" in t:
        return "penalty"
    return "run"


def playable(rows: list[dict]) -> list[dict]:
    """The nflverse rows that are a play somebody watched."""
    return [r for r in rows
            if (r.get("play_type") or "") not in NOT_A_PLAY
            and not _i(r.get("timeout"))]


def match(plays: list[dict], rows: list[dict], tolerance: int = TOLERANCE_SECONDS) -> dict[str, dict]:
    """{ESPN play id: nflverse row}, by the identity rule above.

    `plays` are the shaped ESPN plays a scene is built from: they carry
    `period`, `clock`, `down`, `distance` and `from` (yards to the defending
    end zone), which is the same quantity as nflverse's `yardline_100`.
    Unmatched plays are simply absent; nothing is forced.

    Matched in passes, strongest evidence first, because a single greedy sweep
    lets a weak match consume a row that a later play matches exactly. On
    401772510 that cost a first-quarter touchdown its correction: the row was
    an exact match three seconds away and had already been taken.
    """
    pool = playable(rows)
    # A penalty nullifies a play, and nflverse files it as `no_play`, which is
    # not in `playable`. ESPN keeps it as a play, so the penalty rows are
    # matched from their own pool in the last pass and never compete with a
    # real one.
    flags = [r for r in rows if (r.get("play_type") or "") == "no_play" and _i(r.get("penalty"))]
    used: set[int] = set()
    used_flags: set[int] = set()
    out: dict[str, dict] = {}

    def situation(play: dict):
        return (play.get("period"), _i(play.get("down")), _i(play.get("distance")),
                _i(play.get("from")))

    def row_situation(r: dict):
        return (_i(r.get("qtr")), _i(r.get("down")), _i(r.get("ydstogo")),
                _i(r.get("yardline_100")))

    pending = [p for p in plays if str(p.get("id") or "")]

    def sweep(pred_for, exact: bool, source=None, seen=None):
        """Assign every candidate pair in this pass, closest clock first.

        Closest-first rather than in play order: two plays can want the same
        row, and the one whose clock is nearer is the one that means it. In
        401772510 a penalty four seconds away took the row belonging to a
        touchdown three seconds away, and the touchdown went uncorrected.
        """
        nonlocal pending
        src = pool if source is None else source
        mark = used if seen is None else seen
        pairs = []
        for play in pending:
            pred = pred_for(play)
            if pred is None:
                continue
            clock = _secs(play.get("clock"))
            for j, r in enumerate(src):
                if j in mark or not pred(r):
                    continue
                rc = _secs(r.get("time"))
                gap = 0 if (clock is None or rc is None) else abs(rc - clock)
                if (exact and gap) or gap > tolerance:
                    continue
                pairs.append((gap, str(play.get("id")), j))
        pairs.sort()
        claimed: set[str] = set()
        for _, pid, j in pairs:
            if pid in claimed or j in mark:
                continue
            mark.add(j)
            claimed.add(pid)
            out[pid] = src[j]
        pending = [p for p in pending if str(p.get("id")) not in claimed]

    def flagged(play) -> bool:
        """ESPN keeps a nullified play; nflverse files it as a no-play. So a
        penalty belongs to the flag pool and must not compete for a real row -
        that is how a touchdown lost its row to the penalty before it."""
        return _espn_kind(play) == "penalty"

    def by_situation(play):
        sit = situation(play)
        if not sit[1] or flagged(play) or _espn_kind(play) in POSSESSION_CHANGES:
            return None
        return lambda r: row_situation(r) == sit

    def by_down(play):
        qtr, down, dist, _ = situation(play)
        if not down or flagged(play):
            return None
        kind = _espn_kind(play)
        return lambda r: (_i(r.get("qtr")) == qtr and _i(r.get("down")) == down
                          and _i(r.get("ydstogo")) == dist and _kind(r) == kind)

    def by_kind(play):
        if flagged(play):
            return None
        qtr, kind = play.get("period"), _espn_kind(play)
        return lambda r: _i(r.get("qtr")) == qtr and _kind(r) == kind

    sweep(by_situation, exact=True)     # same situation, same second
    sweep(by_situation, exact=False)    # same situation, clock drifted
    sweep(by_down, exact=False)         # same down and kind: a change of possession
    sweep(by_kind, exact=False)         # same kind in the quarter, nearest clock
    # The penalties, against the no-play rows they became.
    sweep(lambda p: (lambda r: _i(r.get("qtr")) == p.get("period")) if flagged(p) else None,
          exact=False, source=flags, seen=used_flags)
    # A penalty that was declined is a real play after all, so one is allowed
    # a real row once nothing else wants it.
    sweep(lambda p: (lambda r: row_situation(r) == situation(p)) if flagged(p) and situation(p)[1] else None,
          exact=False)
    return out


def _location(v) -> str | None:
    s = (v or "").strip().lower()
    return s if s in ("left", "middle", "right") else None


def facts(row: dict) -> dict:
    """What nflverse states about a play, in the scene's own vocabulary.

    Signed yardages are along the direction the offence attacks, which is how
    a path is laid out, so a path never has to know which way the game runs.
    """
    out: dict = {}
    air, yac = _f(row.get("air_yards")), _f(row.get("yards_after_catch"))
    if air is not None:
        out["airYards"] = round(air, 1)
    if yac is not None:
        out["yacYards"] = round(yac, 1)
    length = (row.get("pass_length") or "").strip().lower()
    if length in ("short", "deep"):
        out["passLength"] = length
    loc = _location(row.get("pass_location"))
    if loc:
        out["passLocation"] = loc
    loc = _location(row.get("run_location"))
    if loc:
        out["runLocation"] = loc
    gap = (row.get("run_gap") or "").strip().lower()
    if gap in ("end", "tackle", "guard"):
        out["runGap"] = gap
    for key, col in (("kickDistance", "kick_distance"), ("returnYards", "return_yards"),
                     ("penaltyYards", "penalty_yards"), ("yards", "yards_gained")):
        v = _f(row.get(col))
        if v is not None:
            out[key] = round(v, 1)
    for key, col in (("shotgun", "shotgun"), ("noHuddle", "no_huddle"), ("scramble", "qb_scramble")):
        v = _i(row.get(col))
        if v is not None:
            out[key] = bool(v)
    return out


def correct(plays: list[dict], rows: list[dict], event: str | None = None,
            tolerance: int = TOLERANCE_SECONDS) -> list[dict]:
    """`plays`, with every field nflverse states replaced in place.

    Pure: the input plays are not touched. Every play comes back carrying
    `truth`, whether or not it was corrected, so a client never has to guess
    which it is looking at:

        {"source": "live"|"corrected", "fields": [...], "estimated": [...],
         "gameId": ..., "playId": ...}
    """
    paired = match(plays, rows, tolerance)
    out = []
    for play in plays:
        pid = str(play.get("id") or "")
        row = paired.get(pid)
        if not row:
            out.append({**play, "truth": {"source": "live", "fields": [],
                                          "estimated": list(ESTIMATED_ALWAYS),
                                          "event": event}})
            continue
        stated = facts(row)
        fixed = {**play, **stated}
        fixed["truth"] = {
            "source": "corrected",
            "fields": sorted(stated),
            "estimated": list(ESTIMATED_ALWAYS),
            "event": event,
            "gameId": row.get("game_id"),
            "playId": str(_i(row.get("play_id")) or ""),
        }
        out.append(fixed)
    return out


def correct_for_espn(plays: list[dict], event: str, refresh: bool = False) -> tuple[list[dict], dict]:
    """`correct`, fetching the rows for an ESPN event. Returns (plays, report).

    A game nflverse has not published is not an error: the plays come back as
    live estimates and the report says the game is not covered yet.
    """
    rows, sched = nflverse.plays_for_espn(event, refresh=refresh)
    fixed = correct(plays, rows, event=event)
    n = sum(1 for p in fixed if (p.get("truth") or {}).get("source") == "corrected")
    return fixed, {
        "event": event,
        "gameId": (sched or {}).get("game_id"),
        "covered": bool(rows),
        "plays": len(plays),
        "corrected": n,
        "rate": round(100.0 * n / len(plays), 1) if plays else 0.0,
    }


# ────────────────────────────── measurement ────────────────────────────────

def _attack(play: dict, home_abbr: str) -> float:
    """+1 when the offence attacks the far (home) end in scene x, else -1."""
    return 1.0 if (play.get("team") or "").upper() == (home_abbr or "").upper() else -1.0


def compare(plays: list[dict], rows: list[dict], home_abbr: str = "",
            estimate_air=None, tolerance: int = TOLERANCE_SECONDS) -> dict:
    """Score the text-derived geometry against what nflverse states.

    `estimate_air(play)` returns the catch point the scene would guess, in
    yards downfield of the snap. Pass `scene.estimated_air_yards` to measure
    the live path; the result is the error a correction removes.
    """
    paired = match(plays, rows, tolerance)
    per: dict[str, list[float]] = {"start": [], "end": [], "air": [], "yards": []}
    kinds = {"same": 0, "differ": 0}
    worst: dict[str, tuple] = {}

    def note(key: str, err: float, play: dict):
        per[key].append(abs(err))
        if key not in worst or abs(err) > worst[key][0]:
            worst[key] = (abs(err), (play.get("text") or "")[:90])

    scrimmage = 0
    for play in plays:
        row = paired.get(str(play.get("id") or ""))
        if not row:
            continue
        espn_kind, nfl_kind = _espn_kind(play), _kind(row)
        # Spots are only comparable where both sources mean the same thing.
        # See POSSESSION_CHANGES: on a kickoff or a punt they do not.
        spots = espn_kind not in POSSESSION_CHANGES
        y100, end = _i(play.get("from")), _i(play.get("to"))
        truth_start = _i(row.get("yardline_100"))
        if spots:
            scrimmage += 1
            if y100 is not None and truth_start is not None:
                note("start", y100 - truth_start, play)
            gained = _f(row.get("yards_gained"))
            if end is not None and truth_start is not None and gained is not None:
                note("end", end - (truth_start - gained), play)
        stat, gained = _f(play.get("yards")), _f(row.get("yards_gained"))
        if stat is not None and gained is not None:
            note("yards", stat - gained, play)
        air = _f(row.get("air_yards"))
        if air is not None and estimate_air is not None:
            guess = estimate_air(play)
            if guess is not None:
                note("air", guess - air, play)
        same = (espn_kind == nfl_kind
                or (espn_kind == "pass" and nfl_kind in ("pass", "qb_spike"))
                or (espn_kind == "run" and nfl_kind in ("run", "qb_kneel"))
                or (espn_kind == "sack" and nfl_kind == "pass")
                # A nullified play: ESPN keeps it, nflverse files it as a
                # no-play. That correspondence is the match, not a difference.
                or (espn_kind == "penalty" and nfl_kind in ("no_play", "penalty")))
        kinds["same" if same else "differ"] += 1

    def stats(key: str) -> dict:
        v = per[key]
        if not v:
            return {"n": 0}
        return {"n": len(v), "mean": round(sum(v) / len(v), 2), "worst": round(max(v), 1),
                "exact": sum(1 for x in v if x < 0.5),
                "worstPlay": worst.get(key, (0, ""))[1]}

    return {
        "plays": len(plays),
        "matched": len(paired),
        "matchRate": round(100.0 * len(paired) / len(plays), 1) if plays else 0.0,
        "scrimmage": scrimmage,
        "startSpot": stats("start"),
        "endSpot": stats("end"),
        "airYards": stats("air"),
        "yardsGained": stats("yards"),
        "playType": kinds,
    }
