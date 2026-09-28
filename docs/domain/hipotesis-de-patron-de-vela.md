# Hipótesis de patrón de vela: descriptiva, nunca predictiva (v1)

- **Estado:** vigente. Contrato temporal, antes de escribir código.
- **Fecha:** 2026-09-29.
- **Tarea:** POINT4-HYPOTHESIS-001 (6 de 7 del punto 4). Reparto revisado con Jessica antes de
  empezar (corregido el 29-09-2026): ver «Qué se reutiliza y qué no» y «Decisiones de alcance v1».
- **Depende de:** [instancia-de-patron-de-vela.md](instancia-de-patron-de-vela.md) (identidad y
  ciclo de vida de un `CandlePatternInstance`), [detectores-de-una-vela.md](detectores-de-una-vela.md)
  sección 4 bis (`AmbiguousGeometry`), [localizacion-de-patron-de-vela.md](localizacion-de-patron-de-vela.md)
  (`PatternLocation`, `operability`, `computed_at`) e [hipotesis-de-figura.md](hipotesis-de-figura.md)
  (el mismo problema, ya resuelto para figuras chartistas — reutilizado, no reinventado donde sirve).
- **Código:** `backend/src/freyja_backend/domain/candlestick_hypothesis.py` (pendiente de esta
  tarea). Dominio puro, sin E/S.

## 1. Qué es y qué no es esta hipótesis

Una **hipótesis de patrón de vela** es un registro **descriptivo**: qué patrón de vela se confirmó,
en qué contexto de tendencia, cerca de qué estructura de precio (localización), y qué otros
patrones de vela coexistentes lo acompañan o lo contradicen. Mismo estilo que `PatternHypothesis`:
identidad estable, historial de solo añadir, autosuficiente.

- **No es una señal, una orden ni una entrada.** Igual que `hipotesis-de-figura.md`, sección 1.
- **No es una probabilidad ni una puntuación.** Varios patrones pueden coincidir, contradecirse o
  quedar neutrales; el contrato **conserva esa discrepancia**, nunca la resuelve en una cifra.
