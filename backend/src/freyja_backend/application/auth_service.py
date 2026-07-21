import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from email_validator import EmailNotValidError, validate_email
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from freyja_backend.core import security
from freyja_backend.core.email import EmailDeliveryError, EmailMessage, EmailSender
from freyja_backend.db.models import (
    AuthPasswordResetToken,
    AuthRateLimitEvent,
    AuthSession,
    AuthUser,
    RateLimitAction,
    UserOrigin,
)

_auth_logger = logging.getLogger("freyja_backend.auth")

NowFn = Callable[[], datetime]

RATE_LIMIT_WINDOW = timedelta(minutes=15)
RATE_LIMIT_EVENT_RETENTION = timedelta(hours=24)

# Centralized, documented thresholds: (max failures/attempts per identifier,
# max per origin) within RATE_LIMIT_WINDOW. LOGIN only counts failures (a
# successful login must never count against the account's own future
# attempts); REGISTER and PASSWORD_RESET_REQUEST have no user-visible
# "failure" — the public response is always identical — so every attempt
# counts.
RATE_LIMITS: dict[RateLimitAction, tuple[int, int]] = {
    RateLimitAction.LOGIN: (5, 20),
    RateLimitAction.REGISTER: (5, 20),
    RateLimitAction.PASSWORD_RESET_REQUEST: (5, 20),
}
_COUNT_ONLY_FAILURES = frozenset({RateLimitAction.LOGIN})

MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 128
MIN_IDENTIFIER_LENGTH = 3
MAX_IDENTIFIER_LENGTH = 64


def default_now() -> datetime:
    return datetime.now(UTC)


class RateLimitedError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


class InvalidOwnerDataError(ValueError):
    pass


class OwnerAlreadyExistsError(ValueError):
    pass


class InvalidRegistrationDataError(ValueError):
    pass


class TokenInvalidError(Exception):
    pass


class TokenExpiredError(Exception):
    pass


@dataclass(frozen=True)
class AuthenticatedSession:
    user_id: uuid.UUID
    identifier: str
    token: str
    expires_at: datetime


def normalize_identifier(raw: str) -> str:
    return raw.strip().lower()


def _validate_and_normalize_email(raw: str) -> str:
    """Format validation via the maintained `email-validator` library (no
    network/deliverability check — see design notes). PostgreSQL's unique
    constraint on `auth_users.identifier` remains the final guarantee of
    uniqueness; this only rejects malformed input early."""
    try:
        validate_email(raw.strip(), check_deliverability=False)
    except EmailNotValidError as exc:
        raise InvalidRegistrationDataError("Correo con formato no válido.") from exc
    return normalize_identifier(raw)


# --- rate limiting (HMAC-keyed, shared by every throttled action) ----------


def _count_recent_events(
    db: Session,
    *,
    action: RateLimitAction,
    column_is_identifier: bool,
    key_value: str,
    now: datetime,
) -> int:
    window_start = now - RATE_LIMIT_WINDOW
    column = (
        AuthRateLimitEvent.identifier_key if column_is_identifier else AuthRateLimitEvent.origin_key
    )
    conditions = [
        AuthRateLimitEvent.action == action,
        column == key_value,
        AuthRateLimitEvent.created_at >= window_start,
    ]
    if action in _COUNT_ONLY_FAILURES:
        conditions.append(AuthRateLimitEvent.success.is_(False))
    stmt = select(func.count()).select_from(AuthRateLimitEvent).where(*conditions)
    return db.execute(stmt).scalar_one()


def is_rate_limited(
    db: Session,
    *,
    action: RateLimitAction,
    identifier: str,
    ip_address: str,
    hmac_key: bytes,
    now_fn: NowFn = default_now,
) -> bool:
    now = now_fn()
    identifier_key = security.hmac_key(normalize_identifier(identifier), hmac_key)
    origin_key = security.hmac_key(ip_address, hmac_key)
    id_limit, ip_limit = RATE_LIMITS[action]

    id_count = _count_recent_events(
        db, action=action, column_is_identifier=True, key_value=identifier_key, now=now
    )
    if id_count >= id_limit:
        return True
    ip_count = _count_recent_events(
        db, action=action, column_is_identifier=False, key_value=origin_key, now=now
    )
    return ip_count >= ip_limit


