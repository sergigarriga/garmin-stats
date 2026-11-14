"""Traduce al castellano los nombres de ejercicio de Garmin (src/garmin_stats/garmin_exercises.json).

Uso (una vez, o al actualizar la lista):  uv run python tools/translate_exercises.py
Escribe src/garmin_stats/garmin_exercise_names_es.json: {"CATEGORIA": {"SUB_CATEGORIA": "Nombre en castellano"}}.
"""

import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import anthropic

ROOT = Path(__file__).resolve().parents[1] / "src" / "garmin_stats"
OUT = ROOT / "garmin_exercise_names_es.json"
KEY = Path("~/.config/anthropic/garmin-stats-key").expanduser().read_text().strip()
SYSTEM = """Traduces nombres de ejercicios de gimnasio de Garmin Connect (en camelCase inglés) al castellano de España,
con la terminología que usa la app Garmin Connect en español. Nombre corto, con mayúscula inicial, sin punto final.
Ejemplos: dumbbellDeadlift → "Peso muerto con mancuernas"; alternatingDumbbellLunge → "Zancada alterna con mancuernas";
extendedPlank → "Plancha extendida"; weightedSwissBallCrunch → "Encogimientos abdominales sobre pelota suiza con peso";
sidePlankToPlankWithReachUnder → "Plancha lateral con extensión de brazo debajo del cuerpo"; barbellBackSquat → "Sentadilla trasera con barra";
weightedStandingCalfRaise → "Elevación de talones de pie con peso"; pushUp → "Flexión"; pullUp → "Dominada"; barbellBenchPress → "Press de banca con barra".
Responde SOLO con un objeto JSON {nombreOriginal: "traducción"} con exactamente las mismas claves que recibes."""


def snake(camel: str) -> str:
    s = re.sub(r"(?<=[a-z])(?=[A-Z0-9])|(?<=[0-9])(?=[A-Za-z])|(?<=[A-Z])(?=[A-Z][a-z])", "_", camel)
    return s.upper()


def translate(item):
    cat, names = item
    client = anthropic.Anthropic(api_key=KEY, max_retries=3, timeout=120)
    out: dict[str, str] = {}
    keys = list(names)
    for i in range(0, len(keys), 80):
        chunk = keys[i:i + 80]
        resp = client.messages.create(model="claude-sonnet-5-5", max_tokens=8000, system=SYSTEM,
                                      messages=[{"role": "user", "content": f"Categoría: {cat}\n" + json.dumps(chunk)}])
        text = "".join(b.text for b in resp.content if b.type == "text")
        got = json.loads(text[text.index("{"):text.rindex("}") + 1])
        out.update({k: str(got[k]).strip() for k in chunk if got.get(k)})
    return snake(cat), {snake(k): v for k, v in out.items()}


def main():
    src = json.loads((ROOT / "garmin_exercises.json").read_text())
    with ThreadPoolExecutor(6) as pool:
        res = dict(pool.map(translate, [(c, v["names"]) for c, v in src.items()]))
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=0, sort_keys=True))
    print(len(res), "categorías,", sum(len(v) for v in res.values()), "nombres →", OUT)


if __name__ == "__main__":
    main()
