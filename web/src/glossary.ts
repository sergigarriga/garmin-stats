/** Explicaciones sencillas de cada métrica para los "?" de la web. */
export interface HelpEntry { title: string; body: string; good?: string }

export const GLOSSARY = {
  steps: {
    title: 'Pasos',
    body: 'Los pasos que das en el día, contados por el reloj. El objetivo lo ajusta Garmin cada día según lo que sueles caminar.',
    good: 'Entre 7.000 y 10.000 al día es una buena referencia para la salud.',
  },
  sleep: {
    title: 'Sueño',
    body: 'El tiempo que has estado dormido de verdad, sin contar los ratos despierto en la cama.',
    good: 'Los adultos necesitan entre 7 y 9 horas.',
  },
  sleepScore: {
    title: 'Puntuación de sueño',
    body: 'Nota de 0 a 100 que resume tu noche: cuánto has dormido, cuánto sueño profundo y REM has tenido, cuántas veces te has despertado y lo relajado que estaba tu cuerpo.',
    good: '80 o más es excelente, de 60 a 79 está bien y por debajo de 60 se puede mejorar.',
  },
  sleepStages: {
    title: 'Fases del sueño',
    body: 'Profundo: el cuerpo se repara. REM: el cerebro ordena recuerdos y emociones (es cuando sueñas). Ligero: la transición entre fases. Despierto: pequeños despertares, casi siempre sin recordarlos.',
    good: 'Una noche típica tiene un 13-23 % de profundo y un 20-25 % de REM.',
  },
  schedule: {
    title: 'Horario de sueño',
    body: 'A qué hora te duermes y te despiertas. Al cuerpo le sienta bien la rutina: un horario estable mejora la calidad del sueño aunque duermas las mismas horas.',
    good: 'Intenta acostarte y levantarte a la misma hora (±30 min), también el fin de semana.',
  },
  weekday: {
    title: 'Sueño según el día',
    body: 'Cuánto duermes de media según el día en que te despiertas. Sirve para ver si entre semana acumulas falta de sueño.',
  },
  bodyBattery: {
    title: 'Body Battery',
    body: 'Tu "batería" de energía, de 0 a 100. Se carga mientras duermes y descansas, y se gasta con la actividad, el estrés y la falta de sueño.',
    good: 'Lo ideal es levantarte por encima de 70 y no bajar de 20 durante el día.',
  },
  rhr: {
    title: 'FC en reposo',
    body: 'Los latidos por minuto cuando estás totalmente relajado, normalmente mientras duermes. Con buena forma física el corazón bombea más por latido y late más despacio.',
    good: 'Fíjate en tu tendencia: si sube 5 lpm o más durante unos días, puede ser cansancio, un resfriado que empieza, alcohol o poco sueño.',
  },
  hrv: {
    title: 'HRV (variabilidad del pulso)',
    body: 'Cuánto varía el tiempo entre un latido y el siguiente mientras duermes. Una HRV alta indica que tu cuerpo está descansado y preparado; baja tras el estrés, el alcohol, la enfermedad o los entrenos duros.',
    good: 'Es muy personal: compárala solo contigo. La banda gris es tu rango normal según Garmin.',
  },
  stress: {
    title: 'Estrés',
    body: 'Nivel de 0 a 100 calculado con tu pulso y tu HRV. No mide emociones: mide cuánto trabaja tu sistema nervioso (preocupaciones, cafeína, digestión, cansancio...).',
    good: '0-25 descanso, 26-50 bajo, 51-75 medio y 76-100 alto.',
  },
  intensity: {
    title: 'Minutos de intensidad',
    body: 'El tiempo que te mueves con algo de esfuerzo: moderado (caminar rápido) o vigoroso (correr, subir cuestas). Los vigorosos cuentan doble.',
    good: 'La OMS recomienda al menos 150 minutos a la semana.',
  },
  calActive: {
    title: 'Calorías activas',
    body: 'Las calorías que gastas al moverte, sin contar las que tu cuerpo quema en reposo para funcionar.',
  },
  vo2max: {
    title: 'VO2max',
    body: 'La cantidad máxima de oxígeno que tu cuerpo puede usar al hacer ejercicio, en ml por kilo y minuto. Es el mejor indicador de tu forma aeróbica. El reloj la estima en cada carrera con el pulso y el ritmo.',
    good: 'Sube con entreno constante y baja tras 3-4 semanas de parón. Por encima de 50 es una forma muy buena.',
  },
  ctl: {
    title: 'Forma física y fatiga',
    body: 'Forma (CTL): tu carga de entreno media de las últimas 6 semanas; refleja lo preparado que estás. Fatiga (ATL): la de los últimos 7 días; refleja lo cansado que estás ahora.',
    good: 'Cuando la fatiga queda por debajo de la forma, estás fresco para rendir.',
  },
  acwr: {
    title: 'Ratio de carga (ACWR)',
    body: 'Compara lo que has entrenado esta semana con tu media del último mes. Sirve para detectar subidas bruscas, que son la causa más común de lesiones.',
    good: 'Entre 0,8 y 1,3 es seguro. Por encima de 1,5 has subido demasiado de golpe.',
  },
  zones: {
    title: 'Zonas de pulso',
    body: 'Rangos de intensidad según tu pulso máximo. Z1 muy suave, Z2 suave (puedes hablar con frases completas), Z3 moderado, Z4 umbral (cuesta hablar) y Z5 máximo.',
    good: 'Para ganar fondo, haz alrededor del 80 % del tiempo en Z1-Z2.',
  },
  ef: {
    title: 'Eficiencia aeróbica',
    body: 'Los metros que avanzas por minuto por cada latido. Si sube con el tiempo, corres más rápido con el mismo esfuerzo del corazón.',
    good: 'Compárala solo contigo, y mejor entre carreras parecidas (mismo terreno y tipo de rodaje).',
  },
  trimp: {
    title: 'Carga (TRIMP)',
    body: 'Puntos que mide cada entreno combinando cuánto dura y lo alto que va tu pulso. Una hora suave suma menos que 30 minutos muy intensos.',
    good: 'Un rodaje suave de 45 minutos suele estar entre 50 y 70.',
  },
  volume: {
    title: 'Volumen de entreno',
    body: 'El tiempo total que entrenas cada semana, separado por deporte.',
    good: 'Mejor subir poco a poco: como máximo un 10 % más por semana.',
  },
  km: {
    title: 'Kilómetros por semana',
    body: 'La distancia que corres cada semana, en exterior y en cinta.',
  },
  predictions: {
    title: 'Predicciones de carrera',
    body: 'El tiempo que podrías hacer en cada distancia según tu VO2max actual (fórmula de Daniels). Es tu potencial si entrenas esa distancia, no una garantía.',
    good: 'Suele ser optimista en media maratón y maratón si no haces tiradas largas.',
  },
  readiness: {
    title: 'Preparación',
    body: 'Una nota de 0 a 100 que dice lo listo que está tu cuerpo hoy. Compara tu HRV, tu sueño, tu pulso en reposo y tu carga de entreno reciente con lo que es normal para ti (tus últimas 28 mediciones).',
    good: '80 o más: día para entrenar fuerte. 60-79: entreno normal. 40-59: suave. Menos de 40: descanso.',
  },
  relation: {
    title: 'Fuerza de la relación',
    body: 'Indica lo a menudo que dos cosas van juntas en tus datos. Para calcularlo se dividen tus días en tres grupos según la primera y se compara la media de la segunda en cada grupo.',
    good: '●●● fuerte, ●●○ clara, ●○○ débil. Que dos cosas vayan juntas no demuestra que una cause la otra.',
  },
  coverage: {
    title: 'Días con reloj',
    body: 'En cuántos días hay datos del reloj (pulso en reposo). Si no lo llevas puesto o no lo sincronizas, ese día queda vacío y las medias son menos fiables.',
  },
  aiUsage: {
    title: 'Uso de la IA',
    body: 'Claude Sonnet 5.5 escribe los textos de la app y responde al chat; Claude Opus 5.5, el modelo más capaz, diseña y reajusta tu plan de entreno. Se cobra por tokens: trozos de texto de unas ¾ partes de una palabra. Solo se llama cuando hay datos nuevos, y como mucho 3 veces al día.',
    good: 'Presupuesto de 50 $ al mes. Si un mes llega a 40 $, la app pasa sola a Haiku 5.5, un modelo mucho más barato.',
  },
} satisfies Record<string, HelpEntry>;

export type HelpKey = keyof typeof GLOSSARY;
