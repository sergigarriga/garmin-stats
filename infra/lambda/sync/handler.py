"""Sincronización en AWS (EventBridge Scheduler cada hora → esta Lambda). Versión multipersona.

- Programada (sin `uid`): lanza una ejecución por persona con Garmin conectado (invocación asíncrona a sí misma).
- Con `uid`: hace lo mismo que `garmin-stats all` para esa persona: descarga lo nuevo de Garmin (o de Google Health,
  si es su fuente), recalcula, escribe los textos de IA (y el lunes reajusta el plan) y publica su web.
- La primera vez baja el historial por tandas: cada ejecución trabaja unos 7 minutos, publica lo que tiene
  y se vuelve a lanzar hasta terminar. Al acabar, si dejó un objetivo en el onboarding, se crea su plan.

Estado en S3 (por persona):
  users/<uid>/state/garmin.sqlite, *.json, *.log, fit/   base de datos, plan, ajustes, caché y gasto de IA
  users/<uid>/state/sync_status.json                      candado y estado de la sincronización
  site/u/<uid>/data.js, acts/                             su web (CloudFront solo se la sirve a esa persona)
Antes de cada persona se vacían /tmp/gs y la caché de Garmin: nada pasa de una persona a otra.
"""

import hashlib
import json
import logging
import os
import shutil
import sqlite3
import time
from pathlib import Path

import boto3

# Hora de Madrid (Lambda va en UTC): "hoy" y "esta semana" cambian a medianoche de aquí. Regla POSIX: no necesita tzdata.
os.environ["TZ"] = "CET-1CEST,M3.5.0,M10.5.0/3"
time.tzset()

ROOT = Path("/tmp/gs")
HOME = Path("/tmp/home")
os.environ["GARMIN_STATS_ROOT"] = str(ROOT)
os.environ["HOME"] = str(HOME)

from garmin_stats import google_health as GH
from garmin_stats import users  # noqa: E402

BUCKET = os.environ["BUCKET"]
FUNCTION = os.environ.get("AWS_LAMBDA_FUNCTION_NAME", "garmin-stats-sync")
API_FUNCTION = os.environ.get("API_FUNCTION", "garmin-stats-api")
s3 = boto3.client("s3")
ssm = boto3.client("ssm")
lam = boto3.client("lambda")
STATE = ["garmin.sqlite", "coach.json", "settings.json", "wellness.json", "weather.json", "food.json", "ai_cache.json",
         "ai_usage.log", "ai_usage_lambda.log"]
# Los escribe la web (API) mientras esta sincronización corre: aquí solo se leen, nunca se suben (se pisarían los cambios).
READ_ONLY = {"settings.json", "wellness.json", "food.json", "ai_usage_lambda.log"}
STALE = 960      # una sincronización "en marcha" de hace más de 16 min se da por muerta
SYNC_SECONDS = 420  # trabajo con Garmin por ejecución; el resto queda para recalcular, IA y subir
MAX_PARTS = 15   # tandas como mucho en la primera descarga
ALERTS_TOPIC = os.environ.get("ALERTS_TOPIC")
GH_ID_PARAM = os.environ.get("GOOGLE_HEALTH_CLIENT_ID_PARAM", "/garmin-stats/google-health-client-id")
GH_SECRET_PARAM = os.environ.get("GOOGLE_HEALTH_CLIENT_SECRET_PARAM", "/garmin-stats/google-health-client-secret")
ALERT_EVERY = 6 * 3600  # el mismo fallo de la misma persona se avisa como mucho cada 6 h
log = logging.getLogger("garmin_stats")
STARTED: dict[str, tuple[int, str | None]] = {}  # uid → (inicio de esta ejecución, fuente con la que empezó)
EMPTY: set[str] = set()  # personas de Google Health sin ningún dato todavía (en esta ejecución)
PULLED: dict[str, str] = {}  # huella de cada archivo de estado al bajarlo: solo se sube lo que esta ejecución cambia


class KeyRejected(Exception):
    """Garmin no acepta la clave de esta persona (caducada o revocada)."""


