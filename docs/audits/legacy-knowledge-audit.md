# Auditoría de conocimiento reutilizable — Freyja anterior

> Tarea: `LEGACY-KNOWLEDGE-AUDIT-001`
> Tipo: auditoría estática de conocimiento, de solo lectura. No es una migración.
> Base de Freyja 2.0 auditada: commit `e626e0da4c76c8056f3709af68c7173f3e62dfc0` (rama `main`).
> **Estado de este documento: revisión preliminar corregida tras bloqueo de completitud del Arquitecto.** Sustituye la versión anterior, que presentaba una matriz parcial como si fuera completa.

---

## 1. Resumen ejecutivo

Esta auditoría revisa el repositorio previo de Freyja (`<LEGACY_ROOT>`, en adelante `LEGACY-SRC-01`) como fuente de conocimiento, sin copiar código, sin ejecutar nada y sin modificar ese repositorio.

**Recuento exacto de cobertura (verificado matemáticamente, ver §17). Actualizado tras el cierre de `LEGACY-AUDIT-L02` (Dominio, persistencia y catálogo POINT1 — 14 archivos + finalización de la migración de siembra):**

| Estado | Archivos | % del total |
|---|---|---|
| `REVIEWED_FULL` (lectura completa) | 53 | 18,4% |
| `REVIEWED_PARTIAL` (lectura parcial) | 2 | 0,7% |
| `MANIFEST_ONLY` (solo vía manifiesto de cuarentena legacy, sin lectura directa del archivo) | 43 | 14,9% |
| `NAME_ONLY` (solo existencia registrada por nombre/ruta, sin contenido leído) | 190 | 66,0% |
| `EXCLUDED` (excluido explícitamente) | 0 | 0% |
| **Total rastreado en `HEAD`** | **288** | **100%** |

Es decir: **el 80,9% de los 288 archivos versionados sigue sin haber sido leído directamente** (era 85,8% antes de L02). De ese 80,9%, la gran mayoría (190 de 288) sigue sin ninguna evidencia más allá de su nombre y ruta.

Los **73 hallazgos** de la matriz de trazabilidad (§5) son, en consecuencia, **preliminares** en su mayor parte — con la excepción de los 13 archivos de L01 y los 15 de L02 (14 archivos + la migración de siembra completada), cuyo contenido ya fue leído íntegro y cuyos hallazgos asociados quedan con `Estado de revisión = VERIFICADO` directo. Se derivan de: 53 archivos leídos íntegramente (documentación, ADR, postmortems, tickets, el prototipo de persistencia `freyja2/*`, los 13 archivos de gobierno/seguridad de L01, y ahora los 14 archivos de dominio/persistencia/catálogo de L02 más la migración de siembra completa), 2 archivos leídos parcialmente, y — para una parte no menor de los hallazgos sobre código de dominio aún no auditado — la clasificación que el propio proyecto anterior hizo de sí mismo en `legacy-trading-manifest.json`. Ese manifiesto es una **fuente secundaria producida por el proyecto que se audita**, no una validación independiente; sus afirmaciones se han tratado en esta versión como lo que son — documentación del propio legacy, sujeta a contraste — y no como hechos verificados por esta auditoría.

Los totales de clasificación (**29 candidatos REUSE, 6 candidatos REWRITE, 25 REFERENCE, 13 REJECT** — verificados por recuento directo sobre la matriz, no estimados) corresponden **únicamente al subconjunto de 55 archivos con evidencia examinada** (53 completos + 2 parciales), más un número limitado de afirmaciones basadas en el manifiesto legacy. **No pueden interpretarse como cobertura completa del proyecto legacy**, ni como conclusión definitiva sobre qué del legacy es o no reutilizable: quedan **233 archivos** (43 `MANIFEST_ONLY` + 190 `NAME_ONLY`) sin evidencia directa. `L01` (13 archivos, Gobierno/ADR/postmortems/seguridad) y `L02` (14 archivos, Dominio/persistencia/catálogo POINT1) quedan **completados**; `L03` (Proveedores, datos, noticias y notificaciones, 10 archivos) es el siguiente lote pendiente, siguiendo el orden ya aprobado (§15).

**Nota sobre el recuento histórico de clasificación:** el recuento preliminar anterior a L01 (`22/7/19/6`) contenía una imprecisión heredada de la corrección estructural previa y no había sido verificado por conteo directo sobre la matriz. El recuento real de los 54 hallazgos originales (verificado ahora por patrón exacto) es **27 REUSE CANDIDATE / 6 REWRITE CANDIDATE / 15 REFERENCE / 6 REJECT**. Los 11 hallazgos nuevos de L01 (LEGACY-AUDIT-055 a 065) aportan **+2/+0/+7/+2**, produciendo el total verificado tras L01: **29/6/22/8 = 65**. Los 8 hallazgos nuevos de L02 (LEGACY-AUDIT-066 a 073) aportan **+0/+0/+3/+5**, produciendo el total actual verificado: **29/6/25/13 = 73**. Ninguna de estas adiciones reclasifica un hallazgo preexistente en su categoría (REUSE/REWRITE/REFERENCE/REJECT) — L02 sí actualizó el `Estado de revisión` (no la clasificación) de varios hallazgos existentes al confirmarlos por código real; ver detalle en §5.

