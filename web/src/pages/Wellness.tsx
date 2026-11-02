import { useEffect, useState } from 'react';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import Chip from '@mui/material/Chip';
import CircularProgress from '@mui/material/CircularProgress';
import Dialog from '@mui/material/Dialog';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import ToggleButton from '@mui/material/ToggleButton';
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup';
import Typography from '@mui/material/Typography';
import SentimentVeryDissatisfiedRounded from '@mui/icons-material/SentimentVeryDissatisfiedRounded';
import SentimentDissatisfiedRounded from '@mui/icons-material/SentimentDissatisfiedRounded';
import SentimentNeutralRounded from '@mui/icons-material/SentimentNeutralRounded';
import SentimentSatisfiedRounded from '@mui/icons-material/SentimentSatisfiedRounded';
import SentimentVerySatisfiedRounded from '@mui/icons-material/SentimentVerySatisfiedRounded';
import HealingRounded from '@mui/icons-material/HealingRounded';
import AddRounded from '@mui/icons-material/AddRounded';
import EditNoteRounded from '@mui/icons-material/EditNoteRounded';
import { call } from '../account';
import { isoLocal, refreshData, toDate, type GarminData, type Injury, type Wellness } from '../data';
import { dateShort } from '../format';
import { useCat } from '../theme';
import { CARD_SX, IconBubble } from '../ui';

const online = window.location.protocol.startsWith('http');
const MOOD = [
  { v: 1, label: 'Muy mal', icon: <SentimentVeryDissatisfiedRounded /> },
  { v: 2, label: 'Mal', icon: <SentimentDissatisfiedRounded /> },
  { v: 3, label: 'Normal', icon: <SentimentNeutralRounded /> },
  { v: 4, label: 'Bien', icon: <SentimentSatisfiedRounded /> },
  { v: 5, label: 'Genial', icon: <SentimentVerySatisfiedRounded /> },
];
const SORE = ['Nada', 'Leves', 'Moderadas', 'Fuertes', 'Muy fuertes'];
export const SEVERITY = ['Leve', 'Molesta', 'Moderada', 'Fuerte', 'Muy fuerte'];
const sevColor = (n: number) => (n >= 4 ? 'error' : n >= 3 ? 'warning' : 'default') as 'error' | 'warning' | 'default';

const pillGroup = {
  gap: 0.75, flexWrap: 'wrap',
  '& .MuiToggleButton-root': { borderRadius: '999px !important', border: '1px solid !important', borderColor: 'var(--mui-palette-divider) !important', px: 1.5, py: 0.5, textTransform: 'none', gap: 0.5 },
  '& .Mui-selected': { bgcolor: 'color-mix(in srgb, var(--mui-palette-primary-main) 16%, transparent) !important', color: 'primary.main', borderColor: 'var(--mui-palette-primary-main) !important' },
} as const;

