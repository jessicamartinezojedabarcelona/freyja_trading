# Tendencia estructural (v1)

- **Estado:** vigente. Definición `trend-v1`, sobre pivotes `pivots-v1` y contexto `context-v1`.
- **Fecha:** 2026-09-25
- **Tarea:** POINT2-TREND-001 (4 de 7 del punto 2).
- **Depende de:** [contexto-y-tendencia.md](contexto-y-tendencia.md) (contrato),
  [estructura-de-precio.md](estructura-de-precio.md) (pivotes y puntos de giro) y
  [contexto-observable.md](contexto-observable.md) (suficiencia de datos).
- **Implementación de referencia:** `backend/src/freyja_backend/domain/market_trend.py`
  (pura: sin BD, red, reloj ni lectura de ningún otro módulo de la aplicación). Pruebas en
  `backend/tests/unit/test_market_trend.py`.
- **Lo usan:** POINT2-POLICY-001 y POINT2-SNAPSHOT-001.

Clasifica **un marco de velas cada vez**, a partir de los puntos de giro confirmados. Produce
un **estado del mercado, no una señal**: no genera entradas, órdenes ni alertas, y no conoce
ningún broker, ejecutor ni canal de notificación (una prueba lo comprueba sobre sus
importaciones).

## 1. Estados

| Estado | Cuándo (definición operativa `trend-v1`) |
| ------ | ---------------------------------------- |
| `UPTREND` | Los dos últimos **máximos** confirmados suben de forma material y los dos últimos **mínimos** confirmados también, y ninguna vela ha cerrado por debajo del último mínimo. |
| `DOWNTREND` | Los dos últimos máximos y los dos últimos mínimos bajan de forma material, y ninguna vela ha cerrado por encima del último máximo. |
| `RANGE` | Los dos últimos máximos están **al mismo nivel** y los dos últimos mínimos también (límites demostrables: cada uno tocado dos veces), y ninguna vela ha cerrado fuera de los límites. |
| `TRANSITION` | Cualquier otra combinación con datos suficientes: **conflicto** entre máximos y mínimos (por ejemplo, máximos que suben y mínimos que bajan), o una **ruptura** (un cierre más allá del último punto del que depende la estructura) todavía sin estructura nueva confirmada. |
| `INSUFFICIENT_DATA` | Los datos no son aptos o hay pocos puntos de giro. **No es un cuarto tipo de mercado: es la ausencia de clasificación** (sección 5). |

Son mutuamente excluyentes y exhaustivos. Ante duda entre estados con datos suficientes, se
usa `TRANSITION`; **nunca se elige un estado direccional por defecto**.

## 2. Cómo se lee la estructura

1. **Datos aptos.** Se construye el contexto observable de la serie (mismos motivos de
   insuficiencia que en `contexto-observable.md`). Si no es suficiente, se responde
   `INSUFFICIENT_DATA` sin mirar puntos de giro.
2. **Ventana.** Las últimas **100 velas cerradas** (la misma ventana en que el contexto ya
   comprobó huecos y calidad).
3. **Puntos de giro.** `pivots-v1` con `k = 3`, solo **confirmados**, reducidos a una secuencia
   que alterna máximo y mínimo. Se leen los **4 más recientes** (`window_swings = 4`): los dos
   últimos máximos y los dos últimos mínimos.
4. **Escalón material.** Sea `altura` = máximo mayor − mínimo menor de esos 4 puntos, y
   `banda` = `significance × altura` (`significance = 0,15`). Entre dos puntos del mismo lado:
   - **sube** si la diferencia es **estrictamente mayor** que la banda; **baja** si lo es hacia
     abajo;
   - **al mismo nivel** si todo el lado cabe dentro de la banda.

   Una sola banda decide ambas cosas, así que un lado nunca es direccional y llano a la vez
   (una prueba lo comprueba con miles de casos). Un escalón **igual** a la banda no cuenta como
   subida ni bajada.
5. **Estado** según la tabla de la sección 1.
6. **Rupturas** (solo con **cierres**, nunca mechas): en `UPTREND`, una vela que cierra por
   debajo del último mínimo; en `DOWNTREND`, por encima del último máximo; en `RANGE`, fuera de
   cualquiera de los dos límites. Cualquiera de ellas convierte el estado en `TRANSITION` y queda
   anotada como evidencia (`STRUCTURE_BROKEN` / `RANGE_BROKEN`). Así una ruptura se ve al
   cerrar la vela, sin esperar los `k` cierres que necesita un pivote nuevo.

### Ejemplos (velas de 5 m; máximos y mínimos confirmados)

