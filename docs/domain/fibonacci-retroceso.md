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
  buscan los impulsos** (qué pares se consideran) se define en la sección 16.

## 3. Cuándo existe un Fibonacci: dos tiempos que no se confunden

Un pivote solo se puede conocer `k` velas después de formarse. Hay **dos instantes distintos** y la
herramienta conserva **los dos**, siempre:

| Tiempo | Qué es | De quién es |
| ------ | ------ | ----------- |
| `pivot_confirmed_market_time` | el cierre de la `k`-ésima vela posterior a `B`: cuándo se confirma el pivote **en el mercado** | del par de pivotes (el de `A` es anterior) |
| `pivot_received_at` | el instante en que Freyja **recibió realmente** esa vela terminada | de los datos (cada vela guardada tiene su `received_at`) |
| `known_at` | el **mayor** de los dos: desde aquí el Fibonacci existe **para Freyja** | de la observación; **sin conocer** si no se conoce la recepción |

**Reglas, que son parte del contrato:**

1. **No se atribuye a la apertura de una vela un conocimiento que en vivo todavía no habría llegado.**
   Una vela es operable solo si **abrió en `known_at` o después**. Una vela que abrió después de la
   confirmación de mercado pero **antes de que Freyja recibiera** la vela que la confirmó no es operable:
   sus toques son retrospectivos, aunque abriera cuando el mercado ya había confirmado el pivote.
2. **Tres estados**, que lleva cada hecho (`availability`), y solo el primero puede usarse como si se
   hubiera visto entonces. **`OPERABLE` significa únicamente «el nivel era conocido desde la apertura de
   esa vela»**: no afirma que existiera una entrada ejecutable, ni un precio al que operar, ni una
   señal. Que se pudiera entrar, y cómo, lo decide cada `StrategySpec`:

   | Estado | Cuándo |
   | ------ | ------ |
   | `OPERABLE` | su vela abrió en `known_at` o después: el **nivel ya era conocido desde la apertura de esa vela** |
   | `RETROSPECTIVE` | su vela abrió antes de `known_at` (o antes de la confirmación de mercado): un hecho sobre el pasado, útil para estudiar y **nunca historia operable** |
   | `UNPROVEN` | su vela abrió tras la confirmación de mercado, pero **no se conoce la recepción** de la vela que la confirmó: no se afirma ni se niega |

3. **Qué recepción es la buena: la de la versión que cuenta** (confirmado por Jessica, 2026-09-26: la
   «vela definitiva» es la **primera versión cerrada recibida**). `pivot_received_at` es el instante en
   que Freyja recibió la vela confirmadora **con los valores que se usan para decidir**: la **primera
   versión cerrada recibida** (ADR 0008, §6). No es la recepción de una versión provisional en curso ni
   la de una revisión posterior del proveedor. En el almacén de velas esto se cumple por construcción:
   una vela guardada **nunca se reescribe** (ni sus valores ni su `received_at`), y una diferencia posterior
   se **señala como revisión sin aplicarse** (pruebas de integración de la sincronización de datos). Las
   velas (`closed`) y sus recepciones (`received_at`) que se pasan a la herramienta tienen que ser **de la
   misma lectura, «tal como era»**; una vela revisada después (`REVISED`) no cambia el impulso calculado
   con la versión que contó, y su señalamiento lo hace la capa de datos (`MARKET-DATA-REVISIONS-001`,
   pendiente), no esta herramienta.
4. **Sin registro de recepción, nada posterior a la confirmación se da por operable** (`UNPROVEN`,
   fail-closed). En particular, las velas **rellenadas a posteriori** traen como `received_at` la hora del
   relleno, no la de su llegada en vivo: no sirven para probar cuándo se supo algo. Una prueba histórica
   que necesite operabilidad exige recepciones reales o una hipótesis de latencia declarada aparte
   (fuera de esta herramienta: es de la prueba de la estrategia).
5. **Datos recibidos con retraso.** Una vela que ya cerró pero que Freyja aún no había recibido en
   `observed_at` **no se lee**. Pedir una observación antes de `known_at` es una petición equivocada. Una
   vela terminada no puede recibirse antes de cerrar (dato incoherente: se rechaza). Una vela sin
   recepción en el registro que se pasa **no se lee**.
