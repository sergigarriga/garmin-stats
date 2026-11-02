"""Pruebas de ritmos (VDOT), natación, gimnasio, registro diario, calendario, cumplimiento y energía actual.

Ejecutar: uv run --with pytest pytest -q
"""

from __future__ import annotations

import json
from datetime import date, timedelta

import pytest

from garmin_stats import calendar_ics, coach, settings, training, wellness
from garmin_stats.store import Store

TODAY = date.today()
iso = lambda d: d.isoformat()  # noqa: E731


@pytest.fixture(autouse=True)
def tmp_state(tmp_path, monkeypatch):
    monkeypatch.setattr(wellness, "PATH", tmp_path / "wellness.json")
    monkeypatch.setattr(settings, "PATH", tmp_path / "settings.json")
    monkeypatch.setattr(coach, "STATE", tmp_path / "coach.json")
    return tmp_path


# ---------------------------------------------------------------- VDOT
def test_vdot_matches_daniels_tables():
    # Tablas de Daniels: 5K en 20:00 ≈ VDOT 49,8; VDOT 50 ≈ 19:57 en 5K y 3:10:49 en maratón
    assert training.vdot_from_race(5000, 20 * 60) == pytest.approx(49.8, abs=0.3)
    assert training.race_time(50, 5000) == pytest.approx(19 * 60 + 57, abs=6)
    assert training.race_time(50, 42195) == pytest.approx(3 * 3600 + 10 * 60 + 49, abs=90)
    # ida y vuelta
    for v in (35, 45, 60):
        assert training.vdot_from_race(10000, training.race_time(v, 10000)) == pytest.approx(v, abs=0.05)


def test_reference_paces_order_and_values():
    r = training.ref_paces(50)
    # más rápido = menos segundos
    assert r["repetition"] < r["interval"] < r["5k"] < r["10k"] < r["threshold"] < r["half"] < r["marathon"] < r["easy"]
    assert r["threshold"] == pytest.approx(4 * 60 + 15, abs=6)  # Daniels T VDOT 50: 4:15 /km
    assert r["interval"] == pytest.approx(3 * 60 + 55, abs=6)   # I: 3:55 /km
    fast, slow = training.easy_range(50)
    assert fast < r["easy"] < slow


def test_pace_zones_contiguous():
    z = training.pace_zones(250)
    assert [x["zone"] for x in z] == [1, 2, 3, 4, 5]
    for a, b in zip(z, z[1:]):
        assert a["fast"] == b["slow"]  # sin huecos entre zonas
        assert a["fast"] > b["fast"]


def test_resolve_step_pace():
    refs = {"10k": 240, "easy": 330}
    assert training.resolve_step_pace({"pace_ref": "10k", "pace_ref_offset_s": -5}, refs) == (230, 240)
    assert training.resolve_step_pace({"pace_ref": "easy"}, refs) == (318, 342)
    # sin referencia: se usa el rango escrito
    assert training.resolve_step_pace({"pace_fast": "4:50", "pace_slow": "5:05"}, refs) == (290, 305)
    assert training.resolve_step_pace({"pace_ref": "5k", "pace_fast": "4:00", "pace_slow": "4:10"}, refs) == (240, 250)
    assert training.resolve_step_pace({}, refs) is None
    assert training.resolve_step_pace({"pace_fast": "x", "pace_slow": None}, refs) is None


def _data(**kw):
    base = {"activities": [], "predictions": []}
    base.update(kw)
    return base


def test_paces_block_source_priority():
    acts = [{"id": 1, "start": "2026-10-01T08:00", "vo2": 53.3, "group": "Correr"}]
    preds = [{"distance": "Media maratón", "best90": 95 * 60 + 40}, {"distance": "10 km", "best90": None}]
    b = training.paces_block(_data(activities=acts, predictions=preds), {})
    assert b["source"] == "recent" and b["vdot"] == pytest.approx(47.5, abs=0.2)
    assert [o["kind"] for o in b["others"]] == ["watch"]
    b2 = training.paces_block(_data(activities=acts, predictions=preds),
                              {"race_test": {"distance_m": 10000, "time_s": 45 * 60, "date": iso(TODAY)}})
    assert b2["source"] == "race" and not b2["stale"]
    assert b2["vdot"] == pytest.approx(training.vdot_from_race(10000, 2700), abs=0.06)
    assert len(b2["list"]) == 8 and len(b2["zones"]) == 5 and len(b2["races"]) == 4
    old = {"race_test": {"distance_m": 5000, "time_s": 1300, "date": iso(TODAY - timedelta(days=200))}}
    assert training.paces_block(_data(), old)["stale"] is True
    assert training.paces_block(_data(), {}) is None
    b3 = training.paces_block(_data(activities=acts), {})
    assert b3["source"] == "watch" and b3["vdot"] == 53.3


