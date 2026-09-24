"""Proposal confirm/cancel and Talk-to-a-human handoff (E6-S2, E6-S3, E7-S1;
api-contracts.md 3.8). Split out of `chat.py` (which owns conversation/
message endpoints) to keep both routers under the code-gen skill's 300-line
block threshold; mounted onto the same `/api/chat/conversations` path
prefix so the public surface is unchanged.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Header, Request, Response, status

from collectai.api.deps import AuditServiceDep, ClockDep, DbSession, PolicyProviderDep
from collectai.api.middleware.error_types import HandoffFailedError
from collectai.api.middleware.errors import (
    AuditUnavailableError,
    ConflictError,
    NotFoundError,
    RequestValidationFailedError,
    resolve_correlation_id,
)
from collectai.api.routers import me_views
from collectai.api.routers._chat_views import message_view
from collectai.api.routers.chat import ChatBoundCustomerId, SettingsDep
from collectai.api.routers.me_ownership import require_owned
from collectai.api.schemas.chat_proposals import (
    CancelProposalResult,
    ConfirmRequest,
    ConfirmResult,
    HandoffRequest,
    HandoffResult,
)
from collectai.application import confirmation_flow
from collectai.application._chat_persistence import persist_message
from collectai.application._confirmation_exceptions import (
    ConfirmIdempotencyReuseError,
    ProposalAmbiguousValidationError,
    ProposalConflictError,
    ProposalInvalidError,
    ProposalNotFoundError,
)
from collectai.audit.service import AuditUnavailable
from collectai.domain_services import proposal_service
from collectai.domain_services.escalation_service import create_escalation
from collectai.domain_services.idempotency import IdempotencyService
from collectai.persistence.orm.conversation import ConversationOrm
from collectai.types.enums import (
    CaseSource,
    ContentSource,
    ConversationStatus,
    EscalationReason,
    MessageLabel,
    MessageRole,
    Persona,
)
from collectai.types.reason_codes import ReasonCode

router = APIRouter(prefix="/api/chat/conversations", tags=["Chat"])

_CHAT_USE = {"x-capability": "chat:use"}
_NOT_FOUND_MESSAGE = "The requested resource does not exist or is not visible to this account."


def _require_idempotency_key(idempotency_key: str) -> None:
    if not idempotency_key:
        raise RequestValidationFailedError(
            reason_code=ReasonCode.IDEMPOTENCY_KEY_REQUIRED,
            message="Idempotency-Key is required for this endpoint.",
        )


@router.post(
    "/{conversation_id}/proposals/{proposal_id}/confirm",
    response_model=ConfirmResult,
    status_code=status.HTTP_201_CREATED,
    openapi_extra=_CHAT_USE,
)
async def confirm_proposal_endpoint(
    conversation_id: str,
    proposal_id: str,
    body: ConfirmRequest,
    request: Request,
    response: Response,
    db: DbSession,
    clock: ClockDep,
    audit_service: AuditServiceDep,
    policy_provider: PolicyProviderDep,
    customer_id: ChatBoundCustomerId,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> ConfirmResult:
    _require_idempotency_key(idempotency_key)
    conversation = await require_owned(
        db,
        request,
        audit_service,
        customer_id,
        ConversationOrm,
        ConversationOrm.conversation_id,
        conversation_id,
    )
    try:
        outcome = await confirmation_flow.confirm_proposal(
            db,
            conversation=conversation,
            proposal_id=proposal_id,
            terms_hash=body.terms_hash,
            customer_id=customer_id,
            persona=Persona.CUSTOMER,
            policy_provider=policy_provider,
            clock=clock,
            audit_service=audit_service,
            correlation_id=resolve_correlation_id(request),
            idempotency_key=idempotency_key,
        )
    except ProposalNotFoundError as exc:
        raise NotFoundError(message=_NOT_FOUND_MESSAGE) from exc
    except ProposalInvalidError as exc:
        raise ConflictError(
            reason_code=ReasonCode.PROPOSAL_INVALID, message=exc.message, context=exc.context
        ) from exc
    except ProposalConflictError as exc:
        raise ConflictError(
            reason_code=exc.reason_code, message=exc.message, context=exc.context
        ) from exc
    except ProposalAmbiguousValidationError as exc:
        raise ConflictError(
            reason_code=ReasonCode.AMBIGUOUS_VALIDATION,
            message="This could not be automatically authorized; a specialist has been notified.",
            context={"escalation_case_id": exc.escalation_case_id},
        ) from exc
    except ConfirmIdempotencyReuseError as exc:
        raise ConflictError(
            reason_code=ReasonCode.IDEMPOTENCY_KEY_REUSED, message=str(exc)
        ) from exc
    except AuditUnavailable as exc:
        raise AuditUnavailableError() from exc
    await db.commit()
    if outcome.replayed:
        response.status_code = status.HTTP_200_OK
        response.headers["Idempotent-Replayed"] = "true"
    return ConfirmResult.model_validate({**outcome.response_body, "replayed": outcome.replayed})


@router.post(
    "/{conversation_id}/proposals/{proposal_id}/cancel",
    response_model=CancelProposalResult,
    openapi_extra=_CHAT_USE,
)
async def cancel_proposal_endpoint(
    conversation_id: str,
    proposal_id: str,
    request: Request,
    db: DbSession,
    clock: ClockDep,
    audit_service: AuditServiceDep,
    customer_id: ChatBoundCustomerId,
) -> CancelProposalResult:
    conversation = await require_owned(
        db,
        request,
        audit_service,
        customer_id,
        ConversationOrm,
        ConversationOrm.conversation_id,
        conversation_id,
    )
    try:
        outcome = await confirmation_flow.cancel_proposal(
            db,
            conversation=conversation,
            proposal_id=proposal_id,
            customer_id=customer_id,
            clock=clock,
        )
    except ProposalNotFoundError as exc:
        raise NotFoundError(message=_NOT_FOUND_MESSAGE) from exc
    except ProposalInvalidError as exc:
        raise ConflictError(reason_code=ReasonCode.PROPOSAL_INVALID, message=exc.message) from exc
    await db.commit()
    return CancelProposalResult(
        proposal=proposal_service.to_wire(outcome.proposal),  # type: ignore[arg-type]
        assistant_message=message_view(outcome.assistant_message),
    )


@router.post(
    "/{conversation_id}/handoff",
    response_model=HandoffResult,
    status_code=status.HTTP_201_CREATED,
    openapi_extra=_CHAT_USE,
)
async def handoff_endpoint(
    conversation_id: str,
    body: HandoffRequest,
    request: Request,
    response: Response,
    db: DbSession,
    clock: ClockDep,
    audit_service: AuditServiceDep,
    policy_provider: PolicyProviderDep,
    settings: SettingsDep,
    customer_id: ChatBoundCustomerId,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> HandoffResult:
    """AC2 (E6-S5), AC1/AC3/AC4 (E7-S1): always allowed, never discouraged,
    and works without the AI provider -- this handler never touches
    `ai_orchestration`. `body.note` is accepted per the wire contract but
    not yet persisted anywhere (no field stores a customer handoff note)."""
    del body, settings
    _require_idempotency_key(idempotency_key)
    conversation = await require_owned(
        db,
        request,
        audit_service,
        customer_id,
        ConversationOrm,
        ConversationOrm.conversation_id,
        conversation_id,
    )
    correlation_id = resolve_correlation_id(request)
    idempotency_service = IdempotencyService(clock)
    try:
        creation = await create_escalation(
            db,
            reason=EscalationReason.REQUEST_HUMAN,
            customer_id=customer_id,
            account_id=conversation.account_id,
            conversation_id=conversation.conversation_id,
            item_id=None,
            source=CaseSource.CUSTOMER,
            policy_provider=policy_provider,
            clock=clock,
            audit_service=audit_service,
            correlation_id=correlation_id,
            idempotency_service=idempotency_service,
            idempotency_key=idempotency_key,
        )
    except AuditUnavailable as exc:
        raise HandoffFailedError() from exc

    conversation.status = ConversationStatus.HANDED_OFF.value
    escalation_view = me_views.escalation_view(creation.case)
    message = await persist_message(
        db,
        conversation_id=conversation.conversation_id,
        customer_id=customer_id,
        role=MessageRole.ASSISTANT,
        content=escalation_view.customer_message,
        content_source=ContentSource.TEMPLATE,
        labels=[MessageLabel.HUMAN_HANDOFF],
        created_at=clock.now(),
    )
    await db.commit()
    if not creation.created:
        response.status_code = status.HTTP_200_OK
        response.headers["Idempotent-Replayed"] = "true"
    return HandoffResult(
        escalation=escalation_view,
        assistant_message=message_view(message),
        replayed=not creation.created,
    )
