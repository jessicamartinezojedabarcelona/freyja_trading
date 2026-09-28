# Instancia de patrón de vela: modelo, identidad y ciclo de vida (v1)

- **Estado:** vigente. Modelo `candle-pattern-instance-v1`, sobre el catálogo `candle-patterns-v1`.
- **Fecha:** 2026-09-27
- **Tarea:** POINT4-MODEL-001 (2 de 7 del punto 4).
- **Depende de:** [patrones-de-vela.md](patrones-de-vela.md) (POINT4-DOMAIN-001). El reparto entre
  documento y modelo replica el que hizo [instancia-de-figura.md](instancia-de-figura.md) para las
  figuras chartistas.
- **Código:** `backend/src/freyja_backend/domain/candlestick_pattern.py`. Dominio puro, sin E/S.
  Sus pruebas están en `backend/tests/unit/test_candlestick_pattern.py`.
- **Lo usan:** POINT4-SINGLE-001, MULTI-001, CONTEXT-001 (detectores y evaluación de contexto) y
  POINT4-HYPOTHESIS-001.

Este documento fija cómo se **representa una instancia concreta** de un patrón de vela detectado
sobre las velas cerradas de una serie, y cómo evoluciona. Es un **modelo, no un detector**: no
decide si una vela concreta es de verdad un martillo; garantiza que lo que un detector afirma es
completo, coherente, sin _look-ahead_ y reconstruible.

## 1. Qué es (y qué no es)

- **Es un registro.** Valores inmutables que se construyen una vez y se guardan tal cual. La
  historia es de **solo añadir**: cada evaluación se suma a las anteriores y nunca las reescribe.
- **No genera `Signal` ni decisión.** No contiene lado, entrada, objetivo, confianza ni
  probabilidad; un test lo comprueba sobre los campos y sobre las claves del documento. El sesgo
  tradicional de un patrón es tradición, no evidencia (`patrones-de-vela.md`, sección 1).
- **No define umbrales ni geometría.** Las proporciones de cuerpo, mecha y rango, y las
  tolerancias de igualdad, son de los detectores (POINT4-SINGLE-001, MULTI-001). El modelo solo
  exige lo estructural: que existan exactamente las velas ancla que el catálogo fija para ese
  patrón (sección 5) y que todo lo demás sea coherente.
- **No evalúa contexto.** Que la tendencia previa sea compatible con la lectura tradicional del
  patrón es de POINT4-CONTEXT-001; este modelo solo exige que, cuando el estado lo requiere, quede
  registrada la evidencia de contexto usada (sección 2, código `CONTEXT`).
- **No persiste.** Esta tarea no crea tabla ni migración: el modelo produce y lee un documento JSON
  estable; su almacenamiento llegará con las tareas que lo usen. Por eso los campos nuevos de un
  patrón futuro no exigen columnas: la evidencia es genérica (sección 6).

## 2. Contenido

### `CandlePatternInstance` (el patrón)

| Campo | Contenido |
| ----- | --------- |
| `candle_pattern_instance_id` | Identidad estable, **derivada** (sección 4). |
| `pattern_type` | Uno de los veintitrés del catálogo. |
| `traditional_bias` | **Del catálogo**, no del detector: una instancia no puede declarar otro sesgo. |
| `instrument_id`, `data_source`, `timeframe` | La serie sobre la que se detectó (las fuentes no se mezclan). |
| `observed_at` | Instante de la primera evaluación: cuándo se vio por primera vez. |
| `started_at` | Apertura de la primera vela ancla. |
| `last_evaluated_at`, `state` | Los de la última evaluación. |
| `detector_version`, `parameter_version` | Quién la encontró y con qué parámetros. |
| `evaluations` | La historia, de más antigua a más reciente; siempre hay al menos una. |

### `CandlePatternEvaluation` (lo que el detector vio en un instante)

Autosuficiente: nombra todo lo que usó, de modo que **se reconstruye por qué se detectó** sin
consultar nada más.

