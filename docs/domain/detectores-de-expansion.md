# Detectores de cuñas y formaciones expansivas (v1)

- **Estado:** en construcción por partes. Vigente hoy: la parte a (cuña ascendente y cuña
  descendente) y la parte b (formación expansiva). La parte c (diamante) tiene aquí su contrato
  **propuesto** (sección 10), en revisión de Jessica; no hay código todavía.
- **Fecha:** 2026-09-26
- **Tarea:** POINT3-EXPANSION-001 (5 de 7 del punto 3), partes a y b.
- **Depende de:** [detectores-de-continuacion.md](detectores-de-continuacion.md) (el canal de dos
  rectas y todo lo que comparte la familia: ruptura por cierre, evidencia de reprueba y de volumen,
  ápice), [detectores-de-reversion.md](detectores-de-reversion.md) (la fontanería común),
  [figuras-chartistas.md](figuras-chartistas.md) e [instancia-de-figura.md](instancia-de-figura.md).
- **Código:** `backend/src/freyja_backend/domain/pattern_wedge.py` (cuñas),
  `pattern_broadening.py` (formación expansiva) y el canal de `pattern_channel.py`. Dominio puro,
  sin E/S. Pruebas en `backend/tests/unit/test_pattern_wedge.py` y `test_pattern_broadening.py`.

Lo dicho en los documentos anteriores sobre **qué hace y qué no hace un detector** vale aquí sin
cambios: función pura de lo que se sabía en un instante, sin patrones de velas ni indicadores, sin
señal, lado, objetivo, vencimiento ni confianza, y con datos no aptos no juzga nada.

## 1. Decisiones de producto aprobadas

Las cuñas se modelan **por su geometría**, con sesgo tradicional descriptivo; su papel de
continuación o de reversión depende de la tendencia previa y de hacia dónde rompan (Jessica,
2026-09-26, al aprobar POINT3-CONTINUATION-001). La formación expansiva sigue el mismo criterio: su
sesgo tradicional es `CONTEXT_DEPENDENT` y la dirección la dice la ruptura. Nada de esto es una
decisión nueva.

## 2. Parámetro nuevo (`continuation-params-v1`)

Las cuñas usan los parámetros de las figuras de dos fronteras (`slope_min`, `contact_tolerance`,
`breakout_margin`, etc., ver el documento de continuación) y añaden uno. **Provisional y sin
validar**; está en PARAMS-VALIDATION-001. Como todo lo de la familia, relativo a la altura de la figura.

| Parámetro | Valor | Significado |
| --------- | ----- | ----------- |
| `wedge_convergence_min` | 0,30 | Solo cuñas: las fronteras convergen si la separación entre ellas al último contacto es, como mucho, `1 - esto` de la altura inicial. |

No cambia la versión `continuation-params-v1`: nada se ha persistido todavía con ella. Debe cumplirse
`parallel_tolerance < wedge_convergence_min`, para que unas fronteras no sean a la vez paralelas y
convergentes; un valor incoherente se rechaza al construir los parámetros.

## 3. La cuña

Una cuña es el **mismo canal** de los triángulos y el rectángulo, con dos condiciones sobre las
pendientes de sus fronteras (medidas, como siempre, sobre lo que se mueve cada recta del primer al
último contacto, en fracción de la altura):

- **Las dos fronteras se inclinan en el mismo sentido**, al menos `slope_min` cada una: las dos suben
  (cuña ascendente, `RISING_WEDGE`) o las dos bajan (cuña descendente, `FALLING_WEDGE`).
- **Convergen**: la separación al último contacto es, como mucho, `1 - wedge_convergence_min` de la
  altura inicial. Es inclusivo: exactamente eso basta.

| Detector | Versión | Frontera superior | Frontera inferior | Sesgo tradicional |
| -------- | ------- | ----------------- | ----------------- | ----------------- |
| `RISING_WEDGE` | `rising-wedge-detector-v1` | sube | sube más deprisa | bajista |
| `FALLING_WEDGE` | `falling-wedge-detector-v1` | baja más deprisa | baja | alcista |

Con eso, las cuñas quedan separadas del resto de la familia por la geometría y nada más:

- un **triángulo** tiene una frontera plana o fronteras que se inclinan en sentidos opuestos;
- un **rectángulo** no tiene ninguna inclinada;
- un **canal paralelo** inclinado no converge (es una bandera si sigue a un mástil, y si no, nada);
- una inclinación intermedia, entre `flat_tolerance` y `slope_min`, no es ninguna figura de la familia.

## 4. La formación expansiva

**Alcance: solo el megáfono clásico** (techo creciente y suelo decreciente). Las variantes expansivas
**inclinadas**, con las dos fronteras moviéndose en el mismo sentido y separándose (por ejemplo, las
dos suben y la superior más deprisa), son otra geometría y **no** las cubre este detector: no
cumplen «la inferior baja». Si se quisieran, serían un detector aparte con su propio contrato. Una
vela aislada muy grande, o un aumento de la volatilidad, tampoco es la figura: hacen falta cinco
swings ordenados que respalden las dos fronteras.