6. **Consecuencias de la confirmación de mercado**, que valen aunque no se conozca la recepción: un toque
   ocurrido en una vela anterior a ella, incluida la vela cuyo cierre confirma `B`, **no es un toque de un
   Fibonacci conocido**: el nivel se calculó después. **No se pierde ni se disfraza**: se registra como
   observación retrospectiva. Y si el precio ya retrocedió más allá de un nivel cuando el Fibonacci se
   conoce, ese nivel se registra como **superado retrospectivamente**, no como tocado en directo.

**Ejemplo con retraso** (velas de 5m, `B` en la vela de las 10:00): las tres velas posteriores abren a las
10:05, 10:10 y 10:15; la tercera cierra a las 10:20:00, así que `pivot_confirmed_market_time` es 10:20:00.
Si Freyja la recibió a las 10:22:30, `known_at` es 10:22:30. La vela que abre a las 10:20 abrió cuando el
mercado ya había confirmado el pivote pero Freyja aún no lo sabía: es **retrospectiva**. La primera vela
**operable** es la que abre a las 10:25. Con la recepción sin retraso (10:20:00), la de las 10:20 sería la
primera operable.

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

- **Identidad:** serie, `A`, `B` (sus instantes y tipos), versión de la calculadora, de la convención, de
  los parámetros y **de la política de búsqueda**. Los mismos anclajes con las mismas versiones son la misma instancia.
- **Los niveles no se recalculan ni se redibujan.** Un Fibonacci conocido es inmutable.
- **El historial de la instancia solo se añade** (toques, cierres más allá, máximo retroceso), como el
  de una figura chartista.
- **Un extremo nuevo aparecido antes de confirmarse `B` no cierra nada** (sección 2): `B` se sustituye
  como candidato.
- **Un extremo nuevo aparecido cuando el Fibonacci ya existe** (`observed_at ≥ known_at`) **no reescribe
  el pasado**. Se aplica la política versionada `fibonacci-extension-policy-v1`, con estos estados y
  tiempos (para un impulso alcista; el bajista es el espejo):

  | Estado | Empieza | Termina | Qué ocurre |
  | ------ | ------- | ------- | ---------- |
  | `CANDIDATE_B` | al cerrar la vela cuya mecha marca un extremo | al confirmarse como pivote, o al aparecer un extremo mayor (lo sustituye) | **no existe ninguna instancia**: nada se registra por él |
  | `ACTIVE` | `known_at` de la instancia | en la extensión | la instancia observa velas y registra hechos |
  | `EXTENDED` | al cerrar la primera vela `E` cuyo máximo supera `B` | nunca: es final | la instancia se conserva íntegra y **no registra nada más** |
  | `NO_ACTIVE_FIBONACCI` | cuando Freyja recibe `E` | al nacer la nueva instancia, o al abandonarse el candidato | intervalo **sin Fibonacci vigente** |

  **Tiempos de la extensión**, todos guardados y ninguno reescrito después:

  - `coverage_end` = la **apertura** de `E`: la instancia anterior no observa `E` ni las siguientes (no
    se sabe si los mínimos de `E` fueron anteriores o posteriores a su nuevo máximo).
  - `extension_market_time` = el **cierre** de `E`, cuando el mercado ya ha superado `B`.
  - `extension_received_at` = la **recepción** de `E` por Freyja: desde aquí, y no antes, Freyja sabe que
    la instancia anterior terminó.
  - **Intervalo de incertidumbre `[coverage_end, extension_received_at)`**: en ese lapso la instancia
    anterior seguía figurando vigente para Freyja aunque el mercado ya la había superado. Queda
    registrado y visible; no se corrige a posteriori.

  **Mientras el nuevo extremo es candidato** (`CANDIDATE_B`): no hay ninguna instancia activa; la anterior
  ya terminó y la nueva aún no existe. Los toques de las velas de ese intervalo **no se registran en
  ninguna**: ni en la anterior (su cobertura terminó) ni en la nueva (no existe). Si antes de confirmarse
  aparece un extremo aún mayor, el candidato se sustituye y el intervalo **sigue abierto**.

  **Cuándo nace la nueva instancia**: en el `known_at` de la nueva (el mayor de la confirmación de mercado
  y la recepción de la vela que confirma el nuevo `B'`), con el nuevo `B'` y **sus dos tiempos propios**,
  y solo si su `A` y `B'` cumplen la regla de extremos de la sección 2. Su `A` es **el que elige la
  política de búsqueda** (sección 16): el mismo que el de la instancia anterior si sigue dentro de la
  ventana, otro si ya salió de ella. Cuando cambia, es otro Fibonacci con otra identidad, no el anterior
  redibujado. Las velas entre el
  cierre del extremo `B'` y ese `known_at` son **retrospectivas** para la nueva. Si el precio hace un
  mínimo por debajo de `A` (por mecha) mientras el intervalo sigue abierto, el candidato se **abandona**
  y el intervalo se cierra como `CANDIDATE_ABANDONED` (el retroceso ya superó el 100 %). **Eso no impide
  que la búsqueda encuentre después un impulso válido**: si el mínimo llega *después* de `B'`, el par
  `(A, B')` sigue cumpliendo la regla de extremos (que solo mira de `A` a `B'`), así que nace su
  instancia por su cuenta, sin cerrar un intervalo que ya se cerró; todo lo que ocurrió antes de su
  `known_at` es retrospectivo para ella.

  **Registro que solo se añade**, sin borrar ni editar: `EXTENSION_DETECTED` (con `coverage_end`,
  `extension_market_time` y `extension_received_at`), `GAP_OPENED` (con el instante real de inicio) y
  `GAP_CLOSED` con su motivo (`NEW_INSTANCE` o `CANDIDATE_ABANDONED`) y su instante. Un intervalo aún
  abierto se ve como abierto; cuando se cierra se **añade** el cierre, no se reescribe la apertura.

  1. La instancia anterior **se conserva íntegra**, con todo lo que registró hasta `coverage_end`.
  2. Desde `coverage_end` **no registra nada más**.
  3. Entre `extension_received_at` y el `known_at` de la nueva **no hay ningún Fibonacci vigente**: no se
     usa el anterior ni se adelanta el nuevo.
  4. Nada se redibuja como si se hubiera sabido antes.

