"""Probabilidad real de llegar al tiempo objetivo del plan, recalculada cada día.

1) Tiempo previsto HOY: tu VDOT actual (el de Ritmos) con la fórmula de Daniels para la distancia del objetivo.
2) Mejora esperada hasta la carrera: unas 0,15 unidades de VDOT por semana entrenando bien (como mucho +3),
   escalada por lo que cumples el plan (últimas 4 semanas).
3) Incertidumbre: ±2,5 % del tiempo, más cuanto más lejos está la carrera y si tu nivel no sale de una carrera real.
4) Probabilidad = la de que el tiempo previsto ese día sea igual o mejor que el objetivo (distribución normal).
"""

from __future__ import annotations

import json
import math
import re
from datetime import date, timedelta

from . import metrics as M

DIST = {"5 km": 5000, "10 km": 10000, "Media maratón": 21097.5, "Maratón": 42195}
GAIN_PER_WEEK = 0.15
GAIN_MAX = 3.0


def goal_seconds(text: str | None, meters: float) -> float | None:
    """'1:30' (media) = 1 h 30; '45:00' o '45.00' (10 km) = 45 min; '1:35:40'; '45' = 45 min."""
    if not text:
        return None
    t = text.strip().lower().replace(".", ":").replace("h", ":").replace("'", ":").replace("min", "").strip(": ")
    parts = [p for p in re.split(r"[:\s]+", t) if p]
    try:
        n = [float(p) for p in parts]
    except ValueError:
        return None
    if len(n) == 3:
        s = n[0] * 3600 + n[1] * 60 + n[2]
    elif len(n) == 2:
        # dos números: horas:minutos en media y maratón si el primero es pequeño; si no, minutos:segundos
        s = n[0] * 3600 + n[1] * 60 if meters >= 21000 and n[0] < 6 else n[0] * 60 + n[1]
    elif len(n) == 1:
        s = n[0] * 60 if n[0] < 400 else n[0]
    else:
        return None
    return s if s > 0 else None


def _phi(z: float) -> float:
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def adherence(plan: dict) -> float | None:
    """Cumplimiento de las últimas 4 semanas (0-1): hecho = 1, a medias = 0,5, no hecho = 0."""
    since = (date.today() - timedelta(days=28)).isoformat()
    due = [s for w in plan.get("weeks", []) for s in w.get("sessions", [])
           if s.get("date", "") >= since and s.get("status") in ("done", "partial", "missed")]
    if len(due) < 3:
        return None
    return sum(1 if s["status"] == "done" else 0.5 if s["status"] == "partial" else 0 for s in due) / len(due)


def compute(plan: dict | None, paces: dict | None, today: date | None = None) -> dict | None:
    if not plan or not paces or not paces.get("vdot"):
        return None
    meters = DIST.get(plan.get("goal", ""))
    goal_s = goal_seconds(plan.get("goalTime"), meters or 0) if meters else None
    if not meters or not goal_s:
        return None
    today = today or date.today()
    try:
        race = date.fromisoformat(plan["raceDate"])
    except (KeyError, ValueError):
        return None
    days = (race - today).days
    if days < 0:
        return None
    weeks = days / 7
    vdot = float(paces["vdot"])
    adh = adherence(plan)
    c = 0.8 if adh is None else adh
    gain = min(GAIN_MAX, GAIN_PER_WEEK * weeks) * max(0.0, (c - 0.3) / 0.7)  # cumplir <30 % = no mejoras
    now_s = M.predict_time(vdot, meters)
    race_s = M.predict_time(vdot + gain, meters)
    sd = 0.025 + 0.0012 * weeks + (0.01 if paces.get("source") != "race" else 0) + (0.01 if paces.get("stale") else 0)
    p = _phi((goal_s - race_s) / (sd * race_s))
    need_vdot = M.vdot_from_effort(meters, goal_s)
    return {
        "goal": plan["goal"], "goalTime": plan.get("goalTime"), "goalS": round(goal_s), "raceDate": plan["raceDate"],
        "daysLeft": days, "pct": round(100 * p), "predictedS": round(race_s), "nowS": round(now_s),
        "vdot": round(vdot, 1), "needVdot": round(need_vdot, 1), "gain": round(gain, 1),
        "adherence": None if adh is None else round(100 * adh), "source": paces.get("source"),
    }


def with_history(odds: dict | None, store) -> dict | None:
    """Guarda un punto al día (últimos 90) para ver si tus opciones suben o bajan."""
    if not odds:
        return odds
    try:
        hist = json.loads(store.state("goal_odds") or "[]")
    except ValueError:
        hist = []
    key = (odds["goal"], odds["goalTime"], odds["raceDate"])
    hist = [h for h in hist if tuple(h.get("k", [])) == key]  # objetivo nuevo = historial nuevo
    d = date.today().isoformat()
    hist = [h for h in hist if h["d"] != d] + [{"d": d, "pct": odds["pct"], "k": list(key)}]
    hist = hist[-90:]
    store.set_state("goal_odds", json.dumps(hist))
    store.commit()
    return {**odds, "history": [{"d": h["d"], "pct": h["pct"]} for h in hist]}
