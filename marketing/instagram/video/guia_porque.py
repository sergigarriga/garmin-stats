"""Guía y hoja de contacto de los vídeos de la serie «El porqué de tus datos» (reels + stories, 4 a 31-dic de 2026).

    uv run --no-project --with playwright==1.58.0 --with fonttools python marketing/instagram/video/guia_porque.py

Lee video/reels-porque.json y stories-porque.json (con el plan de stories.py) y escribe, en marketing/privado/porque/:
`guia-video.md` (fecha, hora de España, archivo, texto y sticker, en orden de publicación) y `contacto-video.png`
(las portadas de los reels y un fotograma de cada story). No sube ni programa nada.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
IG = HERE.parent
ROOT = IG.parent.parent
DEST = ROOT / "marketing" / "privado" / "porque"
REELS = IG / "out" / "video-porque"

os.environ["RUNCH_STORIES_CAL"] = "stories-porque.json"
sys.path.insert(0, str(IG))
import stories as S  # noqa: E402

DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
KIND = {"dato": "Dato del día", "mito": "Mito o realidad", "quiz": "Quiz", "reel": "Hoy reel", "turno": "Tu turno"}
plain = lambda x: x.replace("*", "")  # noqa: E731
win = lambda p: "\\\\wsl.localhost\\Ubuntu" + str(p).replace("/", "\\")  # noqa: E731


def story_text(es: dict, ca: dict) -> tuple[str, str]:
    """Texto (castellano) y nota de sticker de una pareja de stories."""
    k = es["kind"]
    if k == "dato":
        return f'**{es["hero"]}** {es["unit"]} · {plain(es["why"])}', ""
    if k == "mito":
        v = S.T["es"]["verdict"][es["verdict"]].upper()
        return f'{" ".join(es["claim"])} → **{v}** · {plain(es["why"])}', ""
    if k == "reel":
        return f'Hoy reel a las 21:00 · {plain(es["hook"])}', ""
    q, qc = es["turn"], ca["turn"]
    if k == "quiz":
        ok, okc = q["options"][q["answer"]], qc["options"][qc["answer"]]
        return (f'«{plain(" ".join(q["lines"]))}»',
                f'**Sticker de quiz** (ver `-guia.png`). ES: {" / ".join(q["options"])} (correcta: {ok}). '
                f'CA: {" / ".join(qc["options"])} (correcta: {okc})')
    return (f'«{plain(" ".join(q["lines"]))}»',
            f'**Sticker de encuesta** (ver `-guia.png`). ES: {" / ".join(q["options"])}. CA: {" / ".join(qc["options"])}')


def main() -> None:
    reels = json.loads((HERE / "reels-porque.json").read_text())["reels"]
    plan = S.plan()
    DEST.mkdir(parents=True, exist_ok=True)

    # ---------------------------------------------------------------- filas en orden de publicación
    rows = []   # (fecha, hora, texto de la fila)
    by: dict[tuple[str, str], list[dict]] = {}
    for s in plan:
        by.setdefault((s["date"], s["time"]), []).append(s)
    for (date, time), grp in by.items():
        ca = next(s for s in grp if s["lang"] == "ca")
        es = next(s for s in grp if s["lang"] == "es")
        txt, note = story_text(es, ca)
        post = f' · Abajo recuerda el post de las 19:00: «{es["post"]}»' if es.get("post") and es["kind"] != "reel" else ""
        files = " → ".join(f"`{S.name(s)}.mp4`" for s in (ca, es))
        rows.append((date, f"{time[:2]}:{time[2:]}", f"Story · {KIND[es['kind']]}", files, txt + post, note))
    for r in reels:
        date, time = r["schedule"].split(" ")
        idioma = "catalán" if r["lang"] == "ca" else "castellano"
        rows.append((date, time, f"**Reel** ({idioma})", f'`reel-pq-{r["id"]}.mp4` · portada `reel-pq-{r["id"]}-portada.png`',
                     plain(r["hook"]["title"]) + " · caption abajo, en «Reels»", ""))
    rows.sort(key=lambda x: (x[0], x[1]))
    table = []
    for date, time, kind, files, txt, note in rows:
        d = dt.date.fromisoformat(date)
        table.append(f"| {DIAS[d.weekday()]} {d.day}-{d.month:02d} | {time} | {kind} | {files} | {txt} | {note} |")

    # ---------------------------------------------------------------- reels: caption, hashtags, alt
    blocks = []
    for r in reels:
        d = dt.date.fromisoformat(r["schedule"][:10])
        blocks.append(
            f'### {DIAS[d.weekday()]} {d.day}-{d.month:02d} · 21:00 · `reel-pq-{r["id"]}.mp4` ({"catalán" if r["lang"] == "ca" else "castellano"})\n\n'
            f'- Portada: `reel-pq-{r["id"]}-portada.png` (9:16) · cuadrícula: `reel-pq-{r["id"]}-portada-4x5.png` · tono '
            f'{"claro" if r.get("coverBg") == "cream" else "de color"} para el damero\n'
            f'- Sin música (para poner un sonido en tendencia desde la app): `reel-pq-{r["id"]}-sin-musica.mp4`\n'
            f'- Idea: {plain(r["hook"]["title"])} {r["why"]["take"]}\n\n'
            f'Texto del post:\n\n```\n{r["caption"]}\n\n{" ".join(r["hashtags"])}\n```\n\n'
            f'Texto alternativo: {r["alt"]}\n')

    stickers = "\n".join(f"- **{DIAS[dt.date.fromisoformat(d).weekday()]} {int(d[8:])}-{d[5:7]} · {t}** · {files}: {txt} — {note}"
                         for d, t, k, files, txt, note in rows if note)
    out_st = S.OUT
    guide = f"""# Vídeos de @runch.run · serie «El porqué de tus datos» · 4-dic → 31-dic de 2026

