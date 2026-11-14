// Uso de la app (solo lo ve el administrador): cuándo se abre, qué páginas y acciones, y cuántos segundos está a la vista.
// Solo recuentos, nunca el contenido de lo que se escribe. Se envía junto cada ~30 s y al salir; si falla, no pasa nada.
type Ev = { k: 'open' | 'view' | 'act'; n: string; pwa?: boolean };

const FLUSH_MS = 30_000;
const NEW_SESSION_AFTER = 30 * 60_000; // volver tras media hora fuera cuenta como una apertura nueva
let queue: Ev[] = [];
let secs = 0;
let since: number | null = null; // desde cuándo está a la vista (ms)
let started = false;
let hiddenAt = 0;
let lastView = '';

const standalone = () => window.matchMedia?.('(display-mode: standalone)').matches || (navigator as { standalone?: boolean }).standalone === true;

export function track(k: Ev['k'], n: string) {
  if (k === 'view') { if (n === lastView) return; lastView = n; }
  queue.push(k === 'open' ? { k, n, pwa: standalone() } : { k, n });
}

function tick() {
  if (since != null) { const now = Date.now(); secs += Math.round((now - since) / 1000); since = now; }
}

function flush() {
  tick();
  if (!queue.length && secs <= 0) return;
  const body = JSON.stringify({ events: queue.slice(0, 60), secs });
  queue = queue.slice(60);
  secs = 0;
  try { void nativeFetch('./api/track', { method: 'POST', credentials: 'same-origin', keepalive: true, headers: { 'Content-Type': 'application/json' }, body }).catch(() => {}); } catch { /* sin red */ }
}

const nativeFetch: typeof fetch = window.fetch.bind(window);

/** Empieza a contar (una sola vez). Apunta las llamadas de acción a la API (POST) como «acciones». */
export function startTracking() {
  if (started) return;
  started = true;
  window.fetch = (input, init) => {
    try {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
      const m = /(?:^|\/)api\/([a-z0-9_/-]+)/i.exec(url.split('?')[0]);
      const method = (init?.method ?? (typeof input === 'object' && 'method' in input ? input.method : 'GET')).toUpperCase();
      if (m && method !== 'GET' && !/^(track|me)$/.test(m[1])) queue.push({ k: 'act', n: m[1].replace(/\/[0-9a-f-]{8,}.*$/i, '').toLowerCase().slice(0, 40) });
    } catch { /* nunca estorba a la llamada */ }
    return nativeFetch(input, init);
  };
  const mobile = window.matchMedia?.('(max-width: 899px)').matches ?? false;
  track('open', mobile ? 'm' : 'd');
  if (document.visibilityState === 'visible') since = Date.now();
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') { flush(); tick(); since = null; hiddenAt = Date.now(); }
    else {
      since = Date.now();
      if (hiddenAt && Date.now() - hiddenAt > NEW_SESSION_AFTER) track('open', mobile ? 'm' : 'd');
    }
  });
  window.addEventListener('pagehide', flush);
  window.setInterval(() => { if (document.visibilityState === 'visible') flush(); }, FLUSH_MS);
  flush();
}
