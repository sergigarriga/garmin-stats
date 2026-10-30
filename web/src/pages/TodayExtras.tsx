import { useState } from 'react';
import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import IconButton from '@mui/material/IconButton';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { alpha } from '@mui/material/styles';
import { Gauge, gaugeClasses } from '@mui/x-charts/Gauge';
import CloseRounded from '@mui/icons-material/CloseRounded';
import CheckCircleRounded from '@mui/icons-material/CheckCircleRounded';
import TrendingDownRounded from '@mui/icons-material/TrendingDownRounded';
import FlagRounded from '@mui/icons-material/FlagRounded';
import LocalFireDepartmentRounded from '@mui/icons-material/LocalFireDepartmentRounded';
import InfoOutlined from '@mui/icons-material/InfoOutlined';
import { isoLocal, streaks, toDate, type Alert, type GarminData, type WeekStats } from '../data';
import { dateShort, dec1, hm, int } from '../format';
import { CATEGORY, useResolvedMode } from '../theme';
import { AiBadge, CARD_SX, IconBubble, InfoTip } from '../ui';
import { Rich } from '../rich';

// ------------------------------------------------------------------ avisos
const DISMISS_KEY = 'garmin-stats:dismissed';
function readDismissed(): string[] {
  try { return JSON.parse(localStorage.getItem(DISMISS_KEY) ?? '[]'); } catch { return []; }
}

export function Alerts({ alerts }: { alerts?: Alert[] }) {
  const mode = useResolvedMode();
  const [hidden, setHidden] = useState<string[]>(readDismissed);
  const shown = (alerts ?? []).filter((a) => !hidden.includes(`${a.id}:${a.date}`));
  if (!shown.length) return null;
  const hide = (a: Alert) => {
    const next = [...hidden, `${a.id}:${a.date}`].slice(-50);
    setHidden(next);
    try { localStorage.setItem(DISMISS_KEY, JSON.stringify(next)); } catch { /* sin almacenamiento */ }
  };
  return (
    <Stack spacing={1.5} sx={{ mb: 3 }}>
      {shown.map((a) => {
        const color = CATEGORY[a.category]?.[mode] ?? CATEGORY.energy[mode];
        return (
          <Card key={a.id} sx={{ ...CARD_SX, py: 2, display: 'flex', gap: 2, alignItems: 'flex-start',
            bgcolor: alpha(color, mode === 'dark' ? 0.14 : 0.09), border: 1, borderColor: alpha(color, 0.3) }}>
            <IconBubble color={color} size={36}><InfoOutlined /></IconBubble>
            <Box sx={{ flex: 1 }}>
              <Typography variant="subtitle1">{a.title}</Typography>
              <Typography color="text.secondary">{a.body}</Typography>
            </Box>
            <IconButton size="small" aria-label="Ocultar aviso" onClick={() => hide(a)}><CloseRounded fontSize="small" /></IconButton>
          </Card>
        );
      })}
    </Stack>
  );
}

// ------------------------------------------------------------------ preparación
const READY_COLOR = (s: number, mode: 'light' | 'dark') =>
  s >= 80 ? CATEGORY.activity[mode] : s >= 60 ? CATEGORY.recovery[mode] : s >= 40 ? CATEGORY.stress[mode] : CATEGORY.heart[mode];

