from freyja_backend.core import security


def test_hash_password_produces_argon2id_hash() -> None:
    hashed = security.hash_password("a-reasonably-long-password")
    assert hashed.startswith("$argon2id$")


def test_verify_password_accepts_correct_password() -> None:
    hashed = security.hash_password("correct-horse-battery-staple")
    assert security.verify_password(hashed, "correct-horse-battery-staple") is True


def test_verify_password_rejects_wrong_password() -> None:
    hashed = security.hash_password("correct-horse-battery-staple")
    assert security.verify_password(hashed, "wrong-password") is False


def test_verify_password_fails_closed_on_malformed_hash() -> None:
    assert security.verify_password("not-a-real-hash", "anything") is False


def test_needs_rehash_false_for_current_parameters() -> None:
    hashed = security.hash_password("correct-horse-battery-staple")
    assert security.needs_rehash(hashed) is False


def test_generate_opaque_token_is_unique_and_url_safe() -> None:
    first = security.generate_opaque_token()
    second = security.generate_opaque_token()
    assert first != second
    assert len(first) > 20


def test_hash_opaque_token_is_deterministic_sha256_hex() -> None:
    token = "some-opaque-token-value"
    first = security.hash_opaque_token(token)
    second = security.hash_opaque_token(token)
    assert first == second
    assert len(first) == 64
    assert all(c in "0123456789abcdef" for c in first)


def test_hash_opaque_token_differs_from_raw_token() -> None:
    token = security.generate_opaque_token()
    assert security.hash_opaque_token(token) != token


def test_dummy_password_hash_is_a_valid_argon2id_hash() -> None:
    assert security.DUMMY_PASSWORD_HASH.startswith("$argon2id$")
    assert security.verify_password(
        security.DUMMY_PASSWORD_HASH, "freyja-timing-safety-dummy-password"
    )