| Máximos | Mínimos | Estado | Por qué |
| ------- | ------- | ------ | ------- |
| 126,5 → 130,5 | 114,5 → 118,5 | `UPTREND` | ambos suben más de la banda (2,25) |
| 300 − esos | 300 − esos | `DOWNTREND` | el espejo |
| 110,3 → 110,1 | 100,2 → 100,4 | `RANGE` | ambos dentro de la banda; cada límite, dos veces |
| 110 → 130 | 100 → 80 | `TRANSITION` | máximos suben y mínimos bajan: el rango se ensancha |
| 130 → 110 | 80 → 100 | `TRANSITION` | máximos bajan y mínimos suben: se estrecha |
| 120 → 120 | 104 → 112 | `TRANSITION` | máximos llanos con mínimos que suben: conflicto |
| (como el primero) | (como el primero) | `TRANSITION` | un cierre por debajo del último mínimo, 118,5: ruptura |

## 3. Resultado

| Campo | Contenido |
| ----- | --------- |
| `state` | Uno de los cinco estados. |
| `confirmed_swings` | Los puntos de giro confirmados en que se apoya, del más antiguo al más reciente (vacío si los datos no eran aptos antes de buscarlos). |
| `evidence` | Hechos que sustentan el estado, con código estable y texto legible (`HIGHER_HIGHS`, `LOWER_LOWS`, `LEVEL_HIGHS`, `STRUCTURE_BROKEN`, `MIXED_STRUCTURE`, `SWING_COUNT`…). Los precios van como texto decimal exacto. |
| `observed_at`, `as_of` | Instante observado y cierre de la última vela cerrada leída. |
| `definition_version`, `structure_version`, `params`, `pivot_params` | `trend-v1`, `pivots-v1` y los parámetros: con ellos el resultado es reproducible y trazable. |
| `insufficient_data_reasons` | Vacío **exactamente cuando** el estado no es `INSUFFICIENT_DATA`. |
| `instrument_id`, `data_source`, `timeframe`, `window_candles` | Identidad y tamaño de la ventana. |

No hay campo de dirección de operación, señal, entrada, oportunidad ni recomendación (una
prueba lo comprueba, y otra revisa que el texto de la evidencia no use vocabulario de acción).

## 4. Dos marcos, por separado

`classify_trend_pair` clasifica el marco de señal y el de contexto **cada uno con sus velas** y
los devuelve **uno al lado del otro**: no existe una etiqueta combinada, ninguno lee las velas del
otro (si el contexto falla, la señal sigue clasificada, y al revés) y ambos usan la misma fuente.

El par `(signal, context)` es un `TrendTimeframes`: **configuración versionada de la estrategia**
(`config_version` obligatorio), no un mapa universal. El de contexto no es más fino que el de
señal; igual sí. En el código no existe ninguna tabla «marco de señal → marco de contexto» (una
prueba lo vigila).

## 5. Cuándo es `INSUFFICIENT_DATA` (fail-closed)

Sin excepciones ni «mejor esfuerzo». Cualquiera de estas basta:

- Todos los motivos del contexto observable: `SOURCE_NOT_AUTHORIZED`, `SCHEDULE_UNKNOWN`,
  `NO_DATA`, `INVALID_CANDLES`, `INSUFFICIENT_HISTORY` (menos de 100 velas), `STALE_DATA`,
  `GAPS_IN_WINDOW`, `DEGRADED_DATA`. Con ellos no se busca ningún punto de giro.
- `INSUFFICIENT_SWINGS`: los datos son aptos pero hay **menos de 4** puntos de giro confirmados
  en la ventana. Se informa cuántos hay; lo encontrado no se oculta.

Los datos malos **no lanzan errores**: dan `INSUFFICIENT_DATA`. Solo una petición mal formada
(hora sin zona UTC, historial mínimo < 1, parámetros imposibles, par de marcos incoherente)
lanza una excepción.

## 6. Reglas de honestidad

1. **Sin _look-ahead_.** Solo se leen velas cerradas en `observed_at`. Para cada instante de
   varias series aleatorias, clasificar con la serie completa y clasificar solo con lo que había
   cerrado da **exactamente** el mismo resultado (prueba exhaustiva). Una vela abierta no existe.
2. **Reproducible.** Mismas velas + mismo `observed_at` + misma versión y parámetros ⇒ mismo
   resultado. Sin aleatoriedad ni lectura del reloj.
3. **Versionado.** Cualquier cambio en cómo se deriva el estado sube la versión (`trend-v2`…).
   Una versión publicada no se edita.
4. **Es un estado, no una predicción.** `UPTREND` no dice «compra» ni que el precio vaya a
   subir. El contexto solo admite o excluye hipótesis que formula otra parte (POINT2-POLICY-001).

## 7. Parámetros y su justificación

| Parámetro | Valor v1 | Estado |
| --------- | -------- | ------ |
| `window_swings` | **4** (dos máximos y dos mínimos) | **NO VALIDADO** |
| `significance` | **0,15** de la altura | **NO VALIDADO** |
| Ventana | 100 velas | Medido (estructura-de-precio.md, sección 4) |

