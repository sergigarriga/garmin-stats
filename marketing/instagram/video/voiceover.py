"""Voz, música, efectos y subtítulos para un Reel, a partir de un guion (<nombre>.voz.json).

Uso:
  uv run --no-project --with piper-tts --with numpy python marketing/instagram/video/voiceover.py \
      marketing/instagram/video/showreel.voz.json

Genera en marketing/instagram/out/video/:
  <nombre>-voz.wav       la voz: Amazon Polly ("voice": "polly:Lucia:generative:eu-central-1", natural, con la cuenta de
                         AWS) o Piper ("voice": "es_ES-davefx-medium", sin conexión, más robótica)
  <nombre>-musica.wav    base musical compuesta por código (sin derechos de autor) + efectos sincronizados
  <nombre>.captions.json subtítulos en trozos de 2-5 palabras con el tiempo de cada palabra (los pinta render_video.py)
  <nombre>.timing.json   sincronía voz-animación (la usa render_video.py)
  <nombre>.srt           subtítulos en archivo aparte

Guion: {"anim_duration", "lead", "tail", "bpm", "music" ("house" = base actual de Reels; si no, el groove suave), "voice", "tempo", "lines": [{"scene", "text", "say"?}], "sfx": [{"t", "type", "pitch"?}]}
  Todo el guion se graba en UNA toma (entonación natural, como habla una persona). Cada parte lleva "scene": el segundo
  de la animación en el que empieza su escena; la animación espera a la voz (timewarp.py). El vídeo dura lo que la voz.
  text = lo que sale en el subtítulo; say = cómo debe pronunciarlo la voz (p. ej. "Ranch" para que suene bien "Runch").
  Los efectos (sfx) van en segundos de animación. tempo = acelera la voz sin cambiar el tono (1,1 suena a creador de
  contenido). anim_duration = duración de la animación; lead/tail = silencio antes y cierre después de la voz.
  Efectos: whoosh, pop, tick, ding, stamp, swell, sparkle.
"""

from __future__ import annotations

import hashlib
import json
import sys
import subprocess
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "out" / "video"
SR = 44100
CACHE = Path.home() / ".cache" / "runch-tts"
VOICES = "https://huggingface.co/rhasspy/piper-voices/resolve/main/{lang}/{loc}/{name}/{q}/{loc}-{name}-{q}.onnx"


# ---------------------------------------------------------------- voz
def voice_model(voice: str) -> Path:
    loc, name, q = voice.split("-")
    path = CACHE / f"{voice}.onnx"
    if not path.exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        url = VOICES.format(lang=loc.split("_")[0], loc=loc, name=name, q=q)
        for ext in ("", ".json"):  # curl usa los certificados del sistema (en redes con proxy, urllib falla)
            subprocess.run(["curl", "-sSfL", "-o", str(path) + ext, url + ext], check=True)
    return path


def polly(text: str, voice: str) -> tuple[np.ndarray, list[tuple[float, str]] | None]:
    """Voz de Amazon Polly con la cuenta de AWS configurada (perfil por defecto). voice = "polly:Lucia:generative:eu-central-1".
    Devuelve el audio a 44,1 kHz y, si el motor lo permite (neural, long-form), el inicio de cada palabra."""
    _, vid, engine, region = voice.split(":")
    # caché por voz + texto: repetir un vídeo no vuelve a pagar a Polly (solo las frases que cambian)
    key = hashlib.sha1(f"{voice}|{text}".encode()).hexdigest()[:16]
    mp3 = CACHE / "polly" / f"{key}.mp3"
    base = ["aws", "polly", "synthesize-speech", "--region", region, "--engine", engine, "--voice-id", vid, "--text", text]
    if not mp3.exists():
        mp3.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(base + ["--output-format", "mp3", "--sample-rate", "24000", str(mp3)], check=True, capture_output=True)
        print(f"  Polly: {len(text)} caracteres")
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(mp3), "-f", "s16le", "-ac", "1", "-ar", str(SR), "-"],
                         check=True, capture_output=True).stdout
    audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768
    marks = None
    if engine != "generative":  # el motor generativo no da marcas de palabra
        mk = OUT / "_marks.json"
        subprocess.run(base + ["--output-format", "json", "--speech-mark-types", "word", str(mk)], check=True, capture_output=True)
        marks = [(json.loads(x)["time"] / 1000, json.loads(x)["value"]) for x in mk.read_text().splitlines() if x.strip()]
        mk.unlink()
    return audio, marks


