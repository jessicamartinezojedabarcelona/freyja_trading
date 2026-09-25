# Instancia de figura chartista: modelo, identidad y ciclo de vida (v1)

- **Estado:** vigente. Modelo `pattern-instance-v1`, sobre el catálogo `chart-patterns-v1`.
- **Fecha:** 2026-09-25
- **Tarea:** POINT3-MODEL-001 (2 de 7 del punto 3).
- **Depende de:** [figuras-chartistas.md](figuras-chartistas.md) (POINT3-DOMAIN-001) y de
  [estructura-de-precio.md](estructura-de-precio.md) (pivotes confirmados).
- **Código:** `backend/src/freyja_backend/domain/chart_pattern.py`. Dominio puro, sin E/S.
  Sus pruebas están en `backend/tests/unit/test_chart_pattern.py`.
- **Lo usan:** POINT3-REVERSAL-001, CONTINUATION-001 y EXPANSION-001 (detectores) y
  POINT3-HYPOTHESIS-001.

Este documento fija cómo se **representa una figura concreta** detectada sobre las velas cerradas y
los pivotes confirmados de una serie, y cómo evoluciona. Es un **modelo, no un detector**: no
decide si una geometría es de verdad un doble techo; garantiza que lo que un detector afirma es
completo, coherente, sin _look-ahead_ y reconstruible.

## 1. Qué es (y qué no es)

- **Es un registro.** Valores inmutables que se construyen una vez y se guardan tal cual. La
  historia es de **solo añadir**: cada evaluación se suma a las anteriores y nunca las reescribe.
- **No genera `Signal` ni decisión.** No contiene lado, entrada, objetivo, confianza ni
  probabilidad; un test lo comprueba sobre los campos y sobre las claves del documento. El sesgo
  tradicional de una figura es tradición, no evidencia (contrato de figuras, sección 2).
- **No define umbrales ni geometría.** Las tolerancias, el número de velas y el ajuste de las
  fronteras son de los detectores. El modelo solo exige lo estructural: que existan las anclas
  mínimas de la figura (sección 5) y que todo lo demás sea coherente.
- **No persiste.** Esta tarea no crea tabla ni migración: el modelo produce y lee un documento
  JSON estable, y su almacenamiento llegará con las tareas que lo usen (POINT3-HYPOTHESIS-001 y el
  expediente de la señal). Por eso los campos nuevos de una figura futura no exigen columnas: la
  evidencia es genérica (sección 6).

## 2. Contenido

### `PatternInstance` (la figura)

| Campo | Contenido |
| ----- | --------- |
| `pattern_instance_id` | Identidad estable, **derivada** (sección 4). |
| `pattern_type` | Una de las veinte del catálogo. |
| `traditional_roles`, `traditional_bias` | **Del catálogo**, no del detector: una figura no puede declarar otro sesgo. |
| `instrument_id`, `data_source`, `timeframe` | La serie sobre la que se detectó (las fuentes no se mezclan). |
| `observed_at` | Instante de la primera evaluación: cuándo se vio por primera vez. |
| `started_at` | Apertura de la vela del primer pivote ancla. |
| `last_evaluated_at`, `state` | Los de la última evaluación. |
| `detector_version`, `parameter_version` | Quién la encontró y con qué parámetros. |
| `evaluations` | La historia, de más antigua a más reciente; siempre hay al menos una. |

### `PatternEvaluation` (lo que el detector vio en un instante)

Autosuficiente: nombra todo lo que usó, de modo que **se reconstruye por qué se detectó** sin
consultar nada más.

| Campo | Contenido |
| ----- | --------- |
| `evaluated_at` | El instante de la evaluación: solo se leyó lo que se podía conocer entonces. |
| `as_of` | Cierre de la última vela cerrada leída. |
| `candle_count` | Velas del tramo evaluado. |
| `state` | Uno de los ocho estados (sección 3). |
| `anchors` | Los pivotes confirmados en los que se apoya, con la función de cada uno (`HEAD`, `TROUGH`…). |
| `boundaries` | Fronteras (línea de cuello, soporte, resistencia, base, arco) y sus contactos con las anclas. |
| `breakout` | La vela cerrada que cruzó una frontera: dirección, frontera, precio de cierre y si el detector la da por confirmada. |
| `invalidation_reasons` | Por qué dejó de ser una figura. |
| `insufficient_data_reasons` | Por qué no se pudo juzgar. |
| `evidence` | Hechos específicos y extensibles (sección 6). |

## 3. Ciclo de vida

Ocho estados:

| Estado | Significa |
| ------ | --------- |
| `FORMING` | Hay anclas, pero la geometría aún no está completa. |
| `GEOMETRICALLY_VALID` | La geometría está completa. Exige al menos las anclas de su catálogo y fronteras. |
| `BREAKOUT_PENDING_CONFIRMATION` | Una vela cerrada cruzó una frontera; el detector aún no la confirma. |
| `CONFIRMED_UP` / `CONFIRMED_DOWN` | Ruptura confirmada al alza o a la baja. Su ruptura debe coincidir en dirección y estar confirmada. |
| `FAILED_BREAKOUT` | La ruptura fracasó. **Final.** |
| `INVALIDATED` | La figura dejó de serlo, con sus motivos. **Final.** |
| `INSUFFICIENT_DATA` | Con los datos de ese momento no se puede juzgar, con sus motivos. |

Transiciones permitidas de un estado a otro en una evaluación posterior (mantenerse en el mismo
estado, si no es final, siempre está permitido):

| Desde | Puede pasar a |
| ----- | ------------- |
| `FORMING` | `GEOMETRICALLY_VALID`, `BREAKOUT_PENDING_CONFIRMATION`, `CONFIRMED_UP`, `CONFIRMED_DOWN`, `FAILED_BREAKOUT`, `INVALIDATED` |
| `GEOMETRICALLY_VALID` | `BREAKOUT_PENDING_CONFIRMATION`, `CONFIRMED_UP`, `CONFIRMED_DOWN`, `FAILED_BREAKOUT`, `INVALIDATED` |
| `BREAKOUT_PENDING_CONFIRMATION` | `CONFIRMED_UP`, `CONFIRMED_DOWN`, `FAILED_BREAKOUT`, `INVALIDATED` |
| `CONFIRMED_UP`, `CONFIRMED_DOWN` | `FAILED_BREAKOUT`, `INVALIDATED` |
| `FAILED_BREAKOUT`, `INVALIDATED` | nada: **ninguna evaluación posterior, ni siquiera una pausa** |

- Una figura **avanza, nunca retrocede**, y puede saltar varios hitos a la vez: una evaluación
  es un instante discreto y varios hitos pueden hacerse conocibles juntos (un pivote se confirma
  `k` velas tarde, así que la ruptura que lo sigue puede haber ocurrido ya). Se corrigió al
  escribir los detectores de POINT3-REVERSAL-001: exigir el paso intermedio obligaba a informar
  de un estado anterior al real.
- **`INSUFFICIENT_DATA` es una pausa, no un estado del mercado.** Cualquier estado no final puede
  pasar a él, y al salir la figura continúa desde el estado que tenía o desde cualquiera al que
  este pudiera ir; no puede retroceder ni saltar por haber estado en pausa. Una figura que nace
  sin datos suficientes puede empezar a formarse después.
- **Contenido coherente con el estado:** los motivos de invalidación existen exactamente cuando la
  figura está `INVALIDATED`; los de datos insuficientes, exactamente cuando lo está `INSUFFICIENT_DATA`;
  `FORMING` y `GEOMETRICALLY_VALID` no traen ruptura; `INSUFFICIENT_DATA` no afirma nada de una
  ruptura; los estados de ruptura la exigen; toda ruptura cruza una frontera que la figura tiene.

## 4. Identidad y versiones

`pattern_instance_id` es un UUID por nombre (v5) del **tipo, la serie, el inicio, el tipo del
primer pivote, el detector, los parámetros y la versión del modelo**. Por tanto:

- **La misma figura, hallada de nuevo por el mismo detector con los mismos parámetros, es la
  misma instancia**; avanzarla no cambia quién es.
- Un inicio, un detector, unos parámetros o un tipo distintos son **otra instancia**.
- Al leer un documento se comprueba que la identidad escrita es la que da su contenido: un
  documento no puede hacerse pasar por otra figura.

## 5. Solo se añade: una modificación sustancial es otra instancia

Entre dos evaluaciones consecutivas:

- **Las anclas solo pueden añadirse.** Las de la evaluación anterior deben ser exactamente las
  primeras de la nueva (mismo pivote, precio, confirmación y función). Cambiar, quitar o reetiquetar
  una ancla, o empezar por otro pivote, **no es evolucionar: es otra figura**, con su identidad.
  Las fronteras, en cambio, se reajustan en cada evaluación, porque dependen de las anclas.
