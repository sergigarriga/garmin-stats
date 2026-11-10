"""Genera la capa ilustrada de Runch: logotipo, patrón, maquetas (mockups) y hoja de marca.

    uv run --no-project --with playwright --with fonttools --with pillow python marketing/marca/build.py            # todo
    uv run --no-project --with playwright --with fonttools --with pillow python marketing/marca/build.py logo hoja  # partes

Partes: ilustraciones (versiones en olivo), logo, patrones, mockups, hoja. Las plantillas de Instagram van aparte
(templates.py) y se generan antes que las maquetas, porque el móvil y la hoja de marca las muestran.
"""
from __future__ import annotations

import base64
import sys
from pathlib import Path

from kit import C, HERE, Renderer, lettering, wordmark, wordmark_svg

TAGLINES = {
    "run-and-brunch": "RUN & BRUNCH",
    "corre-recupera-repite": "CORRE · RECUPERA · REPITE",
    "club-de-running": "CLUB DE RUNNING",
}
# Combinaciones de tinta y fondo de la capa ilustrada (siempre una sola tinta).
# Los archivos runch-logo-terracota.* de logo/ son del color anterior: se quedan como legado, no se regeneran.
INKS = {
    "olivo": (C["brand"], C["cream"]),
    "crema": (C["cream"], C["brand"]),
    "espresso": (C["espresso"], C["cream"]),
}


def mix(a: str, b: str, t: float) -> str:
    """Mezcla dos colores hex (t=0 → a, t=1 → b)."""
    pa = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    pb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02X}" for x, y in zip(pa, pb))


def word_g(color: str, x: float, y: float, width: float, rot: float = 0) -> str:
    """Logotipo centrado en (x, y) con el ancho indicado, como grupo SVG."""
    g, (vx, vy, vw, vh) = wordmark()
    k = width / vw
    return (f'<g transform="translate({x} {y}) rotate({rot}) scale({k}) translate({-(vx + vw / 2)} {-(vy + vh / 2)})" '
            f'fill="{color}">{g}</g>')


def text_g(text: str, color: str, x: float, y: float, height: float, wght: int = 640, tracking: float = 260,
           anchor: str = "middle", rot: float = 0) -> str:
    """Texto en Gluten (trazados) con altura de mayúscula ≈ height, anclado en (x, y) = centro vertical."""
    g, (bx, by, bw, bh) = lettering(text, wght, tracking)
    k = height / 1170  # altura de mayúscula de Gluten
    ox = {"middle": bx + bw / 2, "start": bx, "end": bx + bw}[anchor]
    return (f'<g transform="translate({x} {y}) rotate({rot}) scale({k}) translate({-ox} {585})" fill="{color}">{g}</g>')


def text_w(text: str, height: float, wght: int = 640, tracking: float = 260) -> float:
    _, (_, _, bw, _) = lettering(text, wght, tracking)
    return bw * height / 1170


def fit(text: str, max_w: float, height: float, wght: int = 640, tracking: float = 260) -> float:
    """Altura de letra para que el texto no pase de max_w."""
    return min(height, height * max_w / text_w(text, height, wght, tracking))


def svg(w: float, h: float, body: str, bg: str | None = None) -> str:
    rect = f'<rect width="{w}" height="{h}" fill="{bg}"/>' if bg else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">'
            f'{rect}{body}</svg>')


# ============================================================================ logotipo
def lockup(tagline: str, color: str, bg: str | None = None) -> tuple[str, float, float]:
    """Logotipo + lema pequeño en mayúsculas debajo. Devuelve (svg, ancho, alto)."""
    W, ww = 1200, 1000
    _, (_, _, vw, vh) = wordmark()
    wh = ww * vh / vw
    th = 46
    tw = text_w(tagline, th)
    if tw > ww * 0.9:
        th = th * ww * 0.9 / tw
    H = wh + th + 120
    body = word_g(color, W / 2, 40 + wh / 2, ww) + text_g(tagline, color, W / 2, 40 + wh + th / 2 + 10, th)
    return svg(W, H, body, bg), W, H


def sello_inner(ink: str, bg: str, top: str = "RUN & BRUNCH", bottom: str = "CLUB DE RUNNING") -> str:
    """Sello redondo (pegatina, parche, avatar alternativo) en una caja de 1000 x 1000."""
    return (f'<circle cx="500" cy="500" r="490" fill="{bg}"/>'
            f'<circle cx="500" cy="500" r="440" fill="none" stroke="{ink}" stroke-width="10" stroke-dasharray="2 26" '
            f'stroke-linecap="round"/>'
            + text_g(top, ink, 500, 330, 40)
            + word_g(ink, 500, 500, 700, -4)
            + text_g(bottom, ink, 500, 676, 40))


