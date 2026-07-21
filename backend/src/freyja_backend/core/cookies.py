from fastapi import Response

from freyja_backend.core import security
from freyja_backend.core.config import get_settings

SESSION_COOKIE_NAME = "freyja_session"
CSRF_COOKIE_NAME = "freyja_csrf"
CSRF_HEADER_NAME = "X-CSRF-Token"

_CSRF_COOKIE_MAX_AGE_SECONDS = 24 * 60 * 60


def set_session_cookie(response: Response, *, token: str, max_age_seconds: int) -> None:
    settings = get_settings()
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=max_age_seconds,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
    )


def ensure_csrf_cookie(existing_value: str | None, response: Response) -> str:
    settings = get_settings()
    token = existing_value or security.generate_opaque_token(security.CSRF_TOKEN_BYTES)
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=token,
        max_age=_CSRF_COOKIE_MAX_AGE_SECONDS,
        httponly=False,
        secure=settings.cookie_secure,
        samesite="strict",
        path="/",
    )
    return token


def clear_csrf_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        key=CSRF_COOKIE_NAME,
        path="/",
        httponly=False,
        secure=settings.cookie_secure,
        samesite="strict",
    )
