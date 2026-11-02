# Instagram de "Mi salud"

Posts con el mismo estilo que la app (letra Google Sans Flex, colores y tarjetas de `web/src/theme.ts`).
El agente `.claude/agents/instagram-posts.md` los crea: pídele "usa el agente de Instagram para hacer el lote 2".

## Generar

```bash
uv run --no-project --with playwright python marketing/instagram/render.py marketing/instagram/lote-01.json
```

Salida en `out/lote-01/` (no se sube a git):
- `01-presentacion-1.png`, `01-presentacion-2.png`… una imagen por diapositiva (1080 x 1350, formato 4:5).
- `captions.md`: texto del post, hashtags y texto alternativo de cada uno.
- `grid.png`: cómo quedará la cuadrícula del perfil cuando estén todos publicados.

Publica los posts en orden (01 primero). Los carruseles se suben como una sola publicación con varias imágenes.

## Formato de un lote

```json
{
  "lote": "02",
  "notes": "Para quien publica",
  "posts": [{
    "id": "hrv", "title": "HRV", "color": "recovery",
    "slides": [ { "layout": "cover", "kicker": "HRV", "icon": "MonitorHeart", "title": "Texto con **resalte**",
                  "body": "Subtítulo", "visual": { "type": "metric", "...": "..." } } ],
    "caption": "Texto del post", "hashtags": ["#hrv"], "alt": "Descripción de la imagen"
  }]
}
```

- `color`: activity (verde), heart (rojo), sleep (índigo), stress (ámbar), recovery (turquesa), energy (azul),
  training (naranja), gym (morado). También vale un color `#RRGGBB`.
- `dark: true` (en el post o en una diapositiva): modo oscuro.
- Diapositivas (`layout`):
  - `hook`: gancho a pantalla completa. `title`, `body`, `sticker` (pegatina ladeada: "Confiesa", "Red flag", "POV"…),
    `bg` ("color" = color del post, por defecto, o "dark"), `size` (118 por defecto), `swipe` (botón "Desliza").
  - `versus`: `title`, `left` y `right` ({`label`, `value`, `unit`, `lines`, `tone`: "good" en el bueno}), `body`.
  - `cover`: `kicker`, `icon`, `title`, `body`, `visual` (opcional), `size` (tamaño del titular, 96 por defecto).
  - `points`: `title` y `points` [{`icon`, `color`, `title`, `body`}] (3-4 puntos).
  - `big`: `big` (número o texto enorme), `title`, `body`.
  - `cta`: `title`, `body`, `icon`, `actions` [{`icon`, `text`}].
  - `example: false` quita la nota "Datos de ejemplo".
- Visuales (`visual.type`, mira `lote-01.json` para ver los campos de cada uno): `rings` (3 anillos), `ring` (un
  anillo con datos al lado), `metric` (número grande y línea con franja), `readiness` (nota y barras), `rows` (lista
  con valores), `zones` (zonas Z1-Z5), `chat` (conversación con el coach), `bars` (barras), `curve` (curva del día),
  `mood` (¿cómo te encuentras?), `schedule` (hora de acostarse), `steps` (pasos de un entreno).
- Iconos: los nombres de `icons.json` (iconos "Rounded" de Material).

El script avisa si un texto no cabe o algo se sale de una tarjeta. Todos los números deben ser de ejemplo.
