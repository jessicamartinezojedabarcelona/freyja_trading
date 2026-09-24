from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from freyja_backend.application import auth_service
from freyja_backend.core.email import InMemoryEmailSender
from freyja_backend.db.models import AuthPasswordResetToken, AuthUser, RateLimitAction

EMAIL = "newuser@freyja-test.dev"
PASSWORD = "correct-horse-battery-staple"
FRONTEND_ORIGIN = "http://localhost:4200"
RESET_TTL_MINUTES = 30
CLIENT_IP = "203.0.113.10"
HMAC_KEY = b"test-only-hmac-key-not-a-real-secret"


class _Clock:
    def __init__(self, start: datetime) -> None:
        self._now = start

    def __call__(self) -> datetime:
        return self._now

    def advance(self, delta: timedelta) -> None:
        self._now += delta


@pytest.fixture
def clock() -> _Clock:
    return _Clock(datetime(2026, 1, 1, tzinfo=UTC))


def _create_owner(db: Session, email: str = EMAIL) -> None:
    # The only supported way to provision an account (AUTH-PRIVATE-ACCESS-001):
    # the administrative bootstrap. There is no public registration.
    auth_service.create_owner(db, identifier=email, password=PASSWORD)


def _authenticate(
    db: Session, clock: _Clock, *, email: str = EMAIL, password: str = PASSWORD
) -> AuthUser:
    return auth_service.authenticate(
        db,
        identifier=email,
        password=password,
        ip_address=CLIENT_IP,
        hmac_key=HMAC_KEY,
        now_fn=clock,
    )


def _request_reset(
    db: Session, sender: InMemoryEmailSender, clock: _Clock, email: str = EMAIL
) -> None:
    auth_service.request_password_reset(
        db,
        email=email,
        email_sender=sender,
        frontend_origin=FRONTEND_ORIGIN,
        reset_ttl_minutes=RESET_TTL_MINUTES,
        ip_address=CLIENT_IP,
        hmac_key=HMAC_KEY,
        now_fn=clock,
    )


def _extract_token_from_link(link_text: str, path: str) -> str:
    marker = f"{path}#token="
    start = link_text.index(marker) + len(marker)
    end = link_text.find("\n", start)
    return link_text[start:end] if end != -1 else link_text[start:]


# --- forgot password ----------------------------------------------------------


def test_forgot_password_for_existing_account_sends_email(
    db_session: Session, email_sender: InMemoryEmailSender, clock: _Clock
) -> None:
    _create_owner(db_session)

    _request_reset(db_session, email_sender, clock)

    assert len(email_sender.sent_messages) == 1
    assert "/reset-password#token=" in email_sender.sent_messages[0].text_body


def test_forgot_password_for_unknown_account_sends_nothing_but_does_not_raise(
    db_session: Session, email_sender: InMemoryEmailSender, clock: _Clock
) -> None:
    _request_reset(db_session, email_sender, clock, email="nobody@freyja-test.dev")
    assert email_sender.sent_messages == []


def test_forgot_password_is_rate_limited_after_max_requests(
    db_session: Session, email_sender: InMemoryEmailSender, clock: _Clock
) -> None:
    _create_owner(db_session)

    limit = auth_service.RATE_LIMITS[RateLimitAction.PASSWORD_RESET_REQUEST][0]
    for _ in range(limit):
        _request_reset(db_session, email_sender, clock)
    assert len(email_sender.sent_messages) == limit

    with pytest.raises(auth_service.RateLimitedError):
        _request_reset(db_session, email_sender, clock)
    assert len(email_sender.sent_messages) == limit


# --- reset password -------------------------------------------------------------


def _request_reset_and_extract_token(
    db: Session, sender: InMemoryEmailSender, clock: _Clock
) -> str:
    _request_reset(db, sender, clock)
    return _extract_token_from_link(sender.sent_messages[-1].text_body, "/reset-password")


