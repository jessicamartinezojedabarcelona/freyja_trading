import uuid
from dataclasses import dataclass

from sqlalchemy import Select, and_, func, select
from sqlalchemy.orm import Session

from freyja_backend.db.models.capability import ExecutionContext, ExecutionEnvironment
from freyja_backend.db.models.catalog import ProductType
from freyja_backend.db.models.provider import Venue

# Read-only queries for ExecutionContext (POINT1-CAPABILITY-001). owner_id is
# always part of the WHERE clause of every single-row/list lookup below —
# never applied as a post-fetch filter in Python — so that "does not exist"
# and "exists but belongs to another owner" are indistinguishable: the same
# query, the same empty result, no enumeration signal either way.

_ExecutionContextRow = tuple[ExecutionContext, Venue, ProductType]


@dataclass(frozen=True)
class ExecutionContextRow:
    execution_context: ExecutionContext
    venue: Venue
    product_type: ProductType


def _execution_context_select() -> Select[_ExecutionContextRow]:
    return (
        select(ExecutionContext, Venue, ProductType)
        .join(Venue, Venue.id == ExecutionContext.venue_id)
        .join(ProductType, ProductType.id == ExecutionContext.product_type_id)
    )


def list_execution_contexts(
    session: Session,
    *,
    owner_id: uuid.UUID,
    venue_id: uuid.UUID | None = None,
    product_type_id: uuid.UUID | None = None,
    execution_environment: ExecutionEnvironment | None = None,
    limit: int,
    offset: int,
) -> tuple[list[ExecutionContextRow], int]:
    conditions = [ExecutionContext.owner_id == owner_id]
    if venue_id is not None:
        conditions.append(ExecutionContext.venue_id == venue_id)
    if product_type_id is not None:
        conditions.append(ExecutionContext.product_type_id == product_type_id)
    if execution_environment is not None:
        conditions.append(ExecutionContext.execution_environment == execution_environment)

    stmt = _execution_context_select().where(and_(*conditions))

    total = session.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()

    stmt = (
        stmt.order_by(
            ExecutionContext.venue_id,
            ExecutionContext.account_key,
            ExecutionContext.execution_environment,
            ExecutionContext.product_type_id,
            ExecutionContext.id,
        )
        .limit(limit)
        .offset(offset)
    )

    rows = [
        ExecutionContextRow(
            execution_context=execution_context, venue=venue, product_type=product_type
        )
        for execution_context, venue, product_type in session.execute(stmt).all()
    ]
    return rows, total


def get_execution_context(
    session: Session, *, context_id: uuid.UUID, owner_id: uuid.UUID
) -> ExecutionContextRow | None:
    stmt = _execution_context_select().where(
        ExecutionContext.id == context_id, ExecutionContext.owner_id == owner_id
    )
    row = session.execute(stmt).first()
    if row is None:
        return None
    execution_context, venue, product_type = row
    return ExecutionContextRow(
        execution_context=execution_context, venue=venue, product_type=product_type
    )
