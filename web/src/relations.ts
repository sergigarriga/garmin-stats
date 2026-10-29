import type { Day } from './data';
import type { Category } from './theme';
import { clockFromNoon, hmShort, int } from './format';

/** Variables que se pueden relacionar, con cómo mostrarlas. */
type VarKey = 'bed' | 'sleepH' | 'sleepScore' | 'bbMax' | 'sleepStress' | 'hrv' | 'rhr' | 'load' | 'stress' | 'steps';

const VARS: Record<VarKey, { name: string; fmt: (v: number) => string; low: string; high: string; cat: Category }> = {
  bed: { name: 'la hora de acostarte', fmt: clockFromNoon, low: 'Antes de las', high: 'Después de las', cat: 'sleep' },
  sleepH: { name: 'las horas de sueño', fmt: (v) => hmShort(v), low: 'Menos de', high: 'Más de', cat: 'sleep' },
  sleepScore: { name: 'tu puntuación de sueño', fmt: (v) => `${int(v)} puntos`, low: 'Menos de', high: 'Más de', cat: 'sleep' },
  bbMax: { name: 'tu Body Battery', fmt: (v) => `${int(v)}`, low: 'Menos de', high: 'Más de', cat: 'energy' },
  sleepStress: { name: 'el estrés durante el sueño', fmt: (v) => `${int(v)}`, low: 'Menos de', high: 'Más de', cat: 'stress' },
  hrv: { name: 'tu HRV', fmt: (v) => `${int(v)} ms`, low: 'Menos de', high: 'Más de', cat: 'recovery' },
  rhr: { name: 'tu pulso en reposo', fmt: (v) => `${int(v)} lpm`, low: 'Menos de', high: 'Más de', cat: 'heart' },
  load: { name: 'la carga de entreno', fmt: (v) => `${int(v)}`, low: 'Menos de', high: 'Más de', cat: 'training' },
  stress: { name: 'tu estrés', fmt: (v) => `${int(v)}`, low: 'Menos de', high: 'Más de', cat: 'stress' },
  steps: { name: 'tus pasos', fmt: (v) => `${int(v)} pasos`, low: 'Menos de', high: 'Más de', cat: 'activity' },
};

interface RelationDef {
  id: string;
  x: VarKey; dx: number; // día de x relativo al día i
  y: VarKey; dy: number; // día de y relativo al día i
  /** Titular según el sentido de la relación (positiva: suben juntos). */
  pos: string; neg: string;
  /** Qué compara la tarjeta, en lenguaje de calle. */
  context: string;
  /** Grupos propios (p. ej. descanso / suave / fuerte) en lugar de tercios. */
  groups?: 'load';
}

const DEFS: RelationDef[] = [
  { id: 'bed-score', x: 'bed', dx: 0, y: 'sleepScore', dy: 0,
    neg: 'Cuanto más tarde te acuestas, peor duermes', pos: 'Acostarte tarde no empeora tu sueño',
    context: 'Hora de acostarte y nota de esa noche' },
  { id: 'sleep-bb', x: 'sleepH', dx: 0, y: 'bbMax', dy: 0,
    pos: 'Dormir más te carga la batería', neg: 'Dormir más no se nota en tu Body Battery',
    context: 'Horas dormidas y Body Battery al levantarte' },
  { id: 'sleepstress-score', x: 'sleepStress', dx: 0, y: 'sleepScore', dy: 0,
    neg: 'Si tu cuerpo no se relaja de noche, duermes peor', pos: 'El estrés nocturno no te quita calidad de sueño',
    context: 'Estrés mientras duermes y nota de la noche' },
  { id: 'hrv-stress', x: 'hrv', dx: 0, y: 'stress', dy: 0,
    neg: 'Con la HRV alta, ese día tienes menos estrés', pos: 'Con la HRV alta, ese día tienes más estrés',
    context: 'HRV de la noche y estrés del día siguiente' },
  { id: 'stress-hrv', x: 'stress', dx: 0, y: 'hrv', dy: 1,
    neg: 'Los días de más estrés, tu HRV baja esa noche', pos: 'El estrés del día no baja tu HRV',
    context: 'Estrés del día y HRV de esa noche' },
  { id: 'stress-score', x: 'stress', dx: 0, y: 'sleepScore', dy: 1,
    neg: 'Los días de más estrés duermes peor', pos: 'El estrés del día no empeora tu sueño',
    context: 'Estrés del día y nota de sueño de esa noche' },
  { id: 'sleep-hrv', x: 'sleepH', dx: 0, y: 'hrv', dy: 0,
    pos: 'Más horas de sueño, mejor HRV', neg: 'Dormir más no sube tu HRV',
    context: 'Horas dormidas y HRV de la noche' },
  { id: 'sleep-rhr', x: 'sleepH', dx: 0, y: 'rhr', dy: 0,
    neg: 'Dormir más te baja el pulso en reposo', pos: 'Dormir más no te baja el pulso en reposo',
    context: 'Horas dormidas y pulso en reposo de ese día' },
  { id: 'load-hrv', x: 'load', dx: -1, y: 'hrv', dy: 0, groups: 'load',
    neg: 'Entrenar fuerte te baja la HRV esa noche', pos: 'Entrenar no te baja la HRV',
    context: 'Entreno del día y HRV de esa noche' },
  { id: 'load-rhr', x: 'load', dx: -1, y: 'rhr', dy: 0, groups: 'load',
    pos: 'Después de entrenar fuerte, tu pulso en reposo sube', neg: 'Entrenar te deja el pulso en reposo más bajo',
    context: 'Entreno del día y pulso en reposo al día siguiente' },
  { id: 'steps-sleep', x: 'steps', dx: 0, y: 'sleepH', dy: 1,
    pos: 'Los días que te mueves más, duermes más', neg: 'Los días que te mueves más, duermes menos',
    context: 'Pasos del día y horas de sueño de esa noche' },
  { id: 'steps-score', x: 'steps', dx: 0, y: 'sleepScore', dy: 1,
    pos: 'Los días activos duermes mejor', neg: 'Los días activos duermes peor',
    context: 'Pasos del día y nota de sueño de esa noche' },
];

