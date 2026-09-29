# Catálogo canónico de patrones de vela (v1)

- **Estado:** vigente. Es el único contrato de patrones de vela de Freyja 2.0.
- **Fecha:** 2026-09-27
- **Tarea:** POINT4-DOMAIN-001 (1 de 7 del punto 4). Documentación vinculante: **no implementa
  código**, ni migraciones, ni API, ni interfaz.
- **Depende de:** POINT3-TEST-001 (cierre del punto 3, ya completado), y de
  [figuras-chartistas.md](figuras-chartistas.md) e [instancia-de-figura.md](instancia-de-figura.md)
  como referencia de estilo y para la distinción entre una figura chartista y un patrón de vela
  (sección 9 de este documento).
- **Lo desarrollan:** POINT4-DOMAIN-001 → MODEL-001 → SINGLE-001 → MULTI-001 → CONTEXT-001 →
  HYPOTHESIS-001 → TEST-001.

Este documento fija **qué es** cada uno de los patrones de vela aprobados, cómo se llama, cuántas
velas necesita y qué significa tradicionalmente. **No fija** los umbrales numéricos con los que se
detecta cada uno (proporciones exactas de cuerpo, mecha y rango): eso lo definen los detectores de
POINT4-SINGLE-001 y POINT4-MULTI-001, con parámetros versionados. Tampoco define cómo se representa
una instancia concreta detectada (POINT4-MODEL-001), ni cómo la interpreta el contexto
(POINT4-CONTEXT-001), ni cómo se combina con otra evidencia en una hipótesis (POINT4-HYPOTHESIS-001).

## 1. Qué es (y qué no es) un patrón de vela

Un **patrón de vela** es una **geometría de una, dos o tres velas cerradas consecutivas** (cuerpo,
mechas y su relación entre sí) a la que la lectura técnica tradicional asigna un significado.

- **No es una figura chartista.** Las figuras del punto 3 se construyen sobre pivotes confirmados a
  lo largo de muchas velas; un patrón de vela se construye sobre la forma de una a tres velas
  concretas, sin pivotes. Los dos contratos son independientes y **nunca se fusionan** (sección 9).
- **No es un indicador.** No usa RSI, MACD, medias ni bandas (punto 5); el volumen tampoco forma
  parte de la definición geométrica.
- **No es una señal, una orden ni una decisión.** Que exista un martillo no dice «compra».
- **No es una probabilidad.** Aporta, como mucho, una **hipótesis direccional** interpretada según
  contexto (POINT4-CONTEXT-001, POINT4-HYPOTHESIS-001); no una probabilidad calibrada ni una
  afirmación de ventaja estadística (CLAUDE.md §4). Esa evidencia exige validación (punto 15).
- **No decide su propia interpretación.** La misma geometría puede leerse de formas opuestas según
  el contexto (sección 6): el patrón describe la forma, no el significado final.

## 2. Vocabulario

### Familia por número de velas

Solo agrupa el catálogo para su presentación; no determina el significado de un patrón.

| Familia | Patrones |
| ------- | -------- |
| Una vela | 9 |
| Dos velas | 8 |
| Tres velas | 6 |

### `traditional_bias` (uno solo, puede ser `NONE`)

El sentido que la tradición asocia al patrón, **antes** de aplicar contexto. Es tradición, no
evidencia (igual que en `figuras-chartistas.md`, sección 2).

| Sesgo | Significa |
| ----- | --------- |
| `BULLISH` | La tradición lo lee como alcista. |
| `BEARISH` | La tradición lo lee como bajista. |
| `CONTEXT_DEPENDENT` | La misma geometría es alcista o bajista solo según el contexto (tendencia previa): sin contexto, no tiene sesgo. |
| `NONE` | Indecisión, sin sesgo (el doji simple). |

### Funciones que un patrón puede cumplir dentro de una `StrategySpec` (punto 6)

Un patrón no decide su propia función: la declara la `StrategySpec` que lo use (POINT4-HYPOTHESIS-001,
punto 6). Se listan aquí porque son parte del vocabulario común del punto 4.

