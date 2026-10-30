"""Aviso de la mañana (Web Push al móvil): preparación de hoy y sesión del plan.

Lo lanza EventBridge Scheduler cada día. Lee data.js y coach.json de S3 y envía una notificación a cada
suscripción guardada en state/push.json. Las suscripciones caducadas (404/410) se borran.
"""

import json
import os
from datetime import date

import boto3
from pywebpush import WebPushException, webpush

BUCKET = os.environ["BUCKET"]
s3 = boto3.client("s3")
ssm = boto3.client("ssm")


def _get_json(key, default):
    try:
        return json.loads(s3.get_object(Bucket=BUCKET, Key=key)["Body"].read())
    except s3.exceptions.NoSuchKey:
        return default


def message() -> dict:
    raw = s3.get_object(Bucket=BUCKET, Key="site/data.js")["Body"].read().decode()
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
    subs = _get_json("state/push.json", [])
    if not subs:
        return {"sent": 0}
    private_key = ssm.get_parameter(Name="/garmin-stats/vapid-private", WithDecryption=True)["Parameter"]["Value"]
    payload = json.dumps((event or {}).get("message") or message(), ensure_ascii=False)
    keep, sent = [], 0
    for sub in subs:
        try:
            webpush(subscription_info=sub, data=payload, vapid_private_key=private_key,
                    vapid_claims={"sub": "mailto:tu@gmail.com"}, ttl=6 * 3600)
            keep.append(sub)
            sent += 1
        except WebPushException as e:
            code = getattr(e.response, "status_code", None)
            if code not in (404, 410):  # 404/410 = suscripción caducada: se descarta
                keep.append(sub)
                print("push error", code, str(e)[:200])
    if len(keep) != len(subs):
        s3.put_object(Bucket=BUCKET, Key="state/push.json", Body=json.dumps(keep).encode())
    return {"sent": sent}
