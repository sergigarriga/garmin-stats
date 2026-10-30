"""Preparación diaria, avisos, resumen de la semana, récords y detalle de cada actividad."""

from __future__ import annotations

import json
import logging
import math
from datetime import date, timedelta
from pathlib import Path

import fitdecode
import numpy as np
import pandas as pd

from . import FIT_DIR

log = logging.getLogger(__name__)


def _f(v, nd=1):
    if v is None:
        return None
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(v) or math.isinf(v):
        return None
    return int(round(v)) if nd == 0 else round(v, nd)


# ======================================================================== preparación
READY_LABELS = [
    (80, "Óptima", "Tu cuerpo está listo para un entreno exigente."),
    (60, "Buena", "Buen día para entrenar con normalidad."),
    (40, "Moderada", "Mejor un entreno suave o técnico."),
    (0, "Baja", "Hoy toca descanso o algo muy suave."),
]


def _label(score: float):
    for lim, name, msg in READY_LABELS:
        if score >= lim:
            return name, msg
    return READY_LABELS[-1][1:]


def readiness(day: pd.DataFrame) -> tuple[pd.Series, dict | None]:
    """Puntuación 0-100 por día frente a TU normalidad (28 días previos):
    HRV 30 %, sueño 30 %, pulso en reposo 20 %, carga 20 %. Se reparte el peso si falta algo."""
    d = day

    def base(col, fn):
        # Normalidad = tus 28 mediciones anteriores (aunque haya huecos sin reloj).
        v = d[col].dropna()
        r = getattr(v.shift(1).rolling(28, min_periods=7), fn)()
        return r.reindex(d.index).ffill()

    hrv_m, hrv_s = base("hrv", "mean"), base("hrv", "std")
    rhr_m = base("rhr", "mean")

    comp = pd.DataFrame(index=d.index)
    z = (d["hrv"] - hrv_m) / hrv_s.clip(lower=3)
    comp["hrv"] = (55 + 22 * z).clip(5, 100)
    dur = (d["sleep_h"] / 7.5 * 100).clip(0, 100)
    comp["sleep"] = (0.6 * d["score"] + 0.4 * dur).where(d["score"].notna(), dur)
    delta = d["rhr"] - rhr_m
    comp["rhr"] = (75 - 9 * delta).clip(5, 100)
    acwr = d["acwr"].shift(1) if "acwr" in d else pd.Series(np.nan, index=d.index)
    load = pd.Series(np.interp(acwr.fillna(1.0), [0, 1.0, 1.3, 1.5, 2.0], [85, 80, 62, 42, 15]), index=d.index)
    comp["load"] = load.where(d["rhr"].notna() | d["sleep_h"].notna())

    w = {"hrv": 0.3, "sleep": 0.3, "rhr": 0.2, "load": 0.2}
    num = sum(comp[k].fillna(0) * v for k, v in w.items())
    den = sum(comp[k].notna() * v for k, v in w.items())
    has = comp[["hrv", "sleep", "rhr"]].notna().sum(axis=1) >= 2
    score = (num / den).where(has & (den > 0))

    latest = None
    s = score.dropna()
    if not s.empty:
        dt = s.index[-1]
        row, val = d.loc[dt], float(s.iloc[-1])
        name, msg = _label(val)
        parts = []
        if pd.notna(comp.at[dt, "hrv"]):
            parts.append({"key": "hrv", "label": "HRV", "score": _f(comp.at[dt, "hrv"], 0),
                          "detail": f"{_f(row['hrv'], 0)} ms frente a tu media de {_f(hrv_m.at[dt], 0)} ms"})
        if pd.notna(comp.at[dt, "sleep"]):
            parts.append({"key": "sleep", "label": "Sueño", "score": _f(comp.at[dt, "sleep"], 0),
                          "detail": (f"{int(row['sleep_h'])} h {int(round(row['sleep_h'] % 1 * 60)):02d} min"
                                     + (f" · nota {int(row['score'])}" if pd.notna(row.get("score")) else ""))})
        if pd.notna(comp.at[dt, "rhr"]):
            dl = row["rhr"] - rhr_m.at[dt]
            parts.append({"key": "rhr", "label": "Pulso en reposo", "score": _f(comp.at[dt, "rhr"], 0),
                          "detail": f"{_f(row['rhr'], 0)} lpm, " + (
                              "igual que tu media" if abs(dl) < 0.5 else
                              f"{abs(dl):.0f} {'más' if dl > 0 else 'menos'} que tu media")})
        if pd.notna(comp.at[dt, "load"]):
            a = acwr.at[dt]
            parts.append({"key": "load", "label": "Carga reciente", "score": _f(comp.at[dt, "load"], 0),
                          "detail": "sin entrenos recientes" if pd.isna(a) else f"ratio de carga {a:.2f}".replace(".", ",")})
        latest = {"date": dt.strftime("%Y-%m-%d"), "score": _f(val, 0), "label": name, "message": msg, "parts": parts}
    return score, latest