def sello_svg(ink: str, bg: str) -> str:
    return svg(1000, 1000, sello_inner(ink, bg))


def build_logo(r: Renderer) -> None:
    out = HERE / "logo"
    for name, (ink, bg) in INKS.items():
        (out / f"runch-logo-{name}.svg").write_text(wordmark_svg(ink))
        r.png(f'<div style="display:grid;place-items:center;height:100%;background:{bg}">'
              f'{wordmark_svg(ink, height=330)}</div>', out / f"runch-logo-{name}.png", 1600, 800)
    for slug, tag in TAGLINES.items():
        s, _, _ = lockup(tag, C["brand"])
        (out / f"runch-lema-{slug}.svg").write_text(s)
        r.png(f'<div style="display:grid;place-items:center;height:100%;background:{C["cream"]}">'
              f'<div style="width:1100px">{s}</div></div>', out / f"runch-lema-{slug}.png", 1600, 900)
    sello = sello_svg(C["cream"], C["brand"])
    (out / "runch-sello.svg").write_text(sello)
    r.png(f'<div style="width:1000px;height:1000px">{sello}</div>', out / "runch-sello.png", 1000, 1000, transparent=True)


# ============================================================================ patrón
def pattern_logo_tile(ink: str) -> tuple[str, float, float]:
    """Baldosa repetible: filas del logotipo en ladrillo (la segunda fila desplazada media pieza)."""
    _, (_, _, vw, vh) = wordmark()
    ww = 300
    wh = ww * vh / vw
    cw, rh = ww * 1.22, wh * 0.86
    body = word_g(ink, cw / 2, rh / 2, ww) + word_g(ink, 0, rh * 1.5, ww) + word_g(ink, cw, rh * 1.5, ww)
    return body, cw, rh * 2


def pattern_fill(w: float, h: float, ink: str, bg: str, rot: float = -8, scale: float = 1, pid: str = "p") -> str:
    tile, tw, th = pattern_logo_tile(ink)
    return (f'<defs><pattern id="{pid}" width="{tw:.2f}" height="{th:.2f}" patternUnits="userSpaceOnUse" '
            f'patternTransform="rotate({rot}) scale({scale})">{tile}</pattern></defs>'
            f'<rect width="{w}" height="{h}" fill="{bg}"/><rect width="{w}" height="{h}" fill="url(#{pid})"/>')


# Olivo con crema son los principales; los acentos de la app (pistacho, lavanda, mar) dan juego en merchandising.
# Los patron-logo-*-terracota*.png que quedan en patrones/ son del color anterior (legado).
PATTERNS = [("crema-sobre-olivo", C["cream"], C["brand"]), ("olivo-sobre-crema", C["brand"], C["cream"]),
            ("espresso-sobre-pistacho", C["espresso"], C["pistachio"]), ("crema-sobre-lavanda", C["cream"], C["lavender"]),
            ("mantequilla-sobre-mar", C["butter"], C["sea"]), ("crema-sobre-espresso", C["cream"], C["espresso"])]


def build_patrones(r: Renderer) -> None:
    out = HERE / "patrones"
    t, tw, th = pattern_logo_tile(C["brand"])
    (out / "patron-logo-baldosa.svg").write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {tw:.1f} {th:.1f}" width="{tw:.1f}" height="{th:.1f}">'
        f'<rect width="100%" height="100%" fill="{C["cream"]}"/>{t}</svg>')
    for slug, ink, bg in PATTERNS:
        r.png(svg(1080, 1350, pattern_fill(1080, 1350, ink, bg)), out / f"patron-logo-{slug}.png", 1080, 1350)


# ============================================================================ ilustraciones
def build_ilustraciones(r: Renderer | None = None) -> None:
    """Versión en olivo (`-olivo.png`) de cada ilustración e icono: misma transparencia que `-terracota.png`, solo
    cambia la tinta. Los originales y las versiones crema, espresso y terracota se quedan como están."""
    from PIL import Image

    ink = tuple(int(C["brand"][i:i + 2], 16) for i in (1, 3, 5))
    d = HERE / "ilustraciones" / "gemini"
    for src in [*d.glob("*-terracota.png"), *(d / "iconos").glob("*-terracota.png")]:
        im = Image.open(src).convert("RGBA")
        out = Image.new("RGBA", im.size, ink + (0,))
        out.putalpha(im.getchannel("A"))
        out.save(src.with_name(src.name.replace("-terracota.png", "-olivo.png")), optimize=True)


# ============================================================================ maquetas
def shadow(cx: float, cy: float, rx: float, ry: float, color: str = "#000", op: float = .12) -> str:
    return f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" fill="{color}" opacity="{op}"/>'


