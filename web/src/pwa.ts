// App instalable y avisos push.
const isWeb = window.location.protocol === 'https:' || window.location.hostname === 'localhost';

type InstallEvent = Event & { prompt: () => Promise<void>; userChoice: Promise<{ outcome: string }> };
let deferred: InstallEvent | null = null;
const listeners = new Set<() => void>();
export const onInstallChange = (f: () => void) => { listeners.add(f); return () => listeners.delete(f); };

export function setupPwa() {
  if (!isWeb || !('serviceWorker' in navigator)) return;
  navigator.serviceWorker.register('/sw.js').catch(() => { /* sin service worker: la web sigue funcionando */ });
  window.addEventListener('beforeinstallprompt', (e) => { e.preventDefault(); deferred = e as InstallEvent; listeners.forEach((f) => f()); });
  window.addEventListener('appinstalled', () => { deferred = null; listeners.forEach((f) => f()); });
}

export const isStandalone = () =>
  window.matchMedia('(display-mode: standalone)').matches || (navigator as unknown as { standalone?: boolean }).standalone === true;
export const isIos = () => /iphone|ipad|ipod/i.test(navigator.userAgent);
export const canPromptInstall = () => !!deferred;

export async function promptInstall() {
  if (!deferred) return false;
  await deferred.prompt();
  const { outcome } = await deferred.userChoice;
  deferred = null;
  listeners.forEach((f) => f());
  return outcome === 'accepted';
}

function urlB64ToUint8Array(b64: string) {
  const pad = '='.repeat((4 - (b64.length % 4)) % 4);
  const raw = atob((b64 + pad).replace(/-/g, '+').replace(/_/g, '/'));
  return Uint8Array.from([...raw].map((c) => c.charCodeAt(0)));
}

export const pushSupported = () => isWeb && 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;

/** Pide permiso, suscribe este dispositivo y envía un aviso de prueba. */
export async function enablePush(vapidPublicKey: string): Promise<string> {
  if (!pushSupported()) {
    return isIos() && !isStandalone()
      ? 'En iPhone, primero añade la app a la pantalla de inicio (Compartir → Añadir a pantalla de inicio) y actívalos desde ahí.'
      : 'Este navegador no admite notificaciones.';
  }
  const perm = await Notification.requestPermission();
  if (perm !== 'granted') return 'No has dado permiso para las notificaciones.';
  const reg = await navigator.serviceWorker.ready;
  const sub = (await reg.pushManager.getSubscription())
    ?? await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: urlB64ToUint8Array(vapidPublicKey) });
  const post = (path: string, body: unknown) => fetch(path, {
    method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Garmin-Stats': '1' }, body: JSON.stringify(body),
  });
  const r = await post('/api/push/subscribe', { subscription: sub.toJSON() });
  if (!r.ok) return 'No se pudo activar. Inténtalo de nuevo.';
  await post('/api/push/test', {});
  return 'Avisos activados: cada día a las 7:30 te llegará tu preparación y la sesión del día. Te he enviado uno de prueba.';
}
