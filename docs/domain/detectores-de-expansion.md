# Detectores de cuñas y formaciones expansivas (v1)

- **Estado:** en construcción por partes. Vigente hoy: la parte a (cuña ascendente y cuña
  descendente) y la parte b (formación expansiva). Pendiente, en su propio cambio: el diamante (c).
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

El diamante (parte c de POINT3-EXPANSION-001), cómo se integran varias
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
