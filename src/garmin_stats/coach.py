"""Entrenador con IA: crea un plan, lo compara con lo que haces y lo reajusta cada semana.

Se vuelve más listo con el tiempo porque guarda en data/coach.json:
- el plan vigente y su historial de ajustes,
- tu valoración de cada sesión (1-5 y una nota),
- una "memoria" de lo que ha aprendido de ti, que la IA lee y actualiza en cada ajuste.

Modelo: Claude Opus 5.5 para crear y reajustar (pocas llamadas, mucho razonamiento), con
alternativas automáticas del servidor si un modelo rechazara la petición.
"""

from __future__ import annotations

import json
import logging
import statistics
from datetime import date, datetime, timedelta
from typing import Literal

import anthropic
from pydantic import BaseModel, Field, ValidationError

from . import DATA_DIR
from . import ai
from . import settings

log = logging.getLogger(__name__)

MODEL = "claude-opus-5-5"  # el plan es lo más difícil y se llama poco: Opus 5.5 (con el tope de gasto cae a Haiku)
STATE = DATA_DIR / "coach.json"
RUN_TYPES = ("easy", "long", "tempo", "intervals", "race")

SessionType = Literal["easy", "long", "tempo", "intervals", "race", "strength", "cross", "rest"]


class Session(BaseModel):
    date: str = Field(description="AAAA-MM-DD")
    type: SessionType
    title: str = Field(description="Nombre corto, p. ej. 'Rodaje suave' o '6 x 1 km'")
    distance_km: float | None = Field(description="Distancia prevista en km (null en fuerza o descanso)")
    duration_min: int | None = Field(description="Duración prevista en minutos")
    target: str = Field(description="Ritmo o zona objetivo, p. ej. '5:50-6:10 /km · Z2'")
    description: str = Field(description="Qué hacer, en 1-2 frases claras")


class Week(BaseModel):
    start: str = Field(description="Lunes de la semana, AAAA-MM-DD")
    focus: str = Field(description="Objetivo de la semana en pocas palabras")
    sessions: list[Session]


class PlanOut(BaseModel):
    summary: str = Field(description="2-3 frases: cómo está planteado el plan y por qué, con tus datos")
    weeks: list[Week]
    memory: list[str] = Field(description="Hasta 12 aprendizajes sobre el atleta, cortos y con dato")


class AdaptOut(BaseModel):
    message: str = Field(description="2-4 frases para el atleta: qué ha pasado esta semana, qué cambias y por qué")
    weeks: list[Week] = Field(description="Las semanas desde la actual hasta el final, completas y actualizadas")
    memory: list[str] = Field(description="Memoria actualizada: hasta 12 aprendizajes, quita los que ya no valgan")


