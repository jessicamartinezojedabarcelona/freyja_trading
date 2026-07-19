# Auditoría de conocimiento reutilizable — Freyja anterior

> Tarea: `LEGACY-KNOWLEDGE-AUDIT-001`
> Tipo: auditoría estática de conocimiento, de solo lectura. No es una migración.
> Base de Freyja 2.0 auditada: commit `e626e0da4c76c8056f3709af68c7173f3e62dfc0` (rama `main`).
> **Estado de este documento: revisión preliminar corregida tras bloqueo de completitud del Arquitecto.** Sustituye la versión anterior, que presentaba una matriz parcial como si fuera completa.

---

## 1. Resumen ejecutivo

Esta auditoría revisa el repositorio previo de Freyja (`<LEGACY_ROOT>`, en adelante `LEGACY-SRC-01`) como fuente de conocimiento, sin copiar código, sin ejecutar nada y sin modificar ese repositorio.

**Recuento exacto de cobertura (verificado matemáticamente, ver §17):**

| Estado | Archivos | % del total |
|---|---|---|
| `REVIEWED_FULL` (lectura completa) | 25 | 8,7% |
| `REVIEWED_PARTIAL` (lectura parcial) | 3 | 1,0% |
| `MANIFEST_ONLY` (solo vía manifiesto de cuarentena legacy, sin lectura directa del archivo) | 48 | 16,7% |
| `NAME_ONLY` (solo existencia registrada por nombre/ruta, sin contenido leído) | 212 | 73,6% |
| `EXCLUDED` (excluido explícitamente) | 0 | 0% |
| **Total rastreado en `HEAD`** | **288** | **100%** |

Es decir: **el 91,3% de los 288 archivos versionados no fue leído directamente.** De ese 91,3%, casi dos tercios (212 de 288) no tienen ninguna evidencia más allá de su nombre y ruta.

Los **54 hallazgos** de la matriz de trazabilidad (§5) son, en consecuencia, **preliminares**. Se derivan de: 25 archivos leídos íntegramente (mayoritariamente documentación — README/ARQUITECTURA/ROADMAP/MANUAL_USUARIO, ADR, postmortems, tickets, y el prototipo de persistencia `freyja2/*`), 3 archivos leídos parcialmente, y — para una parte no menor de los hallazgos sobre código de dominio — la clasificación que el propio proyecto anterior hizo de sí mismo en `legacy-trading-manifest.json`. Ese manifiesto es una **fuente secundaria producida por el proyecto que se audita**, no una validación independiente; sus afirmaciones se han tratado en esta versión como lo que son — documentación del propio legacy, sujeta a contraste — y no como hechos verificados por esta auditoría.

Los totales de clasificación (**22 candidatos REUSE, 7 candidatos REWRITE, 19 REFERENCE, 6 REJECT**) corresponden **únicamente al subconjunto de 28 archivos con evidencia examinada** (25 completos + 3 parciales), más un número limitado de afirmaciones basadas en el manifiesto legacy. **No pueden interpretarse como cobertura completa del proyecto legacy**, ni como conclusión definitiva sobre qué del legacy es o no reutilizable: quedan **260 archivos** (48 `MANIFEST_ONLY` + 212 `NAME_ONLY`) sin evidencia directa, agrupados en un plan de 10 lotes (§15) para revisión posterior.

Ningún hallazgo REUSE/REWRITE debe interpretarse como autorización para copiar código: son, en el mejor de los casos, **candidatos** a reimplementar, pendientes de validación contra el código real en el lote correspondiente. Ninguna sección de este documento crea, modifica ni reordena el roadmap maestro.

**Conclusión de esta versión: AUDITORÍA PRELIMINAR — REQUIERE REVISIÓN POR LOTES** (ver §18/Conclusión final).

---

## 2. Alcance y reglas

- **Objetivo:** inventariar conocimiento reutilizable de la Freyja anterior y relacionarlo con el roadmap vigente, sin copiar ni reactivar código, arquitectura obsoleta, historial de git, bases de datos, migraciones, secretos, configuración ni dependencias.
- **Clasificación aplicada a cada hallazgo** (ver matiz obligatorio introducido en esta corrección, §5):
  - **REUSE CANDIDATE** — concepto o contrato potencialmente reutilizable sin cambios conceptuales, **pendiente de validación directa contra el código correspondiente**. Nunca implica copiar archivos ni autoriza a tratarlo como decidido.
  - **REWRITE CANDIDATE** — capacidad potencialmente todavía necesaria, que debería reimplementarse desde cero con los estándares de Freyja 2.0, **pendiente de la misma validación**.
  - **REFERENCE** — útil para entender decisiones, casos límite, vocabulario o lecciones aprendidas, pero no se incorpora directamente. Se mantiene sin sufijo "CANDIDATE" porque no implica una decisión de incorporación, solo de consulta.
  - **REJECT** — inseguro, obsoleto, duplicado, incompatible o contrario a decisiones vigentes. Se mantiene sin sufijo porque rechazar no requiere el mismo nivel de validación que adoptar.
- **Regla vinculante añadida en esta corrección:** ningún hallazgo REUSE/REWRITE queda "definitivo" en este documento. La promoción de un candidato a clasificación definitiva ocurre únicamente al cerrar el lote que lo cubre (§15), tras contrastar la afirmación documental contra el código real.
- **Alcance autorizado en Freyja 2.0:** exclusivamente la modificación de `docs/audits/legacy-knowledge-audit.md` (ya creado en la versión anterior de esta tarea). No se ha modificado en esta corrección ningún otro archivo del repositorio.
- **Alcance en el repositorio legacy:** estrictamente de solo lectura, sin cambios en esta corrección — no se leyó ningún archivo legacy nuevo (ver instrucción explícita del Arquitecto). Los recuentos exactos de esta versión se calcularon a partir de: (a) la lista completa de 288 rutas ya obtenida en la pasada anterior (`git ls-tree -r --name-only HEAD`, re-ejecutada en esta corrección únicamente para recuperar esa misma lista de metadatos de nombres, no de contenido), y (b) la copia local en caché de `legacy-trading-manifest.json` ya extraída en la sesión anterior (archivo de scratch en disco local, no una nueva lectura del repositorio legacy vía `git show`).
- **Nunca se mostró contenido de:** `.env`, credenciales, claves, certificados, bases de datos, dumps, logs, binarios, historiales de órdenes ni información personal.
- **Nunca se ejecutó:** código Python legacy, scripts npm legacy, tests legacy, migraciones legacy, Docker Compose legacy, ni consultas contra bases de datos legacy.

---

## 3. Fuentes y procedencia

| Fuente | Ruta | Remoto | Rama | Commit | Estado del working tree | Observaciones |
|---|---|---|---|---|---|---|
| `LEGACY-SRC-01` | `<LEGACY_ROOT>` | Repositorio privado de GitHub (URL omitida de este documento: contiene el nombre completo de la propietaria en el nombre de usuario, dato personal). `push` deshabilitado mediante un valor de gobernanza (`DISABLED_BY_RECOVERY_GOVERNANCE`), no una URL real. | `point1-seed-001-canonical-parity` | `44192410e70975a5f156db81f711e56bee63376b` (2026-07-18) | **No limpio** — el árbol de trabajo está deliberadamente vaciado: `git status -sb` reporta los 288 archivos versionados como borrados (`D`, sin stage); en disco solo persisten `.git/`, `.claude/` y `.gitignore`. Registrado explícitamente como evidencia de un working tree no limpio, conforme lo permite la tarea. | Único candidato identificado en el directorio local de trabajo de la propietaria (ruta omitida por privacidad; búsqueda no recursiva) que coincide con "sistema de trading previo" — no hubo ambigüedad que requiriera desambiguación con Jessica. Todo el contenido se accedió vía `git show HEAD:<ruta>`, nunca leyendo del disco. |

No se identificaron otras fuentes candidatas en el nivel inspeccionado. Este estado es idéntico al registrado en la versión anterior de este documento — no se ha vuelto a tocar el repositorio legacy en esta corrección (ver §16 y §18).

---

## 4. Metodología

1. **Precheck de Freyja 2.0** (Fase 1, pasada original): confirmado `HEAD` = `origin/main` = `e626e0da4c76c8056f3709af68c7173f3e62dfc0`.
2. **Identificación segura de la fuente legacy** (Fase 2, pasada original): un único candidato evidente, propiedades de repositorio leídas de forma read-only.
3. **Estrategia de lectura priorizada** (pasada original): se leyó primero `legacy-trading-manifest.json` y `LEGACY_TRADING.md` en su totalidad, luego los 4 documentos raíz, los ADR, postmortems, tickets, el modelo de dominio, el roadmap de testing frontend, y el prototipo `app/freyja2/persistence/*` con una de sus dos migraciones completa.
4. **Corrección de recuento** (esta pasada): se recontó con precisión, mediante herramientas de comparación exacta de conjuntos (no estimación), cuántos archivos `test_architecture_*.py` existen realmente. **Corrección de un error de la versión anterior:** el documento previo afirmaba "2 de 24 Architecture Tests" — el recuento exacto es **26 archivos `test_architecture_*.py`** (más `README.md` y `__init__.py` del mismo directorio, 28 en total), de los cuales 2 fueron leídos parcialmente. Este error se detectó precisamente al aplicar en esta corrección el mismo estándar de verificación matemática que exige el Arquitecto — se deja constancia de él en vez de corregirlo en silencio.
5. **Cinco estados de revisión, aplicados a los 288 archivos sin excepción** (nuevo en esta corrección, ver §17):
   - `REVIEWED_FULL` — leído íntegro por esta auditoría.
   - `REVIEWED_PARTIAL` — leído parcialmente (docstring/cabecera/fragmento) por esta auditoría.
   - `MANIFEST_ONLY` — no leído directamente; la única evidencia es la ficha que el propio `legacy-trading-manifest.json` (fuente secundaria, producida por el proyecto legacy sobre sí mismo) tiene de ese archivo.
   - `NAME_ONLY` — conocida su existencia y ruta exacta (vía `git ls-tree`), sin ninguna otra evidencia.
   - `EXCLUDED` — excluido explícitamente por la Fase 3 de la tarea original (binarios, `.venv`, `node_modules`, dumps, etc.). **Recuento: 0** — ninguno de los 288 archivos *versionados* cae en esta categoría; los artefactos que la Fase 3 pide excluir (`__pycache__`, `.venv`, bases de datos, logs) nunca estuvieron versionados en git y por tanto no aparecen en la lista de 288 rutas rastreadas, ni fue necesario decidir excluirlos activamente.
6. **Sin ejecución, sin nuevas lecturas de contenido del repositorio legacy en esta corrección:** los recuentos y la reclasificación de esta versión se construyeron a partir de evidencia ya obtenida en la pasada anterior (la lista de 288 rutas y la copia local en caché del manifiesto), conforme a la instrucción explícita de no leer archivos legacy nuevos durante esta corrección. La única operación repetida contra el repositorio legacy fue `git ls-tree`/`git status -sb`/`git rev-parse HEAD` (metadatos, no contenido de archivos) para confirmar que su estado no había cambiado desde la versión anterior (ver §18).

**Límite explícito, ahora cuantificado con precisión (ver §15 y §17):** 260 archivos (48 `MANIFEST_ONLY` + 212 `NAME_ONLY`) quedan pendientes de revisión directa, distribuidos en 10 lotes.

---

## 5. Matriz de trazabilidad (preliminar)

Todas las filas tienen `Fuente = LEGACY-SRC-01`. **Columna nueva `Estado de revisión`** (obligatoria en esta corrección): indica la calidad real de la evidencia detrás de cada hallazgo. Ningún hallazgo con estado distinto de `VERIFICADO` debe tratarse como confirmado.

Leyenda de `Estado de revisión`:
- **VERIFICADO** — el hallazgo describe el contenido de un archivo que esta auditoría leyó íntegro (típicamente, un documento describiéndose a sí mismo: una política, un ADR, un dato explícito en un ticket).
- **PARCIAL** — basado en una lectura parcial de la fuente.
- **BASADO EN MANIFIESTO** — la única evidencia es la ficha de `legacy-trading-manifest.json` sobre un archivo no leído directamente por esta auditoría.
- **PENDIENTE DE VALIDACIÓN** — el hallazgo hace una afirmación sobre código o comportamiento real que ningún archivo leído por esta auditoría confirma directamente; la fuente es una descripción de ese código en un documento (README/ARQUITECTURA/MANUAL_USUARIO/ADR), no el código mismo.

