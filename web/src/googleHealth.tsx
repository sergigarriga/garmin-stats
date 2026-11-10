// Google Health: la alternativa a Garmin para quien no tiene reloj Garmin (Apple Watch, Pixel, Fitbit, Oura...).
// Los datos llegan a Google Health desde Apple Salud (iPhone) o Health Connect (Android); la app los lee de ahí.
//
// Flujo: el botón lleva la página entera a ./api/google/connect → Google pide permiso → vuelve a
// /?google=ok o /?google=error&reason=… (con #página detrás). useGoogleReturn() lee eso una vez y limpia la URL.
import { useEffect, useState } from 'react';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import Checkbox from '@mui/material/Checkbox';
import Dialog from '@mui/material/Dialog';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import FormControlLabel from '@mui/material/FormControlLabel';
import IconButton from '@mui/material/IconButton';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import CloseRounded from '@mui/icons-material/CloseRounded';
import FavoriteRounded from '@mui/icons-material/FavoriteRounded';
import OpenInNewRounded from '@mui/icons-material/OpenInNewRounded';
import { call, type Me } from './account';
import { relative } from './format';
import { BRAND, BRAND_DARK } from './brand/colors';

const BTN = { borderRadius: 999, bgcolor: BRAND, color: '#FFFFFF', '&:hover': { bgcolor: BRAND_DARK } } as const;
const DIALOG_SX = { paper: { sx: { borderRadius: '28px', m: 2, width: 'calc(100% - 32px)', maxWidth: 520 } } };

/** Dirección que empieza la conexión. `back` = página a la que volver; `consent` = acepta la privacidad a la vez. */
export function googleConnectUrl(back: string, consent = false): string {
  const q = new URLSearchParams({ back });
  if (consent) q.set('consent', '1');
  return `./api/google/connect?${q}`;
}

const REASONS: Record<string, string> = {
  unavailable: 'Google Health todavía no está disponible en Runch.',
  garmin: 'Tu cuenta ya usa Garmin: tus datos salen de ahí.',
  consent: 'Antes tienes que aceptar la privacidad.',
  state: 'El enlace ha caducado. Vuelve a pulsar «Conectar Google Health».',
  denied: 'Has cancelado en Google. Puedes volver a intentarlo cuando quieras.',
  scopes: 'Hace falta marcar al menos un permiso de salud en Google. Vuelve a intentarlo y deja marcadas las casillas.',
  token: 'Google no ha aceptado la conexión. Vuelve a intentarlo.',
  not_linked: 'Conectado, pero falta un paso: abre la app Google Health en tu móvil e inicia sesión con esta misma cuenta de Google.',
  busy: 'Hay una descarga en marcha. Prueba otra vez en un par de minutos.',
  error: 'Algo ha fallado al conectar con Google Health. Vuelve a intentarlo.',
};

export interface GoogleReturn { ok: boolean; reason?: string; message: string }

/** Lee una vez el resultado de volver de Google (?google=…) y lo quita de la URL para que no se repita al recargar. */
export function readGoogleReturn(): GoogleReturn | null {
  const q = new URLSearchParams(window.location.search);
  const g = q.get('google');
  if (!g) return null;
  const reason = q.get('reason') ?? undefined;
  q.delete('google'); q.delete('reason');
  const rest = q.toString();
  try { window.history.replaceState(null, '', `${window.location.pathname}${rest ? `?${rest}` : ''}${window.location.hash}`); } catch { /* sin history */ }
  if (g === 'ok') return { ok: true, message: 'Google Health conectado. Estamos bajando tus datos.' };
  return { ok: false, reason, message: REASONS[reason ?? 'error'] ?? REASONS.error };
}

/** El resultado de volver de Google, leído una sola vez al cargar. */
let pending: GoogleReturn | null | undefined;
export function useGoogleReturn(): GoogleReturn | null {
  const [r] = useState(() => {
    if (pending === undefined) pending = readGoogleReturn();
    return pending;
  });
  return r;
}

