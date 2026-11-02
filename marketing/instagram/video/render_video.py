"""Graba una animación HTML (con window.render(t) y window.DURATION) como vídeo MP4 vertical para Reels.

Uso:
  uv run --no-project --with playwright python marketing/instagram/video/render_video.py marketing/instagram/video/showreel.html

Si existen en marketing/instagram/out/video/ los archivos de voiceover.py (<nombre>.captions.json, <nombre>-voz.wav y
<nombre>-musica.wav), el vídeo sale completo: subtítulos + voz + música, listo para publicar. Si no, sin audio ni
subtítulos. También deja la portada <nombre>-portada.png (sin subtítulos).

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
OUT = HERE.parent / "out" / "video"

# Subtítulos: cápsula blanca en la zona segura (encima de los botones de Instagram), palabra activa en amarillo.
CAPTION_JS = r"""
(() => {
  const box = document.createElement('div');
  box.id = '__cap';
  box.style.cssText = 'position:absolute;left:90px;right:150px;top:1395px;display:flex;justify-content:center;z-index:99;pointer-events:none';
  box.innerHTML = '<div id="__capin" style="display:inline-flex;flex-wrap:wrap;justify-content:center;gap:4px 14px;max-width:840px;padding:20px 34px;border-radius:34px;' +
    'background:rgba(255,255,255,.94);box-shadow:0 14px 40px rgba(60,50,90,.18);font-family:GSF,system-ui,sans-serif;font-size:54px;font-weight:750;' +
    'letter-spacing:-.02em;line-height:1.18;color:#1D1B2C;text-align:center"></div>';
  (document.getElementById('stage') || document.body).appendChild(box);
  const inner = box.firstChild;
  let shown = null;
  window.__caption = (t) => {
    const caps = window.CAPTIONS || [];
    const c = caps.find((x) => t >= x.t0 - 0.05 && t <= x.t1 + 0.25);
    if (!c) { box.style.opacity = 0; shown = null; return; }
    if (shown !== c) {
      inner.innerHTML = c.words.map((w) => `<span style="padding:0 8px;border-radius:14px">${w.w}</span>`).join('');
      shown = c;
    }
    const q = Math.min(1, Math.max(0, (t - c.t0 + 0.05) / 0.18));
    const back = 1 + 2.4 * Math.pow(q - 1, 3) + 1.4 * Math.pow(q - 1, 2);
    const out = Math.min(1, Math.max(0, (t - c.t1 - 0.1) / 0.15));
    box.style.opacity = q * (1 - out);
    box.style.transform = `translateY(${(1 - q) * 30}px) scale(${0.9 + 0.1 * back})`;
    [...inner.children].forEach((s, i) => {
      const w = c.words[i];
      const on = t >= w.t0 && t < w.t1 + (i === c.words.length - 1 ? 0.3 : 0);
      s.style.background = on ? '#FFE58A' : 'transparent';
      s.style.color = t < w.t0 ? 'rgba(29,27,44,.45)' : '#1D1B2C';
    });
  };
})();
"""


def frames(page_path: Path, dest: Path, fps: int, captions: list | None, timing: dict | None = None) -> float:
    from playwright.sync_api import sync_playwright
    shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True)
    exe = (glob.glob(os.path.expanduser("~/.cache/ms-playwright/chromium_headless_shell-*/*/chrome-headless-shell")) or [None])[0]
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=exe) if exe else p.chromium.launch()
        pg = b.new_page(viewport={"width": 1080, "height": 1920}, device_scale_factor=1)
        pg.goto(page_path.as_uri())
        pg.evaluate("document.fonts.ready")
        if captions is not None:
            pg.evaluate(f"window.CAPTIONS = {json.dumps(captions, ensure_ascii=False)}")
            pg.evaluate(CAPTION_JS)
        pg.wait_for_timeout(300)
        duration = float(timing["duration"]) if timing else float(pg.evaluate("window.DURATION"))
        n = round(duration * fps)
        for i in range(n):
            t = i / fps
            a = warp(t, timing["anchors"]) if timing else t  # la animación sigue a la voz
            pg.evaluate(f"render({a}, {t}); window.__caption && window.__caption({t})")
            pg.screenshot(path=str(dest / f"{i:05d}.jpg"), type="jpeg", quality=94)
            if i % 90 == 0:
                print(f"  fotograma {i}/{n}")
        # portada: un fotograma del gancho, sin subtítulos
        pg.evaluate(f"render(2.6, 2.6); window.__caption && window.__caption(-9)")
        pg.screenshot(path=str(OUT / f"{page_path.stem}-portada.png"))
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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("page")
    ap.add_argument("fps", nargs="?", type=int, default=30)
    a = ap.parse_args()
    page = Path(a.page).resolve()
    OUT.mkdir(parents=True, exist_ok=True)
    name = page.stem
    caps, voice, music = OUT / f"{name}.captions.json", OUT / f"{name}-voz.wav", OUT / f"{name}-musica.wav"
    tmp = OUT / f"_frames-{name}"
    with_audio = caps.exists() and voice.exists()
    tfile = OUT / f"{name}.timing.json"
    timing = json.loads(tfile.read_text()) if with_audio and tfile.exists() else None
    duration = frames(page, tmp, a.fps, json.loads(caps.read_text()) if with_audio else None, timing)
    final = OUT / f"{name}.mp4"
    if not with_audio:
        encode(tmp, a.fps, final)
        shutil.rmtree(tmp)
        print(f"Vídeo: {final} ({duration:.0f} s, sin audio ni subtítulos)")
        return
    silent = OUT / f"_{name}-subs.mp4"
    encode(tmp, a.fps, silent)
    shutil.rmtree(tmp)
    mux(silent, voice, music if music.exists() else None, final)
    silent.unlink()
    print(f"Vídeo: {final} ({duration:.0f} s, voz + música + subtítulos)")

if __name__ == "__main__":
    main()
