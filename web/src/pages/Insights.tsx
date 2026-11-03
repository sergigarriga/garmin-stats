import { useMemo, useState, type ReactElement } from 'react';
import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import Stack from '@mui/material/Stack';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import { alpha } from '@mui/material/styles';
import { BarChart } from '@mui/x-charts/BarChart';
import Bedtime from '@mui/icons-material/Bedtime';
import BatteryChargingFull from '@mui/icons-material/BatteryChargingFull';
import MonitorHeart from '@mui/icons-material/MonitorHeart';
import Favorite from '@mui/icons-material/Favorite';
import SelfImprovement from '@mui/icons-material/SelfImprovement';
import DirectionsWalk from '@mui/icons-material/DirectionsWalk';
import DirectionsRun from '@mui/icons-material/DirectionsRun';
import Watch from '@mui/icons-material/WatchOutlined';
import AutoAwesomeOutlined from '@mui/icons-material/AutoAwesomeOutlined';
import { sliceRange, toDate, type GarminData, type Range } from '../data';
import { computeRelations, type RelationResult } from '../relations';
import { dateShort, int, monthShort } from '../format';
import { CATEGORY, useResolvedMode, type Category } from '../theme';
import { AiBadge, CARD_SX, IconBubble, InsightList, PageHeader, RangeToggle, SectionTitle, chartSx } from '../ui';

const ICON: Record<Category, ReactElement> = {
  sleep: <Bedtime />, energy: <BatteryChargingFull />, recovery: <MonitorHeart />, heart: <Favorite />,
  stress: <SelfImprovement />, activity: <DirectionsWalk />, training: <DirectionsRun />,
};
const STRENGTH_LABEL = { ninguna: 'Sin relación', débil: 'Relación débil', moderada: 'Relación clara', fuerte: 'Relación fuerte' };

function StrengthDots({ level, color }: { level: number; color: string }) {
  return (
    <Stack direction="row" spacing={0.5} aria-hidden>
      {[1, 2, 3].map((i) => (
        <Box key={i} sx={{ width: 8, height: 8, borderRadius: '50%', bgcolor: i <= level ? color : alpha(color, 0.2) }} />
      ))}
    </Stack>
  );
}

function RelationCard({ r }: { r: RelationResult }) {
  const mode = useResolvedMode();
  const color = CATEGORY[r.cat][mode];
  return (
    <Card sx={{ ...CARD_SX, display: 'flex', flexDirection: 'column', gap: 1.5, height: '100%' }}>
      <Stack direction="row" sx={{ alignItems: 'center', justifyContent: 'space-between' }}>
        <IconBubble color={color} size={36}>{ICON[r.cat]}</IconBubble>
        <Tooltip title={`Basado en ${r.n} días. Correlación de Spearman ${r.rho.toFixed(2).replace('.', ',')}`}>
          <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
            <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 500 }}>{STRENGTH_LABEL[r.strength]}</Typography>
            <StrengthDots level={r.level} color={color} />
          </Stack>
        </Tooltip>
      </Stack>
      <Box>
        <Typography variant="subtitle1" sx={{ fontSize: 19, lineHeight: 1.3 }}>{r.headline}</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mt: 0.25 }}>{r.context}</Typography>
      </Box>
      {r.groups.length >= 2 && (
        <Box sx={{ mx: -1 }}>
          <BarChart height={150} sx={chartSx} hideLegend borderRadius={10}
            margin={{ top: 22, bottom: 4, left: 8, right: 8 }}
            xAxis={[{ data: r.groups.map((g) => g.label), scaleType: 'band', disableLine: true, disableTicks: true, categoryGapRatio: 0.35 }]}
            yAxis={[{ disableLine: true, disableTicks: true, position: 'none', min: 0, max: Math.max(...r.groups.map((g) => g.mean)) * 1.22 }]}
            series={[{ data: r.groups.map((g) => g.mean), color, label: r.yName, barLabel: (item) => (item.value == null ? '' : r.fmtY(item.value)),
              barLabelPlacement: 'outside', valueFormatter: (v) => (v == null ? '–' : r.fmtY(v)) }]}
          />
        </Box>
      )}
      <Typography variant="caption" color="text.secondary">Media de {r.yName} en cada grupo · {r.n} días</Typography>
    </Card>
  );
}

