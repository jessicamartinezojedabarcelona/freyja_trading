from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
FRONTEND_DIR = REPO_ROOT / "frontend"

EXPECTED_HEAD = "0009_seed_integrity_guard (head)"
_ALEMBIC_INFO_PREFIX = "INFO  [alembic."


class QualityCheckFailureError(Exception):
    def __init__(self, returncode: int, description: str) -> None:
        super().__init__(f"{description} (codigo {returncode})")
        self.returncode = returncode
        self.description = description


def _resolve_executable(name: str) -> str:
    resolved = shutil.which(name)
    if resolved is None:
        raise QualityCheckFailureError(1, f"no se encontro el ejecutable requerido: {name}")
    return resolved


def run_command(command: list[str], cwd: Path) -> int:
    result = subprocess.run(command, cwd=str(cwd), check=False)
    return result.returncode


def run_command_capture(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=str(cwd), check=False, capture_output=True, text=True)


def run_step(description: str, command: list[str], cwd: Path) -> None:
    print(f"-> {description}")
    returncode = run_command(command, cwd)
    if returncode != 0:
        print(f"FALLO: {description}")
        raise QualityCheckFailureError(returncode, description)
    print(f"OK: {description}")


def _significant_lines(output: str) -> list[str]:
    lines: list[str] = []
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith(_ALEMBIC_INFO_PREFIX):
            continue
        lines.append(line)
    return lines


def validate_alembic_heads(output: str) -> None:
    lines = _significant_lines(output)
    if len(lines) != 1:
        raise QualityCheckFailureError(
            1,
            f"alembic heads debe reportar exactamente una linea significativa "
            f"(encontradas: {len(lines)})",
        )
    if lines[0] != EXPECTED_HEAD:
        raise QualityCheckFailureError(1, f"alembic heads inesperado (no es {EXPECTED_HEAD!r})")


def validate_alembic_current(output: str) -> None:
    lines = _significant_lines(output)
    if len(lines) != 1:
        raise QualityCheckFailureError(
            1,
            f"alembic current debe reportar exactamente una linea significativa "
            f"(encontradas: {len(lines)})",
        )
    if lines[0] != EXPECTED_HEAD:
        raise QualityCheckFailureError(1, f"alembic current inesperado (no es {EXPECTED_HEAD!r})")


def validate_alembic_stderr(stderr: str) -> None:
    if _significant_lines(stderr):
        raise QualityCheckFailureError(
            1, "alembic produjo salida inesperada en stderr (no reconocida como INFO de alembic)"
        )


def validate_compose_ps_stderr(stderr: str) -> None:
    if stderr.strip():
        raise QualityCheckFailureError(1, "docker compose ps produjo salida inesperada en stderr")


