"""API de la web en AWS (Lambda detrás de CloudFront, ruta /api/*). Versión multipersona.

Cada petición trae la cookie de sesión firmada por el login; de ahí sale el email y, con el registro de
usuarias (S3 admin/users.json), su id. Todo lo que se lee o escribe va a SU carpeta:
  site/u/<uid>/data.js           su web (la escribe la sincronización)
  users/<uid>/state/coach.json   su plan, memoria del coach y valoraciones
  users/<uid>/state/*.log        su gasto de IA (tope mensual propio: budgetUsd en el registro)
  users/<uid>/state/food.json    lo que come (módulo Comida; la foto no se guarda, solo los datos estimados)
  users/<uid>/state/shopping.json  su menú de la semana y su lista de la compra
  admin/catalog/mercadona-latest.json  catálogo de productos (privado; solo lectura desde aquí)
  /garmin-stats/users/<uid>/garmin-key (SSM, cifrado)  su clave de Garmin
  /garmin-stats/users/<uid>/google-token (SSM, cifrado) su permiso de Google Health (si usa Google en vez de Garmin)
Antes de cada petición se vacía /tmp/gs: una Lambda caliente nunca mezcla datos de dos personas.

Crear y reajustar el plan tarda minutos y CloudFront corta a los 60 s, así que se hace en segundo plano
(la propia Lambda se invoca en asíncrono) y la web consulta /api/plan hasta que termina.
"""

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import time

# Hora de Madrid (Lambda va en UTC): "hoy" cambia a medianoche de aquí. Regla POSIX: no necesita tzdata.
os.environ["TZ"] = "CET-1CEST,M3.5.0,M10.5.0/3"
time.tzset()
from datetime import date, timedelta
from pathlib import Path

import boto3

ROOT = Path("/tmp/gs")
HOME = Path("/tmp/home")
os.environ.setdefault("GARMIN_STATS_ROOT", str(ROOT))
os.environ.setdefault("GARMIN_STATS_USAGE_LOG", "ai_usage_lambda.log")
os.environ["HOME"] = str(HOME)  # la clave de Anthropic se escribe en ~/.config/anthropic (en /tmp)

from garmin_stats import google_health as GH
from garmin_stats import users as U  # noqa: E402

BUCKET = os.environ["BUCKET"]
SESSION_SECRET = os.environ["SESSION_SECRET"].encode()
ORIGIN_SECRET = os.environ["ORIGIN_SECRET"]
OWNER = os.environ["OWNER_EMAIL"].strip().lower()
ANTHROPIC_PARAM = os.environ["ANTHROPIC_KEY_PARAM"]
FUNCTION_NAME = os.environ.get("AWS_LAMBDA_FUNCTION_NAME", "")
FRIEND_BUDGET = 5.0
STALE = 960  # igual que en la sincronización: una "en marcha" de hace más de 16 min se da por muerta

s3 = boto3.client("s3")
_lambda = boto3.client("lambda")
_ssm = boto3.client("ssm")

STATE = ["coach.json", "settings.json", "wellness.json", "weather.json", "food.json", "shopping.json", "ai_usage.log",
         "ai_usage_lambda.log", "ai_cache.json"]
MAX_BODY = 2_200_000  # la foto de Comida llega en base64 (máx. 1,5 MB); el resto de peticiones son pequeñas
CAL_RE = re.compile(r"^/api/cal/([A-Za-z0-9_-]{24,64})\.ics$")
CUR: dict = {}  # persona de esta petición
GH_ID_PARAM = os.environ.get("GOOGLE_HEALTH_CLIENT_ID_PARAM", "/garmin-stats/google-health-client-id")
GH_SECRET_PARAM = os.environ.get("GOOGLE_HEALTH_CLIENT_SECRET_PARAM", "/garmin-stats/google-health-client-secret")
GH_COOKIE = "gs_google"  # PKCE y state del flujo de conexión (10 min, solo en /api/google)
# Dominio público de la web (el de CloudFront): única dirección de vuelta que se manda a Google. Vacío = sin Google Health.
PUBLIC_HOST = os.environ.get("PUBLIC_HOST", "").strip().lower()
BUSY = "Hay una descarga en marcha; prueba en un par de minutos."
_GH: dict = {}  # cliente OAuth de Google Health, leído de SSM una vez por Lambda caliente


# ------------------------------------------------------------------ persona actual y archivos
def _use(user: dict) -> None:
    """Prepara el entorno para esta persona (y borra cualquier resto de la anterior)."""
    CUR.clear()
    CUR.update(user)
    shutil.rmtree(ROOT, ignore_errors=True)
    shutil.rmtree(HOME / ".config" / "garmin", ignore_errors=True)
    os.environ["GARMIN_STATS_UID"] = user["uid"]
    os.environ["GARMIN_STATS_AI_BUDGET"] = str(user.get("budgetUsd") or FRIEND_BUDGET)
    os.environ["GARMIN_STATS_ADAPT_MODEL"] = "" if user.get("role") == "owner" else "claude-sonnet-5-5"


def _sp(name: str) -> str:
    return U.state_prefix(CUR["uid"]) + name


def _site(name: str) -> str:
    return U.site_prefix(CUR["uid"]) + name


def _setup_key():
    key_file = HOME / ".config/anthropic/garmin-stats-key"
    if not key_file.exists():
        key_file.parent.mkdir(parents=True, exist_ok=True)
        val = _ssm.get_parameter(Name=ANTHROPIC_PARAM, WithDecryption=True)["Parameter"]["Value"]
        key_file.write_text(val)
        key_file.chmod(0o600)


def _exists(key: str) -> bool:
    try:
        s3.head_object(Bucket=BUCKET, Key=key)
        return True
    except s3.exceptions.ClientError:
        return False


def _get_json(key: str, default):
    try:
        return json.loads(s3.get_object(Bucket=BUCKET, Key=key)["Body"].read())
    except s3.exceptions.NoSuchKey:
        return default


def _put_json(key: str, obj) -> None:
    s3.put_object(Bucket=BUCKET, Key=key, Body=json.dumps(obj, ensure_ascii=False).encode(), ContentType="application/json")


def _pull() -> bool:
    """Baja los datos de la persona actual. Devuelve False si aún no tiene web (está en el onboarding)."""
    (ROOT / "site").mkdir(parents=True, exist_ok=True)
    (ROOT / "data").mkdir(parents=True, exist_ok=True)
    for name in STATE:
        try:
            s3.download_file(BUCKET, _sp(name), str(ROOT / "data" / name))
        except s3.exceptions.ClientError:
            pass
    try:
        s3.download_file(BUCKET, _site("data.js"), str(ROOT / "site" / "data.js"))
        return True
    except s3.exceptions.ClientError:
        return False


def _push(*names):
    for name in names:
        p = ROOT / "data" / name
        if p.exists():
            s3.upload_file(str(p), BUCKET, _sp(name))


