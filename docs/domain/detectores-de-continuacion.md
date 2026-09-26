# Detectores de figuras de continuación y consolidación (v1)

- **Estado:** vigente para triángulos y rectángulo. Banderas y banderines llegan en la segunda parte
  de la tarea y se añadirán a este mismo documento.
- **Fecha:** 2026-09-26
- **Tarea:** POINT3-CONTINUATION-001 (4 de 7 del punto 3), parte 1 de 2.
- **Depende de:** [figuras-chartistas.md](figuras-chartistas.md) (qué es cada figura),
  [instancia-de-figura.md](instancia-de-figura.md) (cómo se representa),
  [detectores-de-reversion.md](detectores-de-reversion.md) (la fontanería común: qué es un
  detector, cómo se juzga una ruptura, cómo pasan las instancias de un instante al siguiente) y
  [estructura-de-precio.md](estructura-de-precio.md) (pivotes confirmados).
- **Código:** `backend/src/freyja_backend/domain/pattern_channel.py` (los cuatro detectores) y, en
  `pattern_detection.py`, lo compartido (`ContinuationParams`, `judge`, evidencias de reprueba y de
  volumen). Dominio puro, sin E/S. Pruebas en `backend/tests/unit/test_pattern_channel.py`.

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
| `PRIOR_TREND` | siempre | `state`: la tendencia previa. Solo contexto. |
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

## 7. Límites conocidos

- Con solo dos contactos por frontera, una figura de bordes difusos puede leerse como más de una
  clase a la vez (por ejemplo, ascendente y rectángulo): son figuras distintas con su propia
  identidad y coexisten, como en el documento de reversión. Quien las use (POINT3-HYPOTHESIS-001)
  decide cuál pesa más.
- Un canal con mucho ruido, o cuyo comienzo no coincide con ningún swing confirmado, no se detecta.
  Es un umbral provisional que se validará con datos reales.
- El **ápice** se calcula con las rectas del último tamaño de la figura; si luego la figura crece, el
  ápice cambia con ella.
- No hay estado `FORMING` para estas figuras: nada se afirma antes del cuarto contacto.

## 8. Lo que este documento no decide

Banderas y banderines (parte 2 de esta tarea), cuñas y formaciones expansivas (POINT3-EXPANSION-001),
cómo se integran varias figuras como evidencia de una hipótesis (POINT3-HYPOTHESIS-001), objetivos
de precio, entradas, vencimientos, señales y órdenes, y la persistencia de las instancias.

## 9. Decisiones técnicas tomadas al redactar

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
