"""Refresco semanal del catálogo de la lista de la compra (Lambda garmin-stats-catalog, lunes a las 05:00 de Madrid).

Pide a la tienda online de Mercadona (con su permiso del 03-11-2026) solo los listados de las categorías de comida
(traen el precio; unas 120-190 peticiones con al menos 0,75 s entre una y otra) y la ficha de los productos nuevos.
Si responde 403/429 o algo que no es JSON, para sin reintentar ni esquivar nada y se queda el último catálogo bueno;
la ejecución termina en error para que llegue el aviso por email (alarma garmin-stats-catalogo-falla).
Evento opcional: {"probe": true} (solo comprueba que se llega: 1-3 peticiones, no escribe nada) o {"postcode": "…"}.
"""

import json
import os
import time

os.environ["TZ"] = "CET-1CEST,M3.5.0,M10.5.0/3"
time.tzset()

import boto3  # noqa: E402

from garmin_stats import catalog as C  # noqa: E402

BUCKET = os.environ["BUCKET"]
s3 = boto3.client("s3")


def _status(obj: dict) -> None:
    s3.put_object(Bucket=BUCKET, Key=C.STATUS, Body=json.dumps(obj, ensure_ascii=False).encode(), ContentType="application/json")


def handler(event, ctx):
    event = event or {}
    postcode = str(event.get("postcode") or os.environ.get("CATALOG_POSTCODE") or "") or None  # None: el del catálogo anterior
    probe = bool(event.get("probe"))
    prev = C.load_s3(s3, BUCKET, ttl=0)
    cli = C.Client(gap=float(os.environ.get("CATALOG_GAP") or 0.75))
    left = (ctx.get_remaining_time_in_millis() / 1000) if ctx else 900
    now = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    try:
        cat = C.refresh(prev, cli, postcode, probe=probe, deadline_s=max(60.0, min(780.0, left - 90)))
    except Exception as e:  # noqa: BLE001 - 403/429, sin tiempo o catálogo raro: se mantiene el anterior
        msg = f"{type(e).__name__}: {str(e)[:300]}"
        print(f"catálogo: NO actualizado ({msg}); peticiones={cli.requests}")
        if not probe:
            _status({"ok": False, "at": now, "error": msg, "requests": cli.requests,
                     "kept": ((prev or {}).get("meta") or {}).get("date")})
        raise RuntimeError(f"Catálogo no actualizado: {msg}") from None
    if probe:
        sample = [{k: p.get(k) for k in ("name", "fmt", "price", "perKgL")} for p in cat["products"][:3]]
        print(f"catálogo: prueba correcta, {len(cat['products'])} productos en la primera categoría")
        return {"ok": True, "probe": True, "requests": cli.requests, "meta": cat["meta"], "sample": sample}
    key = C.put_s3(s3, BUCKET, cat)
    status = {"ok": True, "at": now, "key": key, "count": cat["meta"]["count"], "requests": cli.requests,
              "stats": cat["meta"].get("stats"), "seconds": cat["meta"].get("seconds")}
    _status(status)
    print(f"catálogo: actualizado {key} ({status['count']} productos, {cli.requests} peticiones)")
    return status
