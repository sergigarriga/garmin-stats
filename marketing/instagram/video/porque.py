"""Serie «El porqué de tus datos»: escribe un reel-pq-<id>.html por cada reel de reels-porque.json.

    python3 marketing/instagram/video/porque.py            # escribe los HTML
    uv run --no-project --with playwright==1.58.0 --with numpy python marketing/instagram/video/render_video.py \
        marketing/instagram/video/reel-pq-reposo.html --musica --out marketing/instagram/out/video-porque

Todos comparten la misma estructura, pensada para leerse sin sonido: 1 gancho (visible desde el primer fotograma),
2 el porqué con un gráfico animado, 3 qué lo mueve, 4 qué hacer, 5 cierre con el logotipo. Usan kit.css + kit.js.
Gráficos (chart.type): line (línea con franja normal y marca), weight (puntos diarios + media de 7 días), bars (carga
semanal y ratio), zones (semana por zonas), phases (fases de una noche) y parts (nota de Preparación y sus señales).
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "reels-porque.json"
ILL_INK = {"olive": "crema", "sea": "crema", "lavender": "crema", "espresso": "crema", "sage": "espresso",
           "butter": "espresso", "cream": "olivo", "paper": "olivo"}


def rich(text: str) -> str:
    """*asteriscos* → cursiva de color."""
    parts = re.split(r"\*([^*]+)\*", text)
    return "".join(f"<em>{html.escape(x)}</em>" if i % 2 else html.escape(x) for i, x in enumerate(parts))


def page(r: dict, ui: dict) -> str:
    e = html.escape
    t = ui[r["lang"]]
    ch = r["chart"]
    rows3 = "".join(f'<div class="rl"><div class="x">{e(a)}</div><div class="d">{e(b)}</div></div>' for a, b in r["moves"]["rows"])
    steps = "".join(f'<div class="step"><div class="n">{i:02d}</div><div class="x">{e(a)}<small>{e(b)}</small></div></div>'
                    for i, (a, b) in enumerate(r["do"], 1))
    facts = "".join(f"<span>{e(x)}</span>" for x in t["facts"])
    return TEMPLATE.format(
        lang=r["lang"], id=r["id"], flab=f'{e(t["serie"])} · {r["n"]}', bg=r["bg"], bg3=r["bg3"], cbg=r.get("coverBg", r["bg"]),
        hk=e(r["hook"]["k"]), htitle=rich(r["hook"]["title"]), hsize=r["hook"]["size"], hsub=e(r["hook"]["sub"]),
        why=e(t["why"]), wtitle=rich(r["why"]["title"]), take=e(r["why"]["take"]), legend=e(ch.get("legend", "")),
        example=e(t["example"]),
        mk=e(r["moves"]["k"]), mtitle=rich(r["moves"]["title"]), rows3=rows3, nrows=len(r["moves"]["rows"]),
        do=e(t["do"]), dtitle=rich(t["doTitle"]), steps=steps,
        ctitle=rich(r["close"]["title"]), clead=e(r["close"]["lead"]), ill=f'{r["ill"]}-{ILL_INK["espresso"]}', follow=e(t["follow"]),
        ck=e(r["cover"]["k"]), cvtitle=rich(r["cover"]["title"]), cvsize=r["cover"]["size"], facts=facts,
        chart=json.dumps(ch, ensure_ascii=False),
    )


TEMPLATE = r"""<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<!-- Reel de la serie «El porqué de tus datos» ({id}). Lo escribe porque.py a partir de reels-porque.json: no editar a mano.
     render(t) pinta cada fotograma; grabar con render_video.py --musica. Datos de ejemplo. -->
