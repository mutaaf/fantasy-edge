"""A football game as geometry: the scene every renderer draws.

The headset is not the only surface. A web board, a phone and a tablet will
draw the same stadium, and the college app draws it too, so where a pass peaks,
which lane a run takes, when a touchdown lights a section and what colour a
club's chip is are decided here, once. Every client receives primitives - arcs,
lasers, a beacon, a horizon, bowl tiers, moments - and draws them. A client
that computed its own apex would be a second answer to a question with one.

This module knows nothing about fantasy football and imports nothing but the
standard library. Its only input is gamecast-shaped: two teams, a situation,
drives of plays with a type and a start and end yard line, win probability.
That is the seam that lets it move into a shared package later.

COORDINATES
-----------
Yards, right-handed, fixed to the field rather than to whoever has the ball:

  x  yards from the HOME goal line. 0 is the home goal line, 100 the away
     one; the end zones run -10..0 and 100..110. ESPN's `yardLine` is already
     this number - checked against every play of eighteen 2025 games, where
     `yardsToEndzone` is wrong on punts and a placeholder 0 on timeouts.
  z  yards across the field from its centre line, positive toward the home
     sideline.
  y  yards up.

The home team defends x = 0 and attacks toward 100.
"""

from __future__ import annotations

import colorsys
import json
import os
import pathlib

SCENE_VERSION = "1.0"

TOKENS_PATH = pathlib.Path(
    os.environ.get("FANTASYEDGE_TOKENS")
    or pathlib.Path(__file__).resolve().parent.parent / "design" / "tokens.json")

# What differs between codes of football, and nothing else. College is stubbed:
# its field geometry is here because the stadium is shared, and everything the
# scene does not yet use for it is left out rather than guessed.
RULES = {
    "nfl": {
        "field": {"length": 100.0, "endZone": 10.0, "width": 160 / 3,
                  # 70 ft 9 in in from each sideline; 18 ft 6 in apart.
                  "hashFromSideline": 23.583, "goalPostWidth": 6.167},
        "overtimeSeconds": 600,
    },
    "college-football": {
        "field": {"length": 100.0, "endZone": 10.0, "width": 160 / 3,
                  # 60 ft in from each sideline; 40 ft apart.
                  "hashFromSideline": 20.0, "goalPostWidth": 6.167},
        "overtimeSeconds": None,
        "stub": True,
    },
}

# Records that are clock rather than football. They are never drawn.
NOT_A_PLAY = {"timeout", "official timeout", "end period", "end of half",
              "end of game", "end of regulation", "two-minute warning",
              "coin toss", "end of quarter"}

BOWL = {
    "shape": {"type": "superellipse", "exponent": 4.0},
    "tiers": [
        {"name": "lower", "inner": 6.0, "outer": 36.0, "rise": [1.0, 19.6], "color": "bowl.lower"},
        {"name": "upper", "inner": 42.0, "outer": 70.0, "rise": [24.0, 45.8], "color": "bowl.upper"},
    ],
    "concourse": {"inner": 36.0, "outer": 42.0, "color": "bowl.concourse"},
    "rimLights": {"count": 10, "offset": 71.0, "height": 9.0, "side": "far",
                  "color": "rim.light"},
}

PRESENTATION = {
    # The lower bowl reaches 36 yards past the end line, so the tabletop is
    # sized for the bowl rather than the field: 96 yards either side of
    # midfield at 4.5 mm is 0.86 m, inside a 0.9 m volume. Sized for the field
    # alone, the bowl came out 1.28 m across and was clipped by the volume.
    "tabletop": {"metersPerYard": 0.0045, "volume": [0.9, 0.4, 0.6],
                 "floor": -0.18, "bowlTiers": ["lower"]},
    "stadium": {"metersPerYard": 0.9144, "seat": {"x": 50.0, "y": 8.0, "z": 42.7},
                "bowlTiers": ["lower", "upper"]},
    "horizon": {"z": -58.0, "y0": 52.0, "y1": 76.0},
    "beaconHeight": 34.0,
}


def load_tokens(path: pathlib.Path | str | None = None) -> dict:
    return json.loads(pathlib.Path(path or TOKENS_PATH).read_text())


# ───────────────────────────── colour ─────────────────────────────

def _rgb(hexs: str) -> tuple[float, float, float]:
    h = (hexs or "#666666").lstrip("#")
    if len(h) < 6:
        h = "666666"
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _hex(rgb) -> str:
    return "#" + "".join(f"{round(max(0.0, min(1.0, c)) * 255):02X}" for c in rgb)


