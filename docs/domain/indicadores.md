# Contrato canónico de indicadores técnicos (v1)

- **Estado:** vigente. Es el único contrato de indicadores de Freyja 2.0.
- **Fecha:** 2026-09-29
- **Tarea:** POINT5-DOMAIN-001. Documentación vinculante: **no implementa código**, ni migraciones,
  ni API, ni interfaz, ni ninguna fórmula (mismo reparto que `patrones-de-vela.md` para el punto 4).
- **Depende de:** el cierre de POINT4-TEST-001 (ya completado, con la política de gap por mercado
  corregida), [estructura-de-precio.md](estructura-de-precio.md) (pivotes, para Fibonacci) y
  [fibonacci-retroceso.md](fibonacci-retroceso.md) (contrato ya vigente de la herramienta de
  localización, que este documento no redefine).
- **Lo desarrollan:** POINT5-DOMAIN-001 (este documento) → POINT5-REGISTRY-001 (registro
  extensible: `IndicatorDefinition`, `IndicatorVersion`, `IndicatorParameterSchema`,
  `IndicatorMarketCapability`, `StrategyIndicatorUsage`, `IndicatorObservation`) → POINT5-CORE-001
  (las siete fórmulas canónicas) → POINT5-DATA-001 (cuándo cada indicador es fiable, por mercado y
  fuente) → POINT5-POLICY-001 (uso desde `StrategySpec`) → POINT5-SNAPSHOT-001 (persistencia en el
  expediente `Signal`) → POINT5-TEST-001. POINT5-LEGACY-001 está **cancelada** (Jessica, 2026-09-24:
  Freyja 2.0 se reconstruye desde cero, sin auditar el proyecto anterior); no es un bloqueo.

## 1. Qué es (y qué no es) un indicador técnico

Un **indicador técnico** es un **cálculo reproducible sobre datos de mercado ya cerrados** que
resume, transforma o localiza algo sobre el precio (o el volumen, cuando existe) para que una
persona o una `StrategySpec` lo lean como **evidencia técnica adicional**.

- **No es una figura chartista ni un patrón de vela.** Ambos contratos (`figuras-chartistas.md`,
  `patrones-de-vela.md`) se construyen sobre la geometría de las velas y sus pivotes; un indicador
  se construye sobre una fórmula aplicada a una serie de valores (precios de cierre, rangos,
  volumen). Los tres son evidencias **independientes** que pueden coexistir sobre las mismas velas,
  igual que una figura y un patrón de vela ya coexisten (`patrones-de-vela.md`, sección 9): ningún
  indicador redefine una figura o un patrón como si fuera su propio resultado, ni viceversa.
- **No es una señal, una orden ni una decisión.** Que el RSI esté en 28 no dice «compra».
- **No es una probabilidad ni una ventaja estadística.** Un indicador aporta, como mucho, evidencia
  técnica con una función declarada (sección 3); combinarla en una hipótesis calibrada exige
  validación (CLAUDE.md §4), y esa validación no es parte de este contrato.
- **No decide su propia función.** La misma media móvil puede usarse como filtro de tendencia en una
  `StrategySpec` y como dato meramente informativo en otra: el indicador calcula un valor; quién lo
  usa y para qué lo declara la `StrategySpec` (POINT5-POLICY-001), no el indicador (mismo principio
  que `patrones-de-vela.md`, sección 2, aplicó a la función de un patrón).
- **No inventa datos.** Un indicador que no puede calcularse con lo que hay disponible (historia
  insuficiente, campo no soportado por la fuente, dato obsoleto) **no produce un valor**: produce un
  estado explícito que dice por qué (sección 5; los estados exactos son de POINT5-DATA-001).

## 2. Familias técnicas: OHLCV frente a lo que Freyja no soporta hoy

Freyja solo tiene, hoy, velas cerradas OHLCV (apertura, máximo, mínimo, cierre y, cuando la fuente
lo publica, volumen) — el mismo dato que ya usan los contratos de figuras y patrones de vela. Eso
fija una frontera dura sobre qué puede ser un indicador en Freyja 2.0:

- **Familia `OHLCV`**: cualquier indicador que se calcula enteramente a partir de esa serie (precio
  de cierre/máximo/mínimo/apertura, rango, volumen agregado por vela). Es la **única familia
  soportada** por el núcleo inicial (sección 3) y por esta versión del contrato.