export function ReadinessCard({ data }: { data: GarminData }) {
  const mode = useResolvedMode();
  const r = data.readiness;
  if (!r) return null;
  const color = READY_COLOR(r.score, mode);
  const today = isoLocal(new Date());
  if (r.date !== today) {
    return (
      <Card sx={{ ...CARD_SX, mb: 2, display: 'flex', gap: 2, alignItems: 'center' }}>
        <Box sx={{ width: 64, height: 64, borderRadius: '50%', border: '6px solid', borderColor: 'divider', display: 'grid', placeItems: 'center', flexShrink: 0 }}>
          <Typography sx={{ fontSize: 22, fontWeight: 500, color: 'text.secondary' }}>—</Typography>
        </Box>
        <Box>
          <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
            <Typography variant="overline" color="text.secondary" sx={{ lineHeight: 1.5 }}>Preparación</Typography>
            <InfoTip k="readiness" />
          </Stack>
          <Typography sx={{ fontWeight: 500 }}>Aún no hay datos de esta noche</Typography>
          <Typography variant="body2" color="text.secondary">Sincroniza el reloj con la app de Garmin y se calculará solo (en menos de una hora).</Typography>
        </Box>
      </Card>
    );
  }
  return (
    <Card sx={{ ...CARD_SX, mb: 2, background: mode === 'dark'
      ? `linear-gradient(135deg, ${alpha(color, 0.16)}, transparent 60%)` : `linear-gradient(135deg, ${alpha(color, 0.12)}, #fff 60%)` }}>
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={{ xs: 2, md: 5 }} sx={{ alignItems: { md: 'center' } }}>
        <Stack direction="row" spacing={3} sx={{ alignItems: 'center' }}>
          <Box sx={{ position: 'relative', width: 150, height: 150, flexShrink: 0 }}>
            <Gauge width={150} height={150} value={r.score} valueMax={100} innerRadius="80%" outerRadius="100%" cornerRadius="50%" text=""
              sx={{ [`& .${gaugeClasses.valueArc}`]: { fill: color }, [`& .${gaugeClasses.referenceArc}`]: { fill: alpha(color, 0.16) } }} />
            <Box sx={{ position: 'absolute', inset: 0, display: 'grid', placeContent: 'center', textAlign: 'center' }}>
              <Typography sx={{ fontSize: 40, fontWeight: 500, lineHeight: 1 }}>{r.score}</Typography>
              <Typography variant="caption" color="text.secondary">de 100</Typography>
            </Box>
          </Box>
          <Box>
            <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
              <Typography variant="overline" color="text.secondary" sx={{ lineHeight: 1.5 }}>Preparación</Typography>
              <InfoTip k="readiness" />
            </Stack>
            <Typography sx={{ fontSize: 28, fontWeight: 500, color, lineHeight: 1.2 }}>{r.label}</Typography>
            <Typography sx={{ mt: 0.5, maxWidth: 340 }}>{r.message}</Typography>
            {r.date !== today && <Typography variant="caption" color="text.secondary">Con datos del {dateShort(toDate(r.date))}</Typography>}
          </Box>
        </Stack>
        <Box sx={{ flex: 1, display: 'grid', gap: { xs: 1.5, sm: 1.75 }, columnGap: { xs: 2, sm: 3 }, gridTemplateColumns: '1fr 1fr' }}>
          {r.parts.map((p) => {
            const c = READY_COLOR(p.score, mode);
            return (
              <Box key={p.key}>
                <Stack direction="row" sx={{ justifyContent: 'space-between' }}>
                  <Typography variant="body2" sx={{ fontWeight: 500 }}>{p.label}</Typography>
                  <Typography variant="body2" color="text.secondary">{p.score}</Typography>
                </Stack>
                <Box sx={{ height: 6, borderRadius: 999, bgcolor: alpha(c, 0.16), my: 0.75, overflow: 'hidden' }}>
                  <Box sx={{ width: `${p.score}%`, height: '100%', bgcolor: c, borderRadius: 999 }} />
                </Box>
                <Typography variant="caption" color="text.secondary" sx={{ display: 'block', lineHeight: 1.35 }}>{p.detail}</Typography>
              </Box>
            );
          })}
        </Box>
      </Stack>
    </Card>
  );
}

