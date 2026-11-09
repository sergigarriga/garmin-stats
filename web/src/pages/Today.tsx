import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import List from '@mui/material/List';
import ListItemButton from '@mui/material/ListItemButton';
import ListItemText from '@mui/material/ListItemText';
import ListItemAvatar from '@mui/material/ListItemAvatar';
import Typography from '@mui/material/Typography';
import DirectionsWalk from '@mui/icons-material/DirectionsWalk';
import Bedtime from '@mui/icons-material/Bedtime';
import BatteryChargingFull from '@mui/icons-material/BatteryChargingFull';
import Favorite from '@mui/icons-material/Favorite';
import MonitorHeart from '@mui/icons-material/MonitorHeart';
import SelfImprovement from '@mui/icons-material/SelfImprovement';
import Bolt from '@mui/icons-material/Bolt';
import Speed from '@mui/icons-material/Speed';
import FitnessCenter from '@mui/icons-material/FitnessCenter';
import TipsAndUpdates from '@mui/icons-material/TipsAndUpdates';
import { isoLocal, lastWith, mean, toDate, useNow, type Activity, type GarminData, type Day } from '../data';
import AutoAwesomeRounded from '@mui/icons-material/AutoAwesomeRounded';
import { dateLong, dateShort, hm, hmShort, int, dec1, pace } from '../format';
import { useCat } from '../theme';
import { AiBadge, AiCards, CARD_SX, IconBubble, InsightList, MetricCard, PageHeader, RingCard, SectionTitle, chartSx } from '../ui';
import Stack from '@mui/material/Stack';
import { SportIcon } from './sport';
import { Rich } from '../rich';
import DirectionsRunRounded from '@mui/icons-material/DirectionsRunRounded';
import { Alerts, Goals, ReadinessCard, WeekCard } from './TodayExtras';
import { CheckIn } from './Wellness';
import { LineChart } from '@mui/x-charts/LineChart';
import { WeatherIcon } from './PlanTime';
import { FoodTodayCard } from './Food';
import { KeyFacts, activityFacts, heartFacts, sleepFacts, trainingFacts } from '../highlights';

const minutes = (hm: string) => { const [h, m] = hm.split(':').map(Number); return h * 60 + m; };
const hhmm = (min: number) => `${String(Math.floor(min / 60)).padStart(2, '0')}:${String(Math.round(min % 60)).padStart(2, '0')}`;

/** Tu energía y tu pulso de hoy, hora a hora (lo que el reloj ha mandado hasta ahora). */
function TodayCurve({ bb, hr, asOf }: { bb?: [string, number][]; hr?: [string, number][]; asOf?: string }) {
  const cat = useCat();
  if (!bb?.length && !hr?.length) return null;
  const xs = [...new Set([...(bb ?? []), ...(hr ?? [])].map((p) => minutes(p[0])))].sort((a, b) => a - b);
  const pick = (s?: [string, number][]) => { const m = new Map((s ?? []).map((p) => [minutes(p[0]), p[1]])); return xs.map((x) => m.get(x) ?? null); };
  return (
    <Card sx={{ ...CARD_SX, mt: 2 }}>
      <Stack direction="row" sx={{ justifyContent: 'space-between', alignItems: 'baseline', gap: 1, flexWrap: 'wrap' }}>
        <Typography variant="subtitle1">Tu día, hora a hora</Typography>
        {asOf && <Typography variant="caption" color="text.secondary">hasta las {asOf}</Typography>}
      </Stack>
      <LineChart height={190} sx={chartSx} grid={{ horizontal: true }} margin={{ left: 0, right: 0, top: 16, bottom: 0 }}
        xAxis={[{ data: xs, scaleType: 'linear', min: 0, max: Math.max(24 * 60, xs[xs.length - 1] ?? 0), disableLine: true, disableTicks: true,
          tickInterval: [0, 360, 720, 1080, 1440], valueFormatter: (v: number) => hhmm(v) }]}
        yAxis={[{ id: 'bb', min: 0, max: 100, disableLine: true, disableTicks: true, width: 32 },
          { id: 'hr', position: 'right', disableLine: true, disableTicks: true, width: 36 }]}
        series={[
          ...(bb?.length ? [{ data: pick(bb), yAxisId: 'bb', label: 'Body Battery', color: cat('energy'), connectNulls: true, showMark: true, curve: 'linear' as const, valueFormatter: (v: number | null) => (v == null ? '–' : `${v}`) }] : []),
          ...(hr?.length ? [{ data: pick(hr), yAxisId: 'hr', label: 'Pulso', color: cat('heart'), connectNulls: true, showMark: false, curve: 'monotoneX' as const, valueFormatter: (v: number | null) => (v == null ? '–' : `${v} lpm`) }] : []),
        ]} />
    </Card>
  );
}

