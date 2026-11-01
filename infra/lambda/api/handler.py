"""API de la web en AWS (Lambda detrás de CloudFront, ruta /api/*): chat y plan de entreno.

Reutiliza el código del proyecto (garmin_stats.server.ask y garmin_stats.coach). El estado vive en S3:
  site/data.js                 datos de la web (los sube el PC cada hora)
  state/coach.json             plan, memoria del coach y valoraciones
  state/settings.json          ajustes (huecos con el reloj roto)
  state/ai_usage*.log          gasto de IA del PC y de Lambda
Crear y reajustar el plan tarda minutos y CloudFront corta a los 60 s, así que se hace en segundo
plano (la propia Lambda se invoca en asíncrono) y la web consulta /api/plan hasta que termina.
"""

import base64
import hashlib
import hmac
import json
import os
import time
from pathlib import Path

import boto3

ROOT = Path("/tmp/gs")
os.environ.setdefault("GARMIN_STATS_ROOT", str(ROOT))
os.environ.setdefault("GARMIN_STATS_USAGE_LOG", "ai_usage_lambda.log")
os.environ["HOME"] = "/tmp/home"  # la clave de Anthropic se escribe en ~/.config/anthropic (en /tmp)

BUCKET = os.environ["BUCKET"]
SESSION_SECRET = os.environ["SESSION_SECRET"].encode()
ORIGIN_SECRET = os.environ["ORIGIN_SECRET"]
ALLOWED = {e.strip().lower() for e in os.environ["ALLOWED_EMAILS"].split(",") if e.strip()}
ANTHROPIC_PARAM = os.environ["ANTHROPIC_KEY_PARAM"]
FUNCTION_NAME = os.environ.get("AWS_LAMBDA_FUNCTION_NAME", "")

s3 = boto3.client("s3")
_lambda = boto3.client("lambda")
_ssm = boto3.client("ssm")

STATE = ["coach.json", "settings.json", "ai_usage.log", "ai_usage_lambda.log", "ai_cache.json"]


def _setup_key():
    key_file = Path("/tmp/home/.config/anthropic/garmin-stats-key")
    if not key_file.exists():
        key_file.parent.mkdir(parents=True, exist_ok=True)
        val = _ssm.get_parameter(Name=ANTHROPIC_PARAM, WithDecryption=True)["Parameter"]["Value"]
        key_file.write_text(val)
        key_file.chmod(0o600)


def _pull():
    (ROOT / "site").mkdir(parents=True, exist_ok=True)
    (ROOT / "data").mkdir(parents=True, exist_ok=True)
    s3.download_file(BUCKET, "site/data.js", str(ROOT / "site" / "data.js"))
    for name in STATE:
        dst = ROOT / "data" / name
        try:
            s3.download_file(BUCKET, f"state/{name}", str(dst))
        except s3.exceptions.ClientError:
            dst.unlink(missing_ok=True)


def _push(*names):
    for name in names:
        p = ROOT / "data" / name
        if p.exists():
            s3.upload_file(str(p), BUCKET, f"state/{name}")


def _read_data() -> dict:
    raw = (ROOT / "site" / "data.js").read_text(encoding="utf-8")
    return json.loads(raw[raw.index("=") + 1:].rstrip().rstrip(";"))


def _refresh_site(coach) -> None:
    """Actualiza el bloque `coach` de data.js para que la portada lo vea al momento."""
    from datetime import datetime
    data = _read_data()
    data["coach"] = coach.view(data)
    data["generatedAt"] = datetime.now().astimezone().isoformat(timespec="seconds")
    body = "window.__GARMIN__=" + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n"
    s3.put_object(Bucket=BUCKET, Key="site/data.js", Body=body.encode(), ContentType="text/javascript; charset=utf-8",
                  CacheControl="no-store")


def _session_ok(cookies: list[str]) -> bool:
    for c in cookies or []:
        if c.startswith("gs_session="):
            try:
                b64, exp, mac = c.split("=", 1)[1].split(".")
                good = hmac.new(SESSION_SECRET, f"{b64}.{exp}".encode(), hashlib.sha256).hexdigest()
                email = base64.urlsafe_b64decode(b64 + "==").decode().lower()
                return hmac.compare_digest(good, mac) and int(exp) > time.time() and email in ALLOWED
            except Exception:
                return False
    return False


