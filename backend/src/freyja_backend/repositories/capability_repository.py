import uuid
from dataclasses import dataclass

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session

from freyja_backend.db.models.capability import TechnicalCapability
from freyja_backend.db.models.catalog import Instrument, Timeframe
from freyja_backend.db.models.provider import DataSource, Venue

# Read-only queries for TechnicalCapability (POINT1-CAPABILITY-001). "Vigente"
# means effective_from <= now() AND (effective_to IS NULL OR effective_to >
# now()) — evaluated with the database's own now(), never the app server's
# clock, and never treating a future-dated effective_from as already active
# just because effective_to happens to be NULL.

_CapabilityRow = tuple[TechnicalCapability, Instrument, Timeframe, Venue | None, DataSource | None]


@dataclass(frozen=True)
class CapabilityRow:
    capability: TechnicalCapability
    instrument: Instrument
    timeframe: Timeframe
    venue: Venue | None
    data_source: DataSource | None


def _capability_select() -> Select[_CapabilityRow]:
    # See catalog_repository._instrument_select: sqlalchemy's overloads can't
    # see the outerjoin below, so it infers Venue/DataSource as non-optional
    # even though the actual query yields NULL for whichever axis is unset.
    return (
        select(  # type: ignore[return-value]
            TechnicalCapability, Instrument, Timeframe, Venue, DataSource
        )
        .join(Instrument, Instrument.instrument_id == TechnicalCapability.instrument_id)
        .join(Timeframe, Timeframe.id == TechnicalCapability.timeframe_id)
        .outerjoin(Venue, Venue.id == TechnicalCapability.venue_id)
        .outerjoin(DataSource, DataSource.id == TechnicalCapability.data_source_id)
    )


def list_capabilities(
    session: Session,
    *,
    instrument_id: uuid.UUID | None = None,
    venue_id: uuid.UUID | None = None,
    data_source_id: uuid.UUID | None = None,
    timeframe_id: uuid.UUID | None = None,
    include_history: bool = False,
    limit: int,
    offset: int,
) -> tuple[list[CapabilityRow], int]:
    stmt = _capability_select()

    conditions = []
    if instrument_id is not None:
        conditions.append(TechnicalCapability.instrument_id == instrument_id)
    if venue_id is not None:
        conditions.append(TechnicalCapability.venue_id == venue_id)
    if data_source_id is not None:
        conditions.append(TechnicalCapability.data_source_id == data_source_id)
    if timeframe_id is not None:
        conditions.append(TechnicalCapability.timeframe_id == timeframe_id)
    if not include_history:
        conditions.append(TechnicalCapability.effective_from <= func.now())
        conditions.append(
            or_(
                TechnicalCapability.effective_to.is_(None),
                TechnicalCapability.effective_to > func.now(),
            )
        )
    if conditions:
        stmt = stmt.where(and_(*conditions))

    total = session.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()

    stmt = (
        stmt.order_by(
            TechnicalCapability.instrument_id,
            TechnicalCapability.timeframe_id,
            TechnicalCapability.venue_id.nulls_first(),
            TechnicalCapability.data_source_id.nulls_first(),
            TechnicalCapability.effective_from.desc(),
            TechnicalCapability.id,
        )
        .limit(limit)
        .offset(offset)
    )

    rows = [
        CapabilityRow(
            capability=capability,
            instrument=instrument,
            timeframe=timeframe,
            venue=venue,
            data_source=data_source,
        )
        for capability, instrument, timeframe, venue, data_source in session.execute(stmt).all()
    ]
    return rows, total


def get_capability(session: Session, capability_id: uuid.UUID) -> CapabilityRow | None:
    stmt = _capability_select().where(TechnicalCapability.id == capability_id)
    row = session.execute(stmt).first()
    if row is None:
        return None
    capability, instrument, timeframe, venue, data_source = row
    return CapabilityRow(
        capability=capability,
        instrument=instrument,
        timeframe=timeframe,
        venue=venue,
        data_source=data_source,
    )