def record_rate_limit_event(
    db: Session,
    *,
    action: RateLimitAction,
    identifier: str,
    ip_address: str,
    success: bool,
    hmac_key: bytes,
    now: datetime,
) -> None:
    identifier_key = security.hmac_key(normalize_identifier(identifier), hmac_key)
    origin_key = security.hmac_key(ip_address, hmac_key)
    db.add(
        AuthRateLimitEvent(
            action=action,
            identifier_key=identifier_key,
            origin_key=origin_key,
            success=success,
            created_at=now,
        )
    )
    db.flush()
    cutoff = now - RATE_LIMIT_EVENT_RETENTION
    db.execute(delete(AuthRateLimitEvent).where(AuthRateLimitEvent.created_at < cutoff))


# --- login -------------------------------------------------------------------


def authenticate(
    db: Session,
    *,
    identifier: str,
    password: str,
    ip_address: str,
    hmac_key: bytes,
    now_fn: NowFn = default_now,
) -> AuthUser:
    """Raises RateLimitedError or InvalidCredentialsError. Never signals
    which case."""
    normalized = normalize_identifier(identifier)
    now = now_fn()

    if is_rate_limited(
        db,
        action=RateLimitAction.LOGIN,
        identifier=normalized,
        ip_address=ip_address,
        hmac_key=hmac_key,
        now_fn=now_fn,
    ):
        raise RateLimitedError

    user = db.execute(
        select(AuthUser).where(AuthUser.identifier == normalized)
    ).scalar_one_or_none()

    if user is None:
        # Timing-safety: run a real Argon2 verification against a fixed dummy
        # hash so "unknown identifier" takes the same time as "wrong password".
        security.verify_password(security.DUMMY_PASSWORD_HASH, password)
        record_rate_limit_event(
            db,
            action=RateLimitAction.LOGIN,
            identifier=normalized,
            ip_address=ip_address,
            success=False,
            hmac_key=hmac_key,
            now=now,
        )
        raise InvalidCredentialsError

    password_ok = security.verify_password(user.password_hash, password)

    if not password_ok or not user.is_active:
        record_rate_limit_event(
            db,
            action=RateLimitAction.LOGIN,
            identifier=normalized,
            ip_address=ip_address,
            success=False,
            hmac_key=hmac_key,
            now=now,
        )
        raise InvalidCredentialsError

    if security.needs_rehash(user.password_hash):
        user.password_hash = security.hash_password(password)

    user.last_login_at = now
    record_rate_limit_event(
        db,
        action=RateLimitAction.LOGIN,
        identifier=normalized,
        ip_address=ip_address,
        success=True,
        hmac_key=hmac_key,
        now=now,
    )
    return user


def create_session(
    db: Session,
    *,
    user: AuthUser,
    ttl_minutes: int,
    now_fn: NowFn = default_now,
) -> AuthenticatedSession:
    now = now_fn()
    token = security.generate_opaque_token()
    session_row = AuthSession(
        user_id=user.id,
        session_hash=security.hash_opaque_token(token),
        created_at=now,
        expires_at=now + timedelta(minutes=ttl_minutes),
        last_seen_at=now,
    )
    db.add(session_row)
    db.flush()
    return AuthenticatedSession(
        user_id=user.id,
        identifier=user.identifier,
        token=token,
        expires_at=session_row.expires_at,
    )


def resolve_session(db: Session, *, token: str, now_fn: NowFn = default_now) -> AuthUser | None:
    token_hash = security.hash_opaque_token(token)
    session_row = db.execute(
        select(AuthSession).where(AuthSession.session_hash == token_hash)
    ).scalar_one_or_none()
    if session_row is None:
        return None

    now = now_fn()
    if session_row.revoked_at is not None or session_row.expires_at <= now:
        return None

    user = db.get(AuthUser, session_row.user_id)
    if user is None or not user.is_active:
        return None

    session_row.last_seen_at = now
    return user


def revoke_session(db: Session, *, token: str, now_fn: NowFn = default_now) -> None:
    token_hash = security.hash_opaque_token(token)
    session_row = db.execute(
        select(AuthSession).where(AuthSession.session_hash == token_hash)
    ).scalar_one_or_none()
    if session_row is not None and session_row.revoked_at is None:
        session_row.revoked_at = now_fn()


