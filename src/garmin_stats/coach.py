"""Entrenador con IA: crea un plan, lo compara con lo que haces y lo reajusta cada semana.

Se vuelve más listo con el tiempo porque guarda en data/coach.json:
- el plan vigente y su historial de ajustes,
- tu valoración de cada sesión (1-5 y una nota),
- una "memoria" de lo que ha aprendido de ti, que la IA lee y actualiza en cada ajuste.

Modelo: Claude Sonnet 5.5 para crear y reajustar (el mismo para todas las personas), con
alternativas automáticas del servidor si un modelo rechazara la petición.
"""

from __future__ import annotations

import json
import os
import logging
import statistics
from datetime import date, datetime, timedelta
from typing import Literal

import anthropic
from pydantic import BaseModel, Field, ValidationError

from . import DATA_DIR
from . import ai
from . import food
from . import settings
from . import weather
from . import wellness

log = logging.getLogger(__name__)

class Cancelled(Exception):
    """El usuario ha cancelado la generación del plan."""


# Función que dice si hay que cancelar (la pone la Lambda; consulta S3). None = no se puede cancelar.
CANCEL_CHECK = None

MODEL = "claude-sonnet-5-5"  # plan y reajustes: Sonnet 5.5 para todas (con el tope de gasto cae a Haiku)
STATE = DATA_DIR / "coach.json"
RUN_TYPES = ("easy", "long", "tempo", "intervals", "race")

SessionType = Literal["easy", "long", "tempo", "intervals", "race", "strength", "swim", "cross", "rest"]
PaceRef = Literal["easy", "marathon", "half", "10k", "5k", "threshold", "interval", "repetition"]
DONE_RATIO = 0.85  # al menos el 85 % de lo previsto cuenta como hecha
MAX_TOKENS = 128000  # máximo de Sonnet 5.5 (con streaming); el pensamiento también cuenta


class Step(BaseModel):
    kind: Literal["warmup", "active", "recovery", "cooldown", "rest"]
    duration: Literal["distance", "time", "open"] = Field(description="open = hasta pulsar vuelta")
    value: float | None = Field(description="km si distance, minutos si time, null si open")
    target: Literal["pace", "hr", "open"]
    pace_fast: str | None = Field(description="Ritmo más rápido del rango, 'm:ss' por km (solo si target=pace)")
    pace_slow: str | None = Field(description="Ritmo más lento del rango, 'm:ss' por km (solo si target=pace)")
    hr_low: int | None = Field(description="Pulso mínimo en lpm (solo si target=hr)")
    hr_high: int | None = Field(description="Pulso máximo en lpm (solo si target=hr)")
    pace_ref: PaceRef | None = Field(default=None, description="Ritmo de referencia del atleta en el que se basa el paso "
                                     "(solo si target=pace): así el ritmo se actualiza solo cuando mejora")
    pace_ref_offset_s: int | None = Field(default=None, description="Segundos por km sobre el ritmo de referencia "
                                          "(negativo = más rápido), p. ej. -5; 0 o null si es justo ese ritmo")
    name: str = Field(description="Nombre corto del paso, máx. 15 caracteres, p. ej. 'Calentamiento', '1 km ritmo'")


class Block(BaseModel):
    repeat: int = Field(description="Veces que se repite el bloque (1 = sin repetir)")
    steps: list[Step]


class Session(BaseModel):
    date: str = Field(description="AAAA-MM-DD")
    type: SessionType
    title: str = Field(description="Nombre corto, p. ej. 'Rodaje suave' o '6 x 1 km'")
    distance_km: float | None = Field(description="Distancia prevista en km (null en fuerza o descanso)")
    duration_min: int | None = Field(description="Duración prevista en minutos")
    target: str = Field(description="Ritmo o zona objetivo, p. ej. '5:50-6:10 /km · Z2'")
    description: str = Field(description="Qué hacer, en 1-2 frases claras")
    workout: list[Block] | None = Field(default=None, description="Solo en sesiones de carrera: el entreno estructurado para el "
                                        "reloj (calentamiento, bloques/series, vuelta a la calma) con ritmos o pulso objetivo. "
                                        "null en fuerza, descanso o cruzado.")
    weather_note: str | None = Field(default=None, description="Solo si el tiempo previsto afecta a la sesión: nota corta "
                                     "(máx. 70 caracteres), p. ej. '31 °C por la tarde: sal antes de las 9'. Si no, null.")
    best_time: str | None = Field(default=None, description="Mejor franja para hacerla según la previsión, 'HH:MM-HH:MM' "
                                  "(p. ej. '07:00-09:00'). null si no hay previsión para ese día o da igual.")


class Week(BaseModel):
    start: str = Field(description="Lunes de la semana, AAAA-MM-DD")
    focus: str = Field(description="Objetivo de la semana en pocas palabras")
    sessions: list[Session]


MemoryTopic = Literal["nivel", "ritmos", "marcas", "objetivo", "test", "salud", "estructura", "gimnasio", "peso", "preferencias"]


class MemoryItem(BaseModel):
    topic: MemoryTopic
    title: str = Field(description="Titular de 2-6 palabras, p. ej. 'Ritmo suave real: 6:19 /km'")
    detail: str = Field(description="Detalle en una frase corta (máx. 140 caracteres), con el dato concreto")


