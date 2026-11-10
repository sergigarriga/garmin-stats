"""Que nada se rompa con datos escasos o raros, y que el chat responda siempre algo claro (sin llamar a la IA de verdad)."""
from __future__ import annotations

import json
import os
import types
from datetime import date, datetime, timedelta

import anthropic
import pandas as pd
import pytest

try:
    import httpx2 as httpx
except ImportError:  # versiones antiguas del SDK
    import httpx

from garmin_stats import ai, analysis as R, coach, export as X, food, metrics as M, server, settings, weather, wellness
from test_food import api  # noqa: F401 - fixture de la API en AWS con S3 de mentira
from test_missing_data import _report, _tables

REQ = httpx.Request("POST", "https://api.anthropic.com/v1/messages")


def _resp(text="Dormiste **7 h**.", stop="end_turn"):
    usage = types.SimpleNamespace(input_tokens=100, output_tokens=20, cache_creation_input_tokens=0, cache_read_input_tokens=0)
    content = [types.SimpleNamespace(type="thinking", thinking="")] + ([types.SimpleNamespace(type="text", text=text)] if text else [])
    return types.SimpleNamespace(content=content, stop_reason=stop, usage=usage)


@pytest.fixture
def chat(tmp_path, monkeypatch):
    """server.ask con una IA de mentira: `chat.calls` guarda lo que se le manda y `chat.reply` lo que contesta o lanza."""
    site, data_dir = tmp_path / "site", tmp_path / "data"
    site.mkdir()
    data_dir.mkdir()
    key = tmp_path / "key"
    key.write_text("clave-de-prueba")
    monkeypatch.setattr(server, "SITE_DIR", site)
    monkeypatch.setattr(ai, "KEY_FILE", key)
    monkeypatch.setattr(ai, "DATA_DIR", data_dir)
    monkeypatch.setattr(ai, "USAGE_LOG", data_dir / "ai_usage.log")
    for mod, name in ((settings, "settings.json"), (weather, "weather.json"), (wellness, "wellness.json"), (food, "food.json")):
        monkeypatch.setattr(mod, "PATH", data_dir / name)
    monkeypatch.setattr(coach, "STATE", data_dir / "coach.json")
    monkeypatch.setenv("GARMIN_STATS_UID", "u1")
    server._count.clear()
    server._ctx_cache.update(key=None, text=None, last_day=None)
    ns = types.SimpleNamespace(calls=[], reply=_resp(), client=None)

    class Fake:
        def __init__(self, **kw):
            ns.client = kw
            self.beta = types.SimpleNamespace(messages=types.SimpleNamespace(create=self.create))

        def create(self, **kw):
            ns.calls.append(kw)
            if isinstance(ns.reply, Exception):
                raise ns.reply
            return ns.reply

    monkeypatch.setattr(server.anthropic, "Anthropic", Fake)

    def write(data):
        (site / "data.js").write_text("window.__GARMIN__=" + json.dumps(data, ensure_ascii=False) + ";\n", encoding="utf-8")
    ns.write = write
    write(_report())
    return ns


Q = [{"role": "user", "content": "¿Por qué mi HRV está baja hoy?"}]


# ------------------------------------------------------------------ chat: contexto y fechas
def test_chat_answers_and_keeps_data_block_cacheable(chat, monkeypatch):
    assert server.ask(Q)["answer"] == "Dormiste **7 h**."
    system = chat.calls[0]["system"]
    assert [b.get("cache_control") for b in system] == [None, {"type": "ephemeral"}, None]
    first = system[1]["text"]
    assert '"now"' not in first and '"today"' not in first  # la hora va aparte: no rompe la caché cada minuto

    class Later(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, 10, 23, 58)
    monkeypatch.setattr(server, "datetime", Later)
    server.ask(Q)
    assert chat.calls[1]["system"][1]["text"] == first
    now = chat.calls[1]["system"][2]["text"]
    assert "martes 10 de noviembre de 2026" in now and "23:58" in now and "lunes 9 de noviembre" in now
    # un intento que cabe en los 60 s de la web, no varios minutos de reintentos
    assert chat.client["timeout"] <= 55 and chat.client["max_retries"] <= 1


def test_chat_says_when_data_is_not_from_today(chat):
    data = _report()
    data["days"] = data["days"][:-1]  # la última descarga fue ayer
    chat.write(data)
    server.ask(Q)
    assert f"el último día con datos es {data['days'][-1]['d']}" in chat.calls[0]["system"][2]["text"]


