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
import math
import os
import pathlib
import re

SCENE_VERSION = "1.3"

TOKENS_PATH = pathlib.Path(
    os.environ.get("FANTASYEDGE_TOKENS")
    or pathlib.Path(__file__).resolve().parent.parent / "design" / "tokens.json")

# What differs between codes of football, and nothing else. Both codes are
# stated in full: a college field's hash marks are 60 ft in rather than 70 ft
# 9 in, its uprights stand 30 ft above the crossbar rather than 35, its team
# area runs between the 20s rather than the 30s, and its overtime has no clock.
# The league is read from the game (`league_of`), never from the caller.
# ═══════════════════════ actor sections (docs/ART_BIBLE.md) ═══════════════════════
# Each block below is owned by one stadium actor. The spec's shape does not
# change with this layout; it only says whose numbers are whose.
#
#   field       RULES[league].field            -> scene.field
#   sideline    _props()                       -> scene.field.props
#   bowl        BOWL tiers/wall/ribbon/pressBox/tunnels -> scene.bowl
#   lighting    BOWL["rimLights"]              -> scene.bowl.rimLights
#   crowd       build(): crowd, sectionTint    -> scene.bowl.crowd, .sectionTint
#   broadcast   build(): drives, ball, lasers, winProbability, PRESENTATION horizon/beacon
#   moments     build(): moments, activeMoment
#   experience  SEATS, PRESENTATION            -> scene.presentation
#   every actor tokens.json visual.<actor>     -> scene.visual.<actor>

# ── sideline ──

def _props(bench_from: float, bench_to: float, upright_above: float,
           ground_markers: bool = False) -> dict:
    """The sideline furniture, in yards. Both codes share its shape; where
    they differ - the team area and the upright height - is an argument.

    The goal post stands on the end line: a base two yards behind it, a
    gooseneck forward, a crossbar 10 ft up and uprights 18 ft 6 in apart
    (field.goalPostWidth). The NFL builds its uprights 35 ft above the bar
    (2026 Rule 1 §3 Art.2); NCAA 1-2-5-a only asks for tops 30 ft off the
    ground, and college posts are built 30 ft above the bar.

    The benches sit 3.8 yd off the sideline because the bowl's front wall is
    5.4 yd out. The NFL wants them at least 30 ft 4 in back (field diagram
    note 1): that needs a wider apron than this bowl has, and is the bowl's
    change to make, not the benches'."""
    return {
        "goalpost": {"baseBehind": 2.0, "crossbar": 3.333, "uprightAbove": upright_above,
                     "radius": {"base": 0.13, "crossbar": 0.09, "upright": 0.06},
                     "padHeight": 2.2, "padWidth": 0.7, "color": "prop.goalpost"},
        "pylon": {"size": 4 / 36, "height": 0.5, "color": "prop.pylon"},
        "benches": {"fromX": bench_from, "toX": bench_to, "offset": 3.8,
                    "height": 0.5, "depth": 0.7, "backHeight": 0.65, "color": "prop.bench"},
        # The chain crew works the visitors' sideline. `groundMarkers` is the
        # pair of markers laid on the line to gain on both sidelines, which
        # college uses and the NFL does not (NCAA 1-2-4-b). It is stated here,
        # not decided in a renderer: which props a code puts on the field is a
        # rule of that code, and the ports read the same answer.
        "chains": {"length": 10.0, "offset": 2.5, "poleHeight": 2.0, "markerWidth": 0.5,
                   "side": "away", "groundMarkers": ground_markers, "color": "prop.chain"},
    }


# ── the line the boards read ──


def period_label(period: int, league: str) -> str:
    """"4th", or "2OT" once regulation is over. Both codes play four quarters;
    they differ in what an overtime is, not in how many precede it."""
    if period > 4:
        extra = period - 4
        return "OT" if extra == 1 else f"{extra}OT"
    return {1: "1st", 2: "2nd", 3: "3rd", 4: "4th"}.get(period, f"Q{period}")


def status_label(game: dict, state: str, league: str) -> str:
    """What the scoreboard says about the clock, when the payload does not say
    it itself.

    A gamecast that states a `label` has already decided this and wins. One
    that does not is not a reason for the boards to go blank: every fact here
    - the state, the period, the clock, how many overtimes - is stated
    somewhere in the payload, and the league's rules say whether an overtime
    has a clock to show. College overtime is untimed, so "2OT" is the whole
    truth there; an NFL overtime reads "2:43 OT" like any other period.
    """
    st = game.get("status") or {}
    period = int(game.get("period") or st.get("period") or 0)
    if state == "post":
        overtimes = int(st.get("overtimes") or max(0, period - 4))
        if overtimes <= 0:
            return "Final"
        return "Final/OT" if overtimes == 1 else f"Final/{overtimes}OT"
    if state != "in":
        return "Pre-game"
    if st.get("halftime"):
        return "Halftime"
    if st.get("delayed"):
        return "Delay"
    if period <= 0:
        return ""
    label = period_label(period, league)
    clock = (game.get("clock") or st.get("clock") or "").strip()
    if period > 4 and RULES.get(league, {}).get("overtimeSeconds") is None:
        return label          # untimed: a college overtime has no clock to show
    return f"{clock} {label}".strip()


# ── field ──

RULES = {
    "nfl": {
        "field": {"length": 100.0, "endZone": 10.0, "width": 160 / 3,
                  # 70 ft 9 in in from each sideline; 18 ft 6 in apart.
                  "hashFromSideline": 23.583, "goalPostWidth": 6.167},
        "overtimeSeconds": 600,
        # Benches between the 30-yard lines (field diagram note 8), uprights
        # 35 ft above the crossbar (Rule 1 §3 Art.2).
        "props": _props(30.0, 70.0, 35 / 3),
    },
    "college-football": {
        "field": {"length": 100.0, "endZone": 10.0, "width": 160 / 3,
                  # 60 ft in from each sideline; 40 ft apart.
                  "hashFromSideline": 20.0, "goalPostWidth": 6.167},
        "overtimeSeconds": None,
        # The team area runs between the 20-yard lines (NCAA 1-2-4-a); posts
        # are built 30 ft above the crossbar (1-2-5-a sets the 30 ft floor);
        # and the line to gain is marked on the ground on both sidelines.
        "props": _props(20.0, 80.0, 10.0, ground_markers=True),
    },
}

# What ESPN calls each league, in the places it says so. A summary's header
# carries `league.abbreviation`, and every payload carries a `uid` of the form
# `s:20~l:23~e:401858224`, where the `l:` is the league. Both are checked
# because a gamecast keeps the uid when it has dropped the header.
ESPN_LEAGUE = {"nfl": "nfl", "ncaaf": "college-football",
               "college-football": "college-football"}
ESPN_LEAGUE_UID = {"28": "nfl", "23": "college-football"}


def league_of(payload: dict, default: str = "nfl") -> str:
    """Which code this game is played under, read from the payload.

    The league is a property of the game, not of the caller: a college game
    drawn with NFL hash marks puts every play 3.58 yards off across, and does
    it silently. So it is derived here, once, and `build` uses it unless a
    caller insists otherwise.

    Returns `default` when nothing in the payload says, which is honest for a
    hand-built fixture and wrong for nothing: a real ESPN payload always says.
    """
    if not isinstance(payload, dict):
        return default
    stated = str(payload.get("league") or "").strip().lower()
    if stated in RULES:
        return stated
    if stated in ESPN_LEAGUE:
        return ESPN_LEAGUE[stated]
    head = payload.get("header") or {}
    league = head.get("league") if isinstance(head, dict) else None
    if isinstance(league, dict):
        abbr = str(league.get("abbreviation") or "").strip().lower()
        if abbr in ESPN_LEAGUE:
            return ESPN_LEAGUE[abbr]
    for source in (payload, head):
        uid = str((source or {}).get("uid") or "")
        for part in uid.split("~"):
            if part.startswith("l:") and part[2:] in ESPN_LEAGUE_UID:
                return ESPN_LEAGUE_UID[part[2:]]
    return default

# ── field: painted art and pylon spots ──
#
# The markings themselves - lines, hashes, numerals, arrows - are baked from
# the rulebooks into assets/actors/field/markings by tools/blender/field; the
# scene only says where the two things that change per game go: each club's
# name across its end zone and the home club's ring at midfield. Glyph shapes
# are an asset (fonts/glyphs.json), so a client applies the layout below to
# them and typesets nothing itself.

GLYPHS_PATH = pathlib.Path(__file__).resolve().parent.parent / "assets" / "actors" / "field" / "fonts" / "glyphs.json"
_GLYPHS: dict | None = None
_FT = 1 / 3


def _glyphs() -> dict | None:
    global _GLYPHS
    if _GLYPHS is None and GLYPHS_PATH.is_file():
        _GLYPHS = json.loads(GLYPHS_PATH.read_text())
    return _GLYPHS


def text_width(text: str, font: dict, tracking: float = 0.08) -> float:
    """Width of a line in em units (cap height 1), as a client lays it out:
    each glyph advances by its ink width plus `tracking`, a space by
    `font.space`, and unknown characters are skipped."""
    pen, drawn = 0.0, False
    for ch in text.upper():
        if ch == " ":
            pen += font["space"]
            continue
        g = font["glyphs"].get(ch)
        if not g:
            continue
        pen += g["width"] + tracking
        drawn = True
    return max(0.0, pen - tracking) if drawn else 0.0


def club_lines(club: dict) -> tuple[str, str]:
    """The two lines a club letters its end zones with: its nickname at the end
    it defends, its location at the other.

    That is how a split field reads (Soldier Field paints BEARS and CHICAGO).
    A club that gives only one name letters it at both ends, which is equally
    real - Lambeau paints PACKERS twice - and is the only honest answer when
    the parts are not known: splitting a display name on its last word invents
    "NOTRE DAME FIGHTING" and "IRISH".
    """
    full = (club.get("name") or club.get("abbr") or "").strip().upper()
    nick = (club.get("nickname") or "").strip().upper()
    loc = (club.get("location") or "").strip().upper()
    if nick and loc and nick != loc:
        return nick, loc
    one = nick or full
    return one, one


def field_art(field: dict, league: str, home: dict, away: dict,
              paint: dict | None = None, turf: str = "#1E6A34") -> dict | None:
    """Where the home club's name and the midfield ring are painted.

    **The field belongs to the home club.** Both end zones carry its name and
    its colour, and the ring at midfield is its own; a visiting club is not
    painted on someone else's field, and the away side appears in the stands
    (`bowl.crowd`), not on the grass. `away` is still taken because the end
    zone the visitors defend is named for them positionally (`side`), not
    lettered for them.

    **The paint is the club's own colour, not its chip.** A chip is solved
    onto one luminance band so white text clears 4.5:1 in a panel; across a
    thousand square yards it lightens a club past what it is - it painted
    Chicago's navy `#0B162A` as `#366CCD` and both Las Vegas and Pittsburgh's
    black as a mid-grey. Measured over all 34 clubs a fixture here states, the
    club's own colour is the better answer on both counts that matter: the
    worst separation from the grass rises from dE 7.8 to 15.3, because the
    chip band sits near the grass's own luminance, and the lettering stays
    readable because its ink is chosen per club rather than assumed white.

    A text layout maps glyph space to the field: a glyph point (gx, gy) in
    em units lands at origin + (gx * along + gy * up) * capHeight, in (x, z)
    yards. Each name reads from the field of play with its letters' tops
    toward the end line; the midfield name reads from the home sideline. One
    cap height serves both ends, so a long word at one end cannot letter it
    smaller than the other. Clearance follows NCAA 1-2-1-d, four feet from any
    line, which never breaks the NFL's Commissioner-approved rule; midfield
    art stays inside the hashes for college (1-2-1-g-3) and inside the numbers
    for the NFL.
    """
    font = _glyphs()
    if not font:
        return None
    paint = paint or {"white": "#DADAD3", "ink": "#12140F", "endZoneOpacity": 0.8}
    club = (home.get("color") or "").strip() or home.get("chip", "#DADAD3")
    if not club.startswith("#"):
        club = "#" + club
    ink = letter_ink(club, turf, paint["endZoneOpacity"], paint)
    tracking = 0.08
    w = field["width"]
    clear = 4 * _FT
    goal_line = 8 / 36
    depth = field["endZone"] - goal_line - 2 * clear
    span = w - 2 * clear
    near, far = club_lines(home)
    ends = (
        ("home", near, -field["endZone"] / 2 - goal_line / 2, (0.0, -1.0), (-1.0, 0.0)),
        ("away", far, field["length"] + field["endZone"] / 2 + goal_line / 2, (0.0, 1.0), (1.0, 0.0)))
    widths = {side: text_width(text, font, tracking) for side, text, *_ in ends}
    fits = [min(5.0, depth * 0.78, span * 0.92 / width) for width in widths.values() if width]
    cap = min(fits) if fits else 0.0
    zones = []
    for side, text, x_mid, along, up in ends:
        width = widths[side]
        if not width:
            continue
        # centre: half the width back along `along`, half the cap back along `up`
        ox = x_mid - (width * cap / 2) * along[0] - (cap / 2) * up[0]
        oz = 0.0 - (width * cap / 2) * along[1] - (cap / 2) * up[1]
        zones.append({"side": side, "text": text, "capHeight": round(cap, 4),
                      "origin": [round(ox, 4), round(oz, 4)], "along": list(along), "up": list(up),
                      "tint": ink, "fill": "home", "paint": club})
    hash_in = field["hashFromSideline"]
    if league == "college-football":
        half_span = w / 2 - hash_in - 1 * _FT
    else:
        half_span = w / 2 - (12.0 + 2.0) - 1.0          # inside the numerals' tops
    radius = min(8.0, half_span)
    # The ring reads as a mark without being anyone's: a circle struck from the
    # club's own chip with the club's name set inside it. No club's device is
    # copied or approximated, here or anywhere else on the field.
    name = club_lines(home)[0] or (home.get("name") or home.get("abbr") or "").upper()
    width = text_width(name, font, tracking)
    inner = radius * 0.86
    mid = {"center": [50.0, 0.0], "outer": round(radius, 4), "inner": round(inner, 4),
           "tint": "home", "paint": club}
    if width:
        cap = min(inner * 0.55, (2 * inner * 0.8) / width)
        mid["text"] = {"text": name, "capHeight": round(cap, 4),
                       "origin": [round(50.0 - width * cap / 2, 4), round(cap / 2, 4)],
                       "along": [1.0, 0.0], "up": [0.0, -1.0], "tint": ink}
    return {"glyphs": "actors/field/fonts/glyphs.json", "tracking": tracking,
            "endZones": zones, "midfield": mid}