function series(days: Day[], pick: (d: Day) => number | undefined, n = 30) {
  return days.slice(-n).map(pick).filter((v): v is number => v != null);
}

/** Valor del día frente a la media de los 30 días anteriores. */
function vs30(days: Day[], ref: Day | undefined, pick: (d: Day) => number | undefined) {
  if (!ref) return undefined;
  const i = days.indexOf(ref);
  const v = pick(ref);
  const m = mean(days.slice(Math.max(0, i - 30), i).map(pick));
  return v != null && m != null ? v - m : undefined;
}

const dayLabel = (iso: string) => {
  const d = new Date(iso); const t = new Date();
  const diff = Math.round((new Date(t.toDateString()).getTime() - new Date(d.toDateString()).getTime()) / 864e5);
  return diff === 0 ? 'Hoy' : diff === 1 ? 'Ayer' : diff < 7 ? `Hace ${diff} días` : dateShort(d);
};

/** Frase de respaldo (sin IA): el último entreno frente a la media de los parecidos de los 90 días anteriores. */
function ruleInsight(acts: Activity[]): string | null {
  const a = acts[acts.length - 1];
  const since = new Date(a.start).getTime() - 90 * 864e5;
  const same = acts.slice(0, -1).filter((x) => x.group === a.group && new Date(x.start).getTime() >= since);
  if (same.length < 2) return null;
  const avg = (k: 'pace' | 'km' | 'min' | 'hr') => mean(same.map((x) => x[k]));
  const p = avg('pace');
  if (a.pace && p && a.km && a.km > 0.5) {
    const s = Math.round((p - a.pace) * 60);
    if (Math.abs(s) >= 5) return `Ritmo ${pace(a.pace)}: ${Math.abs(s)} s/km ${s > 0 ? 'más rápido' : 'más lento'} que tu media de ${a.group.toLowerCase()} de los últimos 3 meses.`;
    return `Ritmo ${pace(a.pace)}, en tu línea de los últimos 3 meses.`;
  }
  const m = avg('min');
  if (a.min && m) {
    const d = Math.round(a.min - m);
    return Math.abs(d) >= 5 ? `${int(a.min)} min: ${Math.abs(d)} min ${d > 0 ? 'más' : 'menos'} que tu sesión media de los últimos 3 meses.` : `${int(a.min)} min, como tu sesión habitual.`;
  }
  return null;
}

