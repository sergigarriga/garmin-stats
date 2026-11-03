"""Previsión del tiempo para planificar los entrenos (Open-Meteo, sin clave). Python puro: lo usa la API sin pandas.

- Dónde: la ciudad que eliges en el Plan (settings["location"], solo nombre y coordenadas de ciudad).
- Caché en data/weather.json: se pide como mucho cada ~3 h (la sincronización de cada hora, al cambiar de ciudad y
  antes de que el coach reajuste el plan). Si Open-Meteo no responde, todo sigue como siempre sin previsión.
- Por día: mínima/máxima, sensación térmica, lluvia, viento, cielo en castellano, amanecer/anochecer y las mejores
  franjas para correr entre las 06:00 y las 22:00 (menos calor, lluvia y viento, y con luz si se puede).

Licencia: el plan gratuito de Open-Meteo es solo para uso no comercial. Si Runch pasa a ser comercial hay que
contratar su plan de pago (o cambiar de proveedor).
"""

from __future__ import annotations

import json
import logging
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta

from . import DATA_DIR
from . import settings

log = logging.getLogger(__name__)

PATH = DATA_DIR / "weather.json"
GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
TIMEOUT = 8
REFRESH_S = 3 * 3600
DAILY = ("temperature_2m_max,temperature_2m_min,apparent_temperature_max,precipitation_probability_max,precipitation_sum,"
         "wind_speed_10m_max,wind_gusts_10m_max,weather_code,sunrise,sunset")
HOURLY = "temperature_2m,apparent_temperature,precipitation_probability,wind_speed_10m,relative_humidity_2m"

# Códigos WMO → texto corto
WMO = {0: "Despejado", 1: "Casi despejado", 2: "Intervalos de nubes", 3: "Nublado", 45: "Niebla", 48: "Niebla con escarcha",
       51: "Llovizna débil", 53: "Llovizna", 55: "Llovizna intensa", 56: "Llovizna helada", 57: "Llovizna helada",
       61: "Lluvia débil", 63: "Lluvia", 65: "Lluvia fuerte", 66: "Lluvia helada", 67: "Lluvia helada fuerte",
       71: "Nieve débil", 73: "Nieve", 75: "Nieve fuerte", 77: "Nieve granulada", 80: "Chubascos débiles",
       81: "Chubascos", 82: "Chubascos fuertes", 85: "Chubascos de nieve", 86: "Chubascos de nieve fuertes",
       95: "Tormenta", 96: "Tormenta con granizo", 99: "Tormenta con granizo"}
STORM = {95, 96, 99}
SNOW = {71, 73, 75, 77, 85, 86}
HEAVY = {65, 67, 82}
FLAG_TEXT = {"heat": "calor", "storm": "tormenta", "heavy_rain": "lluvia fuerte", "rain": "lluvia", "wind": "viento fuerte",
             "snow": "nieve", "cold": "frío"}
BAD = {"storm", "heavy_rain", "wind", "snow"}  # días en los que conviene mover la sesión de calidad o la tirada