def _read_data() -> dict:
    raw = (ROOT / "site" / "data.js").read_text(encoding="utf-8")
    return json.loads(raw[raw.index("=") + 1:].rstrip().rstrip(";"))


def _refresh_site(coach) -> None:
    """Recalcula en su data.js lo que depende de lo que acaba de cambiar (plan, ritmos, natación, cómo se
    encuentra) para que la web lo vea al momento, sin esperar a la próxima sincronización."""
    from datetime import datetime
    from garmin_stats import training
    data = _read_data()
    training.enrich(data)
    data["coach"] = coach.view(data)
    data["generatedAt"] = datetime.now().astimezone().isoformat(timespec="seconds")
    body = "window.__GARMIN__=" + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n"
    (ROOT / "site" / "data.js").write_text(body, encoding="utf-8")  # la respuesta de esta petición ya lo ve
    s3.put_object(Bucket=BUCKET, Key=_site("data.js"), Body=body.encode(), ContentType="text/javascript; charset=utf-8",
                  CacheControl="no-store")


def _usage_stats(uid: str) -> dict:
    """Coste de IA de una persona: este mes, total, llamadas y última vez (de sus registros ai_usage*.log)."""
    month = date.today().isoformat()[:7]
    out = {"monthCostUsd": 0.0, "totalCostUsd": 0.0, "calls": 0, "lastAi": None}
    for name in ("ai_usage.log", "ai_usage_lambda.log"):
        try:
            text = s3.get_object(Bucket=BUCKET, Key=U.state_prefix(uid) + name)["Body"].read().decode()
        except s3.exceptions.ClientError:
            continue
        for line in text.splitlines():
            parts = line.split()
            cost = next((float(p[6:]) for p in parts if p.startswith("cost=$")), None)
            if not parts or cost is None:
                continue
            out["totalCostUsd"] += cost
            out["calls"] += 1
            if parts[0].startswith(month):
                out["monthCostUsd"] += cost
            if out["lastAi"] is None or parts[0] > out["lastAi"]:
                out["lastAi"] = parts[0]
    out["monthCostUsd"] = round(out["monthCostUsd"], 4)
    out["totalCostUsd"] = round(out["totalCostUsd"], 4)
    return out


def _month_spend(uid: str) -> float:
    month = date.today().isoformat()[:7]
    total = 0.0
    for name in ("ai_usage.log", "ai_usage_lambda.log"):
        try:
            text = s3.get_object(Bucket=BUCKET, Key=U.state_prefix(uid) + name)["Body"].read().decode()
        except s3.exceptions.ClientError:
            continue
        for line in text.splitlines():
            if line.startswith(month):
                for p in line.split():
                    if p.startswith("cost=$"):
                        total += float(p[6:])
    return round(total, 2)


# ------------------------------------------------------------------ sesión
def _session_email(cookies: list[str]) -> str | None:
    for c in cookies or []:
        if c.startswith("gs_session="):
            try:
                b64, exp, mac = c.split("=", 1)[1].split(".")
                good = hmac.new(SESSION_SECRET, f"{b64}.{exp}".encode(), hashlib.sha256).hexdigest()
                if hmac.compare_digest(good, mac) and int(exp) > time.time():
                    return base64.urlsafe_b64decode(b64 + "==").decode().strip().lower()
            except Exception:
                return None
    return None


