"""Plan de comidas y compra semanal: el coach propone un menú de 7 días según tu plan de entreno y tu objetivo de
Comida, y se convierte en una lista de la compra con productos reales de Mercadona (precio, envases y total).

  1. IA (una llamada por semana, Sonnet 5.5, salida estructurada): menú de 7 días × las comidas elegidas, raciones por
     persona y la lista de ingredientes GENÉRICOS con cantidades ("pechuga de pollo 600 g", "plátano 7 ud").
  2. Sin IA (match): cada ingrediente se busca en el catálogo (ingredients.py dice dónde y cómo) y se elige el producto
     que cubre la cantidad al menor coste razonable; se calculan los envases (multipacks, piezas, a peso), el precio y
     el total. Se puede cambiar de producto, quitar líneas y marcarlas. Resumen de nutrición con la del catálogo.

Python puro (Lambda de la API). Estado en data/shopping.json:
  {"prefs": {...}, "plan": {...} | null, "list": {"checked": [], "removed": [], "swaps": {}, "need": []}, "job": {...}}
Mercadona dio permiso (03-11-2026) para usar nombre, formato, precio y nutrición SOLO aquí: la web cita la fuente y
enlaza cada ficha. Nunca se compara con otras cadenas.
"""

from __future__ import annotations

import json
import logging
import math
import re
import secrets
import urllib.parse
from datetime import date, timedelta
from typing import Literal

import anthropic
from pydantic import BaseModel, Field, ValidationError

from . import DATA_DIR, ai, catalog as C, food
from .ingredients import BY_KEY, ITEMS, Ingredient

log = logging.getLogger(__name__)

PATH = DATA_DIR / "shopping.json"
MODEL = "claude-sonnet-5-5"
MEALS = ("desayuno", "comida", "cena", "snacks")
MEAL_LABEL = {"desayuno": "Desayuno", "comida": "Comida", "cena": "Cena", "snacks": "Snacks"}
MEAL_SHARE = {"desayuno": 0.22, "comida": 0.35, "cena": 0.30, "snacks": 0.13}  # parte de la energía del día
DEFAULT_MEALS = ["desayuno", "comida", "cena"]
DIETS = ("vegetariano", "sinLactosa", "sinGluten", "noPescado")
DIET_LABEL = {"vegetariano": "vegetariano", "sinLactosa": "sin lactosa", "sinGluten": "sin gluten", "noPescado": "sin pescado ni marisco"}
DAY_NAMES = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
HARD = {"long": 0.10, "race": 0.12, "tempo": 0.05, "intervals": 0.05}  # más energía (sobre todo hidratos) esos días
OWN_BRANDS = ("hacendado", "deliplus", "bosque verde", "compy")
SEARCH_URL = "https://tienda.mercadona.es/search-results?query="
ALLERGY_NOTE = "Revisa las etiquetas si tienes alergias o intolerancias: los productos pueden cambiar de receta."
MAX_ITEMS = 60


class ShoppingError(RuntimeError):
    """El menú no se ha podido generar (el mensaje se enseña tal cual)."""


# ======================================================================== estado y preferencias
def load() -> dict:
    try:
        st = json.loads(PATH.read_text())
        return st if isinstance(st, dict) else {}
    except (OSError, ValueError):
        return {}


def save(st: dict) -> None:
    PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, ensure_ascii=False, separators=(",", ":")))
    tmp.replace(PATH)


def prefs(st: dict | None = None) -> dict:
    p = ((load() if st is None else st).get("prefs") or {})
    meals = [m for m in MEALS if m in (p.get("meals") or DEFAULT_MEALS)] or list(DEFAULT_MEALS)
    diet = {k: bool((p.get("diet") or {}).get(k)) for k in DIETS}
    budget = p.get("budget")
    return {"enabled": bool(p.get("enabled")), "people": int(p.get("people") or 1), "meals": meals, "diet": diet,
            "allergies": str(p.get("allergies") or ""), "budget": float(budget) if budget else None,
            "cooking": p.get("cooking") if p.get("cooking") in ("rapido", "normal") else "normal"}


def set_prefs(payload: dict) -> dict:
    """{"enabled"?, "people"? 1-4, "meals"? [...], "diet"? {...}, "allergies"? str, "budget"? €|null, "cooking"?}.
    Desactivar no borra el menú ni la lista."""
    st = load()
    p = dict(st.get("prefs") or {})
    if "enabled" in payload:
        p["enabled"] = bool(payload["enabled"])
        if p["enabled"] and not p.get("enabledAt"):
            p["enabledAt"] = food._now()
    if "people" in payload:
        try:
            n = int(payload["people"])
        except (TypeError, ValueError):
            raise ValueError("Número de personas no válido.") from None
        if not 1 <= n <= 4:
            raise ValueError("De 1 a 4 personas.")
        p["people"] = n
    if "meals" in payload:
        meals = payload["meals"]
        if not isinstance(meals, list) or not meals or any(m not in MEALS for m in meals):
            raise ValueError("Elige al menos una comida: desayuno, comida, cena o snacks.")
        p["meals"] = [m for m in MEALS if m in meals]
    if "diet" in payload:
        d = payload["diet"] or {}
        if not isinstance(d, dict):
            raise ValueError("Preferencias no válidas.")
        p["diet"] = {k: bool(d.get(k)) for k in DIETS}
    if "allergies" in payload:
        p["allergies"] = " ".join(str(payload["allergies"] or "").split())[:160]
    if "budget" in payload:
        b = payload["budget"]
        if b in (None, "", 0):
            p.pop("budget", None)
        else:
            try:
                b = float(b)
            except (TypeError, ValueError):
                raise ValueError("Presupuesto no válido.") from None
            if not 10 <= b <= 600:
                raise ValueError("El presupuesto tiene que ir de 10 a 600 € a la semana.")
            p["budget"] = round(b)
    if "cooking" in payload:
        if payload["cooking"] not in ("rapido", "normal"):
            raise ValueError("Tiempo de cocina: rápido o normal.")
        p["cooking"] = payload["cooking"]
    st["prefs"] = p
    save(st)
    return st


