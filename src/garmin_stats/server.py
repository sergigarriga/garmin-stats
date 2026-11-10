"""Servidor local: sirve la web (site/) y responde preguntas a la IA en /api/ask.

Solo escucha en 127.0.0.1. La clave de Anthropic se queda en este proceso; el navegador nunca la ve.
Para que otra web no pueda gastar tu saldo llamando a localhost, /api/ask exige la cabecera
X-Garmin-Stats (una web ajena no puede enviarla sin un permiso CORS que aquí nunca se da).
"""

from __future__ import annotations

import json
import os
import logging
import threading
from datetime import date, datetime, timedelta
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import anthropic

from . import SITE_DIR
from . import ai
from . import coach

log = logging.getLogger(__name__)

MAX_QUESTIONS_PER_DAY = 60
CHAT_MODEL = ai.PREMIUM  # Sonnet 5.5; con el tope de gasto pasa a Haiku
_count: dict[str, int] = {}
_lock = threading.Lock()
_plan_lock = threading.Lock()
_ctx_cache: dict = {"key": None, "text": None, "last_day": None}

CHAT_SYSTEM = ai.SYSTEM + """

Ahora respondes preguntas del usuario sobre sus propios datos, como un asistente de Google Health.
- Empieza con la respuesta directa en una frase. Después, el porqué con sus datos y, si ayuda, qué hacer.
- Formato (se muestra bonito en la app): párrafos cortos separados por una línea en blanco, **negrita** solo para
  la idea clave y los datos importantes (2-4 por respuesta), y listas con "- " (o "1. " si el orden importa) de
  3-4 puntos como mucho. Nada de títulos, tablas ni emojis. Máximo unas 150 palabras.
- Para preguntas por días de la semana, meses o comparaciones, usa las tablas por_dia_semana, por_mes y dias.
- Si los datos no permiten responder, dilo y sugiere qué registrar para saberlo.
- Si falta justo el dato por el que te preguntan (el reloj no lo mide, no se llevó puesto o aún no hay registros), dilo
  claro en la primera frase y no lo calcules ni lo supongas a partir de otros. Un valor null o ausente es "no hay dato", nunca un cero.
- Cada cifra que des, con su porqué en lenguaje de calle: qué significa y si es alta, normal o baja para esta persona
  (compárala con su media o su rango habitual). Si usas un término técnico (HRV, carga, Body Battery), explícalo en media frase.
- Para "¿por qué...?" mira primero lo que cambió justo antes (la última noche, el entreno de ayer, la carga de la
  semana, cómo dice que se encuentra) y cita esos datos con su fecha. Son pistas, no causas seguras: dilo así.
- Fechas: "hoy", "ayer" y "esta semana" se cuentan desde el bloque AHORA (hora de España), que va después de los datos.
  Si el último día con datos no es hoy, dilo en vez de dar por de hoy un dato antiguo.
- En el chat sí puedes hablar de lo que va de hoy si te preguntan (pasos, estrés, Body Battery de ahora): avisa de que
  el día va a medias y di la hora del último dato del reloj.
- Puedes dar consejos generales de hábitos saludables, pero no diagnósticos médicos ni dosis de medicamentos. Ante
  síntomas (dolor en el pecho, mareos, desmayos, falta de aire, palpitaciones) o un dato que preocupa, recomienda
  parar y consultar a un profesional sanitario, sin alarmar.
"""

BUSY_MSG = "La IA está muy ocupada ahora mismo. Vuelve a intentarlo en un minuto."
SLOW_MSG = "La IA ha tardado demasiado en responder. Vuelve a intentarlo."
DAYS_ES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MONTHS_ES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
             "noviembre", "diciembre"]


def _day_es(d: date) -> str:
    return f"{DAYS_ES[d.weekday()]} {d.day} de {MONTHS_ES[d.month - 1]} de {d.year} ({d.isoformat()})"


