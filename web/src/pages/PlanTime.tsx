// "Tu tiempo" (minutos que tienes cada día) y "El tiempo que hará" (ciudad y previsión) en la página del Plan.
// Guardar no llama a la IA: el plan se reajusta con el botón (o solo el lunes), así no se gasta en cada cambio.
import { useEffect, useMemo, useState, type ReactNode } from 'react';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import ButtonBase from '@mui/material/ButtonBase';
import Card from '@mui/material/Card';
import Chip from '@mui/material/Chip';
import CircularProgress from '@mui/material/CircularProgress';
import InputAdornment from '@mui/material/InputAdornment';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import ToggleButton from '@mui/material/ToggleButton';
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import { alpha } from '@mui/material/styles';
import WbSunnyRounded from '@mui/icons-material/WbSunnyRounded';
import WbCloudyRounded from '@mui/icons-material/WbCloudyRounded';
import FilterDramaRounded from '@mui/icons-material/FilterDramaRounded';
import CloudRounded from '@mui/icons-material/CloudRounded';
import ThunderstormRounded from '@mui/icons-material/ThunderstormRounded';
import UmbrellaRounded from '@mui/icons-material/UmbrellaRounded';
import AcUnitRounded from '@mui/icons-material/AcUnitRounded';
import ScheduleRounded from '@mui/icons-material/ScheduleRounded';
import SearchRounded from '@mui/icons-material/SearchRounded';
import LocationOnRounded from '@mui/icons-material/LocationOnRounded';
import WarningAmberRounded from '@mui/icons-material/WarningAmberRounded';
import TuneRounded from '@mui/icons-material/TuneRounded';
import { call } from '../account';
import { isoLocal, refreshData, toDate, type Availability, type CoachView, type Place, type WeatherBlock, type WeatherDay } from '../data';
import { useResolvedMode } from '../theme';
import { CARD_SX, IconBubble } from '../ui';

type Mode = 'light' | 'dark';
const LETTERS = ['L', 'M', 'X', 'J', 'V', 'S', 'D'];
const DAY_NAMES = ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo'];
/** Atajos: null = libre (el coach decide), 0 = nada. */
const QUICK: { v: number | null; label: string }[] = [
  { v: null, label: 'Libre' }, { v: 30, label: '30 min' }, { v: 45, label: '45 min' }, { v: 60, label: '1 h' },
  { v: 90, label: '1 h 30' }, { v: 120, label: '2 h' }, { v: 180, label: '3 h' }, { v: 0, label: 'Nada' },
];
const PILL_SX = { borderRadius: 999 } as const;

/** 45 → "45 min", 60 → "1 h", 90 → "1 h 30", null → "Libre", 0 → "Nada". */
export function minLabel(m: number | null | undefined): string {
  if (m == null) return 'Libre';
  if (m === 0) return 'Nada';
  if (m < 60) return `${m} min`;
  const h = Math.floor(m / 60), r = m % 60;
  return r ? `${h} h ${String(r).padStart(2, '0')}` : `${h} h`;
}

const weekday = (iso: string) => (toDate(iso).getDay() + 6) % 7;  // 0 = lunes

/** Minutos de una fecha: el día concreto manda sobre la semana tipo. */
export function availFor(a: Availability | null | undefined, iso: string): number | null | undefined {
  if (!a) return undefined;
  if (iso in a.days) return a.days[iso];
  return a.weekly[String(weekday(iso))] ?? null;
}

// ------------------------------------------------------------------ iconos y chapitas del tiempo
const WX_COLOR: Record<string, { light: string; dark: string }> = {
  sun: { light: '#E37400', dark: '#FDD663' }, cloud: { light: '#5F6368', dark: '#BDC1C6' },
  rain: { light: '#1A73E8', dark: '#8AB4F8' }, storm: { light: '#9334E6', dark: '#D7AEFB' }, snow: { light: '#00838F', dark: '#78D9EC' },
};

function wxKind(code?: number | null): keyof typeof WX_COLOR {
  if (code == null || code <= 1) return 'sun';
  if (code >= 95) return 'storm';
  if ((code >= 71 && code <= 77) || code === 85 || code === 86) return 'snow';
  if (code >= 51) return 'rain';
  return 'cloud';
}