| Campo | Contenido |
| ----- | --------- |
| `evaluated_at` | El instante de la evaluación: solo se leyó lo que se podía conocer entonces. |
| `as_of` | Cierre de la última vela cerrada leída. |
| `state` | Uno de los ocho estados (sección 3). |
| `anchors` | Las velas cerradas en las que se apoya (`CandleAnchor`, con OHLC completo), en orden. |
| `invalidation_reasons` | Por qué dejó de ser un patrón. |
| `insufficient_data_reasons` | Por qué no se pudo juzgar. |
| `evidence` | Hechos específicos y extensibles (sección 6); incluye el contexto observado con el
  código `CONTEXT`, exigido a partir de `CONTEXT_VALID`. |

### `CandleAnchor` (una vela ancla)

Apertura, máximo, mínimo, cierre, instantes de apertura y cierre, y una etiqueta legible
(`FIRST`, `SECOND`, `THIRD`, elegida por el detector). Cuerpo, rango y mechas **no se guardan**:
se derivan (`body`, `range`, `upper_wick`, `lower_wick`, `is_bullish`, `is_bearish`), porque son
funciones exactas de lo que ya está guardado y guardarlos aparte permitiría que divergieran.

## 3. Ciclo de vida

Ocho estados, ya fijados en su significado por `patrones-de-vela.md` (sección 3); aquí se fija su
**mecánica**:

| Estado | Significa |
| ------ | --------- |
| `FORMING` | Aún no han cerrado todas las velas que el patrón necesita. |
| `MORPHOLOGICALLY_VALID` | Cerraron exactamente las velas del catálogo para este tipo, con su geometría completa. |
| `CONTEXT_VALID` | El contexto necesario es compatible con la lectura tradicional del patrón (`CONTEXT-001`). |
| `PENDING_CONFIRMATION` | El patrón exige una vela o condición **posterior a sus propias velas** que aún no ha cerrado. |
| `CONFIRMED` | El patrón queda establecido como hecho, con su interpretación. |
| `FAILED` | La confirmación esperada no llegó, o llegó en sentido contrario. Final. |
| `INVALIDATED` | El patrón dejó de serlo. Final. |
| `INSUFFICIENT_DATA` | Con los datos de ese momento no se puede juzgar. Pausa, no final. |

Transiciones permitidas (mantenerse en el mismo estado, si no es final, siempre está permitido):

| Desde | Puede pasar a |
| ----- | ------------- |
| `FORMING` | `MORPHOLOGICALLY_VALID`, `CONTEXT_VALID`, `PENDING_CONFIRMATION`, `CONFIRMED`, `FAILED`, `INVALIDATED` |
| `MORPHOLOGICALLY_VALID` | `CONTEXT_VALID`, `PENDING_CONFIRMATION`, `CONFIRMED`, `FAILED`, `INVALIDATED` |
| `CONTEXT_VALID` | `PENDING_CONFIRMATION`, `CONFIRMED`, `FAILED`, `INVALIDATED` |
| `PENDING_CONFIRMATION` | `CONFIRMED`, `FAILED`, `INVALIDATED` |
| `CONFIRMED` | `INVALIDATED` |
| `FAILED`, `INVALIDATED` | nada: ninguna evaluación posterior, ni siquiera una pausa |

- Un patrón **avanza, nunca retrocede**, y puede saltar varios hitos a la vez, igual que una figura
  chartista (`instancia-de-figura.md`, sección 3): un patrón cuya propia última vela ya es su
  confirmación (todo el catálogo v1, columna «Confirmación» de `patrones-de-vela.md`) pasa de
  `CONTEXT_VALID` a `CONFIRMED` en la misma evaluación, sin detenerse en `PENDING_CONFIRMATION`.
- **`PENDING_CONFIRMATION` no lo usa ningún patrón del catálogo v1.** Los veintitrés patrones se
  confirman con sus propias velas (columna «Confirmación»: «No» o «Sí: la propia vela N»); ninguno
  exige una vela **adicional**, fuera de su propia geometría. El estado queda fijado en el modelo
  para un patrón futuro que sí la exija (extensibilidad, sección 8 de `patrones-de-vela.md`); esta
  tarea no le da contenido porque ningún patrón de v1 lo necesita.
- **`INSUFFICIENT_DATA` es una pausa**, igual que en el modelo de figuras: cualquier estado no final
  puede pasar a él, y al salir el patrón continúa desde el estado que tenía.
- **Contenido coherente con el estado:** los motivos de invalidación existen exactamente cuando el
  patrón está `INVALIDATED`; los de datos insuficientes, exactamente cuando lo está
  `INSUFFICIENT_DATA`; a partir de `CONTEXT_VALID` (inclusive) la evaluación exige una evidencia de
  código `CONTEXT` (sección 6): sin contexto registrado, no hay forma de saber qué se comprobó.

