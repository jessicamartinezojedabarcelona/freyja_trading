# Retroceso de Fibonacci: la herramienta bidireccional (v1, propuesta)

- **Estado:** propuesto. Pendiente de la aprobación de Jessica antes de implementar nada.
- **Fecha:** 2026-09-26
- **Tarea:** FIB-DOMAIN-001 (contrato; solo documento).
- **Depende de:** [estructura-de-precio.md](estructura-de-precio.md) (pivotes confirmados y cuándo se
  pueden conocer) y [instancia-de-figura.md](instancia-de-figura.md) (mismo estilo de instancia
  inmutable con historial que solo se añade).
- **Lo usarán:** FIB-CALC-001 (cálculo), FIB-DETECT-001 (detección) y, más adelante y por separado,
  cada `StrategySpec` que quiera usar los niveles. Este documento **no define ninguna estrategia**.
- **Posición en la hoja de ruta:** por confirmar con Jessica (¿herramienta de localización dentro del
  punto 5, o punto propio?). No cambia el contrato.

## 1. Qué es y qué no es

Fibonacci es una **medición reproducible**: dado un impulso ya observado, calcula los precios donde
el movimiento contrario, si llega, habría devuelto ciertas fracciones de él, y registra si el precio
llegó a ellos. Los niveles son **zonas de precio que se observan**, no señales ni probabilidades de
rebote. El 50 % no procede de la sucesión de Fibonacci: se incluye porque la herramienta de trading
lo incorpora habitualmente.

**Decisiones de producto de Jessica (2026-09-26) que este contrato aplica:**

1. **Bidireccional.** Se calcula para impulsos **alcistas y bajistas**, con el mismo contrato.
2. **En todas las temporalidades admitidas** por Freyja (las del catálogo de temporalidades, hoy 1m,
   5m, 15m, 1h y 4h; una temporalidad nueva del catálogo la tiene sin cambiar este contrato).
3. **Los ejemplos no son límites.** El bajista 5m de Notion y el alcista 1m de sus imágenes sirven para
   debatir entrada y vencimiento; ninguno es una variante única del producto y **ninguna regla de uno se
   extrapola al otro ni a ninguna temporalidad**.
4. **La herramienta y las `StrategySpec` están separadas** (sección 9).

## 2. Un impulso válido

Un impulso es un par de **pivotes confirmados** (`pivots-v1`, `swing_points`), `A` (inicio) y `B`
(final), de **la misma serie** (instrumento, fuente y temporalidad) que cumplen:

| | Impulso alcista | Impulso bajista |
| - | --------------- | --------------- |
| `A` | mínimo (`pivot_low`) | máximo (`pivot_high`) |
| `B` | máximo (`pivot_high`) | mínimo (`pivot_low`) |
| orden | `B` es posterior a `A` | `B` es posterior a `A` |
| extremos | entre `A` y `B` ninguna vela tiene un mínimo por debajo del de `A` ni un máximo por encima del de `B` | entre `A` y `B` ninguna vela tiene un máximo por encima del de `A` ni un mínimo por debajo del de `B` |

- **Los extremos son los de las mechas** (el mínimo y el máximo de las velas de los pivotes), que es lo
  que ya guardan los pivotes. No se mezclan cierres.
- **El tamaño se mide en relación con lo reciente, nunca en una cantidad fija**: `D = |B − A|` debe ser
  al menos una fracción (`min_impulse_fraction`, provisional) del rango de precios de las
  `range_window_candles` velas que terminan en `A`, como en las figuras chartistas. Un número fijo de
  euros o de pips no vale para todos los activos.
- **La duración se guarda, no se filtra**: el número de velas del impulso (`impulse_candles`) queda
  registrado sin exigir un mínimo ni un máximo. Un impulso de 8 velas de 5m son 40 minutos.
- Dos personas podrían escoger extremos distintos a ojo; aquí la regla anterior los fija y **cómo se
  buscan los impulsos** (qué pares se consideran) se define en FIB-DETECT-001, no aquí.

## 3. Cuándo existe un Fibonacci: el instante de conocimiento

Un pivote solo se puede conocer `k` velas después de formarse (`confirmed_at`: el cierre de la
`k`-ésima vela posterior). **El Fibonacci de un impulso `A→B` empieza a existir en `known_at =
confirmed_at(B)`** (el de `A` es anterior), más la latencia con la que el proveedor publica esa vela.
Antes de ese instante **no hay Fibonacci que tocar**.

**Consecuencias, que son parte del contrato:**

1. **Solo las velas que abren en `known_at` o después pueden registrar un toque de un Fibonacci
   conocido.** Un toque ocurrido en una vela anterior, incluida la vela cuyo cierre confirma `B`, no lo
   es: el nivel se calculó después.
2. **Ese toque anterior no se pierde ni se disfraza: se registra como observación retrospectiva**
   (`retrospective = true`). Es un hecho sobre el pasado, útil para estudiar, y **nunca una señal
   histórica operable**: una prueba de estrategia no puede usarlo como si se hubiera visto entonces.
