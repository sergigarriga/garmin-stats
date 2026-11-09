"""Textos de la web escritos por Claude con tono Google Health.

Barato por diseño:
- Claude Haiku 5.5 (0,10 $ / 0,50 $ por millón de tokens) con un resumen compacto (~3k tokens).
- Solo se llama cuando cambian los datos importantes (última noche, última actividad o día),
  y como mucho MAX_CALLS_PER_DAY veces al día. El resultado se guarda en data/ai_cache.json.
- Si la API falla (sin saldo, sin red...), se reutiliza el último resultado o la web usa
  los textos por reglas.
"""

from __future__ import annotations

import hashlib
import os
import json
import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Literal

import anthropic
from pydantic import BaseModel, Field, ValidationError

from . import DATA_DIR

log = logging.getLogger(__name__)

MODEL = "claude-haiku-5-5"   # modelo de reserva cuando se llega al límite de gasto
PREMIUM = "claude-sonnet-5-5"  # el que se usa normalmente en todo (mitad de precio que Opus)
FALLBACKS = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
PRICE_IN, PRICE_OUT = 0.10 / 1e6, 0.50 / 1e6  # $/token (prompts < 100k tokens)
# $/token por modelo (entrada, salida). Escritura de caché x1,25 y lectura x0,1 sobre la entrada.
PRICES = {
    "claude-haiku-5-5": (0.10 / 1e6, 0.50 / 1e6),
    "claude-sonnet-5-5": (2.0 / 1e6, 10.0 / 1e6),
    "claude-opus-5-5": (4.0 / 1e6, 20.0 / 1e6),
}
MONTHLY_BUDGET = 50.0   # $ al mes (por defecto; en AWS cada usuaria tiene el suyo en GARMIN_STATS_AI_BUDGET)
SAFE_LIMIT = 40.0       # al llegar aquí, chat y plan pasan a Haiku (80 % del tope)
MAX_CALLS_PER_DAY = 3
SCHEMA_VERSION = 3  # súbelo al cambiar los campos de Insights: fuerza una regeneración por persona
KEY_FILE = Path("~/.config/anthropic/garmin-stats-key").expanduser()
CACHE = DATA_DIR / "ai_cache.json"
# El PC escribe ai_usage.log y AWS Lambda ai_usage_lambda.log; los resúmenes leen los dos.
USAGE_LOG = DATA_DIR / os.environ.get("GARMIN_STATS_USAGE_LOG", "ai_usage.log")

Category = Literal["activity", "heart", "sleep", "stress", "recovery", "energy", "training"]


class Card(BaseModel):
    category: Category
    tone: Literal["positive", "neutral", "attention"]
    title: str = Field(description="Titular breve, máx. 45 caracteres")
    body: str = Field(description="1-2 frases, máx. 230 caracteres, con un dato y una acción concreta")