Es el mismo canal con las fronteras **al revés que el triángulo simétrico**: el precio oscila entre
una frontera superior que **sube** (máximos cada vez más altos) y una inferior que **baja** (mínimos
cada vez más bajos), y las dos se separan.

- **Pendientes:** la superior sube al menos `slope_min` de la altura y la inferior baja al menos
  `slope_min` de la altura (medidas como siempre, del primer al último contacto). Con eso las
  fronteras **divergen por construcción**: la separación final supera a la inicial en la suma de
  ambos movimientos. No hay parámetro de divergencia aparte.
- **Contactos crecientes:** cada máximo es **estrictamente** más alto que el anterior y cada mínimo
  **estrictamente** más bajo. Dos máximos iguales, o uno más bajo, no son una formación expansiva
  aunque las rectas por el primero y el último la insinúen.
- **Cinco swings:** la figura no existe hasta el quinto (tres de un tipo y dos del otro), no hasta el
  cuarto como el resto de la familia. El catálogo de figuras ya lo exigía (`min_anchor_pivots` = 5); el
  detector lo aplica a su crecimiento (`min_swings`).
- **Sin ápice:** las rectas se separan, no se cortan, así que no hay caducidad por ápice. Caduca
  solo por edad (`max_age_candles`).
- **Ruptura:** como en todo el canal, el primer cierre más allá de cualquiera de las dos fronteras
  decide la dirección, y el sesgo (`CONTEXT_DEPENDENT`) no interviene.

| Detector | Versión | Frontera superior | Frontera inferior | Sesgo tradicional |
| -------- | ------- | ----------------- | ----------------- | ----------------- |
| `BROADENING_FORMATION` | `broadening-formation-detector-v1` | sube | baja | según el contexto |

Queda separada del resto de la familia solo por las pendientes: es el espejo del triángulo
simétrico, y una frontera plana (triángulos, rectángulo) o las dos en el mismo sentido (cuñas,
canales, banderas) no la cumplen.

**Una formación expansiva sigue haciendo extremos nuevos.** Un máximo nuevo que cierra por encima de
la recta superior de la figura que acaba justo antes es, para esa figura, una ruptura (y puede
fracasar si el precio vuelve dentro). La figura que **incluye** ese máximo es otra, un swing más
tarde, y también queda en el historial. Es la consecuencia de usar rectas por el primer y el último
contacto y de dejar de crecer cuando el precio las supera (sección 3 del documento de continuación).

## 5. Estados, ruptura y sesgo

Todo lo de la sección 4 del documento de continuación vale sin cambios: cuatro contactos antes de
que exista la figura (no hay `FORMING`), se vigilan **las dos fronteras**, el primer cierre más allá
de cualquiera de ellas es la ruptura y da la dirección (`CONFIRMED_UP` por la superior,
`CONFIRMED_DOWN` por la inferior), la ruptura que fracasó no se deshace, y no existe la invalidación
por cerrar contra el sesgo.

**Cuatro cosas que se conservan por separado**, cada una en su sitio del registro y ninguna
deducida de otra:

| Qué | Dónde queda | Quién la decide |
| --- | ----------- | --------------- |
| El **tipo** de figura (`RISING_WEDGE`, `FALLING_WEDGE`) | `pattern_type`, fijo | la geometría; nunca se renombra por lo que ocurra después |
| La **tendencia anterior** | evidencia `PRIOR_TREND` (`state`) | el clasificador del punto 2, en el primer contacto |
| El **sesgo tradicional** | `traditional_bias` | el catálogo: dato del tipo, no de la tendencia ni de la ruptura |
| La **dirección real de la ruptura** | `breakout` y el estado (`CONFIRMED_UP` o `CONFIRMED_DOWN`) | el primer cierre más allá de una frontera, con el margen versionado |

Por eso una cuña ascendente puede leerse como reversión (tras una subida, rompiendo hacia abajo) o
como continuación (tras una bajada, rompiendo hacia abajo), y una que rompe contra su sesgo clásico
queda registrada tal cual, sin cambiar su nombre ni su sesgo.

**El sesgo tradicional no interviene.** La cuña ascendente es «bajista» y la descendente «alcista»
según la tradición, pero eso es un dato del tipo de figura, no una regla del detector: si una cuña
ascendente rompe al alza, se registra `CONFIRMED_UP` por la frontera superior, tal cual ocurrió.
Que la cuña sea aquí una continuación o una reversión no lo decide el detector: se conserva la
tendencia previa como contexto (`PRIOR_TREND`, solo `state`) y la ruptura dice lo demás.

Las cuñas convergen, así que tienen **ápice**: pasado el punto en que las rectas se cortan no puede
empezar una ruptura, y una cuña sin resolver antes de él caduca (`TOO_LONG`), como los triángulos.
La formación expansiva no tiene ápice (sección 4).

