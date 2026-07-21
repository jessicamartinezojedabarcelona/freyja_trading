from collections.abc import Iterator
from functools import lru_cache

from fastapi import HTTPException
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from freyja_backend.core.database import create_database_engine
from freyja_backend.db.session import create_session_factory

_engine_override: Engine | None = None


@lru_cache
def _default_engine() -> Engine:
    return create_database_engine()


def _session_factory() -> sessionmaker[Session]:
    engine = _engine_override if _engine_override is not None else _default_engine()
    return create_session_factory(engine)


def set_engine_override(engine: Engine | None) -> None:
    """Test-only hook: point the API layer's DB dependency at a different engine."""
    global _engine_override
    _engine_override = engine


def get_db() -> Iterator[Session]:
    """Request-scoped session. `HTTPException` is a deliberate, valid response
    (401/403/429/...), not a data-integrity failure: writes made before raising
    it (e.g. recording a failed login attempt) must still be committed. Only an
    unexpected exception rolls the transaction back."""
    session = _session_factory()()
    try:
        yield session
    except HTTPException:
        session.commit()
        raise
    except Exception:
        session.rollback()
        raise
    else:
        session.commit()
    finally:
        session.close()
