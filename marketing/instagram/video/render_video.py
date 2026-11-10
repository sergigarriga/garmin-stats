"""Graba una animación HTML (con window.render(t) y window.DURATION) como vídeo MP4 vertical para Reels.

Uso:
  uv run --no-project --with playwright python marketing/instagram/video/render_video.py marketing/instagram/video/showreel.html

Si existen en marketing/instagram/out/video/ los archivos de voiceover.py (<nombre>.captions.json, <nombre>-voz.wav y
<nombre>-musica.wav), el vídeo sale completo: subtítulos + voz + música, listo para publicar. Si no, sin audio ni
subtítulos, y además <nombre>-sin-musica.mp4 (voz + subtítulos, para poner un sonido en tendencia desde la app). También deja la
portada <nombre>-portada.png (sin subtítulos) y su recorte 4:5 de la cuadrícula <nombre>-portada-4x5.png (1080 x 1350).

--musica: para los reels sin voz (serie «El porqué», porque.py): pone el bucle propio afro house de
marketing/marca/musica/afro_house.py con la duración del vídeo, a -14 LUFS (necesita numpy). Sin subtítulos: el texto ya
va en pantalla.
--stills 0,2,6.5: no graba; deja <nombre>-stills.png con esos fotogramas en fila, para revisar el diseño rápido.

--out <carpeta>: deja el vídeo y la portada en otra carpeta (p. ej. out/video-olivo); la voz, la música y los subtítulos se
siguen leyendo de out/video, así el audio, el ritmo y el texto no cambian.

Cada fotograma se pinta llamando a render(t) (sin animaciones CSS, así no hay saltos) y se monta con ffmpeg (H.264,
1080 x 1920). El audio se mezcla con la música bajando sola cuando habla la voz y se normaliza a -14 LUFS.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from timewarp import warp  # noqa: E402

HERE = Path(__file__).resolve().parent
SRC = HERE.parent / "out" / "video"  # voz, música, subtítulos y ritmo (voiceover.py)
OUT = SRC  # vídeo y portada (--out para otra carpeta)

# Subtítulos: cápsula blanca en la zona segura (encima de los botones de Instagram), palabra activa en amarillo.
CAPTION_JS = r"""
(() => {
  const box = document.createElement('div');
  box.id = '__cap';
  // centrada; su ancho máximo (780 px) queda fuera de la columna de botones de Instagram (derecha)
  box.style.cssText = 'position:absolute;left:0;right:0;top:1440px;display:flex;justify-content:center;z-index:99;pointer-events:none';
  box.innerHTML = '<div style="max-width:780px;padding:16px 30px 18px;border-radius:30px;background:rgba(250,246,240,.97);border:1.5px solid rgba(34,26,21,.14);' +
    'font-family:GSF,system-ui,sans-serif;font-size:50px;font-weight:720;' +
    'letter-spacing:-.02em;word-spacing:.02em;line-height:1.2;color:#221A15;text-align:center;text-wrap:balance"></div>';
  (document.getElementById('stage') || document.body).appendChild(box);
  const inner = box.firstChild;
  let shown = null;
  window.__caption = (t) => {
    const caps = window.CAPTIONS || [];
    const c = caps.find((x) => t >= x.t0 - 0.05 && t <= x.t1 + 0.2);
    if (!c) { box.style.opacity = 0; shown = null; return; }
    if (shown !== c) {
      // texto corrido con espacios normales; el resaltado va detrás de la palabra sin cambiar su sitio
      inner.innerHTML = c.words.map((w) => `<span style="border-radius:12px;padding:0 .12em;margin:0 -.12em;` +
        `-webkit-box-decoration-break:clone;box-decoration-break:clone">${w.w}</span>`).join(' ');
      shown = c;
    }
    const q = Math.min(1, Math.max(0, (t - c.t0 + 0.05) / 0.16));
    const back = 1 + 2.4 * Math.pow(q - 1, 3) + 1.4 * Math.pow(q - 1, 2);
    const out = Math.min(1, Math.max(0, (t - c.t1 - 0.08) / 0.12));
    box.style.opacity = q * (1 - out);
    box.style.transform = `translateY(${(1 - q) * 24}px) scale(${0.92 + 0.08 * back})`;
    [...inner.children].forEach((s, i) => {
      const w = c.words[i];
      const on = t >= w.t0 && t < w.t1 + (i === c.words.length - 1 ? 0.25 : 0);
      s.style.background = 'transparent';
      s.style.color = on ? '#5A6B32' : t < w.t0 ? 'rgba(34,26,21,.35)' : '#221A15';
    });
  };
})();
"""


def cover(pg, page_path: Path) -> None:
    """Portada sin subtítulos: la composición window.cover() si la página la tiene (titular centrado, cabe en un recorte
    3:4) o, si no, un fotograma del gancho."""
    if pg.evaluate("typeof window.cover === 'function'"):
        pg.evaluate("window.__caption && window.__caption(-9); window.cover()")
    else:
        pg.evaluate("render(2.6, 2.6); window.__caption && window.__caption(-9)")
    pg.wait_for_timeout(200)
    png = OUT / f"{page_path.stem}-portada.png"
    pg.screenshot(path=str(png))
    # recorte 4:5 centrado: lo que enseña la cuadrícula del perfil (la portada deja el titular entre y = 300 y 1620)
    pg.screenshot(path=str(OUT / f"{page_path.stem}-portada-4x5.png"), clip={"x": 0, "y": 285, "width": 1080, "height": 1350})


def shot(pg, path: Path, tries: int = 4) -> None:
    """Captura de un fotograma; con la máquina muy cargada Chromium a veces falla una captura: se reintenta."""
    for k in range(tries):
        try:
            pg.screenshot(path=str(path), type="jpeg", quality=94)
            return
        except Exception:  # noqa: BLE001
            if k == tries - 1:
                raise
            pg.wait_for_timeout(1500)


def frames(page_path: Path, dest: Path, fps: int, captions: list | None, timing: dict | None = None, only_cover: bool = False) -> float:
    from playwright.sync_api import sync_playwright
    shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True)
    exe = (glob.glob(os.path.expanduser("~/.cache/ms-playwright/chromium_headless_shell-*/*/chrome-headless-shell")) or [None])[0]
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=exe) if exe else p.chromium.launch()
        pg = b.new_page(viewport={"width": 1080, "height": 1920}, device_scale_factor=1)
        pg.set_default_timeout(180_000)  # con la máquina cargada, una captura puede tardar más de 30 s
        pg.goto(page_path.as_uri())
        pg.evaluate("document.fonts.ready")
        if captions is not None:
            pg.evaluate(f"window.CAPTIONS = {json.dumps(captions, ensure_ascii=False)}")
            pg.evaluate(CAPTION_JS)
        pg.wait_for_timeout(300)
        duration = float(timing["duration"]) if timing else float(pg.evaluate("window.DURATION"))
        n = 0 if only_cover else round(duration * fps)
        for i in range(n):
            t = i / fps
            a = warp(t, timing["anchors"]) if timing else t  # la animación sigue a la voz
            pg.evaluate(f"render({a}, {t}); window.__caption && window.__caption({t})")
            shot(pg, dest / f"{i:05d}.jpg")
            if i % 90 == 0:
                print(f"  fotograma {i}/{n}")
        cover(pg, page_path)
        b.close()
    return duration


def ffmpeg_bin() -> str:
    f = shutil.which("ffmpeg") or (glob.glob(os.path.expanduser("~/.cache/ms-playwright/ffmpeg-*/ffmpeg-linux")) or [None])[0]
    if not f:
        sys.exit("No encuentro ffmpeg: instálalo (sudo apt install ffmpeg).")
    return f


def encode(src: Path, fps: int, mp4: Path) -> None:
    subprocess.run([ffmpeg_bin(), "-y", "-loglevel", "error", "-framerate", str(fps), "-i", str(src / "%05d.jpg"),
                    "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(mp4)], check=True)


def mux(video: Path, voice: Path, music: Path | None, out: Path) -> None:
    """Música que baja sola cuando habla la voz (sidechain) y volumen final a -14 LUFS (lo que recomienda Instagram)."""
    if music:
        fmt = "aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo"
        fc = (f"[1:a]{fmt},asplit=2[v1][v2];[2:a]{fmt},volume=0.55[m];"
              "[m][v1]sidechaincompress=threshold=0.02:ratio=6:attack=15:release=280[md];"
              "[md][v2]amix=inputs=2:duration=first,volume=2,loudnorm=I=-14:TP=-1.5:LRA=11[a]")
        inputs = ["-i", str(voice), "-i", str(music)]
    else:
        fc = "[1:a]aformat=channel_layouts=stereo,loudnorm=I=-14:TP=-1.5:LRA=11[a]"
        inputs = ["-i", str(voice)]
    subprocess.run([ffmpeg_bin(), "-y", "-loglevel", "error", "-i", str(video), *inputs, "-filter_complex", fc,
                    "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                    "-shortest", "-movflags", "+faststart", str(out)], check=True)


def loop_music(dur: float) -> Path:
    """Bucle afro house propio (hecho por código, sin derechos de terceros) de `dur` segundos, con entrada de 0,2 s y
    salida de 1,2 s. Se guarda por duración en la carpeta de salida y se reutiliza."""
    wav = OUT / f"_musica-afro-house-{dur:g}s.wav"
    if wav.exists():
        return wav
    import wave
    sys.path.insert(0, str(HERE.parent.parent / "marca" / "musica"))
    import afro_house  # noqa: PLC0415  (necesita numpy: uv run --with numpy)
    pcm = (afro_house.song(dur) * 32767).astype("<i2")
    tmp = wav.with_suffix(f".{os.getpid()}.tmp")
    with wave.open(str(tmp), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(afro_house.SR)
        w.writeframes(pcm.tobytes())
    tmp.replace(wav)
    return wav


def mux_music(video: Path, music: Path, dur: float, out: Path) -> None:
    """Solo música (sin voz): fundido de salida y volumen final a -14 LUFS."""
    fc = f"[1:a]afade=t=out:st={max(0, dur - 1.2):.2f}:d=1.2,loudnorm=I=-14:TP=-1.5:LRA=11[a]"
    subprocess.run([ffmpeg_bin(), "-y", "-loglevel", "error", "-i", str(video), "-i", str(music), "-filter_complex", fc,
                    "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                    "-t", f"{dur:.3f}", "-movflags", "+faststart", str(out)], check=True)


def stills(page_path: Path, times: list[float]) -> Path:
    """Fotogramas sueltos en una fila (a un tercio de tamaño), para revisar sin grabar el vídeo."""
    from playwright.sync_api import sync_playwright
    exe = (glob.glob(os.path.expanduser("~/.cache/ms-playwright/chromium_headless_shell-*/*/chrome-headless-shell")) or [None])[0]
    tmp = OUT / f"_stills-{page_path.stem}"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=exe) if exe else p.chromium.launch()
        pg = b.new_page(viewport={"width": 1080, "height": 1920}, device_scale_factor=1)
        pg.goto(page_path.as_uri())
        pg.evaluate("document.fonts.ready")
        pg.wait_for_timeout(300)
        for i, t in enumerate(times):
            pg.evaluate(f"render({t}, {t})")
            pg.screenshot(path=str(tmp / f"{i:05d}.png"))
        if pg.evaluate("typeof window.cover === 'function'"):
            pg.evaluate("window.cover()")
            pg.screenshot(path=str(tmp / f"{len(times):05d}.png"))
        b.close()
    out = OUT / f"{page_path.stem}-stills.png"
    n = len(list(tmp.glob("*.png")))
    subprocess.run([ffmpeg_bin(), "-y", "-loglevel", "error", "-framerate", "1", "-i", str(tmp / "%05d.png"), "-vf",
                    f"scale=360:640,tile={n}x1:padding=8:color=0x2a2420", "-frames:v", "1", str(out)], check=True)
    shutil.rmtree(tmp)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("page")
    ap.add_argument("fps", nargs="?", type=int, default=30)
    ap.add_argument("--cover", action="store_true", help="solo la portada (rápido)")
    ap.add_argument("--out", help="carpeta de salida (por defecto out/video)")
    ap.add_argument("--musica", action="store_true", help="sin voz: bucle afro house propio de la duración del vídeo")
    ap.add_argument("--stills", help="solo fotogramas sueltos en una fila: tiempos separados por comas")
    a = ap.parse_args()
    global OUT
    if a.out:
        OUT = Path(a.out).resolve()
    page = Path(a.page).resolve()
    OUT.mkdir(parents=True, exist_ok=True)
    name = page.stem
    caps, voice, music = SRC / f"{name}.captions.json", SRC / f"{name}-voz.wav", SRC / f"{name}-musica.wav"
    tmp = OUT / f"_frames-{name}"
    with_audio = caps.exists() and voice.exists() and not a.musica
    if a.stills:
        print(f"Fotogramas: {stills(page, [float(x) for x in a.stills.split(',')])}")
        return
    tfile = SRC / f"{name}.timing.json"
    timing = json.loads(tfile.read_text()) if with_audio and tfile.exists() else None
    if a.cover:
        frames(page, tmp, a.fps, None, None, only_cover=True)
        shutil.rmtree(tmp)
        print(f"Portada: {OUT / (name + '-portada.png')}")
        return
    duration = frames(page, tmp, a.fps, json.loads(caps.read_text()) if with_audio else None, timing)
    final = OUT / f"{name}.mp4"
    if a.musica:
        silent = OUT / f"_{name}-mudo.mp4"
        encode(tmp, a.fps, silent)
        shutil.rmtree(tmp)
        mux_music(silent, loop_music(duration), duration, final)
        silent.replace(OUT / f"{name}-sin-musica.mp4")   # para poner un sonido en tendencia desde la app
        print(f"Vídeo: {final} ({duration:.0f} s, música propia) y {name}-sin-musica.mp4")
        return
    if not with_audio:
        encode(tmp, a.fps, final)
        shutil.rmtree(tmp)
        print(f"Vídeo: {final} ({duration:.0f} s, sin audio ni subtítulos)")
        return
    silent = OUT / f"_{name}-subs.mp4"
    encode(tmp, a.fps, silent)
    shutil.rmtree(tmp)
    mux(silent, voice, music if music.exists() else None, final)
    # versión sin música (voz + subtítulos), para añadir un sonido en tendencia desde la app de Instagram
    mux(silent, voice, None, OUT / f"{name}-sin-musica.mp4")
    silent.unlink()
    print(f"Vídeo: {final} ({duration:.0f} s, voz + música + subtítulos) y {name}-sin-musica.mp4")

if __name__ == "__main__":
    main()