- **No elige en silencio.** Un patrón contradictorio permanece visible (sección 5).
- **No afirma una dirección de la próxima vela.** Esta es la diferencia deliberada frente a
  `hipotesis-de-figura.md` (sección 2 bis): `CONFIRMED` en un patrón de vela significa «la
  morfología y su contexto exigido coinciden con la definición del catálogo»
  (`instancia-de-patron-de-vela.md`, `candlestick_pattern.py`: "it decides nothing about whether a
  candle is really a hammer... The traditional bias of a pattern is tradition, not evidence"), no
  «el mercado se movió, ni se moverá, como la tradición sugiere». Ninguna evaluación de esta pieza
  fija `target_scope` en `NEXT_CANDLE` ni `MULTI_CANDLE_MOVE`, ni ningún campo equivalente a
  `hypothesis_direction` con un valor UP/DOWN que se pudiera leer como predicción — ver sección 2
  bis y «Decisiones de alcance v1».

## 2. Cuándo existe una hipótesis

Nace de un `CandlePatternInstance` de origen (`source_candle_pattern_instance_id`) en el primer
instante en que alcanza `CONFIRMED` (`candlestick_pattern.CandlePatternState`) — **nunca antes**:
`FORMING`, `MORPHOLOGICALLY_VALID`, `CONTEXT_VALID`, `PENDING_CONFIRMATION` e `INSUFFICIENT_DATA`
no producen hipótesis, exactamente por lo que ya impide `AmbiguousGeometry` (sección 3): afirmar
algo de una geometría que no ha terminado de identificarse sería tratar una lectura parcial como si
fuera un hecho cerrado.

**Disparador propio, no el de figuras chartistas.** `hipotesis-de-figura.md` (sección 2) dispara en
la primera «ruptura real» (`BREAKOUT_PENDING_CONFIRMATION`/`CONFIRMED_UP`/`CONFIRMED_DOWN`) porque
una figura chartista *rompe* una frontera. Un patrón de vela no rompe nada: su propio
`CandlePatternState.CONFIRMED` (morfología + contexto exigido verificados, sección 3 de
`instancia-de-patron-de-vela.md`) es su único hecho resuelto. Forzar los estados de ruptura de
figuras sobre patrones de vela sería inventar un evento que no existe en este dominio — exactamente
lo que Jessica pidió evitar.

- Un patrón que nunca llega a `CONFIRMED` (se queda en `PENDING_CONFIRMATION`, se invalida antes, o
  falla — `FAILED`, en los patrones de tres velas que exigen confirmación) nunca tuvo hipótesis que
  cerrar: no se crea ninguna.
- La hipótesis avanza con su origen, sin cambiar de identidad: una evaluación nueva cuando el
  `CandlePatternInstance` avanza de estado, o cuando cambia el conjunto de patrones que lo
  acompañan o lo contradicen en un instante posterior (mismo límite de v1 que `hipotesis-de-figura.md`
  sección 6, «Límite conocido»: un cambio del pool *entre* dos evaluaciones de la fuente se recoge
  en la evaluación siguiente de la fuente, no en su propio instante).
- `INVALIDATED` (`SUPERSEDED`/`GEOMETRY_BROKEN`) cierra la hipótesis con una evaluación final. `FAILED`
  (patrones de tres velas sin confirmar) también cierra: el patrón no llegó a ser lo que su
  geometría inicial sugería, y no hay nada más que describir de él.

## 2 bis. Ausencia deliberada de `hypothesis_direction`/`NEXT_CANDLE`/`MULTI_CANDLE_MOVE`

`hipotesis-de-figura.md` deriva `hypothesis_direction` de la **dirección real observada** de una
ruptura — un hecho de mercado ya ocurrido, no una predicción (`traditional_bias` explícitamente
excluido de esa derivación, sección 3.1). Un patrón de vela no tiene ese hecho equivalente: no hay
ninguna ruptura cuya dirección real se pueda leer. La única fuente posible de "dirección" sería el
`traditional_bias` del catálogo (`CandleBias`) — y **ese es precisamente el sesgo que
`candlestick_pattern.py` ya declara "tradición, no evidencia"**.

Por eso esta pieza, en v1:

- **No incluye un campo de dirección afirmada** (ni `UP`/`DOWN`, ni un `BIDIRECTIONAL` reservado a
  la espera de justificarlo): no hay ningún hecho, hoy, del que derivarlo sin copiar el sesgo en
  crudo.
- **`target_scope` sigue siendo `MARKET_DIRECTION`**, el mismo y único valor que produce
  `hipotesis-de-figura.md` hoy, reutilizando literalmente `pattern_hypothesis.TargetScope`.
  `NEXT_CANDLE`/`MULTI_CANDLE_MOVE` **permanecen reservados, sin producir**, exactamente igual que
  en `hipotesis-de-figura.md` sección 3.2 — activarlos exigiría una `StrategySpec` que declare el
  horizonte, y eso sigue sin existir.
- **`traditional_bias` (`CandleBias`) se registra como evidencia descriptiva**, copiado tal cual
  del catálogo (`CandlePatternType.definition.traditional_bias`), nunca usado para fijar un
  resultado de la hipótesis ni para filtrar nada — mismo principio que `hipotesis-de-figura.md`
  aplica al sesgo tradicional de una figura.

## 3. `AmbiguousGeometry`: observable, nunca evidencia

`AmbiguousGeometry` (`candlestick_single.py`, sección 4 bis de `detectores-de-una-vela.md`) no
tiene `pattern_type` ni `CandlePatternState` — deliberadamente, para que ningún consumidor,
"agregador de hipótesis incluido" (su propio docstring), pueda tratarla como si fuera un patrón
confirmado. Esta pieza solo acepta `CandlePatternInstance` como origen y como miembros del *pool*
de patrones coexistentes (sección 5): una `AmbiguousGeometry` no tiene el tipo necesario para
entrar en ninguno de los dos, así que queda excluida **por construcción**, no por una regla que se
pueda olvidar. Se prueba explícitamente (sección 8): un escenario con una `AmbiguousGeometry` real
junto a instancias confirmadas no cambia el resultado de ninguna hipótesis frente al mismo
escenario sin ella.

## 4. Localización y operabilidad: nunca optimista

Cuando la localización de un patrón (`PatternLocation`/`LocationEvaluation`,
`localizacion-de-patron-de-vela.md`) está disponible para el patrón de origen, su evaluación más
reciente conocida en el instante de la hipótesis se registra como evidencia (`LOCATION`, sección 6)
y su `operability` participa en el cálculo de la operabilidad de esta hipótesis (más abajo).

**La operabilidad de esta pieza integra dos fuentes, y toma la peor de las dos, nunca la mejor:**

1. **La operabilidad de la localización usada** (`PatternLocation.latest.operability`, cuando hay
   una localización que citar) — `OPERABLE`/`RETROSPECTIVE`/`UNPROVEN`, tal cual la calculó
   `candlestick_location.py`, nunca recalculada.
2. **La disponibilidad real de la propia vela del patrón.** `candlestick_single.py`/`multi.py` no
   distinguen el cierre de mercado de la vela de cuándo Freyja la recibió realmente
   (`localizacion-de-patron-de-vela.md`, sección 2 bis, límite conocido) — no existe hoy ningún
   mecanismo que demuestre que el patrón de origen fue conocible en vivo. Sin esa prueba, esta
   pieza no puede demostrar `LIVE`: su propio nivel, aislado, es siempre `UNPROVEN` (fail-closed,
   mismo principio que `evidence_provenance` aplica cuando falta `known_at` —
   `pattern_hypothesis.py`, reutilizado, no reinventado).

`operability = worst(UNPROVEN, operabilidad_de_la_localización_si_hay)` — con la función
`_worst_operability` ya existente en `candlestick_location.py`, reutilizada, no duplicada. En la
práctica, v1 nunca produce `OPERABLE`: es la consecuencia honesta, no un caso especial, de que
ningún patrón de vela puede hoy demostrar disponibilidad en vivo. **Ninguna evidencia
`RETROSPECTIVE` o `UNPROVEN` puede habilitar `OPERABLE`, sola o combinada con otra mejor** — mismo
principio, sin excepciones, que `hipotesis-de-figura.md` sección 5.

## 5. Patrones coexistentes: soporte y conflicto, sin puntuación

Mismo alcance v1 que `hipotesis-de-figura.md` sección 3.3: la misma serie (instrumento, fuente,
temporalidad), sin puntuación, sin elegir en silencio.

- Se consideran las demás `CandlePatternInstance` de esa serie cuya evaluación más reciente,
  conocida en un instante **igual o anterior** al de la hipótesis, está `CONFIRMED`. Cualquier otro
  estado (`FORMING`, `MORPHOLOGICALLY_VALID`, `CONTEXT_VALID`, `PENDING_CONFIRMATION`,
  `INSUFFICIENT_DATA`) no tiene lectura propia todavía: **no entra en ninguna de las dos listas**.
- **La lectura comparada no es una dirección afirmada de la hipótesis (sección 2 bis): es la
  comparación entre el `traditional_bias` de dos patrones confirmados**, un hecho sobre cómo se
  relacionan entre sí dos evidencias, no una predicción del conjunto — **y solo cuando ambos, el de
  origen y el comparado, tienen sesgo fijo del catálogo** (`BULLISH`/`BEARISH`, nunca
  `CONTEXT_DEPENDENT`/`NONE`): `BULLISH_ENGULFING`, `BEARISH_ENGULFING`, `PIERCING_PATTERN`,
  `DARK_CLOUD_COVER`, `MORNING_STAR`, `EVENING_STAR`, `THREE_WHITE_SOLDIERS`, `THREE_BLACK_CROWS`,
  `THREE_INSIDE_UP`, `THREE_INSIDE_DOWN` (`candlestick_pattern.CANDLE_PATTERN_CATALOGUE`, nunca
  reescrito aquí, siempre leído de ahí).
  - **Decisión de alcance v1, deliberadamente conservadora:** los patrones `CONTEXT_DEPENDENT`
    (p. ej. `HAMMER`/`HANGING_MAN`, misma geometría, sesgo opuesto solo por el contexto que cada uno
    exige) sí producen hipótesis cuando son el origen (siguen siendo `CONFIRMED`, con su propio
    `HYPOTHESIS_SOURCE`, sección 6) pero **no participan en la comparación de soporte/conflicto**,
    ni como origen ni como miembro del pool: derivar una "lectura efectiva" para ellos a partir de
    qué tendencia previa exigió cada uno sería una inferencia **nueva**, no publicada hoy como un
    hecho propio del catálogo, y exactamente el tipo de paso que Jessica pidió no dar todavía. Se
    tratan igual que un patrón sin lectura (`CandleBias.NONE`, `DOJI`): observables, nunca
    comparados. Revisable en una versión futura, con su propia justificación.
  - Coincide con el sesgo fijo del patrón de origen → `supporting_candles`; lo contradice →
    `conflicting_candles`. **Ambas listas se conservan siempre, incluida cuando hay conflicto**
    (contrato, sección 1): ninguna entrada se descarta por tener peor operabilidad o por ser mayoría
    o minoría.
- Cada entrada guarda `candle_pattern_instance_id`, `pattern_type`, el sesgo efectivo comparado y su
  propia `operability` (sección 4, calculada igual para cada patrón del pool que para el de origen)
  — nunca participa en la operabilidad de la hipótesis (igual que en `hipotesis-de-figura.md`,
  sección 5: solo la del origen decide).
- **Patrones solapados** (anclas que comparten una o más velas, p. ej. un patrón de una vela cuya
  única vela es también parte de un patrón de dos velas confirmado) se incluyen igual: compartir
  velas no es un criterio de exclusión aquí — la exclusión ya la resuelve el propio detector de
  origen (`SharedGeometry`/`AmbiguousGeometry`, sección 3) antes de que exista un
  `CandlePatternInstance` con el que trabajar. Probado explícitamente (sección 8).

## 6. Evidencia

- `HYPOTHESIS_SOURCE`: estado del patrón de origen en este instante, su `traditional_bias` (crudo,
  etiquetado como tal), y su procedencia/operabilidad de disponibilidad (sección 4) — autosuficiente,
  igual que `HYPOTHESIS_SOURCE` en `hipotesis-de-figura.md`.
- `LOCATION`: solo si hay una localización que citar — su `state`, `operability` y `evaluated_at`,
  copiados de `LocationEvaluation`, nunca recalculados.
- `RELATED_CANDLE`: una por cada patrón en `supporting_candles`/`conflicting_candles`, con su propio
  `pattern_type`, sesgo efectivo comparado y `operability`.

## 7. Identidad, versión y evolución

- **Registro propio** (`CandleHypothesis`/`CandleHypothesisEvaluation`), no una `PatternHypothesis`:
  las máquinas de estado de origen (ruptura vs. confirmación) son distintas (sección 2), así que
  forzar el mismo tipo de registro escondería esa diferencia en vez de expresarla.
- **Reutiliza, no reinventa**: `Operability`/`operability_of`/`evidence_provenance` y
  `_worst_operability` (de `pattern_hypothesis.py`/`candlestick_location.py`), `PatternEvidence`/
  `evidence()` (de `chart_pattern.py`), el mismo estilo de identidad estable (UUID v5 del origen +
  versión de definición) y de historial de solo añadir que `PatternHypothesis`/`PatternLocation`.
  No reutiliza `HypothesisEvaluation`/`HypothesisDirection` tal cual: sus invariantes (`UNKNOWN`
  cierra la hipótesis; la dirección viene de una ruptura real) no describen correctamente un patrón
  de vela (sección 2 bis).
- **Versión propia**, independiente de `single-candle-params-v1`/`multi-candle-params-v1`/
  `three-candle-params-v1`/`candle-location-params-v1`: no introduce parámetros numéricos nuevos en
  v1 (no hay umbral que ajustar), así que no hay entrada nueva para PARAMS-VALIDATION-001 todavía.
- **Replay estable y sin reescritura hacia atrás**: mismos principios que `hipotesis-de-figura.md`
  sección 6 y `localizacion-de-patron-de-vela.md` sección 2, verificados con pruebas.

## 8. Pruebas exigidas antes de cerrar la tarea

1. **Geometría ambigua no cuenta como evidencia.** Un `AmbiguousGeometry` real, junto a instancias
   `CandlePatternInstance` confirmadas del mismo pool, no cambia el resultado de ninguna hipótesis
   frente al mismo escenario sin ella (sección 3).
2. **Patrones solapados.** Dos `CandlePatternInstance` cuyas anclas comparten una vela (p. ej. la
   vela final de un patrón de una vela es también la primera de un patrón de dos velas confirmado)
   se evalúan ambas correctamente como evidencia coexistente, sin duplicarse ni excluirse entre sí
   por el solapamiento (sección 5).
3. **Evidencia contradictoria permanece visible.** Dos patrones confirmados con sesgo efectivo
   opuesto (uno alcista, uno bajista) en la misma serie: ambos aparecen, uno en
   `supporting_candles`/uno en `conflicting_candles` del otro según corresponda — ninguno se
   descarta, ninguna puntuación los resuelve (sección 5).
4. **Ninguna evidencia retrospectiva o `UNPROVEN` habilita `OPERABLE`.** Ni sola, ni acompañada de
   evidencia de mejor operabilidad (sección 4).
5. **`CONFIRMED` no es predicción.** Ninguna evaluación de esta pieza lleva un campo de dirección
   afirmada, ni `target_scope` distinto de `MARKET_DIRECTION` (sección 2 bis).

## 9. Lo que este documento no decide

Las cinco funciones dependientes de `StrategySpec` (`REQUIRED`/`CONFIRMATION`/`FILTER`/`CONFLICT`/
`INFORMATIONAL`, punto 6, sin implementar) — diferidas, igual que en `hipotesis-de-figura.md`
sección 8; activar `NEXT_CANDLE`/`MULTI_CANDLE_MOVE`; afirmar una dirección de la próxima vela o de
varias; horizonte, entrada, invalidación; combinar Fibonacci como evidencia (mismo límite que
`hipotesis-de-figura.md`); persistencia, señales, órdenes.
