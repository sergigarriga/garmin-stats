"""Módulo Comida: registro, recálculo proporcional, balance frente a Garmin, objetivo con límites, ocultar calorías,
IA simulada (nunca se llama de verdad), tope de gasto y rutas de la API (la foto no se guarda en ningún sitio)."""

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

from garmin_stats import ai, coach, food, settings, weather, wellness

TODAY = date.today()
iso = lambda d: d.isoformat()  # noqa: E731
# Foto sintética mínima: cabecera JPEG + relleno (nunca fotos reales en las pruebas)
FAKE_JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + b"\x00" * 200 + b"\xff\xd9"


@pytest.fixture(autouse=True)
def tmp_state(tmp_path, monkeypatch):
    monkeypatch.setattr(food, "PATH", tmp_path / "food.json")
    monkeypatch.setattr(coach, "STATE", tmp_path / "coach.json")
    monkeypatch.setattr(settings, "PATH", tmp_path / "settings.json")
    monkeypatch.setattr(wellness, "PATH", tmp_path / "wellness.json")
    monkeypatch.setattr(weather, "PATH", tmp_path / "weather.json")
    monkeypatch.setattr(weather, "_get", lambda url, params: pytest.fail(f"llamada de red sin simular: {url}"))
    monkeypatch.setattr(ai, "DATA_DIR", tmp_path)
    monkeypatch.setattr(ai, "USAGE_LOG", tmp_path / "ai_usage_lambda.log")
    return tmp_path


def garmin_days(n=20, total=2600, active=400, today_cal=1100, today_active=150):
    """Días de Garmin: total = reposo (2200) + actividad. Hoy va a medias."""
    days = [{"d": iso(TODAY - timedelta(days=i)), "cal": total, "calActive": active} for i in range(n, 0, -1)]
    days.append({"d": iso(TODAY), "cal": today_cal, "calActive": today_active})
    return days


def DATA(**kw):  # noqa: N802
    return {"days": garmin_days(), "activities": [], "profile": {}, "weights": [{"d": iso(TODAY - timedelta(days=3)), "kg": 80.0}],
            **kw}


def item(name="Arroz", grams=200, kcal=260, p=5, c=56, f=1, fiber=1):
    return {"name": name, "grams": grams, "kcal": kcal, "protein": p, "carbs": c, "fat": f, "fiber": fiber}


def add(day=TODAY, meal="comida", items=None, **kw):
    e = food.new_entry({"date": iso(day), "time": "14:00", "meal": meal, "items": items or [item()], **kw})
    return food.upsert(e)


# ---------------------------------------------------------------- alimentos y recálculo
def test_clean_item_limits_and_kcal_from_macros():
    it = food.clean_item({"name": "  Pollo  a la plancha ", "grams": 150, "protein": 46, "carbs": 0, "fat": 5})
    assert it["name"] == "Pollo a la plancha" and it["kcal"] == 4 * 46 + 9 * 5
    big = food.clean_item({"name": "x", "kcal": 99999, "protein": -5, "grams": "abc"})
    assert big["kcal"] == food.LIMITS["kcal"] and big["protein"] == 0 and "grams" not in big


def test_merge_items_proportional_and_manual_overrides():
    old = [{**food.clean_item(item()), "id": "a"}, {**food.clean_item(item("Aceite", 10, 90, 0, 0, 10, 0)), "id": "b"}]
    # más gramos de arroz: todo en proporción
    out = food.merge_items(old, [{"id": "a", "grams": 300}, {"id": "b"}])
    assert out[0]["grams"] == 300 and out[0]["kcal"] == 390 and out[0]["carbs"] == 84 and out[0]["protein"] == 7.5
    assert out[1]["kcal"] == 90  # sin cambios
    # gramos y kcal a mano: las kcal mandan, el resto en proporción
    out = food.merge_items(old, [{"id": "a", "grams": 100, "kcal": 150, "protein": 5}])
    assert out[0]["kcal"] == 150 and out[0]["carbs"] == 28 and out[0]["protein"] == 2.5 and len(out) == 1  # aceite quitado
    # un macro a mano sin tocar las kcal: las kcal se ajustan con la diferencia (4/4/9)
    out = food.merge_items(old, [{"id": "a", "protein": 15}])
    assert out[0]["kcal"] == 260 + 40
    # alimento nuevo sin id
    out = food.merge_items(old, [{"id": "a"}, {"name": "Plátano", "grams": 120, "carbs": 27, "protein": 1.3, "fat": 0.4}])
    assert out[1]["name"] == "Plátano" and out[1]["kcal"] == round(4 * 27 + 4 * 1.3 + 9 * 0.4) and out[1]["id"]
    with pytest.raises(ValueError):
        food.merge_items(old, [{"name": "x"}] * (food.MAX_ITEMS + 1))


