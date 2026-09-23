"""Draw the initial Saturday mockups from the recorded 2026-09-12 slate.

Every score, clock, drive arc and win-probability point on these artboards is
read out of data/capture, never typed in, so a mockup cannot quietly show a
game state that did not happen. The output is static .dc.html: literal markup
with inline styles, which is what a designer edits by hand afterwards.

    python3 design/build.py        # writes design/*.dc.html and canvas.json
"""
from __future__ import annotations

import colorsys
import glob
import gzip
import html
import json
import math
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
CAP = ROOT / "data/capture/2026-09-12"
OUT = ROOT / "design"
AT = "20260913T003400Z"                      # the moment the wall depicts
SPOT = "401856682"                           # Ohio State at Texas

# ───────────────────────────── tokens ─────────────────────────────
# The three fills are Theme.swift's, unchanged: they were measured on glass.
INK, INK2, INK3 = "#F7F6F2", "rgba(247,246,242,0.74)", "rgba(247,246,242,0.58)"
PLATE = "rgba(18,20,23,0.88)"
GREEN_FILL, RED_FILL, GOLD_FILL = "#237A04", "#DF0B0B", "#8B7300"
GOLD, RED, BLUE = "#FFD400", "#FF4B4B", "#58A7FF"
TURF_A, TURF_B = "#0E3A1F", "#124726"
ROOM_DARK, ROOM_BRIGHT = "#1a1c20", "#d8dad4"
DISPLAY = "'Big Shoulders Display', 'Arial Narrow', sans-serif"
SANS = "'Instrument Sans', 'Helvetica Neue', Arial, sans-serif"
SERIF = "'Instrument Serif', Georgia, serif"
FONTS = ("https://fonts.googleapis.com/css2?family=Big+Shoulders+Display:wght@600;700;800;900"
         "&amp;family=Instrument+Sans:wght@400;500;600;700&amp;family=Instrument+Serif:ital@0;1&amp;display=swap")
BAND = 0.159                                 # Theme.chipFill's target luminance


def e(s) -> str:
    return html.escape(str(s), quote=True)


# ───────────────────────────── colour ─────────────────────────────

def lin(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def lum(rgb) -> float:
    r, g, b = (lin(x) for x in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b) -> float:
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def rgb(hexs: str):
    h = hexs.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def hexof(c) -> str:
    return "#" + "".join(f"{round(max(0, min(1, x)) * 255):02X}" for x in c)


def over(fg, alpha, bg):
    return tuple(f * alpha + b * (1 - alpha) for f, b in zip(fg, bg))


def chip(hexs: str | None) -> str:
    """Theme.chipFill for a team colour: keep its hue, solve value into the band.

    A blue at full saturation cannot reach the band at any value, so
    saturation gives way first; a near-neutral colour stays neutral.
    """
    h, s, _ = colorsys.rgb_to_hsv(*rgb(hexs or "#666666"))
    s = 0.0 if s < 0.12 else min(s, 0.92)
    while s > 0 and lum(colorsys.hsv_to_rgb(h, s, 1.0)) < BAND:
        s -= 0.02
    lo, hi = 0.0, 1.0
    for _ in range(30):
        m = (lo + hi) / 2
        if lum(colorsys.hsv_to_rgb(h, max(s, 0), m)) < BAND:
            lo = m
        else:
            hi = m
    return hexof(colorsys.hsv_to_rgb(h, max(s, 0), (lo + hi) / 2))


def clash(a: str, b: str) -> bool:
    (ha, sa, _), (hb, sb, _) = (colorsys.rgb_to_hsv(*rgb(x)) for x in (a, b))
    if sa < 0.12 and sb < 0.12:
        return True
    d = abs(ha - hb) * 360
    return min(d, 360 - d) < 16 and sa >= 0.12 and sb >= 0.12


# ───────────────────────────── data ─────────────────────────────

def gz(path) -> dict:
    with gzip.open(path, "rt") as f:
        return json.load(f)


def snapshot(pattern: str, at: str = AT) -> dict:
    files = [p for p in sorted(glob.glob(str(CAP / pattern))) if pathlib.Path(p).name[:16] <= at[:16]]
    return gz(files[-1])


def yards_to_goal(text: str | None, offense: str) -> int | None:
    m = re.search(r"at ([A-Z&\-]+) (\d+)", text or "")
    if not m:
        return 50 if text and text.endswith("at 50") else None
    side, n = m.group(1), int(m.group(2))
    return 100 - n if side == offense else n


def games(board: dict) -> dict[str, dict]:
    out = {}
    for ev in board["events"]:
        c = ev["competitions"][0]
        st = ev["status"]
        sit = c.get("situation") or {}
        sides = {}
        for x in c["competitors"]:
            t = x["team"]
            rank = (x.get("curatedRank") or {}).get("current", 99)
            sides[x["homeAway"]] = {
                "id": t["id"], "abbr": t["abbreviation"], "name": t.get("location") or t["displayName"],
                "rank": rank if rank <= 25 else None, "score": x.get("score") or "0",
                "color": "#" + (t.get("color") or "666666"), "alt": "#" + (t.get("alternateColor") or "666666"),
                "record": ((x.get("records") or [{}])[0]).get("summary", ""),
            }
        pos_id = sit.get("possession")
        offense = next((s["abbr"] for s in sides.values() if s["id"] == pos_id), None)
        away, home = sides["away"], sides["home"]
        away["fill"], home["fill"] = chip(away["color"]), chip(home["color"])
        away["hatch"] = False
        if clash(away["fill"], home["fill"]):
            # Away gives way. Its alternate only if that is a real colour and a
            # different one; otherwise it keeps its own colour and gains a
            # hatch, because a grey chip reads as "no team" rather than "them".
            alt = chip(away["alt"])
            if colorsys.rgb_to_hsv(*rgb(alt))[1] >= 0.12 and not clash(alt, home["fill"]):
                away["fill"] = alt
            else:
                away["hatch"] = True
        out[ev["id"]] = {
            "id": ev["id"], "state": st["type"]["state"], "detail": st["type"]["shortDetail"],
            "period": st.get("period", 0), "clock": st.get("displayClock", ""),
            "away": away, "home": home, "offense": offense,
            "down": sit.get("downDistanceText"), "redzone": bool(sit.get("isRedZone")),
            "ytg": yards_to_goal(sit.get("downDistanceText"), offense) if offense else None,
            "tv": ", ".join(((c.get("broadcasts") or [{}])[0]).get("names", [])[:1]),
            "venue": (c.get("venue") or {}).get("fullName", ""),
            "lastPlay": ((sit.get("lastPlay") or {}).get("text") or ""),
        }
    return out


BOARD = games(snapshot("scoreboard/*.json.gz"))
EARLY = games(snapshot("scoreboard/*.json.gz", "20260913T002000Z"))   # while Clemson sat delayed
SUM = snapshot(f"live/{SPOT}/*.json.gz")
WAKE = gz(CAP / "final/401858224.json.gz")


# ───────────────────────────── glyphs ─────────────────────────────
# One stroke family: 24-unit grid, 1.8 stroke, round caps. Colour is always
# currentColor, so a glyph carries meaning even when the chip beside it fails.
GLYPH = {
    "live": '<circle cx="12" cy="12" r="2.6" fill="currentColor" stroke="none"></circle><path d="M7.8 7.8a6 6 0 0 0 0 8.4M16.2 7.8a6 6 0 0 1 0 8.4M4.9 4.9a10 10 0 0 0 0 14.2M19.1 4.9a10 10 0 0 1 0 14.2"></path>',
    "ball": '<path d="M4.5 19.5c-1.6-4.6.2-10 4.3-13.1 3-2.2 7-2.8 10.7-1.9 1.6 4.6-.2 10-4.3 13.1-3 2.2-7 2.8-10.7 1.9z"></path><path d="M9.5 14.5l5-5M10.6 11.4l2 2M12.6 9.4l2 2M8.6 13.4l2 2"></path>',
    "redzone": '<path d="M19 3v18"></path><path d="M4 8l5 4-5 4M10 8l5 4-5 4"></path>',
    "upset": '<path d="M13.5 2.5L5 13.5h6l-1.5 8 8.5-11h-6z"></path>',
    "ot": '<path d="M20 12a8 8 0 1 1-2.4-5.7"></path><path d="M20 3.5v4.5h-4.5"></path><path d="M12 8v4.2l2.6 1.6"></path>',
    "delayed": '<path d="M6.5 3h11M6.5 21h11"></path><path d="M7.5 3c0 5 9 5 9 9s-9 4-9 9M16.5 3c0 3.5-3 4.5-4.5 5.5"></path>',
    "final": '<circle cx="12" cy="12" r="9"></circle><rect x="8.5" y="8.5" width="7" height="7" rx="1" fill="currentColor" stroke="none"></rect>',
    "tv": '<rect x="3" y="5" width="18" height="12" rx="2"></rect><path d="M8 21h8"></path>',
    "win": '<path d="M8 5l9 7-9 7z" fill="currentColor"></path>',
    "cube": '<path d="M12 2.8l8 4.6v9.2l-8 4.6-8-4.6V7.4z"></path><path d="M4 7.4l8 4.6 8-4.6M12 12v9.2"></path>',
    "stadium": '<path d="M2.5 9c3-2.5 16-2.5 19 0v7c-3 2.5-16 2.5-19 0z"></path><path d="M2.5 9c3 2.5 16 2.5 19 0"></path><path d="M6 4v3M12 3v3M18 4v3"></path>',
    "flag": '<path d="M6 21V4l12 5-12 5"></path>',
    "turnover": '<path d="M6 6l12 12M18 6L6 18"></path>',
}


def g(name: str, size: int = 18, color: str = "currentColor", extra: str = "") -> str:
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" '
            f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink: 0; {extra}">'
            f'{GLYPH[name]}</svg>')


# ───────────────────────────── pieces ─────────────────────────────

def team_chip(t: dict, w: int = 60, h: int = 28, fs: int = 17) -> str:
    """The slanted broadcast slab. White on a band fill clears 4.5:1 for any team."""
    bg = t["fill"]
    if t.get("hatch"):
        bg = f"repeating-linear-gradient(135deg, {t['fill']} 0 7px, rgba(0,0,0,0.28) 7px 10px), {t['fill']}"
    return (f'<div style="width: {w}px; height: {h}px; background: {bg}; color: #FFFFFF; display: flex; '
            f'align-items: center; justify-content: center; font-family: {DISPLAY}; font-weight: 800; '
            f'font-size: {fs}px; letter-spacing: 0.04em; clip-path: polygon(0 0, 100% 0, calc(100% - {h // 3}px) 100%, 0 100%); '
            f'padding-right: {h // 4}px; box-sizing: border-box; flex-shrink: 0">{e(t["abbr"])}</div>')


def badge(text: str, fill: str, glyph: str | None = None, fs: int = 12) -> str:
    icon = g(glyph, fs + 3) if glyph else ""
    return (f'<div style="display: flex; align-items: center; gap: 5px; background: {fill}; color: #FFFFFF; '
            f'padding: 3px 9px 3px 7px; font-family: {SANS}; font-weight: 700; font-size: {fs}px; '
            f'letter-spacing: 0.08em; text-transform: uppercase; clip-path: polygon(0 0, 100% 0, calc(100% - 6px) 100%, 0 100%); '
            f'padding-right: 12px">{icon}<span>{e(text)}</span></div>')


