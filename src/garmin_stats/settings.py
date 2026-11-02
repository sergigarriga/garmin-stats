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
