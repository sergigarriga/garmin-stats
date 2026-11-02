import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableContainer from '@mui/material/TableContainer';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Typography from '@mui/material/Typography';
import useMediaQuery from '@mui/material/useMediaQuery';
import { alpha } from '@mui/material/styles';
import { BarChart } from '@mui/x-charts/BarChart';
import { SparkLineChart } from '@mui/x-charts/SparkLineChart';
import FitnessCenterRounded from '@mui/icons-material/FitnessCenterRounded';
import { toDate, type GarminData } from '../data';
import { dateShort, dec1, int } from '../format';
import { useCat, useResolvedMode } from '../theme';
import { bandAxis, yClean } from '../charts';
import { CARD_SX, IconBubble, PageHeader, SectionTitle, chartSx } from '../ui';

/** Un color por grupo muscular (claro, oscuro). */
const MUSCLE_COLOR: Record<string, [string, string]> = {
  chest: ['#D93025', '#F28B82'], back: ['#1A73E8', '#8AB4F8'], shoulders: ['#E8710A', '#FCAD70'], biceps: ['#9334E6', '#D7AEFB'],
  triceps: ['#C5221F', '#F6AEA9'], quads: ['#188038', '#81C995'], hamstrings: ['#137333', '#A8DAB5'], glutes: ['#00838F', '#78D9EC'],
  calves: ['#5B5BD6', '#AFADFF'], core: ['#C26401', '#FDD663'], fullbody: ['#80868B', '#BDC1C6'],
};
/** "11 dic", con el año si no es este. */
const day = (iso: string) => { const d = toDate(iso); return d.getFullYear() === new Date().getFullYear() ? dateShort(d) : `${dateShort(d)} ${String(d.getFullYear()).slice(2)}`; };
const kg = (v: number) => (Number.isInteger(v) ? `${v}` : dec1(v));