def field_bar(gm: dict, w: int, h: int, markers: bool = True) -> str:
    """A 100-yard strip, drawn so the offense always attacks to the right."""
    if gm["ytg"] is None:
        return f'<div style="height: {h}px; width: {w}px; background: rgba(255,255,255,0.06)"></div>'
    off = gm["away"] if gm["away"]["abbr"] == gm["offense"] else gm["home"]
    de = gm["home"] if off is gm["away"] else gm["away"]
    ez = max(4, round(w * 10 / 120))
    play = w - 2 * ez
    ball = ez + play * (100 - gm["ytg"]) / 100
    m = re.search(r"& (\d+|Goal)", gm["down"] or "")
    togo = gm["ytg"] if (m and m.group(1) == "Goal") else int(m.group(1)) if m else 10
    first = ez + play * min(100, 100 - gm["ytg"] + togo) / 100
    rz = f'<div style="position: absolute; left: {ez + play * 0.8:.1f}px; top: 0; width: {play * 0.2:.1f}px; height: 100%; background: rgba(223,11,11,0.30)"></div>' if gm["redzone"] else ""
    lines = "".join(f'<div style="position: absolute; left: {ez + play * y / 100:.1f}px; top: 0; width: 1px; height: 100%; background: rgba(255,255,255,{0.35 if y == 50 else 0.16})"></div>' for y in range(10, 100, 10))
    mk = ""
    if markers:
        mk = (f'<div style="position: absolute; left: {first - 1:.1f}px; top: -2px; width: 2px; height: {h + 4}px; background: {GOLD}"></div>'
              f'<div style="position: absolute; left: {ball - 1:.1f}px; top: -2px; width: 2px; height: {h + 4}px; background: {BLUE}"></div>'
              f'<div style="position: absolute; left: {ball - h * 0.55:.1f}px; top: {h * 0.12:.1f}px; width: {h * 1.1:.1f}px; height: {h * 0.76:.1f}px; border-radius: 50%; background: #7A3E17; border: 1.5px solid #F7F6F2; box-sizing: border-box"></div>')
    return (f'<div style="position: relative; width: {w}px; height: {h}px; background: linear-gradient(90deg, {TURF_A}, {TURF_B} 50%, {TURF_A}); flex-shrink: 0">'
            f'<div style="position: absolute; left: 0; top: 0; width: {ez}px; height: 100%; background: {off["fill"]}"></div>'
            f'<div style="position: absolute; right: 0; top: 0; width: {ez}px; height: 100%; background: {de["fill"]}"></div>'
            f'{lines}{rz}{mk}</div>')


def status_line(gm: dict, fs: int = 13) -> str:
    s = gm["state"]
    if s == "pre":
        left = f'<span style="color: {INK2}">{e(gm["detail"].split(" - ")[-1])}</span>'
    elif gm["detail"] == "Delayed":
        left = f'{g("delayed", fs + 3)}<span>Delayed</span>'
    elif s == "post":
        left = f'{g("final", fs + 3)}<span>{e(gm["detail"])}</span>'
    else:
        left = f'<span style="color: #6BE04A; display: flex">{g("live", fs + 4)}</span><span>{e(gm["detail"].replace(" - ", " · "))}</span>'
    return (f'<div style="display: flex; align-items: center; justify-content: space-between; font-family: {SANS}; '
            f'font-size: {fs}px; font-weight: 600; color: {INK}; letter-spacing: 0.02em">'
            f'<div style="display: flex; align-items: center; gap: 6px">{left}</div>'
            f'<div style="display: flex; align-items: center; gap: 5px; color: {INK2}; font-weight: 500">{e(gm["tv"])}</div></div>')


def team_row(gm: dict, side: str, size: str) -> str:
    t = gm[side]
    other = gm["home" if side == "away" else "away"]
    big = {"m": 38, "s": 26, "l": 46}[size]
    chipw, chiph, chipfs = {"m": (62, 28, 17), "s": (52, 24, 15), "l": (72, 32, 19)}[size]
    lost = gm["state"] == "post" and int(t["score"]) < int(other["score"])
    won = gm["state"] == "post" and not lost
    ink = INK3 if lost else INK
    poss = g("ball", 16, INK) if gm["offense"] == t["abbr"] and gm["state"] == "in" else ""
    rank = f'<span style="font-family: {SANS}; font-size: 12px; font-weight: 600; color: {INK2}">#{t["rank"]}</span>' if t["rank"] else ""
    name = "" if size == "s" else f'<span style="font-family: {SANS}; font-size: 15px; font-weight: 500; color: {ink}; white-space: nowrap; overflow: hidden; text-overflow: ellipsis">{e(t["name"])}</span>'
    if gm["state"] == "pre":
        score = f'<span style="font-family: {SANS}; font-size: 13px; color: {INK2}">{e(t["record"])}</span>'
    else:
        score = (f'<span style="font-family: {DISPLAY}; font-weight: 800; font-size: {big}px; line-height: 1; color: {ink}; '
                 f'font-variant-numeric: tabular-nums">{e(t["score"])}</span>')
    mark = f'<span style="color: {INK}; display: flex">{g("win", 12)}</span>' if won else '<span style="width: 12px"></span>'
    return (f'<div style="display: flex; align-items: center; gap: 10px; min-width: 0">{team_chip(t, chipw, chiph, chipfs)}'
            f'<div style="display: flex; align-items: baseline; gap: 6px; flex-grow: 1; min-width: 0">{rank}{name}</div>'
            f'<div style="display: flex; align-items: center; gap: 6px">{poss}{score}{mark if gm["state"] == "post" else ""}</div></div>')


def is_upset(gm: dict) -> bool:
    if gm["state"] != "post":
        return False
    a, h = gm["away"], gm["home"]
    win, lose = (a, h) if int(a["score"]) > int(h["score"]) else (h, a)
    return bool(lose["rank"]) and (not win["rank"] or win["rank"] > lose["rank"])


def tile(gm: dict, w: int = 312, h: int = 176, size: str = "m", note: str | None = None, override: dict | None = None) -> str:
    gm = {**gm, **(override or {})}
    delayed = gm["detail"] == "Delayed"
    border = "1px solid rgba(255,255,255,0.10)"
    top = ""
    if gm["redzone"] and gm["state"] == "in":
        border = f"2px solid {RED_FILL}"
        top = badge("Red zone", RED_FILL, "redzone")
    elif is_upset(gm):
        border = f"2px solid {GOLD_FILL}"
        top = badge("Upset", GOLD_FILL, "upset")
    elif gm.get("ot"):
        border = f"2px solid {INK2}"
        top = badge(gm["ot"], "#3B3F46", "ot")
    sit = ""
    if gm["state"] == "in" and not delayed and size != "s":
        down = gm["down"] or ("Halftime" if "Half" in gm["detail"] else "")
        sit = (f'<div style="display: flex; align-items: center; justify-content: space-between; gap: 8px; font-family: {SANS}; font-size: 13px; font-weight: 600; color: {INK}">'
               f'<span>{e(down)}</span>{top}</div>{field_bar(gm, w - 32, 10)}')
    elif top:
        sit = f'<div style="display: flex; justify-content: flex-end">{top}</div>'
    elif gm["state"] == "pre" and size != "s":
        sit = f'<div style="font-family: {SANS}; font-size: 13px; color: {INK2}; white-space: nowrap; overflow: hidden; text-overflow: ellipsis">{e(gm["venue"])}</div>'
    body = (f'{status_line(gm, 13 if size != "s" else 12)}'
            f'<div style="display: flex; flex-direction: column; gap: {8 if size != "s" else 5}px">{team_row(gm, "away", size)}{team_row(gm, "home", size)}</div>{sit}')
    return (f'<div style="width: {w}px; height: {h}px; box-sizing: border-box; padding: {14 if size != "s" else 10}px 16px; background: {PLATE}; '
            f'border: {border}; border-radius: 22px; display: flex; flex-direction: column; justify-content: space-between; '
            f'opacity: {0.82 if delayed else 1}; box-shadow: 0 10px 30px rgba(0,0,0,0.28)">{body}</div>')


def section(over: str, title: str, fs: int = 26) -> str:
    return (f'<div style="display: flex; align-items: baseline; gap: 12px">'
            f'<span style="font-family: {SERIF}; font-style: italic; font-size: {fs}px; color: {INK}; line-height: 1">{e(title)}</span>'
            f'<span style="font-family: {SANS}; font-size: 12px; font-weight: 600; letter-spacing: 0.14em; text-transform: uppercase; color: {INK2}">{e(over)}</span></div>')


def room(kind: str, w: int, h: int, inner: str) -> str:
    if kind == "dark":
        bg = (f"radial-gradient(900px 520px at 12% 8%, rgba(255,190,120,0.16), transparent 70%), "
              f"radial-gradient(1000px 700px at 88% 92%, rgba(80,120,200,0.14), transparent 70%), "
              f"linear-gradient(180deg, #202329 0%, {ROOM_DARK} 60%, #131417 100%)")
    else:
        bg = (f"radial-gradient(900px 600px at 80% 10%, rgba(255,255,250,0.85), transparent 70%), "
              f"radial-gradient(700px 500px at 10% 90%, rgba(150,160,140,0.35), transparent 70%), "
              f"linear-gradient(180deg, #e4e5df 0%, {ROOM_BRIGHT} 55%, #c7c9c2 100%)")
    grain = (f'<svg width="{w}" height="{h}" style="position: absolute; inset: 0; opacity: 0.09; pointer-events: none">'
             f'<filter id="grain"><feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" stitchTiles="stitch"></feTurbulence></filter>'
             f'<rect width="100%" height="100%" filter="url(#grain)"></rect></svg>')
    return f'<div style="position: relative; width: {w}px; height: {h}px; overflow: hidden; background: {bg}">{grain}{inner}</div>'


def glass(x: int, y: int, w: int, h: int, inner: str, radius: int = 46, pad: str = "36px") -> str:
    return (f'<div style="position: absolute; left: {x}px; top: {y}px; width: {w}px; height: {h}px; box-sizing: border-box; '
            f'padding: {pad}; border-radius: {radius}px; background: rgba(34,36,40,0.80); backdrop-filter: blur(40px) saturate(1.3); '
            f'border: 1px solid rgba(255,255,255,0.16); box-shadow: inset 0 1px 0 rgba(255,255,255,0.18), 0 40px 90px rgba(0,0,0,0.35)">{inner}</div>')


def doc(body: str) -> str:
    return ('<!doctype html>\n<html>\n<head>\n  <meta charset="utf-8">\n  <script src="./support.js"></script>\n</head>\n<body>\n<x-dc>\n'
            f'<helmet>\n  <link rel="stylesheet" href="{FONTS}">\n'
            f'  <style>body {{ margin: 0; background: #111214; font-family: {SANS}; }} a {{ color: {GOLD}; }} a:hover {{ color: #FFE766; }}</style>\n</helmet>\n'
            f'{body}\n</x-dc>\n</body>\n</html>\n')


def button(label: str, glyph: str, primary: bool = False, w: int | None = None) -> str:
    bg = INK if primary else "rgba(255,255,255,0.12)"
    fg = "#141619" if primary else INK
    width = f"width: {w}px; justify-content: center;" if w else ""
    return (f'<div style="display: flex; align-items: center; gap: 10px; height: 60px; padding: 0 24px; border-radius: 30px; '
            f'background: {bg}; color: {fg}; font-family: {SANS}; font-weight: 600; font-size: 17px; box-sizing: border-box; {width}">'
            f'{g(glyph, 22)}<span>{e(label)}</span></div>')


# ───────────────────────────── spotlight ─────────────────────────────

def summary_state(sm: dict) -> dict:
    h = sm["header"]["competitions"][0]
    sides = {c["homeAway"]: c for c in h["competitors"]}
    wp = sm.get("winprobability") or []
    return {"home_wp": wp[-1]["homeWinPercentage"] if wp else 0.5, "sides": sides,
            "detail": h["status"]["type"]["shortDetail"]}


def last_plays(sm: dict, n: int = 1) -> list[dict]:
    cur = (sm.get("drives") or {}).get("current") or {}
    return [p for p in cur.get("plays", []) if p["type"]["text"] not in ("End Period", "Timeout")][-n:]


