// All the text of the landing page, in one place. Edit copy here; the section
// components only lay it out.
//
// Rules this copy follows (CLAUDE.md §4, UX-DESIGN-SYSTEM-001 §16):
//  - Freyja never promises profit or safety. No "gana", "rentable", "sin riesgo".
//  - Nothing is presented as available before it exists: every item is tagged
//    "Disponible" or "Próximamente".
//  - No invented numbers, testimonials or reviews. Figures are facts about the
//    product today; update them here when they change.
//  landing.content.spec.ts enforces the wording rules.

export type Availability = 'now' | 'soon';

export interface Feature {
  title: string;
  text: string;
  availability: Availability;
}

export const NAV_LINKS = [
  { label: 'Cómo funciona', href: '#como-funciona' },
  { label: 'Datos y calidad', href: '#datos-y-calidad' },
  { label: 'Preguntas', href: '#preguntas' },
] as const;

export const HERO = {
  eyebrow: 'Análisis de mercado con datos verificables',
  title: 'Entiende el mercado antes de operar.',
  lead: 'Freyja reúne las velas del mercado con su origen, su frescura y su calidad siempre a la vista, para que cada decisión parta de datos que puedes comprobar.',
  primaryCta: 'Crear cuenta',
  secondaryCta: 'Ver cómo funciona',
  note: 'Sin promesas de rentabilidad. Solo datos claros.',
  assurances: ['Hora UTC explícita', 'Solo velas cerradas', 'Cada dato con su origen'],
} as const;

/** Facts about the product today (not performance figures). */
export const FACTS = [
  { value: '4', label: 'pares cripto disponibles hoy' },
  { value: '5', label: 'periodos de vela activos (1m a 4h)' },
  { value: '100 %', label: 'velas cerradas, nunca en curso' },
  { value: '0', label: 'datos de ejemplo mostrados como reales' },
] as const;

export const PROBLEMS = {
  eyebrow: 'El problema',
  title: 'Operar con datos dudosos sale caro',
  lead: 'La mayoría de errores de análisis no vienen de la estrategia, sino de fiarse de un dato que no era lo que parecía.',
  items: [
    {
      title: 'Datos viejos que parecen actuales',
      text: 'Un gráfico que no dice cuándo se actualizó invita a decidir sobre el pasado sin saberlo.',
    },
    {
      title: 'Velas que aún no han cerrado',
      text: 'Usar una vela en curso como si estuviera cerrada distorsiona cualquier lectura del mercado.',
    },
    {
      title: 'Cada broker cotiza distinto',
      text: 'El precio de una fuente no es el de otra. Mezclarlos da resultados que nadie puede reproducir.',
    },
    {
      title: 'Señales sin explicación',
      text: 'Si no sabes por qué aparece una señal, no puedes confiar en ella ni corregirla.',
    },
  ],
} as const;

export const BENEFITS = {
  id: 'datos-y-calidad',
  eyebrow: 'La solución',
  title: 'Datos que se explican solos',
  lead: 'Freyja pone a la vista lo que otros esconden: de dónde viene cada dato, qué tan reciente es y qué le falta.',
  items: [
    {
      title: 'Procedencia en cada dato',
      text: 'Fuente, hora de recepción y calidad de cada serie, siempre junto al gráfico.',
      availability: 'now',
    },
    {
      title: 'Frescura y huecos a la vista',
      text: 'Ves cuánto hace que cerró la última vela y dónde faltan. Un dato viejo nunca se presenta como actual.',
      availability: 'now',
    },
    {
      title: 'Solo velas cerradas',
      text: 'La vela en curso se excluye y se avisa, para que ningún análisis use información incompleta.',
      availability: 'now',
    },
    {
      title: 'El periodo lo eliges tú',
      text: 'Hoy de 1 minuto a 4 horas, con 1 minuto por defecto. Segundos y periodos más largos están previstos.',
      availability: 'now',
    },
    {
      title: 'Tu cuenta es solo tuya',
      text: 'Los datos de mercado son comunes; lo tuyo queda aislado y nadie más lo ve.',
      availability: 'now',
    },
    {
      title: 'Señales explicadas y simulación DEMO',
      text: 'Cada señal con la evidencia que la produjo, y práctica en DEMO antes de cualquier operativa real.',
      availability: 'soon',
    },
  ] satisfies readonly Feature[],
} as const;

