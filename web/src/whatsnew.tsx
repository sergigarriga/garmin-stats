// Novedades de cada versión: se enseñan UNA vez por persona (se guarda en su cuenta) al entrar tras publicar.
//
// Para anunciar una versión nueva: añade una entrada AL PRINCIPIO de RELEASES con un id nuevo (fecha AAAA-MM-DD,
// o AAAA-MM-DD-2 si hay dos el mismo día), un título y 3-7 novedades. Cada novedad puede llevar `go` (la página a la
// que lleva al tocarla). Quien se da de alta después de la fecha no la ve (para esa persona todo es nuevo).
import { forwardRef, useCallback, useEffect, useState, type ReactElement, type ReactNode } from 'react';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import ButtonBase from '@mui/material/ButtonBase';
import Dialog from '@mui/material/Dialog';
import IconButton from '@mui/material/IconButton';
import Slide from '@mui/material/Slide';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import useMediaQuery from '@mui/material/useMediaQuery';
import { alpha } from '@mui/material/styles';
import type { TransitionProps } from '@mui/material/transitions';
import CloseRounded from '@mui/icons-material/CloseRounded';
import ChevronRightRounded from '@mui/icons-material/ChevronRightRounded';
import BatteryChargingFullRounded from '@mui/icons-material/BatteryChargingFullRounded';
import HealingRounded from '@mui/icons-material/HealingRounded';
import SpeedRounded from '@mui/icons-material/SpeedRounded';
import PoolRounded from '@mui/icons-material/PoolRounded';
import FitnessCenterRounded from '@mui/icons-material/FitnessCenterRounded';
import TaskAltRounded from '@mui/icons-material/TaskAltRounded';
import CalendarMonthRounded from '@mui/icons-material/CalendarMonthRounded';
import AutoAwesomeRounded from '@mui/icons-material/AutoAwesomeRounded';
import NewReleasesRounded from '@mui/icons-material/NewReleasesRounded';
import ScheduleRounded from '@mui/icons-material/ScheduleRounded';
import WbSunnyRounded from '@mui/icons-material/WbSunnyRounded';
import RestaurantRounded from '@mui/icons-material/RestaurantRounded';
import BalanceRounded from '@mui/icons-material/BalanceRounded';
import LockOutlined from '@mui/icons-material/LockOutlined';
import { call, type Me } from './account';
import { useResolvedMode } from './theme';
import { spotlight } from './spotlight';

type Color = { light: string; dark: string };
/** go = página a la que lleva; target = clave data-new del elemento que se resalta allí (ver spotlight.tsx). */
export interface Feature { icon: ReactNode; color: Color; title: string; body: string; go?: string; where?: string; target?: string }
export interface Release { id: string; date: string; title: string; subtitle: string; features: Feature[] }

const C = {
  blue: { light: '#1A73E8', dark: '#8AB4F8' }, teal: { light: '#00838F', dark: '#78D9EC' },
  orange: { light: '#E8710A', dark: '#FCAD70' }, purple: { light: '#9334E6', dark: '#D7AEFB' },
  green: { light: '#188038', dark: '#81C995' }, indigo: { light: '#5B5BD6', dark: '#AFADFF' }, red: { light: '#D93025', dark: '#F28B82' },
};

