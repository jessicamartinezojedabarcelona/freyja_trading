# ADR 0008 — Adquisición y continuidad de datos de mercado

- **Estado:** Accepted (diseño técnico de Claude, 2026-09-25). La sección 11 (retención) la
  decidió Jessica el mismo día, tras aclarar que las operaciones se cierran el mismo día.
- **Fecha:** 2026-09-25
- **Tarea:** PLATFORM-DATA-DESIGN-001 (solo diseño: no implementa código, migraciones ni API).
- **Relacionado:** ADR 0002 (contrato y adaptador REST), 0003 (persistencia), 0004 (tiempo
  real y explorador), 0006 (escáner), 0007 (Kraken).
- **Aplaza la implementación** de todo lo que necesita un proceso siempre activo hasta el VPS
  (decisión de Jessica, 2026-09-24: Render Free ahora).

## Contexto

Los ADR 0002 a 0007 ya fijaron el contrato mínimo REST, la persistencia inmutable, el escáner
dentro del backend y la segunda fuente, y el 0004 propuso a nivel de **principios** el empuje por
WebSocket, la evaluación por cierre de vela, el worker de líder único y el almacenamiento por
niveles. Lo que faltaba son los **contratos y las máquinas de estados** que permitan
implementarlo sin improvisar, y las políticas de continuidad: qué es un hueco reparable, qué
hace una revisión, cuándo una fuente está sana y qué se conserva.

Este ADR no repite lo ya decidido: lo **completa**. Donde afina algo del 0004 lo dice.

### Qué existe y qué falta

| Pieza | Estado antes de este ADR | Cubierto por |
| ----- | ------------------------ | ------------ |
| Contrato REST, velas cerradas, calidad y procedencia | Hecho | ADR 0002 |
| Persistencia inmutable, idempotencia, estado de sincronización | Hecho | ADR 0003 |
| Escáner REST, relleno de la cola, bloqueo por serie | Hecho | ADR 0006 |
| Enfriamiento ante límites de peticiones (REST) | Hecho | PR #56 |
| Contrato de flujo (WebSocket) y normalización de eventos | **Sin diseñar** | §2 |
| Estados y transiciones de conexión, reconexión | **Sin diseñar** | §3 |
| Duplicados, orden y cierre de vela por flujo | **Sin diseñar** | §4 |
| Reparación de huecos internos | **Sin diseñar** | §5 |
| Revisiones y su lectura | Solo se señalan | §6 |
| Salud de fuentes y modo degradado | Solo estado por serie | §7 |
| Publicación de cierres | Esbozado en 0004 | §8 |
| Retención | Propuesta en 0004, sin cuadrar | §11 |

## Hechos comprobados (documentación oficial, 2026-09-25)

Contrastados con la documentación de cada proveedor; hay que **volver a comprobarlos al
implementar** (los límites cambian).

| Proveedor | Hecho | Consecuencia |
| --------- | ----- | ------------ |
| Binance | Endpoint solo de datos de mercado `wss://data-stream.binance.vision`; el general es `wss://stream.binance.com`. | Se usa el de solo datos, coherente con el REST `data-api.binance.vision`. |
| Binance | Flujo `<símbolo>@kline_<intervalo>`, intervalos desde `1s`. El mensaje trae `x` (¿vela cerrada?), `E` (instante del evento), `t` y `T` (apertura y cierre). Actualiza cada 1000 ms (`1s`) o 2000 ms (resto). | Binance **declara** cuándo una vela está cerrada. |
| Binance | Una conexión dura como mucho **24 horas**; el servidor envía _ping_ cada **20 s** y desconecta si no recibe _pong_ en **1 minuto**; máximo **5 mensajes entrantes por segundo** y **1024 flujos** por conexión; **300 conexiones cada 5 minutos por IP**, y las IP con desconexiones repetidas pueden ser bloqueadas. | Rotación planificada antes de las 24 h, presupuesto propio de intentos de conexión y una sola conexión para todo el universo. |
| Kraken | WebSocket v2 en `ws.kraken.com/v2`, canal `ohlc`, intervalos en minutos (1, 5, 15, 30, 60, 240, 1440…). Las actualizaciones se generan **con cada operación**; hay instantánea inicial. **No hay marca de vela cerrada.** | Con Kraken **el flujo no cierra velas**: solo sirve para dibujar la vela en curso y para avisar de cuándo pedir la vela cerrada por REST (§4.3). |
| Kraken | Latido (`heartbeat`) aproximadamente cada segundo si no hay otras actualizaciones. El servidor cierra la conexión tras ~1 minuto de inactividad. Límite de conexiones y reconexiones por IP de unos **150 intentos cada 10 minutos**; superarlo supone un bloqueo de 10 minutos. Recomienda reintentar al momento unas pocas veces y, tras mantenimiento, no más de una vez cada 5 s. | Vigilancia de silencio corta para Kraken y presupuesto de reconexión propio. |