class SourceChanged(Exception):
    """Mientras corría, la persona cambió de fuente, desconectó o borró sus datos: no se sube nada."""


# ------------------------------------------------------------------ S3
def _get_json(key: str, default):
    try:
        return json.loads(s3.get_object(Bucket=BUCKET, Key=key)["Body"].read())
    except s3.exceptions.NoSuchKey:
        return default


def _put_json(key: str, obj) -> None:
    s3.put_object(Bucket=BUCKET, Key=key, Body=json.dumps(obj, ensure_ascii=False).encode(), ContentType="application/json")


def _status_key(uid: str) -> str:
    return users.state_prefix(uid) + "sync_status.json"


def _secret(name: str, path: str) -> None:
    p = Path(path).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(ssm.get_parameter(Name=name, WithDecryption=True)["Parameter"]["Value"])
    p.chmod(0o600)


def _reset() -> None:
    shutil.rmtree(ROOT, ignore_errors=True)
    shutil.rmtree(HOME / ".config" / "garmin", ignore_errors=True)
    (ROOT / "data" / "fit").mkdir(parents=True, exist_ok=True)
    (ROOT / "site" / "acts").mkdir(parents=True, exist_ok=True)


def _digest(p: Path) -> str | None:
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None


def _pull(uid: str) -> None:
    sp = users.state_prefix(uid)
    PULLED.clear()
    for name in STATE:
        try:
            s3.download_file(BUCKET, sp + name, str(ROOT / "data" / name))
        except s3.exceptions.ClientError:
            pass
        PULLED[name] = _digest(ROOT / "data" / name)
    try:
        s3.download_file(BUCKET, "site/index.html", str(ROOT / "site" / "index.html"))  # para el id de versión
    except s3.exceptions.ClientError:
        pass
    db_path = ROOT / "data" / "garmin.sqlite"
    if db_path.exists():
        # FIT de sesiones de fuerza cuyas series aún no se han leído
        db = sqlite3.connect(db_path)
        try:
            pending = [k for (k,) in db.execute(
                "SELECT key FROM raw WHERE dataset='activity' AND json_extract(payload,'$.activityType.typeKey')='strength_training' "
                "AND key NOT IN (SELECT key FROM raw WHERE dataset='strength_sets')")]
        except sqlite3.Error:
            pending = []
        finally:
            db.close()
        for k in pending:
            try:
                s3.download_file(BUCKET, f"{sp}fit/{k}.fit", str(ROOT / "data" / "fit" / f"{k}.fit"))
            except s3.exceptions.ClientError:
                pass
    ids = []
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=BUCKET, Prefix=users.site_prefix(uid) + "acts/"):
        ids += [Path(o["Key"]).stem for o in page.get("Contents", [])]
    (ROOT / "site" / "acts" / "_published.txt").write_text("\n".join(ids))


def _source_changed(uid: str) -> bool:
    """¿Ha cambiado de fuente (o desconectado, o borrado sus datos, o su cuenta) desde que empezó esta ejecución?"""
    if uid not in STARTED:
        return False
    started, source = STARTED[uid]
    u = users.find(users.load(s3, BUCKET), uid=uid)
    return u is None or users.source(u) != source or (u.get("sourceChangedAt") or 0) > started


