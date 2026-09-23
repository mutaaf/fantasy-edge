"""Synthesise every sound the stadium plays, from nothing.

    /Applications/Blender.app/Contents/Resources/5.2/python/bin/python3.13 tools/audio/build.py
    nice -n 10 <that python> tools/audio/build.py --only roar whistle

No recordings and no downloads: every file is noise, oscillators and a
synthetic stadium impulse response, seeded, so the same command always
writes the same audio. It runs on Blender's bundled Python because that
interpreter carries numpy; nothing is pip-installed and the app never runs
this code. Output, per sound:

    assets/actors/audio/<name>.caf   Apple Lossless, for the headset
    assets/actors/audio/<name>.ogg   Opus, for the web and Android ports
    assets/actors/audio/manifest.json  seconds, loop, measured RMS and peak

Loudness is normalised here, not by ear: beds to one RMS, effects to
another, every peak soft-limited under -1 dBFS, so the runtime gains in
tokens.json (visual.audio.gains) are the whole mix and nothing arrives
louder than the level it was designed at. See docs/actors/moments-audio.md.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import wave

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "assets" / "actors" / "audio"
TOKENS = ROOT / "design" / "tokens.json"
RATE = 44100


# ───────────────────────────── primitives ─────────────────────────────

def rng(seed: int) -> np.random.Generator:
    return np.random.default_rng(seed)


def seconds(n: float) -> int:
    return int(round(n * RATE))


def t_axis(n: int) -> np.ndarray:
    return np.arange(n) / RATE


def band(x: np.ndarray, lo: float, hi: float, slope: float = 0.25) -> np.ndarray:
    """A soft band-pass in the frequency domain: raised-cosine skirts a
    `slope` octave wide either side, so no filter ever rings."""
    spec = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / RATE)
    g = np.ones_like(f)
    with np.errstate(divide="ignore"):
        lf = np.log2(np.maximum(f, 1e-3))
    if lo > 0:
        a, b = np.log2(lo) - slope, np.log2(lo)
        g *= np.clip((lf - a) / (b - a), 0, 1)
    if hi < RATE / 2:
        a, b = np.log2(hi), np.log2(hi) + slope
        g *= np.clip((b - lf) / (b - a), 0, 1)
    g = 0.5 - 0.5 * np.cos(np.pi * g)
    return np.fft.irfft(spec * g, n=len(x))


def tilt(x: np.ndarray, db_per_octave: float, pivot: float = 1000.0) -> np.ndarray:
    """Pink-ish colouring: a straight line in dB per octave about a pivot."""
    spec = np.fft.rfft(x)
    f = np.maximum(np.fft.rfftfreq(len(x), 1 / RATE), 20.0)
    g = 10 ** (db_per_octave * np.log2(f / pivot) / 20)
    return np.fft.irfft(spec * g, n=len(x))


def formant(x: np.ndarray, peaks: list[tuple[float, float, float]]) -> np.ndarray:
    """Sum of resonances (centre Hz, width Hz, gain) applied as a spectral
    envelope: how a vowel is carved out of a buzz."""
    spec = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / RATE)
    g = np.zeros_like(f)
    for fc, bw, amp in peaks:
        g += amp * np.exp(-0.5 * ((f - fc) / bw) ** 2)
    return np.fft.irfft(spec * g, n=len(x))


def drift(n: int, r: np.random.Generator, period: float) -> np.ndarray:
    """Slow random motion with unit spread: noise low-passed below 1/period Hz.
    Done in the frequency domain; a time-domain kernel this long would take
    minutes at 44.1 kHz."""
    x = band(r.standard_normal(n), 0, 1.0 / period, slope=1.0)
    return x / max(1e-9, np.std(x))


def syllables(n: int, r: np.random.Generator, rate: tuple[float, float], duty: float) -> np.ndarray:
    """A talking envelope: bursts at a syllabic rate, gathered into phrases."""
    env = np.zeros(n)
    t = 0
    while t < n:
        phrase = seconds(r.uniform(0.6, 2.4))
        if r.random() < duty:
            s = t
            while s < min(n, t + phrase):
                length = seconds(1 / r.uniform(*rate))
                seg = min(length, n - s)
                env[s:s + seg] += np.hanning(seg) * r.uniform(0.5, 1.0) if seg > 2 else 0
                s += length
        t += phrase + seconds(r.uniform(0.1, 0.8))
    return env


def buzz(n: int, f0: np.ndarray, harmonics: int = 24) -> np.ndarray:
    """A band-limited glottal buzz following a pitch track."""
    phase = 2 * np.pi * np.cumsum(f0) / RATE
    out = np.zeros(n)
    for h in range(1, harmonics + 1):
        mask = f0 * h < RATE / 2.2
        out += np.where(mask, np.sin(h * phase) / h ** 1.1, 0.0)
    return out


def impulse(length: float, decay: float, r: np.random.Generator, bright: float = 4000.0,
            early: list[tuple[float, float]] | None = None) -> np.ndarray:
    """A stadium's impulse response: sparse early reflections off the stands,
    then a dense tail that darkens as it decays. An open bowl is long but
    thin - most energy leaves through the roof."""
    n = seconds(length)
    t = t_axis(n)
    tail = r.standard_normal(n) * np.exp(-t / decay)
    # High frequencies die faster: split, decay the top quicker, recombine.
    top = band(tail, bright, RATE / 2) * np.exp(-t / (decay * 0.35))
    low = band(tail, 0, bright)
    ir = low + top
    ir[: seconds(0.012)] *= np.linspace(0, 1, seconds(0.012))
    for delay, gain in (early or [(0.0, 1.0), (0.043, 0.45), (0.071, 0.32), (0.118, 0.22), (0.19, 0.12)]):
        i = seconds(delay)
        if i < n:
            ir[i] += gain * 6
    return ir / np.max(np.abs(ir))


def reverb(x: np.ndarray, ir: np.ndarray, wet: float) -> np.ndarray:
    n = len(x) + len(ir) - 1
    size = 1 << (n - 1).bit_length()
    y = np.fft.irfft(np.fft.rfft(x, size) * np.fft.rfft(ir, size), size)[:n]
    y *= np.std(x) / max(1e-9, np.std(y))
    return np.concatenate([x, np.zeros(len(ir) - 1)]) * (1 - wet) + y * wet


def envelope(n: int, points: list[tuple[float, float]]) -> np.ndarray:
    """Piecewise-linear gain from (seconds, level) points."""
    t = t_axis(n)
    xs, ys = zip(*points)
    return np.interp(t, xs, ys)


def loop_seam(x: np.ndarray, fade: float = 1.0) -> np.ndarray:
    """Crossfade the tail into the head, equal power, so a bed loops unheard.

    Measured by `tools/audio/inspect_mix.py files`: every bed that uses this
    joins within its own normal motion. A rhythmic bed must not use it - see
    `wrap_tail` - because a crossfade lays two copies of the beat over itself.
    """
    k = seconds(fade)
    head, tail = x[:k], x[-k:]
    w = np.sin(np.linspace(0, np.pi / 2, k))
    out = x[:-k].copy()
    out[:k] = head * w + tail * np.cos(np.linspace(0, np.pi / 2, k))
    return out


def wrap_tail(y: np.ndarray, n: int) -> np.ndarray:
    """Fold everything past `n` back onto the head: circular convolution.

    For a bed with a rhythm, a crossfade is the wrong tool - it lays two
    copies of the beat over each other. Wrapping a reverb tail onto the
    beginning is what a loop actually does in the room: the decay of the last
    beat is still sounding when the first comes round again.
    """
    out = y[:n].copy()
    over = y[n:]
    if len(over):
        out[:len(over)] += over[:n]
    return out


def air(x: np.ndarray, top: float = 5200.0) -> np.ndarray:
    """Distance: tens of metres of air and a bowl of bodies take the top off
    a crowd. Without it thousands of voices read as hiss, not people."""
    return band(x, 25, top, slope=1.0)


# ───────────────────────────── crowds ─────────────────────────────

VOWELS = {
    "a": [(730, 90, 1.0), (1090, 110, 0.5), (2440, 160, 0.18)],
    "o": [(500, 80, 1.0), (880, 100, 0.45), (2400, 160, 0.10)],
    "e": [(530, 80, 1.0), (1840, 130, 0.45), (2480, 160, 0.20)],
    "u": [(330, 70, 1.0), (870, 100, 0.25), (2250, 150, 0.08)],
}


def babble(n: int, r: np.random.Generator, voices: int, rate=(3.0, 6.0), duty=0.55) -> np.ndarray:
    """Many people talking at once: formant-shaped noise bands, each gated by
    its own syllables. Intelligibility is deliberately impossible."""
    out = np.zeros(n)
    base = r.standard_normal(n)
    for v in range(voices):
        f1 = r.uniform(300, 850)
        f2 = r.uniform(900, 2400)
        layer = formant(np.roll(base, r.integers(0, n)), [(f1, 90, 1.0), (f2, 160, 0.4)])
        out += layer * syllables(n, r, rate, duty)
    return out / max(1, voices) ** 0.5


def shouts(n: int, r: np.random.Generator, count: int, loud: tuple[float, float] = (0.4, 1.0),
           when: tuple[float, float] | None = None) -> np.ndarray:
    """Individual voices over the bed: a pitched 'hey', 'ohh', 'yeah', each
    a buzz through a vowel, with a little pitch rise or fall."""
    out = np.zeros(n)
    lo, hi = (0, n) if when is None else (seconds(when[0]), min(n, seconds(when[1])))
    for _ in range(count):
        length = seconds(r.uniform(0.25, 0.9))
        start = int(r.integers(lo, max(lo + 1, hi - length)))
        seg = min(length, n - start)
        if seg < 64:
            continue
        f0 = r.uniform(140, 330) * np.linspace(1.0, r.uniform(0.85, 1.25), seg)
        f0 *= 1 + 0.02 * np.sin(2 * np.pi * r.uniform(4, 6) * t_axis(seg))
        v = formant(buzz(seg, f0), VOWELS[r.choice(list(VOWELS))])
        env = np.minimum(1, t_axis(seg) / 0.04) * np.exp(-t_axis(seg) / r.uniform(0.3, 0.8))
        out[start:start + seg] += v / max(1e-9, np.max(np.abs(v))) * env * r.uniform(*loud)
    return out


def fan_whistles(n: int, r: np.random.Generator, count: int, when=None) -> np.ndarray:
    """Two-finger whistles from the stands: a bright sine with a swoop."""
    out = np.zeros(n)
    lo, hi = (0, n) if when is None else (seconds(when[0]), min(n, seconds(when[1])))
    for _ in range(count):
        seg = seconds(r.uniform(0.3, 0.9))
        start = int(r.integers(lo, max(lo + 1, hi - seg)))
        seg = min(seg, n - start)
        if seg < 64:
            continue
        f = r.uniform(1900, 3200) * (1 + np.concatenate([np.linspace(-0.15, 0.08, seg // 3),
                                                          np.full(seg - seg // 3, 0.08)]))
        tone = np.sin(2 * np.pi * np.cumsum(f) / RATE)
        env = np.minimum(1, t_axis(seg) / 0.03) * np.minimum(1, (seg - np.arange(seg)) / seconds(0.08))
        out[start:start + seg] += tone * env * r.uniform(0.15, 0.4)
    return out


def claps(n: int, r: np.random.Generator, times: np.ndarray, people: int, jitter: float) -> np.ndarray:
    """Hands: every clapper hits near each beat, 3-8 ms of bright noise."""
    out = np.zeros(n)
    burst_len = seconds(0.008)
    for _ in range(people):
        amp = r.uniform(0.3, 1.0)
        centre = r.uniform(900, 2600)
        shape = np.hanning(burst_len) * amp
        click = band(r.standard_normal(burst_len * 8), centre * 0.6, centre * 1.8)[:burst_len] * shape
        for beat in times:
            i = seconds(beat + r.normal(0, jitter))
            if 0 <= i < n - burst_len:
                out[i:i + burst_len] += click
    return out


def crowd_body(n: int, r: np.random.Generator) -> np.ndarray:
    """The wash under every crowd sound: coloured noise with a hump where
    thousands of voices overlap, 250 Hz - 2 kHz."""
    x = tilt(r.standard_normal(n), -4.0)
    return band(x, 110, 4200, slope=0.7) + 1.1 * band(x, 250, 1800, slope=0.4)


# ───────────────────────────── the sounds ─────────────────────────────

def crowd_bed(r):
    """Between plays: a full bowl talking, restless, never still."""
    n = seconds(17)
    swell = 0.8 + 0.12 * np.sin(2 * np.pi * t_axis(n) / 8.0) + 0.08 * np.sin(2 * np.pi * t_axis(n) / 2.9)
    x = crowd_body(n, r) * 0.55 * swell
    x += babble(n, r, voices=18) * 0.9
    x += shouts(n, r, count=26, loud=(0.15, 0.45))
    x += fan_whistles(n, r, count=3)
    x += claps(n, r, np.sort(r.uniform(0, 17, 40)), people=3, jitter=0.01) * 0.4
    x = reverb(x, impulse(2.4, 0.7, r), wet=0.35)[:n]
    return loop_seam(air(x), 1.0), True


def clap_bed(r):
    """Rhythmic clapping, 120 beats a minute: sixteen beats, looping exactly."""
    n = seconds(8)
    beats = np.arange(0, 8, 0.5)
    x = claps(n, r, beats, people=90, jitter=0.022)
    x += crowd_body(n, r) * 0.08
    # The tail of beat 16 wraps into beat 1. It said so before and did not do
    # it: `[:n]` threw the reverb tail away, so the loop restarted a full clap
    # against a dead room and stepped 9.3 dB - the one bed you could hear go
    # round. No crossfade here: at 120 bpm a fade would double the beats.
    x = wrap_tail(reverb(x, impulse(2.0, 0.55, r), wet=0.45), n)
    return x, True


def murmur_bed(r):
    """The PA and the concourse, far away: speech-shaped, muffled, faint."""
    n = seconds(13)
    f0 = 118 * (1 + 0.06 * drift(n, r, 0.4))
    speech = formant(buzz(n, f0, 16), [(600, 180, 1.0), (1300, 250, 0.4)]) * syllables(n, r, (3.5, 5.5), 0.45)
    speech = band(speech, 150, 1400, slope=0.8)
    x = speech * 0.4 + babble(n, r, voices=8, duty=0.7) * 0.5
    x = reverb(x, impulse(3.2, 1.1, r, bright=1800), wet=0.7)[:n]
    return loop_seam(air(x), 1.2), True


def wind_bed(r):
    """Air over an open rim: low, gusting, a faint whistle at the top."""
    n = seconds(15)
    gust = 0.55 + 0.3 * drift(n, r, 1.2)
    low = band(r.standard_normal(n), 40, 420, slope=0.8) * np.clip(gust, 0.15, 1.3)
    whistle = band(r.standard_normal(n), 900, 1300, slope=0.2) * 0.05 * np.clip(gust - 0.6, 0, 1)
    return loop_seam(low + whistle, 1.5), True


def roar(r):
    """A touchdown: the section on its feet in a third of a second, a surge,
    the long tail as it settles back into a buzz."""
    n = seconds(6.5)
    env = envelope(n, [(0, 0.0), (0.08, 0.35), (0.35, 1.0), (1.4, 0.92), (2.2, 1.0), (3.5, 0.55), (6.5, 0.0)])
    x = crowd_body(n, r) * 1.1 * env
    x += babble(n, r, voices=24, rate=(4, 8), duty=0.8) * 0.8 * env
    x += shouts(n, r, count=70, loud=(0.35, 1.0), when=(0.05, 2.8))
    x += fan_whistles(n, r, count=14, when=(0.2, 3.0))
    x = reverb(x, impulse(2.6, 0.8, r), wet=0.3)[:n]
    return air(x), False


def cheer(r):
    """A field goal: glad, not delirious. Shorter, thinner, sooner over."""
    n = seconds(4.0)
    env = envelope(n, [(0, 0.0), (0.2, 0.8), (0.9, 0.7), (2.0, 0.35), (4.0, 0.0)])
    x = crowd_body(n, r) * 0.8 * env + babble(n, r, voices=14, duty=0.7) * 0.6 * env
    x += shouts(n, r, count=30, loud=(0.2, 0.7), when=(0.1, 1.6))
    x += fan_whistles(n, r, count=5, when=(0.2, 1.8))
    return air(reverb(x, impulse(2.4, 0.7, r), wet=0.32)[:n]), False


def groan(r):
    """The ball turned over, heard from the side that lost it: forty voices
    on one falling 'ohh', breath under it."""
    n = seconds(3.2)
    out = np.zeros(n)
    for _ in range(40):
        start = seconds(r.uniform(0, 0.25))
        seg = n - start
        f0 = r.uniform(130, 230) * np.linspace(1.0, r.uniform(0.68, 0.8), seg)
        v = formant(buzz(seg, f0, 18), VOWELS["o"])
        env = np.minimum(1, t_axis(seg) / 0.18) * np.exp(-t_axis(seg) / 1.1)
        out[start:] += v / max(1e-9, np.max(np.abs(v))) * env * r.uniform(0.3, 1.0)
    out += crowd_body(n, r) * 0.25 * envelope(n, [(0, 0), (0.2, 1), (3.2, 0)])
    return air(reverb(out, impulse(2.2, 0.7, r), wet=0.35)[:n]), False


def sting(r):
    """A turnover, heard from the side that took it: a sharp collective 'HA!'
    that jumps straight into a cheer, a thump of feet under it."""
    n = seconds(3.0)
    out = np.zeros(n)
    for _ in range(36):
        start = seconds(r.uniform(0, 0.08))
        seg = seconds(0.45)
        f0 = r.uniform(170, 320) * np.linspace(1.0, 1.15, seg)
        v = formant(buzz(seg, f0, 18), VOWELS["a"])
        env = np.minimum(1, t_axis(seg) / 0.015) * np.exp(-t_axis(seg) / 0.25)
        out[start:start + seg] += v / max(1e-9, np.max(np.abs(v))) * env * r.uniform(0.4, 1.0)
    thump_n = seconds(0.35)
    thump = np.sin(2 * np.pi * 55 * t_axis(thump_n)) * np.exp(-t_axis(thump_n) / 0.08)
    out[:thump_n] += thump * 0.9
    tail, _ = cheer(r)
    out[seconds(0.25):] += tail[: n - seconds(0.25)] * 0.7
    return air(reverb(out, impulse(2.2, 0.7, r), wet=0.28)[:n]), False


def whistle(r):
    """The referee: a pea whistle, 3 kHz, the pea trilling at ~34 Hz, breath
    around it, one long blast."""
    n = seconds(1.3)
    t = t_axis(n)
    blast = envelope(n, [(0, 0), (0.025, 1), (0.62, 0.95), (0.7, 0.0), (1.3, 0)])
    trill = 1 + 0.5 * np.sin(2 * np.pi * 34 * t)
    f = 2950 * (1 + 0.012 * np.sin(2 * np.pi * 34 * t))
    tone = np.sin(2 * np.pi * np.cumsum(f) / RATE) + 0.25 * np.sin(4 * np.pi * np.cumsum(f) / RATE)
    breath = band(r.standard_normal(n), 2200, 6500, slope=0.5) * 0.18
    x = (tone * trill + breath) * blast
    return reverb(x, impulse(1.6, 0.45, r), wet=0.3)[:n], False


def bell(freq: float, n: int, ratio: float = 1.4, index: float = 2.2, decay: float = 0.9) -> np.ndarray:
    t = t_axis(n)
    i = index * np.exp(-t / (decay * 0.5))
    return np.sin(2 * np.pi * freq * t + i * np.sin(2 * np.pi * freq * ratio * t)) * np.exp(-t / decay)


def chime(r):
    """The stadium PA's three-note chime, rising, with the bowl's slap echo."""
    n = seconds(2.8)
    out = np.zeros(n)
    for start, f in ((0.0, 783.99), (0.24, 1046.5), (0.48, 1318.5)):
        s = seconds(start)
        out[s:] += bell(f, n - s, ratio=2.0, index=1.2, decay=0.7) * np.minimum(1, t_axis(n - s) / 0.004)
    slap = np.zeros(n)
    d = seconds(0.31)
    slap[d:] = out[: n - d] * 0.35
    return reverb(out + slap, impulse(2.4, 0.8, r), wet=0.35)[:n], False


def horn(r):
    """End of a quarter: the scoreboard horn, a buzzing minor third, held."""
    n = seconds(3.0)
    t = t_axis(n)
    env = envelope(n, [(0, 0), (0.03, 1), (1.9, 0.95), (2.2, 0), (3.0, 0)])
    tone = np.zeros(n)
    for f, a in ((196.0, 1.0), (233.08, 0.8), (98.0, 0.4)):
        phase = 2 * np.pi * f * (1 + 0.002 * np.sin(2 * np.pi * 5.3 * t)) * t
        tone += a * (2 * ((phase / (2 * np.pi)) % 1) - 1)
    tone = band(tone, 70, 2600, slope=0.7) * env
    slap = np.zeros(n)
    d = seconds(0.29)
    slap[d:] = tone[: n - d] * 0.3
    return reverb(tone + slap, impulse(2.8, 0.9, r), wet=0.4)[:n], False


def rumble(r):
    """Into the red zone: the stands lean in - a low swell and the babble rising."""
    n = seconds(5.5)
    env = envelope(n, [(0, 0.1), (2.5, 0.8), (4.0, 1.0), (5.5, 0.0)])
    low = band(r.standard_normal(n), 28, 140, slope=0.7) * 2.0 * env
    body = crowd_body(n, r) * 0.6 * env + babble(n, r, voices=16, duty=0.75) * 0.5 * env
    stomps = claps(n, r, np.arange(1.5, 5.0, 0.62), people=40, jitter=0.03) * 0.25 * env
    return air(reverb(low + body + stomps, impulse(2.6, 0.9, r), wet=0.3)[:n]), False


def defense_swell(r):
    """Third down with the home side on defence: noise climbing to a wall,
    clapping on the beat, whistles over the top. No chant, no words."""
    n = seconds(7.5)
    env = envelope(n, [(0, 0.2), (3.0, 0.75), (5.5, 1.0), (7.0, 0.9), (7.5, 0)])
    x = crowd_body(n, r) * 1.0 * env + babble(n, r, voices=20, rate=(5, 9), duty=0.9) * 0.6 * env
    x += claps(n, r, np.arange(0.5, 7.2, 0.5), people=70, jitter=0.02) * 0.5 * env
    x += fan_whistles(n, r, count=12, when=(2.5, 7.0))
    x += shouts(n, r, count=40, loud=(0.2, 0.6), when=(2.0, 7.2))
    return air(reverb(x, impulse(2.6, 0.8, r), wet=0.33)[:n]), False


def final_cheer(r):
    """The home side won: the roar that does not stop, swell after swell."""
    n = seconds(11)
    env = envelope(n, [(0, 0), (0.4, 1.0), (3.0, 0.85), (4.5, 1.0), (7.5, 0.8), (11, 0.0)])
    x = crowd_body(n, r) * 1.1 * env + babble(n, r, voices=24, rate=(4, 8), duty=0.85) * 0.8 * env
    x += shouts(n, r, count=110, loud=(0.3, 1.0), when=(0.1, 9.0))
    x += fan_whistles(n, r, count=22, when=(0.2, 9.0))
    x += claps(n, r, np.sort(r.uniform(1.0, 10.0, 120)), people=6, jitter=0.01) * 0.6
    return air(reverb(x, impulse(2.8, 0.9, r), wet=0.3)[:n]), False


def exodus(r):
    """The visitors won: a deflated murmur, seats flipping up, feet on concrete."""
    n = seconds(9.5)
    env = envelope(n, [(0, 0.8), (3, 0.6), (9.5, 0.15)])
    x = crowd_body(n, r) * 0.25 * env + babble(n, r, voices=12, rate=(2.5, 4.5), duty=0.4) * 0.6 * env
    for _ in range(90):                                    # seat backs springing up
        i = int(r.integers(0, n - seconds(0.05)))
        k = seconds(0.03)
        x[i:i + k] += band(r.standard_normal(k * 6), 600, 3000)[:k] * np.exp(-t_axis(k) / 0.006) * r.uniform(0.1, 0.35)
    return air(reverb(x, impulse(2.4, 0.8, r), wet=0.4)[:n]), False


def fireworks(r):
    """Off the rim: launch thumps, the crack of each shell, crackle falling."""
    n = seconds(4.0)
    out = np.zeros(n)
    for k, at in enumerate((0.0, 0.35, 0.7, 1.05)):
        s = seconds(at)
        thump_n = seconds(0.25)
        out[s:s + thump_n] += np.sin(2 * np.pi * 70 * t_axis(thump_n)) * np.exp(-t_axis(thump_n) / 0.05) * 0.6
        bang = s + seconds(0.45)
        bang_n = seconds(0.5)
        if bang + bang_n < n:
            out[bang:bang + bang_n] += band(r.standard_normal(bang_n), 60, 3000, slope=0.8) * np.exp(-t_axis(bang_n) / 0.07)
        crackle_start = bang + seconds(0.12)
        for _ in range(220):
            i = crackle_start + seconds(abs(r.normal(0.5, 0.4)))
            m = seconds(0.004)
            if i + m < n:
                out[i:i + m] += r.standard_normal(m) * np.exp(-(i - crackle_start) / seconds(0.9)) * r.uniform(0.2, 0.7)
    # The show is over in under two seconds; what follows is its echo off the
    # stands, falling away - not a second of noise at the same level.
    out *= envelope(n, [(0, 1.0), (1.7, 1.0), (2.6, 0.25), (4.0, 0.02)])
    return reverb(out, impulse(2.4, 0.7, r), wet=0.3)[:n] * envelope(n, [(0, 1), (2.4, 0.6), (4.0, 0)]), False


SOUNDS = {
    "crowd_bed": (crowd_bed, "bed"), "clap_bed": (clap_bed, "bed"), "murmur_bed": (murmur_bed, "bed"),
    "wind_bed": (wind_bed, "bed"), "roar": (roar, "effect"), "cheer": (cheer, "effect"),
    "groan": (groan, "effect"), "sting": (sting, "effect"), "whistle": (whistle, "effect"),
    "chime": (chime, "effect"), "horn": (horn, "effect"), "rumble": (rumble, "effect"),
    "defense_swell": (defense_swell, "effect"), "final_cheer": (final_cheer, "effect"),
    "exodus": (exodus, "effect"), "fireworks": (fireworks, "effect"),
}


# ───────────────────────────── loudness and files ─────────────────────────────

def dbfs(x: float) -> float:
    return 20 * np.log10(max(1e-9, x))


def normalise(x: np.ndarray, rms_db: float, peak_db: float) -> np.ndarray:
    """RMS to the class target, then a soft limiter so no peak crosses the
    ceiling. A tanh knee, not a hard clip: a roar distorts nowhere."""
    x = x - np.mean(x)
    x *= 10 ** (rms_db / 20) / max(1e-9, np.sqrt(np.mean(x ** 2)))
    ceiling = 10 ** (peak_db / 20)
    return np.tanh(x / ceiling) * ceiling


def write_wav(path: pathlib.Path, x: np.ndarray) -> None:
    pcm = (np.clip(x, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())


def encode(wav: pathlib.Path, name: str) -> None:
    caf, ogg = OUT / f"{name}.caf", OUT / f"{name}.ogg"
    subprocess.run(["afconvert", "-f", "caff", "-d", "alac", str(wav), str(caf)], check=True)
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise SystemExit("ffmpeg is needed for the .ogg (Opus) twin: brew install ffmpeg")
    subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", str(wav), "-c:a", "libopus", "-b:a", "64k",
                    str(ogg)], check=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", choices=sorted(SOUNDS))
    args = ap.parse_args()
    loud = json.loads(TOKENS.read_text())["visual"]["audio"]["loudness"]
    OUT.mkdir(parents=True, exist_ok=True)
    manifest_path = OUT / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"sounds": {}}
    work = pathlib.Path(tempfile.mkdtemp(prefix="stadium-audio-"))
    try:
        for i, (name, (make, cls)) in enumerate(sorted(SOUNDS.items())):
            if args.only and name not in args.only:
                continue
            # A seed per sound, from its name: adding a sound never changes another.
            seed = sum(ord(c) * (k + 1) for k, c in enumerate(name))
            x, loop = make(rng(seed))
            x = normalise(x, loud["bedRms"] if cls == "bed" else loud["effectRms"], loud["peak"])
            wav = work / f"{name}.wav"
            write_wav(wav, x)
            encode(wav, name)
            manifest["sounds"][name] = {
                "class": cls, "loop": loop, "seconds": round(len(x) / RATE, 3),
                "rms": round(dbfs(float(np.sqrt(np.mean(x ** 2)))), 2),
                "peak": round(dbfs(float(np.max(np.abs(x)))), 2),
                "files": {"apple": f"actors/audio/{name}.caf", "portable": f"actors/audio/{name}.ogg"},
                "seed": seed, "made": "tools/audio/build.py",
            }
            print(f"{name:14s} {cls:6s} {len(x) / RATE:5.1f}s rms {manifest['sounds'][name]['rms']:6.1f} "
                  f"peak {manifest['sounds'][name]['peak']:5.1f} dBFS", flush=True)
        manifest["rate"] = RATE
        manifest["about"] = ("Synthesised by tools/audio/build.py; no recordings. Loudness is normalised per "
                             "class (visual.audio.loudness); the mix lives in visual.audio.gains.")
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
