import { useCallback, useEffect, useState, type ReactElement } from 'react';
import GlobalStyles from '@mui/material/GlobalStyles';
import { PullToRefresh, useManualSync } from './sync';
import Alert from '@mui/material/Alert';
import Divider from '@mui/material/Divider';
import GroupAddOutlined from '@mui/icons-material/GroupAddOutlined';
import KeyOutlined from '@mui/icons-material/KeyOutlined';
import PersonRemoveOutlined from '@mui/icons-material/PersonRemoveOutlined';
import { OwnerCtx } from './owner';
import { AdminDialog, DeleteAccountDialog, GarminKeyDialog, useMe, type Me } from './account';
import Onboarding from './pages/Onboarding';
import AutoAwesomeRounded from '@mui/icons-material/AutoAwesomeRounded';
import AppBar from '@mui/material/AppBar';
import Box from '@mui/material/Box';
import Container from '@mui/material/Container';
import IconButton from '@mui/material/IconButton';
import ListItemIcon from '@mui/material/ListItemIcon';
import ListItemText from '@mui/material/ListItemText';
import Menu from '@mui/material/Menu';
import MenuItem from '@mui/material/MenuItem';
import Snackbar from '@mui/material/Snackbar';
import Stack from '@mui/material/Stack';
import Tab from '@mui/material/Tab';
import Tabs from '@mui/material/Tabs';
import Toolbar from '@mui/material/Toolbar';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import useMediaQuery from '@mui/material/useMediaQuery';
import { useColorScheme, useTheme } from '@mui/material/styles';
import HomeRounded from '@mui/icons-material/HomeRounded';
import BedtimeRounded from '@mui/icons-material/BedtimeRounded';
import FavoriteRounded from '@mui/icons-material/FavoriteRounded';
import { Wordmark } from './brand/Wordmark';
import { haptic } from './haptics';
import DirectionsWalkRounded from '@mui/icons-material/DirectionsWalkRounded';
import DirectionsRunRounded from '@mui/icons-material/DirectionsRunRounded';
import InsightsRounded from '@mui/icons-material/InsightsRounded';
import EventNoteRounded from '@mui/icons-material/EventNoteRounded';
import RefreshRounded from '@mui/icons-material/RefreshRounded';
import LightModeOutlined from '@mui/icons-material/LightModeOutlined';
import DarkModeOutlined from '@mui/icons-material/DarkModeOutlined';
import ContrastOutlined from '@mui/icons-material/ContrastOutlined';
import Check from '@mui/icons-material/Check';
import LogoutRounded from '@mui/icons-material/LogoutRounded';
import InstallMobileRounded from '@mui/icons-material/InstallMobileRounded';
import NotificationsActiveOutlined from '@mui/icons-material/NotificationsActiveOutlined';
import Dialog from '@mui/material/Dialog';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Button from '@mui/material/Button';
import { canPromptInstall, enablePush, isIos, isStandalone, onInstallChange, promptInstall } from './pwa';
import { useGarminData, useNow, type GarminData } from './data';
import { relative, time } from './format';
import Today, { TodayDetail, TodayWeek } from './pages/Today';
import Sleep from './pages/Sleep';
import Heart from './pages/Heart';
import Activity from './pages/Activity';
import Training from './pages/Training';
import Insights from './pages/Insights';
import PlanPage from './pages/PlanPage';
import Paces from './pages/Paces';
import Gym from './pages/Gym';
import Food from './pages/Food';
import Shopping from './pages/Shopping';
import SpeedRounded from '@mui/icons-material/SpeedRounded';
import FitnessCenterRounded from '@mui/icons-material/FitnessCenterRounded';
import ActivityDetail from './pages/ActivityDetail';
import Chat from './Chat';
import { LATEST, WhatsNew } from './whatsnew';
import { Spotlight } from './spotlight';
import { WelcomeTour } from './tour';
import NewReleasesOutlined from '@mui/icons-material/NewReleasesOutlined';
import LockRounded from '@mui/icons-material/LockRounded';

type Page = { key: string; label: string; icon: ReactElement; render: (d: GarminData, go: (k: string) => void) => ReactElement };

