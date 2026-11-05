# Instagram de "Runch" (@runch.run)

Posts con el sistema editorial de la marca (ver "Sistema visual").
El agente `.claude/agents/instagram-posts.md` los crea: pídele "usa el agente de Instagram para hacer el lote 2".

## Generar

```bash
uv run --no-project --with playwright python marketing/instagram/render.py marketing/instagram/lote-01.json
```

Salida en `out/lote-01/` (no se sube a git):
- `01-presentacion-1.png`, `01-presentacion-2.png`… una imagen por diapositiva (1080 x 1350, formato 4:5), y un
  `.mp4` en las diapositivas con `"animate": true` (ver "Diapositivas animadas").
- `captions.md`: texto del post, hashtags y texto alternativo de cada uno.
- `grid.png`: cómo quedará la cuadrícula del perfil cuando estén todos publicados.
- `todos.html`: página para revisar el lote: cada post en una fila con sus imágenes en orden, su texto y sus hashtags.

Publica los posts en orden (01 primero). Los carruseles se suben como una sola publicación con varias imágenes.

## Sistema visual (editorial)

Blanco roto cálido (`cream` #F7F3EC, interiores `paper` #FCFAF6, desde el lote 02), espresso y terracota (más salvia, mar y mantequilla), titulares en Fraunces con la palabra clave en cursiva
terracota, textos en Google Sans Flex, etiquetas en mayúsculas espaciadas y gráficos de línea fina. Maqueta fija:
el logotipo «runch» (`marketing/marca/logo/`, terracota sobre fondo claro y crema sobre oscuro) y "Nº 01 · TEMA" arriba; @runch.run, "Datos de ejemplo" y "Desliza →" abajo. Sirve igual para los datos de
la app que, más adelante, para fotos de quedadas y estilo de vida (formato `photo`). La versión anterior (pastel) queda en
`render_v1.py` y `lote-01-v1.json`.

## Formato de un lote

```json
{
  "lote": "02",
  "handle": "@runch.run",
  "notes": "Para quien publica",
  "posts": [{
    "id": "hrv", "title": "HRV", "bg": "cream", "topic": "HRV",
    "slides": [ { "layout": "cover", "kicker": "Variabilidad cardiaca", "title": "Texto con **cursiva**",
                  "body": "Subtítulo", "visual": { "type": "metric", "...": "..." } } ],
    "caption": "Texto del post", "hashtags": ["#hrv"], "alt": "Descripción de la imagen"
  }]
}
```

- `bg` (portada) y `inner` (resto, `paper` por defecto): `cream`, `paper`, `terracotta`, `espresso`, `sage`, `sea`,
  `butter`. Cada diapositiva puede llevar su propio `bg`.
- Formatos (`layout`): `hook` (`kicker`, `title`, `body`, `facts`, `size`), `cover` (`kicker`, `title`, `body`,
  `visual`), `points` (`title`, `points` [{`title`, `body`}]), `versus` (`title`, `left`, `right`, `body`), `big`
  (`big`, `bigSize`, `title`, `body`), `cta` (`title`, `body`, `actions`) y `photo` (`image`, `title`, `body`).
- Gráficos (`visual.type`, ver `lote-01.json`): `zones`, `readiness`, `rows`, `metric`, `ring`, `curve`, `chat`,
  `schedule`, `steps`. `example: false` quita "Datos de ejemplo".

El script avisa si un texto no cabe o algo se acerca demasiado al borde. Todos los números deben ser de ejemplo.

### Diapositivas animadas (vídeo dentro del carrusel)

Añade `"animate": true` a una diapositiva (y, si quieres, `"duration": 6`, en segundos; 6 por defecto) y, además del
PNG, sale `NN-id-i.mp4`: 1080 x 1350, H.264, 30 fps, sin audio. Solo se mueve el gráfico; el marco (Runch · Nº,
título, texto, pie) queda quieto e idéntico al PNG. Empieza 0,4 s quieto con el gráfico vacío, anima unos 2-3 s y se
queda quieto en el estado final al menos 2 s (el último fotograma es el PNG, así el bucle se lee bien). En el carrusel
de Instagram se mezclan imágenes y vídeos: sube el `.mp4` en lugar del `.png` de esa diapositiva (el PNG sirve de
portada o reserva). Al lado sale `NN-id-i-frames.png`, una hoja con 6 fotogramas para revisarlo sin abrir el vídeo.

- `zones`: las filas entran una tras otra, los rangos cuentan hacia arriba y luego todas se apagan menos la destacada.
- `readiness`: la nota cuenta hacia arriba; cada señal entra, su barra crece y su cifra cuenta; la etiqueta al final.
- `rows`: las filas entran una tras otra y sus cifras cuentan (también ritmos 4:50 y rangos).
- `metric`: la cifra cuenta, la franja se abre y la línea se dibuja con el punto en la punta; el texto en cursiva al final.
- `ring`: el anillo se llena mientras el centro cuenta; los datos de al lado entran después.
- `curve`: la línea se dibuja con el punto en la punta; la etiqueta aparece al final.
- `chat`: los mensajes aparecen uno tras otro. `schedule`: la franja se abre y los puntos aparecen de izquierda a derecha.
- `steps`: los pasos entran uno tras otro con su punto. `big` y `versus`: la cifra cuenta hacia arriba (en `big`, con
  un barrido de abajo arriba).

Las cifras cuentan desde 0 con frenada suave, respetan el formato (7,5 · 5:15 · <40 · +3 · %) y usan dígitos de
ancho fijo mientras cuentan, así nada baila. Una diapositiva sin gráfico (p. ej. `hook`) avisa y solo deja el PNG.
Necesita `ffmpeg`.

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
- Reels editoriales (noviembre 2026, 25-30 s con voz): `reel-fcmax` («Tu Z2 del Garmin no es tu Z2»), `reel-vfc` («Estado
  de VFC: desequilibrado»), `reel-bodybattery` («Duermes 8 horas y tu Body Battery no sube»), `reel-six-seven` (meme
  «Six seven»), `reel-aura` (meme «−1000 / +1000 de aura») y `reel-caminar` («Caminar también es entrenar», Empezar
  desde cero). Usan `video/kit.css` + `video/kit.js`: el sistema de los posts (crema/terracota, Fraunces, Google Sans
  Flex) y sus animaciones (palabras que suben, cifras que cuentan, líneas que se dibujan, filas en cascada, barras),
  ilustraciones de `marketing/marca/ilustraciones/gemini/` con `figure()`, y una portada `window.cover()` con el
  titular centrado (cabe en el recorte 3:4). Zona segura: contenido entre y = 300 y 1410, subtítulos a partir de 1440,
  columna derecha libre en la mitad de abajo. Cierre con «Segueix-nos: @runch.run». El texto «Runch» de la cabecera, del
  cierre y de la portada lo cambia kit.js por el logotipo (terracota sobre claro, crema sobre oscuro, como los posts).
  `render_video.py reel-x.html --cover` saca solo la portada. Captions, hashtags, texto alternativo, fecha y
  `"grid": false` (no salen en la cuadrícula del perfil, para no romper el damero) en `reels.json`.
- Salida en `out/video/<nombre>.mp4` y una portada `<nombre>-portada.png`. Necesita `ffmpeg`.
- **Voz, música y subtítulos:** escribe el guion en `video/<nombre>.voz.json` como habla una persona (frases naturales,
  con ritmo de creador de contenido, nada de frases sueltas de robot). Cada parte lleva `"scene"` (segundo de la
  animación en que empieza su escena) y, si hace falta, cómo pronunciarla (`"say": "Ranch"` para que suene "Runch",
  "zeta dos" para "Z2", "quinientos euros" para "500 €"). Todo se graba en una sola toma y la animación espera a la voz,
  así que el vídeo dura lo que dura la voz (unos 30 s). Efectos: `whoosh`, `pop`, `tick`, `ding`, `stamp`, `swell`,
  `sparkle`, en segundos de animación. Luego:
  `uv run --no-project --with piper-tts --with numpy python marketing/instagram/video/voiceover.py marketing/instagram/video/showreel.voz.json`
  y vuelve a lanzar `render_video.py`. Sale `<nombre>.mp4` completo (voz + música + subtítulos) y `<nombre>.srt`.
- Las tomas de Polly se guardan en `~/.cache/runch-tts/polly/` (por voz + texto): repetir un vídeo o cambiar `tempo`,
  efectos o animación no vuelve a pagar; solo las frases que cambian.
- Voz: Amazon Polly con la cuenta de AWS (`"voice": "polly:Lucia:generative:eu-central-1"`; también Sergio generativa, o
  Alba y Raúl `long-form` en us-east-1, que además dan el tiempo exacto de cada palabra). Unas centésimas de dólar por
  vídeo. `"tempo"` acelera la voz sin cambiar el tono. Muestras en `out/video/voces/`. Sin conexión queda Piper
  (`"voice": "es_ES-davefx-medium"`, más robótica).
- La música la compone el script (sin derechos de autor) y baja sola cuando habla la voz; volumen final a -14 LUFS.
- Para hacer uno nuevo: copia un HTML, cambia las escenas y sus tiempos en `render(t)` y ajusta `window.DURATION`.
  Deja libre el cuarto inferior de la pantalla: Instagram pone ahí el texto y los botones.
