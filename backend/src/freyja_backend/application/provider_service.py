import uuid

from sqlalchemy.orm import Session

from freyja_backend.db.models.provider import (
    DataSource,
    DataSourceInstrument,
    Venue,
    VenueInstrument,
)
from freyja_backend.dto.pagination import Page
from freyja_backend.dto.provider import (
    DataSourceInstrumentOut,
    DataSourceOut,
    InstrumentMappingsOut,
    VenueInstrumentOut,
    VenueOut,
)
from freyja_backend.repositories import catalog_repository, provider_repository


def _venue_out(venue: Venue) -> VenueOut:
    return VenueOut(
        id=venue.id,
        code=venue.code,
        display_name=venue.display_name,
        venue_type=venue.venue_type,
        is_active=venue.is_active,
    )


def _data_source_out(data_source: DataSource) -> DataSourceOut:
    return DataSourceOut(
        id=data_source.id,
        code=data_source.code,
        display_name=data_source.display_name,
        source_type=data_source.source_type,
        is_active=data_source.is_active,
    )


def list_venues(
    session: Session, *, is_active: bool | None = None, limit: int, offset: int
) -> Page[VenueOut]:
    rows, total = provider_repository.list_venues(
        session, is_active=is_active, limit=limit, offset=offset
    )
    return Page(items=[_venue_out(v) for v in rows], total=total, limit=limit, offset=offset)


def list_data_sources(
    session: Session, *, is_active: bool | None = None, limit: int, offset: int
) -> Page[DataSourceOut]:
    rows, total = provider_repository.list_data_sources(
        session, is_active=is_active, limit=limit, offset=offset
    )
    return Page(
        items=[_data_source_out(ds) for ds in rows], total=total, limit=limit, offset=offset
    )


def _venue_instrument_out(venue_instrument: VenueInstrument, venue: Venue) -> VenueInstrumentOut:
    return VenueInstrumentOut(
        id=venue_instrument.id,
        venue=_venue_out(venue),
        provider_symbol=venue_instrument.provider_symbol,
        provider_contract_id=venue_instrument.provider_contract_id,
        is_active=venue_instrument.is_active,
    )


def _data_source_instrument_out(
    data_source_instrument: DataSourceInstrument, data_source: DataSource
) -> DataSourceInstrumentOut:
    return DataSourceInstrumentOut(
        id=data_source_instrument.id,
        data_source=_data_source_out(data_source),
        provider_symbol=data_source_instrument.provider_symbol,
        purpose=data_source_instrument.purpose,
        is_active=data_source_instrument.is_active,
    )


def get_instrument_mappings(
    session: Session, instrument_id: uuid.UUID
) -> InstrumentMappingsOut | None:
    # Existence is proven the same way a plain instrument lookup would: an
    # instrument with zero mappings and a non-existent instrument id must not
    # be confused — both otherwise yield the same empty lists below.
    instrument_row = catalog_repository.get_instrument(session, instrument_id)
    if instrument_row is None:
        return None

    venue_rows = provider_repository.list_venue_instruments_for_instrument(session, instrument_id)
    data_source_rows = provider_repository.list_data_source_instruments_for_instrument(
        session, instrument_id
    )
    return InstrumentMappingsOut(
        instrument_id=instrument_id,
        venue_instruments=[_venue_instrument_out(vi, v) for vi, v in venue_rows],
        data_source_instruments=[
            _data_source_instrument_out(dsi, ds) for dsi, ds in data_source_rows
        ],
    )
