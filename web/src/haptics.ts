// Vibración del móvil. Solo Android (Chrome): navigator.vibrate con patrones para toque, éxito y aviso.
// iPhone: Safari no expone la vibración a las webs instaladas, así que aquí no hace nada.

type Kind = 'tap' | 'success' | 'warning';

const PATTERNS: Record<Kind, number[]> = { tap: [8], success: [18, 60, 26], warning: [40, 70, 40] };

export function haptic(kind: Kind = 'tap') {
  try {
    if (typeof navigator !== 'undefined' && typeof navigator.vibrate === 'function') navigator.vibrate(PATTERNS[kind]);
  } catch { /* sin vibración disponible */ }
}
