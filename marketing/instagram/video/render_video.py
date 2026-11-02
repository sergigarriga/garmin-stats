"""Graba una animación HTML (con window.render(t) y window.DURATION) como vídeo MP4 vertical para Reels.

Uso:
  uv run --no-project --with playwright python marketing/instagram/video/render_video.py \
      marketing/instagram/video/reel-z2.html [fps]

Pinta cada fotograma llamando a render(t) (sin animaciones CSS, así no hay saltos), lo captura con Chromium y lo
monta con ffmpeg (H.264, 1080 x 1920, sin audio: el audio se elige en Instagram). Deja también la portada
(un fotograma a mitad del gancho) en PNG. Salida: marketing/instagram/out/video/<nombre>.mp4
"""

from __future__ import annotations

import glob
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main(src: str, fps: int = 30) -> None:
    from playwright.sync_api import sync_playwright
    page_path = Path(src).resolve()
    out_dir = HERE.parent / "out" / "video"
    frames = out_dir / f"_frames-{page_path.stem}"
    shutil.rmtree(frames, ignore_errors=True)
    frames.mkdir(parents=True)
    exe = (glob.glob(os.path.expanduser("~/.cache/ms-playwright/chromium_headless_shell-*/*/chrome-headless-shell")) or [None])[0]
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=exe) if exe else p.chromium.launch()
        pg = b.new_page(viewport={"width": 1080, "height": 1920}, device_scale_factor=1)
        pg.goto(page_path.as_uri())
        pg.evaluate("document.fonts.ready")
        pg.wait_for_timeout(300)
        duration = float(pg.evaluate("window.DURATION"))
        n = round(duration * fps)
        for i in range(n):
            pg.evaluate(f"render({i / fps})")
            pg.screenshot(path=str(frames / f"{i:05d}.jpg"), type="jpeg", quality=94)
            if i % 60 == 0:
                print(f"  fotograma {i}/{n}")
        pg.evaluate(f"render({min(2.6, duration / 2)})")
        pg.screenshot(path=str(out_dir / f"{page_path.stem}-portada.png"))
        b.close()
    ffmpeg = shutil.which("ffmpeg") or (glob.glob(os.path.expanduser("~/.cache/ms-playwright/ffmpeg-*/ffmpeg-linux")) or [None])[0]
    if not ffmpeg:
        sys.exit("No encuentro ffmpeg: instálalo (sudo apt install ffmpeg).")
    mp4 = out_dir / f"{page_path.stem}.mp4"
    subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-framerate", str(fps), "-i", str(frames / "%05d.jpg"),
                    "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                    str(mp4)], check=True)
    shutil.rmtree(frames)
    print(f"Vídeo: {mp4} ({duration:.0f} s, {fps} fps)")


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 30)