/** La más reciente primero. */
export const RELEASES: Release[] = [
  {
    id: '2026-11-03-3', date: '2026-11-03', title: 'Tu comida, con una foto', subtitle: 'Lo que comes frente a lo que gastas',
    features: [
      { icon: <RestaurantRounded />, color: C.teal, title: 'Haz una foto y listo', target: 'food', where: 'Salud · Comida', go: 'comida',
        body: 'La IA estima alimentos, gramos, calorías y macros. Puedes corregirlo todo o repetir una comida con un toque.' },
      { icon: <BalanceRounded />, color: C.green, title: 'Comido frente a gastado', target: 'food', where: 'Salud · Comida', go: 'comida',
        body: 'Tu día y tu tendencia frente a lo que gastas según el reloj, con la proteína por kilo y un objetivo opcional.' },
      { icon: <LockOutlined />, color: C.indigo, title: 'Tú decides', where: 'Salud · Comida', go: 'comida',
        body: 'Está apagado hasta que lo activas. La foto no se guarda: solo los datos. Y si quieres, ocultas las calorías.' },
    ],
  },
  {
    id: '2026-11-03-2', date: '2026-11-03', title: 'Tu plan, a tu medida', subtitle: 'Con tu tiempo y con el tiempo que hará',
    features: [
      { icon: <ScheduleRounded />, color: C.blue, title: 'Tu tiempo, día a día', target: 'availability', where: 'Entreno · Plan', go: 'plan',
        body: 'Dile al coach cuánto tienes cada día (hoy 2 h, mañana 45 min) y ajusta la carga para que cada sesión quepa.' },
      { icon: <WbSunnyRounded />, color: C.orange, title: 'El plan mira el tiempo que hará', target: 'weather', where: 'Entreno · Plan', go: 'plan',
        body: 'Elige tu ciudad: con calor, lluvia o viento el coach cambia el día o la hora y te dice la mejor franja para salir.' },
    ],
  },
  {
    id: '2026-11-02-2', date: '2026-11-02', title: 'Ahora somos Runch', subtitle: 'Mismo coach, nombre nuevo',
    features: [
      { icon: <AutoAwesomeRounded />, color: C.orange, title: 'Nuevo nombre: Runch', where: 'Hoy', go: 'hoy',
        body: 'Run + brunch: correr, recuperar y disfrutarlo. Tus datos, tu plan y tu coach siguen exactamente igual.' },
      { icon: <NewReleasesRounded />, color: C.blue, title: 'Si tienes la app instalada', where: 'Menú',
        body: 'El icono de tu pantalla de inicio puede seguir con el nombre antiguo. Bórralo y vuelve a instalarla desde el menú.' },
    ],
  },
  {
    id: '2026-11-02', date: '2026-11-02', title: 'Novedades', subtitle: 'Tu entreno, más a tu medida',
    features: [
      { icon: <BatteryChargingFullRounded />, color: C.blue, title: 'Tu energía de ahora', target: 'energy', where: 'Hoy', go: 'hoy',
        body: 'La Body Battery que tienes en este momento, con la hora del último dato del reloj y tu día hora a hora.' },
      { icon: <HealingRounded />, color: C.teal, title: '¿Cómo te encuentras?', target: 'checkin', where: 'Hoy', go: 'hoy',
        body: 'Apunta tu ánimo, las agujetas y las molestias. Tu coach las tiene en cuenta para el día y el plan.' },
      { icon: <SpeedRounded />, color: C.orange, title: 'Tus ritmos y zonas', target: 'paces', where: 'Entreno · Ritmos', go: 'ritmos',
        body: 'Ritmos de entreno según tu nivel real. El plan y el reloj se actualizan solos cuando mejoras.' },
      { icon: <PoolRounded />, color: C.teal, title: 'Natación', target: 'swim', where: 'Entreno · Ritmos', go: 'ritmos',
        body: 'Tu ritmo umbral por 100 m, zonas, metros por semana y SWOLF. Con un test de 400 + 200 m.' },
      { icon: <FitnessCenterRounded />, color: C.purple, title: 'Gimnasio', target: 'gym', where: 'Entreno · Gimnasio', go: 'gimnasio',
        body: 'Tu 1RM estimado por ejercicio, series por músculo cada semana y tus récords.' },
      { icon: <TaskAltRounded />, color: C.green, title: 'Cómo cumples el plan', target: 'compliance', where: 'Entreno · Plan', go: 'plan',
        body: 'Cada sesión te dice cuánto hiciste frente a lo previsto y si fuiste más rápido o más lento.' },
      { icon: <CalendarMonthRounded />, color: C.indigo, title: 'El plan en tu calendario', target: 'calendar', where: 'Entreno · Plan', go: 'plan',
        body: 'Suscríbete desde Google Calendar, el iPhone u Outlook y verás cada sesión con sus ritmos.' },
    ],
  },
];

