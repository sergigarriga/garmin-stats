// Menú y compra de la semana: el coach propone un menú de 7 días según tu entreno y tu objetivo de Comida, y la
// lista de la compra sale con productos reales de Mercadona (con su permiso): envases, precio, total y enlace a cada
// ficha. Se puede cambiar de producto, quitar líneas, marcar lo que ya está en el carro y copiar o compartir la lista.
import { useCallback, useEffect, useMemo, useState } from 'react';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import ButtonBase from '@mui/material/ButtonBase';
import Card from '@mui/material/Card';
import Checkbox from '@mui/material/Checkbox';
import Chip from '@mui/material/Chip';
import CircularProgress from '@mui/material/CircularProgress';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Divider from '@mui/material/Divider';
import IconButton from '@mui/material/IconButton';
import InputAdornment from '@mui/material/InputAdornment';
import LinearProgress from '@mui/material/LinearProgress';
import Link from '@mui/material/Link';
import Snackbar from '@mui/material/Snackbar';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import ToggleButton from '@mui/material/ToggleButton';
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup';
import Typography from '@mui/material/Typography';
import useMediaQuery from '@mui/material/useMediaQuery';
import { alpha, useTheme } from '@mui/material/styles';
import ShoppingCartRounded from '@mui/icons-material/ShoppingCartRounded';
import TuneRounded from '@mui/icons-material/TuneRounded';
import OpenInNewRounded from '@mui/icons-material/OpenInNewRounded';
import ContentCopyRounded from '@mui/icons-material/ContentCopyRounded';
import IosShareRounded from '@mui/icons-material/IosShareRounded';
import AutoAwesomeRounded from '@mui/icons-material/AutoAwesomeRounded';
import ChevronLeftRounded from '@mui/icons-material/ChevronLeftRounded';
import SwapHorizRounded from '@mui/icons-material/SwapHorizRounded';
import BoltRounded from '@mui/icons-material/BoltRounded';
import SearchRounded from '@mui/icons-material/SearchRounded';
import { call } from '../account';
import { toDate } from '../data';
import { dateLong, int } from '../format';
import { useResolvedMode } from '../theme';
import { CARD_SX, IconBubble, PageHeader, SectionTitle } from '../ui';

// ------------------------------------------------------------------ tipos (los manda /api/shopping)
type MealKey = 'desayuno' | 'comida' | 'cena' | 'snacks';
type Diet = { vegetariano: boolean; sinLactosa: boolean; sinGluten: boolean; noPescado: boolean };
interface Prefs { enabled: boolean; people: number; meals: MealKey[]; diet: Diet; allergies: string; budget: number | null; cooking: 'rapido' | 'normal' }
interface Product { id: string; name: string; brand?: string; fmt?: string; pack?: string; price?: number | null; perKgL?: number | null;
  perUnit?: 'kg' | 'l' | null; unitPrice?: number | null; unitPriceUnit?: string | null; url?: string; aisle?: string }
interface Alt extends Product { packs?: number | null; cost: number; byWeight?: boolean; qty?: number | null }
interface Line {
  key: string; name: string; amount: number; unit: 'g' | 'ml' | 'ud'; aisle: string; pantry: boolean; product: Product | null;
  packs: number | null; cost: number | null; alternatives: Alt[]; warning: string | null; searchUrl: string; matchedBy?: string;
  byWeight?: boolean; qty?: number | null; leftover?: number; leftoverUnit?: string; approx?: boolean; swapped?: boolean;
  removed: boolean; checked: boolean; skip: boolean; usedCost?: number; also?: { key: string; name: string; amount: number }[];
}
interface Dish { meal: MealKey; dish: string; portion: string; note?: string | null }
interface Day { date: string; weekday: string; focus?: string | null; meals: Dish[]; kcal_per_person?: number; protein_g_per_person: number;
  sessions: { type: string; title?: string; km?: number | null; min?: number | null }[] }
interface Plan { start: string; end: string; generatedAt: string; summary: string; days: Day[]; tips: string[]; warnings: string[]; people: number;
  meals: MealKey[]; cost: number }
interface ShoppingList { groups: { aisle: string; items: Line[] }[]; total: number; usedTotal: number; items: number; unmatched: number; checkedTotal: number;
  budget: { target: number; over: boolean; mode: 'normal' | 'ahorro'; biggest: { name: string; cost: number }[] } | null }
interface Nutrition { kcalDay?: number | null; proteinDay?: number | null; carbsDay?: number | null; fatDay?: number | null; coverage: number;
  aiKcalDay?: number | null; aiProteinDay?: number | null; targetKcalDay?: number | null; targetMealsKcalDay?: number | null;
  proteinRefG?: number[] | null; mealsShare: number; linesWithData: number; lines: number }
export interface ShoppingView {
  prefs: Prefs; job: { status: 'running' | 'done' | 'error'; at: number; error?: string } | null; hideCalories: boolean;
  catalog: { available: boolean; date?: string; postcode: string; count?: number };
  attribution: { products: string; nutrition: string; allergy: string };
  plan: Plan | null; list: ShoppingList | null; nutrition: Nutrition | null; text?: string; budgetOver: boolean;
}

