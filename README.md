# garmin_stats

Descarga todos tus datos de Garmin Connect con la **Personal API oficial** y genera un
informe HTML con análisis de sueño, recuperación, entrenamiento y carrera.

## La web

Abre `site/index.html` en el navegador (doble clic; no hace falta servidor). Es una app React +
Material UI con estilo Google Health, con pestañas Hoy, Sueño, Corazón, Actividad, Entreno y
Análisis, y modo automático, claro u oscuro.

Se actualiza sola:

1. Cron ejecuta `bin/update.sh` en el minuto 5 de cada hora. El script sincroniza con Garmin y
   reescribe `site/data.js`. El log está en `data/update.log`.
2. La página vuelve a leer `data.js` cada minuto y al volver a la pestaña. Si hay datos nuevos,
   avisa con "Datos actualizados".

Cron solo funciona mientras WSL está encendido. Si WSL está apagado, la siguiente hora en la que
esté encendido recupera todo lo pendiente.

Si cambias el código de la web (`web/src`), recompila:

```bash
cd web && npm install && npm run build   # genera site/index.html (un solo archivo)
npm run dev                               # desarrollo con recarga en caliente
```

## Línea de comandos

```bash
uv run garmin-stats all        # sincroniza y actualiza la web
uv run garmin-stats sync       # solo descarga (la 1.ª vez todo el histórico, después lo nuevo)
uv run garmin-stats report     # solo recalcula el análisis y reescribe site/data.js
```

Opciones de `sync`: `--no-intraday` (sin FC cada 2 min), `--no-fit` (sin archivos FIT),
`--pause 0.35` (segundos entre peticiones).

Salida:

- `site/index.html` y `site/data.js` — la web y sus datos.
- `reports/resumen-AAAA-MM-DD.md` — conclusiones en texto.
- `data/garmin.sqlite` — todo en local:
  - `raw`: JSON tal cual lo da Garmin (dataset, clave, payload).
  - `t_daily`, `t_sleep`, `t_hrv`, `t_weight`, `t_activities`, `t_activity_metrics`,
    `t_load`, `t_day`: tablas limpias para consultar con SQL o pandas.
  - `fit_records`: registros segundo a segundo de cada actividad (FC, velocidad, cadencia, altitud, potencia).
- `data/fit/<id>.fit` — archivo original de cada actividad.

## Credenciales

- Clave: `~/.config/garmin/connect-personal-api-key` (permisos 600). Caduca el **29-10-2027**;
  Garmin avisa por email una semana antes. Se crea o renueva en
  <https://connect.garmin.com/app/settings/personalApiToken>.
- Token de 24 h: `~/.config/garmin/connect-personal-api-bearer-token.json`. Se renueva solo.
- Ninguna de las dos está dentro del proyecto.

## Qué da la API personal (probado el 29-10-2026)

| Dato | Endpoint | Rango máx. por petición |
|---|---|---|
| Resumen diario (pasos, FC reposo/mín/máx, estrés, Body Battery, calorías, minutos de intensidad, respiración, SpO2, pisos) | `usersummary-service/v2/dailysummaries` | ~1 año |
| Sueño (fases, puntuación, necesidad de sueño, SpO2, respiración, estrés nocturno) | `sleep-service/sleep/dailySleepSummariesByDate` | 28-31 días |
| HRV nocturna (media, pico 5 min, rango normal, estado) | `hrv-service/hrv/daily/{a}/{b}` | ~1 año |
| HRV cada 5 min de una noche | `hrv-service/hrv/{fecha}` | 1 día |
| Body Battery a lo largo del día | `wellness-service/wellness/bodyBattery/reports/daily` | 28-31 días |
| FC cada 2 min | `wellness-service/wellness/dailyHeartRate` | 1 día |
| SpO2 | `wellness-service/wellness/daily/spo2acclimation/{fecha}` | 1 día |
| Pasos / estrés / hidratación | `usersummary-service/stats/...` | 28 días |
| Peso | `weight-service/weight/range` | 28 días |
| Edad física | `fitnessage-service/fitnessage/v2/{fecha}` | 1 día |
| Zonas de FC, perfil | `biometric-service/heartRateZones/v2`, `userprofile-service/userprofile/settings` | – |
| Actividades (lista, detalle, archivo FIT original) | `activitylist-service`, `activity-service/activity/{id}`, `download-service/files/activity/{id}` | 100 por página |
| Series de una actividad (muestreadas) | `activity-service/activity/{id}/details` | – |

