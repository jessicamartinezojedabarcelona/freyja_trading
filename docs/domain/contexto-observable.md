# Contexto observable de mercado (v1)

- **Estado:** vigente. Versión del contexto `context-v1`; calendario `forex-sessions-v1`.
- **Fecha:** 2026-09-25
- **Tarea:** POINT2-CONTEXT-001 (3 de 7 del punto 2).
- **Depende de:** [estructura-de-precio.md](estructura-de-precio.md) (profundidad mínima) y
  [contexto-y-tendencia.md](contexto-y-tendencia.md) (contrato).
- **Implementación:** `backend/src/freyja_backend/domain/market_context.py` y
  `market_calendar.py`. Puras, sin BD, red ni reloj. No hay API ni interfaz todavía.

El contexto observable es **todo lo que se puede saber de una serie antes de clasificar
su tendencia**, en un instante. No dice nada de dirección y **no decide si existe una
señal**.

## 1. Qué contiene

| Campo | Contenido |
| ----- | --------- |
| `observed_at` | Instante (UTC) en que se observa. |
| `instrument_id`, `product_type` | Instrumento y producto. |
| `signal_timeframe`, `context_timeframe` | Los dos marcos. El de contexto **no es más fino** que el de señal; si lo es, es un error de petición, no de datos. |
| `last_closed_candle_at` | Cierre de la última vela **cerrada** de la serie de contexto (`None` si no hay). |
| `data_source` | Fuente de las velas. |
| `data_freshness` | `FRESH`, `STALE`, `NO_DATA` o `UNKNOWN` (no se puede juzgar). |
| `market_open` | `True`/`False`, o `None` si el horario se desconoce. |
| `market_session` | Solo Forex (sección 3). `None` = «no aplica», nunca una sesión prestada. |
| `timezone` | Siempre `UTC`. |
| `data_quality_status` | `OK`, `DEGRADED` o `UNAVAILABLE`, de la ventana evaluada. |
| `missing_data_reasons` | Motivos por los que el contexto es insuficiente (sección 4). Vacío = suficiente. |
| `weekday_utc`, `hour_utc` | Día de la semana y hora en UTC. Siempre se registran. |
| `window_candles`, `calendar_version`, `context_version` | Velas evaluadas y versiones de lo que las evaluó. |

Un contexto es **suficiente** solo si `missing_data_reasons` está vacío.

## 2. Reglas de honestidad

1. **Nunca usa la vela abierta.** Toda vela que no haya cerrado en `observed_at` se
   ignora; una que cierra exactamente en `observed_at` sí cuenta.
2. **Nunca reutiliza en silencio el último contexto válido.** La función no tiene
   estado ni caché: cada llamada responde solo con las velas que recibe. Los mismos
   datos una hora después ya no cuentan como actuales, y el contexto anterior no se
   toca.
3. **Datos malos no lanzan errores: dan un contexto insuficiente** con sus motivos.
   Solo una petición mal formada (marcos incoherentes, `observed_at` sin zona UTC,
   historial mínimo < 1) lanza excepción.
4. **Sin decisión de señal:** el contexto no contiene ningún campo de dirección,
   tendencia, señal ni recomendación (hay una prueba que lo guarda).

## 3. Mercados y horarios

Cada serie tiene un **horario** (`MarketSchedule`) que dice cuándo se esperan velas:

| Horario | Mercado | `market_open` | `market_session` |
| ------- | ------- | ------------- | ---------------- |
| `CONTINUOUS_24_7` | Cripto | siempre `True` | `None`; solo día y hora UTC, **sin inventar sesiones oficiales** |
| `FOREX_WEEKLY` | Forex | según el calendario | `ASIA`, `LONDON`, `NEW_YORK`, `OVERLAP_LONDON_NEW_YORK` o `CLOSED` |
| `BROKER_DEFINED` | Instrumentos cuyo horario fija el broker (p. ej. OTC) | `None` | `None` |

### Calendario Forex `forex-sessions-v1`

Una **convención**, no un horario oficial (nadie publica uno para el Forex al contado);
por eso está versionado. Se calcula con la hora local de Nueva York y de Londres, así que
el cambio de hora lo aplica la base de datos horaria IANA (dependencia `tzdata`), no
desfases escritos a mano.

- **Semana:** abre el domingo a las 17:00 y cierra el viernes a las 17:00, hora de
  Nueva York (inicio incluido, fin excluido). El resto es `CLOSED`.
