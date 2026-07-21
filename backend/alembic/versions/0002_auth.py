"""auth

Revision ID: 0002_auth
Revises: 0001_initial
Create Date: 2026-07-20

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_auth"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_USER_ORIGIN_VALUES = ("SELF_REGISTRATION", "ADMIN_BOOTSTRAP")
_RATE_LIMIT_ACTION_VALUES = (
    "LOGIN",
    "REGISTER",
    "RESEND_VERIFICATION",
    "PASSWORD_RESET_REQUEST",
)


def upgrade() -> None:
    # Create the native enum types explicitly (once), then reference them with
    # create_type=False on the columns below — otherwise SQLAlchemy's
    # postgresql.ENUM auto-creation (triggered a second time by attaching the
    # type to a table column) collides with the explicit create() and fails
    # with "type already exists".
    user_origin_create = postgresql.ENUM(*_USER_ORIGIN_VALUES, name="auth_user_origin")
    rate_limit_action_create = postgresql.ENUM(
        *_RATE_LIMIT_ACTION_VALUES, name="auth_rate_limit_action"
    )
    user_origin_create.create(op.get_bind(), checkfirst=False)
    rate_limit_action_create.create(op.get_bind(), checkfirst=False)

    user_origin = postgresql.ENUM(*_USER_ORIGIN_VALUES, name="auth_user_origin", create_type=False)
    rate_limit_action = postgresql.ENUM(
        *_RATE_LIMIT_ACTION_VALUES, name="auth_rate_limit_action", create_type=False
    )

    op.create_table(
        "auth_users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("identifier", sa.String(length=64), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_via", user_origin, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("identifier", name="uq_auth_users_identifier"),
    )
    op.create_index("ix_auth_users_identifier", "auth_users", ["identifier"])

    op.create_table(
        "auth_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["auth_users.id"], name="fk_auth_sessions_user_id", ondelete="CASCADE"
        ),
        sa.UniqueConstraint("session_hash", name="uq_auth_sessions_session_hash"),
    )
    op.create_index("ix_auth_sessions_session_hash", "auth_sessions", ["session_hash"])
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])

    # Append-only rate-limiting ledger shared by every throttled action.
    # Stores only HMAC-keyed fingerprints of the identifier/origin (see
    # core.security.hmac_key) — never the plaintext email, IP, password,
    # token, cookie, header, or request body.
    op.create_table(
        "auth_rate_limit_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("action", rate_limit_action, nullable=False),
        sa.Column("identifier_key", sa.String(length=64), nullable=False),
        sa.Column("origin_key", sa.String(length=64), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_auth_rate_limit_events_action_identifier",
        "auth_rate_limit_events",
        ["action", "identifier_key", "created_at"],
    )
    op.create_index(
        "ix_auth_rate_limit_events_action_origin",
        "auth_rate_limit_events",
        ["action", "origin_key", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_auth_rate_limit_events_action_origin", table_name="auth_rate_limit_events")
    op.drop_index(
        "ix_auth_rate_limit_events_action_identifier", table_name="auth_rate_limit_events"
    )
    op.drop_table("auth_rate_limit_events")

    op.drop_index("ix_auth_sessions_user_id", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_session_hash", table_name="auth_sessions")
    op.drop_table("auth_sessions")

    op.drop_index("ix_auth_users_identifier", table_name="auth_users")
    op.drop_table("auth_users")

    postgresql.ENUM(name="auth_rate_limit_action").drop(op.get_bind(), checkfirst=False)
    postgresql.ENUM(name="auth_user_origin").drop(op.get_bind(), checkfirst=False)