def revoke_all_sessions_for_user(
    db: Session, *, user_id: uuid.UUID, now_fn: NowFn = default_now
) -> None:
    db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=now_fn())
    )


# --- owner bootstrap (admin-only, not a substitute for public registration) -


def create_owner(db: Session, *, identifier: str, password: str) -> AuthUser:
    normalized = normalize_identifier(identifier)
    if not (MIN_IDENTIFIER_LENGTH <= len(normalized) <= MAX_IDENTIFIER_LENGTH):
        raise InvalidOwnerDataError(
            f"El identificador debe tener entre {MIN_IDENTIFIER_LENGTH} y "
            f"{MAX_IDENTIFIER_LENGTH} caracteres."
        )
    if not (MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH):
        raise InvalidOwnerDataError(
            f"La contraseña debe tener entre {MIN_PASSWORD_LENGTH} y "
            f"{MAX_PASSWORD_LENGTH} caracteres."
        )

    existing = db.execute(
        select(AuthUser).where(AuthUser.identifier == normalized)
    ).scalar_one_or_none()
    if existing is not None:
        raise OwnerAlreadyExistsError("La propietaria ya existe.")

    # Trusted local bootstrap: created active immediately, with its
    # administrative origin recorded for audit purposes.
    user = AuthUser(
        identifier=normalized,
        password_hash=security.hash_password(password),
        is_active=True,
        created_via=UserOrigin.ADMIN_BOOTSTRAP,
    )
    db.add(user)
    db.flush()
    return user


def _issue_reset_token(db: Session, *, user_id: uuid.UUID, ttl_minutes: int, now: datetime) -> str:
    token = security.generate_opaque_token()
    db.add(
        AuthPasswordResetToken(
            user_id=user_id,
            token_hash=security.hash_opaque_token(token),
            created_at=now,
            expires_at=now + timedelta(minutes=ttl_minutes),
        )
    )
    db.flush()
    return token


def _invalidate_pending_reset_tokens(db: Session, *, user_id: uuid.UUID, now: datetime) -> None:
    db.execute(
        update(AuthPasswordResetToken)
        .where(
            AuthPasswordResetToken.user_id == user_id,
            AuthPasswordResetToken.consumed_at.is_(None),
        )
        .values(consumed_at=now)
    )


# --- registration --------------------------------------------------------------


