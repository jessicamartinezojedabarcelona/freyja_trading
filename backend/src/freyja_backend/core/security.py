import hashlib
import hmac
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from argon2.low_level import Type

# Explicit, centralized Argon2id cost parameters (OWASP minimum recommendation).
# Any change here requires a deliberate decision; existing hashes are detected
# for rehash via `needs_rehash` and upgraded transparently on next successful login.
_ARGON2_TIME_COST = 2
_ARGON2_MEMORY_COST_KIB = 19 * 1024
_ARGON2_PARALLELISM = 1

_password_hasher = PasswordHasher(
    time_cost=_ARGON2_TIME_COST,
    memory_cost=_ARGON2_MEMORY_COST_KIB,
    parallelism=_ARGON2_PARALLELISM,
    type=Type.ID,
)

SESSION_TOKEN_BYTES = 32
CSRF_TOKEN_BYTES = 32


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False
    except Exception:
        # Malformed/foreign hash string: fail closed, never propagate details.
        return False


def needs_rehash(password_hash: str) -> bool:
    return _password_hasher.check_needs_rehash(password_hash)


# Precomputed at import time so the "user not found" branch of login can run a
# real Argon2 verification against a fixed dummy hash, equalizing response
# timing with the "wrong password" branch and avoiding user-enumeration via
# timing side channels.
DUMMY_PASSWORD_HASH = hash_password("freyja-timing-safety-dummy-password")


def generate_opaque_token(n_bytes: int = SESSION_TOKEN_BYTES) -> str:
    return secrets.token_urlsafe(n_bytes)


def hash_opaque_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# --- Rate-limiting HMAC key -------------------------------------------------
#
# Low-entropy values (emails, IP addresses) must never be rate-limit-keyed
# with a plain hash: a plain SHA-256 of a common email is trivially reversed
# via a dictionary/rainbow lookup. HMAC with a secret key that never touches
# PostgreSQL or Git closes that hole. In production the key is a real,
# operator-managed secret (required — see core.config). Outside production,
# generating a random key once per process is deliberate: rate-limit state is
# meaningless across restarts anyway, so there is nothing to persist, and no
# hardcoded key ever needs to exist in source.
_ephemeral_rate_limit_key: bytes | None = None


def _get_ephemeral_rate_limit_key() -> bytes:
    global _ephemeral_rate_limit_key
    if _ephemeral_rate_limit_key is None:
        _ephemeral_rate_limit_key = secrets.token_bytes(32)
    return _ephemeral_rate_limit_key


def resolve_rate_limit_hmac_key(configured_key: str | None) -> bytes:
    if configured_key:
        return configured_key.encode("utf-8")
    return _get_ephemeral_rate_limit_key()


def hmac_key(value: str, key: bytes) -> str:
    return hmac.new(key, value.encode("utf-8"), hashlib.sha256).hexdigest()
