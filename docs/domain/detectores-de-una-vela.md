# Detectores de patrones de una vela (v1)

- **Estado:** vigente. Cubre los nueve patrones de una vela del catálogo: `DOJI`,
  `DRAGONFLY_DOJI`, `GRAVESTONE_DOJI`, `HAMMER`, `HANGING_MAN`, `INVERTED_HAMMER`,
  `SHOOTING_STAR`, `BULLISH_PIN_BAR`, `BEARISH_PIN_BAR`.
- **Fecha:** 2026-09-28.
- **Tarea:** POINT4-SINGLE-001 (3 de 7 del punto 4).
- **Depende de:** [patrones-de-vela.md](patrones-de-vela.md) (qué es cada patrón) y
  [instancia-de-patron-de-vela.md](instancia-de-patron-de-vela.md) (cómo se representa). Reutiliza
  el clasificador de tendencia del punto 2 (`market_trend.py`, `classify_trend`).
- **Código:** `backend/src/freyja_backend/domain/candlestick_single.py`. Dominio puro, sin E/S.
  Pruebas en `backend/tests/unit/test_candlestick_single.py`.

A diferencia de los detectores de figuras chartistas (`pattern_detection.py`, pivotes
confirmados sobre muchas velas), un detector de un patrón de una vela juzga **una sola vela
cerrada**: su geometría se conoce por completo en el instante de su propio cierre, y no cambia
después. Por eso este documento y su código son deliberadamente más simples: no hay fronteras, no
hay ruptura, no hay instancias que evolucionen a lo largo de varias velas.

## 1. Qué hace un detector y qué no

- **Es una función pura de una vela cerrada y la tendencia inmediatamente anterior a ella.** La
  misma vela, con la misma historia previa, da siempre el mismo resultado.
- **No usa figuras chartistas ni indicadores** (puntos 3 y 5): solo el cuerpo, el rango y las
  mechas de la propia vela, y la clasificación de tendencia del punto 2.
- **Primero geometría, después contexto** (regla esencial de la tarea): una vela nunca se
  interpreta antes de comprobar su forma.
- **Sin ruptura ni confirmación adicional.** Los nueve patrones de esta tarea no la necesitan
  (`patrones-de-vela.md`, columna «Confirmación»: todos son «No»): la propia vela, una vez
  cerrada, es el hecho completo. Una instancia nace ya resuelta en una sola evaluación:
  `CONFIRMED` si la geometría y el contexto encajan, `MORPHOLOGICALLY_VALID` si la geometría
  encaja pero el contexto no (o no se puede clasificar todavía). No hay una evaluación posterior
  para la misma instancia: nada que dependa solo del pasado de esa vela puede cambiar.
- **Ninguna vela abierta produce nada.** Solo se leen velas cerradas.
- **No genera señal, orden ni probabilidad.**

## 2. Parámetros (`single-candle-params-v1`)

**Provisionales y sin validar** (PARAMS-VALIDATION-001), razonados a partir de definiciones
tradicionales de análisis técnico, no de una preferencia personal. Todos relativos al **rango**
(máximo menos mínimo) de la propia vela, para que valgan igual en cualquier instrumento y
temporalidad.

| Parámetro | Valor | Significado |
| --------- | ----- | ----------- |
| `doji_max_body_ratio` | 0,10 | Cuerpo como mucho el 10 % del rango: «prácticamente nulo». |
| `short_wick_max_ratio` | 0,10 | La mecha «corta» (la del lado sin rechazo) como mucho el 10 % del rango. |
| `long_wick_min_ratio` | 0,60 | La mecha «larga» (la del lado del rechazo) como mínimo el 60 % del rango. |
| `small_body_max_ratio` | 0,30 | Cuerpo como mucho el 30 % del rango, para la familia martillo/estrella. |
| `pin_bar_max_body_ratio` | 0,25 | Cuerpo como mucho el 25 % del rango, para pin bar (más exigente que el martillo). |
| `pin_bar_min_wick_ratio` | 0,66 | La mecha de rechazo del pin bar, como mínimo dos tercios del rango. |
| `pivot_params`, `trend_params`, `min_history` | los del punto 2 | Los que usa `classify_trend` para la tendencia previa. |