Reels y stories que explican, en sencillo, por qué importa cada dato de la app y qué lo mueve. Horas de España
(peninsular). Los posts del feed (19:00) son de otro lote (`marketing/instagram/lote-04.json`); aquí solo van los vídeos.

- **Stories** (cada día 09:00; domingos también 12:00): vídeos de 9 s con música, 1080 × 1920. Siempre dos seguidas:
  primero **catalán** (`_1-ca` / `_3-ca`), después **castellano** (`_2-es` / `_4-es`).
  Carpeta: `{out_st.relative_to(ROOT).as_posix()}/` (en Windows: `{win(out_st)}`).
- **Reels** (martes y jueves 21:00): 28 s, 1080 × 1920, con música propia, portada 9:16 y recorte 4:5 para la cuadrícula.
  Se leen sin sonido (no llevan voz). Carpeta: `{REELS.relative_to(ROOT).as_posix()}/` (en Windows: `{win(REELS)}`).
- Hoja de contacto con todo: `marketing/privado/porque/contacto-video.png`.

Nada está subido ni programado: ni S3, ni Business Suite, ni la Lambda de stories.

## Ritmo de la semana

| Día | 09:00 (stories, CA → ES) | 12:00 | 21:00 |
|---|---|---|---|
| Lunes | Mito o realidad | | |
| Martes | Hoy reel | | Reel |
| Miércoles | Quiz (pones tú el sticker) | | |
| Jueves | Hoy reel | | Reel |
| Viernes | Mito o realidad | | |
| Sábado | Dato del día | | |
| Domingo | Dato del día | Tu turno (pones tú la encuesta) | |

El reel es el gancho, el carrusel de las 19:00 es la explicación completa y la story es el recordatorio y la pregunta:
cada story (menos las de «Hoy reel») recuerda abajo el post de ese día.

## Cómo publicarlas

Igual que en `marketing/instagram/out/olivo/stories/calendario/GUIA.md`: Meta Business Suite → **Crear historia** →
cuenta **@runch.run** → subir los dos archivos **en orden** (catalán, castellano) → sin añadir texto ni música (el vídeo
ya los lleva). Si las publica la Lambda `runch-stories`, hay que subir antes estos vídeos a su carpeta de S3: no lo he
hecho. Los reels: desde la app o Business Suite, con la portada `-portada.png`, el texto de abajo y la etiqueta de
contenido que uses en los demás reels.

## Días con sticker (lo pones tú a mano)

En esos vídeos hay un hueco limpio en el centro, entre la pregunta y la ilustración. El archivo `…-guia.png` de cada uno
marca el hueco con un recuadro de rayas (780 × 360 px) y las opciones. En Business Suite o en la app: **Stickers** →
**Quiz** (miércoles, marca la respuesta correcta) o **Encuesta** (domingos) → escribe las opciones → arrástralo al hueco.
El sticker de quiz con tres opciones es más alto: encógelo con dos dedos hasta que quepa.

