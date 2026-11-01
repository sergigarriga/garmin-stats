"""Personas con acceso a la web (versión multipersona en AWS).

El registro vive en S3 (admin/users.json, fuera de site/, así que nunca se sirve):
  {"users": [{"email", "uid", "name", "role": "owner" | "friend", "budgetUsd", "status", "invitedAt", "joinedAt"}]}
status: invited (invitada, aún no ha entrado) · onboarding (ha entrado, falta Garmin) · active (con Garmin)
        · key_invalid (Garmin rechaza su clave).
Cada persona tiene su carpeta privada users/<uid>/state/ y su web site/u/<uid>/ (CloudFront solo le sirve la suya).
El uid sale del email con HMAC (no se puede adivinar sin el secreto de sesión).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time

KEY = "admin/users.json"


def uid_for(email: str, secret: bytes) -> str:
    return hmac.new(secret, b"uid:" + email.strip().lower().encode(), hashlib.sha256).hexdigest()[:16]


def state_prefix(uid: str) -> str:
    return f"users/{uid}/state/"


def site_prefix(uid: str) -> str:
    return f"site/u/{uid}/"


def key_param(uid: str) -> str:
    return f"/garmin-stats/users/{uid}/garmin-key"


def load(s3, bucket: str) -> list[dict]:
    try:
        return json.loads(s3.get_object(Bucket=bucket, Key=KEY)["Body"].read())["users"]
    except s3.exceptions.NoSuchKey:
        return []


def save(s3, bucket: str, users: list[dict]) -> None:
    s3.put_object(Bucket=bucket, Key=KEY, Body=json.dumps({"users": users}, ensure_ascii=False, indent=1).encode(),
                  ContentType="application/json")


def find(users: list[dict], email: str | None = None, uid: str | None = None) -> dict | None:
    for u in users:
        if (email and u["email"] == email.strip().lower()) or (uid and u["uid"] == uid):
            return u
    return None


def update(s3, bucket: str, uid: str, **fields) -> dict | None:
    users = load(s3, bucket)
    u = find(users, uid=uid)
    if u:
        u.update(fields)
        save(s3, bucket, users)
    return u


def now() -> int:
    return int(time.time())
