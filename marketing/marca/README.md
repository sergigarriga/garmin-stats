# Marca Runch: capa ilustrada

Runch tiene dos sistemas visuales que comparten paleta y tono:

| | Editorial (`marketing/instagram/`) | Ilustrado (esta carpeta) |
|---|---|---|
| Para qué | Datos de la app, explicaciones, carruseles (Z2, HRV, ritmos) | Quedadas, retos y sorteos, avisos, merchandising, momentos de comunidad |
| Letra | Fraunces (titulares) + Google Sans Flex | Logotipo y titulares en Gluten + Google Sans Flex para textos |
| Recursos | Gráficos de línea fina, maqueta fija «Nº 01 · TEMA» | Logotipo «runch», lemas, patrón del logotipo, hueco para ilustración |
| Color | Crema, papel, espresso, olivo (+ lavanda, pistacho, mar, mantequilla, salvia) | Los mismos, pero **una sola tinta** por pieza |

Regla rápida: si el post enseña un dato o explica algo, editorial. Si invita a venir, a participar o a llevar
algo puesto, ilustrado. En un mismo carrusel no se mezclan.

Resumen visual: `runch-brand-sheet.png`.

## Logotipo

`logo/`: «runch» en minúsculas, letras gordas y redondas que se tocan y bailan un poco sobre la línea base. Está
dibujado con trazados (no depende de tener la fuente instalada).

- `runch-logo-olivo|crema|espresso.svg/.png`: olivo sobre crema (principal), crema sobre olivo y espresso sobre crema.
- `runch-logo-terracota.svg/.png`: **legado**, del color anterior. No se regenera; se queda porque lo usan las piezas
  editoriales ya programadas y la web (que tiene su propia copia).
- `runch-lema-run-and-brunch|corre-recupera-repite|club-de-running.svg/.png`: logotipo con lema pequeño en mayúsculas.
- `runch-sello.svg/.png`: sello redondo (pegatina, parche, avatar de eventos).

Sí: una sola tinta sobre fondo liso y con buen contraste. No: estirarlo, degradados, varias tintas, solo contorno,
ponerlo sobre fotos con mucho detalle.

## Paleta

El color de marca es **olivo**. Es el mismo sistema que la app (`web/index.html` y `web/src/brand/colors.ts`) y
está en `C` dentro de `kit.py`; en el código se usa siempre `C["brand"]`, no el nombre del color.

| Color | Hex | Para qué |
|---|---|---|
| Olivo | `#5A6B32` (oscuro `#46542A`, claro `#B4C784`) | Marca: logotipo, botones, tinta principal. El claro, sobre fondo oscuro |
| Lavanda | `#8B6FD6` (tinta `#6B4FC0`, claro `#C9B8F5`) | Acento: sección Salud de la app; fondos con crema encima |
| Pistacho | `#9DB43A` (tinta `#5F7414`, claro `#CFE07A`) | Acento: sección Entreno; fondos con espresso encima |
| Mar | `#24496D` (claro `#9CC2E6`) | Acento: sección Análisis; fondos con crema o mantequilla encima |
| Crema | `#F7F3EC` | Fondo principal y tinta sobre olivo, lavanda, mar y espresso |
| Papel | `#FCFAF6` | Tarjetas sobre crema |
| Espresso | `#221A15` | Texto; fondo oscuro |
| Mantequilla | `#F1DEA6` | Fondo cálido (citas, bolsas) |
| Salvia | `#CBD3B8` | Secundario suave |

Fondo de la app en modo claro: `#F6F4EE`. Combinaciones de tinta y fondo: olivo/crema (principal), crema/olivo,
espresso/crema, crema/lavanda, espresso/pistacho, mantequilla/mar, espresso/mantequilla. No: olivo sobre pistacho o
salvia (poco contraste), ni dos tintas en la misma pieza.

Terracota `#D4542F` era el color anterior. Se queda en `kit.py` solo porque lo usan las piezas editoriales ya
programadas (`marketing/instagram/`); los archivos `*-terracota*` de esta carpeta son legado.

## Patrón

`patrones/patron-logo-baldosa.svg` es la pieza que se repite (filas en ladrillo, la segunda desplazada media pieza).
Las versiones 1080 x 1350 van inclinadas -8° en seis combinaciones: crema sobre olivo, olivo sobre crema, espresso
sobre pistacho, crema sobre lavanda, mantequilla sobre mar y crema sobre espresso (`patron-logo-crema-sobre-terracota`,
`-terracota-sobre-crema` y `-espresso-sobre-salvia` son legado). Sirve para fondos, cajas, bolsas,
interiores de packaging y huecos de plantilla.

## Plantillas de Instagram

`plantillas/`: post (1080 x 1350) e historia (1080 x 1920) para quedada, reto, «Tu turno» y cita. Cada una tiene
**una sola pieza protagonista**, muy grande y en Gluten, y lo demás se queda pequeño a su alrededor:

| Plantilla | Color | Protagonista | Acompaña |
|---|---|---|---|
| Quedada | Crema sobre olivo | La hora («9:00») con contorno de eco | «DOMINGO» en mayúsculas, sello «RITMO Z2 · NADIE SE QUEDA ATRÁS» |
| Reto | Olivo sobre crema | «3» gigante + «accesos beta» | Pegatina «de 3 meses», sello «SORTEO» |
| Tu turno | Crema sobre lavanda | La pregunta, con «después» en pegatina | Respuestas en etiquetas rellenas, sello «TE LEEMOS» |
| Cita | Espresso sobre mantequilla | La frase, con «despacio» subrayado en ola | Comilla « gigante, sello «EL CLUB · CADA DOMINGO» |

