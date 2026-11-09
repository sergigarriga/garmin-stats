import { useMemo } from 'react';
import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import Stack from '@mui/material/Stack';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import { alpha } from '@mui/material/styles';
import EmojiEventsOutlined from '@mui/icons-material/EmojiEventsOutlined';
import { isoLocal, toDate, type Activity, type Day, type GarminData, type RecordItem } from '../data';
import { dateLong, dateShort, dec1, duration, int } from '../format';
import { CATEGORY, useResolvedMode } from '../theme';
import { CARD_SX, IconBubble, SectionTitle, chartSx } from '../ui';
import { LineChart } from '@mui/x-charts/LineChart';
import { timeAxis } from '../charts';
import MonitorWeightOutlined from '@mui/icons-material/MonitorWeightOutlined';

function fmtRecord(r: RecordItem) {
  switch (r.kind) {
    case 'time': return duration(r.value);
    case 'km': return `${dec1(r.value)} km`;
    case 'vo2': return `${dec1(r.value)}`;
    case 'steps': return `${int(r.value)} pasos`;
    case 'score': return `${int(r.value)} / 100`;
    case 'bpm': return `${int(r.value)} lpm`;
    case 'ms': return `${int(r.value)} ms`;
  }
}

function Heatmap({ data, go }: { data: GarminData; go: (k: string) => void }) {
  const mode = useResolvedMode();
  const color = CATEGORY.activity[mode];
  const { weeks, months } = useMemo(() => {
    const byDay = new Map(data.days.map((d) => [d.d, d]));
    const actsBy = new Map<string, Activity[]>();
    data.activities.forEach((a) => { const k = a.start.slice(0, 10); actsBy.set(k, [...(actsBy.get(k) ?? []), a]); });
    const end = toDate(data.period.end);
    const start = new Date(end); start.setDate(start.getDate() - (window.innerWidth < 600 ? 7 * Math.max(10, Math.floor((window.innerWidth - 112) / 16)) - 1 : 364));
    start.setDate(start.getDate() - ((start.getDay() + 6) % 7)); // lunes
    const weeks: { d: string; day?: Day; acts: Activity[]; future: boolean }[][] = [];
    const months: { i: number; label: string }[] = [];
    for (let cur = new Date(start), w = 0; cur <= end; w++) {
      const col = [];
      for (let k = 0; k < 7; k++) {
        const iso = isoLocal(cur);
        if (cur.getDate() === 1) months.push({ i: w, label: cur.toLocaleDateString('es-ES', { month: 'short' }).replace('.', '') });
        col.push({ d: iso, day: byDay.get(iso), acts: actsBy.get(iso) ?? [], future: cur > end });
        cur.setDate(cur.getDate() + 1);
      }
      weeks.push(col);
    }
    return { weeks, months };
  }, [data]);
  const level = (c: { day?: Day }) => {
    const s = c.day?.steps, g = c.day?.stepGoal ?? 10000;
    if (s == null) return -1;
    return s >= g ? 4 : s >= 0.75 * g ? 3 : s >= 0.5 * g ? 2 : s >= 0.25 * g ? 1 : 0;
  };
  const shade = (l: number) => (l < 0 ? alpha('#808080', 0.1) : alpha(color, [0.12, 0.3, 0.5, 0.75, 1][l]));
  const CELL = 13, GAP = 3;
  return (
    <Card sx={{ ...CARD_SX }}>
      <Box sx={{ overflowX: 'auto', pb: 1 }}>
        <Box sx={{ position: 'relative', height: 18, minWidth: weeks.length * (CELL + GAP) }}>
          {months.map((m) => (
            <Typography key={`${m.i}${m.label}`} variant="caption" color="text.secondary"
              sx={{ position: 'absolute', left: m.i * (CELL + GAP) + 26 }}>{m.label}</Typography>
          ))}
        </Box>
        <Stack direction="row" sx={{ gap: `${GAP}px` }}>
          <Stack sx={{ gap: `${GAP}px`, mr: 0.5, width: 22 }}>
            {['L', '', 'X', '', 'V', '', 'D'].map((l, i) => (
              <Typography key={i} variant="caption" color="text.secondary" sx={{ height: CELL, lineHeight: `${CELL}px`, fontSize: 10 }}>{l}</Typography>
            ))}
          </Stack>
          {weeks.map((col, w) => (
            <Stack key={w} sx={{ gap: `${GAP}px` }}>
              {col.map((c) => {
                const l = level(c);
                const tip = `${dateLong(toDate(c.d))}: ${c.day?.steps != null ? `${int(c.day.steps)} pasos` : 'sin datos'}`
                  + (c.acts.length ? ` · ${c.acts.map((a) => `${a.group}${a.km ? ` ${dec1(a.km)} km` : ''}`).join(', ')}` : '');
                return (
                  <Tooltip key={c.d} title={tip} disableInteractive>
                    <Box onClick={() => c.acts[0] && go(`act-${c.acts[0].id}`)}
                      sx={{ width: CELL, height: CELL, borderRadius: '4px', bgcolor: c.future ? 'transparent' : shade(l),
                        cursor: c.acts.length ? 'pointer' : 'default', position: 'relative',
                        '&::after': c.acts.length ? { content: '""', position: 'absolute', inset: 4, borderRadius: '50%',
                          bgcolor: mode === 'dark' ? '#0E0E0F' : '#fff' } : undefined }} />
                  </Tooltip>
                );
              })}
            </Stack>
          ))}
        </Stack>
      </Box>
      <Stack direction="row" spacing={1} sx={{ alignItems: 'center', mt: 1.5, flexWrap: 'wrap', rowGap: 1 }}>
        <Typography variant="caption" color="text.secondary">Pasos frente a tu objetivo:</Typography>
        {[0, 1, 2, 3, 4].map((l) => <Box key={l} sx={{ width: CELL, height: CELL, borderRadius: '4px', bgcolor: shade(l) }} />)}
        <Typography variant="caption" color="text.secondary" sx={{ pl: 1 }}>· punto blanco = día con entreno (pulsa para verlo)</Typography>
      </Stack>
    </Card>
  );
}