{stickers}

## Notas

- **Reels en catalán:** el del 15-dic (HRV) y el del 24-dic (peso). El resto, en castellano. Todos cierran con
  «Segueix-nos: @runch.run», como los anteriores.
- **24-dic y 31-dic a las 21:00** (Nochebuena y Nochevieja): se mantiene el horario de siempre, pero a esa hora habrá
  poca gente; si lo prefieres, publícalos esos dos días a las 13:00. El del 24 (peso, «Bones festes») y el del 31
  (Preparación, «En 2027, entrena con cabeza») están escritos para ese día. La story del 25 dice «¡Feliz Navidad!».
- **Portadas de los reels:** tono claro u oscuro según el damero de la cuadrícula que pide
  `marketing/privado/porque/temas-posts.md` (8, 17, 22 y 31-dic claras; 10, 15, 24 y 29-dic de color).
- **Música:** bucle propio de afro house a 120 bpm hecho por código (`marketing/marca/musica/afro_house.py`), sin
  derechos de terceros. Cada reel tiene además su versión `-sin-musica.mp4` por si quieres ponerle un sonido en
  tendencia desde la app.
- **Datos:** todas las cifras de los gráficos son de ejemplo (lo pone en pantalla).
- **Para cambiar un texto:** reels en `marketing/instagram/video/reels-porque.json` (luego `porque.py` y
  `render_video.py <html> --musica --out marketing/instagram/out/video-porque`); stories en
  `marketing/instagram/stories-porque.json` (luego `stories.py --cal=stories-porque.json <fecha>`); y esta guía con
  `marketing/instagram/video/guia_porque.py`.

## Todo, en orden de publicación

| Día | Hora | Qué | Archivos (en este orden) | Texto (castellano) | Sticker a mano |
|---|---|---|---|---|---|
""" + "\n".join(table) + "\n\n## Reels: texto, hashtags y portada\n\n" + "\n".join(blocks)
    (DEST / "guia-video.md").write_text(guide)
    print(DEST / "guia-video.md")

    # ---------------------------------------------------------------- hoja de contacto
    from kit import Renderer  # noqa: PLC0415  (marketing/marca, ya en sys.path por stories.py)

    def cell(img: Path, cap: str) -> str:
        return f'<figure><img src="{img.as_uri()}"><figcaption>{cap}</figcaption></figure>'

    rc = "".join(cell(REELS / f'reel-pq-{r["id"]}-portada.png',
                      f'<b>{int(r["schedule"][8:10])}/12 21:00</b> · reel {r["id"]} ({r["lang"]})') for r in reels)
    sc = "".join(cell(out_st / f"{S.name(s)}.png",
                      f'<b>{int(s["date"][8:])}/12 {s["time"][:2]}:{s["time"][2:]}</b> · {s["n"]}-{s["lang"]} · {s["kind"]}') for s in plan)
    css = ("body{background:#2a2420;font-family:GSF;color:#F7F3EC;padding:28px}h1{font:800 44px Gluten;margin:0 0 6px}"
           "h2{font:800 30px Gluten;margin:26px 0 12px}p{font:500 20px GSF;margin:0;opacity:.8}"
           ".g{display:grid;grid-template-columns:repeat(16,198px);gap:12px}.g.r{grid-template-columns:repeat(8,270px)}"
           "figure{margin:0}img{width:100%;aspect-ratio:9/16;display:block;border-radius:10px}"
           "figcaption{font:500 14px GSF;margin-top:5px;white-space:nowrap;overflow:hidden}.r figcaption{font-size:17px}")
    body = (f"<h1>El porqué de tus datos · reels y stories · 4 → 31 dic 2026</h1>"
            f"<p>Portadas de los 8 reels (mar y jue, 21:00) y un fotograma de cada story (CA → ES; 09:00 y domingos 12:00)</p>"
            f'<h2>Reels</h2><div class="g r">{rc}</div><h2>Stories</h2><div class="g">{sc}</div>')
    with Renderer() as r:
        r.png(body, DEST / "contacto-video.png", 28 * 2 + 16 * 198 + 15 * 12, 600, css=css, full=True)
    print(DEST / "contacto-video.png")


if __name__ == "__main__":
    main()
