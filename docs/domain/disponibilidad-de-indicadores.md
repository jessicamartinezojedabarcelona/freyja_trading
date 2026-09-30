# Disponibilidad de indicadores en tiempo real (v1)

- **Estado:** vigente.
- **Fecha:** 2026-09-30
- **Tarea:** POINT5-DATA-001.
- **Depende de:** [indicadores.md](indicadores.md) (POINT5-DOMAIN-001) y
  [registro-de-indicadores.md](registro-de-indicadores.md) (POINT5-REGISTRY-001: `IndicatorVersion`,
  `IndicatorMarketCapability`). El catálogo técnico del punto 1 (`freyja2_instruments`,
  `freyja2_data_source_instruments`) da los mercados/productos/fuentes reales sobre los que se
  evalúa esta disponibilidad, sin que este documento redefina ese catálogo.
- **Lo usará:** POINT5-CORE-001 (sabrá, para cada fórmula, exactamente cuándo puede calcularse y
  cuándo no) y, más adelante, POINT5-SNAPSHOT-001 (persiste el estado junto al valor en
  `IndicatorObservation`).
- **Implementación:** `backend/src/freyja_backend/domain/indicator_availability.py`. Puro y sin
  E/S: no consulta la base de datos ni ningún proveedor — recibe ya calculados el recuento de velas,
  la calidad de la serie y la capacidad declarada, y decide.

## 1. Qué resuelve

`IndicatorMarketCapability` (POINT5-REGISTRY-001) declara si un indicador **tiene sentido, en
principio**, para un mercado y producto. Este documento fija **el estado real, en el momento de
calcularlo**, cruzando esa declaración con la serie de velas concreta que hay disponible ahora
mismo — nunca al revés: una `IndicatorMarketCapability` con `supported=True` no garantiza
`AVAILABLE`; puede seguir estando `STALE_DATA` o `INSUFFICIENT_HISTORY` hoy.

**Ninguna capacidad se infiere por el nombre de un proveedor o mercado** (mismo principio que
`indicadores.md`, sección 5, y `registro-de-indicadores.md`, sección 2.4): todo lo que sigue actúa
sobre valores ya declarados (`IndicatorMarketCapability`, fuentes autorizadas, calidad de la serie),
nunca sobre una cadena `"FOREX"`/`"TWELVEDATA"` comparada a mano dentro de la lógica de decisión.

## 2. Los seis estados, y su prioridad exacta

Cuando aplica más de una condición a la vez, gana la primera de esta lista — de la causa más
estructural (no se puede saber nada) a la más benigna (solo falta tiempo):

| Orden | Estado | Cuándo | Motivo de la prioridad |
| ----- | ------ | ------ | ----------------------- |
| 1 | `SOURCE_UNSUPPORTED` | La fuente de datos no está entre las autorizadas para este indicador/instrumento. | Si la fuente ni siquiera es válida, nada más importa: no hay serie que evaluar. |
| 2 | `FIELD_UNAVAILABLE` | La `IndicatorMarketCapability` de esta versión para este mercado/producto declara `supported=False` (p. ej. `VOLUME` en `FOREX`/`METALS`). | La fuente es válida, pero el indicador nunca puede calcularse aquí — es una propiedad estructural del mercado, no de esta petición concreta. |
| 3 | `QUALITY_FAILED` | La serie de velas falló su propia validación (`DataQuality.UNAVAILABLE`: `RATE_LIMITED`, `TIMEOUT`, `PROVIDER_ERROR`, `INVALID_RESPONSE`, `SYMBOL_MISMATCH`, `NO_DATA` — `domain/market_data.py`) o está `DEGRADED` por una razón que no es solo frescura (hueco, duplicado, desorden, rango incompleto, vela revisada). | Hay un problema activo con los datos mismos, más allá de si ha pasado suficiente tiempo o si son antiguos. |
| 4 | `STALE_DATA` | La serie está `DEGRADED` únicamente por la razón `STALE` (`QualityIssueCode.STALE`). | Los datos existen y son válidos, solo antiguos — un caso más benigno que un fallo de calidad. |
| 5 | `INSUFFICIENT_HISTORY` | Menos velas cerradas que el `warmup_candles` que exige la `IndicatorVersion`. | El único requisito que se resuelve solo con que pase tiempo, sin que nada esté mal. |
| 6 | `AVAILABLE` | Ninguna de las anteriores. | — |

