from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from freyja_backend.application import auth_service
from freyja_backend.db.models import AuthRateLimitEvent, AuthUser, RateLimitAction

OWNER_IDENTIFIER = "owner@example.test"
OWNER_PASSWORD = "correct-horse-battery-staple"
CLIENT_IP = "203.0.113.10"
HMAC_KEY = b"test-only-hmac-key-not-a-real-secret"

MAX_LOGIN_FAILURES_PER_IDENTIFIER = auth_service.RATE_LIMITS[RateLimitAction.LOGIN][0]
MAX_LOGIN_FAILURES_PER_IP = auth_service.RATE_LIMITS[RateLimitAction.LOGIN][1]


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


@pytest.fixture
def owner(db_session: Session) -> None:
    auth_service.create_owner(db_session, identifier=OWNER_IDENTIFIER, password=OWNER_PASSWORD)
    db_session.commit()


def _authenticate(
    db_session: Session,
    clock: _Clock,
    *,
    identifier: str = OWNER_IDENTIFIER,
    password: str = OWNER_PASSWORD,
    ip_address: str = CLIENT_IP,
) -> AuthUser:
    return auth_service.authenticate(
        db_session,
        identifier=identifier,
        password=password,
        ip_address=ip_address,
        hmac_key=HMAC_KEY,
        now_fn=clock,
    )


def test_normalize_identifier_strips_and_lowercases() -> None:
    assert auth_service.normalize_identifier("  Owner@Example.TEST  ") == "owner@example.test"


def test_create_owner_rejects_short_password(db_session: Session) -> None:
    with pytest.raises(auth_service.InvalidOwnerDataError):
        auth_service.create_owner(db_session, identifier="a-new-owner", password="short")


@pytest.mark.usefixtures("owner")
def test_create_owner_rejects_duplicate_identifier(db_session: Session) -> None:
    with pytest.raises(auth_service.OwnerAlreadyExistsError):
        auth_service.create_owner(
            db_session, identifier=OWNER_IDENTIFIER, password="another-long-password"
        )


@pytest.mark.usefixtures("owner")
def test_create_owner_never_stores_plaintext_password(db_session: Session) -> None:
    user = db_session.execute(
        select(AuthUser).where(AuthUser.identifier == OWNER_IDENTIFIER)
    ).scalar_one()
    assert OWNER_PASSWORD not in user.password_hash
    assert user.password_hash.startswith("$argon2id$")


@pytest.mark.usefixtures("owner")
def test_authenticate_succeeds_with_correct_credentials(db_session: Session, clock: _Clock) -> None:
    user = _authenticate(db_session, clock)
    assert user.identifier == OWNER_IDENTIFIER
    assert user.last_login_at == clock()


@pytest.mark.usefixtures("owner")
def test_authenticate_fails_with_wrong_password(db_session: Session, clock: _Clock) -> None:
    with pytest.raises(auth_service.InvalidCredentialsError):
        _authenticate(db_session, clock, password="wrong-password")


def test_authenticate_fails_with_unknown_identifier(db_session: Session, clock: _Clock) -> None:
    with pytest.raises(auth_service.InvalidCredentialsError):
        _authenticate(
            db_session, clock, identifier="nobody@example.test", password="whatever-password"
        )


@pytest.mark.usefixtures("owner")
def test_authenticate_fails_for_inactive_user(db_session: Session, clock: _Clock) -> None:
    user = db_session.execute(
        select(AuthUser).where(AuthUser.identifier == OWNER_IDENTIFIER)
    ).scalar_one()
    user.is_active = False
    db_session.flush()

    with pytest.raises(auth_service.InvalidCredentialsError):
        _authenticate(db_session, clock)


@pytest.mark.usefixtures("owner")
def test_rate_limit_blocks_after_max_failures_per_identifier(
    db_session: Session, clock: _Clock
) -> None:
    for _ in range(MAX_LOGIN_FAILURES_PER_IDENTIFIER):
        with pytest.raises(auth_service.InvalidCredentialsError):
            _authenticate(db_session, clock, password="wrong-password")

    with pytest.raises(auth_service.RateLimitedError):
        _authenticate(db_session, clock)


@pytest.mark.usefixtures("owner")
def test_rate_limit_resets_after_window_elapses(db_session: Session, clock: _Clock) -> None:
    for _ in range(MAX_LOGIN_FAILURES_PER_IDENTIFIER):
        with pytest.raises(auth_service.InvalidCredentialsError):
            _authenticate(db_session, clock, password="wrong-password")

    clock.advance(auth_service.RATE_LIMIT_WINDOW + timedelta(seconds=1))

    user = _authenticate(db_session, clock)
    assert user.identifier == OWNER_IDENTIFIER


