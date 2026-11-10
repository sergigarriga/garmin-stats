// Que la web se porte como una app en el móvil.
//
// 1. Sin zoom: iOS ignora `user-scalable=no` del viewport, así que el pellizco se corta aquí
//    (los gestos `gesture*` son solo de Safari; el mapa usa eventos táctiles y sigue haciendo zoom).
// 2. Teclado: en iOS el teclado no encoge la página, solo la parte visible (visualViewport).
//    Publicamos su tamaño y posición en variables CSS para que la cabecera y el chat se queden
//    pegados a lo que ves:
//      --vv-h    alto visible (px)
//      --vv-top  cuánto ha desplazado iOS la vista para enseñar el campo (px)
//      --no-kb   1 sin teclado, 0 con teclado (para quitar márgenes de la zona segura)
//    y `<html data-kb="1">` mientras el teclado está abierto.

const KB_MIN = 120; // menos que esto es la barra del navegador, no un teclado

function isTextField(el: Element | null): boolean {
  if (!el) return false;
  if (el instanceof HTMLTextAreaElement) return !el.readOnly;
  if (el instanceof HTMLInputElement) {
    return !el.readOnly && !['button', 'checkbox', 'radio', 'range', 'file', 'submit', 'reset', 'color', 'image'].includes(el.type);
  }
  return (el as HTMLElement).isContentEditable === true;
}

export function setupViewport() {
  const root = document.documentElement;

  const stop = (e: Event) => e.preventDefault();
  for (const ev of ['gesturestart', 'gesturechange', 'gestureend']) document.addEventListener(ev, stop, { passive: false });

  // Alto de referencia sin teclado: el mayor visto con este ancho (cambia al girar el móvil).
  let width = window.innerWidth;
  let full = window.innerHeight;
  const vv = window.visualViewport;

  const update = () => {
    if (window.innerWidth !== width) { width = window.innerWidth; full = window.innerHeight; }
    const h = vv?.height ?? window.innerHeight;
    const top = vv?.offsetTop ?? 0;
    if (!isTextField(document.activeElement)) full = Math.max(full, window.innerHeight, h);
    // iOS: innerHeight no cambia y baja el visible. Android (resizes-content): baja todo.
    const kb = isTextField(document.activeElement) && full - h > KB_MIN;
    root.style.setProperty('--vv-h', `${Math.round(h)}px`);
    root.style.setProperty('--vv-top', `${Math.round(top)}px`);
    root.style.setProperty('--no-kb', kb ? '0' : '1');
    if ((root.dataset.kb === '1') !== kb) root.dataset.kb = kb ? '1' : '0';
  };

  update();
  vv?.addEventListener('resize', update);
  vv?.addEventListener('scroll', update);
  window.addEventListener('resize', update);
  window.addEventListener('orientationchange', () => setTimeout(update, 300));
  document.addEventListener('focusin', update);
  document.addEventListener('focusout', () => {
    update();
    // Al cerrar el teclado iOS a veces deja la página desplazada o con huecos: se recoloca.
    setTimeout(() => {
      update();
      if (!isTextField(document.activeElement) && (vv?.offsetTop ?? 0) > 0) window.scrollTo(window.scrollX, window.scrollY);
    }, 250);
  });
}