def test_entry_crud_scale_repeat_and_validation():
    e = add(note="sin aceite", title="Arroz blanco")
    assert food.find(e["id"])["note"] == "sin aceite"
    half = food.update_entry(e["id"], {"scale": 0.5, "meal": "cena", "fav": True})
    assert half["items"][0]["grams"] == 100 and half["items"][0]["kcal"] == 130 and half["meal"] == "cena" and half["fav"]
    with pytest.raises(ValueError, match="futura"):
        food.update_entry(e["id"], {"date": iso(TODAY + timedelta(days=1))})
    with pytest.raises(ValueError):
        food.update_entry(e["id"], {"meal": "brunch"})
    with pytest.raises(ValueError):
        food.update_entry(e["id"], {"scale": 50})
    rep = food.repeat_entry(e["id"], {"time": "21:00"})
    assert rep["id"] != e["id"] and rep["source"] == "repeat" and rep["items"][0]["kcal"] == 130 and rep["meal"] == "cena"
    assert rep["items"][0]["id"] != half["items"][0]["id"]
    fav = food.favorites()
    assert fav[0]["fav"] and len(fav) == 1  # una por título
    assert food.delete_entry(e["id"]) and not food.find(e["id"]) and not food.delete_entry(e["id"])
    with pytest.raises(LookupError):
        food.update_entry("nope", {"note": "x"})
    assert food.default_meal("08:15") == "desayuno" and food.default_meal("14:30") == "comida"
    assert food.default_meal("18:00") == "merienda" and food.default_meal("21:45") == "cena" and food.default_meal("12:00") == "picoteo"


# ---------------------------------------------------------------- balance
def test_balance_with_garmin_burned_data():
    food.set_prefs({"enabled": True})
    add(TODAY - timedelta(days=1), items=[item(kcal=2400, p=120, c=250, f=90)])
    add(TODAY - timedelta(days=2), items=[item(kcal=2000, p=100, c=200, f=80)])
    add(TODAY, items=[item(kcal=700, p=40, c=80, f=20)])
    v = food.view(DATA(), coach_state={})
    assert v["hasBurned"] and v["month"]["bmrKcal"] == 2200
    # hoy: reposo del día entero (2200) + la actividad que llevas (150), no los 1100 que lleva Garmin
    assert v["today"]["burnedKcal"] == 2350 and v["today"]["intakeKcal"] == 700 and v["today"]["partial"]
    # medias: solo días completos con algo apuntado (ayer y anteayer), hoy no cuenta
    assert v["week"]["loggedDays"] == 2 and v["week"]["intakeKcalAvg"] == 2200 and v["week"]["balanceKcalAvg"] == -400
    assert v["protein"]["gPerKgAvg7"] == round(110 / 80, 2) and v["protein"]["refG"] == [96, 128]
    assert len(v["month"]["days"]) == 30 and v["month"]["days"][-1]["d"] == iso(TODAY)


def test_balance_without_garmin_burned_data_shows_intake_only():
    food.set_prefs({"enabled": True})
    add(TODAY - timedelta(days=1), items=[item(kcal=1800)])
    data = DATA(days=[{"d": iso(TODAY - timedelta(days=1)), "steps": 3000}], weights=[])
    v = food.view(data, coach_state={})
    assert v["hasBurned"] is False and v["today"]["burnedKcal"] is None and v["month"]["bmrKcal"] is None
    assert v["week"]["intakeKcalAvg"] == 1800 and v["week"]["balanceKcalAvg"] is None and v["protein"] is None
    assert v["goal"] is None  # sin gasto no se inventa un objetivo
    v = food.view(None, coach_state={})  # sin data.js (aún conectando Garmin)
    assert v["hasBurned"] is False


