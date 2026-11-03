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