const MEALS: { v: MealKey; label: string }[] = [
  { v: 'desayuno', label: 'Desayuno' }, { v: 'comida', label: 'Comida' }, { v: 'cena', label: 'Cena' }, { v: 'snacks', label: 'Snacks' },
];
const MEAL_LABEL = Object.fromEntries(MEALS.map((m) => [m.v, m.label])) as Record<MealKey, string>;
const DIETS: { k: keyof Diet; label: string }[] = [
  { k: 'vegetariano', label: 'Vegetariano' }, { k: 'sinLactosa', label: 'Sin lactosa' }, { k: 'sinGluten', label: 'Sin gluten' },
  { k: 'noPescado', label: 'Sin pescado' },
];
const COLOR = { light: '#E8710A', dark: '#FCAD70' };
const PILL = { borderRadius: 999 } as const;
const eur = new Intl.NumberFormat('es-ES', { style: 'currency', currency: 'EUR' });
const money = (v?: number | null) => (v == null ? '–' : eur.format(v));
const num = (v: number) => new Intl.NumberFormat('es-ES', { maximumFractionDigits: 2 }).format(v);
const fmtLabel = (f?: string | null) => (f ?? '').replace(/(\d)\.(\d)/g, '$1,$2');
const dShort = (iso: string) => new Intl.DateTimeFormat('es-ES', { day: 'numeric', month: 'short' }).format(toDate(iso)).replace('.', '');
const amountLabel = (l: Line) => `${l.unit === 'ud' ? int(l.amount) : num(l.amount >= 1000 ? l.amount / 1000 : l.amount)} ${l.unit === 'ud' ? 'ud' : l.amount >= 1000 ? (l.unit === 'g' ? 'kg' : 'l') : l.unit}`;
const SESSION: Record<string, string> = { long: 'Tirada larga', tempo: 'Ritmo', intervals: 'Series', race: 'Carrera', easy: 'Rodaje', strength: 'Fuerza',
  swim: 'Natación', cross: 'Cruzado' };

function unitPrice(p: Product) {
  if (p.perKgL != null && p.perUnit) return `${money(p.perKgL)}/${p.perUnit}`;
  if (p.unitPrice != null && p.unitPriceUnit) return `${money(p.unitPrice)}/${p.unitPriceUnit === 'dc' || p.unitPriceUnit === 'dz' ? 'docena' : p.unitPriceUnit}`;
  return '';
}
function qtyLabel(l: { byWeight?: boolean; qty?: number | null; packs?: number | null; approx?: boolean }) {
  if (l.byWeight) return `≈ ${num((l.qty ?? 0) / 1000)} kg a peso`;
  return `${l.packs ?? 1} ×`;
}

// ------------------------------------------------------------------ datos
export function useShopping() {
  const [view, setView] = useState<ShoppingView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    try { setView(await call<ShoppingView>('./api/shopping')); setError(null); } catch (e) { setError((e as Error).message); }
  }, []);
  useEffect(() => { load(); }, [load]);
  const act = useCallback(async (path: string, body: unknown) => {
    const v = await call<ShoppingView>(`./api/shopping/${path}`, body);
    setView(v);
    return v;
  }, []);
  // Mientras se prepara el menú, se pregunta cada 4 s
  const running = view?.job?.status === 'running';
  useEffect(() => {
    if (!running) return;
    const id = window.setInterval(load, 4000);
    return () => window.clearInterval(id);
  }, [running, load]);
  return { view, error, load, act };
}

