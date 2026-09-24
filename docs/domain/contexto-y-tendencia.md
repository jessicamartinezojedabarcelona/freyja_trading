# Contrato de contexto y tendencia (v1)

- **Estado:** vigente. Es el único contrato de contexto y tendencia de Freyja 2.0.
- **Fecha:** 2026-09-24
- **Tarea:** POINT2-DOMAIN-001 (1 de 7 del punto 2). Documentación vinculante: **no
  implementa código**, ni migraciones, ni API, ni interfaz.
- **Depende de:** el catálogo y los datos de mercado ya existentes (ADR 0002, 0003;
  velas cerradas con calidad y procedencia).
- **Lo desarrollan:** POINT2-STRUCTURE-001 → CONTEXT-001 → TREND-001 → POLICY-001 →
  SNAPSHOT-001 → TEST-001.

Este documento fija **qué significa** contexto y tendencia y qué reglas cumplen.
No fija _cómo_ se calculan: la definición operativa de pivote y de estructura es de
POINT2-STRUCTURE-001, y los algoritmos de POINT2-CONTEXT-001 y POINT2-TREND-001.

## 1. Qué es (y qué no es) el contexto

El **contexto** describe el estado de la estructura de precio de un instrumento en
un marco temporal, en un instante concreto, con la evidencia que lo sustenta.

- **El contexto no es una señal.** Ni una oportunidad, ni una recomendación, ni una
  predicción. Una tendencia alcista no dice «compra»; una lateral no dice «no
  operes». El contexto solo puede **admitir o excluir** una hipótesis que otra
  parte del sistema formula (relaciones, sección 4). Nunca origina una orden ni una
  alerta por sí mismo.
- **Se muestra como contexto.** Ninguna pantalla lo presenta con el vocabulario de
  una señal (entrada, oportunidad, comprar, vender) ni con un color o icono de
  «acción». Se etiqueta como «Contexto» o «Tendencia estructural».
- **Se calcula sobre estructura de precio**, no sobre indicadores. Los indicadores
  pertenecen al punto 5 y no intervienen en esta clasificación inicial.

## 2. Estados

Un contexto vale exactamente uno de estos cinco estados.

| Estado              | Significado (nivel de contrato)                                                                           |
| ------------------- | --------------------------------------------------------------------------------------------------------- |
| `UPTREND`           | La estructura de precio en el marco de contexto avanza de forma sostenida hacia máximos y mínimos más altos. |
| `DOWNTREND`         | La estructura avanza de forma sostenida hacia máximos y mínimos más bajos.                                |
| `RANGE`             | La estructura oscila entre límites sin avance sostenido en ninguna dirección.                             |
| `TRANSITION`        | La estructura previa se ha roto o está en disputa y aún no se ha establecido una nueva.                   |
| `INSUFFICIENT_DATA` | No hay datos válidos y suficientes para clasificar. **No es un cuarto tipo de mercado: es la ausencia de clasificación.** |

Reglas:

1. Los estados son **mutuamente excluyentes y exhaustivos**: siempre hay uno, y solo
   uno, por instrumento, fuente, marco de contexto e instante.
2. Ante duda razonable entre dos estados con datos suficientes se usa `TRANSITION`;
   ante datos insuficientes, `INSUFFICIENT_DATA`. **Nunca se elige un estado
   direccional por defecto.**
3. Umbrales, ventana mínima y criterio exacto de «sostenido» **no se fijan aquí**:
   los define POINT2-STRUCTURE-001 y se versionan (sección 7).

### Cuándo el resultado es `INSUFFICIENT_DATA`

Cualquiera de estas condiciones basta, y no admite excepciones ni «mejor esfuerzo»:

- Hay menos velas cerradas que las exigidas por la versión del clasificador.
- La ventana evaluada contiene **huecos** (velas ausentes) o el proveedor la marca
  como no disponible (`UNAVAILABLE`). Los huecos no se rellenan ni se interpolan.
- La ventana contiene velas revisadas por el proveedor tras haberse guardado, o su
  calidad impide garantizar la reproducibilidad (`DEGRADED` con incidencias que
  afecten a la ventana).
