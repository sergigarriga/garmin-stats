"""Aviso de la mañana (Web Push al móvil): preparación de hoy y sesión del plan.

Lo lanza EventBridge Scheduler cada día. Para cada persona lee su data.js (site/u/<uid>/) y envía una
notificación a cada suscripción guardada en users/<uid>/state/push.json. Las caducadas (404/410) se borran.
Con {"uid", "message"} (botón "probar aviso") solo avisa a esa persona.
"""

import json
import os
import time
from datetime import date

os.environ["TZ"] = "CET-1CEST,M3.5.0,M10.5.0/3"  # hora de Madrid sin tzdata
time.tzset()

import boto3
from pywebpush import WebPushException, webpush

from garmin_stats import users

BUCKET = os.environ["BUCKET"]
OWNER = os.environ["OWNER_EMAIL"]
s3 = boto3.client("s3")
ssm = boto3.client("ssm")


def _get_json(key, default):
    try:
        return json.loads(s3.get_object(Bucket=BUCKET, Key=key)["Body"].read())
    except s3.exceptions.NoSuchKey:
        return default


def message(uid: str) -> dict:
    raw = s3.get_object(Bucket=BUCKET, Key=users.site_prefix(uid) + "data.js")["Body"].read().decode()
    data = json.loads(raw[raw.index("=") + 1:].rstrip().rstrip(";"))
    r = data.get("readiness") or {}
    coach = data.get("coach") or {}
    today = (coach.get("today") or {})
    s = today.get("session") or {}
    title = f"Preparación {r['score']} · {r['label']}" if r.get("date") == date.today().isoformat() and r.get("score") is not None \
        else "Buenos días"
    parts = []
    if s:
        km = f" · {s['distance_km']:g} km" if s.get("distance_km") else ""
        parts.append(f"Hoy: {s['title']}{km}")
    if today.get("tip"):
        parts.append(today["tip"])
    elif r.get("message"):
        parts.append(r["message"])
    return {"title": title, "body": " — ".join(parts) or "Mira cómo vas hoy.", "url": "/#hoy", "tag": "morning"}


def handler(event, _ctx):
    event = event or {}
    private_key = ssm.get_parameter(Name="/garmin-stats/vapid-private", WithDecryption=True)["Parameter"]["Value"]
    people = [u for u in users.load(s3, BUCKET) if u.get("status") == "active"]
    if event.get("uid"):
        people = [u for u in people if u["uid"] == event["uid"]]
    sent = 0
    for u in people:
        try:
            sent += _notify(u["uid"], event.get("message"), private_key)
        except Exception as e:  # noqa: BLE001 - que una persona no deje sin aviso a las demás
            print("notify error", u["uid"], str(e)[:200])
    return {"sent": sent}


def _notify(uid: str, msg: dict | None, private_key: str) -> int:
    key = users.state_prefix(uid) + "push.json"
    subs = _get_json(key, [])
    if not subs:
        return 0
    payload = json.dumps(msg or message(uid), ensure_ascii=False)
    keep, sent = [], 0
    for sub in subs:
        try:
            webpush(subscription_info=sub, data=payload, vapid_private_key=private_key,
                    vapid_claims={"sub": f"mailto:{OWNER}"}, ttl=6 * 3600)
            keep.append(sub)
            sent += 1
        except WebPushException as e:
            code = getattr(e.response, "status_code", None)
            if code not in (404, 410):  # 404/410 = suscripción caducada: se descarta
                keep.append(sub)
                print("push error", code, str(e)[:200])
    if len(keep) != len(subs):
        s3.put_object(Bucket=BUCKET, Key=key, Body=json.dumps(keep).encode())
    return sent
