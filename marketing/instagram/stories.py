"""Stories diarias de @runch.run (1080 x 1920) como vídeo corto con música, listas para programar en Meta Business Suite.

    uv run --no-project --with playwright --with fonttools --with numpy python marketing/instagram/stories.py              # todo
    uv run --no-project --with playwright --with fonttools --with numpy python marketing/instagram/stories.py --sin-video  # solo pósteres
    uv run --no-project --with playwright --with fonttools --with numpy python marketing/instagram/stories.py 2026-11-18    # un día

Los textos están en `stories-calendario.json`; el diseño es el de la capa ilustrada (marketing/marca/: logotipo, Gluten,
corredores, sello) con la misma maqueta que la story de la temporada: logotipo arriba a la izquierda, @runch.run a la
derecha, la hora gigante con sombra desplazada y un botón crema a lo ancho abajo.

Cada día sale una pareja a las 09:00 (1 catalán, 2 castellano): «Avui a les 19:00 / Hoy a las 19:00» con el gancho del
post del día y su portada en una tarjeta inclinada que entra deslizando. Variantes: reel (13 y 14-nov), reto (18-nov),
cuenta atrás del reto (19 a 25-nov), sorteo (26-nov). Los domingos, además, «El teu torn / Tu turno» a las 12:00 (3 y 4)
con un hueco libre para la encuesta de Business Suite; el hueco solo se marca en `<nombre>-guia.png`, no en el vídeo.

Salida en out/stories/calendario/: `AAAA-MM-DD_HHMM_N-idioma.mp4` (9 s, 30 fps, H.264 yuv420p, música propia afro house de 120 bpm
hecha por código en marketing/marca/musica/afro_house.py, a −14 LUFS, AAC 160k), su póster `.png`, una hoja de contacto por semana y GUIA.md.
Cada fotograma se pinta llamando a render(t) en la página; el primero y el último son iguales (fondo y logotipo).

Con `--out=carpeta` (relativa a out/, p. ej. `--out=olivo`) las portadas de los posts se toman de out/<carpeta>/ (si
no están, de out/) y todo sale en out/<carpeta>/stories/calendario/.
"""
from __future__ import annotations

import datetime as dt
import html
import json
import os
import re
import shutil
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
MARCA = HERE.parent / "marca"
sys.path.insert(0, str(MARCA))

from kit import C, Renderer, fontface  # noqa: E402
from templates import ILL_DIR, ILLUS, ffmpeg_bin, stamp, wordmark_letters  # noqa: E402

BASE = HERE / "out"
SRC = Path(os.environ.get("RUNCH_STORIES_ROOT", BASE))   # raíz de las portadas (y de la salida); ver --out
OUT = SRC / "stories" / "calendario"
COPY = HERE / "stories-calendario.json"
LOOP = MARCA / "musica" / "afro-house-120bpm.wav"  # música propia (afro house, 120 bpm), la hace musica/afro_house.py
W, H = 1080, 1920
FPS, DUR = 30, 9.0
SAFE = (230, 1735)                                 # zona libre de la interfaz de stories (arriba / abajo)

# Fondo, tinta, sombra de la hora, pegatina «Nou post» (fondo, texto) y tinta del corredor. Una sola tinta por pieza;
# el olivo (marca) solo hace de segundo color en la pegatina y en la sombra.
THEMES = {
    "olive": dict(bg=C["brand"], ink=C["cream"], sh=C["olive_dark"], chip=(C["butter"], C["espresso"]), ill="crema"),
    "espresso": dict(bg=C["espresso"], ink=C["cream"], sh=C["brand"], chip=(C["olive_light"], C["espresso"]), ill="crema"),
    "sage": dict(bg=C["sage"], ink=C["espresso"], sh="#AAB495", chip=(C["brand"], C["cream"]), ill="espresso"),
    "sea": dict(bg=C["sea"], ink=C["cream"], sh="#163049", chip=(C["butter"], C["espresso"]), ill="crema"),
    "butter": dict(bg=C["butter"], ink=C["espresso"], sh="#DBC17A", chip=(C["brand"], C["cream"]), ill="espresso"),
    "cream": dict(bg=C["cream"], ink=C["brand"], sh="#D5DDB8", chip=(C["espresso"], C["cream"]), ill="olivo"),
    # Legado (marca anterior): solo para volver a pintar stories antiguas.
    "terracotta": dict(bg=C["terracotta"], ink=C["cream"], sh="#B8442A", chip=(C["butter"], C["espresso"]), ill="crema"),
}
CYCLE = ["olive", "espresso", "sage", "sea", "butter", "cream"]

DAYS = {"ca": ["dilluns", "dimarts", "dimecres", "dijous", "divendres", "dissabte", "diumenge"],
        "es": ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]}
MONTHS = {"ca": {11: "de novembre", 12: "de desembre"}, "es": {11: "de noviembre", 12: "de diciembre"}}
LANGS = [("ca", 1), ("es", 2)]

T = {  # textos fijos de la maqueta
    "ca": {"today": "Avui a les", "reel_today": "Avui reel", "new": "Nou post", "reel": "Reel",
           "reel_cta": "Mira'l amb so", "stamp": "UN POST CADA DIA · A LES 19:00 · ",
           "reto_k": "Repte Runch · avui a les 19:00", "reto_l": ["accessos", "beta"], "reto_s": "de 3 mesos",
           "reto_cta": "Comenta al post i participa", "reto_stamp": "SORTEIG · FINS AL 25 DE NOVEMBRE · ",
           "count": "Repte Runch · {n}", "left": ["Últim dia!", "Queda 1 dia", "Queden {n} dies"],
           "count_cta": "Comenta al post del repte", "last_cta": "Comenta al repte fins a les 23:59",
           "draw_k": "Repte Runch · sorteig", "draw_hero": "Avui", "draw_chip": "Sorteig",
           "draw_cta": "I a les 19:00, nou post",
           "turn_k": "El teu torn", "turn_cta": "Vota i mira què diu la resta", "turn_body": "I a les 19:00, nou post al feed.", "zone": "Enganxa aquí l'enquesta"},
    "es": {"today": "Hoy a las", "reel_today": "Hoy reel", "new": "Nuevo post", "reel": "Reel",
           "reel_cta": "Míralo con sonido", "stamp": "UN POST CADA DÍA · A LAS 19:00 · ",
           "reto_k": "Reto Runch · hoy a las 19:00", "reto_l": ["accesos", "beta"], "reto_s": "de 3 meses",
           "reto_cta": "Comenta en el post y participa", "reto_stamp": "SORTEO · HASTA EL 25 DE NOVIEMBRE · ",
           "count": "Reto Runch · {n}", "left": ["¡Último día!", "Queda 1 día", "Quedan {n} días"],
           "count_cta": "Comenta en el post del reto", "last_cta": "Comenta en el reto hasta las 23:59",
           "draw_k": "Reto Runch · sorteo", "draw_hero": "Hoy", "draw_chip": "Sorteo",
           "draw_cta": "Y a las 19:00, nuevo post",
           "turn_k": "Tu turno", "turn_cta": "Vota y mira qué dice el resto", "turn_body": "Y a las 19:00, nuevo post en el feed.", "zone": "Pega aquí la encuesta"},
}
RETO_END = dt.date(2026, 11, 25)