def synth(text: str, voice: str, speed: float) -> np.ndarray:
    from piper import PiperVoice, SynthesisConfig
    v = PiperVoice.load(str(voice_model(voice)))
    tmp = OUT / "_line.wav"
    with wave.open(str(tmp), "wb") as w:
        v.synthesize_wav(text, w, syn_config=SynthesisConfig(length_scale=speed))
    with wave.open(str(tmp)) as w:
        sr, data = w.getframerate(), np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    tmp.unlink()
    # a 44,1 kHz
    x = np.linspace(0, len(data) - 1, int(len(data) * SR / sr))
    return np.interp(x, np.arange(len(data)), data)


def tempo(x: np.ndarray, factor: float) -> np.ndarray:
    raw = (np.clip(x, -1, 1) * 32767).astype("<i2").tobytes()
    out = subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "s16le", "-ar", str(SR), "-ac", "1", "-i", "-", "-filter:a", f"atempo={factor}",
                          "-f", "s16le", "-"], input=raw, check=True, capture_output=True).stdout
    return np.frombuffer(out, dtype=np.int16).astype(np.float32) / 32768


def trim(x: np.ndarray, thr: float = 0.01) -> tuple[np.ndarray, float]:
    """Quita el silencio del principio y del final. Devuelve el audio y el silencio inicial quitado (s)."""
    idx = np.where(np.abs(x) > thr)[0]
    if not len(idx):
        return x, 0.0
    a, b = max(0, idx[0] - int(0.02 * SR)), min(len(x), idx[-1] + int(0.06 * SR))
    return x[a:b], a / SR


# ---------------------------------------------------------------- música (compuesta por código)
def note(n: str) -> float:
    names = {"C": 0, "C#": 1, "D": 2, "D#": 3, "E": 4, "F": 5, "F#": 6, "G": 7, "G#": 8, "A": 9, "A#": 10, "B": 11}
    return 440 * 2 ** ((names[n[:-1]] + 12 * (int(n[-1]) + 1) - 69) / 12)


def env(n: int, a: float, d: float) -> np.ndarray:
    t = np.arange(n) / SR
    return np.minimum(1, t / max(a, 1e-4)) * np.exp(-t / d)


def lowpass(x: np.ndarray, cut: float) -> np.ndarray:
    k = np.exp(-2 * np.pi * cut / SR)
    y = np.empty_like(x)
    acc = 0.0
    for i, v in enumerate(x):  # filtro de un polo (suaviza el timbre)
        acc = (1 - k) * v + k * acc
        y[i] = acc
    return y