def _no_nan(obj):
    """NaN e infinitos a null: json.dumps los escribe tal cual y el navegador rechaza la respuesta entera."""
    if isinstance(obj, float):
        return obj if obj == obj and obj not in (float("inf"), float("-inf")) else None
    if isinstance(obj, dict):
        return {k: _no_nan(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_no_nan(v) for v in obj]
    return obj


def _json(status, obj, cookies=None):
    try:
        body = json.dumps(obj, ensure_ascii=False, allow_nan=False)
    except ValueError:
        body = json.dumps(_no_nan(obj), ensure_ascii=False)
    return {"statusCode": status, "headers": {"content-type": "application/json; charset=utf-8", "cache-control": "no-store"},
            "cookies": cookies or [], "body": body}


def _ai_error(e: Exception, what: str = "el plan") -> str:
    """Un fallo al llamar a la IA, dicho en claro (nunca el texto técnico del error)."""
    import anthropic
    if isinstance(e, RuntimeError):  # mensajes propios, ya escritos para la persona
        return str(e)[:300]
    if isinstance(e, anthropic.APIConnectionError):  # incluye cuando tarda demasiado
        return "No hemos podido hablar con la IA. Inténtalo de nuevo en unos minutos."
    if isinstance(e, anthropic.APIStatusError) and (e.status_code == 429 or e.status_code >= 500):
        return "La IA está muy ocupada ahora mismo. Inténtalo de nuevo en unos minutos."
    print(f"IA ({what}): {type(e).__name__}: {str(e)[:300]}")
    if isinstance(e, anthropic.APIStatusError):
        return f"La IA no ha podido preparar {what} ahora. Inténtalo de nuevo más tarde."
    return f"Algo ha fallado al preparar {what}. Inténtalo de nuevo."


def _with_job(view: dict, coach) -> dict:
    view["job"] = coach.load().get("job")
    return view


# ------------------------------------------------------------------ trabajos en segundo plano
def _run_job(event):
    """Crear o reajustar el plan de una persona (lo lanza la propia API o la sincronización)."""
    if event.get("job") == "shopping":
        return _run_shopping(event)
    user = U.find(U.load(s3, BUCKET), uid=event.get("uid"))
    if not user:
        return {"ok": False}
    _use(user)
    from garmin_stats import coach
    _setup_key()
    if not _pull():
        return {"ok": False, "error": "sin datos"}
    action, body = event["job"], event.get("body") or {}
    if event.get("mark"):  # pedido por la sincronización: la web tiene que ver que está en marcha
        state = coach.load()
        state["job"] = {"status": "running", "action": action, "at": int(time.time())}
        coach.save(state)
        _push("coach.json")
        _refresh_site(coach)

    def cancelled() -> bool:
        st = _get_json(_sp("coach.json"), {})
        return bool((st.get("job") or {}).get("cancel"))
    coach.CANCEL_CHECK = cancelled
    try:
        if action == "create":
            coach.create(body)
        else:
            coach.adapt(force=True)
        state = coach.load()
        state["job"] = {"status": "done", "action": action, "at": int(time.time())}
        coach.save(state)
    except coach.Cancelled:
        state = coach.load()
        prev = (state.get("job") or {}).get("prev_ambition")
        if prev and state.get("plan"):
            state["plan"]["ambition"] = prev  # deshace el cambio de nivel
        state["job"] = {"status": "cancelled", "action": action, "at": int(time.time())}
        coach.save(state)
    except Exception as e:  # noqa: BLE001 - se muestra al usuario
        state = coach.load()
        state["job"] = {"status": "error", "action": action, "error": _ai_error(e), "at": int(time.time())}
        coach.save(state)
    _push("coach.json", "ai_usage_lambda.log", "weather.json")
    _refresh_site(coach)
    return {"ok": True}


# ------------------------------------------------------------------ entrada
def handler(event, _ctx):
    try:
        return _handle(event)
    except Exception:  # noqa: BLE001 - un fallo inesperado: la web recibe un aviso claro y el detalle queda en el log
        import traceback
        traceback.print_exc()
        if "job" in event:
            raise
        return _json(500, {"error": "Algo ha fallado en el servidor. Inténtalo de nuevo en un momento."})


def _handle(event):
    if "job" in event:  # invocación asíncrona propia
        return _run_job(event)

    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    if not hmac.compare_digest(headers.get("x-origin-verify", ""), ORIGIN_SECRET):
        return _json(403, {"error": "prohibido"})
    m = CAL_RE.match(event.get("rawPath", ""))
    if m:
        return _calendar_feed(m.group(1))
    email = _session_email(event.get("cookies"))
    if not email:
        return _json(401, {"error": "login"})
    user = U.find(U.load(s3, BUCKET), email=email)
    if not user:
        return _json(401, {"error": "login"})  # la invitación se ha retirado

    method = event["requestContext"]["http"]["method"]
    path = event.get("rawPath", "")
    body = event.get("body") or ""
    if len(body) > MAX_BODY:  # nunca se registra el cuerpo (puede llevar una foto)
        return _json(413, {"error": "La petición es demasiado grande (máx. 1,5 MB de foto)."})
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode()
    try:
        payload = json.loads(body) if body else {}
    except json.JSONDecodeError:
        return _json(400, {"error": "JSON no válido"})
    if not isinstance(payload, dict):
        return _json(400, {"error": "JSON no válido"})

    _use(user)

    # --- cuenta, onboarding y administración (no necesitan sus datos)
    if path == "/api/health":
        return _json(200, {"ok": True, "ai": True, "mode": "aws"})
    if path == "/api/me":
        return _me(user)
    if path == "/api/sync":
        return _sync(method, user)
    if path == "/api/google/connect" and method == "GET":
        return _google_connect(user, headers, _query(event))
    if path == "/api/google/callback" and method == "GET":
        return _google_callback(user, headers, _query(event), event.get("cookies"))
    if path == "/api/google/disconnect" and method == "POST":
        return _google_disconnect(user, payload)
    if path == "/api/whatsnew/seen" and method == "POST":  # ya ha visto las novedades de esta versión
        rel = str(payload.get("release") or "")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}(-\d{1,2})?", rel):
            return _json(400, {"error": "Versión no válida."})
        if user.get("seenRelease") != rel:
            U.update(s3, BUCKET, user["uid"], seenRelease=rel)
        return _json(200, {"ok": True})
    if path == "/api/onboarding/consent" and method == "POST":  # aceptó la privacidad (puede conectar Garmin más tarde)
        if not user.get("consentAt"):
            U.update(s3, BUCKET, user["uid"], consentAt=U.now())
        return _json(200, {"ok": True})
    if path == "/api/onboarding/key" and method == "POST":
        return _onboarding_key(user, payload)
    if path == "/api/onboarding/goal" and method == "POST":
        return _onboarding_goal(user, payload)
    if path == "/api/account/delete" and method == "POST":
        if user.get("role") == "owner":
            return _json(400, {"error": "La cuenta del administrador no se puede borrar desde aquí."})
        _delete_user(user)
        return _json(200, {"ok": True}, cookies=["gs_session=; Path=/; Max-Age=0; Secure; HttpOnly; SameSite=Lax"])
    if path == "/api/chat":  # conversación guardada (para verla igual en el móvil y en el ordenador)
        return _json(200, {"messages": _get_json(_sp("chat.json"), {}).get("messages", [])})
    if path == "/api/chat/clear" and method == "POST":
        _put_json(_sp("chat.json"), {"messages": []})
        return _json(200, {"ok": True})
    if path == "/api/calendar":
        return _calendar_link(user, payload if method == "POST" else None)
    if path == "/api/geo":  # buscador de ciudades para la previsión del tiempo (Open-Meteo, sin clave)
        from urllib.parse import parse_qs
        from garmin_stats import weather
        q = (parse_qs(event.get("rawQueryString") or "").get("q") or [""])[0]
        return _json(200, {"results": weather.geocode(q)})
    if path.startswith("/api/admin/"):
        if user.get("role") != "owner":
            return _json(403, {"error": "Solo el administrador."})
        return _admin(path, method, payload)
    if path == "/api/push/subscribe":
        sub = payload.get("subscription") or {}
        if not str(sub.get("endpoint", "")).startswith("https://") or not (sub.get("keys") or {}).get("p256dh"):
            return _json(400, {"error": "Suscripción no válida."})
        subs = _get_json(_sp("push.json"), [])
        subs = [x for x in subs if x.get("endpoint") != sub["endpoint"]] + [sub]
        _put_json(_sp("push.json"), subs[-10:])
        return _json(200, {"ok": True, "devices": len(subs[-10:])})
    if path == "/api/push/test":
        _lambda.invoke(FunctionName=os.environ["NOTIFY_FUNCTION"], InvocationType="Event",
                       Payload=json.dumps({"uid": user["uid"], "message": {"title": "Runch", "body": "¡Listo! Así te llegará el aviso de cada mañana.",
                                                                           "url": "/#hoy", "tag": "test"}}).encode())
        return _json(200, {"ok": True})

    # --- chat y plan (necesitan sus datos)
    _setup_key()
    has_data = _pull()
    if path == "/api/food" or path.startswith("/api/food/"):
        return _food(path, method, payload, has_data)
    if path == "/api/shopping" or path.startswith("/api/shopping/"):
        return _shopping(path, method, payload, user)
    if not has_data:
        return _json(409, {"error": "Aún no hay datos: termina de conectar tu Garmin."})
    from garmin_stats import coach, server

    if path == "/api/plan" and method == "GET":
        return _json(200, _with_job(coach.view(_read_data()), coach))
    if method != "POST":
        return _json(405, {"error": "método no permitido"})
    if path == "/api/ask":
        msgs = payload.get("messages")
        msgs = [m for m in msgs if isinstance(m, dict)] if isinstance(msgs, list) else []
        res = server.ask(msgs)
        _push("ai_usage_lambda.log")
        if "answer" in res and msgs and msgs[-1].get("role") == "user":
            hist = _get_json(_sp("chat.json"), {}).get("messages", [])
            now = U.now()
            hist += [{"role": "user", "content": str(msgs[-1].get("content", ""))[:2000], "at": now},
                     {"role": "assistant", "content": res["answer"], "at": now}]
            _put_json(_sp("chat.json"), {"messages": hist[-60:]})
        return _json(200 if "answer" in res else 503, res)

    if path == "/api/plan/cancel":
        st = coach.load()
        if (st.get("job") or {}).get("status") == "running":
            st["job"]["cancel"] = True
            coach.save(st)
            _push("coach.json")
        return _json(200, _with_job(coach.view(_read_data()), coach))
    if path == "/api/plan/ambition":
        if payload.get("ambition") not in ("realista", "exigente"):
            return _json(400, {"error": "Nivel no válido."})
        st = coach.load()
        if not st.get("plan"):
            return _json(400, {"error": "No hay plan."})
        if (st.get("job") or {}).get("status") == "running" and time.time() - st["job"].get("at", 0) < 900:
            return _json(409, {"error": "Ya hay un plan generándose. Espera a que termine o cancélalo."})
        prev_ambition = st["plan"].get("ambition", "realista")
        st["plan"]["ambition"] = payload["ambition"]
        coach.save(st)
        _push("coach.json")
        path = "/api/plan/adapt"  # reajusta el plan con el nuevo nivel
    else:
        prev_ambition = None
    if path in ("/api/plan/create", "/api/plan/adapt"):
        state = coach.load()
        if (state.get("job") or {}).get("status") == "running" and time.time() - state["job"].get("at", 0) < 900:
            return _json(409, {"error": "Ya hay un plan generándose. Espera a que termine."})
        if path.endswith("create") and not payload.get("date"):
            return _json(400, {"error": "Falta la fecha."})
        state["job"] = {"status": "running", "action": path.rsplit("/", 1)[1], "at": int(time.time()),
                        **({"prev_ambition": prev_ambition} if prev_ambition else {})}
        coach.save(state)
        _push("coach.json")
        _lambda.invoke(FunctionName=FUNCTION_NAME, InvocationType="Event",
                       Payload=json.dumps({"job": state["job"]["action"], "uid": user["uid"], "body": payload}).encode())
        return _json(202, _with_job(coach.view(_read_data()), coach))

    if path == "/api/plan/structure":
        try:
            coach.structure_week(str(payload.get("week") or ""))
        except RuntimeError as e:
            return _json(400, {"error": str(e)})
        except Exception as e:  # noqa: BLE001 - la IA no responde, va saturada o devuelve algo que no encaja
            _push("ai_usage_lambda.log")
            return _json(503, {"error": _ai_error(e, "los entrenos de la semana")})
        _push("coach.json", "ai_usage_lambda.log")
        _refresh_site(coach)
        return _json(200, _with_job(coach.view(_read_data()), coach))
    if path in ("/api/settings/race", "/api/settings/swim", "/api/settings/availability", "/api/settings/location",
                "/api/wellness", "/api/injury"):
        from garmin_stats import settings as S, weather, wellness as W
        fn = {"/api/settings/race": S.set_race_test, "/api/settings/swim": S.set_swim_test,
              "/api/settings/availability": S.set_availability, "/api/settings/location": S.set_location,
              "/api/wellness": W.set_day, "/api/injury": W.injury}[path]
        try:
            fn(payload)
        except ValueError as e:
            return _json(400, {"error": str(e)})
        _push("settings.json" if "settings" in path else "wellness.json")
        if path == "/api/settings/location" and weather.refresh():  # previsión de la ciudad nueva al momento
            _push("weather.json")
        _refresh_site(coach)
        data = _read_data()
        return _json(200, {k: data.get(k) for k in ("paces", "swim", "wellness", "coach", "availability", "weather")})
    if path == "/api/plan/feedback":
        try:
            coach.feedback(str(date.fromisoformat(str(payload.get("date")))), int(payload.get("rating") or 3),
                           str(payload.get("note") or ""))
        except (TypeError, ValueError):
            return _json(400, {"error": "Valoración no válida."})
    elif path in ("/api/plan/redo", "/api/plan/redo-undo"):
        try:
            if path == "/api/plan/redo":
                coach.redo(str(payload.get("date", "")), str(payload.get("type", "")), payload.get("today"))
            else:
                coach.undo_redo(payload.get("today"))
        except ValueError as e:
            return _json(400, {"error": str(e)})
    elif path == "/api/plan/delete":
        coach.delete()
    else:
        return _json(404, {"error": "no encontrado"})
    _push("coach.json")
    _refresh_site(coach)
    return _json(200, _with_job(coach.view(_read_data()), coach))


