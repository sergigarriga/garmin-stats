"""Plan de comidas y compra semanal: formatos y envases, emparejamiento con el catálogo (multipacks, piezas, a peso,
exclusiones), totales, presupuesto, nutrición, IA simulada, catálogo en S3 (simulado), refresco semanal (HTTP simulado,
para ante 429) y rutas de la API. Catálogo sintético mínimo: nunca datos reales del supermercado en el repositorio."""

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
import urllib.error
from datetime import date, timedelta
from pathlib import Path

import pytest

from garmin_stats import ai, catalog as C, coach, food, settings, shopping as S, weather, wellness

TODAY = date.today()
iso = lambda d: d.isoformat()  # noqa: E731
NUT = {"kcal": 350, "protein": 7, "carbs": 77, "fat": 1, "sugars": 0, "satFat": 0, "fiber": 1, "salt": 0}


def P(pid, name, cat, fmt, price=None, per=None, pack=None, approx=False, brand="Casera", nut=None, flag="", ean=None):  # noqa: N802
    return {"id": pid, "name": name, "cat": cat, "brand": brand, "fmt": fmt, "pack": pack, "price": price, "unitPrice": per,
            "unitPriceUnit": "kg", "perKgL": per, "approx": approx, "url": f"https://tienda.example/product/{pid}/x",
            "ean": ean, "nut": nut, "nutSrc": "openfoodfacts" if nut else None, "nutFlag": flag}


FV, CARNE = "Fruta y verdura > Fruta > Plátanos", "Carne > Aves y pollo > Pollo"
CATALOG = {"meta": {"date": "2026-11-02", "postcode": "28001", "wh": "1", "count": 0}, "products": [
    P("1", "Arroz redondo Casera", "Arroz, legumbres y pasta > Arroz > Arroz", "1 kg", 1.20, 1.2, nut=NUT),
    P("2", "Arroz redondo Casera", "Arroz, legumbres y pasta > Arroz > Arroz", "0.5 kg", 0.70, 1.4, nut=NUT),
    P("3", "Arroz vasito microondas", "Arroz, legumbres y pasta > Arroz > Arroz", "2 x 0.125 kg", 1.50, 6.0),
    P("10", "Plátano", FV, "0.15 kg", 0.30, 2.0, pack="Pieza", approx=True,
      nut={"kcal": 90, "protein": 1, "carbs": 23, "fat": 0.3}),
    P("11", "Plátanos", FV, "1 kg", 1.90, 1.9),
    P("20", "Filetes pechuga de pollo", CARNE, "0.5 kg", 4.00, 8.0, approx=True, nut={"kcal": 110, "protein": 23, "carbs": 0, "fat": 2}),
    P("21", "Pechuga de pollo rebozada", CARNE, "0.4 kg", 2.00, 5.0),
    P("22", "Pechugas enteras familiar de pollo", CARNE, "1.2 kg", 7.20, 6.0, approx=True,
      nut={"kcal": 110, "protein": 23, "carbs": 0, "fat": 2}),
    P("30", "Leche semidesnatada Casera", "Huevos, leche y mantequilla > Leche y bebidas vegetales > Leche semidesnatada",
      "6 x 1 l", 5.10, 0.85, nut={"kcal": 46, "protein": 3.2, "carbs": 4.7, "fat": 1.6}),
    P("31", "Leche semidesnatada sin lactosa Casera", "Huevos, leche y mantequilla > Leche y bebidas vegetales > Leche sin lactosa",
      "1 l", 0.95, 0.95),
    P("40", "Huevos grandes L", "Huevos, leche y mantequilla > Huevos > Huevos", "12 ud", 3.00, None),
    P("41", "Huevos grandes L", "Huevos, leche y mantequilla > Huevos > Huevos", "6 ud", 1.80, None),
    P("50", "Tomate frito Casera", "Conservas, caldos y cremas > Tomate > Tomate frito", "3 x 0.4 kg", 1.35, 1.125),
    P("60", "Sardina limpia", "Marisco y pescado > Pescado fresco > Sardina", "a peso (desde 0.2 kg)", None, 6.0),
    P("61", "Atún claro natural Casera", "Conservas, caldos y cremas > Atún y otras conservas de pescado > Atún", "3 x 0.08 kg",
      2.40, 10.0),
    P("70", "Aceite de oliva virgen extra Casera", "Aceite, especias y salsas > Aceite, vinagre y sal > Aceite de oliva", "1 l", 4.50, 4.5,
      nut={"kcal": 900, "protein": 0, "carbs": 0, "fat": 100}, flag="dudoso: kcal no cuadran con los macros"),
    P("80", "Macarrón Casera", "Arroz, legumbres y pasta > Pasta y fideos > Pasta", "1 kg", 1.10, 1.1),
    P("81", "Macarrón sin gluten Casera", "Arroz, legumbres y pasta > Pasta y fideos > Pasta sin gluten", "0.5 kg", 1.90, 3.8),
    P("90", "Nuez natural Casera", "Aperitivos > Frutos secos y fruta desecada > Frutos secos", "0.2 kg", 2.0, 10.0),
    P("91", "Queso curado mezcla Agrandado", "Charcutería y quesos > Queso curado, semicurado y tierno > Queso curado", "0.4 kg", 4.0, 10.0),
]}