# ============================================================================ piezas
def A(kind: str, d: float, t: float = .6, **kw) -> str:
    """Marca un elemento para el vídeo: tipo de entrada, inicio y duración (s). En el póster no cambia nada."""
    extra = "".join(f' data-{k}="{v}"' for k, v in kw.items())
    return f'data-a="{kind}" data-d="{d:g}" data-t="{t:g}"{extra}'


def at(x: float, y: float, inner: str, rot: float = 0, anim: str = "", style: str = "", cls: str = "") -> str:
    """Elemento colocado en (x, y) y girado; la animación va en una capa interior para no pisar el giro."""
    return (f'<div class="abs {cls}" style="left:{x:.0f}px;top:{y:.0f}px;transform:rotate({rot}deg);{style}">'
            f'<div class="an" {anim}>{inner}</div></div>')


def rich(text: str) -> str:
    """Texto con la parte entre *asteriscos* en una pegatina rellena."""
    parts = re.split(r"\*([^*]+)\*", text)
    return "".join((f'<span class="hi{" nw" if len(p) <= 18 else ""}">{html.escape(p)}</span>' if i % 2 else html.escape(p))
                   for i, p in enumerate(parts))


def figure(name: str, ink: str, x: float, y: float, h: float, d: float) -> str:
    """Corredor suelto con el dibujo de alto h y su esquina en (x, y). corredor-1 entra corriendo y bota; corredor-2
    sube y se mece."""
    il = ILL[name]
    (iw, ih), (l, t, r, b) = il["size"], il["box"]
    k = h / (b - t)
    src = (ILL_DIR / f"{name}-{ink}.png").resolve().as_uri()
    img = (f'<img src="{src}" style="position:absolute;left:{-l * k:.1f}px;top:{-t * k:.1f}px;'
           f'width:{iw * k:.1f}px;height:{ih * k:.1f}px">')
    return (f'<div class="abs fig" style="left:{x:.0f}px;top:{y:.0f}px;width:{(r - l) * k:.0f}px;height:{h:.0f}px">'
            f'<div class="an" {A(il["move"], d, 1.0, x=220)}>{img}</div></div>')


# Ilustraciones de marketing/marca/ilustraciones/gemini/ (<nombre>-<tinta>.png): tamaño del PNG, caja del dibujo y
# cómo se mueve en el vídeo ("run" entra corriendo y bota; "sway" sube y se mece).
ILL = {**ILLUS, **{n: {"size": sz, "box": bx, "move": mv} for n, sz, bx, mv in [
    ("amanecer", (1729, 1406), (40, 40, 1690, 1367), "sway"),
    ("cansado-feliz", (1092, 1491), (40, 40, 1053, 1453), "sway"),
    ("corredora-mayor", (891, 1549), (40, 40, 852, 1510), "run"),
    ("corriendo-perro", (1271, 1547), (40, 40, 1232, 1508), "run"),
    ("estirando-taza", (1381, 1057), (40, 40, 1342, 1018), "sway"),
    ("grupo-corriendo", (1802, 1173), (40, 40, 1763, 1134), "run"),
    ("mirando-reloj", (824, 1539), (40, 40, 785, 1500), "sway"),
    ("silla-deportiva", (1455, 1438), (40, 39, 1416, 1399), "run"),
    ("yema-cafe", (1268, 1554), (40, 40, 1229, 1515), "sway"),
    ("yema-corriendo", (1245, 1152), (40, 40, 1206, 1113), "run"),
]}}


def fit_figure(name: str, ink: str, x: float, y: float, w: float, h: float, d: float, align: str = "center") -> str:
    """Ilustración encajada en la caja (x, y, w, h): lo más grande que quepa, apoyada abajo y pegada al lado `align`."""
    l, t, r, b = ILL[name]["box"]
    k = min(w / (r - l), h / (b - t))
    fw, fh = (r - l) * k, (b - t) * k
    fx = x if align == "left" else x + w - fw if align == "right" else x + (w - fw) / 2
    return figure(name, ink, fx, y + h - fh, fh, d)


def fig_w(name: str, h: float) -> float:
    l, t, r, b = ILL[name]["box"]
    return h * (r - l) / (b - t)


def card(src: Path, x: float, y: float, w: float, rot: float, chip: str, side: int, d: float = 1.25) -> str:
    """Portada del post en una tarjeta inclinada que entra deslizando desde su lado (side=+1 derecha, -1 izquierda),
    con la pegatina «Nou post» en la esquina de fuera."""
    h = w * 1.25
    cx = -34 if side > 0 else w - 150
    chip_html = (f'<div class="cchip" style="left:{cx:.0f}px;top:-40px;transform:rotate({-7 * side}deg)">'
                 f'<div class="an" {A("pop", d + .65, .8, r=-14 * side)}>{html.escape(chip)}</div></div>')
    return (f'<div class="abs cardw" style="left:{x:.0f}px;top:{y:.0f}px;width:{w:.0f}px;height:{h:.0f}px;'
            f'transform:rotate({rot}deg)"><div class="an" {A("card", d, 1.0, x=700 * side, r=14 * side)}>'
            f'<div class="card" style="width:{w:.0f}px;height:{h:.0f}px"><img src="{src.resolve().as_uri()}"></div>'
            f'{chip_html}</div></div>')


