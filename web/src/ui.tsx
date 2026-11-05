import { useState, type ReactNode } from 'react';
import Tooltip from '@mui/material/Tooltip';
import { GLOSSARY, type HelpEntry, type HelpKey } from './glossary';
import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import ToggleButton from '@mui/material/ToggleButton';
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup';
import { alpha } from '@mui/material/styles';
import { Gauge, gaugeClasses } from '@mui/x-charts/Gauge';
import { SparkLineChart } from '@mui/x-charts/SparkLineChart';
import LightbulbOutlined from '@mui/icons-material/LightbulbOutlined';
import AutoAwesomeOutlined from '@mui/icons-material/AutoAwesomeOutlined';
import DirectionsWalk from '@mui/icons-material/DirectionsWalk';
import Favorite from '@mui/icons-material/Favorite';
import Bedtime from '@mui/icons-material/Bedtime';
import SelfImprovement from '@mui/icons-material/SelfImprovement';
import MonitorHeart from '@mui/icons-material/MonitorHeart';
import BatteryChargingFull from '@mui/icons-material/BatteryChargingFull';
import DirectionsRun from '@mui/icons-material/DirectionsRun';
import type { AiCard } from './data';
import { Rich } from './rich';
import { RANGES, type Range } from './data';
import { signed } from './format';
import { CATEGORY, useResolvedMode } from './theme';
import useMediaQuery from '@mui/material/useMediaQuery';

export const CARD_SX = { p: { xs: 2.25, sm: 2.75 }, bgcolor: 'background.paper' } as const;

/** Círculo tonal con icono, en el color de la categoría. */
export function IconBubble({ color, children, size = 40 }: { color: string; children: ReactNode; size?: number }) {
  return (
    <Box sx={{
      width: size, height: size, borderRadius: '50%', display: 'grid', placeItems: 'center', flexShrink: 0,
      color, bgcolor: alpha(color, 0.14), '& svg': { fontSize: size * 0.55 },
    }}>
      {children}
    </Box>
  );
}

export function PageHeader({ title, subtitle, action }: { title: string; subtitle?: string; action?: ReactNode }) {
  return (
    <Stack direction={{ xs: 'column', sm: 'row' }} spacing={{ xs: 1.5, sm: 2 }} sx={{ mb: { xs: 2, sm: 3 }, alignItems: { sm: 'flex-end' }, justifyContent: 'space-between' }}>
      <Box>
        <Typography variant="h4" component="h1" sx={{ fontSize: { xs: 26, sm: 34 } }}>{title}</Typography>
        {subtitle && <Typography color="text.secondary" sx={{ mt: 0.5 }}>{subtitle}</Typography>}
      </Box>
      {action}
    </Stack>
  );
}

export function SectionTitle({ children, help }: { children: ReactNode; help?: HelpKey }) {
  return (
    <Stack direction="row" spacing={1} sx={{ alignItems: 'center', mt: { xs: 4, sm: 5 }, mb: 2 }}>
      <Typography variant="h6">{children}</Typography>
      {help && <InfoTip k={help} />}
    </Stack>
  );
}

export function RangeToggle({ value, onChange, exclude = [] }: {
  value: Range; onChange: (r: Range) => void; exclude?: Range[];
}) {
  return (
    <ToggleButtonGroup
      exclusive size="small" value={value}
      onChange={(_, v) => v && onChange(v)}
      sx={{ bgcolor: 'background.paper', alignSelf: { xs: 'flex-start', sm: 'auto' }, flexWrap: 'wrap',
        '& .MuiToggleButton-root': { borderRadius: '999px !important', color: 'text.secondary' },
        '& .Mui-selected': { bgcolor: 'color-mix(in srgb, var(--mui-palette-primary-main) 16%, transparent) !important', color: 'primary.main' } }}
    >
      {RANGES.filter((r) => !exclude.includes(r.value)).map((r) => (
        <ToggleButton key={r.value} value={r.value}>{r.label}</ToggleButton>
      ))}
    </ToggleButtonGroup>
  );
}

export interface Delta { value: number; digits?: number; unit?: string; goodWhen: 'up' | 'down' | 'none'; label?: string }

