"""Posts de Instagram de Runch (1080 x 1350, 4:5) con el sistema editorial: crema, espresso y terracota, titulares en
serif (Fraunces) con la palabra clave en cursiva, textos en Google Sans Flex y gráficos de línea fina.

Uso:
  uv run --no-project --with playwright python marketing/instagram/render.py marketing/instagram/lote-01.json

Salida en marketing/instagram/out/lote-NN/: un PNG por diapositiva, captions.md, grid.png (cuadrícula del perfil) y
todos.html (todo el lote para revisar). Formato del lote y sistema visual: README.md de esta carpeta.
"""

from __future__ import annotations

import glob
import html
import json
import math
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ICONS = json.loads((HERE / "icons.json").read_text())
W, H = 1080, 1350

# ---------------------------------------------------------------- sistema visual
# Fondos (uno por diapositiva): tinta, tinta secundaria, acento, línea fina.
THEMES = {
    "cream":      {"bg": "#F3ECE2", "ink": "#221A15", "ink2": "#76695F", "accent": "#D4542F", "line": "rgba(34,26,21,.16)", "soft": "#EAE0D2"},
    "paper":      {"bg": "#FAF6F0", "ink": "#221A15", "ink2": "#76695F", "accent": "#D4542F", "line": "rgba(34,26,21,.14)", "soft": "#F1EADF"},
    "terracotta": {"bg": "#D4542F", "ink": "#FBF3E8", "ink2": "rgba(251,243,232,.78)", "accent": "#FFE1A3", "line": "rgba(251,243,232,.3)", "soft": "#C64A27"},
    "espresso":   {"bg": "#221A15", "ink": "#F3ECE2", "ink2": "#B4A79A", "accent": "#EE7550", "line": "rgba(243,236,226,.18)", "soft": "#2E241E"},
    "sage":       {"bg": "#CBD3B8", "ink": "#221A15", "ink2": "#53584A", "accent": "#B1432A", "line": "rgba(34,26,21,.16)", "soft": "#BFC8AA"},
    "sea":        {"bg": "#24496D", "ink": "#F3ECE2", "ink2": "#BCCADA", "accent": "#F4C56E", "line": "rgba(243,236,226,.2)", "soft": "#2B5379"},
    "butter":     {"bg": "#F1DEA6", "ink": "#221A15", "ink2": "#6D5F43", "accent": "#C24A28", "line": "rgba(34,26,21,.16)", "soft": "#E8D294"},
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


def label(text: str, color: str | None = None, size: int = 21) -> str:
    return f'<div class="lab" style="font-size:{size}px;color:{color or T["ink2"]}">{esc(text)}</div>'


# ---------------------------------------------------------------- gráficos de línea fina
def v_zones(v: dict) -> str:
    hi = v.get("highlight", 2)
    rows = []
    for z in v["rows"]:
        on = z["zone"] == hi
        col = T["accent"] if on else T["ink"]
        rows.append(f'''<div class="row" style="align-items:center;gap:26px;padding:20px 0;border-top:1.5px solid {T["line"]};opacity:{1 if on else .55}">
          <div class="serif" style="width:84px;font-size:44px;color:{col}">Z{z["zone"]}</div>
          <div style="flex:1;font-size:32px;font-weight:{650 if on else 450}">{esc(z["name"])}</div>
          <div class="serif" style="font-size:40px;color:{col}">{esc(z["range"])}</div>
          <div style="width:30px;font-size:20px;color:{T["ink2"]}">{esc(v.get("unit", ""))}</div></div>''')
    return f'<div class="col">{"".join(rows)}<div style="border-top:1.5px solid {T["line"]}"></div></div>'


def v_readiness(v: dict) -> str:
    parts = "".join(f'''<div class="row" style="align-items:center;gap:22px;padding:14px 0;border-top:1.5px solid {T["line"]}">
        <div style="width:250px;font-size:28px">{esc(p["label"])}</div>
        <div style="flex:1;height:4px;background:{T["line"]};position:relative"><div style="position:absolute;left:0;top:-1px;height:6px;width:{p["score"]}%;background:{T["accent"]}"></div></div>
        <div class="serif" style="width:64px;text-align:right;font-size:34px">{p["score"]}</div></div>''' for p in v["parts"])
    return f'''<div class="col" style="gap:26px"><div class="row" style="align-items:baseline;gap:18px">
        <div class="serif" style="font-size:190px;line-height:.85;letter-spacing:-.04em">{v["score"]}</div>
        <div class="serif" style="font-size:52px;color:{T["ink2"]}">/100</div>
        <div class="serif" style="margin-left:auto;font-size:60px;font-style:italic;color:{T["accent"]}">{esc(v["label"])}</div></div>
      <div class="col">{parts}</div></div>'''


def v_rows(v: dict) -> str:
    rows = "".join(f'''<div class="row" style="align-items:baseline;justify-content:space-between;gap:24px;padding:20px 0;border-top:1.5px solid {T["line"]}">
        <div class="col" style="gap:4px"><div style="font-size:33px;font-weight:600">{esc(r["label"])}</div>
          {f'<div style="font-size:23px;color:{T["ink2"]}">{esc(r["detail"])}</div>' if r.get("detail") else ''}</div>
        <div class="serif" style="font-size:52px;white-space:nowrap;letter-spacing:-.02em">{esc(r["value"])}<span style="font-family:GSF;font-size:22px;color:{T["ink2"]}"> {esc(r.get("unit", v.get("unit", "")))}</span></div></div>'''
                   for r in v["rows"])
    head = label(v["title"], T["accent"]) if v.get("title") else ""
    return f'<div class="col" style="gap:14px">{head}<div class="col">{rows}<div style="border-top:1.5px solid {T["line"]}"></div></div></div>'


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
        out += f'<rect x="0" y="{y1:.1f}" width="{w}" height="{y2 - y1:.1f}" fill="{T["soft"]}"/>'
    out += f'<path d="{d}" fill="none" stroke="{T["ink"]}" stroke-width="3" stroke-linejoin="round" stroke-linecap="round"/>'
    x, y = xy[-1]
    return out + f'<circle cx="{x:.1f}" cy="{y:.1f}" r="11" fill="{T["accent"]}"/></svg>'


def v_metric(v: dict) -> str:
    return f'''<div class="col" style="gap:18px">{label(v["label"])}
      <div class="row" style="align-items:baseline;gap:14px"><div class="serif" style="font-size:180px;line-height:.85;letter-spacing:-.04em">{esc(v["value"])}</div>
        <div class="serif" style="font-size:54px;color:{T["ink2"]}">{esc(v.get("unit", ""))}</div></div>
      <div class="serif" style="font-size:40px;font-style:italic;color:{T["accent"]}">{esc(v.get("caption", ""))}</div>
      <div style="margin-top:24px">{line_chart(v["points"], 920, 210, v.get("band"))}</div>
      {f'<div style="font-size:22px;color:{T["ink2"]}">{esc(v["note"])}</div>' if v.get("note") else ""}</div>'''


def v_ring(v: dict) -> str:
    size, stroke = 380, 10
    r = (size - stroke) / 2
    circ = 2 * math.pi * r
    side = "".join(f'''<div class="col" style="gap:2px;padding:16px 0;border-top:1.5px solid {T["line"]}">{label(s["label"])}
        <div class="serif" style="font-size:52px">{esc(s["value"])}</div></div>''' for s in v.get("side", []))
    return f'''<div class="row" style="gap:64px;align-items:center">
      <div style="position:relative;width:{size}px;height:{size}px"><svg width="{size}" height="{size}" style="transform:rotate(-90deg)">
        <circle cx="{size/2}" cy="{size/2}" r="{r}" fill="none" stroke="{T["line"]}" stroke-width="{stroke}"/>
        <circle cx="{size/2}" cy="{size/2}" r="{r}" fill="none" stroke="{T["accent"]}" stroke-width="{stroke}" stroke-linecap="round" stroke-dasharray="{circ * v["value"] / v.get("max", 100)} {circ}"/></svg>
        <div style="position:absolute;inset:0;display:grid;place-content:center;text-align:center">
          <div class="serif" style="font-size:150px;line-height:.9">{esc(v["center"])}</div><div style="font-size:24px;color:{T["ink2"]}">{esc(v.get("sub", ""))}</div></div></div>
      <div class="col" style="flex:1">{side}<div style="border-top:1.5px solid {T["line"]}"></div></div></div>'''


def v_curve(v: dict) -> str:
    w, h = 920, 330
    pts = v["points"]
    xy = [(p[0] / 24 * w, h - p[1] / 100 * h) for p in pts]
    d = smooth_path(xy)
    grid = "".join(f'<line x1="0" x2="{w}" y1="{h - g / 100 * h}" y2="{h - g / 100 * h}" stroke="{T["line"]}" stroke-width="1.5"/>' for g in (0, 50, 100))
    x, y = xy[-1]
    ticks = "".join(f'<div style="position:absolute;left:{0 if t == 0 else w - 80 if t == 24 else t / 24 * w - 40:.0f}px;width:80px;text-align:{"left" if t == 0 else "right" if t == 24 else "center"}">{t:02d}:00</div>' for t in (0, 6, 12, 18, 24))
    tag = f'<div class="serif" style="position:absolute;right:{w - x - 6:.0f}px;top:{y - 118:.0f}px;font-size:40px;font-style:italic;color:{T["accent"]};white-space:nowrap">{esc(v.get("tag", ""))}</div>' if v.get("tag") else ""
    return f'''<div class="col" style="gap:16px">{label(v.get("title", ""))}<div style="position:relative;width:{w}px;height:{h}px">{tag}
      <svg width="{w}" height="{h}" style="overflow:visible">{grid}<path d="{d}" fill="none" stroke="{T["ink"]}" stroke-width="3" stroke-linejoin="round" stroke-linecap="round"/>
      <circle cx="{x:.0f}" cy="{y:.0f}" r="12" fill="{T["accent"]}"/></svg></div>
      <div style="position:relative;height:28px;font-size:20px;color:{T["ink2"]}">{ticks}</div></div>'''


def v_chat(v: dict) -> str:
    out = []
    for m in v["messages"]:
        me = m["from"] == "user"
        out.append(f'''<div class="row" style="justify-content:{'flex-end' if me else 'flex-start'}">
          <div style="max-width:760px;padding:26px 32px;border-radius:{'34px 34px 8px 34px' if me else '34px 34px 34px 8px'};font-size:31px;line-height:1.38;
            {f'background:{T["ink"]};color:{T["bg"]}' if me else f'border:1.5px solid {T["ink"]};color:{T["ink"]}'}">
            {'' if me else f'<div class="lab" style="font-size:18px;color:{T["accent"]};margin-bottom:8px">Coach Runch</div>'}{rich(m["text"])}</div></div>''')
    return f'<div class="col" style="gap:22px">{"".join(out)}</div>'


def v_schedule(v: dict) -> str:
    pts = v["points"]
    w, h, lo, hi = 760, 300, 0, 4.5
    band = v.get("band", [1.5, 2.5])
    y = lambda t: h - (t - lo) / (hi - lo) * h  # noqa: E731
    dots = "".join(f'<circle cx="{i * w / (len(pts) - 1):.0f}" cy="{y(t):.0f}" r="12" fill="{T["ink"] if band[0] <= t <= band[1] else T["accent"]}"/>' for i, t in enumerate(pts))
    labels = "".join(f'<div style="position:absolute;left:-104px;top:{y(t) - 14:.0f}px;font-size:20px;color:{T["ink2"]}">{lab}</div>' for t, lab in ((0, "21:00"), (2, "23:00"), (4, "01:00")))
    return f'''<div class="col" style="gap:20px">{label(v.get("title", ""))}<div style="position:relative;margin-left:104px;width:{w}px;height:{h}px">{labels}
      <svg width="{w}" height="{h}" style="overflow:visible"><rect x="-20" y="{y(band[1]):.0f}" width="{w + 40}" height="{y(band[0]) - y(band[1]):.0f}" fill="{T["soft"]}"/>{dots}</svg></div>
      <div style="font-size:22px;color:{T["ink2"]}">{esc(v.get("note", ""))}</div></div>'''


def v_steps(v: dict) -> str:
    rows = "".join(f'''<div class="row" style="align-items:center;gap:24px;padding:20px 0;border-top:1.5px solid {T["line"]}">
        <div style="width:14px;height:14px;border-radius:50%;background:{T["accent"] if s.get("hot") else T["ink2"]}"></div>
        <div class="col" style="flex:1;gap:2px"><div style="font-size:31px;font-weight:600">{esc(s["name"])}</div><div style="font-size:22px;color:{T["ink2"]}">{esc(s.get("detail", ""))}</div></div>
        <div class="serif" style="font-size:40px;white-space:nowrap">{esc(s["pace"])}</div></div>''' for s in v["steps"])
    return f'<div class="col" style="gap:14px">{label(v.get("kicker", ""), T["accent"])}<div class="serif" style="font-size:44px">{esc(v.get("title", ""))}</div><div class="col" style="margin-top:8px">{rows}<div style="border-top:1.5px solid {T["line"]}"></div></div></div>'


VISUALS = {"zones": v_zones, "readiness": v_readiness, "rows": v_rows, "metric": v_metric, "ring": v_ring, "curve": v_curve,
           "chat": v_chat, "schedule": v_schedule, "steps": v_steps}


# ---------------------------------------------------------------- maqueta
def frame_top(post: dict, k: int, s: dict) -> str:
    topic = s.get("topic") or post.get("topic") or ""
    return f'''<div class="row" style="justify-content:space-between;align-items:center">
      <div class="serif" style="font-size:34px;font-weight:600;letter-spacing:-.01em">Runch</div>
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
        def side(x: dict, good: bool) -> str:
            lines = "".join(f'<div style="font-size:27px;line-height:1.4;color:{T["ink2"]}">{rich(t)}</div>' for t in x.get("lines", []))
            return f'''<div class="col" style="flex:1;gap:16px">{label(x["label"], T["accent"] if good else T["ink2"])}
              <div class="serif" style="font-size:130px;line-height:.9;letter-spacing:-.04em;{f'color:{T["accent"]}' if good else ''}">{esc(x["value"])}</div>
              <div style="font-size:22px;color:{T["ink2"]};margin-top:-6px">{esc(x.get("unit", ""))}</div><div class="col" style="gap:6px;margin-top:10px">{lines}</div></div>'''
        body = f'''<div style="flex:.5"></div>{kick}{title(s.get("size", 80), "margin-top:16px")}<div style="flex:1"></div>
          <div class="row" style="gap:48px;align-items:stretch;padding:40px 0;border-top:1.5px solid {T["line"]};border-bottom:1.5px solid {T["line"]}">
            {side(s["left"], False)}<div class="serif" style="align-self:center;font-size:56px;font-style:italic;color:{T["ink2"]}">vs</div>{side(s["right"], True)}</div>
          {lead("margin-top:30px")}<div style="flex:.6"></div>'''
    elif layout == "big":
        body = f'''<div style="flex:1"></div>{kick}
          <div class="serif" style="font-size:{s.get("bigSize", 380)}px;line-height:.82;letter-spacing:-.05em;color:{T["accent"]};margin-top:10px">{esc(s["big"])}</div>
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


# ---------------------------------------------------------------- salida
def main(path: str) -> None:
    from playwright.sync_api import sync_playwright
    lote = json.loads(Path(path).read_text())
    STYLE["handle"] = lote.get("handle")
    out = HERE / "out" / f"lote-{lote['lote']}"
    out.mkdir(parents=True, exist_ok=True)
    for f in out.glob("*.png"):
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
                files.append(name)
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
        imgs = "".join(f'<a href="{k:02d}-{post["id"]}-{i}.png" target="_blank"><img src="{k:02d}-{post["id"]}-{i}.png"></a>' for i in range(1, n + 1))
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
      .num {{ font-family: FR, serif; font-style: italic; color: #D4542F; font-size: 24px; }} .meta {{ margin-left: auto; color: #76695F; font-size: 14px; }}
      .imgs {{ display: flex; gap: 12px; overflow-x: auto; }} .imgs img {{ height: min(52vh, 460px); aspect-ratio: 4/5; border-radius: 6px; display: block; }}
      summary {{ cursor: pointer; color: #D4542F; font-weight: 600; margin-top: 12px; }} details p {{ max-width: 760px; line-height: 1.5; }}
      .tags {{ color: #D4542F; }} .alt {{ color: #76695F; font-size: 14px; }}
    </style></head><body><header><h1>Runch · lote {lote["lote"]}</h1><p>{esc(lote.get("notes", ""))}</p></header>{"".join(rows)}</body></html>''', encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else str(HERE / "lote-01.json"))