def bar() -> str:
    return (f'<div class="abs bar" style="left:88px;right:90px;top:236px">{{WM}}<span>@runch.run</span></div>')


def pill(text: str, d: float = 2.0) -> str:
    return (f'<div class="abs" style="left:90px;right:90px;top:1615px"><div class="an pill" {A("chip", d, .6)}>'
            f'{html.escape(text)}</div></div>')


def kicker(text: str, y: int = 432, d: float = .1) -> str:
    return (f'<div class="abs" style="left:90px;top:{y}px"><div class="an k" data-maxw="900" {A("rise", d, .55, y=24)}>'
            f'{html.escape(text)}</div></div>')


def countdown(text: str, y: int = 398, d: float = .1) -> str:
    return (f'<div class="abs" style="left:84px;top:{y}px;transform:rotate(-2deg)">'
            f'<div class="an kpill" data-maxw="900" {A("pulse", d, .8, r=-6)}>{html.escape(text)}</div></div>')


def hero(text: str, x: int, y: int, size: int, d: float = .45, rot: float = -4) -> str:
    return at(x, y, f'<div class="hero" data-maxw="880" style="font-size:{size}px">{html.escape(text)}</div>', rot,
              A("hero", d, 1.0, r=-9), style="transform-origin:50% 50%")


# ============================================================================ composiciones
def teaser(s: dict, th: dict) -> str:
    """Día normal: «Avui a les / 19:00», el gancho y la tarjeta con la portada. Con ilustración del día
    ("ill" en el JSON) se turna el lado; sin ella, sale el sello."""
    t = T[s["lang"]]
    v = s["variant"]
    top = countdown(s["count"]) if s.get("count") else kicker(s["date_label"])
    reel = s.get("kind") == "reel"
    out = [top,
           at(90, 500 if s.get("count") else 486, f'<div class="day">{html.escape(t["reel_today"] if reel else t["today"])}</div>', 0,
              A("rise", .25, .6, y=40)),
           hero("19:00", 66, 630, 314),
           f'<div class="abs" style="left:90px;top:950px;width:900px"><div class="an hook" data-maxh="175" '
           f'{A("fade", .95, .7)}>{rich(s["hook"])}</div></div>']
    chip = t["reel"] if reel else t["new"]
    ill = s.get("ill")
    if not ill:     # sin ilustración: sello a la izquierda, tarjeta a la derecha
        out += [card(s["cover"], 610, 1175, 316, 5, chip, 1),
                at(130, 1225, stamp(t["stamp"], 300, th["ink"], th["bg"]), -6, A("stamp", 1.5, .9))]
    elif v % 2:     # tarjeta a la izquierda, ilustración a la derecha
        out += [card(s["cover"], 116, 1175, 316, -5, chip, -1),
                fit_figure(ill, th["ill"], 540, 1180, 460, 405, 1.05, "right")]
    else:           # ilustración a la izquierda, tarjeta a la derecha
        out += [card(s["cover"], 610, 1175, 316, 4, chip, 1),
                fit_figure(ill, th["ill"], 90, 1180, 460, 405, 1.2, "left")]
    out.append(pill(s["cta"]))
    return "".join(out)


def reto(s: dict, th: dict) -> str:
    """18-nov: el «3» gigante, «accessos beta» y «de 3 mesos», la tarjeta del post del reto y «Comenta al post»."""
    t = T[s["lang"]]
    lines = "".join(f'<div class="ln"><span class="an" {A("rise", .7 + i * .12, .6, y=50)}>{html.escape(w)}</span></div>'
                    for i, w in enumerate(t["reto_l"]))
    return "".join([
        kicker(t["reto_k"]),
        hero("3", 70, 520, 560, .4, -6),
        at(420, 560, f'<div class="stack">{lines}</div>', -3),
        at(440, 812, f'<div class="sticker">{html.escape(t["reto_s"])}</div>', 4, A("pop", 1.05, .8, r=12)),
        f'<div class="abs" style="left:90px;top:1000px;width:900px"><div class="an hook small" data-maxh="150" '
        f'{A("fade", 1.0, .7)}>{rich(s["hook"])}</div></div>',
        card(s["cover"], 610, 1175, 316, 5, t["new"], 1, 1.35),
        figure("corredor-1", th["ill"], 120, 1200, 370, 1.15),
        pill(t["reto_cta"]),
    ])


def sorteo(s: dict, th: dict) -> str:
    """26-nov (provisional): «Avui» gigante, «la resposta del repte i qui s'emporta els accessos beta» y la tarjeta
    del reto con «Sorteig». La story de verdad (respuesta y ganadores) se hace ese día."""
    t = T[s["lang"]]
    return "".join([
        kicker(t["draw_k"]),
        hero(t["draw_hero"], 66, 540, 330, .4, -5),
        f'<div class="abs" style="left:90px;top:920px;width:900px"><div class="an hook" data-maxh="200" '
        f'{A("fade", .95, .7)}>{rich(s["hook"])}</div></div>',
        card(s["cover"], 116, 1175, 316, -5, t["draw_chip"], -1),
        figure("corredor-1", th["ill"], 1000 - fig_w("corredor-1", 380), 1195, 380, 1.05),
        pill(t["draw_cta"]),
    ])


ZONE = (150, 990, 780, 360)   # hueco para la encuesta: x, y, ancho, alto


