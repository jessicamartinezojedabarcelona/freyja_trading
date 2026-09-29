# ADR 0009 — Twelve Data como tercera fuente, para forex y metales

- **Estado:** Accepted (decisión de Jessica, 2026-09-29: conectar Twelve Data para forex y
  XAU/USD, empezando por el plan gratuito; diseño técnico de Claude)
- **Fecha:** 2026-09-29
- **Tarea:** MARKET-DATA-TWELVEDATA-REST-001 (sigue a MARKET-DATA-TWELVEDATA-CATALOG-001,
  migración 0016)
- **Relacionado:** ADR 0002 (contrato y adaptador REST), ADR 0003 (persistencia), ADR 0006
  (escáner en el backend), ADR 0007 (Kraken como segunda fuente; mismo patrón de adaptador)

## Contexto

Jessica pidió conectar Twelve Data para EUR/USD, GBP/USD, USD/JPY y XAU/USD. Se amplió a
USD/CHF (el cuarto par FOREX habitual) y, tras su decisión explícita del mismo día, XAU/USD
quedó en un mercado propio, **METALS**, no en FOREX (el oro no es un par de divisas). La
migración 0016 ya dio de alta ese catálogo en producción (5 instrumentos: EUR/USD ya existía
desde el catálogo v1; los otros 4 son nuevos). Esta decisión cubre el adaptador REST en sí.

A diferencia de Binance y Kraken, Twelve Data no es solo lectura pública anónima: exige una
clave de API. El plan gratuito, el único autorizado por ahora (CLAUDE.md §4: nada de pagar sin
necesidad y beneficio demostrados), tiene un límite bajo de peticiones.

## Hechos comprobados contra la documentación pública de Twelve Data (2026-09-29)

No se consultó con una clave real (Jessica todavía no la tiene); lo marcado como «sin
verificar» se confirmará con el test opcional `FREYJA_LIVE_MARKET_DATA=1` en cuanto haya una.

| Hecho | Fuente | Consecuencia en el diseño |
| ----- | ------ | -------------------------- |
| `GET /time_series` es el único endpoint necesario: da velas y, en `meta`, también el símbolo confirmado. | Documentación oficial | No hace falta un segundo endpoint para metadatos: `get_instrument_metadata` reutiliza `time_series` con `outputsize=1`. |
| `interval` acepta exactamente `1min, 5min, 15min, 1h, 4h`. | Documentación oficial | 1m/5m/15m/1h se traducen 1 a 1; **4h no se pide** (ver §7 — confirmado en producción que sus velas de 4h no encajan en la cuadrícula UTC de Freyja). |
| Los números llegan como texto (`"1.08423"`); `symbol` en la respuesta usa `BASE/QUOTE`. | Documentación oficial | `Decimal` exacto; el mismo esquema de traducción que Binance/Kraken. |
| `outputsize` máximo documentado: 5000. `start_date`/`end_date` permiten un backfill por rango, sin el horizonte fijo de Kraken. | Documentación oficial | `ProviderLimits(max_candles_per_request=5000)`, sin horizonte (`history_candles=None`), como Binance. |
| Autenticación por `apikey` en la URL o por cabecera `Authorization`. | Documentación oficial | Se usa **solo la cabecera** (CLAUDE.md §5: nunca en logs ni en la URL, que sí puede quedar en trazas/caches intermedios). |
| Plan gratuito: del orden de 800 peticiones/día y 8/minuto. | Documentación oficial (cifras del plan, no garantizadas) | Contador diario propio (ver Decisión §3) y espaciado mínimo entre peticiones. |
| **Sin verificar:** si la vela más reciente de `time_series` puede estar aún en curso; la forma exacta de un error (código HTTP real vs. `status: "error"` con HTTP 200); si `volume` viene relleno para forex/metales (sin bolsa central, es plausible que no). | — | Se asume el peor caso en los tres: `assess_candles` ya descarta cualquier vela con `close_time > now` sin necesitar tratamiento especial; el adaptador reconoce **ambas** formas de error (código HTTP y cuerpo 200 con `status: "error"`); `volume` ausente o nulo se trata como cero, nunca se inventa. |

## Decisión

### 1. Adaptador propio, con clave, de solo lectura de mercado