def test_goal_guardrails():
    t = food.target({"mode": "maintain", "pace": "suave"}, 2600, 2200)
    assert t["targetKcal"] == 2600 and not t["limited"]
    t = food.target({"mode": "lose", "pace": "suave"}, 2600, 2200)
    assert t["targetKcal"] == 2340
    # moderado sería 2210, pero nunca por debajo del reposo (2200) ni más de un 20 % por debajo
    t = food.target({"mode": "lose", "pace": "moderado"}, 2600, 1800)
    assert t["targetKcal"] == 2210 and not t["limited"]
    t = food.target({"mode": "lose", "pace": "moderado"}, 2400, 2300)  # casi todo es reposo: se limita al reposo
    assert t["targetKcal"] == 2300 and t["limited"]
    t = food.target({"mode": "lose", "pace": "moderado"}, 3000, None)
    assert t["targetKcal"] >= 3000 * 0.8
    t = food.target({"mode": "gain", "pace": "moderado"}, 2600, 2200)
    assert t["targetKcal"] == 2860 and t["targetKcal"] <= 2600 * 1.15
    assert food.target(None, 2600, 2200) is None and food.target({"mode": "lose"}, None, None) is None
    with pytest.raises(ValueError):
        food.set_prefs({"goal": {"mode": "secar"}})
    with pytest.raises(ValueError):
        food.set_prefs({"goal": {"mode": "lose", "pace": "rapido"}})


def _keys(obj) -> set[str]:
    if isinstance(obj, dict):
        return set(obj) | set().union(*(_keys(v) for v in obj.values()))
    if isinstance(obj, list):
        return set().union(*(_keys(v) for v in obj)) if obj else set()
    return set()


def test_hide_calories_strips_every_kcal_number():
    food.set_prefs({"enabled": True, "hideCalories": True, "goal": {"mode": "lose", "pace": "suave"}})
    add(TODAY - timedelta(days=1), items=[item(kcal=2000, p=100)])
    v = food.view(DATA(), coach_state={})
    assert not [k for k in _keys(v) if "kcal" in k.lower()]
    assert v["entries"][0]["items"][0]["protein"] == 100 and v["week"]["proteinAvg"] == 100
    c = food.for_coach(DATA())
    assert c["oculta_calorias"] and "kcal_media_dia" not in c and "balance_medio_dia" not in c and c["proteina_media_g"] == 100


def test_fuel_tip_from_plan():
    plan = {"plan": {"weeks": [{"start": iso(TODAY), "sessions": [
        {"date": iso(TODAY), "type": "intervals", "title": "6 x 1 km"},
        {"date": iso(TODAY + timedelta(days=1)), "type": "easy", "title": "Rodaje"}]}]}}
    assert "6 x 1 km" in food.fuel_tip(plan)["text"]
    plan["plan"]["weeks"][0]["sessions"][0]["date"] = iso(TODAY - timedelta(days=1))
    plan["plan"]["weeks"][0]["sessions"].append({"date": iso(TODAY + timedelta(days=1)), "type": "long", "title": "Tirada 18 km"})
    tip = food.fuel_tip(plan)
    assert tip["when"] == "mañana" and "Tirada 18 km" in tip["text"]
    assert food.fuel_tip({}) is None


# ---------------------------------------------------------------- coach
def test_coach_profile_gets_nutrition_only_when_used():
    data = DATA()
    assert "nutricion_7_dias" not in coach.profile(data)
    add(TODAY - timedelta(days=1), items=[item(kcal=2400, p=120)])
    assert "nutricion_7_dias" not in coach.profile(data)  # apuntado pero el módulo está apagado
    food.set_prefs({"enabled": True})
    n = coach.profile(data)["nutricion_7_dias"]
    assert n["kcal_media_dia"] == 2400 and n["gasto_medio_dia_garmin"] == 2600 and n["proteina_g_por_kg"] == 1.5
    assert "nutricion_7_dias" in coach.SYSTEM and "No uses" not in coach.SYSTEM
    assert "neutro en cuanto al género" in coach.SYSTEM


