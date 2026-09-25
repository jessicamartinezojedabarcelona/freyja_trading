# Catálogo canónico de figuras chartistas (v1)

- **Estado:** vigente. Es el único contrato de figuras chartistas de Freyja 2.0.
- **Fecha:** 2026-09-25
- **Tarea:** POINT3-DOMAIN-001 (1 de 7 del punto 3). Documentación vinculante: **no
  implementa código**, ni migraciones, ni API, ni interfaz.
- **Depende de:** POINT2-TEST-001 y los contratos que cierra:
  [contexto-y-tendencia.md](contexto-y-tendencia.md) (tendencia y su relación con una hipótesis),
  [estructura-de-precio.md](estructura-de-precio.md) (pivotes y puntos de giro) y
  [validacion-del-punto-2.md](validacion-del-punto-2.md).
- **Lo desarrollan:** POINT3-MODEL-001 → REVERSAL-001 → CONTINUATION-001 → EXPANSION-001 →
  HYPOTHESIS-001 → TEST-001.

Este documento fija **qué es** cada una de las veinte figuras aprobadas, cómo se llama y qué
significa tradicionalmente. **No fija** los umbrales numéricos con los que se detectan
(tolerancias, número mínimo de velas, inclinaciones): eso lo definen los detectores de los
puntos siguientes, con parámetros versionados. Tampoco define cómo se representa una figura
concreta detectada: es POINT3-MODEL-001.

## 1. Qué es (y qué no es) una figura

Una **figura chartista** es una **geometría formada por los pivotes confirmados y las
fronteras del precio** en un tramo de velas cerradas de un instrumento y una temporalidad, a la
que la lectura técnica tradicional asigna un significado.

- **No es una señal.** Ni una orden, ni una alerta, ni una recomendación. Que exista una figura
  no dice «compra» ni «vende».
- **No es un patrón de velas.** Los patrones de una, dos o tres velas (martillo, envolvente,
  estrella…) pertenecen **exclusivamente al punto 4**. Una figura se construye sobre pivotes, no
  sobre la forma de una vela.
- **No es un indicador.** No usa RSI, MACD, medias ni bandas (punto 5). El volumen tampoco forma
  parte de la definición: si un detector lo usa, será una evidencia adicional declarada por él.
- **No es una estrategia ni una decisión.** Una estrategia podrá declarar que necesita una
  figura, pero la figura no sabe qué estrategia la usa (punto 6).
- **No está ligada a Fibonacci, a _scalping_ ni a un producto.** Una figura vale igual en
  `CRYPTO × SPOT`, en Forex o como fundamento de una binaria; qué significa actuar según ella en
  cada producto es de la estrategia y del producto, nunca de la figura (ver la sección 6).
- **No es una probabilidad.** Puede aportar una **hipótesis direccional**; no aporta una
  probabilidad calibrada ni una afirmación de ventaja estadística (CLAUDE.md §4). Esa evidencia
  exige validación (punto 15) y este contrato no la aporta.

## 2. Vocabulario

### Familia de catálogo

Solo agrupa el catálogo aprobado para su presentación; **no determina el significado** de una
figura (para eso están los roles):

| Grupo | Figuras |
| ----- | ------- |
| `REVERSAL` (reversión) | 8 |
| `CONTINUATION_CONSOLIDATION` (continuación y consolidación) | 8 |
| `COMPRESSION_EXPANSION_CONTEXTUAL` (compresión, expansión y contextuales) | 4 |

### `traditional_roles` (conjunto, uno o varios)

El papel que la lectura tradicional le atribuye. **Una figura puede tener varios**: no se fuerza
a una familia única a cuñas, triángulos ni rectángulos, que según el contexto continúan o
revierten.