const PAGES: Page[] = [
  { key: 'hoy', label: 'Hoy', icon: <HomeRounded />, render: (d, go) => <Today data={d} go={go} /> },
  { key: 'dia', label: 'Tu día', icon: <HomeRounded />, render: (d, go) => <TodayDetail data={d} go={go} /> },
  { key: 'semana', label: 'Semana', icon: <HomeRounded />, render: (d, go) => <TodayWeek data={d} go={go} /> },
  { key: 'sueno', label: 'Sueño', icon: <BedtimeRounded />, render: (d) => <Sleep data={d} /> },
  { key: 'corazon', label: 'Corazón', icon: <FavoriteRounded />, render: (d) => <Heart data={d} /> },
  { key: 'actividad', label: 'Actividad', icon: <DirectionsWalkRounded />, render: (d, go) => <Activity data={d} go={go} /> },
  { key: 'comida', label: 'Comida', icon: <FavoriteRounded />, render: (d, go) => <Food data={d} go={go} /> },
  { key: 'compra', label: 'Menú y compra', icon: <FavoriteRounded />, render: (_d, go) => <Shopping go={go} /> },
  { key: 'entreno', label: 'Entreno', icon: <DirectionsRunRounded />, render: (d, go) => <Training data={d} go={go} /> },
  { key: 'plan', label: 'Plan', icon: <EventNoteRounded />, render: (d, go) => <PlanPage data={d} go={go} /> },
  { key: 'ritmos', label: 'Ritmos', icon: <SpeedRounded />, render: (d) => <Paces data={d} /> },
  { key: 'gimnasio', label: 'Gimnasio', icon: <FitnessCenterRounded />, render: (d, go) => <Gym data={d} go={go} /> },
  { key: 'analisis', label: 'Análisis', icon: <InsightsRounded />, render: (d) => <Insights data={d} /> },
];

function usePageFromHash() {
  const read = () => (window.location.hash.startsWith('#act-') ? window.location.hash.slice(1)
    : window.location.hash === '#progreso' ? 'entreno'  // la antigua pestaña Progreso: sus récords están en Entreno
      : PAGES.find((p) => `#${p.key}` === window.location.hash)?.key ?? 'hoy');
  const [page, setPage] = useState(read);
  useEffect(() => {
    const on = () => setPage(read());
    window.addEventListener('hashchange', on);
    return () => window.removeEventListener('hashchange', on);
  }, []);
  const go = (k: string) => {
    window.location.hash = k;
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };
  return [page, go] as const;
}