def _now_block() -> str:
    """Fecha y hora de la pregunta. Va DESPUÉS de los datos y sin caché: así los datos se siguen leyendo de la caché
    aunque cambie el minuto."""
    now = datetime.now()
    last = _ctx_cache.get("last_day")
    lines = [f"AHORA: {_day_es(now.date())}, {now:%H:%M} (hora de España). Ayer fue {_day_es(now.date() - timedelta(days=1))}."]
    if last and last != now.date().isoformat():
        lines.append(f"Aviso: el último día con datos es {last}; de hoy todavía no hay nada descargado.")
    return "\n".join(lines)


def _context() -> str:
    """Datos para la IA: resumen + tablas compactas. Se recalcula solo si cambia data.js (o la persona, o el día)."""
    path = SITE_DIR / "data.js"
    # La persona y el día van en la clave: en AWS la misma Lambda atiende a varias y nunca debe servir datos de otra.
    key = (os.environ.get("GARMIN_STATS_UID", ""), date.today().isoformat(), path.stat().st_mtime_ns)
    if _ctx_cache["key"] == key:
        return _ctx_cache["text"]
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw[raw.index("=") + 1:].rstrip().rstrip(";"))
    days = data.get("days") or []
    activities = [a for a in data.get("activities") or [] if a.get("start")]
    cols = ["sleepH", "sleepScore", "bed", "wake", "steps", "rhr", "hrv", "stress", "bbMax", "load", "ready"]
    names = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]

    def mean(vals):
        v = [x for x in vals if x is not None]
        return round(sum(v) / len(v), 1) if v else None

    by_wd = []
    for i, n in enumerate(names):
        rows = [d for d in days if date.fromisoformat(d["d"]).weekday() == i]
        by_wd.append({"dia": n, **{c: mean([r.get(c) for r in rows]) for c in cols}})
    months: dict[str, list] = {}
    for d in days:
        months.setdefault(d["d"][:7], []).append(d)
    by_month = [{"mes": m, **{c: mean([r.get(c) for r in rs]) for c in cols}} for m, rs in sorted(months.items())]
    recent = [[d["d"], names[date.fromisoformat(d["d"]).weekday()]] + [d.get(c) for c in cols] for d in days[-120:]]
    acts = [{k: a.get(k) for k in ("start", "group", "name", "km", "min", "pace", "hr", "trimp", "vo2")}
            for a in activities[-40:]]
    runs_wd = []
    for i, n in enumerate(names):
        rs = [a for a in activities if a.get("group") in ("Correr", "Cinta")
              and date.fromisoformat(a["start"][:10]).weekday() == i]
        runs_wd.append({"dia": n, "carreras": len(rs), "km_medio": mean([a.get("km") for a in rs]),
                        "ritmo_medio_min_km": mean([a.get("pace") for a in rs]), "eficiencia_media": mean([a.get("ef") for a in rs]),
                        "pulso_medio": mean([a.get("hr") for a in rs]), "carga_media": mean([a.get("trimp") for a in rs])})
    summary = ai._summary(data)
    for k in ("today", "now"):  # la fecha y la hora van aparte (bloque AHORA): aquí romperían la caché cada minuto
        summary.pop(k, None)
    ctx = {
        "nota": "bed = horas desde mediodía (13,8 = 01:48); wake = hora del reloj (7,9 = 07:54); "
                "las noches llevan la fecha del día en que te despiertas; ready = preparación 0-100. "
                "Un dato que no aparece o vale null significa que no se ha medido.",
        "resumen": summary,
        "preparacion_hoy": data.get("readiness"),
        "semanas": data.get("weeks"),
        "records": data.get("records"),
        "por_dia_semana": by_wd,
        "carreras_por_dia_semana": runs_wd,
        "por_mes": by_month,
        "dias_columnas": ["fecha", "dia"] + cols,
        "dias": recent,
        "actividades_recientes": acts,
        "plan_de_entreno": (data.get("coach") or {}).get("plan") and {
            k: data["coach"]["plan"].get(k) for k in ("goal", "raceDate", "goalTime", "summary", "memory")},
        "plan_hoy": (data.get("coach") or {}).get("today"),
        "plan_sesiones_cercanas": _plan_sessions(data),
        "nota_plan": "plan_sesiones_cercanas = sesiones del plan de los últimos 7 días y los próximos 14 (status: done = "
                     "hecha, partial = a medias, missed = no hecha, today = toca hoy, upcoming = pendiente, moved = cambiada "
                     "de día; actual = lo que hizo de verdad).",
        "avisos": data.get("alerts") or None,
        "peso": (data.get("weights") or [])[-12:] or None,
        "comida": _optional(lambda: _food(data)),
        "prevision_tiempo": _optional(_weather),
        "ahora_segun_el_reloj": {k: v for k, v in (data.get("live") or {}).items() if not k.endswith("Series")} or None,
        "nota_ahora": "bbNow = Body Battery actual (asOf = hora del último dato del reloj); bbMax = máximo del día.",
        "ritmos_de_referencia": data.get("paces") and {k: data["paces"].get(k) for k in ("vdot", "sourceLabel", "refs", "zones", "races")},
        "nota_ritmos": "refs y zones en segundos por km (fast = extremo rápido).",
        "natacion": data.get("swim") and {k: data["swim"].get(k) for k in ("css", "cssSource", "zones", "totals", "best")},
        "nota_natacion": "css y zonas de natación en segundos por 100 m.",
        "gimnasio": data.get("gym") and {"series_por_musculo_4_semanas": data["gym"].get("muscleAvg4w"),
                                         "records": [{k: r.get(k) for k in ("ex", "best", "maxKg", "maxReps", "sets")}
                                                     for r in (data["gym"].get("records") or [])[:15]]},
        "como_se_encuentra": (data.get("wellness") or {}) and {
            "ultimos_dias": data["wellness"].get("recent"), "molestias": data["wellness"].get("injuries")},
    }
    text = json.dumps(ctx, ensure_ascii=False, separators=(",", ":"))
    _ctx_cache.update(key=key, text=text, last_day=days[-1]["d"] if days else None)
    return text