# ======================================================================== red (con tiempo límite y sin romper nada)
def _get(url: str, params: dict) -> dict | None:
    full = f"{url}?{urllib.parse.urlencode(params)}"
    try:
        req = urllib.request.Request(full, headers={"User-Agent": "Runch/1.0 (entrenos personales)"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:  # noqa: S310 - URL fija de Open-Meteo
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001 - sin previsión, el plan funciona igual
        log.warning("Open-Meteo no responde (%s): %s", url.split("/")[2], e)
        return None


def geocode(q: str) -> list[dict]:
    """Ciudades que coinciden con lo que escribes (máx. 5)."""
    q = (q or "").strip()[:60]
    if len(q) < 2:
        return []
    res = _get(GEO_URL, {"name": q, "count": 5, "language": "es", "format": "json"}) or {}
    out = []
    for r in res.get("results") or []:
        if r.get("latitude") is None or r.get("longitude") is None:
            continue
        label = ", ".join(x for x in (r.get("name"), r.get("admin1"), r.get("country")) if x)
        out.append({"name": r.get("name"), "label": label, "admin1": r.get("admin1"), "country": r.get("country"),
                    "lat": round(r["latitude"], 2), "lon": round(r["longitude"], 2)})
    return out


def fetch(lat: float, lon: float) -> dict | None:
    return _get(FORECAST_URL, {"latitude": lat, "longitude": lon, "daily": DAILY, "hourly": HOURLY,
                               "timezone": "Europe/Madrid", "forecast_days": 16, "wind_speed_unit": "kmh"})


# ======================================================================== resumen por día
def _hm(iso: str | None) -> int | None:
    if not iso or "T" not in iso:
        return None
    h, m = iso.split("T")[1][:5].split(":")
    return int(h) * 60 + int(m)


def _r(v, nd=0):
    return None if v is None else (round(v) if nd == 0 else round(v, nd))


def _hour_score(h: dict, sunrise: int | None, sunset: int | None) -> float:
    """Cuanto más bajo, mejor para correr: calor, frío, lluvia, viento, bochorno y oscuridad."""
    feels = h.get("feels") if h.get("feels") is not None else h.get("temp")
    s = 0.0
    if feels is not None:
        s += max(0.0, feels - 16) + 1.5 * max(0.0, feels - 24) + 0.6 * max(0.0, 6 - feels)
    s += (h.get("rain") or 0) / 10
    s += max(0.0, (h.get("wind") or 0) - 15) / 3
    if (h.get("temp") or 0) > 20 and (h.get("rh") or 0) > 70:
        s += (h["rh"] - 70) / 10
    if _dark(h["hour"], sunrise, sunset):
        s += 4  # de noche: mejor evitarlo si hay otra opción
    return s


def _dark(hour: int, sunrise: int | None, sunset: int | None) -> bool:
    mid = hour * 60 + 30
    return (sunrise is not None and mid < sunrise) or (sunset is not None and mid > sunset)


def best_windows(hours: list[dict], sunrise: int | None, sunset: int | None, n: int = 2) -> list[dict]:
    """Las mejores franjas de 2 h entre las 06:00 y las 22:00 (la mejor primero; la segunda, en otro momento del día)."""
    return pick_windows(slots(hours, sunrise, sunset), n)


def slots(hours: list[dict], sunrise: int | None, sunset: int | None) -> list[dict]:
    """Todas las franjas de 2 h entre las 06:00 y las 22:00 con su puntuación (cuanto más baja, mejor)."""
    by = {h["hour"]: h for h in hours}
    cands = []
    for start in range(6, 21):
        a, b = by.get(start), by.get(start + 1)
        if not a or not b:
            continue
        score = (_hour_score(a, sunrise, sunset) + _hour_score(b, sunrise, sunset)) / 2
        temps = [x.get("temp") for x in (a, b) if x.get("temp") is not None]
        feels = [x.get("feels") for x in (a, b) if x.get("feels") is not None]
        cands.append({
            "from": f"{start:02d}:00", "to": f"{start + 2:02d}:00",
            "temp": _r(max(temps)) if temps else None, "feels": _r(max(feels)) if feels else None,
            "rain": _r(max((x.get("rain") or 0) for x in (a, b))), "wind": _r(max((x.get("wind") or 0) for x in (a, b))),
            "dark": _dark(start, sunrise, sunset) or _dark(start + 1, sunrise, sunset), "score": round(score, 2)})
    return cands


def pick_windows(cands: list[dict], n: int = 2, from_hour: int = 0) -> list[dict]:
    """Las `n` mejores franjas que empiezan a partir de `from_hour`, separadas al menos 4 h entre sí."""
    ok = sorted((c for c in cands if int(c["from"][:2]) >= from_hour), key=lambda c: (c["score"], c["from"]))
    out: list[dict] = []
    for c in ok:
        h = int(c["from"][:2])
        if not out:
            out.append(c)
        elif len(out) < n and all(abs(h - int(o["from"][:2])) >= 4 for o in out) and c["score"] <= out[0]["score"] + 4:
            out.append(c)
    return out


def summarise(raw: dict) -> list[dict]:
    """De la respuesta de Open-Meteo a un resumen por día (lo que ve la web y el coach)."""
    d, h = raw.get("daily") or {}, raw.get("hourly") or {}
    hours: dict[str, list[dict]] = {}
    for i, t in enumerate(h.get("time") or []):
        day, hh = t.split("T")
        col = lambda k: (h.get(k) or [None] * (i + 1))[i]  # noqa: E731
        hours.setdefault(day, []).append({"hour": int(hh[:2]), "temp": col("temperature_2m"), "feels": col("apparent_temperature"),
                                          "rain": col("precipitation_probability"), "wind": col("wind_speed_10m"),
                                          "rh": col("relative_humidity_2m")})
    out = []
    for i, day in enumerate(d.get("time") or []):
        col = lambda k: (d.get(k) or [None] * (i + 1))[i]  # noqa: E731
        code = col("weather_code")
        sr, ss = _hm(col("sunrise")), _hm(col("sunset"))
        hs = hours.get(day, [])
        sl = slots(hs, sr, ss)
        tmax, tmin, feels = col("temperature_2m_max"), col("temperature_2m_min"), col("apparent_temperature_max")
        prob, mm, wind, gust = col("precipitation_probability_max"), col("precipitation_sum"), col("wind_speed_10m_max"), col("wind_gusts_10m_max")
        hot = max(hs, key=lambda x: x.get("temp") if x.get("temp") is not None else -99) if hs else {}
        flags = []
        if (feels is not None and feels >= 26) or ((tmax or 0) >= 25 and (hot.get("rh") or 0) >= 70):
            flags.append("heat")
        if code in STORM:
            flags.append("storm")
        if code in SNOW:
            flags.append("snow")
        if code in HEAVY or ((mm or 0) >= 8 and (prob or 0) >= 60):
            flags.append("heavy_rain")
        elif (prob or 0) >= 60 and (mm or 0) >= 1:
            flags.append("rain")
        if (wind or 0) >= 35 or (gust or 0) >= 60:
            flags.append("wind")
        if tmin is not None and tmin <= 3:
            flags.append("cold")
        out.append({
            "date": day, "code": code, "text": WMO.get(code, "—"),
            "tmin": _r(tmin), "tmax": _r(tmax), "feelsMax": _r(feels), "rainProb": _r(prob), "rainMm": _r(mm, 1),
            "windMax": _r(wind), "gustMax": _r(gust), "humidity": _r(hot.get("rh")),
            "sunrise": (col("sunrise") or "")[11:16] or None, "sunset": (col("sunset") or "")[11:16] or None,
            "windows": pick_windows(sl), "slots": sl, "flags": flags,
        })
    return out


# ======================================================================== caché
def load() -> dict:
    try:
        return json.loads(PATH.read_text())
    except (OSError, ValueError):
        return {}


def save(state: dict) -> None:
    PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1))
    tmp.replace(PATH)


