"""Ajustes del usuario en data/settings.json (por ejemplo, periodos con el reloj roto)."""

from __future__ import annotations

import json
from datetime import date, timedelta

from . import DATA_DIR

PATH = DATA_DIR / "settings.json"


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


def set_race_test(payload: dict) -> dict:
    """Una marca reciente (carrera o test a tope) para calcular los ritmos. {"clear": true} la quita."""
    st = load()
    if payload.get("clear"):
        st.pop("race_test", None)
    else:
        try:
            meters, secs = float(payload["distance_m"]), int(payload["time_s"])
        except (KeyError, TypeError, ValueError):
            raise ValueError("Indica la distancia y el tiempo.") from None
        if not 1500 <= meters <= 42195:
            raise ValueError("La distancia tiene que estar entre 1,5 km y la maratón.")
        pace = secs / (meters / 1000)
        if not 150 <= pace <= 600:
            raise ValueError("Ese tiempo da un ritmo fuera de lo normal (entre 2:30 y 10:00 /km). Revísalo.")
        d = payload.get("date") or date.today().isoformat()
        try:
            dd = date.fromisoformat(d)
        except ValueError:
            raise ValueError("Fecha no válida.") from None
        if dd > date.today():
            raise ValueError("La fecha no puede ser futura.")
        st["race_test"] = {"distance_m": meters, "time_s": secs, "date": dd.isoformat()}
    save(st)
    return st


def set_swim_test(payload: dict) -> dict:
    """Test de natación: 400 m y 200 m a tope (en segundos). {"clear": true} lo quita. pool_m: largo de tu piscina."""
    st = load()
    if payload.get("pool_m"):
        try:
            pool = round(float(payload["pool_m"]), 2)
        except (TypeError, ValueError):
            raise ValueError("Largo de piscina no válido.") from None
        if pool not in (25, 50, 22.86):
            raise ValueError("La piscina tiene que ser de 25 m, 50 m o 25 yardas.")
        st["pool_m"] = pool
    if payload.get("clear"):
        st.pop("swim_test", None)
    elif payload.get("t400_s") is not None or payload.get("t200_s") is not None:
        try:
            t400, t200 = int(payload["t400_s"]), int(payload["t200_s"])
        except (KeyError, TypeError, ValueError):
            raise ValueError("Indica los dos tiempos (400 m y 200 m).") from None
        if not 180 <= t400 <= 1500 or not 80 <= t200 <= 720:
            raise ValueError("Tiempos fuera de lo normal: revisa minutos y segundos.")
        if t400 <= 2 * t200:
            raise ValueError("El 400 tiene que ser más lento que dos veces el 200 (si no, el test no vale).")
        if (t400 - t200) / 2 > 300:
            raise ValueError("Ese test da un ritmo de más de 5:00 /100 m: revisa los tiempos.")
        st["swim_test"] = {"t400_s": t400, "t200_s": t200, "date": date.today().isoformat()}
    save(st)
    return st


def watch_gaps() -> list[dict]:
    return load().get("watch_gaps", [])


def in_gap(d: date) -> bool:
    return any(date.fromisoformat(g["from"]) <= d <= date.fromisoformat(g["to"]) for g in watch_gaps())


def recorded_start(days: int, today: date | None = None) -> date:
    """Fecha desde la que hay `days` días REGISTRADOS hasta hoy, saltando los huecos del reloj."""
    cur = today or date.today()
    left = days
    while left > 0:
        cur -= timedelta(days=1)
        if not in_gap(cur):
            left -= 1
    return cur


# ======================================================================== tiempo disponible por día
# settings["availability"] = {"weekly": {"0".."6" (lunes..domingo): minutos | None}, "days": {"AAAA-MM-DD": minutos}}
# 0 = ese día no puedes entrenar; None (o sin valor) = sin límite, el coach decide.
MAX_MIN = 480
AHEAD_DAYS = 56  # los días concretos se pueden fijar hasta ~8 semanas vista


def _minutes(v, what: str) -> int | None:
    if v is None or v == "":
        return None
    try:
        n = round(float(v))
    except (TypeError, ValueError):
        raise ValueError(f"{what}: indica los minutos (0-{MAX_MIN}).") from None
    if not 0 <= n <= MAX_MIN:
        raise ValueError(f"{what}: tiene que estar entre 0 y {MAX_MIN} minutos (8 h).")
    return n


