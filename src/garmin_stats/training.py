"""Ritmos de referencia, zonas, natación y gimnasio a partir de data.js (Python puro, sin pandas).

Se calcula al final de cada informe y también en la Lambda de la API (que no lleva pandas) cuando la persona
introduce una marca o un test de natación, así la web lo ve al momento.

- Ritmos: modelo VDOT de Jack Daniels. Una marca reciente (o el VO2max del reloj) da los ritmos suave, de maratón,
  de media, de 10K, de 5K, de umbral, de series y de repeticiones; del de umbral salen 5 zonas de ritmo.
- Natación: CSS (velocidad crítica) con un test de 400 m y 200 m, y 5 zonas por 100 m.
- Gimnasio: 1RM estimado (Epley), series por grupo muscular y semana, kilos totales y récords por ejercicio.
"""

from __future__ import annotations

import math
from datetime import date, timedelta

# ======================================================================== VDOT (Daniels y Gilbert)


def _vo2_cost(v: float) -> float:
    """ml/kg/min de oxígeno que cuesta correr a v metros por minuto."""
    return -4.60 + 0.182258 * v + 0.000104 * v * v


def _sustainable(t_min: float) -> float:
    """Fracción del VO2max que se aguanta durante t minutos."""
    return 0.8 + 0.1894393 * math.exp(-0.012778 * t_min) + 0.2989558 * math.exp(-0.1932605 * t_min)


def vdot_from_race(meters: float, seconds: float) -> float:
    t = seconds / 60
    return _vo2_cost(meters / t) / _sustainable(t)


def race_time(vdot: float, meters: float) -> float:
    """Segundos que tardaría en una distancia alguien con este VDOT (búsqueda binaria)."""
    lo, hi = meters / 1000 * 100, meters / 1000 * 1200  # entre 1:40 y 20:00 /km
    for _ in range(70):
        mid = (lo + hi) / 2
        if vdot_from_race(meters, mid) > vdot:
            lo = mid  # demasiado rápido para este VDOT: más tiempo
        else:
            hi = mid
    return (lo + hi) / 2


def _speed_at(vo2: float) -> float:
    """m/min a los que se consume `vo2` ml/kg/min (raíz positiva de la ecuación de coste)."""
    a, b, c = 0.000104, 0.182258, -(4.60 + vo2)
    return (-b + math.sqrt(b * b - 4 * a * c)) / (2 * a)


def _pace_at(vdot: float, frac: float) -> float:
    """Segundos por km a una fracción del VDOT."""
    return 60_000 / _speed_at(vdot * frac)


REFS = ("easy", "marathon", "half", "10k", "5k", "threshold", "interval", "repetition")
REF_LABEL = {"easy": "Suave", "marathon": "Maratón", "half": "Media maratón", "10k": "10K", "5k": "5K",
             "threshold": "Umbral", "interval": "Series (VO2max)", "repetition": "Repeticiones"}
REF_USE = {
    "easy": "Rodajes y tiradas largas",
    "marathon": "Bloques largos a ritmo de maratón",
    "half": "Bloques a ritmo de media",
    "10k": "Series largas a ritmo de 10K",
    "5k": "Series a ritmo de 5K",
    "threshold": "Tempo y series de umbral (20-40 min en total)",
    "interval": "Series de 3-5 min (VO2max)",
    "repetition": "Repeticiones cortas y rápidas (200-400 m)",
}


def ref_paces(vdot: float) -> dict[str, int]:
    """Ritmos de referencia en s/km. Suave = el centro de la zona cómoda (unos 66 % del VDOT)."""
    r = round
    return {
        "easy": r(_pace_at(vdot, 0.66)),
        "marathon": r(race_time(vdot, 42195) / 42.195),
        "half": r(race_time(vdot, 21097.5) / 21.0975),
        "10k": r(race_time(vdot, 10000) / 10),
        "5k": r(race_time(vdot, 5000) / 5),
        "threshold": r(_pace_at(vdot, 0.88)),
        "interval": r(_pace_at(vdot, 0.975)),
        "repetition": r(_pace_at(vdot, 1.05)),
    }


