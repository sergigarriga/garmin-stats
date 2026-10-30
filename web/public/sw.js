// Service worker de "Mi salud": abre al instante (guarda la última versión de la página) y recibe los avisos.
const CACHE = 'mi-salud-v1';

self.addEventListener('install', (e) => { self.skipWaiting(); });
self.addEventListener('activate', (e) => {
  e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

// Navegación: red primero (datos siempre frescos); sin red, la última copia guardada.
self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.mode !== 'navigate') return;  // data.js, API, etc.: siempre a la red
  e.respondWith(fetch(req).then((res) => {
    if (res.ok && !res.redirected && new URL(res.url).pathname === '/') {
      const copy = res.clone();
      caches.open(CACHE).then((c) => c.put('/', copy));
    }
    return res;
  }).catch(() => caches.match('/').then((r) => r || Response.error())));
});

self.addEventListener('push', (e) => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; } catch (_) { d = { body: e.data && e.data.text() }; }
  e.waitUntil(self.registration.showNotification(d.title || 'Mi salud', {
    body: d.body || '', icon: '/icons/icon-192.png', badge: '/icons/badge-96.png',
    tag: d.tag || 'mi-salud', renotify: true, data: { url: d.url || '/#hoy' },
  }));
});

self.addEventListener('notificationclick', (e) => {
  e.notification.close();
  const url = (e.notification.data && e.notification.data.url) || '/#hoy';
  e.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((cs) => {
    for (const c of cs) { if ('focus' in c) { c.navigate(url); return c.focus(); } }
    return self.clients.openWindow(url);
  }));
});
