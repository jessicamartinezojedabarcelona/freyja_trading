# Detectores de figuras de continuación y consolidación (v1)

- **Estado:** vigente. Cubre los ocho detectores: triángulos ascendente, descendente y simétrico,
  rectángulo, y banderas y banderines alcistas y bajistas.
- **Fecha:** 2026-09-26
- **Tarea:** POINT3-CONTINUATION-001 (4 de 7 del punto 3), partes 1 y 2.
- **Depende de:** [figuras-chartistas.md](figuras-chartistas.md) (qué es cada figura),
  [instancia-de-figura.md](instancia-de-figura.md) (cómo se representa),
  [detectores-de-reversion.md](detectores-de-reversion.md) (la fontanería común: qué es un
  detector, cómo se juzga una ruptura, cómo pasan las instancias de un instante al siguiente) y
  [estructura-de-precio.md](estructura-de-precio.md) (pivotes confirmados).
- **Código:** `backend/src/freyja_backend/domain/pattern_channel.py` (triángulos y rectángulo, y el
  canal de dos rectas que comparten), `pattern_flag.py` (banderas y banderines) y, en
  `pattern_detection.py`, lo compartido (`ContinuationParams`, `judge`, evidencias de reprueba y de
  volumen). Dominio puro, sin E/S. Pruebas en `backend/tests/unit/test_pattern_channel.py` y
  `test_pattern_flag.py`.

Todo lo dicho en el documento de reversión sobre **qué hace y qué no hace un detector** vale aquí sin
cambios: es una función pura de lo que se sabía en un instante, sin patrones de velas ni
indicadores, sin señal, lado, objetivo ni confianza, y con datos no aptos no juzga nada. Este
documento describe solo lo que es propio de estas figuras.

## 1. Decisiones de producto aprobadas (Jessica, 2026-09-26)

1. **Ruptura por cierre.** Una ruptura es un cierre de vela más allá de la frontera, con un margen
   versionado (`breakout_margin`). Una mecha no rompe nada.
2. **El retroceso a la línea rota es evidencia, no requisito.** No cambia cuándo ocurrió la ruptura
   ni la confirma o la desconfirma: se registra como un hecho posterior (`RETEST`). Una estrategia de
   entrada por _retest_ podrá exigirlo por separado, pero eso no es asunto del detector.
3. **El triángulo simétrico no tiene dirección anticipada.** Conserva la tendencia previa como
   contexto y toma la dirección de la ruptura confirmada. Lo mismo el rectángulo.
4. **El volumen es evidencia informativa** (`BREAKOUT_VOLUME`), sin requisito universal: no es
   comparable entre fuentes y algunas informan ticks en lugar de unidades. Una `StrategySpec`
   concreta podrá exigirlo más adelante.
5. **Las cuñas se modelan por su geometría**, con sesgo tradicional descriptivo; su papel de
   continuación o de reversión depende de la tendencia previa y de hacia dónde rompan
   (POINT3-EXPANSION-001).
6. **El objetivo proyectado por el mástil** queda fuera de los detectores: pertenece a una política
   posterior de objetivos.

Las decisiones 2 y 4 valen para **todos** los detectores de figuras, también los de reversión ya
construidos: `RETEST` y `BREAKOUT_VOLUME` los emiten los ocho.

## 2. Parámetros (`continuation-params-v1`)

**Provisionales y sin validar.** Están razonados, no medidos, y se registran en PARAMS-VALIDATION-001.
Todos son **relativos a la altura de la figura**, de modo que valen igual en cualquier instrumento
y temporalidad.

