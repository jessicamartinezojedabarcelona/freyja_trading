"""auth_email_flows

Revision ID: 0003_auth_email_flows
Revises: 0002_auth
Create Date: 2026-07-20

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_auth_email_flows"
down_revision: str | None = "0002_auth"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


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

    op.create_table(
        "auth_password_reset_tokens",
        *_token_table_columns(),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["auth_users.id"],
            name="fk_auth_password_reset_tokens_user_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("token_hash", name="uq_auth_password_reset_tokens_token_hash"),
    )
    op.create_index(
        "ix_auth_password_reset_tokens_token_hash", "auth_password_reset_tokens", ["token_hash"]
    )
    op.create_index(
        "ix_auth_password_reset_tokens_user_id", "auth_password_reset_tokens", ["user_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_auth_password_reset_tokens_user_id", table_name="auth_password_reset_tokens")
    op.drop_index(
        "ix_auth_password_reset_tokens_token_hash", table_name="auth_password_reset_tokens"
    )
    op.drop_table("auth_password_reset_tokens")

    op.drop_index(
        "ix_auth_email_verification_tokens_user_id", table_name="auth_email_verification_tokens"
    )
    op.drop_index(
        "ix_auth_email_verification_tokens_token_hash", table_name="auth_email_verification_tokens"
    )
    op.drop_table("auth_email_verification_tokens")

    op.drop_column("auth_users", "email_verified_at")
