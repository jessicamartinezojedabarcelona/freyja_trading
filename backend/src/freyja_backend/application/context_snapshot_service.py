import uuid
from dataclasses import dataclass
from datetime import UTC

from sqlalchemy.orm import Session

from freyja_backend.db.models.context_snapshot import ContextSnapshotRow
from freyja_backend.domain.context_snapshot import (
    ContextSnapshot,
    InvalidContextSnapshotError,
    snapshot_from_document,
)
from freyja_backend.repositories import context_snapshot_repository, market_data_repository

# Keeping and reading context snapshots (POINT2-SNAPSHOT-001). Storing writes what it is given;
# reading returns what was written. Nothing here classifies, judges or fetches anything: a
# stored snapshot is never recomputed, so a later reclassification, a new policy version or a
# revised candle cannot reach it.


class UnknownSnapshotReferenceError(Exception):
    """The snapshot names an instrument, source or timeframe the catalog does not have."""


class SnapshotIntegrityError(Exception):
    """A stored snapshot no longer matches its own content hash. It is never repaired."""


@dataclass(frozen=True, slots=True)
class StoreResult:
    snapshot_id: uuid.UUID
    # False when the same observation, judged by the same policy, was already stored: the
    # stored one is kept as it is, including when it was computed.
    inserted: bool


def store_context_snapshot(session: Session, snapshot: ContextSnapshot) -> StoreResult:
    """Insert the snapshot, once. It is only ever inserted: there is no way to change one."""
    values = _row_values(session, snapshot)
    inserted = context_snapshot_repository.insert_if_absent(session, values)
    return StoreResult(snapshot.snapshot_id, inserted)


def load_context_snapshot(session: Session, snapshot_id: uuid.UUID) -> ContextSnapshot | None:
    """The snapshot exactly as it was stored, or None if there is none.

    It reads the stored document; it never recomputes a trend or a judgement. It does check
    that what it read is still what was stored (the content hash), and refuses otherwise.
    """
    row = context_snapshot_repository.get_by_id(session, snapshot_id)
    if row is None:
        return None
    return _snapshot_of(row)


def _snapshot_of(row: ContextSnapshotRow) -> ContextSnapshot:
    try:
        snapshot = snapshot_from_document(row.document, computed_at=row.computed_at.astimezone(UTC))
    except InvalidContextSnapshotError as error:
        raise SnapshotIntegrityError(
            f"stored snapshot {row.id} is not readable: {error}"
        ) from error
    if snapshot.content_hash != row.content_hash or snapshot.snapshot_id != row.id:
        raise SnapshotIntegrityError(
            f"stored snapshot {row.id} does not match its content hash; it is not to be trusted"
        )
    return snapshot


def _row_values(session: Session, snapshot: ContextSnapshot) -> dict[str, object]:
    try:
        instrument_id = uuid.UUID(snapshot.instrument_id)
    except ValueError as error:
        raise UnknownSnapshotReferenceError(
            f"instrument {snapshot.instrument_id!r} is not a catalog id"
        ) from error
    if market_data_repository.get_instrument_by_id(session, instrument_id) is None:
        raise UnknownSnapshotReferenceError(f"instrument {snapshot.instrument_id!r} is unknown")
    source = market_data_repository.get_data_source(session, snapshot.data_source)
    if source is None:
        raise UnknownSnapshotReferenceError(f"data source {snapshot.data_source!r} is unknown")
    signal_timeframe = market_data_repository.get_timeframe(
        session, snapshot.signal.timeframe.value
    )
    context_timeframe = market_data_repository.get_timeframe(
        session, snapshot.context.timeframe.value
    )
    if signal_timeframe is None or context_timeframe is None:
        raise UnknownSnapshotReferenceError("a timeframe of the snapshot is not in the catalog")
    return {
        "id": snapshot.snapshot_id,
        "content_hash": snapshot.content_hash,
        "snapshot_version": snapshot.snapshot_version,
        "instrument_id": instrument_id,
        "data_source_id": source.id,
        "signal_timeframe_id": signal_timeframe.id,
        "context_timeframe_id": context_timeframe.id,
        "observed_at": snapshot.observed_at,
        "computed_at": snapshot.computed_at,
        "signal_trend": snapshot.signal.trend.value,
        "context_trend": snapshot.context.trend.value,
        "signal_data_quality": snapshot.signal.data_quality,
        "context_data_quality": snapshot.context.data_quality,
        "market_session": None
        if snapshot.market_session is None
        else snapshot.market_session.value,
        "policy_version": snapshot.policy_version,
        "required_relationship": (
            None if snapshot.required_relationship is None else snapshot.required_relationship.value
        ),
        "orientation": snapshot.orientation.value,
        "policy_outcome": snapshot.outcome.value,
        "context_compatible": snapshot.context_compatible,
        "reasons": [reason.value for reason in snapshot.reasons],
        "document": snapshot.document(include_computed_at=False),
    }