| Parámetro | Valor | Significado |
| --------- | ----- | ----------- |
| `min_height_fraction` | 0,25 | La altura debe ser al menos esta fracción del rango de precios de las `range_window_candles` velas que terminan en el primer contacto. Lo más pequeño es ruido. |
| `range_window_candles` | 100 | Ventana del rango de referencia. Se fija al empezar la figura y no cambia después. |
| `contact_tolerance` | 0,15 | Los contactos intermedios de una frontera están, como mucho, a esta fracción de la altura de su recta. |
| `flat_tolerance` | 0,10 | Una frontera es **plana** si, del primer al último contacto, se mueve como mucho esta fracción de la altura. |
| `slope_min` | 0,15 | Una frontera **sube o baja** si se mueve al menos esta fracción de la altura. Entre `flat_tolerance` y `slope_min` no es ni plana ni inclinada: no hay figura de esta familia. |
| `min_channel_candles` | 15 | Un canal abarca, del primer al último contacto, al menos estas velas. |
| `breakout_margin` | 0,10 | Un cierre más allá de la frontera por al menos esta fracción de la altura **confirma** la ruptura; uno menor la deja pendiente. |
| `failure_window_candles` | 10 | Un cierre de vuelta al interior dentro de estas velas desde el primer cierre más allá **hace fracasar** la ruptura. |
| `max_age_candles` | 100 | Una figura sin resolver más vieja que esto (desde su primer contacto) caduca. |
| `min_history` | 100 | Velas que necesita el contexto observable para juzgar la serie. |
| `pivot_params.k` | 3 | El de `pivots-v1`, el mismo que usa la tendencia. |
| `mast_max_candles` | 12 | Solo banderas y banderines: el mástil abarca, de su inicio a su final, como mucho estas velas. Un mástil es brusco y corto. |
| `mast_min_height_fraction` | 0,25 | Solo banderas y banderines: el mástil mide al menos esta fracción del rango reciente (las `range_window_candles` velas que terminan en su inicio). Un mástil destaca. |
| `max_retrace` | 0,50 | Solo banderas y banderines: la pausa devuelve como mucho esta fracción del mástil. |
| `flag_max_height_fraction` | 0,50 | Solo banderas y banderines: la altura de la pausa es, como mucho, esta fracción del mástil. |
| `min_flag_candles` | 8 | Solo banderas y banderines: la pausa abarca, del final del mástil a su último contacto, al menos estas velas (cuatro contactos alternos necesitan unas ocho). |
| `max_flag_candles` | 30 | Solo banderas y banderines: y como mucho estas. Una pausa más larga no es una bandera. |
| `parallel_tolerance` | 0,20 | Solo banderas: las fronteras son casi paralelas si la altura de la pausa cambia, como mucho, esta fracción de sí misma. |
| `pennant_convergence_min` | 0,30 | Solo banderines: las fronteras convergen si la altura de la pausa acaba en como mucho `1 - esto` de la que tenía al empezar. Entre `parallel_tolerance` y este valor no es ni bandera ni banderín. |

Un conjunto de parámetros es **parte de la identidad** de cada figura: cambiar su versión da otra
instancia, no reescribe la anterior.

## 3. El canal: dos fronteras entre las que rebota el precio

Las cuatro figuras son la misma cosa vista con distinta inclinación: el precio rebota entre una
frontera **superior** y una **inferior**, cada una una recta que pasa por máximos (o mínimos) de swing.

- **Anclas:** una secuencia de swings consecutivos con al menos dos máximos y dos mínimos. Se llaman
  `UPPER_1`, `LOWER_1`, `UPPER_2`… en orden cronológico. **Antes del cuarto contacto no hay figura**:
  no existe el estado `FORMING`.
- **Rectas:** la superior pasa por el primer y el último máximo; la inferior, por el primer y el
  último mínimo. Se evalúan con `Decimal`, multiplicando antes de dividir y redondeadas a 12
  decimales (`line_through`).
- **Altura:** la distancia vertical entre las dos rectas en el instante del primer contacto. Es la
  vara de medir de toda tolerancia y margen, y no cambia una vez empezada la figura.
- **Contactos intermedios:** cada máximo (o mínimo) que no define la recta está a
  `contact_tolerance × altura` de ella, como mucho.
