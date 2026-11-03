"""Comida: apuntas lo que comes (con una foto o escribiéndolo) y la IA estima alimentos, gramos, calorías y macros.
Después se compara con lo que gastas según Garmin (calorías totales del día = reposo + actividad).

Módulo opcional: está apagado hasta que la persona lo activa. Python puro (lo usa la Lambda de la API, sin pandas).

Privacidad: la foto NO se guarda. Llega en la petición, la IA la analiza en memoria y se descarta; solo se guardan
los datos (alimentos, gramos, kcal, macros, supuestos, nota, tipo de comida y hora).

Estado en data/food.json:
  {"prefs": {"enabled": bool, "hideCalories": bool, "goal": {"mode": "maintain"|"lose"|"gain", "pace": "suave"|"moderado"}},
   "entries": [{"id", "date", "time", "meal", "title", "note", "text", "fromPhoto", "status", "source", "items": [...],
                "confidence", "assumptions", "unclear", "fav", "createdAt", "updatedAt", "cost", "model"}]}
status: ok (estimado por la IA) · manual (lo has puesto tú, o sin IA) · error (la IA falló: puedes editarlo o reintentarlo).
"""

from __future__ import annotations

import base64
import json
import logging
import secrets
import statistics
from datetime import date, datetime, timedelta
from typing import Literal

import anthropic
from pydantic import BaseModel, Field, ValidationError

from . import DATA_DIR
from . import ai

log = logging.getLogger(__name__)

PATH = DATA_DIR / "food.json"
MODEL = "claude-sonnet-5-5"
MEALS = ("desayuno", "comida", "merienda", "cena", "picoteo")
MEAL_LABEL = {"desayuno": "Desayuno", "comida": "Comida", "merienda": "Merienda", "cena": "Cena", "picoteo": "Picoteo"}
NUTRIENTS = ("kcal", "protein", "carbs", "fat", "fiber", "sugar", "satFat", "sodium")
MACROS = ("protein", "carbs", "fat")
KCAL_PER_G = {"protein": 4, "carbs": 4, "fat": 9}
LIMITS = {"kcal": 5000, "protein": 500, "carbs": 800, "fat": 400, "fiber": 150, "sugar": 500, "satFat": 200, "sodium": 20000}
MAX_PHOTO_BYTES = 1_500_000      # foto ya comprimida en el navegador (~1024 px, JPEG 0,8: normalmente < 300 KB)
MAX_ITEMS = 30
MAX_ENTRIES = 4000
HISTORY_DAYS = 400               # se puede apuntar (o corregir) hasta ~1 año atrás
GOAL_FACTOR = {("maintain", "suave"): 1.0, ("maintain", "moderado"): 1.0, ("lose", "suave"): 0.90,
               ("lose", "moderado"): 0.85, ("gain", "suave"): 1.05, ("gain", "moderado"): 1.10}
MAX_DEFICIT = 0.20               # nunca más de un 20 % por debajo de lo que gastas...
MAX_SURPLUS = 0.15
PROTEIN_REF = (1.2, 1.6)         # g/kg: referencia habitual para quien entrena (ACSM/ISSN, rango bajo-medio)
FUEL_TYPES = {"long": "tirada larga", "tempo": "sesión de ritmo", "intervals": "series", "race": "carrera"}
ACCURACY_NOTE = "Estimación a partir de la foto o la descripción: puede variar un ±20-30 %."


class FoodAIError(RuntimeError):
    """La IA no ha podido estimar esta comida (el mensaje se enseña tal cual)."""


class BudgetExceeded(FoodAIError):
    pass


# ======================================================================== estado
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
    goal = p.get("goal") or {}
    mode = goal.get("mode") if goal.get("mode") in ("maintain", "lose", "gain") else None
    pace = goal.get("pace") if goal.get("pace") in ("suave", "moderado") else "suave"
    return {"enabled": bool(p.get("enabled")), "hideCalories": bool(p.get("hideCalories")),
            "goal": {"mode": mode, "pace": pace} if mode else None}


def set_prefs(payload: dict) -> dict:
    """{"enabled"?, "hideCalories"?, "goal"?: {"mode", "pace"} | null}. Activar o desactivar no borra lo apuntado."""
    st = load()
    p = dict(st.get("prefs") or {})
    if "enabled" in payload:
        p["enabled"] = bool(payload["enabled"])
        if p["enabled"] and not p.get("enabledAt"):
            p["enabledAt"] = _now()
    if "hideCalories" in payload:
        p["hideCalories"] = bool(payload["hideCalories"])
    if "goal" in payload:
        g = payload.get("goal")
        if not g or not g.get("mode"):
            p.pop("goal", None)
        else:
            if g.get("mode") not in ("maintain", "lose", "gain"):
                raise ValueError("Objetivo no válido.")
            pace = g.get("pace") or "suave"
            if pace not in ("suave", "moderado"):
                raise ValueError("Ritmo no válido: suave o moderado.")
            p["goal"] = {"mode": g["mode"], "pace": pace}
    st["prefs"] = p
    save(st)
    return st


