const nf0 = new Intl.NumberFormat('es-ES', { maximumFractionDigits: 0, useGrouping: true });
const nf1 = new Intl.NumberFormat('es-ES', { maximumFractionDigits: 1, minimumFractionDigits: 1 });

export const int = (v?: number | null) => (v == null ? '–' : nf0.format(Math.round(v)));
export const dec1 = (v?: number | null) => (v == null ? '–' : nf1.format(v));

export function hm(hours?: number | null) {
  if (hours == null) return '–';
  const m = Math.round(hours * 60);
  return `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, '0')} min`;
}

export function hmShort(hours?: number | null) {
  if (hours == null) return '–';
  const m = Math.round(hours * 60);
  return `${Math.floor(m / 60)}h ${String(m % 60).padStart(2, '0')}`;
}

/** Horas desde mediodía (12,0 = 00:00) → "01:47". */
export function clockFromNoon(h?: number | null) {
  if (h == null) return '–';
  const m = Math.round(((h + 12) % 24) * 60) % 1440;
  return `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`;
}

export function clock(h?: number | null) {
  if (h == null) return '–';
  const m = Math.round(h * 60) % 1440;
  return `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`;
}

export function pace(minKm?: number | null) {
  if (minKm == null || !isFinite(minKm)) return '–';
  let m = Math.floor(minKm);
  let s = Math.round((minKm - m) * 60);
  if (s === 60) { m += 1; s = 0; }
  return `${m}:${String(s).padStart(2, '0')} /km`;
}

export function duration(sec?: number | null) {
  if (sec == null) return '–';
  const s = Math.round(sec);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const r = s % 60;
  return h ? `${h}:${String(m).padStart(2, '0')}:${String(r).padStart(2, '0')}` : `${m}:${String(r).padStart(2, '0')}`;
}

const dfShort = new Intl.DateTimeFormat('es-ES', { day: 'numeric', month: 'short' });
const dfLong = new Intl.DateTimeFormat('es-ES', { weekday: 'long', day: 'numeric', month: 'long' });
const dfMonth = new Intl.DateTimeFormat('es-ES', { month: 'short', year: '2-digit' });
const dfTime = new Intl.DateTimeFormat('es-ES', { hour: '2-digit', minute: '2-digit' });

export const dateShort = (d: Date) => dfShort.format(d).replace('.', '');
export const dateLong = (d: Date) => dfLong.format(d);
export const monthShort = (d: Date) => dfMonth.format(d).replace('.', '');
export const time = (d: Date) => dfTime.format(d);

export function relative(from: Date, now: Date) {
  const s = Math.max(0, Math.round((now.getTime() - from.getTime()) / 1000));
  if (s < 60) return 'ahora mismo';
  const m = Math.round(s / 60);
  if (m < 60) return `hace ${m} min`;
  const h = Math.round(m / 60);
  if (h < 24) return `hace ${h} h`;
  const d = Math.round(h / 24);
  return d === 1 ? 'ayer' : `hace ${d} días`;
}

export function signed(v: number, digits = 0) {
  const s = v.toFixed(digits).replace('.', ',');
  return v > 0 ? `+${s}` : s.replace('-', '−');
}