/** Tu último entreno con los datos clave y un comentario de la IA (o una frase por reglas si no hay IA). */
function LastWorkoutCard({ data, go }: { data: GarminData; go: (tab: string) => void }) {
  const cat = useCat();
  const a = data.activities[data.activities.length - 1];
  if (!a) return null;
  const ai = data.ai?.last_workout && data.ai.last_workout_id === a.id ? data.ai.last_workout : null;
  const text = ai ?? ruleInsight(data.activities);
  const color = cat(a.group === 'Correr' || a.group === 'Cinta' ? 'training' : a.group === 'Natación' ? 'recovery' : 'activity');
  const stats = [
    a.km ? { v: dec1(a.km), u: 'km' } : null,
    a.min ? (a.min >= 60 ? { v: hmShort(a.min / 60), u: '' } : { v: int(a.min), u: 'min' }) : null,
    a.pace && a.km && a.km > 0.5 ? { v: pace(a.pace).replace(' /km', ''), u: '/km' } : null,
    a.hr ? { v: String(a.hr), u: 'lpm' } : null,
    !a.km && a.sets?.length ? { v: String(a.sets.length), u: 'series' } : null,
  ].filter((x): x is { v: string; u: string } => !!x).slice(0, 3);
  return (
    <Card onClick={() => go(`act-${a.id}`)} sx={{ ...CARD_SX, mt: 2, cursor: 'pointer' }}>
      <Stack direction="row" spacing={2} sx={{ alignItems: 'center' }}>
        <IconBubble color={color}><SportIcon group={a.group} /></IconBubble>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>TU ÚLTIMO ENTRENO · {dayLabel(a.start).toUpperCase()}</Typography>
          <Typography variant="subtitle1" noWrap>{a.name ?? a.group}</Typography>
        </Box>
      </Stack>
      {stats.length > 0 && (
        <Box sx={{ display: 'grid', gridTemplateColumns: `repeat(${stats.length}, 1fr)`, gap: 1, mt: 2 }}>
          {stats.map((x, i) => (
            <Box key={i}>
              <Typography component="span" sx={{ fontSize: 22, fontWeight: 600 }}>{x.v}</Typography>
              {x.u && <Typography component="span" variant="body2" color="text.secondary"> {x.u}</Typography>}
            </Box>
          ))}
        </Box>
      )}
      {text && (
        <Box sx={{ mt: 2, p: 1.5, borderRadius: '16px', display: 'flex', gap: 1, alignItems: 'flex-start',
          bgcolor: 'color-mix(in srgb, #D4542F 8%, transparent)' }}>
          {ai && <AutoAwesomeRounded sx={{ fontSize: 18, color: '#D4542F', mt: '2px', flexShrink: 0 }} />}
          <Typography variant="body2"><Rich>{text}</Rich></Typography>
        </Box>
      )}
    </Card>
  );
}

/** Lo que todas las vistas de "Hoy" necesitan: la fila de hoy y los datos en vivo del reloj. */
function useTodayRows(data: GarminData) {
  const todayIso = isoLocal(new Date());
  const row = data.days.find((d) => d.d === todayIso);
  const latest = row?.rhr != null || row?.steps != null ? row : undefined;
  const night = row?.sleepH != null ? row : undefined;  // la noche lleva la fecha del día en que te despiertas
  const hrvDay = row?.hrv != null ? row : undefined;
  const live = data.live?.date === todayIso ? data.live : undefined;
  return { latest, night, hrvDay, live };
}

