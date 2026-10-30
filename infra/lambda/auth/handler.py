"""Login con Google para la web (Lambda detrás de CloudFront, ruta /auth/*).

Flujo OAuth "authorization code" + PKCE. El id_token llega directamente de Google por TLS, así que
basta con comprobar emisor, audiencia, caducidad y email (lo permite la especificación de OpenID).
Si el email es el permitido, pone la cookie de sesión `gs_session` firmada con HMAC, que la
CloudFront Function comprueba antes de servir cualquier archivo.
Solo usa la librería estándar (y boto3, incluido en Lambda).
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
import urllib.parse
import urllib.request

import boto3

ALLOWED = {e.strip().lower() for e in os.environ["ALLOWED_EMAILS"].split(",") if e.strip()}
SESSION_SECRET = os.environ["SESSION_SECRET"].encode()
ORIGIN_SECRET = os.environ["ORIGIN_SECRET"]
CLIENT_ID_PARAM = os.environ["GOOGLE_CLIENT_ID_PARAM"]
CLIENT_SECRET_PARAM = os.environ["GOOGLE_CLIENT_SECRET_PARAM"]
SESSION_DAYS = 30
_ssm = boto3.client("ssm")
_cfg: dict = {}


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
:root{--bg:#f6f8fc;--card:#fff;--text:#1f1f1f;--muted:#5f6368;--line:#e3e6ea;--r1:#188038;--r2:#1a73e8;--r3:#5b5bd6;--heart:#d93025;--btn:#fff;--btnText:#1f1f1f;--btnLine:#dadce0}
@media (prefers-color-scheme:dark){:root{--bg:#0e0e0f;--card:#1e1f20;--text:#e3e3e3;--muted:#a8abaf;--line:#2e3134;--r1:#81c995;--r2:#8ab4f8;--r3:#afadff;--heart:#f28b82;--btn:#131314;--btnText:#e3e3e3;--btnLine:#8e918f}}
*{box-sizing:border-box}html,body{margin:0}
body{min-height:100vh;min-height:100dvh;background:var(--bg);color:var(--text);font:16px/1.55 "Google Sans Flex","Google Sans",Roboto,system-ui,-apple-system,sans-serif;
 display:flex;flex-direction:column;align-items:center;justify-content:center;padding:32px 16px;position:relative;overflow-x:hidden}
.glow{position:fixed;inset:-20% -10% auto;height:70vh;pointer-events:none;filter:blur(60px);opacity:.55;
 background:radial-gradient(40% 50% at 20% 30%,color-mix(in srgb,var(--r3) 35%,transparent),transparent 70%),
            radial-gradient(35% 45% at 80% 20%,color-mix(in srgb,var(--r2) 30%,transparent),transparent 70%),
            radial-gradient(30% 40% at 55% 60%,color-mix(in srgb,var(--r1) 25%,transparent),transparent 70%)}
main{position:relative;width:100%;max-width:440px;text-align:center}
.rings{width:132px;height:132px;display:block;margin:0 auto 8px}
.a1,.a2,.a3{animation:fill 1.4s cubic-bezier(.2,.8,.2,1) both}.a2{animation-delay:.12s}.a3{animation-delay:.24s}
@keyframes fill{from{stroke-dashoffset:330}}
h1{font-size:40px;font-weight:500;letter-spacing:-.02em;margin:8px 0 6px}
.lead{color:var(--muted);font-size:17px;margin:0 auto 28px;max-width:360px}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:12px;height:52px;padding:0 28px;border-radius:999px;
 background:var(--btn);color:var(--btnText);border:1px solid var(--btnLine);text-decoration:none;font-weight:500;font-size:16px;
 box-shadow:0 1px 2px rgba(60,64,67,.12),0 2px 8px rgba(60,64,67,.08);transition:box-shadow .2s,transform .2s;width:100%;max-width:320px}
.btn:hover{box-shadow:0 2px 4px rgba(60,64,67,.18),0 6px 16px rgba(60,64,67,.12);transform:translateY(-1px)}
.btn:focus-visible{outline:3px solid var(--r2);outline-offset:3px}
.note{display:flex;gap:8px;align-items:center;justify-content:center;color:var(--muted);font-size:13px;margin:16px 0 0}
.msg{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:12px 16px;margin:0 auto 20px;font-size:14px;max-width:360px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:40px 0 0;text-align:left}
.f{background:var(--card);border:1px solid var(--line);border-radius:20px;padding:16px}
.f i{display:grid;place-items:center;width:36px;height:36px;border-radius:50%;margin-bottom:10px}
.f svg{width:20px;height:20px}
.f b{display:block;font-weight:500;font-size:15px}.f span{display:block;color:var(--muted);font-size:13px;line-height:1.4;margin-top:2px}
footer{position:relative;color:var(--muted);font-size:12px;margin-top:32px;opacity:.8}
@media (max-width:380px){h1{font-size:34px}.grid{grid-template-columns:1fr}}
@media (prefers-reduced-motion:reduce){.a1,.a2,.a3{animation:none}}
"""


def landing(message: str = "", button_href: str = "/auth/login?go=1", button_text: str = "Continuar con Google", status=200):
    feats = "".join(
        f'<div class="f"><i style="background:color-mix(in srgb,{c} 14%,transparent);color:{c}">'
        f'<svg viewBox="0 0 24 24" fill="currentColor">{svg}</svg></i><b>{t}</b><span>{d}</span></div>'
        for c, t, d, svg in FEATURES)
    msg = f'<p class="msg">{message}</p>' if message else ""
    html = f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light dark">
<meta name="robots" content="noindex,nofollow"><title>Mi salud</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath fill='%23D93025' d='M12 21s-7.5-4.6-9.4-9.3C1.2 8.2 3.4 4.5 7 4.5c2 0 3.5 1.1 5 2.9 1.5-1.8 3-2.9 5-2.9 3.6 0 5.8 3.7 4.4 7.2C19.5 16.4 12 21 12 21z'/%3E%3C/svg%3E">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Google+Sans+Flex:wght@400..600&display=swap" rel="stylesheet">
<style>{CSS}</style></head><body><div class="glow"></div><main>
{RINGS}<h1>Mi salud</h1>
<p class="lead">Tu sueño, tu corazón y tus entrenos en un solo sitio, con un coach que aprende de ti.</p>
{msg}<a class="btn" href="{button_href}">{G_LOGO}<span>{button_text}</span></a>
<p class="note"><svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 1 3 5v6c0 5.5 3.8 10.7 9 12 5.2-1.3 9-6.5 9-12V5l-9-4zm0 6a3 3 0 0 1 3 3v1h1v6H8v-6h1v-1a3 3 0 0 1 3-3zm0 2a1 1 0 0 0-1 1v1h2v-1a1 1 0 0 0-1-1z"/></svg>
Privada: solo tu cuenta de Google tiene acceso</p>
<div class="grid">{feats}</div></main>
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
            "scope": "openid email", "state": state, "prompt": "select_account",
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
              and claims.get("email_verified") is True and email in ALLOWED)
        if not ok:
            return landing(f"La cuenta <b>{email or 'elegida'}</b> no tiene acceso a esta web.", button_text="Probar con otra cuenta")
        return _resp(302, headers={"location": tmp["n"]}, cookies=[
            f"gs_session={session_cookie(email)}; Path=/; Max-Age={SESSION_DAYS * 86400}; Secure; HttpOnly; SameSite=Lax",
            "gs_oauth=; Path=/auth; Max-Age=0; Secure; HttpOnly; SameSite=Lax",
        ])

    return _resp(404, "No encontrado", ctype="text/plain")
