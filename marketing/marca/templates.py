"""Plantillas de Instagram de la capa ilustrada (post 1080 x 1350 y historia 1080 x 1920), en PNG y en vídeo.

    uv run --no-project --with playwright --with fonttools python marketing/marca/templates.py            # PNG y MP4
    uv run --no-project --with playwright --with fonttools python marketing/marca/templates.py --sin-video

Cada plantilla tiene una sola pieza protagonista (la hora, el premio, la pregunta, la frase), un sello redondo con
texto alrededor y un hueco para una ilustración. Mientras no haya ilustración, el hueco lleva el patrón del
logotipo y además sale una versión con el hueco marcado y sus medidas (`<post|story>-<plantilla>-hueco.png`) para
quien dibuje.

Regla: cada plantilla se publica como carrusel bilingüe con el mismo diseño, diapositiva 1 en catalán y diapositiva 2
en castellano: `<post|story>-<plantilla>-1-ca.png` y `-2-es.png` (y sus `.mp4`). Los textos están en TEXTS, un
diccionario por idioma. Cuando exista la ilustración, pon su ruta en "ilustracion" (PNG con fondo transparente, una sola tinta
del color de la plantilla) y vuelve a lanzar el script.

Vídeo (`.mp4`, 6 s, 30 fps, sin sonido, H.264): el patrón se desliza en diagonal, la pieza protagonista
entra con un pequeño rebote, el sello gira despacio, las etiquetas suben una a una y el logotipo hace una ola.
Cada fotograma se pinta llamando a render(t) en la página (sin animaciones CSS, así no hay saltos). El primer y el
último fotograma son iguales (fondo, logotipo y hueco), así que el vídeo se puede repetir sin corte. Junto a cada
vídeo sale `<nombre>-frames.png` con 6 fotogramas para revisarlo sin abrirlo.
"""
from __future__ import annotations

import html
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path

from build import pattern_logo_tile
from kit import C, HERE, Renderer, fontface, wordmark

OUT = HERE / "plantillas"
FPS, DUR = 30, 6.0

# Tema: fondo y tinta (siempre una sola tinta).
THEMES = {
    "terracotta": (C["terracotta"], C["cream"]),
    "cream": (C["cream"], C["terracotta"]),
    "espresso": (C["espresso"], C["cream"]),
    "butter": (C["butter"], C["espresso"]),
}

# Plantillas: diseño (tema e ilustración). Los textos van aparte, en TEXTS, uno por idioma.
TEMPLATES = [
    {"id": "quedada", "theme": "terracotta", "ilustracion": None},
    {"id": "reto", "theme": "cream", "ilustracion": None},
    {"id": "tu-turno", "theme": "espresso", "ilustracion": None},
    {"id": "cita", "theme": "butter", "ilustracion": None},
]

# Regla: cada plantilla se publica como carrusel bilingüe con el mismo diseño, diapositiva 1 en catalán y
# diapositiva 2 en castellano. LANGS fija ese orden (y el número del nombre de archivo).
LANGS = [("ca", 1), ("es", 2)]

