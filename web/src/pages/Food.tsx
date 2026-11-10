// Comida: apuntas lo que comes con una foto (o escribiéndolo) y la IA estima alimentos, gramos, calorías y macros.
// Se compara con lo que gastas según Garmin. Módulo opcional (apagado hasta activarlo), con "Ocultar calorías".
// La foto se reduce en el navegador (~1024 px, JPEG) y NO se guarda: la IA la analiza y solo quedan los datos.
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import Chip from '@mui/material/Chip';
import CircularProgress from '@mui/material/CircularProgress';
import Dialog from '@mui/material/Dialog';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Divider from '@mui/material/Divider';
import FormControlLabel from '@mui/material/FormControlLabel';
import IconButton from '@mui/material/IconButton';
import InputAdornment from '@mui/material/InputAdornment';
import LinearProgress from '@mui/material/LinearProgress';
import Stack from '@mui/material/Stack';
import Switch from '@mui/material/Switch';
import TextField from '@mui/material/TextField';
import ToggleButton from '@mui/material/ToggleButton';
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup';
import Typography from '@mui/material/Typography';
import useMediaQuery from '@mui/material/useMediaQuery';
import { alpha, useTheme } from '@mui/material/styles';
import { BarChart } from '@mui/x-charts/BarChart';
import { LineChart } from '@mui/x-charts/LineChart';
import AddAPhotoRounded from '@mui/icons-material/AddAPhotoRounded';
import PhotoLibraryRounded from '@mui/icons-material/PhotoLibraryRounded';
import RestaurantRounded from '@mui/icons-material/RestaurantRounded';
import ReplayRounded from '@mui/icons-material/ReplayRounded';
import CloseRounded from '@mui/icons-material/CloseRounded';
import TuneRounded from '@mui/icons-material/TuneRounded';
import StarRounded from '@mui/icons-material/StarRounded';
import StarBorderRounded from '@mui/icons-material/StarBorderRounded';
import DeleteOutlineRounded from '@mui/icons-material/DeleteOutlineRounded';
import AddRounded from '@mui/icons-material/AddRounded';
import ChevronLeftRounded from '@mui/icons-material/ChevronLeftRounded';
import ChevronRightRounded from '@mui/icons-material/ChevronRightRounded';
import AutoAwesomeRounded from '@mui/icons-material/AutoAwesomeRounded';
import LockOutlined from '@mui/icons-material/LockOutlined';
import BoltRounded from '@mui/icons-material/BoltRounded';
import { call } from '../account';
import { isoLocal, toDate, type GarminData, type Range } from '../data';
import { dateLong, dateShort, dec1, int } from '../format';
import { bandAxis, timeAxis, yClean } from '../charts';
import { useResolvedMode } from '../theme';
import { CARD_SX, ChartCard, IconBubble, PageHeader, RangeToggle, SectionTitle, chartSx } from '../ui';
import { ShoppingEntryCard } from './Shopping';

// ------------------------------------------------------------------ tipos (los manda /api/food)
export type Meal = 'desayuno' | 'comida' | 'merienda' | 'cena' | 'picoteo';
export interface FoodItem {
  id?: string; name: string; portion?: string; grams?: number; kcal?: number;
  protein?: number; carbs?: number; fat?: number; fiber?: number; sugar?: number; satFat?: number; sodium?: number;
}
interface Totals { kcal?: number; protein: number; carbs: number; fat: number; fiber: number }
export interface FoodEntry {
  id: string; date: string; time: string; meal: Meal; title: string; note: string; text: string; fromPhoto: boolean;
  status: 'ok' | 'manual' | 'error'; source: 'ai' | 'manual' | 'repeat'; items: FoodItem[]; totals: Totals;
  confidence?: 'alta' | 'media' | 'baja'; assumptions?: string[]; unclear?: string | null; fav?: boolean; edited?: boolean;
}
interface DayRow { d: string; intakeKcal?: number | null; burnedKcal?: number | null; balanceKcal?: number | null;
  protein?: number | null; carbs?: number | null; fat?: number | null; fiber?: number | null; entries: number; partial: boolean }
interface Period { loggedDays: number; intakeKcalAvg?: number | null; burnedKcalAvg?: number | null; balanceKcalAvg?: number | null;
  proteinAvg?: number | null; carbsAvg?: number | null; fatAvg?: number | null; fiberAvg?: number | null; bmrKcal?: number | null; days?: DayRow[] }
interface Goal { mode: 'maintain' | 'lose' | 'gain'; pace: 'suave' | 'moderado' }
export interface FoodView {
  prefs: { enabled: boolean; hideCalories: boolean; goal: Goal | null };
  entries: FoodEntry[]; today: DayRow & { burnedActiveKcal?: number | null }; week: Period; month: Period; hasBurned: boolean;
  goal: (Goal & { targetKcal?: number; rangeKcal?: number[]; deltaKcal?: number; limited: boolean }) | null;
  protein: { weightKg: number; weightDate: string; gPerKgAvg7?: number | null; gPerKgToday?: number | null; refGPerKg: number[]; refG: number[] } | null;
  weights: { d: string; kg: number }[]; fuel: { when: string; session: string; text: string } | null;
  favorites: { id: string; title: string; meal: Meal; fav: boolean; totals: Totals; date: string }[];
  note: string; budget: { over: boolean }; entry?: FoodEntry;
}

