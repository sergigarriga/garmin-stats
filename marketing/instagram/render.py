"""Genera los posts de Instagram (1080 x 1350, 4:5) con el estilo de la app "Mi salud".

Uso:
  uv run --no-project --with playwright python marketing/instagram/render.py marketing/instagram/lote-01.json

Lee un lote (JSON con posts y diapositivas), pinta cada diapositiva en HTML con la letra y los colores de la app y la
guarda como PNG en marketing/instagram/out/<lote>/. También escribe captions.md (texto, hashtags y texto
alternativo de cada post) y grid.png (cómo quedará la cuadrícula del perfil).

Formato del lote: ver README.md de esta carpeta.
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

# Paleta pastel "aesthetic": fondo pastel por tema, color de acento con contraste para datos y textos destacados,
# y dos pasteles complementarios para las manchas difuminadas del fondo.
PASTEL = {
    "energy":   {"bg": "#DCEAFF", "accent": "#2F6FE4", "blobs": ["#FFD6E5", "#FFF0B8"]},
    "activity": {"bg": "#D6F2E1", "accent": "#1E8E4E", "blobs": ["#FFF0B8", "#D3E6FF"]},
    "sleep":    {"bg": "#E5DFFF", "accent": "#5B4BD6", "blobs": ["#FFD8EA", "#CFEFFF"]},
    "stress":   {"bg": "#FFF0C2", "accent": "#B86A00", "blobs": ["#FFD7C7", "#E5DFFF"]},
    "recovery": {"bg": "#D0F0EC", "accent": "#00807A", "blobs": ["#E5DFFF", "#FFF0B8"]},
    "training": {"bg": "#FFE1CE", "accent": "#DE6418", "blobs": ["#FFF0B8", "#FFD6E5"]},
    "gym":      {"bg": "#EEDDFF", "accent": "#8A3FD6", "blobs": ["#FFD6E5", "#CFEFFF"]},
    "heart":    {"bg": "#FFDBE4", "accent": "#D23A5C", "blobs": ["#FFE8C4", "#E5DFFF"]},
    "neutral":  {"bg": "#ECEEF2", "accent": "#5F6368", "blobs": ["#DCEAFF", "#FFD6E5"]},
}
# Colores de datos (gráficos, iconos) dentro de las tarjetas blancas
C_LIGHT = {k: v["accent"] for k, v in PASTEL.items()}
ZONES = ["#A6AEBB", "#5B8DEF", "#3FB37F", "#F29A4A", "#EB5E6F"]
INK, INK2 = "#1D1B2C", "#5E5B70"
LIGHT = {"TEXT": INK, "TEXT2": INK2, "BG": "#FFFFFF", "CARD": "#FFFFFF", "LINE": "#EFEDF3", "CHIP": "#F1EFF7", "OUTLINE": "#DDDAE6"}
YELLOW = "#FFE58A"

C: dict = {}
TEXT = TEXT2 = BG = CARD = LINE = CHIP = OUTLINE = ""
DARKMODE = False


def set_theme(dark: bool = False) -> None:
    """Un solo tema (pastel claro). Los visuales leen estas variables al pintarse."""
    global TEXT, TEXT2, BG, CARD, LINE, CHIP, OUTLINE
    t = LIGHT
    TEXT, TEXT2, BG, CARD, LINE, CHIP, OUTLINE = (t[k] for k in ("TEXT", "TEXT2", "BG", "CARD", "LINE", "CHIP", "OUTLINE"))
    C.clear()
    C.update(C_LIGHT)


set_theme()


def pal(key: str | None) -> dict:
    return PASTEL.get(key or "energy", PASTEL["energy"])


def esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


def rich(s) -> str:
    """**negrita** → <b>."""
    parts = esc(s).split("**")
    return "".join(f"<b>{p}</b>" if i % 2 else p for i, p in enumerate(parts))


def col(name: str | None, default: str = "energy") -> str:
    if name and name.startswith("#"):
        return name
    return C.get(name or default, C[default])


def mix(hex_color: str, pct: float, base: str | None = None) -> str:
    """Mezcla un color con el fondo (pct = 0..1 de color)."""
    base = base or BG
    a = [int(hex_color[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(base[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x * pct + y * (1 - pct)):02X}" for x, y in zip(a, b))


def on() -> str:
    """Texto encima de un color de la paleta: blanco sobre los tonos vivos (claro), oscuro sobre los pastel (oscuro)."""
    return BG if DARKMODE else "#FFFFFF"


def icon(name: str, color: str = "currentColor", size: int = 40) -> str:
    paths = "".join(f'<path d="{d}"/>' for d in ICONS.get(name, ICONS["AutoAwesome"]))
    return f'<svg viewBox="0 0 24 24" width="{size}" height="{size}" fill="{color}">{paths}</svg>'


def bubble(name: str, color: str, size: int = 72) -> str:
    return (f'<div class="bubble" style="width:{size}px;height:{size}px;background:{mix(color, .16, CARD)};color:{color}">'
            f'{icon(name, color, round(size * .55))}</div>')


def gauge(value: float, mx: float, color: str, size: int, stroke: int, center: str = "", sub: str = "", big: int = 64) -> str:
    r = (size - stroke) / 2
    circ = 2 * math.pi * r
    frac = max(0, min(1, value / mx if mx else 0))
    return f'''<div class="gauge" style="width:{size}px;height:{size}px">
      <svg width="{size}" height="{size}" style="transform:rotate(-90deg)">
        <circle cx="{size/2}" cy="{size/2}" r="{r}" fill="none" stroke="{mix(color, .30 if DARKMODE else .18, CARD)}" stroke-width="{stroke}"/>
        <circle cx="{size/2}" cy="{size/2}" r="{r}" fill="none" stroke="{color}" stroke-width="{stroke}" stroke-linecap="round"
          stroke-dasharray="{circ * frac} {circ}"/>
      </svg>
      <div class="gc"><div style="font-size:{big}px;font-weight:600;letter-spacing:-.03em;line-height:1">{esc(center)}</div>
        {f'<div style="font-size:{round(big*.36)}px;color:{TEXT2};margin-top:6px">{esc(sub)}</div>' if sub else ''}</div>
    </div>'''


def spark(points: list, color: str, w: int, h: int, band: list | None = None, fill: bool = True) -> str:
    lo, hi = min(points), max(points)
    if band:
        lo, hi = min(lo, band[0]), max(hi, band[1])
    pad = (hi - lo) * .15 or 1
    lo, hi = lo - pad, hi + pad
    xy = [(i * w / (len(points) - 1), h - (v - lo) / (hi - lo) * h) for i, v in enumerate(points)]
    d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in xy)
    out = f'<svg width="{w}" height="{h}" style="overflow:visible">'
    if band:
        y1, y2 = h - (band[1] - lo) / (hi - lo) * h, h - (band[0] - lo) / (hi - lo) * h
        out += f'<rect x="0" y="{y1:.1f}" width="{w}" height="{y2 - y1:.1f}" rx="10" fill="{mix(color, .14, CARD)}"/>'
    if fill:
        out += f'<path d="{d} L{w},{h} L0,{h} Z" fill="{color}" opacity=".10"/>'
    out += f'<path d="{d}" fill="none" stroke="{color}" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>'
    x, y = xy[-1]
    out += f'<circle cx="{x:.1f}" cy="{y:.1f}" r="10" fill="{color}" stroke="{CARD}" stroke-width="4"/></svg>'
    return out


# ---------------------------------------------------------------- visuales (dentro de una tarjeta)
def v_rings(v: dict) -> str:
    items = "".join(f'''<div class="col center" style="gap:14px">
        <div style="font-size:26px;color:{TEXT2};font-weight:500">{esc(it["label"])}</div>
        {gauge(it["value"], it.get("max", 100), col(it.get("color")), 250, 22, it["center"], it.get("sub", ""), 54)}
      </div>''' for it in v["items"])
    return f'<div class="row" style="justify-content:space-around">{items}</div>'


def v_ring(v: dict) -> str:
    c = col(v.get("color"))
    side = "".join(f'''<div><div style="font-size:24px;color:{TEXT2}">{esc(s["label"])}</div>
        <div style="font-size:42px;font-weight:600;letter-spacing:-.02em">{esc(s["value"])}</div></div>''' for s in v.get("side", []))
    return f'''<div class="row" style="gap:56px;align-items:center;justify-content:center">
      {gauge(v["value"], v.get("max", 100), c, 380, 30, v["center"], v.get("sub", ""), 108)}
      <div class="col" style="gap:26px">{side}</div></div>'''


def v_metric(v: dict) -> str:
    c = col(v.get("color"))
    cap = col(v["captionColor"]) if v.get("captionColor") else c
    return f'''<div class="col" style="gap:18px">
      <div class="row" style="gap:18px;align-items:center">{bubble(v.get("icon", "MonitorHeart"), c, 64)}
        <div style="font-size:30px;color:{TEXT2};font-weight:500">{esc(v["label"])}</div></div>
      <div style="font-size:120px;font-weight:600;letter-spacing:-.04em;line-height:1">{esc(v["value"])}
        <span style="font-size:40px;color:{TEXT2};font-weight:400;letter-spacing:0">{esc(v.get("unit", ""))}</span></div>
      <div style="font-size:30px;color:{cap};font-weight:600">{esc(v.get("caption", ""))}</div>
      <div style="margin-top:14px">{spark(v["points"], c, 820, 190, v.get("band"))}</div>
      {f'<div style="font-size:22px;color:{TEXT2}">{esc(v["note"])}</div>' if v.get("note") else ""}
    </div>'''


def v_readiness(v: dict) -> str:
    c = col(v.get("color"), "activity")
    parts = "".join(f'''<div class="col" style="gap:10px">
        <div class="row" style="justify-content:space-between;font-size:28px"><span style="font-weight:600">{esc(p["label"])}
          <span style="color:{TEXT2};font-weight:400"> · {esc(p["weight"])}</span></span><span style="font-weight:600">{p["score"]}</span></div>
        <div class="track" style="background:{mix(c, .16, CARD)}"><div style="width:{p["score"]}%;background:{c}"></div></div></div>''' for p in v["parts"])
    return f'''<div class="row" style="gap:52px;align-items:center">
      {gauge(v["score"], 100, c, 300, 26, str(v["score"]), "de 100", 96)}
      <div class="col" style="gap:24px;flex:1"><div style="font-size:52px;font-weight:600;color:{c};line-height:1">{esc(v["label"])}</div>{parts}</div></div>'''


def v_rows(v: dict) -> str:
    """Filas tipo lista: etiqueta + detalle + valor a la derecha (ritmos, récords)."""
    c = col(v.get("color"), "training")
    rows = "".join(f'''<div class="row" style="justify-content:space-between;align-items:center;padding:20px 0;{('border-top:2px solid ' + LINE) if i else ''}">
        <div class="col" style="gap:4px"><div style="font-size:34px;font-weight:600">{esc(r["label"])}</div>
          {f'<div style="font-size:24px;color:{TEXT2}">{esc(r["detail"])}</div>' if r.get("detail") else ''}</div>
        <div style="font-size:42px;font-weight:650;letter-spacing:-.02em;white-space:nowrap;color:{col(r["color"]) if r.get("color") else TEXT}">{esc(r["value"])}
          <span style="font-size:24px;color:{TEXT2};font-weight:400">{esc(r.get("unit", v.get("unit", "")))}</span></div></div>'''
                   for i, r in enumerate(v["rows"]))
    title = f'<div style="font-size:28px;color:{c};font-weight:600;margin-bottom:6px">{esc(v["title"])}</div>' if v.get("title") else ""
    return f'<div class="col">{title}{rows}</div>'


def v_zones(v: dict) -> str:
    hi = v.get("highlight")

    def row(z: dict) -> str:
        zc, on_ = ZONES[z["zone"] - 1], z["zone"] == hi
        style = f"background:{mix(zc, .30 if on_ else .12, CARD)};" + (f"outline:4px solid {zc};" if on_ else "") + ("opacity:.5;" if hi and not on_ else "")
        return f'''<div class="row" style="align-items:center;gap:22px;padding:16px 22px;border-radius:24px;{style}">
          <div style="width:58px;height:58px;border-radius:50%;background:{zc};color:#fff;display:grid;place-items:center;font-weight:700;font-size:24px">Z{z["zone"]}</div>
          <div style="flex:1;font-size:32px;font-weight:{650 if on_ else 400}">{esc(z["name"])}</div>
          <div style="font-size:34px;font-weight:650">{esc(z["range"])} <span style="font-size:24px;color:{TEXT2};font-weight:400">{esc(v.get("unit", ""))}</span></div></div>'''
    return f'<div class="col" style="gap:14px">{"".join(row(z) for z in v["rows"])}</div>'


def v_chat(v: dict) -> str:
    out = []
    for m in v["messages"]:
        me = m["from"] == "user"
        out.append(f'''<div class="row" style="justify-content:{'flex-end' if me else 'flex-start'};gap:16px;align-items:flex-end">
          {'' if me else bubble("AutoAwesome", C["energy"], 60)}
          <div style="max-width:700px;padding:24px 30px;border-radius:{'36px 36px 10px 36px' if me else '36px 36px 36px 10px'};font-size:30px;line-height:1.35;
            background:{C['energy'] if me else CHIP};color:{on() if me else TEXT}">{rich(m["text"])}</div></div>''')
    return f'<div class="col" style="gap:22px">{"".join(out)}</div>'


def v_bars(v: dict) -> str:
    c = col(v.get("color"))
    mx = max(v["values"]) or 1
    hi = set(v.get("highlight", []))
    bars = "".join(f'''<div class="col center" style="gap:12px;flex:1">
        <div style="font-size:22px;color:{TEXT2};height:28px">{esc(v.get("tops", [""] * len(v["values"]))[i])}</div>
        <div style="width:62%;height:{max(6, val / mx * 330):.0f}px;border-radius:14px;background:{c if (not hi or i in hi) else mix(c, .35, CARD)}"></div>
        <div style="font-size:24px;color:{TEXT2}">{esc(lab)}</div></div>''' for i, (lab, val) in enumerate(zip(v["labels"], v["values"])))
    title = f'<div style="font-size:28px;color:{TEXT2};font-weight:500;margin-bottom:12px">{esc(v["title"])}</div>' if v.get("title") else ""
    return f'<div class="col">{title}<div class="row" style="align-items:flex-end;height:420px">{bars}</div></div>'


def v_curve(v: dict) -> str:
    """Curva del día (Body Battery): puntos [hora, valor]."""
    c = col(v.get("color"))
    pts = v["points"]
    w, h = 770, 320
    xy = [((p[0] / 24) * w, h - p[1] / 100 * h) for p in pts]
    d = "M" + " L".join(f"{x:.0f},{y:.0f}" for x, y in xy)
    dots = "".join(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="9" fill="{CARD}" stroke="{c}" stroke-width="5"/>' for x, y in xy)
    grid = "".join(f'<line x1="0" x2="{w}" y1="{h - g / 100 * h}" y2="{h - g / 100 * h}" stroke="{OUTLINE}" stroke-dasharray="6 8" stroke-width="2"/>'
                   for g in (0, 50, 100))

    def tick(t):  # los extremos se alinean hacia dentro para no salirse de la tarjeta
        left = 0 if t == 0 else w - 70 if t == 24 else t / 24 * w - 35
        align = "left" if t == 0 else "right" if t == 24 else "center"
        return f'<div style="position:absolute;left:{left:.0f}px;width:70px;text-align:{align}">{t:02d}:00</div>'
    ticks = "".join(tick(t) for t in (0, 6, 12, 18, 24))
    x, y = xy[-1]
    tag = (f'<div style="position:absolute;left:{x - 60:.0f}px;top:{y - 82:.0f}px;padding:6px 16px;border-radius:999px;background:{c};color:{on()};'
           f'font-weight:600;font-size:26px;white-space:nowrap">{esc(v.get("tag", ""))}</div>') if v.get("tag") else ""
    return f'''<div class="col" style="gap:14px"><div style="font-size:28px;color:{TEXT2};font-weight:500">{esc(v.get("title", ""))}</div>
      <div style="position:relative;width:{w}px;height:{h}px">{tag}<svg width="{w}" height="{h}" style="overflow:visible">{grid}
        <path d="{d} L{x:.0f},{h} L0,{h} Z" fill="{c}" opacity=".12"/><path d="{d}" fill="none" stroke="{c}" stroke-width="6" stroke-linejoin="round"/>{dots}</svg></div>
      <div style="position:relative;height:30px;font-size:22px;color:{TEXT2}">{ticks}</div></div>'''


def v_mood(v: dict) -> str:
    faces = ["SentimentVeryDissatisfied", "SentimentDissatisfied", "SentimentNeutral", "SentimentSatisfied", "SentimentVerySatisfied"]
    names = ["Muy mal", "Mal", "Normal", "Bien", "Genial"]
    sel = v.get("mood", 4)
    c = C["energy"]
    moods = "".join(f'''<div class="col center" style="gap:8px;padding:14px 10px;border-radius:999px;width:150px;
        border:2px solid {c if i + 1 == sel else OUTLINE};background:{mix(c, .16, CARD) if i + 1 == sel else CARD};color:{c if i + 1 == sel else TEXT2}">
        {icon(f, c if i + 1 == sel else TEXT2, 52)}<div style="font-size:22px;font-weight:{600 if i + 1 == sel else 500}">{n}</div></div>''' for i, (f, n) in enumerate(zip(faces, names)))
    sore = "".join(f'''<div style="padding:12px 26px;border-radius:999px;font-size:26px;border:2px solid {c if i + 1 == v.get("soreness", 2) else OUTLINE};
        background:{mix(c, .16, CARD) if i + 1 == v.get("soreness", 2) else CARD};color:{c if i + 1 == v.get("soreness", 2) else TEXT2}">{n}</div>'''
                   for i, n in enumerate(["Nada", "Leves", "Moderadas", "Fuertes"]))
    chips = "".join(f'<div style="padding:12px 24px;border-radius:999px;background:{col(ch.get("color"), "stress")};color:{on()};font-size:26px;font-weight:600">{esc(ch["text"])}</div>'
                    for ch in v.get("injuries", []))
    return f'''<div class="col" style="gap:22px">
      <div class="row" style="gap:18px;align-items:center">{bubble("Healing", C["recovery"], 64)}<div style="font-size:34px;font-weight:600">¿Cómo te encuentras hoy?</div></div>
      <div style="font-size:26px;color:{TEXT2}">Ánimo</div><div class="row" style="gap:12px">{moods}</div>
      <div style="font-size:26px;color:{TEXT2}">Agujetas</div><div class="row" style="gap:12px;flex-wrap:wrap">{sore}</div>
      {f'<div style="font-size:26px;color:{TEXT2}">Molestias</div><div class="row" style="gap:12px">{chips}</div>' if chips else ''}</div>'''


def v_schedule(v: dict) -> str:
    """Hora de acostarse de cada noche (puntos) con la franja recomendada."""
    c = col(v.get("color"), "sleep")
    pts = v["points"]  # horas desde las 21:00 (0 = 21:00, 4 = 01:00)
    w, h = 700, 300
    lo, hi = 0, 4.5
    band = v.get("band", [1.5, 2.5])
    y = lambda t: h - (t - lo) / (hi - lo) * h  # noqa: E731
    dots = "".join(f'<circle cx="{i * w / (len(pts) - 1):.0f}" cy="{y(t):.0f}" r="13" fill="{c if band[0] <= t <= band[1] else mix(c, .4, CARD)}"/>'
                   for i, t in enumerate(pts))
    labels = "".join(f'<div style="position:absolute;right:{w + 16}px;top:{y(t) - 16:.0f}px;font-size:22px;color:{TEXT2}">{lab}</div>'
                     for t, lab in ((0, "21:00"), (2, "23:00"), (4, "01:00")))
    return f'''<div class="col" style="gap:16px"><div style="font-size:28px;color:{TEXT2};font-weight:500">{esc(v.get("title", ""))}</div>
      <div style="position:relative;width:{w}px;height:{h}px;margin-left:96px">{labels}<svg width="{w}" height="{h}" style="overflow:visible">
        <rect x="-24" y="{y(band[1]):.0f}" width="{w + 48}" height="{y(band[0]) - y(band[1]):.0f}" rx="18" fill="{mix(c, .14, CARD)}"/>{dots}</svg></div>
      <div style="font-size:24px;color:{TEXT2}">{esc(v.get("note", ""))}</div></div>'''


def v_steps(v: dict) -> str:
    """Pasos de un entreno con ritmos (como en el plan)."""
    c = col(v.get("color"), "training")
    rows = "".join(f'''<div class="row" style="gap:20px;align-items:center;padding:18px 0;{('border-top:2px solid ' + LINE) if i else ''}">
        <div style="width:10px;align-self:stretch;border-radius:9px;background:{col(s.get("color"), "training")}"></div>
        <div class="col" style="flex:1;gap:4px"><div style="font-size:32px;font-weight:600">{esc(s["name"])}</div>
          <div style="font-size:24px;color:{TEXT2}">{esc(s.get("detail", ""))}</div></div>
        <div style="font-size:34px;font-weight:650;white-space:nowrap">{esc(s["pace"])}</div></div>''' for i, s in enumerate(v["steps"]))
    head = f'''<div class="row" style="gap:16px;align-items:center;margin-bottom:8px">{bubble(v.get("icon", "DirectionsRun"), c, 60)}
      <div class="col"><div style="font-size:24px;color:{TEXT2}">{esc(v.get("kicker", ""))}</div><div style="font-size:36px;font-weight:650">{esc(v.get("title", ""))}</div></div></div>'''
    return f'<div class="col">{head}{rows}</div>'


VISUALS = {"rings": v_rings, "ring": v_ring, "metric": v_metric, "readiness": v_readiness, "rows": v_rows, "zones": v_zones,
           "chat": v_chat, "bars": v_bars, "curve": v_curve, "mood": v_mood, "schedule": v_schedule, "steps": v_steps}


# ---------------------------------------------------------------- piezas comunes
LOGO = "conic-gradient(from 200deg,#F28B82,#FCAD70,#FDD663,#81C995,#8AB4F8,#AFADFF,#F28B82)"


def brand() -> str:
    """Marca en una cápsula blanca centrada arriba."""
    return f'''<div class="row" style="justify-content:center"><div class="row" style="gap:12px;align-items:center;padding:10px 24px 10px 10px;
      border-radius:999px;background:rgba(255,255,255,.72);box-shadow:0 4px 18px rgba(60,50,90,.08)">
      <div style="width:44px;height:44px;border-radius:50%;background:{LOGO};display:grid;place-items:center">
        <div style="width:30px;height:30px;border-radius:50%;background:#fff;display:grid;place-items:center">{icon("Favorite", "#E8607A", 17)}</div></div>
      <div style="font-size:27px;font-weight:650;color:{INK};letter-spacing:-.01em">Mi salud</div></div></div>'''


def dots(i: int, n: int, accent: str) -> str:
    if n < 2:
        return ""
    d = "".join(f'<div style="height:12px;width:{38 if k == i else 12}px;border-radius:9px;background:{accent if k == i else "rgba(29,27,44,.18)"}"></div>'
                for k in range(1, n + 1))
    return f'<div class="row" style="gap:10px;justify-content:center">{d}</div>'


def chip(text: str, bg: str, fg: str = INK, rot: float = 0, size: int = 30, icon_name: str | None = None, shadow: bool = True) -> str:
    ic = icon(icon_name, fg, round(size * 1.1)) if icon_name else ""
    return (f'<div class="row free" style="gap:10px;align-items:center;padding:14px 28px;border-radius:999px;background:{bg};color:{fg};'
            f'font-size:{size}px;font-weight:700;transform:rotate({rot}deg);white-space:nowrap;'
            f'{"box-shadow:0 10px 26px rgba(60,50,90,.13);" if shadow else ""}">{ic}{esc(text)}</div>')


def kicker(s: dict, accent: str) -> str:
    if not s.get("kicker"):
        return ""
    return f'<div class="row" style="justify-content:center">{chip(s["kicker"], "#FFFFFF", accent, -2.5, 27, s.get("icon"))}</div>'


def blobs(p: dict, seed: int) -> str:
    """Manchas pastel difuminadas en el fondo (cambian de sitio en cada diapositiva)."""
    spots = [[(-160, -120, 620), (680, 860, 680)], [(640, -180, 640), (-220, 760, 700)], [(-120, 520, 560), (700, 140, 520)]][seed % 3]
    return "".join(f'<div class="deco" style="position:absolute;left:{x}px;top:{y}px;width:{r}px;height:{r}px;border-radius:50%;'
                   f'background:{c};filter:blur(70px);opacity:.9"></div>' for (x, y, r), c in zip(spots, p["blobs"]))


def card(inner: str, tilt: float = 0, tag: str | None = None, tag_bg: str = YELLOW, extra: str = "") -> str:
    t = (f'<div class="free" style="position:absolute;top:-30px;right:34px;z-index:2">{chip(tag, tag_bg, INK, 5, 28)}</div>') if tag else ""
    return f'<div style="position:relative;transform:rotate({tilt}deg)">{t}<div class="card" style="{extra}">{inner}</div></div>'


# ---------------------------------------------------------------- diapositivas
def slide_html(post: dict, s: dict, i: int, n: int, k: int = 0) -> str:
    set_theme()
    key = s.get("color") or post.get("color") or "energy"
    p = pal(key)
    accent = p["accent"]
    hl = mix(accent, .28, "#FFFFFF")  # subrayador de la palabra clave
    layout = s.get("layout", "cover")
    bg = p["bg"]
    example = s.get("example", ("visual" in s or layout == "versus") and layout not in ("cta", "hook"))
    title = lambda size, extra="": f'<div class="title" style="font-size:{size}px;{extra}">{rich(s["title"])}</div>'  # noqa: E731
    lead = lambda extra="": f'<div class="lead" style="{extra}">{rich(s["body"])}</div>' if s.get("body") else ""  # noqa: E731

    if layout == "hook":
        floats = s.get("floats") or []
        cloud = "".join(chip(t, ["#FFFFFF", YELLOW, mix(accent, .22, "#FFFFFF")][j % 3], INK, [-5, 4, -2, 6][j % 4], 28) for j, t in enumerate(floats))
        st = f'<div class="row" style="justify-content:center">{chip(s["sticker"], YELLOW, INK, -5, 34)}</div>' if s.get("sticker") else ""
        swipe = (f'<div class="row" style="justify-content:flex-end">{chip("Desliza", "#FFFFFF", INK, 0, 26, None)}</div>'
                 if s.get("swipe", n > 1 and i == 1) else "")
        body = f'''<div style="flex:1"></div>{st}{title(s.get("size", 112), "text-align:center;margin-top:16px")}
          {lead("text-align:center;align-self:center;font-size:38px")}
          {f'<div class="row" style="gap:18px;justify-content:center;flex-wrap:wrap;margin-top:22px">{cloud}</div>' if cloud else ''}
          <div style="flex:1.1"></div>{swipe}'''
    elif layout == "cover":
        vis = s.get("visual")
        body = f'''{kicker(s, accent)}{title(s.get("size", 86), "text-align:center")}{lead("text-align:center;align-self:center")}
          <div style="flex:1"></div>
          {card(VISUALS[vis["type"]](vis), s.get("tilt", [-2, 2, -1.5][k % 3]), s.get("tag")) if vis else ''}<div style="flex:.25"></div>'''
    elif layout == "points":
        pts = s["points"]
        tiles = []
        for j, q in enumerate(pts):
            qp = pal(q.get("color") or key)
            wide = len(pts) == 3 and j == 0
            tiles.append(f'''<div class="col" style="grid-column:{'1 / -1' if wide else 'auto'};gap:14px;padding:36px 34px 38px;border-radius:42px;
                background:{mix(qp["bg"], .85, "#FFFFFF")};box-shadow:0 10px 30px rgba(60,50,90,.07);transform:rotate({[-1, 1, 1, -1][j % 4] * (0 if wide else 1)}deg)">
              <div style="width:76px;height:76px;border-radius:24px;background:#fff;display:grid;place-items:center">{icon(q.get("icon", "CheckCircle"), qp["accent"], 42)}</div>
              <div style="font-size:{40 if wide else 35}px;font-weight:700;letter-spacing:-.02em;line-height:1.12">{rich(q["title"])}</div>
              <div style="font-size:{30 if wide else 28}px;line-height:1.36;color:{INK2}">{rich(q["body"])}</div></div>''')
        body = f'''<div style="flex:1"></div>{kicker(s, accent)}{title(s.get("size", 80), "text-align:center")}
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:24px;margin-top:24px">{"".join(tiles)}</div><div style="flex:1.2"></div>'''
    elif layout == "versus":
        def side(x: dict, rot: float) -> str:
            good = x.get("tone") == "good"
            kp = pal("activity" if good else "heart")
            lines = "".join(f'<div style="font-size:26px;line-height:1.35;color:{INK2}">{rich(t)}</div>' for t in x.get("lines", []))
            return f'''<div class="card col" style="flex:1;gap:14px;padding:34px 32px;transform:rotate({rot}deg);background:{mix(kp["bg"], .55, "#FFFFFF")}">
              <div class="row" style="gap:10px;align-items:center;color:{kp["accent"]};font-size:24px;font-weight:750;letter-spacing:.03em">
                {icon("CheckCircle" if good else "Cancel", kp["accent"], 32)}{esc(x["label"]).upper()}</div>
              <div style="font-size:{x.get("size", 74)}px;font-weight:700;letter-spacing:-.035em;line-height:1">{esc(x["value"])}
                <span style="font-size:26px;color:{INK2};font-weight:500;letter-spacing:0">{esc(x.get("unit", ""))}</span></div>
              <div class="col" style="gap:8px">{lines}</div></div>'''
        vs = (f'<div class="free" style="position:absolute;left:50%;top:50%;transform:translate(-50%,-50%) rotate(-8deg);width:96px;height:96px;'
              f'border-radius:50%;background:{YELLOW};display:grid;place-items:center;font-size:34px;font-weight:800;color:{INK};'
              f'box-shadow:0 10px 26px rgba(60,50,90,.18);z-index:2">VS</div>')
        body = f'''{kicker(s, accent)}{title(s.get("size", 76), "text-align:center")}<div style="flex:1"></div>
          <div class="row" style="position:relative;gap:30px;align-items:stretch">{side(s["left"], -2.5)}{side(s["right"], 2.5)}{vs}</div>
          {lead("text-align:center;align-self:center;margin-top:14px")}<div style="flex:.7"></div>'''
    elif layout == "big":
        body = f'''{kicker(s, accent)}<div style="flex:1"></div>
          <div style="position:relative;display:grid;place-items:center;height:{s.get("bigSize", 300) + 60}px">
            <div class="deco" style="position:absolute;width:{s.get("bigSize", 300) + 200}px;height:{s.get("bigSize", 300) + 200}px;border-radius:50%;background:rgba(255,255,255,.6)"></div>
            <div style="position:relative;font-size:{s.get("bigSize", 300)}px;font-weight:750;letter-spacing:-.05em;line-height:1;color:{accent}">{esc(s["big"])}</div></div>
          {title(s.get("size", 68), "text-align:center;margin-top:34px")}{lead("text-align:center;align-self:center")}<div style="flex:1.2"></div>'''
    elif layout == "cta":
        acts = "".join(chip(a["text"], ["#FFFFFF", YELLOW][j % 2], INK, [-3, 3][j % 2], 30, a.get("icon")) for j, a in enumerate(s.get("actions", [])))
        body = f'''<div style="flex:1"></div>
          <div style="width:180px;height:180px;border-radius:56px;margin:0 auto;display:grid;place-items:center;transform:rotate(-6deg);
            background:{LOGO};box-shadow:0 24px 60px rgba(60,50,90,.18)">{icon(s.get("icon", "AutoAwesome"), "#fff", 92)}</div>
          {title(s.get("size", 84), "text-align:center;margin-top:56px")}{lead("text-align:center;align-self:center")}
          <div class="row" style="gap:22px;justify-content:center;margin-top:50px;flex-wrap:wrap">{acts}</div><div style="flex:1.2"></div>'''
    else:
        raise ValueError(f"layout desconocido: {layout}")
    foot = f'''<div class="row" style="justify-content:space-between;align-items:center;min-height:24px">
      <div style="font-size:19px;color:rgba(29,27,44,.45);width:200px">{"Datos de ejemplo" if example else ""}</div>{dots(i, n, accent)}<div style="width:200px"></div></div>'''
    fonts = HERE / "fonts"
    return f'''<!doctype html><html lang="es"><head><meta charset="utf-8"><style>
      @font-face {{ font-family: GSF; font-weight: 1 1000; src: url("file://{fonts}/google-sans-flex-latin-wght-normal.woff2") format("woff2-variations");
        unicode-range: U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212; }}
      @font-face {{ font-family: GSF; font-weight: 1 1000; src: url("file://{fonts}/google-sans-flex-latin-ext-wght-normal.woff2") format("woff2-variations");
        unicode-range: U+0100-02BA, U+1E00-1EFF, U+2C60-2C7F, U+A720-A7FF; }}
      * {{ box-sizing: border-box; margin: 0; }}
      body {{ width: {W}px; height: {H}px; font-family: GSF, system-ui, sans-serif; color: {INK}; -webkit-font-smoothing: antialiased; }}
      .slide {{ position: relative; width: {W}px; height: {H}px; background: {bg}; overflow: hidden; }}
      .content {{ position: relative; height: 100%; padding: 56px 72px 46px; display: flex; flex-direction: column; gap: 28px; }}
      .row {{ display: flex; }} .col {{ display: flex; flex-direction: column; }} .center {{ align-items: center; }}
      .title {{ font-weight: 700; letter-spacing: -.04em; line-height: 1.04; text-wrap: balance; color: {INK}; }}
      .title b {{ font-weight: 750; color: {INK}; background: linear-gradient(transparent 56%, {hl} 56%, {hl} 90%, transparent 90%);
        -webkit-box-decoration-break: clone; box-decoration-break: clone; padding: 0 .06em; }}
      .lead {{ font-size: 34px; line-height: 1.38; color: {INK2}; text-wrap: pretty; max-width: 880px; }}
      .lead b {{ color: {INK}; font-weight: 650; }}
      .card {{ background: #FFFFFF; border-radius: 46px; padding: 42px 46px; box-shadow: 0 2px 6px rgba(60,50,90,.04), 0 22px 54px rgba(60,50,90,.12); }}
      .bubble {{ border-radius: 50%; display: grid; place-items: center; flex-shrink: 0; }}
      .gauge {{ position: relative; }} .gc {{ position: absolute; inset: 0; display: grid; place-content: center; text-align: center; }}
      .track {{ height: 14px; border-radius: 99px; overflow: hidden; }} .track > div {{ height: 100%; border-radius: 99px; }}
      b {{ font-weight: 650; }}
    </style></head><body><div class="slide">{blobs(p, k + i)}<div class="content">{brand()}{body}{foot}</div></div></body></html>'''


# ---------------------------------------------------------------- salida
def main(path: str) -> None:
    from playwright.sync_api import sync_playwright
    lote = json.loads(Path(path).read_text())
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
            files = []
            n = len(post["slides"])
            for i, s in enumerate(post["slides"], 1):
                tmp = out / "_slide.html"
                tmp.write_text(slide_html(post, s, i, n, k), encoding="utf-8")
                pg.goto(tmp.as_uri())
                pg.evaluate("document.fonts.ready")
                pg.wait_for_timeout(150)
                over = pg.evaluate("() => { const s = document.querySelector('.content'); return s.scrollHeight - s.clientHeight; }")
                if over > 1:
                    print(f"AVISO: {post['id']} diapositiva {i} no cabe ({over}px de más)")
                wide = pg.evaluate("""() => [...document.querySelectorAll('.card')].map(c => {
                    const r = c.getBoundingClientRect(); let m = 0;
                    c.querySelectorAll('*').forEach(e => { if (e.closest('.free')) return; const q = e.getBoundingClientRect(); if (q.width) m = Math.max(m, q.right - (r.right - 24), (r.left + 24) - q.left); });
                    return Math.round(m); }).filter(x => x > 1)""")
                if wide:
                    print(f"AVISO: {post['id']} diapositiva {i}: algo se sale de la tarjeta ({wide}px)")
                edge = pg.evaluate("""() => { let m = 0; document.querySelectorAll('.content *').forEach(e => { if (e.closest('.deco, .free')) return; const q = e.getBoundingClientRect();
                    if (q.width) m = Math.max(m, q.right - (innerWidth - 40), 40 - q.left); }); return Math.round(m); }""")
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
        # cuadrícula del perfil: lo último publicado sale arriba a la izquierda (miniaturas 3:4, como Instagram)
        cells = "".join(f'<img src="{c.as_uri()}">' for c in reversed(covers))
        pg.set_viewport_size({"width": 1080, "height": 1440})
        grid = out / "_grid.html"
        grid.write_text(f'''<html><body style="margin:0;background:#fff"><div style="display:grid;grid-template-columns:repeat(3,1fr);gap:4px;width:1080px">
          {cells.replace("<img", '<img style="width:100%;aspect-ratio:3/4;object-fit:cover;display:block"')}</div></body></html>''')
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
        imgs = "".join(f'<a href="{k:02d}-{post["id"]}-{i}.png" target="_blank"><img src="{k:02d}-{post["id"]}-{i}.png" alt="Diapositiva {i}"></a>'
                       for i in range(1, len(post["slides"]) + 1))
        n = len(post["slides"])
        rows.append(f'''<section><div class="head"><span class="num">{k}</span><h2>{esc(post["title"])}</h2>
          <span class="meta">{n} {"imágenes · carrusel" if n > 1 else "imagen"}</span></div>
          <div class="imgs">{imgs}</div>
          <details open><summary>Texto del post</summary><p>{esc(post["caption"]).replace(chr(10), "<br>")}</p>
          <p class="tags">{esc(" ".join(post.get("hashtags", [])))}</p><p class="alt">Texto alternativo: {esc(post.get("alt", ""))}</p></details></section>''')
    fonts = HERE / "fonts"
    (out / "todos.html").write_text(f'''<!doctype html><html lang="es"><head><meta charset="utf-8"><title>Instagram · lote {lote["lote"]}</title>
      <meta name="viewport" content="width=device-width, initial-scale=1"><style>
      @font-face {{ font-family: GSF; font-weight: 1 1000; src: url("../../fonts/google-sans-flex-latin-wght-normal.woff2") format("woff2-variations"); }}
      body {{ margin: 0; background: #F0F2F5; font-family: GSF, system-ui, sans-serif; color: #1F1F1F; }}
      header {{ padding: 28px 32px 8px; }} header h1 {{ margin: 0; font-size: 28px; }} header p {{ margin: 6px 0 0; color: #5F6368; }}
      section {{ background: #fff; margin: 18px 24px; padding: 20px 22px; border-radius: 24px; box-shadow: 0 1px 4px rgba(0,0,0,.06); }}
      .head {{ display: flex; align-items: center; gap: 12px; margin-bottom: 14px; }} h2 {{ margin: 0; font-size: 21px; }}
      .num {{ width: 34px; height: 34px; border-radius: 50%; background: #1A73E8; color: #fff; display: grid; place-items: center; font-weight: 700; }}
      .meta {{ color: #5F6368; font-size: 14px; margin-left: auto; }}
      .imgs {{ display: flex; gap: 12px; overflow-x: auto; padding-bottom: 6px; }}
      .imgs img {{ height: min(52vh, 460px); aspect-ratio: 4/5; border-radius: 14px; display: block; box-shadow: 0 1px 6px rgba(0,0,0,.12); }}
      details {{ margin-top: 12px; }} summary {{ cursor: pointer; color: #0B57D0; font-weight: 600; }}
      details p {{ max-width: 760px; line-height: 1.5; margin: 10px 0 0; }} .tags {{ color: #0B57D0; }} .alt {{ color: #5F6368; font-size: 14px; }}
      </style></head><body><header><h1>Instagram · lote {lote["lote"]}</h1><p>{esc(lote.get("notes", ""))}</p></header>
      {"".join(rows)}</body></html>''', encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else str(HERE / "lote-01.json"))
