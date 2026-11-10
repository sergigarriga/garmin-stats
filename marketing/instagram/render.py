"""Posts de Instagram de Runch (1080 x 1350, 4:5) con el sistema editorial: crema, espresso y olivo, titulares en
serif (Fraunces) con la palabra clave en cursiva, textos en Google Sans Flex y gráficos de línea fina.

Uso:
  uv run --no-project --with playwright python marketing/instagram/render.py marketing/instagram/lote-01.json

Con `--out carpeta` (relativa a out/) sale en out/<carpeta>/lote-NN/ en lugar de out/lote-NN/ (p. ej. `--out olivo`).

Salida en marketing/instagram/out/lote-NN/: un PNG por diapositiva, captions.md, grid.png (cuadrícula del perfil) y
todos.html (todo el lote para revisar). Formato del lote y sistema visual: README.md de esta carpeta.
"""

from __future__ import annotations

import glob
import html
import json
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ICONS = json.loads((HERE / "icons.json").read_text())
W, H = 1080, 1350

# ---------------------------------------------------------------- sistema visual
# Fondos (uno por diapositiva): tinta, tinta secundaria, acento, línea fina.
THEMES = {
    "cream":      {"bg": "#F7F3EC", "ink": "#221A15", "ink2": "#76695F", "accent": "#5A6B32", "line": "rgba(34,26,21,.16)", "soft": "#EEE7DB", "logo": "olivo"},
    "paper":      {"bg": "#FCFAF6", "ink": "#221A15", "ink2": "#76695F", "accent": "#5A6B32", "line": "rgba(34,26,21,.14)", "soft": "#F3EEE6", "logo": "olivo"},
    "olive":      {"bg": "#5A6B32", "ink": "#F7F3EC", "ink2": "rgba(247,243,236,.8)", "accent": "#F1DEA6", "line": "rgba(247,243,236,.3)", "soft": "#52622D", "logo": "crema"},
    "lavender":   {"bg": "#8B6FD6", "ink": "#FCFAF6", "ink2": "rgba(252,250,246,.86)", "accent": "#F1DEA6", "line": "rgba(252,250,246,.34)", "soft": "#8266CC", "logo": "crema"},
    "espresso":   {"bg": "#221A15", "ink": "#F3ECE2", "ink2": "#B4A79A", "accent": "#B4C784", "line": "rgba(243,236,226,.18)", "soft": "#2E241E", "logo": "crema"},
    "sage":       {"bg": "#CBD3B8", "ink": "#221A15", "ink2": "#53584A", "accent": "#6B4FC0", "line": "rgba(34,26,21,.16)", "soft": "#BFC8AA", "logo": "espresso"},
    "sea":        {"bg": "#24496D", "ink": "#F3ECE2", "ink2": "#BCCADA", "accent": "#F4C56E", "line": "rgba(243,236,226,.2)", "soft": "#2B5379", "logo": "crema"},
    "butter":     {"bg": "#F1DEA6", "ink": "#221A15", "ink2": "#6D5F43", "accent": "#5A6B32", "line": "rgba(34,26,21,.16)", "soft": "#E8D294", "logo": "espresso"},
    # Legado (marca anterior, terracota): solo para volver a pintar piezas antiguas tal cual.
    "terracotta": {"bg": "#D4542F", "ink": "#FBF3E8", "ink2": "rgba(251,243,232,.78)", "accent": "#FFE1A3", "line": "rgba(251,243,232,.3)", "soft": "#C64A27", "logo": "crema"},
}
ZONE_ALPHA = [0.35, 1.0, 0.5, 0.65, 0.8]  # opacidad de cada zona (la destacada usa el acento)
T: dict = {}
STYLE: dict = {"handle": None}


def esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


def rich(s) -> str:
    """**palabra** → cursiva en el color de acento (la firma del sistema)."""
    parts = esc(s).split("**")
    return "".join(f"<em>{p}</em>" if i % 2 else p for i, p in enumerate(parts))


def icon(name: str, color: str, size: int = 36) -> str:
    paths = "".join(f'<path d="{d}"/>' for d in ICONS.get(name, ICONS["AutoAwesome"]))
    return f'<svg viewBox="0 0 24 24" width="{size}" height="{size}" fill="{color}">{paths}</svg>'


def A(kind: str, d: float = 0, t: float = .7, **kw) -> str:
    """Marca un elemento del gráfico para el vídeo (`animate`): tipo de animación, inicio y duración en segundos.
    Los atributos data-* no cambian nada en el PNG; solo los lee ANIM_JS al grabar el vídeo."""
    extra = "".join(f' data-{k}="{v}"' for k, v in kw.items())
    return f' data-a="{kind}" data-d="{d:g}" data-t="{t:g}"{extra}'


def label(text: str, color: str | None = None, size: int = 21) -> str:
    return f'<div class="lab" style="font-size:{size}px;color:{color or T["ink2"]}">{esc(text)}</div>'


# ---------------------------------------------------------------- gráficos de línea fina
def v_zones(v: dict) -> str:
    hi = v.get("highlight", 2)
    rows, dim = [], (len(v["rows"]) - 1) * .2 + 1.0
    for j, z in enumerate(v["rows"]):
        on = z["zone"] == hi
        col = T["accent"] if on else T["ink"]
        rows.append(f'''<div class="row" style="align-items:center;gap:26px;padding:20px 0;border-top:1.5px solid {T["line"]};opacity:{1 if on else .55}"{A("zone", j * .2, .8, d2=f"{dim:g}")}>
          <div class="serif" style="width:84px;font-size:44px;color:{col}">Z{z["zone"]}</div>
          <div style="flex:1;font-size:32px;font-weight:{650 if on else 450}">{esc(z["name"])}</div>
          <div class="serif" style="font-size:40px;color:{col}"{A("count", j * .2 + .1, 1.6, al="right", **{"in": 0})}>{esc(z["range"])}</div>
          <div style="width:30px;font-size:20px;color:{T["ink2"]}">{esc(v.get("unit", ""))}</div></div>''')
    return f'<div class="col">{"".join(rows)}<div style="border-top:1.5px solid {T["line"]}"></div></div>'


