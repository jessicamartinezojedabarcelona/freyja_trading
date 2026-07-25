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

# Capability / eligibility / activation tables (POINT1-CAPABILITY-001).
# Three concepts are kept physically and conceptually separate, never
# collapsed into a single `enabled`/`supported`/`real_execution` boolean:
#
#   1. TechnicalCapability   — what Freyja (or a venue/data source) knows how
#                              to do for an Instrument + venue-or-source +
#                              timeframe combination.
#   2. RegulatoryRule        — what is permitted, restricted, or not yet
#                              evaluated for a jurisdiction/client
#                              classification/product/venue combination.
#   3. ExecutionContext      — what a specific owner's account may actually
#                              use, in a specific environment (DEMO/REAL),
#                              right now.
#
# Instrument/Venue/DataSource/Timeframe (POINT1-DB-001, POINT1-PROVIDER-001)
# are referenced by FK only, never modified, and never gain permission,
# availability, activation, jurisdiction, or DEMO/REAL columns themselves.
#
# No credentials, tokens, API keys, or other secret material are stored
# anywhere here — only opaque status enums. No CASCADE on any FK: deleting a
# referenced Instrument/Venue/DataSource/Timeframe/AuthUser/RegulatoryRule
# fails closed instead of silently discarding capability/eligibility/
# activation history.


class CapabilityStatus(enum.StrEnum):
    """Per-dimension status of one technical capability. Deliberately four
    values, not a boolean: NOT_IMPLEMENTED means Freyja itself has not built
    this capability yet (e.g. backtesting before POINT15 exists) — a fact
    about Freyja, independent of any provider. NOT_EVALUATED means the
    capability could exist but no evidence has been gathered for this
    specific combination yet. Absence of evidence is never read as
    SUPPORTED nor as NOT_SUPPORTED — it is its own explicit state."""

    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    NOT_EVALUATED = "NOT_EVALUATED"
    SUPPORTED = "SUPPORTED"
    NOT_SUPPORTED = "NOT_SUPPORTED"


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
    NOT_EVALUATED = "NOT_EVALUATED"
    GRANTED = "GRANTED"
    DENIED = "DENIED"


class RegulatoryEligibilityStatus(enum.StrEnum):
    NOT_EVALUATED = "NOT_EVALUATED"
    ELIGIBLE = "ELIGIBLE"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"


class OwnerAuthorizationStatus(enum.StrEnum):
    NOT_AUTHORIZED = "NOT_AUTHORIZED"
    AUTHORIZED = "AUTHORIZED"


class ActivationStatus(enum.StrEnum):
    """An ExecutionContext's activation status. ENABLED is only reachable
    (enforced physically by a CHECK constraint on ExecutionContext, not
    merely by convention) when credentials_status, venue_permission_status,
    regulatory_eligibility_status, and owner_authorization_status are all
    simultaneously in their positive state."""

    NOT_CONFIGURED = "NOT_CONFIGURED"
    CONFIGURED = "CONFIGURED"
    ENABLED = "ENABLED"
    SUSPENDED = "SUSPENDED"


class RegulatoryRuleEffect(enum.StrEnum):
    ELIGIBLE = "ELIGIBLE"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"


