import { useEffect, useState } from 'react';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import Checkbox from '@mui/material/Checkbox';
import CircularProgress from '@mui/material/CircularProgress';
import Container from '@mui/material/Container';
import FormControlLabel from '@mui/material/FormControlLabel';
import LinearProgress from '@mui/material/LinearProgress';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import BedtimeRounded from '@mui/icons-material/BedtimeRounded';
import DirectionsRunRounded from '@mui/icons-material/DirectionsRunRounded';
import FavoriteRounded from '@mui/icons-material/FavoriteRounded';
import TuneRounded from '@mui/icons-material/TuneRounded';
import { Wordmark } from '../brand/Wordmark';
import LockOutlined from '@mui/icons-material/LockOutlined';
import ContentCopyRounded from '@mui/icons-material/ContentCopyRounded';
import WatchRounded from '@mui/icons-material/WatchRounded';
import ScheduleRounded from '@mui/icons-material/ScheduleRounded';
import InstallMobileRounded from '@mui/icons-material/InstallMobileRounded';
import ExpandMoreRounded from '@mui/icons-material/ExpandMoreRounded';
import Accordion from '@mui/material/Accordion';
import AccordionSummary from '@mui/material/AccordionSummary';
import AccordionDetails from '@mui/material/AccordionDetails';
import { canPromptInstall, isIos, isStandalone, onInstallChange, promptInstall } from '../pwa';
import { call, GarminKeyForm, GarminKeySteps, type Me } from '../account';
import { CARD_SX, IconBubble } from '../ui';
import { CreateForm } from './PlanPage';

type Step = 'welcome' | 'garmin' | 'goal' | 'download';

/** Terracota del logo: el onboarding va con los colores de Runch. */
const BRAND = '#D4542F';
const BRAND_DARK = '#B9441F';
const BTN = { borderRadius: 999, bgcolor: BRAND, color: '#FFFFFF', '&:hover': { bgcolor: BRAND_DARK } } as const;

function stepFor(me: Me, skippedGoal: boolean): Step {
  if (me.status !== 'active' && me.status !== 'key_invalid') return me.consented ? 'garmin' : 'welcome';
  if (me.status === 'key_invalid') return 'garmin';
  if (!me.hasGoal && !skippedGoal) return 'goal';
  return 'download';
}

const STEPS: { key: Step; label: string }[] = [
  { key: 'welcome', label: 'Bienvenida' }, { key: 'garmin', label: 'Garmin' }, { key: 'goal', label: 'Objetivo' }, { key: 'download', label: 'Tus datos' },
];