// ------------------------------------------------------------------ ajustes
function SettingsDialog({ open, onClose, v, act }: { open: boolean; onClose: () => void; v: ShoppingView; act: (p: string, b: unknown) => Promise<ShoppingView> }) {
  const p = v.prefs;
  const [err, setErr] = useState<string | null>(null);
  const [allergies, setAllergies] = useState(p.allergies);
  const [budget, setBudget] = useState(p.budget ? String(p.budget) : '');
  useEffect(() => { if (open) { setAllergies(p.allergies); setBudget(p.budget ? String(p.budget) : ''); setErr(null); } }, [open, p.allergies, p.budget]);
  const set = async (body: unknown) => { setErr(null); try { await act('prefs', body); return true; } catch (e) { setErr((e as Error).message); return false; } };
  const toggleMeal = (m: MealKey) => {
    const next = p.meals.includes(m) ? p.meals.filter((x) => x !== m) : [...p.meals, m];
    if (next.length) set({ meals: next });
  };
  const save = async () => {
    const b = budget.trim() ? Number(budget.replace(',', '.')) : null;
    if (b != null && !Number.isFinite(b)) { setErr('Escribe el presupuesto en euros, p. ej. 60.'); return; }
    if (await set({ allergies, budget: b })) onClose();
  };
  const tg = { flexWrap: 'wrap', '& .MuiToggleButton-root': { borderRadius: '999px !important', px: 1.75 } } as const;
  return (
    <Dialog open={open} onClose={save} fullWidth maxWidth="xs" slotProps={{ paper: { sx: { borderRadius: '28px', m: 2, width: 'calc(100% - 32px)' } } }}>
      <DialogTitle>Tu menú semanal</DialogTitle>
      <DialogContent>
        <Stack spacing={2.5}>
          <Box>
            <Typography sx={{ mb: 1 }}>Personas</Typography>
            <ToggleButtonGroup exclusive size="small" value={p.people} sx={tg} onChange={(_, n) => n && set({ people: n })}>
              {[1, 2, 3, 4].map((n) => <ToggleButton key={n} value={n}>{n}</ToggleButton>)}
            </ToggleButtonGroup>
          </Box>
          <Box>
            <Typography sx={{ mb: 1 }}>Comidas que planificar</Typography>
            <Stack direction="row" sx={{ flexWrap: 'wrap', gap: 0.75 }}>
              {MEALS.map((m) => {
                const on = p.meals.includes(m.v);
                return <Chip key={m.v} label={m.label} onClick={() => toggleMeal(m.v)} color={on ? 'primary' : 'default'} variant={on ? 'filled' : 'outlined'} />;
              })}
            </Stack>
          </Box>
          <Box>
            <Typography sx={{ mb: 1 }}>Preferencias</Typography>
            <Stack direction="row" sx={{ flexWrap: 'wrap', gap: 0.75 }}>
              {DIETS.map((d) => {
                const on = p.diet[d.k];
                return <Chip key={d.k} label={d.label} onClick={() => set({ diet: { ...p.diet, [d.k]: !on } })} color={on ? 'primary' : 'default'} variant={on ? 'filled' : 'outlined'} />;
              })}
            </Stack>
          </Box>
          <TextField label="Alergias o lo que no comes (opcional)" value={allergies} onChange={(e) => setAllergies(e.target.value)} size="small"
            placeholder="p. ej. frutos secos, kiwi" slotProps={{ htmlInput: { maxLength: 160 } }} />
          <Box>
            <Typography sx={{ mb: 1 }}>Tiempo para cocinar</Typography>
            <ToggleButtonGroup exclusive size="small" value={p.cooking} sx={tg} onChange={(_, c) => c && set({ cooking: c })}>
              <ToggleButton value="rapido">Rápido (≤ 30 min)</ToggleButton>
              <ToggleButton value="normal">Normal</ToggleButton>
            </ToggleButtonGroup>
          </Box>
          <TextField label="Presupuesto (opcional)" value={budget} onChange={(e) => setBudget(e.target.value)} size="small" inputMode="decimal"
            slotProps={{ input: { endAdornment: <InputAdornment position="end">€/semana</InputAdornment> } }} />
          <Typography variant="caption" color="text.secondary" sx={{ mt: -1.5 }}>
            Las calorías salen de tu objetivo de Comida (con sus límites) y de lo que gastas según el reloj; los días de tirada larga o calidad, más hidratos.
            Los cambios valen para el próximo menú.
          </Typography>
          {err && <Alert severity="warning" sx={{ borderRadius: '16px' }}>{err}</Alert>}
          <Divider />
          <Button color="inherit" onClick={async () => { if (await set({ enabled: false })) onClose(); }} sx={{ ...PILL, alignSelf: 'flex-start' }}>
            Desactivar el menú semanal
          </Button>
          <Typography variant="caption" color="text.secondary" sx={{ mt: -1.5 }}>Se oculta; tu último menú y tu lista no se borran.</Typography>
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2.5 }}>
        <Button variant="contained" disableElevation onClick={save} sx={PILL}>Hecho</Button>
      </DialogActions>
    </Dialog>
  );
}

// ------------------------------------------------------------------ una línea de la lista
function LineRow({ l, onOpen, onCheck }: { l: Line; onOpen: () => void; onCheck: (v: boolean) => void }) {
  const p = l.product;
  const off = l.removed || l.skip;
  return (
    <Stack direction="row" spacing={0.5} sx={{ alignItems: 'flex-start', py: 1, opacity: off ? 0.55 : 1 }}>
      <Checkbox checked={l.checked} disabled={off || !p} onChange={(e) => onCheck(e.target.checked)} sx={{ mt: -0.5, ml: -1 }}
        slotProps={{ input: { 'aria-label': `Ya lo tengo: ${l.name}` } }} />
      <ButtonBase onClick={onOpen} sx={{ flex: 1, minWidth: 0, textAlign: 'left', display: 'block', borderRadius: '12px' }}>
        <Typography sx={{ fontWeight: 500, textDecoration: l.checked || l.removed ? 'line-through' : 'none', overflowWrap: 'anywhere' }}>
          {p ? p.name : l.name}
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ overflowWrap: 'anywhere' }}>
          {p ? `${qtyLabel(l)} ${l.byWeight ? '' : fmtLabel(p.fmt)}${unitPrice(p) ? ` · ${unitPrice(p)}` : ''}` : 'Sin producto en el catálogo'}
        </Typography>
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', overflowWrap: 'anywhere' }}>
          Para el menú: {l.also?.length ? [`${l.name} ${amountLabel({ ...l, amount: l.amount - l.also.reduce((a, x) => a + x.amount, 0) })}`,
            ...l.also.map((x) => `${x.name} ${amountLabel({ ...l, amount: x.amount })}`)].join(' + ') : `${l.name} ${amountLabel(l)}`}
          {l.swapped ? ' · elegido por ti' : ''}{l.removed ? ' · quitado' : ''}{l.skip ? ' · ya lo tienes' : ''}
        </Typography>
        {l.warning && <Typography variant="caption" color="warning.main" sx={{ display: 'block' }}>{l.warning}</Typography>}
      </ButtonBase>
      <Stack sx={{ alignItems: 'flex-end', flexShrink: 0 }}>
        <Typography sx={{ fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}>{p ? money(l.cost) : ''}</Typography>
        {p?.url ? (
          <IconButton size="small" href={p.url} target="_blank" rel="noopener noreferrer" aria-label={`Ver ${p.name} en Mercadona`}>
            <OpenInNewRounded fontSize="small" />
          </IconButton>
        ) : (
          <IconButton size="small" href={l.searchUrl} target="_blank" rel="noopener noreferrer" aria-label={`Buscar ${l.name} en Mercadona`}>
            <SearchRounded fontSize="small" />
          </IconButton>
        )}
      </Stack>
    </Stack>
  );
}