def v_readiness(v: dict) -> str:
    parts = "".join(f'''<div class="row" style="align-items:center;gap:22px;padding:14px 0;border-top:1.5px solid {T["line"]}"{A("rise", .25 + j * .18, .6)}>
        <div style="width:250px;font-size:28px">{esc(p["label"])}</div>
        <div style="flex:1;height:4px;background:{T["line"]};position:relative"><div style="position:absolute;left:0;top:-1px;height:6px;width:{p["score"]}%;background:{T["accent"]}"{A("grow-x", .45 + j * .18, 1.4)}></div></div>
        <div class="serif" style="width:64px;text-align:right;font-size:34px"{A("count", .45 + j * .18, 1.6, **{"in": 0})}>{p["score"]}</div></div>''' for j, p in enumerate(v["parts"]))
    return f'''<div class="col" style="gap:26px"><div class="row" style="align-items:baseline;gap:18px">
        <div class="serif" style="font-size:190px;line-height:.85;letter-spacing:-.04em"{A("count", 0, 2.4, al="right")}>{v["score"]}</div>
        <div class="serif" style="font-size:52px;color:{T["ink2"]}">/100</div>
        <div class="serif" style="margin-left:auto;font-size:60px;font-style:italic;color:{T["accent"]}"{A("fade", 2.0, .6)}>{esc(v["label"])}</div></div>
      <div class="col">{parts}</div></div>'''


def v_rows(v: dict) -> str:
    """Tabla limpia: nombre + detalle a la izquierda; a la derecha el valor, en la línea del nombre (cifras en tinta,
    palabras más pequeñas en gris), filetes finos y filas compactas."""
    def value(r: dict, j: int) -> str:
        num = any(c.isdigit() for c in str(r["value"]))
        unit = r.get("unit", v.get("unit", ""))
        style = f'font-size:{40 if num else 33}px;color:{T["ink"] if num else T["ink2"]};white-space:nowrap;letter-spacing:-.01em'
        return (f'''<div class="serif" style="{style}"{A("count", j * .35 + .1, 1.6, al="right", fb="none", **{"in": 0})}>{esc(r["value"])}'''
                f'''{f'<span style="font-family:GSF;font-size:19px;color:{T["ink2"]}"> {esc(unit)}</span>' if unit else ''}</div>''')
    rows = "".join(f'''<div class="row" style="align-items:baseline;justify-content:space-between;gap:24px;padding:15px 0;border-top:1px solid {T["line"]}"{A("rise", j * .35, .8)}>
        <div class="col" style="gap:3px"><div style="font-size:30px;font-weight:600">{esc(r["label"])}</div>
          {f'<div style="font-size:21px;color:{T["ink2"]}">{esc(r["detail"])}</div>' if r.get("detail") else ''}</div>
        {value(r, j)}</div>''' for j, r in enumerate(v["rows"]))
    head = label(v["title"], T["accent"]) if v.get("title") else ""
    return f'<div class="col" style="gap:14px">{head}<div class="col">{rows}<div style="border-top:1px solid {T["line"]}"></div></div></div>'


def smooth_path(xy: list) -> str:
    """Curva suave que pasa por todos los puntos sin pasarse de ellos (cúbica monótona, como d3.curveMonotoneX)."""
    n = len(xy)
    if n < 3:
        return "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in xy)
    dx = [xy[i + 1][0] - xy[i][0] for i in range(n - 1)]
    m = [(xy[i + 1][1] - xy[i][1]) / dx[i] for i in range(n - 1)]
    t = [m[0]] + [0.0 if m[i - 1] * m[i] <= 0 else (dx[i - 1] + dx[i]) * 3 / ((2 * dx[i] + dx[i - 1]) / m[i - 1] + (dx[i] + 2 * dx[i - 1]) / m[i])
                  for i in range(1, n - 1)] + [m[-1]]
    d = f"M{xy[0][0]:.1f},{xy[0][1]:.1f}"
    for i in range(n - 1):
        (x0, y0), (x1, y1), h = xy[i], xy[i + 1], dx[i] / 3
        d += f" C{x0 + h:.1f},{y0 + t[i] * h:.1f} {x1 - h:.1f},{y1 - t[i + 1] * h:.1f} {x1:.1f},{y1:.1f}"
    return d


def line_chart(points: list, w: int, h: int, band: list | None = None) -> str:
    lo, hi = min(points + (band or [])), max(points + (band or []))
    pad = (hi - lo) * .18 or 1
    lo, hi = lo - pad, hi + pad
    xy = [(i * w / (len(points) - 1), h - (p - lo) / (hi - lo) * h) for i, p in enumerate(points)]
    d = smooth_path(xy)
    out = f'<svg width="{w}" height="{h}" style="overflow:visible">'
    if band:
        y1, y2 = h - (band[1] - lo) / (hi - lo) * h, h - (band[0] - lo) / (hi - lo) * h
        out += f'<rect x="0" y="{y1:.1f}" width="{w}" height="{y2 - y1:.1f}" fill="{T["soft"]}"{A("grow-y", 0, .8)}/>'
    out += f'<path d="{d}" fill="none" stroke="{T["ink"]}" stroke-width="3" stroke-linejoin="round" stroke-linecap="round"{A("draw", .2, 2.4)}/>'
    x, y = xy[-1]
    return out + f'<circle cx="{x:.1f}" cy="{y:.1f}" r="11" fill="{T["accent"]}"{A("head", .2, 2.4)}/></svg>'