# ---------------------------------------------------------------- natación
def test_css_and_swim_zones():
    assert training.css_from_test(7 * 60, 3 * 60 + 20) == 110  # (420 - 200) / 2
    z = training.swim_zones(110)
    assert z[3]["name"].startswith("Umbral") and z[3]["fast"] <= 110 <= z[3]["slow"]
    assert all(a["fast"] == b["slow"] for a, b in zip(z, z[1:]))


def _swim(i, d, km, pace_min_km, **kw):
    return {"id": i, "start": f"{d}T10:00", "group": "Natación", "type": "lap_swimming", "km": km, "min": km * pace_min_km,
            "pace": pace_min_km, **kw}


def test_swim_block_estimate_and_test():
    d = iso(TODAY - timedelta(days=10))
    acts = [_swim(1, d, 1.0, 25, swolf=51, poolM=25), _swim(2, d, 0.3, 20), {"id": 3, "start": f"{d}T09:00", "group": "Correr", "km": 5}]
    b = training.swim_block(_data(activities=acts), {})
    assert b["cssSource"] == "estimate" and b["css"] == 150  # 25 min/km = 2:30 /100 m; el de 300 m no cuenta
    assert b["totals"]["sessions"] == 2 and sum(w["m"] for w in b["weeks"]) == 1300
    assert b["poolM"] == 25
    b2 = training.swim_block(_data(activities=acts), {"swim_test": {"t400_s": 400, "t200_s": 185}})
    assert b2["cssSource"] == "test" and b2["css"] == 108  # 107,5 redondeado
    assert training.swim_block(_data(), {}) is None


# ---------------------------------------------------------------- gimnasio
def test_e1rm_epley():
    assert training.e1rm(100, 1) == 100
    assert training.e1rm(100, 10) == pytest.approx(133.3, abs=0.1)
    assert training.e1rm(100, 13) is None and training.e1rm(None, 5) is None and training.e1rm(0, 5) is None


def test_gym_block_muscles_and_records():
    d = iso(TODAY)
    sets = [{"ex": "Press de banca", "reps": 8, "kg": 60}, {"ex": "Press de banca", "reps": 6, "kg": 65},
            {"ex": "Sentadilla", "reps": 5, "kg": 80}, {"ex": "Plancha", "reps": 1, "kg": None},
            {"ex": "Calentamiento", "reps": 10, "kg": None}]
    acts = [{"id": 9, "start": f"{d}T18:00", "type": "strength_training", "group": "Otros", "sets": sets},
            {"id": 10, "start": f"{d}T19:00", "type": "strength_training", "group": "Otros", "sets": None}]
    g = training.gym_block(_data(activities=acts))
    w = g["weeks"][-1]
    assert w["sessions"] == 2 and w["sets"] == 4  # el calentamiento no cuenta
    assert w["muscles"]["chest"] == 2 and w["muscles"]["triceps"] == 1 and w["muscles"]["quads"] == 1
    assert w["muscles"]["glutes"] == 0.5 and w["muscles"]["core"] == 1
    assert w["kg"] == 60 * 8 + 65 * 6 + 80 * 5
    bench = next(r for r in g["records"] if r["ex"] == "Press de banca")
    assert bench["best"]["e1rm"] == pytest.approx(65 * (1 + 6 / 30), abs=0.1) and bench["maxKg"]["kg"] == 65
    assert g["records"][-1]["ex"] in ("Plancha",)  # sin kg: al final
    assert training.gym_block(_data()) is None


# ---------------------------------------------------------------- registro diario y lesiones
def test_wellness_day_and_validation():
    st = wellness.set_day({"mood": 4, "soreness": "2", "note": " bien "})
    e = st["log"][iso(TODAY)]
    assert e["mood"] == 4 and e["soreness"] == 2 and e["note"] == "bien"
    with pytest.raises(ValueError):
        wellness.set_day({"mood": 6})
    with pytest.raises(ValueError):
        wellness.set_day({"mood": 3, "date": iso(TODAY + timedelta(days=1))})
    with pytest.raises(ValueError):
        wellness.set_day({"mood": 3, "date": iso(TODAY - timedelta(days=8))})
    wellness.set_day({"mood": 2, "date": iso(TODAY - timedelta(days=1))})
    b = wellness.block()
    assert b["today"]["mood"] == 4 and len(b["recent"]) == 2
    wellness.set_day({})  # todo vacío: borra el de hoy
    assert wellness.block()["today"] is None