| ID | Ruta relativa | Tipo | Resumen del conocimiento | Clasificación | Estado de revisión | Riesgos | Tarea vigente | Confianza |
|---|---|---|---|---|---|---|---|---|
| LEGACY-AUDIT-001 | `backend/legacy-trading-manifest.json`, `backend/LEGACY_TRADING.md` | Documentación | Modelo de gobernanza de cuarentena FREYJA2-CUTOVER-000/001: estado `DEPRECATED_AND_QUARANTINED`, taxonomía de 4 categorías, allowlist de imports fail-closed. | REFERENCE | VERIFICADO | Ninguno directo; es un precedente de proceso, verificado por lectura directa del propio manifiesto. | PLATFORM-OPS-DESIGN-001 | Alta |
| LEGACY-AUDIT-002 | `README.md`, `ARQUITECTURA.md` | Documentación | La documentación legacy describe SQLite como base de datos de desarrollo por defecto ("no necesitas Docker ni PostgreSQL"). **No verificado si el código (`backend/app/database.py`, `NAME_ONLY`, Lote 2) coincide con esta descripción.** | REJECT | VERIFICADO (del texto del documento); PENDIENTE DE VALIDACIÓN (de si el código coincide) | Contradice persistencia única en PostgreSQL si se toma como descripción vigente del código. | PLATFORM-DATA-DESIGN-001 | Alta (doc) / Baja (código) |
| LEGACY-AUDIT-003 | `docs/tickets/be-bug-004-sqlalchemy-pool-exhaustion.md` | Lección aprendida | El ticket documenta, citando un traceback literal, que producción real corría sobre PostgreSQL gestionado (Supabase, pooler modo "session", límite 15 clientes). | REFERENCE | VERIFICADO (el ticket cita el traceback textualmente; no se verificó de forma independiente contra logs de producción reales, a los que esta auditoría nunca tuvo acceso) | Ninguno; es una lección de dimensionado. | PLATFORM-DATA-DESIGN-001 | Alta |
| LEGACY-AUDIT-004 | `docs/architecture/trading-domain-model.md` | Dominio | Modelo conceptual de 5 capas (Mercado, Estilo operativo, Timeframe, Estrategia técnica, Activos) como grafo de dos ramas paralelas, no cadena lineal. | REUSE CANDIDATE | VERIFICADO (contenido del documento de diseño en sí) | Ninguno; es diseño, no código verificado contra una implementación. | POINT1-DOMAIN | Alta (como documento) |
| LEGACY-AUDIT-005 | `docs/architecture/trading-domain-model.md` (§1); `README.md` "Deuda técnica" | Lección aprendida | `MarketType` mezclaba mercado (spot/futures) con instrumento, según lo describe el propio documento de dominio — antipatrón identificado por el proyecto anterior sobre sí mismo. | REFERENCE | VERIFICADO (afirmación del documento); PENDIENTE DE VALIDACIÓN (el modelo real, `backend/app/models/user_profile.py`, es `NAME_ONLY`, nunca leído) | Riesgo de repetir la misma mezcla de ejes conceptuales. | POINT1-DOMAIN | Media |
| LEGACY-AUDIT-006 | `ARQUITECTURA.md` (§"Modelos de datos") | Contrato/Dominio | `ARQUITECTURA.md` describe en prosa los campos de `Signal`, `Trade`, `PendingExecution`, `BrokerConnection`. Los modelos reales (`backend/app/models/signal.py`, `trade.py` son `MANIFEST_ONLY`; `pending_execution.py` también) no fueron leídos directamente. | REUSE CANDIDATE | PENDIENTE DE VALIDACIÓN | Riesgo de que la prosa del documento no coincida exactamente con los campos reales. | PENDIENTE DE MAPEO — requiere contrastar contratos vigentes de POINT2–POINT15 | Baja |
| LEGACY-AUDIT-007 | `docs/decisions/evaluate-trade-lifecycle.md` | Contrato/Dominio | ADR: contrato de cierre de trade — un trade solo cierra una vez, cierre atómico vía `UPDATE` condicionado, fallos aislados por trade. El código que implementa esto (`monitor.py`, `executor.py`) es `MANIFEST_ONLY`, no leído directamente. | REUSE CANDIDATE | VERIFICADO (el ADR en sí); PENDIENTE DE VALIDACIÓN (que el código implemente exactamente lo que el ADR describe) | Ninguno en el ADR; riesgo de desfase ADR↔código no descartable sin leer el código. | PENDIENTE DE MAPEO — requiere contrastar contratos vigentes de POINT2–POINT15 | Media (ADR) / Baja (código) |
| LEGACY-AUDIT-008 | `docs/decisions/pending-execution-follows-signal-lifecycle.md` | Contrato/Dominio | ADR: una confirmación pendiente debe depender del ciclo de vida de su señal. El propio ADR declara explícitamente que es "solo documentación" y que la regla **no está implementada todavía** en el código legacy. | REUSE CANDIDATE | VERIFICADO | Ninguno — el ADR mismo aclara que describe una regla *futura*, no código existente. | PENDIENTE DE MAPEO — requiere contrastar contratos vigentes de POINT2–POINT15 | Alta (como ADR de una regla no implementada, no como código) |
| LEGACY-AUDIT-009 | `docs/tickets/backend-expiracion-cancelacion-senales.md` | Contrato/Dominio | Máquina de estados de `Signal` (`ACTIVE → EXPIRED / EXECUTED / CANCELLED`) descrita en el ticket; el ticket mismo documenta que la persistencia real de `expires_at` en producción **no llegó a confirmarse** ("prueba decisiva pendiente", bloqueada por caída del servicio). | REUSE CANDIDATE | VERIFICADO (el ticket documenta su propia incertidumbre) | El propio ticket es evidencia de que ni el proyecto legacy pudo confirmar el comportamiento en producción. | UX-STATES-001 | Media |
| LEGACY-AUDIT-010 | `docs/decisions/signal-origin-deferred.md` | Lección aprendida | ADR de decisión diferida: no modelar el origen de una señal hasta que exista un consumidor real. | REFERENCE | VERIFICADO | Ninguno; disciplina de proceso documentada en el propio ADR. | PLATFORM-DATA-DESIGN-001 | Media |
| LEGACY-AUDIT-011 | `docs/decisions/frontend-feature-availability.md` | Contrato/UX | ADR permanente: el frontend nunca inventa estado que el backend no conoce. Es una política declarada, no una verificación de que el frontend legacy la cumple (`frontend/src/**` es casi enteramente `NAME_ONLY`). | REUSE CANDIDATE | VERIFICADO (la política, como texto); PENDIENTE DE VALIDACIÓN (que el frontend legacy la cumpla) | Ninguno como política; sin verificación de cumplimiento real. | UX-STATES-001 | Media |
| LEGACY-AUDIT-012 | `backend/app/freyja2/persistence/models.py`, `backend/alembic/versions/57ce4f19beb7_*.py` | Contrato/Dominio | Esquema de catálogo canónico (6 tablas, constraints de "código normalizado" y "forma exacta" mutuamente excluyente vía `CHECK`). | REUSE CANDIDATE | VERIFICADO (código y migración leídos directamente en su totalidad) | Ninguno; es un patrón de esquema, no datos. No verificado por ejecución de tests (los tests de `freyja2/` son `NAME_ONLY`). | POINT1-DB | Alta (estructura) / Media (que funcione, sin tests ejecutados) |
| LEGACY-AUDIT-013 | `backend/app/freyja2/persistence/identity.py` | Contrato/Dominio | Identidad canónica determinista: `uuid.uuid5(NAMESPACE_URL, identidad_canónica)` a partir de la clave natural. | REUSE CANDIDATE | VERIFICADO (código leído directamente) | Ninguno. | POINT1-SEED | Alta |
| LEGACY-AUDIT-014 | `backend/alembic/versions/a27cf55ab06f_freyja2_seed_canonical_catalog.py` | Contrato/Dominio | Patrón de migración de siembra fail-closed e idempotente (verificación de divergencia antes de `INSERT`, despacho por dialecto). Solo se leyó la cabecera/docstring y ~120 de 858 líneas; el resto (generación de PL/pgSQL fila por fila) no se inspeccionó. | REUSE CANDIDATE | PARCIAL | El patrón general parece sólido por el docstring, pero no se verificó línea por línea que la implementación cumpla lo que el docstring promete. | POINT1-SEED | Media |
| LEGACY-AUDIT-015 | `backend/app/freyja2/__init__.py`, `backend/app/freyja2/persistence/base.py` | Seguridad/Ops | Patrón de cuarentena arquitectónica: base declarativa separada + allowlist explícita de imports, dice el propio módulo que está "verificada por un test de arquitectura" (`test_architecture_freyja2_legacy_quarantine.py`, `REVIEWED_PARTIAL` — el test fue confirmado leyendo sus primeras ~80 líneas, no ejecutado). | REFERENCE | VERIFICADO (el código fuente en sí) / PARCIAL (para la afirmación de que el test lo hace cumplir) | Ninguno directo hoy. | PLATFORM-OPS-DESIGN-001 | Media |
| LEGACY-AUDIT-016 | `backend/legacy-trading-manifest.json` (entrada `app.models.strategy_spec`) | Dominio | El manifiesto clasifica `StrategySpec` como único módulo `REUSABLE_INFRASTRUCTURE` y aprobado como import permitido. El archivo real `backend/app/models/strategy_spec.py` es `MANIFEST_ONLY` — nunca leído directamente por esta auditoría. | REUSE CANDIDATE | BASADO EN MANIFIESTO | El manifiesto es una fuente secundaria (el propio proyecto legacy evaluándose a sí mismo); su clasificación no ha sido contrastada contra el archivo real. | POINT1-DOMAIN | Baja |
| LEGACY-AUDIT-017 | `docs/tickets/be-bug-004-sqlalchemy-pool-exhaustion.md` | Lección aprendida | Disciplina de dimensionado de pool documentada explícitamente por el ticket como regla a mantener. | REFERENCE | VERIFICADO | Ninguno; regla operativa documentada. | PLATFORM-DATA-DESIGN-001 | Alta |
| LEGACY-AUDIT-018 | `backend/tests/architecture/test_architecture_freyja2_legacy_quarantine.py`, `test_architecture_legacy_signal_generation_disabled.py` | Test | Patrón de "Architecture Tests" (invariantes fail-closed verificados con `pytest` contra AST real y BD real). Confirmado solo en los primeros fragmentos de 2 de 26 archivos `test_architecture_*.py` del directorio (recuento exacto y disjunto en el Lote 9F, ver §15); los 24 restantes son `NAME_ONLY`. | REUSE CANDIDATE | PARCIAL | El patrón parece sólido en los 2 archivos vistos; no generalizable automáticamente a los 24 restantes sin leerlos (Lote 9F). | (metodología de testing — sin ID exacto en la lista provista) | Baja |
| LEGACY-AUDIT-019 | `docs/testing/frontend-testing-roadmap.md` | Documentación | Plan de infraestructura de tests frontend por fases. **Inconsistencia verificada directamente por esta auditoría:** el documento afirma "cero archivos `*.test.ts(x)`", pero `git ls-tree` del mismo commit muestra 14 archivos `*.test.tsx`/`*.test.ts` reales y `vitest.config.ts`. | REUSE CANDIDATE (el método de priorización por fases, no el estado "qué existe" que describe) | VERIFICADO (tanto el contenido del documento como la discrepancia con `git ls-tree`, ambos confirmados directamente) | El documento está desactualizado; no usar su sección "qué NO existe" sin verificación adicional (Lote 8E). | ROADMAP GAP → `FRONTEND-TEST-001`, **preliminar, no confirmado** (ver §10) | Media |
| LEGACY-AUDIT-020 | `README.md` (§"Tests") | Documentación | El README declara 175 tests legacy cubriendo ciertas áreas. Ninguno de los archivos de test reales (62 en `backend/tests/*.py` + `freyja2/`, 28 en `architecture/`) fue contado o verificado independientemente — la cifra "175" es una afirmación del propio README, no un recuento propio. | REFERENCE | PENDIENTE DE VALIDACIÓN | La cifra "175" no ha sido verificada; podría estar desactualizada igual que LEGACY-AUDIT-019. | POINT1-TEST | Baja |
| LEGACY-AUDIT-021 | `ARQUITECTURA.md` (§"Seguridad de logs") | Seguridad/Ops | ARQUITECTURA.md describe el patrón `safe_log_exc`. El archivo real `backend/app/utils/safe_log.py` es `NAME_ONLY`. | REUSE CANDIDATE | PENDIENTE DE VALIDACIÓN | Riesgo de que la implementación real difiera de la descripción. | PLATFORM-OPS-DESIGN-001 | Baja |
| LEGACY-AUDIT-022 | `README.md`, `ARQUITECTURA.md` (§"Auditoría") | Seguridad/Ops | Documentación describe tablas de auditoría append-only con patrón ATTEMPT→SUCCESS/FAILED. Los modelos reales (`broker_audit_log.py`, `trade_audit_log.py`) son `NAME_ONLY`. | REUSE CANDIDATE | PENDIENTE DE VALIDACIÓN | Ídem. | SECURITY-BROKER-DESIGN-001 | Baja |
| LEGACY-AUDIT-023 | `ARQUITECTURA.md` (§"Seguridad de claves de broker") | Seguridad/Ops | Documentación describe cifrado Fernet AES-128. `backend/app/utils/broker_crypto.py` es `NAME_ONLY`. | REUSE CANDIDATE | PENDIENTE DE VALIDACIÓN | Ídem; además, riesgo de que la clave de cifrado se gestione de forma insegura en el código real, no visible desde la documentación. | SECURITY-BROKER-DESIGN-001 | Baja |
| LEGACY-AUDIT-024 | `ARQUITECTURA.md` (§"Arquitectura multi-broker") | Seguridad/Ops | Documentación describe `BrokerCapabilities` y `BrokerFactory`. `backend/app/services/brokers/base.py` y `factory.py` son `NAME_ONLY`. | REUSE CANDIDATE | PENDIENTE DE VALIDACIÓN | Ídem. | SECURITY-BROKER-DESIGN-001 | Baja |
| LEGACY-AUDIT-025 | `README.md`, `MANUAL_USUARIO.md` (§7) | Seguridad/Ops | Documentación describe rechazo automático de API Keys con permisos de retirada. El código que lo implementaría (endpoint de test-connection, `backend/app/main.py`, `MANIFEST_ONLY` solo a nivel de endpoint) no fue leído directamente. **Corrección respecto a la versión anterior:** no puede afirmarse "validado en producción real" — es una afirmación de la documentación del proyecto anterior sobre sí mismo, no verificada por esta auditoría (ver §14, reclasificación de afirmaciones). | REUSE CANDIDATE | PENDIENTE DE VALIDACIÓN | Riesgo de que el comportamiento real difiera de lo documentado — precisamente el tipo de riesgo de seguridad que no debe darse por sentado. | SECURITY-BROKER-DESIGN-001 | Baja |
| LEGACY-AUDIT-026 | `backend/app/services/brokers/{binance,coinbase,kraken,bybit}_adapter.py` | Algoritmo | Implementaciones concretas de adaptadores por exchange sobre `ccxt`. **Corrección respecto a la versión anterior:** el documento previo afirmaba que "el manifiesto legacy las clasifica REVIEW_BEFORE_REUSE" — esto es **incorrecto**; se ha verificado ahora, releyendo el manifiesto completo, que estos 4 archivos **no aparecen en absoluto** en `legacy-trading-manifest.json`. Son `NAME_ONLY`, no `MANIFEST_ONLY`. Se retracta la cita anterior al manifiesto. | REWRITE CANDIDATE | PENDIENTE DE VALIDACIÓN | Sin ninguna evidencia directa ni siquiera documental sobre el contenido real de estos 4 archivos — el nivel de confianza más bajo de toda la matriz. | SECURITY-BROKER-DESIGN-001 | Baja |
| LEGACY-AUDIT-027 | `ARQUITECTURA.md` (§"Deuda técnica") | Lección aprendida | ARQUITECTURA.md lista `/auth/login` sin protección de fuerza bruta como deuda técnica conocida. **Corrección de lenguaje:** no puede afirmarse que esta brecha "nunca se cerró en la vida del proyecto" — solo que, a la fecha de este documento (el commit auditado), seguía listada como pendiente; esta auditoría no revisó el historial de commits posteriores ni el código real (`backend/app/utils/auth.py` es `NAME_ONLY`). | REFERENCE | VERIFICADO (que el documento lo lista así, a fecha del documento); INFERENCIA (que "nunca se cerró") | Vector de ataque conocido si se repite sin verificar si de verdad sigue abierto. | F0-AUTH-BACKEND-001 | Media |
| LEGACY-AUDIT-028 | `ARQUITECTURA.md` (§"Seguridad general") | Seguridad/Ops | ARQUITECTURA.md documenta `CORS: allow_origins=["*"]` con la nota "cerrar en producción". Mismo matiz que LEGACY-AUDIT-027: no verificado si se cerró después de la fecha del documento. | REJECT | VERIFICADO (la nota del documento); INFERENCIA (que nunca se cerró) | No usar wildcard de CORS en ningún entorno con datos reales, independientemente de si legacy lo cerró o no. | F0-AUTH-BACKEND-001 | Media |
| LEGACY-AUDIT-029 | `backend/LEGACY_TRADING.md` | Lección aprendida | Documento describe, con cifras concretas, un incidente de purga de datos de producción sin backup externo. | REFERENCE | VERIFICADO (el documento lo declara con cifras específicas); no verificado contra ningún registro externo al propio documento | Crítico: ninguna estrategia de backup/recuperación existía antes de este incidente, según el propio documento. | PLATFORM-OPS-DESIGN-001 | Alta (como afirmación documental) |
| LEGACY-AUDIT-030 | `docs/postmortems/P0-3-strategy-metrics.md` | Lección aprendida | El postmortem describe, citando un hash de commit concreto (`843e28e`), que dos motores de cierre de trade coexistieron y que unificar uno rompió silenciosamente la actualización de métricas. | REJECT (duplicar motores) / REFERENCE (la lección) | VERIFICADO (el postmortem lo describe con detalle técnico verificable internamente, incluyendo el hash) | Repetir dos implementaciones "canónicas" simultáneas de la misma responsabilidad. | PLATFORM-OPS-DESIGN-001 | Alta |
| LEGACY-AUDIT-031 | `docs/postmortems/P0-3-strategy-metrics.md` | Lección aprendida | Disciplina: al eliminar código duplicado, verificar explícitamente los efectos secundarios de la ruta eliminada. | REFERENCE | VERIFICADO | Ninguno; disciplina de revisión de refactors. | PLATFORM-OPS-DESIGN-001 | Alta |
| LEGACY-AUDIT-032 | `docs/postmortems/P0-001-evaluate-trade-timezone.md` | Lección aprendida | El postmortem describe, con el mensaje de error literal, un bug de comparación tz-naive vs. tz-aware en pandas. | REFERENCE | VERIFICADO (el postmortem cita el error literal) | Refuerza la regla ya vigente en `CLAUDE.md` §6. | PLATFORM-DATA-DESIGN-001 | Alta |
| LEGACY-AUDIT-033 | `docs/decisions/evaluate-trade-lifecycle.md` (regla 13, ARCH-006) | Lección aprendida / Contrato | El ADR narra una race condition real y su fix mediante `UPDATE` condicionado atómico. El código real (`executor.py`) y el test (`test_architecture_evaluate_trade.py`) son `MANIFEST_ONLY`/`NAME_ONLY` — no se leyó ni el fix ni el test que lo prueba. | REUSE CANDIDATE | VERIFICADO (la narrativa del ADR); PENDIENTE DE VALIDACIÓN (el código real) | El patrón descrito es correcto en teoría; no confirmado en la implementación real. | PENDIENTE DE MAPEO — requiere contrastar contratos vigentes de POINT2–POINT15 | Media (ADR) / Baja (código) |
| LEGACY-AUDIT-034 | `docs/tickets/backend-contrato-signaldto-frontend.md` | Lección aprendida | El ticket documenta una deriva de contrato real y ya observada (bug visible: señales mostradas como SHORT). | REFERENCE | VERIFICADO | Riesgo de repetir nombres de campo divergentes entre canales. | POINT1-API | Alta |
| LEGACY-AUDIT-035 | `docs/postmortems/P0-3-6-position-sizing-source.md` | Lección aprendida | Pregunta de diseño documentada como abierta y no resuelta en legacy. | REFERENCE | VERIFICADO | Decisión de riesgo que Freyja 2.0 debería tomar deliberadamente, no heredar por omisión. | SAFETY-CONTROL-DESIGN-001 | Alta |
| LEGACY-AUDIT-036 | `ARQUITECTURA.md` (§"Guard de autotrading") | Seguridad/Ops | Documentación describe un guard de 11 condiciones. `backend/app/services/autotrading_guard.py` es `MANIFEST_ONLY` — la ficha del manifiesto confirma su rol pero no las 11 condiciones exactas. | REUSE CANDIDATE | BASADO EN MANIFIESTO / PENDIENTE DE VALIDACIÓN | El detalle de "11 condiciones ordenadas" proviene solo de la documentación, no del código. | SAFETY-CONTROL-DESIGN-001 | Media |
| LEGACY-AUDIT-037 | `README.md`, `MANUAL_USUARIO.md` (§7) | Seguridad/UX | Documentación describe mecanismo de "emergency stop". El endpoint real (`backend/app/main.py::POST .../emergency-stop`) es `MANIFEST_ONLY` a nivel de responsabilidad declarada, no de implementación. | REUSE CANDIDATE | BASADO EN MANIFIESTO / PENDIENTE DE VALIDACIÓN | Ídem. | SAFETY-CONTROL-DESIGN-001 | Media |
| LEGACY-AUDIT-038 | `MANUAL_USUARIO.md` (§7) | Seguridad/UX | El manual describe la confirmación de riesgo escrita ("Entiendo que puedo perder dinero real") como flujo de producto/UX. | REUSE CANDIDATE | VERIFICADO (como descripción de UX en el manual; no como confirmación de que el backend realmente la registra con fecha/hora, que es `NAME_ONLY`) | Ninguno en el concepto de producto. | SAFETY-CONTROL-DESIGN-001 | Media |
| LEGACY-AUDIT-039 | `README.md`, `ARQUITECTURA.md` (§"Monitor loop") | Algoritmo | Documentación describe la regla conservadora SL/TP (gana el Stop Loss en la misma vela). `backend/app/services/monitor.py` es `MANIFEST_ONLY`. | REUSE CANDIDATE | BASADO EN MANIFIESTO / PENDIENTE DE VALIDACIÓN | Riesgo de que la implementación real no siga exactamente esta regla. | SAFETY-CONTROL-DESIGN-001 | Media |
| LEGACY-AUDIT-040 | `README.md` (§"Flujo principal") | Algoritmo | Documentación describe tres zonas de confianza para el modo de ejecución. | REUSE CANDIDATE | VERIFICADO (como descripción documental; los umbrales no se confirmaron contra código, que es `MANIFEST_ONLY`) | Los umbrales concretos son parametrizables, no una verdad de dominio a heredar sin revisión. | SAFETY-CONTROL-DESIGN-001 | Media |
| LEGACY-AUDIT-041 | `ARQUITECTURA.md`, `MANUAL_USUARIO.md` (§4) | Producto/IA | Documentación describe el motor de "voz de Freyja" rule-based sin LLM. `backend/app/services/freyja_voice.py` es `MANIFEST_ONLY`. | REUSE CANDIDATE | VERIFICADO (como concepto documentado); PENDIENTE DE VALIDACIÓN (implementación real) | Ninguno en el concepto. | FREYJA-VOICE-DESIGN-001 | Media |
| LEGACY-AUDIT-042 | `MANUAL_USUARIO.md` (§6) | Producto/UX | Vocabulario unificado documentado en el manual de usuario (artefacto puramente textual, verificable en sí mismo). | REUSE CANDIDATE | VERIFICADO | Ninguno. | FREYJA-VOICE-DESIGN-001 | Alta |
| LEGACY-AUDIT-043 | `MANUAL_USUARIO.md` (§1) | Producto/UX | Manual describe onboarding con selección de perfil en lenguaje humano. `frontend/src/pages/Onboarding.tsx` es `NAME_ONLY`. | REUSE CANDIDATE | PENDIENTE DE VALIDACIÓN | Riesgo de que la UI real no coincida con la descripción del manual. | PRODUCT-ONBOARDING-DESIGN-001 | Baja |
| LEGACY-AUDIT-044 | `ARQUITECTURA.md` (§"Frontend"), `README.md` | Producto/UX | Documentación describe "Modo Fácil"/"Modo Experto" como superficies alternadas por `ModeContext`. El archivo/mecanismo exacto (`context/`) es `NAME_ONLY` — no se ha confirmado el nombre exacto del archivo ni su implementación. | REJECT | VERIFICADO (la descripción textual); PENDIENTE DE VALIDACIÓN (el archivo/mecanismo exacto) | Contradice el principio vigente de `CLAUDE.md` §4 si la descripción documental es exacta. | UX-IA-001 | Media |
| LEGACY-AUDIT-045 | `docs/testing/frontend-testing-roadmap.md` | Lección aprendida | El propio roadmap de testing legacy señala `EasyMode.tsx` (894 líneas) como riesgo de mantenibilidad. | REFERENCE | VERIFICADO (el roadmap lo declara); el tamaño real del archivo no fue confirmado de forma independiente | Antipatrón de componentización; **discrepancia detectada:** `EasyMode.tsx` no aparece en el listado de 288 archivos de este commit, lo que sugiere que el roadmap de testing describe un estado del proyecto anterior a este commit, o un archivo renombrado/eliminado. Ver §12. | UX-MODULES-001 | Media |
| LEGACY-AUDIT-046 | `README.md` (§"Auditoría"), `ARQUITECTURA.md` | Seguridad/Ops | Documentación describe JWT con auditoría de sesión. `backend/app/utils/auth.py`, `backend/app/models/user.py` son `NAME_ONLY`. | REUSE CANDIDATE | PENDIENTE DE VALIDACIÓN | Ninguno en el concepto. | F0-AUTH-DESIGN-001 | Baja |
| LEGACY-AUDIT-047 | `README.md`, `ARQUITECTURA.md` | Algoritmo | Documentación describe filtro de noticias vía scraping de ForexFactory. `backend/app/services/news/*` es `NAME_ONLY`. | REWRITE CANDIDATE | PENDIENTE DE VALIDACIÓN | Ver LEGACY-AUDIT-053. | NOTIFICATION-DESIGN-001 | Baja |
| LEGACY-AUDIT-048 | `README.md` (§"Variables de entorno") | Algoritmo/Ops | Documentación describe notificaciones vía Discord y WhatsApp (CallMeBot). `backend/app/utils/notifications.py` es `MANIFEST_ONLY` (el manifiesto advierte que está acoplado a `strategy_registry` y necesita desacoplarse antes de reutilizarse). | REWRITE CANDIDATE | BASADO EN MANIFIESTO | Ver LEGACY-AUDIT-054. | NOTIFICATION-DESIGN-001 | Baja |
| LEGACY-AUDIT-049 | `ARQUITECTURA.md` (§"Deuda técnica"); manifiesto | Producto/IA | El manifiesto cita textualmente el docstring de `strategy_discoverer.py`, que se autodeclara "SKELETON" sin implementación real. | REFERENCE | BASADO EN MANIFIESTO (que a su vez cita el docstring real del archivo — evidencia indirecta pero de razonable calidad) | Ninguno; es una aspiración sin implementación. | AI-LLM-EVALUATION-001 | Media |
| LEGACY-AUDIT-050 | `README.md` (§"Estrategias"); manifiesto | Algoritmo | Documentación y manifiesto describen 5 estrategias técnicas legacy (RSI+EMA, MACD+Volumen, Bollinger, Scalping, Fibonacci). Ningún archivo de estrategia (`bollinger_strategy.py`, etc.) fue leído directamente — todos son `MANIFEST_ONLY`. | REWRITE CANDIDATE | BASADO EN MANIFIESTO | Ninguna verificación de que el cálculo de indicadores evite look-ahead bias (`CLAUDE.md` §6) — no se puede confirmar sin leer el código. | PENDIENTE DE MAPEO — requiere contrastar contratos vigentes de POINT2–POINT15 | Baja |
| LEGACY-AUDIT-051 | `ROADMAP.md` (v0.1) | Algoritmo | Mención breve de backtesting histórico desde la v0.1; sin ningún detalle de metodología en las fuentes leídas. | REWRITE CANDIDATE | VERIFICADO (que el documento lo menciona así de brevemente, sin más detalle) | Sin evidencia de que el backtest legacy considerara comisiones/spread/slippage. | PENDIENTE DE MAPEO — requiere contrastar contratos vigentes de POINT2–POINT15 | Baja |
| LEGACY-AUDIT-052 | `ARQUITECTURA.md` (§"Deuda técnica") | Algoritmo/UX | Documentación declara el WebSocket de posiciones como polling de 5s, no tiempo real verdadero. | REWRITE CANDIDATE | VERIFICADO (declaración del propio documento) | Ninguno; es una capacidad pendiente según la fuente. | UX-DASHBOARD-001 | Media |
| LEGACY-AUDIT-053 | `README.md`, `ARQUITECTURA.md` (filtro de noticias) | Seguridad/Ops | Documentación describe scraping no oficial de ForexFactory. `backend/app/services/news/provider.py` es `NAME_ONLY` — no se confirmó el mecanismo real, solo la descripción documental. | REJECT | VERIFICADO (la descripción documental); PENDIENTE DE VALIDACIÓN (el código real) | Riesgo legal/ToS y de fragilidad técnica, según lo descrito. | NOTIFICATION-DESIGN-001 | Media |
| LEGACY-AUDIT-054 | `README.md` (notificaciones WhatsApp) | Seguridad/Ops | Documentación describe CallMeBot como transporte de WhatsApp. | REJECT | VERIFICADO (la descripción documental) | Riesgo de disponibilidad/ToS, según lo descrito. | NOTIFICATION-DESIGN-001 | Media |