class PlanOut(BaseModel):
    summary: str = Field(description="2-3 frases: cómo está planteado el plan y por qué, con tus datos")
    weeks: list[Week]
    memory: list[MemoryItem] = Field(description="Hasta 12 aprendizajes sobre el atleta, uno por tema, cortos y con dato")


class AdaptOut(BaseModel):
    message: str = Field(description="Una sola frase de resumen para el atleta (máx. 160 caracteres)")
    changes: list[str] = Field(description="3-5 viñetas cortas (máx. 110 caracteres cada una): qué ha pasado y qué cambias")
    weeks: list[Week] = Field(description="Las semanas desde la actual hasta el final, completas y actualizadas")
    memory: list[MemoryItem] = Field(description="Memoria actualizada: hasta 12 aprendizajes, quita los que ya no valgan")


SYSTEM = """Eres un entrenador de running con criterio y prudencia, y escribes con el tono de Google Health:
castellano de España, tuteando, claro, motivador y sin alarmismo.
Usa lenguaje neutro en cuanto al género de la persona (la app la usan hombres y mujeres): no uses adjetivos ni participios que concuerden con ella (en vez de "estás cansado" o "estás lista", di "tienes fatiga", "tu cuerpo está listo" o "llegas con energía").

Principios:
- Parte del nivel REAL del atleta (kilómetros de las últimas semanas, tirada más larga reciente, ritmos reales).
  Si viene de un parón, empieza por debajo de lo que hacía antes y reconstruye la base.
- Sube el volumen semanal como mucho un 10 % y mete una semana de descarga cada 3-4 semanas.
- Alrededor del 80 % del tiempo a ritmo suave (Z1-Z2). Como mucho 1-2 sesiones de calidad por semana.
- Respeta los días disponibles y el día preferido para la tirada larga. Los demás días: descanso o fuerza suave.
- Últimas 1-2 semanas antes de la carrera: puesta a punto (menos volumen, algo de ritmo).
- Ritmos objetivo basados en sus ritmos reales y su VO2max, no en tablas genéricas.
- Si el objetivo de tiempo no es realista para la fecha, dilo con tacto y plantea uno alcanzable.
- Nivel de ambición ("ambicion" en el objetivo):
  · "realista" (por defecto): prioriza llegar sano; si el tiempo objetivo no es realista, propón uno alcanzable.
  · "exigente": el atleta quiere un reto y apretar. MANTÉN su tiempo objetivo como meta (no lo rebajes; puedes
    decir con honestidad el margen que ve). Sube el volumen en el límite alto de lo seguro (hasta +12 % semanal),
    pon 2 sesiones de calidad por semana (series de VO2 y umbral/ritmo de carrera), tiradas largas con bloques a
    ritmo objetivo en la fase específica y progresión de cargas en el gimnasio más ambiciosa. Mantén las descargas
    cada 3-4 semanas y respeta la preparación diaria baja. Tono motivador y retador ("vamos a por ello").
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
  (proteína, sueño), sin dietas.
- Comida ("nutricion_7_dias", solo si la persona apunta lo que come en la app): puedes comentar cómo se alimenta para
  entrenar con sus propias cifras (hidratos antes y después de la tirada larga y de las sesiones de calidad, proteína
  por kg, balance medio si come bastante menos de lo que gasta en semanas de carga). Son estimaciones aproximadas.
  Nunca prescribas dietas ni menús, ni hables de comida buena o mala, de culpa o de "quemar" lo comido.
  Si "oculta_calorias" es true, no menciones cifras de calorías. Sin ese bloque, no des cifras de calorías.
- Ritmos de referencia: usa "ritmos_de_referencia" (modelo VDOT de Daniels con su marca o su VO2max) para fijar
  los ritmos: suave para rodajes y tiradas, umbral para tempo, series (interval) para VO2max, etc. Si el ritmo suave
  real del atleta es más lento que el de referencia, respeta el real en los rodajes. En los pasos del entreno
  estructurado rellena pace_ref (y pace_ref_offset_s si hace falta) además de pace_fast/pace_slow.
- Molestias y lesiones ("molestias_y_lesiones"): si hay alguna activa, adapta el plan para no agravarla (menos
  impacto o volumen, sin series ni cuestas si afecta a piernas, alternativas como bici o natación) y dilo en la
  descripción. Intensidad 4-5/5: sin sesiones de calidad hasta que mejore. Si se ha recuperado, vuelve poco a poco.
- Cómo se encuentra ("como_se_encuentra_14_dias"): ánimo bajo o agujetas fuertes varios días seguidos son señal
  de fatiga: baja la carga esa semana.
- Natación: si el atleta nada o lo pide en sus notas, puedes programar sesiones "swim" (distance_km en km, p. ej.
  1.5) con las series en la descripción (p. ej. "8 x 100 m a 2:05/100 m, salida cada 2:30") usando sus zonas de
  "natacion" por 100 m (CSS). Cuenta como sesión cruzada suave para las piernas.
- Gimnasio: mira "gimnasio_series_por_musculo" (series por semana de cada músculo, últimas 4 semanas) y sus récords
  (1RM estimado). Reparte el volumen entre grupos (unas 6-12 series por músculo y semana si el objetivo es fuerza
  e hipertrofia compatible con correr) y usa el 1RM para proponer cargas (p. ej. 3 x 8 al 70-75 % del 1RM).
- Tiempo disponible ("tiempo_disponible_por_dia": minutos que tiene cada fecha; null = sin límite, decides tú;
  0 = ese día no puede entrenar). Si no viene, deduce la disponibilidad de su historial como siempre.
  · La duración total de cada día (duration_min con calentamiento y vuelta a la calma, más el gimnasio si es el mismo
    día) NUNCA puede pasar de los minutos disponibles de esa fecha. 0 minutos → descanso.
  · La tirada larga va a un día con tiempo suficiente: el día preferido si cabe; si no, el día con más tiempo cercano.
  · Si tiene menos tiempo del que pide la progresión, baja la carga con criterio. Prioridad: 1) la sesión de calidad
    clave de la semana, 2) la tirada larga, acortada para que quepa, 3) los rodajes suaves, que son lo primero que se
    acorta o se quita. NUNCA metas el mismo volumen en menos tiempo subiendo la intensidad.
  · Más tiempo disponible no es más volumen: sigue la progresión normal (subidas semanales y descargas de siempre).
- Tiempo previsto ("tiempo_previsto": previsión meteorológica de los días que la tienen; el resto, planifica normal):
  · Calor (sensación ≥ 26 °C o mucha humedad): pon la calidad y la tirada en la franja más fresca ("mejor_franja"),
    por pulso o unos 10-20 s/km más lento según el calor, y recuerda beber.
  · Tormenta, lluvia fuerte, nieve o viento/rachas fuertes: cambia la calidad o la tirada por un día cercano con mejor
    tiempo (manteniendo la alternancia duro/suave y el tiempo disponible) o propón cinta, gimnasio o natación.
  · Frío u oscuridad (antes de amanecer o después de anochecer): menciona ir por capas y la visibilidad (reflectante, luz).
  · En las sesiones afectadas rellena weather_note (corta, concreta) y best_time; en las demás déjalos en null.
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
        "ritmos_de_referencia": _paces_for_ai(data.get("paces")),
        "natacion": _swim_for_ai(data.get("swim")),
        "gimnasio_series_por_musculo": (data.get("gym") or {}).get("muscleAvg4w"),
        "gimnasio_records_1rm": [{"ejercicio": r["ex"], "1rm_estimado_kg": (r.get("best") or {}).get("e1rm"),
                                  "mejor_serie": r.get("best") and f"{r['best']['reps']} x {r['best']['kg']} kg",
                                  "fecha": (r.get("best") or {}).get("d")}
                                 for r in ((data.get("gym") or {}).get("records") or [])[:12]],
        **wellness.for_coach(),
        **({"nutricion_7_dias": nut} if (nut := food.for_coach(data)) else {}),
        "huecos_sin_reloj": settings.watch_gaps(),
        "nota_huecos": "Los periodos de 'huecos_sin_reloj' NO son parones: el reloj no registraba. Las ventanas "
                       "de km/carreras ya se calculan saltándolos (últimas semanas registradas). No planifiques "
                       "como si volviera de una lesión o de no correr; parte de su nivel registrado.",
    }


# ======================================================================== perfil: bloques nuevos
def _paces_for_ai(p: dict | None) -> dict | None:
    if not p:
        return None
    from .training import mmss
    return {"vdot": p["vdot"], "fuente": p["sourceLabel"],
            "ritmos_min_km": {x["key"]: mmss(x["sec"]) for x in p["list"]},
            "rango_suave": f"{mmss(p['easyRange'][0])}-{mmss(p['easyRange'][1])}",
            "zonas_de_ritmo": [f"Z{z['zone']} {z['name']}: {mmss(z['fast'])}-{mmss(z['slow'])}" for z in p["zones"]]}


def _swim_for_ai(s: dict | None) -> dict | None:
    if not s:
        return None
    from .training import mmss
    return {"css_por_100m": mmss(s.get("css")), "fuente_css": {"test": "test 400/200", "estimate": "estimado con su mejor nado"}.get(s.get("cssSource")),
            "zonas_por_100m": [f"Z{z['zone']} {z['name']}: {mmss(z['fast'])}-{mmss(z['slow'])}" for z in s.get("zones") or []],
            "piscina_m": s.get("poolM"), "ultimas_sesiones": (s.get("sessions") or [])[-5:], "totales": s.get("totals")}


# ======================================================================== cumplimiento
def _ratio(actual: float, planned: float | None) -> float | None:
    return round(actual / planned, 2) if planned else None


def _match(session: dict, acts_by_day: dict) -> dict:
    """Estado de una sesión y cuánto se parece lo hecho a lo previsto (distancia, tiempo, ritmo o series)."""
    acts = acts_by_day.get(session["date"], [])
    t = session["type"]
    today = date.today().isoformat()
    if t in RUN_TYPES:
        done = [a for a in acts if a["group"] in ("Correr", "Cinta")]
    elif t == "swim":
        done = [a for a in acts if a["group"] == "Natación"]
    elif t == "strength":
        done = [a for a in acts if a["group"] == "Fuerza" or a.get("type") == "strength_training"] or \
               [a for a in acts if a["group"] not in ("Correr", "Cinta")]
    elif t == "rest":
        done = []
    else:
        done = [a for a in acts if a["group"] not in ("Correr", "Cinta")] or acts
    km = round(sum(a.get("km") or 0 for a in done), 2)
    mins = round(sum(a.get("min") or 0 for a in done))
    comp = None
    status: str
    if t == "rest":
        status = "rest"
    elif done:
        p_km, p_min = session.get("distance_km") or None, session.get("duration_min") or None
        comp = {"distRatio": _ratio(km, p_km), "timeRatio": _ratio(mins, p_min)}
        if t in RUN_TYPES and p_km and p_min and km > 0:
            a_pace = sum((a.get("pace") or 0) * (a.get("km") or 0) for a in done) / km  # min/km medio
            if a_pace:
                comp["paceDeltaS"] = round((a_pace - p_min / p_km) * 60)  # + = más lento que lo previsto
        if t == "strength":
            planned_sets = sum(int(x.get("sets") or 0) for x in session.get("strength") or [])
            done_sets = sum(len(a.get("sets") or []) for a in done)
            if planned_sets and done_sets:
                comp.update(setsDone=done_sets, setsPlanned=planned_sets, setsRatio=round(done_sets / planned_sets, 2))
            main = comp.get("setsRatio")  # sin series del reloj: la sesión registrada cuenta como hecha
        else:
            main = comp["distRatio"] if comp["distRatio"] is not None else comp["timeRatio"]
        status = "done" if main is None or main >= DONE_RATIO else "partial"
        comp = {k: v for k, v in comp.items() if v is not None}
    elif session["date"] < today:
        status = "missed"
    elif session["date"] == today:
        status = "today"
    else:
        status = "upcoming"
    if status in ("missed", "today", "upcoming") and session.get("moved_to"):
        status = "moved"  # se hizo (o se hará) otro día: no cuenta como fallada
    actual = None
    if done:
        a = max(done, key=lambda x: x.get("km") or x.get("min") or 0)
        actual = {"id": a["id"], "km": km, "min": mins, "pace": a.get("pace"), "hr": a.get("hr"), "name": a.get("name")}
    return {"status": status, "actual": actual, "compliance": comp or None}


def with_compliance(state: dict, data: dict) -> dict | None:
    plan = state.get("plan")
    if not plan:
        return None
    by_day: dict[str, list] = {}
    for a in data["activities"]:
        by_day.setdefault(a["start"][:10], []).append(a)
    fb = state.get("feedback", {})
    st = settings.load()
    timed = settings.has_availability(st)
    clash = {c["date"]: c for c in time_conflicts(plan["weeks"], st, since=date.today().isoformat())} if timed else {}
    weeks = []
    for w in plan["weeks"]:
        sessions = []
        for s in w["sessions"]:
            m = _match(s, by_day)
            extra = {}
            if timed:
                extra["availMin"] = settings.available_minutes(s["date"], st)
                c = clash.get(s["date"])
                if c and s["type"] != "rest" and m["status"] in ("today", "upcoming"):
                    extra["timeWarn"] = {"avail": c["avail"], "planned": c["planned"]}
            sessions.append({**s, **m, **extra, "feedback": fb.get(s["date"])})
        due = [s for s in sessions if s["status"] in ("done", "partial", "missed")]
        weeks.append({**w, "sessions": sessions,
                      "plannedKm": round(sum(s.get("distance_km") or 0 for s in sessions), 1),
                      "actualKm": round(sum((s["actual"] or {}).get("km", 0) for s in sessions if s["actual"]), 1),
                      "compliance": round(100 * sum(1 if s["status"] == "done" else 0.5 if s["status"] == "partial" else 0
                                                    for s in due) / len(due)) if due else None})
    return {**{k: v for k, v in plan.items() if k != "weeks"}, "weeks": weeks,
            "memory": state.get("memory", []), "history": state.get("history", [])[-6:]}


def _wellness_tip(s: dict, hard: bool) -> str | None:
    """Aviso por molestias activas o por cómo te encuentras hoy (lo que apuntas en la web)."""
    if s["type"] == "rest":
        return None
    st = wellness.load()
    inj = sorted(wellness.active_injuries(st), key=lambda i: -i.get("severity", 0))
    today = st["log"].get(date.today().isoformat()) or {}
    if inj and inj[0].get("severity", 0) >= 3:
        i = inj[0]
        return (f"Tienes una molestia activa en **{i['area']}** ({i['severity']}/5): "
                + ("cambia esta sesión por algo suave que no duela (bici, natación o descanso)." if hard
                   else "haz la sesión solo si no duele; si aparece dolor, para."))
    if (today.get("soreness") or 0) >= 4 and hard:
        return "Tienes agujetas fuertes: haz la sesión más suave (sin series) o muévela a otro día."
    if inj:
        return f"Ojo con la molestia en {inj[0]['area']}: si aumenta, para y apúntalo."
    if (today.get("mood") or 5) <= 2 and hard:
        return "Hoy no te encuentras bien: escucha a tu cuerpo y no pasa nada por hacerla más suave."
    return None


def today_advice(plan: dict | None, readiness: dict | None) -> dict | None:
    """Consejo del día sin IA: cruza la sesión de hoy con tu preparación, tus molestias y cómo te encuentras."""
    if not plan:
        return None
    today = date.today().isoformat()
    s = next((s for w in plan["weeks"] for s in w["sessions"] if s["date"] == today), None)
    if not s:
        return None
    score = (readiness or {}).get("score")
    if (readiness or {}).get("date") != today:
        score = None  # la preparación de otro día no vale para hoy
    hard = s["type"] in ("tempo", "intervals", "long", "race")
    warn = _wellness_tip(s, hard)
    if warn:
        tip = warn
    elif score is None:
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
    out = {"session": s, "tip": tip}
    try:
        wx = weather.advice(s, [x for w in plan["weeks"] for x in w["sessions"]])
    except Exception as e:  # noqa: BLE001 - el consejo del tiempo nunca rompe el del día
        log.warning("Consejo del tiempo: %s", e)
        wx = None
    if wx:
        out.update(weatherTip=wx["tip"], weather={k: wx["day"].get(k) for k in ("date", "code", "text", "tmin", "tmax", "feelsMax", "rainProb", "windMax")},
                   bestWindow=wx["best"])
    return out


# ======================================================================== tu tiempo y el tiempo que hará
def _dates(first: date, last: date) -> list[str]:
    return [(first + timedelta(days=i)).isoformat() for i in range((last - first).days + 1)]


def _availability_for_ai(dates: list[str]) -> dict | None:
    """{fecha: minutos | null} para cada fecha planificada (el día concreto manda sobre la semana tipo)."""
    st = settings.load()
    if not settings.has_availability(st):
        return None
    return {d: settings.available_minutes(d, st) for d in dates}


def _weather_for_ai(dates: list[str]) -> list[dict] | None:
    try:
        weather.refresh()  # como mucho cada ~3 h; sin red, se usa la última previsión guardada
    except Exception as e:  # noqa: BLE001
        log.warning("Previsión: %s", e)
    return weather.for_coach(dates)


def _context_blocks(dates: list[str]) -> str:
    out = ""
    avail = _availability_for_ai(dates)
    if avail:
        out += ("\n\nTIEMPO DISPONIBLE POR DÍA (minutos; null = sin límite; 0 = no puede entrenar). Cada día tiene que caber:\n"
                + json.dumps({"tiempo_disponible_por_dia": avail}, ensure_ascii=False))
    fc = _weather_for_ai(dates)
    if fc:
        out += ("\n\nTIEMPO PREVISTO (los días con previsión; adapta sesiones y horas, rellena weather_note y best_time):\n"
                + json.dumps({"tiempo_previsto": fc}, ensure_ascii=False))
    return out


def _session_minutes(s: dict) -> int:
    if s.get("duration_min"):
        return int(s["duration_min"])
    return round((s.get("distance_km") or 0) * 6)  # sin duración: ~6 min/km


def time_conflicts(weeks: list[dict], st: dict | None = None, since: str | None = None) -> list[dict]:
    """Comprobación sin IA: días cuyo total previsto pasa de tu tiempo disponible (no nos fiamos a ciegas del modelo)."""
    st = settings.load() if st is None else st
    if not settings.has_availability(st):
        return []
    by_day: dict[str, list] = {}
    for w in weeks:
        for s in w["sessions"]:
            if s.get("type") != "rest" and (since is None or s["date"] >= since):
                by_day.setdefault(s["date"], []).append(s)
    out = []
    for d, ss in sorted(by_day.items()):
        avail = settings.available_minutes(d, st)
        planned = sum(_session_minutes(s) for s in ss)
        if avail is not None and planned > avail:
            out.append({"date": d, "avail": avail, "planned": planned, "titles": [s["title"] for s in ss]})
    return out


# ======================================================================== IA
def _client():
    key = ai._api_key()
    if not key:
        raise RuntimeError("No hay clave de Anthropic configurada.")
    return anthropic.Anthropic(api_key=key, max_retries=2, timeout=600)


def _call(schema, prompt: str, kind: str, model: str | None = None):
    if ai.over_budget():
        raise RuntimeError(f"Has llegado al tope de IA de este mes ({ai.budget():.0f} $). El plan se podrá reajustar el día 1.")
    client = _client()
    model = ai.pick_model(model or MODEL)
    extra = ai.FALLBACKS if model != ai.MODEL else {}
    import threading as _threading
    stop, cancelled = _threading.Event(), _threading.Event()
    try:
        with client.beta.messages.stream(
            # 128K: el pensamiento cuenta dentro de max_tokens y el plan completo (con entrenos) es largo
            model=model, max_tokens=MAX_TOKENS, output_config={"effort": "high"}, system=SYSTEM,
            messages=[{"role": "user", "content": prompt}], output_format=schema, **extra,
        ) as stream:
            # Vigilante: cada 3 s mira si el usuario ha cancelado y, si es así, cierra la conexión aunque la IA
            # esté pensando en silencio (en ese rato no llegan eventos, así que no basta con mirar en el bucle).
            def _watch():
                while not stop.wait(3):
                    if CANCEL_CHECK and CANCEL_CHECK():
                        cancelled.set()
                        try:
                            stream.close()
                        except Exception:  # noqa: BLE001
                            pass
                        return
            if CANCEL_CHECK:
                _threading.Thread(target=_watch, daemon=True).start()
            try:
                for _ in stream:
                    pass
                if cancelled.is_set():
                    raise Cancelled()
                resp = stream.get_final_message()
            except (ValidationError, ValueError) as e:
                # El SDK valida el JSON al acabar el bloque de texto, ANTES de saber el stop_reason: un JSON
                # incompleto es casi siempre una respuesta cortada por max_tokens, no un corte de la conexión.
                if cancelled.is_set():
                    raise Cancelled() from None
                raise RuntimeError("La respuesta de la IA salió incompleta (demasiado larga). "
                                   "Inténtalo de nuevo; si se repite, avísanos.") from e
            except Exception:
                if cancelled.is_set():
                    raise Cancelled() from None
                raise
            finally:
                stop.set()
    except (anthropic.APIStatusError, anthropic.APIConnectionError, Cancelled, RuntimeError):
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
        "ambicion": req.get("ambition") if req.get("ambition") in ("realista", "exigente") else "realista",
        "primer_lunes_del_plan": monday.isoformat(),
        "semanas": (race_date - monday).days // 7 + 1,
    }
    state = load()
    prompt = ("Crea un plan de entrenamiento completo, semana a semana, desde el primer lunes hasta la carrera.\n\n"
              f"OBJETIVO:\n{json.dumps(goal, ensure_ascii=False)}\n\n"
              f"PERFIL REAL DEL ATLETA (calculado de sus datos de Garmin):\n{json.dumps(profile(data), ensure_ascii=False)}\n\n"
              f"MEMORIA PREVIA DEL COACH:\n{json.dumps(state.get('memory', []), ensure_ascii=False)}"
              + _context_blocks(_dates(monday, race_date)))
    out, cost = _call(PlanOut, prompt, "plan-create")
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    weeks = [w.model_dump() for w in out.weeks]
    warns = time_conflicts(weeks, since=today.isoformat())
    state.update({
        "plan": {"goal": goal["objetivo"], "raceDate": req["date"], "goalTime": goal["tiempo_objetivo"],
                 "daysPerWeek": goal["dias_por_semana"], "longRunDay": goal["dia_tirada_larga"], "notes": goal["notas_del_atleta"],
                 "gymDays": goal["dias_gimnasio"], "bodyGoal": goal["objetivo_fisico"], "ambition": goal["ambicion"],
                 "createdAt": now, "updatedAt": now, "summary": out.summary,
                 "weeks": weeks, "timeWarnings": warns},
        "memory": [m.model_dump() for m in out.memory[:12]],
        "lastAdaptWeek": monday.isoformat(),
        "history": state.get("history", []) + [{"at": now, "kind": "create", "message": out.summary, "cost": round(cost, 4),
                                                 **({"timeWarnings": len(warns)} if warns else {})}],
    })
    save(state)
    log.info("Plan creado (%d semanas, %.3f $, %d días que no caben en tu tiempo)", len(out.weeks), cost, len(warns))
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
              f"OBJETIVO: {json.dumps({**{k: plan.get(k) for k in ('goal', 'raceDate', 'goalTime', 'daysPerWeek', 'longRunDay', 'notes', 'gymDays', 'bodyGoal')}, 'ambicion': plan.get('ambition', 'realista')}, ensure_ascii=False)}\n\n"
              f"ÚLTIMAS SEMANAS (planificado frente a hecho, con tu valoración):\n{json.dumps(past, ensure_ascii=False)}\n\n"
              f"SEMANAS QUE QUEDAN (plan actual):\n{json.dumps(future, ensure_ascii=False)}\n\n"
              f"PERFIL REAL ACTUALIZADO:\n{json.dumps(profile(data), ensure_ascii=False)}\n\n"
              f"MEMORIA DEL COACH (actualízala):\n{json.dumps(state.get('memory', []), ensure_ascii=False)}\n\n"
              f"Esta semana empieza el {monday}."
              + _context_blocks(_dates(date.fromisoformat(monday), date.fromisoformat(plan["raceDate"]))))
    # Los reajustes semanales pueden ir con un modelo más barato (GARMIN_STATS_ADAPT_MODEL, p. ej. Sonnet para invitadas)
    out, cost = _call(AdaptOut, prompt, "plan-adapt", os.environ.get("GARMIN_STATS_ADAPT_MODEL") or MODEL)
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    kept = [w for w in plan["weeks"] if w["start"] < monday]
    new = [w.model_dump() for w in out.weeks]
    warns = time_conflicts(new, since=today.isoformat())
    plan.update({"weeks": kept + new, "updatedAt": now, "timeWarnings": warns})
    state.update({"plan": plan, "memory": [m.model_dump() for m in out.memory[:12]], "lastAdaptWeek": monday,
                  "history": state.get("history", []) + [{"at": now, "kind": "adapt", "message": out.message,
                                                          "changes": out.changes[:5], "cost": round(cost, 4),
                                                          **({"timeWarnings": len(warns)} if warns else {})}]})
    save(state)
    log.info("Plan reajustado (%.3f $, %d días que no caben en tu tiempo)", cost, len(warns))
    return state


def feedback(day: str, rating: int, note: str = "") -> dict:
    state = load()
    state.setdefault("feedback", {})[day] = {"rating": max(1, min(5, int(rating))), "note": note[:300],
                                             "at": datetime.now().astimezone().isoformat(timespec="seconds")}
    save(state)
    return state


def _family(t: str) -> str:
    return "run" if t in RUN_TYPES else t


def _today(client_today: str | None) -> str:
    """El día de la persona (la web lo manda en su hora local); si no cuadra con el del servidor (±1 día), el del servidor."""
    srv = date.today()
    try:
        c = date.fromisoformat(client_today or "")
        if abs((c - srv).days) <= 1:
            return c.isoformat()
    except ValueError:
        pass
    return srv.isoformat()


def redo(src_date: str, src_type: str, client_today: str | None = None) -> dict:
    """'Hacerlo hoy': copia un entreno de otro día a hoy. Sustituye lo previsto hoy del mismo tipo (carrera por carrera,
    fuerza por fuerza...) o el descanso; lo sustituido se guarda para poder deshacerlo. El original queda como 'movido'."""
    state = load()
    plan = state.get("plan")
    if not plan:
        raise ValueError("No hay plan.")
    today = _today(client_today)
    if (state.get("redo") or {}).get(today):
        _undo(state, today)  # solo un cambio por día: el nuevo sustituye al anterior
    if src_date == today:
        raise ValueError("Ese entreno ya es de hoy.")
    src = next((x for w in plan["weeks"] for x in w["sessions"] if x["date"] == src_date and x["type"] == src_type), None)
    if not src or src["type"] == "rest":
        raise ValueError("No encuentro ese entreno.")
    week = _week_of(plan, today)
    if not week:
        raise ValueError("Hoy no está dentro del plan.")
    fam = _family(src["type"])
    replaced = [x for x in week["sessions"] if x["date"] == today and (_family(x["type"]) == fam or x["type"] == "rest")]
    copy = {k: v for k, v in json.loads(json.dumps(src)).items() if k not in ("moved_to", "redo_from")}
    copy.update(date=today, redo_from=src_date)
    week["sessions"] = sorted([x for x in week["sessions"] if x not in replaced] + [copy], key=lambda x: x["date"])
    src["moved_to"] = today
    state.setdefault("redo", {})[today] = {"from": src_date, "type": src_type, "replaced": replaced,
                                           "at": datetime.now().astimezone().isoformat(timespec="seconds")}
    save(state)
    log.info("Entreno del %s (%s) pasado a hoy %s", src_date, src_type, today)
    return state


def _week_of(plan: dict, day: str) -> dict | None:
    return next((w for w in plan["weeks"]
                 if w["start"] <= day < (date.fromisoformat(w["start"]) + timedelta(days=7)).isoformat()), None)


def _undo(state: dict, today: str) -> None:
    rec = (state.get("redo") or {}).pop(today, None)
    if not rec:
        return
    for w in state["plan"]["weeks"]:
        for x in w["sessions"]:
            if x["date"] == rec["from"] and x["type"] == rec["type"] and x.get("moved_to") == today:
                x.pop("moved_to", None)
    week = _week_of(state["plan"], today)
    if week:
        keep = [x for x in week["sessions"] if not (x["date"] == today and x.get("redo_from") == rec["from"])]
        week["sessions"] = sorted(keep + rec["replaced"], key=lambda x: x["date"])


def undo_redo(client_today: str | None = None) -> dict:
    """Deshace el 'Hacerlo hoy' de hoy: vuelve lo que estaba previsto."""
    state = load()
    if not state.get("plan"):
        raise ValueError("No hay plan.")
    _undo(state, _today(client_today))
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


# ======================================================================== entrenos para el reloj
class StructuredSession(BaseModel):
    date: str
    title: str
    workout: list[Block]


class StructuredWeek(BaseModel):
    sessions: list[StructuredSession]


STRUCT_SYSTEM = """Conviertes sesiones de carrera de un plan en entrenos estructurados para un reloj Garmin.
Para cada sesión de carrera devuelve bloques con pasos: calentamiento, parte principal (series como bloque con
repeat > 1 que contiene el paso de esfuerzo y el de recuperación) y vuelta a la calma.
- Respeta exactamente las distancias, tiempos y ritmos de la descripción y del objetivo.
- Rodajes suaves y tiradas: un paso por distancia con rango de ritmo, o con pulso si el objetivo es por pulso/zona.
- Ritmos como 'm:ss' por km; el rango de ritmo debe tener 10-20 s de margen.
- Si te paso los ritmos de referencia del atleta, en cada paso con ritmo pon también pace_ref (easy, marathon, half,
  10k, 5k, threshold, interval o repetition) y pace_ref_offset_s (segundos por km sobre ese ritmo, negativo = más
  rápido) que correspondan a lo que pide la sesión.