@pytest.mark.usefixtures("owner")
def test_rate_limit_blocks_after_max_failures_per_ip_across_identifiers(
    db_session: Session, clock: _Clock
) -> None:
    for i in range(MAX_LOGIN_FAILURES_PER_IP):
        with pytest.raises(auth_service.InvalidCredentialsError):
            _authenticate(
                db_session,
                clock,
                identifier=f"unknown-user-{i}@example.test",
                password="wrong-password",
            )

    with pytest.raises(auth_service.RateLimitedError):
        _authenticate(db_session, clock)


@pytest.mark.usefixtures("owner")
def test_create_and_resolve_session_round_trip(db_session: Session, clock: _Clock) -> None:
    user = _authenticate(db_session, clock)
    session = auth_service.create_session(db_session, user=user, ttl_minutes=60, now_fn=clock)

    resolved = auth_service.resolve_session(db_session, token=session.token, now_fn=clock)
    assert resolved is not None
    assert resolved.identifier == OWNER_IDENTIFIER


@pytest.mark.usefixtures("owner")
def test_each_login_creates_a_fresh_unpredictable_session_token(
    db_session: Session, clock: _Clock
) -> None:
    user = _authenticate(db_session, clock)
    first = auth_service.create_session(db_session, user=user, ttl_minutes=60, now_fn=clock)
    second = auth_service.create_session(db_session, user=user, ttl_minutes=60, now_fn=clock)

    assert first.token != second.token
    assert auth_service.resolve_session(db_session, token=first.token, now_fn=clock) is not None
    assert auth_service.resolve_session(db_session, token=second.token, now_fn=clock) is not None


def test_resolve_session_returns_none_for_unknown_token(db_session: Session, clock: _Clock) -> None:
    assert auth_service.resolve_session(db_session, token="not-a-real-token", now_fn=clock) is None


@pytest.mark.usefixtures("owner")
def test_resolve_session_returns_none_after_expiry(db_session: Session, clock: _Clock) -> None:
    user = _authenticate(db_session, clock)
    session = auth_service.create_session(db_session, user=user, ttl_minutes=10, now_fn=clock)

    clock.advance(timedelta(minutes=11))

    assert auth_service.resolve_session(db_session, token=session.token, now_fn=clock) is None


@pytest.mark.usefixtures("owner")
def test_resolve_session_returns_none_after_revocation(db_session: Session, clock: _Clock) -> None:
    user = _authenticate(db_session, clock)
    session = auth_service.create_session(db_session, user=user, ttl_minutes=60, now_fn=clock)

    auth_service.revoke_session(db_session, token=session.token, now_fn=clock)

    assert auth_service.resolve_session(db_session, token=session.token, now_fn=clock) is None


@pytest.mark.usefixtures("owner")
def test_revoke_session_is_idempotent(db_session: Session, clock: _Clock) -> None:
    user = _authenticate(db_session, clock)
    session = auth_service.create_session(db_session, user=user, ttl_minutes=60, now_fn=clock)

    auth_service.revoke_session(db_session, token=session.token, now_fn=clock)
    auth_service.revoke_session(db_session, token=session.token, now_fn=clock)  # no error

    assert auth_service.resolve_session(db_session, token=session.token, now_fn=clock) is None


def test_revoke_session_on_unknown_token_does_not_raise(db_session: Session, clock: _Clock) -> None:
    auth_service.revoke_session(db_session, token="not-a-real-token", now_fn=clock)


def test_rate_limit_events_never_store_email_or_ip_in_clear(
    db_session: Session, clock: _Clock, caplog: pytest.LogCaptureFixture
) -> None:
    """auth_rate_limit_events must only ever contain HMAC-keyed fingerprints:
    a real-looking email and IP must never appear in the persisted rows, nor
    in any log/error/response produced along the way."""
    sensitive_email = "sensitive-user-do-not-leak@freyja-test.dev"
    sensitive_ip = "198.51.100.77"

    with (
        caplog.at_level("DEBUG"),
        pytest.raises(auth_service.InvalidCredentialsError) as excinfo,
    ):
        auth_service.authenticate(
            db_session,
            identifier=sensitive_email,
            password="wrong-password",
            ip_address=sensitive_ip,
            hmac_key=HMAC_KEY,
            now_fn=clock,
        )

    rows = db_session.execute(select(AuthRateLimitEvent)).scalars().all()
    assert rows, "expected at least one recorded rate-limit event"

    for row in rows:
        # Only these five columns exist at all — asserting the exact set
        # guards against a future column silently adding a raw PII field.
        assert set(row.__table__.columns.keys()) == {
            "id",
            "action",
            "identifier_key",
            "origin_key",
            "success",
            "created_at",
        }
        assert sensitive_email not in row.identifier_key
        assert sensitive_email not in row.origin_key
        assert sensitive_ip not in row.identifier_key
        assert sensitive_ip not in row.origin_key

    assert sensitive_email not in str(excinfo.value)
    assert sensitive_ip not in str(excinfo.value)
    assert sensitive_email not in caplog.text
    assert sensitive_ip not in caplog.text
