// "Lo importante": 2-3 datos clave arriba de cada página. Filas limpias: dato grande en el color de su
// categoría y una nota que se tiñe de verde (bien) o terracota (ojo). Todo sale de los datos (sin IA).
import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import Typography from '@mui/material/Typography';
import { mean, mmss, type Day, type GarminData } from './data';
import { dateShort, dec1, duration, hm, int } from './format';
import { CATEGORY, useResolvedMode, type Category } from './theme';
import { CARD_SX } from './ui';

type Tone = 'good' | 'watch' | 'neutral';
export interface Fact { cat: Category; label: string; value: string; unit?: string; note: string; tone: Tone }

const TONE = { good: { light: '#146C2E', dark: '#6DD58C' }, watch: { light: '#D4542F', dark: '#F08A66' } };
const ORDER: Record<Tone, number> = { watch: 0, good: 1, neutral: 2 };

export function KeyFacts({ facts }: { facts: (Fact | null)[] }) {
  const mode = useResolvedMode();
  const list = facts.filter((f): f is Fact => !!f).sort((a, b) => ORDER[a.tone] - ORDER[b.tone]).slice(0, 3);
  if (!list.length) return null;
  return (
    <Card sx={{ ...CARD_SX, mb: { xs: 2.5, sm: 3 }, px: { xs: 2, sm: 2.5 }, py: { xs: 1.5, sm: 2 } }}>
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', fontWeight: 600 }}>LO IMPORTANTE</Typography>
      <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: `repeat(${list.length}, 1fr)` }, columnGap: 3 }}>
        {list.map((f, k) => (
          <Box key={f.label} sx={{ display: 'flex', alignItems: 'center', gap: 2, py: 1.25,
            borderTopStyle: 'solid', borderTopColor: 'divider', borderTopWidth: { xs: k ? '1px' : 0, md: 0 } }}>
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <Typography variant="body2" color="text.secondary">{f.label}</Typography>
              <Typography variant="body2" sx={{ mt: 0.25, lineHeight: 1.35, fontWeight: f.tone === 'neutral' ? 400 : 500,
                color: f.tone === 'neutral' ? 'text.primary' : TONE[f.tone][mode] }}>{f.note}</Typography>
            </Box>
            <Typography sx={{ flexShrink: 0, fontSize: 26, fontWeight: 600, lineHeight: 1, letterSpacing: '-0.01em',
              color: CATEGORY[f.cat][mode], fontVariantNumeric: 'tabular-nums' }}>
              {f.value}
              {f.unit && <Typography component="span" variant="caption" sx={{ ml: 0.5, letterSpacing: 0, color: "text.secondary", fontWeight: 400 }}>{f.unit}</Typography>}
            </Typography>
          </Box>
        ))}
      </Box>
    </Card>
  );
}

// ---------------------------------------------------------------- datos de cada página

const lastWith = (days: Day[], k: keyof Day) => [...days].reverse().find((d) => d[k] != null);
/** Último día completo (hoy va a medias): el último con pasos que no sea hoy. */
const lastFull = (days: Day[]) => {
  const today = new Date().toISOString().slice(0, 10);
  return [...days].reverse().find((d) => d.d < today && d.steps != null);
};
const avgOf = (days: Day[], k: keyof Day, n: number, skip = 0) =>
  mean(days.slice(Math.max(0, days.length - n - skip), days.length - skip).map((d) => d[k] as number | undefined));

