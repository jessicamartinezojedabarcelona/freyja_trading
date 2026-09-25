# Instantánea de contexto (snapshot) de una hipótesis (v1)

- **Estado:** vigente. Desarrolla la sección 7 de
  [`contexto-y-tendencia.md`](contexto-y-tendencia.md) sin cambiarla.
- **Fecha:** 2026-09-25
- **Tarea:** POINT2-SNAPSHOT-001 (6 de 7 del punto 2).
- **Depende de:** POINT2-POLICY-001 ([`politica-de-tendencia.md`](politica-de-tendencia.md)).
- **Código:** `backend/src/freyja_backend/domain/context_snapshot.py` (dominio puro),
  `application/context_snapshot_service.py` y `repositories/context_snapshot_repository.py`
  (persistencia), migración `0015_context_snapshots`.
- **Versión del formato:** `context-snapshot-v1`.

Una **instantánea** es la fotografía exacta que Freyja tenía cuando evaluó una hipótesis: qué
mostraban el contexto y la tendencia de los dos marcos, y qué concluyó de ello la política de
tendencia. Se guarda una vez, se lee tal cual y no se recalcula nunca.

## 1. Qué es y qué no es

- **Es un registro, no un cálculo.** Es un valor inmutable que se construye una vez. Leerla no
  reclasifica, no vuelve a juzgar ni consulta velas: devuelve lo que se guardó. Una
  reclasificación futura, una política nueva o una vela revisada no la alcanzan; generan una
  instantánea **nueva**.
- **Separa lo observado de lo juzgado.** `observed` es lo que mostró el mercado; `judged` es lo
  que la política hizo con ello. Ninguna de las dos secciones contiene decisión ni ejecución:
  ni lado, ni entrada, ni orden, ni posición, ni `confidence`. Un test lo comprueba sobre los
  campos y sobre las claves del documento.
- **No es una señal ni una estrategia.** No activa ejecución real ni cambia el motor de
  decisión.

## 2. Todavía no existe `Signal` (decisión técnica)

La tarea habla de guardar la instantánea «en cada Signal». **En el código de Freyja 2.0 aún no
existe `Signal` ni `StrategySpec`** (solo en la auditoría del proyecto antiguo). Por eso la
instantánea es una tabla propia, independiente, y **la futura `Signal` la referenciará** por su
`id`; hoy no hay ninguna referencia hacia ella ni desde ella.

Consecuencias:

- El vínculo con el `StrategySpec` y su versión vivirá en la `Signal`. La instantánea guarda la
  **versión de la política de tendencia** (`policy_version`), que es la parte de la estrategia
  que interviene aquí.
- **No se ha añadido ningún endpoint.** Sin señales que la usen, un endpoint de lectura no
  tendría consumidor. Lo que sí existe es la serialización: `ContextSnapshot.document()` y su
  inversa `snapshot_from_document()` (sección 5). El endpoint llegará con `Signal`.
- **No se rellenan señales antiguas** con tendencias inventadas: nada se genera con
  retroactividad.

## 3. Contenido

### Cabecera

`snapshot_version`, `instrument_id`, `data_source`, `product_type`, `observed_at` (el instante
al que se refiere la observación; solo se leyeron velas cerradas en o antes de ese instante) y
`computed_at` (el instante real en que se creó; nunca forma parte de la identidad).

### `observed` — lo que mostró el mercado

Para **cada marco** (`signal` y `context`), leído de sus propias velas y por separado:

| Campo | Contenido |
| ----- | --------- |
| `timeframe`, `trend` | Marco y estado de tendencia (incluye `INSUFFICIENT_DATA`). |
| `as_of`, `window_candles` | Cierre de la última vela cerrada leída y velas evaluadas. |
| `data_freshness`, `data_quality` | Vigencia y calidad de los datos. |
| `missing_data_reasons` | Por qué los datos no eran aptos (si no lo eran). |
| `insufficient_data_reasons` | Por qué no hay clasificación (si no la hay). |
| `swings` | Los puntos de giro confirmados en los que se apoya el estado (tipo, hora, precio, confirmación). |
| `evidence` | Los hechos legibles que sustentan el estado. |
| `window_swings`, `significance`, `pivot_k` | Parámetros con los que se leyeron, para poder reproducirlo. |

Y, comunes a la observación: `market_open`, `market_session` (solo Forex; `null` es «no aplica»,
nunca una sesión prestada), `weekday_utc`, `hour_utc`, `timezone` (`UTC`), `calendar_version`,
`context_version`, `structure_version` y `trend_definition_version`.

`INSUFFICIENT_DATA` **se guarda siempre con sus motivos**: nunca es solo una etiqueta.

### `judged` — lo que concluyó la política

`policy_version`, `required_relationship`, `orientation`, `outcome` (`COMPATIBLE`,
`INCOMPATIBLE` o `INSUFFICIENT_CONTEXT`), `context_compatible` (`true`, `false` o `null` cuando
no había contexto suficiente para juzgar), `reasons` y `evaluation_version`.

`reasons` está vacío **exactamente cuando** el resultado es `COMPATIBLE`; en cualquier otro caso
dice por qué no lo es. Sin política declarada, `policy_version` y `required_relationship` son
`null` y el resultado es `INSUFFICIENT_CONTEXT` con `POLICY_MISSING`: se guarda igualmente lo
observado.