---

## 6. Candidatos REUSE (preliminares — ninguno validado directamente contra código)

Los cinco grupos siguientes son los de mayor interés aparente, **todos pendientes de contraste directo con el código real en el lote correspondiente (§15)**. El manifiesto legacy, cuando se cita como evidencia, es una fuente secundaria (el proyecto anterior evaluándose a sí mismo) y no sustituye esa validación.

**LEGACY-AUDIT-004 — Modelo de dominio de 5 capas.** VERIFICADO como documento de diseño. No requiere validación de código porque no describe una implementación existente, sino una propuesta. Tarea destino: `POINT1-DOMAIN`. Sigue siendo el candidato más sólido de todo el documento precisamente porque su evidencia es un texto completo, no una inferencia sobre código no leído.

**LEGACY-AUDIT-012/013/014 — Catálogo canónico `freyja2_*`.** VERIFICADO/PARCIAL — el único bloque de "código de producción" leído directamente en su totalidad (excepto la mayor parte de los datos literales de la migración de siembra). Es, junto con LEGACY-AUDIT-004, el candidato con mayor base de evidencia real. Tarea destino: `POINT1-DB`, `POINT1-SEED`. Pendiente: leer completa la migración de siembra (Lote 2) y los 12 tests de `freyja2/` (Lote 9E) antes de promover a definitivo.

**LEGACY-AUDIT-021/022/023/024/025 — Paquete de seguridad de brokers.** Todos **PENDIENTE DE VALIDACIÓN** — ninguno de los archivos de código subyacentes (`safe_log.py`, modelos de auditoría, `broker_crypto.py`, `brokers/base.py`, `brokers/factory.py`) fue leído. La evidencia es exclusivamente prosa de `ARQUITECTURA.md`/`README.md`/`MANUAL_USUARIO.md`. **No puede afirmarse, como hacía la versión anterior de este documento, que la regla de rechazo de permisos de retirada "ya fue validada en producción real"** — eso es una afirmación de la propia documentación legacy sobre sí misma, no verificada por esta auditoría (ver §14). Tarea destino: `SECURITY-BROKER-DESIGN-001`. Requiere Lote 1 (seguridad) y Lote 5 (brokers) antes de cualquier promoción.

**LEGACY-AUDIT-036/037/038/039/040 — Controles de seguridad de ejecución.** Mayormente **BASADO EN MANIFIESTO** o **PENDIENTE DE VALIDACIÓN**; solo LEGACY-AUDIT-038/040 tienen algo más de solidez por describir flujo de producto/UX documentado explícitamente, no comportamiento de backend. Tarea destino: `SAFETY-CONTROL-DESIGN-001`. Requiere Lote 5 (riesgo/brokers) y Lote 4 (señales) antes de promoción.

**LEGACY-AUDIT-041/042 — Motor de voz de Freyja y vocabulario.** LEGACY-AUDIT-042 (vocabulario) es VERIFICADO al ser un artefacto puramente textual del manual. LEGACY-AUDIT-041 (motor rule-based) es PENDIENTE DE VALIDACIÓN en cuanto a implementación (`freyja_voice.py` nunca leído), aunque el *concepto* (existencia de un modo sin LLM) está descrito de forma consistente en tres documentos distintos leídos íntegros. Tarea destino: `FREYJA-VOICE-DESIGN-001`. Requiere Lote 3.

---

## 7. Candidatos REWRITE (preliminares)

**LEGACY-AUDIT-026 — Adaptadores concretos de broker.** **Confianza más baja de todo el documento.** Se retracta expresamente la afirmación de la versión anterior de que "el manifiesto los clasifica REVIEW_BEFORE_REUSE" — verificado ahora que estos 4 archivos no aparecen en el manifiesto en absoluto. No hay ninguna evidencia, ni siquiera documental indirecta, sobre su contenido real. Tarea destino: `SECURITY-BROKER-DESIGN-001`. Requiere Lote 5 íntegro antes de cualquier afirmación sobre estos archivos.

**LEGACY-AUDIT-047 / LEGACY-AUDIT-053 — Filtro de noticias.** PENDIENTE DE VALIDACIÓN / VERIFICADO (documental). La capacidad de producto (filtrar por noticias) está descrita consistentemente; la técnica concreta (scraping) también, y se rechaza como técnica (§9) independientemente de si se valida el código. Tarea destino: `NOTIFICATION-DESIGN-001`. Requiere Lote 3.

**LEGACY-AUDIT-048 / LEGACY-AUDIT-054 — Notificaciones externas.** BASADO EN MANIFIESTO (para `notifications.py`, que sí aparece en el manifiesto con una advertencia explícita de acoplamiento a `strategy_registry`) / VERIFICADO (documental, para CallMeBot). Tarea destino: `NOTIFICATION-DESIGN-001`. Requiere Lote 3.

**LEGACY-AUDIT-050 / LEGACY-AUDIT-051 — Estrategias, indicadores, backtesting.** BASADO EN MANIFIESTO / VERIFICADO (solo de la mención breve en ROADMAP.md, sin metodología). Tarea destino: **pendiente de mapeo**, ver ítem POINT2–POINT15 en §9/§12. Requiere Lote 4 (estrategias/indicadores) y Lote 6 (backtesting).

**LEGACY-AUDIT-052 — WebSocket de posiciones en tiempo real.** VERIFICADO (declaración documental de que hoy es polling, no WS real). Tarea destino: `UX-DASHBOARD-001`. Requiere Lote 8D.

---

## 8. Material REFERENCE

Se mantiene la clasificación de la versión anterior; se añade aquí la distinción hecho/documentación/inferencia donde corresponde (desarrollo completo en §14).

- **LEGACY-AUDIT-001** — Precedente de gobernanza. VERIFICADO (documento leído íntegro describiéndose a sí mismo).
- **LEGACY-AUDIT-003 / LEGACY-AUDIT-017** — Caso de agotamiento de pool. VERIFICADO como afirmación documental con traceback citado; no confirmado contra logs reales externos al documento.
- **LEGACY-AUDIT-005** — Antipatrón `MarketType`. VERIFICADO como autodiagnóstico documental.
- **LEGACY-AUDIT-010** — Patrón de ADR de decisión diferida. VERIFICADO.
- **LEGACY-AUDIT-019** — Roadmap de testing desactualizado. VERIFICADO (la discrepancia se comprobó directamente contra `git ls-tree`, no es una inferencia).
- **LEGACY-AUDIT-020** — Áreas de cobertura de test declaradas. PENDIENTE DE VALIDACIÓN (cifra "175" no verificada).
- **LEGACY-AUDIT-027 / LEGACY-AUDIT-028** — Brechas conocidas. VERIFICADO que el documento las lista a la fecha del commit auditado; **INFERENCIA**, no hecho demostrado, que "nunca se cerraron" — esta auditoría no revisó commits posteriores al `HEAD` auditado (`44192410e70975a5f156db81f711e56bee63376b`) ni el código real.
- **LEGACY-AUDIT-029** — Incidente de purga de datos. VERIFICADO como afirmación documental con cifras específicas; no confirmado contra un registro externo al propio documento (no existe tal registro accesible a esta auditoría).
- **LEGACY-AUDIT-030 / LEGACY-AUDIT-031** — Motores de cierre duplicados. VERIFICADO (postmortem con hash de commit citado).
- **LEGACY-AUDIT-032** — Bug de timezone. VERIFICADO (traceback literal citado en el postmortem).
- **LEGACY-AUDIT-033** — Race condition y su fix. VERIFICADO la narrativa del ADR; PENDIENTE DE VALIDACIÓN el código real del fix.
- **LEGACY-AUDIT-034** — Deriva de contrato `SignalDTO`. VERIFICADO (ticket con bug concreto descrito).
- **LEGACY-AUDIT-035** — Pregunta de position sizing abierta. VERIFICADO (el postmortem la declara explícitamente abierta).
- **LEGACY-AUDIT-045** — Componente monolítico `EasyMode.tsx`. VERIFICADO que el roadmap de testing lo señala; **discrepancia sin resolver:** ese archivo no aparece en el listado de 288 rutas de este commit — ver §12.
- **LEGACY-AUDIT-049** — Skeleton de descubrimiento por ML. BASADO EN MANIFIESTO (que cita el docstring real del archivo).

---

## 9. Elementos REJECT

Se mantiene la tabla de la versión anterior; se ajusta la columna de evidencia donde la versión anterior sobre-afirmaba certeza.

| Elemento | Motivo de rechazo | Riesgo | Regla que lo prohíbe | Estado de la evidencia | Acción |
|---|---|---|---|---|---|
| LEGACY-AUDIT-002 — SQLite documentada como base de datos suficiente | Persistencia dual documentada que no coincide con la política de una única base de datos. | Confusión de arquitectura si se toma el README legacy como referencia vigente. | `CLAUDE.md` §7. | VERIFICADO (lo que dice el documento); PENDIENTE DE VALIDACIÓN (si el código coincide) | No migrar; PostgreSQL ya es la única base de datos de Freyja 2.0 (`F0-DATABASE-001`, ya completada) — este REJECT no depende de validar el código legacy. |
| LEGACY-AUDIT-028 — `CORS allow_origins=["*"]` | Documentado como "cerrar en producción" sin evidencia de haberse cerrado. | Superficie de ataque si se replica tal cual. | Buen juicio de seguridad; `CLAUDE.md` §5. | VERIFICADO (la nota del documento); INFERENCIA (que nunca se cerró) | No copiar la configuración, independientemente de si legacy la cerró después. |
| LEGACY-AUDIT-030 — Dos motores de cierre de trade coexistiendo | Duplicación de responsabilidad que divergió silenciosamente. | Bugs de inconsistencia difíciles de diagnosticar. | `CLAUDE.md` §11. | VERIFICADO (postmortem con hash de commit) | No replicar el patrón. |
| LEGACY-AUDIT-044 — "Modo Fácil"/"Modo Experto" como productos separados | Dos experiencias de producto conmutadas por toggle, en vez de una única profundidad adaptativa. | Fragmentación de producto. | `CLAUDE.md` §4. | VERIFICADO (descripción documental); PENDIENTE DE VALIDACIÓN (archivo/mecanismo exacto — ver nota en la matriz) | No replicar el patrón de dos páginas/toggle. |
| LEGACY-AUDIT-053 — Scraping no oficial de ForexFactory | Sin acuerdo ni API documentada. | Riesgo legal/ToS; fragilidad técnica. | Buen juicio de proveedor/dependencia. | VERIFICADO (descripción documental); PENDIENTE DE VALIDACIÓN (código real, `NAME_ONLY`) | No replicar la técnica. |
| LEGACY-AUDIT-054 — CallMeBot como transporte WhatsApp | API no oficial de terceros. | Riesgo de disponibilidad/ToS. | Buen juicio de proveedor/dependencia. | VERIFICADO (descripción documental) | No replicar la técnica. |

---

## 10. Huecos del roadmap (propuestas preliminares)

| Gap propuesto | Prioridad | Estado | Objetivo | Evidencia legacy | Dependencias | Justificación |
|---|---|---|---|---|---|---|
| `FRONTEND-TEST-001` (propuesto, no creado) | Media | **Propuesta preliminar — NO confirmada.** No se declara "hueco confirmado" hasta completar los sublotes 8A–8E (frontend, 83 archivos, especialmente 8E) y contrastar los archivos `*.test.ts(x)` reales (14, ya detectados por nombre pero no leídos) contra las tareas `UX-*` y `F0-AUTH-TEST-001` existentes — es posible que parte de esa necesidad ya esté cubierta por tareas ya nombradas y esta auditoría simplemente no tiene evidencia suficiente para descartarlo. | Establecer infraestructura de tests de componente para el frontend de Freyja 2.0. | LEGACY-AUDIT-019 — roadmap de testing legacy, verificado desactualizado respecto al propio commit que audita. | `FRONTEND-SHELL-001`; Lote 8E de esta auditoría. | El framework legacy (React/Vitest) no es transferible a Angular; el valor real, si lo hay, está en el método de priorización, no en la herramienta — pero esto no puede confirmarse como un hueco real sin antes revisar si `F0-AUTH-TEST-001` o alguna tarea `UX-*` ya lo cubre. |