def tu_turno(s: dict, th: dict) -> str:
    """Domingo 12:00: la pregunta arriba, el hueco libre en medio para la encuesta y la corredora con la taza."""
    t = T[s["lang"]]
    q = s["turn"]
    lines = []
    for i, ln in enumerate(q["lines"]):
        cls = "hi" if ln.startswith("*") else ""
        lines.append(f'<div class="ln"><span class="an {cls}" {A("pop" if cls else "rise", .3 + i * .13, .7, y=50, r=-8)}>'
                     f'{rich(ln) if not cls else html.escape(ln.replace("*", ""))}</span></div>')
    x, y, w, h = ZONE
    zone = (f'<div class="abs zone" style="left:{x}px;top:{y}px;width:{w}px;height:{h}px"><div><b>{t["zone"]}</b>'
            f'<span>Business Suite · {w} × {h} px</span><span>{" / ".join(html.escape(o) for o in q["options"])}</span>'
            f'</div></div>') if s.get("guide") else ""
    ill = s.get("ill") or "corredor-2"
    l, tt, r, b = ILL[ill]["box"]
    fw = min(330, 290 * (r - l) / (b - tt))
    return "".join([
        kicker(t["turn_k"]),
        f'<div class="abs" style="left:84px;top:505px"><div class="q" data-maxw="910">{"".join(lines)}</div></div>',
        zone,
        fit_figure(ill, th["ill"], 130, 1300, fw, 290, 1.0, "left"),
        f'<div class="abs" style="left:{130 + fw + 34:.0f}px;top:1430px;width:{950 - 130 - fw - 34:.0f}px"><div class="an hook small" {A("fade", 1.3, .7)}>'
        f'{html.escape(t["turn_body"])}</div></div>',
        pill(t["turn_cta"], 1.6),
    ])


LAYOUTS = {"teaser": teaser, "reel": teaser, "reto": reto, "sorteo": sorteo, "turno": tu_turno}


def page(s: dict) -> str:
    th = THEMES[s["bg"]]
    bg, ink, sh = th["bg"], th["ink"], th["sh"]
    cbg, cink = th["chip"]
    css = f"""
html,body{{margin:0;padding:0;width:{W}px;height:{H}px;overflow:hidden}}
*{{box-sizing:border-box}}
.p {{ position:relative; width:{W}px; height:{H}px; background:{bg}; color:{ink}; overflow:hidden; font-family:GSF; }}
.abs {{ position:absolute; }}
.an {{ transform-origin:50% 50%; }}
.bar {{ display:flex; justify-content:space-between; align-items:center; }}
.bar span {{ font: 600 40px GSF; opacity:.95; }}
.k {{ font: 780 46px Gluten; letter-spacing:.08em; text-transform:uppercase; white-space:nowrap; }}
.kpill {{ display:inline-block; background:{ink}; color:{bg}; font: 780 38px/1 Gluten; letter-spacing:.06em;
  text-transform:uppercase; padding:13px 28px 17px; border-radius:999px; white-space:nowrap; }}
.day {{ font: 880 108px/1 Gluten; white-space:nowrap; }}
.hero {{ font-family:Gluten; font-weight:900; line-height:.85; white-space:nowrap; text-shadow: 10px 12px 0 {sh}; }}
.hook {{ font: 620 56px/1.2 GSF; letter-spacing:-.005em; }}
.hook.small {{ font-size:46px; font-weight:560; }}
.hi {{ background:{ink}; color:{bg}; border-radius:16px; padding:0 .2em .04em; margin:0 -.04em;
  -webkit-box-decoration-break:clone; box-decoration-break:clone; }}
.hi.nw {{ white-space:nowrap; }}
.card {{ border:6px solid {ink}; border-radius:24px; overflow:hidden; box-shadow: 14px 16px 0 {sh}; background:{ink}; }}
.card img {{ display:block; width:100%; height:100%; object-fit:cover; object-position:50% 50%; }}
.cchip {{ position:absolute; z-index:2; }}
.cchip .an {{ display:inline-block; background:{cbg}; color:{cink}; font: 800 38px/1 Gluten; padding:14px 26px 18px;
  border-radius:999px; white-space:nowrap; box-shadow: 0 0 0 5px {bg}; }}
.pill {{ background:{ink}; color:{bg}; border-radius:999px; padding:26px 0; font: 700 50px/1.2 GSF; text-align:center;
  white-space:nowrap; }}
.stack {{ font: 880 104px/.92 Gluten; }}
.ln {{ white-space:nowrap; }}
.ln > span {{ display:inline-block; }}
.sticker {{ background:{ink}; color:{bg}; font: 800 58px/1 Gluten; padding:18px 34px 24px; border-radius:999px; }}
.q {{ font: 880 112px/1.04 Gluten; }}
.q .hi {{ border-radius:999px; padding:0 .28em .1em; margin:.04em 0 .06em -.06em; }}
.zone {{ border:6px dashed {ink}; border-radius:36px; display:grid; place-items:center; text-align:center; opacity:.8; }}
.zone b {{ display:block; font: 800 54px Gluten; }}
.zone span {{ display:block; font: 500 30px GSF; margin-top:8px; }}
"""
    body = LAYOUTS[s["kind"]](s, th).replace("{WM}", "")
    doc = (f"<!doctype html><html><head><meta charset='utf-8'><style>{fontface()}{css}</style></head><body>"
           f"<div class='p'>{bar().replace('{WM}', wordmark_letters(ink, 92))}{body}</div>"
           f"<script>{RENDER_JS}</script></body></html>")
    return doc


