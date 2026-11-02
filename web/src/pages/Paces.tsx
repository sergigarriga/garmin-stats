import { useEffect, useState } from 'react';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import Dialog from '@mui/material/Dialog';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { alpha } from '@mui/material/styles';
import { BarChart } from '@mui/x-charts/BarChart';
import SpeedRounded from '@mui/icons-material/SpeedRounded';
import PoolRounded from '@mui/icons-material/PoolRounded';
import FlagRounded from '@mui/icons-material/FlagRounded';
import FavoriteRounded from '@mui/icons-material/FavoriteRounded';
import { call } from '../account';
import { isoLocal, mmss, refreshData, toDate, type GarminData, type PaceZone } from '../data';
import { dateShort, dec1, duration, int } from '../format';
import { ZONES, useCat, useResolvedMode } from '../theme';
import { bandAxis, yClean } from '../charts';
import { CARD_SX, IconBubble, PageHeader, SectionTitle, chartSx } from '../ui';

const online = window.location.protocol.startsWith('http');
/** Primera letra en minúscula salvo siglas (VO2max). */
const lc = (t: string) => (/^[A-ZÁÉÍÓÚ][a-záéíóúñ]/.test(t) ? t[0].toLowerCase() + t.slice(1) : t);
const DIALOG = { paper: { sx: { borderRadius: '28px', m: 2, width: 'calc(100% - 32px)', maxWidth: 440 } } };