def music(duration: float, bpm: float) -> np.ndarray:
    n = int(duration * SR)
    L, R = np.zeros(n), np.zeros(n)
    beat = 60 / bpm
    bar = 4 * beat
    chords = [["F3", "A3", "C4", "E4", "G4"], ["A3", "C4", "E4", "G4", "B4"], ["D3", "F3", "A3", "C4", "E4"], ["A#2", "D3", "F3", "A3", "C4"]]
    t = np.arange(n) / SR
    # pad suave (acordes de séptima), con una pequeña bajada en cada bombo
    pad = np.zeros(n)
    for b in range(int(duration / bar) + 2):
        a, e = int(b * bar * SR), min(n, int((b + 1) * bar * SR) + int(0.3 * SR))
        if a >= n:
            break
        seg = np.arange(e - a) / SR
        ch = chords[b % 4]
        s = sum(np.sin(2 * np.pi * note(x) * seg) + 0.3 * np.sin(2 * np.pi * note(x) * 2.002 * seg) for x in ch) / len(ch)
        s *= np.minimum(1, seg / 0.35) * np.minimum(1, (len(seg) / SR - seg) / 0.3)
        pad[a:e] += s * 0.22
    pump = 1 - 0.35 * np.exp(-((t - 1.6) % beat) / 0.12) * (t > 1.6)
    pad *= pump
    L += pad * 0.9
    R += pad
    # arpegio (pulsado), alternando lados
    step = beat / 2
    for k in range(int(duration / step)):
        ts = k * step
        if ts < 1.6 and k % 2:
            continue
        ch = chords[int(ts / bar) % 4]
        f = note(ch[[0, 2, 3, 4, 3, 2][k % 6]]) * 2
        m = int(0.45 * SR)
        a = int(ts * SR)
        seg = np.arange(min(m, n - a)) / SR
        s = (np.sin(2 * np.pi * f * seg) + 0.25 * np.sin(2 * np.pi * 2 * f * seg)) * env(len(seg), 0.004, 0.16) * 0.16
        (L if k % 2 else R)[a:a + len(seg)] += s
        (R if k % 2 else L)[a:a + len(seg)] += s * 0.4
    # bombo y platos a partir de la segunda escena
    rng = np.random.default_rng(7)
    for k in range(int(duration / beat)):
        ts = k * beat
        if ts < 1.55 or ts > duration - 0.5:
            continue
        a = int(ts * SR)
        seg = np.arange(min(int(0.35 * SR), n - a)) / SR
        f = 48 + 90 * np.exp(-seg / 0.03)
        kick = np.sin(2 * np.pi * np.cumsum(f) / SR) * env(len(seg), 0.002, 0.11) * 0.55
        L[a:a + len(seg)] += kick
        R[a:a + len(seg)] += kick
        h = int((ts + beat / 2) * SR)
        if h < n:
            m = min(int(0.06 * SR), n - h)
            hat = np.diff(rng.standard_normal(m + 1)) * env(m, 0.001, 0.018) * 0.06
            L[h:h + m] += hat
            R[h:h + m] += hat * 0.8
    st = np.stack([L, R], axis=1)
    fade = np.minimum(1, (duration - t) / 0.8)[:, None]
    return st * fade


def _filt(x: np.ndarray, lo: float = 0.0, hi: float = 0.0) -> np.ndarray:
    """Filtro suave por FFT (paso alto en lo, paso bajo en hi; 0 = sin ese lado). Rápido para pistas enteras."""
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR) + 1e-6
    H = np.ones_like(f)
    if lo:
        H /= 1 + (lo / f) ** 4
    if hi:
        H /= 1 + (f / hi) ** 4
    return np.fft.irfft(X * H, len(x))


def _pluck(freq: float, length: float, decay: float = 0.28, bright: int = 8) -> np.ndarray:
    """Pulsado: armónicos que se apagan antes cuanto más agudos (suena a pluck de synth / kalimba)."""
    s = np.arange(int(length * SR)) / SR
    out = sum(np.sin(2 * np.pi * freq * k * s) / k * np.exp(-s / (decay / k ** 0.8)) for k in range(1, bright + 1))
    return out * np.minimum(1, s / 0.002)