def pylon_spots(field: dict, league: str, size: float) -> list[list[float]]:
    """Pylon centres in (x, z) yards, each standing just outside the line it
    marks, touching its inside edge.

    Both codes put eight at the sidelines: the four front corners of the end
    zones, where the goal lines meet the sidelines, and the four back corners,
    where the end lines do (NFL Rule 1 §2 Art.3; NCAA 1-2-6). College adds
    four more where the inbounds lines extended meet the end lines, three feet
    beyond them (1-2-6); the NFL has none there.

    This was wrong in both codes until the league audit, and the count hid it:
    the NFL was drawn with its four back corners missing and four college hash
    pylons standing in the end zone instead, which is 8 either way. A test that
    counts pylons cannot see that, so `test_league.py` checks where they are.
    """
    half = field["width"] / 2
    s = size / 2
    end = field["endZone"]
    length = field["length"]
    spots = []
    for z in (-half - s, half + s):
        spots += [[-s, z], [length + s, z]]                               # goal line x sideline
        spots += [[-end - s, z], [length + end + s, z]]                   # end line x sideline
    if league == "college-football":
        hash_z = half - field["hashFromSideline"]
        back = 1.0                                                        # three feet off (1-2-6)
        for z in (-hash_z, hash_z):
            spots += [[-end - s - back, z], [length + end + s + back, z]]
    return [[round(x, 4), round(z, 4)] for x, z in spots]


# Records that are clock rather than football. They are never drawn.
NOT_A_PLAY = {"timeout", "official timeout", "end period", "end of half",
              "end of game", "end of regulation", "two-minute warning",
              "coin toss", "end of quarter"}

# ── bowl (and lighting's rimLights) ──

BOWL = {
    "shape": {"type": "superellipse", "exponent": 4.0},
    "tiers": [
        {"name": "lower", "inner": 6.0, "outer": 36.0, "rise": [1.0, 19.6], "color": "bowl.lower"},
        {"name": "upper", "inner": 42.0, "outer": 70.0, "rise": [24.0, 45.8], "color": "bowl.upper"},
    ],
    "concourse": {"inner": 36.0, "outer": 42.0, "color": "bowl.concourse"},
    # Light banks just beyond the outermost tier a renderer draws - the upper
    # deck in the stadium, the lower on the tabletop - `beyondOuter` yards out.
    # How high above that tier's top they stand is visual.lighting.rim.heightAbove.
    # side "all": a real bowl is lit from every side, so banks stand all the
    # way round; the ones facing the seats (z <= farSideMaxZ) carry the
    # detailed model and the beams, the rest the cheap one. "far" draws only
    # the banks facing the seats.
    "rimLights": {"count": 16, "beyondOuter": 1.0, "side": "all", "color": "rim.light"},
    # The stands' front wall, lined with LED boards, short of the first row;
    # the ribbon board on the upper deck's fascia, all the way round; the
    # press box in the far concourse; tunnels under each end zone.
    "wall": {"offset": 5.4, "height": 1.4, "color": "board.base"},
    "ribbon": {"offset": 41.6, "rise": [21.0, 23.6], "color": "ribbon.base", "text": "ribbon.text"},
    # The press box stands on the far side's parapet, above the top row: under
    # the upper deck its floor (19.6) was level with the lower bowl's top rows,
    # and no floor between the decks (4.4 yd of room under the ribbon) clears
    # them. Up here the box seat's eye sees the near sideline over the upper
    # deck's last row and its fans (tests/test_bowl.py). It spans the gap
    # between two rim light rigs, so it is shorter than the old room.
    "pressBox": {"side": "far", "fromX": 21.0, "toX": 79.0, "offset": 71.5, "depth": 5.0,
                 "rise": [49.0, 52.6], "mullionEvery": 3.0, "glass": "pressbox.glass",
                 "glassBrightness": 0.38},
    "tunnels": [{"x": -16.0, "width": 7.0, "height": 3.2},
                {"x": 116.0, "width": 7.0, "height": 3.2}],
    # How the stands are divided and seated. A seat is 20 in on centre, an
    # aisle 44 in; sections run radially so aisles line up row to row. Every
    # Nth section carries a vomitory through the rows named, with an accessible
    # platform on the row in front of it. Tunnel rows are cut where a row's
    # tread is lower than the tunnel's height plus `tunnelClear`.
    "seating": {"pitch": 0.55, "aisle": 1.2, "feetDepth": 0.38,
                "seatsPerSection": {"lower": 24, "upper": 26},
                "vomitory": {"lower": {"every": 3, "phase": 1, "rows": [11, 16], "width": 3.0},
                             "upper": {"every": 4, "phase": 2, "rows": [7, 11], "width": 3.0}},
                "accessibleMargin": 1.1, "tunnelClear": 0.25, "holeClear": 0.3,
                "startAngle": 1.5707963267948966},
    # The video board behind the away (east) end zone, standing on the parapet
    # above the upper deck's sightline from the far sideline. `centre` is the
    # middle of the LED face in field yards (x from the home goal line); the
    # face looks along `facing` toward midfield; `size` is width x height in
    # yards. The bowl builds its frame and truss; Broadcast draws on the face.
    "videoBoard": {"centre": [182.5, 57.0, 0.0], "facing": [-0.9903, -0.1392, 0.0],
                   "size": [36.0, 13.5], "screen": "board.base"},
    # The rim the upper tier ends in: a parapet this far out and this high.
    # Light rigs stand on it (`mounts.rim`).
    "parapet": {"offset": 70.6, "top": 47.6},
}


# The bowl's curve, rows and seats. Pure arithmetic, reproduced exactly by
# SceneMath (bowlPoint, inward, row, evenAngles), so every client lands a seat
# on the same spot of the same row.

def bowl_point(shape: dict, m: float, t: float) -> tuple[float, float]:
    a, b = shape["halfLength"] + m, shape["halfWidth"] + m
    e = 2 / shape["exponent"]
    c, s = math.cos(t), math.sin(t)
    return (a * math.copysign(abs(c) ** e, c), b * math.copysign(abs(s) ** e, s))


def bowl_inward(shape: dict, m: float, t: float) -> tuple[float, float]:
    e = 1e-3
    ax, az = bowl_point(shape, m, t - e)
    bx, bz = bowl_point(shape, m, t + e)
    nx, nz = -(bz - az), bx - ax
    hx, hz = bowl_point(shape, m, t)
    if nx * hx + nz * hz > 0:
        nx, nz = -nx, -nz
    n = math.hypot(nx, nz) or 1e-9
    return (nx / n, nz / n)


class BowlRing:
    """A superellipse at offset m, walked by arc length from angle 0."""

    RES = 2880

    def __init__(self, shape: dict, m: float):
        self.shape, self.m = shape, m
        self.t = [2 * math.pi * i / self.RES for i in range(self.RES + 1)]
        self.cum = [0.0]
        px, pz = bowl_point(shape, m, 0.0)
        for t in self.t[1:]:
            x, z = bowl_point(shape, m, t)
            self.cum.append(self.cum[-1] + math.hypot(x - px, z - pz))
            px, pz = x, z
        self.length = self.cum[-1]

    def angle(self, s: float) -> float:
        s %= self.length
        lo, hi = 0, self.RES
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if self.cum[mid] <= s:
                lo = mid
            else:
                hi = mid
        span = self.cum[hi] - self.cum[lo] or 1e-9
        return self.t[lo] + (self.t[hi] - self.t[lo]) * (s - self.cum[lo]) / span

    def arc_at(self, t: float) -> float:
        """Arc length at angle t, interpolated. On the straights a superellipse
        covers most of its length in a sliver of angle, so rounding to the
        nearest sample was off by up to a yard and a half."""
        f = (t % (2 * math.pi)) / (2 * math.pi) * self.RES
        i = min(self.RES - 1, int(f))
        u = f - i
        return self.cum[i] + (self.cum[i + 1] - self.cum[i]) * u


def bowl_row(tier: dict, r: int, rows: int) -> dict:
    """SceneMath.row, exactly."""
    n = max(1, rows)
    depth = (tier["outer"] - tier["inner"]) / n
    front = tier["inner"] + depth * r
    rise = tier["rise"][1] - tier["rise"][0]
    return {"front": front, "back": front + depth,
            "tread": tier["rise"][0] + rise * (r + 1) / n,
            "riserFrom": tier["rise"][0] + rise * r / n}


def _bowl_side(shape: dict, t: float) -> str:
    x, z = bowl_point(shape, 0.0, t)
    if abs(x) > shape["halfLength"] - 2 and abs(z) < shape["halfWidth"]:
        return "east" if x > 0 else "west"
    return "home" if z > 0 else "far"


def bowl_sections(shape: dict, tier: dict, cfg: dict) -> list[dict]:
    """Radial sections by arc-length fraction at the tier's middle row,
    numbered from the home 50-yard line (1xx lower, 3xx upper)."""
    name = tier["name"]
    mid = BowlRing(shape, (tier["inner"] + tier["outer"]) / 2)
    width = cfg["seatsPerSection"][name] * cfg["pitch"] + cfg["aisle"]
    count = max(8, round(mid.length / width))
    start = mid.arc_at(cfg["startAngle"]) / mid.length
    base = {"lower": 100, "upper": 300}.get(name, 500)
    v = cfg["vomitory"].get(name)
    out = []
    for k in range(count):
        f0 = (start + k / count) % 1.0
        t_mid = mid.angle((f0 + 0.5 / count) * mid.length)
        out.append({"id": str(base + k + 1), "from": round(f0, 6), "to": round(f0 + 1 / count, 6),
                    "side": _bowl_side(shape, t_mid),
                    "vomitory": bool(v and k % v["every"] == v["phase"])})
    return out


def bowl_gaps(shape: dict, tier: dict, r: int, rows: int, secs: list[dict], ring: BowlRing,
              cfg: dict, tunnels: list[dict]) -> list[tuple[float, float, str]]:
    """Arc-length stretches of a row with no seats: aisles, vomitories, the
    accessible platform in front of each, and team tunnels."""
    L = ring.length
    gaps = []
    v = cfg["vomitory"].get(tier["name"])
    for sec in secs:
        s = sec["from"] * L
        gaps.append((s - cfg["aisle"] / 2, s + cfg["aisle"] / 2, "aisle"))
        if v and sec["vomitory"]:
            c = (sec["from"] + sec["to"]) / 2 * L
            half = v["width"] / 2
            if v["rows"][0] <= r <= v["rows"][1]:
                gaps.append((c - half, c + half, "vomitory"))
            elif r == v["rows"][0] - 1:
                gaps.append((c - half - cfg["accessibleMargin"], c + half + cfg["accessibleMargin"], "accessible"))
    if tier["name"] == "lower":
        tread = bowl_row(tier, r, rows)["tread"]
        for tn in tunnels:
            if tread < tn["height"] + cfg["tunnelClear"]:
                s = ring.arc_at(0.0 if tn["x"] > 50 else math.pi)
                half = tn["width"] / 2 + 1.0
                gaps.append((s - half, s + half, "tunnel"))
    return gaps


def _covered(s: float, gaps, L: float) -> bool:
    for a, b, _ in gaps:
        for off in (-L, 0.0, L):
            if a + off <= s <= b + off:
                return True
    return False


_SEATING_CACHE: dict = {}


def bowl_seating(shape: dict, rows: dict) -> dict:
    """Every seat as runs along its row: `[firstArc, count]` in yards along the
    row's ring (offset `feet`, walked from angle 0), `pitch` apart. A client
    finds seat k of a run at arc firstArc + k * pitch, turns it into an angle
    by inverting arc length (SceneMath.evenAngles' walk), and faces it along
    SceneMath.inward. The same numbers build the Blender kit."""
    key = (shape["halfLength"], shape["halfWidth"], shape["exponent"], tuple(sorted(rows.items())))
    if key in _SEATING_CACHE:
        return _SEATING_CACHE[key]
    cfg = BOWL["seating"]
    tiers_out, total = [], 0
    for tier in BOWL["tiers"]:
        n = rows.get(tier["name"], 20)
        secs = bowl_sections(shape, tier, cfg)
        rows_out, accessible = [], []
        for r in range(n):
            rw = bowl_row(tier, r, n)
            ring = BowlRing(shape, rw["front"] + (rw["back"] - rw["front"]) * cfg["feetDepth"])
            gaps = bowl_gaps(shape, tier, r, n, secs, ring, cfg, BOWL["tunnels"])
            count = int(ring.length / cfg["pitch"])
            pitch = ring.length / count
            runs, run_start, run_len = [], None, 0
            for i in range(count):
                s = (i + 0.5) * pitch
                # A seat keeps half a pitch clear of an aisle; beside a hole in the
                # tread (vomitory, tunnel) its whole footprint - half a seat plus
                # `holeClear`, which also covers the cut widening toward the row
                # front in a corner - must stand on concrete.
                clear = not _covered(s, [(a - m, b + m, k) for a, b, k in gaps
                                         for m in [pitch * 0.45 if k in ("aisle", "accessible")
                                                   else pitch * 0.5 + cfg["holeClear"]]], ring.length)
                if clear:
                    if run_start is None:
                        run_start, run_len = s, 0
                    run_len += 1
                elif run_start is not None:
                    runs.append([round(run_start, 3), run_len])
                    run_start = None
            if run_start is not None:
                runs.append([round(run_start, 3), run_len])
            for a, b, kind in gaps:
                if kind == "accessible":
                    accessible.append({"row": r + 1, "arc": round(((a + b) / 2) % ring.length, 3),
                                       "length": round(b - a, 2)})
            seated = sum(k for _, k in runs)
            total += seated
            rows_out.append({"row": r + 1, "floor": round(rw["tread"], 3), "feet": round(ring.m, 3),
                             "length": round(ring.length, 3), "pitch": round(pitch, 5),
                             "seats": seated, "runs": runs})
        tiers_out.append({"tier": tier["name"], "sections": secs, "rows": rows_out,
                          "accessible": accessible})
    out = {**json.loads(json.dumps(cfg)), "total": total, "tiers": tiers_out}
    _SEATING_CACHE[key] = out
    return out


