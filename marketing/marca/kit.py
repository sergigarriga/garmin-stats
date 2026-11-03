"""Piezas comunes de la capa ilustrada de Runch: colores, logotipo en trazados y render a PNG.

El logotipo se dibuja a partir de Gluten (OFL, ver fonts/) convertido a trazados SVG: cada letra lleva su propio
giro, salto de línea base y ajuste de espacio, así que el resultado es un dibujo fijo y no depende de la fuente.
"""
from __future__ import annotations

import glob
import os
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).resolve().parent
FONT = HERE / "fonts" / "Gluten[slnt,wght].ttf"
IG_FONTS = HERE.parent / "instagram" / "fonts"

# Misma paleta que el sistema editorial (marketing/instagram/render.py).
C = {
    "cream": "#F7F3EC",
    "paper": "#FCFAF6",
    "terracotta": "#D4542F",
    "espresso": "#221A15",
    "sage": "#CBD3B8",
    "sea": "#24496D",
    "butter": "#F1DEA6",
    "blush": "#FFE1A3",
}

# --------------------------------------------------------------------- logotipo
# Ajustes por letra: (dx extra antes de la letra, dy, giro en grados). Unidades de la fuente (2000/em).
WORD_TWEAKS = {
    "r": (0, 30, -6),
    "u": (-115, -25, 3),
    "n": (-100, 15, -3),
    "c": (-100, -20, 4),
    "h": (-95, 10, -2),
}


@lru_cache(maxsize=8)
def _font(wght: int = 820):
    from fontTools.ttLib import TTFont
    from fontTools.varLib.instancer import instantiateVariableFont

    f = TTFont(str(FONT))
    return instantiateVariableFont(f, {"wght": wght, "slnt": 0})


def _glyph(ch: str, wght: int):
    from fontTools.pens.svgPathPen import SVGPathPen
    from fontTools.pens.boundsPen import BoundsPen

    f = _font(wght)
    gs = f.getGlyphSet()
    name = f.getBestCmap()[ord(ch)]
    pen = SVGPathPen(gs)
    gs[name].draw(pen)
    bp = BoundsPen(gs)
    gs[name].draw(bp)
    return pen.getCommands(), gs[name].width, bp.bounds


@lru_cache(maxsize=64)
def lettering(text: str, wght: int = 820, tracking: float = 0, tweaks: tuple | None = None) -> tuple[str, tuple]:
    """Texto en Gluten convertido a trazados. Devuelve (trazados SVG, caja (x, y, w, h)) con y hacia abajo.

    tracking: espacio extra entre letras (unidades de la fuente, 2000/em). tweaks: ((letra, (dx, dy, giro)), ...).
    """
    tw = dict(tweaks or ())
    x, parts, xs0, xs1, ys0, ys1 = 0.0, [], [], [], [], []
    for i, ch in enumerate(text):
        d, adv, bounds = _glyph(ch, wght)
        dx, dy, rot = tw.get(ch, (0, 0, 0))
        x += dx + (tracking if i else 0)
        if bounds:
            bx0, by0, bx1, by1 = bounds
            cx, cy = x + (bx0 + bx1) / 2, -(by0 + by1) / 2 + dy
            # La fuente tiene y hacia arriba: se invierte y se gira alrededor del centro de la letra.
            parts.append(f'<path transform="rotate({rot} {cx:.0f} {cy:.0f}) translate({x:.0f} {dy}) scale(1 -1)" d="{d}"/>')
            xs0.append(x + bx0); xs1.append(x + bx1); ys0.append(-by1 + dy); ys1.append(-by0 + dy)
        x += adv
    return "".join(parts), (min(xs0), min(ys0), max(xs1) - min(xs0), max(ys1) - min(ys0))


def wordmark(text: str = "runch", wght: int = 820) -> tuple[str, tuple]:
    """El logotipo: letras gordas que se tocan y bailan un poco sobre la línea base."""
    g, (x, y, w, h) = lettering(text, wght, 0, tuple(WORD_TWEAKS.items()))
    pad = 60
    return g, (x - pad, y - pad, w + 2 * pad, h + 2 * pad)


def wordmark_svg(color: str, bg: str | None = None, height: int | None = None, **kw) -> str:
    g, (x, y, w, h) = wordmark(**kw)
    size = f' height="{height}" width="{height * w / h:.0f}"' if height else ""
    rect = f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{bg}"/>' if bg else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x:.0f} {y:.0f} {w:.0f} {h:.0f}"{size}>'
            f'{rect}<g fill="{color}">{g}</g></svg>')


def fontface() -> str:
    """@font-face para las páginas HTML (Gluten: logotipo y titulares de la capa ilustrada; Fraunces y Google Sans Flex del sistema editorial)."""
    return f"""
@font-face {{ font-family: Gluten; src: url("{FONT.as_uri()}"); font-weight: 100 900; }}
@font-face {{ font-family: GSF; src: url("{(IG_FONTS / 'google-sans-flex-latin-wght-normal.woff2').as_uri()}"); font-weight: 1 1000; }}
@font-face {{ font-family: GSF; src: url("{(IG_FONTS / 'google-sans-flex-latin-ext-wght-normal.woff2').as_uri()}"); font-weight: 1 1000;
  unicode-range: U+0100-024F, U+1E00-1EFF; }}
@font-face {{ font-family: FR; src: url("{(IG_FONTS / 'fraunces-latin-full-normal.woff2').as_uri()}"); }}
@font-face {{ font-family: FR; font-style: italic; src: url("{(IG_FONTS / 'fraunces-latin-full-italic.woff2').as_uri()}"); }}
"""


# --------------------------------------------------------------------- render
class Renderer:
    """Un navegador abierto para pintar muchas páginas seguidas."""

    def __enter__(self):
        from playwright.sync_api import sync_playwright

        exe = (glob.glob(os.path.expanduser("~/.cache/ms-playwright/chromium_headless_shell-*/*/chrome-headless-shell"))
               or [None])[0]
        self._p = sync_playwright().start()
        self._b = self._p.chromium.launch(executable_path=exe) if exe else self._p.chromium.launch()
        self.pg = self._b.new_page(device_scale_factor=1)
        return self

    def __exit__(self, *a):
        self._b.close()
        self._p.stop()

    def png(self, body: str, out: Path, w: int, h: int, css: str = "", transparent: bool = False,
            full: bool = False) -> None:
        """Pinta body (HTML o SVG) en un PNG de w x h. full=True: alto según el contenido."""
        bg = "transparent" if transparent else C["cream"]
        size = f"width:{w}px;" + ("" if full else f"height:{h}px;overflow:hidden;")
        page = (f"<!doctype html><html><head><meta charset='utf-8'><style>{fontface()}"
                f"html,body{{margin:0;padding:0;{size}background:{bg}}}"
                f"*{{box-sizing:border-box}}{css}</style></head><body>{body}</body></html>")
        out = Path(out).resolve()
        tmp = out.with_suffix(".tmp.html")
        tmp.write_text(page)
        self.pg.set_viewport_size({"width": w, "height": h})
        self.pg.goto(tmp.as_uri())
        self.pg.evaluate("document.fonts.ready")
        self.pg.wait_for_timeout(60)
        out.parent.mkdir(parents=True, exist_ok=True)
        self.pg.screenshot(path=str(out), omit_background=transparent, full_page=full)
        tmp.unlink()