- **El precio queda dentro:** ningún **cierre** entre el primer y el último contacto está más allá
  de una recta. Un cierre más allá es una ruptura, y la figura deja de crecer allí.
- **Crecimiento:** desde los cuatro swings, se añade un swing cada vez mientras la figura siga siendo
  una figura de su clase en cada tamaño; el primer tamaño que falla termina el crecimiento y lo
  encontrado se queda como estaba. Crecer mueve las rectas (pasan por el primer y el último
  contacto), así que solo se permite mientras el precio no haya salido de las rectas anteriores:
  un nuevo contacto nunca puede hacer que una ruptura ya ocurrida parezca no haber ocurrido.
- **Una figura es una instancia:** los trozos de una figura que empezó antes no son otras figuras
  (se omite una figura que empieza dentro de otra, del mismo detector, y acaba en o antes que ella).
- **Ápice:** las rectas de una figura convergente se cortan. Pasado ese momento la «superior» queda
  por debajo de la «inferior» y una ruptura no significa nada. Una ruptura solo puede empezar en las
  velas que cierran antes del ápice; si no la hay y ya han cerrado velas más allá, la figura ha
  cumplido su ciclo (`TOO_LONG`). Una ruptura empezada antes se sigue hasta su final.
- **Tendencia previa (`PRIOR_TREND`):** la del clasificador del punto 2 en el instante del primer
  contacto. Es solo contexto (`state`): si la figura continúa o revierte esa tendencia lo dice hacia
  dónde rompa, no este detector.

## 4. Estados y ruptura

Las reglas sobre cierres, margen, ventana de fracaso y orden («gana lo que ocurrió primero») son las
del documento de reversión, con estas diferencias:

- **Se vigilan las dos fronteras.** El primer cierre más allá de cualquiera de ellas es la ruptura
  y decide la dirección (`CONFIRMED_UP` por la superior, `CONFIRMED_DOWN` por la inferior). La
  ruptura que fracasó no se deshace por lo que pase después: `FAILED_BREAKOUT` es final.
- **Banderas y banderines vigilan las dos fronteras igual**, con la dirección del mástil como expectativa tradicional: ver la sección 7.
- **No hay «extremo que no se debe superar»**: el precio puede salir por cualquier lado, así que no
  existe la invalidación `CLOSED_THROUGH_AGAINST_BIAS`. Las únicas invalidaciones son `TOO_LONG` (por
  edad o por ápice) y las de instancias entre instantes (`GEOMETRY_BROKEN`, `SUPERSEDED`).
- **Sesgo tradicional frente a dirección observada.** El catálogo dice hacia dónde espera la
  tradición que resuelva (alcista para el ascendente, bajista para el descendente,
  `BREAKOUT_DEPENDENT` para el simétrico y el rectángulo). El detector no lo usa para nada: registra
  la dirección real de la ruptura.

## 5. Evidencia que registran

| Código | Cuándo | Qué contiene |
| ------ | ------ | ------------ |
| `CHANNEL` | siempre | Altura, separación de las rectas al final, cuánto se mueve cada una (`upper_rise`, `lower_rise`), contactos de cada lado, velas del canal, rango de referencia y las tolerancias usadas. |
| `PRIOR_TREND` | siempre | `state`: la tendencia previa. En triángulos y rectángulo, solo contexto. En banderas y banderines, además `required` (la tendencia que el mástil continúa) y `compatible`, medidas en el instante del inicio del mástil. |
| `FLAGPOLE` | banderas y banderines | Dirección del mástil (`mast_direction`), su altura, sus velas, su proporción respecto al rango de referencia, cuánto devolvió la pausa (`retracement_share`), lo alta que es (`flag_height_share`), cuánto deriva contra el mástil (`drift_share`) y sus velas. |
| `FLAG_VOLUME` | banderas y banderines | Volumen medio del mástil y de la pausa, y su cociente (`pause_to_mast`, ausente si el del mástil es cero). Solo informativo. |
| `BREAKOUT_SCAN` | desde el primer cierre más allá | Velas desde ese cierre, si está resuelta y cuánto tardó. |
| `RETEST` | ruptura **confirmada** y una vela posterior que vuelve a la recta rota (basta la mecha) | `candles_after_confirmation` y `held` (si esa vela cerró aún más allá). Es un hecho nuevo, por tanto una evaluación nueva en el historial. No confirma ni desconfirma nada. |
| `BREAKOUT_VOLUME` | desde el primer cierre más allá | Volumen de esa vela, media de las velas que la figura tardó en formarse y su cociente (`ratio`, ausente si la media es cero). Solo informativo. |

