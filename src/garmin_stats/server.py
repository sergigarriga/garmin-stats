"""Servidor local: sirve la web (site/) y responde preguntas a la IA en /api/ask.

Solo escucha en 127.0.0.1. La clave de Anthropic se queda en este proceso; el navegador nunca la ve.
Para que otra web no pueda gastar tu saldo llamando a localhost, /api/ask exige la cabecera
X-Garmin-Stats (una web ajena no puede enviarla sin un permiso CORS que aquí nunca se da).
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import date, datetime
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
_ctx_cache: dict = {"mtime": None, "text": None}

CHAT_SYSTEM = ai.SYSTEM + """

Ahora respondes preguntas del usuario sobre sus propios datos, como un asistente de Google Health.
- Empieza con la respuesta directa en una frase. Después, el porqué con sus datos y, si ayuda, qué hacer.
- Formato (se muestra bonito en la app): párrafos cortos separados por una línea en blanco, **negrita** solo para
  la idea clave y los datos importantes (2-4 por respuesta), y listas con "- " (o "1. " si el orden importa) de
  3-4 puntos como mucho. Nada de títulos, tablas ni emojis. Máximo unas 150 palabras.
- Para preguntas por días de la semana, meses o comparaciones, usa las tablas por_dia_semana, por_mes y dias.
- Si los datos no permiten responder, dilo y sugiere qué registrar para saberlo.
- Puedes dar consejos generales de hábitos saludables, pero no diagnósticos médicos. Ante síntomas, recomienda consultar a un profesional.
"""


def _context() -> str:
    """Datos para la IA: resumen + tablas compactas. Se recalcula solo si cambia data.js."""
    path = SITE_DIR / "data.js"
    mtime = path.stat().st_mtime
    if _ctx_cache["mtime"] == mtime:
        return _ctx_cache["text"]
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw[raw.index("=") + 1:].rstrip().rstrip(";"))
    days = data["days"]
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
            for a in data["activities"][-40:]]
    runs_wd = []
    for i, n in enumerate(names):
        rs = [a for a in data["activities"] if a["group"] in ("Correr", "Cinta")
              and date.fromisoformat(a["start"][:10]).weekday() == i]
        runs_wd.append({"dia": n, "carreras": len(rs), "km_medio": mean([a.get("km") for a in rs]),
                        "ritmo_medio_min_km": mean([a.get("pace") for a in rs]), "eficiencia_media": mean([a.get("ef") for a in rs]),
                        "pulso_medio": mean([a.get("hr") for a in rs]), "carga_media": mean([a.get("trimp") for a in rs])})
    ctx = {
        "nota": "bed = horas desde mediodía (13,8 = 01:48); wake = hora del reloj (7,9 = 07:54); "
                "las noches llevan la fecha del día en que te despiertas; ready = preparación 0-100.",
        "resumen": ai._summary(data),
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
    }
    text = json.dumps(ctx, ensure_ascii=False, separators=(",", ":"))
    _ctx_cache.update(mtime=mtime, text=text)
    return text


def ask(messages: list[dict]) -> dict:
    key = ai._api_key()
    if not key:
        return {"error": "No hay clave de Anthropic configurada."}
    today = date.today().isoformat()
    with _lock:
        if _count.get(today, 0) >= MAX_QUESTIONS_PER_DAY:
            return {"error": f"Has llegado al límite de {MAX_QUESTIONS_PER_DAY} preguntas por hoy."}
        _count[today] = _count.get(today, 0) + 1
    # Solo los últimos turnos, texto plano y alternando roles.
    convo = [{"role": m["role"], "content": str(m["content"])[:2000]} for m in messages[-8:]
             if m.get("role") in ("user", "assistant") and m.get("content")]
    if not convo or convo[-1]["role"] != "user":
        return {"error": "Falta la pregunta."}
    client = anthropic.Anthropic(api_key=key, max_retries=2, timeout=120)
    model = ai.pick_model(CHAT_MODEL)
    extra = ai.FALLBACKS if model != ai.MODEL else {}
    try:
        resp = client.beta.messages.create(
            model=model, max_tokens=8000, output_config={"effort": "medium"}, **extra,
            system=[{"type": "text", "text": CHAT_SYSTEM},
                    # Los datos van en el system con caché: las preguntas seguidas los leen al 10 % del precio.
                    {"type": "text", "text": "DATOS DEL USUARIO (JSON):\n" + _context(), "cache_control": {"type": "ephemeral"}}],
            messages=convo,
        )
    except anthropic.APIStatusError as e:
        return {"error": f"La IA no está disponible ahora ({e.status_code})."}
    except anthropic.APIConnectionError:
        return {"error": "Sin conexión con la IA."}
    cost = ai._log_usage(resp, "chat", model)
    text = "".join(b.text for b in resp.content if b.type == "text").strip()
    if resp.stop_reason == "refusal" or not text:
        text = "No puedo responder a eso. Prueba a preguntarlo de otra forma."
    return {"answer": text, "cost": round(cost, 5)}


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
            return self._json(200, coach.view())
        return self._json(404, {"error": "no encontrado"})


def serve(port: int = 8765) -> None:
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    log.info("Web en http://localhost:%d (Ctrl+C para parar)", port)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