def test_injuries_lifecycle():
    st = wellness.injury({"action": "add", "area": "Rodilla derecha", "severity": 3})
    i = st["injuries"][0]
    assert i["end"] is None and i["start"] == iso(TODAY)
    assert wellness.active_injuries()[0]["area"] == "Rodilla derecha"
    with pytest.raises(ValueError):
        wellness.injury({"action": "add", "area": ""})
    with pytest.raises(ValueError):
        wellness.injury({"action": "close", "id": "nope"})
    with pytest.raises(ValueError):
        wellness.injury({"action": "close", "id": i["id"], "end": iso(TODAY - timedelta(days=3))})
    wellness.injury({"action": "update", "id": i["id"], "severity": 1})
    wellness.injury({"action": "close", "id": i["id"]})
    assert wellness.active_injuries() == [] and wellness.block()["injuries"][0]["end"] == iso(TODAY)
    fc = wellness.for_coach()
    assert "recuperada" in fc["molestias_y_lesiones"][0]["estado"]
    wellness.injury({"action": "delete", "id": i["id"]})
    assert wellness.load()["injuries"] == []


def test_settings_validation():
    settings.set_race_test({"distance_m": 10000, "time_s": 2700})
    assert settings.load()["race_test"]["time_s"] == 2700
    for bad in ({"distance_m": 100, "time_s": 30}, {"distance_m": 10000, "time_s": 1000}, {"time_s": 5},
                {"distance_m": 5000, "time_s": 1200, "date": iso(TODAY + timedelta(days=2))}):
        with pytest.raises(ValueError):
            settings.set_race_test(bad)
    settings.set_race_test({"clear": True})
    assert "race_test" not in settings.load()
    settings.set_swim_test({"t400_s": 400, "t200_s": 185, "pool_m": 25})
    assert settings.load()["swim_test"]["t200_s"] == 185 and settings.load()["pool_m"] == 25
    with pytest.raises(ValueError):
        settings.set_swim_test({"t400_s": 360, "t200_s": 185})  # 400 más rápido que 2 x 200
    with pytest.raises(ValueError):
        settings.set_swim_test({"pool_m": 33})


# ---------------------------------------------------------------- calendario
def _plan():
    d0 = TODAY
    return {"goal": "Media maratón", "weeks": [{"start": iso(d0), "focus": "x", "sessions": [
        {"date": iso(d0), "type": "intervals", "title": "6 x 1 km, a tope; con calma", "distance_km": 10, "duration_min": 55,
         "target": "4:35-4:45 /km", "description": "Calienta bien.\nLuego series." + " muy largo" * 20,
         "workout": [{"repeat": 1, "steps": [{"kind": "warmup", "duration": "distance", "value": 2, "target": "open", "name": "Calentamiento"}]},
                     {"repeat": 6, "steps": [
                         {"kind": "active", "duration": "distance", "value": 1, "target": "pace", "pace_fast": "4:00", "pace_slow": "4:10",
                          "pace_ref": "10k", "pace_ref_offset_s": 0, "name": "1 km"},
                         {"kind": "recovery", "duration": "time", "value": 2, "target": "open", "name": "Trote"}]}]},
        {"date": iso(d0 + timedelta(days=1)), "type": "rest", "title": "Descanso", "target": "", "description": ""},
        {"date": iso(d0 + timedelta(days=2)), "type": "strength", "title": "Gimnasio", "target": "", "description": "",
         "strength": [{"label": "Sentadilla", "sets": 3, "reps": 8, "weight_kg": 60, "rest_s": 90}]},
    ]}]}


def test_calendar_ics():
    ics = calendar_ics.build(_plan(), {"10k": 250}, "Plan de entreno · Media maratón")
    assert ics.startswith("BEGIN:VCALENDAR\r\n") and ics.endswith("END:VCALENDAR\r\n")
    lines = ics.split("\r\n")
    assert all(len(ln.encode()) <= 75 for ln in lines)
    assert ics.count("BEGIN:VEVENT") == 2  # el descanso no se publica
    unfolded = ics.replace("\r\n ", "")
    assert "SUMMARY:Series: 6 x 1 km\\, a tope\\; con calma" in unfolded
    assert "6 x [1 km: 1 km a 4:05-4:15 /km + Trote: 2 min]" in unfolded  # ritmo de 10K actual (250 s) ± 5 s
    assert "Sentadilla: 3 x 8 rep. con 60 kg" in unfolded
    assert f"DTSTART;VALUE=DATE:{TODAY:%Y%m%d}" in unfolded
    assert calendar_ics.build(None).count("VEVENT") == 0


