# Hipótesis de figura: procedencia, operabilidad y evidencia combinada (v1, propuesta)

- **Estado:** vigente. Contrato `hypothesis-v1`, sobre el catálogo `chart-patterns-v1`
  ([figuras-chartistas.md](figuras-chartistas.md)) y el modelo `pattern-instance-v1`
  ([instancia-de-figura.md](instancia-de-figura.md)).
- **Fecha:** 2026-09-27
- **Tarea:** POINT3-HYPOTHESIS-001 (6 de 7 del punto 3).
- **Código:** `backend/src/freyja_backend/domain/pattern_hypothesis.py`. Dominio puro, sin E/S.
  Sus pruebas están en `backend/tests/unit/test_pattern_hypothesis.py`.
- **Depende de:** [figuras-chartistas.md](figuras-chartistas.md) (roles y sesgo tradicional),
  [instancia-de-figura.md](instancia-de-figura.md) (identidad, ciclo de vida y evidencia de una
  figura), [tendencia-estructural.md](tendencia-estructural.md) y
  [contexto-y-tendencia.md](contexto-y-tendencia.md) (tendencia previa, para `context_compatible`),
  [detectores-de-expansion.md](detectores-de-expansion.md) sección 10.4, 10.5 y 10.10 (el diamante,
  origen del cálculo estricto de procedencia que aquí se generaliza) y
  [fibonacci-retroceso.md](fibonacci-retroceso.md) sección 3 (comparado y **no** igualado, sección 4
  de este documento).