Este gap sigue siendo una **propuesta preliminar**, no una tarea creada ni un hueco confirmado. No se ha modificado Notion ni el roadmap maestro.

---

## 11. Cobertura por área (exacta)

Reemplaza la tabla cualitativa de la versión anterior. Cada archivo de los 288 pertenece a **exactamente una** de las 21 áreas siguientes (verificación matemática completa en §17: la suma de la columna "Archivos" es exactamente 288). "Íntegros"/"Parciales"/"Solo manifiesto/nombre" son subconjuntos disjuntos de "Archivos"; "Excluidos" es 0 en todas las filas por las razones explicadas en §4.

| Área | Archivos | Íntegros | Parciales | Solo manifiesto/nombre | Excluidos | Cobertura |
|---|---|---|---|---|---|---|
| Documentación y ADR | 10 | 10 | 0 | 0 | 0 | Completa |
| Gobierno/cutover/postmortems | 10 | 9 | 0 | 1 | 0 | Casi completa |
| Dominio | 8 | 0 | 0 | 8 | 0 | Inventariada, no revisada |
| Persistencia y migraciones | 7 | 2 | 0 | 5 | 0 | Parcial |
| Catálogo/POINT1 | 6 | 4 | 1 | 1 | 0 | Mayormente completa |
| Proveedores y datos | 3 | 0 | 0 | 3 | 0 | Inventariada, no revisada |
| Señales y estrategias | 9 | 0 | 0 | 9 | 0 | Inventariada, no revisada (manifiesto) |
| Indicadores | 3 | 0 | 0 | 3 | 0 | Inventariada, no revisada |
| Ciclo de vida | 4 | 0 | 0 | 4 | 0 | Inventariada, no revisada (manifiesto) |
| Brokers y ejecución | 10 | 0 | 0 | 10 | 0 | Inventariada, no revisada |
| Riesgo | 4 | 0 | 0 | 4 | 0 | Inventariada, no revisada (manifiesto) |
| Backtesting | 2 | 0 | 0 | 2 | 0 | Inventariada, no revisada (manifiesto) |
| Autenticación y seguridad | 12 | 0 | 0 | 12 | 0 | Inventariada, no revisada |
| Operación/observabilidad | 18 | 0 | 0 | 18 | 0 | Inventariada, no revisada (1 archivo con evidencia de manifiesto a nivel de endpoint) |
| Frontend/UX | 69 | 0 | 0 | 69 | 0 | Inventariada, no revisada (17 con ficha de manifiesto) |
| Noticias/notificaciones | 6 | 0 | 0 | 6 | 0 | Inventariada, no revisada (1 con ficha de manifiesto) |
| Voz de Freyja | 1 | 0 | 0 | 1 | 0 | Inventariada, no revisada (manifiesto) |
| ML/IA | 2 | 0 | 0 | 2 | 0 | Inventariada, no revisada (manifiesto) |
| Tests backend (flat + `freyja2/`) | 62 | 0 | 0 | 62 | 0 | No revisada |
| Tests frontend | 14 | 0 | 0 | 14 | 0 | No revisada |
| Architecture tests | 28 | 0 | 2 | 26 | 0 | Mínima (2 de 28) |
| **Total** | **288** | **25** | **3** | **260** | **0** | — |

**Nota de honestidad explícita:** "Inventariada, no revisada" significa que se conoce la existencia y ruta del archivo, no su contenido. No debe leerse como "sin necesidad" ni como evidencia de que el área carece de conocimiento legacy útil — significa exactamente lo contrario: que el conocimiento, si existe, todavía no se ha extraído. Privacidad y Comunidad (áreas cualitativas de la versión anterior) no tienen archivos identificables como propios dentro de los 288 — se mantienen como "sin evidencia legacy" y se listan en §12, no en esta tabla cuantitativa.

---

## 12. Riesgos y decisiones pendientes

**Críticos**
- Ninguna estrategia de backup/recuperación existía en el proyecto anterior antes del incidente de purga de datos (LEGACY-AUDIT-029, VERIFICADO como afirmación documental). Freyja 2.0 debe decidir su estrategia de backup de PostgreSQL antes de acumular cualquier dato de valor.
- **91,3% de los archivos legacy no revisados.** Ninguna decisión de arquitectura de Freyja 2.0 debería citar esta auditoría como "conocimiento legacy agotado" hasta cerrar, al menos, los Lotes que cubran las áreas relevantes a esa decisión.

**Altos**
- `/auth/login` sin protección de fuerza bruta era una brecha conocida a la fecha del commit auditado (LEGACY-AUDIT-027) — pero esta auditoría **no puede confirmar** si seguía abierta en commits posteriores del legacy, ni si el código correspondiente (`NAME_ONLY`) implementaba alguna mitigación no documentada.
- **LEGACY-AUDIT-026 corregido:** los adaptadores concretos de broker no tienen ninguna evidencia, ni siquiera del manifiesto (se retracta la cita incorrecta de la versión anterior). Deben tratarse como completamente desconocidos hasta el Lote 5.
- Privacidad, comunidad y (en gran medida) backtesting **no tienen evidencia legacy** en absoluto dentro de lo revisado — no se debe inferir que el legacy "no tenía nada" en estas áreas; simplemente no se ha buscado con suficiente profundidad.

**Medios**
- **Discrepancia sin resolver (nueva en esta corrección):** LEGACY-AUDIT-045 cita `EasyMode.tsx` como un componente de 894 líneas mencionado por el roadmap de testing legacy, pero ese archivo **no aparece** en el listado de 288 rutas del commit `44192410e70975a5f156db81f711e56bee63376b` que esta auditoría audita. Dos explicaciones posibles, ninguna confirmada: (a) el roadmap de testing describe un estado anterior del proyecto y el archivo fue renombrado o eliminado antes de este commit; (b) un error de transcripción en la auditoría original. Debe resolverse en el Lote 8B antes de dar por buena cualquier afirmación sobre `EasyMode.tsx`.
- Varios hallazgos de dominio de alto valor (LEGACY-AUDIT-006, 007, 008, 033, 050, 051) quedan formalmente **PENDIENTE DE MAPEO — requiere contrastar contratos vigentes de POINT2–POINT15**, no asignados a un ID inventado, porque el encargo de esta auditoría no detalló el contenido de esos puntos del roadmap. Se resuelve en el Lote 10. **Se solicita al Arquitecto** indicar a qué punto exacto corresponden, o confirmar que aún no existe un punto asignado para ellos.
- Deriva de contrato entre canales (LEGACY-AUDIT-034) ya ocurrió una vez en legacy — recomienda una única fuente de verdad tipada desde el principio en `POINT1-API`.

**Bajos**
- El origen del capital para el cálculo de tamaño de posición (LEGACY-AUDIT-035) quedó como pregunta abierta en legacy.
- `docs/testing/frontend-testing-roadmap.md` (LEGACY-AUDIT-019) está desactualizado respecto al estado real del mismo commit — no citarlo como estado vigente sin verificación adicional (Lote 8E).

---

## 13. Recomendaciones de secuencia

Sin cambios de fondo respecto a la versión anterior, salvo que ahora cada recomendación remite al lote correspondiente (§15) en vez de presuponer que la consulta documental ya es suficiente:

- `POINT1-DOMAIN`: consultar LEGACY-AUDIT-004/005 (VERIFICADO) — no requiere esperar a un lote, ya que la evidencia es documental completa.
- `POINT1-DB`/`POINT1-SEED`: consultar LEGACY-AUDIT-012/013/014, pero **cerrar primero el Lote 2** (completar la lectura de la migración de siembra y los 12 tests de `freyja2/`) antes de tratar el patrón como validado.
- `SECURITY-BROKER-DESIGN-001`: **no actuar sobre LEGACY-AUDIT-021 a 026 hasta cerrar los Lotes 1 y 5** — toda la evidencia actual es documental o inexistente (026), nunca de código.
- `SAFETY-CONTROL-DESIGN-001`: **no actuar sobre LEGACY-AUDIT-036 a 040 hasta cerrar el Lote 5**; decidir explícitamente la pregunta abierta de LEGACY-AUDIT-035.
- `FREYJA-VOICE-DESIGN-001`: LEGACY-AUDIT-042 (vocabulario) puede consultarse ya (VERIFICADO); LEGACY-AUDIT-041 (motor) espera al Lote 3.
- `F0-AUTH-BACKEND-001`: revisar LEGACY-AUDIT-027/028 **con la salvedad explícita** de que "nunca se cerró" es una inferencia, no un hecho — confirmar contra el Lote 1 y el Lote 9C (test de rate limiting, `test_be_sec_003_rate_limit_and_docs.py`, hoy `NAME_ONLY`).
- `PLATFORM-OPS-DESIGN-001`: incorporar una estrategia de backup motivada por LEGACY-AUDIT-029; no requiere esperar a un lote (la evidencia documental ya es suficiente para motivar la decisión, aunque no para copiar ningún mecanismo legacy concreto).
- `NOTIFICATION-DESIGN-001`: decidir proveedores con acuerdo/API oficial; esperar al Lote 3 para el resto de detalles.
- `FRONTEND-TEST-001` (gap preliminar): decidir con el Arquitecto solo después de cerrar los sublotes 8A–8E, especialmente 8E.

---

## 14. Reclasificación de afirmaciones (hecho / documentación / inferencia)

Requerido explícitamente por la corrección del Arquitecto. Se listan las afirmaciones de mayor impacto de la versión anterior de este documento, reclasificadas:

| Afirmación (versión anterior) | Reclasificación | Explicación |
|---|---|---|
| "esa regla ya fue validada en producción real por el proyecto anterior" (rechazo de permisos de retirada, LEGACY-AUDIT-025) | **Documentación**, no hecho | El README/MANUAL_USUARIO lo afirman; ningún test ni código fue leído o ejecutado por esta auditoría para confirmarlo. Corregido en §6. |
| "el proyecto anterior ya demostró viable [el motor de voz] sin coste de LLM" (LEGACY-AUDIT-041) | **Documentación**, no hecho | Afirmación de ARQUITECTURA.md/MANUAL_USUARIO.md sobre su propio sistema; `freyja_voice.py` nunca fue leído. Corregido en §6. |
| "brechas... nunca cerradas en la vida del proyecto legacy" (LEGACY-AUDIT-027/028) | **Inferencia del auditor**, no hecho | Se dedujo de la ausencia de mención posterior en los documentos leídos, no de revisar el historial de commits ni el código. Corregido en §8, §9, §12. |
| "este prototipo fue construido explícitamente como el punto de partida de esa misma línea de trabajo" (catálogo `freyja2_*`, LEGACY-AUDIT-012/013/014) | **Hecho documentado en el propio código fuente** (los docstrings del código y las migraciones citan literalmente `POINT1-DB-001`/`POINT1-SEED-001`), no inferencia | Es la afirmación mejor fundamentada del documento: proviene de leer directamente el código, no de una descripción de terceros sobre el código. Se mantiene, pero se aclara que "punto de partida" no implica que el esquema esté libre de errores — no se ejecutaron sus tests. |
| "producción real corría sobre PostgreSQL gestionado (Supabase...)" (LEGACY-AUDIT-003) | **Hecho documentado con evidencia técnica citada en la fuente** (un traceback literal de producción, reproducido en el ticket) | Más fuerte que una simple afirmación de prosa, porque el ticket reproduce un mensaje de error real, pero sigue siendo evidencia de segunda mano (el ticket, no el log de producción original) para esta auditoría. |
| "el manifiesto legacy las clasifica REVIEW_BEFORE_REUSE" (adaptadores de broker, LEGACY-AUDIT-026) | **Error corregido — la afirmación era falsa.** | Verificado en esta corrección, releyendo el manifiesto completo: estos 4 archivos no aparecen en él. Se retracta explícitamente en §5, §7 y §12. |
| "2 de 24 Architecture Tests" (metodología, §4 de la versión anterior) | **Error de recuento corregido** | El recuento exacto es 26 archivos `test_architecture_*.py` (28 con `README.md`/`__init__.py`), no 24. Corregido en §4 y §11. |

---

## 15. Plan de auditoría restante (Lotes 1–10)

Cubre exactamente los **260 archivos** sin evidencia directa (48 `MANIFEST_ONLY` + 212 `NAME_ONLY`), sin solapamientos, verificado matemáticamente (§17, contra el apéndice completo de §19). Los 25 `REVIEWED_FULL` + 3 `REVIEWED_PARTIAL` no se reasignan a ningún lote, salvo una advertencia puntual en los Lotes 2 y 9F para *completar* (no repetir) las 3 lecturas parciales.

**Corrección estructural respecto a la versión anterior:** los Lotes 8 y 9 (83 y 88 archivos) se han subdividido en sublotes de máximo 25 archivos cada uno, por ser demasiado grandes para una sola ejecución.

| Lote | Archivos | Tema |
|---|---|---|
| 1 | 13 | Gobierno, ADR, postmortems y seguridad (infraestructura de seguridad no cubierta por los documentos ya leídos) |
| 2 | 14 | Dominio, persistencia y catálogo POINT1 |
| 3 | 10 | Proveedores, datos, noticias y notificaciones |
| 4 | 15 | Señales, estrategias, indicadores y ciclo de vida |
| 5 | 15 | Brokers, ejecución y riesgo |
| 6 | 4 | Backtesting, evaluación cuantitativa y ML |
| 7 | 18 | Backend API, autenticación y operación |
| 8A | 21 | Frontend — configuración, entrada, routing y shell |
| 8B | 12 | Frontend — páginas y navegación |
| 8C | 23 | Frontend — componentes de dominio y dashboard |
| 8D | 13 | Frontend — servicios, hooks y contratos frontend |
| 8E | 14 | Frontend — tests frontend y reconciliación de `FRONTEND-TEST-001` |
| 9A | 18 | Tests de dominio y modelos |
| 9B | 14 | Tests de servicios, estrategias e indicadores |
| 9C | 13 | Tests de brokers, ejecución y seguridad |
| 9D | 6 | Tests de API e integración |
| 9E | 12 | Tests `freyja2` |
| 9F | 25 | Architecture tests y reconciliación de invariantes |
| 10 | 0 (síntesis) | Reconciliación final y mapeo POINT2–POINT15 |
| **Total** | **260** | — |

Verificación de subtotales: Lotes 1–7 = 13+14+10+15+15+4+18 = **89**. Sublotes 8A–8E = 21+12+23+13+14 = **83**. Sublotes 9A–9F = 18+14+13+6+12+25 = **88**. Lote 10 = 0. `89 + 83 + 88 + 0 = 260` ✓, coincide exactamente con `MANIFEST_ONLY (48) + NAME_ONLY (212)`.

### Lote 1 — Gobierno, ADR, postmortems y seguridad

- **Rutas incluidas (13):** `.claude/launch.json`, `.github/workflows/backend-ci.yml`, `.github/workflows/frontend-ci.yml`, `.gitignore`, `backend/.env.example`, `backend/app/models/broker_audit_log.py`, `backend/app/models/trade_audit_log.py`, `backend/app/models/user.py`, `backend/app/schemas/auth.py`, `backend/app/utils/auth.py`, `backend/app/utils/broker_crypto.py`, `backend/app/utils/safe_log.py`, `backend/docs/tickets/be-bug-004-session-audit.md`.
- **Objetivo:** validar directamente (no solo por descripción documental) los mecanismos de seguridad ya citados como candidatos REUSE en LEGACY-AUDIT-021/023/025/046, y confirmar si `be-bug-004-session-audit.md` (no leído aún) añade contexto al incidente de pool.
- **Riesgos:** puede revelar que `safe_log_exc`/`broker_crypto` no cumplen exactamente lo descrito en ARQUITECTURA.md; posible exposición de patrones inseguros que la documentación no menciona.
- **Entregable:** confirmación o corrección de LEGACY-AUDIT-021/022/023/025/046; nuevos hallazgos si el CI legacy revela prácticas de seguridad no documentadas.
- **Dependencias:** ninguna.
- **Criterios de cierre:** los 13 archivos con estado `REVIEWED_FULL` o `REVIEWED_PARTIAL` justificado; cada hallazgo afectado promovido de CANDIDATE a definitivo o mantenido como candidato con motivo explícito.

### Lote 2 — Dominio, persistencia y catálogo POINT1

- **Rutas incluidas (14):** `backend/alembic.ini`, `backend/alembic/README`, `backend/alembic/env.py`, `backend/alembic/script.py.mako`, `backend/app/database.py`, `backend/app/models/__init__.py`, `backend/app/models/user_profile.py`, `backend/app/schemas/user_profile.py`, `docker-compose.yml`, `backend/app/models/signal.py`, `backend/app/models/trade.py`, `backend/app/models/strategy_spec.py`, `backend/app/models/strategy_spec_seed.py`, `backend/app/models/pending_execution.py`.
- **Tarea adicional (no cuenta en el recuento de 260):** completar la lectura de `backend/alembic/versions/a27cf55ab06f_freyja2_seed_canonical_catalog.py` (hoy `REVIEWED_PARTIAL`, ~120 de 858 líneas).
- **Objetivo:** confirmar si `backend/app/database.py` efectivamente usa solo SQLite (LEGACY-AUDIT-002) o si soporta Postgres como sugiere LEGACY-AUDIT-003; validar los campos reales de `Signal`/`Trade`/`PendingExecution` contra la prosa de ARQUITECTURA.md (LEGACY-AUDIT-006); confirmar `strategy_spec.py` contra la ficha del manifiesto (LEGACY-AUDIT-016).
- **Riesgos:** el manifiesto podría estar desactualizado respecto al código real, igual que ya se detectó en el roadmap de testing (LEGACY-AUDIT-019).
- **Entregable:** matriz de campos reales de los 5 modelos de dominio; confirmación de dual-DB o corrección de LEGACY-AUDIT-002.
- **Dependencias:** ninguna.
- **Criterios de cierre:** los 14 archivos con estado final asignado; migración de siembra promovida a `REVIEWED_FULL`.

### Lote 3 — Proveedores, datos, noticias y notificaciones