- **`ORDER_FLOW`, `DOM` (profundidad de mercado), `FOOTPRINT` y conceptos de `SMC` (Smart Money
  Concepts) NO son indicadores OHLCV y no se modelan en este contrato.** Todos exigen datos que
  Freyja no tiene: operaciones individuales (*trades*) con su lado comprador/vendedor, o el libro de
  órdenes (*order book*) con su profundidad — ninguno de los adaptadores actuales (Binance, Kraken,
  Twelve Data; ADR 0002/0007/0009) sirve eso, solo velas agregadas. POINT5-DATA-001 ya lo anticipa
  explícitamente: «herramientas de order flow, DOM, footprint y delta quedan no soportadas sin datos
  de trades o libro adecuados».
- **No son una variante futura de la misma familia que «ya llegará».** Son una familia de datos
  distinta, con requisitos de fuente distintos. Si algún día Freyja incorpora un proveedor con datos
  de operaciones o de libro, necesitarían su **propio contrato** (una nueva versión de este
  documento, o uno nuevo que lo referencie) — nunca se cuelan como una opción más de un indicador
  OHLCV existente, ni un indicador OHLCV se etiqueta con una de estas familias «por aproximación».
  SMC en particular mezcla, según quién lo enseñe, liquidez, estructura y zonas de order flow de
  forma heterogénea y no siempre reproducible por fórmula: no se adopta como familia hasta que
  exista una definición operativa cerrada y los datos para calcularla.

## 3. Núcleo inicial y función estratégica

**Siete herramientas** (decisión de Jessica, 24-09-2026), todas de familia `OHLCV`:

| Indicador | Qué resume | Implementa |
| --------- | ---------- | ---------- |
| `EMA` | Media móvil exponencial del precio de cierre. | POINT5-CORE-001 |
| `RSI` | Momento (fuerza relativa) del precio de cierre. | POINT5-CORE-001 |
| `MACD` | Convergencia/divergencia de dos medias móviles. | POINT5-CORE-001 |
| `BOLLINGER_BANDS` | Volatilidad como banda alrededor de una media móvil. | POINT5-CORE-001 |
| `ATR` | Volatilidad como rango medio verdadero, sin dirección. | POINT5-CORE-001 |
| `VOLUME` | Actividad negociada por vela (sección 5: límites reales por mercado). | POINT5-CORE-001 |
| `FIBONACCI` | Niveles de retroceso de un impulso confirmado. | Ya contratado en [fibonacci-retroceso.md](fibonacci-retroceso.md); **no se redefine aquí**. |

`FIBONACCI` se clasifica como herramienta de **localización de precio** (decisión de Jessica,
2026-09-26, ya recogida en su propio contrato), no como oscilador ni como medida de volatilidad: por
eso su función admitida por defecto es `LOCATOR` (tabla siguiente), coherente con el resto.

### Funciones admitidas (declaradas por la `StrategySpec` que use el indicador, no por el indicador)

| Función | Significa |
| ------- | --------- |
| `LOCATOR` | Señala una zona de precio (Fibonacci es el caso canónico). |
| `CONTEXT` | Describe el estado general del mercado (p. ej. una EMA larga como filtro de tendencia). |
| `TRIGGER` | Su cruce o condición dispara la evaluación de una hipótesis. |
| `CONFIRMATION` | Refuerza una hipótesis que ya existe por otra evidencia. |
| `FILTER` | Descarta una hipótesis que, sin él, sería válida. |
| `INVALIDATION` | Su condición invalida una hipótesis o instancia ya declarada. |
| `RISK_INPUT` | Alimenta un cálculo de riesgo (p. ej. ATR para un stop), nunca una orden por sí solo. |
| `EXIT_INPUT` | Alimenta una condición de salida, nunca la ejecuta. |
| `SCORING_INPUT` | Aporta un valor a un puntaje agregado de una hipótesis, sin decidir por sí solo. |
| `INFORMATIONAL` | Se conserva como dato, sin peso en la decisión. |

Cada indicador **separa familia técnica** (sección 2: hoy siempre `OHLCV`) **y función
estratégica** (esta tabla): un mismo `IndicatorDefinition` no tiene una función fija — la función es
propiedad del uso que una `StrategySpec` declare (`StrategyIndicatorUsage`, POINT5-REGISTRY-001),
igual que un patrón de vela no decide su propia función dentro de una `StrategySpec`
(`patrones-de-vela.md`, sección 2). **Ningún indicador produce, por sí solo, una señal, una
probabilidad calibrada ni una orden** — es evidencia técnica con una función, nunca una decisión.

## 4. Solo velas cerradas; datos insuficientes nunca se inventan

1. **Solo se usan datos disponibles hasta la última vela cerrada.** Ningún indicador se calcula ni
   se actualiza con una vela en curso — mismo principio de cero *look-ahead* que rige patrones de
   vela y figuras chartistas (CLAUDE.md §6).