# ======================================================================== utilidades
def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _num(v, lo: float = 0, hi: float | None = None, nd: int = 1) -> float | None:
    if v is None or v == "" or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    f = max(lo, f)
    if hi is not None:
        f = min(hi, f)
    return round(f) if nd == 0 else round(f, nd)


def _text(v, n: int) -> str:
    return " ".join(str(v or "").split())[:n]


def default_meal(hhmm: str) -> str:
    """Tipo de comida por la hora (horarios de España)."""
    try:
        h, m = (int(x) for x in hhmm.split(":")[:2])
    except (ValueError, AttributeError):
        return "picoteo"
    t = h * 60 + m
    if 5 * 60 <= t < 11 * 60:
        return "desayuno"
    if 13 * 60 <= t < 16 * 60 + 30:
        return "comida"
    if 16 * 60 + 30 <= t < 20 * 60:
        return "merienda"
    if 20 * 60 <= t < 24 * 60:
        return "cena"
    return "picoteo"


def _kcal_from_macros(it: dict) -> float:
    return round(sum((it.get(k) or 0) * KCAL_PER_G[k] for k in MACROS))


def clean_item(raw: dict) -> dict:
    """Un alimento con límites razonables. Si no trae kcal, se calculan con los macros (4/4/9)."""
    it = {"id": raw.get("id") if isinstance(raw.get("id"), str) and len(raw["id"]) <= 16 else secrets.token_hex(4),
          "name": _text(raw.get("name"), 80) or "Alimento", "portion": _text(raw.get("portion"), 60) or None,
          "grams": _num(raw.get("grams"), 0, 5000, 0)}
    for k in NUTRIENTS:
        it[k] = _num(raw.get(k), 0, LIMITS[k], 0 if k in ("kcal", "sodium") else 1)
    for k in ("protein", "carbs", "fat", "fiber"):
        it[k] = it[k] or 0.0
    if it["kcal"] is None:
        it["kcal"] = _kcal_from_macros(it)
    return {k: v for k, v in it.items() if v is not None}


def merge_items(old_items: list[dict], new_items: list) -> list[dict]:
    """Aplica la edición de la web. Si cambian los gramos de un alimento, sus kcal y nutrientes se recalculan en
    proporción, salvo los que se hayan cambiado a mano. Si cambias un macro a mano y no las kcal, las kcal se
    ajustan con la diferencia (4/4/9). Los alimentos que no vienen se quitan; los que no tienen id son nuevos."""
    if not isinstance(new_items, list):
        raise ValueError("Lista de alimentos no válida.")
    if len(new_items) > MAX_ITEMS:
        raise ValueError(f"Como mucho {MAX_ITEMS} alimentos por comida.")
    by_id = {it.get("id"): it for it in old_items}
    out = []
    for raw in new_items:
        if not isinstance(raw, dict):
            raise ValueError("Alimento no válido.")
        old = by_id.get(raw.get("id")) if raw.get("id") else None
        if not old:
            out.append(clean_item({**raw, "id": None}))
            continue
        item = dict(old)
        if "name" in raw:
            item["name"] = _text(raw["name"], 80) or old.get("name") or "Alimento"
        if "portion" in raw:
            item["portion"] = _text(raw["portion"], 60) or None
        g_old, g_new = old.get("grams"), _num(raw.get("grams"), 0, 5000, 0)
        ratio = g_new / g_old if (g_old and g_new is not None and g_new != g_old) else None
        changed = {k for k in NUTRIENTS if k in raw and raw[k] is not None
                   and _num(raw[k], 0, LIMITS[k], 0 if k in ("kcal", "sodium") else 1) != old.get(k)}
        for k in NUTRIENTS:
            if k in changed:
                item[k] = _num(raw[k], 0, LIMITS[k], 0 if k in ("kcal", "sodium") else 1)
            elif ratio is not None and old.get(k) is not None:
                item[k] = _num(old[k] * ratio, 0, LIMITS[k], 0 if k in ("kcal", "sodium") else 1)
        if "kcal" not in changed and changed & set(MACROS):
            delta = sum(((item.get(k) or 0) - ((old.get(k) or 0) * (ratio or 1))) * KCAL_PER_G[k] for k in MACROS if k in changed)
            item["kcal"] = _num((item.get("kcal") or 0) + delta, 0, LIMITS["kcal"], 0)
        if g_new is not None:
            item["grams"] = g_new
        out.append({k: v for k, v in item.items() if v is not None})
    return out