# ------------------------------------------------------------------ comida
def _food(path: str, method: str, payload: dict, has_data: bool):
    """Módulo Comida. La foto llega en la petición, la IA la analiza en memoria y se descarta: en S3 solo se guarda
    food.json (alimentos, gramos, kcal y macros). Sin datos de Garmin funciona igual, sin el gasto del día."""
    from garmin_stats import coach, food as F
    data = _read_data() if has_data else {}

    def out(status=200, entry=None):
        extra = {"entry": F.present(entry)} if entry is not None else {}
        return _json(status, {**extra, **F.view(data, None, coach.load())})

    def fresh():  # relee food.json justo antes de cambiarlo: no pisa una comida guardada a la vez desde otro móvil
        p = ROOT / "data" / "food.json"
        try:
            s3.download_file(BUCKET, _sp("food.json"), str(p))
        except s3.exceptions.ClientError:
            p.unlink(missing_ok=True)

    if path == "/api/food" and method == "GET":
        return out()
    if method != "POST":
        return _json(405, {"error": "método no permitido"})
    if path == "/api/food/prefs":
        fresh()
        try:
            F.set_prefs(payload)
        except ValueError as e:
            return _json(400, {"error": str(e)})
        _push("food.json")
        return out()
    if not F.prefs()["enabled"]:
        return _json(409, {"error": "Activa primero el módulo Comida."})
    if path in ("/api/food/add", "/api/food/reanalyze"):
        image, media = None, "image/jpeg"
        try:
            if path.endswith("add"):
                entry = F.new_entry(payload)
            else:
                entry = F.find(str(payload.get("id") or ""))
                if not entry:
                    return _json(404, {"error": "Esa comida ya no existe."})
                entry = dict(entry)
                if "note" in payload:
                    entry["note"] = " ".join(str(payload["note"] or "").split())[:300]
            if payload.get("photo"):
                image, media = F.decode_photo(payload["photo"])
        except OverflowError as e:
            return _json(413, {"error": str(e)})
        except ValueError as e:
            return _json(400, {"error": str(e)})
        analyze = bool(image) or (path.endswith("reanalyze")) or (bool(entry["text"]) and not entry["items"])
        if path.endswith("add") and not (image or entry["text"] or entry["items"]):
            return _json(400, {"error": "Añade una foto, escribe lo que has comido o apunta los alimentos."})
        if not payload.get("analyze", True) and not entry["items"]:
            return _json(400, {"error": "Apunta al menos un alimento."})
        if analyze and payload.get("analyze", True):
            try:
                res = F.analyze(entry, image, media)
                F.apply_analysis(entry, *res, from_photo=bool(image))
            except F.BudgetExceeded as e:
                return _json(409, {"error": str(e), "budget": True})
            except F.FoodAIError as e:  # no se guarda nada: la web conserva la foto y deja reintentar o apuntarlo a mano
                return _json(502, {"error": str(e)})
            finally:
                image = None  # la foto no se guarda en ningún sitio
                _push("ai_usage_lambda.log")
        fresh()
        F.upsert(entry)
        _push("food.json")
        return out(entry=entry)
    if path in ("/api/food/update", "/api/food/delete", "/api/food/repeat"):
        eid = str(payload.get("id") or "")
        fresh()
        try:
            if path.endswith("update"):
                entry = F.update_entry(eid, payload)
            elif path.endswith("repeat"):
                entry = F.repeat_entry(eid, payload)
            else:
                if not F.delete_entry(eid):
                    return _json(404, {"error": "Esa comida ya no existe."})
                entry = None
        except LookupError as e:
            return _json(404, {"error": str(e)})
        except ValueError as e:
            return _json(400, {"error": str(e)})
        _push("food.json")
        return out(entry=entry) if entry else out()
    return _json(404, {"error": "no encontrado"})


