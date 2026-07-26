import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from freyja_backend.db.models.provider import (
    DataSource,
    DataSourceInstrument,
    Venue,
    VenueInstrument,
)

# Read-only queries for provider mappings (POINT1-PROVIDER-001). Venue and
# DataSource are queried and returned separately — never merged into a single
# "providers" shape — since their columns/types genuinely differ
# (VenueType vs DataSourceType).


def list_venues(
    session: Session, *, is_active: bool | None = None, limit: int, offset: int
) -> tuple[list[Venue], int]:
    stmt = select(Venue)
    if is_active is not None:
        stmt = stmt.where(Venue.is_active == is_active)
    total = session.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    stmt = stmt.order_by(Venue.code, Venue.id).limit(limit).offset(offset)
    rows = list(session.execute(stmt).scalars().all())
    return rows, total


def list_data_sources(
    session: Session, *, is_active: bool | None = None, limit: int, offset: int
) -> tuple[list[DataSource], int]:
    stmt = select(DataSource)
    if is_active is not None:
        stmt = stmt.where(DataSource.is_active == is_active)
    total = session.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    stmt = stmt.order_by(DataSource.code, DataSource.id).limit(limit).offset(offset)
    rows = list(session.execute(stmt).scalars().all())
    return rows, total


def list_venue_instruments_for_instrument(
    session: Session, instrument_id: uuid.UUID
) -> list[tuple[VenueInstrument, Venue]]:
    stmt = (
        select(VenueInstrument, Venue)
        .join(Venue, Venue.id == VenueInstrument.venue_id)
        .where(VenueInstrument.instrument_id == instrument_id)
        .order_by(Venue.code, VenueInstrument.provider_symbol, VenueInstrument.id)
    )
    return list(session.execute(stmt).all())  # type: ignore[arg-type]


def list_data_source_instruments_for_instrument(
    session: Session, instrument_id: uuid.UUID
) -> list[tuple[DataSourceInstrument, DataSource]]:
    stmt = (
        select(DataSourceInstrument, DataSource)
        .join(DataSource, DataSource.id == DataSourceInstrument.data_source_id)
        .where(DataSourceInstrument.instrument_id == instrument_id)
        .order_by(DataSource.code, DataSourceInstrument.provider_symbol, DataSourceInstrument.id)
    )
    return list(session.execute(stmt).all())  # type: ignore[arg-type]
