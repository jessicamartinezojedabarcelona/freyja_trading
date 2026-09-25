# ADR 0007 — Kraken como segunda fuente de velas

- **Estado:** Accepted (decisión de Jessica, 2026-09-25: hacer la tarea completa; diseño técnico de Claude)
- **Fecha:** 2026-09-25
- **Tarea:** MARKET-DATA-KRAKEN-REST-001
- **Relacionado:** ADR 0002 (contrato y adaptador REST), ADR 0003 (persistencia), ADR 0006
  (escáner en el backend; §4 series por fuente, §5 sin CCXT).

## Contexto

El ADR 0006 fijó que cada fuente tiene su propia serie, que no se usa CCXT y que la segunda
fuente es Kraken con un adaptador propio. Esta decisión lo desarrolla. Kraken ya figuraba como
fuente de análisis de CRYPTO×SPOT en el contrato «Mercado» del Punto 1.

## Hechos comprobados contra la API pública de Kraken (2026-09-25)

Peticiones reales, solo lectura. Un test opcional (`FREYJA_LIVE_MARKET_DATA=1`) los vuelve a
comprobar contra la API real.

| Hecho | Consecuencia en el diseño |
| ----- | ------------------------- |
| `GET /0/public/OHLC` responde siempre con **las 720 velas cerradas más recientes más la que está en curso**, sin `limit` ni `end`. | El límite y la ventana se aplican en el cliente; la vela en curso se descarta. |
| Un `since` más antiguo que ese horizonte **devuelve igualmente las 720 últimas**, no las que se pidieron. | Se filtra por ventana en el cliente y lo que queda fuera del horizonte se declara hueco. |
| `since` incluye la vela que abre justo en ese instante. | Se envía `since = inicio − 1 s`: correcto sea inclusivo o exclusivo. |
| Los errores llegan con **HTTP 200** y una lista `error` no vacía, nunca como código de estado. | Se clasifican por texto (límite, servicio, rechazo) en lugar de por estado HTTP. |
| A partir de unas 9 peticiones seguidas responde `EGeneral:Too many requests`. | Separación mínima de 1 s entre peticiones (un pase completo, 20 series, queda muy por debajo) y reintento acotado. |
| Bitcoin se llama `XBT`: par `XBTUSDT`; los otros tres, `ETHUSDT`, `SOLUSDT`, `XRPUSDT`. | Tabla explícita y única de traducción; `XBT→BTC` solo en el adaptador. |
| Precios y volumen llegan como texto; el tiempo, en segundos enteros. | `Decimal` exacto; un número JSON se rechaza. |
| Horizonte por temporalidad: 1 m ≈ 12 h, 5 m ≈ 60 h, 15 m ≈ 7,5 días, 1 h = 30 días, 4 h = 120 días. | Ver «Límites conocidos». |

## Decisión

### 1. Adaptador propio, solo público y de solo lectura

`infrastructure/market_data/kraken_spot_rest.py`, con los mismos límites duros que el de Binance:
host `api.kraken.com` por HTTPS, sin redirecciones, lista cerrada de dos rutas (`OHLC` y
`AssetPairs`), sin credenciales, solo CRYPTO×SPOT y las cinco temporalidades del catálogo. La
guarda de arquitectura permite el nombre `api.kraken.com` **únicamente** dentro de este fichero
y prohíbe en él cualquier ruta privada, firma, `nonce`, WebSocket o futuros.

### 2. Cada proveedor declara lo que puede servir: `ProviderLimits`

El puerto `CandleProvider` incorpora `limits`: máximo de velas por petición y **horizonte**
(cuántas de las velas cerradas más recientes puede servir todavía, o ninguno). Binance: 1000 y
sin límite; Kraken: 720 y 720. El escáner y el backfill usan esos valores en lugar de un 1000
fijo. Cuando el servicio estuvo dormido más allá del horizonte de una fuente, el relleno
empieza en la vela más antigua que aún se puede pedir y **el resto queda como un hueco
declarado** (`GAP`, calidad degradada): nunca se inventan velas y nunca se rellenan con datos de
otra fuente.

### 3. Series separadas por fuente

Sin cambios respecto al ADR 0006 §4: BINANCE y KRAKEN guardan cada una lo suyo, con su
procedencia, aunque coincidan instrumento y periodo. Los tests lo comprueban de extremo a
extremo (mismo instrumento, mismo periodo, dos fuentes, sin mezcla y sin que una caída de una
afecte a la otra).

### 4. Migración 0014: solo datos

Da de alta la fuente `KRAKEN` y sus 4 mapeos de análisis. No cambia el esquema. Falla sin
adivinar si falta un instrumento del catálogo. Su `downgrade` **se niega** a ejecutarse mientras
existan velas o estado de sincronización de Kraken (no destruye datos guardados en silencio).
Como Render no aplica migraciones, se entrega el script equivalente para Neon
(`docs/operations/neon-0014-kraken-manual.sql`); un test comprueba que produce exactamente las
mismas filas, los mismos identificadores y la misma revisión que Alembic, y que Alembic puede
revertir lo que el script dejó.

### 5. El explorador no cambia

Mercados ya lista las fuentes activas de cada instrumento y abre en la primera. La API las
devuelve ordenadas por código, así que **BINANCE sigue siendo la fuente por defecto**; un test
fija ese orden. Kraken sin velas aún responde «sin datos», nunca un error ni datos de Binance.
Cambiar la fuente por defecto sería una decisión de producto explícita, no un efecto del orden
alfabético.

## Límites conocidos

- **Historia acotada por Kraken.** Solo se pueden pedir sus últimas 720 velas por temporalidad.
  Si el backend duerme más de ~12 h, la serie de 1 m de Kraken tendrá un hueco que no se puede
  recuperar por este endpoint (el de operaciones existe, pero queda fuera de alcance). Binance no
  tiene este límite.
- **Velas sin operaciones.** Kraken no emite una vela de un intervalo sin operaciones, así que
  puede haber huecos reales en pares poco líquidos; se muestran como huecos.
- **Límite de peticiones.** El umbral exacto no está documentado oficialmente en lo que se
  consultó; se aplica un margen amplio y se respetan los errores que devuelva.
- Como Binance, solo avanza mientras el proceso está despierto (ADR 0006).

## Puesta en producción (orden)

1. Aplicar `docs/operations/neon-0014-kraken-manual.sql` en Neon (Jessica).
2. Añadir `KRAKEN` a `FREYJA_CANDLE_SCANNER_SOURCES` en `render.yaml` (PR aparte) y desplegar.
3. Comprobar en los logs `candle_scanner_started ... sources=['BINANCE', 'KRAKEN']` y
   `candle_scan_finished`, y en Mercados que la serie de Kraken avanza.

Hasta el paso 2 nada cambia en producción: el escáner sigue leyendo solo Binance.
