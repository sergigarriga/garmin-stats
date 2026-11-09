"""Análisis: une las tablas en una serie diaria y genera conclusiones en castellano."""

from __future__ import annotations

import math
from datetime import date

import numpy as np
import pandas as pd

from . import metrics as M

DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]


# ================================================================ datos
def assemble(t: dict, prof: dict) -> dict:
    daily, sleep, hrv, acts = t["daily"], t["sleep"], t["hrv"], t["activities"]
    start = min(x["date"].min() for x in (daily, acts) if not x.empty)
    end = pd.Timestamp(date.today())
    days = pd.date_range(start, end, freq="D")
    load = M.training_load(acts, days) if not acts.empty else pd.DataFrame({"date": days})
    day = pd.DataFrame(index=days)
    day.index.name = "date"
    for df in (daily, sleep.drop(columns=["start", "end"], errors="ignore"), hrv, load):
        if not df.empty:
            day = day.join(df.set_index("date"), how="left", rsuffix="_dup")
    day = day[[c for c in day.columns if not c.endswith("_dup")]]
    return {"day": day, "acts": acts, "sleep": sleep, "hrv": hrv, "load": load, "prof": prof,
            "weight": t.get("weight", pd.DataFrame()), "start": start, "end": end}


# ================================================================ conclusiones
def _fmt_h(h: float) -> str:
    if h is None or math.isnan(h):
        return "–"
    m = int(round(h * 60))
    return f"{m // 60} h {m % 60:02d} min"


def _clock(hours_from_noon: float) -> str:
    h = (hours_from_noon + 12) % 24
    m = int(round(h * 60)) % 1440
    return f"{m // 60:02d}:{m % 60:02d}"