# ---------------------------------------------------------------- cumplimiento
def _act(i, d, group, km=None, mins=None, pace=None, **kw):
    return {"id": i, "start": f"{d}T08:00", "group": group, "km": km, "min": mins, "pace": pace, **kw}


def test_match_compliance():
    d = iso(TODAY - timedelta(days=1))
    s = {"date": d, "type": "easy", "distance_km": 10, "duration_min": 60}
    by = {d: [_act(1, d, "Correr", 9.0, 52, 52 / 9)]}
    m = coach._match(s, by)
    assert m["status"] == "done" and m["compliance"]["distRatio"] == 0.9
    assert m["compliance"]["paceDeltaS"] == round((52 / 9 - 6) * 60)  # más rápido: negativo
    m = coach._match(s, {d: [_act(1, d, "Correr", 8.0, 50, 50 / 8)]})
    assert m["status"] == "partial"  # 80 % < 85 %
    assert coach._match(s, {})["status"] == "missed"
    sw = {"date": d, "type": "swim", "distance_km": 1.5, "duration_min": 40}
    m = coach._match(sw, {d: [_act(2, d, "Correr", 5, 30, 6), _act(3, d, "Natación", 1.4, 38, 27)]})
    assert m["status"] == "done" and m["actual"]["id"] == 3
    gym = {"date": d, "type": "strength", "distance_km": None, "duration_min": 50,
           "strength": [{"sets": 3}, {"sets": 3}, {"sets": 4}]}
    sets = [{"ex": "Sentadilla", "reps": 8}] * 7
    m = coach._match(gym, {d: [_act(4, d, "Otros", 0, 45, None, type="strength_training", sets=sets)]})
    assert m["status"] == "partial" and m["compliance"]["setsDone"] == 7 and m["compliance"]["setsPlanned"] == 10
    m = coach._match(gym, {d: [_act(4, d, "Otros", 0, 45, None, type="strength_training", sets=None)]})
    assert m["status"] == "done"  # sin series del reloj: cuenta como hecha
    assert coach._match({"date": d, "type": "rest"}, by)["status"] == "rest"


def test_today_advice_uses_injuries_and_soreness():
    plan = {"weeks": [{"sessions": [{"date": iso(TODAY), "type": "intervals", "title": "Series"}]}]}
    ready = {"date": iso(TODAY), "score": 85}
    assert "ideal" in coach.today_advice(plan, ready)["tip"]
    assert coach.today_advice(plan, {"date": "2000-01-01", "score": 85})["tip"] is None  # preparación de otro día
    wellness.set_day({"soreness": 5})
    assert "agujetas" in coach.today_advice(plan, ready)["tip"]
    wellness.injury({"action": "add", "area": "Gemelo izquierdo", "severity": 4})
    tip = coach.today_advice(plan, ready)["tip"]
    assert "Gemelo izquierdo" in tip and "suave" in tip


# ---------------------------------------------------------------- energía de ahora
def test_live_block(tmp_path):
    store = Store(tmp_path / "g.sqlite")
    d = date(2026, 11, 2)
    store.put("daily_summary", iso(d), {"wellnessChronology": {"endTimestampLocal": "2026-11-02T13:16:00.0"},
                                         "bodyBattery": {"latestValue": 58, "maxValue": 100, "minValue": 28},
                                         "respiration": {"latestValue": 12}})
    store.put("body_battery", iso(d), {"bodyBatteryValuesArray": [[1793574000000, 28], [1793621520000, 58], [1793621600000, None]]})
    store.put("heart_rate", iso(d), {"heartRateValues": [[1793621400000, 80], [1793621520000, 87], [1793621640000, None]]})
    from garmin_stats import extras
    out = extras.live(store, d)
    assert out["bbNow"] == 58 and out["bbMax"] == 100 and out["asOf"] == "13:16"
    assert out["hrLast"] == 87 and len(out["bbSeries"]) == 2 and out["respNow"] == 12
    assert extras.live(store, date(2026, 11, 3)) is None
    json.dumps(out)
