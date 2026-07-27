import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from freyja_backend.db.base import Base

# Capability / activation tables (POINT1-CAPABILITY-001, corrected by
# POINT1-CAPABILITY-API-CORRECTION-001). Two concepts are kept physically and
# conceptually separate, never collapsed into a single
# `enabled`/`supported`/`real_execution` boolean:
#
#   1. TechnicalCapability   — what Freyja (or a venue/data source) knows how
#                              to do for an Instrument + venue-or-source +
#                              timeframe combination.
#   2. ExecutionContext      — what a specific owner's account may actually
#                              use, for a specific product, in a specific
#                              environment (DEMO/REAL), right now.
#
# ARCHITECTURAL DECISION (POINT1-CAPABILITY-API-CORRECTION-001): Freyja does
# not interpret or apply per-jurisdiction legislation, and does not maintain
# an internal legal/regulatory catalog. The connected broker is the sole
# authority over product availability and account permissions: the broker
# knows the account and its permissions, the broker reports what is
# available, and Freyja normalizes and respects that response — a rejection
# or an absence of information from the broker fails closed
# (venue_permission_status stays/goes to a non-positive state), never
# silently treated as permitted. Freyja never attempts to route around a
# broker restriction. There is no jurisdiction/client_classification/
# RegulatoryRule modeling anywhere in this module; a prior revision's
# internal regulatory-eligibility engine was removed by migration
# 0012_remove_regulatory_engine — see that migration for the removal itself
# and its documented reversibility limits. Technical
# capability, broker-reported permission, and user authorization remain
# three independent signals: none of them alone activates REAL trading.
#
# Instrument/Venue/DataSource/Timeframe/ProductType (POINT1-DB-001,
# POINT1-PROVIDER-001) are referenced by FK only, never modified, and never
# gain permission, availability, activation, or DEMO/REAL columns
# themselves.
#
# No credentials, tokens, API keys, or other secret material are stored
# anywhere here — only opaque status enums and `account_key`, an internal,
# opaque, non-secret identifier for which of an owner's several accounts at
# a venue a context refers to (see ExecutionContext). No CASCADE on any FK:
# deleting a referenced Instrument/Venue/DataSource/Timeframe/ProductType/
# AuthUser/ExecutionContext fails closed instead of silently discarding
# capability/activation history.


class CapabilityStatus(enum.StrEnum):
    """Per-dimension status of one technical capability. Deliberately five
    values, not a boolean: NOT_IMPLEMENTED means Freyja itself has not built
    this capability yet (e.g. backtesting before POINT15 exists) — a fact
    about Freyja, independent of any provider. NOT_EVALUATED means the
    capability could exist but no evidence has been gathered for this
    specific combination yet. NOT_APPLICABLE means the dimension is
    structurally meaningless for this row's provider axis — e.g. a
    DataSource (market-data-only) never executes or settles anything, so
    its demo_execution/real_execution/settlement dimensions are
    NOT_APPLICABLE, never NOT_EVALUATED or SUPPORTED (enforced physically,
    see TechnicalCapability). Absence of evidence is never read as
    SUPPORTED nor as NOT_SUPPORTED, and NOT_APPLICABLE is never conflated
    with either — each is its own explicit state."""

    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    NOT_EVALUATED = "NOT_EVALUATED"
    SUPPORTED = "SUPPORTED"
    NOT_SUPPORTED = "NOT_SUPPORTED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class ExecutionEnvironment(enum.StrEnum):
    DEMO = "DEMO"
    REAL = "REAL"


class CredentialsStatus(enum.StrEnum):
    """Status only — never the credential material itself. See
    ExecutionContext for the binding rule against storing secrets."""

    NOT_CONFIGURED = "NOT_CONFIGURED"
    CONFIGURED = "CONFIGURED"
    INVALID = "INVALID"


class VenuePermissionStatus(enum.StrEnum):
    """Permission/availability as reported and normalized from the
    connected broker/venue for this account — never a Freyja-computed legal
    or regulatory decision. GRANTED means the broker has confirmed the
    account may use this venue for the relevant product; DENIED means the
    broker has explicitly refused it; NOT_EVALUATED means Freyja has not yet
    queried or received a broker response. A broker rejection or an absent/
    unknown response is never read as GRANTED — see ExecutionContext's
    ENABLED CHECK."""

    NOT_EVALUATED = "NOT_EVALUATED"
    GRANTED = "GRANTED"
    DENIED = "DENIED"


