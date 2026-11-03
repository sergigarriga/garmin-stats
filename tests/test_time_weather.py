"""Pruebas de "tu tiempo" (minutos disponibles por día) y de la previsión del tiempo (Open-Meteo) en el plan.

Sin red ni IA: Open-Meteo y Claude van simulados. Ejecutar: uv run --with pytest pytest -q
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import importlib.util
import io
import json
import os
import sys
import time
import types
from datetime import date, timedelta
from pathlib import Path

import pytest

from garmin_stats import coach, settings, weather, wellness

TODAY = date.today()
iso = lambda d: d.isoformat()  # noqa: E731
FIXTURE = Path(__file__).parent / "fixtures" / "open_meteo_3d.json"
FIX_DAYS = ["2026-07-15", "2026-07-16", "2026-07-17"]  # calor, tormenta con viento, suave
_REAL_GET = weather._get


@pytest.fixture(autouse=True)
def tmp_state(tmp_path, monkeypatch):
    monkeypatch.setattr(wellness, "PATH", tmp_path / "wellness.json")
    monkeypatch.setattr(settings, "PATH", tmp_path / "settings.json")
    monkeypatch.setattr(weather, "PATH", tmp_path / "weather.json")
    monkeypatch.setattr(coach, "STATE", tmp_path / "coach.json")
    # nunca red de verdad
    monkeypatch.setattr(weather, "_get", lambda url, params: pytest.fail(f"llamada de red sin simular: {url}"))
    return tmp_path


def raw_from(start: date) -> dict:
    """El fixture con sus 3 días movidos para que el primero sea `start`."""
    text = FIXTURE.read_text()
    for i, d in enumerate(FIX_DAYS):
        text = text.replace(d, iso(start + timedelta(days=i)))
    return json.loads(text)


def use_forecast(monkeypatch, start: date, calls: list | None = None):
    def fake(url, params):
        if calls is not None:
            calls.append((url, params))
        return raw_from(start)
    monkeypatch.setattr(weather, "_get", fake)
    settings.set_location({"name": "Tarragona", "lat": 41.1189, "lon": 1.2445})
    assert weather.refresh(force=True)


# ---------------------------------------------------------------- tu tiempo: validación y mezcla
def test_availability_validation_and_merge():
    tue, tomorrow = "1", iso(TODAY + timedelta(days=1))
    settings.set_availability({"weekly": {"0": 60, tue: 180, "5": 0, "6": None}})
    a = settings.availability()
    assert a["weekly"] == {"0": 60, "1": 180, "2": None, "3": None, "4": None, "5": 0, "6": None}
    # los días concretos mandan sobre la semana tipo
    settings.set_availability({"days": {tomorrow: 45, iso(TODAY): "120"}})
    assert settings.available_minutes(tomorrow) == 45
    assert settings.available_minutes(iso(TODAY)) == 120
    other = next(TODAY + timedelta(days=i) for i in range(2, 9) if (TODAY + timedelta(days=i)).weekday() == 1)
    assert settings.available_minutes(other) == 180
    sat = next(TODAY + timedelta(days=i) for i in range(2, 9) if (TODAY + timedelta(days=i)).weekday() == 5)
    assert settings.available_minutes(sat) == 0
    wed = next(TODAY + timedelta(days=i) for i in range(2, 9) if (TODAY + timedelta(days=i)).weekday() == 2)
    assert settings.available_minutes(wed) is None  # sin límite
    # la semana tipo se conserva al tocar solo los días; null quita un día concreto
    settings.set_availability({"days": {tomorrow: None}})
    assert tomorrow not in settings.availability()["days"] and settings.availability()["weekly"]["1"] == 180
    # valores fuera de rango, días pasados o demasiado lejos, claves raras
    for bad in ({"weekly": {"0": 600}}, {"weekly": {"0": -5}}, {"weekly": {"7": 30}}, {"weekly": {"0": "mucho"}},
                {"days": {iso(TODAY - timedelta(days=1)): 30}}, {"days": {iso(TODAY + timedelta(days=80)): 30}},
                {"days": {"ayer": 30}}, {"weekly": [1, 2]}):
        with pytest.raises(ValueError):
            settings.set_availability(bad)
    # al guardar se podan los días pasados
    st = settings.load()
    st["availability"]["days"][iso(TODAY - timedelta(days=3))] = 30
    settings.save(st)
    settings.set_availability({"weekly": {"2": 30}})
    assert all(d >= iso(TODAY) for d in settings.load()["availability"]["days"])
    settings.set_availability({"clear": True})
    assert "availability" not in settings.load() and not settings.has_availability()


def test_location_validation():
    settings.set_location({"name": "Tarragona", "lat": 41.11891, "lon": 1.24456})
    assert settings.location() == {"name": "Tarragona", "lat": 41.12, "lon": 1.24}
    for bad in ({"name": "X"}, {"name": "", "lat": 1, "lon": 1}, {"name": "X", "lat": 91, "lon": 0}, {"name": "X", "lat": "a", "lon": 0}):
        with pytest.raises(ValueError):
            settings.set_location(bad)
    settings.set_location({"clear": True})
    assert settings.location() is None


# ---------------------------------------------------------------- previsión: resumen y franjas
def test_weather_summarise_fixture():
    days = weather.summarise(json.loads(FIXTURE.read_text()))
    assert [d["date"] for d in days] == FIX_DAYS
    hot, storm, mild = days
    assert hot["flags"] == ["heat"] and hot["tmax"] == 33 and hot["feelsMax"] == 35 and hot["text"] == "Casi despejado"
    assert hot["sunrise"] == "06:40" and hot["sunset"] == "21:25"
    assert hot["windows"][0]["from"] == "07:00" and hot["windows"][0]["to"] == "09:00"  # lo más fresco con luz
    assert len(hot["windows"]) == 1  # por la tarde no hay una franja buena
    assert {"storm", "heavy_rain", "wind"} <= set(storm["flags"]) and storm["text"] == "Tormenta"
    assert storm["windows"][0]["from"] == "07:00" and storm["windows"][0]["rain"] == 25
    assert mild["flags"] == [] and mild["rainProb"] == 10
    json.dumps(days)


def test_best_window_avoids_dark_heat_and_rain():
    hours = [{"hour": h, "temp": 15, "feels": 15, "rain": 0, "wind": 5, "rh": 50} for h in range(24)]
    # amanece a las 8:00: la primera franja con luz gana aunque la temperatura sea igual
    assert weather.best_windows(hours, 8 * 60, 18 * 60)[0]["from"] == "08:00"
    # lluvia por la mañana: mejor por la tarde
    wet = [{**h, "rain": 90 if h["hour"] < 14 else 0} for h in hours]
    assert weather.best_windows(wet, 7 * 60, 20 * 60)[0]["from"] >= "14:00"
    # calor a mediodía: dos franjas, por la mañana y por la tarde, separadas
    hot = [{**h, "feels": 30 if 11 <= h["hour"] <= 18 else 16, "temp": 30 if 11 <= h["hour"] <= 18 else 16} for h in hours]
    w = weather.best_windows(hot, 7 * 60, 21 * 60)
    assert len(w) == 2 and abs(int(w[0]["from"][:2]) - int(w[1]["from"][:2])) >= 4
    assert all(not (11 <= int(x["from"][:2]) <= 17) for x in w)
    # todo de 6 a 22
    assert all("06:00" <= x["from"] and x["to"] <= "22:00" for x in w)
    assert weather.best_windows([], None, None) == []


def test_weather_refresh_cache_and_failure(monkeypatch):
    calls: list = []
    assert weather.refresh() is False  # sin ciudad no se pide nada
    use_forecast(monkeypatch, TODAY, calls)
    assert calls[0][1]["timezone"] == "Europe/Madrid" and calls[0][1]["forecast_days"] == 16
    assert "apparent_temperature_max" in calls[0][1]["daily"] and "relative_humidity_2m" in calls[0][1]["hourly"]
    assert weather.refresh() is False and len(calls) == 1  # en caché (menos de 3 h)
    assert list(weather.days()) == [iso(TODAY + timedelta(days=i)) for i in range(3)]
    b = weather.block()
    assert b["location"]["name"] == "Tarragona" and len(b["days"]) == 3 and b["fetchedAt"]
    # caché vieja: se vuelve a pedir
    st = weather.load()
    st["fetchedTs"] -= 4 * 3600
    weather.save(st)
    assert weather.refresh() is True and len(calls) == 2
    # otra ciudad: la previsión anterior no vale; si Open-Meteo falla, no hay previsión pero nada se rompe
    monkeypatch.setattr(weather, "_get", lambda url, params: None)
    settings.set_location({"name": "Madrid", "lat": 40.42, "lon": -3.70})
    assert weather.refresh() is False and weather.days() == {} and weather.block()["days"] == []
    assert weather.for_coach([iso(TODAY)]) is None
    # respuesta con formato raro: tampoco rompe
    monkeypatch.setattr(weather, "_get", lambda url, params: {"daily": {"time": [iso(TODAY)], "sunrise": [42]}})
    assert weather.refresh(force=True) is False


def test_geocode(monkeypatch):
    seen = {}

    def fake(url, params):
        seen.update(url=url, **params)
        return {"results": [{"name": "Tarragona", "admin1": "Cataluña", "country": "España", "latitude": 41.11888, "longitude": 1.24544},
                            {"name": "Sin coordenadas"}]}
    monkeypatch.setattr(weather, "_get", fake)
    r = weather.geocode(" Tarragona ")
    assert seen["url"] == weather.GEO_URL and seen["language"] == "es" and seen["count"] == 5
    assert r == [{"name": "Tarragona", "label": "Tarragona, Cataluña, España", "admin1": "Cataluña", "country": "España",
                  "lat": 41.12, "lon": 1.25}]
    assert weather.geocode("x") == []  # demasiado corto: ni se pregunta


def test_network_failure_is_graceful(monkeypatch):
    def boom(*a, **k):
        raise OSError("sin red")
    monkeypatch.setattr(weather, "_get", _REAL_GET)
    monkeypatch.setattr(weather.urllib.request, "urlopen", boom)
    assert weather.geocode("Tarragona") == []
    settings.set_location({"name": "Tarragona", "lat": 41.12, "lon": 1.25})
    assert weather.refresh(force=True) is False and weather.block()["days"] == []


# ---------------------------------------------------------------- consejo del día con el tiempo
def _at(monkeypatch, hour: int, minute: int = 0):
    """Fija la hora "ahora" del consejo del día (las franjas que ya han pasado no se proponen)."""
    from datetime import datetime as _dt

    class Fixed(_dt):
        @classmethod
        def now(cls, tz=None):
            return _dt(TODAY.year, TODAY.month, TODAY.day, hour, minute)
    monkeypatch.setattr(weather, "datetime", Fixed)


@pytest.fixture
def early(monkeypatch):
    _at(monkeypatch, 5)


def _week(sessions):
    return {"weeks": [{"start": iso(TODAY), "focus": "x", "sessions": sessions}]}


def test_today_advice_heat(monkeypatch, early):
    use_forecast(monkeypatch, TODAY)  # hoy: calor
    plan = _week([{"date": iso(TODAY), "type": "intervals", "title": "Series"}])
    out = coach.today_advice(plan, {"date": iso(TODAY), "score": 85})
    assert "ideal" in out["tip"]  # el consejo de la preparación sigue ahí
    assert "07:00" in out["weatherTip"] and "pulso" in out["weatherTip"] and "agua" in out["weatherTip"]
    assert out["bestWindow"]["from"] == "07:00" and out["weather"]["tmax"] == 33
    # descanso: sin consejo del tiempo
    rest = coach.today_advice(_week([{"date": iso(TODAY), "type": "rest", "title": "Descanso"}]), None)
    assert "weatherTip" not in rest


def test_today_advice_storm_swap_or_treadmill(monkeypatch, early):
    use_forecast(monkeypatch, TODAY - timedelta(days=1))  # hoy: tormenta; mañana: suave
    tomorrow = TODAY + timedelta(days=1)
    plan = _week([{"date": iso(TODAY), "type": "long", "title": "Tirada larga"},
                  {"date": iso(tomorrow), "type": "easy", "title": "Rodaje"}])
    tip = coach.today_advice(plan, None)["weatherTip"]
    assert "tormenta" in tip and "Cambia" in tip
    # sin un día bueno para cambiar: la franja con tregua o la cinta
    plan2 = _week([{"date": iso(TODAY), "type": "intervals", "title": "Series"}])
    tip2 = coach.today_advice(plan2, None)["weatherTip"]
    assert "07:00" in tip2 and "cinta" in tip2
    # un rodaje suave con tormenta: alternativa, sin proponer cambio de día
    tip3 = coach.today_advice(_week([{"date": iso(TODAY), "type": "easy", "title": "Rodaje"}]), None)["weatherTip"]
    assert "Cambia" not in tip3


def test_today_advice_skips_windows_already_gone(monkeypatch):
    use_forecast(monkeypatch, TODAY)  # calor: lo mejor era de 07:00 a 09:00
    plan = _week([{"date": iso(TODAY), "type": "intervals", "title": "Series"}])
    _at(monkeypatch, 11, 10)
    out = coach.today_advice(plan, None)
    assert out["bestWindow"]["from"] == "20:00" and "de 20:00 a 22:00" in out["weatherTip"]
    assert "slots" not in out["weather"] and "07:00" not in out["weatherTip"]
    _at(monkeypatch, 21, 40)  # ya no queda ninguna franja hoy
    out = coach.today_advice(plan, None)
    assert out["bestWindow"] is None and "la hora más fresca" in out["weatherTip"]
    # tormenta a media mañana: la tregua de primera hora ya pasó → cinta
    use_forecast(monkeypatch, TODAY - timedelta(days=1))
    _at(monkeypatch, 10)
    tip = coach.today_advice(_week([{"date": iso(TODAY), "type": "tempo", "title": "Ritmo"}]), None)["weatherTip"]
    assert "cinta" in tip and "tregua" not in tip


def test_weather_block_has_no_slots(monkeypatch):
    use_forecast(monkeypatch, TODAY)
    assert weather.load()["days"][0]["slots"]  # se guardan en el estado…
    assert all("slots" not in d for d in weather.block()["days"])  # …pero no van a la web


def test_today_advice_without_weather_is_unchanged():
    plan = _week([{"date": iso(TODAY), "type": "intervals", "title": "Series"}])
    out = coach.today_advice(plan, {"date": iso(TODAY), "score": 85})
    assert set(out) == {"session", "tip"}


# ---------------------------------------------------------------- comprobación sin IA y cumplimiento
def _plan_weeks(first: date, minutes: list[int | None], types=None):
    types = types or ["easy"] * len(minutes)
    return [{"start": iso(first), "focus": "x", "sessions": [
        {"date": iso(first + timedelta(days=i)), "type": t, "title": f"S{i}", "distance_km": None if m is None else m / 6,
         "duration_min": m, "target": "", "description": ""} for i, (m, t) in enumerate(zip(minutes, types))]}]


def test_time_conflicts_and_compliance_flags():
    tomorrow = TODAY + timedelta(days=1)
    settings.set_availability({"days": {iso(TODAY): 45, iso(tomorrow): 0, iso(tomorrow + timedelta(days=1)): 90}})
    weeks = _plan_weeks(TODAY, [60, 30, 90, None], ["easy", "easy", "long", "rest"])
    weeks[0]["sessions"].append({"date": iso(TODAY), "type": "strength", "title": "Gimnasio", "distance_km": None,
                                 "duration_min": 20, "target": "", "description": ""})  # mismo día: suma
    c = coach.time_conflicts(weeks)
    assert [(x["date"], x["avail"], x["planned"]) for x in c] == [(iso(TODAY), 45, 80), (iso(tomorrow), 0, 30)]
    assert coach.time_conflicts(weeks, since=iso(tomorrow))[0]["date"] == iso(tomorrow)
    # en la web: minutos de cada día y aviso en las sesiones que no caben
    state = {"plan": {"goal": "10 km", "raceDate": iso(TODAY + timedelta(days=60)), "weeks": weeks}}
    full = coach.with_compliance(state, {"activities": []})
    ss = full["weeks"][0]["sessions"]
    assert ss[0]["availMin"] == 45 and ss[0]["timeWarn"] == {"avail": 45, "planned": 80}
    assert ss[1]["timeWarn"]["avail"] == 0 and "timeWarn" not in ss[2] and "timeWarn" not in ss[3]
    # sin tiempo configurado: ni availMin ni avisos (como antes)
    settings.set_availability({"clear": True})
    assert coach.time_conflicts(weeks) == []
    assert "availMin" not in coach.with_compliance(state, {"activities": []})["weeks"][0]["sessions"][0]


# ---------------------------------------------------------------- prompts de crear y reajustar
DATA = {"activities": [], "predictions": [], "days": [], "profile": {}}


def _fake_call(captured: dict, weeks_fn):
    def fake(schema, prompt, kind, model=None):
        captured.update(prompt=prompt, kind=kind)
        weeks = weeks_fn()
        if schema is coach.PlanOut:
            return coach.PlanOut(summary="Plan", weeks=weeks, memory=[]), 0.1
        return coach.AdaptOut(message="ok", changes=["c"], weeks=weeks, memory=[]), 0.1
    return fake


def _ai_weeks(monday: date):
    return [coach.Week(start=iso(monday), focus="base", sessions=[
        coach.Session(date=iso(TODAY), type="long", title="Tirada", distance_km=16, duration_min=100, target="Z2",
                      description="Larga", weather_note="33 °C: sal antes de las 9", best_time="07:00-09:00"),
        coach.Session(date=iso(TODAY + timedelta(days=1)), type="easy", title="Rodaje", distance_km=6, duration_min=40,
                      target="Z2", description="Suave")])]


def test_create_prompt_includes_time_and_weather_and_postcheck(monkeypatch):
    use_forecast(monkeypatch, TODAY)
    settings.set_availability({"weekly": {str(i): 60 for i in range(7)}, "days": {iso(TODAY + timedelta(days=1)): 0}})
    monday = TODAY - timedelta(days=TODAY.weekday())
    cap: dict = {}
    monkeypatch.setattr(coach, "_read_data", lambda: DATA)
    monkeypatch.setattr(coach, "_call", _fake_call(cap, lambda: _ai_weeks(monday)))
    race = TODAY + timedelta(days=60)
    st = coach.create({"date": iso(race), "goal": "Media maratón"})
    p = cap["prompt"]
    assert "TIEMPO DISPONIBLE POR DÍA" in p and "TIEMPO PREVISTO" in p
    avail = json.loads(p.split("TIEMPO DISPONIBLE POR DÍA")[1].split("\n", 1)[1].split("\n\n")[0])["tiempo_disponible_por_dia"]
    assert avail[iso(monday)] == 60 and avail[iso(TODAY + timedelta(days=1))] == 0 and avail[iso(race)] == 60
    assert len(avail) == (race - monday).days + 1  # todas las fechas planificadas
    fc = json.loads(p.split("TIEMPO PREVISTO")[1].split("\n", 1)[1])["tiempo_previsto"]
    assert [d["fecha"] for d in fc] == [iso(TODAY + timedelta(days=i)) for i in range(3)]
    assert fc[0]["avisos"] == ["calor"] and fc[0]["mejor_franja"].startswith("07:00-09:00")
    # comprobación sin IA: 100 min con 60 disponibles y 40 min un día sin tiempo
    warns = st["plan"]["timeWarnings"]
    assert [(w["date"], w["avail"], w["planned"]) for w in warns] == [(iso(TODAY), 60, 100), (iso(TODAY + timedelta(days=1)), 0, 40)]
    assert st["history"][-1]["timeWarnings"] == 2
    s0 = st["plan"]["weeks"][0]["sessions"][0]
    assert s0["weather_note"].startswith("33 °C") and s0["best_time"] == "07:00-09:00"


def test_adapt_prompt_and_no_blocks_without_settings(monkeypatch):
    monday = TODAY - timedelta(days=TODAY.weekday())
    cap: dict = {}
    monkeypatch.setattr(coach, "_read_data", lambda: DATA)
    monkeypatch.setattr(coach, "_call", _fake_call(cap, lambda: _ai_weeks(monday)))
    coach.save({"plan": {"goal": "10 km", "raceDate": iso(TODAY + timedelta(days=40)), "daysPerWeek": 4, "longRunDay": "domingo",
                         "weeks": [w.model_dump() for w in _ai_weeks(monday)]}})
    st = coach.adapt(force=True, data=DATA)
    # sin tiempo ni ciudad: el prompt es como siempre y no hay avisos
    assert "TIEMPO DISPONIBLE" not in cap["prompt"] and "TIEMPO PREVISTO" not in cap["prompt"]
    assert st["plan"]["timeWarnings"] == [] and "timeWarnings" not in st["history"][-1]
    # con tiempo y ciudad: los dos bloques, desde el lunes de esta semana
    use_forecast(monkeypatch, TODAY)
    settings.set_availability({"days": {iso(TODAY): 90}})
    st = coach.adapt(force=True, data=DATA)
    assert "TIEMPO DISPONIBLE POR DÍA" in cap["prompt"] and "TIEMPO PREVISTO" in cap["prompt"]
    assert f'"{iso(monday)}": null' in cap["prompt"] and f'"{iso(TODAY)}": 90' in cap["prompt"]
    assert [w["date"] for w in st["plan"]["timeWarnings"]] == [iso(TODAY)]
    assert "Tiempo disponible" in coach.SYSTEM and "weather_note" in coach.SYSTEM
    assert "lenguaje neutro" in coach.SYSTEM  # la regla de género se mantiene


# ---------------------------------------------------------------- zona de tu última carrera
def test_last_run_area():
    class S:
        def items(self, ds):
            return [("1", {"activityType": {"typeKey": "running"}, "startTimeLocal": "2026-10-01 08:00:00",
                           "startLatitude": 41.1234, "startLongitude": 1.2567}),
                    ("2", {"activityType": {"typeKey": "treadmill_running"}, "startTimeLocal": "2026-10-05 08:00:00",
                           "startLatitude": 40.0, "startLongitude": -3.0}),
                    ("3", {"activityType": {"typeKey": "trail_running"}, "startTimeLocal": "2026-10-03 08:00:00",
                           "startLatitude": 41.61, "startLongitude": 0.62}),
                    ("4", {"activityType": {"typeKey": "running"}, "startTimeLocal": "2026-10-09 08:00:00"})]
    assert weather.last_run_area(S()) == {"lat": 41.6, "lon": 0.6, "date": "2026-10-03"}  # redondeada (~10 km)


# ---------------------------------------------------------------- rutas de la API (S3, Lambda y SSM simulados)
class _ClientError(Exception):
    pass


class _NoSuchKey(_ClientError):
    pass


class FakeS3:
    class exceptions:  # noqa: N801
        ClientError = _ClientError
        NoSuchKey = _NoSuchKey

    def __init__(self):
        self.objs: dict[str, bytes] = {}

    def get_object(self, Bucket, Key):  # noqa: N803
        if Key not in self.objs:
            raise _NoSuchKey(Key)
        return {"Body": io.BytesIO(self.objs[Key])}

    def put_object(self, Bucket, Key, Body, **kw):  # noqa: N803
        self.objs[Key] = Body if isinstance(Body, bytes) else Body.encode()

    def head_object(self, Bucket, Key):  # noqa: N803
        if Key not in self.objs:
            raise _ClientError(Key)

    def download_file(self, Bucket, Key, Filename):  # noqa: N803
        if Key not in self.objs:
            raise _ClientError(Key)
        Path(Filename).write_bytes(self.objs[Key])

    def upload_file(self, Filename, Bucket, Key, ExtraArgs=None):  # noqa: N803
        self.objs[Key] = Path(Filename).read_bytes()

    def get_paginator(self, name):
        objs = self.objs

        class P:
            def paginate(self, Bucket, Prefix):  # noqa: N803
                return [{"Contents": [{"Key": k} for k in objs if k.startswith(Prefix)]}]
        return P()


class _Any:
    class exceptions:  # noqa: N801
        ParameterNotFound = type("ParameterNotFound", (Exception,), {})

    def __init__(self):
        self.calls = []

    def invoke(self, **kw):
        self.calls.append(kw)

    def get_parameter(self, **kw):
        return {"Parameter": {"Value": "clave-de-prueba"}}


@pytest.fixture
def api(tmp_path, monkeypatch):
    secret, origin, email = "s" * 64, "o" * 64, "persona@example.com"
    for k, v in {"BUCKET": "b", "SESSION_SECRET": secret, "ORIGIN_SECRET": origin, "OWNER_EMAIL": email,
                 "ANTHROPIC_KEY_PARAM": "/x", "AWS_LAMBDA_FUNCTION_NAME": "api"}.items():
        monkeypatch.setenv(k, v)
    s3 = FakeS3()
    fake = types.ModuleType("boto3")
    fake.client = lambda name: s3 if name == "s3" else _Any()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "boto3", fake)
    old_env = {k: os.environ.get(k) for k in ("TZ", "HOME")}
    spec = importlib.util.spec_from_file_location("api_handler_test", Path(__file__).parents[1] / "infra/lambda/api/handler.py")
    h = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(h)  # type: ignore[union-attr]
    for k, v in old_env.items():  # el handler fija la hora de Madrid y HOME para la Lambda: aquí se deja como estaba
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    time.tzset()
    root = tmp_path / "gs"
    monkeypatch.setattr(h, "ROOT", root)
    monkeypatch.setattr(h, "HOME", tmp_path / "home")
    for mod, name in ((settings, "settings.json"), (weather, "weather.json"), (wellness, "wellness.json"), (coach, "coach.json")):
        monkeypatch.setattr(mod, "STATE" if mod is coach else "PATH", root / "data" / name)
    uid = "u1"
    s3.objs["admin/users.json"] = json.dumps({"users": [{"email": email, "uid": uid, "role": "owner", "status": "active"}]}).encode()
    s3.objs[f"site/u/{uid}/data.js"] = ("window.__GARMIN__=" + json.dumps(DATA) + ";\n").encode()
    b64 = base64.urlsafe_b64encode(email.encode()).decode().rstrip("=")
    exp = str(int(time.time()) + 3600)
    cookie = f"gs_session={b64}.{exp}.{hmac.new(secret.encode(), f'{b64}.{exp}'.encode(), hashlib.sha256).hexdigest()}"

    def call(method, path, body=None, qs=""):
        ev = {"headers": {"x-origin-verify": origin}, "cookies": [cookie], "requestContext": {"http": {"method": method}},
              "rawPath": path, "rawQueryString": qs, "body": json.dumps(body) if body is not None else ""}
        r = h.handler(ev, None)
        return r["statusCode"], json.loads(r["body"])
    return types.SimpleNamespace(call=call, s3=s3, uid=uid)


def test_api_availability_route(api):
    tomorrow = iso(TODAY + timedelta(days=1))
    code, out = api.call("POST", "/api/settings/availability", {"weekly": {"1": 45, "6": 180}, "days": {tomorrow: 120}})
    assert code == 200 and out["availability"]["weekly"]["1"] == 45 and out["availability"]["days"] == {tomorrow: 120}
    saved = json.loads(api.s3.objs[f"users/{api.uid}/state/settings.json"])
    assert saved["availability"]["weekly"]["6"] == 180
    js = api.s3.objs[f"site/u/{api.uid}/data.js"].decode()
    assert '"availability"' in js and '"weather"' in js  # la web lo ve sin esperar a la sincronización
    code, out = api.call("POST", "/api/settings/availability", {"weekly": {"1": 900}})
    assert code == 400 and "480" in out["error"]


def test_api_location_and_geo_routes(api, monkeypatch):
    monkeypatch.setattr(weather, "_get", lambda url, params: (
        {"results": [{"name": "Tarragona", "admin1": "Cataluña", "country": "España", "latitude": 41.11, "longitude": 1.25}]}
        if url == weather.GEO_URL else raw_from(TODAY)))
    code, out = api.call("GET", "/api/geo", qs="q=Tarragona")
    assert code == 200 and out["results"][0]["label"] == "Tarragona, Cataluña, España"
    code, out = api.call("POST", "/api/settings/location", {"name": "Tarragona", "lat": 41.11, "lon": 1.25})
    assert code == 200 and out["weather"]["location"]["name"] == "Tarragona" and len(out["weather"]["days"]) == 3
    assert json.loads(api.s3.objs[f"users/{api.uid}/state/weather.json"])["days"][0]["flags"] == ["heat"]
    code, out = api.call("POST", "/api/settings/location", {"name": "X"})
    assert code == 400
    code, out = api.call("POST", "/api/settings/location", {"clear": True})
    assert code == 200 and out["weather"]["location"] is None and out["weather"]["days"] == []


def test_sync_only_uploads_state_it_changed(tmp_path, monkeypatch):
    """La sincronización no vuelve a subir coach.json si no lo ha tocado (no pisa un reajuste hecho por la API)."""
    monkeypatch.setenv("BUCKET", "b")
    s3 = FakeS3()
    fake = types.ModuleType("boto3")
    fake.client = lambda name: s3 if name == "s3" else _Any()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "boto3", fake)
    old_env = {k: os.environ.get(k) for k in ("TZ", "HOME", "GARMIN_STATS_ROOT")}
    spec = importlib.util.spec_from_file_location("sync_handler_test", Path(__file__).parents[1] / "infra/lambda/sync/handler.py")
    h = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(h)  # type: ignore[union-attr]
    for k, v in old_env.items():
        os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
    time.tzset()
    monkeypatch.setattr(h, "ROOT", tmp_path / "gs")
    (tmp_path / "gs" / "data" / "fit").mkdir(parents=True)
    (tmp_path / "gs" / "site" / "acts").mkdir(parents=True)
    sp = "users/u1/state/"
    s3.objs[sp + "coach.json"] = b'{"plan": 1}'
    s3.objs[sp + "weather.json"] = b'{"days": []}'
    h._pull("u1")
    s3.objs[sp + "coach.json"] = b'{"plan": 2, "job": {"status": "running"}}'  # la API lo cambia mientras tanto
    (tmp_path / "gs" / "data" / "weather.json").write_text('{"days": [1]}')  # la sincronización cambia la previsión
    (tmp_path / "gs" / "data" / "ai_cache.json").write_text("{}")  # archivo nuevo
    h._push("u1")
    assert s3.objs[sp + "coach.json"] == b'{"plan": 2, "job": {"status": "running"}}'
    assert s3.objs[sp + "weather.json"] == b'{"days": [1]}' and sp + "ai_cache.json" in s3.objs


# ---------------------------------------------------------------- respuesta de la IA cortada por max_tokens
def test_call_reports_truncation_and_uses_128k(monkeypatch):
    from garmin_stats import ai
    seen = {}

    class Stream:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def __iter__(self):
            coach.PlanOut.model_validate_json('{"summary": "x", "weeks": [')  # lo que hace el SDK con un JSON a medias

    class Client:
        class beta:  # noqa: N801
            class messages:  # noqa: N801
                @staticmethod
                def stream(**kw):
                    seen.update(kw)
                    return Stream()
    monkeypatch.setattr(coach, "_client", lambda: Client())
    monkeypatch.setattr(ai, "over_budget", lambda: False)
    monkeypatch.setattr(ai, "pick_model", lambda m: m)
    with pytest.raises(RuntimeError, match="incompleta"):
        coach._call(coach.AdaptOut, "hola", "plan-adapt")
    assert seen["max_tokens"] == 128000
