// Entrenos del plan → archivos FIT de entrenamiento (formato oficial de Garmin) para copiar al reloj.
import { Encoder, Profile } from '@garmin/fitsdk';
import { zipSync } from 'fflate';
import { stepPace, type PaceRef, type PlanSession } from './data';

type Refs = Partial<Record<PaceRef, number>> | null | undefined;
type WithWorkouts = PlanSession;

// Los tipos del SDK no recogen todos los campos del perfil FIT: se pasan como mensaje genérico.
const mesg = (o: Record<string, unknown>) => o as never;

/** Un archivo FIT de entrenamiento para una sesión (null si no tiene entreno estructurado). Los pasos con ritmo de
 * referencia usan tus ritmos ACTUALES (`refs`), así lo que llega al reloj está al día. */
export function sessionFit(s: WithWorkouts, refs?: Refs): Uint8Array | null {
  if (s.strength?.length) return strengthFit(s);
  if (!s.workout?.length) return null;
  const steps: Record<string, unknown>[] = [];
  for (const b of s.workout) {
    const first = steps.length;
    for (const st of b.steps) {
      const m: Record<string, unknown> = {
        messageIndex: steps.length, wktStepName: st.name.slice(0, 15), intensity: st.kind,
        durationType: st.duration, targetType: 'open',
      };
      // Valores en bruto del estándar FIT: tiempo en ms, distancia en cm, velocidad en mm/s, pulso en lpm + 100.
      if (st.duration === 'time' && st.value) m.durationValue = Math.round(st.value * 60) * 1000;  // segundos exactos
      if (st.duration === 'distance' && st.value) m.durationValue = Math.round(st.value * 1000 * 100);
      if (st.target === 'pace') {
        const rng = stepPace(st, refs);  // segundos por km (rápido, lento)
        if (rng) Object.assign(m, { targetType: 'speed', targetValue: 0,
          customTargetValueLow: Math.round((1000 / rng[1]) * 1000), customTargetValueHigh: Math.round((1000 / rng[0]) * 1000) });
      } else if (st.target === 'hr' && st.hr_low && st.hr_high) {
        Object.assign(m, { targetType: 'heartRate', targetValue: 0, customTargetValueLow: st.hr_low + 100, customTargetValueHigh: st.hr_high + 100 });
      }
      steps.push(m);
    }
    if (b.repeat > 1) {
      steps.push({ messageIndex: steps.length, durationType: 'repeatUntilStepsCmplt', durationValue: first, targetType: 'open', targetValue: b.repeat });
    }
  }
  const enc = new Encoder();
  enc.onMesg(Profile.MesgNum.FILE_ID, mesg({ type: 'workout', manufacturer: 'development', product: 0, timeCreated: new Date(), serialNumber: 20261030 }));
  const day = new Date(`${s.date}T00:00:00`).toLocaleDateString('es-ES', { weekday: 'short', day: 'numeric' }).replace('.', '');
  enc.onMesg(Profile.MesgNum.WORKOUT, mesg({ wktName: `${day} ${s.title}`.slice(0, 30), sport: 'running', subSport: 'generic', numValidSteps: steps.length }));
  for (const m of steps) enc.onMesg(Profile.MesgNum.WORKOUT_STEP, mesg(m));
  return enc.close();
}

/** Sesión de gimnasio: cada ejercicio es un bloque [serie, descanso] repetido tantas veces como series. */
function strengthFit(s: WithWorkouts): Uint8Array {
  const steps: Record<string, unknown>[] = [];
  for (const it of s.strength ?? []) {
    const first = steps.length;
    const ex: Record<string, unknown> = {
      messageIndex: steps.length, wktStepName: it.label.slice(0, 22), intensity: 'active', targetType: 'open',
      // Repeticiones (o tiempo en ejercicios como la plancha); el reloj pide confirmarlas al acabar la serie.
      ...(it.seconds ? { durationType: 'time', durationValue: Math.round(it.seconds) * 1000 } : { durationType: 'reps', durationValue: it.reps }),
    };
    if (it.category_id != null) ex.exerciseCategory = it.category_id;
    if (it.name_id != null) ex.exerciseName = it.name_id;
    if (it.weight_kg) { ex.exerciseWeight = it.weight_kg; ex.weightDisplayUnit = 'kilogram'; }  // el SDK aplica la escala (x100)
    steps.push(ex);
    if (it.rest_s > 0) steps.push({ messageIndex: steps.length, wktStepName: 'Descanso', intensity: 'rest', durationType: 'time', durationValue: it.rest_s * 1000, targetType: 'open' });
    if (it.sets > 1) steps.push({ messageIndex: steps.length, durationType: 'repeatUntilStepsCmplt', durationValue: first, targetType: 'open', targetValue: it.sets });
  }
  const enc = new Encoder();
  enc.onMesg(Profile.MesgNum.FILE_ID, mesg({ type: 'workout', manufacturer: 'development', product: 0, timeCreated: new Date(), serialNumber: 20261030 }));
  const day = new Date(`${s.date}T00:00:00`).toLocaleDateString('es-ES', { weekday: 'short', day: 'numeric' }).replace('.', '');
  enc.onMesg(Profile.MesgNum.WORKOUT, mesg({ wktName: `${day} ${s.title}`.slice(0, 30), sport: 'training', subSport: 'strengthTraining', numValidSteps: steps.length }));
  for (const m of steps) enc.onMesg(Profile.MesgNum.WORKOUT_STEP, mesg(m));
  return enc.close();
}

const fileName = (s: PlanSession) => `${s.date}-${s.title}`.normalize('NFD').replace(/[̀-ͯ]/g, '')
  .replace(/[^A-Za-z0-9-]+/g, '_').slice(0, 40) + '.fit';

function save(bytes: Uint8Array, name: string, type: string) {
  const url = URL.createObjectURL(new Blob([new Uint8Array(bytes)], { type }));
  const a = Object.assign(document.createElement('a'), { href: url, download: name });
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

export function downloadSession(s: PlanSession, refs?: Refs) {
  const f = sessionFit(s, refs);
  if (f) save(f, fileName(s), 'application/vnd.ant.fit');
}

/** Todas las sesiones de carrera de la semana con entreno, en un .zip. Devuelve cuántas. */
export function downloadWeek(sessions: PlanSession[], weekStart: string, refs?: Refs): number {
  const files: Record<string, Uint8Array> = {};
  for (const s of sessions) {
    if (s.type === 'swim') continue;  // la natación va en la descripción (sin archivo para el reloj)
    const f = sessionFit(s, refs);
    if (f) files[fileName(s)] = f;
  }
  const n = Object.keys(files).length;
  if (n) save(zipSync(files), `entrenos-semana-${weekStart}.zip`, 'application/zip');
  return n;
}