# ======================================================================== avisos
def alerts(day: pd.DataFrame) -> list[dict]:
    """Avisos suaves cuando algo se sale de tu normalidad (solo con datos recientes)."""
    out = []
    today = pd.Timestamp(date.today())
    recent = day[day.index >= today - pd.Timedelta(days=3)]
    if recent["rhr"].notna().sum() == 0 and (recent.get("sleep_h") is None or recent["sleep_h"].notna().sum() == 0):
        return out  # sin datos de los últimos días: no avisar de cosas viejas
    base = day[(day.index < today - pd.Timedelta(days=2)) & (day.index >= today - pd.Timedelta(days=32))]

    r_now = day["rhr"].dropna().tail(2)
    if len(r_now) and base["rhr"].notna().sum() >= 10 and r_now.mean() >= base["rhr"].mean() + 5:
        out.append({"id": "rhr-high", "category": "heart", "level": "attention",
                    "title": "Tu pulso en reposo está más alto de lo normal",
                    "body": f"{r_now.mean():.0f} lpm frente a tu media de {base['rhr'].mean():.0f}. Puede ser cansancio, "
                            "poco sueño, alcohol o un resfriado que empieza. Si se mantiene, tómatelo con calma."})
    h_now = day["hrv"].dropna().tail(2) if "hrv" in day else pd.Series(dtype=float)
    if len(h_now) == 2 and "base_low" in day:
        low = day["base_low"].dropna()
        if len(low) and (h_now < low.iloc[-1]).all():
            out.append({"id": "hrv-low", "category": "recovery", "level": "attention",
                        "title": "Tu HRV lleva dos noches por debajo de tu rango",
                        "body": f"{h_now.iloc[-1]:.0f} ms, por debajo de tu mínimo normal ({low.iloc[-1]:.0f} ms). "
                                "Tu cuerpo está recuperándose: prioriza dormir bien y entrena suave."})
    if "sleep_h" in day:
        last7 = day["sleep_h"].dropna()
        last7 = last7[last7.index >= today - pd.Timedelta(days=7)]
        if len(last7) >= 5 and (last7 < 7).mean() >= 0.85:
            out.append({"id": "sleep-debt", "category": "sleep", "level": "attention",
                        "title": "Llevas una semana durmiendo poco",
                        "body": f"{int((last7 < 7).sum())} de tus últimas {len(last7)} noches bajo 7 h (media "
                                f"{last7.mean():.1f} h). Una noche larga o una siesta corta ayudan a recuperar.".replace(".", ",", 1)})
    if "acwr" in day and pd.notna(day["acwr"].iloc[-1]) and day["acwr"].iloc[-1] > 1.5:
        out.append({"id": "acwr-high", "category": "training", "level": "attention",
                    "title": "Has subido la carga muy de golpe",
                    "body": f"Esta semana entrenas {day['acwr'].iloc[-1]:.1f} veces tu media del último mes. ".replace(".", ",", 1)
                            + "Es el patrón típico antes de una lesión: mete un día suave."})
    bb = day["bb_max"].dropna().tail(3)
    if len(bb) == 3 and (bb < 50).all() and bb.index[-1] >= today - pd.Timedelta(days=2):
        out.append({"id": "bb-low", "category": "energy", "level": "info",
                    "title": "Te estás levantando con poca energía",
                    "body": f"Tu Body Battery no pasa de {bb.max():.0f} en los últimos 3 días. Dormir antes y bajar el "
                            "ritmo por la tarde suele ayudar a recargar."})
    for a in out:
        a["date"] = today.strftime("%Y-%m-%d")
    return out


# ======================================================================== semana
def _week_stats(day: pd.DataFrame, acts: pd.DataFrame, start: pd.Timestamp) -> dict:
    end = start + pd.Timedelta(days=6)
    d = day[(day.index >= start) & (day.index <= end)]
    a = acts[(acts["date"] >= start) & (acts["date"] <= end)] if not acts.empty else acts
    runs = a[a["group"].isin(["Correr", "Cinta"])] if not a.empty else a
    m = lambda c: _f(d[c].mean(), 1) if c in d and d[c].notna().any() else None  # noqa: E731
    return {
        "start": start.strftime("%Y-%m-%d"), "end": end.strftime("%Y-%m-%d"),
        "daysWorn": int(d["rhr"].notna().sum()),
        "sleepH": m("sleep_h"), "sleepScore": m("score"), "steps": _f(d["steps"].mean(), 0) if d["steps"].notna().any() else None,
        "rhr": m("rhr"), "hrv": m("hrv"), "stress": m("stress_avg"), "bbMax": m("bb_max"),
        "intensity": _f((d["im_moderate"].fillna(0) + 2 * d["im_vigorous"].fillna(0)).sum(), 0),
        "sessions": int(len(a)), "hours": _f(a["duration_min"].sum() / 60, 1) if len(a) else 0,
        "runKm": _f(runs["distance_km"].sum(), 1) if len(runs) else 0,
        "load": _f(d["load"].sum(), 0) if "load" in d else None,
        "nightsUnder7": int((d["sleep_h"] < 7).sum()) if "sleep_h" in d else None,
    }