/** Qué lee la app y para qué. Google exige enseñarlo antes de su pantalla de permisos. */
export function GoogleHealthDisclosure() {
  return (
    <Stack spacing={1}>
      <Typography variant="body2" color="text.secondary">
        Runch leerá de Google Health, solo para enseñarte tus datos, tus análisis y tu plan:
      </Typography>
      <Box component="ul" sx={{ m: 0, pl: 2.5, display: 'grid', gap: 0.5, '& li': { fontSize: 14, color: 'text.secondary' } }}>
        <li><b>Actividad y entrenos</b>: pasos, calorías, minutos activos y tus sesiones.</li>
        <li><b>Medidas de salud</b>: pulso, pulso en reposo, variabilidad (HRV), peso y VO2 máx.</li>
        <li><b>Sueño</b>: cuánto y cómo duermes.</li>
      </Box>
      <Typography variant="body2" color="text.secondary">
        Solo lectura: no cambia nada en tu cuenta. Para los textos del coach, el plan y el chat se envía un resumen a la IA
        de Anthropic, que no lo usa para entrenar sus modelos. No vendemos ni compartimos tus datos y no se usan para
        publicidad. Puedes desconectarlo cuando quieras desde el menú de tu cuenta.
      </Typography>
    </Stack>
  );
}

/** Tarjeta para conectar Google Health (onboarding). */
export function GoogleHealthConnect({ back, consent }: { back: string; consent: boolean }) {
  return (
    <Card sx={{ borderRadius: '24px', p: 2.5, bgcolor: 'background.paper' }}>
      <Stack spacing={2}>
        <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center' }}>
          <Box sx={{ width: 40, height: 40, borderRadius: '12px', display: 'grid', placeItems: 'center', flexShrink: 0,
            bgcolor: 'color-mix(in srgb, #1A73E8 14%, transparent)', color: '#1A73E8' }}>
            <FavoriteRounded />
          </Box>
          <Box>
            <Typography sx={{ fontWeight: 600 }}>¿No tienes Garmin? Conecta Google Health</Typography>
            <Typography variant="body2" color="text.secondary">Apple Watch, Pixel Watch, Fitbit, Oura…</Typography>
          </Box>
        </Stack>
        <Typography variant="body2" color="text.secondary">
          Necesitas la app <b>Google Health</b> en el móvil, con tu cuenta de Google y recibiendo datos de Apple Salud
          (iPhone) o Health Connect (Android).
        </Typography>
        <GoogleHealthDisclosure />
        <Button variant="contained" disableElevation size="large" href={googleConnectUrl(back, consent)} sx={BTN}>
          Conectar Google Health
        </Button>
        <Typography variant="caption" color="text.secondary">
          Con Google Health no hay Body Battery, estrés ni el detalle de cada entreno (ritmo por kilómetro o mapa):
          si tienes Garmin, mejor conéctalo arriba.
        </Typography>
      </Stack>
    </Card>
  );
}

/** Avisos cuando Google Health necesita algo de ti (dentro de la app). */
export function GoogleHealthAlert({ me, onSynced }: { me: Me; onSynced: (msg: string) => void }) {
  const [busy, setBusy] = useState(false);
  if (me.status === 'google_reauth') {
    return (
      <Alert severity="warning" sx={{ borderRadius: '16px', mb: 2 }}
        action={<Button color="inherit" size="small" href={googleConnectUrl('hoy')}>Reconectar</Button>}>
        Google Health ya no da acceso a tus datos: tus datos no se actualizan.
      </Alert>
    );
  }
  if (me.status === 'google_not_linked') {
    const retry = async () => {
      setBusy(true);
      try { await call('./api/sync', {}); onSynced('Comprobando Google Health…'); } catch (e) { onSynced((e as Error).message); } finally { setBusy(false); }
    };
    return (
      <Alert severity="info" sx={{ borderRadius: '16px', mb: 2 }}
        action={<Button color="inherit" size="small" disabled={busy} onClick={retry}>Ya está</Button>}>
        Falta un paso: abre la app Google Health en tu móvil e inicia sesión con esta cuenta de Google.
        {me.google?.linkUrl && <> <a href={me.google.linkUrl} target="_blank" rel="noreferrer" style={{ color: 'inherit' }}>Abrir Google Health</a></>}
      </Alert>
    );
  }
  return null;
}

