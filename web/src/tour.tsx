// Guía de bienvenida: 4 pantallas que se enseñan UNA vez a quien acaba de entrar (cuenta de menos de 14 días).
// Explica dónde está cada cosa; las novedades de versiones (whatsnew.tsx) son para quien ya usaba la app.
import { useEffect, useState, type ReactNode } from 'react';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import Typography from '@mui/material/Typography';
import HomeRounded from '@mui/icons-material/HomeRounded';
import FavoriteRounded from '@mui/icons-material/FavoriteRounded';
import DirectionsRunRounded from '@mui/icons-material/DirectionsRunRounded';
import AutoAwesomeRounded from '@mui/icons-material/AutoAwesomeRounded';
import type { Me } from './account';
import { haptic } from './haptics';

const KEY = 'runch-tour-v1';
const BRAND = '#D4542F';

const SLIDES: { icon: ReactNode; color: string; title: string; body: ReactNode }[] = [
  { icon: <HomeRounded />, color: BRAND, title: 'Hoy: lo importante',
    body: <>Cada mañana, de un vistazo: <b>cómo llegas</b>, tu sesión del plan, pasos, sueño, energía y tu <b>último entreno</b> comentado por la IA.</> },
  { icon: <FavoriteRounded />, color: '#D93025', title: 'Lo importante, arriba',
    body: <>Arriba de cada página verás 2-3 datos clave. Si la nota sale en <b>terracota</b>, mírala primero; en <b>verde</b>, vas bien.</> },
  { icon: <DirectionsRunRounded />, color: '#E8710A', title: 'Tu plan se ajusta solo',
    body: <>En <b>Entreno → Plan</b> está tu semana. El coach la reajusta cada lunes según lo que hagas y cómo te encuentres.</> },
  { icon: <AutoAwesomeRounded />, color: BRAND, title: 'Pregunta lo que quieras',
    body: <>El botón <b>✦</b> abre el coach: «¿por qué duermo peor?», «¿hago la tirada mañana?». Responde con tus datos.</> },
];

export function WelcomeTour({ me }: { me: Me | null }) {
  const [open, setOpen] = useState(false);
  const [i, setI] = useState(0);
  useEffect(() => {
    if (!me?.hasData || !me.since) return;
    if (Date.now() / 1000 - me.since > 14 * 86400) return;  // solo cuentas nuevas
    try { if (localStorage.getItem(KEY)) return; } catch { /* sin almacenamiento: se enseña */ }
    const t = window.setTimeout(() => setOpen(true), 1200);
    return () => window.clearTimeout(t);
  }, [me?.hasData, me?.since]);
  const close = () => { setOpen(false); try { localStorage.setItem(KEY, '1'); } catch { /* nada */ } };
  const s = SLIDES[i];
  const last = i === SLIDES.length - 1;
  return (
    <Dialog open={open} onClose={close} fullWidth maxWidth="xs"
      slotProps={{ paper: { sx: { borderRadius: '28px', m: 2, width: 'calc(100% - 32px)' } } }}>
      <Box sx={{ p: 3, pt: 4, textAlign: 'center' }}>
        <Box sx={{ width: 72, height: 72, mx: 'auto', borderRadius: '50%', display: 'grid', placeItems: 'center', color: '#FFFFFF',
          bgcolor: s.color, '& svg': { fontSize: 36 }, boxShadow: `0 10px 30px color-mix(in srgb, ${s.color} 35%, transparent)` }}>{s.icon}</Box>
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 2.5, fontWeight: 600 }}>
          {i === 0 ? 'BIENVENIDA A RUNCH' : `${i + 1} DE ${SLIDES.length}`}
        </Typography>
        <Typography sx={{ fontSize: 24, fontWeight: 600, mt: 0.5 }}>{s.title}</Typography>
        <Typography color="text.secondary" sx={{ mt: 1.5, minHeight: 96 }}>{s.body}</Typography>
        <Box sx={{ display: 'flex', justifyContent: 'center', gap: 0.75, mt: 2 }}>
          {SLIDES.map((_, k) => <Box key={k} sx={{ width: k === i ? 22 : 8, height: 8, borderRadius: 4, transition: 'all .3s',
            bgcolor: k === i ? BRAND : 'action.selected' }} />)}
        </Box>
        <Box sx={{ display: 'flex', gap: 1, mt: 3 }}>
          {!last && <Button onClick={close} sx={{ borderRadius: 999, color: 'text.secondary', flex: 1 }}>Saltar</Button>}
          <Button variant="contained" disableElevation onClick={() => { haptic('tap'); if (last) close(); else setI(i + 1); }}
            sx={{ borderRadius: 999, flex: 2, py: 1.25, bgcolor: BRAND, color: '#FFFFFF', '&:hover': { bgcolor: '#B9441F' } }}>
            {last ? 'Empezar' : 'Siguiente'}
          </Button>
        </Box>
      </Box>
    </Dialog>
  );
}