## 6. Cada figura

Los cuatro detectores son unidades independientes con su propia versión; solo comparten el ajuste del
canal y la fontanería. Una figura de pendientes intermedias (ni planas ni inclinadas) no es ninguna.

| Detector | Versión | Frontera superior | Frontera inferior |
| -------- | ------- | ----------------- | ----------------- |
| `RECTANGLE` | `rectangle-detector-v1` | plana | plana |
| `ASCENDING_TRIANGLE` | `ascending-triangle-detector-v1` | plana | sube |
| `DESCENDING_TRIANGLE` | `descending-triangle-detector-v1` | baja | plana |
| `SYMMETRICAL_TRIANGLE` | `symmetrical-triangle-detector-v1` | baja | sube |

«Plana», «sube» y «baja» se miden **sobre el movimiento de la recta del primer al último contacto**,
como fracción de la altura (`flat_tolerance` y `slope_min`). Una cuña (ambas fronteras inclinadas
en el mismo sentido) y una formación expansiva (fronteras que divergen) no son ninguna de las cuatro:
pertenecen a POINT3-EXPANSION-001.

## 7. Banderas y banderines

Una **bandera** o un **banderín** es un **mástil** (un movimiento brusco y corto) seguido de una
pausa breve entre dos fronteras. Plantean una **hipótesis de continuación** en la dirección del
mástil: alcista (mástil hacia arriba) o bajista (hacia abajo); la figura por sí sola no demuestra que
esa continuación ocurra. Cada una de las cuatro (`BULL_FLAG`, `BEAR_FLAG`, `BULL_PENNANT`,
`BEAR_PENNANT`) es un detector con su propia versión (`bull-flag-detector-v1`…); las alcistas y las
bajistas son espejo, y la bandera y el banderín solo se diferencian en la forma de la pausa.

- **Anclas:** el inicio del mástil (`MAST_START`), su final (`MAST_END`, que es a la vez el primer
  contacto de una frontera) y al menos tres contactos más de la pausa, numerados por frontera después
  de él (`LOWER_1`, `UPPER_2`, `LOWER_2`… en la alcista). Cinco anclas como mínimo; el inicio del
  mástil es el primer ancla y da la identidad de la instancia. **Antes del cuarto contacto de la
  pausa no hay figura.**
- **La pausa** es el mismo canal de dos rectas de los triángulos (sección 3), que empieza en el final
  del mástil y crece igual, con estas diferencias: su tamaño mínimo no se compara con el rango
  reciente (lo que tiene que destacar es el mástil) y su duración se mide con `min_flag_candles` y
  `max_flag_candles`; un canal más largo deja de ser una pausa y el crecimiento se detiene.
- **Mástil:** de un mínimo de swing a un máximo de swing (al revés en la bajista), de como mucho
  `mast_max_candles` velas, y de una altura de al menos `mast_min_height_fraction` del rango reciente.