| Rol | Significa |
| --- | --------- |
| `REVERSAL` | Tradicionalmente anuncia un cambio del sentido de la tendencia previa. |
| `CONTINUATION` | Tradicionalmente anuncia que la tendencia previa se reanuda. |
| `CONSOLIDATION` | Una pausa o contención del precio, sin sentido propio hasta que se resuelve. |
| `COMPRESSION` | Rango que se estrecha: la volatilidad se contrae. |
| `EXPANSION` | Rango que se ensancha: la volatilidad crece. |

### `traditional_bias` (uno solo)

El sentido que la tradición asocia a la resolución de la figura. **Es tradición, no evidencia.**

| Sesgo | Significa |
| ----- | --------- |
| `BULLISH` | Se resuelve tradicionalmente al alza. |
| `BEARISH` | Se resuelve tradicionalmente a la baja. |
| `BREAKOUT_DEPENDENT` | No lo tiene hasta que se rompe: manda el lado de la ruptura. |
| `CONTEXT_DEPENDENT` | Depende de la tendencia previa (revierte la que traía). |

## 3. Reglas comunes a las veinte figuras

1. **Solo velas cerradas y pivotes confirmados.** Una figura nunca se apoya en una vela en curso
   ni en un pivote `PROVISIONAL` (estructura de precio, sección 2). Cero _look-ahead_.
2. **Lo que se conoce en cada instante.** Una figura solo existe a partir del instante en que sus
   anclas son conocibles; una detección posterior no cambia lo que se sabía antes.
3. **La interpretación tradicional no es una orden.** Un sesgo alcista no es «comprar»; una
   ruptura no es una entrada.
4. **Varias figuras pueden coexistir** sobre las mismas velas (un triángulo dentro de un
   rectángulo mayor, una bandera dentro de una cuña). Ninguna anula a otra por existir.
5. **Una figura es independiente del estado de tendencia** del punto 2. No lo calcula ni lo
   sustituye: un `RANGE` es un estado del mercado y un `RECTANGLE` es una geometría con
   contactos en dos fronteras; pueden coexistir o no, y ninguno implica al otro. La relación
   entre ambas la establece una estrategia (POINT3-HYPOTHESIS-001 y la política de tendencia).
6. **La ruptura se confirma con el cierre.** Una mecha que cruza una frontera no la rompe; la
   ruptura tradicional se lee sobre el **cierre** de una vela (como en la tendencia). Cuánto y
   cuántas velas es del detector.
7. **Un objetivo de precio no forma parte de la figura.** El «movimiento medido» tradicional
   pertenece a los objetivos de las hipótesis (punto 10 y siguientes), no a este contrato.
8. **Precios exactos**, sin coma flotante, e instantes en UTC (CLAUDE.md §6), como en el resto.
9. **Todas las figuras se modelan; su implementación puede hacerse por fases.** Que una figura
   esté en el catálogo no significa que ya se detecte.

## 4. El catálogo

Cada figura tiene un identificador canónico (mayúsculas con guion bajo, fijo y en inglés, como el
resto de identificadores de dominio) y un nombre en español para la documentación. «Anclas» es el
**mínimo estructural** de pivotes confirmados que la geometría necesita; un detector puede
exigir más, nunca menos.

### 4.1 Reversión

