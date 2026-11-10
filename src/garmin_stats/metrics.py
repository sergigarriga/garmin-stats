"""Métricas derivadas: carga de entrenamiento, eficiencia, predicciones, correlaciones."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

RUN_GROUPS = ("Correr", "Cinta")


# ---------------------------------------------------------------- TRIMP
def _trimp(hr: np.ndarray, minutes: np.ndarray, rest: float, mx: float) -> float:
    """TRIMP de Banister (hombre): min × HRr × 0,64·e^(1,92·HRr)."""
    hrr = np.clip((hr - rest) / (mx - rest), 0, 1)
    return float(np.sum(minutes * hrr * 0.64 * np.exp(1.92 * hrr)))


def activity_metrics(acts: pd.DataFrame, fitsum: pd.DataFrame, rec: pd.DataFrame,
                     rest_hr: float, max_hr: float) -> pd.DataFrame:
    """Una fila por actividad: TRIMP, eficiencia aeróbica, desacople y VO2max del FIT."""
    if acts.empty:  # sin ninguna actividad (persona nueva, solo pasos y sueño): tabla vacía pero con sus columnas
        return pd.DataFrame(columns=["activity_id", "start", "date", "name", "type", "group", "distance_km", "duration_min",
                                     "pace_min_km", "avg_hr", "max_hr", "trimp", "ef", "decoupling_pct", "cadence_spm",
                                     "elev_gain", "calories", "is_pr"] + [f"z{i}_min" for i in range(1, 6)])
    out = []
    groups = dict(tuple(rec.groupby("activity_id"))) if not rec.empty else {}
    for a in acts.itertuples():
        row = {"activity_id": a.activity_id, "trimp": math.nan, "ef": math.nan,
               "decoupling_pct": math.nan, "trimp_source": None}
        r = groups.get(a.activity_id)
        if r is not None and r["hr"].notna().sum() > 30:
            r = r.sort_values("ts")
            dt = r["ts"].diff().dt.total_seconds().fillna(1).clip(0, 10) / 60
            ok = r["hr"].notna()
            row["trimp"] = _trimp(r.loc[ok, "hr"].to_numpy(float), dt[ok].to_numpy(), rest_hr, max_hr)
            row["trimp_source"] = "fit"
            if a.group in RUN_GROUPS and a.moving_min >= 20 and "speed" in r:
                mov = r[(r["speed"] > 1.6) & r["hr"].notna()]
                if "cadence" in mov and mov["cadence"].notna().any():
                    # Sensor óptico "enganchado" a la cadencia (FC ≈ pasos/min): muestras falsas.
                    spm = mov["cadence"] * 2
                    mov = mov[(mov["hr"] - spm).abs() > 3]
                if len(mov) > 120:
                    # Sin los 10 primeros minutos (calentamiento: el pulso aún sube).
                    t0 = mov["ts"].iloc[0] + pd.Timedelta(minutes=10)
                    steady = mov[mov["ts"] >= t0]
                    row["ef"] = (mov["speed"].mean() * 60) / mov["hr"].mean()
                    # Desacople solo en carreras de ritmo estable: en series el pulso
                    # sigue al cambio de ritmo y la medida no significa nada.
                    cv = steady["speed"].std() / steady["speed"].mean() if len(steady) else 1
                    if a.moving_min >= 40 and len(steady) > 240 and cv < 0.12:
                        half = len(steady) // 2
                        e1 = steady["speed"].iloc[:half].median() / steady["hr"].iloc[:half].median()
                        e2 = steady["speed"].iloc[half:].median() / steady["hr"].iloc[half:].median()
                        row["decoupling_pct"] = (e1 - e2) / e1 * 100
        elif pd.notna(a.avg_hr) and a.duration_min > 0:
            row["trimp"] = _trimp(np.array([a.avg_hr]), np.array([a.duration_min]), rest_hr, max_hr)
            row["trimp_source"] = "media"
        if math.isnan(row["ef"]) and a.group in RUN_GROUPS and pd.notna(a.avg_hr) \
                and pd.notna(a.avg_speed) and a.moving_min >= 20:
            row["ef"] = a.avg_speed * 60 / a.avg_hr
        out.append(row)
    m = pd.DataFrame(out)
    if not fitsum.empty:
        keep = [c for c in ("activity_id", "vo2max_fit", "avg_step_length", "avg_vertical_oscillation",
                            "avg_stance_time", "workout_rpe", "workout_feel") if c in fitsum]
        m = m.merge(fitsum[keep], on="activity_id", how="left")
    return acts.merge(m, on="activity_id", how="left")


def training_load(acts: pd.DataFrame, days: pd.DatetimeIndex) -> pd.DataFrame:
    """Carga diaria (TRIMP), fatiga (ATL, 7 d), forma (CTL, 42 d), frescura (TSB) y ACWR."""
    load = acts.groupby("date")["trimp"].sum().reindex(days, fill_value=0).fillna(0)
    df = pd.DataFrame({"load": load})
    df["atl"] = load.ewm(alpha=1 / 7, adjust=False).mean()
    df["ctl"] = load.ewm(alpha=1 / 42, adjust=False).mean()
    df["tsb"] = df["ctl"].shift(1) - df["atl"].shift(1)
    acute = load.rolling(7, min_periods=7).sum()
    chronic = load.rolling(28, min_periods=28).sum() / 4
    df["acwr"] = (acute / chronic).where(chronic > 20)
    df.index.name = "date"
    return df.reset_index()


# ---------------------------------------------------------------- carrera
def _daniels_vo2(v_m_min: float) -> float:
    return -4.60 + 0.182258 * v_m_min + 0.000104 * v_m_min ** 2


def _daniels_pct(t_min: float) -> float:
    return 0.8 + 0.1894393 * math.exp(-0.012778 * t_min) + 0.2989558 * math.exp(-0.1932605 * t_min)


def predict_time(vdot: float, meters: float) -> float:
    """Tiempo (s) para una distancia según la fórmula de Daniels/Gilbert (búsqueda binaria)."""
    lo, hi = 1.0, 600.0
    for _ in range(80):
        t = (lo + hi) / 2
        need = _daniels_vo2(meters / t) / _daniels_pct(t)
        if need > vdot:
            lo = t
        else:
            hi = t
    return t * 60


def vdot_from_effort(meters: float, seconds: float) -> float:
    t = seconds / 60
    return _daniels_vo2(meters / t) / _daniels_pct(t)


def fmt_time(seconds: float) -> str:
    if seconds is None or (isinstance(seconds, float) and math.isnan(seconds)):
        return "–"
    s = int(round(seconds))
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def fmt_pace(min_km: float) -> str:
    if min_km is None or (isinstance(min_km, float) and math.isnan(min_km)):
        return "–"
    m = int(min_km)
    s = int(round((min_km - m) * 60))
    if s == 60:
        m, s = m + 1, 0
    return f"{m}:{s:02d}/km"


def best_efforts(acts: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for col, label, meters in (("best_1k_s", "1 km", 1000), ("best_5k_s", "5 km", 5000),
                               ("best_10k_s", "10 km", 10000), ("best_21k_s", "Media maratón", 21097.5),
                               ("best_42k_s", "Maratón", 42195)):
        if col not in acts:
            continue
        s = acts[acts["group"] == "Correr"].dropna(subset=[col])
        if s.empty:
            continue
        best = s.loc[s[col].idxmin()]
        last = s[s["date"] >= s["date"].max() - pd.Timedelta(days=90)]
        rows.append({
            "distance": label, "meters": meters,
            "best_s": best[col], "best_date": best["date"],
            "best_90d_s": last[col].min() if not last.empty else math.nan,
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- correlaciones
def spearman(x: pd.Series, y: pd.Series) -> tuple[float, int]:
    d = pd.concat([x, y], axis=1).dropna()
    if len(d) < 20:
        return math.nan, len(d)
    return float(d.iloc[:, 0].rank().corr(d.iloc[:, 1].rank())), len(d)


def strength(rho: float) -> str:
    a = abs(rho)
    if math.isnan(rho):
        return "pocos datos"
    if a < 0.1:
        return "ninguna"
    if a < 0.3:
        return "débil"
    if a < 0.5:
        return "moderada"
    return "fuerte"


def relations(day: pd.DataFrame) -> pd.DataFrame:
    """Relaciones entre hábitos y recuperación. `day` está indexado por fecha y la noche
    lleva la fecha del día en que te despiertas."""
    nxt = day.shift(-1)  # valor del día siguiente
    prev = day.shift(1)
    pairs = [
        ("Horas de sueño", "HRV de esa noche", day["sleep_h"], day["hrv"]),
        ("Horas de sueño", "FC en reposo de ese día", day["sleep_h"], day["rhr"]),
        ("Horas de sueño", "Body Battery máximo", day["sleep_h"], day["bb_max"]),
        ("Hora de acostarse (más tarde)", "Puntuación de sueño", day["bed_from_noon"], day["score"]),
        ("Carga de entreno del día anterior", "HRV de la noche", prev["load"], day["hrv"]),
        ("Carga de entreno del día anterior", "FC en reposo", prev["load"], day["rhr"]),
        ("Estrés medio del día", "Puntuación de sueño de esa noche", day["stress_avg"], nxt["score"]),
        ("Estrés medio del día", "HRV de esa noche", day["stress_avg"], nxt["hrv"]),
        ("Pasos del día", "Horas de sueño de esa noche", day["steps"], nxt["sleep_h"]),
        ("Pasos del día", "Puntuación de sueño de esa noche", day["steps"], nxt["score"]),
        ("Estrés durante el sueño", "Puntuación de sueño", day["sleep_stress"], day["score"]),
        ("HRV de la noche", "Estrés medio del día", day["hrv"], day["stress_avg"]),
    ]
    rows = []
    for a, b, x, y in pairs:
        rho, n = spearman(x, y)
        rows.append({"a": a, "b": b, "rho": rho, "n": n, "strength": strength(rho)})
    return pd.DataFrame(rows)


def circ_sd_hours(hours_from_noon: pd.Series) -> float:
    return float(hours_from_noon.dropna().std())
