#!/usr/bin/env python3
"""Soundtrack for the WebCoder promo film: music bed cut to the scene table + synthesised cues.

Everything here is driven by the same scene table `T` as film.html, so a cue lands on the
frame that triggers it.  At 120 bpm one bar is exactly 2 s, which is why every scene boundary
(8, 24, 48, 64, 80, 114 ...) sits on a bar line; the music bed is spliced from a 120 bpm
track at bar boundaries so section changes in the music coincide with scene changes.

    python3 score.py <track-name> [out.wav]       # writes a 120 s 48 kHz stereo wav
    python3 score.py --cues cues.wav              # synthesised cues only (for checking)

Tracks (Kevin MacLeod, incompetech.com, CC BY 4.0) live in assets/music/<name>.mp3; the
script expects a 48 kHz stereo wav next to it, time-stretched to exactly 120 bpm:

    ffmpeg -i assets/music/Inspired.mp3 -ac 2 -ar 48000 assets/music/Inspired_120.wav

The film uses 'Inspired'.  The other two entries are the alternates that were auditioned.
"""
import os, sys, json, numpy as np
import scipy.io.wavfile as wf
import scipy.signal as sg

SR = 48000
DUR = 120.0
BAR = 2.0                     # 120 bpm
HERE = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------- scene table (= film.html)
T = dict(s1=(0, 8), s2=(8, 12.5), s3=(12.5, 24), s4a=(24, 31.5), s4b=(31.5, 40), s5=(40, 48),
         s6=(48, 57), s7=(57, 64), s8a=(64, 72), s8b=(72, 80), s9=(80, 85.5),
         s10a=(85.5, 93), s10b=(93, 98.5), s11=(98.5, 114), s12=(114, 120))

# ---------------------------------------------------------------- music edit decision lists
# (film_start_s, source_bar, n_bars): copy n bars starting at source bar k (k=0 is the first
# downbeat) so they start at film_start.  `hit` is the source bar whose downbeat is the final
# chord; it is placed at 114.0 (the title card) and rings out to the end.
TRACKS = {
    # 4:46, corporate/uplifting.  0-39 no hats, 40-51 hats, 104-119 densest, 120-135 thinner
    # outro section, final chord at bar 136.
    'Inspired': dict(downbeat=0.485, hit=136, edl=[
        (0, 0, 4), (8, 4, 20), (48, 40, 8), (64, 104, 9), (82, 120, 16)]),
    # 3:04 at 122.45 bpm, stretched to 120.  Bass leaves at 20, hats build 24-31 without bass,
    # drop at 32, climax phrase 78-84, final crash + pad at 85.
    'Delightful D': dict(downbeat=0.400 / 0.98, hit=85, edl=[
        (0, 0, 4), (8, 4, 8), (24, 12, 8), (40, 20, 4), (48, 24, 8), (64, 32, 8),
        (80, 64, 8), (96, 76, 2), (100, 78, 7)]),
    # 2:12, 80s arpeggiator.  8-bar phrases from bar 8: full 8-15, break 16-23, full 24-31,
    # break 32-39, full 40-47, break 48-55, full 56-63; it stops dead at 63.4, so the ending is
    # the re-entry of the full section at 114 followed by a fade.
    'Nowhere Land': dict(downbeat=0.715, hit=None, edl=[
        (0, 4, 4), (8, 8, 8), (24, 16, 8), (40, 32, 4), (48, 24, 8), (64, 40, 8),
        (80, 56, 8), (96, 48, 7), (110, 54, 1), (112, 55, 1), (114, 56, 3)]),
}


def smooth_edges(x, n):
    """Half-sine ramps of n samples at both ends (equal-power when two pieces overlap)."""
    r = np.sin(np.linspace(0, np.pi / 2, n))[:, None]
    x[:n] *= r
    x[-n:] *= r[::-1]
    return x


def add_at(out, p, piece):
    """out[p:] += piece, clipping at both ends (p may be slightly negative at film start)."""
    if p < 0:
        piece, p = piece[-p:], 0
    n = min(len(piece), len(out) - p)
    out[p:p + n] += piece[:n]