def spot_game() -> dict:
    """The spotlight game as of its own summary, which is newer than the board.

    The scoreboard and the summary are separate polls a minute apart; drawing
    the down from one and the score from the other would put a state on screen
    that never existed. The next snap is derived from the last play instead.
    """
    gm = dict(BOARD[SPOT])
    last = last_plays(SUM)[0]
    m = re.match(r"(\d)(?:st|nd|rd|th) & (\d+|Goal)", last["start"].get("downDistanceText") or "")
    ytg = last["end"]["yardLine"]
    yds = last.get("statYardage") or 0
    if m:
        down, dist = int(m.group(1)), (ytg if m.group(2) == "Goal" else int(m.group(2)))
        down, dist = (1, min(10, ytg)) if yds >= dist else (down + 1, dist - yds)
        side = "TEX" if ytg <= 50 else "OSU"
        spot = ytg if ytg <= 50 else 100 - ytg
        gm["down"] = f"{down}{['st','nd','rd','th'][min(down, 4) - 1]} & {dist if dist < ytg else 'Goal'} at {side} {spot}"
    gm["ytg"], gm["redzone"], gm["offense"] = ytg, ytg <= 20, last_team(SUM)
    st = summary_state(SUM)
    gm["away"] = {**gm["away"], "score": st["sides"]["away"]["score"]}
    gm["home"] = {**gm["home"], "score": st["sides"]["home"]["score"]}
    gm["detail"] = st["detail"]
    return gm


def last_team(sm: dict) -> str:
    return sm["drives"]["current"]["team"]["abbreviation"]


def spotlight(gm: dict, w: int, h: int) -> str:
    st = summary_state(SUM)
    osu_wp = 1 - st["home_wp"]
    last = last_plays(SUM)[0]
    lead = gm["away"] if int(gm["away"]["score"]) >= int(gm["home"]["score"]) else gm["home"]
    lead_wp = osu_wp if lead is gm["away"] else 1 - osu_wp
    # The light bank: the one decorative element, and it is doing a job -
    # it is how the spotlight game reads as lit rather than merely larger.
    bank = "".join(f'<div style="width: 9px; height: 9px; border-radius: 50%; background: #FFF4D6; box-shadow: 0 0 10px 3px rgba(255,236,190,0.55)"></div>' for _ in range(14))

    def big_team(t):
        rank = f'<span style="font-family: {DISPLAY}; font-weight: 700; font-size: 22px; color: {INK2}">#{t["rank"]}</span>' if t["rank"] else ""
        poss = g("ball", 26, INK) if gm["offense"] == t["abbr"] else '<span style="width: 26px"></span>'
        return (f'<div style="display: flex; align-items: center; gap: 16px">{team_chip(t, 96, 44, 26)}'
                f'<div style="display: flex; flex-direction: column; gap: 2px; flex-grow: 1">'
                f'<div style="display: flex; align-items: baseline; gap: 8px">{rank}<span style="font-family: {SANS}; font-size: 22px; font-weight: 600; color: {INK}">{e(t["name"])}</span></div>'
                f'<span style="font-family: {SANS}; font-size: 14px; color: {INK2}">{e(t["record"])}</span></div>'
                f'{poss}<span style="font-family: {DISPLAY}; font-weight: 900; font-size: 72px; line-height: 0.9; color: {INK}; font-variant-numeric: tabular-nums; min-width: 64px; text-align: right">{e(t["score"])}</span></div>')

    wpbar = (f'<div style="display: flex; flex-direction: column; gap: 6px">'
             f'<div style="display: flex; justify-content: space-between; font-family: {SANS}; font-size: 13px; font-weight: 600; color: {INK}">'
             f'<span>{e(lead["abbr"])} {lead_wp * 100:.0f}% to win</span><span style="color: {INK2}">ESPN win probability</span></div>'
             f'<div style="display: flex; height: 8px; gap: 2px"><div style="width: {osu_wp * 100:.1f}%; background: {gm["away"]["fill"]}"></div>'
             f'<div style="flex-grow: 1; background: {gm["home"]["fill"]}"></div></div></div>')
    play_text = re.sub(r"^\(\d+:\d+\)\s*(Shotgun\s*)?", "", last["text"])
    play_text = re.sub(r"#\d+ ", "", play_text).split(" (")[0]
    return (f'<div style="position: relative; width: {w}px; height: {h}px; box-sizing: border-box; padding: 30px 30px 24px; border-radius: 30px; '
            f'background: radial-gradient(420px 220px at 50% -40px, rgba(255,236,190,0.16), transparent 80%), {PLATE}; '
            f'border: 2px solid {RED_FILL}; display: flex; flex-direction: column; gap: 13px; box-shadow: 0 30px 70px rgba(0,0,0,0.45), 0 0 0 8px rgba(255,236,190,0.04)">'
            f'<div style="position: absolute; top: 12px; left: 50%; transform: translateX(-50%); display: flex; gap: 9px">{bank}</div>'
            f'<div style="display: flex; flex-direction: column; gap: 10px; padding-top: 8px">'
            f'{section("ranked · close · driving", "The Big Game", 30)}{status_line(gm, 15)}</div>'
            f'<div style="display: flex; flex-direction: column; gap: 10px">{big_team(gm["away"])}{big_team(gm["home"])}</div>'
            f'<div style="display: flex; align-items: center; justify-content: space-between">'
            f'<span style="font-family: {DISPLAY}; font-weight: 800; font-size: 36px; color: {INK}; letter-spacing: 0.01em">{e(gm["down"])}</span>{badge("Red zone", RED_FILL, "redzone", 14)}</div>'
            f'{field_bar(gm, w - 60, 34)}'
            f'<div style="font-family: {SANS}; font-size: 15px; color: {INK2}; line-height: 1.35"><span style="color: {INK}; font-weight: 600">Last play</span> · {e(play_text)}</div>'
            f'{wpbar}'
            f'<div style="display: flex; gap: 14px">{button("View in 3D", "cube", True)}{button("Game detail", "flag")}</div></div>')


# ───────────────────────────── artboards ─────────────────────────────

def wall() -> str:
    W, H = 1840, 1180
    b = BOARD
    spot = spot_game()
    close_late = [b["401866418"], b["401871045"], b["401856783"]]
    ranked = [b["401856681"], b["401856676"], b["401867796"]]
    also = [b[i] for i in ("401856788", "401860881", "401862707", "401864575", "401862703", "401868008", "401858443", "401856789")]
    finals = [b[i] for i in ("401858224", "401856782", "401856679", "401868187")]
    live_n = sum(1 for x in b.values() if x["state"] == "in")
    pre_n = sum(1 for x in b.values() if x["state"] == "pre")
    post_n = sum(1 for x in b.values() if x["state"] == "post")
    wake = {"ot": "2OT"}

    def row(tiles):
        return f'<div style="display: flex; gap: 20px">{"".join(tiles)}</div>'

    counts = "".join(
        f'<div style="display: flex; align-items: center; gap: 8px; height: 44px; padding: 0 16px; border-radius: 22px; background: rgba(255,255,255,0.08); font-family: {SANS}; font-size: 15px; font-weight: 600; color: {INK}">{glyph}<span>{n} {label}</span></div>'
        for glyph, n, label in ((f'<span style="color: #6BE04A; display: flex">{g("live", 18)}</span>', live_n, "live"),
                                (g("delayed", 18), pre_n, "to come"), (g("final", 18), post_n, "final")))
    header = (f'<div style="display: flex; align-items: center; justify-content: space-between; height: 60px">'
              f'<div style="display: flex; align-items: baseline; gap: 18px"><span style="font-family: {DISPLAY}; font-weight: 900; font-size: 52px; letter-spacing: 0.02em; color: {INK}; text-transform: uppercase; line-height: 1">Saturday</span>'
              f'<span style="font-family: {SERIF}; font-style: italic; font-size: 24px; color: {INK2}">September 12 · FBS</span></div>'
              f'<div style="display: flex; gap: 10px">{counts}</div></div>')

    right = (f'<div style="display: flex; flex-direction: column; gap: 14px">'
             f'{section("4th quarter or within one score", "Close & late")}{row([tile(x) for x in close_late])}'
             f'{section("Top 25 in progress", "Ranked, live")}{row([tile(x) for x in ranked])}'
             f'<div style="display: flex; align-items: baseline; justify-content: space-between">{section(f"{live_n - 7} more live · look to scroll", "Everything else")}</div>'
             f'<div style="display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px">{"".join(tile(x, 228, 100, "s") for x in also)}</div></div>')
    finals_rail = (f'<div style="display: flex; flex-direction: column; gap: 14px; margin-top: 20px">{section("Upsets, overtime, one-score", "Tonight so far")}'
                   f'<div style="display: flex; gap: 20px">'
                   f'{tile(finals[0], 270, 176, override=wake)}{tile(finals[1], 270, 176)}</div></div>')
    left = f'<div style="display: flex; flex-direction: column">{spotlight(spot, 560, 548)}{finals_rail}</div>'
    body = f'{header}<div style="display: flex; gap: 32px; margin-top: 22px">{left}{right}</div>'
    win = glass(80, 56, 1680, 940, body, pad="30px 36px")

    filters = "".join(
        f'<div style="display: flex; align-items: center; gap: 8px; height: 60px; padding: 0 22px; border-radius: 30px; background: {"rgba(255,255,255,0.9)" if i == 0 else "transparent"}; '
        f'color: {"#141619" if i == 0 else INK}; font-family: {SANS}; font-size: 17px; font-weight: 600">{e(lbl)}</div>'
        for i, lbl in enumerate(("All games", "Top 25", "Conference", "Close games", "My teams")))
    ornament = (f'<div style="position: absolute; left: 50%; top: 1030px; transform: translateX(-50%); display: flex; gap: 4px; padding: 8px; '
                f'border-radius: 38px; background: rgba(46,48,52,0.7); border: 1px solid rgba(255,255,255,0.16); box-shadow: 0 20px 50px rgba(0,0,0,0.35)">{filters}</div>')
    return doc(room("dark", W, H, win + ornament))


def find_redzone() -> dict:
    """A red-zone tile needs a game that was in the red zone at the moment
    drawn, so walk back through the recorded boards until one was."""
    for path in reversed(sorted(glob.glob(str(CAP / "scoreboard/*.json.gz")))):
        if pathlib.Path(path).name[:16] > AT[:16]:
            continue
        board = games(gz(path))
        hits = [x for x in board.values() if x["state"] == "in" and x["redzone"] and x["id"] != SPOT]
        if hits:
            return sorted(hits, key=lambda x: (x["away"]["rank"] or 99) + (x["home"]["rank"] or 99))[0]
    raise SystemExit("no red-zone game in the capture")