class Insights(BaseModel):
    headline: str = Field(description="Una frase de bienvenida sobre cómo vas hoy, máx. 110 caracteres")
    today: list[Card] = Field(description="Exactamente 3 tarjetas, de lo más importante a lo menos")
    sleep: list[str] = Field(description="2-3 observaciones sobre el sueño")
    heart: list[str] = Field(description="2-3 observaciones sobre corazón, HRV, estrés y Body Battery")
    activity: list[str] = Field(description="1-2 observaciones sobre pasos y minutos de intensidad")
    training: list[str] = Field(description="2-3 observaciones sobre entreno y carrera")
    weekly_focus: str = Field(description="El objetivo principal para esta semana, una frase")
    analysis: list[str] = Field(description="2-3 conclusiones sencillas sobre qué influye en qué (de 'relations'), "
                                            "en lenguaje de calle, con el dato de cada una y sin hablar de correlaciones ni ρ")
    last_workout: str = Field(description="Tarjeta 'Tu último entreno' (de 'last_activity'): análisis técnico de 4-5 frases, "
                                          "máx. 560 caracteres, para alguien que entrena en serio. Usa los datos que haya: "
                                          "1) cómo fue frente a 'similar_recent' con cifras (ritmo, pulso, km, carga); "
                                          "2) intensidad real: reparto de minutos por zona ('minutes_by_zone_1_to_5', con los lpm de 'hr_zones' si están) "
                                          "y si fue suave, de umbral o de calidad; "
                                          "3) eficiencia: deriva cardiaca ('dec', % que sube el pulso a igual ritmo: <5 % buena base aeróbica, >8 % fatiga, calor o falta de fondo), "
                                          "eficiencia aeróbica ('ef', metros por latido, compárala con 'similar_recent'), cadencia y desnivel si son relevantes; "
                                          "4) qué significa para la carga ('load_now': acwr) y qué hacer en las próximas 24-48 h. "
                                          "Términos técnicos sí, pero cada uno con su cifra y entendible (di 'deriva cardiaca del 4 %', no solo 'dec'). "
                                          "En caminatas o fuerza, adapta: pulso y zonas, desnivel, series y ejercicios. "
                                          "Si no hay entrenos parecidos (count 0), no lo menciones. Km con un decimal. Sin inventar datos que no estén. "
                                          "Esta tarjeta sí puede hablar de un entreno de hoy.")
    data_note: str = Field(description="Una o dos frases amables sobre cuántos datos hay (de 'coverage'): desde cuándo "
                                       "registras, qué parte de los días llevas el reloj y si falta algún mes reciente")


SYSTEM = """Eres el redactor de una app personal de salud con el tono de Google Health / Fitbit.
Escribes en castellano de España, tuteando, con frases cortas y claras.
Usa lenguaje neutro en cuanto al género de la persona (la app la usan hombres y mujeres): no uses adjetivos ni participios que concuerden con ella (en vez de "estás cansado" o "estás lista", di "tienes fatiga", "tu cuerpo está listo" o "llegas con energía").

Tono:
- Cercano, tranquilo y motivador. Reconoce lo que va bien antes de lo que hay que mejorar.
- Concreto: cita el dato que sostiene cada frase (horas, lpm, ms, km, %) y propone una acción pequeña y realista.
- Sin alarmismo, sin diagnósticos médicos, sin culpar. Si algo es preocupante, sugiere observarlo o consultarlo.
- Sin emojis, sin markdown, sin signos de exclamación seguidos. Sin saludos ligados a la hora ("buenos días", "buenas noches"): el texto se lee a cualquier hora.

Reglas:
- Usa solo los datos del JSON. No inventes cifras, tendencias ni causas que no estén ahí.
- Si un dato falta o es antiguo (el reloj no se ha llevado), dilo con naturalidad o no lo menciones.
- Las correlaciones no prueban causa: habla de "suele coincidir", no de "provoca".
- Números con coma decimal (59,5 ms). Duraciones siempre como "5 h 38 min" (nunca "05:38"); la hora del reloj sí como 01:47.
- El día de hoy está a medias: no comentes los pasos, la actividad, las calorías ni el estrés de hoy. Habla de la última noche, del último día completo (ayer) y de las medias. Los textos tienen que seguir siendo ciertos al final del día."""


def _api_key() -> str | None:
    try:
        return KEY_FILE.read_text().strip() or None
    except OSError:
        return None


