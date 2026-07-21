from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field

from freyja_backend.api.deps import (
    ClientIp,
    CurrentUser,
    DbSession,
    EmailSenderDep,
    RateLimitHmacKey,
    require_csrf,
)
from freyja_backend.application import auth_service
from freyja_backend.core.config import get_settings
from freyja_backend.core.cookies import (
    SESSION_COOKIE_NAME,
    clear_csrf_cookie,
    clear_session_cookie,
    ensure_csrf_cookie,
    set_session_cookie,
)

router = APIRouter(prefix="/auth", tags=["auth"])

_GENERIC_LOGIN_ERROR = "Credenciales incorrectas."
_RATE_LIMIT_ERROR = "Demasiados intentos. Vuelve a intentarlo más tarde."
_TOKEN_INVALID_ERROR = "TOKEN_INVALID"
_TOKEN_EXPIRED_ERROR = "TOKEN_EXPIRED"
_REGISTER_ACK_MESSAGE = "Tu cuenta ha sido creada. Ya puedes iniciar sesión."
_FORGOT_PASSWORD_ACK_MESSAGE = "Si el correo existe, se enviará un enlace de restablecimiento."


class LoginRequest(BaseModel):
    identifier: str = Field(min_length=1, max_length=auth_service.MAX_IDENTIFIER_LENGTH)
    password: str = Field(min_length=1, max_length=auth_service.MAX_PASSWORD_LENGTH)


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=auth_service.MAX_PASSWORD_LENGTH)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=1, max_length=512)
    new_password: str = Field(min_length=1, max_length=auth_service.MAX_PASSWORD_LENGTH)


class UserOut(BaseModel):
    id: UUID
    identifier: str


class StatusOut(BaseModel):
    status: str
    message: str | None = None


@router.get("/csrf", response_model=StatusOut, status_code=status.HTTP_200_OK)
def get_csrf(request: Request, response: Response) -> StatusOut:
    """Single-responsibility endpoint: issues/renews the CSRF cookie. Creates
    no session, requires no session, and returns no user information — safe
    to call from a fully anonymous browser before login/register/forgot/
    reset."""
    ensure_csrf_cookie(request.cookies.get("freyja_csrf"), response)
    return StatusOut(status="ok")


@router.post(
    "/login",
    response_model=UserOut,
    dependencies=[Depends(require_csrf)],
    status_code=status.HTTP_200_OK,
)
def login(
    payload: LoginRequest,
    response: Response,
    db: DbSession,
    client_ip: ClientIp,
    hmac_key: RateLimitHmacKey,
) -> UserOut:
    settings = get_settings()
    try:
        user = auth_service.authenticate(
            db,
            identifier=payload.identifier,
            password=payload.password,
            ip_address=client_ip,
            hmac_key=hmac_key,
        )
    except auth_service.RateLimitedError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=_RATE_LIMIT_ERROR
        ) from exc
    except auth_service.InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=_GENERIC_LOGIN_ERROR
        ) from exc

    session = auth_service.create_session(db, user=user, ttl_minutes=settings.session_ttl_minutes)
    set_session_cookie(
        response, token=session.token, max_age_seconds=settings.session_ttl_minutes * 60
    )
    return UserOut(id=user.id, identifier=user.identifier)


@router.post(
    "/logout",
    response_model=StatusOut,
    dependencies=[Depends(require_csrf)],
    status_code=status.HTTP_200_OK,
)
def logout(request: Request, response: Response, db: DbSession) -> StatusOut:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        auth_service.revoke_session(db, token=token)
    clear_session_cookie(response)
    clear_csrf_cookie(response)
    return StatusOut(status="ok")


@router.get("/me", response_model=UserOut)
def me(current_user: CurrentUser) -> UserOut:
    return UserOut(id=current_user.id, identifier=current_user.identifier)


@router.post(
    "/register",
    response_model=StatusOut,
    dependencies=[Depends(require_csrf)],
    status_code=status.HTTP_200_OK,
)
def register(
    payload: RegisterRequest,
    db: DbSession,
    client_ip: ClientIp,
    hmac_key: RateLimitHmacKey,
) -> StatusOut:
    try:
        auth_service.register_user(
            db,
            email=payload.email,
            password=payload.password,
            ip_address=client_ip,
            hmac_key=hmac_key,
        )
    except auth_service.RateLimitedError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=_RATE_LIMIT_ERROR
        ) from exc
    except auth_service.InvalidRegistrationDataError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    return StatusOut(status="ok", message=_REGISTER_ACK_MESSAGE)


@router.post(
    "/forgot-password",
    response_model=StatusOut,
    dependencies=[Depends(require_csrf)],
    status_code=status.HTTP_202_ACCEPTED,
)
def forgot_password(
    payload: ForgotPasswordRequest,
    db: DbSession,
    email_sender: EmailSenderDep,
    client_ip: ClientIp,
    hmac_key: RateLimitHmacKey,
) -> StatusOut:
    settings = get_settings()
    try:
        auth_service.request_password_reset(
            db,
            email=payload.email,
            email_sender=email_sender,
            frontend_origin=settings.frontend_origin,
            reset_ttl_minutes=settings.password_reset_ttl_minutes,
            ip_address=client_ip,
            hmac_key=hmac_key,
        )
    except auth_service.RateLimitedError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=_RATE_LIMIT_ERROR
        ) from exc
    return StatusOut(status="ok", message=_FORGOT_PASSWORD_ACK_MESSAGE)


@router.post(
    "/reset-password",
    response_model=StatusOut,
    dependencies=[Depends(require_csrf)],
    status_code=status.HTTP_200_OK,
)
def reset_password(payload: ResetPasswordRequest, db: DbSession) -> StatusOut:
    try:
        auth_service.reset_password(db, token=payload.token, new_password=payload.new_password)
    except auth_service.InvalidRegistrationDataError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    except auth_service.TokenInvalidError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=_TOKEN_INVALID_ERROR
        ) from exc
    except auth_service.TokenExpiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=_TOKEN_EXPIRED_ERROR
        ) from exc
    return StatusOut(status="ok")