| Función | Significa |
| ------- | --------- |
| `REQUIRED` | Sin este patrón, la hipótesis no se declara. |
| `CONFIRMATION` | Refuerza una hipótesis que ya existe por otra evidencia. |
| `FILTER` | Descarta una hipótesis que, sin él, sería válida. |
| `CONFLICT` | Se registra como evidencia contraria; no borra la hipótesis. |
| `INFORMATIONAL` | Se conserva como dato, sin peso en la decisión. |

### Política de gaps (por mercado y producto)

Varios patrones de tres velas (`MORNING_STAR`, `EVENING_STAR`) se describen tradicionalmente con un
**hueco** entre cuerpos. `CRYPTO × SPOT` cotiza en continuo (sin huecos reales); Forex los tiene solo
en fines de semana; el `FOREIGN_EXCHANGE`/bolsa clásica los tiene a diario. Exigir un hueco real
donde el mercado no los produce nunca invalidaría el patrón por construcción. La política es
**configurable por mercado**, versionada, y ninguna de las tres opciones es la predeterminada
universal:

| Política | Significa |
| -------- | --------- |
| `GAP_REQUIRED` | El patrón exige un hueco real entre los cuerpos implicados. |
| `GAP_OPTIONAL` | El hueco, si existe, es evidencia adicional; su ausencia no invalida el patrón. |
| `GAP_NOT_APPLICABLE` | El mercado no produce huecos relevantes; la condición de hueco se omite. |

Qué política aplica a qué combinación de mercado y producto es una decisión técnica de
POINT4-MULTI-001 (con los parámetros que necesite), no de este documento.

**Decisión tomada (POINT4-TEST-001, seguimiento TWELVEDATA-4H-GRID-001, 29-09-2026):**
`CRYPTO` recibe `GAP_NOT_APPLICABLE` (cotiza en continuo, sin huecos reales). `FOREX` y `METALS`
reciben `GAP_OPTIONAL`: ambos pueden tener un hueco real, pero prácticamente solo en la reapertura
semanal — nunca vela a vela dentro de una sesión, en ninguna de las temporalidades intradía del
catálogo de Freyja — así que exigirlo (`GAP_REQUIRED`) dejaría `MORNING_STAR`/`EVENING_STAR`
virtualmente indetectables ahí, el mismo problema que este documento ya advierte para `CRYPTO`. Un
hueco real, si aparece, sigue siendo evidencia adicional. `METALS` se trata igual que `FOREX` por
ahora porque XAU/USD (Twelve Data) es un mercado de tipo OTC con un patrón de sesión equivalente al
de forex; si en el futuro Freyja añade un mercado con huecos diarios reales (una bolsa clásica), le
correspondería `GAP_REQUIRED`, no `GAP_OPTIONAL`. Implementado en
`candlestick_multi.py::_gap_policy_for_market`, aplicado cuando `ThreeCandleParams.gap_policy` se
deja sin fijar (`None`); un valor explícito siempre gana sobre el valor por mercado.

## 3. Estados

Ocho estados. Este documento fija su **significado**; el modelo de una instancia concreta, sus
transiciones exactas y qué contenido lleva cada uno es POINT4-MODEL-001 (mismo reparto que
`instancia-de-figura.md` hizo para las figuras chartistas).

| Estado | Significa |
| ------ | --------- |
| `FORMING` | Aún no han cerrado todas las velas que el patrón necesita. |
| `MORPHOLOGICALLY_VALID` | La geometría está completa (proporciones de cuerpo, mecha y orden temporal cumplidas), sin evaluar todavía el contexto. |
| `CONTEXT_VALID` | El contexto necesario (tendencia previa, localización) es compatible con la lectura tradicional del patrón. |
| `PENDING_CONFIRMATION` | El patrón exige una vela o condición posterior que aún no ha cerrado. |
| `CONFIRMED` | La confirmación exigida ya cerró: el patrón queda establecido como hecho, con su interpretación. |
| `FAILED` | La confirmación esperada no llegó, o llegó en sentido contrario. Final. |
| `INVALIDATED` | El patrón dejó de serlo (una vela posterior contradice su geometría, o su ancla deja de ser válida). Final. |
| `INSUFFICIENT_DATA` | Con los datos de ese momento no se puede juzgar (huecos, historia insuficiente, fuente no autorizada). Pausa, no estado final. |