def bowl_mounts(shape: dict, rim_tokens: dict) -> dict:
    """Where the bowl offers a place to hang things. `rim`: one headframe per
    rim light bank at angle k*pi/(count/2) + phase, on the parapet, facing
    midfield. Lighting hangs its lamps on these."""
    rim = BOWL["rimLights"]
    count = rim["count"]
    upper = next(t for t in BOWL["tiers"] if t["name"] == "upper")
    m = upper["outer"] + rim["beyondOuter"]
    y = upper["rise"][1] + rim_tokens["heightAbove"]["stadium"]
    lamp = rim_tokens["lampYards"]["stadium"]
    out = []
    for k in range(count):
        t = k * math.pi / (count / 2) + rim_tokens["phase"]
        x, z = bowl_point(shape, m, t)
        nx, nz = bowl_inward(shape, m, t)
        out.append({"id": f"rim-{k:02d}", "angle": round(t, 5),
                    "position": [round(x, 3), round(y, 3), round(z, 3)],
                    "facing": [round(nx, 4), 0.0, round(nz, 4)],
                    "pitch": round(-math.degrees(math.atan2(y, math.hypot(x, z))), 2),
                    "headframe": [round(lamp[0] + 1.0, 2), round(lamp[1] + 1.0, 2)],
                    "base": BOWL["parapet"]["top"],
                    "farSide": z <= rim_tokens["farSideMaxZ"]})
    return {"rim": out}


def _tier_height(name: str, offset: float) -> float:
    tier = next(t for t in BOWL["tiers"] if t["name"] == name)
    f = max(0.0, min(1.0, (offset - tier["inner"]) / (tier["outer"] - tier["inner"])))
    return round(tier["rise"][0] + (tier["rise"][1] - tier["rise"][0]) * f, 3)


def _seat(sid: str, label: str, x: float, z: float, tier: str | None, offset: float,
          look_at=(50.0, 0.0, 0.0), floor: float | None = None, group: str = "sideline",
          lookdev: bool = False) -> dict:
    """A place to sit: the floor under the wearer, in field yards, and the
    point the seat faces. Heights come from the bowl, so a seat is always on a
    row rather than floating in front of one; `floor` is for the one seat that
    is not on a tier, the press box.

    `view` is what a seat picker shows before you move: how far the nearest
    edge of the playing surface (end zones included) is, how high the floor is,
    and which part of the ground it is in. Worked out here so every client says
    the same thing about the same seat."""
    y = floor if floor is not None else (_tier_height(tier, offset) if tier else 0.0)
    dx = max(-10.0 - x, 0.0, x - 110.0)
    dz = max(abs(z) - 80 / 3, 0.0)
    out = {"id": sid, "label": label, "x": x, "y": y, "z": round(z, 3),
           "lookAt": {"x": look_at[0], "y": look_at[1], "z": look_at[2]},
           "view": {"group": group, "distanceYards": round((dx * dx + dz * dz) ** 0.5, 1),
                    "heightYards": round(y, 1)}}
    # A place the look-dev harness needs and a wearer would not choose: it
    # faces away from the play. The picker never offers one; `-stadiumSeat`
    # and the shot table still reach it.
    if lookdev:
        out["lookdev"] = True
    return out


# ── experience ──

HALF_WIDTH = 80 / 3
SEATS = [
    # The first four ids are the look-dev shots' seats; keep them.
    _seat("club", "50-yard line, lower bowl", 50.0, HALF_WIDTH + 24.0, "lower", 24.0),
    _seat("field", "Field level, home sideline", 50.0, HALF_WIDTH + 4.5, None, 0.0, group="field"),
    _seat("endzone", "Behind the home end zone", -24.0, 0.0, "lower", 14.0, group="endzone"),
    _seat("upper", "Upper deck, midfield", 50.0, HALF_WIDTH + 50.0, "upper", 50.0, group="upper"),
    _seat("sideline", "Lower bowl, home 30", 30.0, HALF_WIDTH + 12.0, "lower", 12.0),
    # The last rows of the lower bowl, under the upper deck's overhang: the
    # club seats of a real ground.
    _seat("clubLevel", "Club level, midfield", 50.0, HALF_WIDTH + 34.0, "lower", 34.0, group="club"),
    # On the far side, level with the press box glass, looking across.
    _seat("pressBox", "Press box, far side", 50.0, -(HALF_WIDTH + BOWL["pressBox"]["offset"] + 1.0), None, 0.0,
          floor=BOWL["pressBox"]["rise"][0], group="press"),
    # The camera well behind the away end line, a yard and a half back and off
    # the centre so the near upright does not stand in the middle of the view.
    # Nothing else in the stadium is near a play: every other preset is 25 yd
    # or more from the ball, so the ball's life-size band (Broadcast holds it
    # life size within 14 yd, easing to 2.6x by 45) had never been in a frame.
    # From here the goal line is 12.2 yd away. It is this end and not the
    # home one because this is the end the fixtures score in: the Bears'
    # pick-six, the look-dev touchdown, ends at yard line 100.
    # Look-dev only, like the wall: a yard and a half behind an end line the
    # painted field fills the view, and the dock cannot place a panel that
    # keeps off the paint, the ribbon and the board at once. Promoting it to a
    # seat a wearer may choose needs an answer for that first.
    _seat("goalLine", "Camera well, away goal line", 111.5, 4.0, None, 0.0,
          look_at=(100.0, 0.5, 0.0), group="endzone", lookdev=True),
    # Square on to the LED boards on the stands' wall, where no bench stands
    # between (they run from the 30 to the 30). 2.8 yd of apron, then the wall:
    # near enough for the pixel grid the art bible asks for. Every other
    # preset looks along the wall, so the boards have only ever been shot at a
    # grazing angle. The one seat that faces away from the field, and so the
    # one the picker does not offer.
    _seat("wall", "Wall boards, home side", 20.0, HALF_WIDTH + 2.8, None, 0.0,
          look_at=(20.0, 0.5, HALF_WIDTH + 13.0), group="field", lookdev=True),
]

PRESENTATION = {
    # The table model is sized for the whole two-deck bowl on its plinth, not
    # the lower bowl alone, which read as a shallow dish: the plinth reaches
    # (70 + 3) * 1.03 + a 2.4 yard bevel = 77.6 yards past the field, so the
    # model is 275 yards long and 209 deep. At 4 mm a yard that is
    # 1.10 x 0.83 m on a 1.12 x 0.45 x 0.86 m volume, and the field is 0.48 m.
    # Shrinking to fit 0.9 m instead (3.3 mm) left a 0.40 m field; keeping
    # 4.5 mm needed a 1.25 m volume, wider than the table it sits on.
    # Both decks: Bowl's table model carries the upper deck (2daced9), and
    # tests/test_experience.py holds both to the volume.
    "tabletop": {"metersPerYard": 0.004, "volume": [1.12, 0.45, 0.86],
                 "floor": -0.2, "bowlTiers": ["lower", "upper"]},
    # `seat` is the default of `seats`, kept so a 1.0 renderer still sits down.
    "stadium": {"metersPerYard": 0.9144,
                "seat": {k: SEATS[0][k] for k in ("x", "y", "z")},
                "seats": SEATS, "defaultSeat": SEATS[0]["id"],
                "bowlTiers": ["lower", "upper"]},
    # Above the rim and its light banks from every seat, clear of the glass
    # scorebug that sits a little over eye level straight ahead.
    "horizon": {"z": -62.0, "y0": 62.0, "y1": 86.0},
    "beaconHeight": 22.0,
}


# What the paint reaches past the playing surface, in yards: the NFL's solid
# white border is 6 ft wide, college marks a 4 in sideline instead. Field's
# own rule book (tools/blender/field/rules.py PAINT[...]["boundary"]) is the
# source; tests/test_experience.py holds these to it. A panel that overlaps
# the paint reads as lying on it, whatever its depth says, so the dock treats
# the painted field - surface, end zones and border - as one keep-off region.
PAINTED_BORDER = {"nfl": 6 / 3, "college-football": 4 / 36}


def painted_border(field: dict) -> float:
    return PAINTED_BORDER.get(field.get("league", "nfl"), PAINTED_BORDER["nfl"])


def field_silhouette(seat: dict, field: dict, eye_meters: float, meters_per_yard: float,
                     samples: int = 96, grow: float = 0.0) -> list[tuple[float, float]]:
    """The playing surface's outline, end zones included, as the seated
    wearer sees it: (yaw degrees, + right; degrees below the eye, + down),
    with the wearer facing the seat's lookAt. Densely sampled, so a caller can
    treat it as a polygon in angle space. `grow` widens it by that many yards
    on every side, which is how the dock takes in the painted border."""
    ex, ez = seat["x"], seat["z"]
    ey = seat["y"] + eye_meters / meters_per_yard
    fx, fz = seat["lookAt"]["x"] - ex, seat["lookAt"]["z"] - ez
    n = math.hypot(fx, fz) or 1.0
    fx, fz = fx / n, fz / n
    # Right-handed with y up: facing (fx, fz), the wearer's right is (-fz, fx).
    rx, rz = -fz, fx
    x0, x1 = -field["endZone"] - grow, field["length"] + field["endZone"] + grow
    hw = field["width"] / 2 + grow
    corners = [(x0, -hw), (x1, -hw), (x1, hw), (x0, hw)]
    out = []
    for i in range(4):
        (ax, az), (bx, bz) = corners[i], corners[(i + 1) % 4]
        for k in range(samples):
            t = k / samples
            px, pz = ax + (bx - ax) * t, az + (bz - az) * t
            dx, dz = px - ex, pz - ez
            ahead, right = dx * fx + dz * fz, dx * rx + dz * rz
            out.append((math.degrees(math.atan2(right, ahead)),
                        math.degrees(math.atan2(ey, math.hypot(dx, dz)))))
    return out


def _projector(seat: dict, eye_meters: float, meters_per_yard: float):
    """A function taking a point in field yards to (yaw degrees, + right;
    degrees below the eye, + down) for the seated wearer facing lookAt."""
    ex, ez = seat["x"], seat["z"]
    ey = seat["y"] + eye_meters / meters_per_yard
    fx, fz = seat["lookAt"]["x"] - ex, seat["lookAt"]["z"] - ez
    n = math.hypot(fx, fz) or 1.0
    fx, fz = fx / n, fz / n
    rx, rz = -fz, fx

    def project(px: float, py: float, pz: float) -> tuple[float, float]:
        dx, dz = px - ex, pz - ez
        ahead, right = dx * fx + dz * fz, dx * rx + dz * rz
        return (math.degrees(math.atan2(right, ahead)), math.degrees(math.atan2(ey - py, math.hypot(dx, dz))))
    return project


def video_board_points(seat: dict, board: dict | None, eye_meters: float, meters_per_yard: float,
                       across: int = 13, up: int = 6) -> list[tuple[float, float]]:
    """The video board's face as the seated wearer sees it: a grid of
    (yaw, below) points dense enough that a panel covering any of it holds
    one. Empty when the face is turned away - its back is only a truss."""
    if not board:
        return []
    cx, cy, cz = board["centre"]
    nx, nz = board["facing"][0], board["facing"][2]
    if nx * (seat["x"] - cx) + nz * (seat["z"] - cz) <= 0:
        return []
    h = math.hypot(nx, nz) or 1.0
    rx, rz = -nz / h, nx / h
    w, ht = board["size"]
    project = _projector(seat, eye_meters, meters_per_yard)
    return [project(cx + rx * w * (i / (across - 1) - 0.5), cy + ht * (j / (up - 1) - 0.5),
                    cz + rz * w * (i / (across - 1) - 0.5))
            for i in range(across) for j in range(up)]


def ribbon_points(seat: dict, field: dict, ribbon: dict | None, eye_meters: float, meters_per_yard: float,
                  samples: int = 900) -> list[tuple[float, float]]:
    """The ribbon board all the way round the upper deck's fascia, as
    (yaw, below) points at its bottom, middle and top, only where it is in
    front of the wearer."""
    if not ribbon:
        return []
    shape = {**BOWL["shape"], "halfLength": field["length"] / 2 + field["endZone"], "halfWidth": field["width"] / 2}
    project = _projector(seat, eye_meters, meters_per_yard)
    r0, r1 = ribbon["rise"]
    out = []
    for k in range(samples):
        x, z = bowl_point(shape, ribbon["offset"], 2 * math.pi * k / samples)
        for y in (r0, (r0 + r1) / 2, r1):
            yaw, below = project(x + 50, y, z)
            if abs(yaw) < 90:
                out.append((yaw, below))
    return out


def _inside(pt: tuple[float, float], poly: list[tuple[float, float]]) -> bool:
    x, y = pt
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def panel_box(slot: dict, size: dict, points_per_meter: float, margin: float = 0.0) -> tuple[float, float, float, float]:
    """A panel's angular box (yaw0, yaw1, below0, below1) from its slot and
    its footprint in points (panelSizes). The panel faces the wearer, so its
    half-extents are the angles its half-width and half-height subtend; a slot
    brought nearer than its legible distance carries `scale` < 1, and draws
    that much smaller, so it subtends what it would have further out."""
    d = slot["distance"]
    k = slot.get("scale", 1.0)
    below = math.degrees(math.atan2(-slot["height"], d))
    hw = math.degrees(math.atan2(size["widthPoints"] * k / points_per_meter / 2, d)) + margin
    hh = math.degrees(math.atan2(size["maxHeightPoints"] * k / points_per_meter / 2, d)) + margin
    return slot["yaw"] - hw, slot["yaw"] + hw, below - hh, below + hh


def rim_points(seat: dict, mounts: dict | None, eye_meters: float, meters_per_yard: float) -> list[tuple[float, float]]:
    """Every rim light bank's headframe as the seated wearer sees it: a grid
    of (yaw, below) points over each frame's face. Mount positions are in the
    renderer's local yards, midfield at x 0."""
    if not mounts:
        return []
    project = _projector(seat, eye_meters, meters_per_yard)
    out = []
    for m in mounts.get("rim", []):
        x, y, z = m["position"]
        rx, rz = -m["facing"][2], m["facing"][0]
        w, h = m["headframe"]
        for i in range(9):
            for j in range(5):
                u, v = w * (i / 8 - 0.5), h * (j / 4 - 0.5)
                yaw, below = project(x + 50 + rx * u, y + v, z + rz * u)
                if abs(yaw) < 90:
                    out.append((yaw, below))
    return out


# What stands within arm's length of a seat, from Bowl's kit (tools/blender/bowl/
# seat.py and structure.py; tests/test_experience.py holds these to it): a
# chair's back rises 0.84 m over its tread and 0.3 m behind its feet, an aisle
# rail is 1.04 yd over the riser it starts from, and the press box's glass
# leans out 0.7 yd from a sill 0.6 yd over its floor, over a desk as high.
NEAR = {"chairBackYards": 0.84 / 0.9144, "chairBehindYards": 0.33, "chairHalfWidthYards": 0.25,
        "railYards": 1.04, "railDepth": 0.06, "reachYards": 5.0,
        "pressSillYards": 0.6, "pressCantYards": 0.7, "pressDeskFrontYards": 0.05, "pressDeskDepthYards": 0.38}


