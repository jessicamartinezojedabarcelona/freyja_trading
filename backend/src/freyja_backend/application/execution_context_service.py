import uuid

from sqlalchemy.orm import Session

from freyja_backend.db.models.capability import ExecutionEnvironment, RegulatoryRule
from freyja_backend.dto.catalog import ProductTypeRef
from freyja_backend.dto.execution_context import ExecutionContextOut, RegulatoryRuleEvidenceOut
from freyja_backend.dto.pagination import Page
from freyja_backend.dto.provider import VenueOut
from freyja_backend.repositories import execution_context_repository as ec_repository
from freyja_backend.repositories.execution_context_repository import ExecutionContextRow


def _regulatory_rule_evidence(rule: RegulatoryRule) -> RegulatoryRuleEvidenceOut:
    return RegulatoryRuleEvidenceOut(
        id=rule.id,
        jurisdiction=rule.jurisdiction,
        client_classification=rule.client_classification,
        effect=rule.effect,
        source_citation=rule.source_citation,
        verified_at=rule.verified_at,
        effective_from=rule.effective_from,
        effective_to=rule.effective_to,
    )


def _execution_context_out(
    row: ExecutionContextRow, regulatory_rules: list[RegulatoryRule]
) -> ExecutionContextOut:
    context = row.execution_context
    return ExecutionContextOut(
        id=context.id,
        account_key=context.account_key,
        venue=VenueOut(
            id=row.venue.id,
            code=row.venue.code,
            display_name=row.venue.display_name,
            venue_type=row.venue.venue_type,
            is_active=row.venue.is_active,
        ),
        product_type=ProductTypeRef(
            id=row.product_type.id,
            code=row.product_type.code,
            display_name=row.product_type.display_name,
        ),
        execution_environment=context.execution_environment,
        jurisdiction=context.jurisdiction,
        client_classification=context.client_classification,
        credentials_status=context.credentials_status,
        venue_permission_status=context.venue_permission_status,
        regulatory_eligibility_status=context.regulatory_eligibility_status,
        owner_authorization_status=context.owner_authorization_status,
        activation_status=context.activation_status,
        suspension_reasons=context.suspension_reasons,
        regulatory_rules=[_regulatory_rule_evidence(rule) for rule in regulatory_rules],
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
) -> Page[ExecutionContextOut]:
    rows, total = ec_repository.list_execution_contexts(
        session,
        owner_id=owner_id,
        venue_id=venue_id,
        product_type_id=product_type_id,
        execution_environment=execution_environment,
        limit=limit,
        offset=offset,
    )
    context_ids = [row.execution_context.id for row in rows]
    rules_by_context = ec_repository.load_regulatory_rules_for_contexts(session, context_ids)
    items = [
        _execution_context_out(row, rules_by_context.get(row.execution_context.id, []))
        for row in rows
    ]
    return Page(items=items, total=total, limit=limit, offset=offset)


def get_execution_context(
    session: Session, *, context_id: uuid.UUID, owner_id: uuid.UUID
) -> ExecutionContextOut | None:
    row = ec_repository.get_execution_context(session, context_id=context_id, owner_id=owner_id)
    if row is None:
        return None
    rules_by_context = ec_repository.load_regulatory_rules_for_contexts(
        session, [row.execution_context.id]
    )
    return _execution_context_out(row, rules_by_context.get(row.execution_context.id, []))