- **Solo velas cerradas alcanzan `MORPHOLOGICALLY_VALID` en adelante.** Una vela en curso nunca
  produce nada más que, como mucho, la expectativa de estar `FORMING`.
- **`CONTEXT_VALID` no es automático.** Una geometría válida sin contexto suficiente, o con un
  contexto que no coincide con lo que el patrón necesita, quedaría en `MORPHOLOGICALLY_VALID` sin
  avanzar (POINT4-CONTEXT-001 define exactamente cuándo pasa a `CONTEXT_VALID`).
- **No todos los patrones necesitan `PENDING_CONFIRMATION`.** Un patrón de tres velas cuya tercera
  vela ya es la confirmación (p. ej. `MORNING_STAR`) puede llegar a `CONFIRMED` sin pasar por él; uno
  que tradicionalmente espera una vela más para confirmar (p. ej. una vela que cierre en la
  dirección que el patrón anticipa) sí lo necesita. Cuál necesita cuál es parte del catálogo
  (columna «Confirmación» de las tablas de la sección 5), no una regla genérica.

## 4. Reglas comunes a todos los patrones

1. **Solo velas cerradas.** Ningún patrón se apoya en una vela en curso. Cero _look-ahead_: una
   evaluación nunca usa una vela que aún no había cerrado en su instante.
2. **La interpretación tradicional no es una orden.** Un sesgo alcista no es «comprar».
3. **Varios patrones pueden coexistir** sobre las mismas velas (un doji que es a la vez parte de un
   patrón de tres velas). Ninguno anula a otro por existir.
4. **Una misma geometría no se cuenta dos veces con dos nombres** (sección 6): cuando dos patrones
   comparten geometría exacta, el catálogo dice explícitamente cuál se declara y con qué condición.
5. **La ruptura, si el patrón la tiene, se lee sobre cierres**, nunca sobre mechas.
6. **Precios exactos**, sin coma flotante, e instantes en UTC (CLAUDE.md §6), como en el resto del
   dominio.
7. **Todos los patrones se modelan; su implementación puede hacerse por fases** (SINGLE-001 primero,
   MULTI-001 después). Que un patrón esté en el catálogo no significa que ya se detecte.
8. **El volumen no forma parte de la definición geométrica** de ningún patrón de esta v1.

## 5. El catálogo

«Confirmación» dice si el patrón, además de su geometría, necesita un hecho posterior (una vela más,
o una condición sobre el cierre) para pasar de `CONTEXT_VALID` a `CONFIRMED`. «Contexto requerido»
resume qué necesita de la tendencia previa (punto 2) para que su lectura tradicional aplique; sin él,
el patrón existe pero no pasa de `MORPHOLOGICALLY_VALID` (sección 3).

### 5.1 Una vela

| Identificador | Nombre | Geometría | Sesgo | Contexto requerido | Confirmación |
| -------------- | ------ | --------- | ----- | ------------------- | ------------- |
| `DOJI` | Doji | Cuerpo prácticamente nulo (apertura ≈ cierre); mechas de cualquier longitud. | `NONE` | Ninguno: indecisión por defecto (sección 6). | No. |
| `DRAGONFLY_DOJI` | Doji libélula | Doji con mecha inferior larga y mecha superior mínima o nula (apertura y cierre cerca del máximo de la vela). | `CONTEXT_DEPENDENT` | Tendencia previa bajista, para leerse como posible giro alcista. | No. |
| `GRAVESTONE_DOJI` | Doji lápida | Doji con mecha superior larga y mecha inferior mínima o nula (apertura y cierre cerca del mínimo). | `CONTEXT_DEPENDENT` | Tendencia previa alcista, para leerse como posible giro bajista. | No. |
| `HAMMER` | Martillo | Cuerpo pequeño en el tercio superior del rango; mecha inferior larga (varias veces el cuerpo); mecha superior mínima o nula. | `CONTEXT_DEPENDENT` | Tendencia previa bajista. Misma geometría que `HANGING_MAN` (sección 6). | No. |
| `HANGING_MAN` | Hombre colgado | Idéntica a `HAMMER`. | `CONTEXT_DEPENDENT` | Tendencia previa alcista. Misma geometría que `HAMMER` (sección 6). | No. |
| `INVERTED_HAMMER` | Martillo invertido | Cuerpo pequeño en el tercio inferior del rango; mecha superior larga; mecha inferior mínima o nula. | `CONTEXT_DEPENDENT` | Tendencia previa bajista. Misma geometría que `SHOOTING_STAR` (sección 6). | No. |
| `SHOOTING_STAR` | Estrella fugaz | Idéntica a `INVERTED_HAMMER`. | `CONTEXT_DEPENDENT` | Tendencia previa alcista. Misma geometría que `INVERTED_HAMMER` (sección 6). | No. |
| `BULLISH_PIN_BAR` | Pin bar alcista | Cuerpo pequeño cerca del extremo superior; mecha inferior de rechazo, larga. Puede coincidir con `HAMMER` o con `DRAGONFLY_DOJI` (sección 6). | `CONTEXT_DEPENDENT` | Tendencia previa bajista. | No. |
| `BEARISH_PIN_BAR` | Pin bar bajista | Cuerpo pequeño cerca del extremo inferior; mecha superior de rechazo, larga. Puede coincidir con `SHOOTING_STAR` o con `GRAVESTONE_DOJI` (sección 6). | `CONTEXT_DEPENDENT` | Tendencia previa alcista. | No. |