def easy_range(vdot: float) -> tuple[int, int]:
    """Rango del ritmo suave (rápido, lento) en s/km: del 70 % al 60 % del VDOT."""
    return round(_pace_at(vdot, 0.70)), round(_pace_at(vdot, 0.60))


# Zonas de ritmo como múltiplo del ritmo de umbral (más alto = más lento). (más rápido, más lento)
PACE_ZONES = [(1, "Recuperación", 1.29, 1.45), (2, "Aeróbico", 1.14, 1.29), (3, "Tempo", 1.06, 1.14),
              (4, "Umbral", 0.99, 1.06), (5, "VO2max", 0.90, 0.99)]


def pace_zones(threshold_s: float) -> list[dict]:
    return [{"zone": z, "name": n, "fast": round(threshold_s * a), "slow": round(threshold_s * b)}
            for z, n, a, b in PACE_ZONES]


def mmss(sec: float | None) -> str | None:
    if sec is None:
        return None
    s = int(round(sec))
    return f"{s // 60}:{s % 60:02d}"


def resolve_step_pace(step: dict, refs: dict | None) -> tuple[int, int] | None:
    """Rango de ritmo (rápido, lento) en s/km de un paso del plan. Si el paso va a un ritmo de referencia
    (pace_ref), se calcula con tus ritmos ACTUALES: así el plan se ajusta solo cuando mejoras."""
    ref = step.get("pace_ref")
    if ref and refs and refs.get(ref):
        base = refs[ref] + (step.get("pace_ref_offset_s") or 0)
        m = 12 if ref == "easy" else 5
        return base - m, base + m

    def sec(p):
        if not p or ":" not in str(p):
            return None
        m, s = str(p).split(":", 1)
        try:
            return int(m) * 60 + int(s)
        except ValueError:
            return None
    f, s = sec(step.get("pace_fast")), sec(step.get("pace_slow"))
    if f and s:
        return min(f, s), max(f, s)
    return None


RACES = [("5 km", 5000), ("10 km", 10000), ("Media maratón", 21097.5), ("Maratón", 42195)]


def paces_block(data: dict, settings: dict) -> dict | None:
    """Ritmos de referencia y zonas. Fuente: tu marca (si la has puesto) > tu mejor tramo de los últimos 90 días >
    VO2max del reloj."""
    today = date.today()
    test = settings.get("race_test") or {}
    vo2 = next((a for a in reversed(data.get("activities") or []) if a.get("vo2")), None)
    recent = []
    for p in data.get("predictions") or []:
        meters = dict(RACES).get(p.get("distance"))
        if meters and p.get("best90"):
            recent.append((vdot_from_race(meters, p["best90"]), p["distance"], p["best90"]))
    best_recent = max(recent) if recent else None

    sources = []
    if test.get("distance_m") and test.get("time_s"):
        sources.append({"kind": "race", "vdot": vdot_from_race(test["distance_m"], test["time_s"]),
                        "label": f"Tu marca: {_dist_label(test['distance_m'])} en {_hms(test['time_s'])}",
                        "date": test.get("date")})
    # Lo que has corrido de verdad manda sobre la estimación del reloj (que suele ser optimista).
    if best_recent:
        sources.append({"kind": "recent", "vdot": best_recent[0],
                        "label": f"Tu mejor {best_recent[1].lower() if best_recent[1][0] == 'M' else best_recent[1]} "
                                 f"de los últimos 90 días ({_hms(best_recent[2])})", "date": None})
    if vo2:
        sources.append({"kind": "watch", "vdot": float(vo2["vo2"]), "label": f"VO2max del reloj ({vo2['vo2']:.1f})".replace(".", ","),
                        "date": vo2["start"][:10]})
    if not sources:
        return None
    src = sources[0]
    vdot = round(src["vdot"], 1)
    refs = ref_paces(vdot)
    fast, slow = easy_range(vdot)
    stale = bool(src["kind"] == "race" and src.get("date")
                 and date.fromisoformat(src["date"]) < today - timedelta(days=180))
    return {
        "vdot": vdot, "source": src["kind"], "sourceLabel": src["label"], "sourceDate": src.get("date"), "stale": stale,
        "others": [{"kind": s["kind"], "vdot": round(s["vdot"], 1), "label": s["label"]} for s in sources[1:]],
        "refs": refs, "easyRange": [fast, slow],
        "list": [{"key": k, "label": REF_LABEL[k], "use": REF_USE[k], "sec": refs[k]} for k in REFS],
        "zones": pace_zones(refs["threshold"]),
        "races": [{"distance": n, "time": round(race_time(vdot, m))} for n, m in RACES],
        "test": test or None,
    }


