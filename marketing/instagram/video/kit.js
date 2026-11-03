/* Kit de los Reels editoriales de Runch: utilidades para pintar cada fotograma con render(t) (sin animaciones CSS ni
   reloj real, así render_video.py graba fotograma a fotograma sin saltos). Las mismas animaciones que las diapositivas
   animadas de los posts: palabras que suben, cifras que cuentan (formato 7,5 · 5:15 · −1000 · 150–300), líneas que se
   dibujan con el punto en la punta, filas que entran en cascada y barras que crecen.
   t = tiempo de animación (lo estira timewarp.py para seguir a la voz); rt = tiempo real (para el ambiente). */
const $ = (id) => document.getElementById(id);
const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
const p = (t, a, b) => clamp((t - a) / (b - a));
const eo = (x) => 1 - Math.pow(1 - x, 3);
const e5 = (x) => 1 - Math.pow(1 - x, 5);
const eio = (x) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2);
const eb = (x) => { const c1 = 1.70158, c3 = c1 + 1; return x <= 0 ? 0 : 1 + c3 * Math.pow(x - 1, 3) + c1 * Math.pow(x - 1, 2); };
const set = (el, o = 1, x = 0, y = 0, s = 1, r = 0) => { el.style.opacity = o; el.style.transform = `translate(${x}px,${y}px) scale(${s}) rotate(${r}deg)`; };

/* Cada palabra de los titulares (y de lo que lleve data-split) en su <span class="w">, conservando las cursivas. */
function splitWords(root) {
  const walk = (node) => {
    [...node.childNodes].forEach((n) => {
      if (n.nodeType === 3) {
        const frag = document.createDocumentFragment();
        n.nodeValue.split(/([ \t\n]+)/).forEach((part) => {
          if (!part) return;
          if (/^[ \t\n]+$/.test(part)) frag.appendChild(document.createTextNode(part));
          else { const s = document.createElement('span'); s.className = 'w'; s.textContent = part; frag.appendChild(s); }
        });
        node.replaceChild(frag, n);
      } else if (n.nodeType === 1 && !n.classList.contains('w') && n.tagName !== 'BR') walk(n);
    });
  };
  walk(root);
}
document.querySelectorAll('.title, [data-split]').forEach(splitWords);

/** Escena visible entre a y b: entra desde abajo y sale hacia arriba. */
function scene(el, t, a, b) {
  const i = eo(p(t, a, a + 0.4)), o = eio(p(t, b - 0.35, b));
  el.style.visibility = t < a || t > b ? 'hidden' : 'visible';
  set(el, i * (1 - o), 0, (1 - i) * 50 - o * 110);
}
/** Palabras que suben una tras otra (con un pequeño rebote). */
function words(el, t, start, step = 0.085) {
  el.querySelectorAll('.w').forEach((w, k) => {
    const q = p(t, start + k * step, start + k * step + 0.5);
    set(w, clamp(q * 2.2), 0, (1 - eb(q)) * 56, 0.94 + 0.06 * eb(q));
  });
}
const pop = (el, t, a, rot = 0, dur = 0.45) => { const q = p(t, a, a + dur); set(el, clamp(q * 3), 0, 0, eb(q), rot * (1 - q) + rot * 0.3); };
const rise = (el, t, a, dur = 0.6, dy = 28) => { const q = eo(p(t, a, a + dur)); set(el, q, 0, (1 - q) * dy); };
const fade = (el, t, a, dur = 0.5) => { el.style.opacity = eo(p(t, a, a + dur)); };
/** Hijos que entran uno tras otro (filas en cascada). */
function cascade(box, t, a, step = 0.22, dur = 0.6, sel = ':scope > *') {
  box.querySelectorAll(sel).forEach((el, k) => rise(el, t, a + k * step, dur));
}
/** Barra que crece desde la izquierda (o desde abajo con axis = 'y'). */
function grow(el, t, a, dur = 0.9, axis = 'x') {
  const q = eo(p(t, a, a + dur));
  el.style.transformOrigin = axis === 'x' ? 'left center' : 'center bottom';
  el.style.transform = axis === 'x' ? `scaleX(${q})` : `scaleY(${q})`;
}