Piezas comunes: sello redondo con texto alrededor y una margarita en el centro, etiquetas rellenas (tinta de fondo,
texto del color del fondo), piezas un poco giradas para que no quede rígido, y una ilustración grande y suelta,
sin caja, en la tinta de la plantilla (crema sobre olivo y lavanda; olivo sobre crema; espresso sobre
mantequilla): en quedada y reto, el corredor con gorra (`corredor-1`) llega corriendo encima del «9:00» o del «3»;
en «Tu turno» y cita, la corredora con la taza (`corredor-2`), junto a las respuestas o al pie de la frase.

**Regla: carrusel bilingüe.** Todas las plantillas ilustradas se publican siempre como carrusel de dos diapositivas
con el mismo diseño: la 1 en catalán y la 2 en castellano. Por eso cada pieza sale dos veces:

- `<post|story>-<nombre>-1-ca.png` y `<post|story>-<nombre>-2-es.png`: listas para usar.
- Una plantilla sin ilustración (`"ilustracion": None`) lleva un hueco con el patrón y saca además
  `<post|story>-<nombre>-hueco.png`, el hueco marcado con sus medidas.
- `<post|story>-<nombre>-1-ca.mp4` y `-2-es.mp4`: la misma pieza animada (los vídeos actuales siguen en terracota:
  se rehacen con `templates.py` sin `--sin-video`), 6 s, 30 fps, sin sonido, H.264 (yuv420p), ~1-1,5 MB.
  El corredor entra corriendo desde la izquierda, se queda botando 3 px a ritmo de zancada (~170 pasos/min) y al
  final sale por la derecha; la corredora de la taza sube desde abajo y se mece despacio. La protagonista entra con
  un pequeño rebote, el sello entra girando y luego gira despacio, las etiquetas suben una a una, el subrayado se
  dibuja y el logotipo hace una ola dos veces. Todo se queda quieto unos 3 s y al final se funde, así el primer y el
  último fotograma coinciden y el vídeo se repite sin salto.
- `<post|story>-<nombre>-<n>-<idioma>-frames.png`: hoja con 6 fotogramas del vídeo para revisarlo sin abrirlo.

Los textos están en `TEXTS` dentro de `templates.py`, un diccionario por idioma (`"ca"`, `"es"`) con los mismos
campos en los dos; `LANGS` fija el orden del carrusel. Catalán normativo y natural, no una traducción palabra por
palabra (p. ej. «Diumenge», «Ningú es queda enrere», «Repte», «El teu torn», «Córrer a poc a poc també és córrer»).
La ilustración de cada plantilla se elige en `TEMPLATES` (`"ilustracion": "corredor-1"`; la tinta sale del tema,
`INK_FILE`) y sus medidas están en `ILLUS`;
la colocación de cada pieza está en su función (`quedada`, `reto`, `tu_turno`, `cita`). Las historias dejan libres
los 250 px de arriba y los 300 de abajo (ahí Instagram pone sus botones); el script avisa si algo se sale.

## Ilustración

`ilustraciones/gemini/`: corredor con gorra en zancada (`corredor-1`) y corredora con la taza (`corredor-2`), en
olivo, crema y espresso (y terracota, legado), PNG con fondo transparente (la piel y los huecos son transparentes: dejan ver el
fondo, efecto duotono). Pautas para los siguientes personajes: línea continua de grosor uniforme y puntas redondas, una
sola tinta del color de la plantilla, fondo transparente, poco detalle, ojos cerrados o sonrientes, cuerpos y ritmos
de todo tipo, escenas de correr y de después de correr (estirar, taza en la mano, grupo). Nada de marcas ni
locales reconocibles.

## Maquetas

`mockups/`: cajas apiladas, bolsas de tela (cruda y lavanda), camisetas, gorra, botella, hoja de pegatinas y móvil con
una historia y un post. Usan los acentos de fondo para que la marca tenga ritmo, pero cada pieza lleva una sola tinta. Son escenas planas dibujadas con código, sin fotos.

## Generar

```bash
cd marketing/marca
uv run --no-project --with pillow python build.py ilustraciones              # 1: versiones en olivo de las ilustraciones
uv run --no-project --with playwright --with fonttools python templates.py   # 2: el móvil y la hoja usan las plantillas
#   templates.py --sin-video   solo PNG (no borra los vídeos) · templates.py quedada   solo una plantilla (ffmpeg para los MP4)
uv run --no-project --with playwright --with fonttools --with pillow python build.py   # 3: logo, patrones, mockups, hoja
```

`build.py logo patrones` genera solo esas partes (`ilustraciones`, `logo`, `patrones`, `mockups`, `hoja`). `kit.py` tiene la paleta, el logotipo y el render a PNG.

## Fuente

Gluten (Etcetera Type Co), SIL Open Font License 1.1: `fonts/Gluten[slnt,wght].ttf` y `fonts/OFL-Gluten.txt`.
El logotipo usa el peso 820 sin inclinación, con giros y espacios propios por letra.