- Los datos no son vigentes para el instante evaluado (última vela demasiado
  antigua para el marco).

Los datos de entrada llevan siempre su calidad y procedencia (CLAUDE.md §6); el
snapshot las conserva (sección 7).

## 3. Dos marcos temporales, evaluados por separado

| Marco               | Para qué sirve                                                     |
| ------------------- | ------------------------------------------------------------------ |
| `signal_timeframe`  | Marco de vela en el que se evaluará más adelante una hipótesis.    |
| `context_timeframe` | Marco de vela en el que se clasifica la tendencia que la enmarca. |

1. Se **clasifican por separado**: el contexto se calcula sobre velas del
   `context_timeframe` y nunca mezcla velas de otro marco ni de otra fuente.
2. Ambos son valores del catálogo (`freyja2_timeframes`) habilitados para el
   instrumento. Hoy: 1m, 5m, 15m, 1h y 4h.
3. `context_timeframe` **no es menor** que `signal_timeframe` (puede ser igual si la
   estrategia lo declara). Un contexto más fino que la señal no enmarca nada.
4. El marco es **duración de vela**. No determina por sí solo vencimiento,
   horizonte, ventana de entrada ni duración de posición (POINT1-DOMAIN-001).

## 4. Relaciones entre una hipótesis y el contexto

Una estrategia declara con qué contexto es compatible su hipótesis. Las relaciones
son valores cerrados y **la estrategia debe declararla siempre de forma explícita**:
no hay valor predeterminado, y en particular `ANY` **nunca** se asume.

Definiciones. Sea `orientación` el sentido de la hipótesis (alcista o bajista, según
la sección 5) y `estado` el contexto del `context_timeframe`.

| Relación          | La hipótesis es compatible cuando…                                             |
| ----------------- | ------------------------------------------------------------------------------ |
| `WITH_TREND`      | `estado` es `UPTREND` y la orientación es alcista, o `DOWNTREND` y bajista.    |
| `COUNTER_TREND`   | `estado` es `UPTREND` y la orientación es bajista, o `DOWNTREND` y alcista.    |
| `RANGE_ONLY`      | `estado` es `RANGE` (con cualquier orientación).                               |
| `TRANSITION_ONLY` | `estado` es `TRANSITION` (con cualquier orientación).                          |
| `ANY`             | `estado` es cualquiera **salvo** `INSUFFICIENT_DATA`.                          |

Matriz completa (✔ compatible, ✘ incompatible; «orient.» = orientación de la hipótesis):

| Estado ↓ / Relación → | `WITH_TREND`               | `COUNTER_TREND`            | `RANGE_ONLY` | `TRANSITION_ONLY` | `ANY` |
| --------------------- | -------------------------- | -------------------------- | ------------ | ----------------- | ----- |
| `UPTREND`             | ✔ si orient. alcista       | ✔ si orient. bajista       | ✘            | ✘                 | ✔     |
| `DOWNTREND`           | ✔ si orient. bajista       | ✔ si orient. alcista       | ✘            | ✘                 | ✔     |
| `RANGE`               | ✘                          | ✘                          | ✔            | ✘                 | ✔     |
| `TRANSITION`          | ✘                          | ✘                          | ✘            | ✔                 | ✔     |
| `INSUFFICIENT_DATA`   | ✘                          | ✘                          | ✘            | ✘                 | ✘     |

**Regla central: sin contexto suficiente no existe señal válida.** `INSUFFICIENT_DATA`
es incompatible con **todas** las relaciones, incluida `ANY`. `ANY` significa «el
estado no restringe la hipótesis», no «el contexto no importa».

## 5. La dirección no significa lo mismo en cada producto

La orientación «alcista/bajista» **no es una noción universal**. Este contrato impide
tratarla como tal para no atribuir a un producto una semántica que no tiene.