def test_yesterday_is_picked_by_date_not_by_position():
    today = date.today()
    days = [{"d": (today - timedelta(days=i)).isoformat(), "steps": 1000 * i} for i in (3, 2, 1)]  # sin el día de hoy
    s = ai._summary({"days": days, "activities": [], "profile": {}, "insights": {}, "relations": []})
    assert s["yesterday_complete"]["d"] == (today - timedelta(days=1)).isoformat()
    s = ai._summary({"days": days[:-1], "activities": [], "profile": {}, "insights": {}, "relations": []})
    assert s["yesterday_complete"] is None  # ayer sin datos: no se hace pasar anteayer por ayer


@pytest.mark.parametrize("kw", [{"hrv": False}, {"hrv": False, "sleep": False}, {"days": 1, "hrv": False, "sleep": False}])
def test_chat_works_with_sparse_data(chat, kw):
    chat.write(_report(**kw))
    assert "answer" in server.ask(Q)
    ctx = json.loads(chat.calls[0]["system"][1]["text"].split("\n", 1)[1])
    assert ctx["resumen"]["latest"]["hrv"] is None  # sin dato, no un cero


def test_chat_context_has_plan_sessions_weight_and_alerts(chat):
    today = date.today()
    data = _report()
    data["weights"] = [{"d": today.isoformat(), "kg": 71.2}]
    data["coach"] = {"today": None, "plan": {"goal": "10 km", "weeks": [{"start": today.isoformat(), "sessions": [
        {"date": (today + timedelta(days=1)).isoformat(), "type": "easy", "title": "Rodaje suave", "distance_km": 8,
         "status": "upcoming", "workout": [{"repeat": 1, "steps": []}]},
        {"date": (today + timedelta(days=40)).isoformat(), "type": "long", "title": "Tirada lejana", "status": "upcoming"}]}]}}
    chat.write(data)
    server.ask(Q)
    ctx = json.loads(chat.calls[0]["system"][1]["text"].split("\n", 1)[1])
    assert [s["title"] for s in ctx["plan_sesiones_cercanas"]] == ["Rodaje suave"]
    assert "workout" not in ctx["plan_sesiones_cercanas"][0]
    assert ctx["peso"] == [{"d": today.isoformat(), "kg": 71.2}]


def test_chat_context_is_never_shared_between_people(chat):
    a, b = _report(), _report()
    b["profile"]["age"] = 99
    path = server.SITE_DIR / "data.js"
    chat.write(a)
    stamp = path.stat().st_mtime_ns
    server.ask(Q)
    chat.write(b)
    os.utime(path, ns=(stamp, stamp))  # misma hora de archivo: solo cambia la persona
    os.environ["GARMIN_STATS_UID"] = "u2"
    server.ask(Q)
    assert '"age":99' in chat.calls[1]["system"][1]["text"] and '"age":99' not in chat.calls[0]["system"][1]["text"]


def test_chat_broken_data_file_gives_a_clear_message(chat):
    (server.SITE_DIR / "data.js").write_text("window.__GARMIN__={roto", encoding="utf-8")
    out = server.ask(Q)
    assert "No he podido leer tus datos" in out["error"] and not chat.calls


# ------------------------------------------------------------------ chat: historial
def test_chat_history_is_trimmed_and_cleaned(chat):
    long = [{"role": "user" if i % 2 == 0 else "assistant", "content": f"m{i} " + "x" * 5000} for i in range(21)]
    server.ask(long + ["basura", {"role": "system", "content": "x"}, {"role": "user", "content": "   "}, None])
    sent = chat.calls[0]["messages"]
    assert sent[0]["role"] == "user" and sent[-1]["role"] == "user" and len(sent) <= 8
    assert all(len(m["content"]) <= 2000 for m in sent)


@pytest.mark.parametrize("msgs", [[], None, "hola", [{"role": "assistant", "content": "hola"}], [{"role": "user"}], [42]])
def test_chat_without_a_question(chat, msgs):
    assert server.ask(msgs) == {"error": "Falta la pregunta."}
    assert not chat.calls