3. Si el precio ya retrocedió más allá de un nivel cuando el Fibonacci se conoce, ese nivel se registra
   como **superado retrospectivamente**, no como tocado en directo.

## 4. Fórmulas

Sean `A` y `B` los precios de los anclajes, `D = |B − A|` y `r` la fracción de retroceso.

| Impulso | Nivel `r` |
| ------- | --------- |
| Alcista (`A` < `B`) | `B − r · D` |
| Bajista (`A` > `B`) | `B + r · D` |

Ejemplos exactos: impulso alcista 100 → 120: el 50 % está en 110 y el 61,8 % en 107,64. Impulso bajista
120 → 100: el 50 % está en 110 y el 61,8 % en 112,36. **El bajista es el alcista al revés**: si todos los
precios `p` se sustituyen por `K − p`, los niveles de uno son exactamente los del otro sustituidos igual
(propiedad que las pruebas de FIB-CALC-001 deben comprobar, para las dos direcciones).

- Aritmética **`Decimal` exacta**: se multiplica antes de dividir y el nivel se redondea a los 12
  decimales con los que se guardan los precios. Nunca `float`.
- **Catálogo de niveles versionado** (`fibonacci-levels-v1`): 0,236; 0,382; 0,5; 0,618; 0,786 como
  constantes decimales exactas (no se recalculan a partir de la sucesión). Solo retrocesos; las
  extensiones (zonas fuera del impulso) quedan fuera de esta versión.
- **Convención de precios versionada** (`fibonacci-convention-v1`): extremos de mecha y **escala
  lineal**. La escala logarítmica, si se quiere, será otra convención con otra versión: no se alternan
  según qué dibujo «queda mejor». El gráfico, el backend y las pruebas históricas usan **la misma**
  convención y obtienen los mismos precios.

## 5. La instancia y su estabilidad

- **Identidad:** serie, `A`, `B` (sus instantes y tipos), versión de la calculadora, de la convención y
  de los parámetros. Los mismos anclajes con las mismas versiones son la misma instancia.
- **Los niveles no se recalculan ni se redibujan.** Un Fibonacci conocido es inmutable.
- **Un extremo nuevo no reescribe el pasado.** Si el precio supera `B` antes de retroceder (un nuevo
  máximo en un impulso alcista), el Fibonacci vigente se cierra como **superado por extensión** y, si el
  nuevo extremo llega a ser un pivote confirmado, nace **otra instancia** con su propio `B` y su propio
  `known_at`. Nada se reescribe como si se hubiera sabido antes.
- El historial de la instancia **solo se añade** (toques, cierres más allá, máximo retroceso), como el de
  una figura chartista.

## 6. Qué registra sobre el precio (hechos, no decisiones)

Para cada nivel de `fibonacci-levels-v1`, por separado, con su vela e instante y con la marca
`retrospective`:

- el **primer toque**: la mecha llega al nivel (alcista: el mínimo de la vela ≤ el nivel; bajista: el
  máximo ≥ el nivel);
- el **primer cierre más allá** del nivel;
- y, para el conjunto: el **máximo retroceso** alcanzado (como fracción de `D`, por mechas y por
  cierres) y la **distancia** al nivel más cercano en fracción de `D`.

La herramienta **no aplica tolerancias ni zonas**: distingue solo «tocó», «cerró más allá» y «no
llegó». Qué significa «entrar en una zona» (por ejemplo 50 %–61,8 %), con qué tolerancia, y cuál de esos
hechos cuenta, lo decide cada `StrategySpec`. La zona 50 %–61,8 % es una **hipótesis de trabajo** de
Jessica; 38,2 %, 50 % y 61,8 % se registran por separado y no se declara ninguno «más seguro».

## 7. Datos que usa

Solo **velas cerradas** de la serie de anclaje (1m o más, las del catálogo). **Nada intrabar**: la
herramienta no mira cotizaciones dentro de una vela. Una estrategia que entre mientras la vela se forma
necesitará un dato distinto (cotizaciones con marca de tiempo) y una decisión aparte sobre cómo
guardarlo y probarlo sin anticipar información; con velas de 1m no se sabe si el máximo de una vela llegó
antes que su mínimo.

## 8. Un solo campo de temporalidad

La herramienta conoce **`anchor_timeframe`**: la serie de la que se eligieron los extremos. «Impulso de
5m» significa que los pivotes salen de velas de 5m; no que el impulso dure cinco minutos. Los demás
campos que la investigación propone (`signal_timeframe`, `context_timeframe`, `prediction_horizon`,
`entry_window`) **no son de la herramienta**: pertenecen a la `StrategySpec` que los use.

## 9. Herramienta y `StrategySpec`

