"""Relojes que no miden todo (sin HRV, sin sueño...): el informe tiene que salir igual."""
import pandas as pd

from garmin_stats import analysis as R
from garmin_stats import export as X


def _tables(days=60, hrv=True, sleep=True):
    d = pd.date_range(end=pd.Timestamp.today().normalize(), periods=days, freq="D")
    daily = pd.DataFrame({"date": d, "steps": 8000, "rhr": 55.0, "stress_avg": 30.0, "worn": True})
    full_sleep = {"date": d, "start": d - pd.Timedelta(minutes=30), "end": d + pd.Timedelta(hours=7), "sleep_h": 7.0,
                  "deep_h": 1.2, "light_h": 4.0, "rem_h": 1.5, "awake_h": 0.3, "nap_h": 0.0, "awake_count": 2, "score": 80.0,
                  "score_label": "GOOD", "need_h": 8.0, "sleep_stress": 15.0, "resp": 14.0, "spo2": 95.0, "rem_capable": True,
                  "bed_from_noon": 11.5, "bed_clock": 23.5, "wake_clock": 7.0, "mid_from_noon": 15.0}
    sl = pd.DataFrame(full_sleep) if sleep else pd.DataFrame(columns=list(full_sleep))
    hv = (pd.DataFrame({"date": d, "hrv": 60.0, "base_low": 50.0, "base_high": 70.0}) if hrv
          else pd.DataFrame(columns=["date", "hrv", "hrv_5min_high", "hrv_weekly", "base_low", "base_high", "status"]))
    return {"daily": daily, "sleep": sl, "hrv": hv, "weight": pd.DataFrame(), "activities": pd.DataFrame()}


def _report(**kw):
    X.SECTION_ERRORS.clear()
    A = R.assemble(_tables(**kw), {"max_hr": 190, "rest_hr": 55})
    am = pd.DataFrame(columns=["activity_id", "start", "date", "name", "type", "group", "distance_km", "duration_min",
                               "pace_min_km", "avg_hr", "max_hr", "trimp", "ef", "decoupling_pct", "cadence_spm",
                               "elev_gain", "calories", "is_pr"] + [f"z{i}_min" for i in range(1, 6)])
    return X.payload(A, am, None, {})


def test_watch_without_hrv():
    data = _report(hrv=False)
    assert data["days"] and all("hrv" not in d for d in data["days"])
    assert "readiness" in data
    assert not X.SECTION_ERRORS, X.SECTION_ERRORS  # sin HRV no es un fallo: todo se calcula


def test_watch_without_sleep_or_hrv():
    data = _report(hrv=False, sleep=False)
    assert data["days"]


def test_broken_section_does_not_break_report(monkeypatch):
    def boom(*_a, **_k):
        raise ValueError("dato raro")
    monkeypatch.setattr(X.E, "alerts", boom)
    data = _report()
    assert data["alerts"] == []
    assert any(e.startswith("alerts:") for e in X.SECTION_ERRORS)