def v_metric(v: dict) -> str:
    return f'''<div class="col" style="gap:18px">{label(v["label"])}
      <div class="row" style="align-items:baseline;gap:14px"><div class="serif" style="font-size:180px;line-height:.85;letter-spacing:-.04em"{A("count", 0, 2.4, al="right")}>{esc(v["value"])}</div>
        <div class="serif" style="font-size:54px;color:{T["ink2"]}">{esc(v.get("unit", ""))}</div></div>
      <div class="serif" style="font-size:40px;font-style:italic;color:{T["accent"]}"{A("fade", 2.2, .6)}>{esc(v.get("caption", ""))}</div>
      <div style="margin-top:24px">{line_chart(v["points"], 920, 210, v.get("band"))}</div>
      {f'<div style="font-size:22px;color:{T["ink2"]}">{esc(v["note"])}</div>' if v.get("note") else ""}</div>'''


def v_ring(v: dict) -> str:
    size, stroke = 380, 10
    r = (size - stroke) / 2
    circ = 2 * math.pi * r
    side = "".join(f'''<div class="col" style="gap:2px;padding:16px 0;border-top:1.5px solid {T["line"]}"{A("rise", .6 + j * .2, .7)}>{label(s["label"])}
        <div class="serif" style="font-size:52px">{esc(s["value"])}</div></div>''' for j, s in enumerate(v.get("side", [])))
    return f'''<div class="row" style="gap:64px;align-items:center">
      <div style="position:relative;width:{size}px;height:{size}px"><svg width="{size}" height="{size}" style="transform:rotate(-90deg)">
        <circle cx="{size/2}" cy="{size/2}" r="{r}" fill="none" stroke="{T["line"]}" stroke-width="{stroke}"/>
        <circle cx="{size/2}" cy="{size/2}" r="{r}" fill="none" stroke="{T["accent"]}" stroke-width="{stroke}" stroke-linecap="round" stroke-dasharray="{circ * v["value"] / v.get("max", 100)} {circ}"{A("arc", .1, 2.4)}/></svg>
        <div style="position:absolute;inset:0;display:grid;place-content:center;text-align:center">
          <div class="serif" style="font-size:150px;line-height:.9"{A("count", .1, 2.6, al="center")}>{esc(v["center"])}</div><div style="font-size:24px;color:{T["ink2"]}">{esc(v.get("sub", ""))}</div></div></div>
      <div class="col" style="flex:1">{side}<div style="border-top:1.5px solid {T["line"]}"></div></div></div>'''


def v_curve(v: dict) -> str:
    w, h = 920, 330
    pts = v["points"]
    xy = [(p[0] / 24 * w, h - p[1] / 100 * h) for p in pts]
    d = smooth_path(xy)
    grid = "".join(f'<line x1="0" x2="{w}" y1="{h - g / 100 * h}" y2="{h - g / 100 * h}" stroke="{T["line"]}" stroke-width="1.5"/>' for g in (0, 50, 100))
    x, y = xy[-1]
    ticks = "".join(f'<div style="position:absolute;left:{0 if t == 0 else w - 80 if t == 24 else t / 24 * w - 40:.0f}px;width:80px;text-align:{"left" if t == 0 else "right" if t == 24 else "center"}">{t:02d}:00</div>' for t in (0, 6, 12, 18, 24))
    tag = f'<div class="serif" style="position:absolute;right:{w - x - 6:.0f}px;top:{y - 118:.0f}px;font-size:40px;font-style:italic;color:{T["accent"]};white-space:nowrap"{A("fade", 2.4, .6)}>{esc(v.get("tag", ""))}</div>' if v.get("tag") else ""
    return f'''<div class="col" style="gap:16px">{label(v.get("title", ""))}<div style="position:relative;width:{w}px;height:{h}px">{tag}
      <svg width="{w}" height="{h}" style="overflow:visible">{grid}<path d="{d}" fill="none" stroke="{T["ink"]}" stroke-width="3" stroke-linejoin="round" stroke-linecap="round"{A("draw", 0, 2.6)}/>
      <circle cx="{x:.0f}" cy="{y:.0f}" r="12" fill="{T["accent"]}"{A("head", 0, 2.6)}/></svg></div>
      <div style="position:relative;height:28px;font-size:20px;color:{T["ink2"]}">{ticks}</div></div>'''


def v_chat(v: dict) -> str:
    out = []
    for j, m in enumerate(v["messages"]):
        me = m["from"] == "user"
        out.append(f'''<div class="row" style="justify-content:{'flex-end' if me else 'flex-start'}">
          <div style="max-width:760px;padding:26px 32px;border-radius:{'34px 34px 8px 34px' if me else '34px 34px 34px 8px'};font-size:31px;line-height:1.38;
            {f'background:{T["ink"]};color:{T["bg"]}' if me else f'border:1.5px solid {T["ink"]};color:{T["ink"]}'}"{A("pop", j * 1.2, .7, s=.88, o="bottom right" if me else "bottom left")}>
            {'' if me else f'<div class="lab" style="font-size:18px;color:{T["accent"]};margin-bottom:8px">Coach Runch</div>'}{rich(m["text"])}</div></div>''')
    return f'<div class="col" style="gap:22px">{"".join(out)}</div>'


def v_schedule(v: dict) -> str:
    pts = v["points"]
    w, h, lo, hi = 760, 300, 0, 4.5
    band = v.get("band", [1.5, 2.5])
    y = lambda t: h - (t - lo) / (hi - lo) * h  # noqa: E731
    dots = "".join(f'<circle cx="{i * w / (len(pts) - 1):.0f}" cy="{y(t):.0f}" r="12" fill="{T["ink"] if band[0] <= t <= band[1] else T["accent"]}"{A("pop", .3 + i * .12, .45)}/>' for i, t in enumerate(pts))
    labels = "".join(f'<div style="position:absolute;left:-104px;top:{y(t) - 14:.0f}px;font-size:20px;color:{T["ink2"]}">{lab}</div>' for t, lab in ((0, "21:00"), (2, "23:00"), (4, "01:00")))
    return f'''<div class="col" style="gap:20px">{label(v.get("title", ""))}<div style="position:relative;margin-left:104px;width:{w}px;height:{h}px">{labels}
      <svg width="{w}" height="{h}" style="overflow:visible"><rect x="-20" y="{y(band[1]):.0f}" width="{w + 40}" height="{y(band[0]) - y(band[1]):.0f}" fill="{T["soft"]}"{A("grow-y", 0, .7)}/>{dots}</svg></div>
      <div style="font-size:22px;color:{T["ink2"]}">{esc(v.get("note", ""))}</div></div>'''