| La herramienta (este contrato) | Cada `StrategySpec` |
| ------------------------------ | ------------------- |
| Mide: impulso, niveles, toques, retroceso máximo | Decide: zona, confirmación, entrada, horizonte, invalidación |
| Igual alcista y bajista | Una variante por dirección y temporalidad, cada una con sus reglas |
| Igual en cualquier temporalidad | Declara su propio horizonte |
| Solo velas cerradas | Puede exigir otro dato (intrabar, contexto de otra temporalidad) |
| Sin N ni N+1, sin strike, sin vencimiento, sin payout | Los define, y los define **sin heredarlos de otra variante** |

Conceptos que una `StrategySpec` debe mantener **separados** y no usar unos como sustitutos de otros
(decisión de Jessica, 2026-09-26):

- **dirección de la vela objetivo**: `close` frente a `open`;
- **resultado de una binaria**: precio de liquidación frente al strike del contrato, con el precio y la
  hora del broker;
- **rentabilidad efectiva**: incluye el payout.

**Tipo de contrato binario, sin seleccionar.** Hay dos modelos distintos y **ninguno está elegido**: un
contrato de **duración desde la compra** (vence a la hora de compra más una duración) y uno de
**vencimiento a hora fija** (vence a una hora determinada). Solo puede usarse el que el broker ofrezca
de verdad; los contadores de las imágenes de Jessica no prueban cuál es. No se supone «hora de entrada +
60 s».

Variantes conocidas, **solo como candidatas y sin especificar todavía**: `A_CLOSE_1M` (alcista 1m,
entrada tras cerrar N), `A_INTRABAR_1M` (alcista 1m, entrada durante N) y `B_5M` (bajista 5m, descrita
en Notion: confirmación al cierre de N, hipótesis sobre N+1, entrada al empezar N+1 y vencimiento
correspondiente a su cierre; **pendiente**: el patrón exacto que confirma el rechazo y el retraso
permitido). Ningún ejemplo con velas de este repositorio es una regla aprobada; Jessica dará un ejemplo
real antes de definir una estrategia concreta.

## 10. Parámetros provisionales (`fibonacci-params-v1`)

Razonados, sin validar, para registrar en PARAMS-VALIDATION-001 cuando se implementen. Todos relativos.

| Parámetro | Significado |
| --------- | ----------- |
| `min_impulse_fraction` | fracción mínima del rango reciente que debe medir el impulso (valor por fijar en FIB-DETECT-001) |
| `range_window_candles` | velas del rango de referencia que terminan en `A` |
| `pivot_params.k` | el de `pivots-v1` (3) |

## 11. Pruebas que este contrato exige a quien lo implemente

1. **Espejo exacto**: cada nivel alcista es el bajista al revés, para cada nivel y cada temporalidad.
2. **Todas las temporalidades**: los mismos resultados para la misma forma de precios en 1m, 5m, 15m,
   1h y 4h; ninguna regla depende de la temporalidad.
3. **Sin _look-ahead_**: un toque anterior a `known_at` es siempre `retrospective`; el resultado en un
   instante es el mismo con las velas cerradas hasta ese instante que con toda la serie.
4. **Aritmética exacta**: `Decimal`, 12 decimales, sin `float`.
5. **Identidad estable**, y un extremo nuevo crea otra instancia sin tocar la anterior.
6. **Mutación**: cada comparación cambiada a propósito es detectada.

## 12. Lo que este documento no decide

Cómo se buscan los impulsos (FIB-DETECT-001), el valor de `min_impulse_fraction`, las extensiones, la
escala logarítmica, cualquier zona con tolerancia, cualquier regla de confirmación, entrada, retraso
máximo, vencimiento, horizonte, invalidación, stop u objetivo, y la eficacia de nada de esto.

## 13. Sobre la eficacia

Los niveles son fáciles de calcular; elegir el impulso correcto y demostrar que aportan ventaja es lo
difícil. Un estudio revisado sobre acciones de Dow Jones, Nasdaq y DAX no encontró que las zonas de
Fibonacci rebotasen más que otras zonas de soporte y resistencia. Es evidencia sobre esa muestra y esa
metodología, no una refutación de ninguna estrategia en forex o cripto; sí es motivo para **no atribuir
eficacia a ningún nivel por sí solo**. La utilidad de una estrategia con Fibonacci se comprobará con
costes y contra referencias sin Fibonacci (punto 15), nunca por la forma.

## 14. Decisiones técnicas tomadas al redactar

Registradas para poder corregirlas; ninguna es de producto.

1. Extremos de mecha y escala lineal en la v1, versionados, porque son los que ya guardan los pivotes.
2. Solo retrocesos en la v1: las extensiones son otra medición.
3. El instante de conocimiento es el de confirmación del pivote `B` más la latencia de publicación, para
   que ningún toque anterior parezca operable.
4. La herramienta no aplica tolerancias: registrar hechos exactos deja la interpretación a la estrategia.
5. Un impulso propio de la herramienta es un par de pivotes con extremos propios (sección 2), para que
   los anclajes sean únicos y reproducibles.
