// "Tus opciones": probabilidad real de llegar al tiempo objetivo, con un medidor y su evolución día a día.
// El cálculo está en src/garmin_stats/odds.py (VDOT actual + mejora esperada según cumples el plan ± incertidumbre).
import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import Typography from '@mui/material/Typography';
import { toDate, type GarminData } from './data';
import { dec1, duration } from './format';
import { useResolvedMode } from './theme';
import { CARD_SX } from './ui';

const COLORS = {
  low: { light: '#D4542F', dark: '#F08A66' }, mid: { light: '#E8710A', dark: '#FCAD70' }, high: { light: '#146C2E', dark: '#6DD58C' },
};

function Gauge({ pct, color }: { pct: number; color: string }) {
  // Semicírculo: el arco de fondo y el de valor comparten radio; la aguja es el final del arco.
  const r = 52, cx = 64, cy = 62, len = Math.PI * r;
  const p = Math.max(0, Math.min(100, pct)) / 100;
  const arc = `M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`;
  return (
    <Box sx={{ position: 'relative', width: 128, height: 76, flexShrink: 0 }}>
      <svg width="128" height="76" viewBox="0 0 128 76" aria-hidden>
        <path d={arc} fill="none" stroke="currentColor" strokeOpacity={0.12} strokeWidth={12} strokeLinecap="round" />
        <path d={arc} fill="none" stroke={color} strokeWidth={12} strokeLinecap="round" strokeDasharray={`${len * p} ${len}`} />
      </svg>
      <Box sx={{ position: 'absolute', left: 0, right: 0, bottom: 0, textAlign: 'center' }}>
        <Typography component="span" sx={{ fontSize: 30, fontWeight: 700, lineHeight: 1, color, fontVariantNumeric: 'tabular-nums' }}>{pct}</Typography>
        <Typography component="span" sx={{ fontSize: 15, fontWeight: 600, color }}>%</Typography>
      </Box>
    </Box>
  );
}

function Spark({ hist, color }: { hist: { d: string; pct: number }[]; color: string }) {
  if (hist.length < 2) return null;
  const w = 100, h = 22;
  const pts = hist.map((x, i) => `${(i / (hist.length - 1)) * w},${h - (x.pct / 100) * h}`).join(' ');
  return (
    <svg width="100%" height={h} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" aria-hidden style={{ display: 'block', marginTop: 6 }}>
      <polyline points={pts} fill="none" stroke={color} strokeWidth={2} vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
    </svg>
  );
}

export function GoalOddsCard({ data, go }: { data: GarminData; go: (k: string) => void }) {
  const mode = useResolvedMode();
  const o = data.goalOdds;
  if (!o) return null;
  const tone = o.pct >= 65 ? 'high' : o.pct >= 35 ? 'mid' : 'low';
  const color = COLORS[tone][mode];
  const hist = o.history ?? [];
  const weekAgo = hist.length > 1 ? hist[Math.max(0, hist.length - 8)] : null;
  const delta = weekAgo ? o.pct - weekAgo.pct : null;
  const verdict = o.pct >= 65 ? 'Vas bien encaminado' : o.pct >= 35 ? 'Posible, pero hay que cumplir' : 'Ahora mismo, difícil';
  const raceDay = toDate(o.raceDate).toLocaleDateString('es-ES', { day: 'numeric', month: 'short' }).replace('.', '');
  return (
    <Card onClick={() => go('plan')} sx={{ ...CARD_SX, mb: 2, cursor: 'pointer' }}>
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', fontWeight: 600 }}>
        TUS OPCIONES · {o.goal.toUpperCase()} EN {o.goalTime}
      </Typography>
      <Box sx={{ display: 'flex', gap: 2, alignItems: 'center', mt: 1 }}>
        <Gauge pct={o.pct} color={color} />
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography sx={{ fontWeight: 600, color, lineHeight: 1.25 }}>{verdict}</Typography>
          <Typography variant="body2" sx={{ mt: 0.5, fontVariantNumeric: 'tabular-nums' }}>
            Previsión el {raceDay}: <b>{duration(o.predictedS)}</b>
          </Typography>
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', fontVariantNumeric: 'tabular-nums' }}>
            Hoy: {duration(o.nowS)} · faltan {o.daysLeft} días
            {delta != null && delta !== 0 ? <Box component="span" sx={{ ml: 0.75, fontWeight: 600, color: delta > 0 ? COLORS.high[mode] : COLORS.low[mode] }}>
              {delta > 0 ? '▲' : '▼'} {Math.abs(delta)} en 7 días</Box> : null}
          </Typography>
        </Box>
      </Box>
      <Spark hist={hist} color={color} />
      <Typography variant="body2" color="text.secondary" sx={{ mt: 1.25, lineHeight: 1.45, '& b': { color: 'text.primary' } }}>
        Necesitas un nivel (VDOT) de <b>{dec1(o.needVdot)}</b> y tienes <b>{dec1(o.vdot)}</b>.
        {o.gain > 0 ? <> Si sigues {o.adherence != null ? `cumpliendo el ${o.adherence} % del plan` : 'el plan'}, ganarías unos <b>{dec1(o.gain)}</b>.</>
          : <> Cumpliendo el plan subiría: ahora mismo no da para mejorar.</>}
      </Typography>
    </Card>
  );
}