/** Hoy (resumen): solo lo importante. Lo demás vive en "Tu día" y "Semana". */
export default function Today({ data, go }: { data: GarminData; go: (tab: string) => void }) {
  const cat = useCat();
  const days = data.days;
  const { latest, night, live } = useTodayRows(data);
  const lastSync = lastWith(days, (d) => d.rhr ?? d.steps);
  const today = new Date();
  const now = useNow(60_000);
  const bbNow = live?.bbNow ?? latest?.bbNow;
  // El reloj solo manda datos cuando se sincroniza con el móvil: si hace rato, se avisa.
  const staleMin = live?.asOf ? now.getHours() * 60 + now.getMinutes() - minutes(live.asOf) : null;

  return (
    <Box>
      <PageHeader
        title="Hoy"
        subtitle={`${dateLong(today).replace(/^\w/, (c) => c.toUpperCase())}${!latest && lastSync ? ` · aún no hay datos de hoy (últimos del ${dateShort(toDate(lastSync.d))})` : ''}${live?.asOf ? ` · datos del reloj hasta las ${live.asOf}` : ''}`}
      />

      <Alerts alerts={data.alerts} />
      {data.ai?.headline && (
        <Typography sx={{ fontSize: { xs: 18, sm: 20 }, mt: -1.5, mb: 3, maxWidth: 820 }}><Rich>{data.ai.headline}</Rich></Typography>
      )}
      <ReadinessCard data={data} />
      {data.coach?.today && (
        <Card onClick={() => go('plan')} sx={{ ...CARD_SX, mb: 2, py: 2, cursor: 'pointer', display: 'flex', gap: 2, alignItems: 'center' }}>
          <IconBubble color={cat('training')}><DirectionsRunRounded /></IconBubble>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>HOY EN TU PLAN</Typography>
            <Typography variant="subtitle1">{data.coach.today.session.title}{data.coach.today.session.distance_km ? ` · ${dec1(data.coach.today.session.distance_km)} km` : ''}</Typography>
            {data.coach.today.tip && <Typography variant="body2" color="text.secondary"><Rich>{data.coach.today.tip}</Rich></Typography>}
            {(() => {
              const t = data.coach!.today!;
              const w = t.bestWindow;
              if (!t.weatherTip && !w) return null;
              return (
                <Typography data-new="today-weather" variant="body2" color="text.secondary" component="div"
                  sx={{ display: 'flex', gap: 0.75, alignItems: 'flex-start', mt: 0.5, '& b': { color: 'text.primary' } }}>
                  <Box sx={{ mt: '1px', flexShrink: 0, display: 'flex' }}><WeatherIcon code={t.weather?.code} size={17} /></Box>
                  <span>{t.weatherTip ? <Rich>{t.weatherTip}</Rich>
                    : <>Mejor franja para correr: <b>{w!.from}-{w!.to}</b>{w!.temp != null ? ` (${w!.temp} °C)` : ''}{t.weather?.text ? ` · ${t.weather.text.toLowerCase()}` : ''}.</>}</span>
                </Typography>
              );
            })()}
          </Box>
        </Card>
      )}
      <Box sx={{ display: 'grid', gap: { xs: 1, sm: 2 }, gridTemplateColumns: 'repeat(3, 1fr)' }}>
        <RingCard icon={<DirectionsWalk />} color={cat('activity')} label="Pasos" help="steps"
          value={latest?.steps ?? 0} max={latest?.stepGoal ?? 10000}
          center={latest?.steps != null ? int(latest.steps) : '—'} sub={latest ? `de ${int(latest.stepGoal ?? 10000)}` : 'sin datos de hoy'}
          caption={latest ? 'Hoy' : 'Sincroniza el reloj'} />
        <RingCard icon={<Bedtime />} color={cat('sleep')} label="Sueño" help="sleepScore"
          value={night?.sleepScore ?? 0} max={100}
          center={night?.sleepH != null ? hm(night.sleepH).replace(' min', '') : '—'}
          sub={night ? (night.sleepScore != null ? `Puntuación ${night.sleepScore}` : undefined) : 'sin datos de anoche'}
          caption={night ? 'Anoche' : 'Sin datos de anoche'} />
        <Box data-new="energy" sx={{ height: '100%', minWidth: 0 }}><RingCard icon={<BatteryChargingFull />} color={cat('energy')} label="Body Battery" help="bodyBattery"
          value={bbNow ?? 0} max={100}
          center={bbNow != null ? int(bbNow) : '—'} sub={bbNow != null ? (live?.asOf ? `ahora · ${live.asOf}` : 'ahora') : 'sin datos de hoy'}
          caption={latest?.bbMax != null ? `Máximo ${latest.bbMax} · mínimo ${latest.bbMin ?? '–'}` : 'Sin datos de hoy'} /></Box>
      </Box>
      {staleMin != null && staleMin > 90 && (
        <Typography variant="body2" color="text.secondary" sx={{ mt: 1.5 }}>
          El último dato del reloj es de las {live!.asOf}. Garmin solo recibe datos nuevos cuando el reloj se sincroniza con
          el móvil: abre Garmin Connect y después pulsa actualizar.
        </Typography>
      )}

      <LastWorkoutCard data={data} go={go} />

      <SectionTitle>Cómo estás</SectionTitle>
      <CheckIn data={data} />
    </Box>
  );
}

