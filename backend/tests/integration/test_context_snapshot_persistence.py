"""Context snapshots against real PostgreSQL (POINT2-SNAPSHOT-001).

Nothing is simulated: snapshots are captured from real candles by the real classifier and
policy, stored through the real service in a database migrated by the real migrations, and
every assertion reads back from PostgreSQL.
"""

import json
import uuid
from collections.abc import Callable, Iterator, Mapping
from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from freyja_backend.application import context_snapshot_service as service
from freyja_backend.application.context_snapshot_service import (
    SnapshotIntegrityError,
    UnknownSnapshotReferenceError,
    load_context_snapshot,
    store_context_snapshot,
)
from freyja_backend.db.session import create_session_factory
from freyja_backend.domain.context_snapshot import ContextSnapshot
from freyja_backend.domain.market_calendar import MarketSchedule
from freyja_backend.domain.market_data import DataQuality
from freyja_backend.domain.market_trend import TrendParams, TrendState
from freyja_backend.domain.trend_policy import PolicyOutcome, PolicyReason, TrendRelationship
from tests.unit.test_context_snapshot import capture, policy
from tests.unit.test_market_trend import DOWN as DOWN_EXTREMES
from tests.unit.test_market_trend import EURUSD
from tests.unit.test_market_trend import UP as UP_EXTREMES


@pytest.fixture
def instrument_id(market_data_session: Session) -> str:
    """The catalog's own id for BTC/USDT: a snapshot names a real instrument."""
    found = market_data_session.execute(
        text("SELECT instrument_id FROM freyja2_instruments WHERE canonical_symbol = 'BTC/USDT'")
    ).scalar_one()
    return str(found)


@pytest.fixture
def clean_snapshots(market_data_engine: Engine) -> Iterator[None]:
    with market_data_engine.begin() as connection:
        connection.execute(text("TRUNCATE freyja2_context_snapshots"))
    yield


@pytest.fixture
def session(
    market_data_engine: Engine, clean_snapshots: None, clean_market_data: None
) -> Iterator[Session]:
    del clean_snapshots, clean_market_data
    opened = create_session_factory(market_data_engine)()
    try:
        yield opened
        opened.commit()
    finally:
        opened.close()


def snapshot_of(instrument_id: str, **overrides: Any) -> ContextSnapshot:
    return capture(instrument_id=instrument_id, **overrides)


def count(session: Session) -> int:
    return int(session.execute(text("SELECT COUNT(*) FROM freyja2_context_snapshots")).scalar_one())


# -- keeping a snapshot and reading it back -----------------------------------------------------


def test_a_snapshot_is_stored_and_read_back_exactly(session: Session, instrument_id: str) -> None:
    snapshot = snapshot_of(instrument_id)

    result = store_context_snapshot(session, snapshot)
    session.commit()

    assert (result.snapshot_id, result.inserted) == (snapshot.snapshot_id, True)
    with_a_fresh_session = load_context_snapshot(session, snapshot.snapshot_id)
    assert with_a_fresh_session == snapshot
    assert with_a_fresh_session.document() == snapshot.document()


def test_every_kind_of_snapshot_survives_the_database(session: Session, instrument_id: str) -> None:
    snapshots = [
        snapshot_of(instrument_id),
        snapshot_of(instrument_id, signal_extremes=UP_EXTREMES, context_extremes=DOWN_EXTREMES),
        snapshot_of(instrument_id, context_candles=[]),  # INSUFFICIENT_DATA and its reasons
        snapshot_of(instrument_id, trend_policy=None),  # no policy declared
        snapshot_of(
            instrument_id,
            instrument=EURUSD,
            schedule=MarketSchedule.FOREX_WEEKLY,
        ),  # a Forex session
    ]
    for snapshot in snapshots:
        store_context_snapshot(session, snapshot)
    session.commit()
    session.expire_all()

    assert count(session) == len({s.snapshot_id for s in snapshots})
    for snapshot in snapshots:
        assert load_context_snapshot(session, snapshot.snapshot_id) == snapshot


def test_insufficient_data_is_stored_with_its_reasons(session: Session, instrument_id: str) -> None:
    snapshot = snapshot_of(instrument_id, context_candles=[])
    store_context_snapshot(session, snapshot)
    session.commit()

    row = session.execute(
        text(
            "SELECT signal_trend, context_trend, context_data_quality::text, policy_outcome,"
            " context_compatible, reasons,"
            " document #>> '{observed,context,insufficient_data_reasons}'"
            " FROM freyja2_context_snapshots"
        )
    ).one()
    assert row[0] == TrendState.UPTREND.value
    assert row[1] == TrendState.INSUFFICIENT_DATA.value
    assert row[2] == DataQuality.UNAVAILABLE.value
    assert row[3] == PolicyOutcome.INSUFFICIENT_CONTEXT.value
    assert row[4] is None  # neither compatible nor incompatible
    assert PolicyReason.CONTEXT_TREND_INSUFFICIENT.value in row[5]
    assert "NO_DATA" in row[6]


