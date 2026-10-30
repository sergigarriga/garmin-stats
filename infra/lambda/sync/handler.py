"""Sincronización horaria en AWS (EventBridge Scheduler → esta Lambda).

Hace lo mismo que `garmin-stats all` en el PC: descarga lo nuevo de Garmin, recalcula, escribe los textos
de IA (y el lunes reajusta el plan) y publica la web. El estado vive en S3:
  state/garmin.sqlite   base de datos completa (se baja y se sube en cada ejecución)
  state/*.json, *.log   plan, memoria del coach, ajustes, caché y gasto de IA
  site/                 web publicada (data.js y los detalles de actividad en site/acts/)
Los FIT solo se bajan de Garmin para actividades nuevas; los ya leídos están en la base de datos.
"""

import logging
import os
from pathlib import Path

import boto3

ROOT = Path("/tmp/gs")
os.environ["GARMIN_STATS_ROOT"] = str(ROOT)
os.environ["HOME"] = "/tmp/home"

BUCKET = os.environ["BUCKET"]
s3 = boto3.client("s3")
ssm = boto3.client("ssm")
STATE = ["garmin.sqlite", "coach.json", "settings.json", "ai_cache.json", "ai_usage.log", "ai_usage_lambda.log"]
log = logging.getLogger("garmin_stats")


def _secret(name: str, path: str) -> None:
    p = Path(path).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(ssm.get_parameter(Name=name, WithDecryption=True)["Parameter"]["Value"])
    p.chmod(0o600)


def _pull() -> None:
    (ROOT / "data").mkdir(parents=True, exist_ok=True)
    (ROOT / "site" / "acts").mkdir(parents=True, exist_ok=True)
    for name in STATE:
        try:
            s3.download_file(BUCKET, f"state/{name}", str(ROOT / "data" / name))
        except s3.exceptions.ClientError:
            pass
    try:
        s3.download_file(BUCKET, "site/index.html", str(ROOT / "site" / "index.html"))  # para el id de versión
    except s3.exceptions.ClientError:
        pass
    # FIT de sesiones de fuerza cuyas series aún no se han leído (solo la primera vez)
    import sqlite3
    db = sqlite3.connect(ROOT / "data" / "garmin.sqlite")
    try:
        pending = [k for (k,) in db.execute(
            "SELECT key FROM raw WHERE dataset='activity' AND json_extract(payload,'$.activityType.typeKey')='strength_training' "
            "AND key NOT IN (SELECT key FROM raw WHERE dataset='strength_sets')")]
    finally:
        db.close()
    (ROOT / "data" / "fit").mkdir(parents=True, exist_ok=True)
    for k in pending:
        try:
            s3.download_file(BUCKET, f"state/fit/{k}.fit", str(ROOT / "data" / "fit" / f"{k}.fit"))
        except s3.exceptions.ClientError:
            pass
    ids = []
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=BUCKET, Prefix="site/acts/"):
        ids += [Path(o["Key"]).stem for o in page.get("Contents", [])]
    (ROOT / "site" / "acts" / "_published.txt").write_text("\n".join(ids))


def _push() -> None:
    for name in STATE:
        p = ROOT / "data" / name
        if p.exists() and name != "ai_usage_lambda.log":  # ese lo escribe la Lambda de la API
            s3.upload_file(str(p), BUCKET, f"state/{name}")
    s3.upload_file(str(ROOT / "site" / "data.js"), BUCKET, "site/data.js",
                   ExtraArgs={"ContentType": "text/javascript; charset=utf-8", "CacheControl": "no-store"})
    # FIT nuevos descargados de Garmin: se guardan en S3 (originales, para poder reprocesar)
    existing = {Path(o["Key"]).name for p in s3.get_paginator("list_objects_v2").paginate(Bucket=BUCKET, Prefix="state/fit/")
                for o in p.get("Contents", [])}
    for f in (ROOT / "data" / "fit").glob("*.fit"):
        if f.name not in existing:
            s3.upload_file(str(f), BUCKET, f"state/fit/{f.name}")
    for f in (ROOT / "site" / "acts").glob("*.js"):
        s3.upload_file(str(f), BUCKET, f"site/acts/{f.name}",
                       ExtraArgs={"ContentType": "text/javascript; charset=utf-8", "CacheControl": "no-store"})


def handler(event, _ctx):
    _secret("/garmin-stats/garmin-key", "~/.config/garmin/connect-personal-api-key")
    _secret("/garmin-stats/anthropic-key", "~/.config/anthropic/garmin-stats-key")
    _pull()
    logging.getLogger().setLevel(logging.INFO)
    from garmin_stats.cli import main
    main(["all"])
    _push()
    return {"ok": True}
