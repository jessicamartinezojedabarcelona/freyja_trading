# Registro canónico y extensible de indicadores (v1)

- **Estado:** vigente.
- **Fecha:** 2026-09-30
- **Tarea:** POINT5-REGISTRY-001.
- **Depende de:** [indicadores.md](indicadores.md) (POINT5-DOMAIN-001: qué es un indicador, familia
  `OHLCV`, las diez funciones, el límite de volumen en FOREX/METALS). No implementa código nuevo
  fuera de este registro; **no conecta con el runtime** (escáner, API) — es un límite explícito de
  esta tarea, no un olvido.
- **Lo usarán:** POINT5-CORE-001 (crea las `IndicatorVersion` reales de los siete indicadores del
  núcleo inicial), POINT5-DATA-001 (decide, en tiempo real, si una `IndicatorMarketCapability`
  declarada aquí está de verdad disponible para una serie concreta), POINT5-POLICY-001
  (`StrategyIndicatorUsage`) y POINT5-SNAPSHOT-001 (`IndicatorObservation` persistida en `Signal`).
- **Implementación:** `backend/src/freyja_backend/domain/indicator_registry.py`. Puro y sin E/S,
  como `candlestick_pattern.py`: sin base de datos, sin reloj, sin proveedor, sin ninguna fórmula.

## 1. Qué resuelve este registro

`indicadores.md` fijó qué es un indicador y qué no. Este documento fija **la forma exacta** de las
seis entidades que permiten que el catálogo crezca sin tocar el esquema de `Signal`
(`indicadores.md`, sección 6) y sin mezclar familias de datos (sección 2). Ninguna fórmula, ningún
umbral, ningún estado de disponibilidad en tiempo real: eso es de POINT5-CORE-001 y POINT5-DATA-001.

## 2. Las seis entidades

### 2.1 `IndicatorDefinition`

Identidad canónica de un indicador — nunca su fórmula.

| Campo | Significa |
| ----- | --------- |
| `name` | Nombre canónico (`IndicatorName`: `EMA`, `RSI`, `MACD`, `BOLLINGER_BANDS`, `ATR`, `VOLUME`, `TICK_VOLUME`, `FIBONACCI`). |
| `family` | Siempre `OHLCV` en esta versión (`indicadores.md`, sección 2). Un enum de un solo valor hoy, deliberado: una segunda familia (`ORDER_FLOW`, `DOM`...) exige su propio contrato antes de añadirse aquí, nunca se cuela por extensión silenciosa. |
| `description` | Una frase, para quien lea el catálogo sin ir a `indicadores.md`. |

`VOLUME` y `TICK_VOLUME` son **entradas separadas del catálogo**, nunca una sola con dos
significados (`indicadores.md`, sección 5). `FIBONACCI` está en el catálogo para que
`StrategyIndicatorUsage` pueda referenciarlo con el mismo vocabulario que los demás, pero su
contrato completo sigue siendo [fibonacci-retroceso.md](fibonacci-retroceso.md); este registro no
lo redefine.

### 2.2 `IndicatorParameterSchema` / `ParameterConstraint`

Qué parámetros necesita una versión, genérico a propósito: un periodo (`INTEGER`), una desviación
(`DECIMAL`), un tipo de suavizado (`ENUM`) caben en la misma forma, así que un indicador nuevo con
parámetros distintos nunca exige una columna nueva.

| Campo (`ParameterConstraint`) | Significa |
| ------------------------------ | --------- |
| `name` | Nombre del parámetro (p. ej. `period`). |
| `type` | `INTEGER`, `DECIMAL`, `BOOLEAN` o `ENUM`. |
| `minimum`/`maximum` | Límites, cuando aplican (nunca para `ENUM`/`BOOLEAN`). |
| `allowed_values` | Solo para `ENUM`: los valores válidos. |

`IndicatorParameterSchema` agrupa una tupla de `ParameterConstraint` bajo su propia versión (nombres
de parámetro únicos dentro del esquema).

