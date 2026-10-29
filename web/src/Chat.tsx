import { useEffect, useRef, useState, type ReactNode } from 'react';
import Box from '@mui/material/Box';
import Chip from '@mui/material/Chip';
import Drawer from '@mui/material/Drawer';
import Fab from '@mui/material/Fab';
import IconButton from '@mui/material/IconButton';
import InputBase from '@mui/material/InputBase';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import useMediaQuery from '@mui/material/useMediaQuery';
import { alpha, useTheme } from '@mui/material/styles';
import AutoAwesomeRounded from '@mui/icons-material/AutoAwesomeRounded';
import CloseRounded from '@mui/icons-material/CloseRounded';
import ArrowUpwardRounded from '@mui/icons-material/ArrowUpwardRounded';
import DeleteOutlineRounded from '@mui/icons-material/DeleteOutlineRounded';

type Msg = { role: 'user' | 'assistant'; content: string; error?: boolean };

/** **negrita** dentro de una línea. */
function inline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*)/g).filter(Boolean).map((part, i) =>
    part.startsWith('**') && part.endsWith('**')
      ? <Box key={i} component="strong" sx={{ fontWeight: 600, color: 'text.primary' }}>{part.slice(2, -2)}</Box>
      : part);
}

/** Markdown mínimo y seguro (sin HTML): párrafos, listas con "- " o "1. " y negrita. */
function Formatted({ text }: { text: string }) {
  const blocks: ReactNode[] = [];
  let list: { ordered: boolean; items: string[] } | null = null;
  let para: string[] = [];
  const flushPara = () => {
    if (para.length) blocks.push(<Typography key={blocks.length} sx={{ fontSize: 15, lineHeight: 1.6 }}>{inline(para.join(' '))}</Typography>);
    para = [];
  };
  const flushList = () => {
    if (!list) return;
    const { ordered, items } = list;
    blocks.push(
      <Box key={blocks.length} component={ordered ? 'ol' : 'ul'} sx={{ m: 0, pl: 0, listStyle: 'none', display: 'grid', gap: 1 }}>
        {items.map((it, i) => (
          <Box key={i} component="li" sx={{ display: 'flex', gap: 1.25, alignItems: 'flex-start' }}>
            {ordered ? (
              <Box sx={{ minWidth: 22, height: 22, borderRadius: '50%', bgcolor: 'color-mix(in srgb, var(--mui-palette-primary-main) 16%, transparent)',
                color: 'primary.main', fontSize: 12, fontWeight: 700, display: 'grid', placeItems: 'center', mt: '1px' }}>{i + 1}</Box>
            ) : (
              <Box sx={{ width: 7, height: 7, borderRadius: '50%', bgcolor: 'primary.main', flexShrink: 0, mt: '9px' }} />
            )}
            <Typography sx={{ fontSize: 15, lineHeight: 1.55 }}>{inline(it)}</Typography>
          </Box>
        ))}
      </Box>,
    );
    list = null;
  };
  for (const raw of text.split('\n')) {
    const line = raw.trim();
    const ul = line.match(/^[-•*]\s+(.*)$/);
    const ol = line.match(/^\d+[.)]\s+(.*)$/);
    if (ul || ol) {
      flushPara();
      const ordered = !!ol;
      if (!list || list.ordered !== ordered) { flushList(); list = { ordered, items: [] }; }
      list.items.push((ul ?? ol)![1]);
    } else if (!line) {
      flushPara(); flushList();
    } else {
      flushList();
      para.push(line.replace(/^#+\s*/, ''));
    }
  }
  flushPara(); flushList();
  return <Stack spacing={1.25}>{blocks}</Stack>;
}

const SUGGESTIONS = [
  '¿Por qué duermo peor los domingos?',
  '¿Qué día de la semana entreno mejor?',
  '¿Cómo ha cambiado mi forma este año?',
  '¿Qué me recomiendas para subir mi HRV?',
  '¿Estoy listo para correr una media maratón?',
];
const STORE = 'garmin-stats:chat';
const online = window.location.protocol.startsWith('http');

function loadHistory(): Msg[] {
  try { return JSON.parse(sessionStorage.getItem(STORE) ?? '[]'); } catch { return []; }
}

function Bubble({ m }: { m: Msg }) {
  const user = m.role === 'user';
  return (
    <Box sx={{ alignSelf: user ? 'flex-end' : 'flex-start', maxWidth: user ? '85%' : '100%' }}>
      <Box sx={(t) => ({
        px: 2, py: 1.25, borderRadius: user ? '20px 20px 6px 20px' : '20px 20px 20px 6px', whiteSpace: user ? 'pre-wrap' : 'normal', lineHeight: 1.55,
        bgcolor: user ? 'primary.main' : m.error ? alpha(t.palette.error.main, 0.12) : 'color-mix(in srgb, var(--mui-palette-text-primary) 6%, transparent)',
        color: user ? 'primary.contrastText' : 'text.primary', fontSize: 15,
        ...(user ? {} : { px: 2.25, py: 1.75 }),
      })}>{user || m.error ? m.content : <Formatted text={m.content} />}</Box>
    </Box>
  );
}

export default function Chat() {
  const theme = useTheme();
  const mobile = useMediaQuery(theme.breakpoints.down('md'));
  const [open, setOpen] = useState(false);
  const [msgs, setMsgs] = useState<Msg[]>(loadHistory);
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    try { sessionStorage.setItem(STORE, JSON.stringify(msgs.slice(-20))); } catch { /* sin almacenamiento */ }
    end.current?.scrollIntoView({ behavior: 'smooth' });
  }, [msgs, busy]);

  const send = async (q: string) => {
    const question = q.trim();
    if (!question || busy) return;
    const next: Msg[] = [...msgs, { role: 'user', content: question }];
    setMsgs(next); setText(''); setBusy(true);
    try {
      const r = await fetch('./api/ask', {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Garmin-Stats': '1' },
        body: JSON.stringify({ messages: next.filter((m) => !m.error).map(({ role, content }) => ({ role, content })) }),
      });
      const j = await r.json();
      setMsgs([...next, j.answer ? { role: 'assistant', content: j.answer } : { role: 'assistant', content: j.error ?? 'Algo ha fallado.', error: true }]);
    } catch {
      setMsgs([...next, { role: 'assistant', content: 'No llego al servidor. ¿Está abierta la página desde http://localhost:8765?', error: true }]);
    } finally { setBusy(false); }
  };

  return (
    <>
      <Fab variant="extended" color="primary" onClick={() => setOpen(true)} aria-label="Pregúntale a la IA"
        sx={{ position: 'fixed', right: { xs: 16, md: 28 }, bottom: { xs: 88, md: 28 }, zIndex: 20, textTransform: 'none',
          borderRadius: '18px', px: 2.5, height: 56, boxShadow: '0 2px 6px rgba(0,0,0,.2), 0 6px 18px rgba(0,0,0,.12)' }}>
        <AutoAwesomeRounded sx={{ mr: 1 }} /> Pregunta
      </Fab>
      <Drawer anchor={mobile ? 'bottom' : 'right'} open={open} onClose={() => setOpen(false)}
        slotProps={{ paper: { sx: { width: mobile ? '100%' : 440, height: mobile ? '92vh' : '100%',
          borderRadius: mobile ? '28px 28px 0 0' : '28px 0 0 28px', bgcolor: 'background.paper', backgroundImage: 'none' } } }}>
        <Stack sx={{ height: '100%' }}>
          <Stack direction="row" sx={{ alignItems: 'center', px: 2.5, pt: 2.5, pb: 1.5 }} spacing={1.5}>
            <AutoAwesomeRounded color="primary" />
            <Box sx={{ flex: 1 }}>
              <Typography variant="h6" sx={{ lineHeight: 1.2 }}>Pregunta a tus datos</Typography>
              <Typography variant="caption" color="text.secondary">Claude Sonnet 5.5 · lee tu histórico completo</Typography>
            </Box>
            {msgs.length > 0 && <IconButton aria-label="Borrar conversación" onClick={() => setMsgs([])}><DeleteOutlineRounded /></IconButton>}
            <IconButton aria-label="Cerrar" onClick={() => setOpen(false)}><CloseRounded /></IconButton>
          </Stack>

          <Stack spacing={1.5} sx={{ flex: 1, overflowY: 'auto', px: 2.5, py: 1 }}>
            {!online && (
              <Box sx={{ p: 2, borderRadius: '16px', bgcolor: 'color-mix(in srgb, var(--mui-palette-warning-main) 14%, transparent)' }}>
                <Typography sx={{ fontWeight: 500 }}>El chat necesita el servidor local</Typography>
                <Typography variant="body2">Abre la web desde <b>http://localhost:8765</b> en lugar del archivo.</Typography>
              </Box>
            )}
            {msgs.length === 0 && (
              <>
                <Typography color="text.secondary" sx={{ mt: 1 }}>
                  Pregunta lo que quieras sobre tu sueño, tu pulso, tus entrenos o tus hábitos. Responde con tus propios datos.
                </Typography>
                <Stack direction="row" sx={{ flexWrap: 'wrap', gap: 1 }}>
                  {SUGGESTIONS.map((s) => (
                    <Chip key={s} label={s} onClick={() => send(s)} disabled={!online} variant="outlined"
                      sx={{ borderRadius: '12px', height: 'auto', py: 0.75, '& .MuiChip-label': { whiteSpace: 'normal' } }} />
                  ))}
                </Stack>
              </>
            )}
            {msgs.map((m, i) => <Bubble key={i} m={m} />)}
            {busy && (
              <Box sx={{ alignSelf: 'flex-start', display: 'flex', gap: 0.75, px: 2, py: 1.5, borderRadius: '20px',
                bgcolor: 'color-mix(in srgb, var(--mui-palette-text-primary) 6%, transparent)',
                '& span': { width: 7, height: 7, borderRadius: '50%', bgcolor: 'text.secondary', animation: 'dot 1.2s infinite ease-in-out' },
                '& span:nth-of-type(2)': { animationDelay: '.15s' }, '& span:nth-of-type(3)': { animationDelay: '.3s' },
                '@keyframes dot': { '0%, 80%, 100%': { opacity: 0.25, transform: 'translateY(0)' }, '40%': { opacity: 1, transform: 'translateY(-3px)' } } }}>
                <span /><span /><span />
              </Box>
            )}
            <div ref={end} />
          </Stack>

          <Box component="form" onSubmit={(e) => { e.preventDefault(); send(text); }}
            sx={{ m: 2, mt: 1, display: 'flex', alignItems: 'flex-end', gap: 1, p: 0.75, pl: 2, borderRadius: '24px',
              bgcolor: 'color-mix(in srgb, var(--mui-palette-text-primary) 6%, transparent)' }}>
            <InputBase value={text} onChange={(e) => setText(e.target.value)} placeholder="Escribe tu pregunta…" disabled={!online}
              multiline maxRows={4} sx={{ flex: 1, py: 1, fontSize: 15 }}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(text); } }} />
            <IconButton type="submit" disabled={!text.trim() || busy || !online} aria-label="Enviar"
              sx={{ bgcolor: 'primary.main', color: 'primary.contrastText', '&:hover': { bgcolor: 'primary.dark' },
                '&.Mui-disabled': { bgcolor: 'action.disabledBackground' } }}>
              <ArrowUpwardRounded />
            </IconButton>
          </Box>
          <Typography variant="caption" color="text.disabled" sx={{ textAlign: 'center', pb: 1.5, px: 2 }}>
            Cada pregunta cuesta unos 0,04 $. No es consejo médico.
          </Typography>
        </Stack>
      </Drawer>
    </>
  );
}