export const LATEST = RELEASES[0];
const LOCAL = 'gs-seen-release';

const SlideUp = forwardRef(function SlideUp(props: TransitionProps & { children: ReactElement }, ref: React.Ref<unknown>) {
  return <Slide direction="up" ref={ref} {...props} />;
});

const readLocal = () => { try { return localStorage.getItem(LOCAL); } catch { return null; } };
const writeLocal = (id: string) => { try { localStorage.setItem(LOCAL, id); } catch { /* sin almacenamiento */ } };

const releaseTs = (r: Release) => new Date(`${r.date}T00:00:00`).getTime() / 1000;

/** Versiones que aún no ha visto (la más reciente primero). Quien llegó después de una versión no la ve. */
export function pending(me: Me | null, local: string | null = readLocal()): Release[] {
  if (!me) return [];  // sin cuenta (p. ej. abierta como archivo): no molestar
  const seen = [me.seenRelease ?? '', local ?? ''].sort().pop() ?? '';
  return RELEASES.filter((r) => r.id > seen && !(me.since && me.since >= releaseTs(r) + 86400));
}

/** ¿Hay que enseñarle novedades? Una vez por persona y versión. */
export function shouldShow(me: Me | null, local: string | null = readLocal()): boolean {
  return pending(me, local).length > 0;
}

