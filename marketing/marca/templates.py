"""Plantillas de Instagram de la capa ilustrada (post 1080 x 1350 y historia 1080 x 1920).

    uv run --no-project --with playwright --with fonttools python marketing/marca/templates.py

Cada plantilla tiene un hueco para una ilustración. Mientras no haya ilustración se rellena con el patrón del
logotipo (`<nombre>.png`, lista para usar) y además sale una versión con el hueco marcado y sus medidas
(`<nombre>-hueco.png`) para quien dibuje. Cuando exista la ilustración, pon su ruta en "ilustracion" (PNG con
fondo transparente, una sola tinta del color de la plantilla) y vuelve a lanzar el script.
"""
from __future__ import annotations

import html
from pathlib import Path

from build import pattern_fill, svg
from kit import C, HERE, Renderer, wordmark_svg

OUT = HERE / "plantillas"

# Tema: fondo y tinta (siempre una sola tinta).
THEMES = {
    "terracotta": (C["terracotta"], C["cream"]),
    "cream": (C["cream"], C["terracotta"]),
    "sage": (C["sage"], C["espresso"]),
    "butter": (C["butter"], C["espresso"]),
    "espresso": (C["espresso"], C["cream"]),
}

TEMPLATES = [
    {"id": "quedada", "theme": "terracotta", "kicker": "Quedada Runch", "title": "Domingo, 9:00",
     "body": "Ritmo Z2: el que te deja hablar mientras corres. Nadie se queda atrás.",
     "chips": ["5–8 km", "ritmo Z2", "desayuno después"], "ilustracion": None},
    {"id": "reto", "theme": "cream", "kicker": "Reto Runch", "title": "3 accesos beta de 3 meses",
     "body": "Responde a la pregunta en comentarios. Sorteo entre las respuestas correctas.",
     "chips": ["hasta el 25 de noviembre", "bases en el pie del post"], "ilustracion": None},
    {"id": "tu-turno", "theme": "sage", "kicker": "Tu turno", "title": "¿Qué te pides después de correr?",
     "body": "Te leemos en comentarios.", "chips": ["tostada", "tortilla", "croissant", "otra cosa"],
     "ilustracion": None},
    {"id": "cita", "theme": "butter", "kicker": "Para llevar", "title": "«Correr despacio también es correr.»",
     "body": "El club, cada domingo.", "chips": [], "ilustracion": None, "quote": True},
]


def slot(w: int, h: int, bg: str, ink: str, image: str | None, hueco: bool, pid: str) -> str:
    """Hueco de la ilustración: la imagen, el patrón o un marcador discontinuo con medidas."""
    if image:
        return f'<div class="slot" style="height:{h}px"><img src="{Path(image).resolve().as_uri()}"></div>'
    if hueco:
        return (f'<div class="slot hueco" style="height:{h}px"><div><b>Ilustración</b>'
                f'<span>{w} × {h} px · una tinta · fondo transparente</span></div></div>')
    return f'<div class="slot" style="height:{h}px">{svg(w, h, pattern_fill(w, h, bg, ink, scale=.8, pid=pid))}</div>'


def page(t: dict, story: bool, hueco: bool) -> tuple[str, str]:
    bg, ink = THEMES[t["theme"]]
    W, H = (1080, 1920) if story else (1080, 1350)
    sw, sh = 920, (760 if story else 580)
    title = html.escape(t["title"])
    size = 108 if len(t["title"]) < 18 else 88
    if t.get("quote"):
        size = 96
    chips = "".join(f"<span>{html.escape(c)}</span>" for c in t["chips"])
    css = f"""
.p {{ width:{W}px; height:{H}px; background:{bg}; color:{ink}; padding:{'250px 80px 300px' if story else '70px 80px 80px'};
      display:flex; flex-direction:column; gap:{'44px' if story else '34px'}; }}
.top {{ display:flex; justify-content:space-between; align-items:center; }}
.top span {{ font: 600 26px GSF; opacity:.85; }}
.slot {{ width:{sw}px; border-radius:44px; overflow:hidden; flex:none; }}
.slot svg, .slot img {{ display:block; width:100%; height:100%; object-fit:contain; }}
.hueco {{ border: 5px dashed {ink}; opacity:.6; display:grid; place-items:center; text-align:center; }}
.hueco b {{ display:block; font: 800 56px Gluten; }}
.hueco span {{ font: 500 26px GSF; }}
.k {{ font: 640 34px Gluten; letter-spacing:.1em; text-transform:uppercase; }}
h1 {{ font: 820 {size}px/0.98 Gluten; margin:0; letter-spacing:-.01em; text-wrap:balance; }}
p {{ font: 450 36px/1.35 GSF; margin:0; max-width:24em; }}
.chips {{ display:flex; flex-wrap:wrap; gap:14px; margin-top:auto; }}
.chips span {{ border: 3px solid {ink}; border-radius:999px; padding:12px 26px 14px; font: 600 28px GSF; }}
.txt {{ display:flex; flex-direction:column; gap:22px; flex:1; }}
"""
    body = (f'<div class="p"><div class="top">{wordmark_svg(ink, height=78)}<span>@runch.run</span></div>'
            f'{slot(sw, sh, bg, ink, t.get("ilustracion"), hueco, "s" + t["id"])}'
            f'<div class="txt"><div class="k">{html.escape(t["kicker"])}</div><h1>{title}</h1>'
            f'<p>{html.escape(t["body"])}</p><div class="chips">{chips}</div></div></div>')
    return body, css


def main() -> None:
    OUT.mkdir(exist_ok=True)
    with Renderer() as r:
        for t in TEMPLATES:
            for story in (False, True):
                for hueco in (False, True):
                    body, css = page(t, story, hueco)
                    name = f'{"story" if story else "post"}-{t["id"]}{"-hueco" if hueco else ""}.png'
                    w, h = (1080, 1920) if story else (1080, 1350)
                    r.png(body, OUT / name, w, h, css=css)
                    # Aviso si algo se sale de la página.
                    over = r.pg.evaluate("""() => { const p = document.querySelector('.p');
                        return [...p.querySelectorAll('*')].some(e => e.getBoundingClientRect().bottom > p.clientHeight + 1); }""")
                    print(("AVISO: no cabe " if over else "ok ") + name)


if __name__ == "__main__":
    main()