def test_the_key_facts_can_be_searched_without_opening_the_document(
    session: Session, instrument_id: str
) -> None:
    store_context_snapshot(session, snapshot_of(instrument_id))
    store_context_snapshot(
        session,
        snapshot_of(instrument_id, signal_extremes=UP_EXTREMES, context_extremes=DOWN_EXTREMES),
    )
    store_context_snapshot(session, snapshot_of(instrument_id, trend_policy=None))
    session.commit()

    def rows(where: str) -> int:
        return int(
            session.execute(
                text(f"SELECT COUNT(*) FROM freyja2_context_snapshots WHERE {where}")
            ).scalar_one()
        )

    assert rows("context_compatible IS TRUE") == 1
    assert rows("context_compatible IS FALSE") == 1
    assert rows("context_compatible IS NULL") == 1
    assert rows("policy_version IS NULL") == 1
    assert rows("context_trend = 'DOWNTREND'") == 1
    assert rows("required_relationship = 'WITH_TREND'") == 2
    assert rows("market_session IS NULL") == 3  # crypto: no session, none borrowed


# -- one observation, one snapshot ---------------------------------------------------------------


def test_the_same_observation_is_stored_once_and_the_first_is_kept(
    session: Session, instrument_id: str
) -> None:
    first = snapshot_of(instrument_id, computed_after=timedelta(seconds=1))
    again = snapshot_of(instrument_id, computed_after=timedelta(hours=6))

    assert store_context_snapshot(session, first).inserted is True
    second = store_context_snapshot(session, again)
    session.commit()

    assert second.inserted is False and second.snapshot_id == first.snapshot_id
    assert count(session) == 1
    kept = load_context_snapshot(session, first.snapshot_id)
    assert kept is not None and kept.computed_at == first.computed_at  # not the later attempt


def test_a_reclassification_is_a_new_snapshot_and_the_old_one_is_untouched(
    session: Session, instrument_id: str
) -> None:
    original = snapshot_of(instrument_id)
    store_context_snapshot(session, original)
    session.commit()
    before = load_context_snapshot(session, original.snapshot_id)

    other_definition = snapshot_of(
        instrument_id, params=TrendParams(window_swings=4, significance=Decimal("0.40"))
    )
    store_context_snapshot(session, other_definition)
    session.commit()
    session.expire_all()

    assert count(session) == 2
    assert load_context_snapshot(session, original.snapshot_id) == before == original
    assert load_context_snapshot(session, other_definition.snapshot_id) == other_definition


def test_asking_for_a_snapshot_that_does_not_exist_gives_none(session: Session) -> None:
    assert load_context_snapshot(session, uuid.uuid4()) is None


# -- immutable ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "assignment",
    [
        "policy_outcome = 'INCOMPATIBLE'",
        "context_compatible = NOT context_compatible",
        "signal_trend = 'RANGE'",
        "document = '{}'::jsonb",
        "computed_at = computed_at + interval '1 day'",
        "reasons = ARRAY['X']",
        "content_hash = repeat('a', 64)",
    ],
)
def test_no_column_of_a_stored_snapshot_can_be_rewritten(
    session: Session, instrument_id: str, assignment: str
) -> None:
    store_context_snapshot(session, snapshot_of(instrument_id))
    session.commit()

    with pytest.raises(DBAPIError, match="immutable"):
        session.execute(text(f"UPDATE freyja2_context_snapshots SET {assignment}"))
    session.rollback()

    assert count(session) == 1


def test_an_upsert_can_not_overwrite_a_stored_snapshot(
    session: Session, instrument_id: str
) -> None:
    snapshot = snapshot_of(instrument_id)
    store_context_snapshot(session, snapshot)
    session.commit()

    with pytest.raises(DBAPIError, match="immutable"):
        _raw_insert(
            session,
            snapshot,
            keep_identity=True,
            tail=" ON CONFLICT (id) DO UPDATE SET policy_outcome = 'INCOMPATIBLE'",
        )
    session.rollback()
    kept = load_context_snapshot(session, snapshot.snapshot_id)
    assert kept is not None and kept.outcome is PolicyOutcome.COMPATIBLE