function Coverage({ data }: { data: GarminData }) {
  const mode = useResolvedMode();
  const cov = data.coverage ?? [];
  const worn = cov.reduce((s, m) => s + m.worn, 0);
  const total = cov.reduce((s, m) => s + m.days, 0);
  const color = CATEGORY.energy[mode];
  const start = toDate(data.period.start);
  return (
    <Card sx={{ ...CARD_SX }}>
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={3} sx={{ alignItems: { md: 'center' } }}>
        <Stack direction="row" spacing={2} sx={{ alignItems: 'center', minWidth: 260 }}>
          <IconBubble color={color} size={48}><Watch /></IconBubble>
          <Box>
            <Typography sx={{ fontSize: 30, fontWeight: 500, lineHeight: 1.1 }}>{total ? Math.round((worn / total) * 100) : 0} %</Typography>
            <Typography variant="body2" color="text.secondary">de los días con el reloj · {worn} de {total}</Typography>
          </Box>
        </Stack>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>Desde {dateShort(start)} {start.getFullYear()} · cada cuadro es un mes</Typography>
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
            {cov.map((m) => {
              const pct = m.days ? m.worn / m.days : 0;
              return (
                <Tooltip key={m.month} title={`${monthShort(toDate(`${m.month}-01`))}: ${m.worn} de ${m.days} días`}>
                  <Box sx={{ width: 26, height: 26, borderRadius: '7px', bgcolor: pct === 0 ? alpha(color, 0.08) : alpha(color, 0.25 + 0.75 * pct),
                    display: 'grid', placeItems: 'center', fontSize: 10, fontWeight: 600, color: pct > 0.6 ? '#fff' : 'text.secondary' }}>
                    {monthShort(toDate(`${m.month}-01`)).slice(0, 1).toUpperCase()}
                  </Box>
                </Tooltip>
              );
            })}
          </Box>
        </Box>
      </Stack>
      {data.ai?.data_note && (
        <Stack direction="row" spacing={1.25} sx={{ mt: 2.5, pt: 2, borderTop: 1, borderColor: 'divider', alignItems: 'flex-start' }}>
          <AutoAwesomeOutlined sx={{ fontSize: 18, color: 'primary.main', mt: 0.25 }} />
          <Typography>{data.ai.data_note}</Typography>
        </Stack>
      )}
    </Card>
  );
}

function AiUsageCard({ data }: { data: GarminData }) {
  const mode = useResolvedMode();
  const u = data.aiUsage;
  if (!u) return null;
  const color = CATEGORY.energy[mode];
  const usd = (v?: number | null, d = 3) => (v == null ? '–' : `${v.toFixed(d).replace('.', ',')} $`);
  const KIND: Record<string, string> = { textos: 'Textos diarios', chat: 'Chat', weekly: 'Resumen semanal', 'plan-create': 'Crear el plan', 'plan-adapt': 'Ajustes del plan', 'plan-structure': 'Entrenos para el reloj · carrera', 'plan-structure-gym': 'Entrenos para el reloj · gimnasio', comida: 'Comida (fotos)', compra: 'Menú y compra semanal' };
  const MODEL: Record<string, string> = { 'claude-haiku-5-5': 'Haiku 5.5', 'claude-sonnet-5-5': 'Sonnet 5.5', 'claude-opus-5-5': 'Opus 5.5' };
  const month = u.monthCostUsd ?? 0, budget = u.monthlyBudgetUsd ?? 50;
  const tiles = [
    { label: 'Gasto total', value: usd(u.costUsd, 4), sub: u.first ? `desde el ${dateShort(new Date(u.first))}` : 'sin llamadas aún' },
    { label: 'Llamadas', value: int(u.calls), sub: `máx. ${u.maxCallsPerDay} al día, solo con datos nuevos` },
    { label: 'Tokens', value: `${int((u.inputTokens + u.outputTokens) / 1000)} k`, sub: `${int(u.inputTokens / 1000)} k leídos · ${int(u.outputTokens / 1000)} k escritos` },
    { label: 'Este mes', value: usd(month, 2), sub: `de ${usd(budget, 0)} de presupuesto` },
  ];
  return (
    <Card sx={{ ...CARD_SX }}>
      <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center', mb: 2 }}>
        <IconBubble color={color} size={36}><AutoAwesomeOutlined /></IconBubble>
        <Box>
          <Typography variant="subtitle1">Claude Sonnet 5.5 y Opus 5.5</Typography>
          <Typography variant="body2" color="text.secondary">
            Escribe los textos de la app{u.last ? ` · última vez ${dateShort(new Date(u.last))} a las ${new Date(u.last).toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' })}` : ''}
          </Typography>
        </Box>
      </Stack>
      <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr 1fr', md: 'repeat(4, 1fr)' } }}>
        {tiles.map((t) => (
          <Box key={t.label} sx={{ p: 2, borderRadius: '16px', bgcolor: alpha(color, mode === 'dark' ? 0.1 : 0.06) }}>
            <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 500 }}>{t.label}</Typography>
            <Typography sx={{ fontSize: 24, fontWeight: 500, lineHeight: 1.2 }}>{t.value}</Typography>
            <Typography variant="caption" color="text.secondary">{t.sub}</Typography>
          </Box>
        ))}
      </Box>
      <Box sx={{ mt: 2 }}>
        <Stack direction="row" sx={{ justifyContent: 'space-between', mb: 0.75 }}>
          <Typography variant="body2" sx={{ fontWeight: 500 }}>Presupuesto del mes</Typography>
          <Typography variant="body2" color="text.secondary">{usd(month, 2)} de {usd(budget, 0)} · a partir de {usd(u.safeLimitUsd ?? 40, 0)} todo pasa a Haiku</Typography>
        </Stack>
        <Box sx={{ height: 8, borderRadius: 999, bgcolor: alpha(color, 0.15), overflow: 'hidden' }}>
          <Box sx={{ width: `${Math.min(100, (month / budget) * 100)}%`, minWidth: month > 0 ? 6 : 0, height: '100%', bgcolor: color, borderRadius: 999 }} />
        </Box>
      </Box>
      {u.byKind?.length ? (
        <Box sx={{ mt: 2, display: 'grid', gap: 1 }}>
          {u.byKind.map((k) => (
            <Stack key={`${k.kind}-${k.model}`} direction="row" spacing={2} sx={{ justifyContent: 'space-between', alignItems: 'center', py: 1, borderTop: 1, borderColor: 'divider' }}>
              <Box sx={{ minWidth: 0 }}>
                <Typography variant="body2" sx={{ fontWeight: 500 }}>{KIND[k.kind] ?? k.kind}</Typography>
                <Typography variant="caption" color="text.secondary">{MODEL[k.model] ?? k.model} · {k.calls} {k.calls === 1 ? 'llamada' : 'llamadas'}</Typography>
              </Box>
              <Typography variant="body2" sx={{ fontWeight: 500, whiteSpace: 'nowrap' }}>{usd(k.cost, 3)}</Typography>
            </Stack>
          ))}
        </Box>
      ) : null}
      {u.byDay.length > 1 && (
        <Box sx={{ mt: 2 }}>
          <BarChart height={140} sx={chartSx} hideLegend borderRadius={6} grid={{ horizontal: true }}
            margin={{ top: 8, bottom: 4, left: 4, right: 8 }}
            xAxis={[{ data: u.byDay.map((d) => d.day), scaleType: 'band', disableLine: true, disableTicks: true,
              valueFormatter: (v: string) => dateShort(toDate(v)) }]}
            yAxis={[{ disableLine: true, disableTicks: true, width: 48, valueFormatter: (v: number) => usd(v, 3) }]}
            series={[{ data: u.byDay.map((d) => d.cost), color, label: 'Gasto', valueFormatter: (v) => usd(v, 4) }]} />
        </Box>
      )}
    </Card>
  );
}