Una vela de **rango cero** (máximo igual al mínimo, y por tanto apertura, cierre y ambas mechas
también en cero) no produce ningún patrón: no hay proporción que calcular, y en la práctica no
ocurre con datos reales (implicaría cero movimiento de precio en toda la vela).

## 3. Geometría: qué mide cada forma

Sea cuerpo, mecha superior e inferior expresados como fracción del rango de la vela.

- **`DOJI`**: cuerpo ≤ `doji_max_body_ratio`. Sin exigencia sobre las mechas.
- **`DRAGONFLY_DOJI`**: doji, y además mecha superior ≤ `short_wick_max_ratio` y mecha inferior ≥
  `long_wick_min_ratio`.
- **`GRAVESTONE_DOJI`**: doji, y además mecha inferior ≤ `short_wick_max_ratio` y mecha superior ≥
  `long_wick_min_ratio`.
- **Forma martillo** (`HAMMER` / `HANGING_MAN`, misma geometría): cuerpo ≤
  `small_body_max_ratio`, mecha superior ≤ `short_wick_max_ratio`, mecha inferior ≥
  `long_wick_min_ratio`.
- **Forma martillo invertido** (`INVERTED_HAMMER` / `SHOOTING_STAR`, misma geometría, espejo):
  cuerpo ≤ `small_body_max_ratio`, mecha inferior ≤ `short_wick_max_ratio`, mecha superior ≥
  `long_wick_min_ratio`.
- **`BULLISH_PIN_BAR`**: cuerpo ≤ `pin_bar_max_body_ratio`, mecha inferior ≥
  `pin_bar_min_wick_ratio`.
- **`BEARISH_PIN_BAR`**: cuerpo ≤ `pin_bar_max_body_ratio`, mecha superior ≥
  `pin_bar_min_wick_ratio`.

No hay un umbral separado de «posición del cuerpo dentro del rango» (p. ej. «en el tercio
superior»): con una mecha corta acotada por arriba y una mecha larga acotada por abajo (o al
revés), el cuerpo queda pegado al extremo correspondiente por construcción aritmética. Un umbral
aparte sería redundante y podría contradecir a los otros dos.

**Ninguna geometría descarta otra.** Una vela puede cumplir varias a la vez (un cuerpo casi nulo
con mecha inferior extrema cumple `DOJI`, `DRAGONFLY_DOJI` y la forma martillo al mismo tiempo).
El detector declara **todas** las que cumple, como exige la tarea («pin bar, martillo y shooting
star solapados no se cuentan como tres confirmaciones independientes»: eso es una regla de
POINT4-HYPOTHESIS-001 sobre cómo se **usa** la evidencia agrupada, no una regla de qué geometrías
se declaran aquí — ver también `patrones-de-vela.md`, sección 6).

## 4. Contexto: cuándo se interpreta cada forma

La tendencia previa es la del clasificador del punto 2 (`classify_trend`), evaluada con las
velas **estrictamente anteriores** a la de la vela candidata, en el instante de su propia
apertura. A diferencia de las figuras chartistas (cuya tendencia previa puede tardar en
confirmarse porque su primer pivote se confirma `k` velas tarde), aquí no hay ese retraso: la
tendencia previa a una vela ya cerrada es una función pura de velas todavía más antiguas, así que
se conoce por completo desde el instante en que la propia vela cierra. Por eso una instancia de
un patrón de una vela nunca necesita una segunda evaluación: no hay nada pendiente que datos
futuros puedan resolver.

- **`DOJI`** no exige tendencia previa (`patrones-de-vela.md`: sesgo `NONE`). Su única
  evaluación es siempre `CONFIRMED`, con el contexto observado registrado igualmente (sección 5)
  aunque no condicione nada.
- **Con un solo nombre posible** (`DRAGONFLY_DOJI`, `GRAVESTONE_DOJI`, `BULLISH_PIN_BAR`,
  `BEARISH_PIN_BAR`): si la geometría se cumple, siempre nace una instancia. Si la tendencia
  previa coincide con la exigida, `CONFIRMED`; si no coincide, o no se puede clasificar
  (`INSUFFICIENT_DATA` del clasificador), `MORPHOLOGICALLY_VALID` — la geometría existe y se
  registra, pero no se declara resuelta sin el contexto que la tradición exige.