def register_user(
    db: Session,
    *,
    email: str,
    password: str,
    ip_address: str,
    hmac_key: bytes,
    now_fn: NowFn = default_now,
) -> None:
    """Always completes without signalling whether the email was already
    registered — the public response (status + body) must stay identical in
    every case to avoid account enumeration.

    There is no email verification step: an account created here is active
    immediately and can log in immediately. Exactly one external, uniform
    rate-limit bucket (RateLimitAction.REGISTER) gates every call, checked
    before the account is looked up, with an identical threshold regardless
    of what the lookup will find."""
    if not (MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH):
        raise InvalidRegistrationDataError(
            f"La contraseña debe tener entre {MIN_PASSWORD_LENGTH} y "
            f"{MAX_PASSWORD_LENGTH} caracteres."
        )
    normalized = _validate_and_normalize_email(email)
    now = now_fn()

    if is_rate_limited(
        db,
        action=RateLimitAction.REGISTER,
        identifier=normalized,
        ip_address=ip_address,
        hmac_key=hmac_key,
        now_fn=now_fn,
    ):
        raise RateLimitedError

    # Hash the real submitted password unconditionally, before resolving the
    # identity race. This equalizes the cost of the "brand new account" and
    # "already registered" branches without a separate dummy hash, bounded by
    # the REGISTER rate limit just above (see design notes: no indiscriminate
    # extra Argon2 work, and this one is never skippable/free either way).
    password_hash = security.hash_password(password)

    existing = db.execute(
        select(AuthUser).where(AuthUser.identifier == normalized)
    ).scalar_one_or_none()
    record_rate_limit_event(
        db,
        action=RateLimitAction.REGISTER,
        identifier=normalized,
        ip_address=ip_address,
        success=True,
        hmac_key=hmac_key,
        now=now,
    )

    if existing is not None:
        # Already registered: safe no-op, identical public response — never
        # reveals that the account exists.
        return

    user = AuthUser(
        identifier=normalized,
        password_hash=password_hash,
        is_active=True,
        created_via=UserOrigin.SELF_REGISTRATION,
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        # Lost a concurrent registration race for the same identifier —
        # PostgreSQL's unique constraint is the real guarantee here, not
        # the SELECT above. Treat exactly like "already registered".
        db.rollback()


# --- password reset ------------------------------------------------------------


def request_password_reset(
    db: Session,
    *,
    email: str,
    email_sender: EmailSender,
    frontend_origin: str,
    reset_ttl_minutes: int,
    ip_address: str,
    hmac_key: bytes,
    now_fn: NowFn = default_now,
) -> None:
    """Always completes without signalling whether the account exists. Does
    not claim perfect constant-time behaviour end-to-end: SMTP delivery
    itself still takes measurably longer than the no-op branch. What this
    equalizes is the *local* work (rate-limit bookkeeping + a comparable-cost
    placeholder operation), not the network leg to the mail transport.

    If email_sender.send() raises EmailDeliveryError, that failure is caught
    and degraded gracefully (sanitized log, same generic ack) — it is not
    fail-closed. The reset token itself is still committed to PostgreSQL
    (fail-closed: an unexpected exception there rolls back and surfaces as a
    500), so the account is never left claiming a delivery that did not
    happen, and calling this again reissues a fresh token and invalidates the
    previous one — no unbounded pile-up of pending tokens from repeated
    send failures."""
    normalized = normalize_identifier(email)
    now = now_fn()

    if is_rate_limited(
        db,
        action=RateLimitAction.PASSWORD_RESET_REQUEST,
        identifier=normalized,
        ip_address=ip_address,
        hmac_key=hmac_key,
        now_fn=now_fn,
    ):
        raise RateLimitedError

    user = db.execute(
        select(AuthUser).where(AuthUser.identifier == normalized)
    ).scalar_one_or_none()
    record_rate_limit_event(
        db,
        action=RateLimitAction.PASSWORD_RESET_REQUEST,
        identifier=normalized,
        ip_address=ip_address,
        success=True,
        hmac_key=hmac_key,
        now=now,
    )

    if user is None:
        # Comparable-cost placeholder: the same lightweight token-generation
        # and hashing work the real path performs, then discarded. Not an
        # Argon2 hash — indiscriminate expensive hashing on every anonymous
        # request would itself be a DoS vector (see design notes).
        security.hash_opaque_token(security.generate_opaque_token())
        return

    _invalidate_pending_reset_tokens(db, user_id=user.id, now=now)
    token = _issue_reset_token(db, user_id=user.id, ttl_minutes=reset_ttl_minutes, now=now)
    link = f"{frontend_origin}/reset-password#token={token}"
    try:
        email_sender.send(
            EmailMessage(
                to=normalized,
                subject="Restablece tu contraseña en Freyja 2.0",
                text_body=(
                    "Solicitaste restablecer tu contraseña de Freyja 2.0:\n\n"
                    f"{link}\n\nSi no fuiste tú, ignora este mensaje: tu contraseña "
                    "actual sigue siendo válida."
                ),
            )
        )
    except EmailDeliveryError:
        _auth_logger.error("password_reset_email_send_failed")


def reset_password(
    db: Session, *, token: str, new_password: str, now_fn: NowFn = default_now
) -> None:
    if not (MIN_PASSWORD_LENGTH <= len(new_password) <= MAX_PASSWORD_LENGTH):
        raise InvalidRegistrationDataError(
            f"La contraseña debe tener entre {MIN_PASSWORD_LENGTH} y "
            f"{MAX_PASSWORD_LENGTH} caracteres."
        )

    now = now_fn()
    token_hash = security.hash_opaque_token(token)
    row = db.execute(
        select(AuthPasswordResetToken).where(AuthPasswordResetToken.token_hash == token_hash)
    ).scalar_one_or_none()

    if row is None or row.consumed_at is not None:
        raise TokenInvalidError
    if row.expires_at <= now:
        raise TokenExpiredError

    user = db.get(AuthUser, row.user_id)
    if user is None:
        raise TokenInvalidError

    user.password_hash = security.hash_password(new_password)
    row.consumed_at = now
    db.flush()

    _invalidate_pending_reset_tokens(db, user_id=user.id, now=now)
    revoke_all_sessions_for_user(db, user_id=user.id, now_fn=now_fn)
    _auth_logger.info("password_reset_completed", extra={"user_id": str(user.id)})
