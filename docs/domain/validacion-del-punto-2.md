# Validación del punto 2: contexto, tendencia, política e instantánea

- **Estado:** vigente. Cierra el punto 2.
- **Fecha:** 2026-09-25
- **Tarea:** POINT2-TEST-001 (7 de 7 del punto 2).
- **Depende de:** POINT2-SNAPSHOT-001.
- **Tests:** `backend/tests/unit/test_point2_validation.py` (la tubería completa y la matriz de
  trazabilidad) más los tests propios de cada pieza.

El objetivo es demostrar, con datos temporales controlados, que Freyja clasifica **únicamente con
la información disponible en cada instante**, y que nada de esto sale del proceso.

## 1. Qué prueba esta tarea que no probaba ninguna pieza por separado

- **Tubería completa sin _look-ahead_.** En tres series aleatorias con semilla y en cada tercer
  instante de cada una, desde las velas hasta la instantánea con dos políticas distintas: la
  instantánea hecha con la serie entera (futuro incluido) es **idéntica** a la hecha solo con las
  velas cerradas en ese momento, y no cambia aunque todo lo posterior se reescriba con valores
  extremos. El instante de cálculo se aparta a propósito del instante observado, para que un
  código que leyera el reloj de cálculo lo delatase.
- **Alcance real.** Los mismos recorridos alcanzan los cuatro estados clasificables, y con la
  ausencia de velas también `INSUFFICIENT_DATA`; y las políticas dan más de un resultado, así que
  la prueba no es vacía.
- **Cripto en fin de semana.** Sábado y domingo: mercado abierto, sesión ausente (no se presta la
  de Forex), sin versión de calendario, tendencia clasificada y política compatible.
- **Forex y los cambios de hora.** La sesión registrada en cada lado de los cambios de hora,
  incluidas las tres semanas de 2026 en que EE. UU. y el Reino Unido tienen la hora cambiada en
  fechas distintas (8 y 29 de marzo; 25 de octubre y 1 de noviembre). La semana abre y cierra una
  hora antes en verano que en invierno (22:00 UTC frente a 21:00 UTC), y un fin de semana con el
  mercado cerrado no hace que unos datos del viernes se den por desactualizados, ni en invierno ni
  en verano.
- **Nada externo se activa.** Cada módulo del punto 2 solo importa la biblioteca estándar y el
  dominio; en un intérprete limpio, cargarlos no arrastra red, correo, base de datos, servidor
  web, ni código de infraestructura, aplicación o API; la tubería completa se ejecuta con los
  _sockets_ bloqueados; y ningún nombre de cliente de bróker, ejecutor, envío de mensajes o
  _webhook_ aparece en ellos.
- **Trazabilidad.** Cada uno de los 14 requisitos obligatorios de la tarea nombra los tests que
  lo prueban, y un test comprueba que esos tests siguen existiendo: si alguien borra o renombra
  uno, falla.

## 2. Matriz de requisitos

| Requisito | Tests que lo prueban |
| --------- | -------------------- |
| UPTREND, DOWNTREND, RANGE, TRANSITION e INSUFFICIENT_DATA | `test_market_trend`: alcista, bajista, rango, transición y «pocos giros»; `test_every_state_the_pipeline_can_reach_is_reached_and_recorded` |
| Pivotes provisionales frente a confirmados | `test_market_structure`: provisional hasta la k-ésima vela, puede desaparecer, el confirmado no; snapshot: un giro provisional nunca es evidencia |
| Sin _look-ahead_ | estructura, tendencia y snapshot; **tubería completa** (`test_the_whole_pipeline_decides_only_with_what_was_available_at_each_instant`) |
| Vela abierta excluida | estructura, contexto y tendencia |
| Datos faltantes o atrasados | contexto (`stale`, huecos, sin datos), tendencia y snapshot |
| Marcos clasificados de forma independiente | tendencia: independientes, nunca leen las velas del otro, un contexto insuficiente no vuelve insuficiente la señal |
| Conflicto entre `signal_trend` y `context_trend` | política y snapshot |
| Las cinco relaciones | política: la matriz completa del contrato, celda a celda |
| Sesiones Forex, mercado cerrado y cambios de hora | calendario, contexto y **esta tarea** |
| Cripto en fin de semana sin sesión inventada | contexto y **esta tarea** |
| Snapshot inmutable y versionado | snapshot y persistencia (trigger de la base de datos) |
| Estrategia sin política falla cerrada | política y snapshot |
| Ningún bróker, ejecutor ni mensaje externo | **esta tarea** y `test_architecture_guards` |
| Fixtures y mocks solo en tests | `test_architecture_guards` |

La tabla completa, con el nombre exacto de cada test, es la constante `TRACEABILITY` del fichero de
validación.

## 3. Verificación final

- **Calidad:** `scripts/quality.py --backend` completo y CI en verde.
- **Migración y retroceso:** probados en POINT2-SNAPSHOT-001 (`0015_context_snapshots`: subida,
  bajada, negativa a borrar datos, trigger y equivalencia del script manual de Neon).
- **Mutaciones:** se rompieron a propósito ocho reglas de la tubería (vela abierta contada como
  cerrada, tendencia leyendo velas no cerradas, relojes de Londres y Nueva York ignorados,
  semana de Forex con desfase fijo de invierno, cierre semanal sin cambio de hora, sesión de Forex
  para cripto, instantánea que clasifica con el reloj de cálculo): este fichero las detecta todas
  por sí solo.
- **Despliegue:** los módulos del punto 2 son de dominio puro y ningún endpoint los usa todavía,
  así que el despliegue no cambia el comportamiento en producción.

## 4. Lo que esta validación no demuestra

- **No demuestra que `trend-v1` acierte.** Demuestra que se calcula con lo disponible, que es
  reproducible y que no se contradice. Sus parámetros siguen **sin validar** fuera de muestra
  (ver [`tendencia-estructural.md`](tendencia-estructural.md)); ninguna capa del punto 2 afirma
  ventaja estadística.
- Se hace con series sintéticas controladas, no con datos reales de un proveedor: las velas
  reales y el escáner ya se prueban aparte (ADR 0006).
- El punto 2 no genera señales, órdenes ni alertas, y no cambia `confidence` ni el motor de
  decisión: eso pertenece a puntos posteriores.