def _ring_angle_of(shape: dict, m: float, x: float, z: float) -> float:
    """The angle on the ring at offset m nearest the point (x, z), local yards."""
    best = min(range(1440), key=lambda k: (lambda p: (p[0] - x) ** 2 + (p[1] - z) ** 2)(
        bowl_point(shape, m, 2 * math.pi * k / 1440)))
    lo, hi = 2 * math.pi * (best - 1) / 1440, 2 * math.pi * (best + 1) / 1440
    for _ in range(30):
        a, b = lo + (hi - lo) / 3, hi - (hi - lo) / 3
        da = sum((p - q) ** 2 for p, q in zip(bowl_point(shape, m, a), (x, z)))
        db = sum((p - q) ** 2 for p, q in zip(bowl_point(shape, m, b), (x, z)))
        lo, hi = (lo, b) if da < db else (a, hi)
    return (lo + hi) / 2


def near_occluders(seat: dict, shape: dict, seating: dict, eye_meters: float,
                   meters_per_yard: float) -> list[tuple[float, float, float]]:
    """The solid things within `NEAR.reachYards` in front of a seat, as
    (yaw, below, flat metres from the eye): chair backs and aisle rails in the
    rows ahead, the ground at field level, and the press box's glass and desk.
    A panel further out than one of these, and behind it, is drawn through
    it - it reads as lying on a chair or standing outside the window - so the
    dock keeps every panel nearer than whatever it overlaps."""
    project = _projector(seat, eye_meters, meters_per_yard)
    ex, ez = seat["x"], seat["z"]
    ey = seat["y"] + eye_meters / meters_per_yard
    fx, fz = seat["lookAt"]["x"] - ex, seat["lookAt"]["z"] - ez
    n = math.hypot(fx, fz) or 1.0
    fx, fz = fx / n, fz / n
    reach = NEAR["reachYards"]
    out: list[tuple[float, float, float]] = []

    def add(px: float, py: float, pz: float) -> None:
        dx, dz = px - ex, pz - ez
        flat = math.hypot(dx, dz)
        if flat < 1e-3 or flat > reach or dx * fx + dz * fz <= 0:
            return
        yaw, below = project(px, py, pz)
        out.append((yaw, below, flat * meters_per_yard))

    lx = ex - 50.0
    box = BOWL["pressBox"]
    if abs(seat["y"] - box["rise"][0]) < 1e-6 and ez < 0:
        # In the press box: the glass from its sill up, leaning out, and the
        # desk under it, across the run either side of the wearer.
        y0, y1 = box["rise"]
        frames = {}
        for d in (0.0, -NEAR["pressCantYards"], NEAR["pressDeskFrontYards"],
                  NEAR["pressDeskFrontYards"] + NEAR["pressDeskDepthYards"]):
            m = box["offset"] + d
            t = _ring_angle_of(shape, m, lx, ez)
            frames[d] = (bowl_point(shape, m, t), bowl_inward(shape, m, t))
        (gx0, gz0), (nx0, nz0) = frames[0.0]
        (gx1, gz1), _ = frames[-NEAR["pressCantYards"]]
        sill = y0 + NEAR["pressSillYards"]
        for k in range(-80, 81):
            lat = k * 0.05
            for j in range(41):
                f = j / 40
                add(gx0 + (gx1 - gx0) * f + 50 - nz0 * lat, sill + (y1 - sill) * f, gz0 + (gz1 - gz0) * f + nx0 * lat)
            for d in (NEAR["pressDeskFrontYards"], NEAR["pressDeskFrontYards"] + NEAR["pressDeskDepthYards"]):
                (x, z), (nx, nz) = frames[d]
                add(x + 50 - nz * lat, sill, z + nx * lat)
        return out
    if seat["y"] < 0.5:
        # At field level the ground is the only thing near.
        for i in range(-45, 46):
            a = math.radians(i)
            for j in range(1, 41):
                d = j * reach / 40
                add(ex + (fx * math.cos(a) - fz * math.sin(a)) * d, 0.0, ez + (fz * math.cos(a) + fx * math.sin(a)) * d)
        return out
    tiers = {t["name"]: t for t in BOWL["tiers"]}
    rows_of = {t["tier"]: t for t in seating["tiers"]}
    t0 = _ring_angle_of(shape, 0.0, lx, ez)
    px, pz = bowl_point(shape, 0.0, t0)
    m_eye = math.hypot(lx - px, ez - pz)
    for name, tier in tiers.items():
        plan = rows_of.get(name)
        if not plan or not (tier["rise"][0] - 0.01 <= seat["y"] <= tier["rise"][1] + 0.01):
            continue
        rails: dict[str, list] = {}
        for rw in plan["rows"]:
            geo = bowl_row(tier, rw["row"] - 1, len(plan["rows"]))
            if geo["front"] > m_eye + 1.0 or geo["back"] < m_eye - reach:
                continue
            ring = BowlRing(shape, rw["feet"])
            s_eye = ring.arc_at(_ring_angle_of(shape, rw["feet"], lx, ez))
            back_h = NEAR["chairBackYards"]
            for first, count in rw["runs"]:
                k0 = max(0, math.floor((s_eye - reach - first) / rw["pitch"]))
                k1 = min(count - 1, math.ceil((s_eye + reach - first) / rw["pitch"]))
                for k in range(k0, k1 + 1):
                    t = ring.angle(first + k * rw["pitch"])
                    x, z = bowl_point(shape, rw["feet"], t)
                    if math.hypot(x - lx, z - ez) < rw["pitch"] * 0.6:
                        continue                      # the wearer's own seat
                    nx, nz = bowl_inward(shape, rw["feet"], t)
                    bx, bz = x - nx * NEAR["chairBehindYards"], z - nz * NEAR["chairBehindYards"]
                    w = NEAR["chairHalfWidthYards"]
                    for li in range(11):
                        lat = -w + 2 * w * li / 10
                        for hi in range(6):
                            add(bx + 50 - nz * lat, rw["floor"] + back_h * (0.5 + 0.5 * hi / 5), bz + nx * lat)
            # Aisle rails start at each section's edge, at the riser.
            for sec in plan["sections"]:
                sa = sec["from"] * ring.length
                if abs(((sa - s_eye) + ring.length / 2) % ring.length - ring.length / 2) > reach:
                    continue
                t = ring.angle(sa)
                x, z = bowl_point(shape, geo["front"] + (geo["back"] - geo["front"]) * NEAR["railDepth"], t)
                rails.setdefault(sec["id"], []).append((x + 50, geo["riserFrom"] + NEAR["railYards"], z))
        for pts in rails.values():
            for (x0, y0, z0), (x1, y1, z1) in zip(pts, pts[1:]):
                for q in range(21):
                    f = q / 20
                    add(x0 + (x1 - x0) * f, y0 + (y1 - y0) * f, z0 + (z1 - z0) * f)
    return out


def box_overlaps(box: tuple[float, float, float, float], poly: list[tuple[float, float]]) -> bool:
    y0, y1, b0, b1 = box
    if any(y0 <= p[0] <= y1 and b0 <= p[1] <= b1 for p in poly):
        return True
    grid = [(y0 + (y1 - y0) * i / 6, b0 + (b1 - b0) * j / 4) for i in range(7) for j in range(5)]
    return any(_inside(g, poly) for g in grid)


def points_in_box(box: tuple[float, float, float, float], points: list[tuple[float, float]]) -> bool:
    y0, y1, b0, b1 = box
    return any(y0 <= p[0] <= y1 and b0 <= p[1] <= b1 for p in points)


class ViewGrid:
    """One seat's view as cells of `RES` degrees, (yaw, below): which hold the
    field, which hold something a panel must never cover (the video board,
    the ribbon, the rim light banks), and how near the nearest solid thing in
    each is. Summed-area tables make a box's question constant-time."""

    RES = 0.5
    # The whole circle: a recentred dock looks along a different facing, and in
    # angle space that is only a shift along yaw, so one grid per seat answers
    # every facing.
    YAW = (-180.0, 180.0)
    BELOW = (-30.0, 45.0)

    def __init__(self, field_poly, hard_points, near_points):
        r = self.RES
        self.nx = int((self.YAW[1] - self.YAW[0]) / r)
        self.ny = int((self.BELOW[1] - self.BELOW[0]) / r)
        field = [[0] * self.nx for _ in range(self.ny)]
        # Scanline fill at each row's centre, plus every outline point's cell,
        # so a sliver thinner than a cell still counts.
        n = len(field_poly)
        for j in range(self.ny):
            yc = self.BELOW[0] + (j + 0.5) * r
            xs = []
            for i in range(n):
                (x1, y1), (x2, y2) = field_poly[i], field_poly[(i + 1) % n]
                if (y1 > yc) != (y2 > yc):
                    xs.append(x1 + (yc - y1) * (x2 - x1) / (y2 - y1))
            xs.sort()
            for a, b in zip(xs[0::2], xs[1::2]):
                i0, i1 = max(0, int((a - self.YAW[0]) / r)), min(self.nx - 1, int((b - self.YAW[0]) / r))
                for i in range(i0, i1 + 1):
                    field[j][i] = 1
        for p in field_poly:
            self._mark(field, p)
        hard = [[0] * self.nx for _ in range(self.ny)]
        for p in hard_points:
            self._mark(hard, p)
        self.near = [[math.inf] * self.nx for _ in range(self.ny)]
        for yaw, below, d in near_points:
            c = self._cell(yaw, below)
            if c and d < self.near[c[1]][c[0]]:
                self.near[c[1]][c[0]] = d
        # A sampled chair or pane leaves gaps between its points; spread each
        # distance two cells each way so a box between two samples still sees it.
        spread = {}
        for j in range(self.ny):
            for i, d in enumerate(self.near[j]):
                if d < math.inf:
                    for jj in range(max(0, j - 2), min(self.ny, j + 3)):
                        for ii in range(max(0, i - 2), min(self.nx, i + 3)):
                            if d < spread.get((ii, jj), math.inf):
                                spread[(ii, jj)] = d
        for (i, j), d in spread.items():
            self.near[j][i] = d
        self.field_sum, self.hard_sum = self._sums(field), self._sums(hard)

    def _cell(self, yaw, below):
        i, j = int((yaw - self.YAW[0]) / self.RES), int((below - self.BELOW[0]) / self.RES)
        return (i, j) if 0 <= i < self.nx and 0 <= j < self.ny else None

    def _mark(self, grid, p):
        c = self._cell(*p)
        if c:
            grid[c[1]][c[0]] = 1

    def _sums(self, grid):
        s = [[0] * (self.nx + 1) for _ in range(self.ny + 1)]
        for j in range(self.ny):
            run = 0
            for i in range(self.nx):
                run += grid[j][i]
                s[j + 1][i + 1] = s[j][i + 1] + run
        return s

    def _range(self, box, margin):
        y0, y1, b0, b1 = box
        i0 = max(0, int(math.floor((y0 - margin - self.YAW[0]) / self.RES)))
        i1 = min(self.nx, int(math.ceil((y1 + margin - self.YAW[0]) / self.RES)))
        j0 = max(0, int(math.floor((b0 - margin - self.BELOW[0]) / self.RES)))
        j1 = min(self.ny, int(math.ceil((b1 + margin - self.BELOW[0]) / self.RES)))
        return i0, i1, j0, j1

    @staticmethod
    def _count(s, i0, i1, j0, j1):
        if i1 <= i0 or j1 <= j0:
            return 0
        return s[j1][i1] - s[j0][i1] - s[j1][i0] + s[j0][i0]

    def covers_field(self, box, margin):
        return self._count(self.field_sum, *self._range(box, margin)) > 0

    def covers_hard(self, box, margin):
        return self._count(self.hard_sum, *self._range(box, margin)) > 0

    def nearest(self, box):
        i0, i1, j0, j1 = self._range(box, 0.0)
        return min((self.near[j][i] for j in range(j0, j1) for i in range(i0, i1)), default=math.inf)


def seat_view(seat: dict, field: dict, layout: dict, eye_meters: float, meters_per_yard: float,
              mounts: dict | None = None, seating: dict | None = None, shape: dict | None = None) -> "ViewGrid":
    """Everything the dock must keep off, as this seat sees it: the painted
    field, the video board, the ribbon, the rim light banks and whatever
    stands within arm's length. Built once per seat and used for every facing
    the dock can be recentred to."""
    dock = layout["dock"]
    hard = (video_board_points(seat, BOWL.get("videoBoard"), eye_meters, meters_per_yard)
            + ribbon_points(seat, field, BOWL.get("ribbon"), eye_meters, meters_per_yard)
            + rim_points(seat, mounts, eye_meters, meters_per_yard))
    near = near_occluders(seat, shape, seating, eye_meters, meters_per_yard) if shape and seating else []
    # The keep-off region is the painted field, not the playing surface: a tab
    # low over the white border read as lying on it from the field seat, twice
    # over two checkpoints, however near it really was. `paintClearYards` of
    # ground beyond the paint keeps a panel from hugging the white as well:
    # a degree of margin is only a hand's width of grass at the field seat.
    return ViewGrid(field_silhouette(seat, field, eye_meters, meters_per_yard,
                                     grow=painted_border(field) + dock["paintClearYards"]), hard, near)


