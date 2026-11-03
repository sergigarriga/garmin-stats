"""Detector de desbordes (uso: SITE_URL=https://… OK=<cookie gs_session> uv run --with playwright python tools/overflow_check.py 360,390,768).

Opcional: PAGES=plan,hoy limita las páginas; SHOTS=<carpeta> guarda capturas. Sin OK no pone cookie
(p. ej. contra un proxy local que sirve la web compilada y pide los datos a la web real)."""
import glob, json, os, sys
from playwright.sync_api import sync_playwright

URL = os.environ["SITE_URL"].rstrip("/") + "/"  # p. ej. https://xxxx.cloudfront.net
PAGES = os.environ["PAGES"].split(",") if os.environ.get("PAGES") else ["hoy", "sueno", "corazon", "actividad", "comida", "plan", "entreno", "ritmos", "gimnasio", "progreso", "analisis"]
WIDTHS = [int(w) for w in (sys.argv[1] if len(sys.argv) > 1 else "360,390,768").split(",")]
SHOTS = os.environ.get("SHOTS")
JS = r"""() => {
  const out = []; const vw = document.documentElement.clientWidth;
  const hasText = (el) => [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
  for (const el of document.querySelectorAll('body *')) {
    if (!hasText(el) && !['svg','INPUT'].includes(el.tagName)) continue;
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden' || +cs.opacity === 0) continue;
    const r = el.getBoundingClientRect(); if (!r.width || !r.height) continue;
    let p = el.parentElement, scroller = false, card = null, fixed = false;
    while (p && p !== document.body) {
      const ps = getComputedStyle(p);
      if (/(auto|scroll)/.test(ps.overflowX) && p.scrollWidth > p.clientWidth + 1) scroller = true;
      if (ps.position === 'fixed') fixed = true;
      if (!card && (p.classList.contains('MuiCard-root') || p.classList.contains('MuiPaper-root'))) card = p;
      p = p.parentElement;
    }
    if (scroller) continue;
    if (el.closest('.leaflet-container')) continue;  // el mapa recorta sus capas (overflow: hidden): no se ven fuera
    const text = (el.textContent || el.tagName).trim().replace(/\s+/g, ' ').slice(0, 70);
    if (r.right > vw + 1 || r.left < -1) out.push(['pantalla', text, Math.round(r.right - vw)]);
    else if (card) { const c = card.getBoundingClientRect(); const o = Math.max(r.right - c.right, c.left - r.left);
      if (o > 1) out.push(['tarjeta', text, Math.round(o)]); }
    if (cs.textOverflow === 'ellipsis' && el.scrollWidth > el.clientWidth + 1) out.push(['cortado', text, el.scrollWidth - el.clientWidth]);
  }
  if (document.documentElement.scrollWidth > vw + 1) out.push(['scroll-horizontal', 'la página entera', document.documentElement.scrollWidth - vw]);
  return out;
}"""
exe = glob.glob(os.path.expanduser("~/.cache/ms-playwright/chromium_headless_shell-1208/*/chrome-headless-shell"))[0]
res = {}
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=exe, args=["--disable-renderer-backgrounding", "--disable-background-timer-throttling"])
    for w in WIDTHS:
        c = b.new_context(viewport={"width": w, "height": 900}, device_scale_factor=1, is_mobile=w < 600, has_touch=w < 600)
        if os.environ.get("OK"):
            c.add_cookies([{"name": "gs_session", "value": os.environ["OK"], "domain": URL.split("/")[2].split(":")[0], "path": "/", "secure": True}])
        pg = c.new_page(); pg.goto(URL + "#hoy"); pg.wait_for_timeout(2500)
        act = pg.evaluate("() => (window.__GARMIN__.activities.find(a => a.km) || {}).id")
        for name in PAGES + ([f"act-{act}"] if not os.environ.get("PAGES") else []):
            pg.evaluate(f"location.hash = '{name}'"); pg.wait_for_timeout(1800)
            for f in pg.query_selector_all(".MuiAccordionSummary-root[aria-expanded=false]")[:2]:
                try: f.click(); pg.wait_for_timeout(300)
                except Exception: pass
            items = pg.evaluate(JS)
            seen = set()
            for k, t, o in items:
                if (k, t) in seen: continue
                seen.add((k, t)); res.setdefault(f"{name}", []).append(f"{w}px {k:8} +{o}px  {t}")
            if SHOTS: pg.screenshot(path=f"{SHOTS}/{name}-{w}.png", full_page=True)
    b.close()
for k, v in res.items():
    print(f"== {k}"); [print("  ", x) for x in v[:25]]
if not res: print("sin desbordes")
