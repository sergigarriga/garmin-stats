import { useEffect, useRef, useState } from 'react';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CircularProgress from '@mui/material/CircularProgress';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Typography from '@mui/material/Typography';
import { alpha } from '@mui/material/styles';
import ArrowBackRounded from '@mui/icons-material/ArrowBackRounded';
import { LineChart } from '@mui/x-charts/LineChart';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { loadActivity, type ActivityDetail as Detail, type GarminData } from '../data';
import { dateLong, dec1, duration, int, pace, time } from '../format';
import { SPORTS, ZONES, useCat, useResolvedMode } from '../theme';
import { CARD_SX, ChartCard, IconBubble, InfoTip, SectionTitle, chartSx } from '../ui';
import { yClean } from '../charts';
import { SportIcon } from './sport';

const ZONE_NAMES = ['Z1 muy suave', 'Z2 suave', 'Z3 moderado', 'Z4 umbral', 'Z5 máximo'];

function RouteMap({ track, color }: { track: [number, number][]; color: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const mode = useResolvedMode();
  useEffect(() => {
    if (!ref.current || track.length < 2) return;
    const map = L.map(ref.current, { zoomControl: true, attributionControl: true, scrollWheelZoom: false });
    // Mapa base gris de Esri (claro u oscuro según el tema): gratuito, sin clave, con atribución.
    const layer = mode === 'dark' ? 'Dark_Gray_Base' : 'Light_Gray_Base';
    L.tileLayer(`https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_${layer}/MapServer/tile/{z}/{y}/{x}`, {
      maxZoom: 16, attribution: 'Tiles &copy; Esri &mdash; Esri, HERE, Garmin, OpenStreetMap',
    }).addTo(map);
    const line = L.polyline(track, { color, weight: 4, opacity: 0.95, lineCap: 'round', lineJoin: 'round' }).addTo(map);
    const dot = (p: [number, number], fill: string) =>
      L.circleMarker(p, { radius: 7, color: '#fff', weight: 3, fillColor: fill, fillOpacity: 1 }).addTo(map);
    dot(track[0], '#188038');
    dot(track[track.length - 1], '#D93025');
    map.fitBounds(line.getBounds(), { padding: [24, 24] });
    return () => { map.remove(); };
  }, [track, color, mode]);
  return <Box ref={ref} sx={{ height: { xs: 280, md: 380 }, borderRadius: '20px', overflow: 'hidden', zIndex: 0,
    '& .leaflet-control-attribution': { fontSize: 10 } }} />;
}

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <Box>
      <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 500 }}>{label}</Typography>
      <Typography sx={{ fontSize: 24, fontWeight: 500, lineHeight: 1.2 }}>{value}</Typography>
      {sub && <Typography variant="caption" color="text.secondary">{sub}</Typography>}
    </Box>
  );
}