# ======================================================================== contexto: entreno y objetivo
def week_start(today: date | None = None, mode: str | None = None) -> date:
    """'today' empieza hoy; 'monday' el lunes que viene (por defecto si ya es jueves o más tarde)."""
    today = today or date.today()
    nxt = today + timedelta(days=(7 - today.weekday()) % 7 or 7)
    if mode == "today":
        return today
    if mode == "monday":
        return nxt
    return nxt if today.weekday() >= 3 else today


def context(data: dict, coach_state: dict | None, food_st: dict | None, start: date, today: date | None = None) -> dict:
    """Lo que necesita la IA y el resumen: sesiones de esos 7 días, gasto de Garmin y objetivo (con los límites de Comida)."""
    today = today or date.today()
    fp = food.prefs(food_st or {})
    s = food.series(data or {}, [], 28, today)
    burned = s["burnedKcalAvg"]
    goal = food.target(fp["goal"], burned, s["bmrKcal"]) if fp["goal"] else None
    base = goal["targetKcal"] if goal else (round(burned / 10) * 10 if burned else None)
    floor = max(burned * (1 - food.MAX_DEFICIT), s["bmrKcal"] or 0) if burned else 0
    sessions = {}
    for w in ((coach_state or {}).get("plan") or {}).get("weeks") or []:
        for x in w.get("sessions") or []:
            sessions.setdefault(x.get("date"), []).append(x)
    days = []
    for i in range(7):
        d = start + timedelta(days=i)
        ss = [x for x in sessions.get(d.isoformat(), []) if x.get("type") != "rest"]
        bump = max([HARD.get(x.get("type"), 0) for x in ss] or [0])
        kcal = round(max(base * (1 + bump), floor) / 10) * 10 if base else None
        days.append({"date": d.isoformat(), "weekday": DAY_NAMES[d.weekday()],
                     "sessions": [{"type": x.get("type"), "title": x.get("title"), "km": x.get("distance_km"),
                                   "min": x.get("duration_min")} for x in ss],
                     "hard": bump > 0, "kcal": kcal})
    w = food.latest_weight(data or {})
    return {"days": days, "burnedKcalAvg": burned, "goal": goal, "goalMode": (fp["goal"] or {}).get("mode"),
            "weightKg": w["kg"] if w else None, "hideCalories": fp["hideCalories"],
            "proteinRefG": [round(food.PROTEIN_REF[0] * w["kg"]), round(food.PROTEIN_REF[1] * w["kg"])] if w else None}


# ======================================================================== IA (una llamada por semana)
class DishOut(BaseModel):
    meal: Literal["desayuno", "comida", "cena", "snacks"]
    dish: str = Field(description="Plato sencillo en castellano, máx. 70 caracteres, p. ej. 'Lentejas estofadas con verduras'")
    portion: str = Field(description="Ración por persona, corta, p. ej. '1 plato hondo (~350 g)' o '2 tostadas + 1 plátano'")
    note: str | None = Field(description="Solo si aporta: nota corta (máx. 60 caracteres), p. ej. 'Cocina doble: sirve para el jueves'")


class DayOut(BaseModel):
    date: str = Field(description="AAAA-MM-DD")
    focus: str | None = Field(description="Solo si hay entreno fuerte o algo especial: frase corta (máx. 70 caracteres), "
                                          "p. ej. 'Tirada larga: más hidratos en la comida de antes'")
    meals: list[DishOut]
    kcal_per_person: int = Field(description="Energía aproximada de las comidas planificadas de ese día, por persona")
    protein_g_per_person: int = Field(description="Proteína aproximada de las comidas planificadas de ese día, por persona")


class IngredientOut(BaseModel):
    name: str = Field(description="Nombre genérico, usando los de la lista que te paso siempre que se pueda")
    amount: float = Field(description="Cantidad TOTAL de la semana para todas las personas")
    unit: Literal["g", "ml", "ud"]


class WeekMenu(BaseModel):
    summary: str = Field(description="1-2 frases: cómo está planteado el menú y por qué, con el entreno de la semana")
    days: list[DayOut] = Field(description="Exactamente 7 días, en orden")
    ingredients: list[IngredientOut] = Field(description="Todo lo necesario para el menú, sumado por ingrediente")
    tips: list[str] = Field(description="2-4 consejos cortos de organización (máx. 110 caracteres), p. ej. cocinar doble")