- **La pausa es pequeña y devuelve poco:** su altura, medida en el final del mástil, es como mucho
  `flag_max_height_fraction` del mástil; el contacto que más se aleja del final del mástil, en contra,
  no supera `max_retrace` del mástil; y su deriva (el movimiento medio de las dos rectas) no va a
  favor del mástil más de `flat_tolerance` de él (casi plana). Una pausa que sigue subiendo tras un
  mástil alcista no es una pausa. Cuánto puede ir en contra lo limita ya `max_retrace`, por los contactos.
- **Bandera o banderín:** en la **bandera** las fronteras son casi paralelas (la altura de la pausa al
  acabar difiere de la inicial, como mucho, `parallel_tolerance` de sí misma); en el **banderín**
  convergen (la altura acaba en como mucho `1 - pennant_convergence_min` de la inicial) **desde los dos
  lados: la superior baja y la inferior sube**. Dos fronteras que se estrechan pero se inclinan en el
  mismo sentido son una cuña (POINT3-EXPANSION-001), no un banderín. Entre ambos umbrales no es
  ninguna de las dos. Los umbrales están separados por construcción: los parámetros que los
  solaparían se rechazan.
- **Las dos fronteras se vigilan** y la ruptura es el primer cierre más allá de cualquiera de ellas,
  con el mismo margen, ventana de fracaso y reglas de la sección 4. Que rompa hacia donde apunta el
  mástil es lo que la tradición espera; que rompa **hacia el otro lado** es una ruptura contraria a esa
  expectativa, que se **registra con su dirección real** (`CONFIRMED_DOWN` para un banderín alcista
  que rompe por abajo, por ejemplo) y no se fuerza a continuación. La dirección del mástil queda en
  la evidencia (`mast_direction` de `FLAGPOLE`), de modo que quien use la figura ve si la ruptura fue
  con el mástil o contra él. Lo que ocurre primero gana; el retorno al interior es un hecho aparte
  (`FAILED_BREAKOUT`, `RETEST`).
- **Ápice:** en el banderín rige lo mismo que en los triángulos convergentes (sección 3).
- **Tendencia previa:** la del clasificador del punto 2 en el instante del **inicio del mástil**.
  Se registra con `required` (alcista para el mástil alcista) y `compatible`: un mástil que sale de la
  tendencia contraria (una recuperación brusca dentro de una tendencia bajista) se observa igualmente,
  con eso anotado; quien use la figura decide.
- **Volumen (informativo, sin condición):** la descripción clásica espera actividad alta durante
  el mástil, menor en la pausa y mayor al romper. Se guardan las tres observaciones: `FLAG_VOLUME`
  (media del mástil, media de la pausa y su cociente) y `BREAKOUT_VOLUME`, que compara la vela que
  rompe con la media de la **pausa** (desde el final del mástil), no del mástil, que suele ser más
  ruidoso. Ninguna condiciona nada.
- **La altura es la de la pausa**, no la del mástil: el margen de confirmación es `breakout_margin`
  de la altura de la pausa. El objetivo proyectado con el mástil queda para la política de objetivos.

## 8. Límites conocidos

- Con solo dos contactos por frontera, una figura de bordes difusos puede leerse como más de una
  clase a la vez (por ejemplo, ascendente y rectángulo): son figuras distintas con su propia
  identidad y coexisten, como en el documento de reversión. Quien las use (POINT3-HYPOTHESIS-001)
  decide cuál pesa más.
- Un canal con mucho ruido, o cuyo comienzo no coincide con ningún swing confirmado, no se detecta.
  Es un umbral provisional que se validará con datos reales.
- El **ápice** se calcula con las rectas del último tamaño de la figura; si luego la figura crece, el
  ápice cambia con ella.
- **Pendiente: el estado candidato.** No hay estado `FORMING` para estas figuras: nada se afirma
  antes del cuarto contacto de la pausa. Una **candidata** (mástil ya identificado, pausa aún sin
  medir) sería útil para anticipar, pero exige decidir qué se registra cuando la pausa no se puede
  medir todavía y cómo se evita que una candidata que no llega a figura ensucie el historial. Queda
  como tarea aparte (propuesta: `POINT3-CANDIDATE-001`) y hoy no se afirma nada que no se pueda medir.
