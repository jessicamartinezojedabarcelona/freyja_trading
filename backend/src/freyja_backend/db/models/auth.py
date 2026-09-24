import enum
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from freyja_backend.db.base import Base


class UserOrigin(enum.StrEnum):
    """Audit-only provenance of an auth_users row. Never confers permissions
    or roles by itself."""

    SELF_REGISTRATION = "SELF_REGISTRATION"
    ADMIN_BOOTSTRAP = "ADMIN_BOOTSTRAP"


class RateLimitAction(enum.StrEnum):
    LOGIN = "LOGIN"
    REGISTER = "REGISTER"
    PASSWORD_RESET_REQUEST = "PASSWORD_RESET_REQUEST"


class AuthUser(Base):
    __tablename__ = "auth_users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    identifier: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_via: Mapped[UserOrigin] = mapped_column(
        Enum(UserOrigin, name="auth_user_origin", native_enum=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    sessions: Mapped[list["AuthSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"AuthUser(id={self.id!r}, identifier={self.identifier!r})"


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("auth_users.id", ondelete="CASCADE"), nullable=False
    )
    session_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    user: Mapped[AuthUser] = relationship(back_populates="sessions")

    def __repr__(self) -> str:
        return f"AuthSession(id={self.id!r}, user_id={self.user_id!r})"


class AuthRateLimitEvent(Base):
    """Append-only rate-limiting ledger shared by every throttled action.
    Never stores plaintext emails/IPs/passwords/tokens/cookies/headers/request
    bodies/full user-agents — only HMAC-keyed fingerprints of the identifier
    and the origin, so the table itself cannot be dictionary-attacked to
    recover a real email or IP even if it were ever exposed."""

    __tablename__ = "auth_rate_limit_events"
    __table_args__ = (
        Index(
            "ix_auth_rate_limit_events_action_identifier", "action", "identifier_key", "created_at"
        ),
        Index("ix_auth_rate_limit_events_action_origin", "action", "origin_key", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    action: Mapped[RateLimitAction] = mapped_column(
        Enum(RateLimitAction, name="auth_rate_limit_action", native_enum=True), nullable=False
    )
    identifier_key: Mapped[str] = mapped_column(String(64), nullable=False)
    origin_key: Mapped[str] = mapped_column(String(64), nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"AuthRateLimitEvent(action={self.action!r})"


class AuthPasswordResetToken(Base):
    __tablename__ = "auth_password_reset_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("auth_users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:
        return f"AuthPasswordResetToken(id={self.id!r}, user_id={self.user_id!r})"