2. **Los datos insuficientes o no disponibles nunca se representan con ceros inventados.** Si un
   EMA de periodo 200 no tiene 200 velas cerradas detrás, o si una fuente no publica volumen para un
   instrumento, el resultado es un **estado explícito** que dice por qué (`INSUFFICIENT_HISTORY`,
   `FIELD_UNAVAILABLE`, etc. — el catálogo exacto de estados es de POINT5-DATA-001), nunca un `0`,
   un `null` silencioso ni el último valor repetido sin más contigüedad.
3. **Inicialización y warmup son parte del contrato de cada indicador**, no un detalle de
   implementación: qué serie de calentamiento necesita, cómo se siembra (p. ej. el primer valor de
   una EMA) y desde qué vela empieza a ser válido lo fija POINT5-REGISTRY-001/CORE-001 por
   indicador, versionado — este documento solo exige que exista y sea explícito para los siete.

## 5. Mercados y productos: la compatibilidad se declara, nunca se asume

Como en `patrones-de-vela.md` (sección 7) y en el contrato de figuras, un indicador no significa lo
mismo, ni está disponible igual, en cada mercado. Regla general: **ninguna capacidad de un indicador
se infiere por el nombre de un proveedor o de un mercado** — se declara explícitamente
(`IndicatorMarketCapability`, POINT5-REGISTRY-001; los estados reales de disponibilidad son de
POINT5-DATA-001). Los tres mercados que el catálogo de Freyja tiene hoy —`CRYPTO`, `FOREX` y
`METALS`— deben poder usar los siete indicadores del núcleo inicial sobre precio (`EMA`, `RSI`,
`MACD`, `BOLLINGER_BANDS`, `ATR`, `FIBONACCI`) sin ninguna diferencia de contrato: todos se calculan
sobre cierres/rangos, que existen igual en los tres.

**`VOLUME` es distinto, y es el límite conocido que este contrato deja registrado explícitamente:**

- `CRYPTO` (Binance, Kraken): el volumen que reportan es real, agregado por el propio venue —
  ligado a esa fuente y ese venue, nunca un "volumen del mercado" universal (dos fuentes de cripto
  para el mismo par pueden reportar volúmenes distintos, legítimamente).
- `FOREX` y `METALS` (Twelve Data): **no existe un volumen spot global real** — no hay una única
  bolsa central que lo agregue, a diferencia de una acción o un futuro listado. Lo que hoy llega de
  Twelve Data para estos instrumentos es un campo de volumen ausente o nulo, que el adaptador
  guarda como `Decimal("0")` **porque el contrato de velas exige un valor exacto, nunca porque haya
  ocurrido volumen cero** (`twelve_data_rest.py`, ADR 0009). **Ese `0` almacenado nunca debe leerse,
  mostrarse ni calcularse como "sin actividad": es la ausencia del dato, no una observación.**
  `VOLUME` para `FOREX`/`METALS` debe declararse `FIELD_UNAVAILABLE` (o el estado equivalente que
  fije POINT5-DATA-001) para estas fuentes, no `AVAILABLE` con un valor de cero.
- **Nunca se sustituye en silencio un volumen real por un proxy** (p. ej. número de actualizaciones
  de precio o de velas recibidas, a veces llamado *tick volume*). Un proxy así, si Freyja llega a
  ofrecerlo, es un **indicador distinto con su propio nombre** (p. ej. `TICK_VOLUME`, no `VOLUME`) —
  nunca el mismo `IndicatorDefinition` con dos significados según la fuente. Esta distinción de
  vocabulario es de este contrato; qué fuentes ofrecen cuál, con qué estado, es de POINT5-DATA-001.
- Un indicador (típicamente `VOLUME`, pero la regla es general) que use un venue de ejecución
  distinto del de análisis debe declarar ambos por separado: la fuente de análisis nunca se
  sustituye silenciosamente por la de ejecución, ni al revés (POINT5-DATA-001, «la fuente de
  ejecución puede ser diferente de la fuente de análisis»).

## 6. Extensibilidad

El catálogo de indicadores crece como **datos** (nuevas filas de `IndicatorDefinition`/
`IndicatorVersion`, POINT5-REGISTRY-001), nunca añadiendo una columna nueva al expediente `Signal`
por cada indicador nuevo (p. ej. nunca una columna `rsi_value` específica): añadir un indicador
futuro no debe exigir cambiar ese esquema. Una versión de un indicador, una vez publicada, es
inmutable — igual que una versión de parámetros de patrón de vela nunca cambia su propio significado
retroactivamente (`instancia-de-patron-de-vela.md`).