# -- the database refuses a record that contradicts itself -----------------------------------------


def _raw_insert(
    session: Session,
    snapshot: ContextSnapshot,
    *,
    changes: Mapping[str, object] | None = None,
    edit_document: Callable[[dict[str, Any]], None] | None = None,
    keep_identity: bool = False,
    tail: str = "",
) -> None:
    """Insert a row by hand, bypassing the service, to see what the database itself refuses."""
    values = service._row_values(session, snapshot)
    if not keep_identity:
        values["id"] = uuid.uuid4()
        values["content_hash"] = uuid.uuid4().hex + uuid.uuid4().hex
    if edit_document is not None:
        edit_document(values["document"])  # type: ignore[arg-type]
    values.update(changes or {})
    for name in ("signal_data_quality", "context_data_quality"):
        values[name] = getattr(values[name], "value", values[name])
    values["document"] = json.dumps(values["document"])
    columns = ", ".join(values)
    marks = ", ".join(_placeholder(name) for name in values)
    session.execute(
        text(f"INSERT INTO freyja2_context_snapshots ({columns}) VALUES ({marks}){tail}"), values
    )


def _placeholder(name: str) -> str:
    if name == "document":
        return "CAST(:document AS jsonb)"
    if name.endswith("data_quality"):
        return f"CAST(:{name} AS freyja2_data_quality)"
    return f":{name}"


def test_the_raw_insert_helper_itself_is_sound(session: Session, instrument_id: str) -> None:
    _raw_insert(session, snapshot_of(instrument_id))  # unchanged values are accepted
    session.commit()
    assert count(session) == 1


def _set(path: tuple[str, ...], value: object) -> Callable[[dict[str, Any]], None]:
    """An edit of the stored document that keeps it consistent with a changed column."""

    def edit(document: dict[str, Any]) -> None:
        node = document
        for key in path[:-1]:
            node = node[key]
        node[path[-1]] = value

    return edit


_MATCHES = "ck_freyja2_context_snapshots_document_matches_columns"

# (changes, matching edit of the document, the constraint that alone must refuse the row).
# Where a column and the document are changed together, only the constraint under test fails.
_REFUSED_ROWS: list[tuple[str, dict[str, object], Any, str]] = [
    (
        "trends",
        {"signal_trend": "SIDEWAYS"},
        _set(("observed", "signal", "trend"), "SIDEWAYS"),
        "ck_freyja2_context_snapshots_trends",
    ),
    (
        "relationship",
        {"required_relationship": "MAYBE"},
        _set(("judged", "required_relationship"), "MAYBE"),
        "ck_freyja2_context_snapshots_relationship",
    ),
    (
        "orientation",
        {"orientation": "SIDEWAYS"},
        _set(("judged", "orientation"), "SIDEWAYS"),
        "ck_freyja2_context_snapshots_orientation",
    ),
    (
        "outcome",
        {"policy_outcome": "PERHAPS"},
        _set(("judged", "outcome"), "PERHAPS"),
        "ck_freyja2_context_snapshots_(outcome|compatibility)",  # both refuse it
    ),
    ("hash_length", {"content_hash": "short"}, None, "ck_freyja2_context_snapshots_hash_length"),
    (
        "policy_pair",
        {"policy_version": None},
        _set(("judged", "policy_version"), None),
        "ck_freyja2_context_snapshots_policy_pair",
    ),
    (
        "compatibility",
        {"context_compatible": None},
        _set(("judged", "context_compatible"), None),
        "ck_freyja2_context_snapshots_compatibility",
    ),
    (
        "reasons",
        {"reasons": ["POLICY_MISSING"]},
        None,
        "ck_freyja2_context_snapshots_reasons",
    ),
    (
        "document_object",
        {"document": ["not", "an", "object"]},
        None,
        "ck_freyja2_context_snapshots_document_(object|matches_columns)",  # both refuse it
    ),
    # A copy that says something else than the document does:
    ("copy_of_trend", {"context_trend": "RANGE"}, None, _MATCHES),
    ("copy_of_policy", {"policy_version": "another-version"}, None, _MATCHES),
    ("copy_of_session", {"market_session": "LONDON"}, None, _MATCHES),
    ("copy_of_quality", {"signal_data_quality": "DEGRADED"}, None, _MATCHES),
    ("copy_of_version", {"snapshot_version": "context-snapshot-v0"}, None, _MATCHES),
]