def prefs(**kw):
    return S.prefs({"prefs": {"enabled": True, **kw}})


@pytest.fixture(autouse=True)
def tmp_state(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "PATH", tmp_path / "shopping.json")
    monkeypatch.setattr(food, "PATH", tmp_path / "food.json")
    monkeypatch.setattr(coach, "STATE", tmp_path / "coach.json")
    monkeypatch.setattr(ai, "DATA_DIR", tmp_path)
    monkeypatch.setattr(ai, "USAGE_LOG", tmp_path / "ai_usage_lambda.log")
    C._CACHE.clear()
    S._IDX.clear()
    return tmp_path


def line(name, amount, unit, p=None, cat=CATALOG, **kw):
    return S.match({"key": name, "name": name, "amount": amount, "unit": unit}, cat, p or prefs(), **kw)


# ---------------------------------------------------------------- formatos y envases
def test_parse_format_variants():
    assert C.parse_format("0.5 kg") == {"kind": "g", "size": 500}
    assert C.parse_format("6 x 1 l") == {"kind": "ml", "size": 6000, "units": 6}
    assert C.parse_format("3 x 0.4 kg") == {"kind": "g", "size": 1200, "units": 3}
    assert C.parse_format("12 ud") == {"kind": "ud", "size": 12}
    assert C.parse_format("a peso (desde 0.2 kg)") == {"kind": "weight", "min": 200}
    assert C.parse_format(None) is None and C.parse_format("raro") is None


def test_packs_cheapest_cover_and_exclusions():
    ln = line("arroz", 700, "g")
    assert ln["product"]["id"] == "1" and ln["packs"] == 1 and ln["cost"] == 1.2 and ln["leftover"] == 300
    assert ln["usedCost"] == 0.84  # 700 g de un paquete de 1 kg
    ln = line("arroz", 1500, "g")  # 2 kg en dos paquetes de 1 kg sale mejor que 3 de medio
    assert ln["product"]["id"] == "1" and ln["packs"] == 2 and ln["cost"] == 2.4
    assert {a["id"] for a in ln["alternatives"]} == {"2"}  # el vasito de microondas no vale para "arroz"
    ln = line("pechuga de pollo", 600, "g")
    assert ln["product"]["id"] != "21"  # rebozada: no
    assert all(a["id"] != "21" for a in ln["alternatives"])
    assert line("queso curado", 300, "g")["product"]["id"] == "91"  # "dado" de la marca "Agrandado" no es "en dados"


def test_multipacks_units_pieces_and_by_weight():
    ln = line("leche semidesnatada", 3000, "ml")  # un pack de 6 x 1 l cubre 3 l
    assert ln["packs"] == 1 and ln["cost"] == 5.1 and ln["leftover"] == 3000
    ln = line("tomate frito", 1500, "g")  # 3 x 0,4 kg = 1,2 kg por pack → 2 packs
    assert ln["packs"] == 2 and ln["cost"] == 2.7
    ln = line("huevos", 14, "ud")  # 3 medias docenas (5,40 €) frente a 2 docenas (6 €)
    assert ln["product"]["id"] == "41" and ln["packs"] == 3 and ln["cost"] == 5.4
    ln = line("huevos", 300, "g")  # 300 g ≈ 5 huevos (60 g) → media docena
    assert ln["product"]["id"] == "41" and ln["packs"] == 1
    ln = line("plátano", 5, "ud")  # piezas sueltas: 5 plátanos
    assert ln["product"]["id"] == "10" and ln["packs"] == 5 and ln["cost"] == 1.5 and ln["approx"]
    ln = line("plátano", 2000, "g")  # 2 kg: la bolsa de 1 kg x2 (3,80 €) frente a 14 piezas (4,20 €)
    assert ln["product"]["id"] == "11" and ln["packs"] == 2
    ln = line("sardinas", 150, "g")  # a peso con mínimo 200 g
    assert ln["byWeight"] and ln["qty"] == 200 and ln["cost"] == 1.2 and ln["packs"] is None


def test_unknown_ingredient_uses_text_search_and_unmatched_gets_search_link():
    ln = line("Nuez natural", 200, "g")
    assert ln["product"]["id"] == "90"
    ln = line("Tofu ahumado", 200, "g")
    assert ln["product"] is None and ln["searchUrl"].endswith("Tofu%20ahumado")


def test_clean_ingredients_merges_and_respects_exclusions():
    raw = [{"name": "Pechuga de pollo", "amount": 400, "unit": "g"}, {"name": "pechugas de pollo", "amount": 200, "unit": "g"},
           {"name": "Atún en lata", "amount": 160, "unit": "g"}, {"name": "Nueces", "amount": 100, "unit": "g"},
           {"name": "Huevos", "amount": 6, "unit": "ud"}, {"name": "huevos", "amount": 120, "unit": "g"},
           {"name": "Arroz", "amount": 0, "unit": "g"}]
    items, warns = S.clean_ingredients(raw, prefs())
    chicken = next(i for i in items if i["name"] == "pechuga de pollo")
    assert chicken["amount"] == 600 and not warns
    assert {i["key"] for i in items if i["name"] == "huevos"} == {"huevos", "huevos (g)"}
    assert not any(i["name"] == "arroz" for i in items)  # cantidad 0: fuera
    items, warns = S.clean_ingredients(raw, prefs(diet={"vegetariano": True}))
    assert not any(i["name"] in ("pechuga de pollo", "atún en lata") for i in items) and len(warns) == 3
    items, warns = S.clean_ingredients(raw, prefs(diet={"noPescado": True}, allergies="frutos secos"))
    names = {i["name"] for i in items}
    assert "atún en lata" not in names and "nueces" not in names and "pechuga de pollo" in names
    assert any("alergias" in w for w in warns)


