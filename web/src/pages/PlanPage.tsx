import { useEffect, useState, type ReactNode } from 'react';
import Accordion from '@mui/material/Accordion';
import AccordionDetails from '@mui/material/AccordionDetails';
import AccordionSummary from '@mui/material/AccordionSummary';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CircularProgress from '@mui/material/CircularProgress';
import IconButton from '@mui/material/IconButton';
import LinearProgress from '@mui/material/LinearProgress';
import MenuItem from '@mui/material/MenuItem';
import Rating from '@mui/material/Rating';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import ToggleButton from '@mui/material/ToggleButton';
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import { alpha } from '@mui/material/styles';
import useMediaQuery from '@mui/material/useMediaQuery';
import { BarChart } from '@mui/x-charts/BarChart';
import ExpandMoreRounded from '@mui/icons-material/ExpandMoreRounded';
import CheckCircleRounded from '@mui/icons-material/CheckCircleRounded';
import RemoveCircleOutlineRounded from '@mui/icons-material/RemoveCircleOutlineRounded';
import CancelRounded from '@mui/icons-material/CancelRounded';
import RadioButtonUncheckedRounded from '@mui/icons-material/RadioButtonUncheckedRounded';
import HotelRounded from '@mui/icons-material/HotelRounded';
import AutoAwesomeRounded from '@mui/icons-material/AutoAwesomeRounded';
import PsychologyRounded from '@mui/icons-material/PsychologyRounded';
import TuneRounded from '@mui/icons-material/TuneRounded';
import DeleteOutlineRounded from '@mui/icons-material/DeleteOutlineRounded';
import FlagRounded from '@mui/icons-material/FlagRounded';
import WatchRounded from '@mui/icons-material/WatchRounded';
import Dialog from '@mui/material/Dialog';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import { downloadWeek } from '../workouts';
import { Rich } from '../rich';
import SpeedRounded from '@mui/icons-material/SpeedRounded';
import TimerOutlined from '@mui/icons-material/TimerOutlined';
import EmojiEventsOutlined from '@mui/icons-material/EmojiEventsOutlined';
import ScienceOutlined from '@mui/icons-material/ScienceOutlined';
import BedtimeOutlined from '@mui/icons-material/BedtimeOutlined';
import CalendarMonthOutlined from '@mui/icons-material/CalendarMonthOutlined';
import FitnessCenterRounded from '@mui/icons-material/FitnessCenterRounded';
import MonitorWeightOutlined from '@mui/icons-material/MonitorWeightOutlined';
import TuneRounded2 from '@mui/icons-material/TuneRounded';

const TOPIC: Record<string, { icon: ReactNode; color: { light: string; dark: string } }> = {
  nivel: { icon: <SpeedRounded />, color: { light: '#1A73E8', dark: '#8AB4F8' } },
  ritmos: { icon: <TimerOutlined />, color: { light: '#E8710A', dark: '#FCAD70' } },
  marcas: { icon: <EmojiEventsOutlined />, color: { light: '#C26401', dark: '#FDD663' } },
  objetivo: { icon: <FlagRounded />, color: { light: '#D93025', dark: '#F28B82' } },
  test: { icon: <ScienceOutlined />, color: { light: '#9334E6', dark: '#D7AEFB' } },
  salud: { icon: <BedtimeOutlined />, color: { light: '#5B5BD6', dark: '#AFADFF' } },
  estructura: { icon: <CalendarMonthOutlined />, color: { light: '#00838F', dark: '#78D9EC' } },
  gimnasio: { icon: <FitnessCenterRounded />, color: { light: '#9334E6', dark: '#D7AEFB' } },
  peso: { icon: <MonitorWeightOutlined />, color: { light: '#188038', dark: '#81C995' } },
  preferencias: { icon: <TuneRounded2 />, color: { light: '#80868B', dark: '#BDC1C6' } },
};
import { isoLocal, toDate, type CoachView, type GarminData, type PlanSession, type SessionType } from '../data';
import { dateLong, dateShort, dec1, duration, pace } from '../format';
import { useResolvedMode } from '../theme';
import { CARD_SX, IconBubble, PageHeader, SectionTitle, chartSx } from '../ui';
import { bandAxis, yClean } from '../charts';

const online = window.location.protocol.startsWith('http');
const TYPE: Record<SessionType, { label: string; light: string; dark: string }> = {
  easy: { label: 'Suave', light: '#188038', dark: '#81C995' },
  long: { label: 'Tirada larga', light: '#1A73E8', dark: '#8AB4F8' },
  tempo: { label: 'Ritmo', light: '#E8710A', dark: '#FCAD70' },
  intervals: { label: 'Series', light: '#D93025', dark: '#F28B82' },
  race: { label: 'Carrera', light: '#5B5BD6', dark: '#AFADFF' },
  strength: { label: 'Fuerza', light: '#9334E6', dark: '#D7AEFB' },
  cross: { label: 'Cruzado', light: '#00838F', dark: '#78D9EC' },
  rest: { label: 'Descanso', light: '#80868B', dark: '#9AA0A6' },
};
const DAYS = ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo'];
const GOALS = ['5 km', '10 km', 'Media maratón', 'Maratón'];