SYSTEM = """Eres dietista-nutricionista deportiva y preparas el menú semanal de una persona que entrena (running), para una app en España.
Escribes en castellano de España, con tuteo y lenguaje neutro en cuanto al género (sin "listo/lista": "todo a punto", "te ayuda").

El menú:
- Cocina española y mediterránea, casera, sencilla y realista: legumbres, arroz, pasta, verdura de temporada, fruta, huevos,
  pescado, pollo, aceite de oliva, pan. Platos que se hacen de verdad entre semana. Si piden cocina rápida: 20-30 min como mucho.
- Aprovecha ingredientes entre días (cocinar doble, sobras planificadas) para tirar menos y gastar menos.
- Ajusta la energía de cada día a la referencia que te paso: más hidratos el día antes y el día de una tirada larga o una
  sesión de calidad, y hidratos con proteína después; los días de descanso, platos más ligeros sin pasar hambre.
- Proteína repartida en las comidas; al menos 2 raciones de pescado a la semana si se come pescado; legumbres 2-4 veces.
- Nada de dietas extremas, ayunos, batidos sustitutivos ni suplementos. Nunca por debajo de la referencia que te paso.
- Respeta SIEMPRE las exclusiones y alergias: si no come pescado, ni pescado ni marisco; vegetariano, ni carne ni pescado.
- Tono: neutro y sin juicios. Ningún alimento es bueno o malo, sin culpa, sin "compensar" ni "quemar". Solo propones.

Los ingredientes:
- Usa los nombres genéricos de la lista que te paso (exactos) siempre que se pueda; si hace falta otro, nombre genérico corto.
- Cantidades TOTALES de la semana para todas las personas: g para casi todo, ml para líquidos, ud para piezas (huevos,
  plátanos, fruta suelta, lechugas, aguacates). Cantidades en crudo y realistas (arroz 70-90 g por ración, pasta 80-100 g,
  legumbre cocida 150-200 g, pollo/pescado 125-175 g, aceite unos 10 g por ración).
- Suma bien: la cantidad de cada ingrediente tiene que cubrir TODAS las raciones de la semana en las que aparece
  (pan de cada tostada y de cada cena, huevos de cada plato, fruta de cada desayuno y postre), por todas las personas.
- Incluye el aceite, la sal y las especias que se usan (se marcan como despensa)."""


GOAL_TEXT = {"maintain": "mantener", "lose": "bajar peso poco a poco", "gain": "subir peso"}
MONTHS = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre")


def _prompt(p: dict, ctx: dict, start: date) -> str:
    diet = [DIET_LABEL[k] for k, v in p["diet"].items() if v]
    meals = ", ".join(MEAL_LABEL[m] for m in p["meals"])
    share = sum(MEAL_SHARE[m] for m in p["meals"])
    weight = (f"; peso {ctx['weightKg']:g} kg, proteína de referencia {ctx['proteinRefG'][0]}-{ctx['proteinRefG'][1]} g al día"
              if ctx.get("weightKg") else "")
    days = []
    for d in ctx["days"]:
        ses = "; ".join(f"{s['title'] or s['type']}" + (f" ({s['km']:g} km)" if s.get("km") else "")
                        + (f" ({s['min']} min)" if s.get("min") and not s.get("km") else "") for s in d["sessions"]) or "descanso"
        ref = f", referencia de energía del día entero ~{d['kcal']} kcal (las comidas planificadas, ~{round(d['kcal'] * share / 10) * 10})" \
            if d["kcal"] else ""
        days.append(f"- {d['date']} ({d['weekday']}): {ses}{ref}")
    lines = [
        f"Semana del {start.isoformat()} al {(start + timedelta(days=6)).isoformat()}.",
        f"Personas: {p['people']} (las referencias de energía son de la persona que entrena; para el resto, raciones normales de adulto).",
        f"Comidas a planificar cada día: {meals}.",
        f"Cocina: {'rápida (20-30 min como mucho)' if p['cooking'] == 'rapido' else 'normal'}.",
        f"Preferencias: {', '.join(diet) if diet else 'ninguna'}.",
        f"Alergias o cosas que no come (respétalas siempre): {p['allergies'] or 'ninguna indicada'}.",
        f"Presupuesto orientativo: {p['budget']:.0f} € a la semana en total (prioriza legumbres, huevos, pollo, pescado "
        "congelado, fruta y verdura de temporada si va justo)." if p["budget"] else "Presupuesto: sin límite, pero sin caprichos caros.",
        f"Objetivo de la persona: {GOAL_TEXT.get(ctx['goalMode'] or '', 'ninguno (comer para rendir)')}" + weight + ".",
        f"Estamos en {MONTHS[start.month - 1]}: usa producto de temporada.",
        "Entreno y energía de cada día:", *days,
        "Ingredientes genéricos disponibles (usa estos nombres):",
        ", ".join(i.key for i in ITEMS if _allowed(i, p)[0]),
    ]
    return "\n".join(lines)


def _client():
    key = ai._api_key()
    if not key:
        raise ShoppingError("No hay clave de IA configurada.")
    return anthropic.Anthropic(api_key=key, max_retries=1, timeout=300)


