# Detectores de figuras de reversión (v1)

- **Estado:** vigente. Cubre los ocho detectores: doble techo y suelo, triple techo y suelo,
  hombro-cabeza-hombro superior e invertido, y techo y suelo redondeados.
- **Fecha:** 2026-09-25
- **Tarea:** POINT3-REVERSAL-001 (3 de 7 del punto 3).
- **Depende de:** [figuras-chartistas.md](figuras-chartistas.md) (qué es cada figura),
  [instancia-de-figura.md](instancia-de-figura.md) (cómo se representa) y
  [estructura-de-precio.md](estructura-de-precio.md) (pivotes confirmados).
- **Código:** `backend/src/freyja_backend/domain/pattern_detection.py` (lo común),
  `pattern_double.py`, `pattern_triple.py`, `pattern_head_shoulders.py` y `pattern_rounding.py`.
  Dominio puro, sin E/S. Pruebas en
  `backend/tests/unit/test_pattern_detection.py`.

Cada detector es **una unidad con sus propias reglas y su propia versión**. Lo que comparten es
fontanería (cómo se les alimenta, cómo se juzga una ruptura, cómo se llevan las instancias de un
instante al siguiente), **nunca geometría**: «tres extremos comparables» no es «dos más uno», y el
hombro-cabeza-hombro no se parece a ninguno de los dos. Un techo y su suelo espejo sí comparten
implementación, porque son la misma geometría invertida.

## 1. Qué hace un detector y qué no

- **Es una función pura de lo que se sabía en un instante.** Con las velas cerradas en
  `observed_at` devuelve las figuras que ve; las mismas velas dan siempre lo mismo. Las velas que
  cierran después y la que está en curso se ignoran.
- **No usa patrones de velas ni indicadores** (puntos 4 y 5): solo pivotes confirmados, cierres y
  precios exactos.
- **La semejanza visual no basta**: una figura exige anclas confirmadas, tolerancias relativas y una
  altura mínima. Sin ellas, no hay instancia.
- **Una ruptura puede completar una figura, pero no autoriza ninguna operación.** Un detector no
  emite señal, lado, objetivo ni confianza.
- **Sin tendencia previa compatible, la figura se observa pero no puede validar una señal.** No se
  descarta ni se supone: se registra la tendencia previa (`PRIOR_TREND`) con `compatible` verdadero
  o falso, y quien use la figura (POINT3-HYPOTHESIS-001) decide. La tendencia previa es la del
  clasificador del punto 2, en el instante del primer pivote de la figura.
- **Datos no aptos no se juzgan.** Si el contexto observable de la serie no es suficiente (hueco
  en la ventana, datos atrasados, fuente no autorizada, poca historia), el detector no devuelve
  figuras y dice por qué; las instancias abiertas pasan a `INSUFFICIENT_DATA`.

## 2. Parámetros (`reversal-params-v1`)

**Provisionales y sin validar.** Están razonados, no medidos; se registran en
PARAMS-VALIDATION-001 para validarlos con datos reales. Todos son **relativos**, de modo que valen
igual en cualquier instrumento y temporalidad.

| Parámetro | Valor | Significado |
| --------- | ----- | ----------- |
| `level_tolerance` | 0,15 | Dos extremos son comparables si difieren, como mucho, esta fracción de la **altura** de la figura (de la cima al valle). |
| `min_height_fraction` | 0,25 | La altura debe ser al menos esta fracción del rango de precios de las `range_window_candles` velas que terminan en el primer pivote. Lo más pequeño es ruido. |
| `range_window_candles` | 100 | Ventana del rango de referencia. Se fija al empezar la figura y no cambia después. |
| `breakout_margin` | 0,10 | Un cierre más allá del cuello por al menos esta fracción de la altura **confirma** la ruptura; uno menor la deja pendiente. |
| `failure_window_candles` | 10 | Un cierre de vuelta al lado interior del cuello dentro de estas velas desde el primer cierre más allá **hace fracasar** la ruptura. |
| `max_age_candles` | 150 | Una figura sin resolver más vieja que esto (desde su primer pivote) caduca. |
| `exceed_margin` | 0,15 | Antes de romper, un cierre más allá del extremo por más de esta fracción de la altura es el precio yendo hacia el otro lado: la figura ha terminado. |
| `min_history` | 100 | Velas que necesita el contexto observable para juzgar la serie. |
| `head_prominence` | 0,10 | Solo hombro-cabeza-hombro: la cabeza debe superar al hombro más alto por al menos esta fracción de la altura, o no es una cabeza. |
| `arc_fit_min` | 0,85 | Solo redondeados: los cierres del arco deben seguir una parábola con al menos este coeficiente de determinación (R²). |
| `min_top_dwell` | 0,40 | Solo redondeados: al menos esta parte de los cierres del arco debe estar en el cuarto superior de su altura. Una parábola pasa ahí la mitad de su anchura; una punta, un cuarto. |
| `apex_position_band` | 0,25 | Solo redondeados: el apex está entre esta fracción y su complementaria del recorrido de extremo a extremo. |
| `min_arc_candles` | 30 | Solo redondeados: el arco abarca, de extremo a extremo, al menos estas velas. |
| `max_arc_candles` | 150 | Solo redondeados: y como mucho estas. |
| `shoulder_tolerance` | 0,30 | Solo hombro-cabeza-hombro: los dos hombros son comparables dentro de esta fracción de la altura (más laxa que la de los extremos de un doble techo: los hombros rara vez están al mismo nivel). |
| `pivot_params.k` | 3 | El de `pivots-v1`, el mismo que usa la tendencia. |

