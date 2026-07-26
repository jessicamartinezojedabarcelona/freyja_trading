from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from freyja_backend.api.deps import CurrentUser, DbSession, PageParamsDep
from freyja_backend.application import execution_context_service
from freyja_backend.db.models.capability import ExecutionEnvironment
from freyja_backend.dto.execution_context import ExecutionContextOut
from freyja_backend.dto.pagination import Page

router = APIRouter(prefix="/execution-contexts", tags=["execution-contexts"])

# Deliberately identical whether the id does not exist at all or belongs to
# another owner — the repository query filters by owner_id in the same
# WHERE clause as the id, so there is no separate "found but not yours"
# branch to accidentally leak through a different message.
_CONTEXT_NOT_FOUND = "Contexto de ejecución no encontrado."


@router.get("", response_model=Page[ExecutionContextOut])
def list_execution_contexts(
    db: DbSession,
    current_user: CurrentUser,
    page: PageParamsDep,
    venue_id: Annotated[UUID | None, Query()] = None,
    product_type_id: Annotated[UUID | None, Query()] = None,
    execution_environment: Annotated[ExecutionEnvironment | None, Query()] = None,
) -> Page[ExecutionContextOut]:
    return execution_context_service.list_execution_contexts(
        db,
        owner_id=current_user.id,
        venue_id=venue_id,
        product_type_id=product_type_id,
        execution_environment=execution_environment,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/{context_id}", response_model=ExecutionContextOut)
def get_execution_context(
    context_id: UUID, db: DbSession, current_user: CurrentUser
) -> ExecutionContextOut:
    context = execution_context_service.get_execution_context(
        db, context_id=context_id, owner_id=current_user.id
    )
    if context is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_CONTEXT_NOT_FOUND)
    return context