- **Con dos nombres posibles sobre la misma geometría** (forma martillo → `HAMMER` con tendencia
  previa bajista, `HANGING_MAN` con alcista; forma martillo invertido → `INVERTED_HAMMER` con
  bajista, `SHOOTING_STAR` con alcista): si la tendencia previa es la que un nombre exige, nace
  **esa** instancia, ya `CONFIRMED`. Si la tendencia previa es de rango, transición, o no se
  puede clasificar, **no nace ninguna instancia con nombre**: declarar cualquiera de los dos
  nombres sin contexto sería inventar cuál aplica (decisión ya registrada en
  `instancia-de-patron-de-vela.md`, sección 7). Esto es distinto del caso de un solo nombre
  posible, porque aquí sí hay una alternativa concreta que la ambigüedad dejaría sin declarar
  incorrectamente si se eligiera una al azar. **La observación geométrica no desaparece**: ver
  sección 4 bis.

## 4 bis. Geometría sin nombre: `AmbiguousGeometry`

**Corrección (2026-09-28).** La primera versión de esta tarea (PR #88) no dejaba rastro alguno de
una vela con forma de martillo/martillo invertido cuando el contexto no resolvía el nombre: ni
instancia, ni evidencia, nada consultable. Jessica lo detectó al revisar el resumen del bloque de
trabajo. La corrección (PR #89) separa dos hechos que antes se habían fundido en uno:

- **Que la vela tenga esa geometría** es un hecho, verificable con solo mirar la propia vela.
- **Qué nombre le corresponde** (`HAMMER` o `HANGING_MAN`) exige contexto, y sin él no se afirma.

`AmbiguousGeometry` (`backend/src/freyja_backend/domain/candlestick_single.py`) registra el
primer hecho sin comprometerse con el segundo:

| Campo | Contenido |
| ----- | --------- |
| `geometry` | Cuál de las dos familias compartidas (`HAMMER_OR_HANGING_MAN`, `INVERTED_HAMMER_OR_SHOOTING_STAR`). |
| `instrument_id`, `data_source`, `timeframe` | La serie sobre la que se observó. |
| `anchor` | La vela completa (`CandleAnchor`, mismo tipo que usan las instancias). |
| `observed_at` | El cierre de la vela: el instante en que la geometría quedó fijada. |
| `observed_trend` | La tendencia previa **real** que se observó (`RANGE`, `TRANSITION` o `INSUFFICIENT_DATA`): el motivo concreto, no solo «no se pudo nombrar». |
| `detector_version`, `parameter_version` | Los mismos que llevaría la instancia si el contexto la hubiera resuelto. |

**Deliberadamente no es una `CandlePatternInstance`.** No tiene `pattern_type` ni `state`: no hay
forma de leerlo como un patrón con nombre, ni siquiera sin confirmar, porque el propio campo
`pattern_type` ya sería una interpretación. `SingleCandleResult.ambiguous_geometries` lo devuelve
aparte de `instances`, así que un consumidor que solo recorra `instances` (como hará
POINT4-HYPOTHESIS-001 al agregar evidencia) nunca lo ve ni por accidente.

**Reproducible, nunca reescrito.** Igual que el resto de este detector (sección 6), es una función
pura del pasado de esa vela: si se vuelve a calcular con más velas futuras añadidas, la misma vela
produce el mismo `AmbiguousGeometry`, con el mismo `observed_trend`.

## 5. Evidencia: `CONTEXT`

Toda evaluación `CONFIRMED` (y ninguna `MORPHOLOGICALLY_VALID`, que por definición no llegó a
confirmar el contexto) lleva una evidencia `CONTEXT` con:

- `state`: la tendencia observada (`UPTREND`, `DOWNTREND`, `RANGE`, `TRANSITION`,
  `INSUFFICIENT_DATA`).
- `required`: la tendencia que el patrón exige (`UPTREND` o `DOWNTREND`), o `NONE` para `DOJI`.
- `compatible`: si `state` es la exigida, o `true` sin condición para `DOJI`.

Es el código que `instancia-de-patron-de-vela.md` (sección 6) exige a partir de `CONTEXT_VALID`;
aquí, como la única evaluación de una instancia confirmada ya es `CONFIRMED`, es la misma
evaluación la que la lleva.

## 6. Identidad y versión

- **Detector:** un único `single-candle-detector-v1` para los nueve patrones: comparten
  geometría, parámetros y la misma regla de contexto, así que se versionan juntos. Un cambio en
  cualquiera de sus umbrales sube esta versión.
- **Identidad de la instancia:** la que da el modelo (tipo, serie, vela inicial, detector,
  parámetros). Como cada instancia nace ya resuelta, no hay `advance()` para los patrones de una
  vela en v1: escanear la misma vela otra vez da la misma instancia, con la misma (única)
  evaluación.
- **Sin estado incremental.** El detector es una función pura de la serie completa de velas
  cerradas hasta `observed_at`: cada llamada la recorre entera y construye lo que encuentre. Es
  correcto (nunca dos llamadas dan resultados contradictorios: reproducibilidad y ausencia de
  _look-ahead_) aunque no el más eficiente posible; para una vela cualquiera, su propio resultado
  nunca cambia una vez calculado, así que optimizar el recorrido (no repetirlo desde el principio
  en cada instante) queda abierto para cuando haga falta, sin cambiar el resultado.
- **La memoria de tendencia previa vive solo dentro de una llamada.** `detect_single_candle_patterns`
  construye su propia caché al empezar y la pasa hacia abajo; nunca se guarda en el contexto ni
  sobrevive entre llamadas, ni siquiera reutilizando el mismo contexto con `.at()`. Es la lectura
  final de dos correcciones (sección siguiente): la primera (indexar por `(instante, velas
  leídas)`) bastaba para una vela que llega tarde, pero no para una vela **corregida in situ**
  (mismo recuento, mismo instante, contenido distinto). Sin memoria compartida entre llamadas, no
  hay clave posible que se quede corta: cada llamada empieza en blanco.

**Corrección (2026-09-29, dos revisiones de Jessica).** La afirmación de arriba («nunca dos
llamadas dan resultados contradictorios») no se cumplía en dos variantes distintas, encontradas en
dos revisiones seguidas antes de continuar con POINT4-CONTEXT-001:

1. **Vela que llega tarde.** La primera versión de la caché de tendencia previa
   (`SingleCandleContext._prior_trends`) se indexaba solo por el instante (`at`), no por cuántas
   velas se habían leído para responder. Reutilizando el mismo contexto (`.at()`) entre dos
   llamadas donde una vela anterior, antes ausente, ya ha llegado, la segunda llamada debería ver
   más historia — pero la caché le devolvía la clasificación calculada con menos velas.
   Reproducido con una serie bajista real (60 velas recientes: `INSUFFICIENT_DATA`; las mismas 115
   completas: `DOWNTREND`). Primer arreglo: indexar por `(at, len(before))`, para que el número de
   velas leídas formara parte de la clave.
2. **Vela corregida, mismo recuento.** El primer arreglo no cubría esta variante: una vela
   **anterior** al instante evaluado se corrige o se sustituye (los mismos `open_time`, la misma
   cantidad de velas en `before`, contenido distinto). `len(before)` no cambia, así que la clave
   tampoco, y la caché seguía devolviendo la clasificación antigua. Reproducido reutilizando el
   mismo contexto con dos series reales de la misma longitud y el mismo instante final (una
   bajista, `zigzag(DOWN)`, y la misma sustituida por una alcista, `zigzag(UP)`): la segunda
   llamada devolvía `DOWNTREND` (el valor de la primera) en vez de recalcular `UPTREND`.

Ninguna clave basada en `(instante, alguna medida de antes)` puede cubrir esto de forma general:
cualquier resumen que no sea el contenido completo de `before` puede coincidir por accidente entre
dos series distintas. La corrección final **elimina la caché entre llamadas**: `_prior_trends` deja
de vivir en `SingleCandleContext`; la memoria pasa a ser un diccionario local que
`detect_single_candle_patterns` crea al empezar y descarta al terminar, correcta por construcción
(nunca sobrevive para poder quedarse obsoleta) sin perder el ahorro dentro de una misma llamada
(varias comprobaciones de la misma vela siguen reutilizando el mismo cálculo). El mismo defecto,
idéntico en ambas variantes, se encontró y corrigió a la vez en `candlestick_multi.py`
(`docs/domain/detectores-de-dos-y-tres-velas.md`, sección 4).

## 7. Contexto de detección propio, no el de las figuras chartistas

Este detector usa `SingleCandleContext`, no `DetectionContext` (`pattern_detection.py`, de
POINT3). Ambos comparten la misma forma deliberadamente (instrumento, calendario, fuente,
temporalidad, instante observado, parámetros, caché de tendencias) para que una integración
futura sea mecánica, pero son tipos distintos: extender el contexto de las figuras chartistas
desde una tarea del punto 4 mezclaría el alcance de dos tareas de puntos distintos. Si en el
futuro se decide unificarlos, será su propia tarea, explícita.

## 8. Lo que este documento no decide

Los patrones de dos y tres velas (POINT4-MULTI-001); qué política de gaps aplica a cada mercado
(no la necesita ningún patrón de esta tarea); cómo se combina esta evidencia con otra en una
hipótesis (POINT4-HYPOTHESIS-001); el caso de las geometrías compartidas cuando conviene declarar
una instancia provisional en vez de esperar (sigue abierto, `instancia-de-patron-de-vela.md`
sección 7); persistencia, señales, órdenes.

## 9. Decisiones técnicas tomadas al redactar

Registradas aquí para que se puedan corregir; ninguna es de producto.

1. **Los seis umbrales geométricos son una lectura razonada de definiciones tradicionales de
   análisis técnico** (proporciones de cuerpo y mecha ya publicadas para doji, martillo y pin
   bar), no una preferencia de Jessica ni un ajuste con datos reales: quedan en
   PARAMS-VALIDATION-001 para validarse cuando corresponda.
2. **Sin umbral de «posición del cuerpo»**: es redundante una vez fijadas las dos mechas (sección
   3).
3. **Ninguna geometría excluye a otra**: el catálogo pide explícitamente declarar todas las que
   se cumplan; agruparlas para no contarlas como confirmaciones independientes es de
   POINT4-HYPOTHESIS-001.
4. **Ante una geometría compartida sin contexto que la resuelva, no nace ninguna instancia con
   nombre** (ni siquiera en `MORPHOLOGICALLY_VALID`): se prefirió a la alternativa de crear una
   instancia provisional e invalidarla después con `SUPERSEDED`, por ser más simple y no exigir
   un mecanismo de revocación para v1. `instancia-de-patron-de-vela.md` deja ambas estrategias
   representables por el modelo; esta tarea elige la primera. **Corregido (2026-09-28, sección 4
   bis):** «ninguna instancia con nombre» no es lo mismo que «ninguna observación». La primera
   versión de esta decisión perdía la geometría por completo cuando el contexto no la resolvía;
   `AmbiguousGeometry` la conserva sin nombrarla.
5. **Un solo detector y una sola versión para los nueve patrones**, no una por patrón: comparten
   parámetros y regla de contexto en su totalidad, así que versionarlos por separado no aportaría
   nada y complicaría el seguimiento de un cambio que los afecta a todos.
6. **Sin estado incremental** (sección 6): cada patrón de una vela se resuelve por completo en su
   propia vela, así que no hace falta el mecanismo de «llevar instancias de un instante al
   siguiente» que sí necesitan las figuras chartistas.
7. **`SingleCandleContext` es su propio tipo**, no una extensión de `DetectionContext` de
   `pattern_detection.py` (sección 7): evita modificar un archivo de POINT3 desde una tarea de
   POINT4.
8. **La caché de tendencia previa no sobrevive entre llamadas** (sección 6): corregido el
   2026-09-29 en dos pasos. Un primer arreglo indexó `(instante, velas leídas)` en vez de solo el
   instante, tras reproducir un resultado obsoleto con una vela que llega tarde y el mismo
   contexto reutilizado. Una segunda revisión encontró que esa clave seguía sin cubrir una vela
   **corregida** con el mismo recuento (mismo instante, mismas velas leídas, contenido distinto):
   reproducido reutilizando el mismo contexto con dos series reales de igual longitud. Como
   ninguna clave parcial cubre el caso general, la solución final quita la caché del contexto por
   completo: vive solo dentro de cada llamada a `detect_single_candle_patterns`. El mismo defecto,
   en ambas variantes, se corrigió idéntico en `candlestick_multi.py`.
