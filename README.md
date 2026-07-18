# Freyja 2.0

## Misión

Freyja 2.0 es una plataforma de análisis y asistencia de trading dirigida
principalmente a personas sin conocimientos técnicos, capaz de ofrecer
información avanzada cuando el usuario la necesite. La experiencia adapta
la profundidad de la información mostrada, pero todos los usuarios
comparten el mismo dominio, el mismo motor y la misma base de código.

## Estado inicial del proyecto

Este repositorio se encuentra en **Fase 0 — Fundación técnica**. Todavía
no existe backend, frontend, base de datos ni ningún componente
ejecutable. Este README documenta la fundación aprobada; no describe
software en funcionamiento.

## Stack aprobado

- Backend: Python 3.12, FastAPI, SQLAlchemy 2.x, Alembic, gestionado con `uv`.
- Frontend: Angular 22.x, TypeScript, Node.js 24.x LTS.
- Persistencia: PostgreSQL 18.4 (única base de datos del sistema).
- Infraestructura local: Docker Compose v2 (`docker compose`).
- CI: GitHub Actions.
- Calidad: Ruff (Python), ESLint y Prettier (Angular/TypeScript).

Consulta el detalle completo y las justificaciones en
[`docs/adr/0001-stack-y-arquitectura-inicial.md`](docs/adr/0001-stack-y-arquitectura-inicial.md).

## Principios de seguridad

- La seguridad tiene prioridad sobre la velocidad de entrega.
- La arquitectura es modular, extensible, auditable y `fail-closed`.
- Nunca se aceptarán credenciales de broker con permisos de retirada.
- Las claves y secretos nunca se guardarán en el repositorio, logs,
  ejemplos ni fixtures.
- Todo cálculo de trading debe evitar `look-ahead bias`.
- Las decisiones de una señal deben conservar evidencia y explicación
  humana.

## Ejecución REAL

**La ejecución REAL permanece suspendida.** No se utilizará dinero real
durante las primeras fases del producto. El permiso para ejecutar en
REAL pertenece al contexto de ejecución y no será una propiedad fija del
instrumento.

## Estructura prevista del monorepo

```text
freyja_trading/
├── backend/
├── frontend/
├── docs/
├── infrastructure/
├── .github/
├── .env.example
├── .gitignore
├── docker-compose.yml
├── README.md
└── CLAUDE.md
```

A día de hoy, únicamente existen los archivos de gobernanza fundacional
(`.editorconfig`, `.gitignore`, `README.md`, `CLAUDE.md`,
`docs/adr/0001-stack-y-arquitectura-inicial.md`). El resto de la
estructura se creará en tareas posteriores, cada una revisada y aprobada
de forma individual.

## Repositorio

[https://github.com/jessicamartinezojedabarcelona/freyja_trading](https://github.com/jessicamartinezojedabarcelona/freyja_trading)

## Entorno ejecutable

Todavía no existe un entorno ejecutable. No hay backend, frontend ni
base de datos implementados, por lo que no existen comandos de
instalación o arranque en este momento. Dichos comandos se documentarán
en tareas futuras, una vez los componentes correspondientes existan.