def _dist_label(m: float) -> str:
    named = {5000: "5 km", 10000: "10 km", 21097.5: "media maratón", 21098: "media maratón", 42195: "maratón"}
    return named.get(m) or (f"{m / 1000:g} km".replace(".", ",") if m >= 1000 else f"{m:g} m")


def _hms(sec: float) -> str:
    s = int(round(sec))
    h, m, r = s // 3600, s % 3600 // 60, s % 60
    return f"{h}:{m:02d}:{r:02d}" if h else f"{m}:{r:02d}"


# ======================================================================== natación
def css_from_test(t400_s: float, t200_s: float) -> float:
    """CSS en s/100 m: el ritmo de los 200 m que separan un 400 y un 200 a tope."""
    return (t400_s - t200_s) / 2


# Desfase sobre el CSS en s/100 m: (más rápido, más lento)
SWIM_ZONES = [(1, "Recuperación", 16, 30), (2, "Aeróbico", 8, 16), (3, "Tempo", 3, 8), (4, "Umbral (CSS)", -2, 3),
              (5, "Velocidad", -8, -2)]


def swim_zones(css: float) -> list[dict]:
    return [{"zone": z, "name": n, "fast": round(css + a), "slow": round(css + b)} for z, n, a, b in SWIM_ZONES]


def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def swim_block(data: dict, settings: dict, weeks: int = 16) -> dict | None:
    swims = [a for a in data.get("activities") or [] if a.get("group") == "Natación" and a.get("km")]
    test = settings.get("swim_test") or {}
    if not swims and not test:
        return None
    today = date.today()
    # ritmo medio por 100 m de cada sesión (tiempo en movimiento)
    rows = []
    for a in swims:
        pace100 = a["pace"] * 6 if a.get("pace") else None  # min/km → s/100 m
        rows.append({"id": a["id"], "d": a["start"][:10], "m": round(a["km"] * 1000), "min": a.get("min"),
                     "pace": round(pace100) if pace100 else None, "swolf": a.get("swolf"), "pool": a.get("poolM"),
                     "open": a.get("type") == "open_water_swimming"})
    year_ago = (today - timedelta(days=365)).isoformat()
    cont = [r for r in rows if r["pace"] and r["m"] >= 400 and r["d"] >= year_ago]
    best = min(cont, key=lambda r: r["pace"]) if cont else None
    if test.get("t400_s") and test.get("t200_s"):
        css, src = css_from_test(test["t400_s"], test["t200_s"]), "test"
    elif best:
        css, src = float(best["pace"]), "estimate"  # nado continuo más rápido: estimación prudente (algo lenta)
    else:
        css, src = None, None
    mon = _monday(today)
    wk = []
    for i in range(weeks - 1, -1, -1):
        s = mon - timedelta(weeks=i)
        e = s + timedelta(days=6)
        r = [x for x in rows if s.isoformat() <= x["d"] <= e.isoformat()]
        wk.append({"start": s.isoformat(), "m": sum(x["m"] for x in r), "sessions": len(r)})
    last90 = [r for r in rows if r["d"] >= (today - timedelta(days=90)).isoformat()]
    return {
        "css": round(css) if css else None, "cssSource": src, "test": test or None,
        "poolM": settings.get("pool_m") or next((r["pool"] for r in reversed(rows) if r.get("pool")), 25),
        "zones": swim_zones(css) if css else [],
        "weeks": wk, "sessions": rows[-30:],
        "best": best and {k: best[k] for k in ("d", "m", "pace", "id")},
        "longest": max(rows, key=lambda r: r["m"]) if rows else None,
        "totals": {"sessions": len(rows), "km": round(sum(r["m"] for r in rows) / 1000, 1),
                   "sessions90": len(last90), "km90": round(sum(r["m"] for r in last90) / 1000, 1)},
    }