/** Pantalla de novedades. Se abre sola la primera vez y desde el menú ("Novedades"). */
export function WhatsNew({ me, go, ready }: { me: Me | null; go: (k: string) => void; ready: boolean }) {
  const mode = useResolvedMode();
  const full = useMediaQuery('(max-width:599px)');
  const [open, setOpen] = useState(false);
  const [auto, setAuto] = useState(false);

  useEffect(() => {
    if (ready && shouldShow(me)) { setOpen(true); setAuto(true); }
  }, [ready, me]);
  useEffect(() => {
    const on = () => { setAuto(false); setOpen(true); };
    window.addEventListener('open-whatsnew', on);
    return () => window.removeEventListener('open-whatsnew', on);
  }, []);

  const close = useCallback((f?: Feature) => {
    setOpen(false);
    if (auto) {
      writeLocal(LATEST.id);
      call('./api/whatsnew/seen', { release: LATEST.id }).catch(() => { /* se queda guardado en este dispositivo */ });
    }
    if (f?.go) {
      setTimeout(() => {
        go(f.go!);
        // cuando la página ya está pintada, se baja hasta la novedad y se resalta
        if (f.target) setTimeout(() => spotlight({ target: f.target!, title: f.title, body: f.body }), 450);
      }, 200);
    }
  }, [auto, go]);

  // Al abrirse sola: todas las versiones pendientes juntas (la más reciente manda en la cabecera). Desde el menú: la última.
  const list = auto ? pending(me) : [];
  const r: Release = list.length > 1 ? { ...list[0], features: list.flatMap((x) => x.features) } : LATEST;
  const accent = mode === 'dark' ? '#8AB4F8' : '#0B57D0';
  return (
    <Dialog open={open} onClose={() => close()} fullScreen={full} slots={{ transition: SlideUp }} scroll="paper"
      aria-labelledby="whatsnew-title"
      slotProps={{ paper: { sx: { borderRadius: full ? 0 : '32px', maxWidth: 520, width: '100%', overflow: 'hidden', bgcolor: 'background.default',
        display: 'flex', flexDirection: 'column', maxHeight: full ? '100%' : 'calc(100% - 48px)' } } }}>
      {/* cabecera */}
      <Box sx={{ position: 'relative', flexShrink: 0, px: 3, pt: full ? 'calc(env(safe-area-inset-top) + 40px)' : 5, pb: 3.5, textAlign: 'center',
        background: mode === 'dark'
          ? 'radial-gradient(120% 90% at 50% 0%, rgba(138,180,248,.28), transparent 70%), linear-gradient(180deg, #1B1C1F, var(--mui-palette-background-default))'
          : 'radial-gradient(120% 90% at 50% 0%, rgba(26,115,232,.18), transparent 70%), linear-gradient(180deg, #EEF3FD, var(--mui-palette-background-default))' }}>
        <IconButton onClick={() => close()} aria-label="Cerrar" sx={{ position: 'absolute', top: full ? 'calc(env(safe-area-inset-top) + 8px)' : 12, right: 12, color: 'text.secondary' }}>
          <CloseRounded />
        </IconButton>
        <Box sx={{ width: 64, height: 64, mx: 'auto', mb: 2, borderRadius: '20px', display: 'grid', placeItems: 'center', color: '#fff',
          background: 'conic-gradient(from 200deg, #D93025, #E8710A, #F6AE2D, #188038, #1A73E8, #5B5BD6, #D93025)',
          boxShadow: `0 10px 30px ${alpha(accent, 0.35)}`, '& svg': { fontSize: 32 } }}>
          <AutoAwesomeRounded />
        </Box>
        <Typography variant="overline" sx={{ color: accent, fontWeight: 700, letterSpacing: '0.12em' }}>
          {new Date(`${r.date}T00:00:00`).toLocaleDateString('es-ES', { day: 'numeric', month: 'long', year: 'numeric' })}
        </Typography>
        <Typography id="whatsnew-title" component="h2" sx={{ fontSize: { xs: 30, sm: 34 }, fontWeight: 600, lineHeight: 1.1, letterSpacing: '-0.02em' }}>{r.title}</Typography>
        <Typography color="text.secondary" sx={{ mt: 0.75 }}>{r.subtitle}</Typography>
      </Box>

      {/* novedades */}
      <Box sx={{ flex: 1, overflowY: 'auto', px: { xs: 1.5, sm: 2.5 }, pb: 1 }}>
        <Stack spacing={0.5}>
          {r.features.map((f, i) => {
            const c = f.color[mode];
            return (
              <ButtonBase key={f.title} onClick={() => close(f)} disabled={!f.go}
                sx={{ display: 'flex', alignItems: 'flex-start', gap: 2, p: 1.5, borderRadius: '20px', textAlign: 'left', width: '100%',
                  transition: 'background-color .15s', '&:hover': { bgcolor: alpha(c, 0.08) },
                  animation: open ? `wnIn .45s ${0.08 + i * 0.05}s both cubic-bezier(.2,.8,.2,1)` : 'none',
                  '@keyframes wnIn': { from: { opacity: 0, transform: 'translateY(10px)' }, to: { opacity: 1, transform: 'none' } } }}>
                <Box sx={{ width: 44, height: 44, borderRadius: '14px', flexShrink: 0, display: 'grid', placeItems: 'center', color: c,
                  bgcolor: alpha(c, mode === 'dark' ? 0.18 : 0.12), '& svg': { fontSize: 24 } }}>{f.icon}</Box>
                <Box sx={{ flex: 1, minWidth: 0 }}>
                  <Typography sx={{ fontWeight: 600, fontSize: 16, lineHeight: 1.3 }}>{f.title}</Typography>
                  <Typography variant="body2" color="text.secondary" sx={{ mt: 0.25, lineHeight: 1.45 }}>{f.body}</Typography>
                  {f.where && <Typography variant="caption" sx={{ color: c, fontWeight: 600, display: 'block', mt: 0.5 }}>{f.where}</Typography>}
                </Box>
                {f.go && <ChevronRightRounded sx={{ color: 'text.disabled', alignSelf: 'center', flexShrink: 0 }} />}
              </ButtonBase>
            );
          })}
        </Stack>
      </Box>

      {/* botón */}
      <Box sx={{ flexShrink: 0, px: 3, pt: 1.5, pb: full ? 'calc(env(safe-area-inset-bottom) + 20px)' : 3,
        background: 'linear-gradient(180deg, transparent, var(--mui-palette-background-default) 30%)' }}>
        <Button fullWidth variant="contained" size="large" disableElevation onClick={() => close()}
          sx={{ borderRadius: 999, py: 1.5, fontSize: 16, fontWeight: 600, textTransform: 'none' }}>Continuar</Button>
      </Box>
    </Dialog>
  );
}