def test_lactose_and_gluten_free_variants():
    ln = line("leche semidesnatada", 1000, "ml", prefs(diet={"sinLactosa": True}))
    assert ln["product"]["id"] == "31" and ln["warning"] is None
    ln = line("pasta", 400, "g", prefs(diet={"sinGluten": True}))
    assert ln["product"]["id"] == "81"
    ln = line("pan", 2, "ud", prefs(diet={"sinGluten": True}))  # no hay pan sin gluten en este catálogo
    assert ln["product"] is None and "sin gluten" in ln["warning"]


# ---------------------------------------------------------------- lista, totales, presupuesto, nutrición
def plan_with(items, **kw):
    its, _ = S.clean_ingredients(items, prefs())
    return {"start": iso(TODAY), "ingredients": its, "people": 1, "meals": ["comida", "cena"],
            "days": [{"date": iso(TODAY), "kcal_per_person": 1500, "protein_g_per_person": 90, "meals": []}], **kw}


ITEMS = [{"name": "arroz", "amount": 700, "unit": "g"}, {"name": "plátano", "amount": 5, "unit": "ud"},
         {"name": "pechuga de pollo", "amount": 600, "unit": "g"}, {"name": "aceite de oliva virgen extra", "amount": 200, "unit": "ml"},
         {"name": "Tofu ahumado", "amount": 200, "unit": "g"}]


def test_build_list_totals_pantry_removed_checked_and_swap():
    plan = plan_with(ITEMS)
    out = S.build_list(plan, {}, CATALOG, prefs())
    lines = {i["key"]: i for g in out["groups"] for i in g["items"]}
    assert lines["aceite de oliva virgen extra"]["skip"] and lines["aceite de oliva virgen extra"]["pantry"]
    assert out["groups"][-1]["aisle"].startswith("Despensa")
    base = round(1.2 + 1.5 + lines["pechuga de pollo"]["cost"], 2)
    assert out["total"] == base and out["items"] == 4 and out["unmatched"] == 1
    assert out["usedTotal"] == round(0.84 + 1.5 + lines["pechuga de pollo"]["usedCost"], 2) < out["total"]
    out = S.build_list(plan, {"need": ["aceite de oliva virgen extra"], "removed": ["plátano"], "checked": ["arroz"]}, CATALOG, prefs())
    assert out["total"] == round(base - 1.5 + 4.5, 2) and out["checkedTotal"] == 1.2
    out = S.build_list(plan, {"swaps": {"arroz": "2"}}, CATALOG, prefs())
    ln = next(i for g in out["groups"] for i in g["items"] if i["key"] == "arroz")
    assert ln["product"]["id"] == "2" and ln["packs"] == 2 and ln["swapped"] and ln["cost"] == 1.4
    assert out["total"] == round(base + 0.2, 2)


def test_two_ingredients_on_the_same_product_share_one_line():
    plan = plan_with([{"name": "arroz", "amount": 400, "unit": "g"}, {"name": "arroz redondo", "amount": 300, "unit": "g"},
                      {"name": "Arroz redondo Casera", "amount": 600, "unit": "g"}])
    out = S.build_list(plan, {}, CATALOG, prefs())
    lines = [i for g in out["groups"] for i in g["items"]]
    assert len(lines) == 1 and lines[0]["amount"] == 1300 and lines[0]["packs"] == 2 and out["total"] == 2.4
    assert [a["name"] for a in lines[0]["also"]] == ["Arroz redondo Casera"]


def test_budget_fallback_switches_to_cheapest_and_flags_over():
    plan = plan_with([{"name": "pechuga de pollo", "amount": 1000, "unit": "g"}])
    normal = S.build_list(plan, {}, CATALOG, prefs())
    assert normal["budget"] is None and normal["total"] == 7.2  # sin presupuesto
    cheap = S.build_list(plan, {}, CATALOG, prefs(budget=10))
    assert cheap["budget"]["mode"] in ("normal", "ahorro") and not cheap["budget"]["over"]
    tight = S.build_list(plan, {}, CATALOG, prefs(budget=5))
    assert tight["budget"]["over"] and tight["budget"]["biggest"][0]["name"] == "pechuga de pollo"
    # El modo normal prefiere el nombre que mejor encaja aunque cueste algo más; el de ahorro, lo más barato
    cat = {"meta": {}, "products": [P("a", "Filetes pechuga de pollo", CARNE, "0.5 kg", 4.0, 8.0),
                                    P("b", "Solomillo de pollo", CARNE, "0.5 kg", 3.7, 7.4)]}
    plan = plan_with([{"name": "pechuga de pollo", "amount": 500, "unit": "g"}])
    assert S.build_list(plan, {}, cat, prefs())["groups"][0]["items"][0]["product"]["id"] == "a"
    out = S.build_list(plan, {}, cat, prefs(budget=3.9))
    assert out["budget"]["mode"] == "ahorro" and out["total"] == 3.7 and not out["budget"]["over"]