def _optional(fn):
    """Un bloque extra del contexto (comida, tiempo): si falla, el chat sigue sin él."""
    try:
        return fn()
    except Exception:  # noqa: BLE001
        log.exception("Chat: bloque de contexto opcional no disponible")
        return None


def _plan_sessions(data: dict) -> list[dict] | None:
    """Sesiones del plan cerca de hoy, para responder "¿qué me toca mañana?" o "¿cómo llevo la semana?"."""
    plan = (data.get("coach") or {}).get("plan") or {}
    today = date.today()
    lo, hi = (today - timedelta(days=7)).isoformat(), (today + timedelta(days=14)).isoformat()
    keys = ("date", "type", "title", "distance_km", "duration_min", "target", "description", "status", "moved_to", "weather_note")
    out = []
    for w in plan.get("weeks") or []:
        for s in w.get("sessions") or []:
            if lo <= str(s.get("date") or "") <= hi:
                row = {k: s[k] for k in keys if s.get(k) is not None}
                if s.get("actual"):
                    row["actual"] = {k: s["actual"].get(k) for k in ("km", "min", "pace", "hr")}
                out.append(row)
    return out or None


def _food(data: dict) -> dict | None:
    """Lo que come (solo si usa el módulo Comida): hoy, media de 7 días y objetivo."""
    from . import food
    if not food.prefs()["enabled"]:
        return None
    v = food.view(data, None, coach.load())
    return {"hoy": v.get("today"), "media_7_dias": v.get("week"), "objetivo": v.get("goal"), "proteina": v.get("protein"),
            "nota": "Estimaciones a partir de fotos o texto: orientativas."}