## 6. Evidencia

La misma que la familia (sección 5 del documento de continuación): `CHANNEL` (con `upper_rise`,
`lower_rise`, altura y separación al final), `PRIOR_TREND`, `BREAKOUT_SCAN`, `RETEST` y
`BREAKOUT_VOLUME`. Ninguna es un requisito.

## 7. Límites conocidos

- Los umbrales son provisionales y se validarán con datos reales (PARAMS-VALIDATION-001).
- Con solo dos contactos por frontera, unas fronteras de pendientes casi iguales pueden quedar
  justo a un lado o a otro de `wedge_convergence_min`; por eso el umbral se prueba exactamente en su
  valor y a ambos lados.
- Si el precio sale de las rectas antes de completar el cuarto contacto (el quinto en la formación
  expansiva) no hay figura, como en el resto de la familia.
- La altura de referencia de toda tolerancia es la que hay entre las rectas al **primer** contacto,
  la más pequeña en una figura que se ensancha. En la formación expansiva los umbrales relativos a
  ella (`min_height_fraction`, `contact_tolerance`, `breakout_margin`) son por tanto más exigentes que
  para una figura de altura constante. Es un umbral provisional que se validará con datos reales.

## 8. Lo que este documento no decide

El diamante (parte c de POINT3-EXPANSION-001, sección 10, propuesto), cómo se integran varias
figuras como evidencia de una hipótesis (POINT3-HYPOTHESIS-001), objetivos, entradas, vencimientos,
señales y órdenes, y la persistencia de las instancias.

## 9. Ejemplos: lo que pasa y lo que falla

Una figura de altura 20 entre sus dos rectas al primer contacto:

| Regla | Parámetro | Pasa | Falla |
| ----- | --------- | ---- | ----- |
| Convergen: separación al final como mucho 0,70 de la altura (14) | `wedge_convergence_min` = 0,30 | 13,99 y **14** (exacto) | 14,01 y 20 |
| Cada frontera sube al menos 0,15 de la altura (3) | `slope_min` = 0,15 | **3** (exacto) | 2,99 |
| Las dos en el mismo sentido | — | ambas suben (o ambas bajan) | una sube y otra baja (triángulo simétrico); una plana (triángulo) |

Una serie que sube hasta 130, retrocede hasta 116 y rebota entre máximos en 132, 134 y 135 y
mínimos en 121 y 126 es una cuña ascendente: las dos fronteras suben (3 y 10 en la altura de 14,5) y
la separación acaba en 7,5. Si el precio cierra por debajo de la inferior, `CONFIRMED_DOWN`; si cierra
por encima de la superior, `CONFIRMED_UP`. La serie con las mismas ideas al revés es la cuña
descendente.

Una serie que sube hasta 130 y luego oscila con máximos en 130, 133 y 137 y mínimos en 116 y 106 es
una formación expansiva: la superior sube 7 y la inferior baja 20 en una altura inicial de 10, y la
separación acaba en 37. Si el precio cierra por debajo de la inferior, `CONFIRMED_DOWN`; por encima
de la superior, `CONFIRMED_UP`. Dada la vuelta (mínimos cada vez más bajos primero) es la misma
figura, con los mínimos como primer contacto.

| Regla | Parámetro | Pasa | Falla |
| ----- | --------- | ---- | ----- |
| La superior sube al menos 0,15 de la altura (20) y la inferior baja otro tanto | `slope_min` = 0,15 | +3 y −3 (exactos) | +2,99 o −2,99 |
| Cada máximo más alto que el anterior, cada mínimo más bajo | — | 100, 110, 120 y 90, 80 | 100, 100, 120 o 100, 99, 120; 90, 90 o 90, 91 |
| Cinco swings como mínimo | — | tres máximos y dos mínimos (o al revés) | dos y dos |

## 10. El diamante (parte c): contrato propuesto

**Estado: contrato en revisión de Jessica** (segunda revisión). Nada de esta sección está
implementado. Jessica aceptó para la v1 las cinco decisiones de la propuesta y la secuencia de seis
swings, los vértices consecutivos, el límite de 200 velas y `diamond-params-v1` propio; y pidió
corregir la regla temporal de las rupturas «en vivo» (10.4) y aclarar si un contacto nuevo cambia las
fronteras (10.5). Cuando se apruebe el diff de este documento, el detector se escribe conforme a él.

### 10.1 Qué es

Dos fases conectadas: primero el precio **se expande** (máximos cada vez más altos y mínimos cada vez
más bajos) y después **se contrae** (máximos cada vez más bajos y mínimos cada vez más altos). El
punto más ancho queda en la transición. Un diamante es, pues, un megáfono seguido de un triángulo
simétrico que comparten el punto más ancho.