- **Rutas incluidas (10):** `backend/app/services/news/__init__.py`, `cache.py`, `filter.py`, `models.py`, `provider.py`, `backend/app/services/market_data.py`, `backend/app/services/catalog.py`, `backend/app/utils/notifications.py`, `backend/app/services/freyja_voice.py`, `backend/app/services/ws_manager.py`.
- **Objetivo:** confirmar el mecanismo real de scraping de ForexFactory (LEGACY-AUDIT-047/053), el acoplamiento de `notifications.py` a `strategy_registry` ya advertido por el manifiesto (LEGACY-AUDIT-048), y el contenido real del motor de voz (LEGACY-AUDIT-041).
- **Riesgos:** el código de scraping podría contener endpoints o patrones no descritos en README — revisar con cuidado antes de considerar REWRITE seguro.
- **Entregable:** confirmación/corrección de LEGACY-AUDIT-041/047/048/053.
- **Dependencias:** ninguna.
- **Criterios de cierre:** los 10 archivos con estado final asignado.

### Lote 4 — Señales, estrategias, indicadores y ciclo de vida

- **Rutas incluidas (15):** `backend/app/models/strategy.py`, `backend/app/utils/dates.py`, `backend/app/utils/indicators.py`, `backend/app/utils/signal_normalizer.py`, `backend/app/services/scanner.py`, `signal_service.py`, `strategy.py`, `macd_strategy.py`, `bollinger_strategy.py`, `scalping_strategy.py`, `fibonacci_strategy.py`, `strategy_registry.py`, `strategy_spec_resolver.py`, `signal_outcome.py`, `monitor.py`.
- **Objetivo:** validar los 5 algoritmos de estrategia contra el resumen de README/manifiesto (LEGACY-AUDIT-050), confirmar ausencia o presencia de look-ahead bias, y validar el ADR de `evaluate_trade` (LEGACY-AUDIT-007/033) contra `monitor.py` real.
- **Riesgos:** es el lote con mayor riesgo de encontrar lógica de trading incorrecta o con sesgos temporales — requiere atención cuidadosa dado que `CLAUDE.md` §6 prohíbe explícitamente el look-ahead bias.
- **Entregable:** confirmación/corrección de LEGACY-AUDIT-007/033/050; matriz de indicadores reales usados por cada estrategia.
- **Dependencias:** Lote 2 (para los modelos `Signal`/`Trade` ya validados).
- **Criterios de cierre:** los 15 archivos con estado final asignado; veredicto explícito sobre look-ahead bias por estrategia.

### Lote 5 — Brokers, ejecución y riesgo

- **Rutas incluidas (15):** `backend/app/models/broker_connection.py`, `backend/app/schemas/broker.py`, `backend/app/services/brokers/__init__.py`, `base.py`, `binance_adapter.py`, `bybit_adapter.py`, `coinbase_adapter.py`, `exchange_adapter.py`, `factory.py`, `kraken_adapter.py`, `backend/app/services/executor.py`, `autotrading_guard.py`, `risk_manager.py`, `demo_account.py`, `paper_trading.py`.
- **Objetivo:** este es el lote de mayor prioridad de seguridad — validar directamente el rechazo de permisos de retirada (LEGACY-AUDIT-025), el cifrado de credenciales (LEGACY-AUDIT-023), y las 11 condiciones del guard (LEGACY-AUDIT-036), ninguna de las cuales ha sido confirmada por código hasta ahora. También resuelve por completo LEGACY-AUDIT-026 (adaptadores, hoy sin ninguna evidencia).
- **Riesgos:** alto — es el área donde una afirmación documental incorrecta ("los permisos de retirada se rechazan") tendría el mayor impacto si se asumiera cierta sin verificar.
- **Entregable:** confirmación o corrección explícita, archivo por archivo, de LEGACY-AUDIT-021 a 026 y 036/037.
- **Dependencias:** Lote 1 (seguridad general).
- **Criterios de cierre:** ningún hallazgo de seguridad de broker permanece en estado `CANDIDATE` al cerrar este lote — todos promovidos o rechazados con evidencia de código.

### Lote 6 — Backtesting, evaluación cuantitativa y ML

- **Rutas incluidas (4):** `backend/app/services/ml_filter.py`, `optimizer.py`, `backtest_metrics.py`, `strategy_discoverer.py`.
- **Objetivo:** confirmar si el motor de backtest legacy consideraba comisiones/spread/slippage (pregunta abierta en LEGACY-AUDIT-051); confirmar el estado real de `strategy_discoverer.py` como skeleton (ya sugerido por el manifiesto, LEGACY-AUDIT-049).
- **Riesgos:** bajo volumen de archivos, pero alta relevancia por la regla de `CLAUDE.md` §6 sobre backtests reproducibles con costes.
- **Entregable:** confirmación/corrección de LEGACY-AUDIT-049/051; veredicto explícito sobre metodología de costes del backtest legacy.
- **Dependencias:** Lote 4 (estrategias que se backtestean).
- **Criterios de cierre:** los 4 archivos con estado final asignado.

### Lote 7 — Backend API, autenticación y operación

- **Rutas incluidas (18):** `backend/Dockerfile`, `backend/app/__init__.py`, `config.py`, `backend/app/models/demo_account.py`, `scanner_heartbeat.py`, `backend/app/schemas/__init__.py`, `catalog.py`, `backend/app/services/__init__.py`, `backend/app/utils/__init__.py`, `perf_log.py`, `pool_instrumentation.py`, `trade_audit.py`, `backend/requirements.txt`, `ejemplos_api.py`, `start.bat`, `start.sh`, `vercel.json`, `backend/app/main.py`.
- **Objetivo:** validar `main.py` completo (hoy solo con evidencia a nivel de 15 endpoints vía manifiesto) y confirmar la configuración operativa real (`config.py`, pool, despliegue).
- **Riesgos:** `main.py` es el archivo más grande y central del backend legacy — su ausencia de lectura completa es una de las lagunas más significativas de esta auditoría.
- **Entregable:** inventario completo y verificado de endpoints reales de `main.py`, contrastado contra los 15 ya listados por el manifiesto.
- **Dependencias:** Lotes 2, 4 y 5 (para poder interpretar qué invoca cada endpoint).
- **Criterios de cierre:** `main.py` promovido a `REVIEWED_FULL`; los 18 archivos con estado final asignado.

### Lote 8 — Frontend, UX y tests frontend (83 archivos, subdividido en 8A–8E)

El lote original de 83 archivos se subdivide en 5 sublotes de máximo 25 archivos cada uno, sin solapamientos, cubriendo exactamente los 69 archivos de producción de `frontend/**` más los 14 archivos `*.test.ts(x)`.

#### Lote 8A — Configuración, entrada, routing y shell

- **Cantidad:** 21 archivos.
- **Rutas exactas:** `frontend/.env.example`, `frontend/.gitignore`, `frontend/README.md`, `frontend/eslint.config.js`, `frontend/index.html`, `frontend/package-lock.json`, `frontend/package.json`, `frontend/postcss.config.js`, `frontend/public/favicon.svg`, `frontend/public/icons.svg`, `frontend/src/App.tsx`, `frontend/src/assets/vite.svg`, `frontend/src/index.css`, `frontend/src/main.tsx`, `frontend/src/router.tsx`, `frontend/src/setupTests.ts`, `frontend/tsconfig.app.json`, `frontend/tsconfig.json`, `frontend/tsconfig.node.json`, `frontend/vite.config.ts`, `frontend/vitest.config.ts`.
- **Objetivo:** confirmar el pipeline de build/entrada real (Vite, TypeScript, ESLint, Vitest) y si coincide con lo descrito en `docs/testing/frontend-testing-roadmap.md` (LEGACY-AUDIT-019); confirmar el routing real (`router.tsx`) contra la estructura de rutas descrita en README/MANUAL_USUARIO.
- **Riesgos:** bajo — son mayoritariamente archivos de configuración, no lógica de negocio.
- **Dependencias:** ninguna.
- **Entregable:** confirmación del stack de build real; inventario de rutas reales de `router.tsx`.
- **Criterios de cierre:** los 21 archivos con estado final asignado.

#### Lote 8B — Páginas y navegación

- **Cantidad:** 12 archivos.
- **Rutas exactas:** `frontend/src/pages/Backtest.tsx`, `frontend/src/pages/Dashboard.tsx`, `frontend/src/pages/Help.tsx`, `frontend/src/pages/Login.tsx`, `frontend/src/pages/Onboarding.tsx`, `frontend/src/pages/Optimize.tsx`, `frontend/src/pages/Register.tsx`, `frontend/src/pages/Settings.tsx`, `frontend/src/pages/Signals.tsx`, `frontend/src/pages/Trades.tsx`, `frontend/src/components/RequireAuth.tsx`, `frontend/src/context/AuthContext.tsx`.
- **Objetivo:** resolver la discrepancia de LEGACY-AUDIT-045 (`EasyMode.tsx` no aparece en las 288 rutas — confirmar si `Dashboard.tsx` es en realidad la página que el roadmap de testing legacy llamaba `EasyMode.tsx`, o si el archivo fue eliminado antes de este commit); validar el onboarding real (LEGACY-AUDIT-043) contra el manual de usuario.
- **Riesgos:** alto para la discrepancia `EasyMode.tsx` — es la pieza de evidencia más contradictoria detectada hasta ahora en esta auditoría.
- **Dependencias:** ninguna estricta; se beneficia del Lote 7 (endpoints que estas páginas consumen).
- **Entregable:** resolución explícita de la discrepancia `EasyMode.tsx`; confirmación/corrección de LEGACY-AUDIT-043.
- **Criterios de cierre:** los 12 archivos con estado final asignado; discrepancia `EasyMode.tsx` resuelta con evidencia, no con suposición.

#### Lote 8C — Componentes de dominio y dashboard

- **Cantidad:** 23 archivos.
- **Rutas exactas:** `frontend/src/components/BrokerSection.tsx`, `frontend/src/components/Button.tsx`, `frontend/src/components/EmptyState.tsx`, `frontend/src/components/ErrorBoundary.tsx`, `frontend/src/components/GenerateSignalForm.tsx`, `frontend/src/components/HistoryTable.tsx`, `frontend/src/components/Layout.tsx`, `frontend/src/components/MetricCard.tsx`, `frontend/src/components/OpenTradeModal.tsx`, `frontend/src/components/PositionsTable.tsx`, `frontend/src/components/RiskRewardBar.tsx`, `frontend/src/components/Sidebar.tsx`, `frontend/src/components/SignalsTable.tsx`, `frontend/src/components/StatusDot.tsx`, `frontend/src/components/Topbar.tsx`, `frontend/src/components/TypeBadge.tsx`, `frontend/src/components/dashboard/BrokerResumen.tsx`, `frontend/src/components/dashboard/ConfiguracionRapida.tsx`, `frontend/src/components/dashboard/OperacionesAbiertas.tsx`, `frontend/src/components/dashboard/ResumenFreyja.tsx`, `frontend/src/components/freyja/EstadoDemo.tsx`, `frontend/src/components/freyja/HistorialReciente.tsx`, `frontend/src/components/freyja/OperacionCard.tsx`.
- **Objetivo:** validar el toggle "Modo Fácil"/"Modo Experto" (LEGACY-AUDIT-044) contra el código real de estos componentes, no solo la prosa de ARQUITECTURA.md; confirmar los 17 componentes ya listados con ficha de manifiesto (`LEGACY_UI`).
- **Riesgos:** contiene el mayor volumen de componentes `LEGACY_UI` — riesgo de que el manifiesto (que nunca leyó estos archivos directamente tampoco, solo los clasificó) diverja del código real.
- **Dependencias:** Lote 8B (páginas que ensamblan estos componentes).
- **Entregable:** confirmación/corrección de LEGACY-AUDIT-044; contraste explícito de los 17 componentes `MANIFEST_ONLY` contra su código real.
- **Criterios de cierre:** los 23 archivos con estado final asignado; LEGACY-AUDIT-044 confirmado o corregido con evidencia de código.

#### Lote 8D — Servicios, hooks y contratos frontend

- **Cantidad:** 13 archivos.
- **Rutas exactas:** `frontend/src/config/backendUrl.ts`, `frontend/src/hooks/useCatalog.ts`, `frontend/src/hooks/usePolling.ts`, `frontend/src/hooks/useWebSocket.ts`, `frontend/src/services/api.ts`, `frontend/src/test-utils/catalog.ts`, `frontend/src/types.ts`, `frontend/src/utils/catalog.ts`, `frontend/src/utils/format.ts`, `frontend/src/utils/freyjaFormat.ts`, `frontend/src/utils/mergeRecentSignals.ts`, `frontend/src/utils/metricsScope.ts`, `frontend/src/utils/wsPositionsDispatch.ts`.
- **Objetivo:** validar el contrato tipado real (`types.ts`) contra la deriva de contrato ya documentada en LEGACY-AUDIT-034 (`SignalDTO`); confirmar si `useWebSocket.ts` implementa tiempo real o el polling descrito en LEGACY-AUDIT-052.
- **Riesgos:** medio — `types.ts` es la pieza más directamente relevante para `POINT1-API`, con historial ya conocido de deriva de contrato.
- **Dependencias:** Lote 7 (contrato real de los endpoints backend).
- **Entregable:** confirmación/corrección de LEGACY-AUDIT-034/052 contra el código real del frontend.
- **Criterios de cierre:** los 13 archivos con estado final asignado.

#### Lote 8E — Tests frontend y reconciliación de `FRONTEND-TEST-001`

- **Cantidad:** 14 archivos.
- **Rutas exactas:** `frontend/src/components/EmptyState.test.tsx`, `frontend/src/components/GenerateSignalForm.test.tsx`, `frontend/src/config/backendUrl.test.ts`, `frontend/src/hooks/useCatalog.test.ts`, `frontend/src/hooks/usePolling.test.ts`, `frontend/src/hooks/useWebSocket.test.ts`, `frontend/src/pages/Backtest.test.tsx`, `frontend/src/pages/Onboarding.test.tsx`, `frontend/src/pages/Optimize.test.tsx`, `frontend/src/pages/Settings.test.tsx`, `frontend/src/services/api.test.ts`, `frontend/src/utils/catalog.test.ts`, `frontend/src/utils/mergeRecentSignals.test.ts`, `frontend/src/utils/metricsScope.test.ts`.
- **Objetivo:** leer estos 14 archivos de test reales (hoy `NAME_ONLY`, cuya sola existencia ya contradice la afirmación "cero archivos de test" del roadmap legacy, LEGACY-AUDIT-019) y, con esa evidencia, confirmar o rechazar `FRONTEND-TEST-001` como hueco real, contrastándolo contra `F0-AUTH-TEST-001` y las tareas `UX-*`.
- **Riesgos:** si estos tests ya cubren una parte significativa de lo que `FRONTEND-TEST-001` propondría, el gap debe reducirse de alcance o retirarse, no crearse tal cual está propuesto hoy.
- **Dependencias:** Lotes 8A–8D (para saber qué cubren estos tests).
- **Entregable:** recomendación fundamentada — confirmar, reducir de alcance, o retirar `FRONTEND-TEST-001` de §10.
- **Criterios de cierre:** los 14 archivos con estado final asignado; `FRONTEND-TEST-001` resuelto (confirmado como hueco real, o retirado).

### Lote 9 — Tests backend, integración y architecture tests (88 archivos, subdividido en 9A–9F)

**Recuento exacto y disjunto de `backend/tests/architecture/` (requerido por el Arquitecto, resuelve la ambigüedad de la versión anterior):**

| Concepto | Cantidad | Detalle |
|---|---|---|
| Total de archivos en `backend/tests/architecture/` | 28 | Todo lo que contiene el directorio en el commit auditado. |
| — de los cuales, archivos `test_architecture_*.py` | 26 | Los tests de arquitectura propiamente dichos. |
| — de los cuales, archivos auxiliares (no son tests) | 2 | `README.md` y `__init__.py`. |
| `REVIEWED_PARTIAL` (ya con evidencia parcial) | 2 | `test_architecture_freyja2_legacy_quarantine.py`, `test_architecture_legacy_signal_generation_disabled.py` — ambos dentro de los 26 `test_architecture_*.py`. |
| `NAME_ONLY` (sin ninguna evidencia) | 26 | Los 24 `test_architecture_*.py` restantes + `README.md` + `__init__.py`. |

Verificación: `26 (test_architecture_*.py) + 2 (auxiliares) = 28 (total)` ✓. `2 (REVIEWED_PARTIAL) + 24 (test_architecture_*.py restantes) = 26 (test_architecture_*.py total)` ✓. `24 (test_architecture_*.py NAME_ONLY) + 2 (auxiliares NAME_ONLY) = 26 (NAME_ONLY total)` ✓. `2 (REVIEWED_PARTIAL) + 26 (NAME_ONLY) = 28 (total)` ✓. Estos dos conjuntos — "26 archivos `test_architecture_*.py`" y "26 archivos `NAME_ONLY`" — **no son el mismo conjunto**: el primero excluye `README.md`/`__init__.py` e incluye los 2 `REVIEWED_PARTIAL`; el segundo incluye `README.md`/`__init__.py` y excluye los 2 `REVIEWED_PARTIAL`. Ambos suman 26 por coincidencia aritmética, no por ser idénticos.

- **Qué se completará como tarea adicional (no cuenta en el recuento de 260):** los 2 archivos `REVIEWED_PARTIAL` (`test_architecture_freyja2_legacy_quarantine.py`, `test_architecture_legacy_signal_generation_disabled.py`) se completan de `PARCIAL` a `REVIEWED_FULL` dentro del Lote 9F.
- **Qué pertenece realmente al sublote 9F:** los 24 `test_architecture_*.py` restantes (`NAME_ONLY`) + `__init__.py` de `architecture/` (`NAME_ONLY`) = 25 archivos. `README.md` de `architecture/` se asigna al Lote 9D (ver abajo) para que ningún sublote supere el máximo de 25 archivos.

El lote original de 88 archivos se subdivide en 6 sublotes, sin solapamientos.

#### Lote 9A — Tests de dominio y modelos

