"""Draw Saturday's immersive scenes: the room, the stadium, the touchdown, the ramp.

Same rule as build.py: game state comes from data/capture, never typed in. The
scenes are rendered by a small software renderer - a perspective camera for
the stadium, a cylindrical one for the 180-degree room - with painter's
ordering, so what a designer sees is where things actually sit in space.

One thing is deliberately absent: players. ESPN's feed has no tracking data,
so the stadium shows the ball, the lines and the drive, and never invents
twenty-two men to stand on them.

    python3 design/immersive.py
"""
from __future__ import annotations

import math
import random
import re

import build as B
from build import (DISPLAY, GOLD, GOLD_FILL, INK, INK2, RED, RED_FILL, SANS, SERIF, BLUE, e)

OSU_ID, TEX_ID = "OSU", "TEX"


# ───────────────────────────── cameras ─────────────────────────────

class Persp:
    """Pinhole camera. `fov` is horizontal, in degrees."""

    def __init__(self, w, h, eye, target, fov=100.0):
        self.w, self.h = w, h
        self.cx, self.cy = w / 2, h / 2
        self.f = (w / 2) / math.tan(math.radians(fov / 2))
        self.eye = eye
        self.fwd = B.v_norm(B.v_sub(target, eye))
        self.right = B.v_norm(B.v_cross(self.fwd, (0, 1, 0)))
        self.up = B.v_cross(self.right, self.fwd)

    def p(self, x, y, z):
        d = B.v_sub((x, y, z), self.eye)
        zz = B.v_dot(d, self.fwd)
        if zz < 0.05:
            return None
        return (self.cx + self.f * B.v_dot(d, self.right) / zz, self.cy - self.f * B.v_dot(d, self.up) / zz, zz)


class Cyl:
    """Cylindrical panorama around a seated viewer looking down -z.

    Yaw maps linearly to x, so a panel at 46 degrees sits exactly where the
    angle guide says it does; height maps by tangent, as the eye sees it.
    """

    def __init__(self, w, h, eye, span=160.0, horizon=0.46):
        self.w, self.h, self.eye = w, h, eye
        self.k = w / math.radians(span)
        self.cx, self.cy = w / 2, h * horizon
        self.f = self.k

    def yaw_x(self, deg):
        return self.cx + math.radians(deg) * self.k

    def p(self, x, y, z):
        dx, dy, dz = x - self.eye[0], y - self.eye[1], z - self.eye[2]
        hd = math.hypot(dx, dz)
        if hd < 0.05:
            return None
        yaw = math.atan2(dx, -dz)
        if abs(yaw) > math.radians(100):
            return None
        return (self.cx + yaw * self.k, self.cy - self.k * dy / hd, hd)


# ───────────────────────────── scene ─────────────────────────────

class Scene:
    def __init__(self, cam):
        self.cam = cam
        self.items: list[tuple[float, str]] = []

    def _pts(self, pts):
        out = [self.cam.p(*q) for q in pts]
        if any(o is None for o in out):
            return None
        if all(o[0] < -200 or o[0] > self.cam.w + 200 for o in out) or all(o[1] < -200 or o[1] > self.cam.h + 200 for o in out):
            return None
        return out

    def poly(self, pts, fill, stroke="none", sw=0, extra="", bias=0.0):
        o = self._pts(pts)
        if not o:
            return
        d = " ".join(f"{x:.1f},{y:.1f}" for x, y, _ in o)
        depth = sum(z for *_, z in o) / len(o) + bias
        self.items.append((depth, f'<polygon points="{d}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}" {extra}></polygon>'))

    def line(self, pts, stroke, sw, extra="", bias=0.0, scale=False):
        o = [self.cam.p(*q) for q in pts]
        segs, cur = [], []
        for q in o:
            if q is None:
                if len(cur) > 1:
                    segs.append(cur)
                cur = []
            else:
                cur.append(q)
        if len(cur) > 1:
            segs.append(cur)
        for s in segs:
            depth = min(z for *_, z in s) + bias
            width = sw
            if scale:
                width = max(0.6, sw * self.cam.f / (sum(z for *_, z in s) / len(s)))
            d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y, _ in s)
            self.items.append((depth, f'<path d="{d}" fill="none" stroke="{stroke}" stroke-width="{width:.2f}" stroke-linecap="round" stroke-linejoin="round" {extra}></path>'))

    def dot(self, p, r_world, fill, extra="", rmin=0.5, rmax=4.0, bias=0.0):
        o = self.cam.p(*p)
        if not o or not (-10 < o[0] < self.cam.w + 10 and -10 < o[1] < self.cam.h + 10):
            return
        r = max(rmin, min(rmax, self.cam.f * r_world / o[2]))
        self.items.append((o[2] + bias, f'<circle cx="{o[0]:.1f}" cy="{o[1]:.1f}" r="{r:.2f}" fill="{fill}" {extra}></circle>'))

    def raw(self, depth, svg):
        self.items.append((depth, svg))

    def svg(self, defs=""):
        body = "".join(s for _, s in sorted(self.items, key=lambda t: -t[0]))
        return (f'<svg width="{self.cam.w}" height="{self.cam.h}" viewBox="0 0 {self.cam.w} {self.cam.h}" style="position: absolute; left: 0; top: 0">'
                f'<defs>{defs}</defs>{body}</svg>')


DEFS = (
    '<radialGradient id="bloom"><stop offset="0" stop-color="#FFF6DD" stop-opacity="0.95"></stop><stop offset="0.25" stop-color="#FFE9B8" stop-opacity="0.45"></stop><stop offset="1" stop-color="#FFE9B8" stop-opacity="0"></stop></radialGradient>'
    '<radialGradient id="bloomGold"><stop offset="0" stop-color="#FFF3B0" stop-opacity="1"></stop><stop offset="0.3" stop-color="#FFD400" stop-opacity="0.55"></stop><stop offset="1" stop-color="#FFD400" stop-opacity="0"></stop></radialGradient>'
    '<linearGradient id="beam" x1="0" y1="1" x2="0" y2="0"><stop offset="0" stop-color="#BFE3FF" stop-opacity="0.9"></stop><stop offset="1" stop-color="#58A7FF" stop-opacity="0"></stop></linearGradient>'
    '<linearGradient id="beamGold" x1="0" y1="1" x2="0" y2="0"><stop offset="0" stop-color="#FFF3B0" stop-opacity="1"></stop><stop offset="1" stop-color="#FFD400" stop-opacity="0"></stop></linearGradient>'
    '<filter id="glow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="6"></feGaussianBlur></filter>'
    '<filter id="soft" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="2.2"></feGaussianBlur></filter>'
)