## Decisión

### 1. Un solo cauce, tres orígenes

Todo dato de mercado atraviesa el mismo cauce, sea cual sea su origen:

```
origen (REST actual · REST de histórico/reparación · flujo WebSocket)
   → adaptador del proveedor (traduce en su frontera)
   → normalización (§2) → validación de calidad → almacén inmutable (ADR 0003)
   → aviso de cierre (§8) → consumidores (contexto, señales, explorador)
```

- Ningún origen escribe por su cuenta: **todos** pasan por la misma inserción idempotente y las
  mismas comprobaciones. Un dato que llega por el flujo y el mismo por REST son la misma vela.
- **La verdad es siempre la base de datos.** Los avisos son pistas; un consumidor vuelve a
  leer la base y no se fía del contenido del aviso.
- **REST sigue siendo imprescindible**: histórico, huecos, reconexiones, verificación y los
  proveedores cuyo flujo no declara el cierre.
- **Una fuente, un mecanismo de límites**: el enfriamiento por límites de peticiones (PR #56)
  pasa a ser **compartido por REST y flujo de la misma fuente**, porque limitan por la misma IP.
  Una fuente suspendida no recibe ni peticiones ni intentos de conexión.

### 2. Contrato de flujo y normalización

Un puerto de dominio nuevo, `CandleStream`, independiente del proveedor como `CandleProvider`
(ADR 0002 §1). No expone sockets ni formatos del proveedor; entrega **eventos normalizados**:

| Evento | Contenido | Uso |
| ------ | --------- | --- |
| `CandleUpdate` | Serie (fuente, instrumento, temporalidad), `open_time`, OHLCV como `Decimal`, `closed` (booleano), `event_time` (del proveedor, UTC), `received_at` (de Freyja, UTC), identificador del proveedor si lo hay. | La vela en curso se dibuja; una vela con `closed=true` declarada por el proveedor se guarda. |
| `ConnectionEvent` | Nuevo estado de conexión (§3), motivo y su instante UTC. | Salud (§7) y registro. |
| `Heartbeat` | Instante de recepción. | Vigilancia de silencio. |

Reglas de normalización, idénticas a las del contrato REST y comprobadas en la frontera del
adaptador:

- Instantes en UTC con zona explícita; el `event_time` del proveedor **no se usa como reloj**
  de Freyja (`received_at` sale del reloj de Freyja, ADR 0003 §1).
- Precios y volumen solo desde texto exacto a `Decimal`; un número JSON se rechaza.
- Símbolos traducidos con la **tabla cerrada** de cada fuente; un símbolo que el catálogo no
  autoriza se descarta, se cuenta y se registra; nunca se guarda.
- Solo se suscribe el **universo activo** (0004 §3), en **una conexión** por fuente mientras
  quepa (Binance admite 1024 flujos).
- Una serie se identifica por (fuente, instrumento, temporalidad); las velas de dos fuentes
  **no se mezclan** (ADR 0006 §4).
- Los adaptadores de flujo van en ficheros propios, con su propia guarda de arquitectura: solo
  los hosts de datos públicos (`data-stream.binance.vision`, `ws.kraken.com`), solo canales de
  mercado, sin credenciales ni canales privados. Hoy las guardas prohíben WebSocket en los
  adaptadores REST (ADR 0002 §6; ADR 0007 §1): esa prohibición **se mantiene para esos
  ficheros** y la guarda nueva se añade al implementarlos.

### 3. Estados de conexión y transiciones

Cada conexión de flujo (una por fuente) es una máquina de estados **determinista**: mismas
entradas, mismas transiciones. Reloj y generador de números aleatorios (la variación de la
espera) son inyectables, para probarla sin red y sin esperas.

| Estado | Significa |
| ------ | --------- |
| `IDLE` | No hay universo que suscribir, o la fuente está desactivada. |
| `CONNECTING` | Abriendo la conexión. |
| `SUBSCRIBING` | Conectada; pidiendo los flujos y esperando su confirmación. |
| `RESYNCING` | Suscrita y recibiendo; **rellenando por REST** el tramo perdido (§5.1). |
| `LIVE` | Recibiendo y al día. Único estado en que el flujo cuenta como fuente sana. |
| `RECONNECTING` | Caída detectada; esperando antes de reintentar. |
| `SUSPENDED` | La fuente limita o bloquea: no se intenta nada hasta que acabe el enfriamiento compartido (§1). |
| `STOPPED` | Parada ordenada, o se perdió el liderazgo (0004 §3). |

| Desde | Evento | Hacia | Acción |
| ----- | ------ | ----- | ------ |
| `IDLE` | hay universo y se es líder | `CONNECTING` | Abrir la conexión. |
| `CONNECTING` | conectada | `SUBSCRIBING` | Enviar las suscripciones. |
| `CONNECTING` / `SUBSCRIBING` | fallo o tiempo agotado | `RECONNECTING` | Registrar el motivo. |
| `SUBSCRIBING` | todas las suscripciones confirmadas | `RESYNCING` | Fijar, por serie, la última vela guardada y rellenar hacia delante. |
| `RESYNCING` | tramo rellenado y primera verificación correcta | `LIVE` | Publicar `LIVE`. |
| `LIVE` / `RESYNCING` | silencio superior al umbral (§3.1) | `RECONNECTING` | Cerrar y reintentar. |
| `LIVE` / `RESYNCING` | desconexión | `RECONNECTING` | Registrar el motivo. |
| `LIVE` | **rotación planificada** (Binance, antes de 24 h) | `LIVE` | Abrir la conexión nueva, dejar que solapen (los duplicados los absorbe §4) y cerrar la vieja: **primero se abre, luego se cierra**. |
| cualquiera | señal de límite o bloqueo (429, 418, cierre por límite) | `SUSPENDED` | Abrir o prolongar el enfriamiento compartido (120, 240, 480, 960 y 1800 s como máximo, igual que en REST). |
| `SUSPENDED` | enfriamiento cumplido | `CONNECTING` | **Un solo intento** de sonda. |
| `RECONNECTING` | espera cumplida y presupuesto de intentos disponible | `CONNECTING` | Reintentar. |
| cualquiera | parada ordenada o pérdida de liderazgo | `STOPPED` | Cerrar limpiamente. |

**Espera entre intentos.** Hasta tres reintentos inmediatos ante una caída aislada; después,
exponencial de 1 s hasta 60 s con una variación de ±20 % (generador inyectado). Sobre eso rige
un **presupuesto propio de intentos por fuente**, muy por debajo del límite del proveedor
(≤ 10 por minuto; Binance admite 300 cada 5 minutos por IP y Kraken unos 150 cada 10): un fallo
en bucle no puede convertirse en un bloqueo de IP.

#### 3.1 Vigilancia de silencio

Umbrales por proveedor, **configuración versionada** (`stream-liveness-v1`, sin validar con
datos): Binance, 40 s (dos veces su _ping_ de 20 s); Kraken, 5 s (cinco latidos). Cualquier
trama vale como señal de vida. Superado el umbral, la conexión se da por muerta. Aparte,
**la frescura de cada serie** sigue juzgándose como hasta ahora (ADR 0002 §3): una conexión
viva no vuelve fresca una serie que no recibe velas.

### 4. Orden, duplicados y cierre de vela

**4.1 Identidad.** La clave de cualquier vela es (fuente, instrumento, temporalidad,
`open_time`). Es la clave natural de `freyja2_candles` (ADR 0003 §1): duplicar es imposible.

**4.2 Reglas.**

| Situación | Tratamiento |
| --------- | ----------- |
| Actualización de la vela en curso (`closed=false`) | Se retransmite para dibujar. **Nunca** se guarda, nunca alimenta señal ni orden (0004 §2). Manda la más reciente por `event_time` y, a igualdad, por orden de llegada. |
| Cierre declarado por el proveedor (`closed=true`) | Se inserta con la inserción idempotente. Si ya existe idéntica, no pasa nada. Si existe con **valores distintos**, es una revisión (§6). |
| Actualización de una vela **anterior a la última cerrada** | Se ignora y se cuenta (`OUT_OF_ORDER`). |
| Cierre que llega **tarde** (su vela es anterior a la última guardada) | Se acepta si no existe: rellena un hueco. Se marca como tardío. |
| Mismo cierre por dos conexiones (rotación) o por flujo y REST | Un solo registro; el resto, «sin cambios». |
| Símbolo, fuente o temporalidad que no se suscribió | Se descarta y se cuenta. |

**4.3 El reloj no cierra velas.** Una vela se guarda como cerrada solo cuando **el proveedor
lo declara** o cuando **REST la confirma**; jamás porque haya pasado su hora. En consecuencia:

- **Binance** declara el cierre (`x`): el flujo puede guardar la vela cerrada.
- **Kraken** no lo declara: su flujo **no guarda velas**. Cuando llega una actualización con
  una apertura posterior, o transcurrida la hora de cierre más el margen de publicación
  (10 s, ADR 0002 §3), se lanza **una petición REST dirigida** de esa serie para obtener la
  vela cerrada. Reutiliza el camino y el límite de 1 s entre peticiones del ADR 0007.
- **Verificación cruzada.** En cada reconexión y periódicamente (cada 15 minutos por defecto),
  se piden por REST las últimas cinco velas cerradas de cada serie y se comparan con lo
  guardado. Una diferencia sigue el camino de las revisiones (§6) y degrada la fuente (§7).

### 5. Huecos: detección, reparación y los que no tienen arreglo

**5.1 Hueco de cola** (el proceso estuvo parado o el flujo cayó): ya lo resuelve el escáner
(ADR 0006 §2): relleno hacia delante desde la última vela guardada, con tope por pasada. El
estado `RESYNCING` (§3) usa exactamente ese camino.

**5.2 Hueco interno** (falta una vela entre dos guardadas): hoy solo se **detecta** al leer
(ADR 0003 §5). Se añade una reparación **controlada**:

- Un trabajo lo busca solo dentro de la ventana de retención y de la del proveedor, y pide
  únicamente los rangos que faltan.
- **Acotada**: un máximo de velas y de peticiones por pasada y por fuente; menor prioridad que
  la cola; respeta el enfriamiento; solo la instancia líder; idempotente.
- **Nada se inventa**: ni interpolación ni relleno con la vela vecina.
- Un hueco que el proveedor ya no puede dar (más viejo que su horizonte: por ejemplo, Kraken
  solo conserva las 720 últimas velas de cada temporalidad, ADR 0007) **no se reintenta
  eternamente**: se declara `UNRECOVERABLE` y se conserva su registro.
- Un tramo sin negociación esperada (fin de semana de Forex, mantenimiento declarado) **no es
  un hueco**: lo decide el calendario de mercado (POINT2-CONTEXT-001).

**5.3 Registro de huecos** (tabla `freyja2_candle_gaps`, diseño):

| Campo | Contenido |
| ----- | --------- |
| Serie | Fuente, instrumento y temporalidad. |
| Tramo | `gap_from`, `gap_to` (UTC). |
| Estado | `OPEN`, `REPAIRED`, `UNRECOVERABLE`. |
| Trazabilidad | `first_seen_at`, `last_attempt_at`, `attempts`, motivo (`BEYOND_PROVIDER_HORIZON`, `PROVIDER_LACKS_CANDLE`…). |

El registro sirve para no repetir intentos inútiles, para que las personas y las decisiones
sepan que un hueco **no se va a cerrar**, y para que la validación histórica (POINT15) excluya
o marque esos tramos en lugar de suponerlos completos.

### 6. Revisiones y finalidad

- Una vela guardada **nunca se reescribe** (ADR 0003 §1): se mantiene.
- Si el proveedor informa después valores distintos, se guarda en un **registro de revisiones
  de solo inserción** (`freyja2_candle_revisions`): clave de la vela, número de revisión,
  valores, instante de detección y quién la detectó (flujo, REST, verificación cruzada).
- **Qué vela cuenta para decidir: la primera recibida.** Es la que vio cualquier decisión
  tomada entonces; sustituirla por otra cambiaría el pasado y rompería la reproducibilidad
  (CLAUDE.md §6). La versión más reciente del proveedor queda disponible **de forma explícita**
  para investigación, junto a una lectura «tal como era en el instante X» que necesita el
  backtesting (POINT15, sin _look-ahead_).
- Toda revisión marca la vela como `REVISED` y **degrada** la fuente durante una ventana
  (§7). Una revisión cuya magnitud supere una tolerancia (parámetro versionado, sin validar)
  la deja `DEGRADED` hasta que una persona la revise.
- **Finalidad:** una vela es final cuando está cerrada y ha pasado el margen de publicación.
  Una vela «final» puede aun así ser revisada por el proveedor: por eso existen las revisiones y
  no se presume inmutabilidad del origen, solo la nuestra.

### 7. Salud de fuentes y modo degradado, con fallo cerrado

Se distinguen dos niveles y **no se duplican**:

- **Verdad por serie** (la que decide): frescura, ventana sin huecos y calidad, ya calculadas por
  el contexto observable (POINT2-CONTEXT-001). Una decisión de señal depende de esto.
- **Salud por fuente** (operativa y para la persona usuaria): resumen agregado.

| Estado | Condición (parámetros iniciales, versionados como `source-health-v1`, **sin validar**) |
| ------ | ---------------------------------------------------------------------------------------- |
| `SUSPENDED` | Enfriamiento activo por límite o bloqueo. |
| `UNAVAILABLE` | Todas las series con tres o más fallos seguidos, o conexión caída más de 5 minutos sin una petición REST correcta. |
| `DEGRADED` | Alguna serie fallando u obsoleta; `RESYNCING`; huecos abiertos dentro de la ventana de decisión; revisión en las últimas 24 h; verificación cruzada con diferencias. |
| `HEALTHY` | Ninguna de las anteriores. |

- **Histéresis:** para salir de `DEGRADED` hacen falta tres comprobaciones limpias seguidas, de
  modo que la fuente no parpadee.
- **Fallo cerrado:** si el estado de salud no se puede leer, la fuente cuenta como
  `UNAVAILABLE`. Nunca se asume sana por defecto.
- **Sin sustituciones en silencio:** ninguna capa cambia de fuente por su cuenta. La estrategia
  declara una lista ordenada de fuentes autorizadas y el cambio queda registrado (ADR 0006 §4).
- **Ningún dato antiguo se presenta como actual:** una serie sin datos recientes se marca
  `STALE`; el explorador y la instantánea lo muestran (ya ocurre en Mercados).
- **Publicación:** estado actual por fuente (`freyja2_market_data_source_health`) y un registro
  de transiciones de solo inserción para auditar cuándo y por qué cambió. Sustituye lo dicho en
  0004 §3 («estados de conexión y salud en `freyja2_market_data_sync_state`»): esa tabla sigue
  siendo el estado **por serie** del último intento.

### 8. Aviso de cierres

Como en 0004 §3, con `LISTEN/NOTIFY` de PostgreSQL (conexión directa, no la agrupada) y
_Server-Sent Events_ hacia el navegador. Refinamientos:

- El aviso lleva **solo** la clave de la serie y `open_time` (unas decenas de bytes; el límite
  de PostgreSQL es 8000): el consumidor **lee la base**.
- Entrega **al menos una vez**: un consumidor idempotente ignora repeticiones y, al arrancar,
  lee lo que se perdió, porque un aviso perdido no es un cierre perdido.
- Las evaluaciones se disparan por **cierre de vela** (0004 §2), no por temporizador.

### 9. Líder único y worker

Como en 0004 §3, con dos precisiones: el bloqueo del líder es **de sesión** y exige una
conexión directa (no la agrupada de Neon); y al perder el liderazgo la máquina de conexión pasa
a `STOPPED` sin más escrituras. Las velas son idempotentes, así que una carrera entre dos
líderes no las corrompe; **las órdenes no lo serían**: cualquier camino de órdenes futuro exigirá
un **testigo de exclusión** (_fencing token_) propio, fuera de este ADR.

### 10. Fases, dado Render Free

| Fase | Contenido | Necesita proceso siempre activo |
| ---- | --------- | ------------------------------- |
| 0 (hoy) | Escáner REST dentro del backend, enfriamiento por fuente, dos fuentes. | No |
| 1 | Salud por fuente, registro de huecos y reparación, registro de revisiones. Son lógica y tablas que **pueden construirse y probarse ya** con el escáner actual. | No |
| 2 | Puerto de flujo, normalización y máquina de estados como **lógica pura**, probada sin red. | No |
| 3 | Worker de ingesta con los adaptadores WebSocket reales, avisos y explorador en directo. | **Sí (VPS)** |
| 4 | Temporalidades de segundos y agregación desde 1 s (0004 §4); más fuentes. | Sí |

Tareas que se derivan (cada una con su propio prompt aprobado; ninguna se crea sola):

1. `MARKET-DATA-HEALTH-001` — salud por fuente y modo degradado (§7). Fase 1.
2. `MARKET-DATA-GAPS-001` — registro y reparación controlada de huecos (§5). Fase 1.
3. `MARKET-DATA-REVISIONS-001` — registro de revisiones y lectura «tal como era» (§6). Fase 1.
4. `MARKET-DATA-STREAM-CORE-001` — puerto `CandleStream`, eventos, normalización, reglas de
   §4 y máquina de estados de §3, sin red. Fase 2.
5. `MARKET-DATA-WORKER-001` — worker de líder único y adaptadores reales de flujo. Fase 3.
6. `MARKET-DATA-RETENTION-001` — retención y presupuesto de espacio (§11).
7. `MARKET-DATA-TIMEFRAMES-001` — ampliar el catálogo y agregar desde 1 s. Fase 4.

### 11. Retención — decidida por Jessica (2026-09-25): opción E

**Criterio de Jessica:** que **no se agote el espacio de Neon** por ahora. Cuando Freyja sea
rentable se planteará migrar a una base de datos mayor (seguirá siendo PostgreSQL, CLAUDE.md §7);
hasta entonces, ninguna decisión de datos puede depender de pagar más almacenamiento.

**Regla de producto (2026-09-25):** las operaciones se cierran el mismo día y, como máximo, al
día siguiente por zona horaria. Esto acota la duración de una operación, **no** los datos que
hacen falta para decidirla ni para demostrar que una estrategia funciona:

- **Operar** necesita la ventana de cálculo del contexto y de los indicadores, no un año. El
  clasificador de tendencia pide 100 velas del marco de contexto; se prevén indicadores de hasta
  200 velas. Eso es distinto en cada temporalidad y fija la **ventana operativa**:

  | Temporalidad | 100 velas | 200 velas | Ventana operativa (con margen) |
  | ------------ | --------- | --------- | ------------------------------ |
  | 1 m | 1,7 h | 3,3 h | 2 días |
  | 5 m | 8,3 h | 16,7 h | 7 días |
  | 15 m | 25 h | 50 h | 14 días |
  | 1 h | 4,2 días | 8,3 días | 30 días |
  | 4 h | 16,7 días | 33 días | 90 días |

- **Validar una estrategia** exige meses de datos aunque cada operación dure horas: con una
  operación al día por estrategia hacen falta 100 días solo para reunir 100 operaciones, y hay
  que ver mercados distintos (CLAUDE.md §4). Es el punto 15 y **no necesita estar guardado
  hoy**.
- **Auditar** una señal no necesita sus velas: cada instantánea guarda su propia evidencia
  (giros de precio y motivos, ADR de instantánea de contexto).

**Medido:** 245 bytes por vela, tabla e índice (0004 §5). Neon Free ofrece 0,5 GB **en total**.
Hoy hay 8 combinaciones (4 instrumentos × 2 fuentes), cada una con cinco temporalidades.
Tamaño por combinación según la ventana:

| Temporalidad | Por día | 30 días | 90 días | 1 año |
| ------------ | ------- | ------- | ------- | ----- |
| 1 m | 353 kB | 10,6 MB | 31,8 MB | — |
| 5 m | 70,6 kB | 2,1 MB | 6,4 MB | 25,8 MB |
| 15 m | 23,5 kB | 0,7 MB | 2,1 MB | 8,6 MB |
| 1 h | 5,9 kB | 0,2 MB | 0,5 MB | 2,1 MB |
| 4 h | 1,5 kB | 0,04 MB | 0,1 MB | 0,5 MB |

| Opción | Ventanas (1 m · 5 m · 15 m · 1 h · 4 h) | Por combinación | Las 8 de hoy |
| ------ | ---------------------------------------- | --------------- | ------------ |
| A. Propuesta de 0004 | 90 d · 1 a · 1 a · 1 a · 1 a | 68,8 MB | 550 MB: no cabe |
| B. | 14 d · 90 d · 180 d · 1 a · 2 a | 18,7 MB | 150 MB |
| C. | 3 d · 30 d · 90 d · 1 a · 2 a | 8,5 MB | 68 MB |
| **E. Elegida** | **2 d · 7 d · 14 d · 1 a · 1 a** | **4,2 MB** | **34 MB** |

**Por qué E:**

- Las ventanas de 1 m a 15 m son la **ventana operativa**; 1 h y 4 h a un año son un **historial
  de investigación casi gratuito** (2,7 MB por combinación).
- **Binance** permite volver a bajar su historial por REST cuando haga falta: no hay que
  acumularlo por si acaso. **Kraken** solo da sus últimas 720 velas de cada temporalidad (ADR
  0007), así que lo que no se conserve no se recupera; por eso se guardan a un año las
  temporalidades gruesas, que apenas ocupan.
- Ampliar cualquier ventana cuando llegue el punto 15 es una decisión posterior, con su coste a
  la vista.

**Reglas que acompañan a la decisión:**

- **Presupuesto de espacio.** Activar una serie, una fuente o un instrumento nuevo obliga a
  declarar antes cuánto ocupará con sus ventanas. La tarea de retención incluirá una vigilancia
  del tamaño de la base de datos con **aviso al 60 % (300 MB)** y una regla de fallo cerrado:
  **no se activan series nuevas** si el tamaño pasa del 80 % (400 MB). Umbrales iniciales, sin
  validar.
- **Mecánica.** Borrar por rangos, en lotes acotados y solo lo que salga de la ventana, dejando
  constancia de lo retirado; el particionado queda para cuando el volumen lo justifique. Ningún
  borrado retrospectivo toca una vela que una instantánea o una señal referencien.
- Las velas de segundos, si llegan, **no se persisten** más allá de una ventana muy corta
  (0004 §5).
- **Fuera de alcance y aplazado:** migrar a una base de datos mayor. Se planteará cuando Freyja
  sea rentable, como decisión de Jessica y de coste; este ADR no lo prepara ni lo bloquea.

## Trazabilidad con otros puntos

| Punto | Qué necesita de este diseño |
| ----- | --------------------------- |
| POINT1 (catálogo) | Las temporalidades y los mapeos de fuente son **datos** (`ANALYSIS`/`SETTLEMENT`); las series por fuente; ampliar el catálogo es una migración, nunca cambio de esquema. |
| POINT2 (contexto y tendencia) | El contexto sigue juzgando cada serie (frescura, huecos, calidad); `SOURCE_NOT_AUTHORIZED` y `STALE_DATA` no cambian. Las revisiones y los huecos no recuperables deben poder reflejarse en la instantánea para que siga siendo reproducible. |
| POINT7 (momento de detección) | Eventos de cierre declarados o confirmados, finalidad, retraso (`received_at` frente a `event_time`), eventos fuera de orden y revisiones. |
| POINT15 (backtesting) | Lectura «tal como era», huecos marcados como no recuperables, política de retención frente a la necesidad de historial. |

## Criterios de aceptación de la tarea

| Criterio | Dónde |
| -------- | ----- |
| ADR y contratos de adaptadores | §1, §2 y este documento |
| Estados y transiciones de conexión documentados | §3 |
| Política de continuidad y calidad | §4 a §7 |
| Ningún dato antiguo puede presentarse como actual | §7 (y ADR 0002 §3) |
| Dependencias con POINT1, POINT2, POINT7 y POINT15 trazadas | Tabla anterior |

## Fuera de alcance

Implementación de cualquiera de estas piezas, credenciales o canales privados, ejecución de
órdenes, capacidades REAL, el universo definitivo de instrumentos y la elección de brokers
(pendientes de Jessica según 0004).

## Consecuencias

- Las tareas de la fase 1 y 2 pueden empezar **ya**, sin servidor de pago y sin tocar
  producción más allá de tablas nuevas.
- La retención (§11) está decidida: ya puede diseñarse `MARKET-DATA-RETENTION-001`. Hasta que
  exista, nada borra datos.
- Todo lo que dependa de datos de segundos sigue aplazado hasta el VPS, y se mostrará como no
  disponible, no como un dato retrasado presentado como actual.
