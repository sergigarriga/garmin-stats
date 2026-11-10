# Web en AWS solo para mí (diseño)

Cuenta personal de AWS (perfil `default`, usuario IAM propio).

## Objetivo

Abrir la web desde cualquier navegador (móvil incluido) con login de Google, de modo que solo
el email del dueño (`OWNER_EMAIL` en `~/.config/garmin/deploy.env`) pueda descargar cualquier archivo, y con un coste de casi 0 $ al mes.

## Arquitectura

```
Navegador ──HTTPS──> CloudFront (xxxx.cloudfront.net)
                      ├─ /auth/*   → Lambda "auth" (Function URL, sin firma)
                      │              login con Google (OAuth) → comprueba el email permitido
                      │              → pone la cookie de sesión gs_session (HMAC, 30 días)
                      ├─ /api/*    → Lambda "api" (chat, plan)       [CloudFront Function comprueba la sesión]
                      └─ /*        → S3 privado (web + data.js + acts/)  [CloudFront Function + OAC]
EventBridge Scheduler (cada hora) → Lambda garmin-stats-sync → Garmin API → S3 (state/ + site/)
```

- **Sin Cognito y sin Lambda@Edge:** una CloudFront Function (viewer-request) comprueba la cookie `gs_session`
  (email + caducidad + HMAC-SHA256) y que el email esté permitido. Sin sesión válida no sale ni un byte de S3
  ni de la API (302 al login o 401).
- **Lambda auth:** flujo OAuth de Google (authorization code + PKCE). Valida el `id_token` y que el
  email sea el permitido y esté verificado. Firma la cookie con el secreto de sesión
  (parámetro NoEcho del stack).
- **Lambda api:** el mismo código de `server.py` (chat) y `coach.py` (plan), con la clave de Anthropic en SSM.
  - El estado del coach (`coach.json`) pasa a S3 como fuente única. El PC lo lee de ahí al generar el informe.
  - Crear y reajustar el plan tarda unos 3 minutos y CloudFront corta a los 60 s, así que se hace en
    asíncrono: el POST lanza la Lambda en segundo plano y devuelve 202, y la web consulta `/api/plan` hasta
    que esté listo.
  - El reajuste de los lunes: EventBridge Scheduler → Lambda api.
- **Región:** eu-west-1 para S3, Lambda y SSM; CloudFront es global.

## Coste estimado

| Servicio | Coste |
|---|---|
| S3 (~20 MB) | ~0,01 $ |
| CloudFront | 0 $ (capa gratuita: 1 TB al mes) |
| Lambda | 0 $ (capa gratuita) |
| SSM Parameter Store estándar | 0 $ |
| EventBridge Scheduler | 0 $ |
| **Total AWS** | **< 0,10 $ al mes** |

Más una alarma de presupuesto de AWS a 5 $.

## Lo que hace falta del dueño

1. **Cliente OAuth de Google** (console.cloud.google.com → APIs y servicios → Credenciales):
   - Pantalla de consentimiento: tipo Externo, en modo "Testing", con el email del dueño (`OWNER_EMAIL` en `~/.config/garmin/deploy.env`) como usuario de prueba.
     (Esto es solo el **login**, que pide nombre y email y no usa refresh tokens. El cliente de **Google Health** va en
     otro proyecto y su pantalla de consentimiento se publica **"En producción"**: ver "Google Health como fuente de datos".)
   - Crear credenciales → ID de cliente de OAuth → Aplicación web.
   - URI de redirección autorizada: `https://<dominio de CloudFront>/auth/callback` (se conoce al crear la distribución).
   - Guardar el ID y el secreto directamente en `~/.config/garmin/google-oauth.json` (sin pegarlos en el chat).
2. Confirmar la región eu-west-1.

## Estado final (30-10-2026)

Desplegado. Sincronización 100 % en AWS (Lambda `garmin-stats-sync`, 1 GB, unos 22 s por ejecución, todo en
la capa gratuita). El PC no ejecuta nada y no guarda datos. Pruebas de acceso superadas: sin sesión, con firma
falsa, con otro email, con la sesión caducada o accediendo directamente a S3 o a las Lambda se recibe 302, 401
o 403.

## Catálogo de la lista de la compra (03-11-2026)