def test_nutrition_summary_skips_doubtful_values_and_hides_kcal():
    plan = plan_with(ITEMS)
    st = {"prefs": {"enabled": True, "meals": ["comida", "cena"]}, "plan": {**plan, "context": {"days": [{"kcal": 2500}],
                                                                                              "proteinRefG": [96, 128]}}}
    v = S.view(CATALOG, st, {})
    n = v["nutrition"]
    # arroz 700 g (2450 kcal) + 5 plátanos (675 g de... 0,15 kg cada uno: 675 kcal) + pollo 600 g (660); el aceite es dudoso
    assert n["kcalDay"] == round((2450 + 675 + 660) / 7) and n["linesWithData"] == 3 and n["lines"] == 5
    assert n["targetKcalDay"] == 2500 and n["targetMealsKcalDay"] == round(2500 * 0.65 / 10) * 10 and n["proteinRefG"] == [96, 128]
    assert "Total aprox." in v["text"] and "Mercadona" in v["text"]
    hidden = S.view(CATALOG, st, {"prefs": {"hideCalories": True}})
    assert "kcal" not in json.dumps(hidden) and hidden["nutrition"]["proteinDay"] == n["proteinDay"]


def test_prefs_validation_and_disable_keeps_plan():
    S.set_prefs({"enabled": True, "people": 2, "meals": ["cena", "desayuno"], "budget": 60, "cooking": "rapido",
                 "diet": {"vegetariano": True}, "allergies": "  cacahuete   "})
    p = S.prefs()
    assert p["people"] == 2 and p["meals"] == ["desayuno", "cena"] and p["budget"] == 60 and p["diet"]["vegetariano"]
    assert p["allergies"] == "cacahuete" and p["cooking"] == "rapido"
    for bad in ({"people": 5}, {"meals": []}, {"meals": ["merienda"]}, {"budget": 5}, {"cooking": "lento"}):
        with pytest.raises(ValueError):
            S.set_prefs(bad)
    st = S.load()
    st["plan"] = plan_with(ITEMS)
    S.save(st)
    S.set_prefs({"enabled": False})
    assert S.load()["plan"] and not S.prefs()["enabled"]
    S.set_prefs({"budget": None})
    assert S.prefs()["budget"] is None


# ---------------------------------------------------------------- contexto y semana
def test_week_start_and_context_hard_days_and_guardrails():
    mon = TODAY - timedelta(days=TODAY.weekday())
    assert S.week_start(mon) == mon and S.week_start(mon + timedelta(days=4)) == mon + timedelta(days=7)
    assert S.week_start(mon, "monday") == mon + timedelta(days=7) and S.week_start(mon + timedelta(days=5), "today") == mon + timedelta(days=5)
    days = [{"d": iso(TODAY - timedelta(days=i)), "cal": 2600, "calActive": 400} for i in range(20, 0, -1)]
    start = TODAY + timedelta(days=1)
    plan = {"weeks": [{"sessions": [{"date": iso(start), "type": "long", "title": "Tirada larga", "distance_km": 18},
                                    {"date": iso(start + timedelta(days=1)), "type": "rest", "title": "Descanso"}]}]}
    food_st = {"prefs": {"goal": {"mode": "lose", "pace": "moderado"}}}
    ctx = S.context({"days": days, "weights": [{"d": iso(TODAY), "kg": 70}]}, {"plan": plan}, food_st, start, TODAY)
    long_day, rest_day = ctx["days"][0], ctx["days"][1]
    assert long_day["hard"] and long_day["sessions"][0]["km"] == 18 and not rest_day["sessions"]
    floor = 2600 * 0.8  # nunca más de un 20 % por debajo de lo que gastas
    assert rest_day["kcal"] >= floor and long_day["kcal"] > rest_day["kcal"] and ctx["proteinRefG"] == [84, 112]
    # Sin datos de Garmin: sin referencia de energía, el menú sigue
    ctx = S.context({}, None, None, start, TODAY)
    assert all(d["kcal"] is None for d in ctx["days"])


# ---------------------------------------------------------------- IA (simulada)
class FakeResp:
    def __init__(self, parsed, stop="end_turn"):
        self.parsed_output, self.stop_reason = parsed, stop
        self.usage = types.SimpleNamespace(input_tokens=3500, output_tokens=4500, cache_creation_input_tokens=0, cache_read_input_tokens=0)


def fake_menu(start: date, **kw):
    days = [{"date": iso(start + timedelta(days=i)), "focus": None, "kcal_per_person": 1900, "protein_g_per_person": 95,
             "meals": [{"meal": "comida", "dish": "Arroz con pollo", "portion": "1 plato", "note": None},
                       {"meal": "cena", "dish": "Tortilla y ensalada", "portion": "2 huevos", "note": None},
                       {"meal": "snacks", "dish": "Fruta", "portion": "1 pieza", "note": None}]} for i in range(7)]
    base = {"summary": "Menú sencillo con más hidratos el día de la tirada.", "days": days, "tips": ["Cocina el arroz doble."],
            "ingredients": [{"name": "arroz", "amount": 700, "unit": "g"}, {"name": "pechuga de pollo", "amount": 600, "unit": "g"},
                            {"name": "huevos", "amount": 14, "unit": "ud"}, {"name": "atún en lata", "amount": 160, "unit": "g"}]}
    base.update(kw)
    return S.WeekMenu.model_validate(base)


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