async function api(path: string, body?: unknown): Promise<CoachView> {
  const r = await fetch(path, body === undefined ? undefined : {
    method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Garmin-Stats': '1' }, body: JSON.stringify(body),
  });
  if (r.status === 401) { window.location.href = '/auth/login?next=%2F%23plan'; throw new Error('Sesión caducada'); }
  const j = await r.json();
  if (!r.ok) throw new Error(j.error ?? 'Algo ha fallado.');
  return j;
}

/** En AWS el plan se genera en segundo plano: consulta hasta que termine (máx. ~8 min). */
async function settle(v: CoachView): Promise<CoachView> {
  let cur = v;
  for (let i = 0; i < 100 && cur.job?.status === 'running'; i++) {
    await new Promise((r) => setTimeout(r, 5000));
    cur = await api('./api/plan');
  }
  if (cur.job?.status === 'error') throw new Error(cur.job.error ?? 'No se pudo generar el plan.');
  if (cur.job?.status === 'cancelled') throw new Error('Reajuste cancelado: tu plan sigue igual.');
  return cur;
}

function StatusIcon({ s }: { s: PlanSession['status'] }) {
  const sx = { fontSize: 20 };
  if (s === 'done') return <CheckCircleRounded sx={{ ...sx, color: 'success.main' }} />;
  if (s === 'partial') return <RemoveCircleOutlineRounded sx={{ ...sx, color: 'warning.main' }} />;
  if (s === 'missed') return <CancelRounded sx={{ ...sx, color: 'text.disabled' }} />;
  if (s === 'rest') return <HotelRounded sx={{ ...sx, color: 'text.disabled' }} />;
  return <RadioButtonUncheckedRounded sx={{ ...sx, color: s === 'today' ? 'primary.main' : 'text.disabled' }} />;
}

function plannedText(s: PlanSession) {
  return [s.distance_km ? `${dec1(s.distance_km)} km` : null, s.duration_min ? `${s.duration_min} min` : null].filter(Boolean).join(' · ');
}