# ============================================================================ animación
RENDER_JS = """
(() => {
const D = %DUR%;
const cl = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
const eo = p => 1 - Math.pow(1 - p, 3);
const eio = p => p < .5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2;
const spring = p => p >= 1 ? 1 : 1 - Math.exp(-6 * p) * Math.cos(9.5 * p);
const soft = p => p >= 1 ? 1 : 1 - Math.exp(-5 * p) * Math.cos(7 * p);
const back = p => { const c = 1.7; return 1 + (c + 1) * Math.pow(p - 1, 3) + c * Math.pow(p - 1, 2); };
const fit = () => {
  // textos que no caben: se baja la letra hasta que caben (ancho o alto máximo)
  document.querySelectorAll('[data-maxw]').forEach(el => {
    let fs = parseFloat(getComputedStyle(el).fontSize);
    while (el.scrollWidth > +el.dataset.maxw && fs > 20) { fs -= 2; el.style.fontSize = fs + 'px'; }
  });
  document.querySelectorAll('[data-maxh]').forEach(el => {
    let fs = parseFloat(getComputedStyle(el).fontSize);
    while (el.scrollHeight > +el.dataset.maxh && fs > 20) { fs -= 2; el.style.fontSize = fs + 'px'; }
  });
  // sellos: reparte el texto por todo el círculo
  document.querySelectorAll('.stamp text').forEach(tx => {
    const r = +tx.dataset.r, n = tx.textContent.length, circ = 2 * Math.PI * r;
    tx.setAttribute('letter-spacing', 0);
    const len = tx.getComputedTextLength();
    if (len > circ - n * 1.5) tx.setAttribute('font-size', (31 * (circ - n * 1.5) / len).toFixed(1));
    tx.setAttribute('letter-spacing', ((circ - tx.getComputedTextLength()) / n).toFixed(2));
  });
};
const SH = getComputedStyle(document.querySelector('.hero') || document.body).textShadow;
window.render = (t, still) => {
  if (!window.__fit) { fit(); window.__fit = 1; }
  const ex = still ? 0 : eio(cl((t - (D - .62)) / .48));          // salida suave al final, para el bucle
  for (const el of document.querySelectorAll('[data-a]')) {
    const k = el.dataset.a, d = +el.dataset.d, du = +el.dataset.t;
    const p = still ? 1 : cl((t - d) / du);
    let tr = '', op = 1;
    if (k === 'rise') { tr = `translateY(${(1 - eo(p)) * (+el.dataset.y || 36)}px)`; op = cl(p * 1.8); }
    else if (k === 'fade') { op = eo(p); tr = `translateY(${(1 - eo(p)) * 18}px)`; }
    else if (k === 'pop') { const e = spring(p); tr = `scale(${.45 + .55 * e}) rotate(${(1 - eo(p)) * (+el.dataset.r || -8)}deg)`; op = cl(p * 6); }
    else if (k === 'pulse') {   // entra con rebote y luego late dos veces, suave
      const e = spring(p);
      let s = .45 + .55 * e;
      if (!still) for (const w0 of [3.2, 5.6]) s += .045 * Math.sin(Math.PI * cl((t - w0) / .5));
      tr = `scale(${s}) rotate(${(1 - eo(p)) * (+el.dataset.r || -6)}deg)`; op = cl(p * 6);
    }
    else if (k === 'hero') {    // la hora entra con rebote y se asienta; la sombra se separa después
      const e = soft(p);
      tr = `scale(${.5 + .5 * e}) rotate(${(1 - eo(p)) * (+el.dataset.r || -8)}deg)`; op = cl(p * 6);
      const q = still ? 1 : eio(cl((t - d - .35) / .6));
      const h = el.firstElementChild;
      if (h && SH && SH !== 'none') h.style.textShadow = SH.replace(/(-?[\\d.]+)px (-?[\\d.]+)px/, (m, a, b) => `${a * q}px ${b * q}px`);
    }
    else if (k === 'stamp') { tr = `scale(${Math.max(0, back(p))}) rotate(${(1 - eo(p)) * -100}deg)`; op = cl(p * 5); }
    else if (k === 'chip') { tr = `translateY(${(1 - eo(p)) * 70}px) scale(${.85 + .15 * back(p)})`; op = cl(p * 3); }
    else if (k === 'card') {    // entra deslizando desde su lado, gira hasta su sitio y luego flota muy poco
      const e = back(p), fl = still ? 0 : cl((t - d - du) / 1.2);
      const fy = Math.sin(2 * Math.PI * (t - d - du) / 3) * 6 * fl, fr = Math.sin(2 * Math.PI * (t - d - du) / 3.6) * .6 * fl;
      tr = `translate(${(1 - e) * +el.dataset.x}px, ${fy}px) rotate(${(1 - eo(p)) * +el.dataset.r + fr}deg)`;
      op = cl(p * 4);
    }
    if (k === 'run') {           // entra corriendo desde la izquierda, bota a ~170 pasos/min y al final sale por la derecha
      const bob = still ? 0 : -Math.abs(Math.sin(Math.PI * 2.85 * t)) * 3 * cl(p * 1.5);
      const lean = (1 - eo(p)) * -5;
      el.style.transform = `translate(${(1 - eo(p)) * -el.dataset.x + ex * 140}px, ${bob}px) rotate(${lean}deg)`;
      el.style.opacity = cl(p * 3) * (1 - ex);
      continue;
    }
    if (k === 'sway') {          // sube desde abajo y luego se mece despacio, apoyada en los pies
      const sw = still ? 0 : Math.sin(2 * Math.PI * (t - d) / 2.6) * 1.3 * cl((t - d - du * .5) / 1.2);
      el.style.transformOrigin = '50% 100%';
      el.style.transform = `translateY(${(1 - eo(p)) * 60}px) rotate(${sw}deg)` + (ex ? ` scale(${1 - .05 * ex})` : '');
      el.style.opacity = cl(p * 2.5) * (1 - ex);
      continue;
    }
    el.style.transform = tr + (ex ? ` scale(${1 - .05 * ex})` : '');
    el.style.opacity = op * (1 - ex);
  }
  for (const g of document.querySelectorAll('[data-spin]'))
    g.setAttribute('transform', `rotate(${still ? 0 : t * +g.dataset.spin} 150 150)`);
  document.querySelectorAll('.wm .L').forEach((g, i) => {      // el logotipo hace una ola, suave, dos veces
    let dy = 0, r = 0;
    if (!still) for (const w0 of [2.9, 6.2]) {
      const s = Math.sin(Math.PI * cl((t - w0 - i * .08) / .46));
      dy -= s * 150; r += s * (i % 2 ? 5 : -5);
    }
    const b = g.__bb || (g.__bb = g.getBBox());
    g.setAttribute('transform', `translate(0 ${dy}) rotate(${r} ${b.x + b.width / 2} ${b.y + b.height / 2})`);
  });
};
})();
""".replace("%DUR%", str(DUR))