class OwnerAuthorizationStatus(enum.StrEnum):
    NOT_AUTHORIZED = "NOT_AUTHORIZED"
    AUTHORIZED = "AUTHORIZED"


class ActivationStatus(enum.StrEnum):
    """An ExecutionContext's activation status. ENABLED is only reachable
    (enforced physically by a CHECK constraint on ExecutionContext, not
    merely by convention) when credentials_status, venue_permission_status,
    and owner_authorization_status are all simultaneously in their positive
    state. Explicit user authorization and Freyja's own risk controls remain
    separate, mandatory requirements — none of technical capability, broker
    permission, or user authorization alone activates REAL trading."""

    NOT_CONFIGURED = "NOT_CONFIGURED"
    CONFIGURED = "CONFIGURED"
    ENABLED = "ENABLED"
    SUSPENDED = "SUSPENDED"


class TechnicalCapability(Base):
    """What Freyja (and/or a venue/data source) is technically capable of
    for one Instrument + (venue XOR data source) + Timeframe combination —
    never an authorization, never an activation. A row here never implies
    the broker permits use, nor that any ExecutionContext may enable it.

    A DataSource is market-data-only by construction (POINT1-PROVIDER-001):
    it never executes or settles anything, so a data-source-linked row must
    declare demo_execution_status, real_execution_status, and
    settlement_status as NOT_APPLICABLE — enforced physically below, never
    left to silently default to NOT_EVALUATED or SUPPORTED. A venue-linked
    row evaluates all six dimensions normally; none of them is ever
    defaulted to SUPPORTED.

    Versioned by effective_from/effective_to: multiple historical (closed)
    rows may exist for the same combination, but the partial unique index
    below allows only one currently-open (effective_to IS NULL) row per
    combination — proven by tests to permit legitimate re-evaluation over
    time without colliding.
    """

    __tablename__ = "freyja2_technical_capabilities"
    __table_args__ = (
        CheckConstraint(
            "(venue_id IS NOT NULL AND data_source_id IS NULL) "
            "OR (venue_id IS NULL AND data_source_id IS NOT NULL)",
            name="ck_freyja2_technical_capabilities_exactly_one_provider_axis",
        ),
        CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name="ck_freyja2_technical_capabilities_valid_effective_window",
        ),
        # Bidirectional: reason_unavailable is required, non-blank, and
        # trimmed if AND ONLY IF at least one dimension is NOT_SUPPORTED.
        # NOT_IMPLEMENTED, NOT_EVALUATED, and NOT_APPLICABLE never justify a
        # reason by themselves, and a reason may never be attached when
        # nothing is actually NOT_SUPPORTED.
        CheckConstraint(
            "("
            "market_data_status = 'NOT_SUPPORTED' "
            "OR signal_detection_status = 'NOT_SUPPORTED' "
            "OR backtest_status = 'NOT_SUPPORTED' "
            "OR demo_execution_status = 'NOT_SUPPORTED' "
            "OR real_execution_status = 'NOT_SUPPORTED' "
            "OR settlement_status = 'NOT_SUPPORTED'"
            ") = ("
            "reason_unavailable IS NOT NULL "
            "AND char_length(btrim(reason_unavailable)) > 0 "
            "AND reason_unavailable = btrim(reason_unavailable)"
            ")",
            name="ck_freyja2_technical_capabilities_reason_iff_not_supported",
        ),
        # A DataSource never executes or settles anything — those three
        # dimensions must be NOT_APPLICABLE whenever data_source_id is set.
        # Venue-linked rows are unconstrained here: they evaluate normally
        # (default NOT_EVALUATED, never auto-SUPPORTED).
        CheckConstraint(
            "data_source_id IS NULL OR ("
            "demo_execution_status = 'NOT_APPLICABLE' "
            "AND real_execution_status = 'NOT_APPLICABLE' "
            "AND settlement_status = 'NOT_APPLICABLE'"
            ")",
            name="ck_freyja2_technical_capabilities_data_source_not_applicable",
        ),
        Index("ix_freyja2_technical_capabilities_instrument_id", "instrument_id"),
        Index("ix_freyja2_technical_capabilities_venue_id", "venue_id"),
        Index("ix_freyja2_technical_capabilities_data_source_id", "data_source_id"),
        Index("ix_freyja2_technical_capabilities_timeframe_id", "timeframe_id"),
        # Only the currently-open row per combination must be unique — closed
        # (historical) rows for the same combination are explicitly allowed,
        # so re-evaluating a combination over time never collides. Two
        # partial indexes instead of one composite index over
        # (venue_id, data_source_id): those two columns are never both set
        # (see the exactly-one-axis CHECK above), and a plain UNIQUE index
        # would treat every NULL as distinct from every other NULL — the
        # constraint would never actually fire on whichever column is
        # always NULL. Same fix POINT1-PROVIDER-001 already applied to
        # VenueInstrument.provider_contract_id, applied here for the same
        # reason.
        Index(
            "uq_freyja2_technical_capabilities_current_by_venue",
            "instrument_id",
            "venue_id",
            "timeframe_id",
            unique=True,
            postgresql_where=text("effective_to IS NULL AND venue_id IS NOT NULL"),
        ),
        Index(
            "uq_freyja2_technical_capabilities_current_by_data_source",
            "instrument_id",
            "data_source_id",
            "timeframe_id",
            unique=True,
            postgresql_where=text("effective_to IS NULL AND data_source_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("freyja2_instruments.instrument_id"), nullable=False
    )
    venue_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("freyja2_venues.id")
    )
    data_source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("freyja2_data_sources.id")
    )
    timeframe_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("freyja2_timeframes.id"), nullable=False
    )
    market_data_status: Mapped[CapabilityStatus] = mapped_column(
        Enum(CapabilityStatus, name="freyja2_capability_status", native_enum=True),
        nullable=False,
        default=CapabilityStatus.NOT_EVALUATED,
    )
    signal_detection_status: Mapped[CapabilityStatus] = mapped_column(
        Enum(CapabilityStatus, name="freyja2_capability_status", native_enum=True),
        nullable=False,
        default=CapabilityStatus.NOT_EVALUATED,
    )
    backtest_status: Mapped[CapabilityStatus] = mapped_column(
        Enum(CapabilityStatus, name="freyja2_capability_status", native_enum=True),
        nullable=False,
        default=CapabilityStatus.NOT_EVALUATED,
    )
    demo_execution_status: Mapped[CapabilityStatus] = mapped_column(
        Enum(CapabilityStatus, name="freyja2_capability_status", native_enum=True),
        nullable=False,
        default=CapabilityStatus.NOT_EVALUATED,
    )
    real_execution_status: Mapped[CapabilityStatus] = mapped_column(
        Enum(CapabilityStatus, name="freyja2_capability_status", native_enum=True),
        nullable=False,
        default=CapabilityStatus.NOT_EVALUATED,
    )
    settlement_status: Mapped[CapabilityStatus] = mapped_column(
        Enum(CapabilityStatus, name="freyja2_capability_status", native_enum=True),
        nullable=False,
        default=CapabilityStatus.NOT_EVALUATED,
    )
    reason_unavailable: Mapped[str | None] = mapped_column(Text())
    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"TechnicalCapability(id={self.id!r}, instrument_id={self.instrument_id!r}, "
            f"timeframe_id={self.timeframe_id!r})"
        )