def generate_menu(p: dict, ctx: dict, start: date) -> tuple[WeekMenu, float, str]:
    """Una llamada a Claude con salida estructurada. El coste va al registro de gasto de IA (kind=compra)."""
    if ai.over_budget():
        raise ShoppingError(f"Has llegado al tope de IA de este mes ({ai.budget():.0f} $). El menú se podrá generar el día 1.")
    client = _client()
    model = ai.pick_model(MODEL)
    try:
        resp = client.beta.messages.parse(
            model=model, **(ai.FALLBACKS if model != ai.MODEL else {}), max_tokens=16000,
            output_config={"effort": "low"}, system=SYSTEM,
            messages=[{"role": "user", "content": _prompt(p, ctx, start)}], output_format=WeekMenu)
    except anthropic.APIConnectionError:
        raise ShoppingError("La IA ha tardado demasiado o no responde. Inténtalo de nuevo.") from None
    except anthropic.APIStatusError as e:
        raise ShoppingError(f"La IA no está disponible ahora ({e.status_code}). Inténtalo de nuevo.") from None
    except ValidationError:
        raise ShoppingError("La respuesta de la IA no tenía el formato esperado. Inténtalo de nuevo.") from None
    cost = ai._log_usage(resp, "compra", model)
    if resp.stop_reason == "refusal" or resp.parsed_output is None:
        raise ShoppingError("La IA no ha podido preparar el menú. Inténtalo de nuevo.")
    if resp.stop_reason == "max_tokens":
        raise ShoppingError("La respuesta de la IA salió incompleta. Inténtalo de nuevo.")
    return resp.parsed_output, cost, model


# ======================================================================== ingredientes: nombres, exclusiones
_ALIAS: dict[str, Ingredient] = {}
for _i in ITEMS:
    for _n in (_i.key, *_i.aliases):
        _ALIAS.setdefault(" ".join(C.tokens(_n)), _i)
STOP = {"de", "del", "la", "el", "los", "las", "con", "en", "y", "a", "al", "para", "fresco", "fresca", "natural", "entero", "entera"}
ALLERGY_TAGS = {
    "fruto seco": "nuts", "frutos seco": "nuts", "nuez": "nuts", "almendra": "nuts", "avellana": "nuts", "cacahuete": "nuts",
    "pistacho": "nuts", "anacardo": "nuts", "marisco": "shellfish", "crustaceo": "shellfish", "molusco": "shellfish",
    "gamba": "shellfish", "pescado": "fish", "huevo": "egg", "lactosa": "dairy", "leche": "dairy", "lacteo": "dairy",
    "gluten": "gluten", "trigo": "gluten", "celiac": "gluten", "soja": "soy", "carne": "meat",
}


def ingredient_for(name: str) -> Ingredient | None:
    t = " ".join(C.tokens(name))
    if t in _ALIAS:
        return _ALIAS[t]
    toks = [w for w in t.split() if w not in STOP]
    t2 = " ".join(toks)
    return _ALIAS.get(t2)


def _allergy_tags(text: str) -> set[str]:
    n = " ".join(C.tokens(text))
    return {tag for k, tag in ALLERGY_TAGS.items() if " ".join(C.tokens(k)) in n}


def _allowed(ing: Ingredient, p: dict) -> tuple[bool, str | None]:
    tags = set(ing.tags)
    d = p["diet"]
    if d.get("vegetariano") and tags & {"meat", "fish", "shellfish"}:
        return False, "vegetariano"
    if d.get("noPescado") and tags & {"fish", "shellfish"}:
        return False, "sin pescado"
    hit = tags & _allergy_tags(p.get("allergies") or "")
    if hit:
        return False, "alergias"
    words = set(C.tokens(p.get("allergies") or "")) - STOP
    if words and words & set(C.tokens(ing.key)):
        return False, "alergias"
    return True, None


def clean_ingredients(raw: list, p: dict) -> tuple[list[dict], list[str]]:
    """Une repetidos (mismo ingrediente y unidad), quita lo que choca con las exclusiones o alergias y avisa."""
    out: dict[tuple, dict] = {}
    warnings = []
    for r in raw[:MAX_ITEMS * 2]:
        name = " ".join(str(r.get("name") or "").split())[:60]
        unit = r.get("unit") if r.get("unit") in ("g", "ml", "ud") else "g"
        amount = food._num(r.get("amount"), 0, 50000, 1)
        if not name or not amount:
            continue
        ing = ingredient_for(name)
        if ing:
            ok, why = _allowed(ing, p)
            if not ok:
                warnings.append(f"He quitado «{name}» por tus preferencias ({why}).")
                continue
        else:
            words = set(C.tokens(name)) - STOP
            al = (set(C.tokens(p.get("allergies") or "")) - STOP)
            if al & words:
                warnings.append(f"He quitado «{name}» por tus alergias.")
                continue
        key = ing.key if ing else " ".join(C.tokens(name))
        k = (key, unit)
        if k in out:
            out[k]["amount"] = round(out[k]["amount"] + amount, 1)
            continue
        clash = any(x[0] == key for x in out)  # mismo ingrediente en otra unidad (p. ej. g y ud): otra línea
        out[k] = {"key": f"{key} ({unit})" if clash else key, "name": ing.key if ing else name, "amount": amount,
                  "unit": unit, "known": bool(ing)}
    return list(out.values())[:MAX_ITEMS], warnings


# ======================================================================== emparejar con productos (sin IA)
_IDX: dict = {}


def _index(cat: dict) -> list[dict]:
    """Nombres normalizados de los productos (una vez por catálogo)."""
    key = id(cat)
    if _IDX.get("key") != key:
        rows = []
        for p in cat.get("products") or []:
            n = C.norm(p.get("name"))
            rows.append({"p": p, "toks": set(C.tokens(p.get("name"))), "n": n, "w": re.split(r"[^a-z0-9ñ%]+", n), "c": C.norm(p.get("cat")),
                         "f": C.parse_format(p.get("fmt")), "own": any(b in C.norm(p.get("brand") or p.get("name")) for b in OWN_BRANDS)})
        _IDX.clear()
        _IDX.update({"key": key, "rows": rows, "cat": cat})
    return _IDX["rows"]


