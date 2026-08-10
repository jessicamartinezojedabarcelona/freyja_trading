"""Dispara un despliegue en Render y espera a que quede realmente 'live'
en el commit exacto esperado, consultando la API oficial de Render.

Un deploy hook que responde HTTP 200 solo confirma que Render *aceptó*
la solicitud, no que el despliegue haya terminado ni que haya terminado
con éxito. Este módulo distingue explícitamente ambas cosas: dispara el
hook una única vez por servicio, captura el ID de despliegue que Render
devuelve, y a partir de ahí solo confía en el estado que la API oficial
de Render reporta para ese ID concreto.

Ningún valor secreto (deploy hook URL, API key) se registra ni se
incluye en ningún mensaje de error: los mensajes solo contienen el ID de
despliegue, su estado y el SHA de commit, ninguno de los cuales es
secreto.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable

RENDER_API_BASE = "https://api.render.com/v1"

# Valores de "status" documentados oficialmente por la API de Render para
# un despliegue: https://api-docs.render.com/reference/retrieve-deploy
SUCCESS_STATUS = "live"
FAILURE_STATUSES = frozenset(
    {
        "build_failed",
        "update_failed",
        "canceled",
        "deactivated",
        "pre_deploy_failed",
    }
)
IN_PROGRESS_STATUSES = frozenset(
    {
        "created",
        "queued",
        "build_in_progress",
        "update_in_progress",
        "pre_deploy_in_progress",
    }
)


class RenderDeployError(Exception):
    """Un despliegue no pudo dispararse o no se pudo confirmar 'live' en el SHA esperado."""


@dataclass(frozen=True)
class DeployStatus:
    deploy_id: str
    status: str
    commit_id: str | None


HttpPost = Callable[[str], tuple[int, str]]
HttpGet = Callable[[str, str], tuple[int, str]]


def _http_post(url: str) -> tuple[int, str]:
    request = urllib.request.Request(url, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")


def _http_get(url: str, api_key: str) -> tuple[int, str]:
    request = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")


def _extract_deploy_id(payload: object) -> str:
    if isinstance(payload, dict):
        deploy = payload.get("deploy")
        if isinstance(deploy, dict):
            deploy_id = deploy.get("id")
            if isinstance(deploy_id, str) and deploy_id:
                return deploy_id

        deploy_id = payload.get("id")
        if isinstance(deploy_id, str) and deploy_id:
            return deploy_id

    raise RenderDeployError(
        "Render aceptó la solicitud de despliegue, pero la respuesta no incluye un "
        "ID de despliegue verificable (puede ocurrir en una respuesta 202 sin ID); "
        "no se puede confirmar el resultado del despliegue."
    )


def trigger_deploy(hook_url: str, sha: str, *, http_post: HttpPost = _http_post) -> str:
    """Dispara el deploy hook exactamente una vez y devuelve el ID de despliegue."""
    if not sha:
        raise RenderDeployError("Se requiere un SHA de commit no vacío para desplegar.")

    separator = "&" if "?" in hook_url else "?"
    url = f"{hook_url}{separator}ref={sha}"

    status_code, body = http_post(url)
    # 202 is a documented, legitimate "accepted" response from a Render deploy
    # hook — Render's own docs note it deliberately omits a deploy ID. It is
    # not a rejection: _extract_deploy_id below is what correctly turns that
    # missing-ID case into a hard failure, instead of silently accepting an
    # unverifiable deploy.
    if status_code not in (200, 201, 202):
        raise RenderDeployError(
            f"Render rechazó la solicitud de despliegue (HTTP {status_code})."
        )

    try:
        payload = json.loads(body) if body.strip() else {}
    except json.JSONDecodeError as exc:
        raise RenderDeployError(
            "Render aceptó la solicitud de despliegue, pero la respuesta no es JSON válido."
        ) from exc

    return _extract_deploy_id(payload)


def fetch_deploy_status(
    service_id: str,
    deploy_id: str,
    api_key: str,
    *,
    http_get: HttpGet = _http_get,
) -> DeployStatus:
    """Consulta el estado de un despliegue vía la API oficial de Render (solo lectura)."""
    url = f"{RENDER_API_BASE}/services/{service_id}/deploys/{deploy_id}"
    status_code, body = http_get(url, api_key)
    if status_code != 200:
        raise RenderDeployError(
            f"No se pudo consultar el estado del despliegue {deploy_id} en Render "
            f"(HTTP {status_code})."
        )

    try:
        payload = json.loads(body) if body.strip() else {}
    except json.JSONDecodeError as exc:
        raise RenderDeployError(
            f"Render devolvió una respuesta de estado no válida para el despliegue {deploy_id}."
        ) from exc

    status = payload.get("status") if isinstance(payload, dict) else None
    if not isinstance(status, str) or not status:
        raise RenderDeployError(
            f"La respuesta de Render para el despliegue {deploy_id} no incluye un estado."
        )

    commit = payload.get("commit") if isinstance(payload, dict) else None
    commit_id = commit.get("id") if isinstance(commit, dict) else None
    commit_id = commit_id if isinstance(commit_id, str) else None

    return DeployStatus(deploy_id=deploy_id, status=status, commit_id=commit_id)


def wait_for_live_deploy(
    service_id: str,
    deploy_id: str,
    api_key: str,
    expected_sha: str,
    *,
    timeout_seconds: int,
    poll_interval_seconds: int,
    http_get: HttpGet = _http_get,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], float] = time.monotonic,
) -> DeployStatus:
    """Sondea un despliegue ya disparado hasta que quede 'live' en el SHA esperado.

    Nunca vuelve a disparar el despliegue: solo realiza consultas GET de solo
    lectura contra la API oficial de Render, con un intervalo y un tiempo
    máximo de espera finitos.
    """
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds debe ser positivo.")
    if poll_interval_seconds <= 0:
        raise ValueError("poll_interval_seconds debe ser positivo.")

    deadline = now() + timeout_seconds

    while True:
        result = fetch_deploy_status(service_id, deploy_id, api_key, http_get=http_get)

        if result.status == SUCCESS_STATUS:
            if result.commit_id != expected_sha:
                raise RenderDeployError(
                    f"El despliegue {deploy_id} quedó 'live' en el commit "
                    f"{result.commit_id!r}, pero se esperaba {expected_sha!r}."
                )
            return result

        if result.status in FAILURE_STATUSES:
            raise RenderDeployError(
                f"El despliegue {deploy_id} terminó en estado de fallo: {result.status!r}."
            )

        if result.status not in IN_PROGRESS_STATUSES:
            raise RenderDeployError(
                f"El despliegue {deploy_id} devolvió un estado no reconocido: "
                f"{result.status!r}."
            )

        if now() >= deadline:
            raise RenderDeployError(
                f"Tiempo de espera agotado ({timeout_seconds}s) esperando a que el "
                f"despliegue {deploy_id} llegara a 'live' (último estado: "
                f"{result.status!r})."
            )

        sleep(poll_interval_seconds)


def verify_deploy(
    *,
    hook_url: str,
    service_id: str,
    api_key: str,
    sha: str,
    timeout_seconds: int,
    poll_interval_seconds: int,
    http_post: HttpPost = _http_post,
    http_get: HttpGet = _http_get,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], float] = time.monotonic,
) -> DeployStatus:
    """Dispara un despliegue una única vez y espera su confirmación oficial."""
    deploy_id = trigger_deploy(hook_url, sha, http_post=http_post)
    return wait_for_live_deploy(
        service_id,
        deploy_id,
        api_key,
        sha,
        timeout_seconds=timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
        http_get=http_get,
        sleep=sleep,
        now=now,
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Dispara un despliegue en Render vía deploy hook y no termina en éxito "
            "hasta confirmar, mediante la API oficial de Render, que el servicio "
            "quedó 'live' en el commit exacto esperado."
        )
    )
    parser.add_argument(
        "--service-name",
        required=True,
        help="Nombre descriptivo del servicio, solo para mensajes (p. ej. 'backend').",
    )
    parser.add_argument(
        "--hook-url-env",
        required=True,
        help="Nombre de la variable de entorno que contiene la URL del deploy hook.",
    )
    parser.add_argument(
        "--service-id-env",
        required=True,
        help="Nombre de la variable de entorno que contiene el service ID de Render.",
    )
    parser.add_argument(
        "--api-key-env",
        required=True,
        help="Nombre de la variable de entorno que contiene la API key de Render.",
    )
    parser.add_argument("--sha", required=True, help="SHA de commit exacto esperado.")
    parser.add_argument("--timeout-seconds", type=int, default=600)
    parser.add_argument("--poll-interval-seconds", type=int, default=15)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)

    env_lookup = {
        args.hook_url_env: os.environ.get(args.hook_url_env),
        args.service_id_env: os.environ.get(args.service_id_env),
        args.api_key_env: os.environ.get(args.api_key_env),
    }
    missing = [name for name, value in env_lookup.items() if not value]
    if missing:
        print(
            f"Faltan variables de entorno requeridas: {', '.join(missing)}.",
            file=sys.stderr,
        )
        return 1

    hook_url = env_lookup[args.hook_url_env]
    service_id = env_lookup[args.service_id_env]
    api_key = env_lookup[args.api_key_env]
    assert hook_url is not None
    assert service_id is not None
    assert api_key is not None

    print(f"-> Desplegando {args.service_name} en el commit {args.sha}")
    try:
        result = verify_deploy(
            hook_url=hook_url,
            service_id=service_id,
            api_key=api_key,
            sha=args.sha,
            timeout_seconds=args.timeout_seconds,
            poll_interval_seconds=args.poll_interval_seconds,
        )
    except RenderDeployError as exc:
        print(f"FALLO: despliegue de {args.service_name} no confirmado: {exc}", file=sys.stderr)
        return 1

    print(
        f"OK: {args.service_name} está 'live' en el commit esperado "
        f"(despliegue {result.deploy_id})."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