def v_steps(v: dict) -> str:
    rows = "".join(f'''<div class="row" style="align-items:center;gap:24px;padding:20px 0;border-top:1.5px solid {T["line"]}"{A("rise", j * .45, .8)}>
        <div style="width:14px;height:14px;border-radius:50%;background:{T["accent"] if s.get("hot") else T["ink2"]}"{A("pop", j * .45 + .3, .5)}></div>
        <div class="col" style="flex:1;gap:2px"><div style="font-size:31px;font-weight:600">{esc(s["name"])}</div><div style="font-size:22px;color:{T["ink2"]}">{esc(s.get("detail", ""))}</div></div>
        <div class="serif" style="font-size:40px;white-space:nowrap">{esc(s["pace"])}</div></div>''' for j, s in enumerate(v["steps"]))
    return f'<div class="col" style="gap:14px">{label(v.get("kicker", ""), T["accent"])}<div class="serif" style="font-size:44px">{esc(v.get("title", ""))}</div><div class="col" style="margin-top:8px">{rows}<div style="border-top:1.5px solid {T["line"]}"></div></div></div>'


VISUALS = {"zones": v_zones, "readiness": v_readiness, "rows": v_rows, "metric": v_metric, "ring": v_ring, "curve": v_curve,
           "chat": v_chat, "schedule": v_schedule, "steps": v_steps}


# ---------------------------------------------------------------- maqueta
def logo_src() -> str:
    """Logotipo «runch» (Gluten) en la tinta del tema: olivo sobre crema y papel, espresso sobre salvia y mantequilla
    (el olivo ahí apenas contrasta) y crema sobre fondos oscuros o de color."""
    color = T.get("logo", "crema")
    return (HERE.parent / "marca" / "logo" / f"runch-logo-{color}.svg").resolve().as_uri()


def frame_top(post: dict, k: int, s: dict) -> str:
    topic = s.get("topic") or post.get("topic") or ""
    return f'''<div class="row" style="justify-content:space-between;align-items:center">
      <img src="{logo_src()}" style="height:40px;display:block" alt="runch">
      {label(f"Nº {k:02d}" + (f"  ·  {topic}" if topic else ""), T["ink2"], 20)}</div>'''


def frame_bottom(i: int, n: int, example: bool) -> str:
    right = "Desliza →" if (n > 1 and i == 1) else (f"{i} / {n}" if n > 1 else "")
    mid = "Datos de ejemplo" if example else ""
    return f'''<div class="row" style="justify-content:space-between;align-items:center">
      {label(STYLE.get("handle") or "", T["ink"], 20)}{label(mid, T["ink2"], 17)}{label(right, T["ink"], 20)}</div>'''