def _price(p: dict, f: dict | None) -> float | None:
    if p.get("price") is not None:
        return p["price"]
    if f and f.get("kind") in ("g", "ml") and p.get("perKgL"):
        return round(p["perKgL"] * f["size"] / 1000, 2)
    return None


def _is_piece(p: dict, f: dict | None) -> bool:
    return bool(f and f["kind"] in ("g", "ml") and p.get("approx") and (p.get("pack") or "").lower() in ("pieza", "1/2 pieza"))


def cover(need: float, unit: str, ing: Ingredient | None, row: dict) -> dict | None:
    """Envases necesarios para cubrir la cantidad: multipacks ("6 x 1 l"), piezas sueltas, unidades ("12 ud") y a peso."""
    p, f = row["p"], row["f"]
    gpu = ing.gpu if ing else None
    if not f:
        return None
    mass = unit in ("g", "ml")
    if f["kind"] == "weight":
        per = p.get("perKgL")
        g = need if mass else (need * gpu if gpu else None)
        if not per or not g:
            return None
        qty = max(g, f.get("min") or 0)
        return {"packs": None, "qty": round(qty), "qtyUnit": "g", "cost": round(per * qty / 1000, 2), "leftover": 0.0,
                "leftoverUnit": "g", "byWeight": True, "needG": g}
    price = _price(p, f)
    if price is None:
        return None
    size = f["size"]
    if f["kind"] in ("g", "ml"):
        if _is_piece(p, f) and not mass:  # fruta o verdura suelta: una pieza por unidad
            packs = max(1, math.ceil(need - 0.01))
            return {"packs": packs, "cost": round(packs * price, 2), "leftover": 0.0, "leftoverUnit": "g", "approx": True,
                    "needG": need * size}
        need_m = need if mass else (need * gpu if gpu else None)
        if not need_m:
            return None
        packs = max(1, math.ceil(need_m / size - 0.1))
        got = packs * size
    else:  # unidades
        units = need if not mass else (need / gpu if gpu else None)
        if not units:
            return None
        packs = max(1, math.ceil(units / size - 0.05))
        got, need_m = packs * size, units
    return {"packs": packs, "cost": round(packs * price, 2), "leftover": round(max(0.0, got - need_m), 1),
            "leftoverUnit": "ud" if f["kind"] == "ud" else ("ml" if f["kind"] == "ml" else "g"), "approx": bool(p.get("approx")),
            "needG": need_m if f["kind"] != "ud" else (need_m * gpu if gpu else None)}


def _has(row: dict, x: str) -> bool:
    """¿El nombre lleva esta palabra (o empieza así: 'rebozad' → rebozado/rebozada) o esta frase? Nunca a mitad de
    palabra: 'dado' no casa con 'Hacendado' ni 'pina' con 'espinacas'."""
    if " " in x:
        return f" {x}" in f" {row['n']}"
    return any(w.startswith(x) for w in row["w"])


def _candidates(ing: Ingredient, rows: list[dict], require: str | None = None) -> list[tuple[int, dict]]:
    cats = tuple(C.norm(c) for c in ing.cats)
    inc = [set(C.tokens(x)) for x in ing.inc]
    exc = tuple(C.norm(x) for x in ing.exc)
    req = C.norm(require) if require else None
    out = []
    for r in rows:
        if cats and not r["c"].startswith(cats):
            continue
        if exc and any(_has(r, x) for x in exc if not (req and x in req)):
            continue
        if req and not _has(r, req):
            continue
        idx = next((i for i, t in enumerate(inc) if t <= r["toks"]), None)
        if idx is None:
            continue
        out.append((idx, r))
    return out


def _fuzzy(name: str, rows: list[dict], cats: tuple[str, ...] = ()) -> list[tuple[int, dict]]:
    """Ingrediente fuera de la tabla (o sin producto en sus pasillos): todas sus palabras en el nombre del producto."""
    words = [w for w in C.tokens(name) if w not in STOP and len(w) > 2]
    if not words:
        return []
    cats = tuple(C.norm(c) for c in cats)
    prep = tuple(x for x in ("preparad", "rebozad", "empanad", "salsa", "chocolate", "golosina", "gelatina", "helado", "sabor")
                 if x not in C.norm(name))
    return [(0, r) for r in rows if set(words) <= r["toks"] and not any(_has(r, x) for x in prep)
            and (not cats or r["c"].startswith(cats))]


def _score(c: dict, idx: int, row: dict, ing: Ingredient | None, cheap: bool) -> float:
    """Menor es mejor: lo que pagas, menos parte de lo que sobra (más si dura semanas), y en modo normal un poco de
    preferencia por el nombre que mejor encaja y por la marca propia."""
    p = row["p"]
    keeps = bool(ing and ing.keeps)
    left_val = 0.0
    if c.get("leftover") and c.get("packs") and row["f"]["size"]:
        # Lo que sobra cuenta como ahorro solo hasta otra semana como esta (un saco de 5 kg para 1,5 kg no sale "gratis")
        need = c["packs"] * row["f"]["size"] - c["leftover"]
        left_val = min(c["leftover"], max(need, 0)) / row["f"]["size"] * _price(p, row["f"])
    s = c["cost"] - left_val * (0.8 if keeps else 0.25) + 0.04 * (c.get("packs") or 1)
    if not cheap:
        s *= 1 + 0.15 * idx + (0 if row["own"] else 0.04)
    return s


