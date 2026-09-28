# Localización de un patrón de vela (v1)

- **Estado:** vigente. Contrato temporal, antes de escribir código.
- **Fecha:** 2026-09-29.
- **Tarea:** POINT4-CONTEXT-001 (5 de 7 del punto 4). Ver el reparto acordado en la propia página
  de Notion de la tarea (corregido el 29-09-2026): esto **no** reinterpreta la tendencia, que
  `candlestick_single.py`/`candlestick_multi.py` ya resuelven por completo; añade una dimensión
  nueva, la **localización** respecto a estructura de precio del punto 2 y figuras del punto 3.
- **Depende de:** [instancia-de-patron-de-vela.md](instancia-de-patron-de-vela.md) (el patrón que
  se localiza), `estructura-de-precio.md` (pivotes confirmados del punto 2),
  [instancia-de-figura.md](instancia-de-figura.md) e
  [hipotesis-de-figura.md](hipotesis-de-figura.md) sección 5 (`known_at`, `published_at`,
  procedencia — el mismo vocabulario, reutilizado, no reinventado).
- **Código:** `backend/src/freyja_backend/domain/candlestick_location.py` (pendiente de esta
  tarea). Dominio puro, sin E/S.

## 1. Qué añade esta pieza y qué no

- **Añade**: si un patrón de vela ya detectado (`CandlePatternInstance` de SINGLE-001/MULTI-001)
  ocurre cerca de un nivel de precio que Freyja **podía conocer** en ese momento — un pivote
  confirmado del punto 2, o el borde de una figura chartista del punto 3.
- **No reinterpreta la tendencia.** No toca `CandlePatternInstance`, no cambia su `state`, no
  añade una evaluación a su historial. Es un registro **separado**, referenciando al patrón por su
  identidad, igual que `AmbiguousGeometry` es separado de `CandlePatternInstance` y
  `PatternHypothesis` es separado de `PatternInstance`.
- **No combina evidencias de varios patrones.** Localizar un patrón cerca de un nivel es un hecho
  sobre **ese** patrón; combinar varios patrones y figuras en una lectura conjunta es
  POINT4-HYPOTHESIS-001, que ya tiene ese criterio de aceptación.

## 2. El instante de referencia: `evaluated_at` no es "cuándo se ejecutó esto"

Cada evaluación de localización tiene su propio `evaluated_at`, igual que una `PatternEvaluation`
o una `HypothesisEvaluation`. **No es el instante en que el código corrió**: es el instante en que
el resultado de esa evaluación concreta se volvió conocible, calculado como el máximo entre:

- el instante propio del patrón (`source.observed_at` o `.latest.evaluated_at`, según el modelo de
  `instancia-de-patron-de-vela.md`), y
- el `known_at` (pivotes) o `known_at`/`published_at` (figuras del punto 3) de **cada** nivel que
  esa evaluación usa.

Esto hace que `evaluated_at` sea una función pura de la estructura misma, no de cuándo se llamó al
detector: volver a ejecutar la localización más tarde, con más velas, da la **misma** secuencia de
evaluaciones con los **mismos** instantes — estabilidad de replay, verificada con pruebas (sección
6).

## 3. Qué pasa si un pivote o una figura se confirma o se publica después del patrón

**No se usa en la primera evaluación.** La primera evaluación de un patrón usa únicamente los
niveles cuyo `known_at` (pivotes) o `known_at`/`published_at` (figuras) son **anteriores o iguales**
al instante propio del patrón. Un pivote que se confirma más tarde, o una figura que una política
de solapamiento retuvo hasta más tarde (`published_at`, solo el diamante la tiene —
`detectores-de-expansion.md` sección 10, `hipotesis-de-figura.md` sección 5), no forma parte de esa
primera lectura: no estaba ofrecido cuando el patrón se resolvió, aunque su geometría ya existiera
en la serie.

**Cuando se confirma o se publica, se añade una evaluación nueva** — nunca se reescribe la
anterior. La nueva evaluación:
- Usa el conjunto **acumulado** de niveles conocibles hasta ese instante (los de antes, más los
  recién conocibles).
