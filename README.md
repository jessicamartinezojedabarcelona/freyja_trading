# Freyja 2.0

## 1. Qué es Freyja 2.0 y estado actual

Freyja 2.0 es una plataforma de análisis y asistencia de trading dirigida
principalmente a personas sin conocimientos técnicos, capaz de ofrecer
información avanzada cuando el usuario la necesite. La experiencia adapta
la profundidad de la información mostrada, pero todos los usuarios
comparten el mismo dominio, el mismo motor y la misma base de código.

**Estado real actual: Fase 0 — Fundación técnica.** Existen scaffolds
mínimos y operativos de backend, frontend, persistencia y controles de
calidad (incluida integración continua verde en `main`), pero **todavía no
existe dominio funcional de trading, autenticación, ni ejecución
DEMO/REAL**. Este README describe cómo instalar, arrancar y verificar esa
fundación técnica; no describe un producto terminado.

Consulta el detalle completo y las justificaciones del stack en
[`docs/adr/0001-stack-y-arquitectura-inicial.md`](docs/adr/0001-stack-y-arquitectura-inicial.md).

## 2. Componentes actuales

- **Backend**: Python 3.12, FastAPI, gestionado con `uv`. Expone un único
  endpoint de salud (`/api/v1/health`).
- **Frontend**: Angular 22.x, TypeScript, gestionado con `npm`. Aplicación
  base sin vistas funcionales de dominio.
- **PostgreSQL**: única base de datos del sistema, versión `18.4`,
  ejecutada localmente vía Docker Compose.
- **SQLAlchemy / Alembic**: capa de persistencia y migraciones del
  backend. La base de datos se crea exclusivamente mediante migraciones de
  Alembic.
- **Orquestador de calidad** (`scripts/quality.py`): punto de entrada
  único, reproducible y multiplataforma para ejecutar todos los controles
  locales de backend y frontend.
- **GitHub Actions** (`.github/workflows/ci.yml`): integración continua
  que ejecuta los mismos controles en cada Pull Request contra `main` y en
  cada push a `main`.

## 3. Prerrequisitos

Herramientas necesarias. Se indica la versión exacta verificada en el
desarrollo de este repositorio; salvo que se indique lo contrario, no se ha
probado la compatibilidad con otras versiones.

| Herramienta | Versión verificada | Notas |
|---|---|---|
| Git | 2.55.0 | Cualquier versión reciente de Git 2.x debería funcionar; no se ha probado exhaustivamente una versión mínima distinta. |
| Docker Engine / Docker Desktop | 29.6.1, con Docker Compose v5.3.0 (Compose v2) | Se requiere explícitamente Docker Compose **v2** (`docker compose`, sin guion). |
| WSL2 (solo Windows) | WSL con distribución Ubuntu, versión de WSL 2 | Necesario para que Docker Desktop pueda ejecutar contenedores Linux en Windows. |
| uv | 0.11.6 | Gestiona el entorno y las dependencias del backend. |
| Python | 3.12.10 (`requires-python = "==3.12.*"` en `backend/pyproject.toml`) | `uv` puede aprovisionar el intérprete automáticamente; no requiere una instalación manual previa. |
| Node.js | v24.17.0 | El proyecto declara `"packageManager": "npm@11.13.0"` en `frontend/package.json`. |
| npm | 11.13.0 | Debe coincidir con el `packageManager` declarado para evitar avisos o incompatibilidades. |

Puertos usados en desarrollo local:

- `127.0.0.1:5432` — PostgreSQL (Docker Compose).
- `127.0.0.1:8000` — backend (FastAPI/uvicorn).
- `localhost:4200` — frontend (servidor de desarrollo de Angular).

## 4. Clonación y ubicación

```bash
git clone https://github.com/jessicamartinezojedabarcelona/freyja_trading.git
cd freyja_trading
```

Todos los comandos de este README asumen que la ubicación actual es la
raíz del repositorio, salvo que se indique explícitamente otra carpeta
(`backend/` o `frontend/`).

## 5. Configuración inicial

1. Copia `.env.example` a `.env` en la raíz del repositorio:

   PowerShell:

   ```powershell
   Copy-Item .env.example .env
   ```

   Bash / WSL / Git Bash:

   ```bash
   cp .env.example .env
   ```

2. Edita `.env` y define las variables obligatorias:
   - `POSTGRES_DB`
   - `POSTGRES_USER`
   - `POSTGRES_PASSWORD` — usa una contraseña local robusta y exclusiva
     para este entorno de desarrollo; no reutilices contraseñas de otros
     sistemas.

   Variable opcional:
   - `POSTGRES_PORT` — `5432` por defecto.

   Si falta cualquiera de las tres variables obligatorias, Docker Compose
   falla explícitamente antes de arrancar (configuración *fail-closed*
   mediante `${POSTGRES_DB:?...}` en `docker-compose.yml`).