function DeltaText({ delta }: { delta: Delta }) {
  const good = delta.goodWhen === 'none' ? null : (delta.goodWhen === 'up' ? delta.value > 0 : delta.value < 0);
  const neutral = Math.abs(delta.value) < Math.pow(10, -(delta.digits ?? 0)) / 2;
  return (
    <Typography variant="body2" sx={{
      color: neutral || good === null ? 'text.secondary' : good ? 'success.main' : 'error.main', fontWeight: 500,
    }}>
      {signed(delta.value, delta.digits ?? 0)}{delta.unit ? ` ${delta.unit}` : ''}
      <Box component="span" sx={{ color: 'text.secondary', fontWeight: 400 }}> {delta.label ?? 'vs tu media'}</Box>
    </Typography>
  );
}

/** Tarjeta de métrica: icono, valor grande, variación y mini-gráfico. */
export function MetricCard({ icon, color, label, value, unit, caption, delta, spark, onClick, help }: {
  icon: ReactNode; color: string; label: string; value: string; unit?: string; caption?: ReactNode;
  delta?: Delta; spark?: number[]; onClick?: () => void; help?: HelpKey;
}) {
  return (
    <Card onClick={onClick} sx={{
      ...CARD_SX, p: { xs: 1.75, sm: 2.75 }, height: '100%', display: 'flex', flexDirection: 'column', gap: { xs: 1, sm: 1.5 },
      cursor: onClick ? 'pointer' : 'default', transition: 'box-shadow .2s, transform .2s',
      '&:hover': onClick ? { boxShadow: (t) => `0 1px 3px ${alpha(t.palette.text.primary, 0.12)}, 0 4px 12px ${alpha(t.palette.text.primary, 0.06)}` } : undefined,
    }}>
      <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center' }}>
        <IconBubble color={color} size={32}>{icon}</IconBubble>
        <Typography variant="subtitle2" color="text.secondary" sx={{ fontSize: { xs: 13, sm: 14 }, lineHeight: 1.25, flex: 1, minWidth: 0 }}>{label}</Typography>
        {help && <Box sx={{ display: { xs: 'none', sm: 'block' } }}><InfoTip k={help} /></Box>}
      </Stack>
      <Box>
        <Typography component="div" sx={{ fontSize: { xs: 26, sm: 34 }, fontWeight: 500, lineHeight: 1.1, letterSpacing: '-0.02em' }}>
          {value}
          {unit && <Box component="span" sx={{ fontSize: { xs: 13, sm: 16 }, fontWeight: 400, color: 'text.secondary', ml: 0.5 }}>{unit}</Box>}
        </Typography>
        {delta && <DeltaText delta={delta} />}
        {caption && <Typography variant="body2" color="text.secondary" sx={{ mt: 0.25 }}>{caption}</Typography>}
      </Box>
      {spark && spark.length > 2 && (
        <Box sx={{ mt: 'auto', mx: -0.5 }}>
          <SparkLineChart data={spark} height={40} color={color} curve="monotoneX"
            margin={{ top: 6, bottom: 6, left: 4, right: 4 }}
            sx={{ '& .MuiLineElement-root': { strokeWidth: 2 } }} />
        </Box>
      )}
    </Card>
  );
}