## 4. Identidad y versiones

`candle_pattern_instance_id` es un UUID por nombre (v5) del **tipo, la serie, el inicio, el
detector, los parámetros y la versión del modelo**. Por tanto:

- **El mismo patrón, hallado de nuevo por el mismo detector con los mismos parámetros, es la misma
  instancia**; avanzarlo no cambia quién es.
- Un inicio, un detector, unos parámetros o un tipo distintos son **otra instancia**.
- Al leer un documento se comprueba que la identidad escrita es la que da su contenido.

## 5. Solo se añade: una modificación sustancial es otra instancia

- **Las velas ancla solo pueden añadirse.** Las de la evaluación anterior deben ser exactamente
  las primeras de la nueva (mismo OHLC, mismos instantes, misma etiqueta). Cambiar, quitar o
  reetiquetar una ancla, o empezar por otra vela, **no es evolucionar: es otro patrón**, con su
  identidad.
- Los instantes **avanzan estrictamente** y `as_of` no retrocede.
- **Cada tipo exige exactamente las velas de su catálogo** (`candle_count`: 1, 2 o 3) para llegar a
  `MORPHOLOGICALLY_VALID` en adelante — a diferencia de las figuras chartistas, donde el mínimo de
  anclas es un **suelo** (puede haber más), aquí es un **número exacto**: un patrón de vela no
  admite una cuarta vela ancla propia sin dejar de ser esa geometría. `FORMING` sí puede tener menos
  (el patrón todavía no cerró todas sus velas).
- **Varias instancias coexisten** sobre las mismas velas (`patrones-de-vela.md`, sección 4, regla
  3); ninguna oculta, sustituye ni fusiona a otra. `SUPERSEDED` existe como motivo de invalidación
  para cuando el contexto resuelve a favor del otro nombre de una geometría compartida (`HAMMER` /
  `HANGING_MAN`, sección 7).

## 6. Evidencia extensible

`evidence` reutiliza `PatternEvidence`/`evidence()` de `chart_pattern.py`: mismo código en
mayúsculas y guion bajo, mismo texto legible, mismos valores (texto, entero, booleano o `Decimal`
exacto, nunca coma flotante). Un patrón futuro trae códigos nuevos, no campos nuevos. Un código está
reservado por este modelo:

- **`CONTEXT`**: el contexto observado (tendencia previa, localización) en el que se evaluó el
  patrón. Obligatorio a partir de `CONTEXT_VALID` (inclusive); su contenido exacto (qué hechos lleva)
  lo define POINT4-CONTEXT-001, no este documento.

## 7. Geometrías compartidas y `SUPERSEDED`

Cuando la misma geometría admite dos nombres según el contexto (`HAMMER`/`HANGING_MAN`,
`INVERTED_HAMMER`/`SHOOTING_STAR`, `patrones-de-vela.md` sección 6), este modelo no obliga a elegir
uno al nacer la instancia: un detector puede optar por no crear ninguna instancia hasta que el
contexto decante el nombre, o crear una instancia provisional con el nombre que mejor encaja y
`INVALIDATED` con motivo `SUPERSEDED` si el contexto resuelve a favor del otro. **Cuál de las dos
estrategias se implementa es una decisión de POINT4-SINGLE-001/CONTEXT-001**, no de este modelo: aquí
solo se fija que ambas son representables y que nunca coexisten dos instancias con nombres opuestos
sobre las mismas velas dándose ambas por válidas a la vez.

«Ninguna instancia» se refiere siempre a `CandlePatternInstance`: no nace ninguna con un
`pattern_type` de la geometría compartida. No impide que el detector conserve el hecho geométrico
por otra vía, fuera de este modelo, sin nombrarlo (`AmbiguousGeometry`,
`docs/domain/detectores-de-una-vela.md` sección 4 bis, corrección 2026-09-28 a POINT4-SINGLE-001):
ese registro no es una instancia, no tiene `pattern_type` ni `state`, y este documento no lo
regula.

## 8. Sin _look-ahead_

