from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from freyja_backend.api.deps import CurrentUser, DbSession, PageParamsDep
from freyja_backend.application import catalog_service, provider_service
from freyja_backend.dto.catalog import InstrumentOut
from freyja_backend.dto.pagination import Page
from freyja_backend.dto.provider import DataSourceOut, InstrumentMappingsOut, VenueOut

router = APIRouter(prefix="/catalog", tags=["catalog"])

_INSTRUMENT_NOT_FOUND = "Instrumento no encontrado."


@router.get("/instruments", response_model=Page[InstrumentOut])
def list_instruments(
    db: DbSession,
    _current_user: CurrentUser,
    page: PageParamsDep,
    market_code: Annotated[str | None, Query()] = None,
    product_type_code: Annotated[str | None, Query()] = None,
    symbol: Annotated[str | None, Query()] = None,
    timeframe_code: Annotated[str | None, Query()] = None,
    is_active: Annotated[bool | None, Query()] = None,
) -> Page[InstrumentOut]:
    return catalog_service.list_instruments(
        db,
        market_code=market_code,
        product_type_code=product_type_code,
        symbol=symbol,
        timeframe_code=timeframe_code,
        is_active=is_active,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/instruments/{instrument_id}", response_model=InstrumentOut)
def get_instrument(instrument_id: UUID, db: DbSession, _current_user: CurrentUser) -> InstrumentOut:
    instrument = catalog_service.get_instrument(db, instrument_id)
    if instrument is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_INSTRUMENT_NOT_FOUND)
    return instrument


@router.get("/instruments/{instrument_id}/mappings", response_model=InstrumentMappingsOut)
def get_instrument_mappings(
    instrument_id: UUID, db: DbSession, _current_user: CurrentUser
) -> InstrumentMappingsOut:
    mappings = provider_service.get_instrument_mappings(db, instrument_id)
    if mappings is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_INSTRUMENT_NOT_FOUND)
    return mappings


@router.get("/venues", response_model=Page[VenueOut])
def list_venues(
    db: DbSession,
    _current_user: CurrentUser,
    page: PageParamsDep,
    is_active: Annotated[bool | None, Query()] = None,
) -> Page[VenueOut]:
    return provider_service.list_venues(
        db, is_active=is_active, limit=page.limit, offset=page.offset
    )


@router.get("/data-sources", response_model=Page[DataSourceOut])
def list_data_sources(
    db: DbSession,
    _current_user: CurrentUser,
    page: PageParamsDep,
    is_active: Annotated[bool | None, Query()] = None,
) -> Page[DataSourceOut]:
    return provider_service.list_data_sources(
        db, is_active=is_active, limit=page.limit, offset=page.offset
    )