def _same_place(a: dict | None, b: dict | None) -> bool:
    return bool(a and b) and abs(a["lat"] - b["lat"]) < 0.011 and abs(a["lon"] - b["lon"]) < 0.011


def refresh(force: bool = False) -> bool:
    """Pide la previsión si hace falta (cambio de ciudad o más de ~3 h). True si hay datos nuevos."""
    loc = settings.location()
    if not loc:
        return False
    cache = load()
    if not force and _same_place(cache.get("location"), loc) and time.time() - (cache.get("fetchedTs") or 0) < REFRESH_S:
        return False
    raw = fetch(loc["lat"], loc["lon"])
    if not raw or not (raw.get("daily") or {}).get("time"):
        return False
    try:
        days = summarise(raw)
    except Exception as e:  # noqa: BLE001 - una respuesta rara no puede romper la sincronización
        log.warning("Previsión con un formato inesperado: %s", e)
        return False
    save({"location": loc, "fetchedTs": int(time.time()),
          "fetchedAt": datetime.now().astimezone().isoformat(timespec="minutes"), "source": "open-meteo", "days": days})
    return True


def days(today: date | None = None) -> dict[str, dict]:
    """Previsión por fecha (de hoy en adelante) para la ciudad elegida AHORA. Vacío si no hay ciudad o caché."""
    loc = settings.location()
    cache = load()
    if not loc or not _same_place(cache.get("location"), loc):
        return {}
    lim = (today or date.today()).isoformat()
    return {d["date"]: d for d in cache.get("days") or [] if d["date"] >= lim}


def block() -> dict:
    """Para data.js: la ciudad elegida, cuándo se pidió y los días que quedan."""
    loc = settings.location()
    cache = load()
    ds = [{k: v for k, v in d.items() if k != "slots"} for d in days().values()]  # las franjas sueltas no hacen falta en la web
    return {"location": loc, "fetchedAt": cache.get("fetchedAt") if ds else None, "days": ds}


def for_coach(dates: list[str]) -> list[dict] | None:
    """Los días de `dates` dentro del horizonte de la previsión, en castellano y compactos (para el prompt)."""
    by = days()
    out = []
    for d in dates:
        w = by.get(d)
        if not w:
            continue
        win = w["windows"][0] if w.get("windows") else None
        out.append({
            "fecha": d, "cielo": w["text"], "min_c": w["tmin"], "max_c": w["tmax"], "sensacion_max_c": w["feelsMax"],
            "humedad_hora_mas_calida": w.get("humidity"),
            "lluvia_prob": w["rainProb"], "lluvia_mm": w["rainMm"], "viento_max_kmh": w["windMax"], "rachas_kmh": w["gustMax"],
            "amanece": w["sunrise"], "anochece": w["sunset"],
            "mejor_franja": win and f"{win['from']}-{win['to']} ({win['temp']} °C, lluvia {win['rain']} %)",
            "avisos": [FLAG_TEXT[f] for f in w.get("flags") or []],
        })
    return out or None


