// Ficha de un entreno del plan: perfil de intensidad, cada parte bien marcada (calentamiento, series, recuperaciones,
// vuelta a la calma) con ritmos, pulso y duración, lo que hiciste y el botón "Hacerlo hoy".
import { useState, type ReactNode } from 'react';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import IconButton from '@mui/material/IconButton';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { alpha } from '@mui/material/styles';
import CloseRounded from '@mui/icons-material/CloseRounded';
import ReplayRounded from '@mui/icons-material/ReplayRounded';
import UndoRounded from '@mui/icons-material/UndoRounded';
import OpenInNewRounded from '@mui/icons-material/OpenInNewRounded';
import { mmss, stepPace, toDate, type PaceRef, type PlanSession, type SessionType, type WorkoutStep } from './data';
import { dec1, pace } from './format';
import { useResolvedMode } from './theme';
import { Rich } from './rich';
import { BRAND, BRAND_DARK, BRAND_INK, brandTint } from './brand/colors';

export type Refs = Partial<Record<PaceRef, number>> | null | undefined;

export const SESSION_TYPE: Record<SessionType, { label: string; light: string; dark: string }> = {
  easy: { label: 'Suave', light: '#188038', dark: '#81C995' },
  long: { label: 'Tirada larga', light: '#1A73E8', dark: '#8AB4F8' },
  tempo: { label: 'Ritmo', light: '#E8710A', dark: '#FCAD70' },
  intervals: { label: 'Series', light: '#D93025', dark: '#F28B82' },
  race: { label: 'Carrera', light: '#5B5BD6', dark: '#AFADFF' },
  strength: { label: 'Fuerza', light: '#9334E6', dark: '#D7AEFB' },
  swim: { label: 'Natación', light: '#00838F', dark: '#78D9EC' },
  cross: { label: 'Cruzado', light: '#00838F', dark: '#78D9EC' },
  rest: { label: 'Descanso', light: '#80868B', dark: '#9AA0A6' },
};

const KIND_LABEL: Record<WorkoutStep['kind'], string> = {
  warmup: 'Calentamiento', active: 'Esfuerzo', recovery: 'Recuperación', cooldown: 'Vuelta a la calma', rest: 'Descanso',
};
const REF_NAME: Record<string, string> = {
  easy: 'suave', marathon: 'de maratón', half: 'de media', '10k': 'de 10K', '5k': 'de 5K', threshold: 'umbral',
  interval: 'de series', repetition: 'de repeticiones',
};
/** Intensidad de 1 (muy suave) a 5 (máxima) según el ritmo de referencia del paso. */
const REF_LEVEL: Record<string, number> = { easy: 1.6, marathon: 2.4, half: 2.8, '10k': 3.3, threshold: 3.3, '5k': 3.8, interval: 4.2, repetition: 4.8 };

interface Flat { st: WorkoutStep; sec: number; km: number; level: number; rep?: { i: number; n: number } }

/** Segundos por km de un paso: su rango de ritmo, o tu ritmo suave si va por pulso o libre. */
function stepSecKm(st: WorkoutStep, refs: Refs): number | null {
  const r = stepPace(st, refs);
  if (r) return (r[0] + r[1]) / 2;
  return refs?.easy ?? null;
}

function level(st: WorkoutStep, refs: Refs): number {
  if (st.kind === 'recovery' || st.kind === 'rest') return 0.8;
  if (st.kind === 'warmup' || st.kind === 'cooldown') return 1.2;
  if (st.pace_ref) return REF_LEVEL[st.pace_ref] ?? 3;
  const r = stepPace(st, refs);
  if (r && refs?.easy && refs?.interval) {
    const p = (r[0] + r[1]) / 2;
    return Math.max(1.4, Math.min(4.8, 1.6 + ((refs.easy - p) / (refs.easy - refs.interval)) * 2.6));
  }
  if (st.target === 'hr' && st.hr_high) return st.hr_high >= 165 ? 4 : st.hr_high >= 150 ? 3 : 1.8;
  return 2.5;
}

function flatten(s: PlanSession, refs: Refs): Flat[] {
  const out: Flat[] = [];
  for (const b of s.workout ?? []) {
    const n = Math.max(1, b.repeat || 1);
    for (let i = 0; i < n; i++) {
      for (const st of b.steps) {
        const sk = stepSecKm(st, refs);
        let sec = 0, km = 0;
        if (st.duration === 'time' && st.value) { sec = st.value * 60; km = sk ? sec / sk : 0; }
        else if (st.duration === 'distance' && st.value) { km = st.value; sec = sk ? km * sk : km * 360; }
        else { sec = 300; km = sk ? sec / sk : 0; }  // "hasta pulsar vuelta": se cuenta como 5 min
        out.push({ st, sec, km, level: level(st, refs), rep: n > 1 ? { i, n } : undefined });
      }
    }
  }
  return out;
}