def tile_states() -> str:
    W, H = 1840, 1260
    b, early = BOARD, EARLY
    wake = b["401858224"]
    # Wake Forest's second-overtime possession starts at the 25 after Purdue's
    # failed two-point try left it 36-30; the scores are the capture's own.
    s = WAKE["scoringPlays"]
    pur_td = next(p for p in s if p["period"]["number"] == 6 and p["team"]["abbreviation"] == "PUR")
    wake_ot = {"state": "in", "detail": "2OT", "ot": "2OT", "offense": "WAKE", "down": "1st & 10 at PUR 25",
               "ytg": 25, "redzone": False,
               "away": {**wake["away"], "score": str(pur_td["awayScore"])},
               "home": {**wake["home"], "score": str(pur_td["homeScore"])}}
    states = [
        ("Pre", "Kickoff time, TV, records, venue", tile(b["401856670"])),
        ("Live", "Clock, possession, down & distance, field", tile(b["401856681"])),
        ("Red zone", "Red border + glyph + tinted last 20", tile(find_redzone())),
        ("Overtime", "Period badge, possession from the 25", tile(wake, override=wake_ot)),
        ("Delayed", "Dimmed, no field, hourglass", tile(early["401858219"])),
        ("Final", "Winner full ink + marker, loser dimmed", tile(b["401856674"])),
        ("Upset", "Unranked beats ranked: gold + bolt", tile(b["401856782"])),
    ]

    def band(kind: str, y: int, label: str) -> str:
        cells = "".join(
            f'<div style="display: flex; flex-direction: column; gap: 10px">{t}'
            f'<div style="display: flex; flex-direction: column; gap: 2px; font-family: {SANS}"><span style="font-size: 15px; font-weight: 700; color: {INK if kind == "dark" else "#17191C"}">{e(n)}</span>'
            f'<span style="font-size: 13px; color: {INK2 if kind == "dark" else "rgba(23,25,28,0.74)"}">{e(d)}</span></div></div>'
            for n, d, t in states)
        ink = INK if kind == "dark" else "#17191C"
        inner = (f'<div style="position: absolute; left: 60px; top: 40px; font-family: {SERIF}; font-style: italic; font-size: 34px; color: {ink}">{e(label)}</div>'
                 f'<div style="position: absolute; left: 60px; top: 100px; display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); column-gap: 40px; row-gap: 34px; width: 1368px">{cells}</div>')
        return f'<div style="position: absolute; left: 0; top: {y}px">{room(kind, W, 630, inner)}</div>'

    body = band("dark", 0, "Game tile · dark room (#1a1c20)") + band("bright", 630, "Game tile · bright room (#d8dad4)")
    return doc(f'<div style="position: relative; width: {W}px; height: {H}px">{body}</div>')


# ── the volume: a small perspective renderer, so arcs genuinely rise off the turf ──

S = 0.80 / 120                                # metres per yard: 120 yd field in 0.80 m
FW = 53.33 * S


def v_sub(a, b): return (a[0] - b[0], a[1] - b[1], a[2] - b[2])
def v_dot(a, b): return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
def v_cross(a, b): return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])
def v_norm(a):
    n = math.sqrt(v_dot(a, a))
    return (a[0] / n, a[1] / n, a[2] / n)


class Cam:
    def __init__(self, w, h, eye=(0.0, 0.80, 1.42), target=(0.0, 0.10, -0.02), f=1.62):
        self.cx, self.cy, self.f = w / 2, h * 0.50, f * w
        self.eye = eye
        self.fwd = v_norm(v_sub(target, eye))
        self.right = v_norm(v_cross(self.fwd, (0, 1, 0)))
        self.up = v_cross(self.right, self.fwd)

    def p(self, x, y, z):
        d = v_sub((x, y, z), self.eye)
        zz = v_dot(d, self.fwd)
        return (self.cx + self.f * v_dot(d, self.right) / zz, self.cy - self.f * v_dot(d, self.up) / zz)


def X(yd): return (yd - 50) * S


def poly(cam, pts, fill="none", stroke="none", sw=1.0, extra=""):
    d = " ".join(f"{x:.1f},{y:.1f}" for x, y in (cam.p(*q) for q in pts))
    return f'<polygon points="{d}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}" {extra}></polygon>'


def path3(cam, pts, stroke, sw, extra=""):
    d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in (cam.p(*q) for q in pts))
    return f'<path d="{d}" fill="none" stroke="{stroke}" stroke-width="{sw}" stroke-linecap="round" stroke-linejoin="round" {extra}></path>'


def plane_text(cam, x, z, text, size_yd, fill, ux=(1, 0), weight=800, family=DISPLAY):
    """Text lying on the turf: an affine from the plane's local Jacobian."""
    o = cam.p(x, 0.0005, z)
    ax = cam.p(x + ux[0] * S, 0.0005, z + ux[1] * S)
    az = cam.p(x - ux[1] * S, 0.0005, z + ux[0] * S)
    a, b_ = ax[0] - o[0], ax[1] - o[1]
    c, d = az[0] - o[0], az[1] - o[1]
    return (f'<text transform="matrix({a:.3f},{b_:.3f},{c:.3f},{d:.3f},{o[0]:.1f},{o[1]:.1f})" font-family="{family}" '
            f'font-weight="{weight}" font-size="{size_yd}" fill="{fill}" text-anchor="middle" dominant-baseline="central">{e(text)}</text>')


def drive_plays(drive: dict) -> list[dict]:
    out = []
    for p in drive.get("plays", []):
        kind = p["type"]["text"]
        if kind in ("End Period", "Timeout", "Kickoff") or "start" not in p:
            continue
        a, b_ = p["start"].get("yardLine"), p["end"].get("yardLine")
        if a is None or b_ is None:
            continue
        yds = p.get("statYardage") or 0
        if "Incompletion" in kind:
            m = re.search(r"thrown to (?:([A-Z]+)(\d+)|(\d+))", p["text"])
            tgt = int(m.group(2) or m.group(3)) if m else a - 8
            b_ = tgt if tgt < a else a - 8
        out.append({"from": 100 - a, "to": 100 - b_, "kind": kind, "yds": yds, "text": p["text"],
                    "down": p["start"].get("downDistanceText") or ""})
    return out


def field_svg(w, h, off, de, plays, scrimmage=None, first=None, wp=None, moment="", cam=None, labels=True, tee=None):
    cam = cam or Cam(w, h)
    parts = []
    # volume bounds, the way visionOS draws a volume's edges while you look at it
    bx, by0, by1, bz = 0.45, -0.03, 0.37, 0.30
    for sx in (-1, 1):
        for sy, yy in ((1, by0), (-1, by1)):
            for sz in (-1, 1):
                x, z = sx * bx, sz * bz
                parts.append(path3(cam, [(x - sx * 0.05, yy, z), (x, yy, z), (x, yy, z - sz * 0.05)], "rgba(255,255,255,0.28)", 2))
                parts.append(path3(cam, [(x, yy, z), (x, yy + sy * 0.05, z)], "rgba(255,255,255,0.28)", 2))
    # baseplate glow and slab
    parts.append(poly(cam, [(-0.43, -0.018, -0.24), (0.43, -0.018, -0.24), (0.43, -0.018, 0.24), (-0.43, -0.018, 0.24)], "rgba(255,244,214,0.07)", "rgba(255,244,214,0.18)", 1.2))
    t = 0.012
    L0, L1, zf, zb = X(-10), X(110), FW / 2, -FW / 2
    parts.append(poly(cam, [(L0, 0, zf), (L1, 0, zf), (L1, -t, zf), (L0, -t, zf)], "#07200F"))
    parts.append(poly(cam, [(L1, 0, zb), (L1, 0, zf), (L1, -t, zf), (L1, -t, zb)], "#0A2814"))
    # win probability ribbon, a glass panel behind the far sideline
    if wp:
        zr, y0, y1 = zb - 0.045, 0.02, 0.15
        parts.append(poly(cam, [(X(-10), y0, zr), (X(110), y0, zr), (X(110), y1, zr), (X(-10), y1, zr)], "rgba(20,22,26,0.72)", "rgba(255,255,255,0.2)", 1.2))
        parts.append(path3(cam, [(X(-10), (y0 + y1) / 2, zr), (X(110), (y0 + y1) / 2, zr)], "rgba(255,255,255,0.3)", 1.2, 'stroke-dasharray="5 6"'))
        n = len(wp)
        pts = [(X(-10) + (X(110) - X(-10)) * i / max(1, n - 1), y0 + 0.01 + (y1 - y0 - 0.02) * (1 - q), zr) for i, q in enumerate(wp)]
        parts.append(path3(cam, pts, INK, 3))
        ex, ey = cam.p(*pts[-1])
        parts.append(f'<circle cx="{ex:.1f}" cy="{ey:.1f}" r="5" fill="{INK}"></circle>')
        if labels:
            lx, ly = cam.p(X(110), y1, zr)
            parts.append(f'<text x="{lx + 14:.1f}" y="{ly + 14:.1f}" font-family="{SANS}" font-weight="700" font-size="17" fill="{INK}">{e(off["abbr"])} {(1 - wp[-1]) * 100:.0f}%</text>')
            parts.append(f'<text x="{lx + 14:.1f}" y="{ly + 34:.1f}" font-family="{SANS}" font-size="13" fill="{INK2}">win probability</text>')
    # turf
    for i in range(20):
        a, b_ = X(i * 5), X(i * 5 + 5)
        parts.append(poly(cam, [(a, 0, zb), (b_, 0, zb), (b_, 0, zf), (a, 0, zf)], TURF_A if i % 2 else TURF_B))
    left_team, right_team = off, de
    parts.append(poly(cam, [(X(-10), 0, zb), (X(0), 0, zb), (X(0), 0, zf), (X(-10), 0, zf)], left_team["fill"]))
    parts.append(poly(cam, [(X(100), 0, zb), (X(110), 0, zb), (X(110), 0, zf), (X(100), 0, zf)], right_team["fill"]))
    parts.append(plane_text(cam, X(-5), 0, left_team["name"].upper(), 6.2, "rgba(255,255,255,0.92)", ux=(0, -1)))
    parts.append(plane_text(cam, X(105), 0, right_team["name"].upper(), 6.2, "rgba(255,255,255,0.92)", ux=(0, 1)))
    if scrimmage and scrimmage >= 80 and not tee:
        parts.append(poly(cam, [(X(80), 0.0003, zb), (X(100), 0.0003, zb), (X(100), 0.0003, zf), (X(80), 0.0003, zf)], "rgba(223,11,11,0.28)"))
    for yd in range(0, 101, 5):
        parts.append(path3(cam, [(X(yd), 0.0004, zb), (X(yd), 0.0004, zf)], "rgba(255,255,255,%s)" % (0.85 if yd in (0, 100) else 0.5 if yd % 10 == 0 else 0.28), 1.6 if yd % 10 == 0 else 1))
    hz = FW / 2 - 20 * S                           # college hashes: 60 ft in from each sideline
    for yd in range(1, 100):
        for zz in (hz, -hz):
            parts.append(path3(cam, [(X(yd), 0.0004, zz - 0.35 * S), (X(yd), 0.0004, zz + 0.35 * S)], "rgba(255,255,255,0.35)", 0.8))
    for yd in range(10, 100, 10):
        num = str(yd if yd <= 50 else 100 - yd)
        parts.append(plane_text(cam, X(yd), FW / 2 - 9 * S, num, 3.4, "rgba(255,255,255,0.55)", weight=700))
    if scrimmage is not None:
        parts.append(path3(cam, [(X(scrimmage), 0.0006, zb), (X(scrimmage), 0.0006, zf)], BLUE, 3))
    if first is not None:
        parts.append(path3(cam, [(X(first), 0.0006, zb), (X(first), 0.0006, zf)], GOLD, 3))
    # drive arcs: run low and solid, pass high and dashed, loss red, score gold
    n = len(plays)
    for i, pl in enumerate(plays):
        z = -FW * 0.16 + FW * 0.32 * (i / max(1, n - 1))
        a, b_ = X(pl["from"]), X(pl["to"])
        k = pl["kind"]
        dist = abs(pl["to"] - pl["from"])
        passing = "Pass" in k
        apex = (0.030 + 0.0012 * dist) if passing else (0.008 + 0.0006 * dist)
        col = GOLD if "Touchdown" in k else RED if pl["yds"] < 0 else INK if passing else "#9FD8FF"
        pts = [(a + (b_ - a) * s, 0.002 + apex * 4 * s * (1 - s), z) for s in (j / 28 for j in range(29))]
        last = i == n - 1
        if last:
            parts.append(path3(cam, pts, col, 12, 'opacity="0.22"'))
        dash = 'stroke-dasharray="7 6"' if "Incompletion" in k else 'stroke-dasharray="1 0"'
        parts.append(path3(cam, pts, col, 4 if last else 3, dash))
        sx, sy = cam.p(a, 0.001, z)
        parts.append(f'<circle cx="{sx:.1f}" cy="{sy:.1f}" r="3.5" fill="{col}" opacity="0.8"></circle>')
        exx, eyy = cam.p(b_, 0.001, z)
        if "Incompletion" in k:
            parts.append(f'<path d="M{exx - 6:.1f},{eyy - 6:.1f} L{exx + 6:.1f},{eyy + 6:.1f} M{exx + 6:.1f},{eyy - 6:.1f} L{exx - 6:.1f},{eyy + 6:.1f}" stroke="{INK}" stroke-width="2.5" stroke-linecap="round"></path>')
        if labels:
            ax_, ay_ = cam.p((a + b_) / 2, 0.002 + apex, z)
            parts.append(f'<circle cx="{ax_:.1f}" cy="{ay_ - 14:.1f}" r="11" fill="rgba(18,20,23,0.9)" stroke="{col}" stroke-width="1.5"></circle>'
                         f'<text x="{ax_:.1f}" y="{ay_ - 13.5:.1f}" font-family="{SANS}" font-weight="700" font-size="12" fill="{INK}" text-anchor="middle" dominant-baseline="central">{i + 1}</text>')
    if tee is not None:
        tx, ty = cam.p(X(tee), 0.004, 0)
        parts.append(f'<ellipse cx="{tx:.1f}" cy="{ty:.1f}" rx="9" ry="6" fill="#7A3E17" stroke="{INK}" stroke-width="1.5"></ellipse>')
    elif scrimmage is not None:
        bx_, by_ = cam.p(X(scrimmage), 0.004, 0)
        parts.append(f'<ellipse cx="{bx_:.1f}" cy="{by_:.1f}" rx="10" ry="6.5" fill="#7A3E17" stroke="{INK}" stroke-width="1.5"></ellipse>')
    return f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" style="display: block">{"".join(parts)}</svg>'