## 3. Estados: cuándo cada uno

Reglas comunes, sobre **cierres** (una mecha no rompe nada) y en este orden, gana lo que ocurrió
primero:

1. **Invalidada** si, antes de cualquier ruptura, un cierre supera el extremo por más de
   `exceed_margin` (`CLOSED_THROUGH_AGAINST_BIAS`); si la geometría se rompe (`GEOMETRY_BROKEN`,
   `ANCHOR_EXCEEDED`); o si caduca sin resolverse (`TOO_LONG`).
2. **Ruptura**: el primer cierre más allá del cuello. Si ya supera `breakout_margin` es
   **confirmada** (`CONFIRMED_DOWN` en un techo, `CONFIRMED_UP` en un suelo); si no, queda
   **pendiente** hasta que un cierre lo alcance.
3. **Fallida** (`FAILED_BREAKOUT`) si, dentro de `failure_window_candles` desde ese primer cierre,
   otro cierre vuelve al lado interior del cuello. Pasada la ventana, la ruptura se mantiene.
4. **Geométricamente válida** con las anclas completas y sin ruptura; **en formación** con las
   anclas parciales cuando el precio ha vuelto al nivel de los extremos.

Como el pivote se confirma `k` velas tarde, la ruptura puede ser ya un hecho cuando la figura se
hace conocible: entonces nace directamente en el estado que le corresponde (sin pasar por uno
anterior al real). Detrás, los estados solo avanzan (ver el modelo).

## 4. Instancias entre instantes

- **Identidad:** tipo, serie, primer pivote, detector y parámetros. La misma figura hallada de
  nuevo es la misma instancia; las anclas solo se añaden.
- Una figura que **nace ya invalidada nunca fue una figura**: no crea instancia.
- Si las anclas dejan de ser las de la instancia (el detector ve otra cosa con el mismo primer
  pivote), la instancia se invalida con `SUPERSEDED`; nada se reescribe.
- Una instancia que el detector **ya no ve** se invalida con `GEOMETRY_BROKEN`, salvo que su ruptura
  estuviera confirmada: una figura confirmada se queda como se confirmó.
- Una instancia terminada (`FAILED_BREAKOUT`, `INVALIDATED`) no se toca más.
- Solo se añade una evaluación cuando algo cambia (estado, anclas, ruptura o motivos), no una por vela.
- `replay_detector` reproduce lo que habría construido un detector observando la serie vela a vela;
  es reproducible y sin _look-ahead_ (hay pruebas que lo comprueban en cada instante).

## 5. Doble techo y doble suelo

`DOUBLE_TOP` (`double-top-detector-v1`) y `DOUBLE_BOTTOM` (`double-bottom-detector-v1`) son espejo.

- **Pivotes:** tres puntos de giro consecutivos, **extremo, valle, extremo** (en el suelo: valle,
  cima, valle). Anclas: `FIRST_EXTREME`, `INTERMEDIATE`, `SECOND_EXTREME`.
- **Altura:** de la media de los dos extremos (o del primero, mientras falta el segundo) al valle
  intermedio. Debe cumplir `min_height_fraction`.
- **Comparables:** los dos extremos difieren como mucho `level_tolerance × altura`.
- **Cuello:** el nivel del valle intermedio, horizontal.
- **En formación:** el primer extremo y el valle están confirmados y el precio ha vuelto a
  `level_tolerance × altura` del primer extremo, sin haber cerrado por debajo del cuello ni superado
  el extremo.