`infrastructure/market_data/twelve_data_rest.py`, con los mismos límites duros que Binance y
Kraken salvo el que le es propio: host `api.twelvedata.com` por HTTPS, sin redirecciones, una
sola ruta (`/time_series`), solo FOREX/METALS×SPOT y las cinco temporalidades del catálogo. La
guarda de arquitectura permite el nombre `api.twelvedata.com` únicamente dentro de este fichero
y prohíbe en él WebSocket y rutas de cuenta/órdenes — la diferencia respecto a Binance/Kraken es
que aquí "sin credenciales" no aplica: la clave es legítima y obligatoria, así que la guarda
comprueba en su lugar que nunca hay una clave real escrita en el código y que nunca se registra
en los logs (`_log_failure` no incluye la cabecera ni el cuerpo de la respuesta).

### 2. Un símbolo, dos mercados de catálogo

A diferencia de Binance y Kraken (un único mercado, CRYPTO×SPOT), Twelve Data sirve FOREX
(EUR/USD, GBP/USD, USD/JPY, USD/CHF) **y** METALS (XAU/USD) desde el mismo endpoint.
`_resolve_symbol` comprueba símbolo **y** mercado del catálogo (`SYMBOL_MARKETS`), no solo el
símbolo: pedir XAU/USD como FOREX o EUR/USD como METALS se rechaza igual que un símbolo
desconocido. Esto obligó a generalizar `candle_scanner_wiring._SOURCES`, que hasta ahora asumía
una única pareja mercado×producto fija por fuente (`CRYPTO`×`SPOT`); ahora cada fuente declara
sus propios `InstrumentRef`, lo que además deja el camino listo para una futura fuente con más
de dos mercados sin volver a tocar el cableado del escáner.

### 3. Cuota diaria: contador local, por proceso

El plan gratuito no admite consultarlo por API antes de gastarlo, así que el cliente lleva su
propio contador en memoria (`daily_quota`, 800 por defecto), que se reinicia por día natural UTC
(según el reloj inyectado, nunca `datetime.now()` directo). Si se agota, ninguna petición nueva
sale a la red: se reporta `RATE_LIMITED` igual que un 429 real. Limitación documentada y
aceptada: el contador **no sobrevive un reinicio del proceso** (Render Free duerme el servicio
tras inactividad); es la misma clase de límite ya aceptada para el escáner en el ADR 0006 y no
se considera bloqueante para el plan gratuito.

### 4. Espaciado entre peticiones y reintentos acotados

`min_request_interval_seconds` (8 s por defecto) mantiene un pase completo del escáner muy por
debajo del límite por minuto, con el mismo patrón de espera que Kraken. Los reintentos son el
mismo backoff exponencial acotado y determinista (inyectable `sleep`) que Binance y Kraken; un
error dentro de un HTTP 200 (código 429 o ≥500) se reintenta igual que uno con código HTTP real,
pero un rechazo (símbolo desconocido, clave inválida) no se reintenta nunca — insistir con la
misma petición mal formada no puede arreglarla y solo gastaría cuota.

### 5. Cada petición fuerza `timezone=UTC` y pide orden ascendente

Nunca se depende de un huso horario por defecto de la cuenta ni del orden por defecto de la
respuesta (`order=ASC` para velas; `assess_candles` ya tolera y detecta desorden si llegara a
haberlo). El volumen ausente o nulo (forex/metales sin bolsa central) se guarda como `Decimal("0")`,
nunca se omite la vela ni se inventa un valor.

### 6. Series separadas por fuente; el explorador no cambia por ahora

Sin cambios respecto al ADR 0006 §4 y al ADR 0007 §5: cada fuente guarda su propia serie con su
procedencia. Mercados aún no lista FOREX/METALS como mercados navegables — eso queda para
MARKET-DATA-TWELVEDATA-EXPLORER-001, tarea posterior y explícitamente fuera de alcance aquí.

### 7. 4h excluida para Twelve Data: su cuadrícula no es la de Freyja (TWELVEDATA-4H-GRID-001)

Confirmado en producción el 29-09-2026, con la clave real ya activa: cada intento de vela de 4h
de Twelve Data para los 5 instrumentos llegaba con un `open_time` fuera de la cuadrícula UTC
(00/04/08/12/16/20) que `assess_candles` exige — por ejemplo, `2026-07-08T13:00:00+00:00`. Todo
apunta a que Twelve Data ancla sus velas de 4h de forex/metales a la apertura de la sesión de
Nueva York, no a medianoche UTC; nunca va a encajar, en ningún instrumento de esta fuente.

`assess_candles` ya hacía exactamente lo que debía: descartar la vela y reportarla como
`INVALID_RESPONSE`, nunca guardarla torcida. El escáner repetía el mismo intento fallido en cada
pasada (`PROVIDER_UNAVAILABLE` en las 5 series de 4h, siempre), gastando cuota diaria en una
petición condenada a fallar.

