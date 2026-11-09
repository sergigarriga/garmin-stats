import Box from '@mui/material/Box';
import { useResolvedMode } from '../theme';
import terracota from './runch-logo-terracota.svg?raw';
import crema from './runch-logo-crema.svg?raw';

// Logotipo «runch» (el de Instagram): terracota en modo claro, crema en oscuro.
export function Wordmark({ height = 26 }: { height?: number }) {
  const mode = useResolvedMode();
  const svg = mode === 'dark' ? crema : terracota;
  return (
    <Box component="img" alt="runch" src={`data:image/svg+xml;utf8,${encodeURIComponent(svg)}`}
      sx={{ height, width: 'auto', display: 'block', flexShrink: 0 }} />
  );
}