<link rel="stylesheet" href="kit.css">
<style>
  .scene {{ top: 330px; height: 1200px; padding: 0 130px 0 100px; }}
  .scene.center {{ padding: 0 100px; }}
  .lab {{ font-size: 30px; }}
  .sub {{ font-size: 50px; line-height: 1.3; font-weight: 520; color: var(--ink2); text-wrap: balance; }}
  .take {{ font-size: 47px; line-height: 1.3; font-weight: 540; color: var(--ink); text-wrap: pretty; }}
  .legend {{ font-size: 24px; font-weight: 650; letter-spacing: .13em; text-transform: uppercase; color: var(--ink2); }}
  .tick {{ font: 600 26px GSF; fill: #76695F; letter-spacing: .08em; }}
  .rl {{ padding: 31px 0; align-items: center; }}
  .rl .x {{ font-size: 50px; font-weight: 600; line-height: 1.15; }} .rl .d {{ font-size: 37px; font-weight: 560; color: var(--ink2); text-align: right; line-height: 1.2; max-width: 44%; }}
  .step {{ display: flex; gap: 28px; align-items: baseline; padding: 34px 0; border-top: 1.5px solid var(--line); }}
  .step:last-child {{ border-bottom: 1.5px solid var(--line); }}
  .step .n {{ font-family: FR, Georgia, serif; font-style: italic; font-size: 54px; color: var(--accent); width: 76px; flex: none; }}
  .step .x {{ font-size: 51px; line-height: 1.22; font-weight: 600; }}
  .step .x small {{ display: block; font-size: 40px; font-weight: 450; color: var(--ink2); margin-top: 10px; line-height: 1.28; }}
  .box {{ width: 850px; margin-top: 44px; }}
  .zr {{ display: flex; align-items: center; gap: 20px; height: 92px; }}
  .zr .z {{ font: italic 420 46px FR; width: 70px; color: var(--ink); }}
  .zr .nm {{ font-size: 33px; font-weight: 600; width: 190px; color: var(--ink2); }}
  .zr .tr {{ flex: 1; height: 44px; }}
  .zr .b {{ height: 44px; border-radius: 10px; }}
  .zr .pc {{ font: 420 44px FR; width: 110px; text-align: right; }}
  .tag {{ display: inline-block; padding: 14px 30px 15px; border-radius: 999px; font-size: 36px; font-weight: 700; letter-spacing: .04em; white-space: nowrap; }}
  .pr {{ display: flex; align-items: center; gap: 22px; height: 76px; }}
  .pr .nm {{ font-size: 38px; font-weight: 600; width: 300px; }}
  .pr .tr {{ flex: 1; height: 18px; border-radius: 9px; background: rgba(34,26,21,.09); overflow: hidden; }}
  .pr .b {{ height: 18px; border-radius: 9px; background: #5A6B32; }}
  .pr .pc {{ font: 420 44px FR; width: 80px; text-align: right; }}
</style>
</head>
<body>
<div id="stage">
  <div id="frame"><div class="wm">Runch</div><div class="lab" style="color:inherit;font-size:26px">{flab}</div></div>

  <!-- 1 · gancho -->
  <div class="scene t-{bg}" id="s1">
    <div class="lab acc" id="k1">{hk}</div>
    <div class="title" id="t1" style="font-size:{hsize}px;margin-top:34px">{htitle}</div>
    <div class="sub" id="u1" style="margin-top:54px">{hsub}</div>
    <svg id="spark" width="850" height="150" viewBox="0 0 850 150" style="margin-top:70px"><path id="sp" fill="none" stroke="currentColor" stroke-width="5" stroke-linecap="round" stroke-linejoin="round" style="color:var(--accent)"/><circle id="sph" r="11" style="fill:var(--accent)"/></svg>
  </div>

  <!-- 2 · el porqué -->
  <div class="scene t-paper" id="s2">
    <div class="lab acc">{why}</div>
    <div class="title" id="t2" style="font-size:110px;margin-top:20px">{wtitle}</div>
    <div class="box" id="box"></div>
    <div class="row" id="lg2" style="justify-content:space-between;align-items:baseline;margin-top:26px;width:850px">
      <div class="legend">{legend}</div><div class="legend" style="opacity:.75">{example}</div>
    </div>
    <div class="take" id="k2" style="margin-top:44px;max-width:850px">{take}</div>
  </div>

  <!-- 3 · qué lo mueve -->
  <div class="scene t-{bg3}" id="s3">
    <div class="lab acc">{mk}</div>
    <div class="title" id="t3" style="font-size:108px;margin-top:20px">{mtitle}</div>
    <div class="col" id="rows3" style="margin-top:52px">{rows3}</div>
  </div>

  <!-- 4 · qué hacer -->
  <div class="scene t-butter" id="s4">
    <div class="lab acc">{do}</div>
    <div class="title" id="t4" style="font-size:112px;margin-top:20px">{dtitle}</div>
    <div class="col" id="steps4" style="margin-top:52px">{steps}</div>
  </div>

  <!-- 5 · cierre -->
  <div class="scene center t-espresso" id="s5">
    <div class="title" id="t5" style="font-size:108px">{ctitle}</div>
    <div class="sub" id="l5" style="margin-top:36px;max-width:800px">{clead}</div>
    <img id="im5" src="../../marca/ilustraciones/gemini/{ill}.png" style="height:300px;margin-top:56px" alt="">
    <div class="serif" id="wm5" style="font-size:140px;line-height:.9;letter-spacing:-.04em;margin-top:46px">Runch</div>
    <div class="chip solid" id="c5" style="margin-top:46px">{follow}</div>
  </div>

  <!-- portada -->
  <div id="cover" class="t-{cbg}">
    <div class="wm">Runch</div>
    <div class="lab acc" style="font-size:32px">{ck}</div>
    <div class="title" style="font-size:{cvsize}px;margin-top:30px">{cvtitle}</div>
    <div class="facts" style="margin-top:64px">{facts}</div>
    <div class="hd lab" style="color:var(--ink)">@runch.run</div>
  </div>
</div>

<script src="kit.js"></script>
<script>
  window.DURATION = 28;
  const CH = {chart};
  const SC = [[0, 4.9, '{bg}'], [4.7, 12.0, 'paper'], [11.8, 17.5, '{bg3}'], [17.3, 24.0, 'butter'], [23.8, 28.5, 'espresso']];
  const OL = '#5A6B32', LAV = '#8B6FD6', SEA = '#24496D', TINTA = '#221A15', SAGE = '#B9C4A0';
  const NS = 'http://www.w3.org/2000/svg';
  const el = (tag, at = {{}}, parent = null, txt = null) => {{
    const n = document.createElementNS(NS, tag);
    Object.entries(at).forEach(([k, v]) => n.setAttribute(k, v));
    if (txt !== null) n.textContent = txt;
    if (parent) parent.appendChild(n);
    return n;
  }};
  /* curva suave (Catmull-Rom → Bézier) por los puntos */
  const smooth = (P) => P.map((q, i) => {{
    if (!i) return `M${{q[0].toFixed(1)}},${{q[1].toFixed(1)}}`;
    const p0 = P[Math.max(0, i - 2)], p1 = P[i - 1], p3 = P[Math.min(P.length - 1, i + 1)], k = 6;
    return `C${{(p1[0] + (q[0] - p0[0]) / k).toFixed(1)}},${{(p1[1] + (q[1] - p0[1]) / k).toFixed(1)}} ${{(q[0] - (p3[0] - p1[0]) / k).toFixed(1)}},${{(q[1] - (p3[1] - p1[1]) / k).toFixed(1)}} ${{q[0].toFixed(1)}},${{q[1].toFixed(1)}}`;
  }}).join(' ');
  const bubble = (svg, x, y, text, fill = LAV) => {{
    const g = el('g', {{}}, svg), w = text.length * 19 + 44;
    const bx = clamp(x - w / 2, 0, 850 - w);
    el('rect', {{ x: bx, y: y - 62, width: w, height: 54, rx: 27, fill }}, g);
    el('text', {{ x: bx + w / 2, y: y - 25, 'text-anchor': 'middle', style: 'font:700 30px GSF;fill:#F7F3EC;letter-spacing:.02em' }}, g, text);
    g.style.transformBox = 'fill-box'; g.style.transformOrigin = '50% 100%';
    return g;
  }};
  const A = {{}};          // piezas del gráfico
  const box = $('box');
  const W = 850, H = 520;

  /* gancho: una línea fina que se dibuja bajo el titular (el dato «vivo» desde el segundo 0) */
  (() => {{
    const v = CH.v || CH.dots || [3, 4, 3, 5, 4, 6, 5, 7, 6, 8, 7, 9];
    const lo = Math.min(...v), hi = Math.max(...v);
    $('sp').setAttribute('d', smooth(v.map((y, i) => [i / (v.length - 1) * 850, 135 - (y - lo) / (hi - lo || 1) * 120])));
  }})();

  if (CH.type === 'line' || CH.type === 'weight') {{
    const H = 470, svg = el('svg', {{ width: W, height: H, viewBox: `0 0 ${{W}} ${{H}}` }}, box);
    const src = CH.type === 'weight' ? CH.dots : CH.v, n = src.length;
    const X = (i) => 16 + i / (n - 1) * (W - 32), Y = (v) => 410 - (v - CH.lo) / (CH.hi - CH.lo) * 330;
    if (CH.band) {{
      A.band = el('g', {{}}, svg);
      el('rect', {{ x: 0, y: Y(CH.band[1]), width: W, height: Y(CH.band[0]) - Y(CH.band[1]), rx: 10, fill: 'rgba(90,107,50,.13)' }}, A.band);
      CH.band.forEach((b) => el('line', {{ x1: 0, x2: W, y1: Y(b), y2: Y(b), stroke: 'rgba(34,26,21,.24)', 'stroke-width': 2, 'stroke-dasharray': '6 8' }}, A.band));
      el('text', {{ x: 12, y: Y(CH.band[0]) + 34, class: 'tick' }}, A.band, CH.bandLabel);
    }}
    if (CH.v2) {{
      A.line2 = el('path', {{ d: smooth(CH.v2.map((v, i) => [X(i), Y(v)])), fill: 'none', stroke: SEA, 'stroke-width': 5, 'stroke-dasharray': '4 12', 'stroke-linecap': 'round' }}, svg);
      A.lab2 = el('text', {{ x: W, y: Y(CH.v2[0]) + 42, 'text-anchor': 'end', class: 'tick', style: `fill:${{SEA}}` }}, svg, CH.legend2.toUpperCase());
    }}
    let trend = src;
    if (CH.type === 'weight') {{
      trend = src.map((_, i) => {{ const w = src.slice(Math.max(0, i - 6), i + 1); return w.reduce((a, b) => a + b, 0) / w.length; }});
      A.dots = src.map((v, i) => el('circle', {{ cx: X(i), cy: Y(v), r: i === n - 1 ? 15 : 10, fill: i === n - 1 ? LAV : 'rgba(34,26,21,.3)' }}, svg));
    }}
    A.line = el('path', {{ d: smooth(trend.map((v, i) => [X(i), Y(v)])), fill: 'none', stroke: OL, 'stroke-width': 7, 'stroke-linecap': 'round', 'stroke-linejoin': 'round' }}, svg);
    A.head = el('circle', {{ r: 14, fill: OL }}, svg);
    if (CH.mark) A.mark = bubble(svg, X(n - 1), CH.markBand ? Y(CH.band[1]) + 2 : Y(src[n - 1]) - 12, CH.mark);
    el('text', {{ x: 0, y: 462, class: 'tick' }}, svg, CH.xl);
    el('text', {{ x: W, y: 462, class: 'tick', 'text-anchor': 'end' }}, svg, CH.xr);
    A.fin = el('text', {{ x: 0, y: 56, style: `font:420 72px FR;fill:${{OL}};letter-spacing:-.02em` }}, svg, CH.final);
    if (CH.finalLabel) A.finl = el('text', {{ x: 0, y: 96, class: 'tick' }}, svg, CH.finalLabel.toUpperCase());
    if (CH.type === 'weight' || !CH.mark) {{ /* la cifra arriba a la derecha no pisa la marca */ }}
  }}

  if (CH.type === 'bars') {{
    const svg = el('svg', {{ width: W, height: H, viewBox: `0 0 ${{W}} ${{H}}` }}, box);
    const mx = Math.max(...CH.bars.map((b) => b[1])), bw = 98, gap = 28, x0 = 6, base = 456, hh = 300;
    const Yv = (v) => base - v / mx * hh;
    A.bars = CH.bars.map(([l, v], i) => {{
      const last = i === CH.bars.length - 1, x = x0 + i * (bw + gap);
      const r = el('rect', {{ x, y: Yv(v), width: bw, height: base - Yv(v), rx: 12, fill: last ? LAV : SAGE }}, svg);
      r.style.transformBox = 'fill-box'; r.style.transformOrigin = '50% 100%';
      const tv = el('text', {{ x: x + bw / 2, y: Yv(v) + 58, 'text-anchor': 'middle', style: `font:420 50px FR;fill:${{last ? '#F7F3EC' : TINTA}}` }}, svg, String(v));
      el('text', {{ x: x + bw / 2, y: 512, 'text-anchor': 'middle', class: 'tick' }}, svg, l.toUpperCase());
      return [r, tv];
    }});
    const xe = x0 + CH.bars.length * (bw + gap) - gap + 10;
    A.avg = el('g', {{}}, svg);
    el('line', {{ x1: 0, x2: xe, y1: Yv(CH.avg), y2: Yv(CH.avg), stroke: TINTA, 'stroke-width': 2.5, 'stroke-dasharray': '6 8' }}, A.avg);
    el('text', {{ x: 6, y: Yv(CH.avg) - 14, class: 'tick' }}, A.avg, `${{CH.avgLabel}} · ${{CH.avg}}`);
    A.ratio = el('g', {{}}, svg);
    el('text', {{ x: W, y: 52, 'text-anchor': 'end', class: 'tick' }}, A.ratio, CH.ratioLabel.toUpperCase());
    A.rnum = el('text', {{ x: W, y: 178, 'text-anchor': 'end', style: `font:420 132px FR;fill:${{LAV}};letter-spacing:-.03em` }}, A.ratio, CH.ratio);
    A.zone = el('text', {{ x: W, y: 232, 'text-anchor': 'end', style: 'font:600 28px GSF;fill:#76695F' }}, svg, CH.zone);
  }}

  if (CH.type === 'zones') {{
    const COL = ['#B4C784', OL, '#D9C27A', LAV, SEA];
    box.innerHTML = CH.rows.map(([z, nm, pc], i) => `<div class="zr"><div class="z">${{z}}</div><div class="nm">${{nm}}</div>` +
      `<div class="tr"><div class="b" style="width:${{pc / 58 * 100}}%;background:${{COL[i]}}"></div></div><div class="pc">${{pc}} %</div></div>`).join('') +
      `<div class="row" style="gap:18px;margin-top:22px"><span class="tag" id="tg1" style="background:${{OL}};color:#F7F3EC">${{CH.tags[0]}}</span>` +
      `<span class="tag" id="tg2" style="background:${{LAV}};color:#F7F3EC">${{CH.tags[1]}}</span></div>`;
    A.rows = [...box.querySelectorAll('.zr')];
  }}

  if (CH.type === 'phases') {{
    const svg = el('svg', {{ width: W, height: H, viewBox: `0 0 ${{W}} ${{H}}` }}, box);
    const COL = ['#D9C27A', LAV, SAGE, SEA], x0 = 190, ww = W - x0, rh = 86, y0 = 70;
    CH.rows.forEach((r, i) => {{
      el('text', {{ x: 0, y: y0 + i * (rh + 12) + 54, style: 'font:600 32px GSF;fill:#221A15' }}, svg, r);
      el('rect', {{ x: x0, y: y0 + i * (rh + 12), width: ww, height: rh, rx: 10, fill: 'rgba(34,26,21,.045)' }}, svg);
    }});
    const cp = el('clipPath', {{ id: 'cp' }}, el('defs', {{}}, svg));
    A.clip = el('rect', {{ x: x0, y: 0, width: 0, height: H }}, cp);
    const g = el('g', {{ 'clip-path': 'url(#cp)' }}, svg);
    CH.seg.forEach(([s, a, b]) => el('rect', {{ x: x0 + a / CH.total * ww, y: y0 + s * (rh + 12), width: Math.max(4, (b - a) / CH.total * ww - 2), height: rh, rx: 8, fill: COL[s] }}, g));
    A.ww = ww;
    el('text', {{ x: x0, y: 512, class: 'tick' }}, svg, CH.xl);
    el('text', {{ x: W, y: 512, class: 'tick', 'text-anchor': 'end' }}, svg, CH.xr);
    A.tg1 = bubble(svg, x0 + ww * 0.19, 66, CH.tags[0], SEA);
    A.tg2 = bubble(svg, x0 + ww * 0.80, 66, CH.tags[1], LAV);
  }}

  if (CH.type === 'parts') {{
    const C = 2 * Math.PI * 104;
    box.innerHTML = `<div class="row" style="align-items:center;gap:44px"><svg width="220" height="220" viewBox="0 0 250 250" style="flex:none">` +
      `<circle cx="125" cy="125" r="104" fill="none" stroke="rgba(34,26,21,.09)" stroke-width="20"/>` +
      `<circle id="ring" cx="125" cy="125" r="104" fill="none" stroke="${{OL}}" stroke-width="20" stroke-linecap="round" stroke-dasharray="${{C}} ${{C}}" transform="rotate(-90 125 125)"/>` +
      `<text id="rnum" x="125" y="158" text-anchor="middle" style="font:420 96px FR;fill:${{TINTA}};letter-spacing:-.03em">${{CH.score}}</text></svg>` +
      `<div><div class="serif" id="rlab" style="font-size:66px;font-style:italic;color:${{OL}};line-height:1.05">${{CH.label}}</div>` +
      `<div class="legend" style="margin-top:14px">0–100</div></div></div><div style="margin-top:22px">` +
      CH.rows.map(([nm, v]) => `<div class="pr"><div class="nm">${{nm}}</div><div class="tr"><div class="b" style="width:${{v}}%"></div></div><div class="pc">${{v}}</div></div>`).join('') + '</div>';
    A.C = C; A.rows = [...box.querySelectorAll('.pr')];
  }}

  function chart(t, a, rt) {{
    if (CH.type === 'line') {{
      if (A.band) fade(A.band, t, a + 0.1);
      if (A.line2) {{ draw(A.line2, t, a + 0.3, 1.4); A.line2.style.strokeDasharray = '4 12'; A.line2.style.strokeDashoffset = 0; A.line2.style.opacity = eo(p(t, a + 0.2, a + 0.9)); fade(A.lab2, t, a + 0.6); }}
      draw(A.line, t, a + 0.5, 2.3, A.head);
      A.head.setAttribute('r', 14 + (t > a + 2.8 ? 3 * Math.sin(rt * 4.5) ** 2 : 0));
      if (A.mark) {{ const q = p(t, a + 2.7, a + 3.2); A.mark.style.opacity = clamp(q * 3); A.mark.style.transform = `scale(${{eb(q)}})`; }}
      A.fin.style.opacity = eo(p(t, a + 0.5, a + 1.0)); count(A.fin, t, a + 0.5, 2.3, CH.from);
    }}
    if (CH.type === 'weight') {{
      A.dots.forEach((d, i) => {{ const q = p(t, a + 0.2 + i * 0.1, a + 0.5 + i * 0.1); d.style.opacity = clamp(q * 2); d.style.transformBox = 'fill-box'; d.style.transformOrigin = '50% 50%'; d.style.transform = `scale(${{eb(q)}})`; }});
      const q = p(t, a + 1.7, a + 2.2); A.mark.style.opacity = clamp(q * 3); A.mark.style.transform = `scale(${{eb(q)}})`;
      draw(A.line, t, a + 2.6, 2.0, A.head);
      A.fin.style.opacity = eo(p(t, a + 3.6, a + 4.2)); A.finl.style.opacity = eo(p(t, a + 3.6, a + 4.2));
    }}
    if (CH.type === 'bars') {{
      A.bars.forEach(([r, tv], i) => {{
        const d = a + 0.3 + i * (i === A.bars.length - 1 ? 0.5 : 0.28), q = eo(p(t, d, d + 0.8));
        r.style.transform = `scaleY(${{q}})`; tv.style.opacity = clamp(q * 1.5); count(tv, t, d, 0.8);
      }});
      fade(A.avg, t, a + 2.3); fade(A.ratio, t, a + 3.0); count(A.rnum, t, a + 3.0, 1.1, 1); fade(A.zone, t, a + 3.9);
    }}
    if (CH.type === 'zones') {{
      A.rows.forEach((r, i) => {{ rise(r, t, a + 0.3 + i * 0.22, 0.5, 20); grow(r.querySelector('.b'), t, a + 0.5 + i * 0.22, 0.9); count(r.querySelector('.pc'), t, a + 0.5 + i * 0.22, 0.9); }});
      const dim = eo(p(t, a + 2.6, a + 3.1));
      A.rows.forEach((r, i) => {{ if (i > 1) r.style.opacity = Math.min(+r.style.opacity, 1 - 0.45 * dim * (1 - eo(p(t, a + 3.7, a + 4.2)))); }});
      pop($('tg1'), t, a + 2.7, -3); pop($('tg2'), t, a + 3.8, 3);
    }}
    if (CH.type === 'phases') {{
      A.clip.setAttribute('width', A.ww * eio(p(t, a + 0.4, a + 3.4)));
      [[A.tg1, 1.6], [A.tg2, 3.3]].forEach(([g, d]) => {{ const q = p(t, a + d, a + d + 0.5); g.style.opacity = clamp(q * 3); g.style.transform = `scale(${{eb(q)}})`; }});
    }}
    if (CH.type === 'parts') {{
      const q = e5(p(t, a + 0.3, a + 1.9));
      $('ring').style.strokeDashoffset = A.C * (1 - q * CH.score / 100);
      count($('rnum'), t, a + 0.3, 1.6); rise($('rlab'), t, a + 1.5);
      A.rows.forEach((r, i) => {{ rise(r, t, a + 2.0 + i * 0.3, 0.5, 20); grow(r.querySelector('.b'), t, a + 2.1 + i * 0.3, 0.8); count(r.querySelector('.pc'), t, a + 2.1 + i * 0.3, 0.8); }});
    }}
  }}

  window.render = function (t, rt = t) {{
    background(t, SC);
    const s = (k) => $('s' + k);
    // 1 · gancho: el titular ya está entrando en el primer fotograma
    scene(s(1), t, -1, SC[0][1]);
    set($('k1'), 1);
    words($('t1'), t, -0.28, 0.07);
    rise($('u1'), t, 1.5, 0.6);
    draw($('sp'), t, 0.2, 3.2, $('sph'));

    // 2 · el porqué
    const a = SC[1][0];
    scene(s(2), t, a, SC[1][1]);
    words($('t2'), t, a + 0.15);
    chart(t, a + 0.5, rt);
    fade($('lg2'), t, a + 0.9);
    rise($('k2'), t, a + 2.4, 0.7);

    // 3 · qué lo mueve
    scene(s(3), t, SC[2][0], SC[2][1]);
    words($('t3'), t, SC[2][0] + 0.15);
    cascade($('rows3'), t, SC[2][0] + 0.7, {nrows} > 4 ? 0.34 : 0.42, 0.6);

    // 4 · qué hacer
    scene(s(4), t, SC[3][0], SC[3][1]);
    words($('t4'), t, SC[3][0] + 0.15);
    cascade($('steps4'), t, SC[3][0] + 0.7, 0.7, 0.7);

    // 5 · cierre
    const z = SC[4][0];
    scene(s(5), t, z, 99);
    words($('t5'), t, z + 0.15);
    rise($('l5'), t, z + 0.9);
    figure($('im5'), t, z + 0.6, rt, 0.8, 90); pop($('wm5'), t, z + 1.2, 0, 0.6);
    pop($('c5'), t, z + 1.7, -3);
  }};
  render(0);
</script>
</body>
</html>
"""


def main() -> None:
    data = json.loads(DATA.read_text())
    for r in data["reels"]:
        out = HERE / f'reel-pq-{r["id"]}.html'
        out.write_text(page(r, data["ui"]))
        print(out.name)


if __name__ == "__main__":
    main()