def _push(uid: str) -> None:
    if _source_changed(uid):  # la API acaba de borrar o cambiar sus datos: subir esto los resucitaría
        raise SourceChanged()
    sp, site = users.state_prefix(uid), users.site_prefix(uid)
    for name in STATE:
        p = ROOT / "data" / name
        # Sin cambios aquí, no se sube: así no se pisa lo que la API haya guardado mientras tanto (p. ej. un
        # reajuste del plan o su estado "en marcha" en coach.json).
        if p.exists() and name not in READ_ONLY and (dg := _digest(p)) != PULLED.get(name):
            s3.upload_file(str(p), BUCKET, sp + name)
            PULLED[name] = dg  # un segundo _push en la misma ejecución no lo vuelve a subir
    js = {"ContentType": "text/javascript; charset=utf-8", "CacheControl": "no-store"}
    if (ROOT / "site" / "data.js").exists():
        s3.upload_file(str(ROOT / "site" / "data.js"), BUCKET, site + "data.js", ExtraArgs=js)
    existing = {Path(o["Key"]).name for p in s3.get_paginator("list_objects_v2").paginate(Bucket=BUCKET, Prefix=sp + "fit/")
                for o in p.get("Contents", [])}
    for f in (ROOT / "data" / "fit").glob("*.fit"):
        if f.name not in existing:
            s3.upload_file(str(f), BUCKET, f"{sp}fit/{f.name}")
    for f in (ROOT / "site" / "acts").glob("*.js"):
        s3.upload_file(str(f), BUCKET, f"{site}acts/{f.name}", ExtraArgs=js)


# ------------------------------------------------------------------ avisos
def _alert(uid: str, kind: str, detail: str) -> None:
    """Email inmediato a la dueña con qué ha fallado y a quién. Nunca tumba la sincronización."""
    if not ALERTS_TOPIC:
        return
    try:
        sig = hashlib.sha256(f"{kind}|{detail[:160]}".encode()).hexdigest()[:12]
        key = users.state_prefix(uid) + "alerts_sent.json"
        sent = _get_json(key, {})
        now = time.time()
        if now - sent.get(sig, 0) < ALERT_EVERY:
            return
        u = users.find(users.load(s3, BUCKET), uid=uid) or {}
        who = u.get("email") or uid
        boto3.client("sns").publish(
            TopicArn=ALERTS_TOPIC, Subject=f"Runch: {kind} ({who})"[:99],
            Message=(f"Persona: {who} (uid {uid})\nQué: {kind}\n\n{detail[-3000:]}\n\n"
                     "Lo descargado ya está guardado; la sincronización lo reintenta sola cada hora. "
                     "Logs: CloudWatch /aws/lambda/garmin-stats-sync"))
        sent = {k: v for k, v in sent.items() if now - v < 7 * 86400}
        sent[sig] = now
        _put_json(key, sent)
    except Exception:  # noqa: BLE001
        log.exception("No se pudo enviar el aviso")


# ------------------------------------------------------------------ entrada
def handler(event, ctx):
    event = event or {}
    logging.getLogger().setLevel(logging.INFO)
    if not event.get("uid"):
        return _dispatch()
    return _sync_user(event, ctx)


def _dispatch() -> dict:
    """Ejecución programada: una sincronización por persona con Garmin conectado."""
    n = 0
    for u in users.load(s3, BUCKET):
        # google_not_linked: se reintenta cada hora por si ya ha enlazado Google Health en la app del móvil
        if u.get("status") in ("active", "google_not_linked"):
            lam.invoke(FunctionName=FUNCTION, InvocationType="Event", Payload=json.dumps({"uid": u["uid"]}).encode())
            n += 1
    log.info("Sincronización programada: %d personas", n)
    return {"ok": True, "users": n}