/* Cifras que cuentan desde 0 con frenada suave, respetando el formato del texto final (como ANIM_JS de render.py). */
const NUM = /\d+(?::\d{2})+|\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:[.,]\d+)?/g;
const parseNum = (num) => {
  if (num.includes(':')) return { clock: num.split(':').length, to: num.split(':').reduce((s, x) => s * 60 + +x, 0) };
  const tsep = /^\d{1,3}(\.\d{3})+/.test(num) ? '.' : '', body = tsep ? num.split('.').join('') : num;
  const dm = body.match(/[.,](\d+)$/);
  return { tsep, dsep: dm ? body[body.length - dm[1].length - 1] : ',', dec: dm ? dm[1].length : 0, to: parseFloat(body.replace(',', '.')) };
};
const fmtNum = (c, v) => {
  if (c.clock) {
    let x = Math.round(v); const parts = [];
    for (let k = 1; k < c.clock; k++) { parts.unshift(String(x % 60).padStart(2, '0')); x = Math.floor(x / 60); }
    return [x, ...parts].join(':');
  }
  let txt = v.toFixed(c.dec).replace('.', c.dsep);
  if (c.tsep) { const [a, b] = txt.split(c.dsep); txt = a.replace(/\B(?=(\d{3})+(?!\d))/g, c.tsep) + (b !== undefined ? c.dsep + b : ''); }
  return txt;
};
/** count(el, t, a, dur, from): el muestra su texto final; mientras cuenta, cada cifra va de `from` (0) a su valor. */
function count(el, t, a, dur = 1.4, from = 0) {
  if (!el._raw) {
    el._raw = el.textContent;
    const nums = el._raw.match(NUM) || [], pieces = el._raw.split(NUM), cs = nums.map(parseNum);
    el._txt = (e) => pieces.map((x, i) => x + (i < cs.length ? fmtNum(cs[i], from * (1 - e) + cs[i].to * e) : '')).join('');
    el.style.fontVariantNumeric = 'tabular-nums';
  }
  const q = e5(p(t, a, a + dur));
  el.textContent = q >= 0.999 ? el._raw : el._txt(q);
}
/** Línea que se dibuja (path SVG) con su punto en la punta (head, opcional). */
function draw(path, t, a, dur = 1.6, head = null) {
  if (!path._len) path._len = path.getTotalLength();
  const q = eio(p(t, a, a + dur));
  path.style.strokeDasharray = `${path._len} ${path._len}`;
  path.style.strokeDashoffset = path._len * (1 - q);
  path.style.opacity = t < a ? 0 : 1;
  if (head) {
    const pt = path.getPointAtLength(path._len * q);
    head.setAttribute('cx', pt.x); head.setAttribute('cy', pt.y);
    head.style.opacity = t < a ? 0 : 1;
  }
}

/** Ilustración de la marca: entra deslizándose con un rebote y luego se balancea suave (zancada), en tiempo real. */
function figure(el, t, a, rt, dur = 0.8, from = -90) {
  const q = eb(p(t, a, a + dur)), live = t > a + dur;
  el.style.opacity = clamp(p(t, a, a + dur * 0.5));
  el.style.transform = `translate(${(1 - q) * from}px, ${live ? Math.sin(rt * 2.4) * 7 : 0}px) rotate(${(1 - q) * -5 + (live ? Math.sin(rt * 1.4) * 1.2 : 0)}deg)`;
}

/* Fondo: el de la escena actual, con un fundido corto al cambiar. scenes = [[inicio, fin, 'tema'], ...] */
const BG = { cream: '#F7F3EC', paper: '#FCFAF6', terracotta: '#D4542F', espresso: '#221A15', sage: '#CBD3B8', sea: '#24496D', butter: '#F1DEA6' };
const INK = { cream: '#221A15', paper: '#221A15', terracotta: '#FBF3E8', espresso: '#F3ECE2', sage: '#221A15', sea: '#F3ECE2', butter: '#221A15' };
const hex = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
const mix = (a, b, q) => { const x = hex(a), y = hex(b); return `rgb(${x.map((v, i) => Math.round(v + (y[i] - v) * q)).join(',')})`; };
function background(t, scenes) {
  let k = 0;
  scenes.forEach((s, i) => { if (t >= s[0]) k = i; });
  const cur = scenes[k][2], prev = scenes[Math.max(0, k - 1)][2], q = k ? eio(p(t, scenes[k][0], scenes[k][0] + 0.45)) : 1;
  $('stage').style.background = mix(BG[prev], BG[cur], q);
  const fr = $('frame');
  if (fr) fr.style.color = mix(INK[prev], INK[cur], q);
}

/* Portada: oculta las escenas y enseña #cover (tema en su clase t-*). */
window.cover = function () {
  document.querySelectorAll('.scene, #frame').forEach((el) => { el.style.visibility = 'hidden'; });
  const c = $('cover');
  c.style.display = 'flex';
  $('stage').style.background = getComputedStyle(c).getPropertyValue('--bg');
};
