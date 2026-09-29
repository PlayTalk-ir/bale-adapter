"""Synthesize the brag soundtrack: music + SFX in A minor, one mix, 48 kHz stereo WAV."""

import wave

import numpy as np

SR = 48000
DUR = 21.0
N = int(SR * DUR)
BPM = 112.5
BEAT = 60 / BPM
BAR = 4 * BEAT
rng = np.random.default_rng(7)


def hz(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)


def lowpass(x, cutoff, order=2):
    spec = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    spec *= 1 / np.sqrt(1 + (f / cutoff) ** (2 * order))
    return np.fft.irfft(spec, len(x))


def highpass(x, cutoff, order=2):
    spec = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    spec *= 1 / np.sqrt(1 + (cutoff / np.maximum(f, 1e-3)) ** (2 * order))
    return np.fft.irfft(spec, len(x))


def env(n, a, d, sustain_level=0.0, release=None):
    t = np.arange(n) / SR
    e = np.where(t < a, t / max(a, 1e-4), sustain_level + (1 - sustain_level) * np.exp(-(t - a) / d))
    if release:
        e *= np.clip((n / SR - t) / release, 0, 1)
    return e


L = np.zeros(N)
R = np.zeros(N)


def add(sig, t0, gain=1.0, pan=0.0):
    i = int(t0 * SR)
    if i >= N:
        return
    sig = sig[: N - i]
    l, r = np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)
    L[i:i + len(sig)] += sig * gain * l * np.sqrt(2)
    R[i:i + len(sig)] += sig * gain * r * np.sqrt(2)


def tone(freq, dur, harmonics=(1.0,), detune=0.0):
    t = np.arange(int(dur * SR)) / SR
    out = np.zeros_like(t)
    for k, amp in enumerate(harmonics, start=1):
        out += amp * np.sin(2 * np.pi * freq * k * t * (1 + detune))
    return out


# Am  F  C  G  (roots as MIDI)
CHORDS = [
    (57, [57, 60, 64, 69]),
    (53, [53, 57, 60, 65]),
    (48, [55, 60, 64, 67]),
    (55, [55, 59, 62, 67]),
]
MUSIC_START_FULL = 3.2
OUTRO = 18.2

# ---------- pad ----------
bars = int(np.ceil(OUTRO / BAR))
for b in range(bars):
    t0 = b * BAR
    root, notes = CHORDS[b % 4]
    dur = min(BAR + 0.4, OUTRO + 0.3 - t0)
    if dur <= 0:
        break
    n = int(dur * SR)
    for i, m in enumerate(notes):
        for det, pan in ((-0.003, -0.5), (0.003, 0.5)):
            s = tone(hz(m), dur, harmonics=(1, 0.35, 0.18, 0.08), detune=det)
            s *= env(n, 0.35, 99, 1.0, release=0.45)
            add(s, t0, 0.028, pan)

# final Am chord, long tail
n = int((DUR - OUTRO) * SR)
for m in (45, 57, 60, 64, 69, 72):
    for det, pan in ((-0.003, -0.4), (0.003, 0.4)):
        s = tone(hz(m), DUR - OUTRO, harmonics=(1, 0.3, 0.12), detune=det) * env(n, 0.05, 1.8, 0.0)
        add(s, OUTRO, 0.034, pan)

# ---------- pluck arpeggio ----------
def pluck(freq, dur=0.45):
    n = int(dur * SR)
    s = tone(freq, dur, harmonics=(1, 0.5, 0.25, 0.12)) * env(n, 0.004, 0.16)
    return s