# ───────────────────────────── the stadium, in yards ─────────────────────────────
# Field x: -60..60 including end zones, z: -26.7..26.7, y up. The bowl is a
# superellipse offset from the field, which reads as a stadium without being
# a copy of any real one.

HALF_W = 26.67
TURF_LIT_A, TURF_LIT_B = "#1E6A34", "#237A3C"


def bowl_point(m, t, n=4.0):
    a, b = 60 + m, HALF_W + m
    c, s = math.cos(t), math.sin(t)
    return (a * math.copysign(abs(c) ** (2 / n), c), b * math.copysign(abs(s) ** (2 / n), s))


def tier_height(m):
    if m <= 36:
        return 1.0 + 0.62 * (m - 6)
    return 24.0 + 0.78 * (m - 42)


LOWER = [6, 9, 12, 15, 18, 21, 24, 27, 30, 33, 36]
UPPER = [42, 46, 50, 54, 58, 62, 66, 70]


def stadium(sc: Scene, gm: dict, mood: str = "live", rng_seed: int = 12, dots: int = 2600, visitors_hot: bool = False, upper: bool = True):
    rng = random.Random(rng_seed)
    N = 110
    ts = [2 * math.pi * i / N for i in range(N + 1)]
    for rings, base in ((LOWER, (48, 39, 34)), (UPPER, (38, 31, 28)))[: 2 if upper else 1]:
        for i in range(len(rings) - 1):
            m0, m1 = rings[i], rings[i + 1]
            h0, h1 = tier_height(m0), tier_height(m1)
            shade = 1.0 - 0.25 * i / len(rings)
            col = "#%02X%02X%02X" % tuple(int(c * shade) for c in base)
            for j in range(N):
                x0, z0 = bowl_point(m0, ts[j]); x1, z1 = bowl_point(m0, ts[j + 1])
                x2, z2 = bowl_point(m1, ts[j + 1]); x3, z3 = bowl_point(m1, ts[j])
                sc.poly([(x0, h0, z0), (x1, h0, z1), (x2, h1, z2), (x3, h1, z3)], col, extra='stroke="rgba(255,255,255,0.05)" stroke-width="0.6"')
        # the concourse wall under the upper deck
    for j in range(N if upper else 0):
        x0, z0 = bowl_point(36, ts[j]); x1, z1 = bowl_point(36, ts[j + 1])
        x2, z2 = bowl_point(42, ts[j + 1]); x3, z3 = bowl_point(42, ts[j])
        sc.poly([(x0, tier_height(36), z0), (x1, tier_height(36), z1), (x2, 24, z2), (x3, 24, z3)], "#15110F")
    for m in (LOWER + UPPER if upper else LOWER):
        pts = [(bowl_point(m, t)[0], tier_height(m) + 0.02, bowl_point(m, t)[1]) for t in ts]
        sc.line(pts, "rgba(255,240,220,0.10)", 0.5, bias=-0.2)
    # crowd
    home = B.BOARD[B.SPOT]["home"]["color"]
    away = B.BOARD[B.SPOT]["away"]["color"]
    for _ in range(dots):
        up = upper and rng.random() < 0.42
        m = rng.uniform(6.5, 35.5) if not up else rng.uniform(42.5, 69.5)
        t = rng.uniform(0, 2 * math.pi)
        x, z = bowl_point(m, t)
        y = tier_height(m) + 0.4
        # the visiting section: a wedge of the far upper corner
        in_away = (x > 40 and z < -10 and (up or not upper))
        if in_away:
            col = away if rng.random() < 0.8 else "#F2F2F2"
        else:
            r = rng.random()
            col = home if r < 0.62 else "#F4F1EA" if r < 0.86 else "#2A2A2A"
        op = 0.9
        if visitors_hot:
            op = 1.0 if in_away else 0.28
        glow = ' filter="url(#soft)"' if (visitors_hot and in_away) else ""
        sc.dot((x, y, z), 0.34 if not (visitors_hot and in_away) else 0.8, col, extra=f'opacity="{op}"{glow}', rmin=0.55, rmax=2.6)
    # light banks on the rim: the product's one ornament, now at full size
    rim = 70 if upper else 36
    for t in [k * math.pi / 5 + 0.3 for k in range(10)]:
        x, z = bowl_point(rim + 1, t)
        if z > 12:
            continue
        y = tier_height(rim) + (9 if upper else 5)
        c = sc.cam.p(x, y, z)
        if not c:
            continue
        s = sc.cam.f / c[2]
        w, h = 12 * s, 5 * s
        sc.raw(c[2] - 1, f'<rect x="{c[0] - w / 2:.1f}" y="{c[1] - h / 2:.1f}" width="{w:.1f}" height="{h:.1f}" fill="#FFF8E6" opacity="0.95"></rect>'
                         f'<circle cx="{c[0]:.1f}" cy="{c[1]:.1f}" r="{max(24, 34 * s):.1f}" fill="url(#bloom)" opacity="{0.55 if mood == "td" else 0.9}"></circle>')
        sc.line([(x, y - 2.5, z), (x, tier_height(rim), z)], "#4A4038", 1.2, scale=True)
    # turf, lit
    for i in range(20):
        a, b = i * 5 - 50, i * 5 - 45
        sc.poly([(a, 0, -HALF_W), (b, 0, -HALF_W), (b, 0, HALF_W), (a, 0, HALF_W)], TURF_LIT_A if i % 2 else TURF_LIT_B, bias=0)
    for side, x0, x1, t in ((gm["away"], -60, -50, gm["away"]), (gm["home"], 50, 60, gm["home"])):
        sc.poly([(x0, 0, -HALF_W), (x1, 0, -HALF_W), (x1, 0, HALF_W), (x0, 0, HALF_W)], side["fill"])
    # surround and sidelines
    for x0, z0, x1, z1 in ((-66, -HALF_W - 6, 66, -HALF_W), (-66, HALF_W, 66, HALF_W + 6), (-66, -HALF_W, -60, HALF_W), (60, -HALF_W, 66, HALF_W)):
        sc.poly([(x0, -0.01, z0), (x1, -0.01, z0), (x1, -0.01, z1), (x0, -0.01, z1)], "#17401F")
    field_depth_bias = 0.0
    for yd in range(-50, 51, 5):
        op = 0.9 if yd in (-50, 50) else 0.62 if yd % 10 == 0 else 0.38
        sc.line([(yd, 0.02, -HALF_W), (yd, 0.02, HALF_W)], f"rgba(255,255,255,{op})", 0.28, scale=True, bias=-0.5)
    hz = HALF_W - 20
    for yd in range(-49, 50):
        for zz in (hz, -hz):
            sc.line([(yd, 0.02, zz - 0.4), (yd, 0.02, zz + 0.4)], "rgba(255,255,255,0.45)", 0.12, scale=True, bias=-0.5)
    for yd in range(-40, 41, 10):
        num = str(50 - abs(yd))
        for zz, ux in ((HALF_W - 9, (1, 0)), (-(HALF_W - 9), (-1, 0))):
            txt = world_text(sc, yd, 0.03, zz, num, 2.0 * 1.6, "rgba(255,255,255,0.72)", ux)
            if txt:
                sc.raw(txt[0], txt[1])
    for t, xc, ux in ((gm["away"], -55, (0, -1)), (gm["home"], 55, (0, 1))):
        txt = world_text(sc, xc, 0.03, 0, t["name"].upper(), 6.5, "rgba(255,255,255,0.92)", ux)
        if txt:
            sc.raw(txt[0] - 0.4, txt[1])
    return field_depth_bias