def box(x: float, y: float, w: float, h: float, d: float, color: str, front: str, rot: float = 0) -> str:
    """Caja de cartón en perspectiva caballera: cara frontal con diseño, tapa clara y lateral oscuro."""
    dx, dy = d * .55, -d * .42
    top = mix(color, "#FFFFFF", .2)
    side = mix(color, "#000000", .16)
    cx, cy = x + w / 2, y + h / 2
    return (f'<g transform="rotate({rot} {cx} {cy})">'
            f'<polygon points="{x},{y} {x + w},{y} {x + w + dx},{y + dy} {x + dx},{y + dy}" fill="{top}"/>'
            f'<polygon points="{x + w},{y} {x + w + dx},{y + dy} {x + w + dx},{y + h + dy} {x + w},{y + h}" fill="{side}"/>'
            f'<line x1="{x + w * .15 + dx * .5}" y1="{y + dy * .5}" x2="{x + w * .85 + dx * .5}" y2="{y + dy * .5}" '
            f'stroke="{mix(top, "#000000", .1)}" stroke-width="3"/>'
            f'<svg x="{x}" y="{y}" width="{w}" height="{h}" viewBox="0 0 {w} {h}" overflow="hidden">'
            f'<rect width="{w}" height="{h}" fill="{color}"/>{front}</svg></g>')


def mock_cajas() -> str:
    """Tres cajas apiladas: logotipo + lema, patrón y lema grande."""
    W, H = 1080, 1350
    bw, bh = 600, 400
    hh = fit("nadie se queda", bw * .78, 62, 820, 0)
    f3 = (text_g("nadie se queda", C["brand"], bw / 2, 140, hh, wght=820, tracking=0)
          + text_g("atrás", C["brand"], bw / 2, 140 + hh * 1.45, hh, wght=820, tracking=0)
          + word_g(C["brand"], bw / 2, 320, 150, -3))
    b3 = box(220, 820, bw, bh, 170, C["cream"], f3, 1.5)
    b2 = box(250, 530, 540, 310, 150, C["brand"], pattern_fill(540, 310, C["cream"], C["brand"], scale=.5, pid="pb"), -2.5)
    f1 = word_g(C["brand"], 230, 128, 320, -3) + text_g("RUN & BRUNCH", C["brand"], 230, 224, 20, tracking=320)
    b1 = box(300, 300, 460, 270, 130, C["cream"], f1, 2)
    return svg(W, H, shadow(560, 1236, 360, 30, C["espresso"], .16) + b3 + b2 + b1, C["lavender_light"])


def tote(cx: float, cy: float, canvas: str, print_: str) -> str:
    strap = mix(canvas, "#000000", .12)
    return (f'<g transform="translate({cx} {cy})">'
            + shadow(0, 420, 300, 26, "#000", .16)
            + f'<path d="M-160 -330 C-160 -560 160 -560 160 -330" fill="none" stroke="{strap}" stroke-width="30" stroke-linecap="round"/>'
            + f'<path d="M-270 -360 L270 -360 L296 400 L-296 400 Z" fill="{canvas}"/>'
            + f'<path d="M-270 -360 L270 -360 L271 -326 L-271 -326 Z" fill="{strap}" opacity=".5"/>'
            + f'<path d="M-160 -340 L-160 -250 M160 -340 L160 -250" stroke="{strap}" stroke-width="30" stroke-linecap="round"/>'
            + print_ + "</g>")


def mock_bolsas() -> str:
    W, H = 1600, 1200
    canvas = "#EFE4D0"
    p1 = (word_g(C["brand"], 0, 10, 400, -3)
          + text_g("CORRE · RECUPERA · REPITE", C["brand"], 0, 130, 21, tracking=300))
    clip = '<clipPath id="tc"><path d="M-226 -230 L226 -230 L246 340 L-246 340 Z"/></clipPath>'
    p2 = (f'{clip}<g clip-path="url(#tc)"><g transform="translate(-300 -260)">'
          f'{pattern_fill(600, 640, C["cream"], C["lavender"], scale=.62, pid="tp")}</g></g>')
    body = tote(440, 620, canvas, p1) + tote(1160, 620, C["lavender"], p2)
    return svg(W, H, body, C["butter"])


TEE = ("M-150 -250 C-110 -232 -60 -224 0 -224 C60 -224 110 -232 150 -250 L290 -186 L360 -40 L250 0 L206 -80 "
       "L206 300 C150 312 -150 312 -206 300 L-206 -80 L-250 0 L-360 -40 L-290 -186 Z")


