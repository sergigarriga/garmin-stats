"""API de la web en AWS (Lambda detrás de CloudFront, ruta /api/*). Versión multipersona.

Cada petición trae la cookie de sesión firmada por el login; de ahí sale el email y, con el registro de
usuarias (S3 admin/users.json), su id. Todo lo que se lee o escribe va a SU carpeta:
  site/u/<uid>/data.js           su web (la escribe la sincronización)
  users/<uid>/state/coach.json   su plan, memoria del coach y valoraciones
  users/<uid>/state/*.log        su gasto de IA (tope mensual propio: budgetUsd en el registro)
  /garmin-stats/users/<uid>/garmin-key (SSM, cifrado)  su clave de Garmin
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
import shutil
import time
from datetime import date, timedelta
from pathlib import Path

import boto3

ROOT = Path("/tmp/gs")
HOME = Path("/tmp/home")
os.environ.setdefault("GARMIN_STATS_ROOT", str(ROOT))
os.environ.setdefault("GARMIN_STATS_USAGE_LOG", "ai_usage_lambda.log")
os.environ["HOME"] = str(HOME)  # la clave de Anthropic se escribe en ~/.config/anthropic (en /tmp)

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

STATE = ["coach.json", "settings.json", "ai_usage.log", "ai_usage_lambda.log", "ai_cache.json"]
CUR: dict = {}  # persona de esta petición


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
    """Actualiza el bloque `coach` de su data.js para que la portada lo vea al momento."""
    from datetime import datetime
    data = _read_data()
    data["coach"] = coach.view(data)
    data["generatedAt"] = datetime.now().astimezone().isoformat(timespec="seconds")
    body = "window.__GARMIN__=" + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n"
    s3.put_object(Bucket=BUCKET, Key=_site("data.js"), Body=body.encode(), ContentType="text/javascript; charset=utf-8",
                  CacheControl="no-store")


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


def _json(status, obj, cookies=None):
    return {"statusCode": status, "headers": {"content-type": "application/json; charset=utf-8", "cache-control": "no-store"},
            "cookies": cookies or [], "body": json.dumps(obj, ensure_ascii=False)}


def _with_job(view: dict, coach) -> dict:
    view["job"] = coach.load().get("job")
    return view


# ------------------------------------------------------------------ trabajos en segundo plano
def _run_job(event):
    """Crear o reajustar el plan de una persona (lo lanza la propia API o la sincronización)."""
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
        state["job"] = {"status": "error", "action": action, "error": str(e)[:300], "at": int(time.time())}
        coach.save(state)
    _push("coach.json", "ai_usage_lambda.log")
    _refresh_site(coach)
    return {"ok": True}


# ------------------------------------------------------------------ entrada
def handler(event, _ctx):
    if "job" in event:  # invocación asíncrona propia
        return _run_job(event)

    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    if not hmac.compare_digest(headers.get("x-origin-verify", ""), ORIGIN_SECRET):
        return _json(403, {"error": "prohibido"})
    email = _session_email(event.get("cookies"))
    if not email:
        return _json(401, {"error": "login"})
    user = U.find(U.load(s3, BUCKET), email=email)
    if not user:
        return _json(401, {"error": "login"})  # la invitación se ha retirado

    method = event["requestContext"]["http"]["method"]
    path = event.get("rawPath", "")
    body = event.get("body") or ""
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode()
    try:
        payload = json.loads(body) if body else {}
    except json.JSONDecodeError:
        return _json(400, {"error": "JSON no válido"})

    _use(user)

    # --- cuenta, onboarding y administración (no necesitan sus datos)
    if path == "/api/health":
        return _json(200, {"ok": True, "ai": True, "mode": "aws"})
    if path == "/api/me":
        return _me(user)
    if path == "/api/sync":
        return _sync(method, user)
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
                       Payload=json.dumps({"uid": user["uid"], "message": {"title": "Mi salud", "body": "¡Listo! Así te llegará el aviso de cada mañana.",
                                                                           "url": "/#hoy", "tag": "test"}}).encode())
        return _json(200, {"ok": True})

    # --- chat y plan (necesitan sus datos)
    _setup_key()
    if not _pull():
        return _json(409, {"error": "Aún no hay datos: termina de conectar tu Garmin."})
    from garmin_stats import coach, server

    if path == "/api/plan" and method == "GET":
        return _json(200, _with_job(coach.view(_read_data()), coach))
    if method != "POST":
        return _json(405, {"error": "método no permitido"})
    if path == "/api/ask":
        msgs = payload.get("messages") or []
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
            coach.structure_week(payload.get("week", ""))
        except RuntimeError as e:
            return _json(400, {"error": str(e)})
        _push("coach.json", "ai_usage_lambda.log")
        _refresh_site(coach)
        return _json(200, _with_job(coach.view(_read_data()), coach))
    if path == "/api/plan/feedback":
        coach.feedback(payload["date"], payload.get("rating", 3), payload.get("note", ""))
    elif path == "/api/plan/delete":
        coach.delete()
    else:
        return _json(404, {"error": "no encontrado"})
    _push("coach.json")
    _refresh_site(coach)
    return _json(200, _with_job(coach.view(_read_data()), coach))


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
        "planJob": coach.get("job"), "sync": _get_json(_sp("sync_status.json"), {}),
        "owner": OWNER,
    })


def _sync(method: str, user: dict):
    """Sincronizar con Garmin ahora (botón "actualizar" y onboarding). GET devuelve el estado."""
    st = _get_json(_sp("sync_status.json"), {})
    now = time.time()
    if method == "GET":
        return _json(200, st)
    if user.get("status") != "active":
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
    fields = {"status": "active", "keyAt": U.now()}
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
    users = [u for u in U.load(s3, BUCKET) if u["uid"] != uid]
    U.save(s3, BUCKET, users)


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
            out.append({"email": u["email"], "name": u.get("name") or "", "role": u.get("role"), "status": u.get("status"),
                        "budgetUsd": u.get("budgetUsd"), "monthSpendUsd": _month_spend(u["uid"]),
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