def seat_panels(seat: dict, field: dict, layout: dict, eye_meters: float, meters_per_yard: float,
                mounts: dict | None = None, seating: dict | None = None, shape: dict | None = None,
                facing: float = 0.0, view: "ViewGrid | None" = None, seed: dict | None = None) -> dict:
    """Where every panel goes from this seat: the dock.

    Panels are one anchored layer, laid out by the same rule from every seat
    rather than each hunting its own gap:

    - **The rail** holds what is always there: the Drive tab on the left, the
      Controls pill in the middle, the right-hand tab on the right, on one
      line at one distance. The side tabs stand under the side panels' own
      yaw, so a panel opens where its tab was. The line sits in the lowest
      clear band inside the comfort window - under the field's near sideline
      where there is room - at the height nearest `rail.preferredBelowDegrees`
      in that band.
    - **The gallery** holds what the wearer opens. The two side panels open as
      a mirrored pair, one height and one distance; the controls open centred,
      as near the pill's height as fits. A panel that needs more room than a
      band gives moves further out, where it subtends less, up to
      `gallery.maxDistance`.

    Hard rules, never traded against a cost: off the painted field - surface,
    end zones and border - and off the video board, the ribbon and the rim
    light banks; the whole box, edges and all, inside ±maxSideDegrees and
    above maxBelowDegrees; off every other element of the
    dock it could be shown with; and nearer than any chair, rail, ground or
    glass it overlaps. A place past such a thing is brought in front of it
    and drawn smaller by `scale`, so it subtends the same angle. A panel with
    no clear place carries `clear: false` and starts folded.

    Every client lays panels out from this, not from its own guess."""
    dock = layout["dock"]
    ppm = layout["pointsPerMeter"]
    sizes = layout["panelSizes"]
    max_side, max_below, top = layout["maxSideDegrees"], layout["maxBelowDegrees"], dock["highestBelowDegrees"]
    grid = view or seat_view(seat, field, layout, eye_meters, meters_per_yard, mounts, seating, shape)

    def seen(box):
        """The box as the stadium sees it: the dock's angles are measured from
        where the wearer is facing, the grid's from the seat's own forward."""
        return (box[0] + facing, box[1] + facing, box[2], box[3])

    def at(yaw, below, distance, scale=1.0):
        return {"yaw": round(yaw, 3), "distance": round(distance, 3),
                "height": round(-distance * math.tan(math.radians(below)), 3), "scale": round(scale, 3)}

    def fit(yaw, below, distance, size, avoid=(), scale=1.0):
        slot = at(yaw, below, distance, scale)
        box = panel_box(slot, size, ppm)
        # Where a panel sits is the comfort rule (its centre, within
        # ±maxSideDegrees); how much of it can be seen is a second rule: the
        # whole box, edges and all, stays inside viewWindowDegrees, so no
        # element is ever half out of view (integration-13's redzone-trails
        # showed the drive log cut in two by the frame). Heights are rounded
        # to the millimetre, so stay a hair inside.
        window = dock["viewWindowDegrees"]
        if abs(yaw) > max_side or box[0] < -window or box[1] > window:
            return None
        # However it is moved or scaled, a panel subtends at least what it
        # would full size at the gallery's furthest: shrinking *and* standing
        # back reads smaller than either alone.
        if scale / distance < 1.0 / dock["gallery"]["maxDistance"] - 1e-9:
            return None
        if box[3] > max_below - 0.05 or box[2] < top:
            return None
        world = seen(box)
        if grid.covers_field(world, dock["fieldMarginDegrees"]) or grid.covers_hard(world, dock["hardMarginDegrees"]):
            return None
        if any(_boxes_overlap(box, other, dock["gapDegrees"]) for other in avoid):
            return None
        nearest = grid.nearest(world)
        if nearest - dock["nearClearanceMeters"] < distance:
            placed = nearest - dock["nearClearanceMeters"]
            if placed < dock["minDistance"]:
                return None
            slot = at(yaw, below, placed, scale * placed / distance)
        return slot

    def first(cands, test):
        for _, args in sorted(cands, key=lambda c: c[0]):
            s = test(*args)
            if s:
                return s
        return None

    def below_of(slot):
        return math.degrees(math.atan2(-slot["height"], slot["distance"]))

    def again(slot, size, avoid=()):
        """The same place as last time, if it is still clear. A recentred dock
        starts from the facing beside it, so most panels keep their place and
        the dock does not rearrange itself as the wearer turns."""
        if not slot:
            return None
        height = (slot.get("maxHeightPoints") or size["maxHeightPoints"]) / size["maxHeightPoints"]
        kept = fit(slot["yaw"], below_of(slot), slot["distance"],
                   size if height >= 1.0 else {**size, "maxHeightPoints": size["maxHeightPoints"] * height},
                   avoid, slot.get("scale", 1.0))
        if kept and height < 1.0:
            kept = {**kept, "maxHeightPoints": slot["maxHeightPoints"]}
        return kept

    step = dock["stepDegrees"]
    belows_up = list(_frange(max_below, top, -step))
    belows_all = list(belows_up)
    tab = sizes["tab"]
    rail, gallery, ctl = dock["rail"], dock["gallery"], dock["controls"]
    side_yaw = rail["sideYawDegrees"]
    rail_yaws = {"drive": -side_yaw, "controls": 0.0, "trailing": side_yaw}

    # The rail: the lowest band where all three stand on one line.
    band = []
    if seed:
        kept = {k: again(seed[k]["tab"], tab) for k in rail_yaws}
        if all(kept.values()) and len({round(below_of(v), 3) for v in kept.values()}) == 1:
            band = [(below_of(kept["controls"]), kept)]
            belows_up = []
    for below in belows_up:
        slots = {k: fit(y, below, rail["distance"], tab) for k, y in rail_yaws.items()}
        if all(slots.values()):
            band.append((below, slots))
        elif band:
            break
    if band:
        rail_below, tabs = min(band, key=lambda b: abs(b[0] - rail["preferredBelowDegrees"]))
    else:
        rail_below, tabs = rail["preferredBelowDegrees"], {}
        for k, y in rail_yaws.items():
            cands = [(abs(yy - y) * 2 + abs(b - rail["preferredBelowDegrees"]), (yy, b, rail["distance"], tab))
                     for yy in _frange(-max_side, max_side, step) for b in belows_all]
            tabs[k] = first(cands, fit) or at(y, rail_below, rail["distance"])
    tab_box = {k: panel_box(s, tab, ppm) for k, s in tabs.items()}

    comfy = gallery["comfortableBelowDegrees"]

    def discomfort(below):
        return (comfy[0] - below) * 1.5 if below < comfy[0] else max(0.0, below - comfy[1])

    distances = list(_frange(gallery["minDistance"], gallery["maxDistance"], gallery["distanceStep"]))
    yaw_mags = list(_frange(max_side, gallery["minSideDegrees"], -step))
    # Full size first; a seat whose band is too thin for one (the home 30's,
    # where the ribbon dips on the right) may draw its panel smaller rather
    # than go without.
    scales = list(_frange(1.0, gallery["minScale"], -gallery["scaleStep"]))
    heights = list(_frange(1.0, gallery["minHeightFraction"], -gallery["heightStep"]))

    def shorter(size, fraction):
        return size if fraction >= 1.0 else {**size, "maxHeightPoints": size["maxHeightPoints"] * fraction}

    def side_cost(mag, below, distance, scale=1.0, height=1.0):
        return (gallery["distanceCost"] * (distance / gallery["minDistance"] - 1) + discomfort(below)
                + gallery["inwardCost"] * (max_side - mag)
                + gallery["heightCost"] * (1.0 - height) / max(1e-6, gallery["heightStep"])
                + gallery["scaleCost"] * (1.0 - scale) / max(1e-6, gallery["scaleStep"]))

    # A side panel, open, hides its own tab but not the pill or the other tab.
    avoid_for = {"drive": [tab_box["controls"], tab_box["trailing"]],
                 "trailing": [tab_box["controls"], tab_box["drive"]]}

    def place_side(name, sign, mag, below, distance, scale, height):
        slot = fit(sign * mag, below, distance, shorter(sizes[name], height), avoid_for[name], scale)
        if slot and height < 1.0:
            slot = {**slot, "maxHeightPoints": round(sizes[name]["maxHeightPoints"] * height, 1)}
        return slot

    def pair(mag, below, distance, scale, height):
        left = place_side("drive", -1, mag, below, distance, scale, height)
        right = left and place_side("trailing", 1, mag, below, distance, scale, height)
        return {"drive": left, "trailing": right} if left and right else None

    opened = None
    if seed:
        left = again(seed["drive"], sizes["drive"], avoid_for["drive"]) if seed["drive"]["clear"] else None
        right = again(seed["trailing"], sizes["trailing"], avoid_for["trailing"]) if seed["trailing"]["clear"] else None
        if left and right:
            opened = {"drive": left, "trailing": right}
    # Full size and full height first, and only if nothing fits at all does
    # the search widen to the shortened and then the smaller panel: a seat
    # that needs neither never pays for the candidates that do.
    def side_passes():
        for h in heights:
            for k in scales:
                yield [(side_cost(m, b, d, k, h), (m, b, d, k, h))
                       for m in yaw_mags for b in belows_all for d in distances]

    if opened is None:
        for cands in side_passes():
            opened = first(cands, pair)
            if opened:
                break
        if opened is None:
            opened = {}
            for name, sign in (("drive", -1), ("trailing", 1)):
                for cands in side_passes():
                    opened[name] = first(cands, lambda m, b, d, k, h, name=name, sign=sign:
                                         place_side(name, sign, m, b, d, k, h))
                    if opened[name]:
                        break

    # The controls open centred, nearest the pill, clear of whatever is open
    # or folded either side of them.
    others = [tab_box["drive"], tab_box["trailing"]] + [
        panel_box(s, shorter(sizes[k], (s.get("maxHeightPoints") or sizes[k]["maxHeightPoints"]) / sizes[k]["maxHeightPoints"]), ppm)
        for k, s in opened.items() if s]
    kept_ctl = again(seed["controls"], sizes["controls"], others) if seed and seed["controls"]["clear"] else None
    if kept_ctl is None:
        ctl_cands = [(abs(b - rail_below) * 0.5 + abs(y) + 4 * (d / ctl["minDistance"] - 1), (y, b, d))
                     for y in _frange(-ctl["maxYawDegrees"], ctl["maxYawDegrees"], step) for b in belows_all
                     for d in _frange(ctl["minDistance"], ctl["maxDistance"], gallery["distanceStep"])]
        kept_ctl = first(ctl_cands, lambda y, b, d: fit(y, b, d, sizes["controls"], others))
    opened["controls"] = kept_ctl

    out = {}
    for name in ("drive", "trailing", "controls"):
        place = opened[name]
        clear = place is not None
        # Nowhere clear: it starts folded, and opens over its tab if asked.
        out[name] = {**(place or tabs[name]), "folded": not clear, "clear": clear, "tab": tabs[name]}
    out["scorebugHidden"] = board_carries_score(seat, BOWL.get("videoBoard"), layout["scorebugYield"])
    out["rail"] = {"below": round(rail_below, 2), "clear": bool(band)}
    return out


def _boxes_overlap(a, b, gap: float = 0.0) -> bool:
    return a[0] - gap < b[1] and b[0] - gap < a[1] and a[2] - gap < b[3] and b[2] - gap < a[3]


def board_carries_score(seat: dict, board: dict | None, rule: dict) -> bool:
    """Whether the video board already shows the score legibly from this seat:
    its face turned toward the wearer, near straight ahead, and wide enough.
    Then the glass scorebug would only sit in front of it."""
    if not board:
        return False
    cx, cy, cz = board["centre"]
    ex, ez = seat["x"], seat["z"]
    to_seat = (ex - cx, ez - cz)
    if board["facing"][0] * to_seat[0] + board["facing"][2] * to_seat[1] <= 0:
        return False
    fx, fz = seat["lookAt"]["x"] - ex, seat["lookAt"]["z"] - ez
    ahead = math.atan2(fx * (cz - ez) - fz * (cx - ex), fx * (cx - ex) + fz * (cz - ez))
    if abs(math.degrees(ahead)) > rule["inViewDegrees"]:
        return False
    dist = math.hypot(cx - ex, cz - ez, cy - seat["y"])
    return math.degrees(2 * math.atan2(board["size"][0] / 2, dist)) >= rule["boardMinDegrees"]


def _frange(start: float, stop: float, step: float):
    v = start
    while (step < 0 and v >= stop - 1e-9) or (step > 0 and v <= stop + 1e-9):
        yield round(v, 3)
        v += step


def experience_visual(tokens: dict, field: dict) -> dict:
    """visual.experience with each seat's panel layout worked out for this
    field: `layout.perSeat[seat id] = {drive, trailing, controls}`."""
    exp = tokens["visual"]["experience"]
    eye = exp["camera"]["eyeMeters"]
    mpy = PRESENTATION["stadium"]["metersPerYard"]
    key = (json.dumps(field, sort_keys=True, default=str), json.dumps(exp["layout"], sort_keys=True),
           json.dumps(tokens["visual"]["lighting"]["rim"], sort_keys=True), json.dumps(tokens["visual"]["bowl"]["rows"]))
    if key not in _PANELS_CACHE:
        shape = {**BOWL["shape"], "halfLength": field["length"] / 2 + field["endZone"], "halfWidth": field["width"] / 2}
        mounts = bowl_mounts(shape, tokens["visual"]["lighting"]["rim"])
        seating = bowl_seating(shape, tokens["visual"]["bowl"]["rows"])
        rec = exp["layout"]["dock"]["recentre"]
        step, reach = rec["bucketDegrees"], rec["maxYawDegrees"]
        out = {}
        for s in PRESENTATION["stadium"]["seats"]:
            view = seat_view(s, field, exp["layout"], eye, mpy, mounts, seating, shape)
            home = seat_panels(s, field, exp["layout"], eye, mpy, mounts, seating, shape, view=view)
            # The dock again for every facing the wearer can recentre to. Each
            # bucket starts from the one beside it: the bands a panel lives in
            # are wide, so most facings keep the place they had and cost a
            # check rather than a search.
            buckets, seed = {"0": home}, home
            for sign in (1, -1):
                seed = home
                for k in range(1, int(reach / step) + 1):
                    facing = sign * k * step
                    seed = seat_panels(s, field, exp["layout"], eye, mpy, mounts, seating, shape,
                                       facing=facing, view=view, seed=seed)
                    buckets[str(int(facing)) if facing == int(facing) else str(facing)] = seed
            out[s["id"]] = {**home, "recentre": buckets}
        _PANELS_CACHE[key] = out
    per = json.loads(json.dumps(_PANELS_CACHE[key]))
    return {**exp, "layout": {**exp["layout"], "perSeat": per}}


_PANELS_CACHE: dict = {}


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


def paint_over(paint: str, ground: str, opacity: float) -> str:
    """Paint composited over the grass: what an eye is actually asked to read.

    One alpha blend, which is what the renderer does before it lays blades
    back over the top. The blades and the floods are not modelled, so this is
    an approximation - but the ink is chosen against the same approximation
    the test measures, so the two cannot disagree.
    """
    p, g = _rgb(paint), _rgb(ground)
    return _hex(tuple(opacity * p[i] + (1 - opacity) * g[i] for i in range(3)))


