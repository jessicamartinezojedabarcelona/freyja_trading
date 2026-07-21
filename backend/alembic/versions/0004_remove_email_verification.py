"""remove_email_verification

Product decision: email verification is retired entirely. Registration now
creates an account that is active and can log in immediately — there is no
"pending verification" state left to convert, since `is_active` was already
always true and the separate `email_verified_at` gate is what this migration
removes.

Revision ID: 0004_remove_email_verification
Revises: 0003_auth_email_flows
Create Date: 2026-07-22

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_remove_email_verification"
down_revision: str | None = "0003_auth_email_flows"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_RATE_LIMIT_ACTION_VALUES = (
    "LOGIN",
    "REGISTER",
    "RESEND_VERIFICATION",
    "PASSWORD_RESET_REQUEST",
)
_NEW_RATE_LIMIT_ACTION_VALUES = ("LOGIN", "REGISTER", "PASSWORD_RESET_REQUEST")


def _token_table_columns() -> list[sa.Column]:  # type: ignore[type-arg]
    return [
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
    ]


def upgrade() -> None:
    # Retiring RESEND_VERIFICATION requires recreating the enum type (Postgres
    # has no "DROP VALUE"). Any existing rows tagged with the retiring value
    # are ephemeral rate-limit audit fingerprints (HMAC hashes, no user data,
    # already subject to a 24h retention policy) — safe to discard so the
    # column can be cast to the narrower type.
    op.execute("DELETE FROM auth_rate_limit_events WHERE action = 'RESEND_VERIFICATION'")

    op.execute("ALTER TYPE auth_rate_limit_action RENAME TO auth_rate_limit_action_old")
    new_enum = postgresql.ENUM(*_NEW_RATE_LIMIT_ACTION_VALUES, name="auth_rate_limit_action")
    new_enum.create(op.get_bind(), checkfirst=False)
    op.execute(
        "ALTER TABLE auth_rate_limit_events "
        "ALTER COLUMN action TYPE auth_rate_limit_action "
        "USING action::text::auth_rate_limit_action"
    )
    op.execute("DROP TYPE auth_rate_limit_action_old")

    # Email verification no longer exists as a feature: drop its token table
    # and the gating column on auth_users. No user/session data is touched —
    # every existing account becomes immediately usable simply because the
    # gate that used to check email_verified_at is gone.
    op.drop_index(
        "ix_auth_email_verification_tokens_user_id", table_name="auth_email_verification_tokens"
    )
    op.drop_index(
        "ix_auth_email_verification_tokens_token_hash", table_name="auth_email_verification_tokens"
    )
    op.drop_table("auth_email_verification_tokens")

    op.drop_column("auth_users", "email_verified_at")


def downgrade() -> None:
    op.add_column(
        "auth_users", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True)
    )

    op.create_table(
        "auth_email_verification_tokens",
        *_token_table_columns(),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["auth_users.id"],
            name="fk_auth_email_verification_tokens_user_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("token_hash", name="uq_auth_email_verification_tokens_token_hash"),
    )
    op.create_index(
        "ix_auth_email_verification_tokens_token_hash",
        "auth_email_verification_tokens",
        ["token_hash"],
    )
    op.create_index(
        "ix_auth_email_verification_tokens_user_id",
        "auth_email_verification_tokens",
        ["user_id"],
    )

    op.execute("ALTER TYPE auth_rate_limit_action RENAME TO auth_rate_limit_action_new")
    old_enum = postgresql.ENUM(*_OLD_RATE_LIMIT_ACTION_VALUES, name="auth_rate_limit_action")
    old_enum.create(op.get_bind(), checkfirst=False)
    op.execute(
        "ALTER TABLE auth_rate_limit_events "
        "ALTER COLUMN action TYPE auth_rate_limit_action "
        "USING action::text::auth_rate_limit_action"
    )
    op.execute("DROP TYPE auth_rate_limit_action_new")
