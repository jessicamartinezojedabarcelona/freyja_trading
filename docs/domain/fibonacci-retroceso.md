# Retroceso de Fibonacci: la herramienta bidireccional (v1, propuesta)

- **Estado:** enfoque aprobado por Jessica (2026-09-26); precisiones de esa aprobación incorporadas.
  Ver la sección 15 para lo que sigue pendiente.
- **Fecha:** 2026-09-26
- **Tarea:** FIB-DOMAIN-001 (contrato; solo documento).
- **Depende de:** [estructura-de-precio.md](estructura-de-precio.md) (pivotes confirmados y cuándo se
  pueden conocer) y [instancia-de-figura.md](instancia-de-figura.md) (mismo estilo de instancia
  inmutable con historial que solo se añade).
- **Lo usarán:** FIB-CALC-001 (cálculo), FIB-DETECT-001 (detección) y, más adelante y por separado,
  cada `StrategySpec` que quiera usar los niveles. Este documento **no define ninguna estrategia**.
- **Posición en la hoja de ruta:** herramienta de **localización del punto 5** (decisión de Jessica,
  2026-09-26).

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
| «sin velas fuera de los extremos» | ninguna vela de `A` a `B` tiene un mínimo por debajo de `A` ni un máximo por encima de `B` | ninguna vela de `A` a `B` tiene un máximo por encima de `A` ni un mínimo por debajo de `B` |

**Qué significa «sin velas fuera de los extremos»**, con precisión:

- Se comprueba sobre **todas las velas cerradas desde la vela de `A` hasta la vela de `B`, ambas
  incluidas**, y sobre sus **mechas** (el mínimo y el máximo de cada vela), nunca sobre los cierres.
- Es **no estricta**: una vela cuyo mínimo (o máximo) es *igual* al precio del ancla no está fuera.
- Por tanto el precio de `A` es el mínimo (el máximo, en el bajista) de todo ese tramo y el de `B` su
  máximo (su mínimo). Los extremos son únicos y reproducibles.
- Las velas **anteriores a `A`** y **posteriores a `B`** no cuentan para esta regla. Lo posterior a `B`
  es lo que se observa (sección 6) y lo que puede extender el impulso (sección 5).
- **Un par que no la cumple no es un impulso**, no un impulso «casi»: no se ajusta ni se recorta.

**Un extremo nuevo antes de confirmarse `B` sustituye a `B` como candidato.** Mientras `B` no está
confirmado no existe ningún Fibonacci: no hay instancia vigente que cerrar. Si antes de confirmarse
aparece un extremo mayor (menor, en el bajista), `B` deja de ser un pivote —un pivote exige que las `k`
velas siguientes no lo superen— y el nuevo extremo pasa a ser el candidato a `B`, con su propia
confirmación y su propio instante de conocimiento. Nada se cierra ni se registra por el candidato
descartado.

- **Los extremos son los de las mechas** (el mínimo y el máximo de las velas de los pivotes), que es lo
  que ya guardan los pivotes. No se mezclan cierres.
- **El tamaño se mide en relación con lo reciente, nunca en una cantidad fija**: `D = |B − A|` debe ser
  al menos una fracción (`min_impulse_fraction`, provisional: 0,25 como en las figuras chartistas) del
  rango de precios de las `range_window_candles` velas que terminan en `A`. Un número fijo de euros o de
  pips no vale para todos los activos. El valor exacto **sí** cuenta: `D` igual a esa fracción es
  válido, y por debajo no.
- **La duración se guarda, no se filtra**: el número de velas del impulso (`impulse_candles`, de la vela
  de `A` a la de `B`) queda registrado sin exigir un mínimo ni un máximo. Un impulso de 8 velas de 5m
  son 40 minutos.
- Dos personas podrían escoger extremos distintos a ojo; aquí la regla anterior los fija y **cómo se
  buscan los impulsos** (qué pares se consideran) se define en FIB-DETECT-001, no aquí.

## 3. Cuándo existe un Fibonacci: el instante de conocimiento