export function sleepFacts(data: GarminData): (Fact | null)[] {
  const days = data.days;
  const night = lastWith(days, 'sleepH');
  const last7 = days.slice(-7).filter((d) => d.sleepH != null);
  const avg7 = mean(last7.map((d) => d.sleepH));
  const under = last7.filter((d) => (d.sleepH ?? 0) < 7).length;
  const score7 = mean(last7.map((d) => d.sleepScore));
  return [
    night ? { cat: 'sleep', label: 'Anoche', value: hm(night.sleepH).replace(' min', ''), tone: (night.sleepH ?? 0) >= 7 ? 'good' : 'watch',
      note: (night.sleepH ?? 0) >= 7 ? `Por encima de las 7 h recomendadas${night.sleepScore ? ` · nota ${night.sleepScore}` : ''}` : `Menos de las 7 h recomendadas${night.sleepScore ? ` · nota ${night.sleepScore}` : ''}` } : null,
    avg7 != null ? { cat: 'sleep', label: 'Últimas 7 noches', value: hm(avg7).replace(' min', ''), tone: under >= 4 ? 'watch' : under <= 1 ? 'good' : 'neutral',
      note: under ? `${under} de ${last7.length} noches por debajo de 7 h` : 'Todas las noches por encima de 7 h' } : null,
    score7 != null ? { cat: 'sleep', label: 'Calidad media', value: int(score7), unit: '/ 100', tone: score7 >= 80 ? 'good' : score7 < 65 ? 'watch' : 'neutral',
      note: score7 >= 80 ? 'Dormir bien te está saliendo' : score7 < 65 ? 'Sueño poco reparador estos días' : 'Correcta, con margen para mejorar' } : null,
  ];
}

export function heartFacts(data: GarminData): (Fact | null)[] {
  const days = data.days;
  const r = lastWith(days, 'rhr');
  const rhr30 = avgOf(days, 'rhr', 30, 1);
  const dr = r?.rhr != null && rhr30 != null ? r.rhr - rhr30 : null;
  const h = lastWith(days, 'hrv');
  const full = lastFull(days);
  return [
    r && dr != null ? { cat: 'heart', label: 'Pulso en reposo', value: int(r.rhr), unit: 'lpm', tone: dr >= 3 ? 'watch' : dr <= -1 ? 'good' : 'neutral',
      note: dr >= 3 ? `${int(dr)} lpm por encima de tu normal: cansancio, poco sueño o algo que se incuba`
        : dr <= -1 ? `${int(-dr)} lpm por debajo de tu normal: buena señal` : 'En tu normal del último mes' } : null,
    h?.hrv != null ? { cat: 'recovery', label: 'HRV de anoche', value: int(h.hrv), unit: 'ms',
      tone: h.hrvLow != null && h.hrv < h.hrvLow ? 'watch' : h.hrvLow != null ? 'good' : 'neutral',
      note: h.hrvLow != null && h.hrv < h.hrvLow ? 'Por debajo de tu rango: el cuerpo pide calma'
        : h.hrvHigh != null && h.hrv > h.hrvHigh ? 'Por encima de tu rango' : h.hrvLow != null ? 'Dentro de tu rango: recuperas bien' : 'Compárala solo contigo' } : null,
    full?.stress != null ? { cat: 'stress', label: 'Estrés de ayer', value: int(full.stress), unit: '/ 100', tone: full.stress >= 50 ? 'watch' : full.stress <= 30 ? 'good' : 'neutral',
      note: full.stress >= 50 ? 'Día exigente: busca un rato de calma hoy' : full.stress <= 30 ? 'Día tranquilo' : 'Estrés moderado' } : null,
  ];
}

export function activityFacts(data: GarminData): (Fact | null)[] {
  const days = data.days;
  const full = lastFull(days);
  const goal = full?.stepGoal ?? 10000;
  const im = days.slice(-7).reduce((s, d) => s + (d.imMod ?? 0) + 2 * (d.imVig ?? 0), 0);
  const steps7 = avgOf(days, 'steps', 7, 1);
  return [
    full?.steps != null ? { cat: 'activity', label: 'Pasos de ayer', value: int(full.steps), tone: full.steps >= goal ? 'good' : full.steps < goal * 0.6 ? 'watch' : 'neutral',
      note: full.steps >= goal ? 'Objetivo cumplido' : `Te faltaron ${int(goal - full.steps)} para el objetivo` } : null,
    { cat: 'activity', label: 'Intensidad · 7 días', value: int(im), unit: '/ 150', tone: im >= 150 ? 'good' : im < 75 ? 'watch' : 'neutral',
      note: im >= 150 ? 'Cumples lo que recomienda la OMS' : `Te faltan ${int(150 - im)} min esta semana` },
    steps7 != null ? { cat: 'activity', label: 'Media de pasos', value: int(steps7), tone: 'neutral', note: 'Últimos 7 días completos' } : null,
  ];
}