Cada evaluación se rechaza si usa algo que no se sabía en su instante: una vela ancla que aún no
había cerrado, una vela leída (`as_of`) que cierra después de la evaluación. A diferencia de las
figuras chartistas, un patrón de vela no se apoya en pivotes confirmados (no los tiene): sus anclas
son velas cerradas, así que la única condición de conocibilidad es que cada una haya cerrado
(`close_time`) antes o en el instante evaluado.

## 9. Serialización

`CandlePatternInstance.document()` produce JSON puro: precios como texto decimal exacto, instantes
UTC terminados en `Z`, los tipos de los hechos de evidencia junto a su valor, y el sesgo y la
versión del catálogo con los que se escribió. `candle_pattern_instance_from_document()` lo lee **sin
derivar nada**: valida toda regla, rechaza una versión de modelo que no conoce, un campo ausente, un
valor desconocido, un instante sin zona o no UTC, un precio que no es un decimal positivo y una
identidad que no corresponde al contenido.

## 10. Lo que este modelo no decide

- **La geometría.** Que el cuerpo de una vela sea «pequeño» o que dos mínimos sean «prácticamente
  iguales» lo juzgan los detectores (POINT4-SINGLE-001, MULTI-001); el modelo no comprueba
  proporciones.
- **El contexto.** Si la tendencia previa es compatible con la lectura tradicional (POINT4-CONTEXT-001).
- **La política de gaps.** Configurable por mercado y producto (`patrones-de-vela.md`, sección 2);
  no es un campo de este modelo.
- Cómo se guarda (tabla, migración, retención) ni cómo se expone (API, pantalla).
- Cómo se combina con figuras chartistas u otra evidencia en una hipótesis (POINT4-HYPOTHESIS-001).
- Objetivos de precio, entradas, riesgo, señales u órdenes.
- Si un patrón funciona: sigue sin haber evidencia estadística (punto 15).

## 11. Criterios de aceptación de esta tarea

- [x] El modelo distingue una definición versionada (`CandlePatternDefinition`, el catálogo) de una
      instancia observada (`CandlePatternInstance`) (secciones 2, 4).
- [x] La detección puede reconstruirse desde el documento (sección 9).
- [x] Ninguna dependencia de listas cerradas en frontend: el catálogo es datos, extensible sin
      cambiar el esquema (sección 6, y `patrones-de-vela.md` sección 10).
- [x] No se incorpora probabilidad ni política de ejecución (sección 1).

## 12. Decisiones técnicas tomadas al redactar

Registradas aquí para que se puedan corregir; ninguna es de producto.

1. **El número de velas ancla es exacto, no un mínimo** (a diferencia de `min_anchor_pivots` en el
   modelo de figuras): un patrón de vela es, por definición, una geometría de 1, 2 o 3 velas
   concretas; una cuarta vela ancla propia lo convertiría en otra cosa.
2. **`PENDING_CONFIRMATION` se deja sin uso en v1** en lugar de forzar una fase intermedia
   artificial: el catálogo (`patrones-de-vela.md`) ya deja escrito que las tres velas de, por
   ejemplo, `MORNING_STAR` incluyen su propia confirmación: no hay una vela «cuarta» que confirme.
   El estado queda reservado para cuando exista un patrón que sí la necesite.
3. **`evidence` reutiliza `PatternEvidence`/`evidence()` de `chart_pattern.py`** en vez de duplicar
   el tipo: es una estructura genérica de hechos, ya usada también por `pattern_hypothesis.py`, sin
   nada específico de figuras chartistas en su definición.
4. **Cuerpo, rango y mechas son propiedades derivadas de `CandleAnchor`**, nunca campos guardados:
   evita que un valor guardado pueda divergir del OHLC del que se calcula.
5. **`SUPERSEDED` no fuerza una estrategia de detección** para las geometrías compartidas
   (`HAMMER`/`HANGING_MAN`): dos estrategias razonables son representables por el modelo; cuál se
   implementa es de POINT4-SINGLE-001/CONTEXT-001 (sección 7).
6. **La política de gaps no entra en este modelo**, siguiendo la propia decisión de
   `patrones-de-vela.md` de dejarla para POINT4-MULTI-001: introducirla aquí habría sido decidir un
   punto que el propio contrato de dominio ya asignó a otra tarea.
7. **Sin persistencia en esta tarea** (sección 1), igual que en `instancia-de-figura.md`.
