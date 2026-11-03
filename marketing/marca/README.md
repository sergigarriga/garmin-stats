# Marca Runch: capa ilustrada

Runch tiene dos sistemas visuales que comparten paleta y tono:

| | Editorial (`marketing/instagram/`) | Ilustrado (esta carpeta) |
|---|---|---|
| Para qué | Datos de la app, explicaciones, carruseles (Z2, HRV, ritmos) | Quedadas, retos y sorteos, avisos, merchandising, momentos de comunidad |
| Letra | Fraunces (titulares) + Google Sans Flex | Logotipo y titulares en Gluten + Google Sans Flex para textos |
| Recursos | Gráficos de línea fina, maqueta fija «Nº 01 · TEMA» | Logotipo «runch», lemas, patrón del logotipo, hueco para ilustración |
| Color | Crema, papel, espresso, terracota (+ salvia, mar, mantequilla) | Los mismos, pero **una sola tinta** por pieza |

Regla rápida: si el post enseña un dato o explica algo, editorial. Si invita a venir, a participar o a llevar
algo puesto, ilustrado. En un mismo carrusel no se mezclan.

Resumen visual: `runch-brand-sheet.png`.

## Logotipo

`logo/`: «runch» en minúsculas, letras gordas y redondas que se tocan y bailan un poco sobre la línea base. Está
dibujado con trazados (no depende de tener la fuente instalada).

- `runch-logo-terracota|crema|espresso.svg/.png`: terracota sobre crema (principal), crema sobre terracota y espresso.
- `runch-lema-run-and-brunch|corre-recupera-repite|club-de-running.svg/.png`: logotipo con lema pequeño en mayúsculas.
- `runch-sello.svg/.png`: sello redondo (pegatina, parche, avatar de eventos).

Sí: una sola tinta sobre fondo liso y con buen contraste. No: estirarlo, degradados, varias tintas, solo contorno,
ponerlo sobre fotos con mucho detalle.

## Paleta

Terracota `#D4542F` · Crema `#F7F3EC` · Papel `#FCFAF6` · Espresso `#221A15` · Salvia `#CBD3B8` · Mar `#24496D` ·
Mantequilla `#F1DEA6`. Combinaciones de tinta y fondo: terracota/crema (principal), crema/terracota,
espresso/salvia, espresso/mantequilla, crema/espresso.

## Patrón

`patrones/patron-logo-baldosa.svg` es la pieza que se repite (filas en ladrillo, la segunda desplazada media pieza).
Las versiones 1080 x 1350 van inclinadas -8° en cuatro combinaciones de color. Sirve para fondos, cajas, bolsas,
interiores de packaging y huecos de plantilla.

## Plantillas de Instagram

`plantillas/`: post (1080 x 1350) e historia (1080 x 1920) para quedada, reto, «Tu turno» y cita. Cada una tiene un
hueco para una ilustración:

- `<post|story>-<nombre>.png`: lista para usar, el hueco lleva el patrón.
- `<post|story>-<nombre>-hueco.png`: el hueco marcado con sus medidas (920 x 580 en post, 920 x 760 en historia).

Los textos y las ilustraciones se cambian en `TEMPLATES` dentro de `templates.py` (`"ilustracion": "ruta.png"`).
Las historias dejan libres los 250 px de arriba y los 300 de abajo (ahí Instagram pone sus botones).

## Ilustración (pendiente)

Los personajes se harán aparte. Pautas para que encajen: línea continua de grosor uniforme y puntas redondas, una
sola tinta del color de la plantilla, fondo transparente, poco detalle, ojos cerrados o sonrientes, cuerpos y ritmos
de todo tipo, escenas de correr y de después de correr (estirar, taza en la mano, grupo). Nada de marcas ni
locales reconocibles.

## Maquetas

`mockups/`: cajas apiladas, bolsas de tela, camisetas, gorra, botella, hoja de pegatinas y móvil con una historia y
un post. Son escenas planas dibujadas con código, sin fotos.

## Generar

```bash
cd marketing/marca
uv run --no-project --with playwright --with fonttools python templates.py   # primero: el móvil y la hoja las usan
uv run --no-project --with playwright --with fonttools python build.py       # logo, patrones, mockups, hoja
```

`build.py logo patrones` genera solo esas partes. `kit.py` tiene la paleta, el logotipo y el render a PNG.

## Fuente

Gluten (Etcetera Type Co), SIL Open Font License 1.1: `fonts/Gluten[slnt,wght].ttf` y `fonts/OFL-Gluten.txt`.
El logotipo usa el peso 820 sin inclinación, con giros y espacios propios por letra.
