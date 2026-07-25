"""capability_context

Revision ID: 0011_capability_context
Revises: 0010_provider_mappings
Create Date: 2026-07-25

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0011_capability_context"
down_revision: str | None = "0010_provider_mappings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# POINT1-CAPABILITY-001: separates technical capability (what Freyja/a
# venue/data source knows how to do), regulatory eligibility (what is
# permitted for a jurisdiction/client classification/product/venue), and
# operational activation (what a specific owner's account may use, for a
# specific product, in a specific DEMO/REAL environment) into distinct
# tables. None of these collapse into a single boolean, and none of them
# touch freyja2_instruments/freyja2_venues/freyja2_data_sources/
# freyja2_timeframes/freyja2_product_types beyond a plain, non-cascading FK
# reference. No credentials, tokens, API keys, or secret material are
# stored anywhere — only status enums and account_key, an internal opaque
# (non-secret) account identifier. No provider/account/capability/
# regulatory rows are inserted; schema only.
#
# This revision was corrected after independent audit (2026-07-25), before
# being merged to main, so it is edited in place rather than superseded by
# a new revision: added account_key + product_type_id to
# freyja2_execution_contexts (a single owner+venue+environment triple
# cannot represent several accounts of the same owner, nor per-product
# independence); replaced the single regulatory_rule_id FK with an explicit
# many-to-many association table
# (freyja2_execution_context_regulatory_rules), since a context's
# eligibility may depend on several rules/evidence simultaneously; added
# NOT_APPLICABLE to freyja2_capability_status plus a physical CHECK forcing
# demo_execution/real_execution/settlement to NOT_APPLICABLE whenever a
# capability is linked to a DataSource (which never executes or settles
# anything); replaced the one-directional reason_unavailable CHECK with a
# biconditional (reason present and well-formed if-and-only-if some
# dimension is NOT_SUPPORTED); and added a small IMMUTABLE SQL function to
# validate every element of suspension_reasons (not just its cardinality).

_CAPABILITY_STATUS_VALUES = (
    "NOT_IMPLEMENTED",
    "NOT_EVALUATED",
    "SUPPORTED",
    "NOT_SUPPORTED",
    "NOT_APPLICABLE",
)
_EXECUTION_ENVIRONMENT_VALUES = ("DEMO", "REAL")
_CREDENTIALS_STATUS_VALUES = ("NOT_CONFIGURED", "CONFIGURED", "INVALID")
_VENUE_PERMISSION_STATUS_VALUES = ("NOT_EVALUATED", "GRANTED", "DENIED")
_REGULATORY_ELIGIBILITY_STATUS_VALUES = ("NOT_EVALUATED", "ELIGIBLE", "NOT_ELIGIBLE")
_OWNER_AUTHORIZATION_STATUS_VALUES = ("NOT_AUTHORIZED", "AUTHORIZED")
_ACTIVATION_STATUS_VALUES = ("NOT_CONFIGURED", "CONFIGURED", "ENABLED", "SUSPENDED")
_REGULATORY_RULE_EFFECT_VALUES = ("ELIGIBLE", "NOT_ELIGIBLE")

_ENUM_SPECS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("freyja2_capability_status", _CAPABILITY_STATUS_VALUES),
    ("freyja2_execution_environment", _EXECUTION_ENVIRONMENT_VALUES),
    ("freyja2_credentials_status", _CREDENTIALS_STATUS_VALUES),
    ("freyja2_venue_permission_status", _VENUE_PERMISSION_STATUS_VALUES),
    ("freyja2_regulatory_eligibility_status", _REGULATORY_ELIGIBILITY_STATUS_VALUES),
    ("freyja2_owner_authorization_status", _OWNER_AUTHORIZATION_STATUS_VALUES),
    ("freyja2_activation_status", _ACTIVATION_STATUS_VALUES),
    ("freyja2_regulatory_rule_effect", _REGULATORY_RULE_EFFECT_VALUES),
)

_TEXT_ARRAY_ALL_NONBLANK_FUNCTION = "freyja2_text_array_all_nonblank"


def upgrade() -> None:
    bind = op.get_bind()
    for name, values in _ENUM_SPECS:
        postgresql.ENUM(*values, name=name).create(bind, checkfirst=False)

    def enum_ref(name: str) -> postgresql.ENUM:
        return postgresql.ENUM(name=name, create_type=False)

    # A plain CHECK expression cannot contain a subquery, so validating
    # "every element of this array is non-null and non-blank after trim"
    # needs a small IMMUTABLE SQL function instead — a subquery inside a
    # function body is fully legal even though one directly inside a CHECK
    # clause is not. NULL arrays pass trivially (cardinality is validated
    # separately by ck_freyja2_execution_contexts_suspension_reasons_consistency).
    op.execute(
        f"""
        CREATE FUNCTION {_TEXT_ARRAY_ALL_NONBLANK_FUNCTION}(arr text[])
        RETURNS boolean
        LANGUAGE sql
        IMMUTABLE
        AS $$
            SELECT arr IS NULL OR NOT EXISTS (
                SELECT 1 FROM unnest(arr) AS elem
                WHERE elem IS NULL OR btrim(elem) = '' OR elem <> btrim(elem)
            )
        $$
        """
    )

    op.create_table(
        "freyja2_regulatory_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("jurisdiction", sa.String(length=32), nullable=False),
        sa.Column("client_classification", sa.String(length=32), nullable=True),
        sa.Column("product_type_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("venue_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("effect", enum_ref("freyja2_regulatory_rule_effect"), nullable=False),
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
        "freyja2_technical_capabilities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("instrument_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("venue_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("data_source_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("timeframe_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "market_data_status",
            enum_ref("freyja2_capability_status"),
            nullable=False,
            server_default="NOT_EVALUATED",
        ),
        sa.Column(
            "signal_detection_status",
            enum_ref("freyja2_capability_status"),
            nullable=False,
            server_default="NOT_EVALUATED",
        ),
        sa.Column(
            "backtest_status",
            enum_ref("freyja2_capability_status"),
            nullable=False,
            server_default="NOT_EVALUATED",
        ),
        sa.Column(
            "demo_execution_status",
            enum_ref("freyja2_capability_status"),
            nullable=False,
            server_default="NOT_EVALUATED",
        ),
        sa.Column(
            "real_execution_status",
            enum_ref("freyja2_capability_status"),
            nullable=False,
            server_default="NOT_EVALUATED",
        ),
        sa.Column(
            "settlement_status",
            enum_ref("freyja2_capability_status"),
            nullable=False,
            server_default="NOT_EVALUATED",
        ),
        sa.Column("reason_unavailable", sa.Text(), nullable=True),
        sa.Column(
            "effective_from",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["freyja2_instruments.instrument_id"],
            name="fk_freyja2_technical_capabilities_instrument_id",
        ),
        sa.ForeignKeyConstraint(
            ["venue_id"],
            ["freyja2_venues.id"],
            name="fk_freyja2_technical_capabilities_venue_id",
        ),
        sa.ForeignKeyConstraint(
            ["data_source_id"],
            ["freyja2_data_sources.id"],
            name="fk_freyja2_technical_capabilities_data_source_id",
        ),
        sa.ForeignKeyConstraint(
            ["timeframe_id"],
            ["freyja2_timeframes.id"],
            name="fk_freyja2_technical_capabilities_timeframe_id",
        ),
        sa.CheckConstraint(
            "(venue_id IS NOT NULL AND data_source_id IS NULL) "
            "OR (venue_id IS NULL AND data_source_id IS NOT NULL)",
            name="ck_freyja2_technical_capabilities_exactly_one_provider_axis",
        ),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name="ck_freyja2_technical_capabilities_valid_effective_window",
        ),
        # Bidirectional: reason_unavailable is required, non-blank, and
        # trimmed if AND ONLY IF at least one dimension is NOT_SUPPORTED.
        sa.CheckConstraint(
            "("
            "market_data_status = 'NOT_SUPPORTED' "
            "OR signal_detection_status = 'NOT_SUPPORTED' "
            "OR backtest_status = 'NOT_SUPPORTED' "
            "OR demo_execution_status = 'NOT_SUPPORTED' "
            "OR real_execution_status = 'NOT_SUPPORTED' "
            "OR settlement_status = 'NOT_SUPPORTED'"
            ") = ("
            "reason_unavailable IS NOT NULL "
            "AND char_length(btrim(reason_unavailable)) > 0 "
            "AND reason_unavailable = btrim(reason_unavailable)"
            ")",
            name="ck_freyja2_technical_capabilities_reason_iff_not_supported",
        ),
        # A DataSource never executes or settles anything.
        sa.CheckConstraint(
            "data_source_id IS NULL OR ("
            "demo_execution_status = 'NOT_APPLICABLE' "
            "AND real_execution_status = 'NOT_APPLICABLE' "
            "AND settlement_status = 'NOT_APPLICABLE'"
            ")",
            name="ck_freyja2_technical_capabilities_data_source_not_applicable",
        ),
    )
    op.create_index(
        "ix_freyja2_technical_capabilities_instrument_id",
        "freyja2_technical_capabilities",
        ["instrument_id"],
    )
    op.create_index(
        "ix_freyja2_technical_capabilities_venue_id",
        "freyja2_technical_capabilities",
        ["venue_id"],
    )
    op.create_index(
        "ix_freyja2_technical_capabilities_data_source_id",
        "freyja2_technical_capabilities",
        ["data_source_id"],
    )
    op.create_index(
        "ix_freyja2_technical_capabilities_timeframe_id",
        "freyja2_technical_capabilities",
        ["timeframe_id"],
    )
    # Two partial indexes instead of one composite index over (venue_id,
    # data_source_id): those columns are never both set (see the
    # exactly-one-axis CHECK above), and a plain UNIQUE index treats every
    # NULL as distinct from every other NULL — the constraint would never
    # fire on whichever column is always NULL. Same fix already applied to
    # VenueInstrument.provider_contract_id in 0010_provider_mappings.
    op.create_index(
        "uq_freyja2_technical_capabilities_current_by_venue",
        "freyja2_technical_capabilities",
        ["instrument_id", "venue_id", "timeframe_id"],
        unique=True,
        postgresql_where=sa.text("effective_to IS NULL AND venue_id IS NOT NULL"),
    )
    op.create_index(
        "uq_freyja2_technical_capabilities_current_by_data_source",
        "freyja2_technical_capabilities",
        ["instrument_id", "data_source_id", "timeframe_id"],
        unique=True,
        postgresql_where=sa.text("effective_to IS NULL AND data_source_id IS NOT NULL"),
    )

    op.create_table(
        "freyja2_execution_contexts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("venue_id", postgresql.UUID(as_uuid=True), nullable=False),
        # Internal, opaque, non-secret identifier of which of an owner's
        # several accounts at this venue the row refers to — never a
        # credential, API key, or token. See the model docstring.
        sa.Column("account_key", sa.String(length=64), nullable=False),
        sa.Column(
            "execution_environment",
            enum_ref("freyja2_execution_environment"),
            nullable=False,
        ),
        sa.Column("product_type_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("jurisdiction", sa.String(length=32), nullable=False),
        sa.Column("client_classification", sa.String(length=32), nullable=False),
        sa.Column(
            "credentials_status",
            enum_ref("freyja2_credentials_status"),
            nullable=False,
            server_default="NOT_CONFIGURED",
        ),
        sa.Column(
            "venue_permission_status",
            enum_ref("freyja2_venue_permission_status"),
            nullable=False,
            server_default="NOT_EVALUATED",
        ),
        sa.Column(
            "regulatory_eligibility_status",
            enum_ref("freyja2_regulatory_eligibility_status"),
            nullable=False,
            server_default="NOT_EVALUATED",
        ),
        sa.Column(
            "owner_authorization_status",
            enum_ref("freyja2_owner_authorization_status"),
            nullable=False,
            server_default="NOT_AUTHORIZED",
        ),
        sa.Column(
            "activation_status",
            enum_ref("freyja2_activation_status"),
            nullable=False,
            server_default="NOT_CONFIGURED",
        ),
        sa.Column("suspension_reasons", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["auth_users.id"], name="fk_freyja2_execution_contexts_owner_id"
        ),
        sa.ForeignKeyConstraint(
            ["venue_id"], ["freyja2_venues.id"], name="fk_freyja2_execution_contexts_venue_id"
        ),
        sa.ForeignKeyConstraint(
            ["product_type_id"],
            ["freyja2_product_types.id"],
            name="fk_freyja2_execution_contexts_product_type_id",
        ),
        sa.CheckConstraint(
            "activation_status <> 'ENABLED' OR ("
            "credentials_status = 'CONFIGURED' "
            "AND venue_permission_status = 'GRANTED' "
            "AND regulatory_eligibility_status = 'ELIGIBLE' "
            "AND owner_authorization_status = 'AUTHORIZED'"
            ")",
            name="ck_freyja2_execution_contexts_enabled_requires_all_positive",
        ),
        sa.CheckConstraint(
            "(activation_status = 'SUSPENDED' AND suspension_reasons IS NOT NULL "
            "AND cardinality(suspension_reasons) > 0) "
            "OR (activation_status <> 'SUSPENDED' "
            "AND (suspension_reasons IS NULL OR cardinality(suspension_reasons) = 0))",
            name="ck_freyja2_execution_contexts_suspension_reasons_consistency",
        ),
        sa.CheckConstraint(
            f"{_TEXT_ARRAY_ALL_NONBLANK_FUNCTION}(suspension_reasons)",
            name="ck_freyja2_execution_contexts_suspension_reasons_elements_valid",
        ),
        sa.CheckConstraint(
            "char_length(btrim(jurisdiction)) > 0",
            name="ck_freyja2_execution_contexts_jurisdiction_not_blank",
        ),
        sa.CheckConstraint(
            "jurisdiction = btrim(jurisdiction)",
            name="ck_freyja2_execution_contexts_jurisdiction_trimmed",
        ),
        sa.CheckConstraint(
            "char_length(btrim(client_classification)) > 0",
            name="ck_freyja2_execution_contexts_client_classification_not_blank",
        ),
        sa.CheckConstraint(
            "client_classification = btrim(client_classification)",
            name="ck_freyja2_execution_contexts_client_classification_trimmed",
        ),
        sa.CheckConstraint(
            "char_length(btrim(account_key)) > 0",
            name="ck_freyja2_execution_contexts_account_key_not_blank",
        ),
        sa.CheckConstraint(
            "account_key = btrim(account_key)",
            name="ck_freyja2_execution_contexts_account_key_trimmed",
        ),
    )
    op.create_index(
        "ix_freyja2_execution_contexts_owner_id", "freyja2_execution_contexts", ["owner_id"]
    )
    op.create_index(
        "ix_freyja2_execution_contexts_venue_id", "freyja2_execution_contexts", ["venue_id"]
    )
    op.create_index(
        "ix_freyja2_execution_contexts_product_type_id",
        "freyja2_execution_contexts",
        ["product_type_id"],
    )
    op.create_index(
        "uq_freyja2_execution_contexts_identity",
        "freyja2_execution_contexts",
        ["owner_id", "venue_id", "account_key", "execution_environment", "product_type_id"],
        unique=True,
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


def downgrade() -> None:
    op.drop_index(
        "ix_freyja2_execution_context_regulatory_rules_rule_id",
        table_name="freyja2_execution_context_regulatory_rules",
    )
    op.drop_table("freyja2_execution_context_regulatory_rules")

    op.drop_index(
        "uq_freyja2_execution_contexts_identity",
        table_name="freyja2_execution_contexts",
    )
    op.drop_index(
        "ix_freyja2_execution_contexts_product_type_id",
        table_name="freyja2_execution_contexts",
    )
    op.drop_index("ix_freyja2_execution_contexts_venue_id", table_name="freyja2_execution_contexts")
    op.drop_index("ix_freyja2_execution_contexts_owner_id", table_name="freyja2_execution_contexts")
    op.drop_table("freyja2_execution_contexts")

    op.drop_index(
        "uq_freyja2_technical_capabilities_current_by_data_source",
        table_name="freyja2_technical_capabilities",
    )
    op.drop_index(
        "uq_freyja2_technical_capabilities_current_by_venue",
        table_name="freyja2_technical_capabilities",
    )
    op.drop_index(
        "ix_freyja2_technical_capabilities_timeframe_id",
        table_name="freyja2_technical_capabilities",
    )
    op.drop_index(
        "ix_freyja2_technical_capabilities_data_source_id",
        table_name="freyja2_technical_capabilities",
    )
    op.drop_index(
        "ix_freyja2_technical_capabilities_venue_id",
        table_name="freyja2_technical_capabilities",
    )
    op.drop_index(
        "ix_freyja2_technical_capabilities_instrument_id",
        table_name="freyja2_technical_capabilities",
    )
    op.drop_table("freyja2_technical_capabilities")

    op.drop_index("ix_freyja2_regulatory_rules_venue_id", table_name="freyja2_regulatory_rules")
    op.drop_index(
        "ix_freyja2_regulatory_rules_product_type_id", table_name="freyja2_regulatory_rules"
    )
    op.drop_index("ix_freyja2_regulatory_rules_jurisdiction", table_name="freyja2_regulatory_rules")
    op.drop_table("freyja2_regulatory_rules")

    op.execute(f"DROP FUNCTION {_TEXT_ARRAY_ALL_NONBLANK_FUNCTION}(text[])")

    for name, _values in reversed(_ENUM_SPECS):
        postgresql.ENUM(name=name).drop(op.get_bind(), checkfirst=False)