3. `.env` está ignorado por Git (`.gitignore`) y **nunca** debe
   versionarse, compartirse, pegarse en incidencias, logs o Pull Requests,
   ni copiarse a `.env.example`.

Este README no incluye valores reales de `.env` en ningún ejemplo.

## 6. Instalación de dependencias

### Backend

Desde `backend/`:

```bash
uv sync --locked
```

Instala exactamente las versiones fijadas en `backend/uv.lock`. No uses
`pip install` manual ni `uv add` para instalar el entorno de desarrollo.

### Frontend

Desde `frontend/`:

```bash
npm ci
```

Instala exactamente las versiones fijadas en `frontend/package-lock.json`.
No uses `npm install` para esta instalación: `npm ci` no modifica el
lockfile, mientras que `npm install` sí podría hacerlo.

## 7. PostgreSQL local

Configuración de Docker Compose v2 para levantar una instancia local de
PostgreSQL 18.4, exclusivamente para desarrollo. No incluye ningún otro
servicio (sin Adminer, sin pgAdmin).

Validar la configuración:

```bash
docker compose config --quiet
```

Arrancar:

```bash
docker compose up -d
docker compose ps
```

Espera a que la columna `STATUS` muestre `healthy` (el healthcheck usa
`pg_isready` con reintentos; puede tardar unos segundos). El servicio
expone PostgreSQL únicamente en `127.0.0.1:${POSTGRES_PORT:-5432}`. Los
datos persisten en un volumen Docker nombrado; no se utilizan bind mounts.

Detener sin perder datos:

```bash
docker compose down
```

Reanudar más adelante:

```bash
docker compose up -d
```

Los datos persisten porque el volumen nombrado no se elimina con
`docker compose down`.

**No ejecutes `docker compose down -v`**: elimina el volumen y, con él,
todos los datos persistidos de forma irreversible.

## 8. Migraciones (Alembic)

Requiere que PostgreSQL local esté `healthy` (sección anterior). Todos los
comandos se ejecutan desde `backend/`. Las credenciales se leen del `.env`
de la raíz y nunca se versionan. SQLite no está soportado en ningún caso.

La base de datos **no** se crea mediante `Base.metadata.create_all()`:
Alembic es el único mecanismo autorizado para crear o modificar el
esquema.

Consultar los heads disponibles:

```bash
uv run alembic heads
```

Actualmente existe un único head: `0001_initial (head)`.

Consultar la revisión actual aplicada:

```bash
uv run alembic current
```

Aplicar todas las migraciones pendientes:

```bash
uv run alembic upgrade head
```

El modo offline de Alembic no está soportado: `backend/alembic/env.py`
rechaza explícitamente `alembic upgrade --sql` y comandos equivalentes en
modo offline, exigiendo una conexión real a PostgreSQL.

No se documentan aquí comandos de `downgrade` como operación rutinaria:
son exclusivamente de verificación/desarrollo y no deben ejecutarse sobre
datos valiosos.

## 9. Backend

Arrancar en modo desarrollo, desde `backend/`:

```bash
uv run uvicorn freyja_backend.main:app --host 127.0.0.1 --port 8000
```

- Host y puerto reales verificados: `127.0.0.1:8000`.
- Endpoint de salud verificado: `GET http://127.0.0.1:8000/api/v1/health`
  → `200 OK` con un cuerpo JSON similar a:

  ```json
  {"status":"ok","service":"Freyja 2.0 Backend","version":"0.1.0","environment":"development"}
  ```

Detener: `Ctrl+C` en la terminal donde se ejecuta el proceso.

## 10. Frontend

Arrancar en modo desarrollo, desde `frontend/`:

```bash
npm start
```

(equivalente a `ng serve`).

- URL real verificada: `http://localhost:4200/`.
- El servidor de desarrollo no abre el navegador automáticamente.

Detener: `Ctrl+C` en la terminal donde se ejecuta el proceso.

## 11. Arranque completo

Orden operativo recomendado, con verificación de salud en cada paso:

1. **PostgreSQL** (una terminal, o en segundo plano vía `-d`):
   ```bash
   docker compose up -d
   docker compose ps   # confirmar "healthy"
   ```
2. **Migraciones** (terminal cualquiera, una sola vez o tras cada cambio
   de esquema), desde `backend/`:
   ```bash
   uv run alembic upgrade head
   ```
3. **Backend** (terminal dedicada — el proceso ocupa la terminal), desde
   `backend/`:
   ```bash
   uv run uvicorn freyja_backend.main:app --host 127.0.0.1 --port 8000
   ```
