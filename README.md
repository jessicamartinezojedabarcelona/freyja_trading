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

Todavía no existe una aplicación funcional completa. Existen scaffolds
mínimos de backend y frontend, sin capacidades funcionales, autenticación
ni dominio de trading implementados. Adicionalmente, está disponible la
base de datos PostgreSQL local mediante Docker Compose, descrita a
continuación. El resto de comandos de instalación o arranque se
documentará en tareas futuras, una vez los componentes correspondientes
existan.

## Desarrollo local — PostgreSQL

Este repositorio incluye una configuración de Docker Compose v2 para
levantar una instancia local de PostgreSQL 18.4, exclusivamente para
desarrollo. No incluye ningún otro servicio (sin Adminer, sin pgAdmin).

### Requisitos

- Docker Engine y Docker Compose v2 (`docker compose`).

### Configuración

1. Copia `.env.example` a `.env`.
2. Define `POSTGRES_DB`, `POSTGRES_USER` y `POSTGRES_PASSWORD`.
   `POSTGRES_PORT` es opcional y utiliza `5432` por defecto. Si falta
   cualquiera de las tres variables obligatorias, Docker Compose falla
   antes de iniciar (configuración fail-closed).
3. `.env` está ignorado por Git; nunca debe versionarse ni compartirse.

### Arranque

```bash
docker compose up -d
docker compose ps
```

El servicio expone PostgreSQL únicamente en
`127.0.0.1:${POSTGRES_PORT:-5432}`. Los datos persisten en un volumen
Docker nombrado; no se utilizan bind mounts para los datos.

### Detener

```bash
docker compose down
```

No se debe ejecutar `docker compose down -v`: eliminaría el volumen de
datos persistente.

## Backend — Persistencia y migraciones (Alembic)

Requiere que PostgreSQL local (ver sección anterior) esté `healthy`. Todos
los comandos se ejecutan desde `backend/`. Las credenciales se leen del
`.env` de la raíz del repositorio y nunca se versionan. SQLite no está
soportado en ningún caso.

```bash
uv sync
uv run alembic current
uv run alembic heads
uv run alembic upgrade head
```

`uv run alembic downgrade base` es un comando de verificación/desarrollo
para comprobar la reversibilidad de la cadena de migraciones; no es una
operación rutinaria y no debe ejecutarse sobre datos valiosos.

Para ejecutar los tests de integración (requieren PostgreSQL real):

```bash
uv run pytest tests/integration
```

## Controles de calidad

Existe una única entrada reproducible y multiplataforma (Windows y Linux)
para ejecutar todos los controles locales de calidad, desde la raíz del
repositorio:

```bash
uv run --python 3.12 scripts/quality.py
uv run --python 3.12 scripts/quality.py --backend
uv run --python 3.12 scripts/quality.py --frontend
```

Sin argumentos equivale a `--backend` + `--frontend`. Los tres modos son
mutuamente excluyentes.

El modo completo (o `--backend`) requiere que PostgreSQL local esté
`healthy` (ver sección de PostgreSQL más arriba); los tests de backend usan
PostgreSQL real, nunca SQLite ni mocks. El orquestador no inicia, detiene ni
recrea Docker: solo valida la configuración (`docker compose config
--quiet`) y comprueba de forma segura que el servicio esté disponible. No
utiliza auto-fix ni modifica archivos. Cada control se detiene ante el
primer error y propaga su código de salida.

`F0-CI-001` reutilizará posteriormente estos mismos controles como base de
la integración continua; todavía no existe CI en este repositorio.

### Backend manual

Desde `backend/`:

```bash
uv sync --locked
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests
uv run pytest
uv run alembic heads
uv run alembic current
uv build
```

### Frontend manual

Desde `frontend/`:

```bash
npm ci
npm run format:check
npm run lint
npm run typecheck
npm run test:ci
npm run build
```