### 5.2 Dos velas

| Identificador | Nombre | Geometría | Sesgo | Contexto requerido | Confirmación |
| -------------- | ------ | --------- | ----- | ------------------- | ------------- |
| `BULLISH_ENGULFING` | Envolvente alcista | Vela 1 bajista; vela 2 alcista cuyo **cuerpo** cubre por completo el cuerpo de la vela 1 (abre igual o más abajo que el cierre de la 1, cierra igual o más arriba que su apertura). | `BULLISH` | Tendencia previa bajista, para leerse como reversión. | No. |
| `BEARISH_ENGULFING` | Envolvente bajista | Espejo de `BULLISH_ENGULFING`. | `BEARISH` | Tendencia previa alcista. | No. |
| `BULLISH_HARAMI` | Harami alcista | Vela 1 bajista, de cuerpo amplio; vela 2 alcista, de cuerpo pequeño, contenido dentro del cuerpo de la vela 1. | `CONTEXT_DEPENDENT` | Tendencia previa bajista. | No (ver `THREE_INSIDE_UP`, que añade una tercera vela de confirmación como patrón propio). |
| `BEARISH_HARAMI` | Harami bajista | Espejo de `BULLISH_HARAMI`. | `CONTEXT_DEPENDENT` | Tendencia previa alcista. | No (ver `THREE_INSIDE_DOWN`). |
| `TWEEZER_BOTTOM` | Pinza de suelo | Dos velas consecutivas cuyos **mínimos** son prácticamente iguales (dentro de tolerancia). | `CONTEXT_DEPENDENT` | Tendencia previa bajista, como posible soporte. | No. |
| `TWEEZER_TOP` | Pinza de techo | Dos velas consecutivas cuyos **máximos** son prácticamente iguales. | `CONTEXT_DEPENDENT` | Tendencia previa alcista, como posible resistencia. | No. |
| `PIERCING_PATTERN` | Línea penetrante | Vela 1 bajista; vela 2 alcista que abre por debajo del mínimo (o del cierre) de la vela 1 y cierra por encima de la mitad del cuerpo de la vela 1, sin llegar a cubrirlo por completo (si lo cubriera, es `BULLISH_ENGULFING`). | `BULLISH` | Tendencia previa bajista. | No. |
| `DARK_CLOUD_COVER` | Nube negra | Espejo de `PIERCING_PATTERN`. | `BEARISH` | Tendencia previa alcista. | No. |

### 5.3 Tres velas