class ExecutionContext(Base):
    """What a specific owner's account may actually use, for a specific
    product, in a specific execution_environment (DEMO or REAL), at a
    specific venue — never a second trading engine. DEMO and REAL are two
    rows of the same table, sharing every StrategySpec/business rule/
    execution contract; only the account, endpoint, or credentials
    referenced by this row differ.

    account_key is an internal, opaque, non-secret identifier distinguishing
    an owner's several accounts at the same venue (e.g. a hedged sub-account
    or a second broker account) — it is NEVER a credential, API key, token,
    or anything a broker/exchange issues as a secret. It is chosen by
    Freyja/the owner purely for bookkeeping, so two different accounts at
    the same venue+environment+product never collide, and the same account
    can hold independent contexts per product (e.g. BINARY_OPTION REAL
    SUSPENDED while SPOT REAL is independently NOT_CONFIGURED for the very
    same account).

    No credentials, tokens, or secret material are stored — only status
    enums and the opaque account_key. activation_status = ENABLED is
    enforced physically (CHECK below) to require credentials_status =
    CONFIGURED, venue_permission_status = GRANTED (i.e. the broker has
    confirmed this account may use this venue/product), and
    owner_authorization_status = AUTHORIZED simultaneously — no combination
    of contradictory values can be persisted as ENABLED. Freyja does not
    additionally gate ENABLED on any internal jurisdiction/regulatory
    determination: availability and permissions are the broker's authority,
    normalized here as venue_permission_status, and a broker denial or an
    unevaluated/unknown broker response fails closed exactly like a missing
    credential or a missing user authorization does.

    A SUSPENDED context (e.g. BINARY_OPTION REAL for a specific
    owner/account) never implies a global product suspension — it is scoped
    to exactly this (owner, venue, account, environment, product) row; a
    different product_type_id for the very same account is an entirely
    independent row.
    """

    __tablename__ = "freyja2_execution_contexts"
    __table_args__ = (
        CheckConstraint(
            "activation_status <> 'ENABLED' OR ("
            "credentials_status = 'CONFIGURED' "
            "AND venue_permission_status = 'GRANTED' "
            "AND owner_authorization_status = 'AUTHORIZED'"
            ")",
            name="ck_freyja2_execution_contexts_enabled_requires_all_positive",
        ),
        CheckConstraint(
            "(activation_status = 'SUSPENDED' AND suspension_reasons IS NOT NULL "
            "AND cardinality(suspension_reasons) > 0) "
            "OR (activation_status <> 'SUSPENDED' "
            "AND (suspension_reasons IS NULL OR cardinality(suspension_reasons) = 0))",
            name="ck_freyja2_execution_contexts_suspension_reasons_consistency",
        ),
        # Beyond non-empty-when-SUSPENDED (above), every element of the
        # array (when present) must itself be non-null, non-blank after
        # trim, AND already equal to its own trimmed form (no padding) —
        # enforced via a small IMMUTABLE SQL function, since a plain CHECK
        # expression cannot contain a subquery/iterate over array elements
        # on its own.
        CheckConstraint(
            "freyja2_text_array_all_nonblank(suspension_reasons)",
            name="ck_freyja2_execution_contexts_suspension_reasons_elements_valid",
        ),
        CheckConstraint(
            "char_length(btrim(account_key)) > 0",
            name="ck_freyja2_execution_contexts_account_key_not_blank",
        ),
        CheckConstraint(
            "account_key = btrim(account_key)",
            name="ck_freyja2_execution_contexts_account_key_trimmed",
        ),
        # One context per owner+venue+account+environment+product — a
        # different owner, venue, account, DEMO/REAL environment, or product
        # each add a distinct row, never collide. Proven by tests: two
        # accounts for the same owner+venue+environment+product; the same
        # account across two different products; DEMO vs REAL for the same
        # account+product.
        Index(
            "uq_freyja2_execution_contexts_identity",
            "owner_id",
            "venue_id",
            "account_key",
            "execution_environment",
            "product_type_id",
            unique=True,
        ),
        Index("ix_freyja2_execution_contexts_owner_id", "owner_id"),
        Index("ix_freyja2_execution_contexts_venue_id", "venue_id"),
        Index("ix_freyja2_execution_contexts_product_type_id", "product_type_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("auth_users.id"), nullable=False
    )
    venue_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("freyja2_venues.id"), nullable=False
    )
    account_key: Mapped[str] = mapped_column(String(64), nullable=False)
    execution_environment: Mapped[ExecutionEnvironment] = mapped_column(
        Enum(ExecutionEnvironment, name="freyja2_execution_environment", native_enum=True),
        nullable=False,
    )
    product_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("freyja2_product_types.id"), nullable=False
    )
    credentials_status: Mapped[CredentialsStatus] = mapped_column(
        Enum(CredentialsStatus, name="freyja2_credentials_status", native_enum=True),
        nullable=False,
        default=CredentialsStatus.NOT_CONFIGURED,
    )
    venue_permission_status: Mapped[VenuePermissionStatus] = mapped_column(
        Enum(VenuePermissionStatus, name="freyja2_venue_permission_status", native_enum=True),
        nullable=False,
        default=VenuePermissionStatus.NOT_EVALUATED,
    )
    owner_authorization_status: Mapped[OwnerAuthorizationStatus] = mapped_column(
        Enum(OwnerAuthorizationStatus, name="freyja2_owner_authorization_status", native_enum=True),
        nullable=False,
        default=OwnerAuthorizationStatus.NOT_AUTHORIZED,
    )
    activation_status: Mapped[ActivationStatus] = mapped_column(
        Enum(ActivationStatus, name="freyja2_activation_status", native_enum=True),
        nullable=False,
        default=ActivationStatus.NOT_CONFIGURED,
    )
    suspension_reasons: Mapped[list[str] | None] = mapped_column(ARRAY(Text()))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"ExecutionContext(id={self.id!r}, owner_id={self.owner_id!r}, "
            f"venue_id={self.venue_id!r}, account_key={self.account_key!r}, "
            f"execution_environment={self.execution_environment!r}, "
            f"activation_status={self.activation_status!r})"
        )
