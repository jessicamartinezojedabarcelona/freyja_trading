import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from freyja_backend.application import auth_service
from freyja_backend.core import security
from freyja_backend.core.config import Settings, get_settings
from freyja_backend.core.cookies import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, SESSION_COOKIE_NAME
from freyja_backend.core.email import EmailSender, SmtpConfig, get_email_sender
from freyja_backend.db.deps import get_db, is_database_ready
from freyja_backend.db.models import AuthUser

DbSession = Annotated[Session, Depends(get_db)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
DatabaseReady = Annotated[bool, Depends(is_database_ready)]


def get_email_sender_dep(settings: SettingsDep) -> EmailSender:
    config = SmtpConfig(
        host=settings.smtp_host or "127.0.0.1",
        port=settings.smtp_port,
        use_tls=settings.smtp_use_tls,
        from_address=settings.smtp_from_address or "no-reply@freyja.local",
        username=settings.smtp_username,
        password=settings.smtp_password,
        timeout_seconds=settings.smtp_timeout_seconds,
    )
    return get_email_sender(config)


EmailSenderDep = Annotated[EmailSender, Depends(get_email_sender_dep)]


def get_rate_limit_hmac_key(settings: SettingsDep) -> bytes:
    return security.resolve_rate_limit_hmac_key(settings.rate_limit_hmac_key)


RateLimitHmacKey = Annotated[bytes, Depends(get_rate_limit_hmac_key)]


def require_csrf(request: Request) -> None:
    """Double-submit CSRF check for state-changing endpoints."""
    cookie_value = request.cookies.get(CSRF_COOKIE_NAME)
    header_value = request.headers.get(CSRF_HEADER_NAME)
    if (
        not cookie_value
        or not header_value
        or not secrets.compare_digest(cookie_value, header_value)
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF inválido.")


def get_client_ip(request: Request) -> str:
    # Deliberately request.client.host only: X-Forwarded-For is attacker-
    # controlled unless a trusted reverse proxy strips/sets it, and no such
    # proxy exists yet in this local setup. Proxy-aware resolution belongs to
    # DEPLOY-ONLINE-001, once the real hosting provider and its trusted
    # proxies are known.
    if request.client is not None:
        return request.client.host
    return "unknown"


def get_current_user(request: Request, db: DbSession) -> AuthUser:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No autenticado.")
    user = auth_service.resolve_session(db, token=token)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No autenticado.")
    return user


CurrentUser = Annotated[AuthUser, Depends(get_current_user)]
ClientIp = Annotated[str, Depends(get_client_ip)]
