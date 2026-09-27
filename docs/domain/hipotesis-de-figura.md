# Hipótesis de figura: procedencia, operabilidad y evidencia combinada (v1, propuesta)

- **Estado:** en redacción. Contrato `hypothesis-v1`, sobre el catálogo `chart-patterns-v1`
  ([figuras-chartistas.md](figuras-chartistas.md)) y el modelo `pattern-instance-v1`
  ([instancia-de-figura.md](instancia-de-figura.md)).
- **Fecha:** 2026-09-27
- **Tarea:** POINT3-HYPOTHESIS-001 (6 de 7 del punto 3). Documentación vinculante: **no implementa
  código**, igual que POINT3-DOMAIN-001 y FIB-DOMAIN-001. El modelo (`PatternHypothesis`,
  `HypothesisEvaluation`) y el agregador se implementan después, con este documento como referencia.
- **Depende de:** [figuras-chartistas.md](figuras-chartistas.md) (roles y sesgo tradicional),
  [instancia-de-figura.md](instancia-de-figura.md) (identidad, ciclo de vida y evidencia de una
  figura), [tendencia-estructural.md](tendencia-estructural.md) y
  [contexto-y-tendencia.md](contexto-y-tendencia.md) (tendencia previa, para `context_compatible`),
  [detectores-de-expansion.md](detectores-de-expansion.md) sección 10.4, 10.5 y 10.10 (el diamante,
  origen del cálculo estricto de procedencia que aquí se generaliza) y
  [fibonacci-retroceso.md](fibonacci-retroceso.md) sección 3 (comparado y **no** igualado, sección 4
  de este documento).
- **Relacionado:** `PATTERN-PROVENANCE-001` (Notion, backlog): calcula procedencia en las 18 figuras
  de reversión y continuación que hoy no la tienen. Este contrato no depende de que esa tarea esté
  hecha para poder escribirse ni implementarse: define qué ocurre **mientras no lo esté**
  (sección 4.3).

## 1. Qué es y qué no es una hipótesis

Una **hipótesis de figura** (`PatternHypothesis`) es una afirmación direccional **verificable**
derivada de una figura de origen, junto con qué otras figuras coexistentes la apoyan o la
contradicen. Es un registro, con el mismo estilo que `PatternInstance`: identidad estable, historia
de evaluaciones que **solo se añade**, autosuficiente (cada evaluación se reconstruye sin consultar
nada más).

- **No es una señal, una orden ni una entrada.** No tiene lado ejecutable, tamaño, objetivo de
  precio ni vencimiento. Una hipótesis aislada **nunca llama a un executor ni a un broker**.
- **No es una probabilidad.** No suma puntuaciones, no combina sesgos en una cifra, no produce
  `probability` ni un veredicto ponderado. Varias figuras pueden apoyar, contradecirse o
  permanecer neutrales; el contrato **conserva esa discrepancia**, no la resuelve.
- **No elige en silencio.** Si dos figuras coexistentes apuntan en direcciones distintas, ambas
  quedan registradas (`supporting_patterns`, `conflicting_patterns`); nadie descarta la de menor
  sesgo tradicional a favor de la de mayor.
- **No decide condiciones obligatorias ni confirmaciones.** Eso es del punto 6
  (`StrategySpec`), que leerá esta hipótesis como uno de sus insumos, no al revés.
- **Distingue, siempre por separado, tres cosas que no deben mezclarse** (y que son el objeto de
  este documento):
  1. **La hipótesis descriptiva**: qué dirección sugiere la figura de origen y qué otras figuras la
     acompañan, sea o no utilizable en tiempo real (sección 3).
  2. **La procedencia de cada evidencia**: si esa lectura pudo conocerse en vivo, después de
     formarse pero antes de saberse, de forma retrospectiva, o si no puede probarse ninguna de las
     tres (sección 4).
  3. **La condición para declararla operable**: la regla, única y estricta, que decide si la
     hipótesis en su conjunto puede usarse como base de una señal en tiempo real (sección 5).

  Una hipótesis siempre existe y siempre se describe (1); que además sea **operable** depende
  exclusivamente de (2) y (3), nunca al revés.

## 2. Cuándo existe una hipótesis

