// Mensaje de bienvenida con IA al abrir la app: cómo vas hoy, lo que has hecho y una valoración.
// Una vez por franja del día (mañana / tarde / noche) y cuando hay algo nuevo; el menú lo vuelve a abrir.
import { useCallback, useEffect, useState } from 'react';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import CheckCircleRounded from '@mui/icons-material/CheckCircleRounded';
import ErrorOutlineRounded from '@mui/icons-material/ErrorOutlineRounded';
import WbSunnyRounded from '@mui/icons-material/WbSunnyRounded';
import { call } from './account';
import { useCat } from './theme';
import { IconBubble } from './ui';

export interface BriefText { tone: 'positive' | 'neutral' | 'attention'; title: string; body: string; next_step: string; slot: 'morning' | 'afternoon' | 'evening'; at?: string }
interface BriefResp { brief: BriefText | null; key?: string | null; cached?: boolean }

const STORE = 'gs-brief';
const GREETING = { morning: 'Buenos días', afternoon: 'Buenas tardes', evening: 'Buenas noches' } as const;
const seen = (): { key?: string; at?: number } => { try { return JSON.parse(localStorage.getItem(STORE) ?? '{}'); } catch { return {}; } };
const markSeen = (key: string | null | undefined) => { try { localStorage.setItem(STORE, JSON.stringify({ key, at: Date.now() })); } catch { /* sin almacenamiento */ } };

export function DailyBrief({ name, ready, go }: { name?: string; ready: boolean; go: (page: string) => void }) {
  const cat = useCat();
  const [brief, setBrief] = useState<BriefResp | null>(null);
  const [open, setOpen] = useState(false);

  // Al abrir la app: se pide (la API devuelve el de esta franja o lo genera) y se enseña si es nuevo para este móvil.
  useEffect(() => {
    if (!ready) return;
    let dead = false;
    const s = seen();
    if (s.at && Date.now() - s.at < 45 * 60_000) return; // acaba de verlo: no se repite al volver enseguida
    call<BriefResp>('./api/brief', {}).then(async (r) => {
      if (dead || !r.brief) return;
      setBrief(r);
      if (r.key && r.key === s.key) return;
      // Si hay otro diálogo abierto (novedades, tour…) se espera a que se cierre.
      for (let i = 0; i < 20 && document.documentElement.dataset.modal === '1'; i++) await new Promise((ok) => setTimeout(ok, 1500));
      if (!dead) { setOpen(true); markSeen(r.key); }
    }).catch(() => { /* sin mensaje esta vez */ });
    return () => { dead = true; };
  }, [ready]);

  // Desde el menú: se vuelve a abrir (si aún no se ha pedido, se pide).
  const reopen = useCallback(async () => {
    if (brief?.brief) { setOpen(true); return; }
    try { const r = await call<BriefResp>('./api/brief', {}); if (r.brief) { setBrief(r); setOpen(true); markSeen(r.key); } } catch { /* sin mensaje */ }
  }, [brief]);
  useEffect(() => { window.addEventListener('open-brief', reopen); return () => window.removeEventListener('open-brief', reopen); }, [reopen]);

  const b = brief?.brief;
  if (!b) return null;
  const color = b.tone === 'attention' ? cat('stress') : b.tone === 'positive' ? cat('activity') : cat('energy');
  const first = (name ?? '').trim().split(/\s+/)[0];
  const Icon = b.tone === 'attention' ? ErrorOutlineRounded : b.tone === 'positive' ? CheckCircleRounded : WbSunnyRounded;
  return (
    <Dialog open={open} onClose={() => setOpen(false)} slotProps={{ paper: { sx: { borderRadius: '28px', m: 2, width: 'calc(100% - 32px)', maxWidth: 460, p: 3 } } }}>
      <Stack spacing={2}>
        <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center' }}>
          <IconBubble color={color} size={44}><Icon /></IconBubble>
          <Box>
            <Typography variant="caption" color="text.secondary">{GREETING[b.slot]}{first ? `, ${first}` : ''}</Typography>
            <Typography variant="h6" sx={{ lineHeight: 1.25, fontWeight: 600 }}>{b.title}</Typography>
          </Box>
        </Stack>
        <Typography sx={{ lineHeight: 1.55 }}>{b.body}</Typography>
        {b.next_step && (
          <Box sx={{ p: 1.5, borderRadius: '16px', bgcolor: `color-mix(in srgb, ${color} 12%, transparent)` }}>
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', fontWeight: 500 }}>Para lo que queda de día</Typography>
            <Typography variant="body2">{b.next_step}</Typography>
          </Box>
        )}
        <Stack direction="row" spacing={1} sx={{ justifyContent: 'flex-end' }}>
          <Button onClick={() => setOpen(false)} sx={{ borderRadius: 999 }}>Cerrar</Button>
          <Button variant="contained" disableElevation onClick={() => { setOpen(false); go('dia'); }} sx={{ borderRadius: 999 }}>Ver mi día</Button>
        </Stack>
        <Typography variant="caption" color="text.disabled" sx={{ textAlign: 'center' }}>Resumen escrito por IA con tus datos. No es consejo médico.</Typography>
      </Stack>
    </Dialog>
  );
}