# ------------------------------------------------------------------ chat: cuando la IA falla
@pytest.mark.parametrize("exc, expected, retry", [
    (anthropic.APITimeoutError(request=REQ), server.SLOW_MSG, True),
    (anthropic.APIConnectionError(request=REQ), "No hay conexión con la IA", True),
    (anthropic.RateLimitError("rate", response=httpx.Response(429, request=REQ), body=None), server.BUSY_MSG, True),
    (anthropic.APIStatusError("overloaded", response=httpx.Response(529, request=REQ), body=None), server.BUSY_MSG, True),
    (anthropic.InternalServerError("boom", response=httpx.Response(500, request=REQ), body=None), server.BUSY_MSG, True),
    (anthropic.BadRequestError("prompt is too long", response=httpx.Response(400, request=REQ), body=None), "no ha podido con esta pregunta", False),
    (anthropic.AuthenticationError("invalid x-api-key", response=httpx.Response(401, request=REQ), body=None), "configuración", False),
])
def test_chat_api_failures_are_explained_in_plain_spanish(chat, exc, expected, retry):
    chat.reply = exc
    out = server.ask(Q)
    assert expected in out["error"] and bool(out.get("retry")) is retry
    assert "answer" not in out
    for raw in ("429", "529", "500", "400", "401", "overloaded", "prompt is too long", "x-api-key"):
        assert raw not in out["error"]


def test_chat_truncated_empty_and_refused_answers(chat):
    chat.reply = _resp("Empiezo a explicar y", stop="max_tokens")
    out = server.ask(Q)
    assert out["answer"].startswith("Empiezo a explicar y") and "se ha cortado" in out["answer"]
    chat.reply = _resp("", stop="max_tokens")  # se quedó sin espacio antes de escribir: no es una respuesta
    out = server.ask(Q)
    assert "answer" not in out and out["retry"] and "vacía" in out["error"]
    chat.reply = _resp("", stop="end_turn")
    assert "answer" not in server.ask(Q)
    chat.reply = _resp("texto a medias", stop="refusal")
    assert server.ask(Q)["answer"].startswith("No puedo responder a eso")
    # toda respuesta de la IA se cobra y se apunta, sirva o no
    assert len(ai.USAGE_LOG.read_text().splitlines()) == 4


def test_chat_prompt_rules():
    p = server.CHAT_SYSTEM
    for must in ("no lo calcules ni lo supongas", "diagnósticos médicos", "AHORA", "lenguaje de calle", "consultar a un profesional"):
        assert must in p


# ------------------------------------------------------------------ informe con datos escasos
def test_no_activities_at_all_still_builds_the_report():
    am = M.activity_metrics(pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), 55, 190)
    assert am.empty and {"activity_id", "start", "group", "distance_km", "z5_min"} <= set(am.columns)
    X.SECTION_ERRORS.clear()
    A = R.assemble({**_tables(), "activities": am}, {"max_hr": 190, "rest_hr": 55})
    data = X.payload(A, am, None, {})
    assert data["days"] and data["activities"] == [] and not X.SECTION_ERRORS, X.SECTION_ERRORS


def test_metric_never_recorded_arrives_as_none_column():
    """Solo móvil (Google Health): el pulso en reposo llega como columna de None y el sueño, algunas noches."""
    t = _tables(hrv=False)
    t["daily"]["rhr"] = pd.Series([None] * len(t["daily"]), dtype=object)
    t["sleep"] = t["sleep"].iloc[::2]
    X.SECTION_ERRORS.clear()
    A = R.assemble(t, {"max_hr": 190, "rest_hr": 55})
    data = _payload(A)
    assert not X.SECTION_ERRORS, X.SECTION_ERRORS
    assert all("rhr" not in d for d in data["days"])


def _payload(A):
    am = M.activity_metrics(pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), 55, 190)
    return X.payload(A, am, None, {})


def test_single_night_of_sleep_has_no_nan_in_texts():
    t = _tables(days=2, hrv=False)
    t["sleep"] = t["sleep"].iloc[-1:]
    X.SECTION_ERRORS.clear()
    data = _payload(R.assemble(t, {"max_hr": 190, "rest_hr": 55}))
    assert not X.SECTION_ERRORS, X.SECTION_ERRORS
    texts = [x for v in data["insights"].values() for x in v]
    assert texts and not any("nan" in x.lower() for x in texts), texts


def test_sleep_without_bed_times_keeps_the_insights():
    t = _tables(hrv=False)
    for c in ("bed_from_noon", "bed_clock", "wake_clock", "mid_from_noon"):
        t["sleep"][c] = float("nan")
    X.SECTION_ERRORS.clear()
    data = _payload(R.assemble(t, {"max_hr": 190, "rest_hr": 55}))
    assert not X.SECTION_ERRORS, X.SECTION_ERRORS
    assert data["insights"]["sueno"] and not any("nan" in x.lower() for x in data["insights"]["sueno"])


def test_failed_insights_keep_their_keys(monkeypatch):
    def boom(*_a, **_k):
        raise ValueError("dato raro")
    monkeypatch.setattr(X, "insights", boom)
    data = _report()
    assert data["insights"]["entreno"] == [] and data["insights"]["carrera"] == []  # la web recorre estas listas