| Producto | Qué expresa la orientación de una hipótesis | Lo que NO expresa |
| -------- | ------------------------------------------- | ----------------- |
| `CRYPTO × SPOT` | Alcista: se **posee** el activo esperando un precio mayor. Bajista: **no** se posee o se **sale** de la posición. | Una venta en corto. En spot no se vende lo que no se tiene: «bajista» es abstenerse o reducir, no apostar a la baja. |
| `FOREX × SPOT` | Alcista: comprar la divisa base contra la de cotización. Bajista: vender la base contra la cotización. Ambos sentidos son operaciones **abiertas** simétricas. | Que el mercado tenga un «dueño»: un par se mueve siempre en relación con otra divisa. |
| `BINARY_OPTION` (cripto y Forex) | Alcista/bajista es la elección **CALL/PUT**: una afirmación binaria sobre si el precio **al vencimiento** estará por encima o por debajo de una referencia. | El recorrido del precio ni su magnitud entre la entrada y el vencimiento. Una tendencia en `context_timeframe` no es la misma cosa que acertar en un vencimiento cuyo reloj es distinto (definido en los puntos 8-14). |

Consecuencias vinculantes:

1. `WITH_TREND` y `COUNTER_TREND` se evalúan **con la orientación propia del
   producto** de la estrategia, no con una orientación genérica compartida.
2. En `SPOT` cripto, una hipótesis bajista **no genera una posición corta**. Si una
   estrategia necesita operar en corto, eso exige otro producto o venue y una
   decisión de producto aparte; no se deduce de este contrato.
3. Una relación `WITH_TREND` **no dice** que la operación vaya a ganar, ni que la
   probabilidad sea mayor. Afirmar ventaja estadística exige evidencia (CLAUDE.md §4)
   que este contrato no aporta.
4. Los mismos datos de mercado pueden clasificarse una sola vez; lo que cambia según
   el producto es la lectura de la orientación, no el estado del contexto.

## 6. Sesión, hora y día

El contexto registra **cuándo** se clasifica, siempre en **UTC** (CLAUDE.md §6).

| Mercado | Qué se registra |
| ------- | --------------- |
| `FOREX` | La **sesión** es **obligatoria**. Se deriva de forma determinista del instante UTC mediante un calendario de sesiones **versionado**. Si el calendario no puede asignar sesión a un instante, el resultado es `INSUFFICIENT_DATA`. |
| `CRYPTO` | Solo la **hora UTC** y el **día de la semana UTC**. **No se inventan sesiones oficiales**: cripto no las tiene. El campo de sesión queda vacío de forma explícita («no aplica»), nunca con una sesión prestada de Forex. |

Notas:

- El calendario de sesiones de Forex (cuáles, en qué horas UTC, tratamiento del
  cambio de hora) es una **referencia versionada** y se define en POINT2-CONTEXT-001,
  no aquí. Este contrato solo exige que exista, sea determinista y quede en el
  snapshot con su versión.
- La sesión y la hora **describen** el contexto; no lo filtran por sí solas. Usarlas
  para admitir o excluir una hipótesis es una política (POINT2-POLICY-001).

## 7. Snapshot versionado

Cada clasificación se conserva como **snapshot inmutable** con su evidencia
(CLAUDE.md §6: decisiones deterministas, reproducibles y explicables). Su
persistencia la diseña POINT2-SNAPSHOT-001; este contrato fija su contenido mínimo.

| Campo | Contenido |
| ----- | --------- |
| Identidad | `instrument_id`, `data_source_id`, `context_timeframe`. |
| Instante | `as_of` (UTC): cierre de la última vela cerrada usada. **Nunca** una vela en curso. Además `computed_at` (UTC), la hora real de cálculo. |
| Resultado | `state` (sección 2) y, si es `INSUFFICIENT_DATA`, **el motivo concreto** (sección 2). |
| Evidencia | Rango de velas usado (`open_time` primera y última, número de velas), calidad e incidencias de esos datos, y los elementos de estructura que sustentan el estado, en un formato legible por personas. |
| Marco | Hora UTC y día de la semana UTC; sesión (obligatoria en Forex, «no aplica» en cripto) y versión del calendario. |
| Versiones | Versión de este contrato, del clasificador y de sus parámetros. |
| Explicación | Texto humano que dice por qué se clasificó así. |

