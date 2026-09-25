"""The `freyja-sync-candles` command, run against the real test database.

`main()` receives the engine and the provider instead of building its own, so
no environment patching is needed: the database is real, and only the external
provider is simulated.
"""

from collections.abc import Callable, Iterator

import httpx2
import pytest
from sqlalchemy import Engine, text

from freyja_backend.infrastructure.market_data.binance_spot_rest import (
    BinanceRestConfig,
    BinanceSpotRestClient,
)
from freyja_backend.infrastructure.market_data.kraken_spot_rest import (
    KrakenRestConfig,
    KrakenSpotRestClient,
)
from freyja_backend.scripts import sync_candles
from tests.market_data_support import NOW, SyntheticExchange, SyntheticKraken

pytestmark = pytest.mark.usefixtures("clean_market_data")


@pytest.fixture
def provider_for() -> Iterator[Callable[[SyntheticExchange], BinanceSpotRestClient]]:
    created: list[BinanceSpotRestClient] = []

    def build(exchange: SyntheticExchange) -> BinanceSpotRestClient:
        client = BinanceSpotRestClient(
            BinanceRestConfig(max_attempts=1),
            transport=httpx2.MockTransport(exchange),
            clock=lambda: NOW,
            sleep=lambda _seconds: None,
        )
        created.append(client)
        return client

    yield build
    for client in created:
        client.close()


def run_cli(args: list[str], *, engine: Engine, provider: BinanceSpotRestClient) -> int:
    # A fixed clock: the window a backfill may reach must not depend on the wall clock.
    return sync_candles.main(args, engine=engine, provider=provider, clock=lambda: NOW)


def stored_by_timeframe(engine: Engine) -> dict[str, int]:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT t.code, count(*) FROM freyja2_candles c "
                "JOIN freyja2_timeframes t ON t.id = c.timeframe_id GROUP BY t.code"
            )
        ).all()
    return {str(row[0]): int(row[1]) for row in rows}


def test_defaults_to_the_one_minute_timeframe(
    market_data_engine: Engine,
    provider_for: Callable[[SyntheticExchange], BinanceSpotRestClient],
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = run_cli(
        ["--symbol", "BTC/USDT", "--limit", "5"],
        engine=market_data_engine,
        provider=provider_for(SyntheticExchange()),
    )

    assert exit_code == 0
    assert stored_by_timeframe(market_data_engine) == {"1m": 4}
    out = capsys.readouterr().out
    assert "BINANCE BTC/USDT 1m: OK; nuevas 4, ya existentes 0, revisadas 0." in out
    assert "OPEN_CANDLE_EXCLUDED" in out


def test_the_user_can_pick_another_timeframe(
    market_data_engine: Engine,
    provider_for: Callable[[SyntheticExchange], BinanceSpotRestClient],
) -> None:
    exit_code = run_cli(
        ["--symbol", "ETH/USDT", "--timeframe", "5m", "--limit", "4"],
        engine=market_data_engine,
        provider=provider_for(SyntheticExchange()),
    )

    assert exit_code == 0
    assert stored_by_timeframe(market_data_engine) == {"5m": 3}  # 12:05 is still open


def test_running_it_twice_is_safe(
    market_data_engine: Engine,
    provider_for: Callable[[SyntheticExchange], BinanceSpotRestClient],
    capsys: pytest.CaptureFixture[str],
) -> None:
    provider = provider_for(SyntheticExchange())
    args = ["--symbol", "BTC/USDT", "--limit", "5"]
    assert run_cli(args, engine=market_data_engine, provider=provider) == 0
    capsys.readouterr()

    assert run_cli(args, engine=market_data_engine, provider=provider) == 0

    assert "nuevas 0, ya existentes 4" in capsys.readouterr().out
    assert stored_by_timeframe(market_data_engine) == {"1m": 4}


def test_an_unavailable_provider_exits_with_1_and_stores_nothing(
    market_data_engine: Engine,
    provider_for: Callable[[SyntheticExchange], BinanceSpotRestClient],
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = run_cli(
        ["--symbol", "BTC/USDT"],
        engine=market_data_engine,
        provider=provider_for(SyntheticExchange(failing_calls=frozenset({1}))),
    )

    assert exit_code == 1
    assert stored_by_timeframe(market_data_engine) == {}
    assert "UNAVAILABLE" in capsys.readouterr().out


def test_a_bounded_backfill_reports_completion(
    market_data_engine: Engine,
    provider_for: Callable[[SyntheticExchange], BinanceSpotRestClient],
    capsys: pytest.CaptureFixture[str],
) -> None:
    args = [
        "--symbol",
        "BTC/USDT",
        "--timeframe",
        "5m",
        "--start",
        "2026-09-24T11:00:00+00:00",
        "--end",
        "2026-09-24T13:00:00+02:00",  # 11:00 UTC: an empty window is a completed no-op
    ]
    assert run_cli(args, engine=market_data_engine, provider=provider_for(SyntheticExchange())) == 0
    assert "completo" in capsys.readouterr().out
    assert stored_by_timeframe(market_data_engine) == {}

    args[-1] = "2026-09-24T11:30:00+00:00"
    exchange = SyntheticExchange()
    assert run_cli(args, engine=market_data_engine, provider=provider_for(exchange)) == 0
    assert stored_by_timeframe(market_data_engine) == {"5m": 6}
    assert "nuevas 6" in capsys.readouterr().out


def test_an_incomplete_backfill_exits_with_1_so_it_can_be_repeated(
    market_data_engine: Engine,
    provider_for: Callable[[SyntheticExchange], BinanceSpotRestClient],
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = run_cli(
        [
            "--symbol",
            "BTC/USDT",
            "--timeframe",
            "5m",
            "--start",
            "2026-09-24T11:00:00+00:00",
            "--end",
            "2026-09-24T11:30:00+00:00",
        ],
        engine=market_data_engine,
        provider=provider_for(SyntheticExchange(failing_calls=frozenset({1}))),
    )

    assert exit_code == 1
    assert "INCOMPLETO: repite el comando" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["--symbol", "DOGE/USDT"], "not active in the catalog"),
        (["--symbol", "EUR/USD", "--market", "FOREX"], "no active analysis mapping"),
        (
            ["--symbol", "BTC/USDT", "--end", "2026-09-24T11:30:00+00:00"],
            "--end solo tiene sentido",
        ),
        (
            ["--symbol", "BTC/USDT", "--start", "2026-01-01T00:00:00+00:00"],
            "exceeds the limit of 10000",
        ),
    ],
)
def test_bad_input_exits_with_2_and_touches_nothing(
    market_data_engine: Engine,
    provider_for: Callable[[SyntheticExchange], BinanceSpotRestClient],
    capsys: pytest.CaptureFixture[str],
    args: list[str],
    message: str,
) -> None:
    exchange = SyntheticExchange()

    exit_code = run_cli(args, engine=market_data_engine, provider=provider_for(exchange))

    assert exit_code == 2
    assert message in capsys.readouterr().err
    assert exchange.requests == []
    assert stored_by_timeframe(market_data_engine) == {}