def scale_items(items: list[dict], factor: float) -> list[dict]:
    """"Comí la mitad" (0,5) o "repetí" (2): escala gramos y nutrientes de toda la comida."""
    out = []
    for it in items:
        new = dict(it)
        for k in ("grams", *NUTRIENTS):
            if it.get(k) is not None:
                hi = 5000 if k == "grams" else LIMITS[k]
                new[k] = _num(it[k] * factor, 0, hi, 0 if k in ("grams", "kcal", "sodium") else 1)
        out.append(new)
    return out


def totals(items: list[dict]) -> dict:
    t = {k: 0.0 for k in ("kcal", "protein", "carbs", "fat", "fiber")}
    extra = {k: None for k in ("sugar", "satFat", "sodium")}
    for it in items:
        for k in t:
            t[k] += it.get(k) or 0
        for k in extra:
            if it.get(k) is not None:
                extra[k] = (extra[k] or 0) + it[k]
    out = {k: (round(v) if k == "kcal" else round(v, 1)) for k, v in t.items()}
    out.update({k: (round(v) if k == "sodium" else round(v, 1)) for k, v in extra.items() if v is not None})
    return out


def _date_time(payload: dict, today: date, now_hm: str) -> tuple[str, str]:
    d = payload.get("date") or today.isoformat()
    try:
        dd = date.fromisoformat(str(d))
    except ValueError:
        raise ValueError("Fecha no válida.") from None
    if dd > today:
        raise ValueError("La fecha no puede ser futura.")
    if dd < today - timedelta(days=HISTORY_DAYS):
        raise ValueError("Solo puedes apuntar comidas del último año.")
    t = str(payload.get("time") or now_hm)
    try:
        h, m = (int(x) for x in t.split(":")[:2])
        assert 0 <= h < 24 and 0 <= m < 60
    except (ValueError, AssertionError):
        raise ValueError("Hora no válida.") from None
    return dd.isoformat(), f"{h:02d}:{m:02d}"


# ======================================================================== entradas
def new_entry(payload: dict, today: date | None = None) -> dict:
    """Crea (sin guardar) una comida nueva a partir de lo que manda la web."""
    today = today or date.today()
    d, t = _date_time(payload, today, datetime.now().strftime("%H:%M"))
    meal = payload.get("meal") or default_meal(t)
    if meal not in MEALS:
        raise ValueError("Tipo de comida no válido.")
    items = [clean_item({**it, "id": None}) for it in (payload.get("items") or [])[:MAX_ITEMS] if isinstance(it, dict)]
    now = _now()
    return {"id": secrets.token_hex(6), "date": d, "time": t, "meal": meal,
            "title": _text(payload.get("title"), 60) or (items[0]["name"] if len(items) == 1 else ""),
            "note": _text(payload.get("note"), 300), "text": _text(payload.get("text"), 500),
            "fromPhoto": False, "status": "manual", "source": "manual", "items": items,
            "fav": False, "createdAt": now, "updatedAt": now}


def entries(st: dict | None = None) -> list[dict]:
    return list((load() if st is None else st).get("entries") or [])


def find(entry_id: str, st: dict | None = None) -> dict | None:
    return next((e for e in entries(st) if e.get("id") == entry_id), None)


def upsert(entry: dict) -> dict:
    """Guarda la comida (nueva o la misma id). Lee el archivo justo antes: no pisa otra comida guardada mientras tanto."""
    st = load()
    es = [e for e in entries(st) if e.get("id") != entry["id"]] + [entry]
    es.sort(key=lambda e: (e["date"], e["time"], e.get("createdAt", "")))
    st["entries"] = es[-MAX_ENTRIES:]
    save(st)
    return entry


