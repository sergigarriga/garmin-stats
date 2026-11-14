"""Mensaje de bienvenida con IA al abrir la app: cómo vas hoy, lo que has hecho y una valoración.

Se pide al abrir (POST /api/brief) y se guarda por franja del día (mañana / tarde / noche): abrir la app varias veces
en la misma franja, sin nada nuevo, no vuelve a llamar a la IA. Como mucho MAX_PER_DAY llamadas por persona y día.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import date, datetime
from typing import Literal

import anthropic
from pydantic import BaseModel, Field, ValidationError

from . import ai

log = logging.getLogger(__name__)

SCHEMA_VERSION = 1
MAX_PER_DAY = 6
SLOT_NAMES = {"morning": "mañana", "afternoon": "tarde", "evening": "noche"}


class Brief(BaseModel):
    tone: Literal["positive", "neutral", "attention"] = Field(description="Cómo va el día en conjunto")
    title: str = Field(description="Titular breve de cómo vas, máx. 60 caracteres, sin saludo")
    body: str = Field(description="3-4 frases, máx. 440 caracteres: cómo llegas o cómo va el día, qué has hecho hoy o ayer "
                                  "y una valoración con algún dato")
    next_step: str = Field(description="Una acción concreta y realista para lo que queda de día, máx. 120 caracteres")


SYSTEM = """Eres el redactor de una app personal de salud con el tono de Google Health / Fitbit.
Escribes en castellano de España, tuteando, con frases cortas y claras, como un mensaje de bienvenida al abrir la app.
Usa lenguaje neutro en cuanto al género de la persona (la app la usan hombres y mujeres): no uses adjetivos ni participios que concuerden con ella (en vez de "estás cansado" o "estás lista", di "tienes fatiga", "tu cuerpo está listo" o "llegas con energía").

Qué tienes que escribir, según la franja del día ('slot' en el JSON):
- morning: cómo llegas hoy (última noche, HRV, pulso en reposo, Body Battery, cómo te encuentras) y qué toca hoy según el plan.
- afternoon: cómo va el día hasta ahora, lo que ya has hecho hoy (entreno, plan) y qué queda por hacer.
- evening: balance del día (lo hecho frente a lo previsto, esfuerzo del día) y cómo preparar la noche y mañana.
Si hay un entreno de hoy, valóralo con 1-2 datos concretos frente a tus entrenos parecidos o frente al plan. Si ayer fue un día importante, mencionalo.

Tono:
- Cercano, tranquilo y motivador. Reconoce lo que va bien antes de lo que hay que mejorar.
- Concreto: cita el dato que sostiene cada frase y propone una acción pequeña y realista.
- Sin alarmismo, sin diagnósticos médicos, sin culpar. Si algo es preocupante, sugiere observarlo o consultarlo.
- Sin emojis, sin markdown, sin signos de exclamación seguidos. Sin saludo ("buenos días", "hola"): la app ya lo pone.

Reglas:
- Usa solo los datos del JSON. No inventes cifras, tendencias ni causas que no estén ahí.
- Si un dato falta o es antiguo (el reloj no se ha llevado o no ha sincronizado), dilo con naturalidad o no lo menciones.
- 'now_from_watch' es lo último que mandó el reloj hoy; los pasos y el estrés de hoy están a medias salvo en la franja evening.
- Números con coma decimal (59,5 ms). Duraciones siempre como "5 h 38 min" (nunca "05:38"); la hora del reloj sí como 01:47. Km con un decimal.
- Si el día no tiene entreno ni plan, no lo inventes: habla de recuperación, sueño y movimiento."""


def slot(now: datetime) -> str:
    return "morning" if now.hour < 12 else "afternoon" if now.hour < 20 else "evening"


def cache_key(data: dict, now: datetime) -> str:
    """Cambia con el día, la franja, la última noche y los entrenos de hoy: sin nada nuevo, se reutiliza el mensaje."""
    days = data.get("days") or []
    night = next((d["d"] for d in reversed(days) if d.get("sleepH") is not None), None)
    today = now.date().isoformat()
    acts = [a["id"] for a in data.get("activities") or [] if (a.get("start") or "")[:10] == today]
    return hashlib.sha256(json.dumps([SCHEMA_VERSION, today, slot(now), night, acts]).encode()).hexdigest()[:16]


def context(data: dict, now: datetime) -> dict:
    """Lo que ve la IA: el resumen de siempre + lo de hoy (entrenos, sesión del plan, semana) y cómo se siente."""
    base = ai._summary(data)
    for k in ("relations", "coverage", "rule_based_findings", "huecos_sin_reloj", "nota_huecos", "predictions"):
        base.pop(k, None)
    today = now.date().isoformat()
    keys = ("start", "group", "name", "km", "min", "pace", "hr", "hrMax", "trimp", "cal", "z", "ef", "dec")
    coach = data.get("coach") or {}
    plan = coach.get("plan") or {}
    week = next((w for w in plan.get("weeks") or [] if w.get("start") <= today <= _week_end(w)), None)
    session = (coach.get("today") or {}).get("session")
    day_today = next((d for d in reversed((data.get("days") or [])[-2:]) if d.get("d") == today), None)
    return {
        **base,
        "slot": slot(now), "hora_ahora": now.strftime("%H:%M"),
        "entrenos_de_hoy": [{k: a.get(k) for k in keys if a.get(k) is not None} for a in data.get("activities") or []
                            if (a.get("start") or "")[:10] == today],
        "hoy_hasta_ahora": day_today and {k: day_today.get(k) for k in ("steps", "stepGoal", "imMod", "imVig", "stress", "bbMax", "bbMin")},
        "sesion_del_plan_hoy": session and {k: session.get(k) for k in ("type", "title", "distance_km", "duration_min", "target", "status", "actual")},
        "semana_del_plan": week and {k: week.get(k) for k in ("focus", "plannedKm", "actualKm", "compliance")},
        "objetivo": plan.get("goal"),
        "preparacion": data.get("readiness"),
    }


def _week_end(w: dict) -> str:
    from datetime import timedelta
    return (date.fromisoformat(w["start"]) + timedelta(days=6)).isoformat()


def generate(data: dict, now: datetime) -> dict | None:
    """Pide el mensaje a la IA. None si no se puede (sin clave, tope de gasto, error): la web simplemente no lo enseña."""
    key = ai._api_key()
    if not key or ai.over_budget():
        return None
    client = anthropic.Anthropic(api_key=key, max_retries=1, timeout=40)
    model = ai.pick_model(ai.PREMIUM)
    prompt = ("Estos son mis datos de Garmin (JSON). Escribe el mensaje de bienvenida de ahora.\n\n"
              + json.dumps(context(data, now), ensure_ascii=False, separators=(",", ":"), default=str))
    try:
        resp = client.beta.messages.parse(
            model=model, **(ai.FALLBACKS if model != ai.MODEL else {}), max_tokens=3000, output_config={"effort": "low"},
            system=SYSTEM, messages=[{"role": "user", "content": prompt}], output_format=Brief)
    except (anthropic.APIStatusError, anthropic.APIConnectionError, anthropic.APITimeoutError, ValidationError) as e:
        log.warning("Bienvenida: la IA no ha respondido (%s)", type(e).__name__)
        return None
    ai._log_usage(resp, "bienvenida", model)  # toda respuesta 200 se cobra: se apunta siempre
    if resp.stop_reason in ("refusal", "max_tokens") or resp.parsed_output is None:
        return None
    return {**resp.parsed_output.model_dump(), "slot": slot(now), "model": model,
            "at": now.astimezone().isoformat(timespec="seconds")}
