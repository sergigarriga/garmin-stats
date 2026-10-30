import { useMemo, useState } from 'react';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import Chip from '@mui/material/Chip';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableContainer from '@mui/material/TableContainer';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Typography from '@mui/material/Typography';
import { BarChart } from '@mui/x-charts/BarChart';
import { LineChart } from '@mui/x-charts/LineChart';
import { ScatterChart } from '@mui/x-charts/ScatterChart';
import { ChartsReferenceLine } from '@mui/x-charts/ChartsReferenceLine';
import { isoLocal, sliceRange, toDate, type Activity, type GarminData, type Range } from '../data';
import { dateShort, dec1, duration, int, monthShort, pace } from '../format';
import { SPORTS, ZONES, useCat, useResolvedMode } from '../theme';
import { bandAxis, timeAxis, yClean } from '../charts';
import { CARD_SX, ChartCard, IconBubble, InsightList, PageHeader, RangeToggle, SectionTitle, chartSx , AiBadge } from '../ui';
import { SportIcon } from './sport';

const GROUPS = ['Correr', 'Cinta', 'Bici', 'Natación', 'Fuerza', 'Caminar', 'Otros'];
const ZONE_NAMES = ['Z1 muy suave', 'Z2 suave', 'Z3 moderado', 'Z4 umbral', 'Z5 máximo'];

function mondayOf(iso: string) {
  const d = toDate(iso.slice(0, 10));
  d.setDate(d.getDate() - ((d.getDay() + 6) % 7));
  return isoLocal(d);
}

/** Semanas consecutivas entre la primera y la última fecha (también las vacías). */
function weeksBetween(startIso: string, endIso: string) {
  const out: string[] = [];
  const d = toDate(mondayOf(startIso));
  const end = toDate(endIso);
  while (d <= end) { out.push(isoLocal(d)); d.setDate(d.getDate() + 7); }
  return out;
}