@pytest.mark.parametrize(
    ("changes", "edit_document", "constraint"),
    [case[1:] for case in _REFUSED_ROWS],
    ids=[case[0] for case in _REFUSED_ROWS],
)
def test_the_database_refuses_a_row_that_disagrees_with_itself(
    session: Session,
    instrument_id: str,
    changes: dict[str, object],
    edit_document: Callable[[dict[str, Any]], None] | None,
    constraint: str,
) -> None:
    with pytest.raises(IntegrityError, match=constraint):
        _raw_insert(
            session,
            snapshot_of(instrument_id),
            changes=changes,
            edit_document=edit_document,
        )
    session.rollback()
    assert count(session) == 0


def test_a_snapshot_computed_before_it_observes_is_refused_by_the_database(
    session: Session, instrument_id: str
) -> None:
    snapshot = snapshot_of(instrument_id)
    with pytest.raises(IntegrityError, match="computed_after_observed"):
        _raw_insert(
            session,
            snapshot,
            changes={"computed_at": snapshot.observed_at - timedelta(seconds=1)},
        )
    session.rollback()


def test_a_snapshot_must_name_real_catalog_rows(session: Session, instrument_id: str) -> None:
    snapshot = snapshot_of(instrument_id)
    for column, constraint in (
        ("instrument_id", "fk_freyja2_context_snapshots_instrument"),
        ("data_source_id", "fk_freyja2_context_snapshots_data_source"),
        ("signal_timeframe_id", "fk_freyja2_context_snapshots_signal_timeframe"),
        ("context_timeframe_id", "fk_freyja2_context_snapshots_context_timeframe"),
    ):
        with pytest.raises(IntegrityError, match=constraint):
            _raw_insert(session, snapshot, changes={column: uuid.uuid4()})
        session.rollback()


# -- what the service refuses -------------------------------------------------------------------


@pytest.mark.parametrize(
    "overrides",
    [
        {"instrument_id": "instrument-1"},  # not even an id
        {"instrument_id": str(uuid.uuid4())},  # an id the catalog does not have
        {"data_source": "NOWHERE", "authorized_sources": frozenset({"NOWHERE"})},
    ],
    ids=["not-an-id", "unknown-instrument", "unknown-source"],
)
def test_a_snapshot_of_something_the_catalog_lacks_is_refused_and_stores_nothing(
    session: Session, overrides: dict[str, Any]
) -> None:
    with pytest.raises(UnknownSnapshotReferenceError):
        store_context_snapshot(session, capture(**overrides))
    assert count(session) == 0


# -- a stored snapshot is never trusted blindly --------------------------------------------------


def test_a_stored_snapshot_that_no_longer_matches_its_hash_is_refused(
    session: Session, instrument_id: str, market_data_engine: Engine
) -> None:
    snapshot = snapshot_of(instrument_id)
    store_context_snapshot(session, snapshot)
    session.commit()
    session.close()

    # Someone gets around the trigger and rewrites a swing price in the stored document.
    tampered = snapshot.document(include_computed_at=False)
    tampered["observed"]["signal"]["swings"][0]["price"] = "999999.5"
    with market_data_engine.begin() as connection:
        connection.execute(text("ALTER TABLE freyja2_context_snapshots DISABLE TRIGGER USER"))
        try:
            connection.execute(
                text("UPDATE freyja2_context_snapshots SET document = CAST(:d AS jsonb)"),
                {"d": json.dumps(tampered)},
            )
        finally:
            connection.execute(text("ALTER TABLE freyja2_context_snapshots ENABLE TRIGGER USER"))

    fresh = create_session_factory(market_data_engine)()
    try:
        with pytest.raises(SnapshotIntegrityError, match="content hash"):
            load_context_snapshot(fresh, snapshot.snapshot_id)
    finally:
        fresh.close()


def test_a_snapshot_is_read_from_its_stored_document_and_nothing_is_recomputed(
    session: Session, instrument_id: str
) -> None:
    """The stored row keeps what was known then. A policy that changes its mind about the same
    trends later produces a different snapshot; loading the old one never asks it again."""
    original = snapshot_of(instrument_id)
    store_context_snapshot(session, original)
    later_policy = policy(
        version="strategy-x-trend-v2", relationship=TrendRelationship.COUNTER_TREND
    )
    revised = snapshot_of(instrument_id, trend_policy=later_policy)
    store_context_snapshot(session, revised)
    session.commit()
    session.expire_all()

    kept = load_context_snapshot(session, original.snapshot_id)
    assert kept is not None
    assert kept.outcome is PolicyOutcome.COMPATIBLE and kept.policy_version == (
        "strategy-x-trend-v1"
    )
    assert revised.outcome is PolicyOutcome.INCOMPATIBLE  # the newer policy, its own record