**No disponible** (HTTP 404 en la API personal): Training Readiness, Training Status, carga
aguda, VO2max, predicciones de carrera, récords, dispositivos, equipo, entrenamientos, insignias.
Por eso:

- El **VO2max** se lee del FIT de cada actividad (mensaje 140, campo 7 × 3,5 / 65536; no documentado
  por Garmin).
- La **carga** se calcula con TRIMP de Banister a partir del pulso segundo a segundo, junto con
  forma (CTL 42 d), fatiga (ATL 7 d), frescura (TSB) y ACWR.
- Las **predicciones** usan la fórmula de Daniels con el VO2max del reloj.

## Análisis del informe

- Sueño: duración, fases, puntuación, horario, regularidad, jet lag social y día de la semana.
- Corazón: FC en reposo, HRV frente a tu rango normal, estrés y Body Battery.
- Entrenamiento: volumen semanal por deporte, zonas de pulso por mes, TRIMP/CTL/ATL/TSB y ACWR.
- Carrera: VO2max, km por semana, eficiencia aeróbica (m/min por latido), desacople en tiradas
  largas, cadencia, mejores tramos y predicciones.
- Relaciones (Spearman, con desfase de un día): sueño → HRV/FC en reposo, carga → HRV, estrés → sueño, pasos → sueño.

## Textos con IA (Claude)

Los titulares, las tarjetas "Para ti" y las observaciones de cada página los escribe Claude
Haiku 5.5 con tono Google Health (`src/garmin_stats/ai.py`).

- Clave: `~/.config/anthropic/garmin-stats-key` (permisos 600, fuera del proyecto).
- Coste: un resumen de unos 4k tokens y unos 1,5k de respuesta, menos de 0,002 $ por llamada.
  Solo se llama cuando cambia el día, la última noche o la última actividad, y como máximo 3 veces
  al día. Unos 5 céntimos al mes. El gasto real queda en `data/ai_usage.log`.
- Caché: `data/ai_cache.json`. Si la API falla (sin saldo, sin red), se usa el último texto o, si
  no hay ninguno, los textos por reglas.
- `uv run garmin-stats report --force-ai` regenera ahora; `--no-ai` lo desactiva.

## Servidor local y chat con la IA

La web se usa desde **http://localhost:8765**. El servidor (`garmin-stats serve`) solo escucha en
este ordenador y hace dos cosas:

- sirve la web y sus datos, siempre sin caché;
- responde al chat en `/api/ask`. La clave de Anthropic se queda en el servidor y el navegador nunca
  la ve.

Cron lo arranca al encender (`@reboot`) y comprueba cada 5 minutos que siga vivo (`bin/serve.sh`).
El log está en `data/serve.log`. El chat cuesta unos 0,0006 $ por pregunta, con un máximo de
80 preguntas al día. Abriendo `site/index.html` como archivo, la web sigue funcionando sin el chat.

## Funciones de la web

- **Preparación diaria (0-100):** HRV 30 %, sueño 30 %, pulso en reposo 20 % y carga 20 %, frente a tus
  últimas 28 mediciones (`extras.readiness`).
- **Avisos:** pulso en reposo alto, HRV baja dos noches seguidas, falta de sueño, subida brusca de
  carga y Body Battery bajo (`extras.alerts`).