def _product_out(p: dict) -> dict:
    unit = (p.get("unitPriceUnit") or "").lower()
    per = p.get("perKgL")
    return {"id": p["id"], "name": p["name"], "brand": p.get("brand"), "fmt": p.get("fmt"), "pack": p.get("pack"),
            "price": p.get("price"), "perKgL": per, "perUnit": "kg" if unit in ("kg", "100 g") else ("l" if unit in ("l", "100 ml") else None),
            "unitPrice": p.get("unitPrice"), "unitPriceUnit": p.get("unitPriceUnit"), "url": p.get("url"),
            "aisle": C.top(p.get("cat"))}


def match(item: dict, cat: dict | None, p: dict, cheap: bool = False, swap: str | None = None) -> dict:
    """Una línea de la lista: el producto elegido (o el que has cambiado tú), envases, coste y alternativas."""
    ing = BY_KEY.get(item["name"]) or ingredient_for(item["name"])
    out = {"key": item["key"], "name": item["name"], "amount": item["amount"], "unit": item["unit"],
           "aisle": ing.aisle if ing else "Otros", "pantry": bool(ing and ing.pantry), "product": None, "packs": None,
           "cost": None, "alternatives": [], "warning": None,
           "searchUrl": SEARCH_URL + urllib.parse.quote(item["name"])}
    rows = _index(cat) if cat else []
    if not rows:
        return out
    cands: list[tuple[int, dict]] = []
    if ing:
        tags = set(ing.tags)
        if p["diet"].get("sinLactosa") and "dairy" in tags:
            cands = _candidates(ing, rows, "sin lactosa")
            if not cands:
                out["warning"] = "No encuentro versión sin lactosa: revisa la etiqueta."
        elif p["diet"].get("sinGluten") and "gluten" in tags:
            cands = _candidates(ing, rows, "sin gluten")
            if not cands:
                out["warning"] = "No encuentro versión sin gluten: búscala o cámbiala."
                return out
        if not cands:
            cands = _candidates(ing, rows)
    if not cands:
        cands = _fuzzy(item["name"], rows, ing.cats if ing else ())
        out["matchedBy"] = "texto"
    scored = []
    for idx, r in cands:
        c = cover(item["amount"], item["unit"], ing, r)
        if c:
            scored.append((_score(c, idx, r, ing, cheap), c, r))
    if not scored:
        return out
    scored.sort(key=lambda x: (x[0], x[2]["p"]["name"]))
    pick = scored[0]
    if swap:
        pick = next((x for x in scored if x[2]["p"]["id"] == swap), pick)
        out["swapped"] = pick[2]["p"]["id"] == swap
    _, c, r = pick
    bought = (c.get("packs") or 0) * (r["f"].get("size") or 0)
    used = c["cost"] * (1 - (c.get("leftover") or 0) / bought) if bought else c["cost"]
    out.update({"product": _product_out(r["p"]), "packs": c.get("packs"), "cost": c["cost"], "usedCost": round(used, 2),
                "byWeight": bool(c.get("byWeight")),
                "qty": c.get("qty"), "leftover": c.get("leftover") or 0, "leftoverUnit": c.get("leftoverUnit"),
                "approx": bool(c.get("approx")), "aisle": C.top(r["p"].get("cat")) or out["aisle"],
                "_nut": _nutrition(r["p"], c.get("needG"))})
    seen = {r["p"]["id"]}
    for s, c2, r2 in scored[1:]:
        if r2["p"]["id"] in seen:
            continue
        seen.add(r2["p"]["id"])
        out["alternatives"].append({**_product_out(r2["p"]), "packs": c2.get("packs"), "cost": c2["cost"],
                                    "byWeight": bool(c2.get("byWeight")), "qty": c2.get("qty")})
        if len(out["alternatives"]) >= 5:
            break
    return out


def _nutrition(p: dict, grams: float | None) -> dict | None:
    nut = p.get("nut")
    if not nut or not grams or str(p.get("nutFlag") or "").startswith("dudoso") or nut.get("kcal") is None:
        return None
    f = grams / 100
    return {"kcal": nut["kcal"] * f, "protein": (nut.get("protein") or 0) * f, "carbs": (nut.get("carbs") or 0) * f,
            "fat": (nut.get("fat") or 0) * f, "grams": grams}


def _merge_same_product(lines: list[dict], removed: set, cat: dict | None, p: dict, cheap: bool) -> list[dict]:
    """Dos ingredientes que acaban en el mismo producto (merluza y pescado blanco) van en una sola línea con la
    cantidad sumada: así no se compran dos envases si con uno basta."""
    first: dict[str, int] = {}
    out: list[dict] = []
    for ln in lines:
        pr = ln.get("product")
        k = pr and not ln.get("byWeight") and ln["key"] not in removed and f"{pr['id']}|{ln['unit']}"
        if k and k in first:
            base = out[first[k]]
            item = {"key": base["key"], "name": base["name"], "amount": round(base["amount"] + ln["amount"], 1), "unit": base["unit"]}
            merged = match(item, cat, p, cheap, pr["id"])
            merged["swapped"] = base.get("swapped", False)
            merged["also"] = [*(base.get("also") or []), {"key": ln["key"], "name": ln["name"], "amount": ln["amount"]}]
            out[first[k]] = merged
            continue
        if k:
            first[k] = len(out)
        out.append(ln)
    return out