# ------------------------------------------------------------------ menú y compra semanal
SHOP_STALE = 600  # un menú "generándose" desde hace más de 10 min se da por fallido


def _shopping(path: str, method: str, payload: dict, user: dict):
    """Plan de comidas y lista de la compra. Generar el menú (IA, ~30-60 s) va en segundo plano como el plan."""
    from garmin_stats import catalog as CAT, food as F, shopping as SH
    cat = CAT.load_s3(s3, BUCKET)

    def out(status=200):
        st = SH.load()
        job = st.get("job") or {}
        if job.get("status") == "running" and time.time() - job.get("at", 0) > SHOP_STALE:
            st["job"] = {"status": "error", "error": "El menú ha tardado demasiado. Inténtalo de nuevo.", "at": job.get("at")}
        return _json(status, SH.view(cat, st, F.load()))

    def fresh():  # relee shopping.json justo antes de cambiarlo (otro móvil o el menú que acaba de generarse)
        p = ROOT / "data" / "shopping.json"
        try:
            s3.download_file(BUCKET, _sp("shopping.json"), str(p))
        except s3.exceptions.ClientError:
            p.unlink(missing_ok=True)

    if path == "/api/shopping" and method == "GET":
        return out()
    if method != "POST":
        return _json(405, {"error": "método no permitido"})
    if path == "/api/shopping/prefs":
        fresh()
        try:
            SH.set_prefs(payload)
        except ValueError as e:
            return _json(400, {"error": str(e)})
        _push("shopping.json")
        return out()
    if not SH.prefs()["enabled"]:
        return _json(409, {"error": "Activa primero el plan de comidas y compra semanal."})
    if path == "/api/shopping/generate":
        from garmin_stats import ai
        fresh()
        st = SH.load()
        job = st.get("job") or {}
        if job.get("status") == "running" and time.time() - job.get("at", 0) < SHOP_STALE:
            return _json(409, {"error": "Ya se está preparando tu menú. Espera un momento."})
        if ai.over_budget():
            return _json(409, {"error": f"Has llegado al tope de IA de este mes ({ai.budget():.0f} $). "
                                        "El menú se podrá generar el día 1.", "budget": True})
        start = payload.get("start") if payload.get("start") in ("today", "monday") else None
        st["job"] = {"status": "running", "at": int(time.time()), "start": start}
        SH.save(st)
        _push("shopping.json")
        _lambda.invoke(FunctionName=FUNCTION_NAME, InvocationType="Event",
                       Payload=json.dumps({"job": "shopping", "uid": user["uid"], "body": {"start": start}}).encode())
        return out(202)
    if path in ("/api/shopping/item", "/api/shopping/delete"):
        fresh()
        try:
            SH.update_item(payload) if path.endswith("item") else SH.delete_plan()
        except LookupError as e:
            return _json(404, {"error": str(e)})
        _push("shopping.json")
        return out()
    return _json(404, {"error": "no encontrado"})


def _run_shopping(event):
    """Genera el menú de la semana de una persona (una llamada a la IA) y deja la lista lista para la web."""
    user = U.find(U.load(s3, BUCKET), uid=event.get("uid"))
    if not user:
        return {"ok": False}
    _use(user)
    _setup_key()
    has_data = _pull()
    from garmin_stats import coach, food, shopping as SH
    data = _read_data() if has_data else {}
    try:
        SH.generate(data, coach.load(), food.load(), (event.get("body") or {}).get("start"))
        job = {"status": "done", "at": int(time.time())}
    except SH.ShoppingError as e:
        job = {"status": "error", "error": str(e)[:300], "at": int(time.time())}
    except Exception as e:  # noqa: BLE001 - se enseña un mensaje genérico; el detalle va al log
        print(f"menú: error {type(e).__name__}: {str(e)[:300]}")
        job = {"status": "error", "error": "No se ha podido preparar el menú. Inténtalo de nuevo.", "at": int(time.time())}
    st = SH.load()
    st["job"] = job
    SH.save(st)
    _push("shopping.json", "ai_usage_lambda.log")
    return {"ok": job["status"] == "done"}


# ------------------------------------------------------------------ calendario
def _calendar_link(user: dict, payload: dict | None):
    """Enlace privado al calendario del plan. POST {"action": "enable" | "rotate" | "disable"}."""
    if payload is not None:
        action = payload.get("action")
        if action in ("enable", "rotate"):
            if action == "rotate" or not user.get("calToken"):
                user = U.update(s3, BUCKET, user["uid"], calToken=secrets.token_urlsafe(32)) or user
        elif action == "disable":
            user = U.update(s3, BUCKET, user["uid"], calToken=None) or user
        else:
            return _json(400, {"error": "Acción no válida."})
    tok = user.get("calToken")
    return _json(200, {"path": f"/api/cal/{tok}.ics" if tok else None})


def _calendar_feed(token: str):
    """El calendario (.ics) de quien tenga este enlace secreto. Solo lectura: el plan, sin datos de salud."""
    user = next((u for u in U.load(s3, BUCKET) if u.get("calToken") and hmac.compare_digest(u["calToken"], token)), None)
    if not user:
        return {"statusCode": 404, "headers": {"content-type": "text/plain; charset=utf-8", "cache-control": "no-store"},
                "body": "Este enlace ya no es válido."}
    _use(user)
    _pull()
    from garmin_stats import calendar_ics, coach
    state = coach.load()
    refs = None
    try:
        refs = (_read_data().get("paces") or {}).get("refs")
    except (OSError, ValueError):
        pass
    name = "Plan de entreno" + (f" · {state['plan']['goal']}" if state.get("plan") else "")
    body = calendar_ics.build(state.get("plan"), refs, name)
    return {"statusCode": 200, "headers": {"content-type": "text/calendar; charset=utf-8", "cache-control": "no-store",
                                           "content-disposition": 'inline; filename="plan.ics"'}, "body": body}


