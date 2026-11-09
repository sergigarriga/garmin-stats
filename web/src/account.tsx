import { useCallback, useEffect, useState } from 'react';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import CircularProgress from '@mui/material/CircularProgress';
import Dialog from '@mui/material/Dialog';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import IconButton from '@mui/material/IconButton';
import Link from '@mui/material/Link';
import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import CloseRounded from '@mui/icons-material/CloseRounded';
import ContentCopyRounded from '@mui/icons-material/ContentCopyRounded';
import DeleteOutlineRounded from '@mui/icons-material/DeleteOutlineRounded';
import OpenInNewRounded from '@mui/icons-material/OpenInNewRounded';
import { relative } from './format';

export const GARMIN_KEY_URL = 'https://connect.garmin.com/app/settings/personalApiToken';
const DIALOG_SX = { paper: { sx: { borderRadius: '28px', m: 2, width: 'calc(100% - 32px)', maxWidth: 520 } } };

export interface SyncState { status?: 'running' | 'done' | 'error' | 'key_invalid'; at?: number; finished?: number; backfill?: boolean; part?: number; backfillDone?: boolean }
export interface Me {
  email: string; name: string; role: 'owner' | 'friend'; status: 'invited' | 'onboarding' | 'active' | 'key_invalid';
  budgetUsd: number; monthSpendUsd: number; consented?: boolean; hasData: boolean; hasGoal: boolean; hasPlan: boolean;
  planJob?: { status: string; action: string } | null; sync: SyncState; owner: string;
  /** Última versión de novedades vista y desde cuándo tiene cuenta (epoch s). */
  seenRelease?: string | null; since?: number | null;
}

