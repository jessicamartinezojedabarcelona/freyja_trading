# ADR 0003 — Persistencia de velas: inmutabilidad, calidad y sincronización

- **Estado:** Accepted
- **Fecha:** 2026-09-24
- **Tarea:** MARKET-DATA-PERSISTENCE-001
- **Relacionado:** ADR 0002 (contrato de datos de mercado y adaptador REST)

## Contexto

El adaptador de Binance (ADR 0002) devuelve velas cerradas con calidad y
procedencia, pero no las conserva. Antes de mostrar mercado hace falta
guardarlas en PostgreSQL de forma que repetir una ingesta no cambie nada, que
una vela confirmada no pueda reescribirse en silencio y que la API pueda
distinguir «no hay datos nuevos» de «el proveedor está fallando».

Esta tarea se entrega en dos PRs: primero la capa de persistencia y
sincronización (este ADR); después el endpoint de lectura autenticado.

## Decisión

### 1. Las velas son datos comunes e inmutables

`freyja2_candles` no pertenece a ninguna cuenta: los datos de mercado son
comunes a todas las personas usuarias (CLAUDE.md §4).

- **Clave natural única** `(data_source_id, instrument_id, timeframe_id,
  open_time)`. No hay id sustituto: la misma vela no puede existir dos veces.
- **Una vela guardada nunca se reescribe.** Un disparador (`BEFORE UPDATE`) de la
  base de datos rechaza cualquier `UPDATE`, así que ni un *upsert* ni un fallo
  del código pueden alterarla. `DELETE` sigue permitido para una futura
  política de retención.
- La base también valida la vela: `close_time > open_time`, precios positivos,
  OHLC coherente, volumen no negativo y calidad distinta de `UNAVAILABLE`
  (un fallo no guarda velas).
- Precios y volumen en `NUMERIC(38,12)`: exactos, nunca `float`.
- `received_at` es cuándo Freyja recibió la vela por primera vez, con el reloj
  de Freyja y no el del proveedor; no se reescribe.

### 2. Una discrepancia se comunica, no se aplica

Si el proveedor informa después valores distintos para una vela ya guardada, la
vela **se conserva tal cual** y la sincronización lo señala con
`REVISED_CANDLE` (calidad `DEGRADED`). La resolución de revisiones (guardar
versiones, decidir cuál prevalece) pertenece a PLATFORM-DATA-DESIGN-001; hasta
entonces es visible y no destructiva.

### 3. Idempotencia

Insertar con `ON CONFLICT DO NOTHING` y comparar lo ya existente: cada vela
resulta *nueva*, *sin cambios* o *revisada*. Repetir una ingesta, o solapar
ventanas, deja las filas existentes idénticas (incluido `received_at`).

### 4. Estado de sincronización

`freyja2_market_data_sync_state` guarda, por serie, el resultado del último
intento: cuándo, con qué calidad, códigos de incidencia, último éxito y
fallos consecutivos. Es lo único que permite a la API decir «el proveedor está
fallando» en lugar de servir datos viejos como si fueran actuales. Un fallo
incrementa el contador y conserva `last_success_at`; un éxito (incluso
degradado) lo pone a cero.

### 5. Huecos y frescura se calculan al leer

No se guarda «esta serie tiene un hueco»: se calcula sobre lo que hay
almacenado, con la misma función determinista de dominio que evalúa el
adaptador (`assess_candles`), para que la lectura nunca dependa de una
etiqueta que pudo quedar obsoleta.

### 6. Sincronización y backfill

- `sync_candles`: una petición al proveedor; guarda las velas cerradas y
  registra el intento (también si falla). No hace `commit`: lo decide quien
  llama.
- `backfill_candles`: rellena `[start, end)` por páginas de hasta 1000 velas,
  de la más antigua a la más reciente. **Acotado**: rechaza de entrada una
  ventana de más de 10 000 velas. **Repetible**: `commit` por página; si una
  falla se detiene con `completed=False` y volver a lanzarlo continúa. Solo
  llega hasta la última vela ya cerrada.
- Antes de guardar se comprueba que la respuesta corresponde a lo pedido
  (fuente, instrumento, temporalidad y símbolo del proveedor según el mapeo del
  catálogo); si no, no se guarda nada y se aborta.

### 7. Datos de referencia

La migración 0013 da de alta la fuente `BINANCE` (tipo `EXCHANGE`) y sus cuatro
mapeos `ANALYSIS` (`BTC/USDT`→`BTCUSDT`, etc.), buscando cada instrumento por su
clave natural y **abortando si falta alguno**. Un test comprueba que coinciden
exactamente con la lista cerrada del adaptador.

### 8. Cómo se ejecuta: CLI, no endpoint

Se añade `freyja-sync-candles` (temporalidad por defecto **1m**, elegible con
`--timeframe`). No se expone un endpoint que dispare llamadas al proveedor: eso
permitiría a cualquier cuenta provocar tráfico externo. La ejecución
periódica (planificador) no existe todavía y es una decisión de infraestructura
y coste, pendiente de Jessica.

### 9. Temporalidad

La persistencia no fija temporalidades: guarda cualquiera que exista en el
catálogo y esté habilitada para el instrumento. La referencia de producto de
Jessica es poder elegir entre 5s, 10s, 15s, 20s, 30s, 1m, 2m, 5m, 10m, 15m, 30m,
1h, 4h, 1d, 7d y 1M, con **1 minuto como valor estándar**. Hoy el catálogo solo
tiene 1m, 5m, 15m, 1h y 4h; ampliarlo es otra tarea (nueva versión del
catálogo y, para los periodos de segundos y algunos intermedios, decidir si se
construyen a partir de velas de 1 s/1 m o de operaciones).

## Consecuencias

- Aplicar la migración a Neon **no** ocurre en el despliegue de Render (solo el
  workflow manual lo hace). Por eso el PR de esta capa no expone nada que
  consulte las tablas nuevas, y el endpoint de lectura no se fusiona hasta que
  la base de producción esté migrada.
- Sin planificador, en producción no habrá velas hasta que se ejecute la
  sincronización; la API deberá mostrarlo como «sin datos», nunca inventarlo.
- `downgrade` de la 0013 elimina las tablas y las velas que contengan.

## Fuera de alcance

Más proveedores, retención de años, Redis/Kafka, planificador, revisiones
versionadas, WebSocket, nuevas temporalidades, órdenes y REAL.
