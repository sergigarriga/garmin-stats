import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
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

// Color de marca (terracota del logo) para todo lo del chat.
import { haptic } from './haptics';
import { BRAND, BRAND_DARK } from './brand/colors';

type Msg = { role: 'user' | 'assistant'; content: string; error?: boolean; retry?: boolean };

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
          <Typography key={i} component="li" sx={{ display: 'flex', gap: 1.25, fontSize: 15, lineHeight: 1.55 }}>
            <Box sx={{ height: '1lh', display: 'flex', alignItems: 'center', flexShrink: 0 }}>
              {ordered ? (
                <Box sx={{ width: 22, height: 22, borderRadius: '50%', bgcolor: `color-mix(in srgb, ${BRAND} 16%, transparent)`,
                  color: BRAND, fontSize: 12, fontWeight: 700, display: 'grid', placeItems: 'center' }}>{i + 1}</Box>
              ) : (
                <Box sx={{ width: 7, height: 7, borderRadius: '50%', bgcolor: BRAND }} />
              )}
            </Box>
            <span>{inline(it)}</span>
          </Typography>
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
  '¿Me da para correr una media maratón?',
];
const STORE = 'garmin-stats:chat';
const online = window.location.protocol.startsWith('http');

function loadHistory(): Msg[] {
  try {
    const saved = JSON.parse(sessionStorage.getItem(STORE) ?? '[]');
    return Array.isArray(saved) ? saved.filter((m) => m && typeof m.content === 'string') : [];
  } catch { return []; }
}

const NO_NET = 'No llego al servidor. Comprueba tu conexión y vuelve a probar.';
const SLOW = 'La respuesta está tardando más de lo normal. Vuelve a intentarlo en un momento.';
const offline = () => navigator.onLine === false;
const WAIT_MS = 75_000;  // el servidor corta a los 60 s: pasado ese tiempo ya no va a llegar por esta petición

/** Una petición cortada (sin cobertura, móvil bloqueado, respuesta lenta) no significa que no haya respuesta:
 *  el servidor la guarda en la conversación al terminar. Se mira ahí unas cuantas veces antes de dar el fallo. */
async function recover(question: string, sentAt: number, tries: number): Promise<string | null> {
  for (let i = 0; i < tries; i++) {
    if (i) await new Promise((r) => setTimeout(r, 4000));
    try {
      const r = await fetch('./api/chat', { credentials: 'same-origin' });
      if (r.status === 401 || r.status === 404) return null;
      if (!r.ok) continue;
      const all = (await r.json())?.messages ?? [];
      const a = all[all.length - 1], q = all[all.length - 2];
      if (a?.role === 'assistant' && q?.role === 'user' && q.content === question.slice(0, 2000)
        && (a.at ?? 0) * 1000 >= sentAt - 120_000) return String(a.content);
    } catch { /* sigue sin red: se vuelve a probar */ }
  }
  return null;
}

function Bubble({ m, i, onRetry }: { m: Msg; i: number; onRetry?: () => void }) {
  const user = m.role === 'user';
  return (
    <Box data-msg={i} sx={{ alignSelf: user ? 'flex-end' : 'flex-start', maxWidth: user ? '85%' : '100%' }}>
      <Box sx={(t) => ({
        px: 2, py: 1.25, borderRadius: user ? '20px 20px 6px 20px' : '20px 20px 20px 6px', whiteSpace: user ? 'pre-wrap' : 'normal', lineHeight: 1.55,
        bgcolor: user ? BRAND : m.error ? alpha(t.palette.error.main, 0.12) : 'color-mix(in srgb, var(--mui-palette-text-primary) 6%, transparent)',
        color: user ? '#FFFFFF' : 'text.primary', fontSize: 15,
        ...(user ? {} : { px: 2.25, py: 1.75 }),
      })}>{user || m.error ? m.content : <Formatted text={m.content} />}</Box>
      {m.error && onRetry && (
        <Button size="small" onClick={onRetry} sx={{ mt: 0.5, borderRadius: 999, textTransform: 'none', color: BRAND }}>Reintentar</Button>
      )}
    </Box>
  );
}

