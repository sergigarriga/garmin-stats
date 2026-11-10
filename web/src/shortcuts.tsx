// Atajos de la portada: de Hoy a apuntar algo con un toque (tu día, comida, entreno del día, ánimo, molestia, compra).
// Cada atajo lleva el color de la sección a la que va. Solo hay atajos a cosas que existen de verdad.
//
// Cómo abre cada cosa (mismo mecanismo que ya usaba la tarjeta de comida de Hoy):
//   - comida:   deja la marca `food-add` y va a Comida, que abre "Añadir comida" al montarse (Food.tsx)
//   - entreno:  deja la marca `plan-today` y va al Plan, que abre la sesión de hoy (PlanPage.tsx)
//   - molestia: evento `injury-add`, que escucha la tarjeta "¿Cómo te encuentras hoy?" (Wellness.tsx)
import type { ReactElement } from 'react';
import Box from '@mui/material/Box';
import ButtonBase from '@mui/material/ButtonBase';
import Card from '@mui/material/Card';
import RestaurantRounded from '@mui/icons-material/RestaurantRounded';
import ShoppingCartRounded from '@mui/icons-material/ShoppingCartRounded';
import DirectionsRunRounded from '@mui/icons-material/DirectionsRunRounded';
import SentimentSatisfiedRounded from '@mui/icons-material/SentimentSatisfiedRounded';
import HealingRounded from '@mui/icons-material/HealingRounded';
import TodayRounded from '@mui/icons-material/TodayRounded';
import type { GarminData } from './data';
import { haptic } from './haptics';
import { sectionInk } from './brand/colors';
import { IconBubble } from './ui';

const mark = (key: string) => { try { sessionStorage.setItem(key, '1'); } catch { /* sin almacenamiento: se abre la página sin el diálogo */ } };

/** Baja hasta un elemento de la página dejando sitio para la cabecera fija. */
function scrollToEl(selector: string) {
  const el = document.querySelector(selector);
  if (!el) return;
  const header = document.querySelector('header')?.getBoundingClientRect().height ?? 64;
  const smooth = !window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  window.scrollTo({ top: Math.max(0, window.scrollY + el.getBoundingClientRect().top - header - 16), behavior: smooth ? 'smooth' : 'instant' });
}

interface Shortcut { key: string; label: string; hint: string; section: string; icon: ReactElement; run: () => void }

export function Shortcuts({ data, go }: { data: GarminData; go: (k: string) => void }) {
  const hasSessionToday = !!data.coach?.today;
  const items: Shortcut[] = [
    { key: 'dia', label: 'Tu día', hint: 'Ver tu día al detalle', section: 'hoy', icon: <TodayRounded />,
      run: () => go('dia') },
    { key: 'comida', label: 'Comida', hint: 'Apuntar una comida', section: 'salud', icon: <RestaurantRounded />,
      run: () => { mark('food-add'); go('comida'); } },
    { key: 'entreno', label: 'Entreno', hint: hasSessionToday ? 'Ver tu entreno de hoy' : 'Ir a tu plan de entreno', section: 'entreno', icon: <DirectionsRunRounded />,
      run: () => { if (hasSessionToday) mark('plan-today'); go('plan'); } },
    { key: 'animo', label: 'Ánimo', hint: 'Apuntar cómo te encuentras hoy', section: 'hoy', icon: <SentimentSatisfiedRounded />,
      run: () => scrollToEl('[data-new="checkin"]') },
    { key: 'molestia', label: 'Molestia', hint: 'Apuntar una molestia o lesión', section: 'hoy', icon: <HealingRounded />,
      run: () => window.dispatchEvent(new Event('injury-add')) },
    { key: 'compra', label: 'Compra', hint: 'Ir al menú y la lista de la compra', section: 'salud', icon: <ShoppingCartRounded />,
      run: () => go('compra') },
  ];
  return (
    <Card component="nav" aria-label="Atajos para apuntar" data-new="shortcuts"
      sx={{ mb: 2, px: { xs: 0.5, sm: 1.5 }, py: { xs: 1, sm: 1.5 }, bgcolor: 'background.paper', width: { sm: 'fit-content' }, maxWidth: '100%',
        display: 'grid', gridTemplateColumns: { xs: `repeat(${items.length}, minmax(0, 1fr))`, sm: `repeat(${items.length}, 92px)` } }}>
      {items.map((s) => (
        <ButtonBase key={s.key} data-shortcut={s.key} aria-label={s.hint} title={s.hint} onClick={() => { haptic('tap'); s.run(); }}
          sx={{ minWidth: 0, minHeight: 68, py: 0.75, borderRadius: '18px', display: 'flex', flexDirection: 'column', gap: 0.75,
            alignItems: 'center', justifyContent: 'center', font: 'inherit', color: 'text.primary',
            transition: 'transform .25s cubic-bezier(.34,1.4,.64,1), background-color .15s',
            '&:active': { transform: 'scale(0.92)' },
            '@media (hover: hover)': { '&:hover': { bgcolor: 'color-mix(in srgb, var(--mui-palette-text-primary) 5%, transparent)' } },
            '&.Mui-focusVisible': { outline: '2px solid', outlineColor: sectionInk(s.section), outlineOffset: -2 } }}>
          <IconBubble color={sectionInk(s.section)} size={44}>{s.icon}</IconBubble>
          <Box component="span" sx={{ fontSize: { xs: 11.5, sm: 13 }, fontWeight: 500, lineHeight: 1.1, letterSpacing: '-0.01em',
            maxWidth: '100%', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{s.label}</Box>
        </ButtonBase>
      ))}
    </Card>
  );
}
