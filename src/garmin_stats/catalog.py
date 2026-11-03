"""Catálogo de productos del supermercado para la lista de la compra semanal (Python puro: lo usa la Lambda de la API).

Datos: Mercadona dio permiso por escrito (03-11-2026) para usar los datos básicos de su catálogo (nombre, formato,
precio, precio por kg/l y nutrición) SOLO para la lista de la compra de Runch, con una actualización semanal y pocas
peticiones, citando a Mercadona y enlazando cada ficha; sin revender ni comparar con otras cadenas. Si lo piden, se
retira. Por eso:
  - En este repositorio (público) solo hay código. Los datos viven en el bucket privado:
      admin/catalog/mercadona-latest.json      el catálogo que lee la API
      admin/catalog/mercadona-<fecha>.json     copia de cada semana
      admin/catalog/refresh-status.json        resultado del último refresco
  - El refresco semanal (refresh) pide solo los listados de categorías (traen el precio) y la ficha de los productos
    NUEVOS. Se para al primer 403/429 o respuesta que no sea JSON (sin intentar esquivarlo) y entonces se queda el
    último catálogo bueno.
  - Nutrición: la que ya tenía cada producto (Open Food Facts, ODbL; USDA FoodData Central, dominio público) y, para
    los nuevos, Open Food Facts por EAN.

Formato compacto de cada producto:
  {"id", "name", "cat" (ruta de categorías), "brand", "fmt" ("0.5 kg", "6 x 1 l", "12 ud", "a peso (desde 0.2 kg)"),
   "pack" (envase), "price" (€, null si es a peso), "unitPrice", "unitPriceUnit", "perKgL" (€/kg o €/l), "approx",
   "url", "ean", "nut": {"kcal","protein","carbs","sugars","fat","satFat","fiber","salt"} | null, "nutSrc", "nutFlag"}
"""

from __future__ import annotations

import json
import logging
import os
import random
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

log = logging.getLogger(__name__)

PREFIX = "admin/catalog/"
LATEST = PREFIX + "mercadona-latest.json"
STATUS = PREFIX + "refresh-status.json"
SHOP = "https://tienda.mercadona.es"
OFF_PRODUCT = "https://world.openfoodfacts.org/api/v2/product"
UA = "RunchApp/1.0 (lista de la compra semanal; uso autorizado por Mercadona el 03-11-2026; 1 vez por semana, pocas peticiones)"
# El código postal de la tienda (precios por almacén) es un dato privado: CATALOG_POSTCODE en deploy.env, nunca aquí
ATTRIBUTION = "Productos y precios: Mercadona (tienda.mercadona.es), con su permiso"
NUTRITION_ATTRIBUTION = "Nutrición: Open Food Facts (ODbL) y USDA FoodData Central"
# Solo pasillos de comida: el resto (droguería, mascotas, bebé, bodega...) no hace falta para un menú
FOOD_TOP = (
    "Aceite, especias y salsas", "Agua y refrescos", "Aperitivos", "Arroz, legumbres y pasta", "Azúcar, caramelos y chocolate",
    "Cacao, café e infusiones", "Carne", "Cereales y galletas", "Charcutería y quesos", "Congelados",
    "Conservas, caldos y cremas", "Fruta y verdura", "Huevos, leche y mantequilla", "Marisco y pescado",
    "Panadería y pastelería", "Pizzas y platos preparados", "Postres y yogures", "Zumos",
)
NUT_KEYS = {"kcal": "kcal_100g", "protein": "protein_100g", "carbs": "carbs_100g", "sugars": "sugars_100g",
            "fat": "fat_100g", "satFat": "sat_fat_100g", "fiber": "fiber_100g", "salt": "salt_100g"}
MIN_KEEP = 0.7      # un catálogo nuevo con menos del 70 % de productos que el anterior no se publica
CACHE_TTL = 600     # la API relee el catálogo de S3 como mucho cada 10 min


class Stop(Exception):
    """403, 429 o una respuesta que no es JSON: se para (no se intenta esquivar)."""