def update_entry(entry_id: str, payload: dict, today: date | None = None) -> dict:
    """Edita una comida: fecha, hora, tipo, nota, título, favorito, alimentos ("items") o toda la ración ("scale")."""
    today = today or date.today()
    e = find(entry_id)
    if not e:
        raise LookupError("Esa comida ya no existe.")
    e = dict(e)
    if "date" in payload or "time" in payload:
        e["date"], e["time"] = _date_time({"date": payload.get("date", e["date"]), "time": payload.get("time", e["time"])},
                                          today, e["time"])
    if "meal" in payload:
        if payload["meal"] not in MEALS:
            raise ValueError("Tipo de comida no válido.")
        e["meal"] = payload["meal"]
    for k, n in (("note", 300), ("title", 60)):
        if k in payload:
            e[k] = _text(payload[k], n)
    if "fav" in payload:
        e["fav"] = bool(payload["fav"])
    if "items" in payload:
        e["items"] = merge_items(e.get("items") or [], payload["items"])
        if e.get("source") == "ai":
            e["edited"] = True
    if payload.get("scale") is not None:
        f = _num(payload["scale"], 0, 10, 3)
        if not f or not 0.1 <= f <= 5:
            raise ValueError("La ración tiene que ir de 0,1 a 5 veces.")
        e["items"] = scale_items(e.get("items") or [], f)
    e["updatedAt"] = _now()
    return upsert(e)


def delete_entry(entry_id: str) -> bool:
    st = load()
    es = entries(st)
    left = [e for e in es if e.get("id") != entry_id]
    if len(left) == len(es):
        return False
    st["entries"] = left
    save(st)
    return True


def repeat_entry(entry_id: str, payload: dict, today: date | None = None) -> dict:
    """Repetir una comida anterior (favorita o reciente) sin volver a llamar a la IA."""
    src = find(entry_id)
    if not src:
        raise LookupError("Esa comida ya no existe.")
    e = new_entry({"date": payload.get("date"), "time": payload.get("time"),
                   "meal": payload.get("meal") or src.get("meal")}, today)
    e.update({"title": src.get("title") or "", "note": src.get("note") or "", "text": src.get("text") or "",
              "items": [{**it, "id": secrets.token_hex(4)} for it in src.get("items") or []],
              "source": "repeat", "status": "ok" if src.get("status") == "ok" else "manual", "repeatOf": entry_id,
              "confidence": src.get("confidence"), "assumptions": src.get("assumptions") or []})
    return upsert(e)


def favorites(st: dict | None = None, limit: int = 12) -> list[dict]:
    """Favoritas primero y después las más repetidas/recientes (una por título), para repetir con un toque."""
    es = [e for e in entries(st) if e.get("items")]
    seen, out = set(), []
    for e in sorted(es, key=lambda e: (not e.get("fav"), -_ts(e))):
        key = (e.get("title") or ", ".join(i["name"] for i in e["items"][:3])).lower()
        if key in seen:
            continue
        seen.add(key)
        out.append({"id": e["id"], "title": e.get("title") or ", ".join(i["name"] for i in e["items"][:3]),
                    "meal": e.get("meal"), "fav": bool(e.get("fav")), "totals": totals(e["items"]), "date": e["date"]})
        if len(out) >= limit:
            break
    return out


def _ts(e: dict) -> float:
    try:
        return datetime.fromisoformat(f"{e['date']}T{e['time']}").timestamp()
    except (KeyError, ValueError):
        return 0.0


# ======================================================================== IA (una llamada por comida)
class FoodItemOut(BaseModel):
    name: str = Field(description="Nombre corto del alimento en castellano, p. ej. 'Tortilla de patatas' o 'Aceite de oliva'")
    portion: str = Field(description="Ración en palabras, p. ej. '1 porción mediana', '2 rebanadas', '1 cucharada'")
    grams: float = Field(description="Peso estimado en gramos (ml si es bebida)")
    kcal: float
    protein_g: float
    carbs_g: float
    fat_g: float
    fiber_g: float
    sugar_g: float | None = Field(description="Azúcares en g, null si no lo puedes estimar")
    sat_fat_g: float | None = Field(description="Grasa saturada en g, null si no lo puedes estimar")
    sodium_mg: float | None = Field(description="Sodio en mg, null si no lo puedes estimar")


class FoodAnalysis(BaseModel):
    is_food: bool = Field(description="false si la imagen o el texto no es comida ni bebida")
    title: str = Field(description="Nombre corto de la comida, máx. 50 caracteres, p. ej. 'Lentejas con chorizo y pan'")
    items: list[FoodItemOut] = Field(description="Cada alimento por separado, incluidos aceite, salsas, pan, bebida y postre")
    confidence: Literal["alta", "media", "baja"]
    assumptions: list[str] = Field(description="0-4 supuestos cortos (máx. 90 caracteres cada uno), "
                                               "p. ej. 'Estimo 1 cucharada de aceite en el sofrito'")
    unclear: str | None = Field(description="Lo que no se puede saber por la foto o el texto (relleno, cantidad, salsa), "
                                            "en una frase corta; null si todo está claro")