export function WeatherIcon({ code, size = 18 }: { code?: number | null; size?: number }) {
  const mode = useResolvedMode() as Mode;
  const k = wxKind(code);
  const sx = { fontSize: size, color: WX_COLOR[k][mode] };
  if (k === 'sun') return <WbSunnyRounded sx={sx} />;
  if (k === 'storm') return <ThunderstormRounded sx={sx} />;
  if (k === 'snow') return <AcUnitRounded sx={sx} />;
  if (k === 'rain') return <UmbrellaRounded sx={sx} />;
  if (code === 2) return <FilterDramaRounded sx={sx} />;
  if (code === 45 || code === 48) return <CloudRounded sx={sx} />;
  return <WbCloudyRounded sx={sx} />;
}

/** "☀ 24° · 30 %" en una línea, con el texto completo al pasar por encima. */
export function WeatherBadge({ d, compact }: { d?: WeatherDay; compact?: boolean }) {
  if (!d) return null;
  const rain = d.rainProb != null && d.rainProb >= 20 ? `${d.rainProb} %` : null;
  const title = [d.text, `${d.tmin ?? '–'}-${d.tmax ?? '–'} °C`, d.rainProb != null ? `lluvia ${d.rainProb} %` : null,
    d.windMax != null ? `viento ${d.windMax} km/h` : null, d.windows?.[0] ? `mejor franja ${d.windows[0].from}-${d.windows[0].to}` : null]
    .filter(Boolean).join(' · ');
  return (
    <Tooltip title={title}>
      <Box component="span" sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.4, fontSize: compact ? 12 : 13, color: 'text.secondary', whiteSpace: 'nowrap', fontWeight: 500 }}>
        <WeatherIcon code={d.code} size={compact ? 15 : 17} />
        {d.tmax != null && <span>{d.tmax}°</span>}
        {rain && !compact && <span>· {rain}</span>}
      </Box>
    </Tooltip>
  );
}

/** Chapita "Tienes 45 min" o aviso "No cabe: 80 de 45 min". */
export function TimeTag({ avail, warn }: { avail?: number | null; warn?: { avail: number; planned: number } | null }) {
  if (warn) {
    return (
      <Tooltip title="La sesión pasa de tu tiempo de ese día. Reajusta el plan con tu tiempo o cambia el día.">
        <Box component="span" sx={{ display: 'inline-flex', alignItems: 'flex-start', gap: 0.4, px: 0.75, py: 0.25, borderRadius: '10px', fontSize: 11.5, fontWeight: 600,
          lineHeight: 1.3, color: 'warning.main', bgcolor: (t) => alpha(t.palette.warning.main, 0.12), maxWidth: '100%' }}>
          <WarningAmberRounded sx={{ fontSize: 14, mt: '1px', flexShrink: 0 }} />
          <span>{warn.avail === 0 ? `Día sin tiempo (${warn.planned} min)` : `No cabe: ${warn.planned} de ${warn.avail} min`}</span>
        </Box>
      </Tooltip>
    );
  }
  if (avail === undefined) return null;
  return (
    <Box component="span" sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.4, fontSize: 12, color: 'text.secondary', whiteSpace: 'nowrap' }}>
      <ScheduleRounded sx={{ fontSize: 14 }} />{avail == null ? 'Libre' : avail === 0 ? 'Sin tiempo' : minLabel(avail)}
    </Box>
  );
}

// ------------------------------------------------------------------ "Tu tiempo"
function Tile({ top, bottom, selected, marked, onClick }: { top: ReactNode; bottom: string; selected: boolean; marked?: boolean; onClick: () => void }) {
  return (
    <ButtonBase onClick={onClick} aria-pressed={selected} sx={{
      flexDirection: 'column', gap: 0.25, py: 1, px: 0.5, minWidth: 0, borderRadius: '14px', border: 1,
      borderColor: selected ? 'primary.main' : 'divider',
      bgcolor: selected ? 'color-mix(in srgb, var(--mui-palette-primary-main) 14%, transparent)' : 'transparent',
      color: selected ? 'primary.main' : 'text.primary', position: 'relative' }}>
      <Typography variant="caption" sx={{ fontWeight: 700, lineHeight: 1.1, color: selected ? 'primary.main' : 'text.secondary', textTransform: 'capitalize' }}>{top}</Typography>
      <Typography sx={{ fontSize: 13, fontWeight: 600, lineHeight: 1.2, whiteSpace: 'nowrap' }}>{bottom}</Typography>
      {marked && <Box sx={{ position: 'absolute', top: 5, right: 6, width: 6, height: 6, borderRadius: '50%', bgcolor: 'primary.main' }} />}
    </ButtonBase>
  );
}

