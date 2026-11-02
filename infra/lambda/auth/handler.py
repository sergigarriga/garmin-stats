"""Login con Google para la web (Lambda detrás de CloudFront, ruta /auth/*).

Flujo OAuth "authorization code" + PKCE. El id_token llega directamente de Google por TLS, así que
basta con comprobar emisor, audiencia, caducidad y email (lo permite la especificación de OpenID).
Si el email está en el registro de usuarias (S3 admin/users.json, lo gestiona el dueño desde la web),
pone la cookie de sesión `gs_session` firmada con HMAC, que la CloudFront Function comprueba antes de
servir cualquier archivo (y con la que sirve a cada persona solo su carpeta de datos).
Solo usa la librería estándar (y boto3, incluido en Lambda).
"""

import base64
import hashlib
import hmac
import html
import json
import os
import secrets
import time
import urllib.parse
import urllib.request

import boto3

OWNER = os.environ["OWNER_EMAIL"].strip().lower()
BUCKET = os.environ["BUCKET"]
USERS_KEY = "admin/users.json"
SESSION_SECRET = os.environ["SESSION_SECRET"].encode()
ORIGIN_SECRET = os.environ["ORIGIN_SECRET"]
CLIENT_ID_PARAM = os.environ["GOOGLE_CLIENT_ID_PARAM"]
CLIENT_SECRET_PARAM = os.environ["GOOGLE_CLIENT_SECRET_PARAM"]
SESSION_DAYS = 30
_ssm = boto3.client("ssm")
_s3 = boto3.client("s3")
_cfg: dict = {}


def _check_user(email: str, name: str) -> bool:
    """¿Tiene invitación? Al entrar por primera vez se apunta su nombre y la fecha."""
    try:
        reg = json.loads(_s3.get_object(Bucket=BUCKET, Key=USERS_KEY)["Body"].read())
    except _s3.exceptions.NoSuchKey:
        reg = {"users": []}
    users = reg.setdefault("users", [])
    u = next((x for x in users if x.get("email") == email), None)
    if u is None and email == OWNER:  # arranque: el dueño siempre puede entrar
        uid = hmac.new(SESSION_SECRET, b"uid:" + email.encode(), hashlib.sha256).hexdigest()[:16]
        u = {"email": email, "uid": uid, "name": name, "role": "owner", "budgetUsd": 50, "status": "onboarding",
             "invitedAt": int(time.time())}
        users.append(u)
    if u is None:
        return False
    changed = False
    if u.get("status") == "invited":
        u["status"], changed = "onboarding", True
    if not u.get("joinedAt"):
        u["joinedAt"], changed = int(time.time()), True
    if name and not u.get("name"):
        u["name"], changed = name, True
    if changed:
        _s3.put_object(Bucket=BUCKET, Key=USERS_KEY, Body=json.dumps(reg, ensure_ascii=False, indent=1).encode(),
                       ContentType="application/json")
    return True


