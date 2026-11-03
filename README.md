# garmin_stats

Mi web privada de salud con los datos de mi Garmin. **Todo corre en AWS** (cuenta personal de AWS,
eu-west-1, stack de CloudFormation `garmin-stats`); en el PC solo queda el código.

- Web: https://xxxxxxxxxxxx.cloudfront.net. Solo entra el email del dueño (`OWNER_EMAIL` en `~/.config/garmin/deploy.env`) (login de Google).
- Cada hora (minuto 5, hora de Madrid) la Lambda `garmin-stats-sync` descarga lo nuevo de Garmin, recalcula,
  escribe los textos con IA (y los lunes reajusta el plan) y publica la web en S3.
- El chat y el plan: Lambda `garmin-stats-api`. Login: Lambda `garmin-stats-auth`.
- Datos: bucket privado `garmin-stats-site-<cuenta>` (`state/` con la base de datos, el plan, la
  memoria y los FIT originales; `site/` con la web). Versionado, con 3 días de versiones antiguas.
- Desplegar cambios: `infra/deploy.sh`. Para cambiar la web: `cd web && npm ci && npm run build`
  y después `infra/deploy.sh`, que publica `site/index.html`.
- Claves (solo en este PC, para desplegar): `~/.config/garmin/connect-personal-api-key`,
  `~/.config/anthropic/garmin-stats-key`, `~/.config/garmin/google-oauth.json` y
  `~/.config/garmin/aws-secrets.json`. En AWS están en SSM Parameter Store, cifradas.
- Coste de AWS: prácticamente 0 $ al mes (capa gratuita). La IA tiene un presupuesto de 50 $ al mes.

> Lo que sigue describe los módulos y la historia del proyecto. Las secciones de "servidor local" y "cron"
> quedaron obsoletas el 30-10-2026, cuando todo pasó a AWS.

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

Si cambias el código de la web (`web/src`), reinstala las dependencias (se borraron para ahorrar espacio) y recompila:

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

## Servidor local y chat con la IA (desactivado)

Ahora la web se usa en AWS (más abajo). El servidor local está parado y fuera de cron desde el 30-10-2026;
para volver a usarlo: `uv run garmin-stats serve` y abrir **http://localhost:8765**. El servidor (`garmin-stats serve`) solo escucha en
este ordenador y hace dos cosas:

- sirve la web y sus datos, siempre sin caché;
- responde al chat en `/api/ask`. La clave de Anthropic se queda en el servidor y el navegador nunca
  la ve.

Antes cron lo arrancaba con `bin/serve.sh` (`@reboot` y cada 5 minutos); esas entradas se han quitado.
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

Desactivadas a petición del usuario (30-10-2026): no hay copia en OneDrive. `bin/backup.sh` sigue en el
repositorio por si se quiere reactivar.

## Web en AWS (privada, con login de Google)

Desplegada con un solo stack de CloudFormation (`infra/stack.yaml`) en la cuenta personal de AWS,
región eu-west-1. Diseño completo en `docs/aws.md`.

- URL: https://xxxxxxxxxxxx.cloudfront.net (solo entra el email del dueño (`OWNER_EMAIL` en `~/.config/garmin/deploy.env`)).
- Desplegar o actualizar: `infra/deploy.sh` (idempotente; empaqueta las Lambda y sube la web).
- Cada hora `bin/update.sh` baja el estado de AWS (`bin/aws-sync.sh down`), genera el informe y sube la
  web y el estado (`bin/aws-sync.sh up`).
- Seguridad: una CloudFront Function comprueba la cookie de sesión (HMAC) antes de servir nada. S3 es
  privado (OAC) y las Lambda solo aceptan la cabecera secreta de CloudFront. Los secretos están en
  `~/.config/garmin/aws-secrets.json` y en SSM.
- Cliente OAuth de Google: `~/.config/garmin/google-oauth.json` (`{"client_id": …, "client_secret": …}`),
  que `infra/deploy.sh` sube a SSM.
- Presupuesto de AWS: aviso por email al 80 % de 5 $ (es de toda la cuenta).

## App instalable, avisos, gimnasio y alarmas (30-10-2026)

- **App instalable (PWA):** `web/public/manifest.webmanifest`, `sw.js` e `icons/`. En el menú (arriba a la derecha):
  "Instalar la app" (Android/Chrome) o instrucciones para el iPhone (Safari → Compartir → Añadir a pantalla de inicio).