function ModeMenu({ vapid, onInfo, me, onAccount }: { vapid?: string; onInfo: (t: string) => void; me: Me | null; onAccount: (d: 'admin' | 'key' | 'delete') => void }) {
  const { mode, setMode } = useColorScheme();
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const [, force] = useState(0);
  const [iosHelp, setIosHelp] = useState(false);
  useEffect(() => onInstallChange(() => force((n) => n + 1)) as unknown as () => void, []);
  const remote = !['localhost', '127.0.0.1', ''].includes(window.location.hostname);
  const showInstall = remote && !isStandalone() && (canPromptInstall() || isIos());
  const opts = [
    { v: 'system', label: 'Automático', hint: 'Igual que tu sistema', icon: <ContrastOutlined /> },
    { v: 'light', label: 'Claro', hint: undefined, icon: <LightModeOutlined /> },
    { v: 'dark', label: 'Oscuro', hint: undefined, icon: <DarkModeOutlined /> },
  ] as const;
  const current = opts.find((o) => o.v === mode) ?? opts[0];
  return (
    <>
      <Tooltip title={`Tema: ${current.label.toLowerCase()}`}>
        <IconButton onClick={(e) => setAnchor(e.currentTarget)} aria-label="Cambiar tema"
          aria-haspopup="menu" aria-expanded={!!anchor} sx={{ color: '#D4542F' }}>{current.icon}</IconButton>
      </Tooltip>
      <Menu anchorEl={anchor} open={!!anchor} onClose={() => setAnchor(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
        transformOrigin={{ vertical: 'top', horizontal: 'right' }}
        slotProps={{ paper: { sx: { mt: 1, minWidth: 232 } } }}>
        <Typography variant="caption" sx={{ display: 'block', px: 2.5, pt: 0.5, pb: 1, color: 'text.secondary', fontWeight: 500 }}>
          Tema
        </Typography>
        {opts.map((o) => (
          <MenuItem key={o.v} selected={o.v === mode} onClick={() => { setMode(o.v); setAnchor(null); }}>
            <ListItemIcon sx={{ color: o.v === mode ? 'primary.main' : 'text.secondary' }}>{o.icon}</ListItemIcon>
            <ListItemText primary={o.label} secondary={o.hint}
              slotProps={{ secondary: { sx: { fontSize: 12 } } }} />
            {o.v === mode && <Check fontSize="small" sx={{ color: 'primary.main', ml: 2 }} />}
          </MenuItem>
        ))}
        {showInstall && (
          <MenuItem onClick={async () => { setAnchor(null); if (canPromptInstall()) await promptInstall(); else setIosHelp(true); }} sx={{ mt: 0.5 }}>
            <ListItemIcon><InstallMobileRounded fontSize="small" /></ListItemIcon>
            <ListItemText primary="Instalar la app" secondary="Icono en tu pantalla de inicio" slotProps={{ secondary: { sx: { fontSize: 12 } } }} />
          </MenuItem>
        )}
        {remote && vapid && (
          <MenuItem onClick={async () => { setAnchor(null); onInfo(await enablePush(vapid)); }}>
            <ListItemIcon><NotificationsActiveOutlined fontSize="small" /></ListItemIcon>
            <ListItemText primary="Avisos de la mañana" secondary="Preparación y sesión del día a las 7:30" slotProps={{ secondary: { sx: { fontSize: 12 } } }} />
          </MenuItem>
        )}
        {me && <Divider sx={{ my: 0.5 }} />}
        {me && (
          <Typography variant="caption" sx={{ display: 'block', px: 2.5, pt: 0.5, pb: 0.5, color: 'text.secondary', fontWeight: 500 }} noWrap>
            {me.name ? `${me.name} · ` : ''}{me.email}
          </Typography>
        )}
        <MenuItem onClick={() => { setAnchor(null); window.dispatchEvent(new Event('open-whatsnew')); }}>
          <ListItemIcon><NewReleasesOutlined fontSize="small" /></ListItemIcon>
          <ListItemText primary="Novedades" secondary="Lo último que hemos añadido" slotProps={{ secondary: { sx: { fontSize: 12 } } }} />
        </MenuItem>
        {me?.role === 'owner' && (
          <MenuItem onClick={() => { setAnchor(null); onAccount('admin'); }}>
            <ListItemIcon><GroupAddOutlined fontSize="small" /></ListItemIcon>
            <ListItemText primary="Invitaciones" secondary="Invitar a amigos y amigas y ver su gasto" slotProps={{ secondary: { sx: { fontSize: 12 } } }} />
          </MenuItem>
        )}
        {me && (
          <MenuItem onClick={() => { setAnchor(null); onAccount('key'); }}>
            <ListItemIcon><KeyOutlined fontSize="small" /></ListItemIcon>
            <ListItemText primary="Clave de Garmin" secondary="Cambiarla si caduca" slotProps={{ secondary: { sx: { fontSize: 12 } } }} />
          </MenuItem>
        )}
        {me?.role === 'friend' && (
          <MenuItem onClick={() => { setAnchor(null); onAccount('delete'); }}>
            <ListItemIcon><PersonRemoveOutlined fontSize="small" /></ListItemIcon>
            <ListItemText primary="Borrar mi cuenta" secondary="Y todos mis datos" slotProps={{ secondary: { sx: { fontSize: 12 } } }} />
          </MenuItem>
        )}
        {remote && (
          <MenuItem component="a" href="/auth/logout" sx={{ mt: 0.5 }}>
            <ListItemIcon><LogoutRounded fontSize="small" /></ListItemIcon>
            <ListItemText primary="Cerrar sesión" />
          </MenuItem>
        )}
      </Menu>
      <Dialog open={iosHelp} onClose={() => setIosHelp(false)} slotProps={{ paper: { sx: { borderRadius: '28px', p: 1 } } }}>
        <DialogTitle>Instalar en el iPhone</DialogTitle>
        <DialogContent>
          <Typography component="ol" sx={{ pl: 2.5, m: 0, '& li': { mb: 1 } }}>
            <li>Abre esta web en <b>Safari</b>.</li>
            <li>Pulsa el botón <b>Compartir</b> (el cuadrado con la flecha hacia arriba).</li>
            <li>Elige <b>Añadir a pantalla de inicio</b> y pulsa <b>Añadir</b>.</li>
            <li>Abre <b>Runch</b> desde el icono y activa los <b>Avisos de la mañana</b> en este menú.</li>
          </Typography>
          <Button onClick={() => setIosHelp(false)} sx={{ mt: 2, borderRadius: 999 }} variant="contained" disableElevation>Entendido</Button>
        </DialogContent>
      </Dialog>
    </>
  );
}

type Section = { key: string; label: string; icon: ReactElement; pages: string[]; owner?: boolean };
const SECTIONS: Section[] = [
  { key: 'hoy', label: 'Hoy', icon: <HomeRounded />, pages: ['hoy', 'dia', 'semana'] },
  { key: 'salud', label: 'Salud', icon: <FavoriteRounded />, pages: ['sueno', 'corazon', 'actividad', 'comida', 'compra'] },
  { key: 'entreno', label: 'Entreno', icon: <DirectionsRunRounded />, pages: ['plan', 'entreno', 'ritmos', 'gimnasio'] },
  // Solo la dueña: sus análisis a fondo. Las invitadas ven 3 secciones.
  { key: 'analisis', label: 'Análisis', icon: <InsightsRounded />, pages: ['analisis'], owner: true },
];
const SUB_LABEL: Record<string, string> = {
  hoy: 'Resumen', dia: 'Tu día', semana: 'Semana',
  sueno: 'Sueño', corazon: 'Corazón', actividad: 'Actividad', comida: 'Comida', plan: 'Plan', entreno: 'Actividades', ritmos: 'Ritmos', gimnasio: 'Gimnasio',
  analisis: 'Análisis',
};
const sectionOf = (page: string) => SECTIONS.find((s) => s.pages.includes(page)) ?? SECTIONS[0];
/** Subpáginas sin pestaña propia: se ven bajo la pestaña de su página "madre" (Menú y compra cuelga de Comida). */
const SUB_PARENT: Record<string, string> = { compra: 'comida' };
/** Páginas solo para la dueña: las invitadas no las ven (ni la pestaña ni por enlace). */
const OWNER_ONLY = new Set(['analisis']);

/** Selector de subpágina tipo "segmented control". */
function SubTabs({ section, page, go, owner }: { section: Section; page: string; go: (k: string) => void; owner: boolean }) {
  const tabs = section.pages.filter((k) => !SUB_PARENT[k] && (owner || !OWNER_ONLY.has(k)));
  if (tabs.length < 2) return null;
  const many = tabs.length > 3;  // 4 pestañas en el móvil: letra y márgenes algo menores
  return (
    <Box sx={{ display: 'flex', p: 0.5, gap: 0.5, borderRadius: 999, mb: { xs: 2.5, sm: 3 }, width: { xs: '100%', sm: 'fit-content' },
      bgcolor: 'color-mix(in srgb, var(--mui-palette-text-primary) 6%, transparent)' }}>
      {tabs.map((k) => {
        const on = k === (SUB_PARENT[page] ?? page);
        return (
          <Box key={k} component="button" onClick={() => go(k)}
            sx={{ flex: { xs: 1, sm: 'none' }, px: { xs: many ? 0.5 : 1, sm: 2.5 }, py: 1, border: 0, borderRadius: 999, cursor: 'pointer',
              font: 'inherit', fontSize: { xs: many ? 13 : 14, sm: 14 }, fontWeight: on ? 600 : 500, whiteSpace: 'nowrap', minWidth: 0,
              color: on ? 'text.primary' : 'text.secondary', bgcolor: on ? 'background.paper' : 'transparent',
              boxShadow: on ? '0 1px 3px rgba(0,0,0,.12)' : 'none', transition: 'all .2s' }}>
            {OWNER_ONLY.has(k) ? (
              // Solo tú la ves: candado terracota delante del nombre
              <Box component="span" title="Solo la ves tú" sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.5 }}>
                <LockRounded sx={{ fontSize: 14, color: '#D4542F' }} />{SUB_LABEL[k]}
              </Box>
            ) : SUB_LABEL[k]}
          </Box>
        );
      })}
    </Box>
  );
}