def _sync_user(event: dict, ctx) -> dict:
    uid = event["uid"]
    user = users.find(users.load(s3, BUCKET), uid=uid)
    if not user or user.get("status") not in ("active", "google_not_linked"):
        return {"ok": False, "skipped": "sin Garmin ni Google Health conectado"}
    token = event.get("token")
    st = _get_json(_status_key(uid), {})
    if st.get("status") == "running" and time.time() - st.get("at", 0) < STALE and st.get("token") != token:
        log.warning("Ya hay otra sincronización en marcha para esta persona; esta se salta.")
        return {"ok": True, "skipped": True}
    part = int(event.get("part") or 1)
    started = int(time.time())
    token = token or f"auto-{started}"
    manual = bool(event.get("manual") or (token and not token.startswith("auto-")))
    first = not st.get("finished") and part == 1
    backfill = bool(event.get("continue")) or first
    _put_json(_status_key(uid), {"status": "running", "at": started, "token": token, "manual": manual,
                                 "backfill": backfill, "part": part})
    STARTED[uid] = (started, users.source(user))
    try:
        partial = _run(user, ctx)
        if _source_changed(uid):
            raise SourceChanged()
    except (SourceChanged, GH.NotLinked, GH.Reauth) as e:
        if isinstance(e, SourceChanged) or _source_changed(uid):
            # tras desconectar o cambiar de fuente, el permiso ya no está: ni error ni "vuelve a conectar"
            if _get_json(_status_key(uid), {}).get("token") == token:  # sin rastro de "en marcha"
                _put_json(_status_key(uid), {"status": "cancelled", "at": started, "finished": int(time.time())})
            log.warning("La fuente de %s ha cambiado durante la sincronización: no se sube nada", uid)
            return {"ok": False, "sourceChanged": True}
        if isinstance(e, GH.NotLinked):  # su cuenta de Google aún no tiene Google Health: se reintenta cada hora
            _put_json(_status_key(uid), {"status": "google_not_linked", "at": started, "finished": int(time.time())})
            users.update(s3, BUCKET, uid, status="google_not_linked", googleLinkUrl=e.link_url)
            log.warning("Google Health sin enlazar para %s", uid)
            return {"ok": False, "google_not_linked": True}
        # retiró el permiso o caducó: tiene que volver a conectar
        _put_json(_status_key(uid), {"status": "google_reauth", "at": started, "finished": int(time.time())})
        users.update(s3, BUCKET, uid, status="google_reauth")
        log.warning("Google Health ya no acepta el permiso de %s", uid)
        return {"ok": False, "google_reauth": True}
    except KeyRejected:
        _put_json(_status_key(uid), {"status": "key_invalid", "at": started, "finished": int(time.time())})
        users.update(s3, BUCKET, uid, status="key_invalid")
        log.warning("Garmin rechaza la clave de %s", uid)
        return {"ok": False, "key_invalid": True}  # no es un fallo del sistema: no salta la alarma
    except Exception as e:
        _put_json(_status_key(uid), {"status": "error", "at": started, "finished": int(time.time()), "error": str(e)[:200]})
        import traceback
        _alert(uid, "la sincronización ha fallado", traceback.format_exc())
        raise  # la alarma "sync falla" sigue saltando
    try:
        from garmin_stats import export as X
        if X.SECTION_ERRORS:
            _alert(uid, "una parte de la web no se ha podido calcular", "\n".join(X.SECTION_ERRORS))
    except Exception:  # noqa: BLE001
        log.exception("Revisión de secciones")
    if partial and part < MAX_PARTS:
        # Queda historial: se publica lo que hay y sigue otra ejecución (mismo candado)
        _put_json(_status_key(uid), {"status": "running", "at": int(time.time()), "token": token, "manual": manual,
                                     "backfill": True, "part": part + 1})
        lam.invoke(FunctionName=FUNCTION, InvocationType="Event",
                   Payload=json.dumps({"uid": uid, "token": token, "continue": True, "part": part + 1}).encode())
        return {"ok": True, "partial": True, "part": part}
    _put_json(_status_key(uid), {"status": "done", "at": started, "finished": int(time.time()), "manual": manual,
                                 **({"backfillDone": True} if backfill else {}),
                                 **({"empty": True} if uid in EMPTY else {})})
    if user.get("status") == "google_not_linked":  # ya lo ha enlazado
        users.update(s3, BUCKET, uid, status="active", googleLinkUrl=None)
    _maybe_create_plan(uid)
    return {"ok": True}