# ------------------------------------------------------------------ cuenta
def _me(user: dict):
    onb = _get_json(_sp("onboarding.json"), {})
    coach = _get_json(_sp("coach.json"), {})
    return _json(200, {
        "email": user["email"], "name": user.get("name") or "", "role": user.get("role", "friend"),
        "status": user.get("status"), "budgetUsd": user.get("budgetUsd") or FRIEND_BUDGET,
        "monthSpendUsd": _month_spend(user["uid"]),
        "consented": bool(user.get("consentAt")),
        "hasData": _exists(_site("data.js")), "hasGoal": bool(onb.get("goal")), "hasPlan": bool(coach.get("plan")),
        "source": U.source(user), "google": _google_view(user),
        "planJob": coach.get("job"), "sync": _get_json(_sp("sync_status.json"), {}),
        "owner": OWNER,
        "seenRelease": user.get("seenRelease"),
        "since": user.get("consentAt") or user.get("joinedAt") or user.get("invitedAt"),
    })


def _sync(method: str, user: dict):
    """Sincronizar con Garmin ahora (botón "actualizar" y onboarding). GET devuelve el estado."""
    st = _get_json(_sp("sync_status.json"), {})
    now = time.time()
    if method == "GET":
        return _json(200, st)
    if user.get("status") == "google_reauth":
        return _json(409, {"error": "Google Health ya no da acceso a tus datos. Vuelve a conectarlo."})
    if user.get("status") not in ("active", "google_not_linked"):  # sin enlazar: se reintenta por si ya lo ha hecho
        return _json(409, {"error": "Primero conecta tu Garmin."})
    if st.get("status") == "running" and now - st.get("at", 0) < STALE:
        return _json(200, {**st, "already": True})  # ya hay una en marcha: la web espera a esa
    if st.get("status") == "done" and now - st.get("finished", 0) < 45:
        return _json(200, {**st, "recent": True})  # acaba de terminar: no se vuelve a llamar a Garmin
    return _json(202, _start_sync(user))


def _start_sync(user: dict) -> dict:
    token = base64.urlsafe_b64encode(os.urandom(9)).decode()
    st = {"status": "running", "at": int(time.time()), "token": token, "manual": True}
    _put_json(U.state_prefix(user["uid"]) + "sync_status.json", st)
    _lambda.invoke(FunctionName=os.environ["SYNC_FUNCTION"], InvocationType="Event",
                   Payload=json.dumps({"uid": user["uid"], "token": token, "manual": True}).encode())
    return st


def _onboarding_key(user: dict, payload: dict):
    """Comprueba la clave personal de Garmin, la guarda cifrada y lanza la primera descarga."""
    key = re.sub(r"\s+", "", str(payload.get("key") or ""))
    if U.source(user) == "google":
        return _json(409, {"error": "Tienes Google Health conectado. Desconéctalo antes de usar Garmin."})
    if user.get("dataSource") == "google" and _sync_running(user["uid"]):
        return _json(409, {"error": BUSY})  # se van a borrar sus datos de Google: no con una descarga a medias
    if not payload.get("consent") and not user.get("consentAt"):
        return _json(400, {"error": "Antes tienes que aceptar cómo se guardan tus datos."})
    if len(key) < 20 or len(key) > 400:
        return _json(400, {"error": "Esa clave no parece completa. Cópiala entera desde Garmin Connect."})
    from garmin_personal_api import GarminPersonalApiClient, PersonalApiAuthenticator
    from garmin_personal_api.errors import HttpError
    try:
        (ROOT).mkdir(parents=True, exist_ok=True)
        auth = PersonalApiAuthenticator(bearer_token_cache_file=str(ROOT / "check-token.json"))
        token = auth.obtain_token(key).access_token
        GarminPersonalApiClient(token).get_user_profile_settings()
    except HttpError as e:
        if e.status_code in (400, 401, 403):
            return _json(400, {"error": "Garmin no acepta esta clave. Revisa que la has copiado entera y que no ha caducado."})
        return _json(502, {"error": f"Garmin no responde ahora (HTTP {e.status_code}). Prueba en unos minutos."})
    except Exception:  # noqa: BLE001
        return _json(502, {"error": "No he podido hablar con Garmin. Prueba en unos minutos."})
    finally:
        (ROOT / "check-token.json").unlink(missing_ok=True)
    _ssm.put_parameter(Name=U.key_param(user["uid"]), Value=key, Type="SecureString", Overwrite=True)
    if user.get("dataSource") == "google":  # venía de Google Health: sus datos no se mezclan con los de Garmin
        _wipe_health_data(user["uid"])
    fields = {"status": "active", "keyAt": U.now(), "source": "garmin", "dataSource": "garmin"}
    if user.get("dataSource") == "google":
        fields["sourceChangedAt"] = U.now()  # una descarga anterior de Google ya no puede subir nada
    if not user.get("consentAt"):
        fields["consentAt"] = U.now()
    user = U.update(s3, BUCKET, user["uid"], **fields) or user
    st = _get_json(_sp("sync_status.json"), {})
    if not (st.get("status") == "running" and time.time() - st.get("at", 0) < STALE):
        st = _start_sync(user)
    return _json(200, {"ok": True, "sync": st})


def _onboarding_goal(user: dict, payload: dict):
    """Guarda el objetivo del onboarding; el plan se crea al terminar la primera descarga."""
    try:
        race = date.fromisoformat(str(payload.get("date")))
    except ValueError:
        return _json(400, {"error": "Falta la fecha del objetivo."})
    today = date.today()
    if race <= today + timedelta(days=13):
        return _json(400, {"error": "La fecha tiene que estar al menos a dos semanas vista."})
    if race > today + timedelta(weeks=30):
        return _json(400, {"error": "Elige una fecha a menos de 30 semanas."})
    keep = ("goal", "date", "goalTime", "daysPerWeek", "longRunDay", "gymDays", "bodyGoal", "ambition", "notes")
    goal = {k: payload[k] for k in keep if payload.get(k) not in (None, "")}
    _put_json(_sp("onboarding.json"), {"goal": goal, "at": U.now()})
    # Si su historial ya está descargado (p. ej. lo pone más tarde), el plan se crea ya
    st = _get_json(_sp("sync_status.json"), {})
    coach = _get_json(_sp("coach.json"), {})
    if st.get("status") == "done" and _exists(_site("data.js")) and not coach.get("plan"):
        _put_json(_sp("onboarding.json"), {"goal": goal, "at": U.now(), "planRequested": U.now()})
        _lambda.invoke(FunctionName=FUNCTION_NAME, InvocationType="Event",
                       Payload=json.dumps({"job": "create", "uid": user["uid"], "body": goal, "mark": True}).encode())
        return _json(200, {"ok": True, "planStarted": True})
    return _json(200, {"ok": True})