export default function ActivityDetail({ data, id, back }: { data: GarminData; id: number; back: () => void }) {
  const cat = useCat();
  const mode = useResolvedMode();
  const a = data.activities.find((x) => x.id === id);
  const [d, setD] = useState<Detail | null | undefined>(undefined);
  useEffect(() => { setD(undefined); loadActivity(id).then(setD); }, [id]);

  if (!a) return <Typography>Actividad no encontrada.</Typography>;
  const color = SPORTS[a.group]?.[mode] ?? cat('training');
  const isRun = a.group === 'Correr' || a.group === 'Cinta';
  const col = (name: string) => (d ? d.cols.indexOf(name) : -1);
  const series = d?.series ?? [];
  const hasKm = series.some((r) => (r[col('km')] ?? 0) > 0.2);
  const x = series.map((r) => (hasKm ? (r[col('km')] as number | null) : ((r[col('t')] as number) / 60)));
  const xAxis = [{ data: x, scaleType: 'linear' as const, disableLine: true, disableTicks: true,
    valueFormatter: (v: number | null) => (v == null ? '' : hasKm ? `${dec1(v)} km` : `${int(v)} min`) }];
  const pick = (name: string) => series.map((r) => (r[col(name)] as number | null) ?? null);
  const paceS = pick('pace').map((v) => (v != null && v > 2 && v < 15 ? v : null));
  const totalZ = (d?.zones ?? a.z).reduce((s, v) => s + v, 0);

  const start = new Date(a.start);
  const stats = [
    a.km ? { label: 'Distancia', value: `${dec1(a.km)} km` } : null,
    { label: 'Tiempo', value: duration((a.min ?? 0) * 60) },
    isRun && a.pace ? { label: 'Ritmo medio', value: pace(a.pace) } : null,
    a.hr ? { label: 'Pulso medio', value: `${a.hr} lpm`, sub: a.hrMax ? `máx. ${a.hrMax}` : undefined } : null,
    d?.elevGain ? { label: 'Desnivel', value: `${d.elevGain} m` } : null,
    a.cal ? { label: 'Calorías', value: `${int(a.cal)} kcal` } : null,
    a.trimp != null ? { label: 'Carga', value: int(a.trimp) } : null,
    a.vo2 != null ? { label: 'VO2max', value: dec1(a.vo2) } : null,
    a.cad ? { label: 'Cadencia', value: `${a.cad} ppm` } : null,
  ].filter(Boolean) as { label: string; value: string; sub?: string }[];

  return (
    <Box>
      <Button startIcon={<ArrowBackRounded />} onClick={back} sx={{ mb: 2, ml: -1, borderRadius: 999 }}>Volver</Button>
      <Stack direction="row" spacing={2} sx={{ alignItems: 'center', mb: 3 }}>
        <IconBubble color={color} size={52}><SportIcon group={a.group} /></IconBubble>
        <Box>
          <Typography variant="h4" component="h1" sx={{ fontSize: { xs: 26, sm: 32 } }}>{a.name ?? a.group}</Typography>
          <Typography color="text.secondary">
            {dateLong(start).replace(/^\w/, (c) => c.toUpperCase())} · {time(start)}{d?.location ? ` · ${d.location}` : ''}
          </Typography>
        </Box>
      </Stack>

      <Card sx={{ ...CARD_SX, mb: 2 }}>
        <Box sx={{ display: 'grid', gap: 2.5, gridTemplateColumns: { xs: '1fr 1fr', sm: 'repeat(3, 1fr)', md: `repeat(${Math.min(stats.length, 5)}, 1fr)` } }}>
          {stats.map((s) => <Stat key={s.label} {...s} />)}
        </Box>
      </Card>

      {d === undefined && <Box sx={{ display: 'grid', placeItems: 'center', py: 8 }}><CircularProgress /></Box>}
      {d === null && !a.sets?.length && <Typography color="text.secondary">No hay detalle segundo a segundo para esta actividad.</Typography>}

      {d && (
        <>
          {d.track.length > 1 && (
            <Card sx={{ ...CARD_SX, p: 1, mb: 2 }}><RouteMap track={d.track} color={color} /></Card>
          )}
          <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', lg: '1fr 1fr' } }}>
            {pick('hr').some((v) => v != null) && (
              <ChartCard title="Pulso" help="zones" subtitle={a.hr ? `Media ${a.hr} lpm${d.minHr ? ` · mínimo ${d.minHr}` : ''}` : undefined}>
                <LineChart height={220} sx={chartSx} grid={{ horizontal: true }} hideLegend xAxis={xAxis} yAxis={[{ ...yClean }]}
                  series={[{ data: pick('hr'), color: cat('heart'), showMark: false, area: true, curve: 'monotoneX', label: 'Pulso', valueFormatter: (v) => (v == null ? '–' : `${v} lpm`) }]} />
              </ChartCard>
            )}
            {isRun && paceS.some((v) => v != null) && (
              <ChartCard title="Ritmo" subtitle={a.pace ? `Medio ${pace(a.pace)} · más arriba = más rápido` : undefined}>
                <LineChart height={220} sx={chartSx} grid={{ horizontal: true }} hideLegend xAxis={xAxis}
                  yAxis={[{ ...yClean, reverse: true, valueFormatter: (v: number) => pace(v).replace(' /km', '') }]}
                  series={[{ data: paceS, color, showMark: false, curve: 'monotoneX', label: 'Ritmo', valueFormatter: (v) => pace(v) }]} />
              </ChartCard>
            )}
            {pick('alt').some((v) => v != null) && (
              <ChartCard title="Altitud" subtitle={d.elevGain ? `+${d.elevGain} m de desnivel` : undefined}>
                <LineChart height={220} sx={chartSx} grid={{ horizontal: true }} hideLegend xAxis={xAxis} yAxis={[{ ...yClean }]}
                  series={[{ data: pick('alt'), color: cat('activity'), showMark: false, area: true, curve: 'monotoneX', label: 'Altitud', valueFormatter: (v) => (v == null ? '–' : `${int(v)} m`) }]} />
              </ChartCard>
            )}
            {totalZ > 0 && (
              <ChartCard title="Tiempo en cada zona" help="zones">
                <Stack spacing={1.5} sx={{ mt: 1 }}>
                  {[...d.zones].map((v, i) => ({ v, i })).reverse().map(({ v, i }) => (
                    <Box key={i}>
                      <Stack direction="row" sx={{ justifyContent: 'space-between', mb: 0.5 }}>
                        <Typography variant="body2">{ZONE_NAMES[i]}{d.zoneFloors?.[i] ? <Box component="span" sx={{ color: 'text.secondary' }}> · desde {d.zoneFloors[i]} lpm</Box> : null}</Typography>
                        <Typography variant="body2" color="text.secondary">{duration(v * 60)} · {Math.round((v / totalZ) * 100)} %</Typography>
                      </Stack>
                      <Box sx={{ height: 10, borderRadius: 999, bgcolor: alpha(ZONES[mode][i], 0.15), overflow: 'hidden' }}>
                        <Box sx={{ height: '100%', width: `${(v / totalZ) * 100}%`, bgcolor: ZONES[mode][i], borderRadius: 999 }} />
                      </Box>
                    </Box>
                  ))}
                </Stack>
              </ChartCard>
            )}
          </Box>

          {d.splits.length > 1 && (
            <>
              <SectionTitle>Parciales por kilómetro</SectionTitle>
              <Card sx={{ ...CARD_SX, p: 0, overflowX: 'auto' }}>
                <Table size="small" sx={{ '& td, & th': { px: { xs: 1, sm: 2 } } }}>
                  <TableHead>
                    <TableRow>
                      {['Km', 'Tiempo', 'Ritmo', '', 'Pulso', 'Desnivel'].map((h, i) => (
                        <TableCell key={i} align={i ? 'right' : 'left'} sx={{ color: 'text.secondary', fontWeight: 500, py: 1.5, ...(i === 3 ? { display: { xs: 'none', sm: 'table-cell' } } : {}) }}>{h}</TableCell>
                      ))}
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {(() => {
                      const ps = d.splits.map((s) => s.pace);
                      const fast = Math.min(...ps), slow = Math.max(...ps);
                      return d.splits.map((s) => {
                        const w = slow > fast ? 30 + 70 * ((slow - s.pace) / (slow - fast)) : 100;
                        return (
                          <TableRow key={s.km} hover>
                            <TableCell>{s.km}</TableCell>
                            <TableCell align="right">{duration(s.time)}</TableCell>
                            <TableCell align="right" sx={{ whiteSpace: 'nowrap' }}>{pace(s.pace)}</TableCell>
                            <TableCell sx={{ width: { sm: 180 }, display: { xs: 'none', sm: 'table-cell' } }}>
                              <Box sx={{ height: 8, width: `${w}%`, borderRadius: 999, bgcolor: color, opacity: s.pace === fast ? 1 : 0.55 }} />
                            </TableCell>
                            <TableCell align="right">{s.hr ?? '–'}</TableCell>
                            <TableCell align="right">{s.elev == null ? '–' : `${s.elev > 0 ? '+' : ''}${s.elev} m`}</TableCell>
                          </TableRow>
                        );
                      });
                    })()}
                  </TableBody>
                </Table>
              </Card>
            </>
          )}

          {a.sets && a.sets.length > 0 && (
            <>
              <SectionTitle>Ejercicios</SectionTitle>
              <Box sx={{ display: 'grid', gap: 1.5, gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' } }}>
                {Object.entries(a.sets.reduce<Record<string, typeof a.sets>>((m, s) => { (m[s.ex] ??= []).push(s); return m; }, {}))
                  .map(([ex, ss]) => (
                    <Card key={ex} sx={{ ...CARD_SX, py: 2 }}>
                      <Stack direction="row" sx={{ justifyContent: 'space-between', alignItems: 'baseline', mb: 1 }}>
                        <Typography variant="subtitle1">{ex}</Typography>
                        <Typography variant="body2" color="text.secondary">{ss!.length} series · {ss!.reduce((t, s) => t + s.reps, 0)} reps</Typography>
                      </Stack>
                      <Stack direction="row" sx={{ flexWrap: 'wrap', gap: 1 }}>
                        {ss!.map((s, i) => (
                          <Box key={i} sx={{ px: 1.25, py: 0.5, borderRadius: '10px', fontSize: 14, fontWeight: 500,
                            bgcolor: alpha(color, mode === 'dark' ? 0.18 : 0.1) }}>
                            {s.reps}{s.kg ? ` × ${dec1(s.kg)} kg` : ' reps'}
                          </Box>
                        ))}
                      </Stack>
                    </Card>
                  ))}
              </Box>
              {a.sets.every((s) => !s.kg) && (
                <Typography variant="body2" color="text.secondary" sx={{ mt: 1.5 }}>
                  El reloj no guardó el peso de estas series. Si lo confirmas en el reloj al terminar cada serie, el coach podrá subir las cargas.
                </Typography>
              )}
            </>
          )}

          {isRun && (d.stride || d.gct || d.vertOsc) && (
            <>
              <SectionTitle>Técnica de carrera</SectionTitle>
              <Card sx={{ ...CARD_SX }}>
                <Box sx={{ display: 'grid', gap: 2.5, gridTemplateColumns: { xs: '1fr 1fr', md: 'repeat(4, 1fr)' } }}>
                  {a.cad ? <Stat label="Cadencia" value={`${a.cad} ppm`} sub="pasos por minuto" /> : null}
                  {d.stride ? <Stat label="Zancada" value={`${dec1(d.stride)} m`} /> : null}
                  {d.gct ? <Stat label="Contacto con el suelo" value={`${d.gct} ms`} sub="menos = más reactivo" /> : null}
                  {d.vertOsc ? <Stat label="Oscilación vertical" value={`${dec1(d.vertOsc)} cm`} sub="cuánto botas al correr" /> : null}
                </Box>
              </Card>
            </>
          )}
          <Box sx={{ mt: 2 }}><InfoTip k="trimp" /> <Typography component="span" variant="body2" color="text.secondary">Qué es la carga</Typography></Box>
        </>
      )}
    </Box>
  );
}