Lambda `garmin-stats-catalog` (EventBridge Scheduler, lunes 05:00 hora de Madrid, sin reintentos) → tienda de Mercadona
(con su permiso, pocas peticiones) → `admin/catalog/` del bucket privado, que solo lee la Lambda de la API. Detalle en el
README ("Menú y compra de la semana").

## Google Health como fuente de datos (10-11-2026)

Para personas sin Garmin. Flujo y contrato de la API en el README ("Google Health en lugar de Garmin").

```
Web ── GET /api/google/connect ──> Lambda api ──302──> Google (OAuth + PKCE, solo lectura)
Google ──302──> /api/google/callback ──> Lambda api: código → refresh token → SSM users/<uid>/google-token
EventBridge (cada hora) → Lambda sync → refresh token → access token → health.googleapis.com/v4 → S3 (state/ + site/)
```

- La CloudFront Function de la sesión copia el dominio público en `x-viewer-host` para `/api/*`: la dirección de vuelta
  que se manda a Google sale de ahí (tiene que coincidir con la registrada).
- Parámetros nuevos (los lee la Lambda api, cacheados, y la sync): `/garmin-stats/google-health-client-id` (String) y
  `/garmin-stats/google-health-client-secret` (SecureString). Sin ellos, `/api/me` devuelve `google.available: false`
  y no pasa nada: se puede desplegar antes de preparar Google Cloud.
- Límites de Google: sin verificar la app, como mucho **100 personas** y 2,5 peticiones/s por persona.
- La pantalla de consentimiento del proyecto de Google Health se publica **"En producción"** (sin verificar): en
  modo "Testing" los permisos caducan a los **7 días** y cada persona tendría que reconectar cada semana. Publicada
  pero sin verificar no caducan; Google enseña el aviso "Google no ha verificado esta app" (Avanzado → Ir a Runch)
  y el tope sigue siendo de 100 personas, que basta para las invitaciones.
  Para abrirlo a más gente hace falta la verificación de Google y una auditoría de seguridad anual (CASA).
- Cada persona tiene que haber entrado una vez en la app **Google Health** del móvil con su cuenta de Google
  (si no, la API responde `ACCOUNT_NOT_LINKED` y su estado queda en `google_not_linked`).

### Lo que hace falta del dueño (una vez)

1. console.cloud.google.com → **proyecto nuevo** (p. ej. `runch-health`), aparte del del login: así la revisión de
   permisos de salud no afecta al login.
2. APIs y servicios → Biblioteca → **Google Health API** → Habilitar.
3. Google Auth Platform → Branding: nombre Runch, email de soporte, logo, dominio de la web, enlaces a
   `https://<dominio>/auth/privacidad` y `https://<dominio>/auth/condiciones`.
4. Público: tipo **Externo** → **Publicar app** → estado **"En producción"** (no "Testing": ahí el permiso caduca a
   los 7 días). No hace falta pedir la verificación mientras sean menos de 100 personas.
5. Acceso a datos → Añadir permisos: `googlehealth.activity_and_fitness.readonly`,
   `googlehealth.health_metrics_and_measurements.readonly` y `googlehealth.sleep.readonly` (nada más).
6. Clientes → Crear cliente → **Aplicación web** → URI de redirección autorizada:
   `https://<dominio>/api/google/callback` (salida `GoogleHealthRedirectUri` del stack). Descargar el JSON.
7. Guardar el ID y el secreto en SSM (región eu-west-1), sin pegarlos en ningún chat:
   ```bash
   J=~/.config/garmin/google-health-oauth.json   # el JSON descargado (chmod 600)
   aws ssm put-parameter --name /garmin-stats/google-health-client-id --type String --overwrite \
     --value "$(python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(d.get('web', d)['client_id'], end='')" "$J")"
   f=$(mktemp); trap 'rm -f "$f"' EXIT   # archivo temporal privado (0600) que se borra pase lo que pase
   python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(d.get('web', d)['client_secret'], end='')" "$J" > "$f"
   aws ssm put-parameter --name /garmin-stats/google-health-client-secret --type SecureString --overwrite --value "file://$f"
   ```
8. Desplegar (`infra/deploy.sh`): actualiza la CloudFront Function, las variables y los permisos de las Lambdas, y
   pasa el dominio público (`PublicHost`, sacado de la salida `Url` del stack, o `PUBLIC_HOST` en `deploy.env` si hay
   dominio propio). La API solo acepta ese dominio como vuelta de Google. La Lambda api vuelve a mirar los
   parámetros de SSM como mucho cada 5 minutos.