step = BEAT / 2
t = 0.0
k = 0
while t < OUTRO - 0.05:
    b = int(t // BAR)
    _, notes = CHORDS[b % 4]
    pattern = [0, 2, 1, 3, 2, 1, 3, 2]
    m = notes[pattern[k % 8]] + 12
    sparse = t < MUSIC_START_FULL
    if not sparse or k % 2 == 0:
        add(pluck(hz(m)), t, 0.07 if not sparse else 0.055, 0.35 if k % 2 else -0.35)
    t += step
    k += 1

# ---------- drums + bass (full section) ----------
def kick():
    dur = 0.35
    tt = np.arange(int(dur * SR)) / SR
    f = 45 + 75 * np.exp(-tt / 0.03)
    ph = 2 * np.pi * np.cumsum(f) / SR
    return np.sin(ph) * np.exp(-tt / 0.12)


def hat():
    n = int(0.06 * SR)
    s = highpass(rng.standard_normal(n), 7000)
    return s * env(n, 0.001, 0.015)


def bass(freq, dur):
    n = int(dur * SR)
    s = np.tanh(1.6 * tone(freq, dur, harmonics=(1, 0.25))) * env(n, 0.005, 0.25, 0.4, release=0.05)
    return lowpass(s, 900)


beat_t = MUSIC_START_FULL
i = 0
while beat_t < OUTRO - 0.01:
    add(kick(), beat_t, 0.2)
    add(hat(), beat_t + BEAT / 2, 0.035, 0.3)
    b = int(beat_t // BAR)
    root = CHORDS[b % 4][0]
    add(bass(hz(root - 12), BEAT * 0.9), beat_t, 0.11)
    beat_t += BEAT
    i += 1
add(kick(), OUTRO, 0.22)
add(bass(hz(45 - 12 + 12), 2.0), OUTRO, 0.1)

# ---------- SFX (A minor pentatonic, sit under the music) ----------
PENTA = [81, 84, 86, 88, 91, 93]  # A5 C6 D6 E6 G6 A6


def blip(freq):
    dur = 0.18
    tt = np.arange(int(dur * SR)) / SR
    f = freq * (1 + 0.25 * np.exp(-tt / 0.012))
    s = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-tt / 0.05)
    return s * np.clip(tt / 0.003, 0, 1)


def tick():
    n = int(0.02 * SR)
    return lowpass(highpass(rng.standard_normal(n), 2500), 6000) * env(n, 0.0005, 0.004)


def chime(midis, spread=0.07):
    out = np.zeros(int(1.2 * SR))
    for j, m in enumerate(midis):
        n = int((1.2 - j * spread) * SR)
        s = tone(hz(m), 1.2 - j * spread, harmonics=(1, 0.0, 0.2, 0.0, 0.08)) * env(n, 0.003, 0.35)
        o = int(j * spread * SR)
        out[o:o + n] += s
    return out


def whoosh(dur=0.45):
    n = int(dur * SR)
    noise = rng.standard_normal(n)
    parts = np.array_split(noise, 12)
    out = np.concatenate([lowpass(p, 600 + 5000 * (i / 11)) for i, p in enumerate(parts)])
    tt = np.linspace(0, 1, n)
    return out * np.sin(np.pi * tt) ** 2


def riser(dur=0.6):
    n = int(dur * SR)
    tt = np.arange(n) / SR
    f = hz(69) * 2 ** (tt / dur)
    s = np.sin(2 * np.pi * np.cumsum(f) / SR)
    return s * (tt / dur) ** 2


def click():
    n = int(0.05 * SR)
    tt = np.arange(n) / SR
    s = lowpass(rng.standard_normal(n), 3000) * np.exp(-tt / 0.004)
    s += 0.6 * np.sin(2 * np.pi * 180 * tt) * np.exp(-tt / 0.02)
    return s


# scene 1: bubble blips
for i in range(6):
    add(blip(hz(PENTA[i])), 0.25 + i * 0.36 + 0.03, 0.09, 0.4)

# transitions
for tt in (2.95, 6.55, 10.4, 14.4, 17.95):
    add(whoosh(), tt, 0.035)
add(riser(0.6), 2.6, 0.03)

# typing ticks (≈ every third character)
for a, b_, chars in ((7.3, 8.35, 44), (10.8, 12.25, 96)):
    for c in range(0, chars, 3):
        add(tick(), a + (b_ - a) * c / chars + rng.uniform(-0.004, 0.004), 0.05, rng.uniform(-0.2, 0.2))
# output lines
for i in range(5):
    add(tick(), 8.6 + i * 0.13, 0.06)
for i in range(3):
    add(tick(), 12.45 + i * 0.22, 0.06)

add(blip(hz(76)), 9.5, 0.05)             # row highlight
add(chime([81, 88]), 12.89, 0.06)        # dry-run ok
add(click(), 16.2, 0.12)                 # human click
add(chime([81, 84, 88, 93]), 16.55, 0.07)  # really sent
add(blip(hz(88)), 16.95, 0.04)           # notice

# ---------- master ----------
mix = np.stack([L, R], axis=1)
fade_in = np.clip(np.arange(N) / (0.02 * SR), 0, 1)
fade_out = np.clip((N - np.arange(N)) / (1.2 * SR), 0, 1)
mix *= (fade_in * fade_out)[:, None]
peak = np.max(np.abs(mix))
mix = np.tanh(mix / peak * 1.2) / np.tanh(1.2) * 0.89
pcm = (mix * 32767).astype(np.int16)
with wave.open("audio.wav", "wb") as w:
    w.setnchannels(2)
    w.setsampwidth(2)
    w.setframerate(SR)
    w.writeframes(pcm.tobytes())
print("peak before norm", round(float(peak), 3))