def _clean_days(days: dict, today: date) -> dict:
    """Quita los días pasados (y los que ya no tienen valor)."""
    return {d: m for d, m in sorted(days.items()) if m is not None and d >= today.isoformat()}


def availability(st: dict | None = None, today: date | None = None) -> dict:
    """Tu tiempo disponible, limpio: semana tipo (7 valores) y días concretos de hoy en adelante."""
    st = load() if st is None else st
    today = today or date.today()
    a = st.get("availability") or {}
    weekly = {str(i): (a.get("weekly") or {}).get(str(i)) for i in range(7)}
    return {"weekly": weekly, "days": _clean_days(a.get("days") or {}, today)}


def has_availability(st: dict | None = None) -> bool:
    a = availability(st)
    return any(v is not None for v in a["weekly"].values()) or bool(a["days"])


def set_availability(payload: dict) -> dict:
    """Guarda la semana tipo y/o los días concretos. {"clear": true} lo borra todo.
    weekly: {"0".."6": minutos | null}; days: {"AAAA-MM-DD": minutos | null (null quita ese día)}."""
    st = load()
    today = date.today()
    if payload.get("clear"):
        st.pop("availability", None)
        save(st)
        return st
    cur = availability(st, today)
    weekly, days = dict(cur["weekly"]), dict(cur["days"])
    if "weekly" in payload:
        w = payload.get("weekly") or {}
        if not isinstance(w, dict):
            raise ValueError("Semana no válida.")
        names = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
        for k, v in w.items():
            if str(k) not in weekly:
                raise ValueError("Día de la semana no válido.")
            weekly[str(k)] = _minutes(v, names[int(k)].capitalize())
    if "days" in payload:
        dd = payload.get("days") or {}
        if not isinstance(dd, dict):
            raise ValueError("Días no válidos.")
        if payload.get("replaceDays"):
            days = {}
        for k, v in dd.items():
            try:
                d = date.fromisoformat(str(k))
            except ValueError:
                raise ValueError("Fecha no válida.") from None
            if d < today or d > today + timedelta(days=AHEAD_DAYS):
                raise ValueError("Los días concretos tienen que ser de hoy a 8 semanas vista.")
            m = _minutes(v, d.strftime("%d-%m"))
            if m is None:
                days.pop(d.isoformat(), None)
            else:
                days[d.isoformat()] = m
    st["availability"] = {"weekly": weekly, "days": _clean_days(days, today)}
    if not has_availability(st):
        st.pop("availability", None)
    save(st)
    return st


def available_minutes(d: date | str, st: dict | None = None) -> int | None:
    """Minutos que tienes ese día: el día concreto manda sobre la semana tipo. None = sin límite."""
    a = availability(st)
    key = d if isinstance(d, str) else d.isoformat()
    if key in a["days"]:
        return a["days"][key]
    return a["weekly"].get(str(date.fromisoformat(key).weekday()))


# ======================================================================== dónde entrenas (para la previsión del tiempo)
def location(st: dict | None = None) -> dict | None:
    loc = (load() if st is None else st).get("location")
    return loc if loc and loc.get("lat") is not None and loc.get("lon") is not None else None


def set_location(payload: dict) -> dict:
    """{"name", "lat", "lon"} (ciudad elegida en el buscador) o {"clear": true}. Se guarda a nivel de ciudad
    (coordenadas con 2 decimales, ~1 km): no hace falta más precisión para la previsión."""
    st = load()
    if payload.get("clear"):
        st.pop("location", None)
        save(st)
        return st
    name = str(payload.get("name") or "").strip()[:80]
    try:
        lat, lon = float(payload["lat"]), float(payload["lon"])
    except (KeyError, TypeError, ValueError):
        raise ValueError("Elige una ciudad de la lista.") from None
    if not name:
        raise ValueError("Falta el nombre del lugar.")
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("Coordenadas no válidas.")
    st["location"] = {"name": name, "lat": round(lat, 2), "lon": round(lon, 2)}
    save(st)
    return st