## 7. Indicador, estrategia, figura, patrón, hipótesis, señal y ejecución: siete conceptos distintos

Ampliación explícita de la distinción que `patrones-de-vela.md` (sección 1) ya hacía para patrones
de vela, ahora con indicadores en la lista (decisión vinculante original de esta tarea):

| Concepto | Qué es | Contrato |
| -------- | ------ | -------- |
| Indicador | Un cálculo reproducible sobre OHLCV, con una función declarada por quien lo usa. | Este documento. |
| Figura chartista | Geometría sobre pivotes confirmados a lo largo de muchas velas. | `figuras-chartistas.md`. |
| Patrón de vela | Geometría de una a tres velas concretas. | `patrones-de-vela.md`. |
| Estrategia (`StrategySpec`) | Declara qué evidencias usa, con qué función, y cómo se combinan. | Punto 6 (no contratado aún). |
| Hipótesis | Combinación de evidencia (figuras, patrones, indicadores) según una `StrategySpec`. | POINT4-HYPOTHESIS-001 (patrones); la de indicadores es POINT5-POLICY-001/SNAPSHOT-001. |
| Señal | Lo que una hipótesis produce cuando se declara. | No contratado en el punto 4 ni en el punto 5. |
| Ejecución | Actuar sobre una señal (orden real o demo). | Fuera de alcance de los puntos 4 y 5; REAL sigue suspendida (CLAUDE.md §4). |

Ninguno de los siete sustituye a otro. Un indicador nunca se redefine como figura, patrón, hipótesis
o señal, ni al revés.

## 8. Lo que este documento no decide

- **Fórmulas, parámetros exactos, semillas, redondeo y warmup** de los siete indicadores:
  POINT5-CORE-001 (con el esquema de parámetros de POINT5-REGISTRY-001).
- **Las entidades del registro** (`IndicatorDefinition`, `IndicatorVersion`,
  `IndicatorParameterSchema`, `IndicatorMarketCapability`, `StrategyIndicatorUsage`,
  `IndicatorObservation`) y su esquema exacto: POINT5-REGISTRY-001.
- **Los estados exactos de disponibilidad por mercado, producto y fuente**
  (`AVAILABLE`/`INSUFFICIENT_HISTORY`/`STALE_DATA`/`SOURCE_UNSUPPORTED`/`FIELD_UNAVAILABLE`/
  `QUALITY_FAILED`) y cuándo aplica cada uno: POINT5-DATA-001.
- **Cómo una `StrategySpec` combina indicadores** (con qué función, con qué peso) y **cómo se
  persiste una observación** en el expediente `Signal`: POINT5-POLICY-001 y POINT5-SNAPSHOT-001.
- **Migración o eliminación de cualquier cálculo anterior**: POINT5-CORE-001/CLEANUP-001 (y
  POINT5-LEGACY-001, cancelada: no se audita el proyecto anterior).
- **Validación fuera de muestra o afirmaciones de rentabilidad**: no es parte de ningún contrato del
  punto 5; ver PARAMS-VALIDATION-001 (no iniciada) y CLAUDE.md §4.
- **`StrategySpec` en sí misma**: punto 6, no contratado todavía.
- Nada de frontend.

## 9. Criterios de aceptación de esta tarea

- [x] Una única definición vigente de qué es (y qué no es) un indicador técnico, enlazada desde el
  roadmap.
- [x] Familia OHLCV separada explícitamente de order flow/DOM/footprint/SMC, con la razón (datos que
  Freyja no tiene) y sin dejarla como una variante futura de la misma familia.
- [x] Confirmado que ningún indicador produce por sí solo una señal, probabilidad o ejecución.
- [x] Compatibilidad con `CRYPTO`, `FOREX` y `METALS` explícita para los seis indicadores de precio;
  límite real de `VOLUME` en `FOREX`/`METALS` registrado, con la distinción `VOLUME`/`TICK_VOLUME`
  fijada como vocabulario.
- [x] Fórmulas, parámetros, inicialización, warmup y fuentes quedan versionables (delegado a
  POINT5-REGISTRY-001/CORE-001, sección 8) sin fijarlos aquí.
- [x] Diferencias entre mercados y productos documentadas (sección 5).
- [x] No se modifica código en esta tarea documental.
- [x] Dependencias para POINT5-REGISTRY-001, POINT5-CORE-001 y POINT5-DATA-001 explícitas (sección 8
  y el informe siguiente).

## 10. Decisiones técnicas tomadas al redactar