/** Primeros pasos de una persona invitada: aceptar, conectar Garmin, objetivo y primera descarga. */
export default function Onboarding({ me, refresh, onData }: { me: Me; refresh: () => Promise<Me | null>; onData: () => void }) {
  const [skippedGoal, setSkippedGoal] = useState(false);
  const [step, setStep] = useState<Step>(() => stepFor(me, false));
  const [consent, setConsent] = useState(false);
  const [later, setLater] = useState(false);
  const [copied, setCopied] = useState(false);
  const start = async () => {
    try { await call('./api/onboarding/consent', {}); } catch { /* se vuelve a guardar al poner la clave */ }
    setStep('garmin');
  };
  const copyLink = async () => {
    try { await navigator.clipboard.writeText(window.location.origin); setCopied(true); setTimeout(() => setCopied(false), 2000); } catch { /* sin portapapeles */ }
  };
  const first = (me.name || '').split(' ')[0];

  // Mientras descarga, pregunta cada 5 s; cuando ya hay datos, entra en la app
  useEffect(() => {
    if (step !== 'download') return;
    const id = window.setInterval(async () => { const m = await refresh(); if (m?.hasData) onData(); }, 5000);
    return () => window.clearInterval(id);
  }, [step, refresh, onData]);

  const idx = STEPS.findIndex((s) => s.key === step);
  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default', py: { xs: 3, sm: 6 }, pt: 'calc(env(safe-area-inset-top) + 24px)' }}>
      <Container maxWidth="sm" sx={{ px: { xs: 2, sm: 3 } }}>
        <Stack direction="row" spacing={1.25} sx={{ alignItems: 'center', mb: 3 }}>
          <Wordmark height={30} />
        </Stack>

        <Stack direction="row" spacing={0.75} sx={{ mb: 1 }}>
          {STEPS.map((s, i) => <Box key={s.key} sx={{ flex: 1, height: 4, borderRadius: 2, bgcolor: i <= idx ? BRAND : 'action.selected', transition: 'background-color .4s' }} />)}
        </Stack>
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 3 }}>Paso {idx + 1} de {STEPS.length} · {STEPS[idx].label}</Typography>

        {step === 'welcome' && (
          <Stack spacing={3}>
            <Box>
              <Typography sx={{ fontSize: { xs: 28, sm: 34 }, fontWeight: 500, lineHeight: 1.15, letterSpacing: '-0.01em' }}>
                ¡Hola{first ? `, ${first}` : ''}!
              </Typography>
              <Typography color="text.secondary" sx={{ mt: 1, fontSize: 17 }}>
                Te han invitado a Runch: tus datos de Garmin, claros y en un solo sitio, con un coach con IA que te prepara un plan y lo ajusta cada semana.
              </Typography>
            </Box>
            <Stack spacing={1.5}>
              {[
                { icon: <BedtimeRounded />, color: '#5B5BD6', t: 'Sueño, corazón y energía', d: 'Cómo duermes, tu HRV y cómo llegas cada mañana para entrenar.' },
                { icon: <DirectionsRunRounded />, color: '#E8710A', t: 'Plan de entreno con IA', d: 'Para tu objetivo (5 km, 10 km, media, maratón).' },
                { icon: <TuneRounded />, color: '#D4542F', t: 'Reglas a tu medida', d: 'Más natación, bici, gimnasio o menos series: tú decides qué entra en tu semana, y el coach lo respeta.' },
                { icon: <FavoriteRounded />, color: '#D93025', t: 'Un coach al que preguntar', d: '"¿Por qué duermo peor los domingos?" y te responde con tus datos.' },
              ].map((f) => (
                <Stack key={f.t} direction="row" spacing={1.5} sx={{ alignItems: 'flex-start' }}>
                  <IconBubble color={f.color}>{f.icon}</IconBubble>
                  <Box><Typography sx={{ fontWeight: 500 }}>{f.t}</Typography><Typography variant="body2" color="text.secondary">{f.d}</Typography></Box>
                </Stack>
              ))}
            </Stack>
            <Card sx={{ ...CARD_SX, p: 2.5 }}>
              <Typography sx={{ fontWeight: 600, mb: 1.5 }}>Cómo empezar (unos 3 minutos)</Typography>
              <Stack spacing={1.25}>
                {[
                  'Conectas tu Garmin con una clave que te da el propio Garmin.',
                  'Eliges tu objetivo: una carrera, ponerte en forma o solo ver tus datos.',
                  'Bajamos tu historial y el coach te prepara el plan. Ya está.',
                ].map((t, i) => (
                  <Stack key={i} direction="row" spacing={1.5} sx={{ alignItems: 'flex-start' }}>
                    <Box sx={{ width: 24, height: 24, borderRadius: '50%', flexShrink: 0, display: 'grid', placeItems: 'center', fontSize: 13, fontWeight: 700,
                      bgcolor: BRAND, color: '#FFFFFF' }}>{i + 1}</Box>
                    <Typography variant="body2" sx={{ pt: 0.25 }}>{t}</Typography>
                  </Stack>
                ))}
              </Stack>
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={{ xs: 1, sm: 2 }} sx={{ mt: 2, pt: 2, borderTop: 1, borderColor: 'divider' }}>
                <Stack direction="row" spacing={0.75} sx={{ alignItems: 'center', color: 'text.secondary' }}>
                  <WatchRounded sx={{ fontSize: 18 }} /><Typography variant="body2">Un reloj Garmin y tu cuenta de Garmin Connect</Typography>
                </Stack>
                <Stack direction="row" spacing={0.75} sx={{ alignItems: 'center', color: 'text.secondary' }}>
                  <ScheduleRounded sx={{ fontSize: 18 }} /><Typography variant="body2">3 minutos</Typography>
                </Stack>
              </Stack>
            </Card>
            <Card sx={{ ...CARD_SX, p: 2.5 }}>
              <Stack direction="row" spacing={1.5} sx={{ alignItems: 'flex-start' }}>
                <LockOutlined sx={{ mt: 0.25, color: BRAND }} />
                <Box>
                  <Typography sx={{ fontWeight: 500, mb: 0.5 }}>Tus datos</Typography>
                  <Typography variant="body2" color="text.secondary">
                    Solo tú ves tus datos en la app. Se guardan cifrados en un servidor privado de {me.owner === me.email ? 'tu cuenta' : 'quien te invitó'} (Amazon Web Services, Irlanda),
                    que como administrador podría acceder a ellos técnicamente. Para los textos y el plan se envía un resumen a la IA de Anthropic (Claude).
                    Puedes borrar tu cuenta y todo lo guardado cuando quieras desde el menú.
                  </Typography>
                  <FormControlLabel sx={{ mt: 1 }} control={<Checkbox checked={consent} onChange={(e) => setConsent(e.target.checked)} sx={{ '&.Mui-checked': { color: BRAND } }} />}
                    label={<Typography variant="body2">Acepto que se guarden y analicen mis datos de salud de Garmin para usar la app.</Typography>} />
                </Box>
              </Stack>
            </Card>
            <Button variant="contained" disableElevation size="large" disabled={!consent} onClick={start}
              sx={{ ...BTN, alignSelf: { xs: 'stretch', sm: 'flex-start' }, px: 4, py: 1.5 }}>
              Empezar
            </Button>
            {!consent && <Typography variant="caption" color="text.secondary" sx={{ mt: -2 }}>Marca la casilla de arriba para continuar.</Typography>}
          </Stack>
        )}

        {step === 'garmin' && later && (
          <Stack spacing={3}>
            <Box>
              <Typography sx={{ fontSize: { xs: 26, sm: 30 }, fontWeight: 500, lineHeight: 1.2 }}>Sin problema, lo dejamos aquí</Typography>
              <Typography color="text.secondary" sx={{ mt: 1 }}>
                Ya has aceptado la privacidad. Cuando tengas un momento, abre la app desde el ordenador (es más cómodo para crear la clave
                de Garmin) y entrarás directo a este paso.
              </Typography>
            </Box>
            <Card sx={{ ...CARD_SX, p: 2.5 }}>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 0.5 }}>Enlace de la app</Typography>
              <Typography sx={{ fontWeight: 500, overflowWrap: 'anywhere', mb: 1.5 }}>{window.location.host}</Typography>
              <Button variant="outlined" startIcon={<ContentCopyRounded />} onClick={copyLink} sx={{ borderRadius: 999 }}>
                {copied ? 'Copiado' : 'Copiar enlace'}
              </Button>
            </Card>
            <Button onClick={() => setLater(false)} sx={{ borderRadius: 999, alignSelf: 'flex-start', color: BRAND }}>Conectar Garmin ahora</Button>
          </Stack>
        )}

        {step === 'garmin' && !later && (
          <Stack spacing={3}>
            <Box>
              <Typography sx={{ fontSize: { xs: 26, sm: 30 }, fontWeight: 500, lineHeight: 1.2 }}>Conecta tu Garmin</Typography>
              <Typography color="text.secondary" sx={{ mt: 1 }}>
                Garmin te da una clave personal para que la app pueda leer tus datos. Se crea en un minuto:
              </Typography>
            </Box>
            {me.status === 'key_invalid' && (
              <Alert severity="warning" sx={{ borderRadius: '14px' }}>Garmin ya no acepta tu clave anterior (puede haber caducado). Crea una nueva.</Alert>
            )}
            <Card sx={{ ...CARD_SX, p: 2.5 }}><GarminKeySteps /></Card>
            <KeyFaq />
            <GarminKeyForm consent={consent || !!me.consented || me.status === 'key_invalid'} onDone={async () => { const m = await refresh(); if (m) setStep(stepFor(m, skippedGoal)); }} />
            {me.status !== 'key_invalid' && (
              <Button onClick={() => setLater(true)} sx={{ borderRadius: 999, alignSelf: 'flex-start', color: BRAND }}>Ahora no, lo haré luego</Button>
            )}
          </Stack>
        )}

        {step === 'goal' && (
          <Stack spacing={2.5}>
            <Alert severity="success" icon={<CircularProgress size={18} />} sx={{ borderRadius: '14px', alignItems: 'center' }}>
              ¡Garmin conectado! Ya estamos descargando tu historial mientras eliges tu objetivo.
            </Alert>
            <Box>
              <Typography sx={{ fontSize: { xs: 26, sm: 30 }, fontWeight: 500, lineHeight: 1.2 }}>¿A por qué vas?</Typography>
              <Typography color="text.secondary" sx={{ mt: 1 }}>Con esto el coach te prepara el plan en cuanto tenga tus datos.</Typography>
            </Box>
            <CreateForm submitLabel="Guardar objetivo"
              onSubmit={async (body) => { await call('./api/onboarding/goal', body); await refresh(); setStep('download'); }}
              onSkip={() => { setSkippedGoal(true); setStep('download'); }} />
          </Stack>
        )}

        {step === 'download' && <Download me={me} skippedGoal={skippedGoal} />}
      </Container>
    </Box>
  );
}