# ============================================================================ calendario
def plan() -> list[dict]:
    """Todas las stories, en orden: fecha, hora, número, idioma, tipo, fondo y textos."""
    data = json.loads(COPY.read_text())
    out, prev = [], None
    for i, day in enumerate(data["days"]):
        date = dt.date.fromisoformat(day["date"])
        kind = day.get("kind", "teaser")
        # fondo: siguiente color del ciclo que no repita el de ayer ni el de la portada del post
        j = i
        while CYCLE[j % 6] in (prev, day.get("cover_bg")) or (kind == "reto" and CYCLE[j % 6] == "cream"):
            j += 1
        bg = day.get("bg") or CYCLE[j % 6]
        prev = bg
        left = (RETO_END - date).days
        for lang, n in LANGS:
            t = T[lang]
            cover = day["cover"][lang] if isinstance(day["cover"], dict) else day["cover"]
            s = dict(date=day["date"], time="0900", n=n, lang=lang, kind=kind, bg=bg, variant=i, ill=day.get("ill"),
                     cover=cover_path(cover), hook=day["hook"][lang],
                     date_label=f'{DAYS[lang][date.weekday()]} {date.day} {MONTHS[lang][date.month]}',
                     cta=data["cta"][lang][i % len(data["cta"][lang])])
            if kind == "reel":
                s["cta"] = t["reel_cta"]
            if date > dt.date(2026, 11, 18) and left >= 0 and kind == "teaser":
                word = t["left"][0] if left == 0 else t["left"][1] if left == 1 else t["left"][2].format(n=left)
                s["count"] = t["count"].format(n=word)
                s["cta"] = t["last_cta"] if left == 0 else t["count_cta"]
            out.append(s)
        if day["date"] in data["tu_turno"]:
            tbg = next(c for c in ["espresso", "sea", "olive"] if c != bg)
            for lang, n in LANGS:
                out.append(dict(date=day["date"], time="1200", n=n + 2, lang=lang, kind="turno", bg=tbg,
                                turn=data["tu_turno"][day["date"]][lang], hook="",
                                ill=data["tu_turno"][day["date"]].get("ill")))
    return out


def cover_path(rel: str) -> Path:
    """Portada del post: la de la raíz elegida (--out) si existe; si no, la de out/."""
    return SRC / rel if (SRC / rel).exists() else BASE / rel


def name(s: dict) -> str:
    return f'{s["date"]}_{s["time"]}_{s["n"]}-{s["lang"]}'


# ============================================================================ salida
def music(dur: float = DUR) -> Path:
    """La pista: el bucle afro house de `dur` segundos (entrada y salida de 0,2 s) a −14 LUFS, AAC 160k.
    Se hace una vez por duración y se copia tal cual en cada vídeo."""
    ff = ffmpeg_bin()
    m4a = OUT / f"_musica-afro-house-{dur:g}s.m4a"
    if m4a.exists():
        return m4a
    sys.path.insert(0, str(LOOP.parent))
    import afro_house  # noqa: PLC0415  (necesita numpy: uv run --with numpy)
    afro_house.write(dur)
    base = ["-i", str(LOOP), "-t", str(dur)]
    pre = "anull"
    r = subprocess.run([ff, "-hide_banner", *base, "-af", f"{pre},loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json",
                        "-f", "null", "-"], capture_output=True, text=True, check=True)
    m = json.loads(r.stderr[r.stderr.rindex("{"):r.stderr.rindex("}") + 1])
    ln = (f"loudnorm=I=-14:TP=-1.5:LRA=11:linear=true:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
          f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}")
    subprocess.run([ff, "-y", "-loglevel", "error", *base, "-af", f"{pre},{ln}", "-ar", "44100", "-c:a", "aac",
                    "-b:a", "160k", str(m4a)], check=True)
    return m4a


def check(pg, s: dict) -> list[str]:
    """Avisos: algo fuera de la zona segura o de la página, o un texto que se ha tenido que encoger mucho."""
    lo, hi = SAFE
    return pg.evaluate(f"""() => [...document.querySelectorAll('.p > .abs')].filter(e => !e.classList.contains('zone')).filter(e => {{
        const q = e.getBoundingClientRect();
        return q.top < {lo} || q.bottom > {hi} || q.left < 40 || q.right > {W - 40};
      }}).map(e => e.className + ' «' + e.textContent.trim().slice(0, 24) + '»')""")


def one(job: tuple[dict, bool, Path | None]) -> str:
    s, video, m4a = job
    with Renderer() as r:
        return _one(r, s, video, m4a)


def _one(r, s: dict, video: bool, m4a: Path | None) -> str:
    nm = name(s)
    pg = r.pg
    pg.set_viewport_size({"width": W, "height": H})
    msgs = []
    for guide in ([False, True] if s["kind"] == "turno" else [False]):
        tmp = OUT / f"{nm}{'-guia' if guide else ''}.tmp.html"
        tmp.write_text(page({**s, "guide": guide}))
        pg.goto(tmp.as_uri())
        pg.evaluate("document.fonts.ready")
        pg.wait_for_timeout(120)
        pg.evaluate("window.render(0, true)")
        pg.screenshot(path=str(OUT / f"{nm}{'-guia' if guide else ''}.png"))
        if not guide:
            bad = check(pg, s)
            msgs.append(("AVISO se sale " + str(bad) + " ") if bad else "ok ")
            if video and m4a:
                record(pg, OUT / f"{nm}.mp4", m4a)
        tmp.unlink()
    size = (OUT / f"{nm}.mp4").stat().st_size / 1e6 if (OUT / f"{nm}.mp4").exists() else 0
    return f'{"".join(msgs)}{nm}' + (f"  {size:.2f} MB" if size else "")


def record(pg, mp4: Path, m4a: Path) -> None:
    """Graba la página fotograma a fotograma (los PNG van directos a ffmpeg) y le pone la música."""
    ff = ffmpeg_bin()
    n = round(DUR * FPS)
    p = subprocess.Popen([ff, "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(FPS), "-c:v", "png",
                          "-i", "-", "-i", str(m4a),
                          "-vf", "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p",
                          "-c:v", "libx264", "-preset", "slow", "-crf", "21", "-profile:v", "high", "-r", str(FPS),
                          "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv",
                          "-c:a", "copy", "-t", str(DUR), "-movflags", "+faststart", str(mp4)], stdin=subprocess.PIPE)
    for f in range(n):
        pg.evaluate(f"window.render({f / FPS})")
        p.stdin.write(pg.screenshot())
    p.stdin.close()
    if p.wait():
        raise RuntimeError(f"ffmpeg falló con {mp4.name}")


