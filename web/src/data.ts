import { useCallback, useEffect, useRef, useState } from 'react';

export interface Day {
  d: string;
  steps?: number; stepGoal?: number; walkKm?: number; floors?: number; cal?: number; calActive?: number;
  rhr?: number; hrMin?: number; hrMax?: number; imMod?: number; imVig?: number;
  stress?: number; stressHighH?: number; stressRestH?: number;
  bbMax?: number; bbMin?: number; bbNow?: number; bbCharged?: number; bbDrained?: number; resp?: number; spo2?: number;
  sleepH?: number; deepH?: number; remH?: number; lightH?: number; awakeH?: number; sleepScore?: number;
  sleepNeedH?: number; bed?: number; wake?: number; sleepStress?: number;
  hrv?: number; hrvLow?: number; hrvHigh?: number;
  load?: number; atl?: number; ctl?: number; tsb?: number; acwr?: number; ready?: number;
}

export interface Activity {
  id: number; start: string; name?: string; type: string; group: string;
  km?: number; min?: number; pace?: number; hr?: number; hrMax?: number; trimp?: number;
  ef?: number; dec?: number; vo2?: number; cad?: number; elev?: number; cal?: number;
  z: number[]; pr?: boolean; swolf?: number; poolM?: number;
  sets?: { ex: string; reps: number; kg?: number | null; dur?: number }[] | null;
}

export interface Prediction {
  distance: string; predicted: number; pace?: number; best?: number; bestDate?: string; best90?: number;
}

export interface Relation { a: string; b: string; rho?: number; n: number; strength: string }

export interface Readiness {
  date: string; score: number; label: string; message: string;
  parts: { key: string; label: string; score: number; detail: string }[];
}
export interface Alert { id: string; date: string; category: AiCategory; level: 'info' | 'attention'; title: string; body: string }
export interface WeekStats {
  start: string; end: string; daysWorn: number; sleepH?: number | null; sleepScore?: number | null; steps?: number | null;
  rhr?: number | null; hrv?: number | null; stress?: number | null; bbMax?: number | null; intensity?: number | null;
  sessions: number; hours?: number | null; runKm?: number | null; load?: number | null; nightsUnder7?: number | null;
}
export interface Weekly {
  week: string; title?: string; went_well?: string[]; worse?: string[]; goal?: string; generatedAt?: string;
  last: WeekStats; previous: WeekStats;
}
export interface RecordItem {
  group: string; label: string; value: number; kind: 'time' | 'km' | 'vo2' | 'steps' | 'score' | 'bpm' | 'ms'; date: string; activityId?: number;
}
export interface ActivityDetail {
  id: number; cols: string[]; series: (number | null)[][]; track: [number, number][];
  splits: { km: number; time: number; pace: number; hr?: number; elev?: number | null }[];
  laps: { time: number; dist: number; hr?: number; speed?: number; ascent?: number }[];
  zones: number[]; zoneFloors?: number[]; elevGain?: number; minHr?: number; recoveryHr?: number;
  stride?: number; gct?: number; vertOsc?: number; power?: number; location?: string; teLabel?: string;
}

export type SessionType = 'easy' | 'long' | 'tempo' | 'intervals' | 'race' | 'strength' | 'swim' | 'cross' | 'rest';
export type PaceRef = 'easy' | 'marathon' | 'half' | '10k' | '5k' | 'threshold' | 'interval' | 'repetition';
export interface WorkoutStep {
  kind: 'warmup' | 'active' | 'recovery' | 'cooldown' | 'rest';
  duration: 'distance' | 'time' | 'open'; value?: number | null;
  target: 'pace' | 'hr' | 'open'; pace_fast?: string | null; pace_slow?: string | null;
  hr_low?: number | null; hr_high?: number | null; name: string;
  pace_ref?: PaceRef | null; pace_ref_offset_s?: number | null;
}
export interface WorkoutBlock { repeat: number; steps: WorkoutStep[] }
export interface StrengthItem {
  label: string; category_id: number | null; name_id: number | null; sets: number; reps: number;
  seconds?: number | null; weight_kg?: number | null; rest_s: number;
}
export interface Compliance {
  distRatio?: number; timeRatio?: number; paceDeltaS?: number; setsDone?: number; setsPlanned?: number; setsRatio?: number;
}
export interface PlanSession {
  date: string; type: SessionType; title: string; distance_km?: number | null; duration_min?: number | null;
  target: string; description: string;
  status: 'done' | 'partial' | 'missed' | 'today' | 'upcoming' | 'rest';
  actual?: { id: number; km: number; min: number; pace?: number; hr?: number; name?: string } | null;
  feedback?: { rating: number; note: string } | null;
  compliance?: Compliance | null;
  workout?: WorkoutBlock[] | null; strength?: StrengthItem[] | null;
}
export interface PlanWeek { start: string; focus: string; sessions: PlanSession[]; plannedKm: number; actualKm: number; compliance?: number | null }
export interface Plan {
  goal: string; raceDate: string; goalTime?: string | null; daysPerWeek: number; longRunDay: string; notes?: string;
  gymDays?: number; bodyGoal?: string | null; ambition?: 'realista' | 'exigente';
  createdAt: string; updatedAt: string; summary: string; weeks: PlanWeek[];
  memory: (string | { topic: string; title: string; detail: string })[];
  history: { at: string; kind: 'create' | 'adapt'; message: string; changes?: string[]; cost: number }[];
}
export interface CoachView {
  plan: Plan | null; today: { session: PlanSession; tip?: string | null } | null;
  job?: { status: 'running' | 'done' | 'error' | 'cancelled'; action: string; error?: string; at: number; cancel?: boolean } | null;
}

