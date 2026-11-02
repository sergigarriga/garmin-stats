"""Cómo te encuentras (ánimo y agujetas de 1 a 5) y molestias o lesiones, en data/wellness.json.

Lo escribe la web (API) y lo leen el informe, el coach (para ajustar el plan y el consejo del día) y el chat.
  {"log": {"AAAA-MM-DD": {"mood": 1-5, "soreness": 1-5, "note": str, "at": iso}},
   "injuries": [{"id", "area", "severity": 1-5, "start", "end": None | fecha, "notes"}]}
"""

from __future__ import annotations

import json
import secrets
from datetime import date, datetime, timedelta

from . import DATA_DIR

PATH = DATA_DIR / "wellness.json"
MOOD = {1: "Muy mal", 2: "Mal", 3: "Normal", 4: "Bien", 5: "Genial"}
SORENESS = {1: "Nada", 2: "Leves", 3: "Moderadas", 4: "Fuertes", 5: "Muy fuertes"}
SEVERITY = {1: "Leve", 2: "Molesta", 3: "Moderada", 4: "Fuerte", 5: "Muy fuerte"}


def load() -> dict:
    try:
        d = json.loads(PATH.read_text())
        return {"log": d.get("log") or {}, "injuries": d.get("injuries") or []}
    except (OSError, ValueError):
        return {"log": {}, "injuries": []}


def save(state: dict) -> None:
    PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1))
    tmp.replace(PATH)


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _scale(v, name: str) -> int | None:
    if v in (None, ""):
        return None
    try:
        n = int(v)
    except (TypeError, ValueError):
        raise ValueError(f"{name}: tiene que ser un número del 1 al 5.") from None
    if not 1 <= n <= 5:
        raise ValueError(f"{name}: tiene que ser un número del 1 al 5.")
    return n


def _day(v, default: date | None = None, past_days: int = 400) -> str:
    if v in (None, ""):
        if default is None:
            raise ValueError("Falta la fecha.")
        return default.isoformat()
    try:
        d = date.fromisoformat(str(v))
    except ValueError:
        raise ValueError("Fecha no válida.") from None
    today = date.today()
    if d > today or d < today - timedelta(days=past_days):
        raise ValueError("La fecha tiene que ser de hoy o anterior.")
    return d.isoformat()


def set_day(payload: dict) -> dict:
    """Guarda (o borra, si viene todo vacío) cómo te encuentras un día (hoy o los 7 anteriores)."""
    st = load()
    d = _day(payload.get("date"), date.today(), past_days=7)
    entry = {"mood": _scale(payload.get("mood"), "Ánimo"), "soreness": _scale(payload.get("soreness"), "Agujetas"),
             "note": str(payload.get("note") or "").strip()[:300]}
    entry = {k: v for k, v in entry.items() if v not in (None, "")}
    if entry:
        st["log"][d] = {**entry, "at": _now()}
    else:
        st["log"].pop(d, None)
    # solo se guarda el último año
    lim = (date.today() - timedelta(days=366)).isoformat()
    st["log"] = {k: v for k, v in sorted(st["log"].items()) if k >= lim}
    save(st)
    return st


def injury(payload: dict) -> dict:
    """add | update | close | reopen | delete una molestia o lesión."""
    st = load()
    action = payload.get("action")
    items = st["injuries"]
    if action == "add":
        area = str(payload.get("area") or "").strip()[:60]
        if not area:
            raise ValueError("Indica la zona (p. ej. rodilla derecha).")
        if sum(1 for i in items if not i.get("end")) >= 10:
            raise ValueError("Ya tienes 10 molestias abiertas: cierra alguna antes.")
        items.append({"id": secrets.token_hex(4), "area": area, "severity": _scale(payload.get("severity"), "Intensidad") or 2,
                      "start": _day(payload.get("start"), date.today()), "end": None,
                      "notes": str(payload.get("notes") or "").strip()[:500], "at": _now()})
    else:
        it = next((i for i in items if i["id"] == payload.get("id")), None)
        if not it:
            raise ValueError("No encuentro esa molestia.")
        if action == "update":
            if payload.get("area"):
                it["area"] = str(payload["area"]).strip()[:60]
            if payload.get("severity") is not None:
                it["severity"] = _scale(payload["severity"], "Intensidad")
            if "notes" in payload:
                it["notes"] = str(payload.get("notes") or "").strip()[:500]
        elif action == "close":
            end = _day(payload.get("end"), date.today())
            if end < it["start"]:
                raise ValueError("No puede acabar antes de empezar.")
            it["end"] = end
        elif action == "reopen":
            it["end"] = None
        elif action == "delete":
            items.remove(it)
        else:
            raise ValueError("Acción no válida.")
        it["at"] = _now()
    # las cerradas hace más de un año se olvidan
    lim = (date.today() - timedelta(days=366)).isoformat()
    st["injuries"] = [i for i in items if not i.get("end") or i["end"] >= lim]
    save(st)
    return st


def block(state: dict | None = None) -> dict:
    """Lo que ve la web: hoy, los últimos 14 días y las molestias activas o cerradas hace poco."""
    st = state or load()
    today = date.today()
    since = (today - timedelta(days=13)).isoformat()
    recent = [{"d": d, **{k: v for k, v in e.items() if k != "at"}} for d, e in sorted(st["log"].items()) if d >= since]
    closed_lim = (today - timedelta(days=60)).isoformat()
    inj = [i for i in st["injuries"] if not i.get("end") or i["end"] >= closed_lim]
    inj.sort(key=lambda i: (bool(i.get("end")), i.get("start", "")), reverse=False)
    return {"today": next((r for r in recent if r["d"] == today.isoformat()), None), "recent": recent,
            "injuries": [{k: v for k, v in i.items() if k != "at"} for i in inj]}


def active_injuries(state: dict | None = None) -> list[dict]:
    st = state or load()
    return [i for i in st["injuries"] if not i.get("end")]


def for_coach(state: dict | None = None) -> dict:
    """Resumen para la IA (coach y chat), en palabras."""
    st = state or load()
    b = block(st)
    return {
        "como_se_encuentra_14_dias": [
            {"fecha": r["d"], "animo": MOOD.get(r.get("mood")), "agujetas": SORENESS.get(r.get("soreness")),
             **({"nota": r["note"]} if r.get("note") else {})} for r in b["recent"]],
        "molestias_y_lesiones": [
            {"zona": i["area"], "intensidad": f"{i['severity']}/5 ({SEVERITY.get(i['severity'])})", "desde": i["start"],
             "estado": f"recuperada el {i['end']}" if i.get("end") else "activa", **({"notas": i["notes"]} if i.get("notes") else {})}
            for i in b["injuries"]],
    }