## 6. Qué registra sobre el precio (hechos, no decisiones)

**Velas observadas:** las velas cerradas **posteriores a la vela de `B`** y con `close_time ≤
observed_at`. (La vela de `B` no se observa: en ella se formó el extremo.) Pedir una observación en un
instante anterior a `known_at` (o, sin recepción, a `pivot_confirmed_market_time`) es una petición
equivocada: el Fibonacci aún no existe.

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
  vela `OPERABLE`: la que **abre en `known_at` o después**, sección 3);
- el **primer cierre más allá** y el **primer cierre más allá operable**, con la misma distinción;
- cada hecho lleva su `availability` (`OPERABLE`, `RETROSPECTIVE` o `UNPROVEN`, sección 3).

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
| `search_window_candles` | 100 | velas hacia atrás desde `B` dentro de las que puede estar `A` (sección 16) |
| política de búsqueda | `fibonacci-search-v1` | el tramo dominante que termina en cada swing (sección 16) |
| política de extensión | `fibonacci-extension-policy-v1` | sección 5 |

## 11. Pruebas que este contrato exige a quien lo implemente

1. **Espejo exacto**: cada nivel alcista es el bajista al revés, para cada nivel y cada temporalidad.
2. **Todas las temporalidades**: los mismos resultados para la misma forma de precios en 1m, 5m, 15m,
   1h y 4h; ninguna regla depende de la temporalidad.
3. **Instantes exactos de disponibilidad, en los dos tiempos**: `pivot_confirmed_market_time` es el cierre
   de la `k`-ésima vela posterior a `B`; una vela que abre **en** `known_at` es operable; la que abre un
   instante antes (por ejemplo la que cierra en `known_at`) es retrospectiva; observar antes de `known_at`
   es una petición equivocada. **Con un dato recibido con retraso**: `known_at` es el de la recepción y
   no el del mercado, las velas que abrieron entre los dos son retrospectivas, y una vela cerrada pero aún
   no recibida no se lee. Sin registro de recepción, nada posterior a la confirmación es `OPERABLE`.
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
- **FIB-DETECT-001**, limitada a **búsqueda de impulsos y ciclo de vida**: hecha (secciones 16 y 17). **No**
  incluye confirmación de rechazo, entrada, vencimiento ni ninguna regla de estrategia: esperan el
  ejemplo real de Jessica.