- **Cantidad:** 18 archivos.
- **Rutas exactas:** `backend/tests/test_account_balance_contract.py`, `backend/tests/test_catalog_derivation_compat.py`, `backend/tests/test_catalog_endpoint_contract.py`, `backend/tests/test_catalog_registry.py`, `backend/tests/test_database_migrations.py`, `backend/tests/test_database_pool_config.py`, `backend/tests/test_signal_expiration.py`, `backend/tests/test_signal_idempotency.py`, `backend/tests/test_signal_normalizer.py`, `backend/tests/test_signal_outcome.py`, `backend/tests/test_signal_service.py`, `backend/tests/test_signal_strategy_spec_linkage.py`, `backend/tests/test_strategy_registry.py`, `backend/tests/test_strategy_spec_fingerprint.py`, `backend/tests/test_strategy_spec_model.py`, `backend/tests/test_strategy_spec_resolver.py`, `backend/tests/test_strategy_spec_seed.py`, `backend/tests/test_user_profile_timeframe_validation.py`.
- **Objetivo:** validar los campos y contratos reales de `Signal`/`StrategySpec` contra LEGACY-AUDIT-006/016; verificar la cifra "175 tests" (LEGACY-AUDIT-020) contando este subconjunto.
- **Riesgos:** medio — depende de que el Lote 2 (modelos de dominio) ya esté cerrado para interpretar correctamente estos tests.
- **Dependencias:** Lote 2.
- **Entregable:** confirmación/corrección de LEGACY-AUDIT-006/016.
- **Criterios de cierre:** los 18 archivos con estado final asignado.

#### Lote 9B — Tests de servicios, estrategias e indicadores

- **Cantidad:** 14 archivos.
- **Rutas exactas:** `backend/tests/test_autotrading_pipeline.py`, `backend/tests/test_backtest_metrics.py`, `backend/tests/test_backtest_optimize_contract.py`, `backend/tests/test_backtest_strategies_profit_factor.py`, `backend/tests/test_fibonacci_strategy.py`, `backend/tests/test_freyja_mode_sync.py`, `backend/tests/test_freyja_status_contract.py`, `backend/tests/test_freyja_voice.py`, `backend/tests/test_market_data_fallback.py`, `backend/tests/test_monitor_ohlc.py`, `backend/tests/test_monitor_trailing_stop.py`, `backend/tests/test_news_filter.py`, `backend/tests/test_scanner_heartbeat.py`, `backend/tests/test_scanner_signal_context.py`.
- **Objetivo:** validar look-ahead bias y comportamiento real de las estrategias (LEGACY-AUDIT-007/033/050) mediante los tests que las ejercitan; contrastar `test_freyja_voice.py` contra LEGACY-AUDIT-041.
- **Riesgos:** alto — mismo motivo que el Lote 4, del que este sublote es la contraparte de tests.
- **Dependencias:** Lote 4.
- **Entregable:** confirmación/corrección de LEGACY-AUDIT-007/033/041/050 con evidencia de test, no solo de código de producción.
- **Criterios de cierre:** los 14 archivos con estado final asignado.

#### Lote 9C — Tests de brokers, ejecución y seguridad

- **Cantidad:** 13 archivos.
- **Rutas exactas:** `backend/tests/test_auth_short_session.py`, `backend/tests/test_autotrading_guard.py`, `backend/tests/test_be_sec_003_rate_limit_and_docs.py`, `backend/tests/test_broker_endpoints.py`, `backend/tests/test_demo_account.py`, `backend/tests/test_demo_account_reset_endpoint.py`, `backend/tests/test_executor.py`, `backend/tests/test_guard_modes.py`, `backend/tests/test_log_safety.py`, `backend/tests/test_manual_close_endpoint.py`, `backend/tests/test_multi_broker.py`, `backend/tests/test_paper_trading_readonly.py`, `backend/tests/test_risk_manager.py`.
- **Objetivo:** este sublote contiene `test_be_sec_003_rate_limit_and_docs.py` — la pieza de evidencia directa más relevante para resolver si `/auth/login` tenía o no protección de fuerza bruta (LEGACY-AUDIT-027, hoy marcado como inferencia, no hecho); validar el guard de 11 condiciones (LEGACY-AUDIT-036) y el rechazo de permisos de retirada (LEGACY-AUDIT-025) contra sus tests reales.
- **Riesgos:** alto — es el sublote que puede confirmar o desmentir directamente la inferencia de LEGACY-AUDIT-027.
- **Dependencias:** Lote 5.
- **Entregable:** confirmación/corrección de LEGACY-AUDIT-025/027/036 con evidencia de test.
- **Criterios de cierre:** los 13 archivos con estado final asignado; LEGACY-AUDIT-027 reclasificado de "inferencia" a "hecho" o "hecho contrario", según lo que revele `test_be_sec_003_rate_limit_and_docs.py`.

#### Lote 9D — Tests de API e integración

- **Cantidad:** 6 archivos.
- **Rutas exactas:** `backend/tests/__init__.py`, `backend/tests/test_debug_demo_accounts_schema.py`, `backend/tests/test_perf_log.py`, `backend/tests/test_pool_instrumentation.py`, `backend/tests/architecture/README.md`, `test_system.py`.
- **Objetivo:** confirmar el comportamiento de integración de extremo a extremo (`test_system.py`) y la instrumentación operativa (`perf_log`, `pool_instrumentation`) contra LEGACY-AUDIT-003/017; leer `architecture/README.md` como documentación de la propia suite de Architecture Tests, para contextualizar el Lote 9F.
- **Riesgos:** bajo.
- **Dependencias:** Lote 7.
- **Entregable:** confirmación/corrección de LEGACY-AUDIT-003/017 con evidencia de test.
- **Criterios de cierre:** los 6 archivos con estado final asignado.

#### Lote 9E — Tests `freyja2`

- **Cantidad:** 12 archivos.
- **Rutas exactas:** `backend/tests/freyja2/__init__.py`, `backend/tests/freyja2/conftest.py`, `backend/tests/freyja2/test_constraints.py`, `backend/tests/freyja2/test_foreign_keys_inspection.py`, `backend/tests/freyja2/test_migration_lifecycle.py`, `backend/tests/freyja2/test_no_forbidden_fields_and_no_seeds.py`, `backend/tests/freyja2/test_postgres_migration.py`, `backend/tests/freyja2/test_seed_canonical_parity.py`, `backend/tests/freyja2/test_seed_identity_and_offline_sql.py`, `backend/tests/freyja2/test_seed_postgres.py`, `backend/tests/freyja2/test_seed_sql_escaping.py`, `backend/tests/freyja2/test_seed_sqlite.py`.
- **Objetivo:** validar el catálogo canónico (LEGACY-AUDIT-012/013/014) por ejecución de test, no solo por lectura de código — es el único sublote que puede promover esos hallazgos de "VERIFICADO por lectura de código" a "VERIFICADO por test".
- **Riesgos:** bajo — el código ya fue leído en su mayoría (Lote 2 y la pasada original); este sublote es principalmente confirmatorio.
- **Dependencias:** Lote 2.
- **Entregable:** confirmación de LEGACY-AUDIT-012/013/014 con evidencia de test.
- **Criterios de cierre:** los 12 archivos con estado final asignado.

#### Lote 9F — Architecture tests y reconciliación de invariantes

- **Cantidad:** 25 archivos (24 `test_architecture_*.py` + `__init__.py` de `architecture/`), más la tarea adicional de completar los 2 `REVIEWED_PARTIAL` (que no cuentan en los 25).
- **Rutas exactas (25):** `backend/tests/architecture/__init__.py`, `backend/tests/architecture/test_architecture_be_bug_004_pool_availability.py`, `backend/tests/architecture/test_architecture_dashboard_contract.py`, `backend/tests/architecture/test_architecture_evaluate_trade.py`, `backend/tests/architecture/test_architecture_event_loop_not_blocked.py`, `backend/tests/architecture/test_architecture_fibonacci_scanner.py`, `backend/tests/architecture/test_architecture_freyja2_persistence_import_isolation.py`, `backend/tests/architecture/test_architecture_freyja2_persistence_no_operational_fields.py`, `backend/tests/architecture/test_architecture_freyja2_seed_write_targets.py`, `backend/tests/architecture/test_architecture_freyja_status_briefing_pool.py`, `backend/tests/architecture/test_architecture_freyja_status_contract.py`, `backend/tests/architecture/test_architecture_generate_signal_endpoint_e2e.py`, `backend/tests/architecture/test_architecture_init_db_pool_release.py`, `backend/tests/architecture/test_architecture_metrics_contract.py`, `backend/tests/architecture/test_architecture_paper_trading_api.py`, `backend/tests/architecture/test_architecture_scanner_confidence_auto_policy_disabled.py`, `backend/tests/architecture/test_architecture_scanner_confidence_thresholds.py`, `backend/tests/architecture/test_architecture_signal_strategy_spec_creation_points.py`, `backend/tests/architecture/test_architecture_strategy_identity_canonical.py`, `backend/tests/architecture/test_architecture_strategy_spec_invariants.py`, `backend/tests/architecture/test_architecture_strategy_spec_no_registry_dependency.py`, `backend/tests/architecture/test_architecture_utc_daily_boundary.py`, `backend/tests/architecture/test_architecture_ws_auth_first_message.py`, `backend/tests/architecture/test_architecture_ws_positions_disconnect.py`, `backend/tests/architecture/test_architecture_ws_positions_pool.py`.
- **Tarea adicional (no cuenta en los 25):** completar la lectura íntegra de `test_architecture_freyja2_legacy_quarantine.py` y `test_architecture_legacy_signal_generation_disabled.py` (hoy `REVIEWED_PARTIAL`), y generalizar sus invariantes fail-closed al resto de la suite leída en este sublote.
- **Objetivo:** confirmar que los invariantes fail-closed vistos en los 2 tests parciales (allowlist de imports, `LEGACY_SIGNAL_GENERATION_ENABLED=False`) se generalizan al resto de la suite; producir la matriz de invariantes fail-closed completa de `architecture/`.
- **Riesgos:** medio-alto — es el sublote que más puede alterar la confianza de LEGACY-AUDIT-015/018.
- **Dependencias:** Lotes 2, 4, 5 (para interpretar qué invariante prueba cada test).
- **Entregable:** matriz de invariantes fail-closed de `architecture/`; confirmación/corrección de LEGACY-AUDIT-015/018.
- **Criterios de cierre:** los 25 archivos de este sublote con estado final asignado; los 2 `REVIEWED_PARTIAL` promovidos a `REVIEWED_FULL`.

### Lote 10 — Reconciliación final y mapeo POINT2–POINT15

- **Rutas incluidas:** ninguna nueva — es una síntesis de los Lotes 1 a 9, no una lectura adicional de archivos.
- **Objetivo:** (a) contrastar cada afirmación hoy `BASADO EN MANIFIESTO` contra la lectura real obtenida en los Lotes 1–9, promoviendo o corrigiendo cada una; (b) resolver la asignación **PENDIENTE DE MAPEO** de LEGACY-AUDIT-006/007/008/033/050/051 contra el contenido real de `POINT2`–`POINT15`, que esta auditoría nunca tuvo — requiere que el Arquitecto aporte esas descripciones o confirme que deben tratarse como huecos nuevos; (c) producir la versión definitiva (no preliminar) de la matriz de trazabilidad; (d) confirmar o retirar `FRONTEND-TEST-001`.
- **Riesgos:** si los Lotes 1–7 y los sublotes 8A–8E/9A–9F revelan hallazgos contradictorios entre sí (p. ej. un patrón que el manifiesto describe como `REUSABLE_INFRASTRUCTURE` pero que el código real muestra acoplado a lógica legacy), este lote debe documentar el conflicto, no resolverlo por conveniencia.
- **Entregable:** versión 2.0 de este documento, con clasificaciones definitivas (sin sufijo "CANDIDATE") solo donde exista evidencia `VERIFICADO`.
- **Dependencias:** Lotes 1–7 y sublotes 8A–8E, 9A–9F completos.
- **Criterios de cierre:** cero hallazgos en estado `BASADO EN MANIFIESTO` o `NAME_ONLY`-derivado sin resolver; cero asignaciones `PENDIENTE DE MAPEO` sin respuesta del Arquitecto; conclusión binaria real (`AUDITORÍA COMPLETA` o nueva lista de bloqueos).

---

## 16. Declaraciones de seguridad

- No se copió ningún archivo ni fragmento sustancial de código del repositorio legacy hacia Freyja 2.0, ni en la versión anterior ni en esta corrección.
- No se ejecutó ningún código legacy.
- No se leyó ni mostró ningún secreto, credencial, clave, certificado ni contenido de `.env`.
- No se abrió ninguna base de datos legacy.
- No se ejecutó ninguna migración legacy.
- **En esta corrección específicamente: no se leyó ningún archivo nuevo del repositorio legacy vía `git show`.** Los recuentos exactos se obtuvieron de (a) la lista de 288 rutas re-obtenida mediante `git ls-tree -r --name-only HEAD` (metadatos de nombres de archivo, no contenido) y (b) la copia local en caché de `legacy-trading-manifest.json` ya leída en la sesión anterior.
- No se modificó, formateó, instaló ni eliminó nada dentro del repositorio legacy — su estado (`HEAD` `44192410e70975a5f156db81f711e56bee63376b`, 288 archivos rastreados, working tree vaciado) es idéntico al registrado en la versión anterior (ver §18, verificación final).
- No se importó historial de git del repositorio legacy hacia Freyja 2.0.
- No se realizó ningún `cherry-pick` ni operación de fusión entre repositorios.
- No se realizó ningún cambio en Notion como parte de esta tarea ni de esta corrección.
- No se realizó ningún `git add`, commit, branch, push, Pull Request ni cambio en GitHub dentro de Freyja 2.0 como parte de esta tarea ni de esta corrección.
- No se modificó ningún archivo de Freyja 2.0 distinto de `docs/audits/legacy-knowledge-audit.md`.

Búsqueda explícita realizada sobre el contenido de este documento corregido antes de su entrega: rutas `C:\Users\...`, nombres de usuario locales, contraseñas, tokens, claves de API, claves privadas, URLs con credenciales embebidas, contenido de `.env`, fragmentos largos de código, comandos de migración, instrucciones para ejecutar en REAL, recomendaciones de `cherry-pick`, o afirmaciones de "copiar directamente". Resultado: no se detectó ningún elemento de la lista (se preservan las sanitizaciones ya aplicadas en la versión anterior: la URL del remoto GitHub y las dos rutas locales `C:\Users\...`, ninguna reintroducida en esta corrección).

---

## 17. Verificación matemática de cobertura

Esta verificación se realiza contra el **apéndice completo de 288 filas incluido en este mismo documento (§19)**, no contra listas externas ni archivos auxiliares. El apéndice es la única fuente de verdad de qué ruta tiene qué estado y qué lote asignado; esta sección solo confirma, con comandos de solo lectura, que esa tabla es exacta.

**Comandos de solo lectura ejecutados** (ninguno modifica el repositorio legacy ni lee contenido de archivos, solo metadatos de nombres vía `git ls-tree`, y el propio texto del apéndice de este documento):

1. `git -C <ruta-legacy> ls-tree -r --name-only HEAD | wc -l` → **288**, confirma el total de archivos rastreados en el commit auditado.
2. Extracción de las 288 rutas de la primera columna del apéndice (§19) y comparación exacta (`comm -23`/`comm -13`) contra la salida del comando anterior → **sin ausencias, sin sobrantes**.
3. Recuento de rutas del apéndice (`wc -l` sobre las filas de la tabla) → **288**, y verificación de unicidad (`sort` + `uniq -d` sobre la primera columna) → **cero duplicados**.
4. Recuento por columna "Estado actual" del apéndice (`cut` + `sort` + `uniq -c`):

```
REVIEWED_FULL      25
REVIEWED_PARTIAL    3
MANIFEST_ONLY      48
NAME_ONLY         212
EXCLUDED            0
---------------------
TOTAL             288   ✓ coincide con el punto 1
```

5. Recuento por columna "Área" del apéndice → coincide exactamente con la tabla de §11: 10+10+8+7+6+3+9+3+4+10+4+2+12+18+69+6+1+2+62+14+28 = **288** ✓, sin solapamientos ni huecos contra el punto 2.
6. Recuento por columna "Lote asignado" del apéndice (excluyendo las filas con `—`):

```
Lote 1    13   Lote 8A   21   Lote 9A   18
Lote 2    14   Lote 8B   12   Lote 9B   14
Lote 3    10   Lote 8C   23   Lote 9C   13
Lote 4    15   Lote 8D   13   Lote 9D    6
Lote 5    15   Lote 8E   14   Lote 9E   12
Lote 6     4                  Lote 9F   25
Lote 7    18
-------------------------------------------
Subtotal 89   Subtotal 83   Subtotal 88
```

`89 + 83 + 88 = 260` ✓, coincide exactamente con `MANIFEST_ONLY (48) + NAME_ONLY (212) = 260`. Filas con lote `—` (reviewadas): **28** = `REVIEWED_FULL (25) + REVIEWED_PARTIAL (3)`. `260 + 28 + 0 (EXCLUDED) = 288` ✓.
7. Cada sublote 8A–8E y 9A–9F verificado individualmente ≤ 25 archivos: máximo observado = 23 (8C) y 25 (9F) — ambos dentro del límite.

Todas las comprobaciones anteriores son reproducibles releyendo el apéndice de §19 y aplicando los mismos comandos; ninguna depende de un archivo fuera de este documento.

Las rutas exactas de cada estado están enumeradas en su totalidad: las de los 10 lotes en §15; las de `REVIEWED_FULL`/`REVIEWED_PARTIAL`/`MANIFEST_ONLY` como evidencia de cada hallazgo en §5 y §6–9. Dado el volumen del estado `NAME_ONLY` (212 archivos), su listado exhaustivo de rutas se mantiene en los ficheros de trabajo de esta auditoría (no reproducido íntegro en este documento por motivos de longitud) y es reconstruible en cualquier momento por diferencia exacta contra los demás estados, sin ambigüedad.

---

## 18. Estado del repositorio legacy: inicial vs. final de esta corrección