def _delete_prefix(prefix: str) -> int:
    """Borra todas las versiones (el bucket guarda versiones antiguas 3 días)."""
    n = 0
    for page in s3.get_paginator("list_object_versions").paginate(Bucket=BUCKET, Prefix=prefix):
        objs = [{"Key": v["Key"], "VersionId": v["VersionId"]} for v in page.get("Versions", []) + page.get("DeleteMarkers", [])]
        for i in range(0, len(objs), 1000):
            s3.delete_objects(Bucket=BUCKET, Delete={"Objects": objs[i:i + 1000], "Quiet": True})
            n += len(objs[i:i + 1000])
    return n


def _delete_user(user: dict) -> None:
    uid = user["uid"]
    _delete_prefix(U.state_prefix(uid).rsplit("state/", 1)[0])  # users/<uid>/
    _delete_prefix(U.site_prefix(uid))
    try:
        _ssm.delete_parameter(Name=U.key_param(uid))
    except _ssm.exceptions.ParameterNotFound:
        pass
    if _google_forget(uid) is False:
        print("google: permiso no retirado al borrar la cuenta (se ha borrado igualmente)")
    users = [u for u in U.load(s3, BUCKET) if u["uid"] != uid]
    U.save(s3, BUCKET, users)


# ------------------------------------------------------------------ Google Health (fuente de datos sin Garmin)
def _gh_cfg() -> dict | None:
    """Cliente OAuth de Google Health (SSM). Sin parámetros, Google Health no se ofrece; se vuelve a mirar cada 5 min."""
    if _GH.get("id"):
        return _GH
    if time.time() - _GH.get("checked", 0) < 300:
        return None
    _GH["checked"] = time.time()
    try:
        cid = _ssm.get_parameter(Name=GH_ID_PARAM)["Parameter"]["Value"].strip()
        sec = _ssm.get_parameter(Name=GH_SECRET_PARAM, WithDecryption=True)["Parameter"]["Value"].strip()
    except Exception:  # noqa: BLE001 - sin parámetro o sin permiso: no disponible
        return None
    if not cid or not sec or cid.startswith("PLACEHOLDER") or sec.startswith("PLACEHOLDER"):
        return None
    _GH.update(id=cid, secret=sec)
    return _GH


def _google_view(user: dict) -> dict:
    """Lo que la web necesita saber de Google Health (para enseñar o no el botón y avisos)."""
    out: dict = {"available": bool(PUBLIC_HOST) and _gh_cfg() is not None, "connected": U.source(user) == "google"}
    if out["connected"]:
        st = user.get("status")
        out["status"] = {"google_reauth": "reauth", "google_not_linked": "not_linked"}.get(st, "ok")
        out["scopes"] = user.get("googleScopes") or []
        out["connectedAt"] = user.get("googleAt")
        if out["status"] == "not_linked":
            out["linkUrl"] = user.get("googleLinkUrl") or GH.LINK_URL
    return out


def _query(event) -> dict:
    from urllib.parse import parse_qs
    return {k: v[0] for k, v in parse_qs(event.get("rawQueryString") or "").items()}


def _redirect(location: str, cookies=None):
    return {"statusCode": 302, "headers": {"location": location, "cache-control": "no-store", "referrer-policy": "no-referrer"},
            "cookies": cookies or [], "body": ""}


def _back(ok: bool, back: str = "", reason: str = "") -> str:
    """Vuelta a la web: /?google=ok o /?google=error&reason=... y, si se pidió, #pestaña."""
    from urllib.parse import urlencode
    q = {"google": "ok"} if ok else {"google": "error", "reason": reason or "error"}
    return "/?" + urlencode(q) + (f"#{back}" if back else "")


def _safe_back(v) -> str:
    v = str(v or "")
    return v if re.fullmatch(r"[a-z][a-z0-9-]{0,30}", v) else ""


def _viewer_host(headers: dict) -> str | None:
    """Dominio público de la web: solo el configurado (PUBLIC_HOST). Cualquier otro x-viewer-host se rechaza."""
    h = (headers.get("x-viewer-host") or "").strip().lower()
    return h if PUBLIC_HOST and hmac.compare_digest(h, PUBLIC_HOST) else None


def _sync_running(uid: str) -> bool:
    st = _get_json(U.state_prefix(uid) + "sync_status.json", {})
    return st.get("status") == "running" and time.time() - st.get("at", 0) < STALE


def _google_connect(user: dict, headers: dict, qs: dict):
    """Manda a Google a dar permiso (solo lectura). ?back=pestaña para volver ahí; ?consent=1 si acaba de aceptar."""
    back = _safe_back(qs.get("back"))
    g, host = _gh_cfg(), _viewer_host(headers)
    if not g or not host:
        return _redirect(_back(False, back, "unavailable"))
    if U.source(user) == "garmin":
        return _redirect(_back(False, back, "garmin"))
    consent = qs.get("consent") == "1"
    if not consent and not user.get("consentAt"):
        return _redirect(_back(False, back, "consent"))
    verifier, challenge = GH.pkce()
    state = GH.b64url(secrets.token_bytes(16))
    tmp = GH.b64url(json.dumps({"v": verifier, "s": state, "b": back, "c": consent, "u": user["uid"]}).encode())
    return _redirect(GH.auth_url(g["id"], f"https://{host}/api/google/callback", state, challenge),
                     [f"{GH_COOKIE}={tmp}; Path=/api/google; Max-Age=600; Secure; HttpOnly; SameSite=Lax"])


