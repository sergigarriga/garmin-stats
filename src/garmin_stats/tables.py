"""Convierte el JSON crudo en tablas limpias (una fila por día / noche / actividad)."""

from __future__ import annotations

import logging
import math

import pandas as pd

from . import FIT_DIR
from .fit import parse_fit
from .store import Store

log = logging.getLogger(__name__)


def _g(d, *path, default=None):
    for p in path:
        if not isinstance(d, dict):
            return default
        d = d.get(p)
    return default if d is None else d


def _ms_local(ms):
    return pd.to_datetime(ms, unit="ms") if ms else pd.NaT


# ---------------------------------------------------------------- diario
def daily(store: Store) -> pd.DataFrame:
    rows = []
    for key, r in store.items("daily_summary"):
        rows.append({
            "date": key,
            "has_wellness": bool(r.get("includesWellnessData")),
            "wear_h": (_g(r, "wellnessChronology", "totalDurationInMillis", default=0) or 0) / 3.6e6,
            "steps": _g(r, "movement", "steps", "value"),
            "step_goal": _g(r, "movement", "steps", "goal"),
            "walk_km": (_g(r, "movement", "steps", "distanceInMeters") or 0) / 1000 or None,
            "floors_up": _g(r, "movement", "floorsAscended", "value"),
            "cal_total": _g(r, "calories", "burnedTotal"),
            "cal_active": _g(r, "calories", "burnedActive"),
            "rhr": _g(r, "heartRate", "restingValue"),
            "hr_min": _g(r, "heartRate", "minValue"),
            "hr_max": _g(r, "heartRate", "maxValue"),
            "im_moderate": _g(r, "intensityMinutes", "moderate"),
            "im_vigorous": _g(r, "intensityMinutes", "vigorous"),
            "im_goal": _g(r, "intensityMinutes", "goal"),
            "stress_avg": _g(r, "stress", "avgLevel"),
            "stress_max": _g(r, "stress", "maxLevel"),
            "stress_high_h": (_g(r, "stress", "highStressDurationInMillis") or 0) / 3.6e6,
            "stress_med_h": (_g(r, "stress", "mediumStressDurationInMillis") or 0) / 3.6e6,
            "stress_low_h": (_g(r, "stress", "lowStressDurationInMillis") or 0) / 3.6e6,
            "stress_rest_h": (_g(r, "stress", "restDurationInMillis") or 0) / 3.6e6,
            "bb_max": _g(r, "bodyBattery", "maxValue"),
            "bb_min": _g(r, "bodyBattery", "minValue"),
            "bb_charged": _g(r, "bodyBattery", "chargedValue"),
            "bb_drained": _g(r, "bodyBattery", "drainedValue"),
            "resp_avg": _g(r, "respiration", "avgValue"),
            "spo2_avg": _g(r, "pulseOx", "avgValue"),
            "hydration_ml": _g(r, "hydration", "consumedInMl"),
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    # Días sin reloj: Garmin pone 0 pasos y nada más; se tratan como vacíos.
    no_watch = (~df["has_wellness"]) | (df["rhr"].isna() & (df["steps"].fillna(0) == 0))
    num = df.columns.difference(["date", "has_wellness"])
    df.loc[no_watch, num] = math.nan
    df["worn"] = ~no_watch
    return df.sort_values("date").reset_index(drop=True)


# ---------------------------------------------------------------- sueño
def sleep(store: Store) -> pd.DataFrame:
    rows = []
    for key, r in store.items("sleep"):
        total = r.get("sleepTimeSeconds")
        if not total:
            continue
        rows.append({
            "date": key,  # día en que te despiertas
            "start": _ms_local(r.get("sleepStartTimestampLocal")),
            "end": _ms_local(r.get("sleepEndTimestampLocal")),
            "sleep_h": total / 3600,
            "deep_h": (r.get("deepSleepSeconds") or 0) / 3600,
            "light_h": (r.get("lightSleepSeconds") or 0) / 3600,
            "rem_h": (r.get("remSleepSeconds") or 0) / 3600,
            "awake_h": (r.get("awakeSleepSeconds") or 0) / 3600,
            "nap_h": (r.get("napTimeSeconds") or 0) / 3600,
            "awake_count": r.get("awakeCount"),
            "score": _g(r, "sleepScores", "overall", "value"),
            "score_label": _g(r, "sleepScores", "overall", "qualifierKey"),
            "need_h": (_g(r, "sleepNeed", "actual") or 0) / 60 or None,
            "sleep_stress": r.get("avgSleepStress"),
            "resp": r.get("averageRespirationValue"),
            "spo2": r.get("averageSpO2Value"),
            "rem_capable": r.get("deviceRemCapable"),
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    # Hora de acostarse/levantarse en horas decimales. Acostarse: horas desde mediodía
    # para que 23:30 y 00:30 queden juntas (11,5 y 12,5) y la media tenga sentido.
    st = df["start"].dt.hour + df["start"].dt.minute / 60
    df["bed_from_noon"] = (st - 12) % 24
    df["bed_clock"] = st
    df["wake_clock"] = df["end"].dt.hour + df["end"].dt.minute / 60
    df["mid_from_noon"] = (df["bed_from_noon"] + (df["end"] - df["start"]).dt.total_seconds() / 7200)
    return df.sort_values("date").reset_index(drop=True)


# ---------------------------------------------------------------- HRV
def hrv(store: Store) -> pd.DataFrame:
    rows = []
    for key, r in store.items("hrv"):
        if not r.get("lastNightAvg"):
            continue
        rows.append({
            "date": key,
            "hrv": r.get("lastNightAvg"),
            "hrv_5min_high": r.get("lastNight5MinHigh"),
            "hrv_weekly": r.get("weeklyAvg"),
            "base_low": _g(r, "baseline", "balancedLow"),
            "base_high": _g(r, "baseline", "balancedUpper"),
            "status": r.get("status"),
        })
    df = pd.DataFrame(rows)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
    return df


def weight(store: Store) -> pd.DataFrame:
    rows = []
    for key, r in store.items("weight"):
        w = _g(r, "latestWeight", "weight")
        if w:
            lw = r.get("latestWeight") or {}
            rows.append({"date": key, "weight_kg": w / 1000, "source": lw.get("sourceType"),
                         "body_fat": lw.get("bodyFat"), "muscle_kg": (lw.get("muscleMass") or 0) / 1000 or None,
                         "bmi": lw.get("bmi")})
    df = pd.DataFrame(rows)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
    return df


# ---------------------------------------------------------------- actividades
SPORT_GROUP = {
    "running": "Correr", "trail_running": "Correr", "track_running": "Correr",
    "treadmill_running": "Cinta", "indoor_running": "Cinta",
    "cycling": "Bici", "indoor_cycling": "Bici", "road_biking": "Bici", "mountain_biking": "Bici",
    "lap_swimming": "Natación", "open_water_swimming": "Natación",
    "strength_training": "Fuerza", "walking": "Caminar", "hiking": "Caminar",
}


def activities(store: Store) -> pd.DataFrame:
    rows = []
    for key, a in store.items("activity"):
        det = store.get("activity_detail", key) or {}
        s = det.get("summaryDTO") or {}
        t = _g(a, "activityType", "typeKey", default="other")
        rows.append({
            "activity_id": int(key),
            "start": pd.to_datetime(a.get("startTimeLocal")),
            "name": a.get("activityName"),
            "type": t,
            "group": SPORT_GROUP.get(t, "Otros"),
            "distance_km": (a.get("distance") or 0) / 1000,
            "duration_min": (a.get("duration") or 0) / 60,
            "moving_min": (a.get("movingDuration") or a.get("duration") or 0) / 60,
            "avg_hr": a.get("averageHR"),
            "max_hr": a.get("maxHR"),
            "min_hr": s.get("minHR"),
            "avg_speed": a.get("averageSpeed"),  # m/s
            "calories": a.get("calories"),
            "elev_gain": a.get("elevationGain"),
            "cadence_spm": a.get("averageRunningCadenceInStepsPerMinute"),
            "stride_m": (a.get("avgStrideLength") or 0) / 100 or None,
            "gct_ms": a.get("avgGroundContactTime"),
            "vert_osc_cm": a.get("avgVerticalOscillation"),
            "vert_ratio": a.get("avgVerticalRatio"),
            "avg_power": a.get("avgPower"),
            **{f"z{i}_min": (a.get(f"hrTimeInZone_{i}") or 0) / 60 for i in range(1, 6)},
            "im_moderate": a.get("moderateIntensityMinutes"),
            "im_vigorous": a.get("vigorousIntensityMinutes"),
            "te_aerobic": a.get("aerobicTrainingEffectMessage"),
            "te_label": a.get("trainingEffectLabel"),
            "bb_delta": a.get("differenceBodyBattery"),
            "best_1k_s": a.get("fastestSplit_1000"),
            "best_5k_s": a.get("fastestSplit_5000"),
            "best_10k_s": a.get("fastestSplit_10000"),
            "best_21k_s": a.get("fastestSplit_21098"),
            "best_42k_s": a.get("fastestSplit_42195"),
            "rpe": s.get("directWorkoutRpe"),
            "feel": s.get("directWorkoutFeel"),
            "recovery_hr": s.get("recoveryHeartRate"),
            "location": a.get("locationName"),
            "is_pr": bool(a.get("pr") or a.get("isPR")),
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["date"] = df["start"].dt.normalize()
    df["pace_min_km"] = (df["moving_min"] / df["distance_km"]).where(df["distance_km"] > 0.2)
    return df.sort_values("start").reset_index(drop=True)


# ---------------------------------------------------------------- FIT
FIT_COLUMNS = ["activity_id", "ts", "hr", "speed", "cadence", "distance", "altitude", "power"]


def parse_new_fits(store: Store) -> int:
    """Lee los FIT aún no procesados. Guarda el resumen en `raw` y los registros en
    la tabla `fit_records`."""
    done = store.keys("fit_summary")
    files = sorted(p for p in FIT_DIR.glob("*.fit") if p.stem not in done)
    for i, p in enumerate(files, 1):
        try:
            summary, rec = parse_fit(p)
        except Exception as e:  # FIT corrupto: se marca y se sigue
            log.warning("FIT %s ilegible: %s", p.name, e)
            store.put("fit_summary", p.stem, {"error": str(e)})
            continue
        if not rec.empty:
            rec.insert(0, "activity_id", int(p.stem))
            rec["ts"] = rec["ts"].dt.tz_convert(None)
            rec = rec.reindex(columns=FIT_COLUMNS)
            if _table_exists(store, "fit_records"):
                store.conn.execute("DELETE FROM fit_records WHERE activity_id = ?", (int(p.stem),))
            rec.to_sql("fit_records", store.conn, if_exists="append", index=False)
        summary["n_records"] = len(rec)
        store.put("fit_summary", p.stem, summary)
        if i % 25 == 0:
            log.info("  FIT leídos %d/%d", i, len(files))
            store.commit()
    store.commit()
    return len(files)


def _table_exists(store: Store, name: str) -> bool:
    return store.conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def fit_summary(store: Store) -> pd.DataFrame:
    rows = [{"activity_id": int(k), **v} for k, v in store.items("fit_summary") if "error" not in v]
    return pd.DataFrame(rows)


def fit_records(store: Store, activity_ids) -> pd.DataFrame:
    if not _table_exists(store, "fit_records"):
        return pd.DataFrame()
    ids = ",".join(str(int(i)) for i in activity_ids) or "-1"
    return pd.read_sql(f"SELECT * FROM fit_records WHERE activity_id IN ({ids})", store.conn,
                       parse_dates=["ts"])


def profile(store: Store) -> dict:
    settings = store.get("profile", "settings") or {}
    zones = store.get("profile", "hr_zones") or []
    z = next((x for x in zones if x.get("sport") == "DEFAULT"), zones[0] if zones else {})
    fa_items = list(store.items("fitness_age"))
    fa = fa_items[-1][1] if fa_items else {}
    return {
        "display_name": settings.get("displayName"),
        "max_hr": z.get("maxHeartRateUsed"),
        "rest_hr": z.get("restingHeartRateUsed"),
        "zones": [z.get(f"zone{i}Floor") for i in range(1, 6)],
        "age": fa.get("chronologicalAge"),
        "fitness_age": fa.get("fitnessAge"),
        "achievable_fitness_age": fa.get("achievableFitnessAge"),
    }


def write_tables(store: Store, tables: dict[str, pd.DataFrame]) -> None:
    """Escribe las tablas limpias en el mismo SQLite (prefijo t_) para consultas libres."""
    for name, df in tables.items():
        if df is not None and not df.empty:
            df.to_sql(f"t_{name}", store.conn, if_exists="replace", index=False)
    store.commit()