**Hallazgo de mayor severidad de L01 (sin resolver por completo hasta Lote 5/7):** `backend/app/models/user.py` declara columnas textuales (`binance_api_key`/`binance_api_secret`/`whatsapp_apikey`) capaces de almacenar credenciales, y el modelo no fuerza cifrado en la capa ORM — contradice directamente el mecanismo de cifrado Fernet (`broker_crypto.py`, también en L01) descrito por la documentación. **L02 aporta evidencia parcial nueva:** `backend/app/database.py` contiene una migración one-time (`_migrate_binance_keys_to_broker_connections()`) que mueve esas columnas, cifradas, a `BrokerConnection` y las vacía en `User` — confirma que la ruta en texto plano es un remanente legacy con salida activa hacia el modelo cifrado, **pero esa migración se salta en silencio (sin error, sin log de advertencia) si `BROKER_ENCRYPTION_KEY` no está configurada**. De existir valores de credenciales en esas columnas, la rama observada permite continuar sin completar su limpieza y podrían permanecer almacenados sin la protección esperada. **L02 no abrió ninguna base ni confirmó la existencia, contenido o vigencia de esos valores** — ver LEGACY-AUDIT-067. **La vigencia real de la ruta de escritura (si algún endpoint todavía escribe en esas columnas) permanece PENDIENTE DE VALIDACIÓN** hasta revisar Lote 7 (`main.py`) — ver LEGACY-AUDIT-060 y §12.

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
| LEGACY-AUDIT-002 | `README.md`, `ARQUITECTURA.md`; **confirmado por código en L02:** `backend/app/database.py`, `docker-compose.yml` | Documentación/Persistencia | La documentación legacy describe SQLite como base de datos de desarrollo por defecto ("no necesitas Docker ni PostgreSQL"). **Resuelto en L02:** el código soporta ambos dialectos deliberadamente (`_is_sqlite = settings.DATABASE_URL.startswith("sqlite")`), pero el propio código documenta explícitamente, en un comentario interno (no solo en docs externos), que "producción es PostgreSQL"; `docker-compose.yml` legacy solo provisiona `postgres:15-alpine` (ninguna imagen SQLite, que no la necesita). El código conserva SQLite como default deliberado de desarrollo/tests y admite PostgreSQL mediante configuración. El propio código y la evidencia documental secundaria de LEGACY-AUDIT-003 declaran PostgreSQL como destino previsto para producción; L02 no verificó ningún despliegue real. | REJECT | VERIFICADO (código real leído íntegro en L02: `database.py`, `docker-compose.yml` — ya no solo el texto del documento) | Ninguno si se entiende como "SQLite es válido solo para dev/tests"; alto si se toma como suficiente para producción. | PLATFORM-DATA-DESIGN-001 | Alta |
| LEGACY-AUDIT-003 | `docs/tickets/be-bug-004-sqlalchemy-pool-exhaustion.md` | Lección aprendida | El ticket documenta, citando un traceback literal, que producción real corría sobre PostgreSQL gestionado (Supabase, pooler modo "session", límite 15 clientes). | REFERENCE | VERIFICADO (el ticket cita el traceback textualmente; no se verificó de forma independiente contra logs de producción reales, a los que esta auditoría nunca tuvo acceso) | Ninguno; es una lección de dimensionado. | PLATFORM-DATA-DESIGN-001 | Alta |
| LEGACY-AUDIT-004 | `docs/architecture/trading-domain-model.md` | Dominio | Modelo conceptual de 5 capas (Mercado, Estilo operativo, Timeframe, Estrategia técnica, Activos) como grafo de dos ramas paralelas, no cadena lineal. | REUSE CANDIDATE | VERIFICADO (contenido del documento de diseño en sí) | Ninguno; es diseño, no código verificado contra una implementación. | POINT1-DOMAIN | Alta (como documento) |
| LEGACY-AUDIT-005 | `docs/architecture/trading-domain-model.md` (§1); `README.md` "Deuda técnica"; **confirmado por código en L02:** `backend/app/models/user_profile.py` | Lección aprendida | `MarketType` mezclaba mercado (spot/futures) con instrumento, según lo describe el propio documento de dominio — antipatrón identificado por el proyecto anterior sobre sí mismo. **Resuelto en L02:** el propio código de `user_profile.py` lo autodocumenta con las mismas palabras ("DEUDA TÉCNICA: este enum mezcla mercado... con instrumento... El nombre correcto sería InstrumentType"). | REFERENCE | VERIFICADO (afirmación del documento, ahora confirmada además por el código real leído íntegro en L02 — coinciden palabra por palabra) | Riesgo de repetir la misma mezcla de ejes conceptuales; ver también LEGACY-AUDIT-071 (misma confusión, extendida a `Signal`/`Trade`). | POINT1-DOMAIN | Alta |
| LEGACY-AUDIT-006 | `ARQUITECTURA.md` (§"Modelos de datos"); **confirmado por código en L02:** `backend/app/models/signal.py`, `trade.py`, `pending_execution.py` (`BrokerConnection` sigue fuera de alcance, Lote 5) | Contrato/Dominio | `ARQUITECTURA.md` describe en prosa los campos de `Signal`, `Trade`, `PendingExecution`, `BrokerConnection`. **Resuelto parcialmente en L02:** los tres modelos leídos íntegros confirman el grueso conceptual de la prosa (estados, precios, timestamps), pero con matices no capturados por el documento: `Signal.market_type`/`profile_type` y `Trade.market_type`/`profile_type` son `String` libre sin `Enum` ni `FK` (ver LEGACY-AUDIT-071); `Trade` usa `Float` para todos los importes monetarios (ver LEGACY-AUDIT-070); el `FK` de `Signal.strategy_spec_id` no está garantizado en todas las rutas de despliegue (ver LEGACY-AUDIT-072). `BrokerConnection` sigue sin leerse (Lote 5). | REUSE CANDIDATE | VERIFICADO (código real de `Signal`/`Trade`/`PendingExecution` leído íntegro en L02); PENDIENTE DE VALIDACIÓN (`BrokerConnection`, Lote 5) | La prosa documental coincide en lo general pero omite matices de tipado que si se replican tal cual violarían `CLAUDE.md` §6 (ver LEGACY-AUDIT-070). | PENDIENTE DE MAPEO — requiere contrastar contratos vigentes de POINT2–POINT15 | Alta (Signal/Trade/PendingExecution) / Baja (BrokerConnection) |
| LEGACY-AUDIT-007 | `docs/decisions/evaluate-trade-lifecycle.md`; **`backend/app/models/trade.py` leído en L02 (sin resolver el ADR)** | Contrato/Dominio | ADR: contrato de cierre de trade — un trade solo cierra una vez, cierre atómico vía `UPDATE` condicionado, fallos aislados por trade. El código que implementa esto (`monitor.py`, `executor.py`) es `MANIFEST_ONLY`, no leído directamente. **L02 no resuelve este ADR:** `trade.py` (ahora `REVIEWED_FULL`) solo declara `status = Column(Enum(TradeStatus)...)` sin ningún mecanismo estructural (constraint, trigger) que impida un doble cierre — la atomicidad, si existe, vive enteramente en el código de servicio (`executor.py`/`monitor.py`, Lote 5), no en el modelo. No se afirma atomicidad a partir del modelo. | REUSE CANDIDATE | VERIFICADO (el ADR en sí); VERIFICADO (que el modelo `Trade` por sí solo NO garantiza cierre único — confirmado en L02); PENDIENTE DE VALIDACIÓN (que `executor.py`/`monitor.py` implementen exactamente lo que el ADR describe) | Ninguno en el ADR; riesgo de desfase ADR↔código no descartable sin leer el código de servicio (Lote 5). | PENDIENTE DE MAPEO — requiere contrastar contratos vigentes de POINT2–POINT15 | Media (ADR) / Baja (código de servicio, aún no leído) |
| LEGACY-AUDIT-008 | `docs/decisions/pending-execution-follows-signal-lifecycle.md`; **`backend/app/models/pending_execution.py` leído en L02** | Contrato/Dominio | ADR: una confirmación pendiente debe depender del ciclo de vida de su señal. El propio ADR declara explícitamente que es "solo documentación" y que la regla **no está implementada todavía** en el código legacy. **Confirmado adicionalmente en L02, a nivel de esquema:** `pending_execution.py` (ahora `REVIEWED_FULL`) tiene su propio `status`/`expires_at` independientes, sin `CHECK`, trigger ni referencia al `status` de `Signal` — nada en el modelo acopla su ciclo de vida al de la señal, consistente con la afirmación del ADR de que la regla sigue sin implementarse (al menos en la capa de modelo/esquema dentro de L02; el `monitor_loop` que sí la podría implementar en la capa de servicio es Lote 4/5, no leído). | REUSE CANDIDATE | VERIFICADO | Ninguno — el ADR mismo aclara que describe una regla *futura*, no código existente; L02 confirma que tampoco existe a nivel de esquema. | PENDIENTE DE MAPEO — requiere contrastar contratos vigentes de POINT2–POINT15 | Alta (como ADR de una regla no implementada; confirmado también por ausencia de acoplamiento en el esquema real) |
| LEGACY-AUDIT-009 | `docs/tickets/backend-expiracion-cancelacion-senales.md`; **confirmado por código en L02:** `backend/app/models/signal.py` | Contrato/Dominio | Máquina de estados de `Signal` (`ACTIVE → EXPIRED / EXECUTED / CANCELLED`) descrita en el ticket; el ticket mismo documenta que la persistencia real de `expires_at` en producción **no llegó a confirmarse** ("prueba decisiva pendiente", bloqueada por caída del servicio). **Resuelto parcialmente en L02:** `signal.py` confirma que `SignalStatus` tiene exactamente esos 4 valores y que `expires_at` **sí es una columna real y persistida** (`DateTime(timezone=True)`, timezone-aware). Sigue sin confirmarse si algún proceso real la **escribe/lee** de forma consistente en producción (el scanner/monitor que la gestionaría es Lote 4/5) — la incertidumbre del ticket se resuelve solo en el nivel de esquema, no en el de comportamiento en ejecución. | REUSE CANDIDATE | VERIFICADO (el ticket documenta su propia incertidumbre; L02 confirma por código que la columna existe y es timezone-aware) | El propio ticket es evidencia de que ni el proyecto legacy pudo confirmar el comportamiento en producción; la existencia de la columna no implica que su ciclo de vida esté correctamente gestionado en ejecución. | UX-STATES-001 | Alta (existencia de la columna) / Media (comportamiento real en ejecución, sin confirmar) |
| LEGACY-AUDIT-010 | `docs/decisions/signal-origin-deferred.md` | Lección aprendida | ADR de decisión diferida: no modelar el origen de una señal hasta que exista un consumidor real. | REFERENCE | VERIFICADO | Ninguno; disciplina de proceso documentada en el propio ADR. | PLATFORM-DATA-DESIGN-001 | Media |
| LEGACY-AUDIT-011 | `docs/decisions/frontend-feature-availability.md` | Contrato/UX | ADR permanente: el frontend nunca inventa estado que el backend no conoce. Es una política declarada, no una verificación de que el frontend legacy la cumple (`frontend/src/**` es casi enteramente `NAME_ONLY`). | REUSE CANDIDATE | VERIFICADO (la política, como texto); PENDIENTE DE VALIDACIÓN (que el frontend legacy la cumpla) | Ninguno como política; sin verificación de cumplimiento real. | UX-STATES-001 | Media |
| LEGACY-AUDIT-012 | `backend/app/freyja2/persistence/models.py`, `backend/alembic/versions/57ce4f19beb7_*.py` | Contrato/Dominio | Esquema de catálogo canónico (6 tablas, constraints de "código normalizado" y "forma exacta" mutuamente excluyente vía `CHECK`). | REUSE CANDIDATE | VERIFICADO (código y migración leídos directamente en su totalidad) | Ninguno; es un patrón de esquema, no datos. No verificado por ejecución de tests (los tests de `freyja2/` son `NAME_ONLY`). | POINT1-DB | Alta (estructura) / Media (que funcione, sin tests ejecutados) |
| LEGACY-AUDIT-013 | `backend/app/freyja2/persistence/identity.py` | Contrato/Dominio | Identidad canónica determinista: `uuid.uuid5(NAMESPACE_URL, identidad_canónica)` a partir de la clave natural. | REUSE CANDIDATE | VERIFICADO (código leído directamente) | Ninguno. | POINT1-SEED | Alta |
| LEGACY-AUDIT-014 | `backend/alembic/versions/a27cf55ab06f_freyja2_seed_canonical_catalog.py` | Contrato/Dominio | Patrón de migración de siembra fail-closed e idempotente (verificación de divergencia antes de `INSERT`, despacho por dialecto). **Completado en L02: las 858 líneas leídas íntegras** (antes solo ~120, cabecera/docstring). Confirmado exactamente lo que el docstring prometía: verificación de divergencia campo a campo antes de cualquier `INSERT` (por UUID y por clave natural, en ambos dialectos), `INSERT ... ON CONFLICT DO NOTHING` para PostgreSQL y comprobación de existencia previa en SQLite, UUIDs materializados como literales (nunca recalculados en tiempo de migración), generación programática de literales SQL desde una única fuente de datos Python (sin duplicación de contenido entre dialectos), y `downgrade()` con `DELETE` acotado exactamente a las filas sembradas, sin `CASCADE`, en orden inverso de dependencias. **Los valores embebidos se presentan como catálogo de referencia declarado, no como observaciones históricas de mercado. La auditoría verificó estáticamente el patrón de identidad, divergencia e idempotencia, pero no revalidó la corrección, vigencia o completitud del contenido del catálogo** (los 12 tests de `freyja2/`, Lote 9E, quedan pendientes). | REUSE CANDIDATE | VERIFICADO (las 858 líneas leídas íntegras en L02 — el patrón implementado coincide exactamente con lo que el docstring describe, no solo se infiere de él; el contenido del catálogo en sí no fue revalidado) | Ninguno nuevo; el propio código documenta que el modo offline (`--sql`) solo está soportado para PostgreSQL, no para SQLite (`NotImplementedError` explícito) — no confundir con soporte universal. | POINT1-SEED | Alta |
| LEGACY-AUDIT-015 | `backend/app/freyja2/__init__.py`, `backend/app/freyja2/persistence/base.py` | Seguridad/Ops | Patrón de cuarentena arquitectónica: base declarativa separada + allowlist explícita de imports, dice el propio módulo que está "verificada por un test de arquitectura" (`test_architecture_freyja2_legacy_quarantine.py`, `REVIEWED_PARTIAL` — el test fue confirmado leyendo sus primeras ~80 líneas, no ejecutado). | REFERENCE | VERIFICADO (el código fuente en sí) / PARCIAL (para la afirmación de que el test lo hace cumplir) | Ninguno directo hoy. | PLATFORM-OPS-DESIGN-001 | Media |
| LEGACY-AUDIT-016 | `backend/legacy-trading-manifest.json` (entrada `app.models.strategy_spec`); **confirmado por código en L02:** `backend/app/models/strategy_spec.py`, `strategy_spec_seed.py` | Dominio | El manifiesto clasifica `StrategySpec` como único módulo `REUSABLE_INFRASTRUCTURE` y aprobado como import permitido. **Confirmado en L02, código leído íntegro (576 + 801 líneas):** identidad determinista de dos niveles (`strategy_id` derivado por `uuid5(slug)`, `spec_id` único por versión), inmutabilidad de contenido y no-reactivación de versiones `DEPRECATED` exigidas por evento ORM `before_update`, fingerprint sha256 determinista del contrato algorítmico, y un seed fail-closed e idempotente (valida fingerprints y claves legacy antes de tocar la BD; nunca sobrescribe, nunca reactiva). El propio código documenta honestamente el límite de este enforcement: solo protege escrituras vía `Session` ORM, no `INSERT` SQL directo — no hay triggers de BD. La clasificación del manifiesto queda confirmada como acertada. | REUSE CANDIDATE | VERIFICADO (código real leído íntegro en L02 — ya no solo la ficha del manifiesto) | Ninguno estructural; el enforcement de inmutabilidad es solo a nivel ORM (documentado explícitamente en el propio código como límite conocido, no un descubrimiento de esta auditoría). | POINT1-DOMAIN | Alta |
| LEGACY-AUDIT-017 | `docs/tickets/be-bug-004-sqlalchemy-pool-exhaustion.md` | Lección aprendida | Disciplina de dimensionado de pool documentada explícitamente por el ticket como regla a mantener. | REFERENCE | VERIFICADO | Ninguno; regla operativa documentada. | PLATFORM-DATA-DESIGN-001 | Alta |
| LEGACY-AUDIT-018 | `backend/tests/architecture/test_architecture_freyja2_legacy_quarantine.py`, `test_architecture_legacy_signal_generation_disabled.py` | Test | Patrón de "Architecture Tests" (invariantes fail-closed verificados con `pytest` contra AST real y BD real). Confirmado solo en los primeros fragmentos de 2 de 26 archivos `test_architecture_*.py` del directorio (recuento exacto y disjunto en el Lote 9F, ver §15); los 24 restantes son `NAME_ONLY`. | REUSE CANDIDATE | PARCIAL | El patrón parece sólido en los 2 archivos vistos; no generalizable automáticamente a los 24 restantes sin leerlos (Lote 9F). | (metodología de testing — sin ID exacto en la lista provista) | Baja |
| LEGACY-AUDIT-019 | `docs/testing/frontend-testing-roadmap.md` | Documentación | Plan de infraestructura de tests frontend por fases. **Inconsistencia verificada directamente por esta auditoría:** el documento afirma "cero archivos `*.test.ts(x)`", pero `git ls-tree` del mismo commit muestra 14 archivos `*.test.tsx`/`*.test.ts` reales y `vitest.config.ts`. | REUSE CANDIDATE (el método de priorización por fases, no el estado "qué existe" que describe) | VERIFICADO (tanto el contenido del documento como la discrepancia con `git ls-tree`, ambos confirmados directamente) | El documento está desactualizado; no usar su sección "qué NO existe" sin verificación adicional (Lote 8E). | ROADMAP GAP → `FRONTEND-TEST-001`, **preliminar, no confirmado** (ver §10) | Media |
| LEGACY-AUDIT-020 | `README.md` (§"Tests") | Documentación | El README declara 175 tests legacy cubriendo ciertas áreas. Ninguno de los archivos de test reales (62 en `backend/tests/*.py` + `freyja2/`, 28 en `architecture/`) fue contado o verificado independientemente — la cifra "175" es una afirmación del propio README, no un recuento propio. | REFERENCE | PENDIENTE DE VALIDACIÓN | La cifra "175" no ha sido verificada; podría estar desactualizada igual que LEGACY-AUDIT-019. | POINT1-TEST | Baja |
| LEGACY-AUDIT-021 | `backend/app/utils/safe_log.py` (leído íntegro en L01; antes `ARQUITECTURA.md` §"Seguridad de logs") | Seguridad/Ops | `safe_log_exc()` nunca registra `str(exc)`, solo `type(exc).__name__` + un `context` filtrado. El filtrado es una lista de denegación **exacta de 13 nombres de clave** (`api_key`, `secret`, `password`, `token`, etc.) aplicada solo a las claves de primer nivel del dict `context` — no inspecciona valores ni estructuras anidadas, así que una clave con nombre distinto (variante, typo) que contenga un secreto no sería redactada. No captura traceback (`exc_info` no se activa). | REUSE CANDIDATE | VERIFICADO (código leído íntegro) | Es una defensa parcial y bien intencionada, no una garantía de seguridad: depende de que cada `caller` nombre sus claves correctamente; no escanea contenido. Ver LEGACY-AUDIT-064. | PLATFORM-OPS-DESIGN-001 | Alta (estructura) / Media (cobertura real, dado el mecanismo exacto-por-nombre) |
| LEGACY-AUDIT-022 | `backend/app/models/broker_audit_log.py`, `backend/app/models/trade_audit_log.py` (leídos íntegros en L01) | Seguridad/Ops | Dos tablas append-only por convención (docstring: "nunca se borran"/"nunca se permite DELETE ni UPDATE desde endpoints"), sin restricción de escritura a nivel de BD/ORM en estos archivos (ninguna revocación de permisos, ningún trigger). `broker_connection_id`/`broker_account_id` son `Integer` sin `ForeignKey` real — decisión deliberada para que la fila de auditoría sobreviva aunque se borre la conexión referenciada. `trade_audit_log.py` documenta explícitamente qué NO contiene (API keys, secrets, passphrases, balance, email, nombre). Timestamps `DateTime(timezone=True)` con `server_default=func.now()` (generados por BD, no por la app). | REUSE CANDIDATE | VERIFICADO (código leído íntegro) | La inmutabilidad es una promesa de convención/docstring, no una restricción técnica exigible en estos dos archivos; sin política de retención/borrado visible aquí — relevante para `COMPLIANCE-PRIVACY-DESIGN-001` (primera evidencia legacy real en el área "Privacidad", antes sin evidencia). Ver LEGACY-AUDIT-059. | SECURITY-BROKER-DESIGN-001 | Alta |
| LEGACY-AUDIT-023 | `backend/app/utils/broker_crypto.py` (leído íntegro en L01; antes `ARQUITECTURA.md` §"Seguridad de claves de broker") | Seguridad/Ops | Confirmado: Fernet (AES-128-CBC + HMAC-SHA256, autenticado) para cifrar/descifrar credenciales de broker. Clave única desde `settings.BROKER_ENCRYPTION_KEY` (env, nunca hardcodeada). Fail-closed explícito: si la clave no está configurada, `_get_fernet()` lanza `RuntimeError` en vez de guardar en claro. Incluye `mask_key()` para mostrar solo los primeros/últimos 4 caracteres en frontend. **Sin mecanismo de rotación ni versionado de clave** — una única clave global para todas las credenciales de todos los usuarios. **Contradicción material detectada:** `backend/app/models/user.py` (también L01) declara `binance_api_key`/`binance_api_secret` como columnas de texto plano, sin evidencia en ese archivo de que pasen por `encrypt_secret()` — ver LEGACY-AUDIT-060. | REUSE CANDIDATE | VERIFICADO (código leído íntegro) | El diseño del propio módulo es sólido (autenticado, fail-closed); el riesgo real está en si `user.py` lo evita — sin resolver hasta Lote 5 (`broker_connection.py`). Clave única global sin rotación: compromiso de esa clave expone todas las credenciales de broker del sistema a la vez. | SECURITY-BROKER-DESIGN-001 | Alta (módulo) / Baja (garantía end-to-end, por la contradicción con `user.py`) |
| LEGACY-AUDIT-024 | `ARQUITECTURA.md` (§"Arquitectura multi-broker") | Seguridad/Ops | Documentación describe `BrokerCapabilities` y `BrokerFactory`. `backend/app/services/brokers/base.py` y `factory.py` son `NAME_ONLY`. | REUSE CANDIDATE | PENDIENTE DE VALIDACIÓN | Ídem. | SECURITY-BROKER-DESIGN-001 | Baja |
| LEGACY-AUDIT-025 | `README.md`, `MANUAL_USUARIO.md` (§7) | Seguridad/Ops | Documentación describe rechazo automático de API Keys con permisos de retirada. El código que lo implementaría (endpoint de test-connection, `backend/app/main.py`, `MANIFEST_ONLY` solo a nivel de endpoint) no fue leído directamente. **Corrección respecto a la versión anterior:** no puede afirmarse "validado en producción real" — es una afirmación de la documentación del proyecto anterior sobre sí mismo, no verificada por esta auditoría (ver §14, reclasificación de afirmaciones). | REUSE CANDIDATE | PENDIENTE DE VALIDACIÓN | Riesgo de que el comportamiento real difiera de lo documentado — precisamente el tipo de riesgo de seguridad que no debe darse por sentado. | SECURITY-BROKER-DESIGN-001 | Baja |
| LEGACY-AUDIT-026 | `backend/app/services/brokers/{binance,coinbase,kraken,bybit}_adapter.py` | Algoritmo | Implementaciones concretas de adaptadores por exchange sobre `ccxt`. **Corrección respecto a la versión anterior:** el documento previo afirmaba que "el manifiesto legacy las clasifica REVIEW_BEFORE_REUSE" — esto es **incorrecto**; se ha verificado ahora, releyendo el manifiesto completo, que estos 4 archivos **no aparecen en absoluto** en `legacy-trading-manifest.json`. Son `NAME_ONLY`, no `MANIFEST_ONLY`. Se retracta la cita anterior al manifiesto. | REWRITE CANDIDATE | PENDIENTE DE VALIDACIÓN | Sin ninguna evidencia directa ni siquiera documental sobre el contenido real de estos 4 archivos — el nivel de confianza más bajo de toda la matriz. | SECURITY-BROKER-DESIGN-001 | Baja |
| LEGACY-AUDIT-027 | `ARQUITECTURA.md` (§"Deuda técnica"); `backend/app/utils/auth.py` (leído íntegro en L01) | Lección aprendida | ARQUITECTURA.md lista `/auth/login` sin protección de fuerza bruta como deuda técnica conocida. **Confirmado ahora por código, no solo por documento:** `backend/app/utils/auth.py` (hashing, tokens, `get_current_user`) no contiene ningún contador de intentos fallidos, bloqueo temporal ni retardo — dentro de ese módulo, la ausencia de protección de fuerza bruta es un hecho observado, no una inferencia. Sigue siendo inferencia que la brecha "nunca se cerró en la vida del proyecto": esta auditoría no revisó el historial de commits posteriores, y una protección a nivel de endpoint (`main.py`, fuera de L01) o de infraestructura no puede descartarse sin leerlo. | REFERENCE | VERIFICADO (que `auth.py`, a este commit, no implementa la protección — hecho de código); INFERENCIA (que "nunca se cerró" en ningún otro lugar ni en commits posteriores) | Vector de ataque conocido si se repite sin verificar si de verdad sigue abierto en Freyja 2.0. | F0-AUTH-BACKEND-001 | Alta (para `auth.py` en este commit) / Media (para la ausencia total en el sistema) |
| LEGACY-AUDIT-028 | `ARQUITECTURA.md` (§"Seguridad general") | Seguridad/Ops | ARQUITECTURA.md documenta `CORS: allow_origins=["*"]` con la nota "cerrar en producción". Mismo matiz que LEGACY-AUDIT-027: no verificado si se cerró después de la fecha del documento. | REJECT | VERIFICADO (la nota del documento); INFERENCIA (que nunca se cerró) | No usar wildcard de CORS en ningún entorno con datos reales, independientemente de si legacy lo cerró o no. | F0-AUTH-BACKEND-001 | Media |
| LEGACY-AUDIT-029 | `backend/LEGACY_TRADING.md` | Lección aprendida | Documento describe, con cifras concretas, un incidente de purga de datos de producción sin backup externo. | REFERENCE | VERIFICADO (el documento lo declara con cifras específicas); no verificado contra ningún registro externo al propio documento | Crítico: ninguna estrategia de backup/recuperación existía antes de este incidente, según el propio documento. | PLATFORM-OPS-DESIGN-001 | Alta (como afirmación documental) |
| LEGACY-AUDIT-030 | `docs/postmortems/P0-3-strategy-metrics.md` | Lección aprendida | El postmortem describe, citando un hash de commit concreto (`843e28e`), que dos motores de cierre de trade coexistieron y que unificar uno rompió silenciosamente la actualización de métricas. | REJECT (duplicar motores) / REFERENCE (la lección) | VERIFICADO (el postmortem lo describe con detalle técnico verificable internamente, incluyendo el hash) | Repetir dos implementaciones "canónicas" simultáneas de la misma responsabilidad. | PLATFORM-OPS-DESIGN-001 | Alta |
| LEGACY-AUDIT-031 | `docs/postmortems/P0-3-strategy-metrics.md` | Lección aprendida | Disciplina: al eliminar código duplicado, verificar explícitamente los efectos secundarios de la ruta eliminada. | REFERENCE | VERIFICADO | Ninguno; disciplina de revisión de refactors. | PLATFORM-OPS-DESIGN-001 | Alta |
| LEGACY-AUDIT-032 | `docs/postmortems/P0-001-evaluate-trade-timezone.md` | Lección aprendida | El postmortem describe, con el mensaje de error literal, un bug de comparación tz-naive vs. tz-aware en pandas. | REFERENCE | VERIFICADO (el postmortem cita el error literal) | Refuerza la regla ya vigente en `CLAUDE.md` §6. | PLATFORM-DATA-DESIGN-001 | Alta |
| LEGACY-AUDIT-033 | `docs/decisions/evaluate-trade-lifecycle.md` (regla 13, ARCH-006); **`backend/app/models/trade.py` leído en L02 (sin resolver la race condition)** | Lección aprendida / Contrato | El ADR narra una race condition real y su fix mediante `UPDATE` condicionado atómico. El código real (`executor.py`) y el test (`test_architecture_evaluate_trade.py`) son `MANIFEST_ONLY`/`NAME_ONLY` — no se leyó ni el fix ni el test que lo prueba. **L02 no resuelve este ADR** (mismo caso que LEGACY-AUDIT-007): `trade.py`, ahora íntegro, no contiene ningún `UPDATE` condicionado ni constraint — el fix, si existe, vive en `executor.py` (Lote 5), no en el modelo. | REUSE CANDIDATE | VERIFICADO (la narrativa del ADR); VERIFICADO (que el modelo no implementa el fix — confirmado en L02); PENDIENTE DE VALIDACIÓN (el código real de `executor.py`, Lote 5) | El patrón descrito es correcto en teoría; no confirmado en la implementación real. | PENDIENTE DE MAPEO — requiere contrastar contratos vigentes de POINT2–POINT15 | Media (ADR) / Baja (código de servicio, aún no leído) |
| LEGACY-AUDIT-034 | `docs/tickets/backend-contrato-signaldto-frontend.md` | Lección aprendida | El ticket documenta una deriva de contrato real y ya observada (bug visible: señales mostradas como SHORT). **No resuelto por L02** (el lado frontend, `frontend/src/types.ts`, es Lote 8D): L02 sí deja fijados los nombres de campo reales del lado backend (`signal.py`: `signal_type`, no `direction`; confirma el propio `_migrate_add_missing_signal_columns()` de `database.py`, que documenta ese mismo rename histórico `direction→signal_type`), útil como referencia para cuando se audite el lado frontend. | REFERENCE | VERIFICADO | Riesgo de repetir nombres de campo divergentes entre canales. | POINT1-API | Alta |
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
| LEGACY-AUDIT-046 | `backend/app/utils/auth.py`, `backend/app/models/user.py` (ambos leídos íntegros en L01; antes `README.md`/`ARQUITECTURA.md`) | Seguridad/Ops | Confirmado: JWT (HS256, vía `python-jose`) con claims mínimos (`sub`+`exp` únicamente, sin email/roles embebidos). Hashing de contraseña con `passlib` + `bcrypt`. `get_current_user` falla cerrado ante token inválido o `user.is_active=False`, con mensaje de error genérico (sin filtrar si el fallo es de email o de contraseña). Expiración configurable (`ACCESS_TOKEN_EXPIRE_MINUTES`, 10080 min/7 días en `.env.example`). **No se observa un mecanismo de revocación o blacklist dentro de `auth.py`** — un JWT robado permanece válido hasta su expiración natural dentro de ese módulo; la protección efectiva del sistema permanece PENDIENTE DE VALIDACIÓN hasta revisar endpoints, middleware y tests en Lote 7/Lote 9C/Lote 9D. Auditoría de sesión real: `LOGIN_SUCCESS`/`LOGIN_FAILED`/`LOGOUT` sí existen como valores de `AuditAction` en `broker_audit_log.py`, confirmando la tabla append-only descrita documentalmente. | REUSE CANDIDATE | VERIFICADO (código leído íntegro) | Ausencia de revocación en `auth.py` + expiración larga por defecto = ventana de exposición amplia dentro de ese módulo si un token se compromete; alcance en el resto del sistema sin confirmar. Ver LEGACY-AUDIT-062. | F0-AUTH-DESIGN-001 | Alta |
| LEGACY-AUDIT-047 | `README.md`, `ARQUITECTURA.md` | Algoritmo | Documentación describe filtro de noticias vía scraping de ForexFactory. `backend/app/services/news/*` es `NAME_ONLY`. | REWRITE CANDIDATE | PENDIENTE DE VALIDACIÓN | Ver LEGACY-AUDIT-053. | NOTIFICATION-DESIGN-001 | Baja |
| LEGACY-AUDIT-048 | `README.md` (§"Variables de entorno") | Algoritmo/Ops | Documentación describe notificaciones vía Discord y WhatsApp (CallMeBot). `backend/app/utils/notifications.py` es `MANIFEST_ONLY` (el manifiesto advierte que está acoplado a `strategy_registry` y necesita desacoplarse antes de reutilizarse). | REWRITE CANDIDATE | BASADO EN MANIFIESTO | Ver LEGACY-AUDIT-054. | NOTIFICATION-DESIGN-001 | Baja |
| LEGACY-AUDIT-049 | `ARQUITECTURA.md` (§"Deuda técnica"); manifiesto | Producto/IA | El manifiesto cita textualmente el docstring de `strategy_discoverer.py`, que se autodeclara "SKELETON" sin implementación real. | REFERENCE | BASADO EN MANIFIESTO (que a su vez cita el docstring real del archivo — evidencia indirecta pero de razonable calidad) | Ninguno; es una aspiración sin implementación. | AI-LLM-EVALUATION-001 | Media |
| LEGACY-AUDIT-050 | `README.md` (§"Estrategias"); manifiesto | Algoritmo | Documentación y manifiesto describen 5 estrategias técnicas legacy (RSI+EMA, MACD+Volumen, Bollinger, Scalping, Fibonacci). Ningún archivo de estrategia (`bollinger_strategy.py`, etc.) fue leído directamente — todos son `MANIFEST_ONLY`. | REWRITE CANDIDATE | BASADO EN MANIFIESTO | Ninguna verificación de que el cálculo de indicadores evite look-ahead bias (`CLAUDE.md` §6) — no se puede confirmar sin leer el código. | PENDIENTE DE MAPEO — requiere contrastar contratos vigentes de POINT2–POINT15 | Baja |
| LEGACY-AUDIT-051 | `ROADMAP.md` (v0.1) | Algoritmo | Mención breve de backtesting histórico desde la v0.1; sin ningún detalle de metodología en las fuentes leídas. | REWRITE CANDIDATE | VERIFICADO (que el documento lo menciona así de brevemente, sin más detalle) | Sin evidencia de que el backtest legacy considerara comisiones/spread/slippage. | PENDIENTE DE MAPEO — requiere contrastar contratos vigentes de POINT2–POINT15 | Baja |
| LEGACY-AUDIT-052 | `ARQUITECTURA.md` (§"Deuda técnica") | Algoritmo/UX | Documentación declara el WebSocket de posiciones como polling de 5s, no tiempo real verdadero. | REWRITE CANDIDATE | VERIFICADO (declaración del propio documento) | Ninguno; es una capacidad pendiente según la fuente. | UX-DASHBOARD-001 | Media |
| LEGACY-AUDIT-053 | `README.md`, `ARQUITECTURA.md` (filtro de noticias) | Seguridad/Ops | Documentación describe scraping no oficial de ForexFactory. `backend/app/services/news/provider.py` es `NAME_ONLY` — no se confirmó el mecanismo real, solo la descripción documental. | REJECT | VERIFICADO (la descripción documental); PENDIENTE DE VALIDACIÓN (el código real) | Riesgo legal/ToS y de fragilidad técnica, según lo descrito. | NOTIFICATION-DESIGN-001 | Media |
| LEGACY-AUDIT-054 | `README.md` (notificaciones WhatsApp) | Seguridad/Ops | Documentación describe CallMeBot como transporte de WhatsApp. | REJECT | VERIFICADO (la descripción documental) | Riesgo de disponibilidad/ToS, según lo descrito. | NOTIFICATION-DESIGN-001 | Media |
| LEGACY-AUDIT-055 | `.claude/launch.json` | Seguridad/Ops | Configuración de lanzamiento local para frontend (`npm run dev`, comando reproducible) y backend (ejecutable de un entorno virtual referenciado por una ruta absoluta específica de la máquina/usuario de desarrollo original — no reproducida aquí por ser una ruta personal). No contiene secretos ni argumentos sensibles. | REJECT | VERIFICADO (código leído íntegro) | Ninguno de seguridad; el archivo no es reutilizable tal cual por depender de una ruta de máquina concreta — cualquier equivalente en Freyja 2.0 debe usar comandos relativos/portables, no rutas absolutas de intérprete. | (sin tarea vigente específica — configuración de desarrollo local, no roadmap) | Alta |
| LEGACY-AUDIT-056 | `.github/workflows/backend-ci.yml`, `.github/workflows/frontend-ci.yml` | Seguridad/Ops | Dos workflows separados, disparados por `paths:` (solo cuando cambia `backend/**`/`frontend/**`), a diferencia del workflow único de Freyja 2.0 que siempre ejecuta ambos jobs. Acciones referenciadas por **tag flotante** (`@v7`, `@v5`, `@v6`), no por SHA — a diferencia de la CI vigente de Freyja 2.0, que sí fija SHA de 40 caracteres. Permisos mínimos (`contents: read`) en ambos. Sin `continue-on-error`, sin `\|\| true`, sin pasos que silencien fallos. Sin `pull_request_target`. Credenciales de Postgres de test explícitamente comentadas como no-reales y efímeras (mismo patrón que la CI actual de Freyja 2.0). Backend instala con `pip install -r requirements.txt` (sin lockfile); frontend usa `npm ci` (determinista, mismo patrón que Freyja 2.0). | REFERENCE | VERIFICADO (código leído íntegro; contrastado explícitamente contra `.github/workflows/ci.yml` vigente de Freyja 2.0) | Ninguno directo — es evidencia de que la decisión ya tomada en `F0-CI-001` (SHA-pinning) mejora sobre la práctica legacy, no un patrón a heredar. El particionado por `paths:` es una idea de eficiencia de CI, no una necesidad de seguridad. | PLATFORM-OPS-DESIGN-001 | Alta |
| LEGACY-AUDIT-057 | `.gitignore` | Documentación | Excluye correctamente secretos (`.env`, `*.secret`, `*.pem`, `*.key`), bases de datos (`*.db`, `*.sqlite*`), entornos virtuales, `node_modules/`, cachés y logs. Sin excepciones (`!patrón`) que reintroduzcan algo excluido. No oculta código fuente ni nada que debiera auditarse. | REFERENCE | VERIFICADO (código leído íntegro) | Ninguno; higiene de repositorio sólida y sin patrones peligrosos. | PLATFORM-OPS-DESIGN-001 | Alta |
| LEGACY-AUDIT-058 | `backend/.env.example` | Seguridad/Ops | Todos los valores son placeholders o están vacíos (`SECRET_KEY=cambia-esto-...`, `ANTHROPIC_API_KEY=`, `BROKER_ENCRYPTION_KEY=`) — ningún secreto real. Distingue lo obligatorio para trading real (`BROKER_ENCRYPTION_KEY`, con advertencia "NUNCA subir este valor") de lo opcional. **Contradicción con LEGACY-AUDIT-041 detectada:** este archivo declara `ANTHROPIC_API_KEY` y `FREYJA_MODEL=claude-haiku-4-5-20251001` para "Voz de Freyja" — un modo con LLM de pago — mientras que ARQUITECTURA.md/MANUAL_USUARIO.md (fuente de LEGACY-AUDIT-041) describen ese motor como "rule-based, sin LLM". Ambas cosas pueden ser ciertas si es un modo opcional no documentado en los textos leídos, pero no puede darse por sentado que el motor sea siempre sin LLM. Inconsistencia interna menor: el comentario dice que `/docs` está "cerrado por defecto (ver config.py)" pero el valor literal es `ENABLE_API_DOCS=true`. Sin variables de CORS ni de base de datos distinta de SQLite. | REFERENCE | VERIFICADO (código leído íntegro; valores no reproducidos, solo estructura) | Ninguno de exposición (sin secretos reales); riesgo documental — no asumir "sin LLM" como universalmente cierto para el motor de voz sin contrastar el código real (`freyja_voice.py`, Lote 3). | AI-LLM-EVALUATION-001 | Media |
| LEGACY-AUDIT-059 | `backend/app/models/broker_audit_log.py`, `backend/app/models/trade_audit_log.py` | Contrato/Dominio | Patrón deliberado: `broker_connection_id`/`broker_account_id`/`signal_id`/`trade_id` se guardan como `Integer` simple, **sin `ForeignKey`**, para que la fila de auditoría sobreviva aunque la entidad referenciada se borre — prioriza integridad del rastro de auditoría sobre integridad referencial estricta. | REUSE CANDIDATE | VERIFICADO (código leído íntegro) | Ninguno; es un patrón de diseño deliberado y documentado en el propio código. | SECURITY-BROKER-DESIGN-001 | Alta |
| LEGACY-AUDIT-060 | `backend/app/models/user.py`; **evidencia adicional en L02:** `backend/app/database.py` | Seguridad/Ops | **Hallazgo crítico:** el modelo `User` declara `binance_api_key`, `binance_api_secret` y `whatsapp_apikey` como columnas `String` de texto plano (`Column(String(200), nullable=True)`), sin ninguna referencia a `encrypt_secret()`/`broker_crypto.py` en este archivo. Contradice directamente el mecanismo de cifrado Fernet descrito por la documentación y confirmado en `broker_crypto.py` (LEGACY-AUDIT-023). **Evidencia nueva de L02:** `database.py` contiene `_migrate_binance_keys_to_broker_connections()`, invocada en cada `init_db()`, que busca usuarios con `binance_api_key` no vacío, los cifra vía `encrypt_secret()` hacia un `BrokerConnection` nuevo, y vacía las columnas legacy del `User` — confirma que la ruta en texto plano es un remanente legacy con una salida activa (no simplemente código muerto), pero esa salida **se salta en silencio si `BROKER_ENCRYPTION_KEY` no está configurada** (sin error, sin log). De existir valores de credenciales en esas columnas, la rama observada permite continuar sin completar su limpieza y podrían permanecer almacenados sin la protección esperada; L02 no abrió ninguna base ni confirmó la existencia, contenido o vigencia de esos valores — ver LEGACY-AUDIT-067. Sigue sin poder determinarse desde L01/L02 si algún endpoint (`main.py`, Lote 7) todavía **escribe** en esas columnas hoy, o si la migración es puramente de limpieza sobre datos históricos. `backend/app/models/broker_connection.py` (Lote 5) sigue sin leerse. | REJECT | VERIFICADO (código leído íntegro en L01 y L02; la resolución de "ruta de escritura vigente vs. solo histórica" queda pendiente del Lote 7) | Alto: si esta ruta estuviera activa, expondría credenciales de broker en texto plano en la base de datos; la migración de limpieza no es fail-closed (se salta en silencio sin clave de cifrado). No copiar este patrón bajo ninguna circunstancia. | SECURITY-BROKER-DESIGN-001 | Alta (el hecho de la columna en texto plano y la existencia de la migración de limpieza) / Baja (si hay escritura activa en producción hoy, sin resolver) |
| LEGACY-AUDIT-061 | `backend/app/schemas/auth.py` | Contrato/UX | `UserOut` (el schema de salida pública) declara explícitamente sus campos y **excluye** `hashed_password`, `binance_api_key`, `binance_api_secret` y `whatsapp_apikey` — ninguno de los campos sensibles del modelo `User` se serializa por accidente. Validación de contraseña: longitud mínima 8, sin regla de complejidad adicional. Validación de email: comprobación simple de `"@"` y `"."`, no una validación RFC completa. | REUSE CANDIDATE | VERIFICADO (código leído íntegro) | Ninguno; patrón de schema de salida explícito y seguro. La ausencia de reglas de complejidad de contraseña es una decisión de producto a tomar deliberadamente en `F0-AUTH-BACKEND-001`, no un defecto en sí. | F0-AUTH-DESIGN-001 | Alta |
| LEGACY-AUDIT-062 | `backend/app/utils/auth.py` | Seguridad/Ops | No existe ningún mecanismo de revocación o lista negra de tokens JWT en este módulo — un token robado permanece válido hasta su expiración natural (por defecto 7 días, según `.env.example`). Tampoco hay `jti`/nonce de un solo uso. | REFERENCE | VERIFICADO (ausencia confirmada por lectura íntegra del módulo) | Ventana de exposición amplia ante un token comprometido; decisión de diseño a tomar explícitamente en `F0-AUTH-BACKEND-001`/`SAFETY-CONTROL-DESIGN-001` (revocación, tokens de corta duración + refresh, o ambos). | F0-AUTH-BACKEND-001 | Alta |
| LEGACY-AUDIT-063 | `backend/app/utils/broker_crypto.py` | Seguridad/Ops | Sin mecanismo de rotación ni versionado de `BROKER_ENCRYPTION_KEY` — una única clave global cifra las credenciales de broker de todos los usuarios; no hay campo de versión de clave ni ruta de re-cifrado gradual. | REFERENCE | VERIFICADO (ausencia confirmada por lectura íntegra del módulo) | Si la clave global se compromete o necesita rotarse, no existe un mecanismo incremental — habría que re-cifrar todo de una vez. Relevante para `SECURITY-BROKER-DESIGN-001`. | SECURITY-BROKER-DESIGN-001 | Alta |
| LEGACY-AUDIT-064 | `backend/app/utils/safe_log.py` | Seguridad/Ops | La redacción de `safe_log_exc()` compara claves de `context` contra una lista fija de 13 nombres exactos (`k.lower() in _FORBIDDEN_CONTEXT_KEYS`) — no es un escaneo de contenido ni cubre variantes de nombre, claves anidadas, o el propio mensaje de la excepción (que de todas formas nunca se registra, por diseño). No presenta esto como prueba de seguridad completa: es una defensa de primera capa, dependiente de que cada `caller` nombre correctamente sus claves. | REFERENCE | VERIFICADO (código leído íntegro) | Falso negativo posible si un `caller` usa un nombre de clave no listado para un valor sensible, o anida el valor sensible dentro de otra estructura. | PLATFORM-OPS-DESIGN-001 | Alta |
| LEGACY-AUDIT-065 | `backend/docs/tickets/be-bug-004-session-audit.md` | Lección aprendida | Continuación de la investigación de LEGACY-AUDIT-003/017: tras el fix de dimensionado de pool (PR #61, sesiones cortas en 3 bucles de fondo), producción seguía agotando el pool — la causa real, según esta auditoría posterior con metodología explícita (16 llamadas a `SessionLocal()` + 30 endpoints con `Depends(get_db)`), es que `get_current_user`/`get_db` mantienen la sesión abierta **durante todo el request**, y varios endpoints REST (`GET /freyja/status`, `GET /freyja/briefing` sobre todo, de alta frecuencia por polling del Dashboard) hacen llamadas síncronas lentas (CCXT, LLM) mientras la conexión sigue retenida. El propio `get_current_user` (`utils/auth.py`, L01) documenta y evita deliberadamente este problema para sí mismo. El ticket instrumentó el pool de forma segura (`pool_instrumentation.py`, solo IDs anónimos y metadatos, nunca SQL/tokens/URLs) pero **no aplicó ninguna corrección todavía** — es diagnóstico, no remediación. | REFERENCE | VERIFICADO (código leído íntegro; el ticket documenta su propia metodología con detalle verificable internamente) | Ninguno directo; lección arquitectónica de que el dimensionado de pool (LEGACY-AUDIT-003/017) fue necesario pero no suficiente — la causa raíz real era el acoplamiento entre sesión de BD y llamadas de red síncronas. | PLATFORM-DATA-DESIGN-001 | Alta |
| LEGACY-AUDIT-066 | `backend/app/database.py` | Persistencia/Ops | En los archivos y el commit revisados durante L02, el entorno Alembic observado (`alembic/env.py`) apunta exclusivamente al metadata `freyja2_*` (`target_metadata = Freyja2Base.metadata`). Para el esquema principal (tablas `users`/`signals`/`trades`/`user_profiles`/etc.), `database.py` invoca `Base.metadata.create_all()` y una secuencia de ~12 funciones de migración ad hoc (`_migrate_*`, ALTER TABLE detectado por `sqlalchemy.inspect`) desde su flujo de inicialización (`init_db()`) — su invocación fue observada dentro de `init_db()`, no solo su definición; ninguna fue ejecutada por esta auditoría. L02 no observó otra ruta Alembic dirigida al esquema principal, sin afirmar que sea imposible que exista fuera del alcance leído. El propio `database.py` etiqueta este patrón como "DEUDA DE INFRAESTRUCTURA ACEPTADA", no una decisión definitiva. | REJECT | VERIFICADO (código leído íntegro: el patrón observado en los 15 archivos de L02; no verificado fuera de ese alcance) | Sin historial de versiones del esquema principal, sin posibilidad de rollback estructurado, riesgo de deriva de esquema entre entornos que ejecutaron distintas versiones de `_migrate_*` en distinto orden. Contradice la política vigente de Freyja 2.0 de usar únicamente Alembic versionado. | PLATFORM-DATA-DESIGN-001 | Alta |
| LEGACY-AUDIT-067 | `backend/app/database.py` (`_migrate_binance_keys_to_broker_connections()`) | Seguridad/Ops | La migración one-time que cifra y traslada `User.binance_api_key`/`binance_api_secret` hacia `BrokerConnection` (ver LEGACY-AUDIT-060) define `fail-open` con precisión: **condición** — ausencia o valor vacío de `BROKER_ENCRYPTION_KEY`; **mecanismo** — un `if not settings.BROKER_ENCRYPTION_KEY: return` (guard clause con retorno inmediato, no una excepción capturada); **consecuencia estática** — la limpieza no se completa en esa ejecución y el flujo de inicialización (`init_db()`) continúa sin error ni log de advertencia hacia las siguientes operaciones observadas; **riesgo condicionado** — de existir valores sensibles en las columnas legacy, podrían conservarse sin la protección esperada; **no verificado por L02** — existencia real de esos valores, su contenido, o si esa ruta está activa en producción. | REJECT | VERIFICADO (código leído íntegro: la condición y el guard clause están demostrados estáticamente; la existencia de datos reales no fue verificada) | Alto (potencial, no confirmado): un despliegue que arranca sin `BROKER_ENCRYPTION_KEY` configurada deja abierta la rama que no completa la limpieza — comportamiento fail-open en una ruta de seguridad crítica, condicionado a que existan valores reales en las columnas. No se afirma una exposición de credenciales ya demostrada. | SECURITY-BROKER-DESIGN-001 | Alta (el mecanismo de código) / No aplicable (existencia de datos reales, sin verificar) |
| LEGACY-AUDIT-068 | `docker-compose.yml` | Seguridad/Ops | Inventario completo del archivo (valores no reproducidos): el servicio `db` (PostgreSQL) usa una imagen con versión/variante fijada, no `latest`; el servicio `pgadmin` (interfaz de administración) usa un tag flotante. `db` declara `healthcheck` (`pg_isready`); no se observó `healthcheck` equivalente para `pgadmin`. Existe un volumen nombrado para los datos de `db`; no se observó volumen equivalente para `pgadmin`. Se usa la red predeterminada de Compose, sin red personalizada declarada. Ambos servicios publican un puerto (`db` y `pgadmin`) sin restricción explícita de interfaz. `db` y `pgadmin` declaran credenciales literales por defecto directamente en el archivo versionado, sin usar `.env`/secrets de Docker. No se demostró uso en producción ni exposición pública — ver LEGACY-AUDIT-003, producción real era Supabase gestionado. | REJECT | VERIFICADO (código leído íntegro; valores no reproducidos) | Bajo-Medio: es infraestructura de desarrollo local, sin evidencia de uso en producción ni de exposición pública; aun así, el patrón estático es inseguro por sí mismo — credenciales literales por defecto, tag flotante en el servicio de administración, y publicación de puertos sin restricción explícita de interfaz — y no debe replicarse independientemente de si se demostró su uso real. | PLATFORM-OPS-DESIGN-001 | Alta |
| LEGACY-AUDIT-069 | `docker-compose.yml` | Persistencia/Ops | **Configuración de infraestructura Compose del legacy.** Docker Compose aprovisiona explícitamente un servicio PostgreSQL y una interfaz de administración (pgAdmin). Esto demuestra la existencia de una ruta local/contenedorizada basada en PostgreSQL. No demuestra que un despliegue real la utilizara. **Por qué permanece separado de LEGACY-AUDIT-002 (no es un duplicado):** LEGACY-AUDIT-002 audita la política y el comportamiento de conexión de la propia aplicación (`database.py`: qué dialectos admite, qué declara su código sobre el destino de producción). LEGACY-AUDIT-069 audita la topología de infraestructura *declarada* en `docker-compose.yml` — un artefacto distinto, de una capa distinta (orquestación de contenedores, no código de aplicación). Complementa a LEGACY-AUDIT-002 desde la infraestructura; no sustituye ni repite su conclusión sobre defaults y dialectos. | REFERENCE | VERIFICADO (código leído íntegro: el archivo aprovisiona esos dos servicios; NO VERIFICADO: que un despliegue real los usara) | Ninguno directo; aporta un tipo de evidencia distinto (configuración de infraestructura) al de LEGACY-AUDIT-002 (comentario de código). No usar como prueba de que "producción usaba" PostgreSQL — solo prueba que la infraestructura de desarrollo local lo aprovisionaba. | PLATFORM-DATA-DESIGN-001 | Alta (existencia de la configuración) / No aplicable (uso real en producción, sin verificar) |
| LEGACY-AUDIT-070 | `backend/app/models/trade.py` | Contrato/Dominio | Categorías separadas de campos `Column(Float)` en `Trade`, nunca `Numeric`/`Decimal` ni enteros en unidad mínima: **precios monetarios** (`entry_price`, `exit_price`, `stop_loss`, `take_profit`, `tp2`, `tp3`); **importes monetarios directos** (`risk_amount`, `profit_loss`, `fees`); **cantidad** (`position_size` — no es un importe en sí, pero participa directamente en el cálculo de P&L al multiplicarse por el precio). **Aparte, no incluido en la categoría monetaria:** `profit_loss_percent` es un porcentaje/ratio, no un importe monetario — su tipado en `Float` es el mismo problema de precisión/redondeo, pero no viola la regla de "importes monetarios" en el mismo sentido literal. | REJECT | VERIFICADO (código leído íntegro) | Precisión, redondeo y reproducibilidad: viola `CLAUDE.md` §6 para los precios e importes monetarios listados (`entry_price`/`exit_price`/`stop_loss`/`take_profit`/`tp2`/`tp3`/`risk_amount`/`profit_loss`/`fees`) y afecta indirectamente a `position_size` por su rol en el cálculo. No se observó ni se afirma una pérdida económica real causada por ello — el riesgo es de precisión acumulada, no un incidente confirmado. No replicar este tipado en los campos monetarios bajo ninguna circunstancia. | POINT1-DOMAIN | Alta |
| LEGACY-AUDIT-071 | `backend/app/models/signal.py`, `trade.py` | Contrato/Dominio | `Signal.market_type`/`profile_type` y `Trade.market_type`/`profile_type` se guardan como `String` libre (comentario indica los valores esperados, p. ej. "spot \| futures \| binary"), sin `Enum` ni `FK`, mientras que el mismo concepto en `UserProfile` (L02) sí es `Enum(MarketType)`/`Enum(TradingStyle)`. Mismo eje conceptual, dos niveles de garantía distintos según el modelo. | REJECT | VERIFICADO (código leído íntegro) | Riesgo de valores inconsistentes o mal escritos en `Signal`/`Trade` que un `Enum` habría detectado en el momento de la escritura; ver también LEGACY-AUDIT-005 (mismo tipo de mezcla conceptual). | POINT1-DOMAIN | Alta |
| LEGACY-AUDIT-072 | `backend/app/models/signal.py` | Contrato/Dominio | El propio código documenta honestamente que el `ForeignKey` de `Signal.strategy_spec_id` hacia `strategy_specs.spec_id` **no está garantizado** en todas las rutas de despliegue: SQLite nunca activa `PRAGMA foreign_keys`, y la migración ad-hoc que añadió la columna (`_migrate_add_signal_strategy_spec_id_column()`, `database.py`) no puede crear el constraint sobre una tabla ya existente. La única integridad real hoy es de aplicación (`SignalService`, fuera de L02). | REFERENCE | VERIFICADO (código leído íntegro — es el propio código el que documenta la limitación, no una inferencia de esta auditoría) | Lección: no asumir que una `ForeignKey` declarada en el modelo está realmente aplicada en una base de datos ya desplegada sin verificar la ruta de migración que creó esa columna. | PLATFORM-DATA-DESIGN-001 | Alta |
| LEGACY-AUDIT-073 | `backend/app/models/pending_execution.py` | Contrato/Dominio | `PendingExecution` no declara una restricción de unicidad estructural que impida múltiples registros para una misma señal (ningún `UniqueConstraint` sobre `signal_id`). **Alcance limitado a propósito, para no duplicar LEGACY-AUDIT-008:** LEGACY-AUDIT-008 audita la semántica y el acoplamiento de estados entre `PendingExecution` y `Signal` (ciclo de vida, expiración, cancelación); LEGACY-AUDIT-073 audita exclusivamente la cardinalidad e idempotencia estructural del modelo (cuántas filas puede haber por señal). Son riesgos distintos. No se afirma que existan realmente registros duplicados — solo que el modelo no impone esa unicidad. | REFERENCE | VERIFICADO (código leído íntegro: ausencia del constraint; no verificado si existen duplicados reales) | Riesgo teórico de múltiples confirmaciones pendientes para la misma señal si la capa de servicio (Lote 4/5) no lo impide explícitamente — sin confirmar si eso ocurre ni si alguna vez ocurrió. | PENDIENTE DE MAPEO — requiere contrastar contratos vigentes de POINT2–POINT15 | Media |

---

## 6. Candidatos REUSE (preliminares — ninguno validado directamente contra código)

Los cinco grupos siguientes son los de mayor interés aparente, **todos pendientes de contraste directo con el código real en el lote correspondiente (§15)**. El manifiesto legacy, cuando se cita como evidencia, es una fuente secundaria (el proyecto anterior evaluándose a sí mismo) y no sustituye esa validación.

**LEGACY-AUDIT-004 — Modelo de dominio de 5 capas.** VERIFICADO como documento de diseño. No requiere validación de código porque no describe una implementación existente, sino una propuesta. Tarea destino: `POINT1-DOMAIN`. Sigue siendo el candidato más sólido de todo el documento precisamente porque su evidencia es un texto completo, no una inferencia sobre código no leído.

**LEGACY-AUDIT-012/013/014 — Catálogo canónico `freyja2_*` (actualizado tras L02).** VERIFICADO en su totalidad — L02 completó la lectura íntegra de la migración de siembra (858/858 líneas, antes solo ~120), confirmando exactamente el patrón fail-closed/idempotente que el docstring prometía. Es, junto con LEGACY-AUDIT-004 y el paquete `StrategySpec`/seed (LEGACY-AUDIT-016, también verificado en L02), el candidato con mayor base de evidencia real de todo el documento. Tarea destino: `POINT1-DB`, `POINT1-SEED`. Pendiente: los 12 tests de `freyja2/` (Lote 9E) antes de promover a definitivo — el hecho de que el código esté bien escrito no sustituye la ejecución de sus propios tests.

**LEGACY-AUDIT-016 — `StrategySpec`/`StrategySpecSeed` (nuevo tras L02).** VERIFICADO por lectura íntegra de ambos archivos (576 + 801 líneas). Identidad determinista, inmutabilidad exigida por evento ORM, fingerprint sha256 del contrato algorítmico, seed fail-closed con validación de fingerprint y de clave legacy antes de tocar la BD. La clasificación `REUSABLE_INFRASTRUCTURE` del manifiesto queda confirmada, no solo citada. Tarea destino: `POINT1-DOMAIN`. Comparte con LEGACY-AUDIT-012/013/014 el mismo límite de fondo: sin tests ejecutados (Lote 9A cubre `test_strategy_spec_*.py`).

**LEGACY-AUDIT-021/022/023 — Paquete de seguridad de brokers (actualizado tras L01).** Los tres, hoy **VERIFICADO** por lectura íntegra de `safe_log.py`, `broker_audit_log.py`/`trade_audit_log.py` y `broker_crypto.py`. La clasificación se mantiene `REUSE CANDIDATE` (no se promueve a definitivo solo por leer el código, conforme a la regla explícita de esta corrección) porque ninguno se ha ejecutado ni probado, y porque `broker_crypto.py` en particular queda condicionado a resolver la contradicción con `user.py` (LEGACY-AUDIT-060) en el Lote 5. **LEGACY-AUDIT-024/025 siguen PENDIENTE DE VALIDACIÓN** — sus archivos de evidencia (`brokers/base.py`, `brokers/factory.py`, `backend/app/main.py`) no forman parte de L01 y requieren el Lote 5/7. Tarea destino: `SECURITY-BROKER-DESIGN-001`. L01 (seguridad) completado; requiere Lote 5 (brokers) para cerrar por completo.

**LEGACY-AUDIT-046 — Autenticación JWT + hashing (actualizado tras L01).** VERIFICADO por lectura íntegra de `auth.py`/`user.py`: bcrypt para contraseñas, JWT HS256 con claims mínimos, fallo cerrado en `get_current_user`. Sigue como `REUSE CANDIDATE` porque no se ejecutó ni probó, y porque no se observa mecanismo de revocación de tokens dentro de `auth.py` (LEGACY-AUDIT-062; protección efectiva del sistema sin resolver). Tarea destino: `F0-AUTH-DESIGN-001`.

**LEGACY-AUDIT-059/061 — Patrones nuevos de L01 (integridad de auditoría sin FK; schema de salida sin campos sensibles).** Ambos VERIFICADO por lectura íntegra. Son los candidatos de menor riesgo de todo L01: patrones de diseño defensivo ya demostrados en el propio código, sin dependencia de piezas no leídas. Tarea destino: `SECURITY-BROKER-DESIGN-001` (059), `F0-AUTH-DESIGN-001` (061).

**LEGACY-AUDIT-036/037/038/039/040 — Controles de seguridad de ejecución.** Mayormente **BASADO EN MANIFIESTO** o **PENDIENTE DE VALIDACIÓN**; solo LEGACY-AUDIT-038/040 tienen algo más de solidez por describir flujo de producto/UX documentado explícitamente, no comportamiento de backend. Tarea destino: `SAFETY-CONTROL-DESIGN-001`. Requiere Lote 5 (riesgo/brokers) y Lote 4 (señales) antes de promoción.

**LEGACY-AUDIT-041/042 — Motor de voz de Freyja y vocabulario.** LEGACY-AUDIT-042 (vocabulario) es VERIFICADO al ser un artefacto puramente textual del manual. LEGACY-AUDIT-041 (motor rule-based) es PENDIENTE DE VALIDACIÓN en cuanto a implementación (`freyja_voice.py` nunca leído), aunque el *concepto* (existencia de un modo sin LLM) está descrito de forma consistente en tres documentos distintos leídos íntegros. Tarea destino: `FREYJA-VOICE-DESIGN-001`. Requiere Lote 3.

---

## 7. Candidatos REWRITE (preliminares)

**LEGACY-AUDIT-026 — Adaptadores concretos de broker.** Se retracta expresamente la afirmación de la versión anterior de que "el manifiesto los clasifica REVIEW_BEFORE_REUSE" — verificado ahora que estos 4 archivos no aparecen en el manifiesto en absoluto. No hay ninguna evidencia, ni siquiera documental indirecta, sobre su contenido real. Tarea destino: `SECURITY-BROKER-DESIGN-001`. Requiere Lote 5 íntegro antes de cualquier afirmación sobre estos archivos — el Lote 5 debe además resolver si `broker_connection.py` (también Lote 5) es la ruta cifrada real que sustituye a las columnas en claro de `user.py` (LEGACY-AUDIT-060, la nueva confianza más baja/crítica del documento).

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
- **LEGACY-AUDIT-056** — Workflows de CI legacy con tags flotantes (no SHA-pinned). VERIFICADO por lectura íntegra; confirma que la decisión de SHA-pinning de `F0-CI-001` mejora sobre la práctica legacy.
- **LEGACY-AUDIT-057** — `.gitignore` legacy con higiene sólida. VERIFICADO.
- **LEGACY-AUDIT-058** — Contradicción entre `.env.example` (expone `ANTHROPIC_API_KEY` para "Voz de Freyja") y la documentación ("motor rule-based, sin LLM"). VERIFICADO el contenido del archivo; no resuelto cuál de las dos descripciones es la vigente sin leer `freyja_voice.py` (Lote 3).
- **LEGACY-AUDIT-062** — Ausencia de revocación de tokens JWT. VERIFICADO por lectura íntegra de `auth.py`.
- **LEGACY-AUDIT-063** — Ausencia de rotación de `BROKER_ENCRYPTION_KEY`. VERIFICADO por lectura íntegra de `broker_crypto.py`.
- **LEGACY-AUDIT-064** — Limitación estructural de `safe_log_exc()` (denylist exacta, no escaneo de contenido). VERIFICADO por lectura íntegra.
- **LEGACY-AUDIT-065** — Causa raíz profunda del agotamiento de pool (sesión retenida durante llamadas de red síncronas), continuación de LEGACY-AUDIT-003/017. VERIFICADO por lectura íntegra del ticket de seguimiento.
- **LEGACY-AUDIT-069** (nuevo, L02) — `docker-compose.yml` aprovisiona explícitamente un servicio PostgreSQL; complementa a LEGACY-AUDIT-002 desde la infraestructura, sin repetir su conclusión ni demostrar uso real en producción. VERIFICADO (la configuración existe; no verificado su uso real).
- **LEGACY-AUDIT-072** (nuevo, L02) — Límite honesto de enforcement del FK `Signal.strategy_spec_id` (SQLite sin `PRAGMA foreign_keys`, migración ad-hoc que no añade el constraint). VERIFICADO por lectura íntegra; el propio código documenta la limitación.
- **LEGACY-AUDIT-073** (nuevo, L02) — `PendingExecution` sin `UniqueConstraint` por `signal_id` ni acoplamiento de esquema al `status` de `Signal`. VERIFICADO por lectura íntegra.

---

## 9. Elementos REJECT

Se mantiene la tabla de la versión anterior; se ajusta la columna de evidencia donde la versión anterior sobre-afirmaba certeza.

| Elemento | Motivo de rechazo | Riesgo | Regla que lo prohíbe | Estado de la evidencia | Acción |
|---|---|---|---|---|---|
| LEGACY-AUDIT-002 — SQLite documentada como base de datos suficiente | Persistencia dual real (código y `docker-compose.yml` confirmados en L02) que no coincide con la política de una única base de datos. | Confusión de arquitectura si se toma el README legacy, o el soporte dual real del código, como referencia vigente para Freyja 2.0. | `CLAUDE.md` §7. | VERIFICADO (código real leído íntegro en L02: `database.py` soporta ambos dialectos deliberadamente; `docker-compose.yml` solo aprovisiona PostgreSQL) | No migrar; PostgreSQL ya es la única base de datos de Freyja 2.0 (`F0-DATABASE-001`, ya completada) — el soporte dual del legacy (deliberado y documentado en su propio código) no es un patrón a heredar. |
| LEGACY-AUDIT-066 — Esquema principal sin Alembic, evolucionado por `_migrate_*` ad-hoc | Ausencia total de migraciones versionadas para el esquema de negocio (`users`/`signals`/`trades`/etc.) — solo `create_all()` + `ALTER TABLE` dispatado a mano. | Deriva de esquema no rastreable entre entornos; sin rollback estructurado. | Práctica vigente de Freyja 2.0 (Alembic versionado, sin `create_all()`). | VERIFICADO (código leído íntegro en L02) | No replicar; Freyja 2.0 ya usa Alembic versionado para todo su esquema. |
| LEGACY-AUDIT-067 — Migración de limpieza de credenciales fail-open | La migración que cifra y mueve `binance_api_key`/`secret` se salta en silencio (guard clause, no excepción) sin `BROKER_ENCRYPTION_KEY`. | De existir credenciales en esas columnas, permanecerían sin la protección esperada y sin alerta si falta la variable de entorno; no confirmado que existan valores reales. | `CLAUDE.md` §5 (seguridad > velocidad). | VERIFICADO (código leído íntegro en L02: la condición y el guard clause; NO VERIFICADO: existencia de datos reales) | No replicar el silencio; cualquier ruta de cifrado de credenciales debe fallar cerrado (abortar/alertar), no omitirse. |
| LEGACY-AUDIT-068 — Credenciales por defecto en `docker-compose.yml` | Contraseñas débiles hardcodeadas en un archivo versionado, sin `.env`/secrets. | Exposición si se ejecuta fuera de un host aislado. | Buen juicio de gestión de secretos. | VERIFICADO (código leído íntegro en L02; valores no reproducidos) | No copiar el patrón; cualquier compose de desarrollo de Freyja 2.0 debe leer credenciales de `.env`, nunca hardcodearlas. |
| LEGACY-AUDIT-070 — `Float` para todos los importes monetarios de `Trade` | Viola directamente la regla de tipos exactos para dinero. | Error de redondeo acumulado en P&L. | `CLAUDE.md` §6. | VERIFICADO (código leído íntegro en L02) | No replicar; cualquier modelo `Trade` de Freyja 2.0 debe usar `Numeric`/`Decimal` o enteros en unidad mínima. |
| LEGACY-AUDIT-071 — `market_type`/`profile_type` como `String` libre en `Signal`/`Trade` | Mismo concepto tipado como `Enum` en `UserProfile` pero como texto libre aquí — inconsistencia de garantías dentro del mismo proyecto. | Valores inconsistentes no detectados en el momento de escritura. | Buen juicio de consistencia de tipado; relacionado con `CLAUDE.md` (determinismo). | VERIFICADO (código leído íntegro en L02) | No replicar la inconsistencia; tipar el mismo concepto de forma uniforme en todos los modelos que lo usen. |
| LEGACY-AUDIT-028 — `CORS allow_origins=["*"]` | Documentado como "cerrar en producción" sin evidencia de haberse cerrado. | Superficie de ataque si se replica tal cual. | Buen juicio de seguridad; `CLAUDE.md` §5. | VERIFICADO (la nota del documento); INFERENCIA (que nunca se cerró) | No copiar la configuración, independientemente de si legacy la cerró después. |
| LEGACY-AUDIT-030 — Dos motores de cierre de trade coexistiendo | Duplicación de responsabilidad que divergió silenciosamente. | Bugs de inconsistencia difíciles de diagnosticar. | `CLAUDE.md` §11. | VERIFICADO (postmortem con hash de commit) | No replicar el patrón. |
| LEGACY-AUDIT-044 — "Modo Fácil"/"Modo Experto" como productos separados | Dos experiencias de producto conmutadas por toggle, en vez de una única profundidad adaptativa. | Fragmentación de producto. | `CLAUDE.md` §4. | VERIFICADO (descripción documental); PENDIENTE DE VALIDACIÓN (archivo/mecanismo exacto — ver nota en la matriz) | No replicar el patrón de dos páginas/toggle. |
| LEGACY-AUDIT-053 — Scraping no oficial de ForexFactory | Sin acuerdo ni API documentada. | Riesgo legal/ToS; fragilidad técnica. | Buen juicio de proveedor/dependencia. | VERIFICADO (descripción documental); PENDIENTE DE VALIDACIÓN (código real, `NAME_ONLY`) | No replicar la técnica. |
| LEGACY-AUDIT-054 — CallMeBot como transporte WhatsApp | API no oficial de terceros. | Riesgo de disponibilidad/ToS. | Buen juicio de proveedor/dependencia. | VERIFICADO (descripción documental) | No replicar la técnica. |
| LEGACY-AUDIT-055 — `.claude/launch.json` con ruta absoluta de máquina personal | Configuración de lanzamiento no portable, atada a una ruta de intérprete específica de un equipo de desarrollo concreto. | Ninguno de seguridad; riesgo de confusión/no-reproducibilidad si se copiara tal cual. | Buen juicio de portabilidad; ruta personal no reproducida en este documento. | VERIFICADO (código leído íntegro) | No copiar la ruta; cualquier configuración de lanzamiento local en Freyja 2.0 debe usar comandos relativos/portables. |
| LEGACY-AUDIT-060 — Columnas textuales para credenciales sin cifrado forzado por la capa ORM en `user.py`; uso y protección efectiva pendientes de validación | Columnas de credenciales de broker/terceros sin cifrado visible en el modelo, contradiciendo el mecanismo Fernet de `broker_crypto.py`. **VERIFICADO:** existen columnas textuales (`binance_api_key`/`binance_api_secret`/`whatsapp_apikey`) y el modelo no impone cifrado. **Nuevo en L02:** `database.py` tiene una migración de limpieza activa hacia `BrokerConnection` cifrado (confirma que es un remanente legacy con salida, no solo código muerto), pero esa salida es fail-open si falta `BROKER_ENCRYPTION_KEY` (ver LEGACY-AUDIT-067). **PENDIENTE:** flujo real de escritura (¿algún endpoint sigue escribiendo ahí?), lectura y vigencia — no demostrado hasta Lote 7 (`main.py`). | Alto (potencial): exposición de credenciales de broker en claro en la base de datos, únicamente si esta ruta resultara estar activa y sin cifrado en el flujo real — no confirmado. | `CLAUDE.md` §5 (seguridad tiene prioridad sobre velocidad; nunca credenciales de broker sin protección adecuada). El REJECT se aplica al patrón de persistencia sin garantía estructural de cifrado, no a una afirmación de almacenamiento en claro ya demostrada. | VERIFICADO (columnas textuales y ausencia de cifrado forzado en el modelo, código leído íntegro en L01; migración de limpieza fail-open confirmada en L02); PENDIENTE DE VALIDACIÓN (ruta de escritura real — Lote 7). | No replicar el patrón de persistencia sin garantía estructural de cifrado bajo ninguna circunstancia; confirmar en Lote 7 el flujo real antes de afirmar exposición efectiva. |

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
| Gobierno/cutover/postmortems | 10 | 10 | 0 | 0 | 0 | Completa |
| Dominio | 8 | 7 | 0 | 1 | 0 | Mayormente completa (falta `strategy.py`, Lote 4) |
| Persistencia y migraciones | 7 | 7 | 0 | 0 | 0 | Completa |
| Catálogo/POINT1 | 6 | 6 | 0 | 0 | 0 | Completa |
| Proveedores y datos | 3 | 0 | 0 | 3 | 0 | Inventariada, no revisada |
| Señales y estrategias | 9 | 0 | 0 | 9 | 0 | Inventariada, no revisada (manifiesto) |
| Indicadores | 3 | 0 | 0 | 3 | 0 | Inventariada, no revisada |
| Ciclo de vida | 4 | 1 | 0 | 3 | 0 | Parcial (1 de 4 — `pending_execution.py`) |
| Brokers y ejecución | 10 | 0 | 0 | 10 | 0 | Inventariada, no revisada |
| Riesgo | 4 | 0 | 0 | 4 | 0 | Inventariada, no revisada (manifiesto) |
| Backtesting | 2 | 0 | 0 | 2 | 0 | Inventariada, no revisada (manifiesto) |
| Autenticación y seguridad | 12 | 12 | 0 | 0 | 0 | Completa |
| Operación/observabilidad | 18 | 0 | 0 | 18 | 0 | Inventariada, no revisada (1 archivo con evidencia de manifiesto a nivel de endpoint) |
| Frontend/UX | 69 | 0 | 0 | 69 | 0 | Inventariada, no revisada (17 con ficha de manifiesto) |
| Noticias/notificaciones | 6 | 0 | 0 | 6 | 0 | Inventariada, no revisada (1 con ficha de manifiesto) |
| Voz de Freyja | 1 | 0 | 0 | 1 | 0 | Inventariada, no revisada (manifiesto) |
| ML/IA | 2 | 0 | 0 | 2 | 0 | Inventariada, no revisada (manifiesto) |
| Tests backend (flat + `freyja2/`) | 62 | 0 | 0 | 62 | 0 | No revisada |
| Tests frontend | 14 | 0 | 0 | 14 | 0 | No revisada |
| Architecture tests | 28 | 0 | 2 | 26 | 0 | Mínima (2 de 28) |
| **Total** | **288** | **53** | **2** | **233** | **0** | — |

**Nota de honestidad explícita:** "Inventariada, no revisada" significa que se conoce la existencia y ruta del archivo, no su contenido. No debe leerse como "sin necesidad" ni como evidencia de que el área carece de conocimiento legacy útil — significa exactamente lo contrario: que el conocimiento, si existe, todavía no se ha extraído. Privacidad y Comunidad (áreas cualitativas de la versión anterior) no tienen archivos identificables como propios dentro de los 288 — se mantienen como "sin evidencia legacy" y se listan en §12, no en esta tabla cuantitativa. **Actualización tras L01:** los modelos de auditoría (`broker_audit_log.py`, `trade_audit_log.py`) aportan la primera evidencia legacy real relacionada con Privacidad (ausencia de política de retención/borrado visible) — sigue sin existir una fila cuantitativa propia para Privacidad, pero ya no es cierto que el área carezca por completo de evidencia; ver LEGACY-AUDIT-022 y §12.

**Actualización tras L02:** las áreas "Dominio", "Persistencia y migraciones", "Catálogo/POINT1" y "Ciclo de vida" pasan de mayoritariamente sin revisar a mayormente o completamente revisadas (14 archivos + la migración de siembra completada). El único archivo de "Dominio" que queda sin leer es `backend/app/models/strategy.py`, asignado al Lote 4 — el propio `strategy_spec.py` (L02) documenta que esa tabla "no está integrada en ningún flujo real (0 usos fuera de un import muerto)", afirmación documental interna del código legacy sobre sí mismo, todavía no verificada de forma independiente por esta auditoría (`strategy.py` sigue siendo `NAME_ONLY`).

---

## 12. Riesgos y decisiones pendientes

**Críticos**
- Ninguna estrategia de backup/recuperación existía en el proyecto anterior antes del incidente de purga de datos (LEGACY-AUDIT-029, VERIFICADO como afirmación documental). Freyja 2.0 debe decidir su estrategia de backup de PostgreSQL antes de acumular cualquier dato de valor.
- **85,8% de los archivos legacy siguen sin revisar** (era 91,3% antes de L01). Ninguna decisión de arquitectura de Freyja 2.0 debería citar esta auditoría como "conocimiento legacy agotado" hasta cerrar, al menos, los Lotes que cubran las áreas relevantes a esa decisión.
- **Nuevo, crítico (L01, actualizado en L02):** `backend/app/models/user.py` almacena `binance_api_key`/`binance_api_secret`/`whatsapp_apikey` en columnas de texto plano (LEGACY-AUDIT-060), contradiciendo el cifrado Fernet confirmado en `broker_crypto.py` (LEGACY-AUDIT-023). **L02 confirma** que existe una migración de limpieza activa (`database.py::_migrate_binance_keys_to_broker_connections()`) que cifra y traslada esos valores a `BrokerConnection` — no es simplemente código muerto — pero esa limpieza **se salta en silencio si `BROKER_ENCRYPTION_KEY` no está configurada** (LEGACY-AUDIT-067), sin fallar cerrado ni alertar. Si la ruta de escritura original (`main.py`, Lote 7) siguiera activa además de esta limpieza fail-open, el riesgo persistiría. Sigue sin resolverse "vigente vs. histórico" hasta el Lote 7.
- **Nuevo, crítico (L02):** en los archivos revisados, el esquema principal de la aplicación legacy (`users`/`signals`/`trades`/`user_profiles`/etc.) se crea con `Base.metadata.create_all()` y evoluciona con ~12 funciones `_migrate_*` ad-hoc invocadas desde `init_db()`, sin ningún registro de versión (LEGACY-AUDIT-066); el entorno Alembic observado apunta exclusivamente al prototipo `freyja2_*`. L02 no observó otra ruta Alembic dirigida al esquema principal, sin afirmar que sea imposible que exista fuera del alcance leído. Contradice directamente la política vigente de Freyja 2.0 (Alembic versionado, sin `create_all()`) — riesgo si se asumiera erróneamente que el patrón de migraciones legacy es un precedente a seguir.

**Altos**
- `/auth/login` sin protección de fuerza bruta era una brecha conocida a la fecha del commit auditado (LEGACY-AUDIT-027) — **ahora confirmado por código** que `backend/app/utils/auth.py` no la implementa en ese módulo; sigue sin poder confirmarse si existe en `main.py` (fuera de L01) o en infraestructura.
- **LEGACY-AUDIT-026 corregido:** los adaptadores concretos de broker no tienen ninguna evidencia, ni siquiera del manifiesto (se retracta la cita incorrecta de la versión anterior). Deben tratarse como completamente desconocidos hasta el Lote 5.
- **Nuevo (L01):** no se observa un mecanismo de revocación o blacklist dentro de `auth.py` (LEGACY-AUDIT-062), combinado con expiración larga por defecto (7 días) — ventana de exposición amplia dentro de ese módulo ante un token robado. La protección efectiva del sistema permanece PENDIENTE DE VALIDACIÓN hasta revisar endpoints, middleware y tests en Lote 7/Lote 9C/Lote 9D — no se afirma que todo el sistema legacy carezca de revocación. Decisión de diseño pendiente para `F0-AUTH-BACKEND-001`.
- **Nuevo (L01):** `broker_crypto.py` no soporta rotación ni versionado de la clave global de cifrado (LEGACY-AUDIT-063) — un único punto de fallo para todas las credenciales de broker del sistema.
- **Nuevo (L02):** `backend/app/models/trade.py` declara todos sus importes monetarios (`entry_price`, `exit_price`, `profit_loss`, `fees`, etc.) como `Float` (LEGACY-AUDIT-070) — viola directamente `CLAUDE.md` §6. No replicar este tipado en ningún modelo de trading de Freyja 2.0.
- Comunidad y (en gran medida) backtesting **no tienen evidencia legacy** en absoluto dentro de lo revisado — no se debe inferir que el legacy "no tenía nada" en estas áreas; simplemente no se ha buscado con suficiente profundidad. Privacidad ya cuenta con evidencia parcial tras L01 (ver §11).

**Medios**
- **Discrepancia sin resolver (nueva en la corrección anterior):** LEGACY-AUDIT-045 cita `EasyMode.tsx` como un componente de 894 líneas mencionado por el roadmap de testing legacy, pero ese archivo **no aparece** en el listado de 288 rutas del commit `44192410e70975a5f156db81f711e56bee63376b` que esta auditoría audita. Dos explicaciones posibles, ninguna confirmada: (a) el roadmap de testing describe un estado anterior del proyecto y el archivo fue renombrado o eliminado antes de este commit; (b) un error de transcripción en la auditoría original. Debe resolverse en el Lote 8B antes de dar por buena cualquier afirmación sobre `EasyMode.tsx`.
- **Nueva discrepancia sin resolver (L01):** `backend/.env.example` expone `ANTHROPIC_API_KEY`/`FREYJA_MODEL` para "Voz de Freyja" (LEGACY-AUDIT-058), mientras que la documentación (LEGACY-AUDIT-041) describe ese motor como "rule-based, sin LLM". No se puede afirmar cuál describe el comportamiento real sin leer `freyja_voice.py` (Lote 3).
- **Nuevo (L01):** la redacción de `safe_log_exc()` es una lista de denegación exacta por nombre de clave, no un escaneo de contenido (LEGACY-AUDIT-064) — riesgo de falso negativo si un `caller` usa un nombre de clave no previsto.
- Varios hallazgos de dominio de alto valor (LEGACY-AUDIT-006, 007, 008, 033, 050, 051) quedan formalmente **PENDIENTE DE MAPEO — requiere contrastar contratos vigentes de POINT2–POINT15**, no asignados a un ID inventado, porque el encargo de esta auditoría no detalló el contenido de esos puntos del roadmap. Se resuelve en el Lote 10. **Se solicita al Arquitecto** indicar a qué punto exacto corresponden, o confirmar que aún no existe un punto asignado para ellos.
- Deriva de contrato entre canales (LEGACY-AUDIT-034) ya ocurrió una vez en legacy — recomienda una única fuente de verdad tipada desde el principio en `POINT1-API`.
- **Nueva lección (L01):** el fix de dimensionado de pool (LEGACY-AUDIT-003/017) fue necesario pero no suficiente — la causa raíz real, según LEGACY-AUDIT-065, era el acoplamiento entre sesión de BD y llamadas de red síncronas en varios endpoints REST. Relevante para el diseño de sesión/pool de `PLATFORM-DATA-DESIGN-001` en Freyja 2.0.
- **Nuevo (L02):** `Signal.market_type`/`profile_type` y `Trade.market_type`/`profile_type` son `String` libre sin `Enum` ni `FK`, mientras el mismo concepto en `UserProfile` sí es `Enum` (LEGACY-AUDIT-071) — inconsistencia de tipado del mismo eje conceptual dentro del propio proyecto legacy, mismo tipo de riesgo que LEGACY-AUDIT-005 (`MarketType` mezclando ejes).
- **Nuevo (L02):** el `ForeignKey` de `Signal.strategy_spec_id` no está garantizado en todas las rutas de despliegue (SQLite sin `PRAGMA foreign_keys`; migración ad-hoc que no añade el constraint sobre tablas existentes) — LEGACY-AUDIT-072. Lección: verificar siempre la ruta de migración real antes de asumir que una FK declarada en el ORM está aplicada en una base de datos ya desplegada.
- **Nuevo (L02):** `docker-compose.yml` legacy declara credenciales por defecto en texto plano para Postgres/pgAdmin, sin `.env` (LEGACY-AUDIT-068) — antipatrón de gestión de secretos, aunque de impacto bajo por tratarse de infraestructura de desarrollo local, no de producción (ver LEGACY-AUDIT-003/069).

**Bajos**
- El origen del capital para el cálculo de tamaño de posición (LEGACY-AUDIT-035) quedó como pregunta abierta en legacy.
- `docs/testing/frontend-testing-roadmap.md` (LEGACY-AUDIT-019) está desactualizado respecto al estado real del mismo commit — no citarlo como estado vigente sin verificación adicional (Lote 8E).
- `.claude/launch.json` legacy (LEGACY-AUDIT-055) no es reutilizable tal cual por depender de una ruta de máquina personal — sin impacto más allá de portabilidad.

---

## 13. Recomendaciones de secuencia

Sin cambios de fondo respecto a la versión anterior, salvo que ahora cada recomendación remite al lote correspondiente (§15) en vez de presuponer que la consulta documental ya es suficiente:

- `POINT1-DOMAIN`: **L02 completado** — consultar LEGACY-AUDIT-004/005/006/016 (todos VERIFICADO por código real, no solo documento). **No copiar tal cual:** `Trade.*` en `Float` para dinero (LEGACY-AUDIT-070, viola `CLAUDE.md` §6) y `Signal`/`Trade`.`market_type`/`profile_type` como `String` libre (LEGACY-AUDIT-071) — cualquier recreación de estos modelos en Freyja 2.0 debe corregir ambos puntos desde el diseño, no heredarlos. `strategy_spec.py`/`strategy_spec_seed.py` (LEGACY-AUDIT-016) son el patrón de mayor calidad de todo el lote — identidad determinista, inmutabilidad ORM, fingerprint de contrato — validado por código íntegro, aún sin ejecutar sus tests (Lote 9A).
- `POINT1-DB`/`POINT1-SEED`: **L02 completado** — LEGACY-AUDIT-012/013/014 y la migración de siembra completa (858/858 líneas) confirman el patrón fail-closed/idempotente end-to-end, ya no solo por docstring. Pendiente: los 12 tests de `freyja2/` (Lote 9E) antes de promover a definitivo. **Lección a incorporar, no a copiar:** en los archivos revisados, el esquema principal legacy no se gestionaba con Alembic (LEGACY-AUDIT-066) — reforzar que Freyja 2.0 mantenga Alembic versionado como único mecanismo, sin excepciones "temporales" tipo `create_all()`.
- `SECURITY-BROKER-DESIGN-001`: **L01 completado** para LEGACY-AUDIT-021/022/023 (VERIFICADO por código); **L02 añade evidencia parcial a LEGACY-AUDIT-060** (migración de limpieza activa pero fail-open, LEGACY-AUDIT-067 — no replicar el silencio ante clave de cifrado ausente); **no actuar sobre LEGACY-AUDIT-024/025/026/060 hasta cerrar el Lote 5/Lote 7** — en particular, `broker_connection.py` (Lote 5) y `main.py` (Lote 7) deben resolver si la ruta de escritura en claro sigue activa antes de diseñar el almacenamiento de credenciales de Freyja 2.0.
- `SAFETY-CONTROL-DESIGN-001`: **no actuar sobre LEGACY-AUDIT-036 a 040 hasta cerrar el Lote 5**; decidir explícitamente la pregunta abierta de LEGACY-AUDIT-035.
- `FREYJA-VOICE-DESIGN-001`: LEGACY-AUDIT-042 (vocabulario) puede consultarse ya (VERIFICADO); LEGACY-AUDIT-041 (motor) espera al Lote 3 para resolver la contradicción con LEGACY-AUDIT-058 (`.env.example` con clave de Anthropic).
- `F0-AUTH-BACKEND-001`: **L01 completado** — LEGACY-AUDIT-027 confirmado por código (`auth.py`, este commit, sin protección de fuerza bruta); LEGACY-AUDIT-046 confirmado (JWT+bcrypt); LEGACY-AUDIT-062 (sin revocación de tokens) es una decisión de diseño a tomar explícitamente. Confirmar aún contra el Lote 9C (`test_be_sec_003_rate_limit_and_docs.py`) y el Lote 7 (`main.py`, por si la protección vive ahí).
- `PLATFORM-OPS-DESIGN-001`: incorporar una estrategia de backup motivada por LEGACY-AUDIT-029; no requiere esperar a un lote. **Nuevo tras L01:** incorporar también la lección de LEGACY-AUDIT-065 (no acoplar sesiones de BD a llamadas de red síncronas).
- `PLATFORM-DATA-DESIGN-001`: **nuevo tras L01** — diseñar explícitamente el patrón de sesión corta para dependencias de solo-autenticación (como hace `get_current_user` en `auth.py`, LEGACY-AUDIT-046/065), evitando repetir el patrón que causó el agotamiento de pool documentado en LEGACY-AUDIT-003/017/065.
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

Cubría originalmente los **260 archivos** sin evidencia directa (48 `MANIFEST_ONLY` + 212 `NAME_ONLY`). Tras el cierre de `LEGACY-AUDIT-L01` (13 archivos) y `LEGACY-AUDIT-L02` (14 archivos + finalización de la migración de siembra, antes `REVIEWED_PARTIAL`), quedan **233 archivos pendientes** (43 `MANIFEST_ONLY` + 190 `NAME_ONLY`), sin solapamientos, verificado matemáticamente (§17, contra el apéndice completo de §19). Los 53 `REVIEWED_FULL` + 2 `REVIEWED_PARTIAL` no se reasignan a ningún lote, salvo una advertencia puntual en el Lote 9F para *completar* (no repetir) las 2 lecturas parciales restantes (los `test_architecture_*.py`; la migración de siembra ya se completó en L02).

**Corrección estructural de la versión anterior (mantenida):** los Lotes 8 y 9 (83 y 88 archivos) están subdivididos en sublotes de máximo 25 archivos cada uno.

| Lote | Archivos | Tema | Estado |
|---|---|---|---|
| 1 | 13 | Gobierno, ADR, postmortems y seguridad | ✅ **COMPLETADO** |
| 2 | 14 | Dominio, persistencia y catálogo POINT1 | ✅ **COMPLETADO** |
| 3 | 10 | Proveedores, datos, noticias y notificaciones | ⏭️ **Siguiente lote** |
| 4 | 15 | Señales, estrategias, indicadores y ciclo de vida | Pendiente |
| 5 | 15 | Brokers, ejecución y riesgo | Pendiente |
| 6 | 4 | Backtesting, evaluación cuantitativa y ML | Pendiente |
| 7 | 18 | Backend API, autenticación y operación | Pendiente |
| 8A | 21 | Frontend — configuración, entrada, routing y shell | Pendiente |
| 8B | 12 | Frontend — páginas y navegación | Pendiente |
| 8C | 23 | Frontend — componentes de dominio y dashboard | Pendiente |
| 8D | 13 | Frontend — servicios, hooks y contratos frontend | Pendiente |
| 8E | 14 | Frontend — tests frontend y reconciliación de `FRONTEND-TEST-001` | Pendiente |
| 9A | 18 | Tests de dominio y modelos | Pendiente |
| 9B | 14 | Tests de servicios, estrategias e indicadores | Pendiente |
| 9C | 13 | Tests de brokers, ejecución y seguridad | Pendiente |
| 9D | 6 | Tests de API e integración | Pendiente |
| 9E | 12 | Tests `freyja2` | Pendiente |
| 9F | 25 | Architecture tests y reconciliación de invariantes | Pendiente |
| 10 | 0 (síntesis) | Reconciliación final y mapeo POINT2–POINT15 | Pendiente |
| **Total pendiente** | **233** | — | — |

Verificación de subtotales tras L01+L02: Lotes 3–7 = 10+15+15+4+18 = **62**. Sublotes 8A–8E = 21+12+23+13+14 = **83**. Sublotes 9A–9F = 18+14+13+6+12+25 = **88**. Lote 10 = 0. `62 + 83 + 88 + 0 = 233` ✓, coincide exactamente con `MANIFEST_ONLY (43) + NAME_ONLY (190)`. El orden de lotes aprobado no se ha alterado — solo se retiran los Lotes 1 y 2 del conteo de pendientes por estar completados.

### Lote 1 — Gobierno, ADR, postmortems y seguridad — ✅ COMPLETADO (`LEGACY-AUDIT-L01`)

- **Rutas incluidas (13, todas `REVIEWED_FULL`):** `.claude/launch.json`, `.github/workflows/backend-ci.yml`, `.github/workflows/frontend-ci.yml`, `.gitignore`, `backend/.env.example`, `backend/app/models/broker_audit_log.py`, `backend/app/models/trade_audit_log.py`, `backend/app/models/user.py`, `backend/app/schemas/auth.py`, `backend/app/utils/auth.py`, `backend/app/utils/broker_crypto.py`, `backend/app/utils/safe_log.py`, `backend/docs/tickets/be-bug-004-session-audit.md`.
- **Objetivo (cumplido):** se validaron directamente (no solo por descripción documental) los mecanismos de seguridad ya citados como candidatos REUSE en LEGACY-AUDIT-021/023/025/046, y `be-bug-004-session-audit.md` añadió contexto sustancial al incidente de pool (LEGACY-AUDIT-065).
- **Resultado:** confirmados por código LEGACY-AUDIT-021/022/023/027/046 (promovidos de `PENDIENTE DE VALIDACIÓN`/documental a `VERIFICADO`, manteniendo su clasificación `CANDIDATE`, conforme a la regla de esta corrección). 11 hallazgos nuevos (LEGACY-AUDIT-055 a 065), incluido uno crítico (LEGACY-AUDIT-060 — columnas para credenciales sin garantía de cifrado en la capa ORM en `user.py`, contradiciendo el cifrado de `broker_crypto.py`; protección efectiva pendiente de Lote 5/Lote 7) cuya resolución final depende del Lote 5.
- **Entregable:** ver tabla de transición de archivo→estado y hallazgos nuevos en el informe de cierre de esta tarea.
- **Dependencias:** ninguna (cumplidas).
- **Criterios de cierre (cumplidos):** los 13 archivos con estado `REVIEWED_FULL`; cada hallazgo afectado promovido a `VERIFICADO` o mantenido como candidato con motivo explícito documentado.

### Lote 2 — Dominio, persistencia y catálogo POINT1 — ✅ COMPLETADO (`LEGACY-AUDIT-L02`)

- **Rutas incluidas (14, todas `REVIEWED_FULL`):** `backend/alembic.ini`, `backend/alembic/README`, `backend/alembic/env.py`, `backend/alembic/script.py.mako`, `backend/app/database.py`, `backend/app/models/__init__.py`, `backend/app/models/user_profile.py`, `backend/app/schemas/user_profile.py`, `docker-compose.yml`, `backend/app/models/signal.py`, `backend/app/models/trade.py`, `backend/app/models/strategy_spec.py`, `backend/app/models/strategy_spec_seed.py`, `backend/app/models/pending_execution.py`.
- **Tarea adicional (cumplida, no contaba en el recuento de 260):** lectura completada de `backend/alembic/versions/a27cf55ab06f_freyja2_seed_canonical_catalog.py` (858/858 líneas; antes `REVIEWED_PARTIAL`, ~120 líneas) — promovida a `REVIEWED_FULL`.
- **Objetivo (cumplido):** confirmado que `backend/app/database.py` soporta ambos dialectos deliberadamente y que el propio código documenta que producción es PostgreSQL (LEGACY-AUDIT-002 resuelto); validados los campos reales de `Signal`/`Trade`/`PendingExecution` contra la prosa de ARQUITECTURA.md (LEGACY-AUDIT-006, con matices de tipado no capturados por el documento); confirmado `strategy_spec.py`/`strategy_spec_seed.py` contra la ficha del manifiesto (LEGACY-AUDIT-016, clasificación acertada).
- **Resultado:** confirmados por código LEGACY-AUDIT-002/005/006/009/014/016 (promovidos a `VERIFICADO`); LEGACY-AUDIT-007/008/033 reciben evidencia de modelo pero **no** se resuelven (dependen de código de servicio en Lote 4/5); LEGACY-AUDIT-060 recibe evidencia parcial nueva (migración de limpieza activa pero fail-open). 8 hallazgos nuevos (LEGACY-AUDIT-066 a 073), incluidos dos críticos: LEGACY-AUDIT-066 (esquema principal sin Alembic) y LEGACY-AUDIT-070 (dinero en `Float`, viola `CLAUDE.md` §6).
- **Entregable:** ver tabla de transición de archivo→estado y hallazgos nuevos en el informe de cierre de esta tarea.
- **Dependencias:** ninguna (cumplidas).
- **Criterios de cierre (cumplidos):** los 14 archivos con estado `REVIEWED_FULL`; migración de siembra promovida a `REVIEWED_FULL`.

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

- No se copió ningún archivo ni fragmento sustancial de código del repositorio legacy hacia Freyja 2.0, en ninguna versión de este documento, incluida esta (`L02`).
- No se ejecutó ningún código legacy, ninguna migración legacy (incluida `a27cf55ab06f`, leída pero nunca ejecutada), ni Alembic, Docker Compose, SQL o gestor de dependencias legacy.
- No se leyó ni mostró ningún secreto, credencial, clave, certificado ni contenido de `.env`. **En L02:** `docker-compose.yml` legacy contenía credenciales por defecto en texto plano para PostgreSQL/pgAdmin (LEGACY-AUDIT-068) — se registró su existencia, tipo de riesgo y ubicación, **sin reproducir los valores** en este documento ni en ninguna respuesta. Los fingerprints sha256 pinneados en `strategy_spec_seed.py` (hashes derivados de reglas de estrategia, no credenciales) tampoco se reprodujeron. Ningún dato personal ni credencial de broker real apareció en los 15 archivos leídos en L02.
- No se abrió ninguna base de datos legacy.
- **En L02 (a diferencia de la corrección anterior a L01, que no leyó archivos nuevos): se leyeron íntegramente 15 archivos nuevos del repositorio legacy vía `git show HEAD:<ruta>`** — los 14 pendientes del Lote 2 más la finalización de la migración de siembra (`a27cf55ab06f`, 858/858 líneas). Ningún archivo se restauró al working tree legacy (deliberadamente vaciado) ni se extrajo a disco fuera de la salida de `git show` leída directamente.
- No se modificó, formateó, instaló ni eliminó nada dentro del repositorio legacy — su estado (`HEAD` `44192410e70975a5f156db81f711e56bee63376b`, 288 archivos rastreados, working tree vaciado) es idéntico al registrado antes de L02 (ver §18, verificación final).
- No se importó historial de git del repositorio legacy hacia Freyja 2.0.
- No se realizó ningún `cherry-pick` ni operación de fusión entre repositorios.
- No se realizó ningún cambio en Notion como parte de esta tarea.
- No se realizó ningún `git add`, commit, branch, push, Pull Request ni cambio en GitHub dentro de Freyja 2.0 como parte de esta tarea.
- No se modificó ningún archivo de Freyja 2.0 distinto de `docs/audits/legacy-knowledge-audit.md`.

Búsqueda explícita realizada sobre el contenido añadido/modificado en esta actualización (L02) antes de su entrega: rutas `C:\Users\...`, nombres de usuario locales, contraseñas, tokens, claves de API, claves privadas, URLs con credenciales embebidas, contenido de `.env`, fragmentos largos de código, DDL extenso, catálogo/seeds completos, comandos de migración, instrucciones para ejecutar en REAL, recomendaciones de `cherry-pick` o de copiar migraciones. Resultado: no se detectó ningún elemento de la lista en el texto final; las credenciales por defecto de `docker-compose.yml` (LEGACY-AUDIT-068) se describieron sin reproducir sus valores (se preservan además las sanitizaciones ya aplicadas en versiones anteriores: la URL del remoto GitHub y las rutas locales `C:\Users\...`).

---

## 17. Verificación matemática de cobertura

Esta verificación se realiza contra el **apéndice completo de 288 filas incluido en este mismo documento (§19)**, no contra listas externas ni archivos auxiliares. El apéndice es la única fuente de verdad de qué ruta tiene qué estado y qué lote asignado; esta sección solo confirma, con comandos de solo lectura, que esa tabla es exacta. **Actualizada tras el cierre de `LEGACY-AUDIT-L02`.**

**Comandos de solo lectura ejecutados** (ninguno modifica el repositorio legacy; en L02 se leyó contenido real de 15 archivos vía `git show`, según el alcance autorizado de la tarea — ver §16):

1. `git -C <ruta-legacy> ls-tree -r --name-only HEAD | wc -l` → **288**, confirma el total de archivos rastreados en el commit auditado (sin cambio respecto a antes de L02).
2. Extracción de las 288 rutas de la primera columna del apéndice (§19) y comparación exacta (`comm -23`/`comm -13`) contra la salida del comando anterior → **sin ausencias, sin sobrantes**.
3. Recuento de rutas del apéndice (`wc -l` sobre las filas de la tabla) → **288**, y verificación de unicidad (`sort` + `uniq -d` sobre la primera columna) → **cero duplicados**.
4. Recuento por columna "Estado actual" del apéndice (`cut` + `sort` + `uniq -c`):

```
REVIEWED_FULL      53   (era 38; +15 por L02: 14 archivos + migración de siembra)
REVIEWED_PARTIAL    2   (era 3; −1 por L02: migración de siembra completada)
MANIFEST_ONLY      43   (era 48; −5 por L02: signal.py, trade.py, strategy_spec.py, strategy_spec_seed.py, pending_execution.py)
NAME_ONLY         190   (era 199; −9 por L02: alembic.ini, alembic/README, alembic/env.py, script.py.mako, database.py, models/__init__.py, user_profile.py, schemas/user_profile.py, docker-compose.yml)
EXCLUDED            0   (sin cambio)
---------------------
TOTAL             288   ✓ coincide con el punto 1
```

Verificación cruzada: `5 (MANIFEST_ONLY→FULL) + 9 (NAME_ONLY→FULL) = 14` archivos pendientes promovidos ✓, más 1 `REVIEWED_PARTIAL→FULL` (la migración) = **15 transiciones a `REVIEWED_FULL`** ✓, coincidiendo exactamente con `+15` de la fila anterior. `MANIFEST_ONLY + NAME_ONLY`: antes `48+199=247`; ahora `43+190=233`; diferencia `247−233=14` ✓ (los 14 archivos pendientes de L02; la migración no contaba en el recuento de pendientes por ser `REVIEWED_PARTIAL`, no `MANIFEST_ONLY`/`NAME_ONLY`).

5. Recuento por columna "Área" del apéndice → coincide exactamente con la tabla de §11 tras actualizarla: 10+10+8+7+6+3+9+3+4+10+4+2+12+18+69+6+1+2+62+14+28 = **288** ✓ (las 21 áreas no cambiaron de tamaño, solo "Autenticación y seguridad" y "Gobierno/cutover/postmortems" cambiaron de columnas internas Íntegros/Solo-manifiesto-nombre), sin solapamientos ni huecos contra el punto 2.
6. Recuento por columna "Lote asignado" del apéndice (excluyendo las filas con `—`; el Lote 1 ya no aparece — sus 13 filas pasaron a `—`):

```
Lote 3    10   Lote 8A   21   Lote 9A   18
Lote 4    15   Lote 8B   12   Lote 9B   14
Lote 5    15   Lote 8C   23   Lote 9C   13
Lote 6     4   Lote 8D   13   Lote 9D    6
Lote 7    18   Lote 8E   14   Lote 9E   12
                              Lote 9F   25
-------------------------------------------
Subtotal 62   Subtotal 83   Subtotal 88
```

`62 + 83 + 88 = 233` ✓, coincide exactamente con `MANIFEST_ONLY (43) + NAME_ONLY (190) = 233`. Filas con lote `—` (revisadas): **55** = `REVIEWED_FULL (53) + REVIEWED_PARTIAL (2)`. `233 + 55 + 0 (EXCLUDED) = 288` ✓.
7. Cada sublote 8A–8E y 9A–9F verificado individualmente ≤ 25 archivos: máximo observado = 23 (8C) y 25 (9F) — ambos dentro del límite (sin cambio, L02 no tocó los Lotes 8/9).
8. **Recuento de la matriz de trazabilidad (§5), actualizado tras L02:** 73 filas `LEGACY-AUDIT-NNN` (65 tras L01 + 8 nuevas, `LEGACY-AUDIT-066` a `073`, sin huecos ni renumeración). Recuento de clasificación por patrón exacto sobre las 73 filas: `REUSE CANDIDATE` 29 (sin cambio), `REWRITE CANDIDATE` 6 (sin cambio), `REFERENCE` 25 (era 22, +3: LEGACY-AUDIT-069/072/073; como celda de clasificación única — una fila, LEGACY-AUDIT-030, tiene clasificación compuesta `REJECT/REFERENCE` y se cuenta una sola vez, bajo REJECT), `REJECT` 13 (era 8, +5: LEGACY-AUDIT-066/067/068/070/071). `29 + 6 + 25 + 13 = 73` ✓.
9. **Verificación de que ningún archivo fuera de L02 cambió de estado o lote:** diferencia entre el apéndice actual y el previo a esta tarea (tras L01), restringida a las columnas "Estado actual"/"Lote asignado" → exactamente 15 filas difieren: las 14 rutas del Lote 2 más la migración de siembra, todas listadas en §15. Cero diferencias en cualquier otra fila.

Todas las comprobaciones anteriores son reproducibles releyendo el apéndice/matriz de este documento y aplicando los mismos comandos; ninguna depende de un archivo fuera de este documento ni de scripts auxiliares guardados en el repositorio.

Las rutas exactas de cada estado están enumeradas en su totalidad: las de los lotes/sublotes pendientes en §15; las de `REVIEWED_FULL`/`REVIEWED_PARTIAL`/`MANIFEST_ONLY` como evidencia de cada hallazgo en §5 y §6–9, y la totalidad exacta de las 288 en el apéndice de §19.

---

## 18. Estado del repositorio legacy: inicial vs. final de `LEGACY-AUDIT-L02`

| | Antes de L02 | Después de L02 |
|---|---|---|
| `HEAD` | `44192410e70975a5f156db81f711e56bee63376b` | `44192410e70975a5f156db81f711e56bee63376b` (sin cambio) |
| Archivos rastreados | 288 | 288 (sin cambio) |
| `git status -sb` (líneas) | 288 (todo `D`, working tree vaciado) | 288 (sin cambio) |
| Archivos con contenido leído por esta auditoría durante L02 | — | 15 (los 14 archivos del Lote 2 + finalización de la migración de siembra), todos vía `git show HEAD:<ruta>`, sin restaurar el working tree |

---

## 19. Apéndice completo — los 288 archivos rastreados

Cada una de las 288 rutas rastreadas en `HEAD` (`44192410e70975a5f156db81f711e56bee63376b`) aparece **exactamente una vez** en la tabla siguiente, ordenada alfabéticamente por ruta. Ninguna fila usa comodines ni agrupa rutas. El lote asignado es `—` para los 28 archivos ya revisados (íntegra o parcialmente); para los 260 restantes es el lote o sublote concreto de §15.

| Ruta relativa | Área | Estado actual | Lote asignado | Observación |
|---|---|---|---|---|
| `.claude/launch.json` | Autenticación y seguridad | REVIEWED_FULL | — | L01 — ver LEGACY-AUDIT-055 |
| `.github/workflows/backend-ci.yml` | Autenticación y seguridad | REVIEWED_FULL | — | L01 — ver LEGACY-AUDIT-056 |
| `.github/workflows/frontend-ci.yml` | Autenticación y seguridad | REVIEWED_FULL | — | L01 — ver LEGACY-AUDIT-056 |
| `.gitignore` | Autenticación y seguridad | REVIEWED_FULL | — | L01 — ver LEGACY-AUDIT-057 |
| `ARQUITECTURA.md` | Documentación y ADR | REVIEWED_FULL | — | — |
| `MANUAL_USUARIO.md` | Documentación y ADR | REVIEWED_FULL | — | — |
| `README.md` | Documentación y ADR | REVIEWED_FULL | — | — |
| `ROADMAP.md` | Documentación y ADR | REVIEWED_FULL | — | — |
| `backend/.env.example` | Autenticación y seguridad | REVIEWED_FULL | — | L01 — ver LEGACY-AUDIT-058 (valores no reproducidos) |
| `backend/Dockerfile` | Operación/observabilidad | NAME_ONLY | Lote 7 | — |
| `backend/LEGACY_TRADING.md` | Gobierno/cutover/postmortems | REVIEWED_FULL | — | — |
| `backend/alembic.ini` | Persistencia y migraciones | REVIEWED_FULL | — | L02 — sin URL embebida, `sqlalchemy.url` vacío (se resuelve en `env.py`) |
| `backend/alembic/README` | Persistencia y migraciones | REVIEWED_FULL | — | L02 — plantilla estándar sin modificar |
| `backend/alembic/env.py` | Persistencia y migraciones | REVIEWED_FULL | — | L02 — `target_metadata` exclusivo de `Freyja2Base`, nunca el esquema legacy principal |
| `backend/alembic/script.py.mako` | Persistencia y migraciones | REVIEWED_FULL | — | L02 — plantilla estándar de Alembic sin modificar |
| `backend/alembic/versions/57ce4f19beb7_freyja2_canonical_catalog.py` | Catálogo/POINT1 | REVIEWED_FULL | — | — |
| `backend/alembic/versions/a27cf55ab06f_freyja2_seed_canonical_catalog.py` | Catálogo/POINT1 | REVIEWED_FULL | — | L02 — 858/858 líneas leídas; ver LEGACY-AUDIT-014 |
| `backend/app/__init__.py` | Operación/observabilidad | NAME_ONLY | Lote 7 | — |
| `backend/app/config.py` | Operación/observabilidad | NAME_ONLY | Lote 7 | — |
| `backend/app/database.py` | Persistencia y migraciones | REVIEWED_FULL | — | L02 — ver LEGACY-AUDIT-002/060/066/067 |
| `backend/app/freyja2/__init__.py` | Catálogo/POINT1 | REVIEWED_FULL | — | — |
| `backend/app/freyja2/persistence/__init__.py` | Catálogo/POINT1 | REVIEWED_FULL | — | — |
| `backend/app/freyja2/persistence/base.py` | Persistencia y migraciones | REVIEWED_FULL | — | — |
| `backend/app/freyja2/persistence/identity.py` | Persistencia y migraciones | REVIEWED_FULL | — | — |
| `backend/app/freyja2/persistence/models.py` | Catálogo/POINT1 | REVIEWED_FULL | — | — |
| `backend/app/main.py` | Operación/observabilidad | MANIFEST_ONLY | Lote 7 | MANIFEST_ONLY solo a nivel de 15 endpoints anotados en el manifiesto; archivo completo no leído |
| `backend/app/models/__init__.py` | Dominio | REVIEWED_FULL | — | L02 — agregador de re-exports, sin lógica propia |
| `backend/app/models/broker_audit_log.py` | Autenticación y seguridad | REVIEWED_FULL | — | L01 — ver LEGACY-AUDIT-022/059 |
| `backend/app/models/broker_connection.py` | Brokers y ejecución | NAME_ONLY | Lote 5 | — |
| `backend/app/models/demo_account.py` | Operación/observabilidad | NAME_ONLY | Lote 7 | — |
| `backend/app/models/pending_execution.py` | Ciclo de vida | REVIEWED_FULL | — | L02 — ver LEGACY-AUDIT-008/073 |
| `backend/app/models/scanner_heartbeat.py` | Operación/observabilidad | NAME_ONLY | Lote 7 | — |
| `backend/app/models/signal.py` | Dominio | REVIEWED_FULL | — | L02 — ver LEGACY-AUDIT-006/009/071/072 |
| `backend/app/models/strategy.py` | Dominio | NAME_ONLY | Lote 4 | — |
| `backend/app/models/strategy_spec.py` | Dominio | REVIEWED_FULL | — | L02 — ver LEGACY-AUDIT-016 |
| `backend/app/models/strategy_spec_seed.py` | Dominio | REVIEWED_FULL | — | L02 — ver LEGACY-AUDIT-016 |
| `backend/app/models/trade.py` | Dominio | REVIEWED_FULL | — | L02 — ver LEGACY-AUDIT-006/007/033/070/071 |
| `backend/app/models/trade_audit_log.py` | Autenticación y seguridad | REVIEWED_FULL | — | L01 — ver LEGACY-AUDIT-022/059 |
| `backend/app/models/user.py` | Autenticación y seguridad | REVIEWED_FULL | — | L01 — ver LEGACY-AUDIT-046/060 (crítico) |
| `backend/app/models/user_profile.py` | Dominio | REVIEWED_FULL | — | L02 — ver LEGACY-AUDIT-005 |
| `backend/app/schemas/__init__.py` | Operación/observabilidad | NAME_ONLY | Lote 7 | — |
| `backend/app/schemas/auth.py` | Autenticación y seguridad | REVIEWED_FULL | — | L01 — ver LEGACY-AUDIT-061 |
| `backend/app/schemas/broker.py` | Brokers y ejecución | NAME_ONLY | Lote 5 | — |
| `backend/app/schemas/catalog.py` | Proveedores y datos | NAME_ONLY | Lote 7 | — |
| `backend/app/schemas/user_profile.py` | Dominio | REVIEWED_FULL | — | L02 — `UserProfileSet.symbols`/`strategies` son `List[str]`, `UserProfileOut` los expone como `str` (CSV, igual que la columna ORM) — asimetría de forma, no de contenido |
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
| `backend/app/utils/auth.py` | Autenticación y seguridad | REVIEWED_FULL | — | L01 — ver LEGACY-AUDIT-027/046/062 |
| `backend/app/utils/broker_crypto.py` | Autenticación y seguridad | REVIEWED_FULL | — | L01 — ver LEGACY-AUDIT-023/063 |
| `backend/app/utils/dates.py` | Indicadores | NAME_ONLY | Lote 4 | — |
| `backend/app/utils/indicators.py` | Indicadores | NAME_ONLY | Lote 4 | — |
| `backend/app/utils/notifications.py` | Noticias/notificaciones | MANIFEST_ONLY | Lote 3 | — |
| `backend/app/utils/perf_log.py` | Operación/observabilidad | NAME_ONLY | Lote 7 | — |
| `backend/app/utils/pool_instrumentation.py` | Operación/observabilidad | NAME_ONLY | Lote 7 | — |
| `backend/app/utils/safe_log.py` | Autenticación y seguridad | REVIEWED_FULL | — | L01 — ver LEGACY-AUDIT-021/064 |
| `backend/app/utils/signal_normalizer.py` | Indicadores | NAME_ONLY | Lote 4 | — |
| `backend/app/utils/trade_audit.py` | Operación/observabilidad | NAME_ONLY | Lote 7 | — |
| `backend/docs/tickets/be-bug-004-session-audit.md` | Gobierno/cutover/postmortems | REVIEWED_FULL | — | L01 — ver LEGACY-AUDIT-065 |
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
| `docker-compose.yml` | Catálogo/POINT1 | REVIEWED_FULL | — | L02 — ver LEGACY-AUDIT-068/069; valores de credenciales no reproducidos |
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

**Verificación de esta tabla (actualizada tras `LEGACY-AUDIT-L02`):** 288 filas, 0 rutas duplicadas, 0 rutas ausentes o sobrantes respecto a `git ls-tree -r --name-only HEAD` (ver §17). Totales por estado: `REVIEWED_FULL` 53, `REVIEWED_PARTIAL` 2, `MANIFEST_ONLY` 43, `NAME_ONLY` 190, `EXCLUDED` 0. Los 13 archivos del Lote 1 pasaron de `NAME_ONLY`/`Lote 1` a `REVIEWED_FULL`/`—` (sin cambio en esta tarea). En esta tarea (`L02`), los 14 archivos del Lote 2 pasaron de `NAME_ONLY`/`MANIFEST_ONLY` + `Lote 2` a `REVIEWED_FULL`/`—`, y la migración de siembra pasó de `REVIEWED_PARTIAL`/`—` a `REVIEWED_FULL`/`—`; ninguna otra fila cambió de estado ni de lote.

---

## Conclusión

**AUDITORÍA PRELIMINAR — REQUIERE REVISIÓN POR LOTES**

`LEGACY-AUDIT-L01` (Lote 1 — Gobierno, ADR, postmortems y seguridad, 13 archivos) y `LEGACY-AUDIT-L02` (Lote 2 — Dominio, persistencia y catálogo POINT1, 14 archivos + finalización de la migración de siembra) quedan completados. La auditoría general sigue siendo preliminar: quedan 233 archivos sin evidencia directa, distribuidos en los Lotes 3–7 y los sublotes 8A–8E/9A–9F pendientes (§15). `L03` (Proveedores, datos, noticias y notificaciones, 10 archivos) es el siguiente lote, siguiendo el orden ya aprobado — no alterado por esta tarea. No se publica, no se hace commit, no se modifica GitHub ni Notion. El documento queda a la espera de que el Arquitecto autorice la ejecución del siguiente lote.

**LEGACY-AUDIT-L02 COMPLETADO — INFORME LISTO PARA REVISIÓN**
