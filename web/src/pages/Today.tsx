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
import { isoLocal, lastWith, mean, toDate, type GarminData, type Day } from '../data';
import { dateLong, dateShort, hm, int, dec1, pace } from '../format';
import { useCat } from '../theme';
import { AiBadge, AiCards, CARD_SX, IconBubble, InsightList, MetricCard, PageHeader, RingCard, SectionTitle } from '../ui';
import Stack from '@mui/material/Stack';
import { SportIcon } from './sport';
import { Rich } from '../rich';
import DirectionsRunRounded from '@mui/icons-material/DirectionsRunRounded';
import { Alerts, Goals, ReadinessCard, WeekCard } from './TodayExtras';

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

export default function Today({ data, go }: { data: GarminData; go: (tab: string) => void }) {
  const cat = useCat();
  const days = data.days;
  // Solo datos de HOY: si Garmin aún no los tiene, se muestra "—" en vez de los de ayer.
  const todayIso = isoLocal(new Date());
  const row = days.find((d) => d.d === todayIso);
  const latest = row?.rhr != null || row?.steps != null ? row : undefined;
  const night = row?.sleepH != null ? row : undefined;  // la noche lleva la fecha del día en que te despiertas
  const hrvDay = row?.hrv != null ? row : undefined;
  const lastSync = lastWith(days, (d) => d.rhr ?? d.steps);
  const vo2 = [...data.activities].reverse().find((a) => a.vo2 != null);
  const last7 = days.slice(-7);
  const imWeek = last7.reduce((s, d) => s + (d.imMod ?? 0) + 2 * (d.imVig ?? 0), 0);
  const loadDay = days[days.length - 1];
  const today = new Date();
  const isToday = !!latest;

  const hrvStatus = hrvDay?.hrv != null && hrvDay.hrvLow != null && hrvDay.hrvHigh != null
    ? hrvDay.hrv < hrvDay.hrvLow ? 'Por debajo de tu rango normal'
      : hrvDay.hrv > hrvDay.hrvHigh ? 'Por encima de tu rango normal' : 'Dentro de tu rango normal'
    : undefined;

  const recent = [...data.activities].reverse().slice(0, 5);

  return (
    <Box>
      <PageHeader
        title="Hoy"
        subtitle={`${dateLong(today).replace(/^\w/, (c) => c.toUpperCase())}${!isToday && lastSync ? ` · aún no hay datos de hoy (últimos del ${dateShort(toDate(lastSync.d))})` : ''}`}
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
        <RingCard icon={<BatteryChargingFull />} color={cat('energy')} label="Body Battery" help="bodyBattery"
          value={latest?.bbMax ?? 0} max={100}
          center={latest?.bbMax != null ? int(latest.bbMax) : '—'} sub={latest?.bbMax != null ? 'máximo del día' : 'sin datos de hoy'}
          caption={latest?.bbMin != null ? `Mínimo ${latest.bbMin} · cargado +${latest.bbCharged ?? '–'}` : 'Sin datos de hoy'} />
      </Box>

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
          spark={data.activities.filter((a) => a.vo2 != null).slice(-30).map((a) => a.vo2!)} onClick={() => go('entreno')} />
        <MetricCard icon={<FitnessCenter />} color={cat('training')} label="Forma física (CTL)" help="ctl" value={int(loadDay?.ctl)}
          caption={loadDay?.acwr != null ? `Carga 7 d / 28 d: ${dec1(loadDay.acwr)}` : 'Sin carga reciente'}
          spark={series(days, (d) => d.ctl, 90)} onClick={() => go('entreno')} />
      </Box>

      <SectionTitle>Tus objetivos de la semana</SectionTitle>
      <Goals data={data} />

      <SectionTitle>Tu semana pasada</SectionTitle>
      <WeekCard data={data} />

      <Stack direction="row" sx={{ alignItems: 'baseline', justifyContent: 'space-between', mt: 5, mb: 2 }}>
        <Typography variant="h6">Para ti</Typography>
        {data.ai && <AiBadge at={data.ai.generatedAt} />}
      </Stack>
      {data.ai?.today?.length ? (
        <>
          <AiCards cards={data.ai.today} />
          {data.ai.weekly_focus && (
            <Card sx={{ ...CARD_SX, mt: 2, display: 'flex', gap: 2, alignItems: 'center' }}>
              <IconBubble color={cat('energy')}><TipsAndUpdates /></IconBubble>
              <Box>
                <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>Objetivo de la semana</Typography>
                <Typography>{data.ai.weekly_focus}</Typography>
              </Box>
            </Card>
          )}
        </>
      ) : (
        <InsightList items={data.insights.acciones} color={cat('energy')} icon={<TipsAndUpdates />} />
      )}

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