- Una pausa de más de `max_flag_candles` velas no se detecta como bandera (es otra cosa, o una
  pausa demasiado larga para serlo), y un mástil de más de `mast_max_candles` velas (una subida por
  etapas) tampoco. Son umbrales provisionales que se validarán con datos reales.

## 9. Lo que este documento no decide

Cuñas y formaciones expansivas (POINT3-EXPANSION-001),
cómo se integran varias figuras como evidencia de una hipótesis (POINT3-HYPOTHESIS-001), objetivos
de precio, entradas, vencimientos, señales y órdenes, y la persistencia de las instancias.

## 10. Decisiones técnicas tomadas al redactar

Registradas para poder corregirlas; ninguna es de producto.

1. Las rectas pasan por el **primer y el último** contacto y los intermedios se toleran, en lugar de
   un ajuste por mínimos cuadrados: es exacto, reproducible y no arrastra un contacto anómalo.
2. La ruptura se lee sobre **cierres estrictos**, con la misma definición dentro del canal (para
   decidir que el precio «sigue dentro») y fuera (para decidir que «rompió»), de modo que no hay
   cierres en tierra de nadie.
3. Crecer una figura nunca reescribe lo ya ocurrido (ver sección 3).
4. `RETEST` y `BREAKOUT_VOLUME` se añaden a la fontanería común, no a cada detector, para que valgan
   igual para todas las figuras.
5. Todos los valores de la sección 2 son provisionales y están en PARAMS-VALIDATION-001.
6. En las banderas se mide la pausa contra el mástil y no contra el rango reciente, y se mira el
   mástil contra el rango reciente: cada cosa se compara con lo que la hace destacar.
7. Las banderas y los banderines no incluyen `FORMING`, igual que el resto de la familia, aunque el
   mástil ya se conozca antes: nada se afirma hasta que la pausa se puede medir.

## 11. Ejemplos: lo que pasa y lo que falla

Cada línea es una prueba (`backend/tests/unit/test_pattern_continuation_thresholds.py`): el valor
**exacto** del umbral, y un vecino a cada lado. Un umbral «inclusivo» acepta el valor exacto; uno
«exclusivo», no. Todos los de esta tabla son inclusivos salvo donde se dice.

### 11.1 Mástil brusco y corto

| Regla | Parámetro | Pasa | Falla |
| ----- | --------- | ---- | ----- |
| Corto: como mucho 12 velas de inicio a final | `mast_max_candles` = 12 | 11 velas; **12 velas** (exacto) | 13 velas |
| Brusco: al menos 1/4 del rango de las últimas 100 velas | `mast_min_height_fraction` = 0,25 | rango 28,0: mástil de 7,1; **de 7,0** (exacto, 0,25) | mástil de 6,9 |

Ejemplo de mástil que **pasa** (alcista, diez velas, de un mínimo de 121,5 a un máximo de 150,5:
altura 29,0, más que el rango de 26,9 de las 100 velas anteriores): los valores medios de las velas, desde la del mínimo,
son 122; 124,8; 127,6; 130,4; 133,2; 136,0; 138,8; 141,6; 144,4; 147,2; 150,0. Con el mismo recorrido
repartido en **13 velas** (un paso de 2,15 en lugar de 2,8) no pasa: es demasiado lento para ser un
mástil. Y con la subida de 7,0 en 10 velas (mínimo 169,5 a máximo 176,5, rango 28,0) pasa justo;
con 6,9, no.

### 11.2 Pausa pequeña

Medidas de una pausa tras un mástil de **100** (para la bandera bajista, las mismas medidas
del revés):