SYSTEM = """Eres un entrenador de running con criterio y prudencia, y escribes con el tono de Google Health:
castellano de España, tuteando, claro, motivador y sin alarmismo.

Principios:
- Parte del nivel REAL del atleta (kilómetros de las últimas semanas, tirada más larga reciente, ritmos reales).
  Si viene de un parón, empieza por debajo de lo que hacía antes y reconstruye la base.
- Sube el volumen semanal como mucho un 10 % y mete una semana de descarga cada 3-4 semanas.
- Alrededor del 80 % del tiempo a ritmo suave (Z1-Z2). Como mucho 1-2 sesiones de calidad por semana.
- Respeta los días disponibles y el día preferido para la tirada larga. Los demás días: descanso o fuerza suave.
- Últimas 1-2 semanas antes de la carrera: puesta a punto (menos volumen, algo de ritmo).
- Ritmos objetivo basados en sus ritmos reales y su VO2max, no en tablas genéricas.
- Si el objetivo de tiempo no es realista para la fecha, dilo con tacto y plantea uno alcanzable.
- Fechas exactas (AAAA-MM-DD). Cada semana empieza en lunes. Incluye también los días de descanso.
- Gimnasio: si el atleta pide días de gimnasio, prográmalos como sesiones "strength" con ejercicios concretos en
  la descripción (series x repeticiones y descanso), orientados a su objetivo de físico (p. ej. definición:
  fuerza-hipertrofia de cuerpo completo, 8-12 repeticiones, básicos más core). Evita pierna pesada las 48 h
  previas a series o a la tirada larga, y en la puesta a punto baja el volumen de gimnasio. Puedes poner
  gimnasio el mismo día que un rodaje suave (indícalo en la descripción). Un día puede tener dos sesiones.
- Progresión en el gimnasio: usa "gimnasio_registrado_por_el_reloj" (series reales con repeticiones y kg).
  Si el atleta completó todas las repeticiones con buena técnica, sube la carga un 2,5-5 % o 1-2 repeticiones;
  si falló, mantén. Indica en cada ejercicio el peso o las repeticiones objetivo concretas basadas en lo último
  que hizo (p. ej. "Press de banca 3x10 con 32,5 kg, la última vez 3x10 con 30 kg"). Si no hay kg registrados,
  pide en la descripción que confirme el peso en el reloj al terminar cada serie.
- Peso: usa "peso_registrado" para valorar la tendencia hacia su objetivo de físico (sin dar dietas).
- Si el objetivo incluye definición, añade en la descripción de alguna sesión un consejo breve y práctico
  (proteína, sueño), sin dietas ni cifras de calorías.
- La memoria son aprendizajes sobre ESTE atleta (cómo responde, qué tolera, sus ritmos reales, sus preferencias).
  Cada aprendizaje en una frase con su dato. No repitas reglas generales de entrenamiento."""


# ======================================================================== estado
def load() -> dict:
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return {}


def save(state: dict) -> None:
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1))
    tmp.replace(STATE)


def _read_data() -> dict:
    from . import SITE_DIR
    raw = (SITE_DIR / "data.js").read_text(encoding="utf-8")
    return json.loads(raw[raw.index("=") + 1:].rstrip().rstrip(";"))


# ======================================================================== perfil del atleta
def _pace_fmt(p):
    if p is None:
        return None
    m = int(p)
    return f"{m}:{round((p - m) * 60):02d}"


def profile(data: dict) -> dict:
    """Nivel real, calculado con tus datos (se recalcula en cada llamada: así el coach aprende)."""
    acts = data["activities"]
    runs = [a for a in acts if a["group"] in ("Correr", "Cinta") and a.get("km")]
    today = date.today()

    def since(days):
        # Últimos `days` días REGISTRADOS: los huecos con el reloj roto no cuentan como parón.
        lim = settings.recorded_start(days, today).isoformat()
        return [a for a in runs if a["start"][:10] >= lim]

    def weekly_km(days):
        return round(sum(a["km"] for a in since(days)) / (days / 7), 1)

    zones = data["profile"].get("zones") or []
    z3 = zones[2] if len(zones) > 2 else 140
    easy = [a["pace"] for a in runs[-60:] if a.get("pace") and a.get("hr") and a["hr"] < z3 and a["km"] >= 4]
    wd = [0] * 7
    for a in runs[-80:]:
        wd[date.fromisoformat(a["start"][:10]).weekday()] += 1
    last = runs[-1] if runs else None
    vo2 = next((a["vo2"] for a in reversed(acts) if a.get("vo2")), None)
    return {
        "hoy": today.isoformat(),
        "km_semana_ultimas_4": weekly_km(28), "km_semana_ultimas_12": weekly_km(84),
        "km_semana_ultimas_26": weekly_km(182),
        "carreras_ultimas_4_semanas": len(since(28)),
        "tirada_mas_larga_8_semanas_km": max((a["km"] for a in since(56)), default=0),
        "tirada_mas_larga_historica_km": max((a["km"] for a in runs), default=0),
        "ultima_carrera": last and {k: last.get(k) for k in ("start", "km", "pace", "hr")},
        "ritmo_suave_real_min_km": _pace_fmt(statistics.median(easy)) if easy else None,
        "vo2max": vo2,
        "predicciones_por_vo2max": data.get("predictions"),
        "mejores_marcas": [r for r in data.get("records", []) if r["group"] == "Carrera"],
        "zonas_pulso_desde_lpm": zones,
        "carreras_por_dia_semana": dict(zip(["lun", "mar", "mié", "jue", "vie", "sáb", "dom"], wd)),
        "preparacion_hoy": data.get("readiness"),
        "forma_ctl": next((d.get("ctl") for d in reversed(data["days"]) if d.get("ctl") is not None), None),
        "semanas": data.get("weeks"),
        "gimnasio_registrado_por_el_reloj": data.get("strength"),
        "peso_registrado": (data.get("weights") or [])[-12:],
        "huecos_sin_reloj": settings.watch_gaps(),
        "nota_huecos": "Los periodos de 'huecos_sin_reloj' NO son parones: el reloj no registraba. Las ventanas "
                       "de km/carreras ya se calculan saltándolos (últimas semanas registradas). No planifiques "
                       "como si volviera de una lesión o de no correr; parte de su nivel registrado.",
    }