# Textos por idioma. En "lines", la palabra entre *asteriscos* va en una pegatina rellena y la que va entre
# ~virgulillas~ lleva un subrayado en ola. "<br>" corta la línea del texto corrido.
TEXTS = {
    "ca": {
        "quedada": {"kicker": "Quedada Runch", "day": "Diumenge", "time": "9:00",
                    "body": "Sortim junts<br>a ritme de xerrada.", "stamp": "RITME Z2 · NINGÚ ES QUEDA ENRERE · ",
                    "chips": ["5–8 km", "tots els ritmes", "esmorzar després"]},
        "reto": {"kicker": "Repte Runch", "big": "3", "lines": ["accessos", "beta"], "sticker": "de 3 mesos",
                 "body": "Respon als comentaris i entres al sorteig.", "stamp": "SORTEIG · RESPON I PARTICIPA · ",
                 "chips": ["fins al 25 de novembre", "bases al peu del post"]},
        "tu-turno": {"kicker": "El teu torn", "lines": ["Què et", "demanes", "*després*", "de córrer?"],
                     "stamp": "ET LLEGIM · ALS COMENTARIS · ",
                     "chips": ["torrada", "truita", "croissant", "una altra cosa"]},
        "cita": {"kicker": "Per emportar", "lines": ["Córrer a", "~poc a poc~", "també", "és córrer."],
                 "stamp": "EL CLUB · CADA DIUMENGE · ", "body": "Runch, club de running."},
    },
    "es": {
        "quedada": {"kicker": "Quedada Runch", "day": "Domingo", "time": "9:00",
                    "body": "Salimos juntos<br>a ritmo de charla.", "stamp": "RITMO Z2 · NADIE SE QUEDA ATRÁS · ",
                    "chips": ["5–8 km", "todos los ritmos", "desayuno después"]},
        "reto": {"kicker": "Reto Runch", "big": "3", "lines": ["accesos", "beta"], "sticker": "de 3 meses",
                 "body": "Responde en comentarios y entras en el sorteo.", "stamp": "SORTEO · RESPONDE Y PARTICIPA · ",
                 "chips": ["hasta el 25 de noviembre", "bases en el pie del post"]},
        "tu-turno": {"kicker": "Tu turno", "lines": ["¿Qué te", "pides", "*después*", "de correr?"],
                     "stamp": "TE LEEMOS · EN COMENTARIOS · ", "chips": ["tostada", "tortilla", "croissant", "otra cosa"]},
        "cita": {"kicker": "Para llevar", "lines": ["Correr", "~despacio~", "también", "es correr."],
                 "stamp": "EL CLUB · CADA DOMINGO · ", "body": "Runch, club de running."},
    },
}


# ============================================================================ piezas
def A(kind: str, d: float, t: float = .6, **kw) -> str:
    """Marca un elemento para el vídeo: tipo de entrada, inicio y duración (s). En el PNG no cambia nada."""
    extra = "".join(f' data-{k}="{v}"' for k, v in kw.items())
    return f'data-a="{kind}" data-d="{d:g}" data-t="{t:g}"{extra}'


def at(x: float, y: float, inner: str, rot: float = 0, anim: str = "", cls: str = "", style: str = "") -> str:
    """Elemento colocado en (x, y) y girado; la animación va en una capa interior para no pisar el giro."""
    return (f'<div class="abs {cls}" style="left:{x}px;top:{y}px;transform:rotate({rot}deg);{style}">'
            f'<div class="an" {anim}>{inner}</div></div>')


def wordmark_letters(color: str, height: int) -> str:
    """Logotipo con cada letra en su grupo, para que el vídeo pueda hacerlas botar una a una."""
    g, (x, y, w, h) = wordmark()
    letters = "".join(f'<g class="L">{p}</g>' for p in re.findall(r"<path[^>]*/>", g))
    return (f'<svg class="wm" xmlns="http://www.w3.org/2000/svg" viewBox="{x:.0f} {y:.0f} {w:.0f} {h:.0f}" '
            f'height="{height}" width="{height * w / h:.0f}"><g fill="{color}">{letters}</g></svg>')


def daisy(cx: float, cy: float, r: float, petal: str, heart: str) -> str:
    """Margarita setentera de ocho pétalos (centro del sello)."""
    petals = "".join(f'<circle cx="{cx + r * .62 * math.cos(i * math.pi / 4):.1f}" '
                     f'cy="{cy + r * .62 * math.sin(i * math.pi / 4):.1f}" r="{r * .4:.1f}" fill="{petal}"/>' for i in range(8))
    return f'{petals}<circle cx="{cx}" cy="{cy}" r="{r * .36:.1f}" fill="{heart}"/>'


def stamp(text: str, size: int, fill: str, ink: str) -> str:
    """Sello redondo: texto alrededor de un círculo (gira en el vídeo) y una margarita en el centro."""
    r = 108
    return (f'<svg class="stamp" viewBox="0 0 300 300" width="{size}" height="{size}">'
            f'<defs><path id="ring{size}" d="M150,150 m-{r},0 a{r},{r} 0 1,1 {2 * r},0 a{r},{r} 0 1,1 -{2 * r},0"/></defs>'
            f'<circle cx="150" cy="150" r="149" fill="{fill}"/>'
            f'<g data-spin="-22"><text font-family="Gluten" font-weight="720" font-size="31" fill="{ink}" data-r="{r}">'
            f'<textPath href="#ring{size}">{html.escape(text)}'
            f'</textPath></text></g>'
            f'<circle cx="150" cy="150" r="80" fill="none" stroke="{ink}" stroke-width="3" stroke-dasharray="1 11" '
            f'stroke-linecap="round"/>{daisy(150, 150, 54, ink, fill)}</svg>')