- **Valores a validar con datos reales**: `min_impulse_fraction`, `range_window_candles`, `k`.

## 16. Búsqueda de impulsos (`fibonacci-search-v1`)

**Qué pares de pivotes se consideran impulsos.** Es una decisión técnica de FIB-DETECT-001 (primera
parte), documentada aquí para poder corregirla; no dice nada de zonas, confirmación, entrada ni
vencimiento.

**Política v1: el tramo dominante que termina en cada swing confirmado.** Aprobada por Jessica
(2026-09-26) **como la política v1, no como el único impulso posible**: otras políticas versionadas
podrán coexistir con ella, en particular los **tramos entre swings consecutivos** (patas elementales),
que interesan sobre todo a las estrategias de 1m. Cada política lleva su versión, forma parte de la
identidad de las instancias y no sustituye a las demás.

- Cada swing confirmado `B` (`swing_points`) da, como mucho, **un** impulso: un máximo, uno alcista; un
  mínimo, uno bajista.
- El inicio `A` es el **swing opuesto más antiguo**, a no más de `search_window_candles` velas de `B`,
  con el que el par es un impulso según la sección 2 (sin mechas fuera de los extremos de la vela de `A`
  a la de `B`, y con el tamaño suficiente). Es, por definición de esa regla, el mínimo más bajo (máximo
  más alto, en el bajista) desde la última vez que el precio superó `B`.
- **Nada anterior a la última vela que superó `B` por mecha** puede iniciar un impulso que acabe en `B`:
  lo impide la regla de extremos de la sección 2, y es ella la que decide, no un atajo de la búsqueda.
  **La igualdad no supera**: un máximo idéntico al de `B` (un doble techo exacto) no corta la búsqueda.
- **Las 100 velas son un parámetro provisional de esta política** (`search_window_candles` de
  `fibonacci-search-v1`), sin validar, a registrar en PARAMS-VALIDATION-001; no es una ley del producto.
- **La ventana acota lo que depende del origen de los datos**: `A` no puede estar más lejos de `B` que
  `search_window_candles`, así que el resultado en `B` depende solo de las velas de su entorno (más las
  `range_window_candles` anteriores a `A` para medir el tamaño), nunca de dónde empiece la historia que se
  entregue.
- **Datos no aptos no se juzgan**: como en las figuras chartistas, si el contexto observable de la serie
  no es suficiente (hueco en la ventana, datos atrasados, fuente no autorizada, poca historia) no se
  devuelve ningún impulso y se dice por qué. La historia mínima es `range_window_candles`.
- **Solo velas cerradas y pivotes confirmados** en `observed_at`: el mismo resultado con las velas
  cerradas hasta ese instante que con toda la serie. Un swing no entra en la búsqueda hasta que su
  pivote se confirma; un mínimo posterior a `B` que aún no se conoce no cambia la selección.

**Ejemplo: seis inicios candidatos para un mismo `B`** (velas de 5m; `B` es el máximo de 130,5 de la
vela 120, que se confirma al cierre de la vela 123, es decir, desde la apertura de la vela 124; la
ventana llega hasta la vela 20):

| Candidato | Vela | Mínimo | ¿En la ventana? | Regla de extremos | Resultado |
| --------- | ---- | ------ | --------------- | ----------------- | --------- |
| L1 | 10 | 99,5 | **no** (a 110 velas de `B`) | (fallaría también) | descartado por la ventana |
| L2 | 30 | 95,5 | sí | **falla**: la mecha de 150,5 (vela 40) está por encima de `B` | descartado |
| **L3** | **50** | **101,5** | sí | **cumple** (ningún máximo > 130,5, ningún mínimo < 101,5) | **elegido**: el más antiguo que cumple |
| L4 | 70 | 103,5 | sí | cumple | válido, pero más reciente que L3 |
| L5 | 90 | 105,5 | sí | cumple | válido, pero más reciente que L3 |
| L6 | 110 | 107,5 | sí | cumple | válido, pero más reciente que L3 |