def slide_html(post: dict, s: dict, i: int, n: int, k: int) -> str:
    theme = s.get("bg") or (post.get("bg") if i == 1 else post.get("inner", "paper")) or "cream"
    T.clear()
    T.update(THEMES[theme])
    layout = s.get("layout", "cover")
    example = s.get("example", "visual" in s or layout == "versus")
    title = lambda size, extra="": f'<div class="title" style="font-size:{size}px;{extra}">{rich(s["title"])}</div>'  # noqa: E731
    lead = lambda extra="": f'<div class="lead" style="{extra}">{rich(s["body"])}</div>' if s.get("body") else ""  # noqa: E731
    kick = label(s["kicker"], T["accent"]) if s.get("kicker") else ""

    if layout == "hook":
        facts = "".join(f'<span>{esc(f)}</span>' for f in s.get("facts", []))
        body = f'''<div style="flex:1"></div>{kick}{title(s.get("size", 128), "margin-top:22px")}
          {lead("margin-top:34px;font-size:36px;max-width:820px")}
          {f'<div class="facts" style="margin-top:44px">{facts}</div>' if facts else ''}<div style="flex:.35"></div>'''
    elif layout == "cover":
        vis = s.get("visual")
        body = f'''<div style="flex:.5"></div>{kick}{title(s.get("size", 84), "margin-top:16px")}{lead("margin-top:22px")}
          <div style="flex:1"></div>{VISUALS[vis["type"]](vis) if vis else ''}<div style="flex:.5"></div>'''
    elif layout == "points":
        items = "".join(f'''<div class="row" style="gap:34px;padding:30px 0;border-top:1.5px solid {T["line"]};align-items:baseline">
            <div class="serif" style="width:76px;font-size:44px;font-style:italic;color:{T["accent"]}">{j + 1:02d}</div>
            <div class="col" style="flex:1;gap:8px"><div style="font-size:38px;font-weight:650;letter-spacing:-.01em">{rich(q["title"])}</div>
              <div style="font-size:29px;line-height:1.4;color:{T["ink2"]}">{rich(q["body"])}</div></div></div>''' for j, q in enumerate(s["points"]))
        body = f'''<div style="flex:.6"></div>{kick}{title(s.get("size", 82), "margin-top:16px;margin-bottom:40px")}
          <div class="col">{items}<div style="border-top:1.5px solid {T["line"]}"></div></div><div style="flex:1"></div>'''
    elif layout == "versus":
        def side(x: dict, good: bool) -> str:  # con `animate`, las dos cifras cuentan hacia arriba
            lines = "".join(f'<div style="font-size:27px;line-height:1.4;color:{T["ink2"]}">{rich(t)}</div>' for t in x.get("lines", []))
            return f'''<div class="col" style="flex:1;gap:16px">{label(x["label"], T["accent"] if good else T["ink2"])}
              <div class="serif" style="font-size:130px;line-height:.9;letter-spacing:-.04em;{f'color:{T["accent"]}' if good else ''}"{A("count", .5 if good else 0, 2.2, fb="rise")}>{esc(x["value"])}</div>
              <div style="font-size:22px;color:{T["ink2"]};margin-top:-6px">{esc(x.get("unit", ""))}</div><div class="col" style="gap:6px;margin-top:10px">{lines}</div></div>'''
        body = f'''<div style="flex:.5"></div>{kick}{title(s.get("size", 80), "margin-top:16px")}<div style="flex:1"></div>
          <div class="row" style="gap:48px;align-items:stretch;padding:40px 0;border-top:1.5px solid {T["line"]};border-bottom:1.5px solid {T["line"]}">
            {side(s["left"], False)}<div class="serif" style="align-self:center;font-size:56px;font-style:italic;color:{T["ink2"]}">vs</div>{side(s["right"], True)}</div>
          {lead("margin-top:30px")}<div style="flex:.6"></div>'''
    elif layout == "big":
        body = f'''<div style="flex:1"></div>{kick}
          <div class="serif" style="font-size:{s.get("bigSize", 380)}px;line-height:.82;letter-spacing:-.05em;color:{T["accent"]};margin-top:10px"{A("count", 0, 2.6, mask=1)}>{esc(s["big"])}</div>
          {title(s.get("size", 70), "margin-top:36px")}{lead("margin-top:24px")}<div style="flex:.6"></div>'''
    elif layout == "photo":  # para cuando haya fotos (quedadas, estilo de vida): imagen a sangre + texto abajo
        body = f'''<div style="flex:1"></div>{kick}{title(s.get("size", 100), "margin-top:16px")}{lead("margin-top:22px")}<div style="flex:.2"></div>'''
    elif layout == "cta":
        acts = "  ·  ".join(esc(a) for a in s.get("actions", ["Guárdalo", "Compártelo", "Síguenos"]))
        body = f'''<div style="flex:1"></div>
          <div class="serif" style="text-align:center;font-size:210px;line-height:.9;letter-spacing:-.04em">Runch</div>
          {title(s.get("size", 64), "text-align:center;margin-top:46px")}{lead("text-align:center;align-self:center;margin-top:20px")}
          <div style="text-align:center;margin-top:52px">{label(acts, T["accent"], 24)}</div><div style="flex:1.2"></div>'''
    else:
        raise ValueError(f"layout desconocido: {layout}")
    photo = ""
    if layout == "photo" and s.get("image"):
        src = (HERE / s["image"]).resolve().as_uri()
        photo = (f'<div style="position:absolute;inset:0;background:url(\'{src}\') center/cover"></div>'
                 f'<div style="position:absolute;inset:0;background:linear-gradient(180deg,rgba(0,0,0,.05) 35%,rgba(20,14,10,.7))"></div>')
        T.update(THEMES["espresso"], bg="transparent")
    fonts = HERE / "fonts"
    ff = lambda fam, file, style="normal", rng="": f'@font-face {{ font-family: {fam}; font-style: {style}; font-weight: 1 1000; src: url("file://{fonts}/{file}") format("woff2-variations"); {rng} }}'  # noqa: E731
    LAT = "unicode-range: U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212;"
    EXT = "unicode-range: U+0100-02BA, U+1E00-1EFF, U+2C60-2C7F, U+A720-A7FF;"
    return f'''<!doctype html><html lang="es"><head><meta charset="utf-8"><style>
      {ff("GSF", "google-sans-flex-latin-wght-normal.woff2", rng=LAT)} {ff("GSF", "google-sans-flex-latin-ext-wght-normal.woff2", rng=EXT)}
      {ff("FR", "fraunces-latin-full-normal.woff2", rng=LAT)} {ff("FR", "fraunces-latin-ext-full-normal.woff2", rng=EXT)}
      {ff("FR", "fraunces-latin-full-italic.woff2", "italic", LAT)} {ff("FR", "fraunces-latin-ext-full-italic.woff2", "italic", EXT)}
      * {{ box-sizing: border-box; margin: 0; }}
      body {{ width: {W}px; height: {H}px; font-family: GSF, system-ui, sans-serif; color: {T["ink"]}; -webkit-font-smoothing: antialiased; }}
      .slide {{ position: relative; width: {W}px; height: {H}px; background: {THEMES[theme]["bg"]}; overflow: hidden; }}
      .content {{ position: relative; height: 100%; padding: 64px 84px 56px; display: flex; flex-direction: column; }}
      .row {{ display: flex; }} .col {{ display: flex; flex-direction: column; }}
      .serif {{ font-family: FR, Georgia, serif; font-weight: 420; font-variation-settings: "SOFT" 50, "WONK" 0; }}
      .title {{ font-family: FR, Georgia, serif; font-weight: 440; letter-spacing: -.018em; line-height: 1.0; text-wrap: balance;
        font-variation-settings: "SOFT" 50, "WONK" 0; color: {T["ink"]}; }}
      .title em, .lead em {{ font-style: italic; color: {T["accent"]}; font-variation-settings: "SOFT" 100, "WONK" 1; }}
      .lead {{ font-size: 33px; line-height: 1.42; color: {T["ink2"]}; text-wrap: pretty; max-width: 860px; }}
      .lead em {{ font-family: FR, Georgia, serif; }}
      .lab {{ font-weight: 650; letter-spacing: .16em; text-transform: uppercase; }}
      .facts {{ display: flex; flex-wrap: wrap; gap: 14px 0; }}
      .facts span {{ font-size: 22px; font-weight: 650; letter-spacing: .14em; text-transform: uppercase; color: {T["ink"]}; }}
      .facts span + span::before {{ content: "·"; margin: 0 18px; color: {T["accent"]}; }}
    </style></head><body><div class="slide">{photo}<div class="content">{frame_top(post, k, s)}{body}{frame_bottom(i, n, example)}</div></div></body></html>'''