def frames_sheet(mp4: Path, dest: Path) -> None:
    """Hoja de 6 fotogramas de un vídeo, para revisar la animación sin abrirlo."""
    ff = ffmpeg_bin()
    picks = [round(x * FPS) for x in (.3, .7, 1.2, 1.8, 4.0, DUR - .05)]
    sel = "+".join(f"eq(n\\,{x})" for x in picks)
    subprocess.run([ff, "-y", "-loglevel", "error", "-i", str(mp4), "-vf",
                    f"select='{sel}',scale={W // 4}:{H // 4},tile=6x1:padding=6", "-vsync", "0", "-frames:v", "1",
                    str(dest)], check=True)


def weeks(stories: list[dict]) -> list[tuple[str, list[dict]]]:
    """Semanas de lunes a domingo (la primera empieza el miércoles 4)."""
    out: dict[str, list[dict]] = {}
    for s in stories:
        d = dt.date.fromisoformat(s["date"])
        monday = d - dt.timedelta(days=d.weekday())
        out.setdefault(monday.isoformat(), []).append(s)
    return list(out.items())


def contact_sheets(r, stories: list[dict]) -> list[Path]:
    paths = []
    for k, (monday, ss) in enumerate(weeks(stories), 1):
        d0, d1 = ss[0]["date"], ss[-1]["date"]
        cells = "".join(
            f'<figure><img src="{(OUT / (name(s) + ".png")).as_uri()}"><figcaption><b>{s["date"][8:]}/{s["date"][5:7]} '
            f'{s["time"][:2]}:{s["time"][2:]}</b> · {s["n"]}-{s["lang"]}</figcaption></figure>' for s in ss)
        css = ("body{background:#2a2420;font-family:GSF;color:#F7F3EC;padding:24px}h1{font:800 40px Gluten;margin:0 0 18px}"
               ".g{display:grid;grid-template-columns:repeat(8,270px);gap:14px}figure{margin:0}"
               "img{width:270px;height:480px;display:block;border-radius:10px}figcaption{font:500 18px GSF;margin-top:6px}")
        body = f'<h1>Stories · semana {k} · {d0} → {d1}</h1><div class="g">{cells}</div>'
        out = OUT / f"hoja-semana-{k}_{d0}_{d1}.png"
        r.png(body, out, 24 * 2 + 8 * 270 + 7 * 14, 600, css=css, full=True)
        paths.append(out)
    return paths


def guide_md(stories: list[dict]) -> str:
    """GUIA.md: cómo programarlas en Meta Business Suite y la tabla de todos los días."""
    data = json.loads(COPY.read_text())
    plain = lambda x: x.replace("*", "")  # noqa: E731
    rows = []
    by_day: dict[str, list[dict]] = {}
    for s in stories:
        by_day.setdefault(s["date"], []).append(s)
    for date, ss in by_day.items():
        d = dt.date.fromisoformat(date)
        for time in sorted({s["time"] for s in ss}):
            grp = [s for s in ss if s["time"] == time]
            ca = next(s for s in grp if s["lang"] == "ca")
            es = next(s for s in grp if s["lang"] == "es")
            if ca["kind"] == "extra":
                txt, note = es["text"], es["note"]
            elif ca["kind"] == "turno":
                txt = f'«{plain(" ".join(es["turn"]["lines"]))}» · encuesta: {" / ".join(es["turn"]["options"])}'
                note = "Sticker de encuesta (ver -guia.png)"
            else:
                tag = {"teaser": "", "reel": "Reel · ", "reto": "Reto · ", "sorteo": "Sorteo (provisional) · "}[es["kind"]]
                txt = tag + (f'{es["count"]} · ' if es.get("count") else "") + plain(es["hook"])
                note = {"reto": "Día del reto", "sorteo": "Hacer ese día la story real con la respuesta y las personas ganadoras",
                        "reel": "Reel a las 19:00"}.get(es["kind"], "")
            files = " → ".join(f'`{name(s)}.mp4`' for s in (ca, es))
            rows.append(f'| {DAYS["es"][d.weekday()][:3]} {d.day}-{d.month:02d} | {time[:2]}:{time[2:]} | {files} | {txt} | {note} |')
    turnos = "\n".join(
        f'- **{date}** 12:00: «{plain(" ".join(q["es"]["lines"]))}» — opciones: {" / ".join(q["es"]["options"])} '
        f'(catalán: «{plain(" ".join(q["ca"]["lines"]))}» — {" / ".join(q["ca"]["options"])})'
        for date, q in data["tu_turno"].items())
    first = stories[0]
    REL = OUT.relative_to(HERE.parent.parent).as_posix()
    WIN = str(OUT).replace("/", "\\")
    extras = "".join(f'- **{e["date"]} {e["time"][:2]}:{e["time"][2:]}:** {e["text"]} ({e["note"]}).\n'
                     for e in data.get("extras", []) if e["lang"] == "es")
    return f"""# Stories de @runch.run · 4-nov → 2-dic de 2026

Vídeos de 9 s con música (1080 × 1920, listos para subir). Cada día, a las **09:00**, dos stories seguidas: primero
la de **catalán** (`_1-ca`) y después la de **castellano** (`_2-es`). Los domingos, además, a las **12:00**,
«El teu torn / Tu turno» (`_3-ca` y `_4-es`), donde tú pones la encuesta.

Carpeta: `{REL}/` (en Windows:
`\\\\wsl.localhost\\Ubuntu{WIN}`).
Cada vídeo tiene su póster `.png` con el mismo nombre; las hojas `hoja-semana-*.png` enseñan la semana entera.

## Lo primero: mañana, miércoles 4 de noviembre, a las 09:00

`{name(first)}.mp4` y luego `{name(stories[1])}.mp4`.

## Cómo programarlas en Meta Business Suite (cada día)

1. Abre Meta Business Suite → **Crear historia** (en el móvil: botón **+** → **Historia**).
2. Elige la cuenta de Instagram **@runch.run** (si también sale Facebook, desmárcalo).
3. **Subir** → elige los archivos del día **en orden**: primero `…_1-ca.mp4`, después `…_2-es.mp4`. Salen como dos
   historias seguidas en ese orden.
4. No añadas texto ni música: el vídeo ya lleva las dos cosas.
5. Abajo, en vez de «Compartir ahora», pulsa la flecha → **Programar** → pon la **fecha** y la **hora** de la tabla
   (hora de España) → **Programar historia**.
   Si Business Suite te pide programarlas una a una, pon la de catalán a la hora de la tabla (09:00) y la de
   castellano un minuto después (09:01): así salen siempre en ese orden.
6. Domingos: repite con `…_3-ca.mp4` y `…_4-es.mp4` a las 12:00 y, antes de programar, añade el sticker de
   **Encuesta** (ver abajo).
7. Comprueba en **Planificador** que el día tiene sus historias a la hora buena.

## Días con sticker (domingos, 12:00)

En el vídeo hay un hueco libre en medio, entre la pregunta y el botón. Abre `…_3-ca-guia.png` (o `_4-es-guia.png`):
el recuadro de rayas marca dónde va. En Business Suite: **Stickers** → **Encuesta** → escribe las dos opciones →
arrástralo al hueco. Las opciones:

{turnos}

## Notas

- **18-nov (reto):** la story anuncia el reto de las 19:00 («3 accesos beta de 3 meses · comenta en el post»).
- **19 al 25-nov:** cuenta atrás encima de la story del día («Quedan 6 días» … «¡Último día!» el 25; cierra a las 23:59).
- **26-nov:** la story de las 09:00 es provisional («Hoy: la respuesta del reto y quién se lleva los accesos beta»).
  La de la respuesta y las personas ganadoras se hace ese mismo día, después del sorteo.
- **13 y 14-nov:** «Hoy reel», con la portada del reel de las 19:00.
{extras}- Música: bucle propio de afro house a 120 bpm hecho por código (`marketing/marca/musica/afro_house.py`), sin
  derechos de terceros, así que Business Suite no lo silencia.
- Los textos están en `marketing/instagram/stories-calendario.json`; para cambiar uno: edítalo y ejecuta
  `uv run --no-project --with playwright --with fonttools --with numpy python marketing/instagram/stories.py <fecha>`.

## Todos los días

| Día | Hora | Archivos (en este orden) | Texto (castellano) | Nota |
|---|---|---|---|---|
""" + "\n".join(rows) + "\n"