def tee(cx: float, cy: float, color: str, print_: str) -> str:
    collar = mix(color, "#000000", .14)
    return (f'<g transform="translate({cx} {cy})">'
            + shadow(0, 330, 250, 22, "#000", .1)
            + f'<path d="{TEE}" fill="{color}"/>'
            + f'<path d="M-150 -250 C-110 -232 -60 -224 0 -224 C60 -224 110 -232 150 -250 C110 -196 60 -184 0 -184 '
              f'C-60 -184 -110 -196 -150 -250 Z" fill="{collar}"/>'
            + f'<path d="M-206 -80 L-214 -168 M206 -80 L214 -168" stroke="{collar}" stroke-width="5" opacity=".7"/>'
            + print_ + "</g>")


def mock_camisetas() -> str:
    W, H = 1600, 1000
    p1 = word_g(C["cream"], 0, -70, 270, -3) + text_g("CLUB DE RUNNING", C["cream"], 0, 4, 18, tracking=360)
    p2 = (text_g("nadie se", C["brand"], 0, -66, 50, wght=820, tracking=0)
          + text_g("queda atrás", C["brand"], 0, 4, 50, wght=820, tracking=0)
          + text_g("RITMO Z2 · DOMINGOS", C["brand"], 0, 76, 16, tracking=360)
          + word_g(C["brand"], 0, 190, 120, -3))
    return svg(W, H, tee(430, 470, C["brand"], p1) + tee(1170, 470, C["cream"], p2), C["sea_light"])


def mock_gorra() -> str:
    W, H = 1080, 1080
    cap = C["brand"]
    seam = mix(cap, "#FFFFFF", .12)
    body = (shadow(540, 850, 300, 30, "#000", .16)
            + f'<path d="M260 640 C250 420 380 300 540 300 C700 300 830 420 820 640 Z" fill="{cap}"/>'
            + f'<path d="M540 300 C500 400 492 520 500 640 M540 300 C580 400 588 520 580 640" fill="none" stroke="{seam}" stroke-width="5"/>'
            + f'<circle cx="540" cy="304" r="16" fill="{seam}"/>'
            + f'<path d="M290 628 C400 596 680 596 790 628 C812 700 708 772 540 776 C372 772 268 700 290 628 Z" '
              f'fill="{mix(cap, "#FFFFFF", .1)}"/>'
            + f'<path d="M318 650 C420 624 660 624 762 650" fill="none" stroke="{mix(cap, "#FFFFFF", .22)}" stroke-width="4" stroke-dasharray="12 10"/>'
            + word_g(C["cream"], 540, 470, 240, -3))
    return svg(W, H, body, C["pistachio_light"])


def mock_botella() -> str:
    W, H = 1080, 1350
    btl = C["lavender"]
    body = (shadow(540, 1236, 200, 26, "#000", .12)
            + f'<rect x="470" y="150" width="140" height="120" rx="30" fill="{C["espresso"]}"/>'
            + f'<rect x="450" y="250" width="180" height="40" rx="16" fill="{mix(C["espresso"], "#FFFFFF", .15)}"/>'
            + f'<path d="M450 290 C450 330 380 350 380 420 L380 1170 C380 1206 410 1230 446 1230 L634 1230 C670 1230 700 1206 700 1170 '
              f'L700 420 C700 350 630 330 630 290 Z" fill="{btl}"/>'
            + f'<rect x="402" y="420" width="18" height="760" rx="9" fill="#FFFFFF" opacity=".25"/>'
            + word_g(C["cream"], 548, 800, 560, -90)
            + text_g("RUN & BRUNCH", C["cream"], 640, 800, 20, tracking=320, rot=-90))
    return svg(W, H, body, C["cream"])