/** Anillo de progreso grande (pasos, sueño, energía). */
export function RingCard({ icon, color, label, value, max, center, sub, caption, help }: {
  icon: ReactNode; color: string; label: string; value: number; max: number; center: string; sub?: string; caption?: string; help?: HelpKey;
}) {
  const mode = useResolvedMode();
  const small = useMediaQuery('(max-width:599px)');
  const size = small ? 92 : 168;
  return (
    <Card sx={{ ...CARD_SX, p: { xs: 1.5, sm: 2.75 }, height: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center' }}>
      <Stack direction="row" spacing={1.25} sx={{ alignItems: 'center', alignSelf: { xs: 'center', sm: 'flex-start' } }}>
        {!small && <IconBubble color={color} size={32}>{icon}</IconBubble>}
        <Typography variant="subtitle2" color="text.secondary" sx={{ fontSize: { xs: 12, sm: 14 } }}>{label}</Typography>
        {help && !small && <InfoTip k={help} />}
      </Stack>
      <Box sx={{ position: 'relative', width: size, height: size, my: 1 }}>
        <Gauge
          width={size} height={size} value={Math.min(value, max)} valueMax={max}
          innerRadius="80%" outerRadius="100%" cornerRadius="50%" text=""
          sx={{
            [`& .${gaugeClasses.valueArc}`]: { fill: color },
            [`& .${gaugeClasses.referenceArc}`]: { fill: alpha(color, mode === 'dark' ? 0.2 : 0.14) },
          }}
        />
        <Box sx={{ position: 'absolute', inset: 0, display: 'grid', placeContent: 'center' }}>
          <Typography sx={{ fontSize: small ? 17 : 32, fontWeight: 500, lineHeight: 1.05, letterSpacing: '-0.02em' }}>{center}</Typography>
          {sub && !small && <Typography variant="body2" color="text.secondary">{sub}</Typography>}
        </Box>
      </Box>
      {caption && !small && <Typography variant="body2" color="text.secondary">{caption}</Typography>}
      {small && sub && <Typography variant="caption" color="text.secondary" sx={{ lineHeight: 1.2 }}>{sub}</Typography>}
    </Card>
  );
}

export function ChartCard({ title, subtitle, children, action, help }: {
  title: string; subtitle?: string; children: ReactNode; action?: ReactNode; help?: HelpKey;
}) {
  return (
    <Card sx={{ ...CARD_SX, height: '100%' }}>
      <Stack direction="row" sx={{ justifyContent: 'space-between', alignItems: 'flex-start', mb: 1 }} spacing={2}>
        <Box>
          <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
            <Typography variant="subtitle1">{title}</Typography>
            {help && <InfoTip k={help} />}
          </Stack>
          {subtitle && <Typography variant="body2" color="text.secondary">{subtitle}</Typography>}
        </Box>
        {action}
      </Stack>
      {children}
    </Card>
  );
}

export function InsightList({ items, color, icon }: { items?: string[]; color: string; icon?: ReactNode }) {
  if (!items?.length) return null;
  return (
    <Stack spacing={1.5}>
      {items.map((t, i) => (
        <Card key={i} sx={{ ...CARD_SX, py: 2, display: 'flex', gap: 2, alignItems: 'flex-start', bgcolor: alpha(color, 0.07) }}>
          <IconBubble color={color} size={32}>{icon ?? <LightbulbOutlined />}</IconBubble>
          <Typography sx={{ pt: 0.5, color: 'text.secondary', '& b': { color: 'text.primary' } }}><Rich>{t}</Rich></Typography>
        </Card>
      ))}
    </Stack>
  );
}

/** Estilo común de los gráficos: sin líneas de eje, cuadrícula suave. */
export const chartSx = {
  '& .MuiChartsGrid-line': { stroke: 'var(--mui-palette-divider)', strokeDasharray: '3 4' },
  '& .MuiChartsAxis-tickLabel': { fill: 'var(--mui-palette-text-secondary) !important', fontSize: '12px !important' },
  '& .MuiChartsReferenceLine-label': { fill: 'var(--mui-palette-text-secondary) !important', fontSize: '12px !important' },
  '& .MuiChartsLegend-label': { fontSize: 13 },
  '& .MuiLineChart-area': { fillOpacity: 0.16 },
} as const;

export const axisClean = { disableLine: true, disableTicks: true } as const;

const CAT_ICON = {
  activity: <DirectionsWalk />, heart: <Favorite />, sleep: <Bedtime />, stress: <SelfImprovement />,
  recovery: <MonitorHeart />, energy: <BatteryChargingFull />, training: <DirectionsRun />,
} as const;

/** Etiqueta discreta que indica que el texto lo ha escrito la IA. */
export function AiBadge({ at }: { at?: string }) {
  return (
    <Stack direction="row" spacing={0.75} sx={{ alignItems: 'center', color: 'text.secondary' }}>
      <AutoAwesomeOutlined sx={{ fontSize: 16, color: 'primary.main' }} />
      <Typography variant="caption">Escrito con IA{at ? ` · ${new Date(at).toLocaleDateString('es-ES', { day: 'numeric', month: 'short' }).replace('.', '')}` : ''}</Typography>
    </Stack>
  );
}

/** Tarjetas de la IA para la portada: icono y color de su categoría. */
export function AiCards({ cards }: { cards: AiCard[] }) {
  const mode = useResolvedMode();
  return (
    <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', md: `repeat(${Math.min(cards.length, 3)}, 1fr)` } }}>
      {cards.map((c, i) => {
        const color = CATEGORY[c.category]?.[mode] ?? CATEGORY.energy[mode];
        return (
          <Card key={i} sx={{ ...CARD_SX, display: 'flex', flexDirection: 'column', gap: 1.5, bgcolor: alpha(color, mode === 'dark' ? 0.12 : 0.08) }}>
            <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center' }}>
              <IconBubble color={color} size={36}>{CAT_ICON[c.category] ?? <LightbulbOutlined />}</IconBubble>
              <Typography variant="caption" sx={{ color, fontWeight: 600, letterSpacing: '0.02em' }}>
                {CATEGORY[c.category]?.label ?? ''}
              </Typography>
            </Stack>
            <Typography variant="subtitle1" sx={{ fontSize: 18, lineHeight: 1.3 }}>{c.title}</Typography>
            <Typography color="text.secondary"><Rich>{c.body}</Rich></Typography>
          </Card>
        );
      })}
    </Box>
  );
}

/** Botón redondo "?" con una explicación sencilla. Hover en ordenador, toque en móvil. */
export function InfoTip({ k }: { k: HelpKey }) {
  const e: HelpEntry = GLOSSARY[k];
  const [open, setOpen] = useState(false);
  return (
    <Tooltip
      open={open} onOpen={() => setOpen(true)} onClose={() => setOpen(false)}
      enterDelay={120} leaveDelay={80} enterTouchDelay={0} leaveTouchDelay={6000} placement="bottom-start"
      slotProps={{
        tooltip: {
          sx: (t) => ({
            bgcolor: 'background.paper', color: 'text.primary', p: 2, maxWidth: 320, borderRadius: '16px',
            boxShadow: '0 1px 2px rgba(60,64,67,.25), 0 4px 12px 3px rgba(60,64,67,.15)',
            border: '1px solid', borderColor: 'divider', fontSize: 14, lineHeight: 1.5,
            ...t.applyStyles('dark', { bgcolor: '#2B2C2E', color: '#E3E3E3', boxShadow: '0 4px 16px rgba(0,0,0,.5)' }),
          }),
        },
      }}
      title={
        <Box>
          <Typography sx={{ fontWeight: 600, fontSize: 15, mb: 0.75 }}>{e.title}</Typography>
          <Typography sx={{ fontSize: 14, color: 'text.secondary' }}>{e.body}</Typography>
          {e.good && (
            <Typography sx={{ fontSize: 13, mt: 1.25, pt: 1.25, borderTop: 1, borderColor: 'divider' }}>
              <Box component="span" sx={{ fontWeight: 600, color: 'primary.main' }}>Referencia · </Box>{e.good}
            </Typography>
          )}
        </Box>
      }
    >
      <Box component="button" type="button" aria-label={`Qué es: ${e.title}`}
        onClick={(ev: React.MouseEvent) => { ev.stopPropagation(); setOpen((o) => !o); }}
        sx={{
          width: 18, height: 18, p: 0, borderRadius: '50%', border: '1.5px solid', borderColor: 'text.disabled',
          bgcolor: 'transparent', color: 'text.secondary', fontSize: 11, fontWeight: 700, lineHeight: 1, cursor: 'pointer',
          display: 'inline-grid', placeItems: 'center', flexShrink: 0, fontFamily: 'inherit', verticalAlign: 'middle',
          transition: 'all .15s', '&:hover, &:focus-visible': { borderColor: 'primary.main', color: 'primary.main', outline: 'none' },
        }}>?</Box>
    </Tooltip>
  );
}
