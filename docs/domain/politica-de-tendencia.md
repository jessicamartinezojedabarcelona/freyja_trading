# Política de tendencia de una estrategia (v1)

- **Estado:** vigente. Desarrolla las secciones 3 a 5 de
  [`contexto-y-tendencia.md`](contexto-y-tendencia.md) sin cambiarlas.
- **Fecha:** 2026-09-25
- **Tarea:** POINT2-POLICY-001 (5 de 7 del punto 2).
- **Depende de:** POINT2-TREND-001 (`trend-v1`, ver [`tendencia-estructural.md`](tendencia-estructural.md)).
- **Código:** `backend/src/freyja_backend/domain/trend_policy.py`. Dominio puro, sin E/S.
- **Versión de la evaluación:** `trend-policy-v1`.

Una **política de tendencia** es la parte de una versión de estrategia que declara **qué
contexto de tendencia necesita su hipótesis**. Este documento fija su forma, sus
validaciones y cómo se juzga si una hipótesis encaja con ella.

## 1. Qué es y qué no es

- **Es una comprobación de compatibilidad.** Responde `COMPATIBLE`, `INCOMPATIBLE` o
  `INSUFFICIENT_CONTEXT`, con los motivos.
- **No es una señal.** No contiene lado, entrada, orden, posición, confianza, puntuación ni
  probabilidad, y no puede expresarlos: un test lo comprueba sobre los campos de la política
  y de la evaluación. En `CRYPTO × SPOT`, «bajista» es abstenerse o salir, nunca un corto
  (contrato de contexto, sección 5); esta capa no convierte una orientación en una posición.
- **No es una estrategia.** Fibonacci, Bollinger, RSI y cualquier otro indicador o
  herramienta **no determinan por sí solos la relación con la tendencia**: la relación es un
  valor cerrado que la estrategia declara, y no hay forma de pasar un indicador en su lugar.
- **No toca `confidence` ni el motor de decisión**, y no activa ninguna ejecución REAL.
- Todavía no existe `StrategySpec` (punto 6). Esta política es la pieza que una versión de
  estrategia incorporará; hasta entonces se usa como valor independiente.

## 2. Contrato de la política

Todos los campos son obligatorios y explícitos. **Ninguno tiene valor por defecto**, para que
una línea olvidada no se convierta en permiso.

| Campo | Contenido |
| ----- | --------- |
| `version` | Identificador de la versión de la política. Inmutable. |
| `signal_timeframe` | Marco en el que se evaluará la hipótesis. |
| `context_timeframe` | Marco en el que se clasifica la tendencia que la enmarca. |
| `relationship` | `WITH_TREND`, `COUNTER_TREND`, `RANGE_ONLY`, `TRANSITION_ONLY` o `ANY`. |
| `signal_states` | Estados de tendencia admitidos en el marco de la señal. |
| `context_states` | Estados de tendencia admitidos en el marco de contexto. |
| `conflict_rule` | Qué hacer si ambos marcos están en tendencia y son opuestas. |
| `minimum_history` | Velas cerradas que cada clasificación debe haber leído como mínimo. |
| `trend_definition_version` | Definición de tendencia con la que se escribió la política (hoy `trend-v1`). |

### Validaciones (una política inválida no puede existir)

1. `version` y `trend_definition_version` no vacías.
2. `signal_timeframe`, `context_timeframe`, `relationship` y `conflict_rule` deben ser valores
   declarados de su tipo, no cadenas sueltas ni nombres de indicador.
3. `context_timeframe` **no es más fino** que `signal_timeframe` (sección 3 del contrato de
   contexto). Puede ser igual si la estrategia lo declara.
4. `minimum_history` es un entero de al menos 1.
5. `signal_states` y `context_states` no están vacíos y **nunca admiten
   `INSUFFICIENT_DATA`**: sin contexto no hay señal válida.
6. `context_states` solo puede contener estados que la relación es capaz de satisfacer:

   | Relación | Estados de contexto que puede admitir |
   | -------- | ------------------------------------- |
   | `WITH_TREND`, `COUNTER_TREND` | `UPTREND`, `DOWNTREND` |
   | `RANGE_ONLY` | `RANGE` |
   | `TRANSITION_ONLY` | `TRANSITION` |
   | `ANY` | `UPTREND`, `DOWNTREND`, `RANGE`, `TRANSITION` |

   Una política que admite un estado que su propia relación nunca aceptará se contradice, y
   se rechaza al construirla.

### Semántica de las relaciones

Es la matriz de la sección 4 del contrato de contexto, sin cambios. `ANY` debe declararse
expresamente, no es nunca un valor de reserva, y **no admite `INSUFFICIENT_DATA`**.

### Regla ante conflicto multitimeframe

Hay conflicto cuando **ambos marcos están en tendencia** (`UPTREND` o `DOWNTREND`) y **son
distintas**. Un `RANGE`, una `TRANSITION` o dos tendencias iguales no son un conflicto.