| Identificador | Nombre | Geometría | Sesgo | Contexto requerido | Confirmación |
| -------------- | ------ | --------- | ----- | ------------------- | ------------- |
| `MORNING_STAR` | Estrella de la mañana | Vela 1 bajista de cuerpo amplio; vela 2 de cuerpo pequeño (o doji) que abre más abajo (hueco según la política de gaps, sección 2); vela 3 alcista que cierra dentro del cuerpo de la vela 1, o más allá. | `BULLISH` | Tendencia previa bajista. | Sí: la propia vela 3 es la confirmación. |
| `EVENING_STAR` | Estrella vespertina | Espejo de `MORNING_STAR`. | `BEARISH` | Tendencia previa alcista. | Sí: la vela 3. |
| `THREE_WHITE_SOLDIERS` | Tres soldados blancos | Tres velas alcistas consecutivas, cada cierre más alto que el anterior, cada apertura dentro del cuerpo de la vela previa, mechas superiores pequeñas. | `BULLISH` | Ninguno estricto; más significativo tras una bajada o una consolidación (evidencia, no requisito). | Sí: la tercera vela. |
| `THREE_BLACK_CROWS` | Tres cuervos negros | Espejo de `THREE_WHITE_SOLDIERS`. | `BEARISH` | Igual que arriba, al revés. | Sí: la tercera vela. |
| `THREE_INSIDE_UP` | Tres dentro, arriba | Un `BULLISH_HARAMI` (velas 1 y 2) seguido de una vela 3 que cierra por encima del máximo de la vela 1. | `BULLISH` | Tendencia previa bajista (heredado del harami). | Sí: la vela 3. |
| `THREE_INSIDE_DOWN` | Tres dentro, abajo | Un `BEARISH_HARAMI` seguido de una vela 3 que cierra por debajo del mínimo de la vela 1. | `BEARISH` | Tendencia previa alcista. | Sí: la vela 3. |

## 6. Geometrías compartidas: la misma forma, dos nombres, nunca doble conteo

Varios pares del catálogo son **geométricamente idénticos**; los distingue solo el contexto en el
que aparecen. Esto es una decisión de catálogo, no un accidente:

- **`HAMMER` / `HANGING_MAN`**: la misma vela, tras una bajada es `HAMMER` (posible rechazo alcista),
  tras una subida es `HANGING_MAN` (posible debilidad). Sin contexto (tendencia `RANGE`/`TRANSITION`
  o datos insuficientes), la geometría existe (`MORPHOLOGICALLY_VALID`) pero **no se declara
  ninguno de los dos nombres**: declarar uno sin contexto sería inventar una lectura.
- **`INVERTED_HAMMER` / `SHOOTING_STAR`**: mismo caso, con la geometría invertida.
- **Pin bar y martillo/estrella/doji**: `BULLISH_PIN_BAR` puede coincidir exactamente con un
  `HAMMER` o con un `DRAGONFLY_DOJI` cuando la mecha es extrema y el cuerpo casi nulo. **No se
  cuentan como evidencias independientes**: cuando una misma vela cumple la geometría de más de un
  identificador de esta tabla, el detector declara **todos** los que cumple (cada uno con su propio
  registro, porque cada uno es una afirmación geométrica distinta y verificable), pero
  POINT4-HYPOTHESIS-001 los trata como **una sola pieza de evidencia agrupada**, nunca como
  confirmaciones independientes que se refuercen entre sí por coincidencia geométrica. Repetido de
  la propia tarea: «pin bar, martillo y shooting star solapados no se cuentan como tres
  confirmaciones independientes».
- **`BULLISH_HARAMI`+vela3 y `THREE_INSIDE_UP`**: `THREE_INSIDE_UP` no es un patrón nuevo desde
  cero: es un `BULLISH_HARAMI` confirmado. El detector de `THREE_INSIDE_UP` (POINT4-MULTI-001)
  reconoce el harami subyacente; no se declaran ambos como si fueran hallazgos independientes sobre
  las mismas dos primeras velas — el harami existe por sí solo mientras solo hay dos velas, y pasa a
  ser (o a coexistir con, según decida MODEL-001) el patrón de tres velas cuando la tercera cierra.
  Cuál de las dos formas exactas se implementa es una decisión técnica de POINT4-MODEL-001, no de
  este documento: aquí solo se fija que **no se cuenta el mismo hecho geométrico dos veces** como si
  fueran dos piezas de evidencia independientes.

## 7. Patrones y productos