function LineDialog({ l, onClose, act }: { l: Line | null; onClose: () => void; act: (p: string, b: unknown) => Promise<ShoppingView> }) {
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const theme = useTheme();
  const full = useMediaQuery(theme.breakpoints.down('sm'));
  useEffect(() => setErr(null), [l?.key]);
  if (!l) return null;
  const run = async (body: Record<string, unknown>, close = true) => {
    setBusy(true); setErr(null);
    try { await act('item', { key: l.key, ...body }); if (close) onClose(); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  const p = l.product;
  return (
    <Dialog open onClose={onClose} fullScreen={full} fullWidth maxWidth="sm" slotProps={{ paper: { sx: { borderRadius: { xs: 0, sm: '28px' }, pt: { xs: 'env(safe-area-inset-top)', sm: 0 }, pb: { xs: 'env(safe-area-inset-bottom)', sm: 0 } } } }}>
      <DialogTitle sx={{ pr: 6 }}>{l.name.charAt(0).toUpperCase() + l.name.slice(1)} · {amountLabel(l)}</DialogTitle>
      <DialogContent>
        <Stack spacing={2}>
          {p ? (
            <Card variant="outlined" sx={{ p: 2, borderRadius: '16px' }}>
              <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>{l.swapped ? 'Elegido por ti' : 'Recomendado'}</Typography>
              <Typography sx={{ fontWeight: 500 }}>{p.name}</Typography>
              <Typography variant="body2" color="text.secondary">
                {qtyLabel(l)} {l.byWeight ? '' : fmtLabel(p.fmt)} · {money(l.cost)}{unitPrice(p) ? ` · ${unitPrice(p)}` : ''}
              </Typography>
              {!!l.leftover && l.leftoverUnit && (
                <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                  Sobra ≈ {l.leftoverUnit === 'ud' ? `${int(l.leftover)} ud` : `${num(l.leftover >= 1000 ? l.leftover / 1000 : l.leftover)} ${l.leftover >= 1000 ? (l.leftoverUnit === 'g' ? 'kg' : 'l') : l.leftoverUnit}`} para otra semana.
                </Typography>
              )}
              {l.approx && <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>Peso aproximado: el precio final puede variar un poco.</Typography>}
              {p.url && <Link href={p.url} target="_blank" rel="noopener noreferrer" variant="body2" sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.5, mt: 1 }}>
                Ver en Mercadona <OpenInNewRounded sx={{ fontSize: 16 }} /></Link>}
            </Card>
          ) : (
            <Alert severity="info" sx={{ borderRadius: '16px' }}>
              No he encontrado un producto que encaje. <Link href={l.searchUrl} target="_blank" rel="noopener noreferrer">Búscalo en Mercadona</Link>.
            </Alert>
          )}
          {l.alternatives.length > 0 && (
            <Box>
              <Typography variant="subtitle2" sx={{ mb: 1 }}>Cambiar por</Typography>
              <Stack spacing={1}>
                {l.alternatives.map((a) => (
                  <ButtonBase key={a.id} disabled={busy} onClick={() => run({ productId: a.id })}
                    sx={{ display: 'flex', gap: 1.5, alignItems: 'center', p: 1.5, borderRadius: '16px', textAlign: 'left',
                      border: '1px solid', borderColor: 'divider', '&:hover': { bgcolor: 'action.hover' } }}>
                    <SwapHorizRounded color="action" />
                    <Box sx={{ flex: 1, minWidth: 0 }}>
                      <Typography variant="body2" sx={{ fontWeight: 500, overflowWrap: 'anywhere' }}>{a.name}</Typography>
                      <Typography variant="caption" color="text.secondary">{qtyLabel(a)} {a.byWeight ? '' : fmtLabel(a.fmt)}{unitPrice(a) ? ` · ${unitPrice(a)}` : ''}</Typography>
                    </Box>
                    <Typography variant="body2" sx={{ fontWeight: 600, flexShrink: 0 }}>{money(a.cost)}</Typography>
                  </ButtonBase>
                ))}
              </Stack>
            </Box>
          )}
          {err && <Alert severity="warning" sx={{ borderRadius: '16px' }}>{err}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2.5, flexWrap: 'wrap', gap: 1 }}>
        {l.swapped && <Button disabled={busy} onClick={() => run({ productId: null })} sx={PILL}>Volver al recomendado</Button>}
        {l.pantry && <Button disabled={busy} onClick={() => run({ need: l.skip })} sx={PILL}>{l.skip ? 'Lo necesito' : 'Ya lo tengo'}</Button>}
        <Button color={l.removed ? 'primary' : 'inherit'} disabled={busy} onClick={() => run({ removed: !l.removed })} sx={PILL}>
          {l.removed ? 'Volver a añadir' : 'Quitar de la lista'}
        </Button>
        <Button variant="contained" disableElevation onClick={onClose} sx={PILL}>Cerrar</Button>
      </DialogActions>
    </Dialog>
  );
}