export type AiCategory = 'activity' | 'heart' | 'sleep' | 'stress' | 'recovery' | 'energy' | 'training';
export interface AiCard { category: AiCategory; tone: 'positive' | 'neutral' | 'attention'; title: string; body: string }
export interface AiInsights {
  model: string; generatedAt: string; headline: string; today: AiCard[];
  sleep: string[]; heart: string[]; activity: string[]; training: string[]; weekly_focus: string;
  analysis?: string[]; data_note?: string;
}

export interface AiUsage {
  model: string; calls: number; inputTokens: number; outputTokens: number; costUsd: number;
  first?: string | null; last?: string | null; avgCostUsd?: number | null; maxCallsPerDay: number;
  byDay: { day: string; calls: number; cost: number }[];
  byKind?: { kind: string; calls: number; cost: number; model: string }[];
  monthCostUsd?: number; monthlyBudgetUsd?: number; safeLimitUsd?: number;
}

/** Lo último que ha mandado el reloj hoy (Body Battery actual, curvas y la hora del último dato). */
export interface Live {
  date: string; asOf?: string; bbNow?: number; bbMax?: number; bbMin?: number; bbCharged?: number; bbDrained?: number;
  bbSeries?: [string, number][]; bbFeedback?: string; hrLast?: number; hrLastAt?: string; hrSeries?: [string, number][]; respNow?: number;
}
export interface PaceZone { zone: number; name: string; fast: number; slow: number }
export interface Paces {
  vdot: number; source: 'race' | 'recent' | 'watch'; sourceLabel: string; sourceDate?: string | null; stale: boolean;
  others: { kind: string; vdot: number; label: string }[];
  refs: Record<PaceRef, number>; easyRange: [number, number];
  list: { key: PaceRef; label: string; use: string; sec: number }[];
  zones: PaceZone[]; races: { distance: string; time: number }[];
  test?: { distance_m: number; time_s: number; date: string } | null;
}
export interface SwimSession { id: number; d: string; m: number; min?: number; pace?: number | null; swolf?: number | null; pool?: number | null; open?: boolean }
export interface Swim {
  css?: number | null; cssSource?: 'test' | 'estimate' | null; test?: { t400_s: number; t200_s: number; date: string } | null;
  poolM: number; zones: PaceZone[]; weeks: { start: string; m: number; sessions: number }[]; sessions: SwimSession[];
  best?: { d: string; m: number; pace: number; id: number } | null; longest?: SwimSession | null;
  totals: { sessions: number; km: number; sessions90: number; km90: number };
}
export interface GymRecord {
  ex: string; muscle?: string | null; label: string; sets: number; maxReps: number; last?: string;
  best?: { e1rm: number; kg: number; reps: number; d: string; id: number } | null;
  maxKg?: { kg: number; reps: number; d: string; id: number } | null;
  trend: { d: string; e1rm: number }[];
}
export interface Gym {
  weeks: { start: string; sessions: number; sets: number; kg: number; muscles: Record<string, number> }[];
  records: GymRecord[]; muscleAvg4w: { muscle: string; label: string; sets: number }[];
  muscles: { key: string; label: string }[]; totals: { sessions: number; withSets: number; sets: number };
}
export interface WellnessDay { d: string; mood?: number; soreness?: number; note?: string }
export interface Injury { id: string; area: string; severity: number; start: string; end?: string | null; notes?: string }
export interface Wellness { today?: WellnessDay | null; recent: WellnessDay[]; injuries: Injury[] }

