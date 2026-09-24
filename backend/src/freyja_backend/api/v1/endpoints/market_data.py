from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from freyja_backend.api.deps import ClockDep, CurrentUser, DbSession
from freyja_backend.application import market_data_query_service
from freyja_backend.application.market_data_query_service import (
    DEFAULT_TIMEFRAME_CODE,
    MAX_LIMIT,
    MarketDataInvalidQueryError,
    MarketDataNotFoundError,
)
from freyja_backend.dto.market_data import CandleSeriesOut

router = APIRouter(prefix="/market-data", tags=["market-data"])


@router.get("/candles", response_model=CandleSeriesOut)
def get_candles(
    db: DbSession,
    _current_user: CurrentUser,
    clock: ClockDep,
    instrument_id: Annotated[UUID, Query(description="Instrumento del catálogo.")],
    data_source_code: Annotated[str, Query(description="Código de la fuente, p. ej. BINANCE.")],
    timeframe_code: Annotated[
        str, Query(description="Periodo de las velas; por defecto 1m.")
    ] = DEFAULT_TIMEFRAME_CODE,
    start: Annotated[
        datetime | None, Query(description="Leer hacia delante desde este instante (con zona).")
    ] = None,
    end: Annotated[
        datetime | None, Query(description="Excluye velas que abren en o después de este instante.")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = 500,
) -> CandleSeriesOut:
    """Velas cerradas guardadas de una serie, con su frescura, huecos y estado del proveedor.

    Solo lee lo almacenado; nunca consulta al proveedor. Si `quality` no es `OK`,
    la respuesta debe mostrarse como degradada.
    """
    try:
        return market_data_query_service.get_candle_series(
            db,
            instrument_id=instrument_id,
            data_source_code=data_source_code,
            timeframe_code=timeframe_code,
            start=start,
            end=end,
            limit=limit,
            now=clock(),
        )
    except MarketDataNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from None
    except MarketDataInvalidQueryError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from None