- Una formación expansiva que **nunca se contrae** sigue siendo una formación expansiva (sección 4).
- Un triángulo que **solo se comprime** no es un diamante (no tiene fase de expansión).
- Una cuña no lo es: en una cuña las dos fronteras van en el mismo sentido y no hay expansión.
- «De techo» y «de suelo» **no son tipos**: el catálogo tiene un solo `DIAMOND` con sesgo
  `CONTEXT_DEPENDENT`. Que aparezca tras una subida o tras una bajada es contexto (`PRIOR_TREND`), no
  clasificación. También existen diamantes de continuación: el contexto no demuestra hacia dónde sale.

### 10.2 Los seis pivotes, en orden exacto

Se trabaja con swings confirmados y alternados, `s0 … s5` en orden cronológico. Con seis swings
alternados solo hay dos ordenaciones posibles, y **los dos centrales (`s2` y `s3`) son siempre los
vértices**, el máximo y el mínimo del diamante:

| | `s0` | `s1` | `s2` | `s3` | `s4` | `s5` |
| --- | --- | --- | --- | --- | --- | --- |
| **A (empieza por un máximo)** | máximo 1 | mínimo 1 | **máximo 2 (vértice superior)** | **mínimo 2 (vértice inferior)** | máximo 3 | mínimo 3 |
| **B (empieza por un mínimo)** | mínimo 1 | máximo 1 | **mínimo 2 (vértice inferior)** | **máximo 2 (vértice superior)** | mínimo 3 | máximo 3 |

Condiciones, en ambos casos, sobre los precios de los pivotes:

- **Expansión** (`s0`…`s3`): máximo 1 **<** máximo 2 y mínimo 1 **>** mínimo 2. Las fronteras de
  expansión son la recta por máximo 1 y máximo 2, y la recta por mínimo 1 y mínimo 2.
- **Contracción** (`s2`…`s5`): máximo 3 **<** máximo 2 y mínimo 3 **>** mínimo 2. Las fronteras de
  contracción son la recta por máximo 2 y máximo 3, y la recta por mínimo 2 y mínimo 3.
- Las comparaciones son **estrictas**: dos máximos iguales no expanden ni contraen.
- Cada fase es un canal con las reglas de los demás (sección 3 del documento de continuación): la
  frontera superior de expansión sube y la inferior baja, y en contracción la superior baja y la
  inferior sube, cada una al menos `slope_min` de la altura de su fase. Los cierres entre el primer
  y el último contacto quedan dentro de las fronteras de la fase en la que están (en el solape,
  de las dos).
- Si la expansión tiene más swings (`s0 … sn`, con `n` mayor que 5), los vértices son los dos swings
  consecutivos `sk` y `sk+1` que son el máximo y el mínimo de todo el diamante, y las fases se leen
  igual: máximos estrictamente crecientes y mínimos estrictamente decrecientes hasta el vértice de su
  lado, y al revés a partir de él. En la contracción no hay más swings que los dos primeros
  posteriores a los vértices (`sk+2` y `sk+3`).
- **La geometría se congela al completarse.** Para cada primer ancla, el diamante es su **ventana más
  corta válida**: en cuanto la contracción tiene sus dos swings, las fronteras quedan fijadas. Los
  swings posteriores no la alargan ni la redibujan (10.5): son hechos de la instancia, no anclajes.

Los anclajes se nombran `UPPER_1…`, `LOWER_1…` en orden cronológico; los vértices y la transición se
registran en la evidencia `DIAMOND_PHASES` (10.6), no en los nombres.

**Consecutividad de los vértices: elección restrictiva de `diamond-params-v1`.** El máximo y el mínimo
del diamante deben ser swings **consecutivos**: hay un único punto de transición, el más ancho. Es una
elección de esta versión, no una ley de la figura: la tradición admite diamantes desfasados y aquí
quedan **excluidos**. Ejemplo de forma similar que **no** es un diamante en `diamond-params-v1`:

| Swing | `s0` | `s1` | `s2` | `s3` | `s4` | `s5` | `s6` | `s7` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Tipo | máx. | mín. | máx. | mín. | máx. | mín. | máx. | mín. |
| Precio | 130 | 118 | **140** | 110 | 136 | **100** | 132 | 108 |

Los máximos se expanden hasta 140 y después se contraen (130 < 140 > 136 > 132); los mínimos siguen
expandiéndose hasta 100 y solo entonces se contraen (118 > 110 > 100 < 108). La forma recuerda a un
diamante, pero el máximo (`s2`) y el mínimo (`s5`) no son consecutivos: tiene dos puntos de giro
distintos, no uno. Cambiar esa regla sería otra versión (`diamond-params-v2`), con sus propias pruebas.

### 10.3 Estados: incompleto, formado y con ruptura

