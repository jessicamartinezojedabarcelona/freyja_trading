# Estructura de precio: pivotes y puntos de giro (v1)

- **Estado:** vigente. Algoritmo `pivots-v1`.
- **Fecha:** 2026-09-24
- **Tarea:** POINT2-STRUCTURE-001 (2 de 7 del punto 2).
- **Depende de:** [contexto-y-tendencia.md](contexto-y-tendencia.md) (POINT2-DOMAIN-001).
- **Implementación de referencia:** `backend/src/freyja_backend/domain/market_structure.py`
  (pura, sin BD ni red). Sus pruebas están en
  `backend/tests/unit/test_market_structure.py`.
- **Lo usan:** POINT2-CONTEXT-001 y POINT2-TREND-001. Este documento **no clasifica
  tendencias**: solo define qué es un pivote y cuándo se puede conocer.

Reglas que no se rompen: solo velas **cerradas**; **cero _look-ahead_**; nada de
RSI, MACD, medias, Fibonacci ni figuras chartistas; parámetros justificados y
preparados para validarse después, no elegidos por intuición.

## 1. Definición

Sea `k` el número de velas cerradas exigidas **a cada lado** de la vela candidata
`i`.

- **`pivot_high`**: el máximo de la vela `i` es **estrictamente mayor** que el de
  cada una de las `k` velas anteriores y **mayor o igual** que el de cada una de las
  `k` posteriores.
- **`pivot_low`**: el mínimo de la vela `i` es **estrictamente menor** que el de cada
  una de las `k` velas anteriores y **menor o igual** que el de cada una de las `k`
  posteriores.

Un pivote se decide **solo con las velas `i-k … i+k`**. No depende de dónde empiece
la serie, de cuántas velas haya antes ni de nada posterior a `i+k`. Por eso el mismo
pivote sale igual con una ventana más corta o más larga (hay una prueba de esto).

El precio del pivote es el máximo o mínimo **exacto** (`Decimal`, sin coma flotante).

### Empates

La regla «estricto por la izquierda, mayor o igual por la derecha» hace que una
**meseta de máximos iguales dé exactamente un pivote: el primero**. Los siguientes
tienen a su izquierda un máximo igual y no son estrictamente mayores.

- Dos máximos iguales **separados por más de `k` velas** son dos pivotes distintos
  (el segundo no ve al primero dentro de su vecindad).
- Una serie **plana** no tiene pivotes.
- Una vela puede ser a la vez `pivot_high` y `pivot_low` (vela «exterior»). Se
  devuelven **ambos**, el máximo primero (sección 5).

## 2. Cuándo un pivote se puede conocer

Un pivote en la vela `i` **no existe para nadie** hasta que la vela `i+k` se ha
cerrado: antes de eso, una vela posterior aún puede superarlo.

| Estado        | Significado                                                                 | ¿Puede alimentar una decisión? |
| ------------- | --------------------------------------------------------------------------- | ------------------------------ |
| `PROVISIONAL` | Cumple la condición con las velas posteriores disponibles, pero aún faltan (`< k`). | **No.** Puede desaparecer.     |
| `CONFIRMED`   | Han cerrado las `k` velas posteriores y se cumple la condición.             | Sí.                            |

`confirmed_at` = **hora de cierre de la vela `i+k`**. Es el primer instante en que el
pivote es conocible. Un pivote `CONFIRMED` **nunca desaparece** después (hay una
prueba que lo comprueba en series aleatorias); uno `PROVISIONAL` sí puede hacerlo.

Todo el cálculo recibe un `observed_at` (UTC): **solo se leen las velas cuyo cierre
es igual o anterior a `observed_at`**. Un pivote no puede confirmarse con información
que aún no existía en ese instante. Se comprueba de forma exhaustiva: para cada
instante de series aleatorias, calcular con la serie completa y calcular solo con el
pasado dan el mismo resultado.

### Ejemplo temporal (velas de 5 m, `k = 2`)

Máximos de las velas: `10, 11, 12, 15, 14, 13, 12, 11`; la primera abre a las 10:00.
El máximo de 15 es la vela 3 (abre 10:15, cierra 10:20).

| `observed_at` | Última vela cerrada | Estado del pivote (vela 3, precio 15) |
| ------------- | ------------------- | ------------------------------------- |
| 10:20         | vela 3              | `PROVISIONAL` (0 de 2 velas posteriores) |
| 10:25         | vela 4              | `PROVISIONAL` (1 de 2)                |
| **10:30**     | vela 5              | **`CONFIRMED`**, `confirmed_at = 10:30` |

Un provisional que desaparece: con máximos `10, 11, 12, 15, 14, 16, 13`, a las 10:25
el 15 es `PROVISIONAL`; a las 10:30 la vela 5 (16) lo supera y **deja de ser pivote**.
Por eso un provisional no se usa nunca.

El retraso de conocimiento es **`k` velas del marco**: con `k = 3`, 3 minutos en 1m y
12 horas en 4h.

## 3. Datos incompletos, huecos y velas abiertas

- **Velas abiertas:** no existen para este cálculo. La entrada es una serie de velas
  cerradas, y además se descarta toda vela que no haya cerrado en `observed_at`.
- **Huecos:** no se rellenan ni se interpolan. **No se produce ningún pivote cuya
  vecindad de `k` velas por cada lado contenga una vela ausente.** Un hueco lejos de
  un pivote no lo afecta.
- **Serie corta:** con menos de `k+1` velas no hay ni pivotes provisionales, y con menos
  de `2k+1` no hay ninguno confirmado; no es un error.
- **Datos inválidos:** velas duplicadas, desordenadas o fuera de la cuadrícula del
  marco (`open_time` no alineado) **se rechazan** con `InvalidMarketDataError`.
  Nada se corrige en silencio.