def _weather() -> list[dict] | None:
    from . import weather
    today = date.today()
    return weather.for_coach([(today + timedelta(days=i)).isoformat() for i in range(4)])


def ask(messages: list[dict]) -> dict:
    key = ai._api_key()
    if not key:
        return {"error": "El chat no está configurado todavía (falta la clave de la IA)."}
    if ai.over_budget():
        return {"error": f"Has llegado al tope de IA de este mes ({ai.budget():.0f} $). El chat vuelve el día 1."}
    # Solo los últimos turnos, texto plano. Lo que no sea un mensaje normal (otro tipo, vacío) se ignora.
    convo = [{"role": m["role"], "content": str(m["content"])[:2000]}
             for m in (messages if isinstance(messages, list) else [])[-8:]
             if isinstance(m, dict) and m.get("role") in ("user", "assistant") and str(m.get("content") or "").strip()]
    while convo and convo[0]["role"] != "user":  # una respuesta suelta sin su pregunta no aporta nada
        convo.pop(0)
    if not convo or convo[-1]["role"] != "user":
        return {"error": "Falta la pregunta."}
    today = (os.environ.get("GARMIN_STATS_UID", ""), date.today().isoformat())  # contador por persona
    with _lock:
        if _count.get(today, 0) >= MAX_QUESTIONS_PER_DAY:
            return {"error": f"Has llegado al límite de {MAX_QUESTIONS_PER_DAY} preguntas por hoy."}
        _count[today] = _count.get(today, 0) + 1
    try:
        context = _context()
    except Exception:  # noqa: BLE001 - datos a medias o con una forma rara: mejor un aviso claro que un error 500
        log.exception("Chat: no se pudo preparar el contexto")
        return {"error": "No he podido leer tus datos para responder. Actualiza la app y vuelve a intentarlo."}
    # La web (CloudFront) espera 60 s como mucho: un intento de 55 s y un solo reintento rápido si la IA está saturada.
    client = anthropic.Anthropic(api_key=key, max_retries=1, timeout=55)
    model = ai.pick_model(CHAT_MODEL)
    extra = ai.FALLBACKS if model != ai.MODEL else {}
    try:
        resp = client.beta.messages.create(
            model=model, max_tokens=8000, output_config={"effort": "medium"}, **extra,
            system=[{"type": "text", "text": CHAT_SYSTEM},
                    # Los datos van en el system con caché: las preguntas seguidas los leen al 10 % del precio.
                    {"type": "text", "text": "DATOS DEL USUARIO (JSON):\n" + context, "cache_control": {"type": "ephemeral"}},
                    {"type": "text", "text": _now_block()}],
            messages=convo,
        )
    except anthropic.APITimeoutError:
        log.warning("Chat: la IA no ha respondido a tiempo")
        return {"error": SLOW_MSG, "retry": True}
    except anthropic.APIConnectionError:
        log.warning("Chat: sin conexión con la IA")
        return {"error": "No hay conexión con la IA ahora mismo. Vuelve a intentarlo en un momento.", "retry": True}
    except anthropic.RateLimitError:
        log.warning("Chat: límite de peticiones de la IA (429)")
        return {"error": BUSY_MSG, "retry": True}
    except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as e:
        log.error("Chat: la clave de la IA no vale (%s)", e.status_code)
        return {"error": "El chat no está disponible ahora por un problema de configuración. Prueba más tarde."}
    except anthropic.BadRequestError as e:
        log.error("Chat: petición rechazada: %s", str(e.message)[:200])
        return {"error": "La IA no ha podido con esta pregunta. Prueba a escribirla de otra forma o borra la conversación."}
    except anthropic.APIStatusError as e:
        log.warning("Chat: error %s de la IA", e.status_code)
        return {"error": BUSY_MSG if e.status_code >= 500 else "La IA no está disponible ahora. Vuelve a intentarlo en un rato.",
                "retry": e.status_code >= 500}
    cost = ai._log_usage(resp, "chat", model)  # toda respuesta 200 se cobra: se apunta siempre
    text = "".join(b.text for b in resp.content if b.type == "text").strip()
    if resp.stop_reason == "refusal":
        text = "No puedo responder a eso. Prueba a preguntarlo de otra forma."
    elif not text:
        # Sin texto (p. ej. se quedó sin espacio antes de escribir): no se guarda como respuesta, se deja reintentar
        log.warning("Chat: respuesta vacía (stop=%s)", resp.stop_reason)
        return {"error": "La respuesta ha salido vacía. Vuelve a preguntar, mejor con una pregunta más corta.", "retry": True}
    elif resp.stop_reason == "max_tokens":
        text += "\n\nLa respuesta se ha cortado por ser muy larga. Pídeme que siga si quieres el resto."
    return {"answer": text, "cost": round(cost, 5)}