def world_text(sc, x, y, z, text, size, fill, ux=(1, 0), weight=800):
    o = sc.cam.p(x, y, z)
    ax = sc.cam.p(x + ux[0], y, z + ux[1])
    az = sc.cam.p(x - ux[1], y, z + ux[0])
    if not (o and ax and az):
        return None
    a, b = ax[0] - o[0], ax[1] - o[1]
    c, d = az[0] - o[0], az[1] - o[1]
    return (o[2], f'<text transform="matrix({a:.3f},{b:.3f},{c:.3f},{d:.3f},{o[0]:.1f},{o[1]:.1f})" font-family="{DISPLAY}" font-weight="{weight}" '
                  f'font-size="{size}" fill="{fill}" text-anchor="middle" dominant-baseline="central">{e(text)}</text>')


def fx(yd_from_left_goal):
    """Yards from the offense's own goal line (0..100) to world x."""
    return yd_from_left_goal - 50


def drive_in_air(sc, plays, gold_last=False, width=0.55):
    n = len(plays)
    for i, pl in enumerate(plays):
        z = -9 + 18 * (i / max(1, n - 1))
        a, b = fx(pl["from"]), fx(pl["to"])
        k = pl["kind"]
        dist = abs(pl["to"] - pl["from"])
        passing = "Pass" in k
        apex = (3.0 + 0.35 * dist) if passing else (0.8 + 0.12 * dist)
        last = i == n - 1
        scoring = "Touchdown" in k
        col = GOLD if scoring else RED if pl["yds"] < 0 else "#FFFFFF" if passing else "#9FD8FF"
        pts = [(a + (b - a) * s, 0.3 + apex * 4 * s * (1 - s), z) for s in (j / 36 for j in range(37))]
        halo = 2.6 if (last or scoring) else 1.4
        sc.line(pts, col, width * halo, extra=f'opacity="0.35" filter="url(#glow)"', scale=True, bias=-2)
        dash = 'stroke-dasharray="10 8"' if "Incompletion" in k else ""
        sc.line(pts, col, width * (1.3 if last else 1.0), extra=dash, scale=True, bias=-2.1)
        sc.dot((a, 0.05, z), 0.35, col, extra='opacity="0.9"', rmin=1.5, rmax=6, bias=-2)


def ball_beacon(sc, x, gold=False, height=34):
    base = sc.cam.p(x, 0, 0)
    top = sc.cam.p(x, height, 0)
    if not (base and top):
        return
    w = max(6, sc.cam.f * 1.4 / base[2])
    grad = "beamGold" if gold else "beam"
    sc.raw(base[2] - 3, f'<polygon points="{base[0] - w:.1f},{base[1]:.1f} {base[0] + w:.1f},{base[1]:.1f} {top[0] + w * 0.35:.1f},{top[1]:.1f} {top[0] - w * 0.35:.1f},{top[1]:.1f}" fill="url(#{grad})" opacity="0.75"></polygon>'
                        f'<ellipse cx="{base[0]:.1f}" cy="{base[1]:.1f}" rx="{w * 2.6:.1f}" ry="{w * 0.9:.1f}" fill="url(#{"bloomGold" if gold else "bloom"})" opacity="0.9"></ellipse>')


def laser(sc, x, color):
    sc.line([(x, 0.05, -HALF_W), (x, 0.05, HALF_W)], color, 0.9, extra='opacity="0.45" filter="url(#glow)"', scale=True, bias=-1)
    sc.line([(x, 0.05, -HALF_W), (x, 0.05, HALF_W)], color, 0.35, scale=True, bias=-1.1)


