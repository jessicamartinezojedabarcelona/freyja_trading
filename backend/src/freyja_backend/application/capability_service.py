import uuid

from sqlalchemy.orm import Session

from freyja_backend.dto.capability import (
    CapabilityProviderRef,
    InstrumentRef,
    TechnicalCapabilityOut,
)
from freyja_backend.dto.catalog import TimeframeRef
from freyja_backend.dto.pagination import Page
from freyja_backend.repositories import capability_repository
from freyja_backend.repositories.capability_repository import CapabilityRow


def _provider_ref(row: CapabilityRow) -> CapabilityProviderRef:
    # Exactly one of venue/data_source is set per row — enforced physically
    # by ck_freyja2_technical_capabilities_exactly_one_provider_axis. Never
    # reinterpreted or defaulted here.
    if row.venue is not None:
        return CapabilityProviderRef(
            kind="venue", id=row.venue.id, code=row.venue.code, display_name=row.venue.display_name
        )
    assert row.data_source is not None
    return CapabilityProviderRef(
        kind="data_source",
        id=row.data_source.id,
        code=row.data_source.code,
        display_name=row.data_source.display_name,
    )


def _capability_out(row: CapabilityRow) -> TechnicalCapabilityOut:
    capability = row.capability
    return TechnicalCapabilityOut(
        id=capability.id,
        instrument=InstrumentRef(
            instrument_id=row.instrument.instrument_id,
            canonical_symbol=row.instrument.canonical_symbol,
        ),
        timeframe=TimeframeRef(
            id=row.timeframe.id,
            code=row.timeframe.code,
            display_name=row.timeframe.display_name,
            duration_seconds=row.timeframe.duration_seconds,
        ),
        provider=_provider_ref(row),
        market_data_status=capability.market_data_status,
        signal_detection_status=capability.signal_detection_status,
        backtest_status=capability.backtest_status,
        demo_execution_status=capability.demo_execution_status,
        real_execution_status=capability.real_execution_status,
        settlement_status=capability.settlement_status,
        reason_unavailable=capability.reason_unavailable,
        effective_from=capability.effective_from,
        effective_to=capability.effective_to,
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
) -> Page[TechnicalCapabilityOut]:
    rows, total = capability_repository.list_capabilities(
        session,
        instrument_id=instrument_id,
        venue_id=venue_id,
        data_source_id=data_source_id,
        timeframe_id=timeframe_id,
        include_history=include_history,
        limit=limit,
        offset=offset,
    )
    return Page(items=[_capability_out(r) for r in rows], total=total, limit=limit, offset=offset)


def get_capability(session: Session, capability_id: uuid.UUID) -> TechnicalCapabilityOut | None:
    row = capability_repository.get_capability(session, capability_id)
    if row is None:
        return None
    return _capability_out(row)