# ---------------------------------------------------------------- vídeo de una diapositiva (`"animate": true`)
# Solo se mueve el gráfico: cada elemento marcado con A() se pinta en función del tiempo con window.__render(t) (sin
# animaciones CSS ni reloj real, así cada fotograma es exacto). Al terminar su animación, cada elemento recupera su
# estilo original, de modo que el último fotograma es idéntico al PNG.
LEAD, HOLD, FPS = .4, 2.0, 30  # quieto al principio, mínimo quieto al final, fotogramas por segundo
ANIM_JS = r"""(() => {
  const clamp = (x) => Math.min(1, Math.max(0, x));
  const out3 = (p) => 1 - Math.pow(1 - p, 3), out5 = (p) => 1 - Math.pow(1 - p, 5);
  const back = (p) => 1 + 2.2 * Math.pow(p - 1, 3) + 1.2 * Math.pow(p - 1, 2);
  // cifras dentro del texto: 12 · 7,5 · 12.500 · ritmos 5:15 / 1:45:00 (cuentan en segundos); prefijos (<, +, −),
  // sufijos (%, unidades) y rangos (95–114, 5:49–6:34) se respetan. Sin cifras: `data-fb` (fundido por defecto)
  const NUM = /\d+(?::\d{2})+|\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:[.,]\d+)?/g;
  const parse = (num) => {
    if (num.includes(':')) return { clock: num.split(':').length, to: num.split(':').reduce((s, x) => s * 60 + +x, 0) };
    const tsep = /^\d{1,3}(\.\d{3})+/.test(num) ? '.' : '', body = tsep ? num.split('.').join('') : num;
    const dm = body.match(/[.,](\d+)$/);
    return { tsep, dsep: dm ? body[body.length - dm[1].length - 1] : ',', dec: dm ? dm[1].length : 0, to: parseFloat(body.replace(',', '.')) };
  };
  const fmt = (c, v) => {
    if (c.clock) {
      let x = Math.round(v); const parts = [];
      for (let k = 1; k < c.clock; k++) { parts.unshift(String(x % 60).padStart(2, '0')); x = Math.floor(x / 60); }
      return [x, ...parts].join(':');
    }
    let txt = v.toFixed(c.dec).replace('.', c.dsep);
    if (c.tsep) { const [a, b] = txt.split(c.dsep); txt = a.replace(/\B(?=(\d{3})+(?!\d))/g, c.tsep) + (b !== undefined ? c.dsep + b : ''); }
    return txt;
  };
  const items = [...document.querySelectorAll('[data-a]')].map((el) => {
    const ds = el.dataset;
    const o = { el, a: ds.a, d: +ds.d || 0, t: +ds.t || .7, style: el.getAttribute('style'), op: +getComputedStyle(el).opacity };
    o.end = o.d + o.t;
    if (o.a === 'zone') o.end = Math.max(o.end, +ds.d2 + .7);
    if (o.a === 'draw') o.len = el.getTotalLength();
    if (o.a === 'head') {
      o.path = el.parentNode.querySelector('[data-a=draw]');
      o.len = o.path.getTotalLength(); o.cx = +el.getAttribute('cx'); o.cy = +el.getAttribute('cy');
    }
    if (o.a === 'arc') [o.arc, o.gap] = el.getAttribute('stroke-dasharray').trim().split(/[\s,]+/).map(Number);
    if (o.a === 'count') {
      o.node = [...el.childNodes].find((n) => n.nodeType === 3 && /\d/.test(n.nodeValue));
      if (!o.node) { o.a = ds.fb || 'fade'; return o; }
      o.raw = o.node.nodeValue;
      const nums = o.raw.match(NUM), pieces = o.raw.split(NUM), cs = nums.map(parse);
      o.text = (e) => pieces.map((x, i) => x + (i < cs.length ? fmt(cs[i], cs[i].to * e) : '')).join('');
      const last = o.text(1);
      o.land = 1;  // momento (0..1) en que ya se ve la cifra final: ahí vuelve el texto original
      for (let k = 0; k <= 480; k++) if (o.text(out5(k / 480)) === last) { o.land = k / 480; break; }
      o.w = el.getBoundingClientRect().width;
      o.al = ds.al || getComputedStyle(el).textAlign.replace('start', 'left').replace('end', 'right');
      o.hero = ds.in !== '0';
      o.end = o.d + o.land * o.t + .4;
    }
    return o;
  });
  const end = Math.max(0, ...items.filter((o) => o.a !== 'none').map((o) => o.end));
  const render = (t) => {
    for (const o of items) {
      const p = clamp((t - o.d) / o.t), e = out3(p), st = o.el.style;
      if (o.style === null) o.el.removeAttribute('style'); else o.el.setAttribute('style', o.style);
      if (o.a === 'count') o.node.nodeValue = o.raw;
      if (t >= o.end || o.a === 'none') continue;  // estado final = estilo y texto originales, igual que el PNG
      switch (o.a) {
        case 'fade': st.opacity = o.op * e; break;
        case 'rise': st.opacity = o.op * e; st.transform = `translateY(${(1 - e) * 18}px)`; break;
        case 'zone': {
          const q = out3(clamp((t - +o.el.dataset.d2) / .7));
          st.opacity = e * (1 + (o.op - 1) * q); st.transform = `translateY(${(1 - e) * 18}px)`; break;
        }
        case 'grow-x': st.transformOrigin = 'left center'; st.transform = `scaleX(${e})`; break;
        case 'grow-y': st.transformBox = 'fill-box'; st.transformOrigin = 'center'; st.transform = `scaleY(${e})`; st.opacity = Math.min(1, p * 2.5); break;
        case 'pop': {
          const s0 = +(o.el.dataset.s || 0), k = s0 + (1 - s0) * back(p);
          st.transformBox = 'fill-box'; st.transformOrigin = o.el.dataset.o || 'center';
          st.transform = `${s0 ? `translateY(${(1 - e) * 16}px) ` : ''}scale(${Math.max(0, k)})`; st.opacity = o.op * Math.min(1, p * 2.5); break;
        }
        case 'draw': st.strokeDasharray = `${o.len} ${o.len}`; st.strokeDashoffset = o.len * (1 - e); if (p <= 0) st.opacity = 0; break;
        case 'head': {
          const pt = o.path.getPointAtLength(o.len * e);
          st.transformBox = 'fill-box'; st.transformOrigin = 'center';
          st.transform = `translate(${pt.x - o.cx}px, ${pt.y - o.cy}px) scale(${Math.min(1, p * 8)})`; break;
        }
        case 'arc': st.strokeDasharray = `${o.arc * e} ${o.gap}`; if (p <= 0) st.opacity = 0; break;
        case 'count': {
          // caja fija con cifras tabulares mientras cuenta (nada baila ni empuja a sus vecinos)
          const landed = p >= o.land;
          if (!landed) {
            o.node.nodeValue = o.text(out5(p));
            st.fontVariantNumeric = 'tabular-nums'; st.flex = 'none'; st.width = `${o.w}px`; st.whiteSpace = 'nowrap'; st.textAlign = o.al;
          }
          const tr = [];
          if (o.hero) {  // entrada: sube, crece de 0,92 a 1 y aparece; en `big`, además un barrido de abajo arriba
            const q = out3(clamp((t - o.d) / .6));
            st.opacity = o.op * q; tr.push(`translateY(${(1 - q) * 30}px)`, `scale(${.92 + .08 * q})`);
            if (o.el.dataset.mask) { const m = out3(clamp((t - o.d) / .55)); st.clipPath = `inset(${(1 - m) * 100}% -30% -30% -30%)`; }
          }
          if (landed) {  // asiento suave al llegar
            const s = clamp((t - (o.d + o.land * o.t)) / .4);
            tr.push(`scale(${1 + .03 * Math.sin(Math.PI * s) * (1 - s)})`);
          }
          st.transformOrigin = `${o.al === 'right' ? 'right' : o.al === 'center' ? 'center' : 'left'} bottom`;
          st.transform = tr.join(' ');
          break;
        }
      }
    }
  };
  window.__render = render;
  return end;
})()"""