- **Relacionado:** `PATTERN-PROVENANCE-001` (Notion) — completada el mismo día (PR #79, #80 y #81):
  las 19 figuras que no son el diamante, y Fibonacci, ya calculan procedencia con la definición
  estricta de la sección 4.1. Este contrato no dependía de que esa tarea estuviera hecha para poder
  escribirse: definía qué ocurría **mientras no lo estaba** (sección 4.3), que ahora queda como
  registro histórico de lo que se corrigió, no como estado vigente.

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

### 4.3 Sin procedencia demostrada, `UNPROVEN`: qué la produce hoy

`UNPROVEN` no es «no se sabe si es `LIVE`»: es **la ausencia de una demostración** de que la
procedencia satisface la definición estricta de la sección 4.1, para una instancia y un instante
concretos. **Actualización (2026-09-27, el mismo día):** las dos brechas que motivaron esta sección
al escribirla ya se cerraron:

1. ~~El detector de origen no calcula procedencia en absoluto.~~ Las 19 figuras del catálogo que no
   son el diamante ya calculan `market_formed_at` y `known_at` para su ruptura, con la evidencia
   `BREAKOUT_TIMING` (`PATTERN-PROVENANCE-001`: PR #80, triángulos, rectángulo, cuñas, formación
   expansiva, banderas y banderines; PR #81, las 8 figuras de reversión).
2. ~~Fibonacci calcula algo con otro nombre que no está verificado contra la definición
   estricta.~~ El `known_at` de Fibonacci se corrigió (PR #79, `fibonacci-retroceso.md` sección 3)
   para depender de toda la vela de `A` a `B`, no solo de `B`; su `OPERABLE` ya satisface la
   sección 4.1 y se trata como `LIVE`.

Con esto, `UNPROVEN` hoy solo se produce por **falta de datos en un caso concreto**, nunca por
falta de cálculo:

- El llamador no incluyó, en `closed`/`received_at`, alguna de las velas de las que depende la
  validez de la figura (el ancla, la que confirma el último pivote, o una intermedia) — probado
  para Fibonacci (`test_without_the_full_a_to_b_stretch_known_at_cannot_be_proven_even_if_b_was_received`)
  y para cada detector, con su propio caso equivalente.
- No se pasó ningún registro de recepción en absoluto (`received_at` ausente): entonces ninguna
  figura de esa evaluación puede ser `LIVE`, por diseño (fail-closed).

Este listado es de estado, no de contrato: si una figura futura, o una versión nueva de un detector
existente, todavía no calculara procedencia, su evidencia volvería a ser `UNPROVEN` por esa razón,
sin que este documento cambiara de versión.

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

**Límite conocido de la v1 (al implementar, 2026-09-27):** `pattern_hypothesis.py` solo añade una
evaluación cuando **la propia instancia de origen** avanza; un cambio en el conjunto de soporte o
conflicto que ocurre *entre* dos evaluaciones de la fuente se recoge en la evaluación siguiente de
la fuente, no en el instante exacto en que ocurrió. Sigue sin look-ahead (cada evaluación solo lee
el pool tal como estaba en su propio instante), simplemente es más gruesa que el límite teórico que
describe el párrafo anterior. Una versión futura podría re-evaluar también en cada instante en que
cambia el pool, no solo cuando cambia la fuente.

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

### 7.2 Hipótesis descriptiva, por falta de datos concretos (no por falta de cálculo)

Un `ASCENDING_TRIANGLE` en la misma serie rompe por la resistencia horizontal, `CONFIRMED_UP`. El
detector sí calcula procedencia (`PATTERN-PROVENANCE-001`), pero para esta instancia concreta el
`closed`/`received_at` que se le pasó no incluía la recepción de uno de los contactos intermedios
del canal — por ejemplo, porque la ventana de velas entregada no llegaba tan atrás.

- `hypothesis_kind`: sin rol `EXPANSION`; tendencia previa `UPTREND` coincide con la ruptura `UP` y
  el rol `CONTINUATION` → `CONTINUATION`. `context_compatible`: `true`.
- `hypothesis_direction`: `UP`.
- Procedencia de la evidencia de origen: **`UNPROVEN`** (falta de datos, sección 4.3: falta la
  recepción de una vela de la que depende la validez del canal, no una limitación del detector). →
  `operability`: `UNPROVEN`. La hipótesis se registra completa, con su dirección y su contexto,
  pero **no se ofrece como base operable** de nada en tiempo real.

### 7.3 Hipótesis descriptiva, retrospectiva

Un `TRIPLE_BOTTOM` en la misma serie rompe al alza, `CONFIRMED_UP`, pero la vela de esa ruptura
abrió **antes** de que la figura quedara confirmada en el mercado (`market_formed_at`, sección 4.1):
la figura todavía no existía cuando esa vela abrió — se conoce ya resuelta, por reconstrucción, no en
directo. Se usa como figura de `conflicting_patterns` de una hipótesis bajista, por su lectura
alcista.

- Procedencia de esa evidencia para este contrato: **`RETROSPECTIVE`** (la vela abrió antes de
  `market_formed_at`, sección 4). Se anota en la entrada de `conflicting_patterns` con su
  procedencia, para que quien lea la hipótesis sepa que ese conflicto es una descripción a toro
  pasado, no algo que se pudo ver en vivo; si esta fuera la figura de origen en vez de un conflicto,
  la hipótesis resultante sería `RETROSPECTIVE`, nunca `OPERABLE`.

**Nota de alcance (2026-09-27, al implementar):** `supporting_patterns`/`conflicting_patterns`
admiten otras `PatternInstance` (sección 3.3), nunca una medición de Fibonacci (`FibonacciObservation`,
un modelo de dominio distinto, sin identidad de figura ni ciclo de vida propio). Combinar Fibonacci
como evidencia de una hipótesis queda fuera de esta v1; el ejemplo de esta sección usaba antes un
impulso de Fibonacci por error y se corrigió a una figura chartista para no contradecir la
sección 3.3.

## 8. Lo que este documento no decide

- Cómo usa el punto 6 (`StrategySpec`) `supporting_patterns`, `conflicting_patterns` y
  `operability` para exigir condiciones obligatorias o confirmaciones: esta capa entrega los datos,
  no las reglas de decisión.
- Objetivos de precio, entradas, vencimientos ni tamaño (puntos 8, 10, 11 y siguientes).
- Correlación entre temporalidades o instrumentos distintos (fuera del alcance v1, sección 3.3).
- Usar Fibonacci (`FibonacciObservation`) como `supporting_patterns`/`conflicting_patterns`: esta
  v1 solo combina `PatternInstance` (sección 3.3, 7.3); unificar los dos modelos es de una versión
  futura, si se decide.
- Hipótesis pre-ruptura (`BIDIRECTIONAL`), aplazadas a una versión futura (sección 2).
- Cómo se calcula la procedencia dentro de cada detector: eso lo hicieron `PATTERN-PROVENANCE-001`
  (las 19 figuras que no son el diamante) y la corrección propia de Fibonacci (`FIB-CALC-001`,
  PR #79) — ninguna de las dos fue parte de este documento ni de su PR, aunque ya estén hechas.
- Persistencia (tabla, migración, retención) ni exposición (API, pantalla): mismo alcance que
  `instancia-de-figura.md`, sección 1.

## 9. Criterios de aceptación de esta tarea

- [x] `PatternHypothesis`/`HypothesisEvaluation` con identidad estable y evolución de solo-añadir,
      igual que `PatternInstance` (secciones 2 y 6). Implementado en `pattern_hypothesis.py`.
- [x] Procedencia de evidencia en cuatro estados, con `UNPROVEN` como valor fail-closed por defecto
      cuando no se demuestra la definición estricta (sección 4). `evidence_provenance()` exige
      `known_at` presente en la evidencia del detector, no solo el nombre `provenance`.
- [x] `LIVE`/`OPERABLE` de un detector de origen no se aceptan como equivalentes solo por el nombre
      sin verificar la definición estricta (sección 4.3) — verificado para las 19 figuras y para
      Fibonacci; la misma verificación se repite para cualquier detector nuevo.
- [x] Ninguna hipótesis es `OPERABLE` a partir de evidencia `UNPROVEN` de su figura de origen, sola
      o combinada con evidencia de soporte de mejor procedencia (sección 5). Probado explícitamente
      (`test_an_unproven_source_never_becomes_operable_however_good_its_support`).
- [x] Instantes necesarios (`market_formed_at`, `known_at`, apertura de la vela juzgada)
      especificados de forma general, no solo para el diamante (sección 4.1) — reutilizados tal
      cual los deja `PATTERN-PROVENANCE-001` en la evidencia de cada figura, no recalculados aquí.
- [x] Recepciones desordenadas: `known_at` como máximo de llegadas, nunca por orden de calendario
      (sección 4.2) — garantizado por `PATTERN-PROVENANCE-001`/Fibonacci, de donde esta capa lee.
- [x] Replay estable: una evaluación ya registrada no cambia al añadir datos futuros (sección 6).
      Probado (`test_replay_is_stable_a_prefix_of_the_series_gives_the_same_early_evaluations`).
- [x] Ejemplos de hipótesis operable (diamante) y descriptivas (figura con datos incompletos,
      figura retrospectiva) (sección 7).
- [x] Ninguna puntuación agregada ni `probability` (sección 1). Probado
      (`test_a_hypothesis_never_carries_a_probability_or_a_score`).
- [x] Una hipótesis aislada nunca llama a executor ni a broker (sección 1): el módulo no importa
      ninguna infraestructura de ejecución.

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
7. **`OPERABLE` de Fibonacci se trató como `UNPROVEN`, no como `LIVE`**, hasta que su `known_at` se
   corrigiera para incluir la recepción de `A` y de las velas intermedias del impulso (comparación
   hecha el 2026-09-27, registrada en `PATTERN-PROVENANCE-001`). **Resuelto el mismo día (PR #79):**
   ya se trata como `LIVE` (sección 4.3).
8. **Alcance v1 limitado a una sola serie** para soporte y conflicto: evita inventar una regla de
   correlación multi-temporalidad que no se ha pedido todavía.
9. **Instancias cubiertas por solapamiento no cuentan como evidencia**, generalizando la regla del
   diamante (`held_by_overlap`) a cualquier figura futura que pueda tener el mismo problema.
10. **La procedencia se lee, no se recalcula.** `pattern_hypothesis.py` no vuelve a computar
    `known_at`: lee `BREAKOUT_TIMING`/`DIAMOND_TIMING` de la evidencia que `PATTERN-PROVENANCE-001`
    ya deja en cada `PatternEvaluation`, y solo aplica su propia regla fail-closed (sección 4.3:
    sin `known_at` en la evidencia, `UNPROVEN`, sin mirar qué dice `provenance`). Evita duplicar la
    lógica de `known_at_of`/`provenance_of` (`pattern_detection.py`) en una segunda capa.
11. **Una evaluación es nueva si algo cambia, incluida su propia evidencia** (`_same_content`
    compara también `evidence`, no solo los campos de más alto nivel): así un origen que pasa de
    `BREAKOUT_PENDING_CONFIRMATION` a `CONFIRMED_UP` siempre añade una evaluación, aunque la
    dirección, el tipo y la procedencia leída no cambien, porque `HYPOTHESIS_SOURCE` sí cambia
    (`source_state`, `breakout_confirmed`).
12. **Un cierre sin ruptura propia (`INVALIDATED` por `SUPERSEDED`/`GEOMETRY_BROKEN`) hereda el
    último `hypothesis_kind`/`context_compatible`/`operability` conocidos**, sin recalcularlos: no
    hay ruptura nueva de la que leerlos, y no se inventan.
13. **Límite de v1: solo el avance de la fuente dispara una evaluación nueva**, no un cambio del
    pool por sí solo (sección 6, «Límite conocido»). Documentado, no oculto; revisable en una
    versión futura.
