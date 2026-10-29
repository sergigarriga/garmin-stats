import { useEffect, useState, type ReactElement } from 'react';
import AppBar from '@mui/material/AppBar';
import BottomNavigation from '@mui/material/BottomNavigation';
import BottomNavigationAction from '@mui/material/BottomNavigationAction';
import Box from '@mui/material/Box';
import Container from '@mui/material/Container';
import IconButton from '@mui/material/IconButton';
import ListItemIcon from '@mui/material/ListItemIcon';
import ListItemText from '@mui/material/ListItemText';
import Menu from '@mui/material/Menu';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
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
import DirectionsWalkRounded from '@mui/icons-material/DirectionsWalkRounded';
import DirectionsRunRounded from '@mui/icons-material/DirectionsRunRounded';
import InsightsRounded from '@mui/icons-material/InsightsRounded';
import TrendingUpRounded from '@mui/icons-material/TrendingUpRounded';
import EventNoteRounded from '@mui/icons-material/EventNoteRounded';
import RefreshRounded from '@mui/icons-material/RefreshRounded';
import LightModeOutlined from '@mui/icons-material/LightModeOutlined';
import DarkModeOutlined from '@mui/icons-material/DarkModeOutlined';
import ContrastOutlined from '@mui/icons-material/ContrastOutlined';
import Check from '@mui/icons-material/Check';
import { useGarminData, useNow, type GarminData } from './data';
import { relative, time } from './format';
import Today from './pages/Today';
import Sleep from './pages/Sleep';
import Heart from './pages/Heart';
import Activity from './pages/Activity';
import Training from './pages/Training';
import Insights from './pages/Insights';
import Progress from './pages/Progress';
import PlanPage from './pages/PlanPage';
import ActivityDetail from './pages/ActivityDetail';
import Chat from './Chat';

type Page = { key: string; label: string; icon: ReactElement; render: (d: GarminData, go: (k: string) => void) => ReactElement };

const PAGES: Page[] = [
  { key: 'hoy', label: 'Hoy', icon: <HomeRounded />, render: (d, go) => <Today data={d} go={go} /> },
  { key: 'sueno', label: 'Sueño', icon: <BedtimeRounded />, render: (d) => <Sleep data={d} /> },
  { key: 'corazon', label: 'Corazón', icon: <FavoriteRounded />, render: (d) => <Heart data={d} /> },
  { key: 'actividad', label: 'Actividad', icon: <DirectionsWalkRounded />, render: (d) => <Activity data={d} /> },
  { key: 'entreno', label: 'Entreno', icon: <DirectionsRunRounded />, render: (d, go) => <Training data={d} go={go} /> },
  { key: 'plan', label: 'Plan', icon: <EventNoteRounded />, render: (d, go) => <PlanPage data={d} go={go} /> },
  { key: 'progreso', label: 'Progreso', icon: <TrendingUpRounded />, render: (d, go) => <Progress data={d} go={go} /> },
  { key: 'analisis', label: 'Análisis', icon: <InsightsRounded />, render: (d) => <Insights data={d} /> },
];