| Identificador | Nombre | Roles | Sesgo | Geometría y lectura tradicional | Anclas |
| ------------- | ------ | ----- | ----- | -------------------------------- | ------ |
| `HEAD_AND_SHOULDERS_TOP` | Hombro-cabeza-hombro | `REVERSAL` | `BEARISH` | Tres máximos: el central (cabeza) más alto que los dos laterales (hombros), que son comparables entre sí. Una **línea de cuello** une los dos mínimos intermedios (puede ser inclinada). Se lee tras una tendencia alcista; su ruptura a la baja, por cierre, la confirma. | 5 (H, L, H, L, H) |
| `HEAD_AND_SHOULDERS_BOTTOM` | Hombro-cabeza-hombro invertido | `REVERSAL` | `BULLISH` | La misma geometría invertida: tres mínimos, el central más bajo; línea de cuello por los dos máximos intermedios. Se lee tras una tendencia bajista; su ruptura al alza la confirma. | 5 (L, H, L, H, L) |
| `DOUBLE_TOP` | Doble techo | `REVERSAL` | `BEARISH` | Dos máximos comparables separados por un mínimo intermedio, cuyo nivel es el soporte que, roto por cierre, la confirma. Tras una tendencia alcista. | 3 (H, L, H) |
| `DOUBLE_BOTTOM` | Doble suelo | `REVERSAL` | `BULLISH` | Dos mínimos comparables separados por un máximo intermedio, cuyo nivel es la resistencia que, rota por cierre, la confirma. Tras una tendencia bajista. | 3 (L, H, L) |
| `TRIPLE_TOP` | Triple techo | `REVERSAL` | `BEARISH` | Tres máximos comparables separados por dos mínimos comparables, que forman el soporte cuya ruptura la confirma. Tras una tendencia alcista. | 5 (H, L, H, L, H) |
| `TRIPLE_BOTTOM` | Triple suelo | `REVERSAL` | `BULLISH` | Tres mínimos comparables separados por dos máximos comparables, que forman la resistencia cuya ruptura la confirma. Tras una tendencia bajista. | 5 (L, H, L, H, L) |
| `ROUNDING_TOP` | Techo redondeado | `REVERSAL` | `BEARISH` | Un ascenso y un descenso graduales que dibujan un **arco** (cúpula), sin giros bruscos. Su geometría es una curva, no una secuencia de pivotes nítidos: las anclas son el extremo del arco y sus dos extremos, y la **base** une estos últimos. | 3 (extremo izquierdo, cima, extremo derecho) |
| `ROUNDING_BOTTOM` | Suelo redondeado | `REVERSAL` | `BULLISH` | El arco invertido (cuenco): descenso y ascenso graduales. Mismas anclas; la base une los extremos. | 3 (extremo izquierdo, fondo, extremo derecho) |

### 4.2 Continuación y consolidación

| Identificador | Nombre | Roles | Sesgo | Geometría y lectura tradicional | Anclas |
| ------------- | ------ | ----- | ----- | -------------------------------- | ------ |
| `BULL_FLAG` | Bandera alcista | `CONTINUATION` | `BULLISH` | Un **mástil**: avance brusco y de corta duración. Le sigue una consolidación breve entre dos fronteras aproximadamente paralelas, ligeramente descendentes o laterales. Se confirma con el cierre por encima de la frontera superior. | 2 del mástil (L, H) + 2 por frontera |
| `BEAR_FLAG` | Bandera bajista | `CONTINUATION` | `BEARISH` | Un mástil de caída brusca y una consolidación breve entre fronteras aproximadamente paralelas, ligeramente ascendentes o laterales. Se confirma con el cierre por debajo de la frontera inferior. | 2 del mástil (H, L) + 2 por frontera |
| `BULL_PENNANT` | Banderín alcista | `CONTINUATION` | `BULLISH` | Un mástil alcista seguido de una consolidación breve entre fronteras que **convergen** (un triángulo pequeño). Se confirma con el cierre por encima. | 2 del mástil + 2 por frontera |
| `BEAR_PENNANT` | Banderín bajista | `CONTINUATION` | `BEARISH` | Un mástil bajista seguido de una consolidación breve entre fronteras que convergen. Se confirma con el cierre por debajo. | 2 del mástil + 2 por frontera |
| `ASCENDING_TRIANGLE` | Triángulo ascendente | `CONTINUATION`, `REVERSAL` | `BULLISH` | Una **resistencia horizontal** y un soporte **ascendente**: las fronteras convergen. Tradicionalmente continúa una tendencia alcista, pero también puede aparecer al final de una bajista. Se confirma con el cierre por encima de la resistencia. | 2 por frontera |
| `DESCENDING_TRIANGLE` | Triángulo descendente | `CONTINUATION`, `REVERSAL` | `BEARISH` | Un **soporte horizontal** y una resistencia **descendente**: convergen. Tradicionalmente continúa una tendencia bajista, pero también puede coronar una alcista. Se confirma con el cierre por debajo del soporte. | 2 por frontera |
| `SYMMETRICAL_TRIANGLE` | Triángulo simétrico | `CONTINUATION`, `REVERSAL`, `COMPRESSION` | `BREAKOUT_DEPENDENT` | Máximos descendentes y mínimos ascendentes: dos fronteras que convergen sin favorecer un lado. **Su dirección depende de la ruptura**: la tradición lo lee como continuación, pero puede revertir. | 2 por frontera |
| `RECTANGLE` | Rectángulo | `CONSOLIDATION`, `CONTINUATION`, `REVERSAL` | `BREAKOUT_DEPENDENT` | Un soporte y una resistencia **horizontales y paralelos** con contactos en ambos. Es una contención del precio; **su dirección depende de la ruptura**. | 2 por frontera |