- **Aviso de la mañana:** Web Push cada día a las 7:30 (hora de Madrid, Lambda `garmin-stats-notify`) con la preparación y
  la sesión del día. Se activa desde el menú con "Avisos de la mañana". En el iPhone, primero hay que instalar la app.
  Claves VAPID en `~/.config/garmin/vapid.json` y en SSM; suscripciones en `state/push.json`.
- **Gimnasio:** las series que registra el reloj (ejercicio, repeticiones y kg) se leen de los FIT (`extras.parse_sets`) y
  se ven en el detalle de cada sesión. El coach las usa para subir cargas o repeticiones.
- **Peso:** el que apuntas en Garmin Connect, en Progreso → Peso; el coach ve la tendencia.
- **Alarmas por email** (SNS `garmin-stats-alerts`): la sincronización falla 2 horas seguidas, lleva 3 horas sin
  ejecutarse o falla el aviso de la mañana. Hay que confirmar la suscripción en el email de AWS.

## Entrenos al reloj (archivos FIT)

La API personal de Garmin es de solo lectura (no se pueden crear entrenos ni ponerlos en el calendario: 404). Por eso:
- Cada sesión de carrera del plan lleva un entreno estructurado (`workout`: bloques y pasos con distancia o tiempo y
  ritmo o pulso objetivo). Los planes nuevos lo traen de Opus; en los existentes, `POST /api/plan/structure` lo genera
  por semana con Sonnet.
- En Plan, el botón **"Pasar al reloj"** genera en el navegador los `.fit` de entrenamiento (SDK oficial `@garmin/fitsdk`,
  `web/src/workouts.ts`) y los descarga en un .zip.
- Gimnasio: cada sesión de fuerza se convierte en ejercicios del catálogo oficial de Garmin (52 categorías y 1.846
  ejercicios, en `src/garmin_stats/garmin_exercises.json`, extraído del SDK). La IA identifica categoría y nombre, y el
  código busca el ejercicio exacto. Cada ejercicio es un bloque [serie con repeticiones o tiempo y peso, descanso] x series.
- Para pasarlos: conectar el reloj por USB → `GARMIN/NewFiles` → copiar los `.fit` → aparecen en Entrenamiento → Entrenamientos.

## Últimos cambios (30-10-2026)

- **Nivel del plan:** "Realista" o "🔥 Exigente" (selector en Plan y al crear un plan). En modo exigente el coach
  mantiene tu tiempo objetivo, sube el volumen hasta un +12 % semanal, pone 2 sesiones de calidad y tiradas con
  bloques a ritmo de carrera, sin quitar las descargas ni los avisos por preparación baja (`POST /api/plan/ambition`).
- **Portada solo con datos de hoy:** si Garmin aún no tiene la noche o el día de hoy, se muestra "—" con "sin datos
  de anoche" o "sin datos de hoy", nunca los valores de ayer. La preparación avisa de que falta sincronizar.
- **Uso de la IA:** desglose por tipo y modelo con nombres claros. El registro (`state/ai_usage*.log`) apunta cada
  llamada con los tokens que devuelve la API, incluidas la escritura y la lectura de caché, así que cuadra con la
  factura de Anthropic.
- **Alarmas:** para probar el email sin provocar un fallo real:
  `aws cloudwatch set-alarm-state --alarm-name garmin-stats-sync-falla --state-value ALARM --state-reason "Prueba"`.
  Vuelve sola a OK en la siguiente comprobación y también avisa por email.

## Actualizar ahora (01-11-2026)

- Botón de actualizar en la barra (móvil y escritorio) y gesto de deslizar hacia abajo en el móvil.
- `POST /api/sync` lanza la Lambda `garmin-stats-sync` en el momento (~30-40 s); `GET /api/sync` da el estado.
- `state/sync_status.json` hace de candado: nunca corren dos sincronizaciones a la vez (botón y la de cada hora),
  una pulsación repetida espera a la que ya está en marcha y en los 45 s siguientes a terminar no se vuelve a llamar a Garmin.
- La IA solo reescribe los textos si hay datos nuevos y con límite diario, así que actualizar a menudo no gasta más.
- Ojo: trae lo que ya está en Garmin Connect. Si el reloj no se ha sincronizado con la app del móvil, no hay nada nuevo.

## Versión multipersona (01-11-2026)

La web admite personas invitadas (pensado para unos 5 amigos y amigas). Cada persona entra con su Google, conecta su propio Garmin y ve
**solo sus datos**.