// ------------------------------------------------------------------ crear
function CreateForm({ onDone }: { onDone: (v: CoachView) => void }) {
  const [goal, setGoal] = useState('Media maratón');
  const [date, setDate] = useState(() => { const d = new Date(); d.setDate(d.getDate() + 7 * 16); return isoLocal(d); });
  const [goalTime, setGoalTime] = useState('');
  const [days, setDays] = useState(4);
  const [longDay, setLongDay] = useState('domingo');
  const [notes, setNotes] = useState('');
  const [gymDays, setGymDays] = useState(0);
  const [ambition, setAmbition] = useState<'realista' | 'exigente'>('realista');
  const [bodyGoal, setBodyGoal] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const submit = async () => {
    setBusy(true); setErr(null);
    try { onDone(await settle(await api('./api/plan/create', { goal, date, goalTime, daysPerWeek: days, longRunDay: longDay, notes, gymDays, bodyGoal, ambition }))); }
    catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  return (
    <Card sx={{ ...CARD_SX, maxWidth: 720 }}>
      <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center', mb: 2.5 }}>
        <IconBubble color="#1A73E8" size={44}><AutoAwesomeRounded /></IconBubble>
        <Box>
          <Typography variant="h6">Crea tu plan con IA</Typography>
          <Typography variant="body2" color="text.secondary">Se adapta a tu forma real y se reajusta cada lunes según lo que hagas.</Typography>
        </Box>
      </Stack>
      <Stack spacing={2.5}>
        <Box>
          <Typography variant="subtitle2" sx={{ mb: 1 }}>Objetivo</Typography>
          <ToggleButtonGroup exclusive value={goal} onChange={(_, v) => v && setGoal(v)} size="small"
            sx={{ flexWrap: 'wrap', gap: 1, '& .MuiToggleButton-root': { borderRadius: '999px !important', border: '1px solid', borderColor: 'divider', px: 2 },
              '& .Mui-selected': { bgcolor: 'color-mix(in srgb, var(--mui-palette-primary-main) 16%, transparent) !important', color: 'primary.main', borderColor: 'primary.main' } }}>
            {GOALS.map((g) => <ToggleButton key={g} value={g}>{g}</ToggleButton>)}
          </ToggleButtonGroup>
        </Box>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
          <TextField label="Fecha de la carrera" type="date" value={date} onChange={(e) => setDate(e.target.value)} fullWidth
            slotProps={{ inputLabel: { shrink: true } }} />
          <TextField label="Tiempo objetivo (opcional)" placeholder="1:45:00" value={goalTime} onChange={(e) => setGoalTime(e.target.value)} fullWidth />
        </Stack>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
          <Box sx={{ flex: 1 }}>
            <Typography variant="subtitle2" sx={{ mb: 1 }}>Días por semana</Typography>
            <ToggleButtonGroup exclusive value={days} onChange={(_, v) => v && setDays(v)} size="small"
              sx={{ gap: 1, '& .MuiToggleButton-root': { borderRadius: '999px !important', border: '1px solid', borderColor: 'divider', minWidth: 44 },
                '& .Mui-selected': { bgcolor: 'color-mix(in srgb, var(--mui-palette-primary-main) 16%, transparent) !important', color: 'primary.main', borderColor: 'primary.main' } }}>
              {[3, 4, 5, 6].map((d) => <ToggleButton key={d} value={d}>{d}</ToggleButton>)}
            </ToggleButtonGroup>
          </Box>
          <TextField select label="Día de la tirada larga" value={longDay} onChange={(e) => setLongDay(e.target.value)} sx={{ flex: 1 }}>
            {DAYS.map((d) => <MenuItem key={d} value={d}>{d[0].toUpperCase() + d.slice(1)}</MenuItem>)}
          </TextField>
        </Stack>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
          <Box sx={{ flex: 1 }}>
            <Typography variant="subtitle2" sx={{ mb: 1 }}>Días de gimnasio</Typography>
            <ToggleButtonGroup exclusive value={gymDays} onChange={(_, v) => v !== null && setGymDays(v)} size="small"
              sx={{ gap: 1, '& .MuiToggleButton-root': { borderRadius: '999px !important', border: '1px solid', borderColor: 'divider', minWidth: 44 },
                '& .Mui-selected': { bgcolor: 'color-mix(in srgb, var(--mui-palette-primary-main) 16%, transparent) !important', color: 'primary.main', borderColor: 'primary.main' } }}>
              {[0, 1, 2, 3, 4].map((d) => <ToggleButton key={d} value={d}>{d}</ToggleButton>)}
            </ToggleButtonGroup>
          </Box>
          <TextField label="Objetivo de físico (opcional)" placeholder="Ganar definición, más fuerza…" value={bodyGoal}
            onChange={(e) => setBodyGoal(e.target.value)} sx={{ flex: 1 }} />
        </Stack>
        <Box>
          <Typography variant="subtitle2" sx={{ mb: 1 }}>Nivel</Typography>
          <ToggleButtonGroup exclusive value={ambition} onChange={(_, v) => v && setAmbition(v)} size="small"
            sx={{ gap: 1, '& .MuiToggleButton-root': { borderRadius: '999px !important', border: '1px solid', borderColor: 'divider', px: 2 },
              '& .Mui-selected': { bgcolor: 'color-mix(in srgb, var(--mui-palette-primary-main) 16%, transparent) !important', color: 'primary.main', borderColor: 'primary.main' } }}>
            <ToggleButton value="realista">Realista</ToggleButton>
            <ToggleButton value="exigente">🔥 Exigente: quiero un reto</ToggleButton>
          </ToggleButtonGroup>
        </Box>
        <TextField label="Algo que deba saber (opcional)" placeholder="Molestias, días que no puedes, si prefieres cinta…" value={notes}
          onChange={(e) => setNotes(e.target.value)} multiline minRows={2} />
        {err && <Alert severity="error" sx={{ borderRadius: '14px' }}>{err}</Alert>}
        {!online && <Alert severity="info" sx={{ borderRadius: '14px' }}>Para crear el plan abre la web desde http://localhost:8765.</Alert>}
        <Button variant="contained" size="large" disabled={busy || !online} onClick={submit}
          sx={{ borderRadius: 999, alignSelf: 'flex-start', px: 3, boxShadow: 'none' }}
          startIcon={busy ? <CircularProgress size={18} color="inherit" /> : <AutoAwesomeRounded />}>
          {busy ? 'Diseñando tu plan… (1-3 min)' : 'Crear plan'}
        </Button>
      </Stack>
    </Card>
  );
}

// ------------------------------------------------------------------ piezas del plan
function SessionChip({ s, compact }: { s: PlanSession; compact?: boolean }) {
  const mode = useResolvedMode();
  const c = TYPE[s.type][mode];
  return (
    <Box sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.75, px: 1, py: 0.25, borderRadius: 999, bgcolor: alpha(c, 0.14), color: c,
      fontSize: compact ? 11 : 12, fontWeight: 600, whiteSpace: 'nowrap' }}>
      <Box sx={{ width: 6, height: 6, borderRadius: '50%', bgcolor: c }} />{TYPE[s.type].label}
    </Box>
  );
}

function FeedbackStars({ s, onSaved }: { s: PlanSession; onSaved: (v: CoachView) => void }) {
  const [val, setVal] = useState<number | null>(s.feedback?.rating ?? null);
  if (!online || !(s.status === 'done' || s.status === 'partial')) return null;
  return (
    <Tooltip title="¿Cómo te sentiste? El coach lo usa en el próximo ajuste">
      <Rating size="small" value={val} onChange={async (_, v) => { if (!v) return; setVal(v); onSaved(await api('./api/plan/feedback', { date: s.date, rating: v })); }} />
    </Tooltip>
  );
}