function Download({ me, skippedGoal }: { me: Me; skippedGoal: boolean }) {
  const s = me.sync ?? {};
  const failed = s.status === 'error';
  return (
    <Stack spacing={3}>
      <Box>
        <Typography sx={{ fontSize: { xs: 26, sm: 30 }, fontWeight: 500, lineHeight: 1.2 }}>Descargando tus datos</Typography>
        <Typography color="text.secondary" sx={{ mt: 1 }}>
          La primera vez se baja todo tu historial de Garmin. En cuanto llegue la primera parte (2-8 minutos) entrarás en la app;
          el resto se sigue completando solo.
        </Typography>
      </Box>
      <Card sx={{ ...CARD_SX, p: 2.5 }}>
        {failed ? (
          <Alert severity="error" sx={{ borderRadius: '14px' }}>Garmin ha dado un error. Lo volvemos a intentar solos cada hora; también puedes recargar esta página en un rato.</Alert>
        ) : (
          <Stack spacing={1.5}>
            <Typography sx={{ fontWeight: 500 }}>{s.part && s.part > 1 ? `Bajando tu historial (parte ${s.part})…` : 'Conectando con Garmin…'}</Typography>
            <LinearProgress sx={{ borderRadius: 2, height: 6 }} />
            <Typography variant="body2" color="text.secondary">
              Puedes cerrar esta página: seguirá descargándose y la próxima vez que entres ya estará todo.
            </Typography>
          </Stack>
        )}
      </Card>
      {(me.hasGoal || !skippedGoal) && (
        <Typography variant="body2" color="text.secondary">
          Cuando termine la descarga, tu coach creará tu plan (1-3 minutos más). Lo verás en la pestaña Entreno → Plan.
        </Typography>
      )}
      <InstallCard />
      <Card sx={{ ...CARD_SX, p: 2.5 }}>
        <Typography sx={{ fontWeight: 600, mb: 1.5 }}>Qué vas a encontrar</Typography>
        <Stack spacing={1.25}>
          {[
            { t: 'Hoy', d: 'Lo importante de un vistazo: cómo llegas, tu sesión del día y tu último entreno.' },
            { t: 'Salud', d: 'Sueño, corazón, actividad y comida, con lo que va bien y lo que hay que vigilar.' },
            { t: 'Entreno', d: 'Tu plan, tus actividades, tus ritmos y el gimnasio.' },
            { t: 'El botón ✦', d: 'Pregúntale lo que quieras al coach: responde con tus datos.' },
          ].map((x) => (
            <Box key={x.t}><Typography variant="body2"><b>{x.t}</b> · <Box component="span" sx={{ color: 'text.secondary' }}>{x.d}</Box></Typography></Box>
          ))}
        </Stack>
      </Card>
    </Stack>
  );
}