- **Válida:** el segundo extremo está confirmado y es comparable.
- **Se invalida** si el segundo extremo no es comparable (`ANCHOR_EXCEEDED` si es más extremo,
  `GEOMETRY_BROKEN` si no llega). Un cierre por debajo del cuello justo después del segundo extremo
  **no invalida**: el pivote se confirma `k` velas tarde y esa caída es la ruptura, que se juzga desde
  la vela siguiente a ese extremo en cuanto se confirma.
- **Evidencia conservada:** `EXTREME_LEVELS` (altura, tolerancia, rango de referencia, diferencia
  entre extremos), `PRIOR_TREND` y `BREAKOUT_SCAN`.

## 6. Triple techo y triple suelo

`TRIPLE_TOP` (`triple-top-detector-v1`) y `TRIPLE_BOTTOM` (`triple-bottom-detector-v1`).

- **Pivotes:** cinco puntos consecutivos: extremo, valle, extremo, valle, extremo. Anclas:
  `EXTREME_1`, `INTERMEDIATE_1`, `EXTREME_2`, `INTERMEDIATE_2`, `EXTREME_3`.
- **Altura:** de la media de los extremos a la media de los valles.
- **Comparables:** **cada** extremo dentro de `level_tolerance × altura` de la media de los extremos,
  y los dos valles entre sí dentro de la misma tolerancia. El tercero debe estar de acuerdo con los
  otros dos: no es «un doble techo más uno».
- **Cuello:** el nivel del **valle más bajo** (en el suelo, el más alto), horizontal.
- **En formación:** los dos primeros extremos y los dos valles confirmados y comparables, y el precio
  de vuelta al nivel de los extremos. **Válida:** el tercer extremo confirmado y comparable.
- **Se invalida** si el tercer extremo no es comparable. Como en el doble techo, una caída antes de
  confirmarse el tercer extremo no invalida: es la ruptura.
- Un triple techo **coexiste** con dobles techos sobre las mismas velas: son figuras distintas con su
  propia identidad.

## 7. Hombro-cabeza-hombro y su invertido

`HEAD_AND_SHOULDERS_TOP` (`head-and-shoulders-top-detector-v1`) y `HEAD_AND_SHOULDERS_BOTTOM`
(`head-and-shoulders-bottom-detector-v1`) son espejo. No comparten geometría con los dobles y triples:
tienen una **cabeza** que debe destacar, dos **hombros** solo aproximadamente iguales y un **cuello que
puede ser inclinado**.

- **Pivotes:** cinco puntos consecutivos: hombro, valle, cabeza, valle, hombro (en el invertido, al
  revés). Anclas: `LEFT_SHOULDER`, `LEFT_TROUGH`, `HEAD`, `RIGHT_TROUGH`, `RIGHT_SHOULDER`.
- **Cuello:** la **recta** que pasa por los dos valles, evaluada en cada instante. La ruptura se juzga
  contra esa recta, no contra un nivel horizontal: un cierre que rompería el valle más alto puede
  seguir por encima del cuello real. El valor de la recta se calcula con `Decimal`, multiplicando
  antes de dividir y redondeado a los 12 decimales con los que se guardan los precios.
- **Altura:** la distancia vertical de la cabeza al cuello en el instante de la cabeza. Debe cumplir
  `min_height_fraction`.
- **La cabeza destaca:** supera al hombro más alto por al menos `head_prominence × altura`. Sin eso no
  es una cabeza y no hay figura.
- **Hombros comparables:** difieren como mucho `shoulder_tolerance × altura`, y el derecho no supera a
  la cabeza.
- **En formación:** primer hombro, ambos valles y cabeza confirmados, y el precio de vuelta al nivel
  del primer hombro. **Válida:** el hombro derecho confirmado y comparable.
- **Se invalida** si el hombro derecho iguala o supera a la cabeza (`ANCHOR_EXCEEDED`) o no es
  comparable (`GEOMETRY_BROKEN`); y, antes de romper, por un cierre más allá de la cabeza por más de
  `exceed_margin × altura`.
- **Evidencia conservada:** `HEAD_AND_SHOULDERS` (altura, prominencia de la cabeza y la exigida,
  diferencia entre hombros, subida del cuello por hora), `PRIOR_TREND` y `BREAKOUT_SCAN`.
- **No se exige simetría temporal** entre hombros: solo de precio.

## 8. Techo y suelo redondeados

`ROUNDING_TOP` (`rounding-top-detector-v1`) y `ROUNDING_BOTTOM` (`rounding-bottom-detector-v1`) son
espejo. **No hay pivotes nítidos que comparar**: es una curva, y lo que se puede comprobar, de forma
exacta, es que los cierres la siguen.