# ======================================================================== gimnasio
# Categoría de ejercicio del reloj (nombre en castellano, ver extras.EXERCISES) → (músculo principal, secundarios)
MUSCLE_OF = {
    "Press de banca": ("chest", ("triceps", "shoulders")),
    "Aperturas": ("chest", ("shoulders",)),
    "Flexiones": ("chest", ("triceps", "shoulders")),
    "Dominadas": ("back", ("biceps",)),
    "Remo": ("back", ("biceps",)),
    "Encogimientos": ("back", ()),
    "Hiperextensiones": ("back", ("glutes", "hamstrings")),
    "Press de hombro": ("shoulders", ("triceps",)),
    "Elevaciones laterales": ("shoulders", ()),
    "Estabilidad de hombro": ("shoulders", ()),
    "Curl de bíceps": ("biceps", ()),
    "Extensión de tríceps": ("triceps", ()),
    "Sentadilla": ("quads", ("glutes", "hamstrings")),
    "Zancadas": ("quads", ("glutes",)),
    "Pliometría": ("quads", ("calves", "glutes")),
    "Peso muerto": ("hamstrings", ("glutes", "back")),
    "Curl femoral": ("hamstrings", ()),
    "Puente de glúteo": ("glutes", ("hamstrings",)),
    "Estabilidad de cadera": ("glutes", ()),
    "Swing": ("glutes", ("hamstrings",)),
    "Gemelos": ("calves", ()),
    "Core": ("core", ()), "Abdominales": ("core", ()), "Plancha": ("core", ()), "Sit-ups": ("core", ()),
    "Elevación de piernas": ("core", ()), "Leñador": ("core", ()), "Acarreos": ("core", ("back",)),
    "Halterofilia": ("fullbody", ()), "Cuerpo completo": ("fullbody", ()),
}
MUSCLE_LABEL = {"chest": "Pecho", "back": "Espalda", "shoulders": "Hombros", "biceps": "Bíceps", "triceps": "Tríceps",
                "quads": "Cuádriceps", "hamstrings": "Isquios", "glutes": "Glúteos", "calves": "Gemelos", "core": "Core",
                "fullbody": "Cuerpo completo"}
SKIP = {"Calentamiento", "Cardio", "Carrera"}


def e1rm(kg: float | None, reps: int | None) -> float | None:
    """1RM estimado con la fórmula de Epley. Con más de 12 repeticiones deja de ser fiable: no se estima."""
    if not kg or not reps or kg <= 0 or reps < 1 or reps > 12:
        return None
    return float(kg) if reps == 1 else round(kg * (1 + reps / 30), 1)