| Regla | Parámetro | Pasa | Falla |
| ----- | --------- | ---- | ----- |
| Poco alta: como mucho la mitad del mástil | `flag_max_height_fraction` = 0,50 | 49,99; **50** (exacto) | 50,01 |
| Devuelve poco: el contacto que más se aleja del final del mástil, en contra, no pasa de la mitad | `max_retrace` = 0,50 | 49,99; **50** (exacto) | 50,01 |
| No sigue con el mástil: su deriva a favor es como mucho una décima | `flat_tolerance` = 0,10 | −30 (en contra); 9,99; **10** (exacto) | 10,01 |
| Breve: como mucho 30 velas, del final del mástil a su último contacto | `max_flag_candles` = 30 | 29; **30** (exacto) | 31 |
| Bandera, paralela: la altura al final difiere de la inicial (20) como mucho una quinta parte | `parallel_tolerance` = 0,20 | 16 y 24 (exactos); entre ellos | 15,99 y 24,01 |
| Banderín, convergente: la altura al final es como mucho 0,70 de la inicial (20) | `pennant_convergence_min` = 0,30 | 13,99; **14** (exacto) | 14,01 |
| Banderín: el techo baja y el suelo sube | (sin parámetro: signos estrictos) | techo −0,01 y suelo +0,01 | techo 0 (plano) o suelo 0 (plano); los dos subiendo o los dos bajando (cuña) |

Ejemplo de pausa que **pasa** (bandera alcista sobre el mástil de 29,0): contactos de la pausa a 150,5
(final del mástil), 145,5, 149,0 y 144,5, en 30 velas; techo de 150,5 a 149,0 y suelo de 145,5 a 144,5,
casi paralelos; 4,5 de alto (0,155 del mástil), devuelve 6,0 (0,207) y deriva −1,5 (−0,052). Ejemplos
que **fallan**, con esa misma pausa: bajo `flag_max_height_fraction` = 0,15 (su altura es 0,155 del
mástil; con 0,16 pasa); bajo `max_retrace` = 0,20 (devuelve 0,207; con 0,30 pasa); o con un techo que
sube tan deprisa como el mástil (123, 126, 129 en las pruebas), que ya no es una pausa.

### 11.3 Otro par de umbrales exactos

- `contact_tolerance` = 0,15: un contacto intermedio a medio punto de la recta, con una altura de 20,
  está a 0,025 de la altura. Con la tolerancia en 0,025 **es** contacto (inclusivo); con 0,0249, no.
- Un banderín cuya altura pasa de 10,5 a 7,35 (0,70 exacto) con `pennant_convergence_min` = 0,30 **es**
  banderín; con 0,31, no.

## 12. Tipo de figura, dirección del mástil y dirección real de la ruptura

Son **tres hechos distintos**, guardados en sitios distintos, y ninguno se deduce de otro:

| Qué | Dónde se guarda | Ejemplo: banderín alcista que rompe por abajo |
| --- | --------------- | ---------------------------------------------- |
| **Qué figura es** (y qué espera la tradición de ella) | `pattern_type` de la instancia y su `traditional_bias` en el catálogo | `BULL_PENNANT`, sesgo `BULLISH` |
| **Hacia dónde apuntó el mástil** | ancla `MAST_START` (un mínimo si el mástil sube) y `mast_direction` en la evidencia `FLAGPOLE` | `UP` |
| **Hacia dónde rompió de verdad el precio** | `breakout.direction` y `breakout.boundary` de la evaluación, y el estado (`CONFIRMED_UP` o `CONFIRMED_DOWN`) | `DOWN` por la frontera `LOWER`, estado `CONFIRMED_DOWN` |

De ahí que una ruptura contraria a la expectativa se **registre tal cual**, sin renombrar la figura ni
forzarla a continuación: quien consuma el resultado ve `BULL_PENNANT` con un mástil hacia arriba y una
ruptura `DOWN`, y puede tratarla como lo que es (una ruptura contraria al mástil). Lo mismo vale para
triángulos y rectángulo, cuyo sesgo tradicional también es distinto de la ruptura que ocurre.