def wp_horizon(sc, wp_home, osu_away=True, z=-58, y0=52, y1=76, x0=-70, x1=70):
    n = len(wp_home)
    sc.line([(x0, y0, z), (x1, y0, z)], "rgba(255,255,255,0.18)", 1.5, bias=-5)
    sc.line([(x0, y1, z), (x1, y1, z)], "rgba(255,255,255,0.18)", 1.5, bias=-5)
    sc.line([(x0, (y0 + y1) / 2, z), (x1, (y0 + y1) / 2, z)], "rgba(255,255,255,0.28)", 1.2, extra='stroke-dasharray="8 10"', bias=-5)
    pts = [(x0 + (x1 - x0) * i / max(1, n - 1), y0 + (y1 - y0) * (1 - q if osu_away else q), z) for i, q in enumerate(wp_home)]
    sc.line(pts, INK, 7, extra='opacity="0.35" filter="url(#glow)"', bias=-5.1)
    sc.line(pts, INK, 3.2, bias=-5.2)
    return sc.cam.p(*pts[-1]), sc.cam.p(x0, y1, z)


# ───────────────────────────── overlays ─────────────────────────────

def at(x, y, inner, anchor="center", z=0):
    tx = {"center": "-50%", "left": "0", "right": "-100%"}[anchor]
    return f'<div style="position: absolute; left: {x:.0f}px; top: {y:.0f}px; transform: translate({tx}, -50%); z-index: {z}">{inner}</div>'


def glass_panel(inner, w=None, pad="18px 22px", radius=28):
    width = f"width: {w}px;" if w else ""
    return (f'<div style="{width} box-sizing: border-box; padding: {pad}; border-radius: {radius}px; background: rgba(28,30,34,0.78); '
            f'backdrop-filter: blur(30px); border: 1px solid rgba(255,255,255,0.18); box-shadow: 0 24px 60px rgba(0,0,0,0.45), inset 0 1px 0 rgba(255,255,255,0.16)">{inner}</div>')


def ornament(items, active=0, fs=17):
    cells = "".join(
        f'<div style="display: flex; align-items: center; gap: 9px; height: 60px; padding: 0 22px; border-radius: 30px; font-family: {SANS}; font-size: {fs}px; font-weight: 600; '
        f'background: {"rgba(255,255,255,0.92)" if i == active else "transparent"}; color: {"#141619" if i == active else INK}; white-space: nowrap">{glyph}<span>{e(lbl)}</span></div>'
        for i, (glyph, lbl) in enumerate(items))
    return (f'<div style="display: flex; gap: 4px; padding: 8px; border-radius: 38px; background: rgba(34,36,40,0.82); border: 1px solid rgba(255,255,255,0.18); '
            f'box-shadow: 0 20px 50px rgba(0,0,0,0.45)">{cells}</div>')


def caption(title, sub):
    return (f'<div style="display: flex; flex-direction: column; gap: 6px">'
            f'<span style="font-family: {DISPLAY}; font-weight: 900; font-size: 46px; text-transform: uppercase; color: {INK}; line-height: 1; text-shadow: 0 2px 20px rgba(0,0,0,0.6)">{e(title)}</span>'
            f'<span style="font-family: {SERIF}; font-style: italic; font-size: 22px; color: {INK2}; text-shadow: 0 2px 14px rgba(0,0,0,0.6)">{e(sub)}</span></div>')


def doc_frame(w, h, inner, bg):
    return B.doc(f'<div style="position: relative; width: {w}px; height: {h}px; overflow: hidden; background: {bg}">{inner}</div>')


NIGHT = "linear-gradient(180deg, #03050A 0%, #0A1222 38%, #1A2436 56%, #0B0D12 100%)"


def spot_state():
    gm = B.spot_game()
    cur = B.SUM["drives"]["current"]
    plays = B.drive_plays(cur)
    wp = [q["homeWinPercentage"] for q in B.SUM["winprobability"]]
    return gm, plays, wp


# ───────────────────────────── 1. stadium ─────────────────────────────

def stadium_scene(w, h, eye=(-4, 21, 54), target=(6, -2, -10), fov=100, dots=5200, labels=True, mood="live"):
    gm, plays, wp = spot_state()
    cam = Persp(w, h, eye, target, fov)
    sc = Scene(cam)
    stadium(sc, gm, mood, dots=dots)
    scrim = 100 - gm["ytg"]
    m = re.search(r"& (\d+)", gm["down"] or "")
    first = scrim + int(m.group(1)) if m else None
    laser(sc, fx(scrim), BLUE)
    if first:
        laser(sc, fx(first), GOLD)
    # red zone: the last twenty yards glow faintly red on the turf itself
    sc.poly([(30, 0.01, -HALF_W), (50, 0.01, -HALF_W), (50, 0.01, HALF_W), (30, 0.01, HALF_W)], "rgba(223,11,11,0.20)", bias=-0.3)
    drive_in_air(sc, plays)
    ball_beacon(sc, fx(scrim))
    tip, left_top = wp_horizon(sc, wp)
    overlays = []
    if labels:
        bt = cam.p(fx(scrim), 36, 0)
        if bt:
            overlays.append(at(bt[0], bt[1] - 30, glass_panel(
                f'<div style="display: flex; flex-direction: column; align-items: center; gap: 4px"><span style="font-family: {DISPLAY}; font-weight: 800; font-size: 40px; color: {INK}; line-height: 1">{e(gm["down"].split(" at ")[0])}</span>'
                f'<span style="font-family: {SANS}; font-size: 15px; color: {INK2}">at {e(gm["down"].split(" at ")[1])} · {B.badge("Red zone", RED_FILL, "redzone", 12)}</span></div>', pad="12px 20px", radius=24)))
        if tip:
            overlays.append(at(tip[0] + 18, tip[1], f'<div style="font-family: {SANS}; font-weight: 700; font-size: 22px; color: {INK}; text-shadow: 0 2px 12px #000">OSU {(1 - wp[-1]) * 100:.0f}%</div>', "left"))
        if left_top:
            overlays.append(at(left_top[0], left_top[1] - 22, f'<div style="font-family: {SANS}; font-weight: 600; font-size: 14px; letter-spacing: 0.14em; text-transform: uppercase; color: {INK2}; text-shadow: 0 2px 12px #000">Win probability horizon · ESPN</div>', "left"))
    return sc, cam, gm, plays, wp, overlays