# ======================================================================== cumplimiento
def _match(session: dict, acts_by_day: dict) -> dict:
    acts = acts_by_day.get(session["date"], [])
    t = session["type"]
    today = date.today().isoformat()
    if t in RUN_TYPES:
        done = [a for a in acts if a["group"] in ("Correr", "Cinta")]
    elif t == "rest":
        done = []
    else:
        done = [a for a in acts if a["group"] not in ("Correr", "Cinta")] or acts
    km = round(sum(a.get("km") or 0 for a in done), 2)
    mins = round(sum(a.get("min") or 0 for a in done))
    if t == "rest":
        status = "rest"
    elif done:
        planned = session.get("distance_km") or 0
        status = "done" if not planned or km >= 0.75 * planned else "partial"
    elif session["date"] < today:
        status = "missed"
    elif session["date"] == today:
        status = "today"
    else:
        status = "upcoming"
    actual = None
    if done:
        a = max(done, key=lambda x: x.get("km") or x.get("min") or 0)
        actual = {"id": a["id"], "km": km, "min": mins, "pace": a.get("pace"), "hr": a.get("hr"), "name": a.get("name")}
    return {"status": status, "actual": actual}


def with_compliance(state: dict, data: dict) -> dict | None:
    plan = state.get("plan")
    if not plan:
        return None
    by_day: dict[str, list] = {}
    for a in data["activities"]:
        by_day.setdefault(a["start"][:10], []).append(a)
    fb = state.get("feedback", {})
    weeks = []
    for w in plan["weeks"]:
        sessions = []
        for s in w["sessions"]:
            m = _match(s, by_day)
            sessions.append({**s, **m, "feedback": fb.get(s["date"])})
        due = [s for s in sessions if s["status"] in ("done", "partial", "missed")]
        weeks.append({**w, "sessions": sessions,
                      "plannedKm": round(sum(s.get("distance_km") or 0 for s in sessions), 1),
                      "actualKm": round(sum((s["actual"] or {}).get("km", 0) for s in sessions if s["actual"]), 1),
                      "compliance": round(100 * sum(1 if s["status"] == "done" else 0.5 if s["status"] == "partial" else 0
                                                    for s in due) / len(due)) if due else None})
    return {**{k: v for k, v in plan.items() if k != "weeks"}, "weeks": weeks,
            "memory": state.get("memory", []), "history": state.get("history", [])[-6:]}