def test_generate_menu_one_call_logs_cost_and_saves_plan(monkeypatch, tmp_path):
    seen: dict = {}
    start = S.week_start(TODAY)
    monkeypatch.setattr(ai, "_api_key", lambda: "k")
    monkeypatch.setattr(S.anthropic, "Anthropic", fake_client(seen, FakeResp(fake_menu(start))))
    S.set_prefs({"enabled": True, "people": 2, "diet": {"noPescado": True}, "allergies": "kiwi", "budget": 70, "meals": ["comida", "cena"]})
    coach.save({"plan": {"weeks": [{"sessions": [{"date": iso(start), "type": "long", "title": "Tirada larga", "distance_km": 16}]}]}})
    st = S.generate({"days": [], "weights": []}, coach.load(), {}, today=TODAY)
    prompt = seen["messages"][0]["content"]
    assert seen["model"] == "claude-sonnet-5-5" and seen["output_format"] is S.WeekMenu
    assert "sin pescado ni marisco" in prompt and "kiwi" in prompt and "70 €" in prompt and "Tirada larga (16 km)" in prompt
    assert "Personas: 2" in prompt and "atún en lata" not in prompt.split("usa estos nombres):")[1]  # sin pescado: ni lo ofrece
    assert "neutro en cuanto al género" in S.SYSTEM and "bueno o malo" in S.SYSTEM
    log = (tmp_path / "ai_usage_lambda.log").read_text()
    assert "kind=compra" in log and "model=claude-sonnet-5-5" in log
    plan = st["plan"]
    assert plan["cost"] == pytest.approx(3500 * 2e-6 + 4500 * 10e-6) and len(plan["days"]) == 7
    assert all(m["meal"] in ("comida", "cena") for d in plan["days"] for m in d["meals"])  # snacks no pedidos: fuera
    assert not any(i["name"] == "atún en lata" for i in plan["ingredients"]) and plan["warnings"]
    assert plan["days"][0]["sessions"][0]["type"] == "long" and S.load()["list"] == {"checked": [], "removed": [], "swaps": {}, "need": []}


def test_generate_budget_exhausted_refusal_and_truncated(monkeypatch):
    S.set_prefs({"enabled": True})
    monkeypatch.setattr(ai, "over_budget", lambda: True)
    with pytest.raises(S.ShoppingError, match="tope de IA"):
        S.generate({}, None, None)
    monkeypatch.setattr(ai, "over_budget", lambda: False)
    monkeypatch.setattr(ai, "_api_key", lambda: "k")
    for resp, msg in ((FakeResp(None, "refusal"), "no ha podido"), (FakeResp(fake_menu(TODAY), "max_tokens"), "incompleta")):
        monkeypatch.setattr(S.anthropic, "Anthropic", fake_client({}, resp))
        with pytest.raises(S.ShoppingError, match=msg):
            S.generate({}, None, None)
    assert not S.load().get("plan")


def test_update_item_and_delete():
    st = S.load()
    st["plan"] = plan_with(ITEMS)
    S.save(st)
    S.update_item({"key": "arroz", "checked": True})
    S.update_item({"key": "plátano", "removed": True})
    S.update_item({"key": "arroz", "productId": "2"})
    lst = S.load()["list"]
    assert lst["checked"] == ["arroz"] and lst["removed"] == ["plátano"] and lst["swaps"] == {"arroz": "2"}
    S.update_item({"key": "plátano", "removed": False})
    S.update_item({"key": "arroz", "productId": None})
    S.update_item({"action": "uncheck-all"})
    lst = S.load()["list"]
    assert lst["removed"] == [] and lst["swaps"] == {} and lst["checked"] == []
    with pytest.raises(LookupError):
        S.update_item({"key": "caviar", "checked": True})
    S.delete_plan()
    with pytest.raises(LookupError):
        S.update_item({"key": "arroz", "checked": True})


# ---------------------------------------------------------------- catálogo en S3 y refresco semanal
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
        self.reads = 0

    def get_object(self, Bucket, Key):  # noqa: N803
        self.reads += 1
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


def test_load_catalog_from_s3_with_cache_and_missing():
    s3 = FakeS3()
    assert C.load_s3(s3, "b") is None
    s3.objs[C.LATEST] = json.dumps(CATALOG).encode()
    cat = C.load_s3(s3, "b")
    assert cat["meta"]["postcode"] == "28001" and len(cat["products"]) == len(CATALOG["products"])
    reads = s3.reads
    assert C.load_s3(s3, "b") is cat and s3.reads == reads  # en memoria unos minutos
    assert C.load_s3(s3, "b", ttl=0) is not cat
    key = C.put_s3(s3, "b", {"meta": {"date": "2026-11-09"}, "products": []})
    assert key == "admin/catalog/mercadona-2026-11-09.json" and C.LATEST in s3.writes