const fmtMin = (sec: number) => {
  const m = Math.round(sec / 60);
  return m >= 60 ? `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, '0')}` : `${m} min`;
};
const fmtWhat = (st: WorkoutStep) =>
  st.duration === 'distance' && st.value ? (st.value >= 1 ? `${dec1(st.value).replace(',0', '')} km` : `${Math.round(st.value * 1000)} m`)
    : st.duration === 'time' && st.value ? (st.value < 1 ? `${Math.round(st.value * 60)} s` : `${dec1(st.value).replace(',0', '')} min`)
      : 'hasta pulsar vuelta';

/** Perfil del entreno: una barra por paso, ancho = tiempo, alto = intensidad (como el gráfico del reloj). */
function Profile({ flat, color }: { flat: Flat[]; color: string }) {
  const total = flat.reduce((a, f) => a + f.sec, 0) || 1;
  return (
    <Box sx={{ display: 'flex', alignItems: 'flex-end', gap: '2px', height: 72, px: 0.5, py: 0.75, borderRadius: '14px', bgcolor: alpha(color, 0.06) }}
      aria-label="Perfil de intensidad del entreno">
      {flat.map((f, i) => {
        const hard = f.st.kind === 'active';
        return (
          <Box key={i} sx={{ flexGrow: f.sec / total, flexBasis: 0, minWidth: 3, height: `${Math.round((f.level / 5) * 100)}%`,
            borderRadius: '4px 4px 2px 2px', bgcolor: hard ? color : alpha(color, f.st.kind === 'recovery' || f.st.kind === 'rest' ? 0.22 : 0.4) }} />
        );
      })}
    </Box>
  );
}

function StepRow({ st, refs, color, n }: { st: WorkoutStep; refs: Refs; color: string; n?: number }) {
  const rng = st.target === 'pace' ? stepPace(st, refs) : null;
  const hard = st.kind === 'active';
  const label = st.name && st.name.toLowerCase() !== KIND_LABEL[st.kind].toLowerCase() ? st.name : KIND_LABEL[st.kind];
  const ref = st.pace_ref && refs?.[st.pace_ref]
    ? `ritmo ${REF_NAME[st.pace_ref]}${st.pace_ref_offset_s ? ` ${st.pace_ref_offset_s > 0 ? '+' : '−'}${Math.abs(st.pace_ref_offset_s)} s` : ''}` : null;
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, py: 1 }}>
      <Box sx={{ width: 10, height: 10, borderRadius: '50%', flexShrink: 0, bgcolor: hard ? color : alpha(color, st.kind === 'recovery' || st.kind === 'rest' ? 0.3 : 0.5) }} />
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Typography variant="body2" sx={{ fontWeight: hard ? 600 : 500 }}>{n ? `${label}` : label}</Typography>
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', lineHeight: 1.35 }}>
          {[ref, st.target === 'hr' && st.hr_low && st.hr_high ? `pulso ${st.hr_low}-${st.hr_high} lpm` : null,
            !rng && st.target !== 'hr' ? 'a sensaciones' : null].filter(Boolean).join(' · ') || ' '}
        </Typography>
      </Box>
      <Box sx={{ textAlign: 'right', flexShrink: 0 }}>
        <Typography sx={{ fontWeight: 600, fontVariantNumeric: 'tabular-nums', fontSize: 15, color: hard ? color : 'text.primary' }}>{fmtWhat(st)}</Typography>
        {rng && <Typography variant="caption" sx={{ display: 'block', fontVariantNumeric: 'tabular-nums', color: 'text.secondary' }}>{mmss(rng[0])}-{mmss(rng[1])} /km</Typography>}
        {!rng && st.target === 'hr' && st.hr_low && st.hr_high && <Typography variant="caption" sx={{ display: 'block', color: 'text.secondary' }}>{st.hr_low}-{st.hr_high} lpm</Typography>}
      </Box>
    </Box>
  );
}