Registradas aquí para que se puedan corregir; ninguna es de producto.

1. **`FIBONACCI` no se re-especifica**: su contrato (`fibonacci-retroceso.md`) ya está aprobado y
   vigente; este documento solo lo clasifica dentro del vocabulario común del punto 5 (familia
   `OHLCV`, función `LOCATOR`) para que el catálogo de POINT5-REGISTRY-001 lo incluya sin
   contradicción.
2. **`SMC` se nombra explícitamente como excluida**, en vez de callarla, porque es el término que
   más fácilmente se cuela como «ampliación natural» de un indicador existente sin datos ni
   definición operativa reproducible que lo respalden.
3. **La distinción `VOLUME` / `TICK_VOLUME` como indicadores distintos** (no el mismo con dos
   significados) es nueva en este documento: ni la tarea original de Notion ni POINT5-DATA-001 la
   nombraban con ese vocabulario exacto, pero ambas ya apuntaban a la misma regla («nunca se
   sustituye silenciosamente volumen real por tick volume»). Se fija aquí como vocabulario para que
   POINT5-REGISTRY-001 no tenga que inventarlo ad hoc.
4. **No se propone una sub-familia interna dentro de `OHLCV`** (p. ej. "tendencia", "momento",
   "volatilidad") como vocabulario cerrado: es terminología estándar de análisis técnico, útil para
   presentar el catálogo (sección 3), pero fijar su taxonomía exacta como campo del registro es
   decisión de POINT5-REGISTRY-001 («familia» en su «Contrato de versión»), no de este documento.
5. **No se crea ningún módulo de dominio, enum ni test de guarda en código** para esta tarea (a
   diferencia de, p. ej., `GapPolicy` en POINT4-MULTI-001): igual que `patrones-de-vela.md` fue
   puramente documental para el punto 4 (sin un solo test propio), y POINT5-REGISTRY-001 es quien
   tiene, explícitamente, la responsabilidad de crear las entidades del registro — crear un enum o
   una guarda ahora duplicaría o adelantaría ese trabajo sin necesidad, y no hay hoy ningún código
   de order flow/DOM/footprint/SMC que una guarda pudiera detectar (sección 2): la guarda relevante
   («ningún indicador de estas familias sin su propio contrato») se añadirá junto con
   POINT5-REGISTRY-001, cuando exista código de dominio real que vigilar.

## 11. Informe: decisiones y dependencias para las siguientes tareas del punto 5

Para quien empiece **POINT5-REGISTRY-001**:
- Las seis entidades ya están nombradas en su propia tarea; este documento no las diseña, pero fija
  que `IndicatorMarketCapability` debe poder expresar, para `VOLUME`, un estado distinto de
  `AVAILABLE` en `FOREX`/`METALS` incluso cuando el dato almacenado sea `0` (sección 5) — el
  registro no puede asumir que "hay un valor numérico" implica "el dato es real".
- El catálogo debe admitir `TICK_VOLUME` como una definición separada de `VOLUME` si Freyja llega a
  ofrecerlo (sección 5), sin necesidad de tocar este contrato otra vez.

Para quien empiece **POINT5-CORE-001**:
- Los siete indicadores del núcleo inicial están fijados (sección 3); `FIBONACCI` ya tiene su propio
  contrato completo y no necesita una nueva "fórmula" aquí, solo integrarse en el mismo registro que
  los otros seis.
- Ningún indicador de precio (`EMA`/`RSI`/`MACD`/`BOLLINGER_BANDS`/`ATR`) tiene restricción de
  mercado en este contrato: los tres mercados actuales los admiten igual.

Para quien empiece **POINT5-DATA-001**:
- El límite de `VOLUME` en `FOREX`/`METALS` (sección 5) es el caso concreto, ya confirmado contra la
  fuente real (Twelve Data, ADR 0009), que sus estados de disponibilidad deben cubrir sin inventar
  un valor. `ORDER_FLOW`/`DOM`/`FOOTPRINT`/`SMC` no entran en su inventario de capacidades: no son
  indicadores de este contrato (sección 2), no "capacidades no soportadas" de uno que sí lo sea.

Para **POINT5-POLICY-001** y **POINT5-SNAPSHOT-001** (más adelante): la función de un indicador
(sección 3) vive en `StrategyIndicatorUsage`, nunca en `IndicatorDefinition`; una observación
persistida (`IndicatorObservation`/`Signal`) debe conservar de qué fuente, con qué estado de
disponibilidad y bajo qué versión se calculó, mismo principio de trazabilidad que ya rige
`Provenance` en `domain/market_data.py` (ADR 0002).