| Momento | Qué se registra | Estado |
| ------- | --------------- | ------ |
| Solo hay expansión, o la contracción aún no tiene sus dos swings confirmados | **Nada.** No hay diamante incompleto: nada se afirma que no se pueda medir. La fase de expansión, si cumple sus reglas, ya consta como `BROADENING_FORMATION`. | ninguno |
| Los seis swings están confirmados y recibidos y las dos fases cumplen sus reglas | **Diamante formado.** Aún sin ruptura. | `GEOMETRICALLY_VALID` |
| Un cierre más allá de una frontera de salida, sin llegar al margen | Ruptura pendiente | `BREAKOUT_PENDING_CONFIRMATION` |
| Cierre más allá con al menos `breakout_margin × altura` | **Ruptura confirmada** con su dirección real | `CONFIRMED_UP` o `CONFIRMED_DOWN` |
| El precio vuelve dentro dentro de `failure_window_candles` | Ruptura fracasada, final | `FAILED_BREAKOUT` |
| Sin ruptura y pasado el ápice, o por edad | Caducada | `INVALIDATED` (`TOO_LONG`) |

- **No hay `FORMING`** (decisión aceptada). El estado de candidato es asunto de POINT3-CANDIDATE-001.
- **Salida.** Las fronteras de salida son las **dos de la contracción**: tras la transición las de
  expansión quedan siempre por fuera de ellas, así que cerrar fuera de una de expansión implica haber
  cerrado fuera de una de contracción. El primer **cierre** más allá de cualquiera de las dos es la
  ruptura, con la regla de cierre y margen de toda la familia. **Se registra la dirección real**,
  aunque contradiga el contexto de techo o de suelo.
- **Ápice.** Las fronteras de contracción convergen: pasado el punto en que se cortan no puede empezar
  una ruptura (la última vela en la que aún puede empezar es la última que cierra antes del ápice).

### 10.4 Pivotes conocidos tarde: tres tiempos y tres procedencias

Para cada figura y cada ruptura se guardan instantes **distintos**, en UTC, y nunca se mezclan:

| Instante | Qué es | De dónde sale |
| -------- | ------ | ------------- |
| **De mercado** | Cuándo ocurrió: la apertura y el cierre de la vela (de la ruptura, de la confirmación con margen, de cada pivote) | `open_time` y `close_time` de la vela |
| **De llegada** | Cuándo Freyja recibió esa vela: la primera versión cerrada recibida, sin reescribirse nunca (ADR 0008 §6) | `received_at` de la vela |
| **De formación en el mercado** (`market_formed_at`) | Cuándo el diamante existía ya en el mercado: el cierre de la vela que confirma el último de sus seis pivotes | máximo de los `confirmed_at` de los seis pivotes |
| **De conocimiento** (`known_at`) | Cuándo Freyja pudo reconocerlo: el **último** instante de llegada de **todas** las velas de las que depende, desde la del primer ancla hasta la que confirma el último pivote (los cierres entre contactos también deciden que la figura es válida) | máximo de las llegadas, aunque lleguen desordenadas |

Siempre `market_formed_at <= known_at`. Todos van en la evidencia `DIAMOND_TIMING`, con la apertura, el
cierre de mercado y la llegada de la vela de ruptura (y de la de confirmación con margen, si la hay).

**Regla temporal de la procedencia.** Lo que decide si una ruptura pudo ser detectada en vivo no es
cuándo se **recibió** la vela, sino cuándo **abrió**: Freyja solo puede haber esperado la salida de un
diamante que ya conocía cuando esa vela empezó. Es la misma cautela que se aplicó a los toques de
Fibonacci. Para la vela del **primer cierre más allá** de una frontera de salida:

| Procedencia (`provenance`) | Condición sobre esa vela | Qué significa |
| -------------------------- | ------------------------ | ------------- |
| `LIVE` | abre en `known_at` o después (`open_time >= known_at`); su cierre se recibe, necesariamente, después | Freyja ya conocía el diamante cuando la vela abrió: **detección en vivo**, la única que puede ser base operable |
| `AFTER_MARKET_FORMATION` (intermedia) | abre en `market_formed_at` o después, pero **antes** de `known_at` | El diamante ya existía en el mercado, pero Freyja aún no había recibido los datos que lo crean. Se describe, **no es operable** |
| `RETROSPECTIVE` | abre **antes** de `market_formed_at` | El diamante todavía no existía cuando la vela abrió. Se describe, **no es operable** |

- Que la vela **llegue tarde** no la hace en vivo: si abrió antes de `known_at`, es
  `AFTER_MARKET_FORMATION` o `RETROSPECTIVE` aunque se reciba después. Ejemplo: el diamante se conoce a
  las 10:05; una vela de 5 minutos que abrió a las 09:58 y cerró a las 10:03 llega a las 10:06. Freyja
  puede reconstruir lo ocurrido, pero no pudo detectar a las 10:03 la ruptura de un diamante que aún
  no existía: es `RETROSPECTIVE` (si el diamante se formó en el mercado a las 10:05) o, si ya se había
  formado en el mercado pero Freyja no lo conocía aún, `AFTER_MARKET_FORMATION`. En ningún caso `LIVE`.