SYSTEM = """Eres dietista-nutricionista y estimas lo que hay en una comida a partir de una foto o de una descripción, para una app de deporte en España.
Escribes en castellano de España, con frases cortas.

Cómo estimar:
- Separa cada alimento (también aceite, salsas, pan, bebida y postre) y estima su peso en gramos y su ración.
- Usa las referencias de tamaño de la foto (plato llano de unos 26 cm, cubiertos, vaso, taza, mano) para las raciones.
- Usa valores de tablas españolas y europeas (BEDCA) y recetas caseras típicas de España y del Mediterráneo
  (tortilla de patatas, lentejas, paella, cocido, ensaladilla, bocadillos, tostada con tomate, menú del día, tapas).
- Sé realista con las grasas que no se ven: aceite de oliva del sofrito, las frituras, los aliños y las tostadas
  (1 cucharada sopera = 10 g = 90 kcal). Si no se ve, asume la cantidad de una receta casera normal y dilo en assumptions.
- La nota de la persona manda sobre lo que ves ("sin aceite", "media ración", "con 2 cucharadas de aceite", "leche sin lactosa").
- Las raciones de bar o restaurante suelen ser más grandes que las de casa.
- Las kcal tienen que cuadrar con los macros (unas 4 kcal/g de proteína e hidratos, 9 de grasa y 7 de alcohol).
- Si algo no se distingue (relleno, salsa, cantidad), da tu mejor estimación, baja la confianza y explícalo en unclear.
  No inventes alimentos que no se ven ni se mencionan, salvo el aceite o la sal de cocinar habituales.
- Si no es comida ni bebida, is_food = false y items vacío.

Tono: neutro y sin juicios. No califiques ningún alimento como bueno o malo, ni hables de culpa, de compensar o de quemar lo comido. Solo describes y estimas."""


def _prompt(entry: dict, has_photo: bool) -> str:
    parts = [f"Tipo de comida: {MEAL_LABEL.get(entry.get('meal'), 'Comida')} ({entry.get('time', '')})."]
    if entry.get("text"):
        parts.append(f"Descripción de la persona: {entry['text']}")
    if entry.get("note"):
        parts.append(f"Nota de la persona (manda sobre lo que se ve): {entry['note']}")
    if not has_photo and entry.get("items"):
        # Reanálisis sin foto (la foto no se guarda): se parte de lo que se estimó antes
        prev = [{k: it.get(k) for k in ("name", "portion", "grams")} for it in entry["items"]]
        parts.append("Antes se estimó esto (ajústalo a la nota): " + json.dumps(prev, ensure_ascii=False))
    parts.append("Estima los alimentos, sus gramos y sus nutrientes." if has_photo
                 else "No hay foto: estima a partir del texto.")
    return "\n".join(parts)