class TechnicalCapability(Base):
    """What Freyja (and/or a venue/data source) is technically capable of
    for one Instrument + (venue XOR data source) + Timeframe combination —
    never an authorization, never an activation. A row here never implies a
    RegulatoryRule permits use, nor that any ExecutionContext may enable it.

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
        CheckConstraint(
            "(reason_unavailable IS NOT NULL AND char_length(btrim(reason_unavailable)) > 0) "
            "OR ("
            "market_data_status <> 'NOT_SUPPORTED' "
            "AND signal_detection_status <> 'NOT_SUPPORTED' "
            "AND backtest_status <> 'NOT_SUPPORTED' "
            "AND demo_execution_status <> 'NOT_SUPPORTED' "
            "AND real_execution_status <> 'NOT_SUPPORTED' "
            "AND settlement_status <> 'NOT_SUPPORTED'"
            ")",
            name="ck_freyja2_technical_capabilities_reason_needed_if_unsupported",
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


class RegulatoryRule(Base):
    """A versionable, citable regulatory determination — never inferred,
    never invented. jurisdiction is a free, non-blank/trimmed identifier
    (e.g. an ISO country/region code); client_classification, product_type,
    and venue are nullable, meaning the rule applies regardless of that
    dimension when left unset. source_citation and verified_at exist so the
    rule is always traceable to an actual official source someone can
    review — never asserted without evidence."""

    __tablename__ = "freyja2_regulatory_rules"
    __table_args__ = (
        CheckConstraint(
            "char_length(btrim(jurisdiction)) > 0",
            name="ck_freyja2_regulatory_rules_jurisdiction_not_blank",
        ),
        CheckConstraint(
            "jurisdiction = btrim(jurisdiction)",
            name="ck_freyja2_regulatory_rules_jurisdiction_trimmed",
        ),
        CheckConstraint(
            "client_classification IS NULL OR ("
            "char_length(btrim(client_classification)) > 0 "
            "AND client_classification = btrim(client_classification)"
            ")",
            name="ck_freyja2_regulatory_rules_client_classification_shape",
        ),
        CheckConstraint(
            "char_length(btrim(source_citation)) > 0",
            name="ck_freyja2_regulatory_rules_source_citation_not_blank",
        ),
        CheckConstraint(
            "source_citation = btrim(source_citation)",
            name="ck_freyja2_regulatory_rules_source_citation_trimmed",
        ),
        CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name="ck_freyja2_regulatory_rules_valid_effective_window",
        ),
        Index("ix_freyja2_regulatory_rules_jurisdiction", "jurisdiction"),
        Index("ix_freyja2_regulatory_rules_product_type_id", "product_type_id"),
        Index("ix_freyja2_regulatory_rules_venue_id", "venue_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    jurisdiction: Mapped[str] = mapped_column(String(32), nullable=False)
    client_classification: Mapped[str | None] = mapped_column(String(32))
    product_type_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("freyja2_product_types.id")
    )
    venue_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("freyja2_venues.id")
    )
    effect: Mapped[RegulatoryRuleEffect] = mapped_column(
        Enum(RegulatoryRuleEffect, name="freyja2_regulatory_rule_effect", native_enum=True),
        nullable=False,
    )
    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_citation: Mapped[str] = mapped_column(Text(), nullable=False)
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"RegulatoryRule(id={self.id!r}, jurisdiction={self.jurisdiction!r}, "
            f"effect={self.effect!r})"
        )


class ExecutionContext(Base):
    """What a specific owner's account may actually use, in a specific
    execution_environment (DEMO or REAL), at a specific venue — never a
    second trading engine. DEMO and REAL are two rows of the same table,
    sharing every StrategySpec/business rule/execution contract; only the
    account, endpoint, or credentials referenced by this row differ.

    No credentials, tokens, or secret material are stored — only status
    enums. activation_status = ENABLED is enforced physically (CHECK below)
    to require credentials_status = CONFIGURED, venue_permission_status =
    GRANTED, regulatory_eligibility_status = ELIGIBLE, and
    owner_authorization_status = AUTHORIZED simultaneously — no combination
    of contradictory values can be persisted as ENABLED.

    A SUSPENDED context (e.g. BINARY_OPTION REAL for a specific
    owner/jurisdiction) never implies a global product suspension — it is
    scoped to exactly this (owner, venue, environment) row.
    """

    __tablename__ = "freyja2_execution_contexts"
    __table_args__ = (
        CheckConstraint(
            "activation_status <> 'ENABLED' OR ("
            "credentials_status = 'CONFIGURED' "
            "AND venue_permission_status = 'GRANTED' "
            "AND regulatory_eligibility_status = 'ELIGIBLE' "
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
        CheckConstraint(
            "char_length(btrim(jurisdiction)) > 0",
            name="ck_freyja2_execution_contexts_jurisdiction_not_blank",
        ),
        CheckConstraint(
            "jurisdiction = btrim(jurisdiction)",
            name="ck_freyja2_execution_contexts_jurisdiction_trimmed",
        ),
        CheckConstraint(
            "char_length(btrim(client_classification)) > 0",
            name="ck_freyja2_execution_contexts_client_classification_not_blank",
        ),
        CheckConstraint(
            "client_classification = btrim(client_classification)",
            name="ck_freyja2_execution_contexts_client_classification_trimmed",
        ),
        # One context per owner+venue+environment — additional owners,
        # venues, or environments (DEMO vs REAL) each add a distinct row,
        # never collide.
        Index(
            "uq_freyja2_execution_contexts_owner_venue_environment",
            "owner_id",
            "venue_id",
            "execution_environment",
            unique=True,
        ),
        Index("ix_freyja2_execution_contexts_owner_id", "owner_id"),
        Index("ix_freyja2_execution_contexts_venue_id", "venue_id"),
        Index("ix_freyja2_execution_contexts_regulatory_rule_id", "regulatory_rule_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("auth_users.id"), nullable=False
    )
    venue_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("freyja2_venues.id"), nullable=False
    )
    execution_environment: Mapped[ExecutionEnvironment] = mapped_column(
        Enum(ExecutionEnvironment, name="freyja2_execution_environment", native_enum=True),
        nullable=False,
    )
    jurisdiction: Mapped[str] = mapped_column(String(32), nullable=False)
    client_classification: Mapped[str] = mapped_column(String(32), nullable=False)
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
    regulatory_eligibility_status: Mapped[RegulatoryEligibilityStatus] = mapped_column(
        Enum(
            RegulatoryEligibilityStatus,
            name="freyja2_regulatory_eligibility_status",
            native_enum=True,
        ),
        nullable=False,
        default=RegulatoryEligibilityStatus.NOT_EVALUATED,
    )
    regulatory_rule_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("freyja2_regulatory_rules.id")
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
            f"venue_id={self.venue_id!r}, execution_environment={self.execution_environment!r}, "
            f"activation_status={self.activation_status!r})"
        )