def music_house(duration: float, bpm: float = 122) -> np.ndarray:
    """Base actual, estilo afro/lo-fi house de Reels (≈120-124 bpm): bombo a negras con pegada, palmada en 2 y 4,
    shaker a semicorcheas, charles abierto a contratiempo, bajo a contratiempo, acordes cortos sincopados y un gancho
    pulsado con eco. Progresión Am-F-C-G (la del pop de ahora). Primer compás solo gancho y shaker; luego entra todo.
    Todo compuesto por código: sin derechos de autor."""
    n = int(duration * SR)
    t = np.arange(n) / SR
    beat = 60 / bpm
    six, bar = beat / 4, 4 * beat
    rng = np.random.default_rng(11)
    drums, bass, keys, lead = (np.zeros((n, 2)) for _ in range(4))

    def add(track, x, a, gl=1.0, gr=1.0):
        i = int(a * SR)
        if i >= n or i < 0:
            return
        m = min(len(x), n - i)
        track[i:i + m, 0] += x[:m] * gl
        track[i:i + m, 1] += x[:m] * gr

    prog = [("A1", ["A3", "C4", "E4", "G4"]), ("F1", ["F3", "A3", "C4", "E4"]), ("C2", ["G3", "C4", "E4", "G4"]), ("G1", ["G3", "B3", "D4", "A4"])]
    # sonidos
    ks = np.arange(int(0.34 * SR)) / SR
    kick = np.sin(2 * np.pi * np.cumsum(48 + 120 * np.exp(-ks / 0.03)) / SR) * np.exp(-ks / 0.17)
    kick[: int(0.004 * SR)] += rng.standard_normal(int(0.004 * SR)) * 0.25
    kick = np.tanh(kick * 1.8) / np.tanh(1.8) * 0.8
    cs = np.arange(int(0.25 * SR)) / SR
    clap = np.zeros(len(cs))
    for k, d in enumerate((0, 0.009, 0.018)):  # tres golpes muy juntos = palmada
        i = int(d * SR)
        clap[i:] += rng.standard_normal(len(cs) - i) * np.exp(-(cs[: len(cs) - i]) / (0.012 if k < 2 else 0.08))
    clap = _filt(clap, 900, 6000) * 0.42
    sh = _filt(rng.standard_normal(int(0.05 * SR)), 6500) * np.exp(-np.arange(int(0.05 * SR)) / SR / 0.018) * 0.16
    oh = _filt(rng.standard_normal(int(0.16 * SR)), 7500) * np.exp(-np.arange(int(0.16 * SR)) / SR / 0.06) * 0.13
    nbars = int(duration / bar) + 1
    drop = bar  # a partir del segundo compás entra la base
    for b in range(nbars):
        t0 = b * bar
        root, ch = prog[b % 4]
        full = t0 >= drop - 1e-6
        for q in range(16):  # semicorcheas
            ts = t0 + q * six + (0.012 if q % 2 else 0)  # un poco de swing
            add(drums, sh * (0.9 if q % 4 == 2 else 0.5 if q % 2 else 0.35), ts, 0.7, 1.0)
            if not full:
                continue
            if q % 4 == 0:
                add(drums, kick, ts)
            if q in (4, 12):
                add(drums, clap, ts, 0.9, 1.0)
            if q % 4 == 2:
                add(drums, oh, ts, 1.0, 0.75)
                bs = np.arange(int(0.21 * SR)) / SR
                f0 = note(root)
                bl = sum(np.sin(2 * np.pi * f0 * k * bs) * 0.72 ** k / k for k in range(1, 6)) * np.minimum(1, bs / 0.004) * np.exp(-bs / 0.16)
                add(bass, bl * 0.55, ts)
        if full:  # acordes cortos sincopados
            for q in (3, 6, 10, 14):
                for j, x in enumerate(ch):
                    pl = _pluck(note(x), 0.3, 0.11, 6) * 0.07
                    add(keys, pl, t0 + q * six, 1.0 - 0.15 * j, 0.55 + 0.15 * j)
        # gancho pulsado (dos compases que se repiten)
        hook = [(0, "E5"), (3, "G5"), (6, "A5"), (8, "G5"), (10, "E5"), (13, "D5")] if b % 2 == 0 else \
               [(0, "C5"), (3, "D5"), (6, "E5"), (10, "G5"), (12, "A5" if b % 4 == 1 else "B5")]
        for q, x in hook:
            pl = _pluck(note(x), 0.5, 0.22, 9) * 0.13
            add(lead, pl, t0 + q * six)
            for e, (gl, gr) in enumerate(((0.0, 0.5), (0.32, 0.0)), 1):  # eco a 3/16, de lado a lado
                add(lead, pl * 0.5 ** e, t0 + q * six + e * 3 * six, gl, gr)
    lead[:, 0] = _filt(lead[:, 0], 250, 7000)
    lead[:, 1] = _filt(lead[:, 1], 250, 7000)
    intro = np.clip((t - (drop - 0.6)) / 0.6, 0, 1)  # el gancho del primer compás, apagadito
    lead *= (0.55 + 0.45 * intro)[:, None]
    # bombeo (sidechain del bombo) en bajo, acordes y gancho
    pump = np.where(t >= drop, 1 - 0.55 * np.exp(-((t - drop) % beat) / 0.11), 1.0)[:, None]
    mix_ = drums + (bass + keys * 1.0 + lead) * pump
    mix_ = np.tanh(mix_ * 0.9) / 0.9  # un pelín de saturación, sin ensuciar
    fade = np.minimum(1, (duration - t) / 0.8)[:, None]
    mix_ *= fade
    rms = np.sqrt(np.mean(mix_[int(drop * SR):] ** 2)) + 1e-9
    mix_ *= 10 ** (-17 / 20) / rms  # mismo nivel que el groove: la voz manda
    return mix_ / max(1.0, np.abs(mix_).max() / 0.9)