def scorebug(away, home, clock, situation, flag=None, fs=1.0):
    def side(t):
        return (f'<div style="display: flex; align-items: center; gap: 10px">{team_chip(t, int(64 * fs), int(32 * fs), int(19 * fs))}'
                f'<span style="font-family: {DISPLAY}; font-weight: 900; font-size: {int(40 * fs)}px; line-height: 1; color: {INK}">{e(t["score"])}</span></div>')
    fl = badge(*flag, fs=int(12 * fs)) if flag else ""
    return (f'<div style="display: flex; align-items: center; gap: {int(22 * fs)}px; padding: {int(12 * fs)}px {int(22 * fs)}px; border-radius: {int(26 * fs)}px; '
            f'background: rgba(18,20,23,0.9); border: 1px solid rgba(255,255,255,0.16); box-shadow: 0 16px 40px rgba(0,0,0,0.45)">'
            f'{side(away)}<div style="display: flex; flex-direction: column; align-items: center; gap: 3px; font-family: {SANS}">'
            f'<span style="font-size: {int(15 * fs)}px; font-weight: 700; color: {INK}">{e(clock)}</span>'
            f'<span style="font-size: {max(12, int(13 * fs))}px; color: {INK2}; white-space: nowrap">{e(situation)}</span></div>{side(home)}{fl}</div>')