def _google_callback(user: dict, headers: dict, qs: dict, cookies):
    """Vuelta de Google: comprueba state, cambia el código por el permiso, lo guarda cifrado y lanza la descarga."""
    clear = [f"{GH_COOKIE}=; Path=/api/google; Max-Age=0; Secure; HttpOnly; SameSite=Lax"]
    raw = dict(c.split("=", 1) for c in cookies or [] if "=" in c).get(GH_COOKIE, "")
    try:
        tmp = json.loads(base64.urlsafe_b64decode(raw + "=="))
    except ValueError:
        tmp = {}
    if not isinstance(tmp, dict):  # cookie manipulada
        tmp = {}
    back = _safe_back(tmp.get("b"))

    def fail(reason: str):
        return _redirect(_back(False, back, reason), clear)

    if not tmp or tmp.get("u") != user["uid"] or not hmac.compare_digest(str(qs.get("state") or ""), str(tmp.get("s") or "")):
        return fail("state")
    if qs.get("error"):
        return fail("denied" if qs["error"] == "access_denied" else "error")
    if not user.get("consentAt") and tmp.get("c") is not True:  # sin la privacidad aceptada no se guarda nada
        return fail("consent")
    uid = user["uid"]
    switching = bool(user.get("dataSource") and user.get("dataSource") != "google")
    if switching and _sync_running(uid):
        return fail("busy")
    g, host = _gh_cfg(), _viewer_host(headers)
    if not g or not host:
        return fail("unavailable")
    if not qs.get("code"):
        return fail("state")
    try:
        tok = GH.exchange(g["id"], g["secret"], qs["code"], str(tmp.get("v") or ""), f"https://{host}/api/google/callback")
    except (GH.GoogleError, OSError, ValueError):
        return fail("token")
    scopes = GH.granted(tok.get("scope"))
    if not scopes:  # no marcó ningún permiso de salud: no hay nada que leer
        GH.revoke(tok["refresh_token"])
        return fail("scopes")
    status, link, ident = "active", None, {}
    try:
        ident = GH.Client(g["id"], g["secret"], tok["refresh_token"], access_token=tok["access_token"]).identity()
    except GH.NotLinked as e:
        status, link = "google_not_linked", e.link_url
    except (GH.GoogleError, OSError, ValueError):
        pass  # lo vuelve a comprobar la sincronización
    if switching:
        _wipe_health_data(uid)  # nunca se mezclan datos de dos fuentes
    _ssm.put_parameter(Name=U.google_param(uid), Type="SecureString", Overwrite=True, Value=json.dumps({
        "refresh_token": tok["refresh_token"], "scope": tok.get("scope") or "",
        "healthUserId": ident.get("healthUserId"), "at": U.now()}))
    fields = {"source": "google", "dataSource": "google", "status": status, "googleAt": U.now(),
              "googleScopes": scopes, "googleLinkUrl": link}
    if switching:
        fields["sourceChangedAt"] = U.now()  # una descarga anterior de la otra fuente ya no puede subir nada
    if not user.get("consentAt"):
        fields["consentAt"] = U.now()  # aceptada en la web justo antes de conectar (?consent=1)
    user = U.update(s3, BUCKET, uid, **fields) or user
    if status != "active":
        return fail("not_linked")
    st = _get_json(U.state_prefix(uid) + "sync_status.json", {})
    if not (st.get("status") == "running" and time.time() - st.get("at", 0) < STALE):
        _start_sync(user)
    return _redirect(_back(True, back), clear)


def _google_forget(uid: str) -> bool | None:
    """Retira el permiso en Google y borra el guardado. None si no había permiso; False si Google no lo retiró."""
    try:
        raw = _ssm.get_parameter(Name=U.google_param(uid), WithDecryption=True)["Parameter"]["Value"]
    except _ssm.exceptions.ParameterNotFound:
        return None  # nunca conectó Google Health (p. ej. una cuenta de Garmin)
    try:
        token = json.loads(raw).get("refresh_token") or ""
    except (ValueError, AttributeError):
        token = ""
    revoked = bool(token) and GH.revoke(token)
    if not revoked:
        print("google: Google no ha retirado el permiso; se borra igualmente el guardado")
    try:
        _ssm.delete_parameter(Name=U.google_param(uid))
    except _ssm.exceptions.ParameterNotFound:
        pass
    return revoked


def _wipe_health_data(uid: str) -> None:
    """Borra los datos descargados (no el plan, la comida ni el chat) para empezar de cero con otra fuente."""
    sp, site = U.state_prefix(uid), U.site_prefix(uid)
    for prefix in (sp + "garmin.sqlite", sp + "sync_status.json", sp + "fit/", site + "data.js", site + "acts/"):
        _delete_prefix(prefix)


def _google_disconnect(user: dict, payload: dict):
    """Desconecta Google Health: retira el permiso. Con {"deleteData": true} borra también lo descargado."""
    if U.source(user) != "google":
        return _json(409, {"error": "No tienes Google Health conectado."})
    uid = user["uid"]
    delete = bool(payload.get("deleteData"))
    if delete and _sync_running(uid):
        return _json(409, {"error": BUSY})
    revoked = _google_forget(uid) is not False
    # sourceChangedAt: una descarga en marcha ya no sube nada ni cambia el estado (la sincronización lo comprueba)
    fields = {"source": None, "status": "onboarding", "googleAt": None, "googleScopes": None, "googleLinkUrl": None,
              "sourceChangedAt": U.now()}
    if delete:
        _wipe_health_data(uid)
        fields["dataSource"] = None
    U.update(s3, BUCKET, uid, **fields)
    # revoked=false: la web le dice que lo quite a mano en https://myaccount.google.com/connections
    return _json(200, {"ok": True, "deleted": delete, "revoked": revoked})


# ------------------------------------------------------------------ administración (solo el dueño)
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", re.I)


def _admin(path: str, method: str, payload: dict):
    if path != "/api/admin/users":
        return _json(404, {"error": "no encontrado"})
    users = U.load(s3, BUCKET)
    if method == "GET":
        out = []
        for u in users:
            st = _get_json(U.state_prefix(u["uid"]) + "sync_status.json", {})
            stats = _usage_stats(u["uid"])
            out.append({"email": u["email"], "name": u.get("name") or "", "role": u.get("role"), "status": u.get("status"),
                        "source": U.source(u),
                        "budgetUsd": u.get("budgetUsd"), "monthSpendUsd": stats["monthCostUsd"],
                        "totalCostUsd": stats["totalCostUsd"], "calls": stats["calls"], "lastAi": stats["lastAi"],
                        "invitedAt": u.get("invitedAt"), "joinedAt": u.get("joinedAt"),
                        "lastSync": st.get("finished"), "syncStatus": st.get("status")})
        return _json(200, {"users": out})
    action = payload.get("action")
    email = str(payload.get("email") or "").strip().lower()
    if action == "add":
        if not EMAIL_RE.match(email):
            return _json(400, {"error": "Ese email no es válido."})
        if U.find(users, email=email):
            return _json(400, {"error": "Ya tiene invitación."})
        if sum(1 for u in users if u.get("role") != "owner") >= 10:
            return _json(400, {"error": "Máximo 10 invitaciones."})
        budget = float(payload.get("budgetUsd") or FRIEND_BUDGET)
        users.append({"email": email, "uid": U.uid_for(email, SESSION_SECRET), "name": str(payload.get("name") or "")[:60],
                      "role": "friend", "budgetUsd": max(0.0, min(budget, 20.0)), "status": "invited", "invitedAt": U.now()})
        U.save(s3, BUCKET, users)
    elif action == "remove":
        u = U.find(users, email=email)
        if not u:
            return _json(404, {"error": "No existe."})
        if u.get("role") == "owner":
            return _json(400, {"error": "No puedes quitarte a ti mismo."})
        _delete_user(u)
    elif action == "budget":
        u = U.find(users, email=email)
        if not u:
            return _json(404, {"error": "No existe."})
        u["budgetUsd"] = max(0.0, min(float(payload.get("budgetUsd") or 0), 50.0))
        U.save(s3, BUCKET, users)
    else:
        return _json(400, {"error": "Acción no válida."})
    return _admin(path, "GET", {})