def sfx(kind: str, pitch: float = 1.0) -> np.ndarray:
    rng = np.random.default_rng(int(pitch * 100) + len(kind))
    if kind == "pop":
        seg = np.arange(int(0.12 * SR)) / SR
        f = (900 * pitch) * np.exp(-seg / 0.05) + 300
        return np.sin(2 * np.pi * np.cumsum(f) / SR) * env(len(seg), 0.001, 0.035) * 0.35
    if kind == "tick":
        seg = np.arange(int(0.05 * SR)) / SR
        return np.sin(2 * np.pi * 1800 * seg) * env(len(seg), 0.0005, 0.01) * 0.25
    if kind == "ding":
        seg = np.arange(int(0.9 * SR)) / SR
        return sum(np.sin(2 * np.pi * f * seg) / (i + 1) for i, f in enumerate([1318.5, 1975.5, 2637])) * env(len(seg), 0.002, 0.25) * 0.22
    if kind == "stamp":
        seg = np.arange(int(0.25 * SR)) / SR
        thud = np.sin(2 * np.pi * (70 + 120 * np.exp(-seg / 0.02)) * seg) * env(len(seg), 0.001, 0.06)
        return (thud + rng.standard_normal(len(seg)) * env(len(seg), 0.001, 0.02) * 0.4) * 0.45
    if kind == "whoosh":
        m = int(0.5 * SR)
        noise = rng.standard_normal(m)
        shape = np.sin(np.linspace(0, np.pi, m)) ** 2
        return lowpass(noise * shape, 1400) * 0.22
    if kind == "swell":
        m = int(0.7 * SR)
        noise = lowpass(rng.standard_normal(m), 2500)
        return noise * np.linspace(0, 1, m) ** 2 * 0.12
    if kind == "sparkle":
        out = np.zeros(int(0.9 * SR))
        for i in range(14):
            a = int(rng.uniform(0, 0.6) * SR)
            seg = np.arange(int(0.12 * SR)) / SR
            s = np.sin(2 * np.pi * rng.uniform(2200, 4200) * seg) * env(len(seg), 0.001, 0.03) * 0.08
            out[a:a + len(seg)] += s[: len(out) - a]
        return out
    raise ValueError(kind)


def place(track: np.ndarray, clip: np.ndarray, t: float, gain: float = 1.0) -> None:
    a = int(t * SR)
    if a >= len(track):
        return
    m = min(len(clip), len(track) - a)
    if track.ndim == 2:
        track[a:a + m] += (clip[:m] * gain)[:, None]
    else:
        track[a:a + m] += clip[:m] * gain