def _require_json_object(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise QualityCheckFailureError(
            1, "salida de docker compose ps contiene un elemento que no es un objeto JSON"
        )
    return value


def _parse_compose_ps_ndjson(text: str) -> list[dict[str, object]]:
    objects: list[dict[str, object]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise QualityCheckFailureError(
                1, "salida de docker compose ps no es JSON valido"
            ) from exc
        objects.append(_require_json_object(item))
    return objects


def _parse_compose_ps_json(stdout: str) -> list[dict[str, object]]:
    text = stdout.strip()
    if not text:
        return []

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return _parse_compose_ps_ndjson(text)

    if isinstance(data, dict):
        return [_require_json_object(data)]
    if isinstance(data, list):
        return [_require_json_object(item) for item in data]
    raise QualityCheckFailureError(1, "salida de docker compose ps con formato JSON no reconocido")


def check_postgres_available() -> None:
    docker = _resolve_executable("docker")
    run_step(
        "docker compose config --quiet",
        [docker, "compose", "config", "--quiet"],
        REPO_ROOT,
    )

    print("-> comprobando estado del servicio postgres")
    result = run_command_capture(
        [docker, "compose", "ps", "--format", "json", "postgres"], REPO_ROOT
    )
    if result.returncode != 0:
        raise QualityCheckFailureError(result.returncode, "docker compose ps")

    validate_compose_ps_stderr(result.stderr)

    containers = _parse_compose_ps_json(result.stdout)
    postgres_entries = [c for c in containers if c.get("Service") == "postgres"]

    if len(postgres_entries) != 1:
        raise QualityCheckFailureError(
            1,
            "se esperaba exactamente un contenedor del servicio postgres "
            f"(encontrados: {len(postgres_entries)})",
        )

    health = postgres_entries[0].get("Health")
    if not isinstance(health, str) or health != "healthy":
        raise QualityCheckFailureError(1, "el servicio postgres no esta healthy")
    print("OK: postgres healthy")


def run_backend_checks() -> None:
    print("=== Backend ===")
    uv = _resolve_executable("uv")
    run_step("uv sync --locked", [uv, "sync", "--locked"], BACKEND_DIR)
    run_step(
        "ruff format --check",
        [uv, "run", "ruff", "format", "--check", "."],
        BACKEND_DIR,
    )
    run_step("ruff check", [uv, "run", "ruff", "check", "."], BACKEND_DIR)
    run_step("mypy", [uv, "run", "mypy", "src", "tests"], BACKEND_DIR)

    check_postgres_available()

    run_step("alembic upgrade head", [uv, "run", "alembic", "upgrade", "head"], BACKEND_DIR)

    run_step("pytest", [uv, "run", "pytest"], BACKEND_DIR)

    print("-> uv run alembic heads")
    heads_result = run_command_capture([uv, "run", "alembic", "heads"], BACKEND_DIR)
    if heads_result.returncode != 0:
        raise QualityCheckFailureError(heads_result.returncode, "alembic heads")
    validate_alembic_stderr(heads_result.stderr)
    validate_alembic_heads(heads_result.stdout)
    print(f"OK: alembic heads -> {EXPECTED_HEAD}")

    print("-> uv run alembic current")
    current_result = run_command_capture([uv, "run", "alembic", "current"], BACKEND_DIR)
    if current_result.returncode != 0:
        raise QualityCheckFailureError(current_result.returncode, "alembic current")
    validate_alembic_stderr(current_result.stderr)
    validate_alembic_current(current_result.stdout)
    print(f"OK: alembic current -> {EXPECTED_HEAD}")

    with tempfile.TemporaryDirectory() as tmp_dir:
        run_step("uv build", [uv, "build", "--out-dir", tmp_dir], BACKEND_DIR)

    print("Backend: todos los controles superados.")


def run_frontend_checks() -> None:
    print("=== Frontend ===")
    npm = _resolve_executable("npm")
    run_step("npm ci", [npm, "ci"], FRONTEND_DIR)
    run_step("npm run format:check", [npm, "run", "format:check"], FRONTEND_DIR)
    run_step("npm run lint", [npm, "run", "lint"], FRONTEND_DIR)
    run_step("npm run typecheck", [npm, "run", "typecheck"], FRONTEND_DIR)
    run_step("npm run test:ci", [npm, "run", "test:ci"], FRONTEND_DIR)
    run_step("npm run build", [npm, "run", "build"], FRONTEND_DIR)
    print("Frontend: todos los controles superados.")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Orquestador de controles de calidad de Freyja 2.0."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--all",
        action="store_true",
        help="Ejecuta backend y frontend (comportamiento por defecto).",
    )
    group.add_argument(
        "--backend", action="store_true", help="Ejecuta unicamente los controles de backend."
    )
    group.add_argument(
        "--frontend", action="store_true", help="Ejecuta unicamente los controles de frontend."
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)

    if args.backend:
        run_backend, run_frontend = True, False
    elif args.frontend:
        run_backend, run_frontend = False, True
    else:
        run_backend, run_frontend = True, True

    try:
        if run_backend:
            run_backend_checks()
        if run_frontend:
            run_frontend_checks()
    except QualityCheckFailureError as exc:
        print(f"Control de calidad detenido: {exc.description}", file=sys.stderr)
        return exc.returncode

    print("Todos los controles de calidad solicitados se completaron correctamente.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