- **Objetivos de la semana y rachas:** sueño de 7 h, objetivo de pasos, 150 minutos de intensidad y 3
  entrenos.
- **Tu semana:** comparación con la semana anterior y resumen de la IA, una llamada por semana.
- **Detalle de cada actividad** (pulsa en cualquier actividad): mapa (Esri), pulso, ritmo, altitud,
  zonas, parciales por km y técnica de carrera. Se genera desde los FIT en `site/acts/<id>.js`.
- **Progreso:** últimos 30 días frente a los 30 anteriores, año frente a año, calendario de
  actividad y récords.

## Plan de entreno con IA (pestaña Plan)

- **Crear:** eliges objetivo, fecha, tiempo objetivo, días por semana, día de la tirada larga y notas.
  Claude Opus 5.5 diseña el plan semana a semana a partir de tu nivel real (`coach.profile`): km
  recientes, tirada más larga, ritmo suave real, VO2max, marcas y preparación.
- **Cada día:** se compara cada sesión con tus actividades (hecha, a medias, no hecha) y se da un consejo
  según tu preparación (`coach.today_advice`, sin IA). Puedes valorar cada sesión de 1 a 5.
- **Cada lunes** (primer informe de la semana) o con el botón "Reajustar ahora": Opus revisa lo hecho, tus
  valoraciones, la HRV y los ritmos reales, reajusta las semanas que quedan y actualiza su **memoria**:
  hasta 12 aprendizajes sobre ti, que reutiliza en cada ajuste y en el chat.
- Estado en `data/coach.json` (plan, historial de ajustes, valoraciones y memoria).

## Modelos y gasto

| Uso | Modelo |
|---|---|
| Plan (crear y reajustar) | Claude Opus 5.5 |
| Chat, textos diarios, resumen semanal | Claude Sonnet 5.5 |
| Reserva al llegar a 40 $ en el mes | Claude Haiku 5.5 |

Presupuesto de 50 $ al mes (`ai.MONTHLY_BUDGET`). Opus y Sonnet usan alternativas automáticas del
servidor (`fallbacks: "default"`). El gasto real por tipo y por mes aparece en Análisis → Uso de la IA.

## Copias de seguridad

`bin/backup.sh` (cron, domingos a las 21:30) guarda la base de datos (copia en caliente), el plan, la caché
de la IA y el registro de gasto en `C:\Users\garrigas\OneDrive\Backups\garmin_stats` (OneDrive
**personal**). Conserva las 8 copias más recientes. Para restaurar: descomprimir el `.tar.gz` en `data/`.
Los FIT no se copian: `garmin-stats sync` los vuelve a descargar.

## Web en AWS (privada, con login de Google)

Desplegada con un solo stack de CloudFormation (`infra/stack.yaml`) en la cuenta personal 123456789012,
región eu-west-1. Diseño completo en `docs/aws.md`.

- URL: https://xxxxxxxxxxxxxx.cloudfront.net (solo entra `tu@gmail.com`).
- Desplegar o actualizar: `infra/deploy.sh` (idempotente; empaqueta las Lambda y sube la web).
- Cada hora `bin/update.sh` baja el estado de AWS (`bin/aws-sync.sh down`), genera el informe y sube la
  web y el estado (`bin/aws-sync.sh up`).
- Seguridad: una CloudFront Function comprueba la cookie de sesión (HMAC) antes de servir nada. S3 es
  privado (OAC) y las Lambda solo aceptan la cabecera secreta de CloudFront. Los secretos están en
  `~/.config/garmin/aws-secrets.json` y en SSM.
- Cliente OAuth de Google: `~/.config/garmin/google-oauth.json` (`{"client_id": …, "client_secret": …}`),
  que `infra/deploy.sh` sube a SSM.
- Presupuesto de AWS: aviso por email al 80 % de 5 $ (es de toda la cuenta).
