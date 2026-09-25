# ADR 0004 — Datos de mercado en tiempo real, temporalidades y explorador multi-fuente

- **Estado:** Proposed — el alojamiento está decidido (ver «Decisiones de Jessica»);
  siguen pendientes el universo inicial y los brokers.
- **Fecha:** 2026-09-24
- **Relacionado:** ADR 0002 (contrato y adaptador REST), ADR 0003 (persistencia),
  PLATFORM-DATA-DESIGN-001 (este ADR es su diseño de tiempo real).
- **Refinado por:** ADR 0008 (contratos de flujo, estados de conexión, huecos, revisiones, salud de
  fuentes y retención). Donde difieren, manda el 0008.

## Contexto

Requisitos dichos por Jessica el 2026-09-24:

- Freyja debe reaccionar con datos frescos **cada 30 segundos o menos** para saber
  qué operación abrir, con Binance u otras APIs de broker.
- Velas de **30 segundos o menores**; temporalidad elegible por quien usa Freyja,
  con **1 minuto por defecto**.
- **3 a 5 brokers** con distintos tipos de operativa (binarias, forex, cripto…) y
  muchos activos (Bitcoin, oro, EUR/USD y más).
- Freyja **muestra señales y hará auto-trading** (DEMO primero; REAL sigue
  suspendido, CLAUDE.md §4).

Lo construido hasta ahora (ADR 0002 y 0003) cubre el histórico desde 1 minuto vía
REST. El workflow programado de GitHub Actions (cada 5 minutos) es un parche para
mantener histórico: GitHub tiene un mínimo de 5 minutos, ejecuta en «mejor
esfuerzo» y retrasa u omite ejecuciones. **No puede** alimentar decisiones de
segundos, y Render Free suspende el servicio sin tráfico y no permite procesos en
segundo plano.

## Decisión propuesta

### 1. Empuje (WebSocket) y no sondeo cada 30 s

Consultar por REST cada 30 s desperdicia límites de peticiones, llega tarde
respecto al cierre real de la vela y no escala a varios instrumentos. Se ingiere
por **streams WebSocket** de cada proveedor, con un **proceso siempre activo**
(«worker de ingesta»). REST queda para histórico, huecos y reconexiones.

### 2. Evaluación dirigida por el cierre de vela

"Cada 30 s" significa «cuando cierra la vela de 30 s», no un temporizador. Al
cerrarse una vela `(fuente, instrumento, temporalidad)` se emite un evento y las
estrategias se evalúan de forma determinista sobre velas **cerradas** (sin
*look-ahead*, CLAUDE.md §6). La vela en curso se transmite marcada
`closed=false` para dibujarla, y **nunca** alimenta una señal ni una orden.

### 3. Worker de ingesta

- Proceso propio del mismo código base (misma BD, mismos contratos).
- **Un solo líder** activo (bloqueo consultivo de PostgreSQL); un segundo proceso
  espera. Necesario antes de cualquier auto-trading para no duplicar órdenes.
- Suscribe solo el **universo activo** (lo que hay en watchlists y estrategias),
  no todo el catálogo.
- Reconexión con espera acotada; al reconectar, **relleno por REST** del hueco.
  Estados de conexión y salud: ver ADR 0008 §3 y §7 (`freyja2_market_data_sync_state` queda como
  estado por serie del último intento).
- Sin Redis ni Kafka (CLAUDE.md §7): los cierres se publican con PostgreSQL
  `LISTEN/NOTIFY` (conexión directa, no la agrupada) y la API los retransmite al
  navegador por **Server-Sent Events**, más simples que un WebSocket propio y
  compatibles con la cookie de sesión.

### 4. Temporalidades

- **Bases**: `1s` y `1m` (nativas de Binance Spot). 5 s, 10 s, 15 s, 20 s y 30 s se
  **agregan desde 1 s** (todas dividen 60); 2 m y 10 m, desde 1 m; el resto
  (3 m, 5 m, 15 m, 30 m, 1 h, 4 h, 1 d, 1 w, 1 M…) es nativo cuando el proveedor lo
  ofrece.
- La agregación es una **función de dominio determinista** sobre la rejilla UTC:
  una vela agregada solo se emite si están **todos** sus hijos; si falta alguno, se
  marca incompleta y no se entrega como cerrada. Guarda su origen (`derived_from`).
- El catálogo v2 añade las temporalidades como **datos** (migración), respetando
  la guarda de integridad del seed v1. No se anuncia una temporalidad en la API
  hasta que exista ingesta que la respalde.

### 5. Almacenamiento por niveles

Medido en PostgreSQL 18: **245 bytes por vela** (tabla + índice).

| Serie (1 instrumento) | Velas/año | Tamaño/año |
|---|---|---|
| 1 minuto | 525 600 | ≈ 123 MB |
| 1 segundo | 31 536 000 | ≈ 7,4 GB |