def scorebug_big(gm, detail):
    return B.scorebug(gm["away"], gm["home"], detail.replace(" - ", " · "), gm["down"], ("Red zone", RED_FILL, "redzone"), 1.25)


def artboard_stadium():
    W, H = 2400, 1350
    sc, cam, gm, plays, wp, overlays = stadium_scene(W, H)
    st = B.summary_state(B.SUM)
    # plays within reach: a panel at the left hand, the other games at the right
    rows = []
    for i, p in enumerate(plays):
        txt = re.sub(r"^\(\d+:\d+\)\s*(Shotgun\s*)?", "", p["text"])
        txt = re.sub(r"#\d+ ", "", txt).split(" (")[0].split(", End Of")[0].split(" for ")[0]
        rows.append(f'<div style="display: flex; gap: 10px; font-family: {SANS}; font-size: 15px; color: {INK if i == len(plays) - 1 else INK2}; white-space: nowrap; overflow: hidden; text-overflow: ellipsis">'
                    f'<span style="width: 20px; font-weight: 700; color: {INK}">{i + 1}</span><span style="font-weight: 600; color: {INK}; width: 130px">{e(p["down"])}</span><span>{e(txt)}</span></div>')
    drive = glass_panel(f'{B.section(B.SUM["drives"]["current"]["description"], "This drive", 26)}<div style="display: flex; flex-direction: column; gap: 7px; margin-top: 12px">{"".join(rows)}</div>', 520)
    others = [B.BOARD[i] for i in ("401856681", "401856788", "401866418")]
    other = glass_panel(f'{B.section("tap to jump seats", "Elsewhere", 26)}<div style="display: flex; flex-direction: column; gap: 12px; margin-top: 12px">{"".join(B.tile(x, 300, 100, "s") for x in others)}</div>', 344)
    orn = ornament([(B.g("stadium", 22), "Stadium"), (B.g("cube", 22), "Tabletop"), (B.g("flag", 22), "Replay drive"), (B.g("live", 22), "Crowd audio")])
    jumbo = cam.p(0, 70, -70)
    overlays += [
        at(W / 2, 100, scorebug_big(gm, st["detail"])),
        at(70, 930, drive, "left"),
        at(W - 70, 900, other, "right"),
        at(W / 2, H - 70, orn),
        at(70, 90, caption("Stadium", "Full immersion · seated at the 50, row 16 · Ohio State at Texas, recorded"), "left"),
    ]
    vignette = f'<div style="position: absolute; inset: 0; background: radial-gradient(1400px 900px at 50% 45%, transparent 55%, rgba(0,0,0,0.55) 100%); pointer-events: none"></div>'
    haze = f'<div style="position: absolute; left: 0; right: 0; top: 180px; height: 420px; background: radial-gradient(1200px 260px at 50% 100%, rgba(255,236,200,0.18), transparent 70%); pointer-events: none"></div>'
    return doc_frame(W, H, haze + sc.svg(DEFS) + vignette + "".join(overlays), NIGHT)


# ───────────────────────────── 2. touchdown ─────────────────────────────

def artboard_touchdown():
    W, H = 2400, 1350
    gm, _, wp = spot_state()
    drives = B.SUM["drives"]["previous"]
    td = next(d for d in drives if d.get("displayResult") == "Touchdown")
    plays = B.drive_plays(td)
    score = next(p for p in B.SUM["scoringPlays"] if "TD" in p["text"])
    cam = Persp(W, H, (-6, 30, 64), (34, 6, -18), 96)
    sc = Scene(cam)
    stadium(sc, gm, "td", dots=5600, visitors_hot=True)
    drive_in_air(sc, plays, width=0.6)
    ball_beacon(sc, fx(100), gold=True, height=48)
    # fireworks off the rim above the visiting section
    rng = random.Random(4)
    for cx_, cy_, cz_ in ((70, 58, -50), (40, 66, -62), (88, 50, -30)):
        c = cam.p(cx_, cy_, cz_)
        if not c:
            continue
        s = cam.f / c[2]
        rays = []
        for k in range(22):
            ang = 2 * math.pi * k / 22 + rng.uniform(-0.05, 0.05)
            r0, r1 = 3 * s, rng.uniform(10, 16) * s
            col = gm["away"]["color"] if k % 3 else GOLD
            rays.append(f'<path d="M{c[0] + math.cos(ang) * r0:.1f},{c[1] + math.sin(ang) * r0:.1f} L{c[0] + math.cos(ang) * r1:.1f},{c[1] + math.sin(ang) * r1:.1f}" stroke="{col}" stroke-width="{max(1.5, 0.5 * s):.1f}" stroke-linecap="round"></path>')
        sc.raw(c[2], f'<g opacity="0.95">{"".join(rays)}</g><circle cx="{c[0]:.1f}" cy="{c[1]:.1f}" r="{18 * s:.1f}" fill="url(#bloomGold)" opacity="0.6"></circle>')
    ez = cam.p(55, 20, 0)
    lead = f'{B.badge("Touchdown", GOLD_FILL, "flag", 18)}'
    word = (f'<div style="display: flex; flex-direction: column; align-items: center; gap: 12px">'
            f'<span style="font-family: {DISPLAY}; font-weight: 900; font-size: 190px; line-height: 0.85; color: #FFF6CC; letter-spacing: 0.02em; '
            f'text-shadow: 0 0 30px rgba(255,212,0,0.85), 0 0 90px rgba(255,212,0,0.55), 0 8px 0 rgba(0,0,0,0.35)">TOUCHDOWN</span>'
            f'<span style="font-family: {SANS}; font-weight: 600; font-size: 26px; color: {INK}; text-shadow: 0 2px 14px #000">{e(score["text"])}</span></div>')
    bug = B.scorebug({**gm["away"], "score": str(score["awayScore"])}, {**gm["home"], "score": str(score["homeScore"])},
                     f'1st · {score["clock"]["displayValue"]}', "Ohio State scores", ("Touchdown", GOLD_FILL, "flag"), 1.25)
    note = glass_panel(
        f'<div style="display: flex; flex-direction: column; gap: 10px; font-family: {SANS}; font-size: 16px; color: {INK}; line-height: 1.45">'
        f'{B.section("the stadium follows your team", "Your section", 26)}'
        f'<span>The scarlet corner is the visiting section. When your team scores it lights up and the rest of the bowl dims to 28%. If the home team scores, the reverse.</span>'
        f'<span style="color: {INK2}">Spatial audio: the roar comes from that corner, not from everywhere.</span></div>', 460)
    wash = f'<div style="position: absolute; inset: 0; background: radial-gradient(1600px 900px at 80% 30%, rgba(186,12,47,0.22), transparent 70%); pointer-events: none"></div>'
    flash = f'<div style="position: absolute; inset: 0; background: radial-gradient(900px 600px at 62% 48%, rgba(255,230,140,0.20), transparent 70%); pointer-events: none; mix-blend-mode: screen"></div>'
    overlays = [at(W / 2, 100, bug), at(W / 2 + 120, 330, word), at(70, 1130, note, "left"),
                at(70, 90, caption("The moment", "Ohio State touchdown · J. Jackson 8-yard run, 1st quarter, recorded"), "left"),
                at(W / 2, H - 70, ornament([(B.g("flag", 22), "Replay from all angles"), (B.g("cube", 22), "Tabletop"), (B.g("live", 22), "Crowd audio")], active=-1))]
    return doc_frame(W, H, sc.svg(DEFS) + wash + flash + "".join(overlays), NIGHT)


