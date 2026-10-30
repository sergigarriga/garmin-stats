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


PAGE = """<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Mi salud</title><style>
body{{margin:0;min-height:100vh;display:grid;place-items:center;background:#f2f5fa;font:16px/1.5 "Google Sans",Roboto,system-ui,sans-serif;color:#1f1f1f}}
@media (prefers-color-scheme:dark){{body{{background:#0e0e0f;color:#e3e3e3}}.c{{background:#1e1f20!important}}p{{color:#c4c7c5!important}}}}
.c{{background:#fff;border-radius:28px;padding:40px 36px;max-width:380px;margin:16px;text-align:center}}
h1{{font-size:26px;font-weight:500;margin:12px 0 8px}} p{{color:#444746;margin:0 0 24px}}
a.b{{display:inline-flex;gap:10px;align-items:center;background:#0b57d0;color:#fff;text-decoration:none;padding:12px 24px;border-radius:999px;font-weight:500}}
</style><div class="c"><div style="font-size:40px">❤</div><h1>{title}</h1><p>{text}</p>{button}</div></html>"""


def page(title, text, button=""):
    return _resp(200, PAGE.format(title=title, text=text, button=button))


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
            return page("Falta configurar el login", "Todavía no se ha guardado el cliente OAuth de Google en AWS.")
        if "out" in qs:
            return page("Has cerrado la sesión", "Tus datos de salud solo se ven con tu cuenta de Google.",
                        '<a class="b" href="/auth/login">Entrar con Google</a>')
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
            return _resp(302, headers={"location": "/auth/login"})
        if g is None or qs.get("state") != tmp["s"] or "code" not in qs:
            return page("No se pudo entrar", "La petición de login no es válida. Vuelve a intentarlo.",
                        '<a class="b" href="/auth/login">Volver a intentarlo</a>')
        data = urllib.parse.urlencode({
            "code": qs["code"], "client_id": g["id"], "client_secret": g["secret"], "code_verifier": tmp["v"],
            "redirect_uri": f"{base}/auth/callback", "grant_type": "authorization_code",
        }).encode()
        try:
            with urllib.request.urlopen("https://oauth2.googleapis.com/token", data=data, timeout=10) as r:
                tok = json.load(r)
            claims = json.loads(base64.urlsafe_b64decode(tok["id_token"].split(".")[1] + "=="))
        except Exception:
            return page("No se pudo entrar", "Google no ha aceptado el login. Vuelve a intentarlo.",
                        '<a class="b" href="/auth/login">Volver a intentarlo</a>')
        email = str(claims.get("email", "")).lower()
        ok = (claims.get("iss") in ("https://accounts.google.com", "accounts.google.com")
              and claims.get("aud") == g["id"] and int(claims.get("exp", 0)) > time.time()
              and claims.get("email_verified") is True and email in ALLOWED)
        if not ok:
            return page("Acceso no permitido", f"La cuenta {email or 'elegida'} no tiene acceso a esta web.",
                        '<a class="b" href="/auth/login">Probar con otra cuenta</a>')
        return _resp(302, headers={"location": tmp["n"]}, cookies=[
            f"gs_session={session_cookie(email)}; Path=/; Max-Age={SESSION_DAYS * 86400}; Secure; HttpOnly; SameSite=Lax",
            "gs_oauth=; Path=/auth; Max-Age=0; Secure; HttpOnly; SameSite=Lax",
        ])

    return _resp(404, "No encontrado", ctype="text/plain")