export default function Insights({ data }: { data: GarminData }) {
  const mode = useResolvedMode();
  const [range, setRange] = useState<Range>('all');
  const rels = useMemo(() => computeRelations(sliceRange(data.days, range)), [data.days, range]);
  const clear = rels.filter((r) => r.level >= 1);
  const none = rels.filter((r) => r.level === 0);
  const lastDay = [...data.days].reverse().find((d) => d.rhr != null || d.sleepH != null)?.d;

  return (
    <Box>
      <PageHeader title="Análisis"
        subtitle={`Qué influye en qué, según tus propios datos${lastDay ? ` · al día hasta el ${dateShort(toDate(lastDay))}` : ''}`}
        action={<RangeToggle value={range} onChange={setRange} exclude={['7d', '30d']} />} />

      {data.ai?.analysis?.length ? (
        <>
          <Box sx={{ mb: 1.5 }}><AiBadge at={data.ai.generatedAt} /></Box>
          <InsightList items={data.ai.analysis} color={CATEGORY.recovery[mode]} icon={<AutoAwesomeOutlined />} />
        </>
      ) : null}

      <SectionTitle help="relation">Lo que más te influye</SectionTitle>
      {clear.length ? (
        <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' } }}>
          {clear.map((r) => <RelationCard key={r.id} r={r} />)}
        </Box>
      ) : (
        <Typography color="text.secondary">Con este periodo aún no hay suficientes días para ver relaciones claras.</Typography>
      )}

      {none.length > 0 && (
        <>
          <SectionTitle>Sin relación clara</SectionTitle>
          <Card sx={{ ...CARD_SX, py: 1 }}>
            {none.map((r, i) => (
              <Box key={r.id} sx={{ py: 1.5, borderTop: i ? 1 : 0, borderColor: 'divider' }}>
                <Typography>{r.headline}</Typography>
                <Typography variant="caption" color="text.secondary">{r.context} · {r.n} días</Typography>
              </Box>
            ))}
          </Card>
        </>
      )}
      <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
        Se comparan tus propios días entre sí, en tres grupos de tamaño parecido. Que dos cosas vayan juntas no demuestra que una cause la otra.
      </Typography>

      <SectionTitle help="coverage">Sobre tus datos</SectionTitle>
      <Coverage data={data} />

      <SectionTitle help="aiUsage">Uso de la IA</SectionTitle>
      <AiUsageCard data={data} />
    </Box>
  );
}