# ───────────────────────────── 3. the room ─────────────────────────────

def room_shell(sc: Scene, dim=0.45):
    """A living room at night, seen through passthrough, dimmed by mixed immersion."""
    wallc = "#3A3834"
    sc.poly([(-2.6, 0, -3.2), (2.6, 0, -3.2), (2.6, 2.6, -3.2), (-2.6, 2.6, -3.2)], "#34322E")
    sc.poly([(-2.6, 0, 1.2), (-2.6, 0, -3.2), (-2.6, 2.6, -3.2), (-2.6, 2.6, 1.2)], wallc)
    sc.poly([(2.6, 0, -3.2), (2.6, 0, 1.2), (2.6, 2.6, 1.2), (2.6, 2.6, -3.2)], wallc)
    sc.poly([(-2.6, 0, 1.2), (2.6, 0, 1.2), (2.6, 0, -3.2), (-2.6, 0, -3.2)], "#2A2622")
    sc.poly([(-2.6, 2.6, 1.2), (2.6, 2.6, 1.2), (2.6, 2.6, -3.2), (-2.6, 2.6, -3.2)], "#2E2C29")
    # window on the right wall, night outside
    sc.poly([(2.59, 0.9, -2.6), (2.59, 0.9, -0.9), (2.59, 2.1, -0.9), (2.59, 2.1, -2.6)], "#0E1626", "#6B665C", 3)
    for i in range(14):
        rx = random.Random(i)
        sc.dot((2.58, 0.95 + rx.random() * 0.5, -2.5 + rx.random() * 1.5), 0.01, "#FFD98A", rmin=1, rmax=2.5)
    # rug, coffee table, a lamp in the corner, the TV that is not the point any more
    sc.poly([(-1.4, 0.005, 0.2), (1.4, 0.005, 0.2), (1.4, 0.005, -2.2), (-1.4, 0.005, -2.2)], "#3B2F27")
    top, zf, zb = 0.42, -1.0, -1.72
    sc.poly([(-0.62, top, zf), (0.62, top, zf), (0.62, top, zb), (-0.62, top, zb)], "#4A3B30", bias=0.0)
    sc.poly([(-0.62, top, zf), (0.62, top, zf), (0.62, 0.36, zf), (-0.62, 0.36, zf)], "#2B221C")
    sc.poly([(-2.0, 0.55, -3.19), (-0.7, 0.55, -3.19), (-0.7, 1.28, -3.19), (-2.0, 1.28, -3.19)], "#0B0C0E", "#1E1F22", 2)
    sc.line([(-2.3, 0, -2.9), (-2.3, 1.55, -2.9)], "#5A5248", 3)
    lamp = sc.cam.p(-2.3, 1.6, -2.9)
    if lamp:
        sc.raw(lamp[2] - 0.1, f'<circle cx="{lamp[0]:.1f}" cy="{lamp[1]:.1f}" r="120" fill="url(#bloom)" opacity="0.35"></circle>')
    return top, (zf + zb) / 2


def tabletop(sc: Scene, gm, plays, wp, cx=0.0, cy=0.44, cz=-1.36, scale=0.0040, dots=1400, glow=True):
    """The stadium, lower bowl only, shrunk onto the coffee table: 1 yd = 4 mm, so the field is 0.48 m."""
    class Shrunk:
        def __init__(self, cam):
            self.cam, self.w, self.h, self.f = cam, cam.w, cam.h, cam.f

        def p(self, x, y, z):
            q = self.cam.p(cx + x * scale, cy + y * scale, cz + z * scale)
            if not q:
                return None
            return (q[0], q[1], q[2] / scale)       # depth in yards, so painter order stays local
    inner = Scene(Shrunk(sc.cam))
    stadium(inner, gm, dots=dots, upper=False)
    scrim = 100 - gm["ytg"]
    laser(inner, fx(scrim), BLUE)
    m = re.search(r"& (\d+)", gm["down"] or "")
    if m:
        laser(inner, fx(scrim + int(m.group(1))), GOLD)
    drive_in_air(inner, plays, width=1.1)
    ball_beacon(inner, fx(scrim), height=40)
    body = "".join(s for _, s in sorted(inner.items, key=lambda t: -t[0]))
    c = sc.cam.p(cx, cy, cz)
    sc.raw(c[2] - 0.01, f'<g>{body}</g>')
    if glow:
        sc.raw(c[2] + 0.02, f'<ellipse cx="{c[0]:.1f}" cy="{c[1] + 10:.1f}" rx="360" ry="110" fill="url(#bloom)" opacity="0.30"></ellipse>')
    return c