# ---------------------------------------------------------------- IA (simulada)
class FakeResp:
    def __init__(self, parsed, stop="end_turn"):
        self.parsed_output = parsed
        self.stop_reason = stop
        self.usage = types.SimpleNamespace(input_tokens=1900, output_tokens=700, cache_creation_input_tokens=0,
                                           cache_read_input_tokens=0)


def fake_analysis(**kw):
    base = {"is_food": True, "title": "Tostada con tomate y café con leche", "confidence": "media",
            "assumptions": ["Estimo 1 cucharada de aceite"], "unclear": None,
            "items": [{"name": "Pan", "portion": "1 rebanada", "grams": 60, "kcal": 160, "protein_g": 5, "carbs_g": 30,
                       "fat_g": 1.5, "fiber_g": 2, "sugar_g": 2, "sat_fat_g": 0.3, "sodium_mg": 300},
                      {"name": "Aceite de oliva", "portion": "1 cucharada", "grams": 10, "kcal": 90, "protein_g": 0,
                       "carbs_g": 0, "fat_g": 10, "fiber_g": 0, "sugar_g": None, "sat_fat_g": 1.4, "sodium_mg": None}]}
    base.update(kw)
    return food.FoodAnalysis.model_validate(base)


def fake_client(seen: dict, resp):
    class Client:
        def __init__(self, **kw):
            seen["client"] = kw

        class beta:  # noqa: N801
            class messages:  # noqa: N801
                @staticmethod
                def parse(**kw):
                    seen.update(kw)
                    return resp
    return Client


def test_analyze_photo_logs_cost_and_uses_note(monkeypatch, tmp_path):
    seen: dict = {}
    monkeypatch.setattr(ai, "_api_key", lambda: "k")
    monkeypatch.setattr(food.anthropic, "Anthropic", fake_client(seen, FakeResp(fake_analysis())))
    e = food.new_entry({"meal": "desayuno", "time": "08:00", "note": "con 1 cucharada de aceite"})
    out, cost, model = food.analyze(e, FAKE_JPEG, "image/jpeg")
    content = seen["messages"][0]["content"]
    assert content[0]["type"] == "image" and base64.b64decode(content[0]["source"]["data"]) == FAKE_JPEG
    assert "con 1 cucharada de aceite" in content[1]["text"] and model == "claude-sonnet-5-5"
    assert seen["output_format"] is food.FoodAnalysis and seen["client"]["timeout"] <= 50
    assert cost == pytest.approx(1900 * 2e-6 + 700 * 10e-6)
    log = (tmp_path / "ai_usage_lambda.log").read_text()
    assert "kind=comida" in log and "model=claude-sonnet-5-5" in log
    food.apply_analysis(e, out, cost, model, from_photo=True)
    assert e["status"] == "ok" and e["fromPhoto"] and food.totals(e["items"])["kcal"] == 250 and e["items"][1]["fat"] == 10
    # no es comida
    with pytest.raises(food.FoodAIError, match="No parece comida"):
        food.apply_analysis(food.new_entry({}), fake_analysis(is_food=False, items=[]), 0, model, True)


def test_reanalyze_without_photo_sends_previous_items(monkeypatch):
    seen: dict = {}
    monkeypatch.setattr(ai, "_api_key", lambda: "k")
    monkeypatch.setattr(food.anthropic, "Anthropic", fake_client(seen, FakeResp(fake_analysis())))
    e = add(items=[item("Macarrones", 250)], note="media ración")
    food.analyze(e)
    text = seen["messages"][0]["content"][0]
    assert text["type"] == "text" and "Macarrones" in text["text"] and "media ración" in text["text"]


def test_analyze_budget_exhausted_and_refusal(monkeypatch):
    monkeypatch.setattr(ai, "over_budget", lambda: True)
    with pytest.raises(food.BudgetExceeded, match="a mano"):
        food.analyze(food.new_entry({"text": "café"}))
    monkeypatch.setattr(ai, "over_budget", lambda: False)
    monkeypatch.setattr(ai, "_api_key", lambda: "k")
    monkeypatch.setattr(food.anthropic, "Anthropic", fake_client({}, FakeResp(None, "refusal")))
    with pytest.raises(food.FoodAIError):
        food.analyze(food.new_entry({"text": "café"}))