// ------------------------------------------------------------------ objetivos y rachas
function MiniRing({ value, max, color, center, sub }: { value: number; max: number; color: string; center: string; sub: string }) {
  return (
    <Box sx={{ position: 'relative', width: 116, height: 116 }}>
      <Gauge width={116} height={116} value={Math.min(value, max)} valueMax={max} innerRadius="84%" outerRadius="100%" cornerRadius="50%" text=""
        sx={{ [`& .${gaugeClasses.valueArc}`]: { fill: color }, [`& .${gaugeClasses.referenceArc}`]: { fill: alpha(color, 0.16) } }} />
      <Box sx={{ position: 'absolute', inset: 0, display: 'grid', placeContent: 'center', textAlign: 'center', px: 2.5 }}>
        <Typography sx={{ fontSize: center.length > 5 ? 17 : center.length > 3 ? 20 : 22, fontWeight: 600, lineHeight: 1.1, letterSpacing: '-0.02em' }}>{center}</Typography>
        <Typography variant="caption" color="text.secondary" sx={{ lineHeight: 1.2 }}>{sub}</Typography>
      </Box>
    </Box>
  );
}

export function Goals({ data }: { data: GarminData }) {
  const mode = useResolvedMode();
  const days = data.days;
  const now = new Date();
  const monday = new Date(now); monday.setDate(now.getDate() - ((now.getDay() + 6) % 7));
  const mon = isoLocal(monday);
  const week = days.filter((d) => d.d >= mon);
  const acts = data.activities.filter((a) => a.start.slice(0, 10) >= mon);
  const sleepOk = (d: (typeof days)[number]) => (d.sleepH == null ? null : d.sleepH >= 7);
  const stepsOk = (d: (typeof days)[number]) => (d.steps == null ? null : d.steps >= (d.stepGoal ?? 10000));
  const goals = [
    { key: 'sleep', label: 'Noches de 7 h', value: week.filter((d) => sleepOk(d)).length, max: 5, cat: 'sleep' as const,
      streak: streaks(days, sleepOk), unit: 'noches', sub: 'noches' },
    { key: 'steps', label: 'Objetivo de pasos', value: week.filter((d) => stepsOk(d)).length, max: 5, cat: 'activity' as const,
      streak: streaks(days, stepsOk), unit: 'días', sub: 'días' },
    { key: 'im', label: 'Intensidad', value: week.reduce((s, d) => s + (d.imMod ?? 0) + 2 * (d.imVig ?? 0), 0), max: 150,
      cat: 'energy' as const, sub: 'min' },
    { key: 'train', label: 'Entrenos', value: acts.length, max: 3, cat: 'training' as const, sub: 'sesiones' },
  ];
  return (
    <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr 1fr', lg: 'repeat(4, 1fr)' } }}>
      {goals.map((g) => {
        const color = CATEGORY[g.cat][mode];
        const done = g.value >= g.max;
        const left = Math.max(0, g.max - g.value);
        return (
          <Card key={g.key} sx={{ ...CARD_SX, display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center', gap: 1.25 }}>
            <MiniRing value={g.value} max={g.max} color={color} center={`${int(g.value)}/${int(g.max)}`} sub={g.sub} />
            <Typography variant="subtitle2" noWrap sx={{ maxWidth: '100%' }}>{g.label}</Typography>
            <Typography variant="body2" sx={{ color: done ? 'success.main' : 'text.secondary', fontWeight: done ? 500 : 400 }} noWrap>
              {done ? 'Conseguido esta semana' : `Faltan ${int(left)} ${g.sub}`}
            </Typography>
            <Stack direction="row" spacing={0.5} sx={{ alignItems: 'center', justifyContent: 'center', minHeight: 20, mt: 'auto' }}>
              {g.streak ? (
                <>
                  <LocalFireDepartmentRounded sx={{ fontSize: 16, color: g.streak.current ? '#E8710A' : 'text.disabled' }} />
                  <Typography variant="caption" color="text.secondary" noWrap>
                    Racha {g.streak.current} · mejor {g.streak.best} {g.unit}
                  </Typography>
                </>
              ) : (
                <Typography variant="caption" color="text.secondary" noWrap>Meta semanal</Typography>
              )}
            </Stack>
          </Card>
        );
      })}
    </Box>
  );
}

// ------------------------------------------------------------------ tu semana
function Delta({ label, a, b, fmt, good }: { label: string; a?: number | null; b?: number | null; fmt: (v: number) => string; good: 'up' | 'down' }) {
  const d = a != null && b != null ? a - b : null;
  const better = d == null || Math.abs(d) < 1e-6 ? null : good === 'up' ? d > 0 : d < 0;
  return (
    <Box>
      <Typography variant="caption" color="text.secondary">{label}</Typography>
      <Typography sx={{ fontWeight: 500 }}>{a == null ? '–' : fmt(a)}</Typography>
      {d != null && (
        <Typography variant="caption" sx={{ color: better == null ? 'text.secondary' : better ? 'success.main' : 'error.main' }}>
          {d > 0 ? '▲' : d < 0 ? '▼' : '='} vs {b == null ? '–' : fmt(b)}
        </Typography>
      )}
    </Box>
  );
}

export function WeekCard({ data }: { data: GarminData }) {
  const mode = useResolvedMode();
  const w = data.weekly;
  if (!w?.last) return null;
  const L: WeekStats = w.last, P: WeekStats = w.previous;
  const color = CATEGORY.energy[mode];
  return (
    <Card sx={{ ...CARD_SX }}>
      <Stack direction="row" sx={{ justifyContent: 'space-between', alignItems: 'flex-start', mb: 1.5 }} spacing={2}>
        <Box>
          <Typography variant="overline" color="text.secondary">Semana del {dateShort(toDate(L.start))} al {dateShort(toDate(L.end))}</Typography>
          <Typography variant="h6" sx={{ lineHeight: 1.3 }}>{w.title ?? (L.daysWorn < 2 ? 'Semana con muy pocos datos del reloj' : 'Tu semana')}</Typography>
        </Box>
        {w.generatedAt && <AiBadge at={w.generatedAt} />}
      </Stack>
      <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr 1fr', sm: 'repeat(3, 1fr)', md: 'repeat(6, 1fr)' }, mb: (w.went_well?.length || w.worse?.length) ? 2.5 : 0 }}>
        <Delta label="Sueño medio" a={L.sleepH} b={P.sleepH} fmt={hm} good="up" />
        <Delta label="Pasos al día" a={L.steps} b={P.steps} fmt={int} good="up" />
        <Delta label="Pulso en reposo" a={L.rhr} b={P.rhr} fmt={(v) => `${dec1(v)} lpm`} good="down" />
        <Delta label="HRV" a={L.hrv} b={P.hrv} fmt={(v) => `${int(v)} ms`} good="up" />
        <Delta label="Entrenos" a={L.sessions} b={P.sessions} fmt={int} good="up" />
        <Delta label="Km corridos" a={L.runKm} b={P.runKm} fmt={(v) => `${dec1(v)} km`} good="up" />
      </Box>
      {(w.went_well?.length || w.worse?.length || w.goal) ? (
        <Stack spacing={1.25}>
          {w.went_well?.map((t, i) => (
            <Stack key={`g${i}`} direction="row" spacing={1.25}><CheckCircleRounded sx={{ fontSize: 20, color: CATEGORY.activity[mode], mt: 0.2 }} /><Typography color="text.secondary"><Rich>{t}</Rich></Typography></Stack>
          ))}
          {w.worse?.map((t, i) => (
            <Stack key={`w${i}`} direction="row" spacing={1.25}><TrendingDownRounded sx={{ fontSize: 20, color: CATEGORY.stress[mode], mt: 0.2 }} /><Typography color="text.secondary"><Rich>{t}</Rich></Typography></Stack>
          ))}
          {w.goal && (
            <Stack direction="row" spacing={1.25} sx={{ p: 1.5, borderRadius: '14px', bgcolor: alpha(color, 0.08) }}>
              <FlagRounded sx={{ fontSize: 20, color, mt: 0.2 }} /><Typography><b>Para esta semana:</b> <Rich>{w.goal}</Rich></Typography>
            </Stack>
          )}
        </Stack>
      ) : L.daysWorn < 2 ? (
        <Typography color="text.secondary">La semana pasada casi no llevaste el reloj ({L.daysWorn} días), así que no hay resumen. El lunes que viene saldrá el de esta semana.</Typography>
      ) : null}
    </Card>
  );
}
