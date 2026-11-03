# Stories de @runch.run · 4-nov → 2-dic de 2026

Vídeos de 9 s con música (1080 × 1920, listos para subir). Cada día, a las **09:00**, dos stories seguidas: primero
la de **catalán** (`_1-ca`) y después la de **castellano** (`_2-es`). Los domingos, además, a las **12:00**,
«El teu torn / Tu turno» (`_3-ca` y `_4-es`), donde tú pones la encuesta.

Carpeta: `marketing/instagram/out/stories/calendario/` (en Windows:
`\\wsl.localhost\Ubuntu\home\garrigas\personal\garmin_stats\marketing\instagram\out\stories\calendario`).
Cada vídeo tiene su póster `.png` con el mismo nombre; las hojas `hoja-semana-*.png` enseñan la semana entera.

## Lo primero: mañana, miércoles 4 de noviembre, a las 09:00

`2026-11-04_0900_1-ca.mp4` y luego `2026-11-04_0900_2-es.mp4`.

## Cómo programarlas en Meta Business Suite (cada día)

1. Abre Meta Business Suite → **Crear historia** (en el móvil: botón **+** → **Historia**).
2. Elige la cuenta de Instagram **@runch.run** (si también sale Facebook, desmárcalo).
3. **Subir** → elige los archivos del día **en orden**: primero `…_1-ca.mp4`, después `…_2-es.mp4`. Salen como dos
   historias seguidas en ese orden.
4. No añadas texto ni música: el vídeo ya lleva las dos cosas.
5. Abajo, en vez de «Compartir ahora», pulsa la flecha → **Programar** → pon la **fecha** y la **hora** de la tabla
   (hora de España) → **Programar historia**.
   Si Business Suite te pide programarlas una a una, pon la de catalán a la hora de la tabla (09:00) y la de
   castellano un minuto después (09:01): así salen siempre en ese orden.
6. Domingos: repite con `…_3-ca.mp4` y `…_4-es.mp4` a las 12:00 y, antes de programar, añade el sticker de
   **Encuesta** (ver abajo).
7. Comprueba en **Planificador** que el día tiene sus historias a la hora buena.

## Días con sticker (domingos, 12:00)

En el vídeo hay un hueco libre en medio, entre la pregunta y el botón. Abre `…_3-ca-guia.png` (o `_4-es-guia.png`):
el recuadro de rayas marca dónde va. En Business Suite: **Stickers** → **Encuesta** → escribe las dos opciones →
arrástralo al hueco. Las opciones:

