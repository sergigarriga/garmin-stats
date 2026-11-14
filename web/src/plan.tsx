// «Tu plan»: qué plan tienes, qué incluye Runch Plus y el pago (Stripe Checkout) o la gestión de la suscripción
// (portal de Stripe). Se abre desde el menú y sola cuando una función es de pago (la API responde 402).
import { useCallback, useEffect, useState } from 'react';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import ButtonBase from '@mui/material/ButtonBase';
import CircularProgress from '@mui/material/CircularProgress';
import Dialog from '@mui/material/Dialog';
import IconButton from '@mui/material/IconButton';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import useMediaQuery from '@mui/material/useMediaQuery';
import { useTheme } from '@mui/material/styles';
import AutoAwesomeRounded from '@mui/icons-material/AutoAwesomeRounded';
import CardGiftcardRounded from '@mui/icons-material/CardGiftcardRounded';
import CheckRounded from '@mui/icons-material/CheckRounded';
import CloseRounded from '@mui/icons-material/CloseRounded';
import LockOutlined from '@mui/icons-material/LockOutlined';
import RemoveRounded from '@mui/icons-material/RemoveRounded';
import { call } from './account';
import { BRAND, BRAND_DARK, BRAND_INK, brandTint } from './brand/colors';

type Offer = 'monthly' | 'yearly' | 'founder';
export interface Billing {
  plan: 'comp' | 'free' | 'plus' | 'founder'; entitled: boolean; status?: string | null; periodEnd?: number | null;
  cancelAtEnd: boolean; interval?: 'month' | 'year' | null; trialEnd?: number | null; available: boolean; canManage: boolean;
  prices: Record<Offer, number>; offers: Offer[]; foundersLeft: number; freeAsksLeft: number; trialDays: number;
}

const eur = (v: number) => `${v.toFixed(2).replace('.', ',').replace(',00', '')} €`;
const day = (epoch: number) => new Date(epoch * 1000).toLocaleDateString('es-ES', { day: 'numeric', month: 'long', year: 'numeric' });
const FEATURES: { label: string; free: boolean | string }[] = [
  { label: 'Tus datos, gráficas, récords y detalle de cada entreno', free: true },
  { label: 'Textos del día', free: 'Básicos' },
  { label: 'Coach con IA: plan de entreno y ajuste cada semana', free: false },
  { label: 'Chat con tu coach', free: '3 de prueba' },
  { label: 'Resumen con IA al abrir la app', free: false },
  { label: 'Comida: análisis con foto o texto', free: false },
  { label: 'Menú semanal y lista de la compra', free: false },
];

