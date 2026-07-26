from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from freyja_backend.api.deps import CurrentUser, DbSession, PageParamsDep
from freyja_backend.application import capability_service
from freyja_backend.dto.capability import TechnicalCapabilityOut
from freyja_backend.dto.pagination import Page

router = APIRouter(prefix="/capabilities", tags=["capabilities"])

_CAPABILITY_NOT_FOUND = "Capacidad técnica no encontrada."


@router.get("", response_model=Page[TechnicalCapabilityOut])
def list_capabilities(
    db: DbSession,
    _current_user: CurrentUser,
    page: PageParamsDep,
    instrument_id: Annotated[UUID | None, Query()] = None,
    venue_id: Annotated[UUID | None, Query()] = None,
    data_source_id: Annotated[UUID | None, Query()] = None,
    timeframe_id: Annotated[UUID | None, Query()] = None,
    include_history: Annotated[bool, Query()] = False,
) -> Page[TechnicalCapabilityOut]:
    return capability_service.list_capabilities(
        db,
        instrument_id=instrument_id,
        venue_id=venue_id,
        data_source_id=data_source_id,
        timeframe_id=timeframe_id,
        include_history=include_history,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/{capability_id}", response_model=TechnicalCapabilityOut)
def get_capability(
    capability_id: UUID, db: DbSession, _current_user: CurrentUser
) -> TechnicalCapabilityOut:
    capability = capability_service.get_capability(db, capability_id)
    if capability is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_CAPABILITY_NOT_FOUND)
    return capability