export function trainingFacts(data: GarminData): (Fact | null)[] {
  const days = data.days;
  const load = lastWith(days, 'acwr');
  const since = Date.now() - 7 * 864e5;
  const week = data.activities.filter((a) => new Date(a.start).getTime() >= since);
  const km = week.reduce((s, a) => s + (a.group === 'Correr' || a.group === 'Cinta' ? a.km ?? 0 : 0), 0);
  // Solo carrera: caminar o el gimnasio dan estimaciones de VO2max que no valen
  const vo2s = data.activities.filter((a) => a.vo2 != null && (a.group === 'Correr' || a.group === 'Cinta'));
  const vo2 = vo2s[vo2s.length - 1];
  const old = vo2s.filter((a) => new Date(a.start).getTime() <= Date.now() - 60 * 864e5).pop();
  const dv = vo2?.vo2 != null && old?.vo2 != null ? vo2.vo2 - old.vo2 : null;
  const a = load?.acwr;
  return [
    a != null ? { cat: 'training', label: 'Carga', value: dec1(a), unit: '× tu media',
      tone: a > 1.5 ? 'watch' : a >= 0.8 && a <= 1.3 ? 'good' : 'neutral',
      note: a > 1.5 ? 'Has subido muy de golpe: mete un día suave' : a > 1.3 ? 'Subiendo: vigila el cansancio'
        : a >= 0.8 ? 'Zona segura para progresar' : 'Por debajo de lo habitual: puedes subir poco a poco' } : null,
    { cat: 'training', label: 'Últimos 7 días', value: String(week.length), unit: week.length === 1 ? 'sesión' : 'sesiones', tone: week.length ? 'neutral' : 'watch',
      note: week.length ? (km ? `${dec1(km)} km corriendo` : 'Sin carrera esta semana') : 'Ningún entreno esta semana' },
    vo2?.vo2 != null ? { cat: 'energy', label: 'VO2max', value: dec1(vo2.vo2), tone: dv != null && dv >= 0.5 ? 'good' : dv != null && dv <= -1 ? 'watch' : 'neutral',
      note: dv == null ? 'Tu forma aeróbica según el reloj' : dv >= 0.5 ? `+${dec1(dv)} en 2 meses: estás en mejor forma` : dv <= -1 ? `${dec1(dv)} en 2 meses` : 'Estable en los últimos 2 meses' } : null,
  ];
}

const RUN = (g: string) => g === 'Correr' || g === 'Cinta';
const daysAgo = (n: number) => Date.now() - n * 864e5;
const pctChange = (now: number, before: number) => (before > 0 ? ((now - before) / before) * 100 : null);

export function pacesFacts(data: GarminData): (Fact | null)[] {
  const p = data.paces;
  const runs = data.activities.filter((a) => RUN(a.group) && new Date(a.start).getTime() >= daysAgo(14));
  const total = runs.reduce((s, a) => s + a.z.reduce((x, v) => x + v, 0), 0);
  const easy = runs.reduce((s, a) => s + (a.z[0] ?? 0) + (a.z[1] ?? 0), 0);
  const pct = total >= 30 ? (easy / total) * 100 : null;
  return [
    pct != null ? { cat: 'heart', label: 'Tiempo suave · 14 días', value: int(pct), unit: '%', tone: pct >= 75 ? 'good' : pct < 60 ? 'watch' : 'neutral',
      note: pct >= 75 ? 'Ruedas suave de verdad: así se gana fondo' : pct < 60 ? 'Mucho tiempo en zonas altas: los rodajes, más lentos' : 'Cerca: lo ideal es un 80 % en zonas 1-2' } : null,
    p ? { cat: 'training', label: 'Rodaje', value: `${mmss(p.easyRange[0])}–${mmss(p.easyRange[1])}`, unit: '/km', tone: 'neutral', note: 'Tu ritmo para la mayoría de salidas' } : null,
    p?.stale ? { cat: 'training', label: 'Tu nivel', value: dec1(p.vdot), unit: 'VDOT', tone: 'watch', note: 'Marca de hace más de 6 meses: pon una reciente' }
      : p ? { cat: 'training', label: 'Umbral', value: mmss(p.refs.threshold), unit: '/km', tone: 'neutral', note: 'Para tempo y series largas' } : null,
  ];
}