- **Anclas:** `LEFT_END`, `APEX`, `RIGHT_END`. El **extremo izquierdo** es un swing confirmado (el más
  antiguo, dentro de `max_arc_candles`, desde el que la subida hasta el apex ya sigue una parábola); el
  **apex**, un swing confirmado; el **extremo derecho**, **la primera vela cerrada** después del apex
  cuyo cierre vuelve al nivel de la base. **No es un pivote, a propósito:** una cúpula que atraviesa su
  base sin pausa no deja ahí ningún mínimo confirmado, y esperarlo ocultaría la ruptura que es el objeto
  de la figura. Es la única figura cuyo ancla no es un pivote; su hora de confirmación es el cierre de
  esa vela, así que nada se sabe antes de tiempo.
- **Base:** el **nivel horizontal del extremo izquierdo**; el extremo derecho es la vuelta del precio a
  ese nivel (dentro de `level_tolerance` de la altura). Una recta por los dos extremos subiría hasta
  donde se «cazó» la bajada y las últimas velas del propio arco, que aún bajan hacia la base, contarían ya
  como una ruptura. La ruptura se juzga contra la base con las mismas reglas que las demás figuras
  (sobre cierres, margen de confirmación, ventana de fracaso).
- **Altura:** del nivel de la base al apex. Debe cumplir `min_height_fraction`.
- **Redondeada, no puntiaguda:** (a) los cierres desde el extremo izquierdo hasta el derecho siguen una
  parábola abierta hacia abajo (hacia arriba en el suelo) con R² ≥ `arc_fit_min`, ajustada por mínimos
  cuadrados en **aritmética racional exacta** (sin coma flotante); (b) al menos `min_top_dwell` de los
  cierres están en el cuarto superior de la altura: una punta también ajusta bien una parábola, pero no
  permanece arriba; (c) el apex está en la parte central del arco (`apex_position_band`); (d) el arco
  abarca entre `min_arc_candles` y `max_arc_candles` velas.
- **En formación:** el extremo izquierdo y el apex están confirmados y la subida ya se comporta como
  la mitad de una cúpula (mismo ajuste y misma permanencia arriba, sobre la mitad izquierda), con el
  precio bajando. **Válida:** existe el extremo derecho y el arco completo cumple lo anterior.
- **No es figura** si el precio hace antes un extremo mayor que el apex, si el arco sería más ancho
  del permitido (el extremo derecho se busca dentro de `max_arc_candles` desde el izquierdo), o si el
  precio atraviesa la base en lugar de volver a ella (un cierre por debajo del nivel de la base por más
  de `level_tolerance × altura`).
- **La edad** de una figura sin resolver se cuenta desde su **último ancla**, porque un arco es largo por
  naturaleza.
- **Evidencia conservada:** `ROUNDING_ARC` (R², curvatura, posición del apex, permanencia arriba, velas
  del arco, altura), `PRIOR_TREND` y `BREAKOUT_SCAN`.
- **Límite conocido:** un arco con mucho ruido, o cuyo comienzo no coincida con ningún swing confirmado,
  no se detecta. Es un umbral provisional que se validará con datos reales.
- **Regla de la izquierda sin prueba propia:** el alcance máximo del extremo izquierdo
  (`max_arc_candles` hacia atrás) es una salida temprana equivalente, para todas las formas
  razonables, al límite de búsqueda del extremo derecho; se conserva por claridad.

## 9. Lo que este documento no decide

Las figuras de continuación y de expansión (POINT3-CONTINUATION-001 y EXPANSION-001), cómo se
integran varias figuras como evidencia de una hipótesis (POINT3-HYPOTHESIS-001), objetivos, entradas,
señales y órdenes, y la persistencia de las instancias.

## 10. Decisiones técnicas tomadas al redactar

Registradas aquí para que se puedan corregir; ninguna es de producto.

1. Las tolerancias son **relativas a la altura** de la figura y el tamaño mínimo, relativo al rango
   donde empezó: escala y volatilidad no dependen del instrumento.
2. El rango de referencia se fija en el primer pivote y no cambia, para que una figura no cambie
   de tamaño «por comparación» con lo que pase después.
3. La ruptura se lee solo sobre cierres, con un margen de confirmación y una ventana de fracaso.
4. Un techo y su suelo espejo comparten implementación; figuras distintas, no.
5. La tendencia previa no filtra: se registra. Es coherente con «se observa pero no valida señal».
6. Un detector sin datos aptos no devuelve nada en lugar de adivinar.
7. Todos los valores de la sección 2 son provisionales y están en PARAMS-VALIDATION-001.