/** El entreno por partes: perfil arriba, totales y cada bloque (las series agrupadas con su × N). */
export function WorkoutView({ s, refs }: { s: PlanSession; refs: Refs }) {
  const mode = useResolvedMode();
  const color = SESSION_TYPE[s.type][mode];
  if (s.workout?.length) {
    const flat = flatten(s, refs);
    const total = flat.reduce((a, f) => a + f.sec, 0);
    const km = flat.reduce((a, f) => a + f.km, 0);
    const hard = flat.filter((f) => f.st.kind === 'active').reduce((a, f) => a + f.sec, 0);
    return (
      <Box sx={{ mt: 2 }}>
        <Profile flat={flat} color={color} />
        <Stack direction="row" spacing={2.5} sx={{ mt: 1.25, mb: 0.5, px: 0.5 }}>
          {[['Duración', `≈ ${fmtMin(total)}`], ['Distancia', km ? `≈ ${dec1(km)} km` : '–'], ['A tope', hard ? fmtMin(hard) : '–']].map(([l, v]) => (
            <Box key={l}><Typography variant="caption" color="text.secondary">{l}</Typography>
              <Typography sx={{ fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}>{v}</Typography></Box>
          ))}
        </Stack>
        {s.workout.map((b, i) => b.repeat > 1 ? (
          <Box key={i} sx={{ my: 1, px: 1.5, pt: 1, pb: 0.25, borderRadius: '16px', bgcolor: alpha(color, mode === 'dark' ? 0.12 : 0.07) }}>
            <Typography variant="caption" sx={{ fontWeight: 700, color, letterSpacing: 0.3 }}>REPITE {b.repeat} VECES</Typography>
            {b.steps.map((st, j) => <Box key={j} sx={{ borderTop: j ? 1 : 0, borderColor: 'divider' }}><StepRow st={st} refs={refs} color={color} n={b.repeat} /></Box>)}
          </Box>
        ) : b.steps.map((st, j) => (
          <Box key={`${i}-${j}`} sx={{ px: 1.5, borderTop: i || j ? 1 : 0, borderColor: 'divider' }}><StepRow st={st} refs={refs} color={color} /></Box>
        )))}
      </Box>
    );
  }
  if (s.strength?.length) {
    const sets = s.strength.reduce((a, x) => a + x.sets, 0);
    return (
      <Box sx={{ mt: 2 }}>
        <Typography variant="caption" color="text.secondary">{s.strength.length} ejercicios · {sets} series</Typography>
        {s.strength.map((it, i) => (
          <Box key={i} sx={{ display: 'flex', alignItems: 'center', gap: 1.5, py: 1, borderTop: i ? 1 : 0, borderColor: 'divider' }}>
            <Typography sx={{ width: 22, fontWeight: 700, color, fontVariantNumeric: 'tabular-nums' }}>{i + 1}</Typography>
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <Typography variant="body2" sx={{ fontWeight: 600 }}>{it.label}</Typography>
              <Typography variant="caption" color="text.secondary">descanso {it.rest_s} s</Typography>
            </Box>
            <Box sx={{ textAlign: 'right' }}>
              <Typography sx={{ fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}>{it.sets} × {it.seconds ? `${it.seconds} s` : it.reps}</Typography>
              {it.weight_kg ? <Typography variant="caption" color="text.secondary">{dec1(it.weight_kg).replace(',0', '')} kg</Typography> : null}
            </Box>
          </Box>
        ))}
      </Box>
    );
  }
  return null;
}

const STATUS_TEXT: Record<string, string> = {
  done: 'Hecho', partial: 'A medias', missed: 'No hecho', today: 'Hoy', upcoming: 'Próximo', rest: 'Descanso', moved: 'Movido',
};

export function SessionDialog({ s, refs, onClose, onRedo, onUndo, go, todayIso, extra }: {
  s: PlanSession | null; refs: Refs; onClose: () => void; todayIso: string;
  onRedo: (s: PlanSession) => Promise<void>; onUndo: () => Promise<void>; go: (k: string) => void; extra?: ReactNode;
}) {
  const mode = useResolvedMode();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [confirm, setConfirm] = useState(false);
  if (!s) return null;
  const color = SESSION_TYPE[s.type][mode];
  const canRedo = s.type !== 'rest' && s.date !== todayIso && !s.moved_to && s.status !== 'done';
  const canRepeat = s.type !== 'rest' && s.date < todayIso && s.status === 'done';
  const isRedo = !!s.redo_from && s.date === todayIso;
  const act = async (fn: () => Promise<void>) => {
    setBusy(true); setErr(null);
    try { await fn(); setConfirm(false); onClose(); } catch (e) { setErr(e instanceof Error ? e.message : 'Algo ha fallado.'); } finally { setBusy(false); }
  };
  const statusColor = s.status === 'done' ? 'success.main' : s.status === 'partial' ? 'warning.main' : s.status === 'today' ? BRAND_INK : 'text.secondary';
  return (
    <Dialog open={!!s} onClose={onClose} fullWidth maxWidth="sm" scroll="paper"
      slotProps={{ paper: { sx: { borderRadius: '28px', m: { xs: 1, sm: 2 }, width: { xs: 'calc(100% - 16px)', sm: undefined }, maxHeight: 'calc(100% - 24px)' } } }}>
      <Box sx={{ p: { xs: 2.25, sm: 3 }, overflowY: 'auto' }}>
        <Stack direction="row" sx={{ alignItems: 'flex-start', gap: 1 }}>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography variant="caption" color="text.secondary">
              {toDate(s.date).toLocaleDateString('es-ES', { weekday: 'long', day: 'numeric', month: 'long' }).replace(/^\w/, (c) => c.toUpperCase())}
              {' · '}<Box component="span" sx={{ color: statusColor, fontWeight: 600, textTransform: 'none' }}>
                {s.status === 'moved' && s.moved_to ? `Pasado al ${toDate(s.moved_to).toLocaleDateString('es-ES', { weekday: 'long', day: 'numeric' })}` : STATUS_TEXT[s.status]}
              </Box>
            </Typography>
            <Typography sx={{ fontSize: 22, fontWeight: 600, lineHeight: 1.25, mt: 0.25 }}>{s.title}</Typography>
            <Stack direction="row" spacing={1} sx={{ alignItems: 'center', mt: 0.75, flexWrap: 'wrap', rowGap: 0.5 }}>
              <Box sx={{ px: 1, py: 0.25, borderRadius: 999, fontSize: 12, fontWeight: 600, color, bgcolor: alpha(color, 0.14) }}>{SESSION_TYPE[s.type].label}</Box>
              <Typography variant="body2" color="text.secondary">
                {[s.distance_km ? `${dec1(s.distance_km)} km` : null, s.duration_min ? `${s.duration_min} min` : null, s.target].filter(Boolean).join(' · ')}
              </Typography>
            </Stack>
            {isRedo && <Typography variant="caption" sx={{ display: 'block', mt: 0.5, color: BRAND_INK, fontWeight: 600 }}>
              Retomado del {toDate(s.redo_from!).toLocaleDateString('es-ES', { weekday: 'long', day: 'numeric' })}</Typography>}
          </Box>
          <IconButton onClick={onClose} aria-label="Cerrar" sx={{ mt: -0.5, mr: -0.5 }}><CloseRounded /></IconButton>
        </Stack>

        {s.description && <Typography variant="body2" sx={{ mt: 2, color: 'text.secondary', '& b': { color: 'text.primary' } }}><Rich>{s.description}</Rich></Typography>}
        <WorkoutView s={s} refs={refs} />
        {extra}

        {s.actual && (
          <Box sx={{ mt: 2, p: 1.75, borderRadius: '16px', bgcolor: alpha(mode === 'dark' ? '#6DD58C' : '#146C2E', 0.08) }}>
            <Typography variant="caption" sx={{ fontWeight: 600, color: 'success.main' }}>LO QUE HICISTE</Typography>
            <Typography sx={{ fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}>
              {[s.actual.km ? `${dec1(s.actual.km)} km` : null, `${s.actual.min} min`, s.actual.pace ? pace(s.actual.pace) : null, s.actual.hr ? `${s.actual.hr} lpm` : null].filter(Boolean).join(' · ')}
            </Typography>
            <Button size="small" endIcon={<OpenInNewRounded />} onClick={() => { onClose(); go(`act-${s.actual!.id}`); }} sx={{ mt: 0.5, ml: -1, borderRadius: 999 }}>Ver la actividad</Button>
          </Box>
        )}

        {err && <Typography color="error" variant="body2" sx={{ mt: 2 }}>{err}</Typography>}
        {(canRedo || canRepeat) && (
          confirm ? (
            <Box sx={{ mt: 2.5, p: 1.75, borderRadius: '16px', bgcolor: brandTint(8, BRAND_INK) }}>
              <Typography variant="body2">Este entreno pasa a <b>hoy</b> y sustituye lo que tenías previsto hoy del mismo tipo. Si no lo haces, puedes deshacerlo.</Typography>
              <Stack direction="row" spacing={1} sx={{ mt: 1.5 }}>
                <Button onClick={() => setConfirm(false)} sx={{ borderRadius: 999, flex: 1 }}>Cancelar</Button>
                <Button variant="contained" disableElevation disabled={busy} onClick={() => act(() => onRedo(s))}
                  sx={{ borderRadius: 999, flex: 2, bgcolor: BRAND, '&:hover': { bgcolor: BRAND_DARK } }}>{busy ? 'Guardando…' : 'Sí, lo hago hoy'}</Button>
              </Stack>
            </Box>
          ) : (
            <Button fullWidth variant="contained" disableElevation startIcon={<ReplayRounded />} onClick={() => setConfirm(true)}
              sx={{ mt: 2.5, py: 1.25, borderRadius: 999, bgcolor: BRAND, '&:hover': { bgcolor: BRAND_DARK } }}>
              {canRepeat ? 'Repetirlo hoy' : 'Hacerlo hoy'}
            </Button>
          )
        )}
        {isRedo && (
          <Button fullWidth variant="outlined" startIcon={<UndoRounded />} disabled={busy} onClick={() => act(onUndo)} sx={{ mt: 2, py: 1, borderRadius: 999 }}>
            Deshacer: volver a lo previsto hoy
          </Button>
        )}
      </Box>
    </Dialog>
  );
}