def with_extras(stories: list[dict]) -> list[dict]:
    """Añade las stories hechas aparte («extras» del JSON: sus vídeos ya están en la carpeta y aquí no se pintan) para
    la guía y las hojas de contacto; si no tienen póster, saca uno del vídeo (sin tocar el vídeo)."""
    out = list(stories)
    for e in json.loads(COPY.read_text()).get("extras", []):
        s = {**e, "kind": "extra"}
        mp4, png = OUT / f"{name(s)}.mp4", OUT / f"{name(s)}.png"
        if mp4.exists() and not png.exists():
            subprocess.run([ffmpeg_bin(), "-y", "-loglevel", "error", "-ss", "6", "-i", str(mp4), "-frames:v", "1",
                            str(png)], check=True)
        if png.exists():
            out.append(s)
    return sorted(out, key=lambda s: (s["date"], s["time"], s["n"]))


def duration(f: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(f)],
                       capture_output=True, text=True, check=True)
    return round(float(r.stdout.strip()), 2)


def remux_all(stories: list[dict]) -> None:
    """Cambia solo la música de todos los vídeos (los del calendario y los «extras») por el bucle afro house de su
    misma duración; la imagen se copia tal cual (-c:v copy)."""
    ff = ffmpeg_bin()
    for s in with_extras(stories):
        mp4 = OUT / f"{name(s)}.mp4"
        if not mp4.exists():
            continue
        dur = duration(mp4)
        tmp = mp4.with_suffix(".remux.mp4")
        subprocess.run([ff, "-y", "-loglevel", "error", "-i", str(mp4), "-i", str(music(dur)), "-map", "0:v:0",
                        "-map", "1:a:0", "-c", "copy", "-t", str(dur), "-movflags", "+faststart", str(tmp)], check=True)
        tmp.replace(mp4)
        print("música", mp4.name, f"{dur:g} s", f"{mp4.stat().st_size / 1e6:.2f} MB", flush=True)


def main() -> None:
    global SRC, OUT
    sub = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--out=")), "")
    if sub:   # los procesos hijos leen la raíz de la variable de entorno
        SRC = BASE / sub
        OUT = SRC / "stories" / "calendario"
        os.environ["RUNCH_STORIES_ROOT"] = str(SRC)
    video = "--sin-video" not in sys.argv
    jobs_n = next((int(a.split("=")[1]) for a in sys.argv if a.startswith("--jobs=")), 4)
    only = [a for a in sys.argv[1:] if not a.startswith("--")]
    OUT.mkdir(parents=True, exist_ok=True)
    stories = plan()
    if "--solo-musica" in sys.argv:
        remux_all(stories)
        return
    todo = [s for s in stories if not only or s["date"] in only or name(s) in only]
    m4a = music() if video else None
    jobs = [(s, video, m4a) for s in todo]
    if jobs_n > 1 and len(jobs) > 1:
        with ProcessPoolExecutor(jobs_n) as ex:
            for msg in ex.map(one, jobs):
                print(msg, flush=True)
    else:
        with Renderer() as r:
            for j in jobs:
                print(_one(r, j[0], video, m4a), flush=True)
    if "--frames" in sys.argv:
        rev = OUT / "revision"
        rev.mkdir(exist_ok=True)
        for s in todo:
            if (OUT / f"{name(s)}.mp4").exists():
                frames_sheet(OUT / f"{name(s)}.mp4", rev / f"{name(s)}-frames.png")
    if all((OUT / f"{name(s)}.png").exists() for s in stories):
        everything = with_extras(stories)
        with Renderer() as r:
            for p in contact_sheets(r, everything):
                print("hoja", p.name)
        (OUT / "GUIA.md").write_text(guide_md(everything))
        print("GUIA.md")


if __name__ == "__main__":
    main()