def mock_pegatinas() -> str:
    W, H = 1350, 1350
    wht = "#FFFFFF"
    sh = 'filter="url(#ds)"'
    defs = ('<defs><filter id="ds" x="-20%" y="-20%" width="140%" height="140%">'
            '<feDropShadow dx="0" dy="6" stdDeviation="8" flood-color="#221A15" flood-opacity=".18"/></filter>'
            '<clipPath id="pc"><circle cx="760" cy="1060" r="150"/></clipPath></defs>')
    def t(txt, x, y, h, maxw, color, wght=820, tr=10):
        return text_g(txt, color, x, y, fit(txt, maxw, h, wght, tr), wght=wght, tracking=tr)

    z2x = 340 - (text_w("Z2", 70, 840, 40) + 26 + text_w("CLUB", 30, 640, 120)) / 2
    s = [
        # logotipo en óvalo
        f'<g transform="rotate(-6 380 300)" {sh}><ellipse cx="380" cy="300" rx="250" ry="150" fill="{C["cream"]}" stroke="{wht}" stroke-width="22"/>'
        + word_g(C["brand"], 380, 300, 340) + "</g>",
        # sello
        f'<g transform="translate(1000 330) scale(.36) translate(-500 -500)" {sh}><circle cx="500" cy="500" r="525" fill="{wht}"/>'
        + sello_inner(C["cream"], C["brand"]) + "</g>",
        # Z2 club
        f'<g transform="rotate(5 340 660)" {sh}><rect x="150" y="560" width="380" height="200" rx="56" fill="{C["espresso"]}" stroke="{wht}" stroke-width="22"/>'
        + text_g("Z2", C["cream"], z2x, 660, 70, wght=840, tracking=40, anchor="start")
        + text_g("CLUB", C["cream"], z2x + text_w("Z2", 70, 840, 40) + 26, 660, 30, tracking=120, anchor="start") + "</g>",
        # nadie se queda atrás
        f'<g transform="rotate(-4 930 700)" {sh}><rect x="660" y="610" width="540" height="180" rx="90" fill="{C["pistachio"]}" stroke="{wht}" stroke-width="22"/>'
        + t("nadie se queda", 930, 670, 42, 440, C["espresso"], 780) + t("atrás", 930, 732, fit("nadie se queda", 440, 42, 780, 10), 999, C["espresso"], 780) + "</g>",
        # corre despacio
        f'<g transform="rotate(-8 330 1050)" {sh}><circle cx="330" cy="1050" r="160" fill="{C["butter"]}" stroke="{wht}" stroke-width="22"/>'
        + t("corre", 330, 1010, fit("despacio", 260, 60, 820, 10), 999, C["brand"]) + t("despacio", 330, 1080, 60, 260, C["brand"]) + "</g>",
        # patrón redondo
        f'<g {sh}><circle cx="760" cy="1060" r="161" fill="{wht}"/><g clip-path="url(#pc)"><g transform="translate(600 900)">'
        + pattern_fill(320, 320, C["cream"], C["brand"], scale=.5, pid="pp") + "</g></g></g>",
        # run & brunch
        f'<g transform="rotate(6 1090 1060)" {sh}><rect x="960" y="900" width="260" height="320" rx="40" fill="{C["lavender"]}" stroke="{wht}" stroke-width="22"/>'
        + t("RUN", 1090, 980, fit("BRUNCH", 210, 60, 760, 40), 999, C["cream"], 760, 40)
        + t("&", 1090, 1060, fit("BRUNCH", 210, 60, 760, 40), 999, C["cream"], 760, 0)
        + t("BRUNCH", 1090, 1140, 60, 210, C["cream"], 760, 40) + "</g>",
    ]
    sheet = f'<rect x="60" y="60" width="{W - 120}" height="{H - 120}" rx="36" fill="{C["paper"]}"/>'
    return svg(W, H, defs + sheet + "".join(s), C["sea"])


def mock_movil(story_png: Path, post_png: Path) -> str:
    """Móvil con una historia de Instagram y, al lado, el post en el feed."""
    W, H = 1600, 1200

    def img(p: Path, x, y, w, h, rx, cid):
        if not p.exists():
            return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{C["cream"]}"/>'
        b64 = base64.b64encode(p.read_bytes()).decode()
        return (f'<clipPath id="{cid}"><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}"/></clipPath>'
                f'<image href="data:image/png;base64,{b64}" x="{x}" y="{y}" width="{w}" height="{h}" '
                f'preserveAspectRatio="xMidYMid slice" clip-path="url(#{cid})"/>')

    def phone(x, y, w, h, inner):
        return (shadow(x + w / 2, y + h + 30, w * .42, 18, "#000", .14)
                + f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="64" fill="{C["espresso"]}"/>' + inner
                + f'<rect x="{x + w / 2 - 60}" y="{y + 26}" width="120" height="30" rx="15" fill="{C["espresso"]}"/>')

    pw, ph = 470, 960
    ph1 = round((pw - 32) * 16 / 9) + 32  # pantalla 9:16, para que la historia se vea entera
    x1, y1 = 330, 110 + (ph - ph1) // 2
    s1 = phone(x1, y1, pw, ph1, img(story_png, x1 + 16, y1 + 16, pw - 32, ph1 - 32, 50, "c1"))
    s1 += "".join(f'<rect x="{x1 + 40 + i * 132}" y="{y1 + 76}" width="122" height="6" rx="3" fill="#FFFFFF" '
                  f'opacity="{.95 if i == 0 else .5}"/>' for i in range(3))
    x2, y2 = 870, 160
    iw = pw - 32
    yb = y2 + 160 + iw * 1.25
    feed = (f'<rect x="{x2 + 16}" y="{y2 + 16}" width="{iw}" height="{ph - 32}" rx="50" fill="#FFFFFF"/>'
            + f'<circle cx="{x2 + 70}" cy="{y2 + 120}" r="26" fill="{C["brand"]}"/>'
            + f'<text x="{x2 + 70}" y="{y2 + 131}" text-anchor="middle" font-family="FR" font-style="italic" font-size="32" fill="{C["cream"]}">r</text>'
            + f'<text x="{x2 + 110}" y="{y2 + 128}" font-family="GSF" font-weight="600" font-size="22" fill="{C["espresso"]}">runch.run</text>'
            + img(post_png, x2 + 16, y2 + 160, iw, iw * 1350 / 1080, 0, "c2")
            + f'<path transform="translate({x2 + 44} {yb + 26}) scale(.36)" d="M50 82 C30 68 14 54 14 38 C14 26 24 18 34 18 '
              f'C42 18 48 24 50 30 C52 24 58 18 66 18 C76 18 86 26 86 38 C86 54 70 68 50 82 Z" fill="none" '
              f'stroke="{C["espresso"]}" stroke-width="8" stroke-linejoin="round"/>'
            + f'<rect x="{x2 + 44}" y="{yb + 80}" width="300" height="14" rx="7" fill="{C["espresso"]}" opacity=".7"/>'
            + f'<rect x="{x2 + 44}" y="{yb + 110}" width="220" height="14" rx="7" fill="{C["espresso"]}" opacity=".35"/>')
    return svg(W, H, s1 + phone(x2, y2, pw, ph, feed), C["sage"])