def slot(w: int, h: int, bg: str, ink: str, image: str | None, hueco: bool, pid: str) -> str:
    """Hueco de la ilustración: la imagen, el patrón (se desliza en el vídeo) o un marcador con medidas."""
    if image:
        return f'<div class="slot" style="width:{w}px;height:{h}px"><img src="{Path(image).resolve().as_uri()}"></div>'
    if hueco:
        return (f'<div class="slot hueco" style="width:{w}px;height:{h}px"><div><b>Ilustración</b>'
                f'<span>{w} × {h} px · una tinta · fondo transparente</span></div></div>')
    tile, tw, th = pattern_logo_tile(bg)
    return (f'<div class="slot" style="width:{w}px;height:{h}px"><svg viewBox="0 0 {w} {h}" width="{w}" height="{h}">'
            f'<defs><pattern id="{pid}" width="{tw:.2f}" height="{th:.2f}" patternUnits="userSpaceOnUse" '
            f'patternTransform="rotate(-8) scale(.62)" data-dx="{tw / 2:.2f}" data-dy="{th / 2:.2f}">{tile}</pattern></defs>'
            f'<rect width="{w}" height="{h}" fill="{ink}"/><rect width="{w}" height="{h}" fill="url(#{pid})"/></svg></div>')


def chips(items: list[str], d0: float, gap: float = .12) -> str:
    return "".join(f'<span class="chip" {A("chip", d0 + i * gap, .55)}>{html.escape(c)}</span>' for i, c in enumerate(items))


def lines_html(lines: list[str], d0: float, gap: float = .1, indents: list[int] | None = None) -> str:
    """Líneas del titular; la palabra entre *asteriscos* va en una pegatina rellena (y entra con rebote)."""
    out = []
    for i, ln in enumerate(lines):
        pad = f' style="margin-left:{indents[i]}px"' if indents else ""
        if ln.startswith("~"):
            wave = "M6 20 Q 36 2 66 20 T 126 20 T 186 20 T 246 20 T 306 20 T 366 20 T 426 20 T 486 20 T 546 20 T 606 20"
            out.append(f'<div class="ln"{pad}><span class="sq" {A("rise", d0 + i * gap, .6, y=50)}>{html.escape(ln.strip("~"))}'
                       f'<svg viewBox="0 0 612 40" preserveAspectRatio="none"><path d="{wave}" pathLength="1" '
                       f'stroke-dasharray="1 1" {A("draw", d0 + i * gap + .6, .8)}/></svg></span></div>')
        elif ln.startswith("*"):
            out.append(f'<div class="ln"{pad}><span class="hi" {A("pop", d0 + i * gap + .15, .8, r=-10)}>'
                       f'{html.escape(ln.strip("*"))}</span></div>')
        else:
            out.append(f'<div class="ln"{pad}><span {A("rise", d0 + i * gap, .6, y=50)}>{html.escape(ln)}</span></div>')
    return "".join(out)


# ============================================================================ composiciones
def bar(ink: str, top: int) -> str:
    return (f'<div class="abs bar" style="left:72px;right:72px;top:{top}px">{wordmark_letters(ink, 62)}'
            f'<span>@runch.run</span></div>')


def kicker(text: str, x: int, y: int, d: float = .1, rot: float = 0) -> str:
    return at(x, y, f'<div class="k">{html.escape(text)}</div>', rot, A("rise", d, .55, y=24))


