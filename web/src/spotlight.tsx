// Foco de "novedad": baja hasta el elemento marcado con data-new="<clave>", oscurece el resto y lo resalta con un
// anillo que late y una burbuja que explica qué es. Se lanza con spotlight(...) y se cierra tocando en cualquier sitio.
import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Typography from '@mui/material/Typography';

export interface SpotlightReq { target: string; title: string; body?: string }

export const spotlight = (req: SpotlightReq) => window.dispatchEvent(new CustomEvent<SpotlightReq>('gs-spotlight', { detail: req }));

const PAD = 8;

export function Spotlight() {
  const [req, setReq] = useState<SpotlightReq | null>(null);
  const [rect, setRect] = useState<{ top: number; left: number; width: number; height: number } | null>(null);
  const elRef = useRef<Element | null>(null);

  useEffect(() => {
    const on = (e: Event) => { elRef.current = null; setRect(null); setReq((e as CustomEvent<SpotlightReq>).detail); };
    window.addEventListener('gs-spotlight', on);
    return () => window.removeEventListener('gs-spotlight', on);
  }, []);

  useEffect(() => {
    if (!req) return;
    const t0 = Date.now();
    let raf = 0;
    let last = '';
    const tick = () => {
      if (!elRef.current) {
        const el = document.querySelector(`[data-new="${req.target}"]`);
        if (el) {
          elRef.current = el;
          // la barra flotante del móvil tapa el final de la pantalla: se centra un poco más arriba
          const r = el.getBoundingClientRect();
          const y = window.scrollY + r.top - Math.max(80, (window.innerHeight - Math.min(r.height, window.innerHeight * 0.6)) / 2 - 40);
          window.scrollTo({ top: Math.max(0, y), behavior: 'smooth' });
        } else if (Date.now() - t0 > 4000) { setReq(null); return; }  // la página no tiene ese elemento
      }
      if (elRef.current) {
        const r = elRef.current.getBoundingClientRect();
        const key = `${r.top}|${r.left}|${r.width}|${r.height}`;
        if (key !== last) { last = key; setRect({ top: r.top, left: r.left, width: r.width, height: r.height }); }
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    const close = (e: KeyboardEvent) => e.key === 'Escape' && setReq(null);
    window.addEventListener('keydown', close);
    return () => { cancelAnimationFrame(raf); window.removeEventListener('keydown', close); };
  }, [req]);

  if (!req || !rect) return null;
  const vw = window.innerWidth, vh = window.innerHeight;
  const box = { top: rect.top - PAD, left: Math.max(4, rect.left - PAD), width: Math.min(rect.width + PAD * 2, vw - 8), height: rect.height + PAD * 2 };
  const below = box.top + box.height + 190 < vh || box.top < 200;
  const tipW = Math.min(340, vw - 32);
  const tipLeft = Math.min(Math.max(16, box.left + box.width / 2 - tipW / 2), vw - tipW - 16);
  const tipTop = below ? Math.min(box.top + box.height + 14, vh - 180) : undefined;
  const tipBottom = below ? undefined : Math.min(vh - box.top + 14, vh - 120);

  return createPortal(
    <Box onClick={() => setReq(null)} role="dialog" aria-label={`Novedad: ${req.title}`}
      sx={{ position: 'fixed', inset: 0, zIndex: 1600, cursor: 'pointer', animation: 'spIn .25s ease both',
        '@keyframes spIn': { from: { opacity: 0 }, to: { opacity: 1 } },
        '@keyframes spPulse': { '0%': { transform: 'scale(1)', opacity: 0.9 }, '100%': { transform: 'scale(1.06)', opacity: 0 } },
        '@media (prefers-reduced-motion: reduce)': { animation: 'none', '& *': { animation: 'none !important' } } }}>
      {/* hueco iluminado: la sombra enorme oscurece todo lo demás */}
      <Box sx={{ position: 'fixed', ...box, borderRadius: '24px', boxShadow: '0 0 0 200vmax rgba(10,12,20,.55)',
        outline: '3px solid', outlineColor: 'primary.main', transition: 'all .2s ease', pointerEvents: 'none' }} />
      <Box sx={{ position: 'fixed', ...box, borderRadius: '24px', border: '3px solid', borderColor: 'primary.main', pointerEvents: 'none',
        animation: 'spPulse 1.4s ease-out infinite' }} />
      {/* burbuja */}
      <Box onClick={(e) => e.stopPropagation()}
        sx={{ position: 'fixed', top: tipTop, bottom: tipBottom, left: tipLeft, width: tipW, p: 2, borderRadius: '20px', cursor: 'default',
          bgcolor: 'background.paper', color: 'text.primary', boxShadow: '0 12px 40px rgba(0,0,0,.35)' }}>
        <Typography variant="overline" sx={{ color: 'primary.main', fontWeight: 700, letterSpacing: '0.1em', lineHeight: 1.6 }}>Novedad</Typography>
        <Typography sx={{ fontWeight: 600, fontSize: 17, lineHeight: 1.3 }}>{req.title}</Typography>
        {req.body && <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>{req.body}</Typography>}
        <Box sx={{ textAlign: 'right', mt: 1.25 }}>
          <Button variant="contained" disableElevation size="small" onClick={() => setReq(null)} sx={{ borderRadius: 999, px: 2.5 }}>Entendido</Button>
        </Box>
      </Box>
    </Box>,
    document.body,
  );
}