export function TimeEditor({ value, onSaved, onReplan, busy, warnings }: {
  value: Availability | null | undefined; onSaved: (a: Availability | null, coach?: CoachView) => void;
  onReplan: () => void; busy: boolean; warnings: number;
}) {
  const empty: Availability = { weekly: Object.fromEntries([...Array(7)].map((_, i) => [String(i), null])), days: {} };
  const [draft, setDraft] = useState<Availability>(value ?? empty);
  const [mode, setMode] = useState<'week' | 'days'>('week');
  const todayIso = isoLocal(new Date());
  const [sel, setSel] = useState<string[]>([String(weekday(todayIso))]);
  const [custom, setCustom] = useState('');
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  useEffect(() => { setDraft(value ?? empty); }, [JSON.stringify(value)]);  // eslint-disable-line react-hooks/exhaustive-deps
  const next14 = useMemo(() => [...Array(14)].map((_, i) => { const d = new Date(); d.setDate(d.getDate() + i); return isoLocal(d); }), [todayIso]);
  const dirty = JSON.stringify(draft) !== JSON.stringify(value ?? empty);

  const pickMode = (m: 'week' | 'days') => { setMode(m); setSel(m === 'week' ? [String(weekday(todayIso))] : [todayIso]); setSaved(false); };
  const toggle = (k: string) => setSel((s) => (s.includes(k) ? s.filter((x) => x !== k) : [...s, k]));
  const apply = (v: number | null | 'default') => {
    setSaved(false); setErr(null);
    setDraft((d) => {
      const n: Availability = { weekly: { ...d.weekly }, days: { ...d.days } };
      for (const k of sel) {
        if (mode === 'week') n.weekly[k] = v === 'default' ? null : v;
        else if (v === 'default') delete n.days[k];
        else if (v === null) n.days[k] = 480;  // "libre" un día concreto: sin tope práctico
        else n.days[k] = v;
      }
      return n;
    });
  };
  const applyCustom = () => {
    const m = Math.round(Number(custom.replace(',', '.')));
    if (!custom.trim() || !Number.isFinite(m) || m < 0 || m > 480) { setErr('Pon entre 0 y 480 minutos.'); return; }
    apply(m); setCustom('');
  };
  const save = async () => {
    setSaving(true); setErr(null);
    try {
      const days: Record<string, number | null> = { ...draft.days };
      const r = await call<{ availability: Availability | null; coach?: CoachView }>('./api/settings/availability',
        { weekly: draft.weekly, days, replaceDays: true });
      onSaved(r.availability, r.coach); setSaved(true); refreshData();
    } catch (e) { setErr((e as Error).message); } finally { setSaving(false); }
  };
  const selValue = (() => {
    if (!sel.length) return undefined;
    const vals = sel.map((k) => (mode === 'week' ? draft.weekly[k] ?? null : (k in draft.days ? draft.days[k] : 'default')));
    return vals.every((v) => v === vals[0]) ? vals[0] : undefined;
  })();
  const quick = mode === 'days' ? [{ v: 'default' as const, label: 'Como siempre' }, ...QUICK.filter((q) => q.v !== null)] : QUICK;

  return (
    <Card data-new="availability" sx={{ ...CARD_SX }}>
      <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center', mb: 2 }}>
        <IconBubble color="#1A73E8"><ScheduleRounded /></IconBubble>
        <Box sx={{ minWidth: 0 }}>
          <Typography variant="subtitle1">Tu tiempo</Typography>
          <Typography variant="caption" color="text.secondary">Cuánto tienes cada día para entrenar. El coach encaja cada sesión en ese tiempo.</Typography>
        </Box>
      </Stack>
      <ToggleButtonGroup exclusive size="small" value={mode} onChange={(_, v) => v && pickMode(v)} sx={{ mb: 1.5,
        '& .MuiToggleButton-root': { borderRadius: '999px !important', px: 2, color: 'text.secondary', border: '1px solid', borderColor: 'divider' },
        '& .Mui-selected': { bgcolor: 'color-mix(in srgb, var(--mui-palette-primary-main) 16%, transparent) !important', color: 'primary.main' } }}>
        <ToggleButton value="week">Cada semana</ToggleButton>
        <ToggleButton value="days">Próximos días</ToggleButton>
      </ToggleButtonGroup>
      {mode === 'week' ? (
        <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(7, minmax(0, 1fr))', gap: 0.75 }}>
          {LETTERS.map((l, i) => (
            <Tooltip key={l} title={DAY_NAMES[i]}><Box sx={{ display: 'grid', minWidth: 0 }}>
              <Tile top={l} bottom={minLabel(draft.weekly[String(i)])} selected={sel.includes(String(i))} onClick={() => toggle(String(i))} />
            </Box></Tooltip>
          ))}
        </Box>
      ) : (
        <Box sx={{ display: 'flex', gap: 0.75, overflowX: 'auto', pb: 0.5, mx: -0.5, px: 0.5, scrollbarWidth: 'thin' }}>
          {next14.map((d) => (
            <Box key={d} sx={{ display: 'grid', flex: '0 0 64px' }}>
              <Tile top={d === todayIso ? 'hoy' : toDate(d).toLocaleDateString('es-ES', { weekday: 'short', day: 'numeric' }).replace('.', '')}
                bottom={minLabel(availFor(draft, d) ?? null)} marked={d in draft.days} selected={sel.includes(d)} onClick={() => toggle(d)} />
            </Box>
          ))}
        </Box>
      )}
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1.25, mb: 1 }}>
        {sel.length ? (mode === 'week' ? 'Toca un tiempo para los días marcados (puedes marcar varios).' : 'Cambia solo esas fechas; el punto marca los días que no son como siempre.')
          : 'Marca uno o varios días.'}
      </Typography>
      <Stack direction="row" sx={{ flexWrap: 'wrap', gap: 0.75, alignItems: 'center' }}>
        {quick.map((q) => (
          <Chip key={q.label} label={q.label} disabled={!sel.length} onClick={() => apply(q.v)} size="small"
            color={selValue !== undefined && selValue === q.v ? 'primary' : 'default'}
            variant={selValue !== undefined && selValue === q.v ? 'filled' : 'outlined'} sx={PILL_SX} />
        ))}
        <TextField size="small" placeholder="Otro" value={custom} disabled={!sel.length} onChange={(e) => setCustom(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') applyCustom(); }} onBlur={() => custom && applyCustom()}
          slotProps={{ htmlInput: { inputMode: 'numeric', 'aria-label': 'Otros minutos' }, input: { endAdornment: <InputAdornment position="end">min</InputAdornment> } }}
          sx={{ width: 108, '& .MuiInputBase-root': { borderRadius: 999, height: 32, fontSize: 13 } }} />
      </Stack>
      {err && <Alert severity="error" sx={{ borderRadius: '14px', mt: 1.5 }}>{err}</Alert>}
      <Stack direction="row" sx={{ mt: 2, gap: 1, flexWrap: 'wrap', alignItems: 'center' }}>
        <Button variant="contained" disableElevation disabled={!dirty || saving} onClick={save} sx={PILL_SX}
          startIcon={saving ? <CircularProgress size={16} color="inherit" /> : undefined}>{saving ? 'Guardando…' : 'Guardar'}</Button>
        {dirty && <Button onClick={() => { setDraft(value ?? empty); setErr(null); }} sx={PILL_SX}>Deshacer</Button>}
      </Stack>
      {(saved || warnings > 0) && !dirty && (
        <Alert severity={warnings > 0 ? 'warning' : 'success'} sx={{ borderRadius: '14px', mt: 2, '& .MuiAlert-message': { width: '100%' } }}>
          <Typography variant="body2" sx={{ mb: 1 }}>
            {warnings > 0 ? `${warnings === 1 ? 'Una sesión no cabe' : `${warnings} sesiones no caben`} en tu tiempo.` : 'Guardado.'}
            {' '}El plan se ajusta a tu tiempo el lunes; si quieres, el coach lo rehace ahora.
          </Typography>
          <Button size="small" variant="outlined" color="inherit" startIcon={<TuneRounded />} disabled={busy} onClick={onReplan} sx={PILL_SX}>
            Reajustar el plan con mi tiempo
          </Button>
        </Alert>
      )}
    </Card>
  );
}