const MEALS: { v: Meal; label: string }[] = [
  { v: 'desayuno', label: 'Desayuno' }, { v: 'comida', label: 'Comida' }, { v: 'merienda', label: 'Merienda' },
  { v: 'cena', label: 'Cena' }, { v: 'picoteo', label: 'Picoteo' },
];
const MEAL_LABEL = Object.fromEntries(MEALS.map((m) => [m.v, m.label])) as Record<Meal, string>;
const MEAL_ORDER: Record<Meal, number> = { desayuno: 0, picoteo: 1, comida: 2, merienda: 3, cena: 4 };
type Mode = 'light' | 'dark';
const COL = {
  intake: { light: '#00838F', dark: '#78D9EC' }, burned: { light: '#188038', dark: '#81C995' },
  protein: { light: '#5B5BD6', dark: '#AFADFF' }, carbs: { light: '#E8710A', dark: '#FCAD70' },
  fat: { light: '#1A73E8', dark: '#8AB4F8' }, fiber: { light: '#188038', dark: '#81C995' },
};
const PILL = { borderRadius: 999 } as const;
/** Hasta 2 líneas y después "…" (sin cortar una sola línea a lo ancho). */
const CLAMP2 = { display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden', overflowWrap: 'anywhere' } as const;
// En móvil ocupa toda la pantalla: deja sitio a la hora/batería arriba y a la barra de inicio abajo.
const DIALOG_PAPER = { borderRadius: { xs: 0, sm: '28px' }, pt: { xs: 'env(safe-area-inset-top)', sm: 0 }, pb: { xs: 'env(safe-area-inset-bottom)', sm: 0 } } as const;

/** Tipo de comida por la hora (horarios de España); igual que en el servidor. */
export function defaultMeal(d = new Date()): Meal {
  const t = d.getHours() * 60 + d.getMinutes();
  if (t >= 300 && t < 660) return 'desayuno';
  if (t >= 780 && t < 990) return 'comida';
  if (t >= 990 && t < 1200) return 'merienda';
  if (t >= 1200) return 'cena';
  return 'picoteo';
}
const hhmm = (d = new Date()) => `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
const g1 = (v?: number | null) => (v == null ? '–' : `${dec1(Math.round(v * 10) / 10)} g`);
const kc = (v?: number | null) => (v == null ? '–' : `${int(v)} kcal`);

// ------------------------------------------------------------------ foto: se reduce en el navegador
/** Lado largo 1024 px y JPEG 0,8 (baja la calidad si aún pesa mucho). Devuelve un data URL. */
async function compressPhoto(file: File): Promise<string> {
  const max = 1024;
  let src: CanvasImageSource, w: number, h: number;
  try {
    const bmp = await createImageBitmap(file, { imageOrientation: 'from-image' });
    src = bmp; w = bmp.width; h = bmp.height;
  } catch {
    const url = URL.createObjectURL(file);
    try {
      const img = await new Promise<HTMLImageElement>((ok, ko) => { const i = new Image(); i.onload = () => ok(i); i.onerror = ko; i.src = url; });
      src = img; w = img.naturalWidth; h = img.naturalHeight;
    } catch { throw new Error('No he podido leer esta foto. Prueba con otra (JPEG o PNG).'); } finally { URL.revokeObjectURL(url); }
  }
  const s = Math.min(1, max / Math.max(w, h));
  const canvas = document.createElement('canvas');
  canvas.width = Math.round(w * s); canvas.height = Math.round(h * s);
  canvas.getContext('2d')!.drawImage(src, 0, 0, canvas.width, canvas.height);
  let q = 0.8, out = canvas.toDataURL('image/jpeg', q);
  while (out.length > 1_400_000 && q > 0.35) { q -= 0.15; out = canvas.toDataURL('image/jpeg', q); }
  return out;
}

/** Botones "Hacer foto" y "Galería" con la vista previa (solo en esta pantalla: no se guarda). */
function PhotoPicker({ photo, onPhoto, onError }: { photo: string | null; onPhoto: (p: string | null) => void; onError: (m: string) => void }) {
  const cam = useRef<HTMLInputElement>(null), gal = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const pick = async (f?: File | null) => {
    if (!f) return;
    setBusy(true);
    try { onPhoto(await compressPhoto(f)); } catch (e) { onError((e as Error).message); } finally { setBusy(false); }
  };
  const input = (ref: typeof cam, capture: boolean) => (
    <input ref={ref} type="file" accept="image/*" hidden {...(capture ? { capture: 'environment' } : {})}
      onChange={(e) => { pick(e.target.files?.[0]); e.target.value = ''; }} />
  );
  if (photo) {
    return (
      <Box sx={{ position: 'relative', borderRadius: '20px', overflow: 'hidden', bgcolor: 'action.hover' }}>
        <Box component="img" src={photo} alt="Tu comida" sx={{ display: 'block', width: '100%', maxHeight: 280, objectFit: 'cover' }} />
        <IconButton aria-label="Quitar la foto" onClick={() => onPhoto(null)}
          sx={{ position: 'absolute', top: 8, right: 8, bgcolor: 'rgba(0,0,0,.55)', color: '#fff', '&:hover': { bgcolor: 'rgba(0,0,0,.7)' } }}>
          <CloseRounded />
        </IconButton>
      </Box>
    );
  }
  return (
    <Stack direction="row" spacing={1}>
      {input(cam, true)}{input(gal, false)}
      <Button fullWidth variant="contained" disableElevation startIcon={busy ? <CircularProgress size={18} color="inherit" /> : <AddAPhotoRounded />}
        disabled={busy} onClick={() => cam.current?.click()} sx={{ ...PILL, py: 1.4 }}>Hacer foto</Button>
      <Button fullWidth variant="outlined" startIcon={<PhotoLibraryRounded />} disabled={busy} onClick={() => gal.current?.click()}
        sx={{ ...PILL, py: 1.4 }}>Galería</Button>
    </Stack>
  );
}

// ------------------------------------------------------------------ datos
const FOOD_ON = 'gs-food-on';

export function useFood() {
  const [view, setView] = useState<FoodView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const remember = (x: FoodView) => { try { localStorage.setItem(FOOD_ON, x.prefs.enabled ? '1' : '0'); } catch { /* sin almacenamiento */ } };
  const load = useCallback(async () => {
    try { const x = await call<FoodView>('./api/food'); remember(x); setView(x); setError(null); } catch (e) { setError((e as Error).message); }
  }, []);
  useEffect(() => { load(); }, [load]);
  /** POST a /api/food/...: la respuesta trae la vista completa. Lanza el Error del servidor. */
  const act = useCallback(async (path: string, body: unknown) => {
    const v = await call<FoodView>(`./api/food/${path}`, body);
    remember(v);
    setView(v);
    return v;
  }, []);
  return { view, error, load, act };
}

// ------------------------------------------------------------------ piezas
function MealChips({ value, onChange }: { value: Meal; onChange: (m: Meal) => void }) {
  return (
    <Stack direction="row" sx={{ flexWrap: 'wrap', gap: 0.75 }}>
      {MEALS.map((m) => (
        <Chip key={m.v} label={m.label} onClick={() => onChange(m.v)} color={m.v === value ? 'primary' : 'default'}
          variant={m.v === value ? 'filled' : 'outlined'} sx={{ fontWeight: m.v === value ? 600 : 400 }} />
      ))}
    </Stack>
  );
}

function MacroBar({ label, grams, kcalShare, color, extra }: { label: string; grams?: number | null; kcalShare?: number | null; color: string; extra?: ReactNode }) {
  return (
    <Box>
      <Stack direction="row" sx={{ justifyContent: 'space-between', alignItems: 'baseline' }}>
        <Typography variant="body2" sx={{ fontWeight: 500 }}>{label}</Typography>
        <Typography variant="body2" color="text.secondary">{g1(grams)}{kcalShare != null ? ` · ${Math.round(kcalShare)} %` : ''}</Typography>
      </Stack>
      <LinearProgress variant="determinate" value={Math.min(100, kcalShare ?? 0)}
        sx={{ mt: 0.5, height: 8, borderRadius: 999, bgcolor: alpha(color, 0.15), '& .MuiLinearProgress-bar': { borderRadius: 999, bgcolor: color } }} />
      {extra}
    </Box>
  );
}

/** Reparto de las kcal entre proteína, hidratos y grasa (4/4/9). */
function shares(t: { protein?: number | null; carbs?: number | null; fat?: number | null }) {
  const p = (t.protein ?? 0) * 4, c = (t.carbs ?? 0) * 4, f = (t.fat ?? 0) * 9, sum = p + c + f;
  return sum ? { protein: (p / sum) * 100, carbs: (c / sum) * 100, fat: (f / sum) * 100 } : { protein: null, carbs: null, fat: null };
}

function TodayCard({ v, mode, day }: { v: FoodView; mode: Mode; day: DayRow }) {
  const hide = v.prefs.hideCalories;
  const isToday = day.d === v.today.d;
  const sh = shares(day);
  const intake = day.intakeKcal ?? 0;
  const burned = day.burnedKcal;
  const pct = burned ? Math.min(100, (intake / burned) * 100) : 0;
  const prot = v.protein;
  const gkg = prot && day.protein ? day.protein / prot.weightKg : null;
  return (
    <Card sx={{ ...CARD_SX, minWidth: 0 }}>
      <Typography variant="subtitle1">{isToday ? 'Hoy' : dateLong(toDate(day.d))}</Typography>
      {!hide && (
        <Box sx={{ mt: 1.5 }}>
          <Stack direction="row" sx={{ flexWrap: 'wrap', columnGap: 3, rowGap: 1 }}>
            <Box>
              <Typography variant="caption" color="text.secondary">Comido</Typography>
              <Typography sx={{ fontSize: 30, fontWeight: 500, lineHeight: 1.1, color: COL.intake[mode] }}>{int(intake)}<Box component="span" sx={{ fontSize: 14, color: 'text.secondary', ml: 0.5 }}>kcal</Box></Typography>
            </Box>
            <Box>
              <Typography variant="caption" color="text.secondary">{isToday ? 'Gastado (día completo, previsto)' : 'Gastado'}</Typography>
              <Typography sx={{ fontSize: 30, fontWeight: 500, lineHeight: 1.1, color: COL.burned[mode] }}>{burned != null ? int(burned) : '–'}<Box component="span" sx={{ fontSize: 14, color: 'text.secondary', ml: 0.5 }}>kcal</Box></Typography>
            </Box>
            {burned != null && day.entries > 0 && (
              <Box>
                <Typography variant="caption" color="text.secondary">Diferencia</Typography>
                <Typography sx={{ fontSize: 30, fontWeight: 500, lineHeight: 1.1 }}>{intake - burned > 0 ? '+' : ''}{int(intake - burned)}<Box component="span" sx={{ fontSize: 14, color: 'text.secondary', ml: 0.5 }}>kcal</Box></Typography>
              </Box>
            )}
          </Stack>
          {burned != null && (
            <LinearProgress variant="determinate" value={pct} sx={{ mt: 1.5, height: 10, borderRadius: 999, bgcolor: alpha(COL.burned[mode], 0.18),
              '& .MuiLinearProgress-bar': { borderRadius: 999, bgcolor: COL.intake[mode] } }} />
          )}
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.75 }}>
            {burned == null ? 'Tu reloj no da las calorías gastadas de este día: aquí ves solo lo que comes.'
              : isToday ? `Gastado = lo que gastas en reposo en un día entero (${int(v.month.bmrKcal)} kcal, tu media) + la actividad de hoy hasta ahora (${int(v.today.burnedActiveKcal)} kcal).`
                : 'Gastado = reposo + actividad, según tu reloj.'}
            {isToday && v.goal?.targetKcal ? ` Tu referencia: unas ${int(v.goal.targetKcal)} kcal.` : ''}
          </Typography>
        </Box>
      )}
      <Stack spacing={1.5} sx={{ mt: 2 }}>
        <MacroBar label="Proteína" grams={day.protein} kcalShare={hide ? null : sh.protein} color={COL.protein[mode]}
          extra={gkg != null && prot ? <Typography variant="caption" color="text.secondary">{dec1(Math.round(gkg * 10) / 10)} g por kg de peso (referencia si entrenas: {dec1(prot.refGPerKg[0])}-{dec1(prot.refGPerKg[1])} g/kg, unos {prot.refG[0]}-{prot.refG[1]} g)</Typography> : undefined} />
        <MacroBar label="Hidratos" grams={day.carbs} kcalShare={hide ? null : sh.carbs} color={COL.carbs[mode]} />
        <MacroBar label="Grasa" grams={day.fat} kcalShare={hide ? null : sh.fat} color={COL.fat[mode]} />
        <Typography variant="body2" color="text.secondary">Fibra: {g1(day.fiber)}</Typography>
      </Stack>
    </Card>
  );
}

function EntryCard({ e, hide, onOpen }: { e: FoodEntry; hide: boolean; onOpen: () => void }) {
  const names = e.items.map((i) => i.name).join(', ');
  return (
    <Card onClick={onOpen} sx={{ ...CARD_SX, py: 2, cursor: 'pointer', '&:hover': { bgcolor: 'action.hover' } }}>
      <Stack direction="row" spacing={1.5} sx={{ alignItems: 'flex-start' }}>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography variant="caption" color="text.secondary">{MEAL_LABEL[e.meal]} · {e.time}{e.fav ? ' · ★' : ''}</Typography>
          <Typography variant="subtitle1" sx={{ lineHeight: 1.3, ...CLAMP2 }}>{e.title || names || 'Sin alimentos'}</Typography>
          {e.title && names && <Typography variant="body2" color="text.secondary" sx={CLAMP2}>{names}</Typography>}
          <Typography variant="body2" sx={{ mt: 0.5 }}>
            {!hide && e.totals.kcal != null && <b>{int(e.totals.kcal)} kcal · </b>}
            P {dec1(e.totals.protein)} g · H {dec1(e.totals.carbs)} g · G {dec1(e.totals.fat)} g
          </Typography>
        </Box>
        {e.source === 'ai' && e.confidence && (
          <Chip size="small" icon={<AutoAwesomeRounded />} label={e.confidence === 'alta' ? 'Fiable' : e.confidence === 'media' ? 'Aprox.' : 'Dudosa'}
            variant="outlined" sx={{ flexShrink: 0 }} />
        )}
      </Stack>
    </Card>
  );
}

// ------------------------------------------------------------------ editar alimentos
type Row = FoodItem & { _orig?: FoodItem };
const NUM_KEYS = ['kcal', 'protein', 'carbs', 'fat', 'fiber', 'sugar', 'satFat', 'sodium'] as const;

function scaleRow(r: Row, grams: number | undefined): Row {
  const o = r._orig;
  if (!o || !o.grams || grams == null) return { ...r, grams };
  const k = grams / o.grams;
  const out: Row = { ...r, grams };
  for (const key of NUM_KEYS) if (o[key] != null) out[key] = Math.round(o[key]! * k * (key === 'kcal' || key === 'sodium' ? 1 : 10)) / (key === 'kcal' || key === 'sodium' ? 1 : 10);
  return out;
}

function NumField({ label, value, onChange, unit, width = 84 }: { label: string; value?: number | null; onChange: (v: number | undefined) => void; unit?: string; width?: number }) {
  const [txt, setTxt] = useState(value == null ? '' : String(value).replace('.', ','));
  useEffect(() => { setTxt(value == null ? '' : String(value).replace('.', ',')); }, [value]);
  return (
    <TextField size="small" label={label} value={txt} sx={{ width }}
      onChange={(e) => setTxt(e.target.value)}
      onBlur={() => { const n = parseFloat(txt.replace(',', '.')); onChange(Number.isFinite(n) && n >= 0 ? n : undefined); }}
      slotProps={{ htmlInput: { inputMode: 'decimal' }, input: unit ? { endAdornment: <InputAdornment position="end">{unit}</InputAdornment> } : undefined }} />
  );
}

function ItemsEditor({ rows, setRows, hide }: { rows: Row[]; setRows: (r: Row[]) => void; hide: boolean }) {
  const set = (i: number, r: Row) => setRows(rows.map((x, j) => (j === i ? r : x)));
  return (
    <Stack spacing={1.5}>
      {rows.map((r, i) => (
        <Box key={r.id ?? `n${i}`} sx={{ p: 1.5, borderRadius: '16px', bgcolor: 'action.hover' }}>
          <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
            <TextField size="small" fullWidth label="Alimento" value={r.name} onChange={(e) => set(i, { ...r, name: e.target.value })} />
            <IconButton aria-label={`Quitar ${r.name}`} onClick={() => setRows(rows.filter((_, j) => j !== i))}><DeleteOutlineRounded /></IconButton>
          </Stack>
          {r.portion && <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>{r.portion}</Typography>}
          <Stack direction="row" sx={{ flexWrap: 'wrap', gap: 1, mt: 1 }}>
            <NumField label="Gramos" value={r.grams} unit="g" width={110} onChange={(g) => set(i, scaleRow(r, g))} />
            {!hide && <NumField label="kcal" value={r.kcal} width={90} onChange={(v) => set(i, { ...r, kcal: v })} />}
            <NumField label="Proteína" value={r.protein} unit="g" onChange={(v) => set(i, { ...r, protein: v })} width={100} />
            <NumField label="Hidratos" value={r.carbs} unit="g" onChange={(v) => set(i, { ...r, carbs: v })} width={100} />
            <NumField label="Grasa" value={r.fat} unit="g" onChange={(v) => set(i, { ...r, fat: v })} width={100} />
            <NumField label="Fibra" value={r.fiber} unit="g" onChange={(v) => set(i, { ...r, fiber: v })} width={92} />
          </Stack>
        </Box>
      ))}
      <Button startIcon={<AddRounded />} onClick={() => setRows([...rows, { name: '', grams: undefined }])} sx={{ ...PILL, alignSelf: 'flex-start' }}>
        Añadir alimento
      </Button>
    </Stack>
  );
}

const toRows = (items: FoodItem[]): Row[] => items.map((i) => ({ ...i, _orig: { ...i } }));
const fromRows = (rows: Row[]) => rows.filter((r) => r.name.trim()).map(({ _orig, ...r }) => r);  // eslint-disable-line @typescript-eslint/no-unused-vars

function useFullScreen() {
  const theme = useTheme();
  return useMediaQuery(theme.breakpoints.down('sm'));
}

// ------------------------------------------------------------------ añadir
function AddDialog({ open, onClose, v, act, onSaved }: {
  open: boolean; onClose: () => void; v: FoodView; act: (p: string, b: unknown) => Promise<FoodView>; onSaved: (e: FoodEntry) => void;
}) {
  const full = useFullScreen();
  const [photo, setPhoto] = useState<string | null>(null);
  const [text, setText] = useState('');
  const [note, setNote] = useState('');
  const [meal, setMeal] = useState<Meal>(defaultMeal());
  const [day, setDay] = useState(isoLocal(new Date()));
  const [time, setTime] = useState(hhmm());
  const [manual, setManual] = useState(false);
  const [rows, setRows] = useState<Row[]>([{ name: '' }]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    if (!open) return;
    const now = new Date();
    setPhoto(null); setText(''); setNote(''); setMeal(defaultMeal(now)); setDay(isoLocal(now)); setTime(hhmm(now));
    setManual(v.budget.over); setRows([{ name: '' }]); setErr(v.budget.over ? 'Has llegado al tope de IA de este mes: apunta los alimentos a mano.' : null);
  }, [open, v.budget.over]);
  const save = async () => {
    setBusy(true); setErr(null);
    try {
      const body = manual ? { analyze: false, items: fromRows(rows), title: text, note, meal, date: day, time }
        : { photo: photo ?? undefined, text, note, meal, date: day, time };
      const out = await act('add', body);
      if (out.entry) onSaved(out.entry);
    } catch (e) {
      const m = (e as Error).message;
      setErr(m);
      if (/tope de IA/.test(m)) setManual(true);
    } finally { setBusy(false); }
  };
  const canSave = manual ? fromRows(rows).length > 0 : !!photo || !!text.trim();
  return (
    <Dialog open={open} onClose={busy ? undefined : onClose} fullScreen={full} fullWidth maxWidth="sm" slotProps={{ paper: { sx: DIALOG_PAPER } }}>
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1, pr: 1 }}>
        <Box sx={{ flex: 1 }}>Añadir comida</Box>
        <IconButton aria-label="Cerrar" onClick={onClose} disabled={busy}><CloseRounded /></IconButton>
      </DialogTitle>
      <DialogContent>
        <Stack spacing={2.25} sx={{ pt: 0.5 }}>
          {!manual && (
            <>
              <PhotoPicker photo={photo} onPhoto={setPhoto} onError={setErr} />
              <TextField label={photo ? 'Qué es (opcional)' : '¿Qué has comido?'} placeholder="Café con leche y tostada con tomate"
                value={text} onChange={(e) => setText(e.target.value)} multiline minRows={photo ? 1 : 2} fullWidth />
            </>
          )}
          {manual && (
            <>
              <TextField label="Nombre (opcional)" placeholder="Desayuno de casa" value={text} onChange={(e) => setText(e.target.value)} fullWidth />
              <ItemsEditor rows={rows} setRows={setRows} hide={v.prefs.hideCalories} />
            </>
          )}
          <TextField label="Nota (opcional)" placeholder="Sin aceite, media ración, con 2 cucharadas de aceite…" value={note}
            onChange={(e) => setNote(e.target.value)} fullWidth />
          <MealChips value={meal} onChange={setMeal} />
          <Stack direction="row" spacing={1}>
            <TextField type="date" label="Día" value={day} onChange={(e) => setDay(e.target.value)} size="small"
              slotProps={{ inputLabel: { shrink: true }, htmlInput: { max: isoLocal(new Date()) } }} sx={{ flex: 1 }} />
            <TextField type="time" label="Hora" value={time} onChange={(e) => setTime(e.target.value)} size="small"
              slotProps={{ inputLabel: { shrink: true } }} sx={{ width: 120 }} />
          </Stack>
          {err && <Alert severity={v.budget.over ? 'info' : 'warning'} sx={{ borderRadius: '16px' }}>{err}</Alert>}
          <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
            <LockOutlined sx={{ fontSize: 18, color: 'text.secondary' }} />
            <Typography variant="caption" color="text.secondary">
              {manual ? 'Sin IA: se guarda lo que pongas.' : 'La foto no se guarda: la IA la analiza y solo quedan los datos. Es una estimación (±20-30 %).'}
            </Typography>
          </Stack>
          <Stack direction={{ xs: 'column-reverse', sm: 'row' }} spacing={1} sx={{ justifyContent: 'flex-end' }}>
            <Button onClick={() => { setManual(!manual); setErr(null); }} disabled={busy || (manual && v.budget.over)} sx={PILL}>
              {manual ? 'Estimar con IA' : 'Apuntar a mano'}
            </Button>
            <Button variant="contained" disableElevation onClick={save} disabled={busy || !canSave} sx={{ ...PILL, px: 3 }}
              startIcon={busy ? <CircularProgress size={18} color="inherit" /> : manual ? undefined : <AutoAwesomeRounded />}>
              {busy ? (manual ? 'Guardando…' : 'Analizando…') : err && !manual ? 'Reintentar' : manual ? 'Guardar' : 'Analizar'}
            </Button>
          </Stack>
        </Stack>
      </DialogContent>
    </Dialog>
  );
}

// ------------------------------------------------------------------ editar una comida
function EditDialog({ entry, onClose, v, act }: { entry: FoodEntry | null; onClose: () => void; v: FoodView; act: (p: string, b: unknown) => Promise<FoodView> }) {
  const full = useFullScreen();
  const [rows, setRows] = useState<Row[]>([]);
  const [title, setTitle] = useState('');
  const [note, setNote] = useState('');
  const [meal, setMeal] = useState<Meal>('comida');
  const [day, setDay] = useState('');
  const [time, setTime] = useState('');
  const [fav, setFav] = useState(false);
  const [photo, setPhoto] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [confirmDel, setConfirmDel] = useState(false);
  useEffect(() => {
    if (!entry) return;
    setRows(toRows(entry.items)); setTitle(entry.title); setNote(entry.note); setMeal(entry.meal); setDay(entry.date);
    setTime(entry.time); setFav(!!entry.fav); setPhoto(null); setErr(null); setConfirmDel(false);
  }, [entry]);
  if (!entry) return null;
  const hide = v.prefs.hideCalories;
  const run = async (what: string, fn: () => Promise<unknown>, close = true) => {
    setBusy(what); setErr(null);
    try { await fn(); if (close) onClose(); } catch (e) { setErr((e as Error).message); } finally { setBusy(null); }
  };
  const save = () => run('save', () => act('update', { id: entry.id, items: fromRows(rows), title, note, meal, date: day, time, fav }));
  const reanalyze = () => run('ai', async () => {
    const out = await act('reanalyze', { id: entry.id, note, photo: photo ?? undefined });
    if (out.entry) { setRows(toRows(out.entry.items)); setTitle(out.entry.title); setPhoto(null); }
  }, false);
  const scaleAll = (k: number) => setRows(rows.map((r) => scaleRow({ ...r, _orig: { ...r } }, r.grams != null ? Math.round(r.grams * k) : undefined)));
  const t = rows.reduce((a, r) => ({ kcal: a.kcal + (r.kcal ?? 0), protein: a.protein + (r.protein ?? 0), carbs: a.carbs + (r.carbs ?? 0), fat: a.fat + (r.fat ?? 0) }),
    { kcal: 0, protein: 0, carbs: 0, fat: 0 });
  return (
    <Dialog open={!!entry} onClose={busy ? undefined : onClose} fullScreen={full} fullWidth maxWidth="sm" slotProps={{ paper: { sx: DIALOG_PAPER } }}>
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 0.5, pr: 1 }}>
        <Box sx={{ flex: 1, minWidth: 0 }}>{MEAL_LABEL[meal]} · {dateShort(toDate(day || entry.date))}</Box>
        <IconButton aria-label={fav ? 'Quitar de favoritas' : 'Marcar como favorita'} onClick={() => setFav(!fav)} sx={{ color: fav ? '#F6AE2D' : 'text.secondary' }}>
          {fav ? <StarRounded /> : <StarBorderRounded />}
        </IconButton>
        <IconButton aria-label="Cerrar" onClick={onClose} disabled={!!busy}><CloseRounded /></IconButton>
      </DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 0.5 }}>
          <TextField label="Nombre" value={title} onChange={(e) => setTitle(e.target.value)} fullWidth size="small" />
          <Typography variant="h6" sx={{ fontSize: 18 }}>
            {!hide && `${int(t.kcal)} kcal · `}P {dec1(Math.round(t.protein * 10) / 10)} g · H {dec1(Math.round(t.carbs * 10) / 10)} g · G {dec1(Math.round(t.fat * 10) / 10)} g
          </Typography>
          {(entry.assumptions?.length || entry.unclear) && (
            <Box sx={{ p: 1.5, borderRadius: '16px', bgcolor: (th) => alpha(th.palette.primary.main, 0.07) }}>
              <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>
                Estimado con IA{entry.confidence ? ` · confianza ${entry.confidence}` : ''}{entry.edited ? ' · editado por ti' : ''}
              </Typography>
              {entry.assumptions?.map((a) => <Typography key={a} variant="body2" color="text.secondary">· {a}</Typography>)}
              {entry.unclear && <Typography variant="body2" color="text.secondary">· {entry.unclear}</Typography>}
            </Box>
          )}
          <Stack direction="row" sx={{ gap: 0.75, flexWrap: 'wrap', alignItems: 'center' }}>
            <Typography variant="body2" color="text.secondary" sx={{ mr: 0.5 }}>Toda la ración:</Typography>
            {[0.5, 0.75, 1.5, 2].map((k) => <Chip key={k} label={k === 0.5 ? '½' : k === 0.75 ? '¾' : `×${String(k).replace('.', ',')}`} onClick={() => scaleAll(k)} variant="outlined" />)}
          </Stack>
          <ItemsEditor rows={rows} setRows={setRows} hide={hide} />
          <Divider />
          <MealChips value={meal} onChange={setMeal} />
          <Stack direction="row" spacing={1}>
            <TextField type="date" label="Día" value={day} onChange={(e) => setDay(e.target.value)} size="small"
              slotProps={{ inputLabel: { shrink: true }, htmlInput: { max: isoLocal(new Date()) } }} sx={{ flex: 1 }} />
            <TextField type="time" label="Hora" value={time} onChange={(e) => setTime(e.target.value)} size="small"
              slotProps={{ inputLabel: { shrink: true } }} sx={{ width: 120 }} />
          </Stack>
          <TextField label="Nota" placeholder="Sin aceite, media ración…" value={note} onChange={(e) => setNote(e.target.value)} fullWidth size="small" />
          {!v.budget.over && (
            <Box sx={{ p: 1.5, borderRadius: '16px', border: 1, borderColor: 'divider' }}>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                Volver a estimar con la IA: usa estos alimentos y tu nota. La foto no se guardó; si quieres que mire otra, añádela.
              </Typography>
              <Stack spacing={1}>
                <PhotoPicker photo={photo} onPhoto={setPhoto} onError={setErr} />
                <Button onClick={reanalyze} disabled={!!busy} variant="outlined" sx={PILL}
                  startIcon={busy === 'ai' ? <CircularProgress size={18} /> : <ReplayRounded />}>
                  {busy === 'ai' ? 'Estimando…' : 'Volver a estimar'}
                </Button>
              </Stack>
            </Box>
          )}
          {err && <Alert severity="warning" sx={{ borderRadius: '16px' }}>{err}</Alert>}
          <Stack direction={{ xs: 'column-reverse', sm: 'row' }} spacing={1} sx={{ justifyContent: 'space-between' }}>
            {confirmDel ? (
              <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
                <Typography variant="body2">¿Borrar esta comida?</Typography>
                <Button color="error" onClick={() => run('del', () => act('delete', { id: entry.id }))} disabled={!!busy} sx={PILL}>Borrar</Button>
                <Button onClick={() => setConfirmDel(false)} sx={PILL}>No</Button>
              </Stack>
            ) : (
              <Button color="error" startIcon={<DeleteOutlineRounded />} onClick={() => setConfirmDel(true)} disabled={!!busy} sx={PILL}>Borrar</Button>
            )}
            <Button variant="contained" disableElevation onClick={save} disabled={!!busy} sx={{ ...PILL, px: 3 }}
              startIcon={busy === 'save' ? <CircularProgress size={18} color="inherit" /> : undefined}>Guardar</Button>
          </Stack>
        </Stack>
      </DialogContent>
    </Dialog>
  );
}

// ------------------------------------------------------------------ repetir una comida
function RepeatDialog({ open, onClose, v, act }: { open: boolean; onClose: () => void; v: FoodView; act: (p: string, b: unknown) => Promise<FoodView> }) {
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const go = async (id: string) => {
    setBusy(id); setErr(null);
    try { await act('repeat', { id, meal: defaultMeal(), time: hhmm(), date: isoLocal(new Date()) }); onClose(); } catch (e) { setErr((e as Error).message); } finally { setBusy(null); }
  };
  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="xs" slotProps={{ paper: { sx: { borderRadius: '28px', m: 2, width: 'calc(100% - 32px)' } } }}>
      <DialogTitle>Repetir una comida</DialogTitle>
      <DialogContent>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>Se apunta ahora, igual que la otra vez y sin gastar IA. Luego puedes cambiarla.</Typography>
        {!v.favorites.length && <Typography color="text.secondary">Aún no hay comidas apuntadas.</Typography>}
        <Stack spacing={1}>
          {v.favorites.map((f) => (
            <Box key={f.id} component="button" onClick={() => go(f.id)} disabled={!!busy}
              sx={{ textAlign: 'left', font: 'inherit', color: 'inherit', border: 1, borderColor: 'divider', borderRadius: '16px', p: 1.5, bgcolor: 'transparent', cursor: 'pointer', '&:hover': { bgcolor: 'action.hover' } }}>
              <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
                {f.fav ? <StarRounded sx={{ color: '#F6AE2D', fontSize: 20 }} /> : <RestaurantRounded sx={{ color: 'text.secondary', fontSize: 20 }} />}
                <Box sx={{ flex: 1, minWidth: 0 }}>
                  <Typography sx={{ fontWeight: 500, ...CLAMP2 }}>{f.title}</Typography>
                  <Typography variant="caption" color="text.secondary">
                    {MEAL_LABEL[f.meal]}{!v.prefs.hideCalories && f.totals.kcal != null ? ` · ${int(f.totals.kcal)} kcal` : ''} · P {dec1(f.totals.protein)} g
                  </Typography>
                </Box>
                {busy === f.id && <CircularProgress size={18} />}
              </Stack>
            </Box>
          ))}
        </Stack>
        {err && <Alert severity="warning" sx={{ mt: 2, borderRadius: '16px' }}>{err}</Alert>}
      </DialogContent>
    </Dialog>
  );
}

// ------------------------------------------------------------------ ajustes
function SettingsDialog({ open, onClose, v, act }: { open: boolean; onClose: () => void; v: FoodView; act: (p: string, b: unknown) => Promise<FoodView> }) {
  const [err, setErr] = useState<string | null>(null);
  const set = async (body: unknown) => { setErr(null); try { await act('prefs', body); } catch (e) { setErr((e as Error).message); } };
  const g = v.prefs.goal;
  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="xs" slotProps={{ paper: { sx: { borderRadius: '28px', m: 2, width: 'calc(100% - 32px)' } } }}>
      <DialogTitle>Ajustes de Comida</DialogTitle>
      <DialogContent>
        <Stack spacing={2.5}>
          <FormControlLabel control={<Switch checked={v.prefs.hideCalories} onChange={(e) => set({ hideCalories: e.target.checked })} />}
            label={<Box><Typography>Ocultar calorías</Typography><Typography variant="caption" color="text.secondary">Ves solo alimentos, raciones y macros.</Typography></Box>} />
          <Box>
            <Typography sx={{ mb: 1 }}>Tu objetivo (opcional)</Typography>
            <ToggleButtonGroup exclusive size="small" value={g?.mode ?? 'none'} sx={{ flexWrap: 'wrap', '& .MuiToggleButton-root': { borderRadius: '999px !important', px: 1.5 } }}
              onChange={(_, m) => m && set({ goal: m === 'none' ? null : { mode: m, pace: g?.pace ?? 'suave' } })}>
              <ToggleButton value="none">Ninguno</ToggleButton>
              <ToggleButton value="maintain">Mantener</ToggleButton>
              <ToggleButton value="lose">Bajar peso</ToggleButton>
              <ToggleButton value="gain">Subir peso</ToggleButton>
            </ToggleButtonGroup>
            {g && g.mode !== 'maintain' && (
              <ToggleButtonGroup exclusive size="small" value={g.pace} sx={{ mt: 1, '& .MuiToggleButton-root': { borderRadius: '999px !important', px: 1.5 } }}
                onChange={(_, p) => p && set({ goal: { mode: g.mode, pace: p } })}>
                <ToggleButton value="suave">Poco a poco</ToggleButton>
                <ToggleButton value="moderado">Moderado</ToggleButton>
              </ToggleButtonGroup>
            )}
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
              Es una referencia orientativa a partir de lo que gastas según tu reloj. Por tu salud y tu entreno, nunca baja más de un 20 % de tu gasto
              ni por debajo de lo que gastas en reposo. Los días de entreno fuerte, come para rendir.
            </Typography>
          </Box>
          <Divider />
          <Button color="inherit" onClick={async () => { await set({ enabled: false }); onClose(); }} sx={{ ...PILL, alignSelf: 'flex-start' }}>
            Desactivar Comida
          </Button>
          <Typography variant="caption" color="text.secondary" sx={{ mt: -1.5 }}>Se oculta y el coach deja de verlo. Lo apuntado no se borra.</Typography>
          {err && <Alert severity="warning" sx={{ borderRadius: '16px' }}>{err}</Alert>}
        </Stack>
      </DialogContent>
    </Dialog>
  );
}

// ------------------------------------------------------------------ portada del módulo (apagado)
function Intro({ onEnable }: { onEnable: () => Promise<void> }) {
  const mode = useResolvedMode() as Mode;
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const points = [
    'Haz una foto de lo que comes (o escríbelo) y la IA estima alimentos, gramos, calorías y macros.',
    'Ves lo que comes frente a lo que gastas según tu reloj, día a día y en tendencia.',
    'Todo se puede corregir. Y si prefieres no ver calorías, las ocultas.',
    'La foto no se guarda: solo los datos, y solo los ves tú.',
  ];
  return (
    <Card sx={{ ...CARD_SX, maxWidth: 640, bgcolor: alpha(COL.intake[mode], mode === 'dark' ? 0.12 : 0.07) }}>
      <IconBubble color={COL.intake[mode]} size={48}><RestaurantRounded /></IconBubble>
      <Typography variant="h5" sx={{ mt: 2 }}>Tu comida, con una foto</Typography>
      <Stack component="ul" spacing={1} sx={{ pl: 2.5, my: 2, color: 'text.secondary' }}>
        {points.map((p) => <li key={p}><Typography>{p}</Typography></li>)}
      </Stack>
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 2 }}>
        Es una estimación aproximada (±20-30 %), no un consejo médico. Cada foto gasta un poco de tu IA del mes (unos 2 céntimos).
      </Typography>
      <Button data-new="food" variant="contained" disableElevation size="large" onClick={async () => { setBusy(true); setErr(null); try { await onEnable(); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); } }}
        disabled={busy} sx={{ ...PILL, px: 3 }}>Activar Comida</Button>
      {err && <Typography color="error" variant="body2" sx={{ mt: 1.5 }}>No se ha podido activar: {err}</Typography>}
    </Card>
  );
}

// ------------------------------------------------------------------ página
export default function Food({ data, go }: { data: GarminData; go: (k: string) => void }) {
  const mode = useResolvedMode() as Mode;
  const { view: v, error, load, act } = useFood();
  // Cuando llegan datos nuevos de Garmin (cada hora o al actualizar), el gasto del día cambia: se vuelve a pedir
  const gen = data.generatedAt;
  const first = useRef(true);
  useEffect(() => { if (first.current) { first.current = false; return; } load(); }, [gen, load]);
  const [add, setAdd] = useState(false);
  const [repeat, setRepeat] = useState(false);
  const [settings, setSettings] = useState(false);
  const [edit, setEdit] = useState<FoodEntry | null>(null);
  const [day, setDay] = useState(isoLocal(new Date()));
  const [range, setRange] = useState<Range>('7d');
  // "Añadir comida" desde la portada
  useEffect(() => {
    const on = () => setAdd(true);
    window.addEventListener('food-add', on);
    try {
      if (window.location.hash === '#comida' && sessionStorage.getItem('food-add')) { sessionStorage.removeItem('food-add'); setAdd(true); }
    } catch { /* sin almacenamiento (modo privado estricto): no pasa nada */ }
    return () => window.removeEventListener('food-add', on);
  }, []);
  const dayEntries = useMemo(() => (v?.entries ?? []).filter((e) => e.date === day)
    .sort((a, b) => a.time.localeCompare(b.time) || MEAL_ORDER[a.meal] - MEAL_ORDER[b.meal]), [v, day]);
  if (error && !v) return <Alert severity="warning" sx={{ borderRadius: '16px' }}>{error}</Alert>;
  if (!v) return <Box sx={{ py: 6, display: 'grid', placeItems: 'center' }}><CircularProgress /></Box>;
  if (!v.prefs.enabled) {
    return (
      <Box>
        <PageHeader title="Comida" subtitle="Lo que comes frente a lo que gastas" />
        <Intro onEnable={async () => { await act('prefs', { enabled: true }); }} />
        <Box sx={{ mt: 2, maxWidth: 640 }}><ShoppingEntryCard go={go} /></Box>
      </Box>
    );
  }
  const hide = v.prefs.hideCalories;
  const rows = (range === '7d' ? v.month.days?.slice(-7) : v.month.days) ?? [];
  const per = range === '7d' ? v.week : v.month;
  const dayRow = v.month.days?.find((r) => r.d === day) ?? { ...v.today, d: day, entries: 0, intakeKcal: null, burnedKcal: null, protein: null, carbs: null, fat: null, fiber: null };
  const shift = (n: number) => { const d = toDate(day); d.setDate(d.getDate() + n); const s = isoLocal(d); if (s <= isoLocal(new Date())) setDay(s); };
  const weights = v.weights ?? [];
  const avgLine = hide
    ? `Media de ${per.loggedDays} días apuntados: proteína ${g1(per.proteinAvg)}, hidratos ${g1(per.carbsAvg)}, grasa ${g1(per.fatAvg)}`
    : per.loggedDays
      ? `Media de ${per.loggedDays} ${per.loggedDays === 1 ? 'día apuntado' : 'días apuntados'}: comes ${kc(per.intakeKcalAvg)}${per.burnedKcalAvg != null ? ` y gastas ${kc(per.burnedKcalAvg)}` : ''}${per.balanceKcalAvg != null ? ` (${per.balanceKcalAvg > 0 ? '+' : ''}${int(per.balanceKcalAvg)} kcal al día)` : ''}`
      : 'Aún no hay días completos apuntados.';
  return (
    <Box>
      <PageHeader title="Comida" subtitle="Lo que comes frente a lo que gastas" />
      <Stack direction="row" spacing={1} sx={{ mb: 2, alignItems: 'center' }}>
        <Button data-new="food" variant="contained" disableElevation size="large" startIcon={<AddAPhotoRounded />} onClick={() => setAdd(true)}
          sx={{ ...PILL, flex: { xs: 1, sm: 'none' }, px: 3, py: 1.5 }}>Añadir comida</Button>
        <Button variant="outlined" size="large" startIcon={<ReplayRounded />} onClick={() => setRepeat(true)} sx={{ ...PILL, py: 1.5 }}>Repetir</Button>
        <IconButton aria-label="Ajustes de Comida" onClick={() => setSettings(true)}><TuneRounded /></IconButton>
      </Stack>
      {v.fuel && (
        <Alert icon={<BoltRounded />} severity="info" sx={{ borderRadius: '16px', mb: 2 }}>{v.fuel.text}</Alert>
      )}
      <Box sx={{ mb: 2 }}><ShoppingEntryCard go={go} /></Box>
      {!v.hasBurned && !hide && (
        <Alert severity="info" sx={{ borderRadius: '16px', mb: 2 }}>Tu reloj aún no nos da las calorías gastadas: de momento ves solo lo que comes.</Alert>
      )}
      <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: 'minmax(0, 1fr)', md: 'repeat(2, minmax(0, 1fr))' }, alignItems: 'start' }}>
        <TodayCard v={v} mode={mode} day={dayRow} />
        <Box>
          <Stack direction="row" sx={{ alignItems: 'center', mb: 1 }}>
            <IconButton aria-label="Día anterior" onClick={() => shift(-1)}><ChevronLeftRounded /></IconButton>
            <Typography sx={{ flex: 1, textAlign: 'center', fontWeight: 500 }}>
              {day === isoLocal(new Date()) ? 'Hoy' : dateLong(toDate(day))}
            </Typography>
            <IconButton aria-label="Día siguiente" onClick={() => shift(1)} disabled={day >= isoLocal(new Date())}><ChevronRightRounded /></IconButton>
          </Stack>
          <Stack spacing={1.25}>
            {dayEntries.map((e) => <EntryCard key={e.id} e={e} hide={hide} onOpen={() => setEdit(e)} />)}
            {!dayEntries.length && (
              <Typography color="text.secondary" sx={{ textAlign: 'center', py: 3 }}>Nada apuntado este día.</Typography>
            )}
          </Stack>
        </Box>
      </Box>

      <SectionTitle>Tendencia</SectionTitle>
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} sx={{ mb: 2, justifyContent: 'space-between', alignItems: { sm: 'center' } }}>
        <Typography color="text.secondary">{avgLine}</Typography>
        <RangeToggle value={range} onChange={setRange} exclude={['90d', '1y', 'all']} />
      </Stack>
      <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: 'minmax(0, 1fr)', lg: weights.length > 1 ? 'minmax(0, 2fr) minmax(0, 1fr)' : 'minmax(0, 1fr)' } }}>
        {hide ? (
          <ChartCard title="Macros por día" subtitle="Gramos de proteína, hidratos y grasa">
            <BarChart height={280} sx={chartSx} grid={{ horizontal: true }} borderRadius={6}
              xAxis={[bandAxis(rows.map((r) => r.d))]} yAxis={[{ ...yClean }]}
              series={[{ data: rows.map((r) => r.protein ?? null), label: 'Proteína', color: COL.protein[mode], stack: 'm', valueFormatter: (x) => g1(x) },
                { data: rows.map((r) => r.carbs ?? null), label: 'Hidratos', color: COL.carbs[mode], stack: 'm', valueFormatter: (x) => g1(x) },
                { data: rows.map((r) => r.fat ?? null), label: 'Grasa', color: COL.fat[mode], stack: 'm', valueFormatter: (x) => g1(x) }]} />
          </ChartCard>
        ) : (
          <ChartCard title="Comido frente a gastado" subtitle={v.hasBurned ? 'kcal cada día · hoy, gasto previsto del día completo' : 'kcal cada día'}>
            <BarChart height={280} sx={chartSx} grid={{ horizontal: true }} borderRadius={6}
              xAxis={[bandAxis(rows.map((r) => r.d))]} yAxis={[{ ...yClean }]}
              series={[{ data: rows.map((r) => r.intakeKcal ?? null), label: 'Comido', color: COL.intake[mode], valueFormatter: (x) => kc(x) },
                ...(v.hasBurned ? [{ data: rows.map((r) => r.burnedKcal ?? null), label: 'Gastado', color: COL.burned[mode], valueFormatter: (x: number | null) => kc(x) }] : [])]} />
          </ChartCard>
        )}
        {weights.length > 1 && (
          <ChartCard title="Peso" subtitle="Lo que apuntas en Garmin Connect (6 meses)">
            <LineChart height={280} sx={chartSx} grid={{ horizontal: true }} hideLegend
              xAxis={[timeAxis(weights.map((w) => toDate(w.d)))]} yAxis={[{ ...yClean }]}
              series={[{ data: weights.map((w) => w.kg), label: 'Peso', color: COL.protein[mode], curve: 'monotoneX', valueFormatter: (x) => `${dec1(x)} kg` }]} />
          </ChartCard>
        )}
      </Box>
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 2 }}>
        {v.note} Las medias cuentan los días completos con algo apuntado: si un día no lo apuntas todo, sale más bajo.
      </Typography>

      <AddDialog open={add} onClose={() => setAdd(false)} v={v} act={act} onSaved={(e) => { setAdd(false); setDay(e.date); setEdit(e); }} />
      <EditDialog entry={edit} onClose={() => setEdit(null)} v={v} act={act} />
      <RepeatDialog open={repeat} onClose={() => setRepeat(false)} v={v} act={act} />
      <SettingsDialog open={settings} onClose={() => setSettings(false)} v={v} act={act} />
    </Box>
  );
}

/** Tarjeta pequeña en Hoy (solo si tienes Comida activada en este navegador): lo comido hoy y un botón para añadir. */
export function FoodTodayCard({ go, mt = 2 }: { go: (k: string) => void; mt?: number }) {
  const mode = useResolvedMode() as Mode;
  const on = (() => { try { return localStorage.getItem(FOOD_ON) === '1'; } catch { return false; } })();
  const [v, setV] = useState<FoodView | null>(null);
  const [loaded, setLoaded] = useState(!on);
  useEffect(() => { if (on) call<FoodView>('./api/food').then(setV).catch(() => setV(null)).finally(() => setLoaded(true)); }, [on]);
  if (!loaded) return null;
  if (!on || !v?.prefs.enabled) {
    // Sin el módulo activado: invitación amable en vez de un hueco vacío
    return (
      <Card onClick={() => go('comida')} sx={{ ...CARD_SX, mt, display: 'flex', gap: 2, alignItems: 'center', cursor: 'pointer' }}>
        <IconBubble color={COL.intake[mode]}><RestaurantRounded /></IconBubble>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography variant="subtitle1">Apunta lo que comes con una foto</Typography>
          <Typography variant="body2" color="text.secondary">
            La IA calcula calorías y proteína y lo compara con lo que gastas. Está apagado hasta que tú lo actives.
          </Typography>
        </Box>
        <Button variant="outlined" sx={{ ...PILL, flexShrink: 0 }} onClick={(e) => { e.stopPropagation(); go('comida'); }}>Probar</Button>
      </Card>
    );
  }
  const t = v.today;
  const hide = v.prefs.hideCalories;
  const addNow = () => { try { sessionStorage.setItem('food-add', '1'); } catch { /* sin almacenamiento */ } go('comida'); };
  return (
    <Card sx={{ ...CARD_SX, mt, display: 'flex', gap: 2, alignItems: 'center', flexWrap: 'wrap' }}>
      <IconBubble color={COL.intake[mode]}><RestaurantRounded /></IconBubble>
      <Box sx={{ flex: 1, minWidth: 160, cursor: 'pointer' }} onClick={() => go('comida')}>
        <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>Comida de hoy</Typography>
        <Typography>
          {!t.entries ? 'Aún no has apuntado nada hoy. Haz una foto de tu próxima comida y listo.'
            : hide ? `Proteína ${g1(t.protein)} · hidratos ${g1(t.carbs)} · grasa ${g1(t.fat)}`
              : `Comido ${kc(t.intakeKcal)}${t.burnedKcal != null ? ` · gastado ${kc(t.burnedKcal)} (previsto)` : ''} · proteína ${g1(t.protein)}`}
        </Typography>
      </Box>
      <Button variant="contained" disableElevation startIcon={<AddAPhotoRounded />} onClick={addNow} sx={PILL}>Añadir</Button>
    </Card>
  );
}
