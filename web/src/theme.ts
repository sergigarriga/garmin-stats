import { createTheme, useColorScheme } from '@mui/material/styles';
import useMediaQuery from '@mui/material/useMediaQuery';

/** Un color por categoría, como en Google Health / Fitbit. Tono claro y tono oscuro. */
export const CATEGORY = {
  activity: { light: '#188038', dark: '#81C995', label: 'Actividad' },
  heart: { light: '#D93025', dark: '#F28B82', label: 'Corazón' },
  sleep: { light: '#5B5BD6', dark: '#AFADFF', label: 'Sueño' },
  stress: { light: '#C26401', dark: '#FDD663', label: 'Estrés' },
  recovery: { light: '#00838F', dark: '#78D9EC', label: 'Recuperación' },
  energy: { light: '#1A73E8', dark: '#8AB4F8', label: 'Energía' },
  training: { light: '#E8710A', dark: '#FCAD70', label: 'Entreno' },
} as const;
export type Category = keyof typeof CATEGORY;

/** Fases del sueño: de más profunda (oscuro) a más ligera (claro); despierto aparte. */
export const SLEEP_STAGES = {
  light: { deep: '#3B3BA8', rem: '#7C7CF0', light: '#B9B8FF', awake: '#F6AE2D' },
  dark: { deep: '#6E6CFF', rem: '#A3A1FF', light: '#D4D3FF', awake: '#FDD663' },
};

/** Zonas de pulso con la convención de Garmin (gris, azul, verde, naranja, rojo). */
export const ZONES = {
  light: ['#9AA0A6', '#1A73E8', '#188038', '#E8710A', '#D93025'],
  dark: ['#BDC1C6', '#8AB4F8', '#81C995', '#FCAD70', '#F28B82'],
};

/** Colores de cada deporte, en orden fijo. */
export const SPORTS: Record<string, { light: string; dark: string }> = {
  Correr: { light: '#E8710A', dark: '#FCAD70' },
  Cinta: { light: '#F6AE2D', dark: '#FDD663' },
  Bici: { light: '#1A73E8', dark: '#8AB4F8' },
  Natación: { light: '#00838F', dark: '#78D9EC' },
  Fuerza: { light: '#9334E6', dark: '#D7AEFB' },
  Caminar: { light: '#188038', dark: '#81C995' },
  Otros: { light: '#80868B', dark: '#BDC1C6' },
};

export function useResolvedMode(): 'light' | 'dark' {
  const { mode, systemMode } = useColorScheme();
  const prefersDark = useMediaQuery('(prefers-color-scheme: dark)');
  const m = mode === 'system' ? systemMode : mode;
  if (m === 'light' || m === 'dark') return m;
  return prefersDark ? 'dark' : 'light';
}

export function useCat() {
  const mode = useResolvedMode();
  return (c: Category) => CATEGORY[c][mode];
}

const font = '"Google Sans Flex Variable", "Google Sans", Roboto, system-ui, -apple-system, sans-serif';