class FakeHTTP:
    """Tienda falsa: árbol de categorías, listados con precio, fichas y Open Food Facts. Apunta cada URL pedida."""

    def __init__(self, fail: dict | None = None, products=None):
        self.urls: list[str] = []
        self.fail = fail or {}
        self.products = products or [
            {"id": "1", "display_name": "Arroz redondo Casera", "packaging": "Paquete", "share_url": "https://tienda.example/p/1",
             "price_instructions": {"unit_price": "1.25", "reference_price": "1.25", "reference_format": "kg", "unit_size": 1,
                                    "size_format": "kg"}},
            {"id": "99", "display_name": "Lentejas nuevas Casera", "packaging": "Bote", "share_url": "https://tienda.example/p/99",
             "price_instructions": {"unit_price": "0.95", "reference_price": "1.67", "reference_format": "kg", "unit_size": 0.57,
                                    "size_format": "kg"}},
            {"id": "60", "display_name": "Sardina limpia", "share_url": "https://tienda.example/p/60",
             "price_instructions": {"selling_method": 1, "reference_price": "6.50", "reference_format": "kg", "min_bunch_amount": 0.2,
                                    "size_format": "kg", "approx_size": True}}]

    def __call__(self, req, timeout):
        url = req.full_url
        self.urls.append(url)
        for frag, code in self.fail.items():
            if frag in url:
                raise urllib.error.HTTPError(url, code, "x", {}, None)
        if "change-pc" in url:
            assert req.get_method() == "PUT" and req.get_header("User-agent").startswith("RunchApp")
            return _Resp(b"{}", {"x-customer-wh": "9999"})
        if url.startswith(C.SHOP + "/api/categories/?"):
            return _Resp(json.dumps({"results": [
                {"name": "Arroz, legumbres y pasta", "categories": [{"id": 7, "name": "Arroz"}]},
                {"name": "Limpieza y hogar", "categories": [{"id": 8, "name": "Lejía"}]}]}).encode())
        if "/api/categories/7/" in url:
            return _Resp(json.dumps({"categories": [{"name": "Arroz", "products": self.products}]}).encode())
        if "/api/products/" in url:
            pid = url.split("/api/products/")[1].split("/")[0]
            return _Resp(json.dumps({"ean": "84000000" + pid.zfill(5), "details": {"brand": "Casera"}}).encode())
        if "openfoodfacts" in url:
            return _Resp(json.dumps({"status": 1, "product": {"nutriments": {"energy-kcal_100g": 116, "proteins_100g": 9,
                                                                             "carbohydrates_100g": 20, "fat_100g": 0.4}}}).encode())
        raise AssertionError(f"URL inesperada {url}")


class _Resp(io.BytesIO):
    def __init__(self, data: bytes, headers: dict | None = None):
        super().__init__(data)
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def client(http, gap=0.75):
    slept: list = []
    return C.Client(gap=gap, opener=http, sleep=slept.append), slept


def test_refresh_listings_prices_new_details_and_nutrition():
    prev = {"meta": {"wh": "9999"}, "products": [
        C.compact_row(P("1", "Arroz redondo Casera", "Arroz, legumbres y pasta > Arroz > Arroz", "1 kg", 1.20, 1.2, nut=NUT,
                        ean="8400000000001")),
        C.compact_row(P("60", "Sardina limpia", "Marisco y pescado > x > y", "a peso (desde 0.2 kg)", None, 6.0))]}
    http = FakeHTTP()
    cli, slept = client(http)
    off, _ = client(http, gap=1.0)
    cat = C.refresh(prev, cli, "28001", off_cli=off)
    by = {p["id"]: p for p in cat["products"]}
    assert by["1"]["price"] == 1.25 and by["1"]["nut"] == NUT and by["1"]["ean"] == "8400000000001"  # precio nuevo, nutrición de antes
    assert by["99"]["brand"] == "Casera" and by["99"]["nut"]["kcal"] == 116 and by["99"]["nutSrc"] == "openfoodfacts"
    assert by["60"]["price"] is None and by["60"]["perKgL"] == 6.5 and by["60"]["fmt"] == "a peso (desde 0.2 kg)"
    assert not any("/categories/8/" in u for u in http.urls)  # droguería: no se pide
    assert sum("/api/products/" in u for u in http.urls) == 1  # ficha solo del producto nuevo
    assert cat["meta"]["wh"] == "9999" and cat["meta"]["stats"]["new"] == 1 and cat["meta"]["postcode"] == "28001"
    assert slept and min(slept) > 0  # pausa entre peticiones


def test_refresh_stops_on_429_403_and_non_json_without_retry():
    for frag, code in (("/api/categories/7/", 429), ("/api/categories/?", 403)):
        http = FakeHTTP(fail={frag: code})
        cli, _ = client(http)
        with pytest.raises(C.Stop):
            C.refresh(None, cli, wh="9999")
        assert sum(frag in u for u in http.urls) == 1  # ni un reintento
    http = FakeHTTP()
    cli, _ = client(http)
    real = http.__call__

    def wall(req, timeout):
        if "/api/categories/7/" in req.full_url:
            return _Resp(b"<html>bot</html>")
        return real(req, timeout)
    cli._open = wall
    with pytest.raises(C.Stop, match="no es JSON"):
        C.refresh(None, cli, wh="9999")


