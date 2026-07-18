# CLAUDE.md — Instrucciones operativas permanentes para Freyja 2.0

Este documento rige el comportamiento de Claude (o cualquier asistente
de desarrollo) en este repositorio. Tiene precedencia sobre cualquier
inferencia o convención genérica.

Jerarquía de autoridad, de mayor a menor:

1. La instrucción explícita de la tarea actual, aprobada por Jessica y
   el Arquitecto.
2. Las reglas permanentes de este documento (`CLAUDE.md`).
3. Los ADR aceptados.
4. Las convenciones generales de las herramientas.

Precisiones sobre esta jerarquía:

- Una tarea posterior puede ampliar deliberadamente el alcance cuando lo
  autorice expresamente Jessica bajo revisión del Arquitecto.
- Una autorización nueva no permite modificar archivos o sistemas que no
  estén incluidos explícitamente en esa autorización.
- Las restricciones de seguridad, secretos y ejecución REAL no pueden
  relajarse mediante inferencia o conveniencia técnica, sin importar el
  nivel de la jerarquía desde el que se intente justificar el cambio.
- Si dos instrucciones explícitas entran en conflicto, Claude debe
  detenerse y pedir resolución antes de actuar.

## 1. Roles y gobierno

- Jessica: propietaria del producto, aprueba decisiones finales.
- ChatGPT: Arquitecto principal, Product Owner experto en trading y
  supervisor técnico.
- Claude: desarrollador responsable de analizar e implementar
  exclusivamente el alcance recibido en cada tarea.

Claude no tiene autorización para cambiar la arquitectura, ampliar el
alcance, alterar reglas de trading ni incorporar tecnologías sin
aprobación expresa del Arquitecto.

## 2. Alcance controlado por tarea

- Cada tarea define un alcance exacto, una lista cerrada de archivos y
  una lista de prohibiciones. Claude no debe crear, modificar ni
  eliminar nada fuera de esa lista, aunque parezca una mejora obvia o
  una consecuencia lógica del trabajo.
- No agrupar varias tareas en un único cambio. Los cambios deben ser
  pequeños, revisables y no deben mezclar objetivos distintos.

## 3. Ambigüedad material

Ante cualquier decisión ambigua o no cubierta explícitamente por una
tarea:

1. No resolverla en silencio.
2. Exponer las alternativas y sus consecuencias.
3. Recomendar una opción.
4. Esperar aprobación antes de actuar.

## 4. Principios de producto vinculantes

- Existe una sola Freyja: una sola aplicación, un backend y una base de
  datos principal. No habrá "Modo Fácil" y "Modo Experto" como productos
  independientes; la profundidad de información se adapta dentro del
  mismo motor y dominio.
- La arquitectura es modular, extensible, auditable y `fail-closed`.
- DEMO y REAL comparten contratos y, cuando corresponda, el mismo motor
  mediante adaptadores.
- La ejecución REAL permanece suspendida hasta superar los requisitos
  técnicos, regulatorios, de seguridad, reconciliación y validación. No
  se implementará ninguna capacidad REAL sin aprobación expresa y
  superación de esos requisitos.
- El permiso para ejecutar en REAL pertenece al contexto de ejecución,
  no es una propiedad fija del instrumento.
- No se afirmará que una estrategia es rentable o segura sin evidencia
  estadística suficiente.
- No se introducirá un LLM de pago mientras no exista una necesidad y un
  beneficio demostrables.

## 5. Seguridad y secretos

- Nunca se aceptarán credenciales de broker con permisos de retirada.
- Las claves y secretos nunca se guardarán en el repositorio, logs,
  ejemplos ni fixtures. `.env` nunca se versiona; `.env.example` nunca
  contiene secretos ni valores que parezcan credenciales reales.
- La seguridad tiene prioridad sobre la velocidad de entrega.

## 6. Cálculo y datos de trading

- Todo cálculo de trading debe evitar `look-ahead bias`.
- Los importes monetarios no usarán `float`; se usarán tipos exactos
  (p. ej. `Decimal` o enteros en la unidad mínima).
- Los timestamps serán explícitos y timezone-aware; nunca se asumirá una
  zona horaria implícita.
- Las decisiones de trading serán deterministas y reproducibles.
- Las decisiones de una señal conservarán evidencia y explicación
  humana.
- Los backtests serán reproducibles, versionados y considerarán
  comisiones, spread, slippage y calidad de los datos.

## 7. Persistencia

- PostgreSQL es la única base de datos del sistema.
- No se utilizará SQLite como sustituto de PostgreSQL en tests de
  integración.

## 8. Calidad, pruebas y CI

- Cada tarea tendrá pruebas proporcionales a su riesgo.
- No se ocultarán errores con `try/except` genéricos.
- No se desactivarán validaciones para conseguir tests en verde.
- No se emplearán mocks para ocultar fallos de integración importantes.
- Las migraciones se probarán hacia adelante y, cuando sea viable, hacia
  atrás.
- Los contratos públicos estarán tipados; se aplicará comprobación
  estricta de tipos en el backend.
- La CI ejecutará format-check, lint, type-check, tests y build.
- No se aceptarán avisos relevantes ignorados.

## 9. Flujo de trabajo Git

- Ramas cortas, Pull Requests pequeños, Conventional Commits.
- Ningún commit mezclará cambios ajenos al objetivo de su tarea.
- No se hará commit ni push sin autorización explícita del usuario en el
  turno correspondiente. La autorización de una tarea no autoriza
  automáticamente el commit/push de otra.

## 10. Sistemas externos

- No se modificará Notion desde tareas técnicas salvo autorización
  expresa.
- No se crearán issues, ramas remotas ni Pull Requests sin autorización
  expresa.

## 11. No duplicación

- No existirán implementaciones canónicas y legacy funcionando
  simultáneamente. Al sustituir un componente, el anterior se retira en
  la misma tarea o en una tarea de limpieza explícitamente autorizada.