def test_decode_photo_limits():
    img, mt = food.decode_photo("data:image/jpeg;base64," + base64.b64encode(FAKE_JPEG).decode())
    assert img == FAKE_JPEG and mt == "image/jpeg"
    with pytest.raises(OverflowError):
        food.decode_photo(base64.b64encode(b"\xff\xd8\xff" + b"0" * (food.MAX_PHOTO_BYTES + 10)).decode())
    with pytest.raises(ValueError):
        food.decode_photo(base64.b64encode(b"GIF89a....").decode())
    with pytest.raises(ValueError):
        food.decode_photo("no es base64!!")


# ---------------------------------------------------------------- API
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
        self.writes: list[str] = []

    def get_object(self, Bucket, Key):  # noqa: N803
        if Key not in self.objs:
            raise _NoSuchKey(Key)
        return {"Body": io.BytesIO(self.objs[Key])}

    def put_object(self, Bucket, Key, Body, **kw):  # noqa: N803
        self.writes.append(Key)
        self.objs[Key] = Body if isinstance(Body, bytes) else Body.encode()

    def head_object(self, Bucket, Key):  # noqa: N803
        if Key not in self.objs:
            raise _ClientError(Key)

    def download_file(self, Bucket, Key, Filename):  # noqa: N803
        if Key not in self.objs:
            raise _ClientError(Key)
        Path(Filename).write_bytes(self.objs[Key])

    def upload_file(self, Filename, Bucket, Key, ExtraArgs=None):  # noqa: N803
        self.writes.append(Key)
        self.objs[Key] = Path(Filename).read_bytes()


class _Any:
    class exceptions:  # noqa: N801
        ParameterNotFound = type("ParameterNotFound", (Exception,), {})

    def invoke(self, **kw):
        pass

    def get_parameter(self, **kw):
        return {"Parameter": {"Value": "clave-de-prueba"}}


@pytest.fixture
def api(tmp_path, monkeypatch):
    secret, origin = "s" * 64, "o" * 64
    owner, friend = "persona@example.com", "amiga@example.com"
    for k, v in {"BUCKET": "b", "SESSION_SECRET": secret, "ORIGIN_SECRET": origin, "OWNER_EMAIL": owner,
                 "ANTHROPIC_KEY_PARAM": "/x", "AWS_LAMBDA_FUNCTION_NAME": "api"}.items():
        monkeypatch.setenv(k, v)
    s3 = FakeS3()
    fake = types.ModuleType("boto3")
    fake.client = lambda name: s3 if name == "s3" else _Any()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "boto3", fake)
    old_env = {k: os.environ.get(k) for k in ("TZ", "HOME", "GARMIN_STATS_UID", "GARMIN_STATS_AI_BUDGET", "GARMIN_STATS_ADAPT_MODEL")}
    spec = importlib.util.spec_from_file_location("api_handler_food_test", Path(__file__).parents[1] / "infra/lambda/api/handler.py")
    h = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(h)  # type: ignore[union-attr]
    root = tmp_path / "gs"
    monkeypatch.setattr(h, "ROOT", root)
    monkeypatch.setattr(h, "HOME", tmp_path / "home")
    for mod, name in ((settings, "settings.json"), (weather, "weather.json"), (wellness, "wellness.json"),
                      (coach, "coach.json"), (food, "food.json")):
        monkeypatch.setattr(mod, "STATE" if mod is coach else "PATH", root / "data" / name)
    monkeypatch.setattr(ai, "DATA_DIR", root / "data")
    monkeypatch.setattr(ai, "USAGE_LOG", root / "data" / "ai_usage_lambda.log")
    s3.objs["admin/users.json"] = json.dumps({"users": [
        {"email": owner, "uid": "u1", "role": "owner", "status": "active"},
        {"email": friend, "uid": "u2", "role": "friend", "status": "active"}]}).encode()
    for uid in ("u1", "u2"):
        s3.objs[f"site/u/{uid}/data.js"] = ("window.__GARMIN__=" + json.dumps(DATA()) + ";\n").encode()

    def cookie(email):
        b64 = base64.urlsafe_b64encode(email.encode()).decode().rstrip("=")
        exp = str(int(time.time()) + 3600)
        return f"gs_session={b64}.{exp}.{hmac.new(secret.encode(), f'{b64}.{exp}'.encode(), hashlib.sha256).hexdigest()}"

    def call(method, path, body=None, who=owner, raw=None):
        ev = {"headers": {"x-origin-verify": origin}, "cookies": [cookie(who)] if who else [],
              "requestContext": {"http": {"method": method}}, "rawPath": path, "rawQueryString": "",
              "body": raw if raw is not None else (json.dumps(body) if body is not None else "")}
        r = h.handler(ev, None)
        return r["statusCode"], json.loads(r["body"])
    yield types.SimpleNamespace(call=call, s3=s3, friend=friend, h=h)
    for k, v in old_env.items():  # el handler fija la hora de Madrid, HOME y la persona: aquí se deja como estaba
        os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
    time.tzset()