def ffmpeg_bin() -> str | None:
    return shutil.which("ffmpeg") or (glob.glob(os.path.expanduser("~/.cache/ms-playwright/ffmpeg-*/ffmpeg-linux")) or [None])[0]


def record(pg, out: Path, stem: str, duration: float) -> str | None:
    """Graba la diapositiva abierta en `pg` como <stem>.mp4 (1080 x 1350, H.264, 30 fps, sin audio) y una hoja de
    contacto <stem>-frames.png con 6 fotogramas. Devuelve el nombre del MP4, o None si no hay nada que animar."""
    ff = ffmpeg_bin()
    if not ff:
        print(f"AVISO: {stem}: no encuentro ffmpeg (sudo apt install ffmpeg), solo queda el PNG")
        return None
    end = pg.evaluate(ANIM_JS)
    if not end:
        print(f"AVISO: {stem}: \"animate\" en una diapositiva sin gráfico que animar, solo queda el PNG")
        return None
    total = max(duration, LEAD + end + HOLD)
    tmp = out / "_frames"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir()
    n = round(total * FPS)
    for f in range(n):
        pg.evaluate(f"window.__render({f / FPS - LEAD})")
        pg.screenshot(path=str(tmp / f"{f:04d}.png"))
    mp4 = out / f"{stem}.mp4"
    # sRGB → BT.709 de rango limitado, etiquetado, para que los colores salgan iguales que en el PNG
    subprocess.run([ff, "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", str(tmp / "%04d.png"),
                    "-vf", "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p",
                    "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-profile:v", "high", "-r", str(FPS),
                    "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv",
                    "-an", "-movflags", "+faststart", str(mp4)], check=True)
    shutil.rmtree(tmp)
    # hoja de contacto: inicio, cuatro momentos de la animación y el final
    picks = [round(.2 * FPS)] + [round((LEAD + end * q) * FPS) for q in (.15, .4, .7, 1)] + [n - 1]
    sel = "+".join(f"eq(n\\,{min(x, n - 1)})" for x in picks)
    subprocess.run([ff, "-y", "-loglevel", "error", "-i", str(mp4), "-vf", f"select='{sel}',scale=360:450,tile=3x2:padding=6",
                    "-vsync", "0", "-frames:v", "1", str(out / f"{stem}-frames.png")], check=True)
    print(f"Vídeo: {mp4.name} ({total:.1f} s, animación {end:.1f} s, {mp4.stat().st_size / 1e6:.1f} MB)")
    return mp4.name