Un indicador **nunca produce un valor a medias**: exactamente uno de estos seis estados, siempre con
un motivo legible (`indicadores.md`, sección 4: los datos insuficientes nunca se representan con
ceros inventados).

## 3. Reglas por mercado y producto (lo que esta tarea debía cubrir explícitamente)

- **`CRYPTO` × `SPOT`**: volumen real, ligado al venue y proveedor (Binance, Kraken) —
  `IndicatorMarketCapability(VOLUME, ..., "CRYPTO", "SPOT", supported=True)`. Los seis indicadores
  de precio (`EMA`/`RSI`/`MACD`/`BOLLINGER_BANDS`/`ATR`/`FIBONACCI`) también soportados.
- **`FOREX` × `SPOT`** (Twelve Data): sin volumen spot global fiable —
  `IndicatorMarketCapability(VOLUME, ..., "FOREX", "SPOT", supported=False, reason=...)`, resultado
  `FIELD_UNAVAILABLE` para cualquier `IndicatorVersion` que declare `volume` entre sus `inputs`. Los
  indicadores solo-OHLC siguen soportados igual que en `CRYPTO`.
- **`METALS` × `SPOT`** (XAU/USD, Twelve Data): tratado como mercado propio, con la **misma
  cautela que `FOREX`** para volumen (`indicadores.md`, sección 5: XAU/USD es un mercado de tipo
  OTC con un patrón de sesión equivalente) — mismo resultado `FIELD_UNAVAILABLE` que `FOREX` para
  `VOLUME`, nunca heredado automáticamente de `FOREX` por similitud: es una declaración propia de
  `METALS`, para que un futuro mercado similar (que si acabara teniendo volumen fiable) no quede
  arrastrado por la misma regla sin revisarla.
- **Binarias (`BINARY_OPTION`)**: los indicadores se calculan **sobre el instrumento subyacente**,
  nunca sobre el `payout`; la disponibilidad se evalúa exactamente igual que para el `SPOT`
  correspondiente — el producto binario no es una fuente de datos de mercado distinta.
- **Indicadores solo-OHLC** (`EMA`, `RSI`, `MACD`, `BOLLINGER_BANDS`, `ATR`, `FIBONACCI`): su único
  campo requerido es el precio, disponible en los tres mercados — nunca dependen de `FIELD_UNAVAILABLE`
  por volumen.
- **Indicadores que requieren volumen** (`VOLUME`): dependen de la `IndicatorMarketCapability` de
  cada mercado; hoy solo `CRYPTO` la declara `supported=True`.
- **La fuente de ejecución puede ser distinta de la fuente de análisis** (`indicadores.md`, sección
  5): este módulo evalúa siempre la fuente de **análisis**, nunca sustituye una por otra en silencio.

## 4. Límites de esta tarea

- **Sin fórmulas.** Este módulo no calcula ningún indicador; decide si POINT5-CORE-001 podría
  hacerlo ahora mismo.
- **Sin `StrategySpec` ni señales.** Un estado de disponibilidad no es una recomendación operativa:
  `AVAILABLE` no dice "opera", `FIELD_UNAVAILABLE` no dice "evita este mercado" fuera del contexto
  técnico de ese indicador concreto.
- **Sin frontend.**
- **No sustituye `IndicatorMarketCapability`.** La declara `supported=False`; este módulo la lee,
  nunca la redefine ni la calcula por su cuenta.

## 5. Criterios de aceptación

- [x] Ninguna capacidad se infiere por tener un nombre de proveedor (sección 1).
- [x] No se sustituye silenciosamente volumen real por *tick volume*: `FIELD_UNAVAILABLE` para
  `VOLUME` en `FOREX`/`METALS` nunca se convierte en `AVAILABLE` usando otro campo por debajo.
- [x] Cada observación conserva fuente, venue, símbolo de proveedor y frescura: ya garantizado por
  `Provenance` (`domain/market_data.py`) e `IndicatorObservation` (POINT5-REGISTRY-001); este módulo
  añade el estado de disponibilidad sobre esa misma trazabilidad.
- [x] Fallo *fail-closed* cuando el requisito de datos no se cumple: los seis estados cubren
  exhaustivamente "no se puede calcular", nunca un valor con una advertencia adjunta.