- Esta capa **no decide** si una serie es suficiente para clasificar: eso es de la
  tendencia, que, según el contrato de contexto, devuelve `INSUFFICIENT_DATA` ante
  huecos o datos no vigentes en la ventana.

## 4. Profundidad histórica mínima

**100 velas cerradas por marco** (`MIN_HISTORY_CANDLES`), sin huecos, para todos los
marcos (1m, 5m, 15m, 1h y 4h).

| Marco | 100 velas equivalen a |
| ----- | --------------------- |
| 1m    | 1 h 40 min            |
| 5m    | 8 h 20 min            |
| 15m   | 25 h                  |
| 1h    | 4 días 4 h            |
| 4h    | 16 días 16 h          |

Justificación (medición descriptiva, sección 7): con `k = 3`, **ninguna** de 1.800
ventanas de 100 velas reales tuvo menos de 4 puntos de giro; con 50 velas fallaron el
1,9 % y con 30 velas el 34,2 %. Con 100 hay margen. Cabe sobradamente en lo que se
guarda (500 velas por sincronización).

Esto mide **tener estructura que leer**, no que la clasificación acierte.

## 5. Puntos de giro (swings)

Los **puntos de giro** son los pivotes `CONFIRMED` reducidos a una secuencia que
**alterna** máximo y mínimo:

1. Se recorren en orden de vela.
2. Dos pivotes consecutivos **del mismo tipo** se funden en **el más extremo** (el
   máximo mayor, el mínimo menor); si empatan, se conserva **el anterior**.
3. Una vela que es a la vez `pivot_high` y `pivot_low` **se deja fuera**: no se puede
   saber el orden del máximo y del mínimo dentro de una vela, y elegir uno inventaría
   información.
4. Los `PROVISIONAL` se ignoran.

La cola de la secuencia **puede cambiar** cuando se confirman pivotes nuevos (un
máximo posterior más alto sustituye al anterior). Por eso un resultado siempre va
unido a su `observed_at`.

## 6. Versionado y reproducibilidad

Cada resultado lleva `algorithm_version` (`pivots-v1`), sus parámetros (`k`),
`observed_at` y el número de velas usadas.

- **Mismas velas + mismo `observed_at` + misma versión y parámetros ⇒ mismos
  pivotes**, en el mismo orden. Sin aleatoriedad ni lectura del reloj.
- **Cualquier cambio** en cómo se derivan pivotes o puntos de giro sube la versión
  (`pivots-v2`…). Una versión publicada no se edita.
- Cambiar `k` es cambiar de parámetros: el resultado lo registra. Los snapshots del
  contrato de contexto guardan versión y parámetros.

## 7. Parámetros y su justificación

| Parámetro | Valor v1 | Estado |
| --------- | -------- | ------ |
| `k` (velas por lado) | **3**, igual en todos los marcos | **NO VALIDADO** |
| Profundidad mínima | 100 velas | Medido (sección 4) |

Mediciones descriptivas sobre velas **reales** cerradas de Binance (999 por serie; 4
pares × 5 marcos = 20 series; API pública, solo lectura):

| `k` | Pivotes confirmados por cada 100 velas | Puntos de giro por cada 100 | Retraso |
| --- | -------------------------------------- | --------------------------- | ------- |
| 1   | 46,4 | 33,5 | 1 vela |
| 2   | 27,6 | 21,4 | 2 velas |
| **3** | **19,7** | **15,9** | **3 velas** |
| 4   | 15,4 | 12,4 | 4 velas |
| 5   | 12,6 | 10,0 | 5 velas |
| 8   | 7,8  | 6,3  | 8 velas |

Por qué `k = 3` como valor de partida:

1. `k = 1` marca un pivote cada ~2 velas (46 por 100): cualquier zigzag de tres velas
   es «estructura». No distingue estructura de ruido.
2. Cada vela de `k` es **retraso** en conocer el pivote; `k` grande retrasa demasiado,
   sobre todo en 4h.
3. `k = 3` da un pivote cada ~5 velas (unos 16 puntos de giro por 100) con 3 velas de
   retraso: un punto intermedio entre ambos extremos.
4. Se usa el mismo `k` en todos los marcos porque **el marco ya escala el tiempo**;
   parametrizar por marco añadiría grados de libertad sin evidencia.

**Esto no demuestra que `k = 3` sea el mejor.** Solo describe el comportamiento del
detector. Hasta validarlo, todo resultado con `k = 3` se considera **parámetro
provisional**. Queda preparado para validación posterior: la rejilla candidata es
**`k ∈ {2, 3, 5}`**, y se compara **fuera de muestra**, con criterios fijados de
antemano, en las tareas de pruebas y de _backtesting_ (POINT2-TEST-001 y punto 15).
Hasta entonces no se afirma que ningún valor sea rentable ni seguro.

## 8. Fuera de alcance

No clasifica tendencias (POINT2-TREND-001), no define umbrales de amplitud, no usa
indicadores, figuras ni patrones de velas, no persiste nada (POINT2-SNAPSHOT-001), no
expone API ni interfaz, y no define entradas, caducidad, horizonte ni salidas.

## 9. Criterios de aceptación

- [x] Mismos OHLCV y misma versión ⇒ mismos pivotes (pruebas de reproducibilidad y de
      independencia de la ventana).
- [x] Ejemplos temporales que muestran cuándo cada pivote se vuelve conocible
      (sección 2 y pruebas).
- [x] Casos límite y datos insuficientes definidos: empates, meseta, serie plana, vela
      exterior, huecos, serie corta, datos inválidos, velas abiertas.
- [x] Sin _look-ahead_: comprobado para cada instante de series aleatorias.
- [x] Parámetros justificados con datos y marcados como no validados.