/** Tu día: consejos, curva hora a hora, métricas y comida. */
export function TodayDetail({ data, go }: { data: GarminData; go: (tab: string) => void }) {
  const cat = useCat();
  const days = data.days;
  const { latest, hrvDay, live } = useTodayRows(data);
  const isRun = (a: Activity) => a.group === 'Correr' || a.group === 'Cinta';  // VO2max solo de carrera
  const vo2 = [...data.activities].reverse().find((a) => a.vo2 != null && isRun(a));
  const imWeek = days.slice(-7).reduce((s, d) => s + (d.imMod ?? 0) + 2 * (d.imVig ?? 0), 0);
  const loadDay = days[days.length - 1];
  const hrvStatus = hrvDay?.hrv != null && hrvDay.hrvLow != null && hrvDay.hrvHigh != null
    ? hrvDay.hrv < hrvDay.hrvLow ? 'Por debajo de tu rango normal'
      : hrvDay.hrv > hrvDay.hrvHigh ? 'Por encima de tu rango normal' : 'Dentro de tu rango normal'
    : undefined;

  return (
    <Box>
      <PageHeader title="Tu día" subtitle="Consejos, tu día hora a hora y tus métricas" />
      <KeyFacts facts={[...sleepFacts(data), ...heartFacts(data), ...activityFacts(data)]} />

      <Stack direction="row" sx={{ alignItems: 'baseline', justifyContent: 'space-between', mb: 2 }}>
        <Typography variant="h6">Para ti</Typography>
        {data.ai && <AiBadge at={data.ai.generatedAt} />}
      </Stack>
      {data.ai?.today?.length
        ? <AiCards cards={data.ai.today} />
        : <InsightList items={data.insights.acciones} color={cat('energy')} icon={<TipsAndUpdates />} />}

      <TodayCurve bb={live?.bbSeries} hr={live?.hrSeries} asOf={live?.asOf} />

      <SectionTitle>Tus métricas</SectionTitle>
      <Box sx={{ display: 'grid', gap: { xs: 1.25, sm: 2 }, gridTemplateColumns: { xs: 'repeat(2, 1fr)', lg: 'repeat(3, 1fr)' } }}>
        <MetricCard icon={<Favorite />} color={cat('heart')} label="FC en reposo" help="rhr" value={latest?.rhr != null ? int(latest.rhr) : '—'} unit={latest?.rhr != null ? 'lpm' : undefined}
          delta={(() => { const v = vs30(days, latest, (d) => d.rhr); return v != null ? { value: v, unit: 'lpm', goodWhen: 'down' as const } : undefined; })()}
          spark={series(days, (d) => d.rhr)} onClick={() => go('corazon')} />
        <MetricCard icon={<MonitorHeart />} color={cat('recovery')} label="HRV nocturna" help="hrv" value={hrvDay ? int(hrvDay.hrv) : '—'} unit={hrvDay ? 'ms' : undefined}
          caption={hrvDay ? hrvStatus : 'Sin datos de anoche'}
          spark={series(days, (d) => d.hrv)} onClick={() => go('corazon')} />
        <MetricCard icon={<SelfImprovement />} color={cat('stress')} label="Estrés medio" help="stress" value={latest?.stress != null ? int(latest.stress) : '—'} unit={latest?.stress != null ? '/ 100' : undefined}
          delta={(() => { const v = vs30(days, latest, (d) => d.stress); return v != null ? { value: v, goodWhen: 'down' as const } : undefined; })()}
          spark={series(days, (d) => d.stress)} onClick={() => go('corazon')} />
        <MetricCard icon={<Bolt />} color={cat('activity')} label="Intensidad · 7 días" help="intensity" value={int(imWeek)} unit="/ 150"
          caption={imWeek >= 150 ? 'Objetivo semanal cumplido' : `Te faltan ${int(150 - imWeek)} min para el objetivo de la OMS`}
          spark={days.slice(-30).map((d) => (d.imMod ?? 0) + 2 * (d.imVig ?? 0))} onClick={() => go('actividad')} />
        <MetricCard icon={<Speed />} color={cat('training')} label="VO2max" help="vo2max" value={dec1(vo2?.vo2)} unit="ml/kg/min"
          caption={vo2 ? `Última estimación del reloj · ${dateShort(new Date(vo2.start))}` : undefined}
          spark={data.activities.filter((a) => a.vo2 != null && isRun(a)).slice(-30).map((a) => a.vo2!)} onClick={() => go('entreno')} />
        <MetricCard icon={<FitnessCenter />} color={cat('training')} label="Forma física (CTL)" help="ctl" value={int(loadDay?.ctl)}
          caption={loadDay?.acwr != null ? `Carga 7 d / 28 d: ${dec1(loadDay.acwr)}` : 'Sin carga reciente'}
          spark={series(days, (d) => d.ctl, 90)} onClick={() => go('entreno')} />
      </Box>

      <SectionTitle>Comida</SectionTitle>
      <FoodTodayCard go={go} mt={0} />
    </Box>
  );
}

