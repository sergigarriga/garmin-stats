import { useCallback, useEffect, useRef, useState } from 'react';
import Box from '@mui/material/Box';
import CircularProgress from '@mui/material/CircularProgress';
import RefreshRounded from '@mui/icons-material/RefreshRounded';
import { isoLocal, type GarminData } from './data';

type Status = { status?: 'running' | 'done' | 'error'; at?: number; finished?: number; token?: string; recent?: boolean; already?: boolean; error?: string };

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

async function call(method: 'GET' | 'POST'): Promise<Status> {
  const r = await fetch('./api/sync', { method, credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: method === 'POST' ? '{}' : undefined });
  if (r.status === 401) { window.location.href = './auth/login'; throw new Error('login'); }
  if (!r.ok) throw new Error(String(r.status));
  return r.json();
}

/** Qué ha llegado de nuevo, en una frase. */
function summary(before: GarminData, after: GarminData): string {
  const known = new Set(before.activities.map((a) => a.id));
  const fresh = after.activities.filter((a) => !known.has(a.id));
  const today = isoLocal(new Date());
  const hadSleep = before.days.some((d) => d.d === today && d.sleepH != null);
  const hasSleep = after.days.find((d) => d.d === today && d.sleepH != null);
  const parts: string[] = [];
  if (fresh.length === 1) {
    const a = fresh[0];
    parts.push(`1 actividad nueva (${a.name ?? a.type}${a.km ? ` · ${a.km.toFixed(1).replace('.', ',')} km` : ''})`);
  } else if (fresh.length > 1) parts.push(`${fresh.length} actividades nuevas`);
  if (!hadSleep && hasSleep) parts.push('tu sueño de anoche');
  if (parts.length) return `Actualizado con Garmin: ${parts.join(' y ')}.`;
  return 'Al día con Garmin: no hay nada nuevo. Si acabas de entrenar, sincroniza antes el reloj con la app Garmin Connect.';
}

/** Botón "actualizar": pide a AWS que se conecte a Garmin ahora y espera a los datos nuevos (~30 s). */
export function useManualSync(data: GarminData | undefined, check: () => Promise<GarminData | undefined>, onDone: (msg: string) => void) {
  const [syncing, setSyncing] = useState(false);
  const busy = useRef(false);
  const latest = useRef(data);
  latest.current = data;

  const run = useCallback(async () => {
    if (busy.current || !latest.current) return;
    busy.current = true;
    setSyncing(true);
    const before = latest.current;
    try {
      const st = await call('POST');
      let end: Status = st;
      if (st.status === 'running') {
        const deadline = Date.now() + 3 * 60_000;
        for (;;) {
          await sleep(3000);
          end = await call('GET');
          if (end.status !== 'running' || Date.now() > deadline) break;
        }
      }
      if (end.status === 'error') { onDone('Garmin no ha respondido. Vuelve a probar en unos minutos.'); return; }
      if (end.status === 'running') { onDone('Garmin va lento: los datos llegarán en un momento.'); return; }
      const after = (await check()) ?? latest.current;
      onDone(summary(before, after));
    } catch (e) {
      if ((e as Error).message !== 'login') onDone('No se ha podido conectar. Comprueba tu conexión.');
    } finally {
      busy.current = false;
      setSyncing(false);
    }
  }, [check, onDone]);

  return { syncing, sync: run };
}

/** Deslizar hacia abajo desde arriba del todo para actualizar (móvil). */
export function PullToRefresh({ onRefresh, busy }: { onRefresh: () => void; busy: boolean }) {
  const [pull, setPull] = useState(0);
  const cb = useRef(onRefresh);
  cb.current = onRefresh;

  useEffect(() => {
    let start: { x: number; y: number } | null = null;
    let dist = 0;
    // No se activa con un diálogo o el chat abiertos (MUI bloquea el scroll del body) ni a media página.
    const blocked = () => window.scrollY > 0 || document.body.style.overflow === 'hidden';
    const set = (v: number) => { dist = v; setPull(v); };
    const onStart = (e: TouchEvent) => {
      start = e.touches.length === 1 && !blocked() ? { x: e.touches[0].clientX, y: e.touches[0].clientY } : null;
    };
    const onMove = (e: TouchEvent) => {
      if (!start) return;
      const dy = e.touches[0].clientY - start.y;
      const dx = Math.abs(e.touches[0].clientX - start.x);
      if (blocked() || dy <= 0 || dx > dy) { if (dist) set(0); return; }
      set(Math.min(120, dy * 0.5));
    };
    const onEnd = () => {
      if (dist >= 70) cb.current();
      start = null;
      if (dist) set(0);
    };
    window.addEventListener('touchstart', onStart, { passive: true });
    window.addEventListener('touchmove', onMove, { passive: true });
    window.addEventListener('touchend', onEnd, { passive: true });
    window.addEventListener('touchcancel', onEnd, { passive: true });
    return () => {
      window.removeEventListener('touchstart', onStart);
      window.removeEventListener('touchmove', onMove);
      window.removeEventListener('touchend', onEnd);
      window.removeEventListener('touchcancel', onEnd);
    };
  }, []);

  if (!pull && !busy) return null;
  const y = busy && !pull ? 70 : pull;
  const ready = pull >= 70;
  return (
    <Box aria-hidden sx={{ position: 'fixed', left: '50%', zIndex: 1200, pointerEvents: 'none',
      top: 'calc(env(safe-area-inset-top) + 8px)', transform: `translate(-50%, ${y}px)`,
      transition: pull ? 'none' : 'transform 200ms ease',
      width: 40, height: 40, borderRadius: '50%', display: 'grid', placeItems: 'center',
      bgcolor: 'background.paper', boxShadow: '0 2px 10px rgba(0,0,0,.18)', color: ready || busy ? 'primary.main' : 'text.secondary' }}>
      {busy && !pull
        ? <CircularProgress size={20} thickness={5} />
        : <RefreshRounded sx={{ fontSize: 22, transform: `rotate(${pull * 3}deg)`, opacity: Math.min(1, 0.3 + pull / 70) }} />}
    </Box>
  );
}