- El límite es inclusivo hacia la detección en vivo: una vela que abre exactamente en `known_at` es
  `LIVE`; un instante antes, no.
- Solo `LIVE` puede ser una confirmación histórica operable. Las otras dos conservan estado y dirección
  (`CONFIRMED_UP`, `CONFIRMED_DOWN`, pendiente o fracasada) como descripción retrospectiva, nunca
  presentada como detectada en vivo en aquella vela. La procedencia forma parte del registro y no cambia
  después.
- La procedencia la fija la vela del **primer cierre más allá**: si la ruptura empezó antes de
  conocerse la figura, no es `LIVE` aunque el margen se alcance más tarde.
- **El diamante nace con el estado que ya tenía**: no pasa por `GEOMETRICALLY_VALID` para simular un
  nacimiento en vivo. Su primera evaluación lleva la ruptura y su procedencia.

**Si la figura se conoce cuando ya pasó su ápice.** Se mira qué ocurrió antes del ápice, con la misma
regla temporal:

1. Hubo un **primer cierre más allá antes del ápice**: el diamante nace con su ruptura y sigue las
   reglas de siempre (pendiente, confirmada o fracasada). Esa vela abrió antes del ápice y, por tanto,
   antes de `known_at` (que es posterior al ápice): su procedencia es `AFTER_MARKET_FORMATION` o
   `RETROSPECTIVE`, **nunca `LIVE`**.
2. **No** hubo ninguno: ya no es posible una ruptura futura, así que no puede ser `GEOMETRICALLY_VALID`.
   El detector lo devuelve como `INVALIDATED` (`TOO_LONG`) y, como en el resto de la familia, **una
   figura que nace ya invalidada nunca fue una figura: no se registra como instancia**. La evidencia
   `DIAMOND_TIMING` del resultado del detector dice que el ápice ya había pasado.

Lo mismo con la edad (10.7): un diamante que se conoce con más de 200 velas de edad no es una figura.

Otros efectos del tiempo, que se prueban:

- Antes de que se confirme y reciba lo último de lo que depende no hay diamante; el instante exacto de
  `known_at` es el primero en que existe.
- Con recepciones **desordenadas** (una vela anterior que llega después de una posterior), `known_at` es
  el máximo de las llegadas, y la procedencia se calcula con él, no con el orden del calendario.
- El resultado en cada instante depende solo de las velas cerradas y recibidas hasta él (verificado
  por instante y en paseos aleatorios, como en los otros detectores).

### 10.5 Un extremo nuevo después de formarse: geometría y estado por separado

**La geometría de una instancia registrada está congelada** desde que se completa (10.2): sus seis (o más)
anclajes y sus cuatro fronteras son las mismas en todas las evaluaciones, y **son las únicas con las
que se juzgan los cierres futuros**. Ningún hecho posterior añade un anclaje ni mueve una frontera. Lo
que llega después se guarda como **evidencia**, no como geometría. Si alguna versión futura quisiera
que un contacto nuevo moviera una frontera, tendría que guardar una **nueva versión de la geometría con
su propio instante de conocimiento** y conservar la anterior, y sería otra política (`diamond-params-v2`).

La regla de ruptura no cambia: **cierre fuera de la frontera más el margen**; una mecha no rompe nada.

| Qué ocurre | Se conserva el hecho | La geometría | El estado |
| ---------- | -------------------- | ------------ | --------- |
| **Mecha fuera de una frontera de salida y el cierre vuelve dentro** (10.5.1) | Sí: evidencia `WICK_PENETRATIONS` | **Ni se invalida ni se redibuja**: penetración tolerada, sin límite de profundidad | **No cambia**; en particular no es `CONFIRMED_UP` ni `CONFIRMED_DOWN` |
| **Cierre fuera de la frontera sin llegar al margen** | Sí: es la ruptura pendiente | Sin cambio | `BREAKOUT_PENDING_CONFIRMATION`; si vuelve dentro a tiempo, `FAILED_BREAKOUT` |
| **Cierre fuera con margen** | Sí: es la ruptura | Sin cambio | `CONFIRMED_UP` o `CONFIRMED_DOWN` |
| **Un swing nuevo por encima del vértice superior o por debajo del inferior**, sin cierre fuera de las fronteras (10.5.2) | Sí: en `WICK_PENETRATIONS` | La instancia **no cambia** (ese swing no entra en ella) | No cambia |
| **Un swing nuevo que sigue la contracción**, dentro de las fronteras y a `contact_tolerance × altura` de una de ellas (10.5.3) | Sí: evidencia `ADDITIONAL_CONTACTS` | **Sin cambio**: no es un anclaje y **no modifica las fronteras** con las que se evalúan los cierres siguientes | No cambia |

