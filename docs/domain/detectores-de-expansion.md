# Detectores de cuñas y formaciones expansivas (v1)

- **Estado:** en construcción por partes. Vigente hoy: la parte a (cuña ascendente y cuña
  descendente). Pendientes, cada una en su propio cambio: la formación expansiva (b) y el diamante (c).
- **Fecha:** 2026-09-26
- **Tarea:** POINT3-EXPANSION-001 (5 de 7 del punto 3), parte a.
- **Depende de:** [detectores-de-continuacion.md](detectores-de-continuacion.md) (el canal de dos
  rectas y todo lo que comparte la familia: ruptura por cierre, evidencia de reprueba y de volumen,
  ápice), [detectores-de-reversion.md](detectores-de-reversion.md) (la fontanería común),
  [figuras-chartistas.md](figuras-chartistas.md) e [instancia-de-figura.md](instancia-de-figura.md).
- **Código:** `backend/src/freyja_backend/domain/pattern_wedge.py` y el canal de
  `pattern_channel.py`. Dominio puro, sin E/S. Pruebas en
  `backend/tests/unit/test_pattern_wedge.py`.

Lo dicho en los documentos anteriores sobre **qué hace y qué no hace un detector** vale aquí sin
cambios: función pura de lo que se sabía en un instante, sin patrones de velas ni indicadores, sin
señal, lado, objetivo, vencimiento ni confianza, y con datos no aptos no juzga nada.

## 1. Decisiones de producto aprobadas

Las cuñas se modelan **por su geometría**, con sesgo tradicional descriptivo; su papel de
continuación o de reversión depende de la tendencia previa y de hacia dónde rompan (Jessica,
2026-09-26, al aprobar POINT3-CONTINUATION-001). Nada de esto es una decisión nueva.

## 2. Parámetro nuevo (`continuation-params-v1`)

Las cuñas usan los parámetros de las figuras de dos fronteras (`slope_min`, `contact_tolerance`,
`breakout_margin`, etc., ver el documento de continuación) y añaden uno. **Provisional y sin
validar**; está en PARAMS-VALIDATION-001. Como todo lo de la familia, relativo a la altura de la figura.

| Parámetro | Valor | Significado |
| --------- | ----- | ----------- |
| `wedge_convergence_min` | 0,30 | Solo cuñas: las fronteras convergen si la separación entre ellas al último contacto es, como mucho, `1 - esto` de la altura inicial. |

No cambia la versión `continuation-params-v1`: nada se ha persistido todavía con ella. Debe cumplirse
`parallel_tolerance < wedge_convergence_min`, para que unas fronteras no sean a la vez paralelas y
convergentes; un valor incoherente se rechaza al construir los parámetros.

## 3. La cuña

Una cuña es el **mismo canal** de los triángulos y el rectángulo, con dos condiciones sobre las
pendientes de sus fronteras (medidas, como siempre, sobre lo que se mueve cada recta del primer al
último contacto, en fracción de la altura):

- **Las dos fronteras se inclinan en el mismo sentido**, al menos `slope_min` cada una: las dos suben
  (cuña ascendente, `RISING_WEDGE`) o las dos bajan (cuña descendente, `FALLING_WEDGE`).
- **Convergen**: la separación al último contacto es, como mucho, `1 - wedge_convergence_min` de la
  altura inicial. Es inclusivo: exactamente eso basta.

| Detector | Versión | Frontera superior | Frontera inferior | Sesgo tradicional |
| -------- | ------- | ----------------- | ----------------- | ----------------- |
| `RISING_WEDGE` | `rising-wedge-detector-v1` | sube | sube más deprisa | bajista |
| `FALLING_WEDGE` | `falling-wedge-detector-v1` | baja más deprisa | baja | alcista |

Con eso, las cuñas quedan separadas del resto de la familia por la geometría y nada más:

- un **triángulo** tiene una frontera plana o fronteras que se inclinan en sentidos opuestos;
- un **rectángulo** no tiene ninguna inclinada;
- un **canal paralelo** inclinado no converge (es una bandera si sigue a un mástil, y si no, nada);
- una inclinación intermedia, entre `flat_tolerance` y `slope_min`, no es ninguna figura de la familia.

## 4. Estados, ruptura y sesgo

Todo lo de la sección 4 del documento de continuación vale sin cambios: cuatro contactos antes de
que exista la figura (no hay `FORMING`), se vigilan **las dos fronteras**, el primer cierre más allá
de cualquiera de ellas es la ruptura y da la dirección (`CONFIRMED_UP` por la superior,
`CONFIRMED_DOWN` por la inferior), la ruptura que fracasó no se deshace, y no existe la invalidación
por cerrar contra el sesgo.

**El sesgo tradicional no interviene.** La cuña ascendente es «bajista» y la descendente «alcista»
según la tradición, pero eso es un dato del tipo de figura, no una regla del detector: si una cuña
ascendente rompe al alza, se registra `CONFIRMED_UP` por la frontera superior, tal cual ocurrió.
Que la cuña sea aquí una continuación o una reversión no lo decide el detector: se conserva la
tendencia previa como contexto (`PRIOR_TREND`, solo `state`) y la ruptura dice lo demás.

Las cuñas convergen, así que tienen **ápice**: pasado el punto en que las rectas se cortan no puede
empezar una ruptura, y una cuña sin resolver antes de él caduca (`TOO_LONG`), como los triángulos.

## 5. Evidencia

La misma que la familia (sección 5 del documento de continuación): `CHANNEL` (con `upper_rise`,
`lower_rise`, altura y separación al final), `PRIOR_TREND`, `BREAKOUT_SCAN`, `RETEST` y
`BREAKOUT_VOLUME`. Ninguna es un requisito.

## 6. Límites conocidos

- Los umbrales son provisionales y se validarán con datos reales (PARAMS-VALIDATION-001).
- Con solo dos contactos por frontera, unas fronteras de pendientes casi iguales pueden quedar
  justo a un lado o a otro de `wedge_convergence_min`; por eso el umbral se prueba exactamente en su
  valor y a ambos lados.
- Si el precio sale de las rectas antes de completar el cuarto contacto no hay figura, como en el
  resto de la familia.

## 7. Lo que este documento no decide

La formación expansiva y el diamante (partes b y c de POINT3-EXPANSION-001), cómo se integran varias
figuras como evidencia de una hipótesis (POINT3-HYPOTHESIS-001), objetivos, entradas, vencimientos,
señales y órdenes, y la persistencia de las instancias.

## 8. Ejemplos: lo que pasa y lo que falla

Una figura de altura 20 entre sus dos rectas al primer contacto:

| Regla | Parámetro | Pasa | Falla |
| ----- | --------- | ---- | ----- |
| Convergen: separación al final como mucho 0,70 de la altura (14) | `wedge_convergence_min` = 0,30 | 13,99 y **14** (exacto) | 14,01 y 20 |
| Cada frontera sube al menos 0,15 de la altura (3) | `slope_min` = 0,15 | **3** (exacto) | 2,99 |
| Las dos en el mismo sentido | — | ambas suben (o ambas bajan) | una sube y otra baja (triángulo simétrico); una plana (triángulo) |

Una serie que sube hasta 130, retrocede hasta 116 y rebota entre máximos en 132, 134 y 135 y
mínimos en 121 y 126 es una cuña ascendente: las dos fronteras suben (3 y 10 en la altura de 14,5) y
la separación acaba en 7,5. Si el precio cierra por debajo de la inferior, `CONFIRMED_DOWN`; si cierra
por encima de la superior, `CONFIRMED_UP`. La serie con las mismas ideas al revés es la cuña
descendente.