/** Preguntas típicas sobre la clave de Garmin, plegadas para no agobiar. */
function KeyFaq() {
  const items = [
    { q: '¿Qué es esta clave?', a: 'Una función oficial de Garmin Connect para que una app lea tus datos sin darle tu contraseña. Solo permite leer: la app no puede cambiar nada de tu cuenta.' },
    { q: '¿Es seguro?', a: 'Se guarda cifrada y solo la usa la app para bajar tus datos. Puedes borrarla en Garmin Connect cuando quieras y la app deja de tener acceso al momento.' },
    { q: 'No encuentro la opción', a: 'Abre el enlace del paso 1 desde el navegador (mejor en el ordenador) e inicia sesión con tu cuenta de Garmin. Si te pide aceptar condiciones, acéptalas y vuelve a abrir el enlace.' },
    { q: '¿Puedo hacerlo desde el móvil?', a: 'Sí: abre el enlace, crea la clave, cópiala y vuelve aquí. Con el botón Pegar se pone sola.' },
  ];
  return (
    <Box>
      {items.map((x) => (
        <Accordion key={x.q} disableGutters elevation={0} sx={{ bgcolor: 'transparent', '&:before': { display: 'none' } }}>
          <AccordionSummary expandIcon={<ExpandMoreRounded />} sx={{ px: 0.5, minHeight: 44 }}>
            <Typography variant="body2" sx={{ fontWeight: 600 }}>{x.q}</Typography>
          </AccordionSummary>
          <AccordionDetails sx={{ px: 0.5, pt: 0 }}><Typography variant="body2" color="text.secondary">{x.a}</Typography></AccordionDetails>
        </Accordion>
      ))}
    </Box>
  );
}

/** Instalar la app en la pantalla de inicio mientras se descargan los datos (Android: botón; iPhone: instrucciones). */
function InstallCard() {
  const [, force] = useState(0);
  useEffect(() => onInstallChange(() => force((n) => n + 1)) as unknown as () => void, []);
  if (isStandalone() || (!canPromptInstall() && !isIos())) return null;
  return (
    <Card sx={{ ...CARD_SX, p: 2.5, display: 'flex', gap: 2, alignItems: 'center' }}>
      <IconBubble color={BRAND}><InstallMobileRounded /></IconBubble>
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Typography sx={{ fontWeight: 600 }}>Mientras tanto, instala la app</Typography>
        <Typography variant="body2" color="text.secondary">
          {isIos() ? 'En Safari: Compartir → Añadir a pantalla de inicio.' : 'Tendrás Runch en tu pantalla de inicio, como cualquier otra app.'}
        </Typography>
      </Box>
      {canPromptInstall() && <Button variant="contained" disableElevation onClick={() => promptInstall()} sx={{ ...BTN, flexShrink: 0 }}>Instalar</Button>}
    </Card>
  );
}