/** Semana: objetivos, semana pasada y actividades recientes. */
export function TodayWeek({ data, go }: { data: GarminData; go: (tab: string) => void }) {
  const cat = useCat();
  const recent = [...data.activities].reverse().slice(0, 5);
  return (
    <Box>
      <PageHeader title="Semana" subtitle="Tus objetivos, cómo fue la semana pasada y lo último que has hecho" />
      <KeyFacts facts={[...trainingFacts(data), activityFacts(data)[1]]} />
      {data.ai?.weekly_focus && (
        <Card sx={{ ...CARD_SX, mb: 2, display: 'flex', gap: 2, alignItems: 'center' }}>
          <IconBubble color={cat('energy')}><TipsAndUpdates /></IconBubble>
          <Box>
            <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>Objetivo de la semana</Typography>
            <Typography>{data.ai.weekly_focus}</Typography>
          </Box>
        </Card>
      )}
      <Goals data={data} />

      <SectionTitle>Tu semana pasada</SectionTitle>
      <WeekCard data={data} />

      <SectionTitle>Actividades recientes</SectionTitle>
      <Card sx={{ ...CARD_SX, p: { xs: 0.5, sm: 1 } }}>
        <List disablePadding>
          {recent.map((a) => {
            const color = cat(a.group === 'Correr' || a.group === 'Cinta' ? 'training' : a.group === 'Natación' ? 'recovery' : 'activity');
            const bits = [
              a.km ? `${dec1(a.km)} km` : null,
              a.min ? `${int(a.min)} min` : null,
              a.pace && a.km && a.km > 0.5 ? pace(a.pace) : null,
              a.hr ? `${a.hr} lpm` : null,
            ].filter(Boolean).join(' · ');
            return (
              <ListItemButton key={a.id} sx={{ borderRadius: '16px' }} onClick={() => go(`act-${a.id}`)}>
                <ListItemAvatar><IconBubble color={color}><SportIcon group={a.group} /></IconBubble></ListItemAvatar>
                <ListItemText primary={a.name ?? a.group} secondary={bits} />
                <Typography variant="body2" color="text.secondary" sx={{ whiteSpace: 'nowrap', ml: 2 }}>
                  {dateShort(new Date(a.start))}
                </Typography>
              </ListItemButton>
            );
          })}
        </List>
      </Card>
    </Box>
  );
}