Un pivote solo se puede conocer `k` velas después de formarse (`confirmed_at`: el cierre de la
`k`-ésima vela posterior). **El Fibonacci de un impulso `A→B` empieza a existir en `known_at = confirmed_at(B)`** (el de `A` es
anterior): el cierre de la `k`-ésima vela posterior a `B`. La latencia con la que el proveedor publica una
vela no se suma a `known_at`: se aplica al **observar**, porque una vela solo se lee cuando ya se ha
publicado (`observed_at`). Antes de ese instante **no hay Fibonacci que tocar**.

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
- **El historial de la instancia solo se añade** (toques, cierres más allá, máximo retroceso), como el
  de una figura chartista.
- **Un extremo nuevo aparecido antes de confirmarse `B` no cierra nada** (sección 2): `B` se sustituye
  como candidato.
- **Un extremo nuevo aparecido cuando el Fibonacci ya existe** (`observed_at ≥ known_at`) **no reescribe
  el pasado**. Se aplica la política versionada `fibonacci-extension-policy-v1`:
  1. La instancia anterior **se conserva íntegra**, con todo lo que registró hasta entonces.
  2. Se anota en ella un **suceso de extensión** con el instante en que cierra la primera vela que
     supera `B` (por mecha, no por cierre: es lo que dice la regla de la sección 2 sobre los extremos).
  3. Desde ese instante **la instancia anterior no registra nada más**: lo que ocurra ya no es el
     retroceso de ese impulso.
  4. Si el nuevo extremo llega a ser un pivote confirmado, **nace otra instancia** con el mismo `A`, el
     nuevo `B` y su propio `known_at`; solo si cumple la regla de extremos de la sección 2. Entre el
     suceso de extensión y ese `known_at` **no hay ningún Fibonacci vigente**: no se usa el anterior ni
     se adelanta el nuevo.
  5. Nada se redibuja como si se hubiera sabido antes.

## 6. Qué registra sobre el precio (hechos, no decisiones)

**Velas observadas:** las velas cerradas **posteriores a la vela de `B`** y con `close_time ≤
observed_at`. (La vela de `B` no se observa: en ella se formó el extremo.) Pedir una observación en un
instante anterior a `known_at` es una petición equivocada: el Fibonacci aún no existe.

**Definiciones, exactas y solo sobre OHLC:**

- **Toque de un nivel `L`**: una vela lo toca si **`low ≤ L ≤ high`** (los dos extremos incluidos). Es
  un hecho sobre el rango de la vela y **nada más**: no dice en qué orden pasó el precio por sus
  valores dentro de la vela, **ni a qué precio se habría podido ejecutar nada, ni que se pudiera
  entrar ahí, ni que sea una señal**. Un toque no atribuye capacidad de entrada.
- **Primer cierre más allá de `L`**, con dirección y nivel explícitos: la primera vela con
  - **`close < L`** en un impulso **alcista** (el precio, retrocediendo hacia abajo, cierra por debajo
    del nivel, del lado de `A`), o
  - **`close > L`** en un impulso **bajista** (el precio, retrocediendo hacia arriba, cierra por encima
    del nivel, del lado de `A`).

  Las desigualdades son **estrictas**: un cierre igual al nivel no está más allá (y es un toque).
- Que una vela toque `L` y otra cierre más allá son hechos **independientes**: una vela puede cruzar un
  nivel entero sin cerrarlo por el otro lado, y un hueco entre velas puede dejar un nivel superado sin
  que ninguna lo toque.

**Para cada nivel** de `fibonacci-levels-v1`, por separado, con su vela y su instante:

- el **primer toque** (de cualquier vela observada) y el **primer toque operable** (el de la primera
  vela que **abre en `known_at` o después**);
- el **primer cierre más allá** y el **primer cierre más allá operable**, con la misma distinción;
- cada hecho lleva la marca `retrospective` (sección 3), verdadera si su vela abrió antes de `known_at`.

**Para el conjunto:** el **máximo retroceso** alcanzado como fracción de `D`, por mechas y por cierres
(0 si el precio no retrocedió), y la **distancia** al nivel más cercano en fracción de `D`.