def today_advice(plan: dict | None, readiness: dict | None) -> dict | None:
    """Consejo del día sin IA: cruza la sesión de hoy con tu preparación."""
    if not plan:
        return None
    today = date.today().isoformat()
    s = next((s for w in plan["weeks"] for s in w["sessions"] if s["date"] == today), None)
    if not s:
        return None
    score = (readiness or {}).get("score")
    hard = s["type"] in ("tempo", "intervals", "long", "race")
    if score is None:
        tip = None
    elif s["type"] == "rest":
        tip = "Hoy toca descanso: aprovecha para dormir bien." if score < 60 else "Hoy descansas. Tu cuerpo está bien; mañana lo notarás."
    elif hard and score < 40:
        tip = f"Tu preparación es {score}: cambia esta sesión por 30-40 min muy suaves o descansa. La moveremos en el próximo ajuste."
    elif hard and score < 60:
        tip = f"Tu preparación es {score}: haz la sesión, pero quédate en la parte baja de los ritmos y corta si notas las piernas pesadas."
    elif score >= 80:
        tip = f"Tu preparación es {score}: día ideal para esta sesión."
    else:
        tip = f"Tu preparación es {score}: adelante con la sesión tal como está."
    return {"session": s, "tip": tip}


# ======================================================================== IA
def _client():
    key = ai._api_key()
    if not key:
        raise RuntimeError("No hay clave de Anthropic configurada.")
    return anthropic.Anthropic(api_key=key, max_retries=2, timeout=600)


def _call(schema, prompt: str, kind: str):
    client = _client()
    model = ai.pick_model(MODEL)
    extra = ai.FALLBACKS if model != ai.MODEL else {}
    try:
        with client.beta.messages.stream(
            model=model, max_tokens=48000, output_config={"effort": "high"}, system=SYSTEM,
            messages=[{"role": "user", "content": prompt}], output_format=schema, **extra,
        ) as stream:
            resp = stream.get_final_message()
    except (anthropic.APIStatusError, anthropic.APIConnectionError):
        raise
    except Exception as e:  # corte a mitad de la respuesta (red, suspensión del equipo...)
        raise RuntimeError("Se cortó la conexión con la IA mientras escribía el plan. Inténtalo de nuevo.") from e
    cost = ai._log_usage(resp, kind, model)
    if resp.stop_reason == "refusal":
        raise RuntimeError("La IA no ha podido generar el plan.")
    if resp.stop_reason == "max_tokens":
        raise RuntimeError("El plan es demasiado largo; prueba con una fecha más cercana.")
    text = "".join(b.text for b in resp.content if b.type == "text")
    try:
        return schema.model_validate_json(text), cost
    except ValidationError as e:
        raise RuntimeError("La respuesta de la IA no tenía el formato esperado.") from e


def create(req: dict) -> dict:
    data = _read_data()
    race_date = date.fromisoformat(req["date"])
    today = date.today()
    if race_date <= today + timedelta(days=13):
        raise RuntimeError("La fecha tiene que estar al menos a dos semanas vista.")
    if race_date > today + timedelta(weeks=30):
        raise RuntimeError("Elige una fecha a menos de 30 semanas.")
    monday = today - timedelta(days=today.weekday())
    goal = {
        "objetivo": req.get("goal", "Media maratón"), "fecha_carrera": req["date"],
        "tiempo_objetivo": req.get("goalTime") or None, "dias_por_semana": int(req.get("daysPerWeek", 4)),
        "dia_tirada_larga": req.get("longRunDay", "domingo"), "notas_del_atleta": (req.get("notes") or "")[:600],
        "dias_gimnasio": int(req.get("gymDays", 0) or 0),
        "objetivo_fisico": (req.get("bodyGoal") or "")[:200] or None,
        "primer_lunes_del_plan": monday.isoformat(),
        "semanas": (race_date - monday).days // 7 + 1,
    }
    state = load()
    prompt = ("Crea un plan de entrenamiento completo, semana a semana, desde el primer lunes hasta la carrera.\n\n"
              f"OBJETIVO:\n{json.dumps(goal, ensure_ascii=False)}\n\n"
              f"PERFIL REAL DEL ATLETA (calculado de sus datos de Garmin):\n{json.dumps(profile(data), ensure_ascii=False)}\n\n"
              f"MEMORIA PREVIA DEL COACH:\n{json.dumps(state.get('memory', []), ensure_ascii=False)}")
    out, cost = _call(PlanOut, prompt, "plan-create")
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    state.update({
        "plan": {"goal": goal["objetivo"], "raceDate": req["date"], "goalTime": goal["tiempo_objetivo"],
                 "daysPerWeek": goal["dias_por_semana"], "longRunDay": goal["dia_tirada_larga"], "notes": goal["notas_del_atleta"],
                 "gymDays": goal["dias_gimnasio"], "bodyGoal": goal["objetivo_fisico"],
                 "createdAt": now, "updatedAt": now, "summary": out.summary,
                 "weeks": [w.model_dump() for w in out.weeks]},
        "memory": out.memory[:12],
        "lastAdaptWeek": monday.isoformat(),
        "history": state.get("history", []) + [{"at": now, "kind": "create", "message": out.summary, "cost": round(cost, 4)}],
    })
    save(state)
    log.info("Plan creado (%d semanas, %.3f $)", len(out.weeks), cost)
    return state


