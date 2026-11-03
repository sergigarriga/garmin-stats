"""Bucle original de música para stories y reels: afro house / lo-fi house a 120 bpm, compuesto por código.

    uv run --no-project --with numpy python marketing/marca/musica/afro_house.py [segundos]   # por defecto 9 s

Bombo a negras con pegada, palmas en 2 y 4, shaker en semicorcheas con swing, hi-hat abierto a contratiempo, congas
sincopadas, bajo a contratiempo con compresión lateral («sidechain») y un gancho de kalimba pegadizo con eco ping-pong
sobre La menor – Fa – Do – Sol. Sale `afro-house-120bpm.wav` (44,1 kHz, estéreo) con entrada y salida de 0,2 s;
el volumen final (−14 LUFS) lo pone quien lo usa (stories.py). Es música propia: se puede subir a Business Suite sin
problemas de derechos.
"""
from __future__ import annotations

import sys
import wave
from pathlib import Path

import numpy as np

SR = 44100
BPM = 120
BEAT = 60 / BPM
STEP = BEAT / 4                      # semicorchea
SWING = .14                          # retraso de las semicorcheas pares, en fracción de semicorchea
rng = np.random.default_rng(7)       # siempre el mismo ruido: el bucle sale idéntico cada vez

NOTE = {n: i for i, n in enumerate(["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"])}


def hz(name: str) -> float:
    """'A4' → 440 Hz."""
    n, o = name[:-1], int(name[-1])
    return 440 * 2 ** ((NOTE[n] + 12 * (o + 1) - 69) / 12)


def t_step(bar: int, step: int) -> float:
    return bar * 4 * BEAT + step * STEP + (SWING * STEP if step % 2 else 0)


def env(n: int, attack: float, decay: float) -> np.ndarray:
    t = np.arange(n) / SR
    return np.minimum(1, t / max(attack, 1e-4)) * np.exp(-t / decay)


def add(buf: np.ndarray, sig: np.ndarray, at: float, gain: float = 1, pan: float = 0) -> None:
    """Suma una señal mono en el instante `at` con ganancia y panorama (−1 izquierda, +1 derecha)."""
    i = int(at * SR)
    if i >= len(buf):
        return
    sig = sig[: len(buf) - i] * gain
    buf[i:i + len(sig), 0] += sig * np.sqrt((1 - pan) / 2)
    buf[i:i + len(sig), 1] += sig * np.sqrt((1 + pan) / 2)


def hp(x: np.ndarray, a: float = .92) -> np.ndarray:
    """Paso alto de un polo (para ruido de platos y shaker)."""
    y = np.empty_like(x)
    prev_x = prev_y = 0.0
    for i, v in enumerate(x):
        prev_y = a * (prev_y + v - prev_x)
        prev_x = v
        y[i] = prev_y
    return y


def lp(x: np.ndarray, a: float) -> np.ndarray:
    """Paso bajo de un polo (a cerca de 1 = más oscuro)."""
    y = np.empty_like(x)
    acc = 0.0
    for i, v in enumerate(x):
        acc = a * acc + (1 - a) * v
        y[i] = acc
    return y


# ------------------------------------------------------------------ instrumentos
def kick() -> np.ndarray:
    n = int(.42 * SR)
    t = np.arange(n) / SR
    f = 48 + 110 * np.exp(-t / .035)                   # barrido de tono: la pegada
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / .16)
    click = rng.standard_normal(n) * np.exp(-t / .002) * .18
    return np.tanh(1.6 * (body + click))


def clap() -> np.ndarray:
    n = int(.3 * SR)
    t = np.arange(n) / SR
    noise = hp(rng.standard_normal(n), .85)
    e = sum(np.exp(-np.clip(t - d, 0, None) / .006) * (t >= d) for d in (0, .011, .022)) + .5 * np.exp(-t / .09)
    return noise * e * .5


def shaker(accent: bool) -> np.ndarray:
    n = int(.07 * SR)
    noise = hp(hp(rng.standard_normal(n), .7), .7)
    return noise * env(n, .004, .018 if not accent else .028) * (.5 if accent else .3)


def open_hat() -> np.ndarray:
    n = int(.22 * SR)
    noise = hp(hp(rng.standard_normal(n), .6), .6)
    return noise * env(n, .002, .06) * .32


def conga(f: float) -> np.ndarray:
    n = int(.25 * SR)
    t = np.arange(n) / SR
    fr = f * (1 + .35 * np.exp(-t / .01))
    return np.sin(2 * np.pi * np.cumsum(fr) / SR) * np.exp(-t / .07) * .55


