# Web en AWS solo para mí (diseño)

Cuenta personal 123456789012 (perfil `default`, usuario IAM `Sergi`). Nunca en cuentas de la empresa.

## Objetivo

Abrir la web desde cualquier navegador (móvil incluido) con login de Google, de modo que solo
`tu@gmail.com` pueda descargar cualquier archivo, y con un coste de casi 0 $ al mes.

## Arquitectura

```
Navegador ──HTTPS──> CloudFront (xxxx.cloudfront.net)
                      ├─ /auth/*   → Lambda "auth" (Function URL, sin firma)
                      │              login con Google (OAuth) → comprueba el email permitido
                      │              → pone cookies firmadas de CloudFront (30 días)
                      ├─ /api/*    → Lambda "api" (chat, plan)       [exige cookie firmada]
                      └─ /*        → S3 privado (web + data.js + acts/)  [exige cookie firmada, OAC]
EventBridge Scheduler (cada hora) → Lambda garmin-stats-sync → Garmin API → S3 (state/ + site/)
```

- **Sin Cognito y sin Lambda@Edge:** CloudFront comprueba las cookies firmadas (trusted key group).
  Sin cookie válida no sale ni un byte de S3 ni de la API.
- **Lambda auth:** flujo OAuth de Google (authorization code + PKCE). Valida el `id_token` y que el
  email sea el permitido y esté verificado. Firma las cookies con la clave privada de CloudFront,
  guardada en SSM Parameter Store (SecureString).
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

## Lo que hace falta de Sergi

1. **Cliente OAuth de Google** (console.cloud.google.com → APIs y servicios → Credenciales):
   - Pantalla de consentimiento: tipo Externo, en modo "Testing", con `tu@gmail.com` como usuario de prueba.
   - Crear credenciales → ID de cliente de OAuth → Aplicación web.
   - URI de redirección autorizada: `https://<dominio de CloudFront>/auth/callback` (se conoce al crear la distribución).
   - Guardar el ID y el secreto directamente en `~/.config/garmin/google-oauth.json` (sin pegarlos en el chat).
2. Confirmar la región eu-west-1.

## Pasos de construcción

1. Bucket S3 privado + OAC; par de claves RSA → clave pública y key group en CloudFront; clave privada en SSM.
2. Lambda auth y Lambda api (Python 3.12, dependencias en una capa) y sus Function URLs.
3. Distribución de CloudFront con tres comportamientos (`/auth/*`, `/api/*` y por defecto).
4. Web: detectar el modo AWS (API relativa `/api`), polling del plan y botón de cerrar sesión.
5. `bin/update.sh`: tras el informe, `aws s3 sync site/ s3://… --delete` e invalidar `index.html` y `data.js`.
6. Presupuesto de AWS a 5 $ con aviso por email. Prueba: sin cookie se recibe 403; con otro email, acceso denegado.


## Estado final (30-10-2026)

Desplegado. Sincronización 100 % en AWS (Lambda `garmin-stats-sync`, 1 GB, unos 22 s por ejecución, todo en
la capa gratuita). El PC no ejecuta nada y no guarda datos. Pruebas de acceso superadas: sin sesión, con firma
falsa, con otro email, con la sesión caducada o accediendo directamente a S3 o a las Lambda se recibe 302, 401
o 403.