def letter_ink(paint: str, ground: str, opacity: float, inks: dict) -> str:
    """Which ink a club letters its end zone in.

    White is the common answer and not the universal one: New Orleans' old
    gold is light enough that white lettering measures 1.7:1 on it, which is
    unreadable at any size. So the ink is *chosen* - the better of the field's
    own white and its dark - rather than assumed, and a club whose paint is
    light gets dark letters, the way a real light-coloured end zone does.
    """
    seen = paint_over(paint, ground, opacity)
    return max((inks["white"], inks["ink"]), key=lambda i: contrast(i, seen))


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
        # `location` and `nickname` are the club's name in its two parts, which
        # the field letters its two end zones with. They are carried only when
        # the source states them; see club_lines on why they are never guessed.
        # `rank` is a college fact and is carried only when the payload states
        # one: the AP top 25 is half of what a Saturday's boards say, and an
        # NFL club has no such thing. A team outside the 25 states nothing,
        # which is not the same as being 26th.
        rank = t.get("rank")
        out = {"abbr": t.get("abbr", ""), "name": t.get("name", ""),
               "location": t.get("location", ""), "nickname": t.get("nickname", ""),
               "id": str(t.get("id", "")), "color": t.get("color", ""),
               "chip": chip(t.get("color", ""), band), "chipText": band["text"],
               "hatch": False, "score": t.get("score", 0)}
        if isinstance(rank, int) and 1 <= rank <= 25:
            out["rank"] = rank
        return out
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


def goal_kick(play: dict, from_x: float, side: str | None, field: dict, tokens: dict) -> dict | None:
    """Where a field goal or extra point goes: through the uprights or past them.

    ESPN's end yard line for a kick is where the next play starts, not where
    the ball went, so a made kick drawn from it landed beside the posts. The
    uprights stand on the end line of the end zone the kicking side attacks
    (home attacks x = 100, so x = 110). A good kick ends `overshootYards` past
    that plane on the centre line, and the kick apex formula carries it over
    the crossbar (a test asserts the clearance). A miss the text calls wide
    ends `wideYards` outside the upright on that side of the kicker; a short
    one ends `shortYards` in front of the plane. Returns None for anything
    else, including blocks, which keep their own lane.

    Facing +x with +y up, the kicker's right is +z.
    """
    kind = (play.get("type") or "").lower()
    if "field goal" not in kind and "extra point" not in kind:
        return None
    text = (play.get("text") or "").lower()
    if "blocked" in text or "blocked" in kind:
        return None
    rule = tokens["arc"]["goalKick"]
    if side is None:
        side = "home" if from_x >= field["length"] / 2 else "away"
    attack = 1.0 if side == "home" else -1.0
    plane = field["length"] + field["endZone"] if side == "home" else -field["endZone"]
    half = field["goalPostWidth"] / 2
    if "short" in text:
        return {"toX": round(plane - attack * rule["shortYards"], 3), "lane": 0.0, "result": "short"}
    to_x = round(plane + attack * rule["overshootYards"], 3)
    if "wide right" in text or "wide left" in text:
        right = 1.0 if "wide right" in text else -1.0
        return {"toX": to_x, "lane": round(right * attack * (half + rule["wideYards"]), 3),
                "result": "wideRight" if right > 0 else "wideLeft"}
    if "no good" in text or "missed" in kind:
        return {"toX": to_x, "lane": round(attack * (half + rule["wideYards"]), 3), "result": "wide"}
    return {"toX": to_x, "lane": 0.0, "result": "good"}


# ───────────────────────────── how a play moves ─────────────────────────────
#
# A broadcast replay graphic, not tracking: the feed says where a play started
# and ended, what kind it was, and in its text which way it went ("right end",
# "pass deep left", "punts 51 yards to DAL 26"). play_path turns that into
# timed segments - hold, carry, air - that every client flies the same way, so
# a run hugs the grass, a pass drops back and throws, and a punt hangs. It never
# draws a person; where the text is silent it takes the plain middle.

CROSSBAR_YARDS = 3.333   # 10 ft, both codes (_props)
_RE_YARDS = re.compile(r"(-?\d+)\s+yards?")
# The verb that announces a kick. The NFL conjugates it ("J.Moody kicks 65
# yards from DET 35"); college names it ("P.Woodring kickoff 65 yards to the
# ARK00"). Splitting on the NFL's word alone left every college kick with an
# empty clause, so nothing knew where the ball came down.
_RE_KICKED = re.compile(r"\b(?:kicks?|kick ?off|punts?)\b", re.I)


def _kick_clause(text: str) -> str:
    """What the text says after the ball was kicked, in either code."""
    m = _RE_KICKED.search(text)
    return text[m.end():] if m else ""


def _return_clause(clause: str) -> str:
    """What the text says about the runback, after the catch. College names it
    outright ("to the PUR36 X.Townsend return 0 yards to the PUR36"); the NFL
    starts a new sentence for it."""
    m = re.search(r"\breturns?\b", clause, re.I)
    if m:
        return clause[m.end():]
    return clause.split(".", 1)[-1] if "." in clause else ""


def _club_x(abbr: str, n: float, home: dict, away: dict) -> float | None:
    """A text spot ("DAL 32") as field x. Home's goal line is x = 0. The text
    may shorten an abbreviation ("LA" for LAR), so a prefix either way counts."""
    up = abbr.upper()
    for club, x in ((home.get("abbr") or "", n), (away.get("abbr") or "", 100.0 - n)):
        club = club.upper()
        if club and (club == up or club.startswith(up) or up.startswith(club)):
            return float(x)
    return None


def _spot_after(text: str, words: tuple[str, ...], home: dict, away: dict) -> float | None:
    """The first spot following any of `words` ("at", "to") in `text`.

    The two codes write a spot differently: the NFL puts a space in it ("to
    DAL 32"), college runs it together and pads it ("to the ARK00"). Both are
    a club and a yard line, so both are read here rather than in two places.
    """
    for m in re.finditer(r"\b(?:%s)\s+(?:the\s+)?(?:([A-Z]{2,4})\s?(\d{1,2})\b|(50)\b)" % "|".join(words), text):
        if m.group(3):
            return 50.0
        x = _club_x(m.group(1), float(m.group(2)), home, away)
        if x is not None:
            return x
    return None


def _direction(text: str) -> str | None:
    t = text.lower()
    for word in ("left", "right", "middle"):
        if re.search(rf"\b{word}\b", t):
            return word
    return None


def _depth(text: str) -> str:
    t = text.lower()
    return "deep" if " deep" in t else "short" if " short" in t else "other"


def air_yards(play: dict, gain: float | None = None, tokens: dict | None = None) -> float:
    """How far downfield the ball was thrown, in yards from the line.

    nflverse states it, and when it does that number is used and nothing here
    runs. ESPN does not, so a live play falls back on the estimate below: the
    depth word bounds a share of the gain. That estimate is wrong by exactly
    the yards after the catch, which is why `truth.compare` measures it.
    """
    stated = play.get("airYards")
    if stated is not None:
        try:
            return float(stated)
        except (TypeError, ValueError):
            pass
    tokens = tokens or load_tokens()
    ps = tokens["visual"]["broadcast"]["play"]["pass"]
    text = play_body(play.get("text") or "")
    depth = play.get("passLength") or _depth(text)
    if depth not in ps["air"]:
        depth = "other"
    if "incomplete" in text.lower():
        return float(ps["incompleteAir"][depth])
    if gain is None:
        a, b = play.get("from"), play.get("to")
        gain = (float(a) - float(b)) if a is not None and b is not None else 0.0
    band = ps["air"][depth]
    if gain > band["min"]:
        return float(max(band["min"], min(band["max"], gain * band["share"])))
    return float(max(-2.0, gain))


class _Path:
    """Segments laid end to end; every one starts where the last ended."""

    def __init__(self, at: tuple[float, float, float]):
        self.at = at
        self.segments: list[dict] = []

    @staticmethod
    def _r(p):
        return [round(v, 3) for v in p]

    def hold(self, seconds: float, phase: str, y: float | None = None):
        if y is not None:
            self.at = (self.at[0], y, self.at[2])
        self.segments.append({"kind": "hold", "phase": phase, "at": self._r(self.at),
                              "seconds": round(max(0.0, seconds), 3)})

    def carry(self, points: list[tuple[float, float, float]], seconds: float, phase: str):
        pts = [self.at] + [p for p in points]
        self.segments.append({"kind": "carry", "phase": phase,
                              "points": [self._r(p) for p in pts],
                              "seconds": round(max(0.05, seconds), 3)})
        self.at = pts[-1]

    def air(self, to: tuple[float, float, float], hang: float, drag: float, gravity: float,
            phase: str, floor_rise: float = 0.0):
        rise = max(floor_rise, gravity * hang * hang / 8.0 * drag)
        self.segments.append({"kind": "air", "phase": phase, "from": self._r(self.at),
                              "to": self._r(to), "rise": round(rise, 3),
                              "seconds": round(max(0.1, hang), 3)})
        self.at = to

    @property
    def seconds(self) -> float:
        return sum(s["seconds"] for s in self.segments)


def _timed(path: dict, speed: float, tokens: dict) -> dict:
    """A path's animation length at a replay speed, the way `duration` scales a play."""
    motion = tokens["motion"]
    factor = max(1.0, float(speed or 1.0) / motion["referenceSpeed"])
    return {**path, "duration": round(max(motion["floorSeconds"], path["seconds"] / factor), 3)}


def play_body(text: str) -> str:
    """The part of a play's text that says what the ball did. A review that
    reversed the call is followed by the play as it stands ("...REVERSED.
    (Shotgun) M.Stafford pass..."), and a conversion or a penalty after the
    play is another snap: "pass to Z.Charbonnet is incomplete" in a two-point
    try must not make the touchdown pass before it fall to the grass."""
    if "REVERSED." in text:
        text = text.rsplit("REVERSED.", 1)[1]
    return re.split(r"TWO-POINT CONVERSION|PENALTY on|\*\* Injury|The Replay Official", text)[0].strip()


def air_point(seg: dict, u: float) -> tuple[float, float, float]:
    """Where an `air` segment has the ball `u` of the way through its hang:
    level ground speed, and a gravity parabola over the chord."""
    u = max(0.0, min(1.0, u))
    a, b = seg["from"], seg["to"]
    return (a[0] + (b[0] - a[0]) * u,
            a[1] + (b[1] - a[1]) * u + seg["rise"] * 4 * u * (1 - u),
            a[2] + (b[2] - a[2]) * u)


def _segment_point(seg: dict, u: float) -> tuple[float, float, float]:
    """SceneMath.segmentPoint in field coordinates: a carry eases in time
    (smoothstep) and is walked by length; air is air_point; a hold is its spot."""
    if seg["kind"] == "air":
        return air_point(seg, u)
    if seg["kind"] == "carry":
        pts = seg["points"]
        e = u * u * (3 - 2 * u)
        lengths = [0.0]
        for a, b in zip(pts, pts[1:]):
            lengths.append(lengths[-1] + math.dist(a, b))
        want = e * lengths[-1]
        i = 1
        while i < len(pts) - 1 and lengths[i] < want:
            i += 1
        span = max(1e-9, lengths[i] - lengths[i - 1])
        k = max(0.0, min(1.0, (want - lengths[i - 1]) / span))
        return tuple(pts[i - 1][j] + (pts[i][j] - pts[i - 1][j]) * k for j in range(3))
    return tuple(seg["at"])


def trail_points(arc: dict, count: int = 72, lift: float = 0.12) -> list[tuple[float, float, float]]:
    """The line a play's trail draws, in field coordinates - SceneMath.trace,
    restated so a port or a test draws the same line: carried legs lie at
    `lift`, a flight's ends ease down to it and its middle keeps its height,
    holds draw nothing."""
    segs = arc["path"]["segments"]

    def length(seg):
        if seg["kind"] == "hold":
            return 0.0
        a, b = _segment_point(seg, 0.0), _segment_point(seg, 1.0)
        flat = math.dist((a[0], a[2]), (b[0], b[2]))
        return flat + 2 * seg.get("rise", 0.0) if seg["kind"] == "air" else flat

    lengths = [length(s) for s in segs]
    total = max(1e-6, sum(lengths))
    out: list[tuple[float, float, float]] = []
    for seg, ln in zip(segs, lengths):
        if seg["kind"] == "hold":
            continue
        n = max(2, round(count * ln / total) + 1)
        for i in range(n):
            f = i / (n - 1)
            if seg["kind"] == "carry":
                e = f
                u = 0.5 - math.sin(math.asin(1 - 2 * e) / 3)
                x, _, z = _segment_point(seg, u)
                q = (x, lift, z)
            else:
                x, y, z = _segment_point(seg, f)
                w = 4 * f * (1 - f)
                q = (x, lift if seg["phase"] == "snap" else lift + w * (y - lift), z)
            if out and math.dist(out[-1], q) < 1e-4:
                continue
            out.append(q)
    return out