- Si el objetivo es una zona de pulso, usa las zonas del atleta (lpm) que te paso.
- Nombres de paso cortos, en castellano."""


def structure_week(week_start: str) -> dict:
    """Añade el entreno estructurado a las sesiones de carrera de una semana que aún no lo tengan."""
    state = load()
    plan = state.get("plan")
    if not plan:
        raise RuntimeError("No hay plan.")
    week = next((w for w in plan["weeks"] if w["start"] == week_start), None)
    if not week:
        raise RuntimeError("Semana no encontrada.")
    data = _read_data()
    changed = structure_strength(week, data)
    todo = [s for s in week["sessions"] if s["type"] in RUN_TYPES and not s.get("workout")]
    if not todo:
        if changed:
            save(state)
        return state
    zones = data["profile"].get("zones")
    model = ai.pick_model(ai.PREMIUM)
    extra = ai.FALLBACKS if model != ai.MODEL else {}
    client = _client()
    prompt = (f"Zonas de pulso del atleta (lpm desde Z1..Z5): {zones}\n\n"
              f"Ritmos de referencia del atleta: {json.dumps(_paces_for_ai(data.get('paces')), ensure_ascii=False)}\n\nSesiones:\n"
              + json.dumps([{k: s.get(k) for k in ("date", "type", "title", "distance_km", "duration_min", "target", "description")}
                            for s in todo], ensure_ascii=False))
    resp = client.beta.messages.parse(model=model, max_tokens=12000, output_config={"effort": "low"}, system=STRUCT_SYSTEM,
                                      messages=[{"role": "user", "content": prompt}], output_format=StructuredWeek, **extra)
    ai._log_usage(resp, "plan-structure", model)
    if resp.parsed_output is None:
        raise RuntimeError("No se pudo estructurar la semana.")
    by_key = {(x.date, x.title): x for x in resp.parsed_output.sessions}
    by_date = {x.date: x for x in resp.parsed_output.sessions}
    for s in week["sessions"]:
        if s in todo:
            got = by_key.get((s["date"], s["title"])) or by_date.get(s["date"])
            if got:
                s["workout"] = [b.model_dump() for b in got.workout]
    save(state)
    return state


# ======================================================================== gimnasio para el reloj
from pathlib import Path as _Path
import difflib as _difflib
import re as _re

_CATALOG = json.loads((_Path(__file__).with_name("garmin_exercises.json")).read_text())


class StrengthItem(BaseModel):
    date: str
    label: str = Field(description="Nombre del ejercicio en castellano, corto (máx. 22 caracteres)")
    category: str = Field(description="Categoría de Garmin (una de la lista)")
    garmin_name: str = Field(description="Nombre del ejercicio en inglés, en camelCase, lo más parecido al catálogo de Garmin "
                                         "(p. ej. barbellBenchPress, dumbbellRow, latPulldown, gobletSquat, plank)")
    sets: int
    reps: int = Field(description="Repeticiones por serie; en ejercicios por tiempo (plancha) usa 0 y rellena seconds")
    seconds: int | None = Field(description="Segundos por serie si el ejercicio va por tiempo, si no null")
    weight_kg: float | None = Field(description="Peso por serie en kg si se indica o se deduce del historial, si no null")
    rest_s: int = Field(description="Descanso entre series en segundos")


class StrengthWeek(BaseModel):
    items: list[StrengthItem]


STRENGTH_SYSTEM = """Conviertes sesiones de gimnasio de un plan en una lista de ejercicios para un reloj Garmin.
Para cada ejercicio de cada sesión: categoría de Garmin (de la lista dada), nombre en inglés en camelCase lo más
parecido al catálogo de Garmin, series, repeticiones (o segundos si va por tiempo), peso en kg y descanso.
- Respeta exactamente series, repeticiones, pesos y descansos de la descripción.
- Si no se indica el peso, usa el historial del atleta para ese ejercicio (último peso usado) o déjalo en null.
- No inventes ejercicios que no estén en la descripción. Mantén el orden."""


def _norm(s: str) -> str:
    return _re.sub(r"[^a-z0-9]", "", _re.sub(r"(?<!^)(?=[A-Z])", " ", s).lower())


def _match_exercise(category: str, name: str) -> tuple[int | None, int | None, str | None]:
    cat = _CATALOG.get(category)
    if not cat:
        # categoría parecida (p. ej. "bench_press" → "benchPress")
        keys = {_norm(k): k for k in _CATALOG}
        hit = _difflib.get_close_matches(_norm(category), list(keys), n=1, cutoff=0.6)
        if not hit:
            return None, None, None
        category, cat = keys[hit[0]], _CATALOG[keys[hit[0]]]
    names = {_norm(k): k for k in cat["names"]}
    hit = _difflib.get_close_matches(_norm(name), list(names), n=1, cutoff=0.55)
    if not hit:
        return cat["id"], None, None
    key = names[hit[0]]
    return cat["id"], cat["names"][key], key


def structure_strength(week: dict, data: dict) -> bool:
    todo = [s for s in week["sessions"] if s["type"] == "strength" and not s.get("strength")]
    if not todo:
        return False
    model = ai.pick_model(ai.PREMIUM)
    extra = ai.FALLBACKS if model != ai.MODEL else {}
    prompt = ("Categorías de Garmin disponibles: " + ", ".join(_CATALOG) + "\n\n"
              + "Historial de gimnasio del atleta: " + json.dumps((data.get("strength") or {}).get("por_ejercicio"), ensure_ascii=False)
              + "\n\nSesiones:\n" + json.dumps([{k: s.get(k) for k in ("date", "title", "duration_min", "target", "description")}
                                                  for s in todo], ensure_ascii=False))
    resp = _client().beta.messages.parse(model=model, max_tokens=8000, output_config={"effort": "low"}, system=STRENGTH_SYSTEM,
                                         messages=[{"role": "user", "content": prompt}], output_format=StrengthWeek, **extra)
    ai._log_usage(resp, "plan-structure-gym", model)
    if resp.parsed_output is None:
        raise RuntimeError("No se pudieron preparar las sesiones de gimnasio.")
    by_date: dict[str, list] = {}
    for it in resp.parsed_output.items:
        cat_id, name_id, key = _match_exercise(it.category, it.garmin_name)
        by_date.setdefault(it.date, []).append({
            "label": it.label[:22], "category_id": cat_id, "name_id": name_id, "garmin_key": key,
            "sets": max(1, it.sets), "reps": max(0, it.reps), "seconds": it.seconds, "weight_kg": it.weight_kg,
            "rest_s": max(0, it.rest_s)})
    for s in todo:
        if by_date.get(s["date"]):
            s["strength"] = by_date[s["date"]]
    return True