4. **Frontend** (otra terminal dedicada — el proceso ocupa la terminal),
   desde `frontend/`:
   ```bash
   npm start
   ```
5. **Verificación de salud**:
   - Backend: `GET http://127.0.0.1:8000/api/v1/health` → `200 OK`.
   - Frontend: `http://localhost:4200/` → página cargada.

Backend y frontend necesitan cada uno su propia terminal, ya que ambos
procesos permanecen en primer plano hasta que se detienen manualmente.

## 12. Calidad y pruebas

Entrada única, reproducible y multiplataforma (Windows y Linux) para
ejecutar todos los controles locales, desde la raíz del repositorio:

```bash
uv run --python 3.12 scripts/quality.py
uv run --python 3.12 scripts/quality.py --backend
uv run --python 3.12 scripts/quality.py --frontend
```

Sin argumentos equivale a `--backend` + `--frontend`. Los tres modos son
mutuamente excluyentes.

- `--backend` valida: instalación desde lockfile, format-check y lint de
  Ruff, `mypy` estricto, `pytest`, la cadena de migraciones de Alembic
  (heads/current, de forma estricta) y el build del paquete.
- `--frontend` valida: instalación desde lockfile, format-check de
  Prettier, ESLint, type-check de TypeScript, tests no interactivos y el
  build de producción.

El modo `--backend` (o el modo completo) requiere que PostgreSQL local
esté `healthy`; los tests de backend usan PostgreSQL real, nunca SQLite ni
mocks. El orquestador no inicia, detiene ni recrea Docker: solo valida la
configuración (`docker compose config --quiet`) y comprueba de forma
segura que el servicio esté disponible. No utiliza auto-fix ni modifica
archivos. Cada control se detiene ante el primer error y propaga su código
de salida.

### Comandos individuales — backend

Desde `backend/`, con PostgreSQL local `healthy`:

```bash
uv sync --locked
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests
uv run pytest
uv run alembic heads
uv run alembic current
```

El build del paquete backend no se incluye en esta lista suelta: forma
parte del control canónico `uv run --python 3.12 scripts/quality.py
--backend`. El orquestador genera el build en un directorio temporal y
evita dejar `backend/dist/` dentro del checkout; para la comprobación
completa del backend debe preferirse ese comando canónico.

### Comandos individuales — frontend

Desde `frontend/`:

```bash
npm ci
npm run format:check
npm run lint
npm run typecheck
npm run test:ci
npm run build
```

Esta es la única sección del README que enumera estos comandos
individuales; el resto del documento remite aquí en lugar de repetirlos,
para evitar que ambos textos diverjan con el tiempo.

## 13. Integración continua (GitHub Actions)

`.github/workflows/ci.yml` ejecuta los controles de calidad de backend y
frontend como **dos jobs independientes**, activados en Pull Requests
contra `main` y en cada push a `main`.

- El job de backend usa un contenedor de servicio PostgreSQL **18.4**
  efímero, exclusivo de cada ejecución de CI, con credenciales
  deterministas y no sensibles generadas solo para ese contenedor.
- Las dependencias se instalan siempre desde los lockfiles
  (`uv sync --locked`, `npm ci`).
- Todas las `actions` de terceros están fijadas a un SHA de commit
  completo e inmutable (no a un tag flotante).
- La CI **no depende del `.env` local**: no se crea, copia, lee ni publica
  ningún `.env` en ningún paso del workflow.

Para reproducir localmente todos los controles equivalentes:

```bash
uv run --python 3.12 scripts/quality.py
```

## 14. Estructura del repositorio

```text
freyja_trading/
├── backend/
│   ├── alembic/               # migraciones de base de datos (Alembic)
│   ├── src/freyja_backend/    # código de la aplicación FastAPI
│   ├── tests/                 # tests de backend (unitarios e integración)
│   ├── alembic.ini
│   ├── pyproject.toml
│   └── uv.lock
├── frontend/
│   ├── src/                   # aplicación Angular
│   ├── angular.json
│   ├── package.json
│   └── package-lock.json
├── scripts/
│   └── quality.py             # orquestador local de controles de calidad
├── .github/
│   └── workflows/
│       └── ci.yml             # integración continua (GitHub Actions)
├── docs/
│   └── adr/                   # decisiones de arquitectura
├── docker-compose.yml         # PostgreSQL local
├── .env.example
├── README.md
└── CLAUDE.md
```

## 15. Solución de problemas

- **El daemon de Docker no está iniciado**: arranca Docker Desktop (o el
  servicio de Docker Engine) y espera a que esté completamente listo antes
  de ejecutar `docker compose`.
