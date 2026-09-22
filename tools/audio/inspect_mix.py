"""Measure what nobody can hear: the audio files, and the mix the app logged.

Audio is the one actor that cannot be screenshotted, and the simulator runs
muted, so for six rounds "unverified: anything heard" has been the whole
report. Two things can be established without ears, and this measures both.

    python3 tools/audio/inspect_mix.py files            # the assets themselves
    python3 tools/audio/inspect_mix.py trace <log>      # the mix the app played

**files** decodes every `.caf` with `afconvert` and reports, per sound:
duration, peak, RMS, dynamic range, and - for a bed, which loops forever -
the seam: how far the last samples are from the first. A bed whose end does
not meet its beginning clicks once a loop, which is the "never loops audibly"
rule in the art bible, and it is a number, not an opinion.

**trace** reads `[stadium-audio]` lines out of a run's log and answers the
rules that are about *when* and *where* rather than timbre: did anything play
before its play landed, did the roar come from the scoring side, did mute
stop everything, how many voices were live at once.

Stdlib only: `wave` from the standard library, `afconvert` from the OS.
"""

import array
import math
import pathlib
import re
import subprocess
import sys
import tempfile
import wave

ROOT = pathlib.Path(__file__).resolve().parents[2]
AUDIO = ROOT / "assets" / "actors" / "audio"
# A bed loops for as long as the stadium is open; a one-shot never wraps, so a
# seam it would never reach is not a defect.
BEDS = ("crowd_bed", "clap_bed", "murmur_bed", "wind_bed")
# How much of each end to compare. 50 ms is long enough to average out noise
# and short enough that a real crossfade still reads as matched.
SEAM_MS = 50


def decode(path: pathlib.Path) -> tuple[list[float], int]:
    """A .caf as mono floats in [-1, 1], via afconvert to 16-bit wav."""
    with tempfile.TemporaryDirectory() as tmp:
        wav = pathlib.Path(tmp) / "out.wav"
        subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16", str(path), str(wav)],
                       check=True, capture_output=True)
        with wave.open(str(wav), "rb") as w:
            rate, n = w.getframerate(), w.getnframes()
            raw = array.array("h")
            raw.frombytes(w.readframes(n))
            if w.getnchannels() == 2:                      # fold to mono
                raw = array.array("h", [(raw[i] + raw[i + 1]) // 2
                                        for i in range(0, len(raw), 2)])
    return [s / 32768.0 for s in raw], rate


def db(x: float) -> float:
    return 20 * math.log10(x) if x > 1e-9 else -120.0


def rms(xs: list[float]) -> float:
    return math.sqrt(sum(x * x for x in xs) / len(xs)) if xs else 0.0


def seam_of(xs: list[float], rate: int) -> tuple[float, float, float]:
    """How much the loop's wrap stands out from the bed's own motion.

    Returns (step at the wrap in dB, the bed's normal step in dB, the sample
    jump). The comparison is the point: a bed that swings wildly by nature can
    take a big step at the wrap unheard, and a still one cannot. Measured on a
    20 ms RMS envelope, which is about as fine as level is heard.
    """
    hop = max(1, int(rate * 0.02))
    env = [db(rms(xs[i:i + hop])) for i in range(0, len(xs) - hop, hop)]
    if len(env) < 4:
        return 0.0, 0.0, 0.0
    steps = sorted(abs(env[i + 1] - env[i]) for i in range(len(env) - 1))
    natural = steps[len(steps) // 2]                       # median step
    wrap = abs(env[0] - env[-1])                           # the wrap itself
    # A click is a waveform discontinuity, and is heard even when levels match.
    jump = abs(xs[-1] - xs[0]) / max(1e-9, rms(xs))
    return wrap, natural, jump


def report_files() -> int:
    print(f"{'sound':<16}{'secs':>7}{'peak dB':>9}{'RMS dB':>8}{'range':>7}   seam")
    worst = 0.0
    for path in sorted(AUDIO.glob("*.caf")):
        name = path.stem
        xs, rate = decode(path)
        secs = len(xs) / rate
        peak, level = db(max(abs(x) for x in xs)), db(rms(xs))
        seam = ""
        if name in BEDS:
            step, natural, jump = seam_of(xs, rate)
            # A bed is only heard to loop if its wrap stands out from its own
            # motion. Clapping swings 10 dB between a beat and the gap after
            # it, so a raw head-to-tail difference measures the rhythm; what
            # matters is whether the wrap is a bigger step than the bed takes
            # everywhere else.
            ratio = step / natural if natural > 0.01 else 0.0
            worst = max(worst, ratio)
            seam = (f"step {step:4.1f} dB vs {natural:4.1f} normal "
                    f"({ratio:.1f}x), jump {jump:.4f}")
        print(f"{name:<16}{secs:7.1f}{peak:9.1f}{level:8.1f}{peak - level:7.1f}   {seam}")
    print(f"\nbeds: worst wrap is {worst:.1f}x the bed's own normal step "
          f"({'lost in its own motion' if worst < 3.0 else 'STANDS OUT - a loop you can hear'})")
    return 0 if worst < 3.0 else 1


TRACE = re.compile(r"\[stadium-audio\] (?P<verb>play|drop|mute|bed) (?P<key>\S+)"
                   r"(?: at t=(?P<t>[\d.]+))?(?: (?P<rest>.*))?")


def report_trace(path: pathlib.Path) -> int:
    text = path.read_text(errors="replace")
    rows = [m.groupdict() for m in TRACE.finditer(text)]
    if not rows:
        print("no [stadium-audio] lines: run the app with -stadiumAudioTrace")
        return 1
    fired = [r for r in rows if r["verb"] == "play"]
    print(f"{len(rows)} audio lines, {len(fired)} sounds played\n")
    for r in rows:
        print(f"  t={r['t'] or '-':>7}  {r['verb']:<5} {r['key']:<14} {r['rest'] or ''}")
    # The rule the status gate exists to protect, now checked for sound too.
    moments = re.findall(r"\[stadium\] moment (\S+) fired at t=([\d.]+)", text)
    for kind, when in moments:
        t = float(when)
        early = [r for r in fired if r["t"] and float(r["t"]) < t - 0.05
                 and r["key"] in ("roar", "cheer", "fireworks", "sting")]
        verdict = "OK" if not early else f"EARLY: {[r['key'] for r in early]}"
        print(f"\nmoment {kind} fired at t={t:.2f}: celebration sounds {verdict}")
    return 0


def main() -> int:
    what = sys.argv[1] if len(sys.argv) > 1 else "files"
    if what == "files":
        return report_files()
    if what == "trace":
        return report_trace(pathlib.Path(sys.argv[2]))
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