def kalimba(f: float, dur: float = .9) -> np.ndarray:
    """Pulsación tipo kalimba/marimba: fundamental + armónico inarmónico (×5,4) que muere rápido, y un toque de 2.º."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    s = (np.sin(2 * np.pi * f * t) * np.exp(-t / .32)
         + .28 * np.sin(2 * np.pi * 2 * f * t) * np.exp(-t / .12)
         + .22 * np.sin(2 * np.pi * 5.4 * f * t) * np.exp(-t / .025))
    return s * np.minimum(1, t / .002) * .5


def bass(f: float, dur: float) -> np.ndarray:
    n = int(dur * SR)
    t = np.arange(n) / SR
    s = np.sin(2 * np.pi * f * t) + .45 * np.sin(2 * np.pi * 2 * f * t) + .18 * np.sin(2 * np.pi * 3 * f * t)
    return np.tanh(1.4 * s) * env(n, .006, dur * .7) * .55


def pad(freqs: list[float], dur: float) -> np.ndarray:
    n = int(dur * SR)
    t = np.arange(n) / SR
    s = sum(np.sin(2 * np.pi * f * t + i) + .3 * np.sin(2 * np.pi * 2.003 * f * t) for i, f in enumerate(freqs))
    e = np.minimum(1, t / .08) * np.minimum(1, (dur - t) / .1)
    return s * e * .07


# ------------------------------------------------------------------ canción
CHORDS = [("A2", ["A3", "C4", "E4"]), ("F2", ["F3", "A3", "C4"]), ("C3", ["G3", "C4", "E4"]), ("G2", ["G3", "B3", "D4"])]
HOOK = [  # (compás dentro de la frase de 2, semicorchea, nota)
    (0, 0, "A4"), (0, 3, "C5"), (0, 6, "E5"), (0, 8, "D5"), (0, 10, "C5"), (0, 14, "A4"),
    (1, 0, "G4"), (1, 3, "A4"), (1, 6, "C5"), (1, 8, "E5"), (1, 11, "D5"), (1, 13, "C5"),
]
CONGA = [(3, 196), (7, 262), (10, 196), (11, 262), (14, 294)]


def song(seconds: float) -> np.ndarray:
    n = int(seconds * SR)
    drums, music, side = np.zeros((n, 2)), np.zeros((n, 2)), np.ones(n)
    bars = int(np.ceil(seconds / (4 * BEAT)))
    k, c, oh = kick(), clap(), open_hat()
    for bar in range(bars):
        root, chord = CHORDS[bar % 4]
        for b in range(4):
            at = bar * 4 * BEAT + b * BEAT
            add(drums, k, at, .95)
            i = int(at * SR)                                   # compresión lateral: todo lo demás se aparta
            dk = int(.2 * SR)
            if i < n:
                seg = 1 - .65 * np.exp(-np.arange(min(dk, n - i)) / SR / .07)
                side[i:i + len(seg)] = np.minimum(side[i:i + len(seg)], seg)
            if b in (1, 3):
                add(drums, c, at, .55, .05)
            add(drums, oh, at + 2 * STEP, .45, .25)
        for st in range(16):
            add(drums, shaker(st % 4 == 2), t_step(bar, st), .55, .55)
        for st, f in CONGA:
            add(drums, conga(f), t_step(bar, st), .8 if bar % 2 else .65, -.45)
        for st in (2, 6, 10, 13):                            # bajo a contratiempo
            add(music, bass(hz(root), STEP * (2.6 if st != 13 else 1.8)), t_step(bar, st), .9)
        add(music, pad([hz(x) for x in chord], 4 * BEAT), bar * 4 * BEAT, 1)
        for pb, st, note in HOOK:
            if pb == bar % 2:
                f = hz(note)
                if bar == 3 and st == 13:
                    f = hz("G5")                              # variación al final de la segunda vuelta
                add(music, kalimba(f), t_step(bar, st), 1.0, -.15)
                # eco ping-pong de corchea con puntillo, cada vez más bajo
                for r, (g, p) in enumerate([(.34, .7), (.2, -.7), (.11, .7)], 1):
                    add(music, lp(kalimba(f), .55), t_step(bar, st) + r * 3 * STEP, g * 1.6, p)
    music *= side[:, None]
    mix = drums + music
    mix = np.tanh(1.1 * mix) / np.tanh(1.1)
    fade = int(.2 * SR)                                       # entrada y salida suaves de 0,2 s
    mix[:fade] *= np.linspace(0, 1, fade)[:, None]
    mix[-fade:] *= np.linspace(1, 0, fade)[:, None]
    return mix / np.max(np.abs(mix)) * .89


def write(seconds: float = 9.0) -> Path:
    out = Path(__file__).with_name("afro-house-120bpm.wav")
    pcm = (song(seconds) * 32767).astype("<i2")
    with wave.open(str(out), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    return out


def main() -> None:
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 9.0
    print(write(seconds), f"{seconds:g} s")


if __name__ == "__main__":
    main()