def gym_block(data: dict, weeks: int = 12) -> dict | None:
    sessions = [a for a in data.get("activities") or [] if a.get("type") == "strength_training"]
    if not sessions:
        return None
    today = date.today()
    mon = _monday(today)
    first = mon - timedelta(weeks=weeks - 1)
    wk: dict[str, dict] = {}
    for i in range(weeks):
        s = (first + timedelta(weeks=i)).isoformat()
        wk[s] = {"start": s, "sessions": 0, "sets": 0, "kg": 0, "muscles": {}}
    by_ex: dict[str, dict] = {}
    for a in sessions:
        d = a["start"][:10]
        sets = [x for x in (a.get("sets") or []) if x.get("ex") not in SKIP]
        ws = _monday(date.fromisoformat(d)).isoformat()
        w = wk.get(ws)
        if w is not None:
            w["sessions"] += 1
        for x in sets:
            reps, kg = x.get("reps") or 0, x.get("kg") or 0
            if w is not None:
                w["sets"] += 1
                w["kg"] += round(kg * reps)
                main, sec = MUSCLE_OF.get(x["ex"], (None, ()))
                if main:
                    w["muscles"][main] = w["muscles"].get(main, 0) + 1
                for m in sec:
                    w["muscles"][m] = w["muscles"].get(m, 0) + 0.5
            ex = by_ex.setdefault(x["ex"], {"ex": x["ex"], "muscle": MUSCLE_OF.get(x["ex"], (None,))[0], "sets": 0,
                                             "best": None, "maxKg": None, "maxReps": 0, "history": {}, "last": None})
            ex["sets"] += 1
            ex["maxReps"] = max(ex["maxReps"], reps)
            if kg and (ex["maxKg"] is None or kg > ex["maxKg"]["kg"]):
                ex["maxKg"] = {"kg": kg, "reps": reps, "d": d, "id": a["id"]}
            est = e1rm(kg, reps)
            if est and (ex["best"] is None or est > ex["best"]["e1rm"]):
                ex["best"] = {"e1rm": est, "kg": kg, "reps": reps, "d": d, "id": a["id"]}
            if est:
                ex["history"][d] = max(ex["history"].get(d, 0), est)
            if ex["last"] is None or d >= ex["last"]:
                ex["last"] = d
    records = []
    for ex in by_ex.values():
        hist = sorted(ex.pop("history").items())
        ex["trend"] = [{"d": d, "e1rm": v} for d, v in hist][-12:]
        ex["label"] = MUSCLE_LABEL.get(ex["muscle"] or "", "Otro")
        records.append(ex)
    records.sort(key=lambda r: (r["best"] is None, -(r["best"] or {}).get("e1rm", 0), -r["sets"]))
    wl = list(wk.values())
    for w in wl:
        w["muscles"] = {k: round(v, 1) for k, v in sorted(w["muscles"].items(), key=lambda kv: -kv[1])}
    recent = wl[-4:]
    avg = {}
    for w in recent:
        for k, v in w["muscles"].items():
            avg[k] = avg.get(k, 0) + v / len(recent)
    return {
        "weeks": wl, "records": records,
        "muscleAvg4w": [{"muscle": k, "label": MUSCLE_LABEL[k], "sets": round(v, 1)}
                        for k, v in sorted(avg.items(), key=lambda kv: -kv[1])],
        "muscles": [{"key": k, "label": v} for k, v in MUSCLE_LABEL.items()],
        "totals": {"sessions": len(sessions), "withSets": sum(1 for a in sessions if a.get("sets")),
                   "sets": sum(len(a.get("sets") or []) for a in sessions)},
    }


# ======================================================================== todo junto
def enrich(data: dict, settings: dict | None = None, wellness_block: dict | None = None) -> dict:
    """Añade a data.js los bloques paces, swim, gym, wellness, tu tiempo disponible y la previsión del tiempo
    (los puede recalcular la API sin pandas)."""
    if settings is None:
        from . import settings as S
        settings = S.load()
    if wellness_block is None:
        from . import wellness as W
        wellness_block = W.block()
    data["paces"] = paces_block(data, settings)
    data["swim"] = swim_block(data, settings)
    data["gym"] = gym_block(data)
    data["wellness"] = wellness_block
    from . import settings as S2, weather
    data["availability"] = S2.availability(settings) if S2.has_availability(settings) else None
    data["weather"] = weather.block()
    return data
