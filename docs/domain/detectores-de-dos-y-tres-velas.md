# Detectores de patrones de dos y tres velas (v1)

- **Estado:** vigente. Cubre los catorce patrones de dos y tres velas del catálogo:
  `BULLISH_ENGULFING`, `BEARISH_ENGULFING`, `BULLISH_HARAMI`, `BEARISH_HARAMI`, `TWEEZER_BOTTOM`,
  `TWEEZER_TOP`, `PIERCING_PATTERN`, `DARK_CLOUD_COVER`, `MORNING_STAR`, `EVENING_STAR`,
  `THREE_WHITE_SOLDIERS`, `THREE_BLACK_CROWS`, `THREE_INSIDE_UP`, `THREE_INSIDE_DOWN`.
- **Fecha:** 2026-09-28 (dos velas), 2026-09-29 (tres velas y correcciones).
- **Tarea:** POINT4-MULTI-001 (4 de 7 del punto 4). Implementada en dos entregas (una por
  familia): dos velas primero (PR #90), tres velas después (PR #91), porque las de tres velas
  reutilizan la geometría del harami.
- **Depende de:** [patrones-de-vela.md](patrones-de-vela.md) (qué es cada patrón) y
  [instancia-de-patron-de-vela.md](instancia-de-patron-de-vela.md) (cómo se representa). Reutiliza
  el clasificador de tendencia del punto 2 (`classify_trend`), igual que
  [detectores-de-una-vela.md](detectores-de-una-vela.md).
- **Código:** `backend/src/freyja_backend/domain/candlestick_multi.py`. Dominio puro, sin E/S.
  Pruebas en `backend/tests/unit/test_candlestick_multi.py`.

Como en `detectores-de-una-vela.md`: cada patrón se resuelve por completo en el instante en que
cierra su última vela (dos o tres, según el patrón), sin instancias incrementales, porque la
tendencia previa es una función pura de velas todavía más antiguas.

## 1. Qué hace un detector y qué no

- **Es una función pura de las velas cerradas implicadas y la tendencia inmediatamente anterior a
  la primera de ellas.**
- **Orden temporal exacto**: las velas del patrón son consecutivas, en el orden del catálogo; no
  se buscan combinaciones fuera de orden.
- **Primero geometría, después contexto**, igual que en el punto anterior.
- **Sin ruptura ni confirmación adicional para las de dos velas** (columna «Confirmación»: «No»
  en las ocho). **Las de tres velas sí confirman con su propia tercera vela** (columna
  «Confirmación»: «Sí»): la geometría de las dos primeras, por sí sola, es como mucho un patrón de
  dos velas ya existente (el harami); la tercera vela no es una evaluación posterior de la misma
  instancia, es lo que la hace nacer ya `CONFIRMED` (mismo principio que
  `detectores-de-una-vela.md`, sección 6: nace resuelta, sin una fase `PENDING_CONFIRMATION`
  separada).
- **Ninguna vela abierta produce nada.** Solo se leen velas cerradas.
- **No genera señal, orden ni probabilidad.**

## 2. Parámetros: dos versiones independientes, nunca una compartida

**Provisionales y sin validar** (PARAMS-VALIDATION-001), razonados a partir de definiciones
tradicionales de análisis técnico. Dos velas y tres velas se versionan **por separado**: ver la
sección 9 («Versionado») para por qué.

### 2.1 Dos velas (`multi-candle-params-v1`, `MultiCandleParams`)

| Parámetro | Valor | Significado |
| --------- | ----- | ----------- |
| `harami_outer_min_body_ratio` | 0,50 | La vela 1 del harami es «de cuerpo amplio»: su cuerpo es al menos esta fracción de su propio rango. |
| `harami_inner_max_body_ratio` | 0,50 | La vela 2 del harami es «de cuerpo pequeño»: su cuerpo es como mucho esta fracción del cuerpo de la vela 1. |
| `tweezer_tolerance` | 0,10 | Dos mínimos (o máximos) son «prácticamente iguales» si difieren, como mucho, esta fracción de la media de los rangos de las dos velas. |
| `pivot_params`, `trend_params`, `min_history` | los del punto 2 | Los que usa `classify_trend` para la tendencia previa. |

### 2.2 Tres velas (`three-candle-params-v1`, `ThreeCandleParams`)

| Parámetro | Valor | Significado |
| --------- | ----- | ----------- |
| `harami_outer_min_body_ratio` | 0,50 | **Copia propia** del umbral de la vela 1 del harami, leída aquí para `THREE_INSIDE_UP`/`DOWN` y para la vela 1 de las estrellas — nunca de `MultiCandleParams` (sección 9). |
| `harami_inner_max_body_ratio` | 0,50 | Copia propia, igual razón. |
| `min_body_ratio` | 0,30 | La vela 2 de `MORNING_STAR`/`EVENING_STAR` tiene un cuerpo como mucho esta fracción de su propio rango (o es un doji). |
| `gap_min_fraction` | 0,10 | Con `GAP_REQUIRED`: el hueco entre cuerpos (vela 1 a vela 2) es al menos esta fracción del cuerpo de la vela 1. |
| `gap_policy` | `GAP_NOT_APPLICABLE` | La política de gaps vigente (sección 6). |
| `three_soldiers_upper_wick_max_ratio` | 0,20 | En `THREE_WHITE_SOLDIERS`/`THREE_BLACK_CROWS`, la mecha del lado contrario a la tendencia de cada vela es como mucho esta fracción de su rango («mechas superiores pequeñas»). |
| `pivot_params`, `trend_params`, `min_history` | los del punto 2 | Los que usa `classify_trend`. |

`ThreeCandleParams.harami_params()` construye, a partir de sus propios campos, un `MultiCandleParams`
con su **propia** versión (nunca `multi-candle-params-v1`) para que `is_bullish_harami`/
`is_bearish_harami` lo lean sin acoplar las dos familias (sección 9).

## 3. Contexto: el mismo principio que en el punto anterior

La tendencia previa se evalúa con `classify_trend`, con las velas **estrictamente anteriores a la
primera vela del patrón**, en el instante de su apertura — nunca con velas intermedias del propio
patrón. Como en `detectores-de-una-vela.md`, es una función pura del pasado: no hay retraso de
confirmación de pivotes que resolver más tarde, así que ninguna instancia de estas familias
necesita una segunda evaluación.

- Ningún patrón de esta tarea tiene una pareja de geometría compartida (a diferencia del martillo
  o el martillo invertido): cada geometría de esta tarea tiene un único nombre posible. Por tanto
  no existe aquí el caso de `AmbiguousGeometry` (`detectores-de-una-vela.md`, sección 4 bis): con
  la geometría cumplida, siempre nace una instancia; `CONFIRMED` si el contexto coincide,
  `MORPHOLOGICALLY_VALID` si no coincide o no se puede clasificar (con una excepción: bajo
  `GAP_REQUIRED`, un hueco insuficiente hace que `MORNING_STAR`/`EVENING_STAR` no exista en
  absoluto, ni siquiera `MORPHOLOGICALLY_VALID` — el hueco es parte de la geometría, no del
  contexto; sección 6).
- `THREE_WHITE_SOLDIERS`/`THREE_BLACK_CROWS` no exigen una tendencia previa estricta
  (`patrones-de-vela.md`: «ninguno estricto»), así que no tienen un valor `required`: su evidencia
  `CONTEXT` registra la tendencia observada como informativa, `compatible` siempre verdadero, y la
  instancia nace directamente `CONFIRMED` en cuanto la geometría se cumple.

## 4. Caché de tendencia previa: sin resultados obsoletos

**Dos correcciones (2026-09-29), dos revisiones de Jessica antes de la entrega 2/2.** Igual que
`detectores-de-una-vela.md`, este módulo recuerda la clasificación de tendencia ya calculada para
un instante, para no repetir el cálculo si varios patrones de la misma vela inicial la necesitan.

**Primera variante: vela que llega tarde.** La primera versión guardaba esa memoria
(`_prior_trends`) en el contexto, indexada solo por el instante (`at`): segura mientras se procesa
una sola llamada, pero no si el mismo contexto se reutiliza (`.at()`, su propio mecanismo de
repetición) entre dos llamadas donde una vela anterior, antes ausente, ya ha llegado — el segundo
cálculo debería ver más historia, pero la memoria le devolvía la clasificación antigua, calculada
con menos velas. Se reprodujo con una serie bajista real (`zigzag(DOWN)`, 115 velas): con solo las
60 más recientes, el clasificador da `INSUFFICIENT_DATA`; con las 115 completas, da `DOWNTREND`.
Reutilizando el mismo contexto, la segunda llamada devolvía `INSUFFICIENT_DATA` en lugar de
`DOWNTREND`. Primer arreglo: indexar por `(at, len(before))`, para que el número de velas leídas
formara parte de la clave.

**Segunda variante, que ese arreglo no cubría: vela corregida, mismo recuento.** Una vela
**anterior** al instante evaluado se corrige o se sustituye: mismo `open_time` del inicio del
patrón, la misma cantidad de velas en `before`, contenido distinto. `len(before)` no cambia, así
que la clave tampoco, y la memoria seguía devolviendo la clasificación antigua. Se reprodujo
reutilizando el mismo contexto con dos series reales de la misma longitud y el mismo instante
final (`zigzag(DOWN)` y la misma sustituida por `zigzag(UP)`, 115 velas cada una, mismo `at`): la
segunda llamada devolvía `DOWNTREND` (el valor de la primera) en vez de recalcular `UPTREND`.

Ninguna clave basada en `(instante, alguna medida de antes)` cubre esto en general: cualquier
resumen que no sea el contenido completo de `before` puede coincidir por accidente entre dos
series distintas. La corrección final **elimina la caché entre llamadas**: `_prior_trends` deja de
vivir en `MultiCandleContext`; la memoria pasa a ser un diccionario local que
`detect_multi_candle_patterns` crea al empezar y descarta al terminar, correcta por construcción
(nunca sobrevive para poder quedarse obsoleta) sin perder el ahorro dentro de una misma llamada. El
mismo defecto, en ambas variantes, se encontró y corrigió a la vez en `detectores-de-una-vela.md`
(`SingleCandleContext._prior_trends`).

## 5. Dos velas: geometría exacta

Sea cuerpo, mecha superior e inferior de cada vela, y `c1`/`c2` las dos velas en orden.

- **`BULLISH_ENGULFING`**: `c1` bajista; `c2` alcista; `c2.open ≤ c1.close` y `c2.close ≥ c1.open`
  (el cuerpo de `c2` cubre por completo el de `c1`, límites inclusive). Sin umbral: es una
  comparación exacta de precios, tal como la describe el catálogo.
- **`BEARISH_ENGULFING`**: espejo (`c1` alcista, `c2` bajista, `c2.open ≥ c1.close`,
  `c2.close ≤ c1.open`).
- **`BULLISH_HARAMI`**: `c1` bajista con `body(c1)/range(c1) ≥ harami_outer_min_body_ratio`; `c2`
  alcista con `body(c2) ≤ harami_inner_max_body_ratio × body(c1)`, y `c2.open`, `c2.close`
  **estrictamente** dentro de `(c1.close, c1.open)` (el cuerpo de `c1`, ya que `c1` es bajista).
- **`BEARISH_HARAMI`**: espejo.
- **`TWEEZER_BOTTOM`**: `|c1.low − c2.low| ≤ tweezer_tolerance × (range(c1) + range(c2)) / 2`. Sin
  exigencia de color de vela (el catálogo no la pide).
- **`TWEEZER_TOP`**: espejo, sobre los máximos.
- **`PIERCING_PATTERN`**: `c1` bajista; `c2` alcista; `c2.open ≤ c1.close` (la lectura más laxa de
  «abre por debajo del mínimo (o del cierre) de la vela 1»: la más estricta —por debajo del
  mínimo— casi nunca ocurre en un mercado que cotiza en continuo, sin huecos reales, así que exigir
  solo esa invalidaría el patrón por construcción en `CRYPTO × SPOT`, igual que un hueco exigido
  sin política — ver `patrones-de-vela.md`, sección 2); `c2.close` estrictamente entre el punto
  medio de `c1` (`(c1.open + c1.close) / 2`) y `c1.open`, sin llegar a `c1.open` (si lo alcanzara o
  lo superara, es `BULLISH_ENGULFING`: los dos patrones no se solapan en el límite).
- **`DARK_CLOUD_COVER`**: espejo.

## 6. Tres velas: geometría exacta y política de gaps

Sea `c1`, `c2`, `c3` las tres velas en orden.

- **`MORNING_STAR`**: `c1` bajista con cuerpo amplio (`harami_outer_min_body_ratio`); `c2` con
  cuerpo pequeño (`body(c2)/range(c2) ≤ min_body_ratio`, incluye un doji); `c3` alcista que cierra
  dentro del cuerpo de `c1` o más allá (`c3.close ≥ (c1.open + c1.close) / 2`, la mitad del cuerpo
  de `c1`). El hueco entre `c1` y `c2` sigue la política de gaps:

  | Política | Qué exige |
  | -------- | --------- |
  | `GAP_REQUIRED` | `c2` debe abrir y cerrar fuera del cuerpo de `c1` (midiendo desde el extremo del cuerpo de `c1` más próximo hasta el de `c2` más próximo), con una separación de al menos `gap_min_fraction × body(c1)`; si no la alcanza, **el patrón no existe**, ni siquiera `MORPHOLOGICALLY_VALID` — el hueco es parte de la geometría, no del contexto. |
  | `GAP_OPTIONAL` | El hueco, si existe, se mide y se registra como evidencia `GAP`; su ausencia no impide el patrón. |
  | `GAP_NOT_APPLICABLE` (por defecto) | No se comprueba ningún hueco: solo se exige que `c2` tenga cuerpo pequeño. Sin evidencia `GAP`. |

  **`CRYPTO × SPOT` usa `GAP_NOT_APPLICABLE`** por defecto (cotiza en continuo, sin huecos reales
  — `patrones-de-vela.md`, sección 2); el resto de mercados quedan con `GAP_OPTIONAL` hasta que una
  tarea posterior revise el caso de un mercado con sesiones reales. Es una decisión técnica de
  esta tarea, versionada en `three-candle-params-v1` (sección 2.2).
- **`EVENING_STAR`**: espejo.
- **`THREE_WHITE_SOLDIERS`**: `c1`, `c2`, `c3` alcistas; `c2.close > c1.close`,
  `c3.close > c2.close`; `c2.open` y `c3.open` dentro del cuerpo de la vela anterior (entre su
  apertura y su cierre); mecha superior de cada vela ≤ `three_soldiers_upper_wick_max_ratio` de su
  propio rango.
- **`THREE_BLACK_CROWS`**: espejo (mecha **inferior** pequeña).
- **`THREE_INSIDE_UP`**: `c1`/`c2` cumplen la geometría de `BULLISH_HARAMI` (sección 5,
  reutilizada, no reescrita: ver sección 7), con los umbrales propios de `three-candle-params-v1`
  (sección 2.2, nunca los de `multi-candle-params-v1`); `c3` cierra por encima del máximo de `c1`
  (`c3.close > c1.high`).
- **`THREE_INSIDE_DOWN`**: espejo sobre `BEARISH_HARAMI` (`c3.close < c1.low`).

## 7. `THREE_INSIDE_UP`/`DOWN` no duplica el harami

`patrones-de-vela.md` (sección 6) deja escrito que `THREE_INSIDE_UP` «no es un patrón nuevo desde
cero: es un `BULLISH_HARAMI` confirmado», y que la forma exacta de implementarlo era una decisión
pendiente para quien lo construyera. Esta tarea la resuelve así:

- El detector de `THREE_INSIDE_UP` **reutiliza la misma función de geometría** que el detector de
  `BULLISH_HARAMI` (`is_bullish_harami`, pública) para juzgar `c1`/`c2` — una sola implementación,
  nunca dos copias de la misma comprobación — pero con los **umbrales propios** de
  `three-candle-params-v1`, nunca los de `multi-candle-params-v1` directamente (sección 9).
- **Ambas instancias coexisten**, con su propia identidad, igual que ya coexisten patrones con
  geometrías solapadas en el punto de una vela (pin bar y martillo, `detectores-de-una-vela.md`).
  `BULLISH_HARAMI` existe en cuanto cierra `c2`; `THREE_INSIDE_UP`, en cuanto cierra `c3` y
  confirma. No se invalida ni se reescribe el harami cuando nace el patrón de tres velas: son dos
  afirmaciones geométricas distintas y verificables por separado.
- **Evitar que HYPOTHESIS-001 las cuente dos veces** (el «no se cuenta el mismo hecho geométrico
  dos veces» de `patrones-de-vela.md`) es, como en el caso del pin bar, una regla de agregación de
  esa tarea, no de detección: aquí solo se garantiza que ambas instancias son reproducibles y que
  ninguna se fabrica ni se descarta por conveniencia.

## 8. Evidencia: `CONTEXT`, y `GAP` para las estrellas

Mismo formato que `detectores-de-una-vela.md` (sección 5) para `CONTEXT`. `MORNING_STAR` y
`EVENING_STAR`, bajo `GAP_REQUIRED` u `GAP_OPTIONAL`, llevan además una evidencia `GAP` con la
política aplicada, el hueco medido (como precio exacto, no como fracción — el umbral sí es una
fracción del cuerpo de `c1`), el hueco exigido y si se cumplió.

## 9. Versionado: dos familias, dos versiones, nunca una compartida

**Corrección (2026-09-29), revisión de Jessica antes de implementar las tres velas.** La primera
versión de este documento planeaba un único `multi-candle-detector-v1`/`multi-candle-params-v1`
para los catorce patrones, «porque comparten parámetros y regla de contexto en su totalidad» — una
afirmación que resultó falsa: las de tres velas necesitan umbrales que las de dos velas no leen
(`min_body_ratio`, `gap_min_fraction`, `gap_policy`, `three_soldiers_upper_wick_max_ratio`).

El problema no es solo de estilo: si las catorce compartieran una sola versión, cambiar un umbral
de `MORNING_STAR` obligaría a subir la versión que **también** llevan las instancias de
`BULLISH_ENGULFING` ya guardadas — la identidad de una figura que no cambió en absoluto cambiaría
igualmente, porque `derive_candle_pattern_instance_id` incluye `parameter_version`
(`instancia-de-patron-de-vela.md`, sección 4). «La misma figura, hallada de nuevo, es la misma
instancia» dejaría de cumplirse por un cambio ajeno.

La corrección, antes de escribir una sola línea de las tres velas:

- **Dos velas**: `MultiCandleParams`/`multi-candle-params-v1`, `MULTI_CANDLE_DETECTOR_VERSION`.
  Sin cambios respecto a la entrega 1/2: ningún campo nuevo, ninguna subida de versión.
- **Tres velas**: `ThreeCandleParams`/`three-candle-params-v1`, `THREE_CANDLE_DETECTOR_VERSION`,
  un conjunto propio, independiente.
- **El puente entre ambas** (`THREE_INSIDE_UP`/`DOWN` reutilizando el harami) no comparte versión:
  `ThreeCandleParams.harami_params()` construye un `MultiCandleParams` con los umbrales propios de
  `ThreeCandleParams` pero **estampado con la versión de `ThreeCandleParams`**, nunca con
  `multi-candle-params-v1`. Es el mismo recurso que usa `DiamondParams.channel_params()` en
  `pattern_detection.py` para reutilizar el canal de dos fronteras sin atar la identidad del
  diamante a `continuation-params-v1`. Con esto: cambiar un umbral de las estrellas o de los
  soldados nunca desplaza la identidad de `BULLISH_HARAMI`, y cambiar un umbral del harami de dos
  velas nunca desplaza la de `THREE_INSIDE_UP`. Verificado con pruebas que cambian un parámetro de
  una familia y comprueban que la identidad de la otra no se mueve.

## 10. Lo que este documento no decide

Qué política de gaps aplica a mercados distintos de `CRYPTO × SPOT` con sesiones reales (queda
`GAP_OPTIONAL` hasta revisarlo); cómo se combina esta evidencia con otra en una hipótesis
(POINT4-HYPOTHESIS-001, incluida la regla de no doble conteo del harami); persistencia, señales,
órdenes.

## 11. Decisiones técnicas tomadas al redactar

Registradas aquí para que se puedan corregir; ninguna es de producto.

1. **`PIERCING_PATTERN`/`DARK_CLOUD_COVER` usan la lectura más laxa** («abre por debajo del cierre
   de la vela 1», no del mínimo): la estricta casi nunca se cumple sin huecos reales, y el propio
   catálogo ofrece las dos lecturas como equivalentes («el mínimo (o el cierre)»).
2. **`THREE_INSIDE_UP`/`DOWN` reutilizan la función de geometría del harami** y coexisten con él
   como instancias separadas, en vez de invalidar o fusionar: mismo principio que las geometrías
   solapadas del punto de una vela (sección 7).
3. **`CRYPTO × SPOT` usa `GAP_NOT_APPLICABLE`** para `MORNING_STAR`/`EVENING_STAR`, siguiendo
   directamente la razón que da `patrones-de-vela.md` (sin huecos reales en continuo).
4. **Ninguna geometría de esta tarea comparte pareja** (a diferencia de martillo/hanging man): no
   hace falta un `AmbiguousGeometry` propio de esta tarea (sección 3).
5. **Dos familias, dos versiones de parámetros y de detector, nunca una compartida** (sección 9):
   corregido antes de implementar las tres velas, sobre la decisión original (un único
   `multi-candle-detector-v1`/`multi-candle-params-v1` para las catorce) que habría desplazado la
   identidad de las instancias de dos velas ante cualquier cambio en las de tres.
6. **La caché de tendencia previa no sobrevive entre llamadas** (sección 4): corregido en dos
   pasos. Un primer arreglo indexó `(instante, velas leídas)` en vez de solo el instante, tras
   reproducir un resultado obsoleto con una vela que llega tarde y el mismo contexto reutilizado.
   Una segunda revisión encontró que esa clave seguía sin cubrir una vela corregida con el mismo
   recuento; la solución final quita la caché del contexto por completo: vive solo dentro de cada
   llamada a `detect_multi_candle_patterns`. El mismo defecto, en ambas variantes, se corrigió
   idéntico en `detectores-de-una-vela.md`.
7. **Umbrales provisionales, sin validar**, registrados en PARAMS-VALIDATION-001 al introducirlos.
