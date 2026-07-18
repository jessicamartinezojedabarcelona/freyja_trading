# ADR 0001 — Stack y arquitectura inicial de Freyja 2.0

- **Estado:** Accepted
- **Fecha:** 2026-07-18

## Contexto

Freyja 2.0 se reconstruye desde cero como una única plataforma de
análisis y asistencia de trading, con un solo backend, un solo frontend
y una sola base de datos principal. El proyecto anterior fue eliminado
localmente y no se recupera ni se reutiliza. Antes de crear cualquier
scaffold de código era necesario fijar por escrito el stack técnico y
las decisiones arquitectónicas de base, para que las tareas posteriores
de la Fase 0 (Fundación técnica) tengan un marco de referencia estable y
auditable.

## Decisión

Se adopta el siguiente stack y las siguientes decisiones arquitectónicas
como fundación de Freyja 2.0. Ningún componente descrito aquí está
implementado todavía; este documento registra la decisión, no el
estado del código.

## Stack y versiones aprobadas

| Componente | Versión |
|---|---|
| Python | 3.12.10 |
| Gestor de dependencias Python | `uv` (`pyproject.toml` + `uv.lock`) |
| FastAPI | 0.139.2 |
| SQLAlchemy | última estable de la serie 2.0.x, bloqueada vía `uv.lock` |
| Alembic | 1.18.5 |
| PostgreSQL | 18.4 |
| Angular | 22.x (último patch estable disponible al ejecutar el scaffold) |
| Node.js | 24.x LTS (instalación actual 24.17.0 válida) |
| TypeScript | >=6.0.0 <6.1.0 (seleccionada por Angular 22) |
| Docker Compose | v2 integrado (`docker compose`) |

## Estructura prevista

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

Monorepo sencillo, sin herramientas de orquestación de monorepo (se
descartan explícitamente Nx, Turborepo u otras) mientras no exista una
necesidad demostrada.

## Arquitectura del backend

Backend como monolito modular, con separación conceptual en cuatro
capas:

- `domain`: reglas y modelos de negocio, sin dependencias de framework.
- `application`: casos de uso que orquestan el dominio.
- `infrastructure`: implementaciones concretas (persistencia, clientes
  externos, adaptadores).
- `api`: capa de entrada HTTP (FastAPI), versionada bajo `/api/v1`.

## Persistencia

PostgreSQL 18.4 es la única base de datos del sistema. No se introducirá
ninguna base de datos adicional sin aprobación expresa. No se utilizará
SQLite como sustituto de PostgreSQL en tests de integración: los tests
de integración deben ejercitar PostgreSQL real para evitar divergencias
entre el comportamiento de test y producción.

## Configuración

Configuración mediante variables de entorno, cargadas y validadas con
`pydantic-settings`. `.env` nunca se versiona; `.env.example` documenta
las claves necesarias sin contener secretos ni valores que parezcan
credenciales reales.

## Migraciones

Alembic mantiene una única cadena lineal de migraciones y un solo
`head`. No se permite bifurcar el historial de migraciones sin una
tarea explícita de resolución.

## Testing

Las pruebas serán proporcionales al riesgo de cada componente. Los
tests de integración se ejecutan contra PostgreSQL real (no SQLite, no
mocks que oculten fallos de integración). Las migraciones se prueban
hacia adelante y, cuando sea viable, hacia atrás.

## Calidad

- Python: Ruff para formato y lint; comprobación estricta de tipos en
  el backend.
- Angular/TypeScript: ESLint y Prettier.

## CI

GitHub Actions ejecutará, como mínimo: format-check, lint, type-check,
tests y build, para backend y frontend.

## Secretos

Los secretos nunca se guardan en el repositorio, logs, ejemplos ni
fixtures. `.env` está excluido de versionado; `.env.example` no contiene
valores reales ni verosímiles como credenciales.

## Observabilidad

Logging estructurado y `request_id` forman parte de la fundación
técnica del backend, para permitir trazabilidad desde las primeras
tareas de implementación.

## Flujo Git

Ramas cortas, Pull Requests pequeños, Conventional Commits. Ningún
commit mezcla cambios ajenos al objetivo de la tarea que lo origina. No
se realizan commits ni pushes sin autorización explícita del usuario en
el turno correspondiente.

## Capacidades expresamente excluidas de esta fase

- Autenticación de usuarios.
- Trading, señales o estrategias.
- Integración con brokers.
- Modos DEMO o REAL implementados.
- Cualquier base de datos operativa.
- Instalación de Docker, Angular CLI, `uv init`, o cualquier dependencia.
- Workflows de CI ejecutables.
- Código Python o TypeScript de aplicación.

Toda capacidad de ejecución REAL permanece ausente y suspendida hasta
superar los requisitos técnicos, regulatorios, de seguridad,
reconciliación y validación definidos por el Arquitecto y aprobados por
Jessica.

## Consecuencias

- Las tareas siguientes de la Fase 0 (scaffold de backend, frontend,
  Docker Compose, CI) podrán referenciar este ADR como fuente única de
  verdad sobre versiones y estructura, evitando decisiones implícitas o
  divergentes entre tareas.
- Cualquier cambio de versión o de decisión arquitectónica aquí descrita
  requiere un nuevo ADR o una revisión explícita de este documento,
  aprobada por el Arquitecto.

## Riesgos conocidos

- Docker Desktop no está instalado en el entorno de desarrollo local
  inspeccionado; es un prerrequisito antes de implementar PostgreSQL vía
  Docker Compose, pero no bloquea la fundación documental ni el scaffold
  de backend/frontend sin base de datos.
- La versión exacta de Angular 22.x (último patch) deberá confirmarse en
  el momento de ejecutar el scaffold, ya que este ADR fija la serie
  mayor, no un patch concreto.
- La versión final de SQLAlchemy 2.0.x quedará fijada por `uv.lock` en
  el momento de resolución de dependencias, no por este documento.
