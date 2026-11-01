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
import LockOutlined from '@mui/icons-material/LockOutlined';
import { call, GarminKeyForm, GarminKeySteps, type Me } from '../account';
import { CARD_SX, IconBubble } from '../ui';
import { CreateForm } from './PlanPage';

type Step = 'welcome' | 'garmin' | 'goal' | 'download';

function stepFor(me: Me, skippedGoal: boolean): Step {
  if (me.status !== 'active' && me.status !== 'key_invalid') return 'welcome';
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
          <Box sx={{ width: 30, height: 30, borderRadius: '50%', display: 'grid', placeItems: 'center',
            background: 'conic-gradient(from 200deg, #D93025, #E8710A, #F6AE2D, #188038, #1A73E8, #5B5BD6, #D93025)' }}>
            <Box sx={{ width: 21, height: 21, borderRadius: '50%', bgcolor: 'background.default', display: 'grid', placeItems: 'center' }}>
              <FavoriteRounded sx={{ fontSize: 12, color: '#D93025' }} />
            </Box>
          </Box>
          <Typography variant="h6" sx={{ fontSize: 20 }}>Mi salud</Typography>
        </Stack>

        <Stack direction="row" spacing={0.75} sx={{ mb: 1 }}>
          {STEPS.map((s, i) => <Box key={s.key} sx={{ flex: 1, height: 4, borderRadius: 2, bgcolor: i <= idx ? 'primary.main' : 'action.selected' }} />)}
        </Stack>
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 3 }}>Paso {idx + 1} de {STEPS.length} · {STEPS[idx].label}</Typography>

        {step === 'welcome' && (
          <Stack spacing={3}>
            <Box>
              <Typography sx={{ fontSize: { xs: 28, sm: 34 }, fontWeight: 500, lineHeight: 1.15, letterSpacing: '-0.01em' }}>
                ¡Hola{first ? `, ${first}` : ''}! 👋
              </Typography>
              <Typography color="text.secondary" sx={{ mt: 1, fontSize: 17 }}>
                Te han invitado a Mi salud: tus datos de Garmin, claros y en un solo sitio, con un coach con IA que te prepara un plan y lo ajusta cada semana.
              </Typography>
            </Box>
            <Stack spacing={1.5}>
              {[
                { icon: <BedtimeRounded />, color: '#5B5BD6', t: 'Sueño, corazón y energía', d: 'Cómo duermes, tu HRV y cómo de preparada estás cada mañana.' },
                { icon: <DirectionsRunRounded />, color: '#E8710A', t: 'Plan de entreno con IA', d: 'Para tu objetivo (5 km, 10 km, media, maratón) y con gimnasio si quieres.' },
                { icon: <FavoriteRounded />, color: '#D93025', t: 'Un coach al que preguntar', d: '"¿Por qué duermo peor los domingos?" y te responde con tus datos.' },
              ].map((f) => (
                <Stack key={f.t} direction="row" spacing={1.5} sx={{ alignItems: 'flex-start' }}>
                  <IconBubble color={f.color}>{f.icon}</IconBubble>
                  <Box><Typography sx={{ fontWeight: 500 }}>{f.t}</Typography><Typography variant="body2" color="text.secondary">{f.d}</Typography></Box>
                </Stack>
              ))}
            </Stack>
            <Card sx={{ ...CARD_SX, p: 2.5 }}>
              <Stack direction="row" spacing={1.5} sx={{ alignItems: 'flex-start' }}>
                <LockOutlined color="primary" sx={{ mt: 0.25 }} />
                <Box>
                  <Typography sx={{ fontWeight: 500, mb: 0.5 }}>Tus datos</Typography>
                  <Typography variant="body2" color="text.secondary">
                    Solo tú ves tus datos en la app. Se guardan cifrados en un servidor privado de {me.owner === me.email ? 'tu cuenta' : 'quien te invitó'} (Amazon Web Services, Irlanda),
                    que como administrador podría acceder a ellos técnicamente. Para los textos y el plan se envía un resumen a la IA de Anthropic (Claude).
                    Puedes borrar tu cuenta y todo lo guardado cuando quieras desde el menú.
                  </Typography>
                  <FormControlLabel sx={{ mt: 1 }} control={<Checkbox checked={consent} onChange={(e) => setConsent(e.target.checked)} />}
                    label={<Typography variant="body2">Acepto que se guarden y analicen mis datos de salud de Garmin para usar la app.</Typography>} />
                </Box>
              </Stack>
            </Card>
            <Button variant="contained" disableElevation size="large" disabled={!consent} onClick={() => setStep('garmin')} sx={{ borderRadius: 999, alignSelf: 'flex-start', px: 4 }}>
              Empezar
            </Button>
          </Stack>
        )}

        {step === 'garmin' && (
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
            <GarminKeyForm consent={consent || me.status === 'key_invalid'} onDone={async () => { const m = await refresh(); if (m) setStep(stepFor(m, skippedGoal)); }} />
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
    </Stack>
  );
}