def play_path(play: dict, style: str, shape: str, x0: float, x1: float, lane: float,
              side: str | None, goal: dict | None, field: dict, home: dict, away: dict,
              tokens: dict) -> dict:
    """How the ball moves on one play, as timed segments (see `visual.broadcast.play`).

    x0 and x1 are the scene's snap and finish spots; `lane` the drive's layout
    lane the snap sits in. Facing the side's attack (+x for home), right is
    +z x attack. Every segment carries a `phase` a client may key a graphic to:
    presnap, snap, drop, mesh, run, throw, catch, yac, fall, kick, return, walk.
    """
    rule = tokens["visual"]["broadcast"]["play"]
    h, g = rule["heights"], rule["gravity"]
    text = play_body(play.get("text") or "")
    low = text.lower()
    kind = (play.get("type") or "").lower()
    half = field["width"] / 2 - 0.5
    attack = 1.0 if side == "home" else -1.0 if side == "away" else (1.0 if x1 >= x0 else -1.0)
    clamp_z = lambda z: max(-half, min(half, z))
    end_x = (-field["endZone"], field["length"] + field["endZone"])
    clamp_x = lambda x: max(end_x[0], min(end_x[1], x))
    shotgun = bool(play["shotgun"]) if play.get("shotgun") is not None else "shotgun" in low
    path = _Path((x0, h["kick"], lane))
    path.hold(rule["presnapSeconds"], "presnap")

    def lateral(word: str | None, table: dict, default: float = 0.0) -> float:
        if word == "right":
            return attack * table.get("right", table.get("side", default))
        if word == "left":
            return -attack * table.get("left", table.get("side", default))
        return 0.0

    def snap_to_qb():
        if shotgun:
            back = (x0 - attack * rule["snap"]["shotgunYards"], h["carry"], lane)
            path.air(back, rule["snap"]["shotgunSeconds"], 0.0, g, "snap")
        else:
            path.carry([(x0 - attack * 0.6, h["carry"], lane)], rule["snap"]["underCenterSeconds"], "snap")

    def run_from_here(to_x: float, word: str | None, gap: str | None, sideline: bool, scramble: bool):
        r = rule["run"]
        hole = r["holeYards"].get(gap or "", r["holeYards"]["middle"]) if word != "middle" else 0.0
        sign = attack if word == "right" else -attack if word == "left" else 0.0
        hole_z = clamp_z(lane + sign * hole)
        if not scramble:
            # The mesh: the ball is handed off beside the quarterback - just
            # behind the line under center, a step up from him in the gun.
            back = rule["snap"]["shotgunYards"] - 1.0 if shotgun else r["handoffBackYards"]
            mesh = (x0 - attack * back, h["carry"], clamp_z(lane + sign * min(hole, 1.5)))
            path.carry([mesh], r["meshSeconds"], "mesh")
        start = path.at
        at_line = (x0 + attack * 0.5, h["carry"], hole_z)
        d_hole = math.dist(start[::2], at_line[::2])
        path.carry([at_line], max(0.2, d_hole / r["toHoleYardsPerSecond"]), "run")
        gain = to_x - at_line[0]
        drift = sign * min(r["maxDriftYards"], abs(gain) * r["driftShare"])
        end_z = clamp_z(hole_z + drift)
        if sideline:
            end_z = half if (end_z if end_z != 0 else sign or 1.0) > 0 else -half
        # A cut: two-thirds of the way the runner bends toward where he ends.
        cut = (at_line[0] + gain * 0.6, h["carry"], hole_z + (end_z - hole_z) * 0.35)
        end = (to_x, h["carry"], end_z)
        length = math.dist(at_line[::2], cut[::2]) + math.dist(cut[::2], end[::2])
        path.carry([cut, end], max(0.25, length / r["yardsPerSecond"]), "run")
        path.hold(r["settleSeconds"], "settle")

    sideline = bool(re.search(r"\b(?:pushed|ran)\s+ob\b|out of bounds", low))
    gap_m = re.search(r"\b(left|right)\s+(end|tackle|guard)\b", low)
    # nflverse names the gap and the side outright; the text only sometimes
    # does ("up the middle", "right guard"), so it is the fallback.
    gap = play.get("runGap") or (gap_m.group(2) if gap_m else ("middle" if "middle" in low else None))
    word = play.get("runLocation") or (gap_m.group(1) if gap_m else _direction(text))

    if shape == "flat":
        pen = rule["penalty"]
        path.hold(pen["flagSeconds"], "flag", y=h["ground"])
        path.carry([(x1, h["ground"], lane)], pen["walkSeconds"], "walk")

    elif shape == "kick" and goal is not None:
        k = rule["goalKick"]
        path.carry([(x0 - attack * k["backYards"], h["kick"], lane)], k["snapSeconds"], "snap")
        path.hold(k["holdSeconds"], "hold")
        start = path.at
        to = (goal["toX"], 0.0, goal["lane"])
        dist = abs(to[0] - start[0])
        hang = k["hangBase"] + k["hangPerYard"] * dist
        # Clear the crossbar with the clearance the scene promises a good kick.
        floor = 0.0
        plane = field["length"] + field["endZone"] if attack > 0 else -field["endZone"]
        if goal.get("result") == "good" and dist > 0:
            u = abs(plane - start[0]) / dist
            need = CROSSBAR_YARDS + tokens["arc"]["goalKick"].get("minClearanceYards", 1.0)
            base = start[1] + (to[1] - start[1]) * u
            if 0 < u < 1:
                floor = (need + 0.5 - base) / (4 * u * (1 - u))
        path.air(to, hang, k["drag"], g, "kick", floor_rise=floor)

    elif shape == "kick" and ("field goal" in kind or "extra point" in kind):
        # Blocked: the snap, the hold, and the ball knocked down short.
        k = rule["goalKick"]
        path.carry([(x0 - attack * k["backYards"], h["kick"], lane)], k["snapSeconds"], "snap")
        path.hold(k["holdSeconds"], "hold")
        path.air((x0 - attack * (k["backYards"] - 2.0), 0.0, lane), 0.5, 0.3, g, "kick")
        if abs(x1 - path.at[0]) > 1.0:
            path.carry([(x1, h["carry"], clamp_z(lane * 0.6))],
                       max(0.3, abs(x1 - path.at[0]) / rule["returnYardsPerSecond"]), "return")
        path.hold(rule["run"]["settleSeconds"], "settle")

    elif shape == "kick" and "punt" in kind:
        p = rule["punt"]
        path.carry([(x0 - attack * p["backYards"], h["carry"], lane)], p["snapSeconds"], "snap")
        path.hold(p["operationSeconds"], "hold")
        clause = _kick_clause(text)
        n = _RE_YARDS.search(clause.lower())
        land_x = _spot_after(clause, ("to",), home, away)
        kicked = play.get("kickDistance")
        if land_x is None and kicked is not None:
            land_x = x0 + attack * float(kicked)     # nflverse states the distance
        if land_x is None:
            land_x = x0 + attack * (float(n.group(1)) if n else abs(x1 - x0))
        land_x = clamp_x(land_x)
        start = path.at
        hang = p["hangBase"] + p["hangPerYard"] * abs(land_x - x0)
        oob = "out of bounds" in low
        land = (land_x, h["catch"] if not oob else 0.0, clamp_z(lane * 0.5) if not oob else (half + 1.0) * (1 if lane >= 0 else -1))
        path.air(land, hang, p["drag"], g, "kick")
        # The NFL marks the snap that started it ("Center-J.Smith"); college
        # names the return itself. Either way the spot wanted is the one after
        # the catch, not the one the punt came down on.
        tail = text.split("Center-", 1)[-1] if "Center-" in text else _return_clause(clause)
        if "fair catch" in low or "downed" in low or oob or "touchback" in low:
            path.hold(p["fairCatchSeconds"], "catch")
        else:
            back = _spot_after(tail, ("to", "at"), home, away)
            if back is None and "touchdown" in low:
                back = -field["endZone"] / 2 if attack > 0 else field["length"] + field["endZone"] / 2
            if back is None:
                back = x1
            end_z = clamp_z(land[2] * 0.6)
            path.carry([(back, h["carry"], end_z)],
                       max(0.3, math.dist((land[0], land[2]), (back, end_z)) / rule["returnYardsPerSecond"]),
                       "return")
            path.hold(rule["run"]["settleSeconds"], "settle")

    elif shape == "kick":   # kickoffs, and anything else kicked
        k = rule["kickoff"]
        path.hold(k["approachSeconds"], "approach")
        clause = _kick_clause(text)
        land_x = None
        if "to end zone" in clause.lower():
            land_x = (field["length"] + k["endZoneYards"]) if attack > 0 else -k["endZoneYards"]
        else:
            land_x = _spot_after(clause, ("to",), home, away)
        n = _RE_YARDS.search(clause)
        kicked = play.get("kickDistance")
        if land_x is None and kicked is not None:
            land_x = x0 + attack * float(kicked)     # nflverse states the distance
        if land_x is None:
            land_x = x0 + attack * (float(n.group(1)) if n else max(10.0, abs(x1 - x0)))
        land_x = clamp_x(land_x)
        hang = k["hangBase"] + k["hangPerYard"] * abs(land_x - x0)
        # A kick that leaves the field crosses the sideline; it is not caught
        # in the middle of it and then carried out.
        oob = "out of bounds" in low
        land = (land_x, h["catch"] if not oob else 0.0,
                clamp_z(lane * 0.3) if not oob else (half + 1.0) * (1 if lane >= 0 else -1))
        path.air(land, hang, k["drag"], g, "kick")
        if "touchback" in low or "fair catch" in low or oob:
            # None of the three is a return: the ball is dead where it stopped.
            path.hold(k["touchbackSeconds"], "catch")
        else:
            after = _return_clause(clause)
            back = _spot_after(after, ("at", "to"), home, away)
            if back is None and "touchdown" in low:
                back = -field["endZone"] / 2 if attack > 0 else field["length"] + field["endZone"] / 2
            if back is None:
                back = x1
            end_z = clamp_z(land[2] * 0.5)
            path.carry([(back, h["carry"], end_z)],
                       max(0.3, math.dist((land[0], land[2]), (back, end_z)) / rule["returnYardsPerSecond"]),
                       "return")
            path.hold(rule["run"]["settleSeconds"], "settle")

    elif re.search(r"\bkneels?\b", low):
        path.carry([(x0 - attack * 1.0, h["carry"], lane)], 0.5, "snap")
        path.hold(1.0, "settle", y=h["ground"])

    elif re.search(r"\bspike[sd]?\b", low):
        path.carry([(x0 - attack * 0.6, h["carry"], lane)], rule["snap"]["underCenterSeconds"], "snap")
        path.carry([(x0 - attack * 0.4, h["ground"], lane)], 0.25, "spike")
        path.hold(0.6, "settle")

    elif "sack" in kind or " sacked" in low:
        snap_to_qb()
        ps = rule["pass"]
        drop = ps["dropYards"]["shotgun" if shotgun else "underCenter"]
        qb = (x0 - attack * (rule["snap"]["shotgunYards"] if shotgun else 0.0) - attack * drop, h["carry"], lane)
        path.carry([qb], ps["pocketSeconds"]["shotgun" if shotgun else "underCenter"], "drop")
        at = _spot_after(text, ("at",), home, away)
        down_x = at if at is not None else x1
        path.carry([(down_x, h["ground"] + 0.4, clamp_z(lane + 1.2 * (1 if lane <= 0 else -1)))],
                   rule["sack"]["pushSeconds"], "sack")
        path.hold(rule["run"]["settleSeconds"], "settle")

    elif "interception" in kind or "intercepted" in low:
        snap_to_qb()
        ps = rule["pass"]
        drop = ps["dropYards"]["shotgun" if shotgun else "underCenter"]
        qb = (x0 - attack * (rule["snap"]["shotgunYards"] if shotgun else 0.0) - attack * drop, h["release"], lane)
        path.carry([qb], ps["pocketSeconds"]["shotgun" if shotgun else "underCenter"], "drop")
        pick = _spot_after(text.split("INTERCEPTED", 1)[-1], ("at",), home, away)
        depth = _depth(text)
        if pick is None:
            pick = x0 + attack * ps["incompleteAir"][depth]
        pick_z = clamp_z(lane + lateral(_direction(text.split("intended", 1)[0]),
                                        {"side": ps["wideYards"]["deep" if depth == "deep" else "short"]}))
        dist = math.dist((qb[0], qb[2]), (pick, pick_z))
        path.air((pick, h["catch"], pick_z), ps["hangBase"] + ps["hangPerYard"] * dist, ps["drag"], g, "throw")
        tail = text.split("INTERCEPTED", 1)[-1].split(".", 1)[-1]
        back = _spot_after(tail, ("to", "at"), home, away)
        if back is None and "touchdown" in low:
            back = -field["endZone"] / 2 if attack > 0 else field["length"] + field["endZone"] / 2
        if back is None:
            back = x1
        dist = abs(back - pick)
        path.carry([(back, h["carry"], clamp_z(pick_z * 0.6))], max(0.3, dist / rule["returnYardsPerSecond"]), "return")
        path.hold(rule["run"]["settleSeconds"], "settle")

    # The text is the fallback for a play whose type did not say, never a
    # second opinion about one that did: "3-yd run, two-point pass conversion
    # failed" is a run, and drawing it as a pass threw the ball on a rushing
    # touchdown. The conversion is a different play, appended to this one.
    elif shape == "pass" or "pass" in kind or (re.search(r"\bpass\b", low)
                                               and not re.search(r"\b(?:rush|run)", kind)):
        snap_to_qb()
        ps = rule["pass"]
        mode = "shotgun" if shotgun else "underCenter"
        qb_x = x0 - attack * (rule["snap"]["shotgunYards"] if shotgun else 0.0) - attack * ps["dropYards"][mode]
        qb = (qb_x, h["release"], lane)
        path.carry([qb], ps["pocketSeconds"][mode], "drop")
        depth = play.get("passLength") or _depth(text)
        direction = play.get("passLocation") or _direction(text.split(" to ", 1)[0] if " to " in text else text)
        wide = ps["wideYards"]["middle"] if direction == "middle" else ps["wideYards"]["deep" if depth == "deep" else "short"]
        if style == "incomplete" or "incomplete" in low:
            # Where it was thrown, not where the down ended: an incompletion
            # ends the play back at the line, and the ball did not go there.
            air = air_yards(play, tokens=tokens)
            to_z = clamp_z(lane + lateral(direction, {"side": wide}))
            if "thrown away" in low or sideline:
                to_z = (half + 1.5) * (1 if to_z >= 0 else -1)
            to = (clamp_x(x0 + attack * air), 0.0, to_z)
            dist = math.dist((qb[0], qb[2]), (to[0], to[2]))
            path.air(to, ps["hangBase"] + ps["hangPerYard"] * dist, ps["drag"], g, "throw",
                     floor_rise=ps["minRiseYards"])
            path.hold(ps["fallSeconds"], "fall")
        else:
            gain = (x1 - x0) * attack
            air = air_yards(play, gain, tokens)
            catch_x = clamp_x(x0 + attack * air)
            catch_z = clamp_z(lane + lateral(direction, {"side": wide}))
            if sideline:
                # Pushed out after the catch: it was caught near that sideline.
                edge = 1.0 if (catch_z if abs(catch_z) > 1e-6 else lane or 1.0) > 0 else -1.0
                catch_z = edge * (half - ps["sidelineCatchYards"])
            to = (catch_x, h["catch"], catch_z)
            dist = math.dist((qb[0], qb[2]), (to[0], to[2]))
            # A throw always rises enough to read as a throw: at a hundred
            # yards a 1.2 yd arc is flat, and a short pass looked like a run.
            path.air(to, ps["hangBase"] + ps["hangPerYard"] * dist, ps["drag"], g, "throw",
                     floor_rise=ps["minRiseYards"])
            yac = abs(x1 - catch_x)
            end_z = catch_z
            if sideline:
                end_z = half if catch_z >= 0 else -half
            if yac > 0.5 or sideline:
                length = math.dist((catch_x, catch_z), (x1, end_z))
                path.carry([(x1, h["carry"], end_z)], max(0.25, length / ps["yacYardsPerSecond"]), "yac")
            path.hold(ps["settleSeconds"], "settle")

    else:   # every run, scramble, and the plays a run carries
        if shotgun or "scrambles" in low:
            snap_to_qb()
        else:
            path.carry([(x0 - attack * 0.6, h["carry"], lane)], rule["snap"]["underCenterSeconds"], "snap")
        run_from_here(x1, word, gap, sideline, scramble="scrambles" in low)

    total = min(rule["maxSeconds"], path.seconds)
    scale = total / path.seconds if path.seconds > 0 else 1.0
    if scale < 1.0:
        for s in path.segments:
            s["seconds"] = round(s["seconds"] * scale, 3)
    return {"seconds": round(sum(s["seconds"] for s in path.segments), 3),
            "snap": [round(x0, 3), round(lane, 3)],
            "segments": path.segments}


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