def build_mockups(r: Renderer) -> None:
    out = HERE / "mockups"
    tpl = HERE / "plantillas"
    items = {
        "cajas": (mock_cajas(), 1080, 1350),
        "bolsas": (mock_bolsas(), 1600, 1200),
        "camisetas": (mock_camisetas(), 1600, 1000),
        "gorra": (mock_gorra(), 1080, 1080),
        "botella": (mock_botella(), 1080, 1350),
        "pegatinas": (mock_pegatinas(), 1350, 1350),
        "movil": (mock_movil(tpl / "story-quedada-1-ca.png", tpl / "post-reto-2-es.png"), 1600, 1200),
    }
    for name, (s, w, h) in items.items():
        r.png(s, out / f"{name}.png", w, h)


# ============================================================================ hoja de marca
def build_hoja(r: Renderer) -> None:
    def png(p: Path) -> str:
        return "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode()

    m = HERE / "mockups"
    sw = [("Olivo", "olive", "marca", C["cream"]), ("Lavanda", "lavender", "Salud", C["cream"]),
          ("Pistacho", "pistachio", "Entreno", C["espresso"]), ("Mar", "sea", "Análisis", C["cream"]),
          ("Crema", "cream", "fondo", C["espresso"]), ("Papel", "paper", "fondo", C["espresso"]),
          ("Espresso", "espresso", "texto", C["cream"]), ("Mantequilla", "butter", "cálido", C["espresso"]),
          ("Salvia", "sage", "suave", C["espresso"])]
    swatches = "".join(f'<div class="sw" style="background:{C[k]};color:{fg}"><b>{n}</b><span>{C[k]} · {u}</span></div>'
                       for n, k, u, fg in sw)
    tints = "".join(f'<div class="tn" style="background:{C[k]};color:{fg}">{n}<span>{C[k]}</span></div>' for n, k, fg in
                    [("Olivo oscuro", "olive_dark", C["cream"]), ("Olivo claro", "olive_light", C["espresso"]),
                     ("Lavanda tinta", "lavender_ink", C["cream"]), ("Lavanda clara", "lavender_light", C["espresso"]),
                     ("Pistacho tinta", "pistachio_ink", C["cream"]), ("Pistacho claro", "pistachio_light", C["espresso"]),
                     ("Mar claro", "sea_light", C["espresso"])])
    logos = "".join(f'<div class="lg" style="background:{bg}">{wordmark_svg(ink, height=120)}</div>'
                    for ink, bg in INKS.values())
    lemas = "".join(f'<div class="lema">{lockup(t, C["brand"])[0]}</div>' for t in TAGLINES.values())
    pats = "".join(f'<img src="{png(HERE / "patrones" / f"patron-logo-{slug}.png")}">' for slug, _, _ in PATTERNS)
    mocks = "".join(f'<img class="mk" src="{png(m / f)}">' for f in ["cajas.png", "botella.png", "pegatinas.png"])
    mocks_wide = "".join(f'<img class="mkw" src="{png(m / f)}">' for f in ["bolsas.png", "camisetas.png", "movil.png", "gorra.png"])
    tpls = "".join(f'<img class="tp" src="{png(HERE / "plantillas" / f)}">' for f in
                   ["post-quedada-1-ca.png", "post-reto-2-es.png", "post-tu-turno-1-ca.png", "post-cita-2-es.png"])
    ils = "".join(f'<img src="{png(HERE / "ilustraciones" / "gemini" / f"corredor-{i}-olivo.png")}">' for i in (1, 2))

    g, (vx, vy, vw, vh) = wordmark()

    def wm(style: str = "", fill: str = C["brand"], extra: str = "") -> str:
        return f'<svg viewBox="{vx} {vy} {vw} {vh}" style="width:76%;{style}"><g fill="{fill}" {extra}>{g}</g></svg>'

    def dd(ok: bool, bg: str, inner: str, txt: str) -> str:
        mark, col = ("Sí", C["brand"]) if ok else ("No", C["lavender_ink"])
        return (f'<div class="dd"><div class="ddbox" style="background:{bg}">{inner}</div>'
                f'<p><b style="color:{col}">{mark}.</b> {txt}</p></div>')

    grad = (f'<svg viewBox="{vx} {vy} {vw} {vh}" style="width:76%"><defs><linearGradient id="gr">'
            f'<stop offset="0" stop-color="{C["brand"]}"/><stop offset=".5" stop-color="{C["lavender"]}"/>'
            f'<stop offset="1" stop-color="{C["pistachio"]}"/></linearGradient></defs><g fill="url(#gr)">{g}</g></svg>')
    dos = (dd(True, C["cream"], wm(), "Una sola tinta sobre fondo liso.")
           + dd(True, C["brand"], wm(fill=C["cream"]), "Crema sobre olivo.")
           + dd(False, C["cream"], wm("transform:scaleX(1.5)"), "Estirarlo o deformarlo.")
           + dd(False, C["cream"], grad, "Degradados o varias tintas.")
           + dd(False, C["cream"], wm(fill="none", extra=f'stroke="{C["brand"]}" stroke-width="30"'), "Solo el contorno.")
           + dd(False, C["pistachio"], wm(), "Olivo sobre pistacho: poco contraste."))

    css = f"""
body {{ background:{C["cream"]}; color:{C["espresso"]}; font-family:GSF, sans-serif; }}
.page {{ padding:110px 120px 130px; display:grid; gap:80px; }}
h2 {{ font: 700 40px Gluten; color:{C["brand"]}; margin:0 0 26px; }}
.hero {{ display:grid; grid-template-columns: 1.25fr 1fr; gap:80px; align-items:center; }}
.hero h1 {{ font: 400 66px/1.06 FR; margin:36px 0 22px; }}
.hero p {{ font-size:29px; line-height:1.5; max-width:30em; margin:0; color:#5b4f46; }}
.row {{ display:grid; gap:24px; }}
.lg {{ height:220px; display:grid; place-items:center; border-radius:28px; box-shadow: inset 0 0 0 2px rgba(34,26,21,.08); }}
.lema {{ background:{C["paper"]}; border-radius:28px; padding:30px 40px; }}
.lema svg {{ width:100%; height:auto; display:block; }}
.sws {{ display:grid; grid-template-columns: repeat(9, 1fr); gap:16px; }}
.tns {{ display:grid; grid-template-columns: repeat(7, 1fr); gap:16px; margin-top:16px; }}
.tn {{ height:96px; border-radius:20px; padding:14px 18px; font-size:21px; display:flex; flex-direction:column;
       justify-content:flex-end; box-shadow: inset 0 0 0 2px rgba(34,26,21,.08); }}
.tn span {{ opacity:.75; font-size:18px; }}
.sw {{ height:230px; border-radius:24px; padding:22px; display:flex; flex-direction:column; justify-content:flex-end;
       font-size:25px; box-shadow: inset 0 0 0 2px rgba(34,26,21,.08); }}
.sw span {{ opacity:.8; font-size:19px; margin-top:4px; }}
.type {{ display:grid; grid-template-columns: 1fr 1fr 1fr; gap:24px; }}
.type > div {{ background:{C["paper"]}; border-radius:28px; padding:34px 38px; }}
.type .s {{ font-size:23px; color:#76695F; margin-top:14px; line-height:1.45; }}
.pats {{ display:grid; grid-template-columns: repeat(6, 1fr); gap:20px; }}
.pats img {{ width:100%; height:440px; object-fit:cover; border-radius:28px; display:block; }}
.mks {{ display:grid; grid-template-columns: repeat(3, 1fr); gap:24px; }}
.mk {{ width:100%; height:760px; object-fit:cover; border-radius:28px; display:block; }}
.mkws {{ display:grid; grid-template-columns: 1fr 1fr; gap:24px; margin-top:24px; }}
.mkw {{ width:100%; height:700px; object-fit:cover; border-radius:28px; display:block; }}
.tps {{ display:grid; grid-template-columns: repeat(4, 1fr); gap:24px; }}
.tp {{ width:100%; border-radius:20px; display:block; box-shadow: 0 0 0 2px rgba(34,26,21,.08); }}
.dds {{ display:grid; grid-template-columns: repeat(6, 1fr); gap:20px; }}
.ddbox {{ height:180px; border-radius:22px; display:grid; place-items:center; overflow:hidden; box-shadow: inset 0 0 0 2px rgba(34,26,21,.08); }}
.dd p {{ font-size:22px; margin:14px 4px 0; line-height:1.35; }}
.two {{ display:grid; grid-template-columns: 1fr 1fr 1fr; gap:24px; }}
.use {{ background:{C["paper"]}; border-radius:28px; padding:36px 40px; font-size:25px; line-height:1.5; }}
.use b {{ display:block; font: 400 40px FR; margin-bottom:12px; }}
.use.il b {{ font: 800 42px Gluten; color:{C["brand"]}; }}
.use.ph {{ background:none; border: 4px solid rgba(90,107,50,.35); }}
.ils {{ display:flex; gap:28px; align-items:flex-end; margin:6px 0 18px; }}
.ils img {{ height:230px; width:auto; display:block; }}
.use.ph b {{ font: 800 42px Gluten; color:{C["brand"]}; }}
"""
    body = f"""<div class="page">
  <div class="hero">
    <div>{wordmark_svg(C["brand"], height=250)}
      <h1>Correr juntos y desayunar después.</h1>
      <p>La capa ilustrada de la marca, para quedadas, comunidad, merchandising y anuncios: una sola tinta, letras
      gordas y redondas, buen rollo. Los carruseles de datos siguen con el sistema editorial.</p></div>
    <div>{sello_svg(C["cream"], C["brand"])}</div>
  </div>
  <section><h2>Logotipo</h2><div class="row" style="grid-template-columns:repeat(3,1fr)">{logos}</div></section>
  <section><h2>Lemas</h2><div class="row" style="grid-template-columns:repeat(3,1fr)">{lemas}</div></section>
  <section><h2>Color</h2><div class="sws">{swatches}</div><div class="tns">{tints}</div></section>
  <section><h2>Tipografía</h2><div class="type">
    <div><div style="font:820 66px Gluten;color:{C["brand"]}">Gluten</div><div class="s">Logotipo, titulares y lemas de la capa ilustrada. Licencia OFL, incluida en fonts/.</div></div>
    <div><div style="font:400 66px FR">Fraunces <i style="color:{C["brand"]}">cursiva</i></div><div class="s">Titulares del sistema editorial: datos y carruseles.</div></div>
    <div><div style="font:600 58px GSF">Google Sans Flex</div><div class="s">Textos y detalles en los dos sistemas.</div></div>
  </div></section>
  <section><h2>Patrón</h2><div class="pats">{pats}</div></section>
  <section><h2>Instagram</h2><div class="tps">{tpls}</div></section>
  <section><h2>Aplicaciones</h2><div class="mks">{mocks}</div><div class="mkws">{mocks_wide}</div></section>
  <section><h2>Sí y no</h2><div class="dds">{dos}</div></section>
  <section><h2>Cuándo usar cada sistema</h2><div class="two">
    <div class="use"><b>Editorial</b>Datos, explicaciones y carruseles de la app: Fraunces, gráficos de línea fina y la maqueta fija con «Nº 01 · TEMA».</div>
    <div class="use il"><b>Ilustrado</b>Quedadas, retos, merchandising, avisos y momentos de comunidad: logotipo, Gluten, patrón y una sola tinta.</div>
    <div class="use ph"><b>Ilustración</b><div class="ils">{ils}</div>Línea gruesa, una tinta, ojos cerrados; la piel deja ver el fondo. Grandes y sueltas, sin caja.</div>
  </div></section>
</div>"""
    r.png(body, HERE / "runch-brand-sheet.png", 2400, 6000, css=css, full=True)


def main(parts: list[str]) -> None:
    parts = parts or ["ilustraciones", "logo", "patrones", "mockups", "hoja"]
    steps = {"ilustraciones": build_ilustraciones, "logo": build_logo, "patrones": build_patrones,
             "mockups": build_mockups, "hoja": build_hoja}
    with Renderer() as r:
        for p in parts:
            steps[p](r)
            print("ok", p)


if __name__ == "__main__":
    main(sys.argv[1:])