### 4.3 Compresión, expansión y contextuales

| Identificador | Nombre | Roles | Sesgo | Geometría y lectura tradicional | Anclas |
| ------------- | ------ | ----- | ----- | -------------------------------- | ------ |
| `RISING_WEDGE` | Cuña ascendente | `REVERSAL`, `CONTINUATION`, `COMPRESSION` | `BEARISH` | Dos fronteras **ascendentes que convergen** (la inferior más inclinada). Tradicionalmente bajista: revierte una tendencia alcista o, dentro de una bajista, continúa la caída. | 2 por frontera |
| `FALLING_WEDGE` | Cuña descendente | `REVERSAL`, `CONTINUATION`, `COMPRESSION` | `BULLISH` | Dos fronteras **descendentes que convergen**. Tradicionalmente alcista: revierte una bajista o, dentro de una alcista, continúa la subida. | 2 por frontera |
| `BROADENING_FORMATION` | Formación expansiva | `REVERSAL`, `EXPANSION` | `CONTEXT_DEPENDENT` | Máximos crecientes y mínimos decrecientes: dos fronteras que **divergen** y un rango cada vez mayor. Suele asociarse con el agotamiento de la tendencia previa; el sentido lo da esa tendencia. | 5 (3 de un tipo, 2 del otro) |
| `DIAMOND` | Diamante | `REVERSAL`, `EXPANSION`, `COMPRESSION` | `CONTEXT_DEPENDENT` | Una fase que se ensancha seguida de otra que se estrecha, con forma de rombo. Figura poco frecuente, asociada al agotamiento de la tendencia previa; el sentido lo da esa tendencia. | 6 o más, en dos fases |

Notas sobre la tabla:

- **Sesgos sin contradicción entre roles.** En una figura con roles `CONTINUATION` y `REVERSAL`
  (por ejemplo un triángulo ascendente) el sesgo es el mismo: `BULLISH` describe hacia dónde la
  tradición espera la resolución, no si esa resolución continúa o revierte lo anterior. Cuál de
  los dos casos es lo determina la tendencia previa, que no es propiedad de la figura.
- **`CONTEXT_DEPENDENT`** significa que el sesgo solo existe respecto de una tendencia previa
  (revierte la que traía). Cómo se conoce esa tendencia es el punto 2, y cómo se combina con la
  figura es POINT3-HYPOTHESIS-001.
- **Las anclas de una fase** son los pivotes que definen las fronteras: «2 por frontera» quiere
  decir dos contactos como mínimo en cada una.
- **Las figuras con mástil** exigen que el avance o la caída previos sean *bruscos y cortos*
  frente a la consolidación posterior; cuánto es «brusco» y «corto» lo fija el detector.

## 5. Lo que no se define aquí

Este contrato **no define**: tolerancias de igualdad entre pivotes ni de paralelismo, número
mínimo o máximo de velas de una figura, cómo se ajustan las fronteras o el arco, ni cuánto debe
cerrarse fuera para dar una ruptura por válida (POINT3-REVERSAL-001, CONTINUATION-001 y
EXPANSION-001, con parámetros versionados y sin validar); el ciclo de vida de una figura concreta
—formándose, válida, rota, fallida, invalidada— ni su representación (POINT3-MODEL-001); cómo se
integran varias figuras como evidencia (POINT3-HYPOTHESIS-001); objetivos de precio, entradas,
salidas ni riesgo; patrones de velas (punto 4); indicadores (punto 5).