/** Ver y gestionar la conexión (menú de la cuenta). */
export function GoogleHealthDialog({ open, onClose, me, onChanged }: { open: boolean; onClose: () => void; me: Me | null; onChanged: (msg: string) => void }) {
  const [confirm, setConfirm] = useState(false);
  const [deleteData, setDeleteData] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { if (!open) { setConfirm(false); setDeleteData(false); setErr(null); } }, [open]);
  const g = me?.google;
  const disconnect = async () => {
    setBusy(true); setErr(null);
    try {
      const r = await call<{ ok: boolean; deleted?: boolean; revoked?: boolean }>('./api/google/disconnect', { deleteData });
      const done = deleteData ? 'Google Health desconectado y datos borrados.' : 'Google Health desconectado.';
      // Si Google no ha confirmado que retira el permiso, se explica cómo quitarlo a mano.
      onChanged(r.revoked === false
        ? `${done} Google no ha confirmado que retira el permiso: quítalo en myaccount.google.com/connections.`
        : done);
      onClose();
      window.setTimeout(() => window.location.reload(), 800);
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  const state = g?.status === 'reauth' ? { t: 'Hay que reconectar', c: 'warning.main' }
    : g?.status === 'not_linked' ? { t: 'Falta enlazar la app Google Health', c: 'warning.main' }
      : { t: 'Conectado', c: 'success.main' };
  return (
    <Dialog open={open} onClose={busy ? undefined : onClose} slotProps={DIALOG_SX}>
      <DialogTitle sx={{ pr: 6 }}>Google Health
        <IconButton onClick={onClose} aria-label="Cerrar" disabled={busy} sx={{ position: 'absolute', right: 12, top: 12 }}><CloseRounded /></IconButton>
      </DialogTitle>
      <DialogContent>
        <Stack spacing={2.5}>
          <Box>
            <Typography sx={{ fontWeight: 600, color: state.c }}>{state.t}</Typography>
            {g?.connectedAt && (
              <Typography variant="body2" color="text.secondary">Desde {relative(new Date(g.connectedAt * 1000), new Date())}</Typography>
            )}
          </Box>
          {g?.status === 'not_linked' && g.linkUrl && (
            <Button variant="outlined" href={g.linkUrl} target="_blank" rel="noreferrer" endIcon={<OpenInNewRounded />} sx={{ borderRadius: 999, alignSelf: 'flex-start' }}>
              Abrir Google Health
            </Button>
          )}
          {g?.status === 'reauth' && (
            <Button variant="contained" disableElevation href={googleConnectUrl('hoy')} sx={{ ...BTN, alignSelf: 'flex-start' }}>Reconectar</Button>
          )}
          <GoogleHealthDisclosure />
          {!confirm ? (
            <Button color="error" onClick={() => setConfirm(true)} sx={{ borderRadius: 999, alignSelf: 'flex-start' }}>Desconectar Google Health</Button>
          ) : (
            <Card variant="outlined" sx={{ borderRadius: '16px', p: 2 }}>
              <Stack spacing={1.5}>
                <Typography sx={{ fontWeight: 500 }}>¿Desconectar Google Health?</Typography>
                <Typography variant="body2" color="text.secondary">Runch deja de leer tus datos al momento y Google retira el permiso.</Typography>
                <FormControlLabel control={<Checkbox checked={deleteData} onChange={(e) => setDeleteData(e.target.checked)} />}
                  label={<Typography variant="body2">Borrar también los datos ya descargados (tu plan, comidas y chat se quedan)</Typography>} />
                {err && <Alert severity="error" sx={{ borderRadius: '12px' }}>{err}</Alert>}
                <Stack direction="row" spacing={1}>
                  <Button variant="contained" color="error" disableElevation disabled={busy} onClick={disconnect} sx={{ borderRadius: 999 }}>Desconectar</Button>
                  <Button disabled={busy} onClick={() => setConfirm(false)} sx={{ borderRadius: 999 }}>Cancelar</Button>
                </Stack>
              </Stack>
            </Card>
          )}
        </Stack>
      </DialogContent>
    </Dialog>
  );
}