def artboard_room():
    W, H = 2600, 1500
    gm, plays, wp = spot_state()
    eye = (0, 1.1, 0)
    cam = Cyl(W, H, eye, span=150, horizon=0.40)
    sc = Scene(cam)
    room_shell(sc)
    c = tabletop(sc, gm, plays, wp)
    dim = f'<div style="position: absolute; inset: 0; background: rgba(6,7,10,0.42); pointer-events: none"></div>'
    spill = (f'<div style="position: absolute; inset: 0; pointer-events: none; background: radial-gradient(900px 420px at {c[0]:.0f}px {c[1] + 60:.0f}px, rgba(191,87,0,0.28), transparent 70%), '
             f'radial-gradient(1400px 500px at 50% 8%, rgba(255,236,190,0.12), transparent 70%)"></div>')
    fg = Scene(cam)
    # the light bank floats over the arc, 2.25 m up, 1.9 m out
    for deg in range(-44, 45, 4):
        r = 1.9
        x, z = r * math.sin(math.radians(deg)), -r * math.cos(math.radians(deg))
        fg.raw(0, "")
        q = cam.p(x, 2.0, z)
        if q:
            fg.raw(q[2], f'<circle cx="{q[0]:.1f}" cy="{q[1]:.1f}" r="7" fill="#FFF6DD"></circle><circle cx="{q[0]:.1f}" cy="{q[1]:.1f}" r="26" fill="url(#bloom)" opacity="0.8"></circle>')
    overlays = []

    def place(deg, height, inner, r=1.9, scale=1.0, anchor="center"):
        x, z = r * math.sin(math.radians(deg)), -r * math.cos(math.radians(deg))
        q = cam.p(x, height, z)
        s = scale * 1.9 / r
        return (f'<div style="position: absolute; left: {q[0]:.0f}px; top: {q[1]:.0f}px; transform: translate(-50%, -50%) scale({s:.3f}); transform-origin: center">{inner}</div>')

    b = B.BOARD
    st = B.summary_state(B.SUM)
    # the arc: 17 degrees a column, starting 0.18 m above the eye, as the headset app learned
    left = [("401866418", -34, 1.62), ("401871045", -17, 1.62), ("401856783", -34, 1.26), ("401856681", -17, 1.26)]
    right = [("401856676", 17, 1.62), ("401867796", 34, 1.62), ("401856788", 17, 1.26), ("401860881", 34, 1.26)]
    for gid, deg, hgt in left + right:
        overlays.append(place(deg, hgt, B.tile(b[gid]), scale=0.72))
    overlays.append(place(-25.5, 1.86, f'<div style="text-shadow: 0 2px 12px #000">{B.section("4th quarter or one score", "Close & late", 30)}</div>', scale=0.9))
    overlays.append(place(25.5, 1.86, f'<div style="text-shadow: 0 2px 12px #000">{B.section("top 25", "Ranked, live", 30)}</div>', scale=0.9))
    wake = {"ot": "2OT"}
    wing_l = glass_panel(f'{B.section("so far", "Tonight", 28)}<div style="display: flex; flex-direction: column; gap: 14px; margin-top: 12px">{B.tile(b["401858224"], override=wake)}{B.tile(b["401856782"])}</div>', 352)
    wing_r = glass_panel(f'{B.section("next", "Coming up", 28)}<div style="display: flex; flex-direction: column; gap: 14px; margin-top: 12px">{B.tile(b["401856670"])}{B.tile(b["401858445"])}</div>', 352)
    overlays.append(place(-46, 1.35, wing_l, r=1.75, scale=0.72))
    overlays.append(place(46, 1.35, wing_r, r=1.75, scale=0.72))
    # the spotlight game is on the table: its scorebug and horizon float just above it
    overlays.append(place(0, 1.08, B.scorebug(gm["away"], gm["home"], st["detail"].replace(" - ", " · "), gm["down"], ("Red zone", RED_FILL, "redzone"), 1.0), r=1.3, scale=0.9))
    osu = (1 - wp[-1]) * 100
    horizon = (f'<svg width="560" height="70" style="display: block">'
               f'<line x1="0" y1="35" x2="560" y2="35" stroke="rgba(255,255,255,0.3)" stroke-dasharray="6 7"></line>'
               f'<path d="M' + " L".join(f"{560 * i / (len(wp) - 1):.1f},{8 + 54 * q:.1f}" for i, q in enumerate(wp)) + f'" fill="none" stroke="{INK}" stroke-width="3"></path></svg>')
    overlays.append(place(0, 1.36, f'<div style="display: flex; flex-direction: column; align-items: center; gap: 6px">{horizon}<span style="font-family: {SANS}; font-size: 15px; font-weight: 600; color: {INK}; text-shadow: 0 2px 10px #000">OSU {osu:.0f}% · win probability</span></div>', r=1.5, scale=0.85))
    orn = ornament([(B.g("cube", 22), "Room"), (B.g("stadium", 22), "Stadium"), (B.g("live", 22), "Crowd audio")])
    overlays.append(place(-27, 0.62, orn, r=1.1, scale=0.62))
    # angle guides, the constraints this layout is built inside
    guides = []
    for deg, lab in ((-46, "−46°"), (46, "+46°")):
        x = cam.yaw_x(deg)
        guides.append(f'<line x1="{x:.0f}" y1="60" x2="{x:.0f}" y2="{H - 40}" stroke="rgba(255,212,0,0.45)" stroke-width="1.5" stroke-dasharray="6 8"></line>'
                      f'<text x="{x + 8:.0f}" y="80" font-family="{SANS}" font-size="14" font-weight="600" fill="rgba(255,212,0,0.8)">{lab} wing limit</text>')
    y33 = cam.cy + cam.k * math.tan(math.radians(33))
    guides.append(f'<line x1="40" y1="{y33:.0f}" x2="{W - 40}" y2="{y33:.0f}" stroke="rgba(255,212,0,0.35)" stroke-width="1.5" stroke-dasharray="6 8"></line>'
                  f'<text x="{W - 48}" y="{y33 - 10:.0f}" font-family="{SANS}" font-size="14" font-weight="600" fill="rgba(255,212,0,0.8)" text-anchor="end">33° below eye · lowest panel</text>')
    guide_svg = f'<svg width="{W}" height="{H}" style="position: absolute; inset: 0; pointer-events: none">{"".join(guides)}</svg>'
    cap = at(70, H - 110, caption("Saturday Room", "Mixed immersion · 150° of your living room · the spotlight game lives on the coffee table"), "left")
    return doc_frame(W, H, sc.svg(DEFS) + dim + spill + fg.svg(DEFS) + guide_svg + "".join(overlays) + cap, "#15141A")


