"""Voz, música, efectos y subtítulos para un Reel, a partir de un guion (<nombre>.voz.json).

Uso:
  uv run --no-project --with piper-tts --with numpy python marketing/instagram/video/voiceover.py \
      marketing/instagram/video/showreel.voz.json

Genera en marketing/instagram/out/video/:
  <nombre>-voz.wav       la voz: Amazon Polly ("voice": "polly:Lucia:generative:eu-central-1", natural, con la cuenta de
                         AWS) o Piper ("voice": "es_ES-davefx-medium", sin conexión, más robótica)
  <nombre>-musica.wav    base musical compuesta por código (sin derechos de autor) + efectos sincronizados
  <nombre>.captions.json subtítulos con el tiempo de cada palabra (los pinta render_video.py dentro del vídeo)
  <nombre>.srt           subtítulos en archivo aparte

Guion: {"duration", "bpm", "voice", "speed" (Piper), "tempo" (acelera la voz sin cambiar el tono), "lines": [{"t", "text", "say"?}], "sfx": [{"t", "type", "pitch"?}]}
  text = lo que sale en el subtítulo; say = cómo debe pronunciarlo la voz (p. ej. "Ranch" para que suene bien "Runch").
  Efectos: whoosh, pop, tick, ding, stamp, swell, sparkle.
"""

from __future__ import annotations

import json
import sys
import subprocess
import wave
from pathlib import Path

import numpy as np

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
    mp3 = OUT / "_line.mp3"
    base = ["aws", "polly", "synthesize-speech", "--region", region, "--engine", engine, "--voice-id", vid, "--text", text]
    subprocess.run(base + ["--output-format", "mp3", "--sample-rate", "24000", str(mp3)], check=True, capture_output=True)
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(mp3), "-f", "s16le", "-ac", "1", "-ar", str(SR), "-"],
                         check=True, capture_output=True).stdout
    mp3.unlink()
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


def main(path: str) -> None:
    spec = json.loads(Path(path).read_text())
    name = Path(path).name.replace(".voz.json", "")
    OUT.mkdir(parents=True, exist_ok=True)
    dur = float(spec["duration"])
    voice = np.zeros(int(dur * SR))
    captions = []
    for ln in spec["lines"]:
        vname = spec.get("voice", "es_ES-davefx-medium")
        if vname.startswith("polly:"):
            raw, marks = polly(ln.get("say", ln["text"]), vname)
        else:
            raw, marks = synth(ln.get("say", ln["text"]), vname, spec.get("speed", 1.0)), None
        audio, cut = trim(raw)
        if spec.get("tempo", 1.0) != 1.0:  # acelerar sin cambiar el tono (atempo de ffmpeg)
            audio = tempo(audio, spec["tempo"])
            marks = marks and [(m[0] / spec["tempo"], m[1]) for m in marks]
            cut /= spec["tempo"]
        t0, t1 = ln["t"], ln["t"] + len(audio) / SR
        if t1 > dur:
            print(f"AVISO: «{ln['text']}» acaba en {t1:.2f} s, después del final del vídeo ({dur} s)")
        place(voice, audio, t0)
        # tiempo de cada palabra: repartido según su longitud
        words = ln["text"].split()
        if marks and len(marks) == len(words):  # tiempo exacto de cada palabra (marcas de la voz)
            starts = [t0 + max(0.0, m[0] - cut) for m in marks]
            edges = np.array(starts + [t1])
        else:  # repartido según la longitud de cada palabra
            weights = np.array([len(w.strip(".,;:¡!¿?«»")) + 1.5 for w in words], dtype=float)
            edges = t0 + np.concatenate([[0], np.cumsum(weights / weights.sum())]) * (t1 - t0)
        captions.append({"text": ln["text"], "t0": round(t0, 3), "t1": round(t1, 3),
                         "words": [{"w": w, "t0": round(edges[i], 3), "t1": round(edges[i + 1], 3)} for i, w in enumerate(words)]})
        print(f"  {t0:5.2f}–{t1:5.2f} s  {ln['text']}")
    m = music(dur, spec.get("bpm", 104))
    for e in spec.get("sfx", []):
        place(m, sfx(e["type"], e.get("pitch", 1.0)), e["t"])
    write_wav(OUT / f"{name}-voz.wav", voice * 0.95)
    write_wav(OUT / f"{name}-musica.wav", m * 0.8)
    (OUT / f"{name}.captions.json").write_text(json.dumps(captions, ensure_ascii=False, indent=1), encoding="utf-8")
    srt = []
    for i, c in enumerate(captions, 1):
        srt += [str(i), f"{srt_time(c['t0'])} --> {srt_time(min(dur, c['t1'] + 0.25))}", c["text"], ""]
    (OUT / f"{name}.srt").write_text("\n".join(srt), encoding="utf-8")
    print(f"Voz, música y subtítulos en {OUT}")


if __name__ == "__main__":
    main(sys.argv[1])