### 2.3 `IndicatorVersion`

Una forma concreta, inmutable, de calcular un indicador. Corresponde exactamente al «Contrato de
versión» que POINT5-REGISTRY-001 pedía fijar:

| Campo | Significa |
| ----- | --------- |
| `indicator` | A qué `IndicatorName` del catálogo pertenece. |
| `version` | Cadena de versión; nunca vacía, nunca reutilizada tras publicarse (sección 3). |
| `parameter_schema` | El `IndicatorParameterSchema` de esta versión. |
| `inputs` / `outputs` | Qué series lee (p. ej. `close`) y qué produce (p. ej. `value`, o `upper`/`middle`/`lower` para Bollinger) — al menos un output. |
| `initialization` | `SEEDED_FROM_FIRST_VALUE`, `REQUIRES_FULL_WARMUP_WINDOW` o `NONE` (p. ej. Fibonacci, función pura de un impulso ya confirmado, sin calentamiento). |
| `warmup_candles` | Cuántas velas cerradas necesita antes de producir su primer valor real. |
| `precision` | Decimales exactos de redondeo (CLAUDE.md §6: nunca coma flotante). |
| `incomplete_data_policy` | Hoy un único valor, `FAIL_CLOSED_NO_VALUE` (`indicadores.md`, sección 4: nunca un cero inventado). |
| `status` | `ACTIVE` o `DEPRECATED`. |

POINT5-CORE-001 crea las `IndicatorVersion` reales de los siete indicadores del núcleo inicial; este
registro no inventa ninguna fórmula ni ningún umbral por su cuenta.

### 2.4 `IndicatorMarketCapability`

Declara que una `IndicatorVersion` es, **en principio**, aplicable a un mercado y producto — nunca
se infiere del nombre de un proveedor (`indicadores.md`, sección 5).

| Campo | Significa |
| ----- | --------- |
| `indicator` / `indicator_version` | A qué versión se refiere. |
| `market` / `product` | El par de catálogo (p. ej. `FOREX`/`SPOT`). |
| `supported` | `True`/`False`. |
| `reason` | Obligatoria cuando `supported=False` (p. ej. «no existe un volumen spot global real»); vacía cuando `supported=True`. |

Esta declaración es **estructural** («¿tiene sentido este indicador aquí?»), no de disponibilidad en
vivo: si una fuente concreta está caída, obsoleta o sin ese campo ahora mismo es de
POINT5-DATA-001 (`AVAILABLE`/`INSUFFICIENT_HISTORY`/`STALE_DATA`/`SOURCE_UNSUPPORTED`/
`FIELD_UNAVAILABLE`/`QUALITY_FAILED`), que se apoya en esta declaración sin sustituirla.

### 2.5 `StrategyIndicatorUsage`

Cómo una `StrategySpec` (punto 6, no contratada todavía) usaría una versión concreta.

| Campo | Significa |
| ----- | --------- |
| `strategy_id` | Referencia opaca; no se asume ninguna forma de `StrategySpec`. |
| `indicator` / `indicator_version` | Qué versión usa. |
| `function` | Una de las diez de `indicadores.md` sección 3 (`LOCATOR`, `CONTEXT`, `TRIGGER`, `CONFIRMATION`, `FILTER`, `INVALIDATION`, `RISK_INPUT`, `EXIT_INPUT`, `SCORING_INPUT`, `INFORMATIONAL`). |

La función es propiedad de **este uso**, nunca del indicador ni de `IndicatorVersion`: la misma
versión de una EMA puede ser `CONTEXT` en una estrategia e `INFORMATIONAL` en otra.

### 2.6 `IndicatorObservation`

Un valor calculado, para una serie, en un instante — misma disciplina de trazabilidad que
`Provenance` (`domain/market_data.py`, ADR 0002).