def build_list(plan: dict | None, lst: dict | None, cat: dict | None, p: dict) -> dict:
    """La lista por pasillos con totales. Si pasa del presupuesto, se repite eligiendo siempre lo más barato."""
    lst = lst or {}
    items = (plan or {}).get("ingredients") or []
    swaps, removed, checked = lst.get("swaps") or {}, set(lst.get("removed") or []), set(lst.get("checked") or [])
    need = set(lst.get("need") or [])

    def run(cheap: bool):
        lines = _merge_same_product([match(it, cat, p, cheap, swaps.get(it["key"])) for it in items], removed, cat, p, cheap)
        for ln in lines:
            ln["removed"] = ln["key"] in removed
            ln["checked"] = ln["key"] in checked
            ln["skip"] = ln["pantry"] and ln["key"] not in need  # despensa: no cuenta salvo que digas que lo necesitas
        total = round(sum(ln["cost"] or 0 for ln in lines if not ln["removed"] and not ln["skip"]), 2)
        return lines, total
    lines, total = run(False)
    mode = "normal"
    budget = p.get("budget")
    if budget and total > budget:
        cheap_lines, cheap_total = run(True)
        if cheap_total < total:
            lines, total, mode = cheap_lines, cheap_total, "ahorro"
    active = [ln for ln in lines if not ln["removed"] and not ln["skip"]]
    groups: dict[str, list] = {}
    for ln in sorted(lines, key=lambda x: (x["pantry"], x["aisle"], x["name"])):
        groups.setdefault("Despensa (seguramente ya lo tienes)" if ln["pantry"] else ln["aisle"], []).append(ln)
    nut = [ln.pop("_nut", None) for ln in lines]
    over = bool(budget and total > budget)
    top3 = sorted(active, key=lambda x: -(x["cost"] or 0))[:3] if over else []
    return {
        "groups": [{"aisle": k, "items": v} for k, v in groups.items()],
        "total": total, "items": len(active), "unmatched": sum(1 for ln in active if not ln["product"]),
        # Lo que se gasta esta semana de verdad (la parte de cada envase que usa el menú); el resto dura para otras
        "usedTotal": round(sum(ln.get("usedCost") or 0 for ln in active), 2),
        "checkedTotal": round(sum(ln["cost"] or 0 for ln in active if ln["checked"]), 2),
        "budget": {"target": budget, "over": over, "mode": mode,
                   "biggest": [{"name": x["name"], "cost": x["cost"]} for x in top3]} if budget else None,
        "_nut": nut,
    }


def nutrition_summary(plan: dict, nut: list, people: int, ctx: dict | None, meals: list[str]) -> dict | None:
    """Energía y proteína por persona y día de lo planificado, con la nutrición del catálogo (y la cobertura)."""
    if not plan:
        return None
    known = [n for n in nut if n]
    days = 7 * max(1, people)
    out = {"kcalDay": round(sum(n["kcal"] for n in known) / days) if known else None,
           "proteinDay": round(sum(n["protein"] for n in known) / days) if known else None,
           "carbsDay": round(sum(n["carbs"] for n in known) / days) if known else None,
           "fatDay": round(sum(n["fat"] for n in known) / days) if known else None,
           "coverage": round(len(known) / len(nut), 2) if nut else 0, "linesWithData": len(known), "lines": len(nut),
           "aiKcalDay": None, "aiProteinDay": None}
    ds = plan.get("days") or []
    if ds:
        out["aiKcalDay"] = round(sum(d.get("kcal_per_person") or 0 for d in ds) / len(ds))
        out["aiProteinDay"] = round(sum(d.get("protein_g_per_person") or 0 for d in ds) / len(ds))
    share = sum(MEAL_SHARE[m] for m in meals)
    if ctx:
        ks = [d["kcal"] for d in ctx.get("days") or [] if d.get("kcal")]
        out["targetKcalDay"] = round(sum(ks) / len(ks)) if ks else None
        out["targetMealsKcalDay"] = round(out["targetKcalDay"] * share / 10) * 10 if out["targetKcalDay"] else None
        out["proteinRefG"] = ctx.get("proteinRefG")
    out["mealsShare"] = round(share, 2)
    return out


# ======================================================================== el menú de la semana
def new_plan(menu: WeekMenu, cost: float, model: str, p: dict, ctx: dict, start: date) -> dict:
    items, warnings = clean_ingredients([i.model_dump() for i in menu.ingredients], p)
    want = {(start + timedelta(days=i)).isoformat() for i in range(7)}
    days = [d.model_dump() for d in menu.days if d.date in want] or [d.model_dump() for d in menu.days[:7]]
    for d in days:
        d["meals"] = [m for m in d["meals"] if m["meal"] in p["meals"]] or d["meals"]
        d["weekday"] = DAY_NAMES[date.fromisoformat(d["date"]).weekday()] if re.fullmatch(r"\d{4}-\d{2}-\d{2}", d["date"]) else ""
        hard = next((x for x in ctx["days"] if x["date"] == d["date"]), None)
        d["sessions"] = (hard or {}).get("sessions") or []
    return {"id": secrets.token_hex(5), "start": start.isoformat(), "end": (start + timedelta(days=6)).isoformat(),
            "generatedAt": food._now(), "model": model, "cost": round(cost, 5), "summary": menu.summary[:400],
            "days": days, "ingredients": items, "tips": [t[:140] for t in menu.tips[:4]], "warnings": warnings,
            "people": p["people"], "meals": p["meals"], "context": ctx}


