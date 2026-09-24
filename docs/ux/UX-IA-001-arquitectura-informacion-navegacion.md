# UX-IA-001 — Arquitectura de información y navegación de Freyja 2.0

- **Estado:** En elaboración — entregado para auditoría independiente del
  Arquitecto. No implementado.
- **Fecha:** 2026-09-23
- **Tarea Notion:** [UX-IA-001 — Definir arquitectura de información y
  navegación](https://app.notion.com/p/3a14f4ea4dcc8192ac91c5be622372be)
- **Orden del roadmap:** 1 de 3 (`UX-IA-001` → `UX-DESIGN-SYSTEM-001` →
  `UX-DASHBOARD-001`). Este documento no diseña visualmente nada, no
  implementa pantallas y no adelanta las dos tareas siguientes.

## 1. Objetivo

Definir y documentar el sitemap, las rutas canónicas y la navegación
principal de Freyja 2.0 antes de diseñar el sistema visual o cualquier
pantalla funcional, de forma que `UX-DESIGN-SYSTEM-001` y
`UX-DASHBOARD-001` (y las pantallas posteriores) tengan un mapa aprobado
sobre el que trabajar en lugar de decidir estructura de forma implícita o
divergente entre tareas.

## 2. Principios rectores

- **Una sola Freyja.** No existen productos independientes "Modo Fácil" y
  "Modo Experto"; la navegación es única para todas las personas usuarias.
  La profundidad de información podrá adaptarse dentro de cada pantalla en
  tareas futuras, pero comparte dominio, motor y rutas.
- **Registro público, una cuenta por persona.** Cualquier persona puede
  crear su propia cuenta desde la pantalla de registro y accede con sus
  propias credenciales; las cuentas no se comparten ni se reutilizan. La
  autenticación (registro, inicio de sesión, sesión y recuperación) está
  integrada mediante `AUTH-LOGIN-001`. Los datos de mercado y los gráficos
  son comunes; los datos privados de cada persona siguen aislados por su
  propietario. Un panel para administrar cuentas será una tarea posterior y
  no bloquea el registro. Este documento no diseña ese panel ni un modelo de
  roles — reutiliza el `authGuard` existente
  (`frontend/src/app/core/auth/auth.guard.ts`) como única puerta de acceso a
  todo lo definido aquí.
- **DEMO y REAL están conceptualmente separados en todo momento**, nunca
  fusionados en una sola vista ambigua. REAL permanece bloqueado y
  fail-closed a nivel de backend (`ExecutionContext.activation_status`,
  `credentials_status`, `venue_permission_status`,
  `owner_authorization_status`); ninguna pantalla de este sitemap puede
  presentar REAL como disponible mientras eso no cambie.
- **No hay datos ficticios.** Ninguna pantalla de este documento asume
  señales, operaciones, rendimientos o cartera simulados como si fueran
  reales. Donde no exista contrato de backend, la pantalla se documenta
  como conceptual, no como "disponible con datos de ejemplo".
- **No se inventan contratos.** Toda fuente de datos citada abajo es un
  endpoint que existe hoy (`/api/v1/auth`, `/api/v1/catalog`,
  `/api/v1/capabilities`, `/api/v1/execution-contexts`,
  `/api/v1/health`) o se marca explícitamente como pendiente de un Punto
  del `ROADMAP ÚNICO — FREYJA 2.0` sin backend todavía.

## 3. Sitemap y rutas canónicas

| Ruta | Pantalla | Prioridad |
|---|---|---|
| `/dashboard` | Dashboard | P0 |
| `/mercados` | Mercados | P1 |
| `/oportunidades` | Oportunidades | P2 |
| `/estrategias` | Estrategias | P3 |
| `/operaciones` | Operaciones | P3 |
| `/riesgo` | Riesgo y cartera | P3 |
| `/backtesting` | Backtesting | P4 |
| `/analitica` | Analítica | P4 |
| `/sistema` | Sistema | P5 |
| `/configuracion` | Configuración | P5 |

Rutas públicas (fuera del sitemap autenticado), accesibles sin sesión:

- `/register` — creación de una cuenta propia, abierta a cualquier persona.
- `/login` — inicio de sesión con las credenciales de cada persona.
- `/forgot-password` y `/reset-password` — flujo de recuperación de
  contraseña ya aprobado en `AUTH-LOGIN-001`.

Este documento no cambia ninguna decisión de autenticación ya integrada.

**Actualización (rediseño de interfaz):** `''` es ahora la **landing pública**
(`features/landing/`). Las pantallas autenticadas viven bajo un *shell* común con
guarda de sesión (`features/app-shell/`): `/dashboard` (`features/dashboard/`, que
sustituye al placeholder `HomePage`) y `/mercados`, `/mercados/:instrumentId`. El
login lleva a `/dashboard`; «Entrar» en la landing apunta a `/dashboard` y la guarda
decide (con sesión entra, sin sesión va a `/login`). El texto anterior queda como
histórico:

`''` (raíz autenticada) redirige a `/dashboard`. Hoy `''` carga
`HomePage` como *placeholder* de autenticación (`frontend/src/app/features/home/`);
sustituirlo por el shell real es alcance de `FRONTEND-SHELL-001`, no de
este documento.

La prioridad indica la importancia funcional y el orden conceptual de
las áreas, no el orden de ejecución de las tareas. El Dashboard es P0
porque será la pantalla principal después de autenticarse, pero su
diseño sigue el orden vinculante del roadmap:

`UX-IA-001` → `UX-DESIGN-SYSTEM-001` → `UX-DASHBOARD-001`.

Por tanto, que el Dashboard tenga prioridad P0 no autoriza diseñarlo ni
implementarlo antes de completar sus dependencias.

## 4. Detalle por pantalla

### 4.1 Dashboard — `/dashboard`

- **Propósito:** resumen operativo honesto del estado de Freyja: fuentes
  activas, calidad de datos, oportunidades vigentes, riesgo/exposición
  cuando existan contratos reales, alertas recientes.
- **Prioridad:** P0 (primera pantalla tras autenticarse).
- **Consumidor:** personas usuarias autenticadas.
- **Fuente de datos / contrato:** ninguno propio; agrega datos de las
  demás pantallas. Su disponibilidad real depende de la disponibilidad de
  cada área que resume.
- **Estado actual:** conceptual. No implementada — es el objeto de
  `UX-DASHBOARD-001`, la tarea siguiente después de
  `UX-DESIGN-SYSTEM-001`.
- **Estados vacío/error:** si ninguna área subyacente tiene datos, el
  dashboard debe mostrarlo explícitamente (p. ej. "Sin datos de mercado
  todavía"), nunca placeholders que parezcan cifras reales.
- **Dependencias:** `UX-IA-001`, `UX-DESIGN-SYSTEM-001` y los contratos
  conceptuales de las áreas que el dashboard resume. No requiere que las
  demás pantallas estén implementadas: puede diseñarse después de
  `UX-DESIGN-SYSTEM-001` aunque el resto siga pendiente de
  implementación.
- **Exclusiones:** ninguna métrica sin definición, fuente y timestamp
  (criterio ya fijado en `UX-DASHBOARD-001`).

### 4.2 Mercados — `/mercados`

- **Propósito:** explorar el catálogo canónico (mercados, productos,
  activos, instrumentos, timeframes) y su capacidad técnica por
  proveedor.
- **Prioridad:** P1 — única área con contrato de backend completo hoy.
- **Consumidor:** personas usuarias autenticadas.
- **Fuente de datos / contrato:** `POINT1-API-001`:
  `GET /api/v1/catalog/instruments` (filtrable por mercado, tipo de
  producto, símbolo y timeframe; cada `InstrumentOut` incluye embebidos
  su mercado, tipo de producto, activos y timeframes — no existen
  endpoints propios para esas entidades),
  `GET /api/v1/catalog/instruments/{instrument_id}`,
  `GET /api/v1/catalog/instruments/{instrument_id}/mappings`,
  `GET /api/v1/catalog/venues`, `GET /api/v1/catalog/data-sources`, y
  `GET /api/v1/capabilities` (`TechnicalCapability` por
  instrumento+timeframe+proveedor).
- **Estado actual:** contrato disponible; pantalla no implementada
  todavía (`POINT1-CATALOG-UI-001`, en backlog).
- **Estados vacío/error:** catálogo vacío para un filtro dado, capacidad
  `NOT_EVALUATED`/`NOT_SUPPORTED` mostrada tal cual (nunca colapsada a
  booleano), error de red distinto de "sin resultados".
- **Dependencias:** ninguna pantalla previa; es la primera con datos
  reales.
- **Exclusiones:** no muestra `ExecutionContext` (eso vive en
  Operaciones/Riesgo), no ejecuta órdenes.

### 4.3 Oportunidades — `/oportunidades`

- **Propósito:** oportunidades activas y caducadas detectadas sobre el
  catálogo (patrones, indicadores, condiciones/filtros, predicción).
- **Prioridad:** P2.
- **Consumidor:** personas usuarias autenticadas.
- **Fuente de datos / contrato:** ninguno implementado. Corresponde a
  varios Puntos del `ROADMAP ÚNICO` aún en backlog (detección de
  patrones, indicadores, condiciones/confirmaciones, predicción). El
  mapeo exacto pantalla↔Punto no está cerrado — ver §11.
- **Estado actual:** conceptual, sin contrato de backend.
- **Estados vacío/error:** "sin oportunidades vigentes" es un estado
  válido y distinto de "error al calcular oportunidades".
- **Dependencias:** Mercados (instrumento/timeframe base) y los Puntos de
  dominio pendientes citados arriba.
- **Exclusiones:** no ejecuta ni simula órdenes; una oportunidad nunca se
  presenta como señal confirmada, orden, fill o resultado — esos son
  conceptos distintos que no deben confundirse (criterio de aceptación de
  esta tarea).

### 4.4 Estrategias — `/estrategias`

- **Propósito:** definir/consultar combinaciones de condiciones,
  indicadores y patrones que producen oportunidades.
- **Prioridad:** P3.
- **Consumidor:** personas usuarias autenticadas.
- **Fuente de datos / contrato:** ninguno implementado; no hay Punto del
  roadmap identificado todavía como propietario exclusivo de
  "Estrategia" como entidad. Ver §11.
- **Estado actual:** conceptual, sin contrato de backend ni Punto de
  roadmap asignado con certeza.
- **Estados vacío/error:** sin estrategias definidas es un estado inicial
  válido, no un error.
- **Dependencias:** Oportunidades (los mismos bloques de dominio:
  patrones, indicadores, condiciones).
- **Exclusiones:** no ejecuta operaciones; no gestiona posiciones (eso es
  Operaciones/Riesgo).

### 4.5 Operaciones — `/operaciones`

- **Propósito:** ciclo de vida de una posición: apertura, gestión,
  resolución, cuando exista `ExecutionContext` habilitado.
- **Prioridad:** P3.
- **Consumidor:** personas usuarias autenticadas.
- **Fuente de datos / contrato:** `GET /api/v1/execution-contexts`
  (entorno DEMO/REAL, `activation_status`, `credentials_status` — ya
  existe) para saber *si* se puede operar; el contrato de la operación en
  sí (apertura, gestión de posiciones, resolución) corresponde a Puntos
  del roadmap todavía en backlog (gestión de posiciones y resolución —
  ver §11) y no está implementado.
- **Estado actual:** parcialmente disponible: el contrato de
  `ExecutionContext` existe (permite saber si DEMO/REAL están
  configurados), pero no existe todavía contrato de órdenes/posiciones.
  Pantalla conceptual.
- **Estados vacío/error:** "sin `ExecutionContext` configurado" es
  distinto de "sin posiciones abiertas", que es distinto de "REAL
  bloqueado" — los tres deben distinguirse en la interfaz, nunca
  colapsarse en un único mensaje genérico.
- **Dependencias:** Mercados, Oportunidades/Estrategias,
  `ExecutionContext`.
- **Exclusiones:** REAL se muestra siempre como bloqueado mientras el
  backend lo mantenga fail-closed (CLAUDE.md §4); esta pantalla nunca
  ofrece un botón de ejecución REAL funcional.

### 4.6 Riesgo y cartera — `/riesgo`

- **Propósito:** exposición, límites de pérdida y principios de
  protección aplicados, cuando existan contratos reales de ejecución.
- **Prioridad:** P3.
- **Consumidor:** personas usuarias autenticadas.
- **Fuente de datos / contrato:** ninguno implementado; corresponde a
  Puntos de gestión de posiciones y principios de protección, aún en
  backlog (ver §11).
- **Estado actual:** conceptual, sin contrato de backend.
- **Estados vacío/error:** sin `ExecutionContext` habilitado, esta
  pantalla debe indicar explícitamente que no hay cartera real que
  mostrar, no mostrar ceros como si fueran datos reales.
- **Dependencias:** Operaciones, `ExecutionContext`.
- **Exclusiones:** no calcula ni sugiere apalancamiento o tamaño de
  posición sin que el Punto de dominio correspondiente esté aprobado e
  implementado.

### 4.7 Backtesting — `/backtesting`

- **Propósito:** ejecutar y consultar backtests reproducibles de
  estrategias/oportunidades sobre datos históricos.
- **Prioridad:** P4.
- **Consumidor:** personas usuarias autenticadas.
- **Fuente de datos / contrato:** ninguno implementado todavía; el
  roadmap ya tiene un Punto dedicado explícitamente a esto
  (`POINT15-DOMAIN-001 — Contrato de backtesting y evidencia`), en
  backlog.
- **Estado actual:** conceptual, sin contrato de backend.
- **Estados vacío/error:** "sin backtests ejecutados" es un estado
  inicial válido; un backtest fallido se distingue de uno con resultado
  cero.
- **Dependencias:** Estrategias/Oportunidades, catálogo (Mercados).
- **Exclusiones:** ningún backtest se presenta sin comisiones, spread,
  slippage y calidad de datos considerados (CLAUDE.md §6); no hay
  ejecución REAL disparada desde esta pantalla.

### 4.8 Analítica — `/analitica`

- **Propósito:** métricas agregadas de rendimiento y calidad sobre
  oportunidades, estrategias y backtests históricos.
- **Prioridad:** P4.
- **Consumidor:** personas usuarias autenticadas.
- **Fuente de datos / contrato:** ninguno implementado; sin Punto de
  roadmap identificado con certeza como propietario (ver §11).
- **Estado actual:** conceptual, sin contrato de backend.
- **Estados vacío/error:** sin histórico suficiente, la pantalla lo
  declara explícitamente en vez de mostrar gráficas vacías sin
  explicación.
- **Dependencias:** Backtesting, Operaciones (para datos reales cuando
  existan).
- **Exclusiones:** no afirma que una estrategia es rentable o segura sin
  evidencia estadística suficiente (CLAUDE.md §4).

### 4.9 Sistema — `/sistema`

- **Propósito:** estado técnico de Freyja: salud del backend, conexión a
  base de datos, fuentes de datos activas/caídas.
- **Prioridad:** P5.
- **Consumidor:** personas usuarias autenticadas.
- **Fuente de datos / contrato:** `GET /api/v1/health` y
  `GET /api/v1/health/ready` (liveness/readiness, ya existen). Cobertura
  más amplia de observabilidad corresponde a `PLATFORM-OPS-DESIGN-001`
  (backlog, sin implementar).
- **Estado actual:** contrato parcial disponible (salud básica); el
  resto es conceptual.
- **Estados vacío/error:** "readiness=503" (no listo) es un estado
  explícito, no un error genérico de carga.
- **Dependencias:** ninguna pantalla previa.
- **Exclusiones:** no expone detalles de conexión, credenciales ni
  *stack traces* (ya es una restricción del propio endpoint de backend).

### 4.10 Configuración — `/configuracion`

- **Propósito:** preferencias de cuenta y, en el futuro, gestión de
  `ExecutionContext`/credenciales de proveedor.
- **Prioridad:** P5.
- **Consumidor:** personas usuarias autenticadas.
- **Fuente de datos / contrato:** `GET /api/v1/auth/me` existe para datos
  de la cuenta autenticada; gestión de credenciales de broker/venue no
  tiene contrato todavía (`SECURITY-BROKER-DESIGN-001`, backlog).
- **Estado actual:** contrato mínimo disponible (identidad de cuenta);
  resto conceptual.
- **Estados vacío/error:** sin credenciales configuradas es el estado
  inicial esperado, no un error.
- **Dependencias:** Auth (`AUTH-LOGIN-001`, ya integrado).
- **Exclusiones:** esta pantalla nunca solicita ni muestra credenciales
  de broker con permisos de retirada (CLAUDE.md §5).

## 5. Navegación

- **Navegación lateral:** lista fija con las 10 secciones de §3, en el
  orden de la tabla (Dashboard primero, Configuración último). Sin
  agrupamiento en submenús por ahora — 10 ítems planos son manejables sin
  jerarquía adicional; si el número de secciones crece, revisar en una
  tarea posterior.
- **Cabecera y contexto de sección activa:** la cabecera muestra el
  nombre de la sección activa y, cuando aplique, el entorno de ejecución
  actual (DEMO/REAL) de forma permanente y visible — nunca implícita.
- **Breadcrumbs:** no son necesarios en esta primera versión. El sitemap
  es plano (un nivel bajo cada ruta de §3); se reevaluará si aparecen
  subrutas (p. ej. detalle de un instrumento dentro de Mercados) en una
  tarea posterior.

## 6. Rutas protegidas y permisos

- Todas las rutas de §3 requieren sesión autenticada vía el `authGuard`
  ya existente (`frontend/src/app/core/auth/auth.guard.ts`). Todas las
  cuentas autenticadas tienen el mismo acceso a las pantallas del sitemap:
  no se define ningún modelo de roles ni permisos distintos por cuenta. Los
  datos de catálogo y de mercado son comunes; los recursos personales u
  operativos (p. ej. `ExecutionContext`) se muestran solo a su propietario.
- No existe todavía un concepto de "ruta no disponible" a nivel de
  *routing* de Angular: todas las rutas de §3 son alcanzables una vez
  autenticado, pero su contenido debe declararse "conceptual" (§4) cuando
  no exista contrato de backend, en vez de bloquear la ruta a nivel de
  navegación.
- El bloqueo de REAL ocurre en el backend (`ExecutionContext` fail-closed,
  ya implementado), no en el *routing* del frontend: ninguna ruta de
  Operaciones/Riesgo debe reimplementar esa lógica de bloqueo en el
  cliente.

## 7. Estados transversales de pantalla

Todas las pantallas de §4 deben distinguir, sin colapsar entre sí:

| Estado | Significado | Regla |
|---|---|---|
| Cargando | petición en curso | *skeleton*/indicador, nunca cifras provisionales que parezcan reales |
| Sin datos (vacío) | la fuente respondió pero no hay contenido | mensaje explícito de por qué está vacío |
| Parcialmente disponible | parte de la pantalla tiene datos, parte no | cada bloque sin datos se marca individualmente, nunca se omite en silencio |
| Error | la fuente falló | mensaje de error distinto del estado vacío, con reintento si aplica |
| Desconectado | no hay sesión válida o la API es inalcanzable | reutiliza el flujo ya existente del `authGuard` (redirección a `/login` en 401); un fallo de red 5xx/timeout se distingue de una sesión expirada |

## 8. Diferenciación DEMO/REAL en la navegación

- Dondequiera que una pantalla muestre datos de un `ExecutionContext`
  (Operaciones, Riesgo y cartera, y Backtesting cuando incorpore
  ejecución), el entorno (`DEMO` o `REAL`) se etiqueta de forma
  permanente y visualmente distinguible — sin depender solo del color
  (consistente con `UX-DESIGN-SYSTEM-001`, que definirá esa semántica
  visual).
- REAL se muestra siempre como presente-pero-bloqueado mientras el
  backend lo mantenga fail-closed; nunca se oculta el concepto ni se
  simula su disponibilidad.

## 9. Resumen de disponibilidad actual

| Pantalla | Contrato de backend | Pantalla implementada |
|---|---|---|
| Dashboard | No (agrega otras) | No |
| Mercados | Sí (`catalog`, `capabilities`) | No |
| Oportunidades | No | No |
| Estrategias | No | No |
| Operaciones | Parcial (`execution-contexts`) | No |
| Riesgo y cartera | No | No |
| Backtesting | No | No |
| Analítica | No | No |
| Sistema | Parcial (`health`, `health/ready`) | No |
| Configuración | Parcial (`auth/me`) | No |

Hoy, tras autenticarse, solo existe el *placeholder* `HomePage`. Ninguna
de las 10 pantallas de este sitemap está implementada; este documento
define el destino, no el estado actual del código.

## 10. Dependencias

- `AUTH-LOGIN-001` (completada) — autenticación y `authGuard` reutilizados
  tal cual.
- `POINT1-API-001` (completada) — contrato de catálogo y capacidades que
  respalda Mercados.
- `Roadmap de producto` y Puntos 2–15 del `ROADMAP ÚNICO — FREYJA 2.0`
  (backlog) — contratos de dominio pendientes para Oportunidades,
  Estrategias, Operaciones, Riesgo, Backtesting y Analítica.
- Este documento es dependencia de entrada para `UX-DESIGN-SYSTEM-001` y,
  transitivamente, de `UX-DASHBOARD-001`.

## 11. Decisiones pendientes

No se resuelven aquí; se exponen para que el Arquitecto decida:

1. **Mapeo exacto pantalla↔Punto del roadmap** para Oportunidades,
   Estrategias, Operaciones, Riesgo y Analítica. Los Puntos 3, 4, 5, 6 y
   10 (patrones, indicadores, condiciones, predicción) alimentan con
   bastante certeza a Oportunidades; los Puntos 12, 13 y 14 (gestión de
   posiciones, protección, resolución) alimentan a Operaciones/Riesgo;
   pero no hay Punto identificado con certeza como propietario de
   "Estrategia" como entidad distinta de "Oportunidad", ni de
   "Analítica" como área propia. Los Puntos 2, 7, 9 y 11 no se han
   revisado en detalle para este documento.
2. **Agrupamiento futuro de la navegación lateral:** si el catálogo de
   pantallas crece más allá de estas 10, ¿se agrupan en submenús o se
   mantiene lista plana? No es una decisión necesaria hoy, pero conviene
   dejarla anotada.
3. **Alcance de "Sistema" frente a `PLATFORM-OPS-DESIGN-001`:** este
   documento asume que `/sistema` es la superficie de UI de esa tarea de
   diseño (todavía en backlog), pero esa relación no está confirmada
   explícitamente en el roadmap.

## 12. Fuera de alcance de este documento

- Sistema visual, tokens, componentes, colores y tipografías
  (`UX-DESIGN-SYSTEM-001`).
- Diseño detallado o implementación del Dashboard (`UX-DASHBOARD-001`).
- Implementación de cualquier pantalla funcional o shell
  (`FRONTEND-SHELL-001`).
- Conexión con APIs, brokers o fuentes de mercado.
- Panel de administración de cuentas (tarea posterior; no bloquea el
  registro público).
- Cualquier dato ficticio de señales, operaciones, rendimientos o
  cartera.
- Cualquier contrato de backend no citado explícitamente como existente
  en este documento.