Nada de esto se supone por lo escrito arriba.

## 6. Figuras y productos

Como en el contrato de contexto (sección 5), la orientación **no significa lo mismo en cada
producto**. Una figura con sesgo `BEARISH` en `CRYPTO × SPOT` significa abstenerse o salir, no
vender en corto. En Forex, una posición abierta simétrica; en una binaria, una afirmación sobre el
precio al vencimiento. La figura conserva su sesgo tradicional y **no decide** qué se hace con él.

## 7. Extensibilidad

El catálogo se amplía como **datos**, no como código que reescriba el contrato: una figura nueva
(por ejemplo, taza con asa, no incluida en las veinte) necesitaría su identificador, roles, sesgo
y geometría definidos aquí, una versión del catálogo y un detector propio. Ninguna figura se
añade ni se retira sin cambiar la versión de este contrato.

## 8. Glosario

| Término | Definición |
| ------- | ---------- |
| Figura | Geometría de pivotes y fronteras con un significado tradicional. No es señal. |
| Ancla | Pivote confirmado que fija un punto de la geometría. |
| Frontera | Línea (o curva) que contiene los máximos o mínimos de una figura: soporte, resistencia o línea de cuello. |
| Línea de cuello | Frontera que une los mínimos (o máximos) intermedios de un hombro-cabeza-hombro. |
| Mástil | Movimiento brusco y corto que precede a una bandera o un banderín. |
| Ruptura | Cierre de una vela fuera de una frontera de la figura. |
| Rol tradicional | Papel que la tradición técnica atribuye a la figura: revertir, continuar, consolidar, comprimir, expandir. |
| Sesgo tradicional | Sentido que la tradición asocia a la resolución. No es evidencia. |
| Hipótesis direccional | Afirmación con orientación (alcista o bajista) que una figura puede aportar; no es una probabilidad calibrada. |

## 9. Criterios de aceptación de esta tarea

- [x] Las veinte figuras tienen identificador, nombre, roles, sesgo y semántica canónicos
      (sección 4).
- [x] No se fuerza una familia única a cuñas, triángulos ni rectángulos: cada una tiene los
      roles que la tradición le atribuye (secciones 2 y 4).
- [x] No se mezcla ninguna figura con patrones de velas, indicadores, _scalping_, Fibonacci ni
      un producto concreto (secciones 1 y 6).
- [x] La interpretación tradicional no es una orden y no es una probabilidad calibrada
      (secciones 1 y 3).
- [x] Todas las figuras se modelan, con implementación posible por fases (sección 3.9).

## 10. Decisiones técnicas tomadas al redactar

Registradas aquí para que se puedan corregir; ninguna es de producto.

1. Los roles son un **conjunto** y el sesgo es **único**: así una figura como el triángulo
   ascendente puede continuar o revertir sin que el sesgo se contradiga.
2. El sesgo tiene cuatro valores, incluidos `BREAKOUT_DEPENDENT` y `CONTEXT_DEPENDENT`, para las
   figuras que la tradición no orienta por sí mismas.
3. Los techos y suelos redondeados se definen por un **arco**, no por pivotes nítidos, y sus
   anclas son el extremo y los dos extremos del arco.
4. Las «anclas» son un **mínimo estructural**, no un umbral de detección: un detector puede pedir
   más.
5. El volumen no forma parte de la definición de ninguna figura.
6. El catálogo son las veinte figuras aprobadas; añadir otras es un cambio versionado, con su
   detector.
7. Las clasificaciones de la tabla (roles y sesgos) son **lectura tradicional** de la literatura
   técnica habitual, no una afirmación de Freyja sobre su acierto.