def quedada(t: dict, story: bool, sl) -> str:
    v = (lambda p, s: s if story else p)
    y0 = v(0, 200)
    sw, sh = v((500, 380), (540, 440))
    big = v(480, 505)
    return "".join([
        at(1008 - sw, y0 + v(168, 190), sl(sw, sh), 3),
        kicker(t["kicker"], 72, y0 + v(196, 222), .1),
        at(72, y0 + v(262, 300), f'<p class="body">{t["body"]}</p>', 0, A("fade", .35, .7)),
        at(72, y0 + v(596, 700), f'<div class="day">{html.escape(t["day"].upper())}</div>', 0, A("rise", .3, .6, y=40)),
        at(v(56, 60), y0 + v(752, 880),
           f'<div class="hero-wrap"><div class="hero echo" {A("echo", .75, .7, x=v(14, 16), y=v(14, 16))} '
           f'style="font-size:{big}px">{t["time"]}</div>'
           f'<div class="hero" {A("pop", .5, .95, r=-9)} style="font-size:{big}px">{t["time"]}</div></div>', -5),
        at(v(790, 770), y0 + v(430, 520), stamp(t["stamp"], v(250, 280), C["cream"], C["terracotta"]), 0, A("stamp", 1.05, .9)),
        f'<div class="abs chips" style="left:72px;top:{y0 + v(1172, 1330)}px">{chips(t["chips"], 1.35)}</div>',
    ])


def reto(t: dict, story: bool, sl) -> str:
    v = (lambda p, s: s if story else p)
    y0 = v(0, 200)
    sw, sh = v((500, 380), (540, 440))
    big = v(560, 640)
    return "".join([
        at(72, y0 + v(168, 190), sl(sw, sh), -3),
        kicker(t["kicker"], v(620, 660), y0 + v(196, 222), .1),
        at(v(620, 660), y0 + v(262, 300), f'<p class="body" style="width:{v(388, 348)}px">{html.escape(t["body"])}</p>', 0, A("fade", .35, .7)),
        at(v(58, 56), y0 + v(640, 770),
           f'<div class="hero-wrap"><div class="hero echo" {A("echo", .75, .7, x=v(16, 18), y=v(16, 18))} '
           f'style="font-size:{big}px">{t["big"]}</div>'
           f'<div class="hero" {A("pop", .5, .95, r=-12)} style="font-size:{big}px">{t["big"]}</div></div>', -6),
        at(v(420, 450), y0 + v(720, 850), f'<div class="stack">{lines_html(t["lines"], .7, .12)}</div>', -3),
        at(v(440, 380), y0 + v(450, 520), stamp(t["stamp"], v(230, 260), C["terracotta"], C["cream"]), 0, A("stamp", 1.05, .9)),
        at(v(436, 486), y0 + v(990, 1140), f'<div class="sticker">{html.escape(t["sticker"])}</div>', 4, A("pop", 1.0, .8, r=12)),
        f'<div class="abs chips" style="left:72px;top:{y0 + v(1172, 1330)}px">{chips(t["chips"], 1.4)}</div>',
    ])


def tu_turno(t: dict, story: bool, sl) -> str:
    v = (lambda p, s: s if story else p)
    y0 = v(0, 200)
    sw, sh = v((420, 330), (460, 380))
    return "".join([
        kicker(t["kicker"], 72, y0 + v(170, 200), .1),
        at(v(64, 64), y0 + v(236, 276), f'<div class="q">{lines_html(t["lines"], .25, .12, [0, 120, 40, 0])}</div>', -3),
        f'<div class="abs chips col" style="left:72px;top:{y0 + v(900, 1030)}px">{chips(t["chips"], 1.3, .1)}</div>',
        at(1008 - sw, y0 + v(880, 1000), sl(sw, sh), 3),
        at(v(490, 470), y0 + v(800, 910), stamp(t["stamp"], v(210, 240), C["cream"], C["espresso"]), 0, A("stamp", 1.0, .9)),
    ])


def cita(t: dict, story: bool, sl) -> str:
    v = (lambda p, s: s if story else p)
    y0 = v(0, 200)
    sw, sh = v((460, 330), (500, 380))
    return "".join([
        kicker(t["kicker"], 72, y0 + v(170, 200), .1),
        at(v(700, 690), y0 + v(70, 90), '<div class="qm" ' + A("pop", .2, .9, r=-14) + '>«</div>', 8),
        at(72, y0 + v(335, 375), f'<div class="q quote">{lines_html(t["lines"], .45, .12, [0, 60, 0, 0])}</div>', -2),
        at(72, y0 + v(950, 1010), sl(sw, sh), -3),
        at(v(620, 640), y0 + v(966, 1020), stamp(t["stamp"], v(250, 280), C["espresso"], C["butter"]), 0, A("stamp", 1.2, .9)),
        at(v(610, 630), y0 + v(1246, 1330), f'<p class="body sig">{html.escape(t["body"])}</p>', 0, A("fade", 1.5, .7)),
    ])