# ---------------------------------------------------------------- salida
def main(path: str, sub: str = "") -> None:
    from playwright.sync_api import sync_playwright
    lote = json.loads(Path(path).read_text())
    STYLE["handle"] = lote.get("handle")
    out = HERE / "out" / sub / f"lote-{lote['lote']}"
    out.mkdir(parents=True, exist_ok=True)
    for f in [*out.glob("*.png"), *out.glob("*.mp4")]:
        f.unlink()
    exe = (glob.glob(os.path.expanduser("~/.cache/ms-playwright/chromium_headless_shell-*/*/chrome-headless-shell")) or [None])[0]
    covers, md = [], [f"# Instagram · lote {lote['lote']}\n", lote.get("notes", ""), ""]
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=exe) if exe else p.chromium.launch()
        pg = b.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
        for k, post in enumerate(lote["posts"], 1):
            files, n = [], len(post["slides"])
            for i, s in enumerate(post["slides"], 1):
                tmp = out / "_slide.html"
                tmp.write_text(slide_html(post, s, i, n, k), encoding="utf-8")
                pg.goto(tmp.as_uri())
                pg.evaluate("document.fonts.ready")
                pg.wait_for_timeout(150)
                over = pg.evaluate("() => { const s = document.querySelector('.content'); return s.scrollHeight - s.clientHeight; }")
                if over > 1:
                    print(f"AVISO: {post['id']} diapositiva {i} no cabe ({over}px de más)")
                edge = pg.evaluate("""() => { let m = 0; document.querySelectorAll('.content *').forEach(e => { const q = e.getBoundingClientRect();
                    if (q.width) m = Math.max(m, q.right - (innerWidth - 60), 60 - q.left); }); return Math.round(m); }""")
                if edge > 1:
                    print(f"AVISO: {post['id']} diapositiva {i}: algo se acerca demasiado al borde ({edge}px)")
                name = f"{k:02d}-{post['id']}-{i}.png"
                pg.screenshot(path=str(out / name))
                vid = record(pg, out, name[:-4], float(s.get("duration", 6))) if s.get("animate") else None
                files.append(f"{vid} (vídeo; portada y reserva: {name})" if vid else name)
                if i == 1:
                    covers.append(out / name)
            (out / "_slide.html").unlink(missing_ok=True)
            md += [f"## Post {k} · {post['title']}", "", f"Archivos: {', '.join(files)}" + (" (carrusel)" if n > 1 else ""), "",
                   "**Texto:**", "", post["caption"].strip(), "", " ".join(post.get("hashtags", [])), "",
                   f"**Texto alternativo:** {post.get('alt', '')}", "", "---", ""]
        cells = "".join(f'<img src="{c.as_uri()}" style="width:100%;aspect-ratio:3/4;object-fit:cover;display:block">' for c in reversed(covers))
        pg.set_viewport_size({"width": 1080, "height": 1440})
        grid = out / "_grid.html"
        grid.write_text(f'<html><body style="margin:0;background:#fff"><div style="display:grid;grid-template-columns:repeat(3,1fr);gap:4px;width:1080px">{cells}</div></body></html>')
        pg.goto(grid.as_uri())
        pg.wait_for_timeout(300)
        pg.screenshot(path=str(out / "grid.png"), full_page=True)
        grid.unlink()
        b.close()
    (out / "captions.md").write_text("\n".join(md), encoding="utf-8")
    write_overview(lote, out)
    print(f"{len(lote['posts'])} posts en {out}")


def write_overview(lote: dict, out: Path) -> None:
    """todos.html: cada post en una fila con sus imágenes en orden y, debajo, el texto y los hashtags."""
    rows = []
    for k, post in enumerate(lote["posts"], 1):
        n = len(post["slides"])
        imgs = "".join(f'<a href="{f}.mp4" target="_blank"><video src="{f}.mp4" poster="{f}.png" autoplay loop muted playsinline></video></a>'
                       if (out / f"{f}.mp4").exists() else f'<a href="{f}.png" target="_blank"><img src="{f}.png"></a>'
                       for f in (f'{k:02d}-{post["id"]}-{i}' for i in range(1, n + 1)))
        rows.append(f'''<section><div class="head"><span class="num">{k:02d}</span><h2>{esc(post["title"])}</h2><span class="meta">{n} {"imágenes · carrusel" if n > 1 else "imagen"}</span></div>
          <div class="imgs">{imgs}</div><details open><summary>Texto del post</summary><p>{esc(post["caption"]).replace(chr(10), "<br>")}</p>
          <p class="tags">{esc(" ".join(post.get("hashtags", [])))}</p><p class="alt">Texto alternativo: {esc(post.get("alt", ""))}</p></details></section>''')
    (out / "todos.html").write_text(f'''<!doctype html><html lang="es"><head><meta charset="utf-8"><title>Runch · lote {lote["lote"]}</title><style>
      @font-face {{ font-family: FR; src: url("../../fonts/fraunces-latin-full-normal.woff2"); }}
      @font-face {{ font-family: GSF; src: url("../../fonts/google-sans-flex-latin-wght-normal.woff2"); }}
      body {{ margin: 0; background: #EDE5D9; font-family: GSF, system-ui, sans-serif; color: #221A15; }}
      header {{ padding: 32px 36px 8px; }} header h1 {{ margin: 0; font-family: FR, serif; font-weight: 450; font-size: 40px; }} header p {{ color: #76695F; }}
      section {{ background: #FAF6F0; margin: 18px 28px; padding: 22px 24px; border-radius: 18px; }}
      .head {{ display: flex; align-items: baseline; gap: 14px; margin-bottom: 14px; }} h2 {{ margin: 0; font-family: FR, serif; font-weight: 450; font-size: 26px; }}
      .num {{ font-family: FR, serif; font-style: italic; color: #5A6B32; font-size: 24px; }} .meta {{ margin-left: auto; color: #76695F; font-size: 14px; }}
      .imgs {{ display: flex; gap: 12px; overflow-x: auto; }} .imgs img, .imgs video {{ height: min(52vh, 460px); aspect-ratio: 4/5; border-radius: 6px; display: block; }}
      summary {{ cursor: pointer; color: #5A6B32; font-weight: 600; margin-top: 12px; }} details p {{ max-width: 760px; line-height: 1.5; }}
      .tags {{ color: #5A6B32; }} .alt {{ color: #76695F; font-size: 14px; }}
    </style></head><body><header><h1>Runch · lote {lote["lote"]}</h1><p>{esc(lote.get("notes", ""))}</p></header>{"".join(rows)}</body></html>''', encoding="utf-8")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    sub = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else ""
    args = [a for a in args if a != sub]
    main(args[0] if args else str(HERE / "lote-01.json"), sub)