Mediciones **descriptivas** (2026-09-25) sobre velas reales cerradas de Binance: 4 pares × 5
marcos = 20 series de 999 velas y **18 000 instantes**. Se compara además con una **caminata
aleatoria** con exactamente las mismas velas barajadas (mismos retornos y formas, sin orden
temporal). Porcentaje de instantes por estado:

| `window_swings` | `significance` | Datos | `UPTREND` | `DOWNTREND` | `RANGE` | `TRANSITION` | Cambios de estado entre instantes consecutivos |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 4 | 0,10 | reales | 21,8 | 18,7 | 0,6 | 58,8 | 8,4 % |
| 4 | 0,10 | aleatoria | 22,6 | 16,6 | 1,0 | 59,7 | 7,5 % |
| **4** | **0,15** | **reales** | **18,2** | **15,4** | **1,5** | **64,9** | **8,4 %** |
| **4** | **0,15** | **aleatoria** | **19,5** | **14,4** | **2,3** | **63,8** | **7,8 %** |
| 4 | 0,25 | reales | 11,7 | 9,1 | 7,7 | 71,4 | 8,8 % |
| 4 | 0,25 | aleatoria | 12,7 | 9,1 | 7,7 | 70,6 | 8,1 % |
| 6 | 0,15 | reales | 2,1 | 2,0 | 0,0 | 95,7 | 1,2 % |
| 6 | 0,15 | aleatoria | 3,2 | 2,1 | 0,0 | 94,7 | 1,3 % |

Por qué esos valores:

1. **`window_swings = 6` se descartó.** Exigir tres máximos y tres mínimos ordenados deja el
   92–98 % de los instantes en `TRANSITION`: un clasificador que casi nunca clasifica no aporta
   información. Con 4 (la lectura clásica de máximos y mínimos crecientes o decrecientes) el
   reparto es legible.
2. **`significance = 0,15`** es un punto intermedio: 0,10 marca tendencia con escalones muy
   pequeños; 0,25 casi no deja tendencias y sube los rangos. Con 0,15 una tendencia exige que cada
   escalón supere el 15 % de la altura del tramo.
3. **Todo depende de una sola banda**, para que un lado no sea direccional y llano a la vez.

**Lo que estas cifras NO demuestran.** Sobre la caminata aleatoria salen porcentajes casi iguales
a los reales: estos estados **describen la forma de la estructura de precio, no que el mercado
tenga una tendencia predecible**. Ninguna cifra de aquí dice que `UPTREND` sea mejor o peor que
otro estado para nada. No se afirma que los parámetros sean los mejores, ni rentables, ni
seguros. Los valores son **provisionales**; la rejilla candidata para validarlos, fuera de
muestra y con criterios fijados de antemano (POINT2-TEST-001 y punto 15), es
`window_swings ∈ {4, 6}` y `significance ∈ {0,10; 0,15; 0,25}`.

## 8. Límites conocidos

- **Retraso.** Un pivote se conoce `k = 3` velas después (15 min en 5 m, 12 h en 4 h). Una
  ruptura por cierre se ve antes, sin esperar a un pivote nuevo.
- **Mucho `TRANSITION`.** Cerca de dos tercios de los instantes son «conflicto o ruptura». Es lo
  que dice la definición con datos reales y con la caminata aleatoria; no es un fallo.
- **`RANGE` es raro** con `significance = 0,15` (1–2 %): exige límites tocados dos veces dentro de
  una banda estrecha.
- **La ventana son 100 velas**: la estructura anterior no cuenta.
- **Estado al cambiar de marco**: un cambio de `window_swings` o `significance` es un cambio de
  parámetros y queda registrado en el resultado; un cambio de cómo se derivan los estados sube la
  versión.

## 9. Fuera de alcance

No define señal, entrada, ventana de entrada, caducidad, horizonte, tamaño, salidas ni riesgo. No
aplica política (POINT2-POLICY-001), no persiste el snapshot (POINT2-SNAPSHOT-001), no expone API
ni interfaz, no lee la base de datos (recibe las velas ya leídas), no usa indicadores, figuras ni
patrones de velas, y no valida los parámetros (POINT2-TEST-001 y punto 15).

## 10. Criterios de aceptación

- [x] Sin _look-ahead_: comprobado para cada instante de series aleatorias (sección 6).
- [x] Resultado reproducible: mismas entradas, mismo resultado; versión y parámetros registrados.
- [x] `INSUFFICIENT_DATA` es fail-closed, con los motivos concretos (sección 5).
- [x] Los dos marcos se clasifican por separado y no se comprimen en una etiqueta (sección 4).
- [x] El par de marcos es configuración versionada de la estrategia, no un mapa universal.
- [x] No genera señales ni invoca ejecutor, broker ni notificaciones.
- [x] Parámetros justificados con datos y marcados como no validados (sección 7).