export interface GarminData {
  generatedAt: string;
  lastSync?: string;
  period: { start: string; end: string };
  profile: { max_hr?: number; rest_hr?: number; age?: number; fitness_age?: number;
    achievable_fitness_age?: number; zones?: number[] };
  days: Day[];
  activities: Activity[];
  insights: Record<'datos' | 'sueno' | 'corazon' | 'entreno' | 'carrera' | 'relaciones' | 'acciones', string[]>;
  relations: Relation[];
  predictions: Prediction[];
  ai?: AiInsights | null;
  appBuild?: string;
  aiUsage?: AiUsage;
  coverage?: { month: string; worn: number; days: number }[];
  readiness?: Readiness | null;
  alerts?: Alert[];
  weeks?: { current: WeekStats; last: WeekStats; previous: WeekStats };
  weekly?: Weekly | null;
  records?: RecordItem[];
  coach?: CoachView;
  weights?: { d: string; kg: number; fat?: number; muscle?: number }[];
  push?: { vapidPublicKey?: string | null } | null;
  live?: Live | null;
  paces?: Paces | null;
  swim?: Swim | null;
  gym?: Gym | null;
  wellness?: Wellness | null;
}

/** Pide a la app que vuelva a leer data.js (la API ya lo ha actualizado tras un cambio). */
export const refreshData = () => window.dispatchEvent(new Event('gs-refresh'));

/** s → "m:ss". */
export const mmss = (sec?: number | null) => {
  if (sec == null || !isFinite(sec)) return '–';
  const s = Math.round(sec);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
};

/** Rango de ritmo (rápido, lento) en s/km de un paso: con su ritmo de referencia (si lo tiene) y tus ritmos actuales. */
export function stepPace(st: WorkoutStep, refs?: Partial<Record<PaceRef, number>> | null): [number, number] | null {
  if (st.pace_ref && refs?.[st.pace_ref]) {
    const base = refs[st.pace_ref]! + (st.pace_ref_offset_s ?? 0);
    const m = st.pace_ref === 'easy' ? 12 : 5;
    return [base - m, base + m];
  }
  const sec = (p?: string | null) => {
    if (!p || !p.includes(':')) return null;
    const [m, s] = p.split(':').map(Number);
    return Number.isFinite(m) && Number.isFinite(s) ? m * 60 + s : null;
  };
  const f = sec(st.pace_fast), s = sec(st.pace_slow);
  return f && s ? [Math.min(f, s), Math.max(f, s)] : null;
}

declare global {
  interface Window { __GARMIN__?: GarminData; __ACTS__?: Record<number, ActivityDetail> }
}

/**
 * Lee window.__GARMIN__ (cargado por data.js) y vuelve a cargar data.js cada `intervalMs`
 * y al volver a la pestaña. Funciona también abriendo el HTML como archivo (file://),
 * porque usa <script> y no fetch.
 */
export function useGarminData(intervalMs = 60_000) {
  const [data, setData] = useState<GarminData | undefined>(() => window.__GARMIN__);
  const [checking, setChecking] = useState(false);
  const [fresh, setFresh] = useState(false);
  const [lastCheck, setLastCheck] = useState(() => new Date());
  const current = useRef(data?.generatedAt);

  const check = useCallback(() => new Promise<GarminData | undefined>((resolve) => {
    setChecking(true);
    const s = document.createElement('script');
    s.src = `./data.js?t=${Date.now()}`;
    const done = () => {
      s.remove();
      setChecking(false);
      setLastCheck(new Date());
      const d = window.__GARMIN__;
      // Hay una versión MÁS NUEVA de la página: recargar para usarla. Nunca hacia atrás y como mucho una
      // vez cada 5 minutos, para que no pueda entrar en bucle si los datos aún no conocen la versión nueva.
      if (d?.appBuild && Number(d.appBuild) > Number(__BUILD_ID__)) {
        let last = 0;
        try { last = Number(sessionStorage.getItem('gs-reload') ?? 0); } catch { /* sin almacenamiento */ }
        if (Date.now() - last > 5 * 60_000) {
          try { sessionStorage.setItem('gs-reload', String(Date.now())); } catch { /* sin almacenamiento */ }
          window.location.reload();
          resolve(d);
          return;
        }
      }
      if (d && d.generatedAt !== current.current) {
        const first = current.current === undefined;
        current.current = d.generatedAt;
        setData(d);
        if (!first) setFresh(true);
      }
      resolve(d);
    };
    s.onload = done;
    s.onerror = done;
    document.head.appendChild(s);
  }), []);

  useEffect(() => {
    const id = window.setInterval(check, intervalMs);
    const onVis = () => document.visibilityState === 'visible' && check();
    document.addEventListener('visibilitychange', onVis);
    return () => {
      window.clearInterval(id);
      document.removeEventListener('visibilitychange', onVis);
    };
  }, [check, intervalMs]);

  return { data, checking, fresh, clearFresh: () => setFresh(false), check, lastCheck };
}