/** Llamada a la API de la web. Lanza un Error con el mensaje del servidor si algo falla. */
export async function call<T = unknown>(path: string, body?: unknown): Promise<T> {
  const r = await fetch(path, {
    method: body === undefined ? 'GET' : 'POST', credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (r.status === 401) { window.location.href = './auth/login'; throw new Error('Sesión caducada'); }
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error((j as { error?: string }).error ?? 'Algo ha fallado.');
  return j as T;
}

/** Quién soy y en qué punto está mi cuenta. `pollMs` > 0 vuelve a preguntar cada X ms. */
export function useMe(pollMs = 0) {
  const [me, setMe] = useState<Me | null>(null);
  const [error, setError] = useState<string | null>(null);
  const refresh = useCallback(async () => {
    try { const m = await call<Me>('./api/me'); setMe(m); setError(null); return m; } catch (e) { setError((e as Error).message); return null; }
  }, []);
  useEffect(() => {
    refresh();
    if (!pollMs) return;
    const id = window.setInterval(refresh, pollMs);
    return () => window.clearInterval(id);
  }, [refresh, pollMs]);
  return { me, error, refresh };
}

// ------------------------------------------------------------------ clave de Garmin
export function GarminKeySteps() {
  const steps = [
    <>Abre <Link href={GARMIN_KEY_URL} target="_blank" rel="noopener">Garmin Connect → Clave de API personal <OpenInNewRounded sx={{ fontSize: 14, verticalAlign: '-2px' }} /></Link> e inicia sesión (mejor desde el ordenador).</>,
    <>Pulsa <b>Crear clave</b>, acepta las condiciones de Garmin y elige que caduque en <b>1 año</b>.</>,
    <>Copia la clave: Garmin solo la enseña <b>una vez</b>. Pégala aquí abajo.</>,
  ];
  return (
    <Stack component="ol" spacing={1.25} sx={{ m: 0, p: 0, listStyle: 'none' }}>
      {steps.map((s, i) => (
        <Stack key={i} component="li" direction="row" spacing={1.5} sx={{ alignItems: 'flex-start' }}>
          <Box sx={{ width: 24, height: 24, borderRadius: '50%', flexShrink: 0, display: 'grid', placeItems: 'center', fontSize: 13, fontWeight: 600,
            bgcolor: 'primary.main', color: 'primary.contrastText' }}>{i + 1}</Box>
          <Typography variant="body2" sx={{ pt: 0.25 }}>{s}</Typography>
        </Stack>
      ))}
    </Stack>
  );
}

export function GarminKeyForm({ consent = true, onDone, submitLabel = 'Conectar Garmin' }: { consent?: boolean; onDone: () => void; submitLabel?: string }) {
  const [key, setKey] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const submit = async () => {
    setBusy(true); setErr(null);
    try { await call('./api/onboarding/key', { key, consent }); onDone(); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  return (
    <Stack spacing={1.5}>
      <TextField label="Tu clave de Garmin" value={key} onChange={(e) => setKey(e.target.value)} fullWidth multiline minRows={2}
        autoComplete="off" spellCheck={false} slotProps={{ htmlInput: { style: { fontFamily: 'monospace', fontSize: 13 } } }} />
      {err && <Alert severity="error" sx={{ borderRadius: '14px' }}>{err}</Alert>}
      <Button variant="contained" disableElevation size="large" onClick={submit} disabled={busy || key.trim().length < 20}
        startIcon={busy ? <CircularProgress size={18} color="inherit" /> : undefined} sx={{ borderRadius: 999, alignSelf: 'flex-start' }}>
        {busy ? 'Comprobando con Garmin…' : submitLabel}
      </Button>
      <Typography variant="caption" color="text.secondary">
        La clave se guarda cifrada y solo sirve para leer tus datos de Garmin. Puedes borrarla en Garmin Connect cuando quieras.
      </Typography>
    </Stack>
  );
}

export function GarminKeyDialog({ open, onClose, onDone }: { open: boolean; onClose: () => void; onDone: () => void }) {
  return (
    <Dialog open={open} onClose={onClose} slotProps={DIALOG_SX}>
      <DialogTitle sx={{ pr: 6 }}>Cambiar la clave de Garmin
        <IconButton onClick={onClose} aria-label="Cerrar" sx={{ position: 'absolute', right: 12, top: 12 }}><CloseRounded /></IconButton>
      </DialogTitle>
      <DialogContent>
        <Stack spacing={2.5}>
          <GarminKeySteps />
          <GarminKeyForm submitLabel="Guardar clave" onDone={() => { onDone(); onClose(); }} />
        </Stack>
      </DialogContent>
    </Dialog>
  );
}

// ------------------------------------------------------------------ borrar mi cuenta
export function DeleteAccountDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const del = async () => {
    setBusy(true); setErr(null);
    try { await call('./api/account/delete', {}); window.location.href = './auth/logout'; } catch (e) { setErr((e as Error).message); setBusy(false); }
  };
  return (
    <Dialog open={open} onClose={busy ? undefined : onClose} slotProps={DIALOG_SX}>
      <DialogTitle>¿Borrar tu cuenta?</DialogTitle>
      <DialogContent>
        <Typography color="text.secondary">
          Se borran tus datos de Garmin, tu plan, tus conversaciones con el coach y tu clave de Garmin. No se puede deshacer.
          Si quieres volver, tendrán que invitarte otra vez.
        </Typography>
        {err && <Alert severity="error" sx={{ mt: 2, borderRadius: '14px' }}>{err}</Alert>}
        <Stack direction="row" spacing={1} sx={{ justifyContent: 'flex-end', mt: 3 }}>
          <Button onClick={onClose} disabled={busy} sx={{ borderRadius: 999 }}>Cancelar</Button>
          <Button color="error" variant="contained" disableElevation onClick={del} disabled={busy} sx={{ borderRadius: 999 }}>
            {busy ? 'Borrando…' : 'Borrar todo'}
          </Button>
        </Stack>
      </DialogContent>
    </Dialog>
  );
}

// ------------------------------------------------------------------ invitaciones (solo el dueño)
interface AdminUser {
  email: string; name: string; role: 'owner' | 'friend'; status: Me['status']; budgetUsd: number; monthSpendUsd: number;
  invitedAt?: number; joinedAt?: number; lastSync?: number; syncStatus?: string;
  totalCostUsd?: number; calls?: number; lastAi?: string | null;
}
const STATUS: Record<string, { label: string; color: 'default' | 'success' | 'warning' | 'error' | 'info' }> = {
  invited: { label: 'Invitación enviada', color: 'default' },
  onboarding: { label: 'Configurando', color: 'info' },
  active: { label: 'Activa', color: 'success' },
  key_invalid: { label: 'Clave caducada', color: 'error' },
};
const money = (v: number) => `${v.toFixed(2).replace('.', ',')} $`;

export function AdminDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [list, setList] = useState<AdminUser[] | null>(null);
  const [email, setEmail] = useState('');
  const [name, setName] = useState('');
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [invite, setInvite] = useState<{ name: string; email: string } | null>(null);
  const [removing, setRemoving] = useState<AdminUser | null>(null);
  const [copied, setCopied] = useState(false);

  const act = async (body?: Record<string, unknown>) => {
    setBusy(true); setErr(null);
    try { const r = await call<{ users: AdminUser[] }>('./api/admin/users', body); setList(r.users); return true; }
    catch (e) { setErr((e as Error).message); return false; } finally { setBusy(false); }
  };
  useEffect(() => { if (open) { setInvite(null); act(); } }, [open]);  // eslint-disable-line react-hooks/exhaustive-deps

  const add = async () => {
    const e = email.trim().toLowerCase();
    if (await act({ action: 'add', email: e, name: name.trim() })) { setInvite({ name: name.trim(), email: e }); setEmail(''); setName(''); }
  };
  const site = window.location.origin;
  const message = invite
    ? `¡Hola${invite.name ? ` ${invite.name}` : ''}! Te he invitado a Runch, mi app con tus datos de Garmin y un coach con IA que te hace un plan de entreno. `
      + `Entra con tu cuenta de Google (${invite.email}) aquí: ${site} y sigue los pasos. Tardas 5 minutos y te pedirá una clave de tu Garmin Connect.`
    : '';
  const copy = async () => { try { await navigator.clipboard.writeText(message); setCopied(true); setTimeout(() => setCopied(false), 2000); } catch { /* sin portapapeles */ } };

  return (
    <Dialog open={open} onClose={onClose} slotProps={{ paper: { sx: { borderRadius: '28px', m: 2, width: 'calc(100% - 32px)', maxWidth: 600 } } }}>
      <DialogTitle sx={{ pr: 6 }}>Invitaciones
        <IconButton onClick={onClose} aria-label="Cerrar" sx={{ position: 'absolute', right: 12, top: 12 }}><CloseRounded /></IconButton>
      </DialogTitle>
      <DialogContent>
        <Stack spacing={2.5}>
          {!list ? <CircularProgress size={24} /> : (
            <Stack spacing={1.25}>
              {list.map((u) => (
                <Box key={u.email} sx={{ p: 1.5, borderRadius: '16px', bgcolor: 'action.hover' }}>
                  <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
                    <Box sx={{ flex: 1, minWidth: 0 }}>
                      <Typography sx={{ fontWeight: 500 }} noWrap>{u.name || u.email.split('@')[0]}{u.role === 'owner' ? ' (tú)' : ''}</Typography>
                      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', overflowWrap: 'anywhere' }}>{u.email}</Typography>
                    </Box>
                    <Chip size="small" label={STATUS[u.status]?.label ?? u.status} color={STATUS[u.status]?.color ?? 'default'} />
                    {u.role !== 'owner' && (
                      <IconButton size="small" aria-label={`Quitar a ${u.email}`} onClick={() => setRemoving(u)}><DeleteOutlineRounded fontSize="small" /></IconButton>
                    )}
                  </Stack>
                  <Stack direction="row" spacing={2} sx={{ mt: 1, flexWrap: 'wrap', rowGap: 0.75, alignItems: 'center' }}>
                    <Typography variant="caption" color="text.secondary">IA este mes: <b>{money(u.monthSpendUsd)}</b> de</Typography>
                    <TextField select size="small" value={u.budgetUsd} disabled={busy} variant="standard"
                      onChange={(e) => act({ action: 'budget', email: u.email, budgetUsd: Number(e.target.value) })}
                      sx={{ minWidth: 70, '& .MuiInputBase-input': { fontSize: 13, py: 0.25 } }}>
                      {[...new Set([2, 5, 10, 20, 50, u.budgetUsd])].sort((a, b) => a - b).map((v) => <MenuItem key={v} value={v}>{v} $</MenuItem>)}
                    </TextField>
                    {u.lastSync && <Typography variant="caption" color="text.secondary">Garmin {relative(new Date(u.lastSync * 1000), new Date())}</Typography>}
                  </Stack>
                </Box>
              ))}
            </Stack>
          )}

          <Box>
            <Typography variant="subtitle2" sx={{ mb: 1 }}>Invitar a alguien</Typography>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
              <TextField size="small" label="Nombre" value={name} onChange={(e) => setName(e.target.value)} sx={{ flex: 1 }} />
              <TextField size="small" label="Email de Google" type="email" value={email} onChange={(e) => setEmail(e.target.value)} sx={{ flex: 2 }} />
              <Button variant="contained" disableElevation onClick={add} disabled={busy || !email.includes('@')} sx={{ borderRadius: 999, whiteSpace: 'nowrap' }}>Invitar</Button>
            </Stack>
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
              Tope de IA por defecto: 5 $ al mes. Al llegar al 80 % pasa al modelo barato y al 100 % la IA se pausa hasta el mes siguiente.
            </Typography>
          </Box>

          {invite && (
            <Alert severity="success" sx={{ borderRadius: '16px' }}>
              <Typography variant="body2" sx={{ mb: 1 }}>Invitación creada. Mándale este mensaje:</Typography>
              <Typography variant="body2" sx={{ p: 1.25, borderRadius: '12px', bgcolor: 'background.paper', mb: 1 }}>{message}</Typography>
              <Button size="small" startIcon={<ContentCopyRounded />} onClick={copy} sx={{ borderRadius: 999 }}>{copied ? 'Copiado' : 'Copiar mensaje'}</Button>
              <Typography variant="caption" sx={{ display: 'block', mt: 1 }}>
                Mientras la app de Google esté en modo de prueba, añade también su email en Google Cloud → Google Auth Platform → Público → Usuarios de prueba.
              </Typography>
            </Alert>
          )}
          {err && <Alert severity="error" sx={{ borderRadius: '14px' }}>{err}</Alert>}
        </Stack>
      </DialogContent>

      <Dialog open={!!removing} onClose={() => setRemoving(null)} slotProps={DIALOG_SX}>
        <DialogTitle>¿Quitar a {removing?.name || removing?.email}?</DialogTitle>
        <DialogContent>
          <Typography color="text.secondary">Pierde el acceso y se borran todos sus datos, su plan y su clave de Garmin. No se puede deshacer.</Typography>
          <Stack direction="row" spacing={1} sx={{ justifyContent: 'flex-end', mt: 3 }}>
            <Button onClick={() => setRemoving(null)} sx={{ borderRadius: 999 }}>Cancelar</Button>
            <Button color="error" variant="contained" disableElevation sx={{ borderRadius: 999 }}
              onClick={async () => { const u = removing; setRemoving(null); if (u) await act({ action: 'remove', email: u.email }); }}>Quitar y borrar</Button>
          </Stack>
        </DialogContent>
      </Dialog>
    </Dialog>
  );
}