| | Antes de esta corrección | Después de esta corrección |
|---|---|---|
| `HEAD` | `44192410e70975a5f156db81f711e56bee63376b` | `44192410e70975a5f156db81f711e56bee63376b` (sin cambio) |
| Archivos rastreados | 288 | 288 (sin cambio) |
| `git status -sb` (líneas) | 288 (todo `D`, working tree vaciado) | 288 (sin cambio) |
| Archivos con contenido leído por esta auditoría durante esta corrección | — | 0 (solo se reutilizó evidencia ya extraída: lista de rutas y copia local del manifiesto) |

---

## 19. Apéndice completo — los 288 archivos rastreados

Cada una de las 288 rutas rastreadas en `HEAD` (`44192410e70975a5f156db81f711e56bee63376b`) aparece **exactamente una vez** en la tabla siguiente, ordenada alfabéticamente por ruta. Ninguna fila usa comodines ni agrupa rutas. El lote asignado es `—` para los 28 archivos ya revisados (íntegra o parcialmente); para los 260 restantes es el lote o sublote concreto de §15.

| Ruta relativa | Área | Estado actual | Lote asignado | Observación |
|---|---|---|---|---|
| `.claude/launch.json` | Autenticación y seguridad | NAME_ONLY | Lote 1 | — |
| `.github/workflows/backend-ci.yml` | Autenticación y seguridad | NAME_ONLY | Lote 1 | — |
| `.github/workflows/frontend-ci.yml` | Autenticación y seguridad | NAME_ONLY | Lote 1 | — |
| `.gitignore` | Autenticación y seguridad | NAME_ONLY | Lote 1 | — |
| `ARQUITECTURA.md` | Documentación y ADR | REVIEWED_FULL | — | — |
| `MANUAL_USUARIO.md` | Documentación y ADR | REVIEWED_FULL | — | — |
| `README.md` | Documentación y ADR | REVIEWED_FULL | — | — |
| `ROADMAP.md` | Documentación y ADR | REVIEWED_FULL | — | — |
| `backend/.env.example` | Autenticación y seguridad | NAME_ONLY | Lote 1 | — |
| `backend/Dockerfile` | Operación/observabilidad | NAME_ONLY | Lote 7 | — |
| `backend/LEGACY_TRADING.md` | Gobierno/cutover/postmortems | REVIEWED_FULL | — | — |
| `backend/alembic.ini` | Persistencia y migraciones | NAME_ONLY | Lote 2 | — |
| `backend/alembic/README` | Persistencia y migraciones | NAME_ONLY | Lote 2 | — |
| `backend/alembic/env.py` | Persistencia y migraciones | NAME_ONLY | Lote 2 | — |
| `backend/alembic/script.py.mako` | Persistencia y migraciones | NAME_ONLY | Lote 2 | — |
| `backend/alembic/versions/57ce4f19beb7_freyja2_canonical_catalog.py` | Catálogo/POINT1 | REVIEWED_FULL | — | — |
| `backend/alembic/versions/a27cf55ab06f_freyja2_seed_canonical_catalog.py` | Catálogo/POINT1 | REVIEWED_PARTIAL | — | Cabecera/docstring y patrón general leídos (~120 de 858 líneas); resto pendiente en Lote 2 |
| `backend/app/__init__.py` | Operación/observabilidad | NAME_ONLY | Lote 7 | — |
| `backend/app/config.py` | Operación/observabilidad | NAME_ONLY | Lote 7 | — |
| `backend/app/database.py` | Persistencia y migraciones | NAME_ONLY | Lote 2 | — |
| `backend/app/freyja2/__init__.py` | Catálogo/POINT1 | REVIEWED_FULL | — | — |
| `backend/app/freyja2/persistence/__init__.py` | Catálogo/POINT1 | REVIEWED_FULL | — | — |
| `backend/app/freyja2/persistence/base.py` | Persistencia y migraciones | REVIEWED_FULL | — | — |
| `backend/app/freyja2/persistence/identity.py` | Persistencia y migraciones | REVIEWED_FULL | — | — |
| `backend/app/freyja2/persistence/models.py` | Catálogo/POINT1 | REVIEWED_FULL | — | — |
| `backend/app/main.py` | Operación/observabilidad | MANIFEST_ONLY | Lote 7 | MANIFEST_ONLY solo a nivel de 15 endpoints anotados en el manifiesto; archivo completo no leído |
| `backend/app/models/__init__.py` | Dominio | NAME_ONLY | Lote 2 | — |
| `backend/app/models/broker_audit_log.py` | Autenticación y seguridad | NAME_ONLY | Lote 1 | — |
| `backend/app/models/broker_connection.py` | Brokers y ejecución | NAME_ONLY | Lote 5 | — |
| `backend/app/models/demo_account.py` | Operación/observabilidad | NAME_ONLY | Lote 7 | — |
| `backend/app/models/pending_execution.py` | Ciclo de vida | MANIFEST_ONLY | Lote 2 | — |
| `backend/app/models/scanner_heartbeat.py` | Operación/observabilidad | NAME_ONLY | Lote 7 | — |
| `backend/app/models/signal.py` | Dominio | MANIFEST_ONLY | Lote 2 | — |
| `backend/app/models/strategy.py` | Dominio | NAME_ONLY | Lote 4 | — |
| `backend/app/models/strategy_spec.py` | Dominio | MANIFEST_ONLY | Lote 2 | — |
| `backend/app/models/strategy_spec_seed.py` | Dominio | MANIFEST_ONLY | Lote 2 | — |
| `backend/app/models/trade.py` | Dominio | MANIFEST_ONLY | Lote 2 | — |
| `backend/app/models/trade_audit_log.py` | Autenticación y seguridad | NAME_ONLY | Lote 1 | — |
| `backend/app/models/user.py` | Autenticación y seguridad | NAME_ONLY | Lote 1 | — |
| `backend/app/models/user_profile.py` | Dominio | NAME_ONLY | Lote 2 | — |
| `backend/app/schemas/__init__.py` | Operación/observabilidad | NAME_ONLY | Lote 7 | — |
| `backend/app/schemas/auth.py` | Autenticación y seguridad | NAME_ONLY | Lote 1 | — |
| `backend/app/schemas/broker.py` | Brokers y ejecución | NAME_ONLY | Lote 5 | — |
| `backend/app/schemas/catalog.py` | Proveedores y datos | NAME_ONLY | Lote 7 | — |
| `backend/app/schemas/user_profile.py` | Dominio | NAME_ONLY | Lote 2 | — |
| `backend/app/services/__init__.py` | Operación/observabilidad | NAME_ONLY | Lote 7 | — |
| `backend/app/services/autotrading_guard.py` | Riesgo | MANIFEST_ONLY | Lote 5 | — |
| `backend/app/services/backtest_metrics.py` | Backtesting | MANIFEST_ONLY | Lote 6 | — |
| `backend/app/services/bollinger_strategy.py` | Señales y estrategias | MANIFEST_ONLY | Lote 4 | — |
| `backend/app/services/brokers/__init__.py` | Brokers y ejecución | NAME_ONLY | Lote 5 | — |
| `backend/app/services/brokers/base.py` | Brokers y ejecución | NAME_ONLY | Lote 5 | — |
| `backend/app/services/brokers/binance_adapter.py` | Brokers y ejecución | NAME_ONLY | Lote 5 | — |
| `backend/app/services/brokers/bybit_adapter.py` | Brokers y ejecución | NAME_ONLY | Lote 5 | — |
| `backend/app/services/brokers/coinbase_adapter.py` | Brokers y ejecución | NAME_ONLY | Lote 5 | — |
| `backend/app/services/brokers/exchange_adapter.py` | Brokers y ejecución | NAME_ONLY | Lote 5 | — |
| `backend/app/services/brokers/factory.py` | Brokers y ejecución | NAME_ONLY | Lote 5 | — |
| `backend/app/services/brokers/kraken_adapter.py` | Brokers y ejecución | NAME_ONLY | Lote 5 | — |
| `backend/app/services/catalog.py` | Proveedores y datos | MANIFEST_ONLY | Lote 3 | — |
| `backend/app/services/demo_account.py` | Riesgo | MANIFEST_ONLY | Lote 5 | — |
| `backend/app/services/executor.py` | Ciclo de vida | MANIFEST_ONLY | Lote 5 | — |
| `backend/app/services/fibonacci_strategy.py` | Señales y estrategias | MANIFEST_ONLY | Lote 4 | — |
| `backend/app/services/freyja_voice.py` | Voz de Freyja | MANIFEST_ONLY | Lote 3 | — |
| `backend/app/services/macd_strategy.py` | Señales y estrategias | MANIFEST_ONLY | Lote 4 | — |
| `backend/app/services/market_data.py` | Proveedores y datos | MANIFEST_ONLY | Lote 3 | — |
| `backend/app/services/ml_filter.py` | ML/IA | MANIFEST_ONLY | Lote 6 | — |
| `backend/app/services/monitor.py` | Ciclo de vida | MANIFEST_ONLY | Lote 4 | — |
| `backend/app/services/news/__init__.py` | Noticias/notificaciones | NAME_ONLY | Lote 3 | — |
| `backend/app/services/news/cache.py` | Noticias/notificaciones | NAME_ONLY | Lote 3 | — |
| `backend/app/services/news/filter.py` | Noticias/notificaciones | NAME_ONLY | Lote 3 | — |
| `backend/app/services/news/models.py` | Noticias/notificaciones | NAME_ONLY | Lote 3 | — |
| `backend/app/services/news/provider.py` | Noticias/notificaciones | NAME_ONLY | Lote 3 | — |
| `backend/app/services/optimizer.py` | Backtesting | MANIFEST_ONLY | Lote 6 | — |
| `backend/app/services/paper_trading.py` | Riesgo | MANIFEST_ONLY | Lote 5 | — |
| `backend/app/services/risk_manager.py` | Riesgo | MANIFEST_ONLY | Lote 5 | — |
| `backend/app/services/scalping_strategy.py` | Señales y estrategias | MANIFEST_ONLY | Lote 4 | — |
| `backend/app/services/scanner.py` | Señales y estrategias | MANIFEST_ONLY | Lote 4 | — |
| `backend/app/services/signal_outcome.py` | Ciclo de vida | MANIFEST_ONLY | Lote 4 | — |
| `backend/app/services/signal_service.py` | Señales y estrategias | MANIFEST_ONLY | Lote 4 | — |
| `backend/app/services/strategy.py` | Señales y estrategias | MANIFEST_ONLY | Lote 4 | — |
| `backend/app/services/strategy_discoverer.py` | ML/IA | MANIFEST_ONLY | Lote 6 | — |
| `backend/app/services/strategy_registry.py` | Señales y estrategias | MANIFEST_ONLY | Lote 4 | — |
| `backend/app/services/strategy_spec_resolver.py` | Señales y estrategias | MANIFEST_ONLY | Lote 4 | — |
| `backend/app/services/ws_manager.py` | Operación/observabilidad | MANIFEST_ONLY | Lote 3 | — |
| `backend/app/utils/__init__.py` | Operación/observabilidad | NAME_ONLY | Lote 7 | — |
| `backend/app/utils/auth.py` | Autenticación y seguridad | NAME_ONLY | Lote 1 | — |
| `backend/app/utils/broker_crypto.py` | Autenticación y seguridad | NAME_ONLY | Lote 1 | — |
| `backend/app/utils/dates.py` | Indicadores | NAME_ONLY | Lote 4 | — |
| `backend/app/utils/indicators.py` | Indicadores | NAME_ONLY | Lote 4 | — |
| `backend/app/utils/notifications.py` | Noticias/notificaciones | MANIFEST_ONLY | Lote 3 | — |
| `backend/app/utils/perf_log.py` | Operación/observabilidad | NAME_ONLY | Lote 7 | — |
| `backend/app/utils/pool_instrumentation.py` | Operación/observabilidad | NAME_ONLY | Lote 7 | — |
| `backend/app/utils/safe_log.py` | Autenticación y seguridad | NAME_ONLY | Lote 1 | — |
| `backend/app/utils/signal_normalizer.py` | Indicadores | NAME_ONLY | Lote 4 | — |
| `backend/app/utils/trade_audit.py` | Operación/observabilidad | NAME_ONLY | Lote 7 | — |
| `backend/docs/tickets/be-bug-004-session-audit.md` | Gobierno/cutover/postmortems | NAME_ONLY | Lote 1 | — |
| `backend/legacy-trading-manifest.json` | Gobierno/cutover/postmortems | REVIEWED_FULL | — | — |
| `backend/requirements.txt` | Operación/observabilidad | NAME_ONLY | Lote 7 | — |
| `backend/tests/__init__.py` | Tests backend | NAME_ONLY | Lote 9D | — |
| `backend/tests/architecture/README.md` | Architecture tests | NAME_ONLY | Lote 9D | — |
| `backend/tests/architecture/__init__.py` | Architecture tests | NAME_ONLY | Lote 9F | — |
| `backend/tests/architecture/test_architecture_be_bug_004_pool_availability.py` | Architecture tests | NAME_ONLY | Lote 9F | — |
| `backend/tests/architecture/test_architecture_dashboard_contract.py` | Architecture tests | NAME_ONLY | Lote 9F | — |
| `backend/tests/architecture/test_architecture_evaluate_trade.py` | Architecture tests | NAME_ONLY | Lote 9F | — |
| `backend/tests/architecture/test_architecture_event_loop_not_blocked.py` | Architecture tests | NAME_ONLY | Lote 9F | — |
| `backend/tests/architecture/test_architecture_fibonacci_scanner.py` | Architecture tests | NAME_ONLY | Lote 9F | — |
| `backend/tests/architecture/test_architecture_freyja2_legacy_quarantine.py` | Architecture tests | REVIEWED_PARTIAL | — | Docstring + ~80 líneas leídas; resto pendiente en Lote 9F (tarea adicional) |
| `backend/tests/architecture/test_architecture_freyja2_persistence_import_isolation.py` | Architecture tests | NAME_ONLY | Lote 9F | — |
| `backend/tests/architecture/test_architecture_freyja2_persistence_no_operational_fields.py` | Architecture tests | NAME_ONLY | Lote 9F | — |
| `backend/tests/architecture/test_architecture_freyja2_seed_write_targets.py` | Architecture tests | NAME_ONLY | Lote 9F | — |
| `backend/tests/architecture/test_architecture_freyja_status_briefing_pool.py` | Architecture tests | NAME_ONLY | Lote 9F | — |
| `backend/tests/architecture/test_architecture_freyja_status_contract.py` | Architecture tests | NAME_ONLY | Lote 9F | — |
| `backend/tests/architecture/test_architecture_generate_signal_endpoint_e2e.py` | Architecture tests | NAME_ONLY | Lote 9F | — |
| `backend/tests/architecture/test_architecture_init_db_pool_release.py` | Architecture tests | NAME_ONLY | Lote 9F | — |
| `backend/tests/architecture/test_architecture_legacy_signal_generation_disabled.py` | Architecture tests | REVIEWED_PARTIAL | — | Docstring + ~80 líneas leídas; resto pendiente en Lote 9F (tarea adicional) |
| `backend/tests/architecture/test_architecture_metrics_contract.py` | Architecture tests | NAME_ONLY | Lote 9F | — |
| `backend/tests/architecture/test_architecture_paper_trading_api.py` | Architecture tests | NAME_ONLY | Lote 9F | — |
| `backend/tests/architecture/test_architecture_scanner_confidence_auto_policy_disabled.py` | Architecture tests | NAME_ONLY | Lote 9F | — |
| `backend/tests/architecture/test_architecture_scanner_confidence_thresholds.py` | Architecture tests | NAME_ONLY | Lote 9F | — |
| `backend/tests/architecture/test_architecture_signal_strategy_spec_creation_points.py` | Architecture tests | NAME_ONLY | Lote 9F | — |
| `backend/tests/architecture/test_architecture_strategy_identity_canonical.py` | Architecture tests | NAME_ONLY | Lote 9F | — |
| `backend/tests/architecture/test_architecture_strategy_spec_invariants.py` | Architecture tests | NAME_ONLY | Lote 9F | — |
| `backend/tests/architecture/test_architecture_strategy_spec_no_registry_dependency.py` | Architecture tests | NAME_ONLY | Lote 9F | — |
| `backend/tests/architecture/test_architecture_utc_daily_boundary.py` | Architecture tests | NAME_ONLY | Lote 9F | — |
| `backend/tests/architecture/test_architecture_ws_auth_first_message.py` | Architecture tests | NAME_ONLY | Lote 9F | — |
| `backend/tests/architecture/test_architecture_ws_positions_disconnect.py` | Architecture tests | NAME_ONLY | Lote 9F | — |
| `backend/tests/architecture/test_architecture_ws_positions_pool.py` | Architecture tests | NAME_ONLY | Lote 9F | — |
| `backend/tests/freyja2/__init__.py` | Tests backend | NAME_ONLY | Lote 9E | — |
| `backend/tests/freyja2/conftest.py` | Tests backend | NAME_ONLY | Lote 9E | — |
| `backend/tests/freyja2/test_constraints.py` | Tests backend | NAME_ONLY | Lote 9E | — |
| `backend/tests/freyja2/test_foreign_keys_inspection.py` | Tests backend | NAME_ONLY | Lote 9E | — |
| `backend/tests/freyja2/test_migration_lifecycle.py` | Tests backend | NAME_ONLY | Lote 9E | — |
| `backend/tests/freyja2/test_no_forbidden_fields_and_no_seeds.py` | Tests backend | NAME_ONLY | Lote 9E | — |
| `backend/tests/freyja2/test_postgres_migration.py` | Tests backend | NAME_ONLY | Lote 9E | — |
| `backend/tests/freyja2/test_seed_canonical_parity.py` | Tests backend | NAME_ONLY | Lote 9E | — |
| `backend/tests/freyja2/test_seed_identity_and_offline_sql.py` | Tests backend | NAME_ONLY | Lote 9E | — |
| `backend/tests/freyja2/test_seed_postgres.py` | Tests backend | NAME_ONLY | Lote 9E | — |
| `backend/tests/freyja2/test_seed_sql_escaping.py` | Tests backend | NAME_ONLY | Lote 9E | — |
| `backend/tests/freyja2/test_seed_sqlite.py` | Tests backend | NAME_ONLY | Lote 9E | — |
| `backend/tests/test_account_balance_contract.py` | Tests backend | NAME_ONLY | Lote 9A | — |
| `backend/tests/test_auth_short_session.py` | Tests backend | NAME_ONLY | Lote 9C | — |
| `backend/tests/test_autotrading_guard.py` | Tests backend | NAME_ONLY | Lote 9C | — |
| `backend/tests/test_autotrading_pipeline.py` | Tests backend | NAME_ONLY | Lote 9B | — |
| `backend/tests/test_backtest_metrics.py` | Tests backend | NAME_ONLY | Lote 9B | — |
| `backend/tests/test_backtest_optimize_contract.py` | Tests backend | NAME_ONLY | Lote 9B | — |
| `backend/tests/test_backtest_strategies_profit_factor.py` | Tests backend | NAME_ONLY | Lote 9B | — |
| `backend/tests/test_be_sec_003_rate_limit_and_docs.py` | Tests backend | NAME_ONLY | Lote 9C | — |
| `backend/tests/test_broker_endpoints.py` | Tests backend | NAME_ONLY | Lote 9C | — |
| `backend/tests/test_catalog_derivation_compat.py` | Tests backend | NAME_ONLY | Lote 9A | — |
| `backend/tests/test_catalog_endpoint_contract.py` | Tests backend | NAME_ONLY | Lote 9A | — |
| `backend/tests/test_catalog_registry.py` | Tests backend | NAME_ONLY | Lote 9A | — |
| `backend/tests/test_database_migrations.py` | Tests backend | NAME_ONLY | Lote 9A | — |
| `backend/tests/test_database_pool_config.py` | Tests backend | NAME_ONLY | Lote 9A | — |
| `backend/tests/test_debug_demo_accounts_schema.py` | Tests backend | NAME_ONLY | Lote 9D | — |
| `backend/tests/test_demo_account.py` | Tests backend | NAME_ONLY | Lote 9C | — |
| `backend/tests/test_demo_account_reset_endpoint.py` | Tests backend | NAME_ONLY | Lote 9C | — |
| `backend/tests/test_executor.py` | Tests backend | NAME_ONLY | Lote 9C | — |
| `backend/tests/test_fibonacci_strategy.py` | Tests backend | NAME_ONLY | Lote 9B | — |
| `backend/tests/test_freyja_mode_sync.py` | Tests backend | NAME_ONLY | Lote 9B | — |
| `backend/tests/test_freyja_status_contract.py` | Tests backend | NAME_ONLY | Lote 9B | — |
| `backend/tests/test_freyja_voice.py` | Tests backend | NAME_ONLY | Lote 9B | — |
| `backend/tests/test_guard_modes.py` | Tests backend | NAME_ONLY | Lote 9C | — |
| `backend/tests/test_log_safety.py` | Tests backend | NAME_ONLY | Lote 9C | — |
| `backend/tests/test_manual_close_endpoint.py` | Tests backend | NAME_ONLY | Lote 9C | — |
| `backend/tests/test_market_data_fallback.py` | Tests backend | NAME_ONLY | Lote 9B | — |
| `backend/tests/test_monitor_ohlc.py` | Tests backend | NAME_ONLY | Lote 9B | — |
| `backend/tests/test_monitor_trailing_stop.py` | Tests backend | NAME_ONLY | Lote 9B | — |
| `backend/tests/test_multi_broker.py` | Tests backend | NAME_ONLY | Lote 9C | — |
| `backend/tests/test_news_filter.py` | Tests backend | NAME_ONLY | Lote 9B | — |
| `backend/tests/test_paper_trading_readonly.py` | Tests backend | NAME_ONLY | Lote 9C | — |
| `backend/tests/test_perf_log.py` | Tests backend | NAME_ONLY | Lote 9D | — |
| `backend/tests/test_pool_instrumentation.py` | Tests backend | NAME_ONLY | Lote 9D | — |
| `backend/tests/test_risk_manager.py` | Tests backend | NAME_ONLY | Lote 9C | — |
| `backend/tests/test_scanner_heartbeat.py` | Tests backend | NAME_ONLY | Lote 9B | — |
| `backend/tests/test_scanner_signal_context.py` | Tests backend | NAME_ONLY | Lote 9B | — |
| `backend/tests/test_signal_expiration.py` | Tests backend | NAME_ONLY | Lote 9A | — |
| `backend/tests/test_signal_idempotency.py` | Tests backend | NAME_ONLY | Lote 9A | — |
| `backend/tests/test_signal_normalizer.py` | Tests backend | NAME_ONLY | Lote 9A | — |
| `backend/tests/test_signal_outcome.py` | Tests backend | NAME_ONLY | Lote 9A | — |
| `backend/tests/test_signal_service.py` | Tests backend | NAME_ONLY | Lote 9A | — |
| `backend/tests/test_signal_strategy_spec_linkage.py` | Tests backend | NAME_ONLY | Lote 9A | — |
| `backend/tests/test_strategy_registry.py` | Tests backend | NAME_ONLY | Lote 9A | — |
| `backend/tests/test_strategy_spec_fingerprint.py` | Tests backend | NAME_ONLY | Lote 9A | — |
| `backend/tests/test_strategy_spec_model.py` | Tests backend | NAME_ONLY | Lote 9A | — |
| `backend/tests/test_strategy_spec_resolver.py` | Tests backend | NAME_ONLY | Lote 9A | — |
| `backend/tests/test_strategy_spec_seed.py` | Tests backend | NAME_ONLY | Lote 9A | — |
| `backend/tests/test_user_profile_timeframe_validation.py` | Tests backend | NAME_ONLY | Lote 9A | — |
| `docker-compose.yml` | Catálogo/POINT1 | NAME_ONLY | Lote 2 | — |
| `docs/architecture/trading-domain-model.md` | Documentación y ADR | REVIEWED_FULL | — | — |
| `docs/decisions/evaluate-trade-lifecycle.md` | Documentación y ADR | REVIEWED_FULL | — | — |
| `docs/decisions/frontend-feature-availability.md` | Documentación y ADR | REVIEWED_FULL | — | — |
| `docs/decisions/pending-execution-follows-signal-lifecycle.md` | Documentación y ADR | REVIEWED_FULL | — | — |
| `docs/decisions/signal-origin-deferred.md` | Documentación y ADR | REVIEWED_FULL | — | — |
| `docs/postmortems/P0-001-evaluate-trade-timezone.md` | Gobierno/cutover/postmortems | REVIEWED_FULL | — | — |
| `docs/postmortems/P0-3-6-position-sizing-source.md` | Gobierno/cutover/postmortems | REVIEWED_FULL | — | — |
| `docs/postmortems/P0-3-strategy-metrics.md` | Gobierno/cutover/postmortems | REVIEWED_FULL | — | — |
| `docs/testing/frontend-testing-roadmap.md` | Documentación y ADR | REVIEWED_FULL | — | — |
| `docs/tickets/backend-contrato-signaldto-frontend.md` | Gobierno/cutover/postmortems | REVIEWED_FULL | — | — |
| `docs/tickets/backend-expiracion-cancelacion-senales.md` | Gobierno/cutover/postmortems | REVIEWED_FULL | — | — |
| `docs/tickets/backend-pending-execution-flow.md` | Gobierno/cutover/postmortems | REVIEWED_FULL | — | — |
| `docs/tickets/be-bug-004-sqlalchemy-pool-exhaustion.md` | Gobierno/cutover/postmortems | REVIEWED_FULL | — | — |
| `ejemplos_api.py` | Operación/observabilidad | NAME_ONLY | Lote 7 | — |
| `frontend/.env.example` | Frontend/UX | NAME_ONLY | Lote 8A | — |
| `frontend/.gitignore` | Frontend/UX | NAME_ONLY | Lote 8A | — |
| `frontend/README.md` | Frontend/UX | NAME_ONLY | Lote 8A | — |
| `frontend/eslint.config.js` | Frontend/UX | NAME_ONLY | Lote 8A | — |
| `frontend/index.html` | Frontend/UX | NAME_ONLY | Lote 8A | — |
| `frontend/package-lock.json` | Frontend/UX | NAME_ONLY | Lote 8A | — |
| `frontend/package.json` | Frontend/UX | NAME_ONLY | Lote 8A | — |
| `frontend/postcss.config.js` | Frontend/UX | NAME_ONLY | Lote 8A | — |
| `frontend/public/favicon.svg` | Frontend/UX | NAME_ONLY | Lote 8A | — |
| `frontend/public/icons.svg` | Frontend/UX | NAME_ONLY | Lote 8A | — |
| `frontend/src/App.tsx` | Frontend/UX | NAME_ONLY | Lote 8A | — |
| `frontend/src/assets/vite.svg` | Frontend/UX | NAME_ONLY | Lote 8A | — |
| `frontend/src/components/BrokerSection.tsx` | Frontend/UX | NAME_ONLY | Lote 8C | — |
| `frontend/src/components/Button.tsx` | Frontend/UX | NAME_ONLY | Lote 8C | — |
| `frontend/src/components/EmptyState.test.tsx` | Tests frontend | NAME_ONLY | Lote 8E | — |
| `frontend/src/components/EmptyState.tsx` | Frontend/UX | NAME_ONLY | Lote 8C | — |
| `frontend/src/components/ErrorBoundary.tsx` | Frontend/UX | NAME_ONLY | Lote 8C | — |
| `frontend/src/components/GenerateSignalForm.test.tsx` | Tests frontend | NAME_ONLY | Lote 8E | — |
| `frontend/src/components/GenerateSignalForm.tsx` | Frontend/UX | MANIFEST_ONLY | Lote 8C | — |
| `frontend/src/components/HistoryTable.tsx` | Frontend/UX | MANIFEST_ONLY | Lote 8C | — |
| `frontend/src/components/Layout.tsx` | Frontend/UX | NAME_ONLY | Lote 8C | — |
| `frontend/src/components/MetricCard.tsx` | Frontend/UX | NAME_ONLY | Lote 8C | — |
| `frontend/src/components/OpenTradeModal.tsx` | Frontend/UX | MANIFEST_ONLY | Lote 8C | — |
| `frontend/src/components/PositionsTable.tsx` | Frontend/UX | MANIFEST_ONLY | Lote 8C | — |
| `frontend/src/components/RequireAuth.tsx` | Frontend/UX | NAME_ONLY | Lote 8B | — |
| `frontend/src/components/RiskRewardBar.tsx` | Frontend/UX | NAME_ONLY | Lote 8C | — |
| `frontend/src/components/Sidebar.tsx` | Frontend/UX | NAME_ONLY | Lote 8C | — |
| `frontend/src/components/SignalsTable.tsx` | Frontend/UX | MANIFEST_ONLY | Lote 8C | — |
| `frontend/src/components/StatusDot.tsx` | Frontend/UX | NAME_ONLY | Lote 8C | — |
| `frontend/src/components/Topbar.tsx` | Frontend/UX | NAME_ONLY | Lote 8C | — |
| `frontend/src/components/TypeBadge.tsx` | Frontend/UX | NAME_ONLY | Lote 8C | — |
| `frontend/src/components/dashboard/BrokerResumen.tsx` | Frontend/UX | MANIFEST_ONLY | Lote 8C | — |
| `frontend/src/components/dashboard/ConfiguracionRapida.tsx` | Frontend/UX | MANIFEST_ONLY | Lote 8C | — |
| `frontend/src/components/dashboard/OperacionesAbiertas.tsx` | Frontend/UX | MANIFEST_ONLY | Lote 8C | — |
| `frontend/src/components/dashboard/ResumenFreyja.tsx` | Frontend/UX | MANIFEST_ONLY | Lote 8C | — |
| `frontend/src/components/freyja/EstadoDemo.tsx` | Frontend/UX | MANIFEST_ONLY | Lote 8C | — |
| `frontend/src/components/freyja/HistorialReciente.tsx` | Frontend/UX | MANIFEST_ONLY | Lote 8C | — |
| `frontend/src/components/freyja/OperacionCard.tsx` | Frontend/UX | MANIFEST_ONLY | Lote 8C | — |
| `frontend/src/config/backendUrl.test.ts` | Tests frontend | NAME_ONLY | Lote 8E | — |
| `frontend/src/config/backendUrl.ts` | Frontend/UX | NAME_ONLY | Lote 8D | — |
| `frontend/src/context/AuthContext.tsx` | Frontend/UX | NAME_ONLY | Lote 8B | — |
| `frontend/src/hooks/useCatalog.test.ts` | Tests frontend | NAME_ONLY | Lote 8E | — |
| `frontend/src/hooks/useCatalog.ts` | Frontend/UX | NAME_ONLY | Lote 8D | — |
| `frontend/src/hooks/usePolling.test.ts` | Tests frontend | NAME_ONLY | Lote 8E | — |
| `frontend/src/hooks/usePolling.ts` | Frontend/UX | NAME_ONLY | Lote 8D | — |
| `frontend/src/hooks/useWebSocket.test.ts` | Tests frontend | NAME_ONLY | Lote 8E | — |
| `frontend/src/hooks/useWebSocket.ts` | Frontend/UX | NAME_ONLY | Lote 8D | — |
| `frontend/src/index.css` | Frontend/UX | NAME_ONLY | Lote 8A | — |
| `frontend/src/main.tsx` | Frontend/UX | NAME_ONLY | Lote 8A | — |
| `frontend/src/pages/Backtest.test.tsx` | Tests frontend | NAME_ONLY | Lote 8E | — |
| `frontend/src/pages/Backtest.tsx` | Frontend/UX | MANIFEST_ONLY | Lote 8B | — |
| `frontend/src/pages/Dashboard.tsx` | Frontend/UX | MANIFEST_ONLY | Lote 8B | — |
| `frontend/src/pages/Help.tsx` | Frontend/UX | NAME_ONLY | Lote 8B | — |
| `frontend/src/pages/Login.tsx` | Frontend/UX | NAME_ONLY | Lote 8B | — |
| `frontend/src/pages/Onboarding.test.tsx` | Tests frontend | NAME_ONLY | Lote 8E | — |
| `frontend/src/pages/Onboarding.tsx` | Frontend/UX | NAME_ONLY | Lote 8B | — |
| `frontend/src/pages/Optimize.test.tsx` | Tests frontend | NAME_ONLY | Lote 8E | — |
| `frontend/src/pages/Optimize.tsx` | Frontend/UX | MANIFEST_ONLY | Lote 8B | — |
| `frontend/src/pages/Register.tsx` | Frontend/UX | NAME_ONLY | Lote 8B | — |
| `frontend/src/pages/Settings.test.tsx` | Tests frontend | NAME_ONLY | Lote 8E | — |
| `frontend/src/pages/Settings.tsx` | Frontend/UX | NAME_ONLY | Lote 8B | — |
| `frontend/src/pages/Signals.tsx` | Frontend/UX | MANIFEST_ONLY | Lote 8B | — |
| `frontend/src/pages/Trades.tsx` | Frontend/UX | MANIFEST_ONLY | Lote 8B | — |
| `frontend/src/router.tsx` | Frontend/UX | NAME_ONLY | Lote 8A | — |
| `frontend/src/services/api.test.ts` | Tests frontend | NAME_ONLY | Lote 8E | — |
| `frontend/src/services/api.ts` | Frontend/UX | NAME_ONLY | Lote 8D | — |
| `frontend/src/setupTests.ts` | Frontend/UX | NAME_ONLY | Lote 8A | — |
| `frontend/src/test-utils/catalog.ts` | Frontend/UX | NAME_ONLY | Lote 8D | — |
| `frontend/src/types.ts` | Frontend/UX | NAME_ONLY | Lote 8D | — |
| `frontend/src/utils/catalog.test.ts` | Tests frontend | NAME_ONLY | Lote 8E | — |
| `frontend/src/utils/catalog.ts` | Frontend/UX | NAME_ONLY | Lote 8D | — |
| `frontend/src/utils/format.ts` | Frontend/UX | NAME_ONLY | Lote 8D | — |
| `frontend/src/utils/freyjaFormat.ts` | Frontend/UX | NAME_ONLY | Lote 8D | — |
| `frontend/src/utils/mergeRecentSignals.test.ts` | Tests frontend | NAME_ONLY | Lote 8E | — |
| `frontend/src/utils/mergeRecentSignals.ts` | Frontend/UX | NAME_ONLY | Lote 8D | — |
| `frontend/src/utils/metricsScope.test.ts` | Tests frontend | NAME_ONLY | Lote 8E | — |
| `frontend/src/utils/metricsScope.ts` | Frontend/UX | NAME_ONLY | Lote 8D | — |
| `frontend/src/utils/wsPositionsDispatch.ts` | Frontend/UX | NAME_ONLY | Lote 8D | — |
| `frontend/tsconfig.app.json` | Frontend/UX | NAME_ONLY | Lote 8A | — |
| `frontend/tsconfig.json` | Frontend/UX | NAME_ONLY | Lote 8A | — |
| `frontend/tsconfig.node.json` | Frontend/UX | NAME_ONLY | Lote 8A | — |
| `frontend/vite.config.ts` | Frontend/UX | NAME_ONLY | Lote 8A | — |
| `frontend/vitest.config.ts` | Frontend/UX | NAME_ONLY | Lote 8A | — |
| `start.bat` | Operación/observabilidad | NAME_ONLY | Lote 7 | — |
| `start.sh` | Operación/observabilidad | NAME_ONLY | Lote 7 | — |
| `test_system.py` | Tests backend | NAME_ONLY | Lote 9D | — |
| `vercel.json` | Operación/observabilidad | NAME_ONLY | Lote 7 | — |

**Verificación de esta tabla:** 288 filas, 0 rutas duplicadas, 0 rutas ausentes o sobrantes respecto a `git ls-tree -r --name-only HEAD` (ver §17). Totales por estado: `REVIEWED_FULL` 25, `REVIEWED_PARTIAL` 3, `MANIFEST_ONLY` 48, `NAME_ONLY` 212, `EXCLUDED` 0.

---

## Conclusión

**AUDITORÍA PRELIMINAR — REQUIERE REVISIÓN POR LOTES**

No se publica, no se hace commit, no se modifica GitHub ni Notion. El documento queda a la espera de que el Arquitecto autorice la ejecución de los Lotes 1–10 (§15), en el orden propuesto o en el que se determine, antes de que cualquier hallazgo de este documento pueda tratarse como definitivo.
