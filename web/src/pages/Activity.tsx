import { useState } from 'react';
import Box from '@mui/material/Box';
import { BarChart } from '@mui/x-charts/BarChart';
import { LineChart } from '@mui/x-charts/LineChart';
import { ChartsReferenceLine } from '@mui/x-charts/ChartsReferenceLine';
import { mean, rolling, sliceRange, toDate, weekly, type GarminData, type Range } from '../data';
import { int } from '../format';
import { useCat } from '../theme';
import { bandAxis, timeAxis, yClean } from '../charts';
import { KeyFacts, activityFacts } from '../highlights';
import { AiBadge, ChartCard, InsightList, PageHeader, RangeToggle, SectionTitle, chartSx } from '../ui';
import { Weight, YearInActivity } from './Progress';

export default function Activity({ data, go }: { data: GarminData; go: (k: string) => void }) {
  const cat = useCat();
  const [range, setRange] = useState<Range>('90d');
  const rows = sliceRange(data.days, range);
  const useWeeks = rows.length > 100;
  const steps = useWeeks ? weekly(rows, ['steps', 'stepGoal']) : rows;
  const im = weekly(rows.map((r) => ({ ...r, im: (r.imMod ?? 0) + 2 * (r.imVig ?? 0) })), ['im'], 'sum');
  const goal = mean(rows.map((r) => r.stepGoal)) ?? 10000;
  const ref = { strokeDasharray: '4 4', stroke: 'var(--mui-palette-text-secondary)' };

  return (
    <Box>
      <PageHeader title="Actividad diaria"
        subtitle={`Media ${int(mean(rows.map((r) => r.steps)))} pasos al día · ${int(mean(rows.map((r) => r.floors)))} pisos`}
        action={<RangeToggle value={range} onChange={setRange} />} />
      <KeyFacts facts={activityFacts(data)} />
      <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', lg: '1fr 1fr' } }}>
        <Box sx={{ gridColumn: { lg: '1 / -1' } }}>
          <ChartCard help="steps" title="Pasos" subtitle={useWeeks ? 'Media diaria por semana' : 'Cada día'}>
            <BarChart height={300} sx={chartSx} grid={{ horizontal: true }} hideLegend borderRadius={6}
              xAxis={[bandAxis(steps.map((s) => s.d as string), { weekly: useWeeks })]}
              yAxis={[{ ...yClean }]}
              series={[{ data: steps.map((s) => (s.steps as number | null) ?? null), label: 'Pasos', color: cat('activity'), valueFormatter: (v) => int(v) }]}>
              <ChartsReferenceLine y={goal} label={`Objetivo ${int(goal)}`} labelAlign="end" lineStyle={ref} />
            </BarChart>
          </ChartCard>
        </Box>
        <ChartCard help="intensity" title="Minutos de intensidad por semana" subtitle="Moderados + vigorosos ×2. La OMS recomienda 150">
          <BarChart height={280} sx={chartSx} grid={{ horizontal: true }} hideLegend borderRadius={8}
            xAxis={[bandAxis(im.map((s) => s.d), { weekly: true })]}
            yAxis={[{ ...yClean }]}
            series={[{ data: im.map((s) => (s.im as number | null) ?? null), label: 'Minutos', color: cat('activity'), valueFormatter: (v) => `${int(v)} min` }]}>
            <ChartsReferenceLine y={150} label="150 min" labelAlign="end" lineStyle={ref} />
          </BarChart>
        </ChartCard>
        <ChartCard help="calActive" title="Calorías activas" subtitle="Media de 7 días">
          <LineChart height={280} sx={chartSx} grid={{ horizontal: true }} hideLegend
            xAxis={[timeAxis(rows.map((r) => toDate(r.d)))]} yAxis={[{ ...yClean, min: 0 }]}
            series={[{ data: rolling(rows.map((r) => r.calActive), 7), label: 'kcal', color: cat('training'), showMark: false, curve: 'monotoneX', area: true, connectNulls: false, valueFormatter: (v) => `${int(v)} kcal` }]}
          />
        </ChartCard>
      </Box>
      {data.ai?.activity?.length ? (
        <>
          <SectionTitle>Qué dicen tus datos</SectionTitle>
          <Box sx={{ mt: -1, mb: 2 }}><AiBadge at={data.ai.generatedAt} /></Box>
          <InsightList items={data.ai.activity} color={cat('activity')} />
        </>
      ) : null}
      <YearInActivity data={data} go={go} />
      <Weight data={data} />
    </Box>
  );
}
