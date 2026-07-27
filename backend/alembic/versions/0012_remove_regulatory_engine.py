"""remove_internal_regulatory_engine

Revision ID: 0012_remove_regulatory_engine
Revises: 0011_capability_context
Create Date: 2026-07-27

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0012_remove_regulatory_engine"
down_revision: str | None = "0011_capability_context"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# POINT1-CAPABILITY-API-CORRECTION-001: retires the internal regulatory-
# eligibility engine introduced by 0011_capability_context. Freyja does not
# interpret or apply per-jurisdiction legislation and does not maintain an
# internal legal/regulatory catalog — the connected broker is the sole
# authority over product availability and account permissions, normalized on
# ExecutionContext as venue_permission_status (unchanged by this migration).
# This migration:
#
#   - drops freyja2_execution_context_regulatory_rules (the association
#     table) first, then freyja2_regulatory_rules itself — no CASCADE,
#     explicit DROP INDEX/DROP TABLE in dependency order;
#   - drops jurisdiction, client_classification, and
#     regulatory_eligibility_status from freyja2_execution_contexts, and
#     rebuilds ck_freyja2_execution_contexts_enabled_requires_all_positive
#     to require only credentials_status/venue_permission_status/
#     owner_authorization_status (never regulatory_eligibility_status,
#     which no longer exists);
#   - drops the now-unused freyja2_regulatory_eligibility_status and
#     freyja2_regulatory_rule_effect enum types.
#
# It never touches freyja2_instruments, any catalog/seed table, any
# freyja2_venues/freyja2_data_sources/provider-mapping table, or
# freyja2_technical_capabilities. Existing freyja2_execution_contexts rows
# are preserved (only 3 of their columns are dropped; the rows themselves
# are never deleted).
#
# SAFETY (fail-closed): if freyja2_regulatory_rules or
# freyja2_execution_context_regulatory_rules contain any row, upgrade()
# aborts BEFORE issuing any DDL — this migration has no replacement internal
# regulatory model to migrate that data into, and never silently discards
# it. The abort message reports only row COUNTS, never row content (no
# jurisdiction, citation, or classification value is ever printed).
#
# REVERSIBILITY LIMIT (downgrade): downgrade() structurally recreates the
# 0011 schema (tables, columns, constraints, enums) exactly, but never
# fabricates regulatory data. jurisdiction/client_classification/
# regulatory_eligibility_status are re-added as NOT NULL with no default —
# by construction this succeeds only when freyja2_execution_contexts is
# empty at the time of downgrade (the same fail-closed pattern
# 0006_catalog_display_names already established: PostgreSQL itself refuses
# ADD COLUMN ... NOT NULL without a default against a non-empty table). If
# ExecutionContext rows exist, downgrade past this revision requires manual
# intervention — there is no automatic way to reconstruct real regulatory
# values for them.


class RegulatoryDataPresentError(RuntimeError):
    """Raised when the regulatory tables are not empty at upgrade time. See
    the module docstring for the required manual remediation — this
    migration never deletes regulatory data silently."""


def _fail_if_regulatory_data_present() -> None:
    bind = op.get_bind()
    rule_count = bind.execute(sa.text("SELECT COUNT(*) FROM freyja2_regulatory_rules")).scalar_one()
    association_count = bind.execute(
        sa.text("SELECT COUNT(*) FROM freyja2_execution_context_regulatory_rules")
    ).scalar_one()
    if rule_count or association_count:
        raise RegulatoryDataPresentError(
            "POINT1-CAPABILITY-API-CORRECTION-001: refusing to upgrade past "
            "0011_capability_context — freyja2_regulatory_rules has "
            f"{rule_count} row(s) and freyja2_execution_context_regulatory_rules "
            f"has {association_count} row(s) (counts only; row content is "
            "intentionally never included in this error). This migration has "
            "no automatic replacement for that data and never deletes it "
            "silently. Export/archive the existing rows out-of-band first, "
            "then re-run this migration against an empty regulatory dataset."
        )


def upgrade() -> None:
    _fail_if_regulatory_data_present()

    op.drop_index(
        "ix_freyja2_execution_context_regulatory_rules_rule_id",
        table_name="freyja2_execution_context_regulatory_rules",
    )
    op.drop_table("freyja2_execution_context_regulatory_rules")

    op.drop_index("ix_freyja2_regulatory_rules_venue_id", table_name="freyja2_regulatory_rules")
    op.drop_index(
        "ix_freyja2_regulatory_rules_product_type_id", table_name="freyja2_regulatory_rules"
    )
    op.drop_index("ix_freyja2_regulatory_rules_jurisdiction", table_name="freyja2_regulatory_rules")
    op.drop_table("freyja2_regulatory_rules")

    # Drop every CHECK that depends on a column being dropped below — no
    # CASCADE, so these must go first, in the same order (constraints, then
    # columns) that would otherwise require it.
    op.drop_constraint(
        "ck_freyja2_execution_contexts_enabled_requires_all_positive",
        "freyja2_execution_contexts",
        type_="check",
    )
    op.drop_constraint(
        "ck_freyja2_execution_contexts_jurisdiction_not_blank",
        "freyja2_execution_contexts",
        type_="check",
    )
    op.drop_constraint(
        "ck_freyja2_execution_contexts_jurisdiction_trimmed",
        "freyja2_execution_contexts",
        type_="check",
    )
    op.drop_constraint(
        "ck_freyja2_execution_contexts_client_classification_not_blank",
        "freyja2_execution_contexts",
        type_="check",
    )
    op.drop_constraint(
        "ck_freyja2_execution_contexts_client_classification_trimmed",
        "freyja2_execution_contexts",
        type_="check",
    )

    op.drop_column("freyja2_execution_contexts", "regulatory_eligibility_status")
    op.drop_column("freyja2_execution_contexts", "jurisdiction")
    op.drop_column("freyja2_execution_contexts", "client_classification")

    op.create_check_constraint(
        "ck_freyja2_execution_contexts_enabled_requires_all_positive",
        "freyja2_execution_contexts",
        "activation_status <> 'ENABLED' OR ("
        "credentials_status = 'CONFIGURED' "
        "AND venue_permission_status = 'GRANTED' "
        "AND owner_authorization_status = 'AUTHORIZED'"
        ")",
    )

    postgresql.ENUM(name="freyja2_regulatory_eligibility_status").drop(
        op.get_bind(), checkfirst=False
    )
    postgresql.ENUM(name="freyja2_regulatory_rule_effect").drop(op.get_bind(), checkfirst=False)


def downgrade() -> None:
    # See the "REVERSIBILITY LIMIT" note above: the ADD COLUMN calls below
    # are NOT NULL with no default, so this only succeeds against an empty
    # freyja2_execution_contexts table — by design, never by inventing data.
    regulatory_rule_effect = postgresql.ENUM(
        "ELIGIBLE", "NOT_ELIGIBLE", name="freyja2_regulatory_rule_effect"
    )
    regulatory_rule_effect.create(op.get_bind(), checkfirst=False)
    regulatory_eligibility_status = postgresql.ENUM(
        "NOT_EVALUATED",
        "ELIGIBLE",
        "NOT_ELIGIBLE",
        name="freyja2_regulatory_eligibility_status",
    )
    regulatory_eligibility_status.create(op.get_bind(), checkfirst=False)

    op.drop_constraint(
        "ck_freyja2_execution_contexts_enabled_requires_all_positive",
        "freyja2_execution_contexts",
        type_="check",
    )

    op.add_column(
        "freyja2_execution_contexts",
        sa.Column("jurisdiction", sa.String(length=32), nullable=False),
    )
    op.add_column(
        "freyja2_execution_contexts",
        sa.Column("client_classification", sa.String(length=32), nullable=False),
    )
    op.add_column(
        "freyja2_execution_contexts",
        sa.Column(
            "regulatory_eligibility_status",
            postgresql.ENUM(
                "NOT_EVALUATED",
                "ELIGIBLE",
                "NOT_ELIGIBLE",
                name="freyja2_regulatory_eligibility_status",
                create_type=False,
            ),
            nullable=False,
        ),
    )

    op.create_check_constraint(
        "ck_freyja2_execution_contexts_jurisdiction_not_blank",
        "freyja2_execution_contexts",
        "char_length(btrim(jurisdiction)) > 0",
    )
    op.create_check_constraint(
        "ck_freyja2_execution_contexts_jurisdiction_trimmed",
        "freyja2_execution_contexts",
        "jurisdiction = btrim(jurisdiction)",
    )
    op.create_check_constraint(
        "ck_freyja2_execution_contexts_client_classification_not_blank",
        "freyja2_execution_contexts",
        "char_length(btrim(client_classification)) > 0",
    )
    op.create_check_constraint(
        "ck_freyja2_execution_contexts_client_classification_trimmed",
        "freyja2_execution_contexts",
        "client_classification = btrim(client_classification)",
    )
    op.create_check_constraint(
        "ck_freyja2_execution_contexts_enabled_requires_all_positive",
        "freyja2_execution_contexts",
        "activation_status <> 'ENABLED' OR ("
        "credentials_status = 'CONFIGURED' "
        "AND venue_permission_status = 'GRANTED' "
        "AND regulatory_eligibility_status = 'ELIGIBLE' "
        "AND owner_authorization_status = 'AUTHORIZED'"
        ")",
    )

    op.create_table(
        "freyja2_regulatory_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("jurisdiction", sa.String(length=32), nullable=False),
        sa.Column("client_classification", sa.String(length=32), nullable=True),
        sa.Column("product_type_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("venue_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "effect",
            postgresql.ENUM(
                "ELIGIBLE",
                "NOT_ELIGIBLE",
                name="freyja2_regulatory_rule_effect",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "effective_from",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_citation", sa.Text(), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["product_type_id"],
            ["freyja2_product_types.id"],
            name="fk_freyja2_regulatory_rules_product_type_id",
        ),
        sa.ForeignKeyConstraint(
            ["venue_id"], ["freyja2_venues.id"], name="fk_freyja2_regulatory_rules_venue_id"
        ),
        sa.CheckConstraint(
            "char_length(btrim(jurisdiction)) > 0",
            name="ck_freyja2_regulatory_rules_jurisdiction_not_blank",
        ),
        sa.CheckConstraint(
            "jurisdiction = btrim(jurisdiction)",
            name="ck_freyja2_regulatory_rules_jurisdiction_trimmed",
        ),
        sa.CheckConstraint(
            "client_classification IS NULL OR ("
            "char_length(btrim(client_classification)) > 0 "
            "AND client_classification = btrim(client_classification)"
            ")",
            name="ck_freyja2_regulatory_rules_client_classification_shape",
        ),
        sa.CheckConstraint(
            "char_length(btrim(source_citation)) > 0",
            name="ck_freyja2_regulatory_rules_source_citation_not_blank",
        ),
        sa.CheckConstraint(
            "source_citation = btrim(source_citation)",
            name="ck_freyja2_regulatory_rules_source_citation_trimmed",
        ),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name="ck_freyja2_regulatory_rules_valid_effective_window",
        ),
    )
    op.create_index(
        "ix_freyja2_regulatory_rules_jurisdiction",
        "freyja2_regulatory_rules",
        ["jurisdiction"],
    )
    op.create_index(
        "ix_freyja2_regulatory_rules_product_type_id",
        "freyja2_regulatory_rules",
        ["product_type_id"],
    )
    op.create_index(
        "ix_freyja2_regulatory_rules_venue_id", "freyja2_regulatory_rules", ["venue_id"]
    )

    op.create_table(
        "freyja2_execution_context_regulatory_rules",
        sa.Column("execution_context_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("regulatory_rule_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["execution_context_id"],
            ["freyja2_execution_contexts.id"],
            name="fk_freyja2_execution_context_regulatory_rules_context_id",
        ),
        sa.ForeignKeyConstraint(
            ["regulatory_rule_id"],
            ["freyja2_regulatory_rules.id"],
            name="fk_freyja2_execution_context_regulatory_rules_rule_id",
        ),
    )
    op.create_index(
        "ix_freyja2_execution_context_regulatory_rules_rule_id",
        "freyja2_execution_context_regulatory_rules",
        ["regulatory_rule_id"],
    )