def _summary(data: dict) -> dict:
    """Resumen compacto para el prompt (unos pocos miles de tokens)."""
    days = data["days"]

    def avg(key, n, offset=0):
        rows = days[len(days) - n - offset: len(days) - offset] if n + offset <= len(days) else days
        vals = [d[key] for d in rows if d.get(key) is not None]
        return round(sum(vals) / len(vals), 1) if vals else None

    def last(key):
        for d in reversed(days):
            if d.get(key) is not None:
                return {"date": d["d"], "value": d[key]}
        return None

    def hm(h):
        if h is None:
            return None
        m = round(h * 60)
        return f"{m // 60} h {m % 60:02d} min"

    metrics = ["steps", "rhr", "hrv", "sleepH", "sleepScore", "stress", "bbMax", "bbMin", "imMod", "imVig", "ctl", "acwr"]
    trends = {k: {"7d": avg(k, 7), "30d": avg(k, 30), "prev30d": avg(k, 30, 30), "90d": avg(k, 90)} for k in metrics}
    for k in ("sleepH",):
        trends[k] = {p: hm(v) for p, v in trends[k].items()}
    night = next((d for d in reversed(days) if d.get("sleepH") is not None), None)
    if night:
        night = {**night, **{k: hm(night.get(k)) for k in ("sleepH", "deepH", "remH", "lightH", "awakeH")}}
    yesterday = days[-2] if len(days) > 1 else None
    acts = data["activities"][-8:]
    return {
        "last_activity": _last_activity(data["activities"], data.get("profile"), days),
        "today": date.today().isoformat(),
        "now": datetime.now().strftime("%H:%M"),
        "yesterday_complete": yesterday and {k: yesterday.get(k) for k in ("d", "steps", "stepGoal", "rhr", "stress", "bbMax", "bbMin", "imMod", "imVig")},
        "profile": {k: v for k, v in data["profile"].items() if k in ("age", "fitness_age", "max_hr", "rest_hr")},
        "latest": {k: last(k) for k in metrics + ["bed", "wake"]},
        "last_night": night and {k: night.get(k) for k in ("d", "sleepH", "deepH", "remH", "lightH", "awakeH", "sleepScore", "bed", "wake", "hrv", "hrvLow", "hrvHigh")},
        "trends": trends,
        "recent_activities": [{k: a.get(k) for k in ("start", "group", "name", "km", "min", "pace", "hr", "trimp", "vo2")} for a in acts],
        "predictions": data.get("predictions"),
        "now_from_watch": {k: v for k, v in (data.get("live") or {}).items() if not k.endswith("Series")} or None,
        "now_note": "now_from_watch = lo último que ha mandado el reloj hoy (asOf = hora). bbNow es la Body Battery "
                    "actual; bbMax es el máximo del día (por la mañana). Si hablas de la energía de ahora, usa bbNow.",
        "how_they_feel": __import__("garmin_stats.wellness", fromlist=["x"]).for_coach(),
        "rule_based_findings": data["insights"],
        "coverage": data.get("coverage"),
        "huecos_sin_reloj": __import__("garmin_stats.settings", fromlist=["x"]).watch_gaps(),
        "nota_huecos": "En 'huecos_sin_reloj' el reloj estaba roto: no hables de parón ni de falta de entreno en ese periodo.",
        "relations": [r for r in data["relations"] if r.get("rho") is not None and abs(r["rho"]) >= 0.2],
        "notes": "bed = horas desde mediodía (13,8 = 01:48). wake = hora del reloj (7,9 = 07:54). "
                 "imVig cuenta doble para el objetivo OMS de 150 min/semana. ctl = forma (carga media 42 d), "
                 "acwr = carga 7 d / 28 d (seguro 0,8-1,3).",
    }


def _last_activity(acts: list[dict], profile: dict | None = None, days: list[dict] | None = None) -> dict | None:
    """El último entreno con más detalle y la media de los parecidos (mismo deporte, 90 días antes) para comparar."""
    if not acts:
        return None
    a = acts[-1]
    keys = ("start", "group", "name", "km", "min", "pace", "hr", "hrMax", "trimp", "ef", "dec", "vo2", "cad", "elev", "cal", "pr", "swolf")
    out = {k: a.get(k) for k in keys if a.get(k) is not None}
    if a.get("z"):
        out["minutes_by_zone_1_to_5"] = a["z"]
    if a.get("sets"):
        out["sets"] = len(a["sets"])
        out["exercises"] = sorted({x.get("ex") for x in a["sets"] if x.get("ex")})[:8]
    start = (a.get("start") or "")[:10]
    try:
        since = (date.fromisoformat(start) - timedelta(days=90)).isoformat()
    except ValueError:
        since = ""
    same = [x for x in acts[:-1] if x.get("group") == a.get("group") and (x.get("start") or "")[:10] >= since]

    def avg(k):
        vals = [x[k] for x in same if x.get(k) is not None]
        return round(sum(vals) / len(vals), 2) if vals else None

    out["similar_recent"] = {"count": len(same), **{k: avg(k) for k in ("km", "min", "pace", "hr", "trimp", "ef", "dec", "cad")}}
    zones = (profile or {}).get("zones")
    if zones:
        out["hr_zones"] = {"floors_bpm_z1_to_z5": zones, "max_hr": (profile or {}).get("max_hr")}
    load = next((d for d in reversed(days or []) if d.get("acwr") is not None), None)
    if load:
        out["load_now"] = {k: load.get(k) for k in ("d", "acwr", "atl", "ctl", "tsb")}
    out["note"] = ("pace = minutos por km (5,5 = 5:30 /km); similar_recent = media del mismo deporte en los 90 días anteriores; "
                   "ef = metros por latido; dec = deriva cardiaca en %; acwr = carga 7 días / carga 28 días (0,8-1,3 seguro, >1,5 riesgo).")
    return out


