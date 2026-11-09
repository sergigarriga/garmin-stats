import { useState } from 'react';
import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import Bedtime from '@mui/icons-material/Bedtime';
import { BarChart } from '@mui/x-charts/BarChart';
import { LineChart } from '@mui/x-charts/LineChart';
import { ChartsReferenceLine } from '@mui/x-charts/ChartsReferenceLine';
import { lastWith, mean, rolling, sliceRange, toDate, weekly, type GarminData, type Range } from '../data';
import { clockFromNoon, dateLong, hm, hmShort, int } from '../format';
import { SLEEP_STAGES, useCat, useResolvedMode } from '../theme';
import { bandAxis, timeAxis, yClean } from '../charts';
import { KeyFacts, sleepFacts } from '../highlights';
import { CARD_SX, ChartCard, IconBubble, InsightList, PageHeader, RangeToggle, SectionTitle, chartSx , AiBadge } from '../ui';

const STAGES = [
  { key: 'deepH', label: 'Profundo' },
  { key: 'remH', label: 'REM' },
  { key: 'lightH', label: 'Ligero' },
  { key: 'awakeH', label: 'Despierto' },
] as const;

export default function Sleep({ data }: { data: GarminData }) {
  const cat = useCat();
  const mode = useResolvedMode();
  const stageColor = SLEEP_STAGES[mode];
  const [range, setRange] = useState<Range>('90d');
  const nights = data.days.filter((d) => d.sleepH != null);
  const rows = sliceRange(nights, range, data.days[data.days.length - 1]?.d);
  const night = lastWith(nights, (d) => d.sleepH);
  const useWeeks = rows.length > 100;
  const bars = useWeeks ? weekly(rows, ['deepH', 'remH', 'lightH', 'awakeH']) : rows.map((r) => ({ ...r }));

  const avg = mean(rows.map((r) => r.sleepH));
  const under7 = rows.length ? rows.filter((r) => (r.sleepH ?? 0) < 7).length / rows.length : 0;
  const dates = rows.map((r) => toDate(r.d));

  const total = night ? (night.deepH ?? 0) + (night.remH ?? 0) + (night.lightH ?? 0) + (night.awakeH ?? 0) : 0;

  // Media por día de la semana (lunes = 0), según el día en que te despiertas.
  const wd = ['lun', 'mar', 'mié', 'jue', 'vie', 'sáb', 'dom'];
  const byWd = wd.map((_, i) => mean(rows.filter((r) => (toDate(r.d).getDay() + 6) % 7 === i).map((r) => r.sleepH)) ?? null);

  return (
    <Box>
      <PageHeader title="Sueño" subtitle={`${rows.length} noches · media ${hm(avg)} · ${Math.round(under7 * 100)} % por debajo de 7 h`}
        action={<RangeToggle value={range} onChange={setRange} />} />
      <KeyFacts facts={sleepFacts(data)} />

      {night && (
        <Card sx={{ ...CARD_SX, mb: 2 }}>
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={{ xs: 2, md: 4 }} sx={{ alignItems: { md: 'center' } }}>
            <Stack direction="row" spacing={2} sx={{ alignItems: 'center', minWidth: 260 }}>
              <IconBubble color={cat('sleep')} size={48}><Bedtime /></IconBubble>
              <Box>
                <Typography variant="body2" color="text.secondary">Última noche · {dateLong(toDate(night.d))}</Typography>
                <Typography sx={{ fontSize: 34, fontWeight: 500, lineHeight: 1.1 }}>{hm(night.sleepH)}</Typography>
                <Typography variant="body2" color="text.secondary">
                  {clockFromNoon(night.bed)} → {clockFromNoon(night.wake != null ? night.wake - 12 : undefined)}
                  {night.sleepScore != null && ` · puntuación ${night.sleepScore}`}
                </Typography>
              </Box>
            </Stack>
            <Box sx={{ flex: 1 }}>
              <Box sx={{ display: 'flex', height: 14, borderRadius: 999, overflow: 'hidden', gap: '2px' }}>
                {STAGES.map((s) => {
                  const v = night[s.key] ?? 0;
                  return v > 0 ? <Box key={s.key} sx={{ flex: v, bgcolor: stageColor[s.key.replace('H', '') as keyof typeof stageColor] }} /> : null;
                })}
              </Box>
              <Stack direction="row" spacing={3} sx={{ mt: 1.5, flexWrap: 'wrap', rowGap: 1 }}>
                {STAGES.map((s) => (
                  <Stack key={s.key} direction="row" spacing={1} sx={{ alignItems: 'center' }}>
                    <Box sx={{ width: 10, height: 10, borderRadius: '50%', bgcolor: stageColor[s.key.replace('H', '') as keyof typeof stageColor] }} />
                    <Typography variant="body2">
                      {s.label} <Box component="span" sx={{ color: 'text.secondary' }}>
                        {hmShort(night[s.key])} · {total ? Math.round(((night[s.key] ?? 0) / total) * 100) : 0} %
                      </Box>
                    </Typography>
                  </Stack>
                ))}
              </Stack>
            </Box>
          </Stack>
        </Card>
      )}

      <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', lg: '2fr 1fr' } }}>
        <ChartCard help="sleepStages" title="Duración y fases" subtitle={useWeeks ? 'Media por semana' : 'Cada noche'}>
          <BarChart
            height={300} sx={chartSx} grid={{ horizontal: true }}
            xAxis={[bandAxis(bars.map((b) => b.d as string), { weekly: useWeeks })]}
            yAxis={[{ ...yClean, valueFormatter: (v: number) => `${v} h` }]}
            series={STAGES.map((s) => ({
              data: bars.map((b) => (b[s.key] as number | null) ?? null), label: s.label, stack: 'sleep',
              color: stageColor[s.key.replace('H', '') as keyof typeof stageColor], valueFormatter: (v: number | null) => hmShort(v),
            }))}
          >
            <ChartsReferenceLine y={7} label="7 h" labelAlign="start" lineStyle={{ strokeDasharray: '4 4', stroke: 'var(--mui-palette-text-secondary)' }} />
          </BarChart>
        </ChartCard>
        <ChartCard help="weekday" title="Según el día" subtitle="Horas de media, por día en que te despiertas">
          <BarChart
            height={300} sx={chartSx} grid={{ horizontal: true }} hideLegend
            xAxis={[{ data: wd, scaleType: 'band', disableLine: true, disableTicks: true, categoryGapRatio: 0.35 }]}
            yAxis={[{ ...yClean, min: 0, valueFormatter: (v: number) => `${v} h` }]}
            series={[{ data: byWd, color: cat('sleep'), label: 'Horas', valueFormatter: (v: number | null) => hmShort(v) }]}
            borderRadius={10}
          />
        </ChartCard>
        <ChartCard help="schedule" title="Horario" subtitle="A qué hora te acuestas y te levantas (media de 7 noches)">
          <LineChart
            height={280} sx={chartSx} grid={{ horizontal: true }}
            xAxis={[timeAxis(dates)]}
            yAxis={[{ ...yClean, valueFormatter: (v: number) => clockFromNoon(v) }]}
            series={[
              { data: rolling(rows.map((r) => r.bed), 7), label: 'Te acuestas', color: cat('sleep'), showMark: false, curve: 'monotoneX', connectNulls: false, valueFormatter: (v) => clockFromNoon(v) },
              { data: rolling(rows.map((r) => (r.wake != null ? r.wake + 12 : undefined)), 7), label: 'Te levantas', color: cat('stress'), showMark: false, curve: 'monotoneX', connectNulls: false, valueFormatter: (v) => clockFromNoon(v) },
            ]}
          />
        </ChartCard>
        <ChartCard help="sleepScore" title="Puntuación de sueño" subtitle={`Media ${int(mean(rows.map((r) => r.sleepScore)))} / 100`}>
          <LineChart
            height={280} sx={chartSx} grid={{ horizontal: true }} hideLegend
            xAxis={[timeAxis(dates)]}
            yAxis={[{ ...yClean, min: 0, max: 100 }]}
            series={[
              { data: rolling(rows.map((r) => r.sleepScore), 7), label: 'Media 7 noches', color: cat('sleep'), showMark: false, curve: 'monotoneX', area: true, connectNulls: false, valueFormatter: (v) => int(v) },
            ]}
          />
        </ChartCard>
      </Box>

      <SectionTitle>Qué dicen tus datos</SectionTitle>
      {data.ai && <Box sx={{ mt: -1, mb: 2 }}><AiBadge at={data.ai.generatedAt} /></Box>}
      <InsightList items={data.ai?.sleep?.length ? data.ai.sleep : data.insights.sueno} color={cat('sleep')} />
    </Box>
  );
}