- Los instantes **avanzan estrictamente**, `as_of` no retrocede y el número de velas no baja.
- **Cada tipo exige un mínimo de anclas para ser geométricamente válido** (columna «Anclas» del
  catálogo): 3 para doble techo o suelo y para el arco, 4 para triángulos, rectángulo y cuñas, 5
  para hombro-cabeza-hombro, triple techo o suelo, banderas, banderines y la formación
  expansiva, 6 para el diamante. Una figura en formación puede tener menos.
- **Varias figuras coexisten** sobre las mismas velas, cada una con su identidad; ninguna oculta,
  sustituye ni fusiona a otra. `SUPERSEDED` existe como motivo de invalidación para cuando un
  detector reemplace una figura por otra que ajusta mejor; el modelo no la enlaza.

## 6. Evidencia extensible

`evidence` es una lista de hechos con un **código** en mayúsculas y guion bajo (`FLAGPOLE`,
`HEAD_AND_SHOULDERS`, `ROUNDING_ARC`, `EXPANSION_RANGE`, `DIAMOND_PHASES`…), un texto legible y
valores con nombre. Los valores son texto, entero, booleano o `Decimal` exacto; **nunca un
número de coma flotante**. Una figura futura trae códigos nuevos, no campos nuevos: por eso no
hacen falta columnas por figura.

## 7. Sin _look-ahead_

Cada evaluación se rechaza si usa algo que no se sabía en su instante: un pivote cuya
confirmación es posterior, una vela de ruptura que aún no había cerrado, una frontera con puntos
posteriores, una vela leída que cierra después. Solo se aceptan pivotes **confirmados**; uno
provisional, aunque traiga una hora de confirmación, se rechaza.

## 8. Serialización

`PatternInstance.document()` produce JSON puro: precios como texto decimal exacto, instantes UTC
terminados en `Z`, los tipos de los hechos de evidencia junto a su valor, y el sesgo, los roles y
la versión del catálogo con los que se escribió. `pattern_instance_from_document()` lo lee **sin
derivar nada**: valida toda regla, rechaza una versión de modelo que no conoce, un campo ausente,
un valor desconocido, un instante sin zona o no UTC, un precio que no es un decimal positivo y
una identidad que no corresponde al contenido.

## 9. Lo que este modelo no decide

- **La geometría.** Que las anclas de un doble techo sean H, L, H o que dos máximos sean
  «comparables» lo juzga el detector; el modelo no comprueba el tipo de cada ancla contra el
  tipo de figura.
- Cómo se guarda (tabla, migración, retención) ni cómo se expone (API, pantalla).
- Cómo se combinan varias figuras como evidencia de una hipótesis (POINT3-HYPOTHESIS-001).
- Objetivos de precio, entradas, riesgo, señales u órdenes.
- Si una figura funciona: sigue sin haber evidencia estadística (punto 15).

## 10. Criterios de aceptación de esta tarea

- [x] Modelo extensible **sin columnas nuevas por figura futura** (sección 6).
- [x] Reconstrucción completa de por qué se detectó: cada evaluación nombra sus anclas,
      fronteras, ruptura, motivos y evidencia (sección 2).
- [x] Identidad y versiones estables (sección 4).
- [x] Solo velas cerradas y pivotes confirmados (sección 7).
- [x] Una modificación sustancial crea una instancia nueva; no se reescribe el pasado (sección 5).
- [x] Varias figuras coexisten sobre las mismas velas (sección 5).
- [x] No genera `Signal` ni decisión (sección 1).

## 11. Decisiones técnicas tomadas al redactar

Registradas aquí para que se puedan corregir; ninguna es de producto.

1. La figura es una **identidad con una historia de evaluaciones**, no una fila mutable: es lo que
   permite «no reescribir el pasado» y reconstruir cada momento.
2. La identidad se deriva del **inicio** (primer pivote), no del conjunto completo de anclas, para
   que añadir anclas sea evolucionar y cambiar las existentes sea otra figura.
3. Los motivos de invalidación son un conjunto cerrado y versionado con el modelo
   (`GEOMETRY_BROKEN`, `ANCHOR_EXCEEDED`, `CLOSED_THROUGH_AGAINST_BIAS`, `TOO_LONG`, `SUPERSEDED`).
   Los detectores podrán pedir más con una versión nueva.
4. Las anclas mínimas del catálogo son totales de pivotes **distintos**; en banderas y banderines
   el extremo del mástil cuenta también como primer contacto de una frontera (se precisó en el
   contrato de figuras al escribir este modelo).
5. Un test compara el catálogo del código con las tablas de `figuras-chartistas.md`: si el
   documento y el código divergen, falla.
6. Sin persistencia en esta tarea (sección 1).