def _fingerprint(data: dict) -> str:
    """Cambia solo cuando hay algo nuevo que comentar: día, última noche o última actividad."""
    days = data["days"]
    night = next((d["d"] for d in reversed(days) if d.get("sleepH") is not None), None)
    act = data["activities"][-1]["id"] if data["activities"] else None
    return hashlib.sha256(json.dumps([SCHEMA_VERSION, date.today().isoformat(), night, act]).encode()).hexdigest()[:16]


def _load_cache() -> dict:
    try:
        return json.loads(CACHE.read_text())
    except (OSError, ValueError):
        return {}


def generate(data: dict, force: bool = False, offline: bool = False) -> dict | None:
    """Devuelve el bloque `ai` para data.js (nuevo o de caché), o None si nunca se ha generado.
    offline=True: no llama a la API, solo devuelve la caché."""
    cache = _load_cache()
    if offline:
        return cache.get("result")
    fp = _fingerprint(data)
    today = date.today().isoformat()
    calls_today = cache.get("calls", {}).get(today, 0)
    if not force and cache.get("fingerprint") == fp:
        return cache.get("result")
    if not force and calls_today >= MAX_CALLS_PER_DAY:
        log.info("IA: límite de %d llamadas/día alcanzado, uso la caché", MAX_CALLS_PER_DAY)
        return cache.get("result")
    key = _api_key()
    if not key:
        log.info("IA: sin clave en %s, uso textos por reglas", KEY_FILE)
        return cache.get("result")
    if over_budget():
        log.info("IA: tope de %.2f $ de este mes alcanzado, uso la caché", budget())
        return cache.get("result")

    client = anthropic.Anthropic(api_key=key, max_retries=2, timeout=60)
    prompt = ("Estos son mis datos de Garmin (JSON). Escribe los textos de la app.\n\n"
              + json.dumps(_summary(data), ensure_ascii=False, separators=(",", ":")))
    try:
        model = pick_model(PREMIUM)
        resp = client.beta.messages.parse(
            model=model, **(FALLBACKS if model != MODEL else {}),
            max_tokens=16000,
            output_config={"effort": "low"},  # redactar con datos dados: no necesita pensar mucho
            system=SYSTEM,
            messages=[{"role": "user", "content": prompt}],
            output_format=Insights,
        )
    except anthropic.AuthenticationError:
        log.warning("IA: clave no válida (%s)", KEY_FILE)
        return cache.get("result")
    except anthropic.BadRequestError as e:
        log.warning("IA: petición rechazada: %s", str(e.message)[:160])
        return cache.get("result")
    except (anthropic.APIStatusError, anthropic.APIConnectionError) as e:
        log.warning("IA: error temporal (%s), uso la caché", type(e).__name__)
        return cache.get("result")
    except ValidationError:
        log.warning("IA: respuesta con formato inválido, uso la caché")
        return cache.get("result")

    # Toda respuesta 200 se cobra: se apunta siempre, aunque luego no sirva.
    cost = _log_usage(resp, "textos", model)
    stamp = datetime.now().astimezone().isoformat(timespec="seconds")
    u = resp.usage

    cache.setdefault("calls", {})[today] = calls_today + 1
    cache["calls"] = {k: v for k, v in cache["calls"].items() if k >= today[:8]}  # solo este mes
    if resp.stop_reason in ("refusal", "max_tokens") or resp.parsed_output is None:
        log.warning("IA: respuesta incompleta (%s), uso la caché", resp.stop_reason)
        CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1))
        return cache.get("result")

    result = {
        "model": MODEL,
        "generatedAt": stamp,
        **resp.parsed_output.model_dump(),
        # A qué entreno se refiere last_workout: la web solo lo enseña si sigue siendo el último
        "last_workout_id": data["activities"][-1]["id"] if data["activities"] else None,
    }
    cache.update({"fingerprint": fp, "result": result})
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1))
    log.info("IA: textos nuevos (%d+%d tokens, %.4f $)", u.input_tokens, u.output_tokens, cost)
    return result