# ======================================================================== consejo del día (sin IA)
HARD = ("tempo", "intervals", "long", "race")
OUTDOOR = ("easy", "long", "tempo", "intervals", "race")


def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " y " + items[-1]


def _win_text(w: dict | None) -> str:
    return f"de {w['from']} a {w['to']}" if w else "a la hora más fresca que puedas"


def advice(session: dict, plan_days: list[dict] | None = None, today: date | None = None,
           now: datetime | None = None) -> dict | None:
    """Si la sesión de hoy choca con el tiempo (calor, tormenta, lluvia fuerte, viento, frío), un consejo concreto:
    la mejor franja, cambiarla por otro día de la semana con mejor tiempo o una alternativa a cubierto.
    plan_days: las sesiones de los próximos días del plan (para proponer el cambio)."""
    today = today or date.today()
    by = days(today)
    w = by.get(today.isoformat())
    if not w or session.get("type") not in OUTDOOR:
        return None
    flags = set(w.get("flags") or [])
    # solo franjas que aún no han pasado (el consejo se recalcula cada hora con la sincronización)
    now = now or datetime.now()
    start = now.hour + (1 if now.minute >= 30 else 0) if now.date() == today else 0
    left = pick_windows(w.get("slots") or [], 2, start) if w.get("slots") else [x for x in w.get("windows") or [] if int(x["from"][:2]) >= start]
    best = left[0] if left else None
    hard = session["type"] in HARD
    tip = None
    bad = flags & BAD
    if bad:
        what = _join([FLAG_TEXT[f] for f in ("storm", "heavy_rain", "snow", "wind") if f in bad])
        sky = "" if w["text"].lower() in what else f" ({w['text'].lower()})"
        swap = None
        if hard:
            for s in plan_days or []:
                d = s.get("date", "")
                if d <= today.isoformat() or d > (today + timedelta(days=3)).isoformat():
                    continue
                other = by.get(d)
                if other and not (set(other.get("flags") or []) & BAD) and s.get("type") in ("easy", "rest", "cross", "swim", "strength"):
                    swap = (s, other)
                    break
        if swap:
            s, other = swap
            dn = date.fromisoformat(s["date"]).strftime("%w")
            name = ["domingo", "lunes", "martes", "miércoles", "jueves", "viernes", "sábado"][int(dn)]
            tip = (f"Hoy hay **{what}**{sky}. Cambia esta sesión por la del **{name}** "
                   f"({other['text'].lower()}, {other['tmax']} °C) y hoy haz la de ese día.")
        elif best and best.get("rain", 100) < 40 and best.get("wind", 99) < 30:
            tip = f"Hoy hay **{what}**, pero {_win_text(best)} da una tregua: sal entonces o haz la sesión en cinta."
        else:
            tip = (f"Hoy hay **{what}**: mejor en cinta o en el gimnasio" + (" (mismos bloques y ritmos)." if hard else ", o cámbiala por bici o natación."))
    elif "heat" in flags:
        feels = w.get("feelsMax") or w.get("tmax")
        tip = (f"Hoy se llega a {w['tmax']} °C (sensación {feels} °C): sal {_win_text(best)}"
               + (", ve por pulso o unos 10-20 s/km más lento" if hard else ", a ritmo cómodo")
               + " y lleva agua.")
    elif "rain" in flags:
        tip = f"Probabilidad de lluvia del {w['rainProb']} %: la mejor franja es {_win_text(best)}." if best else None
    elif "cold" in flags:
        tip = f"Mínima de {w['tmin']} °C: abrígate por capas" + (" y lleva algo reflectante si sales sin luz." if best and best.get("dark") else ".")
    day = {k: v for k, v in w.items() if k != "slots"}
    return {"tip": tip, "best": best, "day": day}


# ======================================================================== zona de tu última carrera (sugerencia)
def last_run_area(store) -> dict | None:
    """Zona (redondeada a ~10 km) de tu última carrera al aire libre con GPS, para sugerirla como ciudad."""
    best = None
    for _, a in store.items("activity"):
        t = ((a.get("activityType") or {}).get("typeKey") or "")
        if "running" not in t or any(x in t for x in ("treadmill", "indoor", "virtual")):
            continue
        lat, lon = a.get("startLatitude"), a.get("startLongitude")
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)) or (abs(lat) < 0.01 and abs(lon) < 0.01):
            continue
        start = a.get("startTimeLocal") or ""
        if best is None or start > best[0]:
            best = (start, lat, lon)
    if not best:
        return None
    return {"lat": round(best[1], 1), "lon": round(best[2], 1), "date": best[0][:10]}