def generate(data: dict, coach_state: dict | None, food_st: dict | None, mode: str | None = None,
             today: date | None = None) -> dict:
    """Genera el menú de la semana (una llamada a la IA) y empieza una lista nueva. Guarda en shopping.json."""
    st = load()
    p = prefs(st)
    start = week_start(today, mode)
    ctx = context(data, coach_state, food_st, start, today)
    menu, cost, model = generate_menu(p, ctx, start)
    plan = new_plan(menu, cost, model, p, ctx, start)
    st = load()  # relee: no pisa un cambio de ajustes guardado mientras tanto
    st["plan"] = plan
    st["list"] = {"checked": [], "removed": [], "swaps": {}, "need": []}
    save(st)
    return st


def update_item(payload: dict) -> dict:
    """Marcar, quitar o volver a poner una línea, cambiar de producto o decir que necesitas algo de la despensa."""
    st = load()
    plan = st.get("plan")
    if not plan:
        raise LookupError("No hay lista esta semana.")
    if payload.get("action") == "uncheck-all":
        lst = dict(st.get("list") or {})
        lst["checked"] = []
        st["list"] = lst
        save(st)
        return st
    key = str(payload.get("key") or "")
    if key not in {i["key"] for i in plan.get("ingredients") or []}:
        raise LookupError("Ese producto ya no está en la lista.")
    lst = {k: list(v) if isinstance(v, list) else dict(v) for k, v in (st.get("list") or {}).items()}
    for k in ("checked", "removed", "need"):
        lst.setdefault(k, [])
    lst.setdefault("swaps", {})
    for flag, name in (("checked", "checked"), ("removed", "removed"), ("need", "need")):
        if flag in payload:
            s = set(lst[name])
            (s.add if payload[flag] else s.discard)(key)
            lst[name] = sorted(s)
    if "productId" in payload:
        pid = payload["productId"]
        if pid:
            lst["swaps"][key] = str(pid)[:20]
        else:
            lst["swaps"].pop(key, None)
    st["list"] = lst
    save(st)
    return st


def delete_plan() -> dict:
    st = load()
    st.pop("plan", None)
    st["list"] = {"checked": [], "removed": [], "swaps": {}, "need": []}
    save(st)
    return st


def _strip_kcal(obj):
    if isinstance(obj, dict):
        return {k: _strip_kcal(v) for k, v in obj.items() if "kcal" not in k.lower()}
    if isinstance(obj, list):
        return [_strip_kcal(v) for v in obj]
    return obj


def view(cat: dict | None, st: dict | None = None, food_st: dict | None = None) -> dict:
    """Todo lo que necesita la página: ajustes, menú, lista por pasillos, total, nutrición y de dónde salen los datos."""
    st = load() if st is None else st
    p = prefs(st)
    hide = food.prefs(food_st or {})["hideCalories"]
    meta = (cat or {}).get("meta") or {}
    out = {"prefs": p, "job": st.get("job"), "hideCalories": hide,
           "catalog": {"available": bool(cat), "date": meta.get("date"), "postcode": meta.get("postcode"),
                       "count": meta.get("count")},
           "attribution": {"products": C.ATTRIBUTION, "nutrition": C.NUTRITION_ATTRIBUTION, "allergy": ALLERGY_NOTE},
           "plan": None, "list": None, "nutrition": None, "budgetOver": ai.over_budget()}
    plan = st.get("plan")
    if plan:
        lst = build_list(plan, st.get("list"), cat, p)
        nut = lst.pop("_nut")
        out["nutrition"] = nutrition_summary(plan, nut, plan.get("people") or p["people"], plan.get("context"),
                                             plan.get("meals") or p["meals"])
        out["plan"] = {k: v for k, v in plan.items() if k != "context"}
        out["plan"]["goal"] = (plan.get("context") or {}).get("goal")
        out["list"] = lst
        out["text"] = as_text(out)
    return _strip_kcal(out) if hide else out


def as_text(v: dict) -> str:
    """La lista como texto para copiar o compartir (lo que no está quitado ni marcado como ya lo tienes)."""
    lst = v.get("list") or {}
    lines = [f"Lista de la compra · semana del {((v.get('plan') or {}).get('start') or '')}"]
    for g in lst.get("groups") or []:
        its = [i for i in g["items"] if not i["removed"] and not i["skip"]]
        if not its:
            continue
        lines.append(f"\n{g['aisle']}")
        for i in its:
            pr = i.get("product")
            if pr:
                q = f"{i['qty']} g" if i.get("byWeight") else f"{i['packs']} x"
                lines.append(f"- {q} {pr['name']} ({pr.get('fmt') or ''}) · {i['cost']:.2f} €")
            else:
                lines.append(f"- {i['name']} {i['amount']:g} {i['unit']}")
    lines.append(f"\nTotal aprox.: {lst.get('total', 0):.2f} €")
    cat = v.get("catalog") or {}
    lines.append(f"{C.ATTRIBUTION} · Precios del {cat.get('date')}, CP {cat.get('postcode')}")
    return "\n".join(lines)