La herramienta **no aplica tolerancias ni zonas**. Qué significa «entrar en una zona» (por ejemplo
50 %–61,8 %), con qué tolerancia, y cuál de estos hechos cuenta, lo decide cada `StrategySpec`. La zona
50 %–61,8 % es una **hipótesis de trabajo** de Jessica; 38,2 %, 50 % y 61,8 % se registran por separado
y no se declara ninguno «más seguro».

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

## 10. Parámetros versionados (`fibonacci-params-v1`)

Todo lo siguiente es **parámetro con versión**: cambiar cualquiera cambia la versión y, con ella, la
identidad de las instancias. Razonados, sin validar, a registrar en PARAMS-VALIDATION-001. Todos relativos.

| Parámetro | Valor | Significado |
| --------- | ----- | ----------- |
| `pivot_params.k` | 3 | el de `pivots-v1`: velas a cada lado que confirman un pivote |
| `convention` | `fibonacci-convention-v1` | extremos de mecha y escala lineal |
| `levels` | `fibonacci-levels-v1` | 0,236; 0,382; 0,5; 0,618; 0,786 |
| `min_impulse_fraction` | 0,25 | fracción mínima del rango reciente que debe medir el impulso |
| `range_window_candles` | 100 | velas del rango de referencia que terminan en `A` |
| política de extensión | `fibonacci-extension-policy-v1` | sección 5 |

## 11. Pruebas que este contrato exige a quien lo implemente

1. **Espejo exacto**: cada nivel alcista es el bajista al revés, para cada nivel y cada temporalidad.
2. **Todas las temporalidades**: los mismos resultados para la misma forma de precios en 1m, 5m, 15m,
   1h y 4h; ninguna regla depende de la temporalidad.
3. **Instantes exactos de disponibilidad**: `known_at` es el cierre de la `k`-ésima vela posterior a `B`;
   una vela que abre **en** `known_at` es operable; la que abre un instante antes (la que cierra en
   `known_at`) es retrospectiva; observar antes de `known_at` es una petición equivocada.
4. **Sin _look-ahead_**: el resultado en un instante es el mismo con las velas cerradas hasta ese
   instante que con toda la serie.
5. **Toque y cierre más allá exactos**: `low ≤ L ≤ high` con los dos extremos, `close < L` / `close > L`
   estrictos, y ningún resultado depende del orden dentro de la vela ni atribuye entrada o señal.
6. **Regla de extremos**: una vela fuera por una mecha invalida el impulso; una igual al ancla, no;
   los cierres no cuentan.
7. **Aritmética exacta**: `Decimal`, 12 decimales, sin `float`.
8. **Identidad estable**; un extremo antes de confirmarse `B` no cierra nada; uno posterior conserva la
   instancia anterior y crea la nueva según la política de la sección 5.
9. **Mutación**: cada comparación cambiada a propósito es detectada.

## 12. Lo que este documento no decide

Cómo se buscan los impulsos (FIB-DETECT-001), las extensiones de precio (niveles fuera del impulso), la
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
3. El instante de conocimiento es el de confirmación del pivote `B` (la latencia de publicación se aplica al
   observar), para que ningún toque anterior parezca operable.
4. La herramienta no aplica tolerancias: registrar hechos exactos deja la interpretación a la estrategia.
5. Un impulso propio de la herramienta es un par de pivotes con extremos propios (sección 2), para que
   los anclajes sean únicos y reproducibles.

## 15. Lo que sigue pendiente

- **La primera `StrategySpec`** espera el ejemplo real de Jessica: zona, confirmación, entrada, retraso
  máximo, horizonte, invalidación y tipo de contrato quedan sin fijar. Las variantes `A_CLOSE_1M`,
  `A_INTRABAR_1M` y `B_5M` son ejemplos, no estrategias aprobadas.
- **FIB-DETECT-001**: cómo se buscan los impulsos y cómo se aplica la política de extensión en el tiempo.
- **Valores a validar con datos reales**: `min_impulse_fraction`, `range_window_candles`, `k`.
