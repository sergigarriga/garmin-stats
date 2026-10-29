"""Exporta los datos para la web (site/data.js) y el resumen en Markdown."""

from __future__ import annotations

import json
import math
import re
from datetime import date, datetime

import pandas as pd

from . import metrics as M
from .analysis import insights
from . import extras as E


def _num(v, nd=2):
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return int(round(f)) if nd == 0 else round(f, nd)


def _clean(d: dict) -> dict:
    return {k: v for k, v in d.items() if v is not None}


DAY_FIELDS = {
    # columna: (clave en JSON, decimales)
    "steps": ("steps", 0), "step_goal": ("stepGoal", 0), "walk_km": ("walkKm", 2),
    "floors_up": ("floors", 0), "cal_total": ("cal", 0), "cal_active": ("calActive", 0),
    "rhr": ("rhr", 0), "hr_min": ("hrMin", 0), "hr_max": ("hrMax", 0),
    "im_moderate": ("imMod", 0), "im_vigorous": ("imVig", 0),
    "stress_avg": ("stress", 0), "stress_high_h": ("stressHighH", 2), "stress_rest_h": ("stressRestH", 2),
    "bb_max": ("bbMax", 0), "bb_min": ("bbMin", 0), "bb_charged": ("bbCharged", 0), "bb_drained": ("bbDrained", 0),
    "resp_avg": ("resp", 1), "spo2_avg": ("spo2", 0),
    "sleep_h": ("sleepH", 2), "deep_h": ("deepH", 2), "rem_h": ("remH", 2), "light_h": ("lightH", 2),
    "awake_h": ("awakeH", 2), "score": ("sleepScore", 0), "need_h": ("sleepNeedH", 2),
    "bed_from_noon": ("bed", 2), "wake_clock": ("wake", 2), "sleep_stress": ("sleepStress", 0),
    "hrv": ("hrv", 0), "base_low": ("hrvLow", 0), "base_high": ("hrvHigh", 0),
    "load": ("load", 0), "atl": ("atl", 1), "ctl": ("ctl", 1), "tsb": ("tsb", 1), "acwr": ("acwr", 2),
    "ready": ("ready", 0),
}


def payload(A: dict, am: pd.DataFrame, last_sync: str | None) -> dict:
    day = A["day"].copy()
    ready, ready_latest = E.readiness(day)
    day["ready"] = ready
    rel = M.relations(day)
    best = M.best_efforts(am) if not am.empty else pd.DataFrame()
    ins = insights(A, am, rel, best)
    # Coma decimal en castellano (las fechas usan guiones, no se tocan).
    ins = {k: [re.sub(r"(\d)\.(\d)", r"\1,\2", t) for t in v] for k, v in ins.items()}

    days = []
    for ts, row in day.iterrows():
        rec = {"d": ts.strftime("%Y-%m-%d")}
        for col, (key, nd) in DAY_FIELDS.items():
            if col in row:
                rec[key] = _num(row[col], nd)
        days.append(_clean(rec))

    acts = []
    for a in am.sort_values("start").itertuples():
        acts.append(_clean({
            "id": int(a.activity_id), "start": a.start.strftime("%Y-%m-%dT%H:%M"), "name": a.name,
            "type": a.type, "group": a.group, "km": _num(a.distance_km, 2), "min": _num(a.duration_min, 1),
            "pace": _num(a.pace_min_km, 3), "hr": _num(a.avg_hr, 0), "hrMax": _num(a.max_hr, 0),
            "trimp": _num(a.trimp, 0), "ef": _num(a.ef, 3), "dec": _num(a.decoupling_pct, 1),
            "vo2": _num(getattr(a, "vo2max_fit", None), 1), "cad": _num(a.cadence_spm, 0),
            "elev": _num(a.elev_gain, 0), "cal": _num(a.calories, 0),
            "z": [_num(getattr(a, f"z{i}_min"), 1) or 0 for i in range(1, 6)],
            "pr": bool(a.is_pr) or None,
        }))

    preds = []
    v = am.dropna(subset=["vo2max_fit"]).sort_values("date") if "vo2max_fit" in am else pd.DataFrame()
    if not v.empty:
        vd = float(v["vo2max_fit"].iloc[-1])
        for label, meters in (("5 km", 5000), ("10 km", 10000), ("Media maratón", 21097.5), ("Maratón", 42195)):
            t = M.predict_time(vd, meters)
            b = best[best["distance"] == label] if not best.empty else pd.DataFrame()
            preds.append(_clean({
                "distance": label, "predicted": round(t), "pace": _num(t / 60 / (meters / 1000), 3),
                "best": _num(b["best_s"].iloc[0], 0) if not b.empty else None,
                "bestDate": b["best_date"].iloc[0].strftime("%Y-%m-%d") if not b.empty else None,
                "best90": _num(b["best_90d_s"].iloc[0], 0) if not b.empty else None,
            }))

    worn = day["rhr"].notna() if "rhr" in day else pd.Series(False, index=day.index)  # mismo criterio que las conclusiones
    g = worn.groupby(day.index.to_period("M"))
    coverage = [{"month": str(m), "worn": int(v.sum()), "days": int(len(v))} for m, v in g]

    prof = A["prof"]
    return {
        "coverage": coverage,
        "readiness": ready_latest,
        "alerts": E.alerts(day),
        "weeks": E.last_weeks(day, am),
        "records": E.records(am, day) if not am.empty else [],
        "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "lastSync": last_sync,
        "period": {"start": A["start"].strftime("%Y-%m-%d"), "end": A["end"].strftime("%Y-%m-%d")},
        "profile": _clean({k: (_num(v, 1) if isinstance(v, (int, float)) else v) for k, v in prof.items()
                           if k != "display_name" and not isinstance(v, list)}) | {"zones": prof.get("zones")},
        "days": days,
        "activities": acts,
        "insights": ins,
        "relations": [_clean({"a": r.a, "b": r.b, "rho": _num(r.rho, 2), "n": int(r.n), "strength": r.strength})
                      for r in rel.itertuples()],
        "predictions": preds,
    }


def write_site(data: dict, site_dir) -> object:
    """data.js se carga con <script>, así la web funciona abriendo el HTML (file://)."""
    site_dir.mkdir(parents=True, exist_ok=True)
    try:  # versión del HTML compilado: si cambia, la página abierta se recarga sola
        m = re.search(r'name="app-build" content="(\d+)"', (site_dir / "index.html").read_text(encoding="utf-8"))
        if m:
            data["appBuild"] = m.group(1)
    except OSError:
        pass
    out = site_dir / "data.js"
    tmp = out.with_suffix(".js.tmp")
    tmp.write_text("window.__GARMIN__=" + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n",
                   encoding="utf-8")
    tmp.replace(out)  # escritura atómica: la página nunca lee un archivo a medias
    return out


def write_markdown(data: dict, out_dir) -> object:
    out_dir.mkdir(parents=True, exist_ok=True)
    titles = {"acciones": "Qué te recomiendo", "datos": "Datos", "sueno": "Sueño", "corazon": "Corazón",
              "entreno": "Entrenamiento", "carrera": "Carrera", "relaciones": "Relaciones"}
    md = [f"# Resumen Garmin ({data['generatedAt'][:16].replace('T', ' ')})", ""]
    for k, t in titles.items():
        items = data["insights"].get(k) or []
        if items:
            md += [f"## {t}", ""] + [f"- {x}" for x in items] + [""]
    path = out_dir / f"resumen-{date.today().isoformat()}.md"
    path.write_text("\n".join(md), encoding="utf-8")
    return path