def insights(A: dict, am: pd.DataFrame, rel: pd.DataFrame, best: pd.DataFrame) -> dict:
    day, sleep, load, prof = A["day"], A["sleep"], A["load"], A["prof"]
    out: dict[str, list[str]] = {"datos": [], "sueno": [], "corazon": [], "entreno": [],
                                 "carrera": [], "relaciones": [], "acciones": []}
    worn = day["rhr"].notna() if "rhr" in day else pd.Series(False, index=day.index)
    out["datos"].append(f"Periodo analizado: {A['start']:%d-%m-%Y} a {A['end']:%d-%m-%Y} "
                        f"({len(day)} días). Días con datos del reloj: {int(worn.sum())}.")
    months = worn.groupby(day.index.to_period("M")).sum()
    gaps = [str(p) for p, n in months.items() if n < 5]
    if gaps:
        out["datos"].append("Meses casi sin datos diarios (reloj sin llevar o sin sincronizar): "
                            + ", ".join(gaps) + ".")

    # ---- sueño
    if not sleep.empty:
        s = sleep
        last = s[s["date"] >= s["date"].max() - pd.Timedelta(days=90)]
        out["sueno"].append(f"Duermes de media {_fmt_h(s['sleep_h'].mean())} "
                            f"(últimos 90 días: {_fmt_h(last['sleep_h'].mean())}).")
        short = (s["sleep_h"] < 7).mean() * 100
        out["sueno"].append(f"El {short:.0f} % de las noches duermes menos de 7 h "
                            "(lo recomendado para adultos son 7-9 h).")
        if s["score"].notna().any():
            out["sueno"].append(f"Puntuación de sueño media: {s['score'].mean():.0f}/100.")
        sd = M.circ_sd_hours(s["bed_from_noon"])
        out["sueno"].append(f"Te acuestas de media a las {_clock(s['bed_from_noon'].mean())} y te levantas a "
                            f"las {_clock(s['wake_clock'].mean() - 12)}. La hora de acostarte varía "
                            f"±{sd * 60:.0f} min de una noche a otra"
                            + (" (bastante irregular; >60 min empeora el sueño)." if sd > 1 else "."))
        wk = s[s["date"].dt.dayofweek < 5]["mid_from_noon"].mean()
        we = s[s["date"].dt.dayofweek >= 5]["mid_from_noon"].mean()
        if not math.isnan(wk) and not math.isnan(we):
            jl = (we - wk) * 60
            out["sueno"].append(f"Jet lag social: el punto medio de tu sueño en fin de semana se desplaza "
                                f"{jl:+.0f} min respecto a entre semana"
                                + (" (más de 1 h desajusta el reloj interno)." if abs(jl) > 60 else "."))
        deep = (s["deep_h"] / s["sleep_h"]).mean() * 100
        rem = (s["rem_h"] / s["sleep_h"]).mean() * 100
        out["sueno"].append(f"Fases: {deep:.0f} % profundo y {rem:.0f} % REM "
                            "(referencia habitual: 13-23 % profundo, 20-25 % REM).")

    # ---- corazón
    r = day["rhr"].dropna() if "rhr" in day else pd.Series(dtype=float)
    if len(r) > 60:
        first, last = r.iloc[:60].mean(), r.iloc[-60:].mean()
        out["corazon"].append(f"FC en reposo: {first:.1f} lpm en tus primeros 60 días con datos frente a "
                              f"{last:.1f} lpm en los últimos 60 ({last - first:+.1f} lpm). "
                              + ("Bajar es buena señal de forma." if last < first - 1 else
                                 "Subir puede indicar fatiga, poco sueño o menos entreno." if last > first + 1
                                 else "Estable."))
    h = day["hrv"].dropna() if "hrv" in day else pd.Series(dtype=float)
    if len(h) > 20:
        out["corazon"].append(f"HRV nocturna media: {h.mean():.0f} ms (últimas 30 noches con dato: "
                              f"{h.iloc[-30:].mean():.0f} ms). Compárala solo contigo mismo: varía mucho entre personas.")
    if prof.get("fitness_age"):
        out["corazon"].append(f"Edad física según Garmin: {prof['fitness_age']:.0f} años "
                              f"(edad real {prof.get('age')}; alcanzable {(prof.get('achievable_fitness_age') or 0):.0f}).")

    # ---- entreno
    acts = A["acts"]
    if not acts.empty:
        recent = acts[acts["date"] >= A["end"] - pd.Timedelta(weeks=12)]
        out["entreno"].append(f"{len(acts)} actividades en total. Últimas 12 semanas: {len(recent)} sesiones, "
                              f"{recent['duration_min'].sum() / 60 / 12:.1f} h por semana de media.")
        end = A["end"]
        h8 = acts[acts["date"] >= end - pd.Timedelta(weeks=8)]["duration_min"].sum() / 60 / 8
        prev = acts[(acts["date"] < end - pd.Timedelta(weeks=8)) & (acts["date"] >= end - pd.Timedelta(weeks=34))]
        h_prev = prev["duration_min"].sum() / 60 / 26
        from . import settings
        recent_gap = any(date.fromisoformat(g["to"]) >= (end - pd.Timedelta(weeks=8)).date() for g in settings.watch_gaps())
        if h_prev > 1 and h8 < 0.4 * h_prev and not recent_gap:
            out["entreno"].append(f"Parón: las últimas 8 semanas entrenas {h8:.1f} h/semana frente a {h_prev:.1f} h/semana "
                                  "en los 6 meses anteriores. La forma (CTL) y el VO2max bajan tras 3-4 semanas sin estímulo.")
            out["acciones"].append(f"Vuelta progresiva: tras el parón, empieza con ~{max(1.5, h_prev * 0.5):.1f} h/semana "
                                   "de rodaje suave y sube como máximo un 10 % por semana.")
        z = acts[[f"z{i}_min" for i in range(1, 6)]].sum()
        if z.sum() > 0:
            easy = (z["z1_min"] + z["z2_min"]) / z.sum() * 100
            hard = (z["z4_min"] + z["z5_min"]) / z.sum() * 100
            out["entreno"].append(f"Intensidad global: {easy:.0f} % suave (Z1-Z2), {z['z3_min'] / z.sum() * 100:.0f} % "
                                  f"moderado (Z3), {hard:.0f} % duro (Z4-Z5). Referencia para fondo: ~80 % suave.")
        if "acwr" in load and load["acwr"].notna().any():
            l90 = load[load["date"] >= A["end"] - pd.Timedelta(days=90)]
            risky = int((l90["acwr"] > 1.5).sum())
            cur = load["acwr"].dropna().iloc[-1]
            out["entreno"].append(f"ACWR actual {cur:.2f}. En los últimos 90 días hubo {risky} días por encima de 1,5 "
                                  "(subidas bruscas de carga, el patrón típico antes de lesiones).")
        if "ctl" in load:
            c = load.set_index("date")["ctl"]
            peak_date = c.idxmax()
            out["entreno"].append(f"Tu forma (CTL) está en {c.iloc[-1]:.0f}; el pico fue {c.max():.0f} "
                                  f"el {peak_date:%d-%m-%Y}.")

    # ---- carrera
    runs = am[am["group"].isin(M.RUN_GROUPS)]
    if not runs.empty:
        out["carrera"].append(f"{len(runs)} carreras, {runs['distance_km'].sum():.0f} km en total.")
        v = am.dropna(subset=["vo2max_fit"]).sort_values("date") if "vo2max_fit" in am else pd.DataFrame()
        if len(v) >= 2:
            out["carrera"].append(f"VO2max del reloj: {v['vo2max_fit'].iloc[0]:.1f} → {v['vo2max_fit'].iloc[-1]:.1f} "
                                  f"ml/kg/min (de {v['date'].iloc[0]:%m-%Y} a {v['date'].iloc[-1]:%m-%Y}).")
        out_runs = runs[(runs["group"] == "Correr") & runs["ef"].notna()].sort_values("date")
        if len(out_runs) >= 30:
            a, b = out_runs["ef"].iloc[:15].median(), out_runs["ef"].iloc[-15:].median()
            out["carrera"].append(f"Eficiencia aeróbica (exterior): {a:.2f} → {b:.2f} ({(b / a - 1) * 100:+.0f} %). "
                                  "Más alto = corres más rápido con el mismo pulso.")
        dc = runs["decoupling_pct"].dropna()
        if len(dc) >= 5:
            out["carrera"].append(f"Desacople medio en carreras ≥ 40 min: {dc.median():.1f} % "
                                  f"({(dc > 5).mean() * 100:.0f} % de ellas por encima del 5 %). Con pulso de muñeca cada "
                                  "carrera suelta es ruidosa: fíjate en la mediana, no en puntos aislados.")
        if not best.empty:
            for b in best.itertuples():
                out["carrera"].append(f"Mejor {b.distance}: {M.fmt_time(b.best_s)} ({b.best_date:%d-%m-%Y}).")

    # ---- relaciones
    for x in rel.dropna(subset=["rho"]).sort_values("rho", key=abs, ascending=False).itertuples():
        if abs(x.rho) < 0.2:
            continue
        sentido = "más" if x.rho > 0 else "menos"
        out["relaciones"].append(f"{x.a} → {x.b}: relación {x.strength} (ρ = {x.rho:+.2f}, {x.n} días). "
                                 f"Cuando sube lo primero, suele haber {sentido} de lo segundo.")
    if not out["relaciones"]:
        out["relaciones"].append("No aparecen relaciones claras (|ρ| ≥ 0,2) con los datos actuales.")

    # ---- acciones
    if not sleep.empty and (sleep["sleep_h"] < 7).mean() > 0.4:
        out["acciones"].append("Sueño, lo más urgente: más del 40 % de noches por debajo de 7 h. Adelantar 30 min la "
                               "hora de acostarte es la mejora con más retorno en HRV y recuperación.")
    if not sleep.empty and M.circ_sd_hours(sleep["bed_from_noon"]) > 1:
        out["acciones"].append("Horario más regular: acostarte a la misma hora (±30 min), también el fin de semana.")
    if not acts.empty:
        z = acts[[f"z{i}_min" for i in range(1, 6)]].sum()
        if z.sum() > 0 and (z["z1_min"] + z["z2_min"]) / z.sum() < 0.7:
            out["acciones"].append("Más rodajes suaves: menos del 70 % del tiempo es suave. Hacer la mayoría de "
                                   "kilómetros en Z2 (puedes hablar mientras corres) mejora la base aeróbica.")
    dc = am["decoupling_pct"].dropna() if "decoupling_pct" in am else pd.Series(dtype=float)
    if len(dc) >= 5 and dc.median() > 5:
        out["acciones"].append("El pulso se dispara al final de las carreras largas: alarga poco a poco la tirada "
                               "larga a ritmo suave.")
    if "acwr" in load and (load["acwr"].tail(90) > 1.5).sum() > 5:
        out["acciones"].append("Sube la carga de forma más gradual (≤ 10 % por semana) para evitar picos de ACWR > 1,5.")
    if not out["acciones"]:
        out["acciones"].append("Sin alertas: mantener la regularidad.")
    return out