- **Londres:** 08:00–17:00 hora de Londres. **Nueva York:** 08:00–17:00 hora de Nueva York.
- **Sesión:** ambas abiertas → `OVERLAP_LONDON_NEW_YORK`; solo Londres → `LONDON`; solo
  Nueva York → `NEW_YORK`; mercado abierto y ninguna de las dos → `ASIA` (las horas
  entre el cierre de Nueva York y la apertura de Londres, en que lidera Asia-Pacífico).

Ejemplos (UTC): invierno, Londres 08–17 y Nueva York 13–22 ⇒ solapamiento 13–17; verano,
Londres 07–16 y Nueva York 12–21 ⇒ solapamiento 12–16. En marzo, cuando EE. UU. ya está en
horario de verano y el Reino Unido aún no, el solapamiento dura cinco horas. Lo cubren las
pruebas.

**Límite conocido:** la v1 no modela festivos (Navidad, Año Nuevo). En un festivo el
calendario dirá «abierto»; la ausencia de velas la detectan la frescura y los huecos.

### OTC

**Decisión de Jessica (2026-09-25): OTC ya no está excluido** (antes lo estaba en la v1,
POINT1-DOMAIN-001). El contexto no rechaza ningún instrumento por ser OTC. Un OTC es un
instrumento distinto del canónico, con su propia identidad y sus propios datos.

Lo que este contrato **no** hace, porque no se puede saber todavía: inventar el horario de
un OTC. Sus cotizaciones y horarios los fija cada broker, así que su horario es
`BROKER_DEFINED` y, hasta que un adaptador del broker lo aporte, su contexto es
**insuficiente** con `SCHEDULE_UNKNOWN`. Si un horario es conocido (p. ej. continuo), la
serie se trata como cualquier otra. Falta, en tareas de catálogo aparte y con decisión de
Jessica: qué broker, qué instrumentos OTC y con qué horarios y fuente de datos.

La elegibilidad regulatoria pertenece al `ExecutionContext` (jurisdicción declarada), no al
instrumento ni al contexto de mercado.

## 4. Cuándo el contexto es insuficiente

| Motivo | Cuándo |
| ------ | ------ |
| `SOURCE_NOT_AUTHORIZED` | La fuente no está en la lista de fuentes autorizadas. Sus velas **ni se leen**. |
| `SCHEDULE_UNKNOWN` | El horario del mercado no se conoce (`BROKER_DEFINED`). |
| `NO_DATA` | No hay ninguna vela cerrada. |
| `INVALID_CANDLES` | Velas contradictorias (duplicadas con valores distintos) o fuera de la cuadrícula del marco. |
| `INSUFFICIENT_HISTORY` | Menos velas cerradas que el mínimo (100 por defecto). |
| `STALE_DATA` | La última vela cerrada es más antigua que la que debía existir. |
| `GAPS_IN_WINDOW` | Falta alguna vela **esperada** dentro de las últimas 100. |
| `DEGRADED_DATA` | Otras incidencias de calidad (velas duplicadas iguales descartadas, desorden). |

- **Frescura:** fresca si la última vela abierta es la que debía existir (la última que
  cerró hace más de 10 s de gracia). Con el Forex **cerrado**, se juzga en el último cierre
  semanal, no en el presente: los datos del viernes siguen frescos el sábado, pero no el
  lunes por la mañana.
- **Huecos:** solo cuentan las velas que el mercado **debía** publicar. Un fin de semana de
  Forex no es un hueco. Huecos anteriores a la ventana no afectan.
- La calidad es la de la **ventana evaluada** (las últimas 100 velas).

## 5. Parámetros y su estado

- **Profundidad mínima:** 100 velas, medida en POINT2-STRUCTURE-001.
- **Gracia de publicación:** 10 s, la misma que la API de velas (ADR 0002).
- Ninguna de las dos se ha validado más allá de esas mediciones.

## 6. Fuera de alcance

No clasifica tendencia (POINT2-TREND-001), no aplica política (POINT2-POLICY-001), no
persiste el snapshot (POINT2-SNAPSHOT-001), no expone API ni interfaz, y no lee la base
de datos: recibe las velas ya leídas.

## 7. Criterios de aceptación

- [x] No utiliza la vela todavía abierta.
- [x] No reutiliza silenciosamente el último contexto válido.
- [x] Las sesiones se calculan con zona horaria y calendario versionados.
- [x] El contexto no decide todavía si existe una señal.
- [x] Datos atrasados, incompletos o fuente no autorizada producen contexto insuficiente.
- [x] Cripto: 24/7, día, hora UTC y fuente, sin sesiones inventadas.
- [x] OTC no excluido (decisión de Jessica, 2026-09-25).