def _media_type(img: bytes) -> str:
    if img[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if img[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if img[:4] == b"RIFF" and img[8:12] == b"WEBP":
        return "image/webp"
    raise ValueError("Formato de foto no válido (usa JPEG, PNG o WebP).")


def decode_photo(b64: str) -> tuple[bytes, str]:
    """Foto en base64 (con o sin prefijo data:). Comprueba tamaño y formato. Nunca se guarda ni se registra."""
    s = str(b64 or "")
    if s.startswith("data:"):
        s = s.split(",", 1)[-1]
    if len(s) > MAX_PHOTO_BYTES * 4 // 3 + 8:
        raise OverflowError("La foto pesa demasiado (máx. 1,5 MB). La app la reduce sola: vuelve a elegirla.")
    try:
        img = base64.b64decode(s, validate=True)
    except (ValueError, TypeError):
        raise ValueError("Foto no válida.") from None
    if not img:
        raise ValueError("Foto vacía.")
    if len(img) > MAX_PHOTO_BYTES:
        raise OverflowError("La foto pesa demasiado (máx. 1,5 MB). La app la reduce sola: vuelve a elegirla.")
    return img, _media_type(img)


def analyze(entry: dict, image: bytes | None = None, media_type: str = "image/jpeg") -> tuple[FoodAnalysis, float, str]:
    """Una llamada a Claude (visión + salida estructurada). El coste se apunta en el registro de gasto de IA."""
    if ai.over_budget():
        raise BudgetExceeded(f"Has llegado al tope de IA de este mes ({ai.budget():.0f} $): apunta los alimentos a mano. "
                             "La estimación con IA vuelve el día 1.")
    key = ai._api_key()
    if not key:
        raise FoodAIError("No hay clave de IA configurada: apunta los alimentos a mano.")
    # CloudFront corta a los 60 s: un solo intento con 45 s como mucho; si falla, la comida queda guardada para reintentar
    client = anthropic.Anthropic(api_key=key, max_retries=0, timeout=45)
    model = ai.pick_model(MODEL)
    content: list[dict] = []
    if image:
        content.append({"type": "image", "source": {"type": "base64", "media_type": media_type,
                                                    "data": base64.standard_b64encode(image).decode()}})
    content.append({"type": "text", "text": _prompt(entry, bool(image))})
    try:
        resp = client.beta.messages.parse(
            model=model, **(ai.FALLBACKS if model != ai.MODEL else {}),
            max_tokens=8000, output_config={"effort": "low"}, system=SYSTEM,
            messages=[{"role": "user", "content": content}], output_format=FoodAnalysis)
    except anthropic.BadRequestError as e:
        log.warning("Comida: petición rechazada: %s", str(e.message)[:160])
        raise FoodAIError("La IA no ha podido leer esta foto. Prueba con otra o escríbelo.") from None
    except anthropic.APIConnectionError:
        raise FoodAIError("La IA ha tardado demasiado o no responde. Tu comida está guardada: pulsa Reintentar.") from None
    except anthropic.APIStatusError as e:
        raise FoodAIError(f"La IA no está disponible ahora ({e.status_code}). Tu comida está guardada: pulsa Reintentar.") from None
    except ValidationError:
        raise FoodAIError("La respuesta de la IA no tenía el formato esperado. Pulsa Reintentar.") from None
    cost = ai._log_usage(resp, "comida", model)  # toda respuesta 200 se cobra: se apunta siempre
    if resp.stop_reason == "refusal" or resp.parsed_output is None:
        raise FoodAIError("La IA no ha podido estimar esta comida. Apunta los alimentos a mano.")
    if resp.stop_reason == "max_tokens":
        raise FoodAIError("La respuesta de la IA salió incompleta. Pulsa Reintentar.")
    return resp.parsed_output, cost, model


def apply_analysis(entry: dict, out: FoodAnalysis, cost: float, model: str, from_photo: bool) -> dict:
    if not out.is_food or not out.items:
        raise FoodAIError("No parece comida. Prueba con otra foto o escribe lo que has comido.")
    items = [clean_item({"name": i.name, "portion": i.portion, "grams": i.grams, "kcal": i.kcal, "protein": i.protein_g,
                         "carbs": i.carbs_g, "fat": i.fat_g, "fiber": i.fiber_g, "sugar": i.sugar_g,
                         "satFat": i.sat_fat_g, "sodium": i.sodium_mg}) for i in out.items[:MAX_ITEMS]]
    entry.update({"items": items, "title": _text(out.title, 60), "confidence": out.confidence,
                  "assumptions": [_text(a, 120) for a in out.assumptions[:4]], "unclear": _text(out.unclear, 200) or None,
                  "status": "ok", "source": "ai", "fromPhoto": entry.get("fromPhoto") or from_photo,
                  "cost": round((entry.get("cost") or 0) + cost, 5), "model": model, "updatedAt": _now()})
    entry.pop("error", None)
    entry.pop("edited", None)
    return entry


# ======================================================================== balance frente a lo que gastas
def burned_by_day(days: list[dict], today: date | None = None) -> tuple[dict, float | None]:
    """{fecha: {"kcal", "active", "partial"}} y el gasto en reposo típico (mediana de los últimos 28 días completos).
    Garmin da el total del día (reposo + actividad). El de hoy va a medias (el reposo se suma hora a hora): se estima
    como el reposo típico del día entero + la actividad que llevas, sin inventar actividad futura."""
    today = today or date.today()
    t = today.isoformat()
    rest = [d["cal"] - (d.get("calActive") or 0) for d in days
            if d.get("cal") and d["d"] < t and d["d"] >= (today - timedelta(days=28)).isoformat()]
    rest = [r for r in rest if 800 <= r <= 4500]
    bmr = round(statistics.median(rest)) if rest else None
    out = {}
    for d in days:
        if not d.get("cal"):
            continue
        active = d.get("calActive") or 0
        if d["d"] == t:
            out[t] = {"kcal": max(d["cal"], (bmr or 0) + active), "active": active, "partial": True}
        elif d["d"] < t:
            out[d["d"]] = {"kcal": d["cal"], "active": active, "partial": False}
    return out, bmr


def daily_totals(es: list[dict]) -> dict[str, dict]:
    by: dict[str, list] = {}
    for e in es:
        by.setdefault(e["date"], []).extend(e.get("items") or [])
    return {d: {**totals(items), "entries": sum(1 for e in es if e["date"] == d)} for d, items in by.items()}


def latest_weight(data: dict) -> dict | None:
    w = [x for x in (data.get("weights") or []) if x.get("kg")]
    return {"kg": w[-1]["kg"], "date": w[-1]["d"]} if w else None


def series(data: dict, es: list[dict], n: int, today: date | None = None) -> dict:
    """Los últimos n días: lo que comes, lo que gastas y la diferencia. Las medias cuentan solo los días completos
    (hasta ayer) con algo apuntado."""
    today = today or date.today()
    burned, bmr = burned_by_day(data.get("days") or [], today)
    food = daily_totals(es)
    rows = []
    for i in range(n - 1, -1, -1):
        d = (today - timedelta(days=i)).isoformat()
        f, b = food.get(d), burned.get(d)
        rows.append({"d": d, "intakeKcal": f and f["kcal"], "burnedKcal": b and b["kcal"],
                     "balanceKcal": (f["kcal"] - b["kcal"]) if f and b else None,
                     "protein": f and f["protein"], "carbs": f and f["carbs"], "fat": f and f["fat"],
                     "fiber": f and f["fiber"], "entries": f["entries"] if f else 0, "partial": d == today.isoformat()})
    done = [r for r in rows if r["entries"] and not r["partial"]]

    def avg(key, rs=done):
        v = [r[key] for r in rs if r.get(key) is not None]
        return round(sum(v) / len(v), 1) if v else None
    return {"days": rows, "loggedDays": len(done), "intakeKcalAvg": avg("intakeKcal"),
            "burnedKcalAvg": avg("burnedKcal", [r for r in rows if not r["partial"]]),
            "balanceKcalAvg": avg("balanceKcal"), "proteinAvg": avg("protein"), "carbsAvg": avg("carbs"),
            "fatAvg": avg("fat"), "fiberAvg": avg("fiber"), "bmrKcal": bmr}


def target(goal: dict | None, burned_avg: float | None, bmr: float | None) -> dict | None:
    """Objetivo orientativo con límites: nunca más de un 20 % por debajo de lo que gastas ni por debajo de tu gasto
    en reposo; como mucho un 15 % por encima. Sin cifras extremas."""
    if not goal or not goal.get("mode") or not burned_avg:
        return None
    f = GOAL_FACTOR.get((goal["mode"], goal.get("pace") or "suave"), 1.0)
    t = burned_avg * f
    floor = max(burned_avg * (1 - MAX_DEFICIT), bmr or 0)
    limited = False
    if t < floor:
        t, limited = floor, True
    if t > burned_avg * (1 + MAX_SURPLUS):
        t, limited = burned_avg * (1 + MAX_SURPLUS), True
    t = round(t / 10) * 10
    return {"mode": goal["mode"], "pace": goal.get("pace") or "suave", "targetKcal": t,
            "rangeKcal": [t - 100, t + 100], "deltaKcal": round(t - burned_avg), "limited": limited}


def fuel_tip(coach_state: dict | None, today: date | None = None) -> dict | None:
    """Si hoy (o mañana) toca una sesión exigente del plan: recordatorio de comer hidratos antes y después."""
    today = today or date.today()
    plan = (coach_state or {}).get("plan") or {}
    sess = {s.get("date"): s for w in plan.get("weeks") or [] for s in w.get("sessions") or [] if s.get("type") in FUEL_TYPES}
    t, tm = today.isoformat(), (today + timedelta(days=1)).isoformat()
    if t in sess:
        s = sess[t]
        return {"when": "hoy", "session": s.get("title") or FUEL_TYPES[s["type"]],
                "text": f"Hoy toca {s.get('title') or FUEL_TYPES[s['type']]}: unos hidratos 2-3 h antes (pan, arroz, fruta) y, "
                        "al terminar, hidratos con algo de proteína para recuperar. Y bebe."}
    if tm in sess and sess[tm]["type"] in ("long", "race"):
        s = sess[tm]
        return {"when": "mañana", "session": s.get("title") or FUEL_TYPES[s["type"]],
                "text": f"Mañana toca {s.get('title') or FUEL_TYPES[s['type']]}: una cena con hidratos (pasta, arroz, patata) "
                        "te ayuda a llegar con energía."}
    return None


def _strip_kcal(obj):
    """'Ocultar calorías': quita todo lo que sea una cifra de calorías (claves con 'kcal')."""
    if isinstance(obj, dict):
        return {k: _strip_kcal(v) for k, v in obj.items() if "kcal" not in k.lower()}
    if isinstance(obj, list):
        return [_strip_kcal(v) for v in obj]
    return obj


def present(entry: dict | None, st: dict | None = None) -> dict | None:
    """Una comida tal como la ve la web: con sus totales y sin calorías si las ocultas."""
    if entry is None:
        return None
    e = {**entry, "totals": totals(entry.get("items") or [])}
    return _strip_kcal(e) if prefs(st)["hideCalories"] else e


def view(data: dict | None, st: dict | None = None, coach_state: dict | None = None, today: date | None = None,
         days: int = 30) -> dict:
    """Todo lo que necesita la página Comida."""
    today = today or date.today()
    st = load() if st is None else st
    p = prefs(st)
    data = data or {}
    since = (today - timedelta(days=max(days, 30) - 1)).isoformat()
    es = [e for e in entries(st) if e["date"] >= since]
    s30 = series(data, es, 30, today)
    s7 = {k: v for k, v in series(data, es, 7, today).items() if k != "days"}
    has_burned = any(r["burnedKcal"] is not None for r in s30["days"])
    today_row = s30["days"][-1]
    weight = latest_weight(data)
    goal = target(p["goal"], s7["burnedKcalAvg"] or s30["burnedKcalAvg"], s30["bmrKcal"])
    protein_ref = None
    if weight:
        protein_ref = {"weightKg": weight["kg"], "weightDate": weight["date"],
                       "gPerKgAvg7": round(s7["proteinAvg"] / weight["kg"], 2) if s7["proteinAvg"] else None,
                       "gPerKgToday": round(today_row["protein"] / weight["kg"], 2) if today_row["protein"] else None,
                       "refGPerKg": list(PROTEIN_REF),
                       "refG": [round(PROTEIN_REF[0] * weight["kg"]), round(PROTEIN_REF[1] * weight["kg"])]}
    out = {
        "prefs": p,
        "entries": [{**e, "totals": totals(e.get("items") or [])} for e in es],  # se quitan las kcal al final si toca
        "today": {**today_row, "burnedActiveKcal": None},
        "week": s7, "month": s30,
        "hasBurned": has_burned,
        "goal": goal,
        "protein": protein_ref,
        "weights": [w for w in (data.get("weights") or []) if w.get("d", "") >= (today - timedelta(days=180)).isoformat()],
        "fuel": fuel_tip(coach_state, today),
        "favorites": favorites(st),
        "note": ACCURACY_NOTE,
        "budget": {"over": ai.over_budget()},
    }
    burned, _ = burned_by_day(data.get("days") or [], today)
    if today.isoformat() in burned:
        out["today"]["burnedActiveKcal"] = burned[today.isoformat()]["active"]
    return _strip_kcal(out) if p["hideCalories"] else out


def for_coach(data: dict, today: date | None = None) -> dict | None:
    """Resumen de la última semana para el coach, solo si la persona usa el módulo y ha apuntado algo."""
    today = today or date.today()
    st = load()
    p = prefs(st)
    if not p["enabled"]:
        return None
    es = [e for e in entries(st) if e["date"] >= (today - timedelta(days=7)).isoformat()]
    s = series(data, es, 8, today)  # 7 días completos + hoy
    if not s["loggedDays"]:
        return None
    w = latest_weight(data)
    out = {
        "dias_con_comidas_apuntadas_de_7": s["loggedDays"],
        "kcal_media_dia": s["intakeKcalAvg"], "gasto_medio_dia_garmin": s["burnedKcalAvg"],
        "balance_medio_dia": s["balanceKcalAvg"],
        "proteina_media_g": s["proteinAvg"], "hidratos_media_g": s["carbsAvg"], "grasa_media_g": s["fatAvg"],
        "fibra_media_g": s["fiberAvg"],
        "proteina_g_por_kg": round(s["proteinAvg"] / w["kg"], 2) if (w and s["proteinAvg"]) else None,
        "objetivo_de_la_persona": p["goal"],
        "oculta_calorias": p["hideCalories"],
        "nota": "Estimaciones por foto o texto (±20-30 %). Solo cuentan los días con algo apuntado; si un día no se "
                "apuntó todo, el balance sale más bajo de lo real.",
    }
    if p["hideCalories"]:
        out = {k: v for k, v in out.items() if not any(x in k for x in ("kcal", "gasto", "balance"))}
    return out