function Weight({ data }: { data: GarminData }) {
  const mode = useResolvedMode();
  const w = data.weights ?? [];
  if (w.length === 0) return null;
  const color = CATEGORY.energy[mode];
  const last = w[w.length - 1];
  const ago = (days: number) => {
    const lim = new Date(toDate(last.d)); lim.setDate(lim.getDate() - days);
    return [...w].reverse().find((x) => toDate(x.d) <= lim);
  };
  const p30 = ago(30), p90 = ago(90);
  const delta = (p?: { kg: number }) => (p ? `${last.kg - p.kg > 0 ? '+' : last.kg - p.kg < 0 ? '−' : ''}${dec1(Math.abs(last.kg - p.kg))} kg` : '–');
  const hasFat = w.some((x) => x.fat != null);
  return (
    <>
      <SectionTitle>Peso</SectionTitle>
      <Card sx={{ ...CARD_SX }}>
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={3} sx={{ alignItems: { md: 'center' }, mb: 2 }}>
          <Stack direction="row" spacing={2} sx={{ alignItems: 'center' }}>
            <IconBubble color={color} size={48}><MonitorWeightOutlined /></IconBubble>
            <Box>
              <Typography sx={{ fontSize: 30, fontWeight: 500, lineHeight: 1.1 }}>{dec1(last.kg)} kg</Typography>
              <Typography variant="body2" color="text.secondary">Último registro · {dateShort(toDate(last.d))}{last.fat != null ? ` · ${dec1(last.fat)} % grasa` : ''}</Typography>
            </Box>
          </Stack>
          <Stack direction="row" spacing={3}>
            <Box><Typography variant="caption" color="text.secondary">30 días</Typography><Typography sx={{ fontWeight: 500 }}>{delta(p30)}</Typography></Box>
            <Box><Typography variant="caption" color="text.secondary">90 días</Typography><Typography sx={{ fontWeight: 500 }}>{delta(p90)}</Typography></Box>
            <Box><Typography variant="caption" color="text.secondary">Registros</Typography><Typography sx={{ fontWeight: 500 }}>{w.length}</Typography></Box>
          </Stack>
        </Stack>
        {w.length > 1 && (
          <LineChart height={220} sx={chartSx} grid={{ horizontal: true }} hideLegend={!hasFat}
            xAxis={[timeAxis(w.map((x) => toDate(x.d)))]}
            yAxis={[{ disableLine: true, disableTicks: true, valueFormatter: (v: number) => `${dec1(v)}` }]}
            series={[{ data: w.map((x) => x.kg), label: 'Peso (kg)', color, curve: 'monotoneX', showMark: w.length < 40, valueFormatter: (v) => `${dec1(v)} kg` }]} />
        )}
        <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
          Sale de lo que apuntas en Garmin Connect. Pésate en condiciones parecidas (por la mañana, en ayunas) para que la tendencia sea fiable.
        </Typography>
      </Card>
    </>
  );
}

// Antes era la pestaña "Progreso"; ahora sus piezas viven donde se miran: récords en Entreno,
// tu año en actividad y el peso en Salud → Actividad.

/** "Tus récords" (va en Entreno → Actividades). */
export function Records({ data, go }: { data: GarminData; go: (k: string) => void }) {
  const mode = useResolvedMode();
  const recs = data.records ?? [];
  if (!recs.length) return null;
  return (
    <>
      <SectionTitle>Tus récords</SectionTitle>
      <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr 1fr', md: 'repeat(4, 1fr)' } }}>
        {recs.map((r) => {
          const color = (r.group === 'Carrera' ? CATEGORY.training : CATEGORY.recovery)[mode];
          return (
            <Card key={r.label} onClick={() => r.activityId && go(`act-${r.activityId}`)}
              sx={{ ...CARD_SX, cursor: r.activityId ? 'pointer' : 'default', display: 'flex', flexDirection: 'column', gap: 1,
                transition: 'box-shadow .2s', '&:hover': r.activityId ? { boxShadow: '0 2px 10px rgba(60,64,67,.15)' } : undefined }}>
              <IconBubble color={color} size={32}><EmojiEventsOutlined /></IconBubble>
              <Typography variant="body2" color="text.secondary">{r.label}</Typography>
              <Typography sx={{ fontSize: 24, fontWeight: 500, lineHeight: 1.15 }}>{fmtRecord(r)}</Typography>
              <Typography variant="caption" color="text.secondary">{dateShort(toDate(r.date))} {toDate(r.date).getFullYear()}</Typography>
            </Card>
          );
        })}
      </Box>
    </>
  );
}

/** "Tu año en actividad" (va en Salud → Actividad). */
export function YearInActivity({ data, go }: { data: GarminData; go: (k: string) => void }) {
  return (
    <>
      <SectionTitle>Tu año en actividad</SectionTitle>
      <Heatmap data={data} go={go} />
    </>
  );
}

export { Weight };