| Campo | Significa |
| ----- | --------- |
| `indicator` / `indicator_version` | Qué se calculó y con qué versión exacta. |
| `instrument_id` / `data_source` / `timeframe` | La serie exacta. |
| `observed_at` | Cuándo se calculó (UTC, obligatorio). |
| `as_of` | Cierre de la vela más reciente usada, o `None`. |
| `availability` | `AVAILABLE` o `UNAVAILABLE` (marcador; el catálogo exacto de motivos es de POINT5-DATA-001). |
| `values` | Mapa nombre→`Decimal` de cada output declarado por la versión; vacío si `UNAVAILABLE`, nunca vacío si `AVAILABLE`. |

Una observación `UNAVAILABLE` nunca lleva valores — ni siquiera un cero — coherente con
`indicadores.md`, sección 4.

## 3. Versionado e inmutabilidad

- **Una `IndicatorVersion` publicada nunca cambia de significado.** Corregir un umbral o una
  fórmula es una versión nueva, nunca una edición de la existente — mismo principio que
  `THREE_CANDLE_PARAMETER_VERSION` en `candlestick_multi.py`.
- **`INDICATOR_CATALOGUE_VERSION`** (este módulo) sube solo si cambia la propia lista de
  `IndicatorDefinition` (añadir, quitar o renombrar un indicador del catálogo) — nunca por una
  `IndicatorVersion` nueva, que tiene su propia versión independiente.
- **No se crea un catálogo paralelo.** `INDICATOR_CATALOGUE` es la única fuente de nombres de
  indicador válidos; `IndicatorVersion.indicator` debe existir en él (verificado al construirse).

## 4. Límites de esta tarea

- **Ninguna columna específica por indicador en `Signal`.** `IndicatorObservation.values` es un
  mapa genérico; añadir un indicador nunca exige una migración de `Signal`.
- **Ningún indicador de familia distinta de `OHLCV`.** `IndicatorFamily` tiene un solo valor hoy a
  propósito (sección 2.1): `ORDER_FLOW`/`DOM`/`FOOTPRINT`/`SMC` seguirán sin existir aquí hasta que
  tengan su propio contrato (`indicadores.md`, sección 2).
- **Sin conexión a runtime.** Nada de este módulo se usa todavía desde el escáner, la API o
  cualquier `StrategySpec` real — es exactamente lo que la tarea pedía no hacer todavía.
- **Sin fórmulas.** Los siete indicadores del núcleo inicial están en `INDICATOR_CATALOGUE` por
  nombre y descripción; ninguno tiene todavía una `IndicatorVersion` real (eso es POINT5-CORE-001).

## 5. Criterios de aceptación

- [x] Añadir un indicador futuro es una fila nueva de `IndicatorDefinition`/`IndicatorVersion`, sin
  tocar el esquema de `Signal` (`IndicatorObservation.values` es genérico).
- [x] Una versión histórica es inmutable (sección 3; no hay ningún método que mute una
  `IndicatorVersion` ya construida — son `frozen`).
- [x] No se crea un catálogo paralelo sin plan de sustitución del legacy: no aplica (POINT5-LEGACY-001
  confirmó que no hay legacy relevante en este repo que sustituir).

## 6. Lo que este documento no decide

- **Las fórmulas, parámetros reales y umbrales** de los siete indicadores del núcleo inicial:
  POINT5-CORE-001.
- **Los estados reales de disponibilidad** por mercado, producto, fuente y frescura:
  POINT5-DATA-001 (esta tarea solo fija que toda `IndicatorMarketCapability` y toda
  `IndicatorObservation` cargan un marcador de soporte/disponibilidad explícito, nunca lo asumen).
- **`StrategySpec` en sí misma**: punto 6, no contratada. `StrategyIndicatorUsage.strategy_id` es
  deliberadamente una referencia opaca.
- **Cómo se persiste `IndicatorObservation` en el expediente `Signal`**: POINT5-SNAPSHOT-001.
- Nada de frontend, nada de backtesting, nada de ejecución.
