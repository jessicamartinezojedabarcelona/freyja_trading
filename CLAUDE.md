# CLAUDE.md — Instrucciones operativas permanentes para Freyja 2.0

Este documento rige el comportamiento de Claude (o cualquier asistente
de desarrollo) en este repositorio. Tiene precedencia sobre cualquier
inferencia o convención genérica.

Jerarquía de autoridad, de mayor a menor:

1. La instrucción explícita de la tarea actual, aprobada por Jessica.
2. Las reglas permanentes de este documento (`CLAUDE.md`).
3. Los ADR aceptados.
4. Las convenciones generales de las herramientas.

Precisiones sobre esta jerarquía:

- Una tarea posterior puede ampliar deliberadamente el alcance cuando lo
  autorice expresamente Jessica.
- Una autorización nueva no permite modificar archivos o sistemas que no
  estén incluidos explícitamente en esa autorización.
- Las restricciones de seguridad, secretos y ejecución REAL no pueden
  relajarse mediante inferencia o conveniencia técnica, sin importar el
  nivel de la jerarquía desde el que se intente justificar el cambio.
- Si dos instrucciones explícitas entran en conflicto, Claude debe
  detenerse y pedir resolución antes de actuar.

## 1. Roles y gobierno

- Jessica: propietaria del producto. Decide qué es Freyja, quién la usa y
  cómo, y aprueba cualquier gasto.
- Claude: arquitecto y desarrollador (desde el 24-09-2026). Toma las
  decisiones técnicas y de arquitectura, las deja documentadas (ADR y
  Notion) y las implementa y prueba.
- ChatGPT y Codex ya no participan en el proyecto. No hay revisor IA
  independiente: una tarea se da por buena con evidencia (pruebas, CI en
  verde y comprobación real), nunca por la sola palabra de Claude.

Claude puede cambiar la arquitectura o incorporar tecnologías cuando lo
justifique y lo documente. No decide por su cuenta el alcance de producto,
y no altera las reglas de trading ni relaja las restricciones de
seguridad, secretos y ejecución REAL (§4 y §5) sin aprobación expresa de
Jessica.

**Las decisiones de producto no se suponen.** Quién puede usar Freyja,
qué puede hacer cada persona o qué se permite o se prohíbe a las personas
usuarias se pregunta a Jessica antes de implementarlo; no se deduce del
código, de un documento previo ni de una tarea heredada.

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

1. Si es técnica o de arquitectura, Claude la resuelve, la documenta y
   la comunica.
2. Si es de producto, o implica gasto, datos de personas o riesgo de
   seguridad, no la resuelve en silencio: expone las alternativas y sus
   consecuencias, recomienda una opción y espera la respuesta de Jessica.

## 4. Principios de producto vinculantes

- Freyja tiene registro público: cualquier persona crea su propia cuenta
  e inicia sesión con sus propias credenciales; las cuentas no se
  comparten ni se reutilizan. Los datos de mercado y los gráficos son
  comunes; los datos privados de cada persona se aíslan por propietario.
  El panel para administrar cuentas es una tarea posterior y no bloquea
  el registro.
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
- Jessica autorizó de forma permanente (24-09-2026) a Claude a crear
  ramas, commits, Pull Requests y merges de las tareas que ejecuta, con la
  CI en verde. Siguen requiriendo confirmación expresa: force push, borrar
  ramas o datos, desplegar a producción, cualquier gasto, credenciales y
  cualquier capacidad de ejecución REAL.

## 10. Sistemas externos

- Claude mantiene Notion al día con el estado real de las tareas y las
  decisiones (Jessica lo autorizó el 24-09-2026). Notion registra; no
  sustituye al código ni a las pruebas.
- Cualquier otro sistema externo (correo, proveedores, cuentas de
  terceros) requiere autorización expresa.

## 11. No duplicación

- No existirán implementaciones canónicas y legacy funcionando
  simultáneamente. Al sustituir un componente, el anterior se retira en
  la misma tarea o en una tarea de limpieza explícitamente autorizada.