def last_weeks(day: pd.DataFrame, acts: pd.DataFrame) -> dict:
    """Última semana completa (lunes a domingo) y la anterior."""
    today = pd.Timestamp(date.today())
    this_monday = today - pd.Timedelta(days=today.dayofweek)
    last = this_monday - pd.Timedelta(days=7)
    return {"current": _week_stats(day, acts, this_monday),
            "last": _week_stats(day, acts, last),
            "previous": _week_stats(day, acts, last - pd.Timedelta(days=7))}


# ======================================================================== récords
def records(acts: pd.DataFrame, day: pd.DataFrame) -> list[dict]:
    out = []
    runs = acts[acts["group"] == "Correr"]
    for col, label in (("best_1k_s", "1 km"), ("best_5k_s", "5 km"), ("best_10k_s", "10 km"),
                       ("best_21k_s", "Media maratón"), ("best_42k_s", "Maratón")):
        s = runs.dropna(subset=[col]) if col in runs else pd.DataFrame()
        if not s.empty:
            b = s.loc[s[col].idxmin()]
            out.append({"group": "Carrera", "label": f"Mejor {label}", "value": float(b[col]), "kind": "time",
                        "date": b["date"].strftime("%Y-%m-%d"), "activityId": int(b["activity_id"])})
    if not runs.empty:
        b = runs.loc[runs["distance_km"].idxmax()]
        out.append({"group": "Carrera", "label": "Carrera más larga", "value": _f(b["distance_km"], 2), "kind": "km",
                    "date": b["date"].strftime("%Y-%m-%d"), "activityId": int(b["activity_id"])})
    if "vo2max_fit" in acts and acts["vo2max_fit"].notna().any():
        b = acts.loc[acts["vo2max_fit"].idxmax()]
        out.append({"group": "Carrera", "label": "VO2max más alto", "value": _f(b["vo2max_fit"], 1), "kind": "vo2",
                    "date": b["date"].strftime("%Y-%m-%d")})
    for col, label, kind, fn in (("steps", "Día con más pasos", "steps", "idxmax"),
                                 ("score", "Mejor nota de sueño", "score", "idxmax"),
                                 ("rhr", "Pulso en reposo más bajo", "bpm", "idxmin"),
                                 ("hrv", "HRV más alta", "ms", "idxmax")):
        if col in day and day[col].notna().any():
            idx = getattr(day[col], fn)()
            out.append({"group": "Salud", "label": label, "value": _f(day.at[idx, col], 0), "kind": kind,
                        "date": idx.strftime("%Y-%m-%d")})
    return out


# ======================================================================== detalle de actividad
DETAIL_VERSION = "3"
SEMI = 180 / 2 ** 31


def _parse_detail(path: Path) -> tuple[pd.DataFrame, list[dict]]:
    rows, laps = [], []
    with fitdecode.FitReader(path, check_crc=fitdecode.CrcCheck.DISABLED) as r:
        for fr in r:
            if not isinstance(fr, fitdecode.FitDataMessage):
                continue
            if fr.name == "record":
                v = {f.name: f.value for f in fr.fields}
                if v.get("timestamp") is None:
                    continue
                lat, lon = v.get("position_lat"), v.get("position_long")
                cad = v.get("cadence")
                if cad is not None and v.get("fractional_cadence"):
                    cad = cad + v["fractional_cadence"]
                rows.append({
                    "ts": v["timestamp"], "hr": v.get("heart_rate"),
                    "speed": v.get("enhanced_speed") if v.get("enhanced_speed") is not None else v.get("speed"),
                    "dist": v.get("distance"), "alt": v.get("enhanced_altitude") if v.get("enhanced_altitude") is not None else v.get("altitude"),
                    "cad": cad, "power": v.get("power"),
                    "lat": lat * SEMI if isinstance(lat, int) else None, "lon": lon * SEMI if isinstance(lon, int) else None,
                })
            elif fr.name == "lap":
                v = {f.name: f.value for f in fr.fields}
                laps.append({"time": _f(v.get("total_timer_time"), 0), "dist": _f(v.get("total_distance"), 0),
                             "hr": _f(v.get("avg_heart_rate"), 0),
                             "speed": _f(v.get("enhanced_avg_speed") or v.get("avg_speed"), 3),
                             "ascent": _f(v.get("total_ascent"), 0)})
    df = pd.DataFrame(rows)
    if not df.empty:
        df["ts"] = pd.to_datetime(df["ts"], utc=True)
        df = df.sort_values("ts").reset_index(drop=True)
        df["t"] = (df["ts"] - df["ts"].iloc[0]).dt.total_seconds()
    return df, laps