def usage() -> dict:
    """Resumen del gasto en IA a partir de data/ai_usage.log (solo llamadas que han funcionado;
    las rechazadas no se cobran)."""
    calls = []
    lines = sorted(line for f in DATA_DIR.glob("ai_usage*.log") for line in f.read_text().splitlines() if line.strip())
    try:
        for line in lines:
            parts = dict(p.split("=", 1) for p in line.split()[1:] if "=" in p)
            calls.append({"at": line.split()[0], "in": int(parts.get("in", 0)), "out": int(parts.get("out", 0)),
                          "cost": float(parts.get("cost", "$0").lstrip("$")), "kind": parts.get("kind", "textos"),
                          "model": parts.get("model", MODEL)})
    except OSError:
        pass
    by_day: dict[str, dict] = {}
    for c in calls:
        d = by_day.setdefault(c["at"][:10], {"day": c["at"][:10], "calls": 0, "cost": 0.0})
        d["calls"] += 1
        d["cost"] += c["cost"]
    kinds: dict[str, dict] = {}
    for c in calls:
        k = kinds.setdefault((c["kind"], c["model"]), {"kind": c["kind"], "calls": 0, "cost": 0.0, "model": c["model"]})
        k["calls"] += 1
        k["cost"] = round(k["cost"] + c["cost"], 5)
        k["model"] = c["model"]
    month = date.today().isoformat()[:7]
    return {
        "model": MODEL,
        "byKind": sorted(kinds.values(), key=lambda x: -x["cost"]),
        "monthCostUsd": round(sum(c["cost"] for c in calls if c["at"].startswith(month)), 4),
        "monthlyBudgetUsd": budget(), "safeLimitUsd": safe_limit(),
        "calls": len(calls),
        "inputTokens": sum(c["in"] for c in calls),
        "outputTokens": sum(c["out"] for c in calls),
        "costUsd": round(sum(c["cost"] for c in calls), 5),
        "first": calls[0]["at"] if calls else None,
        "last": calls[-1]["at"] if calls else None,
        "avgCostUsd": round(sum(c["cost"] for c in calls) / len(calls), 5) if calls else None,
        "maxCallsPerDay": MAX_CALLS_PER_DAY,
        "byDay": [{**d, "cost": round(d["cost"], 5)} for d in sorted(by_day.values(), key=lambda x: x["day"])][-60:],
    }


# ======================================================================== resumen semanal
class Weekly(BaseModel):
    title: str = Field(description="Titular de la semana, máx. 70 caracteres")
    went_well: list[str] = Field(description="1-3 cosas que fueron bien, con su dato")
    worse: list[str] = Field(description="0-2 cosas que empeoraron frente a la semana anterior, con su dato, sin culpar")
    goal: str = Field(description="Un objetivo concreto y alcanzable para esta semana")


WEEKLY_SYSTEM = SYSTEM + """

Ahora escribes el resumen de la semana pasada (lunes a domingo) comparándola con la anterior.
Si la semana tiene pocos días con reloj (daysWorn < 4), dilo y sé prudente con las conclusiones."""