Reglas:

1. **Reproducible**: mismos datos de entrada + misma versión ⇒ mismo snapshot. Sin
   aleatoriedad ni dependencia del reloj salvo `computed_at`.
2. **Sin _look-ahead_**: solo usa velas cerradas con `open_time` anterior o igual a
   `as_of`. Ninguna información posterior afecta al resultado.
3. **Inmutable**: una corrección genera un snapshot **nuevo**, con otra versión; el
   antiguo se conserva.
4. **Nada de números en coma flotante para importes**; los precios de la evidencia
   se conservan como texto decimal exacto, igual que la API de velas.

## 8. Glosario

| Término | Definición |
| ------- | ---------- |
| Contexto | Estado de la estructura de precio de un instrumento en un marco y un instante, con su evidencia. No es una señal. |
| Tendencia | Cualquiera de los estados `UPTREND` o `DOWNTREND`. Es un valor del contexto, no una recomendación. |
| Estructura de precio | Secuencia de máximos y mínimos relevantes de la serie de velas cerradas. Su definición operativa es de POINT2-STRUCTURE-001. |
| `signal_timeframe` | Marco de vela en el que se evaluará una hipótesis. |
| `context_timeframe` | Marco de vela en el que se clasifica el contexto que la enmarca. |
| Hipótesis | Afirmación sobre el futuro del precio con una orientación. Su definición y evaluación son de los puntos 3-6; aquí solo importa su orientación. |
| Orientación | Sentido alcista o bajista de una hipótesis, según la sección 5 para cada producto. |
| Relación | Condición cerrada (`WITH_TREND`, `COUNTER_TREND`, `RANGE_ONLY`, `TRANSITION_ONLY`, `ANY`) que liga una hipótesis a un estado de contexto. |
| Snapshot | Registro inmutable y versionado de una clasificación con su evidencia. |
| `as_of` | Instante (UTC) de cierre de la última vela cerrada usada para clasificar. |
| Datos suficientes | Ventana completa de velas cerradas, sin huecos ni datos no disponibles, en cantidad no inferior a la exigida por la versión del clasificador y vigente. |
| Sesión | Tramo horario de negociación de un mercado definido por un calendario versionado. Solo aplica a Forex. |

## 9. Fuera de alcance

Este contrato **no define**: figuras, patrones de velas, indicadores, señal,
entrada, ventana de entrada, caducidad o invalidación, horizonte predicho,
tamaño, salidas, riesgo, ni backtesting. Tampoco define pivotes ni umbrales
numéricos (POINT2-STRUCTURE-001), el calendario de sesiones (POINT2-CONTEXT-001), la
política de uso del contexto (POINT2-POLICY-001) ni el almacenamiento del snapshot
(POINT2-SNAPSHOT-001). Nada de esto se supone por lo escrito arriba.

## 10. Criterios de aceptación de esta tarea

- [x] Glosario inequívoco (sección 8).
- [x] Spot, Forex y binarias no comparten una semántica direccional falsa
      (sección 5).
- [x] La tendencia no se presenta como una señal (sección 1); solo admite o excluye
      hipótesis (sección 4).
- [x] Sin contexto suficiente no existe señal válida, ni siquiera con `ANY`
      (secciones 2 y 4).
- [x] No se definen figuras, patrones, indicadores, entrada, caducidad, horizonte ni
      salidas (sección 9).

## 11. Decisiones técnicas tomadas al redactar

Registradas aquí para que se puedan corregir; ninguna es de producto.

1. `context_timeframe` puede ser igual a `signal_timeframe`, pero no menor.
2. Datos con huecos, revisados o no vigentes en la ventana dan `INSUFFICIENT_DATA`:
   se prefiere no clasificar a clasificar con datos dudosos.
3. `ANY` no restringe por estado pero tampoco admite `INSUFFICIENT_DATA`.
4. En `SPOT` cripto, «bajista» significa abstenerse o salir; no implica venta en
   corto.
5. El calendario de sesiones de Forex es una referencia versionada, definida en
   POINT2-CONTEXT-001.