/** Barra inferior flotante tipo "cristal" (móvil): 4 secciones + botón del chat aparte. */
function GlassNav({ current, go, last, sections: SECTIONS }: { current: Section; go: (k: string) => void; last: Record<string, string>; sections: Section[] }) {
  // Barra de navegación en el terracota del logo, con iconos blancos.
  const glass = {
    bgcolor: '#D4542F',
    border: 0,
    boxShadow: '0 8px 32px rgba(0,0,0,.14), inset 0 1px 0 rgba(255,255,255,.35)',
  } as const;
  return (
    <Box sx={{ position: 'fixed', zIndex: 20, left: 12, right: 12, bottom: 'max(10px, calc(env(safe-area-inset-bottom) - 12px))',
      display: 'flex', gap: 1, alignItems: 'center', maxWidth: 520, mx: 'auto' }}>
      <Box sx={{ ...glass, flex: 1, height: 64, borderRadius: 999, display: 'flex', p: 0.5, position: 'relative' }}>
        {/* Burbuja que se desliza hasta la sección activa (efecto líquido, con rebote suave) */}
        <Box aria-hidden sx={{ position: 'absolute', top: 4, bottom: 4, borderRadius: 999, bgcolor: 'rgba(255,255,255,0.22)',
          width: `calc((100% - 8px) / ${SECTIONS.length})`,
          left: `calc(4px + (100% - 8px) / ${SECTIONS.length} * ${Math.max(0, SECTIONS.findIndex((x) => x.key === current.key))})`,
          transition: 'left 560ms cubic-bezier(.34,1.4,.64,1), width 560ms cubic-bezier(.34,1.4,.64,1)',
          boxShadow: 'inset 0 1px 0 rgba(255,255,255,.35)' }} />
        {SECTIONS.map((sec) => {
          const on = sec.key === current.key;
          return (
            <Box key={sec.key} component="button" onClick={() => { haptic('tap'); go(last[sec.key] ?? sec.pages[0]); }} aria-label={sec.label}
              sx={{ flex: 1, border: 0, borderRadius: 999, cursor: 'pointer', font: 'inherit', display: 'flex', flexDirection: 'column',
                alignItems: 'center', justifyContent: 'center', gap: 0.25, color: '#FFFFFF', opacity: on ? 1 : 0.72,
                position: 'relative', zIndex: 1, background: 'transparent',
                transition: 'opacity .4s ease, transform .45s cubic-bezier(.34,1.4,.64,1)',
                transform: on ? 'scale(1.04)' : 'scale(1)',
                '&:active': { transform: 'scale(0.94)' },
                '& svg': { fontSize: 23, transition: 'transform .5s cubic-bezier(.34,1.4,.64,1)' },
                '&:hover svg': { transform: 'translateY(-1px)' } }}>
              <Box sx={{ position: 'relative', display: 'flex' }}>
                {sec.icon}
                {sec.owner && <LockRounded aria-label="solo para ti" sx={{ position: 'absolute', right: -7, top: -4, fontSize: '12px !important', p: '1px',
                  borderRadius: '50%', bgcolor: '#FFFFFF', color: '#D4542F' }} />}
              </Box>
              <Box component="span" sx={{ fontSize: 11, fontWeight: on ? 600 : 500, lineHeight: 1 }}>{sec.label}</Box>
            </Box>
          );
        })}
      </Box>
      <Box component="button" aria-label="Pregúntale a la IA" onClick={() => window.dispatchEvent(new Event('open-chat'))}
        sx={{ ...glass, width: 64, height: 64, borderRadius: '50%', cursor: 'pointer', display: 'grid', placeItems: 'center',
          color: '#FFFFFF', '& svg': { fontSize: 26 } }}>
        <AutoAwesomeRounded />
      </Box>
    </Box>
  );
}

