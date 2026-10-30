import type { ReactNode } from 'react';
import Box from '@mui/material/Box';

// Datos que se resaltan en los textos: 5 h 38 min, 48 ms, 1:30, 4:16 /km, 44 km, 83 kg, 58 lpm, 12 %, 3x10...
const DATA = /(\*\*[^*]+\*\*|\d+\s?h\s?\d+\s?min|\d+(?:[.,:]\d+)*\s?(?:min\/km|\/km|km\/semana|km|kg|ms|lpm|%|kcal|min|h|s|reps|semanas|noches|días|pasos)(?![a-záéíóúñ])|\d+x\d+(?:\s?kg)?|\d:\d{2}(?::\d{2})?)/gi;

/** Texto con los datos clave en negrita (y **negrita** explícita). */
export function Rich({ children }: { children: string }): ReactNode {
  const parts = children.split(DATA);
  return parts.map((p, i) => {
    if (i % 2 === 0) return p;
    const t = p.startsWith('**') ? p.slice(2, -2) : p;
    return <Box key={i} component="b" sx={{ fontWeight: 600, color: 'text.primary' }}>{t}</Box>;
  });
}