LAYOUTS = {"quedada": quedada, "reto": reto, "tu-turno": tu_turno, "cita": cita}


def page(t: dict, story: bool, hueco: bool) -> tuple[str, str]:
    bg, ink = THEMES[t["theme"]]
    W, H = (1080, 1920) if story else (1080, 1350)
    big_q = 140 if story else 120
    css = f"""
.p {{ position:relative; width:{W}px; height:{H}px; background:{bg}; color:{ink}; overflow:hidden; }}
.abs {{ position:absolute; }}
.an {{ transform-origin:50% 50%; }}
.bar {{ display:flex; justify-content:space-between; align-items:center; }}
.bar span {{ font: 600 26px GSF; opacity:.85; }}
.slot {{ border-radius:38px; overflow:hidden; }}
.slot svg, .slot img {{ display:block; width:100%; height:100%; object-fit:contain; }}
.hueco {{ border: 5px dashed {ink}; opacity:.6; display:grid; place-items:center; text-align:center; }}
.hueco b {{ display:block; font: 800 52px Gluten; }}
.hueco span {{ display:block; font: 500 24px GSF; margin-top:6px; padding:0 20px; }}
.k {{ font: 680 30px Gluten; letter-spacing:.16em; text-transform:uppercase; }}
.body {{ font: 460 34px/1.3 GSF; margin:0; opacity:.92; }}
.day {{ font: 760 {104 if story else 92}px/1 Gluten; letter-spacing:.07em; }}
.hero-wrap {{ position:relative; }}
.hero {{ font-family:Gluten; font-weight:840; line-height:.8; letter-spacing:-.02em; white-space:nowrap; }}
.echo {{ position:absolute; left:0; top:0; color:transparent; -webkit-text-stroke: 4px {ink}; }}
.stack {{ font: 820 {118 if story else 116}px/.9 Gluten; }}
.ln {{ white-space:nowrap; }}
.ln > span {{ display:inline-block; }}
.sticker {{ background:{ink}; color:{bg}; font: 760 {58 if story else 52}px/1 Gluten; padding:18px 34px 24px; border-radius:999px; }}
.q {{ font: 830 {big_q}px/.98 Gluten; letter-spacing:-.01em; }}
.quote {{ font-size:{150 if story else 136}px; line-height:1.06; }}
.hi {{ display:inline-block; background:{ink}; color:{bg}; border-radius:999px; padding:0 .28em .12em; margin:.04em 0 .06em -.1em; }}
.qm {{ font: 840 {420 if story else 380}px/1 Gluten; opacity:1; }}
.sig {{ font-size:28px; }}
.sq {{ position:relative; }}
.sq svg {{ position:absolute; left:2%; width:96%; bottom:-.13em; height:.2em; overflow:visible; }}
.sq path {{ fill:none; stroke:{ink}; stroke-width:8; stroke-linecap:round; }}
.chips {{ display:flex; flex-wrap:wrap; gap:14px; width:936px; }}
.chips.col {{ flex-direction:column; align-items:flex-start; width:auto; gap:14px; }}
.chip {{ display:inline-block; background:{ink}; color:{bg}; border-radius:999px; padding:14px 30px 16px; font: 640 30px GSF; }}
.chip:nth-child(2n) {{ transform:rotate(-1.5deg); }}
"""

    def sl(w: int, h: int) -> str:
        return slot(w, h, bg, ink, t.get("ilustracion"), hueco, "s" + t["id"] + ("s" if story else "p"))

    body = f'<div class="p">{bar(ink, 240 if story else 60)}{LAYOUTS[t["id"]](t, story, sl)}</div>'
    return body, css