def test_refresh_off_429_only_stops_nutrition_and_guard_against_tiny_catalog():
    http = FakeHTTP(fail={"openfoodfacts": 429})
    cli, _ = client(http)
    cat = C.refresh(None, cli, wh="9999", off_cli=cli)
    assert len(cat["products"]) == 3 and cat["meta"]["stats"]["stoppedOff"]
    big_prev = {"meta": {}, "products": [C.compact_row(P(str(i), f"x{i}", "Arroz, legumbres y pasta > a > b", "1 kg", 1, 1))
                                         for i in range(100, 120)]}
    with pytest.raises(RuntimeError, match="no se publica"):
        C.refresh(big_prev, client(FakeHTTP())[0], wh="9999", off_cli=client(FakeHTTP())[0])


def _load_module(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).parents[1] / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def test_catalog_lambda_keeps_last_good_on_429_and_publishes_on_success(monkeypatch):
    s3 = FakeS3()
    s3.objs[C.LATEST] = json.dumps(CATALOG).encode()
    fake = types.ModuleType("boto3")
    fake.client = lambda name: s3  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "boto3", fake)
    monkeypatch.setenv("BUCKET", "b")
    old_tz = os.environ.get("TZ")
    job = _load_module("catalog_job_test", "infra/lambda/catalog/catalog_job.py")
    try:
        http = FakeHTTP(fail={"/api/categories/7/": 429})
        real = C.Client
        monkeypatch.setattr(C, "Client", lambda gap=0.75, **kw: real(gap=0, opener=http, sleep=lambda s: None))
        with pytest.raises(RuntimeError, match="no actualizado"):
            job.handler({}, None)
        assert json.loads(s3.objs[C.LATEST]) == CATALOG  # el último catálogo bueno sigue ahí
        status = json.loads(s3.objs[C.STATUS])
        assert not status["ok"] and "429" in status["error"] and status["kept"] == "2026-11-02"
        http.fail = {}
        out = job.handler({"probe": True}, None)
        assert out["probe"] and C.LATEST not in s3.writes
        small = {"meta": {"date": "2026-11-02", "wh": "9999"}, "products": [C.compact_row(CATALOG["products"][0])]}
        s3.objs[C.LATEST] = json.dumps(small).encode()
        out = job.handler({}, None)
        assert out["ok"] and out["count"] >= 2 and json.loads(s3.objs[C.LATEST])["meta"]["wh"] == "9999"
        assert json.loads(s3.objs[C.STATUS])["ok"]
    finally:
        os.environ.pop("TZ", None) if old_tz is None else os.environ.__setitem__("TZ", old_tz)
        time.tzset()


# ---------------------------------------------------------------- API
class _Lambda:
    class exceptions:  # noqa: N801
        ParameterNotFound = type("ParameterNotFound", (Exception,), {})

    def __init__(self):
        self.calls: list[dict] = []

    def invoke(self, **kw):
        self.calls.append(json.loads(kw["Payload"]))

    def get_parameter(self, **kw):
        return {"Parameter": {"Value": "clave-de-prueba"}}


@pytest.fixture
def api(tmp_path, monkeypatch):
    secret, origin = "s" * 64, "o" * 64
    owner, friend = "persona@example.com", "amiga@example.com"
    for k, v in {"BUCKET": "b", "SESSION_SECRET": secret, "ORIGIN_SECRET": origin, "OWNER_EMAIL": owner,
                 "ANTHROPIC_KEY_PARAM": "/x", "AWS_LAMBDA_FUNCTION_NAME": "api"}.items():
        monkeypatch.setenv(k, v)
    s3, lam = FakeS3(), _Lambda()
    fake = types.ModuleType("boto3")
    fake.client = lambda name: s3 if name == "s3" else lam  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "boto3", fake)
    old_env = {k: os.environ.get(k) for k in ("TZ", "HOME", "GARMIN_STATS_UID", "GARMIN_STATS_AI_BUDGET", "GARMIN_STATS_ADAPT_MODEL")}
    h = _load_module("api_handler_shopping_test", "infra/lambda/api/handler.py")
    root = tmp_path / "gs"
    monkeypatch.setattr(h, "ROOT", root)
    monkeypatch.setattr(h, "HOME", tmp_path / "home")
    for mod, name in ((settings, "settings.json"), (weather, "weather.json"), (wellness, "wellness.json"),
                      (coach, "coach.json"), (food, "food.json"), (S, "shopping.json")):
        monkeypatch.setattr(mod, "STATE" if mod is coach else "PATH", root / "data" / name)
    monkeypatch.setattr(ai, "DATA_DIR", root / "data")
    monkeypatch.setattr(ai, "USAGE_LOG", root / "data" / "ai_usage_lambda.log")
    s3.objs["admin/users.json"] = json.dumps({"users": [
        {"email": owner, "uid": "u1", "role": "owner", "status": "active"},
        {"email": friend, "uid": "u2", "role": "friend", "status": "active"}]}).encode()
    days = [{"d": iso(TODAY - timedelta(days=i)), "cal": 2600, "calActive": 400} for i in range(20, 0, -1)]
    for uid in ("u1", "u2"):
        s3.objs[f"site/u/{uid}/data.js"] = ("window.__GARMIN__=" + json.dumps({"days": days, "weights": []}) + ";\n").encode()
    s3.objs[C.LATEST] = json.dumps(CATALOG).encode()

    def cookie(email):
        b64 = base64.urlsafe_b64encode(email.encode()).decode().rstrip("=")
        exp = str(int(time.time()) + 3600)
        return f"gs_session={b64}.{exp}.{hmac.new(secret.encode(), f'{b64}.{exp}'.encode(), hashlib.sha256).hexdigest()}"

    def call(method, path, body=None, who=owner):
        ev = {"headers": {"x-origin-verify": origin}, "cookies": [cookie(who)] if who else [],
              "requestContext": {"http": {"method": method}}, "rawPath": path, "rawQueryString": "",
              "body": json.dumps(body) if body is not None else ""}
        r = h.handler(ev, None)
        return r["statusCode"], json.loads(r["body"])
    yield types.SimpleNamespace(call=call, s3=s3, lam=lam, h=h, friend=friend)
    for k, v in old_env.items():
        os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
    time.tzset()


