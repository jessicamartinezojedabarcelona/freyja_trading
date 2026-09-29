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
| `interval` acepta exactamente `1min, 5min, 15min, 1h, 4h`. | Documentación oficial | Coincide con las cinco temporalidades del catálogo; tabla de traducción 1 a 1. |
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

## Límites conocidos

- **Cuota y ritmo del plan gratuito.** Bajos en comparación con Binance/Kraken; un pase de
  escáner con las 5 series × 5 temporalidades ya usa una fracción significativa del límite
  diario si se ejecuta con frecuencia. Vigilar en producción antes de bajar el intervalo del
  escáner por debajo de su valor por defecto.
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

## Puesta en producción (orden)

1. Jessica obtiene una clave del plan gratuito de Twelve Data.
2. Correr `FREYJA_LIVE_MARKET_DATA=1 FREYJA_TWELVE_DATA_API_KEY=... uv run pytest tests/integration/test_twelve_data_live.py -v`
   y confirmar lo que esta ADR marca como sin verificar.
3. Configurar `FREYJA_TWELVE_DATA_API_KEY` en las variables de entorno de Render (nunca en el
   repo).
4. Añadir `TWELVEDATA` a `FREYJA_CANDLE_SCANNER_SOURCES` en `render.yaml` (PR aparte) y
   desplegar. `Settings` se niega a arrancar si `TWELVEDATA` está en la lista sin una clave
   configurada — un error de despliegue explícito, nunca un arranque a medias.
5. Comprobar en los logs `candle_scanner_started ... sources=[...'TWELVEDATA']` y
   `candle_scan_finished`, y que las series de FOREX/METALS avanzan.

Hasta el paso 4, nada cambia en producción: el escáner desplegado sigue leyendo solo Binance y
Kraken (un test estático, `test_the_candle_scanner_reads_only_sources_the_backend_knows_how_to_build`,
lo fija).

## Fuera de alcance

- Mostrar FOREX/METALS en el explorador de Mercados (MARKET-DATA-TWELVEDATA-EXPLORER-001).
- Cualquier plan de pago de Twelve Data, mientras el gratuito baste (CLAUDE.md §4).
- Cobertura amplia de materias primas más allá de XAU/USD (decisión explícita de Jessica,
  2026-09-29): solo el mercado METALS mínimo para el oro.
