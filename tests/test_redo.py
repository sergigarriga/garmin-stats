"""'Hacerlo hoy': pasar un entreno de otro día a hoy y deshacerlo."""
from datetime import date, timedelta

from garmin_stats import coach


def _plan():
    t = date.today()
    mon = t - timedelta(days=t.weekday())
    d = lambda n: (mon + timedelta(days=n)).isoformat()
    sess = [{"date": d(i), "type": "rest", "title": "Descanso"} for i in range(7)]
    sess[1] = {"date": d(1), "type": "tempo", "title": "Umbral", "distance_km": 8}
    sess[3] = {"date": d(3), "type": "easy", "title": "Rodaje", "distance_km": 6}
    prev = [{"date": (mon - timedelta(days=6)).isoformat(), "type": "intervals", "title": "6 x 600", "distance_km": 7.8}]
    return {"plan": {"weeks": [{"start": (mon - timedelta(days=7)).isoformat(), "focus": "", "sessions": prev},
                               {"start": mon.isoformat(), "focus": "", "sessions": sess}]}}


def test_redo_and_undo(monkeypatch):
    st = _plan()
    monkeypatch.setattr(coach, "load", lambda: st)
    monkeypatch.setattr(coach, "save", lambda s: None)
    today = date.today().isoformat()
    src = st["plan"]["weeks"][0]["sessions"][0]
    before = [dict(x) for x in st["plan"]["weeks"][1]["sessions"]]
    coach.redo(src["date"], "intervals")
    todays = [x for x in st["plan"]["weeks"][1]["sessions"] if x["date"] == today]
    assert [x["type"] for x in todays] == ["intervals"] and todays[0]["redo_from"] == src["date"]
    assert src["moved_to"] == today
    m = coach._match(src, {})
    assert m["status"] == "moved"
    coach.undo_redo()
    assert "moved_to" not in src
    assert st["plan"]["weeks"][1]["sessions"] == before


def test_redo_rejects_today_and_rest(monkeypatch):
    st = _plan()
    monkeypatch.setattr(coach, "load", lambda: st)
    monkeypatch.setattr(coach, "save", lambda s: None)
    import pytest
    with pytest.raises(ValueError):
        coach.redo(date.today().isoformat(), "rest")