def _lin(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def luminance(hexs: str) -> float:
    r, g, b = (_lin(c) for c in _rgb(hexs))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def chip(hexs: str, band: dict) -> str:
    """A club colour with its hue kept and its value solved into the band.

    Saturation gives way first when a hue cannot reach the band at any value -
    a pure blue is darker than the band even at full brightness - and a colour
    that was near-grey to begin with stays grey rather than acquiring a hue.
    """
    target = band["luminance"]
    h, s, _ = colorsys.rgb_to_hsv(*_rgb(hexs))
    s = 0.0 if s < band["neutralBelow"] else min(s, band["maxSaturation"])
    while s > 0 and luminance(_hex(colorsys.hsv_to_rgb(h, s, 1.0))) < target:
        s = max(0.0, s - 0.02)
    lo, hi = 0.0, 1.0
    for _ in range(32):
        mid = (lo + hi) / 2
        if luminance(_hex(colorsys.hsv_to_rgb(h, s, mid))) < target:
            lo = mid
        else:
            hi = mid
    return _hex(colorsys.hsv_to_rgb(h, s, (lo + hi) / 2))


def clash(a: str, b: str, band: dict) -> bool:
    (ha, sa, _), (hb, sb, _) = (colorsys.rgb_to_hsv(*_rgb(x)) for x in (a, b))
    if sa < band["neutralBelow"] and sb < band["neutralBelow"]:
        return True
    d = abs(ha - hb) * 360
    return (min(d, 360 - d) < band["clashDegrees"]
            and sa >= band["neutralBelow"] and sb >= band["neutralBelow"])


def team_chips(home: dict, away: dict, band: dict) -> tuple[dict, dict]:
    """Both chips, with the away side giving way when the two would read alike.

    Away takes its alternate colour if that is a real, different colour, and
    otherwise keeps its own and is marked `hatch` - a grey chip reads as "no
    team", not as the other team.
    """
    def one(t):
        return {"abbr": t.get("abbr", ""), "name": t.get("name", ""),
                "id": str(t.get("id", "")), "color": t.get("color", ""),
                "chip": chip(t.get("color", ""), band), "chipText": band["text"],
                "hatch": False, "score": t.get("score", 0)}
    h, a = one(home), one(away)
    if clash(h["chip"], a["chip"], band):
        alt = chip(away.get("altColor") or "", band)
        if away.get("altColor") and colorsys.rgb_to_hsv(*_rgb(alt))[1] >= band["neutralBelow"] \
                and not clash(alt, h["chip"], band):
            a["chip"] = alt
        else:
            a["hatch"] = True
    return h, a


# ───────────────────────────── plays ─────────────────────────────

def style_of(play: dict) -> tuple[str, str] | None:
    """(style, shape) for a play, or None for a clock record.

    Style decides colour and emphasis; shape decides the curve. They differ on
    purpose: a touchdown pass is styled `score` and still flies like a pass.
    """
    kind = (play.get("type") or "").strip().lower()
    if not kind or kind in NOT_A_PLAY:
        return None
    yards = play.get("yards") or 0
    if "kickoff" in kind or "punt" in kind or "field goal" in kind or "extra point" in kind:
        shape = "kick"
    elif "interception" in kind or "fumble" in kind:
        # The yards on a turnover are the return, run along the ground. Flown
        # as a pass, the 68-yard pick-six in 401772810 peaked 27 yards up.
        shape = "run"
    elif "incompletion" in kind or "pass" in kind or "reception" in kind:
        shape = "pass"
    elif "penalty" in kind:
        shape = "flat"
    else:
        shape = "run"
    if play.get("scoring"):
        return "score", shape
    if play.get("turnover"):
        return "turnover", shape
    if "penalty" in kind:
        return "penalty", "flat"
    if shape == "kick":
        return "kick", shape
    if "incompletion" in kind:
        return "incomplete", shape
    if "sack" in kind or (yards < 0 and shape in ("run", "pass")):
        return "loss", "run" if "sack" in kind else shape
    return shape, shape


def apex(shape: str, distance: float, tokens: dict) -> float:
    rule = tokens["arc"]["shape"][shape]
    return round(rule["apexBase"] + rule["apexPerYard"] * abs(distance), 3)


def seconds(style: str, distance: float, tokens: dict) -> float:
    """Roughly how long the play took in real time, clamped for animation."""
    rule = tokens["arc"]["seconds"].get(style) or tokens["arc"]["seconds"]["run"]
    motion = tokens["motion"]
    raw = rule["base"] + rule["perYard"] * abs(distance)
    return round(min(motion["maxSeconds"], max(motion["minSeconds"], raw)), 3)


def duration(real: float, speed: float, tokens: dict) -> float:
    """The animation length at a replay speed. Live is speed 1."""
    motion = tokens["motion"]
    factor = max(1.0, float(speed or 1.0) / motion["referenceSpeed"])
    return round(max(motion["floorSeconds"], real / factor), 3)


def lane(index: int, count: int, width: float, tokens: dict) -> float:
    """Where across the field a play is drawn. ESPN does not say where a play
    went laterally, so the drive is fanned across the middle only to keep its
    arcs from overlapping - a lane is a layout, not a claim."""
    spread = width * tokens["arc"]["laneSpread"]
    if count <= 1:
        return 0.0
    return round(-spread + 2 * spread * index / (count - 1), 3)


def _side(team_abbr: str, home: dict, away: dict) -> str | None:
    if team_abbr and team_abbr == home.get("abbr"):
        return "home"
    if team_abbr and team_abbr == away.get("abbr"):
        return "away"
    return None


def _num(v, default=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def moment_kind(play: dict, points: float) -> str:
    kind = (play.get("type") or "").lower()
    text = (play.get("text") or "").upper()
    if "touchdown" in kind or "TOUCHDOWN" in text:
        return "touchdown"
    if "safety" in kind or "SAFETY" in text:
        return "safety"
    if "field goal" in kind or points == 3:
        return "fieldGoal"
    return "score"


# ───────────────────────────── the scene ─────────────────────────────

def build(game: dict, league: str = "nfl", speed: float = 1.0,
          tokens: dict | None = None) -> dict:
    """The scene for one game at one instant. Pure: `game` is not touched."""
    tokens = tokens or load_tokens()
    rules = RULES.get(league)
    if rules is None:
        raise ValueError(f"no field rules for {league!r}; known: {', '.join(RULES)}")
    field = dict(rules["field"])
    width = field["width"]
    band = tokens["chip"]
    home, away = team_chips(game.get("home") or {}, game.get("away") or {}, band)
    sit = game.get("situation") or {}

    drives_out, moments = [], []
    prev_home = prev_away = 0.0
    last_ref = None
    raw_drives = game.get("drives") or []
    for di, drive in enumerate(raw_drives):
        plays = [p for p in (drive.get("plays") or []) if style_of(p)]
        arcs = []
        for pi, play in enumerate(plays):
            style, shape = style_of(play)
            x0, x1 = play.get("fromYard"), play.get("toYard")
            if x0 is None or x1 is None:
                continue
            dist = abs(_num(x1) - _num(x0))
            real = seconds(style, dist, tokens)
            arcs.append({
                "id": str(play.get("id", "")),
                "style": style, "shape": shape,
                "type": play.get("type", ""),
                "fromX": _num(x0), "toX": _num(x1),
                "lane": lane(pi, len(plays), width, tokens),
                "apex": apex(shape, dist, tokens),
                "color": f"arc.{style}",
                "dash": tokens["arc"]["dash"].get(style),
                "seconds": real,
                "duration": duration(real, speed, tokens),
                "side": _side(play.get("team") or drive.get("team", ""), home, away),
                "text": play.get("text", ""),
                "period": play.get("period"), "clock": play.get("clock", ""),
                "down": play.get("down"), "distance": play.get("distance"),
            })
            last_ref = (len(drives_out), len(arcs) - 1)
        for play in (drive.get("plays") or []):
            h, a = _num(play.get("home"), prev_home), _num(play.get("away"), prev_away)
            if h > prev_home or a > prev_away:
                scorer = "home" if h - prev_home >= a - prev_away else "away"
                points = max(h - prev_home, a - prev_away)
                moments.append({"kind": moment_kind(play, points), "side": scorer,
                                "team": (home if scorer == "home" else away)["abbr"],
                                "points": points, "playId": str(play.get("id", "")),
                                "text": play.get("text", ""),
                                "period": play.get("period"), "clock": play.get("clock", "")})
            elif play.get("turnover") and style_of(play):
                offense = _side(play.get("team") or drive.get("team", ""), home, away)
                taker = {"home": "away", "away": "home"}.get(offense)
                if taker:
                    moments.append({"kind": "turnover", "side": taker,
                                    "team": (home if taker == "home" else away)["abbr"],
                                    "points": 0, "playId": str(play.get("id", "")),
                                    "text": play.get("text", ""),
                                    "period": play.get("period"),
                                    "clock": play.get("clock", "")})
            # A running maximum, not the last record's score. After a
            # touchdown ESPN's timeout records can carry the score from before
            # the conversion - 38, then 36, 36, then 38 again at "End of Game"
            # in 401772949 - and trusting the dip invents a second score.
            prev_home, prev_away = max(prev_home, h), max(prev_away, a)
        drives_out.append({"id": str(drive.get("id", "")), "team": drive.get("team", ""),
                           "side": _side(drive.get("team", ""), home, away),
                           "result": drive.get("result", ""), "arcs": arcs})

    state = game.get("state", "pre")
    current = len(drives_out) - 1 if drives_out and state == "in" else None

    # The instant's moment: the newest one, but only while its play is still
    # the last thing that happened. A touchdown from the first quarter is not
    # lighting a section in the third.
    # A moment holds until the game clock moves. The try, a timeout and the
    # kickoff that follow a touchdown all carry its clock - 12:51 for the
    # pick-six in 401772810 - so they arrive in the same poll, and "until the
    # next drawn play" cleared the touchdown before a single frame showed it.
    active = None
    if moments:
        newest = moments[-1]
        drawn = [(a["id"], a["period"], a["clock"]) for d in drives_out for a in d["arcs"]]
        ids = [x[0] for x in drawn]
        if newest["playId"] in ids:
            after = drawn[ids.index(newest["playId"]) + 1:]
            if all((p, c) == (newest["period"], newest["clock"]) for _, p, c in after):
                active = newest
        elif drawn and (drawn[-1][1], drawn[-1][2]) == (newest["period"], newest["clock"]):
            active = newest
    # While a moment holds, the drive to show is the one it happened in. The
    # kickoff after a touchdown starts the next drive on the same clock, and
    # showing that drive put a kick arc in the air under a TOUCHDOWN banner
    # while the scoring play itself was nowhere to be seen.
    if active and state == "in":
        for i, d in enumerate(drives_out):
            if any(a["id"] == active["playId"] for a in d["arcs"]):
                current = i
                break

    possession = sit.get("possession")
    holder = "home" if possession and str(possession) == home["id"] else \
        "away" if possession and str(possession) == away["id"] else None
    ball, lasers = None, []
    yard_line = sit.get("yardLine")
    if state == "in" and yard_line is not None:
        x = _num(yard_line)
        scoring = bool(active and active["kind"] in ("touchdown", "fieldGoal", "safety"))
        ball = {"x": x, "y": 0.0, "z": 0.0,
                "beacon": {"height": PRESENTATION["beaconHeight"],
                           "color": "beacon.score" if scoring else "beacon"}}
        lasers.append({"kind": "scrimmage", "x": x, "color": "laser.scrimmage"})
        dist, to_goal = sit.get("distance"), sit.get("yardsToEndzone")
        if holder and dist and (to_goal is None or _num(dist) < _num(to_goal)):
            step = 1.0 if holder == "home" else -1.0
            lasers.append({"kind": "lineToGain", "x": x + step * _num(dist),
                           "color": "laser.lineToGain"})

    wp = [w.get("home") for w in (game.get("winProbability") or [])
          if w.get("home") is not None]
    tint_side = active["side"] if active and active["kind"] != "turnover" else None
    bowl = json.loads(json.dumps(BOWL))
    bowl["shape"].update({"halfLength": field["length"] / 2 + field["endZone"],
                          "halfWidth": width / 2})
    bowl["crowd"] = {"home": home["color"] or home["chip"], "away": away["color"] or away["chip"],
                     "neutral": "crowd.neutral", "dark": "crowd.dark",
                     "awaySection": {"side": "far", "fromX": 90.0}}
    bowl["sectionTint"] = {"side": tint_side,
                           "color": (home if tint_side == "home" else away)["chip"]
                           if tint_side else None,
                           "dim": tokens["motion"]["sectionDim"]}

    return {
        "version": SCENE_VERSION,
        "kind": "football-scene",
        "league": league,
        "event": str(game.get("event", "")),
        "source": "replay" if game.get("replay") else "live",
        "replay": game.get("replay"),
        "speed": float(speed or 1.0),
        "units": {"length": "yard", "time": "second"},
        "axes": {"x": "yards from the home goal line; end zones -10..0 and 100..110",
                 "z": "yards from the centre line, positive toward the home sideline",
                 "y": "yards up"},
        "field": {**field, "league": league, "stripeEvery": 5, "numbersEvery": 10,
                  "homeEndZone": [-field["endZone"], 0.0],
                  "awayEndZone": [field["length"], field["length"] + field["endZone"]]},
        "teams": {"home": home, "away": away},
        "status": {"state": state, "label": game.get("label", ""),
                   "clock": game.get("clock", ""), "period": game.get("period", 0),
                   "homeScore": home["score"], "awayScore": away["score"],
                   "possession": holder, "down": sit.get("down"),
                   "distance": sit.get("distance"),
                   "downDistance": sit.get("downDistanceText") or "",
                   "redZone": bool(sit.get("isRedZone"))},
        "ball": ball,
        "lasers": lasers,
        "drives": drives_out,
        "currentDrive": current,
        "winProbability": {"side": "home", "series": wp,
                           "horizon": {**PRESENTATION["horizon"],
                                       "x0": -field["endZone"],
                                       "x1": field["length"] + field["endZone"]}},
        "moments": moments,
        "activeMoment": active,
        "bowl": bowl,
        "presentation": PRESENTATION,
        "palette": tokens["color"],
        "motion": tokens["motion"],
    }