def test_api_shopping_flow(api, monkeypatch):
    code, out = api.call("GET", "/api/shopping")
    assert code == 200 and not out["prefs"]["enabled"] and out["catalog"]["available"] and out["plan"] is None
    assert "Mercadona" in out["attribution"]["products"] and "etiquetas" in out["attribution"]["allergy"]
    assert api.call("POST", "/api/shopping/generate", {})[0] == 409  # hay que activarlo antes
    code, out = api.call("POST", "/api/shopping/prefs", {"enabled": True, "people": 2, "budget": 60})
    assert code == 200 and out["prefs"]["people"] == 2 and "users/u1/state/shopping.json" in api.s3.writes
    assert api.call("POST", "/api/shopping/prefs", {"people": 9})[0] == 400
    code, out = api.call("POST", "/api/shopping/generate", {"start": "monday"})
    assert code == 202 and out["job"]["status"] == "running"
    assert api.lam.calls[-1] == {"job": "shopping", "uid": "u1", "body": {"start": "monday"}}
    assert api.call("POST", "/api/shopping/generate", {})[0] == 409  # ya en marcha
    # La invocación asíncrona: genera el menú (IA simulada) y deja la lista
    start = S.week_start(TODAY, "monday")
    monkeypatch.setattr(S, "generate_menu", lambda p, ctx, st: (fake_menu(start), 0.05, "claude-sonnet-5-5"))
    assert api.h.handler(api.lam.calls[-1], None) == {"ok": True}
    code, out = api.call("GET", "/api/shopping")
    assert code == 200 and out["job"]["status"] == "done" and out["plan"]["start"] == iso(start)
    lst = out["list"]
    assert lst["total"] > 0 and lst["items"] == 4 and "Total aprox." in out["text"]
    first = next(i for g in lst["groups"] for i in g["items"] if i["product"])
    assert first["product"]["url"].startswith("https://")
    code, out = api.call("POST", "/api/shopping/item", {"key": "arroz", "removed": True})
    assert code == 200 and out["list"]["total"] < lst["total"]
    assert api.call("POST", "/api/shopping/item", {"key": "caviar", "checked": True})[0] == 404
    # Desactivar no rompe nada: la página sigue respondiendo y el menú se conserva
    code, out = api.call("POST", "/api/shopping/prefs", {"enabled": False})
    assert code == 200 and not out["prefs"]["enabled"] and out["plan"]
    assert api.call("POST", "/api/shopping/item", {"key": "arroz", "removed": False})[0] == 409


def test_api_shopping_job_error_budget_auth_and_isolation(api, monkeypatch):
    api.call("POST", "/api/shopping/prefs", {"enabled": True})
    monkeypatch.setattr(ai, "over_budget", lambda: True)
    code, out = api.call("POST", "/api/shopping/generate", {})
    assert code == 409 and out["budget"]
    monkeypatch.setattr(ai, "over_budget", lambda: False)
    api.call("POST", "/api/shopping/generate", {})

    def boom(*a):
        raise S.ShoppingError("La IA no está disponible ahora (529). Inténtalo de nuevo.")
    monkeypatch.setattr(S, "generate_menu", boom)
    assert api.h.handler(api.lam.calls[-1], None) == {"ok": False}
    code, out = api.call("GET", "/api/shopping")
    assert out["job"]["status"] == "error" and "529" in out["job"]["error"] and out["plan"] is None
    # Sin sesión: 401. La amiga no ve nada de la lista del dueño.
    assert api.call("GET", "/api/shopping", who=None)[0] == 401
    code, out = api.call("GET", "/api/shopping", who=api.friend)
    assert code == 200 and not out["prefs"]["enabled"] and out["job"] is None
    # Un "generándose" de hace más de 10 min se da por fallido
    st = json.loads(api.s3.objs["users/u1/state/shopping.json"])
    st["job"] = {"status": "running", "at": int(time.time()) - 3600}
    api.s3.objs["users/u1/state/shopping.json"] = json.dumps(st).encode()
    assert api.call("GET", "/api/shopping")[1]["job"]["status"] == "error"


def test_api_shopping_without_catalog_still_works(api):
    del api.s3.objs[C.LATEST]
    code, out = api.call("GET", "/api/shopping")
    assert code == 200 and not out["catalog"]["available"]