// ------------------------------------------------------------------ menú y nutrición
function MenuDays({ plan, hide }: { plan: Plan; hide: boolean }) {
  return (
    <Box sx={{ display: 'grid', gap: 1.5, gridTemplateColumns: { xs: 'minmax(0, 1fr)', md: 'repeat(2, minmax(0, 1fr))' } }}>
      {plan.days.map((d) => (
        <Card key={d.date} sx={{ ...CARD_SX }}>
          <Stack direction="row" sx={{ alignItems: 'center', gap: 1, flexWrap: 'wrap', mb: 1 }}>
            <Typography sx={{ fontWeight: 600, textTransform: 'capitalize' }}>{dateLong(toDate(d.date))}</Typography>
            {d.sessions.map((s, i) => (
              <Chip key={i} size="small" icon={['long', 'tempo', 'intervals', 'race'].includes(s.type) ? <BoltRounded /> : undefined}
                label={`${SESSION[s.type] ?? s.title ?? s.type}${s.km ? ` ${num(s.km)} km` : ''}`}
                color={['long', 'tempo', 'intervals', 'race'].includes(s.type) ? 'warning' : 'default'} variant="outlined" />
            ))}
          </Stack>
          {d.focus && <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>{d.focus}</Typography>}
          <Stack spacing={1}>
            {d.meals.map((m, i) => (
              <Box key={i}>
                <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>{MEAL_LABEL[m.meal] ?? m.meal}</Typography>
                <Typography sx={{ overflowWrap: 'anywhere' }}>{m.dish}</Typography>
                <Typography variant="body2" color="text.secondary" sx={{ overflowWrap: 'anywhere' }}>
                  {m.portion}{m.note ? ` · ${m.note}` : ''}
                </Typography>
              </Box>
            ))}
          </Stack>
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
            Por persona, aprox.: {!hide && d.kcal_per_person ? `${int(d.kcal_per_person)} kcal · ` : ''}{int(d.protein_g_per_person)} g de proteína
          </Typography>
        </Card>
      ))}
    </Box>
  );
}

function NutritionCard({ n, hide, people }: { n: Nutrition; hide: boolean; people: number }) {
  const mode = useResolvedMode() as 'light' | 'dark';
  const rows: [string, string][] = [];
  if (!hide && n.kcalDay != null) rows.push(['Energía de lo planificado', `${int(n.kcalDay)} kcal al día`]);
  if (n.proteinDay != null) rows.push(['Proteína', `${int(n.proteinDay)} g al día`]);
  if (n.carbsDay != null) rows.push(['Hidratos', `${int(n.carbsDay)} g al día`]);
  if (n.fatDay != null) rows.push(['Grasa', `${int(n.fatDay)} g al día`]);
  return (
    <Card sx={{ ...CARD_SX, bgcolor: alpha(COLOR[mode], mode === 'dark' ? 0.1 : 0.06) }}>
      <Typography variant="subtitle2" color="text.secondary">Por persona y día{people > 1 ? ` (repartido entre ${people})` : ''}</Typography>
      <Stack spacing={0.75} sx={{ mt: 1 }}>
        {rows.map(([k, val]) => (
          <Stack key={k} direction="row" sx={{ justifyContent: 'space-between', gap: 2 }}>
            <Typography color="text.secondary">{k}</Typography><Typography sx={{ fontWeight: 600, textAlign: 'right' }}>{val}</Typography>
          </Stack>
        ))}
      </Stack>
      <Divider sx={{ my: 1.5 }} />
      {!hide && n.targetMealsKcalDay != null && (
        <Typography variant="body2" sx={{ mb: 0.5 }}>
          Tu referencia para estas comidas: unas {int(n.targetMealsKcalDay)} kcal al día ({Math.round(n.mealsShare * 100)} % de {int(n.targetKcalDay)} kcal; el resto, con lo que piques).
        </Typography>
      )}
      {n.proteinRefG && <Typography variant="body2" sx={{ mb: 0.5 }}>Proteína de referencia para quien entrena: {n.proteinRefG[0]}-{n.proteinRefG[1]} g al día.</Typography>}
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
        Con la nutrición de {n.linesWithData} de {n.lines} productos (los demás no tienen datos fiables).
        {!hide && n.aiKcalDay ? ` La IA lo estima en ~${int(n.aiKcalDay)} kcal y ${int(n.aiProteinDay)} g de proteína.` : ''} Es orientativo, no un consejo médico.
      </Typography>
    </Card>
  );
}