export default function App() {
  const { data, checking, fresh, clearFresh, check } = useGarminData(60_000);
  const [info, setInfo] = useState<string | null>(null);
  const now = useNow();
  const [page, go] = usePageFromHash();
  const theme = useTheme();
  const mobile = useMediaQuery(theme.breakpoints.down('md'));
  const [last, setLast] = useState<Record<string, string>>({});
  const onSynced = useCallback((msg: string) => { clearFresh(); setInfo(msg); haptic('success'); }, [clearFresh]);
  const { me, error: meError, refresh: refreshMe } = useMe(120_000);
  const isOwner = me?.role === 'owner';
  const [dialog, setDialog] = useState<null | 'admin' | 'key' | 'delete'>(null);
  // Ya hay datos en el servidor pero esta página se cargó antes: traerlos
  useEffect(() => { if (me?.hasData && !data) check(); }, [me?.hasData, data, check]);
  const { syncing, sync } = useManualSync(data, check, onSynced);
  // Tras guardar algo (marca, test, cómo estás…) la API ya ha reescrito data.js: se vuelve a leer
  useEffect(() => { const on = () => { check(); }; window.addEventListener('gs-refresh', on); return () => window.removeEventListener('gs-refresh', on); }, [check]);

  const actId = page.startsWith('act-') ? Number(page.slice(4)) : null;
  // Invitadas: las páginas solo de la dueña llevan a Hoy.
  const blocked = OWNER_ONLY.has(page) && !!me && !isOwner;
  const pageKey = actId != null ? 'entreno' : blocked ? 'hoy' : (PAGES.some((p) => p.key === page) ? page : 'hoy');
  const section = sectionOf(pageKey);
  const sections = SECTIONS.filter((x) => !x.owner || isOwner);
  // El logo lleva al inicio: Hoy → Resumen, arriba del todo.
  const goHome = () => { haptic('tap'); go('hoy'); window.scrollTo({ top: 0, behavior: 'smooth' }); };
  useEffect(() => { if (actId == null) setLast((l) => ({ ...l, [section.key]: pageKey })); }, [pageKey, section.key, actId]);

  if (!data) {
    if (me && !me.hasData) return <Onboarding me={me} refresh={refreshMe} onData={() => { check(); }} />;
    return (
      <Box sx={{ minHeight: '100vh', display: 'grid', placeItems: 'center', p: 3, textAlign: 'center' }}>
        {meError
          ? <Stack spacing={2} sx={{ alignItems: 'center' }}><Typography color="text.secondary">{meError}</Typography>
              <Button href="./" variant="outlined" sx={{ borderRadius: 999 }}>Reintentar</Button></Stack>
          : <Typography color="text.secondary">Cargando tus datos…</Typography>}
      </Box>
    );
  }

  const current = PAGES.find((p) => p.key === pageKey) ?? PAGES[0];
  const generated = new Date(data.generatedAt);

  return (
    <OwnerCtx.Provider value={isOwner}>
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default', pb: mobile ? 'calc(92px + env(safe-area-inset-bottom))' : 6 }}>
      <AppBar position="sticky" sx={{ pt: 'env(safe-area-inset-top)', bgcolor: 'color-mix(in srgb, var(--mui-palette-background-default) 82%, transparent)',
        backdropFilter: 'blur(16px) saturate(160%)', WebkitBackdropFilter: 'blur(16px) saturate(160%)' }}>
        <Container maxWidth="lg">
          <Toolbar disableGutters sx={{ gap: { xs: 0.75, sm: 1.5 }, minHeight: { xs: 56, sm: 68 } }}>
            {mobile ? (
              <Box sx={{ flex: 1, minWidth: 0, lineHeight: 1 }}>
                <Box component="button" aria-label="Ir al inicio" onClick={goHome}
                  sx={{ p: 0, border: 0, background: 'none', cursor: 'pointer', display: 'inline-flex', '&:active': { transform: 'scale(0.96)' } }}>
                  <Wordmark height={26} />
                </Box>
                <Typography variant="caption" color="text.secondary" sx={{ display: 'block', lineHeight: 1.2 }} noWrap>
                  {syncing ? 'Conectando con Garmin…' : `Actualizado ${relative(generated, now)}`}
                </Typography>
              </Box>
            ) : (
              <Box component="button" aria-label="Ir al inicio" onClick={goHome}
                  sx={{ p: 0, border: 0, background: 'none', cursor: 'pointer', display: 'inline-flex', '&:active': { transform: 'scale(0.96)' } }}>
                  <Wordmark height={32} />
                </Box>
            )}
            {!mobile && (
              <Tabs value={section.key} onChange={(_, v) => { const sec = SECTIONS.find((x) => x.key === v)!; go(last[sec.key] ?? sec.pages[0]); }}
                sx={{ flex: 1, minWidth: 0, ml: 3, '& .MuiTabs-indicator': { height: 3, borderRadius: '3px 3px 0 0' } }}>
                {sections.map((sec) => <Tab key={sec.key} value={sec.key} label={sec.label} icon={sec.owner ? <LockRounded sx={{ fontSize: 14, color: '#D4542F' }} /> : undefined} iconPosition="end" sx={{ minHeight: 48 }} />)}
              </Tabs>
            )}
            {!mobile && (
              <Tooltip title={syncing ? 'Conectando con Garmin…' : `Datos de las ${time(generated)}. Se actualizan solos cada hora; pulsa para traerlos de Garmin ahora.`}>
                <Stack direction="row" spacing={0.5} sx={{ alignItems: 'center', color: 'text.secondary' }}>
                  <Typography variant="body2" sx={{ whiteSpace: 'nowrap' }}>{syncing ? 'Conectando con Garmin…' : `Actualizado ${relative(generated, now)}`}</Typography>
                  <IconButton size="small" onClick={sync} disabled={syncing} aria-label="Actualizar con Garmin ahora"
                    sx={{ animation: syncing || checking ? 'spin 0.8s linear infinite' : 'none', '@keyframes spin': { to: { transform: 'rotate(360deg)' } } }}>
                    <RefreshRounded fontSize="small" />
                  </IconButton>
                </Stack>
              </Tooltip>
            )}
            {Date.now() - new Date(`${LATEST.date}T00:00:00`).getTime() < 30 * 864e5 && (
              <Tooltip title="Novedades">
                <IconButton data-new="news-button" aria-label="Novedades" onClick={() => window.dispatchEvent(new Event('open-whatsnew'))} sx={{ color: 'primary.main', p: { xs: 0.75, sm: 1 } }}>
                  <NewReleasesOutlined />
                </IconButton>
              </Tooltip>
            )}
            <ModeMenu vapid={data.push?.vapidPublicKey ?? undefined} onInfo={setInfo} me={me} onAccount={setDialog} />
          </Toolbar>
        </Container>
      </AppBar>

      <Container maxWidth="lg" sx={{ pt: { xs: 2, sm: 4 }, px: { xs: 2, sm: 3 } }}>
        {me?.status === 'key_invalid' && (
          <Alert severity="warning" sx={{ borderRadius: '16px', mb: 2 }}
            action={<Button color="inherit" size="small" onClick={() => setDialog('key')}>Poner clave nueva</Button>}>
            Garmin ya no acepta tu clave (puede haber caducado): tus datos no se actualizan.
          </Alert>
        )}
        {me?.sync?.status === 'running' && me.sync.backfill && (
          <Alert severity="info" sx={{ borderRadius: '16px', mb: 2 }}>
            Seguimos bajando tu historial de Garmin: algunas gráficas se completarán en unos minutos.
          </Alert>
        )}
        {me && me.budgetUsd > 0 && me.monthSpendUsd >= me.budgetUsd && (
          <Alert severity="info" sx={{ borderRadius: '16px', mb: 2 }}>
            Has usado el tope de IA de este mes{isOwner ? ` (${me.budgetUsd} $)` : ''}. Los textos del coach y el chat vuelven el día 1; tus datos se siguen actualizando.
          </Alert>
        )}
        {actId == null && <SubTabs section={section} page={pageKey} go={go} owner={isOwner} />}
        {actId != null
          ? <ActivityDetail data={data} id={actId} back={() => (window.history.length > 1 ? window.history.back() : go('entreno'))} />
          : current.render(data, go)}
        <Typography variant="caption" color="text.disabled" sx={{ display: 'block', textAlign: 'center', mt: 6 }}>
          Datos de Garmin Connect · No es consejo médico · actualizado {relative(generated, now)}
        </Typography>
      </Container>

      {mobile && <GlassNav current={section} go={go} last={last} sections={sections} />}
      <AdminDialog open={dialog === 'admin'} onClose={() => setDialog(null)} />
      <GarminKeyDialog open={dialog === 'key'} onClose={() => setDialog(null)} onDone={() => { refreshMe(); setInfo('Clave guardada: actualizando tus datos de Garmin…'); }} />
      <DeleteAccountDialog open={dialog === 'delete'} onClose={() => setDialog(null)} />
      {mobile && <GlobalStyles styles={{ 'html, body': { overscrollBehaviorY: 'contain' } }} />}
      {mobile && <PullToRefresh onRefresh={sync} busy={syncing} />}

      <Chat showFab={!mobile} />
      <WhatsNew me={me} go={go} ready={!!me} />
      <WelcomeTour me={me} />
      <Spotlight />
      <Snackbar open={!!info} autoHideDuration={9000} onClose={() => setInfo(null)} message={info}
        anchorOrigin={{ vertical: mobile ? 'top' : 'bottom', horizontal: 'center' }} sx={{ '& .MuiSnackbarContent-root': { maxWidth: 520 } }} />
      <Snackbar open={fresh} autoHideDuration={4000} onClose={clearFresh} message="Datos actualizados"
        anchorOrigin={{ vertical: mobile ? 'top' : 'bottom', horizontal: 'center' }} />
    </Box>
    </OwnerCtx.Provider>
  );
}
