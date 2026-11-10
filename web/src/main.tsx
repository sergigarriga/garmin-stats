import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import CssBaseline from '@mui/material/CssBaseline';
import { ThemeProvider } from '@mui/material/styles';
import './fonts.css';
import { useEffect } from 'react';
import { theme, useResolvedMode } from './theme';
import App from './App';
import { setupPwa } from './pwa';
import { setupViewport } from './viewport';

setupPwa();
setupViewport();

// El fondo bajo la barra de estado del iPhone sigue el tema que eliges en la app (no el del sistema).
function ThemeChrome() {
  const mode = useResolvedMode();
  useEffect(() => {
    const bg = mode === 'dark' ? '#0E0E0F' : '#F6F4EE';
    document.documentElement.style.backgroundColor = bg;
    document.querySelectorAll('meta[name="theme-color"]').forEach((m) => m.setAttribute('content', bg));
  }, [mode]);
  return null;
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider theme={theme} defaultMode="system" disableTransitionOnChange>
      <CssBaseline enableColorScheme />
      <ThemeChrome />
      <App />
    </ThemeProvider>
  </StrictMode>,
);