function DayCard({ s, go, onSaved, sets }: { s: PlanSession; go: (k: string) => void; onSaved: (v: CoachView) => void; sets?: (id: number) => { ex: string }[] | null | undefined }) {
  const mode = useResolvedMode();
  const c = TYPE[s.type][mode];
  const today = s.status === 'today';
  return (
    <Card sx={{ ...CARD_SX, p: 1.75, display: 'flex', flexDirection: 'column', gap: 0.75, minHeight: 150, position: 'relative',
      outline: today ? `2px solid ${c}` : 'none', opacity: s.status === 'missed' ? 0.7 : 1 }}>
      <Stack direction="row" sx={{ justifyContent: 'space-between', alignItems: 'center' }}>
        <Typography variant="caption" sx={{ fontWeight: 600, color: today ? c : 'text.secondary', textTransform: 'capitalize' }}>
          {toDate(s.date).toLocaleDateString('es-ES', { weekday: 'short', day: 'numeric' }).replace('.', '')}
        </Typography>
        <StatusIcon s={s.status} />
      </Stack>
      <SessionChip s={s} compact />
      <Typography variant="body2" sx={{ fontWeight: 600, lineHeight: 1.3 }}>{s.title}</Typography>
      {s.type !== 'rest' && <Typography variant="caption" color="text.secondary">{plannedText(s)}</Typography>}
      {s.actual && (
        <Typography variant="caption" onClick={() => go(`act-${s.actual!.id}`)}
          sx={{ color: 'success.main', fontWeight: 500, cursor: 'pointer', mt: 'auto' }}>
          Hecho: {s.actual.km ? `${dec1(s.actual.km)} km` : `${s.actual.min} min`}{s.actual.pace ? ` · ${pace(s.actual.pace)}` : ''}
          {(() => { const st = sets?.(s.actual!.id); return st && st.length ? ` · ${new Set(st.map((x) => x.ex)).size} ejercicios, ${st.length} series` : ''; })()}
        </Typography>
      )}
      <FeedbackStars s={s} onSaved={onSaved} />
    </Card>
  );
}

/** Día de la semana en una línea (móvil). */
function DayRow({ s, go, first }: { s: PlanSession; go: (k: string) => void; first: boolean }) {
  const mode = useResolvedMode();
  const c = TYPE[s.type][mode];
  const today = s.status === 'today';
  return (
    <Box onClick={() => s.actual && go(`act-${s.actual.id}`)} sx={{ display: 'flex', alignItems: 'center', gap: 1.5, px: 1.5, py: 1.25,
      borderTop: first ? 0 : 1, borderColor: 'divider', borderRadius: today ? '16px' : 0, cursor: s.actual ? 'pointer' : 'default',
      bgcolor: today ? alpha(c, mode === 'dark' ? 0.16 : 0.09) : 'transparent' }}>
      <Box sx={{ width: 40, textAlign: 'center', flexShrink: 0 }}>
        <Typography variant="caption" sx={{ display: 'block', color: today ? c : 'text.secondary', fontWeight: 600, textTransform: 'uppercase', lineHeight: 1.1 }}>
          {toDate(s.date).toLocaleDateString('es-ES', { weekday: 'short' }).replace('.', '')}
        </Typography>
        <Typography sx={{ fontWeight: 600, fontSize: 18, lineHeight: 1.1 }}>{toDate(s.date).getDate()}</Typography>
      </Box>
      <Box sx={{ width: 4, alignSelf: 'stretch', borderRadius: 999, bgcolor: s.type === 'rest' ? 'divider' : c, flexShrink: 0 }} />
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Typography variant="body2" noWrap sx={{ fontWeight: 600, color: s.type === 'rest' ? 'text.secondary' : 'text.primary' }}>{s.title}</Typography>
        <Typography variant="caption" color="text.secondary" noWrap sx={{ display: 'block' }}>
          {s.actual ? `Hecho: ${s.actual.km ? `${dec1(s.actual.km)} km` : `${s.actual.min} min`}` : s.type === 'rest' ? 'Descanso' : [TYPE[s.type].label, plannedText(s)].filter(Boolean).join(' · ')}
        </Typography>
      </Box>
      <StatusIcon s={s.status} />
    </Box>
  );
}