def _run(user: dict, ctx) -> bool:
    """Sincroniza a una persona. Devuelve True si se cortó por tiempo y queda historial por bajar."""
    uid = user["uid"]
    google = users.source(user) == "google"
    EMPTY.discard(uid)
    _reset()
    client = None
    if google:
        client = _google_client(uid)
    else:
        try:
            _secret(users.key_param(uid), "~/.config/garmin/connect-personal-api-key")
        except ssm.exceptions.ParameterNotFound:
            raise KeyRejected() from None
    _secret("/garmin-stats/anthropic-key", "~/.config/anthropic/garmin-stats-key")
    owner = user.get("role") == "owner"
    os.environ["GARMIN_STATS_UID"] = uid
    os.environ["GARMIN_STATS_AI_BUDGET"] = str(user.get("budgetUsd") or 5)
    os.environ["GARMIN_STATS_ADAPT_MODEL"] = "" if owner else "claude-sonnet-5-5"
    os.environ["GARMIN_STATS_OWNER"] = "1" if owner else "0"
    left = ctx.get_remaining_time_in_millis() / 1000 if ctx else 900
    os.environ["GARMIN_STATS_DEADLINE"] = str(time.time() + max(60, min(SYNC_SECONDS, left - 420)))
    _pull(uid)

    if not google:
        from garmin_personal_api.errors import HttpError
        from garmin_stats.api import Api
        try:
            Api()  # cambia la clave por un token: si Garmin la rechaza, no hay nada que hacer hasta que ponga otra
        except HttpError as e:
            if e.status_code in (400, 401, 403):
                raise KeyRejected() from e
            raise

    from garmin_stats import export, sync
    from garmin_stats.cli import main
    export.SECTION_ERRORS.clear()
    partial = False
    try:
        if google:
            partial = GH.sync(client)
        else:
            main(["sync"])
            partial = bool(sync.LAST_PARTIAL)
        # Lo descargado se guarda YA: si el cálculo de la web falla o se queda sin tiempo/memoria,
        # la siguiente ejecución sigue desde aquí en vez de repetir la descarga.
        _push(uid)
        if not _has_data():
            # Aún no hay nada suyo (reloj recién enlazado o cuenta vacía): sin datos no hay informe que hacer
            EMPTY.add(uid)
            log.info("Sin datos todavía para %s", uid)
        else:
            main(["report"])
    finally:
        # Aunque el informe falle, lo descargado de Garmin se guarda: el reintento sigue donde se quedó
        # en vez de volver a bajar todo el historial desde cero.
        try:
            _push(uid)
        except Exception:  # noqa: BLE001
            log.exception("No se pudo guardar el estado tras el fallo")
    return partial


def _has_data() -> bool:
    """¿Hay algo descargado (entrenos o días)? Sin nada, el informe no se puede calcular."""
    db = sqlite3.connect(ROOT / "data" / "garmin.sqlite")
    try:
        return db.execute("SELECT 1 FROM raw WHERE dataset IN ('activity', 'daily_summary') LIMIT 1").fetchone() is not None
    except sqlite3.Error:
        return False
    finally:
        db.close()


def _google_client(uid: str) -> GH.Client:
    """Cliente de Google Health con el permiso guardado de esta persona."""
    try:
        tok = json.loads(ssm.get_parameter(Name=users.google_param(uid), WithDecryption=True)["Parameter"]["Value"])
    except ssm.exceptions.ParameterNotFound:
        raise GH.Reauth(401, "sin permiso guardado") from None
    cid = ssm.get_parameter(Name=GH_ID_PARAM)["Parameter"]["Value"].strip()
    sec = ssm.get_parameter(Name=GH_SECRET_PARAM, WithDecryption=True)["Parameter"]["Value"].strip()
    return GH.Client(cid, sec, tok["refresh_token"])


def _maybe_create_plan(uid: str) -> None:
    """Tras la primera descarga completa: si dejó un objetivo en el onboarding y aún no tiene plan, se crea."""
    onb_key = users.state_prefix(uid) + "onboarding.json"
    onb = _get_json(onb_key, {})
    if not onb.get("goal") or onb.get("planRequested"):
        return
    coach = _get_json(users.state_prefix(uid) + "coach.json", {})
    if coach.get("plan") or (coach.get("job") or {}).get("status") == "running":
        return
    onb["planRequested"] = int(time.time())
    _put_json(onb_key, onb)
    lam.invoke(FunctionName=API_FUNCTION, InvocationType="Event",
               Payload=json.dumps({"job": "create", "uid": uid, "body": onb["goal"], "mark": True}).encode())
    log.info("Plan pedido para %s", uid)