def _google():
    if not _cfg:
        try:
            _cfg["id"] = _ssm.get_parameter(Name=CLIENT_ID_PARAM)["Parameter"]["Value"]
            _cfg["secret"] = _ssm.get_parameter(Name=CLIENT_SECRET_PARAM, WithDecryption=True)["Parameter"]["Value"]
        except _ssm.exceptions.ParameterNotFound:
            return None
    return _cfg


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def session_cookie(email: str) -> str:
    exp = int(time.time()) + SESSION_DAYS * 86400
    payload = f"{_b64(email.encode())}.{exp}"
    mac = hmac.new(SESSION_SECRET, payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{mac}"


def _resp(status, body="", headers=None, cookies=None, ctype="text/html; charset=utf-8"):
    h = {"content-type": ctype, "cache-control": "no-store", "referrer-policy": "no-referrer"}
    h.update(headers or {})
    return {"statusCode": status, "headers": h, "cookies": cookies or [], "body": body}


G_LOGO = ('<svg width="20" height="20" viewBox="0 0 48 48" aria-hidden="true"><path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 '
          '9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/>'
          '<path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 '
          '7.09-10.36 7.09-17.65z"/><path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 '
          '16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/><path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c'
          '-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/></svg>')

FEATURES = [
    ("#5B5BD6", "Sueño", "Fases, horario y lo que te ayuda a dormir mejor",
     '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>'),
    ("#D93025", "Corazón", "Pulso en reposo, HRV, estrés y energía",
     '<path d="M12 21s-7.5-4.6-9.4-9.3C1.2 8.2 3.4 4.5 7 4.5c2 0 3.5 1.1 5 2.9 1.5-1.8 3-2.9 5-2.9 3.6 0 5.8 3.7 4.4 7.2C19.5 16.4 12 21 12 21z"/>'),
    ("#E8710A", "Entreno", "Carreras con mapa, carga, forma y récords",
     '<circle cx="13.5" cy="4.5" r="2"/><path d="M9.8 8.9 7 22h2.1l1.8-8 2.1 2v6h2v-7.5l-2.1-2 .6-3A7.3 7.3 0 0 0 19 12v-2a5.4 5.4 0 0 1-4.6-2.6l-1-1.6A2 2 0 0 0 11.7 5c-.3 0-.5 0-.8.1L6 7.2V12h2V8.6z"/>'),
    ("#00838F", "Coach con IA", "Un plan que se adapta a ti cada semana",
     '<path d="M12 2l1.9 5.6L19.5 9l-5.6 1.9L12 16.5l-1.9-5.6L4.5 9l5.6-1.4z"/><path d="M19 15l.9 2.6 2.6.9-2.6.9L19 22l-.9-2.6-2.6-.9 2.6-.9z"/>'),
]

RINGS = """<svg class="rings" viewBox="0 0 120 120" aria-hidden="true">
<g fill="none" stroke-linecap="round" stroke-width="9" transform="rotate(-90 60 60)">
<circle cx="60" cy="60" r="52" stroke="var(--r1)" opacity=".18"/><circle cx="60" cy="60" r="52" stroke="var(--r1)" stroke-dasharray="327" stroke-dashoffset="60" class="a1"/>
<circle cx="60" cy="60" r="39" stroke="var(--r2)" opacity=".18"/><circle cx="60" cy="60" r="39" stroke="var(--r2)" stroke-dasharray="245" stroke-dashoffset="70" class="a2"/>
<circle cx="60" cy="60" r="26" stroke="var(--r3)" opacity=".18"/><circle cx="60" cy="60" r="26" stroke="var(--r3)" stroke-dasharray="163" stroke-dashoffset="35" class="a3"/>
</g><path transform="translate(48.5 49) scale(.96)" fill="var(--heart)" d="M12 21s-7.5-4.6-9.4-9.3C1.2 8.2 3.4 4.5 7 4.5c2 0 3.5 1.1 5 2.9 1.5-1.8 3-2.9 5-2.9 3.6 0 5.8 3.7 4.4 7.2C19.5 16.4 12 21 12 21z"/></svg>"""

CSS = """
:root{--bg:#f6f8fc;--card:#fff;--text:#1f1f1f;--muted:#5f6368;--line:#e3e6ea;--r1:#188038;--r2:#1a73e8;--r3:#5b5bd6;--heart:#d93025;
 --btn:#fff;--btnText:#1f1f1f;--btnLine:#dadce0;--shadow:0 1px 2px rgba(60,64,67,.10),0 8px 28px rgba(60,64,67,.10)}
@media (prefers-color-scheme:dark){:root{--bg:#0e0e0f;--card:#1e1f20;--text:#e3e3e3;--muted:#a8abaf;--line:#2e3134;--r1:#81c995;--r2:#8ab4f8;
 --r3:#afadff;--heart:#f28b82;--btn:#131314;--btnText:#e3e3e3;--btnLine:#8e918f;--shadow:0 8px 28px rgba(0,0,0,.45)}}
*{box-sizing:border-box}html,body{margin:0}
body{min-height:100vh;min-height:100dvh;background:var(--bg);color:var(--text);
 font:16px/1.55 "Google Sans Flex","Google Sans",Roboto,system-ui,-apple-system,sans-serif;display:flex;flex-direction:column;overflow-x:hidden}
.glow{position:fixed;inset:-25% -10% auto;height:80vh;pointer-events:none;filter:blur(70px);opacity:.5;z-index:0;
 background:radial-gradient(40% 50% at 15% 30%,color-mix(in srgb,var(--r3) 35%,transparent),transparent 70%),
  radial-gradient(35% 45% at 85% 25%,color-mix(in srgb,var(--r2) 30%,transparent),transparent 70%),
  radial-gradient(30% 40% at 55% 70%,color-mix(in srgb,var(--r1) 22%,transparent),transparent 70%)}
header{position:relative;z-index:1;display:flex;align-items:center;gap:10px;padding:20px clamp(16px,4vw,48px);font-weight:500;font-size:18px}
header svg{width:30px;height:30px}
main{position:relative;z-index:1;flex:1;display:grid;align-items:center;gap:clamp(32px,5vw,72px);
 grid-template-columns:minmax(0,1fr);max-width:1180px;width:100%;margin:0 auto;padding:16px clamp(16px,4vw,48px) 40px}
@media (min-width:960px){main{grid-template-columns:1.05fr 1fr}}
.hero{text-align:center}@media (min-width:960px){.hero{text-align:left}}
.hero .rings{width:120px;height:120px;margin:0 auto 12px;display:block}@media (min-width:960px){.hero .rings{display:none}}
h1{font-size:clamp(36px,5.2vw,60px);line-height:1.05;font-weight:500;letter-spacing:-.025em;margin:0 0 16px}
h1 em{font-style:normal;background:linear-gradient(90deg,var(--r3),var(--r2) 50%,var(--r1));-webkit-background-clip:text;background-clip:text;color:transparent}
.lead{color:var(--muted);font-size:clamp(16px,1.6vw,19px);margin:0 auto 28px;max-width:520px}@media (min-width:960px){.lead{margin-left:0}}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:12px;height:54px;padding:0 30px;border-radius:999px;
 background:var(--btn);color:var(--btnText);border:1px solid var(--btnLine);text-decoration:none;font-weight:500;font-size:16px;
 box-shadow:0 1px 2px rgba(60,64,67,.12),0 2px 8px rgba(60,64,67,.08);transition:box-shadow .2s,transform .2s;width:100%;max-width:340px}
.btn:hover{box-shadow:0 2px 4px rgba(60,64,67,.18),0 6px 16px rgba(60,64,67,.12);transform:translateY(-1px)}
.btn:focus-visible{outline:3px solid var(--r2);outline-offset:3px}
.note{display:flex;gap:8px;align-items:center;justify-content:center;color:var(--muted);font-size:13px;margin:16px 0 0}
@media (min-width:960px){.note{justify-content:flex-start}}
.msg{display:inline-block;background:var(--card);border:1px solid var(--line);border-radius:16px;padding:12px 16px;margin:0 0 20px;font-size:14px;max-width:520px}
/* vista previa (derecha en ordenador, debajo en móvil) */
.preview{background:var(--card);border:1px solid var(--line);border-radius:32px;padding:22px;box-shadow:var(--shadow)}
.top{display:flex;align-items:center;gap:18px;padding:6px 6px 18px;border-bottom:1px solid var(--line)}
.top .rings{width:96px;height:96px;flex:none}
.top small{color:var(--muted);font-size:12px;letter-spacing:.06em;text-transform:uppercase}
.top b{display:block;font-size:26px;font-weight:500;color:var(--r1)}.top span{color:var(--muted);font-size:14px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:16px}
.f{border-radius:20px;padding:14px;background:color-mix(in srgb,var(--c) 8%,transparent)}
.f i{display:grid;place-items:center;width:34px;height:34px;border-radius:50%;margin-bottom:8px;color:var(--c);background:color-mix(in srgb,var(--c) 16%,transparent)}
.f svg{width:19px;height:19px}.f b{display:block;font-weight:500;font-size:15px}.f span{display:block;color:var(--muted);font-size:13px;line-height:1.4;margin-top:2px}
footer{position:relative;z-index:1;text-align:center;color:var(--muted);font-size:12px;padding:0 16px 24px;opacity:.85}
@media (max-width:959px){.preview .top{display:none}.preview{background:none;border:0;box-shadow:none;padding:0}}
@media (max-width:380px){.grid{grid-template-columns:1fr}}
.a1,.a2,.a3{animation:fill 1.4s cubic-bezier(.2,.8,.2,1) both}.a2{animation-delay:.12s}.a3{animation-delay:.24s}
@keyframes fill{from{stroke-dashoffset:330}}
@media (prefers-reduced-motion:reduce){.a1,.a2,.a3{animation:none}.btn{transition:none}}
"""

HEART = '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="var(--heart)" d="M12 21s-7.5-4.6-9.4-9.3C1.2 8.2 3.4 4.5 7 4.5c2 0 3.5 1.1 5 2.9 1.5-1.8 3-2.9 5-2.9 3.6 0 5.8 3.7 4.4 7.2C19.5 16.4 12 21 12 21z"/></svg>'


def landing(message: str = "", button_href: str = "/auth/login?go=1", button_text: str = "Continuar con Google", status=200):
    feats = "".join(
        f'<div class="f" style="--c:{c}"><i><svg viewBox="0 0 24 24" fill="currentColor">{svg}</svg></i>'
        f'<b>{t}</b><span>{d}</span></div>'
        for c, t, d, svg in FEATURES)
    msg = f'<p class="msg">{message}</p>' if message else ""
    html = f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="color-scheme" content="light dark">
<meta name="robots" content="noindex,nofollow"><title>Mi salud</title>
<link rel="manifest" href="/manifest.webmanifest"><link rel="apple-touch-icon" href="/apple-touch-icon.png">
<meta name="theme-color" content="#F6F8FC" media="(prefers-color-scheme: light)"><meta name="theme-color" content="#0E0E0F" media="(prefers-color-scheme: dark)">
<meta name="apple-mobile-web-app-capable" content="yes"><meta name="mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-title" content="Mi salud">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath fill='%23D93025' d='M12 21s-7.5-4.6-9.4-9.3C1.2 8.2 3.4 4.5 7 4.5c2 0 3.5 1.1 5 2.9 1.5-1.8 3-2.9 5-2.9 3.6 0 5.8 3.7 4.4 7.2C19.5 16.4 12 21 12 21z'/%3E%3C/svg%3E">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Google+Sans+Flex:wght@400..600&display=swap" rel="stylesheet">
<style>{CSS}</style></head><body><div class="glow"></div>
<header>{HEART}Mi salud</header>
<main>
 <section class="hero">
  {RINGS}
  <h1>Tu salud, <em>clara y a tu medida</em></h1>
  <p class="lead">Sueño, corazón y entrenos de tu Garmin en un solo sitio, con un coach con IA que aprende de ti cada semana.</p>
  {msg}<div><a class="btn" href="{button_href}">{G_LOGO}<span>{button_text}</span></a></div>
  <p class="note"><svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 1 3 5v6c0 5.5 3.8 10.7 9 12 5.2-1.3 9-6.5 9-12V5l-9-4zm0 6a3 3 0 0 1 3 3v1h1v6H8v-6h1v-1a3 3 0 0 1 3-3zm0 2a1 1 0 0 0-1 1v1h2v-1a1 1 0 0 0-1-1z"/></svg>
  Privada: solo con invitación, y cada persona ve únicamente sus datos</p>
 </section>
 <section class="preview" aria-label="Qué encontrarás dentro">
  <div class="top">{RINGS}<div><small>Preparación de hoy</small><b>Buen día para entrenar</b><span>HRV, sueño, pulso y carga frente a tu normalidad</span></div></div>
  <div class="grid">{feats}</div>
 </section>
</main>
<footer>Datos de Garmin Connect · No es consejo médico</footer></body></html>"""
    return _resp(status, html)


def page(title, text, button=""):
    """Compatibilidad: mensajes con el diseño de la portada."""
    return landing(f"<b>{title}.</b> {text}")


def handler(event, _ctx):
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    if not hmac.compare_digest(headers.get("x-origin-verify", ""), ORIGIN_SECRET):
        return _resp(403, "Prohibido", ctype="text/plain")
    host = headers.get("x-forwarded-host") or headers.get("host")
    host = headers.get("x-viewer-host", host)
    base = f"https://{host}"
    path = event.get("rawPath", "")
    qs = event.get("queryStringParameters") or {}
    cookies = dict(c.split("=", 1) for c in event.get("cookies") or [] if "=" in c)
    g = _google()

    if path == "/auth/logout":
        return _resp(302, headers={"location": "/auth/login?out=1"},
                     cookies=["gs_session=; Path=/; Max-Age=0; Secure; HttpOnly; SameSite=Lax"])

    if path == "/auth/login":
        if g is None:
            return landing("El acceso con Google aún no está configurado.")
        if "out" in qs:
            return landing("Has cerrado la sesión.")
        if "go" not in qs:
            nxt = qs.get("next", "/")
            return landing(button_href="/auth/login?go=1&next=" + urllib.parse.quote(nxt, safe=""))
        verifier = _b64(secrets.token_bytes(32))
        state = _b64(secrets.token_bytes(16))
        nxt = qs.get("next", "/")
        if not nxt.startswith("/") or nxt.startswith("//"):
            nxt = "/"
        params = {
            "client_id": g["id"], "redirect_uri": f"{base}/auth/callback", "response_type": "code",
            "scope": "openid email profile", "state": state, "prompt": "select_account",
            "code_challenge": _b64(hashlib.sha256(verifier.encode()).digest()), "code_challenge_method": "S256",
        }
        tmp = json.dumps({"v": verifier, "s": state, "n": nxt})
        return _resp(302, headers={"location": "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)},
                     cookies=[f"gs_oauth={_b64(tmp.encode())}; Path=/auth; Max-Age=600; Secure; HttpOnly; SameSite=Lax"])

    if path == "/auth/callback":
        try:
            tmp = json.loads(base64.urlsafe_b64decode(cookies["gs_oauth"] + "=="))
        except Exception:
            return _resp(302, headers={"location": "/auth/login?go=1"})
        if g is None or qs.get("state") != tmp["s"] or "code" not in qs:
            return landing("No se pudo completar el acceso. Vuelve a intentarlo.")
        data = urllib.parse.urlencode({
            "code": qs["code"], "client_id": g["id"], "client_secret": g["secret"], "code_verifier": tmp["v"],
            "redirect_uri": f"{base}/auth/callback", "grant_type": "authorization_code",
        }).encode()
        try:
            with urllib.request.urlopen("https://oauth2.googleapis.com/token", data=data, timeout=10) as r:
                tok = json.load(r)
            claims = json.loads(base64.urlsafe_b64decode(tok["id_token"].split(".")[1] + "=="))
        except Exception:
            return landing("Google no ha aceptado el acceso. Vuelve a intentarlo.")
        email = str(claims.get("email", "")).lower()
        ok = (claims.get("iss") in ("https://accounts.google.com", "accounts.google.com")
              and claims.get("aud") == g["id"] and int(claims.get("exp", 0)) > time.time()
              and claims.get("email_verified") is True)
        if ok:
            try:
                ok = _check_user(email, str(claims.get("given_name") or claims.get("name") or "")[:60])
            except Exception:  # noqa: BLE001
                return landing("No se pudo comprobar tu acceso. Vuelve a intentarlo en un momento.")
        if not ok:
            return landing(f"La cuenta <b>{html.escape(email) or 'elegida'}</b> no tiene invitación. Pide a quien te pasó el enlace que te invite con este email.",
                           button_text="Probar con otra cuenta")
        return _resp(302, headers={"location": tmp["n"]}, cookies=[
            f"gs_session={session_cookie(email)}; Path=/; Max-Age={SESSION_DAYS * 86400}; Secure; HttpOnly; SameSite=Lax",
            "gs_oauth=; Path=/auth; Max-Age=0; Secure; HttpOnly; SameSite=Lax",
        ])

    return _resp(404, "No encontrado", ctype="text/plain")