# ============================================================================ animación
RENDER_JS = """
(() => {
const D = %DUR%;
const cl = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
const eo = p => 1 - Math.pow(1 - p, 3);
const eio = p => p < .5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2;
const spring = p => p >= 1 ? 1 : 1 - Math.exp(-6 * p) * Math.cos(9.5 * p);
const back = p => { const c = 1.7; return 1 + (c + 1) * Math.pow(p - 1, 3) + c * Math.pow(p - 1, 2); };
// Echo offsets: read final position once
document.querySelectorAll('[data-a="echo"]').forEach(e => { e.style.left = e.dataset.x + 'px'; e.style.top = e.dataset.y + 'px'; });
// Sellos: reparte el texto por todo el círculo (textLength no se aplica en textPath)
const fit = () => document.querySelectorAll('.stamp text').forEach(tx => {
  const r = +tx.dataset.r, n = tx.textContent.length, circ = 2 * Math.PI * r;
  tx.setAttribute('letter-spacing', 0);
  const len = tx.getComputedTextLength();
  if (len > circ - n * 1.5) { tx.setAttribute('font-size', (31 * (circ - n * 1.5) / len).toFixed(1)); }
  tx.setAttribute('letter-spacing', ((circ - tx.getComputedTextLength()) / n).toFixed(2));
});
window.render = (t, still) => {
  if (!window.__fit) { fit(); window.__fit = 1; }
  const ex = still ? 0 : eio(cl((t - (D - .62)) / .48));          // salida suave al final, para el bucle
  for (const el of document.querySelectorAll('[data-a]')) {
    const k = el.dataset.a, d = +el.dataset.d, du = +el.dataset.t;
    const p = still ? 1 : cl((t - d) / du);
    let tr = '', op = 1;
    if (k === 'rise') { tr = `translateY(${(1 - eo(p)) * (+el.dataset.y || 36)}px)`; op = cl(p * 1.8); }
    else if (k === 'fade') { op = eo(p); tr = `translateY(${(1 - eo(p)) * 14}px)`; }
    else if (k === 'pop') { const e = spring(p); tr = `scale(${.45 + .55 * e}) rotate(${(1 - eo(p)) * (+el.dataset.r || -8)}deg)`; op = cl(p * 6); }
    else if (k === 'echo') { const e = eio(p); tr = `translate(${(e - 1) * el.dataset.x}px, ${(e - 1) * el.dataset.y}px)`; op = cl(p * 4); }
    else if (k === 'stamp') { tr = `scale(${Math.max(0, back(p))}) rotate(${(1 - eo(p)) * -100}deg)`; op = cl(p * 5); }
    else if (k === 'chip') { tr = `translateY(${(1 - eo(p)) * 70}px) scale(${.85 + .15 * back(p)})`; op = cl(p * 3); }
    if (k === 'draw') { el.style.strokeDashoffset = 1 - eio(p); el.style.opacity = (p > .02 ? 1 : 0) * (1 - ex); continue; }
    const base = el.classList.contains('chip') && [...el.parentNode.children].indexOf(el) % 2 ? ' rotate(-1.5deg)' : '';
    el.style.transform = tr + base + (ex ? ` scale(${1 - .05 * ex})` : '');
    el.style.opacity = op * (1 - ex);
  }
  for (const g of document.querySelectorAll('[data-spin]'))
    g.setAttribute('transform', `rotate(${still ? 0 : t * +g.dataset.spin} 150 150)`);
  for (const pt of document.querySelectorAll('pattern[data-dx]')) {      // medio paso de baldosa = mismo dibujo
    const f = still ? 0 : t / D;
    pt.setAttribute('x', -f * pt.dataset.dx); pt.setAttribute('y', -f * pt.dataset.dy);
  }
  document.querySelectorAll('.wm .L').forEach((g, i) => {
    let dy = 0, r = 0;
    if (!still) for (const w0 of [2.2, 4.1]) {
      const s = Math.sin(Math.PI * cl((t - w0 - i * .07) / .42));
      dy -= s * 260; r += s * (i % 2 ? 6 : -6);
    }
    const b = g.__bb || (g.__bb = g.getBBox());
    g.setAttribute('transform', `translate(0 ${dy}) rotate(${r} ${b.x + b.width / 2} ${b.y + b.height / 2})`);
  });
};
})();
""".replace("%DUR%", str(DUR))


def ffmpeg_bin() -> str | None:
    import glob
    import os
    return shutil.which("ffmpeg") or (glob.glob(os.path.expanduser("~/.cache/ms-playwright/ffmpeg-*/ffmpeg-linux")) or [None])[0]