def build_music(name):
    sr, src = wf.read(os.path.join(HERE, 'assets', 'music', f'{name}_120.wav'))
    assert sr == SR
    src = src.astype(np.float32) / 32768
    cfg = TRACKS[name]
    out = np.zeros((int(DUR * SR) + SR * 10, 2), np.float32)
    xf = int(0.012 * SR)                      # 12 ms splice ramps
    for film_t, bar, n in cfg['edl']:
        a = int((cfg['downbeat'] + bar * BAR) * SR) - xf // 2
        b = a + int(n * BAR * SR) + xf
        piece = smooth_edges(src[a:b].copy(), xf)
        add_at(out, int(film_t * SR) - xf // 2, piece)
    if cfg['hit'] is not None:
        a = int((cfg['downbeat'] + cfg['hit'] * BAR) * SR) - xf // 2
        piece = src[a:a + int(6.5 * SR)].copy()
        piece[:xf] *= np.sin(np.linspace(0, np.pi / 2, xf))[:, None]
        add_at(out, int(114.0 * SR) - xf // 2, piece)
    out = out[:int(DUR * SR)]
    t = np.arange(len(out)) / SR
    env = np.clip(t / 0.4, 0, 1) * np.clip((DUR - t) / 2.5, 0, 1)   # fade in 0.4 s, out 2.5 s
    return out * env[:, None]


# ---------------------------------------------------------------- cue synthesis
def place(buf, t, x, gain=1.0):
    p = int(t * SR)
    n = min(len(x), len(buf) - p)
    if n > 0:
        buf[p:p + n] += x[:n, None] * gain


def env_ad(n, a, d):
    """Attack/decay envelope in samples."""
    e = np.ones(n)
    e[:a] = np.linspace(0, 1, a)
    e[a:] = np.exp(-np.arange(n - a) / d)
    return e


def click(rng, bright=4000):
    """Keyboard click: 8 ms of band-passed noise."""
    n = int(0.008 * SR)
    x = rng.standard_normal(n) * env_ad(n, 20, n / 3)
    b, a = sg.butter(2, [bright * 0.6 / (SR / 2), min(bright * 1.6, 20000) / (SR / 2)], 'band')
    return sg.lfilter(b, a, x)


def tick(f=2600, n_ms=18):
    n = int(n_ms / 1000 * SR)
    t = np.arange(n) / SR
    return np.sin(2 * np.pi * f * t) * env_ad(n, 8, n / 4)


def pop(f, n_ms=70):
    n = int(n_ms / 1000 * SR)
    t = np.arange(n) / SR
    return np.sin(2 * np.pi * (f * (1 + 0.3 * np.exp(-t * 120))) * t) * env_ad(n, 40, n / 3)


def bell(f, dur=1.6, gain=1.0):
    n = int(dur * SR)
    t = np.arange(n) / SR
    x = (np.sin(2 * np.pi * f * t) * np.exp(-t * 2.2)
         + 0.4 * np.sin(2 * np.pi * f * 2.0 * t) * np.exp(-t * 4)
         + 0.25 * np.sin(2 * np.pi * f * 3.01 * t) * np.exp(-t * 6))
    x[:200] *= np.linspace(0, 1, 200)
    return x * gain


def two_tone(f1, f2):
    """Soft 'done' chime: two short notes."""
    a, b = bell(f1, 0.5), bell(f2, 0.9)
    x = np.zeros(len(b) + int(0.09 * SR))
    x[:len(a)] += a
    x[int(0.09 * SR):] += b
    return x * 0.8


def whoosh(rng, dur=0.45, up=True):
    n = int(dur * SR)
    x = rng.standard_normal(n)
    f0, f1 = (300, 5000) if up else (5000, 300)
    fc = np.geomspace(f0, f1, n)
    # time-varying band-pass: new coefficients every 10 ms, filter state carried across blocks
    out = np.zeros(n)
    blk = 480
    zi = None
    for i in range(0, n, blk):
        c = fc[min(i, n - 1)]
        sos = sg.butter(2, [c * 0.7 / (SR / 2), min(c * 1.4, 22000) / (SR / 2)], 'band', output='sos')
        if zi is None:
            zi = sg.sosfilt_zi(sos) * 0
        out[i:i + blk], zi = sg.sosfilt(sos, x[i:i + blk], zi=zi)
    return out * np.sin(np.linspace(0, np.pi, n)) ** 1.5


def riser(dur):
    """Filtered noise + rising tone, for the anchor curve build-up."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    rng = np.random.default_rng(7)
    noise = rng.standard_normal(n)
    b, a = sg.butter(2, 1800 / (SR / 2), 'high')
    noise = sg.lfilter(b, a, noise) * (t / dur) ** 2.5
    tone = np.sin(2 * np.pi * np.cumsum(np.geomspace(220, 880, n)) / SR) * (t / dur) ** 2 * 0.5
    return (noise * 0.35 + tone) * 0.6


def build_cues():
    buf = np.zeros((int(DUR * SR), 2), np.float32)
    rng = np.random.default_rng(42)
    PENTA = [523.25, 587.33, 659.25, 783.99, 880.0, 1046.5, 1174.7, 1318.5, 1568.0, 1760.0]

    # S1: the request is typed 0.6-3.6 s, five capability chips pop at 3.8 + 0.28 i
    t = 0.6
    while t < 3.55:
        place(buf, t, click(rng, rng.uniform(3000, 5000)), 0.5 * rng.uniform(0.6, 1))
        t += rng.uniform(0.05, 0.11)
    for i in range(5):
        place(buf, 3.8 + 0.28 * i + 0.3, pop(PENTA[i + 2]), 0.22)
    place(buf, 5.6, pop(392, 120), 0.12)

    # S3: code is typed 13.0-17.7, terminal lines 17.9-19.9, browser flips at 20.1
    t = 13.0
    while t < 17.6:
        place(buf, t, click(rng, rng.uniform(2500, 4500)), 0.22 * rng.uniform(0.5, 1))
        t += rng.uniform(0.045, 0.1)
    for i in range(7):
        place(buf, 17.9 + 2.0 * i / 7, tick(1800, 25), 0.16)
    place(buf, 20.1, two_tone(659.25, 987.77), 0.16)

    # S4a: 27 checklist items appear 24.9-28.6, the RS comparison at 29.4
    for k in range(1, 28):
        place(buf, 24.9 + 3.7 * k / 27, tick(2600 + 20 * k, 16), 0.2)
    place(buf, 29.4, two_tone(587.33, 880.0), 0.2)

    # S6: anchor curve draws 48.6-53.0, +66.2 % lands at 53.2
    place(buf, 48.6, riser(4.6), 0.2)
    place(buf, 53.2, bell(1046.5, 2.2), 0.22)
    place(buf, 53.2, bell(523.25, 2.2), 0.12)

    # S7: counts 57.4-59.6, dots light 59.8-62.4
    for i in range(22):
        place(buf, 59.8 + 2.6 * i / 22, tick(2200, 14), 0.1)

    # S8a/S8b/S9: result bars grow; +21.3 lands at 75.4
    for t0, n in ((64.4, 6), (72.4, 6), (80.3, 4)):
        for i in range(n):
            place(buf, t0 + 0.12 * i, whoosh(rng, 0.9, True), 0.07)
    place(buf, 75.4, bell(1046.5, 2.0), 0.2)
    place(buf, 75.4, bell(659.25, 2.0), 0.1)

    # S10b: 24 wall tiles pop at 93.3 + 0.07 i -> ascending pentatonic run
    for i in range(24):
        place(buf, 93.3 + 0.07 * i, pop(PENTA[i % 10] * (2 if i >= 10 else 1), 90), 0.1)

    # S11: a requirement lights up when the live app reaches it (MARKS in film.html, clip starts at 1.4 s)
    for m in (3.02, 5.37, 7.58, 9.31, 11.02, 12.74, 15.27):
        place(buf, 98.5 + m - 1.4, two_tone(783.99, 1174.7), 0.08)

    # S12: title card
    place(buf, 114.0, bell(523.25, 4.0), 0.16)
    place(buf, 114.0, bell(783.99, 4.0), 0.12)
    place(buf, 114.0, bell(1046.5, 4.0), 0.1)

    # scene transitions: a short whoosh ending on the cut
    major = {8, 24, 48, 64, 85.5, 98.5, 114}
    for a, b in T.values():
        if b >= DUR:
            continue
        g = 0.16 if b in major else 0.08
        place(buf, b - 0.42, whoosh(rng, 0.5, b in major), g)
    return buf


def main():
    if sys.argv[1] == '--cues':
        cues = build_cues()
        wf.write(sys.argv[2], SR, (np.clip(cues, -1, 1) * 32767).astype(np.int16))
        return
    name = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else f'/tmp/{name}_mix.wav'
    music = build_music(name)
    music *= 0.89 / np.abs(music).max()
    cues = build_cues()
    mix = music + cues * 0.9
    peak = np.abs(mix).max()
    if peak > 0.98:
        mix *= 0.98 / peak
    wf.write(out, SR, (mix * 32767).astype(np.int16))
    wf.write(out.replace('_mix', '_music'), SR, (music * 32767).astype(np.int16))
    print(f'{name}: wrote {out}  peak={np.abs(mix).max():.3f}')


if __name__ == '__main__':
    main()