# ── moments ──
# What a moment was, beyond its kind, so a client can treat a pick-six
# differently from a drive that ends in the end zone, and an interception
# from a fumble. Read from ESPN's play type; the text only settles a turnover
# whose type does not say (a fumble inside a "Rush").

def moment_detail(play: dict, kind: str) -> str | None:
    t = (play.get("type") or "").lower()
    text = (play.get("text") or "").upper()
    if "interception" in t:
        return "interception"
    if "fumble" in t:
        return "fumble"
    if "punt return" in t:
        return "puntReturn"
    if "kickoff return" in t:
        return "kickReturn"
    if "blocked" in t:
        return "blocked"
    if kind == "turnover":
        if "INTERCEPT" in text:
            return "interception"
        if "FUMBLE" in text:
            return "fumble"
    return None


# Cues are the game's other beats: nothing scored, nothing changed hands, but
# a stadium still reacts - the horn at the end of a quarter, the chime at the
# two-minute warning, the home crowd rising when the visitors face third down,
# the rumble as a drive crosses the twenty, the final whistle. They are kept
# apart from `moments` on purpose: moments stay scores and turnovers, which is
# what every client already reads them as.
CUE_TYPES = {"two-minute warning": "twoMinute", "end period": "quarterEnd",
             "end of half": "halfEnd", "end of regulation": "regulationEnd",
             "end of game": "final"}
RED_ZONE = 20.0


def _cue(kind: str, cue_id: str, play: dict | None, side: str | None, source: str,
         detail: str | None = None, sequence: int = -1) -> dict:
    treatment = kind if kind != "final" else "final" + (detail or "tie")[0].upper() + (detail or "tie")[1:]
    return {"kind": kind, "id": cue_id, "playId": str((play or {}).get("id", "")),
            "side": side, "detail": detail, "treatment": treatment, "source": source,
            "period": (play or {}).get("period"), "clock": (play or {}).get("clock", ""),
            "sequence": sequence}


def build_cues(raw: list[dict], drives_out: list[dict], home: dict, away: dict,
               field: dict) -> list[dict]:
    """Every event cue up to this instant, in the order the game played them.

    `raw` is every play record in order, drawn or not. A red-zone crossing is
    a drawn play whose offence starts outside the twenty and finishes inside
    it without scoring; home attacks x = length."""
    order = {str(p.get("id", "")): i for i, p in enumerate(raw)}
    cues = []
    for i, p in enumerate(raw):
        kind = CUE_TYPES.get((p.get("type") or "").strip().lower())
        if not kind:
            continue
        if kind == "final":
            h, a = _num(home.get("score")), _num(away.get("score"))
            side = "home" if h > a else "away" if a > h else None
            detail = {"home": "homeWon", "away": "awayWon", None: "tie"}[side]
            cues.append(_cue(kind, f"final:{p.get('id', '')}", p, side, "bowl", detail, i))
        else:
            cues.append(_cue(kind, f"{kind}:{p.get('id', '')}", p, None, "pa", None, i))
    length = field["length"]
    for d in drives_out:
        for a in d["arcs"]:
            side, f, t = a["side"], a["fromX"], a["toX"]
            goal_line = length if side == "home" else 0.0
            before, after = abs(goal_line - f), abs(goal_line - t)
            if side in ("home", "away") and before > RED_ZONE >= after > 0 and a["style"] != "score":
                play = {"id": a["id"], "period": a["period"], "clock": a["clock"]}
                cues.append(_cue("redZone", f"redZone:{a['id']}", play, side,
                                 "standsHome" if side == "home" else "standsAway", None,
                                 order.get(a["id"], -1)))
    cues.sort(key=lambda c: c["sequence"])
    return cues


_FANS: dict = {}


def fan_sections(bowl: dict) -> dict:
    """Which `bowl.seating` sections each club's fans fill: the visitors'
    section is `crowd.awaySection` (a side of the bowl beyond a field x), the
    home crowd everything else. A section belongs to whoever sits at its
    middle, on its tier's middle ring. Decided here so no client repeats it."""
    away = bowl["crowd"]["awaySection"]
    key = (json.dumps(bowl["shape"], sort_keys=True), json.dumps(away, sort_keys=True),
           tuple(s["id"] for t in bowl["seating"]["tiers"] for s in t.get("sections", [])))
    if key in _FANS:
        return _FANS[key]
    out = {"home": [], "away": []}
    for tier in bowl["tiers"]:
        seats = next((t for t in bowl["seating"]["tiers"] if t["tier"] == tier["name"]), None)
        if not seats:
            continue
        ring = BowlRing(bowl["shape"], (tier["inner"] + tier["outer"]) / 2)
        for sec in seats.get("sections", []):
            mid = ((sec["from"] + sec["to"]) / 2) % 1.0
            x, z = bowl_point(bowl["shape"], ring.m, ring.angle(mid * ring.length))
            far = z < 0
            visitors = (far if away["side"] == "far" else not far) and x + 50 >= away["fromX"]
            out["away" if visitors else "home"].append(sec["id"])
    _FANS[key] = out
    return out


def dress_final(cues: list[dict], bowl: dict) -> None:
    """The final's crowd: the winners' sections stand, the losers' sit."""
    fans = None
    for c in cues:
        if c["kind"] != "final":
            continue
        fans = fans or fan_sections(bowl)
        if c["side"] in ("home", "away"):
            loser = "away" if c["side"] == "home" else "home"
            c["crowd"] = {"stand": fans[c["side"]], "sit": fans[loser]}
        else:
            c["crowd"] = {"stand": [], "sit": []}


def active_cue(cues: list[dict], raw: list[dict], state: str, status: dict) -> dict | None:
    """The cue for this instant.

    An event cue holds, like a moment, until the game clock moves past it.
    Failing that, a state cue: the visitors facing third down, which is when
    a home crowd is at its loudest. It has no play of its own, so its id is
    the down's own situation and a client plays it once per third down."""
    if cues:
        newest = cues[-1]
        after = raw[newest["sequence"] + 1:] if newest["sequence"] >= 0 else []
        if all((p.get("period"), p.get("clock")) == (newest["period"], newest["clock"]) for p in after):
            return newest
    if state == "in" and status.get("down") == 3 and status.get("possession") == "away":
        last = raw[-1] if raw else {}
        return _cue("thirdDown", f"thirdDown:{last.get('id', '')}:{status.get('distance')}", last,
                    "home", "standsHome", None, len(raw) - 1)
    return None


# ───────────────────────────── the scene ─────────────────────────────

def build(game: dict, league: str | None = None, speed: float = 1.0,
          tokens: dict | None = None) -> dict:
    """The scene for one game at one instant. Pure: `game` is not touched.

    `league` defaults to whatever the game says it is (`league_of`), so a
    caller that does not care cannot silently draw a college game on an NFL
    field. Pass one only to override the payload.
    """
    tokens = tokens or load_tokens()
    league = league or league_of(game)
    rules = RULES.get(league)
    if rules is None:
        raise ValueError(f"no field rules for {league!r}; known: {', '.join(RULES)}")
    field = dict(rules["field"])
    width = field["width"]
    band = tokens["chip"]
    home, away = team_chips(game.get("home") or {}, game.get("away") or {}, band)
    sit = game.get("situation") or {}

    drives_out, moments, raw = [], [], []
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
            side = _side(play.get("team") or drive.get("team", ""), home, away)
            goal = goal_kick(play, _num(x0), side, field, tokens)
            if goal:
                x1 = goal["toX"]
            dist = abs(_num(x1) - _num(x0))
            real = seconds(style, dist, tokens)
            arcs.append({
                "id": str(play.get("id", "")),
                "style": style, "shape": shape,
                "type": play.get("type", ""),
                "fromX": _num(x0), "toX": _num(x1),
                "lane": goal["lane"] if goal else lane(pi, len(plays), width, tokens),
                "apex": apex(shape, dist, tokens),
                "color": f"arc.{style}",
                "dash": tokens["arc"]["dash"].get(style),
                "seconds": real,
                "duration": duration(real, speed, tokens),
                "path": _timed(play_path(play, style, shape, _num(x0), _num(x1),
                                         goal["lane"] if goal else lane(pi, len(plays), width, tokens),
                                         side, goal, field, home, away, tokens), speed, tokens),
                "side": side,
                "text": play.get("text", ""),
                "period": play.get("period"), "clock": play.get("clock", ""),
                "down": play.get("down"), "distance": play.get("distance"),
                # Where this play's geometry came from. A live estimate and a
                # corrected play are drawn the same way and are not the same
                # claim, so the arc says which it is rather than leaving a
                # client to assume the stronger one.
                "source": (play.get("truth") or {}).get("source", "live"),
                "corrected": (play.get("truth") or {}).get("fields") or [],
            })
            last_ref = (len(drives_out), len(arcs) - 1)
        for play in (drive.get("plays") or []):
            raw.append(play)
            h, a = _num(play.get("home"), prev_home), _num(play.get("away"), prev_away)
            if h > prev_home or a > prev_away:
                scorer = "home" if h - prev_home >= a - prev_away else "away"
                points = max(h - prev_home, a - prev_away)
                kind = moment_kind(play, points)
                moments.append({"kind": kind, "side": scorer,
                                "team": (home if scorer == "home" else away)["abbr"],
                                "detail": moment_detail(play, kind),
                                "points": points, "playId": str(play.get("id", "")),
                                "text": play.get("text", ""),
                                "period": play.get("period"), "clock": play.get("clock", "")})
            elif play.get("turnover") and style_of(play):
                offense = _side(play.get("team") or drive.get("team", ""), home, away)
                taker = {"home": "away", "away": "home"}.get(offense)
                if taker:
                    moments.append({"kind": "turnover", "side": taker,
                                    "team": (home if taker == "home" else away)["abbr"],
                                    "detail": moment_detail(play, "turnover"),
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

    # 1.1: whether a moment stops the stadium, and where its banner, light and
    # sound go - the middle of the end zone the scoring side attacks. Home
    # attacks x = 100, so a home score lands in 100..110.
    celebrate = set(tokens["visual"]["moments"]["celebrate"])
    for m in moments:
        m["celebrates"] = m["kind"] in celebrate
        ez = field["endZone"]
        m["anchor"] = {"x": field["length"] + ez / 2 if m["side"] == "home" else -ez / 2,
                       "y": 0.0, "z": 0.0}

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
        if holder and dist:
            step = 1.0 if holder == "home" else -1.0
            gain_x = x + step * _num(dist)
            # Goal to go: there is no line to gain, because the goal line is
            # nearer than it. Decided on where the line would fall, not on
            # `yardsToEndzone`, which ESPN sends for the NFL and never for
            # college - 0 of 887 live college situations carried one. Trusting
            # it painted a line to gain on every college goal-to-go, and for
            # 2nd and 8 from the 3 it painted it five yards inside the end
            # zone. The geometry is in both codes and cannot go missing.
            goal_line = field["length"] if step > 0 else 0.0
            goal_to_go = gain_x >= goal_line if step > 0 else gain_x <= goal_line
            if to_goal is not None:
                goal_to_go = goal_to_go or _num(dist) >= _num(to_goal)
            if not goal_to_go:
                lasers.append({"kind": "lineToGain", "x": gain_x,
                               "color": "laser.lineToGain"})

    props = json.loads(json.dumps(rules["props"]))
    props["pylon"]["at"] = pylon_spots(field, league, props["pylon"]["size"])
    wp = [w.get("home") for w in (game.get("winProbability") or [])
          if w.get("home") is not None]
    tint_side = active["side"] if active and active["kind"] != "turnover" else None
    bowl = json.loads(json.dumps(BOWL))
    bowl["shape"].update({"halfLength": field["length"] / 2 + field["endZone"],
                          "halfWidth": width / 2})
    bowl["seating"] = bowl_seating(bowl["shape"], tokens["visual"]["bowl"]["rows"])
    bowl["mounts"] = bowl_mounts(bowl["shape"], tokens["visual"]["lighting"]["rim"])
    # Shirts wear the chip, not the raw club colour: at night a navy or a
    # black shirt is indistinguishable from an empty seat, and the chip is
    # the same hue solved into a band that reads.
    bowl["crowd"] = {"home": home["chip"], "away": away["chip"],
                     "neutral": "crowd.neutral", "dark": "crowd.dark",
                     "awaySection": {"side": "far", "fromX": 90.0}}
    bowl["sectionTint"] = {"side": tint_side,
                           "color": (home if tint_side == "home" else away)["chip"]
                           if tint_side else None,
                           "dim": tokens["motion"]["sectionDim"]}

    status = {"state": state, "label": game.get("label") or status_label(game, state, league),
              "clock": game.get("clock", ""), "period": game.get("period", 0),
              "homeScore": home["score"], "awayScore": away["score"],
              "possession": holder, "down": sit.get("down"),
              "distance": sit.get("distance"),
              "downDistance": sit.get("downDistanceText") or "",
              "redZone": bool(sit.get("isRedZone"))}
    cues = build_cues(raw, drives_out, home, away, field)
    dress_final(cues, bowl)

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
                  "props": props,
                  "art": field_art(field, league, home, away,
                                   paint=tokens["visual"]["field"]["paint"],
                                   turf=tokens["color"]["turf.a"]),
                  "markings": f"actors/field/markings/{league}",
                  "homeEndZone": [-field["endZone"], 0.0],
                  "awayEndZone": [field["length"], field["length"] + field["endZone"]]},
        "teams": {"home": home, "away": away},
        "status": status,
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
        # The game's other beats, and the one playing now (see build_cues). Additive; the director bumps the minor version at merge.
        "cues": cues,
        "activeCue": active_cue(cues, raw, state, status),
        "bowl": bowl,
        "presentation": PRESENTATION,
        "palette": tokens["color"],
        "shaderGraph": tokens.get("shaderGraph", {}),
        "motion": tokens["motion"],
        "visual": {**tokens["visual"], "experience": experience_visual(tokens, field)},
    }