Una hipótesis nace de una `PatternInstance` de origen (`source_pattern_instance_id`) en el primer
instante en que esa instancia tiene una **ruptura real** que interpretar:
`BREAKOUT_PENDING_CONFIRMATION`, `CONFIRMED_UP` o `CONFIRMED_DOWN` (ciclo de vida de
`instancia-de-figura.md`, sección 3).

- **No hay hipótesis antes de la ruptura.** `FORMING`, `GEOMETRICALLY_VALID` e
  `INSUFFICIENT_DATA` no producen hipótesis: la figura existe, pero afirmar una dirección antes de
  que rompa sería tratar el sesgo tradicional como si fuera evidencia, justo lo que
  `figuras-chartistas.md` (sección 1) prohíbe. **Decisión de alcance de la v1**, revisable: una
  versión futura podría declarar una hipótesis pre-ruptura con `hypothesis_direction: BIDIRECTIONAL`
  para figuras de sesgo `BREAKOUT_DEPENDENT`/`CONTEXT_DEPENDENT` («va a moverse, lado por
  determinar»); v1 no la emite y ese valor del enum queda reservado, sin uso.
- **La hipótesis evoluciona con su origen, sin cambiar de identidad.** Si la instancia de origen
  pasa de `BREAKOUT_PENDING_CONFIRMATION` a `CONFIRMED_UP`, o a `FAILED_BREAKOUT`, se añade una
  evaluación nueva a la **misma** hipótesis (sección 6), igual que una `PatternInstance` avanza sin
  crear otra figura.
- **Una instancia `INVALIDATED` sin ruptura previa nunca tuvo hipótesis** que cerrar: no se crea
  ninguna. Si ya la tenía (por haber pasado antes por un estado de ruptura) y luego se invalida, la
  hipótesis recibe una evaluación final (sección 6).

## 3. La hipótesis descriptiva: contrato

Toda hipótesis, sea o no operable, tiene esta forma. Es la generalización del borrador aprobado en
Notion (POINT3-HYPOTHESIS-001), con la procedencia hecha explícita.

| Campo | Contenido |
| ----- | --------- |
| `pattern_hypothesis_id` | Identidad estable, UUID v5 de (`source_pattern_instance_id`, `definition_version`): el mismo origen produce siempre la misma hipótesis. |
| `source_pattern_instance_id` | La figura de la que nace. |
| `hypothesis_kind` | `CONTINUATION` \| `REVERSAL` \| `BREAKOUT` \| `VOLATILITY_EXPANSION` (sección 3.1). |
| `hypothesis_direction` | `UP` \| `DOWN` \| `UNKNOWN` (`BIDIRECTIONAL` reservado, sin uso en v1). |
| `target_scope` | `MARKET_DIRECTION` \| `NEXT_CANDLE` \| `MULTI_CANDLE_MOVE` (sección 3.2). |
| `context_compatible` | Si la tendencia previa (punto 2) es coherente con la lectura tradicional del rol usado (sección 3.1). |
| `supporting_patterns[]` | Otras instancias, de cualquier figura, cuya propia lectura direccional coincide (sección 3.3). |
| `conflicting_patterns[]` | Igual, en sentido contrario. |
| `evidence` | Hechos con código, igual que `PatternInstance.evidence`: al menos `HYPOTHESIS_SOURCE` (estado, dirección y ruptura de la instancia de origen en este instante, para que la evaluación sea autosuficiente). |
| `operability` | `OPERABLE` \| `RETROSPECTIVE` \| `UNPROVEN` (sección 5). |
| `definition_version` | `hypothesis-v1`. |

### 3.1 `hypothesis_kind` y `context_compatible`: derivados, nunca del sesgo en crudo

El sesgo tradicional (`traditional_bias`) no es evidencia (`figuras-chartistas.md`, sección 1);
`hypothesis_kind` no lo copia. Se deriva de los **roles** (`traditional_roles`) de la figura de
origen, la **tendencia previa** conocida en el instante de la ruptura (`contexto-y-tendencia.md`) y
la **dirección real** de la ruptura, con esta prioridad fija:

| Prioridad | Condición | `hypothesis_kind` |
| --------- | --------- | ------------------ |
| 1 | El catálogo da a la figura el rol `EXPANSION` (`BROADENING_FORMATION`, `DIAMOND`) | `VOLATILITY_EXPANSION` |
| 2 | Rol `REVERSAL` y la tendencia previa iba **en sentido contrario** a la ruptura (hay tendencia que revertir) | `REVERSAL` |
| 3 | Rol `CONTINUATION` y la tendencia previa iba **en el mismo sentido** que la ruptura | `CONTINUATION` |
| 4 | Ninguna de las anteriores (sin tendencia previa clara, `RANGE`/`TRANSITION`, o el rol disponible no encaja con la tendencia observada) | `BREAKOUT` |

`context_compatible` es `true` exactamente cuando se aplicó la prioridad 2 o la 3; `false` en la 4
(la figura rompió, pero no en un contexto que la tradición reconozca como reversión o continuación
de lo que la precedía). Prioridad 1 no fija `context_compatible`: se registra igualmente, con su
propio valor, como dato adicional (una expansión puede o no coincidir con el contexto).

Una figura con varios roles (p. ej. un triángulo ascendente, `CONTINUATION` y `REVERSAL`) no elige
uno por convención: la tendencia previa real decide cuál aplicó esta vez.

### 3.2 `target_scope`: siempre `MARKET_DIRECTION` en este contrato

Sin una `StrategySpec` todavía (punto 6, sin implementar), no hay quien exija un horizonte
concreto. Por tanto, en las hipótesis que produce este contrato, `target_scope` es siempre
`MARKET_DIRECTION` («la dirección general del mercado», sin plazo). `NEXT_CANDLE` y
`MULTI_CANDLE_MOVE` quedan reservados a cuando una `StrategySpec` (punto 6) declare explícitamente
que los necesita, con el horizonte exacto que fije el punto 10; ninguna figura ni esta capa lo
asume por su cuenta.

### 3.3 Soporte y conflicto: misma serie, mismo instante, sin puntuación

`supporting_patterns[]` y `conflicting_patterns[]` se calculan así:

- **Alcance v1: la misma serie** (mismo instrumento, misma fuente, misma temporalidad) que la
  figura de origen. La correlación entre temporalidades o instrumentos distintos no es de esta
  tarea (queda para cuando exista, POINT7-MULTITIMEFRAME-001 u otra).
- Se consideran las demás `PatternInstance` de esa serie cuya evaluación más reciente, en un
  instante **conocido y no posterior** al de la hipótesis (nunca del futuro), tiene una lectura
  direccional propia: su propia ruptura, si la tiene (`BREAKOUT_PENDING_CONFIRMATION`,
  `CONFIRMED_UP`, `CONFIRMED_DOWN`), en la dirección de esa ruptura.
- **Coincide con `hypothesis_direction` → `supporting_patterns`; la contradice →
  `conflicting_patterns`.** Una figura sin ruptura propia (`FORMING`, `GEOMETRICALLY_VALID`,
  `INSUFFICIENT_DATA`) no tiene lectura direccional: **no entra en ninguna de las dos listas**
  («permanecer neutral», sección 1).
- **Una instancia cubierta por solapamiento no cuenta.** Si en el instante de evaluación la
  instancia está tapada por otra vigente de su misma familia (el caso del diamante,
  `held_by_overlap`, `detectores-de-expansion.md` sección 10.10), no se usa como evidencia mientras
  siga cubierta: no estaba realmente publicada, así que no pudo apoyar ni contradecir nada.
- Cada entrada guarda `pattern_instance_id`, `pattern_type`, la dirección que aportó y **su propia
  procedencia** (sección 4), aunque esa procedencia no cambie la operabilidad de la hipótesis
  (sección 5): sirve para que quien lea la hipótesis sepa qué tan sólida es cada pieza, no solo
  cuántas hay.
- **Sin puntuación.** El número de figuras que apoyan o contradicen no se suma, ni se pondera por
  sesgo, ni decide nada por sí solo: es información que el punto 6 podrá usar con sus propias
  reglas, explícitas y versionadas allí.

## 4. Procedencia de cada evidencia

Cada pieza de evidencia direccional que participa en una hipótesis —la ruptura de la figura de
origen y la de cada figura en `supporting_patterns`/`conflicting_patterns`— lleva su propia
**procedencia** (`evidence_provenance`), en cuatro valores:

| Procedencia | Significa |
| ----------- | --------- |
| `LIVE` | La vela del primer cierre más allá de la frontera de salida **abrió en el `known_at` de esa figura o después**: se pudo detectar en vivo. |
| `AFTER_MARKET_FORMATION` | Esa vela abrió en el `market_formed_at` de la figura o después, pero **antes** de su `known_at`: la figura ya existía en el mercado: Freyja aún no la conocía. Se describe, no es operable. |
| `RETROSPECTIVE` | Esa vela abrió **antes** de `market_formed_at`: la figura todavía no existía cuando la vela abrió. Se describe, no es operable. |
| `UNPROVEN` | No puede probarse ninguna de las tres anteriores (sección 4.3). **Fail-closed: nunca se trata como si fuera `LIVE`.** |

Estas son las mismas tres primeras categorías del diamante (`detectores-de-expansion.md`, sección
10.4), con `UNPROVEN` añadido como cuarto valor explícito para cuando la procedencia **no se puede
demostrar en absoluto** con la definición estricta (sección 4.1) — algo que el diamante, al tener
siempre sus seis pivotes y sus recepciones, no necesitaba distinguir, pero que esta capa sí, porque
combina figuras que hoy no ofrecen esa garantía.

### 4.1 Instantes necesarios

Para juzgar la procedencia de una ruptura (o de un toque, en herramientas como Fibonacci) hacen
falta, para **esa figura o esa instancia concreta**, generalizando `detectores-de-expansion.md`
sección 10.4:

- **`market_formed_at`**: el mayor de los instantes de **confirmación de mercado** de todos los
  pivotes o anclas de los que depende la geometría (el cierre de la vela que confirma cada uno).
- **`known_at`**: el mayor de los instantes de **llegada** (`received_at`) de **todas** las velas
  de las que depende que la geometría sea válida — no solo la que confirma el último pivote:
  también las velas intermedias cuyos cierres o mechas tienen que respetar una frontera o un
  extremo para que la figura siga siendo la misma (los «cierres entre contactos» del diamante, o
  las velas entre `A` y `B` de un impulso de Fibonacci que no pueden salirse de sus extremos).
  **Esta es la definición estricta**, y es la que decide si una etiqueta de procedencia de un
  detector concreto puede aceptarse como tal (sección 4.3).
- **La apertura de la vela juzgada** (`open_time`): la del primer cierre más allá de la frontera de
  salida, para una ruptura; la del toque o cierre más allá de un nivel, para Fibonacci.
- Con estos tres instantes, la tabla de la sección 4 se aplica igual que en el diamante: límite
  inclusivo hacia `LIVE` (abrir exactamente en `known_at` cuenta como `LIVE`; un instante antes, no).

### 4.2 Velas recibidas fuera de orden

`known_at` es un **máximo de llegadas**, nunca un orden de calendario. Si una vela anterior (por su
apertura) llega después que una posterior —un relleno, una reconexión, un hueco que se completa
tarde—, `known_at` sube hasta esa llegada tardía, y la procedencia de cualquier ruptura que dependa
de esa figura se recalcula con el `known_at` correcto, no con el que parecía tener antes de que
llegara el dato tardío. Esto es exactamente lo que ya prueba `detectores-de-expansion.md` sección
10.4 para el diamante; aquí se exige igual para cualquier figura que aporte evidencia a una
hipótesis.

### 4.3 Sin procedencia demostrada, `UNPROVEN`: qué cubre hoy

`UNPROVEN` no es «no se sabe si es `LIVE`»: es **la ausencia de una demostración** de que la
etiqueta de procedencia de un detector satisface la definición estricta de la sección 4.1. Cubre,
a fecha de este documento (2026-09-27), dos situaciones distintas que no deben confundirse entre
sí ni con las 18 figuras pendientes:

1. **El detector de origen no calcula procedencia en absoluto.** Las 18 figuras de reversión y
   continuación (todo el catálogo salvo el diamante) solo garantizan que cada evaluación fue
   correcta para su propio instante (`evaluated_at`, `instancia-de-figura.md` sección 7); ninguna
   calcula `market_formed_at` ni `known_at` para su ruptura todavía. Su evidencia es `UNPROVEN`
   hasta que `PATTERN-PROVENANCE-001` la incorpore, figura por figura.