def volume() -> str:
    W = 1840
    gm = spot_game()
    osu, tex = gm["away"], gm["home"]
    cur = SUM["drives"]["current"]
    plays = drive_plays(cur)
    ytg, down = gm["ytg"], gm["down"]
    scrim = 100 - ytg
    m = re.search(r"& (\d+)", down or "")
    first = scrim + int(m.group(1)) if m else None
    wp_home = [q["homeWinPercentage"] for q in SUM.get("winprobability", [])]
    st = summary_state(SUM)
    osu_s = {**osu, "score": st["sides"]["away"]["score"]}
    tex_s = {**tex, "score": st["sides"]["home"]["score"]}

    hero = field_svg(1180, 760, osu, tex, plays, scrim, first, wp_home)
    bug = scorebug(osu_s, tex_s, st["detail"].replace(" - ", " · "), down, ("Red zone", RED_FILL, "redzone"))

    # the drive scrubber ornament
    drives = SUM["drives"]["previous"]
    pills = []
    for i, d in enumerate(drives):
        is_cur = d.get("id") == cur.get("id")
        team = osu if d["team"]["abbreviation"] == "OSU" else tex
        res = d.get("displayResult") or "In progress"
        pills.append(f'<div style="display: flex; align-items: center; gap: 8px; height: 60px; padding: 0 16px 0 10px; border-radius: 30px; '
                     f'background: {"rgba(255,255,255,0.92)" if is_cur else "rgba(255,255,255,0.08)"}; color: {"#141619" if is_cur else INK}; font-family: {SANS}; font-size: 15px; font-weight: 600">'
                     f'<div style="width: 12px; height: 26px; background: {team["fill"]}; clip-path: polygon(0 0, 100% 0, 70% 100%, 0 100%)"></div>'
                     f'<span>{e(team["abbr"])}</span><span style="font-weight: 500; opacity: 0.8; white-space: nowrap">{e(res)}</span></div>')
    scrub = (f'<div style="display: flex; align-items: center; gap: 6px; padding: 8px; border-radius: 38px; background: rgba(46,48,52,0.72); '
             f'border: 1px solid rgba(255,255,255,0.16)">{"".join(pills)}</div>')

    # arc grammar legend, with the current drive's plays written out
    def legend_row(col, dash, label):
        return (f'<div style="display: flex; align-items: center; gap: 12px; font-family: {SANS}; font-size: 14px; color: {INK}">'
                f'<svg width="54" height="22"><path d="M3,19 Q27,{2 if "Pass" in label else 12} 51,19" fill="none" stroke="{col}" stroke-width="3" stroke-linecap="round" stroke-dasharray="{dash}"></path></svg><span>{e(label)}</span></div>')
    legend = "".join((legend_row("#9FD8FF", "1 0", "Run — low, solid"), legend_row(INK, "1 0", "Pass complete — high, solid"),
                      legend_row(INK, "7 6", "Pass incomplete — dashed, ends in ×"), legend_row(RED, "1 0", "Loss of yards"),
                      legend_row(GOLD, "1 0", "Scoring play")))
    rows = []
    for i, p in enumerate(plays):
        txt = re.sub(r"^\(\d+:\d+\)\s*(Shotgun\s*)?", "", p["text"])
        txt = re.sub(r"#\d+ ", "", txt).split(" (")[0].split(", End Of")[0]
        rows.append(f'<div style="display: flex; gap: 12px; font-family: {SANS}; font-size: 14px; line-height: 1.3; color: {INK if i == len(plays) - 1 else INK2}">'
                    f'<span style="width: 22px; height: 22px; flex-shrink: 0; border-radius: 11px; border: 1.5px solid {INK3}; display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 700; color: {INK}">{i + 1}</span>'
                    f'<span><span style="font-weight: 600; color: {INK}">{e(p["down"])}</span> · {e(txt)}</span></div>')
    side_panel = (f'<div style="display: flex; flex-direction: column; gap: 16px; width: 520px; padding: 28px; box-sizing: border-box; border-radius: 30px; background: {PLATE}; border: 1px solid rgba(255,255,255,0.12)">'
                  f'{section(cur.get("description", ""), "This drive", 28)}<div style="display: flex; flex-direction: column; gap: 10px">{"".join(rows)}</div>'
                  f'<div style="height: 1px; background: rgba(255,255,255,0.12)"></div>{section("How a play is drawn", "Arc grammar", 24)}'
                  f'<div style="display: flex; flex-direction: column; gap: 8px">{legend}</div>'
                  f'<div style="font-family: {SANS}; font-size: 13px; color: {INK2}; line-height: 1.4">Blue line: scrimmage. Gold line: line to gain. Arcs are staggered across the field only so they don’t overlap. ESPN doesn’t report where across the field a play went.</div></div>')

    # two more moments, same renderer
    td = next(d for d in drives if d.get("displayResult") == "Touchdown")
    td_plays = drive_plays(td)
    wp_ids = {q["playId"]: i for i, q in enumerate(SUM["winprobability"])}
    last_id = td["plays"][-1]["id"]
    td_wp = wp_home[: (wp_ids.get(last_id, len(wp_home) // 2)) + 1]
    thumbs_cam = Cam(540, 360, eye=(0.0, 0.82, 1.42), f=1.5)
    kick = field_svg(540, 360, osu, tex, [], None, None, wp_home[:1], cam=thumbs_cam, labels=False, tee=35)
    score = field_svg(540, 360, osu, tex, td_plays, 100, None, td_wp, cam=Cam(540, 360, eye=(0.0, 0.82, 1.42), f=1.5), labels=False)
    first_sc = SUM["scoringPlays"]

    def moment(svg, title, bugs):
        return (f'<div style="position: relative; width: 540px; height: 430px; border-radius: 30px; overflow: hidden; background: rgba(0,0,0,0.18); border: 1px solid rgba(255,255,255,0.1)">'
                f'<div style="position: absolute; left: 0; top: 50px">{svg}</div>'
                f'<div style="position: absolute; left: 24px; top: 20px">{section("", title, 24)}</div>'
                f'<div style="position: absolute; left: 50%; bottom: 20px; transform: translateX(-50%)">{bugs}</div></div>')
    k_bug = scorebug({**osu, "score": "0"}, {**tex, "score": "0"}, "1st · 15:00", "Opening kickoff", None, 0.72)
    td_osu = next(p for p in first_sc if "TD" in p["text"])
    s_bug = scorebug({**osu, "score": str(td_osu["awayScore"])}, {**tex, "score": str(td_osu["homeScore"])},
                     f'1st · {td_osu["clock"]["displayValue"]}', "J. Jackson 8 yd run", ("Touchdown", GOLD_FILL, "flag"), 0.72)
    hero_block = (f'<div style="position: relative; width: 1180px; height: 900px">'
                  f'<div style="position: absolute; left: 0; top: 40px">{hero}</div>'
                  f'<div style="position: absolute; left: 50%; top: 40px; transform: translateX(-50%)">{bug}</div>'
                  f'<div style="position: absolute; left: 50%; top: 800px; transform: translateX(-50%)">{scrub}</div></div>')
    top = (f'<div style="position: absolute; left: 60px; top: 40px; display: flex; flex-direction: column; gap: 6px">'
           f'<span style="font-family: {DISPLAY}; font-weight: 900; font-size: 44px; text-transform: uppercase; color: {INK}; line-height: 1">Game Volume</span>'
           f'<span style="font-family: {SERIF}; font-style: italic; font-size: 22px; color: {INK2}">Ohio State at Texas · mid-drive in the red zone · from the recorded capture</span></div>')
    inner = (top + f'<div style="position: absolute; left: 40px; top: 120px">{hero_block}</div>'
             f'<div style="position: absolute; left: 1240px; top: 140px">{side_panel}</div>')
    upper = room("dark", W, 1060, inner)
    # moments need 430 tall; the lower band is laid out as a row of three with the elevation
    lower = room("dark", W, 520,
                 f'<div style="position: absolute; left: 60px; top: 20px; display: flex; gap: 40px">'
                 f'{moment(kick, "Kickoff", k_bug)}{moment(score, "Scoring play", s_bug)}{elevation()}</div>')
    return doc(f'<div style="position: relative; width: {W}px; height: 1580px">{upper}<div style="position: absolute; left: 0; top: 1060px">{lower}</div></div>')


def elevation() -> str:
    """Side view, to scale: 1 m = 600 px."""
    k = 520
    w, h = 540, 400
    ox, oy = 18, 300                                  # volume's front-bottom-left in px
    def P(x, y): return (ox + x * k, oy - y * k)
    parts = []
    x0, y0 = P(0, 0); x1, y1 = P(0.9, 0.40)
    parts.append(f'<rect x="{x0}" y="{y1}" width="{x1 - x0}" height="{y0 - y1}" fill="none" stroke="rgba(255,255,255,0.35)" stroke-width="1.5" stroke-dasharray="6 6"></rect>')
    fx0, fy = P(0.05, 0.012); fx1, _ = P(0.85, 0)
    parts.append(f'<rect x="{fx0}" y="{fy}" width="{fx1 - fx0}" height="{0.012 * k}" fill="{TURF_B}" stroke="rgba(255,255,255,0.4)"></rect>')
    # a 10-yard completion: apex 30 mm + 1.2 mm/yd
    a = 0.030 + 0.0012 * 10
    sx, _ = P(0.45, 0); ex, _ = P(0.45 + 10 * S, 0)
    _, ay = P(0, 0.014 + a)
    parts.append(f'<path d="M{sx},{fy} Q{(sx + ex) / 2},{2 * ay - fy} {ex},{fy}" fill="none" stroke="{INK}" stroke-width="2.5"></path>')
    rx, ry0 = P(0.02, 0.02); rx1, ry1 = P(0.88, 0.15)
    parts.append(f'<rect x="{rx}" y="{ry1}" width="{rx1 - rx}" height="{ry0 - ry1}" fill="rgba(255,255,255,0.06)" stroke="rgba(255,255,255,0.3)"></rect>')
    bx0, by0 = P(0.30, 0.24); bx1, by1 = P(0.60, 0.30)
    parts.append(f'<rect x="{bx0}" y="{by1}" width="{bx1 - bx0}" height="{by0 - by1}" rx="8" fill="rgba(18,20,23,0.9)" stroke="rgba(255,255,255,0.4)"></rect>')
    ox0, oy0 = P(0.22, -0.07); ox1, oy1 = P(0.68, -0.03)
    parts.append(f'<rect x="{ox0}" y="{oy1}" width="{ox1 - ox0}" height="{oy0 - oy1}" rx="12" fill="rgba(255,255,255,0.1)" stroke="rgba(255,255,255,0.4)"></rect>')
    def label(x, y, t, anchor="start", col=INK2):
        return f'<text x="{x}" y="{y}" font-family="{SANS}" font-size="13" fill="{col}" text-anchor="{anchor}">{e(t)}</text>'
    parts += [label((x0 + x1) / 2, y1 - 10, "volume 0.90 × 0.40 × 0.60 m", "middle", INK),
              label((bx0 + bx1) / 2, by1 - 8, "scorebug · 0.24–0.30 m", "middle"),
              label(rx + 8, ry1 + 18, "win-probability ribbon · 0.02–0.15 m, 45 mm behind"),
              label((fx0 + fx1) / 2, fy + 30, "field 0.80 m = 120 yd · 6.7 mm/yd · slab 12 mm", "middle"),
              label(ex + 10, ay - 14, "pass apex 30 mm + 1.2 mm/yd"), label(ex + 10, ay + 2, "run apex 8 mm + 0.6 mm/yd"),
              label((ox0 + ox1) / 2, oy0 + 20, "drive scrubber ornament · 30 mm below the base", "middle")]
    return (f'<div style="width: {w + 20}px; height: 430px; border-radius: 30px; background: rgba(0,0,0,0.18); border: 1px solid rgba(255,255,255,0.1); position: relative">'
            f'<div style="position: absolute; left: 24px; top: 20px">{section("to scale", "Side elevation", 24)}</div>'
            f'<svg width="{w + 20}" height="{h}" style="position: absolute; left: 0; top: 30px">{"".join(parts)}</svg></div>')


def detail() -> str:
    W, H = 1440, 1060
    gm = BOARD[SPOT]
    osu, tex = gm["away"], gm["home"]
    st = summary_state(SUM)
    sides = st["sides"]
    teams = {"OSU": osu, "TEX": tex}

    def lines(c):
        return [l.get("displayValue", "0") for l in c.get("linescores", [])]
    per = max(len(lines(sides["away"])), len(lines(sides["home"])))

    def score_side(t, c, align):
        rank = f'<span style="font-family: {DISPLAY}; font-weight: 700; font-size: 20px; color: {INK2}">#{t["rank"]}</span>' if t["rank"] else ""
        inner = (f'{team_chip(t, 84, 40, 23)}<div style="display: flex; flex-direction: column"><div style="display: flex; gap: 6px; align-items: baseline">{rank}'
                 f'<span style="font-family: {SANS}; font-size: 19px; font-weight: 600; color: {INK}">{e(t["name"])}</span></div>'
                 f'<span style="font-family: {SANS}; font-size: 13px; color: {INK2}">{e(t["record"])} · quarters {" · ".join(lines(c))}</span></div>'
                 f'<span style="font-family: {DISPLAY}; font-weight: 900; font-size: 64px; line-height: 1; color: {INK}">{e(c["score"])}</span>')
        return f'<div style="display: flex; align-items: center; gap: 14px; flex-direction: {"row" if align == "l" else "row-reverse"}">{inner}</div>'
    info = SUM.get("gameInfo") or {}
    weather = info.get("weather") or {}
    odds = (SUM.get("pickcenter") or [{}])[0]
    meta = " · ".join(x for x in (gm["venue"], f'{weather.get("temperature")}°' if weather.get("temperature") else "", gm["tv"],
                                   f'{odds.get("details")} (DraftKings)' if odds.get("details") else "") if x)
    header = (f'<div style="display: flex; align-items: center; justify-content: space-between">{score_side(osu, sides["away"], "l")}'
              f'<div style="display: flex; flex-direction: column; align-items: center; gap: 6px">'
              f'<span style="font-family: {DISPLAY}; font-weight: 800; font-size: 30px; color: {INK}">{e(st["detail"].replace(" - ", " · "))}</span>'
              f'{badge("Red zone", RED_FILL, "redzone", 13)}</div>{score_side(tex, sides["home"], "r")}</div>'
              f'<div style="display: flex; align-items: center; justify-content: space-between; margin-top: 14px">'
              f'<span style="font-family: {SANS}; font-size: 14px; color: {INK2}">{e(meta)}</span>'
              f'<div style="display: flex; gap: 12px">{button("View in 3D", "cube", True)}{button("Enter stadium", "stadium")}</div></div>')

    # drives
    cur = SUM["drives"]["current"]
    drows = []
    for d in SUM["drives"]["previous"]:
        t = teams.get(d["team"]["abbreviation"], osu)
        res = d.get("displayResult") or "In progress"
        is_cur = d.get("id") == cur.get("id")
        glyph = "flag" if res in ("Touchdown", "Field Goal") else "turnover" if res in ("Fumble", "Interception") else "ball" if is_cur else "final"
        drows.append(f'<div style="display: flex; align-items: center; gap: 12px; min-height: 60px; padding: 0 14px; border-radius: 16px; background: {"rgba(255,255,255,0.10)" if is_cur else "transparent"}">'
                     f'{team_chip(t, 52, 24, 15)}<div style="display: flex; flex-direction: column; flex-grow: 1">'
                     f'<span style="font-family: {SANS}; font-size: 15px; font-weight: 600; color: {INK}">{e(res)}</span>'
                     f'<span style="font-family: {SANS}; font-size: 13px; color: {INK2}">{e(d.get("description", ""))}</span></div>'
                     f'<span style="color: {INK}; display: flex">{g(glyph, 20)}</span></div>')
        if is_cur:
            for p in [x for x in cur["plays"] if x["type"]["text"] not in ("End Period", "Timeout")][-4:]:
                txt = re.sub(r"^\(\d+:\d+\)\s*(Shotgun\s*)?", "", p["text"])
                txt = re.sub(r"#\d+ ", "", txt).split(" (")[0].split(", End Of")[0]
                drows.append(f'<div style="display: flex; gap: 10px; padding: 4px 14px 4px 80px; font-family: {SANS}; font-size: 13px; line-height: 1.35; color: {INK2}">'
                             f'<span style="color: {INK}; font-weight: 600; white-space: nowrap">{e(p["start"].get("downDistanceText") or "")}</span><span>{e(txt)}</span></div>')
    drives_col = (f'<div style="display: flex; flex-direction: column; gap: 6px; width: 470px; flex-shrink: 0">{section(f"{len(SUM["drives"]["previous"])} so far", "Drives")}'
                  f'<div style="display: flex; flex-direction: column; gap: 2px; margin-top: 8px">{"".join(drows)}</div></div>')

    # win probability chart: above the line favours the away side
    wp = SUM["winprobability"]
    cw, ch = 400, 250
    pts = [(i / max(1, len(wp) - 1) * cw, (q["homeWinPercentage"]) * ch) for i, q in enumerate(wp)]
    line = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area_top = f'M0,{ch / 2} L' + " L".join(f"{x:.1f},{min(y, ch / 2):.1f}" for x, y in pts) + f" L{cw},{ch / 2} Z"
    area_bot = f'M0,{ch / 2} L' + " L".join(f"{x:.1f},{max(y, ch / 2):.1f}" for x, y in pts) + f" L{cw},{ch / 2} Z"
    ids = {q["playId"]: i for i, q in enumerate(wp)}
    marks = []
    for d in SUM["drives"]["previous"]:
        res = d.get("displayResult")
        if res in ("Touchdown", "Field Goal", "Fumble", "Interception") and d.get("plays"):
            i = ids.get(d["plays"][-1]["id"])
            if i is None:
                i = max((ids[p["id"]] for p in d["plays"] if p["id"] in ids), default=None)
            if i is None:
                continue
            x, y = pts[i]
            lab = {"Touchdown": "TD", "Field Goal": "FG", "Fumble": "FUM", "Interception": "INT"}[res]
            ly = y + 22 if res in ("Fumble", "Interception") else y - 12
            marks.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{INK}"></circle>'
                         f'<text x="{x:.1f}" y="{ly:.1f}" font-family="{SANS}" font-size="12" font-weight="700" fill="{INK}" text-anchor="middle">{lab}</text>')
    chart = (f'<svg width="{cw + 60}" height="{ch + 40}" style="display: block; overflow: visible">'
             f'<g transform="translate(40,10)"><path d="{area_top}" fill="{osu["fill"]}" opacity="0.55"></path><path d="{area_bot}" fill="{tex["fill"]}" opacity="0.55"></path>'
             f'<line x1="0" y1="{ch / 2}" x2="{cw}" y2="{ch / 2}" stroke="rgba(255,255,255,0.35)" stroke-dasharray="4 5"></line>'
             f'<path d="{line}" fill="none" stroke="{INK}" stroke-width="2.5"></path>{"".join(marks)}'
             f'<text x="-10" y="14" font-family="{SANS}" font-size="12" fill="{INK2}" text-anchor="end">OSU</text>'
             f'<text x="-10" y="{ch - 4}" font-family="{SANS}" font-size="12" fill="{INK2}" text-anchor="end">TEX</text>'
             f'<text x="0" y="{ch + 22}" font-family="{SANS}" font-size="12" fill="{INK2}">Kickoff</text>'
             f'<text x="{cw}" y="{ch + 22}" font-family="{SANS}" font-size="12" fill="{INK2}" text-anchor="end">Now · OSU {(1 - wp[-1]["homeWinPercentage"]) * 100:.0f}%</text></g></svg>')
    scoring = "".join(
        f'<div style="display: flex; align-items: center; gap: 12px; font-family: {SANS}; font-size: 14px; color: {INK}">{team_chip(teams.get(s["team"]["abbreviation"], osu), 48, 22, 14)}'
        f'<span style="color: {INK2}; width: 64px">Q{s["period"]["number"]} {e(s["clock"]["displayValue"])}</span><span>{e(s["text"])}</span></div>'
        for s in SUM.get("scoringPlays", []))
    mid = (f'<div style="display: flex; flex-direction: column; gap: 14px; width: 440px; flex-shrink: 0">{section("ESPN’s model, not ours", "Win probability")}{chart}'
           f'{section("", "Scoring")}<div style="display: flex; flex-direction: column; gap: 10px">{scoring}</div></div>')

    # box score
    stats = {t["team"]["abbreviation"]: {s["label"]: s["displayValue"] for s in t["statistics"]} for t in SUM["boxscore"]["teams"]}
    def num(v):
        try:
            return float(str(v).split("-")[0].split(":")[0]) + (float(str(v).split(":")[1]) / 60 if ":" in str(v) else 0)
        except ValueError:
            return 0.0
    rows = []
    for label in ("Total Yards", "1st Downs", "3rd down efficiency", "Turnovers", "Possession"):
        a, b_ = stats["OSU"].get(label, "0").strip(), stats["TEX"].get(label, "0").strip()
        na, nb = num(a), num(b_)
        share = na / (na + nb) if na + nb else 0.5
        rows.append(f'<div style="display: flex; flex-direction: column; gap: 5px"><div style="display: flex; justify-content: space-between; font-family: {SANS}; font-size: 14px; color: {INK}">'
                    f'<span style="font-weight: 700">{e(a)}</span><span style="color: {INK2}">{e(label)}</span><span style="font-weight: 700">{e(b_)}</span></div>'
                    f'<div style="display: flex; height: 6px; gap: 2px"><div style="width: {share * 100:.0f}%; background: {osu["fill"]}"></div><div style="flex-grow: 1; background: {tex["fill"]}"></div></div></div>')
    leaders = []
    for p in SUM["boxscore"].get("players", []):
        t = teams.get(p["team"]["abbreviation"], osu)
        for cat in p["statistics"][:3]:
            if not cat.get("athletes"):
                continue
            a = cat["athletes"][0]
            lab = dict(zip(cat["labels"], a["stats"]))
            line_ = {"passing": f'{lab.get("C/ATT")}, {lab.get("YDS")} yds', "rushing": f'{lab.get("CAR")} car, {lab.get("YDS")} yds',
                     "receiving": f'{lab.get("REC")} rec, {lab.get("YDS")} yds'}.get(cat["name"], "")
            leaders.append(f'<div style="display: flex; align-items: center; gap: 10px; font-family: {SANS}; font-size: 14px">{team_chip(t, 44, 20, 13)}'
                           f'<span style="color: {INK}; font-weight: 600; flex-grow: 1">{e(a["athlete"]["displayName"])}</span><span style="color: {INK2}; white-space: nowrap">{e(line_)}</span></div>')
    box = (f'<div style="display: flex; flex-direction: column; gap: 14px; flex-grow: 1">{section("", "Box score")}'
           f'<div style="display: flex; flex-direction: column; gap: 14px">{"".join(rows)}</div>{section("", "Leaders")}'
           f'<div style="display: flex; flex-direction: column; gap: 9px">{"".join(leaders)}</div></div>')

    body = (f'{header}<div style="height: 1px; background: rgba(255,255,255,0.14); margin: 22px 0"></div>'
            f'<div style="display: flex; gap: 34px">{drives_col}{mid}{box}</div>')
    win = glass(80, 70, 1280, 860, body, pad="30px 34px")
    tabs = "".join(f'<div style="height: 56px; padding: 0 22px; display: flex; align-items: center; border-radius: 28px; font-family: {SANS}; font-size: 16px; font-weight: 600; '
                   f'background: {"rgba(255,255,255,0.9)" if i == 0 else "transparent"}; color: {"#141619" if i == 0 else INK}">{e(t)}</div>'
                   for i, t in enumerate(("Game", "Play-by-play", "Box score", "Team stats")))
    orn = (f'<div style="position: absolute; left: 50%; top: 958px; transform: translateX(-50%); display: flex; gap: 4px; padding: 8px; border-radius: 36px; '
           f'background: rgba(46,48,52,0.78); border: 1px solid rgba(255,255,255,0.2)">{tabs}</div>')
    return doc(room("bright", W, H, win + orn))


def tokens() -> str:
    W, H = 1840, 1320
    white = (1, 1, 1)
    plate = rgb("#121417")
    dark_c = over(plate, 0.88, over(rgb("#222428"), 0.80, rgb(ROOM_DARK)))
    bright_c = over(plate, 0.88, over(rgb("#222428"), 0.80, rgb(ROOM_BRIGHT)))
    glass_b = over(rgb("#222428"), 0.80, rgb(ROOM_BRIGHT))
    ink2_dark = over(rgb(INK), 0.74, dark_c)
    ink2_bright = over(rgb(INK), 0.74, bright_c)

    def swatch(name, hexs, note, text_on=True):
        c = contrast(white, rgb(hexs)) if text_on else None
        cr = f'white {c:.1f}:1' if c else ""
        return (f'<div style="display: flex; flex-direction: column; gap: 8px; width: 170px"><div style="height: 72px; background: {hexs}; border: 1px solid rgba(255,255,255,0.14); display: flex; align-items: flex-end; padding: 8px; box-sizing: border-box; font-family: {SANS}; font-size: 13px; font-weight: 700; color: #FFFFFF">{e(cr)}</div>'
                f'<span style="font-family: {SANS}; font-size: 14px; font-weight: 700; color: {INK}">{e(name)}</span>'
                f'<span style="font-family: {SANS}; font-size: 13px; color: {INK2}">{e(hexs)} · {e(note)}</span></div>')
    colours = "".join((
        swatch("Live", GREEN_FILL, "Theme.greenFill"), swatch("Red zone", RED_FILL, "Theme.redFill"), swatch("Upset", GOLD_FILL, "Theme.goldFill"),
        swatch("Plate", "#121417", "88% on glass"), swatch("Turf A", TURF_A, "pitch"), swatch("Turf B", TURF_B, "stripe"),
        swatch("Line to gain", GOLD, "graphic only", False), swatch("Scrimmage", BLUE, "graphic only", False)))
    ratio = (f'<div style="font-family: {SANS}; font-size: 14px; color: {INK2}; line-height: 1.5">Measured through glass and plate: ink {contrast(rgb(INK), dark_c):.1f}:1 / secondary {contrast(ink2_dark, dark_c):.1f}:1 in the dark room, '
             f'ink {contrast(rgb(INK), bright_c):.1f}:1 / secondary {contrast(ink2_bright, bright_c):.1f}:1 in the bright room. Straight on window glass in the bright room: secondary {contrast(over(rgb(INK), 0.74, glass_b), glass_b):.1f}:1. Body needs 4.5:1.</div>')

    teams = {}
    for gm in BOARD.values():
        for s in ("away", "home"):
            teams[gm[s]["abbr"]] = gm[s]
    pick = ["TEX", "TENN", "OSU", "UGA", "ORE", "OKST", "MICH", "LSU", "IOWA", "WASH", "UCLA", "COLO"]
    norm_rows = "".join(
        f'<div style="display: flex; flex-direction: column; align-items: center; gap: 6px; font-family: {SANS}; font-size: 12px; color: {INK2}">'
        f'<div style="width: 104px; height: 34px; background: {teams[a]["color"]}; display: flex; align-items: center; justify-content: center; font-family: {DISPLAY}; font-weight: 800; font-size: 18px; color: #FFFFFF">{e(a)}</div>'
        f'<span>{contrast(white, rgb(teams[a]["color"])):.1f}:1 raw</span>'
        f'{team_chip({**teams[a], "fill": chip(teams[a]["color"]), "hatch": False}, 104, 34, 18)}'
        f'<span style="color: {INK}">{contrast(white, rgb(chip(teams[a]["color"]))):.1f}:1 in band</span></div>'
        for a in pick if a in teams)
    wake, pur = BOARD["401858224"]["away"], BOARD["401858224"]["home"]
    clash_demo = (f'<div style="display: flex; align-items: center; gap: 28px; font-family: {SANS}; font-size: 14px; color: {INK2}">'
                  f'<div style="display: flex; flex-direction: column; gap: 8px"><span>Raw: both {e(wake["color"])}</span><div style="display: flex; gap: 8px">'
                  f'{team_chip({**wake, "fill": wake["color"], "hatch": False}, 80, 34, 18)}{team_chip({**pur, "fill": pur["color"], "hatch": False}, 80, 34, 18)}</div></div>'
                  f'<div style="display: flex; flex-direction: column; gap: 8px"><span>In band: still identical</span><div style="display: flex; gap: 8px">'
                  f'{team_chip({**wake, "fill": chip(wake["color"]), "hatch": False}, 80, 34, 18)}{team_chip({**pur, "fill": chip(pur["color"]), "hatch": False}, 80, 34, 18)}</div></div>'
                  f'<div style="display: flex; flex-direction: column; gap: 8px"><span style="color: {INK}">Resolved: away takes a distinct alternate, else keeps its colour and gains a hatch</span><div style="display: flex; gap: 8px">'
                  f'{team_chip(wake, 80, 34, 18)}{team_chip(pur, 80, 34, 18)}</div></div></div>')

    type_rows = "".join(
        f'<div style="display: flex; align-items: baseline; gap: 24px"><span style="width: 180px; font-family: {SANS}; font-size: 13px; color: {INK2}">{e(n)}</span>'
        f'<span style="font-family: {fam}; font-weight: {wt}; font-size: {sz}px; color: {INK}; line-height: 1.1; {extra}">{e(sample)}</span></div>'
        for n, fam, wt, sz, extra, sample in (
            ("Score · Display 900 · 84", DISPLAY, 900, 84, "", "10  0"),
            ("Situation · Display 800 · 36", DISPLAY, 800, 36, "", "3rd & 6 at TEX 17"),
            ("Section · Serif italic · 30", SERIF, 400, 30, "font-style: italic", "The Big Game"),
            ("Team · Sans 600 · 22", SANS, 600, 22, "", "Ohio State"),
            ("Body · Sans 500 · 15", SANS, 500, 15, "", "Bo Jackson rush middle for 4 yards to the TEX17"),
            ("Overline · Sans 600 · 12 · +14%", SANS, 600, 12, "letter-spacing: 0.14em; text-transform: uppercase", "Ranked, close, driving")))

    glyphs = "".join(
        f'<div style="display: flex; flex-direction: column; align-items: center; gap: 10px; width: 96px; font-family: {SANS}; font-size: 13px; color: {INK2}">'
        f'<div style="display: flex; gap: 10px; align-items: center; color: {INK}">{g(k, 20)}{g(k, 32)}</div><span>{e(label)}</span></div>'
        for k, label in (("live", "Live"), ("ball", "Possession"), ("redzone", "Red zone"), ("upset", "Upset"), ("ot", "Overtime"),
                         ("delayed", "Delayed"), ("final", "Final"), ("flag", "Score"), ("turnover", "Turnover"), ("cube", "View in 3D"), ("stadium", "Stadium"), ("tv", "Broadcast")))

    motion = "".join(
        f'<div style="display: flex; flex-direction: column; gap: 8px; padding: 20px; width: 520px; box-sizing: border-box; background: {PLATE}; border-radius: 22px; border: 1px solid rgba(255,255,255,0.1)">'
        f'<span style="font-family: {SERIF}; font-style: italic; font-size: 24px; color: {INK}">{e(t)}</span>'
        f'<span style="font-family: {SANS}; font-size: 14px; color: {INK}; line-height: 1.45">{e(m)}</span>'
        f'<span style="font-family: {SANS}; font-size: 13px; color: {INK2}; line-height: 1.45"><strong style="color: {INK}">Reduce motion:</strong> {e(r)}</span></div>'
        for t, m, r in (
            ("Score change", "The old number slides up and out while the new one arrives from below: 280 ms, ease-out. The scoring side's chip flashes to full team colour and settles back to the band over 900 ms. The light bank brightens once. A touchdown in the volume lifts a gold arc with a 1.2 s ring at the goal line.",
             "Instant swap of the number, the chip holds full colour for 2 s, the gold arc appears without its ring."),
            ("Possession flip", "The ball glyph travels between team rows along a 40 px arc in 360 ms. The field bar mirrors so the new offense attacks right: a 420 ms horizontal flip with the end zones trading places.",
             "Glyph and field bar crossfade over 200 ms."),
            ("Upset reveal", "When a ranked team goes final with a loss, the tile's border draws around its perimeter in gold over 700 ms. The badge stamps in with a 1.06→1.0 scale, and the tile moves up to Tonight so far.",
             "Border and badge appear at once; the tile moves with a crossfade.")))

    inner = (f'<div style="position: absolute; left: 60px; top: 44px; display: flex; flex-direction: column; gap: 34px; width: 1720px">'
             f'<div style="display: flex; align-items: baseline; gap: 18px"><span style="font-family: {DISPLAY}; font-weight: 900; font-size: 48px; text-transform: uppercase; color: {INK}">Saturday system</span>'
             f'<span style="font-family: {SERIF}; font-style: italic; font-size: 22px; color: {INK2}">stadium lights at night · type, colour, chips, glyphs, motion</span></div>'
             f'<div style="display: flex; gap: 60px"><div style="display: flex; flex-direction: column; gap: 16px; width: 820px">{section("Big Shoulders Display · Instrument Sans · Instrument Serif", "Type")}{type_rows}</div>'
             f'<div style="display: flex; flex-direction: column; gap: 16px; flex-grow: 1">{section("fills from the headset app, measured on glass", "Colour")}'
             f'<div style="display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 18px">{colours}</div>{ratio}</div></div>'
             f'<div style="display: flex; flex-direction: column; gap: 16px">{section(f"hue kept, value solved to relative luminance {BAND}", "Team colour normalisation")}'
             f'<div style="display: flex; gap: 20px; flex-wrap: wrap">{norm_rows}</div></div>'
             f'<div style="display: flex; gap: 80px"><div style="display: flex; flex-direction: column; gap: 16px">{section("Wake Forest at Purdue, same old gold", "A real clash")}{clash_demo}</div></div>'
             f'<div style="display: flex; flex-direction: column; gap: 16px">{section("24-unit grid · 1.8 stroke · always paired with a word or chip", "Glyphs")}<div style="display: flex; gap: 22px">{glyphs}</div></div>'
             f'<div style="display: flex; flex-direction: column; gap: 16px">{section("motion is spent on scoring, nowhere else", "Motion")}<div style="display: flex; gap: 20px">{motion}</div></div></div>')
    return doc(room("dark", W, H, inner))


def sketch(title: str, motive: str, tradeoff: str, body: str) -> str:
    W, H = 1200, 800
    hand = "'Kalam', 'Comic Sans MS', cursive"
    return ('<!doctype html>\n<html>\n<head>\n  <meta charset="utf-8">\n  <script src="./support.js"></script>\n</head>\n<body>\n<x-dc>\n'
            '<helmet>\n  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Kalam:wght@400;700&amp;display=swap">\n'
            '  <style>body { margin: 0; } a { color: #B42318; } a:hover { color: #7A1A12; }</style>\n</helmet>\n'
            f'<div style="width: {W}px; height: {H}px; box-sizing: border-box; padding: 40px 48px; background: #F4F2EC; font-family: {hand}; color: #26241F; display: flex; flex-direction: column; gap: 18px">'
            f'<div style="display: flex; justify-content: space-between; align-items: baseline"><span style="font-size: 40px; font-weight: 700">{e(title)}</span><span style="font-size: 18px; color: #6B675E">low-fi alternate</span></div>'
            f'<div style="display: flex; gap: 32px; font-size: 18px; line-height: 1.35"><div style="flex: 1"><strong>Why:</strong> {e(motive)}</div><div style="flex: 1"><strong>Cost:</strong> {e(tradeoff)}</div></div>'
            f'{body}</div>\n</x-dc>\n</body>\n</html>\n')


def alt_rails() -> str:
    confs = [("SEC", ["TENN 17–10 GT", "MISS 7–0 CLT", "LSU 10–0 LT", "SC 17–3 TOW"]), ("Big Ten", ["OSU 10–0 TEX", "NEB 35–0 BGSU", "WIS 23–6 WIU", "UCLA 0–0 SDSU"]),
             ("Big 12", ["ISU 9–0 IOWA", "TTU 0–0 ORST", "BAY 0–3 PV", "TCU 7–0 GRAM"]), ("ACC", ["CLEM delayed", "—", "—", "—"]),
             ("G5", ["MRSH 14–13 MTSU", "BOIS 31–20 MEM", "FAU 14–7 NAVY", "TLSA 10–14 SHSU"])]
    cols = "".join(
        f'<div style="flex: 1; display: flex; flex-direction: column; gap: 10px"><div style="font-size: 24px; font-weight: 700; border-bottom: 3px solid #26241F">{e(c)}</div>'
        + "".join(f'<div style="border: 2px solid #26241F; border-radius: 10px; padding: 10px 12px; font-size: 19px; background: {"#FFE2DC" if j == 0 and i == 1 else "transparent"}">{e(x)}</div>' for j, x in enumerate(games_))
        + '</div>' for i, (c, games_) in enumerate(confs))
    ticker = '<div style="border: 2px dashed #26241F; border-radius: 10px; padding: 10px 14px; font-size: 19px">FINAL ticker → WAKE 38–36 PUR (2OT) · OKST 39–31 #6 ORE · MICH 17–10 #11 OU · …</div>'
    return sketch("Conference Rails", "It's how fans already follow a Saturday: by league. Each conference is a rail you scroll on its own, and you can't lose your team.",
                  "Importance stops being spatial. A great G5 finish sits in the last column, and the wall no longer says which game to watch.",
                  f'{ticker}<div style="display: flex; gap: 18px; flex-grow: 1">{cols}</div>')


def alt_field() -> str:
    live = [x for x in BOARD.values() if x["state"] == "in" and x["ytg"] is not None]
    dots = []
    lanes = {}
    for gm in sorted(live, key=lambda x: x["ytg"]):
        lane = lanes.setdefault(round((100 - gm["ytg"]) / 8), 0)
        lanes[round((100 - gm["ytg"]) / 8)] += 1
        x = 60 + 980 * (100 - gm["ytg"]) / 100
        y = 40 + lane * 44
        hot = gm["redzone"]
        dots.append(f'<div style="position: absolute; left: {x - 40:.0f}px; top: {y}px; width: 80px; height: 34px; border: 2px solid #26241F; border-radius: 17px; '
                    f'background: {"#FFE2DC" if hot else "#FFFFFF"}; display: flex; align-items: center; justify-content: center; font-size: 16px; font-weight: 700">{e(gm["offense"])}</div>')
    field = ('<div style="position: relative; flex-grow: 1; border: 3px solid #26241F; border-radius: 12px; background: repeating-linear-gradient(90deg, #E4EFDF 0 98px, #26241F 98px 100px)">'
             '<div style="position: absolute; right: 0; top: 0; bottom: 0; width: 60px; background: rgba(180,35,24,0.18); border-left: 3px solid #26241F"></div>'
             + "".join(dots) + '<div style="position: absolute; left: 20px; bottom: 12px; font-size: 18px">← own goal · every offense attacks right · red zone →</div></div>')
    return sketch("One Field", "Every live game on a single shared field, placed where its ball is. You can see at a glance which games are about to score, which is exactly the question on a Saturday.",
                  "Loses scores and clocks at a glance; tap to reveal. It's novel, so it needs a first-run explanation, and it only works for games in progress.",
                  field)


# ───────────────────────────── write ─────────────────────────────

def main() -> None:
    files = {
        "Main.dc.html": wall(), "TileStates.dc.html": tile_states(), "GameVolume.dc.html": volume(),
        "GameDetail.dc.html": detail(), "System.dc.html": tokens(),
        "ConferenceRails.dc.html": alt_rails(), "OneField.dc.html": alt_field(),
    }
    for name, src in files.items():
        (OUT / name).write_text(src)
    canvas = {
        "pages": [{"id": "page-4", "name": "Immersive"}, {"id": "page-1", "name": "Views"}, {"id": "page-2", "name": "System"}, {"id": "page-3", "name": "Alternates"}],
        "artboards": [
            {"file": "ImmersiveRoom.dc.html", "title": "Saturday Room · mixed immersion", "x": 0, "y": 0, "w": 2600, "h": 1500, "page": "page-4"},
            {"file": "ImmersiveStadium.dc.html", "title": "Stadium · full immersion", "x": 2720, "y": 0, "w": 2400, "h": 1350, "page": "page-4"},
            {"file": "ImmersiveTouchdown.dc.html", "title": "The moment · touchdown", "x": 2720, "y": 1490, "w": 2400, "h": 1350, "page": "page-4"},
            {"file": "ImmersionRamp.dc.html", "title": "Immersion ramp · Digital Crown", "x": 0, "y": 1640, "w": 2400, "h": 900, "page": "page-4"},
            {"file": "Main.dc.html", "title": "Saturday Wall · window", "x": 0, "y": 0, "w": 1840, "h": 1180, "page": "page-1"},
            {"file": "GameVolume.dc.html", "title": "Game Volume · tabletop", "x": 1960, "y": 0, "w": 1840, "h": 1580, "page": "page-1"},
            {"file": "TileStates.dc.html", "title": "Game tile · states", "x": 0, "y": 1340, "w": 1840, "h": 1260, "page": "page-1"},
            {"file": "GameDetail.dc.html", "title": "Game Detail · window", "x": 1960, "y": 1740, "w": 1440, "h": 1060, "page": "page-1"},
            {"file": "System.dc.html", "title": "System", "x": 0, "y": 0, "w": 1840, "h": 1320, "page": "page-2"},
            {"file": "ConferenceRails.dc.html", "title": "Alternate · Conference Rails", "x": 0, "y": 0, "w": 1200, "h": 800, "page": "page-3"},
            {"file": "OneField.dc.html", "title": "Alternate · One Field", "x": 1300, "y": 0, "w": 1200, "h": 800, "page": "page-3"},
        ],
        "annotations": [
            {"id": "no-players", "x": 0, "y": -170, "w": 640, "page": "page-4",
             "text": "No players on the field, on purpose: ESPN's feed has no tracking data. The stadium shows what the feed knows: the ball (a beam of light), scrimmage and line to gain (lasers on the turf), every play of the drive traced life-size in the air, and ESPN's win probability as a horizon over the far stands."},
            {"id": "scale-note", "x": 2720, "y": -170, "w": 640, "page": "page-4",
             "text": "Life-size arcs: a pass peaks at 3 yd + 0.35 yd per air yard, a run at 0.8 yd + 0.12 yd per yard gained. The tabletop uses the same stadium at 4 mm per yard. Everything is drawn in code; no stadium assets, and not a replica of any real venue."},
            {"id": "wall-order", "x": 0, "y": -150, "w": 560, "page": "page-1",
             "text": "Real slate at 7:34 PM CT, 2026-09-12. In the headset, importance is depth as well as size: the spotlight sits closest to you, close & late next, everything else furthest back."},
            {"id": "volume-note", "x": 1960, "y": -150, "w": 560, "page": "page-1",
             "text": "Drawn with a real perspective projection of the 0.9 × 0.4 × 0.6 m volume. Arcs come from ESPN's play-by-play for Ohio State's current drive."},
        ],
        "launch": {"view": "canvas", "page": "page-4"},
    }
    (OUT / "canvas.json").write_text(json.dumps(canvas, indent=2))
    print("wrote", ", ".join(files))


if __name__ == "__main__":
    main()
