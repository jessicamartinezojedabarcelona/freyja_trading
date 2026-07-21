import uuid

from freyja_backend.db.models import AuthSession, AuthUser

PASSWORD_HASH = "$argon2id$v=19$m=19456,t=2,p=1$somesaltbase64$somehashbase64"


def test_auth_user_repr_never_includes_password_hash() -> None:
    user = AuthUser(id=uuid.uuid4(), identifier="owner@example.test", password_hash=PASSWORD_HASH)
    rendered = repr(user)
    assert PASSWORD_HASH not in rendered
    assert "password_hash" not in rendered
    assert "owner@example.test" in rendered


def test_auth_session_repr_never_includes_session_hash() -> None:
    session_hash = "a" * 64
    session = AuthSession(id=uuid.uuid4(), user_id=uuid.uuid4(), session_hash=session_hash)
    rendered = repr(session)
    assert session_hash not in rendered
    assert "session_hash" not in rendered
