# ADR 0002 — Datos de mercado: contrato de adaptadores y primer adaptador REST público

- **Estado:** Accepted
- **Fecha:** 2026-09-24
- **Tarea:** MARKET-DATA-BINANCE-REST-001

## Contexto

Freyja necesita velas reales antes de poder mostrar mercado (MARKET-DATA-EXPLORER-001)
o calcular nada. MARKET-DATA-BINANCE-REST-001 exige que exista un contrato de
datos aprobado por PLATFORM-DATA-DESIGN-001, pero esa tarea sigue en *Backlog*
y abarca mucho más (WebSocket, backfill, reconexión, retención, reparación de
huecos).

Como Claude es arquitecta y desarrolladora del proyecto (CLAUDE.md §1), este
ADR fija **solo el contrato mínimo que necesita el adaptador REST**, para no
bloquear el trabajo ni improvisar. **No cierra PLATFORM-DATA-DESIGN-001**: todo
lo que este documento no cubre (ver «Fuera de alcance») sigue pendiente allí.

## Decisión

### 1. Contrato independiente del proveedor

`domain/market_data.py` define el vocabulario común: `InstrumentRef`,
`Timeframe`, `Candle`, `CandleBatch`, `MetadataResult`, `Provenance`,
`QualityIssue` y el puerto `CandleProvider`. No contiene tipos, nombres ni
formatos de ningún proveedor; un test lo vigila. Cada proveedor vive en
`infrastructure/` y traduce en su frontera.

### 2. Qué es una vela y cuándo se entrega

- Una vela cubre el intervalo semiabierto `[open_time, close_time)`.
- Todos los instantes son UTC con zona horaria explícita; los precios y el
  volumen son `Decimal`, nunca `float`.
- **Solo se entregan velas cerradas.** Una vela cuyo `close_time` aún no ha
  llegado está en curso, sus valores todavía cambian, y usarla como cerrada
  introduciría *look-ahead bias*. Se descarta y se informa
  (`OPEN_CANDLE_EXCLUDED`); nunca se devuelve.
- La temporalidad la elige quien consume el contrato, como parámetro. El
  catálogo v1 aprobado admite 1m, 5m, 15m, 1h y 4h; ampliarlo (por ejemplo
  con segundos) es una decisión de producto y requiere cambiar el catálogo,
  no solo el adaptador.

### 3. Calidad explícita, nunca silenciosa

Todo resultado lleva `DataQuality` (`OK`, `DEGRADED`, `UNAVAILABLE`), la lista de
`QualityIssue` que lo explica y su procedencia (fuente, endpoint, símbolo del
proveedor, instante de petición y de recepción, intentos).

| Situación | Resultado |
|---|---|
| Vela en curso descartada | `OK` (informativo) |
| Duplicado idéntico, fuera de orden, hueco, ventana incompleta, dato obsoleto, instrumento sin negociación | `DEGRADED`, se conservan las velas reales |
| 429 agotado, 418, timeout, red, 5xx agotado, 4xx, respuesta inválida, símbolo incoherente con el catálogo | `UNAVAILABLE`, **sin velas** |
| Duplicado con valores distintos, OHLC incoherente, fuera de la rejilla UTC, número no textual | `UNAVAILABLE` (`INVALID_RESPONSE`): no se «repara» |

Frescura: sin `start` ni `end`, la última vela cerrada no puede ser anterior a la
última que cerró hace más de 10 s (margen de publicación); si lo es, `STALE`.
Con ventana histórica se juzga la completitud frente a la ventana pedida.
Un dato antiguo nunca se presenta como actual.

### 4. Traducción de símbolos por lista cerrada

El adaptador solo procesa CRYPTO × SPOT con los pares del catálogo v1
(`BTC/USDT`, `ETH/USDT`, `SOL/USDT`, `XRP/USDT`), mediante una tabla inmutable
canónico → proveedor. Un test la contrasta con el seed del catálogo para que no
diverja. No se escriben filas en `freyja2_data_sources` ni en
`freyja2_data_source_instruments`: sembrarlas pertenece a
MARKET-DATA-PERSISTENCE-001.

### 5. Adaptador Binance Spot (REST público)

- Host `https://data-api.binance.vision` (endpoint oficial solo de datos de
  mercado), sin redirecciones. Endpoints permitidos, y nada más:
  `GET /api/v3/klines` y `GET /api/v3/exchangeInfo`.
- Timeout de 5 s. Reintentos acotados: 3 intentos, retroceso exponencial
  0,5 s → 4 s máx., sin *jitter* (determinista). Se respeta `Retry-After` en
  segundos; si supera 10 s no se espera y se devuelve `RATE_LIMITED`. 418
  (bloqueo de IP) no se reintenta; los 4xx tampoco.
- `httpx2` pasa de dependencia de desarrollo a dependencia de ejecución.

### 6. Sin credenciales **en esta tarea**

Leer velas públicas no requiere API key, y este adaptador no las maneja. Esto
no es una prohibición del proyecto: operar en un broker sí requerirá claves, y
llegará en tareas posteriores con su diseño de seguridad (CLAUDE.md §5: nunca
claves con permiso de retirada, nunca en el repositorio, ejecución REAL
suspendida hasta aprobación de Jessica). Cada adaptador de operativa será un
componente distinto con su propia autorización.

Guardas automáticas de esta tarea (`tests/unit/test_architecture_guards.py`):
`infrastructure/` solo admite los ficheros explícitamente autorizados; el
adaptador de datos públicos no puede contener claves, firmas, endpoints de
cuenta/órdenes/margen/futuros, WebSocket ni Testnet; y el dominio y las capas
internas no mencionan al proveedor.

### 7. Pruebas

Deterministas: transporte en proceso, reloj fijo y `sleep` inyectado, sin red
en CI. Una comprobación en vivo contra Binance existe pero es opt-in
(`FREYJA_LIVE_MARKET_DATA=1`), de modo que la CI no depende de un tercero.

## Consecuencias

- El contrato es reutilizable por un futuro adaptador Forex sin tocar el
  dominio.
- Un consumidor está obligado a mirar `quality`: no existe camino para leer
  velas sin conocer su calidad.
- Un despliegue en una región que Binance bloquee (HTTP 451) se verá como
  `UNAVAILABLE / PROVIDER_ERROR`, no como datos falsos.

## Fuera de alcance (sigue en PLATFORM-DATA-DESIGN-001 y tareas posteriores)

WebSocket, reconexión y estados de conexión; backfill y reparación controlada de
huecos; persistencia, revisiones y retención (MARKET-DATA-PERSISTENCE-001);
salud de fuentes agregada; segundos u otras temporalidades; credenciales,
Testnet, órdenes, balances, futuros, margen, Forex y ejecución REAL.