function usePageFromHash() {
  const read = () => (window.location.hash.startsWith('#act-') ? window.location.hash.slice(1)
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

function ModeMenu() {
  const { mode, setMode } = useColorScheme();
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
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
          aria-haspopup="menu" aria-expanded={!!anchor}>{current.icon}</IconButton>
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
      </Menu>
    </>
  );
}

export default function App() {
  const { data, checking, fresh, clearFresh, check } = useGarminData(60_000);
  const now = useNow();
  const [page, go] = usePageFromHash();
  const theme = useTheme();
  const mobile = useMediaQuery(theme.breakpoints.down('md'));

  if (!data) {
    return (
      <Box sx={{ minHeight: '100vh', display: 'grid', placeItems: 'center', p: 3, textAlign: 'center' }}>
        <Box>
          <Typography variant="h5">Aún no hay datos</Typography>
          <Typography color="text.secondary" sx={{ mt: 1 }}>Ejecuta <code>uv run garmin-stats all</code> en la carpeta del proyecto.</Typography>
        </Box>
      </Box>
    );
  }

  const actId = page.startsWith('act-') ? Number(page.slice(4)) : null;
  const current = actId != null ? PAGES.find((p) => p.key === 'entreno')! : PAGES.find((p) => p.key === page) ?? PAGES[0];
  const generated = new Date(data.generatedAt);

  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default', pb: mobile ? 10 : 6 }}>
      <AppBar position="sticky" sx={{ bgcolor: 'color-mix(in srgb, var(--mui-palette-background-default) 86%, transparent)', backdropFilter: 'blur(12px)' }}>
        <Container maxWidth="lg">
          <Toolbar disableGutters sx={{ gap: 1.5, minHeight: { xs: 60, sm: 68 } }}>
            <Box sx={{ width: 32, height: 32, borderRadius: '50%', display: 'grid', placeItems: 'center',
              background: 'conic-gradient(from 200deg, #D93025, #E8710A, #F6AE2D, #188038, #1A73E8, #5B5BD6, #D93025)' }}>
              <Box sx={{ width: 22, height: 22, borderRadius: '50%', bgcolor: 'background.default', display: 'grid', placeItems: 'center' }}>
                <FavoriteRounded sx={{ fontSize: 13, color: '#D93025' }} />
              </Box>
            </Box>
            <Typography variant="h6" sx={{ fontSize: 22, color: 'text.primary', flex: mobile ? 1 : 'none' }}>Mi salud</Typography>
            {!mobile && (
              <Tabs value={current.key} onChange={(_, v) => go(v)} variant="scrollable" scrollButtons={false}
                sx={{ flex: 1, minWidth: 0, ml: 3,
                '& .MuiTabs-indicator': { height: 3, borderRadius: '3px 3px 0 0' } }}>
                {PAGES.map((p) => <Tab key={p.key} value={p.key} label={p.label} />)}
              </Tabs>
            )}
            <Tooltip title={`Datos generados a las ${time(generated)}. Se comprueba cada minuto; Garmin se sincroniza cada hora.`}>
              <Stack direction="row" spacing={0.5} sx={{ alignItems: 'center', color: 'text.secondary' }}>
                <Typography variant="body2" sx={{ display: { xs: 'none', lg: 'block' }, whiteSpace: 'nowrap' }}>Actualizado {relative(generated, now)}</Typography>
                <IconButton size="small" onClick={check} aria-label="Comprobar ahora"
                  sx={{ animation: checking ? 'spin 0.8s linear infinite' : 'none', '@keyframes spin': { to: { transform: 'rotate(360deg)' } } }}>
                  <RefreshRounded fontSize="small" />
                </IconButton>
              </Stack>
            </Tooltip>
            <ModeMenu />
          </Toolbar>
        </Container>
      </AppBar>

      <Container maxWidth="lg" sx={{ pt: { xs: 2, sm: 4 } }}>
        {actId != null
          ? <ActivityDetail data={data} id={actId} back={() => (window.history.length > 1 ? window.history.back() : go('entreno'))} />
          : current.render(data, go)}
        <Typography variant="body2" color="text.disabled" sx={{ mt: 6, textAlign: 'center' }}>
          Datos de Garmin Connect (Personal API). No es consejo médico.
        </Typography>
        <Typography variant="caption" color="text.disabled" sx={{ display: 'block', textAlign: 'center', mt: 0.5 }}>
          Versión de la página: {new Date(Number(__BUILD_ID__)).toLocaleString('es-ES', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}
          {' · '}datos: {generated.toLocaleString('es-ES', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}
        </Typography>
      </Container>

      {mobile && (
        <Paper sx={{ position: 'fixed', bottom: 0, left: 0, right: 0, borderTop: 1, borderColor: 'divider', zIndex: 10 }} square>
          <BottomNavigation value={current.key} onChange={(_, v) => go(v)}
            sx={{ height: 72, bgcolor: 'background.paper', '& .MuiBottomNavigationAction-root': { minWidth: 0, px: 0.5 } }}>
            {PAGES.map((p) => <BottomNavigationAction key={p.key} value={p.key} label={p.label} icon={p.icon} />)}
          </BottomNavigation>
        </Paper>
      )}

      <Chat />
      <Snackbar open={fresh} autoHideDuration={4000} onClose={clearFresh} message="Datos actualizados"
        anchorOrigin={{ vertical: mobile ? 'top' : 'bottom', horizontal: 'center' }} />
    </Box>
  );
}
