import { useState } from 'react';
import Box from '@mui/material/Box';
import { LineChart } from '@mui/x-charts/LineChart';
import { mean, rolling, sliceRange, toDate, type GarminData, type Range } from '../data';
import { int } from '../format';
import { alpha } from '@mui/material/styles';
import { useCat, useResolvedMode } from '../theme';
import { timeAxis, yClean } from '../charts';
import { ChartCard, InsightList, PageHeader, RangeToggle, SectionTitle, chartSx , AiBadge } from '../ui';

export default function Heart({ data }: { data: GarminData }) {
  const cat = useCat();
  const band = useResolvedMode() === 'dark' ? '#8E918F' : '#B0B4B8';
  const [range, setRange] = useState<Range>('90d');
  const rows = sliceRange(data.days, range);
  const dates = rows.map((r) => toDate(r.d));
  const win = rows.length > 120 ? 14 : 7;
  const fmt = (u: string) => (v: number | null) => (v == null ? '–' : `${int(v)} ${u}`);

  // Banda del rango normal de HRV: base transparente + alto del rango, apiladas.
  const low = rolling(rows.map((r) => r.hrvLow), 3, 1);
  const high = rolling(rows.map((r) => r.hrvHigh), 3, 1);

  return (
    <Box>
      <PageHeader title="Corazón y recuperación"
        subtitle={`FC en reposo media ${int(mean(rows.map((r) => r.rhr)))} lpm · HRV media ${int(mean(rows.map((r) => r.hrv)))} ms`}
        action={<RangeToggle value={range} onChange={setRange} />} />

      <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', lg: '1fr 1fr' } }}>
        <ChartCard help="rhr" title="FC en reposo" subtitle="Más baja suele indicar mejor forma y recuperación">
          <LineChart height={280} sx={chartSx} grid={{ horizontal: true }}
            xAxis={[timeAxis(dates)]} yAxis={[{ ...yClean }]}
            series={[
              { data: rows.map((r) => r.rhr ?? null), label: 'Cada día', color: alpha(cat('heart'), 0.3), showMark: false, curve: 'linear', connectNulls: false, valueFormatter: fmt('lpm'), id: 'raw' },
              { data: rolling(rows.map((r) => r.rhr), win), label: `Media ${win} días`, color: cat('heart'), showMark: false, curve: 'monotoneX', connectNulls: false, valueFormatter: fmt('lpm'), id: 'avg' },
            ]}
          />
        </ChartCard>
        <ChartCard help="hrv" title="HRV nocturna" subtitle="Banda gris: tu rango normal según Garmin">
          <LineChart height={280} sx={chartSx}
            grid={{ horizontal: true }}
            xAxis={[timeAxis(dates)]} yAxis={[{ ...yClean }]}
            series={[
              { id: 'band0', data: low, stack: 'band', area: true, showMark: false, color: 'transparent', label: 'Rango normal (mín.)', valueFormatter: fmt('ms'), connectNulls: false },
              { id: 'band1', data: high.map((h, i) => (h != null && low[i] != null ? h - low[i]! : null)), stack: 'band', area: true, showMark: false, color: band, label: 'Rango normal (máx.)', valueFormatter: (_v, ctx) => fmt('ms')(high[ctx.dataIndex]), connectNulls: false },
              { id: 'hrv', data: rolling(rows.map((r) => r.hrv), win, 2), label: `HRV media ${win} noches`, color: cat('recovery'), showMark: false, curve: 'monotoneX', connectNulls: false, valueFormatter: fmt('ms') },
            ]}
            hideLegend
          />
        </ChartCard>
        <ChartCard help="stress" title="Estrés medio diario" subtitle="0-100, calculado con tu pulso. Menos de 25 = descanso">
          <LineChart height={280} sx={chartSx} grid={{ horizontal: true }} hideLegend
            xAxis={[timeAxis(dates)]} yAxis={[{ ...yClean, min: 0 }]}
            series={[{ data: rolling(rows.map((r) => r.stress), win), label: `Media ${win} días`, color: cat('stress'), showMark: false, curve: 'monotoneX', area: true, connectNulls: false, valueFormatter: (v) => int(v) }]}
          />
        </ChartCard>
        <ChartCard help="bodyBattery" title="Body Battery" subtitle="Máximo (al levantarte) y mínimo (al acostarte)">
          <LineChart height={280} sx={chartSx} grid={{ horizontal: true }}
            xAxis={[timeAxis(dates)]} yAxis={[{ ...yClean, min: 0, max: 100 }]}
            series={[
              { data: rolling(rows.map((r) => r.bbMax), win), label: 'Máximo', color: cat('energy'), showMark: false, curve: 'monotoneX', connectNulls: false, valueFormatter: (v) => int(v) },
              { data: rolling(rows.map((r) => r.bbMin), win), label: 'Mínimo', color: cat('stress'), showMark: false, curve: 'monotoneX', connectNulls: false, valueFormatter: (v) => int(v) },
            ]}
          />
        </ChartCard>
      </Box>

      <SectionTitle>Qué dicen tus datos</SectionTitle>
      {data.ai && <Box sx={{ mt: -1, mb: 2 }}><AiBadge at={data.ai.generatedAt} /></Box>}
      <InsightList items={data.ai?.heart?.length ? data.ai.heart : data.insights.corazon} color={cat('heart')} />
    </Box>
  );
}