def _mock_ai(monkeypatch, seen=None, analysis=None):
    def fake(entry, image=None, media_type="image/jpeg"):
        if seen is not None:
            seen.append({"image": image, "note": entry.get("note"), "text": entry.get("text")})
        return analysis or fake_analysis(), 0.014, "claude-sonnet-5-5"
    monkeypatch.setattr(food, "analyze", fake)


def test_api_food_flow_never_stores_the_photo(api, monkeypatch):
    seen: list = []
    _mock_ai(monkeypatch, seen)
    code, out = api.call("GET", "/api/food")
    assert code == 200 and out["prefs"]["enabled"] is False and out["entries"] == []
    code, out = api.call("POST", "/api/food/add", {"text": "café"})
    assert code == 409  # opt-in: apagado hasta que se activa
    code, out = api.call("POST", "/api/food/prefs", {"enabled": True})
    assert code == 200 and out["prefs"]["enabled"]
    photo = base64.b64encode(FAKE_JPEG).decode()
    api.s3.writes.clear()
    code, out = api.call("POST", "/api/food/add", {"photo": photo, "note": "sin azúcar", "meal": "desayuno", "time": "08:10"})
    assert code == 200 and out["entry"]["status"] == "ok" and out["entry"]["fromPhoto"] and out["entry"]["totals"]["kcal"] == 250
    assert seen[0]["image"] == FAKE_JPEG and seen[0]["note"] == "sin azúcar"
    # en S3 solo se escribe el JSON de estado: ni la foto ni ningún objeto nuevo fuera de state/
    assert set(api.s3.writes) == {"users/u1/state/food.json"}
    assert not any(k.endswith((".jpg", ".jpeg", ".png", ".webp")) or "/food/" in k for k in api.s3.objs)
    assert all(FAKE_JPEG not in v and photo.encode() not in v for v in api.s3.objs.values())
    saved = json.loads(api.s3.objs["users/u1/state/food.json"])
    assert len(saved["entries"]) == 1 and "photo" not in json.dumps(saved).lower().replace("fromphoto", "")
    eid = out["entry"]["id"]
    # edición: gramos del pan x2 → kcal del pan x2
    pan = out["entry"]["items"][0]
    code, out = api.call("POST", "/api/food/update", {"id": eid, "items": [{**pan, "grams": 120}, out["entry"]["items"][1]]})
    assert code == 200 and out["entry"]["totals"]["kcal"] == 410 and out["entry"]["edited"]
    # reanalizar con otra nota: sin foto (no se guardó), parte de los alimentos
    code, out = api.call("POST", "/api/food/reanalyze", {"id": eid, "note": "sin aceite"})
    assert code == 200 and seen[-1]["image"] is None and seen[-1]["note"] == "sin aceite" and out["entry"]["id"] == eid
    # repetir sin IA
    n = len(seen)
    code, out = api.call("POST", "/api/food/repeat", {"id": eid})
    assert code == 200 and len(seen) == n and len(out["entries"]) == 2
    # manual (sin IA)
    code, out = api.call("POST", "/api/food/add", {"analyze": False, "items": [{"name": "Plátano", "grams": 120, "carbs": 27}]})
    assert code == 200 and out["entry"]["status"] == "manual" and len(seen) == n
    code, out = api.call("POST", "/api/food/add", {"analyze": False, "text": "algo"})
    assert code == 400
    code, out = api.call("POST", "/api/food/delete", {"id": eid})
    assert code == 200 and all(e["id"] != eid for e in out["entries"])
    code, out = api.call("POST", "/api/food/delete", {"id": eid})
    assert code == 404