2. **El detector de origen calcula algo con otro nombre que no está verificado contra la
   definición estricta.** Es el caso de Fibonacci: su `availability` (`OPERABLE` /
   `RETROSPECTIVE` / `UNPROVEN`, `fibonacci-retroceso.md` sección 3) usa un `known_at` que es «el
   mayor de **dos** valores» (la confirmación de mercado y la recepción de `B`), sin incluir la
   recepción de `A` ni la de las velas intermedias que sostienen el impulso (sección 2 del mismo
   documento). No es la misma prueba que la sección 4.1 exige. **`OPERABLE` de Fibonacci no se
   trata como `LIVE`**: mientras esa brecha no se cierre, toda evidencia que provenga de Fibonacci
   entra en una hipótesis como `UNPROVEN`, exactamente igual que una de las 18 figuras pendientes,
   **aunque Fibonacci devuelva `OPERABLE`**. La corrección de ese `known_at` es una tarea propia,
   pequeña, sobre código ya fusionado (PR #71), con prioridad propia y **fuera de este documento y
   de su PR**: no se toca código de Fibonacci aquí.

Este listado es de estado, no de contrato: en cuanto un detector demuestre (con pruebas, no solo
con un nombre parecido) que satisface la sección 4.1, su evidencia deja de ser `UNPROVEN` sin que
este documento cambie de versión.

## 5. Condición para declararse operable

La **operabilidad de la hipótesis** (`operability`, sección 3) depende **exclusivamente** de la
procedencia de la ruptura de su **figura de origen** — nunca de las de `supporting_patterns` o
`conflicting_patterns`, que se registran para que se vea qué tan acompañada está la hipótesis pero
no participan en esta decisión (evita que una figura de soporte con buena procedencia «blanquee»
una hipótesis cuyo origen no la tiene).

| Procedencia de la ruptura de origen | `operability` de la hipótesis |
| ------------------------------------ | ------------------------------ |
| `LIVE` | `OPERABLE` |
| `AFTER_MARKET_FORMATION` o `RETROSPECTIVE` | `RETROSPECTIVE` |
| `UNPROVEN` | `UNPROVEN` |

**Regla crítica, sin excepciones:** una hipótesis solo es `OPERABLE` cuando la procedencia de su
figura de origen es `LIVE` **demostrado con la definición estricta de la sección 4.1**. Ninguna
evidencia `UNPROVEN` habilita `OPERABLE`, ni por sí sola ni combinada con otras: si la figura de
origen es `UNPROVEN`, la hipótesis es `UNPROVEN`, sin importar cuántas figuras `LIVE` la apoyen en
`supporting_patterns`. `RETROSPECTIVE` y `UNPROVEN` se conservan como registro — explican qué
habría dicho la hipótesis y por qué no se puede o no se pudo usar en vivo—, pero **nunca son base
de una señal en tiempo real** (punto 6, cuando exista).

## 6. Evolución y no reescritura del pasado

Una `HypothesisEvaluation` es tan inmutable como una `PatternEvaluation`
(`instancia-de-figura.md`, secciones 1 y 5): una vez registrada, ninguna llegada posterior de datos
la reescribe.

- **Replay estable.** Ejecutar el mismo tramo de velas dos veces —una deteniéndose en el instante
  `T`, otra continuando con velas posteriores a `T`— debe producir, para todo instante evaluado
  hasta `T`, la **misma** `HypothesisEvaluation` byte a byte: mismo `hypothesis_kind`,
  `hypothesis_direction`, `context_compatible`, listas de soporte y conflicto, procedencia de cada
  evidencia y `operability`. Añadir velas futuras no cambia una clasificación ya emitida para un
  instante pasado. Es la misma propiedad que exige `PATTERN-PROVENANCE-001` para el retrofit de los
  detectores, aplicada ahora también a la capa de agregación que este contrato añade encima de
  ellos: agregar evidencia sin mirar al futuro no basta si el agregador sí lo hace.
- **Una llegada tardía nunca edita hacia atrás.** Si una figura de `supporting_patterns` recibe,
  fuera de orden, un dato que le habría cambiado su lectura en un instante `T` ya evaluado, esa
  evidencia se incorpora en una evaluación **nueva**, fechada en su propio `evaluated_at` (posterior
  a `T`), nunca reescribiendo la evaluación de `T`.
- **La hipótesis avanza con su origen, no antes ni después.** Se añade una evaluación cuando la
  instancia de origen avanza de estado (`BREAKOUT_PENDING_CONFIRMATION` → `CONFIRMED_UP`/`DOWN` →,
  si aplica, `FAILED_BREAKOUT`/`INVALIDATED`) o cuando cambia el conjunto de figuras que la apoyan o
  la contradicen en un instante posterior. Un estado final de la instancia de origen
  (`FAILED_BREAKOUT`, `INVALIDATED`) cierra también la evolución de la hipótesis: su última
  evaluación registra `hypothesis_direction: UNKNOWN` y el motivo en `evidence`, y no se añade
  ninguna más — mismo principio de finalidad que `instancia-de-figura.md` sección 3.

## 7. Ejemplos

### 7.1 Hipótesis operable, sustentada por un diamante verificado

Un `DIAMOND` en `BTCUSDT` 15m, con seis pivotes confirmados y recibidos, rompe por la frontera
inferior de su contracción. Su procedencia (`detectores-de-expansion.md` sección 10.4) es `LIVE`:
la vela del cierre por debajo abrió en su `known_at` o después. La tendencia previa (punto 2) era
`UPTREND`.

- `hypothesis_kind`: rol `EXPANSION` del diamante tiene prioridad 1 → `VOLATILITY_EXPANSION`.
- `hypothesis_direction`: `DOWN` (la ruptura real, no el sesgo `CONTEXT_DEPENDENT` del catálogo).
- `context_compatible`: `true` (rompió en contra de la tendencia previa, lectura de agotamiento
  coherente con el rol `REVERSAL` que también tiene el diamante, aunque `hypothesis_kind` use
  `EXPANSION` por prioridad).
- `supporting_patterns`: una `FALLING_WEDGE` en la misma serie, con ruptura `CONFIRMED_DOWN` y
  procedencia también `LIVE`, en el mismo tramo.
- `conflicting_patterns`: vacío (ninguna otra figura, en ese instante, tenía una lectura `UP`).
- Procedencia de la evidencia de origen: `LIVE` → `operability`: `OPERABLE`.

### 7.2 Hipótesis descriptiva, sustentada por una figura pendiente de retrofit

Un `ASCENDING_TRIANGLE` en la misma serie rompe por la resistencia horizontal, `CONFIRMED_UP`. El
detector de triángulos (POINT3-CONTINUATION-001) todavía no calcula `market_formed_at` ni
`known_at` (pendiente en `PATTERN-PROVENANCE-001`).

- `hypothesis_kind`: sin rol `EXPANSION`; tendencia previa `UPTREND` coincide con la ruptura `UP` y
  el rol `CONTINUATION` → `CONTINUATION`. `context_compatible`: `true`.
- `hypothesis_direction`: `UP`.
- Procedencia de la evidencia de origen: **`UNPROVEN`** (situación 1 de la sección 4.3: el
  detector no calcula procedencia). → `operability`: `UNPROVEN`. La hipótesis se registra completa,
  con su dirección y su contexto, pero **no se ofrece como base operable** de nada en tiempo real.

### 7.3 Hipótesis descriptiva, sustentada por Fibonacci

Un impulso alcista de Fibonacci, en la misma serie, tiene un cierre por debajo del nivel 0,618 que
su propio cálculo etiqueta `availability: OPERABLE` (`fibonacci-retroceso.md` sección 3). Se usa
como figura de `conflicting_patterns` de una hipótesis alcista, por su lectura bajista en ese
nivel.

- Procedencia de esa evidencia para este contrato: **`UNPROVEN`** (situación 2 de la sección 4.3:
  Fibonacci calcula algo con ese nombre, pero su `known_at` no satisface todavía la definición
  estricta de la sección 4.1). Se anota en la entrada de `conflicting_patterns` junto con el dato
  de que la herramienta de origen la marcó `OPERABLE`, para que quede constancia de la discrepancia,
  pero **no se trata como `LIVE`** y, si esta fuera la figura de origen en vez de un conflicto, la
  hipótesis resultante sería `UNPROVEN`, nunca `OPERABLE`, solo por esa etiqueta.

## 8. Lo que este documento no decide

- Cómo usa el punto 6 (`StrategySpec`) `supporting_patterns`, `conflicting_patterns` y
  `operability` para exigir condiciones obligatorias o confirmaciones: esta capa entrega los datos,
  no las reglas de decisión.
- Objetivos de precio, entradas, vencimientos ni tamaño (puntos 8, 10, 11 y siguientes).
- Correlación entre temporalidades o instrumentos distintos (fuera del alcance v1, sección 3.3).
- Hipótesis pre-ruptura (`BIDIRECTIONAL`), aplazadas a una versión futura (sección 2).
- Cómo se calcula la procedencia dentro de cada detector: eso es `PATTERN-PROVENANCE-001` (las 18
  figuras) y la corrección propia de Fibonacci (`FIB-CALC-001`), ninguna de las dos parte de este
  documento ni de su PR.
- Persistencia (tabla, migración, retención) ni exposición (API, pantalla): mismo alcance que
  `instancia-de-figura.md`, sección 1.

## 9. Criterios de aceptación de esta tarea

- [ ] `PatternHypothesis`/`HypothesisEvaluation` con identidad estable y evolución de solo-añadir,
      igual que `PatternInstance` (secciones 2 y 6).
- [ ] Procedencia de evidencia en cuatro estados, con `UNPROVEN` como valor fail-closed por defecto
      cuando no se demuestra la definición estricta (sección 4).
- [ ] `LIVE` y `OPERABLE` (Fibonacci) **no se presentan como equivalentes**; la evidencia de
      Fibonacci es `UNPROVEN` hasta que se corrija su `known_at` (sección 4.3).
- [ ] Ninguna hipótesis es `OPERABLE` a partir de evidencia `UNPROVEN` de su figura de origen, sola
      o combinada con evidencia de soporte de mejor procedencia (sección 5).
- [ ] Instantes necesarios (`market_formed_at`, `known_at`, apertura de la vela juzgada)
      especificados de forma general, no solo para el diamante (sección 4.1).
- [ ] Recepciones desordenadas: `known_at` como máximo de llegadas, nunca por orden de calendario
      (sección 4.2).
- [ ] Replay estable: una evaluación ya registrada no cambia al añadir datos futuros (sección 6).
- [ ] Ejemplos de hipótesis operable (diamante) y descriptivas (figura pendiente, Fibonacci)
      (sección 7).
- [ ] Ninguna puntuación agregada ni `probability` (sección 1).
- [ ] Una hipótesis aislada nunca llama a executor ni a broker (sección 1).

## 10. Decisiones técnicas tomadas al redactar

Registradas aquí para que se puedan corregir; ninguna es de producto.

1. **Una hipótesis solo nace de una ruptura real** (`BREAKOUT_PENDING_CONFIRMATION` en adelante);
   no hay hipótesis pre-ruptura en v1. `BIDIRECTIONAL` queda reservado, sin uso.
2. **La identidad de la hipótesis se deriva de su origen**, igual que `PatternInstance` deriva la
   suya del primer pivote: mismo origen, misma hipótesis, que evoluciona sin cambiar de identidad.
3. **La operabilidad depende solo de la procedencia del origen**, nunca de las de soporte o
   conflicto, para que una evidencia `UNPROVEN` no pueda «lavarse» con evidencia de mejor
   procedencia que la acompañe.
4. **`hypothesis_kind` se deriva con una tabla de prioridad fija** (expansión, luego reversión o
   continuación por contexto, luego ruptura sin más), nunca copiando el sesgo tradicional en crudo.
5. **`target_scope` es siempre `MARKET_DIRECTION`** en este contrato, a falta de una `StrategySpec`
   que pida otra cosa.
6. **Procedencia en cuatro estados**, no tres: `UNPROVEN` se añade porque esta capa combina
   detectores que hoy no ofrecen la garantía que el diamante sí ofrece, y hacía falta un valor para
   «no se puede demostrar», distinto de «se demostró que fue retrospectivo».
7. **`OPERABLE` de Fibonacci se trata como `UNPROVEN`, no como `LIVE`**, hasta que su `known_at` se
   corrija para incluir la recepción de `A` y de las velas intermedias del impulso (comparación
   hecha el 2026-09-27, registrada en `PATTERN-PROVENANCE-001`).
8. **Alcance v1 limitado a una sola serie** para soporte y conflicto: evita inventar una regla de
   correlación multi-temporalidad que no se ha pedido todavía.
9. **Instancias cubiertas por solapamiento no cuentan como evidencia**, generalizando la regla del
   diamante (`held_by_overlap`) a cualquier figura futura que pueda tener el mismo problema.