def test_activity_without_name_is_valid_json():
    d = pd.Timestamp.today().normalize()
    row = {"activity_id": 1, "start": d + pd.Timedelta(hours=8), "date": d, "name": float("nan"), "type": "running",
           "group": "Correr", "distance_km": 8.0, "duration_min": 45.0, "pace_min_km": 5.6, "avg_hr": 150.0, "max_hr": 170.0,
           "trimp": 60.0, "ef": 1.2, "decoupling_pct": float("nan"), "cadence_spm": 170.0, "elev_gain": 50.0,
           "calories": 500.0, "is_pr": False, **{f"z{i}_min": 5.0 for i in range(1, 6)}}
    am = pd.DataFrame([row])
    A = R.assemble({**_tables(), "activities": am}, {"max_hr": 190, "rest_hr": 55})
    data = X.payload(A, am, None, {})
    assert "name" not in data["activities"][0]
    json.dumps(data, allow_nan=False)  # ni un NaN: el navegador rechazaría la respuesta entera


def test_coach_profile_without_heart_rate_zones(monkeypatch, tmp_path):
    """Google Health no da zonas de pulso: el perfil para el plan sale igual."""
    monkeypatch.setattr(settings, "PATH", tmp_path / "settings.json")
    start = (date.today() - timedelta(days=3)).isoformat() + "T08:00"
    data = {"profile": {"zones": [None] * 5}, "days": [],
            "activities": [{"id": 1, "start": start, "group": "Correr", "km": 8.0, "min": 45.0, "pace": 5.6, "hr": 150}]}
    assert coach.profile(data)


# ------------------------------------------------------------------ API en AWS
def test_api_never_answers_with_nan(api):  # noqa: F811
    body = api.h._json(200, {"a": float("nan"), "b": [1.5, float("inf")], "c": {"d": "ok"}})["body"]
    assert json.loads(body) == {"a": None, "b": [1.5, None], "c": {"d": "ok"}}


def test_api_bad_bodies_are_400_not_500(api):  # noqa: F811
    for raw in ("[1, 2]", '"hola"', "42"):
        assert api.call("POST", "/api/plan/feedback", raw=raw)[0] == 400
    for body in ({}, {"date": "ayer"}, {"date": date.today().isoformat(), "rating": "abc"}, {"date": None, "rating": 3}):
        code, out = api.call("POST", "/api/plan/feedback", body)
        assert code == 400 and out["error"], body
    code, _ = api.call("POST", "/api/plan/feedback", {"date": date.today().isoformat(), "rating": None, "note": None})
    assert code == 200


def test_api_unexpected_failure_is_a_clear_json_error(api, monkeypatch):  # noqa: F811
    def boom(*_a, **_k):
        raise KeyError("algo inesperado")
    monkeypatch.setattr(coach, "delete", boom)
    code, out = api.call("POST", "/api/plan/delete", {})
    assert code == 500 and "Algo ha fallado" in out["error"] and "inesperado" not in out["error"]


def test_api_ask_stores_only_real_answers(api, monkeypatch):  # noqa: F811
    seen = []
    replies = [{"error": server.BUSY_MSG, "retry": True}, {"answer": "Bien.", "cost": 0.01}, {"error": "Falta la pregunta."}]
    monkeypatch.setattr(server, "ask", lambda msgs: (seen.append(msgs), replies.pop(0))[1])
    code, out = api.call("POST", "/api/ask", {"messages": [{"role": "user", "content": "¿Cómo voy?"}, "basura"]})
    assert code == 503 and out["error"] == server.BUSY_MSG and seen[0] == [{"role": "user", "content": "¿Cómo voy?"}]
    assert api.call("GET", "/api/chat")[1]["messages"] == []  # una pregunta fallida no se guarda como conversación
    code, out = api.call("POST", "/api/ask", {"messages": [{"role": "user", "content": "¿Cómo voy?"}]})
    assert code == 200 and [m["role"] for m in api.call("GET", "/api/chat")[1]["messages"]] == ["user", "assistant"]
    assert api.call("POST", "/api/ask", {"messages": "hola"})[0] == 503 and seen[-1] == []  # forma rara: nunca un 500


def test_api_structure_week_when_the_ai_is_down(api, monkeypatch):  # noqa: F811
    def down(_week):
        raise anthropic.APIStatusError("overloaded_error", response=httpx.Response(529, request=REQ), body=None)
    monkeypatch.setattr(coach, "structure_week", down)
    code, out = api.call("POST", "/api/plan/structure", {"week": "2026-11-09"})
    assert code == 503 and "muy ocupada" in out["error"] and "overloaded" not in out["error"]