/** Re-render cada `ms` para textos tipo "hace 5 min". */
export function useNow(ms = 30_000) {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), ms);
    return () => window.clearInterval(id);
  }, [ms]);
  return now;
}

// ------------------------------------------------------------------ utilidades de series
export type Range = '7d' | '30d' | '90d' | '1y' | 'all';
export const RANGES: { value: Range; label: string; days: number }[] = [
  { value: '7d', label: '7 días', days: 7 },
  { value: '30d', label: '30 días', days: 30 },
  { value: '90d', label: '3 meses', days: 90 },
  { value: '1y', label: '1 año', days: 365 },
  { value: 'all', label: 'Todo', days: 100_000 },
];

export const toDate = (iso: string) => new Date(`${iso}T00:00:00`);
/** Fecha local AAAA-MM-DD (toISOString usaría UTC y movería el día). */
export const isoLocal = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;

export function sliceRange<T extends { d: string }>(rows: T[], range: Range, endIso?: string): T[] {
  const days = RANGES.find((r) => r.value === range)!.days;
  const end = toDate(endIso ?? rows[rows.length - 1]?.d ?? isoLocal(new Date()));
  const start = new Date(end);
  start.setDate(start.getDate() - days + 1);
  return rows.filter((r) => toDate(r.d) >= start && toDate(r.d) <= end);
}

/** Media móvil de n días (ignora vacíos; necesita al menos minP valores). */
export function rolling(values: (number | undefined | null)[], n: number, minP = Math.ceil(n / 3)) {
  return values.map((_, i) => {
    const w = values.slice(Math.max(0, i - n + 1), i + 1).filter((v): v is number => v != null);
    return w.length >= minP ? w.reduce((a, b) => a + b, 0) / w.length : null;
  });
}

/** Agrupa por semana (lunes) y calcula la media o la suma de cada campo. */
export function weekly<T extends { d: string }>(
  rows: T[], fields: (keyof T)[], how: 'mean' | 'sum' = 'mean',
): { d: string; [k: string]: number | string | null }[] {
  const groups = new Map<string, T[]>();
  for (const r of rows) {
    const dt = toDate(r.d);
    const monday = new Date(dt);
    monday.setDate(dt.getDate() - ((dt.getDay() + 6) % 7));
    const k = isoLocal(monday);
    if (!groups.has(k)) groups.set(k, []);
    groups.get(k)!.push(r);
  }
  return [...groups.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([d, rs]) => {
    const out: { d: string; [k: string]: number | string | null } = { d };
    for (const f of fields) {
      const v = rs.map((r) => r[f] as unknown as number | undefined).filter((x): x is number => x != null);
      out[f as string] = v.length ? (how === 'sum' ? v.reduce((a, b) => a + b, 0) : v.reduce((a, b) => a + b, 0) / v.length) : null;
    }
    return out;
  });
}

export function mean(values: (number | undefined | null)[]) {
  const v = values.filter((x): x is number => x != null);
  return v.length ? v.reduce((a, b) => a + b, 0) / v.length : undefined;
}

export function lastWith<T>(rows: T[], pick: (r: T) => unknown): T | undefined {
  for (let i = rows.length - 1; i >= 0; i--) if (pick(rows[i]) != null) return rows[i];
  return undefined;
}

/** Carga el detalle de una actividad (site/acts/<id>.js) con <script>, válido también en file://. */
export function loadActivity(id: number): Promise<ActivityDetail | null> {
  const have = window.__ACTS__?.[id];
  if (have) return Promise.resolve(have);
  return new Promise((resolve) => {
    const s = document.createElement('script');
    s.src = `./acts/${id}.js?t=${Date.now()}`;
    s.onload = () => { s.remove(); resolve(window.__ACTS__?.[id] ?? null); };
    s.onerror = () => { s.remove(); resolve(null); };
    document.head.appendChild(s);
  });
}

/** Rachas de días seguidos que cumplen `ok` (los días sin datos rompen la racha, salvo hoy). */
export function streaks(days: Day[], ok: (d: Day) => boolean | null) {
  let best = 0, run = 0;
  for (const d of days) {
    const v = ok(d);
    if (v) { run += 1; best = Math.max(best, run); } else run = 0;
  }
  // racha actual: desde el final hacia atrás, ignorando el último día si aún no tiene dato
  let cur = 0;
  for (let i = days.length - 1; i >= 0; i--) {
    const v = ok(days[i]);
    if (v == null && i === days.length - 1) continue;
    if (v) cur += 1; else break;
  }
  return { current: cur, best };
}