@pytest.mark.parametrize(
    "args",
    [
        ["--symbol", "BTC/USDT", "--start", "2026-09-24T11:00:00"],  # no time zone
        ["--symbol", "BTC/USDT", "--start", "yesterday"],
        ["--symbol", "BTC/USDT", "--timeframe", "30s"],
        ["--symbol", "BTC/USDT", "--source", "NOWHERE"],
        ["--timeframe", "5m"],  # symbol is required
    ],
)
def test_malformed_arguments_are_rejected_by_the_parser(
    market_data_engine: Engine,
    provider_for: Callable[[SyntheticExchange], BinanceSpotRestClient],
    args: list[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        run_cli(args, engine=market_data_engine, provider=provider_for(SyntheticExchange()))
    assert raised.value.code == 2


# -- Kraken as a source (MARKET-DATA-KRAKEN-REST-001) ------------------------------------------


@pytest.fixture
def kraken_provider() -> Iterator[Callable[[SyntheticKraken], KrakenSpotRestClient]]:
    created: list[KrakenSpotRestClient] = []

    def build(kraken: SyntheticKraken) -> KrakenSpotRestClient:
        client = KrakenSpotRestClient(
            KrakenRestConfig(max_attempts=1, min_request_interval_seconds=0.0),
            transport=httpx2.MockTransport(kraken),
            clock=lambda: NOW,
            sleep=lambda _seconds: None,
        )
        created.append(client)
        return client

    yield build
    for client in created:
        client.close()


def test_the_source_can_be_kraken_and_is_stored_under_kraken(
    market_data_engine: Engine,
    kraken_provider: Callable[[SyntheticKraken], KrakenSpotRestClient],
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = sync_candles.main(
        ["--source", "KRAKEN", "--symbol", "BTC/USDT", "--limit", "5"],
        engine=market_data_engine,
        provider=kraken_provider(SyntheticKraken()),
        clock=lambda: NOW,
    )

    assert exit_code == 0
    assert "KRAKEN BTC/USDT 1m: OK; nuevas 5, ya existentes 0, revisadas 0." in (
        capsys.readouterr().out
    )
    with market_data_engine.connect() as connection:
        sources = connection.execute(
            text(
                "SELECT s.code, count(*) FROM freyja2_candles c "
                "JOIN freyja2_data_sources s ON s.id = c.data_source_id GROUP BY s.code"
            )
        ).all()
    assert [(row[0], row[1]) for row in sources] == [("KRAKEN", 5)]


def test_a_backfill_from_kraken_pages_by_kraken_s_own_limit(
    market_data_engine: Engine,
    kraken_provider: Callable[[SyntheticKraken], KrakenSpotRestClient],
) -> None:
    """The CLI must not assume Binance's 1000-candle page: Kraken serves at most 720."""
    kraken = SyntheticKraken()
    exit_code = sync_candles.main(
        [
            "--source",
            "KRAKEN",
            "--symbol",
            "BTC/USDT",
            "--start",
            "2026-09-24T02:00:00+00:00",  # 10 h before NOW: 600 one-minute candles
            "--end",
            "2026-09-24T12:00:00+00:00",
        ],
        engine=market_data_engine,
        provider=kraken_provider(kraken),
        clock=lambda: NOW,
    )

    assert exit_code == 0
    assert stored_by_timeframe(market_data_engine) == {"1m": 600}
    assert len(kraken.requests) == 1  # one page of 720 covers it; 1000 would have been refused