- **WSL no está instalado o Docker Desktop no arranca en Windows**:
  confirma que WSL2 está instalado y habilitado (`wsl --status`) y que
  Docker Desktop está configurado para usar el backend WSL2.
- **El puerto de PostgreSQL (5432) está ocupado**: define
  `POSTGRES_PORT` en `.env` con un puerto libre y vuelve a ejecutar
  `docker compose up -d`.
- **Variables obligatorias ausentes o vacías**: `docker compose` fallará
  con un mensaje explícito (`... is required`). Revisa que `.env` exista y
  tenga `POSTGRES_DB`, `POSTGRES_USER` y `POSTGRES_PASSWORD` completados.
- **Fallo de autenticación tras cambiar `POSTGRES_PASSWORD` en `.env` con
  el volumen ya existente**: PostgreSQL solo lee las variables
  `POSTGRES_*` la primera vez que inicializa el volumen. Cambiar
  únicamente `POSTGRES_PASSWORD` en `.env` **no** actualiza la contraseña
  del rol ya creado dentro del volumen persistente. La corrección conceptual
  y segura consiste en conectarse al contenedor en ejecución y actualizar
  la contraseña del rol mediante una sentencia `ALTER ROLE ... WITH
  PASSWORD ...` ejecutada de forma interactiva (nunca como texto literal en
  un comando de shell, script, log o historial). Si no puedes realizar esa
  rotación de forma segura, solicita una rotación controlada de la
  credencial en lugar de exponerla en texto plano.
- **PostgreSQL no alcanza el estado `healthy`**: revisa los logs con
  `docker compose logs postgres`; normalmente indica que el proceso sigue
  inicializando o que las variables de entorno no son válidas. No borres
  el volumen como primera solución.
- **`alembic current` aparece vacío o distinto de `0001_initial (head)`**:
  ejecuta `uv run alembic upgrade head` desde `backend/` con PostgreSQL
  `healthy`. Un valor vacío es normal en una base de datos recién creada
  antes de aplicar migraciones.
- **El comando `python` está "sombreado" por Microsoft Store en
  Windows** (no hace nada o abre la tienda): usa `py` o invoca el
  intérprete de `uv` explícitamente (`uv run python ...`,
  `uv run --python 3.12 ...`); no es necesario instalar Python desde la
  Microsoft Store.
- **Versión incorrecta de Node.js**: instala/activa Node 24.x (por
  ejemplo, mediante `nvm`) antes de ejecutar `npm ci`. No edites
  `packageManager` en `package.json` para forzar compatibilidad.
- **`npm ci` falla por lockfile desincronizado**: `npm ci` exige que
  `package-lock.json` sea coherente con `package.json`. No edites el
  lockfile manualmente; si el desajuste es real, debe resolverse en una
  tarea explícita de dependencias, no ejecutando `npm install` como atajo.
- **El backend o el frontend no arrancan**: confirma que
  `uv sync --locked` / `npm ci` se ejecutaron sin errores y que
  PostgreSQL está `healthy` antes de arrancar el backend.
- **Los controles locales fallan pero la CI pasa (o al contrario)**:
  suele deberse a diferencias de entorno: sistema operativo (Windows local
  frente a Ubuntu en el runner), estado previo de la base de datos local
  (con migraciones ya aplicadas) frente al contenedor efímero de CI, o
  caché local desactualizada. Ejecuta `uv sync --locked` / `npm ci` de
  nuevo localmente antes de asumir una contradicción real.

Ninguna de estas soluciones implica borrar volúmenes, desactivar
seguridad, usar `trust`, ignorar errores o editar lockfiles manualmente.

## 16. Limitaciones actuales

- No existe todavía autenticación.
- No existe dominio funcional de trading.
- No existe integración con brokers.
- No existe ejecución DEMO ni REAL.
- **La ejecución REAL permanece suspendida** hasta superar los requisitos
  técnicos, regulatorios, de seguridad, reconciliación y validación
  correspondientes.
- Los scaffolds de backend y frontend son fundación técnica verificada,
  no un producto terminado.
- El entorno documentado en este README está orientado exclusivamente a
  desarrollo local.

## 17. Seguridad operativa

- No versiones `.env` bajo ninguna circunstancia.
- No pegues secretos (contraseñas, tokens, credenciales) en incidencias,
  logs, mensajes de commit ni Pull Requests.
- No uses credenciales de broker ni de producción en este entorno.
- PostgreSQL local está restringido a `127.0.0.1`; no lo expongas en otras
  interfaces de red.
- No ejecutes `docker compose down -v` salvo una decisión consciente y
  explícitamente destructiva de eliminar todos los datos locales.
- No habilites `POSTGRES_HOST_AUTH_METHOD=trust` ni ningún mecanismo de
  autenticación sin contraseña.
