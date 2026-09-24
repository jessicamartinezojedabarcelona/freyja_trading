# ADR 0006 — Escáner de velas dentro del backend

- **Estado:** Accepted (decisión de Jessica, 2026-09-25; diseño técnico de Claude)
- **Fecha:** 2026-09-25
- **Tarea:** MARKET-DATA-SCANNER-001
- **Sustituye a:** el planificador de GitHub Actions cada 5 minutos (workflow «Sync
  candles (scheduled)», PR #37, #38, #41).
- **Relacionado:** ADR 0003 (persistencia), ADR 0004 (tiempo real, propuesto).

## Contexto

Las velas guardadas en PostgreSQL debían mantenerse al día por un cron de GitHub Actions.
GitHub **nunca creó una ejecución `schedule`** para este repositorio: ni con `*/5`, ni con
minutos desplazados, ni con una lista explícita, ni con un workflow mínimo de prueba sin
entorno ni secretos, durante más de 5 horas, mientras `push`, `pull_request` y ejecución
manual funcionaban y GitHub no reportaba incidencias. Hay reportes públicos del mismo
síntoma en agosto y septiembre de 2026 sin solución conocida. Fuera de nuestro control.

Jessica decidió (2026-09-25) que el backend mantenga las velas él mismo y que el código
sirva también cuando se mude a una máquina virtual o un servidor de pago.

## Decisión

### 1. Un bucle en segundo plano que vive con la aplicación

- Se arranca en el `lifespan` de FastAPI y se detiene con él; no es un `create_task` suelto.
- La pasada es síncrona (SQLAlchemy y HTTP bloqueante), así que corre en un hilo
  (`asyncio.to_thread`) y no bloquea las peticiones.
- **Desactivado por defecto** (`FREYJA_CANDLE_SCANNER_ENABLED=false`): tests, CI y
  desarrollo local no lo arrancan solos. Si está activado y no puede construirse (base de
  datos mal configurada), **la aplicación no arranca**: mejor un fallo visible que datos que
  envejecen sin avisar.
- Si una pasada falla por un error inesperado, se registra con su traza y el bucle sigue
  tras una pausa creciente. Los problemas esperados (proveedor caído, base sin conexión) no
  son excepciones: se devuelven como resultado de cada serie.

### 2. Qué hace cada pasada, serie a serie

| Situación de la serie | Acción |
| --------------------- | ------ |
| Ya al día | **Ninguna petición.** |
| Vacía o con pocas velas de retraso (< 500) | Una petición de las últimas 500. |
| Muy atrasada (el servicio estuvo dormido) | Relleno hacia delante desde la última vela guardada, por páginas de 1000, con tope de 5000 velas por pasada; la siguiente pasada continúa. |

El relleno avanza desde lo guardado, no desde «ahora», para no dejar un agujero en medio del
histórico. Reutiliza `sync_candles`, así que hereda la inmutabilidad, la calidad y el
registro del estado de sincronización (el proveedor caído se ve en la API).

### 3. Varias instancias: bloqueo consultivo de transacción

Cada petición se guarda en su transacción tras `pg_try_advisory_xact_lock` de una clave
estable por serie. Un bloqueo de **transacción** (no de sesión) funciona detrás del *pooler*
de Neon en modo transacción, que rompe los de sesión. Si otra instancia tiene la serie, se
omite. Es eficiencia, no corrección: los inserts ya son idempotentes.

### 4. Cada fuente, su propia serie

Las velas de dos exchanges difieren, así que **no se mezclan en una serie ni se sustituye una
fuente por otra en silencio**. Cada fuente se sincroniza en su propia serie; quien consume
(el explorador, el contexto observable) elige de forma explícita y registrada la siguiente
fuente autorizada si la principal está obsoleta. La segunda fuente (Kraken) se añade en la
tarea MARKET-DATA-KRAKEN-REST-001 con un adaptador propio.

### 5. Sin CCXT por ahora

Se mantiene el puerto `CandleProvider` con un adaptador pequeño por exchange. El contrato de
Freyja exige velas **cerradas**, calidad y procedencia; CCXT devuelve la vela abierta, tiene
límites distintos por exchange y es una dependencia pesada. Se reevaluará si se necesitan
muchos exchanges.

### 6. TradingView no es una fuente

No existe una API gratuita y oficial de velas de TradingView. Lo disponible (scrapers y
librerías no oficiales) incumple sus términos de uso. `lightweight-charts` es solo la
librería de dibujo (ADR 0005).

## Límites conocidos

- **Solo avanza mientras el proceso está despierto.** Render Free lo duerme tras ~15 min sin
  tráfico; la primera pasada al despertar rellena lo que faltó. No sirve para decidir cada
  30 s: eso sigue requiriendo el worker con WebSocket en un servidor siempre activo (ADR 0004).
- **Neon Free** ofrece 100 CU-horas al mes y apaga el cómputo a los 5 minutos de inactividad.
  Una base consultada sin parar no se apaga y consume esa cuota; el intervalo es configurable.
- Solo Binance (spot, cripto) está conectado. El calendario de Forex y las fuentes de OTC
  llegarán con sus adaptadores.

## Retirada del mecanismo anterior

El workflow de GitHub pierde su `schedule` y pasa a llamarse «Sync candles (manual)»: queda
como respaldo que se lanza a mano (CLAUDE.md §11: no conviven dos mecanismos). Se elimina el
workflow temporal de sondeo usado para el diagnóstico.