Neon Free ofrece 0,5 GB **en total**. Por tanto: las velas **de segundos no se
persisten a largo plazo** (memoria o una ventana corta, p. ej. 48 h); 1 m se
conserva una ventana acotada (p. ej. 90 días) y las de 5 m o más, por más tiempo.
La retención se aplica borrando particiones antiguas. El tamaño del universo y los
plazos son decisión de producto/coste. **Ojo:** los plazos de este párrafo no caben en Neon
Free con las dos fuentes actuales; la retención vigente es la del ADR 0008 §11 (opción E, decidida por Jessica el 2026-09-25).

### 6. Varias fuentes y tipos de producto

- Una serie se identifica por `(fuente, instrumento, temporalidad)`. Una vela de
  Binance y una de un broker de forex **no son la misma serie** aunque el activo se
  parezca: cada broker cotiza distinto.
- El catálogo ya separa el propósito de cada fuente: `ANALYSIS` (sobre qué se
  calcula) y `SETTLEMENT` (con qué precio liquida el contrato). Para **binarias**,
  la señal puede calcularse sobre un activo subyacente, pero el resultado lo fija
  el precio de liquidación del broker: hay que **guardar también las velas de la
  fuente que liquida** y usar esa fuente para backtests y auto-trading. Con
  vencimientos de 30 s, una diferencia de cotización entre fuentes puede decidir el
  resultado.
- Cada proveedor implementa el puerto `CandleProvider` (REST) y un puerto de stream
  equivalente. Un broker sin API oficial estable **no se integra sin decisión
  expresa de Jessica**: las librerías no oficiales pueden incumplir los términos
  del broker y romperse sin aviso.

### 7. Explorador en Angular

- Ruta `/mercados/:instrumentId` con `?tf=1m&source=BINANCE` en la URL (enlazable);
  1 m por defecto.
- **Selector de instrumento** con búsqueda en servidor (hay miles), filtros por
  fuente, mercado y producto, y favoritos. **Selector de temporalidad** agrupado
  (segundos · minutos · horas · días o más); las no disponibles para la fuente se
  ven deshabilitadas con el motivo, tomándolo de `capabilities`.
- **Gráfico**: `lightweight-charts` de TradingView (Apache-2.0, unos 45 KB, velas y
  volumen, actualización de la última vela, marcadores para señales). Su licencia
  exige mostrar la atribución a TradingView. Los precios llegan como **texto
  decimal exacto**; se convierten a número solo en el borde de dibujo (la
  presentación puede usar `number`, ningún cálculo de trading se hace en el
  navegador).
- **Estado siempre visible**: fuente, hora UTC de la última vela y de su recepción,
  frescura (`FRESH`/`STALE`/`NO_DATA`), calidad y estado del proveedor; huecos
  marcados; un aviso destacado si la calidad no es `OK`. Sin datos = estado vacío,
  nunca un gráfico de ejemplo (UX-DESIGN-SYSTEM-001 §16); resumen textual como
  alternativa accesible.
- **Fases**: A) histórico ≥ 1 m con la API ya desplegada; B) vela en curso y cierres
  en directo por SSE cuando exista el worker; C) señales como marcadores y varios
  gráficos.

### 8. Fuera de alcance de este ADR

Motor de señales, ejecución de órdenes y credenciales de broker (tareas propias con
su diseño de seguridad); cualquier capacidad REAL, que sigue suspendida.

## Decisiones de Jessica

- **Alojamiento (2026-09-24): se mantiene Render Free** mientras Freyja «está en
  pañales» y no hay ingresos; el paso a un **VPS** se hará al acercarse al final.
  Consecuencia directa: el worker de tiempo real y las velas de segundos (fase B) se
  **aplazan hasta el VPS**. Entre tanto, el histórico se mantiene con el workflow
  programado de GitHub Actions y el explorador de fase A muestra honestamente el
  desfase de los datos («la última vela cerró hace…», `Desactualizado`).

## Decisiones que necesito de Jessica

1. ~~Alojamiento del worker~~ — decidido arriba (Render Free ahora, VPS después).
2. **Universo inicial** de instrumentos en directo (recomiendo ≤ 10 al empezar). Los plazos de
   retención ya están decididos: ADR 0008 §11.
3. **Brokers**: cuáles 3–5, y cuál va primero para forex y oro. Para cada uno
   compruebo si tiene API oficial antes de diseñar el adaptador.
4. **Base de datos**: Neon Free no basta cuando crezca el universo; habrá que
   prever un plan de pago o una retención más estricta.

## Consecuencias

- El histórico y el explorador de fase A no dependen de estas decisiones y pueden
  avanzar ya con datos reales.
- Sin worker, Freyja **no** puede operar con datos de segundos: se mostrará como
  no disponible, no como dato retrasado presentado como actual.
- Toda decisión de operar quedará ligada a la serie exacta (fuente, temporalidad y
  vela) que la produjo, para poder reproducirla y auditarla.
