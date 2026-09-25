import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from freyja_backend.db.base import Base
from freyja_backend.domain.market_data import DataQuality

# Context snapshots (POINT2-SNAPSHOT-001, contract in docs/domain/instantanea-de-contexto.md).
#
# The immutable record of the context a hypothesis was judged in. Market data and what a policy
# made of it: nothing here is owned by an account. A row is inserted once and never rewritten:
# a database trigger (migration 0015) rejects every UPDATE, and a later reclassification is a
# new row. `document` is the complete snapshot; the other columns copy its key facts so it can
# be searched, and CHECK constraints (see the migration) tie each copy to the document.


class ContextSnapshotRow(Base):
    __tablename__ = "freyja2_context_snapshots"
    __table_args__ = (
        Index("ix_freyja2_context_snapshots_instrument_observed", "instrument_id", "observed_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    # sha256 of the canonical document without `computed_at`: the same observation, judged by
    # the same policy, is stored once.
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    snapshot_version: Mapped[str] = mapped_column(String(32), nullable=False)
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("freyja2_instruments.instrument_id"), nullable=False
    )
    data_source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("freyja2_data_sources.id"), nullable=False
    )
    signal_timeframe_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("freyja2_timeframes.id"), nullable=False
    )
    context_timeframe_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("freyja2_timeframes.id"), nullable=False
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    signal_trend: Mapped[str] = mapped_column(String(24), nullable=False)
    context_trend: Mapped[str] = mapped_column(String(24), nullable=False)
    signal_data_quality: Mapped[DataQuality] = mapped_column(
        Enum(DataQuality, name="freyja2_data_quality", native_enum=True), nullable=False
    )
    context_data_quality: Mapped[DataQuality] = mapped_column(
        Enum(DataQuality, name="freyja2_data_quality", native_enum=True), nullable=False
    )
    # Only Forex has sessions; NULL is "not applicable".
    market_session: Mapped[str | None] = mapped_column(String(32), nullable=True)
    policy_version: Mapped[str | None] = mapped_column(String(200), nullable=True)
    required_relationship: Mapped[str | None] = mapped_column(String(24), nullable=True)
    orientation: Mapped[str] = mapped_column(String(16), nullable=False)
    policy_outcome: Mapped[str] = mapped_column(String(24), nullable=False)
    # NULL when the policy lacked the context to judge (INSUFFICIENT_CONTEXT).
    context_compatible: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    reasons: Mapped[list[str]] = mapped_column(ARRAY(String(48)), nullable=False)
    document: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    def __repr__(self) -> str:
        return (
            f"ContextSnapshotRow(id={self.id!r}, instrument_id={self.instrument_id!r}, "
            f"observed_at={self.observed_at!r}, policy_outcome={self.policy_outcome!r})"
        )