# ======================================================================== utilidades
def norm(s: str | None) -> str:
    s = unicodedata.normalize("NFKD", str(s or "").lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def stem(w: str) -> str:
    """Singular aproximado para comparar palabras: tomates/tomate → tomat, limones/limón → limon, huevos → huevo."""
    if len(w) > 3 and w.endswith("s"):
        w = w[:-1]
    if len(w) > 4 and w.endswith("e"):
        w = w[:-1]
    return w


def tokens(s: str | None) -> list[str]:
    return [stem(t) for t in re.split(r"[^a-z0-9ñ]+", norm(s)) if t]


def _num(v) -> float | None:
    try:
        f = float(str(v).replace(",", "."))
        return None if f != f else f
    except (TypeError, ValueError):
        return None


def parse_format(fmt: str | None) -> dict | None:
    """'0.5 kg' → {"kind": "g", "size": 500}; '6 x 1 l' → {"kind": "ml", "size": 6000, "units": 6};
    '12 ud' → {"kind": "ud", "size": 12}; 'a peso (desde 0.2 kg)' → {"kind": "weight", "min": 200}."""
    s = norm(fmt).strip()
    if not s:
        return None
    m = re.match(r"a peso(?: \(desde ([\d.]+) (kg|l)\))?", s)
    if m:
        return {"kind": "weight", "min": round((_num(m.group(1)) or 0) * 1000) or None}
    m = re.match(r"^(?:(\d+) x )?([\d.]+) (kg|l|ud|g|ml)$", s)
    if not m:
        return None
    n, each, unit = int(m.group(1) or 1), _num(m.group(2)) or 0, m.group(3)
    if each <= 0:
        return None
    if unit in ("kg", "l"):
        kind, size = ("g" if unit == "kg" else "ml"), each * 1000 * n
    elif unit in ("g", "ml"):
        kind, size = unit, each * n
    else:
        kind, size = "ud", each * n
    out = {"kind": kind, "size": round(size, 1)}
    if n > 1:
        out["units"] = n
    return out


def top(cat: str | None) -> str:
    return (cat or "").split(" > ")[0]


# ======================================================================== formato compacto
def _nut_from_row(r: dict) -> dict | None:
    nut = {k: _num(r.get(col)) for k, col in NUT_KEYS.items()}
    return nut if nut.get("kcal") is not None else None


def compact_row(r: dict) -> dict:
    """Una fila del catálogo completo (research/…/catalog-*.json o el refresco) en el formato compacto."""
    return {"id": str(r["id"]), "name": r.get("name") or "", "cat": r.get("category_path") or r.get("cat") or "",
            "brand": r.get("brand"), "fmt": r.get("format") or r.get("fmt"), "pack": r.get("packaging") or r.get("pack"),
            "price": _num(r.get("price_eur", r.get("price"))), "unitPrice": _num(r.get("unit_price_eur", r.get("unitPrice"))),
            "unitPriceUnit": r.get("unit_price_unit") or r.get("unitPriceUnit"),
            "perKgL": _num(r.get("price_per_kg_l", r.get("perKgL"))), "approx": bool(r.get("approx")),
            "url": r.get("url"), "ean": r.get("ean"), "nut": r.get("nut") if "nut" in r else _nut_from_row(r),
            "nutSrc": r.get("nutrition_source") or r.get("nutSrc"), "nutFlag": r.get("nutrition_flag") or r.get("nutFlag") or ""}


def compact(products: list[dict], meta: dict) -> dict:
    """Solo comida y solo los campos que hacen falta."""
    rows = [compact_row(r) for r in products if top(r.get("category_path") or r.get("cat")) in FOOD_TOP]
    rows = [r for r in rows if r["price"] is not None or r["perKgL"] is not None]
    return {"meta": {**meta, "count": len(rows)}, "products": rows}


# ======================================================================== lectura desde S3 (API)
_CACHE: dict = {}


def load_s3(s3, bucket: str, key: str = LATEST, ttl: int = CACHE_TTL) -> dict | None:
    """El catálogo vigente (en memoria de la Lambda durante unos minutos). None si aún no hay ninguno."""
    hit = _CACHE.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    try:
        cat = json.loads(s3.get_object(Bucket=bucket, Key=key)["Body"].read())
    except Exception as e:  # noqa: BLE001 - sin catálogo la lista sale sin productos, el menú sigue
        log.warning("Catálogo: no se puede leer %s: %s", key, type(e).__name__)
        return hit[1] if hit else None
    _CACHE[key] = (time.time(), cat)
    return cat


def put_s3(s3, bucket: str, cat: dict) -> str:
    """Publica el catálogo: copia de la semana + el vigente."""
    body = json.dumps(cat, ensure_ascii=False, separators=(",", ":")).encode()
    day = (cat.get("meta") or {}).get("date") or datetime.now().date().isoformat()
    dated = f"{PREFIX}mercadona-{day}.json"
    for key in (dated, LATEST):
        s3.put_object(Bucket=bucket, Key=key, Body=body, ContentType="application/json")
    _CACHE.pop(LATEST, None)
    return dated


# ======================================================================== refresco semanal
class Client:
    """HTTP con pausa mínima entre peticiones, User-Agent descriptivo y parada ante 403/429 (sin evasión)."""

    def __init__(self, gap: float = 0.75, opener=None, sleep=time.sleep, clock=time.monotonic):
        self.gap, self.last, self.requests, self.bytes = gap, -1e9, 0, 0
        self._open = opener or (lambda req, timeout: urllib.request.urlopen(req, timeout=timeout))  # noqa: S310
        self._sleep, self._clock = sleep, clock

    def get(self, url: str, method: str = "GET", body: bytes | None = None, headers: dict | None = None,
            retries: int = 2) -> tuple[bytes, dict]:
        for attempt in range(retries + 1):
            wait = self.gap - (self._clock() - self.last)
            if wait > 0:
                self._sleep(wait)
            self.last = self._clock()
            self.requests += 1
            req = urllib.request.Request(url, data=body, method=method,
                                         headers={"User-Agent": UA, "Accept": "application/json", **(headers or {})})
            try:
                with self._open(req, 40) as r:
                    data = r.read()
                    self.bytes += len(data)
                    return data, dict(r.headers)
            except urllib.error.HTTPError as e:
                if e.code in (403, 429):
                    raise Stop(f"HTTP {e.code} en {url}: paro (sin reintentar)") from None
                if e.code < 500 or attempt == retries:
                    raise
            except (urllib.error.URLError, TimeoutError):
                if attempt == retries:
                    raise
            self._sleep(min(30, 2 ** (attempt + 2)) + random.random())
        raise RuntimeError("inalcanzable")

    def json(self, url: str, **kw):
        data, _ = self.get(url, **kw)
        if data.lstrip()[:1] not in (b"{", b"["):
            raise Stop(f"Respuesta que no es JSON en {url} (¿muro anti-bots?): paro")
        return json.loads(data)


def normalise_price(pi: dict) -> dict:
    """price_instructions → precio, precio por unidad de referencia y €/kg-l. unit_size es el tamaño TOTAL
    (6 l en un pack de 6 x 1 l); pack_size, el de cada unidad. Lo que se vende a peso no tiene precio fijo."""
    ref, ref_fmt = _num(pi.get("reference_price")), (pi.get("reference_format") or "").strip()
    size, size_fmt = _num(pi.get("unit_size")), (pi.get("size_format") or "").strip().lower()
    by_weight = pi.get("selling_method") == 1
    price = None if by_weight else _num(pi.get("unit_price"))
    per = None
    if ref is not None and ref_fmt.lower() in ("kg", "l"):
        per = ref
    elif price and size and size_fmt in ("kg", "l"):
        per = round(price / size, 2)
    fmt = None
    if by_weight:
        step = _num(pi.get("min_bunch_amount"))
        fmt = f"a peso (desde {step:g} {size_fmt or 'kg'})" if step else "a peso"
        per = per if per is not None else _num(pi.get("bulk_price"))
    elif size:
        units, each = pi.get("total_units"), _num(pi.get("pack_size"))
        fmt = f"{units} x {each:g} {size_fmt}" if units and each and units > 1 else f"{size:g} {size_fmt}"
    return {"price": price, "unitPrice": ref, "unitPriceUnit": ref_fmt or None, "perKgL": per, "fmt": fmt,
            "approx": bool(pi.get("approx_size"))}


def _nut_from_off(nutriments: dict) -> dict | None:
    n = nutriments or {}
    kcal = _num(n.get("energy-kcal_100g"))
    if kcal is None and _num(n.get("energy_100g")) is not None:
        kcal = round(_num(n.get("energy_100g")) / 4.184)
    if kcal is None or not 0 <= kcal <= 900:
        return None
    return {"kcal": kcal, "protein": _num(n.get("proteins_100g")), "carbs": _num(n.get("carbohydrates_100g")),
            "sugars": _num(n.get("sugars_100g")), "fat": _num(n.get("fat_100g")), "satFat": _num(n.get("saturated-fat_100g")),
            "fiber": _num(n.get("fiber_100g")), "salt": _num(n.get("salt_100g"))}


def nut_flag(nut: dict | None) -> str:
    """'dudoso: …' si los valores no cuadran (la lista no los usa para el resumen de nutrición)."""
    if not nut or nut.get("kcal") is None:
        return ""
    k = nut["kcal"]
    est = 4 * (nut.get("protein") or 0) + 4 * (nut.get("carbs") or 0) + 9 * (nut.get("fat") or 0)
    if k == 0 and est > 20:
        return "dudoso: 0 kcal"
    if (nut.get("protein") or 0) > 95:
        return "dudoso: proteína >95 g"
    if est and abs(k - est) > max(40, 0.25 * k):
        return "dudoso: kcal no cuadran con los macros"
    return ""


def resolve_wh(cli: Client, postcode: str) -> str | None:
    """Código postal → almacén (cabecera x-customer-wh)."""
    _, headers = cli.get(f"{SHOP}/api/postal-codes/actions/change-pc/", method="PUT",
                         body=json.dumps({"new_postal_code": postcode}).encode(), headers={"Content-Type": "application/json"})
    return {k.lower(): v for k, v in headers.items()}.get("x-customer-wh")


def refresh(prev: dict | None, cli: Client, postcode: str | None = None, wh: str | None = None,
            max_details: int = 200, max_off: int = 80, deadline_s: float = 780, clock=time.monotonic,
            off_cli: Client | None = None, probe: bool = False) -> dict:
    """Catálogo nuevo: listados de categorías (precios) + ficha solo de los productos nuevos + nutrición conocida.
    Lanza Stop si Mercadona responde 403/429 o algo que no es JSON, y RuntimeError si no da tiempo: en los dos casos
    quien llama se queda con el catálogo anterior. probe=True: solo el árbol y la primera categoría, para comprobar
    que se llega (no escribe nada)."""
    t0 = clock()
    prev_rows = {p["id"]: p for p in (prev or {}).get("products") or []}
    by_ean = {p["ean"]: p for p in prev_rows.values() if p.get("ean")}
    postcode = postcode or ((prev or {}).get("meta") or {}).get("postcode")
    wh = wh or (resolve_wh(cli, postcode) if postcode else None) or ((prev or {}).get("meta") or {}).get("wh")
    if not wh:
        raise RuntimeError(f"Mercadona no ha devuelto almacén para el código postal {postcode}.")
    q = urllib.parse.urlencode({"lang": "es", "wh": wh})
    tree = cli.json(f"{SHOP}/api/categories/?{q}")
    rows: dict[str, dict] = {}
    subs = [(t, s) for t in tree.get("results") or [] if t.get("name") in FOOD_TOP for s in t.get("categories") or []]
    if probe:
        subs = subs[:1]
    for t, sub in subs:
        if clock() - t0 > deadline_s:
            raise RuntimeError("No ha dado tiempo a leer todas las categorías: se mantiene el catálogo anterior.")
        d = cli.json(f"{SHOP}/api/categories/{sub['id']}/?{q}")
        for leaf in d.get("categories") or []:
            for p in leaf.get("products") or []:
                pid = str(p["id"])
                if pid in rows:
                    continue
                old = prev_rows.get(pid) or {}
                rows[pid] = {"id": pid, "name": p.get("display_name") or old.get("name") or "",
                             "cat": " > ".join([t.get("name", ""), sub.get("name", ""), leaf.get("name", "")]),
                             "brand": old.get("brand"), "pack": p.get("packaging"), "url": p.get("share_url") or old.get("url"),
                             "ean": old.get("ean"), "nut": old.get("nut"), "nutSrc": old.get("nutSrc"),
                             "nutFlag": old.get("nutFlag") or "", **normalise_price(p.get("price_instructions") or {})}
    new_ids = [pid for pid in rows if pid not in prev_rows]
    stats = {"listings": len(subs), "products": len(rows), "new": len(new_ids), "details": 0, "offTried": 0, "offHits": 0,
             "removed": len(set(prev_rows) - set(rows)), "stoppedOff": None}
    if probe:
        return {"meta": {"probe": True, "wh": wh, "postcode": postcode, "stats": stats}, "products": list(rows.values())}
    # Ficha (marca y EAN) solo de los nuevos
    for pid in new_ids[:max_details]:
        if clock() - t0 > deadline_s:
            break
        p = cli.json(f"{SHOP}/api/products/{pid}/?{q}")
        stats["details"] += 1
        r = rows[pid]
        r["brand"] = (p.get("details") or {}).get("brand") or p.get("brand")
        r["ean"] = p.get("ean")
        twin = by_ean.get(r["ean"]) if r["ean"] else None
        if twin and twin.get("nut"):  # mismo producto con otra id: se reutiliza su nutrición
            r.update(nut=twin["nut"], nutSrc=twin.get("nutSrc"), nutFlag=twin.get("nutFlag") or "")
    # Nutrición de Open Food Facts por EAN para los nuevos sin nutrición (si OFF dice 429, solo se para esta parte)
    off = off_cli or Client(gap=1.0)
    for pid in [i for i in new_ids if rows[i].get("ean") and not rows[i].get("nut")][:max_off]:
        if clock() - t0 > deadline_s:
            break
        stats["offTried"] += 1
        try:
            d = off.json(f"{OFF_PRODUCT}/{rows[pid]['ean']}.json?fields=code,product_name,nutriments")
        except Stop as e:
            stats["stoppedOff"] = str(e)[:160]
            break
        except Exception:  # noqa: BLE001 - un producto sin datos no para el resto
            continue
        nut = _nut_from_off((d.get("product") or {}).get("nutriments") or {}) if d.get("status") == 1 else None
        if nut:
            rows[pid].update(nut=nut, nutSrc="openfoodfacts", nutFlag=nut_flag(nut))
            stats["offHits"] += 1
    meta = {"source": "Mercadona (tienda.mercadona.es), con su permiso (03-11-2026)", "date": datetime.now().date().isoformat(),
            "refreshedAt": datetime.now().astimezone().isoformat(timespec="seconds"), "wh": wh, "postcode": postcode,
            "requests": cli.requests, "nutrition": NUTRITION_ATTRIBUTION, "stats": stats,
            "seconds": round(clock() - t0)}
    out = compact(list(rows.values()), meta)
    if prev_rows and len(out["products"]) < MIN_KEEP * len(prev_rows):
        raise RuntimeError(f"El catálogo nuevo tiene {len(out['products'])} productos frente a {len(prev_rows)}: "
                           "no se publica (se mantiene el anterior).")
    return out


# ======================================================================== uso local (subir el catálogo de research/)
def _main() -> None:  # pragma: no cover - herramienta local
    import argparse
    ap = argparse.ArgumentParser(description="Catálogo de la lista de la compra (los datos nunca van al repositorio).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="Compacta un catálogo completo (JSON de research/) y opcionalmente lo sube a S3")
    b.add_argument("src")
    b.add_argument("--out")
    b.add_argument("--bucket", help="Bucket privado: lo publica en admin/catalog/")
    b.add_argument("--date", help="Fecha de los precios (AAAA-MM-DD)")
    b.add_argument("--wh", required=True, help="Almacén de los precios (cabecera x-customer-wh)")
    b.add_argument("--postcode", default=os.environ.get("CATALOG_POSTCODE"))
    r = sub.add_parser("refresh", help="Refresco semanal desde este PC (si la Lambda no puede) y lo sube a S3")
    r.add_argument("--bucket", required=True)
    r.add_argument("--postcode", default=os.environ.get("CATALOG_POSTCODE"))
    r.add_argument("--probe", action="store_true")
    a = ap.parse_args()
    import boto3
    s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "eu-west-1"))
    if a.cmd == "build":
        src = json.load(open(a.src))
        day = a.date or (src.get("meta") or {}).get("date", "")[:10] or datetime.now().date().isoformat()
        cat = compact(src["products"], {"source": "Mercadona (tienda.mercadona.es), con su permiso (03-11-2026)",
                                        "date": day, "wh": a.wh, "postcode": a.postcode, "nutrition": NUTRITION_ATTRIBUTION})
        if a.out:
            open(a.out, "w").write(json.dumps(cat, ensure_ascii=False, separators=(",", ":")))
        print(f"{cat['meta']['count']} productos de comida")
        if a.bucket:
            print("Subido:", put_s3(s3, a.bucket, cat))
    else:
        prev = load_s3(s3, a.bucket)
        cat = refresh(prev, Client(), a.postcode, probe=a.probe)
        print(json.dumps(cat["meta"], ensure_ascii=False))
        if not a.probe:
            print("Subido:", put_s3(s3, a.bucket, cat))


if __name__ == "__main__":  # pragma: no cover
    _main()