def _splits(df: pd.DataFrame) -> list[dict]:
    if df.empty or df["dist"].isna().all() or df["dist"].max() < 900:
        return []
    out, k, start = [], 1, 0
    d = df.dropna(subset=["dist"]).reset_index(drop=True)
    for i in range(len(d)):
        if d.at[i, "dist"] >= k * 1000 or i == len(d) - 1:
            seg = d.iloc[start:i + 1]
            secs = seg["t"].iloc[-1] - seg["t"].iloc[0]
            km = (seg["dist"].iloc[-1] - seg["dist"].iloc[0]) / 1000
            if km < 0.2:
                break
            alt = seg["alt"].dropna()
            out.append({"km": k if km > 0.95 else round(k - 1 + km, 2), "time": _f(secs, 0),
                        "pace": _f(secs / 60 / km, 3), "hr": _f(seg["hr"].mean(), 0),
                        "elev": _f(alt.iloc[-1] - alt.iloc[0], 0) if len(alt) > 1 else None})
            start, k = i, k + 1
    return out


def _downsample(df: pd.DataFrame, n: int) -> pd.DataFrame:
    step = max(1, math.ceil(len(df) / n))
    return df.iloc[::step]


def write_activity_details(am: pd.DataFrame, site_dir: Path, zones: list | None) -> int:
    """Un archivo site/acts/<id>.js por actividad (se carga bajo demanda con <script>)."""
    out_dir = site_dir / "acts"
    out_dir.mkdir(parents=True, exist_ok=True)
    # En AWS los detalles ya publicados están en S3: el handler deja aquí su lista para no rehacerlos.
    index = out_dir / "_published.txt"
    published = set(index.read_text().split()) if index.exists() else set()
    written = 0
    for a in am.itertuples():
        fit = FIT_DIR / f"{a.activity_id}.fit"
        dst = out_dir / f"{a.activity_id}.js"
        if not fit.exists() or str(a.activity_id) in published:
            continue
        if dst.exists():
            with dst.open() as f:
                if f.readline().strip() == f"// v{DETAIL_VERSION}":
                    continue
        try:
            df, laps = _parse_detail(fit)
        except Exception as e:  # FIT corrupto
            log.warning("Detalle %s: %s", a.activity_id, e)
            continue
        series, track = [], []
        if not df.empty:
            s = _downsample(df, 900)
            for r in s.itertuples():
                pace = 60 / (r.speed * 3.6) if r.speed and r.speed > 0.8 else None  # min/km
                series.append([_f(r.t, 0), _f(r.hr, 0), _f(pace, 2), _f(r.alt, 1),
                               _f(r.dist / 1000 if r.dist is not None else None, 3),
                               _f(r.cad * 2 if r.cad is not None and a.group in ("Correr", "Cinta") else r.cad, 0)])
            g = df.dropna(subset=["lat", "lon"])
            g = g[(g["lat"].abs() > 0.0001) | (g["lon"].abs() > 0.0001)]
            if len(g) > 10:
                track = [[round(x, 5), round(y, 5)] for x, y in _downsample(g, 700)[["lat", "lon"]].itertuples(index=False)]
        detail = {
            "id": int(a.activity_id), "series": series, "cols": ["t", "hr", "pace", "alt", "km", "cad"],
            "track": track, "splits": _splits(df), "laps": laps if len(laps) > 1 else [],
            "zones": [_f(getattr(a, f"z{i}_min"), 1) or 0 for i in range(1, 6)], "zoneFloors": zones,
            "elevGain": _f(a.elev_gain, 0), "minHr": _f(a.min_hr, 0), "recoveryHr": _f(a.recovery_hr, 0),
            "stride": _f(a.stride_m, 2), "gct": _f(a.gct_ms, 0), "vertOsc": _f(a.vert_osc_cm, 1),
            "power": _f(a.avg_power, 0), "location": a.location if isinstance(a.location, str) else None,
            "teLabel": a.te_label if isinstance(a.te_label, str) else None,
        }
        dst.write_text(f"// v{DETAIL_VERSION}\nwindow.__ACTS__=window.__ACTS__||{{}};window.__ACTS__[{int(a.activity_id)}]="
                       + json.dumps(detail, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
        written += 1
    return written