export default function Training({ data, go }: { data: GarminData; go: (k: string) => void }) {
  const cat = useCat();
  const mode = useResolvedMode();
  const [range, setRange] = useState<Range>('1y');
  const [showAll, setShowAll] = useState(false);
  const days = sliceRange(data.days, range);
  const start = days[0]?.d ?? data.period.start;
  const acts = data.activities.filter((a) => a.start.slice(0, 10) >= start);
  const runs = acts.filter((a) => a.group === 'Correr' || a.group === 'Cinta');

  const weeks = useMemo(() => weeksBetween(start, data.period.end), [start, data.period.end]);
  const byWeek = (pick: (a: Activity) => number, filter: (a: Activity) => boolean) => {
    const m = new Map<string, number>();
    for (const a of acts) if (filter(a)) m.set(mondayOf(a.start), (m.get(mondayOf(a.start)) ?? 0) + pick(a));
    return weeks.map((w) => m.get(w) ?? 0);
  };
  const groupsPresent = GROUPS.filter((g) => acts.some((a) => a.group === g));

  // Zonas por mes (% del tiempo).
  const months = [...new Set(acts.map((a) => a.start.slice(0, 7)))].sort();
  const zoneMonth = months.map((m) => {
    const z = [0, 0, 0, 0, 0];
    acts.filter((a) => a.start.startsWith(m)).forEach((a) => a.z.forEach((v, i) => (z[i] += v)));
    const tot = z.reduce((x, y) => x + y, 0);
    return z.map((v) => (tot ? (v / tot) * 100 : 0));
  });

  const dates = days.map((d) => toDate(d.d));
  const vo2 = acts.filter((a) => a.vo2 != null);
  const efRuns = (g: string) => runs.filter((a) => a.group === g && a.ef != null);
  const list = [...acts].reverse().slice(0, showAll ? 200 : 12);
  const totKm = runs.reduce((s, a) => s + (a.km ?? 0), 0);
  const totH = acts.reduce((s, a) => s + (a.min ?? 0), 0) / 60;

  return (
    <Box>
      <PageHeader title="Entreno"
        subtitle={`${acts.length} sesiones · ${int(totH)} h · ${int(totKm)} km corriendo`}
        action={<RangeToggle value={range} onChange={setRange} exclude={['7d']} />} />

      <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', lg: '1fr 1fr' } }}>
        <ChartCard help="volume" title="Horas por semana" subtitle="Por deporte">
          <BarChart height={300} sx={chartSx} grid={{ horizontal: true }}
            xAxis={[bandAxis(weeks, { weekly: true })]} yAxis={[{ ...yClean }]}
            series={groupsPresent.map((g) => ({
              data: byWeek((a) => (a.min ?? 0) / 60, (a) => a.group === g), label: g, stack: 'h',
              color: SPORTS[g][mode], valueFormatter: (v: number | null) => (v ? `${dec1(v)} h` : null),
            }))} />
        </ChartCard>
        <ChartCard help="km" title="Kilómetros corridos por semana">
          <BarChart height={300} sx={chartSx} grid={{ horizontal: true }}
            xAxis={[bandAxis(weeks, { weekly: true })]} yAxis={[{ ...yClean }]}
            series={['Correr', 'Cinta'].filter((g) => groupsPresent.includes(g)).map((g) => ({
              data: byWeek((a) => a.km ?? 0, (a) => a.group === g), label: g, stack: 'km',
              color: SPORTS[g][mode], valueFormatter: (v: number | null) => (v ? `${dec1(v)} km` : null),
            }))} />
        </ChartCard>
        <ChartCard help="ctl" title="Forma y fatiga" subtitle="Forma (CTL) = carga media de 42 días · Fatiga (ATL) = de 7 días">
          <LineChart height={280} sx={chartSx} grid={{ horizontal: true }}
            xAxis={[timeAxis(dates)]} yAxis={[{ ...yClean, min: 0 }]}
            series={[
              { data: days.map((d) => d.ctl ?? null), label: 'Forma', color: cat('energy'), showMark: false, curve: 'monotoneX', area: true, valueFormatter: (v) => int(v) },
              { data: days.map((d) => d.atl ?? null), label: 'Fatiga', color: cat('training'), showMark: false, curve: 'monotoneX', valueFormatter: (v) => int(v) },
            ]} />
        </ChartCard>
        <ChartCard help="acwr" title="Ratio de carga (ACWR)" subtitle="Carga 7 días ÷ media de 28. Seguro 0,8-1,3 · más de 1,5 = riesgo de lesión">
          <LineChart height={280} sx={chartSx} grid={{ horizontal: true }} hideLegend
            xAxis={[timeAxis(dates)]} yAxis={[{ ...yClean, min: 0 }]}
            series={[{ data: days.map((d) => d.acwr ?? null), label: 'ACWR', color: cat('training'), showMark: false, curve: 'linear', valueFormatter: (v) => (v == null ? '–' : v.toFixed(2).replace('.', ',')) }]}>
            <ChartsReferenceLine y={1.3} label="1,3" labelAlign="end" lineStyle={{ strokeDasharray: '4 4', stroke: 'var(--mui-palette-success-main)' }} />
            <ChartsReferenceLine y={0.8} label="0,8" labelAlign="end" lineStyle={{ strokeDasharray: '4 4', stroke: 'var(--mui-palette-success-main)' }} />
            <ChartsReferenceLine y={1.5} label="1,5" labelAlign="end" lineStyle={{ strokeDasharray: '2 3', stroke: 'var(--mui-palette-error-main)' }} />
          </LineChart>
        </ChartCard>
        <ChartCard help="zones" title="Intensidad por mes" subtitle="% del tiempo en cada zona de pulso. Para crear fondo: ~80 % en Z1-Z2">
          <BarChart height={300} sx={chartSx} grid={{ horizontal: true }}
            xAxis={[{ data: months, scaleType: 'band', disableLine: true, disableTicks: true, categoryGapRatio: 0.3,
              valueFormatter: (v: string) => monthShort(toDate(`${v}-01`)) }]}
            yAxis={[{ ...yClean, max: 100, valueFormatter: (v: number) => `${v} %` }]}
            series={ZONE_NAMES.map((n, i) => ({
              data: zoneMonth.map((z) => z[i]), label: n, stack: 'z', color: ZONES[mode][i],
              valueFormatter: (v: number | null) => `${Math.round(v ?? 0)} %`,
            }))} />
        </ChartCard>
        <ChartCard help="vo2max" title="VO2max" subtitle="Estimación del reloj tras cada carrera (leída del archivo FIT)">
          <LineChart height={300} sx={chartSx} grid={{ horizontal: true }} hideLegend
            xAxis={[timeAxis(vo2.map((a) => new Date(a.start)))]} yAxis={[{ ...yClean }]}
            series={[{ data: vo2.map((a) => a.vo2!), label: 'VO2max', color: cat('training'), curve: 'stepAfter', showMark: false, valueFormatter: (v) => `${dec1(v)} ml/kg/min` }]} />
        </ChartCard>
        <Box sx={{ gridColumn: { lg: '1 / -1' } }}>
          <ChartCard help="ef" title="Eficiencia aeróbica" subtitle="Metros por minuto por cada latido. Más alto = más rápido con el mismo pulso">
            <ScatterChart height={300} sx={chartSx} grid={{ horizontal: true }}
              xAxis={[{ scaleType: 'time', disableLine: true, disableTicks: true, valueFormatter: (v: Date) => monthShort(v) }]}
              yAxis={[{ ...yClean }]}
              series={['Correr', 'Cinta'].map((g) => ({
                label: g, color: SPORTS[g][mode], markerSize: 5,
                data: efRuns(g).map((a) => ({ x: new Date(a.start).getTime(), y: a.ef!, id: a.id })),
                valueFormatter: (v: { x: number; y: number } | null) => {
                  if (!v) return '';
                  const a = runs.find((r) => new Date(r.start).getTime() === v.x);
                  return `${dateShort(new Date(v.x))} · ${pace(a?.pace)} a ${a?.hr ?? '–'} lpm · EF ${v.y.toFixed(2)}`;
                },
              }))} />
          </ChartCard>
        </Box>
      </Box>

      {data.predictions.length > 0 && (
        <>
          <SectionTitle help="predictions">Predicciones de carrera</SectionTitle>
          <Box sx={{ display: 'grid', gap: { xs: 1.25, sm: 2 }, gridTemplateColumns: { xs: '1fr 1fr', md: 'repeat(4, 1fr)' } }}>
            {data.predictions.map((p) => (
              <Card key={p.distance} sx={{ ...CARD_SX, p: { xs: 1.75, sm: 2.75 } }}>
                <Typography variant="subtitle2" color="text.secondary">{p.distance}</Typography>
                <Typography sx={{ fontSize: { xs: 24, sm: 30 }, fontWeight: 500, letterSpacing: '-0.02em' }}>{duration(p.predicted)}</Typography>
                <Typography variant="body2" color="text.secondary">{pace(p.pace)} según tu VO2max</Typography>
                {p.best != null && (
                  <Chip size="small" sx={{ mt: 1.5 }} label={`Tu mejor: ${duration(p.best)}`} />
                )}
              </Card>
            ))}
          </Box>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 1.5 }}>
            Fórmula de Daniels con el VO2max del reloj. Es optimista si no entrenas tiradas largas para esa distancia.
          </Typography>
        </>
      )}

      <SectionTitle>Qué dicen tus datos</SectionTitle>
      {data.ai && <Box sx={{ mt: -1, mb: 2 }}><AiBadge at={data.ai.generatedAt} /></Box>}
      <InsightList items={data.ai?.training?.length ? data.ai.training : [...data.insights.entreno, ...data.insights.carrera.filter((t) => !t.startsWith('Mejor '))]} color={cat('training')} />

      <SectionTitle>Actividades</SectionTitle>
      <Card sx={{ ...CARD_SX, p: 0.5, display: { xs: 'block', md: 'none' } }}>
        {list.map((a, i) => (
          <Stack key={a.id} direction="row" spacing={1.5} onClick={() => go(`act-${a.id}`)}
            sx={{ alignItems: 'center', px: 1.5, py: 1.25, cursor: 'pointer', borderTop: i ? 1 : 0, borderColor: 'divider', minWidth: 0 }}>
            <IconBubble color={SPORTS[a.group]?.[mode] ?? cat('training')} size={34}><SportIcon group={a.group} /></IconBubble>
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <Typography variant="body2" noWrap sx={{ fontWeight: 600 }}>{a.name ?? a.group}</Typography>
              <Typography variant="caption" color="text.secondary" noWrap sx={{ display: 'block' }}>
                {[a.km ? `${dec1(a.km)} km` : null, duration((a.min ?? 0) * 60), a.km && a.km > 0.5 ? pace(a.pace) : null, a.hr ? `${a.hr} lpm` : null].filter(Boolean).join(' · ')}
              </Typography>
            </Box>
            <Typography variant="caption" color="text.secondary" sx={{ whiteSpace: 'nowrap' }}>{dateShort(new Date(a.start))}</Typography>
          </Stack>
        ))}
        {acts.length > 12 && (
          <Box sx={{ p: 1, textAlign: 'center' }}>
            <Button onClick={() => setShowAll((s) => !s)}>{showAll ? 'Ver menos' : `Ver todas (${acts.length})`}</Button>
          </Box>
        )}
      </Card>
      <Card sx={{ ...CARD_SX, p: 0, display: { xs: 'none', md: 'block' } }}>
        <TableContainer>
          <Table size="small">
            <TableHead>
              <TableRow>
                {['Actividad', 'Fecha', 'Distancia', 'Tiempo', 'Ritmo', 'FC media', 'Carga', 'VO2max'].map((h, i) => (
                  <TableCell key={h} align={i > 1 ? 'right' : 'left'} sx={{ color: 'text.secondary', fontWeight: 500, py: 1.5 }}>{h}</TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {list.map((a) => (
                <TableRow key={a.id} hover onClick={() => go(`act-${a.id}`)} sx={{ cursor: 'pointer' }}>
                  <TableCell>
                    <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center' }}>
                      <IconBubble color={SPORTS[a.group]?.[mode] ?? cat('training')} size={30}><SportIcon group={a.group} /></IconBubble>
                      <Typography variant="body2" sx={{ fontWeight: 500 }}>{a.name ?? a.group}</Typography>
                    </Stack>
                  </TableCell>
                  <TableCell sx={{ whiteSpace: 'nowrap' }}>{dateShort(new Date(a.start))}</TableCell>
                  <TableCell align="right">{a.km ? `${dec1(a.km)} km` : '–'}</TableCell>
                  <TableCell align="right">{duration((a.min ?? 0) * 60)}</TableCell>
                  <TableCell align="right" sx={{ whiteSpace: 'nowrap' }}>{a.km && a.km > 0.5 ? pace(a.pace) : '–'}</TableCell>
                  <TableCell align="right">{a.hr ?? '–'}</TableCell>
                  <TableCell align="right">{int(a.trimp)}</TableCell>
                  <TableCell align="right">{a.vo2 != null ? dec1(a.vo2) : '–'}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
        {acts.length > 12 && (
          <Box sx={{ p: 1.5, textAlign: 'center' }}>
            <Button onClick={() => setShowAll((s) => !s)}>{showAll ? 'Ver menos' : `Ver todas (${acts.length})`}</Button>
          </Box>
        )}
      </Card>
    </Box>
  );
}