// ------------------------------------------------------------------ portada (apagado) y estados
function Intro({ onEnable }: { onEnable: () => Promise<void> }) {
  const mode = useResolvedMode() as 'light' | 'dark';
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const points = [
    'El coach te propone un menú de 7 días según tu plan: más hidratos antes y después de la tirada larga y las series.',
    'Lo convierte en tu lista de la compra con productos reales de Mercadona, cuánto coger, el precio y el total.',
    'Cambia un producto por otro, quita lo que ya tienes y copia o comparte la lista.',
    'Tú eliges personas, comidas, si es vegetariano, sin lactosa, sin gluten o sin pescado, y un presupuesto.',
  ];
  return (
    <Card sx={{ ...CARD_SX, maxWidth: 640, bgcolor: alpha(COLOR[mode], mode === 'dark' ? 0.12 : 0.07) }}>
      <IconBubble color={COLOR[mode]} size={48}><ShoppingCartRounded /></IconBubble>
      <Typography variant="h5" sx={{ mt: 2 }}>Tu compra de la semana</Typography>
      <Stack component="ul" spacing={1} sx={{ pl: 2.5, my: 2, color: 'text.secondary' }}>
        {points.map((p) => <li key={p}><Typography>{p}</Typography></li>)}
      </Stack>
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 2 }}>
        Cada menú gasta unos 5-8 céntimos de tu IA del mes. Es una propuesta orientativa, no un consejo médico.
      </Typography>
      <Button data-new="shopping" variant="contained" disableElevation size="large" disabled={busy} sx={{ ...PILL, px: 3 }}
        onClick={async () => { setBusy(true); setErr(null); try { await onEnable(); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); } }}>
        Activar el menú semanal
      </Button>
      {err && <Typography color="error" variant="body2" sx={{ mt: 1.5 }}>No se ha podido activar: {err}</Typography>}
    </Card>
  );
}

function Generate({ v, act, again }: { v: ShoppingView; act: (p: string, b: unknown) => Promise<ShoppingView>; again?: boolean }) {
  const [start, setStart] = useState<'today' | 'monday'>(new Date().getDay() >= 4 || new Date().getDay() === 0 ? 'monday' : 'today');
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const p = v.prefs;
  const diet = DIETS.filter((d) => p.diet[d.k]).map((d) => d.label.toLowerCase());
  const go = async () => { setBusy(true); setErr(null); try { await act('generate', { start }); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); } };
  return (
    <Card sx={{ ...CARD_SX }}>
      <Typography sx={{ fontWeight: 600 }}>{again ? 'Preparar otro menú' : 'Prepara tu menú de la semana'}</Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
        {p.people} {p.people === 1 ? 'persona' : 'personas'} · {p.meals.map((m) => MEAL_LABEL[m].toLowerCase()).join(', ')}
        {diet.length ? ` · ${diet.join(', ')}` : ''}{p.budget ? ` · hasta ${money(p.budget)}` : ''}{p.cooking === 'rapido' ? ' · cocina rápida' : ''}
      </Typography>
      <ToggleButtonGroup exclusive size="small" value={start} onChange={(_, s) => s && setStart(s)}
        sx={{ mt: 1.5, flexWrap: 'wrap', '& .MuiToggleButton-root': { borderRadius: '999px !important', px: 1.75 } }}>
        <ToggleButton value="today">Desde hoy</ToggleButton>
        <ToggleButton value="monday">Desde el lunes</ToggleButton>
      </ToggleButtonGroup>
      {err && <Alert severity="warning" sx={{ borderRadius: '16px', mt: 1.5 }}>{err}</Alert>}
      {v.budgetOver && <Alert severity="info" sx={{ borderRadius: '16px', mt: 1.5 }}>Has llegado al tope de IA de este mes: el menú vuelve el día 1.</Alert>}
      <Box>
        <Button data-new="shopping" variant="contained" disableElevation size="large" startIcon={<AutoAwesomeRounded />} onClick={go} disabled={busy || v.budgetOver}
          sx={{ ...PILL, mt: 2, px: 3 }}>{again ? 'Nuevo menú' : 'Preparar mi menú'}</Button>
      </Box>
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>Tarda menos de un minuto. Unos 5-8 céntimos de tu IA.</Typography>
    </Card>
  );
}