def weekly(data: dict, offline: bool = False) -> dict | None:
    """Una llamada por semana como mucho: cuando cambia la última semana completa."""
    weeks = data.get("weeks") or {}
    last, prev = weeks.get("last"), weeks.get("previous")
    if not last:
        return None
    cache = _load_cache()
    w = cache.get("weekly") or {}
    stats = {"last": last, "previous": prev}
    if w.get("week") == last["start"] or offline:
        return {**w.get("result", {}), **stats} if w.get("result") else ({"week": last["start"], **stats} if last else None)
    if (last.get("daysWorn") or 0) < 2:
        return {"week": last["start"], **stats}
    key = _api_key()
    if not key:
        return {"week": last["start"], **stats}
    if over_budget():
        return {"week": last["start"], **stats}
    client = anthropic.Anthropic(api_key=key, max_retries=2, timeout=60)
    try:
        model = pick_model(PREMIUM)
        resp = client.beta.messages.parse(
            model=model, **(FALLBACKS if model != MODEL else {}),
            max_tokens=12000, output_config={"effort": "low"}, system=WEEKLY_SYSTEM,
            messages=[{"role": "user", "content": "Semana pasada frente a la anterior (JSON):\n"
                       + json.dumps(stats, ensure_ascii=False, separators=(",", ":"))}],
            output_format=Weekly,
        )
    except (anthropic.APIStatusError, anthropic.APIConnectionError, ValidationError) as e:
        log.warning("IA semanal: %s", type(e).__name__)
        return {**w.get("result", {}), **stats} if w.get("result") else {"week": last["start"], **stats}
    _log_usage(resp, "weekly", model)
    if resp.parsed_output is None:
        return {"week": last["start"], **stats}
    result = {"week": last["start"], "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
              **resp.parsed_output.model_dump()}
    cache["weekly"] = {"week": last["start"], "result": result}
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1))
    log.info("IA semanal: resumen nuevo de la semana del %s", last["start"])
    return {**result, **stats}


def _log_usage(resp, kind: str, model: str = MODEL) -> float:
    """Apunta el coste real: tokens normales + escritura de caché (x1,25) + lectura de caché (x0,1)."""
    p_in, p_out = PRICES.get(model, (PRICE_IN, PRICE_OUT))
    u = resp.usage
    created = getattr(u, "cache_creation_input_tokens", 0) or 0
    read = getattr(u, "cache_read_input_tokens", 0) or 0
    tokens_in = u.input_tokens + created + read
    cost = (u.input_tokens + 1.25 * created + 0.1 * read) * p_in + u.output_tokens * p_out
    stamp = datetime.now().astimezone().isoformat(timespec="seconds")
    with USAGE_LOG.open("a") as f:
        f.write(f"{stamp} in={tokens_in} out={u.output_tokens} cost=${cost:.5f} stop={resp.stop_reason} kind={kind} model={model}\n")
    return cost


def month_spend() -> float:
    """Gasto de este mes según el registro."""
    month = date.today().isoformat()[:7]
    total = 0.0
    try:
        for line in (l for f in DATA_DIR.glob("ai_usage*.log") for l in f.read_text().splitlines()):
            if line.startswith(month):
                for p in line.split():
                    if p.startswith("cost=$"):
                        total += float(p[6:])
    except OSError:
        pass
    return total


def budget() -> float:
    """Tope de gasto en IA de este mes para la usuaria actual."""
    try:
        return float(os.environ.get("GARMIN_STATS_AI_BUDGET") or MONTHLY_BUDGET)
    except ValueError:
        return MONTHLY_BUDGET


def safe_limit() -> float:
    return round(budget() * 0.8, 2)


def over_budget() -> bool:
    """Tope del mes alcanzado: no se llama más a la IA hasta el mes que viene."""
    return month_spend() >= budget()


def pick_model(preferred: str) -> str:
    """El modelo bueno mientras el mes esté por debajo del 80 % del tope; si no, Haiku."""
    return preferred if month_spend() < safe_limit() else MODEL