/** Ventana "Pasar al reloj": prepara los entrenos de la semana y explica cómo copiarlos. */
function WatchDialog({ open, onClose, weekStart, sessions, onView }: {
  open: boolean; onClose: () => void; weekStart: string; sessions: PlanSession[]; onView: (v: CoachView) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const runs = sessions.filter((x) => ['easy', 'long', 'tempo', 'intervals', 'race'].includes(x.type));
  const gym = sessions.filter((x) => x.type === 'strength');
  type Wk = PlanSession & { workout?: unknown; strength?: unknown };
  const go = async () => {
    setBusy(true); setMsg(null);
    try {
      let list = sessions;
      if (runs.some((x) => !(x as Wk).workout) || gym.some((x) => !(x as Wk).strength)) {
        const v = await api('./api/plan/structure', { week: weekStart });
        onView(v);
        list = v.plan?.weeks.find((w) => w.start === weekStart)?.sessions ?? sessions;
      }
      const n = downloadWeek(list, weekStart);
      setMsg(n ? `Descargados ${n} entrenos. Ahora cópialos al reloj (pasos de abajo).` : 'Esta semana no tiene sesiones para el reloj.');
    } catch (e) { setMsg((e as Error).message); } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm" slotProps={{ paper: { sx: { borderRadius: '28px', m: 2 } } }}>
      <DialogTitle sx={{ pb: 1 }}>Pasar los entrenos al reloj</DialogTitle>
      <DialogContent>
        <Typography color="text.secondary" sx={{ mb: 2 }}>
          {runs.length} de carrera (calentamiento, series y ritmo o pulso objetivo) y {gym.length} de gimnasio (ejercicios del catálogo de Garmin con series, repeticiones, peso y descansos). El reloj te guiará paso a paso.
        </Typography>
        <Button variant="contained" disableElevation onClick={go} disabled={busy || !online || runs.length + gym.length === 0}
          startIcon={busy ? <CircularProgress size={18} color="inherit" /> : <WatchRounded />} sx={{ borderRadius: 999, mb: 2 }}>
          {busy ? 'Preparando entrenos…' : 'Descargar entrenos de la semana'}
        </Button>
        {msg && <Alert severity="info" sx={{ borderRadius: '14px', mb: 2 }}>{msg}</Alert>}
        <Typography variant="subtitle2" sx={{ mb: 1 }}>Cómo pasarlos (desde el ordenador)</Typography>
        <Typography component="ol" sx={{ pl: 2.5, m: 0, '& li': { mb: 0.75 } }}>
          <li>Conecta el reloj al ordenador con su cable USB.</li>
          <li>Ábrelo como una unidad (aparece en el Explorador de archivos) y entra en <b>GARMIN → NewFiles</b>.</li>
          <li>Descomprime el .zip descargado y copia los archivos <b>.fit</b> en esa carpeta.</li>
          <li>Desconecta el reloj: los verás en <b>Entrenamiento → Entrenamientos</b>. Elige el del día y pulsa Iniciar.</li>
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mt: 1.5 }}>
          En el gimnasio, al acabar cada serie el reloj te pide confirmar repeticiones y peso: así el coach sabe cuánto subir. Puedes descargar desde el móvil, pero para copiarlos hace falta el ordenador.
        </Typography>
        <Box sx={{ textAlign: 'right', mt: 1 }}><Button onClick={onClose} sx={{ borderRadius: 999 }}>Cerrar</Button></Box>
      </DialogContent>
    </Dialog>
  );
}