/** "1:35:40", "45:10" o "7:05" → segundos (null si no se entiende). */
export function parseTime(t: string): number | null {
  const p = t.trim().replace(/[.,']/g, ':').split(':').filter(Boolean).map(Number);
  if (!p.length || p.some((x) => !Number.isFinite(x) || x < 0)) return null;
  if (p.length === 1) return p[0] * 60;
  if (p.length === 2) return p[1] < 60 ? p[0] * 60 + p[1] : null;
  if (p.length === 3) return p[1] < 60 && p[2] < 60 ? p[0] * 3600 + p[1] * 60 + p[2] : null;
  return null;
}

function ZoneRows({ zones, unit }: { zones: PaceZone[]; unit: string }) {
  const mode = useResolvedMode();
  return (
    <Stack spacing={1}>
      {zones.map((z) => {
        const c = ZONES[mode][z.zone - 1];
        return (
          <Stack key={z.zone} direction="row" spacing={1.5} sx={{ alignItems: 'center', p: 1, pl: 1.25, borderRadius: '12px', bgcolor: alpha(c, mode === 'dark' ? 0.14 : 0.08) }}>
            <Box sx={{ width: 30, height: 30, borderRadius: '50%', bgcolor: c, color: '#fff', display: 'grid', placeItems: 'center', fontWeight: 700, fontSize: 13, flexShrink: 0 }}>Z{z.zone}</Box>
            <Typography sx={{ flex: 1, minWidth: 0, fontSize: { xs: 14, sm: 16 }, lineHeight: 1.25 }}>{z.name}</Typography>
            <Typography sx={{ fontWeight: 600, whiteSpace: 'nowrap', fontVariantNumeric: 'tabular-nums' }}>{mmss(z.fast)}–{mmss(z.slow)}<Box component="span" sx={{ color: 'text.secondary', fontWeight: 400 }}> {unit}</Box></Typography>
          </Stack>
        );
      })}
    </Stack>
  );
}

// ------------------------------------------------------------------ marca para los ritmos
const DISTANCES = [
  { label: '5 km', m: 5000 }, { label: '10 km', m: 10000 }, { label: 'Media maratón', m: 21097.5 }, { label: 'Maratón', m: 42195 },
  { label: 'Otra (km)', m: 0 },
];

function RaceDialog({ open, onClose, hasTest }: { open: boolean; onClose: () => void; hasTest: boolean }) {
  const [dist, setDist] = useState(10000);
  const [other, setOther] = useState('');
  const [time, setTime] = useState('');
  const [date, setDate] = useState(isoLocal(new Date()));
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { if (open) setErr(null); }, [open]);
  const send = async (body: Record<string, unknown>) => {
    setBusy(true); setErr(null);
    try { await call('./api/settings/race', body); refreshData(); onClose(); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  const save = () => {
    const meters = dist || Number(other.replace(',', '.')) * 1000;
    const secs = parseTime(time);
    if (!meters) { setErr('Indica la distancia.'); return; }
    if (!secs) { setErr('Escribe el tiempo como 45:10 o 1:35:40.'); return; }
    send({ distance_m: meters, time_s: secs, date });
  };
  return (
    <Dialog open={open} onClose={onClose} fullWidth slotProps={DIALOG}>
      <DialogTitle sx={{ pb: 1 }}>Tu marca reciente</DialogTitle>
      <DialogContent>
        <Typography color="text.secondary" sx={{ mb: 2 }}>
          Una carrera o un test a tope de los últimos meses. Con ella se calculan tus ritmos de entreno, y el plan los usa al momento.
        </Typography>
        <Stack spacing={2}>
          <Stack direction="row" spacing={1.5}>
            <TextField select label="Distancia" value={dist} onChange={(e) => setDist(Number(e.target.value))} sx={{ flex: 1 }}>
              {DISTANCES.map((d) => <MenuItem key={d.label} value={d.m}>{d.label}</MenuItem>)}
            </TextField>
            {dist === 0 && <TextField label="Km" value={other} onChange={(e) => setOther(e.target.value)} sx={{ width: 96 }} slotProps={{ htmlInput: { inputMode: 'decimal' } }} />}
          </Stack>
          <TextField label="Tiempo" placeholder="45:10 o 1:35:40" value={time} onChange={(e) => setTime(e.target.value)} slotProps={{ htmlInput: { inputMode: 'numeric' } }} />
          <TextField label="Fecha" type="date" value={date} onChange={(e) => setDate(e.target.value)} slotProps={{ inputLabel: { shrink: true } }} />
          {err && <Alert severity="error" sx={{ borderRadius: '14px' }}>{err}</Alert>}
          <Stack direction="row" spacing={1} sx={{ justifyContent: 'flex-end', flexWrap: 'wrap' }}>
            {hasTest && <Button color="error" disabled={busy} onClick={() => send({ clear: true })} sx={{ borderRadius: 999, mr: 'auto' }}>Quitar mi marca</Button>}
            <Button onClick={onClose} sx={{ borderRadius: 999 }}>Cancelar</Button>
            <Button variant="contained" disableElevation disabled={busy || !online} onClick={save} sx={{ borderRadius: 999 }}>{busy ? 'Guardando…' : 'Guardar'}</Button>
          </Stack>
        </Stack>
      </DialogContent>
    </Dialog>
  );
}

function SwimTestDialog({ open, onClose, hasTest, pool }: { open: boolean; onClose: () => void; hasTest: boolean; pool: number }) {
  const [t400, setT400] = useState('');
  const [t200, setT200] = useState('');
  const [poolM, setPoolM] = useState(pool === 50 ? 50 : pool < 24 ? 22.86 : 25);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { if (open) setErr(null); }, [open]);
  const send = async (body: Record<string, unknown>) => {
    setBusy(true); setErr(null);
    try { await call('./api/settings/swim', body); refreshData(); onClose(); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  const save = () => {
    const a = parseTime(t400), b = parseTime(t200);
    if (!a || !b) { setErr('Escribe los tiempos como 7:05 y 3:20.'); return; }
    send({ t400_s: a, t200_s: b, pool_m: poolM });
  };
  return (
    <Dialog open={open} onClose={onClose} fullWidth slotProps={DIALOG}>
      <DialogTitle sx={{ pb: 1 }}>Test de natación (CSS)</DialogTitle>
      <DialogContent>
        <Typography component="ol" color="text.secondary" sx={{ pl: 2.5, mt: 0, mb: 2, '& li': { mb: 0.5 } }}>
          <li>Calienta 10-15 minutos.</li>
          <li>Nada <b>400 m a tope</b> (crol) y apunta el tiempo.</li>
          <li>Descansa 5-10 minutos nadando suave.</li>
          <li>Nada <b>200 m a tope</b> y apunta el tiempo.</li>
        </Typography>
        <Stack spacing={2}>
          <Stack direction="row" spacing={1.5}>
            <TextField label="400 m" placeholder="7:05" value={t400} onChange={(e) => setT400(e.target.value)} sx={{ flex: 1 }} />
            <TextField label="200 m" placeholder="3:20" value={t200} onChange={(e) => setT200(e.target.value)} sx={{ flex: 1 }} />
          </Stack>
          <TextField select label="Piscina" value={poolM} onChange={(e) => setPoolM(Number(e.target.value))}>
            <MenuItem value={25}>25 m</MenuItem><MenuItem value={50}>50 m</MenuItem><MenuItem value={22.86}>25 yardas</MenuItem>
          </TextField>
          {err && <Alert severity="error" sx={{ borderRadius: '14px' }}>{err}</Alert>}
          <Stack direction="row" spacing={1} sx={{ justifyContent: 'flex-end', flexWrap: 'wrap' }}>
            {hasTest && <Button color="error" disabled={busy} onClick={() => send({ clear: true })} sx={{ borderRadius: 999, mr: 'auto' }}>Quitar el test</Button>}
            <Button onClick={onClose} sx={{ borderRadius: 999 }}>Cancelar</Button>
            <Button variant="contained" disableElevation disabled={busy || !online} onClick={save} sx={{ borderRadius: 999 }}>{busy ? 'Guardando…' : 'Guardar'}</Button>
          </Stack>
        </Stack>
      </DialogContent>
    </Dialog>
  );
}

// ------------------------------------------------------------------ página
export default function Paces({ data }: { data: GarminData }) {
  const cat = useCat();
  const mode = useResolvedMode();
  const [raceOpen, setRaceOpen] = useState(false);
  const [swimOpen, setSwimOpen] = useState(false);
  const p = data.paces;
  const sw = data.swim;
  const zones = data.profile.zones?.filter((z): z is number => z != null) ?? [];
  const maxHr = data.profile.max_hr;
  const swimColor = cat('recovery');

  return (
    <Box>
      <PageHeader title="Ritmos y zonas" subtitle="A qué ritmo entrenar según tu nivel de ahora. El plan y los entrenos del reloj los usan solos." />

      {p ? (
        <>
          <Card sx={{ ...CARD_SX, mb: 2 }}>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} sx={{ alignItems: { sm: 'center' } }}>
              <Stack direction="row" spacing={2} sx={{ alignItems: 'center', flex: 1, minWidth: 0 }}>
                <IconBubble color={cat('training')} size={48}><SpeedRounded /></IconBubble>
                <Box sx={{ minWidth: 0 }}>
                  <Typography variant="caption" color="text.secondary">Tu nivel (VDOT)</Typography>
                  <Typography sx={{ fontSize: 34, fontWeight: 500, lineHeight: 1.1 }}>{dec1(p.vdot)}</Typography>
                  <Typography variant="body2" color="text.secondary">Según {lc(p.sourceLabel)}{p.sourceDate ? ` · ${dateShort(toDate(p.sourceDate))}` : ''}</Typography>
                </Box>
              </Stack>
              <Button variant={p.source === 'race' ? 'outlined' : 'contained'} disableElevation startIcon={<FlagRounded />} onClick={() => setRaceOpen(true)}
                disabled={!online} sx={{ borderRadius: 999, alignSelf: { xs: 'flex-start', sm: 'center' }, flexShrink: 0 }}>
                {p.source === 'race' ? 'Cambiar mi marca' : 'Poner una marca reciente'}
              </Button>
            </Stack>
            {p.stale && <Alert severity="info" sx={{ borderRadius: '14px', mt: 2 }}>Tu marca tiene más de 6 meses: si has hecho una carrera o un test hace poco, ponla para afinar los ritmos.</Alert>}
            {p.others.length > 0 && (
              <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
                Otras estimaciones: {p.others.map((o) => `${lc(o.label)} → VDOT ${dec1(o.vdot)}`).join(' · ')}.
                {p.source !== 'race' && ' Si tienes una marca reciente, ponla: es lo más fiable.'}
              </Typography>
            )}
          </Card>

          <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', md: '1.3fr 1fr' } }}>
            <Card sx={{ ...CARD_SX }}>
              <Typography variant="subtitle1" sx={{ mb: 1.5 }}>Tus ritmos de entreno</Typography>
              <Stack divider={<Box sx={{ borderTop: 1, borderColor: 'divider' }} />}>
                {p.list.map((r) => (
                  <Stack key={r.key} direction="row" spacing={2} sx={{ alignItems: 'center', py: 1.1 }}>
                    <Box sx={{ flex: 1, minWidth: 0 }}>
                      <Typography sx={{ fontWeight: 500 }}>{r.label}</Typography>
                      <Typography variant="caption" color="text.secondary">{r.use}</Typography>
                    </Box>
                    <Typography sx={{ fontWeight: 600, whiteSpace: 'nowrap', fontVariantNumeric: 'tabular-nums', fontSize: 17 }}>
                      {r.key === 'easy' ? `${mmss(p.easyRange[0])}–${mmss(p.easyRange[1])}` : mmss(r.sec)}
                      <Box component="span" sx={{ color: 'text.secondary', fontWeight: 400, fontSize: 14 }}> /km</Box>
                    </Typography>
                  </Stack>
                ))}
              </Stack>
            </Card>
            <Stack spacing={2}>
              <Card sx={{ ...CARD_SX }}>
                <Typography variant="subtitle1" sx={{ mb: 1.5 }}>Zonas de ritmo</Typography>
                <ZoneRows zones={p.zones} unit="/km" />
              </Card>
              <Card sx={{ ...CARD_SX }}>
                <Typography variant="subtitle1" sx={{ mb: 1 }}>Lo que puedes correr hoy</Typography>
                <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 1.5 }}>
                  {p.races.map((r) => (
                    <Box key={r.distance}>
                      <Typography variant="caption" color="text.secondary">{r.distance}</Typography>
                      <Typography sx={{ fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}>{duration(r.time)}</Typography>
                    </Box>
                  ))}
                </Box>
              </Card>
            </Stack>
          </Box>
        </>
      ) : (
        <Card sx={{ ...CARD_SX, mb: 2 }}>
          <Typography sx={{ mb: 2 }}>Aún no hay datos para calcular tus ritmos. Pon una marca reciente (una carrera o un test a tope).</Typography>
          <Button variant="contained" disableElevation startIcon={<FlagRounded />} onClick={() => setRaceOpen(true)} disabled={!online} sx={{ borderRadius: 999 }}>Poner una marca</Button>
        </Card>
      )}

      {zones.length === 5 && (
        <>
          <SectionTitle>Zonas de pulso</SectionTitle>
          <Card sx={{ ...CARD_SX }}>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>Las de tu reloj (Garmin){maxHr ? `, con un pulso máximo de ${maxHr} lpm` : ''}.</Typography>
            <Stack spacing={1}>
              {zones.map((lo, i) => {
                const c = ZONES[mode][i];
                const hi = i < 4 ? zones[i + 1] - 1 : maxHr;
                const name = ['Muy suave', 'Suave', 'Moderado', 'Umbral', 'Máximo'][i];
                return (
                  <Stack key={i} direction="row" spacing={1.5} sx={{ alignItems: 'center', p: 1, pl: 1.25, borderRadius: '12px', bgcolor: alpha(c, mode === 'dark' ? 0.14 : 0.08) }}>
                    <Box sx={{ width: 30, height: 30, borderRadius: '50%', bgcolor: c, color: '#fff', display: 'grid', placeItems: 'center', fontWeight: 700, fontSize: 13, flexShrink: 0 }}>Z{i + 1}</Box>
                    <Typography sx={{ flex: 1 }}>{name}</Typography>
                    <Typography sx={{ fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}>{lo}{hi ? `–${hi}` : '+'}<Box component="span" sx={{ color: 'text.secondary', fontWeight: 400 }}> lpm</Box></Typography>
                    <FavoriteRounded sx={{ fontSize: 16, color: c }} />
                  </Stack>
                );
              })}
            </Stack>
          </Card>
        </>
      )}

      <SectionTitle>Natación</SectionTitle>
      {sw?.css ? (
        <>
          <Card sx={{ ...CARD_SX, mb: 2 }}>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} sx={{ alignItems: { sm: 'center' } }}>
              <Stack direction="row" spacing={2} sx={{ alignItems: 'center', flex: 1, minWidth: 0 }}>
                <IconBubble color={swimColor} size={48}><PoolRounded /></IconBubble>
                <Box sx={{ minWidth: 0 }}>
                  <Typography variant="caption" color="text.secondary">Tu ritmo umbral (CSS)</Typography>
                  <Typography sx={{ fontSize: 34, fontWeight: 500, lineHeight: 1.1 }}>{mmss(sw.css)}<Box component="span" sx={{ fontSize: 16, color: 'text.secondary', fontWeight: 400 }}> /100 m</Box></Typography>
                  <Typography variant="body2" color="text.secondary">
                    {sw.cssSource === 'test' && sw.test ? `Test del ${dateShort(toDate(sw.test.date))}: 400 m en ${mmss(sw.test.t400_s)} y 200 m en ${mmss(sw.test.t200_s)}`
                      : `Estimado con tu mejor nado (${sw.best ? `${int(sw.best.m)} m el ${dateShort(toDate(sw.best.d))}` : '–'}). Haz el test para afinarlo.`}
                  </Typography>
                </Box>
              </Stack>
              <Button variant={sw.cssSource === 'test' ? 'outlined' : 'contained'} disableElevation onClick={() => setSwimOpen(true)} disabled={!online}
                sx={{ borderRadius: 999, alignSelf: { xs: 'flex-start', sm: 'center' }, flexShrink: 0 }}>
                {sw.cssSource === 'test' ? 'Repetir el test' : 'Hacer el test (400 + 200 m)'}
              </Button>
            </Stack>
          </Card>
          <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', md: '1fr 1.3fr' } }}>
            <Card sx={{ ...CARD_SX }}>
              <Typography variant="subtitle1" sx={{ mb: 1.5 }}>Zonas de natación</Typography>
              <ZoneRows zones={sw.zones} unit="/100 m" />
            </Card>
            <Card sx={{ ...CARD_SX }}>
              <Stack direction="row" sx={{ justifyContent: 'space-between', alignItems: 'baseline', gap: 1, flexWrap: 'wrap' }}>
                <Typography variant="subtitle1">Metros por semana</Typography>
                <Typography variant="caption" color="text.secondary">{sw.totals.sessions} sesiones · {dec1(sw.totals.km)} km en total</Typography>
              </Stack>
              <BarChart height={200} sx={chartSx} grid={{ horizontal: true }} borderRadius={5} hideLegend
                xAxis={[bandAxis(sw.weeks.map((w) => w.start), { weekly: true })]} yAxis={[{ ...yClean, width: 44 }]}
                series={[{ data: sw.weeks.map((w) => w.m), label: 'Metros', color: swimColor, valueFormatter: (v) => `${int(v)} m` }]} />
              <Stack spacing={0.5} sx={{ mt: 1 }}>
                {sw.sessions.slice(-5).reverse().map((s) => (
                  <Stack key={s.id} direction="row" spacing={1.5} sx={{ fontSize: 14, color: 'text.secondary' }}>
                    <Box sx={{ width: 60 }}>{dateShort(toDate(s.d))}</Box>
                    <Box sx={{ flex: 1, color: 'text.primary' }}>{int(s.m)} m{s.open ? ' (aguas abiertas)' : ''}</Box>
                    <Box sx={{ fontVariantNumeric: 'tabular-nums' }}>{s.pace ? `${mmss(s.pace)} /100 m` : '–'}</Box>
                    {s.swolf != null && <Box sx={{ width: 76, textAlign: 'right' }}>SWOLF {s.swolf}</Box>}
                  </Stack>
                ))}
              </Stack>
            </Card>
          </Box>
        </>
      ) : (
        <Card sx={{ ...CARD_SX }}>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} sx={{ alignItems: { sm: 'center' } }}>
            <IconBubble color={swimColor}><PoolRounded /></IconBubble>
            <Typography sx={{ flex: 1 }}>Si nadas, haz el test de 400 + 200 m: con él salen tus zonas por 100 m y el coach puede programarte natación.</Typography>
            <Button variant="outlined" onClick={() => setSwimOpen(true)} disabled={!online} sx={{ borderRadius: 999, flexShrink: 0 }}>Hacer el test</Button>
          </Stack>
        </Card>
      )}

      <RaceDialog open={raceOpen} onClose={() => setRaceOpen(false)} hasTest={p?.source === 'race' || !!p?.test} />
      <SwimTestDialog open={swimOpen} onClose={() => setSwimOpen(false)} hasTest={!!sw?.test} pool={sw?.poolM ?? 25} />
    </Box>
  );
}