export const theme = createTheme({
  cssVariables: { colorSchemeSelector: 'data-mui-color-scheme' },
  colorSchemes: {
    light: {
      palette: {
        primary: { main: '#5A6B32', contrastText: '#FFFFFF' },  // olivo (marca)
        secondary: { main: '#24496D' },  // mar
        background: { default: '#F6F4EE', paper: '#FFFFFF' },  // crema suave
        text: { primary: '#1F1F1F', secondary: '#444746', disabled: '#8E918F' },
        divider: '#E1E3E1',
        success: { main: '#146C2E' },
        warning: { main: '#B06000' },
        error: { main: '#B3261E' },
      },
    },
    dark: {
      palette: {
        primary: { main: '#B4C784', contrastText: '#1F2A0A' },
        secondary: { main: '#9CC2E6' },
        background: { default: '#0E0E0F', paper: '#1E1F20' },
        text: { primary: '#E3E3E3', secondary: '#C4C7C5', disabled: '#8E918F' },
        divider: '#333537',
        success: { main: '#6DD58C' },
        warning: { main: '#FDD663' },
        error: { main: '#F2B8B5' },
      },
    },
  },
  shape: { borderRadius: 16 },
  typography: {
    fontFamily: font,
    h3: { fontWeight: 500, letterSpacing: '-0.02em' },
    h4: { fontWeight: 500, letterSpacing: '-0.015em' },
    h5: { fontWeight: 500, letterSpacing: '-0.01em' },
    h6: { fontWeight: 500 },
    subtitle1: { fontWeight: 500 },
    subtitle2: { fontWeight: 500 },
    button: { textTransform: 'none', fontWeight: 500, letterSpacing: 0 },
  },
  components: {
    MuiPaper: { styleOverrides: { root: { backgroundImage: 'none' } } },
    MuiCard: {
      defaultProps: { elevation: 0 },
      styleOverrides: { root: { borderRadius: 24 } },
    },
    MuiAppBar: { defaultProps: { elevation: 0, color: 'transparent' } },
    MuiTab: {
      styleOverrides: {
        root: { textTransform: 'none', fontWeight: 500, fontSize: 15, minHeight: 48, borderRadius: 999 },
      },
    },
    MuiToggleButton: {
      styleOverrides: {
        root: { textTransform: 'none', fontWeight: 500, paddingInline: 14, paddingBlock: 4, border: 0 },
      },
    },
    MuiToggleButtonGroup: {
      styleOverrides: { root: { borderRadius: 999, padding: 3, gap: 2 } },
    },
    MuiChip: { styleOverrides: { root: { fontWeight: 500 } } },
    // Menús y popups al estilo Material 3: esquinas 16 px, sombra suave, superficie elevada.
    MuiPopover: {
      styleOverrides: {
        paper: ({ theme }) => ({
          borderRadius: 16,
          backgroundColor: '#FFFFFF',
          boxShadow: '0 1px 2px rgba(60,64,67,.20), 0 2px 8px 2px rgba(60,64,67,.12)',
          ...theme.applyStyles('dark', {
            backgroundColor: '#2B2C2E',
            boxShadow: '0 1px 3px rgba(0,0,0,.5), 0 4px 12px 4px rgba(0,0,0,.35)',
          }),
        }),
      },
    },
    MuiMenu: { styleOverrides: { list: { paddingTop: 8, paddingBottom: 8 } } },
    MuiMenuItem: {
      styleOverrides: {
        root: {
          minHeight: 48, marginInline: 8, borderRadius: 12, gap: 4,
          '&.Mui-selected, &.Mui-selected:hover': { backgroundColor: 'color-mix(in srgb, var(--mui-palette-primary-main) 13%, transparent)' },
          '&.Mui-focusVisible': { backgroundColor: 'color-mix(in srgb, var(--mui-palette-text-primary) 8%, transparent)' },
        },
      },
    },
    MuiListItemIcon: { styleOverrides: { root: { minWidth: 36 } } },
    MuiTooltip: {
      defaultProps: { arrow: false, enterDelay: 400 },
      styleOverrides: {
        tooltip: ({ theme }) => ({
          backgroundColor: '#3C4043', color: '#F1F3F4', fontSize: 12, fontWeight: 400,
          borderRadius: 6, padding: '6px 10px', maxWidth: 280,
          ...theme.applyStyles('dark', { backgroundColor: '#E3E3E3', color: '#1F1F1F' }),
        }),
      },
    },
    MuiSnackbarContent: {
      styleOverrides: {
        root: ({ theme }) => ({
          borderRadius: 12, backgroundColor: '#303030', color: '#F2F2F2', fontWeight: 500, boxShadow: 'none',
          ...theme.applyStyles('dark', { backgroundColor: '#E3E3E3', color: '#1F1F1F' }),
        }),
      },
    },
    MuiTableCell: { styleOverrides: { root: { borderColor: 'var(--mui-palette-divider)' } } },
  },
},
// Textos de las gráficas en castellano (una gráfica sin datos decía "No data to display")
{ components: { MuiChartsLocalizationProvider: { defaultProps: { localeText: { loading: 'Cargando…', noData: 'Aún no hay datos' } } } } });