# ================================================================ tablas
def monthly_table(day: pd.DataFrame, acts: pd.DataFrame) -> pd.DataFrame:
    g = day.groupby(day.index.to_period("M"))
    t = pd.DataFrame({
        "Días con reloj": g["rhr"].count(),
        "Pasos/día": g["steps"].mean().round(0),
        "FC reposo": g["rhr"].mean().round(1),
        "HRV (ms)": g["hrv"].mean().round(0) if "hrv" in day else np.nan,
        "Sueño (h)": g["sleep_h"].mean().round(2) if "sleep_h" in day else np.nan,
        "Nota sueño": g["score"].mean().round(0) if "score" in day else np.nan,
        "Estrés": g["stress_avg"].mean().round(0),
        "TRIMP total": g["load"].sum().round(0) if "load" in day else np.nan,
    })
    if not acts.empty:
        a = acts.groupby(acts["date"].dt.to_period("M"))
        t["Sesiones"] = a.size()
        t["Horas entreno"] = (a["duration_min"].sum() / 60).round(1)
        run = acts[acts["group"].isin(M.RUN_GROUPS)]
        t["Km corridos"] = run.groupby(run["date"].dt.to_period("M"))["distance_km"].sum().round(1)
    t.index = t.index.astype(str)
    t.index.name = "Mes"
    return t.sort_index(ascending=False)