def test_reset_password_changes_password_and_revokes_sessions(
    db_session: Session, email_sender: InMemoryEmailSender, clock: _Clock
) -> None:
    _create_owner(db_session)

    user = _authenticate(db_session, clock)
    session = auth_service.create_session(db_session, user=user, ttl_minutes=60, now_fn=clock)
    assert auth_service.resolve_session(db_session, token=session.token, now_fn=clock) is not None

    reset_token = _request_reset_and_extract_token(db_session, email_sender, clock)
    new_password = "a-brand-new-strong-password"
    auth_service.reset_password(
        db_session, token=reset_token, new_password=new_password, now_fn=clock
    )

    # old password no longer works
    with pytest.raises(auth_service.InvalidCredentialsError):
        _authenticate(db_session, clock)

    # new password works
    refreshed = _authenticate(db_session, clock, password=new_password)
    assert refreshed.identifier == EMAIL

    # previous session was revoked
    assert auth_service.resolve_session(db_session, token=session.token, now_fn=clock) is None


def test_reset_password_invalidates_other_pending_reset_tokens(
    db_session: Session, email_sender: InMemoryEmailSender, clock: _Clock
) -> None:
    _create_owner(db_session)

    first_reset_token = _request_reset_and_extract_token(db_session, email_sender, clock)
    second_reset_token = _request_reset_and_extract_token(db_session, email_sender, clock)

    auth_service.reset_password(
        db_session, token=second_reset_token, new_password="second-new-password-123", now_fn=clock
    )

    with pytest.raises(auth_service.TokenInvalidError):
        auth_service.reset_password(
            db_session, token=first_reset_token, new_password="another-password-456", now_fn=clock
        )


def test_reset_password_rejects_unknown_token(db_session: Session, clock: _Clock) -> None:
    with pytest.raises(auth_service.TokenInvalidError):
        auth_service.reset_password(
            db_session, token="not-a-real-token", new_password="a-new-password-123", now_fn=clock
        )


def test_reset_password_rejects_expired_token(
    db_session: Session, email_sender: InMemoryEmailSender, clock: _Clock
) -> None:
    _create_owner(db_session)
    reset_token = _request_reset_and_extract_token(db_session, email_sender, clock)

    clock.advance(timedelta(minutes=RESET_TTL_MINUTES, seconds=1))
    with pytest.raises(auth_service.TokenExpiredError):
        auth_service.reset_password(
            db_session, token=reset_token, new_password="a-new-password-123", now_fn=clock
        )


def test_reset_password_rejects_reused_token(
    db_session: Session, email_sender: InMemoryEmailSender, clock: _Clock
) -> None:
    _create_owner(db_session)
    reset_token = _request_reset_and_extract_token(db_session, email_sender, clock)

    auth_service.reset_password(
        db_session, token=reset_token, new_password="a-new-password-123", now_fn=clock
    )
    with pytest.raises(auth_service.TokenInvalidError):
        auth_service.reset_password(
            db_session, token=reset_token, new_password="yet-another-password-789", now_fn=clock
        )


def test_reset_password_rejects_short_new_password(
    db_session: Session, email_sender: InMemoryEmailSender, clock: _Clock
) -> None:
    _create_owner(db_session)
    reset_token = _request_reset_and_extract_token(db_session, email_sender, clock)

    with pytest.raises(auth_service.InvalidRegistrationDataError):
        auth_service.reset_password(
            db_session, token=reset_token, new_password="short", now_fn=clock
        )


def test_no_usable_reset_token_stored_in_postgres(
    db_session: Session, email_sender: InMemoryEmailSender, clock: _Clock
) -> None:
    _create_owner(db_session)
    reset_token = _request_reset_and_extract_token(db_session, email_sender, clock)

    row = db_session.execute(select(AuthPasswordResetToken)).scalar_one()
    assert reset_token not in row.token_hash
    assert row.token_hash != reset_token


def test_password_reset_completed_log_is_sanitized(
    db_session: Session,
    email_sender: InMemoryEmailSender,
    clock: _Clock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _create_owner(db_session)
    reset_token = _request_reset_and_extract_token(db_session, email_sender, clock)
    new_password = "a-brand-new-strong-password"

    with caplog.at_level("INFO", logger="freyja_backend.auth"):
        auth_service.reset_password(
            db_session, token=reset_token, new_password=new_password, now_fn=clock
        )

    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.message == "password_reset_completed"
    assert new_password not in caplog.text
    assert reset_token not in caplog.text
    assert EMAIL not in caplog.text