def adapt(force: bool = False, data: dict | None = None) -> dict | None:
    """Reajuste semanal: lo lanza el cron el lunes (o el botón de la web)."""
    state = load()
    plan = state.get("plan")
    if not plan:
        return None
    today = date.today()
    monday = (today - timedelta(days=today.weekday())).isoformat()
    if not force and state.get("lastAdaptWeek") == monday:
        return state
    if plan["raceDate"] < today.isoformat():
        return state
    data = data or _read_data()
    full = with_compliance(state, data)
    past = [w for w in full["weeks"] if w["start"] < monday][-3:]
    future = [w for w in plan["weeks"] if w["start"] >= monday]
    prompt = ("Revisa cómo ha ido el plan y reajusta desde esta semana hasta la carrera. Mantén lo que funciona;"
              " cambia lo que los datos pidan (sesiones no hechas, cansancio, HRV baja, ritmos reales distintos).\n\n"
              f"OBJETIVO: {json.dumps({k: plan.get(k) for k in ('goal', 'raceDate', 'goalTime', 'daysPerWeek', 'longRunDay', 'notes', 'gymDays', 'bodyGoal')}, ensure_ascii=False)}\n\n"
              f"ÚLTIMAS SEMANAS (planificado frente a hecho, con tu valoración):\n{json.dumps(past, ensure_ascii=False)}\n\n"
              f"SEMANAS QUE QUEDAN (plan actual):\n{json.dumps(future, ensure_ascii=False)}\n\n"
              f"PERFIL REAL ACTUALIZADO:\n{json.dumps(profile(data), ensure_ascii=False)}\n\n"
              f"MEMORIA DEL COACH (actualízala):\n{json.dumps(state.get('memory', []), ensure_ascii=False)}\n\n"
              f"Esta semana empieza el {monday}.")
    out, cost = _call(AdaptOut, prompt, "plan-adapt")
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    kept = [w for w in plan["weeks"] if w["start"] < monday]
    plan.update({"weeks": kept + [w.model_dump() for w in out.weeks], "updatedAt": now})
    state.update({"plan": plan, "memory": out.memory[:12], "lastAdaptWeek": monday,
                  "history": state.get("history", []) + [{"at": now, "kind": "adapt", "message": out.message, "cost": round(cost, 4)}]})
    save(state)
    log.info("Plan reajustado (%.3f $)", cost)
    return state


def feedback(day: str, rating: int, note: str = "") -> dict:
    state = load()
    state.setdefault("feedback", {})[day] = {"rating": max(1, min(5, int(rating))), "note": note[:300],
                                             "at": datetime.now().astimezone().isoformat(timespec="seconds")}
    save(state)
    return state


def delete() -> None:
    state = load()
    if state.get("plan"):
        state.setdefault("archive", []).append(state["plan"])
        state["plan"] = None
    save(state)


def view(data: dict | None = None) -> dict:
    """Lo que necesita la web: plan con cumplimiento, consejo de hoy y memoria."""
    data = data or _read_data()
    state = load()
    full = with_compliance(state, data)
    return {"plan": full, "today": today_advice(full, data.get("readiness"))}
