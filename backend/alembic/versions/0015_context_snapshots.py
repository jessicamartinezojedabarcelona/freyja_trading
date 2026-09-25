"""context_snapshots

Revision ID: 0015_context_snapshots
Revises: 0014_kraken_data_source
Create Date: 2026-09-25

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0015_context_snapshots"
down_revision: str | None = "0014_kraken_data_source"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# POINT2-SNAPSHOT-001. Adds freyja2_context_snapshots: the immutable record of the context
# (trend and observable data of the signal and context timeframes) a hypothesis was judged in.
#
#   - `document` is the whole snapshot, exactly as it was captured; the other columns are
#     copies of its key facts so it can be searched. CHECK constraints tie every copy to the
#     document, so the two can never disagree.
#   - Identified by its content: `content_hash` (sha256 of the canonical document, without
#     `computed_at`) is unique, so the same observation is stored once.
#   - A BEFORE UPDATE trigger rejects every UPDATE, as on freyja2_candles: a snapshot can only
#     be inserted. A later reclassification is a new snapshot.
#   - Nothing here is owned by an account: it holds market data and what a policy made of it.
#     A future Signal will point at a snapshot; no signal exists yet, so no reference does.
#
# Forward-only for data: downgrade() refuses to run while any snapshot is stored.

_TRENDS = "('UPTREND', 'DOWNTREND', 'RANGE', 'TRANSITION', 'INSUFFICIENT_DATA')"
_RELATIONSHIPS = "('WITH_TREND', 'COUNTER_TREND', 'RANGE_ONLY', 'TRANSITION_ONLY', 'ANY')"
_OUTCOMES = "('COMPATIBLE', 'INCOMPATIBLE', 'INSUFFICIENT_CONTEXT')"


def upgrade() -> None:
    quality = postgresql.ENUM(
        "OK", "DEGRADED", "UNAVAILABLE", name="freyja2_data_quality", create_type=False
    )

    op.create_table(
        "freyja2_context_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("snapshot_version", sa.String(length=32), nullable=False),
        sa.Column("instrument_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("data_source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("signal_timeframe_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("context_timeframe_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("signal_trend", sa.String(length=24), nullable=False),
        sa.Column("context_trend", sa.String(length=24), nullable=False),
        sa.Column("signal_data_quality", quality, nullable=False),
        sa.Column("context_data_quality", quality, nullable=False),
        sa.Column("market_session", sa.String(length=32), nullable=True),
        sa.Column("policy_version", sa.String(length=200), nullable=True),
        sa.Column("required_relationship", sa.String(length=24), nullable=True),
        sa.Column("orientation", sa.String(length=16), nullable=False),
        sa.Column("policy_outcome", sa.String(length=24), nullable=False),
        sa.Column("context_compatible", sa.Boolean(), nullable=True),
        sa.Column("reasons", postgresql.ARRAY(sa.String(length=48)), nullable=False),
        sa.Column("document", postgresql.JSONB(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_freyja2_context_snapshots"),
        sa.UniqueConstraint("content_hash", name="uq_freyja2_context_snapshots_content_hash"),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["freyja2_instruments.instrument_id"],
            name="fk_freyja2_context_snapshots_instrument",
        ),
        sa.ForeignKeyConstraint(
            ["data_source_id"],
            ["freyja2_data_sources.id"],
            name="fk_freyja2_context_snapshots_data_source",
        ),
        sa.ForeignKeyConstraint(
            ["signal_timeframe_id"],
            ["freyja2_timeframes.id"],
            name="fk_freyja2_context_snapshots_signal_timeframe",
        ),
        sa.ForeignKeyConstraint(
            ["context_timeframe_id"],
            ["freyja2_timeframes.id"],
            name="fk_freyja2_context_snapshots_context_timeframe",
        ),
        sa.CheckConstraint(
            "char_length(content_hash) = 64", name="ck_freyja2_context_snapshots_hash_length"
        ),
        sa.CheckConstraint(
            "computed_at >= observed_at",
            name="ck_freyja2_context_snapshots_computed_after_observed",
        ),
        sa.CheckConstraint(
            f"signal_trend IN {_TRENDS} AND context_trend IN {_TRENDS}",
            name="ck_freyja2_context_snapshots_trends",
        ),
        sa.CheckConstraint(
            f"required_relationship IS NULL OR required_relationship IN {_RELATIONSHIPS}",
            name="ck_freyja2_context_snapshots_relationship",
        ),
        sa.CheckConstraint(
            "orientation IN ('BULLISH', 'BEARISH')", name="ck_freyja2_context_snapshots_orientation"
        ),
        sa.CheckConstraint(
            f"policy_outcome IN {_OUTCOMES}", name="ck_freyja2_context_snapshots_outcome"
        ),
        sa.CheckConstraint(
            "(policy_version IS NULL) = (required_relationship IS NULL)",
            name="ck_freyja2_context_snapshots_policy_pair",
        ),
        sa.CheckConstraint(
            "(policy_outcome = 'COMPATIBLE' AND context_compatible IS TRUE)"
            " OR (policy_outcome = 'INCOMPATIBLE' AND context_compatible IS FALSE)"
            " OR (policy_outcome = 'INSUFFICIENT_CONTEXT' AND context_compatible IS NULL)",
            name="ck_freyja2_context_snapshots_compatibility",
        ),
        sa.CheckConstraint(
            "(cardinality(reasons) = 0) = (policy_outcome = 'COMPATIBLE')",
            name="ck_freyja2_context_snapshots_reasons",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(document) = 'object'", name="ck_freyja2_context_snapshots_document_object"
        ),
        # Every copy is the document's own value: they can never disagree.
        sa.CheckConstraint(
            "document ->> 'snapshot_version' = snapshot_version"
            " AND document #>> '{observed,signal,trend}' = signal_trend"
            " AND document #>> '{observed,context,trend}' = context_trend"
            " AND document #>> '{observed,signal,data_quality}' = signal_data_quality::text"
            " AND document #>> '{observed,context,data_quality}' = context_data_quality::text"
            " AND (document #>> '{observed,market_session}') IS NOT DISTINCT FROM market_session"
            " AND (document #>> '{judged,policy_version}') IS NOT DISTINCT FROM policy_version"
            " AND (document #>> '{judged,required_relationship}')"
            " IS NOT DISTINCT FROM required_relationship"
            " AND document #>> '{judged,orientation}' = orientation"
            " AND document #>> '{judged,outcome}' = policy_outcome"
            " AND (document #>> '{judged,context_compatible}')::boolean"
            " IS NOT DISTINCT FROM context_compatible",
            name="ck_freyja2_context_snapshots_document_matches_columns",
        ),
    )
    op.create_index(
        "ix_freyja2_context_snapshots_instrument_observed",
        "freyja2_context_snapshots",
        ["instrument_id", "observed_at"],
    )

    op.execute(
        """
        CREATE FUNCTION freyja2_context_snapshots_reject_update() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION
                'freyja2_context_snapshots rows are immutable: a snapshot cannot be updated'
                USING ERRCODE = 'restrict_violation';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_freyja2_context_snapshots_immutable
        BEFORE UPDATE ON freyja2_context_snapshots
        FOR EACH ROW EXECUTE FUNCTION freyja2_context_snapshots_reject_update()
        """
    )


def downgrade() -> None:
    stored = op.get_bind().execute(sa.text("SELECT COUNT(*) FROM freyja2_context_snapshots"))
    count = stored.scalar_one()
    if count:
        raise RuntimeError(
            f"0015 downgrade would delete {count} stored context snapshot(s), which are "
            "immutable records. Remove them on purpose first, if that is really intended."
        )
    op.drop_table("freyja2_context_snapshots")
    op.execute("DROP FUNCTION freyja2_context_snapshots_reject_update()")