def _json(status, obj):
    return {"statusCode": status, "headers": {"content-type": "application/json; charset=utf-8", "cache-control": "no-store"},
            "body": json.dumps(obj, ensure_ascii=False)}


def _with_job(view: dict, coach) -> dict:
    view["job"] = coach.load().get("job")
    return view


def _run_job(event):
    """Trabajo en segundo plano: crear o reajustar el plan."""
    from garmin_stats import coach
    _setup_key()
    _pull()
    action, body = event["job"], event.get("body") or {}

    def cancelled() -> bool:
        try:
            st = json.loads(s3.get_object(Bucket=BUCKET, Key="state/coach.json")["Body"].read())
            return bool((st.get("job") or {}).get("cancel"))
        except Exception:
            return False
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


def _sync_status() -> dict:
    try:
        return json.loads(s3.get_object(Bucket=BUCKET, Key="state/sync_status.json")["Body"].read())
    except Exception:  # noqa: BLE001
        return {}


def _sync(method: str):
    """Sincronizar con Garmin ahora (botón "actualizar" de la web). GET devuelve el estado."""
    st = _sync_status()
    now = time.time()
    if method == "GET":
        return _json(200, st)
    if st.get("status") == "running" and now - st.get("at", 0) < 300:
        return _json(200, {**st, "already": True})  # ya hay una en marcha: la web espera a esa
    if st.get("status") == "done" and now - st.get("finished", 0) < 45:
        return _json(200, {**st, "recent": True})  # acaba de terminar: no se vuelve a llamar a Garmin
    token = base64.urlsafe_b64encode(os.urandom(9)).decode()
    st = {"status": "running", "at": int(now), "token": token, "manual": True}
    s3.put_object(Bucket=BUCKET, Key="state/sync_status.json", Body=json.dumps(st).encode(), ContentType="application/json")
    _lambda.invoke(FunctionName=os.environ["SYNC_FUNCTION"], InvocationType="Event", Payload=json.dumps({"token": token}).encode())
    return _json(202, st)


def handler(event, _ctx):
    if "job" in event:  # invocación asíncrona propia
        return _run_job(event)

    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    if not hmac.compare_digest(headers.get("x-origin-verify", ""), ORIGIN_SECRET):
        return _json(403, {"error": "prohibido"})
    if not _session_ok(event.get("cookies")):
        return _json(401, {"error": "login"})

    method = event["requestContext"]["http"]["method"]
    path = event.get("rawPath", "")
    body = event.get("body") or ""
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode()
    try:
        payload = json.loads(body) if body else {}
    except json.JSONDecodeError:
        return _json(400, {"error": "JSON no válido"})

    if path == "/api/sync":
        return _sync(method)

    _setup_key()
    _pull()
    from garmin_stats import coach, server

    if path == "/api/health":
        return _json(200, {"ok": True, "ai": True, "mode": "aws"})
    if path == "/api/plan" and method == "GET":
        return _json(200, _with_job(coach.view(_read_data()), coach))
    if method != "POST":
        return _json(405, {"error": "método no permitido"})

    if path == "/api/push/subscribe":
        sub = payload.get("subscription") or {}
        if not str(sub.get("endpoint", "")).startswith("https://") or not (sub.get("keys") or {}).get("p256dh"):
            return _json(400, {"error": "Suscripción no válida."})
        try:
            subs = json.loads(s3.get_object(Bucket=BUCKET, Key="state/push.json")["Body"].read())
        except s3.exceptions.NoSuchKey:
            subs = []
        subs = [x for x in subs if x.get("endpoint") != sub["endpoint"]] + [sub]
        s3.put_object(Bucket=BUCKET, Key="state/push.json", Body=json.dumps(subs[-10:]).encode())
        return _json(200, {"ok": True, "devices": len(subs[-10:])})
    if path == "/api/push/test":
        _lambda.invoke(FunctionName=os.environ["NOTIFY_FUNCTION"], InvocationType="Event",
                       Payload=json.dumps({"message": {"title": "Mi salud", "body": "¡Listo! Así te llegará el aviso de cada mañana.",
                                                       "url": "/#hoy", "tag": "test"}}).encode())
        return _json(200, {"ok": True})
    if path == "/api/ask":
        res = server.ask(payload.get("messages") or [])
        _push("ai_usage_lambda.log")
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
                       Payload=json.dumps({"job": state["job"]["action"], "body": payload}).encode())
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