// ------------------------------------------------------------------ página
export default function Shopping({ go }: { go: (k: string) => void }) {
  const { view: v, error, act } = useShopping();
  const [settings, setSettings] = useState(false);
  const [tab, setTab] = useState<'lista' | 'menu' | 'nutricion'>('lista');
  const [open, setOpen] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [again, setAgain] = useState(false);
  const lines = useMemo(() => (v?.list?.groups ?? []).flatMap((g) => g.items), [v]);
  const line = lines.find((l) => l.key === open) ?? null;
  if (error && !v) return <Alert severity="warning" sx={{ borderRadius: '16px' }}>{error}</Alert>;
  if (!v) return <Box sx={{ py: 6, display: 'grid', placeItems: 'center' }}><CircularProgress /></Box>;
  const back = (
    <Button size="small" startIcon={<ChevronLeftRounded />} onClick={() => go('comida')} sx={{ ...PILL, mb: 1, ml: -1 }}>Comida</Button>
  );
  const header = <PageHeader title="Menú y compra" subtitle="Tu semana de comidas y la lista del súper" />;
  const attribution = (
    <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 3 }}>
      {v.attribution.products} · Precios del {v.catalog.date ? new Intl.DateTimeFormat('es-ES').format(toDate(v.catalog.date)) : '–'}, CP {v.catalog.postcode}
      {' · '}{v.attribution.nutrition}. {v.attribution.allergy}
    </Typography>
  );
  if (!v.prefs.enabled) {
    return (
      <Box>
        {back}{header}
        <Intro onEnable={async () => { await act('prefs', { enabled: true }); setSettings(true); }} />
        <SettingsDialog open={settings} onClose={() => setSettings(false)} v={v} act={act} />
      </Box>
    );
  }
  const { plan, list, nutrition, job } = v;
  const hide = v.hideCalories;
  const copy = async () => {
    if (!v.text) return;
    try { await navigator.clipboard.writeText(v.text); setToast('Lista copiada'); } catch { setToast('No he podido copiar la lista'); }
  };
  const share = async () => {
    if (!v.text) return;
    try { await navigator.share({ title: 'Lista de la compra', text: v.text }); } catch { /* cancelado */ }
  };
  const canShare = typeof navigator !== 'undefined' && 'share' in navigator;
  const running = job?.status === 'running';
  return (
    <Box>
      {back}
      <PageHeader title="Menú y compra" subtitle="Tu semana de comidas y la lista del súper"
        action={<IconButton aria-label="Ajustes del menú semanal" onClick={() => setSettings(true)} sx={{ alignSelf: { xs: 'flex-start', sm: 'auto' } }}><TuneRounded /></IconButton>} />
      {!v.catalog.available && <Alert severity="info" sx={{ borderRadius: '16px', mb: 2 }}>El catálogo de productos no está disponible ahora: verás el menú, pero la lista sin precios.</Alert>}
      {running && (
        <Card sx={{ ...CARD_SX, mb: 2 }}>
          <Typography sx={{ fontWeight: 600 }}>Preparando tu menú…</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>El coach mira tu plan y tu objetivo. Tarda menos de un minuto; puedes salir y volver.</Typography>
          <LinearProgress sx={{ borderRadius: 4 }} />
        </Card>
      )}
      {job?.status === 'error' && !running && <Alert severity="warning" sx={{ borderRadius: '16px', mb: 2 }}>{job.error ?? 'No se ha podido preparar el menú.'}</Alert>}
      {!plan && !running && <Generate v={v} act={act} />}
      {plan && list && (
        <>
          <Card sx={{ ...CARD_SX, mb: 2 }}>
            <Stack direction="row" sx={{ justifyContent: 'space-between', alignItems: 'flex-start', gap: 2, flexWrap: 'wrap' }}>
              <Box sx={{ minWidth: 0 }}>
                <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>
                  Semana del {dShort(plan.start)} al {dShort(plan.end)} · {plan.people} {plan.people === 1 ? 'persona' : 'personas'}
                </Typography>
                <Typography data-new="shopping" variant="h4" component="p" sx={{ fontWeight: 600, fontSize: { xs: 30, sm: 36 } }}>{money(list.total)}</Typography>
                <Typography variant="body2" color="text.secondary">
                  {list.items} productos{list.checkedTotal ? ` · en el carro ${money(list.checkedTotal)}` : ''}{list.unmatched ? ` · ${list.unmatched} sin producto` : ''}
                </Typography>
                {list.usedTotal > 0 && list.usedTotal < list.total - 0.5 && (
                  <Typography variant="body2" color="text.secondary">
                    El menú usa unos {money(list.usedTotal)} esta semana; lo demás (arroz, aceite, frutos secos…) te dura para otras.
                  </Typography>
                )}
              </Box>
              <Stack direction="row" spacing={1}>
                <Button variant="outlined" startIcon={<ContentCopyRounded />} onClick={copy} sx={PILL}>Copiar</Button>
                {canShare && <IconButton aria-label="Compartir la lista" onClick={share}><IosShareRounded /></IconButton>}
              </Stack>
            </Stack>
            {list.budget && (list.budget.over ? (
              <Alert severity="warning" sx={{ borderRadius: '16px', mt: 1.5 }}>
                Te pasas {money(list.total - list.budget.target)} de tu presupuesto ({money(list.budget.target)}).
                {list.budget.mode === 'ahorro' ? ' Ya he elegido lo más barato.' : ''} Lo que más pesa: {list.budget.biggest.map((b) => `${b.name} (${money(b.cost)})`).join(', ')}.
                Puedes cambiar o quitar productos, o pedir un menú nuevo.
              </Alert>
            ) : (
              <Typography variant="body2" sx={{ mt: 1, color: 'success.main' }}>
                Dentro de tu presupuesto ({money(list.budget.target)}){list.budget.mode === 'ahorro' ? ', eligiendo lo más barato' : ''}.
              </Typography>
            ))}
            <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>{plan.summary}</Typography>
          </Card>
          {plan.warnings?.length > 0 && (
            <Alert severity="info" sx={{ borderRadius: '16px', mb: 2 }}>{plan.warnings.join(' ')}</Alert>
          )}
          <ToggleButtonGroup exclusive fullWidth value={tab} onChange={(_, t) => t && setTab(t)} size="small"
            sx={{ mb: 2, maxWidth: 480, '& .MuiToggleButton-root': { borderRadius: '999px !important', border: 0, py: 1, fontWeight: 600 },
              bgcolor: 'color-mix(in srgb, var(--mui-palette-text-primary) 6%, transparent)', borderRadius: 999, p: 0.5,
              '& .Mui-selected': { bgcolor: 'background.paper !important', boxShadow: '0 1px 3px rgba(0,0,0,.12)' } }}>
            <ToggleButton value="lista">Lista</ToggleButton>
            <ToggleButton value="menu">Menú</ToggleButton>
            <ToggleButton value="nutricion">Nutrición</ToggleButton>
          </ToggleButtonGroup>

          {tab === 'lista' && (
            <Stack spacing={2}>
              {list.groups.map((g) => (
                <Card key={g.aisle} sx={{ ...CARD_SX, py: { xs: 1.5, sm: 2 } }}>
                  <Typography variant="subtitle2" color="text.secondary" sx={{ fontWeight: 600 }}>{g.aisle}</Typography>
                  {g.aisle.startsWith('Despensa') && (
                    <Typography variant="caption" color="text.secondary">No cuenta en el total. Toca el que necesites y pulsa «Lo necesito».</Typography>
                  )}
                  {g.items.map((l, i) => (
                    <Box key={l.key}>
                      {i > 0 && <Divider />}
                      <LineRow l={l} onOpen={() => setOpen(l.key)} onCheck={(c) => act('item', { key: l.key, checked: c }).catch((e) => setToast((e as Error).message))} />
                    </Box>
                  ))}
                </Card>
              ))}
              {list.checkedTotal > 0 && (
                <Button color="inherit" onClick={() => act('item', { action: 'uncheck-all' })} sx={{ ...PILL, alignSelf: 'flex-start' }}>Desmarcar todo</Button>
              )}
            </Stack>
          )}
          {tab === 'menu' && (
            <>
              <MenuDays plan={plan} hide={hide} />
              {plan.tips?.length > 0 && (
                <>
                  <SectionTitle>Para organizarte</SectionTitle>
                  <Stack component="ul" spacing={0.75} sx={{ pl: 2.5, m: 0 }}>
                    {plan.tips.map((t) => <li key={t}><Typography>{t}</Typography></li>)}
                  </Stack>
                </>
              )}
            </>
          )}
          {tab === 'nutricion' && nutrition && <NutritionCard n={nutrition} hide={hide} people={plan.people} />}

          <Box sx={{ mt: 3 }}>
            {again ? <Generate v={v} act={async (p, b) => { const r = await act(p, b); setAgain(false); return r; }} again /> : (
              <Button variant="outlined" startIcon={<AutoAwesomeRounded />} onClick={() => setAgain(true)} disabled={running} sx={PILL}>Nuevo menú</Button>
            )}
          </Box>
        </>
      )}
      {attribution}
      <SettingsDialog open={settings} onClose={() => setSettings(false)} v={v} act={act} />
      <LineDialog l={line} onClose={() => setOpen(null)} act={act} />
      <Snackbar open={!!toast} autoHideDuration={2500} onClose={() => setToast(null)} message={toast} />
    </Box>
  );
}

/** Tarjeta en la página de Comida que lleva al menú semanal (siempre visible: es la puerta de entrada). */
export function ShoppingEntryCard({ go }: { go: (k: string) => void }) {
  const mode = useResolvedMode() as 'light' | 'dark';
  return (
    <ButtonBase onClick={() => go('compra')} sx={{ display: 'block', width: '100%', textAlign: 'left', borderRadius: '28px' }}>
      <Card data-new="shopping" sx={{ ...CARD_SX, display: 'flex', gap: 2, alignItems: 'center', bgcolor: alpha(COLOR[mode], mode === 'dark' ? 0.1 : 0.06) }}>
        <IconBubble color={COLOR[mode]}><ShoppingCartRounded /></IconBubble>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography sx={{ fontWeight: 600 }}>Plan de comidas y compra semanal</Typography>
          <Typography variant="body2" color="text.secondary">Un menú para tu semana de entreno y la lista del súper con precios.</Typography>
        </Box>
        <ChevronLeftRounded sx={{ transform: 'rotate(180deg)', color: 'text.secondary' }} />
      </Card>
    </ButtonBase>
  );
}
