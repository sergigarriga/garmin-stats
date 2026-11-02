# Instagram de "Runch"

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
- `todos.html`: página para revisar el lote: cada post en una fila con sus imágenes en orden, su texto y sus hashtags.

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
- Estilo: fondos pastel con manchas difuminadas, titulares centrados con subrayador en `**palabra**`, pegatinas y
  tarjetas un poco giradas. No hay modo oscuro.
- Diapositivas (`layout`):
  - `hook`: gancho centrado. `title`, `body`, `sticker` (pegatina ladeada: "Confiesa", "Red flag", "POV"…), `floats`
    (2-4 pegatinas con datos cortos), `size` (112 por defecto), `swipe` (botón "Desliza").
  - `versus`: `title`, `left` y `right` ({`label`, `value`, `unit`, `lines`, `tone`: "good" en el bueno}), `body`.
  - `cover`: `kicker`, `icon`, `title`, `body`, `visual` (tarjeta girada), `tag` (etiqueta en su esquina), `tilt`
    (giro en grados), `size` (tamaño del titular, 86 por defecto).
  - `points`: mosaico. `title` y `points` [{`icon`, `color`, `title`, `body`}] (3-4 bloques; con 3, el primero ocupa
    todo el ancho).
  - `big`: `big` (número o texto enorme), `title`, `body`.
  - `cta`: `title`, `body`, `icon`, `actions` [{`icon`, `text`}].
  - `example: false` quita la nota "Datos de ejemplo".
- Visuales (`visual.type`, mira `lote-01.json` para ver los campos de cada uno): `rings` (3 anillos), `ring` (un
  anillo con datos al lado), `metric` (número grande y línea con franja), `readiness` (nota y barras), `rows` (lista
  con valores), `zones` (zonas Z1-Z5), `chat` (conversación con el coach), `bars` (barras), `curve` (curva del día),
  `mood` (¿cómo te encuentras?), `schedule` (hora de acostarse), `steps` (pasos de un entreno).
- Iconos: los nombres de `icons.json` (iconos "Rounded" de Material).

El script avisa si un texto no cabe o algo se sale de una tarjeta. Todos los números deben ser de ejemplo.

## Vídeos (Reels)

Animaciones hechas con código (HTML + una función `render(t)` que pinta cada fotograma), con el mismo estilo que los
posts. Se graban fotograma a fotograma, sin saltos, y se montan en MP4 vertical (1080 x 1920, 30 fps, sin audio: el
audio se elige en Instagram).

```bash
uv run --no-project --with playwright python marketing/instagram/video/render_video.py marketing/instagram/video/showreel.html
```

- `video/showreel.html`: presentación de Runch en 15 s (logo, cintas de texto, móvil en 3D con la app, zonas, coach y
  comunidad).
- `video/reel-z2.html`: "¿Tienes un Garmin y no sabes qué es la Z2?" en 15 s.
- Salida en `out/video/<nombre>.mp4` y una portada `<nombre>-portada.png`. Necesita `ffmpeg`.
- **Voz, música y subtítulos:** escribe el guion en `video/<nombre>.voz.json` (frase, segundo en que empieza y, si hace
  falta, cómo pronunciarla: `"say": "Ranch"` para que la voz diga bien "Runch") y los efectos (`whoosh`, `pop`, `tick`,
  `ding`, `stamp`, `swell`, `sparkle`). Luego:
  `uv run --no-project --with piper-tts --with numpy python marketing/instagram/video/voiceover.py marketing/instagram/video/showreel.voz.json`
  y vuelve a lanzar `render_video.py`. Sale `<nombre>.mp4` completo (voz + música + subtítulos) y `<nombre>.srt`.
- Voz: Amazon Polly con la cuenta de AWS (`"voice": "polly:Lucia:generative:eu-central-1"`; también Sergio generativa, o
  Alba y Raúl `long-form` en us-east-1, que además dan el tiempo exacto de cada palabra). Unas centésimas de dólar por
  vídeo. `"tempo"` acelera la voz sin cambiar el tono. Muestras en `out/video/voces/`. Sin conexión queda Piper
  (`"voice": "es_ES-davefx-medium"`, más robótica).
- La música la compone el script (sin derechos de autor) y baja sola cuando habla la voz; volumen final a -14 LUFS.
- Para hacer uno nuevo: copia un HTML, cambia las escenas y sus tiempos en `render(t)` y ajusta `window.DURATION`.
  Deja libre el cuarto inferior de la pantalla: Instagram pone ahí el texto y los botones.