export interface Group { label: string; mean: number; n: number }
export interface RelationResult {
  id: string; headline: string; context: string; rho: number; n: number;
  strength: 'ninguna' | 'débil' | 'moderada' | 'fuerte'; level: number;
  groups: Group[]; cat: Category; yName: string; fmtY: (v: number) => string; summary: string;
}

function ranks(v: number[]) {
  const idx = v.map((x, i) => [x, i] as const).sort((a, b) => a[0] - b[0]);
  const r = new Array<number>(v.length);
  for (let i = 0; i < idx.length;) {
    let j = i;
    while (j + 1 < idx.length && idx[j + 1][0] === idx[i][0]) j++;
    const avg = (i + j) / 2 + 1;
    for (let k = i; k <= j; k++) r[idx[k][1]] = avg;
    i = j + 1;
  }
  return r;
}

function pearson(a: number[], b: number[]) {
  const n = a.length;
  const ma = a.reduce((s, x) => s + x, 0) / n;
  const mb = b.reduce((s, x) => s + x, 0) / n;
  let num = 0, da = 0, db = 0;
  for (let i = 0; i < n; i++) { num += (a[i] - ma) * (b[i] - mb); da += (a[i] - ma) ** 2; db += (b[i] - mb) ** 2; }
  return da && db ? num / Math.sqrt(da * db) : 0;
}

const quantile = (sorted: number[], q: number) => sorted[Math.min(sorted.length - 1, Math.floor(q * (sorted.length - 1)))];
const meanOf = (v: number[]) => v.reduce((s, x) => s + x, 0) / v.length;

function strengthOf(r: number): [RelationResult['strength'], number] {
  const a = Math.abs(r);
  if (a < 0.1) return ['ninguna', 0];
  if (a < 0.3) return ['débil', 1];
  if (a < 0.5) return ['moderada', 2];
  return ['fuerte', 3];
}

/** Calcula todas las relaciones sobre las filas dadas (días consecutivos). */
export function computeRelations(days: Day[], minN = 20): RelationResult[] {
  const out: RelationResult[] = [];
  for (const def of DEFS) {
    const xs: number[] = [];
    const ys: number[] = [];
    for (let i = 0; i < days.length; i++) {
      const dx = days[i + def.dx];
      const dy = days[i + def.dy];
      const x = dx?.[def.x];
      const y = dy?.[def.y];
      if (x != null && y != null) { xs.push(x); ys.push(y); }
    }
    if (xs.length < minN) continue;
    const rho = pearson(ranks(xs), ranks(ys));
    const [strength, level] = strengthOf(rho);
    const X = VARS[def.x];
    const Y = VARS[def.y];

    let groups: Group[];
    if (def.groups === 'load') {
      const pos = xs.filter((v) => v > 0).sort((a, b) => a - b);
      const med = pos.length ? quantile(pos, 0.5) : 0;
      const pick = (f: (x: number) => boolean) => ys.filter((_, i) => f(xs[i]));
      groups = [
        { label: 'Día de descanso', ys: pick((x) => x === 0) },
        { label: 'Entreno suave', ys: pick((x) => x > 0 && x <= med) },
        { label: 'Entreno fuerte', ys: pick((x) => x > med) },
      ].filter((g) => g.ys.length >= 5).map((g) => ({ label: g.label, mean: meanOf(g.ys), n: g.ys.length }));
    } else {
      const s = [...xs].sort((a, b) => a - b);
      const q1 = quantile(s, 1 / 3);
      const q2 = quantile(s, 2 / 3);
      const pick = (f: (x: number) => boolean) => ys.filter((_, i) => f(xs[i]));
      groups = [
        { label: `${X.low} ${X.fmt(q1)}`, ys: pick((x) => x < q1) },
        { label: `${X.fmt(q1)} – ${X.fmt(q2)}`, ys: pick((x) => x >= q1 && x <= q2) },
        { label: `${X.high} ${X.fmt(q2)}`, ys: pick((x) => x > q2) },
      ].filter((g) => g.ys.length >= 5).map((g) => ({ label: g.label, mean: meanOf(g.ys), n: g.ys.length }));
    }

    const headline = strength === 'ninguna'
      ? `No se nota relación entre ${X.name} y ${Y.name}`
      : rho > 0 ? def.pos : def.neg;
    const lo = groups[0];
    const hi = groups[groups.length - 1];
    const summary = lo && hi && lo !== hi
      ? `${lo.label}: ${Y.fmt(lo.mean)} de media · ${hi.label}: ${Y.fmt(hi.mean)}`
      : '';
    out.push({ id: def.id, headline, context: def.context, rho, n: xs.length, strength, level, groups,
      cat: Y.cat, yName: Y.name, fmtY: Y.fmt, summary });
  }
  return out.sort((a, b) => Math.abs(b.rho) - Math.abs(a.rho));
}
