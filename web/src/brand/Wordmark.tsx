import Box from '@mui/material/Box';
import { useResolvedMode } from '../theme';
import logo from './runch-logo-terracota.svg?raw';

// Logotipo «runch» (el de Instagram) pintado con el color de marca: --brand en modo claro, crema en oscuro.
// Se dibuja en línea (no como imagen) para que siga a las variables de index.html.
const svg = logo.replace(/fill="#[0-9A-Fa-f]{6}"/, 'fill="currentColor"');

export function Wordmark({ height = 26 }: { height?: number }) {
  const mode = useResolvedMode();
  return (
    <Box component="span" role="img" aria-label="runch" dangerouslySetInnerHTML={{ __html: svg }}
      sx={{ display: 'block', flexShrink: 0, lineHeight: 0, color: mode === 'dark' ? 'var(--brand-cream)' : 'var(--brand)',
        '& svg': { height, width: 'auto', display: 'block' } }} />
  );
}