export default function Gym({ data, go }: { data: GarminData; go: (k: string) => void }) {
  const cat = useCat();
  const mode = useResolvedMode();
  const small = useMediaQuery('(max-width:599px)');
  const g = data.gym;
  const color = cat('training');
  if (!g) {
    return (
      <Box>
        <PageHeader title="Gimnasio" subtitle="Tus series, tus récords y el volumen de cada músculo" />
        <Card sx={{ ...CARD_SX }}>
          <Typography color="text.secondary">Aún no hay sesiones de fuerza. Graba el gimnasio en el reloj (actividad "Fuerza") y confirma repeticiones y peso al acabar cada serie.</Typography>
        </Card>
      </Box>
    );
  }
  const muscles = g.muscles.filter((m) => g.weeks.some((w) => w.muscles[m.key]));
  const noKg = data.activities.filter((a) => a.type === 'strength_training').flatMap((a) => a.sets ?? []).filter((s) => !s.kg).length;
  const maxAvg = Math.max(12, ...g.muscleAvg4w.map((m) => m.sets));
  const recent = data.activities.filter((a) => a.type === 'strength_training').slice(-6).reverse();

  return (
    <Box>
      <PageHeader title="Gimnasio" subtitle="Lo que registra tu reloj en cada serie: récords, volumen por músculo y progresión" />
      <Box sx={{ display: 'grid', gap: { xs: 1.25, sm: 2 }, gridTemplateColumns: { xs: 'repeat(2, 1fr)', md: 'repeat(4, 1fr)' }, mb: 2 }}>
        {[
          { l: 'Sesiones', v: int(g.totals.sessions), s: `${g.totals.withSets} con series` },
          { l: 'Series registradas', v: int(g.totals.sets), s: noKg ? `${noKg} sin peso` : 'todas con peso' },
          { l: 'Esta semana', v: `${int(g.weeks[g.weeks.length - 1]?.sets ?? 0)} series`, s: `${int(g.weeks[g.weeks.length - 1]?.kg ?? 0)} kg levantados` },
          { l: 'Mejor 1RM estimado', v: g.records[0]?.best ? `${kg(g.records[0].best.e1rm)} kg` : '–', s: g.records[0]?.best ? g.records[0].ex : 'sin series con peso' },
        ].map((x) => (
          <Card key={x.l} sx={{ ...CARD_SX, p: { xs: 1.75, sm: 2.5 } }}>
            <Typography variant="caption" color="text.secondary">{x.l}</Typography>
            <Typography sx={{ fontSize: { xs: 22, sm: 28 }, fontWeight: 500, lineHeight: 1.2 }} noWrap>{x.v}</Typography>
            <Typography variant="caption" color="text.secondary" noWrap sx={{ display: 'block' }}>{x.s}</Typography>
          </Card>
        ))}
      </Box>
      {noKg > 0 && (
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          En {noKg} series el reloj no tiene el peso. Al acabar cada serie, confirma en el reloj las repeticiones y los kilos: así salen tus récords y el coach sabe cuánto subir.
        </Typography>
      )}

      <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', md: '1fr 1.4fr' } }}>
        <Card sx={{ ...CARD_SX }}>
          <Typography variant="subtitle1">Series por músculo</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>Media semanal de las últimas 4 semanas. Los ejercicios que ayudan cuentan media serie.</Typography>
          {g.muscleAvg4w.length ? (
            <Stack spacing={1.25}>
              {g.muscleAvg4w.map((m) => {
                const c = (MUSCLE_COLOR[m.muscle] ?? MUSCLE_COLOR.fullbody)[mode === 'dark' ? 1 : 0];
                return (
                  <Box key={m.muscle}>
                    <Stack direction="row" sx={{ justifyContent: 'space-between', mb: 0.5 }}>
                      <Typography variant="body2">{m.label}</Typography>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>{dec1(m.sets)}</Typography>
                    </Stack>
                    <Box sx={{ height: 8, borderRadius: 999, bgcolor: alpha(c, 0.15), overflow: 'hidden' }}>
                      <Box sx={{ height: '100%', width: `${Math.min(100, (m.sets / maxAvg) * 100)}%`, bgcolor: c, borderRadius: 999 }} />
                    </Box>
                  </Box>
                );
              })}
              <Typography variant="caption" color="text.secondary">Referencia: 6-12 series por músculo y semana para ganar fuerza sin quitarle piernas a la carrera.</Typography>
            </Stack>
          ) : <Typography color="text.secondary">Sin series en las últimas 4 semanas.</Typography>}
        </Card>
        <Card sx={{ ...CARD_SX }}>
          <Typography variant="subtitle1">Series por semana</Typography>
          <Typography variant="body2" color="text.secondary">Últimas 12 semanas, por músculo (los que ayudan cuentan media serie)</Typography>
          <BarChart height={260} sx={chartSx} grid={{ horizontal: true }} borderRadius={4}
            xAxis={[bandAxis(g.weeks.map((w) => w.start), { weekly: true })]} yAxis={[{ ...yClean, width: 32 }]}
            slotProps={{ legend: { position: { vertical: 'bottom', horizontal: 'center' } } }}
            series={muscles.map((m) => ({
              data: g.weeks.map((w) => w.muscles[m.key] ?? 0), label: m.label, stack: 'm',
              color: (MUSCLE_COLOR[m.key] ?? MUSCLE_COLOR.fullbody)[mode === 'dark' ? 1 : 0], valueFormatter: (v: number | null) => (v ? dec1(v) : '–'),
            }))} />
        </Card>
      </Box>

      <SectionTitle>Récords por ejercicio</SectionTitle>
      <Card sx={{ ...CARD_SX, p: { xs: 0.5, sm: 1.5 } }}>
        <TableContainer>
          <Table size="small" sx={{ '& td, & th': { borderColor: 'divider' } }}>
            <TableHead>
              <TableRow>
                <TableCell>Ejercicio</TableCell>
                <TableCell align="right">1RM estimado</TableCell>
                {!small && <TableCell align="right">Mejor serie</TableCell>}
                {!small && <TableCell align="right">Series</TableCell>}
                <TableCell align="right" sx={{ width: { xs: 64, sm: 110 } }}>Progreso</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {g.records.map((r) => (
                <TableRow key={r.ex} hover sx={{ cursor: r.best ? 'pointer' : 'default' }} onClick={() => r.best && go(`act-${r.best.id}`)}>
                  <TableCell>
                    <Typography variant="body2" sx={{ fontWeight: 500 }}>{r.ex}</Typography>
                    <Typography variant="caption" color="text.secondary">{r.label}{small && r.best ? ` · ${r.best.reps} × ${kg(r.best.kg)} kg` : ''}</Typography>
                  </TableCell>
                  <TableCell align="right" sx={{ whiteSpace: 'nowrap' }}>
                    {r.best ? <><b>{kg(r.best.e1rm)} kg</b><Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>{day(r.best.d)}</Typography></>
                      : <Typography variant="body2" color="text.secondary">{r.maxReps ? `máx ${r.maxReps} rep.` : '–'}</Typography>}
                  </TableCell>
                  {!small && <TableCell align="right" sx={{ whiteSpace: 'nowrap' }}>{r.best ? `${r.best.reps} × ${kg(r.best.kg)} kg` : r.maxKg ? `${r.maxKg.reps} × ${kg(r.maxKg.kg)} kg` : '–'}</TableCell>}
                  {!small && <TableCell align="right">{r.sets}</TableCell>}
                  <TableCell align="right">
                    {r.trend.length > 1
                      ? <SparkLineChart data={r.trend.map((t) => t.e1rm)} height={28} width={small ? 56 : 100} color={color} curve="linear" />
                      : <Typography variant="caption" color="text.disabled">–</Typography>}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', px: 2, py: 1.25 }}>
          1RM estimado: el peso que podrías levantar una vez, calculado con la fórmula de Epley a partir de series de hasta 12 repeticiones.
        </Typography>
      </Card>

      <SectionTitle>Últimas sesiones</SectionTitle>
      <Stack spacing={1}>
        {recent.map((a) => {
          const sets = (a.sets ?? []).filter((s) => s.ex !== 'Calentamiento');
          const exs = [...new Set(sets.map((s) => s.ex))];
          const tonnage = sets.reduce((t, s) => t + (s.kg ?? 0) * s.reps, 0);
          return (
            <Card key={a.id} onClick={() => go(`act-${a.id}`)} sx={{ ...CARD_SX, py: 1.75, cursor: 'pointer', display: 'flex', gap: 2, alignItems: 'center' }}>
              <IconBubble color={color}><FitnessCenterRounded /></IconBubble>
              <Box sx={{ flex: 1, minWidth: 0 }}>
                <Typography sx={{ fontWeight: 500 }} noWrap>{a.name ?? 'Fuerza'} · {dateShort(new Date(a.start))}</Typography>
                <Typography variant="body2" color="text.secondary" sx={{ display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                  {sets.length ? `${exs.length} ejercicios · ${sets.length} series${tonnage ? ` · ${int(tonnage)} kg` : ''} · ${exs.slice(0, 3).join(', ')}${exs.length > 3 ? '…' : ''}` : `${int(a.min)} min · sin series registradas`}
                </Typography>
              </Box>
            </Card>
          );
        })}
      </Stack>
    </Box>
  );
}