/** Tarjeta de la portada: cómo te encuentras hoy (ánimo y agujetas) y tus molestias. El coach lo tiene en cuenta. */
export function CheckIn({ data }: { data: GarminData }) {
  const cat = useCat();
  const w: Wellness = data.wellness ?? { recent: [], injuries: [] };
  const todayIso = isoLocal(new Date());
  const saved = w.today?.d === todayIso ? w.today : null;
  const [mood, setMood] = useState<number | null>(saved?.mood ?? null);
  const [sore, setSore] = useState<number | null>(saved?.soreness ?? null);
  const [note, setNote] = useState(saved?.note ?? '');
  const [showNote, setShowNote] = useState(!!saved?.note);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [injDialog, setInjDialog] = useState<Injury | 'new' | null>(null);
  useEffect(() => { setMood(saved?.mood ?? null); setSore(saved?.soreness ?? null); setNote(saved?.note ?? ''); },
    [saved?.mood, saved?.soreness, saved?.note]);  // eslint-disable-line react-hooks/exhaustive-deps

  const save = async (m: number | null, s: number | null, n: string) => {
    setBusy(true); setMsg(null);
    try {
      await call('./api/wellness', { mood: m, soreness: s, note: n });
      setMsg({ ok: true, text: 'Guardado. Tu coach lo tendrá en cuenta.' });
      refreshData();
    } catch (e) { setMsg({ ok: false, text: (e as Error).message }); } finally { setBusy(false); }
  };
  const active = w.injuries.filter((i) => !i.end);
  const healed = w.injuries.filter((i) => i.end);
  const color = cat('recovery');

  return (
    <Card data-new="checkin" sx={{ ...CARD_SX, mb: 2 }}>
      <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center', mb: 2 }}>
        <IconBubble color={color}><HealingRounded /></IconBubble>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography variant="subtitle1">¿Cómo te encuentras hoy?</Typography>
          <Typography variant="caption" color="text.secondary">Tu coach lo usa para el consejo del día y para reajustar el plan</Typography>
        </Box>
        {busy && <CircularProgress size={18} />}
      </Stack>
      {!online && <Alert severity="info" sx={{ borderRadius: '14px', mb: 2 }}>Para guardarlo abre la web desde internet.</Alert>}
      <Stack spacing={1.75}>
        <Box>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 0.75 }}>Ánimo</Typography>
          <ToggleButtonGroup exclusive size="small" value={mood} disabled={!online || busy} sx={pillGroup}
            onChange={(_, v) => { const m = v ?? null; setMood(m); save(m, sore, note); }}>
            {MOOD.map((o) => (
              <ToggleButton key={o.v} value={o.v} aria-label={o.label}>
                {o.icon}<Box component="span" sx={{ display: { xs: mood === o.v ? 'inline' : 'none', sm: 'inline' } }}>{o.label}</Box>
              </ToggleButton>
            ))}
          </ToggleButtonGroup>
        </Box>
        <Box>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 0.75 }}>Agujetas o cansancio muscular</Typography>
          <ToggleButtonGroup exclusive size="small" value={sore} disabled={!online || busy} sx={pillGroup}
            onChange={(_, v) => { const s = v ?? null; setSore(s); save(mood, s, note); }}>
            {SORE.map((l, i) => <ToggleButton key={l} value={i + 1}>{l}</ToggleButton>)}
          </ToggleButtonGroup>
        </Box>
        {showNote ? (
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} sx={{ alignItems: { sm: 'center' } }}>
            <TextField size="small" fullWidth label="Nota (opcional)" placeholder="Dormí mal, mucho trabajo, piernas cargadas…"
              value={note} onChange={(e) => setNote(e.target.value)} slotProps={{ htmlInput: { maxLength: 300 } }} />
            <Button variant="outlined" disabled={!online || busy} onClick={() => save(mood, sore, note)} sx={{ borderRadius: 999, flexShrink: 0 }}>Guardar nota</Button>
          </Stack>
        ) : (
          <Button size="small" startIcon={<EditNoteRounded />} onClick={() => setShowNote(true)} sx={{ alignSelf: 'flex-start', borderRadius: 999, ml: -0.5 }}>Añadir una nota</Button>
        )}
        {msg && <Alert severity={msg.ok ? 'success' : 'error'} onClose={() => setMsg(null)} sx={{ borderRadius: '14px' }}>{msg.text}</Alert>}
        <Box sx={{ pt: 1.5, borderTop: 1, borderColor: 'divider' }}>
          <Stack direction="row" sx={{ alignItems: 'center', justifyContent: 'space-between', mb: active.length || healed.length ? 1 : 0, gap: 1 }}>
            <Typography variant="body2" color="text.secondary">Molestias y lesiones</Typography>
            <Button size="small" startIcon={<AddRounded />} disabled={!online} onClick={() => setInjDialog('new')} sx={{ borderRadius: 999 }}>Añadir</Button>
          </Stack>
          <Stack direction="row" sx={{ flexWrap: 'wrap', gap: 1 }}>
            {active.map((i) => (
              <Chip key={i.id} color={sevColor(i.severity)} variant={i.severity >= 3 ? 'filled' : 'outlined'} onClick={() => setInjDialog(i)}
                label={`${i.area} · ${SEVERITY[i.severity - 1].toLowerCase()} · desde el ${dateShort(toDate(i.start))}`} />
            ))}
            {healed.map((i) => (
              <Chip key={i.id} variant="outlined" onClick={() => setInjDialog(i)} sx={{ color: 'text.secondary' }}
                label={`${i.area} · recuperada el ${dateShort(toDate(i.end!))}`} />
            ))}
          </Stack>
        </Box>
      </Stack>
      <InjuryDialog value={injDialog} onClose={() => setInjDialog(null)} />
    </Card>
  );
}

