"""Sync market-data candles into PostgreSQL (MARKET-DATA-PERSISTENCE-001).

Reads public candles from the configured provider and stores the closed ones.
Safe to repeat: stored candles are never duplicated or rewritten.

    freyja-sync-candles --symbol BTC/USDT                       # latest 500, 1m
    freyja-sync-candles --symbol BTC/USDT --timeframe 5m --limit 200
    freyja-sync-candles --symbol BTC/USDT --start 2026-09-20T00:00:00+00:00 \\
        --end 2026-09-21T00:00:00+00:00                         # bounded backfill

Exit code: 0 data stored (OK or DEGRADED), 1 provider unavailable, 2 bad input.
"""

import argparse
import sys
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy.engine import Engine

from freyja_backend.application import market_data_service
from freyja_backend.core.database import create_database_engine
from freyja_backend.db.session import create_session_factory, session_scope
from freyja_backend.domain.market_data import (
    CandleProvider,
    Clock,
    DataQuality,
    InstrumentRef,
    MarketDataRequestError,
    Timeframe,
    utc_now,
)
from freyja_backend.infrastructure.market_data.binance_spot_rest import (
    SOURCE_CODE as BINANCE,
)
from freyja_backend.infrastructure.market_data.binance_spot_rest import BinanceSpotRestClient
from freyja_backend.infrastructure.market_data.kraken_spot_rest import (
    SOURCE_CODE as KRAKEN,
)
from freyja_backend.infrastructure.market_data.kraken_spot_rest import KrakenSpotRestClient

# 1 minute is Freyja's standard candle period; the user may pick another.
DEFAULT_TIMEFRAME = Timeframe.M1
_CLIENTS = {BINANCE: BinanceSpotRestClient, KRAKEN: KrakenSpotRestClient}
_SUPPORTED_SOURCES = tuple(_CLIENTS)


def _parse_utc(value: str) -> datetime:
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"fecha no válida: {value!r} (usa ISO 8601)") from None
    if moment.tzinfo is None:
        raise argparse.ArgumentTypeError(
            f"la fecha {value!r} no indica zona horaria; añade p. ej. +00:00"
        )
    return moment.astimezone(UTC)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="freyja-sync-candles",
        description="Sincroniza velas cerradas desde un proveedor público a PostgreSQL.",
    )
    parser.add_argument("--source", default=BINANCE, choices=_SUPPORTED_SOURCES)
    parser.add_argument("--market", default="CRYPTO")
    parser.add_argument("--product", default="SPOT")
    parser.add_argument("--symbol", required=True, help="Símbolo canónico, p. ej. BTC/USDT")
    parser.add_argument(
        "--timeframe",
        default=DEFAULT_TIMEFRAME.value,
        choices=[timeframe.value for timeframe in Timeframe],
        help=f"Periodo de las velas (por defecto {DEFAULT_TIMEFRAME.value})",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=500,
        help="Velas recientes a leer (máximo del proveedor: Binance 1000, Kraken 720)",
    )
    parser.add_argument("--start", type=_parse_utc, help="Inicio de un backfill (con zona horaria)")
    parser.add_argument("--end", type=_parse_utc, help="Fin del backfill; por defecto, ahora")
    parser.add_argument(
        "--max-candles",
        type=int,
        default=market_data_service.MAX_BACKFILL_CANDLES,
        help="Tope de velas de un backfill",
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    engine: Engine | None = None,
    provider: CandleProvider | None = None,
    clock: Clock = utc_now,
) -> int:
    args = _build_parser().parse_args(argv)
    if args.end is not None and args.start is None:
        print("--end solo tiene sentido junto con --start.", file=sys.stderr)
        return 2

    owns_engine = engine is None
    db_engine = engine if engine is not None else create_database_engine()
    try:
        if provider is not None:
            return _run(args, provider, db_engine, clock)
        with _CLIENTS[args.source]() as client:
            return _run(args, client, db_engine, clock)
    finally:
        if owns_engine:
            db_engine.dispose()


def _run(args: argparse.Namespace, provider: CandleProvider, engine: Engine, clock: Clock) -> int:
    instrument = InstrumentRef(args.market, args.product, args.symbol)
    timeframe = Timeframe(args.timeframe)
    label = f"{args.source} {args.symbol} {timeframe.value}"
    with session_scope(create_session_factory(engine)) as session:
        try:
            if args.start is None:
                result = market_data_service.sync_candles(
                    session,
                    provider,
                    source_code=args.source,
                    instrument=instrument,
                    timeframe=timeframe,
                    limit=args.limit,
                )
                session.commit()
                print(
                    f"{label}: {result.quality.value}; nuevas {result.inserted}, "
                    f"ya existentes {result.unchanged}, revisadas {len(result.revised)}."
                )
                for issue in result.issues:
                    print(f"  - {issue.code.value}: {issue.detail}")
                return 1 if result.quality is DataQuality.UNAVAILABLE else 0

            backfill = market_data_service.backfill_candles(
                session,
                provider,
                source_code=args.source,
                instrument=instrument,
                timeframe=timeframe,
                start=args.start,
                end=args.end or clock(),
                max_candles=args.max_candles,
                clock=clock,
            )
            print(
                f"{label}: {backfill.quality.value}; páginas {backfill.pages}, "
                f"nuevas {backfill.inserted}, ya existentes {backfill.unchanged}, "
                f"revisadas {backfill.revised}; "
                f"{'completo' if backfill.completed else 'INCOMPLETO: repite el comando'}."
            )
            return 0 if backfill.completed else 1
        except (
            market_data_service.MarketDataConfigurationError,
            market_data_service.MarketDataIntegrityError,
            MarketDataRequestError,
        ) as exc:
            session.rollback()
            print(f"No se sincronizó nada: {exc}", file=sys.stderr)
            return 2


if __name__ == "__main__":
    raise SystemExit(main())