// ------------------------------------------------------------------ "El tiempo que hará"
interface GeoResult { name: string; label: string; lat: number; lon: number }

export function WeatherCard({ value, lastRun, onSaved }: {
  value: WeatherBlock | null | undefined; lastRun?: { lat: number; lon: number; date: string } | null;
  onSaved: (w: WeatherBlock | null, coach?: CoachView) => void;
}) {
  const mode = useResolvedMode() as Mode;
  const loc = value?.location ?? null;
  const [editing, setEditing] = useState(!loc);
  const [q, setQ] = useState('');
  const [results, setResults] = useState<GeoResult[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { setEditing(!loc); }, [loc?.name]);  // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (q.trim().length < 2) { setResults(null); return; }
    const t = window.setTimeout(async () => {
      setSearching(true);
      try { setResults((await call<{ results: GeoResult[] }>(`./api/geo?q=${encodeURIComponent(q.trim())}`)).results); }
      catch (e) { setErr((e as Error).message); } finally { setSearching(false); }
    }, 350);
    return () => window.clearTimeout(t);
  }, [q]);
  const save = async (body: Partial<Place> & { clear?: boolean }) => {
    setBusy(true); setErr(null);
    try {
      const r = await call<{ weather: WeatherBlock | null; coach?: CoachView }>('./api/settings/location', body);
      onSaved(r.weather, r.coach); setQ(''); setResults(null); refreshData();
      if (!body.clear && !r.weather?.days?.length) setErr('Guardado, pero ahora no llega la previsión. Se volverá a intentar en la próxima actualización.');
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  const days = (value?.days ?? []).slice(0, 7);
  const first = days[0];
  const now = new Date();
  const fromHour = now.getHours() + (now.getMinutes() >= 30 ? 1 : 0);
  const todayWins = first && first.date === isoLocal(now) ? first.windows.filter((w) => Number(w.from.slice(0, 2)) >= fromHour) : [];

  return (
    <Card data-new="weather" sx={{ ...CARD_SX }}>
      <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center', mb: 2 }}>
        <IconBubble color={WX_COLOR.sun[mode]}><WbSunnyRounded /></IconBubble>
        <Box sx={{ minWidth: 0 }}>
          <Typography variant="subtitle1">El tiempo que hará</Typography>
          <Typography variant="caption" color="text.secondary">
            {loc ? 'El coach mira el calor, la lluvia y el viento para elegir día y hora.' : 'Elige tu ciudad y el coach tendrá en cuenta el calor, la lluvia y el viento.'}
          </Typography>
        </Box>
      </Stack>

      {loc && !editing && (
        <Stack direction="row" sx={{ alignItems: 'center', gap: 1, flexWrap: 'wrap', mb: 2 }}>
          <Chip icon={<LocationOnRounded />} label={loc.name} sx={{ ...PILL_SX, maxWidth: '100%' }} />
          <Button size="small" onClick={() => setEditing(true)} sx={PILL_SX}>Cambiar</Button>
          <Button size="small" color="inherit" disabled={busy} onClick={() => save({ clear: true })} sx={{ ...PILL_SX, color: 'text.secondary' }}>Quitar</Button>
        </Stack>
      )}
      {editing && (
        <Box sx={{ mb: 2 }}>
          <TextField fullWidth size="small" placeholder="Busca tu ciudad (p. ej. Valencia)" value={q} onChange={(e) => setQ(e.target.value)} autoComplete="off"
            slotProps={{ input: { startAdornment: <InputAdornment position="start"><SearchRounded fontSize="small" /></InputAdornment>,
              endAdornment: searching ? <InputAdornment position="end"><CircularProgress size={16} /></InputAdornment> : undefined } }}
            sx={{ '& .MuiInputBase-root': { borderRadius: 999 } }} />
          {results && (
            <Stack sx={{ mt: 1 }}>
              {results.length === 0 && <Typography variant="body2" color="text.secondary" sx={{ px: 1 }}>No encuentro esa ciudad.</Typography>}
              {results.map((r) => (
                <ButtonBase key={`${r.lat},${r.lon}`} disabled={busy} onClick={() => save({ name: r.name, lat: r.lat, lon: r.lon })}
                  sx={{ justifyContent: 'flex-start', textAlign: 'left', gap: 1, px: 1, py: 1, borderRadius: '12px', '&:hover': { bgcolor: 'action.hover' } }}>
                  <LocationOnRounded fontSize="small" sx={{ color: 'text.secondary', flexShrink: 0 }} />
                  <Typography variant="body2" sx={{ minWidth: 0, overflowWrap: 'anywhere' }}>{r.label}</Typography>
                </ButtonBase>
              ))}
            </Stack>
          )}
          <Stack direction="row" sx={{ gap: 1, flexWrap: 'wrap', mt: 1 }}>
            {lastRun && (
              <Button size="small" variant="outlined" startIcon={<LocationOnRounded />} disabled={busy} sx={PILL_SX}
                onClick={() => save({ name: 'Zona de tu última carrera', lat: lastRun.lat, lon: lastRun.lon })}>Usar la zona de mi última carrera</Button>
            )}
            {loc && <Button size="small" onClick={() => { setEditing(false); setQ(''); setResults(null); }} sx={PILL_SX}>Cancelar</Button>}
          </Stack>
        </Box>
      )}
      {err && <Alert severity="info" sx={{ borderRadius: '14px', mb: 2 }}>{err}</Alert>}

      {days.length > 0 && (
        <>
          <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(7, minmax(0, 1fr))', gap: 0.5, textAlign: 'center' }}>
            {days.map((d) => {
              const bad = d.flags.some((f) => ['storm', 'heavy_rain', 'wind', 'snow', 'heat'].includes(f));
              return (
                <Tooltip key={d.date} title={`${d.text}${d.windows[0] ? ` · mejor franja ${d.windows[0].from}-${d.windows[0].to}` : ''}`}>
                  <Box sx={{ py: 1, borderRadius: '12px', minWidth: 0, bgcolor: bad ? (t) => alpha(t.palette.warning.main, 0.08) : 'transparent' }}>
                    <Typography variant="caption" sx={{ display: 'block', color: 'text.secondary', fontWeight: 600, textTransform: 'capitalize', lineHeight: 1.2 }}>
                      {d.date === isoLocal(new Date()) ? 'hoy' : toDate(d.date).toLocaleDateString('es-ES', { weekday: 'short' }).replace('.', '')}
                    </Typography>
                    <Box sx={{ my: 0.5 }}><WeatherIcon code={d.code} size={22} /></Box>
                    <Typography sx={{ fontSize: 13, fontWeight: 600, lineHeight: 1.2 }}>{d.tmax ?? '–'}°</Typography>
                    <Typography sx={{ fontSize: 12, color: 'text.secondary', lineHeight: 1.2 }}>{d.tmin ?? '–'}°</Typography>
                    <Typography sx={{ fontSize: 11, color: (d.rainProb ?? 0) >= 50 ? WX_COLOR.rain[mode] : 'text.secondary', mt: 0.25, lineHeight: 1.2 }}>
                      {d.rainProb != null ? `${d.rainProb} %` : ''}
                    </Typography>
                  </Box>
                </Tooltip>
              );
            })}
          </Box>
          {todayWins.length > 0 && (
            <Typography variant="body2" color="text.secondary" sx={{ mt: 1.5 }}>
              Hoy, la mejor franja para correr: <b>{todayWins[0].from}-{todayWins[0].to}</b>
              {todayWins[0].temp != null ? ` (${todayWins[0].temp} °C)` : ''}{todayWins[1] ? ` o ${todayWins[1].from}-${todayWins[1].to}` : ''}.
            </Typography>
          )}
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
            Previsión de Open-Meteo{value?.fetchedAt ? ` · actualizada a las ${value.fetchedAt.slice(11, 16)}` : ''}. Si cambia a mitad de semana, el consejo del día te avisa.
          </Typography>
        </>
      )}
    </Card>
  );
}