def _refresh_site_coach() -> None:
    """Tras cambiar el plan, actualiza ya el bloque `coach` de data.js (la portada lo usa)."""
    from . import export
    try:
        path = SITE_DIR / "data.js"
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw[raw.index("=") + 1:].rstrip().rstrip(";"))
        data["coach"] = coach.view(data)
        data["generatedAt"] = datetime.now().astimezone().isoformat(timespec="seconds")
        export.write_site(data, SITE_DIR)
    except Exception:
        log.exception("No se pudo refrescar data.js tras cambiar el plan")


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(SITE_DIR), **kw)

    def log_message(self, fmt, *args):  # silencioso salvo errores
        if args and str(args[1]).startswith(("4", "5")):
            log.info("%s %s", self.address_string(), fmt % args)

    def end_headers(self):
        # Que el navegador no guarde copias viejas del HTML ni de los datos.
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def _json(self, code: int, obj: dict):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/health":
            return self._json(200, {"ok": True, "ai": bool(ai._api_key()), "time": datetime.now().isoformat()})
        if self.path == "/api/plan":
            return self._json(200, coach.view())
        return super().do_GET()

    def do_POST(self):
        if self.headers.get("X-Garmin-Stats") != "1":
            return self._json(403, {"error": "petición no permitida"})
        try:
            n = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(min(n, 50_000)) or b"{}")
        except (ValueError, json.JSONDecodeError):
            return self._json(400, {"error": "JSON no válido"})
        if self.path == "/api/ask":
            res = ask(body.get("messages") or [])
            return self._json(HTTPStatus.OK if "answer" in res else HTTPStatus.SERVICE_UNAVAILABLE, res)
        plan_actions = {
            "/api/plan/create": lambda: coach.create(body),
            "/api/plan/adapt": lambda: coach.adapt(force=True),
            "/api/plan/feedback": lambda: coach.feedback(body["date"], body.get("rating", 3), body.get("note", "")),
            "/api/plan/delete": coach.delete,
            "/api/plan/redo": lambda: coach.redo(str(body.get("date", "")), str(body.get("type", "")), body.get("today")),
            "/api/plan/redo-undo": lambda: coach.undo_redo(body.get("today")),
        }
        if self.path in plan_actions:
            with _plan_lock:  # una operación de plan a la vez
                try:
                    plan_actions[self.path]()
                except (RuntimeError, KeyError, ValueError) as e:
                    return self._json(400, {"error": str(e)})
                except anthropic.APIStatusError as e:
                    return self._json(503, {"error": f"La IA no está disponible ahora ({e.status_code})."})
                except anthropic.APIConnectionError:
                    return self._json(503, {"error": "Sin conexión con la IA."})
                except Exception:
                    log.exception("Error en %s", self.path)
                    return self._json(500, {"error": "Algo ha fallado en el servidor. Inténtalo de nuevo."})
            _refresh_site_coach()
            return self._json(200, coach.view())
        return self._json(404, {"error": "no encontrado"})


def serve(port: int = 8765) -> None:
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    log.info("Web en http://localhost:%d (Ctrl+C para parar)", port)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