**10.5.1 Penetración por mecha.** Cuando una vela tiene su máximo por encima de la frontera superior
de salida (o su mínimo por debajo de la inferior) y **cierra dentro**, la evidencia `WICK_PENETRATIONS`
registra: cuántas velas lo han hecho, la hora de mercado de la primera y de la última, y la mayor
penetración como fracción de la altura de la contracción. Cambiar esa evidencia añade una evaluación
al historial (es un hecho nuevo), pero no cambia el estado ni la geometría. No hay una profundidad a
partir de la cual una mecha «cuente»: contar cierres es lo aprobado.

**10.5.2 Un swing más allá de un vértice.** Una mecha larga puede convertirse en un swing confirmado
por encima del vértice superior (o por debajo del inferior) sin que ningún cierre haya salido de las
fronteras. Ese swing **no forma parte** de la instancia registrada y **no la invalida** (los cierres
siguen dentro): queda como hecho en `WICK_PENETRATIONS`. Puede, en cambio, formar **otra candidata**: una
ventana con otro primer ancla se evalúa con estas mismas reglas, es otra instancia con otra
identidad y no reescribe la anterior.

**10.5.3 Un contacto más.** Un swing nuevo que sigue la contracción (máximo más bajo que el anterior,
mínimo más alto) y queda a `contact_tolerance × altura` de una frontera de contracción, con todos los
cierres desde el último contacto dentro de las fronteras, es un **contacto adicional**: `ADDITIONAL_CONTACTS`
guarda su hora, su precio y a qué frontera se acerca. Es evidencia. **No es un anclaje de la frontera ni
la modifica**: las evaluaciones posteriores juzgan los cierres con las mismas rectas de siempre.

### 10.6 Evidencia

- `DIAMOND_PHASES`: vértices (hora y precio de cada uno), anchura máxima (máximo menos mínimo del
  diamante), swings y velas de cada fase, movimiento de cada una de las cuatro fronteras, y
  `expansion_phase_is_broadening` (verdadero si la fase de expansión, por sí sola, cumple las reglas de
  `BROADENING_FORMATION`, o sea, tiene cinco swings o más).
- `DIAMOND_TIMING`: los instantes de 10.4 (mercado, llegada, `market_formed_at`, `known_at`) y `provenance` (`LIVE`, `AFTER_MARKET_FORMATION` o `RETROSPECTIVE`).
- `WICK_PENETRATIONS`: 10.5.1 y 10.5.2 (solo si ha ocurrido).
- `ADDITIONAL_CONTACTS`: 10.5.3 (solo si ha ocurrido).
- `PRIOR_TREND` (solo contexto), `BREAKOUT_SCAN`, `RETEST` y `BREAKOUT_VOLUME`, que **no son
  requisitos** (decisiones 2 y 4 del documento de continuación).

**¿Puede un tramo expansivo figurar como evidencia de un diamante posterior sin reescribir su
detección histórica?** Sí, y por diseño: la formación expansiva que ya se detectó sigue siendo su
propia instancia con su propio historial (solo se añade, nunca se reescribe), y el diamante que se
forma más tarde recalcula su fase de expansión con las mismas reglas y lo indica en
`expansion_phase_is_broadening`. No hay referencia cruzada entre detectores (cada uno es una unidad
independiente); quien quiera unirlas (POINT3-HYPOTHESIS-001) lo hace por el primer ancla. Se prueba que
la historia de la formación expansiva hasta el instante de la transición es idéntica con y sin el
resto del diamante.

### 10.7 Parámetros: `diamond-params-v1` (provisionales, sin validar)

`diamond-params-v1` es la versión del conjunto que usa el diamante y **es parte de la identidad** de
cada instancia. Reúne, con sus valores propios, los números de la familia que usa (un cambio en
`continuation-params-v1` no cambia un diamante ya registrado) y añade uno. Todos irán a
PARAMS-VALIDATION-001.

| Qué se decide | Parámetro | Valor | Nota |
| ------------- | --------- | ----- | ---- |
| Contactos intermedios | `contact_tolerance` | 0,15 | de la altura de la fase |
| Pendiente mínima de cada frontera | `slope_min` | 0,15 | de la altura de la fase |
| Tamaño | `min_height_fraction` | 0,25 | aplicado a la **anchura máxima** (máximo − mínimo del diamante) frente al rango de las `range_window_candles` (100) velas previas al primer ancla; no a la altura inicial, que en una expansión es la más pequeña |
| Duración mínima | `min_channel_candles` | 15 | **de cada fase**, por separado |
| Ruptura | `breakout_margin`, `failure_window_candles` | 0,10 · 10 | de la altura de la fase de contracción |
| Edad máxima | `diamond_max_age_candles` | **200 (nuevo)** | ver abajo |
| Consecutividad de los vértices | — | — | **estructural, fijada por la versión** (10.2): otra regla sería `diamond-params-v2` |
| Mínimo de swings | — | 6 | estructural (10.2) |

**Cómo se cuentan las 200 velas.** La **edad** de un diamante en un instante es la **diferencia de
posición** entre la última vela cerrada y recibida hasta ese instante y la vela del **primer ancla**
(la vela cuya apertura es la hora del pivote), en la serie de velas contiguas del detector:

    edad = posición(última vela cerrada) − posición(vela del primer ancla)