def test_api_food_payload_limits(api, monkeypatch):
    _mock_ai(monkeypatch)
    api.call("POST", "/api/food/prefs", {"enabled": True})
    code, out = api.call("POST", "/api/food/add", raw="x" * 2_300_000)
    assert code == 413
    big = base64.b64encode(b"\xff\xd8\xff" + b"0" * (food.MAX_PHOTO_BYTES + 100)).decode()
    code, out = api.call("POST", "/api/food/add", {"photo": big})
    assert code == 413 and "1,5 MB" in out["error"]
    code, out = api.call("POST", "/api/food/add", {"photo": base64.b64encode(b"%PDF-1.4 ...").decode()})
    assert code == 400
    code, out = api.call("POST", "/api/food/add", {})
    assert code == 400
    code, out = api.call("POST", "/api/food/add", {"text": "café", "date": iso(TODAY + timedelta(days=2))})
    assert code == 400 and "futura" in out["error"]


def test_api_food_ai_failure_saves_nothing_and_budget_fallback(api, monkeypatch):
    api.call("POST", "/api/food/prefs", {"enabled": True})
    real = food.analyze

    def boom(*a, **k):
        raise food.FoodAIError("La IA no responde. Pulsa Reintentar.")
    monkeypatch.setattr(food, "analyze", boom)
    code, out = api.call("POST", "/api/food/add", {"photo": base64.b64encode(FAKE_JPEG).decode()})
    assert code == 502 and "Reintentar" in out["error"]
    assert json.loads(api.s3.objs["users/u1/state/food.json"]).get("entries", []) == []
    monkeypatch.setattr(food, "analyze", real)  # el de verdad, que mira el tope antes de llamar a la IA
    monkeypatch.setattr(ai, "over_budget", lambda: True)
    code, out = api.call("POST", "/api/food/add", {"text": "lentejas"})
    assert code == 409 and out["budget"] and "a mano" in out["error"]
    code, out = api.call("GET", "/api/food")
    assert out["budget"]["over"] is True
    code, out = api.call("POST", "/api/food/add", {"analyze": False, "items": [{"name": "Lentejas", "grams": 300, "kcal": 350}]})
    assert code == 200 and out["entry"]["status"] == "manual"


def test_api_food_auth_and_ownership(api, monkeypatch):
    _mock_ai(monkeypatch)
    code, _ = api.call("GET", "/api/food", who=None)
    assert code == 401
    api.call("POST", "/api/food/prefs", {"enabled": True})
    code, out = api.call("POST", "/api/food/add", {"text": "tostada con tomate"})
    eid = out["entry"]["id"]
    # otra persona no ve ni toca las comidas del dueño
    code, out = api.call("GET", "/api/food", who=api.friend)
    assert code == 200 and out["entries"] == [] and out["prefs"]["enabled"] is False
    api.call("POST", "/api/food/prefs", {"enabled": True}, who=api.friend)
    for path in ("/api/food/update", "/api/food/delete", "/api/food/repeat", "/api/food/reanalyze"):
        code, out = api.call("POST", path, {"id": eid, "note": "x"}, who=api.friend)
        assert code == 404, path
    assert "users/u2/state/food.json" in api.s3.objs
    assert len(json.loads(api.s3.objs["users/u1/state/food.json"])["entries"]) == 1
    assert json.loads(api.s3.objs["users/u2/state/food.json"]).get("entries", []) == []


def test_api_food_hide_calories(api, monkeypatch):
    _mock_ai(monkeypatch)
    api.call("POST", "/api/food/prefs", {"enabled": True, "hideCalories": True})
    code, out = api.call("POST", "/api/food/add", {"text": "tostada"})
    assert code == 200 and not [k for k in _keys(out) if "kcal" in k.lower()]
    code, out = api.call("POST", "/api/food/prefs", {"goal": {"mode": "lose", "pace": "moderado"}})
    assert code == 200 and out["goal"] is not None and "targetKcal" not in out["goal"]