Decisión: **excluir 4h específicamente en el adaptador de Twelve Data**
(`_INTERVALS`/`SUPPORTED_TIMEFRAMES` en `twelve_data_rest.py`), no en el validador compartido.
`_resolve_interval` rechaza `Timeframe.H4` antes de cualquier llamada de red, con un mensaje que
explica por qué; `candle_scanner_wiring._SOURCES` ahora lleva, junto al cliente y los
instrumentos de cada fuente, las temporalidades que de verdad sirve — Binance y Kraken siguen con
las cinco, Twelve Data con cuatro. El catálogo (migración 0016) sigue declarando que estos 5
instrumentos "admiten" 4h como concepto: es un hecho real del instrumento, no del proveedor, y
deja el camino abierto a que otra fuente sirva 4h real para alguno de ellos en el futuro sin
tocar nada más.

Alternativa descartada: soportar la cuadrícula/ancla propia de Twelve Data. No hay ningún
parámetro documentado para fijarla a UTC, y desplazar o renombrar la vela como si cubriera la
ventana UTC estándar sería falsear qué representa el dato — exactamente lo que CLAUDE.md §6
prohíbe. La única forma honesta de servir 4h real sería agregar 4 velas de 1h verificadas (esas sí
encajan en la cuadrícula) dentro del propio adaptador; queda anotada como posible tarea futura, no
autorizada todavía.

## Límites conocidos

- **Cuota y ritmo del plan gratuito.** Bajos en comparación con Binance/Kraken; un pase de
  escáner con las 5 series × 4 temporalidades (4h excluida, §7) ya usa una fracción
  significativa del límite diario si se ejecuta con frecuencia. Vigilar en producción antes de
  bajar el intervalo del escáner por debajo de su valor por defecto.
- **Sin velas de 4h para ningún instrumento de Twelve Data** (§7, TWELVEDATA-4H-GRID-001):
  confirmado, no un límite provisional. EUR/USD, GBP/USD, USD/JPY, USD/CHF y XAU/USD siguen sin
  4h mientras no se construya (como tarea aparte, no autorizada) un agregador propio a partir de
  velas de 1h.
- **Contador de cuota no persistente.** Se reinicia con cada arranque del proceso (ver
  Decisión §3); en el peor caso (reinicios frecuentes) el límite real de Twelve Data manda,
  no el contador local, que entonces solo sirve de primera línea de defensa.
- **Formas de error sin confirmar con una clave real** (ver tabla de hechos). El test opcional
  `tests/integration/test_twelve_data_live.py` (`FREYJA_LIVE_MARKET_DATA=1` +
  `FREYJA_TWELVE_DATA_API_KEY=...`) debe correrse a mano en cuanto Jessica tenga una clave, antes
  de activar esta fuente en producción.
- Sin la ventana fija de Kraken: los huecos por parada del proceso pueden rellenarse con
  `start_date`/`end_date`, igual que Binance, sujeto a la cuota diaria.
- Como Binance y Kraken, el escáner solo avanza mientras el proceso está despierto (ADR 0006).

## Puesta en producción

Completada el 29-09-2026: clave configurada en Render, `TWELVEDATA` activo en
`FREYJA_CANDLE_SCANNER_SOURCES` (#103), escáner desplegado sincronizando de verdad las 5 series
en 1m/5m/15m/1h (4h excluida a propósito, §7). Confirmado con datos reales en Mercados (precio de
EUR/USD y XAU/USD en vivo) y en los logs de Render (`candle_scan_finished`).

Sigue pendiente, sin bloquear lo anterior: correr
`FREYJA_LIVE_MARKET_DATA=1 FREYJA_TWELVE_DATA_API_KEY=... uv run pytest tests/integration/test_twelve_data_live.py -v`
para terminar de confirmar lo que esta ADR aún marca como sin verificar (forma exacta de un error,
si la vela más reciente puede estar en curso).

## Fuera de alcance

- Mostrar FOREX/METALS en el explorador de Mercados (MARKET-DATA-TWELVEDATA-EXPLORER-001).
- Cualquier plan de pago de Twelve Data, mientras el gratuito baste (CLAUDE.md §4).
- Cobertura amplia de materias primas más allá de XAU/USD (decisión explícita de Jessica,
  2026-09-29): solo el mercado METALS mínimo para el oro.
- Agregador propio de 4h a partir de velas de 1h para Twelve Data (§7): posible tarea futura,
  no autorizada todavía.