Como en el contrato de figuras (`figuras-chartistas.md`, sección 6), la orientación no significa lo
mismo en cada producto: un patrón `BEARISH` en `CRYPTO × SPOT` significa abstenerse o salir, no
vender en corto; en una binaria, una afirmación sobre el precio al vencimiento. El patrón conserva su
sesgo tradicional y no decide qué se hace con él.

## 8. Lo que no se define aquí

Este contrato **no define**: proporciones exactas de cuerpo, mecha y rango, ni tolerancias de
igualdad (mínimos de `TWEEZER_*`, cuerpos de `HARAMI`); cómo se representa una instancia concreta ni
su ciclo de vida exacto entre estados (POINT4-MODEL-001); cómo el contexto decide `CONTEXT_VALID`
(POINT4-CONTEXT-001); cómo se combina con otra evidencia en una hipótesis (POINT4-HYPOTHESIS-001);
qué política de gaps aplica a cada mercado y producto en concreto (POINT4-MULTI-001); indicadores
(punto 5); objetivos, entradas, vencimientos, `stop-loss` ni `take-profit` (puntos 8, 10, 11+);
ejecución. Nada de esto se supone por lo escrito arriba.

## 9. Patrones de vela y figuras chartistas: contratos separados

Un patrón de vela y una figura chartista (`figuras-chartistas.md`) **son evidencias distintas que
pueden coexistir** sobre las mismas velas — una `SHOOTING_STAR` puede aparecer justo en la resistencia
de un `RECTANGLE`, y ambas se registran por separado, sin que una dependa de la otra ni una
sustituya a la otra. Ningún patrón de vela se redefine como figura chartista ni viceversa; la
integración de ambas como evidencia conjunta de una hipótesis es del punto 6 (`StrategySpec`), no de
este documento ni del contrato de figuras.

## 10. Extensibilidad

El catálogo se amplía como **datos**, no como código que reescriba el contrato: un patrón nuevo
necesitaría su identificador, geometría, sesgo y contexto requerido definidos aquí, una versión del
catálogo y un detector propio. Ningún patrón se añade ni se retira sin cambiar la versión de este
contrato.

## 11. Criterios de aceptación de esta tarea

- [x] Existe una única definición vigente y sin contradicciones (secciones 1 a 7).
- [x] Figura chartista y patrón de vela quedan separados (sección 9).
- [x] La misma geometría no se cuenta varias veces mediante alias (sección 6).
- [x] Ningún patrón se presenta como garantía o probabilidad calibrada (sección 1).
- [x] No se modifica código en esta tarea documental.

## 12. Decisiones técnicas tomadas al redactar

Registradas aquí para que se puedan corregir; ninguna es de producto.

1. **23 patrones** (9 de una vela, 8 de dos, 6 de tres), tomados del catálogo ya anotado en
   POINT4-SINGLE-001/MULTI-001 al crear las tareas; este documento los consolida con geometría,
   sesgo y contexto explícitos, que antes no estaban escritos en un solo sitio.
2. **`traditional_bias` tiene cuatro valores**, uno más que el catálogo de figuras
   (`NONE`, solo para el doji simple): un patrón de vela puede no tener ninguna lectura, algo que
   ninguna de las veinte figuras chartistas necesitaba expresar.
3. **Los pares de geometría idéntica (`HAMMER`/`HANGING_MAN`, `INVERTED_HAMMER`/`SHOOTING_STAR`) no
   se declaran sin contexto**: mejor no nombrar ninguno de los dos que inventar cuál aplica.
4. **`THREE_INSIDE_UP`/`DOWN` se documentan como la confirmación de un harami**, no como patrones
   sin relación con `BULLISH_HARAMI`/`BEARISH_HARAMI`, para que MODEL-001 no los modele como
   independientes por accidente y así duplique evidencia.
5. **La política de gaps es configurable por mercado**, nunca fija, porque `CRYPTO × SPOT` no
   produce huecos reales y una regla bursátil clásica lo invalidaría todo por construcción.
6. **Los ocho estados los fija este documento, pero su mecánica (transiciones, contenido de cada
   evaluación) es de POINT4-MODEL-001**, replicando el reparto de `figuras-chartistas.md` /
   `instancia-de-figura.md`, con la diferencia de que aquí la propia tarea de dominio pidió incluir
   los estados (a diferencia del punto 3, donde el catálogo no los tocaba).