Se cuenta en velas, no en tiempo de reloj, y **no depende de cuándo se conozca la figura**. Una figura
sin ruptura caduca cuando `edad > 200`: con 199 y con 200 sigue viva, con 201 caduca (`TOO_LONG`). Si
ya hay ruptura en curso o resuelta, se sigue hasta su final como en toda la familia. La caducidad por
ápice puede llegar antes; el límite de 200 es el de las figuras cuyas fronteras de salida aún no se
han cortado. Es un valor provisional que se validará con datos reales.

### 10.8 Pruebas que se escribirán

- **Forma:** diamante formado tras subida y tras bajada (mismo detector, contexto distinto), las dos
  ordenaciones A y B de los seis pivotes; ruptura por cada uno de los dos lados y ruptura contra el
  contexto; ruptura pendiente y fracasada; expansión sin contracción (nada); contracción sin expansión
  (nada); una cuña ascendente y una descendente que no se clasifican como diamante; la formación
  expansiva anterior intacta; **la forma desfasada de 10.2 (excluida)**; comparaciones estrictas.
- **Tiempo y procedencia:** el instante exacto de `known_at`; el ejemplo de 10.4 (vela que cierra antes
  de conocerse la figura y llega después: nunca `LIVE`); una vela que abre **exactamente** en
  `known_at` (`LIVE`) y otra un instante antes (no); una vela que abre entre `market_formed_at` y
  `known_at` (`AFTER_MARKET_FORMATION`) y otra antes de `market_formed_at` (`RETROSPECTIVE`); una vela
  `LIVE` que llega **tarde** (sigue siendo `LIVE`, con su retraso visible); **recepciones desordenadas**
  (una vela anterior que llega después de una posterior mueve `known_at` y la procedencia sigue a
  `known_at`, no al calendario); ruptura con margen alcanzado después (procedencia por su primer
  cierre); ninguna ruptura retrospectiva se etiqueta `LIVE`.
- **Ápice:** figura conocida **después del ápice**, con ruptura anterior (nace con ella, nunca `LIVE`) y
  sin ella (no se registra, nunca `GEOMETRICALLY_VALID`), y con recepciones desordenadas que retrasan
  `known_at` más allá del ápice; figura conocida con más de 200 velas.
- **Extremos nuevos y geometría congelada:** mecha fuera con cierre dentro (ni `CONFIRMED_*` ni cambio
  de geometría, hecho registrado); swing por encima del vértice sin cierre fuera (la instancia no
  cambia; posible otra candidata); contacto adicional (queda como evidencia y **las fronteras de las
  evaluaciones posteriores son idénticas a las anteriores**); un extremo que deshace la contracción
  **antes** de que exista figura válida (no hay figura); todas las evaluaciones de una instancia
  comparten sus anclajes y sus rectas.
- **Edad:** 199, 200 y 201 velas (viva, viva, caducada).
- **Generales:** umbrales exactos en su valor y a ambos lados; datos no aptos; sin look-ahead por
  instante y en paseos aleatorios; y mutación del código.

### 10.9 Decisiones

Aceptadas por Jessica para la v1 al revisar la propuesta:

1. **No hay diamante incompleto ni `FORMING`.**
2. **Seis swings como mínimo**, sin exigir simetría entre las fases.
3. **`diamond_max_age_candles` = 200**, valor provisional, con límite inclusivo.
4. **Se vigilan las dos fronteras de contracción** y se registra la dirección real.
5. **La fase de expansión del diamante puede tener menos swings que la formación expansiva
   independiente** (`expansion_phase_is_broadening` deja constancia).
6. **La secuencia de seis swings, los vértices consecutivos y `diamond-params-v1` propio**, como
   política provisional versionada (10.2 y 10.7).
7. **Las penetraciones por mecha se conservan y no son rupturas confirmadas** (10.5).

Incorporadas a petición suya en esta revisión:

8. **Procedencia por la apertura de la vela** (10.4): `LIVE` solo si la vela del primer cierre más allá
   **abre** cuando Freyja ya conocía el diamante (`open_time >= known_at`); la recepción tardía no la
   hace en vivo. Procedencia intermedia `AFTER_MARKET_FORMATION`, no operable; y `RETROSPECTIVE`. Se
   guardan por separado el cierre de mercado y la recepción.
9. **Figura conocida tras su ápice** (10.4): nace solo si hubo ruptura antes de él, y entonces nunca es
   `LIVE`; si no, no se registra.
10. **La geometría registrada está congelada** (10.2 y 10.5): un contacto adicional es evidencia
    (`ADDITIONAL_CONTACTS`), no un anclaje, y no modifica las fronteras de las evaluaciones posteriores.
    Un cambio de frontera exigiría una nueva versión de la geometría con su propio instante de
    conocimiento, conservando la anterior, y sería otra política.