// ------------------------------------------------------------------ página
export default function PlanPage({ data, go }: { data: GarminData; go: (k: string) => void }) {
  const mode = useResolvedMode();
  const [view, setView] = useState<CoachView | undefined>(data.coach);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [moreSummary, setMoreSummary] = useState(false);
  const [watchOpen, setWatchOpen] = useState(false);
  const [confirm, setConfirm] = useState<null | { title: string; text: string; action: () => void }>(null);
  const [cancelling, setCancelling] = useState(false);
  const cancel = async () => { setCancelling(true); try { await api('./api/plan/cancel', {}); } catch { /* el polling lo resuelve */ } };
  const small = useMediaQuery('(max-width:599px)');
  useEffect(() => {
    if (!online) return;
    api('./api/plan').then((v) => { setView(v); if (v.job?.status === 'running') { setBusy(true); settle(v).then(setView).catch((e) => setErr(e.message)).finally(() => setBusy(false)); } })
      .catch(() => setView(data.coach));
  }, [data.generatedAt]);  // eslint-disable-line react-hooks/exhaustive-deps

  const plan = view?.plan;
  if (!plan) {
    return (
      <Box>
        <PageHeader title="Plan" subtitle="Tu entrenador con IA: un plan hecho a tu medida que aprende de ti cada semana" />
        <CreateForm onDone={setView} />
      </Box>
    );
  }

  const todayIso = isoLocal(new Date());
  const week = plan.weeks.find((w) => { const e = toDate(w.start); e.setDate(e.getDate() + 6); return w.start <= todayIso && todayIso <= isoLocal(e); }) ?? plan.weeks[0];
  const weeksLeft = Math.max(0, Math.ceil((toDate(plan.raceDate).getTime() - Date.now()) / (7 * 864e5)));
  const wi = plan.weeks.indexOf(week);
  const done = plan.weeks.flatMap((w) => w.sessions).filter((s) => ['done', 'partial', 'missed'].includes(s.status));
  const compliance = done.length ? Math.round((100 * done.reduce((x, s) => x + (s.status === 'done' ? 1 : s.status === 'partial' ? 0.5 : 0), 0)) / done.length) : null;
  const pred = data.predictions.find((p) => p.distance === plan.goal);
  const last = plan.history[plan.history.length - 1];
  const t = view?.today;

  const run = async (path: string, confirmText?: string, body: Record<string, unknown> = {}) => {
    if (confirmText && !window.confirm(confirmText)) return;
    setBusy(true); setErr(null);
    try { setView(await settle(await api(path, body))); } catch (e) { setErr((e as Error).message); setView(await api('./api/plan').catch(() => view)); }
    finally { setBusy(false); setCancelling(false); }
  };
  const ask = (title: string, text: string, action: () => void) => setConfirm({ title, text, action });

  return (
    <Box>
      <PageHeader title="Plan" subtitle={`${plan.goal} · ${dateLong(toDate(plan.raceDate))}`}
        action={online ? (
          <Stack direction="row" spacing={1}>
            <Button variant="outlined" startIcon={busy ? <CircularProgress size={16} /> : <TuneRounded />} disabled={busy}
              onClick={() => ask('¿Reajustar el plan ahora?', 'El coach revisa tus últimos datos y rehace las semanas que quedan. Tarda 1-3 minutos y cuesta unos 0,50 $ (Opus). Ya se reajusta solo cada lunes.', () => run('./api/plan/adapt'))}
              sx={{ borderRadius: 999 }}>{busy ? 'Reajustando…' : 'Reajustar ahora'}</Button>
            <Tooltip title="Borrar plan"><IconButton onClick={() => run('./api/plan/delete', '¿Borrar el plan? Se guarda una copia en el historial.')}><DeleteOutlineRounded /></IconButton></Tooltip>
          </Stack>
        ) : undefined} />
      {err && <Alert severity="error" sx={{ mb: 2, borderRadius: '14px' }}>{err}</Alert>}
      {online && (
        <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center', mb: 2, flexWrap: 'wrap', rowGap: 1 }}>
          <Typography variant="body2" color="text.secondary">Nivel del plan</Typography>
          <ToggleButtonGroup exclusive size="small" value={plan.ambition ?? 'realista'} disabled={busy}
            onChange={(_, v) => v && v !== (plan.ambition ?? 'realista') && ask(v === 'exigente' ? '¿Pasar al modo exigente? 🔥' : '¿Pasar al modo realista?',
              (v === 'exigente' ? 'Mantiene tu objetivo, sube el volumen y pone 2 sesiones de calidad por semana.' : 'Prioriza llegar sano y ajusta el objetivo si no es realista.')
              + ' Se reajusta todo el plan: tarda 1-3 minutos y cuesta unos 0,50 $.', () => run('./api/plan/ambition', undefined, { ambition: v }))}
            sx={{ bgcolor: 'background.paper', '& .MuiToggleButton-root': { borderRadius: '999px !important', px: 2, color: 'text.secondary' },
              '& .Mui-selected': { bgcolor: 'color-mix(in srgb, var(--mui-palette-primary-main) 16%, transparent) !important', color: 'primary.main' } }}>
            <ToggleButton value="realista">Realista</ToggleButton>
            <ToggleButton value="exigente">🔥 Exigente</ToggleButton>
          </ToggleButtonGroup>
          {busy && (
            <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
              <CircularProgress size={14} />
              <Typography variant="caption" color="text.secondary">{cancelling ? 'Cancelando…' : 'Reajustando el plan (1-3 min)…'}</Typography>
              <Button size="small" color="error" onClick={cancel} disabled={cancelling} sx={{ borderRadius: 999, minWidth: 0 }}>Cancelar</Button>
            </Stack>
          )}
        </Stack>
      )}

      <Dialog open={!!confirm} onClose={() => setConfirm(null)} slotProps={{ paper: { sx: { borderRadius: '28px', m: 2, maxWidth: 420 } } }}>
        <DialogTitle sx={{ pb: 1 }}>{confirm?.title}</DialogTitle>
        <DialogContent>
          <Typography color="text.secondary">{confirm?.text}</Typography>
          <Stack direction="row" spacing={1} sx={{ justifyContent: 'flex-end', mt: 3 }}>
            <Button onClick={() => setConfirm(null)} sx={{ borderRadius: 999 }}>No</Button>
            <Button variant="contained" disableElevation onClick={() => { const a = confirm?.action; setConfirm(null); a?.(); }} sx={{ borderRadius: 999 }}>Sí, reajustar</Button>
          </Stack>
        </DialogContent>
      </Dialog>

      {/* resumen */}
      <Card sx={{ ...CARD_SX, mb: 2 }}>
        <Box sx={{ display: 'grid', gap: { xs: 2, sm: 3 }, gridTemplateColumns: { xs: '1fr 1fr', md: 'repeat(4, 1fr)' } }}>
          <Box><Typography variant="caption" color="text.secondary">Faltan</Typography>
            <Typography sx={{ fontSize: { xs: 21, sm: 28 }, fontWeight: 500, lineHeight: 1.25 }}>{weeksLeft} semanas</Typography>
            <Typography variant="caption" color="text.secondary">semana {wi + 1} de {plan.weeks.length}</Typography></Box>
          <Box><Typography variant="caption" color="text.secondary">Objetivo</Typography>
            <Typography sx={{ fontSize: { xs: 21, sm: 28 }, fontWeight: 500, lineHeight: 1.25 }}>{plan.goalTime || 'Terminar bien'}</Typography>
            {pred && <Typography variant="caption" color="text.secondary">Tu VO2max apunta a {duration(pred.predicted)}</Typography>}</Box>
          <Box><Typography variant="caption" color="text.secondary">Cumplimiento</Typography>
            <Typography sx={{ fontSize: { xs: 21, sm: 28 }, fontWeight: 500, lineHeight: 1.25 }}>{compliance == null ? '–' : `${compliance} %`}</Typography>
            <Typography variant="caption" color="text.secondary">{done.length} sesiones pasadas</Typography></Box>
          <Box><Typography variant="caption" color="text.secondary">Esta semana</Typography>
            <Typography sx={{ fontSize: { xs: 21, sm: 28 }, fontWeight: 500, lineHeight: 1.25 }}>{dec1(week.actualKm)} / {dec1(week.plannedKm)} km</Typography>
            <LinearProgress variant="determinate" value={Math.min(100, (week.actualKm / (week.plannedKm || 1)) * 100)}
              sx={{ mt: 1, height: 6, borderRadius: 999, bgcolor: alpha('#808080', 0.15), '& .MuiLinearProgress-bar': { borderRadius: 999 } }} /></Box>
        </Box>
        <Box sx={{ mt: 2.5, pt: 2, borderTop: 1, borderColor: 'divider' }}>
          <Typography color="text.secondary" sx={{ fontSize: { xs: 14, sm: 16 }, ...(moreSummary ? {} : { display: '-webkit-box', WebkitLineClamp: { xs: 4, md: 'unset' }, WebkitBoxOrient: 'vertical', overflow: 'hidden' }) }}>
            <Rich>{plan.summary}</Rich>
          </Typography>
          <Button size="small" onClick={() => setMoreSummary((m) => !m)} sx={{ display: { md: 'none' }, mt: 0.5, ml: -1, borderRadius: 999 }}>
            {moreSummary ? 'Leer menos' : 'Leer más'}
          </Button>
        </Box>
      </Card>

      {/* hoy */}
      {t && (
        <Card sx={{ ...CARD_SX, mb: 2, bgcolor: alpha(TYPE[t.session.type][mode], mode === 'dark' ? 0.12 : 0.07) }}>
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} sx={{ alignItems: { md: 'center' } }}>
            <Box sx={{ flex: 1 }}>
              <Stack direction="row" spacing={1} sx={{ alignItems: 'center', mb: 0.5 }}>
                <Typography variant="overline" color="text.secondary">Hoy</Typography><SessionChip s={t.session} />
              </Stack>
              <Typography variant="h5">{t.session.title}</Typography>
              <Typography color="text.secondary">{[plannedText(t.session), t.session.target].filter(Boolean).join(' · ')}</Typography>
              <Typography sx={{ mt: 1, color: 'text.secondary', '& b': { color: 'text.primary' } }}><Rich>{t.session.description}</Rich></Typography>
            </Box>
            {t.tip && (
              <Box sx={{ p: 2, borderRadius: '16px', bgcolor: 'background.paper', maxWidth: { md: 360 } }}>
                <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>Según tu preparación</Typography>
                <Typography><Rich>{t.tip}</Rich></Typography>
              </Box>
            )}
          </Stack>
        </Card>
      )}

      {/* semana */}
      <Stack direction="row" sx={{ alignItems: 'center', justifyContent: 'space-between', gap: 1, mt: { xs: 4, sm: 5 }, mb: 2 }}>
        <Typography variant="h6" sx={{ minWidth: 0 }}>Semana {wi + 1} · {week.focus}</Typography>
        <Button variant="outlined" size="small" startIcon={<WatchRounded />} onClick={() => setWatchOpen(true)}
          sx={{ borderRadius: 999, flexShrink: 0, whiteSpace: 'nowrap' }}>Pasar al reloj</Button>
      </Stack>
      <WatchDialog open={watchOpen} onClose={() => setWatchOpen(false)} weekStart={week.start} sessions={week.sessions} onView={setView} />
      {small ? (
        <Card sx={{ ...CARD_SX, p: 0.5 }}>
          {week.sessions.map((s, i) => <DayRow key={`${s.date}-${s.type}`} s={s} go={go} first={i === 0} />)}
        </Card>
      ) : (
        <Box sx={{ display: 'grid', gap: 1.5, gridTemplateColumns: { sm: 'repeat(4, 1fr)', lg: 'repeat(7, 1fr)' } }}>
          {week.sessions.map((s) => <DayCard key={`${s.date}-${s.type}`} s={s} go={go} onSaved={setView} sets={(id) => data.activities.find((x) => x.id === id)?.sets} />)}
        </Box>
      )}

      {/* planificado vs real */}
      <SectionTitle>Planificado frente a hecho</SectionTitle>
      <Card sx={{ ...CARD_SX }}>
        <BarChart height={260} sx={chartSx} grid={{ horizontal: true }} borderRadius={6}
          xAxis={[bandAxis(plan.weeks.map((w) => w.start), { weekly: true })]} yAxis={[{ ...yClean }]}
          series={[
            { data: plan.weeks.map((w) => w.plannedKm), label: 'Planificado', color: alpha(TYPE.long[mode], 0.35), valueFormatter: (v) => `${dec1(v)} km` },
            { data: plan.weeks.map((w) => (w.start <= todayIso ? w.actualKm : null)), label: 'Hecho', color: TYPE.easy[mode], valueFormatter: (v) => (v == null ? '–' : `${dec1(v)} km`) },
          ]} />
      </Card>

      {/* coach */}
      <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', md: last?.kind === 'adapt' ? '1fr 1fr' : '1fr' }, mt: 2 }}>
        <Card sx={{ ...CARD_SX }}>
          <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center', mb: 2 }}>
            <IconBubble color={TYPE.race[mode]}><PsychologyRounded /></IconBubble>
            <Box><Typography variant="subtitle1">Lo que tu coach sabe de ti</Typography>
              <Typography variant="caption" color="text.secondary">Se actualiza en cada ajuste con tus datos y valoraciones</Typography></Box>
          </Stack>
          <Stack spacing={1.75}>
            {plan.memory.map((m, i) => {
              const it = typeof m === 'string' ? { topic: 'preferencias' as const, title: '', detail: m } : m;
              const tc = TOPIC[it.topic] ?? TOPIC.preferencias;
              return (
                <Stack key={i} direction="row" spacing={1.5} sx={{ alignItems: 'flex-start' }}>
                  <IconBubble color={tc.color[mode]} size={30}>{tc.icon}</IconBubble>
                  <Box sx={{ minWidth: 0, pt: 0.25 }}>
                    {it.title && <Typography variant="body2" sx={{ fontWeight: 600 }}>{it.title}</Typography>}
                    <Typography variant="body2" color="text.secondary" sx={{ '& b': { color: 'text.primary' } }}><Rich>{it.detail}</Rich></Typography>
                  </Box>
                </Stack>
              );
            })}
          </Stack>
        </Card>
        {last && last.kind === 'adapt' && (
          <Card sx={{ ...CARD_SX }}>
            <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center', mb: 1.5 }}>
              <IconBubble color={TYPE.long[mode]}><FlagRounded /></IconBubble>
              <Box><Typography variant="subtitle1">Último ajuste</Typography>
                <Typography variant="caption" color="text.secondary">{dateShort(new Date(last.at))} · se reajusta solo cada lunes</Typography></Box>
            </Stack>
            {last.changes?.length ? (
              <>
                <Typography sx={{ fontWeight: 500, mb: 1.25 }}><Rich>{last.message}</Rich></Typography>
                <Stack spacing={1}>
                  {last.changes.map((c, i) => (
                    <Typography key={i} variant="body2" component="div" sx={{ display: 'flex', gap: 1.25, color: 'text.secondary', '& b': { color: 'text.primary' } }}>
                      <Box sx={{ height: '1lh', display: 'flex', alignItems: 'center', flexShrink: 0 }}>
                        <Box sx={{ width: 6, height: 6, borderRadius: '50%', bgcolor: TYPE.long[mode] }} />
                      </Box>
                      <span><Rich>{c}</Rich></span>
                    </Typography>
                  ))}
                </Stack>
              </>
            ) : (
              <Typography variant="body2" color="text.secondary" sx={{ '& b': { color: 'text.primary' } }}><Rich>{last.message}</Rich></Typography>
            )}
          </Card>
        )}
      </Box>

      {/* plan completo */}
      <SectionTitle>Plan completo</SectionTitle>
      {plan.weeks.map((w, i) => (
        <Accordion key={w.start} disableGutters defaultExpanded={false} elevation={0}
          sx={{ mb: 1, borderRadius: '16px !important', bgcolor: 'background.paper', '&::before': { display: 'none' } }}>
          <AccordionSummary expandIcon={<ExpandMoreRounded />} sx={{ '& .MuiAccordionSummary-content': { minWidth: 0 } }}>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={{ xs: 0.25, sm: 2 }} sx={{ alignItems: { sm: 'center' }, width: '100%', minWidth: 0, pr: 1 }}>
              <Stack direction="row" sx={{ justifyContent: 'space-between', minWidth: { sm: 92 }, gap: 1 }}>
                <Typography sx={{ fontWeight: 600 }}>Semana {i + 1}</Typography>
                <Typography variant="body2" color="text.secondary" sx={{ whiteSpace: 'nowrap', display: { sm: 'none' } }}>
                  {w.start <= todayIso ? `${dec1(w.actualKm)} / ` : ''}{dec1(w.plannedKm)} km
                </Typography>
              </Stack>
              <Typography variant="body2" color="text.secondary" sx={{ flex: 1, minWidth: 0, textWrap: 'pretty', lineHeight: 1.4 }}>{dateShort(toDate(w.start))} · {w.focus}</Typography>
              <Typography variant="body2" color="text.secondary" sx={{ whiteSpace: 'nowrap', display: { xs: 'none', sm: 'block' } }}>
                {w.start <= todayIso ? `${dec1(w.actualKm)} / ` : ''}{dec1(w.plannedKm)} km{w.compliance != null ? ` · ${w.compliance} %` : ''}
              </Typography>
            </Stack>
          </AccordionSummary>
          <AccordionDetails sx={{ pt: 0 }}>
            <Stack spacing={1.25}>
              {w.sessions.map((s) => (
                <Stack key={`${s.date}-${s.type}`} direction="row" spacing={1.5} sx={{ alignItems: 'flex-start', minWidth: 0 }}>
                  <StatusIcon s={s.status} />
                  <Typography variant="body2" sx={{ minWidth: { xs: 52, sm: 70 }, color: 'text.secondary', textTransform: 'capitalize' }}>
                    {toDate(s.date).toLocaleDateString('es-ES', { weekday: 'short', day: 'numeric' }).replace('.', '')}
                  </Typography>
                  <Box sx={{ flex: 1, minWidth: 0, overflowWrap: 'anywhere' }}>
                    <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap', rowGap: 0.5 }}>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>{s.title}</Typography><SessionChip s={s} compact />
                    </Stack>
                    {s.type !== 'rest' && <Typography variant="caption" color="text.secondary">{[plannedText(s), s.target].filter(Boolean).join(' · ')}</Typography>}
                    <Typography variant="body2" color="text.secondary">{s.description}</Typography>
                  </Box>
                </Stack>
              ))}
            </Stack>
          </AccordionDetails>
        </Accordion>
      ))}
    </Box>
  );
}