- Se fecha (`evaluated_at`) en el máximo `known_at`/`published_at` entre los niveles que la
  componen (sección 2) — no en el instante en que se ejecutó el replay.
- Solo se añade si cambia algo observable (el estado, o el conjunto de niveles cercanos): una
  vela que confirma un pivote lejano que no cambia nada no genera una evaluación nueva, mismo
  principio de deduplicación que `PatternHypothesis` (`hipotesis-de-figura.md`, decisión #11).

La evaluación anterior **no se toca**. Sigue afirmando, para siempre, lo que Freyja podía saber en
su propio instante — igual que ninguna evaluación de un `PatternInstance` se reescribe cuando una
posterior la sigue.

## 4. Figuras del punto 3: `known_at`, `published_at` **y** procedencia

Un nivel derivado de una figura chartista exige, para poder usarse en una evaluación con instante
de referencia `T`:

1. **`known_at` de la figura no es `None`** (hay recepciones para toda la ventana de anclas —
   `pattern_detection.known_at_of`) **y** `known_at ≤ T`.
2. **Si la figura tiene `published_at`** (solo el diamante, cuando una política de solapamiento la
   retuvo), **`published_at ≤ T` también**. Sin este segundo requisito, se usaría una figura que en
   el instante `T` aún no había sido ofrecida como tal, aunque su geometría ya se conociera.
3. **La procedencia de la figura (`provenance`, cuando la figura ya tiene ruptura) se registra
   como evidencia**, no como filtro adicional: la procedencia describe la ruptura, un hecho
   distinto de si la frontera geométrica podía usarse como nivel. Una figura `GEOMETRICALLY_VALID`
   sin ruptura todavía no tiene procedencia que registrar, y su frontera se usa igual si cumple 1 y
   2. Cuando sí hay procedencia, se copia tal cual a la evidencia de esta pieza
   (`LEVEL`, sección 5) para que quede auditable de dónde viene el nivel usado — nunca se
   recalcula, nunca se infiere de otra cosa (mismo principio que `hipotesis-de-figura.md`, sección
   5: «la procedencia se lee, no se recalcula»).

Un pivote del punto 2 (soporte/resistencia simple, sin figura) solo exige la condición 1, con su
propio `confirmed_at` en el papel de `known_at`: no tiene `published_at` ni procedencia (esos
conceptos son propios de una figura con ruptura).

## 5. Evidencia: `LEVEL`

Por cada nivel cercano encontrado, una evidencia `LEVEL` con:

- `kind`: `PIVOT` o `CHART_PATTERN_BOUNDARY`.
- `label`: qué es (`HIGH pivot`, `RECTANGLE UPPER boundary`…).
- `price`: el precio exacto del nivel en el instante de referencia (una frontera inclinada se
  evalúa en ese instante, con la misma aritmética exacta que ya usa
  `pattern_detection.line_through`).
- `distance_fraction`: la distancia entre el patrón y el nivel, como fracción del rango de
  referencia (versionado, sección 7).
- `source_known_at`, y cuando aplique `source_published_at`, `source_provenance`: copiados tal
  cual del nivel de origen (sección 4).

Cuando no hay ningún nivel cerca, una evidencia `LEVELS_CHECKED` con cuántos niveles se
comprobaron y la distancia mínima encontrada (`distance_fraction` del más cercano) — para poder
distinguir «se comprobó y no hay nada cerca» de «no se comprobó nada» con solo leer la evidencia.

## 6. Dos estados, nunca confundidos

| Estado | Significa |
| ------ | --------- |
| `NEAR_LEVEL` | Hay al menos un nivel conocible en el instante de referencia, y el patrón está dentro de la tolerancia de al menos uno. |
| `NOT_NEAR_LEVEL` | Hay estructura suficiente para juzgar (min_history superado, fuente autorizada) y **se comprobó**, pero ningún nivel conocible está lo bastante cerca. |
| `INSUFFICIENT_DATA` | No se pudo juzgar: menos velas que `min_history`, fuente no autorizada, datos inválidos. |

**Un pivote o una figura que aún no se ha confirmado/publicado no es «datos insuficientes».** Es,
correctamente, «ningún nivel conocido ahí todavía» (`NOT_NEAR_LEVEL`, si por lo demás hay
suficiente estructura para juzgar) — declarar `INSUFFICIENT_DATA` en ese caso sería tan incorrecto
como inventar un nivel que todavía no existía: `INSUFFICIENT_DATA` se reserva para cuando **no se
puede juzgar en absoluto**, no para cuando se juzgó y el resultado, sinceramente, es que no hay
nada confirmado cerca. Cuando ese pivote se confirme más tarde, la sección 3 explica cómo se añade
la evaluación que sí lo ve, sin tocar la anterior.

## 7. Identidad, versión y parámetros

- **Registro propio** (`PatternLocation`), no una `CandlePatternInstance`: referencia al patrón por
  su `candle_pattern_instance_id`, nunca lo modifica.
- **Historial de solo añadir**, igual que `PatternHypothesis`: instantes estrictamente crecientes,
  una evaluación nueva solo cuando algo observable cambia.
- **Versión propia** (`candle-location-params-v1`), independiente de
  `single-candle-params-v1`/`multi-candle-params-v1`/`three-candle-params-v1`: mismo principio de
  versionado por familia que corrigió POINT4-MULTI-001 antes de su segunda entrega — un cambio en
  la tolerancia de «cerca» nunca debe desplazar la identidad de un patrón ya guardado, y viceversa.
- Umbral de tolerancia (`distance_fraction` máximo para `NEAR_LEVEL`) provisional y sin validar:
  PARAMS-VALIDATION-001 al introducirlo.

## 8. Replay: casos que el código debe superar

Registrados aquí antes de escribir el código, como especificación:

1. **Llegada tardía de un pivote.** Un patrón se resuelve en `T0` sin pivotes conocibles
   todavía cerca (`NOT_NEAR_LEVEL` o `INSUFFICIENT_DATA` según haya o no suficiente historia). Unas
   velas más tarde, un pivote cercano se confirma. La localización gana una **segunda** evaluación,
   fechada en el `known_at` de ese pivote, que ahora dice `NEAR_LEVEL`. La primera evaluación sigue
   diciendo lo que decía.
2. **Figura inicialmente cubierta por otra.** Una figura (p. ej. una ventana dentro de un
   diamante) tiene `known_at ≤ T0` pero `published_at > T0` porque una política de solapamiento la
   retuvo. En `T0` no cuenta como nivel conocido (aunque su geometría ya existiera). Cuando se
   publica, una evaluación nueva la incorpora, fechada en su `published_at` — nunca en `T0` ni en
   su `known_at`.
3. **Replay estable.** Recalcular la localización de un patrón ya resuelto, con más velas
   disponibles de las que había cuando se resolvió, reproduce exactamente la misma secuencia de
   evaluaciones (mismos instantes, misma evidencia) que se habría obtenido evaluando paso a paso —
   **rehaciendo la misma secuencia de llamadas** (primera restringida al instante del patrón,
   después encadenando `previous`), no con una única llamada `previous=None`: por diseño (sección
   3), esa primera llamada siempre se restringe a `pattern_at`, sin importar cuántas velas o qué
   `observed_at` se le pasen, así que una sola llamada nunca reproduce el estado acumulado que solo
   alcanza una evaluación posterior encadenada.

`as_of` (la vela más nueva efectivamente leída) nunca puede superar el `evaluated_at` de esa misma
evaluación: una evaluación no puede afirmar haber leído una vela posterior a lo que ella misma
puede saber, aunque el contexto de la llamada tenga velas más recientes disponibles. Se acota
explícitamente (`min(as_of, evaluated_at)` para las evaluaciones con candidatos; `min(as_of,
knowability_cutoff)` cuando falta estructura suficiente para evaluar) en vez de asumir que la vela
más nueva del lote es la vela más nueva relevante para esa evaluación en concreto.

## 9. Lo que este documento no decide

Los umbrales numéricos exactos de tolerancia (versionados, provisionales); cómo se combina esta
evidencia con la de otros patrones o figuras en una hipótesis (POINT4-HYPOTHESIS-001); si el
mercado/producto/instrumento aportan una interpretación adicional más allá de la identidad de la
serie (abierto, ver la página de Notion de la tarea); persistencia, señales, órdenes.