# ───────────────────────────── 4. immersion ramp ─────────────────────────────

def artboard_ramp():
    W, H = 2400, 900
    fw, fh = 740, 560
    gm, plays, wp = spot_state()

    def room_frame(portal: float):
        cam = Persp(fw, fh, (0, 1.18, 0.2), (0, 0.8, -2.2), 96)
        sc = Scene(cam)
        room_shell(sc)
        c = tabletop(sc, gm, plays, wp, dots=500, glow=portal == 0)
        inner = sc.svg(DEFS)
        dim = f'<div style="position: absolute; inset: 0; background: rgba(6,7,10,{0.35 + 0.35 * portal:.2f})"></div>'
        if portal <= 0:
            return inner + dim
        # the portal: a rounded opening in the back wall, the stadium beyond it
        p0 = cam.p(-1.9 * portal - 0.5, 0.15, -3.18)
        p1 = cam.p(1.9 * portal + 0.5, 2.45, -3.18)
        sx, sy = p0[0], p1[1]
        pw, ph = p1[0] - p0[0], p0[1] - p1[1]
        st, *_ = stadium_scene(fw, fh, eye=(0, 16, 50), target=(0, 3, -8), fov=90, dots=900, labels=False)
        return (inner + dim +
                f'<div style="position: absolute; left: {sx:.0f}px; top: {sy:.0f}px; width: {pw:.0f}px; height: {ph:.0f}px; border-radius: 48px; overflow: hidden; '
                f'box-shadow: 0 0 0 2px rgba(255,255,255,0.35), 0 0 80px 10px rgba(255,236,190,0.35); background: {NIGHT}">'
                f'<div style="position: absolute; left: {-sx:.0f}px; top: {-sy:.0f}px; width: {fw}px; height: {fh}px">{st.svg(DEFS)}</div></div>')

    def stadium_frame():
        st, cam, *_ = stadium_scene(fw, fh, eye=(0, 14, 44), target=(4, 2, -6), fov=100, dots=1400, labels=False)
        hands = (f'<div style="position: absolute; left: 0; right: 0; bottom: 0; height: 90px; background: linear-gradient(0deg, rgba(40,34,30,0.85), transparent); '
                 f'display: flex; align-items: flex-end; justify-content: center; padding-bottom: 14px; font-family: {SANS}; font-size: 13px; color: {INK2}">your hands and the sofa edge stay in passthrough</div>')
        return f'<div style="position: absolute; inset: 0; background: {NIGHT}"></div>{st.svg(DEFS)}{hands}'

    frames = [("0% · Tabletop", "The game on your coffee table. The room is yours; games ring the wall.", room_frame(0.0)),
              ("45% · Portal", "Turn the Crown and the back wall opens. The stadium is out there, in scale, while the table stays put.", room_frame(0.45)),
              ("100% · Stadium", "Keep turning and you are seated at the 50. The room is gone except your hands.", stadium_frame())]
    cells = "".join(
        f'<div style="display: flex; flex-direction: column; gap: 16px; width: {fw}px">'
        f'<div style="position: relative; width: {fw}px; height: {fh}px; border-radius: 30px; overflow: hidden; background: #15141A; border: 1px solid rgba(255,255,255,0.12)">{inner}</div>'
        f'<span style="font-family: {DISPLAY}; font-weight: 800; font-size: 34px; color: {INK}; text-transform: uppercase">{e(t)}</span>'
        f'<span style="font-family: {SANS}; font-size: 17px; color: {INK2}; line-height: 1.4">{e(d)}</span></div>'
        for t, d, inner in frames)
    crown = (f'<svg width="{3 * fw + 80}" height="30" style="display: block"><line x1="0" y1="15" x2="{3 * fw + 80}" y2="15" stroke="rgba(255,255,255,0.25)" stroke-width="2"></line>'
             f'<line x1="0" y1="15" x2="{(3 * fw + 80) * 0.999:.0f}" y2="15" stroke="{GOLD}" stroke-width="3" stroke-dasharray="2 10"></line></svg>')
    body = (f'<div style="position: absolute; left: 60px; top: 44px; display: flex; flex-direction: column; gap: 22px">'
            f'{caption("Immersion ramp", "One gesture from coffee table to the 50-yard line · Digital Crown, progressive immersion")}'
            f'<div style="display: flex; gap: 40px">{cells}</div>{crown}</div>')
    return doc_frame(W, H, body, "linear-gradient(180deg, #1B1D22, #111215)")


def main():
    files = {"ImmersiveRoom.dc.html": artboard_room(), "ImmersiveStadium.dc.html": artboard_stadium(),
             "ImmersiveTouchdown.dc.html": artboard_touchdown(), "ImmersionRamp.dc.html": artboard_ramp()}
    for name, src in files.items():
        (B.OUT / name).write_text(src)
        print(name, f"{len(src) / 1024:.0f} KB")


if __name__ == "__main__":
    main()