export function PlanDialog() {
  const theme = useTheme();
  const mobile = useMediaQuery(theme.breakpoints.down('sm'));
  const [open, setOpen] = useState(false);
  const [why, setWhy] = useState<string | null>(null);
  const [b, setB] = useState<Billing | null>(null);
  const [offer, setOffer] = useState<Offer>('yearly');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(() => call<Billing>('./api/billing').then((x) => {
    setB(x);
    setOffer((o) => (x.offers.includes('founder') && x.foundersLeft > 0 ? 'founder' : x.offers.length && !x.offers.includes(o) ? x.offers[0] : o));
  }).catch((e) => setErr((e as Error).message)), []);

  useEffect(() => {
    const on = (e: Event) => { setWhy((e as CustomEvent<string | undefined>).detail ?? null); setErr(null); setOpen(true); load(); };
    window.addEventListener('open-plan', on);
    return () => window.removeEventListener('open-plan', on);
  }, [load]);

  const go = async (path: 'checkout' | 'portal') => {
    setBusy(true); setErr(null);
    try {
      const r = await call<{ url: string }>(`./api/billing/${path}`, path === 'checkout' ? { offer } : {});
      window.location.href = r.url;
    } catch (e) { setErr((e as Error).message); setBusy(false); }
  };

  const paid = !!b && (b.plan === 'plus' || b.plan === 'founder') && b.entitled;
  const showOffers = !!b && b.plan !== 'comp' && !paid;
  const perMonth = b ? b.prices.yearly / 12 : 0;
  const saving = b ? Math.round((1 - b.prices.yearly / (b.prices.monthly * 12)) * 100) : 0;
  const options: { key: Offer; title: string; price: string; sub: string; tag?: string }[] = !b ? [] : [
    { key: 'founder' as const, title: 'Fundadores', price: `${eur(b.prices.founder)}/mes`, sub: `Para siempre · quedan ${b.foundersLeft} plazas`, tag: 'Precio de lanzamiento' },
    { key: 'yearly' as const, title: 'Anual', price: `${eur(b.prices.yearly)}/año`, sub: `${eur(perMonth)} al mes`, tag: `Ahorras un ${saving} %` },
    { key: 'monthly' as const, title: 'Mensual', price: `${eur(b.prices.monthly)}/mes`, sub: 'Sin permanencia' },
  ].filter((o) => (b.available ? b.offers.includes(o.key) : true) && (o.key !== 'founder' || b.foundersLeft > 0 || !b.available));

  return (
    <Dialog open={open} onClose={() => setOpen(false)} fullScreen={mobile}
      slotProps={{ paper: { sx: mobile ? {} : { borderRadius: '28px', width: '100%', maxWidth: 520 } } }}>
      <Box sx={{ p: { xs: 2.5, sm: 3.5 }, pt: { xs: 'calc(env(safe-area-inset-top) + 20px)', sm: 3.5 }, pb: { xs: 'calc(env(safe-area-inset-bottom) + 24px)', sm: 3.5 } }}>
        <Stack direction="row" sx={{ alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
          <Typography variant="h5" component="h2" sx={{ fontWeight: 600 }}>Tu plan</Typography>
          <IconButton onClick={() => setOpen(false)} aria-label="Cerrar"><CloseRounded /></IconButton>
        </Stack>

        {!b && !err && <Box sx={{ display: 'grid', placeItems: 'center', py: 8 }}><CircularProgress /></Box>}
        {why && showOffers && (
          <Alert icon={<LockOutlined fontSize="small" />} severity="info" sx={{ borderRadius: '16px', mb: 2 }}>{why}</Alert>
        )}

        {b && (
          <Stack spacing={2.5}>
            {/* Plan actual */}
            <Box sx={{ p: 2, borderRadius: '20px', bgcolor: brandTint(12), display: 'flex', gap: 1.5, alignItems: 'center' }}>
              <Box sx={{ width: 44, height: 44, borderRadius: '50%', display: 'grid', placeItems: 'center', bgcolor: BRAND, color: '#fff', flexShrink: 0 }}>
                {b.plan === 'comp' ? <CardGiftcardRounded /> : <AutoAwesomeRounded />}
              </Box>
              <Box sx={{ minWidth: 0 }}>
                <Typography sx={{ fontWeight: 600 }}>
                  {b.plan === 'comp' ? 'Invitación: todo incluido' : paid ? `Runch Plus${b.plan === 'founder' ? ' · Fundadores' : b.interval === 'year' ? ' · anual' : ' · mensual'}`
                    : b.trialEnd ? 'Prueba de Runch Plus' : 'Plan gratis'}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  {b.plan === 'comp' ? 'Tienes Runch completo, sin pagar nada.'
                    : paid && b.status === 'past_due' ? 'No hemos podido cobrar la última cuota. Revisa tu tarjeta para no perder Plus.'
                    : paid && b.periodEnd ? (b.cancelAtEnd ? `Cancelado: sigues con Plus hasta el ${day(b.periodEnd)}.` : `Se renueva el ${day(b.periodEnd)}.`)
                    : b.trialEnd ? `Todo incluido hasta el ${day(b.trialEnd)}.`
                    : 'Tus datos y gráficas, siempre gratis.'}
                </Typography>
              </Box>
            </Box>

            {paid && b.canManage && (
              <Button variant="outlined" disabled={busy} onClick={() => go('portal')} sx={{ borderRadius: 999, py: 1.2 }}>
                {busy ? 'Abriendo…' : 'Gestionar suscripción'}
              </Button>
            )}
            {paid && b.canManage && (
              <Typography variant="caption" color="text.secondary" sx={{ textAlign: 'center', mt: '-12px !important' }}>
                Cambia la tarjeta, descarga facturas o cancela cuando quieras.
              </Typography>
            )}

            {/* Ofertas */}
            {showOffers && (
              <Stack spacing={1.25}>
                {options.map((o) => {
                  const sel = o.key === offer;
                  return (
                    <ButtonBase key={o.key} onClick={() => setOffer(o.key)} aria-pressed={sel}
                      sx={{ display: 'flex', textAlign: 'left', font: 'inherit', p: 2, borderRadius: '20px', border: 2, gap: 1.5, alignItems: 'center',
                        borderColor: sel ? BRAND : 'divider', bgcolor: sel ? brandTint(8) : 'transparent', transition: 'border-color .15s, background-color .15s' }}>
                      <Box sx={{ width: 22, height: 22, borderRadius: '50%', border: 2, borderColor: sel ? BRAND : 'text.disabled', display: 'grid', placeItems: 'center', flexShrink: 0 }}>
                        {sel && <Box sx={{ width: 10, height: 10, borderRadius: '50%', bgcolor: BRAND }} />}
                      </Box>
                      <Box sx={{ flex: 1, minWidth: 0 }}>
                        <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap', rowGap: 0.25 }}>
                          <Typography sx={{ fontWeight: 600 }}>{o.title}</Typography>
                          {o.tag && <Box sx={{ px: 1, py: 0.25, borderRadius: 999, fontSize: 11, fontWeight: 700, fontFamily: theme.typography.fontFamily, bgcolor: BRAND, color: '#fff' }}>{o.tag}</Box>}
                        </Stack>
                        <Typography variant="body2" color="text.secondary">{o.sub}</Typography>
                      </Box>
                      <Typography sx={{ fontWeight: 700, whiteSpace: 'nowrap' }}>{o.price}</Typography>
                    </ButtonBase>
                  );
                })}
                <Button variant="contained" disableElevation disabled={busy || !b.available} onClick={() => go('checkout')}
                  sx={{ borderRadius: 999, py: 1.5, fontSize: 16, fontWeight: 600, bgcolor: BRAND, color: '#fff', '&:hover': { bgcolor: BRAND_DARK } }}>
                  {!b.available ? 'Muy pronto' : busy ? 'Abriendo el pago…' : 'Pasar a Runch Plus'}
                </Button>
                <Typography variant="caption" color="text.secondary" sx={{ textAlign: 'center' }}>
                  {b.available ? 'Pago seguro con Stripe. IVA incluido. Cancelas cuando quieras desde aquí.'
                    : 'Los pagos aún no están abiertos. Te avisaremos en Novedades.'}
                </Typography>
              </Stack>
            )}
            {/* Qué incluye */}
            <Box>
              <Stack direction="row" sx={{ px: 0.5, mb: 0.5, alignItems: 'center' }}>
                <Typography variant="overline" color="text.secondary" sx={{ flex: 1 }}>Qué incluye</Typography>
                <Typography variant="caption" color="text.secondary" sx={{ width: 76, textAlign: 'center' }}>Gratis</Typography>
                <Typography variant="caption" sx={{ width: 56, textAlign: 'center', fontWeight: 700, color: BRAND_INK }}>Plus</Typography>
              </Stack>
              {FEATURES.map((f) => (
                <Stack key={f.label} direction="row" sx={{ alignItems: 'center', py: 1, px: 0.5, borderTop: 1, borderColor: 'divider' }}>
                  <Typography variant="body2" sx={{ flex: 1, pr: 1 }}>{f.label}</Typography>
                  <Box sx={{ width: 76, display: 'grid', placeItems: 'center', color: 'text.disabled' }}>
                    {f.free === true ? <CheckRounded fontSize="small" sx={{ color: 'text.secondary' }} />
                      : f.free === false ? <RemoveRounded fontSize="small" /> : <Typography variant="caption" color="text.secondary">{f.free}</Typography>}
                  </Box>
                  <Box sx={{ width: 56, display: 'grid', placeItems: 'center', color: BRAND_INK }}><CheckRounded fontSize="small" /></Box>
                </Stack>
              ))}
            </Box>

          </Stack>
        )}
        {err && <Alert severity="error" sx={{ borderRadius: '14px', mt: 2 }}>{err}</Alert>}
      </Box>
    </Dialog>
  );
}

/** Vuelta del pago de Stripe (/?billing=ok|cancel): limpia la URL y dice qué ha pasado. Se llama una vez al arrancar. */
export function readBillingReturn(): 'ok' | 'cancel' | null {
  try {
    const q = new URLSearchParams(window.location.search);
    const v = q.get('billing');
    if (v !== 'ok' && v !== 'cancel') return null;
    q.delete('billing');
    window.history.replaceState(null, '', window.location.pathname + (q.toString() ? `?${q}` : '') + window.location.hash);
    return v;
  } catch { return null; }
}