| `conflict_rule` | Efecto |
| --------------- | ------ |
| `REJECT_ON_CONFLICT` | Hay conflicto ⇒ `INCOMPATIBLE` con `MULTITIMEFRAME_CONFLICT`. |
| `ALLOW_CONFLICT` | El conflicto no es un motivo de rechazo por sí mismo. |

No hay valor por defecto: la estrategia decide expresamente cuál de las dos.

## 3. Evaluación

`evaluate_trend_policy(policy, orientation=..., pair=...)` recibe la política, la orientación
de la hipótesis (`BULLISH` o `BEARISH`, declarada) y el `TrendPair` ya clasificado por
POINT2-TREND-001. Devuelve una evaluación inmutable con el resultado, todos los motivos, la
versión de política, la relación, los dos estados, la definición de tendencia y la versión de
la evaluación.

### Orden y prioridad

**Fail-closed.** Primero se comprueba que hay contexto suficiente y correcto; solo si lo hay
se juzga la compatibilidad. Si algo de lo primero falla, el resultado es
`INSUFFICIENT_CONTEXT` **aunque además haya una incompatibilidad**: no se dice «no encaja»
de algo que no se ha podido juzgar.

| Motivo | Resultado | Cuándo |
| ------ | --------- | ------ |
| `POLICY_MISSING` | `INSUFFICIENT_CONTEXT` | La estrategia no tiene política. |
| `TIMEFRAME_MISMATCH` | `INSUFFICIENT_CONTEXT` | Las tendencias se clasificaron para otros marcos que los de la política. |
| `SIGNAL_TREND_INSUFFICIENT` | `INSUFFICIENT_CONTEXT` | El marco de la señal está en `INSUFFICIENT_DATA`. |
| `CONTEXT_TREND_INSUFFICIENT` | `INSUFFICIENT_CONTEXT` | El marco de contexto está en `INSUFFICIENT_DATA`. |
| `TREND_DEFINITION_MISMATCH` | `INSUFFICIENT_CONTEXT` | Alguna clasificación es de otra definición de tendencia que la de la política. |
| `MINIMUM_HISTORY_NOT_MET` | `INSUFFICIENT_CONTEXT` | Una clasificación suficiente leyó menos velas que `minimum_history`. |
| `SIGNAL_STATE_NOT_ADMITTED` | `INCOMPATIBLE` | El estado de la señal no está en `signal_states`. |
| `CONTEXT_STATE_NOT_ADMITTED` | `INCOMPATIBLE` | El estado de contexto no está en `context_states`. |
| `RELATIONSHIP_NOT_SATISFIED` | `INCOMPATIBLE` | La matriz de la relación no se cumple para esa orientación. |
| `MULTITIMEFRAME_CONFLICT` | `INCOMPATIBLE` | Tendencias opuestas con `REJECT_ON_CONFLICT`. |

- Se informan **todos** los motivos que fallan, no solo el primero.
- `minimum_history` se compara con las velas que la clasificación **realmente leyó**
  (`window_candles`), y solo donde hay clasificación: una clasificación sin datos ya tiene
  su propio motivo.
- Nunca hay un `COMPATIBLE` por omisión: solo se llega a él sin ningún motivo.

## 4. Versionado e historia

- Una política es un **valor inmutable**. Cambiarla es publicar una **política nueva**
  (`as_new_version`), con otro identificador y sometida a las mismas validaciones; la
  anterior queda intacta.
- Cada evaluación **guarda la versión de política y de evaluación con la que se hizo**, así
  que publicar una versión nueva no altera lo ya evaluado.
- Toda modificación de cómo se juzga una política incrementa `POLICY_EVALUATION_VERSION`.
- Es determinista y sin reloj ni aleatoriedad: mismas entradas, misma evaluación.

## 5. Lo que este contrato no decide

- Cómo se guardan las políticas ni las evaluaciones (POINT2-SNAPSHOT-001 y `StrategySpec`).
- Qué estrategias existen, qué valores concretos de política usan ni si una política concreta
  es acertada. `trend-v1` está **sin validar** (ver `tendencia-estructural.md`): esta capa
  hereda esa limitación y no afirma ventaja estadística alguna, ni siquiera para `WITH_TREND`.
- La lectura de HIGHER/LOWER de las opciones binarias (un punto posterior). La orientación de
  esta capa es alcista o bajista y **no activa ejecución real**.
- Sesión, hora y día como filtro: son política aparte y no forman parte de esta versión.

## 6. Decisiones técnicas tomadas al redactar

Registradas aquí para que se puedan corregir; ninguna es de producto.

1. La regla de conflicto tiene dos valores y se declara siempre; no hay valor por defecto.
2. Solo hay conflicto entre dos tendencias direccionales opuestas.
3. La falta de contexto gana a la incompatibilidad y se informa de todo lo que falla.
4. `signal_states` admite cualquiera de los cuatro estados clasificables; `context_states` se
   limita a los que la relación puede satisfacer, para que una política no se contradiga.
5. `minimum_history` se juzga contra las velas realmente leídas por cada clasificación.
6. Ninguna cadena libre ni nombre de indicador puede ocupar el lugar de la relación.
