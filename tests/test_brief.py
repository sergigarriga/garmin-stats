"""Mensaje de bienvenida con IA: franja del día, caché y límites."""

import json
from datetime import datetime

from garmin_stats import brief as B

DATA = {"days": [{"d": "2026-11-14", "sleepH": 6.1, "steps": 3000}],
        "activities": [{"id": 7, "start": "2026-11-14T08:30:00", "group": "Correr", "km": 5.0, "min": 30}],
        "coach": {"plan": {"goal": "Media", "weeks": [{"start": "2026-11-09", "focus": "Base", "plannedKm": 30, "actualKm": 12}]},
                  "today": {"session": {"type": "easy", "title": "Rodaje", "status": "done", "target": "6:00"}}}}


def test_slot_changes_with_the_hour():
    assert [B.slot(datetime(2026, 11, 14, h)) for h in (7, 12, 19, 20, 23)] == ["morning", "afternoon", "afternoon", "evening", "evening"]


def test_key_changes_with_slot_and_with_a_new_workout_but_not_with_time():
    a = B.cache_key(DATA, datetime(2026, 11, 14, 9, 0))
    assert a == B.cache_key(DATA, datetime(2026, 11, 14, 11, 59))  # misma franja y nada nuevo
    assert a != B.cache_key(DATA, datetime(2026, 11, 14, 13, 0))   # otra franja
    more = {**DATA, "activities": DATA["activities"] + [{"id": 8, "start": "2026-11-14T10:00:00"}]}
    assert a != B.cache_key(more, datetime(2026, 11, 14, 11, 0))   # entreno nuevo hoy


def test_context_has_today_plan_and_week_without_the_heavy_parts(monkeypatch):
    monkeypatch.setattr(B.ai, "_summary", lambda d: {"today": "2026-11-14", "relations": [1], "coverage": {}, "latest": {}})
    ctx = B.context(DATA, datetime(2026, 11, 14, 18, 30))
    assert ctx["slot"] == "afternoon" and ctx["hora_ahora"] == "18:30"
    assert ctx["entrenos_de_hoy"][0]["km"] == 5.0 and ctx["sesion_del_plan_hoy"]["status"] == "done"
    assert ctx["semana_del_plan"]["actualKm"] == 12 and ctx["objetivo"] == "Media"
    assert "relations" not in ctx and "coverage" not in ctx