**Invitar a alguien**
1. En la web, menú (icono del tema) → **Invitaciones** → nombre + email de Google → Invitar. Copia el mensaje y envíaselo.
2. Mientras la app de Google OAuth esté en modo de prueba, añade también su email en Google Cloud Console →
   Google Auth Platform → Público → **Usuarios de prueba** (si no, Google le muestra "Acceso bloqueado").
3. La persona invitada entra, acepta el aviso de privacidad, crea su clave en Garmin Connect
   (<https://connect.garmin.com/app/settings/personalApiToken>, caducidad 1 año), la pega, elige su objetivo y listo:
   la primera descarga tarda unos minutos y después el coach crea su plan.

**Cómo está montado**
- Registro: `s3://…/admin/users.json` (dueño + personas invitadas, tope de IA por persona, estado).
  El login solo deja entrar a quien está ahí.
- Datos privados: `users/<uid>/state/` (SQLite, plan, chat, gasto de IA, avisos). Web: `site/u/<uid>/`.
  El `uid` es un HMAC del email.
- CloudFront: la función de la cookie reescribe `/data.js` y `/acts/*` a la carpeta de esa persona.
  Pedir `/u/...` directamente da 404.
- Clave de Garmin: SSM SecureString `/garmin-stats/users/<uid>/garmin-key`. Si Garmin la rechaza, el estado pasa a
  `key_invalid` y la web le pide una nueva (sin alarmas por email).
- Sincronización: la programada lanza una ejecución por persona. La primera descarga va por tandas de ~7 min que se
  encadenan solas; al terminar se crea el plan si dejó objetivo.
- IA: tope mensual por persona (5 $ cada persona invitada, 50 $ el dueño). Al 80 % pasa a Haiku, al 100 % se pausa hasta el
  día 1. A las personas invitadas el reajuste semanal se lo hace Sonnet (el plan inicial, Opus).
- Borrar: cada persona invitada puede borrar su cuenta desde el menú y el dueño puede quitarla desde Invitaciones. Se borran todas
  las versiones de sus archivos, su clave y su entrada del registro.
- `infra/migrate_multiuser.sh`: migración única de los datos del dueño (ya ejecutada el 01-11-2026).

## Ritmos, gimnasio, natación, calendario y cómo te encuentras (02-11-2026)

Ideas tomadas de otra app de entrenamiento y escritas de nuevo aquí (solo fórmulas públicas: Daniels, Epley, CSS).

- **Energía de ahora:** la portada muestra la Body Battery **actual** (`bodyBattery.latestValue`) con la hora del último
  dato del reloj, y la curva del día (energía y pulso). Antes enseñaba el máximo de la mañana. Si el último dato tiene
  más de 90 min, avisa: Garmin solo recibe datos cuando el reloj se sincroniza con el móvil (`extras.live`, `data.live`).
- **Hora de Madrid en AWS:** las Lambda iban en UTC (de 0:00 a 1:00/2:00 "hoy" era ayer). Ahora fijan
  `TZ=CET-1CEST,M3.5.0,M10.5.0/3` (regla POSIX, no necesita tzdata).
- **Ritmos y zonas** (Entreno → Ritmos, `training.paces_block`): VDOT de Daniels a partir de tu marca (si la pones), si no
  de tu mejor tramo de los últimos 90 días, si no del VO2max del reloj. Da 8 ritmos de referencia, 5 zonas de ritmo y
  los tiempos que puedes correr. Los pasos del plan llevan `pace_ref` (p. ej. "ritmo de 10K − 5 s"): la web, el reloj
  (FIT) y el calendario calculan el ritmo con tus referencias **actuales**, así el plan se ajusta solo cuando mejoras.
- **Natación** (`training.swim_block`): CSS con el test de 400 + 200 m (o estimado con tu mejor nado continuo), 5 zonas
  por 100 m, metros por semana y SWOLF. El coach puede programar sesiones `swim` (sin archivo para el reloj).
- **Gimnasio** (Entreno → Gimnasio, `training.gym_block`): 1RM estimado (Epley, series de hasta 12 repeticiones),
  series por músculo y semana (los músculos que ayudan cuentan media serie), kilos totales y récords por ejercicio.
- **Cumplimiento fino** (`coach._match`): % de distancia o tiempo, segundos por km más rápido o lento que lo previsto y
  series hechas frente a las previstas. Cuenta como hecha a partir del 85 %.
- **Cómo te encuentras** (portada): ánimo y agujetas de 1 a 5, nota, y molestias o lesiones (zona, intensidad, fechas).
  Se guarda en `state/wellness.json`. El consejo del día y el reajuste del plan lo tienen en cuenta.
- **Calendario:** Plan → icono de calendario → enlace privado `/api/cal/<código>.ics` para Google Calendar, iPhone u
  Outlook. CloudFront lo deja pasar sin cookie solo con ese formato; el código se puede cambiar o desactivar
  (`calToken` en `admin/users.json`).
- API nueva: `POST /api/settings/race`, `/api/settings/swim`, `/api/wellness`, `/api/injury`, `GET|POST /api/calendar`.
  Tras cada cambio la API recalcula esos bloques en `data.js` (sin esperar a la sincronización). La sincronización solo
  **lee** `settings.json` y `wellness.json` (nunca los sube, para no pisar lo que guardes mientras corre).
- Pruebas: `uv run --with pytest pytest -q` (fórmulas, natación, gimnasio, registro, calendario, cumplimiento, energía).

## Tu tiempo y el tiempo que hará (03-11-2026)

- **Tu tiempo, día a día** (Plan → "Tu tiempo"): minutos que tienes cada día de la semana (L-D, con atajos Libre / 30 min /
  … / 3 h / Nada) y excepciones para fechas concretas (hoy 2 h, mañana 45 min). Se guarda en `settings.json`
  (`availability = {"weekly": {"0".."6": minutos | null}, "days": {"AAAA-MM-DD": minutos}}`; null = sin límite, 0 = nada;
  0-480 min; días de hoy a 8 semanas, los pasados se borran al guardar). Guardar no llama a la IA: el plan se ajusta
  el lunes o con "Reajustar el plan con mi tiempo". El coach recibe `tiempo_disponible_por_dia` para cada fecha
  planificada y reglas para encajar cada día; después, una comprobación sin IA (`coach.time_conflicts`) marca los días
  que no caben (`timeWarnings` en el plan, aviso "No cabe" en cada día).
- **El plan mira el tiempo que hará** (Plan → "El tiempo que hará"): eliges tu ciudad (buscador con
  `GET /api/geo?q=`; o la zona de tu última carrera, redondeada a ~10 km) y se guarda en `settings.json` (`location`,
  solo nombre y coordenadas de ciudad). `src/garmin_stats/weather.py` pide a **Open-Meteo** (sin clave) la previsión de
  16 días como mucho cada ~3 h (sincronización, cambio de ciudad y antes de reajustar) y la resume por día en
  `state/weather.json`: mínima/máxima, sensación, lluvia, viento, cielo, amanecer/anochecer y las mejores franjas para
  correr entre las 06:00 y las 22:00. El coach recibe `tiempo_previsto` y reglas (calor → franja fresca y más lento;
  tormenta, lluvia fuerte o viento → cambiar de día o cinta/gimnasio/natación; frío u oscuridad → capas y visibilidad);
  cada sesión puede llevar `weather_note` y `best_time`. A mitad de semana no se llama a la IA: el consejo del día
  (`weather.advice`) avisa si la sesión de hoy choca con la previsión y propone franja o cambio de día. Si Open-Meteo no
  responde, todo funciona como antes, sin previsión.
- **Licencia de Open-Meteo:** el plan gratuito es solo para uso no comercial. Si Runch pasa a ser comercial hay que
  contratar su plan de pago o cambiar de proveedor.
- API nueva: `POST /api/settings/availability`, `POST /api/settings/location` (`{"clear": true}` para quitar),
  `GET /api/geo?q=`. data.js lleva `availability`, `weather` y `lastRunArea`.
- Pruebas: `tests/test_time_weather.py` (validación, franjas, caché, consejo del día, prompts, comprobación y rutas de la API).

## Novedades de cada versión (pantalla "Novedades")

La primera vez que cada persona entra después de publicar una versión con novedades, la web le enseña una pantalla
"Novedades" (a pantalla completa en el móvil). Se ve **una vez por persona**: al pulsar Continuar se guarda en su
cuenta (`seenRelease` en `admin/users.json`, `POST /api/whatsnew/seen`), así que no vuelve a salir en otro dispositivo.
Quien se da de alta después de la fecha de la versión no la ve. Siempre se puede abrir desde el menú → **Novedades**.

**Cada vez que se publiquen novedades:** añadir una entrada al principio de `RELEASES` en `web/src/whatsnew.tsx`
(id nuevo `AAAA-MM-DD`, título, subtítulo y 3-7 novedades con icono, color, texto corto y la página a la que llevan),
compilar la web y desplegar. Sin entrada nueva no se anuncia nada.