export const HOW_IT_WORKS = {
  id: 'como-funciona',
  eyebrow: 'Cómo funciona',
  title: 'Tres pasos, sin claves de broker',
  steps: [
    {
      title: 'Crea tu cuenta',
      text: 'Solo necesitas un correo y una contraseña. No se pide ninguna clave de broker para explorar.',
      availability: 'now',
    },
    {
      title: 'Explora el mercado',
      text: 'Elige un instrumento y un periodo. Verás las velas cerradas con su fuente, su frescura y su calidad.',
      availability: 'now',
    },
    {
      title: 'Analiza con criterio',
      text: 'Señales explicadas, simulación en DEMO y pruebas históricas reproducibles, cuando estén listas.',
      availability: 'soon',
    },
  ] satisfies readonly Feature[],
} as const;

export const USE_CASES = {
  eyebrow: 'Casos de uso',
  title: 'Qué puedes hacer con Freyja',
  items: [
    {
      title: 'Revisar el histórico de un par cripto',
      text: 'Recorre las velas guardadas y carga tramos anteriores cuando los necesites.',
      availability: 'now',
    },
    {
      title: 'Comparar periodos',
      text: 'Cambia de 1 minuto a 4 horas sin perder el instrumento; el enlace guarda tu vista.',
      availability: 'now',
    },
    {
      title: 'Comprobar la calidad antes de fiarte',
      text: 'Detecta huecos, retrasos y fallos de la fuente antes de tomar una decisión.',
      availability: 'now',
    },
    {
      title: 'Simular una estrategia en DEMO',
      text: 'Prueba reglas con dinero ficticio y resultados que se pueden reproducir.',
      availability: 'soon',
    },
    {
      title: 'Probar una idea sobre datos pasados',
      text: 'Backtesting con comisiones, spread y calidad de datos, sin conclusiones infladas.',
      availability: 'soon',
    },
  ] satisfies readonly Feature[],
} as const;

export const PRINCIPLES = {
  eyebrow: 'Nuestros compromisos',
  title: 'Lo que Freyja no hará nunca',
  items: [
    {
      title: 'No prometer rentabilidad',
      text: 'No afirmamos que una estrategia sea rentable o segura sin evidencia estadística suficiente.',
    },
    {
      title: 'No mostrar datos de ejemplo como reales',
      text: 'Sin datos, verás un estado vacío, no un gráfico decorativo.',
    },
    {
      title: 'No aceptar claves con permiso de retirada',
      text: 'Cuando conectes un broker, solo se admitirán claves que no puedan sacar dinero.',
    },
    {
      title: 'No operar en real hasta validarlo',
      text: 'La ejecución real está bloqueada hasta superar los requisitos técnicos, de seguridad y de validación.',
    },
  ],
} as const;

export const FAQ = {
  id: 'preguntas',
  eyebrow: 'Preguntas frecuentes',
  title: 'Antes de empezar',
  items: [
    {
      question: '¿Freyja opera por mí?',
      answer:
        'Hoy no. Freyja muestra datos y calidad del mercado. La ejecución real está bloqueada y solo se habilitará tras superar los requisitos técnicos, de seguridad y de validación; antes llegará un modo DEMO.',
    },
    {
      question: '¿Puedo esperar resultados concretos?',
      answer:
        'No, y desconfía de quien te los prometa. Operar con instrumentos financieros conlleva riesgo de pérdida. Freyja no es asesoramiento financiero.',
    },
    {
      question: '¿De dónde salen los datos?',
      answer:
        'Hoy, de la API pública de Binance para pares cripto al contado. Cada serie indica su fuente. Otras fuentes y brokers se irán añadiendo, cada una identificada por separado.',
    },
    {
      question: '¿Y si los datos llegan con retraso?',
      answer:
        'Se ve. La serie aparece como «Desactualizado» y se indica cuánto hace que cerró la última vela. Un dato antiguo nunca se presenta como actual.',
    },
    {
      question: '¿Tengo que conectar mi broker?',
      answer:
        'No para explorar el mercado. Cuando exista esa opción, nunca se aceptarán claves con permiso de retirada.',
    },
    {
      question: '¿Mis datos son privados?',
      answer:
        'Cada persona tiene su propia cuenta y sesión. Los datos de mercado son comunes; lo que sea tuyo queda aislado y solo tú lo ves.',
    },
  ],
} as const;

export const FINAL_CTA = {
  title: 'Empieza por entender.',
  text: 'Crea tu cuenta y explora velas reales con su calidad a la vista.',
  primaryCta: 'Crear cuenta',
  secondaryCta: 'Ya tengo cuenta',
} as const;

export const FOOTER = {
  tagline: 'Trading inteligente, explicado de forma sencilla.',
  risk: 'Operar con instrumentos financieros conlleva riesgo de pérdida, incluida la totalidad del capital. Freyja muestra datos y análisis; no es asesoramiento financiero ni garantiza resultados.',
} as const;