### `explanation`

Texto legible, determinista, con las mismas palabras que los códigos, p. ej. *«signal 5m is
UPTREND; context 1h is DOWNTREND; policy p-v1 (WITH_TREND) judged a BULLISH hypothesis
INCOMPATIBLE: RELATIONSHIP_NOT_SATISFIED.»* Con esto una señal nueva puede explicar por qué el
contexto era compatible o no.

## 4. Identidad e inmutabilidad

- **Identificada por su contenido.** `content_hash` es el sha256 del documento canónico (claves
  ordenadas, sin espacios, precios como texto decimal exacto) **sin `computed_at`**.
  `snapshot_id` es el UUID por nombre (v5) de ese hash. La misma observación, juzgada por la
  misma política, es siempre la misma instantánea: se guarda una vez y se conserva la primera
  (con su `computed_at` original).
- **Reproducible.** Mismas velas + mismo instante + mismos parámetros + misma política ⇒ mismo
  documento. Sin aleatoriedad ni reloj salvo `computed_at`.
- **Sin _look-ahead_.** Las velas que cierran después de `observed_at`, y la que está en curso,
  se ignoran: añadir futuro a las series no cambia la instantánea (probado).
- **Inmutable en la base de datos.** Un trigger rechaza cualquier `UPDATE` (igual que en las
  velas); no hay ruta de actualización ni siquiera en el código. Un `INSERT … ON CONFLICT DO
  UPDATE` tampoco puede sobrescribirla.
- **Solo se guarda tal cual.** Al leerla se comprueba que el documento guardado sigue
  correspondiendo a su `content_hash`; si no, se rechaza (`SnapshotIntegrityError`) y no se
  «repara».
- **Sin importes en coma flotante** (CLAUDE.md §6): los precios van como texto decimal; los
  instantes, en UTC.

`DELETE` no está bloqueado, igual que con las velas, para permitir una política de retención
futura; cuando exista `Signal`, la clave foránea protegerá las referenciadas. Es lo único que
hoy no impide el esquema y se anota aquí para que se pueda corregir.

## 5. Serialización

`ContextSnapshot.document()` produce JSON puro (cadenas, números enteros, booleanos, listas,
`null`): precios en texto decimal exacto e instantes UTC terminados en `Z`.
`snapshot_from_document()` lo lee **sin derivar nada**: no recalcula una tendencia ni rellena un
campo ausente. Un documento al que le falta algo, con un valor desconocido, un instante sin zona
o no UTC, o que se contradice, se rechaza con `InvalidContextSnapshotError`.

## 6. Persistencia (`freyja2_context_snapshots`)

- **`document`** (JSONB) es la instantánea completa. El resto de columnas son **copias** de sus
  hechos principales (tendencias, calidad, sesión, política, relación, orientación, resultado,
  compatibilidad, motivos) para poder buscar sin abrir el documento.
- **Restricciones que impiden una fila incoherente:** cada copia debe coincidir con el
  documento (`document_matches_columns`); `computed_at >= observed_at`; los valores de
  tendencia, relación, orientación y resultado pertenecen a su conjunto cerrado;
  `policy_version` y `required_relationship` van juntas o ninguna; `context_compatible` es
  coherente con el resultado; `reasons` está vacío solo si es `COMPATIBLE`; `content_hash`
  único.
- Claves foráneas al instrumento, la fuente y los dos marcos del catálogo.
- **No pertenece a ninguna cuenta**: es dato de mercado y lo que una política concluyó de él.
- La migración **se niega a bajar** (`downgrade`) mientras haya instantáneas guardadas.

### Aplicarla en Neon

Render nunca ejecuta migraciones. El script equivalente está en
[`docs/operations/neon-0015-context-snapshots-manual.sql`](../operations/neon-0015-context-snapshots-manual.sql):
se pega entero en el SQL Editor de Neon y se ejecuta una vez. Es todo o nada y aborta si la base
no está en `0014_kraken_data_source` o si ya se ejecutó. Un test comprueba que deja
exactamente el mismo esquema que Alembic (columnas, restricciones, índice, trigger, función y
revisión).

## 7. Lo que este contrato no decide

- La entidad `Signal`, su tabla y el vínculo con `StrategySpec` (puntos posteriores).
- Un endpoint de lectura y la presentación en pantalla (llegan con `Signal`).
- Quién genera las instantáneas ni cuándo: esta tarea define el registro, no el proceso que lo
  produce.
- Retención y borrado.
- Si `trend-v1` acierta. Sigue **sin validar**: la instantánea conserva lo que se creyó, no
  garantiza que fuese correcto.

## 8. Decisiones técnicas tomadas al redactar

Registradas aquí para que se puedan corregir; ninguna es de producto.

1. Tabla independiente que la futura `Signal` referenciará, por no existir aún `Signal`.
2. Sin endpoint por ahora; sí serialización estable.
3. Identidad por contenido (hash) con `computed_at` fuera, para que repetir la misma
   observación no cree duplicados.
4. El documento completo más copias buscables atadas por restricciones, en lugar de
   normalizar swings y evidencias en tablas.
5. `DELETE` permitido por ahora (retención futura); `UPDATE` bloqueado.
6. La explicación se escribe en inglés, con las palabras de los códigos; la interfaz podrá
   traducirla a partir de ellos.