`fibonacci-search-v1` selecciona **L3**: el impulso de 101,5 a 130,5 (29,0 de altura, 70 velas). Con la
ventana en 69 velas, L3 queda fuera y selecciona **L4**; con 70, sigue siendo L3 (la ventana es
inclusiva). Antes del instante de apertura de la vela 124 no existe ningún impulso que acabe en `B`: su
pivote aún no está confirmado.

**Lo que esta política no hace**, y se añadirá, si se decide, como otra política versionada que
coexista con ella: considerar las patas
elementales entre swings consecutivos dentro de un tramo dominante (un rally con retrocesos intermedios da
una sola pata larga por swing, no una por cada retroceso interno).

**Ciclo de vida**: sección 17.

## 17. Ciclo de vida implementado (`fibonacci-extension-policy-v1`)

`replay_lifecycle` sigue una serie tal como llegó y mantiene, por instancia, un **registro que solo se
añade**. Es una implementación de referencia (vuelve a buscar en cada instante): correcta y simple, no
incremental.

**Instantes.** Son aquellos en que Freyja aprendió algo: el cierre de cada vela o, si se dan las
recepciones (`received_at`), esas recepciones. En cada instante solo se leen las velas **cerradas y
recibidas** para entonces: nada depende de lo posterior, y los registros de un historial más corto son un
prefijo de los de uno más largo. Si los datos no son aptos en un instante (hueco, historia corta, fuente no
autorizada), **no se afirma nada** en él (fail-closed); lo que habría mostrado se registra cuando los datos
vuelvan a ser aptos, con el instante posterior.

**Instancia.** Un Fibonacci tal como se conoció: identidad (serie, dirección, `A`, `B` y las versiones de
parámetros, niveles, convención y búsqueda), su impulso, `pivot_confirmed_market_time`,
`pivot_received_at` y `known_at` (sección 3). Inmutable.

**Registros** (`LifecycleRecord`), cada uno con `sequence`, `recorded_at` (el instante en que Freyja lo
supo), `market_time` (cuándo ocurrió en el mercado) y `received_at` (cuándo recibió Freyja la vela que lo
prueba; `None` si no se conoce):

| Tipo | Cuándo | Campos propios |
| ---- | ------ | -------------- |
| `INSTANCE_BORN` | al conocerse el Fibonacci (pivote `B` confirmado y su vela confirmadora recibida) | `market_time` = confirmación de mercado |
| `EXTENSION_DETECTED` | la primera vela (recibida) que supera `B` por mecha, estrictamente | `coverage_end` = apertura de esa vela; `market_time` = su cierre; `received_at` = su recepción |
| `GAP_OPENED` | a la vez que la extensión | los mismos tiempos |
| `GAP_CLOSED` | al cerrarse el intervalo | `closure` = `NEW_INSTANCE` (con `successor_id`) o `CANDIDATE_ABANDONED` |

- **`NEW_INSTANCE`**: nace una instancia de la misma dirección cuyo `B'` está más allá del `B` anterior y no
  es anterior a la vela que lo superó. Varias instancias antiguas pueden cerrarse con la misma sucesora.
- **`CANDIDATE_ABANDONED`**: una vela (desde la que superó `B`) supera `A` por mecha mientras el intervalo
  está abierto.
- Un intervalo sin cerrar se ve como **abierto**; al cerrarse **se añade** el cierre, la apertura no se
  reescribe. `Gap.uncertainty` devuelve `(coverage_end, extension_received_at)`: el lapso en que la
  instancia anterior seguía figurando vigente para Freyja aunque el mercado ya la había superado.
- **Estado de una instancia derivado de los registros**: `ACTIVE` mientras no haya `EXTENSION_DETECTED`;
  `EXTENDED` después, y es final.
- El candidato a `B'` (`CANDIDATE_B`) **no genera registro propio**: no existe instancia. Si antes de
  confirmarse aparece un extremo mayor, el candidato se sustituye y nunca nace nada por el descartado.
- Un máximo exactamente igual a `B` (un doble techo) **no supera** `B`: no extiende.

**Lo que no hace**: ninguna regla de zona, confirmación de rechazo, entrada, vencimiento ni señal.