export default function Chat({ showFab = true }: { showFab?: boolean }) {
  const theme = useTheme();
  const mobile = useMediaQuery(theme.breakpoints.down('md'));
  const [open, setOpen] = useState(false);
  const [msgs, setMsgs] = useState<Msg[]>(loadHistory);
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const list = useRef<HTMLDivElement | null>(null);
  // Por qué cambia la conversación: 'ask' (has preguntado), 'answer' (ha respondido) o null (carga/borrado).
  const why = useRef<'ask' | 'answer' | null>(null);
  // La lista aparece al abrir el chat (MUI la monta un instante después): se abre ya abajo del todo.
  const listRef = useCallback((el: HTMLDivElement | null) => {
    list.current = el;
    if (el) el.scrollTop = el.scrollHeight;
  }, []);
  useEffect(() => {
    const on = () => setOpen(true);
    window.addEventListener('open-chat', on);
    return () => window.removeEventListener('open-chat', on);
  }, []);

  // La conversación se guarda en el servidor: al abrir la app se recupera (también desde otro dispositivo)
  useEffect(() => {
    fetch('./api/chat', { credentials: 'same-origin' }).then((r) => (r.ok ? r.json() : null))
      .then((j) => {
        if (!j?.messages?.length) return;
        const server: Msg[] = j.messages.map(({ role, content }: Msg) => ({ role, content }));
        // Si es la misma conversación no se toca (si no, la lista se repinta y salta mientras lees).
        // Tampoco si lo último es un aviso de fallo: la pregunta sigue ahí con su botón de reintentar.
        setMsgs((cur) => (busyRef.current || cur[cur.length - 1]?.error
          || JSON.stringify(cur.filter((m) => !m.error).map(({ role, content }) => ({ role, content }))) === JSON.stringify(server) ? cur : server));
      })
      .catch(() => { /* sin conexión: se queda la copia local */ });
  }, [open]);
  const busyRef = useRef(false);
  busyRef.current = busy;

  useEffect(() => {
    try { sessionStorage.setItem(STORE, JSON.stringify(msgs.slice(-20))); } catch { /* sin almacenamiento */ }
  }, [msgs]);

  // Scroll del chat: solo se mueve la lista de mensajes (nunca la página de detrás) y solo cuando toca.
  // - Al preguntar: baja hasta tu pregunta y los puntitos.
  // - Al llegar la respuesta: tu pregunta arriba y la respuesta debajo, para leerla desde el principio.
  // - Si llega la conversación del servidor o se borra: abajo del todo, sin animación.
  useEffect(() => {
    const l = list.current;
    const reason = why.current;
    why.current = null;
    if (!l) return;
    if (reason === 'answer') {
      const q = l.querySelector<HTMLElement>(`[data-msg="${msgs.length - 2}"]`);
      const top = q ? q.offsetTop - 8 : l.scrollHeight;
      l.scrollTo({ top: Math.min(top, l.scrollHeight - l.clientHeight), behavior: 'smooth' });
    } else if (reason === 'ask') {
      l.scrollTo({ top: l.scrollHeight, behavior: 'smooth' });
    } else {
      l.scrollTop = l.scrollHeight;
    }
  }, [msgs]);

  const send = async (q: string, base: Msg[] = msgs) => {
    const question = q.trim();
    if (!question || busyRef.current) return;
    busyRef.current = true;  // al momento (no al repintar): dos toques seguidos no mandan la pregunta dos veces
    const next: Msg[] = [...base, { role: 'user', content: question }];
    const sentAt = Date.now();
    why.current = 'ask';
    setMsgs(next); setText(''); setBusy(true);
    const answer = (content: string) => { why.current = 'answer'; setMsgs([...next, { role: 'assistant', content }]); };
    const fail = (content: string, retry: boolean) => {
      why.current = 'answer';
      setMsgs([...next, { role: 'assistant', content, error: true, retry }]);
    };
    try {
      if (offline()) { fail(NO_NET, true); return; }
      const ctl = new AbortController();
      const timer = setTimeout(() => ctl.abort(), WAIT_MS);
      let r: Response;
      try {
        r = await fetch('./api/ask', {
          method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Garmin-Stats': '1' }, signal: ctl.signal,
          body: JSON.stringify({ messages: next.filter((m) => !m.error).slice(-12).map(({ role, content }) => ({ role, content })) }),
        });
      } catch {
        const late = await recover(question, sentAt, 5);
        if (late) answer(late); else fail(offline() ? NO_NET : SLOW, true);
        return;
      } finally { clearTimeout(timer); }
      if (r.status === 401) { window.location.href = '/auth/login'; return; }
      const j = await r.json().catch(() => null);
      if (j?.answer) { answer(String(j.answer)); return; }
      if (j?.error) { fail(String(j.error), !!j.retry); return; }
      // Sin respuesta de la app: el servidor ha cortado por tiempo o ha fallado. Puede que la respuesta llegue tarde.
      const late = r.status >= 502 ? await recover(question, sentAt, 10) : null;
      if (late) answer(late); else fail(r.status >= 502 ? SLOW : 'Algo ha fallado. Vuelve a intentarlo.', true);
    } finally { busyRef.current = false; setBusy(false); }
  };
  // Reintentar: quita el aviso de fallo y vuelve a mandar la misma pregunta.
  const retry = () => {
    const i = msgs.length - 1;
    if (i < 1 || !msgs[i].error || msgs[i - 1].role !== 'user') return;
    send(msgs[i - 1].content, msgs.slice(0, i - 1));
  };

  return (
    <>
      {showFab && <Fab variant="extended" onClick={() => setOpen(true)} aria-label="Pregúntale a la IA"
        sx={{ position: 'fixed', right: { xs: 16, md: 28 }, bottom: { xs: 88, md: 28 }, zIndex: 20, textTransform: 'none',
          bgcolor: BRAND, color: '#FFFFFF', '&:hover': { bgcolor: BRAND_DARK }, borderRadius: '18px', px: 2.5, height: 56, boxShadow: '0 2px 6px rgba(0,0,0,.2), 0 6px 18px rgba(0,0,0,.12)' }}>
        <AutoAwesomeRounded sx={{ mr: 1 }} /> Pregunta
      </Fab>}
      <Drawer anchor={mobile ? 'bottom' : 'right'} open={open} onClose={() => setOpen(false)}
        slotProps={{ paper: { sx: mobile ? {
          // Móvil: el chat ocupa la parte visible de la pantalla. Con el teclado abierto se encoge y se
          // queda justo encima de él (iOS no encoge la página: usamos el alto visible, ver viewport.ts).
          '--chat-h': 'min(92dvh, calc(var(--vv-h, 100dvh) - 12px * var(--no-kb, 1)))',
          width: '100%', height: 'var(--chat-h)', bottom: 'auto',
          top: 'calc(var(--vv-top, 0px) + var(--vv-h, 100dvh) - var(--chat-h))',
          pb: 'calc(env(safe-area-inset-bottom) * var(--no-kb, 1))',
          borderRadius: '28px 28px 0 0',
          bgcolor: 'background.paper', backgroundImage: 'none', overscrollBehavior: 'contain',
        } : { width: 440, height: '100%', borderRadius: '28px 0 0 28px', bgcolor: 'background.paper', backgroundImage: 'none' } } }}>
        <Stack sx={{ height: '100%' }}>
          <Stack direction="row" sx={{ alignItems: 'center', px: 2.5, pt: 2.5, pb: 1.5 }} spacing={1.5}>
            <AutoAwesomeRounded sx={{ color: BRAND }} />
            <Box sx={{ flex: 1 }}>
              <Typography variant="h6" sx={{ lineHeight: 1.2 }}>Pregunta a tus datos</Typography>
              <Typography variant="caption" color="text.secondary">Claude Sonnet 5.5 · lee tu histórico completo</Typography>
            </Box>
            {msgs.length > 0 && <IconButton aria-label="Borrar conversación" onClick={() => { setMsgs([]); fetch('./api/chat/clear', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: '{}' }).catch(() => {}); }}><DeleteOutlineRounded /></IconButton>}
            <IconButton aria-label="Cerrar" onClick={() => setOpen(false)}><CloseRounded /></IconButton>
          </Stack>

          <Stack ref={listRef} spacing={1.5} sx={{ flex: 1, minHeight: 0, overflowY: 'auto', overscrollBehavior: 'contain', position: 'relative', px: 2.5, py: 1 }}>
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
            {msgs.map((m, i) => <Bubble key={i} i={i} m={m} onRetry={m.retry && !busy && i === msgs.length - 1 ? retry : undefined} />)}
            {busy && (
              <Box sx={{ alignSelf: 'flex-start', display: 'flex', gap: 0.75, px: 2, py: 1.5, borderRadius: '20px',
                bgcolor: 'color-mix(in srgb, var(--mui-palette-text-primary) 6%, transparent)',
                '& span': { width: 7, height: 7, borderRadius: '50%', bgcolor: 'text.secondary', animation: 'dot 1.2s infinite ease-in-out' },
                '& span:nth-of-type(2)': { animationDelay: '.15s' }, '& span:nth-of-type(3)': { animationDelay: '.3s' },
                '@keyframes dot': { '0%, 80%, 100%': { opacity: 0.25, transform: 'translateY(0)' }, '40%': { opacity: 1, transform: 'translateY(-3px)' } } }}>
                <span /><span /><span />
              </Box>
            )}
          </Stack>

          <Box component="form" onSubmit={(e) => { e.preventDefault(); send(text); }}
            sx={{ m: 2, mt: 1, display: 'flex', alignItems: 'flex-end', gap: 1, p: 0.75, pl: 2, borderRadius: '24px',
              bgcolor: 'color-mix(in srgb, var(--mui-palette-text-primary) 6%, transparent)' }}>
            <InputBase value={text} onChange={(e) => setText(e.target.value)} placeholder="Escribe tu pregunta…" disabled={!online}
              multiline maxRows={4} sx={{ flex: 1, py: 1, fontSize: 16 }}  /* 16px: iOS no hace zoom al escribir */
              slotProps={{ input: { enterKeyHint: 'send' } }}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(text); } }} />
            <IconButton type="submit" onClick={() => haptic('tap')} disabled={!text.trim() || busy || !online} aria-label="Enviar"
              sx={{ bgcolor: BRAND, color: '#FFFFFF', '&:hover': { bgcolor: BRAND_DARK },
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