- **2026-11-08** 12:00: «¿Domingo de tirada larga o de sofá?» — opciones: Tirada larga / Sofá y manta (catalán: «Diumenge de tirada llarga o de sofà?» — Tirada llarga / Sofà i manta)
- **2026-11-15** 12:00: «¿Cómo sabes que vas suave?» — opciones: Por el reloj / Porque puedo hablar (catalán: «Com saps que vas suau?» — Pel rellotge / Perquè puc parlar)
- **2026-11-22** 12:00: «¿Caminar cuenta como entreno?» — opciones: Claro que sí / Aún no me lo creo (catalán: «Caminar compta com a entreno?» — I tant que sí / Encara no m'ho crec)
- **2026-11-29** 12:00: «¿Cuándo corres mejor: mañana o tarde?» — opciones: Por la mañana / Por la tarde (catalán: «Quan corres millor: matí o vespre?» — Al matí / Al vespre)

## Notas

- **18-nov (reto):** la story anuncia el reto de las 19:00 («3 accesos beta de 3 meses · comenta en el post»).
- **19 al 25-nov:** cuenta atrás encima de la story del día («Quedan 6 días» … «¡Último día!» el 25; cierra a las 23:59).
- **26-nov:** la story de las 09:00 es provisional («Hoy: la respuesta del reto y quién se lleva los accesos beta»).
  La de la respuesta y las personas ganadoras se hace ese mismo día, después del sorteo.
- **13 y 14-nov:** «Hoy reel», con la portada del reel de las 19:00.
- **2026-11-08 10:30:** Yema: «Buenos días, runners · Corre. Desayuna. Repite.» (Vídeo de la mascota Yema, ya hecho (10 s)).
- Música: bucle propio de afro house a 120 bpm hecho por código (`marketing/marca/musica/afro_house.py`), sin
  derechos de terceros, así que Business Suite no lo silencia.
- Los textos están en `marketing/instagram/stories-calendario.json`; para cambiar uno: edítalo y ejecuta
  `uv run --no-project --with playwright --with fonttools --with numpy python marketing/instagram/stories.py <fecha>`.

## Todos los días

| Día | Hora | Archivos (en este orden) | Texto (castellano) | Nota |
|---|---|---|---|---|
| mié 4-11 | 09:00 | `2026-11-04_0900_1-ca.mp4` → `2026-11-04_0900_2-es.mp4` | Un reloj de 500 € para mirar la hora. |  |
| jue 5-11 | 09:00 | `2026-11-05_0900_1-ca.mp4` → `2026-11-05_0900_2-es.mp4` | Tienes un Garmin y no sabes qué es la Z2. |  |
| vie 6-11 | 09:00 | `2026-11-06_0900_1-ca.mp4` → `2026-11-06_0900_2-es.mp4` | Hoy no tocaban series. Tu cuerpo lo sabía. |  |
| sáb 7-11 | 09:00 | `2026-11-07_0900_1-ca.mp4` → `2026-11-07_0900_2-es.mp4` | Tu ritmo suave no es suave. Es ego. |  |
| dom 8-11 | 09:00 | `2026-11-08_0900_1-ca.mp4` → `2026-11-08_0900_2-es.mp4` | Tu HRV lleva dos noches avisando. Y tú: «hoy series». |  |
| dom 8-11 | 10:30 | `2026-11-08_1030_5-ca.mp4` → `2026-11-08_1030_6-es.mp4` | Yema: «Buenos días, runners · Corre. Desayuna. Repite.» | Vídeo de la mascota Yema, ya hecho (10 s) |
| dom 8-11 | 12:00 | `2026-11-08_1200_3-ca.mp4` → `2026-11-08_1200_4-es.mp4` | «¿Domingo de tirada larga o de sofá?» · encuesta: Tirada larga / Sofá y manta | Sticker de encuesta (ver -guia.png) |
| lun 9-11 | 09:00 | `2026-11-09_0900_1-ca.mp4` → `2026-11-09_0900_2-es.mp4` | Body Battery a 12 y tú pensando en la tirada larga. |  |
| mar 10-11 | 09:00 | `2026-11-10_0900_1-ca.mp4` → `2026-11-10_0900_2-es.mp4` | Runners que no pisan el gimnasio: tenemos que hablar. |  |
| mié 11-11 | 09:00 | `2026-11-11_0900_1-ca.mp4` → `2026-11-11_0900_2-es.mp4` | Duermes 5 horas y la culpa es de las zapatillas. |  |
| jue 12-11 | 09:00 | `2026-11-12_0900_1-ca.mp4` → `2026-11-12_0900_2-es.mp4` | Tu plan de PDF no sabe que anoche dormiste fatal. |  |
| vie 13-11 | 09:00 | `2026-11-13_0900_1-ca.mp4` → `2026-11-13_0900_2-es.mp4` | Reel · Confiesa: ¿en qué zona corres tus rodajes? | Reel a las 19:00 |
| sáb 14-11 | 09:00 | `2026-11-14_0900_1-ca.mp4` → `2026-11-14_0900_2-es.mp4` | Reel · Tu reloj sabe mucho de ti. Ya era hora de entenderlo. | Reel a las 19:00 |
| dom 15-11 | 09:00 | `2026-11-15_0900_1-ca.mp4` → `2026-11-15_0900_2-es.mp4` | Un vaso es un vaso. Un rodaje suave es un rodaje suave. |  |
| dom 15-11 | 12:00 | `2026-11-15_1200_3-ca.mp4` → `2026-11-15_1200_4-es.mp4` | «¿Cómo sabes que vas suave?» · encuesta: Por el reloj / Porque puedo hablar | Sticker de encuesta (ver -guia.png) |
| lun 16-11 | 09:00 | `2026-11-16_0900_1-ca.mp4` → `2026-11-16_0900_2-es.mp4` | Tu Z2 del Garmin no es tu Z2. |  |
| mar 17-11 | 09:00 | `2026-11-17_0900_1-ca.mp4` → `2026-11-17_0900_2-es.mp4` | «Déu n'hi do», las agujetas de ayer. |  |
| mié 18-11 | 09:00 | `2026-11-18_0900_1-ca.mp4` → `2026-11-18_0900_2-es.mp4` | Reto · Responde la pregunta en los comentarios del post y entras en el sorteo. | Día del reto |
| jue 19-11 | 09:00 | `2026-11-19_0900_1-ca.mp4` → `2026-11-19_0900_2-es.mp4` | Reto Runch · Quedan 6 días · Siempre negativo, nunca positivo. Hablamos de parciales. |  |
| vie 20-11 | 09:00 | `2026-11-20_0900_1-ca.mp4` → `2026-11-20_0900_2-es.mp4` | Reto Runch · Quedan 5 días · «Estado de VFC: desequilibrado». ¿Y ahora qué? |  |
| sáb 21-11 | 09:00 | `2026-11-21_0900_1-ca.mp4` → `2026-11-21_0900_2-es.mp4` | Reto Runch · Quedan 4 días · ¡Qué fuerte, qué fuerte! Tu HRV no baja. |  |
| dom 22-11 | 09:00 | `2026-11-22_0900_1-ca.mp4` → `2026-11-22_0900_2-es.mp4` | Reto Runch · Quedan 3 días · Caminar también es entrenar. |  |
| dom 22-11 | 12:00 | `2026-11-22_1200_3-ca.mp4` → `2026-11-22_1200_4-es.mp4` | «¿Caminar cuenta como entreno?» · encuesta: Claro que sí / Aún no me lo creo | Sticker de encuesta (ver -guia.png) |
| lun 23-11 | 09:00 | `2026-11-23_0900_1-ca.mp4` → `2026-11-23_0900_2-es.mp4` | Reto Runch · Quedan 2 días · Es el Garmin el que quiere que el runner sea el Garmin. |  |
| mar 24-11 | 09:00 | `2026-11-24_0900_1-ca.mp4` → `2026-11-24_0900_2-es.mp4` | Reto Runch · Queda 1 día · Tu plan: series a las 14:00. El tiempo: 36 grados. |  |
| mié 25-11 | 09:00 | `2026-11-25_0900_1-ca.mp4` → `2026-11-25_0900_2-es.mp4` | Reto Runch · ¡Último día! · Kilómetro 18 y, de repente: ¡fuente de mi vida! |  |
| jue 26-11 | 09:00 | `2026-11-26_0900_1-ca.mp4` → `2026-11-26_0900_2-es.mp4` | Sorteo (provisional) · La respuesta del reto y quién se lleva los accesos beta. | Hacer ese día la story real con la respuesta y las personas ganadoras |
| vie 27-11 | 09:00 | `2026-11-27_0900_1-ca.mp4` → `2026-11-27_0900_2-es.mp4` | «Un poquito de por favor» en el rodaje en grupo. |  |
| sáb 28-11 | 09:00 | `2026-11-28_0900_1-ca.mp4` → `2026-11-28_0900_2-es.mp4` | No empieces corriendo 5 km. Empieza trotando 1 minuto. |  |
| dom 29-11 | 09:00 | `2026-11-29_0900_1-ca.mp4` → `2026-11-29_0900_2-es.mp4` | «Excelente.» Estado de entrenamiento: Productivo. |  |
| dom 29-11 | 12:00 | `2026-11-29_1200_3-ca.mp4` → `2026-11-29_1200_4-es.mp4` | «¿Cuándo corres mejor: mañana o tarde?» · encuesta: Por la mañana / Por la tarde | Sticker de encuesta (ver -guia.png) |
| lun 30-11 | 09:00 | `2026-11-30_0900_1-ca.mp4` → `2026-11-30_0900_2-es.mp4` | Tu VO2máx del Garmin no es tu VO2máx. |  |
| mar 1-12 | 09:00 | `2026-12-01_0900_1-ca.mp4` → `2026-12-01_0900_2-es.mp4` | −1000 de aura: pausar en un semáforo y no volver a darle al play. |  |
| mié 2-12 | 09:00 | `2026-12-02_0900_1-ca.mp4` → `2026-12-02_0900_2-es.mp4` | Tu reloj habla raro. Aquí va el diccionario. |  |