def record(pg, mp4: Path, w: int, h: int) -> None:
    """Graba la página abierta en `pg` fotograma a fotograma y la monta en MP4 + hoja de contacto de 6 fotogramas."""
    ff = ffmpeg_bin()
    if not ff:
        print("AVISO: no encuentro ffmpeg (sudo apt install ffmpeg), solo quedan los PNG")
        return
    tmp = mp4.parent / "_frames"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir()
    n = round(DUR * FPS)
    for f in range(n):
        pg.evaluate(f"window.render({f / FPS})")
        pg.screenshot(path=str(tmp / f"{f:04d}.png"))
    # sRGB → BT.709 de rango limitado, etiquetado, para que los colores salgan iguales que en el PNG
    subprocess.run([ff, "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", str(tmp / "%04d.png"),
                    "-vf", "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p",
                    "-c:v", "libx264", "-preset", "slow", "-crf", "20", "-profile:v", "high", "-r", str(FPS),
                    "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv",
                    "-an", "-movflags", "+faststart", str(mp4)], check=True)
    shutil.rmtree(tmp)
    picks = [round(s * FPS) for s in (.45, .8, 1.2, 1.7, 3.2, n / FPS - .1)]
    sel = "+".join(f"eq(n\\,{min(x, n - 1)})" for x in picks)
    sheet = mp4.with_name(mp4.stem + "-frames.png")
    subprocess.run([ff, "-y", "-loglevel", "error", "-i", str(mp4), "-vf",
                    f"select='{sel}',scale={w // 3}:{h // 3},tile=3x2:padding=6", "-vsync", "0", "-frames:v", "1",
                    str(sheet)], check=True)
    print(f"   vídeo {mp4.name}: {mp4.stat().st_size / 1e6:.2f} MB")


# ============================================================================ salida
def main() -> None:
    video = "--sin-video" not in sys.argv
    only = [a for a in sys.argv[1:] if not a.startswith("--")]
    OUT.mkdir(exist_ok=True)
    with Renderer() as r:
        if not only:  # se borra lo generado antes, para que no queden archivos con nombres viejos
            for f in [*OUT.glob("*.png"), *OUT.glob("*.mp4")]:
                f.unlink()
        for tpl in TEMPLATES:
            if only and tpl["id"] not in only:
                continue
            # una diapositiva por idioma; el hueco marcado sale una sola vez (el diseño es el mismo)
            jobs = [(lang, n, False) for lang, n in LANGS] + [("es", 0, True)]
            for story, (lang, n, hueco) in ((s, j) for s in (False, True) for j in jobs):
                    t = {**tpl, **TEXTS[lang][tpl["id"]]}
                    body, css = page(t, story, hueco)
                    fmt = "story" if story else "post"
                    name = f'{fmt}-{tpl["id"]}-hueco' if hueco else f'{fmt}-{tpl["id"]}-{n}-{lang}'
                    w, h = (1080, 1920) if story else (1080, 1350)
                    doc = (f"<!doctype html><html><head><meta charset='utf-8'><style>{fontface()}"
                           f"html,body{{margin:0;padding:0;width:{w}px;height:{h}px;overflow:hidden}}"
                           f"*{{box-sizing:border-box}}{css}</style></head><body>{body}"
                           f"<script>{RENDER_JS}</script></body></html>")
                    tmp = OUT / f"{name}.tmp.html"
                    tmp.write_text(doc)
                    r.pg.set_viewport_size({"width": w, "height": h})
                    r.pg.goto(tmp.as_uri())
                    r.pg.evaluate("document.fonts.ready")
                    r.pg.wait_for_timeout(80)
                    r.pg.evaluate("window.render(0, true)")
                    r.pg.screenshot(path=str(OUT / f"{name}.png"))
                    # Aviso si algo se sale de la página (o, en historias, de la zona libre de botones).
                    lo, hi = (230, h - 290) if story else (40, h - 40)
                    bad = r.pg.evaluate(f"""() => [...document.querySelectorAll('.p > .abs')].filter(e => {{
                        const q = e.getBoundingClientRect(); return q.top < {lo} || q.bottom > {hi} || q.left < 30 || q.right > {w - 30};
                        }}).map(e => e.className + ' ' + e.textContent.slice(0, 20))""")
                    print(("AVISO: se sale " + str(bad) + " " if bad else "ok ") + name)
                    if video and not hueco:
                        record(r.pg, OUT / f"{name}.mp4", w, h)
                    tmp.unlink()


if __name__ == "__main__":
    main()