export function gymFacts(data: GarminData): (Fact | null)[] {
  const g = data.gym;
  if (!g) return [];
  // El lunes la semana va a cero: entonces se enseña la semana pasada
  const thisWeek = g.weeks[g.weeks.length - 1];
  const usePrev = !!thisWeek && thisWeek.sets === 0 && g.weeks.length > 1;
  const end = g.weeks.length - (usePrev ? 1 : 0);
  const w = g.weeks[end - 1];
  const prev = g.weeks.slice(Math.max(0, end - 5), end - 1);
  const avg = prev.length ? prev.reduce((s, x) => s + x.sets, 0) / prev.length : null;
  const low = [...g.muscleAvg4w].filter((m) => m.sets < 6).sort((a, b) => a.sets - b.sets)[0];
  const rec = g.records.filter((r) => r.best && new Date(r.best.d).getTime() >= daysAgo(30))
    .sort((a, b) => (b.best!.d).localeCompare(a.best!.d))[0];
  return [
    rec?.best ? { cat: 'training', label: `Récord en ${rec.label.toLowerCase()}`, value: int(rec.best.e1rm), unit: 'kg', tone: 'good',
      note: `1RM estimado con ${dec1(rec.best.kg).replace(',0', '')} kg × ${rec.best.reps}` } : null,
    low ? { cat: 'training', label: low.label, value: dec1(low.sets), unit: 'series/sem', tone: 'watch', note: 'Por debajo de 6 a la semana: añade alguna serie' } : null,
    w ? { cat: 'training', label: usePrev ? 'Semana pasada' : 'Esta semana', value: int(w.sets), unit: w.sets === 1 ? 'serie' : 'series', tone: 'neutral',
      note: avg != null ? `Tu media: ${int(avg)} series por semana` : `${w.sessions} sesiones` } : null,
  ];
}

export function progressFacts(data: GarminData): (Fact | null)[] {
  const inRange = (a: { start: string }, from: number, to: number) => { const t = new Date(a.start).getTime(); return t >= from && t < to; };
  const now = Date.now();
  const cur = data.activities.filter((a) => inRange(a, daysAgo(30), now + 864e5));
  const old = data.activities.filter((a) => inRange(a, daysAgo(60), daysAgo(30)));
  const km = (l: typeof cur) => l.reduce((s, a) => s + (RUN(a.group) ? a.km ?? 0 : 0), 0);
  const dKm = pctChange(km(cur), km(old));
  const dN = pctChange(cur.length, old.length);
  const rec = (data.records ?? []).filter((r) => new Date(r.date).getTime() >= daysAgo(30)).sort((a, b) => b.date.localeCompare(a.date))[0];
  const recValue = (r: NonNullable<typeof rec>) => r.kind === 'time' ? duration(r.value) : r.kind === 'km' || r.kind === 'vo2' ? dec1(r.value) : int(r.value);
  const recUnit: Record<string, string> = { km: 'km', steps: 'pasos', score: '/ 100', bpm: 'lpm', ms: 'ms' };
  const trend = (d: number | null): Tone => d == null ? 'neutral' : d >= 10 ? 'good' : d <= -30 ? 'watch' : 'neutral';
  const vs = (d: number | null) => `${d != null && d > 0 ? '+' : ''}${int(d)} % frente a los 30 días anteriores`;
  return [
    rec ? { cat: 'training', label: `Récord: ${rec.label.toLowerCase()}`, value: recValue(rec), unit: recUnit[rec.kind], tone: 'good',
      note: `Lo conseguiste el ${dateShort(new Date(rec.date))}` } : null,
    // Sin mes anterior con el que comparar, el bloque de abajo ya lo cuenta: no se repite
    dKm != null ? { cat: 'training', label: 'Km corriendo · 30 días', value: dec1(km(cur)), unit: 'km', tone: trend(dKm), note: vs(dKm) } : null,
    dN != null ? { cat: 'activity', label: 'Entrenos · 30 días', value: int(cur.length), tone: trend(dN), note: vs(dN) } : null,
  ];
}