function InjuryDialog({ value, onClose }: { value: Injury | 'new' | null; onClose: () => void }) {
  const isNew = value === 'new';
  const inj = value && value !== 'new' ? value : null;
  const [area, setArea] = useState('');
  const [sev, setSev] = useState(2);
  const [start, setStart] = useState(isoLocal(new Date()));
  const [notes, setNotes] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    setErr(null);
    setArea(inj?.area ?? ''); setSev(inj?.severity ?? 2); setStart(inj?.start ?? isoLocal(new Date())); setNotes(inj?.notes ?? '');
  }, [value]);  // eslint-disable-line react-hooks/exhaustive-deps
  const act = async (body: Record<string, unknown>) => {
    setBusy(true); setErr(null);
    try { await call('./api/injury', body); refreshData(); onClose(); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  return (
    <Dialog open={!!value} onClose={onClose} fullWidth maxWidth="xs" slotProps={{ paper: { sx: { borderRadius: '28px', m: 2, width: 'calc(100% - 32px)' } } }}>
      <DialogTitle sx={{ pb: 1 }}>{isNew ? 'Nueva molestia o lesión' : inj?.area}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          {isNew && <TextField label="Zona" placeholder="Rodilla derecha, gemelo, espalda baja…" value={area} onChange={(e) => setArea(e.target.value)}
            slotProps={{ htmlInput: { maxLength: 60 } }} autoFocus />}
          <Box>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 0.75 }}>Intensidad</Typography>
            <ToggleButtonGroup exclusive size="small" value={sev} onChange={(_, v) => v && setSev(v)} sx={pillGroup}>
              {SEVERITY.map((l, i) => <ToggleButton key={l} value={i + 1}>{l}</ToggleButton>)}
            </ToggleButtonGroup>
          </Box>
          {isNew && <TextField label="Desde" type="date" value={start} onChange={(e) => setStart(e.target.value)} slotProps={{ inputLabel: { shrink: true } }} />}
          <TextField label="Notas (opcional)" placeholder="Cuándo duele, qué la empeora…" value={notes} onChange={(e) => setNotes(e.target.value)}
            multiline minRows={2} slotProps={{ htmlInput: { maxLength: 500 } }} />
          {inj?.end && <Alert severity="success" sx={{ borderRadius: '14px' }}>Recuperada el {dateShort(toDate(inj.end))}.</Alert>}
          {err && <Alert severity="error" sx={{ borderRadius: '14px' }}>{err}</Alert>}
          <Stack direction="row" sx={{ flexWrap: 'wrap', gap: 1, justifyContent: 'flex-end' }}>
            {inj && <Button color="error" disabled={busy} onClick={() => act({ action: 'delete', id: inj.id })} sx={{ borderRadius: 999, mr: 'auto' }}>Borrar</Button>}
            {inj && !inj.end && <Button variant="outlined" color="success" disabled={busy} onClick={() => act({ action: 'close', id: inj.id })} sx={{ borderRadius: 999 }}>Ya estoy bien</Button>}
            {inj?.end && <Button variant="outlined" disabled={busy} onClick={() => act({ action: 'reopen', id: inj.id })} sx={{ borderRadius: 999 }}>Ha vuelto</Button>}
            <Button variant="contained" disableElevation disabled={busy || (isNew && !area.trim())} sx={{ borderRadius: 999 }}
              onClick={() => act(isNew ? { action: 'add', area, severity: sev, start, notes } : { action: 'update', id: inj!.id, severity: sev, notes })}>
              {busy ? 'Guardando…' : 'Guardar'}
            </Button>
          </Stack>
        </Stack>
      </DialogContent>
    </Dialog>
  );
}