def write_wav(path: Path, x: np.ndarray) -> None:
    x = np.clip(x, -1, 1)
    ch = 1 if x.ndim == 1 else x.shape[1]
    with wave.open(str(path), "wb") as w:
        w.setnchannels(ch)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((x * 32767).astype("<i2").tobytes())


def srt_time(s: float) -> str:
    ms = int(round(s * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def voice_take(text: str, spec: dict) -> tuple[np.ndarray, list | None]:
    vname = spec.get("voice", "es_ES-davefx-medium")
    if vname.startswith("polly:"):
        raw, marks = polly(text, vname)
    else:
        raw, marks = synth(text, vname, spec.get("speed", 1.0)), None
    audio, cut = trim(raw)
    marks = marks and [(max(0.0, m[0] - cut), m[1]) for m in marks]
    if spec.get("tempo", 1.0) != 1.0:  # acelerar sin cambiar el tono
        audio = tempo(audio, spec["tempo"])
        marks = marks and [(m[0] / spec["tempo"], m[1]) for m in marks]
    return audio, marks


def pauses(x: np.ndarray, min_s: float = 0.06, thr: float = 0.012) -> list[tuple[float, float]]:
    """Silencios dentro de la toma: [(inicio, fin)] en segundos."""
    hop = int(0.01 * SR)
    rms = np.sqrt(np.convolve(x ** 2, np.ones(hop) / hop, mode="same"))[::hop]
    quiet = rms < thr
    out, start = [], None
    for i, q in enumerate(quiet):
        if q and start is None:
            start = i
        elif not q and start is not None:
            if (i - start) * 0.01 >= min_s:
                out.append((start * 0.01, i * 0.01))
            start = None
    return out


WEAK = {"de", "del", "la", "el", "los", "las", "un", "una", "y", "o", "que", "en", "a", "al", "con", "por", "para", "tu", "tus",
        "mi", "se", "te", "lo", "le", "es", "no", "ni", "más", "muy", "su", "sus", "como"}


def chunks(words: list[str], size: int = 5) -> list[list[int]]:
    """Trozos de subtítulo de 2-5 palabras: se corta tras una coma o un punto, y nunca justo después de una palabra
    corta (de, la, un, y, que…), que se pasa al trozo siguiente para que cada trozo se lea como una frase."""
    out, cur = [], []
    for i, w in enumerate(words):
        cur.append(i)
        punct = w[-1] in ",.;:?!…»"
        if punct and (len(cur) >= 2 or w[-1] in ".?!…"):
            if len(cur) == 1 and out and len(out[-1]) <= 5 and words[out[-1][-1]][-1] not in ".?!…":
                out[-1] += cur  # una palabra suelta al final de frase ("ego.") va con el trozo anterior
            else:
                out.append(cur)
            cur = []
        elif len(cur) >= size:
            keep = cur
            while len(keep) > 2 and words[keep[-1]].lower().strip("¿¡«") in WEAK:
                keep = keep[:-1]
            out.append(keep)
            cur = cur[len(keep):]
    if cur:
        if out and len(cur) == 1:
            out[-1] += cur
        else:
            out.append(cur)
    return out


def main(path: str) -> None:
    """Una sola toma de voz para todo el guion (entonación natural). Cada parte del guion lleva "scene": el segundo de la
    animación en el que empieza su escena; la animación se sincroniza con la voz (ver timewarp.py)."""
    from timewarp import unwarp
    spec = json.loads(Path(path).read_text())
    name = Path(path).name.replace(".voz.json", "")
    OUT.mkdir(parents=True, exist_ok=True)
    lines = spec["lines"]
    said = [ln.get("say", ln["text"]) for ln in lines]
    take, marks = voice_take(" ".join(said), spec)
    T = len(take) / SR
    # dónde empieza cada parte dentro de la toma
    shown = [[w for w in ln["text"].strip().split(" ") if w] for ln in lines]  # el espacio fino (80\u00a0%) no corta
    spoken = [x.split() for x in said]
    starts, ends = [0.0], []
    if marks and len(marks) == sum(len(w) for w in spoken):
        k = 0
        for w in spoken[:-1]:
            k += len(w)
            starts.append(marks[k][0])
    else:  # sin marcas: se buscan los silencios cerca de donde tocaría cada corte
        sizes = [len(voice_take(x, spec)[0]) / SR for x in said] if len(said) > 1 else [T]
        gaps = pauses(take)
        cum = np.cumsum(sizes) / sum(sizes) * T
        for e in cum[:-1]:
            cand = [g for g in gaps if g[1] > starts[-1] + 0.3 and abs((g[0] + g[1]) / 2 - e) < 1.2]
            starts.append(min(cand, key=lambda g: abs((g[0] + g[1]) / 2 - e))[1] if cand else float(e))
    gaps = pauses(take)
    for i in range(len(lines)):
        nxt = starts[i + 1] if i + 1 < len(lines) else T
        g = [x for x in gaps if starts[i] < x[0] < nxt and x[1] >= nxt - 0.02]
        ends.append(g[-1][0] if g else nxt)
    lead, tail = spec.get("lead", 0.35), spec.get("tail", 1.8)
    dur = lead + T + tail
    anchors = [(0.0, 0.0)] + [(lead + starts[i], float(ln["scene"])) for i, ln in enumerate(lines)] + [(dur, float(spec["anim_duration"]))]
    voice = np.zeros(int(dur * SR))
    place(voice, take, lead)
    captions = []
    for i, ln in enumerate(lines):
        t0, t1 = lead + starts[i], lead + ends[i]
        words = shown[i]
        if marks and len(marks) == sum(len(w) for w in spoken) and len(spoken[i]) == len(words):
            k0 = sum(len(w) for w in spoken[:i])
            edges = np.array([lead + marks[k0 + j][0] for j in range(len(words))] + [t1])
        else:
            weights = np.array([len(w.strip(".,;:¡!¿?«»…")) + 1.5 for w in words], dtype=float)
            edges = t0 + np.concatenate([[0], np.cumsum(weights / weights.sum())]) * (t1 - t0)
        for ch in chunks(words):
            captions.append({"text": " ".join(words[j] for j in ch), "t0": round(float(edges[ch[0]]), 3), "t1": round(float(edges[ch[-1] + 1]), 3),
                             "words": [{"w": words[j], "t0": round(float(edges[j]), 3), "t1": round(float(edges[j + 1]), 3)} for j in ch]})
        print(f"  {t0:5.2f}–{t1:5.2f} s  (escena {ln['scene']})  {ln['text']}")
    m = music_house(dur, spec.get("bpm", 122)) if spec.get("music") == "house" else music(dur, spec.get("bpm", 104))
    for e in spec.get("sfx", []):  # los efectos van en tiempo de animación: se pasan a tiempo real
        place(m, sfx(e["type"], e.get("pitch", 1.0)), unwarp(e["t"], anchors))
    write_wav(OUT / f"{name}-voz.wav", voice * 0.95)
    write_wav(OUT / f"{name}-musica.wav", m * 0.8)
    (OUT / f"{name}.captions.json").write_text(json.dumps(captions, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / f"{name}.timing.json").write_text(json.dumps({"duration": round(dur, 3), "anchors": anchors}), encoding="utf-8")
    srt = []
    for i, c in enumerate(captions, 1):
        srt += [str(i), f"{srt_time(c['t0'])} --> {srt_time(c['t1'] + 0.15)}", c["text"], ""]
    (OUT / f"{name}.srt").write_text("\n".join(srt), encoding="utf-8")
    print(f"Voz de {T:.1f} s, vídeo de {dur:.1f} s. Voz, música, subtítulos y sincronía en {OUT}")


if __name__ == "__main__":
    main(sys.argv[1])
